"""Ecosystem structure & function indicators (A8) — expert guidance from a senior forest official (2026-10-21):
"land degradation is linked to ecosystem structure and function; any structural change (e.g. river-course change)
that reduces function (e.g. water availability) reduces productivity". These features describe the *mechanisms*
behind productivity loss, from Sentinel-2 data already on disk (no extra download).

WATER FUNCTION (perennial streams, ponds, water recession, wetlands, rice -> other crops)
  water      : open water in month t: MNDWI > 0 or NDVI < 0. B11 is reconstructed from the stored monthly
               indices: B8 = R (1+NDVI)/(1-NDVI); B11 = B8 (1-NDMI)/(1+NDMI); MNDWI = (G-B11)/(G+B11).
               (Medians of indices != indices of medians; adequate for a water flag.)
  water_frac12 / water_loss12 : share of the last 12 observed months with water; loss vs 2017-2020 share
  nbw_frac12 / nbw_loss12     : same for the 210 m neighbourhood (ponds / channels / wetlands around the pixel)
  paddy_frac12 / paddy_change : share of months with surface flooding of vegetation/soil (LSWI(=NDMI)+0.05 >= NDVI,
               NDVI < 0.5, not open water; Xiao et al. 2005 paddy rule) - loss = rice->dryland crop / wetland drying
VEGETATION STRUCTURE / FUNCTION (drought-hardy, invasive evergreen, thorny scrub, fire-adapted, cactus)
  p10_12 / p90_12 : dry-season (10th pct) and peak (90th pct) NDVI of the last 12 months
  evergreen_shift : p10_12 - its 2017-2020 mean (rising dry-season greenness = evergreen/woody encroachment,
                    e.g. Prosopis, Lantana; falling = loss of perennial cover)
  amp_change      : seasonal amplitude (p90-p10) change vs 2017-2020 (structure / life-form shift)
  peak_shift      : months between the current 12-month NDVI peak and the 2017-2020 climatological peak
  tex12 / tex_change : 30 m NDVI texture (3x3 SD; fragmentation / patchiness) and change vs 2017-2020
All rolling windows end at t (causal). Baselines use 2017-2020 like mu_m (documented in-training look-ahead).
"""
import warnings
import numpy as np
from . import tsops as ts
from .features import spatial_mean

warnings.filterwarnings("ignore", category=RuntimeWarning)
ECO_FEATURES = ["water_frac12", "water_loss12", "nbw_frac12", "nbw_loss12", "paddy_frac12", "paddy_change",
                "p10_12", "p90_12", "evergreen_shift", "amp_change", "peak_shift", "tex12", "tex_change"]


def water_flag(ndvi, ndmi, red, green):
    with np.errstate(all="ignore"):
        nd = np.clip(ndvi, -0.99, 0.95)
        b8 = red * (1 + nd) / (1 - nd)
        b11 = b8 * (1 - ndmi) / (1 + ndmi)
        mndwi = (green - b11) / (green + b11)
        w = ((mndwi > 0) | (ndvi < 0)).astype(np.float32)
    w[~np.isfinite(ndvi) | ~np.isfinite(ndmi) | ~np.isfinite(green)] = np.nan
    return w


def paddy_flag(ndvi, ndmi, water):
    with np.errstate(all="ignore"):
        f = ((ndmi + 0.05 >= ndvi) & (ndvi < 0.5) & (np.nan_to_num(water) < 0.5)).astype(np.float32)
    f[~np.isfinite(ndvi) | ~np.isfinite(ndmi)] = np.nan
    return f


def full_grid(ctx_like, T, H, W, rr, cc, Y, ndmi, red, green):
    """Grid-level layers: per-pixel water/paddy flags [T,N], 210 m neighbourhood water [T,N], 30 m texture [T,N]."""
    water = water_flag(Y, ndmi, red, green)
    paddy = paddy_flag(Y, ndmi, water)
    cube = np.full((T, H, W), np.nan, np.float32); cube[:, rr, cc] = water
    nbw = spatial_mean(cube, 21)[:, rr, cc]
    cube[:] = np.nan; cube[:, rr, cc] = Y
    m = spatial_mean(cube, 3); m2 = spatial_mean(cube * cube, 3)
    tex = np.sqrt(np.maximum(m2 - m * m, 0))[:, rr, cc]
    del cube, m, m2
    h = lambda a: a.astype(np.float16)     # half precision storage (I-031); cast back per pixel subset
    return dict(water=h(water), paddy=h(paddy), nbw=h(nbw), tex=h(tex))


