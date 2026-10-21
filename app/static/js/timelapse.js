// Sentinel-2 true-colour time-lapse clipped to ONE hotspot box.
//
// The AOI's monthly RGB overlays (aois/<key>/rgb/<YYYY-MM>.png, listed in meta.months_rgb) cover the whole AOI
// bbox; each frame is shown through an ImageryLayer whose `rectangle` is the hotspot box, so nothing outside the
// block is drawn. Frames are fetched with trackedFetch (global progress bar), cached as blob URLs, prefetched
// one step ahead, and cross-faded (two layers) so playback does not flicker.
/* global Cesium */
import { esc } from './data.js';
import { trackedFetch } from './progress.js';
import { flyToBox } from './globe.js';

const C = Cesium;
const FRAME_MS = 670;          // ~1.5 frames per second
const FADE_MS = 260;
const CACHE_MAX = 30;          // decoded frames kept in memory

const monthIdx = (m) => { const [y, mo] = m.split('-').map(Number); return y * 12 + mo - 1; };
const idxMonth = (i) => `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`;

export class HotspotTimelapse {
  constructor(viewer, { basemaps, view }) {
    this.viewer = viewer;
    this.basemaps = basemaps;
    this.view = view;
    this.ds = new C.CustomDataSource('timelapse-frame');
    viewer.dataSources.add(this.ds);
    this.cache = new Map();        // url -> Promise<provider>
    this.blobUrls = new Map();     // url -> blob: URL (revoked on eviction)
    this.layer = null;             // layer currently shown
    this.active = false;
    this.token = 0;
    this.timer = null;
  }

  // ---------------------------------------------------------------- lifecycle
  /** Attach to a hotspot shown in `host` (the hotspot panel body). */
  open(host, { feature, bundle, aoi }) {
    this.close();
    const months = bundle?.meta?.months_rgb || [];
    if (!months.length) {
      const note = document.createElement('div');
      note.className = 'note small';
      note.textContent = 'No monthly Sentinel-2 frames (meta.json months_rgb) for this area, so no time-lapse.';
      host.insertBefore(note, host.querySelector(':scope > h3'));
      return;
    }
    const ring = feature.geometry.coordinates[0];
    const xs = ring.map((c) => c[0]), ys = ring.map((c) => c[1]);
    this.box = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    this.feature = feature;
    this.bundle = bundle;
    this.aoi = aoi;
    this.months = months;
    this.id = feature.properties.id ?? feature.properties.label;
    this.i = 0;
    this.sameSeason = false;
    this.el = this.buildUi(host);
    this.setOn(true);
  }

  /** Remove everything and restore the AOI overlays. */
  close() {
    this.pause();
    this.token++;
    this.active = false;
    if (this.layer) { this.viewer.imageryLayers.remove(this.layer, true); this.layer = null; }
    this.ds.entities.removeAll();
    if (this.feature) this.view.setHotspotFill(this.id, true);
    this.view.setSuppressed(false);
    this.feature = null;
    this.el = null;
  }

  setOn(on) {
    if (!this.feature) return;
    this.el?.classList.toggle('off', !on);
    if (!on) {
      this.pause();
      this.token++;
      this.active = false;
      if (this.layer) { this.viewer.imageryLayers.remove(this.layer, true); this.layer = null; }
      this.ds.entities.removeAll();
      this.view.setHotspotFill(this.id, true);
      this.view.setSuppressed(false);
      return;
    }
    this.active = true;
    this.view.setSuppressed(true);           // hide risk / NDVI / RGB overlays so the imagery is visible
    this.view.setHotspotFill(this.id, false);
    this.drawFrame();
    // fit the block with a small margin and a gentle tilt; on narrow screens the panel is a bottom sheet,
    // so extend the box southwards to put the block in the visible upper half of the map
    const [w, s, e, n] = this.box;
    const pad = Math.max(e - w, n - s) * 0.12 + 0.0003;
    const south = window.innerWidth < 900 ? (n - s + 2 * pad) * 1.6 : 0;
    flyToBox(this.viewer, [w - pad, s - pad - south, e + pad, n + pad], { duration: 1.4, pitchDeg: -64 });
    this.show(this.i);
  }

  // ---------------------------------------------------------------- frames
  url(m) { return `${this.bundle.dir}rgb/${m}.png`; }

