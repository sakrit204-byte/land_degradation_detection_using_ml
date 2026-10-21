// CARE-EW application controller: wires data, globe, panels and charts together.
/* global Cesium */
import { ATTRIBUTION_HTML, OSM_ATTRIBUTION } from './config.js';
import { loadIndex, loadMetrics, loadAoiBundle, fetchPixel, forgetAoi, esc, fmt } from './data.js';
import { BoxDrawer, AnalysePanel, JobsPanel } from './area-tool.js';
import { createViewer, Basemaps, installNavWidgets, flyToBox, flyHome } from './globe.js';
import { AoiPins, AoiView } from './aoi-layers.js';
import { Analytics } from './charts.js';
import { renderAoiList, renderLegend, renderHotspot, renderStation, renderRiver, renderModelCard } from './panels.js';
import { exportGeoJSON, exportCSV } from './export.js';
import { HotspotTimelapse } from './timelapse.js';
import { mountProgress, trackGlobe, step, stepDone, stepFail, tilesDetail, tilesPending } from './progress.js';

const C = Cesium;
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const state = {
  index: null,          // aois.json
  aoi: null,            // active AOI entry
  bundle: null,         // its loaded files
  months: [],           // months_risk of the active AOI
  monthIdx: 0,
  playing: null,
  labelsOn: true,
};
window.careew = state;    // handy for debugging / automated UI tests

