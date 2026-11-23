# Fire-spread literature review for Ratapani

*Written 15 Oct 2026 for the Ratapani surface-fire spread project. It covers 36 papers and reports.*

**How to read this.** Each entry carries a reading tag:
- **[FULL]**: I read the full text (PDF or HTML) and took the numbers from it.
- **[PARTIAL]**: I read part of the full text, such as the abstract, methods and key tables.
- **[ABSTRACT]**: I saw only the abstract, a catalogue record or a secondary summary. Treat these numbers as less certain.

Unit conversions to m/h are mine and are marked "≈". I have not invented any number. Where I was unsure, I say so.

**Our setting in one line.** Teak-litter surface fires in Ratapani, observed only by VIIRS 375 m passes (about 01:30 and 13:30) and by burn scars dated to a 1–3 week window. Measured fronts creep at 10–60 m/h. Rothermel plus level set does no better than a circle. Gradient boosting beats persistence mainly at gaps longer than 9 h.

---

## 1. C-DAC and other Indian work

### 1.1 Kale et al. 2024, the C-DAC operational WRF-SFIRE system (Sikkim) [FULL]
**Citation.** Kale, M.P., Meher, S.S., Chavan, M., Kumar, V., Sultan, Md.A., Dongre, P., Narkhede, K., Mhatre, J., Sharma, N., Luitel, B., Limboo, N., Baingne, M., Pardeshi, S., Labade, M., Mukherjee, A., Joshi, U., Kharkar, N., Islam, S., Pokale, S., Thakare, G., Talekar, S., Behera, M.D., Sreshtha, D., Khare, M., et al. (2024). Operational Forest-Fire Spread Forecasting Using the WRF-SFIRE Model. *Remote Sensing* 16(13), 2480. https://doi.org/10.3390/rs16132480 (PDF: https://mdpi-res.com/d_attachment/remotesensing/remotesensing-16-02480/article_deploy/remotesensing-16-02480.pdf)

**What they did.**
- Ran WRF-SFIRE for one surface fire in North Sikkim on 27 Jan 2023, driven by GFS 0.25° forecasts.
- Used nested WRF domains of 7.2 km, 2.4 km and 800 m, with a 40 m fire grid.
- Set the ignition at a VIIRS 375 m alert.
- Took fuel load and depth from 23 field plots of 0.1 ha each. Took surface-area-to-volume ratio (SAVR) from the literature (Scott and Burgan).
- Validated against a burned area hand-digitised from one post-fire Sentinel-2 image.

**Numbers.**
- Fuel loads were 0.16, 0.234, 0.243 and 0.270 kg/m² for grass, dense scrub, open scrub and forest. Fuel depths were 0.305, 0.61, 0.91 and 0.061 m.
- Moisture of extinction was set at 0.12–0.30, varying by class.
- Forecast burned area was 1.72 km² against 1.07 km² observed, so the model over-predicted by about 60%. The paper says the shapes matched well except to the southwest.
- About 98% of the simulated area burned in the first 15 h.
- One run took 2 h 11 min on 8 HPC nodes.
- The paper reports no Sørensen or Jaccard score and no baseline. It evaluates only total area and a visual shape match on one fire.
- The authors note there are six MODIS/VIIRS overpasses a day over India and that alerts arrive 1–1.5 h after detection.

**What this means for Ratapani.** The C-DAC system has been validated on one fire with an area ratio and a visual check. It has not been tested against a circle or persistence baseline. Our finding that Rothermel plus level set does no better than a circle therefore does not contradict any published C-DAC skill score; there is none. Also, the C-DAC fuel inputs (forest litter at 0.27 kg/m²) are Himalayan and differ from teak litter (see 5.2).

### 1.2 Chavan et al. 2025, C-DAC fuel parameterisation and FDS (Sikkim) [PARTIAL]
**Citation.** Chavan, M., Labade, M., Kale, M., Kumar, V., Pardeshi, S., Khare, M. (2025). Forest Fuel Parameterization and Large-Scale Fire Simulation Modeling Using High-Performance Computing in the Himalayas. *ISPRS Annals* X-5/W2-2025, 103. https://isprs-annals.copernicus.org/articles/X-5-W2-2025/103/2025/isprs-annals-X-5-W2-2025-103-2025.pdf

**What they did.** Ran the Fire Dynamics Simulator (a CFD model) at 1 m resolution on HPC for a grass fire near Melli, Sikkim. They compared the result with a 23.45-acre burned polygon digitised from satellite imagery.

**Numbers.**
- The paper states plainly: "There are no ready references available for Indian regions for grasses rate of spread."
- It cites Sati et al. (2016) for 0.888 m/s in Chir pine and pine-oak forests in Uttarakhand. I have not read Sati et al.
- Forest staff told the authors spread is about 2 m/s.
- The FDS input table lists a rate of spread of 0.002 m/s (≈7 m/h), taken from McGrattan et al.
- I found no quantitative overlap score.

**What this means for Ratapani.** C-DAC itself flags that India has no measured rates of spread or fuel parameters. Anything we measure from VIIRS for teak litter would be new information, not something to check against an Indian reference.

### 1.3 Sikkim Wildfire Spread Forecasting and Monitoring System (SWFMS) [ABSTRACT]
**Source.** National Supercomputing Mission project page. https://nsmindia.in/applications/projects/sikkim-wildfire-spread-forecasting-and-monitoring-system-swfms/

**What it is.** C-DAC built the system with the Sikkim Department of Science and Technology and IIT Kharagpur. It gives 48 h WRF-SFIRE forecasts from a satellite- or field-reported ignition.

**What I could not find.** I found no published C-DAC WRF-SFIRE system or skill evaluation for Uttarakhand or Himachal. Searches turned up only academic WRF-Fire weather studies of the Western Himalaya (Khadke, Mukherjee and Ghosh, *J. Earth Syst. Sci.* 2026), which I did not read. Treat claims of a C-DAC Uttarakhand system as unverified.

### 1.4 Mondal and Sukumar 2016, fire controls across a rainfall gradient at Mudumalai [FULL, via HTML]
**Citation.** Mondal, N., Sukumar, R. (2016). Fires in Seasonally Dry Tropical Forest: Testing the Varying Constraints Hypothesis across a Regional Rainfall Gradient. *PLoS ONE* 11(7): e0159691. https://doi.org/10.1371/journal.pone.0159691

**What they did.** Mapped annual area burnt at Mudumalai (321 km²) by ground and GPS survey for 1991–2010. Related it to 13 rain gauges across four moisture regimes.

