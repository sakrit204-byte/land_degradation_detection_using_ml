"""Climate drivers (only those needed for the climate-conditioning model).

* [optional, not used in v1] CHIRPS v2.0 monthly rainfall (UCSB CHC, ~0.05 deg, 1981-present) - COG windowed read,
  AOI-mean over a 0.15 deg window (~3x3 CHIRPS cells) around the AOI centre.
* ERA5-Land (ECMWF/Copernicus C3S) via the Open-Meteo archive API (no key): precipitation from ERA5;
  2 m temperature, soil moisture 0-7 cm and 7-28 cm; ET0 (FAO-56) from ERA5.
Derived monthly predictors (all as anomalies vs the 1991-2020 climatology of the same month):
  P1, P3, P6, P12  - standardised rainfall accumulation (SPI-like z, gamma-free for robustness)
  T1               - temperature anomaly (degC)
  SM1, SM3         - soil-moisture anomaly (z)
  WB3              - 3-month climatic water balance (P - ET0) anomaly (z)
Output: data/processed/<aoi>/climate_monthly.csv
"""
import sys, time
import numpy as np, pandas as pd, requests, rasterio
from rasterio.windows import from_bounds
from concurrent.futures import ThreadPoolExecutor
from .config import AOIS, AOI_BY_KEY, PROC, RAW

CHIRPS = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/cogs/chirps-v2.0.{y}.{m:02d}.cog"
OM = "https://archive-api.open-meteo.com/v1/archive"


