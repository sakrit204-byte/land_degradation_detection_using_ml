"""Screen candidate AOIs BEFORE committing to a full Sentinel-2 download (lesson from I-015, Kenya lake):
snap the grid, fetch ESA WorldCover for the block, report land-cover shares. Cheap (~1 MB per site).
Usage: python scripts/screen_sites.py   (candidates defined below; results -> data/candidates/screen.json)"""
import json, sys
sys.path.insert(0, ".")
import numpy as np, odc.stac
from care_ew.config import AOI, PROC
from care_ew import s2 as s2mod, context

CANDIDATES = [
    # ---- Nepal: different degradation processes and physiography
    AOI("NPL_chure_dang", "Nepal", "Siwalik (Chure) hills, Dang - western Chure", 82.45, 27.95,
        "Western Chure: forest degradation, gravel mining, erosion into Rapti valley."),
    AOI("NPL_kavre", "Nepal", "Middle-hills terraced farmland and degraded slopes", 85.62, 27.55,
        "Kavrepalanchok mid-hills: terrace abandonment, landslides, soil erosion."),
    AOI("NPL_mustang", "Nepal", "Trans-Himalayan arid rangeland", 83.85, 28.95,
        "Upper Mustang: high-altitude rangeland under grazing pressure; cold arid ecosystem."),
    AOI("NPL_chure_sarlahi", "Nepal", "Eastern Chure foothills, Sarlahi/Mahottari", 85.55, 27.10,
        "Eastern Chure: deforestation and erosion feeding Terai rivers; second eastern Chure site."),
    AOI("NPL_surkhet", "Nepal", "Inner-Terai valley and Chure/Mahabharat slopes", 81.65, 28.55,
        "Surkhet / Bheri: forest and shrubland degradation, mid-western dry hills."),
    # ---- India: major Desertification & Land Degradation Atlas hotspots
    AOI("IND_banni", "India", "Banni grassland, Kachchh - saline grassland invaded by Prosopis", 69.70, 23.65,
        "Banni: Asia's largest tropical grassland, degraded by Prosopis invasion and salinity."),
    AOI("IND_jharia", "India", "Jharia coalfield - mining-driven degradation", 86.38, 23.75,
        "Jharia: open-cast coal mining, fires and land subsidence; strong anthropogenic degradation."),
    AOI("IND_marathwada", "India", "Marathwada semi-arid rainfed cropland", 75.65, 18.75,
        "Marathwada (Beed): recurrent drought, soil erosion, groundwater depletion."),
    AOI("IND_thar", "India", "Thar desert margin rangeland/cropland", 72.70, 26.55,
        "Western Rajasthan (Jodhpur): desertification, wind erosion, overgrazing."),
    AOI("IND_chambal", "India", "Chambal ravines - gully erosion badlands", 78.30, 26.65,
        "Chambal ravines (Morena/Bhind): one of the largest gully-erosion landscapes in Asia."),
]

if __name__ == "__main__":
    import care_ew.config as C
    out = {}
    for a in CANDIDATES:
        C.AOI_BY_KEY[a.key] = a
        (PROC / a.key).mkdir(parents=True, exist_ok=True)
        try:
            g = s2mod.grid_info(a)
            ds = context.static(a.key)
            lc = ds["landcover"].values
            u, n = np.unique(lc, return_counts=True)
            share = {int(k): round(float(v) / lc.size, 3) for k, v in zip(u, n)}
            usable = sum(v for k, v in share.items() if k in (10, 20, 30, 40, 60, 90, 95, 100))
            out[a.key] = dict(tile=g["tile"], bbox=g["bbox_wgs84"], landcover=share, usable_share=round(usable, 3),
                              water=share.get(80, 0), built=share.get(50, 0), elev_mean=float(ds["elev"].mean()))
        except Exception as e:
            out[a.key] = dict(error=str(e)[:200])
        print(a.key, out[a.key], flush=True)
    (PROC.parent / "candidates").mkdir(exist_ok=True)
    json.dump(out, open(PROC.parent / "candidates" / "screen.json", "w"), indent=1)
