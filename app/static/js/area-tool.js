// On-demand analysis: draw a box anywhere (or type coordinates) -> /api/plan -> /api/analyze,
// then follow the pipeline job via /api/jobs/{id} until the new area appears in aois.json.
/* global Cesium */
import { api, esc, fmt } from './data.js';

const C = Cesium;
const color = (css, a = 1) => C.Color.fromCssColorString(css).withAlpha(a);
const NO_DEPTH = Number.POSITIVE_INFINITY;

export const STAGES = [
  ['grid', 'Grid', 'Snap to 5.12 km Sentinel-2 blocks'],
  ['static', 'Static layers', 'Land cover, terrain, masks'],
  ['climate', 'Climate', 'ERA5-Land rainfall, temperature, soil moisture'],
  ['sentinel2', 'Sentinel-2', 'Monthly composites 2017 → now (longest step)'],
  ['modis', 'MODIS', 'Long-term NDVI context'],
  ['rivers', 'Rivers', 'HydroRIVERS network & discharge'],
  ['features', 'Features', 'Climate-conditioned residuals'],
  ['predict', 'Predict', 'Trained model → monthly risk'],
  ['export', 'Export', 'Maps, hotspots and charts'],
];

/** Box size in km (east-west, north-south) of [w, s, e, n]. */
export function boxKm([w, s, e, n]) {
  const lat = (s + n) / 2;
  return [(e - w) * 111.32 * Math.cos((lat * Math.PI) / 180), (n - s) * 110.574];
}
const fmtBounds = (b) => b.map((v) => v.toFixed(5));
const fmtDur = (sec) => {
  if (!isFinite(sec) || sec < 0) return '–';
  const m = Math.round(sec / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
};

// ------------------------------------------------------------------ rectangle drawing on the globe
export class BoxDrawer {
  constructor(viewer) {
    this.viewer = viewer;
    this.ds = new C.CustomDataSource('drawbox');
    viewer.dataSources.add(this.ds);
    this.active = false;
    this.bbox = null;          // [w, s, e, n] currently shown
    this.lastEnd = 0;          // time the last drawing ended (to swallow the click that ended it)
    this.handler = null;
    this.jobBoxes = new Map();
    this._makeEntities();
  }

  _makeEntities() {
    const rect = () => (this.bbox ? C.Rectangle.fromDegrees(...this.bbox) : C.Rectangle.fromDegrees(0, 0, 0.0001, 0.0001));
    const ring = () => {
      if (!this.bbox) return [];
      const [w, s, e, n] = this.bbox;
      return C.Cartesian3.fromDegreesArrayHeights([w, s, 10, e, s, 10, e, n, 10, w, n, 10, w, s, 10]);
    };
    this.fill = this.ds.entities.add({
      show: false,
      rectangle: { coordinates: new C.CallbackProperty(rect, false), height: 4, material: color('#00e5ff', 0.13) },
    });
    this.outline = this.ds.entities.add({
      show: false,
      polyline: {
        positions: new C.CallbackProperty(ring, false), width: 2.5,
        material: new C.PolylineDashMaterialProperty({ color: color('#ffffff'), gapColor: color('#000000', 0.35), dashLength: 14 }),
      },
    });
    this.label = this.ds.entities.add({
      show: false,
      position: new C.CallbackProperty(() => {
        if (!this.bbox) return C.Cartesian3.ZERO;
        const [w, , e, n] = this.bbox;
        return C.Cartesian3.fromDegrees((w + e) / 2, n, 12);
      }, false),
      label: {
        text: new C.CallbackProperty(() => {
          if (!this.bbox) return '';
          const [kw, kh] = boxKm(this.bbox);
          return `${kw.toFixed(2)} × ${kh.toFixed(2)} km`;
        }, false),
        font: '600 13px Inter, system-ui, sans-serif', fillColor: color('#03141c'), showBackground: true,
        backgroundColor: color('#00e5ff', 0.92), backgroundPadding: new C.Cartesian2(8, 4),
        verticalOrigin: C.VerticalOrigin.BOTTOM, pixelOffset: new C.Cartesian2(0, -6), disableDepthTestDistance: NO_DEPTH,
      },
    });
  }

  _show(v) { [this.fill, this.outline, this.label].forEach((e) => (e.show = v)); }

  show(bbox) { this.bbox = bbox; this._show(true); }

  clear() { this.bbox = null; this._show(false); }

  _pick(pos) {
    const p = this.viewer.camera.pickEllipsoid(pos);
    if (!p) return null;
    const c = C.Cartographic.fromCartesian(p);
    return [C.Math.toDegrees(c.longitude), C.Math.toDegrees(c.latitude)];
  }

  _set(a, b) {
    this.bbox = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
    this._show(true);
  }

  _camera(enabled) {
    const ssc = this.viewer.scene.screenSpaceCameraController;
    // zoom stays enabled while drawing; dragging draws instead of rotating the globe
    ssc.enableRotate = ssc.enableTranslate = ssc.enableTilt = ssc.enableLook = enabled;
  }

  /** Enter drawing mode. Drag a rectangle, or click one corner then the opposite corner. */
  start({ onDone, onCancel } = {}) {
    this.stop();
    this.active = true;
    this.onDone = onDone; this.onCancel = onCancel;
    this.clear();
    this._camera(false);
    const canvas = this.viewer.scene.canvas;
    canvas.classList.add('drawing');
    document.body.classList.add('drawing-mode');
    const h = (this.handler = new C.ScreenSpaceEventHandler(canvas));
    let a = null, down = null, clickMode = false;
    const finish = (b) => {
      if (!b) return;
      this._set(a, b);
      const [kw, kh] = boxKm(this.bbox);
      if (kw < 0.05 || kh < 0.05) { clickMode = true; return; }   // degenerate: keep waiting for a 2nd corner
      const box = this.bbox;
      this.stop();
      this.onDone?.(box);
    };
    h.setInputAction((e) => {
      if (clickMode) return;
      a = this._pick(e.position);
      down = e.position.clone();
    }, C.ScreenSpaceEventType.LEFT_DOWN);
    h.setInputAction((e) => {
      if (!a) return;
      const b = this._pick(e.endPosition);
      if (b) this._set(a, b);
    }, C.ScreenSpaceEventType.MOUSE_MOVE);
    h.setInputAction((e) => {
      if (!a) return;
      const moved = C.Cartesian2.distance(down, e.position) > 6;
      if (clickMode || moved) finish(this._pick(e.position));
      else clickMode = true;                                          // first corner placed by a click
    }, C.ScreenSpaceEventType.LEFT_UP);
  }

  /** Leave drawing mode (keeps the drawn box visible). */
  stop() {
    if (!this.active) return;
    this.active = false;
    this.lastEnd = performance.now();
    this.handler?.destroy(); this.handler = null;
    this._camera(true);
    this.viewer.scene.canvas.classList.remove('drawing');
    document.body.classList.remove('drawing-mode');
  }

  cancel() {
    if (!this.active) return;
    this.stop();
    this.clear();
    this.onCancel?.();
  }

  /** True while a click should be ignored by the normal picking handler. */
  busy() { return this.active || performance.now() - this.lastEnd < 400; }

  /** Dashed boxes of running jobs (so the user sees what is being analysed). */
  setJobBoxes(jobs) {
    const keep = new Set(jobs.map((j) => j.id));
    for (const [id, ents] of this.jobBoxes) if (!keep.has(id)) { ents.forEach((e) => this.ds.entities.remove(e)); this.jobBoxes.delete(id); }
    for (const j of jobs) {
      if (this.jobBoxes.has(j.id) || !Array.isArray(j.bbox)) continue;
      const [w, s, e, n] = j.bbox;
      this.jobBoxes.set(j.id, [
        this.ds.entities.add({ polyline: {
          positions: C.Cartesian3.fromDegreesArrayHeights([w, s, 9, e, s, 9, e, n, 9, w, n, 9, w, s, 9]), width: 2.5,
          material: new C.PolylineDashMaterialProperty({ color: color('#ffd60a'), gapColor: color('#000000', 0.35), dashLength: 14 }) } }),
        this.ds.entities.add({ position: C.Cartesian3.fromDegrees((w + e) / 2, n, 12), label: {
          text: `Analysing · ${j.name || 'area'}`, font: '600 12px Inter, system-ui, sans-serif', fillColor: color('#1a1405'),
          showBackground: true, backgroundColor: color('#ffd60a', 0.92), backgroundPadding: new C.Cartesian2(7, 4),
          verticalOrigin: C.VerticalOrigin.BOTTOM, pixelOffset: new C.Cartesian2(0, -6), disableDepthTestDistance: NO_DEPTH } }),
      ]);
    }
  }
}

// ------------------------------------------------------------------ analyse panel (draw / coordinates -> plan -> run)
export class AnalysePanel {
  constructor(root, { drawer, onFly, onStarted, toast }) {
    this.root = root;
    this.drawer = drawer;
    this.onFly = onFly;
    this.onStarted = onStarted;
    this.toast = toast;
    this.bbox = null;
    this.plan = null;
    this.planToken = 0;
    const $ = (s) => root.querySelector(s);
    this.$ = $;

    $('#ap-close').addEventListener('click', () => this.close());
    $('#ap-redraw').addEventListener('click', () => this.draw());
    root.querySelectorAll('.ap-tabs button').forEach((b) => b.addEventListener('click', () => this.mode(b.dataset.mode)));
    root.querySelectorAll('input[name=ap-cmode]').forEach((r) => r.addEventListener('change', () => {
      const centre = root.querySelector('input[name=ap-cmode]:checked').value === 'centre';
      $('#ap-centre').hidden = !centre; $('#ap-bounds').hidden = centre;
    }));
    $('#ap-coords').addEventListener('submit', (e) => { e.preventDefault(); this.fromCoords(); });
    $('#ap-run').addEventListener('click', () => this.run());
    $('#ap-name').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !$('#ap-run').disabled) this.run(); });
  }

  get isOpen() { return !this.root.hidden; }

  open(mode = 'draw') {
    this.root.hidden = false;
    document.body.classList.add('analyse-open');
    this.mode(mode);
  }

  close() {
    this.drawer.cancel();
    this.drawer.clear();
    this.root.hidden = true;
    document.body.classList.remove('analyse-open');
    this.bbox = null; this.plan = null;
    this.$('#ap-summary').hidden = true;
  }

  mode(m) {
    this.root.querySelectorAll('.ap-tabs button').forEach((b) => b.classList.toggle('active', b.dataset.mode === m));
    this.$('[data-pane=draw]').hidden = m !== 'draw';
    this.$('[data-pane=coords]').hidden = m !== 'coords';
    if (m === 'draw') this.draw();
    else this.drawer.cancel();
  }

  draw() {
    this.$('#ap-draw-state').innerHTML = '<span class="pulse"></span> Drawing — drag a rectangle on the globe, or click two opposite corners. <kbd>Esc</kbd> cancels, scroll to zoom.';
    this.$('#ap-draw-state').classList.add('live');
    this.drawer.start({
      onDone: (b) => { this.$('#ap-draw-state').classList.remove('live'); this.$('#ap-draw-state').textContent = 'Box drawn. Adjust by drawing again.'; this.setBox(b); },
      onCancel: () => { this.$('#ap-draw-state').classList.remove('live'); this.$('#ap-draw-state').textContent = 'Drawing cancelled.'; },
    });
  }

  /** Read the coordinate form, validate, preview and plan. */
  fromCoords() {
    const v = (id) => parseFloat(this.$(id).value);
    const err = this.$('#ap-coord-err');
    err.textContent = '';
    let b;
    if (this.root.querySelector('input[name=ap-cmode]:checked').value === 'centre') {
      const lon = v('#ap-lon'), lat = v('#ap-lat'), km = v('#ap-size');
      if (![lon, lat, km].every(isFinite)) { err.textContent = 'Enter numeric longitude, latitude and size.'; return; }
      if (Math.abs(lat) > 85 || Math.abs(lon) > 180) { err.textContent = 'Longitude must be −180…180 and latitude −85…85.'; return; }
      if (km <= 0 || km > 20) { err.textContent = 'Size must be between 0.2 and ~10 km.'; return; }
      const dlat = km / 2 / 110.574, dlon = km / 2 / (111.32 * Math.cos((lat * Math.PI) / 180));
      b = [lon - dlon, lat - dlat, lon + dlon, lat + dlat];
    } else {
      b = ['#ap-w', '#ap-s', '#ap-e', '#ap-n'].map(v);
      if (!b.every(isFinite)) { err.textContent = 'Enter all four bounds as decimal degrees.'; return; }
      if (!(b[0] < b[2] && b[1] < b[3])) { err.textContent = 'West must be < East and South < North.'; return; }
    }
    this.drawer.show(b);
    this.onFly?.(b);
    this.setBox(b);
  }

  setBox(b) {
    this.bbox = b;
    const [kw, kh] = boxKm(b);
    const f = fmtBounds(b);
    this.$('#ap-summary').hidden = false;
    this.$('#ap-size-out').textContent = `${kw.toFixed(2)} × ${kh.toFixed(2)} km  (${(kw * kh).toFixed(1)} km²)`;
    this.$('#ap-bounds-out').innerHTML = `W ${f[0]} · S ${f[1]}<br>E ${f[2]} · N ${f[3]}`;
    // keep the coordinate form in sync with the drawn box
    ['#ap-w', '#ap-s', '#ap-e', '#ap-n'].forEach((id, i) => (this.$(id).value = b[i].toFixed(5)));
    this.$('#ap-lon').value = ((b[0] + b[2]) / 2).toFixed(5);
    this.$('#ap-lat').value = ((b[1] + b[3]) / 2).toFixed(5);
    this.$('#ap-size').value = Math.max(kw, kh).toFixed(2);
    this.requestPlan();
  }

  async requestPlan() {
    const token = ++this.planToken;
    const out = this.$('#ap-plan');
    const run = this.$('#ap-run');
    this.plan = null;
    run.disabled = true;
    out.className = 'plan pending';
    out.innerHTML = '<span class="spin"></span> Checking Sentinel-2 coverage…';
    try {
      const p = await api('api/plan', { method: 'POST', body: { bbox: this.bbox, name: this.name() } });
      if (token !== this.planToken) return;
      this.plan = p;
      out.className = 'plan ok';
      out.innerHTML = `<div class="plan-main"><b>${p.blocks}</b> Sentinel-2 block${p.blocks > 1 ? 's' : ''} · <b>~${p.estimate_minutes}</b> min · tile <b class="mono">${esc(p.tile)}</b></div>
        <div class="muted small">Analysed area ${fmt(p.analysed_km2, 1)} km² (whole 5.12 km blocks covering your ${fmt(p.box_km?.[0], 2)} × ${fmt(p.box_km?.[1], 2)} km box). Downloads every Sentinel-2 month since 2017.</div>`;
      run.disabled = false;
    } catch (e) {
      if (token !== this.planToken) return;
      out.className = 'plan err';
      out.innerHTML = `<b>Cannot analyse this box.</b> ${esc(e.message)}<div class="hint">${esc(suggestion(e.message))}</div>`;
    }
  }

  name() { return (this.$('#ap-name').value || 'My area').trim().slice(0, 40) || 'My area'; }

  async run() {
    if (!this.bbox || !this.plan) return;
    const btn = this.$('#ap-run');
    btn.disabled = true; btn.textContent = 'Starting…';
    try {
      const r = await api('api/analyze', { method: 'POST', body: { bbox: this.bbox, name: this.name() } });
      try { localStorage.setItem(`careew-est-${r.job}`, String(this.plan.estimate_minutes)); } catch { /* storage unavailable */ }
      this.toast(`Analysis started: ${this.name()} (~${this.plan.estimate_minutes} min). Follow it in Jobs.`);
      this.close();
      this.onStarted?.(r.job);
    } catch (e) {
      const out = this.$('#ap-plan');
      out.className = 'plan err';
      out.innerHTML = `<b>${e.status === 409 ? 'Another analysis is running.' : 'Could not start.'}</b> ${esc(e.message)}${e.status === 409 ? '<div class="hint">Only one analysis runs at a time. Open Jobs to follow it, then try again.</div>' : ''}`;
    } finally {
      btn.textContent = '▶ Run analysis';
      btn.disabled = !this.plan;
    }
  }
}

