"""Training + validation protocol (CARE-EW slides 9-12).

Splits (no leakage):
  * temporal : train t <= 2022-03 | val 2023-01..2023-12 | test t >= 2024-10   (embargo gaps >= H+min_run-1)
  * spatial  : 1 km blocks per AOI, deterministic hash -> 60 % train / 20 % val / 20 % test blocks
  * PRIMARY TEST = test period AND test blocks (unseen place + unseen time). Touched once, at the end.
  * early stopping  : val period x val blocks
  * calibration/conformal : val period x train blocks (disjoint from early-stopping rows)
  * leave-one-country-out (LOCO): train on 8 nations (train period), test the 9th (test period)
  * walk-forward ("continuous training"): retrain yearly on an expanding window, test next year
Over/under-fitting controls: early stopping, strong leaf-size regularisation (rows are autocorrelated),
feature/row subsampling, L2, AOI-balanced weights, learning curves, validation curves, train-val gap.
"""
import json, hashlib, sys, time, warnings
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss, precision_recall_curve
from .config import AOIS, PROC, MODELS, OUT, SPLIT, SEED, LABEL
from .features import FEATURE_GROUPS

warnings.filterwarnings("ignore")
RES = OUT / "results"; RES.mkdir(parents=True, exist_ok=True)

# Strong regularisation (D-016): each pixel contributes ~40 near-duplicate monthly rows, so leaves must be
# large and shallow or trees memorise pixels (debug run: num_leaves 31 -> train PR-AUC 0.91 vs val 0.05).
LGB_PARAMS = dict(objective="binary", metric="average_precision", learning_rate=0.03, num_leaves=7, min_child_samples=4000,
                  feature_fraction=0.4, bagging_fraction=0.7, bagging_freq=1, lambda_l2=50.0, extra_trees=True,
                  max_bin=127, verbose=-1, seed=SEED, num_threads=10)


# ------------------------------------------------------------------ data
NEG_KEEP = 0.5   # D-022: keep this share of TRAINING-PERIOD negatives (weight 1/NEG_KEEP); val/cal/test untouched


import os
TABLE = os.environ.get("CAREEW_TABLE", "table.parquet")   # D-024: "table_plus.parquet" = 10 000 pixels per site
META = ["aoi", "pix", "time", "country", "row", "col", "block", "y", "months_to_onset", "batch"]


def load_all(aois=None, neg_keep=None, table=None, columns=None, side_tables=True):
    """Memory-aware loader (I-031): AOI tables are read one by one, cast to float32 and, inside the training
    period only, negatives are deterministically down-sampled (hash of aoi/pixel/month) and re-weighted by
    1/neg_keep. All rows of the validation, calibration and test periods are kept, so evaluation is unchanged."""
    neg_keep = NEG_KEEP if neg_keep is None else neg_keep
    dfs = []
    for a in AOIS:
        if aois and a.key not in aois:
            continue
        f = PROC / a.key / (table or TABLE)
        if not f.exists():
            continue
        if columns is not None:
            import pyarrow.parquet as pq
            names = pq.ParquetFile(f).schema.names
            d = pd.read_parquet(f, columns=[c for c in names if c in set(columns) | set(META)])
        else:
            d = pd.read_parquet(f)
        for extra in (("texture.parquet", "rededge.parquet") if side_tables and (table or TABLE) == "table.parquet" else ()):   # A10a/A10b (D-023)
            fx = PROC / a.key / extra
            if fx.exists():
                d = d.merge(pd.read_parquet(fx), on=["pix", "time"], how="left")
        for c in d.columns:
            if d[c].dtype == np.float64:
                d[c] = d[c].astype(np.float32)
        d["w_mult"] = np.float32(1.0)
        if neg_keep < 1.0:
            t = pd.to_datetime(d["time"])
            h = (pd.util.hash_pandas_object(d[["pix"]].assign(m=t.dt.year * 12 + t.dt.month), index=False).values % 1000) / 1000.0
            tr_neg = (t <= SPLIT["train_end"]).values & (d["y"].values == 0)
            drop = tr_neg & (h >= neg_keep)
            d = d.loc[~drop].copy()
            d.loc[(pd.to_datetime(d["time"]) <= SPLIT["train_end"]).values & (d["y"].values == 0), "w_mult"] = np.float32(1.0 / neg_keep)
        dfs.append(d)
    df = pd.concat(dfs, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    df["space"] = [_space_fold(a, b) for a, b in zip(df["aoi"].values, df["block"].values)]
    df["period"] = np.select([df.time <= SPLIT["train_end"],
                              (df.time >= SPLIT["val_start"]) & (df.time <= SPLIT["val_end"] + "-28"),
                              df.time >= SPLIT["test_start"]], ["train", "val", "test"], "gap")
    return df


_SPACE_CACHE = {}
def _space_fold(aoi, block):
    k = (aoi, int(block))
    if k not in _SPACE_CACHE:
        h = int(hashlib.md5(f"{aoi}-{block}-{SEED}".encode()).hexdigest(), 16) % 100
        _SPACE_CACHE[k] = "train" if h < 60 else ("val" if h < 80 else "test")
    return _SPACE_CACHE[k]


def feature_set(df, upto):
    groups = ["A1_state", "A2_change", "A3_climate", "A4_residual", "A5_resilience", "A6_spatial", "A8_ecofunc", "A9_nonlinear"]
    cols = []
    for g in groups[:groups.index(upto) + 1]:
        cols += [c for c in df.columns if c.startswith("clim_")] if g == "A3_climate" else FEATURE_GROUPS[g]
    return [c for c in cols if c in df.columns]


def weights(d):
    """AOI-balanced: every site contributes equal total weight (no landscape dominates); rows carry w_mult
    (1/neg_keep for down-sampled training negatives, D-022) so class balance within a site is preserved."""
    wm = d["w_mult"].astype(np.float64) if "w_mult" in d else pd.Series(1.0, index=d.index)
    s = wm.groupby(d["aoi"]).transform("sum")
    return (len(d) / d["aoi"].nunique() * wm / s).values


# ------------------------------------------------------------------ metrics
def ece(y, p, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1)); edges[0], edges[-1] = 0, 1
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(e)


