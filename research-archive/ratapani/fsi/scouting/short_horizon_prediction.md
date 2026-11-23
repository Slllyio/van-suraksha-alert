# Short-horizon (1-7 day), fine-scale fire occurrence prediction: what else works

Literature note, 14 Oct 2026. Builds on `research/fire-prediction-landscape.md` and `research/ratapani-ignition/README.md` and does not repeat them. Already tried there: Poisson ignition model, calendar flags (mahua, tendu, Holi, weekends: no effect), ERA5 per cell, wind (no effect), satellite dryness (the one input that helped), day-shared budgets, upweighting hard fires, calibration deciles (good), rank-averaging two models (no gain).

Baseline we are trying to beat: LightGBM, about 29 % recall of first-burn cell-days at 5 picks per beat per day, against about 17 % for random picks.

Labels used below: **[found]** means the source says it. **[inference]** means it is my reading of how it applies to Ratapani. Expected effects are guesses in recall points at 5 picks per beat, unless stated otherwise.

---

## 1. Benchmarks for daily fire occurrence (next-day danger)

**Mesogeos (Mediterranean, 1 km, daily, 2006-2022; NeurIPS 2023).** https://arxiv.org/abs/2306.05144 · https://orionlab.space.noa.gr/mesogeos
[found] A datacube of weather, vegetation and human-activity drivers with ignition and burned-area records, plus a "next-day danger" track. LSTM and Transformer models score about 0.86-0.87 AUPRC, but on a **balanced, subsampled** test set.
[inference] Those AUPRC numbers are not comparable with recall at a base rate under 1 %. What carries over is their input design: a 30-day time series of each driver for each cell, rather than one value per day.
*Experiment:* give each cell lagged and trend versions of its own S2 dryness: NDVI/NDMI slope over the last 30 and 60 days, and days since NDVI fell below 0.35. Expected **+0.5 to 2 pts**, because dryness is already our best "where" signal.

**FireCube Greece and the daily danger deep-learning paper (Prapas et al. 2021).** https://arxiv.org/abs/2111.02736 · https://zenodo.org/records/6475592
[found] At 1 km and next-day horizon, a ConvLSTM using spatial and temporal context beat a Random Forest (AUROC 0.926). Either spatial context or temporal context alone was enough to win. The paper also warns that "no fire" does not mean "no danger", which makes negative sampling delicate.
[inference] Our deep models failed for lack of data, but the *spatial-context* part can be added to LightGBM as features.
*Experiment:* add neighbourhood features: the mean, minimum and maximum of NDVI/NBR over the 3x3 and 5x5 cells around each cell, and the cell's dryness rank within its beat. Expected **+0.5 to 1.5 pts**.

**Next Day Wildfire Spread and FireSenseNet (evaluation pitfalls).** https://arxiv.org/abs/2112.02447 · https://arxiv.org/abs/2604.07675
[found] FireSenseNet reports that the previous day's fire mask dominates prediction, that wind is noise at daily resolution (which matches our finding), and that common evaluation choices can inflate F1 by over 44 %.
*Experiment:* none to build. Use it as a checklist item (see section 7).

**CanadaFireSat (multi-modal, high resolution).** https://arxiv.org/abs/2506.08690
[found] Samples negatives across each province's yearly range of fire drivers, rather than only from cells that burned at some point, to avoid a biased training set.
[inference] We train on all cells, so this mainly matters if anyone subsamples negatives.

## 2. Operational fire danger and its skill in India

**ECMWF Probability of Fire (PoF), Di Giuseppe et al., Nature Communications 2025.** https://www.ecmwf.int/en/about/media-centre/news/2025/scientists-present-new-ml-tool-improved-fire-prediction · slides: https://resources.eumetrain.org/data/7/744/slides/FrancescaDiGiuseppi.pdf
[found] An XGBoost classifier trained on MODIS, VIIRS and geostationary detections, using fuel moisture from the SPARKY model, human presence and lightning. Adding all of these sources improved skill by up to 30 %. In the Los Angeles 2025 case, dead fuel moisture was anomalously low exactly where the fires started.
*Experiment:* add **dead-fuel moisture** to the "when" part. The free proxy is FFMC/DMC computed from POWER/ERA5 (next item). Expected: Spearman for "when" rises by **+0.02 to 0.05**, and "where" barely moves, because the input is sanctuary-wide.

