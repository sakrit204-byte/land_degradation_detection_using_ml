"""On-demand detection for ANY user-drawn box (steps whose output exists are skipped -> resumable) (the app's "Draw box -> analyse" tool).

    python -m care_ew.ondemand --job JOBID --bbox W S E N --name "My area"

1. Snap the box to the 512 x 512 px (5.12 km) internal COG blocks of the Sentinel-2 MGRS tile that contains the
   box centre (same grid logic as the study AOIs, D-006). Up to MAX_BLOCKS blocks; each becomes a user AOI
   'USR_<slug>_<i>' registered in data/user_aois.json (so every module can find it via AOI_BY_KEY).
2. Per block: land cover/terrain/water -> climate (ERA5) -> Sentinel-2 2017-now monthly composites -> MODIS
   -> rivers (best effort) -> features -> TRAINED model (no retraining) -> calibrated risk + conformal status
   for every pixel and month -> hotspots -> app export.
Progress is written to data/jobs/<job>.json (stage, fraction, messages) and polled by the web app.
The model is applied out of its training domain for new landscapes: results carry that warning.
"""
import argparse, json, math, re, time, traceback
import numpy as np
from .config import ROOT, PROC, AOI

JOBS = ROOT / "data" / "jobs"; JOBS.mkdir(parents=True, exist_ok=True)
USER_AOIS = ROOT / "data" / "user_aois.json"
MAX_BLOCKS = 4
STAGES = [("grid", 0.02), ("static", 0.05), ("climate", 0.08), ("sentinel2", 0.70), ("modis", 0.85),
          ("rivers", 0.88), ("features", 0.93), ("predict", 0.98), ("export", 1.0)]


class Job:
    def __init__(self, jid, **meta):
        self.f = JOBS / f"{jid}.json"
        self.d = dict(id=jid, status="running", stage="queued", progress=0.0, messages=[], started=time.time(), **meta)
        self.save()

    def save(self):
        self.d["updated"] = time.time()
        tmp = self.f.with_suffix(".tmp"); json.dump(self.d, open(tmp, "w"), indent=1); tmp.replace(self.f)

    def log(self, msg, stage=None, progress=None):
        if stage: self.d["stage"] = stage
        if progress is not None: self.d["progress"] = round(float(progress), 3)
        self.d["messages"] = (self.d["messages"] + [f"{time.strftime('%H:%M:%S')} {msg}"])[-60:]
        self.save(); print(msg, flush=True)


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:24] or "area"


