# CARE-EW: Climate-Adjusted Resilience Early Warning of Persistent Land Degradation from Open Earth-Observation Data

*Draft v0.3 (2026-10-19) — written from `docs/PROJECT_LOG.md`; every number in §4 is taken from
`outputs/results/metrics.json` and `corroboration.json` (run E-003). Remaining ⟨…⟩ are author details.*

**Authors:** ⟨author list⟩  **Affiliation:** ⟨affiliation⟩  **Corresponding author:** ⟨email⟩

---

## Abstract

Land-degradation monitoring with satellite data is usually retrospective: maps show where vegetation has
already declined. Management agencies need the opposite — a warning *before* the decline becomes
persistent, with an honest statement of uncertainty. We present CARE-EW, an open, reproducible framework
that predicts, at month *t*, the probability that a 10 m pixel will enter a persistent,
climate-unexplained vegetation decline within the next six months. CARE-EW combines Sentinel-2 spectral
state and change, a climate-conditioned residual (observed minus climate-expected vegetation anomaly),
resilience indicators (lag-1 autocorrelation, variance, recovery), MODIS long-record context and
terrain/hydrological context in a gradient-boosted model with isotonic calibration and split-conformal
abstention. Labels are derived with one rule from one provider (Copernicus Sentinel-2 L2A) in locally
standardised units, making them consistent across nine study areas in nine nations on five continents.
Under a locked spatio-temporal hold-out (unseen 1 km blocks *and* unseen months, December 2024 – October
2025), CARE-EW reaches a PR-AUC of 0.113 (95 % CI 0.085–0.163; 4.4× the 2.6 % base rate) and ROC-AUC 0.76
with well-calibrated probabilities (ECE 0.009), against 0.058 for the best non-learning baseline and 0.035
for a Sentinel-only random forest. A cumulative ablation shows that spectral state, change and raw climate
variables barely exceed chance, the climate-conditioned residual roughly triples skill, and resilience
indicators add a further 30 %; five of the nine most influential features are resilience indicators. At a
2 % false-alarm rate, 31 % of test events are warned at least one month ahead (median lead 2 months).
Models transfer to nations never seen in training (2.4–9.3× lift), skill grows monotonically with
accumulating Sentinel-2 history in walk-forward retraining (PR-AUC 0.03 → 0.16), and results hold under
nine alternative label definitions. Landsat 8/9 independently corroborates the labels in seven of nine
areas (agreement AUC 0.61–0.93) but not in the Sahel and Mongolian steppe sites, which we report as
unverified. We release code, labels and an operational web console that maps warnings, explanations and
upstream river networks.

**Keywords:** land degradation; early warning; Sentinel-2; resilience; critical slowing down; climate
conditioning; conformal prediction; SDG 15.3

---

## 1. Introduction

Land degradation affects roughly a quarter to a third of the global land surface and is the target of
SDG indicator 15.3.1 (proportion of land that is degraded). Operational assessment, e.g. through the
UNCCD Good Practice Guidance, relies on trends in productivity, land cover and soil organic carbon.
Remote-sensing approaches range from NDVI trend analysis and residual trend analysis (RESTREND), which
removes the rainfall-driven component of vegetation change, to machine-learning classification of
degraded land from multi-temporal imagery. These approaches answer *where has degradation occurred?* —
they are retrospective by construction.

A separate literature on resilience and critical slowing down shows that systems approaching a transition
often recover more slowly from perturbations, which manifests as rising lag-1 autocorrelation (AC1) and
variance in their time series. Satellite vegetation records have been used to map such resilience
indicators at global scale. Whether they translate into *useful, calibrated, pixel-level forecasts* of
degradation events — with measurable lead time and controlled false alarms — is much less established.

**Contribution.** We do not claim a new sensor, a new index or a new model class. The contribution is an
integrated, forward-looking and falsifiable experiment:
1. a **future-event target** — onset of a persistent (≥ 4 months), climate-unexplained decline within
   the next 6 months — so the task is a forecast, not a classification of the present;
2. **climate conditioning** that separates drought-driven decline from unexplained decline, with an
   explicit rule that climate adjustment is only applied where it is skilful out-of-sample;
3. **resilience features** treated as hypotheses, tested by ablation rather than assumed;
4. **calibrated probabilities with conformal abstention**, so the system can say "uncertain — inspect";
5. a **validation protocol** designed against the three usual sources of optimism in EO machine learning:
   spatial autocorrelation, temporal leakage and landscape over-representation;