**ECMWF global FWI forecast skill (Di Giuseppe et al., NHESS 2020).** https://nhess.copernicus.org/articles/20/2365/2020/
[found] FWI forecasts keep skill beyond 10 days compared with climatology. However, good FWI forecasts did **not** translate into good forecasts of fire activity in regions with agricultural and human burning. High FWI (above the ERA5 90th percentile) coincided with fires in only about 50 % of cases globally, and in under 20 % of cases in the South-East Asia region, which includes India (corrected after full read).
[inference] This explains why weather here gives us "when" but not "where".

**FWI behaviour over India (Barik, EGU21; IIT Delhi EGU24).** https://meetingorganizer.copernicus.org/EGU21/EGU21-14231.html · https://meetingorganizer.copernicus.org/EGU24/EGU24-14686.html
[found] FWI computed from ERA5 correlates well with Indian forest fires **only if** it is spun up for at least 60 days and calibrated locally. Temperature and RH are the key drivers. The IIT Delhi framework sets danger classes per forest zone, Central India included, and claims 30-50 % better detection of fire probability.
*Experiment:* compute the FWI system (FFMC, DMC, DC, BUI) and KBDI from our POWER series, with a spin-up starting 1 Dec. Use **local percentiles** (each day's value against 2017-24) as daily inputs in place of raw RH/temperature. Expected **+0 to 0.5 pts** on "where", and a small gain in the "when" correlation. This is cheap, so worth running even though it is probably minor.

**FSI pre-fire alerts.** https://fsiforestfire.gov.in/Home/PreFireDetails
[found] Uses GEOS-5 FWI from NASA GFWED with thresholds set per physiographic zone, then reclassified using forest type, archival fires, active large fires and forecast rain. Alerts are weekly on 5 km grids.
*Experiment:* use FSI's weekly class for Ratapani's 5 km cells as a **baseline to beat**, not as an input, since it is 10x coarser. It shows officers how much the 500 m model adds.

**KBDI.** Earth Engine KBDI dataset: https://developers.google.com/earth-engine/datasets/catalog/UTOKYO_WTLAB_KBDI_v1 · Shivalik KBDI forewarning: https://www.spiedigitallibrary.org/conference-proceedings-of-spie/11528/115280O/An-approach-for-forewarning-forest-fires-in-Shivalik-forest-tracts/10.1117/12.2572128.full
[found] There is a ready KBDI layer in Earth Engine. An Uttarakhand study used KBDI for forewarning but reported no accuracy figures. I found **no** validation of KBDI for central Indian dry deciduous forest.
[inference] KBDI is a slow drought accumulator, close to our day-of-year and dryness inputs, so expect almost nothing.

**India papers (MP and CG, Odisha, Western Ghats).** MP/CG random forest: https://consensus.app/papers/details/eb289536505953869be3d252d7895771/ · Similipal dNBR + ML: https://consensus.app/papers/details/3e8dfd8f9cfd57198e9dcf80c3d4f103/ · MP modified McArthur FFDI with MODIS NMDI: https://consensus.app/papers/details/7c64930bea705b18bf282726e359486e/
[found] All are susceptibility models (monthly or static) reporting AUC or accuracy. NDVI and rainfall anomalies matter in MP/CG. In Similipal, land cover, NDVI and **NDMI** rank top. The MP FFDI work replaces the station-based drought term with satellite NMDI (82 % accuracy).
[inference] These confirm our NDMI finding but offer no daily method. I still found no daily 500 m forecast for a central Indian reserve.
*Experiment:* add **NMDI** (a SWIR-based moisture index, used in the MP FFDI study) from S2 B8A/B11/B12 next to NDMI. Expected **+0 to 1 pt**.

## 3. Human-caused fire occurrence models (closest in method to us)

**Yang & Woolford 2026, IJWF: 1-4 day spatio-temporal forecasts of human-caused fires, Ontario.** https://connectsci.au/wf/article/35/7/WF25211/273126/Short-term-spatio-temporal-forecasting-of-human
[found] A logistic GAM on daily 10 km voxels, with a separate model per lead time (1-4 days). It uses the **forecast** FFMC, not the observed one, and corrects for forecast error (SIMEX). That correction improved Brier scores and pushed 95 % interval coverage from 82-88 % to 93-96 %. Roads, the wildland-industrial interface and a smooth spatial term mattered.
*Experiment (a pitfall check):* rescore our model using the weather that would have been **available at issue time**: a day-t forecast, or the day t-1 observation, for target days t+1 and t+2. Use a separate model per horizon. Expected: recall unchanged or **-0.5 to 1 pt**. This is a check that the 29 % is honest, not a gain.

**Phelps & Woolford 2021, IJWF: calibrated ML vs logistic GAM, human-caused fires, Alberta.** https://publish.csiro.au/WF/WF20139
[found] Many machine-learning fire occurrence models overpredict unless calibrated. Once calibrated, a logistic GAM matches the ML models; its AUC-PR was in fact the highest, more than 10 % above the others, though the differences were not significant. A follow-up paper shows that calibrated tree-model estimates of the total fire count can differ by more than 40 % across hyperparameter settings: https://arxiv.org/abs/2412.16209
[inference] Our deciles look well calibrated already. A GAM with a 2-D spatial smooth is a cheap second opinion that behaves differently from trees.
*Experiment:* fit a Poisson GAM: s(day of year), s(NDVI), s(NBR), s(RH), a spatial smooth s(x,y), and a random effect per beat. Then rank-average it with the LightGBM. Expected **+0 to 1 pt**. Our earlier rank-average of two tree-ish models gave nothing, but a smooth spatial surface is a different kind of model.

**Nadeem et al. 2019 (BC, lasso-logistic, daily human and lightning fires).** https://publish.csiro.au/WF/WF19058 · **Martell et al. (Ontario) seasonal periodic terms:** https://researchconnect.suny.edu/en/publications/modelling-seasonal-variation-in-daily-people-caused-forest-fire-o/
[found] Daily logistic models with ROC AUC above 0.9. Seasonality enters as periodic (Fourier) functions of the date.
[inference] We already use day of year, so this gives us nothing new.

**Galicia: arson vs negligence vs natural fire patterns (Marey-Pérez et al. 2023, IJWF 32(2)).** https://consensus.app/papers/details/2ba43010e59855c397c5dacda821f310/
[found] Arson fires show strong **interaction between outbreaks**: fires cluster around earlier fires, and the hotspot shifts both within a year and between years. Negligence fires cluster only at short distances. The authors conclude that different causes need different covariates.
[inference] This matches "interior ignites more" if a few people or groups set repeated fires in particular forest compartments. Their activity would show up as **local, recent ignition clusters** at beat scale, not sanctuary-wide.
*Experiment:* see the Hawkes items below. Add **beat-level and 2-5 km-ring new-ignition counts for the last 3, 7 and 14 days**. Today we only use a sanctuary-wide count and the distance to a front. Expected **+1 to 3 pts on new ignitions**. This is my top idea.

## 4. Self-exciting (Hawkes) and point-process models of contagion

**Reinhart 2017, review of self-exciting spatio-temporal point processes.** https://arxiv.org/abs/1708.02647
[found] A Hawkes model splits events into "background" events and events "triggered" by recent nearby events, with fitted decay curves over distance and time. Standard in earthquake, crime and epidemic modelling.

**Mohler et al., crime ETAS and PredPol field trials.** Field trials: Mohler et al. 2015, JASA 110:1399 (arXiv 1811.12880 is a Bogotá deployment, not a review) · CrimeRank: https://link.springer.com/article/10.1186/s40163-020-00112-x
[found] In randomised field trials (Los Angeles and Kent), ETAS predicted **1.4-2.2x** as much crime as a dedicated analyst. Patrols directed by ETAS cut crime volume by 7.4 % (second-hand figures). A Chicago study found the triggering functions fragile.
[inference] Crime hotspot work is the closest analogue to "5 picks per beat". It is human-caused, sparse and budgeted, and it is scored by the share of events captured in the top k cells.

**Hawkes for wildfire: California (arXiv 2207.13250), Sicily, Holbrook et al.** https://arxiv.org/abs/2207.13250 · https://researchseminars.org/talk/gbgphd/49/ · https://par.nsf.gov/servlets/purl/10492363
[found] Mutually exciting point processes give real-time fire risk. Past fires and fires in neighbouring areas can raise **or lower** the risk of new ignitions (lowering through fuel depletion). The Sicily work lets the branching ratio, i.e. how strongly fires trigger new ones, depend on covariates. Holbrook et al. handle uncertain event locations, which is analogous to our interval-censored dates. None of these give numbers usable for us.
*Experiment:* fit a **discrete Hawkes feature set**. For each cell and issue day, compute the sum over past ignitions j of exp(-Δt_j/τ)·k(d_j/σ), for a few (τ, σ) pairs: τ = 2, 7 and 21 days, σ = 1, 3 and 8 km. Compute it separately for new ignitions and for all burns. Optionally fit τ and σ by Poisson likelihood. Feed these to LightGBM. Expected **+1 to 3 pts**, mostly on new ignitions. This generalises section 3 and replaces the single sanctuary-wide count.

**Log-Gaussian Cox processes with INLA (Opitz et al. 2020; Koh et al. 2021, France).** https://consensus.app/papers/details/652bbe85d1945a6297c3c9e47aaf46f2/ · https://consensus.app/papers/details/ba0077fd34b451b893abca5b2054065f/
[found] Daily Bayesian occurrence models with a spatial random effect (Matérn) and yearly autoregression. They subsample zeros, stratified, and correct for it. Shared random effects improved prediction.
[inference] The "per-cell random effect with a year-to-year carry-over" corresponds to our burn-history features. This is useful if we want uncertainty bands, and unlikely to raise recall.

## 5. Patrol allocation, recall at a budget, and ranking objectives

**PAWS: poaching prediction and patrol planning (Xu, Gholami, Tambe et al. 2020).** https://arxiv.org/abs/1903.06669 · overview: https://arxiv.org/abs/2001.00088
[found] Predicts snares with extreme class imbalance (up to 1:200). It uses Gaussian-process **uncertainty** to make patrol plans robust, and raised snare detection by about 30 % on historical data from Uganda and Cambodia. It also had field tests. Its key data issue: absence of a detected snare depends on **patrol effort**, so an unpatrolled cell is not a true zero.
[inference] Our equivalent is a cell not seen clearly, or a small fire under 0.5 ha that the scar map misses.
*Experiment:* give 1 of the 5 daily picks per beat to **exploration**: the cell with high predicted rate × high model uncertainty (variance across bootstrap LightGBMs), or one long unpicked. Expected **-0.5 to +0.5 pts** of recall. It would, however, reduce the "same cells every day" pattern officers will notice. Report coverage alongside recall.

**Decision-focused / game-focused learning (Perrault et al.).** https://arxiv.org/abs/1903.00958
[found] Training the model on a proxy for the defender's actual payoff, instead of prediction accuracy, gave better outcomes when data was limited.

**CrimeRank (Mohler et al. 2020) and SpatialRank (NeurIPS 2023).** https://link.springer.com/article/10.1186/s40163-020-00112-x · https://arxiv.org/abs/2310.00270
[found] Standard training does not focus accuracy on the top k cells, even though the score is recall at k. CrimeRank, a boosting learning-to-rank model that maximises the share captured in the top k, beat the 2017 NIJ challenge winners on the validation data (PAI 61.5 vs 57.5-58.8). The authors' own winning entry was a different method (RGPM). SpatialRank optimises NDCG for sparse urban events.
*Experiment:* swap the LightGBM objective to **`lambdarank`**, with query = (beat, issue day), label = burned in the next 2 days, and `lambdarank_truncation_level=5`. Train only on beat-days with at least one positive. Keep the Poisson model for calibrated rates, and either use the ranker for ordering or rank-average the two. Expected **+0.5 to 2 pts**. Our metric is exactly recall@5 within a beat-day, which the current objective does not optimise.

## 6. Label noise, missed small fires, and transfer

**Song, Raskutti & Willett 2021: prediction with response-dependent missing labels (California fires).** https://arxiv.org/abs/2103.13555
[found] Small fires are more often undetected, so "negatives" include hidden positives. They jointly model occurrence and **detection probability**: positive-unlabeled learning combined with a zero-inflated model. This beat earlier methods, but only on fire-size error with random 90/10 splits; there was no occurrence-ranking test.

**Wildfire danger prediction as a positive-unlabeled task (NeurIPS 2026, on Mesogeos).** https://neurips.cc/virtual/2026/165402
[found] Five positive-unlabeled (PU) methods compared with a supervised baseline. Several collapse into unstable or all-negative predictions. Variational PU methods match the baseline at detecting fires. So PU learning is no free win.
[inference] Our scar labels have a recall of about 0.71, and misses concentrate in fires under 2 ha, near villages and at low elevation. These are the same cells where we score 12-15 %.
*Experiment:* add a **detection layer**. Estimate per cell, from the label-check sample, P(scar is detected | burned), as a function of forest share, canopy and cloud gaps. Fit occurrence × detection, and rank by occurrence alone. Expected **+0 to 1 pt** on the current labels, since scoring uses the same noisy labels. The real value is a more honest map for officers.

**Cross-regional transfer of fire occurrence models (Bekar et al. 2020, IJWF; Alps and Mediterranean).** https://www.uv.es/777DBUnMiI!Mhk=/papers/Bekar-2020-IJWF_fire-crossregional.pdf
[found] Models trained in one region transfer well only to regions with similar conditions. A **cross-regional** model trained on pooled regions transferred better. However, the pooled data included the target region itself, and its AUC was within +0.04 of the local models. An earlier Swiss study found transfer across time works but transfer across space does not.
*Experiment:* pretrain the same LightGBM on **other central Indian dry deciduous reserves**, e.g. Singhori, Nauradehi, Satpura, Panna and Melghat. Use VIIRS-dated first burns plus the same S2 dryness and terrain features, which are all in Earth Engine. Then continue boosting (`init_model`) on Ratapani. Expected **+1 to 2 pts**, because the bottleneck is data, not model capacity. The risk is that VIIRS labels differ from scar labels. Pool at the feature level and include a `region` feature.

## 7. Human-ignition drivers: what is and is not supported

- **Mahua and tendu timing.** Mahua is collected in March-April, with burning under the trees to clear the ground: Melghat collection-sheet trial (Kulkarni & Mehta 2020) https://indianforester.co.in/index.php/indianforester/article/view/154919 and World Bank feature https://www.banquemondiale.org/fr/news/feature/2022/12/07/preventing-forest-fires-one-flower-at-a-time. Tendu-linked fires in Maharashtra: https://thehitavada.com/Encyc/2023/7/6/Tendu-collection-process-a-reason-behind-forest-fires-in-Maharashtra-Study.html. [found] There is no daily fire-date-vs-collection-date study. [inference] Calendar flags already showed nothing. The spatial version may still help: **where mahua trees are**.
  *Experiment:* mahua density per cell. Mahua is leafless and flowering in March, which may be separable in S2 March phenology. Alternatively, use forest working-plan compartment data if the forest department has it. Expected: unknown, possibly the missing "interior" driver. Needs data first.
- **Night-time burning.** DMSP studies in Uttaranchal found most fire episodes there at night: https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=02604. A 2025 preprint argues the VIIRS product filters out low-confidence night detections: https://arxiv.org/abs/2510.26816. Polar orbiters miss afternoon fires: https://ntrs.nasa.gov/citations/20260005893. [inference] A per-cell share of past VIIRS detections at night vs by day could mark slow-smouldering litter burning. This is weak evidence, so low priority.
- **Nighttime lights.** I found no peer-reviewed study using VIIRS night lights as a fire-ignition predictor in tropical forest (only an Indonesia conference paper: https://pos.sissa.it/434/025). [inference] Ratapani villages are dim, and lights would only repeat the distance-to-village signal, which already points the wrong way. Skip.
- **Leaf fall.** A MODIS leaf-fall proxy for central Indian forests exists, matched to ground observations: https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=38322. [inference] We could add, per cell per season, the date the cell's NDVI dropped and the days since then, as a measure of litter build-up. This partly overlaps the current NDVI input. Expected **+0 to 1 pt**.
- **LST anomaly.** In BC and Campania, fires followed positive MODIS land surface temperature anomalies in the 1-3 days before ignition, and cumulative anomalies helped: https://dl.uc.pt/handle/10316.2/34292 · https://open.library.ubc.ca/collections/researchdata/items/1.0396751. [inference] MODIS/VIIRS LST is 1 km and daily, coarse for 500 m cells but finer than our weather. Landsat LST is 30 m but only every 8-16 days.
  *Experiment:* add the cell's Landsat LST anomaly (latest within 16 days) and its MODIS 1 km daily LST anomaly over 3 days. Expected **+0 to 1 pt**.

## 8. Leakage and evaluation pitfalls to check before trusting 29 %

1. **Activity features built from interval-censored scars.** "New ignitions last 7 days" or "front distance" must only use scars whose **closing clear image is dated before the issue day**. A scar first seen in an image taken after day t, even if dated into a window starting before t, would leak. [inference] This is the biggest risk, because these are top-gain features.
2. **Weather at issue time** (Yang & Woolford): use forecasts or day t-1 data, never the observed weather of the target day.
3. **Spatial autocorrelation.** Season-out splits are good. Neighbouring cells on the same day still share labels, so report confidence intervals with a block bootstrap over beat-days. Landslide studies show random cross-validation is optimistic: https://doaj.org/article/bc4bfcef8be04bc6981e192574e91ef2. The AlphaEarth fire study used a 3 km buffer chosen from a semivariogram: https://arxiv.org/abs/2608.12663.
4. **Subsampled negatives** inflate precision. Recalibrate if any experiment subsamples (Phelps & Woolford; arXiv 2412.16209).
5. **Persistence baseline.** Always report "closest fresh front + long-run burn frequency" next to the model (NDWS, FireSenseNet).

---

## Ranked top 5 experiments not yet tried

| # | Experiment | Why (source) | Expected effect | Cost |
|---|---|---|---|---|
| 1 | **Local Hawkes / self-excitation features**: exp-decay kernels of past new ignitions and burns at 1, 3 and 8 km × 2, 7 and 21 days, plus beat-level counts over the last 3, 7 and 14 days, replacing the single sanctuary-wide count | Arson-type clustering of outbreaks (Galicia); ETAS crime field trials 1.4-2.2x; wildfire Hawkes (arXiv 2207.13250) | +1 to 3 pts, mostly new ignitions | Low: features only |
| 2 | **LambdaRank objective**, query = beat × issue day, truncation level 5; rank-average with the Poisson model | CrimeRank, SpatialRank: train for recall@k, the metric we score | +0.5 to 2 pts | Low |
| 3 | **Pretrain on other central Indian dry deciduous reserves** (VIIRS-dated first burns + S2 dryness + terrain), then continue boosting on Ratapani | Pooled cross-regional models transfer better (Bekar 2020); our limit is data | +1 to 2 pts | Medium: Earth Engine pulls |
| 4 | **Dryness dynamics and neighbourhood context**: NDVI/NDMI 30- and 60-day slopes, days since NDVI fell below 0.35 (leaf-fall date), 3x3 and 5x5 neighbourhood stats, within-beat dryness rank, NMDI | Mesogeos/FireCube temporal and spatial context; MP FFDI NMDI; PoF fuel moisture | +0.5 to 2 pts | Low |
| 5 | **Leakage audit + honest rescoring**: activity features only from scars closed before issue day; forecast or t-1 weather; block-bootstrap CIs | Yang & Woolford 2026; FireSenseNet (+44 % F1 inflation) | 0 to -2 pts, but makes every comparison trustworthy | Low |

Close runners-up: an FWI/KBDI system with local percentiles (helps "when" only); a Poisson GAM with spatial smooth and beat random effect to ensemble with; one exploration pick per beat (PAWS-style, for officer coverage rather than recall); an occurrence × detection model for small fires (Song et al.).

All expected effects are my estimates [inference], not results reported by the sources. Several sources are preprints, conference abstracts or press summaries; I did not re-verify their numbers.
