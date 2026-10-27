# CARE-EW — Project Log

> **Purpose.** This log is the single source of truth for the CARE-EW study: every data source, every
> processing choice, every threshold, every deviation from the original slide plan, every result and
> every known weakness. It is written so that (a) the paper can be drafted directly from it and (b) a
> reviewer — human or another LLM — can reconstruct the workflow and **look for flaws**. Where we know
> of a flaw we say so in the "Known issues / threats to validity" section rather than hiding it.
>
> Conventions: `D-xxx` = design decision, `E-xxx` = experiment, `I-xxx` = issue found, `R-xxx` = result.
> Paths are relative to the project root. Times are local (UTC+05:45).

---

## 0. Project in one paragraph

CARE-EW ("Climate-Adjusted Resilience Early Warning") asks whether we can **warn before land degradation
becomes obvious**. Rather than classifying already-degraded land, we predict, at month *t*, the probability
that a pixel will enter a *persistent, climate-unexplained vegetation decline* in the next *H* = 6 months.
Inputs are only what is observable at *t*: Sentinel-2 10 m spectral state and change, a climate-conditioned
residual (observed vs. climate-expected vegetation), resilience indicators (lag-1 autocorrelation, variance,
recovery), MODIS 250 m long-record context, and spatial/terrain/hydrological context. The model is a
gradient-boosted tree ensemble with isotonic calibration and split-conformal abstention. Validation uses
spatial **and** temporal hold-outs, leave-one-country-out, cumulative ablations A0–A7, lead-time analysis,
and independent-sensor corroboration of the labels.

Source plan: `AI_Project_CARE_EW_Polished_Final  -  Repaired.pptx` (15 slides; text extracted 2026-10-19).

---

## 1. Environment

| Item | Value |
|---|---|
| Machine | Windows 11 Pro, 12 logical cores, 16 GB RAM, RTX 4050 6 GB (not needed: tree models on CPU) |
| Python | 3.11.9, project venv `.venv` |
| Key libs | numpy 2.4, pandas 2.3, xarray 2026.9, rasterio 1.4.4, odc-stac 0.5.3, pystac-client, planetary-computer 1.0, geopandas 1.2, lightgbm 4.7, scikit-learn 1.9 |
| Network | ~0.5 MB/s single stream, ~1.3 MB/s aggregate to Azure (measured 2026-10-19). **Bandwidth is the binding constraint of the whole study** and drove D-005, D-006, D-007. |
| Accounts | none required (all sources are open, anonymous access) |

Reproduce: `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`, then run the
pipeline in §9.

---

## 2. Data sources (all open; OSINT)

| Layer | Provider / organisation | Product | Res. | Period | Access | Used for |
|---|---|---|---|---|---|---|
| Optical reflectance | ESA / Copernicus | Sentinel-2 L2A (Sen2Cor) | 10–20 m | 2017-01 → 2026-09 | Microsoft Planetary Computer STAC `sentinel-2-l2a` | features + **labels** |
| Vegetation history | NASA LP DAAC | MODIS Terra MOD13Q1 v061 NDVI | 250 m | 2000-02 → | PC `modis-13Q1-061` | long-record anomaly & resilience context |
| Independent optical | NASA / USGS | Landsat 8/9 C2 L2 | 30 m | 2017 → | PC `landsat-c2-l2` | **label corroboration only** (never a feature) |
| Climate | ECMWF / Copernicus C3S | ERA5-Land (T2m, soil moisture 0–7 & 7–28 cm), ERA5 (precip., FAO-56 ET0) | ~9–25 km | 1991 → | Open-Meteo archive API | climate-expected vegetation |
| Land cover | ESA | WorldCover 2021 v200 | 10 m | 2021 | PC `esa-worldcover` | masking, stratification, feature |
| Terrain | NASA | NASADEM | 30 m | 2000 | PC `nasadem` | elevation, slope |
| Surface water | EC JRC | Global Surface Water v1.3 occurrence | 30 m | 1984–2020 | PC `jrc-gsw` | context feature |
| Rivers | WWF / HydroSHEDS | HydroRIVERS v1.0 | 15″ | static | data.hydrosheds.org | upstream network, distance-to-river |
| River discharge | Copernicus EMS | GloFAS v4 reanalysis | ~5 km | 1984 → | Open-Meteo Flood API | "before vs now" river flow |
| Base imagery (UI only) | Esri | World Imagery | – | – | ArcGIS REST | visual context, not analysis |

**Label provenance (D-002).** Every training label in every nation comes from *one* provider (Copernicus
Sentinel-2 L2A), *one* processor family (Sen2Cor), *one* rule (§5) with *one* set of thresholds, expressed in
units of each pixel's own seasonal baseline and variability. That is what makes labels comparable between,
e.g., Sahelian rangeland and Nepali Siwalik forest.

---

## 3. Study areas (D-001)

Nine 5 × 5 km AOIs (500 × 500 px at 10 m), nine nations, five continents, chosen to span climates and
degradation processes **and** to include "hard negatives" where vegetation declines for climatic reasons:

| Key | Nation | Landscape | Centre (lon, lat) | Why |
|---|---|---|---|---|
| NPL_chure | Nepal | Siwalik/Chure foothill forest–agri mosaic | 85.95, 27.05 | forest degradation, erosion, sediment to Terai |
| IND_bundelkhand | India | semi-arid rainfed cropland/scrub | 79.60, 25.40 | drought, erosion, abandonment |
| ETH_tigray | Ethiopia | highland cropland & hillslopes | 39.50, 13.60 | soil degradation; 2020–22 conflict shock |
| KEN_baringo | Kenya | semi-arid rangeland | 36.05, 0.65 | overgrazing, gullying, *Prosopis* |
| SEN_ferlo | Senegal | Sahelian rangeland | −14.90, 15.40 | rainfall-driven greening/browning (climate test) |
| ESP_murcia | Spain | Mediterranean dryland | −1.35, 37.75 | EU desertification hotspot |
| BRA_matopiba | Brazil | Cerrado frontier | −45.90, −12.20 | rapid conversion → clear true positives |
| MNG_steppe | Mongolia | temperate steppe | 106.50, 46.40 | grazing + dzud; winter snow masking |
| AUS_murraydarling | Australia | semi-arid rangeland/dry cropping | 146.00, −31.50 | 2017–19 drought = decline that is *climate*, not degradation |

AOI size was limited by bandwidth (D-005). Each AOI is gridded on a fixed 10 m UTM grid (zone from centre
longitude) so all months align pixel-exactly.

---

## 4. Processing chain

### 4.1 Sentinel-2 monthly composites — `care_ew/s2.py`
1. STAC search per AOI-month, scene cloud cover < 70 %.
2. **De-duplication (I-001, D-003).** The archive contains several processings of the same datatake/tile
   (e.g. baseline 02.12 from 2020 and the 05.00 reprocessing from 2022). Without de-duplication those
   are counted twice and — worse — carry *different radiometric offsets*. We keep the newest processing per
   (MGRS tile, sensing time).
3. **Single tile + 4 least-cloudy acquisitions (D-005).** Overlapping MGRS tiles are re-gridded copies of
   the same photons; we use the first tile (alphabetical) whose footprint fully contains the AOI, and the 4
   lowest-cloud acquisitions of the month. Reduces download ~3× with minimal information loss. Scene-level
   cloud % is tile-wide, so a "clear" scene can be cloudy over the AOI; pixel masking (step 5) handles it.
4. **Radiometric harmonisation (D-004).** Baseline ≥ 04.00 (from 2022-01-25, and all reprocessed data)
   has `BOA_ADD_OFFSET = −1000`: reflectance = (DN − 1000)/10 000; older baselines: DN/10 000. Applied
   per scene, *before* compositing, by loading offset and non-offset scenes as separate groups
   (I-002: time-slice order returned by odc-stac does not match item order, so offsets cannot be mapped
   by position).
5. Pixel mask: Sen2Cor SCL ∈ {4 vegetation, 5 bare soil, 6 water}; everything else (cloud, shadow,
   cirrus, snow, saturated, unclassified) removed.
6. Indices per observation, then monthly **median**: NDVI, NDMI, NBR, BSI; plus median R, G, B for
   true-colour proof chips. Valid acquisition-day count `nobs` kept for QC.
7. Stored int16 × 10⁻⁴ in `data/processed/<aoi>/s2_monthly.nc`.

### 4.2 Climate — `care_ew/climate.py`
AOI-centre daily series → monthly; anomalies vs **1991–2020** same-month climatology:
P1, P3, P6, P12 (standardised rainfall accumulations), T1 (temperature anomaly), SM1, SM3 (soil
moisture z), WB3 (3-month P − ET0 z). **D-007:** rainfall from ERA5 rather than CHIRPS (slide 4): CHIRPS'
global 25 MB COGs required ~2 GB of block reads on our link. Side benefit: all climate inputs come from
one organisation (Copernicus C3S). Known cost: ERA5 precipitation is less accurate than CHIRPS over
convective tropics (Ethiopia, Kenya, Sahel) — see Threats §11.

### 4.3 Context — `care_ew/context.py`, `care_ew/hydro.py`
WorldCover 2021 (10 m), NASADEM elevation/slope, JRC GSW occurrence → `static.nc`.
MODIS MOD13Q1 NDVI monthly max (reliability ≤ 1), 250 m with 2.5 km padding → `modis.nc`.
HydroRIVERS: outlet reach = largest-discharge reach intersecting the AOI (else nearest order ≥ 3);
upstream network traced via `NEXT_DOWN` topology (≤ 300 km), downstream path 60 reaches;
GloFAS daily discharge at outlet + up to 3 large tributaries; "before" = 1984–2000, "now" = 2016–present
(mean and low-flow Q90). Distance-to-river raster for features.

---

## 5. Targets — `care_ew/labels.py` (D-008)

Notation per pixel, month *t*:
* *Y*ₜ observed NDVI; μₘ per-pixel calendar-month **median** over calibration years 2017–2020;
  σ = 1.4826·MAD of (*Y* − μₘ) over calibration years, floored at 0.02.
* *z*ₜ = (*Y*ₜ − μₘ₍ₜ₎)/σ.
* Climate model (D-009): for each AOI × WorldCover class, ridge regression *g* of the class-mean *z*
  on climate predictors (P1,P3,P6,P12,T1,SM1,SM3,WB3, lagged P3/SM3, season interactions), fitted on the
  **training period only** (≤ 2022-03) with **leave-one-year-out cross-fitting** inside it; per-pixel
  sensitivity β (regression of pixel *z* on *g*, shrunk toward 1 with 24 pseudo-months, clipped [0, 3]).
  Ẑₜ = β·*g*(climateₜ).
* Absolute residual R^abs = z − Ẑ; **peer-relative residual (label v2, D-014)**
  **Rₜ = R^abs_ₜ − median{R^abs_ₜ over pixels of the same land-cover class}**; likewise
  devₜ = (Yₜ − μₘ) − peer median of (Y − μₘ).
* Month *s* is *below expectation* if Rₛ ≤ −1.0 **and** devₛ ≤ −0.02 (noise floor; label v3, D-017).
* **Event onset** at *s*: below at *s*, not below at *s* − 1, run length ≥ **6** months (D-015),
  ≥ 75 % of the first 6 run months are real (not gap-filled) observations, and the **mean dev over those
  6 months ≤ −0.05** (D-017).
