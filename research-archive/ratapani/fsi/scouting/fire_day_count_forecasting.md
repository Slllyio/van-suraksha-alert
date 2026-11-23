# Forecasting fire counts, busy days and aggregated targets: what others do, and what our own predictions already show (scouting round 3, topic "counts", 14 Oct 2026)

Written for the "Rethink the 2-day question" thread. That thread is testing coarser targets: beat-week fire counts, sanctuary-level big-fire days, and spread from active fires.

Already covered elsewhere, so not repeated here:
- Ontario daily counts with prediction intervals, BC, Pourmohamad, Preisler 2016, Prestemon, Padilla, Plucinski (abstract), ProbFire and INPE: `operational_occurrence_systems.md`.
- Di Giuseppe 2020 FWI skill (below 20 % POD in the SE Asia region), Yang & Woolford 2026, Phelps & Woolford: `short_horizon_prediction_fullread.md`.
- SeasFire (Michail 2024) and Mesogeos: `small_data_models.md`.
- FSI weekly pre-fire alert and IIT Delhi FWI calibration: `short_horizon_prediction.md`.

Labels used below: FULL = whole paper read; PARTIAL = main sections read; ABSTRACT ONLY. [inference] marks my own reasoning.

---

## Headline findings

1. **We already have the aggregation gain, measured on our own LOSO predictions (Part A).** Summing the current 2-day cell model (`pipeline_lean`, LOSO 2017-24) over larger units raises the Spearman correlation with observed burn rates:

   | Unit | Spearman |
   |---|---|
   | beat-day | 0.50 |
   | beat-week | 0.58 |
   | range-day | 0.62 |
   | range-week | 0.65 |
   | sanctuary-day | 0.80 |
   | sanctuary-week | 0.85 |

   A LOSO climatology (beat factor × season-week shape, no weather and no model) already reaches 0.40, 0.50, 0.54, 0.56, 0.62 and 0.68 on the same units. The model's real added value is therefore **+0.08 to +0.10 at beat level and +0.17 at sanctuary level**.

2. **For "busy" sanctuary days, VIIRS persistence beats the model.** Busy means the top 10 % of 2-day windows by VIIRS detections.
   - AUC: model 0.834, detections in the last 3 days 0.865, simple rank-sum of both 0.870.
   - A negative-binomial (NB) count model on log(1 + detections in the last 3 days) gives LOSO MAE 7.7 detections per 2 days (constant-mean model: 12.6), with 95 % coverage of the nominal 90 % interval. Adding the model's mean probability did not lower MAE (8.0).

   So for a sanctuary busy-day product, persistence is the baseline to beat, and the cell model's "when" signal is largely already contained in recent detections. [inference] Most VIIRS detections on busy days are multi-day fires and clusters, not new ignitions.

3. **The US standard for "busy day" targets is exact and easy to copy** (FIRES / FireFamily Plus, Andrews & Bradshaw 1997):
   - fire-day = at least 1 fire discovered;
   - multiple-fire-day = at least N fires (default 5);
   - large-fire-day = at least 1 fire with final size at or above X (default 10 acres).

   Each is fitted by a logistic regression on one index. Decision classes are set at the 60/80/90/97th climatological percentiles of the index, so each class covers exactly 60/20/10/7/3 % of days (SFDI, Jolly 2019).

4. **Expected skill of percentile-class busy-day products elsewhere:**
   - **SFDI (CONUS):** the top 10 % of days (Very High plus Severe) hold 29 % of new fires, 58 % of area burned and 75 % of MODIS large-fire pixels. The Severe class (3 % of days) holds 10.7 % of new fires, a 3.6× lift.
   - **Meteosat FRP daily model (Mediterranean):** 72 % of very large energy-release events fall in the "extreme" class, 1.5× EFFIS. P(large event | extreme) = 16.5 %.
   - **Preisler & Westerling 2007 (1° monthly):** the observed large-fire rate is 76 % where the forecast is "extreme" and 3 % where it is "low".

   [inference] A Ratapani percentile class built on weather only should give about a 2-4× lift for new-fire counts in its top class, with a hit rate well below 50 %.

