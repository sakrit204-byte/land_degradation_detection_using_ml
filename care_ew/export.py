"""Export pipeline products to the app data contract (docs/UI_DATA_SPEC.md) under app/static/data/.

Overlays are reprojected from the 10 m UTM analysis grid to a WGS84 grid that exactly covers the
AOI bbox (nearest neighbour), so they register correctly when draped over the globe.
"""
import json, shutil, sys, time
import numpy as np, pandas as pd, xarray as xr
from PIL import Image
from affine import Affine
from rasterio.warp import reproject, Resampling
from rasterio.crs import CRS
from scipy import ndimage
from pyproj import Transformer
from .config import AOIS, AOI_BY_KEY, PROC, OUT, ROOT
from .s2 import grid_info
from .features import LC_NAME
from . import s2 as s2mod

APP = ROOT / "app" / "static" / "data"
PRED = OUT / "predictions"
RES = OUT / "results"
FRIENDLY = {
    "R": "Climate residual R (now)", "R_mean3": "Residual R (3-mo mean)", "R_mean6": "Residual R (6-mo mean)",
    "R_mean12": "Residual R (12-mo mean)", "R_min6": "Residual R (6-mo min)", "R_slope12": "Residual trend (12 mo)",
    "R_negrun": "Months with negative residual", "R_fracbelow12": "Share of last 12 mo below expectation",
    "z": "NDVI anomaly z", "z_mean3": "NDVI anomaly (3-mo mean)", "z_mean6": "NDVI anomaly (6-mo mean)",
    "z_min6": "NDVI anomaly (6-mo min)", "ndvi": "NDVI now", "ndvi_dev": "NDVI minus seasonal baseline",
    "ndvi_slope12": "NDVI trend (12 mo)", "ndvi_slope36": "NDVI trend (36 mo)", "d_ndvi_1": "NDVI change (1 mo)",
    "d_ndvi_3": "NDVI change (3 mo)", "d_ndvi_12": "NDVI change vs last year", "ac1_24": "Autocorrelation AC1 (24 mo)",
    "ac1_12": "Autocorrelation AC1 (12 mo)", "var_24": "Residual variance (24 mo)", "var_12": "Residual variance (12 mo)",
    "ac1_trend": "Change in AC1 (12 mo)", "var_ratio": "Variance ratio", "months_since_dip": "Months since last dip",
    "recovery_frac": "Recovery from 12-mo low", "R_nb5": "Neighbour residual (50 m)", "R_nb21": "Neighbour residual (210 m)",
    "R_sd21": "Residual heterogeneity (210 m)", "z_nb21": "Neighbour anomaly (210 m)", "aoi_frac_below": "Share of AOI below expectation",
    "elev": "Elevation", "slope": "Slope", "water_occ": "Surface-water occurrence", "dist_river_km": "Distance to river",
    "landcover": "Land cover", "ndmi": "Moisture index NDMI", "nbr": "Burn ratio NBR", "bsi": "Bare-soil index BSI",
    "d_ndmi_3": "NDMI change (3 mo)", "bsi_slope12": "Bare-soil trend (12 mo)", "modis_z": "MODIS long-term anomaly",
    "modis_ac1_60": "MODIS AC1 (5 yr)", "modis_var_60": "MODIS variance (5 yr)", "sigma": "Local NDVI variability",
    "mu_now": "Seasonal baseline NDVI", "data_age": "Months since last clear view", "zhat": "Climate-expected anomaly",
    "month_sin": "Season (sin)", "month_cos": "Season (cos)", "clim_P1": "Rain anomaly (1 mo)", "clim_P3": "Rain anomaly (3 mo)",
    "clim_P6": "Rain anomaly (6 mo)", "clim_P12": "Rain anomaly (12 mo)", "clim_T1": "Temperature anomaly",
    "clim_SM1": "Soil-moisture anomaly", "clim_SM3": "Root-zone soil-moisture anomaly", "clim_WB3": "Water balance P-ET0 (3 mo)",
}