6. **label consistency across nations** and **independent-sensor corroboration** of labels.

---

## 2. Study areas and data

### 2.1 Study areas
Nine 5.12 × 5.12 km areas (512 × 512 Sentinel-2 pixels) were selected to span biomes, land uses and
degradation processes and to include "hard negatives" where vegetation declines for climatic reasons
(Table 1, Fig. 1). Each area is snapped to one internal 512-px block of one MGRS tile (§3.1).

**Table 1.** Study areas (5.12 × 5.12 km; one internal block of the listed Sentinel-2 tile). Land cover from
ESA WorldCover 2021 (classes ≥ 3 %); rows = eligible labelled pixel-months 2019–2025 for 5000 sampled pixels;
positive rate = share with y = 1.

| Area | Nation | Tile | Land cover (%) | Rows | Positive rate | Onsets / pixel / yr | Climate model applied to |
|---|---|---|---|---|---|---|---|
| Chure foothills | Nepal | 45RUK | tree 85, crop 8, bare 5 | 326 032 | 0.78 % | 0.014 | bare, pooled small classes |
| Bundelkhand | India | 44RLP | crop 81, grass 13, tree 4 | 316 887 | 0.95 % | 0.018 | tree, grass, crop |
| Tigray highlands | Ethiopia | 37PER | crop 49, shrub 35, grass 16 | 340 513 | 1.62 % | 0.027 | — |
| Marigat, Baringo | Kenya | 36NZF | grass 38, tree 26, shrub 19, crop 14 | 336 514 | 2.91 % | 0.056 | tree, shrub, grass |
| Ferlo | Senegal | 28PEC | grass 88, shrub 10 | 357 686 | 0.82 % | 0.014 | grass, pooled |
| Murcia | Spain | 30SXG | grass 40, crop 38, bare 19 | 337 139 | 3.11 % | 0.056 | grass, crop, bare |
| Western Bahia (MATOPIBA) | Brazil | 23LLG | crop 80, grass 10, shrub 6, tree 4 | 320 163 | 2.99 % | 0.053 | — |
| Central steppe | Mongolia | 48TXS | grass 100 | 371 304 | 0.03 % | 0.0004 | — |
| Western NSW | Australia | 55JCF | tree 72, grass 28 | 355 419 | 2.10 % | 0.041 | tree, grass |

### 2.2 Data
All inputs are open and anonymously accessible (Table 2): Sentinel-2 L2A (ESA/Copernicus, 2017-01 to
2026-09), MODIS MOD13Q1 v061 NDVI (NASA, 2000–), Landsat 8/9 Collection-2 L2 (NASA/USGS; label
corroboration only), ERA5-Land and ERA5 (ECMWF/Copernicus C3S; 2 m temperature, soil moisture 0–7 and
7–28 cm, precipitation, FAO-56 reference evapotranspiration), ESA WorldCover 2021, NASADEM, JRC Global
Surface Water, HydroRIVERS v1.0 and GloFAS v4 discharge reanalysis.

**Table 2.** Data sources (all open; anonymous access).

| Layer | Provider | Product | Resolution | Period | Role |
|---|---|---|---|---|---|
| Optical | ESA / Copernicus | Sentinel-2 L2A | 10–20 m | 2017-01 – 2026-09 | features, labels |
| Vegetation history | NASA | MODIS MOD13Q1 v061 | 250 m | 2000 – | long-record features |
| Optical (independent) | NASA / USGS | Landsat 8/9 C2 L2 | 30 m | 2018–20, 2023–26 | label corroboration only |
| Climate | ECMWF / C3S | ERA5-Land, ERA5 | 9–25 km | 1991 – | climate expectation |
| Land cover | ESA | WorldCover 2021 v200 | 10 m | 2021 | masking, strata |
| Terrain | NASA | NASADEM | 30 m | 2000 | context |
| Surface water | EC JRC | GSW v1.3 | 30 m | 1984–2020 | context |
| Rivers | WWF | HydroRIVERS v1.0 | 15″ | static | network, distance |
| Discharge | Copernicus EMS | GloFAS v4 reanalysis | ~5 km | 1984 – | display only |

---

## 3. Methods

