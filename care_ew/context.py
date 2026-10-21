"""Context & corroboration layers, all from Microsoft Planetary Computer.

static.nc   : ESA WorldCover 2021 (10 m land cover), NASADEM elevation + slope (resampled to 10 m),
              JRC Global Surface Water occurrence (30 m -> 10 m).
modis.nc    : MODIS Terra MOD13Q1 v061 NDVI, 250 m, 2000-present, reliability <= 1, monthly max.
              Long history -> long-term climatology & resilience context at coarse scale.
landsat.nc  : Landsat 8/9 C2 L2 NDVI, 30 m, monthly median 2017-present.
              INDEPENDENT sensor (NASA/USGS) used ONLY for corroborating S2-derived labels.
"""
import sys, warnings
import numpy as np, pandas as pd, xarray as xr
import pystac_client, planetary_computer as pc, odc.stac
from odc.geo.geobox import GeoBox
from affine import Affine
from .config import AOIS, AOI_BY_KEY, PROC, STAC_URL, S2_START, S2_END, MODIS_START
from .s2 import _grid, _epsg, grid_info

warnings.filterwarnings("ignore", category=RuntimeWarning)


def cat():
    return pystac_client.Client.open(STAC_URL, modifier=pc.sign_inplace)


def gbox(aoi, res=10, pad_m=0):
    x0, y0, n = _grid(aoi)
    x0 -= pad_m; y0 -= pad_m
    size = int((n * 10 + 2 * pad_m) / res)
    return GeoBox((size, size), Affine(res, 0, x0, 0, -res, y0 + size * res), f"EPSG:{_epsg(aoi)}")


def static(aoi_key):
    aoi = AOI_BY_KEY[aoi_key]
    c = cat(); g = gbox(aoi)
    wc = odc.stac.load(list(c.search(collections=["esa-worldcover"], bbox=grid_info(aoi)["bbox_wgs84"], datetime="2021").items()),
                       bands=["map"], geobox=g, resampling="nearest")["map"].max("time")
    dem = odc.stac.load(list(c.search(collections=["nasadem"], bbox=grid_info(aoi)["bbox_wgs84"]).items()), bands=["elevation"],
                        geobox=g, resampling="bilinear", dtype="float32").elevation.max("time")
    gy, gx = np.gradient(dem.values, 10.0)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    gsw = odc.stac.load(list(c.search(collections=["jrc-gsw"], bbox=grid_info(aoi)["bbox_wgs84"]).items()), bands=["occurrence"],
                        geobox=g, resampling="nearest").occurrence.max("time")
    occ = gsw.values.astype(np.float32); occ[occ > 100] = 0
    ds = xr.Dataset({"landcover": (("y", "x"), wc.values.astype(np.uint8)),
                     "elev": (("y", "x"), dem.values.astype(np.float32)),
                     "slope": (("y", "x"), slope.astype(np.float32)),
                     "water_occ": (("y", "x"), occ)})
    ds.to_netcdf(PROC / aoi.key / "static.nc")
    return ds


def modis(aoi_key):
    aoi = AOI_BY_KEY[aoi_key]
    c = cat()
    items = [i for i in c.search(collections=["modis-13Q1-061"], bbox=grid_info(aoi)["bbox_wgs84"],
                                 datetime=f"{MODIS_START}-01/{S2_END}-28").items() if i.id.startswith("MOD13Q1")]
    # dedupe processing versions
    best = {}
    for i in items:
        k = i.id.split(".")[1] + i.id.split(".")[2]
        best[k] = i
    items = sorted(best.values(), key=lambda i: i.properties.get("start_datetime") or str(i.datetime))
    g = gbox(aoi, res=250, pad_m=2500)
    odc.stac.configure_rio(cloud_defaults=True, GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_CONNECTTIMEOUT=20, GDAL_HTTP_MAX_RETRY=5)
    ds = odc.stac.load(items, bands=["250m_16_days_NDVI", "250m_16_days_pixel_reliability"], geobox=g,
                       chunks={"time": 32}, groupby="solar_day", resampling="nearest", dtype="float32",
                       fail_on_error=False)   # an unreadable composite becomes a gap, not a crash (I-020)
    nd = ds["250m_16_days_NDVI"].astype("float32")
    rel = ds["250m_16_days_pixel_reliability"]
    nd = nd.where((rel >= 0) & (rel <= 1) & (nd > -3000) & (nd <= 10000)) * 1e-4
    mon = nd.resample(time="MS").max().compute()
    mon.name = "NDVI"
    mon.to_dataset().to_netcdf(PROC / aoi.key / "modis.nc")
    print(f"[{aoi.key}] modis {mon.sizes}", flush=True)
    return mon


