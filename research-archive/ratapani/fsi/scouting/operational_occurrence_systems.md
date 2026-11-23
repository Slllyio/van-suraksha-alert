# Operational daily fire-occurrence prediction systems: what agencies run, how they score it, and what we can copy (scouting round 3, topic: ops)

Scope: the daily ignition-prediction systems that agencies actually run, and the research models behind them. For each one I give the resolution, the inputs (especially stand-ins for human activity), the model form, how thresholds or resources are set, the validation numbers, and the lessons. Everything is aimed at thread 1 (the 2-day, 500 m LightGBM: 29.5 % recall at 5 picks/beat/day, against 16.6 % for random picks) and thread 5 (live alerts).

I did not repeat sources already covered in `short_horizon_prediction*.md` (Yang & Woolford 2026, Phelps & Woolford 2021, the Nadeem et al. headline, Marey-Pérez 2023, ECMWF PoF, FSI pre-fire alerts, Barik/IIT Delhi FWI work, KBDI), `small_data_models.md` (Mesogeos and FireCube for Greece), `field_alert_systems.md` (INPE Queimadas as an alert service, SiPongi) or `leaf_fall_phenology.md` (the spring burning window). Where I add to one of those, I say so.

Labels used in this note:
- **FULL**: the whole text was read.
- **PARTIAL**: some sections were read.
- **ABSTRACT ONLY**: only the abstract or metadata was read.
- **[inference]**: my own reasoning, not a finding from the source.
- Gains are my estimates in recall points at 5 picks/beat/day, unless stated otherwise.

---

## Headline findings

1. **Every mature operational system (Ontario, BC, US Predictive Services, Madrid, Galicia) reports daily counts with intervals, not only ranked maps.** Each one checks that the sum of cell probabilities matches the observed daily count, and that a 95 % Monte Carlo interval covers the observed count about 95 % of the time. Ontario reports 98 % coverage in 2017 for its Northwest Region. Over 2016-18, coverage was 99.7 % in the Northwest Region and 94.8 % in the Northeast Region. We report neither number. Both are cheap to compute and would make the live system credible to officers.
2. **Recent nearby fires are the strongest daily human-ignition signal anyone has measured.** In Galicia's 19 district models, a fire in a *contiguous* district the day before raises the log rate by **+0.8 to +1.7**, and the district's own count the day before has an autoregressive coefficient of **0.23-0.48**. The effect persists **2-3 days** and cut out-of-sample RMSE by about 15 %. Brazil's INPE forces any cell with a satellite fire in the last 3 rain-free days up to "high" risk. That single rule raised its hit rate by **10-30 percentage points** in the low-fire months (Jan-Jun and Oct-Dec).
3. **How negatives are sampled decides whether a map is useful.** A 2026 western-US model trained on random "no-fire" points scored 99.8 % accuracy. It then painted the whole West high-risk on a bad-weather day, and only 67-80 % of hard negatives (same date nearby, or same place another date) were classed correctly. Adding those hard negatives to training raised that to **96-100 %** while still catching 82 % of human ignitions [Pourmohamad 2026]. Our within-beat top-5 metric is already a "same date, nearby" test, which is good. If we ever subsample negatives for training, they must be stratified this way.
4. **Weekday and holiday effects are real in the West but sanctuary-wide flags are the wrong form for us.** Galicia's coefficients are Saturday +0.10 to +0.39 and Sunday +0.13 to +0.73 (log scale). BC finds Friday-Monday positive and Western Australia uses a work-day flag. [inference] In Ratapani, ignition follows mahua and tendu work, and village market (haat) days differ from village to village. That may be why our single calendar flag gave nothing. A **beat-specific market-day flag** is the version nobody has tried.
5. **Linear infrastructure is a top predictor wherever it is mapped:** railways (Ontario, Madrid), power lines (the top variable for intentional fires in Chile), and trails (Korea, odds ratio 4.3). [inference] Ratapani is crossed by the Bhopal-Itarsi railway and NH-46, and probably by transmission lines; check this on OSM. We have only "village distance".
6. **Operational scoring conventions to copy:** the 95 % interval coverage and daily-count MAE/RMSE above; reliability diagrams; a "fraction of fires captured vs fraction of area-days flagged" curve, never a hit rate on its own; relative economic value (cost-loss) curves; a persistence baseline and a same-week-last-year baseline; and a separate check on a shock year (COVID 2020 cut recall from 83 % to 24 % in the US).

---

## Part A. Canada

### A1. Woolford, Martell, McFayden, Evens, Stacey, Wotton & Boychuk 2021, "The development and implementation of a human-caused wildland fire occurrence prediction system for the province of Ontario, Canada", *Can. J. For. Res.* 51:303-325. **FULL** (accepted manuscript, 66 pp)
Link: https://doi.org/10.1139/cjfr-2020-0313 · OA copy: https://utoronto.scholaris.ca/bitstreams/1b47d62e-3515-4b8d-aaaa-9096b2d43502/download

**What it is.** This is Ontario MNRF's operational human-caused fire occurrence prediction (FOP), used in daily planning since 2015. Prediction intervals were added in 2016.

**Resolution.**
- About 10 × 10 km UTM cells, daily, for April-October.
- Training data: 1963-2012. The area covers 73.8 Mha in three strata: the Northwest Region, the southern Northeast Region, and a set of far-north communities.
- The 10 km cells nest inside the 20 km cells of the lightning FOP (Wotton & Martell 2005), so the two maps can be shown together.

**Model.**
- A logistic GAM on space-time voxels, following Brillinger et al. (2003), fitted in mgcv.
- All fire voxels are kept, plus **1 % of zero-fire voxels** (10 % in the far north, where there are few cells). An offset corrects the probabilities for this sampling.
- They warn that too low a sampling rate distorts the fitted smooth effects.
- Models are stratified by two **seasonal cause groups**:
  - Category 1 (recreation, industrial, incendiary): a spring peak and a large mid-summer peak.
  - Category 2 (resident, miscellaneous, railway, unknown): a spring peak and two smaller summer peaks.
- Fires of unknown cause are treated as human-caused.

**Inputs and the fitted NWR Category 2 model.**
- Ecoregion intercepts, ranging from −1.3 to +0.88 relative to −11.08 on the log-odds scale.
- An indicator for ≥ 10 % non-fuel: −1.75 (SE 0.72).
- s(day of year), s(longitude, latitude), s(FFMC).
- s(railway length) and s(primary road length), each fitted only in cells that contain the feature.
- s(% HAI).
- An annual trend in some models. Local roads and residential roads in others.
- All smooth terms had p < 0.0001.
- FFMC is the only daily weather term.

**HAI (human activity and interface index).** This is the novel human proxy. Fire staff in each of the 13 response sectors drew polygons of sparse, moderate or heavy human activity, at whatever scale they chose. The polygons were merged with buffered roads and lakes. The predictor is the % of each cell under moderate or heavy HAI. The authors say the exercise also built trust in the model.

**Arrival vs ignition.** 50 % of human-caused fires are reported within 1.6 h of ignition and 90 % on the day of ignition, so they model report date.

**Outputs and how they are used.**
- Cell probabilities are summed to give the expected number of fires per sector or region.
- **Monte Carlo prediction intervals:** simulate Bernoulli outcomes in every cell and take the 2.5th and 97.5th percentiles of the simulated daily total. Staff were already used to giving ranges such as "0-2 fires", so they wanted ranges.
- Maps use a **20-class colour scale** with breakpoints from a power function f(x) = a·x^b, 0 < b < 1, because "concern rises quickly at first, then more slowly". Greens are avoided for colour-blind users.
- Human-caused FOP is capped at "high". "Extreme" is kept for lightning surges.
- Legend units are "fires per cell" when the expected count is high and "**cells per fire**" when it is low. For example, the low/moderate boundary is about 30 cells per fire.
- The GAMs are deployed as **lookup tables**: each smooth is discretised (FFMC in steps of 0.1) and its additive log-odds read off a table. This avoids running R in the agency software.
- Every afternoon, sector response officers still submit a subjective forecast of the next day's fires, and the model is used alongside it.