// ------------------------------------------------------------------ helpers
let toastTimer;
function toast(msg, ms = 3500) {
  const t = $('#toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), ms);
}
function setLoading(on, text) {
  const l = $('#loading');
  l.classList.toggle('hidden', !on);
  if (text) l.querySelector('span').textContent = text;
}

// ------------------------------------------------------------------ boot (every step reports real progress)
mountProgress({ bar: $('#netbar'), chip: $('#netchip'), startup: $('#loading') });
step('engine', 'Globe engine and app code', 'done', `Cesium ${Cesium.VERSION || ''}`);
step('index', 'Area list (aois.json)', 'run', 'downloading…');
step('globe', '3D globe', 'run', 'creating…');
step('tiles', 'Base-map tiles (Esri World Imagery)', 'wait', 'waiting for globe');
const viewer = createViewer('cesium', $('#cesium-credits'));
stepDone('globe', 'ready');
trackGlobe(viewer);
const basemaps = new Basemaps(viewer);
basemaps.set('esri');
basemaps.ensureLabels();
installNavWidgets(viewer, { compassEl: $('#compass'), scaleEl: $('#scalebar'), readoutEl: $('#readout') });
const pins = new AoiPins(viewer);
const view = new AoiView(viewer, basemaps);
const timelapse = new HotspotTimelapse(viewer, { basemaps, view });   // Sentinel-2 frames clipped to a hotspot
const analytics = new Analytics($('#analytics'));

// ------------------------------------------------------------------ on-demand analysis (draw box -> plan -> run -> jobs)
const drawer = new BoxDrawer(viewer);
const analysePanel = new AnalysePanel($('#analyse-panel'), {
  drawer,
  toast,
  onFly: (b) => flyToBox(viewer, b, { duration: 2, pitchDeg: -60 }),
  onStarted: (id) => { jobs.watch(id); jobs.toggle(true); jobs.refresh(); },
});
const jobs = new JobsPanel($('#jobs-panel'), $('#btn-jobs'), {
  toast,
  onRunning: (running) => drawer.setJobBoxes(running),
  onOpenKey: (k) => { jobs.toggle(false); enterAoi(k); },
  onFinished: async (job) => {
    // the pipeline added new area(s) to aois.json: reload, list them, fly to the first one
    try { state.index = await loadIndex({ fresh: true }); } catch (e) { toast(`Could not reload aois.json: ${e.message}`); return; }
    (job.keys || []).forEach(forgetAoi);
    pins.render(state.index.aois || []);
    pins.setActive(state.aoi?.key ?? null);
    $('#aoi-count').textContent = `${(state.index.aois || []).length}`;
    refreshList();
    const key = (job.keys || []).find((k) => (state.index.aois || []).some((a) => a.key === k));
    toast(`Analysis “${job.name}” finished${key ? ' – opening ' + key : ''}.`, 6000);
    if (key) enterAoi(key);
  },
});
$('#btn-draw').addEventListener('click', () => {
  if (analysePanel.isOpen && drawer.active) { drawer.cancel(); return; }
  closeInfo();
  analysePanel.open('draw');
});
view.onRasterError = (kind, url) => console.warn('[overlay] missing', kind, url);
$('#attribution').innerHTML = ATTRIBUTION_HTML;
viewer.camera.setView({ destination: C.Cartesian3.fromDegrees(40, 12, 2.4e7) });

// base-map tiles: live "done / total" until the first full view has arrived
step('tiles', null, 'run', 'requesting…');
let sawTiles = false;
const removeTileListener = viewer.scene.globe.tileLoadProgressEvent.addEventListener((n) => {
  if (n > 0) { sawTiles = true; step('tiles', null, 'run', tilesDetail()); }
  if (n === 0 && sawTiles) { stepDone('tiles', 'first view complete'); removeTileListener(); }
});

async function boot() {
  try {
    state.index = await loadIndex();
    stepDone('index', `${(state.index.aois || []).length} areas`);
  } catch (e) {
    stepFail('index', e.message);
    console.error(e);
    $('#aoi-list').innerHTML = `<li class="empty">Could not load <code>data/aois.json</code>.<br>Run the pipeline exporter
      or <code>python app/make_mock_data.py</code>.</li>`;
    return;
  }
  const idx = state.index;
  $('#model-version').textContent = idx.model_version || 'model n/a';
  $('#latest-month').textContent = idx.latest_month || '–';
  $('#mock-badge').hidden = !(idx.mock || (idx.aois || []).some((a) => a.mock));
  $('#aoi-count').textContent = `${(idx.aois || []).length}`;
  pins.render(idx.aois || []);
  refreshList();
  refreshLegend();
  jobs.refresh();
  // deep link: #aoi=KEY
  const m = location.hash.match(/aoi=([\w-]+)/);
  if (m) enterAoi(m[1]);
  else flyHome(viewer, centroidOfAois(), 2.2);
}

function centroidOfAois() {
  const a = state.index?.aois || [];
  if (!a.length) return [40, 12];
  return [a.reduce((s, x) => s + x.center[0], 0) / a.length, a.reduce((s, x) => s + x.center[1], 0) / a.length];
}

function refreshList() {
  renderAoiList($('#aoi-list'), state.index?.aois || [], {
    query: $('#aoi-search').value, activeKey: state.aoi?.key, onPick: (k) => { enterAoi(k); closeSidebarIfNarrow(); },
  });
}

function refreshLegend() {
  renderLegend($('#legend'), { meta: state.bundle?.meta, visible: view.visible, inAoi: !!state.aoi });
}

// ------------------------------------------------------------------ AOI enter / exit
async function enterAoi(key) {
  const aoi = (state.index?.aois || []).find((a) => a.key === key);
  if (!aoi) { toast(`Unknown AOI ${key}`); return; }
  stopPlay();
  closeInfo();
  state.aoi = aoi;
  history.replaceState(null, '', `#aoi=${encodeURIComponent(key)}`);
  refreshList();
  $('#crumb-aoi').innerHTML = aoi.user
    ? ` › <b>${esc(aoi.landscape || 'User area')}</b> <span class="user-badge">USER</span> · <span class="mono">${esc(aoi.key)}</span>`
    : ` › <b>${esc(aoi.country)}</b> · <span class="mono">${esc(aoi.key)}</span>`;
  $('#aoi-warning').hidden = !aoi.warning;
  $('#aoi-warning').innerHTML = aoi.warning ? `⚠ ${esc(aoi.warning)}` : '';
  $('#an-title').textContent = `${aoi.country} · ${aoi.key} — ${aoi.landscape || ''}`;
  $('#export-scope').textContent = `Hotspots · ${aoi.key}`;
  $('#layers-hint').textContent = aoi.key;
  $('#layers-panel').classList.add('enabled');
  pins.setActive(key);
  const fb = Array.isArray(aoi.user_bbox) ? [Math.min(aoi.bbox[0], aoi.user_bbox[0]), Math.min(aoi.bbox[1], aoi.user_bbox[1]),
    Math.max(aoi.bbox[2], aoi.user_bbox[2]), Math.max(aoi.bbox[3], aoi.user_bbox[3])] : aoi.bbox;
  const flight = flyToBox(viewer, fb);
  const bundle = await loadAoiBundle(key);
  if (state.aoi !== aoi) return;            // user moved on meanwhile
  state.bundle = bundle;
  view.load(aoi, bundle);
  const meta = bundle.meta || {};
  state.months = meta.months_risk || [];
  state.monthIdx = Math.max(0, state.months.length - 1);
  setupTimebar();
  await view.setMonth(state.months[state.monthIdx]);
  analytics.renderTimeseries(bundle.ts);
  analytics.renderFlow(bundle.hydro);
  resetPixelPane();
  refreshLegend();
  openAnalytics(true);
  await flight;
  if (!bundle.meta) toast('meta.json missing for this AOI – raster overlays unavailable.');
}

function exitAoi() {
  stopPlay();
  closeInfo();
  view.clear();
  state.aoi = null; state.bundle = null; state.months = [];
  history.replaceState(null, '', location.pathname);
  pins.setActive(null);
  $('#crumb-aoi').innerHTML = '';
  $('#aoi-warning').hidden = true;
  $('#timebar').hidden = true;
  $('#an-title').textContent = 'Select an AOI';
  $('#export-scope').textContent = 'Hotspots · all AOIs';
  $('#layers-hint').textContent = 'open an AOI';
  $('#layers-panel').classList.remove('enabled');
  analytics.renderTimeseries(null);
  openAnalytics(false);
  refreshList();
  refreshLegend();
  flyHome(viewer, centroidOfAois());
}

// ------------------------------------------------------------------ time slider
function setupTimebar() {
  const n = state.months.length;
  $('#timebar').hidden = n === 0;
  const r = $('#tb-range');
  r.max = Math.max(0, n - 1);
  r.value = state.monthIdx;
  // year ticks
  $('#tb-ticks').innerHTML = state.months.map((m, i) => (m.endsWith('-01') || i === 0
    ? `<span style="left:${n > 1 ? (i / (n - 1)) * 100 : 0}%">${m.endsWith('-01') ? m.slice(0, 4) : ''}</span>` : '')).join('');
  updateMonthLabel();
}

function updateMonthLabel() {
  const m = state.months[state.monthIdx] || '–';
  $('#tb-month').textContent = m;
  const latest = state.months[state.months.length - 1];
  $('#tb-note').textContent = m !== latest ? `hotspots shown for ${latest}` : 'latest';
  analytics.setCursor(m);
}

async function goMonth(i) {
  const n = state.months.length;
  if (!n) return;
  state.monthIdx = (i + n) % n;
  $('#tb-range').value = state.monthIdx;
  updateMonthLabel();
  view.prefetch(state.months[(state.monthIdx + 1) % n]);
  await view.setMonth(state.months[state.monthIdx]);
}

function togglePlay() {
  if (state.playing) { stopPlay(); return; }
  if (state.monthIdx >= state.months.length - 1) goMonth(0);
  $('#tb-play').textContent = '❚❚'; $('#tb-play').title = 'Pause';
  state.playing = setInterval(() => goMonth(state.monthIdx + 1), 1100);
}
function stopPlay() {
  clearInterval(state.playing); state.playing = null;
  $('#tb-play').textContent = '▶'; $('#tb-play').title = 'Play';
}

$('#tb-range').addEventListener('input', (e) => { stopPlay(); goMonth(+e.target.value); });
$('#tb-prev').addEventListener('click', () => { stopPlay(); goMonth(state.monthIdx - 1); });
$('#tb-next').addEventListener('click', () => { stopPlay(); goMonth(state.monthIdx + 1); });
$('#tb-play').addEventListener('click', togglePlay);
document.addEventListener('keydown', (e) => {
  if (e.target.matches('input[type=search], input[type=text]')) return;
  if (e.key === 'Escape' && drawer.active) { drawer.cancel(); return; }
  if (e.key === 'Escape') { closeInfo(); $$('.modal').forEach((m) => (m.hidden = true)); }
  if (!state.aoi) return;
  if (e.key === 'ArrowRight') { stopPlay(); goMonth(state.monthIdx + 1); }
  if (e.key === 'ArrowLeft') { stopPlay(); goMonth(state.monthIdx - 1); }
});

// ------------------------------------------------------------------ info panel
function openInfo() {
  $('#infopanel').hidden = false;
  document.body.classList.add('info-open');
  $('#infopanel .ip-close')?.addEventListener('click', closeInfo);
  setTimeout(() => analytics.resizeAll(), 50);
}
function closeInfo() {
  $('#infopanel').hidden = true;
  document.body.classList.remove('info-open');
  timelapse.close();
  view.selectHotspot(null);
  setTimeout(() => analytics.resizeAll(), 50);
}

function showHotspot(f) {
  timelapse.close();
  const id = f.properties.id ?? f.properties.label;
  view.selectHotspot(id);
  renderHotspot($('#infopanel'), f, {
    bundle: state.bundle,
    warning: state.aoi?.warning,
    onZoom: () => {
      const r = f.geometry.coordinates[0];
      const xs = r.map((c) => c[0]), ys = r.map((c) => c[1]);
      const pad = 0.004;
      flyToBox(viewer, [Math.min(...xs) - pad, Math.min(...ys) - pad, Math.max(...xs) + pad, Math.max(...ys) + pad], { duration: 1.6, pitchDeg: -55 });
    },
    onExport: () => exportGeoJSON([{ aoi: state.aoi, hotspots: { features: [f] } }], state.index, `careew_${state.aoi.key}_${f.properties.label}`),
  });
  openInfo();
  timelapse.open($('#infopanel .ip-body'), { feature: f, bundle: state.bundle, aoi: state.aoi });
}

// ------------------------------------------------------------------ globe picking
const handler = new C.ScreenSpaceEventHandler(viewer.scene.canvas);
handler.setInputAction((click) => {
  if (drawer.busy()) return;               // the click belonged to box drawing
  const picked = viewer.scene.pick(click.position);
  const tag = picked?.id?.careew;
  if (tag?.type === 'aoi') { if (tag.key !== state.aoi?.key) enterAoi(tag.key); return; }
  if (tag?.type === 'hotspot') { showHotspot(tag.feature); return; }
  if (tag?.type === 'station') { timelapse.close(); renderStation($('#infopanel'), tag.station, { bundle: state.bundle }); openInfo(); return; }
  const cart = viewer.camera.pickEllipsoid(click.position);
  if (!cart) return;
  const c = C.Cartographic.fromCartesian(cart);
  const lon = C.Math.toDegrees(c.longitude), lat = C.Math.toDegrees(c.latitude);
  if (state.aoi && view.contains(lon, lat)) { inspectPixel(lon, lat); return; }
  if (tag?.type === 'river') { timelapse.close(); renderRiver($('#infopanel'), tag.props, { bundle: state.bundle }); openInfo(); return; }
  // clicking inside another AOI's box from the globe view opens it
  const hit = (state.index?.aois || []).find((a) => lon >= a.bbox[0] && lon <= a.bbox[2] && lat >= a.bbox[1] && lat <= a.bbox[3]);
  if (hit && hit.key !== state.aoi?.key) enterAoi(hit.key);
}, C.ScreenSpaceEventType.LEFT_CLICK);

// pointer cursor over clickable things
handler.setInputAction((m) => {
  const p = viewer.scene.pick(m.endPosition);
  viewer.scene.canvas.style.cursor = p?.id?.careew ? 'pointer' : (state.aoi ? 'crosshair' : 'grab');
}, C.ScreenSpaceEventType.MOUSE_MOVE);

// ------------------------------------------------------------------ pixel inspector
function resetPixelPane() {
  $('#px-empty').hidden = false;
  $('#px-info').hidden = true;
  $('#px-charts').hidden = true;
  analytics.destroy('px');
}

async function inspectPixel(lon, lat) {
  const aoi = state.aoi;
  view.markPixel(lon, lat);
  openAnalytics(true);
  selectTab('px');
  $('#px-empty').hidden = false;
  $('#px-empty').textContent = `Loading pixel ${lat.toFixed(5)}, ${lon.toFixed(5)} …`;
  try {
    const px = await fetchPixel(aoi.key, lon, lat);
    if (state.aoi !== aoi) return;
    $('#px-empty').hidden = true;
    $('#px-info').hidden = false;
    $('#px-charts').hidden = false;
    $('#px-info').innerHTML = `<span class="mono">${lat.toFixed(5)}, ${lon.toFixed(5)}</span>
      <span>row ${px.row ?? '–'} · col ${px.col ?? '–'}</span>
      <span>land cover <b class="cap">${esc(px.landcover ?? '–')}</b></span>
      <span>label onsets <b>${(px.label_onsets || []).length ? esc(px.label_onsets.join(', ')) : 'none'}</b></span>
      ${px.mock ? '<span class="badge mock sm">MOCK pixel series</span>' : ''}`;
    analytics.renderPixel(px);
  } catch (e) {
    $('#px-empty').textContent = `No data for this pixel: ${e.message}.`;
    $('#px-info').hidden = true; $('#px-charts').hidden = true;
  }
}

// ------------------------------------------------------------------ analytics drawer
function openAnalytics(open) {
  $('#analytics').classList.toggle('collapsed', !open);
  $('#an-toggle').textContent = open ? '▾' : '▴';
  setTimeout(() => analytics.resizeAll(), 260);
}
function selectTab(name) {
  $$('#analytics .tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  $$('#analytics .tabpane').forEach((p) => p.classList.toggle('active', p.dataset.pane === name));
  setTimeout(() => analytics.resizeAll(), 20);
}
$$('#analytics .tab').forEach((t) => t.addEventListener('click', () => { selectTab(t.dataset.tab); openAnalytics(true); }));
$('#an-toggle').addEventListener('click', () => openAnalytics($('#analytics').classList.contains('collapsed')));

// ------------------------------------------------------------------ layer controls
$$('[data-toggle]').forEach((cb) => cb.addEventListener('change', () => {
  const what = cb.dataset.toggle;
  if (what === 'labels') basemaps.setLabelsVisible(cb.checked);
  else view.setVisible(what, cb.checked);
  refreshLegend();
}));
$$('[data-alpha]').forEach((r) => r.addEventListener('input', () => view.setAlpha(r.dataset.alpha, +r.value)));
$('#base-layer').addEventListener('change', async (e) => {
  await basemaps.set(e.target.value);
  $('#attribution').innerHTML = ATTRIBUTION_HTML + (e.target.value === 'osm' ? ' · ' + OSM_ATTRIBUTION : '');
});

// ------------------------------------------------------------------ top bar
$('#btn-home').addEventListener('click', exitAoi);
$('#brand').addEventListener('click', (e) => { e.preventDefault(); exitAoi(); });
$('#crumbs [data-home]').addEventListener('click', (e) => { e.preventDefault(); exitAoi(); });
$('#aoi-search').addEventListener('input', refreshList);
$('#aoi-search').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { const first = $('#aoi-list .aoi-card'); if (first) first.click(); }
});
$('#zoom-in').addEventListener('click', () => viewer.camera.zoomIn(viewer.camera.positionCartographic.height * 0.4));
$('#zoom-out').addEventListener('click', () => viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.6));

