r"""Nonlinear-dynamics indicators of approaching critical transitions (feature group A9, PROJECT_LOG D-021).

Theory: degrading land systems often have alternative stable states separated by thresholds (Scheffer et al. 2009;
Kefi et al. 2007; Rietkerk et al. 2004). Near a transition the restoring force weakens (critical slowing down),
fluctuations become skewed / heavy-tailed / "flickering", memory lengthens, complexity drops, and in drylands the
vegetation patch-size distribution loses its power-law form. Each indicator below is computed CAUSALLY on the
peer-relative residual x_t = R_t (and NDVI where stated), using trailing windows that end at t.

Notation: x_t residual series of one pixel, w window length (months), \Delta x_t = x_t - x_{t-1}.

(1) Higher moments (w = 36):  skew = m3 / m2^{3/2},  kurt = m4 / m2^2 - 3   (moments of detrended x)
    Spectral reddening:       red = Var(MA_6(x)) / Var(x)  (share of variance at periods > ~6 months)
(2) Time-varying AR(1) by exponentially-weighted recursive least squares (forgetting factor l = 0.95, a
    Kalman-type random-walk-coefficient estimate):
        phi_t = S_xy(t) / S_xx(t),  S_xy(t) = l S_xy(t-1) + x_t x_{t-1},  S_xx(t) = l S_xx(t-1) + x_{t-1}^2
    Recovery (return) rate  lambda_t = -ln|phi_t|   (lambda -> 0: critical slowing down)
(3) Langevin / Kramers-Moyal on w = 48:  \Delta x_t = a1 x_{t-1} + a3 x_{t-1}^3 + e_t, D = Var(e)
    The deterministic potential V(x) = -(a1 x^2/2 + a3 x^4/4). Curvature at the current state
    kappa = -(a1 + 3 a3 x^2) (stability; -> 0 near a fold); bistability flag a1 > 0 and a3 < 0 (double well);
    noise-to-restoring ratio D / max(-a1, eps).
(4) Detrended fluctuation analysis (w = 48, scales s = 4, 6, 8, 12): profile Y = cumsum(x - mean); per scale,
    F(s) = RMS of residuals of linear fits in non-overlapping segments; alpha = slope of log F vs log s.
    alpha ~ 0.5 white, > 1 non-stationary / long memory.
(5) Permutation entropy (Bandt & Pompe 2002), order 3, w = 36: H = -sum p_i ln p_i / ln 3!  (complexity, 0..1)
(6) Rain response (w = 36): OLS of NDVI anomaly z on rainfall anomaly P3: elasticity b_rain, coupling R^2_rain;
    d_b_rain = b_rain(t) - b_rain(t-12) (decoupling = rain-use-efficiency loss)
(7) Spatial EWS on the full 10 m grid at each month (21 x 21 px = 210 m window):
        spatial skewness of R; spatial autocorrelation (Moran-type) = corr(R, 3x3-neighbour mean of R) in the window
    Patch-size statistics per 1 km block (vegetation = NDVI > the AOI's 2017-2020 median NDVI): vegetated fraction,
    largest-patch fraction, and the power-law exponent of the patch-size complementary CDF (sizes >= 4 px)
    (Kefi et al. 2007: degradation truncates the power law, the exponent steepens, the largest patch shrinks).
"""
import warnings
import numpy as np
from scipy import ndimage
from . import tsops as ts
from .features import spatial_mean

warnings.filterwarnings("ignore", category=RuntimeWarning)
NONLIN_FEATURES = ["nl_skew36", "nl_kurt36", "nl_red36", "nl_ar1_ewm", "nl_lambda", "nl_dlambda12",
                   "nl_kappa", "nl_bistable", "nl_noise_ratio", "nl_dfa48", "nl_pe36",
                   "nl_brain36", "nl_r2rain36", "nl_dbrain12",
                   "nl_sp_skew21", "nl_sp_moran21", "nl_patch_vegfrac", "nl_patch_largest", "nl_patch_alpha"]


