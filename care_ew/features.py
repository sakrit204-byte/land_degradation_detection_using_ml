"""Per-AOI feature + label construction (CARE-EW slides 5-8).

Pipeline for one AOI (all arrays [T, N]):
  Y      observed monthly NDVI (S2 10 m median composite)
  mu_m   per-pixel calendar-month median over CALIB_YEARS          (seasonal baseline)
  sigma  per-pixel robust SD of (Y - mu_m) over CALIB_YEARS         (local variability)
  z      (Y - mu_m) / sigma                                          (standardised anomaly)
  zhat   climate-expected anomaly = beta_pix * g_class(climate_t)    (climate model)
  R      z - zhat                                                    (climate-conditioned residual)
Features at t use only data <= t (causal carry-forward gap fill <= 2 months).
Labels at t use months t+1 ... t+H+min_run-1 (see labels.py).
"""
import numpy as np, pandas as pd, xarray as xr
from scipy.ndimage import uniform_filter
from sklearn.linear_model import RidgeCV
from . import tsops as ts
from .config import AOI_BY_KEY, PROC, CALIB_YEARS, SPLIT, LABEL, SEED, PIX_PER_AOI, BLOCK_PX
from . import s2 as s2mod

LC_KEEP = (10, 20, 30, 40, 60, 90, 95, 100)   # WorldCover: drop built-up 50, snow 70, water 80
LC_NAME = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare", 70: "snow",
           80: "water", 90: "wetland", 95: "mangrove", 100: "moss"}
CLIM_COLS = ["P1", "P3", "P6", "P12", "T1", "SM1", "SM3", "WB3"]
SIGMA_FLOOR = 0.02
MIN_CLASS_PIX = 2000   # classes smaller than this use a pooled AOI climate model
MIN_CV_R2 = 0.05       # climate model applied only if leave-one-year-out R2 >= this


# ------------------------------------------------------------------ baseline
def seasonal_baseline(Y, months, years):
    cal = (years >= CALIB_YEARS[0]) & (years <= CALIB_YEARS[1])
    mu = np.full((12, Y.shape[1]), np.nan, np.float32)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for m in range(1, 13):
            sel = cal & (months == m)
            mu[m - 1] = np.nanmedian(Y[sel], axis=0)
        # months never observed in calibration (e.g. monsoon clouds): circular neighbour fill
        for _ in range(3):
            miss = ~np.isfinite(mu)
            if not miss.any():
                break
            nb = np.nanmean(np.stack([np.roll(mu, 1, 0), np.roll(mu, -1, 0)]), axis=0)
            mu[miss] = nb[miss]
        dev = Y[cal] - mu[months[cal] - 1]
        mad = np.nanmedian(np.abs(dev - np.nanmedian(dev, axis=0)), axis=0)
    sigma = np.maximum(1.4826 * mad, SIGMA_FLOOR).astype(np.float32)
    return mu, sigma


# ------------------------------------------------------------------ climate model
def climate_design(clim, times):
    c = clim.reindex(times)[CLIM_COLS].astype(float)
    X = c.copy()
    X["P3_lag3"] = c["P3"].shift(3)       # delayed vegetation response
    X["SM3_lag2"] = c["SM3"].shift(2)
    m = times.month.values
    X["sin"] = np.sin(2 * np.pi * m / 12); X["cos"] = np.cos(2 * np.pi * m / 12)
    for k in ["P3", "SM1", "T1"]:        # season-dependent sensitivity
        X[k + "_sin"] = c[k] * X["sin"]; X[k + "_cos"] = c[k] * X["cos"]
    return X.fillna(0.0)


