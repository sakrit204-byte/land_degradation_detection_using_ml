// Chart.js charts for the analytics drawer. One measure family per chart (no dual axes).
/* global Chart */
import { SERIES } from './config.js';
import { esc, fmt, fmtPct } from './data.js';

const INK = '#c9d4df', MUTED = '#7f8fa0', GRID = 'rgba(140,160,180,0.12)';
Chart.defaults.color = MUTED;
Chart.defaults.font.family = 'Inter, "Segoe UI", system-ui, sans-serif';
Chart.defaults.font.size = 11;
Chart.defaults.borderColor = GRID;
Chart.defaults.animation = { duration: 250 };

// Vertical marker lines (current month, label onsets, ...). options.plugins.vlines.lines = [{x, color, dash, text}]
const vlines = {
  id: 'vlines',
  afterDatasetsDraw(chart, _args, opts) {
    const lines = opts?.lines || [];
    if (!lines.length) return;
    const { ctx, chartArea: a, scales: { x } } = chart;
    const labels = chart.data.labels || [];
    ctx.save();
    for (const l of lines) {
      const i = labels.indexOf(l.x);
      if (i < 0) continue;
      const px = x.getPixelForValue(i);
      ctx.strokeStyle = l.color || '#fff';
      ctx.lineWidth = l.width || 1.5;
      ctx.setLineDash(l.dash || []);
      ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
      if (l.text) {
        ctx.setLineDash([]);
        ctx.font = '600 10px Inter, system-ui, sans-serif';
        ctx.fillStyle = l.color || '#fff';
        ctx.textAlign = px > a.right - 40 ? 'right' : 'left';
        ctx.fillText(l.text, px + (ctx.textAlign === 'right' ? -4 : 4), a.top + 10);
      }
    }
    ctx.restore();
  },
};
Chart.register(vlines);

function yearTicks(labels) {
  return {
    autoSkip: false, maxRotation: 0,
    callback(v, i) {
      const m = labels[i];
      if (!m) return '';
      if (!m.endsWith('-01')) return labels.length <= 30 ? m.slice(2) : '';
      // thin out year labels when the chart is narrow (~34 px per label)
      const years = labels.filter((x) => x.endsWith('-01')).length;
      const step = Math.max(1, Math.ceil((years * 34) / Math.max(1, this.width)));
      return +m.slice(0, 4) % step === 0 ? m.slice(0, 4) : '';
    },
    color: MUTED,
  };
}

function baseOptions(labels, { yTitle, yMin, yMax, legend = true, suggestedMin, suggestedMax } = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    elements: { point: { radius: 0, hoverRadius: 4, hitRadius: 8 }, line: { borderWidth: 2, tension: 0.25 } },
    scales: {
      x: { ticks: yearTicks(labels), grid: { display: false } },
      y: {
        min: yMin, max: yMax, suggestedMin, suggestedMax,
        title: { display: !!yTitle, text: yTitle, color: MUTED },
        grid: { color: GRID }, ticks: { color: MUTED, maxTicksLimit: 5 },
      },
    },
    plugins: {
      legend: { display: legend, position: 'top', align: 'end', labels: { boxWidth: 10, boxHeight: 2, color: INK, padding: 8 } },
      tooltip: {
        backgroundColor: 'rgba(10,16,24,0.95)', borderColor: '#2b3b4d', borderWidth: 1,
        titleColor: '#fff', bodyColor: INK, padding: 8,
        callbacks: { label: (c) => ` ${c.dataset.label}: ${c.raw == null ? '–' : Number(c.raw).toFixed(3)}` },
      },
      vlines: { lines: [] },
    },
  };
}

const line = (label, data, i, extra = {}) => ({ label, data, borderColor: SERIES[i], backgroundColor: SERIES[i], spanGaps: false, ...extra });

export class Analytics {
  constructor(root) {
    this.root = root;
    this.charts = {};
    this.cursor = null;
    this.ts = null;
  }