### 3.1 Sentinel-2 monthly composites
For each area and month we query Sentinel-2 L2A scenes with scene cloud cover < 70 %. Because the archive
contains multiple processings of the same datatake (e.g. processing baselines 02.12 and the 05.00
reprocessing), we keep only the newest processing per (tile, sensing time). Reflectance is harmonised per
scene: baselines ≥ 04.00 carry `BOA_ADD_OFFSET = −1000`, so ρ = (DN − 1000)/10⁴; earlier baselines
ρ = DN/10⁴. To bound download volume we use the single MGRS tile to which the area grid is aligned and the
four least-cloudy acquisitions of each month. Pixels are retained where the Sen2Cor scene classification
is vegetation, bare soil or water. NDVI, NDMI, NBR and BSI are computed per observation and composited by
the monthly median.

### 3.2 Seasonal baseline and anomaly
For each pixel, the seasonal baseline μₘ is the calendar-month median NDVI over 2017–2020 and σ is the
robust standard deviation (1.4826 × MAD) of deviations from μₘ over the same years, floored at 0.02.
The standardised anomaly is zₜ = (Yₜ − μₘ₍ₜ₎)/σ.

### 3.3 Climate conditioning
For each area and land-cover class (classes < 2000 pixels pooled), a ridge regression g predicts the
class-mean anomaly from climate predictors: standardised precipitation accumulations over 1, 3, 6 and 12
months, temperature anomaly, surface and root-zone soil-moisture anomalies, 3-month climatic water balance
(P − ET0), lagged terms and season interactions. It is fitted only on the training period (≤ 2022-03);
predictions inside that period are leave-one-year-out cross-fitted. Pixel sensitivity β is the regression
slope of pixel z on g, shrunk toward 1 (24 pseudo-observations) and clipped to [0, 3]. The
climate-expected anomaly is Ẑₜ = β·gₜ and the residual Rₜ = zₜ − Ẑₜ. **Climate adjustment is applied only
where the leave-one-year-out R² ≥ 0.05**; otherwise Ẑ = 0 and R = z. This operationalises the principle of
adding weather data only where it demonstrably helps.

### 3.4 Target definition
A degradation signal must be *local*: if every pixel of a land-cover class in an area declines together in
the same month (a regional drought, a late monsoon, haze or a compositing artefact), that is not land
degradation. Following the logic of Local Net Production Scaling (LNS; Prince et al., 2009), we therefore
express the residual relative to landscape peers: Rₜ = (zₜ − Ẑₜ) − median over pixels of the same
land-cover class in the same month of (z − Ẑ), and similarly for the absolute deviation
devₜ = (Yₜ − μₘ) − peer median. Month s is *below expectation* if Rₛ ≤ −1 and devₛ ≤ −0.02 (a noise floor). An
*event onset* occurs at s if s is below expectation, s − 1 is not, the run lasts ≥ 6 months (longer than
one cropping season), at least 75 % of the first six run months are real (not gap-filled) observations,
and the mean NDVI loss relative to peers over those six months is ≥ 0.05. Applying the 0.05 magnitude
to the run rather than to every month matters in drylands: where vegetation is dormant for more than half
the year (steppe, Sahel), a per-month requirement makes a six-month run physically impossible — an
earlier variant produced zero events in the Mongolian site for this reason (Supplement S1).
At prediction month t, an eligible pixel (not below expectation at t) is labelled yₜ = 1 if an onset occurs
in (t, t + 6]. Labels are undefined where the record ends before t + 11 or fewer than 60 % of months
t + 1…t + 11 are observed. The same rule and thresholds are used in all nations; a 3 × 3 sensitivity grid
varies the threshold (−0.75, −1, −1.5) and the minimum run (4, 6, 9 months).

*Why not the simpler definition?* A first version (absolute residual, 4-month run) was rejected during
development (Supplement S1): in the Indian site 57 % of all onsets fell in five July/August months
(monsoon sowing, ≤ 32 % of pixels cloud-free), i.e. the label tracked landscape-wide phenology and cloud
artefacts, and models learned to recognise event *months* rather than at-risk *places*. The peer-relative,
6-month definition reduced that concentration and lowered cropland onset rates from 7.6 % to 0.5 % per
pixel-year.

