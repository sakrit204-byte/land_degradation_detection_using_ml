// HTML panels: AOI list, hotspot / station info, legend, model card.
import { STATUS, RISK_LEGEND, NDVI_LEGEND, RIVER, riskClass } from './config.js';
import { esc, fmt, fmtPct, ringBounds } from './data.js';

// ------------------------------------------------------------------ AOI list
export function renderAoiList(el, aois, { query = '', activeKey = null, onPick }) {
  const q = query.trim().toLowerCase();
  const list = aois
    .filter((a) => !q || [a.key, a.country, a.landscape].some((s) => (s || '').toLowerCase().includes(q)))
    .sort((a, b) => (b.stats?.risk_mean ?? -1) - (a.stats?.risk_mean ?? -1));
  if (!list.length) { el.innerHTML = '<li class="empty">No AOI matches your search.</li>'; return; }
  // user-drawn areas first ("Your areas"), then the study areas
  const user = list.filter((a) => a.user), study = list.filter((a) => !a.user);
  const card = (a) => {
    const s = a.stats || {}, rc = riskClass(s.risk_mean);
    const trend = s.ndvi_trend_per_yr;
    const trendTxt = trend == null ? '–' : `${trend > 0 ? '▲' : trend < 0 ? '▼' : '■'} ${fmt(trend, 4)}/yr`;
    const title = a.user ? (a.landscape || 'User area') : a.country;
    return `<li class="aoi-card ${a.user ? 'user' : ''} ${a.key === activeKey ? 'active' : ''}" data-key="${esc(a.key)}" tabindex="0" role="button" aria-label="Fly to ${esc(a.key)}">
      <div class="aoi-head">
        <span class="dot" style="background:${rc.color}"></span>
        <div class="aoi-title"><b>${esc(title)}${a.user ? ' <span class="user-badge">USER</span>' : ''}</b><span class="mono">${esc(a.key)}</span></div>
        <span class="risk-chip" style="--c:${rc.color}">${rc.label}</span>
      </div>
      ${a.user ? `<div class="aoi-land">Drawn ${esc(a.created || '')} · indicative (outside training areas)</div>` : ''}
      ${a.user ? '' : `<div class="aoi-land">${esc(a.landscape || '')}</div>`}
      <div class="aoi-stats">
        <div><span>${fmt(s.risk_mean, 3)}</span><label>mean risk</label></div>
        <div><span>${s.n_hotspots ?? '–'}</span><label>hotspots</label></div>
        <div><span>${fmt(s.area_high_ha, 1)}</span><label>ha high</label></div>
        <div><span>${fmt(s.area_abstain_ha, 1)}</span><label>ha abstain</label></div>
      </div>
      <div class="aoi-trend ${trend < 0 ? 'neg' : ''}">NDVI trend ${trendTxt}</div>
    </li>`;
  };
  el.innerHTML = (user.length ? `<li class="group-head">Your areas <span>${user.length}</span></li>${user.map(card).join('')}` : '')
    + (study.length ? `${user.length ? `<li class="group-head">Study areas <span>${study.length}</span></li>` : ''}${study.map(card).join('')}` : '');
  el.querySelectorAll('.aoi-card').forEach((li) => {
    const go = () => onPick(li.dataset.key);
    li.addEventListener('click', go);
    li.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  });
}

// ------------------------------------------------------------------ legend
function gradient(stops, lo, hi) {
  return `linear-gradient(90deg, ${stops.map(([v, c]) => `${c} ${(((v - lo) / (hi - lo)) * 100).toFixed(1)}%`).join(', ')})`;
}