* **Label** at *t* (pixel eligible = not below at *t*): *y*ₜ = 1 iff an onset occurs in (*t*, *t* + 6].
  Undefined if the record ends before *t* + 11 or < 60 % of months *t*+1…*t*+11 were observed.
* Sensitivity grid: thr ∈ {−0.75, −1.0, −1.5} × min_run ∈ {4, 6, 9}.
* (v1 — absolute residual, min_run 4 — rejected in E-001; v2 — per-month dev ≤ −0.05 — rejected in I-021
  because it made events impossible in dormant ecosystems. Both kept in the log for transparency.)

Unit tests (`tests/test_core.py`) verify the onset/label logic on synthetic series (persistent vs.
transient dip, eligibility, end-of-record), and that **every feature operator is causal** (perturbing the
future never changes values at ≤ *t*).

---

## 6. Features — `care_ew/features.py` (all causal; ablation groups)

| Group | Features |
|---|---|
| A1 state | NDVI, *z*, NDVI−μ, NDMI, NBR, BSI, data age, σ, μₘ, month sin/cos, land cover |
| A2 change | ΔNDVI (1, 3, 12 mo), *z* mean 3/6, *z* min 6, NDVI slope 12/36, negative-*z* run, ΔNDMI 3, BSI slope 12 |
| A3 climate | P1, P3, P6, P12, T1, SM1, SM3, WB3 |
| A4 residual | Ẑ, R^abs, R^abs mean 3, peer median R (common mode), NDVI dev rel. to peers, R (peer-relative), R mean 3/6/12, R min 6, R slope 12, negative-R run, fraction below thr (12 mo) |
| A5 resilience | AC1 & variance of high-passed R (12 & 24 mo), ΔAC1 (12 mo), variance ratio, months since dip, recovery fraction, MODIS AC1/var (60 mo) and *z* (lagged 1 month) |
| A6 spatial | R neighbourhood mean 50 m/210 m, R s.d. 210 m, *z* mean 210 m, AOI fraction below, elevation, slope, water occurrence, distance to river |
| A7 uncertainty | isotonic calibration + Mondrian split-conformal sets (α = 0.10) → event / no-event / **abstain** |

Gap filling for features is **causal** (carry-forward ≤ 2 months, with `data_age` exposed). Gap filling
for labels uses interior linear interpolation (labels may see the future by definition).
MODIS features are lagged 1 month because a 16-day composite starting in month *m* can extend into *m* + 1.

---

## 7. Training & validation protocol — `care_ew/train.py` (D-010)

* Temporal: train *t* ≤ 2022-03 │ val 2023-03…2023-12 │ test 2024-12…2025-10. Gaps ≥ *H* + min_run − 1 = 11
  months so no label window of an earlier split overlaps a later split ("embargo").
* Spatial: 1 km blocks (100 × 100 px); deterministic hash → 60 % train / 20 % val / 20 % test blocks.
* **Primary test = test period ∩ test blocks** (new place *and* new time); evaluated once.
* Early stopping on val-period × val-blocks; calibration & conformal on val-period × train-blocks
  (disjoint rows).
* AOI-balanced sample weights (each nation equal total weight).
* Leave-one-country-out; walk-forward expanding-window retraining ("continuous training").
* Metrics: PR-AUC (primary; imbalanced), ROC-AUC, Brier, ECE, precision/recall/F1/false-alarm rate at
  the val-chosen F1 threshold, lead time, conformal coverage/abstention; 95 % CIs by (AOI, block)
  cluster bootstrap.

### 7.1 Over-/under-fitting controls (D-011)
| Risk | Control | Evidence produced |
|---|---|---|
| Spatial autocorrelation inflating scores | 1 km block hold-out; cluster bootstrap | spatial-only vs temporal-only vs joint hold-out table |
| Temporal leakage | causal features (unit-tested), 9-month embargo, climate model fit ≤ train end with cross-fitting | tests; split table |
| Over-fitting trees | early stopping (150 rounds patience, AP only) on a *different place & time*; 7 leaves, min_child_samples 4000, feature fraction 0.4, bagging 0.7, L2 = 50, extra-trees (D-016) | validation curve (num_leaves 3…255), train–val gap per ablation step |
| Memorising time (AOI-level features identify event months) | peer-relative labels (D-014); ablation shows the value of A3 climate separately | E-001 diagnostics |
| Under-fitting | validation curve shows where capacity stops helping; learning curve shows whether more data helps | `fig_validation_curve`, `fig_learning_curve` |
| One landscape dominating | AOI-balanced weights; per-AOI metrics; LOCO | per-AOI table, LOCO table |
| Threshold tuned on test | threshold chosen on calibration rows only | – |
| Mis-calibrated probabilities | isotonic on held-out rows; ECE & reliability diagram | `fig_reliability` |

---

## 8. Chronological log

### 2026-10-19
* Extracted the 15-slide plan. Mapped slides → modules: s3/4 data stack → `s2.py`, `climate.py`,
  `context.py`; s5 features → `features.py`; s6 climate conditioning → `fit_climate_model`;
  s7 resilience → A5; s8 future target → `labels.py`; s9–12 → `train.py`; s14 execution plan → §9.
* Verified anonymous access to Planetary Computer, Open-Meteo archive & flood APIs, CHIRPS server.
* **I-001** duplicate processings in the S2 archive (02.12 + 05.00 of the same datatake). Fixed (D-003).
* **I-002** odc-stac returns time slices in an order that does not match the item list → per-position
  offset mapping was wrong. Fixed by loading offset/non-offset groups separately (D-004).
* **I-003** first full S2 run projected ~14 h: 10+ scenes × 7 bands per month incl. overlapping tiles.
  Profiling: search 3.8 s, COG open 1.5 s, throughput 0.5 MB/s single / 1.3 MB/s aggregate → network-bound.
  Fixed by D-005 (single tile, 4 least-cloudy scenes). All earlier partial months deleted and recomputed
  so every month follows the same rule.
* **I-004** CHIRPS COG reads competing for bandwidth (~2 GB). Switched rainfall to ERA5 (D-007).
* Climate tables built for all 9 AOIs (1991-01 → 2026-09).
* Unit tests: 5/5 pass (causality of all operators, AC1 & slope correctness, gap-fill limits, label logic).
* **I-005 / D-006 COG block alignment.** Sentinel-2 COGs on PC use 512 × 512 internal blocks (10 m bands
  → 5.12 km). An arbitrary 5 km window straddles 2 × 2 blocks, so 4× more bytes are fetched than used.
  Each AOI is now **snapped to the single 512-px block of one MGRS tile that contains the AOI centre**
  (`care_ew/s2.py::grid_info`, cached in `data/processed/<aoi>/grid.json`: tile, EPSG, x0, y0, WGS84 bbox).
  AOIs are therefore 5.12 × 5.12 km and their centres are within ≤ 2.6 km of the nominal centre in §3
  (all nine nominal centres verified to lie inside their grid box). All previously downloaded months were
  discarded and recomputed on the aligned grid so that every month is identical in processing.
  Effect: ~16 s per AOI-month (vs 26 s) and lower bytes; aggregate ~4–7 AOI-months/min on our link.
* **I-006** smoke test of the full feature/label chain on the 28 Nepal months then available ran in 21 s
  for 246 751 pixels, produced 57 features with no infinities. It showed that on short records the
  climate model's leave-one-year-out R² can be ≤ 0 (it then *adds noise* to R).
  **D-012 climate-skill guard:** climate adjustment is applied to an AOI × land-cover class only if its
  leave-one-year-out R² ≥ 0.05; otherwise Ẑ = 0 (R = z). Classes with < 2000 pixels share one pooled AOI
  model. This is the formal implementation of the requirement "use weather data only if strictly
  necessary": weather enters the *label* only where it demonstrably explains vegetation, and enters the
  *model* only through ablation step A3, whose added value is measured on the locked test set.
* **I-007** Open-Meteo Flood API: the nearest GloFAS cell to a river vertex is often a hill-slope cell
  (Nepal outlet: GloFAS 0.8 m³/s vs HydroRIVERS long-term mean 15.9 m³/s). **D-013** snap each station to
  the cell in a 3 × 3 (0.05°) neighbourhood whose 2005–06 mean discharge best matches HydroRIVERS
  `DIS_AV_CMS` (log ratio, small distance penalty). Also hit the API's hourly quota once (HTTP 429) →
  retry/backoff added, query volume reduced.
* **I-008** HydroRIVERS Africa archive arrived truncated (28 of 108 MB, curl exited without error);
  detected with `unzip -t`, re-downloaded. All archives now integrity-checked.
* **I-009** MODIS: items carry `start_datetime` (no `datetime`) → sort fixed; pixel-reliability band is
  int8 with nodata 255 → loaded as float32. MODIS fetch for Nepal: 320 monthly maxima (2000-02 → 2026-09),
  89 % valid.
* UI (built in parallel against a fixed data contract, `docs/UI_DATA_SPEC.md`): CesiumJS globe, Esri World
  Imagery, AOI boxes, labelled hotspot boxes, upstream river network highlighting, before/after chips,
  model card, pixel inspector, GeoJSON/CSV export for field teams. Verified with headless-Chromium
  screenshots (`outputs/screenshots/ui_dev/`, mock data clearly badged "MOCK DATA · not results").
  Pixel lookup in `/api/pixel` changed from linear-bbox to the exact UTM grid transform (grid.json).
* Provenance: `scripts/provenance.py` writes the exact scene IDs (and baseline/offset) behind every
  AOI-month → `data/processed/<aoi>/s2_items.csv` (audit trail for every label).
* Continuous training: `scripts/update_monthly.py` (ingest new month → rebuild → challenger trained on all
  labelled months → promoted only if PR-AUC does not drop > 0.01 and ECE does not rise > 0.01 on the most
  recent 6 labelled months of test blocks → predict → export; history in `update_history.jsonl`).
* **I-010 memory pressure.** With 3 parallel S2 AOI processes + MODIS + hydro + desktop apps, free RAM fell
  below ~1 GB and all background jobs were terminated by the host (progress kept: per-month part files).
  With the user's permission, heavy desktop apps were closed and the Oracle XE services stopped (free RAM
  4.7 → 9.1 GB). Acquisition restarted as one sequential chain (`scripts/fetch_rest.sh`): S2 with 2 AOI
  processes × 4 month-threads, then MODIS, hydrology, Landsat. All steps resume from saved files.

#### E-001 — debug training on the first two complete AOIs (IND, NPL) — label definition v1 rejected
Purpose: exercise the full chain before all data arrive. **Transparency note:** test-set numbers of these
two AOIs were printed during debugging. Design choices below were made on validation numbers (and on
label diagnostics that use no model at all), but a reviewer should know the test rows of IND/NPL were seen.
1. **I-011 early-stopping bug.** LightGBM's early stopping watched the default `binary_logloss` as well as
   AP; with `scale_pos_weight` the weighted log-loss rises from the first tree, so every model stopped at
   1–3 trees (PR-AUC ≈ base rate). Fix: `metric="average_precision"`, `first_metric_only=True`.
   After the fix a Sentinel-only RF already reached ROC-AUC 0.71, i.e. signal existed.
