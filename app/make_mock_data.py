"""Generate MOCK data for the CARE-EW web UI (development only).

Writes files in exactly the format described in docs/UI_DATA_SPEC.md into
app/static/data/ so the front-end can be developed before the real pipeline
(care_ew/export.py) has produced results.

EVERYTHING WRITTEN HERE IS SYNTHETIC. Every JSON file carries "mock": true and the
UI shows a prominent "MOCK DATA" badge. Never cite these numbers.

Usage:
    .venv/Scripts/python app/make_mock_data.py            # 3 AOIs
    .venv/Scripts/python app/make_mock_data.py --force    # overwrite even real data

Dependency-free apart from numpy (PNG files are written with zlib).
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import zlib
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parent
OUT = APP / "static" / "data"

H = W = 500                      # 10 m grid over a 5 x 5 km box
PIX_HA = 0.01                    # 10 m x 10 m = 0.01 ha
MONTHS = [f"{y}-{m:02d}" for y in range(2019, 2027) for m in range(1, 13)]
MONTHS = MONTHS[: MONTHS.index("2026-09") + 1]
MONTHS_RISK = MONTHS[MONTHS.index("2024-10"):]            # 24 months
MONTHS_RGB = MONTHS_RISK

# AOI centres are the real study sites; everything else is invented.
AOIS = [
    dict(key="NPL_chure", country="Nepal", landscape="Siwalik (Chure) foothill forest/agri mosaic",
         rationale="Chure range: documented forest loss, erosion and sediment delivery to the Terai.",
         center=(85.95, 27.05), flow_deg=-90, runoff=0.035, season_peak=8, n_hot=7, lc=[10, 40, 20],
         soil=(150, 128, 98), seed=11, risk_bias=0.02),
    dict(key="ETH_tigray", country="Ethiopia", landscape="Highland cropland and degraded hillslopes",
         rationale="Tigray highlands: classic soil-degradation region; strong drought & conflict shocks (2020-22).",
         center=(39.50, 13.60), flow_deg=180, runoff=0.006, season_peak=9, n_hot=6, lc=[40, 20, 60],
         soil=(168, 140, 108), seed=23, risk_bias=0.07),
    dict(key="BRA_matopiba", country="Brazil", landscape="Cerrado savanna frontier",
         rationale="Western Bahia (MATOPIBA): rapid native-vegetation conversion; strong true positives.",
         center=(-45.90, -12.20), flow_deg=10, runoff=0.012, season_peak=2, n_hot=8, lc=[20, 40, 30],
         soil=(176, 146, 112), seed=37, risk_bias=0.04),
]
LC_NAME = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare", 80: "water"}
DRIVERS = ["Residual R (6-mo mean)", "Fraction below expectation (21 px)", "NDVI z (3-mo min)",
           "Rain anomaly P6", "Soil moisture SM3", "Distance to river", "Neighbour residual (5 px)",
           "Landcover = crop", "Slope proxy", "Temperature anomaly T1"]
VEG_LEVEL = {10: 0.9, 20: 0.6, 30: 0.5, 40: 0.62, 60: 0.18}
VEG_COL = {10: (24, 56, 30), 20: (70, 88, 48), 30: (110, 122, 66), 40: (88, 128, 52), 60: (150, 132, 104)}


# ----------------------------------------------------------------------------- helpers
def bbox_of(lon, lat, half_km=2.5):
    """Same formula as care_ew.config.AOI.bbox."""
    dlat = half_km / 110.574
    dlon = half_km / (111.320 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def write_png(path: Path, rgba: np.ndarray):
    """Minimal RGB(A) (H, W, 3|4) uint8 PNG writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = rgba.shape[:2]
    if rgba.shape[2] == 3:
        rgba = np.dstack([rgba, np.full((h, w), 255, np.uint8)])
    raw = b"".join(b"\x00" + rgba[i].tobytes() for i in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def write_json(path: Path, obj, indent=None):
    path.write_text(json.dumps(obj, indent=indent), encoding="utf-8")


def smooth_noise(rng, scale_px, shape=(H, W)):
    """Gaussian-filtered white noise via FFT, normalised to zero mean / unit sd."""
    n = rng.standard_normal(shape)
    fy = np.fft.fftfreq(shape[0])[:, None]
    fx = np.fft.fftfreq(shape[1])[None, :]
    g = np.exp(-2 * (math.pi * scale_px) ** 2 * (fx ** 2 + fy ** 2))
    out = np.real(np.fft.ifft2(np.fft.fft2(n) * g))
    return (out - out.mean()) / (out.std() + 1e-9)


def ramp(values, stops):
    """Piecewise-linear colour ramp. stops = [(v, (r,g,b,a)), ...] sorted by v."""
    v = np.asarray(values, float)
    xs = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], float)
    out = np.empty(v.shape + (4,), float)
    for k in range(4):
        out[..., k] = np.interp(v, xs, cols[:, k])
    return out


