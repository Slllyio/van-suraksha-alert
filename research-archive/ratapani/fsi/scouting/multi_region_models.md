# Fire occurrence models across many regions: per-division vs pooled vs hierarchical, cold start, evaluation and calibration (scouting round 11, topic "region", 15 Oct 2026)

**For:** thread 1 (the all-MP model with one model per forest division, 87 divisions, VIIRS S-NPP + NOAA-20 + NOAA-21, train 2019-21, test 2022-24, about 84.6% of fire points in the top 10% of squares; new fires score 56.5%). Some items also touch thread 4 (calibrated burn probabilities) and thread 5 (patrol budgets).

**Not repeated here** (already in other notes): kNNDM CV (`small_data_models.md` G1), Bekar et al. 2020 cross-regional Maxent (`short_horizon_prediction_fullread.md` 8), Phelps & Woolford calibration of tree models (same file, 10), Ontario/BC/Spain/Brazil INPE/ProbFire operational systems (`operational_occurrence_systems.md`), FSI pre-fire alerts, Barik/IIT Delhi FWI, the MP/CG susceptibility papers (`short_horizon_prediction.md` 2), FSI risk zonation (`risk_zone_method.md`, `ground_truth_sources.md` 5c), Opitz 2020 and Koh 2023 point-process models, Kale et al. 2022.

**Labels:** FULL = full text obtained and the methods and results read. PARTIAL = full text obtained but only the named sections read, or only part of the page came through. ABSTRACT ONLY = abstract or search snippet. Anything marked [inference] is my reasoning, not a finding from the source.

---

## Headline findings

1. **Pooled models with a division label usually match or beat one-model-per-region, and a hierarchical (random-effect) model beats both, especially for regions with few fires.** The theory (Montero-Manso & Hyndman) says a pooled model generalises better as the number of groups grows, because its complexity does not grow with the number of groups. The one paper that claims per-country models win (Shmuel et al. 2025: per-country AUC 0.86 vs global 0.71) compared them against a *depth-5 decision tree* for 160 countries, a model too small to learn the differences. That result does not argue against a pooled LightGBM. [inference]
2. **The pooled score hides weak divisions.** In the French department-aware benchmark, the same models score F1 0.43 when scored over all of France but only 0.13-0.16 when the score is averaged per department. Our 84.6% "share of fire points in the top 10% of squares" is pooled, so it is probably carried by a few high-fire divisions. The first job is a per-division table and its median. [inference]
3. **Split recurring and new fires into two models.** Graff et al. 2020 (Alaska) used separate Poisson-hurdle models for cells with fire yesterday and cells without. Against persistence, the split models gain about 15-20% in RMSE skill, and the skill rises above 30% at 3-5 day leads. The new-ignition model did *not* beat "always zero" in RMSE, but it ranked ignitions well above random. This matches our 56.5% vs 84.6% gap.
4. **Satellite and regime changes between train and test years need an explicit term.** In Firelihood (Mediterranean France), removing the fitted "post-2003" step cut the 95% interval coverage of annual fire counts from 58% to 4.2% (MAE 40%). Our train years (2019-21) and test years (2022-24) differ in how many VIIRS satellites flew (NOAA-21 launched Nov 2022, so it can only contribute in the test years; check the exact first date in our FIRMS pull) [inference], and S-NPP alone sees about half the fire square-days of three satellites. That is the same kind of step change.
5. **How a hit is counted can change the verdict.** In the Wildfire-FM benchmark, occupancy F1 was 0.45% when only the same cell on the same day counted. It rose to 29.7% when a small spatial or temporal offset was allowed, and 59% when either rule counted. Model rankings flipped under the different rules. "Top 10% of squares" must state its tolerance, and the tolerance should match how far a patrol actually reaches. [inference]
6. **"X% of fires fell in high classes" means nothing without the area share.** Nepal's operational FWI system reports 83% of 1,223 fire points in Moderate-to-Very-High classes but never gives those classes' area, and its thresholds were tuned on the same seasons. Report the predictive accuracy index PAI = (share of fires) / (share of area) next to the capture rate. Ours is 84.6 / 10 = 8.5.
7. **India still has no published daily, division-level occurrence model with honest skill numbers.** The one next-day Uttarakhand deep-learning paper (2026) got **zero true positives** on its test patches. State and FSI products are weekly FWI classes or static risk zones. Our per-division model would be the first such baseline.

---

## Part A. Per-region vs pooled vs hierarchical models

### A1. Montero-Manso & Hyndman 2021, "Principles and algorithms for forecasting groups of time series: locality and globality", *Int. J. Forecasting* 37:1632-1653. arXiv 2008.00444. **PARTIAL** (abstract, sections 3.6, 5.3, 5.5, 6.3 and 7 read)
https://arxiv.org/abs/2008.00444

**What it shows:**
- A "global" (pooled) model and a set of "local" (per-series) models can produce the same forecasts with no assumption that the series are similar. Pooling is not more restrictive.
- Generalisation bound: the complexity term for local models grows with the number of series K. For a global model it stays constant. A pooled model can therefore afford to be much more complex and still generalise better.
- Partitioning is the middle ground. With P groups, each fitted by its own global model, the bound sits between the two extremes. Choosing the groups from the data (clustering) adds hidden complexity.
- Experiment: randomly splitting the M4 series into 10 equal groups, each with its own global model, often *improved* accuracy when the single global model was capacity-limited. Random groups are not similar series, so the gain came from extra model capacity, not from "matching like with like".
- M4 heterogeneous set, one-step MASE: auto.arima 0.762, ETS 0.764, theta 0.775. Global linear 0.928, cluster linear 0.856. Global deep net 0.815, cluster deep net 0.763, **global deep net + series features 0.760** (best). Adding group descriptors as features to one big model matched or beat clustering.
- Scale normalisation helped (relative MASE 0.950), and adding the scale back as a feature helped a little more (0.948; relative MAE 1.021 → 0.996).