2. **I-012 overfitting via time-identifying features.** Train PR-AUC 0.3–0.8 vs val 0.03; *adding* AOI-level
   climate made test worse. Diagnosis: labels were clustered in time. IND: 57 % of all 2019–25 onsets fell
   in 5 months, all July/August (monsoon sowing; observed-pixel fraction as low as 0.32). AOI-level
   features then identify "event months" — memorisation, not prediction. The v1 label was mostly measuring
   **landscape-wide phenology shifts and cloud-season artefacts**, not local degradation.
3. **D-014 peer-relative (LNS) residual.** Following Local Net Production Scaling (Prince et al. 2009),
   the label residual is now R = (z − Ẑ) − median over all pixels of the same land-cover class in the same
   month (and likewise for the absolute NDVI-drop condition). Anything that hits the whole landscape at
   once (regional drought, late monsoon, haze, composite artefacts) cancels; a pixel must decline
   **relative to its peers**. Also: the first `min_run` months of an event must contain ≥ 75 % *real*
   observations (gap-filled months cannot manufacture events). Unit tests added: a synchronous landscape
   dip yields < 1 % onsets while a pixel dipping more than its peers is still labelled; a run made of
   gap-filled months yields no onset. Effect: top-5-month share of onsets IND 0.57 → 0.33, NPL 0.27 → 0.19.
   **Known cost:** degradation that affects an entire land-cover class of an AOI uniformly cannot be
   detected by construction (standard LNS limitation; Threats §11.9).
4. **D-015 persistence ≥ 6 months.** With LNS and min_run = 4 the onset rate became implausible
   (IND 8.8 %/pixel/yr; cropland 7.6 %) — 4 months below peers in cropland is crop choice / fallow.
   Diagnostic grid (no model involved), onsets per pixel per year 2019–2025:

   | AOI | thr | min_run 4 | 6 | 9 | 12 |
   |---|---|---|---|---|---|
   | IND | −1.0 | 0.088 | **0.014** | 0.0045 | 0.0016 |
   | IND (cropland) | −1.0 | 0.076 | **0.005** | 0.0007 | 0.0002 |
   | IND (tree) | −1.0 | 0.128 | **0.057** | 0.028 | 0.013 |
   | NPL | −1.0 | 0.053 | **0.016** | 0.006 | 0.0025 |
   | NPL | −1.5 | 0.030 | 0.0096 | 0.0036 | 0.0016 |

   min_run = 6 (longer than one cropping season) removes most cropland noise and yields ~1.5 %/pixel/yr in
   these hotspot AOIs. Adopted; sensitivity grid now thr ∈ {−0.75, −1, −1.5} × min_run ∈ {4, 6, 9}.
   Label look-ahead becomes H + min_run − 1 = 11 months → splits re-embargoed: val 2023-03…2023-12,
   test ≥ 2024-12 (last labelable month 2025-10).
5. Result with v2 labels (2 AOIs, default params): PR-AUC rises with each layer — A1 0.028, A2 0.029,
   A3 0.029, A4 0.035, A5 0.040, A6 **0.047** (base rate 0.013; ROC 0.75); best non-learning baseline
   (residual rule) 0.031; Sentinel-only RF 0.047. Climate variables alone (A3) add nothing here.
6. **D-016 regularisation.** Train PR-AUC 0.91 vs val 0.05 (num_leaves 31, min_child 400): each pixel
   contributes ~40 near-duplicate monthly rows, so trees memorise pixels. Compared on **validation** AP:
   base 0.047 · {15 leaves, 2000 min_child, L2 20, ff 0.5} 0.068 · **{7 leaves, 4000 min_child, L2 50,
   ff 0.4, extra-trees} 0.097** · same with lr 0.01 & max_bin 31 0.061. Adopted the third (train AP 0.24 —
   gap shrinks from 0.87 to 0.15). Final capacity is re-checked by the full validation curve.

#### E-002 — three AOIs (IND, NPL, ETH), v2 labels, D-016 params — downstream chain debugging
* Final model on the locked test: PR-AUC 0.065 (base 0.011, lift 5.8), ROC-AUC 0.79, ECE 0.005. Skill grows
  with the number of nations (2 AOIs: 0.047 → 3 AOIs: 0.065) — consistent with the learning-curve hypothesis
  that positives (≈ 0.5 % of rows) are the limiting resource.
* Wall-to-wall inference: 260 k pixels × 45 months in 2.8 min (NPL). Export: 57 s.
* **I-013** first real-data UI review (screenshots `outputs/screenshots/ui_real_debug/`): (a) 25 overlapping
  "active" boxes, most only 1 month below peers — contradicts our own persistence rule → active hotspots
  now require a trailing run ≥ min_run (6) months, per-status caps, labels only for the top 10;
  (b) risk overlay invisible: calibrated probabilities are small (base rate ~1 %) but the legend assumed
  0.15–1 → colour scale now anchored on the operating threshold (0.5·thr … 4·thr) and written into
  `meta.json` so legend and PNG always agree; AOI risk classes re-scaled to probability units
  (Low < 0.005 < Moderate < 0.015 < Elevated < 0.04 < High); (c) warnings = pixels warned in any of the
  last 3 months (a warning covers 6 months; one cloudy month should not erase it).
* **I-014** hydrology outlet picked a large river ~4 km outside the Nepal AOI (0.05° buffer) → outlet is now
  the largest reach *inside* the AOI box (fallback 0.02° buffer). The Nepal AOI is a Chure headwater
  (outlet 1.8 m³/s, 1 upstream reach): its relevant connection is downstream sediment delivery.
* Evidence gallery (fig18) prototype: top correct test warnings show (NPL) river-bank sand deposition /
  channel migration in the Chure — itself a Chure degradation process — and (IND) field-level change,
  illustrating the cropland caveat. Duplicate pixels removed from the gallery.

#### R-001 — data lineage (`data/processed/<aoi>/s2_items.csv`, `scripts/provenance.py`)
| AOI | scenes | months with data / 117 | offset applied | median scene cloud % | tile(s) |
|---|---|---|---|---|---|
| NPL_chure | 376 | 114 | 51 % | 4 | 45RUK (+45RUL fallback) |
| IND_bundelkhand | 393 | 114 | 51 % | 0 | 44RLP |
| ETH_tigray | 450 | 117 | 49 % | 4 | 37PER |
| KEN_baringo | 454 | 117 | 50 % | 11 | 36NZF |
| SEN_ferlo | 436 | 117 | 50 % | 3 | 28PEC |
| ESP_murcia | 436 | 116 | 49 % | 5 | 30SXG |
| BRA_matopiba | 394 | 117 | 51 % | 2 | 23LLG (+23LMG fallback) |
| MNG_steppe | 441 | 117 | 51 % | 4 | 48TXS |
| AUS_murraydarling | 426 | 116 | 51 % | 0 | 55JCF |

3 806 scenes in total. **Half of all scenes required the −1000 BOA offset** — omitting D-004 would have
introduced a ~0.1 reflectance step in half the record (a spurious "change"). In NPL and BRA a few months had
no acquisition on the aligned tile and fell back to the overlapping tile (same grid after reprojection;
logged per month in the manifest). Missing months (≤ 3 per AOI) are monsoon/winter months with no scene
< 70 % cloud.

* **I-016 internet outage (~16:41).** DNS resolution failed; the chain fell through all steps without
  data (MNG 104/117, AUS 95/117 S2 months; MODIS/Landsat/hydro errors). Chain rewritten to retry each step
  (up to 15×, 2–5 min apart) until all outputs exist; restarted, resuming from saved parts.
* **I-017 hung reads.** After the outage, S2 workers sat at 0 % CPU for > 5 min: GDAL's HTTP reads have no
  timeout by default, so a half-open connection blocks forever. Added `GDAL_HTTP_TIMEOUT=60`,
  `GDAL_HTTP_CONNECTTIMEOUT=20` (S2, MODIS, Landsat); hung workers killed; chain retry resumed.
* **I-018** the S2 builder re-assembled and rewrote finished cubes on every retry; on Windows that fails if
  any process has the file open (PermissionError on SEN). Finished cubes (all months present) are now never
  rewritten. MODIS is fetched in a parallel job (latency-bound small reads) while S2 finishes.
* **I-019** after the outage some KEN 2017 scenes returned `Read failed`; the month failed 4× and aborted the
  AOI job, which the chain retried forever. Now: the failing scene (identified from the COG URL in the
  error) is excluded and the month recomposited from the rest; if nothing works the month is left empty.
  All exclusions are written to `data/processed/<aoi>/bad_scenes.txt` (audit trail). Re-test: the problem
  month composited normally (transient failure).