def fit_climate_model(z, lc, clim, times):
    """g_class: ridge regression of the class-mean anomaly on climate predictors, fitted on the
    TRAINING period only. Inside the fit period predictions are leave-one-year-out (cross-fitted)
    so training-period residuals are out-of-sample like the val/test residuals.
    beta_pix: per-pixel sensitivity, shrunk toward 1 (k = 24 pseudo-months)."""
    X = climate_design(clim, times).values
    fit = times <= pd.Timestamp(SPLIT["train_end"])
    years = times.year.values
    zhat = np.zeros_like(z)
    info = {}
    # small classes (< MIN_CLASS_PIX) share one pooled AOI model
    groups = {}
    for c in np.unique(lc):
        groups.setdefault(int(c) if (lc == c).sum() >= MIN_CLASS_PIX else -1, []).append(c)
    for c, members in groups.items():
        cols = np.isin(lc, members)
        if cols.sum() < 30:
            continue
        zc = np.nanmean(z[:, cols], axis=1)
        okt = np.isfinite(zc)
        g = np.zeros(len(times))
        alphas = np.logspace(-1, 3, 20)
        full = RidgeCV(alphas=alphas).fit(X[fit & okt], zc[fit & okt])
        g[:] = full.predict(X)
        for y in np.unique(years[fit]):                       # cross-fitting
            tr = fit & okt & (years != y); te = fit & (years == y)
            if tr.sum() > 12 and te.any():
                g[te] = RidgeCV(alphas=alphas).fit(X[tr], zc[tr]).predict(X[te])
        # pixel sensitivity
        zp = z[:, cols]; gm = g[:, None]
        ok = np.isfinite(zp) & fit[:, None]
        n = ok.sum(0)
        num = np.nansum(np.where(ok, zp * gm, 0), 0); den = np.nansum(np.where(ok, gm * gm, 0), 0)
        k = 24.0
        beta = (num + k * (den / np.maximum(n, 1))) / (den + k * (den / np.maximum(n, 1)) + 1e-9)
        beta = np.clip(beta, 0, 3)
        r2_in = 1 - np.nanvar(zc[fit & okt] - full.predict(X[fit & okt])) / np.nanvar(zc[fit & okt])
        cv_res = zc[fit & okt] - g[fit & okt]
        r2_cv = 1 - np.nanvar(cv_res) / np.nanvar(zc[fit & okt])
        used = bool(r2_cv >= MIN_CV_R2)   # climate adjustment only where it is skilful out-of-sample
        if used:
            zhat[:, cols] = g[:, None] * beta[None, :]
        info[int(c)] = dict(members=[int(m) for m in members], n_pix=int(cols.sum()), alpha=float(full.alpha_),
                            r2_in=float(r2_in), r2_loyo=float(r2_cv), beta_med=float(np.median(beta)), used=used)
    return zhat.astype(np.float32), info