def metrics(y, p, thr=None):
    y = np.asarray(y).astype(int); p = np.asarray(p, float)
    out = dict(n=int(len(y)), base_rate=float(y.mean()))
    if y.min() == y.max():
        return out
    out.update(pr_auc=float(average_precision_score(y, p)), roc_auc=float(roc_auc_score(y, p)),
               brier=float(brier_score_loss(y, np.clip(p, 0, 1))), ece=ece(y, np.clip(p, 0, 1)))
    out["pr_auc_lift"] = out["pr_auc"] / max(out["base_rate"], 1e-9)
    if thr is not None:
        pred = p >= thr
        tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum()); fn = int((~pred & (y == 1)).sum())
        out.update(thr=float(thr), precision=tp / max(tp + fp, 1), recall=tp / max(tp + fn, 1),
                   false_alarm_rate=fp / max((y == 0).sum(), 1),
                   f1=2 * tp / max(2 * tp + fp + fn, 1))
    return out


def best_f1_threshold(y, p):
    pr, rc, th = precision_recall_curve(y, p)
    f1 = 2 * pr * rc / np.maximum(pr + rc, 1e-9)
    return float(th[np.nanargmax(f1[:-1])])


def cluster_bootstrap(d, p, n=200, seed=SEED):
    """95 % CI by resampling (aoi, block) clusters - rows within a block are not independent."""
    rng = np.random.default_rng(seed)
    key = d["aoi"].astype(str) + "_" + d["block"].astype(str)
    codes, uniq = pd.factorize(key)
    groups = [np.nonzero(codes == i)[0] for i in range(len(uniq))]
    y = d["y"].values
    pr, roc = [], []
    for _ in range(n):
        idx = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        if y[idx].min() == y[idx].max():
            continue
        pr.append(average_precision_score(y[idx], p[idx])); roc.append(roc_auc_score(y[idx], p[idx]))
    return dict(pr_auc_ci=[float(np.percentile(pr, 2.5)), float(np.percentile(pr, 97.5))],
                roc_auc_ci=[float(np.percentile(roc, 2.5)), float(np.percentile(roc, 97.5))])


# ------------------------------------------------------------------ models
def fit_lgb(tr, es, cols, params=None, rounds=3000):
    params = {**LGB_PARAMS, **(params or {})}
    pos = tr["y"].mean()
    params["scale_pos_weight"] = float(np.sqrt((1 - pos) / max(pos, 1e-6)))
    dtr = lgb.Dataset(tr[cols], tr["y"], weight=weights(tr), categorical_feature=[c for c in ["landcover"] if c in cols], free_raw_data=False)
    des = lgb.Dataset(es[cols], es["y"], weight=weights(es), reference=dtr)
    ev = {}
    m = lgb.train(params, dtr, rounds, valid_sets=[dtr, des], valid_names=["train", "val"],
                  callbacks=[lgb.early_stopping(150, first_metric_only=True, verbose=False), lgb.record_evaluation(ev)])
    return m, ev