**Numbers.**
- On average 20.1% (±3.2% SE) of the landscape burned each year. The range was 49% in 1991 down to 0.1% in 2006.
- Mean fire return interval was 4.9 years. It was 19.2 years in the wettest regime (≥1400 mm), 2.9 years in the 1000–1200 mm regime and 11.6 years in the driest (≤1000 mm).
- Fires come mainly in Jan–Apr, peaking in Feb–Mar.
- In wetter forest, early-dry-season rain (a proxy for fuel moisture) limits fire. In the driest forest, wet-season rain (a proxy for fuel load) limits it. Area burned the previous year also matters.
- The study reports no spread rates.

**What this means for Ratapani.** Ratapani (Central India, roughly 1000–1200 mm, dry deciduous) probably sits in the middle regime, where both fuel load and moisture matter. Two features follow: the previous year's burn scar (fuel not yet rebuilt) and pre-season rainfall.

### 1.5 Other Indian context [ABSTRACT]
- **Kodandapani et al.**, Western Ghats fire-regime work (e.g., "Conservation threat of increasing fire frequencies in the Western Ghats"). Seen only in search results. Their snippets say Mudumalai fires are "mostly surface fires… with grass and litter as the primary fuel". https://www.academia.edu/3479596/Conservation_Threat_of_Increasing_Fire_Frequencies_in_the_Western_Ghats_India
- **Khandwa / North Betul, Madhya Pradesh** (*Environ. Monit. Assess.* 2024, https://link.springer.com/article/10.1007/s10661-024-12960-0). A 22-year MODIS fire-risk study. The press summary says teak-dominated Khandwa is at higher risk than mixed Betul and that fires cluster near roads. It is a fire-occurrence study, not a spread study.

**Gap.** I did not find any Indian field measurement of rate of spread, flame length or fuel load for teak litter in Central India, Bandipur or Mudumalai, despite several searches. The closest Indian numbers are the Himalayan C-DAC fuel plots (1.1) and the Chir pine rate quoted second-hand (1.2). **This is a real gap, not a search failure that I am hiding.**

---

## 2. Operational spread simulators and how they are evaluated

### 2.1 Filippi, Mallet and Nader 2014, four spread models against 80 Corsican fires [PARTIAL: methods, figures and discussion read]
**Citation.** Filippi, J.B., Mallet, V., Nader, B. (2014). Evaluation of forest fire models on a large observation database. *Nat. Hazards Earth Syst. Sci.* 14, 3077–3091. https://doi.org/10.5194/nhess-14-3077-2014

**What they did.**
- Ran 320 fully automated simulations: four models on each of 80 fires, with only the ignition point and final burned area known and no tuning.
- The four models were a "3% of wind speed" rule of thumb (used deliberately as the lowest reference), Balbi stationary, Balbi non-stationary and Rothermel.
- Scored each run with Sørensen, Jaccard and Kappa, plus shape and arrival-time agreement.

**Numbers.**
- Scores are shown only as distributions in figures; I did not find a single mean in the text. Sørensen per fire ranges from about 0 to about 0.9 across the 80 cases.
- The non-stationary Balbi model was best overall.
- Rothermel was best on arrival time, "less prone to over-prediction", because its wind limit slows the front.
- Fire durations were unknown and were set to a 24 h maximum. The authors say this is "a very rough approximation", and it made arrival-time scores less meaningful.

**What this means for Ratapani.** Keep a trivial reference model in every evaluation, as they did; for us that is the circle and persistence. Expect a wide spread of per-fire scores, so report distributions, not one mean. Unknown fire start and end times, which is our burn-scar problem, damage time-based scores most.

### 2.2 Fox-Hughes et al. 2024, Australian simulators compared [ABSTRACT]
**Citation.** Fox-Hughes, P., et al. (2024). An evaluation of wildland fire simulators used operationally in Australia. *Int. J. Wildland Fire* 33, WF23028. https://doi.org/10.1071/WF23028

**What they did.** Compared Australis, Phoenix, Prometheus and Spark on 10 historical fires, using spatial metrics designed with end users and perturbed-input ensembles.

**Finding.** "No simulator was clearly superior to others." I could not get the exact scores (the CSIRO and connectsci full text was blocked to me).

**What this means for Ratapani.** Swapping one physics engine for another is unlikely to fix our model. Input uncertainty dominates.

### 2.3 Phoenix RapidFire version comparison and Spark lateral-spread study [ABSTRACT]
- **Phoenix versions** (*Forests*, 2018; https://doaj.org/article/a2829722dc4c4b3f89e475c251a1c12c). Two Phoenix versions were scored on 9 fires with an Area Difference Index. The newer version was only marginally, and not significantly, better, and 3 of the 9 fires were better predicted by the old version.
- **Spark with vorticity-driven lateral spread** (Sharples et al., MODSIM 2017, https://mssanz.org.au/modsim2017/H10/sharples.pdf). Used the threat score (which is the same as Jaccard/IoU). The simulation matched perimeters over 45 h except where suppression likely acted.

### 2.4 Cardil et al. 2023, Wildfire Analyst on 1,853 Californian fires [ABSTRACT]
**Citation.** Cardil, A., et al. (2023). Performance of operational fire spread models in California. *Int. J. Wildland Fire* 32(11), 1492–1502. https://doi.org/10.1071/WF22128

**What they did.** Compared observed rate of spread (from the FireGuard database) with automatic Wildfire Analyst predictions for 1,853 initial-attack fires from 2019–2021.

**Finding.** Errors were "reasonable" for automatic runs. Some timber fuel models under-predicted rate of spread. I could not get the exact error numbers.

**What this means for Ratapani.** The models judged adequate operationally were evaluated on rate of spread for initial-attack fires, a different task from multi-day shape forecasts.

### 2.5 Cruz and Alexander 2013, how accurate rate-of-spread models really are [FULL]
**Citation.** Cruz, M.G., Alexander, M.E. (2013). Uncertainty associated with model predictions of surface and crown fire rates of spread. *Environ. Model. Softw.* 47, 16–28. PDF: https://d10.nrfirescience.org/sites/default/files/2023-07/09-S-03-1_CruzAlexander_2013_EMS_UncerModeledROS.pdf

**What they did.** Compiled 49 evaluation datasets with 1,278 observations of predicted against observed rate of spread.

**Numbers.**
- Only 3% of predictions (35 of 1,278) were "exact".
- Mean absolute percent error (MAPE) ranged from 20% to 310%. Slightly more than half the datasets had MAPE of 51–75%.
- Under-prediction bias appeared in 75% of datasets; over individual predictions, 64% were under-predictions.
- For Rothermel (1972) datasets, MAPE ranged from 20% to 310%. Examples: hardwood-forest litter datasets (Brose 1997) at 20%, and Grabner at 53% and 67%. Conifer-forest litter datasets (van Wagtendonk and Botti) ranged from 57% to 310%.
- Surface fires are harder to predict than crown fires because the model must cover 3–4 orders of magnitude of rate of spread and must handle marginal, high-moisture burning.
- The authors propose ±35% as a reasonable accuracy target.

**What this means for Ratapani.** A physics model run with uncalibrated fuel and moisture inputs typically misses rate of spread by 50% or more, and creeping, marginal litter fires are the hardest case. Our physics model tying with a circle is what this literature would predict.

### 2.6 Benali et al. 2016 and Sá et al. 2017, FARSITE scored against satellite active fire (Portugal) [ABSTRACT]
- **Benali, A., et al. (2016).** Deciphering the impact of uncertainty on the accuracy of large wildfire spread simulations. *Sci. Total Environ.* 569–570, 73–85. https://doi.org/10.1016/j.scitotenv.2016.06.112
  - Eight large Portuguese fires, simulated in FARSITE and scored against satellite-observed fire progression.
  - Uncertainty in wind, fuel model assignment, and ignition location and time had the largest effect on accuracy.
- **Sá, A.C.L., Benali, A., et al. (2017).** Evaluating fire growth simulations using satellite active fire data. *Remote Sens. Environ.* 190, 302–317. https://doi.org/10.1016/j.rse.2016.12.023
  - Scored FARSITE on nine fires directly against MODIS active-fire detections, without reference perimeters.
  - Used absolute and relative spatial-discrepancy measures.
  - Found that coarse active-fire data still capture the spatial dynamics of fire growth.

**What this means for Ratapani.** There is published precedent for evaluating spread models against active-fire pixels instead of perimeters, which is our situation. Ignition time and location are a leading error source, and burn scars dated only to a 1–3 week window hit exactly that.

### 2.7 FARSITE, FlamMap, Prometheus and ELMFIRE in general [not separately read]
I did not read the original FARSITE (Finney 1998), Prometheus (Tymstra et al. 2010) or ELMFIRE (Lautenberger 2013) reports for this review. Their descriptions here come second-hand from papers I did read (2.1, 4.5, 3.6). All four rest on Rothermel-type surface spread, with Huygens elliptical wavelets (FARSITE, Prometheus) or a level set (ELMFIRE, WRF-SFIRE). None has published calibration for tropical teak litter that I could find. The standard US hardwood-litter fuel models are below.

### 2.8 Scott and Burgan 2005, standard fire-behaviour fuel models [FULL, tables checked]
**Citation.** Scott, J.H., Burgan, R.E. (2005). Standard Fire Behavior Fuel Models. USDA FS Gen. Tech. Rep. RMRS-GTR-153. https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr153.pdf

**Numbers (hardwood litter models).**

| Model | Description | 1-h fuel load | Dead-fuel moisture of extinction |
|---|---|---|---|
| TL2 | "low load, compact", "spread rate very low" | 1.40 t/ac (≈3.1 t/ha) | 25% |
| TL6 | moderate load | 2.40 t/ac (≈5.4 t/ha) | 25% |
| TL9 | very high load | 6.65 t/ac (≈14.9 t/ha) | 35% |

**What this means for Ratapani.** Teak litter measured in Ecuador averaged about 11 t/ha (see 5.2), between TL6 and TL9. If the level-set model used a default TL2 or TL6 with 25% moisture of extinction, it may be badly mis-parameterised for large, curled teak leaves.

---

## 3. Assimilating satellite active fire into spread models

### 3.1 Coen and Schroeder 2013, initialising and cycling from VIIRS [ABSTRACT]
**Citation.** Coen, J.L., Schroeder, W. (2013). Use of spatially refined satellite remote sensing fire detection data to initialize and evaluate coupled weather-wildfire growth model simulations. *Geophys. Res. Lett.* 40, 5536–5541. https://doi.org/10.1002/2013GL057868

**What they did.** Restarted CAWFE runs of the 2012 Little Bear Fire (New Mexico) from VIIRS 375 m, 12-hourly detections.

**Finding.**
- Restarted runs matched later satellite observations well for about 12–24 h, then drifted.
- Re-initialising every 12 h from the latest VIIRS perimeter ("cycling") corrected the drift.

**What this means for Ratapani.** Even a coupled physics model is skilful for only about one pass interval before it must be reset to observations. This matches our finding that learned models gain only at longer gaps. The useful product is "reset at every pass, forecast to the next pass".

### 3.2 Mandel et al. 2014, assimilating detections through fire arrival time [FULL]
**Citation.** Mandel, J., Kochanski, A.K., Vejmelka, M., Beezley, J.D. (2014). Data Assimilation of Satellite Fire Detection in Coupled Atmosphere-Fire Simulation by WRF-SFIRE. In *Advances in Forest Fire Research* (Coimbra). arXiv:1410.6948. https://arxiv.org/abs/1410.6948

**What they did.**
- Represented the fire state as a fire arrival time field.
- Found the most probable arrival-time field that stays close to the forecast and also maximises the likelihood of the detections, including the absence of detection.
- Used a likelihood that depends on hours since fire arrival.

**Key statements.**
- Detection squares mean that "a fire… was detected somewhere in the square; it does not mean that the whole square is burning".
- False negatives are common.
- The authors cite Schroeder et al. 2014: VIIRS 375 m has a 50% probability of detecting about a 2 m² flaming fire at night and about 40 m² during the day.
- Without a cloud mask they "could not distinguish between missing data and negative fire detection".
- Detections "should be used to improve fire modeling in a statistical sense only, rather than as a direct input".

**What this means for Ratapani.** Treat each VIIRS pass as a noisy likelihood over fire arrival time, not as a hard mask. Use the cloud mask so that "not seen" means "seen clear and not burning", not "no data".

### 3.3 Farguell et al. 2021, fire arrival time from VIIRS and MODIS by support vector machine [FULL]
**Citation.** Farguell, A., Mandel, J., Haley, J., Mallia, D.V., Kochanski, A., Hilburn, K. (2021). Machine Learning Estimation of Fire Arrival Time from Level-2 Active Fires Satellite Data. *Remote Sensing* 13(11), 2203. https://doi.org/10.3390/rs13112203

**What they did.**
- Labelled every satellite pixel at every pass as fire, clear ground or no data, with confidence weights. Fire pixels below 70% confidence were dropped, and clear-ground pixels were given 95%.
- Fitted a support vector machine in (x, y, t) whose decision boundary is the fire arrival time surface.
- Tested on the 10 largest California fires of 2020 against airborne infrared perimeters.

**Numbers.** Burned-area absolute percentage error 12%; total burned-area mean percentage error 5%; false-alarm ratio 0.21; probability of detection 0.86; Sørensen 0.82.

**What this means for Ratapani.** This is the best-matched method for turning our sparse VIIRS passes into a continuous arrival-time map. It also gives a gap-filled "truth" that is better than raw pixels, which we can use both to train and to score our spread model. The clear-ground pixels carry information.

### 3.4 Srivas et al. 2016 and 2017, ensemble Kalman filter on FARSITE (WIFIRE) [ABSTRACT]
- **2016** (*Procedia Comput. Sci.*, https://doi.org/10.1016/j.procs.2016.05.328). Nudged FARSITE perimeters toward noisy observed perimeters with an ensemble Kalman filter. Tested on the 2014 Cocos fire with hourly updates.
- **2017** (ICCS; WIFIRE page https://wifire.ucsd.edu/portfolio/ensembles). Also estimated "fuel adjustment factors", which are per-fuel-type multipliers on rate of spread, over time.
- **Subramanian et al. 2020** (ICCS, https://www.iccs-meeting.org/archive/iccs2020/papers/121420217.pdf) added barrier points and reported significant improvement for the 2016 Sand Fire.

**What this means for Ratapani.** A cheap version of data assimilation is to learn one rate-of-spread multiplier per fire, per fuel class or per day from past passes. That is a low-dimensional calibration that can work even with sparse data.

### 3.5 Rochoux et al. 2015, ensemble Kalman filter on a Rothermel front tracker [PARTIAL: abstract and introduction]
**Citation.** Rochoux, M.C., Emery, C., Ricci, S., Cuenot, B., Trouvé, A. (2015). Towards predictive data-driven simulations of wildfire spread, Part II. *Nat. Hazards Earth Syst. Sci.* 15, 1721–1739. https://doi.org/10.5194/nhess-15-1721-2015

**What they did.** Compared correcting the fire front itself (state estimation) with correcting rate-of-spread parameters (parameter estimation, as in Part I). Tested on synthetic cases and a small grassland experiment.

**Findings.**
- Both approaches correct the front, and they complement each other.
- Ensemble members must vary both the initial fire location and the rate-of-spread parameters.
- The assimilation window must be matched to how long the initial condition stays informative ("persistence") and to how fast conditions change.

**What this means for Ratapani.** This supports perturbing the ignition or initial front in our ensemble, not only fuel and wind. It also says the useful horizon is set by how fast conditions change, which for us is the day–night cycle.

### 3.6 Fire-EnSF 2025, a diffusion-model filter [PARTIAL]
**Citation.** Shi, H.Z., Wang, Y., Liu, X. (2025). Fire-EnSF: Wildfire Spread Data Assimilation using Ensemble Score Filter. arXiv:2510.15954. https://arxiv.org/abs/2510.15954

**Finding.** The authors claim better accuracy, stability and cost than the ensemble Kalman filter. As far as I read, testing was on simulated fires. This is research-stage.

### 3.7 Neural-parameterised cellular automata 2026 [PARTIAL]
**Citation.** Zhenirovskyy, M., Matei, I., Vuppala, R., Kurihana, T., Wong, H.Y. (2026). Neural-Parameterized Cellular Automata for Wildfire Spread. arXiv:2606.11676. https://arxiv.org/abs/2606.11676

**What they did.** A convolutional network outputs spatially varying spread probability, wind-alignment and slope parameters for a differentiable probabilistic cellular automaton (written in JAX). The model is fitted to observed perimeters over a 10-day window.

**Number.** "IoU > 0.6 over 72-hour forecast horizons", on six large western-US fires.

**Caution.** IoU computed on cumulative burned area is inflated by the already-burned interior, which any persistence forecast also gets right. The abstract does not report a persistence comparison.

**What this means for Ratapani.** A hybrid model, with physics structure and learned local parameters, is a plausible next step. Score it only on new burned area.

---

## 4. Machine-learning spread models, and persistence

### 4.1 Huot et al. 2022, the Next Day Wildfire Spread dataset [FULL]
**Citation.** Huot, F., Hu, R.L., Goyal, N., Sankar, T., Ihme, M., Chen, Y.-F. (2022). Next Day Wildfire Spread: A Machine Learning Dataset to Predict Wildfire Spreading From Remote-Sensing Data. *IEEE Trans. Geosci. Remote Sens.* 60. arXiv:2112.02447. https://arxiv.org/abs/2112.02447

**What they did.** Used 18,545 US fire samples on 64×64 km tiles at 1 km resolution, with MODIS MOD14A1 daily fire masks. The task was to predict the day t+1 fire mask from the day t mask plus 11 drivers.

**Numbers.**

| Model | AUC-PR | Precision | Recall |
|---|---|---|---|
| Persistence | 11.5 | **35.7** | 27.3 |
| Logistic regression | 19.8 | 32.5 | 35.3 |
| Random forest | 22.5 | 26.3 | 46.9 |
| Neural network (best) | 28.4 | 33.6 | 43.1 |

Further results:
- **Persistence had the highest precision of all models.** It scores low on AUC-PR partly because a 0/1 forecast has no ranking, so AUC-PR penalises it.
- Removing the previous fire mask dropped AUC-PR to 6.8. Using the mask alone gave 22.9 (precision 29.2, recall 49.6).
- Other single drivers added only about 3–5 AUC-PR points.
- Coarsening the output to 2×, 4× and 8× pixels raised AUC-PR to 39.8, 53.5 and 66.3. Persistence at the same coarsening reached 19.5, 30.6 and 41.3.
- The authors flag several limitations: MODIS misses the late afternoon, its detection "is also conservative, especially at night or when there is cloud coverage", labels are noisy, and suppression affects the labels.

**What this means for Ratapani.** Most of the skill in learned next-day models comes from the current fire mask. When ML "beats persistence", it is mainly through ranking and recall, not precision. Compare our gradient boosting with persistence at a matched operating point (same predicted area), not only on AUC.

### 4.2 Gerard, Zhao and Sullivan 2023, the WildfireSpreadTS dataset [FULL]
**Citation.** Gerard, S., Zhao, Y., Sullivan, J. (2023). WildfireSpreadTS: A dataset of multi-modal time series for wildfire spread prediction. *NeurIPS 2023 Datasets and Benchmarks*. https://papers.neurips.cc/paper_files/paper/2023/file/ebd545176bdaa9cd5d45954947bd74b7-Paper-Datasets_and_Benchmarks.pdf

**What they did.** Built 607 US fires (2018–2021) with VIIRS 375 m daily masks (passes aggregated over 24 h) and 23 input channels. Predicted the next-day mask.

**Numbers.**
- Persistence scored a mean AP of 0.193 (F1 0.432), varying from 0.105 to 0.287 between years.
- **A "last pass of the day" persistence was worse:** AP 0.135, F1 0.333. The authors attribute this to later passes not covering the same area and to view-angle, intensity and cloud differences.
- Logistic regression reached 0.279–0.288 AP, Res18 U-Net 0.328–0.344, ConvLSTM 0.292–0.310, and UTAE (5 input days, vegetation features) 0.372.
- Adding the weather forecast, energy release component (ERC) and drought features made results worse.
- 35–49% of images had no detection on a given day, even within official fire dates. The dataset has "highly imbalanced labels and… noisy labels, due to smoke, clouds".

**What this means for Ratapani.**
- Build persistence as the union of recent passes, for example over the last 24 h, not just the last pass. A single VIIRS pass misses part of an active fire.
- More input variables can hurt.
- Day-to-day and year-to-year variation in persistence skill is large, so report it per fire-season.

### 4.3 Lahrichi et al. 2025, the WSTS+ benchmark [PARTIAL]
**Citation.** Lahrichi, S., Bova, J., Johnson, J., Malof, J. (2025). Improved Wildfire Spread Prediction with Time-Series Data and the WSTS+ Benchmark. arXiv:2502.12003 (v3). https://arxiv.org/abs/2502.12003

**Numbers.**
- Careful training raised WildfireSpreadTS AP from about 0.34 to 0.455–0.478 (Res18-UNet 0.468; UTAE(Res18) 0.478).
- In the ablations, removing focal loss dropped AP to 0.345, and not using AP for validation dropped it to 0.321.
- Test-year results vary widely.

**What this means for Ratapani.** Training choices (loss, class weighting, validation metric) moved skill as much as architecture did. For gradient boosting, the equivalent levers are class weights and choosing the decision threshold on the target metric.

### 4.4 Gopakumar and Pannozzo 2026, WildfireSpreadBench ("the metric decides the model") [FULL]
**Citation.** Gopakumar, A., Pannozzo, M. (2026). WildfireSpreadBench: The Metric Decides the Model in Wildfire Spread Prediction. NeurIPS 2026 Climate Change AI workshop. arXiv:2609.22191. https://arxiv.org/abs/2609.22191

**Numbers (2021 test year, threshold 0.5).**
- Persistence scored AP 0.287 and F1 0.535.
- The best-AP model (a BCE-trained U-Net, AP 0.53–0.56) had F1 of only 0.31–0.33 and flagged 4–5× the observed area.
- UTAE had AP 0.32–0.38 but F1 0.08–0.12, flagging 16–23× the observed area.
- **Only 3 of 6 models (ResNet18 U-Net, ConvLSTM, logistic regression) beat persistence on F1.** BCE U-Net, UTAE and flow matching all "fall below a parameter-free baseline once a threshold is applied".
- Going from 7 to 23 input channels changed AP by only 0.03.
- They recommend reporting AP together with F1 or IoU, the predicted-to-observed area ratio, and the same metrics for persistence.

**What this means for Ratapani.** This is the clearest published evidence that ML spread models often do not beat persistence once forced to draw a map. Always report the ratio of predicted to observed area. Also note that F1 and IoU carry the same information (IoU = F1/(2−F1)), so report one of them.

### 4.5 Radke et al. 2019, FireCast [FULL]
**Citation.** Radke, D., Hessler, A., Ellsworth, D. (2019). FireCast: Leveraging Deep Learning to Predict Wildfire Spread. *IJCAI 2019*, 4575–4581. https://www.ijcai.org/proceedings/2019/636

**What they did.** A CNN on Landsat, topography and 24 h of weather predicts which sampled pixels near the perimeter burn in the next 24 h. Tested on the Beaver Creek fire.

**Numbers.**
- Accuracy 87.7% for FireCast, 50.4% for random, and 67.8% (wet) and 63.6% (dry) for FARSITE.
- FireCast recall was 91.1%, but its **precision was only 3.6% and F-score 6.4%**.
- **There was no persistence baseline. The only baselines were random and an uncalibrated FARSITE.**

**What this means for Ratapani.** Many early ML spread papers report wins against weak baselines. Do not read their headline numbers as evidence that ML beats persistence.

### 4.6 Moustakas and Davlias 2021, random forest on 22 years of Kruger savanna burns [PARTIAL: abstract, methods, discussion]
**Citation.** Moustakas, A., Davlias, O. (2021). Minimal effect of prescribed burning on fire spread rate and intensity in savanna ecosystems. *Stoch. Environ. Res. Risk Assess.* https://doi.org/10.1007/s00477-021-01977-3 (arXiv:2005.07593)

**What they did.** Predicted rate of spread for experimental plot burns.

**Numbers.**
- Regression gave "< 20% accuracy", so they switched to five-class bins.
- The top drivers of spread rate were fuel moisture (21%), relative humidity (15%), wind (14%) and the previous year's rain (14%).
- They state that "predicting fire spread rate and intensity has been a poor endeavour… accuracy… has not yet exceeded 50%".

**What this means for Ratapani.** Even with measured moisture and wind on flat savanna plots, the rate of spread is hard to predict. Expect a ceiling on how much the drivers can add on top of persistence.

---

## 5. Litter and surface fires in tropical dry forest and savanna

### 5.1 Junpen et al. 2013, 80 experimental fires in northern Thai deciduous forest [FULL]
**Citation.** Junpen, A., Garivait, S., Bonnet, S., Pongpullponsak, A. (2013). Fire spread prediction for deciduous forest fires in Northern Thailand. *ScienceAsia* 39, 535–545. https://doi.org/10.2306/scienceasia1513-1874.2013.39.535

**What they did.**
- Ran 80 prescribed burns in 2008–2009 in mixed deciduous forest (whose characteristic species include *Tectona grandis*) and in dry dipterocarp forest.
- Weather during burns: 35–40 °C, relative humidity 58–75%, ground wind 0–0.5 m/s.
- Fuel: 3.88 t/ha in total, of which 2.36 t/ha was leaves and grass. Dead leaf and grass moisture was 4.5–17%. Slopes were 9–41%.

**Numbers.**

| Front | Rate of spread (m/min) | ≈ m/h | Mean (m/min) |
|---|---|---|---|
| Head fire | 0.51–2.55 | 31–153 | 1.37 |
| Back fire | 0.05–0.77 | 3–46 | 0.30 |
| Flank fire | 0.13–1.05 | 8–63 | 0.46 |

- Head fire flame length averaged 1.10 m and intensity 166 kW/m.
- Head fire was 2–15× faster than back fire.
- Leaf combustion efficiency was 0.98.
- The best model was ROS = a·exp(b·slope)·exp(−c·leaf moisture), with R² = 0.88.
- Monthly mean leaf moisture was 14% in January and about 6–7% from February to May.

**What this means for Ratapani.** This is the closest analogue. Ratapani's 10–60 m/h sits between back/flank and head-fire rates. Slope and dead-leaf moisture explain most of the variance; wind under the canopy is near zero. Slope deserves a strong place in the model, and fine-fuel moisture estimated from humidity and temperature is the main time-varying driver.

### 5.2 Ramos-Rodríguez et al. 2026, controlled burns in teak plantations (Ecuador) [FULL, Spanish]
**Citation.** Ramos-Rodríguez, M.P., Macías-Briones, K.Y., Cantos-Pionce, R.A., Manrique-Toala, T.O. (2026). Efectos de variables meteorológicas y del combustible sobre el comportamiento del fuego en *Tectona grandis* L.f. en Manabí, Ecuador. *Revista Forestal Mesoamericana Kurú* 23(52). https://doi.org/10.18845/rfmk.v23i52.8442

**What they did.** Ran 15 controlled burns in teak litter. Weather: 30–35 °C, relative humidity 51–64%, wind averaging 0.06 m/s.

**Numbers.**
- Litter load averaged 1.10 kg/m² (≈11 t/ha), ranging 0.56–2.31. Litter depth averaged 13.6 cm (7.7–21.7). Litter moisture averaged 12.4% (7.4–19.7%).
- **Rate of spread averaged 0.0080 m/s (≈29 m/h), ranging 0.0045–0.0119 m/s (≈16–43 m/h).**
- Flame height averaged 0.46 m (0.35–0.70).
- Intensity averaged 31 kcal/m/s (≈130 kW/m).
- Fuel load and moisture correlated with fire behaviour; the weather variables did not, though their range was narrow.
- The authors recommend burning at fuel moisture above 10% for safety.

**What this means for Ratapani.** These are directly measured teak-litter spread rates, and they sit right inside our observed 10–60 m/h. Our VIIRS-derived speeds are therefore physically plausible and are not artefacts. At about 30 m/h, a front crosses one 375 m VIIRS pixel in roughly 12 h, about one pass interval (see 6.4).

### 5.3 Huai Kha Khaeng dry dipterocarp burns (Thailand) [ABSTRACT]
**Source.** "Fire Behavior in Dry Deciduous Dipterocarp Forest at Huai Kha Khaeng Wildlife Sanctuary" (Thai journal; ResearchGate record https://www.researchgate.net/publication/265975738). I could not identify the authors or year with confidence.

**Numbers (from the abstract).** Across 21 plots, mean rate of spread was 1.89 m/min (≈113 m/h), intensity 190 kW/m and flame length 0.86 m. Dead fuel was 4.64 t/ha. Spread rose with wind and fuel-bed depth and fell with live-fuel moisture.

### 5.4 Govender, Trollope and van Wilgen 2006, Kruger savanna fire intensity [ABSTRACT]
**Citation.** Govender, N., Trollope, W.S.W., van Wilgen, B.W. (2006). The effect of fire season, fire frequency, rainfall and management on fire intensity in savanna vegetation in South Africa. *J. Appl. Ecol.* 43, 748–758.

**Numbers.** From 956 plot burns over 21 years, intensity ranged 28–17,905 kW/m. It varied with season (through fuel moisture) and with fuel load.

**What this means for Ratapani.** Savanna grass fires are 1–3 orders of magnitude more intense than our litter fires, so savanna rate-of-spread models should not be transferred.

### 5.5 Plucinski and Anderson 2008, when litter ignition fails [ABSTRACT]
**Citation.** Plucinski, M.P., Anderson, W.R. (2008). Laboratory determination of factors influencing successful point ignition in the litter layer of shrubland vegetation. *Int. J. Wildland Fire* 17(5), 628–637. https://doi.org/10.1071/WF07046

**Finding.** Sustained spread from a point is a logistic function of fuel moisture. Denser (more compact) beds tolerate less moisture. Larger ignition sources ignite wetter fuel. I did not get the threshold values.

**What this means for Ratapani.** Whether a litter fire keeps spreading at all is a probability that falls steeply with moisture. It depends on bed compaction, so fresh, loose teak leaves behave differently from compacted ones.

### 5.6 Balch et al. 2022, night-time flammability thresholds [ABSTRACT]
**Citation.** Balch, J.K., Abatzoglou, J.T., Joseph, M.B., Koontz, M.J., Mahood, A.L., McGlinchy, J., Cattau, M.E., Williams, A.P. (2022). Warming weakens the night-time barrier to global fire. *Nature* 602, 442–448. https://doi.org/10.1038/s41586-021-04325-1

**What they did.** Derived land-cover-specific vapour pressure deficit (VPD) thresholds, below which fire detections become very rare, from global day and night detections and hourly climate data.

**Numbers.** Flammable night hours rose by 110 h per year (1979–2020). Night fires became 7.2% more intense (2003–2020). I could not read the per-biome threshold values.

**What this means for Ratapani.** Night humidity recovery is the "barrier" that stalls creeping fires. A "night-time VPD above threshold" feature (or hours above threshold between passes) is a direct, physically motivated way to model whether a front advances overnight. It fits our 01:30 and 13:30 pass structure.

### 5.7 Global Fire Atlas: typical spread speeds in Southeast Asia and India (see 6.3)
Mean speeds are 0.7 km/day for Southeast Asia and 0.9 km/day for savanna. Details are in 6.3.

---

## 6. Evaluation: baselines, metrics, detection omission and pixel size

### 6.1 Schroeder et al. 2014, the VIIRS 375 m active-fire algorithm [PARTIAL]
**Citation.** Schroeder, W., Oliva, P., Giglio, L., Csiszar, I.A. (2014). The New VIIRS 375 m active fire detection data product: Algorithm description and initial assessment. *Remote Sens. Environ.* 143, 85–96. https://directreadout.sci.gsfc.nasa.gov/publications_documents/Schroeder_et_al_2014b_RSE.pdf

**Numbers.**
- Commission error was below 1.2% for nominal-confidence pixels.
- It detects 3× (day) and 25× (night) more fire pixels than the 750 m product.
- Pixels grow to about 795 × 784 m at the swath edge.
- Simulated daytime detection probability is lower than night-time for the same fire. The authors expect diurnal fire behaviour (bigger fires by day, cooler fires at night) to partly even out actual day and night detection rates.
- On average they found about 59,000 daytime and 15,000 night-time fire pixels per day globally (Aug 2013).

### 6.2 Chen et al. 2022, Fire Events Data Suite (FEDS) tracking of California fires [FULL, via PMC HTML]
**Citation.** Chen, Y., Hantson, S., Andela, N., Coffield, S.R., Graff, C.A., Morton, D.C., Ott, L.E., Foufoula-Georgiou, E., Smyth, P., Goulden, M.L., Randerson, J.T. (2022). California wildfire spread derived using VIIRS satellite observations and an object-based tracking system. *Scientific Data* 9, 249. https://doi.org/10.1038/s41597-022-01343-0 (https://pmc.ncbi.nlm.nih.gov/articles/PMC9151742/)

**What they did.**
- Tracked fires every 12 h at the ~01:30 and ~13:30 VIIRS passes.
- New detections join a fire if they fall within a 5 km buffer (forest) or 1 km (other land types).
- The perimeter is an alpha shape (α = 1 km) of all pixels since ignition, buffered by 187.5 m.
- The active front is the perimeter within 500 m of new detections.
- A fire is marked inactive after 5 days without detections.

**Numbers.**
- Against 2018 FRAP perimeters, per fire: IoU 0.706 ± 0.212, F1 0.847, precision 0.827, recall 0.923, area ratio 1.145. Daily progressions against NIFC gave per-fire F1 of 0.72–0.95.
- Positional uncertainty is about ±500 m (1σ).
- Pixels average about 470 m across the swath.
- The authors quote theoretical 50% detection thresholds of about 200 m² by day and 40 m² by night for a 700 K fire, and say small or cool fires may be missed, "especially by day".

**What this means for Ratapani.**
- This is the standard way to build 12-hourly fire objects and fronts from VIIRS; our pipeline should mirror it.
- With ±500 m position error and about 30 m/h fronts, a single 12 h pass-to-pass step (≈360 m of true spread) is below the positional noise. Spread can only be measured reliably over several passes or by fitting arrival-time surfaces.
- Cool, low-intensity litter fires are exactly those VIIRS misses by day, so daytime "no detection" is weak evidence of no fire.

### 6.3 Andela et al. 2019, the Global Fire Atlas [FULL]
**Citation.** Andela, N., Morton, D.C., Giglio, L., Paugam, R., Chen, Y., Hantson, S., van der Werf, G.R., Randerson, J.T. (2019). The Global Fire Atlas of individual fire size, duration, speed and direction. *Earth Syst. Sci. Data* 11, 529–552. https://doi.org/10.5194/essd-11-529-2019

**What they did.** Tracked 13.25 million fires (2003–2016) from the daily 500 m MCD64A1 burned-area product.

**Mean speeds (size-weighted in brackets).**

| Region or fire type | km/day | ≈ m/h |
|---|---|---|
| Global | 0.9 (3.2) | ≈38 |
| Southeast Asia | 0.7 (1.8) | ≈29 |
| Savanna | 0.9 (3.4) | not computed |

- Mean duration was 4.1 days in Southeast Asia.
- The authors warn that moderate-resolution burned area misses fires of about 100 ha or less, and that "care should be taken… in regions dominated by small fires".

**What this means for Ratapani.**
- Global mean speeds come out near one pixel per day (500 m/day ≈ 21 m/h). The measurable speed is partly set by pixel size divided by revisit time.
- Our 10–60 m/h range overlaps the floor set by 375 m pixels and 12 h revisits (≈31 m/h per pixel step). Speeds below about 30 m/h are hard to resolve pass to pass and show up as "no change" then a jump, which favours persistence at short gaps.

### 6.4 Veraverbeke et al. 2014, daily progression by kriging active-fire times [FULL: abstract and methods]
**Citation.** Veraverbeke, S., Sedano, F., Hook, S.J., Randerson, J.T., Jin, Y., Rogers, B.M. (2014). Mapping the daily progression of large wildland fires using MODIS active fire data. *Int. J. Wildland Fire* 23, 655–667. https://doi.org/10.1071/WF13015 (PDF: https://jin.ucdavis.edu/download_file/view/89/256)

**What they did.** Kriged MODIS detection times into a continuous burn-date map for 16 fires.

**Numbers.**
- Median kriging standard error was 0.80–3.56 days. Geolocation error added another 0.34–2.72 days.
- On 9 US fires, 73% of pixels were dated within one day, against 33% for MCD45A1 and 53% for MCD64A1.

**What this means for Ratapani.** Interpolating detection times (kriging, or the support vector machine of 3.3) gives better burn dates than burned-area products. This is a way to put sub-window dates on our 1–3-week burn scars, using VIIRS detections inside each scar.

### 6.5 FIRED (Balch et al. 2020) and GlobFire (Artés et al. 2019): event datasets [ABSTRACT]
- **FIRED.** Balch, J.K., et al. (2020). FIRED (Fire Events Delineation): an open, flexible algorithm and database of US fire events derived from the MODIS burned area product (2001–2019). *Remote Sensing* 12(21), 3498.
  - Its best US clustering thresholds were an 11-day window and 5 pixels (≈2.3 km), giving R² = 0.92 against MTBS fire sizes.
  - The authors expect the optimal thresholds "to vary across regions, based on… fire event size and rate of spread".
- **GlobFire.** Artés, T., Oom, D., de Rigo, D., Durrant, T.H., Maianti, P., Libertà, G., San-Miguel-Ayanz, J. (2019). A global wildfire dataset for the analysis of fire regimes and fire behaviour. *Scientific Data* 6, 296. https://doi.org/10.1038/s41597-019-0312-2
  - Builds a space-time graph of MCD64A1 patches, available in Earth Engine as daily and final perimeters.

**What this means for Ratapani.** The space and time clustering thresholds must be tuned locally. The US values (5 km buffer, 11 days, 5 days inactive) assume larger, faster fires than teak-litter creep.

### 6.6 Oliva and Schroeder 2015, VIIRS active fire as a burned-area map [ABSTRACT]
**Citation.** Oliva, P., Schroeder, W. (2015). Assessment of VIIRS 375 m active fire detection product for direct burned area mapping. *Remote Sens. Environ.* 160, 144–155. https://doi.org/10.1016/j.rse.2015.01.010

**Finding.** Compared against Landsat-8, accuracy was highest for large, long-lasting forest fires. **Omission and commission were largest in grasslands, savannas and agricultural areas** (short-lived, low-fuel fires).

**What this means for Ratapani.** Short, low-intensity litter fires behave more like the poorly detected class. Expect substantial VIIRS omission and calibrate it against the Sentinel-2/Landsat scars: what fraction of scar area ever had a VIIRS detection?

### 6.7 Metric lessons drawn across the papers
- Persistence is the standard reference in short-range forecasting; 4.4 states this explicitly.
- Persistence scores low on AUC-PR and AP only because its 0/1 output has no ranking (4.1, 4.4). Compare at matched predicted area or at an F1-optimal threshold.
- Sørensen/F1, Jaccard/IoU and the threat score are all the same overlap family. IoU = F1/(2−F1) exactly (4.4).
- Cumulative-area IoU is inflated by area that burned earlier (3.7). Score on newly burned area or on the front.
- Filippi et al. (2.1) argue that one score is never enough. Report a distribution over fires and several metrics, including a shape metric and a timing metric.

---

## Top lessons for our spread model (ranked)

**1. Make persistence fair, then evaluate on new area at a matched predicted area.**
- Use "union of detections over the last 24 h (or the last 2 passes)" as persistence, not "the last pass only". The last-pass version lost about 30% of its AP on WildfireSpreadTS (0.193 to 0.135; Gerard et al. 2023, 4.2).
- Score only newly burned pixels, and report the predicted-to-observed area ratio plus F1 at a fixed operating point as well as AP. Several published ML models fall below persistence once thresholded (Gopakumar and Pannozzo 2026, 4.4; Huot et al. 2022, 4.1, where persistence had the best precision).
- This may change our ">9 h" finding in either direction, so redo it before changing models.

**2. Switch from pixel masks to fire arrival time, assimilated at every pass.**
- Fit a continuous arrival-time surface from all VIIRS passes, using fire pixels, clear non-fire pixels and cloud as "unknown".
- Farguell et al. 2021 (3.3) reached Sørensen 0.82 and probability of detection 0.86. Mandel et al. 2014 (3.2) give the likelihood framework. Veraverbeke et al. 2014 (6.4) show interpolated burn dates beat burned-area products (73% against 53% within 1 day).
- Use the surface as both training target and evaluation truth. It also dates our 1–3-week Sentinel-2 and Landsat scars.

**3. Accept that the measurement floor is about one pixel per pass, and design for it.**
- At 375 m pixels, ±500 m positional error (Chen et al. 2022, 6.2) and 12 h passes, fronts of 10–60 m/h (teak litter measured at 16–43 m/h, Ramos-Rodríguez et al. 2026, 5.2) move less than one pixel between passes. Persistence will be hard to beat at short gaps by construction.
- Report skill as a function of gap length and quote the pixel-step speed (≈31 m/h) next to it (Andela et al. 2019, 6.3).
- Do not expect to beat persistence at 12 h.

**4. Model the day–night cycle explicitly: spread mostly happens in the afternoon, and nights stall or kill fires.**
- Use hours with VPD (or dead-fuel moisture) beyond a flammability threshold between passes as a key feature (Balch et al. 2022, 5.6).
- Dead-leaf moisture is the strongest driver of litter rate of spread (R² = 0.88 together with slope; Junpen et al. 2013, 5.1). Whether a fire keeps spreading is a steep logistic function of moisture (Plucinski and Anderson 2008, 5.5).
- Treat day→night and night→day transitions as different forecasting problems.

**5. Treat VIIRS non-detection as weak, asymmetric evidence, especially in daytime and for cool litter fires.**
- Detection thresholds are much larger by day than by night (about 200 m² against 40 m² at 700 K; Chen et al. 2022 citing Schroeder; Mandel et al. 2014; Schroeder et al. 2014, 6.1).
- Short, low-fuel fires have the highest omission (Oliva and Schroeder 2015, 6.6), and 35–49% of fire-days in WildfireSpreadTS have no detection (Gerard et al. 2023).
- Use cloud and scan-angle masks, add confidence weights, and do not penalise a model for "fire" predictions on pixels that were cloudy or at the swath edge.

**6. If we keep physics, calibrate it per fire and reset it at every pass. Do not run it free.**
- Uncalibrated rate-of-spread models typically miss by 50% or more and usually under-predict, and marginal surface fires are the hardest case (Cruz and Alexander 2013, 2.5).
- Free runs drift after 12–24 h, and re-initialising from VIIRS each cycle fixes the drift (Coen and Schroeder 2013, 3.1).
- Learn a few rate-of-spread multipliers per fire or fuel class (Srivas et al. 2016/17, 3.4; Rochoux et al. 2015, 3.5).
- Replace default US hardwood-litter fuel models (TL2/TL6, 25% moisture of extinction) with teak values. Measured teak load is about 11 t/ha (Scott and Burgan 2005, 2.8; Ramos-Rodríguez et al. 2026).

**7. Put slope, fuel continuity and last year's burn into the learned model; do not count on more weather channels.**
- Slope is a top driver in the closest analogue (Junpen et al. 2013).
- The previous year's burned area and seasonal rain control fuel availability in Indian dry forest (Mondal and Sukumar 2016, 1.4).
- Adding weather forecast, ERC and drought channels made ML worse on WildfireSpreadTS (Gerard et al. 2023). Expanding from 7 to 23 channels changed AP by only 0.03 (Gopakumar and Pannozzo 2026).

**8. Consider a hybrid next: a learned local spread probability inside a cellular automaton or level set, fitted by assimilation.**
- This is supported by neural-parameterised cellular automata (3.7) and by the result that ensembles must vary both initial location and rate-of-spread parameters (Rochoux et al. 2015). It keeps the physical structure (contiguity, slope, wind) while learning teak-specific rates.
- Score it on new area against persistence (lesson 1).

**9. Do not benchmark against weak baselines or single-fire area matches, and do not read others' skill claims that way.**
- FireCast's "beats FARSITE" came with 3.6% precision and no persistence baseline (Radke et al. 2019, 4.5).
- C-DAC's validation is one fire and an area ratio of 1.72 to 1.07 km² (Kale et al. 2024, 1.1).
- Report per-fire score distributions (Filippi et al. 2014, 2.1). Use per-season splits, because persistence skill varies 0.105–0.287 AP between years (Gerard et al. 2023).

**10. Fill the Indian field-data gap ourselves if possible.**
- There are no published Indian teak-litter measurements of rate of spread, fuel load or moisture of extinction. C-DAC says the same (Chavan et al. 2025, 1.2).
- A small set of timed, ground-truthed fires in Ratapani would calibrate everything above. Thai and Ecuadorian protocols (5.1, 5.2) show 15–80 plots are enough.

---

## Reading status summary

**[FULL] (12):**
- Kale 2024
- Mondal and Sukumar 2016
- Cruz and Alexander 2013
- Scott and Burgan 2005 (tables)
- Mandel 2014
- Farguell 2021
- Huot 2022
- Gerard 2023
- Gopakumar and Pannozzo 2026
- Radke 2019
- Junpen 2013
- Ramos-Rodríguez 2026

**[FULL or near-full] (3):**
- Chen 2022 (FEDS)
- Andela 2019 (Global Fire Atlas)
- Veraverbeke 2014

**[PARTIAL] (8):**
- Moustakas and Davlias 2021
- Chavan 2025
- Filippi 2014
- Rochoux 2015
- Fire-EnSF 2025
- Neural cellular automata 2026
- Lahrichi 2025 (WSTS+)
- Schroeder 2014

**[ABSTRACT] (13 papers, plus 3 non-paper sources):**
- Phoenix version comparison 2018
- Fox-Hughes 2024
- Cardil 2023
- Spark/Sharples 2017
- Coen and Schroeder 2013
- Srivas 2016/2017
- Benali 2016
- Sá 2017
- FIRED 2020
- GlobFire 2019
- Oliva and Schroeder 2015
- Govender 2006
- Plucinski and Anderson 2008

Also seen only in abstract or summary form, and not counted as papers above: Balch 2022, the Huai Kha Khaeng study, and the SWFMS project page.

**Not found despite searching:**
- Any Indian field measurement of teak-litter rate of spread, flame length or fuel load.
- A published C-DAC WRF-SFIRE system for Uttarakhand or Himachal.
- Exact per-biome VPD thresholds (Balch 2022 full text was paywalled).