**Validation (2016-18, operational years).**
- NWR 2017: RMSE of daily count 1.31, MAE 1.08. The 95 % interval covered 107 of 109 days (98 %).
- 2016-18 coverage: 99.7 % (NWR) and 94.8 % (NER).
- Sector-month MAE ranged from 0 to 1.95, with 94 % ≤ 0.5. RMSE was ≤ 1.0 in 97 % of cases.
- No AUC is reported. The checks that mattered to the agency were count accuracy and interval coverage, plus overlay maps.

**Lessons and failures the authors list.**
- The historical data may not represent current responsibility: about 10 % of fires were handed to municipalities after 1998.
- The HAI is a fixed snapshot of expert opinion.
- Restricted fire zones (burn bans) are not yet in the model.
- Power-line fires caused by wind "spread out" in time and space and need their own model.
- Plans: interaction smooths of season × sector, and finer cause groups (anglers, berry pickers, and so on).

**Concrete action for us.**
- (thread 1, evaluation) Add Ontario's checks to our backtest:
  - Sum the cell probabilities per beat and per day for the sanctuary, and compare with observed new burn scars.
  - Report MAE/RMSE of daily counts per range-month.
  - Report 95 % Monte Carlo interval coverage. This needs calibrated probabilities: isotonic-calibrate the LightGBM on a held-out year.
  - Expected effect: no change to recall, but the first count-calibration numbers we can show officers.
- (thread 5) The daily bulletin should give "expected new fires today in your range: 3 (1-6)" plus a map in "cells per fire" units with a non-linear colour scale.
- (thread 1, new feature) Run a **Ratapani HAI exercise**:
  - Ask each of the 94 beat guards to mark polygons on a printed beat map: heavy, moderate or sparse human use in Feb-May (mahua groves, tendu phads, cattle routes, footpaths, firewood areas).
  - Rasterise to % of each 500 m cell.
  - Expected **+1 to 3 pts** on "where". This targets our puzzle that interior cells ignite about 2× more than cells near villages: the activity may be at the mahua and tendu sites, not at the villages.
  - Effort: one week of field coordination.
- (thread 1) Stratify the season. Fit separate models, or add interaction features, for the mahua window (about Mar-mid Apr) and the tendu window (about mid Apr-May), as Ontario does with its two cause groups. Expected 0 to +1 pt, since LightGBM already sees day of year.

### A2. McFayden, Woolford, Stacey, Boychuk, Johnston, Wheatley & Martell 2020, "Risk assessment for wildland fire aerial detection patrol route planning in Ontario, Canada", *IJWF* 29:28-41. **FULL** (main text read via the publisher page; the equation images and Tables 4-7 did not render)
Link: https://connectsci.au/wf/article/29/1/28/21506/Risk-assessment-for-wildland-fire-aerial-detection

**How the FOP output is turned into patrol decisions.**
- Ontario computes a **Detection Demand Index (DDI)** on about 20 × 20 km cells for a 1-day horizon.
- **Likelihood factor Lf:** the human FOP (expected fires per day) and the lightning FOP (expected holdover fires still undetected, which differs from expected arrivals) are each mapped to ordinal classes 1-10, combined, then raised to the power **0.8**.
- **Fire behaviour:** head fire intensity at 17:00 for the dominant fuel type, compressed with an elicited polynomial.
- **Values at risk:** 10 senior staff scored 25 asset and resource types from 0 to 10. The median score is multiplied by the count, km or ha per cell and summed, capped at 40 000, then raised to the power **0.5**.
- The three factors are **multiplied**, so any factor near zero sends the cell's demand near zero. The result is scaled to 0-100 and binned 1-10.
- **ADDI** then discounts cells where the public is likely to report a fire within 4, 8, 12 or 24 h, based on 1998-2013 report data.
- There is no automatic trigger threshold. Detection Leaders still draw the routes.

**Evaluation.** On 1 Jun-15 Aug of 2016 and 2017, the authors matched aircraft GPS "heartbeats" to cells: a "look" is a cell centroid within 20 km of a heartbeat. In a logistic GLM, the probability of a look rose with ADDI (p ≈ 0). This is a check of uptake, not of skill. Staff said the index worked under average conditions.

**Concrete action for us (thread 5).** Rank the daily field-check list by **risk × consequence**, not risk alone:
- Lf^0.8 × (values)^0.5, where values = plantation or regeneration area, tiger or core-zone cells, and distance from the nearest watcher.
- Discount cells that a watchtower can see (field_alert_systems/management notes have the viewshed idea).

Effect: a better use of patrol time, not a change in recall. Effort: low once the layers exist.

### A3. Nadeem, Taylor, Woolford & Dean 2020, "Mesoscale spatiotemporal predictive models of daily human- and lightning-caused wildland fire occurrence in British Columbia", *IJWF* 29:11-27. **PARTIAL** (about 70 % of the text; the discussion is cut off). This adds detail to the one-line entry in `short_horizon_prediction.md`.
Link: https://connectsci.au/wf/article/29/1/11/21497/Mesoscale-spatiotemporal-predictive-models-of

**Resolution and data.**
- 20 × 20 km cells (2 541 in BC), daily, 16 Mar-14 Oct.
- Human-caused model trained on 1981-2008 and tested on **2009-14**. This is a temporal hold-out, not leave-one-year-out.
- Fire occurs in only **0.18 %** of human-caused voxels.

**Model.**
- Lasso logistic regression (glmnet).
- **500 balanced bootstrap samples:** all fires plus an equal number of random non-fire voxels in each, with an offset of log(p1/p0). The results are averaged as an ensemble.
- The authors note the sampling ratio can be tuned like a hyperparameter.

**Human-caused predictors.**
- Road length, interpolated population, distance to the wildland-urban and wildland-industrial interfaces.
- A "**baseline risk**" term: the historical fire density of the cell, entered as logit and logit².
- Day-of-week indicators: **Friday-Monday positive, Tuesday-Thursday negative**.
- Seasonality from NDVI spline fits and the start and end dates of the fire season.
- A 1992 change-point.
- Wind and ISI.
- No lagged human-fire counts. Lags were used only for lightning.

**Numbers.**
- AUC > 0.9 for all models; the human-caused model is the lowest of the three.
- Specificity of the human-caused model 0.811.
- About 4.5-4.7 % higher AUC than a single ordinary logistic regression.
- Temporal RMSPE 1.10 and spatial RMSPE 0.77 for the human-caused model.
- Example day, 3 Aug 2009: 7.4 predicted vs 10 observed human-caused fires.

**Variables that mattered most.** Baseline risk was top in every model. Then relative humidity, previous-day rain, SDMC and PSUF. For human-caused fires, distance to the wildland-urban interface (negative), the change-point, wind and ISI. Vegetation terms were weakest, which the authors blame on the 20 km scale.

**Failures.** The human-caused model over-predicts from June onward. Spatial prediction is harder for human-caused fires than for lightning fires. The authors suggest **mobile-phone location data** as a better measure of human activity.

**Concrete action for us (thread 1).**
- Copy the **bagged balanced-sample ensemble**: 50-500 LightGBMs, each on all positives plus a fresh random or stratified set of negatives, with predictions averaged. This mainly stabilises the top-5 ranking from day to day. Expected 0 to +1 pt, plus smoother ranks.
- The 2009-14 temporal hold-out is the convention to copy: train on 2017-2023 and test on 2024-26, rather than random or leave-one-out splits.