### 3.5 Features
All features at t are computed from data ≤ t (verified by unit tests that perturb future values). Gap
filling for features is causal (carry-forward ≤ 2 months, with a "data age" feature). Groups (ablation
order): **A1 state** (NDVI, z, NDMI, NBR, BSI, season, land cover), **A2 change** (1/3/12-month
differences, 12/36-month slopes, negative-anomaly run length), **A3 climate** (§3.3 predictors),
**A4 residual** (R and its 3/6/12-month means, minimum, slope, run length, fraction below threshold),
**A5 resilience** (AC1 and variance of the high-passed residual over 12 and 24 months, their change,
months since the last dip, recovery fraction; MODIS 250 m anomaly, 60-month AC1 and variance, lagged 1
month), **A6 spatial context** (neighbourhood residual mean at 50 and 210 m, residual heterogeneity,
area-wide fraction below expectation, elevation, slope, surface-water occurrence, distance to river).

### 3.6 Model, calibration and abstention
A LightGBM classifier is trained with early stopping (on average precision only) on a validation set that
is new in both space and time. Because every pixel contributes ~40 strongly autocorrelated monthly rows,
trees easily memorise individual pixels (train AP 0.91 vs validation 0.05 with 31 leaves); we therefore
use deliberately small, heavily regularised trees: 7 leaves, ≥ 4000 rows per leaf, feature subsampling 0.4,
row subsampling 0.7, L2 = 50, extremely randomised split thresholds, learning rate 0.03, class weight
√(neg/pos) and area-balanced sample weights. Capacity is justified by a validation curve (§4). Scores are calibrated by isotonic
regression on a disjoint calibration set. A Mondrian (class-conditional) split-conformal predictor with
α = 0.10 converts calibrated probabilities into prediction sets; a set {0, 1} is reported as *abstain*.
The operating threshold maximises F1 on the calibration set.

### 3.7 Validation design
* **Temporal hold-out with embargo:** train t ≤ 2022-03, validation 2023-03…2023-12, test 2024-12…2025-10.
  The ≥ 11-month gaps equal the label look-ahead (H + min_run − 1), so no training label sees validation or
  test months.
* **Spatial hold-out:** 1 km blocks, deterministically assigned 60/20/20 to train/validation/test.
* **Primary test** = test period ∩ test blocks, evaluated once.
* **Leave-one-country-out (LOCO)** transfer.
* **Walk-forward retraining** (expanding window, yearly) as a model of continuous operational updating.
* **Ablation** A0–A6 on the same locked test set; A0 baselines: anomaly persistence, NDVI trend,
  residual rule; plus a Sentinel-only random forest.
* **Metrics:** PR-AUC (primary, imbalanced task), ROC-AUC, Brier score, expected calibration error,
  precision/recall/false-alarm rate at the operating threshold, lead time (months between the first
  warning and onset), conformal coverage and abstention rate. 95 % confidence intervals by cluster
  bootstrap over (area, block).
* **Over-/under-fitting diagnostics:** validation curve over model capacity, learning curve over training
  size, train–validation gap per ablation step.
* **Label corroboration:** for S2 event onsets vs. matched controls, the NDVI anomaly seen by Landsat 8/9
  (30 m) and MODIS (250 m) in months s…s + 3; AUC measures agreement.

### 3.9 Nonlinear-dynamics framework (feature group A9)
Land systems prone to degradation can possess alternative stable states separated by thresholds; as a
system approaches a fold bifurcation its deterministic restoring force weakens (critical slowing down).
Let $x_t$ be a pixel's peer-relative residual (§3.4), detrended with a 12-month trailing mean. We model its
local dynamics as a one-dimensional stochastic system

$$dx = f(x)\,dt + \sigma\,dW_t,\qquad f(x) = -V'(x),$$

and estimate, on trailing windows ending at the prediction month $t$ (strictly causal):

* **Recovery rate.** With exponentially weighted recursive least squares (forgetting factor $\ell=0.95$),
  $\hat\phi_t = S_{xy}(t)/S_{xx}(t)$, $S_{xy}(t)=\ell S_{xy}(t-1)+x_t x_{t-1}$, $S_{xx}(t)=\ell S_{xx}(t-1)+x_{t-1}^2$;
  the return rate $\lambda_t=-\ln|\hat\phi_t|$ tends to 0 at a critical transition.