  destroy(prefix) {
    for (const k of Object.keys(this.charts)) {
      if (k.startsWith(prefix)) { this.charts[k].destroy(); delete this.charts[k]; }
    }
  }

  make(key, canvasId, config) {
    this.charts[key]?.destroy();
    const el = this.root.querySelector('#' + canvasId);
    if (!el) return null;
    this.charts[key] = new Chart(el, config);
    return this.charts[key];
  }

  resizeAll() { Object.values(this.charts).forEach((c) => c.resize()); }

  // ------------------------------------------------------------ AOI time series
  renderTimeseries(ts) {
    this.ts = ts;
    this.destroy('ts');
    const box = this.root.querySelector('#ts-empty');
    if (!ts || !ts.months) { box.hidden = false; return; }
    box.hidden = true;
    const L = ts.months;
    const has = (k) => Array.isArray(ts[k]) && ts[k].some((v) => v != null);
    this.make('ts-ndvi', 'c-ts-ndvi', {
      type: 'line',
      data: { labels: L, datasets: [line('NDVI mean', ts.ndvi_mean || [], 2)] },
      options: baseOptions(L, { legend: false }),
    });
    const zsets = [];
    if (has('z_mean')) zsets.push(line('NDVI z', ts.z_mean, 0));
    if (has('resid_mean')) zsets.push(line('Climate residual R', ts.resid_mean, 1));
    this.make('ts-z', 'c-ts-z', {
      type: 'line', data: { labels: L, datasets: zsets },
      options: baseOptions(L, { suggestedMin: -2, suggestedMax: 1 }),
    });
    const rsets = [];
    if (has('risk_mean')) rsets.push(line('Mean risk', ts.risk_mean, 1, { fill: false }));
    if (has('frac_below')) rsets.push(line('Fraction below expectation', ts.frac_below, 0));
    this.make('ts-risk', 'c-ts-risk', {
      type: 'line', data: { labels: L, datasets: rsets },
      options: baseOptions(L, { yMin: 0, suggestedMax: 0.4 }),
    });
    const rain = ts.rain_anom_6m || [];
    this.make('ts-rain', 'c-ts-rain', {
      type: 'bar',
      data: { labels: L, datasets: [{
        label: '6-month rain anomaly', data: rain, borderRadius: 2, barPercentage: 0.9, categoryPercentage: 1,
        backgroundColor: rain.map((v) => (v == null ? 'transparent' : v >= 0 ? '#3987e5' : '#b5762f')),
      }] },
      options: baseOptions(L, { legend: false, suggestedMin: -1.5, suggestedMax: 1.5 }),
    });
    this.setCursor(this.cursor);
  }

  /** Marks the time-slider month on every time-series chart. */
  setCursor(month) {
    this.cursor = month;
    for (const k of ['ts-ndvi', 'ts-z', 'ts-risk', 'ts-rain']) {
      const c = this.charts[k];
      if (!c) continue;
      c.options.plugins.vlines.lines = month ? [{ x: month, color: 'rgba(255,255,255,0.75)', dash: [4, 3], text: month }] : [];
      c.update('none');
    }
  }

