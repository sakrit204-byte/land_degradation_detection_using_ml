"""Independent-sensor corroboration of the Sentinel-2-derived labels.

Question: when S2 says "a persistent below-expectation decline starts at month s", does a DIFFERENT
sensor/organisation (Landsat 8/9, NASA/USGS, 30 m; MODIS Terra, NASA, 250 m) see a vegetation
anomaly at the same place and time? If S2 events were processing artefacts (cloud residue, offset
errors, tile mismatches) the other sensors would NOT agree.
Statistic: mean NDVI anomaly z of the other sensor over months s..s+3 for S2 event onsets vs. matched
controls (eligible pixel-months, same AOI and calendar month, no onset in the next 6 months).
AUC = P(z_event < z_control). 0.5 = no agreement.
"""
import json, sys, warnings
import numpy as np, pandas as pd, xarray as xr
from sklearn.metrics import roc_auc_score
from .config import AOIS, PROC, OUT, SEED
from . import tsops as ts

warnings.filterwarnings("ignore")
RES = OUT / "results"


def sensor_z(nc, ref_years, max_gap=1):
    da = xr.open_dataset(nc)["NDVI"]
    t = pd.DatetimeIndex(da.time.values)
    V = da.values.reshape(len(t), -1).astype(np.float32)
    V = ts.interp_short_gaps(V, max_gap)
    ref = (t.year >= ref_years[0]) & (t.year <= ref_years[1])
    mu = np.stack([np.nanmedian(V[ref & (t.month == m)], 0) for m in range(1, 13)])
    dev = V - mu[t.month - 1]
    sd = np.maximum(1.4826 * np.nanmedian(np.abs(dev[ref]), 0), 0.02)
    return pd.DataFrame(dev / sd, index=t), da.sizes["y"], da.sizes["x"]


def corroborate_aoi(key, n=6000, eval_from="2021-01"):
    d = PROC / key
    c = np.load(d / "cube.npz")
    times = pd.DatetimeIndex(pd.to_datetime(c["times"]))
    onset, elig, y = c["onset"], c["eligible"], c["y"].astype(np.float32)
    rr, cc = c["rr"].astype(int), c["cc"].astype(int)
    rng = np.random.default_rng(SEED)
    out = {}
    for name, nc, ref, res_m, pad in [("landsat", d / "landsat.nc", (2018, 2020), 30, 0),
                                     ("modis", d / "modis.nc", (2001, 2020), 250, 2500)]:
        if not nc.exists():
            continue
        Z, h, w = sensor_z(nc, ref)
        r2 = np.clip((rr * 10 + pad) // res_m, 0, h - 1); c2 = np.clip((cc * 10 + pad) // res_m, 0, w - 1)
        cell = r2 * w + c2
        tsel = times >= pd.Timestamp(eval_from)
        ev_t, ev_p = np.nonzero(onset & tsel[:, None])
        # controls: eligible, y == 0 (no onset within 6 months), same months
        ct_t, ct_p = np.nonzero(elig & (y == 0) & tsel[:, None])
        if len(ev_t) == 0:
            continue
        i = rng.choice(len(ev_t), min(n, len(ev_t)), replace=False)
        j = rng.choice(len(ct_t), min(n, len(ct_t)), replace=False)

        def window_mean(tt, pp):
            vals = []
            for t_, p_ in zip(tt, pp):
                ts_ = times[t_]
                win = Z.loc[ts_: ts_ + pd.DateOffset(months=3), :]
                v = win.iloc[:, cell[p_]].values if len(win) else np.array([np.nan])
                vals.append(np.nanmean(v) if np.isfinite(v).any() else np.nan)
            return np.array(vals)

        ze, zc = window_mean(ev_t[i], ev_p[i]), window_mean(ct_t[j], ct_p[j])
        ok_e, ok_c = np.isfinite(ze), np.isfinite(zc)
        if ok_e.sum() < 20 or ok_c.sum() < 20:
            out[name] = dict(note="insufficient overlapping observations", n_event=int(ok_e.sum()), n_control=int(ok_c.sum()))
            continue
        lab = np.r_[np.ones(ok_e.sum()), np.zeros(ok_c.sum())]
        auc = roc_auc_score(lab, -np.r_[ze[ok_e], zc[ok_c]])
        out[name] = dict(n_event=int(ok_e.sum()), n_control=int(ok_c.sum()),
                         z_event_median=float(np.median(ze[ok_e])), z_control_median=float(np.median(zc[ok_c])),
                         frac_event_below_minus1=float((ze[ok_e] < -1).mean()), frac_control_below_minus1=float((zc[ok_c] < -1).mean()),
                         auc_agreement=float(auc))
        np.savez(RES / f"corrob_{key}_{name}.npz", ze=ze[ok_e], zc=zc[ok_c])
    print(key, json.dumps(out), flush=True)
    return out


if __name__ == "__main__":
    allr = {}
    for a in (sys.argv[1:] or [a.key for a in AOIS]):
        try:
            allr[a] = corroborate_aoi(a)
        except FileNotFoundError as e:
            print(a, "missing", e)
    json.dump(allr, open(RES / "corroboration.json", "w"), indent=2)