# ------------------------------------------------------------------ feature block
def spatial_mean(cube_tyx, size):
    """NaN-aware moving-window mean on each time slice of a [T, H, W] cube."""
    ok = np.isfinite(cube_tyx)
    v = np.where(ok, cube_tyx, 0).astype(np.float32)
    s = uniform_filter(v, size=(1, size, size), mode="nearest")
    c = uniform_filter(ok.astype(np.float32), size=(1, size, size), mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = s / c
    out[c < 0.2] = np.nan
    return out


def peer_median(V, lc):
    """LNS-style common mode: per month, the median of V over all pixels of the same land-cover class
    (classes < MIN_CLASS_PIX pooled). Cross-sectional at each t, hence causal. [T,N] -> [T,N]."""
    out = np.zeros_like(V)
    import warnings
    big = [c for c in np.unique(lc) if (lc == c).sum() >= MIN_CLASS_PIX]
    groups = [lc == c for c in big] + [~np.isin(lc, big)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for g in groups:
            if g.sum() == 0:
                continue
            med = np.nanmedian(V[:, g], axis=1)
            out[:, g] = np.nan_to_num(med)[:, None]
    return out.astype(np.float32)


def build_features(Yc, age, mu, sigma, zhat, months, other, clim_X, peer_R, peer_d):
    """Yc: causally gap-filled NDVI [T,N]; other: dict of other causally filled indices.
    peer_R / peer_d: same-class median of the absolute residual / NDVI deviation at each month (LNS)."""
    T, N = Yc.shape
    F = {}
    d = Yc - mu[months - 1]
    z = d / sigma
    R_abs = z - zhat
    R = R_abs - peer_R            # peer-relative residual (what the label is defined on)
    F["R_abs"] = R_abs; F["R_abs_mean3"] = ts.roll_mean(R_abs, 3); F["peer_R"] = peer_R
    F["ndvi_dev_rel"] = d - peer_d
    # A1 state
    F["ndvi"] = Yc; F["z"] = z; F["ndvi_dev"] = d
    for k, v in other.items():
        F[k.lower()] = v
    F["data_age"] = age.astype(np.float32)
    F["sigma"] = np.broadcast_to(sigma, (T, N))
    F["mu_now"] = mu[months - 1]
    # A2 temporal change
    F["d_ndvi_1"] = Yc - ts.lag(Yc, 1)
    F["d_ndvi_3"] = Yc - ts.lag(Yc, 3)
    F["d_ndvi_12"] = Yc - ts.lag(Yc, 12)
    F["z_mean3"] = ts.roll_mean(z, 3); F["z_mean6"] = ts.roll_mean(z, 6)
    F["z_min6"] = ts.roll_min(z, 6)
    F["ndvi_slope12"] = ts.roll_slope(Yc, 12)
    F["ndvi_slope36"] = ts.roll_slope(Yc, 36)
    F["z_negrun"] = ts.run_length_back(np.nan_to_num(z, nan=0) < 0).astype(np.float32)
    if "NDMI" in other:
        F["d_ndmi_3"] = other["NDMI"] - ts.lag(other["NDMI"], 3)
    if "BSI" in other:
        F["bsi_slope12"] = ts.roll_slope(other["BSI"], 12)
    # A3 climate (AOI-level, broadcast)
    for c in clim_X.columns:
        F["clim_" + c] = np.broadcast_to(clim_X[c].values[:, None].astype(np.float32), (T, N))
    # A4 residual
    F["zhat"] = zhat; F["R"] = R
    F["R_mean3"] = ts.roll_mean(R, 3); F["R_mean6"] = ts.roll_mean(R, 6); F["R_mean12"] = ts.roll_mean(R, 12)
    F["R_min6"] = ts.roll_min(R, 6)
    F["R_slope12"] = ts.roll_slope(R, 12)
    F["R_negrun"] = ts.run_length_back(np.nan_to_num(R, nan=0) < 0).astype(np.float32)
    below = np.nan_to_num(R, nan=0) <= LABEL.resid_thr
    F["R_fracbelow12"] = ts.roll_mean(below.astype(np.float32), 12)
    # A5 resilience: on high-passed residual (minus 12-month trailing mean) to remove slow trend
    Rd = R - ts.roll_mean(R, 12)
    F["ac1_24"] = ts.roll_ac1(Rd, 24); F["var_24"] = ts.roll_var(Rd, 24)
    F["ac1_12"] = ts.roll_ac1(Rd, 12); F["var_12"] = ts.roll_var(Rd, 12)
    F["ac1_trend"] = F["ac1_24"] - ts.lag(F["ac1_24"], 12)
    F["var_ratio"] = F["var_12"] / (ts.lag(F["var_24"], 12) + 1e-3)
    F["months_since_dip"] = ts.months_since(below).astype(np.float32)
    rmin = ts.roll_min(R, 12)
    F["recovery_frac"] = (R - rmin) / (np.abs(rmin) + 0.1)   # how far R has climbed from its 12-mo low
    return F, z, R


FEATURE_GROUPS = {
    "A1_state": ["ndvi", "z", "ndvi_dev", "ndmi", "nbr", "bsi", "data_age", "sigma", "mu_now", "month_sin", "month_cos", "landcover"],
    "A2_change": ["d_ndvi_1", "d_ndvi_3", "d_ndvi_12", "z_mean3", "z_mean6", "z_min6", "ndvi_slope12", "ndvi_slope36",
                  "z_negrun", "d_ndmi_3", "bsi_slope12"],
    "A3_climate": None,   # filled dynamically: all clim_* columns
    "A4_residual": ["zhat", "R_abs", "R_abs_mean3", "peer_R", "ndvi_dev_rel", "R", "R_mean3", "R_mean6", "R_mean12", "R_min6", "R_slope12", "R_negrun", "R_fracbelow12"],
    "A5_resilience": ["ac1_24", "var_24", "ac1_12", "var_12", "ac1_trend", "var_ratio", "months_since_dip",
                      "recovery_frac", "modis_ac1_60", "modis_var_60", "modis_z"],
    "A6_spatial": ["R_nb5", "R_nb21", "z_nb21", "R_sd21", "aoi_frac_below", "elev", "slope", "water_occ", "dist_river_km"],
    # A7 heat stress (D-018): MODIS LST anomaly (1 km, lagged 1 mo), surface-minus-air temperature anomaly,
    # ERA5-Land hot days > p90, Tmax anomaly, VPD anomalies. Prefix heat_ keeps them out of A3.
    # A8 ecosystem structure & function (D-020, expert guidance): water recession / wetland & paddy loss,
    # dry-season greenness (evergreen/invasive encroachment), seasonal amplitude, peak timing, texture.
    "A8_ecofunc": ["water_frac12", "water_loss12", "nbw_frac12", "nbw_loss12", "paddy_frac12", "paddy_change",
                   "p10_12", "p90_12", "evergreen_shift", "amp_change", "peak_shift", "tex12", "tex_change"],
    # A9 nonlinear dynamics (D-021): higher-moment & spectral EWS, time-varying recovery rate, Langevin
    # potential (bistability), DFA long memory, permutation entropy, nonlinear rain response, spatial EWS and
    # vegetation patch-size scaling (Kefi et al. 2007). See care_ew/nonlinear.py for the equations.
    "A9_nonlinear": ["nl_skew36", "nl_kurt36", "nl_red36", "nl_ar1_ewm", "nl_lambda", "nl_dlambda12",
                     "nl_kappa", "nl_bistable", "nl_noise_ratio", "nl_dfa48", "nl_pe36",
                     "nl_brain36", "nl_r2rain36", "nl_dbrain12",
                     "nl_sp_skew21", "nl_sp_moran21", "nl_patch_vegfrac", "nl_patch_largest", "nl_patch_alpha"],
    "A7_heat": ["lst_z", "lst_z3", "dT_z", "dT_z3", "heat_HD1", "heat_HD3", "heat_TMAX1", "heat_VPD1", "heat_VPD3"],
}
HEAT_COLS = ["HD1", "HD3", "TMAX1", "VPD1", "VPD3"]