def plan_blocks(bbox):
    """Return (tile, epsg, list of (x0, y0)) for 5.12 km blocks of the S2 tile covering bbox."""
    from shapely.geometry import box, shape, mapping
    from pyproj import Transformer
    from .s2 import _catalog
    w, s, e, n = bbox
    cx, cy = (w + e) / 2, (s + n) / 2
    cat = _catalog()
    items = list(cat.search(collections=["sentinel-2-l2a"], intersects=mapping(box(*bbox)),
                            datetime="2023-01-01/2023-06-30", max_items=60).items())
    b = box(*bbox)
    cands = sorted({(i.properties["s2:mgrs_tile"],
                     int(i.properties.get("proj:epsg") or str(i.properties.get("proj:code", "EPSG:0")).split(":")[1]))
                    for i in items if shape(i.geometry).contains(b)})
    if not cands:  # box straddles tiles: use the tile containing the centre
        from shapely.geometry import Point
        cands = sorted({(i.properties["s2:mgrs_tile"],
                         int(i.properties.get("proj:epsg") or str(i.properties.get("proj:code", "EPSG:0")).split(":")[1]))
                        for i in items if shape(i.geometry).contains(Point(cx, cy))})
    if not cands:
        raise RuntimeError("no Sentinel-2 tile found for this box (ocean or outside coverage?)")
    zone = int((cx + 180) // 6) + 1
    utm = (32600 if cy >= 0 else 32700) + zone
    tile, epsg = sorted(cands, key=lambda t: (t[1] != utm, t[0]))[0]
    it = next(i for i in items if i.properties["s2:mgrs_tile"] == tile)
    tr = it.assets["B04"].extra_fields["proj:transform"]
    ulx, uly = tr[2], tr[5]
    fwd = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = zip(*[fwd.transform(x, y) for x, y in [(w, s), (w, n), (e, s), (e, n)]])
    bs = 5120
    if max(xs) - min(xs) <= 5000 and max(ys) - min(ys) <= 5000:
        # small box: ONE 5.12 km window centred on the box (snapped to the tile's 10 m pixel grid). It straddles
        # up to 4 COG blocks, but one 4-block read per scene is ~2.5x faster than 4 separate aligned blocks
        # (26 s vs 4 x 16 s per month measured, D-006), and only one area has to be processed.
        cx_m, cy_m = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        x0 = ulx + round((cx_m - bs / 2 - ulx) / 10) * 10
        y0 = uly - round((uly - (cy_m - bs / 2)) / 10) * 10
        return tile, epsg, [(x0, y0)]
    c0, c1 = math.floor((min(xs) - ulx) / bs), math.floor((max(xs) - ulx) / bs)
    r0, r1 = math.floor((uly - max(ys)) / bs), math.floor((uly - min(ys)) / bs)
    blocks = [(ulx + c * bs, uly - (r + 1) * bs) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
    return tile, epsg, blocks


def register(key, name, lon, lat, tile, epsg, x0, y0, user_bbox):
    from pyproj import Transformer
    back = Transformer.from_crs(epsg, 4326, always_xy=True)
    pts = [back.transform(x, y) for x in (x0, x0 + 5120) for y in (y0, y0 + 5120)]
    lons, lats = zip(*pts)
    g = dict(tile=tile, epsg=int(epsg), x0=float(x0), y0=float(y0), n=512,
             bbox_wgs84=[min(lons), min(lats), max(lons), max(lats)])
    d = PROC / key; d.mkdir(parents=True, exist_ok=True)
    json.dump(g, open(d / "grid.json", "w"), indent=1)
    reg = json.load(open(USER_AOIS)) if USER_AOIS.exists() else {}
    reg[key] = dict(key=key, country="User area", landscape=name, lon=(min(lons) + max(lons)) / 2,
                    lat=(min(lats) + max(lats)) / 2, rationale=f"User-drawn box {user_bbox}", user=True,
                    user_bbox=user_bbox, created=time.strftime("%Y-%m-%d %H:%M"))
    json.dump(reg, open(USER_AOIS, "w"), indent=1)
    return g


def run(jid, bbox, name):
    job = Job(jid, bbox=bbox, name=name, keys=[])
    try:
        job.log("planning Sentinel-2 blocks", "grid", 0.01)
        tile, epsg, blocks = plan_blocks(bbox)
        if len(blocks) > MAX_BLOCKS:
            raise RuntimeError(f"box needs {len(blocks)} blocks of 5.12 km; maximum is {MAX_BLOCKS} (~10 x 10 km). Draw a smaller box.")
        base = f"USR_{slug(name)}_{jid[-4:]}"
        keys = []
        for i, (x0, y0) in enumerate(blocks):
            key = f"{base}_{i + 1}" if len(blocks) > 1 else base
            register(key, name, None, None, tile, epsg, x0, y0, bbox)
            keys.append(key)
        job.d["keys"] = keys; job.d["tile"] = tile
        job.log(f"{len(blocks)} block(s) on tile {tile}: {', '.join(keys)}", "grid", 0.02)
        # import AFTER registration so config picks up the user AOIs
        import importlib, care_ew.config as C
        importlib.reload(C)
        from . import s2, context, climate, hydro, dataset, predict, export
        for m in (s2, context, climate, hydro, dataset, predict, export):
            m.AOI_BY_KEY = C.AOI_BY_KEY
        nb = len(keys)

        def prog(i, stage, frac_in_stage=1.0):
            lo = 0.0 if stage == "grid" else dict(STAGES)[STAGES[[s for s, _ in STAGES].index(stage) - 1][0]]
            hi = dict(STAGES)[stage]
            return lo + (hi - lo) * ((i + frac_in_stage) / nb)

        for i, k in enumerate(keys):
            job.log(f"[{k}] land cover, terrain, surface water", "static", prog(i, "static", 0))
            if not (PROC / k / "static.nc").exists():
                context.static(k)
            st = __import__("xarray").open_dataset(PROC / k / "static.nc")
            lc = st["landcover"].values
            usable = np.isin(lc, (10, 20, 30, 40, 60, 90, 95, 100)).mean()
            job.log(f"[{k}] usable land share {usable:.0%} (water {np.mean(lc == 80):.0%}, built {np.mean(lc == 50):.0%})", "static", prog(i, "static"))
            if usable < 0.2:
                raise RuntimeError(f"block {k} is {1 - usable:.0%} water/built/snow - nothing to analyse")
        for i, k in enumerate(keys):
            job.log(f"[{k}] ERA5 / ERA5-Land climate 1991-now", "climate", prog(i, "climate", 0))
            if not (PROC / k / "climate_monthly.csv").exists():
                climate.build(k)
        for i, k in enumerate(keys):
            job.log(f"[{k}] Sentinel-2 monthly composites 2017-now (the long step)", "sentinel2", prog(i, "sentinel2", 0))
            import threading
            done = {"v": False}

            def watch(k=k, i=i):
                from .config import S2_START, S2_END
                import pandas as pd
                tot = len(pd.period_range(S2_START, S2_END, freq="M"))
                while not done["v"]:
                    n = len(list((PROC / k / "s2_parts").glob("*.npz"))) if (PROC / k / "s2_parts").exists() else 0
                    job.d["detail"] = f"{k}: {n}/{tot} months"
                    job.d["progress"] = round(prog(i, "sentinel2", n / tot), 3); job.save()
                    time.sleep(10)
            th = threading.Thread(target=watch, daemon=True); th.start()
            s2.build(k)
            done["v"] = True
        for i, k in enumerate(keys):
            job.log(f"[{k}] MODIS 250 m NDVI history 2000-now", "modis", prog(i, "modis", 0))
            if not (PROC / k / "modis.nc").exists():
                context.modis(k)
        for i, k in enumerate(keys):
            job.log(f"[{k}] river network + discharge (best effort)", "rivers", prog(i, "rivers", 0))
            try:
                if not (PROC / k / "hydro_summary.json").exists():
                    hydro.build(k)
            except Exception as e:
                job.log(f"[{k}] rivers skipped: {str(e)[:120]}")
        for i, k in enumerate(keys):
            job.log(f"[{k}] features, labels history, climate conditioning", "features", prog(i, "features", 0))
            ctx = dataset.aoi_context(k, save_cube=True)
            y, el = ctx["y"], ctx["eligible"]
            info = dict(aoi=k, user=True, n_pixels=int(ctx["N"]), pos_rate=float(np.nanmean(np.where(el, y, np.nan))),
                        onsets_total=int(ctx["onset"].sum()), climate_model=ctx["cm_info"])
            json.dump(info, open(PROC / k / "dataset_info.json", "w"), indent=1, default=str)
            job.log(f"[{k}] trained model -> risk for {ctx['N']:,} pixels x every month", "predict", prog(i, "predict", 0))
            predict.predict_aoi(k, ctx=ctx)
            del ctx
        job.log("exporting maps, hotspots and charts to the app", "export", 0.98)
        for k in keys:
            export.add_aoi(k)
        job.d.update(status="done", stage="done", progress=1.0, finished=time.time())
        job.log(f"finished in {(time.time() - job.d['started']) / 60:.0f} min")
    except Exception as e:
        job.d.update(status="error", error=str(e)[:400], traceback=traceback.format_exc()[-2000:])
        job.log(f"ERROR: {str(e)[:300]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True); ap.add_argument("--name", default="area")
    ap.add_argument("--bbox", nargs=4, type=float, required=True)
    a = ap.parse_args()
    run(a.job, a.bbox, a.name)