def _cs(a):
    c = np.cumsum(np.nan_to_num(a), axis=0, dtype=np.float64)
    return np.concatenate([np.zeros((1,) + a.shape[1:]), c], 0)


def _win(cs, w, T):
    hi = np.arange(1, T + 1); lo = np.maximum(hi - w, 0)
    return cs[hi] - cs[lo]


def rolling_moments(x, w, minp):
    """Causal rolling skewness, excess kurtosis of x (NaN-aware) via power sums."""
    T = x.shape[0]
    ok = np.isfinite(x).astype(np.float64)
    xv = np.where(ok > 0, x, 0.0)
    n = _win(_cs(ok), w, T)
    s1, s2, s3, s4 = (_win(_cs(xv ** k), w, T) for k in (1, 2, 3, 4))
    with np.errstate(all="ignore"):
        m = s1 / n
        m2 = s2 / n - m ** 2
        m3 = s3 / n - 3 * m * s2 / n + 2 * m ** 3
        m4 = s4 / n - 4 * m * s3 / n + 6 * m ** 2 * s2 / n - 3 * m ** 4
        skew = m3 / np.power(np.maximum(m2, 1e-9), 1.5)
        kurt = m4 / np.maximum(m2, 1e-9) ** 2 - 3
    skew[n < minp] = np.nan; kurt[n < minp] = np.nan
    return skew.astype(np.float32), kurt.astype(np.float32)


def ewm_ar1(x, lam=0.95):
    """Exponentially-weighted recursive AR(1) coefficient and return rate (causal)."""
    T, N = x.shape
    sxy = np.zeros(N); sxx = np.zeros(N)
    phi = np.full((T, N), np.nan, np.float32)
    prev = np.full(N, np.nan)
    for t in range(T):
        cur = x[t]
        ok = np.isfinite(cur) & np.isfinite(prev)
        sxy = lam * sxy + np.where(ok, cur * prev, 0)
        sxx = lam * sxx + np.where(ok, prev * prev, 0)
        with np.errstate(all="ignore"):
            phi[t] = np.where(sxx > 1e-6, sxy / sxx, np.nan)
        prev = np.where(np.isfinite(cur), cur, prev)
    phi = np.clip(phi, -0.999, 0.999)
    lam_rate = -np.log(np.abs(phi) + 1e-6)
    return phi, lam_rate.astype(np.float32)


def langevin(x, w=48, minp=24):
    """Causal cubic-drift fit Dx_t = a1 x + a3 x^3 + e on a trailing window; returns kappa, bistable, noise ratio."""
    T, N = x.shape
    x0 = np.full_like(x, np.nan); x0[1:] = x[:-1]
    dx = x - x0
    ok = (np.isfinite(x0) & np.isfinite(dx)).astype(np.float64)
    a = np.where(ok > 0, x0, 0.0); d = np.where(ok > 0, dx, 0.0)
    S = {k: _win(_cs(v), w, T) for k, v in dict(n=ok, x2=a ** 2, x4=a ** 4, x6=a ** 6, xd=a * d, x3d=a ** 3 * d, d2=d ** 2).items()}
    with np.errstate(all="ignore"):
        det = S["x2"] * S["x6"] - S["x4"] ** 2
        a1 = (S["xd"] * S["x6"] - S["x3d"] * S["x4"]) / det
        a3 = (S["x2"] * S["x3d"] - S["x4"] * S["xd"]) / det
        sse = S["d2"] - a1 * S["xd"] - a3 * S["x3d"]
        D = np.maximum(sse, 0) / np.maximum(S["n"] - 2, 1)
        xc = np.nan_to_num(x)
        kappa = -(a1 + 3 * a3 * xc ** 2)
        bist = ((a1 > 0) & (a3 < 0)).astype(np.float32)
        noise_ratio = D / np.maximum(-a1, 0.01)
    bad = (S["n"] < minp) | ~np.isfinite(det) | (np.abs(det) < 1e-9)
    for v in (kappa, noise_ratio):
        v[bad] = np.nan
    bist[bad] = np.nan
    return kappa.astype(np.float32), bist, np.clip(noise_ratio, 0, 50).astype(np.float32)


