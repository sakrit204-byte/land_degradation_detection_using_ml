"""Future persistent-degradation labels (CARE-EW slide 8).

A month s is BELOW-EXPECTATION for a pixel when
    R_s <= resid_thr            (vegetation below what climate explains, in local SD units) AND

An EVENT ONSET at s: s is below-expectation, s-1 is not, and the run starting at s lasts >= min_run months.
Label at prediction time t (pixel must be ELIGIBLE: not below-expectation at t):
    y_t = 1 if an onset occurs in (t, t+H]
The label needs observations up to t + H + min_run - 1; if they do not exist (end of record) or if
fewer than 60 % of those months were observed, the label is undefined (NaN) and the row is dropped.
Identical rule, identical thresholds, one data provider (Copernicus S2 L2A) for every nation ->
labels are consistent across landscapes because they are expressed relative to each pixel's own
seasonal baseline and variability.
"""
import numpy as np
from . import tsops as ts
from .config import LABEL


def below_expectation(R, dev, cfg=LABEL):
    """Per-month test. The absolute-loss part is only a noise floor (month_floor): requiring the full
    min_abs_drop in EVERY month made 6-month runs impossible wherever vegetation is dormant for > 6 months
    (steppe, Sahel: NDVI ~0.1-0.2, tiny variation) - see PROJECT_LOG I-021 / D-017."""
    with np.errstate(invalid="ignore"):
        return (R <= cfg.resid_thr) & (dev <= -cfg.month_floor)


def make_labels(R, dev, observed, cfg=LABEL):
    """R, dev: [T,N] label-version residual and NDVI deviation; observed: [T,N] bool (real obs)."""
    T, N = R.shape
    below = below_expectation(R, dev, cfg)
    fwd = ts.run_length_fwd(below)
    prev_below = np.zeros_like(below); prev_below[1:] = below[:-1]
    # the first min_run months of the run must contain >= ceil(0.75*min_run) REAL observations
    # (not gap-filled) - stops interpolation across cloudy seasons from manufacturing events
    obs_c0 = np.concatenate([np.zeros((1, N)), np.cumsum(observed, axis=0)], 0)
    need = int(np.ceil(0.75 * cfg.min_run))
    real = np.zeros((T, N), bool)
    real[:T - cfg.min_run + 1] = (obs_c0[cfg.min_run:] - obs_c0[:T - cfg.min_run + 1]) >= need
    # magnitude: the mean NDVI loss vs peers over the first min_run months must reach min_abs_drop
    dev_c = np.concatenate([np.zeros((1, N)), np.cumsum(np.nan_to_num(dev), axis=0)], 0)
    run_mean = np.zeros((T, N), np.float32)
    run_mean[:T - cfg.min_run + 1] = (dev_c[cfg.min_run:] - dev_c[:T - cfg.min_run + 1]) / cfg.min_run
    onset = below & ~prev_below & (fwd >= cfg.min_run) & real & (run_mean <= -cfg.min_abs_drop)
    H, L = cfg.horizon, cfg.horizon + cfg.min_run - 1
    y = np.full((T, N), np.nan, np.float32)
    onset_c = np.concatenate([np.zeros((1, N)), np.cumsum(onset, axis=0)], 0)
    obs_c = np.concatenate([np.zeros((1, N)), np.cumsum(observed, axis=0)], 0)
    for t in range(T - L):
        n_on = onset_c[t + H + 1] - onset_c[t + 1]
        cov = (obs_c[t + L + 1] - obs_c[t + 1]) / L
        yt = (n_on > 0).astype(np.float32)
        yt[cov < 0.6] = np.nan
        y[t] = yt
    eligible = ~below & np.isfinite(R)
    # months until the next onset (for lead-time analysis), 999 if none within H
    nxt = np.full((T, N), 999, np.int16)
    last = np.full(N, 10 ** 6)
    for t in range(T - 1, -1, -1):
        nxt[t] = np.minimum(np.where(last < 10 ** 6, last - t, 999), 999)
        last = np.where(onset[t], t, last)
    return y, eligible, onset, below, nxt