def fast_nanquantile(a, q):
    """Vectorised NaN-aware quantile along axis 0 (linear interpolation, same as np.nanpercentile 'linear').
    np.nanpercentile falls back to a per-column Python loop when NaNs are present (~95 % of feature time)."""
    srt = np.sort(a, axis=0)                     # NaNs sort to the end
    n = np.isfinite(a).sum(0)
    pos = q * (n - 1)
    lo = np.floor(pos).astype(int); hi = np.minimum(lo + 1, np.maximum(n - 1, 0))
    lo = np.clip(lo, 0, a.shape[0] - 1); hi = np.clip(hi, 0, a.shape[0] - 1)
    vlo = np.take_along_axis(srt, lo[None, :], 0)[0]; vhi = np.take_along_axis(srt, hi[None, :], 0)[0]
    out = vlo + (pos - np.floor(pos)) * (vhi - vlo)
    out[n == 0] = np.nan
    return out


def _roll_q(Y, w, q, t_skip=None):
    out = np.full(Y.shape, np.nan, np.float32)
    for t in range(Y.shape[0]):
        if t_skip is not None and t_skip[t]:
            continue
        win = Y[max(0, t - w + 1):t + 1]
        n = np.isfinite(win).sum(0)
        v = fast_nanquantile(win, q / 100.0)
        v[n < 4] = np.nan
        out[t] = v
    return out


def _base(A, years, lo=2017, hi=2020):
    sel = (years >= lo) & (years <= hi)
    return np.nanmean(A[sel], axis=0)


def eco_features(Yc, water, paddy, nbw, tex, mu, years, t_from=0):
    """All inputs [T,n] for the selected pixels (mu: [12,n] climatology). Returns dict of [T,n] float32."""
    F = {}
    F["water_frac12"] = ts.roll_mean(water, 12, minp=4)
    F["water_loss12"] = _base(water, years)[None, :] - F["water_frac12"]
    F["nbw_frac12"] = ts.roll_mean(nbw, 12, minp=4)
    F["nbw_loss12"] = _base(nbw, years)[None, :] - F["nbw_frac12"]
    F["paddy_frac12"] = ts.roll_mean(paddy, 12, minp=4)
    F["paddy_change"] = F["paddy_frac12"] - _base(paddy, years)[None, :]
    # months needed: the 2017-2020 baseline and t >= t_from (maps); skip the rest for speed
    t_skip = ~(((years >= 2017) & (years <= 2020)) | (np.arange(len(years)) >= t_from))
    p10, p90 = _roll_q(Yc, 12, 10, t_skip), _roll_q(Yc, 12, 90, t_skip)
    F["p10_12"], F["p90_12"] = p10, p90
    base_sel = (years >= 2017) & (years <= 2020)
    F["evergreen_shift"] = p10 - np.nanmean(p10[base_sel], 0)[None, :]
    amp = p90 - p10
    F["amp_change"] = amp - np.nanmean(amp[base_sel], 0)[None, :]
    # NDVI peak month of the last 12 months vs the climatological peak month (circular difference, months)
    clim_peak = np.nanargmax(np.nan_to_num(mu, nan=-9), axis=0)
    T = Yc.shape[0]
    peak = np.full(Yc.shape, np.nan, np.float32)
    for t in range(11, T):
        win = np.nan_to_num(Yc[t - 11:t + 1], nan=-9)
        k = np.argmax(win, axis=0)                     # 0..11 within window
        cal = (t - 11 + k) % 12                          # calendar month index assuming t index aligned below
        peak[t] = cal
    F["peak_shift"] = peak  # placeholder, aligned to calendar in eco_align()
    F["_clim_peak"] = np.broadcast_to(clim_peak[None, :], Yc.shape).astype(np.float32)
    F["tex12"] = ts.roll_mean(tex, 12, minp=4)
    F["tex_change"] = F["tex12"] - _base(tex, years)[None, :]
    return F


def eco_align(F, months):
    """Convert window peak index to calendar month and take circular difference to the climatological peak."""
    T = F["peak_shift"].shape[0]
    first_month0 = int(months[0]) - 1                   # calendar month (0-11) of time index 0
    cal = (F["peak_shift"] + first_month0) % 12
    d = (cal - F.pop("_clim_peak")) % 12
    F["peak_shift"] = np.where(d > 6, d - 12, d).astype(np.float32)
    return F
