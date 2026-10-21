# CARE-EW — Climate-Adjusted Resilience Early Warning of land degradation

Predicts, every month and for every 10 m pixel, the **probability that persistent, climate-unexplained
vegetation decline will begin within the next 6 months**, with calibrated probabilities and an explicit
"abstain / inspect in the field" state. Built only on open Earth-observation data (Sentinel-2, MODIS,
Landsat, ERA5/ERA5-Land, ESA WorldCover, NASADEM, JRC GSW, HydroRIVERS, GloFAS).

| Read this | For |
|---|---|
| `docs/PROJECT_LOG.md` | **Everything**: data, every decision (D-xxx), issue (I-xxx), experiment (E-xxx), result (R-xxx), threats to validity |
| `paper/CARE-EW_paper_draft.md` | Paper draft |
| `docs/UI_DATA_SPEC.md` | Data contract between pipeline and web console |
| `app/README.md` | Web console |
| `outputs/figures/` | Paper figures (PNG + PDF) |
| `outputs/results/metrics.json` | All validation numbers |
| `outputs/screenshots/` | UI screenshots (proof of the operational product) |

## Layout
```
care_ew/            pipeline package
  config.py         AOIs, periods, thresholds, splits (single source of truth)
  s2.py             Sentinel-2 L2A monthly composites (dedupe, BOA offset, block-aligned grid)
  climate.py        ERA5 / ERA5-Land anomalies
  context.py        WorldCover, NASADEM, JRC water, MODIS, Landsat
  hydro.py          HydroRIVERS upstream network, GloFAS discharge before/now, distance to river
  tsops.py          causal time-series operators (unit-tested)
  features.py       baseline, climate model, peer-relative residual, feature groups A1-A6
  labels.py         future persistent-degradation labels
  dataset.py        per-AOI cube + training table
  train.py          ablation, calibrated model + conformal, LOCO, curves, walk-forward, sensitivity
  predict.py        wall-to-wall monthly risk maps
  corroborate.py    Landsat / MODIS agreement with labels
  figures.py        paper figures
  export.py         app data
scripts/            run_all.py, fetch_rest.sh, provenance.py, update_monthly.py
tests/              leakage + label tests (pytest)
app/                FastAPI server + CesiumJS console
```

## Run
```
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
bash scripts/fetch_rest.sh                    # data (resumable, outage-tolerant; hours on slow links)
.venv/Scripts/python scripts/run_all.py       # dataset -> train -> predict -> corroborate -> figures -> export
.venv/Scripts/python -m uvicorn app.server:app --port 8765   # open http://127.0.0.1:8765
.venv/Scripts/python -m pytest -q tests
CAREEW_S2_END=2026-10 .venv/Scripts/python scripts/update_monthly.py   # monthly operational update
```

## Honest scope
Labels are Earth-observation proxies (persistent decline relative to climate expectation *and* landscape
peers), not field-verified degradation. The console is decision support for prioritising field
inspection, not an automated determination. See PROJECT_LOG §11.