export function renderLegend(el, { meta, visible, inAoi }) {
  const risk = { ...RISK_LEGEND, ...(meta?.legend?.risk || {}) };
  const ndvi = { ...NDVI_LEGEND, ...(meta?.legend?.ndvi || {}) };
  const parts = [];
  if (!inAoi) {
    parts.push(`<h4>AOI mean risk</h4><div class="lg-classes">
      ${[['Low', '#35c27f'], ['Moderate', '#ffd23f'], ['Elevated', '#ff8c1a'], ['High', '#e3261c']].map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join('')}
    </div><p class="lg-note">Click a pin or a list entry to open an AOI.</p>`);
  } else {
    if (visible.risk) {
      const lo = risk.stops[0][0], hi = risk.stops[risk.stops.length - 1][0];
      parts.push(`<h4>${esc(risk.title)}</h4>
        <div class="lg-ramp" style="background:${gradient(risk.stops, lo, hi)}"></div>
        <div class="lg-ticks"><span>${lo}</span><span>${risk.stops[Math.floor(risk.stops.length / 2)][0]}</span><span>${hi}</span></div>
        <div class="lg-row"><i class="sw hatch" style="--c:${risk.abstain || '#9b59ff'}"></i>Abstain – model uncertain, inspect in field</div>
        <div class="lg-row muted">Transparent below ${risk.min_shown ?? 0.15}</div>`);
    }
    if (visible.ndvi) {
      parts.push(`<h4>${esc(ndvi.title)}</h4>
        <div class="lg-ramp" style="background:${gradient(ndvi.stops, -3, 3)}"></div>
        <div class="lg-ticks"><span>−3 browning</span><span>0</span><span>+3 greening</span></div>`);
    }
    if (visible.hotspots) {
      parts.push(`<h4>Hotspots (latest month)</h4><div class="lg-grid">${
        Object.entries(STATUS).map(([k, s]) => `<span><i class="sw box ${k === 'abstain' ? 'dashed' : ''}" style="--c:${s.color}"></i>${s.label}</span>`).join('')}</div>`);
    }
    if (visible.network || visible.local || visible.stations) {
      parts.push(`<h4>Hydrology</h4><div class="lg-grid">
        ${visible.network ? `<span><i class="ln" style="--c:${RIVER.upstream};height:4px"></i>Upstream network</span>
        <span><i class="ln" style="--c:${RIVER.outlet};height:5px"></i>AOI outlet reach</span>
        <span><i class="ln dashed" style="--c:${RIVER.downstream}"></i>Downstream</span>` : ''}
        ${visible.local ? `<span><i class="ln" style="--c:${RIVER.local};height:1.5px"></i>Local reaches</span>` : ''}
        ${visible.stations ? '<span><i class="gauge"></i>Discharge point</span>' : ''}
      </div><p class="lg-note">Line width ∝ Strahler order.</p>`);
    }
  }
  el.querySelector('.lg-body').innerHTML = parts.join('') || '<p class="lg-note">No layers visible.</p>';
}