**Concrete action for us (thread 1):**
- Fit **one pooled LightGBM over all 87 divisions** with: division ID (categorical); division descriptors (forest area, prior-season fire-point density, share of fires that were new, mean NDMI, satellite count per season); and the same cell and weather features. Use more leaves and rounds than a single division model.
- Compare against the current 87 models on the 2022-24 test, per division.
- Also try the "partition" middle ground: 5-8 groups of divisions (by FSI physiographic zone, or by fire density tercile), each with its own LightGBM.
- Expected [inference]: equal or slightly better top-10% capture in high-fire divisions, and a clearly better result (several points) in the 20-30 divisions with the fewest fires.
- Effort: low (one training run plus the per-division table).

### A2. Sigrist 2022/2023, "Gaussian Process Boosting" (GPBoost), arXiv 2004.02653 (v7, 2024); JMLR 2022 and IEEE TPAMI 2023. **PARTIAL** (abstract, sections 1, 3.6, 4.5, 5.1, 5.2 and 6 read)
https://arxiv.org/abs/2004.02653 · code: https://github.com/fabsig/GPBoost (`pip install gpboost`, R package on CRAN v1.6.6, Feb 2026)

**What it shows:**
- The model is y = F(X) + Zb + e. F is a tree ensemble grown with **LightGBM**, and b holds grouped random effects and/or a Gaussian process. Both are learned together.
- This is a principled way to handle a high-cardinality grouping such as a division ID.
- Simulation (grouped data, 'hajjem' function), test RMSE for groups seen in training / groups not seen:

  | Model | Seen groups | New groups |
  |---|---|---|
  | **GPBoost** | **1.100** | **1.458** |
  | LightGBM with the group as a categorical | 1.156 | 1.493 |
  | CatBoost | 1.183 | 1.464 |
  | MERF (mixed-effects random forest) | 1.104 | 1.460 |
  | Linear mixed model | 1.342 | 1.635 |

  GPBoost was best in all of them (paired p < 1e-5). It ran in about 0.9 s against 417 s for MERF.
- Real panel data (4,711 groups), test RMSE: GPBoost 0.296; MERF 0.299; CatBoost 0.303; LightGBM with the group as a categorical 0.321, and **0.313 with the group ID as a plain number** (as the LightGBM authors suggest).
- The library also does nested and crossed random effects, random slopes, and a Vecchia-approximated spatial GP. Non-Gaussian (binary) outcomes use a Laplace approximation (Sigrist 2022).

**Concrete action for us (thread 1, cold start):**
- Fit GPBoost with a Bernoulli likelihood on the MP cell-day table. Inputs: fixed effects = the current features; random intercept per division; random slope per division on the dryness and weather terms; optionally a random intercept per range or beat nested in division.
- Divisions with few fires are pulled toward the state mean automatically. That is the cold-start fix.
- Test it with **leave-division-out** (train on 86 divisions and score the held-out one) to mimic a new division, and on 2022-24 for all divisions.
- Expected [inference]: small gain where data is plentiful (under 1 point of top-10% capture), larger gain in divisions with under about 200 training fire points, and better-calibrated probabilities.
- Effort: medium. Subsample negatives, because the full cell-day table is large; correct the intercept afterwards (see D1).

### A3. Shmuel, Lazebnik, Heifetz, Glickman & Price 2025, "Fire weather indices tailored to regional patterns outperform global models", *npj Natural Hazards* 2:74. **FULL** (9 pp)
https://doi.org/10.1038/s44304-025-00126-y

**What it shows:**
- Global daily ignitions, 2014-2020, on a 0.25° grid from the GlobFire-style dataset of Artés et al. (over 7 million fires). Negatives randomly undersampled to 1:1. Results are given for 160 countries with at least 50 observations.
- ROC AUC: Canadian FWI 0.69 (best FWI in 91 of 160 countries), Australian 0.65, American 0.61.
- FWI re-tuned per country with a genetic algorithm: 0.79 (test).
- LightGBM per country: **0.91**. That LightGBM distilled into a depth-5 decision tree: 0.86.
- **One global depth-5 decision tree: 0.71.** Leave-one-year-out gave 0.82 (vs 0.86).
- Weaknesses: the train/test split is a random 80/20 within each country, so neighbouring days and cells leak across it. The "global" comparison uses a five-split tree, which cannot represent 160 countries.

**Concrete action for us (thread 1):**
- [inference] Read this as support for country- or division-specific *thresholds and interactions*, not as evidence against a pooled high-capacity model.
- The cheap transferable idea: **re-fit the FWI or dryness-to-fire link per division**, i.e. a per-division logistic on FWI percentile. Use it as a "when" input and as a baseline that each division model must beat.
- Expected: +0 to 1 point; mainly a baseline.

### A4. Liu & Mostafavi 2025, "WildfireGenome: interpretable machine learning reveals local drivers of wildfire risk and their cross-county variation", arXiv 2511.11589. **FULL**
https://arxiv.org/abs/2511.11589

**What it shows:**
- Seven US counties, H3 level-8 cells. The label is a PCA composite of 7 federal hazard indicators, split into within-county quartiles.
- Random forest, random 70/30 split inside each county: accuracy 0.755-0.878, QWK 0.875-0.951.
- Transfer between counties: Boulder ↔ Larimer QWK 0.85 / 0.65. **Butte → Boulder QWK -0.24**, worse than chance.
- The authors blame two things: different local fire regimes, and labels defined as *within-county quantiles*, which makes the classes mean different things in each county.

**Concrete action for us (thread 1):**
- [inference] Our "top 10% of squares *within each division*" is also a within-region quantile. It cannot be compared across divisions, and a model trained on one division's ranking may not carry over.
- When ranking squares for the state (patrol allocation across divisions), use calibrated probabilities on one common scale, not per-division percentiles.
- Report both: (a) capture with top 10% *per division*, (b) capture with the top 10% of squares *statewide* (one cut on calibrated probability).
- Effort: low.

