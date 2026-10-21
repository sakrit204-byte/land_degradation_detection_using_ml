"""Sentinel-2 L2A monthly composites (Microsoft Planetary Computer, no account needed).

Per AOI and month:
  1. STAC search, scene cloud cover < S2_MAX_CLOUD
  2. load B02,B03,B04,B08,B11,B12,SCL at 10 m in the AOI's UTM zone (20 m bands bilinear)
  3. per-scene radiometric harmonisation: baseline >= 04.00 -> (DN - 1000)/1e4 else DN/1e4
  4. pixel mask: SCL in {4,5,6}
  5. indices per observation, then monthly MEDIAN; valid-observation count kept for QC
Output: data/processed/<aoi>/s2_monthly.nc (int16, scale 1e-4)
"""
import sys, time, logging
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, xarray as xr
import pystac_client, planetary_computer as pc, odc.stac
from .config import AOI_BY_KEY, PROC, STAC_URL, S2_BANDS, S2_MAX_CLOUD, SCL_VALID, BOA_OFFSET_BASELINE, S2_START, S2_END

log = logging.getLogger("s2")
INDICES = ["NDVI", "NDMI", "NBR", "BSI", "R", "G", "B"]


def _catalog():
    return pystac_client.Client.open(STAC_URL, modifier=pc.sign_inplace)


def _baseline(item):
    try:
        return float(item.properties.get("s2:processing_baseline") or 0)
    except ValueError:
        return 0.0


def dedupe(items):
    """The archive holds several processings of the same datatake/tile (e.g. baseline 02.12
    and the 05.00 reprocessing). Keep only the newest processing per (tile, sensing time)."""
    best = {}
    for it in items:
        k = (it.properties.get("s2:mgrs_tile"), it.datetime.isoformat()[:19])
        if k not in best or _baseline(it) > _baseline(best[k]):
            best[k] = it
    return list(best.values())


MAX_SCENES = 4   # least-cloudy acquisitions per month used in the median composite


def select_scenes(aoi, items):
    """Use ONE MGRS tile that fully contains the AOI (overlapping tiles are the same photons,
    re-gridded) and keep the MAX_SCENES least-cloudy acquisitions of the month. Deterministic."""
    from shapely.geometry import shape, box
    g = grid_info(aoi)
    same = [i for i in items if i.properties.get("s2:mgrs_tile") == g["tile"]]
    if same:                       # the tile the grid is aligned to (normal case)
        items = same
    else:                          # fallback: any tile fully containing the grid box
        b = box(*g["bbox_wgs84"])
        full = sorted({i.properties.get("s2:mgrs_tile") for i in items if shape(i.geometry).contains(b)})
        if full:
            items = [i for i in items if i.properties.get("s2:mgrs_tile") == full[0]]
    items = sorted(items, key=lambda i: (i.properties.get("eo:cloud_cover", 100), i.datetime))
    return items[:MAX_SCENES]


GRID_N = 512     # one internal COG block of a 10 m band (512 px = 5.12 km)


def grid_info(aoi):
    """Snap the AOI to the single 512x512 internal COG block (of one MGRS tile) that contains the
    AOI centre. Reading exactly one block per 10 m band (and one 20 m block) instead of the 2x2
    blocks an arbitrary 5 km window straddles cuts download ~4x (PROJECT_LOG D-006). Cached."""
    import json
    f = PROC / aoi.key / "grid.json"
    if f.exists():
        return json.load(open(f))
    from shapely.geometry import shape, Point
    cat = _catalog()
    items = list(cat.search(collections=["sentinel-2-l2a"], intersects=Point(aoi.lon, aoi.lat).buffer(0.03).__geo_interface__,
                            datetime="2023-01-01/2023-03-31").items())
    pt = Point(aoi.lon, aoi.lat).buffer(0.03)
    tiles = sorted({(i.properties["s2:mgrs_tile"], i.properties["proj:epsg"] if "proj:epsg" in i.properties else
                     int(str(i.properties.get("proj:code", "EPSG:0")).split(":")[1])) for i in items if shape(i.geometry).contains(pt)})
    # prefer a tile in the AOI's own UTM zone
    tiles = sorted(tiles, key=lambda t: (t[1] != aoi.utm_epsg, t[0]))
    tile, epsg = tiles[0]
    it = next(i for i in items if i.properties["s2:mgrs_tile"] == tile)
    tr = it.assets["B04"].extra_fields.get("proj:transform")
    ulx, uly = tr[2], tr[5]
    from pyproj import Transformer
    cx, cy = Transformer.from_crs(4326, epsg, always_xy=True).transform(aoi.lon, aoi.lat)
    bs = GRID_N * 10
    x0 = ulx + np.floor((cx - ulx) / bs) * bs
    ytop = uly - np.floor((uly - cy) / bs) * bs
    tr_back = Transformer.from_crs(epsg, 4326, always_xy=True)
    xs = [x0, x0 + bs]; ys = [ytop - bs, ytop]
    lons, lats = zip(*[tr_back.transform(x, y) for x in xs for y in ys])
    g = dict(tile=tile, epsg=int(epsg), x0=float(x0), y0=float(ytop - bs), n=GRID_N,
             bbox_wgs84=[min(lons), min(lats), max(lons), max(lats)])
    f.parent.mkdir(parents=True, exist_ok=True)
    json.dump(g, open(f, "w"), indent=2)
    return g


