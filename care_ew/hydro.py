"""Hydrological context (OSINT): which rivers feed the target, and how their flow changed.

* HydroRIVERS v1.0 (WWF/HydroSHEDS, 15 arc-sec): river reaches with topology (HYRIV_ID -> NEXT_DOWN),
  long-term mean discharge DIS_AV_CMS, upstream area, Strahler order.
  - reaches intersecting / nearest to the AOI
  - full UPSTREAM network of the AOI's outlet reach, truncated to ORD_FLOW <= 7 & within 300 km
  - the downstream path for 100 km
* GloFAS v4 reanalysis daily river discharge (Copernicus EMS) via Open-Meteo Flood API, sampled at
  the AOI outlet reach and at the 3 largest upstream tributary confluences: "before vs now" =
  1984-2000 vs 2016-present, monthly mean + low-flow (Q90) statistics.
* distance-to-river raster (10 m grid) for the A6 spatial context features.
Outputs: data/processed/<aoi>/rivers_upstream.geojson, rivers_local.geojson, discharge.csv, hydro_summary.json
"""
import sys, json, zipfile, time
import numpy as np, pandas as pd, geopandas as gpd, requests
from shapely.geometry import box, Point
from .config import AOIS, AOI_BY_KEY, PROC, RAW
from .s2 import _epsg, grid_info

HR = RAW / "hydrorivers"
REGION = {"NPL_chure": "as", "IND_bundelkhand": "as", "ETH_tigray": "af", "KEN_baringo": "af", "SEN_ferlo": "af",
          "ESP_murcia": "eu", "BRA_matopiba": "sa", "MNG_steppe": "as", "AUS_murraydarling": "au"}
FLOOD = "https://flood-api.open-meteo.com/v1/flood"


def load_region(reg, bbox):
    z = HR / f"HydroRIVERS_{reg}.zip"
    with zipfile.ZipFile(z) as f:
        shp = [n for n in f.namelist() if n.endswith(".shp")][0]
    return gpd.read_file(f"zip://{z}!{shp}", bbox=tuple(bbox))


def upstream_ids(df, outlet, max_n=20000):
    up = df.groupby("NEXT_DOWN")["HYRIV_ID"].apply(list).to_dict()
    out, stack = set(), [outlet]
    while stack and len(out) < max_n:
        r = stack.pop()
        if r in out:
            continue
        out.add(r)
        stack.extend(up.get(r, []))
    return out


def downstream_ids(df, outlet, n=60):
    nd = df.set_index("HYRIV_ID")["NEXT_DOWN"].to_dict()
    out, r = [], outlet
    while r and r in nd and len(out) < n:
        out.append(r); r = nd[r]
    return out


def glofas(lat, lon, start="1984-01-01", end="2026-09-30"):
    for k in range(5):
        r = requests.get(FLOOD, params=dict(latitude=lat, longitude=lon, daily="river_discharge",
                                            start_date=start, end_date=end), timeout=120)
        if r.status_code == 429:          # hourly quota: wait and retry
            time.sleep(300); continue
        if r.status_code == 200:
            d = r.json()["daily"]
            s = pd.Series(d["river_discharge"], index=pd.to_datetime(d["time"]), dtype=float)
            return s
        time.sleep(10 * (k + 1))
    return pd.Series(dtype=float)


def glofas_snap(lat, lon, target_q, step=0.05, k=1):
    """GloFAS is a ~0.05 deg grid; the nearest cell to a river vertex is often a hillslope cell with
    tiny discharge. Search a (2k+1)^2 neighbourhood and keep the cell whose 2000-2009 mean discharge is
    closest (log ratio) to HydroRIVERS' long-term mean DIS_AV_CMS for that reach."""
    lats, lons = [], []
    for i in range(-k, k + 1):
        for j in range(-k, k + 1):
            lats.append(round(lat + i * step, 4)); lons.append(round(lon + j * step, 4))
    r = requests.get(FLOOD, params=dict(latitude=",".join(map(str, lats)), longitude=",".join(map(str, lons)),
                                        daily="river_discharge", start_date="2005-01-01", end_date="2006-12-31"), timeout=180)
    if r.status_code != 200:
        return lat, lon, None
    js = r.json(); js = js if isinstance(js, list) else [js]
    best, score = (lat, lon, None), np.inf
    for la, lo, d in zip(lats, lons, js):
        q = pd.Series(d["daily"]["river_discharge"], dtype=float)
        if q.notna().sum() < 60:
            continue
        m = q.mean()
        sc = abs(np.log((m + 0.01) / (target_q + 0.01))) + 0.02 * (abs(la - lat) + abs(lo - lon)) / step
        if sc < score:
            best, score = (la, lo, float(m)), sc
    return best