### A5. Zhuang, Hobeichi, Shi & Huang 2026, "Evaluating AlphaEarth Foundations embeddings for wildfire susceptibility mapping", arXiv 2608.12663. **FULL**
https://arxiv.org/abs/2608.12663

**What it shows:**
- Victoria, Australia, 2017-2025, 1 km grid. Fire label = any MODIS MCD14ML detection at confidence 80 or higher; 18,140 fire cells, about 8% of cells.
- Pseudo-absences: at least 3 km from fires, one per 3 km block.
- Models trained on AlphaEarth Foundations (AEF) 64-band annual embeddings reach ROC AUC above 0.92, about the same as hand-built physical variables.
- Transfer to new regions, ROC AUC change:
  - Physical-variable models: **about -25%** even at the nearest temperate sites (Canberra, Western Sydney–Blue Mountains).
  - Embedding models: **+4% at Canberra** (recall about +13%), **-2% at Western Sydney**.
  - The losses grow toward subtropical Queensland and arid Alice Springs.
  - Recall falls faster than specificity as the target gets more distant.
- Possible leakage: the 2020 embedding layer got the highest weight, and about 28% of fire cells come from the 2019-20 Black Summer. The embedding of a fire year may partly encode the burn itself.

**Concrete action for us (thread 1, cold start):**
- Add the AEF annual embedding (Earth Engine `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`), averaged to the 500 m cell, as static features in the pooled model. Always use **the previous calendar year's embedding** (year t-1 for season t), so the current season's scars cannot leak in.
- Test on the 20-30 low-fire divisions with leave-division-out.
- Expected [inference]: +1 to 3 points of top-10% capture in cold-start divisions, about 0 in fire-rich ones.
- Effort: medium (Earth Engine export over 373,681 cells, 64 bands × 8 years).

### A6. Caron, Noura, Guyeux & Aynes 2025, "Localized forest fire risk prediction: a department-aware approach for operational decision support", arXiv 2506.04254 (v2, Oct 2025). **FULL** (8 pp)
https://arxiv.org/abs/2506.04254 · code: https://github.com/NicolasCaronPro/Localized-Forest-Fire-Risk-Prediction-ADepartment-Aware-Approach-for-Operational-DecisionSupport

**What it shows:**
- 92 French departments, daily targets 2017-2024. Train 2017-20 + 2022, validation 2021 + 2024, **test 2023**. The 2024 low-fire year (about 1,600 fires vs 2,300 in 2023) was deliberately kept out of the test.
- Targets are ordinal 5-class "fire level" classes, built *per department* with K-means on that department's own fire counts. Two fires in Brittany is an alarm, two in the Mediterranean is routine.
- Features: 162 of 261, including "past risk" (fire history smoothed with a cubic kernel and lagged one day), a department ID encoded with CatBoost target encoding, clusters of departments by DTW on fire time series, and calendar and holiday encodings.
- Pooled F1 for "at least one fire": CatBoost 0.43 (P 0.37, R 0.51), GraphCast-GRU 0.43 (R 0.60), logistic regression 0.39, **FWI alone 0.17** (R 0.87, P 0.10).
- **Averaged per department, F1 falls to 0.13-0.16 for every model** (FWI 0.14). IoU falls from about 0.24 to 0.07-0.09.
- Historical features dominate SHAP in fire-active departments and "can hurt generalization in low-risk or emerging areas".

**Concrete action for us (thread 1):**
1. **Per-division report card** (effort low; do first). For each of the 87 divisions on 2022-24, give:
   - test fire points;
   - top-10% capture and PAI;
   - capture for new fires and for recurring fires;
   - a random baseline.

   Then report the median across divisions and the fire-weighted mean, and plot capture against the division's fire count.

   Expected [inference]: the median division sits well below 84.6%, perhaps 65-75%. Divisions with under 50 test points will be noisy, so add bootstrap intervals.
2. Use a **division-level "level" target** next to the cell target: for each division-day, predict the class of the fire count within that division's own distribution. This gives each DFO a "busy day" signal that is fair across divisions.
3. Watch whether the history features dominate. Train a variant with the history features capped (for example, only "any fire in the last 3 seasons"), and check new-fire capture.

### A7. Pimont, Fargeon, Opitz, Ruffault, Barbero, Martin-StPaul, Rigolot, Rivière & Dupuy 2021, "Prediction of regional wildfire activity in the probabilistic Bayesian framework of Firelihood", *Ecol. Appl.* 31:e02316 (bioRxiv 2020.05.20.105767). **FULL** (bioRxiv full text read through the fetch tool, both halves; the HAL postprint was blocked by a bot check)
https://doi.org/10.1002/eap.2316 · preprint https://www.biorxiv.org/content/10.1101/2020.05.20.105767v1.full

**What it shows:**
- Mediterranean France, 15 NUTS3 units (75,560 km²), 8 × 8 km voxels, summer weeks 22-44, 1995-2018. About 4.44 million pixel-days, 7,193 escaped fires (1 ha or more).
- Occurrence model: Poisson in INLA, with **forest area as a log offset** and also as a non-linear covariate, plus a weekly seasonal effect (23 segments), daily FWI, and a spatial Matérn SPDE random field (1,143 mesh nodes, fitted range about 30 km). That field is how regional differences enter.
- Train 1995-2014, validation 2015-2018. Occurrence AUC above 0.8 in both.
- A fixed **"post-2003" effect** (posterior mean 0.46 on the log scale, about a 37% drop in rate) was needed:
  - with it, coverage of annual counts was 58%;
  - without it, coverage was **4.2%** with MAE 40%.
