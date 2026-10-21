"""Sentinel-2 red-edge monthly composites (feature group A10b, PROJECT_LOG D-023).

Red-edge reflectance (B05 705 nm, B06 740 nm, B07 783 nm) tracks leaf chlorophyll; it falls when shrubs and trees
dry out or die back, often before NDVI drops. Same scene rule as s2.py (one MGRS tile, 4 least-cloudy scenes,
baselines de-duplicated, BOA offset, SCL in {4,5,6}, scenes listed in bad_scenes.txt excluded) but bands are read
at their NATIVE 20 m on a grid aligned with the 10 m grid (one 20 m cell = 2 x 2 10 m pixels).
Indices per observation, then monthly median:
    NDRE  = (B8A - B05) / (B8A + B05)            (Barnes et al. 2000)
    CIre  = B07 / B05 - 1                        (Gitelson et al. 2003, red-edge chlorophyll index)
    IRECI = (B07 - B04) / (B05 / B06)            (Frampton et al. 2013)
Output: data/processed/<aoi>/s2_rededge.nc (int16, scale 1e-4; CIre and IRECI scale 1e-3)
"""
import sys, time, logging
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, xarray as xr
import planetary_computer as pc, odc.stac
from .config import AOI_BY_KEY, PROC, S2_MAX_CLOUD, SCL_VALID, BOA_OFFSET_BASELINE, S2_START, S2_END
from .s2 import _catalog, _baseline, dedupe, select_scenes, grid_info

log = logging.getLogger("rededge")
BANDS = ["B04", "B05", "B06", "B07", "B8A", "SCL"]
RE_INDICES = ["NDRE", "CIre", "IRECI"]
SCALE = {"NDRE": 1e4, "CIre": 1e3, "IRECI": 1e3}


def _bad_ids(aoi):
    f = PROC / aoi.key / "bad_scenes.txt"
    if not f.exists():
        return set()
    out = set()
    for line in open(f):
        p = line.split("\t")
        if len(p) > 1 and p[1] != "ALL":
            out.update(p[1].split(","))
    return out


def month_composite(aoi, month, cat=None, retries=6):
    cat = cat or _catalog()
    start = pd.Timestamp(month); end = start + pd.offsets.MonthEnd(0)
    g = grid_info(aoi); n = g["n"] // 2
    empty = {k: np.full((n, n), np.nan, np.float32) for k in RE_INDICES}
    bad = _bad_ids(aoi)
    for k in range(retries):
        try:
            items = list(cat.search(collections=["sentinel-2-l2a"], bbox=g["bbox_wgs84"],
                                    datetime=f"{start:%Y-%m-%d}/{end:%Y-%m-%d}",
                                    query={"eo:cloud_cover": {"lt": S2_MAX_CLOUD}}).items())
            items = select_scenes(aoi, [i for i in dedupe(items) if i.id not in bad])
            if not items:
                return empty, 0
            from odc.geo.geobox import GeoBox
            from affine import Affine
            gbox = GeoBox((n, n), Affine(20, 0, g["x0"], 0, -20, g["y0"] + g["n"] * 10), f"EPSG:{g['epsg']}")
            parts = []
            for has_off in (False, True):
                grp = [pc.sign(i) for i in items if (_baseline(i) >= BOA_OFFSET_BASELINE) == has_off]
                if not grp:
                    continue
                d_ = odc.stac.load(grp, bands=BANDS, geobox=gbox, groupby="id",
                                   resampling={"SCL": "nearest", "*": "average"}, chunks={}, dtype="float32", nodata=0).compute()
                d_["off"] = ("time", np.full(d_.sizes["time"], 1000.0 if has_off else 0.0))
                parts.append(d_)
            ds = xr.concat(parts, dim="time") if len(parts) > 1 else parts[0]
            off = ds["off"].values[:, None, None]
            valid = np.isin(ds["SCL"].values, SCL_VALID)
            b = {}
            for band in BANDS[:-1]:
                raw = ds[band].values
                v = (raw - off) / 1e4
                v[~valid | (raw == 0)] = np.nan
                b[band] = np.clip(v, 1e-4, 1.5)
            with np.errstate(all="ignore"):
                idx = {"NDRE": (b["B8A"] - b["B05"]) / (b["B8A"] + b["B05"]),
                       "CIre": b["B07"] / b["B05"] - 1,
                       "IRECI": (b["B07"] - b["B04"]) / (b["B05"] / b["B06"])}
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    out = {k_: np.nanmedian(v, axis=0).astype(np.float32) for k_, v in idx.items()}
            out["CIre"] = np.clip(out["CIre"], -1, 30); out["IRECI"] = np.clip(out["IRECI"], -5, 30)
            return out, len(items)
        except Exception as e:   # network hiccups: retry; a scene that cannot be read is dropped
            msg = str(e)
            hit = [i for i in (items if "items" in locals() else []) if i.id.split("_")[2] in msg and i.id.split("_")[-1] in msg]
            if hit:
                bad.update(i.id for i in hit)
            log.warning("%s %s attempt %d failed: %s", aoi.key, month, k + 1, msg[:200])
            time.sleep(5 * (k + 1))
            cat = _catalog()
    return empty, 0