def build(aoi_key):
    aoi = AOI_BY_KEY[aoi_key]
    d = PROC / aoi.key
    big = [aoi.lon - 3, aoi.lat - 3, aoi.lon + 3, aoi.lat + 3]
    reg0 = REGION.get(aoi.key)
    if reg0 is None:   # user-drawn areas: pick the HydroSHEDS region by location
        lo, la = aoi.lon, aoi.lat
        reg0 = ("eu" if (la > 35 and -25 < lo < 60) else "af" if (-40 < la <= 35 and -25 < lo < 55) else
                "sa" if (lo < -30 and la < 15) else "au" if (lo > 110 and la < -10) else
                "si" if la > 55 else "as")
    rv = load_region(reg0, big)
    if len(rv) < 50:                      # AOI near a HydroSHEDS region border (e.g. Mongolia: as / si)
        for reg in ("si", "as", "eu", "af"):
            if reg != reg0 and (HR / f"HydroRIVERS_{reg}.zip").exists():
                alt = load_region(reg, big)
                if len(alt) > len(rv):
                    rv = alt
    a_box = box(*grid_info(aoi)["bbox_wgs84"])
    rv_m = rv.to_crs(_epsg(aoi))
    centre = gpd.GeoSeries([Point(aoi.lon, aoi.lat)], crs=4326).to_crs(_epsg(aoi)).iloc[0]
    rv_m["dist_km"] = rv_m.distance(centre) / 1000
    # outlet: the largest-discharge reach INSIDE the AOI box (the river that drains the target);
    # only if none crosses the box, widen to a 0.02 deg (~2 km) buffer; else nearest reach of order >= 3
    local = rv[rv.intersects(a_box)]
    if not len(local):
        local = rv[rv.intersects(a_box.buffer(0.02))]
    if len(local):
        outlet = local.sort_values("DIS_AV_CMS", ascending=False).iloc[0]
    else:
        cand = rv_m[rv_m["ORD_STRA"] >= 3].sort_values("dist_km")
        outlet = rv.loc[cand.index[0]]
    oid = int(outlet["HYRIV_ID"])
    ups = upstream_ids(rv, oid)
    upg = rv[rv["HYRIV_ID"].isin(ups)].copy()
    upg = upg.join(rv_m["dist_km"])
    upg = upg[(upg["dist_km"] <= 300)]
    # keep the visible skeleton: reaches with mean flow >= 0.5 m3/s or order >= 3, plus everything within 25 km
    upg = upg[(upg["DIS_AV_CMS"] >= 0.5) | (upg["ORD_STRA"] >= 3) | (upg["dist_km"] <= 25)]
    dn = rv[rv["HYRIV_ID"].isin(downstream_ids(rv, oid))].copy()
    upg["role"] = "upstream"; dn["role"] = "downstream"
    upg.loc[upg["HYRIV_ID"] == oid, "role"] = "outlet"
    keep = ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "ORD_STRA", "ORD_FLOW", "DIS_AV_CMS", "UPLAND_SKM", "LENGTH_KM", "role", "geometry"]
    net = pd.concat([upg, dn[~dn["HYRIV_ID"].isin(upg["HYRIV_ID"])]])[keep]
    net.to_file(d / "rivers_network.geojson", driver="GeoJSON")
    near = rv[rv.intersects(a_box.buffer(0.15))][keep[:-2] + ["geometry"]]
    near.to_file(d / "rivers_local.geojson", driver="GeoJSON")

    # discharge stations: outlet + 3 biggest tributary inflow points (largest upstream reaches whose
    # NEXT_DOWN is on the main stem but which belong to a different MAIN_RIV / big tributary)
    pts = [("outlet", outlet.geometry.interpolate(0.5, normalized=True), float(outlet["DIS_AV_CMS"]))]
    tribs = upg[(upg["role"] == "upstream") & (upg["dist_km"] > 15)].sort_values("UPLAND_SKM", ascending=False)
    seen = set()
    for _, r in tribs.iterrows():
        key = round(r["UPLAND_SKM"] / max(outlet["UPLAND_SKM"], 1), 1)
        if r["NEXT_DOWN"] in seen or key in seen:
            continue
        pts.append((f"upstream_{len(pts)}", r.geometry.interpolate(0.5, normalized=True), float(r["DIS_AV_CMS"])))
        seen.add(key); seen.add(r["NEXT_DOWN"])
        if len(pts) >= 4:
            break
    series, summ = {}, []
    for name, p, q_ref in pts:
        try:   # discharge is display-only context: an API outage must not lose the river network (I-027)
            la, lo, q_snap = glofas_snap(p.y, p.x, q_ref)
            time.sleep(1)
            q = glofas(la, lo)
        except Exception as e:
            print(f"[{aoi.key}] GloFAS unavailable for {name}: {str(e)[:80]}", flush=True)
            la, lo, q = p.y, p.x, pd.Series(dtype=float)
        p = Point(lo, la)
        series[name] = q
        if q.dropna().empty:
            summ.append(dict(name=name, lat=p.y, lon=p.x, available=False)); continue
        before, now = q["1984":"2000"], q["2016":]
        summ.append(dict(name=name, lat=round(p.y, 5), lon=round(p.x, 5), available=True, hydrorivers_mean_q=q_ref,
                         mean_before=float(before.mean()), mean_now=float(now.mean()),
                         q90_before=float(before.quantile(0.1)), q90_now=float(now.quantile(0.1)),
                         change_mean_pct=float(100 * (now.mean() / before.mean() - 1)) if before.mean() > 0 else None,
                         change_lowflow_pct=float(100 * (now.quantile(0.1) / before.quantile(0.1) - 1)) if before.quantile(0.1) > 0 else None))
    series = {k: v for k, v in series.items() if len(v.dropna())}
    if series:
        pd.DataFrame(series).resample("MS").mean().to_csv(d / "discharge_monthly.csv")
    info = dict(outlet_id=oid, outlet_main_river=int(outlet["MAIN_RIV"]), outlet_mean_q=float(outlet["DIS_AV_CMS"]),
                outlet_upland_km2=float(outlet["UPLAND_SKM"]), n_upstream_reaches=len(upg), stations=summ,
                source="HydroRIVERS v1.0 + GloFAS v4 (Open-Meteo Flood API)")
    json.dump(info, open(d / "hydro_summary.json", "w"), indent=2)
    # distance-to-river raster for features
    import xarray as xr
    from .s2 import _grid
    x0, y0, n = _grid(aoi)
    xs = x0 + 5 + 10 * np.arange(n)[::10]; ys = y0 + n * 10 - 5 - 10 * np.arange(n)[::10]
    lines = near.to_crs(_epsg(aoi)).union_all() if len(near) else None
    if lines is not None:
        from shapely import points, distance
        XX, YY = np.meshgrid(xs, ys)
        dd = distance(points(XX.ravel(), YY.ravel()), lines).reshape(XX.shape) / 1000
        dd = np.kron(dd, np.ones((10, 10)))[:n, :n]
    else:
        dd = np.full((n, n), 50.0)
    np.save(d / "dist_river_km.npy", dd.astype(np.float32))
    print(f"[{aoi.key}] rivers: {len(upg)} upstream reaches, outlet Q={outlet['DIS_AV_CMS']:.1f} m3/s", flush=True)
    return info


if __name__ == "__main__":
    for a in (sys.argv[1:] or [a.key for a in AOIS]):
        build(a)