- Weekly counts: MAE 32%, 95% interval coverage 84% (target 95%).
- Counts were overdispersed, but a negative binomial gave simulated counts "until 10 times larger than maximum observations", so they kept the Poisson.

**Concrete action for us (thread 1):**
- [inference] Our 2019-21 → 2022-24 split crosses a detection-regime change (NOAA-21 only in test years; S-NPP sees about half of the three-satellite square-days). Without a regime term, the model's base rate is wrong in the test years even if the ranking is fine.
- Options:
  - (a) build the label from **S-NPP only** for a consistent long series, with three-satellite labels used only as a sensitivity check;
  - (b) add "number of VIIRS satellites in orbit that season" and "overpasses per day" as features;
  - (c) refit only the intercept per test season (see D1).
- Also use **log(forest area in the cell or square)** as an offset or feature, as Firelihood does, so partly forested edge squares are not under-ranked.
- Expected: little change in ranking, a large improvement in calibrated counts (thread 5 staff budgets).
- Effort: low.

### A8. Papadopoulos, Diamanti, …, Papoutsis 2026, "Adapting global wildfire danger models to high-stakes regional fire regimes", NeurIPS 2026 (virtual page). **ABSTRACT ONLY**
https://neurips.cc/virtual/2026/165276
- A regionally fine-tuned FireCastNet on a dense regional graph beat the global model on AUPRC in Greece, California and New South Wales.
- Absolute skill stayed modest in Greece and California. New South Wales gained most over climatology.
- Attribution differed by region: slow drought and vegetation drivers in New South Wales, solar radiation elsewhere.
- *Action (thread 1):* supports "pretrain pooled, then fine-tune per region". The LightGBM version is `init_model` continued training: train pooled, then add 50-200 trees per division on that division's data. Compare with A1 and A2. Effort low.

### A9. Rodrigues, de la Riva & Fotheringham 2014, "Modeling the spatial variation of the explanatory factors of human-caused wildfires in Spain using geographically weighted logistic regression", *Applied Geography* 48:52-63; Martínez-Fernández, Chuvieco & Koutsias 2013, *NHESS* 13:311. **ABSTRACT ONLY**
https://nhess.copernicus.org/articles/13/311/2013/
- Geographically weighted logistic regression (local coefficients smoothed over space) beat global logistic regression on accuracy and fit for human-caused fires in continental Spain.
- The 2013 GWR study used 7,638 municipalities; its binary logistic model was 76.4% correct.
- A follow-up (Rodrigues et al. 2018, *J. Env. Manage.* 225:177) found human factors losing, and climate factors gaining, explanatory power between 1988-92 and 2006-10.
- *Action (thread 1):* [inference] GWR is the spatial version of partial pooling. Our GPBoost spatial-GP option (A2) or "neighbour-division mean residual" features do the same job. No separate experiment.

---

## Part B. Recurring vs new fires

### B1. Graff, Coffield, Chen, Foufoula-Georgiou, Randerson & Smyth 2020, "Forecasting daily wildfire activity using Poisson regression", *IEEE TGRS* 58:4837-4851. **FULL** (CC BY)
https://doi.org/10.1109/TGRS.2020.2968029

**What it shows:**
- Alaska, 10 fire seasons of MODIS counts on a 0.5° grid, ERA-Interim weather, lead times k = 1-5 days, cross-validation across years.
- Every cell-day is labelled one of four ways:
  - *sustain*: fire yesterday and today;
  - *extinction*: fire yesterday, none today;
  - *ignition*: no fire yesterday, fire today;
  - *quiescence*: no fire either day.
- Persistence over-predicts because it never forecasts extinction.
- A Poisson **hurdle** model (one part for zero vs non-zero, one for the count) with VPD and a log autoregressive term was best. VPD alone was the best single weather input. A lagged AR term cut RMSE by about 4%. An MLP (16-8 neurons) was no better.
- Skill vs persistence on fire days: hurdle model **above 30% at k = 3-5**, against 18-20% for VPD-modulated persistence.
- **Two separate hurdle models (fire-yesterday cells vs no-fire-yesterday cells)** gave about 15-20% skill improvement over persistence on all days, and a small gain over one hurdle model.
- The new-ignition model did not beat "always zero" on RMSE, but its *ranking* of ignitions was far above random (cumulative capture curve, Fig. 9). Ignition should be scored as a ranking or probability, not by count error.

**Concrete action for us (thread 1):**
- Split the all-MP training rows into **"active"** (VIIRS within 5 km in the past 7 days) and **"new"** (none). Train two LightGBMs, or one with a forced first split on that flag, and score each part with its own capture curve.
  - The active model gets the fire's age, detection count in the last 3 days, FRP and days since first detection.
  - The new model gets no fire-history features from the current season, only prior-season history and static and dryness features.
- Allocate the top 10% across the two pools by their calibrated probabilities.
- Expected [inference]: new-fire capture 56.5% → 58-62%; overall capture about the same or +1 point.
- Effort: low.
- Also report the four Graff states for our 2-day lead (sustain / extinction / ignition / quiescence counts) so the persistence baseline is explicit.

---

## Part C. Evaluation: spatial autocorrelation, leakage, area-normalised scores and matching rules

### C1. Ploton et al. 2020, "Spatial validation reveals poor predictive performance of large-scale ecological mapping models", *Nature Communications* 11:4540. **FULL**
https://doi.org/10.1038/s41467-020-18321-y

**What it shows:**
- Random forest for forest biomass in central Africa: about 60,000 1 km pixels from 190,000 inventory plots, MODIS + climate + topography.
- Biomass is autocorrelated to about 120 km, and the predictors to about 250-500 km.
- Random 10-fold CV: R² 0.53. **Spatial 44-fold CV: R² 0.14.**
- Buffered leave-one-out: R² 0.50 with no buffer, about 0.15 when test pixels are about 50 km from training pixels, and near zero beyond about 100 km.
- Residuals from the random CV showed no spatial autocorrelation, so "no autocorrelation in the residuals" does not prove the validation is sound.

