"""Mathematical validation of the nonlinear-dynamics indicators (A9) on processes with KNOWN properties."""
import numpy as np
from scipy import stats
from care_ew import nonlinear as NL

rng = np.random.default_rng(42)


def test_rolling_moments_match_scipy():
    x = rng.gamma(2.0, 1.0, (200, 3)).astype(np.float32)          # skewed distribution
    sk, ku = NL.rolling_moments(x, 36, 20)
    w = x[-36:, 0]
    assert abs(sk[-1, 0] - stats.skew(w)) < 1e-3
    assert abs(ku[-1, 0] - stats.kurtosis(w)) < 1e-2


def _ar1(phi, T=600, N=20):
    x = np.zeros((T, N))
    for t in range(1, T):
        x[t] = phi * x[t - 1] + rng.normal(size=N)
    return x.astype(np.float32)


def test_ewm_ar1_recovers_coefficient_and_slowing_down():
    for phi in (0.2, 0.8):
        est, lam = NL.ewm_ar1(_ar1(phi), lam=0.98)
        assert abs(np.nanmean(est[-1]) - phi) < 0.1
    # critical slowing down: higher phi -> lower return rate
    assert np.nanmean(NL.ewm_ar1(_ar1(0.9))[1][-1]) < np.nanmean(NL.ewm_ar1(_ar1(0.3))[1][-1])


def _langevin(drift, T=3000, N=10, dt=0.1, s=0.5):
    x = np.zeros((T, N)); x[0] = 0.1
    for t in range(1, T):
        x[t] = x[t - 1] + drift(x[t - 1]) * dt + s * np.sqrt(dt) * rng.normal(size=N)
    return x[::5].astype(np.float32)


def test_langevin_detects_double_well_vs_single_well():
    dbl = _langevin(lambda x: x - x ** 3)          # bistable potential V = -x^2/2 + x^4/4
    sgl = _langevin(lambda x: -x)                  # single well
    _, b_dbl, _ = NL.langevin(dbl, w=400, minp=200)
    _, b_sgl, _ = NL.langevin(sgl, w=400, minp=200)
    assert np.nanmean(b_dbl[-1]) > 0.6 and np.nanmean(b_sgl[-1]) < 0.4


def test_dfa_white_noise_and_random_walk():
    wn = rng.normal(size=(400, 30)).astype(np.float32)
    rw = np.cumsum(rng.normal(size=(400, 30)), 0).astype(np.float32)
    a_wn = np.nanmean(NL.dfa_alpha(wn)[-1]); a_rw = np.nanmean(NL.dfa_alpha(rw)[-1])
    assert 0.3 < a_wn < 0.75 and a_rw > 1.2, (a_wn, a_rw)


def test_permutation_entropy_bounds():
    wn = rng.normal(size=(200, 10)).astype(np.float32)
    mono = np.tile(np.arange(200, dtype=np.float32)[:, None], (1, 10))
    assert np.nanmean(NL.perm_entropy(wn)[-1]) > 0.9
    assert np.nanmax(NL.perm_entropy(mono)[-1]) < 1e-6


def test_rain_response_elasticity():
    p3 = rng.normal(size=120).astype(np.float32)
    z = (2.0 * p3[:, None] + 0.3 * rng.normal(size=(120, 5))).astype(np.float32)
    b, r2, _ = NL.rain_response(z, p3)
    assert abs(np.nanmean(b[-1]) - 2.0) < 0.15 and np.nanmean(r2[-1]) > 0.9


def test_all_temporal_indicators_are_causal():
    x = rng.normal(size=(120, 15)).astype(np.float32)
    p3 = rng.normal(size=120).astype(np.float32)
    t = 80
    x2 = x.copy(); x2[t + 1:] = 50.0
    p2 = p3.copy(); p2[t + 1:] = -9.0
    fns = [lambda a, p: NL.rolling_moments(a, 36, 20)[0], lambda a, p: NL.ewm_ar1(a)[0],
           lambda a, p: NL.langevin(a)[0], lambda a, p: NL.dfa_alpha(a), lambda a, p: NL.perm_entropy(a),
           lambda a, p: NL.rain_response(a, p)[0]]
    for f in fns:
        np.testing.assert_allclose(np.nan_to_num(f(x, p3)[:t + 1]), np.nan_to_num(f(x2, p2)[:t + 1]), atol=1e-4)


def test_patch_stats_power_law_exponent_and_degradation_signal():
    # intact: many patches of varied size; degraded: same cover broken into small uniform patches
    H = W = 100
    intact = np.zeros((1, H, W), np.float32)
    rr, cc = np.mgrid[0:H, 0:W]
    for (r, c, rad) in [(30, 30, 18), (70, 70, 12), (20, 80, 8), (80, 20, 6), (50, 50, 4), (10, 50, 3), (60, 10, 3), (90, 60, 2)]:
        intact[0][(rr - r) ** 2 + (cc - c) ** 2 <= rad ** 2] = 0.8
    degraded = np.zeros((1, H, W), np.float32)
    degraded[0][(rr % 6 < 2) & (cc % 6 < 2)] = 0.8
    vf_i, lp_i, _ = NL.patch_stats(intact); vf_d, lp_d, _ = NL.patch_stats(degraded)
    assert lp_i[0, 0, 0] > 0.3 and lp_d[0, 0, 0] < 0.05      # largest-patch fraction collapses when fragmented


def test_fast_nanquantile_matches_numpy():
    from care_ew.ecofunc import fast_nanquantile
    a = rng.normal(size=(12, 500)); a[rng.random(a.shape) < 0.3] = np.nan
    for q in (0.1, 0.5, 0.9):
        ref = np.nanpercentile(a, q * 100, axis=0)
        np.testing.assert_allclose(fast_nanquantile(a, q), ref, rtol=1e-12, atol=1e-12)
