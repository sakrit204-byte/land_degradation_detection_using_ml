# CARE-EW accuracy report

Generated from `outputs/results/metrics.json` (run 2026-10-21 03:29; 4,294,330 pixel-months, 17 study areas). Target: onset of persistent degradation within the next 6 months (label v3, PROJECT_LOG §5). Test = months ≥ 2024-12 on spatially held-out 1 km blocks, never used for any choice.

**How to read.** Events are rare (2.5 % of test pixel-months), so ROC-AUC alone flatters any model; PR-AUC and its lift over chance are the honest headline. Precision/recall/false-alarm use the decision threshold fixed on the calibration set.

## 1. Operational model (feature set A6_spatial)

| | PR-AUC | lift ×chance | ROC-AUC | precision | recall | false-alarm | base rate | n |
|---|---|---|---|---|---|---|---|---|
| **Test set** | 0.144 | 5.7 | 0.805 | 0.217 | 0.289 | 2.7 % | 0.0252 | 132230 |
| Test, confident pixels only (conformal) | 0.200 | 6.3 | 0.877 | 0.217 | 0.480 | 5.7 % | 0.0317 | 63369 |
| Future months, training blocks | 0.154 | 6.3 | 0.812 | 0.229 | 0.303 | 2.6 % | 0.0245 | 591768 |
| Training months, unseen blocks | 0.118 | 5.7 | 0.787 | 0.233 | 0.146 | 1.0 % | 0.0209 | 261960 |

* 95 % cluster-bootstrap CI: PR-AUC 0.112–0.184, ROC-AUC 0.766–0.838
* Calibration: ECE 0.0025, Brier 0.0228 (a stated 10 % risk ≈ 10 % observed)
* Conformal (α = 0.1): abstains on 52.1 %; coverage events 94.0 %, non-events 87.5 %; when it says *no event* it is right 99.6 %; when it says *event*, 10.1 %
* The raw A6 model scores test PR-AUC 0.152; isotonic calibration merges near-equal scores into ties, which costs a little ranking precision in exchange for trustworthy probabilities (the operational choice).
* Lead time: 41.3 % of 1444 test onsets warned ≥ 1 month ahead; median lead 3 months (histogram months→onsets: {'0': 847, '1': 186, '2': 97, '3': 92, '4': 72, '5': 80, '6': 70})

## 2. Per study area (operational model, test set)

| site | landscape | PR-AUC | lift | ROC-AUC | precision | recall | false-alarm | base rate | n |
|---|---|---|---|---|---|---|---|---|---|
| AUS_murraydarling | Semi-arid woodland | 0.156 | 15.1 | 0.939 | 0.102 | 0.744 | 6.8 % | 0.0103 | 7558 |
| BRA_matopiba | Cerrado cropland frontier | 0.051 | 2.5 | 0.591 | 0.088 | 0.190 | 4.2 % | 0.0206 | 9190 |
| ESP_murcia | Mediterranean dryland | 0.308 | 4.6 | 0.791 | 0.411 | 0.296 | 3.0 % | 0.0663 | 10585 |
| ETH_tigray | Highland cropland / shrub | 0.242 | 9.2 | 0.868 | 0.301 | 0.446 | 2.8 % | 0.0262 | 14116 |
| IND_banni | Arid grassland / rangeland | 0.213 | 2.0 | 0.692 | 0.387 | 0.139 | 2.6 % | 0.1056 | 5038 |
| IND_bundelkhand | Semi-arid Indian cropland | 0.076 | 5.9 | 0.757 | 0.138 | 0.192 | 1.6 % | 0.0130 | 9606 |
| IND_chambal | Semi-arid Indian cropland | 0.254 | 19.5 | 0.873 | 0.373 | 0.318 | 0.7 % | 0.0130 | 9886 |
| IND_jharia | Mining landscape | 0.005 | 2.7 | 0.770 | 0.005 | 0.059 | 2.5 % | 0.0020 | 8530 |
| IND_thar | Semi-arid Indian cropland | 0.115 | 3.9 | 0.764 | 0.164 | 0.203 | 3.2 % | 0.0298 | 8252 |
| KEN_baringo | Arid grassland / rangeland | 0.207 | 9.3 | 0.829 | 0.159 | 0.602 | 7.2 % | 0.0222 | 8378 |
| MNG_steppe | Arid grassland / rangeland | – | – | – | – | – | – | 0.0000 | 2314 |
| NPL_chure | Himalayan foothill forest | 0.155 | 8.6 | 0.827 | 0.315 | 0.204 | 0.8 % | 0.0180 | 10629 |
| NPL_chure_dang | Himalayan foothill forest | 0.043 | 6.8 | 0.819 | 0.143 | 0.109 | 0.4 % | 0.0063 | 7291 |
| NPL_chure_sarlahi | Himalayan foothill forest | 0.198 | 8.5 | 0.853 | 0.351 | 0.260 | 1.1 % | 0.0233 | 6430 |
| NPL_kavre | Himalayan foothill forest | 0.240 | 9.2 | 0.915 | 0.240 | 0.510 | 4.3 % | 0.0261 | 5706 |
| NPL_surkhet | Himalayan foothill forest | 0.157 | 11.4 | 0.667 | 0.273 | 0.188 | 0.7 % | 0.0138 | 2326 |
| SEN_ferlo | Arid grassland / rangeland | 0.239 | 8.3 | 0.892 | 0.302 | 0.157 | 1.1 % | 0.0289 | 6395 |