// ------------------------------------------------------------------ hotspot panel
export function renderHotspot(el, f, { bundle, onZoom, onExport, warning }) {
  const p = f.properties || {};
  const st = STATUS[p.status] || { label: p.status, color: '#888' };
  const { center } = ringBounds(f);
  const dNdvi = p.ndvi_now != null && p.ndvi_baseline ? (p.ndvi_now / p.ndvi_baseline - 1) * 100 : null;
  const drivers = (p.drivers || []).slice(0, 5);
  const maxC = Math.max(1e-9, ...drivers.map((d) => Math.abs(d.contribution || 0)));
  const mrgb = bundle?.meta?.months_rgb || [];
  const chip = (rel) => (rel ? `${bundle.dir}${rel}` : null);
  const before = chip(p.chip_before), after = chip(p.chip_after);
  const riskPct = Math.max(0, Math.min(1, (p.risk_mean ?? 0) / Math.max(1e-6, 4 * (bundle?.meta?.threshold ?? 0.25)))) * 100;  // bar full at 4x the operating threshold

  el.innerHTML = `
    <div class="ip-head" style="--c:${st.color}">
      <div>
        <div class="ip-kicker">${esc(bundle?.key || '')} · Hotspot</div>
        <h2>${esc(p.label || p.id)} <span class="status-pill" style="--c:${st.color}">${esc(st.label)}</span></h2>
      </div>
      <button class="icon-btn ip-close" title="Close" aria-label="Close panel">✕</button>
    </div>
    <div class="ip-body">
      ${warning ? `<div class="note warn user-warn">⚠ ${esc(warning)}</div>` : ''}
      ${p.status === 'active_degradation' ? `
      <div class="ip-risk">
        <div class="big">${p.months_below ?? '–'}<small> months below peers</small></div>
        <div class="muted small">Already in persistent decline (mean peer-relative residual ${fmt(p.resid_mean, 2)} σ). Past the early-warning stage: prioritise for field verification / intervention.</div>
      </div>` : `
      <div class="ip-risk">
        <div class="big">${fmt(p.risk_mean, 3)}<small> mean risk</small></div>
        <div class="riskbar"><i style="width:${riskPct}%"></i></div>
        <div class="muted small">max ${fmt(p.risk_max, 2)} · probability of a persistent degradation onset within 6 months</div>
      </div>`}
      <div class="kv">
        <div><label>Area</label><span>${fmt(p.area_ha, 1)} ha</span></div>
        <div><label>First warning</label><span>${esc(p.first_warning || '–')}</span></div>
        <div><label>Land cover</label><span class="cap">${esc(p.landcover || '–')}</span></div>
        <div><label>Distance to river</label><span>${fmt(p.dist_river_km, 2)} km</span></div>
        <div><label>NDVI now / baseline</label><span>${fmt(p.ndvi_now, 3)} / ${fmt(p.ndvi_baseline, 3)} <em class="${dNdvi < 0 ? 'neg' : ''}">${fmtPct(dNdvi, 0)}</em></span></div>
        <div><label>Rain anomaly (6 mo)</label><span>${fmt(p.rain_anom_6m, 2)} σ</span></div>
      </div>
      ${p.status === 'abstain' ? '<div class="note abstain">Abstain: the conformal predictor could not give a confident answer. This site needs a <b>field inspection</b>.</div>' : ''}
      ${Array.isArray(p.attribution) && p.attribution.length ? `
      <h3>Likely process <span class="muted small">(ecosystem structure &amp; function)</span></h3>
      <ul class="attr-list">${p.attribution.map((a) => `<li class="attr-${esc(a.code)}">${esc(a.text)}</li>`).join('')}</ul>` : ''}
      <h3>Top drivers <span class="muted small">(model explanation)</span></h3>
      <div class="drivers">${drivers.length ? drivers.map((d) => `
        <div class="drv"><div class="drv-name" title="${esc(d.name)}">${esc(d.name)}</div>
          <div class="drv-bar"><i style="width:${(Math.abs(d.contribution || 0) / maxC) * 100}%"></i></div>
          <div class="drv-val">${fmt(d.contribution, 2)}</div></div>`).join('') : '<p class="muted">No driver attribution available.</p>'}
      </div>
      <h3>Sentinel-2 before / after</h3>
      <div class="chips">
        <figure>${before ? `<img src="${esc(before)}" alt="Before" loading="lazy">` : '<div class="noimg">n/a</div>'}<figcaption>Before${(p.chip_before_month || mrgb[0]) ? ' · ' + esc(p.chip_before_month || mrgb[0]) : ''}</figcaption></figure>
        <figure>${after ? `<img src="${esc(after)}" alt="After" loading="lazy">` : '<div class="noimg">n/a</div>'}<figcaption>After${(p.chip_after_month || mrgb.length) ? ' · ' + esc(p.chip_after_month || mrgb[mrgb.length - 1]) : ''}</figcaption></figure>
      </div>
      <div class="coords mono">${center[1].toFixed(5)}, ${center[0].toFixed(5)}</div>
      <div class="ip-actions">
        <button class="btn" data-act="zoom">Zoom to</button>
        <button class="btn" data-act="copy">Copy coordinates</button>
        <button class="btn primary" data-act="export">Export GeoJSON</button>
      </div>
      <p class="disclaimer">EO-proxy based probability, not field-verified.</p>
    </div>`;
  el.querySelector('[data-act=zoom]').onclick = onZoom;
  el.querySelector('[data-act=export]').onclick = onExport;
  el.querySelector('[data-act=copy]').onclick = async (ev) => {
    try { await navigator.clipboard.writeText(`${center[1].toFixed(6)}, ${center[0].toFixed(6)}`); ev.target.textContent = 'Copied'; }
    catch { ev.target.textContent = `${center[1].toFixed(5)}, ${center[0].toFixed(5)}`; }
  };
  el.querySelectorAll('.chips img').forEach((img) => img.addEventListener('error', () => { img.replaceWith(Object.assign(document.createElement('div'), { className: 'noimg', textContent: 'image missing' })); }));
}

