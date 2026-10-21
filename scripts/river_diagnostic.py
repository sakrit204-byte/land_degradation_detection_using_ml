"""Are 'degradation' events concentrated in river corridors and after wet periods? (user question, I-028)

Per AOI, from the stored cube (label-version onsets 2019-2025) and static layers:
  * river corridor = pixel was open water at any time (Sentinel-2 NDVI < 0 in >= 1 month, i.e. channel / flooded)
    OR JRC surface-water occurrence > 0 (1984-2020) OR within 150 m of such a pixel
  * onset rate per pixel-year inside vs outside the corridor -> rate ratio
  * rainfall context: 3-month rainfall anomaly (P3) at the onset month vs all months -> are onsets after wet spells?
Output: outputs/results/river_diagnostic.json
"""
import json, sys
sys.path.insert(0, ".")
import numpy as np, pandas as pd, xarray as xr
from scipy import ndimage
from care_ew.config import AOIS, PROC, OUT

res = {}
for a in AOIS:
    d = PROC / a.key
    if not (d / "cube.npz").exists():
        continue
    c = np.load(d / "cube.npz")
    H, W = int(c["H"]), int(c["W"])
    rr, cc = c["rr"].astype(int), c["cc"].astype(int)
    times = pd.to_datetime(c["times"])
    sel = (times >= "2019-01-01") & (times <= "2025-12-31")
    onset = c["onset"][sel]                                  # [T, N]
    ndvi = c["ndvi"].astype(np.float32)
    st = xr.open_dataset(d / "static.nc")
    occ = st["water_occ"].values
    water_any = np.zeros((H, W), bool)
    water_any[rr, cc] = (np.nan_to_num(ndvi, nan=1) < 0).any(0)
    water_any |= occ > 0
    water_any |= st["landcover"].values == 80
    corridor = ndimage.binary_dilation(water_any, iterations=15)        # 15 px = 150 m
    in_c = corridor[rr, cc]
    yrs = sel.sum() / 12
    n_on = onset.sum(0)
    r_in = n_on[in_c].sum() / max(in_c.sum(), 1) / yrs
    r_out = n_on[~in_c].sum() / max((~in_c).sum(), 1) / yrs
    share_onsets_in = n_on[in_c].sum() / max(n_on.sum(), 1)
    clim = pd.read_csv(d / "climate_monthly.csv", index_col=0, parse_dates=True)
    p3 = clim["P3"].reindex(times[sel]).values
    w = onset.sum(1)                                          # onsets per month
    p3_onset = float(np.nansum(p3 * w) / max(w.sum(), 1))    # onset-weighted mean P3
    p3_prev = clim["P3"].shift(1).reindex(times[sel]).values
    wet = p3_prev > 1.0                                      # preceded by a wet 3-month spell (> +1 sd)
    res[a.key] = dict(corridor_share_of_pixels=round(float(in_c.mean()), 3),
                      onset_rate_in_corridor=round(float(r_in), 4), onset_rate_outside=round(float(r_out), 4),
                      rate_ratio=round(float(r_in / r_out), 2) if r_out > 0 else None,
                      share_of_onsets_in_corridor=round(float(share_onsets_in), 3),
                      mean_P3_at_onsets=round(p3_onset, 2), mean_P3_all_months=round(float(np.nanmean(p3)), 2),
                      share_onsets_after_wet_spell=round(float(w[wet].sum() / max(w.sum(), 1)), 3),
                      share_months_after_wet_spell=round(float(np.mean(wet)), 3))
    print(a.key, res[a.key], flush=True)
    del c, ndvi, onset
json.dump(res, open(OUT / "results" / "river_diagnostic.json", "w"), indent=1)