## 3. Per land cover (test set)

| | PR-AUC | lift ×chance | ROC-AUC | precision | recall | false-alarm | base rate | n |
|---|---|---|---|---|---|---|---|---|
| tree | 0.110 | 8.8 | 0.812 | 0.164 | 0.360 | 2.3 % | 0.0125 | 39947 |
| shrub | 0.275 | 6.8 | 0.858 | 0.329 | 0.422 | 3.6 % | 0.0404 | 11093 |
| grass | 0.218 | 6.6 | 0.870 | 0.257 | 0.384 | 3.8 % | 0.0329 | 25593 |
| crop | 0.096 | 3.5 | 0.743 | 0.184 | 0.169 | 2.1 % | 0.0274 | 51199 |
| bare/sparse | 0.123 | 4.1 | 0.755 | 0.158 | 0.250 | 4.1 % | 0.0300 | 4398 |

## 4. Feature groups (cumulative ablation; choice by VALIDATION AP only)

| model | features | val AP | test PR-AUC | lift | test ROC | train AP | train−val gap | trees |
|---|---|---|---|---|---|---|---|---|
| A0_persistence(-z_mean3) | – | – | 0.036 | 1.4 | 0.592 | – | – | – |
| A0_ndvi_trend(-slope12) | – | – | 0.023 | 0.9 | 0.495 | – | – | – |
| A0_residual_rule(-R_mean3) | – | – | 0.055 | 2.2 | 0.671 | – | – | – |
| RF_sentinel_only(A1+A2) | – | – | 0.044 | 1.8 | 0.622 | – | – | – |
| LGB_A1_state | 12 | 0.038 | 0.032 | 1.3 | 0.573 | 0.091 | 0.054 | 972 |
| LGB_A2_change | 23 | 0.053 | 0.036 | 1.4 | 0.561 | 0.094 | 0.041 | 110 |
| LGB_A3_climate | 31 | 0.050 | 0.034 | 1.4 | 0.575 | 0.133 | 0.083 | 157 |
| LGB_A4_residual | 44 | 0.140 | 0.131 | 5.2 | 0.783 | 0.088 | -0.052 | 27 |
| LGB_A5_resilience | 55 | 0.128 | 0.143 | 5.7 | 0.797 | 0.150 | 0.022 | 99 |
| LGB_A6_spatial | 64 | 0.138 | 0.152 | 6.1 | 0.805 | 0.127 | -0.012 | 41 |
| LGB_A8_ecofunc | 77 | 0.132 | 0.139 | 5.5 | 0.801 | 0.153 | 0.021 | 55 |
| LGB_A9_nonlinear | 96 | 0.138 | 0.147 | 5.8 | 0.808 | 0.164 | 0.026 | 97 |

### 4b. Texture (A10a) and red-edge (A10b) test — D-023

