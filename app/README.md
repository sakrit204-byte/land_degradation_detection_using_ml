# CARE-EW web app

A Google-Earth-style console for the CARE-EW land-degradation early-warning system:
a CesiumJS 3D globe with risk overlays, hotspot boxes, river networks, time slider,
analytics charts, a pixel inspector and a model card. Plain ES modules, no build step.

```
app/
  server.py            FastAPI: serves static/ at "/", /api/health, /api/pixel, /api/plan, /api/analyze, /api/jobs
  make_mock_data.py    writes MOCK files into static/data/ (UI development only)
  ui_screenshots.py    headless Playwright smoke test -> outputs/screenshots/ui_dev/
  ui_drawbox_test.py   Playwright test of Draw box / Jobs on its own server (port 8766) -> outputs/screenshots/ui_drawbox/
  ui_timelapse_test.py Playwright test of the hotspot time-lapse on its own server (port 8766) -> outputs/screenshots/ui_timelapse/
  static/
    index.html
    css/app.css · css/area-tool.css · css/timelapse.css
    js/  main.js (controller) · globe.js (viewer, basemaps, compass, scale bar)
         aoi-layers.js (pins, overlays, hotspots, rivers, stations) · charts.js (Chart.js)
         panels.js (AOI list, legend, hotspot/station panels, model card) · export.js · data.js · config.js
         area-tool.js (box drawing, plan/run panel, jobs panel + polling)
         timelapse.js (Sentinel-2 time-lapse clipped to one hotspot box)
    data/              <- written by the pipeline (care_ew/export.py) or by make_mock_data.py
```

## Run

```bash
# 1. data: real pipeline output, or mock data for development
.venv/Scripts/python app/make_mock_data.py          # refuses to overwrite real (non-mock) data

# 2. server
.venv/Scripts/python -m uvicorn app.server:app --port 8765
# open http://127.0.0.1:8765/   (deep link to an AOI: http://127.0.0.1:8765/#aoi=NPL_chure)

# 3. optional: automated smoke test + screenshots (server must be running)
.venv/Scripts/python -m playwright install chromium   # once
.venv/Scripts/python app/ui_screenshots.py
.venv/Scripts/python app/ui_drawbox_test.py          # starts/stops its own server on :8766; never clicks "Run"
.venv/Scripts/python app/ui_timelapse_test.py        # starts/stops its own server on :8766
```

Internet access is needed in the browser: CesiumJS 1.121.0 and Chart.js 4.4.1 come from
jsDelivr, and the base maps are streamed from Esri / OpenStreetMap. No Cesium ion token is used.

## Data contract

The UI only reads the files described in **[docs/UI_DATA_SPEC.md](../docs/UI_DATA_SPEC.md)**
(`static/data/aois.json`, `metrics.json` and `static/data/aois/<key>/…`) plus the two API endpoints.
Missing optional files are handled gracefully (the panel shows "not available").

`make_mock_data.py` writes the same format for three AOIs (NPL_chure, ETH_tigray, BRA_matopiba;
real centres, ±2.5 km box). **Every mock file carries `"mock": true` and the UI shows a purple
"MOCK DATA · not results" badge**, so mock output cannot be mistaken for results. Re-running the
real exporter overwrites the mock files.

### API

* `GET /api/health` – status, whether `aois.json` is mock, and which AOIs have `cube.npz` / `risk_cube.npz`.
* `GET /api/pixel?aoi=KEY&lon=..&lat=..` – reads `data/processed/<aoi>/cube.npz` (lazily loaded, cached
  per file mtime) and, if present, `static/data/aois/<aoi>/risk_cube.npz`. lon/lat are mapped linearly
  onto the H×W grid using the AOI bbox from `aois.json` (row 0 = north edge).
  Returns `{months, ndvi, z, resid, risk, label, label_onsets, landcover, row, col, mock}`; NaN → `null`.
  `404` for unknown AOI, a point outside the AOI or a masked pixel. Without `cube.npz` a deterministic
  synthetic series is returned with `"mock": true` (the UI labels it "MOCK pixel series").

## Using the interface

* **Globe view** – every AOI is a pin coloured by its mean risk (Low < 0.06 ≤ Moderate < 0.10 ≤ Elevated
  < 0.15 ≤ High; thresholds in `js/config.js`). Click a pin, its box, or a sidebar card to fly in.
  The sidebar search filters by key, country or landscape (Enter opens the first match).
* **AOI view layers** (left sidebar, each with opacity slider where relevant):
  * *Risk probability* – `risk/<month>.png`: calibrated probability of a persistent degradation onset
    within 6 months; transparent below 0.15; purple hatching = conformal **abstain** (inspect in field).
  * *NDVI anomaly* – `ndvi/<month>.png`: z-score vs seasonal baseline, brown (−3) → green (+3).
  * *Sentinel-2 true colour* – `rgb/<month>.png` (latest available month ≤ the slider month).
  * *Hotspot boxes* – `hotspots.geojson`, labelled `H1 · risk · area`; red = warning, orange = watch,
    purple dashed/striped = abstain, dark red = active degradation. Click for the detail panel
    (risk, area, first warning, land cover, NDVI now vs baseline, rain anomaly, distance to river,
    top-5 drivers, before/after Sentinel-2 chips, zoom / copy coordinates / export).
  * *Upstream river network* – `rivers_network.geojson`: upstream reaches glowing cyan, width ∝ Strahler
    order; the AOI outlet reach in gold; downstream reaches dashed light blue.
  * *Local river reaches* – `rivers_local.geojson`, thin lines.
  * *Discharge points* – `hydro.json` stations (click for before/after flow numbers).
  * *Place labels* – Esri World Boundaries & Places reference layer.