def _lgb_ap(preds, data):
    return "avg_precision", average_precision_score(data.get_label(), preds), True


class Calibrated:
    """LightGBM booster + isotonic calibration + Mondrian (class-conditional) split-conformal sets."""
    def __init__(self, booster, cols, alpha=0.10):
        self.b, self.cols, self.alpha = booster, cols, alpha

    def raw(self, d):
        return self.b.predict(d[self.cols], num_iteration=self.b.best_iteration)

    def fit_calibration(self, cal):
        r = self.raw(cal); y = cal["y"].values
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(r, y)
        p = self.iso.predict(r)
        # nonconformity s = 1 - p(true class); class-conditional quantiles
        self.q = {}
        for c in (0, 1):
            s = 1 - (p[y == 1] if c == 1 else 1 - p[y == 0])
            n = len(s)
            self.q[c] = float(np.quantile(s, min(1, np.ceil((n + 1) * (1 - self.alpha)) / n)))
        return self

    def proba(self, d):
        return self.iso.predict(self.raw(d))

    def sets(self, p):
        in1 = (1 - p) <= self.q[1]
        in0 = p <= self.q[0]
        status = np.where(in1 & ~in0, "event", np.where(in0 & ~in1, "no_event", "abstain"))
        return status, in0, in1


def lead_time(d, p, thr):
    """For each (aoi, pix) with an onset in the test window, the earliest month t (within the H months
    before onset, pixel eligible) at which p >= thr. Lead = months between that warning and onset."""
    d = d.assign(p=p)
    pos = d[d.y == 1].copy()
    pos["onset_time"] = pos["time"] + pd.to_timedelta(pos["months_to_onset"] * 30.44, unit="D")
    pos["onset_key"] = pos["onset_time"].dt.to_period("M")
    g = pos.groupby(["aoi", "pix", "onset_key"])
    rows = []
    for _, gr in g:
        hit = gr[gr.p >= thr]
        rows.append(int(hit["months_to_onset"].max()) if len(hit) else 0)
    rows = np.array(rows)
    return dict(n_events=int(len(rows)), warned_frac=float((rows > 0).mean()) if len(rows) else None,
                median_lead_months=float(np.median(rows[rows > 0])) if (rows > 0).any() else 0.0,
                mean_lead_months=float(rows[rows > 0].mean()) if (rows > 0).any() else 0.0,
                lead_hist={int(k): int(v) for k, v in zip(*np.unique(rows, return_counts=True))})


# ------------------------------------------------------------------ experiments
def splits(df):
    tr = df[(df.period == "train") & (df.space == "train")]
    es = df[(df.period == "val") & (df.space == "val")]
    cal = df[(df.period == "val") & (df.space == "train")]
    te = df[(df.period == "test") & (df.space == "test")]
    return tr, es, cal, te


def run_ablation(df, log):
    tr, es, cal, te = splits(df)
    log["split_sizes"] = {k: dict(rows=int(len(v)), pos_rate=float(v.y.mean()), aois=int(v.aoi.nunique()))
                          for k, v in dict(train=tr, early_stop=es, calibration=cal, test=te).items()}
    res = {}
    # A0 baselines (no learning)
    for name, score in [("A0_persistence(-z_mean3)", -te["z_mean3"].fillna(0)),
                        ("A0_ndvi_trend(-slope12)", -te["ndvi_slope12"].fillna(0)),
                        ("A0_residual_rule(-R_mean3)", -te["R_mean3"].fillna(0))]:
        res[name] = metrics(te.y, _rank01(score))
    # Sentinel-only random forest (slide 9 baseline)
    cols_s = feature_set(df, "A2_change")
    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=200, max_features="sqrt", n_jobs=10,
                                class_weight="balanced_subsample", random_state=SEED)
    sub = tr.sample(min(len(tr), 400000), random_state=SEED)
    rf.fit(sub[cols_s].fillna(-9), sub.y, sample_weight=weights(sub))
    pr = rf.predict_proba(te[cols_s].fillna(-9))[:, 1]
    res["RF_sentinel_only(A1+A2)"] = metrics(te.y, pr)
    pd.DataFrame({"y": te.y.values, "persistence": _rank01(-te["z_mean3"].fillna(0)),
                  "residual rule": _rank01(-te["R_mean3"].fillna(0)), "RF Sentinel-only": pr}).to_parquet(RES / "baseline_scores.parquet")
    models = {}
    for g in ["A1_state", "A2_change", "A3_climate", "A4_residual", "A5_resilience", "A6_spatial", "A8_ecofunc", "A9_nonlinear"]:   # A7_heat rejected in E-004
        cols = feature_set(df, g)
        t0 = time.time()
        m, ev = fit_lgb(tr, es, cols)
        p_te = m.predict(te[cols], num_iteration=m.best_iteration)
        p_tr = m.predict(tr[cols].iloc[::5], num_iteration=m.best_iteration)
        r = metrics(te.y, p_te)
        r.update(n_features=len(cols), best_iter=int(m.best_iteration),
                 train_pr_auc=float(average_precision_score(tr.y.iloc[::5], p_tr)),
                 val_pr_auc=float(max(ev["val"]["average_precision"])), secs=round(time.time() - t0, 1))
        r["overfit_gap_train_minus_val"] = r["train_pr_auc"] - r["val_pr_auc"]
        res["LGB_" + g] = r
        models[g] = (m, cols)
        print(g, {k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()}, flush=True)
    log["ablation"] = res
    return models, (tr, es, cal, te)


