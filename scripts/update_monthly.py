"""Operational monthly update = "continuous training" with a champion/challenger gate.

  CAREEW_S2_END=2026-10 python scripts/update_monthly.py

1. ingest the new month(s) of Sentinel-2 (existing monthly parts are reused), refresh ERA5 climate
2. rebuild cubes / features / labels (labels for the newest 9 months stay undefined - by design)
3. train a CHALLENGER on every labelled month (expanding window, same hyper-parameters, early stopping
   on the most recent labelled 9 months of validation blocks)
4. compare challenger vs CHAMPION on the most recent labelled 6 months of TEST blocks (never trained on);
   promote only if PR-AUC does not drop by > 0.01 and ECE does not rise by > 0.01 (no silent regressions)
5. predict wall-to-wall with the champion and export the app data
Every run appends a JSON line to outputs/results/update_history.jsonl.
"""
import json, os, shutil, sys, time
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from care_ew.config import AOIS, RAW, MODELS, OUT, LABEL
from care_ew import s2, climate, dataset, train, predict, export

RES = OUT / "results"


def main():
    end = os.environ.get("CAREEW_S2_END")
    print("updating to", end)
    for a in AOIS:
        s2.build(a.key)
        (RAW / f"era5_{a.key}.csv").unlink(missing_ok=True)
        climate.build(a.key)
        dataset.build_aoi(a.key)
    df = train.load_all()
    last_lab = df.time.max()
    recent = df[(df.time > last_lab - pd.DateOffset(months=6)) & (df.space == "test")]
    es = df[(df.time > last_lab - pd.DateOffset(months=15)) & (df.time <= last_lab - pd.DateOffset(months=6)) & (df.space == "val")]
    tr = df[(df.time <= last_lab - pd.DateOffset(months=15 + LABEL.horizon + LABEL.min_run)) & (df.space == "train")]
    cols = train.feature_set(df, "A6_spatial")
    ch, _ = train.fit_lgb(tr, es, cols)
    import lightgbm as lgb
    champ = lgb.Booster(model_file=str(MODELS / "careew_lgbm.txt"))
    m_ch = train.metrics(recent.y, ch.predict(recent[cols], num_iteration=ch.best_iteration))
    m_cp = train.metrics(recent.y, champ.predict(recent[cols]))
    promote = (m_ch.get("pr_auc", 0) >= m_cp.get("pr_auc", 0) - 0.01) and (m_ch.get("ece", 1) <= m_cp.get("ece", 1) + 0.01)
    if promote:
        shutil.copy(MODELS / "careew_lgbm.txt", MODELS / f"careew_lgbm_retired_{time.strftime('%Y%m%d')}.txt")
        ch.save_model(str(MODELS / "careew_lgbm.txt"), num_iteration=ch.best_iteration)
        cal = df[(df.time > last_lab - pd.DateOffset(months=15)) & (df.time <= last_lab - pd.DateOffset(months=6)) & (df.space == "train")]
        cm = train.Calibrated(ch, cols).fit_calibration(cal)
        import pickle
        thr = train.best_f1_threshold(cal.y.values, cm.proba(cal))
        pickle.dump(dict(iso=cm.iso, q=cm.q, alpha=cm.alpha, cols=cols, thr=thr), open(MODELS / "calibration.pkl", "wb"))
    rec = dict(time=time.strftime("%Y-%m-%d %H:%M"), s2_end=end, last_labelled=str(last_lab.date()), train_rows=int(len(tr)),
               challenger=m_ch, champion=m_cp, promoted=bool(promote))
    with open(RES / "update_history.jsonl", "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(json.dumps(rec, indent=1, default=str))
    for a in AOIS:
        predict.predict_aoi(a.key)
    export.main()


if __name__ == "__main__":
    main()