def lst(aoi_key):
    """MODIS Terra MOD11A2 v061 daytime land-surface temperature, 8-day, 1 km, QC 'good' or 'other quality'
    (bits 0-1 in {0,1}), monthly mean in degC, 2.5 km padding. (D-018)"""
    aoi = AOI_BY_KEY[aoi_key]
    c = cat()
    items = [i for i in c.search(collections=["modis-11A2-061"], bbox=grid_info(aoi)["bbox_wgs84"],
                                 datetime=f"{MODIS_START}-01/{S2_END}-28").items() if i.id.startswith("MOD11A2")]
    best = {}
    for i in items:
        best[i.id.split(".")[1] + i.id.split(".")[2]] = i
    items = sorted(best.values(), key=lambda i: i.properties.get("start_datetime") or str(i.datetime))
    g = gbox(aoi, res=1000, pad_m=2500)
    odc.stac.configure_rio(cloud_defaults=True, GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_CONNECTTIMEOUT=20, GDAL_HTTP_MAX_RETRY=5)
    ds = odc.stac.load(items, bands=["LST_Day_1km", "QC_Day"], geobox=g, chunks={"time": 32}, groupby="solar_day",
                       resampling="nearest", dtype="float32", fail_on_error=False)
    # QC_Day == 0 means "good quality" but the asset declares nodata=0, so odc masks it to NaN. Treat a
    # missing QC as 0 (good); LST validity itself is enforced by LST > 0. (I-022: the first version used
    # fillna(255) and silently discarded every best-quality pixel -> 20-40 % coverage, cool bias.)
    qc = ds["QC_Day"].fillna(0).astype("uint16")
    t = ds["LST_Day_1km"].where((ds["LST_Day_1km"] > 0) & ((qc & 3) <= 1)) * 0.02 - 273.15
    mon = t.resample(time="MS").mean().compute()
    mon.name = "LST"
    mon.to_dataset().to_netcdf(PROC / aoi.key / "lst.nc")
    print(f"[{aoi.key}] lst {dict(mon.sizes)} valid {float(np.isfinite(mon).mean()):.2f}", flush=True)
    return mon


def landsat(aoi_key):
    aoi = AOI_BY_KEY[aoi_key]
    c = cat()
    items = []
    for period in ("2018-01-01/2020-12-31", "2023-01-01/2026-09-30"):   # baseline years + evaluation years
        items += list(c.search(collections=["landsat-c2-l2"], bbox=grid_info(aoi)["bbox_wgs84"], datetime=period,
                               query={"platform": {"in": ["landsat-8", "landsat-9"]}, "eo:cloud_cover": {"lt": 60}}).items())
    by_m = {}
    for i in items:
        by_m.setdefault(i.datetime.strftime("%Y-%m"), []).append(i)
    items = [j for v in by_m.values() for j in sorted(v, key=lambda i: i.properties["eo:cloud_cover"])[:2]]
    g = gbox(aoi, res=30)
    odc.stac.configure_rio(cloud_defaults=True, GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_CONNECTTIMEOUT=20, GDAL_HTTP_MAX_RETRY=5)
    ds = odc.stac.load(items, bands=["red", "nir08", "qa_pixel"], geobox=g, chunks={"time": 16},
                       groupby="solar_day", resampling={"qa_pixel": "nearest", "*": "bilinear"}, fail_on_error=False)
    qa = ds.qa_pixel.astype("uint16")
    bad = ((qa & (1 << 1)) | (qa & (1 << 3)) | (qa & (1 << 4)) | (qa & (1 << 5)) | (qa & (1 << 0))) > 0
    red = ds.red.astype("float32") * 2.75e-5 - 0.2
    nir = ds.nir08.astype("float32") * 2.75e-5 - 0.2
    nd = ((nir - red) / (nir + red)).where(~bad & (ds.red > 0))
    mon = nd.resample(time="MS").median().compute()
    mon.name = "NDVI"
    mon.to_dataset().to_netcdf(PROC / aoi.key / "landsat.nc")
    print(f"[{aoi.key}] landsat {mon.sizes}", flush=True)
    return mon


if __name__ == "__main__":
    what = sys.argv[1]
    for a in (sys.argv[2:] or [a.key for a in AOIS]):
        (PROC / a).mkdir(parents=True, exist_ok=True)
        {"static": static, "modis": modis, "landsat": landsat, "lst": lst}[what](a)
        print(what, a, "ok", flush=True)