export function renderStation(el, s, { bundle }) {
  const ok = s.available !== false;
  el.innerHTML = `
    <div class="ip-head" style="--c:#00b8d9">
      <div><div class="ip-kicker">${esc(bundle?.key || '')} · Discharge</div><h2>${esc(s.name)}</h2></div>
      <button class="icon-btn ip-close" title="Close" aria-label="Close panel">✕</button>
    </div>
    <div class="ip-body">
      ${ok ? `<div class="kv">
        <div><label>Mean flow before (1984–2000)</label><span>${fmt(s.mean_before, 2)} m³/s</span></div>
        <div><label>Mean flow now (2016–)</label><span>${fmt(s.mean_now, 2)} m³/s</span></div>
        <div><label>Change in mean flow</label><span class="${s.change_mean_pct < 0 ? 'neg' : ''}">${fmtPct(s.change_mean_pct)}</span></div>
        <div><label>Low flow Q90 before</label><span>${fmt(s.q90_before, 3)} m³/s</span></div>
        <div><label>Low flow Q90 now</label><span>${fmt(s.q90_now, 3)} m³/s</span></div>
        <div><label>Change in low flow</label><span class="${s.change_lowflow_pct < 0 ? 'neg' : ''}">${fmtPct(s.change_lowflow_pct)}</span></div>
      </div>` : '<div class="note">No discharge record is available for this point.</div>'}
      <div class="coords mono">${fmt(s.lat, 5)}, ${fmt(s.lon, 5)}</div>
      <p class="disclaimer">Discharge from GloFAS reanalysis (modelled, not gauged) unless stated otherwise.</p>
    </div>`;
}

export function renderRiver(el, p, { bundle }) {
  el.innerHTML = `
    <div class="ip-head" style="--c:${p.role === 'outlet' ? RIVER.outlet : RIVER.upstream}">
      <div><div class="ip-kicker">${esc(bundle?.key || '')} · HydroRIVERS reach</div><h2>Reach ${esc(p.HYRIV_ID)}</h2></div>
      <button class="icon-btn ip-close" title="Close" aria-label="Close panel">✕</button>
    </div>
    <div class="ip-body"><div class="kv">
      <div><label>Role</label><span class="cap">${esc(p.role || 'local')}</span></div>
      <div><label>Strahler order</label><span>${esc(p.ORD_STRA)}</span></div>
      <div><label>Long-term mean flow</label><span>${fmt(p.DIS_AV_CMS, 2)} m³/s</span></div>
      <div><label>Upstream area</label><span>${fmt(p.UPLAND_SKM, 1)} km²</span></div>
    </div></div>`;
}

// ------------------------------------------------------------------ model card
const ALIASES = {
  pr_auc: ['pr_auc', 'PR_AUC', 'prauc', 'ap', 'average_precision', 'auprc'],
  roc_auc: ['roc_auc', 'ROC_AUC', 'auc', 'auroc'],
  brier: ['brier', 'brier_score'],
  ece: ['ece', 'ECE', 'expected_calibration_error'],
  lead: ['lead_time_months_median', 'lead_time_months', 'lead_time', 'median_lead_time'],
  base_rate: ['base_rate', 'pos_rate', 'prevalence'],
  coverage: ['conformal_coverage', 'coverage'],
  abstain: ['abstain_rate', 'abstention_rate'],
};
const HEADLINE = [
  ['pr_auc', 'PR-AUC', 3, 'Precision-recall area (primary; rare events)'],
  ['roc_auc', 'ROC-AUC', 3, 'Ranking quality'],
  ['brier', 'Brier', 3, 'Probability error (lower = better)'],
  ['ece', 'ECE', 3, 'Calibration error (lower = better)'],
  ['lead', 'Lead time', 1, 'Median months of warning before onset'],
  ['base_rate', 'Base rate', 3, 'Share of positive samples'],
  ['coverage', 'Conformal coverage', 3, 'Target 0.90'],
  ['abstain', 'Abstain rate', 3, 'Share flagged "needs inspection"'],
];