def _grid(aoi):
    g = grid_info(aoi)
    return g["x0"], g["y0"], g["n"]


def _epsg(aoi):
    return grid_info(aoi)["epsg"]


def month_composite(aoi, month, cat=None, retries=6):
    """Unreadable scenes (corrupt / missing COG in the archive, I-019) are excluded one by one and the month
    is recomposited from the remaining scenes; excluded ids are appended to data/processed/<aoi>/bad_scenes.txt."""
    cat = cat or _catalog()
    start = pd.Timestamp(month)
    end = start + pd.offsets.MonthEnd(0)
    bad = set()
    for k in range(retries):
        try:
            items = list(cat.search(collections=["sentinel-2-l2a"], bbox=grid_info(aoi)["bbox_wgs84"],
                                    datetime=f"{start:%Y-%m-%d}/{end:%Y-%m-%d}",
                                    query={"eo:cloud_cover": {"lt": S2_MAX_CLOUD}}).items())
            x0, y0, n = _grid(aoi)
            out = {k_: np.full((n, n), np.nan, np.float32) for k_ in INDICES}
            if not items:
                return out, 0, 0
            from odc.geo.geobox import GeoBox
            from affine import Affine
            gbox = GeoBox((n, n), Affine(10, 0, x0, 0, -10, y0 + n * 10), f"EPSG:{_epsg(aoi)}")
            items = sel = select_scenes(aoi, [i for i in dedupe(items) if i.id not in bad])
            if not items:
                return out, 0, 0
            parts = []
            for has_off in (False, True):
                grp = [pc.sign(i) for i in items if (_baseline(i) >= BOA_OFFSET_BASELINE) == has_off]
                if not grp:
                    continue
                d_ = odc.stac.load(grp, bands=S2_BANDS, geobox=gbox, groupby="id",
                                   resampling={"SCL": "nearest", "*": "bilinear"}, chunks={}, dtype="float32", nodata=0).compute()
                d_["off"] = ("time", np.full(d_.sizes["time"], 1000.0 if has_off else 0.0))
                parts.append(d_)
            ds = xr.concat(parts, dim="time") if len(parts) > 1 else parts[0]
            base = np.array([_baseline(i) for i in items])
            off = ds["off"].values[:, None, None]
            scl = ds["SCL"].values
            valid = np.isin(scl, SCL_VALID)
            b = {}
            for band in S2_BANDS[:-1]:
                v = ds[band].values
                v = (v - off) / 1e4
                v[~valid | (ds[band].values == 0)] = np.nan
                b[band] = np.clip(v, 0, 1.5)
            eps = 1e-6
            idx = {
                "NDVI": (b["B08"] - b["B04"]) / (b["B08"] + b["B04"] + eps),
                "NDMI": (b["B08"] - b["B11"]) / (b["B08"] + b["B11"] + eps),
                "NBR": (b["B08"] - b["B12"]) / (b["B08"] + b["B12"] + eps),
                "BSI": ((b["B11"] + b["B04"]) - (b["B08"] + b["B02"])) / ((b["B11"] + b["B04"]) + (b["B08"] + b["B02"]) + eps),
                "R": b["B04"], "G": b["B03"], "B": b["B02"],
            }
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                out = {k_: np.nanmedian(v, axis=0).astype(np.float32) for k_, v in idx.items()}
            # distinct acquisition days with a valid obs (tiles overlap on the same day)
            days = pd.to_datetime(ds.time.values).normalize()
            cnt = np.zeros((n, n), np.int16)
            for d in np.unique(days):
                cnt += valid[days == d].any(axis=0)
            out["nobs"] = cnt
            return out, len(items), float(np.mean(base))
        except Exception as e:  # network hiccups are common; retry with backoff
            msg = str(e)
            cand = [i for i in (sel if "sel" in locals() else []) if i.id not in bad]
            # the failing COG URL contains the sensing time and processing time of the scene id
            hit = [i for i in cand if i.id.split("_")[2] in msg and i.id.split("_")[-1] in msg]
            if not hit and "Read failed" in msg and k >= 2 and cand:
                hit = [cand[-1]]          # cannot identify the scene: drop the cloudiest selected one
            if hit:
                bad.update(i.id for i in hit)
                with open(PROC / aoi.key / "bad_scenes.txt", "a") as f:
                    f.write("%s\t%s\t%s\n" % (month, ",".join(i.id for i in hit), msg[:160].replace("\n", " ")))
            log.warning("%s %s attempt %d failed: %s", aoi.key, month, k + 1, e)
            time.sleep(5 * (k + 1))
            cat = _catalog()
    # last resort: an empty (all-NaN) month, recorded - better than blocking the whole AOI
    with open(PROC / aoi.key / "bad_scenes.txt", "a") as f:
        f.write("%s\tALL\tmonth left empty after %d attempts\n" % (month, retries))
    x0, y0, n = _grid(aoi)
    return {k_: np.full((n, n), np.nan, np.float32) for k_ in INDICES}, 0, 0


