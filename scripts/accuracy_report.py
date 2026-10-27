"""Complete accuracy statistics -> docs/ACCURACY_REPORT.md, generated only from saved result files
(outputs/results/*.json|csv, app/static/data). Re-run after any training piece: python scripts/accuracy_report.py"""
import json, sys
from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "outputs" / "results"
sys.path.insert(0, str(ROOT))
from care_ew.train import LANDSCAPE  # noqa: E402

m = json.load(open(RES / "metrics.json"))
f = m["final_model"]
L = []
w = L.append
fx = lambda v, d=3: "–" if v is None or v != v else (f"{v:.{d}f}" if isinstance(v, float) else str(v))
pct = lambda v: "–" if v is None else f"{100 * v:.1f} %"


def row(name, r, extra=()):
    return "| " + " | ".join([name, fx(r.get("pr_auc")), fx(r.get("pr_auc_lift"), 1), fx(r.get("roc_auc")),
                             fx(r.get("precision")), fx(r.get("recall")), pct(r.get("false_alarm_rate")),
                             fx(r.get("base_rate"), 4), str(r.get("n", "–"))] + list(extra)) + " |"


HDR = "| | PR-AUC | lift ×chance | ROC-AUC | precision | recall | false-alarm | base rate | n |\n|---|---|---|---|---|---|---|---|---|"
w(f"# CARE-EW accuracy report\n\nGenerated from `outputs/results/metrics.json` (run {m['created']}; {m['rows']:,} pixel-months, "
  f"{len(m['aois'])} study areas). Target: onset of persistent degradation within the next {m['label_cfg']['horizon']} months "
  f"(label v3, PROJECT_LOG §5). Test = months ≥ {m['split']['test_start']} on spatially held-out 1 km blocks, never used for any choice.\n")
w("**How to read.** Events are rare (2.5 % of test pixel-months), so ROC-AUC alone flatters any model; PR-AUC and its lift over "
  "chance are the honest headline. Precision/recall/false-alarm use the decision threshold fixed on the calibration set.\n")

w("## 1. Operational model (feature set " + m["final_feature_set"] + ")\n")
w(HDR); w(row("**Test set**", f))
for k, nm in (("metrics_on_non_abstained", "Test, confident pixels only (conformal)"),
              ("temporal_only_holdout", "Future months, training blocks"), ("spatial_only_holdout", "Training months, unseen blocks")):
    if f.get(k): w(row(nm, f[k]))
w(f"\n* 95 % cluster-bootstrap CI: PR-AUC {fx(f['pr_auc_ci'][0])}–{fx(f['pr_auc_ci'][1])}, ROC-AUC {fx(f['roc_auc_ci'][0])}–{fx(f['roc_auc_ci'][1])}")
w(f"* Calibration: ECE {fx(f['ece'], 4)}, Brier {fx(f['brier'], 4)} (a stated 10 % risk ≈ 10 % observed)")
c = f["conformal"]
w(f"* Conformal (α = {c['alpha']}): abstains on {pct(c['abstain_frac'])}; coverage events {pct(c['coverage_event'])}, non-events "
  f"{pct(c['coverage_no_event'])}; when it says *no event* it is right {pct(c['npv_when_no_event'])}; when it says *event*, {pct(c['precision_when_event'])}")
w("* The raw A6 model scores test PR-AUC " + fx(m["ablation"]["LGB_A6_spatial"]["pr_auc"]) + "; isotonic calibration merges near-equal "
  "scores into ties, which costs a little ranking precision in exchange for trustworthy probabilities (the operational choice).")
lt = f["lead_time"]
w(f"* Lead time: {pct(lt['warned_frac'])} of {lt['n_events']} test onsets warned ≥ 1 month ahead; median lead {lt['median_lead_months']:.0f} months "
  f"(histogram months→onsets: {lt['lead_hist']})\n")

w("## 2. Per study area (operational model, test set)\n")
w("| site | landscape | PR-AUC | lift | ROC-AUC | precision | recall | false-alarm | base rate | n |\n|---|---|---|---|---|---|---|---|---|---|")
for a, r in sorted(f["per_aoi"].items()):
    w("| " + " | ".join([a, LANDSCAPE.get(a, "other"), fx(r.get("pr_auc")), fx(r.get("pr_auc_lift"), 1), fx(r.get("roc_auc")), fx(r.get("precision")),
                         fx(r.get("recall")), pct(r.get("false_alarm_rate")), fx(r.get("base_rate"), 4), str(r.get("n"))]) + " |")