RISK_STOPS = [(0.15, (255, 226, 77, 150)), (0.35, (255, 150, 30, 190)),
              (0.6, (232, 40, 28, 215)), (1.0, (120, 0, 10, 235))]
NDVI_STOPS = [(-3, (122, 72, 24, 220)), (-1.5, (196, 150, 90, 190)), (0, (245, 245, 240, 15)),
              (1.5, (110, 180, 90, 190)), (3, (20, 110, 40, 220))]
ABSTAIN_RGBA = (155, 89, 255, 210)


def risk_png(risk, abstain):
    img = ramp(np.clip(risk, 0, 1), RISK_STOPS)
    img[risk < 0.15, 3] = 0
    rr, cc = np.mgrid[0:H, 0:W]
    hatch = ((rr + cc) % 8) < 3                        # diagonal hatch for abstain pixels
    img[abstain & hatch] = ABSTAIN_RGBA
    img[abstain & ~hatch] = (155, 89, 255, 70)
    return img.astype(np.uint8)


def km_to_deg(lat, x_km, y_km):
    return x_km / (111.320 * math.cos(math.radians(lat))), y_km / 110.574


# ----------------------------------------------------------------------------- rivers
class Reach:
    def __init__(self, pts, children):
        self.pts = pts                  # downstream -> upstream, km coords
        self.children = children
        self.order = 1
        self.upland = 0.0
        self.role = "upstream"


def grow_reach(rng, start, heading, level, length_scale=1.0):
    """Random-walk a meandering reach upstream from `start`, then branch."""
    length = rng.uniform(1.4, 3.0) * (0.75 + 0.18 * level) * length_scale
    n = 10
    pts = [np.array(start, float)]
    h = heading
    for _ in range(n):
        h += rng.normal(0, 14)
        step = length / n
        pts.append(pts[-1] + step * np.array([math.cos(math.radians(h)), math.sin(math.radians(h))]))
    children = []
    if level > 0:
        spread = rng.uniform(25, 55)
        lv_a = level - 1
        lv_b = level - 1 if rng.random() < 0.6 else max(level - 2, 0)
        children = [grow_reach(rng, pts[-1], h + spread, lv_a),
                    grow_reach(rng, pts[-1], h - spread * rng.uniform(0.7, 1.2), lv_b)]
    return Reach(pts, children)


def strahler(r: Reach, runoff_area_per_km=1.6):
    seg_len = sum(np.linalg.norm(r.pts[i + 1] - r.pts[i]) for i in range(len(r.pts) - 1))
    if not r.children:
        r.order, r.upland = 1, seg_len * runoff_area_per_km * 1.8
        return r
    for c in r.children:
        strahler(c, runoff_area_per_km)
    o = sorted([c.order for c in r.children], reverse=True)
    r.order = o[0] + 1 if len(o) > 1 and o[0] == o[1] else o[0]
    r.upland = sum(c.upland for c in r.children) + seg_len * runoff_area_per_km
    return r


def walk(r: Reach):
    yield r
    for c in r.children:
        yield from walk(c)


