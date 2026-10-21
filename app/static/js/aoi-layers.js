// Everything drawn on the globe: AOI pins (global view) and the per-AOI layers
// (raster overlays, hotspots, rivers, stations, clicked-pixel marker).
/* global Cesium */
import { STATUS, RIVER, riskClass } from './config.js';
import { ringBounds } from './data.js';

const C = Cesium;
const color = (css, a = 1) => C.Color.fromCssColorString(css).withAlpha(a);
const NO_DEPTH = Number.POSITIVE_INFINITY;
const FONT = '600 13px Inter, "Segoe UI", system-ui, sans-serif';

// ------------------------------------------------------------------ global AOI pins
export class AoiPins {
  constructor(viewer) {
    this.viewer = viewer;
    this.ds = new C.CustomDataSource('aoi-pins');
    viewer.dataSources.add(this.ds);
    this.pinBuilder = new C.PinBuilder();
    this.byKey = new Map();
  }

  render(aois) {
    this.ds.entities.removeAll();
    this.byKey.clear();
    for (const a of aois) {
      const rc = riskClass(a.stats?.risk_mean);
      const [w, s, e, n] = a.bbox;
      const pin = this.ds.entities.add({
        position: C.Cartesian3.fromDegrees(a.center[0], a.center[1]),
        billboard: {
          image: this.pinBuilder.fromColor(color(rc.color), 46).toDataURL(),
          verticalOrigin: C.VerticalOrigin.BOTTOM,
          disableDepthTestDistance: NO_DEPTH,
          scaleByDistance: new C.NearFarScalar(2e5, 1.0, 2e7, 0.75),
        },
        label: {
          text: a.user ? `${a.landscape || a.key}\nUSER AREA` : `${a.key}\n${a.country}`,
          font: FONT,
          fillColor: C.Color.WHITE,
          showBackground: true,
          backgroundColor: color('#0d141c', 0.82),
          backgroundPadding: new C.Cartesian2(8, 5),
          verticalOrigin: C.VerticalOrigin.TOP,
          pixelOffset: new C.Cartesian2(0, 6),
          disableDepthTestDistance: NO_DEPTH,
          scaleByDistance: new C.NearFarScalar(2e5, 1.0, 2e7, 0.8),
        },
      });
      pin.careew = { type: 'aoi', key: a.key };
      const box = this.ds.entities.add({
        polyline: {
          positions: C.Cartesian3.fromDegreesArray([w, s, e, s, e, n, w, n, w, s]),
          width: 2,
          material: color(rc.color, 0.95),
          distanceDisplayCondition: new C.DistanceDisplayCondition(0, 4e5),
        },
      });
      box.careew = { type: 'aoi', key: a.key };
      const ents = [pin, box];
      // user-drawn areas: keep the box the user drew visible (dashed white) next to the analysed blocks
      if (Array.isArray(a.user_bbox) && a.user_bbox.length === 4) {
        const [uw, us, ue, un] = a.user_bbox;
        const ub = this.ds.entities.add({
          polyline: {
            positions: C.Cartesian3.fromDegreesArrayHeights([uw, us, 8, ue, us, 8, ue, un, 8, uw, un, 8, uw, us, 8]),
            width: 2.5,
            material: new C.PolylineDashMaterialProperty({ color: color('#ffffff', 0.95), gapColor: color('#000000', 0.35), dashLength: 14 }),
          },
        });
        ub.careew = { type: 'aoi', key: a.key };
        ents.push(ub);
      }
      this.byKey.set(a.key, ents);
    }
  }

  /** Hide the active AOI's pin (its own layers replace it). */
  setActive(key) {
    for (const [k, ents] of this.byKey) ents[0].show = k !== key;
  }
}

// ------------------------------------------------------------------ per-AOI layers
export class AoiView {
  constructor(viewer, basemaps) {
    this.viewer = viewer;
    this.basemaps = basemaps;
    this.ds = {
      boundary: new C.CustomDataSource('aoi-boundary'),
      hotspots: new C.CustomDataSource('hotspots'),
      network: new C.CustomDataSource('rivers-network'),
      local: new C.CustomDataSource('rivers-local'),
      stations: new C.CustomDataSource('stations'),
      pixel: new C.CustomDataSource('pixel'),
    };
    Object.values(this.ds).forEach((d) => viewer.dataSources.add(d));
    // raster overlay state, bottom -> top
    this.rasterKinds = ['rgb', 'ndvi', 'risk'];
    this.raster = Object.fromEntries(this.rasterKinds.map((k) => [k, { layer: null, url: null, token: 0 }]));
    this.visible = { rgb: false, ndvi: false, risk: true, hotspots: true, network: true, local: true, stations: true };
    this.alpha = { rgb: 1.0, ndvi: 0.8, risk: 0.85 };
    this.bundle = null;
    this.month = null;
    this.selectedId = null;
    this.hotspotEntities = new Map();
    this.onRasterError = () => {};
  }