function suggestion(msg) {
  const m = (msg || '').toLowerCase();
  if (/maximum|too big|blocks/.test(m)) return 'Draw a smaller box: at most ~10 × 10 km (4 Sentinel-2 blocks of 5.12 km). A single 5 × 5 km box is fastest.';
  if (/small/.test(m)) return 'Draw a larger box (at least 200 m on each side).';
  if (/invalid|coverage|60s|75n/.test(m)) return 'Sentinel-2 covers land between about 60°S and 75°N. Check the coordinates.';
  if (/ocean|no tile|tile|plan/.test(m)) return 'No usable Sentinel-2 land tile was found here. Try a box over land.';
  return 'Adjust the box and try again.';
}

// ------------------------------------------------------------------ jobs panel + polling
export class JobsPanel {
  constructor(root, badgeBtn, { onFinished, onOpenKey, onRunning, toast }) {
    this.root = root;
    this.btn = badgeBtn;
    this.onFinished = onFinished;
    this.onOpenKey = onOpenKey;
    this.onRunning = onRunning;
    this.toast = toast;
    this.list = [];
    this.job = null;           // full record of the job being shown
    this.watchId = null;
    this.prevStatus = {};
    this.timer = null;
    root.querySelector('#jp-close').addEventListener('click', () => this.toggle(false));
    badgeBtn.addEventListener('click', () => this.toggle());
    setInterval(() => this.refresh(), 30000);   // pick up jobs started elsewhere
    setInterval(() => this.render(), 1000 * 15);  // keep elapsed time fresh
  }