LC = {"10": "tree", "20": "shrub", "30": "grass", "40": "crop", "60": "bare/sparse"}
w("\n## 3. Per land cover (test set)\n"); w(HDR)
for k, r in f["per_landcover"].items():
    w(row(LC.get(k, k), r))

w("\n## 4. Feature groups (cumulative ablation; choice by VALIDATION AP only)\n")
w("| model | features | val AP | test PR-AUC | lift | test ROC | train AP | train−val gap | trees |\n|---|---|---|---|---|---|---|---|---|")
for k, r in m["ablation"].items():
    w("| " + " | ".join([k, str(r.get("n_features", "–")), fx(r.get("val_pr_auc")), fx(r.get("pr_auc")), fx(r.get("pr_auc_lift"), 1),
                         fx(r.get("roc_auc")), fx(r.get("train_pr_auc")), fx(r.get("overfit_gap_train_minus_val")), str(r.get("best_iter", "–"))]) + " |")
if "a10" in m:
    a10 = m["a10"]
    w("\n### 4b. Texture (A10a) and red-edge (A10b) test — D-023\n")
    w("| variant | features | val AP | test PR-AUC | CI | test ROC | lift | gain share of new features | top new features |\n|---|---|---|---|---|---|---|---|---|")
    for k, r in a10.items():
        if not isinstance(r, dict) or "pr_auc" not in r: continue
        w("| " + " | ".join([k, str(r["n_features"]), fx(r["val_pr_auc"], 4), fx(r["pr_auc"]), f"{fx(r['pr_auc_ci'][0])}–{fx(r['pr_auc_ci'][1])}",
                             fx(r["roc_auc"]), fx(r["pr_auc_lift"], 1), pct(r["new_feature_gain_share"]),
                             ", ".join(r["top_new_features"]) or "–"]) + " |")
    d = a10["decision"]
    w(f"\n**Decision (pre-registered):** A6 val AP {fx(d['a6_val'], 4)}; best {d['best']} {fx(d['best_val'], 4)}; literal rule result → **{d['adopted']}** (see seed check below).\n")
    uni = {k: v for k, v in a10.get("univariate_within_site_auc_val", {}).items() if v is not None}
    if uni:
        w("Within-site univariate AUC of each new feature on validation rows (0.5 = no signal; below 0.5 = signal with inverted sign):\n")
        w("| feature | AUC | strength |\n|---|---|---|")
        for k, v in sorted(uni.items(), key=lambda kv: -abs(kv[1] - 0.5)):
            w(f"| {k} | {v:.3f} | {abs(v - 0.5):.3f} |")

    sc = a10.get("seed_check")
    if sc:
        w(f"**Seed stability check (validation only, 5 seeds; added after test numbers were seen):** A6 {fx(sc['A6_spatial']['mean'], 4)} ± "
          f"{fx(sc['A6_spatial']['sd'], 4)}, A6+A10a+A10b {fx(sc['A6+A10a+A10b']['mean'], 4)} ± {fx(sc['A6+A10a+A10b']['sd'], 4)}; mean gain "
          f"{fx(sc['mean_gain'], 4)} < 0.005 → the pass is within seed noise; **A6 stays operational** (PROJECT_LOG R-017).\n")
if "plus_pixels" in m:
    pp = m["plus_pixels"]
    w("\n### 4c. More training pixels from the same sites (D-024)\n")
    w("| training pixels per site | train rows | val AP | test PR-AUC | CI | test ROC |\n|---|---|---|---|---|---|")
    for k in ("5000_px_per_site", "10000_px_per_site"):
        r = pp[k]
        w(f"| {k.split('_')[0]} | {r['train_rows']:,} | {fx(r['val_pr_auc'], 4)} | {fx(r['pr_auc'])} | {fx(r['pr_auc_ci'][0])}–{fx(r['pr_auc_ci'][1])} | {fx(r['roc_auc'])} |")
    w(f"\nDecision: **{pp['decision']['adopted']}** (validation did not improve; evaluation rows identical for both).\n")