| variant | features | val AP | test PR-AUC | CI | test ROC | lift | gain share of new features | top new features |
|---|---|---|---|---|---|---|---|---|
| A6_spatial | 64 | 0.1384 | 0.152 | 0.119–0.192 | 0.805 | 6.1 | 0.0 % | – |
| A6+A10a_texture | 82 | 0.1341 | 0.154 | 0.121–0.202 | 0.811 | 6.1 | 20.5 % | tx_sd2712, tx_sd312, tx_hom12, tx_ent_chg, tx_ent12, tx_hom_chg |
| A6+A10b_rededge | 76 | 0.1370 | 0.146 | 0.119–0.181 | 0.789 | 5.8 | 9.8 % | re_ndre_m12, re_ireci, re_ndre_d3, re_ndre, re_ndre_anom, re_cire |
| A6+A10a+A10b | 94 | 0.1438 | 0.151 | 0.117–0.193 | 0.792 | 6.0 | 22.4 % | tx_sd2712, re_cire_m12, tx_ent12, tx_ndmi_sd12, tx_hom12, re_ndre_m12 |

**Decision (pre-registered):** A6 val AP 0.1384; best A6+A10a+A10b 0.1438; literal rule result → **A6+A10a+A10b** (see seed check below).

Within-site univariate AUC of each new feature on validation rows (0.5 = no signal; below 0.5 = signal with inverted sign):

| feature | AUC | strength |
|---|---|---|
| tx_sd312 | 0.616 | 0.116 |
| tx_sd2712 | 0.599 | 0.099 |
| tx_ndmi_sd12 | 0.592 | 0.092 |
| tx_con12 | 0.591 | 0.091 |
| tx_bsi_sd12 | 0.588 | 0.088 |
| tx_ent12 | 0.576 | 0.076 |
| tx_hom12 | 0.428 | 0.072 |
| re_ndre_anom | 0.430 | 0.070 |
| tx_lsr12 | 0.437 | 0.063 |
| re_cire_anom | 0.440 | 0.060 |
| tx_sd3_chg | 0.547 | 0.047 |
| tx_con_chg | 0.543 | 0.043 |
| tx_cor12 | 0.541 | 0.041 |
| tx_hom_chg | 0.460 | 0.040 |
| tx_ent_chg | 0.535 | 0.035 |
| re_ireci_d3 | 0.535 | 0.035 |
| re_cire_m12 | 0.468 | 0.032 |
| re_ndre_d3 | 0.527 | 0.027 |
| tx_sd27_chg | 0.525 | 0.025 |
| re_ndre_m12 | 0.475 | 0.025 |
| re_cire_d3 | 0.524 | 0.024 |
| re_ireci_m12 | 0.478 | 0.022 |
| tx_lsr_chg | 0.481 | 0.019 |
| re_ireci_anom | 0.481 | 0.019 |
| re_ireci | 0.516 | 0.016 |
| tx_bsi_sd_chg | 0.490 | 0.010 |
| tx_ndmi_sd_chg | 0.509 | 0.009 |
| tx_cor_chg | 0.507 | 0.007 |
| re_cire | 0.493 | 0.007 |
| re_ndre | 0.494 | 0.006 |
**Seed stability check (validation only, 5 seeds; added after test numbers were seen):** A6 0.1397 ± 0.0059, A6+A10a+A10b 0.1427 ± 0.0066; mean gain 0.0031 < 0.005 → the pass is within seed noise; **A6 stays operational** (PROJECT_LOG R-017).


### 4c. More training pixels from the same sites (D-024)

| training pixels per site | train rows | val AP | test PR-AUC | CI | test ROC |
|---|---|---|---|---|---|
| 5000 | 800,784 | 0.1220 | 0.165 | 0.130–0.212 | 0.812 |
| 10000 | 1,595,949 | 0.1196 | 0.171 | 0.129–0.225 | 0.812 |

Decision: **5000_px_per_site** (validation did not improve; evaluation rows identical for both).


## 5. Individual predictors (mean |SHAP| share, operational model, top 20)

| rank | feature | share |
|---|---|---|
| 1 | modis_var_60 | 13.0 % |
| 2 | R_fracbelow12 | 9.0 % |
| 3 | ac1_24 | 8.1 % |
| 4 | ac1_trend | 8.0 % |
| 5 | R_mean6 | 6.6 % |
| 6 | var_24 | 5.8 % |
| 7 | modis_ac1_60 | 5.4 % |
| 8 | ndvi_slope36 | 5.3 % |
| 9 | R_min6 | 4.1 % |
| 10 | R_negrun | 2.7 % |
| 11 | sigma | 2.2 % |
| 12 | landcover | 2.1 % |
| 13 | R_mean3 | 1.8 % |
| 14 | d_ndvi_12 | 1.7 % |
| 15 | R_mean12 | 1.7 % |
| 16 | d_ndvi_3 | 1.6 % |
| 17 | ac1_12 | 1.6 % |
| 18 | R_slope12 | 1.6 % |
| 19 | ndvi_dev_rel | 1.6 % |
| 20 | dist_river_km | 1.6 % |

