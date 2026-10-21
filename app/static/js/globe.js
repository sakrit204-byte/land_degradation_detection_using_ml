// Cesium viewer setup: no Cesium ion (no token) - Esri / OSM imagery on an ellipsoid globe.
/* global Cesium */
import { BASEMAPS, LABELS_URL } from './config.js';

const C = Cesium;

export function createViewer(containerId, creditContainer) {
  const viewer = new C.Viewer(containerId, {
    baseLayer: false,                 // disables the default ion imagery
    baseLayerPicker: false,
    geocoder: false,                  // ion geocoder needs a token
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    terrainProvider: new C.EllipsoidTerrainProvider(),
    creditContainer,
    msaaSamples: 4,
  });
  const scene = viewer.scene;
  scene.backgroundColor = C.Color.fromCssColorString('#05080c');
  scene.globe.baseColor = C.Color.fromCssColorString('#0b1622');
  scene.globe.maximumScreenSpaceError = 1.6;   // a little sharper than default
  scene.globe.showGroundAtmosphere = true;
  scene.fog.enabled = true;
  scene.postProcessStages.fxaa.enabled = true;
  scene.screenSpaceCameraController.minimumZoomDistance = 300;
  // the default double-click "track entity" behaviour is confusing for analysts
  viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
  return viewer;
}

/** Manages the base layer (index 0) and the reference-labels layer (always on top). */
export class Basemaps {
  constructor(viewer) {
    this.viewer = viewer;
    this.base = null;
    this.labels = null;
    this.current = null;
  }

  async set(id) {
    const def = BASEMAPS[id] || BASEMAPS.esri;
    const layers = this.viewer.imageryLayers;
    const provider = def.kind === 'osm'
      ? new C.OpenStreetMapImageryProvider({ url: def.url })
      : C.ArcGisMapServerImageryProvider.fromUrl(def.url, { enablePickFeatures: false });
    const layer = def.kind === 'osm'
      ? new C.ImageryLayer(provider)
      : C.ImageryLayer.fromProviderAsync(provider);
    layers.add(layer, 0);
    if (this.base) layers.remove(this.base, true);
    this.base = layer;
    this.current = id;
    return layer;
  }

  ensureLabels() {
    if (this.labels) return this.labels;
    this.labels = C.ImageryLayer.fromProviderAsync(
      C.ArcGisMapServerImageryProvider.fromUrl(LABELS_URL, { enablePickFeatures: false }));
    this.viewer.imageryLayers.add(this.labels);   // top
    return this.labels;
  }

  setLabelsVisible(v) { this.ensureLabels().show = v; }

  /** Index at which data overlays should be inserted (just below the labels). */
  overlayIndex() {
    const layers = this.viewer.imageryLayers;
    return this.labels ? layers.indexOf(this.labels) : layers.length;
  }
}

// ------------------------------------------------------------------ navigation widgets
const NICE = [1, 2, 5];
function niceDistance(maxMeters) {
  const p = Math.pow(10, Math.floor(Math.log10(maxMeters)));
  let best = p;
  for (const n of NICE) if (n * p <= maxMeters) best = n * p;
  return best;
}

/** Compass (rotates with heading; click = north up) + scale bar + cursor readout. */
export function installNavWidgets(viewer, { compassEl, scaleEl, readoutEl }) {
  const scene = viewer.scene, camera = viewer.camera;
  const geodesic = new C.EllipsoidGeodesic();
  let last = 0;

  function updateScale() {
    const canvas = scene.canvas;
    const y = canvas.clientHeight - 40, x = canvas.clientWidth / 2;
    const a = camera.pickEllipsoid(new C.Cartesian2(x, y));
    const b = camera.pickEllipsoid(new C.Cartesian2(x + 100, y));
    if (!a || !b) { scaleEl.style.visibility = 'hidden'; return; }
    geodesic.setEndPoints(C.Cartographic.fromCartesian(a), C.Cartographic.fromCartesian(b));
    const mPerPx = geodesic.surfaceDistance / 100;
    const d = niceDistance(mPerPx * 120);
    scaleEl.style.visibility = 'visible';
    scaleEl.querySelector('.bar').style.width = `${Math.round(d / mPerPx)}px`;
    scaleEl.querySelector('.txt').textContent = d >= 1000 ? `${d / 1000} km` : `${d} m`;
  }

  scene.postRender.addEventListener(() => {
    const now = performance.now();
    if (now - last < 120) return;
    last = now;
    compassEl.querySelector('.needle').style.transform = `rotate(${-C.Math.toDegrees(camera.heading)}deg)`;
    updateScale();
    const h = camera.positionCartographic.height;
    readoutEl.querySelector('.alt').textContent =
      `Eye ${h > 10000 ? (h / 1000).toFixed(0) + ' km' : (h / 1000).toFixed(2) + ' km'}`;
  });

  compassEl.addEventListener('click', () => {
    camera.flyTo({
      destination: camera.positionWC.clone(),
      orientation: { heading: 0, pitch: camera.pitch, roll: 0 },
      duration: 0.6,
    });
  });

  const handler = new C.ScreenSpaceEventHandler(scene.canvas);
  handler.setInputAction((m) => {
    const p = camera.pickEllipsoid(m.endPosition);
    const el = readoutEl.querySelector('.ll');
    if (!p) { el.textContent = ''; return; }
    const c = C.Cartographic.fromCartesian(p);
    const lat = C.Math.toDegrees(c.latitude), lon = C.Math.toDegrees(c.longitude);
    el.textContent = `${Math.abs(lat).toFixed(5)}°${lat >= 0 ? 'N' : 'S'}  ${Math.abs(lon).toFixed(5)}°${lon >= 0 ? 'E' : 'W'}`;
  }, C.ScreenSpaceEventType.MOUSE_MOVE);
}

/** Smooth tilted 3D flight to a lon/lat box. */
export function flyToBox(viewer, bbox, { duration = 2.8, pitchDeg = -52, range } = {}) {
  const [w, s, e, n] = bbox;
  const center = C.Cartesian3.fromDegrees((w + e) / 2, (s + n) / 2);
  const span = C.Cartesian3.distance(C.Cartesian3.fromDegrees(w, s), C.Cartesian3.fromDegrees(e, n));
  return new Promise((resolve) => {
    viewer.camera.flyToBoundingSphere(new C.BoundingSphere(center, span / 2), {
      offset: new C.HeadingPitchRange(C.Math.toRadians(8), C.Math.toRadians(pitchDeg), range ?? span * 1.75),
      duration,
      complete: resolve,
      cancel: resolve,
    });
  });
}

export function flyHome(viewer, lonLat = [40, 12], duration = 2.5) {
  viewer.camera.flyTo({
    destination: C.Cartesian3.fromDegrees(lonLat[0], lonLat[1], 1.75e7),
    orientation: { heading: 0, pitch: C.Math.toRadians(-90), roll: 0 },
    duration,
  });
}