  get active() { return !!this.bundle; }

  rect() {
    const [w, s, e, n] = this.aoi.bbox;
    return C.Rectangle.fromDegrees(w, s, e, n);
  }

  /** Activate an AOI with its loaded bundle. */
  load(aoi, bundle) {
    this.clear();
    this.aoi = aoi;
    this.bundle = bundle;
    this.drawBoundary();
    this.drawRivers();
    this.drawHotspots();
    this.drawStations();
    this.applyVisibility();
  }

  clear() {
    Object.values(this.ds).forEach((d) => d.entities.removeAll());
    for (const k of this.rasterKinds) this.removeRaster(k);
    this.hotspotEntities.clear();
    this.bundle = null;
    this.aoi = null;
    this.month = null;
    this.selectedId = null;
  }

  // ---------------------------------------------------------------- rasters
  rasterUrl(kind, month) {
    const meta = this.bundle.meta || {};
    if (kind === 'rgb') {
      const list = meta.months_rgb || [];
      if (!list.length) return null;
      // most recent RGB month not after the selected month (else the earliest)
      const m = [...list].reverse().find((x) => x <= month) || list[0];
      return `${this.bundle.dir}rgb/${m}.png`;
    }
    return `${this.bundle.dir}${kind}/${month}.png`;
  }

  async setMonth(month) {
    this.month = month;
    await Promise.all(this.rasterKinds.map((k) => this.refreshRaster(k)));
  }

  async refreshRaster(kind) {
    const st = this.raster[kind];
    if (!this.bundle || !this.visible[kind] || !this.month) { this.removeRaster(kind); return; }
    const url = this.rasterUrl(kind, this.month);
    if (!url) { this.removeRaster(kind); return; }
    if (url === st.url && st.layer) return;
    const token = ++st.token;
    let provider;
    try {
      provider = await C.SingleTileImageryProvider.fromUrl(url, { rectangle: this.rect() });
    } catch (e) {
      if (token === st.token) { this.removeRaster(kind); this.onRasterError(kind, url); }
      return;
    }
    if (token !== st.token || !this.bundle) return;           // superseded by a newer request
    const layer = new C.ImageryLayer(provider, { alpha: this.alpha[kind] });
    if (kind !== 'rgb') layer.magnificationFilter = C.TextureMagnificationFilter.NEAREST;
    const layers = this.viewer.imageryLayers;
    layer.show = !this.suppressed;                              // hidden while a hotspot time-lapse runs
    layers.add(layer, this.insertIndex(kind));
    if (st.layer) layers.remove(st.layer, true);                // swap after the new one is in
    st.layer = layer;
    st.url = url;
  }

  /** Hide (true) or restore (false) the AOI raster overlays, e.g. while a hotspot time-lapse plays. */
  setSuppressed(v) {
    this.suppressed = v;
    for (const k of this.rasterKinds) if (this.raster[k].layer) this.raster[k].layer.show = !v;
  }

  /** Show / hide the translucent fill of one hotspot (its outline and label stay). */
  setHotspotFill(id, v) {
    const h = this.hotspotEntities.get(id);
    if (h) h.fill.show = v;
  }

  /** Keep rgb < ndvi < risk < labels in the imagery stack. */
  insertIndex(kind) {
    const layers = this.viewer.imageryLayers;
    const order = this.rasterKinds.indexOf(kind);
    for (let i = order + 1; i < this.rasterKinds.length; i++) {
      const above = this.raster[this.rasterKinds[i]].layer;
      if (above) return layers.indexOf(above);
    }
    return this.basemaps.overlayIndex();
  }

  removeRaster(kind) {
    const st = this.raster[kind];
    st.token++;
    if (st.layer) this.viewer.imageryLayers.remove(st.layer, true);
    st.layer = null;
    st.url = null;
  }

  setAlpha(kind, a) {
    this.alpha[kind] = a;
    if (this.raster[kind].layer) this.raster[kind].layer.alpha = a;
  }

  /** Warm the browser cache so playback is smooth. */
  prefetch(month) {
    if (!this.bundle) return;
    for (const k of this.rasterKinds) {
      if (!this.visible[k]) continue;
      const u = this.rasterUrl(k, month);
      if (u) { const img = new Image(); img.src = u; }
    }
  }

  // ---------------------------------------------------------------- visibility
  setVisible(what, v) {
    this.visible[what] = v;
    if (this.rasterKinds.includes(what)) this.refreshRaster(what);
    else this.applyVisibility();
  }

  applyVisibility() {
    this.ds.hotspots.show = this.visible.hotspots;
    this.ds.network.show = this.visible.network;
    this.ds.local.show = this.visible.local;
    this.ds.stations.show = this.visible.stations;
  }

