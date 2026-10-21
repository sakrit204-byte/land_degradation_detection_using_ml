// Data access: the UI reads ONLY the files described in docs/UI_DATA_SPEC.md plus /api/*.
import { DATA_ROOT } from './config.js';
import { trackedFetch } from './progress.js';

const cache = new Map();

/** Fetch JSON once; resolves to null (not an exception) when a file is missing. */
export function getJSON(path, { optional = true } = {}) {
  if (!cache.has(path)) {
    cache.set(path, trackedFetch(path, { cache: 'no-cache' }).then(async (r) => {
      if (!r.ok) {
        if (optional) return null;
        throw new Error(`${path}: HTTP ${r.status}`);
      }
      return r.json();
    }).catch((e) => {
      if (optional) { console.warn('[data] optional file unavailable:', path, e.message); return null; }
      throw e;
    }));
  }
  return cache.get(path);
}

export const aoiDir = (key) => `${DATA_ROOT}aois/${encodeURIComponent(key)}/`;

/** aois.json; fresh=true re-reads it (e.g. after an on-demand analysis added areas). */
export function loadIndex({ fresh = false } = {}) {
  const path = `${DATA_ROOT}aois.json`;
  if (fresh) cache.delete(path);
  return getJSON(path, { optional: false });
}

/** Forget cached per-AOI files (an AOI re-analysed under the same key). */
export function forgetAoi(key) {
  const d = aoiDir(key);
  for (const k of [...cache.keys()]) if (k.startsWith(d)) cache.delete(k);
}

/** JSON request to the backend; throws Error(detail) with .status on HTTP errors. */
export async function api(path, { method = 'GET', body } = {}) {
  const r = await fetch(path, {
    method, cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = j.detail;
    const msg = Array.isArray(d) ? d.map((x) => x.msg || JSON.stringify(x)).join('; ') : (d || `HTTP ${r.status}`);
    throw Object.assign(new Error(msg), { status: r.status });
  }
  return j;
}
export const loadMetrics = () => getJSON(`${DATA_ROOT}metrics.json`);

/** Load all per-AOI files in parallel. Missing files come back as null. */
export async function loadAoiBundle(key) {
  const d = aoiDir(key);
  const [meta, hotspots, network, local, hydro, ts] = await Promise.all([
    getJSON(d + 'meta.json'),
    getJSON(d + 'hotspots.geojson'),
    getJSON(d + 'rivers_network.geojson'),
    getJSON(d + 'rivers_local.geojson'),
    getJSON(d + 'hydro.json'),
    getJSON(d + 'timeseries.json'),
  ]);
  return { key, dir: d, meta, hotspots, network, local, hydro, ts };
}

/** GET /api/pixel. Throws an Error whose message is the server's "detail". */
export async function fetchPixel(aoi, lon, lat) {
  const u = `api/pixel?aoi=${encodeURIComponent(aoi)}&lon=${lon.toFixed(6)}&lat=${lat.toFixed(6)}`;
  const r = await trackedFetch(u);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
}

// ------------------------------------------------------------------ small helpers
export const fmt = (v, d = 2, suffix = '') =>
  v == null || !isFinite(v) ? '–' : `${Number(v).toFixed(d)}${suffix}`;
export const fmtPct = (v, d = 1) =>
  v == null || !isFinite(v) ? '–' : `${v > 0 ? '+' : ''}${Number(v).toFixed(d)}%`;
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Centroid + bbox of a GeoJSON Polygon feature (first ring). */
export function ringBounds(feature) {
  const ring = feature.geometry.coordinates[0];
  const xs = ring.map((c) => c[0]), ys = ring.map((c) => c[1]);
  const b = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  return { bbox: b, center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] };
}