**Concrete action for us (thread 1):**
- Our 2022-24 test is a clean temporal hold-out, but the **same squares** appear in train and test. Square-level history and static features let the model "remember" squares. That is fine for operational use, where we always forecast known squares.
- It is not fine for any claim about **new divisions or new squares**. For the cold-start claim, use leave-division-out with a buffer of at least 10 km around the held-out division (drop training squares within 10 km of its border). Report how much capture falls.
- Expected: the leave-division-out number will be clearly below 84.6%. That number is the honest one for divisions with no history.
- Effort: low.

### C2. Meyer & Pebesma 2021, "Predicting into unknown space? Estimating the area of applicability of spatial prediction models", *Methods Ecol. Evol.* 12:1620 (arXiv 2005.07939). **PARTIAL** (preprint abstract, sections 2-3.1)
https://arxiv.org/abs/2005.07939 · R package CAST (`aoa()`)

**What it shows:**
- Dissimilarity index (DI): the distance from a new point to the nearest training point in feature space, with features weighted by their importance and standardised by the mean training distance.
- The area of applicability (AOA) is where DI stays below a threshold. Over 972 simulated scenarios, the 0.95 quantile of training DI (computed respecting the CV folds) gave a mean gap between CV error and true error of 0.002.
- The published version may use a different threshold rule. I did not read it.

**Concrete action for us (thread 1):**
- Compute DI for every division's test squares against the pooled training set (CAST `aoa()` in R; a Python re-implementation is about 30 lines).
- Flag divisions where more than 20% of squares fall outside the AOA, and show the flag on the alert page.
- Expected: no change in skill; it tells officers where not to trust the map.
- Effort: low.

### C3. Kapoor & Narayanan 2023, "Leakage and the reproducibility crisis in machine-learning-based science", *Patterns* 4:100804 (arXiv 2207.07048). **PARTIAL** (abstract, taxonomy section 2.4, case-study summary)
https://arxiv.org/abs/2207.07048

**What it shows:**
- Errors were found in 17 fields, affecting 329 papers. The paper sorts leakage into 8 types. The ones that matter for us:
  - L1.2 pre-processing on train and test together;
  - L1.3 feature selection on train and test together;
  - L2 illegitimate features;
  - **L3.1 temporal leakage**;
  - **L3.2 non-independence between train and test**;
  - L3.3 sampling bias in the test set.
- Civil war prediction case: once leakage was fixed, complex models (random forest, AdaBoost) no longer beat 1990s logistic regression.
- Proposes "model info sheets" that declare each of these.

**Concrete action for us (threads 1 and 4):**
- Write a one-page model info sheet for the all-MP model. Check in particular:
  - (a) that every fire-history feature is lagged by at least the forecast lead (a 2-day forecast must not see day t+1 VIIRS);
  - (b) that per-division feature scaling and target encoding of the division ID are fitted on 2019-21 only;
  - (c) that FSI fire-point de-duplication does not leave the same fire's points on both sides of the split. Points from one multi-day fire that straddles 31 Dec 2021 are unlikely, because the season ends in June, but the same check matters for any random-day CV used in tuning.
- Expected: protects the 84.6% claim. If a leak exists, the honest number will be lower.
- Effort: low.

### C4. Joshi, D'Ath, Curtis-Ham & Searle 2020, "Considerations for developing predictive models of crime and new methods for measuring their accuracy", arXiv 2006.08008. **PARTIAL** (abstract, sections 2-3.1)
https://arxiv.org/abs/2006.08008

**What it shows:**
- Hit rate = n/N, the share of events inside the predicted hotspots.
- PAI = (n/N) / (a/A), where a/A is the hotspot share of the area. PAI favours small hotspots too strongly. In their example, a model that finds only the single top hotspot (1% of area, 10% of crime) gets PAI 10 and beats one that finds the top three (3%, 27%, PAI 9).
- **Penalised PAI**: PPAI = (n/N) / (a/A)^α, with 0 ≤ α ≤ 1. α = 0 gives the hit rate; α = 1 gives PAI.
- α can be set to the hit rate, or tuned so that PPAI peaks at the area a patrol can actually cover (for example 2%).
- Also proposes the average log score (ALS) as a proper probabilistic score.
- Other measures in the literature: the recapture rate index (RRI) and the area-to-perimeter ratio (compactness).

**Concrete action for us (threads 1 and 5):**
- Report, per division, the capture curve at 2, 5, 10 and 20% of area, with PAI and PPAI at the patrol-feasible area. For example, if a range can patrol about 5% of its squares per day, set α so that PPAI peaks at 5%.
- Add a compactness measure: the number of separate patches in the top 10%. Fewer, larger patches are easier to patrol.
- Expected: no skill change; a fairer comparison between models and the calendar baseline.
- Effort: low.

### C5. Xu, Dai, Chang, Wang & Dong 2026, "Does your wildfire prediction model actually work, or just score well?" (Wildfire-FM), arXiv 2605.18911. **PARTIAL** (abstract, sections 3.3-4.3)
https://arxiv.org/abs/2605.18911 · weights: https://huggingface.co/RAI-Lab/Wildfire-FM

**What it shows:**
- With the model outputs held fixed, only the matching rule was varied:

  | Model | Exact F1 | Tolerated F1 | Union F1 |
  |---|---|---|---|
  | Wildfire-FM | 0.45% | 29.7% | 59.1% |
  | ClimaX | 0.35% | 29.8% | 60.2% |
  | AlphaEarth | 2.06% | 29.4% | 37.4% |

- Rankings moved under each rule: ClimaX went from 9th to 3rd, AlphaEarth from 1st to 6th.
- Choosing a model head by PR-AUC rather than by decision F1 cost decision performance ("selection regret").

