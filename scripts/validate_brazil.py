"""Independent validation in BRA_matopiba against official, expert-mapped clearing polygons.

References (both independent of our Sentinel-2 processing):
  * INPE PRODES Cerrado yearly deforestation polygons (PRODES year Y = Aug Y-1 ... Jul Y), 2019-2025
  * MapBiomas Alerta validated alerts (detection year), 2019-2025
Tests:
  1. label recall   - share of officially cleared pixels (year Y) with an S2 label onset in [Aug Y-1 - 3 mo, Jul Y + 6 mo]
  2. label precision - share of S2 onsets 2019-2025 that fall inside any official clearing polygon of 2019-2025
     (expected partial: our label = persistent decline incl. degradation, crop failure; PRODES = clearing of
     native vegetation only)
  3. warning skill  - for pixels cleared in PRODES years 2023-2025, max calibrated risk in the 12 months up to
     the end of the clearing year (eligible months only) vs the same statistic for never-cleared pixels -> AUC
Output: outputs/results/brazil_validation.json, outputs/figures/fig19_brazil_independent.png
"""
import json, sys
sys.path.insert(0, ".")
import numpy as np, pandas as pd, geopandas as gpd
from rasterio.features import rasterize
from affine import Affine
from sklearn.metrics import roc_auc_score
from care_ew.config import AOI_BY_KEY, PROC, OUT
from care_ew.s2 import grid_info

KEY = "BRA_matopiba"
GR = "data/ground_ref/"
aoi = AOI_BY_KEY[KEY]; g = grid_info(aoi)
H = W = g["n"]
tr = Affine(10, 0, g["x0"], 0, -10, g["y0"] + g["n"] * 10)

prodes = gpd.read_file(GR + "prodes_cerrado/yearly_deforestation_bbox+0.05deg.geojson").to_crs(g["epsg"])
alerta = gpd.read_file(GR + "mapbiomas_alerta/BRA_matopiba_alerts_bbox+0.1deg.geojson").to_crs(g["epsg"])
prodes["year"] = prodes["year"].astype(int); alerta["year"] = alerta["ano_det"].astype(int)
ref = pd.concat([prodes[["year", "geometry"]].assign(src="PRODES"), alerta[["year", "geometry"]].assign(src="Alerta")])
ref = ref[(ref.year >= 2019) & (ref.year <= 2025)]


def burn(gdf):
    if len(gdf) == 0:
        return np.zeros((H, W), np.int16)
    shapes = sorted(zip(gdf.geometry, gdf.year), key=lambda s: s[1])   # earliest year wins (burn later first)
    return rasterize([(geom, int(y)) for geom, y in reversed(shapes)], out_shape=(H, W), transform=tr, fill=0, dtype="int16")


yr_any = burn(ref); yr_prodes = burn(ref[ref.src == "PRODES"]); yr_alerta = burn(ref[ref.src == "Alerta"])

c = np.load(PROC / KEY / "cube.npz")
rr, cc = c["rr"].astype(int), c["cc"].astype(int)
times = pd.to_datetime(c["times"]); onset = c["onset"]
pix_year = yr_any[rr, cc]
res = dict(reference_pixels_in_aoi={str(y): int((pix_year == y).sum()) for y in range(2019, 2026)},
           reference_area_ha=float((pix_year > 0).sum() * 0.01),
           polygons_in_bbox_2019_2025=dict(PRODES=int((ref.src == "PRODES").sum()), Alerta=int((ref.src == "Alerta").sum())))

# 1. label recall
hit, tot = 0, 0
per_year = {}
for y in range(2019, 2026):
    px = np.nonzero(pix_year == y)[0]
    if len(px) == 0:
        continue
    w = (times >= pd.Timestamp(f"{y-1}-05-01")) & (times <= pd.Timestamp(f"{y}-12-31"))
    h = onset[w][:, px].any(0)
    per_year[str(y)] = dict(pixels=int(len(px)), recall=float(h.mean()))
    hit += int(h.sum()); tot += len(px)
res["label_recall"] = dict(overall=hit / max(tot, 1), n_pixels=tot, by_year=per_year)
# baseline: chance of an onset in a random 20-month window for never-cleared pixels
never = np.nonzero(pix_year == 0)[0]
w = (times >= "2021-05-01") & (times <= "2022-12-31")
res["label_recall"]["background_rate_never_cleared_same_window_length"] = float(onset[w][:, never].any(0).mean())

# 2. label precision
sel = (times >= "2019-01-01") & (times <= "2025-12-31")
on_px = onset[sel].any(0)
res["label_precision"] = dict(share_of_S2_onset_pixels_inside_official_clearings=float((pix_year[on_px] > 0).mean()),
                              share_of_all_pixels_inside_official_clearings=float((pix_year > 0).mean()),
                              n_onset_pixels=int(on_px.sum()))

# 3. warning skill
pz = np.load(OUT / "predictions" / f"{KEY}_risk.npz", allow_pickle=True)
risk = pz["risk"].astype(np.float32); months = pd.to_datetime(pz["months"])
scores, labels, info = [], [], {}
for y in (2023, 2024, 2025):
    px = np.nonzero(pix_year == y)[0]
    win = (months >= pd.Timestamp(f"{y-1}-01-01")) & (months <= pd.Timestamp(f"{y}-07-31"))
    if len(px) == 0 or win.sum() == 0:
        continue
    s_pos = np.nanmax(risk[win][:, px], 0)
    s_neg = np.nanmax(risk[win][:, never], 0)
    ok_p, ok_n = np.isfinite(s_pos), np.isfinite(s_neg)
    scores += [s_pos[ok_p], s_neg[ok_n]]; labels += [np.ones(ok_p.sum()), np.zeros(ok_n.sum())]
    info[str(y)] = dict(cleared_pixels_scored=int(ok_p.sum()), median_max_risk_cleared=float(np.median(s_pos[ok_p])) if ok_p.any() else None,
                        median_max_risk_never=float(np.median(s_neg[ok_n])))
if scores:
    sc, lb = np.concatenate(scores), np.concatenate(labels)
    res["warning_skill"] = dict(auc=float(roc_auc_score(lb, sc)), n_cleared=int(lb.sum()), n_never=int((lb == 0).sum()), by_year=info)

json.dump(res, open(OUT / "results" / "brazil_validation.json", "w"), indent=2)
print(json.dumps(res, indent=1))

# figure
import matplotlib; matplotlib.use("Agg")
from care_ew import figures as F
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
fig, ax = plt.subplots(1, 2, figsize=(10, 5))
grid_on = np.full((H, W), np.nan); grid_on[rr, cc] = np.where(on_px, 1, np.nan)
ax[0].imshow(np.where(yr_any > 0, yr_any, np.nan), cmap="viridis", vmin=2019, vmax=2025)
ax[0].imshow(grid_on, cmap=ListedColormap(["#e34948"]), alpha=0.45)
ax[0].set_title("Official clearings 2019-25 (colour = year)\nred wash = Sentinel-2 label onsets 2019-25", loc="left", fontsize=9)
last = np.full((H, W), np.nan); last[rr, cc] = np.nanmax(risk[-12:], 0)
ax[1].imshow(last, cmap=F.RISK, vmin=0, vmax=0.4)
ax[1].contour(yr_any >= 2025, levels=[0.5], colors="#2a78d6", linewidths=1)
ax[1].set_title("Max warning risk, last 12 months\nblue outline = 2025 official clearings", loc="left", fontsize=9)
for a in ax: a.set_xticks([]); a.set_yticks([]); a.grid(False)
F.save(fig, "fig19_brazil_independent")