* **Potential shape.** A Kramers–Moyal drift estimate $\Delta x_t = a_1 x_{t-1} + a_3 x_{t-1}^3 + \varepsilon_t$
  (48-month window) gives $V(x) = -\tfrac{a_1}{2}x^2 - \tfrac{a_3}{4}x^4$, the local curvature
  $\kappa = -(a_1 + 3a_3x_t^2)$, a bistability indicator $\mathbb{1}[a_1>0,\ a_3<0]$ (double well) and the
  noise-to-restoring ratio $\hat\sigma^2/\max(-a_1,\epsilon)$.
* **Higher-order and spectral signals.** Rolling skewness $m_3/m_2^{3/2}$, excess kurtosis $m_4/m_2^2-3$
  (36 months) and spectral reddening $\mathrm{Var}(\mathrm{MA}_6(x))/\mathrm{Var}(x)$.
* **Long memory.** The detrended-fluctuation exponent $\alpha$ from $F(s)\propto s^{\alpha}$,
  $s\in\{4,6,8,12\}$ months (48-month window).
* **Complexity.** Bandt–Pompe permutation entropy of order 3, $H=-\sum_i p_i\ln p_i/\ln 3!$.
* **Rain-use dynamics.** Rolling elasticity $b$ and coupling $R^2$ of the NDVI anomaly on the 3-month
  rainfall anomaly, and $\Delta b$ over 12 months (decoupling from rainfall).
* **Spatial signals.** Within 210 m windows: spatial skewness and a Moran-type autocorrelation
  $\mathrm{corr}(x_i, \bar x_{N(i)})$. Per 1 km block: vegetated fraction, largest-patch fraction and the
  exponent of the patch-size complementary distribution $P(S\ge s)\propto s^{-\beta}$ — the dryland
  degradation indicator of Kéfi et al. (2007).

Each estimator was verified on synthetic processes with known properties before use (moments vs. SciPy;
AR(1) coefficients 0.2/0.8 recovered; a simulated double-well $dx=(x-x^3)dt+\sigma dW$ classified as bistable
and a single well $dx=-x\,dt+\sigma dW$ not; DFA $\alpha\approx0.5$ for white noise and $>1.2$ for a random walk;
permutation entropy $\approx1$ for noise and 0 for a monotone series; rain elasticity $b=2$ recovered;
causality: perturbing future values leaves all indicators at $\le t$ unchanged).

### 3.10 Ecosystem structure-and-function indicators (feature group A8)
Following expert review, productivity loss is linked to its mechanisms. From the stored monthly composites
we reconstruct SWIR-1 as $B_{11} = B_8(1-\mathrm{NDMI})/(1+\mathrm{NDMI})$ with $B_8 = B_4(1+\mathrm{NDVI})/(1-\mathrm{NDVI})$
and flag open water by $\mathrm{MNDWI}=(G-B_{11})/(G+B_{11})>0$ or NDVI $<0$, and surface flooding of
vegetation by $\mathrm{LSWI}+0.05\ge\mathrm{NDVI}$ (Xiao et al. 2005). Features: pixel and 210 m water
frequency and its loss relative to 2017–2020 (stream/pond/wetland recession), paddy-flooding frequency
change (e.g. rice → dryland crops), dry-season (10th-percentile) greenness shift (evergreen or invasive woody
encroachment vs. loss of perennial cover), seasonal-amplitude and peak-timing change (life-form shift) and
30 m NDVI texture change (fragmentation). Every hotspot additionally receives a rule-based process
attribution (hydrological loss, river dynamics, paddy/wetland loss, evergreen encroachment, perennial-cover
loss, structure shift, failure to green up after a wet spell, post-drought decline).

### 3.8 Hydrological context (operational layer)
For each area, the HydroRIVERS reach with the largest mean discharge intersecting the area is the outlet;
its upstream network is traced through the river topology. GloFAS daily discharge is sampled at the
outlet and up to three large tributaries (grid cell snapped to match the HydroRIVERS long-term mean) and
summarised as 1984–2000 vs. 2016–present mean and low flow. Distance to river enters the model as a
feature; discharge is displayed for interpretation but is not a model input in v1.

---

## 4. Results
### 4.1 Data
The nine areas yield 3.06 million labelled pixel-month rows (Table 1). Event frequency differs by an order of
magnitude between landscapes: highest in Kenya, Spain and Brazil (≈ 0.05 onsets per pixel-year), lowest in
Mongolia (0.0004), where the homogeneous steppe moves as one and a peer-relative rule finds almost no local
declines. Climate conditioning passed the out-of-sample skill test (leave-one-year-out R² ≥ 0.05) for at
least one land-cover class in six areas and was rejected in Ethiopia, Brazil and Mongolia (Fig. 5). Every
composite is traceable to its source scenes (3 806 Sentinel-2 scenes); half required the −1000 BOA offset.

