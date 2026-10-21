// Field-team exports of hotspots as GeoJSON or CSV.
import { ringBounds } from './data.js';

const DISCLAIMER = 'EO-proxy based probabilities, not field-verified. status=abstain means the model is uncertain: field inspection needed.';

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** groups = [{aoi, hotspots: FeatureCollection}] */
function flatten(groups) {
  const out = [];
  for (const { aoi, hotspots } of groups) {
    for (const f of hotspots?.features || []) {
      const { bbox, center } = ringBounds(f);
      out.push({ aoi, f, bbox, center });
    }
  }
  return out;
}

export function exportGeoJSON(groups, index, name) {
  const fc = {
    type: 'FeatureCollection',
    metadata: {
      source: 'CARE-EW', model_version: index?.model_version, latest_month: index?.latest_month,
      exported_at: new Date().toISOString(), mock: !!index?.mock, disclaimer: DISCLAIMER,
    },
    features: flatten(groups).map(({ aoi, f, center }) => ({
      type: 'Feature', geometry: f.geometry,
      properties: {
        aoi: aoi.key, country: aoi.country, ...f.properties,
        centroid_lon: +center[0].toFixed(6), centroid_lat: +center[1].toFixed(6),
        drivers: (f.properties.drivers || []).map((d) => `${d.name} (${d.contribution})`).join('; '),
      },
    })),
  };
  download(`${name}.geojson`, JSON.stringify(fc, null, 1), 'application/geo+json');
}

export function exportCSV(groups, index, name) {
  const cols = ['aoi', 'country', 'id', 'label', 'status', 'risk_mean', 'risk_max', 'area_ha', 'first_warning',
    'landcover', 'centroid_lat', 'centroid_lon', 'west', 'south', 'east', 'north', 'ndvi_now', 'ndvi_baseline',
    'rain_anom_6m', 'dist_river_km', 'top_driver', 'model_version', 'mock', 'caveat'];
  const q = (v) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = flatten(groups).map(({ aoi, f, bbox, center }) => {
    const p = f.properties;
    const r = { ...p, aoi: aoi.key, country: aoi.country, centroid_lat: center[1].toFixed(6), centroid_lon: center[0].toFixed(6),
      west: bbox[0].toFixed(6), south: bbox[1].toFixed(6), east: bbox[2].toFixed(6), north: bbox[3].toFixed(6),
      top_driver: p.drivers?.[0]?.name, model_version: index?.model_version, mock: !!index?.mock,
      caveat: 'EO-proxy probability, not field-verified; abstain = field inspection needed' };
    return cols.map((c) => q(r[c])).join(',');
  });
  // UTF-8 BOM so Excel opens non-ASCII text correctly
  download(`${name}.csv`, '﻿' + [cols.join(','), ...rows].join('\r\n'), 'text/csv;charset=utf-8');
}
