"""Wall-to-wall inference: calibrated risk + conformal status for every pixel and month >= MAP_START.

status codes: 0 no_event | 1 event (warning) | 2 abstain (uncertain) | 3 active (already below expectation:
an onset may be under way, the pixel is not eligible for "early" warning) | 255 no data / masked.
"""
import sys, pickle
import numpy as np, pandas as pd, lightgbm as lgb
from .config import AOIS, PROC, MODELS, OUT
from .dataset import aoi_context, features_for

MAP_START = "2023-01"
PRED = OUT / "predictions"; PRED.mkdir(parents=True, exist_ok=True)


def load_model():
    b = lgb.Booster(model_file=str(MODELS / "careew_lgbm.txt"))
    cal = pickle.load(open(MODELS / "calibration.pkl", "rb"))
    return b, cal


def predict_aoi(aoi_key, chunk=12000, ctx=None, contrib_month=None):
    b, cal = load_model()
    cols, iso, q, thr = cal["cols"], cal["iso"], cal["q"], cal["thr"]
    ctx = ctx or aoi_context(aoi_key, save_cube=False)
    times = ctx["times"]
    tm = np.nonzero(times >= pd.Timestamp(MAP_START))[0]
    N = ctx["N"]
    risk = np.full((len(tm), N), np.nan, np.float16)
    status = np.full((len(tm), N), 255, np.uint8)
    contrib_last = np.zeros((N, len(cols)), np.float16)
    ECO_KEEP = ["water_frac12", "water_loss12", "nbw_loss12", "paddy_change", "evergreen_shift", "amp_change", "peak_shift", "tex_change"]
    eco_last = np.full((N, len(ECO_KEEP)), np.nan, np.float16)   # process attribution (D-020)
    for s in range(0, N, chunk):
        idx = np.arange(s, min(N, s + chunk))
        need = set(cols) | set(ECO_KEEP)
        F, R = features_for(ctx, idx, need=need, t_from=int(tm[0]))
        X = np.stack([np.asarray(F[c], np.float32)[tm] if c in F else np.full((len(tm), len(idx)), np.nan, np.float32)
                      for c in cols], -1)                     # [Tm, n, f]
        flatX = X.reshape(-1, len(cols))
        raw = b.predict(flatX)
        p = iso.predict(raw).reshape(len(tm), len(idx))
        elig = ctx["eligible"][tm][:, idx] & np.isfinite(R[tm])
        in1 = (1 - p) <= q[1]; in0 = p <= q[0]
        st = np.where(in1 & ~in0, 1, np.where(in0 & ~in1, 0, 2)).astype(np.uint8)
        active = ~ctx["eligible"][tm][:, idx] & np.isfinite(R[tm])
        st[active] = 3
        st[~np.isfinite(R[tm])] = 255
        p[~elig] = np.nan
        risk[:, idx] = p.astype(np.float16); status[:, idx] = st
        c = b.predict(X[-1], pred_contrib=True)[:, :-1]           # explanations at the latest month
        contrib_last[idx] = c.astype(np.float16)
        for j, k in enumerate(ECO_KEEP):
            if k in F:
                eco_last[idx, j] = np.asarray(F[k], np.float32)[tm[-1]].astype(np.float16)
        print(f"[{aoi_key}] {idx[-1] + 1}/{N}", flush=True)
    np.savez_compressed(PRED / f"{aoi_key}_risk.npz", eco_last=eco_last, eco_cols=np.array(ECO_KEEP), risk=risk, status=status, months=times[tm].strftime("%Y-%m").values,
                        rr=ctx["rr"], cc=ctx["cc"], H=ctx["H"], W=ctx["W"], thr=thr, cols=np.array(cols),
                        contrib_last=contrib_last)
    return ctx


if __name__ == "__main__":
    for a in (sys.argv[1:] or [a.key for a in AOIS]):
        predict_aoi(a)
