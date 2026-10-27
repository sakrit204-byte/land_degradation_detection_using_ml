"""Column-width (3.4 in) figures for the IEEE-format paper (CARE-EW_Conference_Paper.docx).
Every number is read from outputs/results/. Output: paper/figs/*.png (300 dpi)."""
import json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from sklearn.metrics import roc_curve, precision_recall_curve, roc_auc_score, average_precision_score

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "outputs" / "results"; OUT = ROOT / "paper" / "figs"; OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                     "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "legend.fontsize": 6.5,
                     "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "axes.linewidth": 0.6, "lines.linewidth": 1.1,
                     "axes.spines.top": False, "axes.spines.right": False})
W = 3.4
M = json.load(open(RES / "metrics.json"))
INK, MUTED = "#222222", "#888888"
C_MODEL, C_B1, C_B2, C_B3 = "#1f5fa8", "#c0504d", "#e39b2d", "#6a9a3a"


def arch():
    fig, ax = plt.subplots(figsize=(W, 3.0)); ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")

    def box(x, y, w, h, title, sub, fc):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.18", fc=fc, ec=INK, lw=0.6))
        ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=6.8, weight="bold")
        ax.text(x + w / 2, y + h * 0.30, sub, ha="center", va="center", fontsize=5.6, color="#333333")

    def arrow(x1, y1, x2, y2):
        ax.annotate("", (x2, y2), (x1, y1), arrowprops=dict(arrowstyle="-|>", lw=0.7, color=INK, mutation_scale=7))
    # inputs
    ins = [("Sentinel-2", "10 m, monthly"), ("MODIS", "history, Landsat"), ("ERA5", "P, T, soil water"),
           ("Static", "DEM, water, rivers")]
    for i, (t, s) in enumerate(ins):
        box(0.1 + i * 2.48, 8.3, 2.3, 1.45, t, s, "#e8f0fa")
    box(0.6, 6.15, 8.8, 1.45, "Pre-processing", "de-duplication · BOA offset · cloud mask · monthly median", "#f3f3f3")
    for i in range(4):
        arrow(1.25 + i * 2.48, 8.3, 1.25 + i * 2.48 if i in (0, 3) else 5.0, 7.62)
    box(0.1, 3.75, 4.6, 1.75, "Climate conditioning", "ridge model per land cover\nresidual R = z − β·g, peer-relative", "#fdf1e3")
    box(5.3, 3.75, 4.6, 1.75, "Feature engineering", "state · change · residual ·\nresilience (AC1, variance) · context", "#fdf1e3")
    arrow(3.0, 6.15, 2.4, 5.52); arrow(7.0, 6.15, 7.6, 5.52); arrow(4.7, 4.6, 5.28, 4.6)
    box(0.1, 1.35, 3.0, 1.75, "Labels v3", "persistent decline\nonset in (t, t+6]", "#e9f5e4")
    box(3.5, 1.35, 3.0, 1.75, "LightGBM", "7 leaves, L2 = 50\nearly stop on AP", "#e9f5e4")
    box(6.9, 1.35, 3.0, 1.75, "Calibration", "isotonic + conformal\nα = 0.10 → abstain", "#e9f5e4")
    arrow(2.4, 3.75, 1.6, 3.12); arrow(7.6, 3.75, 5.0, 3.12); arrow(3.1, 2.2, 3.48, 2.2); arrow(6.5, 2.2, 6.88, 2.2)
    ax.text(5.0, 0.45, "Output: monthly risk map, warning / no-event / abstain, explanation, web console",
            ha="center", va="center", fontsize=6.2, style="italic")
    arrow(8.4, 1.35, 8.4, 0.75)
    fig.savefig(OUT / "arch.png", dpi=300, bbox_inches="tight"); plt.close(fig)


def roc_pr():
    d = pd.read_parquet(RES / "test_predictions.parquet"); b = pd.read_parquet(RES / "baseline_scores.parquet")
    assert (d["y"].values == b["y"].values).all()
    curves = [("CARE-EW (calibrated)", d["p"].values, C_MODEL, "-"), ("RF, Sentinel-2 only", b["RF Sentinel-only"].values, C_B3, "--"),
              ("Residual rule", b["residual rule"].values, C_B2, "-."), ("Anomaly persistence", b["persistence"].values, C_B1, ":")]
    y = d["y"].values
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 2.25)); hs = []
    for name, s, c, ls in curves:
        f, t, _ = roc_curve(y, s); a1.plot(f, t, color=c, ls=ls, label=name)
        p, r, _ = precision_recall_curve(y, s); k = r >= 0.01; a2.plot(r[k], p[k], color=c, ls=ls)
        hs.append((name, roc_auc_score(y, s), average_precision_score(y, s)))
    a1.plot([0, 1], [0, 1], color=MUTED, lw=0.6); a2.axhline(y.mean(), color=MUTED, lw=0.6)
    a1.set(xlabel="False-positive rate", ylabel="True-positive rate", title="(a) ROC"); a2.set(xlabel="Recall", ylabel="Precision", title="(b) Precision–recall", ylim=(0, 0.6))
    h, _ = a1.get_legend_handles_labels()
    fig.legend(h, [f"{n}: ROC {r:.3f}, PR {q:.3f}" for n, r, q in hs], loc="lower center", ncol=2, frameon=False, fontsize=5.4, handlelength=2.2)
    fig.tight_layout(pad=0.3, rect=(0, 0.17, 1, 1)); fig.savefig(OUT / "roc_pr.png", dpi=300); plt.close(fig)