* **Time slider** – steps through `months_risk` (◀ ▶, play, or ← → keys) and swaps the raster overlays.
  Hotspots always describe the latest month.
* **Analytics drawer** – *AOI time series* (NDVI; z & residual; risk & fraction below expectation;
  6-month rain anomaly; dashed line = slider month), *River flow* (mean and Q90 low flow, 1984–2000 vs
  2016–, with % change table), *Pixel inspector* (click anywhere inside the AOI box: NDVI, z/residual and
  risk series with label onsets marked in red).
* **Model card** – headline metrics, baselines, ablation and leave-one-country-out tables from
  `metrics.json` (common key aliases are accepted; missing sections say "not available"), plus the
  disclaimer that probabilities are EO-proxy based and not field-verified.
* **Export** – hotspots of the open AOI (or of all AOIs from the globe view) as GeoJSON or CSV for field
  teams; the files include model version, the mock flag and the not-field-verified caveat.
* Base map selector: Esri World Imagery (default), Esri Topographic, OpenStreetMap.

## Hotspot Sentinel-2 time-lapse

Clicking any hotspot box (it is most useful for **active degradation** boxes) adds a
**Sentinel-2 time-lapse (this block)** section to the hotspot panel. It is ON by default.
* It plays the AOI's monthly true-colour frames (`rgb/<YYYY-MM>.png`, the months in `meta.json` `months_rgb`)
  through an imagery layer whose `rectangle` is exactly the hotspot box, so **nothing outside the block is
  drawn**. Frames are shown with nearest-neighbour sampling, so each 10 m pixel stays crisp.
* While it is on, the camera fits the block (small margin, gentle tilt) and the block gets a bright cyan
  frame. The AOI risk, NDVI and RGB overlays and the box's own fill are hidden so the imagery is clear.
  Everything is restored when the switch is turned off, the panel closes, another hotspot or a station is
  clicked, or the user leaves the AOI.
* The mini timeline is independent of the main risk slider. It has a slider over all available months
  (cloudy months are simply absent), ‹ › step buttons (`,` and `.` also work while the panel has focus),
  ▶ play / pause at about 1.5 frames per second, and **Same season only**, which steps 12 months at a
  time (same calendar month every year) to separate real change from seasonality.
* Ticks on the slider, with a legend under it, mark:
  * the first-warning month;
  * the month the block went below its peers (latest month − `months_below` + 1, for active degradation);
  * the before / after chip months (`chip_before_month`, `chip_after_month`).
* Frames are fetched through the shared progress tracker (top progress bar and chip) and show
  "loading frame…" in the panel. The next frame is prefetched, frames cross-fade on two layers, and
  about 30 decoded frames are cached.
* The same feature works for study areas and user areas. On narrow screens the hotspot panel becomes a
  bottom sheet and the block is framed in the visible upper half of the map.

## Analyse any place: ✎ Draw box

1. Click **✎ Draw box** in the top bar. The cursor becomes a crosshair: **drag** a rectangle on the globe, or
   **click one corner, then the opposite corner**. The size in km is shown live. Mouse-wheel zoom still works;
   **Esc** cancels. Works from the whole-globe view and when zoomed in.
2. The *Analyse a new area* panel shows the box size, its W/S/E/N bounds and a name field, and asks
   `POST /api/plan` how it would be processed: *“N Sentinel-2 blocks · ~XX min · tile T”* plus the analysed
   area. Errors are shown in red with a suggestion (for example *too big → draw at most ~10 × 10 km / 4 blocks*;
   too small; outside Sentinel-2 land coverage).
3. For precise areas use the **⌖ Type coordinates** tab: *centre lon/lat + size (km)* or *W / S / E / N*.
   *Preview box & check* draws the box, flies to it and runs the same plan check.
4. **▶ Run analysis** calls `POST /api/analyze` (only one analysis at a time; a 409 is explained in the panel).
   The real pipeline downloads every Sentinel-2 month since 2017, so expect ~45 min per 5.12 km block.

**Jobs** (top bar; it shows a spinner and the percentage while an analysis runs) opens the jobs panel. It polls
`GET /api/jobs/{id}` every 5 s and shows the stage pipeline (grid → static → climate → Sentinel-2 → MODIS →
rivers → features → predict → export) with the current step highlighted, a progress bar, the detail line
(for example months downloaded), elapsed time and a rough ETA, plus the last 10 log lines. Errors appear in red.
Earlier analyses are listed underneath (click one to view it). Running jobs are also outlined on the globe in
dashed yellow. The job list is re-read every 30 s, so jobs started from another browser also appear.

When a job finishes, the app re-reads `aois.json`, lists the new area(s) under **Your areas** (dashed card,
`USER` badge) and flies there. User areas behave exactly like the study areas (layers, hotspots, time slider,
charts, pixel inspector, export). Two extra things are shown for them:
* the box the user drew stays visible as a **dashed white** outline (`user_bbox`), next to the analysed
  5.12 km blocks (the AOI `bbox`);
* the `warning` text (*“Model applied outside its training areas - treat as indicative.”*) appears as an
  amber banner under the breadcrumb and at the top of every hotspot panel.

## Limitations

* Terrain is the WGS84 ellipsoid (no ion terrain), so 3D tilt shows flat ground.
* Raster overlays are single PNG tiles over the AOI bbox; pixel lookup uses a linear lon/lat → row/col
  mapping over that bbox (adequate for 5 km boxes, not an exact UTM transform).
* Headless screenshots use SwiftShader WebGL; real GPUs render faster and sharper.
