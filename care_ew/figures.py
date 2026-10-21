"""All paper figures. Each figure reads only files written by the pipeline (results/, processed/).
Run: python -m care_ew.figures [name ...]
Palette: validated categorical order (blue, orange, aqua, yellow, magenta, green, violet, red);
diverging blue<->red with grey midpoint; status colours reserved for warning states.
"""
import json, sys, warnings
import numpy as np, pandas as pd, xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from .config import AOIS, AOI_BY_KEY, PROC, FIG, OUT, LABEL, LABEL_SENSITIVITY, SPLIT

warnings.filterwarnings("ignore")
RES = OUT / "results"
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
STATUS = dict(good="#0ca30c", warning="#fab219", serious="#ec835a", critical="#d03b3b")
DIVERGE = LinearSegmentedColormap.from_list("bgr", ["#104281", "#3987e5", "#9ec5f4", "#f0efec", "#f4a3a2", "#e34948", "#8f1d1d"])
SEQ = LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#6da7ec", "#2a78d6", "#1c5cab", "#0d366b"])
RISK = LinearSegmentedColormap.from_list("risk", ["#fff3c4", "#fab219", "#ec835a", "#d03b3b", "#6e1414"])
GROUP_COL = {"A1_state": CAT[0], "A2_change": CAT[1], "A3_climate": CAT[2], "A4_residual": CAT[3],
             "A5_resilience": CAT[4], "A6_spatial": CAT[5]}

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.labelcolor": INK2,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2, "legend.frameon": False,
    "savefig.dpi": 200, "savefig.bbox": "tight",
})


def save(fig, name):
    fig.savefig(FIG / f"{name}.png"); fig.savefig(FIG / f"{name}.pdf"); plt.close(fig)
    print("figure", name, flush=True)


def metrics():
    return json.load(open(RES / "metrics.json"))


# ------------------------------------------------------------------ study design
def fig_study_areas():
    import geopandas as gpd
    from .config import RAW
    f = RAW / "ne_110m_admin_0_countries.zip"
    if not f.exists():
        import requests
        r = requests.get("https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip", timeout=120)
        f.write_bytes(r.content)
    world = gpd.read_file(f"zip://{f}")
    fig, ax = plt.subplots(figsize=(9, 4.4))
    world.plot(ax=ax, color="#ecebe6", edgecolor="#d6d5cf", linewidth=0.4)
    hl = world[world["ADMIN"].isin([a.country if a.country != "Brazil" else "Brazil" for a in AOIS] + ["United States of America"] * 0)]
    hl.plot(ax=ax, color="#cde2fb", edgecolor="#86b6ef", linewidth=0.5)
    for i, a in enumerate(AOIS):
        ax.plot(a.lon, a.lat, "o", ms=7, mfc=CAT[0], mec=SURF, mew=1.5, zorder=5)
        ax.annotate(f"{a.key}\n{a.landscape.split('/')[0][:30]}", (a.lon, a.lat), xytext=(6, 4), textcoords="offset points",
                    fontsize=7, color=INK, zorder=6)
    ax.set_xlim(-60, 160); ax.set_ylim(-45, 60); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for s in ax.spines.values(): s.set_visible(False)
    ax.set_title("Nine study areas (5.12 x 5.12 km each), nine nations, five continents", loc="left")
    save(fig, "fig01_study_areas")