# ------------------------------------------------------------------ geometry helpers
def wgs_grid(aoi, n=512):
    g = grid_info(aoi)
    w, s, e, nn = g["bbox_wgs84"]
    h = int(round(n * (nn - s) / (e - w) / np.cos(np.radians((s + nn) / 2)) ))
    h = max(64, min(2 * n, h))
    return g, Affine((e - w) / n, 0, w, 0, -(nn - s) / h, nn), (h, n)


def to_wgs(arr, aoi, nodata=np.nan, resampling=Resampling.nearest):
    g, dst_tr, shape = wgs_grid(aoi)
    src_tr = Affine(10, 0, g["x0"], 0, -10, g["y0"] + g["n"] * 10)
    out = np.full(shape, nodata, np.float32)
    reproject(arr.astype(np.float32), out, src_transform=src_tr, src_crs=CRS.from_epsg(g["epsg"]),
              dst_transform=dst_tr, dst_crs=CRS.from_epsg(4326), resampling=resampling,
              src_nodata=nodata, dst_nodata=nodata)
    return out


def utm_box_to_lonlat(aoi, r0, r1, c0, c1):
    g = grid_info(aoi)
    tr = Transformer.from_crs(g["epsg"], 4326, always_xy=True)
    ytop = g["y0"] + g["n"] * 10
    pts = [(g["x0"] + c * 10, ytop - r * 10) for r, c in [(r0, c0), (r0, c1 + 1), (r1 + 1, c1 + 1), (r1 + 1, c0)]]
    ll = [list(map(lambda v: round(v, 6), tr.transform(x, y))) for x, y in pts]
    return ll + [ll[0]]


def lerp_cmap(stops, v):
    """stops: [(pos, (r,g,b))]; v in [0,1] array -> uint8 rgb."""
    pos = np.array([s[0] for s in stops]); cols = np.array([s[1] for s in stops], float)
    out = np.stack([np.interp(v, pos, cols[:, k]) for k in range(3)], -1)
    return out.astype(np.uint8)


RISK_STOPS = [(0.0, (255, 243, 196)), (0.25, (250, 178, 25)), (0.5, (236, 131, 90)), (0.75, (208, 59, 59)), (1.0, (110, 20, 20))]
Z_STOPS = [(0.0, (120, 72, 30)), (0.33, (196, 154, 108)), (0.5, (245, 245, 240)), (0.67, (140, 200, 120)), (1.0, (16, 110, 40))]


def risk_scale(thr):
    """Display scale anchored on the operating threshold (calibrated probabilities are small because the
    6-month onset base rate is ~1 %): shown from 0.5*thr, yellow at thr, red at 2*thr, dark at 4*thr."""
    t = float(thr)
    return [[round(0.5 * t, 4), "#ffe24d"], [round(t, 4), "#ff961e"], [round(2 * t, 4), "#e8281c"], [round(4 * t, 4), "#78000a"]]