$('#btn-model').addEventListener('click', async () => {
  $('#modal-model').hidden = false;
  $('#model-card').innerHTML = '<p class="muted">Loading…</p>';
  renderModelCard($('#model-card'), await loadMetrics(), state.index);
});
$('#link-about').addEventListener('click', (e) => { e.preventDefault(); $('#modal-about').hidden = false; });
$$('.modal').forEach((m) => m.addEventListener('click', (e) => { if (e.target === m || e.target.closest('[data-close]')) m.hidden = true; }));

const menu = $('#export-menu');
$('#btn-export').addEventListener('click', (e) => {
  e.stopPropagation();
  menu.hidden = !menu.hidden;
  $('#btn-export').setAttribute('aria-expanded', String(!menu.hidden));
});
document.addEventListener('click', () => { menu.hidden = true; });
menu.querySelectorAll('button').forEach((b) => b.addEventListener('click', async () => {
  const groups = [];
  if (state.aoi) groups.push({ aoi: state.aoi, hotspots: state.bundle?.hotspots });
  else for (const a of state.index?.aois || []) groups.push({ aoi: a, hotspots: (await loadAoiBundle(a.key)).hotspots });
  const n = groups.reduce((s, g) => s + (g.hotspots?.features?.length || 0), 0);
  if (!n) { toast('No hotspots to export.'); return; }
  const name = `careew_hotspots_${state.aoi ? state.aoi.key : 'all'}_${state.index?.latest_month || ''}`;
  (b.dataset.fmt === 'csv' ? exportCSV : exportGeoJSON)(groups, state.index, name);
  toast(`Exported ${n} hotspot${n > 1 ? 's' : ''} as ${b.dataset.fmt.toUpperCase()}.`);
}));

