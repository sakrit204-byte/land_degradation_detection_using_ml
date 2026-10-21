// Real, measured loading progress for every user (no fake spinners).
//
// Three sources are tracked:
//   1. every data request made through trackedFetch(): files in flight / done, bytes received / expected
//      (streamed from the response body, so large files advance smoothly);
//   2. Cesium globe tiles: tileLoadProgressEvent gives the number of tiles still queued; we keep the peak of
//      the current burst so "done / total" is exact for that burst;
//   3. named startup steps (engine, area list, globe, first tiles) shown as a checklist on first load.
// A stall watchdog reports "no data for N s" when work is pending but nothing has arrived recently, so a slow
// connection can be told apart from a frozen app.

const STALL_MS = 15000;
const st = {
  files: { active: 0, done: 0, failed: 0 },
  bytes: { got: 0, expected: 0 },
  tiles: { pending: 0, peak: 0 },
  lastActivity: performance.now(),
  steps: [],          // [{id, label, state: 'wait'|'run'|'done'|'fail', detail}]
  listeners: new Set(),
};

const now = () => performance.now();
const emit = () => { st.lastActivity = now(); render(); };

// ------------------------------------------------------------------ data requests
export async function trackedFetch(url, opts = {}) {
  st.files.active++; emit();
  let resp;
  try {
    resp = await fetch(url, opts);
  } catch (e) {
    st.files.active--; st.files.failed++; emit();
    throw e;
  }
  const len = Number(resp.headers.get('content-length')) || 0;
  if (!resp.body || !resp.ok) {
    st.files.active--; st.files.done++; emit();
    return resp;
  }
  st.bytes.expected += len;
  const reader = resp.body.getReader();
  const chunks = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value); got += value.length; st.bytes.got += value.length;
    if (!len) st.bytes.expected += value.length;   // unknown length: expected grows with what arrives
    emit();
  }
  st.files.active--; st.files.done++;
  if (st.files.active === 0) { st.bytes.got = 0; st.bytes.expected = 0; }   // reset per burst
  emit();
  return new Response(new Blob(chunks), { status: resp.status, statusText: resp.statusText, headers: resp.headers });
}

// ------------------------------------------------------------------ globe tiles
export function trackGlobe(viewer) {
  viewer.scene.globe.tileLoadProgressEvent.addEventListener((n) => {
    if (n > st.tiles.peak || st.tiles.pending === 0) st.tiles.peak = Math.max(n, st.tiles.peak);
    st.tiles.pending = n;
    if (n === 0) st.tiles.peak = 0;
    emit();
  });
}

// ------------------------------------------------------------------ startup checklist
export function step(id, label, state = 'run', detail = '') {
  let s = st.steps.find((x) => x.id === id);
  if (!s) { s = { id, label }; st.steps.push(s); }
  Object.assign(s, { label: label || s.label, state, detail });
  emit();
}
export const stepDone = (id, detail = '') => step(id, null, 'done', detail);
export const stepFail = (id, detail = '') => step(id, null, 'fail', detail);

// ------------------------------------------------------------------ rendering
let els = null, startupOpen = true, onStartupDone = null;
export function mountProgress({ bar, chip, startup }, { onReady } = {}) {
  els = { bar, chip, startup }; onStartupDone = onReady;
  setInterval(render, 1000);   // keeps the "x s ago" stall timer honest even when no events arrive
  render();
}

function fmtBytes(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(0)} kB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function snapshot() {
  const filesTotal = st.files.active + st.files.done;
  const tilesDone = st.tiles.peak ? st.tiles.peak - st.tiles.pending : 0;
  const busy = st.files.active > 0 || st.tiles.pending > 0;
  // overall fraction: weight bytes (if known) and tiles equally
  const parts = [];
  if (st.files.active > 0) parts.push(st.bytes.expected ? st.bytes.got / st.bytes.expected : st.files.done / Math.max(1, filesTotal));
  if (st.tiles.pending > 0) parts.push(tilesDone / Math.max(1, st.tiles.peak));
  const frac = parts.length ? parts.reduce((a, b) => a + b, 0) / parts.length : 1;
  const idle = now() - st.lastActivity;
  return { busy, frac, filesTotal, tilesDone, idle };
}

function render() {
  if (!els) return;
  const s = snapshot();
  const stalled = s.busy && s.idle > STALL_MS;
  // top bar
  els.bar.classList.toggle('active', s.busy);
  els.bar.classList.toggle('stalled', stalled);
  els.bar.querySelector('i').style.width = `${Math.round((s.busy ? Math.max(0.03, s.frac) : 1) * 100)}%`;
  // status chip
  const bits = [];
  if (st.files.active > 0) {
    bits.push(`files ${st.files.done}/${s.filesTotal}`);
    if (st.bytes.expected) bits.push(`${fmtBytes(st.bytes.got)} / ${fmtBytes(st.bytes.expected)}`);
  }
  if (st.tiles.pending > 0) bits.push(`map tiles ${s.tilesDone}/${st.tiles.peak}`);
  if (s.busy) {
    els.chip.innerHTML = `<b>${Math.round(s.frac * 100)}%</b> ${bits.join(' · ')}` +
      (stalled ? ` · <em>waiting for network – last data ${Math.round(s.idle / 1000)} s ago</em>` : '');
    els.chip.classList.add('show');
  } else {
    els.chip.classList.remove('show');
  }
  els.chip.classList.toggle('stalled', stalled);
  // startup checklist
  if (startupOpen && els.startup) {
    const list = els.startup.querySelector('ul');
    list.innerHTML = st.steps.map((x) => `<li class="${x.state}"><i></i><span>${x.label}</span><small>${x.detail || ''}</small></li>`).join('');
    const pct = els.startup.querySelector('.pct');
    const doneN = st.steps.filter((x) => x.state === 'done').length;
    pct.textContent = `${Math.round(50 + 50 * (doneN / Math.max(1, st.steps.length)))}%`;   // libraries = first 50 %
    els.startup.querySelector('.bar i').style.width = pct.textContent;
    const stall = els.startup.querySelector('.stall');
    stall.textContent = stalled ? `Still working – no data received for ${Math.round(s.idle / 1000)} s. Your connection may be slow; the app is not frozen.` : '';
    if (st.steps.length && st.steps.every((x) => x.state === 'done' || x.state === 'fail')) {
      startupOpen = false;
      setTimeout(() => { els.startup.classList.add('hidden'); onStartupDone && onStartupDone(); }, 400);
    }
  }
}

/** Live step detail for the globe-tiles step: "38 / 52 tiles". */
export function tilesDetail() {
  return st.tiles.peak ? `${st.tiles.peak - st.tiles.pending} / ${st.tiles.peak} tiles` : '';
}
export const tilesPending = () => st.tiles.pending;