* **I-020** MODIS BRA failed with `WarpOperationError: Chunk and warp failed` (one unreadable composite out
  of ~600). MODIS/Landsat loads now use `fail_on_error=False`: an unreadable composite becomes a gap, like a
  cloudy period, instead of aborting the AOI. MODIS was fetched in up to four parallel streams; the
  machine was dedicated to the run (browsers and chat/office apps closed at the user's request).
* **All acquisition complete 18:38** (S2, MODIS, HydroRIVERS/GloFAS, Landsat for 9 AOIs; one unreadable MODIS
  composite in KEN, 2017-289, became a gap). Nine-AOI dataset: 3 218 615 pixel-month rows.
* **I-021 label rule blind in dormant ecosystems.** Full dataset showed **MNG 0 positives** (0 onsets in
  262 k pixels × 7 yr) and SEN 0.0006. Hypothesis "winter snow gaps" rejected (MNG observed ≥ 0.92 of
  months Mar–Nov). Cause: every month of the 6-month run had to show NDVI loss ≥ 0.05 vs peers; where
  vegetation is dormant > 6 months (steppe, Sahel: NDVI ≈ 0.1–0.2, minimal variance) such a loss is
  physically impossible, so runs could never form — a systematic bias against exactly the drylands
  this system targets. Training that had already started on these labels was **stopped** (no results
  used). **D-017 (label v3):** per-month condition R ≤ −1 and dev ≤ −0.02 (noise floor); magnitude
  requirement moved to the run: mean dev over the first 6 months ≤ −0.05. Test added (3 growing months
  at −0.09 + 3 dormant at −0.03 → event; 6 months at −0.03 → no event). Onsets /pixel/yr (2019–25,
  20 k-pixel samples), v2 → v3: SEN 0.0017 → 0.020, ETH 0.012 → 0.036, MNG 0 → 0.0005, IND 0.014 → 0.020,
  NPL 0.016 → 0.019, KEN 0.065 → 0.071, ESP 0.053 → 0.069, BRA 0.055 → 0.063, AUS 0.039 → 0.050.
  MNG remains near zero: ≥ 88 % homogeneous grass steppe that moves as one under a peer-relative rule
  (limitation §11.9 — whole-landscape degradation is invisible to LNS-type labels).
* **I-015 Kenya AOI on a lake.** Label diagnostics showed only 58 294 valid pixels for KEN: the snapped block
  around (36.05, 0.65) was **77.7 % Lake Baringo** (WorldCover class 80). Site-selection error (centre chosen
  from memory, not checked against a land-cover map). AOI moved to the Marigat / Il Chamus plains
  (35.98, 0.47; tile 36NZF; block bbox 35.971–36.017 E, 0.441–0.487 N), the documented *Prosopis*-invasion
  and rangeland-degradation hotspot of Baringo: tree 24.7 % (largely *Prosopis* thicket), grass 35.5 %,
  shrub 17.3 %, crop 13.5 %, built 5.8 %, water 0.2 %. Old data kept in `data/rejected/KEN_baringo_lake_v1`.
  **Lesson / check added:** every AOI's land-cover composition is now printed at dataset build and
  reported in Table 1 so a reviewer can verify each site is what it claims to be.
* Label diagnostics, v2 labels (before MODIS features; 2019–2025):

  | AOI | positive rate (eligible pixel-months) | onsets /pixel/yr | top-5-month share | obs. fraction | climate model used for |
  |---|---|---|---|---|---|
  | BRA_matopiba | 0.0266 | 0.055 | 0.40 | 0.94 | none (LOYO R² < 0) |
  | ESP_murcia | 0.0235 | 0.053 | 0.23 | 0.98 | grass, crop, bare (R² 0.32–0.54) |
  | IND_bundelkhand | 0.0069 | 0.016 | 0.28 | 0.91 | tree, grass, crop (0.06–0.25) |
  | KEN (lake v1, rejected) | 0.0062 | 0.018 | 0.34 | 0.98 | tree, shrub, grass |
  | NPL_chure | 0.0061 | 0.015 | 0.27 | 0.83 | pooled small, bare |
  | ETH_tigray | 0.0048 | 0.011 | 0.37 | 0.99 | none |
  | SEN_ferlo | 0.0006 | 0.0016 | 0.60 | 1.00 | pooled, grass |

  Interpretation: Brazil (Cerrado conversion) and Spain (irrigation expansion / dryland abandonment) carry
  most events; the Sahel site has almost none under a peer-relative rule (rangeland responds to rain as a
  whole) — a hard-negative region; its remaining events are temporally concentrated (0.60).

---

### 2026-10-19 (evening) — status at end of day
* Full nine-AOI run E-003 complete (§10). 8/8 unit tests pass. 18 figures reviewed visually and fixed
  (risk-map "below peers" now a neutral wash, corroboration labels, LOCO "no events" note, method example
  on Spain where the climate model is used, walk-forward axis). UI exported from real data; final
  screenshots in `outputs/screenshots/ui_final/`; model card shows headline metrics, baselines, ablation,
  LOCO, independent-sensor check and walk-forward tables. Paper draft v0.3 written from these results.
* **Recommended next steps (in priority order):**
  1. Field or very-high-resolution validation of a stratified sample of warnings and non-warnings
     (the decisive missing evidence for agency use).
  2. More AOIs per nation (≥ 5) — the learning curve is still rising; also makes LOCO a within-nation test.
  3. Cropland: add crop-calendar / multi-season features or exclude cropland from "degradation" warnings.
  4. Add an absolute (non-peer-relative) companion indicator so whole-landscape degradation (MNG-type) is
     visible; re-examine SEN labels (Landsat AUC 0.46) before trusting SEN warnings.
  5. Extend the test period as months accrue (`scripts/update_monthly.py`); re-verify novelty in a
     final literature search before submission.

### 2026-10-20 — E-004 temperature / heat-stress experiment (pre-registered before results)
* Motivation (user question): temperature entered v1 only as the monthly 2 m air-temperature anomaly T1
  (ERA5-Land); as a direct feature it ranked 50/64 by |SHAP| (0.001). Monthly means at ~9 km are too blunt:
  vegetation damage is driven by heat *extremes* and atmospheric dryness, and a single AOI-level value
  cannot separate neighbouring pixels.
* **D-018 new feature group A7_heat** (added after A6 so A1–A6 stay identical):
  - `lst_z`, `lst_z3` — MODIS Terra MOD11A2 v061 daytime land-surface temperature, 8-day 1 km, QC good/other,
    monthly mean, z vs 2001–2020 same-month climatology per 1 km cell, 1-month lag (composites can extend into
    the next month). Rationale: water-stressed / thinning vegetation transpires less and heats up before it
    browns; LST varies within the AOI.
  - `dT_z`, `dT_z3` — (LST − ERA5-Land mean air temperature) anomaly: canopy cooling deficit.
  - `heat_HD1`, `heat_HD3` — days with ERA5-Land Tmax > the 1991–2020 90th percentile of that calendar month.
  - `heat_TMAX1` — monthly mean Tmax anomaly; `heat_VPD1`, `heat_VPD3` — z-anomaly of daily-max vapour-pressure
    deficit (atmospheric drought).
* **Pre-registered decision rule:** A7 replaces A6 as the operational model only if its **validation** AP
  exceeds A6's by ≥ 0.005; locked-test results are reported whatever the outcome. The climate-expectation
  model (labels) is NOT changed, so labels stay identical and the comparison isolates the features.
* **I-022 MODIS LST QC bug.** First fetch gave only 20–46 % valid months and implausibly cool Sahel daytime
  LST (~30 °C). Cause: `QC_Day` value 0 = *good quality*, but the asset declares nodata = 0, so odc-stac
  masked it to NaN; `fillna(255)` then rejected every best-quality pixel, keeping only "other quality"
  (often cloud-edge, cooler) pixels. Fix: missing QC treated as 0; validity enforced by LST > 0. Re-test SEN:
  98 % valid, monthly means 33.5–42.8 °C with an April–May maximum and a July–August rainy-season minimum
  (physically plausible). All LST files discarded and re-fetched. Lesson: always sanity-check value ranges
  and seasonal cycles of a new data source before using it.
* Ground-reference searches (3 agents, 2026-10-19): see §12.
* **R-013 E-004 result — heat features rejected.** (LST re-fetched with fixed QC; memory-light rebuild with one
  process per AOI after a host memory kill, I-023.) A1–A6 reproduced to the last digit (pipeline deterministic).
  | model | val AP | test PR-AUC | test ROC |
  |---|---|---|---|
  | A6 (operational) | 0.150 | 0.118 | 0.762 |
  | A7 = A6 + heat | 0.139 | 0.109 | 0.752 |
  Pre-registered rule → **A7 rejected**; operational model unchanged (final metrics identical to E-003).
  Diagnostic — univariate AUC on validation rows, pooled vs mean within-AOI: lst_z 0.504/0.511, lst_z3
  0.502/0.520, dT_z 0.458/0.500, HD3 0.582/0.472, TMAX1 0.572/0.481, VPD3 0.565/0.494, (old) T1 0.579/0.488;
  for comparison R_mean6 0.244/0.234 (i.e. 0.76 inverted) and ac1_24 0.646/0.631. Heat variables carry only
  *between-site / between-year* contrast and **no within-site signal**: heat stress is landscape-wide (ERA5
  ≈ 9 km, LST 1 km vs 10 m pixels) and the peer-relative label cancels landscape-wide stress by design.
  Temperature therefore acts through the climate-expectation model (where skilful) and the peer comparison,
  not as a pixel-level predictor. Supports the "weather only if strictly necessary" principle with evidence.
  Possible future test: 70–100 m thermal (Landsat TIRS / ECOSTRESS) could carry within-site signal.

### 2026-10-20 — E-005 expansion sites + on-demand detection
* **User feedback:** one site per nation (forced by bandwidth) under-represents Nepal and India. Eight sites
  added after a cheap land-cover screen (`scripts/screen_sites.py`, `data/candidates/screen.json`; all ≥ 74 %
  usable land): NPL_chure_dang (tree 96 %), NPL_chure_sarlahi (tree 63/crop 33), NPL_kavre (tree 56/crop 23/
  grass 19), NPL_surkhet (tree 90), IND_banni (Prosopis grassland; crop/grass 68, shrub 27), IND_jharia
  (coal mining; 25 % built masked), IND_chambal (gully ravines; crop 92), IND_thar (desert margin; crop 85).
  Rejected: NPL_mustang (97 % bare, 3 700 m: no vegetation signal), IND_marathwada (redundant with
  Bundelkhand). Acquisition: `scripts/fetch_new.sh` (S2, MODIS, LST, Landsat, rivers).
* **On-demand detection ("Draw box", user request).** `care_ew/ondemand.py` + FastAPI `/api/plan`,
  `/api/analyze`, `/api/jobs[/id]`. Any box ≤ ~10 × 10 km is snapped to 1–4 Sentinel-2 512-px blocks; each
  becomes a user AOI (registered in `data/user_aois.json`, added to AOI_BY_KEY but **never to AOIS**, so user
  areas cannot leak into training or validation), runs static → climate → S2 → MODIS → rivers → features →
  **trained model** (no retraining) → export, with progress in `data/jobs/<id>.json`. Steps whose outputs
  exist are skipped (resumable). Results carry the warning "model applied outside its training areas".
  **Self-test:** a box inside the NPL_chure block, pre-seeded with that block's downloads, ran end-to-end in
  10 min and reproduced the study-site predictions exactly (max |Δrisk| = 0.0 over 45 months × 260 614 px;
  status identical) — the on-demand path is the same pipeline. Test artefacts removed afterwards.
  Expected run time for a new area on this link ≈ 45 min per block (S2 history 2017–now is required for the
  2017–2020 baseline).
* **I-024 app stuck on 'Loading globe…'** while the S2 download saturated the link: Cesium.js (4 MB) alone took
  16 s from the CDN plus ~40 worker/asset files. Fix: Cesium 1.121.0 and Chart.js 4.4.1 vendored into
  `app/static/vendor/` (same pinned versions; 20 MB); startup 1.7 s, zero CDN requests. Only Esri base-map
  tiles still need the internet. Also better for agencies on poor connections.
* **D-019 real loading progress (user request: "so every user is sure it is not stuck").** No fake spinners:
  (1) an inline bootstrap renders the page and a progress card first, then streams the libraries with
  byte counts ("Globe engine 1.8 MB / 4.8 MB"); fonts no longer block first paint; (2) `app/static/js/progress.js`
  counts every data request (files in flight/done, bytes received/expected, streamed) and Cesium globe tiles
  (exact done/total per burst) and drives a top progress bar + status chip whenever anything loads;
  (3) a startup checklist (engine → area list → globe → base-map tiles) completes on real events instead of a
  blind 12 s timeout; (4) a stall watchdog shows "waiting for network – last data N s ago" after 15 s without
  data. Verified headless: normal 1.8 s; throttled 150 kB/s + 400 ms latency: progress 4 % → 19 % → 40 % at
  3/15/30 s, ready at 42 s, no errors (`outputs/screenshots/ui_progress/`).
* **I-025 'main.js failed to load' in the user's browser** (not reproducible in a clean headless browser): the
  server log showed main.js/progress.js fetched fresh while the other app modules came from the browser cache -
  stale cached modules mixed with updated ones. FastAPI static files carried no Cache-Control, so browsers used
  heuristic caching. Fix: middleware sets `Cache-Control: no-cache` on app code/styles/data (always revalidate;
  unchanged files return 304); vendor libraries keep normal caching. The loader now retries once with a
  cache-busting URL and shows the captured error text instead of a generic message. Verified: two consecutive
  loads in one browser context start cleanly (1.6 s / 2.3 s). Existing browsers need one Ctrl+F5.
* **I-026 real root cause of 'Could not start the app' (inspected in the user's own Chrome).** Dynamic-import
  probes showed every module loading except `js/analyse.js`; a direct `fetch('/js/analyse.js')` failed inside a
  Chrome extension's request interceptor (`chrome-extension://eppiocemhmnlbhjplcgkofciiegomcon/libs/requests.js`)
  while all other files returned 200. Privacy/ad-block filter rules block script URLs named like `analyse.js`
  (tracking scripts). Clean headless browsers have no extensions, so tests passed. Fix: renamed
  `analyse.js`→`area-tool.js`, `analyse.css`→`area-tool.css`. Verified in the user's Chrome: app starts,
  9 areas, Draw box present. Rule for the project: never name front-end files analytics/analyse/track/ads/
  beacon/pixel. (The I-025 cache policy remains a valid hardening, but was not the cause.)
* Neural-network challenger and "Under the hood" view deferred at the user's request (PyTorch in this
  environment is CPU-only; a CUDA build is ~2.5 GB to download).


### 2026-10-21 — E-006 expert review: ecosystem structure & function (pre-registered before results)
* **External review** (senior forest official, comment received via the user): *degradation is tied to ecosystem
  structure and function; a structural change (e.g. river-course change) that reduces a function (e.g. water
  availability) reduces productivity, so models must relate to productivity loss.* Suggested evidence:
  (1) vegetation type/structure (drought-hardy, invasive, thorny, fire-resistant, cactus); (2) loss of perennial
  streams, ponds, water recession, wetland loss, rice→maize; (3) livestock / water-dependent species change;
  (4) temperature imagery; (5) GLOF / glacier shift for mountains.
* **Consequence for the river question (I-028).** The river diagnostic (`scripts/river_diagnostic.py`,
  `outputs/results/river_diagnostic.json`) showed onsets concentrated in water corridors at NPL_chure (rate
  ratio 1.71; 82 % of onsets), IND_chambal (1.82), IND_jharia (2.64), NPL_chure_dang/kavre (1.44/1.43), and
  more onsets after wet 3-month spells at ETH, SEN, AUS, IND_thar, IND_jharia. Following the expert framing,
  river-course change that lowers productivity **is** degradation and stays in the label; it is no longer silent:
  every hotspot now carries a **process attribution** (water loss, river dynamics, paddy/wetland loss, evergreen
  encroachment, perennial-cover loss, structure shift, failed green-up after a wet spell = rain-use-efficiency
  loss, post-drought decline). The earlier proposal to exclude river events (label v4) is withdrawn.
* **D-020 feature group A8_ecofunc** (`care_ew/ecofunc.py`, causal, unit-tested): water_frac12, water_loss12,
  nbw_frac12, nbw_loss12 (210 m), paddy_frac12, paddy_change, p10_12, p90_12, evergreen_shift, amp_change,
  peak_shift, tex12, tex_change — all derived from stored S2 monthly indices (B11 reconstructed from NDVI, NDMI
  and red; MNDWI water flag; Xiao et al. paddy flooding rule). Sanity check NPL_chure: water 0.5 % of
  pixel-months, paddy ≈ 0, shifts in plausible ranges.
* **Pre-registered rule:** A8 (= A6 + ecosystem function) replaces A6 operationally only if validation AP ≥ A6
  + 0.005; locked-test results reported regardless. Run together with the 17-site expansion (E-005), so the
  baseline for comparison is A6 on 17 sites (same run), not the 9-site model.
* Mapped but not yet implemented: (3) livestock / species — no pixel-level open data; FAO GLW (10 km, 2015) and
  GBIF are context only; district livestock census series requested from the user. (4) Landsat 30 m surface
  temperature (MODIS 1 km gave no within-site signal, E-004). (5) glacier / glacial-lake change for mountain
  boxes (none of the 17 sites is glacial). (1, partly) MODIS burned area for fire regime.


### 2026-10-21 — E-007 nonlinear dynamics & critical-transition theory (pre-registered before results)
* User request: more mathematical rigour / nonlinear science. Rationale: degrading land systems can have
  alternative stable states and thresholds (Scheffer et al. 2009; Kéfi et al. 2007; Rietkerk et al. 2004); AC1
  and variance (A5) are only the linear edge of critical-slowing-down theory.
* **D-021 feature group A9_nonlinear** (`care_ew/nonlinear.py`, equations in the module docstring):
  (1) rolling skewness/kurtosis and spectral reddening of the detrended residual; (2) exponentially-weighted
  recursive AR(1) (Kalman-type random-walk coefficient) and return rate λ = −ln|φ| plus its 12-month change;
  (3) Langevin / Kramers–Moyal cubic-drift fit Δx = a₁x + a₃x³ + ε → potential curvature κ, bistability flag
  (a₁ > 0, a₃ < 0), noise-to-restoring ratio; (4) DFA-1 exponent α; (5) Bandt–Pompe permutation entropy;
  (6) rolling rain elasticity, coupling R² and its change (rain-use efficiency); (7) spatial EWS (210 m spatial
  skewness, Moran-type autocorrelation) and Kéfi patch statistics per 1 km block (vegetated fraction,
  largest-patch fraction, CCDF power-law exponent).
* **Mathematical validation** (`tests/test_nonlinear.py`, 9 tests, all pass): moments equal SciPy; EW-AR(1)
  recovers φ = 0.2/0.8 and λ falls as φ → 1; Langevin flags a simulated double-well (dx = (x − x³)dt + σdW)
  as bistable and a single well (dx = −x dt + σdW) as not; DFA α ≈ 0.5 for white noise, > 1.2 for a random
  walk; permutation entropy ≈ 1 for noise and 0 for a monotone series; rain elasticity recovers b = 2.0;
  patch statistics detect fragmentation; every temporal indicator is causal (future perturbation leaves
  values ≤ t unchanged); vectorised quantile equals np.nanpercentile to 1e-12.
* **I-029** first sanity check showed vegetated fraction ≡ 0.500: the vegetation threshold was the block's
  own monthly median (tautological). Fixed: one threshold per AOI = 2017–2020 median NDVI (KEN: 0.29–0.58
  across years, 0.01–0.56 across space).
* **I-030 speed:** np.nanpercentile on gappy data fell back to a per-pixel Python loop (95 % of feature time);
  replaced by a vectorised sort-and-interpolate quantile (identical results) and map-mode computation limited
  to needed groups/months: 75 s → 4.4 s per 4 881 pixels; wall-to-wall maps ≈ 3.7 min per AOI.
* **Pre-registered rule:** among the cumulative steps A6 (current), A8 (+ ecosystem function) and A9
  (+ nonlinear dynamics), the operational model is the one with the highest **validation** AP, adopted only if it
  beats A6 by ≥ 0.005. Locked-test results reported regardless. 17 sites, same splits as E-005.

* **I-031 / D-022 memory.** The combined run was killed twice by the host memory guard (free RAM fell to
  3 GB). With the user's permission non-essential apps were closed and Oracle services stopped again (free
  11.1 GB). Changes that do not touch evaluation: (a) inside the TRAINING period only, negatives are
  down-sampled to 50 % deterministically (hash of pixel and month) and re-weighted ×2 within the AOI-balanced
  weights — validation, calibration and test rows are all kept; (b) A8 grid layers stored as float16;
  (c) training split into pieces run as separate processes that append to `metrics.json`;
  (d) `scripts/slow_run.sh`: resumable driver (marker per piece, one retry, waits for ≥ 5 GB free RAM before
  each piece). Caveat for comparisons: the E-005 17-site no-A8/A9 run (`metrics_E005_17sites_noA8.json`) used
  all training negatives; the A6 row of the new ablation (same down-sampling) is the like-for-like reference.
