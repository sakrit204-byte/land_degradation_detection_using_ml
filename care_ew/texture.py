r"""Texture / spatial-pattern features (feature group A10a, PROJECT_LOG D-023). No new download.

Per month t, on the 10 m causal (gap-filled) NDVI grid of an AOI:
  (1) Grey-level co-occurrence matrix (Haralick et al. 1973). NDVI is quantised to L = 8 levels with
      equal-probability bins (AOI 2017-2020 quantiles, fixed through time). Symmetric GLCM P(i,j) from the
      offsets (0,1) and (1,0), counted in a W x W window (W = 7 px = 70 m) around each pixel; pairs with a
      missing member are skipped. With p_ij = P(i,j) / sum P:
          contrast    = sum p_ij (i-j)^2                 homogeneity = sum p_ij / (1 + (i-j)^2)
          entropy     = -sum p_ij ln p_ij               correlation = sum p_ij (i-mu)(j-mu) / sigma^2
  (2) Multi-scale heterogeneity: NaN-aware local SD of NDVI in 3, 9 and 27 px windows and the scale ratio
      ln(SD27 / SD3) (how fast variance grows with scale; patchy / fragmented mosaics have large ratios).
  (3) Moisture / bare-soil texture: 5 x 5 local SD of NDMI and of BSI (patchy drying, bare-soil patches).
Each layer X is turned into the 12-month causal mean X12 and the change X_chg = X12 - mean(X, 2017-2020).
Only the pixels sampled in table.parquet are kept; output data/processed/<aoi>/texture.parquet (pix, time, ...).
"""
import sys, time
import numpy as np, pandas as pd
from scipy.ndimage import uniform_filter
from . import tsops as ts
from . import s2 as s2mod
from .config import AOIS, PROC

L = 8
WIN = 7
LAYERS = ["con", "hom", "ent", "cor", "sd3", "sd27", "lsr", "ndmi_sd", "bsi_sd"]
TEX_FEATURES = [f"tx_{k}{s}" for k in LAYERS for s in ("12", "_chg")]


def _box(a, w):
    return uniform_filter(a, size=w, mode="constant")      # proportional to the window sum (ratios cancel)