  // ------------------------------------------------------------ river flow
  renderFlow(hydro) {
    this.destroy('flow');
    const tbl = this.root.querySelector('#flow-table');
    const empty = this.root.querySelector('#flow-empty');
    const st = (hydro?.stations || []);
    const ok = st.filter((s) => s.available !== false && s.mean_before != null);
    if (!ok.length) { empty.hidden = false; tbl.innerHTML = ''; return; }
    empty.hidden = true;
    const names = ok.map((s) => s.name.replace(/\s*\(.*\)\s*$/, ''));
    const barOpts = (title) => {
      const o = baseOptions(names, { yMin: 0, yTitle: title });
      o.scales.x.ticks = { color: INK, autoSkip: false, maxRotation: 0 };
      o.elements = {};
      o.plugins.legend.labels = { ...o.plugins.legend.labels, boxHeight: 10, boxWidth: 10 };
      o.plugins.tooltip.callbacks.label = (c) => ` ${c.dataset.label}: ${fmt(c.raw, 2)} m³/s`;
      return o;
    };
    const bars = (a, b) => [
      { label: 'Before (1984–2000)', data: ok.map((s) => s[a]), backgroundColor: '#5b6b7d', borderRadius: 4, borderSkipped: 'bottom', barPercentage: 0.8, categoryPercentage: 0.7 },
      { label: 'Now (2016–)', data: ok.map((s) => s[b]), backgroundColor: '#00b8d9', borderRadius: 4, borderSkipped: 'bottom', barPercentage: 0.8, categoryPercentage: 0.7 },
    ];
    this.make('flow-mean', 'c-flow-mean', { type: 'bar', data: { labels: names, datasets: bars('mean_before', 'mean_now') }, options: barOpts('Mean flow (m³/s)') });
    this.make('flow-low', 'c-flow-low', { type: 'bar', data: { labels: names, datasets: bars('q90_before', 'q90_now') }, options: barOpts('Low flow Q90 (m³/s)') });

    const chg = (v) => {
      if (v == null) return '<span class="muted">–</span>';
      const cls = v <= -10 ? 'neg' : v >= 10 ? 'pos' : 'flat';
      const arrow = v < 0 ? '▼' : v > 0 ? '▲' : '■';
      return `<span class="chg ${cls}">${arrow} ${fmtPct(v)}</span>`;
    };
    tbl.innerHTML = `<table class="data-table"><thead><tr><th>Station</th><th>Mean before</th><th>Mean now</th><th>Δ mean</th><th>Q90 before</th><th>Q90 now</th><th>Δ low flow</th></tr></thead><tbody>${
      st.map((s) => s.available === false
        ? `<tr class="na"><td>${esc(s.name)}</td><td colspan="6" class="muted">No discharge record available</td></tr>`
        : `<tr><td>${esc(s.name)}</td><td>${fmt(s.mean_before, 2)}</td><td>${fmt(s.mean_now, 2)}</td><td>${chg(s.change_mean_pct)}</td><td>${fmt(s.q90_before, 2)}</td><td>${fmt(s.q90_now, 2)}</td><td>${chg(s.change_lowflow_pct)}</td></tr>`).join('')
    }</tbody></table><p class="foot">Units m³/s. “Before” = 1984–2000, “now” = 2016–present. Q90 = flow exceeded 90 % of the time (low-flow index). Outlet long-term mean: ${fmt(hydro.outlet_mean_q, 2)} m³/s.</p>`;
  }

  // ------------------------------------------------------------ pixel inspector
  renderPixel(px) {
    this.destroy('px');
    const L = px.months || [];
    const onsetLines = (px.label_onsets || []).map((m) => ({ x: m, color: '#ff4d4d', dash: [5, 3], width: 2, text: 'onset' }));
    const opts = (o) => { const b = baseOptions(L, o); b.plugins.vlines.lines = onsetLines; return b; };
    this.make('px-ndvi', 'c-px-ndvi', { type: 'line', data: { labels: L, datasets: [line('NDVI', px.ndvi || [], 2, { pointRadius: 1.5 })] }, options: opts({ legend: false, suggestedMin: 0, suggestedMax: 0.8 }) });
    this.make('px-z', 'c-px-z', { type: 'line', data: { labels: L, datasets: [line('NDVI z', px.z || [], 0), line('Residual R', px.resid || [], 1)] }, options: opts({ suggestedMin: -3, suggestedMax: 2 }) });
    this.make('px-risk', 'c-px-risk', { type: 'line', data: { labels: L, datasets: [line('Predicted risk', px.risk || [], 1, { fill: { target: 'origin', above: 'rgba(217,89,38,0.15)' } })] }, options: opts({ legend: false, yMin: 0, yMax: 1 }) });
  }
}