def fit_curves():
    vc = pd.DataFrame(M["validation_curve"]); lc = pd.DataFrame(M["learning_curve"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 1.6))
    a1.plot(vc.num_leaves, vc.train_pr_auc, "o-", ms=2.5, color=C_B1, label="train")
    a1.plot(vc.num_leaves, vc.val_pr_auc, "s-", ms=2.5, color=C_MODEL, label="validation")
    a1.axvline(7, color=MUTED, lw=0.6, ls="--"); a1.set_xscale("log", base=2)
    a1.set_xticks([4, 16, 64, 256]); a1.set_xticklabels(["4", "16", "64", "256"]); a1.minorticks_off()
    a1.set(xlabel="Leaves per tree", ylabel="PR-AUC", title="(a) Capacity"); a1.legend(frameon=False, loc="lower right", fontsize=5.6)
    a2.plot(lc.rows / 1e3, lc.train_pr_auc, "o-", ms=2.5, color=C_B1, label="train")
    a2.plot(lc.rows / 1e3, lc.val_pr_auc, "s-", ms=2.5, color=C_MODEL, label="validation")
    a2.plot(lc.rows / 1e3, lc.test_pr_auc, "^-", ms=2.5, color=C_B3, label="test")
    a2.set_xscale("log"); a2.set_xticks([40, 100, 200, 400, 800]); a2.set_xticklabels(["40", "100", "200", "400", "800"]); a2.minorticks_off()
    a2.set(xlabel="Training rows (thousands)", title="(b) Training size"); a2.legend(frameon=False)
    fig.tight_layout(pad=0.3); fig.savefig(OUT / "fit_curves.png", dpi=300); plt.close(fig)


def ablation():
    ab = M["ablation"]
    rows = []
    for k, v in (ab.items() if isinstance(ab, dict) else [(x["name"], x) for x in ab]):
        if isinstance(v, dict) and "test" in v:
            rows.append((k, v["test"]["pr_auc"]))
        elif isinstance(v, dict) and "pr_auc" in v:
            rows.append((k, v["pr_auc"]))
    keep = ["A0_persistence(-z_mean3)", "A0_residual_rule(-R_mean3)", "RF_sentinel_only(A1+A2)", "LGB_A1_state", "LGB_A2_change",
            "LGB_A3_climate", "LGB_A4_residual", "LGB_A5_resilience", "LGB_A6_spatial"]
    lab = {"A0_persistence(-z_mean3)": "Persistence", "A0_residual_rule(-R_mean3)": "Residual rule", "RF_sentinel_only(A1+A2)": "RF S2-only",
           "LGB_A1_state": "+A1 state", "LGB_A2_change": "+A2 change", "LGB_A3_climate": "+A3 climate", "LGB_A4_residual": "+A4 residual",
           "LGB_A5_resilience": "+A5 resilience", "LGB_A6_spatial": "+A6 context"}
    dd = dict(rows); names = [k for k in keep if k in dd]; vals = [dd[k] for k in names]
    base = M["final_model"]["base_rate"]
    fig, ax = plt.subplots(figsize=(W, 1.7))
    cols = [MUTED if not k.startswith("LGB") else (C_MODEL if k in ("LGB_A4_residual", "LGB_A5_resilience", "LGB_A6_spatial") else "#9bb7d8") for k in names]
    ax.bar(range(len(names)), vals, color=cols, width=0.7)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.003, f"{v:.3f}", ha="center", fontsize=5.4)
    ax.axhline(base, color=C_B1, lw=0.6, ls="--"); ax.text(-0.45, base + 0.004, "chance", color=C_B1, fontsize=5.4, ha="left")
    ax.set_xticks(range(len(names))); ax.set_xticklabels([lab[k] for k in names], rotation=35, ha="right", fontsize=5.8)
    ax.set_ylabel("Test PR-AUC (raw)")
    fig.tight_layout(pad=0.3); fig.savefig(OUT / "ablation.png", dpi=300); plt.close(fig)
    return dict(zip(names, vals))


def walk_forward():
    wf = pd.DataFrame(M["walk_forward"])
    fig, ax = plt.subplots(figsize=(W, 1.45)); ax2 = ax.twinx(); ax2.spines["right"].set_visible(True)
    ax.plot(wf.test_year, wf.pr_auc, "o-", color=C_MODEL, ms=3, label="PR-AUC")
    ax.plot(wf.test_year, wf.base_rate, ":", color=MUTED, label="chance")
    ax2.bar(wf.test_year, wf.train_rows / 1e6, color="#dfe7f1", width=0.5, zorder=0)
    ax.set_zorder(ax2.get_zorder() + 1); ax.patch.set_visible(False)
    ax.set(xlabel="Test year (model retrained each January)", ylabel="Test PR-AUC"); ax2.set_ylabel("Training rows (M)", fontsize=6.5)
    ax.set_xticks(wf.test_year); ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(pad=0.3); fig.savefig(OUT / "walk_forward.png", dpi=300); plt.close(fig)


if __name__ == "__main__":
    arch(); roc_pr(); fit_curves(); print(ablation()); walk_forward()
    print("written", sorted(p.name for p in OUT.glob("*.png")))