def _hex(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def risk_png(p_w, st_w, thr, f):
    h, w = p_w.shape
    rgba = np.zeros((h, w, 4), np.uint8)
    stops = risk_scale(thr)
    lo, hi = stops[0][0], stops[-1][0]
    v = np.clip((p_w - lo) / (hi - lo), 0, 1)
    show = np.isfinite(p_w) & (p_w >= lo)
    rgba[..., :3] = lerp_cmap([((s_[0] - lo) / (hi - lo), _hex(s_[1])) for s_ in stops], np.nan_to_num(v))
    rgba[..., 3] = np.where(show, np.clip(120 + 115 * np.nan_to_num(v), 0, 235), 0).astype(np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    stripes = ((xx + yy) // 3) % 3 == 0
    ab = (st_w == 2) & np.isfinite(p_w) & (p_w >= thr * 0.5)
    rgba[ab & stripes] = (98, 80, 214, 220)
    act = st_w == 3
    rgba[act] = (185, 183, 174, 90)     # below peers this month (not eligible): neutral wash, not an alarm colour
    Image.fromarray(rgba, "RGBA").save(f, optimize=True)


def z_png(z_w, f):
    v = np.clip((z_w + 3) / 6, 0, 1)
    rgba = np.zeros(z_w.shape + (4,), np.uint8)
    rgba[..., :3] = lerp_cmap(Z_STOPS, np.nan_to_num(v, nan=0.5))
    rgba[..., 3] = np.where(np.isfinite(z_w), 200, 0)
    Image.fromarray(rgba, "RGBA").save(f, optimize=True)


def rgb_png(r, g_, b, f, scale=None):
    rgb = np.stack([r, g_, b], -1)
    scale = scale or np.nanpercentile(rgb, 98)
    img = np.clip(rgb / scale * 255, 0, 255)
    a = np.where(np.isfinite(rgb).all(-1), 255, 0)
    img = np.nan_to_num(img)
    Image.fromarray(np.dstack([img, a]).astype(np.uint8), "RGBA").save(f, optimize=True)
    return scale


# ------------------------------------------------------------------ process attribution (D-020)
def attribute(eco, p3_before, landcover):
    """Rule-based explanation of WHY productivity is falling (expert framing: degradation = loss of ecosystem
    function -> productivity). Thresholds are deliberately conservative and documented; tags are explanations
    for field teams, not model outputs."""
    tags = []
    g = lambda k: eco.get(k, np.nan)
    if g("nbw_loss12") > 0.05 or g("water_loss12") > 0.10:
        tags.append(dict(code="water_loss", text="Hydrological loss: surface water receded (stream / pond / wetland drying)"))
    if g("water_frac12") > 0.05 or g("water_loss12") < -0.10:
        tags.append(dict(code="river_dynamics", text="River dynamics: channel shift, flooding or sand deposition at this site"))
    if g("paddy_change") < -0.05:
        tags.append(dict(code="paddy_loss", text="Crop-system change: seasonal flooding (paddy / wetland) lost, e.g. rice to dryland crop"))
    if g("evergreen_shift") > 0.08 and landcover in ("shrub", "grass", "crop", "bare"):
        tags.append(dict(code="evergreen_encroachment", text="Dry-season greening: evergreen / woody encroachment (possible invasive, e.g. Prosopis, Lantana)"))
    if g("evergreen_shift") < -0.08:
        tags.append(dict(code="perennial_loss", text="Loss of perennial green cover (dry-season greenness fell)"))
    if abs(g("amp_change")) > 0.15:
        tags.append(dict(code="structure_shift", text="Vegetation structure shift: seasonal amplitude changed strongly (life-form change)"))
    if np.isfinite(p3_before) and p3_before > 1.0:
        tags.append(dict(code="rain_use_loss", text=f"Did not green up after a wet spell (rain +{p3_before:.1f} sd): rain-use efficiency loss"))
    elif np.isfinite(p3_before) and p3_before < -1.0:
        tags.append(dict(code="post_drought", text=f"Decline followed a dry spell (rain {p3_before:.1f} sd): check recovery before calling it degradation"))
    if not tags:
        tags.append(dict(code="other", text="Persistent productivity decline without a single dominant mechanism"))
    return tags


# ------------------------------------------------------------------ main export
def export_aoi(key, metrics_doc):
    aoi = AOI_BY_KEY[key]
    d = PROC / key
    o = APP / "aois" / key
    if o.exists():
        shutil.rmtree(o)
    for sub in ("risk", "ndvi", "rgb", "chips"):
        (o / sub).mkdir(parents=True, exist_ok=True)
    c = np.load(d / "cube.npz")
    pz = np.load(PRED / f"{key}_risk.npz", allow_pickle=True)
    H, W = int(c["H"]), int(c["W"])
    rr, cc = c["rr"].astype(int), c["cc"].astype(int)
    times = list(c["times"])
    months_risk = [str(m) for m in pz["months"]]
    thr = float(pz["thr"])
    risk, status = pz["risk"], pz["status"]
    np.savez_compressed(o / "risk_cube.npz", risk=risk, months=np.array(months_risk))

    def grid(v, fill=np.nan):
        a = np.full((H, W), fill, np.float32); a[rr, cc] = v; return a

    # --- overlays
    s2 = s2mod.load(key)
    s2t = list(pd.DatetimeIndex(s2.time.values).strftime("%Y-%m"))
    zc = c["z"]
    scale = None
    months_rgb = []
    for i, m in enumerate(months_risk):
        ti = times.index(m)
        p_w = to_wgs(grid(risk[i].astype(np.float32)), aoi)
        st_w = to_wgs(grid(status[i].astype(np.float32), 255), aoi, nodata=255)
        risk_png(p_w, st_w, thr, o / "risk" / f"{m}.png")
        z_png(to_wgs(grid(zc[ti].astype(np.float32)), aoi), o / "ndvi" / f"{m}.png")
    for m in s2t:
        if m < "2019-01":
            continue
        k = s2t.index(m)
        R_, G_, B_ = (s2[b].values[k] for b in ("R", "G", "B"))
        if np.isfinite(R_).mean() < 0.6:
            continue
        scale = rgb_png(*(to_wgs(x, aoi) for x in (R_, G_, B_)), o / "rgb" / f"{m}.png", scale)
        months_rgb.append(m)

    # --- hotspots at the latest month
    last = -1
    p_last = grid(risk[last].astype(np.float32)); st_last = grid(status[last].astype(np.float32), 255)
    contrib = pz["contrib_last"].astype(np.float32)
    cols = list(pz["cols"])
    # a warning refers to the next 6 months, so a pixel warned in ANY of the last 3 months stays a warning
    # (otherwise one cloudy/ineligible month would make it disappear from the map)
    p_recent = np.nanmax(np.stack([grid(risk[i].astype(np.float32)) for i in range(-3, 0)]), axis=0)
    classes = {"warning": (st_last == 1) | (np.nan_to_num(p_recent) >= thr),
               "abstain": (st_last == 2) & (np.nan_to_num(p_last) >= 0.5 * thr),
               "watch": (np.nan_to_num(p_last) >= 0.5 * thr) & (st_last != 1) & (st_last != 2),
               "active_degradation": st_last == 3}
    idx_map = np.full((H, W), -1, np.int64); idx_map[rr, cc] = np.arange(len(rr))
    clim = pd.read_csv(d / "climate_monthly.csv", index_col=0, parse_dates=True)
    rain6 = float(clim["P6"].iloc[-1]) if len(clim) else None
    eco_last = pz["eco_last"].astype(np.float32) if "eco_last" in pz.files else None
    eco_cols = list(pz["eco_cols"]) if "eco_last" in pz.files else []
    dist = np.load(d / "dist_river_km.npy") if (d / "dist_river_km.npy").exists() else None
    lc_grid = np.full((H, W), 0); lc_grid[rr, cc] = c["lc"]
    ndvi_now = grid(c["ndvi"][times.index(months_risk[last])].astype(np.float32))
    mu = c["mu"].astype(np.float32); m_idx = int(months_risk[last][5:7]) - 1
    base_now = grid(mu[m_idx])
    R_last = grid(c["R"][times.index(months_risk[last])].astype(np.float32))
    feats = []
    minpx = {"warning": 30, "abstain": 60, "watch": 60, "active_degradation": 150}
    for status_name, mask in classes.items():
        mask = ndimage.binary_opening(mask, iterations=1)
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        if n == 0:
            continue
        sl = ndimage.find_objects(lab)
        sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
        for j in np.argsort(-sizes)[:25]:
            if sizes[j] < minpx[status_name]:
                break
            r0, r1 = sl[j][0].start, sl[j][0].stop - 1
            c0, c1 = sl[j][1].start, sl[j][1].stop - 1
            px = lab == j + 1
            ids = idx_map[px]; ids = ids[ids >= 0]
            pv = p_recent[px] if status_name == "warning" else p_last[px]
            mc = contrib[ids].mean(0) if len(ids) else np.zeros(len(cols))
            top = np.argsort(-mc)[:5]
            drivers = [dict(name=FRIENDLY.get(cols[t], cols[t]), feature=cols[t], contribution=round(float(mc[t]), 3)) for t in top if mc[t] > 0]
            # first warning: earliest month of the trailing run where >= 30 % of cluster pixels were >= thr
            fw = None
            for i in range(len(months_risk) - 1, -1, -1):
                pr = grid(risk[i].astype(np.float32))[px]
                if np.nanmean(np.nan_to_num(pr) >= thr) >= 0.3:
                    fw = months_risk[i]
                else:
                    break
            lcv = np.bincount(lc_grid[px].ravel()).argmax()
            # trailing months the cluster has been in active decline (majority of its pixels status 3)
            mb = 0
            for i in range(len(months_risk) - 1, -1, -1):
                if np.mean(grid(status[i].astype(np.float32), 255)[px] == 3) >= 0.5: mb += 1
                else: break
            r_now = R_last[px]
            # onset month of an active run (or the latest month for warnings) -> rainfall context before it
            on_m = months_risk[max(0, len(months_risk) - max(mb, 1))]
            p3_before = clim["P3"].shift(1).get(pd.Timestamp(on_m + "-01"), np.nan) if len(clim) else np.nan
            eco = {k: float(np.nanmean(eco_last[ids, j])) for j, k in enumerate(eco_cols)} if eco_last is not None and len(ids) else {}
            attribution = attribute(eco, p3_before, LC_NAME.get(int(lcv), ""))
            feats.append(dict(type="Feature", geometry=dict(type="Polygon", coordinates=[utm_box_to_lonlat(aoi, r0, r1, c0, c1)]),
                              properties=dict(status=status_name, risk_mean=round(float(np.nanmean(pv)), 3) if np.isfinite(pv).any() else None,
                                              risk_max=round(float(np.nanmax(pv)), 3) if np.isfinite(pv).any() else None,
                                              area_ha=round(float(px.sum()) * 0.01, 2), landcover=LC_NAME.get(int(lcv), str(lcv)),
                                              first_warning=fw, drivers=drivers if status_name != "active_degradation" else [],
                                              attribution=attribution, eco={k: round(v, 3) for k, v in eco.items() if np.isfinite(v)},
                                              rain_anom_3m_before_onset=None if not np.isfinite(p3_before) else round(float(p3_before), 2),
                                              months_below=mb, resid_mean=round(float(np.nanmean(r_now)), 2) if np.isfinite(r_now).any() else None,
                                              ndvi_now=round(float(np.nanmean(ndvi_now[px])), 3), ndvi_baseline=round(float(np.nanmean(base_now[px])), 3),
                                              rain_anom_6m=None if rain6 is None or not np.isfinite(rain6) else round(rain6, 2),
                                              dist_river_km=None if dist is None else round(float(dist[px].mean()), 2),
                                              _box=(r0, r1, c0, c1))))
    from .config import LABEL
    feats = [f for f in feats if f["properties"]["status"] != "active_degradation" or f["properties"]["months_below"] >= LABEL.min_run]
    caps = {"warning": 10, "abstain": 5, "watch": 5, "active_degradation": 8}
    rank = {"warning": 0, "abstain": 1, "watch": 2, "active_degradation": 3}
    feats.sort(key=lambda f: (rank[f["properties"]["status"]], -(f["properties"]["risk_mean"] or 0) * f["properties"]["area_ha"]))
    kept, cnt = [], {}
    for f in feats:
        k = f["properties"]["status"]; cnt[k] = cnt.get(k, 0) + 1
        if cnt[k] <= caps[k]:
            kept.append(f)
    feats = kept
    # chips before / after for each hotspot
    rgb_ok = [m for m in months_rgb]
    after = rgb_ok[-1] if rgb_ok else None
    before = None
    if after:
        target = (pd.Period(after) - 24).strftime("%Y-%m")
        before = min(rgb_ok, key=lambda m: abs((pd.Period(m) - pd.Period(target)).n))
    for i, f in enumerate(feats, 1):
        p = f["properties"]; p["id"] = i; p["label"] = f"H{i}"; p["show_label"] = i <= 10
        r0, r1, c0, c1 = p.pop("_box")
        pad = 20
        R0, R1, C0, C1 = max(0, r0 - pad), min(H, r1 + pad + 1), max(0, c0 - pad), min(W, c1 + pad + 1)
        for tag, m in (("before", before), ("after", after)):
            if m is None:
                p[f"chip_{tag}"] = None; continue
            k = s2t.index(m)
            rgb = np.stack([s2[b].values[k][R0:R1, C0:C1] for b in ("R", "G", "B")], -1)
            img = np.nan_to_num(np.clip(rgb / (scale or 0.3) * 255, 0, 255)).astype(np.uint8)
            im = Image.fromarray(img).resize((max(64, (C1 - C0) * 3), max(64, (R1 - R0) * 3)), Image.NEAREST)
            fn = f"chips/H{i}_{tag}_{m}.png"; im.save(o / fn)
            p[f"chip_{tag}"] = fn; p[f"chip_{tag}_month"] = m
    json.dump(dict(type="FeatureCollection", features=feats), open(o / "hotspots.geojson", "w"))

    # --- rivers / hydro
    for fn in ("rivers_network.geojson", "rivers_local.geojson"):
        if (d / fn).exists():
            shutil.copy(d / fn, o / fn)
    if (d / "hydro_summary.json").exists():
        shutil.copy(d / "hydro_summary.json", o / "hydro.json")

    # --- time series
    eli = c["eligible"]
    rm = np.full(len(times), np.nan)
    for i, m in enumerate(months_risk):
        rm[times.index(m)] = np.nanmean(risk[i].astype(np.float32))
    dis = pd.read_csv(d / "discharge_monthly.csv", index_col=0, parse_dates=True) if (d / "discharge_monthly.csv").exists() else None
    ct = clim.reindex(pd.to_datetime(times))
    def L(a): return [None if (v is None or not np.isfinite(v)) else round(float(v), 4) for v in a]
    ts = dict(months=times, ndvi_mean=L(np.nanmean(c["ndvi"].astype(np.float32), 1)),
              z_mean=L(np.nanmean(c["z"].astype(np.float32), 1)), resid_mean=L(np.nanmean(c["R"].astype(np.float32), 1)),
              frac_below=L(c["aoi_frac"]), risk_mean=L(rm), rain_anom_6m=L(ct["P6"].values), temp_anom=L(ct["T1"].values),
              soil_moist_anom=L(ct["SM1"].values),
              discharge_outlet=L(dis["outlet"].reindex(pd.to_datetime(times)).values) if dis is not None and "outlet" in dis else [None] * len(times))
    json.dump(ts, open(o / "timeseries.json", "w"))
    meta = dict(months_risk=months_risk, months_rgb=months_rgb, grid=dict(H=H, W=W), threshold=thr,
                legend=dict(risk=dict(title="P(persistent degradation onset ≤ 6 months)", min_shown=risk_scale(thr)[0][0],
                                      stops=risk_scale(thr), threshold=thr),
                            note="abstain = conformal set {0,1}; dark violet wash = already below peers"))
    json.dump(meta, open(o / "meta.json", "w"))
    g = grid_info(aoi)
    yr = (pd.to_datetime(times).year.values)
    nd_y = pd.Series(ts["ndvi_mean"], index=yr, dtype=float).groupby(level=0).mean()
    slope = float(np.polyfit(nd_y.index[nd_y.notna()], nd_y[nd_y.notna()], 1)[0]) if nd_y.notna().sum() > 2 else None
    info = json.load(open(d / "dataset_info.json"))
    stats = dict(risk_mean=round(float(np.nanmean(risk[last].astype(np.float32))), 4),
                 area_high_ha=round(float((np.nan_to_num(risk[last].astype(np.float32)) >= thr).sum()) * 0.01, 1),
                 area_abstain_ha=round(float((status[last] == 2).sum()) * 0.01, 1),
                 area_active_ha=round(float((status[last] == 3).sum()) * 0.01, 1),
                 n_hotspots=len(feats), ndvi_trend_per_yr=None if slope is None else round(slope, 4),
                 pos_rate_hist=round(info["pos_rate"], 4))
    return dict(key=key, country=aoi.country, landscape=aoi.landscape, rationale=aoi.rationale,
                center=[aoi.lon, aoi.lat], bbox=[round(v, 6) for v in g["bbox_wgs84"]], stats=stats)


def add_aoi(key):
    """Export ONE area (e.g. a user-drawn box) and insert/replace it in aois.json without touching the others."""
    from .config import AOI_BY_KEY as ABK, DATA
    metrics_doc = {}
    entry = export_aoi(key, metrics_doc)
    ufile = DATA / "user_aois.json"
    if ufile.exists():
        u = json.load(open(ufile)).get(key)
        if u:
            entry.update(user=True, user_bbox=u.get("user_bbox"), created=u.get("created"),
                         warning="Model applied outside its training areas - treat as indicative.")
    idx_f = APP / "aois.json"
    idx = json.load(open(idx_f)) if idx_f.exists() else dict(aois=[], months=[])
    idx["aois"] = [a for a in idx["aois"] if a["key"] != key] + [entry]
    months = json.load(open(APP / "aois" / key / "meta.json"))["months_risk"]
    idx["months"] = sorted(set(idx.get("months", [])) | set(months))
    idx["latest_month"] = idx["months"][-1]
    json.dump(idx, open(idx_f, "w"), indent=1)
    return entry


def main(keys=None):
    metrics_doc = json.load(open(RES / "metrics.json")) if (RES / "metrics.json").exists() else {}
    if (RES / "corroboration.json").exists():
        metrics_doc["corroboration"] = json.load(open(RES / "corroboration.json"))
    APP.mkdir(parents=True, exist_ok=True)
    # remove mock AOIs (anything without real predictions)
    for p in (APP / "aois").glob("*") if (APP / "aois").exists() else []:
        if (p.name not in [a.key for a in AOIS] and not p.name.startswith("USR_")) or not (PRED / f"{p.name}_risk.npz").exists():
            shutil.rmtree(p)
    out = []
    for a in AOIS:
        if keys and a.key not in keys:
            continue
        if not (PRED / f"{a.key}_risk.npz").exists():
            print("skip (no predictions)", a.key); continue
        out.append(export_aoi(a.key, metrics_doc)); print("exported", a.key, flush=True)
    months = sorted({m for a in out for m in json.load(open(APP / "aois" / a["key"] / "meta.json"))["months_risk"]})
    json.dump(dict(generated=time.strftime("%Y-%m-%d"), model_version="careew-lgbm-v1", mock=False,
                   latest_month=months[-1] if months else None, months=months, aois=out), open(APP / "aois.json", "w"), indent=1)
    metrics_doc["mock"] = False
    f = metrics_doc.get("final_model", {})
    if f:
        from .config import SPLIT, S2_END, LABEL
        conf = f.get("conformal", {})
        metrics_doc["headline"] = dict(pr_auc=f.get("pr_auc"), roc_auc=f.get("roc_auc"), brier=f.get("brier"), ece=f.get("ece"),
                                       lead_time_months_median=f.get("lead_time", {}).get("median_lead_months"),
                                       base_rate=f.get("base_rate"), conformal_coverage=conf.get("coverage_event"),
                                       abstain_rate=conf.get("abstain_frac"))
        metrics_doc["test_period"] = f"{SPLIT['test_start']} to 2025-10, unseen 1 km blocks (n = {f.get('n')})"
        metrics_doc["model_version"] = "careew-lgbm-v1"
        ab = metrics_doc.get("ablation", {})
        metrics_doc["baselines"] = {k: v for k, v in ab.items() if k.startswith("A0") or k.startswith("RF")}
        metrics_doc["ablation"] = {k: v for k, v in ab.items() if k.startswith("LGB")}
        co = metrics_doc.get("corroboration", {})
        metrics_doc["corroboration_table"] = {k: {"landsat_auc": v.get("landsat", {}).get("auc_agreement"),
                                                  "modis_auc": v.get("modis", {}).get("auc_agreement"),
                                                  "landsat_n_events": v.get("landsat", {}).get("n_event")} for k, v in co.items()}
        metrics_doc["walk_forward_table"] = metrics_doc.get("walk_forward", [])
        metrics_doc["notes"] = (f"Operating threshold {f.get('thr', 0):.3f}: precision {f.get('precision', 0):.2f}, recall "
                                f"{f.get('recall', 0):.2f}, false-alarm rate {f.get('false_alarm_rate', 0):.3f}. 95% cluster-bootstrap CI "
                                f"PR-AUC {f.get('pr_auc_ci')}, ROC-AUC {f.get('roc_auc_ci')}. Label: peer-relative residual <= {LABEL.resid_thr} "
                                f"for >= {LABEL.min_run} months, onset within {LABEL.horizon} months. Senegal/Mongolia labels are NOT "
                                f"corroborated by Landsat (AUC ~0.5) - treat their warnings with extra caution.")
    json.dump(metrics_doc, open(APP / "metrics.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