* All 17 datasets with A8 + A9 were built 02:17–02:39 (after the I-029/I-030 fixes); 110–114 columns.


#### R-014 — E-006/E-007 results (17 sites, A8 + A9; slow run 03:29–04:48, 2026-10-21)
Training rows 4 294 330 (training-period negatives at 50 %, weight ×2); locked test 132 230 rows, base 0.0252.
| model | test PR-AUC | lift | ROC | **val AP** |
|---|---|---|---|---|
| A4 + residual | 0.131 | 5.2 | 0.783 | 0.140 |
| A5 + resilience | 0.143 | 5.7 | 0.797 | 0.128 |
| **A6 + spatial (operational)** | **0.152** | 6.0 | 0.805 | **0.1384** |
| A8 = A6 + ecosystem function | 0.139 | 5.5 | 0.801 | 0.1318 |
| A9 = A8 + nonlinear dynamics | 0.147 | 5.8 | 0.808 | 0.1385 |
**Pre-registered rule → A8 and A9 rejected** (val gain −0.0066 and +0.0001 < 0.005). Operational model stays A6.
Final calibrated A6 (17 sites): PR-AUC 0.144 (CI 0.112–0.184), lift 5.7, ROC 0.805 (0.766–0.838), ECE 0.0025,
precision 0.217, recall 0.289, false-alarm rate 2.7 %; 41 % of 1 444 test onsets warned ≥ 1 month ahead (median
lead 3 months; was 31 % / 2 months with 9 sites); conformal abstain 52 %, coverage 0.94/0.875, NPV 0.996;
non-abstained ROC 0.877. Per site: Nepal Kavre ROC 0.915 (×9.2), Sarlahi 0.853, Chure 0.827, Chure-Dang 0.819,
Surkhet 0.667; India Chambal ×19.5 (ROC 0.873), Bundelkhand 0.757, Thar 0.764, Banni 0.692, Jharia 0.770
(base 0.2 %). LOCO: Nepal 0.104 (×6.2, ROC 0.771; 9-site model ×3.5), India 0.122 (×4.1), Australia ×13.8,
Ethiopia ×10.2, Senegal ×9.8, Kenya ×7.0, Spain ×4.6, Brazil ×2.3. Walk-forward PR-AUC 2021→2025: 0.034, 0.028,
0.072, 0.140, 0.179. Label sensitivity: lift 2.9–6.6, ROC 0.74–0.82 across 9 definitions. Learning curve still
rising (test 0.068 at 5 % → 0.152 at 100 %).
**Why A8/A9 did not help — within-site univariate AUC on validation rows (0.5 = none):** the EW-AR(1) and
Langevin noise ratio (0.616) carry the SAME information as the existing AC1/variance (0.609/0.615); return
rate λ 0.386 (i.e. 0.614 inverted) ditto — nonlinear estimators corroborate critical slowing down but are
redundant with A5. Dry-season greenness loss is individually strong (evergreen_shift 0.285 → 0.715 inverted)
but redundant with the residual (R_mean6 0.245). Higher moments, DFA, permutation entropy, Langevin curvature
are weak (|AUC−0.5| ≤ 0.06); spatial EWS, patch-size statistics, paddy and water features ≈ 0.5 at this scale.
Interpretation for the paper: at 10 m / monthly resolution, the predictive information about future onsets is
captured by the climate-conditioned residual and linear critical-slowing-down indicators; more sophisticated
nonlinear estimators agree with them (a consistency check of the theory) but add no independent skill. The
binding constraint is data volume / label quality (learning curve), not model or feature sophistication.
A8 remains in use for **process attribution** of hotspots (explanation), not prediction.