5. **India:**
   - Indian fire danger rating runs at 10-day steps (see the ops note).
   - The only Indian fire-count forecast I found is monthly ARIMA on 25 km cells (Kale et al. 2022, C-DAC/IMD). It reports R² 0.94 for tropical dry deciduous forest in year 1 and 0.64 over 3 years. That R² is almost all seasonal cycle, and the peak 2015 counts fell outside the 95 % bands.
   - IMD/NCMRWF heat-extreme verification (Singh et al. 2017): for Tmax > 40 °C in March, deterministic POD is about 0.25 with FAR 0.7-0.8, and it changes little from day 1 to day 9. The ensemble (NEPS) is more reliable from day 2 on.
   - No IITM/IMD extended-range fire product with skill numbers was found.

6. **Aggregation gain in the literature:**
   - No fire paper directly refits one model at several cell sizes and reports how skill changes.
   - Crime forecasting says the same qualitatively: Rummens & Hardyns 2021 (abstract only) find that higher space-time resolution lowers performance.
   - The Firelihood/Koh group in France scores at the month-département level because pixel-day scores are uninformative.
   - Our own Part A numbers are the best quantification available. [inference]

---

## Part A. Our own data: aggregation gain and busy-day skill (DATA, computed 14 Oct 2026)

**Inputs**
- `/mnt/project-files/ratapani/scoring/pipeline_lean_pred_loso_2017_24.parquet`: LOSO 2-day cell scores, 2.39 M valid cell-days.
- Labels: `pos` from `/mnt/project-files/ratapani/fsi/scouting/data/exp_preds.parquet`. These are first-burn, H = 2 labels with a base rate of 4.65 %. A row-for-row merge matched all 2,387,409 rows.
- Beats from `/mnt/project-files/ratapani/beats/cell_beat.csv` (94 beats). Ranges are the first 7 characters of `beat_uid` (13 groups).
- VIIRS detections from `/mnt/project-files/ratapani/fsi/scouting/data/viirs_cells.parquet` (reserve = Ratapani) and new events from `events.parquet`.
- Script: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/agg/agg.py` and `agg2.py` (scratch, not shared).

**Definitions**
- Unit predicted rate = mean cell score over the unit's valid cell-days.
- Observed rate = positives / valid cell-days.
- "Busy" = observed rate in the top 10 % of units within the season, and above 0.
- Climatology baseline (LOSO) = season-week burn rate from the other 7 seasons × the unit's relative rate in the other seasons.
- Units with fewer than 5 valid cell-days were dropped.

| Unit | n units | P(any positive) | Spearman, model | Spearman, climatology | AUC busy-10 %, model | AUC busy-10 %, climatology | POD / FAR when flagging top 10 % |
|---|---|---|---|---|---|---|---|
| cell-day (reference) | 2.39 M | 0.047 | – | – | AUC 0.827 (all cell-days) | – | – |
| beat-day | 76,657 | 0.29 | 0.50 | 0.40 | 0.799 | 0.779 | 0.35 / 0.65 |
| beat-week | 14,046 | 0.33 | 0.58 | 0.50 | 0.838 | 0.812 | 0.42 / 0.58 |
| range-day | 10,512 | 0.48 | 0.62 | 0.54 | 0.818 | 0.802 | 0.40 / 0.59 |
| range-week | 1,951 | 0.46 | 0.65 | 0.56 | 0.860 | 0.830 | 0.46 / 0.54 |
| sanctuary-day | 1,065 | 0.93 | 0.80 | 0.62 | 0.800 | 0.817 | 0.34 / 0.65 |
| sanctuary-week | 156 | 0.95 | 0.85 | 0.68 | 0.874 | 0.870 | 0.56 / 0.44 |

**Sanctuary-day against VIIRS** (2-day windows; mean 10.8 detections per window; 34 % of windows have none):

| Score | Spearman with detections on t+1..t+2 | AUC for busy (top 10 % of detections) |
|---|---|---|
| Model mean probability on day t | 0.72 (0.73 with new VIIRS events) | 0.834 |
| Persistence: detections on day t | 0.72 | 0.859 |
| Persistence: detections on t-2..t | 0.76 | 0.865 |
| Rank-sum of model and 3-day persistence | 0.78 | 0.870 |

**NB count model for the 2-day sanctuary detection count (LOSO, 90 % prediction interval)**

| Predictors | Coverage | MAE | α |
|---|---|---|---|
| logit(model) only | 0.95 | 9.9 | 1.46 |
| log1p(last-3-day detections) only | 0.95 | 7.7 | 1.34 |
| both | 0.94 | 8.0 | 1.13 |
| constant mean | – | 12.6 | – |

**What this means [inference]**
- Coarsening to beat-week gains about +0.08 Spearman over beat-day. Most of that gain comes from Poisson noise averaging out, not from new skill: the climatology gains the same +0.10.
- The model's edge over climatology is about constant at the beat level (+0.08 to +0.10) and grows to +0.17 at the sanctuary level, where the weather "when" signal dominates. This is consistent with Spearman of about 0.70 between weather and daily counts.
- For busy-day classification, the climatology alone matches the model at sanctuary-day level (0.817 vs 0.800). The weather signal helps rank ordinary days but does not separate the top 10 %. Persistence does.
- Caveat: scar labels repeat over cloudy windows and are masked after the first burn, which blurs timing. The VIIRS rows give the cleaner timing test.

**Concrete actions for us (2-day thread, alert thread)**
1. Report every coarse target **against two baselines**: the LOSO climatology above, and VIIRS persistence (last 1-3 days). Effort: the code is written.
2. **Sanctuary busy-day product:** NB GLM, log(μ) = a + b·log1p(detections on t-2..t) + c·logit(mean model probability) + calendar terms. Publish the 90 % prediction interval. Expected coverage is about 0.94; MAE is 35-40 % below the constant mean. Test whether c survives once DC/DMC percentiles are added.
3. **Beat-week target:** expect Spearman of about 0.58 and AUC of about 0.84 for busy beat-weeks. Flagging the top 10 % catches about 42 % of busy beat-weeks, with 58 % false alarms. Set officers' expectations from these figures.

---

## Part B. Target definitions and "fire business" thresholds

### B1. Andrews & Bradshaw 1997, "FIRES: Fire Information Retrieval and Evaluation System: a program for fire danger rating analysis", USDA FS GTR INT-367. **FULL** (definitions, logistic and percentile chapters)
https://research.fs.usda.gov/download/treesearch/40613.pdf. The companion paper is Andrews, Loftsgaarden & Bradshaw 2003, IJWF 12:213 (ABSTRACT ONLY).

**What it shows**
- The three target definitions are exactly those in Headline 3:
  - **fire-day**: at least 1 fire discovered;
  - **large-fire-day**: at least 1 fire discovered that day with final size above X acres (default 10 acres);
  - **multiple-fire-day**: more than N fires (default 5).
- The date is the **discovery date**, not the ignition date.
- Each target is modelled as P = 1/(1 + exp(−(β0 + β1·index))) with one index. The worked example is P(fire-day) = 1/(1 + exp(−(−0.9855 + 0.0100·BI))).
- Percentile tables compare all-days, fire-days, large-fire-days and multiple-fire-days. Example: ERC 90th/97th percentiles = 81/85.
- Day-level linear regression of fire size on BI gave R² = 0.06. Binned percentages of fire-days and large-fire-days, by contrast, rise cleanly with index class.

**Concrete action (2-day thread / "rethink")**
- Define the Ratapani sanctuary-day targets the same way:
  - fire-day = at least 1 new VIIRS event that day;
  - multiple-fire-day = at least N new events, with N the 90th percentile of daily event counts (compute it);
  - large-fire-day = at least 1 event later mapped at 10 ha or more of scar, or with 3 or more VIIRS detections.
- Fit a one-index logistic for each on our best "when" index (DMC or DC percentile, or model mean), and publish the FIRES-style table: % of days in each class that are fire-days, multiple-fire-days and large-fire-days.
- Effort: low. Gain: a target officers understand.

### B2. Jolly, Freeborn, Page & Butler 2019, "Severe Fire Danger Index: a forecastable metric to inform firefighter and community wildfire risk management", *Fire* 2:47. **FULL**
https://doi.org/10.3390/fire2030047 (PDF via mdpi-res.com). Licence CC BY.

**Method**
- gridMET 4 km, 1979-2017, NFDRS 1978 fuel model G everywhere, so it works as a pure weather index.
- ERC and BI are converted to per-cell **percentiles** of the 39-year climatology. Then p = ERC′ × BI′, and SFDI = percentile of p, split into classes:

  | Class | Percentile of p |
  |---|---|
  | Low | 0-60 |
  | Moderate | 60-80 |
  | High | 80-90 |
  | Very High | 90-97 |
  | Severe | 97-100 |

- These breakpoints are the US interagency staffing-level breakpoints.

**Results (Table 1, CONUS)**

| Measure | Low | Moderate | High | Very High | Severe |
|---|---|---|---|---|---|
| Share of days (by construction) | 60 % | 20 % | 10 % | 7 % | 3 % |
| New fires (FPA FOD 1992-2017) | 25.0 % | 26.3 % | 19.6 % | 18.4 % | 10.7 % |
| Area burned | 6.6 % | 15.2 % | 20.2 % | 28.1 % | 29.9 % |
| MODIS large-fire pixels | 2.6 % | 7.4 % | 14.7 % | 29.7 % | 45.5 % |
| FRP | 1.2 % | 4.9 % | 12.7 % | 27.2 % | 54.0 % |

- Half of all new fires fell on days with ERC′ ≥ 81 or BI′ ≥ 73.
- Operational forecasts run 7 days ahead on the NDFD 2.5 km grid. Next-day forecasts placed on average 49 % of the 2.5 km cells burned in the first 2 days of 9 large California fires in Severe.

**Concrete action**
- Build a **Ratapani percentile class** from POWER/ERA5:
  - slow term: DMC or DC percentile (the ERC analogue);
  - fast term: FFMC or VPD percentile (the BI analogue);
  - p = product, classes at 60/80/90/97.
- Score it as SFDI does: % of new events, % of scar hectares, % of VIIRS detections per class.
- [inference] Expect the top 10 % of days to hold 20-30 % of new events (lift 2-3), and a higher share of scar area, because big burns cluster on dry days.
- Inputs: daily POWER Tmax, RHmin, wind, rain. Effort: low.

### B3. Pinto, DaCamara, Trigo & Trigo 2018, "Fire danger rating over Mediterranean Europe based on fire radiative power derived from Meteosat", *NHESS* 18:515-529. **FULL**
https://nhess.copernicus.org/articles/18/515/2018/

**Method**
- The target is the **daily energy released per pixel** (sum of FRP, in GJ) from Meteosat, 2004-2016. The 2017 validation is out-of-sample.
- Model: P(E > 2000 GJ | E > 200 GJ) from a generalized Pareto exceedance model whose scale depends on FWI. The fitted values are α = 0.31 and σ = 2470.
- Danger classes are defined on two axes, (exceedance probability G, anomaly A = G − mean for that pixel and day of year):
  - "low" = A < 0;
  - the other classes are separated by curves with break points 0.103, 0.206 and 0.309;
  - "very high" and "extreme" are set to hold equal numbers of events.

**Results**
- Of events above 10,000 GJ, 72 % fall in "extreme" and 98 % in "very high" plus "extreme" (EFFIS: 70 %).
- P(large | extreme) = 898/5443 = 16.5 % (EFFIS 11.7 %).
- P(small | low) = 77.5 %.

**Concrete action**
- For "big-fire days", rank by **daily summed VIIRS FRP per sanctuary**, not by counts.
- Use the **anomaly axis** (today's danger minus the day-of-season mean) as a second class dimension. This handles our strong seasonal cycle explicitly. [inference]
- Effort: low, since FRP is already in `viirs_cells.parquet`.

### B4. Wang, Swystun, Oliver, Levesque & Flannigan 2025, "When is fire weather extreme enough for active fire spread in Canada?", *Phil. Trans. R. Soc. B* 380:20230465 (PMC12004105). **FULL** (tables did not parse cleanly)
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12004105/

**Method**
- **Spread day** = a day of substantial daily fire growth. Daily growth comes from Parks' interpolation of MODIS/VIIRS hotspots inside NBAC perimeters (fires ≥ 50 ha, 2001-21).
- ERA5 FWI components are kriged to 100 m with elevation as covariate.
- The **threshold** is the FWI-system value at which accumulated burned area reaches 50 %. It is found with a mgcv GAM, bootstrapped 100 times on 10 of 21 years.

**Results**
- Thresholds sit mostly above the 50th percentile of fire weather, so median conditions already support spread.
- More than 60 % of area burned on days above the median.
- Only 22-30 % of potential spread days are realized as actual spread days.

**Concrete action (spread-from-active-fires target)**
- Define a Ratapani **spread day** for an active VIIRS event as one with new detections or new scar area on day t+1 adjacent to the event.
- Derive the weather threshold with the same "50 % of accumulated growth" rule.
- [inference] Expect a realization rate as low as Canada's (around 25 %). The weather threshold alone will have a high false-alarm rate, so condition on fuel continuity (unburned NBR neighbours).

---

## Part C. Count models and their skill

### C1. Koh, Pimont, Dupuy & Opitz 2023, "Spatiotemporal wildfire modeling through point processes with moderate and extreme marks", *Ann. Appl. Stat.* (arXiv 2105.08004). **FULL**
https://arxiv.org/abs/2105.08004

**Method**
- Data: French Mediterranean, daily summer fires 1995-2018, 2 km ignition cells aggregated to the 8 km SAFRAN grid (1,143 cells).
- Occurrence model: a log-Gaussian Cox process, i.e. a Poisson count per pixel-day with smooth FWI and forest-area effects (the FWI effect varies by month) plus SPDE spatial random effects.
- Size model: a mixture with a GPD tail above the 95 % quantile (79 ha, shape about 0.7).
- **Subsampling of zero counts** using Poisson additivity: all positive pixel-days are kept, and 2 zero observations per pixel-year carry weights. This cut 5 M rows to about 50,000. The rule of thumb is that the subsample should be at least 4× the number of events.

**Scoring**
- sCRPS, Brier score and AUC for individual fires.
- sCRPS for burned area **aggregated to month × département**, from 500 posterior simulations.
- Regional annual series: the model's interquantile ranges cover the observations about 50 % of the time, as intended.

**Concrete action**
- Copy the **zero-subsampling with weights** if we fit a Poisson/NB GLM or GAM on cell-days (2.39 M rows). Keep all positives plus k weighted zeros per cell-season.
- Copy the **simulate-then-aggregate** scoring: draw Bernoulli or Poisson outcomes per cell from calibrated probabilities, sum to beat-week, and compare CRPS against the climatology baseline.

### C2. Pimont, Fargeon, Opitz, Ruffault, Barbero, Martin-StPaul, Rigolot, Rivière & Dupuy 2021, "Prediction of regional wildfire activity in the probabilistic Bayesian framework of Firelihood", *Ecol. Appl.* 31:e02316. **ABSTRACT ONLY**
HAL hal-03395958 (blocked by a bot check) and bioRxiv 2020.05.20.105767 (HTTP 429). Content here is from Koh's summary and a supplement found in search.

**What is known**
- A Poisson count per 8 km pixel per day, with wildland area and FWI as covariates, plus a size component.
- It is used to forecast regional activity and is evaluated at aggregated levels (département, year).

**Concrete action**
- Read it when HAL is reachable. It is the closest published template for a "daily cell Poisson model, scored on aggregates".

### C3. Kale, Mishra, Pardeshi, Ghosh, Pai & Roy 2022, "Forecasting wildfires in major forest types of India", *Front. For. Glob. Change* 5:882685. **FULL**
https://doi.org/10.3389/ffgc.2022.882685

**Method**
- MODIS monthly active-fire counts on a 25 km grid, 2003-17, summed per forest type: TDDF (tropical dry deciduous), TMDF (tropical moist deciduous) and TEGF (tropical evergreen).
- Seasonal ARIMA. TDDF uses (0,0,1)(2,1,0); the regressor version adds temperature and dry days.

**R² of the test forecasts (2015-17)**

| Forest type | Year 1 | Year 2 | Year 3 | All 3 years |
|---|---|---|---|---|
| TDDF | 0.94 | 0.76 | 0.88 | 0.64 |
| TMDF | 0.98 | 0.99 | 0.67 | 0.89 |
| TEGF | 0.97 | 0.95 | 0.89 | 0.89 |

- The regressors added nothing. For TDDF, the 2015 peak fell outside the 80 % and 95 % bands. The regressor model produced negative counts off-season.

**Concrete action**
- Treat as a **warning about inflated aggregate skill**: monthly R² is mostly seasonal cycle.
- Always report skill **within season and against the week-of-season climatology**, as in Part A (rho(clim) = 0.62 at sanctuary-day).
- This is the only Indian count-forecast paper found. Our sanctuary-day result (0.80 vs 0.62 for climatology) is already well beyond it.

### C4. Preisler & Westerling 2007, "Statistical model for forecasting monthly large wildfire events in western United States", *J. Appl. Meteor. Climatol.* 46:1020. **FULL** (6 pp)
https://research.fs.usda.gov/download/treesearch/33039.pdf

**Method**
- Two-stage logistic GAM on 1° cells × month, 1980-2004: P(any fire) × P(at least 400 ha | fire).
- Predictors: lagged PDSI and temperature. The baseline is persistence, meaning the historic frequency per cell and month.

**Results**
- In July, the observed share of cells with a large fire was 3 % where the forecast was "low", 11 % where "moderate", and 76 % where "extreme".
- Model forecast probabilities spanned 0-76 %, against 0-47 % for persistence.
- Maps show **odds ratio vs persistence** ("above/below normal").
- Observed counts are checked against 95 % bounds that include binomial variation.

**Concrete action**
- Publish the beat-week product as an **odds ratio against beat-week climatology** ("this week is 2.3× normal for this beat"). Officers already know which beats burn, so the useful message is the departure from normal.
- Effort: low, since the climatology is already computed in Part A.

---

## Part D. Forecast skill with lead time (ECMWF, PoF, S2S)

### D1. Di Giuseppe, McNorton, Lombardi & Wetterhall 2025, "Global data-driven prediction of fire activity", *Nat. Commun.* 16:2918 (PMC11962136). **FULL**
https://doi.org/10.1038/s41467-025-58097-7

**Method**
- ECMWF operational **Probability of Fire (PoF)**: XGBoost at 9 km, daily, running since 2023, trained on MODIS/VIIRS active fires.
- 19 predictors in three groups:
  - weather: ERA5-Land T2m, dewpoint, wind, precipitation;
  - fuel: live and dead loads and moistures from a fuel model, plus VOD and LAI;
  - ignitions: population, road density, urban fraction, lightning, orography.

**Results**
- Dropping fuel or ignitions costs about 30 % of skill. Weather-only models over-predict high probabilities, which means false alarms.
- A neural network gave no gain over XGBoost (normalized score 0.83 vs similar). Random forest scored 0.77-0.78.
- Useful forecasts of the 2023 Canadian activity came **up to 10 days ahead**. An experimental 1 km version exists.
- The paper warns that a reliability score aggregated over a large domain can hide compensating regional biases.

**Concrete action**
- Download PoF for the Ratapani 9 km cells (2023-26) as a **sanctuary-day baseline**, and as an input to the NB count model. This needs an ECMWF data request.
- Expected gain: small [inference], since its weather "when" component equals ours and its ignition layer is static.

### D2. Singh, Arora, Ashrit & Rajagopal 2017, "Verification of pre-monsoon temperature forecasts over India during 2016 with a focus on heatwave prediction", *NHESS* 17:1469. **FULL** (scores table partly parsed)
https://doi.org/10.5194/nhess-17-1469-2017

**Method**
- NCMRWF deterministic NCUM (17 km) and the 44-member NEPS against IMD gridded Tmax, March-May 2016.

**Results**
- Tmax > 40 °C in March, NCUM: POD 0.23-0.27, FAR 0.71-0.81, ETS 0.09 on days 1, 3 and 5. Skill barely changes from day 1 to day 9.
- NEPS is quasi-constant to day 10 and reliable from day 2 on.
- NCUM over-predicts heat over MP, UP and Bihar (warm bias).

**Concrete action**
- For a 1-7 day "when" forecast, expect **little decay from day 1 to day 5** in temperature-driven danger. The pre-monsoon atmosphere is persistent. [inference]
- Use the ensemble mean (GEFS/ENS or NEPS) and bias-correct against POWER for Ratapani before computing DMC/FFMC percentiles.
- Test a sanctuary-week product at lead 0-6 days; expected loss vs analysis weather is about 0.02-0.05 Spearman. [inference]

### D3. Prapas et al. 2023, "TeleViT: teleconnection-driven transformers improve subseasonal to seasonal wildfire forecasting", arXiv 2306.10940 (ICCV workshop). **PARTIAL** (numbers are in figures only)
https://arxiv.org/abs/2306.10940

**Method**
- SeasFire cube: 0.25°, 8-day steps.
- Target: presence of GWIS burned area at lead h = 1, 2, 4, 8 or 16 × 8 days, with one model per lead.
- Metric: AUPRC on patches that contain burned area.

**Results**
- AUPRC decays slowly with lead. Adding global coarse inputs and ocean-climate indices helps more at longer leads.

**Concrete action**
- None for daily work. It supports an **8-day (weekly) unit** as the natural S2S target, and shows weekly burned-area presence keeps skill for weeks.
- For Ratapani, a pre-season (Jan) forecast of seasonal intensity could use the previous monsoon's rainfall and ENSO. Low priority.

---

## Part E. Other sources checked

- **Rummens & Hardyns 2021**, IJF 37:125 (predictive policing, home burglary, Belgium). **ABSTRACT ONLY**. It tests grid size, temporal resolution and history length, and concludes that high space-time resolution lowers performance. No numbers were accessible.
- **Swedish Risk Terrain Modelling scale study (Nordregio).** Search-level only. Smaller cells give a higher PAI but a lower F1 and efficiency, and no single grid is best everywhere.
- **Plucinski et al. 2014**, IJWF 23:520. Abstract only (already in the ops note).
  - Model: NB regression of daily human-caused counts per management area. Predictors: fuel moisture, the number of recent fires, workday versus weekend or holiday, and rain.
  - Result: 81-99 % of daily counts fell in the predicted range. It was useful only in the densely populated areas.
- **IITM/IMD extended-range fire products.** Nothing with published skill was found. FSI pre-fire alerts remain the only operational Indian baseline.
- **Consensus, Semantic Scholar and OpenAlex** were rate-limited or out of quota during this session, so the literature search relied on web search plus Europe PMC, arXiv and publisher OA.

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| Our LOSO predictions + labels | `/mnt/project-files/ratapani/scoring/pipeline_lean_pred_loso_2017_24.parquet`, `.../fsi/scouting/data/exp_preds.parquet` | 500 m, daily | 2017-24 | internal | parquet |
| VIIRS detections / events (Ratapani) | `.../fsi/scouting/data/viirs_cells.parquet`, `events.parquet` | 375 m | 2013-26 | NASA open | parquet |
| ECMWF PoF (Probability of Fire) | ECMWF / CEMS fire (on request); paper code at doi 10.24433/CO (CodeOcean) | 9 km (1 km experimental), daily, to 10 days | 2023- | ECMWF terms | ECMWF data request |
| McNorton & Di Giuseppe fuel characteristics | doi 10.24381/378d1497 (CDS) | 9 km daily | 2003- | Copernicus licence | CDS API |
| GEFF/CEMS FWI reanalysis and forecasts | Copernicus CDS / EWDS "fire danger indices" | 0.25° (ERA5), 9 km HRES, ENS | 1940- | Copernicus licence | CDS API |
| gridMET / NFDRS climatology (for method only) | climatologylab.org/gridmet | 4 km | 1979- | public | download |
| SeasFire cube | zenodo (SeasFire) | 0.25°, 8-day | 2001-21 | CC BY | zarr |
| NCMRWF NCUM / NEPS forecasts | ncmrwf.gov.in (data on request) | 12-17 km | – | MoES | request |
| GEFS / ECMWF open-data ENS | NOAA NOMADS; ECMWF open data | 0.25° | current | open | HTTP |

---

## Ranked action list

| # | Action | Thread | Gain (expected) | Effort |
|---|---|---|---|---|
| 1 | Report every coarse target against **LOSO climatology** and **VIIRS persistence** baselines (Part A code). The honest gains are +0.08 to +0.10 Spearman at beat level and +0.17 at sanctuary level | rethink / 1 | Prevents over-claiming; sets real targets | done / low |
| 2 | **Sanctuary 2-day NB count model**: log1p(last-3-day detections) + logit(model mean) + DMC/DC percentile, with a 90 % prediction interval. Baseline: MAE 7.7, coverage 0.95 | 5 (alerts) | Busy-day AUC about 0.87; usable daily count with interval | low |
| 3 | **FIRES-style targets** (fire-day, multiple-fire-day at the 90th percentile of events, large-fire-day ≥ 10 ha scar) with one-index logistic curves and class tables | rethink | Interpretable officer product | low |
| 4 | **SFDI-style percentile class** (DMC′ × FFMC′ or VPD′, cuts at 60/80/90/97). Score the share of events, area and FRP per class | rethink / 5 | Lift of about 2-3× in the top 10 % of days [inference] | low |
| 5 | **Beat-week odds ratio vs beat climatology** as the weekly bulletin. Expect Spearman about 0.58, busy AUC about 0.84, POD 0.42 / FAR 0.58 at the top 10 % | 5 | Communicates "above normal" | low |
| 6 | **Big-fire day by daily summed FRP**, with the anomaly axis (Pinto 2018) | rethink | Better target for intensity than counts | low |
| 7 | **Spread-day target** for active events (growth on t+1), with a weather threshold found by the "50 % of accumulated growth" rule | 4 / rethink | New target; realization rate likely about 25 % | medium |
| 8 | Lead-time test: rebuild the "when" index from GEFS/ECMWF ENS at day 1-7, bias-corrected to POWER, and score sanctuary-week | 1 / 5 | Expected decay ≤ 0.05 Spearman to day 5 [inference] | medium |
| 9 | Weighted zero-subsampling + Poisson GAM (Koh 2023) as an interpretable alternative to LightGBM at cell level, aggregated by simulation | 1 | Calibrated counts for any unit | medium |
| 10 | Obtain ECMWF PoF for Ratapani as an external sanctuary-day baseline | 1 / 5 | Benchmark; small gain as an input | medium (data request) |

## Reading status

- **FULL (10):**
  - FIRES GTR (Andrews & Bradshaw 1997)
  - Jolly et al. 2019 SFDI
  - Pinto et al. 2018
  - Wang et al. 2025
  - Koh et al. 2023
  - Kale et al. 2022
  - Preisler & Westerling 2007
  - Di Giuseppe et al. 2025 (PoF)
  - Singh et al. 2017
  - our own data analysis (Part A)
- **PARTIAL (1):** TeleViT.
- **ABSTRACT ONLY / search level:** Firelihood (Pimont 2021), Andrews et al. 2003, Rummens & Hardyns 2021, the Swedish RTM study, Plucinski 2014, IITM/IMD extended-range products.