## 6. Transfer to places the model never saw

### Leave one country out

| | PR-AUC | lift ×chance | ROC-AUC | precision | recall | false-alarm | base rate | n |
|---|---|---|---|---|---|---|---|---|
| Australia | 0.198 | 13.8 | 0.922 | – | – | – | 0.0143 | 47236 |
| Brazil | 0.103 | 2.3 | 0.642 | – | – | – | 0.0443 | 39863 |
| Ethiopia | 0.252 | 10.2 | 0.882 | – | – | – | 0.0247 | 43302 |
| India | 0.122 | 4.1 | 0.717 | – | – | – | 0.0296 | 199748 |
| Kenya | 0.238 | 7.0 | 0.835 | – | – | – | 0.0339 | 40514 |
| Mongolia | – | – | – | – | – | – | 0.0000 | 49171 |
| Nepal | 0.104 | 6.2 | 0.771 | – | – | – | 0.0167 | 214841 |
| Senegal | 0.271 | 9.8 | 0.865 | – | – | – | 0.0276 | 46979 |
| Spain | 0.236 | 4.6 | 0.754 | – | – | – | 0.0511 | 42344 |

### Leave one site out (landscape type known from other sites?)

| site | landscape | same type in training | PR-AUC | lift | ROC-AUC | n |
|---|---|---|---|---|---|---|
| MNG_steppe | Arid grassland / rangeland | no | – | – | – | 49171 |
| IND_banni | Arid grassland / rangeland | yes | 0.215 | 2.5 | 0.678 | 41344 |
| KEN_baringo | Arid grassland / rangeland | yes | 0.238 | 7.0 | 0.835 | 40514 |
| SEN_ferlo | Arid grassland / rangeland | yes | 0.271 | 9.8 | 0.865 | 46979 |
| BRA_matopiba | Cerrado cropland frontier | no | 0.103 | 2.3 | 0.642 | 39863 |
| ETH_tigray | Highland cropland / shrub | no | 0.252 | 10.2 | 0.882 | 43302 |
| NPL_chure | Himalayan foothill forest | yes | 0.120 | 8.2 | 0.804 | 43915 |
| NPL_chure_dang | Himalayan foothill forest | yes | 0.080 | 9.9 | 0.806 | 45121 |
| NPL_chure_sarlahi | Himalayan foothill forest | yes | 0.217 | 11.2 | 0.823 | 42407 |
| NPL_kavre | Himalayan foothill forest | yes | 0.283 | 9.3 | 0.874 | 39070 |
| NPL_surkhet | Himalayan foothill forest | yes | 0.085 | 6.7 | 0.766 | 44328 |
| ESP_murcia | Mediterranean dryland | no | 0.236 | 4.6 | 0.754 | 42344 |
| IND_jharia | Mining landscape | no | 0.028 | 3.8 | 0.693 | 35851 |
| IND_bundelkhand | Semi-arid Indian cropland | yes | 0.088 | 5.7 | 0.726 | 41001 |
| IND_chambal | Semi-arid Indian cropland | yes | 0.157 | 15.6 | 0.788 | 41088 |
| IND_thar | Semi-arid Indian cropland | yes | 0.127 | 4.7 | 0.757 | 40464 |
| AUS_murraydarling | Semi-arid woodland | no | 0.198 | 13.8 | 0.922 | 47236 |

## 7. Stability over time (walk-forward: train only on the past, test the next year)

| | PR-AUC | lift ×chance | ROC-AUC | precision | recall | false-alarm | base rate | n |
|---|---|---|---|---|---|---|---|---|
| 2021 | 0.034 | 1.1 | 0.527 | – | – | – | 0.0318 | 76840 |
| 2022 | 0.028 | 1.0 | 0.500 | – | – | – | 0.0271 | 131571 |
| 2023 | 0.072 | 3.1 | 0.732 | – | – | – | 0.0232 | 146414 |
| 2024 | 0.140 | 5.1 | 0.748 | – | – | – | 0.0272 | 147069 |
| 2025 | 0.179 | 6.8 | 0.823 | – | – | – | 0.0263 | 119773 |