#### R-015 — Leave-one-site-out transfer by landscape type (user question: does the model work in new places of a KNOWN landscape type?)
`care_ew/train.py::loso` — train on 16 sites (training period, train blocks), test on the held-out site (test
period, all blocks); landscape groups assigned by hand (`LANDSCAPE` dict). ROC on the never-seen site
(in-domain ROC in brackets):
* Himalayan foothill forest — Kavre 0.874 (0.915), Sarlahi 0.823 (0.853), Chure-Dang 0.806 (0.819), Chure
  0.804 (0.827), Surkhet 0.766 (0.667); lift ×6.7–11.2.
* Semi-arid Indian cropland — Chambal 0.788 (0.873, ×15.6), Thar 0.757 (×4.7), Bundelkhand 0.726 (×5.7).
* Arid grassland/rangeland — Senegal 0.865, Kenya 0.835, Banni 0.678.
* No same-type site in training — Australia 0.922, Ethiopia 0.882, Spain 0.754, Jharia (mining) 0.693,
  Brazil 0.642. Mongolia: no test events.
* Median ROC / lift: **with a same-type sibling 0.804 / ×8.2 (n = 11)**, without 0.754 / ×4.6 (n = 5); the
  corresponding in-domain medians are 0.827 and 0.791, so part of the gap is intrinsic difficulty, not only
  transfer. Conclusion: new places of a represented landscape type are predicted almost as well as training
  sites (ΔROC ≈ 0.02); unrepresented types are weaker and less predictable. Caveats: small n, hand-assigned
  groups. Operational guidance: trust maps most in Himalayan foothill forest, semi-arid Indian cropland /
  ravines and arid rangeland; treat humid tropical forest, cold high mountains and industrial agriculture as
  indicative only.
* Also completed: user area "hilly test" (USR_hilly_test_861e, ~87.87 E 26.95 N), interrupted at the
  features stage on 2026-10-20 01:48 and resumed (cached S2 reused, 14 min): mean risk 0.042 (High),
  122 ha above threshold, 807 ha in active decline, 12 hotspots in forest, mostly attributed "post-drought".

#### D-023 — Pre-registration (2026-10-21): texture (A10a) and red-edge (A10b) feature tests (user question:
"have we considered pixelation or texture ... shrub species and if it has dried out")
* Motivation. A8 texture was only a 3×3 NDVI standard deviation. Shrub die-back / drying is seen only through
  NDMI and greenness; Sentinel-2 red-edge bands (B05–B07), which track chlorophyll loss before NDVI falls, were
  never downloaded (S2_BANDS = B02, B03, B04, B08, B11, B12). Species identification is NOT attempted (10–20 m
  pixels mix shrubs and soil; needs VHR/hyperspectral + field plots) — documented as out of scope.
* A10a texture (`care_ew/texture.py`, no new download): per month on the 10 m causal NDVI grid, 8-level
  equal-probability quantisation (AOI 2017–2020 quantiles), symmetric GLCM over offsets (0,1),(1,0) in a 7×7 px
  (70 m) window → Haralick contrast, homogeneity, entropy, correlation; multi-scale local SD of NDVI at 3, 9 and
  27 px and the log scale ratio ln(SD27/SD3); 5×5 local SD of NDMI and BSI. Each layer → 12-month causal mean
  (`*12`) and change vs its 2017–2020 mean (`*_chg`, same documented baseline as A8). Stored in
  `texture.parquet` beside `table.parquet` (joined on pix, time) so the base table is untouched.
* A10b red-edge (`care_ew/rededge.py`): B04, B05, B06, B07, B8A, SCL at native 20 m from the SAME scene
  selection rule as the base composite; monthly medians of NDRE = (B8A−B05)/(B8A+B05), CIre = B07/B05 − 1,
  IRECI = (B07−B04)/(B05/B06). Features: value, 3-month change, 12-month mean, anomaly vs 2017–2020 same-month mean.
* Comparison: A6 (operational) vs A6 + A10a, A6 + A10b, A6 + A10a + A10b, same splits / weights / LightGBM
  parameters. **Decision rule (fixed now): a variant replaces A6 only if its VALIDATION AP ≥ A6 + 0.005; the
  test set is reported regardless and is not used to choose.** If rejected, the features may still be used
  for hotspot attribution (as A8).

#### R-016 — A10a texture test (D-023), run 2026-10-27
All 17 sites (texture.parquet, ~4–5 min/site). Same rows, splits and parameters as A6:
| variant | features | val AP | test PR-AUC | test ROC |
|---|---|---|---|---|
| A6 (operational) | 64 | 0.1384 | 0.1522 | 0.805 |
| A6 + A10a texture | 82 | 0.1341 | 0.1535 | 0.811 |
**Rejected** by the pre-registered rule (val −0.004 < +0.005); the small test gain is not used to choose.
Texture is informative on its own — within-site univariate validation AUC: local NDVI SD 3×3 0.616, SD 27×27
0.599, NDMI SD 0.592, GLCM contrast 0.591, BSI SD 0.588, entropy 0.576, homogeneity 0.428 (inverted) — i.e.
heterogeneous / patchy pixels are more likely to degrade, and the texture features take 21 % of the model's gain
when offered — but this information overlaps the resilience (variance) and neighbourhood features already in A6.
Answer to the user question: pixel texture has been tested at three scales and with GLCM; it corroborates
but does not add independent predictive skill at 10 m.

#### R-017 — Red-edge (A10b), texture+red-edge, and doubled training pixels (D-023, D-024), run 2026-10-27
Red-edge composites for all 17 sites (scene counts identical to the base composite in every month).
| variant (5 000 px/site table) | features | val AP | test PR-AUC (95 % CI) | test ROC |
|---|---|---|---|---|
| A6 (operational) | 64 | 0.1384 | 0.152 (0.119–0.192) | 0.805 |
| A6 + texture | 82 | 0.1341 | 0.154 (0.121–0.202) | 0.811 |
| A6 + red-edge | 76 | 0.1370 | 0.146 (0.119–0.181) | 0.789 |
| A6 + texture + red-edge | 94 | 0.1438 | 0.151 (0.117–0.193) | 0.792 |
* The combined variant passed the literal rule by 0.0004 (0.1438 ≥ 0.1434). Because the margin was tiny, the
  best of three variants was selected on validation, and the test set did not confirm (ROC −0.013), a seed
  stability check was run — **added after the test numbers were seen (deviation from D-023, declared here)**,
  using VALIDATION only: 5 LightGBM seeds each. A6 val AP 0.1397 ± 0.0059, A6+A10a+A10b 0.1427 ± 0.0063; mean gain
  +0.0031 (< 0.005), per-seed paired gains −0.007, −0.003, +0.013, +0.016, −0.003. **Decision: the pass is within seed
  noise; A6 stays operational.** A reviewer may prefer the literal rule; both numbers are reported.
* Red-edge individually: within-site validation AUC 0.43 (NDRE anomaly, inverted = 0.57), 0.44 (CIre anomaly);
  i.e. chlorophyll loss relative to the 2017–2020 same-month mean is associated with later onsets, but less
  strongly than the NDVI-based residual (R_mean6 0.755 inverted). At 20 m and monthly medians, red-edge adds
  little beyond NDVI/NDMI for shrub drying; it cannot separate drought-deciduous dormancy from mortality.
* D-024 doubled training pixels (5 000 → 10 000 per site; original pixels kept, identical rows verified): on the
  common 10 000-pixel validation/test rows val AP 0.1220 (5 000) vs 0.1196 (10 000); test 0.165 vs 0.171.
  **Rejected.** Note the same 5 000-px model scores 0.152 on the original test rows and 0.165 on the doubled
  set — test-set sampling noise is ≈ ±0.01, so the "still-rising" learning curve (R-0xx) is within noise.
  Conclusion: more pixels from the SAME 17 sites do not help; new sites/landscapes (R-015) do.

#### D-025 — Pre-registration (2026-10-27): six new sites (E-008), user request "do that and raise accuracy"
R-016/R-017 showed that more features or more pixels from the same sites do not help, while R-015 showed that a
same-landscape sibling in training raises transfer (median ROC 0.754 → 0.804). New sites, chosen BEFORE any
result and screened for land cover (data/candidates/screen_v2.json): NPL_chure_udayapur, NPL_chure_kailali,
NPL_sindhupalchok, IND_shivalik (Himalayan foothill forest), IND_marathwada (semi-arid Indian cropland),
IND_singrauli (mining; sibling for Jharia). Same pipeline, label rule, splits and LightGBM parameters.
* Primary comparison (`python -m care_ew.train sites`): A6 trained on the 17 original sites vs on all 23,
  scored on the SAME validation rows of the 17 original sites. **Adopt the 23-site model only if its validation
  AP ≥ the 17-site model's + 0.005.** Test metrics on the 17 original sites and on the 6 new sites are reported
  regardless. Secondary (reported, not used to choose): leave-one-site-out ROC for Jharia with/without
  Singrauli and for the Nepal sites.

#### D-026 — Pre-registration (2026-10-27): training-label cleaning by confident learning ("better labels")
Satellite labels are noisy (residual cloud in monthly medians, gap-filled months, phenology shifts). Confident
learning (Northcutt, Jiang & Chuang 2021, JAIR 70): out-of-fold A6 probabilities p for every TRAINING row (5 folds
grouped by site × 1 km block, so a pixel never scores itself); per-class thresholds t1 = mean p of labelled
positives, t0 = mean p of labelled negatives; a labelled-1 row with p ≤ t0 or a labelled-0 row with p ≥ t1 is a
suspected label error and is removed from TRAINING only. Validation, calibration and test labels are untouched,
so the comparison measures whether cleaner training labels predict the unchanged reference labels better.
**Rule (fixed now, after the R-017 seed lesson): 5 LightGBM seeds each; adopt only if the mean validation AP gain
≥ 0.005.** Test reported regardless. If E-008 sites are adopted first, the test is repeated on 23 sites.

#### R-018 — Confident-learning label cleaning (D-026), run 2026-10-27 (17 sites, 16 min)
Flagged as suspected label errors: 2 588 of 16 987 training positives (15.2 %) and 22 103 of 783 797 negatives
(2.8 %). Five seeds each: validation AP original 0.1397 ± 0.0059, cleaned 0.1392 ± 0.0026 (gain −0.0005);
test 0.1484 vs 0.1504. **Rejected.** Side observation: cleaned labels halve the seed-to-seed spread, i.e. the
suspected errors are what makes single models unstable — but removing them does not raise skill on the
unchanged reference labels.

#### D-027 — Pre-registration (2026-10-27): 5-seed prediction ensemble
Average the predictions of 5 A6 models that differ only in seed (bagging / feature sampling / extra-trees draws).
Comparison on the same validation rows, AP of the averaged score vs the mean AP of the 5 single models.
**Adopt only if the gain ≥ 0.005.** Test reported regardless.

#### R-019 — 5-seed prediction ensemble (D-027), run 2026-10-27
Validation AP: single models 0.1407 (mean of 5), ensemble 0.1448 → gain +0.0041 < 0.005. **Rejected by the
pre-registered rule.** Test (reported only): single 0.1484, ensemble 0.1561. The ensemble is the closest of all
attempts (R-016 … R-019); a future pre-registered test on the 23-site data may revisit it, but it is not adopted now.