def build_rivers(rng, a):
    """Upstream tree flowing INTO the AOI, outlet reach crossing it, dashed downstream reaches."""
    lon0, lat0 = a["center"]
    flow = a["flow_deg"]                      # direction of flow (math angle, 0 = east)
    up = flow + 180
    fx, fy = math.cos(math.radians(flow)), math.sin(math.radians(flow))
    outlet_pt = np.array([1.9 * fx, 1.9 * fy]) + rng.normal(0, 0.3, 2)
    # outlet reach: from the AOI's downstream edge, upstream right across the AOI
    root = grow_reach(rng, outlet_pt, up + rng.normal(0, 10), 4, length_scale=1.8)
    root.children = [grow_reach(rng, root.pts[-1], up + 35, 4), grow_reach(rng, root.pts[-1], up - 40, 3)]
    strahler(root)
    root.role = "outlet"
    reaches = list(walk(root))
    # downstream continuation (larger reaches leaving the AOI)
    down, cur, order, upl = [], outlet_pt, root.order, root.upland
    h = flow
    for k in range(4):
        pts = [cur]
        for _ in range(12):
            h += rng.normal(0, 9)
            pts.append(pts[-1] + 0.28 * np.array([math.cos(math.radians(h)), math.sin(math.radians(h))]))
        rr = Reach(pts[::-1], [])            # stored downstream -> upstream like the others
        upl += rng.uniform(20, 60)
        if k == 1:
            order += 1
        rr.order, rr.upland, rr.role = order, upl, "downstream"
        down.append(rr)
        cur = pts[-1]
    reaches += down

    # unrelated local streams near the AOI (rivers_local only)
    local_extra = []
    for _ in range(9):
        p = rng.uniform(-4.5, 4.5, 2)
        rr = grow_reach(rng, p, rng.uniform(0, 360), rng.integers(0, 2), length_scale=0.6)
        strahler(rr)
        local_extra += list(walk(rr))

    def to_feat(r, rid, role=True):
        coords = []
        for x, y in r.pts[::-1]:             # write upstream -> downstream (flow direction)
            dx, dy = km_to_deg(lat0, x, y)
            coords.append([round(lon0 + dx, 6), round(lat0 + dy, 6)])
        props = dict(HYRIV_ID=rid, ORD_STRA=int(r.order), DIS_AV_CMS=round(r.upland * a["runoff"], 3),
                     UPLAND_SKM=round(r.upland, 1))
        if role:
            props["role"] = r.role
        return dict(type="Feature", properties=props, geometry=dict(type="LineString", coordinates=coords))

    base = 40_000_000 + a["seed"] * 10_000
    net = [to_feat(r, base + i) for i, r in enumerate(reaches)]
    local = [to_feat(r, base + i, role=False) for i, r in enumerate(reaches)]
    local += [to_feat(r, base + 5000 + i, role=False) for i, r in enumerate(local_extra)]

    def near(f):                              # keep local reaches within ~6 km of centre
        lon, lat = f["geometry"]["coordinates"][0]
        return abs(lon - lon0) < 0.07 and abs(lat - lat0) < 0.06
    local = [f for f in local if near(f)]
    return net, local, root, down


def rasterize_rivers(net_feats, bbox):
    """Pixel mask of river channels (for the mock RGB)."""
    w, s, e, n = bbox
    mask = np.zeros((H, W), bool)
    rr, cc = np.mgrid[0:H, 0:W]
    for f in net_feats:
        rad = 0.6 + 0.5 * f["properties"]["ORD_STRA"]
        c = np.array(f["geometry"]["coordinates"])
        for i in range(len(c) - 1):
            for t in np.linspace(0, 1, 8):
                lon, lat = c[i] + t * (c[i + 1] - c[i])
                col, row = (lon - w) / (e - w) * W, (n - lat) / (n - s) * H
                if -5 < col < W + 5 and -5 < row < H + 5:
                    r0, r1 = int(max(row - rad - 1, 0)), int(min(row + rad + 2, H))
                    c0, c1 = int(max(col - rad - 1, 0)), int(min(col + rad + 2, W))
                    if r0 < r1 and c0 < c1:
                        sub = (rr[r0:r1, c0:c1] - row) ** 2 + (cc[r0:r1, c0:c1] - col) ** 2 <= rad ** 2
                        mask[r0:r1, c0:c1] |= sub
    return mask