**Concrete action for us (threads 1 and 5):**
- State the rule. Our "fire point in a top-10% square" is exact matching in space, with a day tolerance set by the 2-day window. Report a second version where a fire point within one square (500 m) of a selected square counts. Patrols see smoke and ash beyond the square edge, so that is closer to operational reality.
- Pick models and thresholds on the operational score (capture at the patrol budget), not on AUC.
- Expected: capture rises by several points under the tolerant rule [inference]. The *ranking of models* is what to watch.
- Effort: low.

### C6. Thapa, Maraseni, Dhonju, Shakya, Shakya, Apan & Banerjee 2025, "Predictive assessment of forest fire risk in the Hindu Kush Himalaya region using HIWAT data integration", *Remote Sensing* 17:2255 (Nepal / ICIMOD). **FULL** (20 pp; see also E1)
https://doi.org/10.3390/rs17132255

**What it shows (evaluation side):**
- 1,223 fire points (MODIS, VIIRS and field reports) on 11 selected dates, 10 Mar – 15 May 2023.
- Share of points per class: High 58%, Moderate 20.4%, Very High 4.6%, Low 6.9%, Very Low 10.1%, so "over 80% in Moderate to Very High".
- The **area share of each class is not reported**.
- The class thresholds were "empirically calibrated by trialling multiple value ranges against observed fire activity during recent peak fire seasons", and validation covers only 2023.

**Concrete action for us (thread 1):**
- [inference] This is the standard way capture-rate claims mislead: if Moderate-to-Very-High covers 70% of the map, 83% capture is a PAI of only 1.2.
- Every capture number we publish carries its area share and a random baseline. Our 84.6% at 10% area (PAI 8.5) is far stronger than "80% in the upper classes".
- When we compare against FSI weekly pre-fire alerts for MP, compute FSI's area share for the same days.
- Effort: low.

---

## Part D. Calibration per division and base-rate shifts

### D1. King & Zeng 2001, "Logistic regression in rare events data", *Political Analysis* 9:137-163. **PARTIAL** (sections 1-4.2)
https://gking.harvard.edu/files/0s.pdf

**What it shows:**
- When negatives are subsampled (or the population fraction of events τ differs from the sample fraction ȳ), the slope estimates stay consistent. Only the intercept needs fixing:
  β̂₀ − ln[((1 − τ)/τ) · (ȳ/(1 − ȳ))]
- Also covers weighting as the alternative, and a small-sample bias correction for rare events.

**Concrete action for us (threads 1 and 4):**
- Per-division calibration in two layers [inference]:
  - (a) **intercept-only shift per division and season**, using that division's training-season event rate τ_d, or a shrunk rate for low-fire divisions (empirical-Bayes mean between the division rate and the state rate);
  - (b) a **single pooled isotonic or Platt map** on top.
- Fit a separate isotonic map only for divisions with at least about 100 test-season positives; isotonic with fewer positives overfits [inference].
- For the 2022-24 satellite change, refit τ per season from the live label stream. This is the "prior shift" fix (Saerens et al. 2002, *Neural Computation* 14:21, **ABSTRACT ONLY**; their EM re-estimates τ from unlabelled outputs, not needed here because labels arrive daily).
- Score with a per-division reliability table, Brier score and log loss.
- Expected: ranking unchanged; expected-count error per division-season down sharply (Firelihood-style). This is what thread 5's staff budgets need.
- Effort: low.

### D2. Caron, Guyeux & Aynès 2024, "Predicting wildfire events with calibrated probabilities", ICMLC 2024 (FEMTO-ST author PDF). **FULL** (12 pp)
https://publiweb.femto-st.fr/tntnet/entries/20295/documents/author/data

**What it shows:**
- Three French departments (Ain 2,654 fires, Doubs 1,892, Yvelines 2,375). Each department is split into 10 K-means sub-regions of fire locations. Target = at least one fire per sub-region-day. Test 2018-22, generalisation year 2023.
- They smooth the fire series with a Laplacian kernel plus rolling means over 1-20 days (the effect saturates around 20 days), map it to (0,1) with a logistic regression, and *regress* on that smoothed target instead of the 0/1 label.
- Binary XGBoost: log loss 0.60, fire-day log loss 0.97, **ECE 9.9%**. With a sigmoid calibrator: ECE 2.7%, but fire-day log loss 1.59.
- Random forest: ECE 12.95% → 1.64% with sigmoid, fire-day log loss 0.93 → 1.60.
- "Regressive" XGBoost: ECE 2.27%, fire-day log loss 1.12.
- 2023 was slightly worse throughout.
- Weakness [inference]: the smoothed target uses *future* days (J+i). It is a legitimate training target but not something to score against. ECE was computed against weighted samples whose definition is unclear.

**Concrete action for us (thread 4):**
- The useful lesson: a global sigmoid calibration fixes reliability but can **pull fire-day probabilities down too far**. Check calibration separately on fire days and on all days, per division.
- For the 6/12/24/48 h burn-probability maps, try training on a kernel-smoothed target (fire within ±1 day, weight 0.5) only if fire-day log loss improves on the hold-out.
- Expected: small; mostly a warning.
- Effort: low.

### D3. Caron, Noura & Guyeux 2025, "A voting system to optimize daily forest fire prediction", ICTAI 2025 (author PDF). **PARTIAL** (abstract, sections 2-4)
https://publiweb.femto-st.fr/tntnet/entries/21858/documents/author/data

**What it shows:**
- One model is trained per smoothed version of the target: mean, max, min, cubic and quartic kernels, with windows of 1, 3 or 5 days or a "specialized" length (the mean run length per season and cluster, with sequences split by 3-day gaps). Then the models vote.
- The authors say the vote improves cross-region transfer and extreme days. I did not see per-department numbers in the sections read.
- Notes a department (Ain) with only 11 fires in 7 years at the coarse level.
- *Action (thread 1):* [inference] a cheap ensemble for low-fire divisions: train the new-fire model on the 0/1 label and on a ±1-day max-smoothed label, then average. Expected 0 to 1 point. Low priority.