#### R-020 — Six new sites (E-008 / D-025), run 2026-10-27 18:05–18:16
**Independent transfer test (the strongest accuracy evidence so far):** the operational 17-site model, which
never saw these places, on their test period (all blocks): ROC-AUC Sindhupalchok 0.873 (×9.8), Singrauli 0.876
(×6.8), Chure-Udayapur 0.844 (×7.0), Chure-Kailali 0.803 (×10.1), Shivalik 0.782 (×12.7), Marathwada 0.597
(×1.7); **all six together ROC 0.839, lift ×8.6, PR-AUC 0.217** — better than the original test set (0.805, ×5.7).
Intensive cropland (Marathwada) remains the weak case, consistent with the land-cover results.
**Pre-registered comparison (single seed):** val AP on the original 17 sites' rows 0.1384 (17 sites) vs 0.1332
(23 sites) → **rejected**. Test (reported only): original-17 PR-AUC 0.152 → 0.166 (CI 0.119–0.192 → 0.129–0.217),
ROC 0.805 → 0.801; new-6 PR-AUC 0.217 → 0.258.
Sibling leave-one-site-out (held-out site test PR-AUC / ROC, without → with the new sibling): Chure 0.120/0.814 →
0.147/0.814; Kavre 0.320/0.886 → 0.271/0.876; Surkhet 0.101/0.785 → 0.102/0.796; Bundelkhand 0.093/0.725 →
0.075/0.736; Jharia 0.034/0.699 → 0.033/0.686. Mixed: siblings do not reliably help at n = 1 sibling.
**Declared check:** D-025 used one seed although seed noise (≈ 0.006, R-017) exceeds the 0.005 margin; the 5-seed
protocol used since D-026 is applied symmetrically (`python -m care_ew.train sites5`). Until a test adopts them,
E-008 sites are excluded from training by default (`TRAIN_EXCLUDE_DEFAULT`) and serve as independent test sites.

#### R-020b — 5-seed check of D-025 and a weakness of the selection protocol
Five seeds each (validation = original-17 val rows): 17 sites 0.1397 ± 0.0059, 23 sites 0.1388 ± 0.0092 → gain
−0.0008. **Rejected; the operational model stays the 17-site A6.** Reported only: test original-17 AP 0.148 → 0.167
(+0.019, all five seeds), new-6 test AP 0.210 → 0.254 (+0.044).
**Observation (threat to validity, added to §11):** across R-016 … R-020 the test set moved in favour of several
rejected changes (ensemble +0.008, 23 sites +0.019) while validation did not. The validation window is a single
10-month period (2023-03 … 2023-12) and therefore a noisy, single-year selector; its seed noise (± 0.006) is as
large as the decision margin. Changing the selection rule now, after seeing which way the test moved, would be a
forking path, so no decision is reversed. **Plan (D-028, to be pre-registered before the data exist):** a
*prospective* test — as months after 2025-10 receive labels (each month needs 11 months of look-ahead), compare
the 17-site A6, the 23-site A6 and the 5-seed ensemble on those genuinely future months; adopt whichever wins by
≥ 0.005 AP averaged over 5 seeds.

## 12. Ground-reference inventory (2026-10-19; three search agents; all endpoints actually queried)
Files: `data/ground_ref/` — `photo_sources_inventory.json`, `field_sources_inventory.json`,
`vhr_sources_inventory.json`, per-source subfolders, `inventory_queries.py` (re-runnable).

**Ground-level labelled photos.** Only EU LUCAS (ESP: 2–4 points inside the AOI, 37–79 within 10 km per survey
year 2006–2022, 5 photos per point, land cover/use; 2022 gully observations at 3 nearby points). GLOBE Observer:
nothing within 10 km of any AOI (nearest 51 km, KEN). iNaturalist/GBIF: thousands of photos near KEN/ESP but
species labels only. Wikimedia/KartaView/Panoramax/Degree Confluence: unlabelled, roadside. Mapillary/Flickr
need credentials (not checked).

**Field plots / expert maps.** No open field plot inside any AOI covering 2019–2025.
BRA: PRODES Cerrado (13 polygons in AOI; 40 polygons 2019–25 within ~5 km) and MapBiomas Alerta (36 alerts
2019–25 within ~11 km) — the only dated, expert-checked, S2-independent event references. IND: Bhuvan/NRSC
1:50k degradation atlas (17 polygons, 8.4 of 26.8 km² degraded; 2005-06/2015-16). ETH: Nyssen et al. 2024
post-war photo survey (55 sites, nearest 14.5 km; qualitative). MNG: Ahlborn PANGAEA grazing-gradient plots
(4.4 km; 2014–15). AUS: NSW SLATS clearing maps exist but need manual browser download; TERN transects ≥ 75 km.
SEN/KEN/NPL: nothing open nearby (LDSF Kenya nearest 128 km; Ethiopian LDSF restricted). Hansen GFC: useful
only in BRA; KEN 2020 "loss" coincides with the Lake Baringo flood (artefact).

**Very-high-resolution imagery.** Esri Wayback (0.25–0.46 m, 3–7 distinct acquisition dates per AOI since 2016,
all 9 AOIs) — licence permits visual inspection/figures, not clearly bulk harvesting for model training.
Spain PNOA 0.25 m (2016, 2019, 2022, 2025; CC BY 4.0) and Brazil CBERS-4A WPM 2 m (open) are usable as model
inputs. Planet NICFI 4.77 m (tropical AOIs) needs a user sign-up; programme status changed 2025.

**R-012 Independent validation in BRA vs official clearing maps** (`scripts/validate_brazil.py`,
`outputs/results/brazil_validation.json`, fig19). Within the 5.12 km AOI only PRODES/Alerta 2025 clearings
fall inside (80.8 ha, 8 080 pixels; 40 PRODES + 36 Alerta polygons 2019–25 in the surrounding bbox).
* Label recall: **94.7 %** of officially cleared pixels carry an S2 label onset in [May Y-1, Dec Y], vs a
  **6.2 %** background rate for never-cleared pixels in an equal-length window (15× enrichment).
* Label precision: 10.7 % of S2 onset pixels (2019–25) lie inside official clearings vs 3.1 % of all pixels
  (3.4× enrichment); the remainder are declines that PRODES does not map (crop failure, degradation, pivots).
* **Warning skill: AUC 0.45** — max risk in the 19 months before the end of the 2025 clearing year was not
  higher at cleared pixels (median 0.020) than at never-cleared pixels (0.028). Interpretation: clearing is
  an abrupt management decision, not preceded by vegetation-resilience loss; CARE-EW *detects* clearing
  (labels) but cannot *forecast* it. Scope statement for the paper: CARE-EW warns of gradual, ecologically
  driven decline, not of planned land conversion. Caveat: one AOI, one clearing year.

**Implication.** A pixel-level, time-specific ground truth exists only for BRA (clearing events). Elsewhere the
feasible reference is (a) blind visual interpretation of multi-date VHR at sampled warnings / non-warnings /
events (protocol to be written), (b) spatial agreement with expert maps (IND atlas, ESP LUCAS), (c) field
visits. A "combined satellite + field-imagery" model can be trained with permissively licensed VHR only in
ESP and BRA unless NICFI or Esri permission is obtained.

## 9. How to reproduce
```
.venv/Scripts/python scripts/run_s2_all.py          # S2 cubes (bandwidth-bound, hours)
.venv/Scripts/python -m care_ew.climate             # climate
.venv/Scripts/python -m care_ew.context static      # land cover, DEM, water
.venv/Scripts/python -m care_ew.context modis       # MODIS history
.venv/Scripts/python -m care_ew.hydro               # rivers + discharge
.venv/Scripts/python -m care_ew.dataset             # cubes, features, labels, tables
.venv/Scripts/python -m care_ew.train               # ablation, final model, LOCO, curves, walk-forward
.venv/Scripts/python -m care_ew.corroborate         # Landsat/MODIS label corroboration
.venv/Scripts/python -m care_ew.figures             # all paper figures
.venv/Scripts/python -m care_ew.export              # app data
.venv/Scripts/python -m uvicorn app.server:app --port 8765
```

---

## 10. Results (E-003: nine AOIs, label v3, D-016 parameters — run 2026-10-19 18:45–19:34)

All numbers from `outputs/results/metrics.json` and `outputs/results/corroboration.json`. Pipeline timing:
dataset 522 s · train (ablation, final, validation curve, learning curve, walk-forward, LOCO, label
sensitivity) 897 s · wall-to-wall prediction 1215 s · corroboration 117 s · figures 68 s · export 393 s.

### R-002 Data set
| AOI | tile | valid pixels | rows | positive rate | onsets /px/yr | land cover (≥ 3 %) | climate model applied to |
|---|---|---|---|---|---|---|---|
| NPL_chure | 45RUK | 260 614 | 326 032 | 0.0078 | 0.014 | tree 85, crop 8, bare 5 | pooled small classes, bare |
| IND_bundelkhand | 44RLP | 258 610 | 316 887 | 0.0095 | 0.018 | crop 81, grass 13, tree 4 | tree, grass, crop |
| ETH_tigray | 37PER | 262 111 | 340 513 | 0.0162 | 0.027 | crop 49, shrub 35, grass 16 | none |
| KEN_baringo | 36NZF | 244 036 | 336 514 | 0.0291 | 0.056 | grass 38, tree 26, shrub 19, crop 14 | tree, shrub, grass |
| SEN_ferlo | 28PEC | 262 144 | 357 686 | 0.0082 | 0.014 | grass 88, shrub 10 | pooled, grass |
| ESP_murcia | 30SXG | 243 025 | 337 139 | 0.0311 | 0.056 | grass 40, crop 38, bare 19 | grass, crop, bare |
| BRA_matopiba | 23LLG | 261 256 | 320 163 | 0.0299 | 0.053 | crop 80, grass 10, shrub 6, tree 4 | none |
| MNG_steppe | 48TXS | 262 141 | 371 304 | 0.0003 | 0.0004 | grass 100 | none |
| AUS_murraydarling | 55JCF | 261 988 | 355 419 | 0.0210 | 0.041 | tree 72, grass 28 | tree, grass |

Totals: 3.06 M pixel-month rows (45 000 sampled pixels). Splits: train 824 743 rows (pos 1.10 %), early
stopping 93 592 (1.67 %), calibration 198 015 (1.75 %), **locked test 78 771 (2.57 %)**, all 9 AOIs in each.

### R-003 Ablation on the locked test (unseen 1 km blocks × 2024-12…2025-10)
| model | PR-AUC | lift | ROC-AUC | train AP − val AP |
|---|---|---|---|---|
| A0 anomaly persistence (−z̄₃) | 0.043 | 1.7 | 0.630 | – |
| A0 NDVI trend (−slope₁₂) | 0.023 | 0.9 | 0.478 | – |
| A0 residual rule (−R̄₃) | 0.058 | 2.2 | 0.687 | – |
| RF Sentinel-only (A1+A2) | 0.035 | 1.3 | 0.572 | – |
| LGB A1 state | 0.030 | 1.2 | 0.534 | 0.009 |
| + A2 change | 0.033 | 1.3 | 0.545 | 0.109 |
| + A3 climate | 0.034 | 1.3 | 0.562 | 0.179 |
| **+ A4 climate-conditioned residual** | **0.093** | **3.6** | **0.735** | −0.010 |
| **+ A5 resilience** | **0.122** | **4.7** | **0.765** | −0.022 |
| + A6 spatial context | 0.117 | 4.6 | 0.762 | 0.019 |