  toggle(v = this.root.hidden) {
    this.root.hidden = !v;
    this.btn.setAttribute('aria-expanded', String(v));
    if (v) this.render();
  }

  async refresh() {
    try { this.list = await api('api/jobs'); } catch (e) { console.warn('[jobs] list failed', e.message); return; }
    for (const j of this.list) if (!(j.id in this.prevStatus)) this.prevStatus[j.id] = j.status;
    const running = this.list.filter((j) => j.status === 'running');
    this.onRunning?.(running);
    if (running.length && this.watchId !== running[0].id) this.watch(running[0].id);
    else if (!this.watchId && this.list.length) this.watch(this.list[0].id, { once: true });
    this.render();
  }

  /** Show one job; poll every 5 s while it runs. */
  watch(id, { once = false } = {}) {
    this.watchId = id;
    clearInterval(this.timer); this.timer = null;
    this.poll();
    if (!once) this.timer = setInterval(() => this.poll(), 5000);
  }

  async poll() {
    const id = this.watchId;
    if (!id) return;
    let j;
    try { j = await api(`api/jobs/${encodeURIComponent(id)}`); } catch (e) {
      if (e.status === 404) { clearInterval(this.timer); this.timer = null; this.job = null; this.watchId = null; this.render(); }
      return;
    }
    if (id !== this.watchId) return;
    const was = this.prevStatus[id];
    this.prevStatus[id] = j.status;
    this.job = j;
    const row = this.list.find((x) => x.id === id);
    if (row) Object.assign(row, j); else this.list.unshift(j);
    if (j.status !== 'running') {
      clearInterval(this.timer); this.timer = null;
      this.onRunning?.(this.list.filter((x) => x.status === 'running'));
      if (was === 'running' && j.status === 'done') this.onFinished?.(j);
      if (was === 'running' && j.status === 'error') { this.toast(`Analysis “${j.name}” failed: ${j.error || 'see Jobs'}`, 8000); this.toggle(true); }
    } else {
      this.onRunning?.(this.list.filter((x) => x.status === 'running'));
    }
    this.render();
  }