def dfa_alpha(x, w=48, scales=(4, 6, 8, 12), minp=36, t_from=0):
    """Causal rolling DFA-1 exponent (computed at each t from the last w months; NaNs filled by window mean)."""
    T, N = x.shape
    out = np.full((T, N), np.nan, np.float32)
    ls = np.log(scales)
    for t in range(max(w - 1, t_from), T):   # t_from: skip months that are not needed (maps)
        win = x[t - w + 1:t + 1]
        cnt = np.isfinite(win).sum(0)
        m = np.nanmean(win, 0)
        win = np.where(np.isfinite(win), win, m)
        Y = np.cumsum(win - m, axis=0)
        logF = []
        for s in scales:
            k = w // s
            seg = Y[:k * s].reshape(k, s, N)
            tt = np.arange(s, dtype=np.float64); tt -= tt.mean()
            ym = seg.mean(1, keepdims=True)
            b = ((seg - ym) * tt[None, :, None]).sum(1, keepdims=True) / (tt ** 2).sum()
            res = seg - ym - b * tt[None, :, None]
            F = np.sqrt((res ** 2).mean(axis=(0, 1)))
            logF.append(np.log(F + 1e-9))
        logF = np.stack(logF)                                   # [S, N]
        lsc = ls - ls.mean()
        out[t] = ((logF - logF.mean(0)) * lsc[:, None]).sum(0) / (lsc ** 2).sum()
        out[t][cnt < minp] = np.nan
    return out


def perm_entropy(x, w=36, minp=20):
    """Causal rolling permutation entropy of order 3 (normalised to [0,1])."""
    T, N = x.shape
    a, b, c = x[:-2], x[1:-1], x[2:]
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    # 6 ordinal patterns of (a,b,c)
    pats = [(a <= b) & (b <= c), (a <= c) & (c < b), (c < a) & (a <= b),
            (b < a) & (a <= c), (b <= c) & (c < a), (c < b) & (b < a)]
    counts = []
    for p in pats:
        v = np.zeros((T, N)); v[2:] = (p & ok)
        counts.append(_win(_cs(v), w - 2, T))
    C = np.stack(counts)                                        # [6, T, N]
    tot = C.sum(0)
    with np.errstate(all="ignore"):
        P = C / tot
        H = -(np.where(P > 0, P * np.log(P), 0)).sum(0) / np.log(6)
    H[tot < minp] = np.nan
    return H.astype(np.float32)


def rain_response(z, p3, w=36, minp=18):
    """Rolling OLS of z on rainfall anomaly p3 ([T] broadcast): elasticity and R^2 (causal)."""
    T, N = z.shape
    P = np.broadcast_to(p3[:, None], z.shape)
    ok = (np.isfinite(z) & np.isfinite(P)).astype(np.float64)
    zv, pv = np.where(ok > 0, z, 0), np.where(ok > 0, P, 0)
    n = _win(_cs(ok), w, T)
    sp, sz, spp, szz, spz = (_win(_cs(v), w, T) for v in (pv, zv, pv * pv, zv * zv, pv * zv))
    with np.errstate(all="ignore"):
        cov = spz - sp * sz / n; vp = spp - sp ** 2 / n; vz = szz - sz ** 2 / n
        b = cov / vp
        r2 = cov ** 2 / (vp * vz)
    b[n < minp] = np.nan; r2[n < minp] = np.nan
    db = b - ts.lag(b.astype(np.float32), 12)
    return b.astype(np.float32), np.clip(r2, 0, 1).astype(np.float32), db.astype(np.float32)