### A4. Magnussen & Taylor 2012, "Prediction of daily lightning- and human-caused fires in British Columbia", *IJWF* 21:342-356. **ABSTRACT ONLY**
Link: https://connectsci.au/wf/article/21/4/342/119252/Prediction-of-daily-lightning-and-human-caused

- Binary logistic regression on 950 cells of 20 × 20 km, daily, 1981-2000.
- **Coefficients fitted separately for each year.** Forecasts use the mean coefficient, and the spread of the 20 yearly models gives the confidence interval.
- Leave-one-year-out validation. Provincial daily counts: R = 0.83 for lightning but only **R = 0.55 for human-caused** fires, and worse at regional scale.

**Lesson.** Human ignitions are much harder to forecast than lightning, even for strong agencies.

**Concrete action for us (thread 1, uncertainty).** Train one LightGBM per held-out year (we have about 9 seasons). The spread across the 9 models gives a per-cell uncertainty band for the bulletin at no extra modelling cost.

### A5. Alberta: what the province runs. **ABSTRACT ONLY** (search level)
Links:
- Vega-García et al. 1995, Whitecourt Forest: https://publish.csiro.au/wf/WF9950101
- Morrison 2016, MSc thesis: https://era.library.ualberta.ca/files/cxd07gs955/Morrison_Kimberly_H_201609_MSc.pdf
- Phelps & Woolford 2021 (already covered)

Findings:
- **Vega-García 1995** was the first logistic human-caused FOP with sampled non-fire cells and an offset. It predicted 79.0 % of fire days and 81.5 % of no-fire days. A neural-net follow-up (1996) predicted 78 % of fire days and 85 % of no-fire days.
- **Morrison 2016:** a negative-binomial GLM with FFMC, FWI, ecoregion and season was best. The author says **spring fire starts are the weakest part**.

I found no public document describing Alberta Wildfire's current operational FOP. [inference] Its ML work runs through the Woolford group (Phelps), so the conventions are the same as Ontario's.

---

## Part B. United States

### B1. Pourmohamad, Abatzoglou, Fleishman, Belval, Short, Williamson, Perlmutter, Seydi & Sadegh 2026, "Predictive understanding of wildfire ignitions across the western United States", *Earth's Future* 14:e2025EF006935. **FULL**
Link: https://doi.org/10.1029/2025EF006935 · PDF: https://www.nwfirescience.org/sites/default/files/publications/Earth%20s%20Future%20-%202026%20-%20Pourmohamad%20-%20Predictive%20Understanding%20of%20Wildfire%20Ignitions%20Across%20the%20Western%20United%20States.pdf

**Data.**
- FPA FOD v6, augmented to **FPA FOD-Attributes**: about 270 attributes attached to every ignition (Pourmohamad et al. 2024).
- 383 872 western-US ignitions from 2000-2020, after removing records that combine all three of: reported by county or local agencies, < 0.1 acre, and on developed land.

**Model.** XGBoost (it beat RF and 1D-CNNs) on 29 attributes:
- day of discovery (DOY), fire year
- VPD, minimum temperature, 100-h and 1000-h fuel moisture, burning index, ERC and ERC percentile, wind, rain
- climate normals, topography within 1 km, vegetation type
- GDP, Global Human Modification (GHM), population, social vulnerability
- national preparedness level, county FIPS code, protected-area status

**Absence sampling, the main point of the paper.**
- (i) "Hyper-sampling": a 4 km grid × 9 random dates per year, about 36.6 M points.
- (ii) SSS: the **same location as a past ignition, on 9 other dates**.
- (iii) TSS: the **same date as an ignition, at a random point within 4 km** (TSS-4) or 15 km (TSS-15).
- The IM model uses (i) only. The AIM model adds SSS and TSS-4.
- Split: 65/15/20 within 2000-2018, plus 2019 and 2020 as extra test years.

**Numbers (human-caused fires).**

| Model | Test precision | Test recall | Accuracy on SSS / TSS-4 / TSS-15 negatives | 2019 recall | 2020 recall |
|---|---|---|---|---|---|
| IM | 96.8 % | 78.3 % | 79.9 / 67.2 / 68.1 % | 76.2 % | **23.1 %** |
| AIM | 90.9 % | 74.6 % | 99.8 / 96.9 / 96.9 % | 64.9 % | 21.8 % |

- On 5 Sep 2019 (323 fires), the IM map was high almost everywhere, which the authors call "not useful for resource allocation". The AIM map was informative and still caught 82 % of human ignitions.
- On gridded maps, the share of fires correctly flagged rose with finer grids: 76 % at 4 km, 81 % at 1 km, 83 % at 250 m, 86 % at 30 m.
- Class weights changed nothing (99.95 % vs 99.96 % accuracy).

**SHAP drivers.** The top four are annual temperature, national preparedness level (negative effect, which the authors read as burn bans and closures), DOY and fire year. For human fires, the next are FIPS code, 1000-h fuel moisture and GHM. GHM has a hump-shaped effect: ignitions rise with human modification up to a threshold, then fall.
- A **weather-only model does not predict ignitions well** (their Text S1).
- At an arson site, predicted probability stayed high all year except in wet, cold spells.

**Failures.** COVID-2020 changed human behaviour, and recall fell to 22-23 %. Random-split testing inflates every headline number. The authors deliberately did no spatial blocking.

**Concrete actions for us.**
- (thread 1, evaluation) Add two **hard-negative test sets** to our backtest:
  - "same cell, other days in the same season": tests *when*.
  - "same day, cells within 2 km": tests *where*, which our top-5-per-beat metric already does.
  - Report recall or AUC on each separately. Expected: a diagnosis, not a gain. It tells us whether the 29.5 % comes from timing or from location.
- (thread 1, training) If we subsample negatives for LightGBM or for the bagged ensemble in A3, draw them **stratified**: half from the same day in the same or a neighbouring beat, and half from the same cell on other days. Do not sample uniformly. Expected 0 to +1.5 pts on top-5 recall.
- (thread 1, robustness) Score **2020** (lockdown during the Mar-Apr peak) and **2021** separately. If recall collapses as in the US, add a year-level "human activity regime" flag, or at least warn users. This is cheap.
- (thread 1) Try a **GHM-style human-modification layer** (Kennedy et al. 2019, 1 km, on GEE) and **county-level fixed effects**. For us that means beat ID or range ID as a categorical feature. Expected 0 to +1 pt. Beat ID may be partly captured by burn history already.

### B2. Preisler, Riley, Stonesifer, Calkin & Jolly 2016, "Near-term probabilistic forecast of significant wildfire events for the Western United States", *IJWF* 25:1169-1180. **PARTIAL** (methods and results)
Link: https://research.fs.usda.gov/treesearch/53305 · PDF: https://research.fs.usda.gov/download/treesearch/53305.pdf

**Setup.**
- Predictive Services Areas (PSAs), daily, Western US.
- Inputs: the human-made **7-Day Significant Fire Potential Outlook** (SFPO, a categorical forecast from GACC meteorologists, reliable since 2007) and gridded **ERC converted to a per-pixel percentile** of its own history.
- The authors say ERC percentile is more strongly related to large fires than raw ERC.

**Model.** Separate logistic models give P(≥ 1 lightning fire), P(≥ 1 recreation fire) and P(≥ 1 other human fire) per PSA-day. Each has terms for the PSA's attributes, a seasonal smooth in day of year by GACC, the SFPO category, and s(ERC). A conditional model gives P(significant fire | ignition).
- For days 2-7, **day-1 ERC is simply carried forward** (persistence), because ERC for fuel model G has a strong lag.

**Validation.** Reliability diagrams with 7 probability bins, and parallel boxplots of observed counts within each predicted-risk class. The odds of a lightning fire were 4.1× higher on SFPO "lightning" days than on "moist" days.