### 4.2 Which layers carry the signal? (ablation, Fig. 6)
On the locked test set (78 771 rows, base rate 0.026), models using Sentinel-2 state (A1, PR-AUC 0.030),
temporal change (A2, 0.033) and climate variables (A3, 0.034) barely exceed chance. Adding the
climate-conditioned, peer-relative residual (A4) raises PR-AUC to 0.093 (ROC-AUC 0.735), and resilience
indicators (A5) to 0.122 (0.765). Spatial context (A6, 0.117) adds no further skill. The best non-learning
baseline, a 3-month residual rule, scores 0.058; anomaly persistence 0.043; a Sentinel-only random forest
0.035; an NDVI trend rule is no better than chance (0.023).

### 4.3 Final model (Figs. 7, 8, 12, 13)
The calibrated model reaches PR-AUC 0.113 (95 % cluster-bootstrap CI 0.085–0.163) and ROC-AUC 0.762
(0.713–0.808), Brier score 0.024 and expected calibration error 0.009. At the operating threshold chosen on
calibration rows (p = 0.127) precision is 0.205, recall 0.201 and the false-alarm rate 2.1 %. Of 910 test
onsets, 31 % were warned at least one month ahead (median 2, mean 2.6 months; 23 events six months ahead).
The conformal layer abstains on 47.5 % of cases while attaining near-nominal class coverage (0.874 events,
0.900 non-events at α = 0.10); on the confident half ROC-AUC is 0.843 and 99.2 % of "no event" calls are
correct. The joint place-and-time hold-out is the hardest test: temporal-only and spatial-only hold-outs
give ROC-AUC 0.806 and 0.838. Skill is highest in shrubland and grassland (PR-AUC 0.22 and 0.19) and lowest
in cropland (0.073, 3.1× chance). Mean absolute SHAP values rank MODIS 5-year variance first (0.25), followed
by 24-month lag-1 autocorrelation (0.17) and the fraction of the last 12 months below expectation (0.14);
five of the nine most influential features are resilience indicators.

### 4.4 Over- and under-fitting (Fig. 9)
Increasing tree capacity from 7 to 255 leaves raises training AP from 0.17 to 0.44 while validation AP stays
at 0.13–0.15, i.e. additional capacity only memorises autocorrelated pixel histories. Conversely, test AP rises
monotonically with training data (0.074 at 5 % of pixels to 0.117 at 100 %) without saturating: the model is
data-limited rather than capacity-limited.

### 4.5 Generalisation across nations and through time (Figs. 10, 11)
Trained on eight nations and tested on the ninth, the model retains 2.4–9.3× lift (Australia 9.3×,
Ethiopia 8.2×, Senegal 7.8×, Kenya 4.4×, Spain 3.9×, India 3.7×, Nepal 3.5×, Brazil 2.4×; Mongolia has no test
events). In walk-forward retraining, test-year PR-AUC rises from 0.030 (2021; 23 k training rows) to 0.156
(2025; 1.02 M rows), supporting continuous retraining as Sentinel-2 history accumulates.

### 4.6 Robustness of the target definition (Fig. 17)
Across nine label definitions (threshold −0.75/−1/−1.5 × persistence 4/6/9 months) the model retains 2.7–5.0×
lift and ROC-AUC 0.70–0.80; prevalence varies from 0.3 % to 8.4 %.

### 4.7 Are the labels real? (Figs. 14, 18)
Landsat 8/9 — a different sensor, agency, overpass and cloud mask — sees lower NDVI at Sentinel-2-labelled
onsets than at matched controls in seven of nine areas (agreement AUC: Brazil 0.93, Australia 0.83, Spain
0.75, Kenya 0.73, Ethiopia 0.69, India 0.68, Nepal 0.61), but not in Mongolia (0.57) or Senegal (0.46).
MODIS (250 m) agrees only where events are large (Brazil, 0.75). The evidence gallery (Fig. 18) shows correct
one- to five-month-ahead warnings with before/after imagery: vegetation-cover loss on Kenyan rangeland and
Ethiopian hillslopes, and field-level management change in Brazil and India.