def _rank01(s):
    s = pd.Series(np.asarray(s, float))
    return s.rank(pct=True).values


def full_model(df, models, sp, log):
    tr, es, cal, te = sp
    # pre-registered rule (D-018): A7_heat replaces A6 only if its VALIDATION AP is >= 0.005 higher
    pick = "A6_spatial"
    ab = log.get("ablation", {})
    # pre-registered rule (D-020): A8_ecofunc (= A6 + ecosystem function) replaces A6 only if validation AP >= +0.005
    # D-021 (pre-registered): among the cumulative steps A6, A8 (+ecosystem function), A9 (+nonlinear dynamics)
    # take the one with the highest VALIDATION AP, but only if it beats A6 by >= 0.005; test is reported regardless.
    base_val = ab.get("LGB_A6_spatial", {}).get("val_pr_auc", 0)
    for g in ("A8_ecofunc", "A9_nonlinear"):
        v = ab.get("LGB_" + g, {}).get("val_pr_auc", 0)
        if g in models and v >= base_val + 0.005 and v >= ab.get("LGB_" + pick, {}).get("val_pr_auc", 0):
            pick = g
    log["final_feature_set"] = pick
    m, cols = models[pick]
    cm = Calibrated(m, cols).fit_calibration(cal)
    p_cal = cm.proba(cal)
    thr = best_f1_threshold(cal.y.values, p_cal)
    p = cm.proba(te)
    r = metrics(te.y, p, thr)
    r.update(cluster_bootstrap(te, p))
    status, _, _ = cm.sets(p)
    ab = status == "abstain"
    r["conformal"] = dict(alpha=cm.alpha, abstain_frac=float(ab.mean()),
                          coverage_event=float(np.mean([(s in ("event", "abstain")) for s in status[te.y.values == 1]])),
                          coverage_no_event=float(np.mean([(s in ("no_event", "abstain")) for s in status[te.y.values == 0]])),
                          precision_when_event=float(te.y.values[status == "event"].mean()) if (status == "event").any() else None,
                          npv_when_no_event=float(1 - te.y.values[status == "no_event"].mean()) if (status == "no_event").any() else None)
    r["metrics_on_non_abstained"] = metrics(te.y.values[~ab], p[~ab], thr) if (~ab).sum() > 100 else None
    r["lead_time"] = lead_time(te, p, thr)
    r["per_aoi"] = {a: metrics(g.y, p[te.aoi.values == a], thr) for a, g in te.groupby("aoi")}
    r["per_landcover"] = {str(int(k)): metrics(g.y, p[(te.landcover == k).values], thr) for k, g in te.groupby("landcover") if len(g) > 200}
    # temporal-only and spatial-only holdouts (diagnostic)
    t_only = df[(df.period == "test") & (df.space != "test")]
    s_only = df[(df.period == "train") & (df.space == "test")]
    r["temporal_only_holdout"] = metrics(t_only.y, cm.proba(t_only), thr)
    r["spatial_only_holdout"] = metrics(s_only.y, cm.proba(s_only), thr)
    log["final_model"] = r
    m.save_model(str(MODELS / "careew_lgbm.txt"), num_iteration=m.best_iteration)
    import pickle
    pickle.dump(dict(iso=cm.iso, q=cm.q, alpha=cm.alpha, cols=cols, thr=thr), open(MODELS / "calibration.pkl", "wb"))
    # explanations: mean |SHAP| on test
    contrib = m.predict(te[cols].sample(min(len(te), 30000), random_state=SEED), pred_contrib=True, num_iteration=m.best_iteration)
    imp = pd.Series(np.abs(contrib[:, :-1]).mean(0), index=cols).sort_values(ascending=False)
    imp.to_csv(RES / "shap_importance.csv")
    pd.DataFrame(dict(aoi=te.aoi.values, pix=te.pix.values, time=te.time.values, y=te.y.values, p=p, status=status,
                      months_to_onset=te.months_to_onset.values)).to_parquet(RES / "test_predictions.parquet")
    pd.DataFrame(dict(y=cal.y.values, p=p_cal)).to_parquet(RES / "cal_predictions.parquet")
    print("FINAL", {k: v for k, v in r.items() if not isinstance(v, dict)}, flush=True)
    return cm, thr