  // ---------------------------------------------------------------- vectors
  drawBoundary() {
    const [w, s, e, n] = this.aoi.bbox;
    const ring = C.Cartesian3.fromDegreesArrayHeights([w, s, 4, e, s, 4, e, n, 4, w, n, 4, w, s, 4]);
    this.ds.boundary.entities.add({
      polyline: {
        positions: ring, width: 3,
        material: new C.PolylineOutlineMaterialProperty({
          color: color('#ffffff', 0.95), outlineColor: color('#000000', 0.55), outlineWidth: 1.5 }),
      },
    });
    this.ds.boundary.entities.add({
      position: C.Cartesian3.fromDegrees(w, n, 4),
      label: {
        text: `${this.aoi.key} · 5.12 × 5.12 km AOI`, font: '600 12px Inter, system-ui, sans-serif',
        fillColor: C.Color.WHITE, showBackground: true, backgroundColor: color('#0d141c', 0.8),
        backgroundPadding: new C.Cartesian2(7, 4), horizontalOrigin: C.HorizontalOrigin.LEFT,
        verticalOrigin: C.VerticalOrigin.BOTTOM, pixelOffset: new C.Cartesian2(0, -6),
        disableDepthTestDistance: NO_DEPTH,
      },
    });
  }

  drawRivers() {
    const net = this.bundle.network?.features || [];
    const local = this.bundle.local?.features || [];
    const netIds = new Set(net.map((f) => f.properties?.HYRIV_ID));
    // local reaches first (thin), skipping ones drawn as part of the network
    for (const f of local) {
      if (netIds.has(f.properties?.HYRIV_ID)) continue;
      this.addLine(this.ds.local, f, {
        width: 1.2 + 0.4 * (f.properties?.ORD_STRA || 1),
        material: color(RIVER.local, 0.75),
        height: 3,
      });
    }
    for (const f of net) {
      const p = f.properties || {};
      const order = p.ORD_STRA || 1;
      let style;
      if (p.role === 'outlet') {
        style = { width: 4 + 0.9 * order, material: new C.PolylineGlowMaterialProperty({ glowPower: 0.3, color: color(RIVER.outlet) }), height: 6 };
      } else if (p.role === 'downstream') {
        style = { width: 1.5 + 0.5 * order, material: new C.PolylineDashMaterialProperty({ color: color(RIVER.downstream), dashLength: 14 }), height: 5 };
      } else {
        style = { width: 2 + 0.9 * order, material: new C.PolylineGlowMaterialProperty({ glowPower: 0.3, color: color(RIVER.upstream) }), height: 5 };
      }
      const ent = this.addLine(this.ds.network, f, style);
      ent.careew = { type: 'river', props: p };
    }
  }

  addLine(ds, f, { width, material, height }) {
    const coords = f.geometry?.type === 'MultiLineString' ? f.geometry.coordinates.flat() : f.geometry.coordinates;
    const flat = [];
    for (const c of coords) flat.push(c[0], c[1], height);
    return ds.entities.add({ polyline: { positions: C.Cartesian3.fromDegreesArrayHeights(flat), width, material } });
  }

  drawHotspots() {
    const feats = this.bundle.hotspots?.features || [];
    for (const f of feats) {
      const p = f.properties || {};
      const st = STATUS[p.status] || STATUS.watch;
      const ring = f.geometry.coordinates[0];
      const flat = [];
      for (const c of ring) flat.push(c[0], c[1], 3);
      const isAbstain = p.status === 'abstain';
      const fill = this.ds.hotspots.entities.add({
        polygon: {
          hierarchy: C.Cartesian3.fromDegreesArrayHeights(flat),
          height: 2, perPositionHeight: false,
          material: isAbstain
            ? new C.StripeMaterialProperty({ evenColor: color(st.color, 0.38), oddColor: color(st.color, 0.04), repeat: 9, orientation: C.StripeOrientation.VERTICAL })
            : color(st.color, 0.14),
        },
      });
      const line = this.ds.hotspots.entities.add({
        polyline: {
          positions: C.Cartesian3.fromDegreesArrayHeights(flat),
          width: isAbstain ? 3 : 4,
          material: isAbstain
            ? new C.PolylineDashMaterialProperty({ color: color(st.color), gapColor: color('#000000', 0.25), dashLength: 12 })
            : new C.PolylineOutlineMaterialProperty({ color: color(st.color), outlineColor: color('#000000', 0.6), outlineWidth: 1 }),
        },
      });
      const { bbox } = ringBounds(f);
      const label = this.ds.hotspots.entities.add({
        show: p.show_label !== false,   // keep the map readable: only the top hotspots are labelled
        position: C.Cartesian3.fromDegrees((bbox[0] + bbox[2]) / 2, bbox[3], 6),
        label: {
          text: p.status === 'active_degradation'
            ? `${p.label ?? '?'} · ACTIVE ${p.months_below ?? '?'} mo · ${(p.area_ha ?? NaN).toFixed(1)} ha`
            : `${p.label ?? '?'} · p=${(p.risk_mean ?? NaN).toFixed(3)} · ${(p.area_ha ?? NaN).toFixed(1)} ha`,
          font: FONT,
          fillColor: color(st.text),
          showBackground: true,
          backgroundColor: color(st.color, 0.92),
          backgroundPadding: new C.Cartesian2(7, 4),
          verticalOrigin: C.VerticalOrigin.BOTTOM,
          pixelOffset: new C.Cartesian2(0, -4),
          disableDepthTestDistance: NO_DEPTH,
          distanceDisplayCondition: new C.DistanceDisplayCondition(0, 6e4),
        },
      });
      for (const e of [fill, line, label]) e.careew = { type: 'hotspot', feature: f };
      this.hotspotEntities.set(p.id ?? p.label, { fill, line, label, feature: f });
    }
  }