$('#legend .lg-toggle').addEventListener('click', () => {
  const lg = $('#legend'); lg.classList.toggle('closed');
  $('#legend .lg-toggle').setAttribute('aria-expanded', String(!lg.classList.contains('closed')));
});

// responsive sidebar
$('#btn-menu').addEventListener('click', () => document.body.classList.toggle('side-open'));
function closeSidebarIfNarrow() { if (window.innerWidth < 900) document.body.classList.remove('side-open'); }
window.addEventListener('resize', () => analytics.resizeAll());

// hooks for the automated UI smoke test (app/ui_screenshots.py)
window.__careewViewer = viewer;
window.__careewTest = {
  openFirstHotspot: () => { const f = state.bundle?.hotspots?.features?.[0]; if (f) showHotspot(f); },
  closeInfo,
  inspectCenter: () => state.aoi && inspectPixel(state.aoi.center[0] - 0.006, state.aoi.center[1] - 0.004),
  drawing: () => drawer.active,
  drawnBox: () => drawer.bbox,
  activeAoi: () => state.aoi?.key ?? null,
  timelapse,
  showHotspotByLabel: (l) => { const f = state.bundle?.hotspots?.features?.find((x) => x.properties.label === l); if (f) showHotspot(f); return !!f; },
  overlaysShown: () => view.rasterKinds.filter((k) => view.raster[k].layer && view.raster[k].layer.show),
};

if (window.innerWidth < 900) $('#legend').classList.add('closed');
boot();