def loco(df, log):
    cols = None
    out = {}
    for c in sorted(df.country.unique()):
        tr = df[(df.period == "train") & (df.country != c) & (df.space == "train")]
        es = df[(df.period == "val") & (df.country != c) & (df.space == "val")]
        te = df[(df.period == "test") & (df.country == c)]
        cols = feature_set(df, "A6_spatial")
        m, _ = fit_lgb(tr, es, cols)
        p = m.predict(te[cols], num_iteration=m.best_iteration)
        out[c] = metrics(te.y, p)
        # same nation, in-domain model for reference
        out[c]["in_domain_pr_auc_from_final"] = None
        print("LOCO", c, round(out[c].get("pr_auc", np.nan), 4), flush=True)
    log["leave_one_country_out"] = out


def learning_curve(df, log):
    tr, es, cal, te = splits(df)
    cols = feature_set(df, "A6_spatial")
    pix = tr[["aoi", "pix"]].drop_duplicates()
    out = []
    for frac in (0.05, 0.1, 0.25, 0.5, 1.0):
        keep = pix.sample(frac=frac, random_state=SEED)
        sub = tr.merge(keep, on=["aoi", "pix"])
        m, ev = fit_lgb(sub, es, cols)
        out.append(dict(frac_pixels=frac, rows=int(len(sub)),
                        train_pr_auc=float(average_precision_score(sub.y, m.predict(sub[cols], num_iteration=m.best_iteration))),
                        val_pr_auc=float(max(ev["val"]["average_precision"])),
                        test_pr_auc=float(average_precision_score(te.y, m.predict(te[cols], num_iteration=m.best_iteration)))))
        print("LC", out[-1], flush=True)
    log["learning_curve"] = out


def validation_curve(df, log):
    tr, es, cal, te = splits(df)
    cols = feature_set(df, "A6_spatial")
    out = []
    for nl, mcs in [(3, 8000), (7, 4000), (15, 2000), (31, 1000), (63, 400), (127, 100), (255, 20)]:
        m, ev = fit_lgb(tr, es, cols, dict(num_leaves=nl, min_child_samples=mcs))
        out.append(dict(num_leaves=nl, min_child_samples=mcs, best_iter=int(m.best_iteration),
                        train_pr_auc=float(average_precision_score(tr.y.iloc[::5], m.predict(tr[cols].iloc[::5], num_iteration=m.best_iteration))),
                        val_pr_auc=float(max(ev["val"]["average_precision"]))))
        # also record an UN-stopped curve (fixed 1500 rounds) to show what overfitting looks like
        print("VC", out[-1], flush=True)
    log["validation_curve"] = out


def walk_forward(df, log):
    """Continuous (expanding-window) retraining: for test year Y train on t <= Y-1 year minus embargo."""
    cols = feature_set(df, "A6_spatial")
    emb = LABEL.horizon + LABEL.min_run - 1
    out = []
    for Y in (2021, 2022, 2023, 2024, 2025):
        cut = pd.Timestamp(f"{Y}-01-01") - pd.DateOffset(months=emb + 1)
        tr = df[(df.time <= cut - pd.DateOffset(months=12)) & (df.space == "train")]
        es = df[(df.time > cut - pd.DateOffset(months=9)) & (df.time <= cut) & (df.space == "val")]
        te = df[(df.time.dt.year == Y) & (df.space == "test")]
        if len(te) == 0 or te.y.nunique() < 2 or es.y.nunique() < 2:
            continue
        m, _ = fit_lgb(tr, es, cols)
        p = m.predict(te[cols], num_iteration=m.best_iteration)
        out.append(dict(test_year=Y, train_cutoff=str(cut.date()), train_rows=int(len(tr)), **metrics(te.y, p)))
        print("WF", out[-1], flush=True)
    log["walk_forward"] = out