## 8. Over/under-fitting checks

### Model complexity (validation curve)

| leaves | min child | trees | train AP | val AP |
|---|---|---|---|---|
| 3 | 8000 | 124 | 0.115 | 0.145 |
| 7 | 4000 | 41 | 0.127 | 0.138 |
| 15 | 2000 | 34 | 0.140 | 0.132 |
| 31 | 1000 | 14 | 0.118 | 0.136 |
| 63 | 400 | 24 | 0.140 | 0.146 |
| 127 | 100 | 14 | 0.121 | 0.142 |
| 255 | 20 | 14 | 0.124 | 0.139 |

### Learning curve (share of training pixels)

| share | rows | train AP | val AP | test AP |
|---|---|---|---|---|
| 5.0 % | 39,774 | 0.175 | 0.086 | 0.068 |
| 10.0 % | 79,721 | 0.159 | 0.113 | 0.102 |
| 25.0 % | 199,879 | 0.162 | 0.132 | 0.127 |
| 50.0 % | 399,547 | 0.110 | 0.141 | 0.146 |
| 100.0 % | 800,784 | 0.127 | 0.138 | 0.152 |

## 9. Robustness to the label definition (9 alternative definitions)

| residual threshold | min run (mo) | event rate | PR-AUC | lift | ROC-AUC |
|---|---|---|---|---|---|
| -0.75 | 4 | 8.5 % | 0.246 | 2.9 | 0.744 |
| -0.75 | 6 | 3.2 % | 0.152 | 4.8 | 0.779 |
| -0.75 | 9 | 1.1 % | 0.058 | 5.0 | 0.822 |
| -1.0 | 4 | 7.0 % | 0.245 | 3.5 | 0.771 |
| -1.0 | 6 | 2.5 % | 0.148 | 5.9 | 0.799 |
| -1.0 | 9 | 0.9 % | 0.057 | 6.2 | 0.814 |
| -1.5 | 4 | 3.9 % | 0.194 | 4.9 | 0.798 |
| -1.5 | 6 | 1.3 % | 0.087 | 6.6 | 0.770 |
| -1.5 | 9 | 0.4 % | 0.026 | 6.6 | 0.782 |

## 10. Independent checks of the labels

Do pixels labelled as degradation onsets also look degraded to OTHER sensors? (AUC 0.5 = no agreement)

| site | Landsat 30 m AUC | Landsat: event / control below −1 sd | MODIS 250 m AUC |
|---|---|---|---|
| NPL_chure | 0.614 | 18.3 % / 7.4 % | 0.492 |
| IND_bundelkhand | 0.679 | 16.8 % / 6.9 % | 0.534 |
| ETH_tigray | 0.686 | 37.3 % / 18.7 % | 0.576 |
| KEN_baringo | 0.733 | 63.8 % / 31.6 % | 0.522 |
| SEN_ferlo | 0.464 | 1.8 % / 1.2 % | 0.568 |
| ESP_murcia | 0.747 | 64.8 % / 28.1 % | 0.524 |
| BRA_matopiba | 0.931 | 93.6 % / 32.4 % | 0.745 |
| MNG_steppe | 0.566 | 17.9 % / 6.7 % | 0.480 |
| AUS_murraydarling | 0.830 | 2.2 % / 0.0 % | 0.527 |
| NPL_chure_dang | – | – / – | 0.564 |
| NPL_chure_sarlahi | – | – / – | 0.550 |
| NPL_kavre | – | – / – | 0.646 |
| NPL_surkhet | – | – / – | 0.563 |
| IND_banni | – | – / – | 0.625 |
| IND_jharia | – | – / – | 0.651 |
| IND_chambal | – | – / – | 0.491 |
| IND_thar | – | – / – | 0.510 |

**Brazil vs official PRODES/DETER clearing polygons:** 94.7 % of officially cleared pixels carry an onset label (background 6.2 %); warning AUC before clearing 0.448 — sudden clearing is detected, not forecast.

## 11. Current predictions (latest month, all areas)

Latest month 2026-09. High = risk above the calibrated threshold; abstain = conformal 'uncertain'; active = already below expectation.