def fig_aoi_mosaic(month="2024-03"):
    fig, axes = plt.subplots(3, 6, figsize=(12, 6.6))
    for i, a in enumerate(AOIS):
        ds = xr.open_dataset(PROC / a.key / "s2_monthly.nc")
        t = list(pd.DatetimeIndex(ds.time.values).strftime("%Y-%m"))
        # least-cloudy month near `month` with most valid pixels
        cand = [k for k in range(len(t)) if t[k][:4] == month[:4]]
        k = max(cand, key=lambda j: (ds["R"].values[j] != -32768).mean())
        rgb = np.stack([ds[c].values[k] for c in ("R", "G", "B")], -1).astype(float) * 1e-4
        rgb[rgb < -1] = np.nan
        rgb = np.clip(rgb / np.nanpercentile(rgb, 98), 0, 1); rgb = np.nan_to_num(rgb, nan=1)
        st = xr.open_dataset(PROC / a.key / "static.nc")
        ax = axes[(i // 3), (i % 3) * 2]; ax.imshow(rgb); ax.set_title(f"{a.key}  {t[k]}", fontsize=8, loc="left")
        ax2 = axes[(i // 3), (i % 3) * 2 + 1]
        lc = st.landcover.values
        cmap = ListedColormap(["#006400", "#ffbb22", "#ffff4c", "#f096ff", "#fa0000", "#b4b4b4", "#f0f0f0", "#0064c8", "#0096a0", "#00cf75", "#fae6a0"])
        vals = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        idx = np.searchsorted(vals, lc)
        ax2.imshow(idx, cmap=cmap, vmin=0, vmax=10, interpolation="nearest"); ax2.set_title("ESA WorldCover 2021", fontsize=8, loc="left")
        for x in (ax, ax2): x.set_xticks([]); x.set_yticks([]); x.grid(False)
    from matplotlib.patches import Patch
    names = ["tree", "shrub", "grass", "crop", "built", "bare", "snow", "water", "wetland", "mangrove", "moss"]
    cols = ["#006400", "#ffbb22", "#ffff4c", "#f096ff", "#fa0000", "#b4b4b4", "#f0f0f0", "#0064c8", "#0096a0", "#00cf75", "#fae6a0"]
    fig.legend([Patch(color=c) for c in cols], names, loc="lower center", ncol=11, fontsize=7)
    fig.suptitle("Sentinel-2 true colour (monthly median) and land cover for each AOI", x=0.01, ha="left", fontweight="bold")
    save(fig, "fig02_aoi_mosaic")


# ------------------------------------------------------------------ method illustration
def fig_method_example(aoi="ESP_murcia"):
    c = np.load(PROC / aoi / "cube.npz")
    times = pd.to_datetime(c["times"])
    onset = c["onset"]; y = c["y"].astype(float)
    cand = np.nonzero(onset[(times >= "2019-06") & (times <= "2025-06")].any(0))[0]
    if len(cand) == 0:
        return
    p = cand[len(cand) // 2]
    nd, mu, sg = c["ndvi"][:, p].astype(float), c["mu"][:, p].astype(float), float(c["sigma"][p])
    z, zh, R = c["z"][:, p].astype(float), c["zhat"][:, p].astype(float), c["R_lab"][:, p].astype(float)
    m = times.month.values
    fig, ax = plt.subplots(3, 1, figsize=(9, 6.4), sharex=True)
    ax[0].plot(times, nd, color=CAT[0], label="observed NDVI  Y")
    ax[0].plot(times, mu[m - 1], color=MUTED, lw=1.5, ls="--", label="seasonal baseline  mu_m (2017-2020)")
    ax[0].set_ylabel("NDVI"); ax[0].legend(loc="lower left", fontsize=8); ax[0].set_title(f"(a) Observation and baseline - {aoi}, pixel {p}", loc="left")
    ax[1].plot(times, z, color=CAT[0], label="anomaly z")
    ax[1].plot(times, zh, color=CAT[2], label="climate-expected anomaly  z-hat")
    ax[1].axhline(0, color=AXIS, lw=0.8); ax[1].legend(loc="lower left", fontsize=8); ax[1].set_ylabel("SD units")
    ax[1].set_title("(b) Climate conditioning", loc="left")
    ax[2].plot(times, R, color=CAT[1], label="peer-relative residual  R = (z - z-hat) - same-class median")
    ax[2].axhline(LABEL.resid_thr, color=STATUS["critical"], lw=1, ls=":", label=f"threshold {LABEL.resid_thr}")
    for t in times[onset[:, p]]:
        ax[2].axvline(t, color=STATUS["critical"], lw=1.5)
        ax[2].axvspan(t - pd.DateOffset(months=LABEL.horizon), t, color="#fab219", alpha=0.18, lw=0)
    ax[2].text(0.01, 0.06, "red line = event onset (>= 6 consecutive months below, mean NDVI loss vs peers >= 0.05);  shaded = months t labelled y=1",
               transform=ax[2].transAxes, fontsize=7.5, color=INK2)
    ax[2].legend(loc="upper left", fontsize=8); ax[2].set_ylabel("SD units"); ax[2].set_title("(c) Persistent unexplained decline -> future-event label", loc="left")
    save(fig, "fig03_method_example")


def fig_label_stats():
    rows = {}
    for a in AOIS:
        f = PROC / a.key / "dataset_info.json"
        if f.exists():
            rows[a.key] = json.load(open(f))["yearly_pos_rate"]
    df = pd.DataFrame(rows).T
    df = df[[c for c in df.columns if 2019 <= int(c) <= 2025]]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    im = ax.imshow(df.values * 100, cmap=SEQ, aspect="auto")
    ax.set_xticks(range(df.shape[1]), df.columns); ax.set_yticks(range(df.shape[0]), df.index); ax.grid(False)
    for i in range(df.shape[0]):
        for j in range(df.shape[1]):
            v = df.values[i, j] * 100
            ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=7, color="white" if v > np.nanmax(df.values) * 60 else INK)
    plt.colorbar(im, ax=ax, label="% of eligible pixel-months with y = 1")
    ax.set_title("Positive-label rate by AOI and year (same rule everywhere)", loc="left")
    save(fig, "fig04_label_rates")


def fig_climate_model():
    rows = []
    for a in AOIS:
        f = PROC / a.key / "dataset_info.json"
        if f.exists():
            for c, v in json.load(open(f))["climate_model"].items():
                rows.append(dict(aoi=a.key, cls=c, r2=v["r2_loyo"], used=v["used"], n=v["n_pix"]))
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    names = {"10": "tree", "20": "shrub", "30": "grass", "40": "crop", "60": "bare", "90": "wetland", "-1": "pooled small"}
    for i, (k, g) in enumerate(df.groupby("aoi", sort=False)):
        for _, r in g.iterrows():
            ax.scatter(i, r.r2, s=12 + 60 * np.sqrt(r.n / df.n.max()), color=CAT[0] if r.used else MUTED, edgecolor=SURF, lw=1, zorder=3)
    ax.axhline(0.05, color=STATUS["critical"], lw=1, ls=":")
    ax.text(len(df.aoi.unique()) - 0.5, 0.06, "applied only if LOYO R2 >= 0.05", ha="right", fontsize=7.5, color=INK2)
    ax.set_xticks(range(df.aoi.nunique()), df.aoi.unique(), rotation=30, ha="right")
    ax.set_ylabel("leave-one-year-out R2"); ax.set_ylim(max(-0.6, df.r2.min() - 0.05), min(1, df.r2.max() + 0.1))
    ax.set_title("Climate-expectation model skill per AOI x land-cover class (blue = used, grey = rejected)", loc="left")
    save(fig, "fig05_climate_model_skill")


# ------------------------------------------------------------------ results
def fig_ablation():
    m = metrics()
    ab = m["ablation"]
    order = [k for k in ab if k.startswith("A0")] + ["RF_sentinel_only(A1+A2)"] + [k for k in ab if k.startswith("LGB_")]
    vals = [ab[k].get("pr_auc", np.nan) for k in order]
    base = ab[order[0]]["base_rate"]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    cols = [MUTED] * 4 + [CAT[0]] * (len(order) - 4)
    ax.bar(range(len(order)), vals, color=cols, width=0.65)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center", fontsize=7.5, color=INK)
    ax.axhline(base, color=STATUS["critical"], lw=1, ls=":")
    ax.text(5.5, base * 0.55, f"no skill = base rate {base:.3f}", ha="center", fontsize=7.5, color=INK2,
            bbox=dict(boxstyle="round,pad=0.2", fc=SURF, ec="none"))
    lab = [k.replace("LGB_", "+").replace("_", " ") for k in order]
    ax.set_xticks(range(len(order)), lab, rotation=28, ha="right", fontsize=7.5)
    ax.set_ylabel("PR-AUC (locked test: unseen 1 km blocks, 2024-12 to 2025-10)", fontsize=8)
    ax.set_title("Cumulative ablation A0 -> A6 on the locked test set (grey = non-learning / Sentinel-only baselines)", loc="left")
    ax.grid(axis="x", visible=False)
    save(fig, "fig06_ablation")


def fig_reliability():
    tp = pd.read_parquet(RES / "test_predictions.parquet")
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.8))
    bins = np.quantile(tp.p, np.linspace(0, 1, 13)); bins[0], bins[-1] = 0, 1
    g = tp.groupby(pd.cut(tp.p, np.unique(bins), include_lowest=True), observed=True)
    ax[0].plot([0, 1], [0, 1], color=AXIS, lw=1, ls="--")
    ax[0].plot(g.p.mean(), g.y.mean(), "o-", color=CAT[0], ms=6, mec=SURF, label="calibrated CARE-EW (test)")
    ax[0].set_xlabel("predicted probability"); ax[0].set_ylabel("observed event frequency"); ax[0].legend(loc="upper left")
    mx = max(g.p.mean().max(), g.y.mean().max()) * 1.1
    ax[0].set_xlim(0, mx); ax[0].set_ylim(0, mx); ax[0].set_title("(a) Reliability", loc="left")
    ax[1].hist(tp.p[tp.y == 0], bins=50, color=CAT[0], alpha=0.85, label="y = 0", density=True)
    ax[1].hist(tp.p[tp.y == 1], bins=50, color=CAT[1], alpha=0.75, label="y = 1", density=True)
    ax[1].set_yscale("log"); ax[1].set_xlabel("predicted probability"); ax[1].legend(); ax[1].set_title("(b) Score distributions", loc="left")
    save(fig, "fig07_reliability")


def fig_pr_curves():
    from sklearn.metrics import precision_recall_curve
    tp = pd.read_parquet(RES / "test_predictions.parquet")
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    pr, rc, _ = precision_recall_curve(tp.y, tp.p)
    ax.plot(rc, pr, color=CAT[0], label="CARE-EW (A6 + calibration)")
    ax.axhline(tp.y.mean(), color=STATUS["critical"], ls=":", lw=1, label=f"no skill ({tp.y.mean():.3f})")
    if (RES / "baseline_scores.parquet").exists():
        bs = pd.read_parquet(RES / "baseline_scores.parquet")
        for i, c in enumerate([c for c in bs.columns if c != "y"]):
            pr, rc, _ = precision_recall_curve(bs.y, bs[c]); ax.plot(rc, pr, color=CAT[i + 1], lw=1.5, label=c)
    ax.set_xlabel("recall"); ax.set_ylabel("precision"); ax.legend(fontsize=7.5); ax.set_title("Precision-recall on the locked test set", loc="left")
    save(fig, "fig08_pr_curves")


def fig_fit_curves():
    m = metrics()
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.8))
    vc = pd.DataFrame(m.get("validation_curve", []))
    if len(vc):
        ax[0].plot(vc.num_leaves, vc.train_pr_auc, "o-", color=CAT[1], ms=6, mec=SURF, label="train")
        ax[0].plot(vc.num_leaves, vc.val_pr_auc, "o-", color=CAT[0], ms=6, mec=SURF, label="validation (new blocks, 2023)")
        ax[0].set_xscale("log", base=2); ax[0].set_xlabel("num_leaves (min_child_samples decreases ->)")
        ax[0].set_ylabel("PR-AUC"); ax[0].legend(); ax[0].set_title("(a) Validation curve: capacity vs generalisation", loc="left")
    lc = pd.DataFrame(m.get("learning_curve", []))
    if len(lc):
        ax[1].plot(lc.rows, lc.train_pr_auc, "o-", color=CAT[1], ms=6, mec=SURF, label="train")
        ax[1].plot(lc.rows, lc.val_pr_auc, "o-", color=CAT[0], ms=6, mec=SURF, label="validation")
        ax[1].plot(lc.rows, lc.test_pr_auc, "o-", color=CAT[2], ms=6, mec=SURF, label="test")
        ax[1].set_xscale("log"); ax[1].set_xlabel("training rows (pixel subsample)"); ax[1].legend()
        ax[1].set_title("(b) Learning curve: more data vs skill", loc="left")
    save(fig, "fig09_fit_curves")


