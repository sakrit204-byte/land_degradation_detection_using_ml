"""Data-lineage manifest: the exact Sentinel-2 scenes behind every AOI-month composite.
Re-runs the deterministic scene selection (dedupe -> single aligned tile -> 4 least cloudy) on STAC
metadata only (no pixels) and writes data/processed/<aoi>/s2_items.csv with item id, tile, datetime,
processing baseline, offset applied and scene cloud cover. This is the audit trail for every label."""
import sys, time
sys.path.insert(0, ".")
import pandas as pd
from care_ew.config import AOIS, PROC, S2_START, S2_END, S2_MAX_CLOUD, BOA_OFFSET_BASELINE
from care_ew.s2 import _catalog, dedupe, select_scenes, grid_info, _baseline

for a in AOIS if len(sys.argv) < 2 else [x for x in AOIS if x.key in sys.argv[1:]]:
    cat = _catalog(); rows = []
    bbox = grid_info(a)["bbox_wgs84"]
    for m in pd.period_range(S2_START, S2_END, freq="M"):
        s, e = m.start_time, m.end_time
        for k in range(4):
            try:
                items = list(cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{s:%Y-%m-%d}/{e:%Y-%m-%d}",
                                        query={"eo:cloud_cover": {"lt": S2_MAX_CLOUD}}).items()); break
            except Exception:
                time.sleep(5 * (k + 1)); cat = _catalog()
        for it in select_scenes(a, dedupe(items)):
            b = _baseline(it)
            rows.append(dict(month=str(m), item_id=it.id, tile=it.properties.get("s2:mgrs_tile"), datetime=it.datetime.isoformat(),
                             processing_baseline=b, boa_offset_applied=b >= BOA_OFFSET_BASELINE,
                             scene_cloud_pct=it.properties.get("eo:cloud_cover"), n_candidates=len(items)))
    pd.DataFrame(rows).to_csv(PROC / a.key / "s2_items.csv", index=False)
    print(a.key, len(rows), "scenes", flush=True)