  provider(m) {
    const url = this.url(m);
    if (!this.cache.has(url)) {
      const [w, s, e, n] = this.aoi.bbox;
      const rect = C.Rectangle.fromDegrees(w, s, e, n);       // the image covers the whole AOI ...
      const p = trackedFetch(url).then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blobUrl = URL.createObjectURL(await r.blob());
        this.blobUrls.set(url, blobUrl);
        return C.SingleTileImageryProvider.fromUrl(blobUrl, { rectangle: rect });
      });
      p.catch(() => this.cache.delete(url));
      this.cache.set(url, p);
      while (this.cache.size > CACHE_MAX) {                    // evict the oldest frame
        const old = this.cache.keys().next().value;
        this.cache.delete(old);
        const b = this.blobUrls.get(old);
        if (b) { URL.revokeObjectURL(b); this.blobUrls.delete(old); }
      }
    }
    return this.cache.get(url);
  }

  async show(i) {
    if (!this.feature) return;
    this.i = Math.max(0, Math.min(this.months.length - 1, i));
    const m = this.months[this.i];
    this.updateUi(m, true);
    if (!this.active) return;
    const token = ++this.token;
    let provider;
    try { provider = await this.provider(m); } catch (e) {
      if (token === this.token) this.updateUi(m, false, `frame ${m} unavailable (${e.message})`);
      return;
    }
    if (token !== this.token || !this.active) return;
    // ... but this layer only draws inside the hotspot rectangle
    const layer = new C.ImageryLayer(provider, { rectangle: C.Rectangle.fromDegrees(...this.box), alpha: this.layer ? 0 : 1 });
    layer.magnificationFilter = C.TextureMagnificationFilter.NEAREST;   // crisp 10 m pixels, no smearing
    const layers = this.viewer.imageryLayers;
    layers.add(layer, this.basemaps.overlayIndex());         // above data overlays, below place labels
    const old = this.layer;
    this.layer = layer;
    if (old) this.fade(layer, old);
    this.updateUi(m, false);
    // prefetch the next frame in the current stepping mode
    const nxt = this.nextIndex(1);
    if (nxt !== this.i) this.provider(this.months[nxt]).catch(() => {});
  }

  fade(layer, old) {
    const t0 = performance.now();
    const tick = () => {
      const k = Math.min(1, (performance.now() - t0) / FADE_MS);
      layer.alpha = k;
      if (k < 1 && this.layer === layer) requestAnimationFrame(tick);
      else this.viewer.imageryLayers.remove(old, true);
    };
    requestAnimationFrame(tick);
  }

  /** Index `dir` steps away; in same-season mode jump to the same calendar month of the next/previous year. */
  nextIndex(dir) {
    const n = this.months.length;
    if (!this.sameSeason) return (this.i + dir + n) % n;
    const cur = monthIdx(this.months[this.i]);
    const mo = cur % 12;
    const same = this.months.map((m, k) => [monthIdx(m), k]).filter(([v]) => v % 12 === mo);
    const pos = same.findIndex(([v]) => v === cur);
    return same[(pos + dir + same.length) % same.length][1];
  }

  step(dir) { this.show(this.nextIndex(dir)); }

  play() {
    if (this.timer) return;
    if (!this.active) { this.el.querySelector('.tl-on').checked = true; this.setOn(true); }
    this.timer = setInterval(() => this.step(1), FRAME_MS);
    this.el?.querySelector('.tl-play')?.replaceChildren('❚❚');
  }

  pause() {
    clearInterval(this.timer); this.timer = null;
    this.el?.querySelector('.tl-play')?.replaceChildren('▶');
  }

  // ---------------------------------------------------------------- bright frame around the block
  drawFrame() {
    this.ds.entities.removeAll();
    const [w, s, e, n] = this.box;
    const ring = C.Cartesian3.fromDegreesArrayHeights([w, s, 7, e, s, 7, e, n, 7, w, n, 7, w, s, 7]);
    this.ds.entities.add({ polyline: { positions: ring, width: 9,
      material: new C.PolylineGlowMaterialProperty({ glowPower: 0.25, color: C.Color.fromCssColorString('#00e5ff') }) } });
    this.ds.entities.add({ polyline: { positions: ring, width: 2, material: C.Color.WHITE } });
  }

  // ---------------------------------------------------------------- panel UI
  buildUi(host) {
    const p = this.feature.properties;
    const M = this.months, n = M.length;
    const latest = M[n - 1];
    // context markers (shown as ticks on the mini slider)
    const marks = [];
    const nearest = (m) => {
      if (!m) return -1;
      const t = monthIdx(m);
      let best = -1, d = 1e9;
      M.forEach((x, k) => { const dd = Math.abs(monthIdx(x) - t); if (dd < d) { d = dd; best = k; } });
      return d <= 2 ? best : -1;
    };
    if (p.first_warning) marks.push({ m: p.first_warning, cls: 'warn', label: 'First warning' });
    if (p.status === 'active_degradation' && p.months_below > 0) {
      const latestMonth = this.bundle.meta?.months_risk?.at(-1) || latest;
      marks.push({ m: idxMonth(monthIdx(latestMonth) - p.months_below + 1), cls: 'onset', label: `Below peers since (${p.months_below} mo)` });
    }
    if (p.chip_before_month) marks.push({ m: p.chip_before_month, cls: 'chip', label: 'Before chip' });
    if (p.chip_after_month) marks.push({ m: p.chip_after_month, cls: 'chip', label: 'After chip' });
    const pos = (k) => (n > 1 ? (k / (n - 1)) * 100 : 0);
    const years = M.map((m, k) => [m, k]).filter(([m], k) => m.endsWith('-01') || k === 0);
    const ticks = marks.map((mk) => ({ ...mk, k: nearest(mk.m) })).filter((mk) => mk.k >= 0);
    this.marks = ticks;

    const sec = document.createElement('section');
    sec.className = 'tl';
    sec.innerHTML = `
      <div class="tl-head">
        <h3>Sentinel-2 time-lapse <span class="muted">(this block)</span></h3>
        <label class="switch" title="Show monthly true colour inside this box"><input type="checkbox" class="tl-on" checked><i></i></label>
      </div>
      <div class="tl-body">
        <div class="tl-now">
          <b class="tl-month mono">${esc(M[0])}</b>
          <span class="tl-state small"></span>
          <span class="tl-count muted small mono"></span>
        </div>
        <div class="tl-track">
          <div class="tl-marks">${ticks.map((t) => `<i class="mk ${t.cls}" style="left:${pos(t.k)}%" title="${esc(t.label)}: ${esc(t.m)}"></i>`).join('')}</div>
          <input type="range" class="tl-range" min="0" max="${n - 1}" value="0" aria-label="Time-lapse month">
          <div class="tl-years">${years.map(([m, k]) => `<span style="left:${pos(k)}%">${m.endsWith('-01') ? m.slice(0, 4) : ''}</span>`).join('')}</div>
        </div>
        <div class="tl-ctrls">
          <button class="icon-btn tl-prev" title="Previous frame (,)" aria-label="Previous frame">‹</button>
          <button class="icon-btn tl-play" title="Play / pause (≈1.5 frames/s)" aria-label="Play">▶</button>
          <button class="icon-btn tl-next" title="Next frame (.)" aria-label="Next frame">›</button>
          <label class="tl-season" title="Step 12 months at a time (same calendar month each year) to separate change from seasonality">
            <input type="checkbox" class="tl-same"> Same season only</label>
        </div>
        <ul class="tl-legend small">
          ${ticks.map((t) => `<li><i class="mk ${t.cls}"></i>${esc(t.label)} <b class="mono">${esc(t.m)}</b></li>`).join('')}
          <li class="muted">${n} cloud-free months (${esc(M[0])} → ${esc(latest)}); cloudy months are skipped.</li>
        </ul>
      </div>`;
    const firstH3 = host.querySelector(':scope > h3');
    host.insertBefore(sec, firstH3 || null);
    const q = (s) => sec.querySelector(s);
    q('.tl-on').addEventListener('change', (e) => this.setOn(e.target.checked));
    q('.tl-range').addEventListener('input', (e) => { this.pause(); this.show(+e.target.value); });
    q('.tl-prev').addEventListener('click', () => { this.pause(); this.step(-1); });
    q('.tl-next').addEventListener('click', () => { this.pause(); this.step(1); });
    q('.tl-play').addEventListener('click', () => (this.timer ? this.pause() : this.play()));
    q('.tl-same').addEventListener('change', (e) => { this.sameSeason = e.target.checked; });
    // keyboard: , and . step frames while focus is in the panel
    sec.addEventListener('keydown', (e) => {
      if (e.key === ',') { this.pause(); this.step(-1); }
      if (e.key === '.') { this.pause(); this.step(1); }
    });
    return sec;
  }

  updateUi(m, loading, error) {
    if (!this.el) return;
    const q = (s) => this.el.querySelector(s);
    q('.tl-month').textContent = m;
    q('.tl-range').value = this.i;
    q('.tl-count').textContent = `${this.i + 1} / ${this.months.length}`;
    const st = q('.tl-state');
    st.className = `tl-state small ${error ? 'is-err' : loading ? 'is-loading' : 'is-ok'}`;
    st.innerHTML = error ? esc(error) : loading && this.active ? '<span class="spin"></span> loading frame…' : '';
    const hit = (this.marks || []).filter((t) => this.months[t.k] === m).map((t) => t.label);
    if (!error && !loading && hit.length) st.textContent = hit.join(' · ');
  }
}