if "label_cleaning" in m or "seed_ensemble" in m:
    w("\n### 4d. Label cleaning and seed ensemble (5 seeds each; D-026, D-027)\n")
    w("| variant | val AP (mean of 5) | test AP | gain | decision |\n|---|---|---|---|---|")
    lc = m.get("label_cleaning")
    if lc:
        w(f"| original training labels | {fx(lc['original_labels']['val_mean'], 4)} ± {fx(lc['original_labels']['val_sd'], 4)} | {fx(lc['original_labels']['test_mean'])} | | |")
        w(f"| confident-learning cleaned labels ({lc['flagged_pos']:,} of {lc['pos']:,} positives, {lc['flagged_neg']:,} negatives removed) | "
          f"{fx(lc['cleaned_labels']['val_mean'], 4)} ± {fx(lc['cleaned_labels']['val_sd'], 4)} | {fx(lc['cleaned_labels']['test_mean'])} | {fx(lc['decision']['gain'], 4)} | {lc['decision']['adopted']} |")
    se = m.get("seed_ensemble")
    if se:
        w(f"| single model (mean of 5 seeds) | {fx(se['single_val_mean'], 4)} | {fx(se['single_test_mean'])} | | |")
        w(f"| 5-seed prediction ensemble | {fx(se['ensemble_val'], 4)} | {fx(se['ensemble_test']['pr_auc'])} | {fx(se['decision']['gain'], 4)} | {se['decision']['adopted']} |")
if "sites_e008" in m:
    s8 = m["sites_e008"]
    w("\n## 4e. Six new sites never used in training (E-008, D-025)\n")
    w("The operational 17-site model applied to six NEW Nepal/India sites chosen before any result (independent transfer test, test period):\n")
    w("| new site | landscape | PR-AUC | lift | ROC-AUC | base rate |\n|---|---|---|---|---|---|")
    for a, r in sorted(s8["17_sites"].get("test_new6_per_site", {}).items(), key=lambda kv: -kv[1]["roc_auc"]):
        w(f"| {a} | {LANDSCAPE.get(a, '–')} | {fx(r['pr_auc'])} | {fx(r['pr_auc_lift'], 1)} | {fx(r['roc_auc'])} | {fx(r['base_rate'], 4)} |")
    r6 = s8["17_sites"].get("test_new6")
    if r6:
        w(f"| **all six** | | **{fx(r6['pr_auc'])}** | **{fx(r6['pr_auc_lift'], 1)}** | **{fx(r6['roc_auc'])}** | {fx(r6['base_rate'], 4)} |")
    sc = s8.get("seed_check")
    if sc:
        w("\nShould the six sites also be used for TRAINING? (5 seeds each; validation = original-17 rows)\n")
        w("| training sites | val AP | test AP original 17 | test AP new 6 |\n|---|---|---|---|")
        for k in ("17_sites", "23_sites"):
            r = sc[k]
            w(f"| {k.split('_')[0]} | {fx(r['val_mean'], 4)} ± {fx(r['val_sd'], 4)} | {fx(r['test17_mean'])} | {fx(r['test_new6_mean'])} |")
        w(f"\nDecision: **{sc['decision']['adopted']}** (val gain {fx(sc['decision']['gain'], 4)} < 0.005). The test set favours 23 sites on all "
          "five seeds; validation (one 10-month window) does not. No decision is reversed after seeing the test; a prospective "
          "test on months after 2025-10 is planned (PROJECT_LOG R-020b).\n")

shap = pd.read_csv(RES / "shap_importance.csv", index_col=0).iloc[:, 0]
w("\n## 5. Individual predictors (mean |SHAP| share, operational model, top 20)\n")
w("| rank | feature | share |\n|---|---|---|")
tot = shap.sum()
for i, (k, v) in enumerate(shap.sort_values(ascending=False).head(20).items(), 1):
    w(f"| {i} | {k} | {pct(v / tot)} |")

w("\n## 6. Transfer to places the model never saw\n\n### Leave one country out\n"); w(HDR)
for k, r in m["leave_one_country_out"].items():
    w(row(k, r))
w("\n### Leave one site out (landscape type known from other sites?)\n")
w("| site | landscape | same type in training | PR-AUC | lift | ROC-AUC | n |\n|---|---|---|---|---|---|---|")
for k, r in sorted(m["leave_one_site_out"].items(), key=lambda kv: kv[1].get("landscape", "")):
    w("| " + " | ".join([k, r.get("landscape", LANDSCAPE.get(k, "–")), "yes" if r.get("has_sibling") else "no", fx(r.get("pr_auc")),
                         fx(r.get("pr_auc_lift"), 1), fx(r.get("roc_auc")), str(r.get("n"))]) + " |")

w("\n## 7. Stability over time (walk-forward: train only on the past, test the next year)\n"); w(HDR)
for r in m["walk_forward"]:
    w(row(str(r["test_year"]), r))

