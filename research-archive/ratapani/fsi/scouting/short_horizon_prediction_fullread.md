# Short-horizon prediction: full-text reading of the key sources

Companion to `short_horizon_prediction.md`, 14 Oct 2026. For each source, I read the paper itself, extracted the parameters we can copy, checked the numbers the earlier note quotes, and wrote one concrete action.

**Context.** We predict first-burn cell-days 1-2 days ahead, scored as recall at 5 picks per beat per day. The current LightGBM gets about 29.5 %, against 16.6 % for random picks.

**Labels.** [found] means the paper says it. [inference] means it is my reading of how it applies to us. Expected effects are my guesses, in recall points at 5 picks per beat.

**Reading status, 12 sources.**
- **Full text (10):** CrimeRank (Mohler et al. 2020); SpatialRank (NeurIPS 2023); PAWS (Xu et al. 2020); Song, Raskutti & Willett 2021; Xu et al. wildfire Hawkes (arXiv 2207.13250); Galicia point patterns (Marey-Pérez et al. 2023); Di Giuseppe et al. NHESS 2020; Bekar et al. 2020; Phelps, Lizotte & Woolford (arXiv 2412.16209); the Bogotá ETAS deployment (arXiv 1811.12880).
- **Full HTML text without supplements (2):** Yang & Woolford 2026 (the first 100k of about 114k characters, which covers methods and results); Phelps & Woolford 2021 (the first 100k of about 132k characters; the values in Table 2 were not in the HTML).
- **No India daily paper with features and ablations was found.** Details are in section 11.

---

## 1. Mohler, Porter, Carter & LaFree 2020, "Learning to rank spatio-temporal event hotspots" (CrimeRank). Crime Science 9:3