### 4.8 Operational product (Fig. 15; console screenshots in Supplement S3)
For September 2026 the system issues 60 warning hotspots and 32 confirmed active-decline sites across seven
areas; the Kenyan Marigat plains carry the highest current risk (425 ha above threshold). For each area the
console traces the upstream river network (HydroRIVERS) and compares 1984–2000 with 2016–present discharge
(e.g. −36 % mean flow at the western-Bahia outlet, consistent with reported irrigation withdrawals).

---

## 5. Discussion
**The early-warning signal is real but modest, and it lives in the residual and in resilience.** The central
question of this study — can degradation be anticipated before it is obvious? — receives a qualified yes. A
4.4-fold improvement over chance at a 2 % false-alarm rate, under a hold-out that is new in both place and
time, is useful for prioritising inspections, not for automated enforcement. The ablation is the most
informative result: neither spectral state nor raw climate predicts future decline, whereas the
climate-conditioned residual and resilience indicators do. This is the pattern expected from
critical-slowing-down theory, here tested as a forecasting hypothesis rather than assumed: variance and
autocorrelation of the residual carry information about future persistent decline. We do not claim that AC1
increases mark tipping points; we show that they improve held-out prediction.

**Weather data are needed only through the residual.** Climate predictors added directly (A3) bring no skill,
and the climate model itself is retained in only six of nine areas. The large gain comes from removing
landscape-wide variability — climatic or otherwise — by comparing each pixel with its peers. Operational
systems can therefore rely on a small set of reanalysis variables, applied only where demonstrably skilful.

**Label design dominated the outcome.** Two earlier label definitions were rejected for documented reasons:
one tracked monsoon timing and cloud artefacts (57 % of Indian events in five July/August months), the other
was blind in dormant ecosystems (zero events in Mongolia). Both would have produced plausible-looking but
meaningless accuracy. We recommend that EO degradation studies report label diagnostics — temporal
concentration of events, rates by land cover, and independent-sensor agreement — alongside accuracy.

**Calibration and abstention make the warnings usable.** Probabilities are well calibrated (ECE 0.009), so a
0.3 warning means roughly a 30 % chance. Abstention on half of the cases is the honest price of moderate
discrimination at 2.6 % prevalence; it turns the model into a triage tool that confidently clears much of
the landscape (NPV 99.2 %) and routes uncertain sites to field teams.

**Where the system should not yet be trusted.** Cropland (crop-management changes resemble degradation),
homogeneous rangeland (Mongolia; peer-relative labels cannot see uniform decline) and the Sahel site (labels
not corroborated by Landsat) need additional information — crop calendars, absolute-trend indicators and
field data — before operational use.

### 5.1 Limitations
1. Labels are EO proxies, not field observations: persistent unexplained NDVI decline also captures land-use
   change (clearing, fallowing), fire and harvest timing. Landsat agreement supports their physical reality
   in seven areas, not that they constitute *degradation* in a land-management sense.
2. The Sentinel-2 baseline spans four years (2017–2020); degradation already under way then depresses μₘ.
3. Climate predictors are area-level (≈ 9–25 km); ERA5 precipitation is weaker than gauge-blended products
   over convective tropics.
4. One 5 km area per nation: LOCO measures transfer to a new landscape, not to new places within a nation.
5. Interpolated label months use future observations (≤ 2 months) — legitimate for labels only.
6. Peer-relative labels cannot detect degradation affecting a whole land-cover class uniformly.
7. The test period spans 11 months (bounded by the 11-month label look-ahead), so intervals are wide.
8. During development, test rows of two areas were viewed in debugging runs (Supplement S1); all design
   decisions were taken on validation data or model-free label diagnostics.
9. Discharge is displayed for interpretation but is not a model input; GloFAS cannot resolve small reaches.

---

## 6. Conclusion
CARE-EW turns open Earth-observation data into calibrated, explainable six-month warnings of persistent,
climate-unexplained vegetation decline at 10 m resolution. Across nine nations it achieves a 4.4-fold lift over
chance at a 2 % false-alarm rate on a hold-out new in both space and time, transfers to unseen nations, and
improves steadily as the Sentinel-2 record lengthens. Its predictive power comes from the climate-conditioned
residual and from resilience indicators, not from spectral state or raw climate. Equally important for
operational adoption are the negative results: where labels cannot be independently corroborated, or where
land management mimics degradation, the system says so. We release the full pipeline, labels, a log of every
design decision, and a web console intended for prioritising field inspection by land-management agencies.