function pick(objs, names) {
  for (const o of objs) {
    if (!o || typeof o !== 'object') continue;
    for (const n of names) if (o[n] != null && typeof o[n] !== 'object') return o[n];
  }
  return null;
}

/** Render a list-of-objects or object-of-objects as a table. */
function table(data, firstCol = 'name') {
  let rows = [];
  if (Array.isArray(data)) rows = data;
  else if (data && typeof data === 'object') rows = Object.entries(data).map(([k, v]) => (v && typeof v === 'object' ? { [firstCol]: k, ...v } : { [firstCol]: k, value: v }));
  if (!rows.length) return '<p class="muted">Not available in metrics.json.</p>';
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter((c) => rows.some((r) => typeof r[c] !== 'object' || r[c] === null));
  const cell = (v, c) => (typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(3)) : esc(c === firstCol ? String(v ?? '–').replace(/_/g, ' ') : v ?? '–'));
  return `<table class="data-table"><thead><tr>${cols.map((c) => `<th>${esc(c.replace(/_/g, ' '))}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td>${cell(r[c], c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

export function renderModelCard(el, m, index) {
  const disclaimer = `<div class="note warn"><b>How to read these probabilities.</b> Risk values are derived from Earth-observation
    proxies (Sentinel-2 NDVI residuals after climate conditioning) and are <b>not field-verified</b>. “Abstain” means the model is
    not confident and the location <b>needs field inspection</b>. Use outputs to prioritise inspections, not as proof of degradation.</div>`;
  if (!m) {
    el.innerHTML = `${disclaimer}<p class="muted">metrics.json has not been produced by the pipeline yet.</p>`;
    return;
  }
  const sources = [m.headline, m.test, m.metrics, m.overall, m];
  const tiles = HEADLINE.map(([k, label, d, hint]) => {
    const v = pick(sources, ALIASES[k]);
    return v == null ? '' : `<div class="tile"><label>${label}</label><span>${typeof v === 'number' ? v.toFixed(d) : esc(v)}${k === 'lead' ? '<small> mo</small>' : ''}</span><em>${hint}</em></div>`;
  }).join('');
  const abl = m.ablation ?? m.ablations;
  const loco = m.loco ?? m.leave_one_country_out ?? m.leave_one_out;
  el.innerHTML = `
    ${m.mock || index?.mock ? '<div class="note mock">MOCK metrics for interface development – these are not results.</div>' : ''}
    <div class="mc-meta">
      <div><label>Model</label><span>${esc(m.model_version || index?.model_version || '–')}</span></div>
      <div><label>Task</label><span>${esc(m.task || 'Probability of a persistent degradation onset within 6 months')}</span></div>
      <div><label>Test period</label><span>${esc(m.test_period || '–')}</span></div>
      <div><label>Generated</label><span>${esc(m.generated || index?.generated || '–')}</span></div>
    </div>
    <h3>Headline metrics (held-out test)</h3>
    <div class="tiles">${tiles || '<p class="muted">No headline metrics found.</p>'}</div>
    ${m.baselines ? `<h3>Baselines</h3>${table(m.baselines, 'baseline')}` : ''}
    <h3>Ablation</h3>${table(abl, 'model')}
    <h3>Leave-one-country-out</h3>${table(loco, 'country')}
    ${m.corroboration_table ? `<h3>Independent-sensor label check (agreement AUC, 0.5 = none)</h3>${table(m.corroboration_table, 'aoi')}` : ''}
    ${m.walk_forward_table ? `<h3>Continuous retraining (walk-forward)</h3>${table(m.walk_forward_table, 'test_year')}` : ''}
    ${m.notes ? `<p class="muted small">${esc(m.notes)}</p>` : ''}
    ${disclaimer}`;
}