def fig_walk_forward():
    wf = pd.DataFrame(metrics().get("walk_forward", []))
    if not len(wf):
        return
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.plot(wf.test_year, wf.pr_auc, "o-", color=CAT[0], ms=7, mec=SURF, label="PR-AUC")
    ax.plot(wf.test_year, wf.base_rate, "o--", color=MUTED, ms=5, lw=1.5, label="base rate")
    for _, r in wf.iterrows():
        lab = f"{r.train_rows/1e6:.2f}M rows" if r.train_rows >= 1e5 else f"{r.train_rows/1e3:.0f}k rows"
        ax.annotate(lab, (r.test_year, r.pr_auc), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=7, color=INK2)
    ax.set_xticks(wf.test_year.astype(int))
    ax.set_xlabel("test year (model retrained each year on all earlier data)"); ax.set_ylabel("score"); ax.legend()
    ax.set_title("Continuous (walk-forward) retraining", loc="left")
    save(fig, "fig10_walk_forward")


def fig_loco():
    lo = metrics().get("leave_one_country_out", {})
    if not lo:
        return
    df = pd.DataFrame(lo).T.sort_values("pr_auc")
    fig, ax = plt.subplots(figsize=(7, 3.8))
    y = np.arange(len(df))
    ax.barh(y, df.pr_auc, color=CAT[0], height=0.6, label="PR-AUC (country never seen in training)")
    ax.scatter(df.base_rate, y, color=STATUS["critical"], marker="|", s=200, lw=2, zorder=3, label="base rate (no skill)")
    for i, (k, r) in enumerate(df.iterrows()):
        ax.text(r.pr_auc + 0.005, i, f"{r.pr_auc:.2f}  (x{r.pr_auc / r.base_rate:.1f})", va="center", fontsize=7.5, color=INK)
    for i, (k, r) in enumerate(df.iterrows()):
        if not np.isfinite(r.pr_auc):
            ax.text(0.003, i, "no events in test period (cannot be scored)", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(y, df.index); ax.set_xlabel("PR-AUC"); ax.legend(loc="lower right", fontsize=7.5)
    ax.set_title("Leave-one-country-out transfer (bar label: PR-AUC and multiple of the base rate)", loc="left"); ax.grid(axis="y", visible=False)
    save(fig, "fig11_loco")


def fig_lead_time():
    lt = metrics()["final_model"]["lead_time"]["lead_hist"]
    k = sorted(int(x) for x in lt); v = [lt[str(x)] if str(x) in lt else lt[x] for x in k]
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.bar(k, v, color=[MUTED if x == 0 else CAT[0] for x in k], width=0.7)
    ax.set_xticks(k, ["missed" if x == 0 else f"{x}" for x in k]); ax.set_xlabel("months of warning before onset")
    ax.set_ylabel("test events"); ax.set_title("Warning lead time at the operating threshold", loc="left"); ax.grid(axis="x", visible=False)
    save(fig, "fig12_lead_time")


def fig_shap():
    from .features import FEATURE_GROUPS
    imp = pd.read_csv(RES / "shap_importance.csv", index_col=0).iloc[:, 0].head(22)[::-1]
    def grp(f):
        if f.startswith("clim_"): return "A3_climate"
        for g, cols in FEATURE_GROUPS.items():
            if cols and f in cols: return g
        return "A1_state"
    fig, ax = plt.subplots(figsize=(6.5, 5.2))
    ax.barh(range(len(imp)), imp.values, color=[GROUP_COL[grp(f)] for f in imp.index], height=0.65)
    ax.set_yticks(range(len(imp)), imp.index, fontsize=7.5); ax.set_xlabel("mean |SHAP| (log-odds)")
    from matplotlib.patches import Patch
    ax.legend([Patch(color=c) for c in GROUP_COL.values()], GROUP_COL.keys(), fontsize=7, loc="lower right")
    ax.set_title("What drives the warnings (test set)", loc="left"); ax.grid(axis="y", visible=False)
    save(fig, "fig13_shap")


def fig_corroboration():
    f = RES / "corroboration.json"
    if not f.exists():
        return
    co = json.load(open(f))
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, sensor in zip(axes, ("landsat", "modis")):
        keys = [k for k in co if sensor in co[k] and "auc_agreement" in co[k][sensor]]
        data_e, data_c = [], []
        for k in keys:
            z = np.load(RES / f"corrob_{k}_{sensor}.npz"); data_e.append(np.clip(z["ze"], -6, 6)); data_c.append(np.clip(z["zc"], -6, 6))
        pos = np.arange(len(keys))
        b1 = ax.boxplot(data_c, positions=pos - 0.18, widths=0.3, patch_artist=True, showfliers=False)
        b2 = ax.boxplot(data_e, positions=pos + 0.18, widths=0.3, patch_artist=True, showfliers=False)
        for b, c in ((b1, CAT[0]), (b2, CAT[1])):
            for p in b["boxes"]: p.set_facecolor(c); p.set_edgecolor(SURF)
            for p in b["medians"]: p.set_color(INK)
        ax.set_xticks(pos, [k.split("_")[0] + "\nAUC " + format(co[k][sensor]["auc_agreement"], ".2f") for k in keys], fontsize=7.5)
        ax.axhline(0, color=AXIS, lw=0.8); ax.set_ylim(-6.5, 6.5)
        ax.set_title(f"{'Landsat 8/9 (30 m)' if sensor == 'landsat' else 'MODIS Terra (250 m)'}", loc="left")
    axes[0].set_ylabel("independent-sensor NDVI anomaly z\n(months s..s+3)")
    from matplotlib.patches import Patch
    axes[1].legend([Patch(color=CAT[0]), Patch(color=CAT[1])], ["control pixel-months", "S2 event onsets"], loc="lower right", fontsize=7.5)
    fig.suptitle("Do other sensors see the Sentinel-2-labelled declines?", x=0.01, ha="left", fontweight="bold")
    save(fig, "fig14_corroboration")


def fig_risk_maps():
    fig, axes = plt.subplots(3, 3, figsize=(10, 10.4))
    for ax, a in zip(axes.ravel(), AOIS):
        f = OUT / "predictions" / f"{a.key}_risk.npz"
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        if not f.exists():
            continue
        z = np.load(f, allow_pickle=True)
        H, W = int(z["H"]), int(z["W"])
        img = np.full((H, W), np.nan); st = np.full((H, W), 255)
        img[z["rr"], z["cc"]] = z["risk"][-1].astype(float); st[z["rr"], z["cc"]] = z["status"][-1]
        ax.imshow(np.where(st == 255, 1, np.nan), cmap=ListedColormap(["#e1e0d9"]), vmin=0, vmax=1)
        im = ax.imshow(img, cmap=RISK, vmin=0, vmax=max(0.3, np.nanpercentile(img, 99.5)))
        act = np.where(st == 3, 1, np.nan)
        ax.imshow(act, cmap=ListedColormap(["#b9b7ae"]), alpha=0.55)
        ax.set_title(f"{a.key} - {str(z['months'][-1])}", fontsize=8.5, loc="left")
    cb = fig.colorbar(im, ax=axes, shrink=0.5, location="bottom", pad=0.03, label="P(persistent degradation onset within 6 months)")
    fig.suptitle("Early-warning maps, latest month. Warm colours: P(onset within 6 months) for eligible pixels. "
                 "Grey wash: below peers this month (not eligible for an early warning); light grey: masked (water, built-up).",
                 x=0.01, ha="left", fontweight="bold", fontsize=9.5)
    save(fig, "fig15_risk_maps")


def fig_hydro():
    rows = []
    for a in AOIS:
        f = PROC / a.key / "hydro_summary.json"
        if f.exists():
            for s in json.load(open(f))["stations"]:
                if s.get("available"):
                    rows.append(dict(aoi=a.key, st=s["name"], before=s["mean_before"], now=s["mean_now"], d=s.get("change_mean_pct"), dl=s.get("change_lowflow_pct")))
    if not rows:
        return
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    x = np.arange(len(df))
    ax.bar(x - 0.2, df.before, 0.38, color=MUTED, label="1984-2000 mean")
    ax.bar(x + 0.2, df.now, 0.38, color=CAT[0], label="2016-present mean")
    ax.set_yscale("log"); ax.set_xticks(x, [f"{r.aoi.split('_')[0]}\n{r.st}" for r in df.itertuples()], fontsize=6.5)
    ax.set_ylabel("GloFAS discharge (m3/s, log)"); ax.legend(); ax.set_title("River flow feeding each AOI: before vs now", loc="left")
    save(fig, "fig16_hydro")


def fig_label_sensitivity():
    f = RES / "label_sensitivity.csv"
    if not f.exists():
        return
    df = pd.read_csv(f)
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    for i, (m, g) in enumerate(df.groupby("min_run")):
        ax[0].plot(g.resid_thr, g.pos_rate * 100, "o-", color=CAT[i], ms=6, mec=SURF, label=f"min run {m} mo")
        if "pr_auc" in g:
            ax[1].plot(g.resid_thr, g.pr_auc / g.base_rate, "o-", color=CAT[i], ms=6, mec=SURF, label=f"min run {m} mo")
    ax[0].set_xlabel("residual threshold"); ax[0].set_ylabel("% positive"); ax[0].legend(); ax[0].set_title("(a) Label prevalence", loc="left")
    ax[1].set_xlabel("residual threshold"); ax[1].set_ylabel("PR-AUC lift over base rate"); ax[1].set_title("(b) Predictability under each definition", loc="left")
    save(fig, "fig17_label_sensitivity")


def fig_evidence_gallery(n=6, half=24):
    """Proof figure: highest-confidence TRUE warnings on the locked test set (one per AOI where possible).
    Columns: S2 true colour 12 months before the warning | at the warning | 3 months after onset |
    pixel time series (NDVI, peer-relative residual) with warning (orange) and onset (red) marked."""
    from . import s2 as s2mod
    tp = pd.read_parquet(RES / "test_predictions.parquet")
    thr = metrics()["final_model"]["thr"]
    hits = tp[(tp.y == 1) & (tp.p >= thr)].sort_values(["p", "months_to_onset"], ascending=False)
    hits = hits.drop_duplicates(["aoi", "pix"])          # one row per pixel (earliest-lead warning kept)
    pick = hits.groupby("aoi").head(1).head(n)
    if len(pick) < n:
        pick = pd.concat([pick, hits[~hits.index.isin(pick.index)].head(n - len(pick))])
    fig, axes = plt.subplots(len(pick), 4, figsize=(12, 2.9 * len(pick)), gridspec_kw=dict(width_ratios=[1, 1, 1, 2.6]),
                             constrained_layout=True)
    axes = np.atleast_2d(axes)
    for r, (_, row) in enumerate(pick.iterrows()):
        c = np.load(PROC / row.aoi / "cube.npz")
        times = pd.to_datetime(c["times"]); rr, cc = int(c["rr"][row.pix]), int(c["cc"][row.pix])
        ds = s2mod.load(row.aoi)
        t_w = pd.Timestamp(row.time); t_on = t_w + pd.DateOffset(months=int(row.months_to_onset))
        def chip(t):
            # nearest month with a mostly clear chip
            order = np.argsort(np.abs((times - t).days))
            for k in order[:6]:
                rgb = np.stack([ds[b].values[k, max(0, rr - half):rr + half, max(0, cc - half):cc + half] for b in ("R", "G", "B")], -1)
                if np.isfinite(rgb).mean() > 0.9:
                    return np.clip(np.nan_to_num(rgb) / 0.25, 0, 1), times[k]
            return np.ones((2 * half, 2 * half, 3)), t
        for j, (t, title) in enumerate([(t_w - pd.DateOffset(months=12), "12 mo before warning"), (t_w, "at warning"),
                                        (t_on + pd.DateOffset(months=3), "3 mo after onset")]):
            img, tt = chip(t)
            ax = axes[r, j]; ax.imshow(img); ax.plot(half, half, "s", ms=7, mfc="none", mec="#ff3b30", mew=1.5)
            ax.set_title(f"{title} · {tt:%Y-%m}", fontsize=7.5, loc="left"); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        ax = axes[r, 3]
        nd = c["ndvi"][:, row.pix].astype(float); R = c["R"][:, row.pix].astype(float)
        ax.plot(times, nd, color=CAT[0], lw=1.5, label="NDVI")
        ax.plot(times, np.clip(R, -6, 6) / 10 + 0.0, color=CAT[1], lw=1.2, alpha=0.9, label="residual R / 10")
        ax.axvline(t_w, color=STATUS["warning"], lw=2, label=f"warning p={row.p:.2f}")
        ax.axvline(t_on, color=STATUS["critical"], lw=2, label="onset (label)")
        ax.set_xlim(times[0], times[-1]); ax.legend(fontsize=6.5, loc="lower left", ncol=2)
        ax.set_title(f"{row.aoi} · pixel {row.pix} · lead {int(row.months_to_onset)} mo", fontsize=8, loc="left")
    fig.suptitle("Evidence gallery: correct early warnings on the locked test set (unseen place + unseen time)", x=0.01, ha="left", fontweight="bold")
    save(fig, "fig18_evidence_gallery")


ALL = [fig_study_areas, fig_aoi_mosaic, fig_method_example, fig_label_stats, fig_climate_model, fig_ablation,
       fig_reliability, fig_pr_curves, fig_fit_curves, fig_walk_forward, fig_loco, fig_lead_time, fig_shap,
       fig_corroboration, fig_risk_maps, fig_hydro, fig_label_sensitivity, fig_evidence_gallery]

if __name__ == "__main__":
    names = sys.argv[1:]
    for f in ALL:
        if not names or f.__name__ in names:
            try:
                f()
            except Exception as e:
                print("FAILED", f.__name__, repr(e), flush=True)