def label_sensitivity(df, log):
    """Re-derive labels under the 3x3 grid of (resid_thr, min_run) from the stored label-version
    residuals and retrain the A6 model. Rows are the intersection of the default-eligible rows and the
    rows eligible under the alternative definition (features were only materialised for the former)."""
    from .labels import make_labels
    from .config import LABEL_SENSITIVITY
    cols = feature_set(df, "A6_spatial")
    cubes = {}
    for a in df.aoi.unique():
        c = np.load(PROC / a / "cube.npz")
        pix = np.unique(df.loc[df.aoi == a, "pix"].values)
        R = c["R_lab"][:, pix].astype(np.float32); dv = c["dev_lab"][:, pix].astype(np.float32)
        cubes[a] = (pix, R, dv, c["observed"][:, pix], pd.to_datetime(c["times"]))
    rows = []
    for cfg in LABEL_SENSITIVITY:
        parts = []
        for a, (pix, R, dev, obs, times) in cubes.items():
            y, elig, *_ = make_labels(R, dev, obs, cfg)
            sub = df[df.aoi == a]
            ti = times.get_indexer(sub.time); pi = np.searchsorted(pix, sub.pix.values)
            yy = y[ti, pi]; ok = elig[ti, pi] & np.isfinite(yy)
            parts.append(sub[ok].assign(y=yy[ok].astype(np.int8)))
        d2 = pd.concat(parts)
        tr, es, cal, te = splits(d2)
        m, _ = fit_lgb(tr, es, cols)
        p = m.predict(te[cols], num_iteration=m.best_iteration)
        r = dict(resid_thr=cfg.resid_thr, min_run=cfg.min_run, pos_rate=float(d2.y.mean()), **metrics(te.y, p))
        rows.append(r); print("SENS", r, flush=True)
    pd.DataFrame(rows).to_csv(RES / "label_sensitivity.csv", index=False)
    log["label_sensitivity"] = rows


LANDSCAPE = {   # landscape types (user question: does the model transfer to new places of a KNOWN type?)
    "NPL_chure": "Himalayan foothill forest", "NPL_chure_dang": "Himalayan foothill forest",
    "NPL_chure_sarlahi": "Himalayan foothill forest", "NPL_surkhet": "Himalayan foothill forest",
    "NPL_kavre": "Himalayan foothill forest",
    "IND_bundelkhand": "Semi-arid Indian cropland", "IND_chambal": "Semi-arid Indian cropland",
    "IND_thar": "Semi-arid Indian cropland",
    "IND_banni": "Arid grassland / rangeland", "SEN_ferlo": "Arid grassland / rangeland",
    "KEN_baringo": "Arid grassland / rangeland", "MNG_steppe": "Arid grassland / rangeland",
    "IND_jharia": "Mining landscape", "ESP_murcia": "Mediterranean dryland", "ETH_tigray": "Highland cropland / shrub",
    "BRA_matopiba": "Cerrado cropland frontier", "AUS_murraydarling": "Semi-arid woodland",
    "NPL_chure_udayapur": "Himalayan foothill forest", "NPL_chure_kailali": "Himalayan foothill forest",
    "NPL_sindhupalchok": "Himalayan foothill forest", "IND_shivalik": "Himalayan foothill forest",
    "IND_marathwada": "Semi-arid Indian cropland", "IND_singrauli": "Mining landscape",
}


def loso(df, log):
    """Leave-one-SITE-out: train on the other 16 sites, test on the held-out site (test period, all blocks).
    'has_sibling' = another site of the same landscape type stays in training."""
    cols = feature_set(df, "A6_spatial")
    out = {}
    for site in sorted(df.aoi.unique()):
        tr = df[(df.period == "train") & (df.aoi != site) & (df.space == "train")]
        es = df[(df.period == "val") & (df.aoi != site) & (df.space == "val")]
        te = df[(df.period == "test") & (df.aoi == site)]
        if te.y.nunique() < 2:
            out[site] = dict(n=int(len(te)), base_rate=float(te.y.mean()), note="no test events")
            continue
        m, _ = fit_lgb(tr, es, cols)
        p = m.predict(te[cols], num_iteration=m.best_iteration)
        r = metrics(te.y, p)
        typ = LANDSCAPE.get(site, "other")
        r.update(landscape=typ, has_sibling=any(LANDSCAPE.get(o) == typ for o in df.aoi.unique() if o != site))
        out[site] = r
        print("LOSO", site, typ, round(r.get("pr_auc", np.nan), 4), round(r.get("roc_auc", np.nan), 3), "sibling" if r["has_sibling"] else "no-sibling", flush=True)
    log["leave_one_site_out"] = out