# ----------------------------------------------------------------------------- one AOI
def make_aoi(a):
    rng = np.random.default_rng(a["seed"])
    lon0, lat0 = a["center"]
    bbox = bbox_of(lon0, lat0)
    w, s, e, n = bbox
    d = OUT / "aois" / a["key"]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)

    # ---- rivers
    net, local, root, down = build_rivers(rng, a)
    write_json(d / "rivers_network.geojson", dict(type="FeatureCollection", mock=True, features=net))
    write_json(d / "rivers_local.geojson", dict(type="FeatureCollection", mock=True, features=local))
    river_mask = rasterize_rivers(net, bbox)

    # ---- static landscape: Voronoi "parcels" (fields / forest stands), each with a land-cover class
    rr, cc = np.mgrid[0:H, 0:W]
    n_par = 160
    seeds = np.c_[rng.uniform(0, H, n_par), rng.uniform(0, W, n_par)]
    warp_r, warp_c = 6 * smooth_noise(rng, 12), 6 * smooth_noise(rng, 12)     # wobbly edges
    parcel = np.zeros((H, W), np.int32)
    best = np.full((H, W), np.inf)
    for k, (sy, sx) in enumerate(seeds):
        dd = (rr + warp_r - sy) ** 2 + (cc + warp_c - sx) ** 2
        better = dd < best
        parcel[better], best[better] = k, dd[better]
    macro = smooth_noise(rng, 60)                                         # forest on the "hills"
    lc_choice = np.array(a["lc"])
    par_lc = lc_choice[rng.choice(len(lc_choice), n_par, p=[0.5, 0.3, 0.2])]
    par_lc = np.where(macro[seeds[:, 0].astype(int), seeds[:, 1].astype(int)] > 0.6, lc_choice[0], par_lc)
    lc_codes = par_lc[parcel]
    par_veg = np.array([VEG_LEVEL.get(int(c), 0.5) for c in par_lc]) * rng.uniform(0.8, 1.1, n_par)
    par_phase = rng.uniform(-1.5, 1.5, n_par)                             # crop calendars differ
    veg = np.clip(par_veg[parcel] + 0.08 * smooth_noise(rng, 25) + 0.05 * smooth_noise(rng, 2), 0.05, 1)
    vegc_map = np.array([VEG_COL.get(int(c), (70, 96, 50)) for c in par_lc], float)[parcel]
    crop_mask = lc_codes == 40
    phase_map = par_phase[parcel]
    edge = np.zeros((H, W), bool)                                         # parcel boundaries / tracks
    edge[1:, :] |= parcel[1:, :] != parcel[:-1, :]
    edge[:, 1:] |= parcel[:, 1:] != parcel[:, :-1]

    base_risk = np.clip(0.05 + a["risk_bias"] + 0.04 * smooth_noise(rng, 25), 0, 0.14 + 2 * a["risk_bias"])
    unc = smooth_noise(rng, 20)

    # ---- hotspot blobs (synthetic degradation processes)
    T_all = len(MONTHS)
    blobs = []
    statuses = ["warning", "warning", "watch", "abstain", "active_degradation", "watch", "warning", "watch"]
    for k in range(a["n_hot"]):
        cy, cx = rng.uniform(60, H - 60), rng.uniform(60, W - 60)
        for _ in range(30):                     # keep blobs apart
            if all((cy - b["cy"]) ** 2 + (cx - b["cx"]) ** 2 > 90 ** 2 for b in blobs):
                break
            cy, cx = rng.uniform(60, H - 60), rng.uniform(60, W - 60)
        status = statuses[k % len(statuses)]
        t0 = MONTHS.index(MONTHS_RISK[0]) + int(rng.integers(-6, 16))
        if status == "active_degradation":
            t0 = MONTHS.index(MONTHS_RISK[0]) - int(rng.integers(6, 14))
        blobs.append(dict(cy=cy, cx=cx, ry=rng.uniform(10, 26), rx=rng.uniform(10, 30),
                          ang=rng.uniform(0, math.pi), t0=t0, status=status,
                          amp={"warning": 0.85, "watch": 0.5, "abstain": 0.45, "active_degradation": 0.95}[status]))

    def blob_field(b):
        y, x = rr - b["cy"], cc - b["cx"]
        ca, sa = math.cos(b["ang"]), math.sin(b["ang"])
        u, v = (x * ca + y * sa) / b["rx"], (-x * sa + y * ca) / b["ry"]
        return np.exp(-(u ** 2 + v ** 2) * 1.2) * (1 + 0.15 * smooth_noise(rng, 3))

    for b in blobs:
        b["field"] = np.clip(blob_field(b), 0, None)

    def progress(b, ti):
        return 1 / (1 + math.exp(-(ti - b["t0"]) / 2.0))

    def risk_at(ti):
        r = base_risk.copy()
        ab = np.zeros((H, W), bool)
        for b in blobs:
            p = progress(b, ti)
            r = np.maximum(r, b["amp"] * p * b["field"])
            if b["status"] == "abstain":
                ab |= (b["field"] * p > 0.35)
        r += 0.03 * unc
        ab |= (unc > 2.3) & (r > 0.12)
        return np.clip(r, 0, 1), ab

    def degr_at(ti):                            # NDVI loss fraction 0..1
        g = np.zeros((H, W))
        for b in blobs:
            lag = 3 if b["status"] != "active_degradation" else 0
            p = 1 / (1 + math.exp(-(ti - b["t0"] - lag) / 2.5))
            g = np.maximum(g, b["field"] * p * (0.75 if b["status"] != "watch" else 0.4))
        return g

    def season(month_idx):
        m = int(MONTHS[month_idx][5:])
        return 0.75 + 0.25 * math.cos((m - a["season_peak"]) / 12 * 2 * math.pi)

    soil = np.array(a["soil"], float)
    tex = smooth_noise(rng, 0.8) + 0.5 * smooth_noise(rng, 3)
    water = np.array([40, 62, 70], float)
    sand = np.array([196, 180, 150], float)

    def rgb_at(ti):
        m = int(MONTHS[ti][5:])
        crop_season = 0.55 + 0.45 * np.cos((m - a["season_peak"] - phase_map) / 12 * 2 * np.pi)
        seas = np.where(crop_mask, crop_season, season(ti))
        v = np.clip(veg * seas * (1 - degr_at(ti)), 0, 1)[..., None]
        img = soil * (1 - v) + vegc_map * v
        img *= (1 + 0.07 * tex)[..., None]
        img = np.where(edge[..., None], img * 0.88 + sand * 0.12, img)
        img = np.where(river_mask[..., None], water * 0.8 + sand * 0.2, img)
        return np.clip(img, 0, 255).astype(np.uint8)

    # ---- per-month overlays
    for m in MONTHS_RISK:
        ti = MONTHS.index(m)
        r, ab = risk_at(ti)
        write_png(d / "risk" / f"{m}.png", risk_png(r, ab))
        z = 0.5 * smooth_noise(rng, 15) * 0.8 - 3.2 * degr_at(ti) + 0.4 * (season(ti) - 0.75)
        write_png(d / "ndvi" / f"{m}.png", ramp(np.clip(z, -3, 3), NDVI_STOPS).astype(np.uint8))
    for m in MONTHS_RGB:
        write_png(d / "rgb" / f"{m}.png", rgb_at(MONTHS.index(m)))

    # ---- hotspots at the latest month
    t_last = MONTHS.index(MONTHS_RISK[-1])
    r_last, ab_last = risk_at(t_last)
    feats = []
    for k, b in enumerate(sorted(blobs, key=lambda b: -b["amp"])):
        pmask = (b["field"] > 0.3) & (r_last > 0.25)
        if pmask.sum() < 30:
            continue
        rows, cols = np.nonzero(pmask)
        r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
        lon_a, lon_b = w + c0 / W * (e - w), w + c1 / W * (e - w)
        lat_a, lat_b = n - r1 / H * (n - s), n - r0 / H * (n - s)
        label = f"H{len(feats) + 1}"
        # first month this cluster exceeded the warning threshold
        fw = next((MONTHS[t] for t in range(T_all) if b["amp"] * progress(b, t) > 0.35), MONTHS_RISK[0])
        # chips: crop with padding, before = first RGB month, after = latest
        pad = 25
        R0, R1, C0, C1 = max(r0 - pad, 0), min(r1 + pad, H), max(c0 - pad, 0), min(c1 + pad, W)
        for tag, mm in (("before", MONTHS_RGB[0]), ("after", MONTHS_RGB[-1])):
            chip = rgb_at(MONTHS.index(mm))[R0:R1, C0:C1]
            rep = max(1, 192 // max(chip.shape[:2]))
            chip = np.repeat(np.repeat(chip, rep, 0), rep, 1)
            write_png(d / "chips" / f"{label}_{tag}.png", chip)
        contrib = np.sort(rng.dirichlet(np.ones(5) * 1.4))[::-1] * rng.uniform(0.5, 0.9)
        names = [DRIVERS[0]] + list(rng.choice(DRIVERS[1:], 4, replace=False))
        if b["status"] == "abstain":
            rng.shuffle(names)
        lc_here = int(np.bincount(lc_codes[pmask]).argmax())
        nd_base = float(np.round(0.25 + 0.5 * veg[pmask].mean(), 3))
        degr = float(degr_at(t_last)[pmask].mean())
        # distance from hotspot centre to nearest network vertex (km)
        clon, clat = (lon_a + lon_b) / 2, (lat_a + lat_b) / 2
        verts = np.array([c for f in net for c in f["geometry"]["coordinates"]])
        dx = (verts[:, 0] - clon) * 111.32 * math.cos(math.radians(clat))
        dy = (verts[:, 1] - clat) * 110.574
        feats.append(dict(type="Feature", geometry=dict(type="Polygon", coordinates=[[
            [round(lon_a, 6), round(lat_a, 6)], [round(lon_b, 6), round(lat_a, 6)],
            [round(lon_b, 6), round(lat_b, 6)], [round(lon_a, 6), round(lat_b, 6)],
            [round(lon_a, 6), round(lat_a, 6)]]]),
            properties=dict(
                id=f"{a['key']}_{label}", label=label,
                risk_mean=round(float(r_last[pmask].mean()), 3), risk_max=round(float(r_last[pmask].max()), 3),
                area_ha=round(float(pmask.sum() * PIX_HA), 2), status=b["status"],
                landcover=LC_NAME.get(lc_here, str(lc_here)), first_warning=fw,
                drivers=[dict(name=str(nm), contribution=round(float(cv), 3)) for nm, cv in zip(names, contrib)],
                ndvi_now=round(nd_base * (1 - degr), 3), ndvi_baseline=nd_base,
                rain_anom_6m=round(float(rng.normal(-0.3, 0.6)), 2),
                dist_river_km=round(float(np.sqrt(dx ** 2 + dy ** 2).min()), 2),
                chip_before=f"chips/{label}_before.png", chip_after=f"chips/{label}_after.png")))
    write_json(d / "hotspots.geojson", dict(type="FeatureCollection", mock=True, features=feats), indent=1)

    # ---- meta
    meta = dict(mock=True, months_risk=MONTHS_RISK, months_rgb=MONTHS_RGB, grid=dict(H=H, W=W),
                legend=dict(
                    risk=dict(title="Risk: P(degradation onset within 6 months)", min_shown=0.15,
                              stops=[[v, "#%02x%02x%02x" % c[:3]] for v, c in RISK_STOPS],
                              abstain="#9b59ff"),
                    ndvi=dict(title="NDVI anomaly (z)", stops=[[v, "#%02x%02x%02x" % c[:3]] for v, c in NDVI_STOPS])))
    write_json(d / "meta.json", meta, indent=1)

    # ---- hydrology
    outlet_coords = net[0]["geometry"]["coordinates"][-1]
    up_reach = max((r for r in walk(root) if r is not root), key=lambda r: r.upland)
    up_lon = lon0 + km_to_deg(lat0, *up_reach.pts[0])[0]
    up_lat = lat0 + km_to_deg(lat0, *up_reach.pts[0])[1]
    dn_coords = [f for f in net if f["properties"]["role"] == "downstream"][-1]["geometry"]["coordinates"][-1]
    q_out = root.upland * a["runoff"]

    def station(name, lon, lat, q, avail=True):
        if not avail:
            return dict(name=name, lat=round(lat, 5), lon=round(lon, 5), available=False, mean_before=None,
                        mean_now=None, q90_before=None, q90_now=None, change_mean_pct=None, change_lowflow_pct=None)
        cm, cl = rng.normal(-9, 6), rng.normal(-22, 9)
        mb, q90b = q, q * rng.uniform(0.12, 0.25)
        mn, q90n = mb * (1 + cm / 100), q90b * (1 + cl / 100)
        return dict(name=name, lat=round(lat, 5), lon=round(lon, 5), available=True,
                    mean_before=round(mb, 3), mean_now=round(mn, 3), q90_before=round(q90b, 3), q90_now=round(q90n, 3),
                    change_mean_pct=round(cm, 1), change_lowflow_pct=round(cl, 1))

    hydro = dict(mock=True, outlet_id=net[0]["properties"]["HYRIV_ID"], outlet_mean_q=round(q_out, 3), stations=[
        station("Upstream reach (GloFAS cell)", up_lon, up_lat, up_reach.upland * a["runoff"]),
        station("AOI outlet (GloFAS cell)", outlet_coords[0], outlet_coords[1], q_out),
        station("Downstream reach (GloFAS cell)", dn_coords[0], dn_coords[1], down[-1].upland * a["runoff"]),
        station("Historic gauge (no record)", dn_coords[0] + 0.01, dn_coords[1] - 0.008, 0, avail=False),
    ])
    write_json(d / "hydro.json", hydro, indent=1)

    # ---- AOI time series
    T = len(MONTHS)
    t = np.arange(T)
    mo = np.array([int(m[5:]) for m in MONTHS])
    seas = np.cos((mo - a["season_peak"]) / 12 * 2 * np.pi)
    trend = -0.0004 * t
    rain = np.convolve(rng.normal(0, 1, T + 5), np.ones(6) / 6 * 2.2, "valid")[:T]
    stress = np.clip(-rain, 0, None) * 0.25 + np.array(
        [np.mean([b["field"].mean() * progress(b, k) for b in blobs]) for k in t]) * 9
    z_mean = 0.35 * rain - 1.2 * stress + rng.normal(0, 0.15, T)
    resid = z_mean - 0.35 * rain + rng.normal(0, 0.08, T)
    ndvi = 0.48 + 0.14 * seas + trend + 0.03 * z_mean
    frac_below = np.clip(0.05 + 0.25 * stress + 0.03 * rng.random(T), 0, 1)
    risk_mean = np.clip(0.06 + 0.5 * stress + 0.01 * rng.normal(size=T), 0, 1)
    q = q_out * (1 + 0.9 * np.cos((mo - a["season_peak"]) / 12 * 2 * np.pi)) * np.exp(0.15 * rain)

    def lst(x, missing_tail=0):
        out = [None if not np.isfinite(v) else round(float(v), 4) for v in x]
        for i in range(missing_tail):
            out[-1 - i] = None
        return out

    ts_obj = dict(mock=True, months=MONTHS, ndvi_mean=lst(ndvi), z_mean=lst(z_mean), resid_mean=lst(resid),
                  frac_below=lst(frac_below), risk_mean=lst(risk_mean), rain_anom_6m=lst(rain),
                  temp_anom=lst(rng.normal(0.4, 0.5, T)), soil_moist_anom=lst(0.6 * rain + rng.normal(0, 0.3, T)),
                  discharge_outlet=lst(q, missing_tail=3))
    for i in (5, 6, 30):                                   # simulate cloudy months
        ts_obj["ndvi_mean"][i] = ts_obj["z_mean"][i] = ts_obj["resid_mean"][i] = None
    write_json(d / "timeseries.json", ts_obj)

    stats = dict(risk_mean=round(float(r_last.mean()), 4),
                 area_high_ha=round(float((r_last > 0.5).sum() * PIX_HA), 1),
                 area_abstain_ha=round(float(ab_last.sum() * PIX_HA), 1),
                 n_hotspots=len(feats), ndvi_trend_per_yr=round(float(np.polyfit(t / 12, ndvi, 1)[0]), 4),
                 pos_rate_hist=round(float(rng.uniform(0.02, 0.08)), 3))
    return dict(key=a["key"], country=a["country"], landscape=a["landscape"], rationale=a["rationale"],
                center=list(a["center"]), bbox=[round(v, 6) for v in bbox], stats=stats, mock=True)


def make_metrics():
    rng = np.random.default_rng(5)
    return dict(
        mock=True, model_version="careew-lgbm-v1 (MOCK)", generated="2026-10-19",
        task="P(persistent NDVI-residual degradation onset within 6 months), per 10 m pixel",
        test_period="2024-10 .. 2025-12 (labels need 9 months of look-ahead)",
        headline=dict(pr_auc=0.412, roc_auc=0.861, brier=0.041, ece=0.018, base_rate=0.051,
                      lead_time_months_median=3.0, conformal_coverage=0.903, abstain_rate=0.074),
        baselines=dict(persistence_pr_auc=0.191, ndvi_threshold_pr_auc=0.142),
        ablation=[
            dict(model="Full model (S2 + climate + context)", pr_auc=0.412, roc_auc=0.861, brier=0.041),
            dict(model="- climate conditioning", pr_auc=0.331, roc_auc=0.822, brier=0.046),
            dict(model="- spatial context", pr_auc=0.365, roc_auc=0.840, brier=0.044),
            dict(model="- hydrology (dist. to river)", pr_auc=0.401, roc_auc=0.856, brier=0.042),
            dict(model="NDVI z only", pr_auc=0.214, roc_auc=0.761, brier=0.050),
        ],
        loco=[dict(country=c, pr_auc=round(float(rng.uniform(0.22, 0.48)), 3),
                   roc_auc=round(float(rng.uniform(0.74, 0.88)), 3), n_pos=int(rng.integers(120, 900)))
              for c in ["Nepal", "India", "Ethiopia", "Kenya", "Senegal", "Spain", "Brazil", "Mongolia", "Australia"]],
        notes="MOCK metrics generated by app/make_mock_data.py for UI development. Not results.",
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="overwrite even if real (non-mock) data exists")
    args = ap.parse_args()
    existing = OUT / "aois.json"
    if existing.exists() and not args.force:
        try:
            if not json.loads(existing.read_text(encoding="utf-8")).get("mock", False):
                raise SystemExit("app/static/data/aois.json holds REAL pipeline output; refusing to overwrite "
                                 "(use --force if you really mean it).")
        except json.JSONDecodeError:
            pass
    OUT.mkdir(parents=True, exist_ok=True)
    aois = []
    for a in AOIS:
        print("mock AOI", a["key"])
        aois.append(make_aoi(a))
    doc = dict(mock=True, generated="2026-10-19", model_version="careew-lgbm-v1 (MOCK)",
               latest_month=MONTHS_RISK[-1], months=MONTHS, aois=aois)
    write_json(existing, doc, indent=1)
    write_json(OUT / "metrics.json", make_metrics(), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