  render() {
    const running = this.list.find((j) => j.status === 'running');
    // top-bar badge
    const badge = this.btn.querySelector('.jobs-badge');
    if (running) {
      const p = this.job && this.job.id === running.id ? this.job.progress : running.progress;
      badge.innerHTML = `<span class="spin"></span>${Math.round((p || 0) * 100)}%`;
      badge.hidden = false;
      this.btn.classList.add('running');
    } else {
      badge.textContent = this.list.length ? String(this.list.length) : '';
      badge.hidden = !this.list.length;
      this.btn.classList.remove('running');
    }
    if (this.root.hidden) return;
    const body = this.root.querySelector('.jp-body');
    const j = this.job;
    const cur = j ? jobCard(j) : '<p class="muted">No analyses yet. Use <b>✎ Draw box</b> to analyse any place on Earth.</p>';
    const others = this.list.filter((x) => !j || x.id !== j.id);
    body.innerHTML = cur + (others.length ? `<h4>Previous analyses</h4><ul class="jp-list">${others.map((x) => `
      <li data-id="${esc(x.id)}" tabindex="0" role="button">
        <span class="st st-${esc(x.status)}">${x.status === 'running' ? '<span class="spin"></span>' : x.status === 'done' ? '✓' : '✕'}</span>
        <span class="nm">${esc(x.name || x.id)}</span>
        <span class="muted small">${x.started ? new Date(x.started * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : ''}</span>
      </li>`).join('')}</ul>` : '');
    body.querySelectorAll('.jp-list li').forEach((li) => li.addEventListener('click', () => {
      const x = this.list.find((y) => y.id === li.dataset.id);
      this.watch(li.dataset.id, { once: x?.status !== 'running' });
    }));
    body.querySelectorAll('[data-open]').forEach((b) => b.addEventListener('click', () => this.onOpenKey?.(b.dataset.open)));
  }
}

function jobCard(j) {
  const now = Date.now() / 1000;
  const elapsed = (j.finished || (j.status === 'running' ? now : j.updated || now)) - (j.started || now);
  const p = Math.max(0, Math.min(1, j.progress || 0));
  let eta = '';
  if (j.status === 'running') {
    let est = null;
    try { est = parseFloat(localStorage.getItem(`careew-est-${j.id}`)); } catch { /* ignore */ }
    if (p > 0.05) eta = `~${fmtDur((elapsed * (1 - p)) / p)} left`;
    else if (isFinite(est)) eta = `~${fmtDur(est * 60 - elapsed)} left (estimate)`;
    else eta = 'estimating…';
  }
  const stale = j.status === 'running' && j.updated && now - j.updated > 900;
  const idx = STAGES.findIndex(([k]) => k === j.stage);
  const steps = STAGES.map(([k, label, hint], i) => {
    let cls = 'todo';
    if (j.status === 'done' || i < idx) cls = 'done';
    else if (i === idx) cls = j.status === 'error' ? 'fail' : 'now';
    const icon = cls === 'done' ? '✓' : cls === 'now' ? '<span class="spin"></span>' : cls === 'fail' ? '✕' : i + 1;
    return `<li class="${cls}" title="${esc(hint)}"><i>${icon}</i><span>${label}</span></li>`;
  }).join('');
  const msgs = (j.messages || []).slice(-10);
  const st = j.status || 'running';
  return `
    <div class="jp-card st-${esc(st)}">
      <div class="jp-title">
        <div><div class="ip-kicker">Analysis · ${esc(j.id)}</div><h3>${esc(j.name || 'Area')}</h3></div>
        <span class="status-pill st-${esc(st)}">${st === 'running' ? 'Running' : st === 'done' ? 'Done' : 'Error'}</span>
      </div>
      ${Array.isArray(j.bbox) ? `<div class="mono small muted">${fmtBounds(j.bbox).join(', ')}</div>` : ''}
      <div class="jp-progress"><i style="width:${(p * 100).toFixed(1)}%"></i></div>
      <div class="jp-meta"><span><b>${Math.round(p * 100)}%</b> · ${esc(stageLabel(j.stage))}</span><span>elapsed ${fmtDur(elapsed)}${eta ? ' · ' + eta : ''}</span></div>
      ${j.detail && st === 'running' ? `<div class="jp-detail">${esc(j.detail)}</div>` : ''}
      ${stale ? '<div class="note warn small">No progress reported for over 15 minutes – the job may have stopped.</div>' : ''}
      ${st === 'error' ? `<div class="note err"><b>Error:</b> ${esc(j.error || 'unknown error')}</div>` : ''}
      <ol class="jp-steps">${steps}</ol>
      ${st === 'done' && (j.keys || []).length ? `<div class="jp-open">${j.keys.map((k) => `<button class="btn primary" data-open="${esc(k)}">Open ${esc(k)}</button>`).join('')}</div>` : ''}
      ${msgs.length ? `<details class="jp-log" ${st !== 'done' ? 'open' : ''}><summary>Log (last ${msgs.length})</summary><pre>${msgs.map(esc).join('\n')}</pre></details>` : ''}
    </div>`;
}

function stageLabel(s) {
  const f = STAGES.find(([k]) => k === s);
  return f ? f[1] : s === 'done' ? 'finished' : s || 'starting';
}
