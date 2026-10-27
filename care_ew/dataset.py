"""Assemble the per-AOI analysis cube and the pixel-month training table."""
import sys, json, warnings
import numpy as np, pandas as pd, xarray as xr
from . import tsops as ts
from .config import AOIS, AOI_BY_KEY, PROC, LABEL, SEED, PIX_PER_AOI, BLOCK_PX, CALIB_YEARS
from .features import (LC_KEEP, LC_NAME, CLIM_COLS, HEAT_COLS, seasonal_baseline, fit_climate_model, build_features,
                       spatial_mean, peer_median)
from .labels import make_labels, below_expectation
from . import s2 as s2mod

warnings.filterwarnings("ignore", category=RuntimeWarning)
FEAT_START = pd.Timestamp("2019-01-01")   # need >= 24 months of residual history for resilience


def modis_features(aoi_key, times, rows, cols, n):
    """MODIS 250 m long-record anomaly + resilience, mapped to S2 pixels, lagged 1 month (the
    16-day composite starting in month m can extend into m+1)."""
    f = PROC / aoi_key / "modis.nc"
    if not f.exists():
        return None
    m = xr.open_dataset(f)["NDVI"]
    mt = pd.DatetimeIndex(m.time.values)
    V = m.values.reshape(len(mt), -1).astype(np.float32)
    V = ts.interp_short_gaps(V, 1)
    ref = (mt.year >= 2001) & (mt.year <= 2020)
    mu = np.stack([np.nanmedian(V[ref & (mt.month == k)], 0) for k in range(1, 13)])
    dev = V - mu[mt.month - 1]
    sd = np.maximum(1.4826 * np.nanmedian(np.abs(dev[ref]), 0), 0.02)
    z = dev / sd
    zd = z - ts.roll_mean(z, 12)
    ac1 = ts.roll_ac1(zd, 60, minp=36); var = ts.roll_var(zd, 60, minp=36)
    # map S2 pixel (row, col on 10 m grid) -> MODIS cell (250 m grid padded by 2.5 km = 10 cells)
    mr = np.clip((rows * 10 + 2500) // 250, 0, m.sizes["y"] - 1)
    mc = np.clip((cols * 10 + 2500) // 250, 0, m.sizes["x"] - 1)
    idx = (mr * m.sizes["x"] + mc).astype(int)
    out = {}
    for k, a in {"modis_z": z, "modis_ac1_60": ac1, "modis_var_60": var}.items():
        s = pd.DataFrame(a, index=mt).shift(1).reindex(times)   # 1-month lag
        out[k] = s.values[:, idx].astype(np.float32)
    return out


def lst_features(aoi_key, times, rows, cols, clim):
    """MODIS LST anomaly and LST - Tair anomaly per 1 km cell, z vs 2001-2020 same-month climatology, lagged
    1 month (an 8-day composite starting late in month m extends into m+1). Mapped to S2 pixels."""
    f = PROC / aoi_key / "lst.nc"
    if not f.exists():
        return None
    m = xr.open_dataset(f)["LST"]
    mt = pd.DatetimeIndex(m.time.values)
    V = m.values.reshape(len(mt), -1).astype(np.float32)
    if "T_C" in clim:
        tair = clim["T_C"].reindex(mt).values.astype(np.float32)[:, None]
    else:
        tair = np.zeros((len(mt), 1), np.float32)
    out = {}
    ref = (mt.year >= 2001) & (mt.year <= 2020)
    for name, A in (("lst", V), ("dT", V - tair)):
        mu = np.stack([np.nanmean(A[ref & (mt.month == k)], 0) for k in range(1, 13)])
        sd = np.stack([np.nanstd(A[ref & (mt.month == k)], 0) for k in range(1, 13)])
        z = (A - mu[mt.month - 1]) / np.maximum(sd[mt.month - 1], 0.5)
        out[name + "_z"], out[name + "_z3"] = z, ts.roll_mean(z, 3)
    mr = np.clip((rows * 10 + 2500) // 1000, 0, m.sizes["y"] - 1)
    mc = np.clip((cols * 10 + 2500) // 1000, 0, m.sizes["x"] - 1)
    idx = (mr * m.sizes["x"] + mc).astype(int)
    res = {}
    for k, a in out.items():
        res[k] = pd.DataFrame(a, index=mt).shift(1).reindex(times).values[:, idx].astype(np.float32)
    return res


def aoi_context(aoi_key, save_cube=True):
    """Everything computed on the FULL grid of one AOI (baseline, climate model, residuals, labels,
    spatial context). Pixel-level features are then produced by features_for(ctx, idx)."""
    aoi = AOI_BY_KEY[aoi_key]
    d = PROC / aoi.key
    s2 = s2mod.load(aoi.key)
    times = pd.DatetimeIndex(s2.time.values)
    months, years = times.month.values, times.year.values
    T, H, W = s2["NDVI"].shape
    st = xr.open_dataset(d / "static.nc")
    lc = st["landcover"].values
    nd_all = s2["NDVI"].values
    cal = (years >= CALIB_YEARS[0]) & (years <= CALIB_YEARS[1])
    valid_frac = np.isfinite(nd_all[cal]).mean(0)
    mask = np.isin(lc, LC_KEEP) & (valid_frac >= 0.3)
    rr, cc = np.nonzero(mask)
    N = len(rr)
    flat = lambda v: v[:, rr, cc].astype(np.float32)
    Y = flat(nd_all)
    observed = np.isfinite(Y)
    Yi = ts.interp_short_gaps(Y, LABEL.max_gap_fill)
    Yc, age = ts.causal_interp_short_gaps(Y, LABEL.max_gap_fill)
    mu, sigma = seasonal_baseline(Yi, months, years)
    zc = (Yc - mu[months - 1]) / sigma
    clim = pd.read_csv(d / "climate_monthly.csv", index_col=0, parse_dates=True)
    lcf = lc[rr, cc]
    zhat, cm_info = fit_climate_model(zc, lcf, clim, times)
    # peer-relative (LNS) residuals: subtract the same-class median at each month (D-014)
    Rabs_feat = zc - zhat
    dev_feat = Yc - mu[months - 1]
    peer_R = peer_median(Rabs_feat, lcf); peer_d = peer_median(dev_feat, lcf)
    R_feat = Rabs_feat - peer_R
    dev_abs = Yi - mu[months - 1]
    Rabs_lab = dev_abs / sigma - zhat
    R_lab = Rabs_lab - peer_median(Rabs_lab, lcf)
    dev_lab = dev_abs - peer_median(dev_abs, lcf)
    y, eligible, onset, below_lab, nxt = make_labels(R_lab, dev_lab, observed)

    def cube(v):
        c = np.full((T, H, W), np.nan, np.float32); c[:, rr, cc] = v; return c
    Rc, Zc = cube(R_feat), cube(zc)
    R_nb5 = spatial_mean(Rc, 5)[:, rr, cc]
    m21 = spatial_mean(Rc, 21); m21sq = spatial_mean(Rc * Rc, 21)
    R_nb21 = m21[:, rr, cc]; R_sd21 = np.sqrt(np.maximum(m21sq - m21 * m21, 0))[:, rr, cc]
    z_nb21 = spatial_mean(Zc, 21)[:, rr, cc]
    del Rc, Zc, m21, m21sq
    below_feat = below_expectation(R_feat, dev_feat - peer_d)
    aoi_frac = below_feat.mean(1)
    dist = np.load(d / "dist_river_km.npy")[rr, cc] if (d / "dist_river_km.npy").exists() else np.full(N, np.nan, np.float32)
    clim_X = clim.reindex(times)[CLIM_COLS].astype(np.float32)
    others = {k: flat(s2[k].values) for k in ("NDMI", "NBR", "BSI")}
    # ecosystem structure & function layers (A8, D-020): water / paddy flags, 210 m water, 30 m texture
    from .ecofunc import full_grid
    eco = full_grid(None, T, H, W, rr, cc, Y, others["NDMI"], flat(s2["R"].values), flat(s2["G"].values))
    # nonlinear spatial early-warning signals (A9, D-021), computed 12 months at a time to bound memory
    from .nonlinear import spatial_ews, patch_stats
    nl_sp = {k: np.full((T, N), np.nan, np.float16) for k in ("sp_skew", "sp_moran", "vf", "lp", "al")}
    veg_thr = float(np.nanmedian(Yc[cal]))      # one vegetation threshold per AOI (calibration years)
    for t0 in range(0, T, 12):
        t1 = min(T, t0 + 12)
        Rc_ = np.full((t1 - t0, H, W), np.nan, np.float32); Rc_[:, rr, cc] = R_feat[t0:t1]
        sk_, mo_ = spatial_ews(Rc_)
        nl_sp["sp_skew"][t0:t1] = sk_[:, rr, cc]; nl_sp["sp_moran"][t0:t1] = mo_[:, rr, cc]
        Yc_ = np.full((t1 - t0, H, W), np.nan, np.float32); Yc_[:, rr, cc] = Yc[t0:t1]
        vf_, lp_, al_ = patch_stats(Yc_, veg_thr=veg_thr)
        nl_sp["vf"][t0:t1] = vf_[:, rr, cc]; nl_sp["lp"][t0:t1] = lp_[:, rr, cc]; nl_sp["al"][t0:t1] = al_[:, rr, cc]
        del Rc_, Yc_, sk_, mo_, vf_, lp_, al_
    if save_cube:
        np.savez_compressed(d / "cube.npz", rr=rr.astype(np.int16), cc=cc.astype(np.int16), H=H, W=W,
                            times=times.values.astype("datetime64[M]").astype(str),
                            R=R_feat.astype(np.float16), z=zc.astype(np.float16), ndvi=Yc.astype(np.float16),
                            y=y.astype(np.float16), onset=onset, below=below_lab, eligible=eligible,
                            mu=mu.astype(np.float16), sigma=sigma.astype(np.float16), zhat=zhat.astype(np.float16),
                            R_lab=R_lab.astype(np.float16), dev_lab=dev_lab.astype(np.float16),
                            lc=lcf, aoi_frac=aoi_frac, observed=observed)
    return dict(aoi=aoi, times=times, months=months, years=years, T=T, H=H, W=W, rr=rr, cc=cc, N=N,
                Yc=Yc, age=age, mu=mu, sigma=sigma, zhat=zhat, R_feat=R_feat, y=y, eligible=eligible,
                onset=onset, nxt=nxt, observed=observed, peer_R=peer_R, peer_d=peer_d, R_nb5=R_nb5, R_nb21=R_nb21, R_sd21=R_sd21,
                z_nb21=z_nb21, aoi_frac=aoi_frac, dist=dist, clim_X=clim_X, others=others, lcf=lcf,
                static=st, cm_info=cm_info, clim=clim, eco=eco, nl_sp=nl_sp)


def features_for(ctx, idx, need=None, t_from=0):
    """Feature dict (arrays [T, len(idx)]) for the pixel subset idx (indices into ctx['rr'])."""
    other = {k: ts.causal_interp_short_gaps(v[:, idx], LABEL.max_gap_fill)[0] for k, v in ctx["others"].items()}
    months = ctx["months"]
    F, z_s, R_s = build_features(ctx["Yc"][:, idx], ctx["age"][:, idx], ctx["mu"][:, idx], ctx["sigma"][idx],
                                 ctx["zhat"][:, idx], months, other, ctx["clim_X"], ctx["peer_R"][:, idx], ctx["peer_d"][:, idx])
    shp = F["ndvi"].shape
    F["month_sin"] = np.broadcast_to(np.sin(2 * np.pi * months / 12)[:, None], shp)
    F["month_cos"] = np.broadcast_to(np.cos(2 * np.pi * months / 12)[:, None], shp)
    for k in ("R_nb5", "R_nb21", "R_sd21", "z_nb21"):
        F[k] = ctx[k][:, idx]
    F["aoi_frac_below"] = np.broadcast_to(ctx["aoi_frac"][:, None], shp)
    rr, cc = ctx["rr"][idx], ctx["cc"][idx]
    for k in ("elev", "slope", "water_occ"):
        F[k] = np.broadcast_to(ctx["static"][k].values[rr, cc][None, :], shp)
    F["dist_river_km"] = np.broadcast_to(ctx["dist"][idx][None, :], shp)
    F["landcover"] = np.broadcast_to(ctx["lcf"][idx][None, :].astype(np.float32), shp)
    mf = modis_features(ctx["aoi"].key, ctx["times"], rr, cc, len(idx))
    if mf:
        F.update(mf)
    from .ecofunc import ECO_FEATURES
    from .nonlinear import NONLIN_FEATURES
    # need: set of feature names actually required (e.g. the model's columns); None = everything (training tables)
    want = lambda names: need is None or any(n in need for n in names)
    if "eco" in ctx and (want(ECO_FEATURES) or need is not None and any(k in need for k in ("water_loss12",))):
        from .ecofunc import eco_features, eco_align
        e = ctx["eco"]
        f32 = lambda a: a.astype(np.float32)
        ef = eco_features(ctx["Yc"][:, idx], f32(e["water"][:, idx]), f32(e["paddy"][:, idx]), f32(e["nbw"][:, idx]), f32(e["tex"][:, idx]),
                          ctx["mu"][:, idx], ctx["years"], t_from=t_from)
        F.update(eco_align(ef, months))
    if "nl_sp" in ctx and want(NONLIN_FEATURES):
        from .nonlinear import nonlinear_features
        sp = {k: v[:, idx].astype(np.float32) for k, v in ctx["nl_sp"].items()}
        z_idx = (ctx["Yc"][:, idx] - ctx["mu"][:, idx][months - 1]) / ctx["sigma"][idx]
        p3 = ctx["clim"]["P3"].reindex(ctx["times"]).values.astype(np.float32)
        F.update(nonlinear_features(ctx["R_feat"][:, idx], z_idx, p3, sp["sp_skew"], sp["sp_moran"], sp["vf"], sp["lp"], sp["al"], t_from=t_from))
    lf = lst_features(ctx["aoi"].key, ctx["times"], rr, cc, ctx["clim"])
    if lf:
        F.update(lf)
    for k in HEAT_COLS:
        if k in ctx["clim"]:
            F["heat_" + k] = np.broadcast_to(ctx["clim"][k].reindex(ctx["times"]).values.astype(np.float32)[:, None], shp)
    return F, R_s


def build_aoi(aoi_key, n_sample=PIX_PER_AOI, extra=0, out_name="table.parquet"):
    """extra > 0 (D-024): keep the original n_sample pixels (same RNG draw) and add `extra` NEW pixels drawn from
    the rest; rows carry batch = 0 (original) / 1 (added) so experiments can compare on identical evaluation rows."""
    ctx = aoi_context(aoi_key, save_cube=(extra == 0))
    aoi, times, years, N, W = ctx["aoi"], ctx["times"], ctx["years"], ctx["N"], ctx["W"]
    d = PROC / aoi.key
    rng = np.random.default_rng(SEED + sum(map(ord, aoi.key)))
    samp = np.sort(rng.choice(N, size=min(n_sample, N), replace=False))
    batch_of = {}
    if extra:
        rest = np.setdiff1d(np.arange(N), samp)
        add = np.sort(np.random.default_rng(SEED + 1000 + sum(map(ord, aoi.key))).choice(rest, size=min(extra, len(rest)), replace=False))
        batch_of = dict.fromkeys(add.tolist(), 1)
        samp = np.sort(np.concatenate([samp, add]))
    F, R_s = features_for(ctx, samp)
    y, eligible, nxt, rr, cc = ctx["y"], ctx["eligible"], ctx["nxt"], ctx["rr"], ctx["cc"]
    tsel = times >= FEAT_START
    keep = tsel[:, None] & eligible[:, samp] & np.isfinite(y[:, samp]) & np.isfinite(R_s)
    ti, pi = np.nonzero(keep)
    df = pd.DataFrame({k: np.asarray(v)[ti, pi].astype(np.float32) for k, v in F.items()})
    df.insert(0, "time", times[ti]); df.insert(0, "pix", samp[pi].astype(np.int32)); df.insert(0, "aoi", aoi.key)
    df["country"] = aoi.country
    df["row"] = rr[samp][pi].astype(np.int16); df["col"] = cc[samp][pi].astype(np.int16)
    df["block"] = ((df["row"] // BLOCK_PX) * (W // BLOCK_PX + 1) + df["col"] // BLOCK_PX).astype(np.int16)
    df["y"] = y[ti, samp[pi]].astype(np.int8)
    df["months_to_onset"] = nxt[ti, samp[pi]]
    df["batch"] = np.array([batch_of.get(int(p), 0) for p in samp], np.int8)[pi]
    df.to_parquet(d / out_name, index=False)
    if extra:
        print(f"[{aoi.key}] {out_name} rows={len(df)} pixels={len(samp)}", flush=True)
        return dict(rows=int(len(df)))
    lab_ok = np.isfinite(y) & eligible
    lcf = ctx["lcf"]
    info = dict(aoi=aoi.key, country=aoi.country, n_pixels=int(N), n_sampled=int(len(samp)), rows=int(len(df)),
                pos_rate=float(df["y"].mean()), onsets_total=int(ctx["onset"].sum()),
                onset_rate_per_pixel_year=float(ctx["onset"].sum() / N / (ctx["T"] / 12)),
                obs_fraction=float(ctx["observed"].mean()), climate_model=ctx["cm_info"],
                landcover_share={LC_NAME.get(int(k), str(k)): float((lcf == k).mean()) for k in np.unique(lcf)},
                yearly_pos_rate={int(yy): float(np.nanmean(np.where(lab_ok, y, np.nan)[years == yy])) for yy in np.unique(years)},
                monthly_obs_fraction=[float(v) for v in ctx["observed"].mean(1)])
    json.dump(info, open(d / "dataset_info.json", "w"), indent=2)
    print(f"[{aoi.key}] N={N} rows={len(df)} pos={info['pos_rate']:.3f}", flush=True)
    return info


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "plus":                 # python -m care_ew.dataset plus 5000 [aoi ...]  (D-024)
        for a in (args[2:] or [a.key for a in AOIS]):
            if not (PROC / a / "table_plus.parquet").exists():
                build_aoi(a, extra=int(args[1]), out_name="table_plus.parquet")
    else:
        for a in (args or [a.key for a in AOIS]):
            build_aoi(a)
