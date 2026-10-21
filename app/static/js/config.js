// CARE-EW UI configuration: endpoints, colours and thresholds used across modules.

export const DATA_ROOT = 'data/';

export const BASEMAPS = {
  esri: {
    name: 'Esri World Imagery',
    url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer',
    kind: 'arcgis',
  },
  topo: {
    name: 'Esri World Topographic',
    url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer',
    kind: 'arcgis',
  },
  osm: {
    name: 'OpenStreetMap',
    url: 'https://tile.openstreetmap.org/',
    kind: 'osm',
  },
};
export const LABELS_URL =
  'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer';

// Hotspot status styling (status palette is reserved for hotspot state only).
export const STATUS = {
  warning:            { label: 'Warning',            color: '#ff3b30', text: '#ffffff' },
  watch:              { label: 'Watch',              color: '#ff9f1c', text: '#1a1206' },
  abstain:            { label: 'Abstain · inspect',  color: '#a368ff', text: '#ffffff' },
  active_degradation: { label: 'Active degradation', color: '#9b0d0d', text: '#ffffff' },
};

// Default risk / NDVI legends (overridden by meta.json "legend" when present).
export const RISK_LEGEND = {
  title: 'P(degradation onset ≤ 6 months)',
  min_shown: 0.15,
  stops: [[0.15, '#ffe24d'], [0.35, '#ff961e'], [0.6, '#e8281c'], [1.0, '#78000a']],
  abstain: '#9b59ff',
};
export const NDVI_LEGEND = {
  title: 'NDVI anomaly (z)',
  stops: [[-3, '#7a4818'], [-1.5, '#c4965a'], [0, '#f5f5f0'], [1.5, '#6eb45a'], [3, '#146e28']],
};

// AOI-level risk classes on stats.risk_mean = mean calibrated 6-month onset probability of eligible
// pixels. The pooled base rate is ~1 %, so "Moderate" ~ typical, "High" ~ 4x typical.
export const RISK_CLASSES = [
  { max: 0.005, label: 'Low',      color: '#35c27f' },
  { max: 0.015, label: 'Moderate', color: '#ffd23f' },
  { max: 0.04,  label: 'Elevated', color: '#ff8c1a' },
  { max: Infinity, label: 'High', color: '#e3261c' },
];
export function riskClass(v) {
  if (v == null || !isFinite(v)) return { label: 'n/a', color: '#7d8a99' };
  return RISK_CLASSES.find((c) => v < c.max);
}

// River styling.
export const RIVER = {
  upstream: '#00e5ff',
  outlet: '#ffd60a',
  downstream: '#6ec6ff',
  local: '#8fb8d8',
};

// Chart series colours (validated categorical order, dark-surface steps).
export const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9'];

export const ATTRIBUTION_HTML = [
  'Imagery © <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a>, Maxar, Earthstar Geographics',
  'Analysis: contains modified <a href="https://dataspace.copernicus.eu" target="_blank" rel="noopener">Copernicus Sentinel-2</a> data (ESA)',
  'Rivers: <a href="https://www.hydrosheds.org" target="_blank" rel="noopener">HydroSHEDS / HydroRIVERS</a>',
  'Discharge: <a href="https://global-flood.emergency.copernicus.eu" target="_blank" rel="noopener">GloFAS</a> (Copernicus EMS)',
  'Land cover: <a href="https://esa-worldcover.org" target="_blank" rel="noopener">ESA WorldCover</a>',
].join(' · ');
export const OSM_ATTRIBUTION = 'Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';