def chirps_all(start="1981-01", end="2026-09", workers=8):
    cache = RAW / "chirps_aoi_monthly.csv"
    have = pd.read_csv(cache, index_col=0, parse_dates=True) if cache.exists() else pd.DataFrame()
    months = pd.period_range(start, end, freq="M")
    todo = [m for m in months if m.to_timestamp() not in have.index]

    def one(m):
        for k in range(4):
            try:
                with rasterio.Env(GDAL_HTTP_MAX_RETRY=3, GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
                    with rasterio.open("/vsicurl/" + CHIRPS.format(y=m.year, m=m.month)) as src:
                        row = {}
                        for a in AOIS:
                            w = from_bounds(a.lon - .075, a.lat - .075, a.lon + .075, a.lat + .075, src.transform)
                            v = src.read(1, window=w, boundless=True, fill_value=-9999).astype(float)
                            v[v < 0] = np.nan
                            row[a.key] = np.nanmean(v) if np.isfinite(v).any() else np.nan
                        return m.to_timestamp(), row
            except Exception as e:
                time.sleep(3 * (k + 1))
        return m.to_timestamp(), {a.key: np.nan for a in AOIS}

    with ThreadPoolExecutor(workers) as ex:
        rows = dict(ex.map(one, todo))
    new = pd.DataFrame.from_dict(rows, orient="index")
    df = pd.concat([have, new]).sort_index()
    df = df[~df.index.duplicated()]
    df.to_csv(cache)
    return df


def _om(lat, lon, start, end, daily, model):
    for k in range(5):
        r = requests.get(OM, params=dict(latitude=lat, longitude=lon, start_date=start, end_date=end,
                                         daily=",".join(daily), models=model, timezone="GMT"), timeout=120)
        if r.status_code == 200:
            d = r.json()["daily"]
            return pd.DataFrame(d).set_index("time")
        time.sleep(10 * (k + 1))
    raise RuntimeError(r.text)


def era5_point(aoi, start="1991-01-01", end="2026-09-30"):
    f = RAW / f"era5_{aoi.key}.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0, parse_dates=True)
    a = _om(aoi.lat, aoi.lon, start, end,
            ["temperature_2m_mean", "soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean"], "era5_land")
    b = _om(aoi.lat, aoi.lon, start, end, ["et0_fao_evapotranspiration", "precipitation_sum"], "era5")
    df = a.join(b)
    df.index = pd.to_datetime(df.index)
    df.to_csv(f)
    return df


def _z(s, ref=("1991", "2020")):
    """Anomaly z-score vs same-calendar-month climatology of the reference period."""
    r = s[ref[0]:ref[1]]
    mu = r.groupby(r.index.month).mean()
    sd = r.groupby(r.index.month).std().replace(0, np.nan)
    m = s.index.month
    return (s - mu.reindex(m).values) / sd.reindex(m).values


def era5_heat(aoi, start="1991-01-01", end="2026-09-30"):
    """Daily ERA5-Land maximum temperature and maximum vapour-pressure deficit (heat/dry-air extremes)."""
    f = RAW / f"era5heat_{aoi.key}.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0, parse_dates=True)
    df = _om(aoi.lat, aoi.lon, start, end, ["temperature_2m_max", "vapour_pressure_deficit_max"], "era5_land")
    df.index = pd.to_datetime(df.index)
    df.to_csv(f)
    return df


def heat_features(aoi, t_mean_monthly):
    """Monthly heat-stress predictors (PROJECT_LOG D-018):
    HD1/HD3  days with Tmax above the 1991-2020 90th percentile of the same calendar month (1 / 3 months)
    TMAX1    anomaly of monthly mean Tmax (degC)
    VPD1/3   z-anomaly of monthly mean daily-max VPD (1 / 3 months) - atmospheric dryness
    T_C      absolute monthly mean 2 m air temperature (degC; used for LST - Tair)"""
    d = era5_heat(aoi)
    tx, vpd = d["temperature_2m_max"].astype(float), d["vapour_pressure_deficit_max"].astype(float)
    ref = tx["1991":"2020"]
    p90 = ref.groupby(ref.index.month).quantile(0.9)
    hot = (tx > p90.reindex(tx.index.month).values).astype(float)
    hot[tx.isna()] = np.nan
    out = pd.DataFrame(index=tx.resample("MS").mean().index)
    out["HD1"] = hot.resample("MS").sum(min_count=20)
    out["HD3"] = out["HD1"].rolling(3, min_periods=3).sum()
    txm = tx.resample("MS").mean()
    clim_tx = txm["1991":"2020"].groupby(txm["1991":"2020"].index.month).mean()
    out["TMAX1"] = txm - clim_tx.reindex(txm.index.month).values
    vm = vpd.resample("MS").mean()
    out["VPD1"] = _z(vm)
    out["VPD3"] = _z(vm.rolling(3, min_periods=3).mean())
    out["T_C"] = t_mean_monthly.reindex(out.index)
    return out


def build(aoi_key, chirps=None):
    """Rainfall source: ERA5 (Copernicus C3S) precipitation by default. CHIRPS is kept as an optional
    source (chirps_all) but was not used in v1 because its 25 MB global COGs cost ~2 GB of block reads
    on our 1.3 MB/s link (see PROJECT_LOG D-007)."""
    aoi = AOI_BY_KEY[aoi_key]
    e = era5_point(aoi)
    P = e["precipitation_sum"].resample("MS").sum(min_count=20) if chirps is None else chirps[aoi.key].astype(float)
    mon = pd.DataFrame({
        "T": e["temperature_2m_mean"].resample("MS").mean(),
        "SM": e["soil_moisture_0_to_7cm_mean"].resample("MS").mean(),
        "SM2": e["soil_moisture_7_to_28cm_mean"].resample("MS").mean(),
        "ET0": e["et0_fao_evapotranspiration"].resample("MS").sum(min_count=20),
    })
    df = pd.DataFrame({"P": P}).join(mon, how="outer")
    out = pd.DataFrame(index=df.index)
    out["P_mm"] = df["P"]
    for k in (1, 3, 6, 12):
        out[f"P{k}"] = _z(df["P"].rolling(k, min_periods=k).sum())
    out["T1"] = df["T"] - df["T"]["1991":"2020"].groupby(df["T"]["1991":"2020"].index.month).mean().reindex(df.index.month).values
    out["SM1"] = _z(df["SM"])
    out["SM3"] = _z(df["SM2"].rolling(3, min_periods=3).mean())
    out["WB3"] = _z((df["P"] - df["ET0"]).rolling(3, min_periods=3).sum())
    out = out.join(heat_features(aoi, df["T"]), how="left")
    out.index.name = "time"
    d = PROC / aoi.key
    d.mkdir(parents=True, exist_ok=True)
    out.to_csv(d / "climate_monthly.csv")
    return out


if __name__ == "__main__":
    for a in (sys.argv[1:] or [a.key for a in AOIS]):
        build(a)
        print("climate", a, flush=True)