Interpretation: spectral state/change and raw climate barely beat chance; the **peer-relative climate
residual triples skill**, **resilience indicators add a further ~30 %**; spatial context adds nothing
measurable. Raw climate variables (A3) add no direct skill — weather matters only *through* the residual
(supports the "weather only if strictly necessary" rule). A6 was pre-specified as the final model and is
kept (A5 ≥ A6 on both validation and test; difference within CI; not re-selected after seeing test).

### R-004 Final model (A6 + isotonic calibration + Mondrian conformal, α = 0.10)
* **PR-AUC 0.113 (95 % cluster-bootstrap CI 0.085–0.163), lift 4.4; ROC-AUC 0.762 (0.713–0.808);
  Brier 0.024; ECE 0.009.**
* Operating threshold (max-F1 on calibration rows) p = 0.127: precision 0.205, recall 0.201,
  **false-alarm rate 2.1 %**, F1 0.203.
* Conformal: abstain 47.5 %; class coverage 0.874 (events) / 0.900 (non-events) vs nominal 0.90.
  On non-abstained cases PR-AUC 0.160, ROC-AUC 0.843; "no event" calls correct 99.2 % (NPV).
* Lead time: 910 test onsets; 31 % warned ≥ 1 month ahead at the operating threshold; median lead
  2 months (mean 2.6); histogram {missed 629, 1 mo 109, 2 mo 48, 3 mo 38, 4 mo 33, 5 mo 30, 6 mo 23}.
* Hold-out diagnostics: temporal-only (test months, seen blocks) PR-AUC 0.133 / ROC 0.806; spatial-only
  (test blocks, training months) 0.127 / 0.838 — the joint place-and-time hold-out is the hardest, as it
  should be.
* Per AOI (test): AUS 0.146 (×14.2, ROC 0.92) · ETH 0.249 (×9.5, 0.88) · SEN 0.261 (×9.0, 0.91) ·
  KEN 0.171 (×7.7, 0.82) · NPL 0.126 (×7.0, 0.79) · IND 0.058 (×4.5, 0.72) · ESP 0.274 (×4.1, 0.76) ·
  BRA 0.046 (×2.2, 0.62) · MNG no test events.
* Per land cover: shrub 0.220 (×6.4) · grass 0.192 (×5.6) · bare 0.203 (×4.4) · tree 0.092 (×7.1) ·
  **cropland 0.073 (×3.1, ROC 0.70) — weakest**, consistent with crop-management changes in the labels.
* Explanations (mean |SHAP|, test): MODIS 5-yr variance 0.248 · AC1 (24 mo) 0.165 · fraction of last 12 mo
  below expectation 0.140 · σ 0.121 · land cover 0.120 · ΔAC1 (12 mo) 0.115 · R̄₆ 0.114 · μₘ 0.106 ·
  variance (24 mo) 0.104. **Five of the nine strongest drivers are resilience indicators.**

### R-005 Over-/under-fitting evidence
* Validation curve (val AP): 3 leaves 0.146 · **7 leaves 0.150** · 15 0.139 · 31 0.140 · 63 0.135 ·
  127 0.146 · 255 0.142, while train AP rises 0.11 → 0.44. Capacity beyond 7 leaves only memorises.
* Learning curve (fraction of training pixels → test AP): 5 % 0.074 · 10 % 0.091 · 25 % 0.097 · 50 % 0.109 ·
  100 % 0.117 — still rising: **the model is data-limited, not capacity-limited** (no under-fitting from
  over-regularisation; more AOIs/years should keep helping).
* Train–val AP gap per ablation step ≤ 0.18 and ≈ 0 for the final feature sets.

### R-006 Continuous (walk-forward) retraining
| test year | training rows | PR-AUC | lift | ROC-AUC |
|---|---|---|---|---|
| 2021 | 22 686 | 0.030 | 1.6 | 0.645 |
| 2022 | 289 268 | 0.035 | 1.4 | 0.595 |
| 2023 | 543 509 | 0.089 | 3.7 | 0.754 |
| 2024 | 784 870 | 0.127 | 4.3 | 0.702 |
| 2025 | 1 020 379 | 0.156 | 5.9 | 0.792 |
Skill grows as Sentinel-2 history accumulates. (Walk-forward models are uncalibrated: ECE 0.03–0.10.)

### R-007 Leave-one-country-out (train on 8 nations, test the 9th, test period)
Australia 0.133 (×9.3, ROC 0.87) · Ethiopia 0.203 (×8.2, 0.89) · Senegal 0.216 (×7.8, 0.85) · Kenya 0.150
(×4.4, 0.80) · Spain 0.197 (×3.9, 0.73) · India 0.057 (×3.7, 0.69) · Nepal 0.051 (×3.5, 0.70) · Brazil 0.107
(×2.4, 0.71) · Mongolia not scorable (no events). Transfer to a never-seen nation retains ×2.4–×9.3 lift.

### R-008 Label-definition sensitivity (re-labelled, retrained, same test protocol)
| thr \\ min_run | 4 | 6 | 9 |
|---|---|---|---|
| −0.75 | 0.227 (×2.7, ROC 0.74) | 0.112 (×3.4, 0.73) | 0.032 (×3.2, 0.73) |
| −1.0 | 0.224 (×3.3, 0.77) | **0.119 (×4.6, 0.74)** | 0.022 (×3.0, 0.72) |
| −1.5 | 0.187 (×5.0, 0.80) | 0.062 (×4.9, 0.77) | 0.013 (×4.6, 0.70) |
Lift 2.7–5.0 and ROC 0.70–0.80 under every definition — the result is not an artefact of one threshold.

### R-009 Independent-sensor corroboration of labels (agreement AUC; 0.5 = none)
| AOI | Landsat 8/9 30 m | MODIS 250 m |
|---|---|---|
| BRA_matopiba | **0.931** | 0.745 |
| AUS_murraydarling | 0.830 | 0.527 |
| ESP_murcia | 0.747 | 0.524 |
| KEN_baringo | 0.733 | 0.522 |
| ETH_tigray | 0.686 | 0.576 |
| IND_bundelkhand | 0.679 | 0.534 |
| NPL_chure | 0.614 | 0.492 |
| MNG_steppe | 0.566 | 0.480 |
| SEN_ferlo | **0.464** | 0.568 |
Landsat (different sensor, agency, overpass and cloud mask) confirms S2-labelled declines in 7 of 9 AOIs.
**SEN and MNG labels are not corroborated** — their S2 events may be dominated by artefacts or by
signals too subtle for Landsat; SEN's high test score must therefore not be read as validated skill.
MODIS 250 m is mostly uninformative at 10 m event scale (mixed pixels) except in BRA (large clearings).

### R-010 Hydrology (GloFAS, outlet reach, 1984–2000 vs 2016–present mean flow)
NPL +2 % · IND +51 % · ETH +3 % (Q90 −27 %) · KEN +2 % (upstream tributaries +17/+18 %) · SEN +22 % ·
ESP +455 % (implausible: tiny reach, GloFAS cannot resolve it) · **BRA −36 % (Q90 −35 %)** — consistent
with documented irrigation-driven streamflow decline in western Bahia · AUS −90 % (ephemeral channel).
Discharge is shown in the console for context; it is **not** a model input in v1 (Threats §11.10).

### R-011 Operational products
Risk/NDVI/RGB overlays for 45 months × 9 AOIs, 92 hotspots at 2026-09 (warning 60, active decline 32,
none in SEN/MNG), highest current risk KEN (425 ha above threshold). Screenshots:
`outputs/screenshots/ui_final/` (globe, AOI with hotspots + upstream rivers, hotspot panel with drivers
and before/after chips, pixel inspector, river-flow before/now, model card). All 18 paper figures in
`outputs/figures/` (PNG + PDF).

---

## 11. Known issues / threats to validity (keep honest; reviewers start here)

* **Model selection uses a single-year validation window** (2023-03 … 2023-12); seed noise ≈ the 0.005 decision margin. Several rejected changes improved the test set (R-019, R-020b). Decisions were not reversed; a prospective test is planned (R-020b / D-028).
1. **EO proxies ≠ field truth.** Labels are persistent, climate-unexplained NDVI declines. They include
   true degradation, but also land-use change (cropland fallowing, conversion), fire scars, and harvest.
   Land-cover-stratified results and independent-sensor corroboration are reported, but no field data.
2. **Short S2 baseline.** μₘ and σ come from 4 years (2017–2020). If an AOI was already degrading in
   2017–2020, the baseline is depressed and later decline under-estimated. MODIS 2001–2020 anomalies are
   provided as a long-baseline feature to partly compensate.
3. **Climate at AOI scale.** One climate series per AOI (≈ 10–25 km cells) vs. 10 m pixels. Local
   rainfall variability is absorbed by β and by the residual.
4. **ERA5 precipitation** (D-007) is weaker than CHIRPS over convective tropics.
5. **Within-training-period look-ahead.** μₘ, σ (2017–2020) and the climate model (≤ 2022-03) are
   estimated with data that are in the future relative to early training rows. This cannot leak into
   validation/test (all ≥ 2023), but training-period residuals are slightly optimistic.
6. **Scene cloud cover is tile-level**; the "4 least-cloudy" scenes may be cloudy over the AOI, reducing
   valid observations in monsoon months (NPL, IND, ETH).
7. **Five 5 × 5 km AOIs per nation would be better than one.** One AOI per nation means LOCO tests
   transfer to a new landscape, not to a new place in the same nation.
8. Interpolated label months (≤ 2) use future observations — acceptable for labels, never for features.
9. **Peer-relative (LNS) labels cannot see whole-landscape degradation.** If an entire land-cover class of
   an AOI degrades together it cancels against its own peers. MNG (100 % grass) has essentially no events
   for this reason; the system is a *local* early-warning tool and should be paired with absolute-trend
   indicators (e.g. SDG 15.3.1 productivity sub-indicator) for regional assessment.
10. **Discharge is context only.** GloFAS at ~5 km cannot resolve small reaches (ESP +455 % is an
   artefact); flow change is not a model input and must not be read as causal attribution.
11. **SEN / MNG labels uncorroborated** by Landsat (AUC 0.46 / 0.57). Report their skill separately.
12. **Cropland is the weakest stratum** (PR-AUC 0.073, ×3.1): labels mix crop-management change with
   degradation. Operational use in cropland needs crop-calendar information or field checks.
13. **High abstention (47.5 %).** With ~2.6 % prevalence and moderate discrimination, honest 90 % class
   coverage requires abstaining on half the cases. This is a feature for prioritisation (the confident half
   has ROC 0.84) but means the map is not a wall-to-wall verdict.
14. **One debugging pass saw IND/NPL test rows** (E-001, two-AOI runs). Design choices were made on
   validation and label diagnostics; the final 9-AOI test set includes those AOIs' test blocks.
15. Test period is ~11 months (2024-12…2025-10) — bounded by the 11-month label look-ahead; confidence
   intervals are correspondingly wide (PR-AUC 0.085–0.163).
16. ERA5-based climate conditioning was rejected (LOYO R² < 0.05) in ETH, BRA, MNG; there the residual is
   purely peer-relative.
