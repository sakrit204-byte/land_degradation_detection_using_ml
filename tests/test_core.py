"""Leakage + label-logic tests. Run: .venv/Scripts/python -m pytest -q tests"""
import numpy as np
from care_ew import tsops as ts
from care_ew.labels import make_labels
from care_ew.config import LabelCfg


def _causal(fn, *a, **k):
    rng = np.random.default_rng(0)
    Y = rng.normal(size=(60, 50)).astype(np.float32); Y[rng.random(Y.shape) < .2] = np.nan
    base = fn(Y, *a, **k)
    for t in (10, 30, 45):
        Y2 = Y.copy(); Y2[t + 1:] = rng.normal(size=Y2[t + 1:].shape) * 100   # perturb the future
        out = fn(Y2, *a, **k)
        np.testing.assert_allclose(np.nan_to_num(base[:t + 1]), np.nan_to_num(out[:t + 1]), rtol=1e-5, atol=1e-5)


def test_operators_are_causal():
    for fn, a in [(ts.roll_mean, (6,)), (ts.roll_var, (12,)), (ts.roll_slope, (12,)), (ts.roll_ac1, (24,)),
                  (ts.roll_min, (6,)), (ts.lag, (3,))]:
        _causal(fn, *a)
    _causal(lambda Y: ts.causal_interp_short_gaps(Y, 2)[0])


def test_roll_ac1_matches_numpy():
    rng = np.random.default_rng(1)
    x = np.cumsum(rng.normal(size=200)).astype(np.float32)[:, None]
    a = ts.roll_ac1(x, 24)[-1, 0]
    w = x[-24:, 0]
    assert abs(a - np.corrcoef(w[1:], w[:-1])[0, 1]) < 1e-4


def test_roll_slope():
    x = (0.5 * np.arange(30)).astype(np.float32)[:, None]
    assert abs(ts.roll_slope(x, 12)[-1, 0] - 0.5) < 1e-5


def test_gap_fill_only_short():
    Y = np.array([1, np.nan, np.nan, 4, np.nan, np.nan, np.nan, 8], np.float32)[:, None]
    f = ts.interp_short_gaps(Y, 2)[:, 0]
    assert np.allclose(f[:4], [1, 2, 3, 4]) and np.isnan(f[4:7]).all()


def test_labels():
    cfg = LabelCfg(resid_thr=-1, min_run=4, min_abs_drop=0.05, horizon=6)
    T = 40
    R = np.zeros((T, 2), np.float32); dev = np.zeros((T, 2), np.float32)
    R[20:26, 0] = -2; dev[20:26, 0] = -0.1            # persistent event, onset at 20
    R[20:22, 1] = -2; dev[20:22, 1] = -0.1            # transient dip (2 months) -> NOT an event
    y, elig, onset, below, nxt = make_labels(R, dev, np.ones((T, 2), bool), cfg)
    assert onset[20, 0] and onset.sum() == 1
    assert y[14, 0] == 1 and y[19, 0] == 1 and y[13, 0] == 0   # (t, t+6] contains 20 for t=14..19
    assert np.nansum(y[:, 1]) == 0
    assert not elig[21, 0] and elig[19, 0]
    assert nxt[17, 0] == 3
    assert np.isnan(y[T - 5, 0])                         # end of record -> undefined


def test_peer_relative_removes_common_mode():
    from care_ew.features import peer_median
    T, N = 40, 3000
    rng = np.random.default_rng(3)
    R = rng.normal(0, 0.2, (T, N)).astype(np.float32); dev = R * 0.05
    R[20:26] -= 2.0; dev[20:26] -= 0.1            # whole landscape dips (drought / late monsoon / haze)
    R[20:26, :10] -= 2.0; dev[20:26, :10] -= 0.1  # 10 pixels dip MORE than their peers -> local event
    lc = np.full(N, 40)
    Rr = R - peer_median(R, lc); dr = dev - peer_median(dev, lc)
    cfg = LabelCfg()
    _, _, onset, _, _ = make_labels(Rr, dr, np.ones((T, N), bool), cfg)
    assert onset[:, :10].any(axis=0).all()          # local events kept
    assert onset[:, 10:].sum() < 0.01 * (N - 10)    # common-mode dip no longer labelled


def test_unobserved_runs_do_not_make_events():
    cfg = LabelCfg(min_run=4)
    T = 30
    R = np.zeros((T, 1), np.float32); dev = np.zeros((T, 1), np.float32)
    R[10:16] = -2; dev[10:16] = -0.1
    obs = np.ones((T, 1), bool); obs[10:14] = False   # run months were gap-filled, not observed
    _, _, onset, _, _ = make_labels(R, dev, obs, cfg)
    assert onset.sum() == 0


def test_dormant_season_does_not_block_events():
    """Steppe/Sahel: 3 growing months with a big loss + 3 dormant months with a small loss = one event."""
    cfg = LabelCfg()
    T = 40
    R = np.zeros((T, 2), np.float32); dev = np.zeros((T, 2), np.float32)
    R[20:26] = -2
    dev[20:23, 0] = -0.09; dev[23:26, 0] = -0.03      # mean -0.06 -> event
    dev[20:26, 1] = -0.03                              # tiny loss all along (mean -0.03) -> no event
    _, _, onset, _, _ = make_labels(R, dev, np.ones((T, 2), bool), cfg)
    assert onset[20, 0] and onset[:, 1].sum() == 0


def test_ecofunc_features_are_causal():
    from care_ew.ecofunc import eco_features, eco_align
    rng = np.random.default_rng(5)
    T, N = 72, 40
    months = (np.arange(T) % 12) + 1
    years = 2017 + np.arange(T) // 12
    Y = rng.uniform(0.1, 0.8, (T, N)).astype(np.float32)
    water = (rng.random((T, N)) < 0.2).astype(np.float32)
    paddy = (rng.random((T, N)) < 0.1).astype(np.float32)
    nbw = rng.random((T, N)).astype(np.float32); tex = rng.random((T, N)).astype(np.float32)
    mu = rng.uniform(0.1, 0.8, (12, N)).astype(np.float32)
    base = eco_align(eco_features(Y, water, paddy, nbw, tex, mu, years), months)
    t = 55                                   # after the 2017-2020 baseline window (index 47)
    Y2, w2 = Y.copy(), water.copy(); Y2[t + 1:] = 0.99; w2[t + 1:] = 1
    pert = eco_align(eco_features(Y2, w2, paddy, nbw, tex, mu, years), months)
    for k in base:
        np.testing.assert_allclose(np.nan_to_num(base[k][:t + 1]), np.nan_to_num(pert[k][:t + 1]), atol=1e-5, err_msg=k)