## Data and code availability
Code, configuration, labels and the web console: ⟨repository⟩. All inputs are open (Table 2). The complete
development record, including rejected label definitions and all issues encountered, is Supplement S1
(`docs/PROJECT_LOG.md`); per-month scene provenance is Supplement S2; console screenshots are Supplement S3.

## References (to be verified against the final literature search)
* Cherlet M. et al. (2018) *World Atlas of Desertification*, 3rd ed. Publications Office of the EU.
* Sims N.C. et al. (2021) *Good Practice Guidance, SDG Indicator 15.3.1*, v2. UNCCD.
* Prince S.D., Becker-Reshef I., Rishmawi K. (2009) Detection and mapping of long-term land degradation using local net production scaling: application to Zimbabwe. *Remote Sens. Environ.* 113, 1046–1057.
* Wessels K.J. et al. (2007) Can human-induced land degradation be distinguished from the effects of rainfall variability? *J. Arid Environ.* 68, 271–297. (RESTREND)
* Scheffer M. et al. (2009) Early-warning signals for critical transitions. *Nature* 461, 53–59.
* Dakos V. et al. (2012) Methods for detecting early warnings of critical transitions in time series. *PLoS ONE* 7, e41010.
* Verbesselt J. et al. (2016) Remotely sensed resilience of tropical forests. *Nat. Clim. Change* 6, 1028–1031.
* Smith T., Traxl D., Boers N. (2022) Empirical evidence for recent global shifts in vegetation resilience. *Nat. Clim. Change* 12, 477–484.
* Roberts D.R. et al. (2017) Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography* 40, 913–929.
* Ploton P. et al. (2020) Spatial validation reveals poor predictive performance of large-scale ecological mapping models. *Nat. Commun.* 11, 4540.
* Ke G. et al. (2017) LightGBM: A highly efficient gradient boosting decision tree. *NeurIPS*.
* Zadrozny B., Elkan C. (2002) Transforming classifier scores into accurate multiclass probability estimates. *KDD*.
* Vovk V., Gammerman A., Shafer G. (2005) *Algorithmic Learning in a Random World*. Springer.
* Angelopoulos A.N., Bates S. (2023) Conformal prediction: a gentle introduction. *Found. Trends ML* 16, 494–591.
* Drusch M. et al. (2012) Sentinel-2: ESA's optical high-resolution mission. *Remote Sens. Environ.* 120, 25–36.
* Muñoz-Sabater J. et al. (2021) ERA5-Land. *Earth Syst. Sci. Data* 13, 4349–4383.
* Lehner B., Grill G. (2013) Global river hydrography and network routing (HydroSHEDS). *Hydrol. Process.* 27, 2171–2186.
* Harrigan S. et al. (2020) GloFAS-ERA5 operational global river discharge reanalysis 1979–present. *Earth Syst. Sci. Data* 12, 2043–2060.
* Zanaga D. et al. (2022) ESA WorldCover 10 m 2021 v200. Zenodo.
* Kéfi S. et al. (2007) Spatial vegetation patterns and imminent desertification in Mediterranean arid ecosystems. *Nature* 449, 213–217.
* Rietkerk M. et al. (2004) Self-organized patchiness and catastrophic shifts in ecosystems. *Science* 305, 1926–1929.
* Bandt C., Pompe B. (2002) Permutation entropy: a natural complexity measure for time series. *Phys. Rev. Lett.* 88, 174102.
* Peng C.-K. et al. (1994) Mosaic organization of DNA nucleotides (detrended fluctuation analysis). *Phys. Rev. E* 49, 1685.
* Livina V.N., Lenton T.M. (2007) A modified method for detecting incipient bifurcations in a dynamical system. *Geophys. Res. Lett.* 34, L03712.
* Kéfi S. et al. (2014) Early warning signals of ecological transitions: methods for spatial patterns. *PLoS ONE* 9, e92097.
* Xiao X. et al. (2005) Mapping paddy rice agriculture in southern China using multi-temporal MODIS images. *Remote Sens. Environ.* 95, 480–492.
* Lundberg S.M., Lee S.-I. (2017) A unified approach to interpreting model predictions. *NeurIPS*.
* Pekel J.-F. et al. (2016) High-resolution mapping of global surface water. *Nature* 540, 418–422.
