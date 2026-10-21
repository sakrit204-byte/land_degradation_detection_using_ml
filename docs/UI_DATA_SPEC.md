# CARE-EW app data contract (pipeline -> UI)

The pipeline (`care_ew/export.py`) writes everything the UI needs under `app/static/data/`.
The UI must ONLY read these files (plus the small FastAPI endpoints below). All coordinates WGS84 lon/lat.

## `aois.json`
```json
{ "generated": "2026-10-19", "model_version": "careew-lgbm-v1", "latest_month": "2026-09",
  "months": ["2019-01", "...", "2026-09"],
  "aois": [ { "key": "NPL_chure", "country": "Nepal", "landscape": "...", "rationale": "...",
              "center": [85.95, 27.05], "bbox": [w, s, e, n],
              "stats": { "risk_mean": 0.12, "area_high_ha": 35.2, "area_abstain_ha": 12.0,
                         "n_hotspots": 7, "ndvi_trend_per_yr": -0.004, "pos_rate_hist": 0.05 } } ] }
```

## Per AOI: `aois/<key>/`
* `risk/<YYYY-MM>.png` – RGBA overlay exactly covering `bbox`. Colour = calibrated probability of a
  future persistent degradation onset within 6 months (transparent below 0.15; yellow->orange->red).
  Hatched/purple pixels = conformal "abstain" (model uncertain).  Available for every month in `months_risk`.
* `ndvi/<YYYY-MM>.png` – NDVI anomaly (z) overlay, brown(-3)..white(0)..green(+3).
* `rgb/<YYYY-MM>.png` – Sentinel-2 true colour of that month (for before/after).
* `meta.json` – `{ "months_risk": [...], "months_rgb": [...], "grid": {"H":500,"W":500}, "legend": {...} }`
* `hotspots.geojson` – FeatureCollection of Polygon boxes (axis-aligned bbox of a connected cluster of
  high-risk pixels at the latest month). properties:
  `id, label ("H1"...), risk_mean, risk_max, area_ha, status ("warning"|"watch"|"abstain"|"active_degradation"),
   landcover, first_warning (YYYY-MM, first month this cluster exceeded the threshold),
   drivers: [{"name": "Residual R (6-mo mean)", "contribution": 0.31}, ...] (top-5 model explanations),
   ndvi_now, ndvi_baseline, rain_anom_6m, dist_river_km, chip_before, chip_after (relative png paths)`
* `rivers_network.geojson` – LineStrings, properties `HYRIV_ID, ORD_STRA, DIS_AV_CMS (long-term mean
  flow m3/s), UPLAND_SKM, role ("upstream"|"outlet"|"downstream")`. Draw width by ORD_STRA, colour by role.
* `rivers_local.geojson` – all reaches near the AOI (same properties, no role).
* `hydro.json` – `{ outlet_id, outlet_mean_q, stations: [{name, lat, lon, available, mean_before,
  mean_now, q90_before, q90_now, change_mean_pct, change_lowflow_pct}] }` ("before" = 1984-2000, "now" = 2016-).
* `timeseries.json` – `{ "months": [...], "ndvi_mean": [...], "z_mean": [...], "resid_mean": [...],
  "frac_below": [...], "risk_mean": [...], "rain_anom_6m": [...], "temp_anom": [...], "soil_moist_anom": [...],
  "discharge_outlet": [...] }` (null where missing)

## Global
* `metrics.json` – model validation summary (see train.py); UI shows a "Model card" panel:
  PR-AUC, ROC-AUC, Brier, ECE, lead time, ablation table, leave-one-country-out table.

## API (FastAPI, `app/server.py`)
* `GET /api/pixel?aoi=KEY&lon=..&lat=..` -> `{months, ndvi, z, resid, risk, label_onsets:[YYYY-MM], landcover}`
* `GET /api/health`