def local_sd(x, w):
    ok = np.isfinite(x); v = np.where(ok, x, 0).astype(np.float64)
    c = _box(ok.astype(np.float64), w); s = _box(v, w); s2 = _box(v * v, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / c
        sd = np.sqrt(np.maximum(s2 / c - m * m, 0))
    sd[c * w * w < 0.5 * w * w] = np.nan                    # fewer than half the window valid
    return sd


def glcm(q, w=WIN, levels=L):
    """q: [H, W] integer levels 0..L-1, -1 = missing. Returns contrast, homogeneity, entropy, correlation."""
    H, W_ = q.shape
    out_shape = (H, W_)
    acc = {}
    pairs = []
    for da, db in (((slice(None), slice(0, -1)), (slice(None), slice(1, None))),
                   ((slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
        a = np.full(out_shape, -1, np.int8); b = np.full(out_shape, -1, np.int8)
        a[da] = q[da]; b[da] = q[db]                       # pair assigned to the position of its first member
        pairs.append((a, b))
    V = sum(_box(((a >= 0) & (b >= 0)).astype(np.float64), w) for a, b in pairs)     # pair count / w^2
    con = sum(_box(np.where((a >= 0) & (b >= 0), (a - b).astype(np.float64) ** 2, 0), w) for a, b in pairs)
    hom = sum(_box(np.where((a >= 0) & (b >= 0), 1.0 / (1 + (a - b).astype(np.float64) ** 2), 0), w) for a, b in pairs)
    # symmetric moments: each pair counted as (a,b) and (b,a)
    s1 = sum(_box(np.where((a >= 0) & (b >= 0), (a + b).astype(np.float64), 0), w) for a, b in pairs)       # sum of i+j
    s2 = sum(_box(np.where((a >= 0) & (b >= 0), (a.astype(np.float64) ** 2 + b.astype(np.float64) ** 2), 0), w) for a, b in pairs)
    sab = sum(_box(np.where((a >= 0) & (b >= 0), (a * b).astype(np.float64), 0), w) for a, b in pairs)
    with np.errstate(invalid="ignore", divide="ignore"):
        mu = s1 / (2 * V)
        var = s2 / (2 * V) - mu * mu
        cor = (sab / V - mu * mu) / var
        cor[var < 1e-9] = 1.0                               # constant window: perfectly correlated
        # entropy from the 36 symmetric cells
        ent = np.zeros(out_shape)
        oh = [[(a == i) for i in range(levels)] for a, _ in pairs]
        ohb = [[(b == i) for i in range(levels)] for _, b in pairs]
        for i in range(levels):
            for j in range(i, levels):
                c = sum(_box((oh[k][i] & ohb[k][j]).astype(np.float64) + ((oh[k][j] & ohb[k][i]).astype(np.float64) if i != j else 0), w)
                        for k in range(len(pairs)))
                if i == j:
                    p = c / V                               # diag: (a,b)+(b,a) both i -> 2c / 2V
                    ent -= np.where(p > 0, p * np.log(p), 0)
                else:
                    p = c / (2 * V)                          # p_ij = p_ji = c / 2V, two cells
                    ent -= 2 * np.where(p > 0, p * np.log(p), 0)
        con = con / V; hom = hom / V
    bad = V * w * w < 0.5 * len(pairs) * w * w
    for a in (con, hom, ent, cor):
        a[bad] = np.nan
    return con, hom, ent, cor


def quantiser(ndvi_cal):
    edges = np.nanquantile(ndvi_cal, np.linspace(0, 1, L + 1)[1:-1])
    def q(x):
        out = np.digitize(x, edges).astype(np.int8)
        out[~np.isfinite(x)] = -1
        return out
    return q


def texture_aoi(aoi_key):
    d = PROC / aoi_key
    tab = pd.read_parquet(d / "table.parquet", columns=["pix", "time"])
    cz = np.load(d / "cube.npz")
    rr, cc, H, W = cz["rr"].astype(int), cz["cc"].astype(int), int(cz["H"]), int(cz["W"])
    times = pd.DatetimeIndex(pd.to_datetime(cz["times"]))
    years = times.year.values
    nd = cz["ndvi"].astype(np.float32)                       # causal gap-filled NDVI [T, N] (= Yc)
    T = nd.shape[0]
    pix = np.sort(tab["pix"].unique())
    pr, pc_ = rr[pix], cc[pix]
    s2 = s2mod.load(aoi_key)
    assert len(s2.time) == T, (aoi_key, len(s2.time), T)
    cal = (years >= 2017) & (years <= 2020)
    qf = quantiser(nd[cal])
    lay = {k: np.full((T, len(pix)), np.nan, np.float32) for k in LAYERS}
    for t in range(T):
        g = np.full((H, W), np.nan, np.float32); g[rr, cc] = nd[t]
        con, hom, ent, cor = glcm(qf(g))
        sd3, sd9, sd27 = local_sd(g, 3), local_sd(g, 9), local_sd(g, 27)
        with np.errstate(invalid="ignore", divide="ignore"):
            lsr = np.log((sd27 + 1e-3) / (sd3 + 1e-3))
        mask = np.full((H, W), False); mask[rr, cc] = True
        nm = np.where(mask, s2["NDMI"].values[t], np.nan); bs = np.where(mask, s2["BSI"].values[t], np.nan)
        for k, a in (("con", con), ("hom", hom), ("ent", ent), ("cor", cor), ("sd3", sd3), ("sd27", sd27),
                     ("lsr", lsr), ("ndmi_sd", local_sd(nm, 5)), ("bsi_sd", local_sd(bs, 5))):
            lay[k][t] = a[pr, pc_]
    F = {}
    for k, X in lay.items():
        m12 = ts.roll_mean(X, 12, minp=4)
        F[f"tx_{k}12"] = m12
        F[f"tx_{k}_chg"] = m12 - np.nanmean(X[cal], 0)[None, :]
    # gather the table's (pix, time) rows
    ti = times.get_indexer(pd.to_datetime(tab["time"]))
    pi = np.searchsorted(pix, tab["pix"].values)
    out = pd.DataFrame({k: v[ti, pi].astype(np.float32) for k, v in F.items()})
    out.insert(0, "time", tab["time"].values); out.insert(0, "pix", tab["pix"].values)
    out.to_parquet(d / "texture.parquet", index=False)
    return len(out), len(pix)


if __name__ == "__main__":
    for a in (sys.argv[1:] or [a.key for a in AOIS]):
        t0 = time.time()
        n, npx = texture_aoi(a)
        print(f"[{a}] texture rows={n} pixels={npx} {time.time() - t0:.0f}s", flush=True)