**Concrete action for us (thread 1).** The per-pixel percentile trick is already proposed in `short_horizon_prediction.md` §2, so it is not repeated. New here:
- (thread 1, issue-time honesty) For the t+2 target, carry the slow indices (KBDI, DC, days-since-rain) forward from day t, as Preisler does. Use forecast values only for the fast variables (RH, temperature).
- (thread 5) Add an officer-entered categorical field (each range officer's "fire potential tomorrow: low / normal / high") as a logged input. After one season, test it as a feature, the way SFPO was tested. Ontario also collects these subjective forecasts.

### B3. Prestemon, Butry & Thomas 2016, "The net benefits of human-ignited wildfire forecasting: the case of tribal land units in the United States", *IJWF* 25:390-402. **PARTIAL** (abstract, introduction, methods)
Link: https://research.fs.usda.gov/treesearch/50673 · PDF: https://research.fs.usda.gov/download/treesearch/50673.pdf

**Setup.** Weekly counts for 23 BIA tribal land units, Jan 1996-Oct 2008, with an out-of-sample hold-out.
- Models: an **autoregressive conditional Poisson (ACP)** model, with up to 5 lags of observed counts and lagged conditional means; random walk; annual moving average; "**CompStat53**" (the 5-week moving average centred on the same week a year earlier); and an equal-weight ensemble.
- **Results:** the simplest ACP was the best single model, and the **ensemble was better still**.
- **Net benefits.** A simulated "hotspot tool" moved law-enforcement effort to the forecast hot units. It gave large positive net benefits (suppression costs avoided) for **incendiary** fires, and little for accidental human fires. Clusters can arise from serial or copycat fire-setting and from particular events such as holidays.

**Concrete action for us (thread 1, baselines).** Report our model against three baselines:
- persistence: yesterday's burning cells and their neighbours
- CompStat53: the same 15-day window last year, by beat
- random

We already have random (16.6 %). Without persistence and same-window-last-year baselines, officers cannot tell whether the model beats "go where it burned last week". This is cheap. If persistence turns out close to 29 %, that is important to know.

### B4. FPA FOD and the US pyromes
FPA FOD v6 (Short 2022) is the national ignition database behind B1. The USFS "pyromes" product (Short et al.) is a static regionalisation, not a daily predictor. I did not read it [not read]. **No action**, apart from the data note in the datasets table.

---

## Part C. Spain and Portugal

### C1. Prestemon, Chas-Amil, Touza & Goodrick 2012, "Forecasting intentional wildfires using temporal and spatiotemporal autocorrelations", *IJWF* 21:743-754. Main paper **ABSTRACT ONLY**; supplementary tables S1-S4 **FULL** (12 pp of coefficients)
Links: https://connectsci.au/wf/article/21/6/743/119241/Forecasting-intentional-wildfires-using-temporal · supplement: https://research.fs.usda.gov/download/treesearch/42375.pdf

**Setup.** Daily counts of intentional fires in each of Galicia's **19 forest districts**. Trained on 1999-2003 and tested on 2004-06. The model is a Poisson autoregressive PAR(P) per district.

**Covariates, with coefficients for districts I-XII from the supplement (log scale).**
- Friday: −0.39 to +0.20 (mostly not significant).
- **Saturday +0.10 to +0.39** and **Sunday +0.13 to +0.73**. Significant in about half the districts.
- Holiday: −1.8 to +1.5 (rarely significant).
- Month dummies, with March and August-September highest in most districts.
- Previous day's modified FWI (+0.25 to +1.40), minimum RH (−0.6 to −1.8) and maximum wind (−0.2 to −1.8).
  - The negative wind sign is notable [inference: arsonists avoid windy days, or wind marks rain-bearing fronts in Galicia].
- Income, unemployment, district arrests over the past year, and Galicia-wide arrests in the previous period. Arrests sometimes had a significant negative coefficient.
- **Fires in contiguous districts at t−1: +0.17 to +1.74, almost all p < 0.001.**
- Fires in distant districts at t−1: +0.31 to +1.03.
- Contiguous districts at t−2: +0.12 to +0.74.
- Own lags: **P1 = 0.23-0.48** (all p < 0.01), P2 about 0.04-0.07, P3/P4 mostly not significant.

**Forecast skill.**
- Out-of-sample RMSE about 15 % lower than static Poisson, constant and random-walk models.
- Examples: Santiago district 2.11 vs 2.32 (Poisson), 3.29 (constant) and 2.33 (random walk). Bergantiños 1.69 vs 1.72, 2.32 and 2.03.
- Autocorrelation lasts up to 3 days (temporal) and 2 days (spatial).
- The abstract reports a long-run elasticity of fires to arrests of −0.94 (one more arrest → about −140 intentional fires across Galicia in the long run).

**Concrete action for us (thread 1, the top feature idea, refined).** `short_horizon_prediction.md` already proposes beat-level and ring counts of new ignitions. Galicia says how to build them:
- Use **separate features** for (a) the beat's own new ignitions on t−1 and t−2; (b) new ignitions in **adjacent beats** (shared boundary) on t−1 and t−2; and (c) new ignitions in the rest of the sanctuary on t−1.
- Use the *new-ignition* count, not active fire pixels.
- Keep lags 1-3 days and drop longer ones.
- Expected **+1 to 3 pts on new ignitions**, the same estimate as before, now with coefficient evidence.

**Concrete action (thread 1, allocation; new and cheap).** Fit a beat-day Poisson autoregression (or use the summed LightGBM probabilities) to predict *how many* new fires each beat will have. Then **allocate the daily pick budget across beats in proportion to expected count**, for example 470 picks per day sanctuary-wide with between 0 and 15 per beat, instead of a flat 5 per beat. Re-score recall at the same total budget.
- Expected **+2 to 6 pts** of sanctuary-wide recall [inference: fires are clumped by beat and day, so a flat 5 per beat wastes picks in quiet beats].
- Check with the DFO whether a variable list per beat is acceptable to field staff.

### C2. Vilar, Woolford, Martell & Martín 2010, "A model for predicting human-caused wildfire occurrence in the region of Madrid, Spain", *IJWF* 19:325-337. **ABSTRACT ONLY**
Link: https://connectsci.au/wf/article/19/3/325/23247/A-model-for-predicting-human-caused-wildfire

- Logistic GAM, **1 km² × daily**, for the 8 028 km² Madrid region, where more than 90 % of fires are human-caused.
- Socio-economic and weather covariates plus spatial and temporal smooths. Expected counts were predicted for 2002-05.
- **Significant effects: railways, roads, WUI inside forest, daily maximum temperature and rain.**
- Closest in scale to us among the European operational-style models.

**Action.** See the railway feature in the ranked list.

### C3. Padilla & Vega-García 2011, "On the comparative importance of fire danger rating indices and their integration with spatial and temporal variables for predicting daily human-caused fire occurrences in Spain", *IJWF* 20:46-58. **ABSTRACT ONLY**
Link: https://connectsci.au/wf/article/20/1/46/23293/On-the-comparative-importance-of-fire-danger

- 10 km grid, daily, 2002-05, peninsular Spain, with a separate logistic model for each of **53 ecoregions**.
- On a held-out 2005, the percentage correctly predicted ranged from **47.4 % to 82.6 % between ecoregions**.

**Lesson.** Skill varies hugely between regions even with one method, so a single headline number hides a lot.

**Action (thread 1, reporting).** Report recall per range and per beat, not only sanctuary-wide. Mark the beats where the model is no better than random.

### C4. Ríos-Pena, Kneib, Cadarso-Suárez & Marey-Pérez 2015/2017, binary structured additive regression (STAR) for daily wildfire occurrence in Galicia. **ABSTRACT ONLY**
Links: https://investigacion.usc.gal/documentos/5da705a82999527d16bbb6e4 · Procedia: https://publications.goettingen-research-online.de/bitstream/2/5960/2/1-s2.0-S1878029615003333-main.pdf

- 1 km × daily voxels. A Bayesian STAR model with a **structured spatial effect (Markov random field) plus an unstructured effect** per cell.
- [inference] This is the GAM-with-spatial-random-effect idea already proposed in `short_horizon_prediction.md`. No new action.

### C5. Gelabert, Jiménez-Ruano, Ochoa, … Vega-García & Rodrigues 2025, "Assessing human-caused wildfire ignition likelihood across Europe", EGUsphere-2025-143 (FirEUrisk). **PARTIAL** (abstract and setup)
Link: https://egusphere.copernicus.org/preprints/2025/egusphere-2025-143/egusphere-2025-143.pdf

- Random forest at **100 m** for 20 pilot regions, including Catalonia, Attica, Portugal and southern Sweden. Agency ignition records are combined with land cover, accessibility, population and dead fine-fuel moisture (DFMC).
- AUC 0.70-0.89.
- **The yearly anomaly in DFMC was the top variable in every region.** Among human factors, the order was distance to the WUI, then roads, then population, then wildland fraction.
- A model pooled across regions lost 0.10 AUC locally in Sweden and Attica.
- This is a structural (multi-year) map, not a daily operational product. I found no public document of a daily human-ignition model run by the Bombers de la Generalitat (Catalonia) [search].

**Action (thread 1).** Weak. A per-season DFMC anomaly would duplicate our day-of-year and NDMI features.

### C6. IPMA (Portugal), "Nota metodológica: cálculo do perigo de incêndio rural (2023): Índice Conjuntural e Meteorológico, RCM", v1.0, 16 Aug 2023. **FULL** (10 pp)
Link: https://www.ipma.pt/export/sites/ipma/bin/docs/relatorios/meteorologia/nota-metodologica-calculo-RCM2023-vf20230816.pdf

**What Portugal runs every day.** RCM is a **matrix** combining two inputs.
- **FWI**: from 120 stations at 12 UTC, IDW-interpolated to 1 km. Six classes with breakpoints 8.4 / 17.1 / 24.5 / 38.2 / 64. The ≥ 64 class was added on 1 Jun 2022.
- **ICNF's "perigosidade" (hazard)**: a decadal structural map for 2020-2030 at 25 m, updated each year with the burned areas of the previous 3 years ("conjuntural"). Classes 0-5. Resampled to 1 km by modal class, with class 0 recoded to 1.
- Matrix rows (hazard 1→5) × columns (FWI class 1→6):
  - 1 1 1 2 3 4
  - 1 1 2 2 3 4
  - 1 1 2 3 4 5
  - 1 2 3 4 5 5
  - 1 2 3 4 5 5
- **Aggregation to municipality and district (since 2020):** not the median. A unit takes the **most severe class that covers ≥ 20 % of its area** ("P80").
- When a municipality is at RCM 4 or 5, legal restrictions apply automatically (Decreto-Lei 82/2021).
- The note gives **no validation numbers**.

**Concrete action for us (thread 5).** For the beat-level traffic light sent to guards, use Portugal's **P80 rule**: a beat takes the class of its top 20 % of cells by area, not the mean. A few hot cells in a large beat should trigger the alert. Also consider a rule like "beat at class 4-5 → no-burning order and extra watcher", as Portugal does. This is an operational design choice, not a recall gain.

[inference] The matrix of slow structural hazard × fast weather class is a very simple, transparent baseline that officers would trust. Our LightGBM should beat it clearly, and showing that comparison helps adoption.

---

## Part D. Brazil

### D1. Setzer, Sismanoglu & Santos 2019, "Método do cálculo do risco de fogo do Programa do INPE, versão 11, junho/2019". **FULL** (31 pp)
Link: https://dataserver-coids.inpe.br/queimadas/queimadas/Publicacoes-Impacto/documentos/RiscoFogo_Sucinto.pdf

**What INPE runs.** Daily observed fire risk ("Risco de Fogo", RF) for South America, plus forecasts up to 5 days and 1-4 weeks using numerical weather forecasts. Published at about 1 km to 0.25°. The rule-based recipe:
1. **"Dias de secura" (PSE).** Rain over each of the previous 1-120 days is converted to decay factors, and PSE = 105 × fp1 × fp2 × … × fp91-120. The factors are:
   - fp1 = e^(−0.14·P1)
   - fp2 = e^(−0.07·(P2−P1))
   - fp3 = e^(−0.04·Δ), fp4 = e^(−0.03·Δ), fp5 = e^(−0.02·Δ)
   - 6-10 days: e^(−0.01·Δ); 11-15 days: e^(−0.008·Δ); 16-30 days: e^(−0.004·Δ); 31-60 days: e^(−0.002·Δ); 61-90 days: e^(−0.001·Δ); 91-120 days: e^(−0.0007·Δ)
   - P_n is cumulative rain over the last n days (mm) and Δ is the extra rain in that window. The PSE is capped at 120 days.
   - Rain comes from **IMERG** (GPM) and is the most heavily weighted component.
2. **Basic risk:** RB = 0.8 × (1 + sin((A·PSE − 90)·π/180)) / 2, a sinusoid in PSE whose speed depends on vegetation constant A:

   | Vegetation | A |
   |---|---|
   | dense ombrophilous forest / flooded | 1.5 |
   | **deciduous and seasonal forest** | **1.72** |
   | contact forest / campinarana | 2.0 |
   | wooded savanna | 2.4 |
   | open savanna / caatinga | 3.0 |
   | agriculture | 4.0 |
   | pasture / grass | 6.0 |

3. **Humidity and temperature factors:**
   - FU = −0.006 × RHmin + 1.3 (RH below 40 % raises risk)
   - FT = 0.02 × Tmax + 0.4 (Tmax above 30 °C raises risk)
   - RF = RB × FU × FT
4. **Latitude and elevation:** × (1 + |lat| × 0.003) × (1 + elevation_m × 0.00003).
5. **Fire override:** if a satellite active fire was detected in the cell in the last 3 days and there was no rain, a cell at minimum or low risk (0-0.4) is raised to **high (0.7-0.95)**.
6. **Classes:** minimum < 0.15, low 0.15-0.4, medium 0.4-0.7, high 0.7-0.95, critical > 0.95.

**Claimed skill.** "More than 95 %" of satellite fires fall in the medium + high + critical classes combined.

### D2. Sismanoglu & Setzer 2004, "Avaliação da previsão do risco de fogo … modelo ETA … 2003" (CBMET). **PARTIAL**
Link: https://dataserver-coids.inpe.br/queimadas/queimadas/Publicacoes-Impacto/documentos/200409_sismanoglu&setzer_cbmet8_fortaleza_638.pdf

- Adding the recent-fire override (fires in a low-risk cell over ≥ 3 rain-free days) raised the hit rate by **10-30 percentage points** for medium-to-extreme classes, and by 10-22 points for the high class. The gain was **mainly in the low-fire months (Jan-Jun and Oct-Dec)**, with more than 95 % of about 300 000 fires in medium+ classes.
- Example, January: 40 % → 61 % of fires in high-critical and 60 % → 79 % in medium-critical.
- Forecast days 2 and 3 were about 5 points worse than day 1 for the medium class.
- Forecast skill fell 20 points in the north-east wet season when Eta rain forecasts were poor ("50 % precipitation accuracy" in the south-east in summer).

**Lessons from D1-D2.**
- (a) Recent fire presence matters most in the **early or off-season**. For us that means Jan-Feb, before the March peak. [inference] Our recent-fire features should be checked for gain by month.
- (b) **INPE's skill metric is flawed:** "% of fires inside medium+ classes" ignores how much area and time are in those classes. Medium+ probably covers most of the dry season. **We must never report a hit rate without the share of cell-days flagged.**
- (c) Forecast rain error dominates forecast skill.

**Concrete actions for us.**
- (thread 1, new "when" feature) Compute INPE's **PSE (dias de secura)** from IMERG or POWER rain using the exact decay factors above. Also compute RB with A = 1.72 (deciduous). This is a ready-made, well-tested drought memory that we have not tried, and it takes about 30 lines of code. Expected 0 to +0.5 pt on top-5 recall (it is sanctuary-wide, so "when" only), and +0.02 to 0.04 Spearman on daily counts.
- (thread 1) Make sure we have the INPE rule as a feature: "**own cell or 8-neighbour had a VIIRS detection in t−1…t−3 and no rain since**". Check the gain separately for Jan-Feb.
- (thread 1, evaluation) Report a **capture-vs-effort curve**: the share of new fires captured against the share of cell-days flagged.

---

## Part E. Indonesia, Malaysia and South-East Asia

### E1. Nikonovas, Spessa, Doerr, Clay & Mezbahuddin 2022, "ProbFire: a probabilistic fire early warning system for Indonesia", *NHESS* 22:303-322. **FULL**
Link: https://doi.org/10.5194/nhess-22-303-2022 · code: http://github.com/ToFEWSI/ProbFire

**Setup.** 0.25° cells, **monthly**, lead times of 0-5 months.
- Target: P(monthly MODIS active-fire count > 10). That covers 5 % of cell-months but most of the burned area. The > 0 target covers 20 % of cell-months.
- **Model:** an MLP with 18 inputs, one hidden layer of 15 ReLU units, LBFGS, L2 α = 1. An MLP was chosen because it **gives well-calibrated probabilities**.
- **Inputs:** monthly rain plus rain in each of the 5 previous months (t−1…t−5); temperature; RH; annual land-cover features (peat, forest loss, oil palm and others); 5 sub-region flags.
- SEAS5 forecasts are bias-corrected to ERA5 by mean-and-variance adjustment.

**Evaluation conventions, the main reason it is here.**
- AUC, Brier score, reliability diagrams and probability of detection / false-alarm rate.
- **Relative economic value** against cost/loss ratio from 0.001 to 1. For reliable probabilities, the best decision threshold equals the user's cost/loss ratio.
- In the El Niño-driven regions (S Kalimantan, S Sumatra, S Papua), forecasts reached **more than 60 % of the value of a perfect forecast** at cost/loss ratios near the event frequency.
- In central Sumatra and west Kalimantan, where human drivers dominate, value stayed **below 60 %** and seasonal forecasts added nothing beyond 0-month lead.
- Climatology plus non-climate features already predicted the "any fire" target as well as SEAS5 did. Forecasts helped only for the rare, high-activity target.

**Concrete action for us (thread 1 and thread 5, evaluation).**
- Plot **relative economic value** curves for the 2-day model. Taking the cost of a patrol visit as a share of the loss from an unchecked fire, the curve shows which probability threshold maximises value. That threshold is the honest answer to "when should a guard be sent?".
- Separately, test whether our model has more skill for the **"large or many-cell burn"** target than for "any burn", as ProbFire found.
- Expected: no recall change; it supplies a threshold rule for thread 5.

### E2. Indonesian and Malaysian FDRS (BMKG; de Groot, Field and others). **Search level / slides only**
Links:
- LAPAN slides 2011: https://gofcgold.umd.edu/sites/default/files/fireit_meetings/Wildfire_RN_SA_2011/South%20Africa_RN/Indonesia%20(Orbita%20Roswintiarti,%20LAPAN).pdf
- Field 2018 GOFC slides: https://gofcgold.umd.edu/sites/default/files/fireit_meetings/GOFC_Fire_IT_2018/GWIS-GOFC_presentations/Monday_Afternoon/20181001.Field.pdf
- ASEAN haze portal: https://hazeportal.asean.org/?p=10687

**What they run.** The Canadian FWI system, operated by BMKG since April 2000 and recalibrated:
- **FFMC > 82** (also given as ≥ 83) for grass ignition potential.
- **DC > 400** for severe haze from peat.
- **ISI ≥ 6** for extreme grass-fire intensity.

**The evaluation line worth copying.** LAPAN 2011 reports that **78 % of hotspots occurred on days with FFMC > 81, which were only 20 % of days**. That is a capture-vs-effort statement. Field 2018 found FFMC computed from IMERG-Final rain matched MODIS fires best when gauges and satellite rain were combined.

**Concrete action for us (thread 1, a "when" baseline).** Compute FFMC from POWER or ERA5 and report "% of new fires vs % of season-days above FFMC threshold X" for Ratapani. This is the simplest baseline for the timing part. If FFMC already captures about 80 % of fires on 20 % of days, our timing component must beat that.

---

## Part F. Australia, Chile, South Korea, China, Greece, India

### F1. Plucinski, McCaw, Gould & Wotton 2014, "Predicting the number of daily human-caused bushfires to assist suppression planning in south-west Western Australia", *IJWF* 23:520-531. **ABSTRACT ONLY**, plus Plucinski's 2012 slides **PARTIAL**
Links: https://connectsci.au/wf/article/23/4/520/23532/Predicting-the-number-of-daily-human-caused · slides: https://sites.ualberta.ca/~wildfire/2012/PDFs/Matt%20Plucinski.pdf

**Setup.** Negative-binomial regression of daily human-caused fire counts in each of 10 management areas. Trained on 3 years and tested on an independent year.
- **Common model form:** fuel moisture content, **number of recent human-caused fires**, a **work-day indicator** (weekends and public holidays vs other days), and rain.
- Cause mix: deliberate 34.5 %, accidental 23.9 %, lightning 6.5 %, other 15.5 %, unknown 19.5 %.
- The slides show human-fire probability curves against fuel moisture, separately for work days and non-work days, and for deliberate vs all human fires.
- A Bushfire CRC summary reports **81-99 % of daily counts within the predicted range** around Perth.

**Lesson.** Daily prediction was **only operationally useful in the more densely populated areas dominated by deliberate ignitions**. In quiet areas, day-to-day noise swamps the signal.

**Action (thread 1).** Same as C1: a recent-count feature, plus a test of a work-day flag *by beat*.

### F2. Chile: Crespo Pérez 2024 (supervisor M. Rodrigues), Universidad de Zaragoza MSc thesis, "Modelización de igniciones de origen humano en Chile" (TAZ-TFM-2024-1379). **PARTIAL** (abstract, methods, results)
Link: https://zaguan.unizar.es/record/145769/files/TAZ-TFM-2024-1379.pdf

**Setup.**
- Random forest, **100 m, daily**, for all of continental Chile.
- CONAF ignition records 2009-2019: 229 813 records filtered to 66 057, excluding fires < 1 ha.
- **Separate models for intentional and unintentional fires.**
- Absences: random points outside a 500 m buffer around fires, drawn **on the same dates as real fires** (matching their time distribution), with spatial stratification.
- Inputs: distance to power lines (covered or bare), buildings and roads; fuel type; daily **DFMC** from C3S.
- 250 repeated models, with Moran's I checks on the residuals.

**Results.**
- Intentional fires: AUC mean 0.86 (range 0.80-0.91).
- Unintentional fires: AUC 0.835 (range 0.77-0.89).
- **Top variable for intentional fires: distance to power lines**, then roads and buildings, then DFMC.
- **Top variable for unintentional fires: distance to buildings.** Fuels contribute little.
- Intentional fires concentrate more tightly along the access network.
- Many runs had spatially autocorrelated residuals; 219 of 250 and 195 of 250 runs were kept.

**Other Chilean work (search level).** Deep-learning studies report F1 > 0.999 after class balancing, which is clearly a leakage or design artefact. A Maule Transformer has no baseline.

**Concrete action for us (thread 1).** Add **distance to power lines** and **distance to railway / NH-46** (OSM `power=line`, `railway=rail`, `highway=trunk`) as static cell features. Also try their interaction with day of year: Ontario's railway fires peak early in the season, when last year's grass is cured. Expected **+0.5 to 2 pts** if the lines cross high-fire beats [inference]. Effort: low.

### F3. South Korea: Youn, Lee, Lee & Kim 2026, "Human activities and wildfires: the impact of forest roads, trails, and forest management on wildfire occurrence", *Fire* 9:246. **PARTIAL**, plus KFFDRS background from search
Links: https://mdpi-res.com/d_attachment/fire/fire-09-00246/article_deploy/fire-09-00246.pdf · KFFDRS: https://www.doi.org/10.5532/KJAFM.2018.20.4.348

**What Korea runs.** The **KFFDRS** (National Institute of Forest Science and Korea Forest Service) combines a daily weather index (DWI) with a fuel index and a topography index, each on a 10-point scale.
- The DWI is a logistic model of maximum temperature, RH, **effective humidity** and wind, fitted per region (8-9 regional models) on 2000-2010 fires.
- Reported validation varies: "86 % predictive value in 2016" in one paper, 66 % in another.
- It is issued in spring (1 Feb-15 May) and autumn (1 Nov-15 Dec).
- The 2026 paper states that the operational system **includes no human factors**, even though most Korean fires are human-caused and weekend hiking has increased.

**The 2026 study.** 1 km cells in Gangwon and Gyeongbuk, Jan 2022-Aug 2025: 471 fire cells and 1 000 region-stratified non-fire cells. Logistic regression, RF and XGBoost were used for variable selection.
- **Effective humidity:** He = (H0 + r·H1 + r²·H2 + r³·H3 + r⁴·H4) / (1 + r + r² + r³ + r⁴) with **r = 0.7**, where Hn is RH n days before.
- AUC about 0.80 (LR 0.809, RF 0.801, XGB 0.795).
- **Trail density raises fire odds (odds ratio 4.3)**. Forest-road density lowers occurrence.
- Effective humidity coefficient −0.071 per %. Pseudo-R² 0.195.
- **Design flaw:** non-fire cells were given weather from a **random date**, so the weather effects are confounded with season. This is the mistake that B1 warns about.

**Concrete action for us (thread 1).**
- Effective humidity (r = 0.7, 5 days) is a trivially cheap "when" feature. Expected about 0 pt (we have RH and dryness already).
- More useful: map **footpaths and cattle trails** (from guards, or from high-resolution imagery in `high_res_imagery.md`) as a trail-density layer. This is the Korean analogue of the HAI in A1. Expected +0.5 to 2 pts if paths can be mapped.

### F4. China. **ABSTRACT ONLY** (search level)
Links:
- Fujian spatial GAM, monthly, 2006-2020: https://journal.hep.com.cn/jfr/EN/1160207867951243344
- Heilongjiang geographically weighted logistic: https://www.frontiersin.org/journals/forests-and-global-change/articles/10.3389/ffgc.2022.1040408/full
- Human-caused drivers by region, 2026: https://journal.hep.com.cn/jfr/EN/10.1007/s11676-026-02111-1

Findings:
- The published Chinese models are monthly or seasonal susceptibility models.
- In Heilongjiang, geographically weighted logistic regression beat plain logistic by 6.3-11.0 %. Spatial GAMs were best in Fujian.
- I found no documented daily operational ignition model with validation (the CMA forest fire danger forecast is weather-index based).

**Action.** None beyond the spatial random effect already proposed.

### F5. Greece
- Greek Civil Protection issues a daily expert-based fire-risk map.
- The ML research (Kondylatos et al. 2022, GRL, 1 km daily datacube; Mesogeos 2023) is covered in `small_data_models.md`.
- I could not retrieve the GRL full text here (Wiley returned 403). **ABSTRACT ONLY**: https://doi.org/10.1029/2022GL099368

### F6. India beyond the FSI weekly pre-warning
- `short_horizon_prediction.md` already covers the FSI pre-fire alerts (weekly, 5 km), Barik/IIT Delhi FWI calibration, KBDI, and the MP/CG susceptibility papers.
- **New:** Prabhakaran & Srivastava 2026 (IIT Roorkee), EGUsphere-2026-2474. **PARTIAL**. https://egusphere.copernicus.org/preprints/2026/egusphere-2026-2474/egusphere-2026-2474.pdf
  - WRF at 5 km and 1 km for Himachal Pradesh and Uttarakhand in 2024. VPD and FWI from WRF are proposed for daily alerts.
  - Validated against 98 IMD stations: VPD mean RMSE 0.86-0.91 kPa, mean bias +0.69 to +0.75 kPa, so WRF is too dry.
  - States that the **current Indian fire danger rating "operates at 10-day intervals"**.
- I found **no daily, sub-5 km operational ignition model anywhere in India**. Our 2-day, 500 m model has no domestic precedent to compare against, so the FSI weekly class is the only Indian baseline.

### F7. A cautionary example: Xu et al. 2026, "Trustworthy data-driven wildfire risk prediction and understanding in western Canada", arXiv 2601.01677. **PARTIAL**
Link: https://arxiv.org/abs/2601.01677 · code: https://github.com/SynUW/mmFire

- Reports F1 0.90 and PR-AUC 0.98 with a 1:2 positive:negative design that excludes negatives within 60 km and ±3 days of any fire.
- **Lesson:** excluding hard negatives makes the task easy and the numbers meaningless for patrol allocation. Our metric (top 5 within a beat, all cell-days) is far stricter. Do not compare our 29.5 % with headline numbers like these.

### F8. Taylor, Woolford, Dean & Martell 2013, "Wildfire prediction to inform fire management: statistical science challenges", *Statistical Science* 28:586-615. **PARTIAL** (fire occurrence section)
Link: https://arxiv.org/abs/1312.6481

- A review linking the Ontario, BC and Alberta FOP lineage to point-process theory: voxel logistic regression approximates the conditional intensity.
- Notes Xu & Schoenberg (2011): point-process models with **lagged weather and historical burn patterns** beat the raw Burning Index in Los Angeles.
- No new action. It is useful as the citation for "voxel logistic regression = point-process intensity" in our write-up.

---

## Part G. Evaluation conventions to copy (summary)

| Convention | Who uses it | What we would compute | Thread |
|---|---|---|---|
| Expected count = sum of cell probabilities; MAE/RMSE of daily counts per sector-month | Ontario (A1), BC (A3) | Per beat and range-month MAE/RMSE of new-ignition counts, after isotonic calibration | 1, 5 |
| 95 % Monte Carlo prediction-interval coverage of daily counts | Ontario (98 %; 99.7 / 94.8 %) | Simulate Bernoulli per cell from the calibrated probability, then coverage of the observed daily sanctuary count | 1, 5 |
| Reliability diagram, Brier score | Preisler (B2), ProbFire (E1) | Deciles of calibrated probability vs observed rate | 1 |
| Capture vs effort (share of fires on share of flagged cell-days) | Indonesia FFMC (78 % on 20 %), implicit in our recall@k | Curve for the whole season; never quote an INPE-style hit rate alone | 1 |
| Relative economic value vs cost/loss | ProbFire (E1) | Value curve; pick the dispatch threshold | 5 |
| Hard-negative test sets (same day nearby; same cell other days) | Pourmohamad (B1) | Separate "where" and "when" scores | 1 |
| Temporal hold-out, plus a shock-year check | BC (2009-14 test), US (2020 collapse) | Train ≤ 2023, test 2024-26; report 2020 and 2021 separately | 1 |
| Persistence, same-window-last-year and ensemble baselines | Prestemon (B3, C1) | Recall of "yesterday's burning cells + neighbours" and "same 15 days last year" | 1 |
| Per-region skill table | Padilla (C3: 47-83 %) | Recall per range and per beat | 1 |
| Ensemble of yearly or bagged models for uncertainty | Magnussen (A4), Nadeem (A3) | Spread of per-year or bagged models | 1, 5 |

---

## Datasets

| Name | Link | Resolution | Years | Licence | How to access |
|---|---|---|---|---|---|
| FPA FOD v6 (US ignitions) | https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.6 | point, daily | 1992-2020 | US public domain | Direct download (SQLite / GeoPackage). Useful only for method tests and pretraining experiments |
| FPA FOD-Attributes (about 270 attributes per ignition) | cited in Pourmohamad 2026 (Pourmohamad et al. 2024, ESSD) | point, daily | 1992-2020 | open (check record) | Linked from the paper's data statement |
| INPE Risco de Fogo daily grids and method | https://dataserver-coids.inpe.br/queimadas/queimadas/riscofogo_meteorologia/ | about 1 km to 0.25° | 2002-present | method document CC BY-NC 3.0; data open | HTTP directory. The **method** is what we need |
| GPM IMERG daily rain (the INPE PSE input) | https://gpm.nasa.gov/data/imerg | 0.1°, daily (half-hourly native) | 2000-present | NASA open | GEE `NASA/GPM_L3/IMERG_V07` |
| IPMA RCM method and ICNF hazard maps | https://www.ipma.pt/ (nota metodológica) · ICNF perigosidade | 1 km RCM; 25 m hazard | 2020-2030 structural | Portuguese public data | Method PDF; only the method is relevant to us |
| ProbFire code | http://github.com/ToFEWSI/ProbFire | 0.25°, monthly | 2002-2019 | see repository | Git clone. Cost-loss value code is reusable |
| mmFire code (western Canada) | https://github.com/SynUW/mmFire | daily | 2023-2024 | see repository | Git clone (cautionary design) |
| OSM railways, power lines, trunk roads, paths for Ratapani | https://download.geofabrik.de/asia/india.html | vector | current | ODbL | Geofabrik extract → rasterise to distance and length per 500 m cell |
| Global Human Modification (gHM) | GEE `CSP/HM/GlobalHumanModification` | 1 km | 2016 | CC BY 4.0 | Earth Engine |
| CONAF ignition records (Chile, for method comparison only) | via the Chile thesis and the CONAF statistics portal | point, daily | 1985-2024 | Chilean public | Not needed by us |

---

## Reading status

- **FULL (7):**
  - Woolford et al. 2021 (CJFR, accepted manuscript)
  - Pourmohamad et al. 2026 (Earth's Future)
  - Nikonovas et al. 2022 (ProbFire, NHESS)
  - Setzer et al. 2019 (INPE RF v11 method)
  - IPMA RCM 2023 note
  - McFayden et al. 2020 (IJWF, main text)
  - Prestemon et al. 2012 supplementary tables
- **PARTIAL (11):**
  - Nadeem et al. 2020
  - Preisler et al. 2016
  - Prestemon et al. 2016
  - Sismanoglu & Setzer 2004
  - Youn et al. 2026 (Korea)
  - Chile TFM 2024
  - Gelabert et al. 2025
  - Taylor et al. 2013
  - Plucinski 2012 slides
  - Prabhakaran & Srivastava 2026
  - Xu et al. 2026
- **ABSTRACT ONLY:**
  - Vilar 2010
  - Padilla & Vega-García 2011
  - Magnussen & Taylor 2012
  - Plucinski 2014
  - Prestemon 2012 main text
  - Ríos-Pena 2017
  - Kondylatos 2022
  - Vega-García 1995
  - Morrison 2016
  - the China papers
  - Indonesia FDRS (slides/search)
- IJWF moved to connectsci.au. Most papers there are paywalled for this proxy; OA items opened through WebFetch.

---

## Ranked action list

Gains are my estimates [inference], in points of top-5-per-beat recall unless stated.

| # | Action | Thread | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Allocate picks across beats by expected count** instead of a flat 5 per beat (same total of 470 per day, 0-15 per beat) | 1, 5 | Beat-day sum of calibrated LightGBM probabilities (or a Poisson AR on beat counts); re-score recall at the same total budget | **+2 to 6 pts** sanctuary-wide (needs field approval) | Very low (re-scoring only) |
| 2 | **Galicia-style recent-ignition lags:** own beat t−1, t−2; adjacent beats t−1, t−2; rest of sanctuary t−1; plus INPE's "VIIRS in own or neighbouring cell in last 3 rain-free days" flag; check gain by month (Jan-Feb especially) | 1 | New-ignition counts from dated scars and VIIRS; lags of 3 days maximum | **+1 to 3 pts** on new ignitions | Low |
| 3 | **Persistence and same-window-last-year baselines**, plus capture-vs-effort curve | 1 | "Yesterday's burning + 8 neighbours"; "same 15 days last year by beat" | Diagnostic (shows what the 29.5 % is worth) | Very low |
| 4 | **Count calibration and 95 % Monte Carlo interval coverage**; daily-count MAE/RMSE per range-month; reliability diagram | 1, 5 | Isotonic calibration on a held-out year; 1 000 Bernoulli simulations per day | Credibility; the bulletin can give "3 (1-6) fires expected" | Low |
| 5 | **Ratapani HAI mapping by beat guards** (heavy / moderate / sparse use; mahua, tendu, cattle, paths) | 1 | Polygons → % of 500 m cell; static feature | **+1 to 3 pts** on "where"; also builds trust | Medium (field week) |
| 6 | **Railway, NH-46, power-line and path distance or length features**, with a day-of-year interaction | 1 | OSM extract; distance and length per cell | +0.5 to 2 pts if the lines cross fire beats | Low |
| 7 | **Hard-negative diagnostic sets** (same cell other days; same day within 2 km) and stratified negative sampling for any subsampled training | 1 | As in Pourmohamad AIM | 0 to +1.5 pts; separates "when" from "where" | Low |
| 8 | **Bagged balanced-sample ensemble** (Nadeem) or per-year models (Magnussen) for stable ranks and uncertainty bands | 1, 5 | 50-500 LightGBMs with an offset, or 9 leave-one-year models | 0 to +1 pt; plus intervals | Low-medium |
| 9 | **INPE PSE ("dias de secura") and FFMC "when" features**; Indonesian-style "% fires on % days above threshold" baseline | 1 | Exact INPE decay factors, A = 1.72; FFMC from POWER | 0 to +0.5 pt; +0.02-0.04 Spearman on daily counts | Very low |
| 10 | **Beat-specific market-day (haat) and festival flags** instead of a sanctuary-wide weekday flag | 1 | Haat day per village → nearest beat; Holi, Mahashivratri fair dates | 0 to +1 pt (untested anywhere; this local form is our own guess) | Medium (needs village lists) |
| 11 | **Shock-year check:** score 2020 and 2021 separately | 1 | Existing predictions | Diagnostic | Very low |
| 12 | **Bulletin design from Ontario and Portugal:** non-linear 20-class scale; "cells per fire" units; P80 beat rule (worst class covering ≥ 20 % of the beat); risk × consequence ordering (Lf^0.8 × values^0.5); cost-loss threshold for dispatch; log officers' subjective next-day forecasts | 5 | Calibrated probabilities, values layer, officer form | Adoption, not recall | Low-medium |
| 13 | Two-window season models (mahua vs tendu), Ontario-style | 1 | Separate models or interaction features | 0 to +1 pt | Low |
| 14 | Effective humidity (r = 0.7) | 1 | 5-day RH | about 0 | Very low |