# ------------------------------------------------------------------ spatial (full grid, each month)
def spatial_ews(Rcube):
    """Spatial skewness and Moran-type autocorrelation of R in 21x21 windows. Rcube [T,H,W] -> two cubes."""
    m1 = spatial_mean(Rcube, 21); m2 = spatial_mean(Rcube ** 2, 21); m3 = spatial_mean(Rcube ** 3, 21)
    var = np.maximum(m2 - m1 ** 2, 1e-6)
    skew = (m3 - 3 * m1 * m2 + 2 * m1 ** 3) / var ** 1.5
    nb = spatial_mean(Rcube, 3)                                 # local neighbour mean
    mxy = spatial_mean(Rcube * nb, 21); mn = spatial_mean(nb, 21); mn2 = spatial_mean(nb ** 2, 21)
    moran = (mxy - m1 * mn) / np.sqrt(var * np.maximum(mn2 - mn ** 2, 1e-6))
    return skew.astype(np.float32), np.clip(moran, -1, 1).astype(np.float32)


def patch_stats(ndvi_cube, block=100, veg_thr=0.3):
    """Per 1 km block and month: vegetated fraction, largest-patch fraction, CCDF power-law exponent.
    Returns three [T,H,W] cubes (block values broadcast to pixels)."""
    T, H, W = ndvi_cube.shape
    vf = np.full((T, H, W), np.nan, np.float32); lp = vf.copy(); al = vf.copy()
    st = np.ones((3, 3), bool)
    for t in range(T):
        img = ndvi_cube[t]
        for r0 in range(0, H, block):
            for c0 in range(0, W, block):
                b = img[r0:r0 + block, c0:c0 + block]
                okm = np.isfinite(b)
                if okm.mean() < 0.6:
                    continue
                veg = (b > veg_thr) & okm   # ONE threshold per AOI (calibration-period median NDVI), not per block-month (I-029)
                lab, n = ndimage.label(veg, structure=st)
                v = veg.sum() / okm.sum()
                vf[t, r0:r0 + block, c0:c0 + block] = v
                if n == 0:
                    lp[t, r0:r0 + block, c0:c0 + block] = 0
                    continue
                sizes = np.bincount(lab.ravel())[1:]
                lp[t, r0:r0 + block, c0:c0 + block] = sizes.max() / max(veg.sum(), 1)
                s = np.sort(sizes[sizes >= 4])
                if len(s) >= 8:
                    ccdf = 1.0 - np.arange(len(s)) / len(s)
                    xs, ys = np.log(s), np.log(ccdf)
                    xs = xs - xs.mean()
                    if (xs ** 2).sum() > 1e-9:
                        al[t, r0:r0 + block, c0:c0 + block] = float((xs * (ys - ys.mean())).sum() / (xs ** 2).sum())
    return vf, lp, al


def nonlinear_features(R, z, p3, sp_skew, sp_moran, pvf, plp, pal, t_from=0):
    """Per-pixel features for selected pixels. R, z [T,n]; p3 [T]; spatial inputs [T,n]."""
    F = {}
    Rd = R - ts.roll_mean(R, 12)
    F["nl_skew36"], F["nl_kurt36"] = rolling_moments(Rd, 36, 20)
    with np.errstate(all="ignore"):
        F["nl_red36"] = (ts.roll_var(ts.roll_mean(Rd, 6, minp=3), 36) / ts.roll_var(Rd, 36)).astype(np.float32)
    F["nl_ar1_ewm"], F["nl_lambda"] = ewm_ar1(Rd)
    F["nl_dlambda12"] = F["nl_lambda"] - ts.lag(F["nl_lambda"], 12)
    F["nl_kappa"], F["nl_bistable"], F["nl_noise_ratio"] = langevin(Rd)
    F["nl_dfa48"] = dfa_alpha(R, t_from=t_from)
    F["nl_pe36"] = perm_entropy(R)
    F["nl_brain36"], F["nl_r2rain36"], F["nl_dbrain12"] = rain_response(z, p3)
    F["nl_sp_skew21"], F["nl_sp_moran21"] = sp_skew, sp_moran
    F["nl_patch_vegfrac"], F["nl_patch_largest"], F["nl_patch_alpha"] = pvf, plp, pal
    return F