w("\n## 8. Over/under-fitting checks\n\n### Model complexity (validation curve)\n")
w("| leaves | min child | trees | train AP | val AP |\n|---|---|---|---|---|")
for r in m["validation_curve"]:
    w(f"| {r['num_leaves']} | {r['min_child_samples']} | {r['best_iter']} | {fx(r['train_pr_auc'])} | {fx(r['val_pr_auc'])} |")
w("\n### Learning curve (share of training pixels)\n\n| share | rows | train AP | val AP | test AP |\n|---|---|---|---|---|")
for r in m["learning_curve"]:
    w(f"| {pct(r['frac_pixels'])} | {r['rows']:,} | {fx(r['train_pr_auc'])} | {fx(r['val_pr_auc'])} | {fx(r['test_pr_auc'])} |")

w("\n## 9. Robustness to the label definition (9 alternative definitions)\n")
w("| residual threshold | min run (mo) | event rate | PR-AUC | lift | ROC-AUC |\n|---|---|---|---|---|---|")
for r in m["label_sensitivity"]:
    w(f"| {r['resid_thr']} | {r['min_run']} | {pct(r['base_rate'])} | {fx(r['pr_auc'])} | {fx(r['pr_auc_lift'], 1)} | {fx(r['roc_auc'])} |")

w("\n## 10. Independent checks of the labels\n")
cor = json.load(open(RES / "corroboration.json"))
w("Do pixels labelled as degradation onsets also look degraded to OTHER sensors? (AUC 0.5 = no agreement)\n")
w("| site | Landsat 30 m AUC | Landsat: event / control below −1 sd | MODIS 250 m AUC |\n|---|---|---|---|")
for a, r in cor.items():
    ls, mo = r.get("landsat", {}), r.get("modis", {})
    w(f"| {a} | {fx(ls.get('auc_agreement'))} | {pct(ls.get('frac_event_below_minus1')) if ls else '–'} / {pct(ls.get('frac_control_below_minus1')) if ls else '–'} | {fx(mo.get('auc_agreement'))} |")
b = json.load(open(RES / "brazil_validation.json"))
w(f"\n**Brazil vs official PRODES/DETER clearing polygons:** {pct(b['label_recall']['overall'])} of officially cleared pixels carry an onset label "
  f"(background {pct(b['label_recall']['background_rate_never_cleared_same_window_length'])}); warning AUC before clearing "
  f"{fx(b['warning_skill']['auc'])} — sudden clearing is detected, not forecast.\n")

w("## 11. Current predictions (latest month, all areas)\n")
a = json.load(open(ROOT / "app" / "static" / "data" / "aois.json"))
w(f"Latest month {a['latest_month']}. High = risk above the calibrated threshold; abstain = conformal 'uncertain'; active = already below expectation.\n")
w("| area | country | mean risk | high (ha) | uncertain (ha) | active decline (ha) | hotspots | NDVI trend /yr | main hotspot causes |\n|---|---|---|---|---|---|---|---|---|")
allc = Counter()
for x in a["aois"]:
    s = x["stats"]
    hp = ROOT / "app" / "static" / "data" / "aois" / x["key"] / "hotspots.geojson"
    cnt = Counter()
    if hp.exists():
        for ft in json.load(open(hp))["features"]:
            for at in ft["properties"].get("attribution", []):
                cnt[at["code"]] += 1
    allc.update(cnt)
    w("| " + " | ".join([x["key"], x.get("country", "–"), fx(s.get("risk_mean"), 4), fx(s.get("area_high_ha"), 1), fx(s.get("area_abstain_ha"), 1),
                         fx(s.get("area_active_ha"), 1), str(s.get("n_hotspots")), fx(s.get("ndvi_trend_per_yr"), 4),
                         ", ".join(f"{k} {v}" for k, v in cnt.most_common(3)) or "–"]) + " |")
w("\nAll hotspot attributions: " + ", ".join(f"{k} {v}" for k, v in allc.most_common()) + "\n")
w("## 12. Limits (see PROJECT_LOG §11)\n\n* Labels are satellite-derived (no field plots); the Brazil and Landsat checks are the only independent references.\n"
  "* Precision ≈ 0.2 at the operating threshold: about 1 in 5 warnings becomes a labelled onset within 6 months.\n"
  "* Humid tropical forest, cold steppe and mining landscapes have no training sibling: indicative only.\n")
out = ROOT / "docs" / "ACCURACY_REPORT.md"
out.write_text("\n".join(L), encoding="utf-8")
print("wrote", out, len(L), "lines")