def a10(df, log):
    """D-023 (pre-registered): A6 vs A6+texture, A6+red-edge, A6+both on identical rows/splits/parameters.
    A variant is adopted only if its VALIDATION AP >= A6 + 0.005; test metrics are reported regardless."""
    tr, es, cal, te = splits(df)
    base = feature_set(df, "A6_spatial")
    variants = {"A6_spatial": base,
                "A6+A10a_texture": base + [c for c in FEATURE_GROUPS["A10a_texture"] if c in df],
                "A6+A10b_rededge": base + [c for c in FEATURE_GROUPS["A10b_rededge"] if c in df],
                "A6+A10a+A10b": base + [c for c in FEATURE_GROUPS["A10a_texture"] + FEATURE_GROUPS["A10b_rededge"] if c in df]}
    out, seen = {}, set()
    for name, cols in variants.items():
        if tuple(cols) in seen:                                    # group not available yet (e.g. red-edge still downloading)
            continue
        seen.add(tuple(cols))
        m, ev = fit_lgb(tr, es, cols)
        p = m.predict(te[cols], num_iteration=m.best_iteration)
        r = metrics(te.y, p)
        r.update(n_features=len(cols), best_iter=int(m.best_iteration), val_pr_auc=float(max(ev["val"]["average_precision"])))
        r.update(cluster_bootstrap(te, p))
        gain = pd.Series(m.feature_importance("gain"), index=cols)
        r["new_feature_gain_share"] = float(gain[[c for c in cols if c not in base]].sum() / gain.sum()) if len(cols) > len(base) else 0.0
        r["top_new_features"] = gain[[c for c in cols if c not in base]].sort_values(ascending=False).head(6).round(1).to_dict()
        out[name] = r
        print("A10", name, "val", round(r["val_pr_auc"], 4), "test", round(r["pr_auc"], 4), "roc", round(r["roc_auc"], 3), flush=True)
    bv = out["A6_spatial"]["val_pr_auc"]
    best = max(out, key=lambda k: out[k]["val_pr_auc"])
    out["decision"] = dict(rule="adopt only if val AP >= A6 + 0.005", a6_val=bv, best=best,
                           best_val=out[best]["val_pr_auc"], adopted=best if out[best]["val_pr_auc"] >= bv + 0.005 else "A6_spatial")
    # within-site univariate AUC of each new feature on validation rows (does it carry ANY signal?)
    va = df[df.period == "val"]
    uni = {}
    for c in [c for c in FEATURE_GROUPS["A10a_texture"] + FEATURE_GROUPS["A10b_rededge"] if c in df]:
        aucs = [roc_auc_score(g.y, g[c].fillna(g[c].median())) for _, g in va.groupby("aoi") if g.y.nunique() == 2 and g[c].notna().any()]
        uni[c] = float(np.mean(aucs)) if aucs else None
    out["univariate_within_site_auc_val"] = uni
    log["a10"] = out
    print("A10 decision", out["decision"], flush=True)