---

## Part E. National and state systems in India and nearby

### E1. Nepal: ICIMOD / Department of Forests "Forest Fire Risk Outlook" inside the Forest Fire Detection and Monitoring System (Thapa et al. 2025, C6). **FULL**
- Inputs: HIWAT (WRF + GPM, 4 km, 54 h ensemble) noon temperature, RH, wind and 24 h rain. Outputs the Canadian FWI system (FFMC, DMC, DC, ISI, BUI, FWI), daily and 2-day, published as WMS.
- Five classes with locally tuned thresholds. The thresholds are not given in the paper.
- 2023 season: FWI peaked at 63.8 on 15 Apr; BUI rose from 11.0 (15 Mar) to 16.3 (10 May).
- March-April hold about 69% of Nepal's MODIS detections. Forests hold about 65% of detections each year (76.5% in 2019).
- **No fuel, vegetation or human-ignition input. No persistence or "active fire" term.** Recurring and new fires are treated the same.
- *Action (thread 1):* the regional equivalent of FSI's weekly FWI classes, run daily. It confirms that FWI-only systems in South Asia report no area-normalised skill. Use FWI class only as a "when" input and a baseline (C6).

### E2. Mohapatra, Sahoo, Das & Pradhan 2026, "Next-day forest fire risk prediction using machine learning and multimodal satellite data", *Eng. Proc.* 124:120 (Uttarakhand). **FULL** (4 pp)
https://doi.org/10.3390/engproc2026124120

**What it shows:**
- Data:
  - 1 Apr – 29 May 2016 only, 30 m daily 10-band stacks: ERA5 weather, SRTM terrain, land cover, NDVI.
  - Label: VIIRS S-NPP fire mask, medium and high confidence.
  - Split by days: train 1-27 Apr and 1-3 May, validation 28-30 Apr and 4-20 May.
- Model: ResUNet-A trained from scratch.
- Results:
  - Positive prevalence 0.0027% (3,377 of 123 million pixels).
  - Validation IoU/Dice about 0.7-0.8, inflated by large connected peak-season fires.
  - **Test patches: 4 true fire pixels in 13.1 million, 0 true positives.** The maximum predicted probability was 0.16.
- *Action (thread 1):* [inference] the only Indian next-day pixel model found, and it fails at 30 m. Our 500 m squares and 2-day windows are the right aggregation, and India still has no published daily division-level skill to benchmark against.