  selectHotspot(id) {
    for (const [k, h] of this.hotspotEntities) {
      const sel = k === id;
      h.label.label.scale = sel ? 1.15 : 1.0;
      h.line.polyline.width = sel ? 7 : (h.feature.properties.status === 'abstain' ? 3 : 4);
    }
    this.selectedId = id;
  }

  drawStations() {
    for (const s of this.bundle.hydro?.stations || []) {
      if (s.lon == null || s.lat == null) continue;
      const ok = s.available !== false;
      const ent = this.ds.stations.entities.add({
        position: C.Cartesian3.fromDegrees(s.lon, s.lat, 8),
        billboard: { image: gaugeIcon(ok), verticalOrigin: C.VerticalOrigin.CENTER, disableDepthTestDistance: NO_DEPTH },
        label: {
          text: s.name, font: '500 12px Inter, system-ui, sans-serif',
          fillColor: color(ok ? '#e8f6ff' : '#b8c1cc'), showBackground: true,
          backgroundColor: color('#0d141c', 0.78), backgroundPadding: new C.Cartesian2(6, 3),
          horizontalOrigin: C.HorizontalOrigin.LEFT, pixelOffset: new C.Cartesian2(16, 0),
          disableDepthTestDistance: NO_DEPTH,
          distanceDisplayCondition: new C.DistanceDisplayCondition(0, 9e4),
        },
      });
      ent.careew = { type: 'station', station: s };
    }
  }

  markPixel(lon, lat) {
    this.ds.pixel.entities.removeAll();
    this.ds.pixel.entities.add({
      position: C.Cartesian3.fromDegrees(lon, lat, 6),
      billboard: { image: crosshairIcon(), disableDepthTestDistance: NO_DEPTH },
    });
  }

  contains(lon, lat) {
    if (!this.aoi) return false;
    const [w, s, e, n] = this.aoi.bbox;
    return lon >= w && lon <= e && lat >= s && lat <= n;
  }
}

// ------------------------------------------------------------------ canvas icons
let _gauge = {};
function gaugeIcon(ok) {
  if (_gauge[ok]) return _gauge[ok];
  const c = document.createElement('canvas'); c.width = c.height = 26;
  const g = c.getContext('2d');
  g.beginPath(); g.arc(13, 13, 10, 0, Math.PI * 2);
  g.fillStyle = ok ? '#0b3a5c' : '#2a3038'; g.fill();
  g.lineWidth = 2.5; g.strokeStyle = ok ? '#7fdcff' : '#8a949e'; g.stroke();
  g.beginPath();   // little wave
  g.moveTo(6, 14); g.quadraticCurveTo(9.5, 9, 13, 14); g.quadraticCurveTo(16.5, 19, 20, 14);
  g.lineWidth = 2; g.strokeStyle = ok ? '#ffffff' : '#9aa3ad'; g.stroke();
  _gauge[ok] = c.toDataURL();
  return _gauge[ok];
}
let _cross;
function crosshairIcon() {
  if (_cross) return _cross;
  const c = document.createElement('canvas'); c.width = c.height = 34;
  const g = c.getContext('2d');
  g.strokeStyle = '#000'; g.lineWidth = 4;
  const draw = () => { g.beginPath(); g.arc(17, 17, 8, 0, Math.PI * 2); g.moveTo(17, 1); g.lineTo(17, 10); g.moveTo(17, 24); g.lineTo(17, 33); g.moveTo(1, 17); g.lineTo(10, 17); g.moveTo(24, 17); g.lineTo(33, 17); g.stroke(); };
  draw(); g.strokeStyle = '#fffb00'; g.lineWidth = 2; draw();
  _cross = c.toDataURL();
  return _cross;
}