| area | country | mean risk | high (ha) | uncertain (ha) | active decline (ha) | hotspots | NDVI trend /yr | main hotspot causes |
|---|---|---|---|---|---|---|---|---|
| NPL_chure | Nepal | 0.0139 | 18.6 | 925.1 | 535.0 | 11 | 0.0081 | other 7, river_dynamics 2, perennial_loss 1 |
| IND_bundelkhand | India | 0.0169 | 32.9 | 857.8 | 988.4 | 10 | 0.0140 | structure_shift 7, other 3 |
| ETH_tigray | Ethiopia | 0.0233 | 47.3 | 1094.5 | 897.9 | 10 | 0.0028 | post_drought 10 |
| KEN_baringo | Kenya | 0.0616 | 203.7 | 909.5 | 538.7 | 18 | 0.0023 | post_drought 15, perennial_loss 8, structure_shift 4 |
| SEN_ferlo | Senegal | 0.0142 | 25.3 | 751.4 | 855.0 | 10 | 0.0025 | other 6, post_drought 4 |
| ESP_murcia | Spain | 0.0449 | 181.4 | 1318.8 | 349.3 | 18 | 0.0059 | other 10, rain_use_loss 4, perennial_loss 3 |
| BRA_matopiba | Brazil | 0.0355 | 138.9 | 913.2 | 249.7 | 18 | 0.0026 | other 11, perennial_loss 7, structure_shift 2 |
| MNG_steppe | Mongolia | 0.0071 | 0.5 | 518.8 | 576.1 | 0 | -0.0018 | – |
| AUS_murraydarling | Australia | 0.0206 | 46.4 | 1085.1 | 577.9 | 16 | 0.0027 | rain_use_loss 11, post_drought 5 |
| NPL_chure_dang | Nepal | 0.0198 | 10.5 | 589.8 | 1492.4 | 10 | 0.0101 | other 10 |
| NPL_chure_sarlahi | Nepal | 0.0144 | 24.9 | 857.6 | 487.4 | 13 | 0.0041 | post_drought 12, perennial_loss 7, structure_shift 2 |
| NPL_kavre | Nepal | 0.0189 | 53.3 | 901.5 | 665.1 | 17 | -0.0001 | post_drought 10, perennial_loss 10, rain_use_loss 6 |
| NPL_surkhet | Nepal | 0.0168 | 24.8 | 837.8 | 463.6 | 12 | 0.0026 | post_drought 11, perennial_loss 7, structure_shift 2 |
| IND_banni | India | 0.0436 | 163.3 | 1106.2 | 909.2 | 13 | 0.0135 | other 12, structure_shift 1, rain_use_loss 1 |
| IND_jharia | India | 0.0200 | 27.5 | 339.7 | 464.0 | 14 | 0.0084 | other 5, river_dynamics 4, perennial_loss 3 |
| IND_chambal | India | 0.0129 | 8.5 | 874.7 | 732.1 | 10 | 0.0043 | other 10 |
| IND_thar | India | 0.0213 | 28.5 | 1240.3 | 856.1 | 10 | 0.0012 | structure_shift 7, other 3 |
| USR_My_area_3106 | User area | 0.0132 | 14.6 | 1141.5 | 314.9 | 18 | 0.0067 | other 9, river_dynamics 7, rain_use_loss 5 |
| USR_My_area_8b6b | User area | 0.0292 | 60.2 | 1113.8 | 626.4 | 15 | 0.0016 | post_drought 10, perennial_loss 5, river_dynamics 3 |
| USR_hilly_test_861e | User area | 0.0424 | 122.2 | 966.5 | 807.3 | 12 | 0.0006 | post_drought 10, perennial_loss 2, structure_shift 1 |
| USR_My_area_a348 | User area | 0.0182 | 41.3 | 918.3 | 658.9 | 18 | 0.0011 | perennial_loss 15, post_drought 12, structure_shift 4 |

All hotspot attributions: post_drought 105, other 87, perennial_loss 71, structure_shift 37, rain_use_loss 33, river_dynamics 20, water_loss 2

## 12. Limits (see PROJECT_LOG §11)

* Labels are satellite-derived (no field plots); the Brazil and Landsat checks are the only independent references.
* Precision ≈ 0.2 at the operating threshold: about 1 in 5 warnings becomes a labelled onset within 6 months.
* Humid tropical forest, cold steppe and mining landscapes have no training sibling: indicative only.