def build(aoi_key, workers=4):
    odc.stac.configure_rio(cloud_defaults=True, GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=3,
                           GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_CONNECTTIMEOUT=20)   # stalled reads fail + retry (I-017)
    aoi = AOI_BY_KEY[aoi_key]
    d = PROC / aoi.key
    d.mkdir(parents=True, exist_ok=True)
    fn = d / "s2_monthly.nc"
    months = pd.period_range(S2_START, S2_END, freq="M")
    if fn.exists():
        with xr.open_dataset(fn) as old:
            if old.sizes["time"] == len(months):      # finished cube: never rewrite (I-018)
                return fn
    part = d / "s2_parts"
    part.mkdir(exist_ok=True)
    meta = []

    def job(m):
        f = part / f"{m}.npz"
        if f.exists():
            z = np.load(f)
            return m, int(z["nitems"]), float(z["base"])
        res, nitems, base = month_composite(aoi, str(m))
        if "nobs" not in res:
            x0, y0, n = _grid(aoi)
            res["nobs"] = np.zeros((n, n), np.int16)
        np.savez_compressed(f, nitems=nitems, base=base, **res)
        print(f"[{aoi.key}] {m} items={nitems}", flush=True)
        return m, nitems, base

    with ThreadPoolExecutor(workers) as ex:
        meta = list(ex.map(job, months))

    x0, y0, n = _grid(aoi)
    xs = x0 + 5 + 10 * np.arange(n)
    ys = y0 + n * 10 - 5 - 10 * np.arange(n)
    data = {}
    for k_ in INDICES + ["nobs"]:
        arr = np.stack([np.load(part / f"{m}.npz")[k_] for m in months])
        if k_ == "nobs":
            data[k_] = (("time", "y", "x"), arr.astype(np.int16))
        else:
            data[k_] = (("time", "y", "x"), np.where(np.isfinite(arr), np.round(arr * 1e4), -32768).astype(np.int16))
    ds = xr.Dataset(data, coords={"time": months.to_timestamp(), "y": ys, "x": xs})
    ds["n_items"] = ("time", np.array([m[1] for m in meta]))
    ds["baseline"] = ("time", np.array([m[2] for m in meta]))
    ds.attrs.update(crs=f"EPSG:{_epsg(aoi)}", scale=1e-4, nodata=-32768, aoi=aoi.key,
                    source="sentinel-2-l2a @ Microsoft Planetary Computer")
    enc = {k_: {"zlib": True, "complevel": 4} for k_ in INDICES + ["nobs"]}
    ds.to_netcdf(fn, encoding=enc)
    print(f"[{aoi.key}] wrote {fn}", flush=True)
    return fn


def load(aoi_key):
    ds = xr.open_dataset(PROC / aoi_key / "s2_monthly.nc")
    out = ds.copy()
    for k_ in INDICES:
        v = ds[k_].values.astype(np.float32)
        v[ds[k_].values == -32768] = np.nan
        out[k_] = (("time", "y", "x"), v * 1e-4)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    for k in sys.argv[1:]:
        build(k)