Full text (NSF accepted manuscript, https://par.nsf.gov/servlets/purl/10172953). Licence CC BY. Code: https://github.com/gomohler/crimerank

**Method [found]**
- The query is one time window, and each document is a cell. The label is the count in the next window.
- The features are deliberately "univariate": the event counts in the cell over each of the last 52 weeks (52 features). Random forest, GLM, GBM-NDCG and CrimeRank all get the same features.
- The loss is PAI@k, which is recall@k divided by area. It is optimised with a LambdaMART-style pseudo-gradient. The pair weight Δ_kt(i,j) = c·(y_i − y_j)/N_t applies only when one cell of the pair is inside the top k and the other is outside it. Pairs that are both inside or both outside get zero weight.
- The gradient for each cell is the sum over pairs of |Δ|/(1+e^(s_i−s_j)). A regression tree is fitted to it, using stochastic gradient boosting with 1/4 subsampling per tree and a maximum leaf size of 500. On NIJ the leaf size was 100 for street crime and 50 for all calls for service.
- Training converged within about 200 iterations (Fig. 2).
- **Off-grid step.** The trained model scores g×g shifted copies of the grid (g = 10 works well). A greedy sort then picks the k highest-scoring cells that do not overlap.

**Results, Table 1 (PAI at k = 200 cells of 150 m, about 0.4 % of the city; weekly windows) [found]**

| Data | CrimeRank | RF | GLM | Hawkes | CNN-LSTM | KDE | GBM-NDCG |
|---|---|---|---|---|---|---|---|
| Indianapolis burglary | 41.56 | 28.61 | 25.52 | 30.41 | 29.14 | 3.47 | 16.31 |
| Indianapolis robbery | 88.71 | 53.61 | 69.68 | 68.32 | 32.68 | 10.46 | 46.48 |
| Traffic crash | 60.56 | 54.37 | 54.63 | 55.13 | 54.84 | 43.10 | 40.38 |
| Baghdad IED | 95.13 | 57.11 | 66.77 | 65.05 | 64.74 | 62.56 | 47.84 |

**NIJ Portland validation (Table 3) [found]**
- All calls for service: CrimeRank 61.5, rotational CrimeRank 64.5, GLM 57.5, Hawkes 57.5, GBM-NDCG 57.8, RGPM (the authors' competition entry) 58.8.
- Street crime: 91.6 and 100.6 against 84.2, 84.0, 80.9 and 87.0 respectively.

**What this changes [found + inference]**
- The headline "+28 to 42 %" gains in Indianapolis and Baghdad mix two things: the top-k loss **and** the off-grid geometry. On NIJ, where only the loss differs from GLM and Hawkes, the gain is **+7 to 9 % relative** (61.5 vs 57.5; 91.6 vs 84.2).
- **GBM optimising NDCG did worse than random forest or GLM** in 3 of 4 datasets. A generic NDCG ranking objective is not the same thing as a top-k cutoff loss.
- The earlier note said a boosting learning-to-rank model "won the 2017 NIJ challenge". That is wrong. The entry that tied for the most first places was RGPM: grid optimisation with a point-process GLM or a random forest. CrimeRank beat the winners afterwards, on the validation set.
- Hawkes was about equal to GLM on 52-week count features. Self-excitation added little over well-chosen lagged counts.

**Concrete action (pipeline thread)**
- Write a custom LightGBM objective that uses CrimeRank's binary-cutoff pair weights in place of LambdaRank's ΔNDCG.
- Query group = beat × issue day.
- For each query, rank the cells by the current score. For every pair (positive i, negative j) where exactly one of the two is in the top 5, set w = 1/N_pos. Then grad_i −= w·σ(s_j − s_i) and grad_j += w·σ(s_j − s_i), with hess = w·σ(1−σ).
- Settings: about 300 rounds, learning rate 0.05, bagging_fraction = 0.25 (copying their 1/4 subsampling), min_data_in_leaf about 50-200.
- Compare it with stock `lambdarank` (with `lambdarank_truncation_level=5` and `label_gain=[0,1]`) and with the current Poisson model. Use the same LOSO folds and block-bootstrap CIs.
- Expected: +0.5 to 2 pts (7-9 % relative on 29.5 % is about +2 pts at best). A stock NDCG ranker may do **worse** (GBM-NDCG lost to RF in this paper), so do not adopt it on faith.

## 2. SpatialRank (NeurIPS 2023). arXiv 2310.00270

Full text. Code: https://github.com/BANG23333/SpatialRank

**Setup [found]**
- Chicago, 500 m × 500 m cells (a 64 × 80 grid), daily risk. Trained on 18 months, validated on 6 and tested on 2021.
- k = 30, 40 and 50.
- The loss is (1−σ)·NDCG + σ·L-NDCG. L-NDCG is the NDCG computed within each location's neighbourhood (Euclidean radius R), averaged over all locations.
- Importance-based location sampling with a Gaussian filter on the importance scores, re-weighted every epoch.

**Optimisation comparison, same network (Table 2) [found]**

| Loss | Chicago accident Prec@30 | Chicago crime Prec@30 |
|---|---|---|
| Cross-entropy | 0.424 | 0.475 |
| ApproxNDCG | 0.426 | 0.455 |
| SONG | 0.438 | 0.484 |
| SpatialRank | 0.444 | 0.491 |

So the top-k loss alone was worth about **+2.0 points of Prec@30 (+4.7 % relative)** for accidents and +1.6 points (+3.4 %) for crime. The best σ was 0.1. At σ = 0.3, results were worse than at σ = 0 (Table 3).

[inference] Our metric is recall@5 **within a beat**, which is already a "local" ranking, like L-NDCG with neighbourhood = beat. So the only lever here is the top-k loss, worth about **+1 pt**. Their deep model is not worth copying for us, given our data size.

**Concrete action (pipeline thread).** Fold this into action 1 as an expectation check. If the CrimeRank objective gains less than 1 pt, stop work on ranking losses.

## 3. PAWS: Xu, Gholami, McCarthy, Dilkina, Plumptre, Tambe et al. 2020 (ICDE), arXiv 1903.06669

Full text. The earlier note named the authors "Gholami, Fang, Tambe". The lead author is **Lily Xu**, with Gholami as co-first author.

**Method and numbers [found]**
- 1 × 1 km cells, three-month time steps; 22, 19 and 21 static features per park.
- Positive rates per park: 14.3 % (MFNP), 4.7 % (QENP), 0.36 % (SWS) and 0.25 % (SWS dry season).
- **iWare-E.** Train I classifiers. Classifier i uses all positives but only the negatives whose patrol effort is at or above threshold θ_i. The thresholds are set at **effort percentiles**, not fixed km values: 20 classifiers for MFNP and QENP, 10 for SWS. The classifiers are combined with weights tuned by 5-fold CV to minimise log loss.
- iWare-E raised AUC by **+0.100 on average** across weak learners (Table II). For example, the decision-tree weak learner went from 0.599 to 0.699 in MFNP, and from 0.626 to 0.720 in QENP.
- Balanced-bagging undersampling raised AUC by **15 %** on SWS.
- **Bagged-tree "uncertainty" is almost useless.** The variance across bagged decision trees correlated **0.979** with the prediction itself. For a Gaussian process it was −0.198.
- The "about 30 % more snares detected" result comes from **simulated evaluation** of patrols planned with GP uncertainty (β-weighted robust plans) on historical data. It is not from the field trials.
- Field trials (Table III), detections per patrolled cell for high / medium / low risk:
  - MFNP trial 2: 0.47 / 0.21 / 0.08.
  - SWS trials: 0.34 / 0.13 / 0 and 0.31 / 0.08 / 0.
  - Chi-squared p = 0.0105 (MFNP).
- In SWS, the 1 km risk was convolved to 3 × 3 km blocks before blocks were picked, and blocks with historical effort above the 50th percentile were dropped.

**What this changes [inference]**
- The earlier note's "exploration pick from the variance across bootstrap LightGBMs" will mostly re-pick the highest-risk cells, because tree variance tracks the mean (r = 0.979).
- iWare-E is the more useful idea. Our "patrol effort" equivalent is **observation quality**: the number of clear S2/Landsat looks in the window, or the cloud-gap length that brackets each scar.

**Concrete action (labels and pipeline threads)**
- For each cell-season, compute obs_quality = the number of clear (<20 % cloud) S2+Landsat acquisitions from Feb to Jun, or the median gap between clear looks.
- Build 5 LightGBM models. Model i keeps all positives and keeps only the negatives whose obs_quality is at or above the (0, 20, 40, 60, 80)th percentile.
- Average the 5 models with weights fitted by LOSO log loss.
- Expected: +0.5 to 1.5 pts. Detection misses concentrate in poorly observed, near-village cells, where we score 12-15 %. Effort: low.
- Drop "bootstrap-variance exploration". If officers need coverage, use a plain rule instead, such as one pick from cells not picked in the last 7 days.

## 4. Song, Raskutti & Willett 2021, "Prediction in the presence of response-dependent missing labels". arXiv 2103.13555

Full text. No code link in the paper.

**Method [found]**
- Observed size Z equals the true size Y with probability Γ(Y), and is otherwise 0.
- Γ is a **Gamma CDF** of fire size, chosen so the integral has a closed form.
- Occurrence is logistic. Magnitude is Gamma. Fitting is by projected gradient descent over 20 λ values.

**Data [found]**
- California 2001-2018, from the Artés et al. 2019 GlobFire perimeters.
- 75 % of recorded fires were 0.19-1.33 km². Fires under about 0.19 km² (19 ha) are largely missing.
- Pseudo-absences were sampled uniformly, one per fire per year, outside a 0.1° buffer around fires.
- 43 covariates: SRTM terrain (elevation, slope, aspect, dissection, heat load, TPI, TRI), ERA-Interim temperature, precipitation, RH and VPD, and GPW population density plus distances.

**Evaluation [found]**
- **Random 90/10 splits, 100 times, scored on magnitude error (MAD, RMSE, SMAPE) only.**
- It beat logistic-Gamma and logistic-lognormal models, by an amount given only in a figure.
- There is **no occurrence ranking, no AUC and no temporal hold-out.**

So the earlier note's "this beat earlier methods" holds only in that narrow sense.

[inference] The transferable idea is to make detection a known function of scar size. The method itself is not proven for ranking.

**Concrete action (labels thread)**
- From our label-check sample, fit P(scar detected | true burned area, canopy, obs_quality) as a logistic, or as a Gamma CDF in area.
- Use it to **weight negatives**: weight = 1 − P(missed | cell features), where P(missed) is the expected probability that a burn in that cell would go unseen. Apply this only in training.
- Expected: +0 to 1 pt on current labels. The real value is a more honest map. This overlaps with action 3; do action 3 first.

## 5. Xu, Xie, Zuniga Vazquez, Yao & Qiu, "Spatio-temporal wildfire prediction using multi-modal data". arXiv 2207.13250 (v5, 2023)

Full text.

**Data [found]**
- California utility (PG&E, SCE, SDG&E) fire incidents 2014-2019, 3,191 incidents.
- Cells of **0.24° (about 25 km)**: 36 in the small region and 453 in the large one.
- Small region: trained on 238 fires (2014-17), validated on 70 fires (2018). That is 13,140 cell-day predictions with 70 positives.

**Model [found]**
- λ(t,k,m) = [μ_k + Σ_j α_{u_j,k} · β·e^(−β(t−t_j))] · γᵀm.
- β is found by a 1-D grid search (each fixed β is a convex problem; 25 grid points).
- α_ij is forced to 0 when cell centroids are more than 4 × 0.24° apart. α_ij is allowed to be **negative** (inhibition).
- Marks were spline-interpolated and scaled to [0,1].

**Results [found]**
- Largest weights: fire threat tiers 1-3 (0.301, 0.231, 0.184) and the dynamic marks summer, temperature and RH (0.57, 0.472, 0.46).
- Example cell 20: summed positive influence into it 0.40, negative −0.30. Its negative influence on others: −1.44.
- **No fitted β (decay time) value is reported.**
- The baselines are only one-class anomaly detectors (isolation forest, one-class SVM, LOF, elliptic envelope). Scoring is per-cell F1 with dynamic thresholds.

[inference] The evidence is weak, and there are no parameters to copy. The one useful finding is that **inhibitory** neighbour effects are as large as excitatory ones (fuel depletion). We should therefore let LightGBM see "area burned this season within r km", not just recent ignition counts, so it can learn suppression.

**Concrete action (pipeline thread).** In the Hawkes feature set (action 6), add the burned fraction this season within 1, 3 and 8 km next to the decayed ignition counts. Expected: +0 to 0.5 pts over the counts alone.

## 6. Marey-Pérez, Fuentes-Santos, Saavera-Nieves & González-Manteiga, IJWF 32(2):178-194, **2023** (the earlier note says 2022). doi:10.1071/WF22030

Full text (USC repository PDF). Licence CC BY-NC-ND.

**Data and methods [found]**
- Galicia 1999-2014, 29,574 km², more than 255,000 fires since records began.
- Size classes: outbreak < 1 ha, fire ≥ 1 ha.
- Inhomogeneous L and L-cross functions, plus the spatio-temporal inhomogeneous K tested **up to 15 km and 15 days**.
- Plug-in bandwidths (ks package); Monte Carlo envelopes.

**Numbers to copy [found]**
- **Arson** wildfires: the maximum spatial aggregation radius per year ranged **0.45-8.79 km** (median about 2.4 km over 1999-2014; 1.36-5.30 km in most years). There is inhibition at larger distances.
- Arson outbreaks: 0-8.18 km. Arson outbreak × fire cross-aggregation reached the 15 km cap in 15 of 16 years.
- **Negligence**: at most 1.52 km, and usually 0.15-0.76 km.
- **Natural**: mostly independent.
- Spatio-temporal K: the interaction radius **shrinks with time lag**. In some years it reached 15 km within 2 days of an ignition. In 1999, 2005 and 2006 it persisted at 6-10 km over longer lags. In 2007 there was independence.
- Arson also aggregates **between years** in the same places. Negligence and natural fires do not.

**Concrete action (pipeline thread, top priority).** These are the kernel scales to copy. For each cell c and issue day t, using only scars **closed before t**:
- H(c,t; τ, σ) = Σ_j exp(−(t − t_j)/τ) · exp(−d_cj²/(2σ²)).
- σ ∈ {1, 2.5, 5} km and τ ∈ {2, 5, 15} days; 9 features each for new ignitions and for all burns.
- Plus beat-level new-ignition counts over the last 3, 7 and 14 days.
- Expected: +1 to 3 pts, mainly on new ignitions. This replaces the earlier note's σ = 1/3/8 km and τ = 2/7/21 days: 8 km and 21 days lie beyond where Galicia's arson clustering lives, and both scales were tested only up to 15 km and 15 days.

## 7. Di Giuseppe, Vitolo, Krzeminski, Barnard, Maciel & San-Miguel 2020, NHESS 20:2365. "Fire Weather Index: the skill provided by the ECMWF ensemble prediction system"

Full text. Licence CC BY 4.0.

**Method [found]**
- One year of pre-operational service (2017).
- Forecast FWI comes from the 9 km HRES and the 18 km, 51-member ensemble. The ERA5 FWI (about 30 km) is the reference.
- A "hit" is a GFAS/MODIS fire pixel (0.1°, FRP > 0.5 W m⁻²) on a day when the FWI is above the **90th percentile** of its ERA5 climatology.
- Verification uses POD only, because false alarms are not meaningful for a danger index.

**Results [found]**
- CRPS skill over climatology lasts beyond 10 days.
- POD is above 0.5 only in Europe and Boreal North America. Central America, the Middle East and northern-hemisphere Africa are at 0.2-0.5.
- **South-East Asia (SEAS) and Equatorial Asia (EQAS) are below 0.2**: "only 20 % of fires corresponded to the FWI above the 90th percentile". The authors note that the drought code may be the better indicator there.
- GFED's SEAS region includes India.

**Correction to the earlier note.** "High FWI coincided with fires in only about 50 % of cases" is the global, all-fires figure, and only boreal regions exceed it. For our GFED region the figure is **below 20 %**.

**Concrete action (weather "when" thread)**
- If the FWI system is computed from POWER/ERA5, test **DC and DMC percentiles** first, not FWI. Score them on the sanctuary-wide daily count (the Spearman for "when"), not on "where".
- Expected: Spearman +0.02 to 0.05 and about 0 pts of recall. Effort: low. Run it only after actions 1 and 6.

## 8. Bekar, Tavşanoğlu, Pezzatti, Vacik, Pausas, Bugmann & Petter 2020, IJWF, doi:10.1071/WF19158. "Cross-regional modelling of fire occurrence in the Alps and the Mediterranean Basin"

Full text.

**Method [found]**
- **Static Maxent** presence/background models, fitted at two resolutions.
- Regions: Switzerland 2000-16 (831 fires), Austria 2000-17 (491), Spain 2001-14 (2,688) and Turkey 2013-17 (2,512).
- Predictors: 19 WorldClim bioclim variables, roads, settlements, land cover, forest type, tree cover, aspect and slope. Variables with Pearson r > 0.7 were pruned.
- A transfer counted as successful at AUC ≥ 0.7 plus a correlation threshold.

**Key detail the earlier note missed [found]**
- The cross-regional model was "combined from the data from these regions … a joint model based on the entire dataset". Its "transfer" to each region therefore **includes that region's own data**. It is pooled training, not out-of-region transfer.
- Fine-resolution AUC, own regional model vs cross-regional model (Table 3):

| Region | Own model | Cross-regional |
|---|---|---|
| Switzerland | 0.865 | 0.868 |
| Spain | 0.673 | 0.715 |
| Turkey | 0.707 | 0.714 |
| Austria | 0.689 | 0.670 |

- True cross-region transfers were often much worse. For example, Switzerland → Spain had AUC 0.488, and Spain → Austria 0.569.

[inference] This supports **pooling the target with other regions, with a region flag**, which gives about the same or slightly better results than the local model. It argues against pretraining elsewhere and then fine-tuning. The gains are small (+0.00 to 0.04 AUC). This was a static, annual model, so it is weak evidence for daily ranking.

**Concrete action (research thread)**
- Pool Ratapani with 2-3 similar reserves, e.g. Singhori and Nauradehi, at the feature level, with a `region` categorical. Use the same label pipeline if possible, and VIIRS-dated scars elsewhere.
- Score only Ratapani folds.
- Try pooling before the `init_model` warm-start, because "pooled pretraining has not helped yet".
- Expected: +0 to 1 pt, lower than the earlier note's +1 to 2. Effort: medium.

## 9. Yang & Woolford 2026, IJWF 35(7), WF25211. "Short-term spatio-temporal forecasting of human-caused wildfires"

Full HTML text without supplement. Licence CC BY-NC-ND, open access since 21 Jul 2026.

**Data and model [found]**
- Ontario Fire Region, 2006-2019, May-Sept, about 10 × 10 km voxels (2,574 cells per day).
- Train 2006-13, test 2014-19, with whole seasons kept as blocks.
- Logistic GAM: η = β0 + β1·FFMC* + f1(road length)·I(road) + β2·I(road) + β3·%non-fuel + f2(DoY) + f3(%WII) + f4(%INF) + f5(lon, lat).
- One model per horizon (1-4 days).
- FFMC* is the **forecast** FFMC, with error U_d modelled as a zero-mean normal mixture estimated from forecast-vs-observed history and corrected by a modified SIMEX.
- Response-based sampling: all fires kept, a small share of non-fires, and an offset (the share is in the supplement).
- 1-day coefficients: intercept −19.91, FFMC* 0.14, road indicator 1.55, %non-fuel −0.081.

**Results, test set (Brier naive → SIMEX; 95 % PI coverage naive → SIMEX) [found]**

| Horizon | Brier naive | Brier SIMEX | Coverage naive | Coverage SIMEX |
|---|---|---|---|---|
| 1 day | 0.0006826 | 0.0006735 | 0.820 | 0.925 |
| 2 day | 0.0006781 | 0.0006736 | 0.853 | 0.945 |
| 3 day | 0.0006753 | 0.0006740 | 0.875 | 0.952 |
| 4 day | 0.0006751 | 0.0006741 | 0.838 | 0.959 |

The coverage gain is real, from 82-88 % to 93-96 %, as the earlier note says. The **Brier gain is tiny: 1.3 % at 1 day and 0.15 % at 4 days.** The naive model **under-predicts** the counts.

[inference] Correcting forecast-weather error fixes interval width, not ranking. For "where" it is irrelevant to us. For "when" (the daily budget), it is a reminder that a model trained on observed weather but run on forecasts will under-predict busy days.

**Concrete action (leakage audit, pipeline thread)**
- Retrain the "when" component on day t−1 observations, or on archived forecasts if we have them, as the input for targets t+1 and t+2. Fit a separate model per horizon.
- Check the interval coverage of the daily count.
- Expected: about 0 pts of recall, but an honest daily-count interval for officers. Effort: low.

## 10. Phelps & Woolford 2021, IJWF 30:850, plus Phelps, Lizotte & Woolford (arXiv 2412.16209)

Phelps & Woolford 2021: HTML full text, but the values in Table 2 are missing from the page. Phelps, Lizotte & Woolford: full text.

**2021 paper [found]**
- Lac La Biche, Alberta, 1996-2016, about 10 km² × 1-day voxels.
- 550 fire voxels in training, a prevalence under 0.06 %. Train 1996-2011, test 2012-16.
- 10 % of non-fire voxels sampled, with a −log(π) offset for the GLM and GAM.
- Balanced random forests calibrated by Platt scaling (with a GAM) using 4-fold year-wise CV.
- **The logistic GAM had the highest AUC-PR, "more than 10 % greater" than any other model.** None differed significantly on the calibration scores.
- The GAM included a **"baseline" covariate**: the logit of each cell's historical fire proportion. The best random forest used the baseline plus the GAM predictors.
- 500-tree forests give only 501 distinct probabilities.

**2024 follow-up [found]**
- Same data, with undersampled random forests (500 trees) analytically calibrated by the Dal Pozzolo formula.
- The **predicted total number of test-period fires varied by more than 40 %** across mtry (1-15) and sampling rates (0.01-0.10). The ratio of maximum predictions changed from 1.034 to 1.738 after calibration.
- Single decision trees **over-predict** under imbalance: the mean-prediction / truth ratio was 1.019 at 40 % prevalence, rising to 1.233 at 2.1 % and 1.157 at 0.2 %.

The earlier note's wording, "calibration … can itself be biased by more than 40 %", is loosely right. More exactly, the spread of calibrated prevalence estimates across hyperparameters exceeds 40 %.

**Concrete action (research thread)**
- Fit a Bernoulli or Poisson GAM (mgcv or pyGAM) with: s(DoY), s(NDMI), s(NBR), the logit of the cell's 2017-24 burn frequency (excluding the test season), te(x, y) with k about 60, and a beat random effect.
- Rank-average it with LightGBM, using equal weights and then LOSO-tuned weights.
- Expected: +0 to 1 pt. It is the only model family here that beat trees on AUC-PR at very low prevalence. Effort: low.

## 11. Searched for, not found or low value

- **India daily fire ML with features and ablations.** I found none for central India.
  - The nearest is a next-day Uttarakhand ResUNet-A model at 30 m (April-May 2016; ERA5, SRTM, fuel, VIIRS masks). Only the abstract or slides were seen; it reports no ablation.
  - All-India susceptibility work (Sharma et al. 2022, IJWF WF22016) is annual: SVM AUC 0.908, ANN 0.903.
  - A South-East Asia VIIRS paper (PMC12122932) is **monthly, country-level and fire-count-only**, so it is not usable.
  - Context: on 7 Aug 2026 the parliamentary Standing Committee on S&T, Environment, Forests and Climate Change reported that **only about 12.5 % of FSI alerts in Uttarakhand corresponded to actual fires** (PRS summary, https://prsindia.org/files/policy/policy_committee_reports/Report_Summary_Forest_fires_Himalayan_Region.pdf). The summary does not say whether these were pre-fire or active-fire alerts.
- **Wildfire Hawkes papers with fitted decay times.** None found. Xu et al. report no β. The Sicily work is a talk only. The kernel scales above therefore come from Galicia's second-order analysis.
- **Bogotá ETAS (arXiv 1811.12880).** The earlier note cites this as a "review of the field trials". It is actually a Bogotá deployment paper, with a temporal decay parameter of 0.03 and a spatial σ of 100 (units unclear) for crime. The 1.4-2.2x and 7.4 % figures come from Mohler et al. 2015, JASA 110:1399, "Randomized controlled field trials of predictive policing".

---

## Verified numbers

| Claim in `short_horizon_prediction.md` | Source checked | Verdict |
|---|---|---|
| Yang & Woolford: SIMEX coverage 82-88 % → 93-96 % | HTML Table | Correct (0.820-0.875 → 0.925-0.959). Brier gain only 0.15-1.3 %. |
| Yang & Woolford: daily 10 km voxels, one model per lead time 1-4 days | HTML | Correct. 2006-19, May-Sep, train 2006-13 / test 2014-19. |
| Phelps & Woolford 2021: calibrated GAM "matches" ML | HTML | GAM had the **highest** AUC-PR (>10 % above the others); differences not significant. |
| arXiv 2412.16209: calibration "biased by more than 40 %" | Full text | Loosely right: calibrated prevalence estimates **vary** by >40 % across RF settings. Single trees over-predict by up to 23 %. |
| NHESS 2020: high FWI coincides with fires only ~50 % of cases | Full text | Global figure. **SEAS/EQAS (our region) POD < 0.2.** Hit = FWI > ERA5 90th percentile. |
| ETAS 1.4-2.2x analyst; 7.4 % crime cut | Not re-read (JASA 2015) | Numbers are from Mohler 2015 JASA. The linked arXiv 1811.12880 is the Bogotá deployment, not a review. |
| CrimeRank won the 2017 NIJ challenge | Full text | **Wrong.** The authors' RGPM entry tied for the most 1st places; CrimeRank beat the winners later on validation (PAI 61.5 vs 57.5-58.8; street 91.6 vs 84-87). |
| PAWS: imbalance up to 1:200; +30 % snare detection | Full text | Correct, but the 30 % is from **simulated** uncertainty-aware planning on historical data. Lead author is Xu, not Gholami/Fang. |
| Song 2021 "beat earlier methods" | Full text | Only on magnitude error (MAD/RMSE/SMAPE) with random 90/10 splits. No occurrence-ranking test. |
| Bekar 2020: pooled cross-regional model transfers better | Full text | The pooled model **includes** the target region. Pooled vs own model: AUC +0.003 to +0.04, and −0.02 in Austria. True cross-region transfers fell as low as 0.49. |
| Galicia arson clustering (2022) | Full text | Published **2023**, IJWF 32(2). Arson radius 0.45-8.79 km; negligence ≤ 1.5 km; space-time interaction up to 15 km within 2 days, decaying with lag. |
| Hawkes California: no usable numbers | Full text | Correct. 0.24° cells; no fitted β; one-class baselines only. |
| SpatialRank optimises NDCG | Full text | Correct. Top-k loss vs cross-entropy on the same network: +1.6 to 2.0 pts Prec@30. |

Not re-checked here: Mesogeos AUPRC 0.86-0.87, the FireSenseNet "+44 % F1 inflation", and the ECMWF PoF "up to 30 %".

---

## Ranked action list

| # | Action | Thread | Settings to copy | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | Local self-excitation features from scars closed before the issue day | pipeline | Gaussian space × exponential time kernels: σ = 1, 2.5, 5 km; τ = 2, 5, 15 days; new ignitions and all burns separately; beat counts over the last 3, 7, 14 days; burned fraction this season within 1, 3, 8 km (inhibition) | +1 to 3 pts | Low |
| 2 | Effort-thresholded ensemble (iWare-E) using observation quality | labels / pipeline | 5 LightGBMs; negatives filtered at the 0/20/40/60/80th percentile of clear-look count; positives always kept; weights by LOSO log loss | +0.5 to 1.5 pts | Low |
| 3 | CrimeRank-style top-5 cutoff objective (custom LightGBM fobj), compared against stock lambdarank | pipeline | Query = beat × day; pair weight only for pairs straddling rank 5; bagging 0.25; about 300 rounds | +0.5 to 2 pts (7-9 % relative at best; a stock NDCG ranker may lose) | Low-medium |
| 4 | GAM with spatial smooth + cell baseline logit, rank-averaged with LightGBM | research | s(DoY), s(NDMI), s(NBR), te(x,y) k ≈ 60, beat RE, logit of long-run burn frequency | +0 to 1 pt | Low |
| 5 | Leakage and horizon audit: t−1 or forecast weather, one model per horizon, daily-count interval coverage | pipeline | As in Yang & Woolford: separate t+1 / t+2 models | 0 pts, but honest numbers | Low |
| 6 | Pooled multi-reserve training with a region flag (not pretrain-then-finetune) | research | 2-3 similar reserves; score Ratapani folds only | +0 to 1 pt | Medium |
| 7 | DC/DMC percentiles in place of FWI for the "when" budget | weather | 90th-percentile framing; spin-up from 1 Dec | Spearman +0.02 to 0.05; about 0 recall | Low |
| 8 | Detection-weighted negatives (Song-style detection curve in scar size) | labels | P(detect \| area, canopy, obs_quality) from the label-check sample | +0 to 1 pt | Medium |
| Drop | Bootstrap-variance "exploration" pick | — | Tree variance correlates 0.979 with the mean (PAWS) | ~0 | — |

All expected gains are my estimates [inference], scaled from the relative gains the papers report.