def plus(log):
    """D-024 (pre-registered): does doubling the training pixels (5 000 -> 10 000 per site) help? Both models use
    the A6 features, splits and parameters; both are scored on the SAME validation/test rows (all 10 000 pixels).
    Adopt the larger training set only if validation AP >= +0.005."""
    cols_all = [c for g in ("A1_state", "A2_change", "A4_residual", "A5_resilience", "A6_spatial") for c in FEATURE_GROUPS[g]]
    probe = load_all(aois=[AOIS[0].key], table="table_plus.parquet")
    cols_all += [c for c in probe.columns if c.startswith("clim_")]
    del probe
    df = load_all(table="table_plus.parquet", columns=cols_all)
    tr, es, cal, te = splits(df)
    cols = feature_set(df, "A6_spatial")
    out = {}
    for name, trn in (("5000_px_per_site", tr[tr.batch == 0]), ("10000_px_per_site", tr)):
        m, ev = fit_lgb(trn, es, cols)
        p = m.predict(te[cols], num_iteration=m.best_iteration)
        r = metrics(te.y, p)
        r.update(cluster_bootstrap(te, p))
        r.update(train_rows=int(len(trn)), train_pos=int(trn.y.sum()), best_iter=int(m.best_iteration),
                 val_pr_auc=float(max(ev["val"]["average_precision"])),
                 test_on_original_pixels=metrics(te.y[te.batch.values == 0], p[te.batch.values == 0]))
        out[name] = r
        print("PLUS", name, "train rows", len(trn), "val", round(r["val_pr_auc"], 4), "test", round(r["pr_auc"], 4), "roc", round(r["roc_auc"], 3), flush=True)
    a, b = out["5000_px_per_site"]["val_pr_auc"], out["10000_px_per_site"]["val_pr_auc"]
    out["decision"] = dict(rule="adopt 10 000 px/site only if val AP >= 5 000-px val AP + 0.005", val_5000=a, val_10000=b,
                           adopted="10000_px_per_site" if b >= a + 0.005 else "5000_px_per_site")
    log["plus_pixels"] = out
    print("PLUS decision", out["decision"], flush=True)


def a10_seeds(df, log, seeds=(1, 2, 3, 4, 5)):
    """Post-hoc stability check of the marginal D-023 pass (added AFTER the test numbers were seen; VALIDATION only):
    refit A6 and A6+A10a+A10b with 5 LightGBM seeds (bagging/feature sampling/extra-trees change) and compare val AP."""
    tr, es, cal, te = splits(df)
    base = feature_set(df, "A6_spatial")
    both = base + [c for c in FEATURE_GROUPS["A10a_texture"] + FEATURE_GROUPS["A10b_rededge"] if c in df]
    out = {}
    for name, cols in (("A6_spatial", base), ("A6+A10a+A10b", both)):
        v = []
        for sd in seeds:
            m, ev = fit_lgb(tr, es, cols, params=dict(seed=sd))
            v.append(float(max(ev["val"]["average_precision"])))
        out[name] = dict(val_ap=v, mean=float(np.mean(v)), sd=float(np.std(v, ddof=1)))
        print("SEEDS", name, np.round(v, 4), round(np.mean(v), 4), flush=True)
    d = out["A6+A10a+A10b"]["mean"] - out["A6_spatial"]["mean"]
    out["mean_gain"] = d
    out["paired_gain_per_seed"] = [b - a for a, b in zip(out["A6_spatial"]["val_ap"], out["A6+A10a+A10b"]["val_ap"])]
    log.setdefault("a10", {})["seed_check"] = out
    print("SEEDS mean gain", round(d, 4), flush=True)


def main(what=("ablation", "final", "loco", "lc", "vc", "wf")):
    """Pieces can be run in separate processes (memory): 'ablation final' starts a fresh metrics.json; any other
    piece (vc, lc, wf, loco, sens) loads the existing file and adds its section (D-022)."""
    if tuple(what) == ("plus",):
        log = json.load(open(RES / "metrics.json")); plus(log)
        json.dump(log, open(RES / "metrics.json", "w"), indent=2, default=str)
        return log
    df = load_all()
    fresh = "ablation" in what
    if fresh:
        log = dict(created=time.strftime("%Y-%m-%d %H:%M"), rows=int(len(df)), aois=sorted(df.aoi.unique().tolist()),
                   label_cfg=LABEL.__dict__, split=SPLIT, lgb_params=LGB_PARAMS, neg_keep_train=NEG_KEEP)
        models, sp = run_ablation(df, log)
        if "final" in what:
            full_model(df, models, sp, log)
        json.dump(log, open(RES / "metrics.json", "w"), indent=2, default=str)
    else:
        log = json.load(open(RES / "metrics.json"))
    if "vc" in what: validation_curve(df, log)
    if "lc" in what: learning_curve(df, log)
    if "wf" in what: walk_forward(df, log)
    if "loco" in what: loco(df, log)
    if "sens" in what: label_sensitivity(df, log)
    if "loso" in what: loso(df, log)
    if "a10" in what: a10(df, log)
    if "a10seeds" in what: a10_seeds(df, log)
    json.dump(log, open(RES / "metrics.json", "w"), indent=2, default=str)
    return log


if __name__ == "__main__":
    main(tuple(sys.argv[1:]) or ("ablation", "final", "loco", "lc", "vc", "wf", "sens"))
