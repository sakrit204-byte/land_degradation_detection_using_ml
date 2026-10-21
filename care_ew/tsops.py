"""Vectorised, NaN-aware time-series operators on arrays shaped [T, N] (time x pixels).

Every operator at index t uses ONLY values at indices <= t (causal), which is what
guarantees that features never contain future information. Unit tests: tests/test_tsops.py
"""
import numpy as np


def interp_short_gaps(Y, max_gap=2):
    """Linear interpolation of interior NaN gaps of length <= max_gap. Longer gaps stay NaN.
    NOTE: interpolation uses the next valid value, so it is NOT causal; it is applied to the
    observation record before features are built and the leakage is bounded to max_gap months.
    Features additionally get a causal 'data_age' so the model knows when values were filled."""
    Y = Y.astype(np.float32).copy()
    T, N = Y.shape
    ok = np.isfinite(Y)
    idx = np.arange(T)[:, None].repeat(N, 1)
    prev = np.where(ok, idx, -1); prev = np.maximum.accumulate(prev, axis=0)
    nxt = np.where(ok, idx, T); nxt = np.minimum.accumulate(nxt[::-1], axis=0)[::-1]
    gap = nxt - prev - 1
    fill = (~ok) & (prev >= 0) & (nxt < T) & (gap <= max_gap)
    if fill.any():
        cols = np.nonzero(fill)
        p, q = prev[cols], nxt[cols]
        yp, yq = Y[p, cols[1]], Y[q, cols[1]]
        w = (cols[0] - p) / (q - p)
        Y[cols] = yp + w * (yq - yp)
    return Y


def causal_interp_short_gaps(Y, max_gap=2):
    """Causal variant: carry the last valid value forward for <= max_gap months."""
    Y = Y.astype(np.float32).copy()
    T, N = Y.shape
    ok = np.isfinite(Y)
    idx = np.arange(T)[:, None].repeat(N, 1)
    prev = np.maximum.accumulate(np.where(ok, idx, -1), axis=0)
    age = np.where(prev >= 0, idx - prev, 999)
    fill = (~ok) & (prev >= 0) & (age <= max_gap)
    cols = np.nonzero(fill)
    Y[cols] = Y[prev[cols], cols[1]]
    return Y, age.astype(np.int16)


def _csum(a):
    c = np.cumsum(a, axis=0, dtype=np.float64)
    return np.concatenate([np.zeros((1,) + a.shape[1:]), c], axis=0)


def roll_sum_count(Y, w):
    ok = np.isfinite(Y)
    v = np.where(ok, Y, 0.0)
    cs, cc = _csum(v), _csum(ok.astype(np.float64))
    T = Y.shape[0]
    lo = np.maximum(np.arange(1, T + 1) - w, 0)
    hi = np.arange(1, T + 1)
    return cs[hi] - cs[lo], cc[hi] - cc[lo]


def roll_mean(Y, w, minp=None):
    minp = minp or max(1, w // 2)
    s, c = roll_sum_count(Y, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / c
    m[c < minp] = np.nan
    return m.astype(np.float32)


def roll_var(Y, w, minp=None):
    minp = minp or max(3, w // 2)
    s, c = roll_sum_count(Y, w)
    s2, _ = roll_sum_count(Y * Y, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        v = (s2 - s * s / c) / (c - 1)
    v[c < minp] = np.nan
    return np.maximum(v, 0).astype(np.float32)


def roll_min(Y, w):
    T = Y.shape[0]
    out = np.full(Y.shape, np.nan, np.float32)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for t in range(T):
                out[t] = np.nanmin(Y[max(0, t - w + 1):t + 1], axis=0)
    return out


def roll_slope(Y, w, minp=None):
    """OLS slope per time step over trailing window (units of Y per month)."""
    minp = minp or max(4, w // 2)
    T = Y.shape[0]
    tt = np.arange(T, dtype=np.float64)[:, None] * np.ones((1, Y.shape[1]))
    ok = np.isfinite(Y)
    tt = np.where(ok, tt, np.nan)
    sy, n = roll_sum_count(Y, w)
    st, _ = roll_sum_count(tt, w)
    stt, _ = roll_sum_count(tt * tt, w)
    sty, _ = roll_sum_count(tt * np.where(ok, Y, np.nan), w)
    with np.errstate(invalid="ignore", divide="ignore"):
        b = (n * sty - st * sy) / (n * stt - st * st)
    b[n < minp] = np.nan
    return b.astype(np.float32)


def roll_ac1(Y, w, minp=None):
    """Lag-1 autocorrelation over trailing window of w months (pairs (t-1, t) both inside)."""
    minp = minp or max(6, w // 2)
    x = Y[1:]; y = Y[:-1]
    ok = np.isfinite(x) & np.isfinite(y)
    xv, yv = np.where(ok, x, np.nan), np.where(ok, y, np.nan)
    sx, n = roll_sum_count(xv, w - 1)
    sy, _ = roll_sum_count(yv, w - 1)
    sxx, _ = roll_sum_count(xv * xv, w - 1)
    syy, _ = roll_sum_count(yv * yv, w - 1)
    sxy, _ = roll_sum_count(xv * yv, w - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sxy - sx * sy / n
        r = cov / np.sqrt((sxx - sx * sx / n) * (syy - sy * sy / n))
    r[n < minp] = np.nan
    out = np.full(Y.shape, np.nan, np.float32)
    out[1:] = np.clip(r, -1, 1)
    return out


def run_length_back(cond):
    """Consecutive months ending at t where cond is True."""
    out = np.zeros(cond.shape, np.int16)
    run = np.zeros(cond.shape[1], np.int16)
    for t in range(cond.shape[0]):
        run = np.where(cond[t], run + 1, 0)
        out[t] = run
    return out


def run_length_fwd(cond):
    """Consecutive months starting at t where cond is True (uses the future: LABELS ONLY)."""
    out = np.zeros(cond.shape, np.int16)
    run = np.zeros(cond.shape[1], np.int16)
    for t in range(cond.shape[0] - 1, -1, -1):
        run = np.where(cond[t], run + 1, 0)
        out[t] = run
    return out


def lag(Y, k):
    out = np.full(Y.shape, np.nan, np.float32)
    out[k:] = Y[:-k]
    return out


def months_since(cond):
    """Months since cond was last True (causal); 999 if never."""
    T, N = cond.shape
    out = np.zeros((T, N), np.int16)
    last = np.full(N, -10000)
    for t in range(T):
        last = np.where(cond[t], t, last)
        out[t] = np.minimum(t - last, 999)
    return out
