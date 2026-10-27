"""CARE-EW web backend (FastAPI).

Serves the single-page app in app/static at "/" and two small JSON endpoints:

* GET /api/health                       -> liveness + which data are present
* GET /api/pixel?aoi=KEY&lon=..&lat=..  -> per-pixel time series (docs/UI_DATA_SPEC.md)

/api/pixel reads data/processed/<aoi>/cube.npz (written by care_ew/dataset.py) and, if present,
app/static/data/aois/<aoi>/risk_cube.npz. Both are loaded lazily and cached (keyed on file
mtime, so a re-run of the pipeline is picked up without restarting). When cube.npz does not
exist yet a deterministic MOCK series is returned and flagged with "mock": true.

Run:  .venv/Scripts/python -m uvicorn app.server:app --port 8765
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
STATIC = APP_DIR / "static"
DATA = STATIC / "data"
PROC = ROOT / "data" / "processed"

LC_NAME = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare", 70: "snow",
           80: "water", 90: "wetland", 95: "mangrove", 100: "moss"}

app = FastAPI(title="CARE-EW", version="1.0")

# ----------------------------------------------------------------------------- caching
_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def _cached(path: Path, loader):
    """Load `path` with `loader` once per file mtime."""
    key = str(path)
    mtime = path.stat().st_mtime
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
    obj = loader(path)
    with _lock:
        _cache[key] = (mtime, obj)
    return obj


def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _load_cube(p: Path):
    """Load cube.npz fully into memory and build a (H, W) -> pixel-index lookup."""
    with np.load(p, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    H, W = int(d["H"]), int(d["W"])
    index = np.full((H, W), -1, np.int32)
    index[d["rr"].astype(np.int32), d["cc"].astype(np.int32)] = np.arange(len(d["rr"]), dtype=np.int32)
    d["index"] = index
    d["times"] = [str(t)[:7] for t in d["times"]]
    return d


def _load_risk(p: Path):
    with np.load(p, allow_pickle=False) as z:
        return {"risk": z["risk"], "months": [str(m)[:7] for m in z["months"]]}


def aois_doc() -> dict:
    p = DATA / "aois.json"
    if not p.exists():
        raise HTTPException(503, "app/static/data/aois.json not found - run the exporter or app/make_mock_data.py")
    return _cached(p, _load_json)


def find_aoi(key: str) -> dict:
    for a in aois_doc().get("aois", []):
        if a.get("key") == key:
            return a
    raise HTTPException(404, f"unknown AOI '{key}'")


def _series(x) -> list:
    """float array -> JSON list with None for NaN/inf."""
    return [None if not math.isfinite(v) else round(v, 4) for v in np.asarray(x, dtype=np.float64).tolist()]


# ----------------------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    out = {"status": "ok", "aois_json": (DATA / "aois.json").exists(), "cubes": {}}
    try:
        doc = aois_doc()
        out["mock_data"] = bool(doc.get("mock", False))
        for a in doc.get("aois", []):
            out["cubes"][a["key"]] = {
                "cube": (PROC / a["key"] / "cube.npz").exists(),
                "risk_cube": (DATA / "aois" / a["key"] / "risk_cube.npz").exists(),
            }
    except HTTPException as e:
        out["detail"] = e.detail
    return out


@app.get("/api/pixel")
def pixel(aoi: str = Query(..., max_length=64), lon: float = Query(...), lat: float = Query(...)):
    a = find_aoi(aoi)
    w, s, e, n = a["bbox"]
    if not (w <= lon <= e and s <= lat <= n):
        raise HTTPException(404, "point is outside the AOI")

    cube_p = PROC / aoi / "cube.npz"
    if not cube_p.exists():
        return _mock_pixel(a, lon, lat)

    try:
        cube = _cached(cube_p, _load_cube)
    except Exception as ex:  # corrupt / partially written file
        raise HTTPException(500, f"could not read cube.npz: {ex}")
    H, W = cube["index"].shape
    grid_p = PROC / aoi / "grid.json"
    if grid_p.exists():
        # exact: the analysis grid is a 10 m UTM grid (grid.json written by care_ew/s2.py)
        from pyproj import Transformer
        g = _cached(grid_p, _load_json)
        x, y = Transformer.from_crs(4326, g["epsg"], always_xy=True).transform(lon, lat)
        row = int((g["y0"] + g["n"] * 10 - y) // 10)
        col = int((x - g["x0"]) // 10)
        if not (0 <= row < H and 0 <= col < W):
            raise HTTPException(404, "point is outside the AOI")
    else:
        # fallback: linear lon/lat -> row/col over the AOI bbox (row 0 = north edge)
        row = min(int((n - lat) / (n - s) * H), H - 1)
        col = min(int((lon - w) / (e - w) * W), W - 1)
    i = int(cube["index"][row, col])
    if i < 0:
        raise HTTPException(404, "pixel is masked (landcover excluded or too cloudy)")

    months = cube["times"]
    out = {
        "aoi": aoi, "row": row, "col": col, "mock": False, "months": months,
        "ndvi": _series(cube["ndvi"][:, i]), "z": _series(cube["z"][:, i]),
        "resid": _series(cube["R"][:, i]),
        "label": _series(cube["y"][:, i]) if "y" in cube else None,
        "label_onsets": [m for m, o in zip(months, cube["onset"][:, i]) if o] if "onset" in cube else [],
        "landcover": None, "risk": [None] * len(months),
    }
    if "lc" in cube:
        code = int(np.asarray(cube["lc"]).reshape(-1)[i]) if np.asarray(cube["lc"]).size > 1 else int(cube["lc"])
        out["landcover"] = LC_NAME.get(code, str(code))

    risk_p = DATA / "aois" / aoi / "risk_cube.npz"
    if risk_p.exists():
        try:
            rc = _cached(risk_p, _load_risk)
            if rc["risk"].shape[1] == len(cube["rr"]):
                pos = {m: k for k, m in enumerate(months)}
                vals = _series(rc["risk"][:, i])
                for m, v in zip(rc["months"], vals):
                    if m in pos:
                        out["risk"][pos[m]] = v
            else:
                out["risk_note"] = "risk_cube.npz pixel count does not match cube.npz"
        except Exception as ex:
            out["risk_note"] = f"could not read risk_cube.npz: {ex}"
    return out


def _mock_pixel(a: dict, lon: float, lat: float) -> dict:
    """Deterministic synthetic series; degrades if the point is inside a (mock) hotspot."""
    doc = aois_doc()
    months = doc.get("months") or [f"{y}-{m:02d}" for y in range(2019, 2027) for m in range(1, 13)][:93]
    w, s, e, n = a["bbox"]
    H = W = 500
    row, col = min(int((n - lat) / (n - s) * H), H - 1), min(int((lon - w) / (e - w) * W), W - 1)
    seed = int(hashlib.md5(f"{a['key']}:{row}:{col}".encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)

    hot = None
    hp = DATA / "aois" / a["key"] / "hotspots.geojson"
    if hp.exists():
        for f in _cached(hp, _load_json).get("features", []):
            ring = f["geometry"]["coordinates"][0]
            xs, ys = [c[0] for c in ring], [c[1] for c in ring]
            if min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys):
                hot = f["properties"]
                break

    T = len(months)
    mo = np.array([int(m[5:7]) for m in months])
    seas = np.cos((mo - 8) / 12 * 2 * np.pi)
    z = rng.normal(0, 0.6, T)
    onsets, risk = [], np.clip(0.04 + 0.03 * rng.standard_normal(T), 0, 1)
    if hot:
        fw = hot.get("first_warning") or months[-12]
        t0 = months.index(fw) if fw in months else T - 12
        ramp = 1 / (1 + np.exp(-(np.arange(T) - t0 - 3) / 2.0))
        z -= 2.6 * ramp
        risk = np.clip(risk + hot.get("risk_mean", 0.5) * 1 / (1 + np.exp(-(np.arange(T) - t0) / 2.0)), 0, 1)
        if hot.get("status") != "watch" and t0 + 4 < T:
            onsets = [months[min(t0 + 4, T - 1)]]
    resid = z + rng.normal(0, 0.2, T)
    ndvi = np.clip(0.5 + 0.15 * seas + 0.06 * z, 0, 1)
    risk_out = _series(risk)
    first_risk = months.index("2024-10") if "2024-10" in months else 0
    risk_out = [None if k < first_risk else v for k, v in enumerate(risk_out)]
    return {"aoi": a["key"], "row": row, "col": col, "mock": True,
            "note": "cube.npz not found - synthetic pixel series for UI development",
            "months": months, "ndvi": _series(ndvi), "z": _series(z), "resid": _series(resid),
            "risk": risk_out, "label_onsets": onsets,
            "landcover": (hot or {}).get("landcover") or ["tree", "crop", "shrub"][seed % 3]}


# ----------------------------------------------------------------------------- on-demand detection
# POST /api/analyze  {"bbox":[w,s,e,n], "name":"..."} -> starts care_ew.ondemand in a separate process
# POST /api/plan     {"bbox":[...]}                     -> blocks / area / time estimate, no download
# GET  /api/jobs                                        -> all jobs (newest first)
# GET  /api/jobs/{id}                                   -> one job: status, stage, progress, messages, keys
import subprocess, sys, time as _time, uuid
from pydantic import BaseModel

JOBS = ROOT / "data" / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
MIN_PER_BLOCK = 45          # observed on a ~1.3 MB/s link; shown to the user as an estimate


class AnalyzeReq(BaseModel):
    bbox: list[float]
    name: str = "My area"


def _check_bbox(b):
    if len(b) != 4:
        raise HTTPException(400, "bbox must be [west, south, east, north]")
    w, s, e, n = b
    if not (-180 <= w < e <= 180 and -60 <= s < n <= 75):
        raise HTTPException(400, "invalid bbox (Sentinel-2 land coverage is ~60S..75N)")
    km_w = (e - w) * 111.32 * math.cos(math.radians((s + n) / 2)); km_h = (n - s) * 110.57
    if km_w * km_h > 120:
        raise HTTPException(400, f"box is {km_w:.1f} x {km_h:.1f} km; maximum ~10 x 10 km (4 Sentinel-2 blocks)")
    if km_w < 0.2 or km_h < 0.2:
        raise HTTPException(400, "box too small (min 200 m)")
    return km_w, km_h


@app.post("/api/plan")
def plan(req: AnalyzeReq):
    km_w, km_h = _check_bbox(req.bbox)
    try:
        sys.path.insert(0, str(ROOT))
        from care_ew.ondemand import plan_blocks, MAX_BLOCKS
        tile, epsg, blocks = plan_blocks(req.bbox)
    except Exception as ex:
        raise HTTPException(400, f"cannot plan this box: {ex}")
    if len(blocks) > MAX_BLOCKS:
        raise HTTPException(400, f"box spans {len(blocks)} Sentinel-2 blocks; maximum {MAX_BLOCKS}. Draw a smaller box.")
    return {"tile": tile, "blocks": len(blocks), "box_km": [round(km_w, 2), round(km_h, 2)],
            "analysed_km2": round(len(blocks) * 5.12 ** 2, 1),
            # one centred window (small boxes) reads up to 4 COG blocks per scene in one request: ~1.5x a block
            "estimate_minutes": 70 if len(blocks) == 1 and (km_w <= 5 and km_h <= 5) else len(blocks) * MIN_PER_BLOCK}


@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    _check_bbox(req.bbox)
    running = [j for j in _jobs() if j.get("status") == "running" and _time.time() - j.get("updated", 0) < 900]
    if running:
        raise HTTPException(409, f"another analysis is running ({running[0]['name']}); wait for it to finish")
    jid = _time.strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:4]
    name = (req.name or "My area").strip()[:40]
    log = open(JOBS / f"{jid}.log", "w")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([str(VENV_PY), "-u", "-m", "care_ew.ondemand", "--job", jid, "--name", name, "--bbox",
                      *[str(v) for v in req.bbox]], cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    (JOBS / f"{jid}.json").write_text(json.dumps(dict(id=jid, name=name, bbox=req.bbox, status="running", stage="starting",
                                                     progress=0.0, messages=["started"], started=_time.time(), updated=_time.time())))
    return {"job": jid}


def _jobs():
    out = []
    for f in JOBS.glob("*.json"):
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            pass
    return sorted(out, key=lambda j: j.get("started", 0), reverse=True)


@app.get("/api/jobs")
def jobs():
    return [{k: j.get(k) for k in ("id", "name", "bbox", "status", "stage", "progress", "detail", "keys", "error",
                                   "started", "updated", "finished")} for j in _jobs()]


@app.get("/api/jobs/{jid}")
def job(jid: str):
    f = JOBS / f"{jid}.json"
    if not f.exists():
        raise HTTPException(404, "no such job")
    j = json.loads(f.read_text())
    j.pop("traceback", None)
    return j


# ----------------------------------------------------------------------------- cache policy
# App code / styles / data must never be served from a stale browser cache after an update (I-025: a browser
# mixed cached old modules with new ones and the app failed to start). "no-cache" = always revalidate; unchanged
# files still return a cheap 304. Large immutable vendor libraries may be cached normally.
@app.middleware("http")
async def _no_stale_code(request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if not path.startswith("/vendor/") and (path == "/" or path.endswith((".js", ".css", ".html", ".json", ".geojson"))):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# ----------------------------------------------------------------------------- blind VHR review (PROJECT_LOG D-029)
VHR = ROOT / "data" / "vhr"
_ans_lock = threading.Lock()


@app.get("/api/vhr/pairs")
def vhr_pairs():
    """Image pairs to review. The warning/control key (data/vhr/key.json) is never served."""
    f = VHR / "pairs.json"
    if not f.exists():
        raise HTTPException(404, "no review campaign yet (python scripts/vhr_campaign.py sample && ... fetch)")
    d = _load_json(f)
    return {"pairs": [{k: p[k] for k in ("id", "aoi", "lon", "lat", "t", "before", "after")} for p in d["pairs"]]}


@app.get("/api/vhr/answers")
def vhr_answers(who: str = Query(..., min_length=1, max_length=40)):
    f = VHR / "answers.json"
    return (_load_json(f) if f.exists() else {}).get(who, {})


@app.post("/api/vhr/answer")
def vhr_answer(body: dict):
    who, pid, a = str(body.get("who", ""))[:40].strip(), str(body.get("id", ""))[:16], body.get("answer")
    if not who or a not in ("yes", "no", "unsure", "nodata"):
        raise HTTPException(400, "need who and answer in yes/no/unsure/nodata")
    f = VHR / "answers.json"
    with _ans_lock:
        d = _load_json(f) if f.exists() else {}
        d.setdefault(who, {})[pid] = a
        f.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return {"ok": True, "n": len(d[who])}


@app.get("/api/vhr/chip/{name}", include_in_schema=False)
def vhr_chip(name: str):
    import re as _re
    if not _re.fullmatch(r"[0-9a-f]{8}_[ab]\.png", name):
        raise HTTPException(404, "bad chip name")
    f = VHR / "chips" / name
    if not f.exists():
        raise HTTPException(404, "chip not found")
    return FileResponse(f)


# ----------------------------------------------------------------------------- static app
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.exception_handler(404)
async def _not_found(request, exc):
    detail = getattr(exc, "detail", "not found")
    return JSONResponse({"detail": detail}, status_code=404)


app.mount("/", StaticFiles(directory=STATIC), name="static")