def build(aoi_key, workers=3):
    odc.stac.configure_rio(cloud_defaults=True, GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=3,
                           GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_CONNECTTIMEOUT=20)
    aoi = AOI_BY_KEY[aoi_key]
    d = PROC / aoi.key
    fn = d / "s2_rededge.nc"
    if fn.exists():
        return fn
    months = pd.period_range(S2_START, S2_END, freq="M")
    part = d / "s2re_parts"; part.mkdir(exist_ok=True)

    def job(m):
        f = part / f"{m}.npz"
        if not f.exists():
            res, nitems = month_composite(aoi, str(m))
            np.savez_compressed(f, nitems=nitems, **res)
            print(f"[{aoi.key}] red-edge {m} items={nitems}", flush=True)
        return int(np.load(f)["nitems"])

    with ThreadPoolExecutor(workers) as ex:
        nitems = list(ex.map(job, months))
    g = grid_info(aoi); n = g["n"] // 2
    xs = g["x0"] + 10 + 20 * np.arange(n); ys = g["y0"] + g["n"] * 10 - 10 - 20 * np.arange(n)
    data = {}
    for k in RE_INDICES:
        arr = np.stack([np.load(part / f"{m}.npz")[k] for m in months])
        data[k] = (("time", "y", "x"), np.where(np.isfinite(arr), np.round(arr * SCALE[k]), -32768).astype(np.int16))
    ds = xr.Dataset(data, coords={"time": months.to_timestamp(), "y": ys, "x": xs})
    ds["n_items"] = ("time", np.array(nitems))
    ds.attrs.update(crs=f"EPSG:{g['epsg']}", nodata=-32768, aoi=aoi.key, resolution_m=20,
                    scale_NDRE=1e-4, scale_CIre=1e-3, scale_IRECI=1e-3, source="sentinel-2-l2a @ Microsoft Planetary Computer")
    ds.to_netcdf(fn, encoding={k: {"zlib": True, "complevel": 4} for k in RE_INDICES})
    print(f"[{aoi.key}] wrote {fn}", flush=True)
    return fn


def load10(aoi_key):
    """Red-edge indices on the 10 m grid (each 20 m cell repeated 2 x 2), float32 with NaN."""
    ds = xr.open_dataset(PROC / aoi_key / "s2_rededge.nc")
    out = {}
    for k in RE_INDICES:
        v = ds[k].values
        a = np.where(v == -32768, np.nan, v / SCALE[k]).astype(np.float32)
        out[k] = np.repeat(np.repeat(a, 2, axis=1), 2, axis=2)
    return out, pd.DatetimeIndex(ds.time.values)


RE_FEATURES = [f"re_{k.lower()}{s}" for k in RE_INDICES for s in ("", "_d3", "_m12", "_anom")]


def features_aoi(aoi_key):
    """A10b features for the pixels/months of table.parquet -> data/processed/<aoi>/rededge.parquet.
    value (short gaps <= 2 months filled causally), 3-month change, 12-month causal mean, anomaly vs the
    2017-2020 mean of the same calendar month (documented baseline, as mu in features.py)."""
    from . import tsops as ts
    d = PROC / aoi_key
    tab = pd.read_parquet(d / "table.parquet", columns=["pix", "time", "row", "col"])
    ds = xr.open_dataset(d / "s2_rededge.nc")
    times = pd.DatetimeIndex(ds.time.values)
    px = tab.drop_duplicates("pix").sort_values("pix")
    pix = px["pix"].values
    r2, c2 = px["row"].values.astype(int) // 2, px["col"].values.astype(int) // 2
    cal = (times.year >= 2017) & (times.year <= 2020)
    F = {}
    for k in RE_INDICES:
        v = ds[k].values[:, r2, c2]
        Y = np.where(v == -32768, np.nan, v / SCALE[k]).astype(np.float32)
        Yc, _ = ts.causal_interp_short_gaps(Y, 2)
        clim = np.stack([np.nanmean(Yc[cal & (times.month == m)], 0) for m in range(1, 13)])
        n = "re_" + k.lower()
        F[n] = Yc
        F[n + "_d3"] = Yc - ts.lag(Yc, 3)
        F[n + "_m12"] = ts.roll_mean(Yc, 12, minp=4)
        F[n + "_anom"] = Yc - clim[times.month.values - 1]
    ti = times.get_indexer(pd.to_datetime(tab["time"]))
    pi = np.searchsorted(pix, tab["pix"].values)
    assert (ti >= 0).all()
    out = pd.DataFrame({k: v[ti, pi].astype(np.float32) for k, v in F.items()})
    out.insert(0, "time", tab["time"].values); out.insert(0, "pix", tab["pix"].values)
    out.to_parquet(d / "rededge.parquet", index=False)
    return len(out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    args = sys.argv[1:]
    if args and args[0] == "features":
        for k in args[1:]:
            print(k, features_aoi(k), flush=True)
    else:
        for k in args:
            build(k)