### E3. Indian state and national susceptibility papers (none daily, none per division with hold-out skill). **ABSTRACT ONLY** unless noted
- **Singh & Jeganathan 2024**, *Adv. Space Res.*: random forest, monthly fire probability for MP and Chhattisgarh. Forecast for 2018-2020 with "accuracy" 86.46% (MP) and 93.78% (CG); no AUC or capture rate in the abstract. Coverage: https://eos.org/articles/new-model-can-better-predict-areas-vulnerable-to-forest-fires-in-india
- **Khandwa vs North Betul divisions, MP**, *Environ. Monit. Assess.* 2024, doi 10.1007/s10661-024-12960-0 (not open access): 22 years of MODIS; a slight, non-significant rise in fires (about +3/yr in Khandwa, +1/yr in North Betul); risk-zone maps. The only division-level MP fire paper found.
- **Melghat Tiger Reserve (Maharashtra)**, *J. For. Res.* 2018, doi 10.1007/s11676-018-0826-z: frequency-ratio risk map 81.3% overall accuracy (kappa 0.78) vs AHP 79.3%, validated on FSI fire points.
- **Sharma, Gupta & Fatima 2022**, *IJWF*, doi 10.1071/WF22016 (all India, MODIS, six ML models): SVM AUC 0.908, ANN 0.903. The CSIRO PDF would not download (connection reset).
- **Mishra et al. 2024**, *Sci. Total Environ.* (Odisha 2001-2022, MODIS, 19 factors): RF precision above 94%, SVM 89%; 20.1% (RF) and 16.7% (SVM) of the area in "Very High".
- **IIT Delhi, EGU24-14686**: an ERA5 FWI framework with five classes per forest zone (2003-2021); "consistently high hit rate", "30-50% efficiency gain", no absolute numbers.
- **ISFR 2021** (secondary sources only): 2.81% of forest cover "extremely", 7.85% "very highly" and 11.61% "highly" fire prone; 64.54% "less fire prone". FSI pre-fire alerts are weekly and FWI-based per physiographic zone (parliament reply). I did not verify the class rules (fire-point frequency on a grid).
- **Telangana**: 13,479 SNPP-VIIRS fire incidents, Nov 2023 – Jan 2024 (Deccan Chronicle report; news only).
- **MP department documents**: the FFPM plan approval mentions fire watchers in all 63 territorial divisions and 8 wildlife areas of MP (2019-20 order, https://moef.gov.in/uploads/2019/08/41mp.pdf). No list of fire-prone compartments was found online; the existing `ground_truth_sources.md` request list covers this.
- *Action (thread 1):* [inference] treat MODIS-based "accuracy" figures as non-comparable: random splits, balanced pseudo-absences, no area share. The only usable comparator is FSI's own weekly class or static risk zone, scored with our per-division capture/PAI. This repeats what earlier notes recommended; it is listed so the gap is clear.

---

## Datasets and code

| Item | What it gives us | Link | Thread |
|---|---|---|---|
| GPBoost (Python/R, LightGBM trees + random effects + GP) | Division random intercepts and slopes, cold-start shrinkage, Bernoulli likelihood | https://github.com/fabsig/GPBoost | 1 |
| LightGBM `init_model` (continued training) | Pooled pretrain, then per-division fine-tune | LightGBM docs | 1 |
| AlphaEarth Foundations annual embeddings (64-d, 10 m) | Static features that transfer to low-fire divisions; use year t-1 | Earth Engine `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` | 1 |
| CAST R package (`aoa()`, `knndm()`) | Area of applicability per division; spatial CV folds | CRAN `CAST` | 1 |
| Caron et al. French department dataset code | Department-aware features (history kernels, CatBoost ID encoding, DTW clusters), ordinal per-department targets | https://github.com/NicolasCaronPro/Localized-Forest-Fire-Risk-Prediction-ADepartment-Aware-Approach-for-Operational-DecisionSupport | 1 |
| Wildfire-FM weights and evaluation contracts | Exact / tolerated / union matching code idea | https://huggingface.co/RAI-Lab/Wildfire-FM | 1 |
| Graff et al. 2020 two-Poisson hurdle (code linked in the paper) | Template for separate active vs new models | https://doi.org/10.1109/TGRS.2020.2968029 | 1 |
| Nepal FFDMS outlook (HIWAT FWI, WMS) | Regional FWI baseline design | ICIMOD SERVIR FFDMS portal | 1 |
| King & Zeng prior correction | Intercept fix after negative subsampling or base-rate shift | https://gking.harvard.edu/files/0s.pdf | 1, 4 |

---

## Ranked action list

Gains and efforts are my estimates [inference] unless a number comes from our own data.

| # | Action | Thread | Inputs | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Per-division report card** on 2022-24: capture at 2/5/10/20% of area, PAI, PPAI at patrol area, new vs recurring capture, bootstrap intervals; median and fire-weighted mean (A6, C4) | 1 | Existing predictions, FSI points | Shows the true spread; probably a median well below 84.6% | Low (half a day) |
| 2 | **Leakage audit / model info sheet**: history-feature lags ≥ 2 days, scaling and ID encoding fitted on 2019-21 only (C3) | 1 | Feature code | Protects the headline; may lower it | Low |
| 3 | **Satellite-regime fix**: S-NPP-only label variant, satellites-per-season feature, per-season intercept refit (A7, D1) | 1, 5 | VIIRS by satellite | Ranking ±0; expected-count error per division-season much lower | Low |
| 4 | **Separate "new" and "active" models**, allocated by calibrated probability (B1) | 1 | Same table plus the 5 km / 7-day flag | New-fire capture +2 to 5 points (56.5% → about 60%) | Low |
| 5 | **One pooled LightGBM with division ID and descriptors** vs 87 models; plus a 5-8-group partition variant (A1) | 1 | Same table plus division descriptors | Low-fire divisions +several points; others about the same | Low |
| 6 | **Two-layer calibration**: per-division intercept shift (shrunk τ) plus pooled isotonic; per-division reliability, fire-day vs all-day checks (D1, D2) | 1, 4, 5 | Hold-out predictions | Correct probabilities and budgets; no ranking change | Low |
| 7 | **Tolerant matching score** (fire within 1 square counts) next to exact; choose models on capture at the patrol budget (C5) | 1, 5 | Predictions | Clearer model choice; capture +several points under the tolerant rule | Low |
| 8 | **GPBoost with division random intercept and weather slopes**, scored with leave-division-out plus a 10 km buffer (A2, C1) | 1 | Subsampled table | Cold-start divisions +2 to 5 points; better calibration | Medium |
| 9 | **Pretrain pooled, fine-tune per division** (`init_model`, 50-200 trees) (A8) | 1 | Same | 0 to 2 points in fire-rich divisions | Low |
| 10 | **AlphaEarth t-1 embeddings** as static features, tested on low-fire divisions with leave-division-out (A5) | 1 | Earth Engine export | Cold-start +1 to 3 points | Medium |
| 11 | **Area of applicability flag per division** on the alert page (C2) | 1, 5 | Features plus importance | Trust signal only | Low |
| 12 | **Statewide vs per-division top-X%**: both rankings, the statewide one on calibrated probability (A4) | 1, 5 | Calibrated predictions | Correct cross-division patrol allocation | Low |
| 13 | **Division "busy-day level" target** (ordinal per-division count classes) for DFO-level alerts (A6) | 1, 5 | Division-day counts | New product; skill unknown | Medium |
| 14 | **Per-division FWI-percentile logistic** as the "when" baseline (A3) | 1 | POWER/ERA5 FWI | Baseline only | Low |
| 15 | Smoothed-target ensemble for low-fire divisions (D3) | 1 | Same | 0 to 1 point | Low |

## Reading tally

- **FULL (10):** Shmuel 2025; Liu & Mostafavi 2025; Zhuang 2026 (AlphaEarth); Caron 2025 department-aware; Caron 2024 calibrated; Pimont 2021 Firelihood (bioRxiv via the fetch tool); Graff 2020; Ploton 2020; Thapa 2025 (Nepal); Mohapatra 2026 (Uttarakhand).
- **PARTIAL (8):** Montero-Manso & Hyndman 2021; Sigrist GPBoost; Meyer & Pebesma (preprint); Kapoor & Narayanan 2023; Joshi 2020 (PPAI); Wildfire-FM 2026; King & Zeng 2001; Caron 2025 voting.
- **ABSTRACT ONLY (10):** Papadopoulos 2026 (NeurIPS); Rodrigues 2014 / Martínez-Fernández 2013 (GWLR); Saerens 2002; Singh & Jeganathan 2024; Khandwa–North Betul 2024; Melghat 2018; Sharma 2022; Mishra 2024 (Odisha); IIT Delhi EGU24; ISFR 2021 fire-prone figures (secondary sources).
- **Blocked:** HAL postprint of Firelihood (bot check; got the bioRxiv copy instead), the CSIRO PDF of WF22016 (connection reset), the Saerens 2002 repository copy (error page). The Consensus search quota for the month was used up, so all searching was done through web search.
- Downloaded copies: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r11_region/` (session-local).
