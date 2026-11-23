# Fire type and cause from satellite patterns: what the literature offers, what our own data shows, and what to do (scouting round 3, topic "cause", 14 Oct 2026)

This note asks one question: can we tell managed or deliberate burns, crop fires and escapes apart from satellite patterns (shape, timing, FRP, persistence, size, location), and would doing so improve the 2-day model? Rule sets for fire lines and controlled burns are already in `fire_management_practice.md` (Part D1–D2). Crop-burn imagery (Walker et al. 2022) is in `high_res_imagery.md` §4, and Hawkes and point-process contagion is in `short_horizon_prediction.md` §4. They are not repeated here. This note adds cause-classifier literature, crop-versus-forest timing, weekly cycles, and hot-spot methods. It also adds new measurements on our own VIIRS, the 20 m scar rasters and the lean LOSO model, made this session.

Reading status: **FULL** = whole paper read; **PARTIAL** = main text read, supplement or part missing; **ABSTRACT ONLY**. My own reasoning is marked [inference].

---

## Headline findings

1. **Cause classifiers on fire records work for "natural vs human" (93–94% accuracy), not for separating human causes (55–70%).** Spain, France and the western US all agree. The most useful predictors are season or day of year, time of day, elevation and human-modification indices. Distance to roads was *not* important in the largest study (US, 2.3 M fires). For us, >95% of fires are human-caused and there are no cause records. We cannot train a cause classifier. We can only build proxy rules and check them in the field.
2. **Our own data: crop fires are a small contaminant of our labels.** Only 207 of 8,117 VIIRS points (2.5%) fall in cells with ≥20% cropland. Those points are late: 34% fall after 15 April, against 9% in the forest interior. They are also hotter (p90 FRP 16.3 vs 10.9 MW). The scar labels already exclude WorldCover cropland pixels.
3. **There is no weekly cycle in Ratapani fire activity** (Monte Carlo p = 0.26–0.80 in every subgroup). That matches the global literature, which finds weekly cycles in croplands but not in wildlands. **Do not add day-of-week features.**
4. **Winter fires look managed. Spring fires do not.** Night detections are 2–10% of Nov–Jan events and 37–39% of Mar–May events. Linear scars (elongation ≥4, width ≤80 m, length ≥300 m) make up 9.7% of January scar patches and 1.6–3.6% from February to May. Under the round-2 rule (Nov–20 Feb, day-only, one day, FRP ≤ median), 379 of 953 Nov–Feb VIIRS events are "probable managed".
5. **Probable-managed and crop-edge positives are a small share of what the model has to catch, and both are caught less often than the rest.**
   - Managed-proxy or linear first burns are 4.8% + 2.5% of positive cell-days, with recall@5 23.0%.
   - Crop-edge cells are 14.5% of positive cell-days, with recall@5 23.4% against 29.4% for the interior.
   - The model's real strengths are elsewhere. Recall@5 is 32.5% in cells that burned in ≥4 of the other 7 seasons (74% of positives) but only 1.4% in cells that never burned in other seasons. It is 46% for scars of 10–25 ha against 20% for scars ≤2 ha, and 34% for "spread" positives against 25% for isolated ones.
6. **Retraining tests (LOSO 2017–2024, same scorer, section D).** Seed noise is about ±0.25 points.
   - Dropping managed-proxy positives from training labels: −0.1 point. Do not do it.
   - Per-cell timing priors: +0.1.
   - A separate crop-edge model raises crop-edge recall from 23.2% to 27.6% but costs the interior. Rank-blended with the base model it gives 29.07% vs 28.70% overall (8/8 seasons better), with crop-edge recall at 25.2%. Roughly half of that gain is plain ensembling.
   - **The realistic gain from cause separation is +0.2–0.5 points overall and about +2 points on crop-edge cells.**
7. **Hot-spot methods add nothing over the burn-history prior.** An emerging-hot-spot classification (Getis-Ord Gi* plus Mann-Kendall) on 10 years of scars, and neighbourhood-smoothed burn frequency, rank held-out burned cells no better than plain own-cell frequency: 12.7% vs 12.5% at top-5 per beat-season. Repeat VIIRS ignition sources exist but are few: 75 cells had an event start in ≥4 of 12 seasons, against 42 expected at random.

---

## A. Literature: classifying fire cause from records and attributes

### A1. Ochoa, Franquesa, Rodrigues & Chuvieco 2026, *Fire* 9(4):138, "Inferring Wildfire Ignition Causes in Spain Using Machine Learning and Explainable AI". https://doi.org/10.3390/fire9040138 (OA PDF via https://zaguan.unizar.es/record/171165). **FULL**

**Data.**
- The ESFire30 Landsat perimeters (1985–2023, burns >5 ha, 119,498 perimeters, 5.98 Mha) were joined to the EGIF official cause records.
- EGIF has coordinates only from 2012; before that it uses a 10 × 10 km grid. Ignitions were scattered randomly over burnable land in each grid square.
- A perimeter took the cause of an EGIF record in the same grid square with a similar burned area (±10 ha). Failing that, it took the grid square's majority cause.

**Classes (Table 1).**

| Cause | Fires | Share | 90th-percentile size |
|---|---|---|---|
| Lightning | 2,966 | 3% | 85 ha |
| Negligence | 11,809 | 10% | 58 ha |
| Intentional | 50,344 | 42% | 68 ha |
| Unknown | 54,167 | 45% | |
| Rekindling | 212 | 0.17% | |

**Model.**
- Random forest: 200 trees, max_features = sqrt, min_samples_split = 5, class_weight = balanced.
- SMOTE with k = 2 on the training set only. 70/30 stratified split. 5-fold CV accuracy 0.79 ± 0.004.

**Inputs.**
- Kernel density of secondary roads.
- Five interface areas inside each perimeter: forest–agriculture, wildland–urban, wildland–agriculture, wildland–forest and forest–urban. Each is a 250 m buffer around forest or wildland intersected with the other land use.
- Rural population (1–100 people/km²), land abandonment, livestock density.
- Summer means of nine climate variables, August SPEI-3, standardised spring NDVI.

**Results.**

| Class | Precision | Recall | F1 |
|---|---|---|---|
| Intentional | 0.91 | 0.89 | 0.90 |
| Negligence | 0.57 | 0.65 | 0.61 |
| Lightning | 0.49 | 0.39 | 0.43 |
| Rekindling | 0.15 | 0.03 | 0.05 |
| Overall | | | 0.82 (accuracy 0.82) |

SMOTE did not raise overall F1. Negligence fires happen under hot, dry, windy conditions at agricultural interfaces. Intentional fires happen in cooler, wetter, more populated places with land-use change. The authors stress that "inference" here means prediction, not causal proof, and that the cause records themselves are uncertain.

**Concrete action for us (threads 1, 5):**
- (i) The interface metric is cheap: the area of forest within 250 m of cropland or settlement, per cell. It is a better-defined version of our `dist_crop_cell` and `dist_village`. Compute it from WorldCover at 10 m (`wc_40`, `wc_50` against `wc_10/20/30`) as `fai_ha` and `wui_ha` per 500 m cell. Expected gain for the 2-day model: ≤0.5 point [inference], because distance features already carry most of this.
- (ii) Their perimeter-to-record matching rule (same grid square, ±10 ha) is a template for matching Forest Department fire registers to our scars in thread 5. Use the beat plus a ±2-day window plus an area tolerance.

### A2. Bountzouklis, Fox & Di Bernardino 2023, *Environ. Res. Lett.* 18:044038, "Predicting wildfire ignition causes in Southern France using XAI". https://doi.org/10.1088/1748-9326/acc8ee (HAL: hal-04091177). **FULL**

**Data.** Prométhée database, 1997–2020, 48,038 fires on a 2 × 2 km grid. 60% have a known cause. Of the 27,620 known: arson 38.4%, private negligence 26.7%, professional negligence 17.2%, accidental 10.1%, lightning 7.6%.

**Features.**
- Corine land cover, elevation, aspect, TWI, TRI.
- Population density, Gini index, income, unemployment.
- Road, powerline and railway densities.
- Season.
- Burned-area class: <0.1, 0.1–0.5, 0.6–1, 1–25, >25 ha.
- XY coordinates.
- Time of day: morning 05–12, afternoon 12–17, evening 17–21, night 21–05.

**Model.** RF with SMOTE, 70/30 split, random search then grid search.

**Results.** Overall accuracy 69.8%.

| Class | Precision | Recall | F1 |
|---|---|---|---|
| Lightning | 0.85 | 0.91 | 0.88 |
| Accidental | 0.81 | 0.74 | 0.77 |
| Professional negligence | 0.67 | 0.63 | 0.65 |
| Arson | 0.60 | 0.69 | 0.64 |
| Private negligence | 0.59 | 0.52 | 0.55 |

- The top SHAP features were summer, elevation and **afternoon**. Spring, coordinates, BA <0.1 ha and secondary road density came next.
- Arson is marked by summer, **night** and location. Professional negligence (agricultural burning) is marked by being outside summer and by small size (<0.1 ha).
- Arson and private negligence are confused 159 and 266 times. Both happen at the wildland–urban interface.

**Concrete action for us:**
- (i) The two best separators of deliberate vs negligent human fires here are **time of day** and **size**. We have both: VIIRS day/night, and scar ha. Night ignitions point to deliberate burning in France. In Ratapani, night share rises from 2–10% (Nov–Jan) to ~38% (Mar–May) (section C1). That fits winter burns being attended and put out by evening, and spring fires being left to run [inference].
- (ii) Small, out-of-peak-season burns are the "professional or agricultural" signature, the same as our managed proxy.
- (iii) Coordinates as features helped. Our `prior` and cell ID already do this.

### A3. Pourmohamad, Abatzoglou, Belval, Fleishman, Short, Reeves, Nauslar, Higuera, Henderson, Ball, AghaKouchak, Prestemon, Olszewski & Sadegh 2025, *Earth's Future* 13:e2024EF005187, "Inference of Wildfire Causes From Their Physical, Biological, Social and Management Attributes". https://doi.org/10.1029/2024EF005187 (Treesearch PDF 68868). **FULL**

**Data.** FPA FOD-Attributes, western US, 1992–2020, 12 known causes, >300 attributes per fire. Inputs were weather on the ignition day, climate, topography, infrastructure, land cover, NDVI, population, social vulnerability, GDP, and preparedness level.

**Model.** XGBoost beat RF, AdaBoost, GBoost and a deep neural network. Out-of-sample accuracy was >70%.

**Results.**
- Natural vs human: **93%** (natural 94%). Among the 11 human causes: **55%**.
- Power-line fires: 8%. One cause class: 1%.
- Class weights did not help.
- Top SHAP features: global human modification index, elevation, discovery day of year, fire year, minimum temperature on the ignition day.
- **"Distance to road was not an important attribute"** in their model.
- Debris and open burning, and recreation fires, ignite on days with relatively *low* VPD and high fuel moisture (fm100). Lightning and power-line fires ignite when VPD is high.
- Day of year drives the debris-burning and fireworks classes.
- State models ranged from 60% (CA) to 81% (NV).
- The 150,247 unknown-cause fires were attributed as: equipment 21%, natural 20%, arson 18%, debris 15%. The authors accept a class only at >90% probability.

**Concrete action for us (thread 1 label hygiene, thread 5):**
- (i) **Weather as a cause marker:** deliberate debris or management burns happen on *low-danger* days. Test: among our Nov–Feb day-only VIIRS events, do "probable managed" ones fall on days with RH above the season median? If they do, add `RH ≥ median` to the managed rule as a fifth condition.
- (ii) For any cause label we infer, use a probability threshold such as 0.9 and leave the rest "unknown", as they did. Do not force every scar into a class.
- (iii) Their finding that discovery day of year is a top cause feature backs up what our data shows: season is the main discriminator.

### A4. Earlier cause-classifier work (from the reference lists above, and searches). **ABSTRACT ONLY**

- **Rodrigues & de la Riva 2014** (Spain): RF for human-caused ignition. AUC 0.90, falling to ~0.76 when only known-cause fires are used. Lesson: unknown-cause records bias the model.
- **Syphard & Keeley 2015**, IJWF 24:37–47, https://doi.org/10.1071/WF14024. In southern California (>95% human), the number of fires and the area burned differ by cause. The causes that burn most area cluster in autumn. Equipment causes most fires, while power lines cause the most area.
- **ArcGIS FPA FOD sample notebook** (https://developers.arcgis.com/python/samples/historical-wildfire-analysis/): RF gives about 0.92 for arson vs not, from fields known at discovery. Warning: some of those fields leak post-ignition information (also raised by a 2026 BIO Web Conf paper, https://www.bio-conferences.org/10.1051/bioconf/202623100037).

**Lesson for us:** without ground-truth causes, any classifier is circular. We should collect cause labels in the field (thread 5) before training one.

---

## B. Literature: satellite signatures of fire type (timing, weekday, persistence, shape, land cover)

### B1. Jethva 2026, *Remote Sensing* 18:1506, "Timing the Flames: Geostationary Satellite Detection of …" (NW India stubble burning). https://mdpi-res.com/d_attachment/remotesensing/remotesensing-18-01506/article_deploy/remotesensing-18-01506.pdf. **FULL**

- **The shift.** GK2A-AMI geostationary data (10-minute full disc, 2 km IR, 3.8 µm and 11.2 µm) show that peak paddy-residue burning in Punjab and Haryana has moved from **13–14 h to 16–17 h IST** since 2022.
- **Consequence.** MODIS and VIIRS counts have fallen sharply since 2022 even though aerosol rose. Polar orbiters at ~13:30 miss the late fires. Aqua's orbital drift catches some.
- **Method.** Hourly ΔTb(3.8 − 11.2 µm), normalised to the 09–11 IST mean, mapped for 12–18 IST.
- **Cross-checks.** A Current Science MSG study reports the peak moving from ~13:30 (2020) to ~17:00 (2024). iFOREST reports >90% of large Punjab farm fires after 15:00 in 2025, against 3% in 2021.

**Concrete action for us (threads 1, 2, 5):**
- (i) VIIRS sees Ratapani only at ~13:30 and ~02:00 IST. Our day overpass times run 12:45–14:15 IST (5–95%, section C1).
- (ii) Any fire that starts after ~14:30 and dies before ~01:30 is invisible to VIIRS. The scar is then dated only by imagery. That is the likely reason 47% of our first-burn windows have no VIIRS match (section C3).
- (iii) If crop or managed fires in MP follow the Punjab shift, crop-edge VIIRS counts will undercount crop fires.
- (iv) For the live system (thread 5), ask in the field when fires are lit. If ignitions cluster after 15:00, the alert lag from VIIRS is ~11 h (next 02:00 pass), not 0.

### B2. Earl & Simmonds 2018, *JGR Atmospheres*, "Spatial and temporal variability and trends in 2001–2016 global fire activity". University of Melbourne repository PDF. **FULL** (accepted manuscript)

- **Method.** MODIS active-fire counts in 18 regions, weekly-cycle Monte Carlo test: the range between the weekday maximum and minimum, compared against 10,000 shuffles.
- **Results.** The USA has the strongest weekly cycle. Africa's is significant in all seasons, and Canada's in all seasons except summer.
- **India.** Box 14 has a significant upward trend in active fires (p < 0.01), linked to crop-residue burning. Its weekly-cycle analysis was **inconclusive**.

### B3. Pereira, Turkman, Turkman & Oom 2019, *Sci. Rep.* 9:11424, "Anthromes displaying evidence of weekly cycles in active fire data cover 70% of the global land surface". https://doi.org/10.1038/s41598-019-47678-4 (PMC6684812). **FULL**

- **Method.** Bayesian harmonic regression with a simultaneous 95% credible band on MCD14ML.
- **Global pattern.** Sunday is the minimum. Tue–Thu each average >12,000 fires and Sunday <11,000.
- **By land use.** Croplands show the strongest cycles. Rangelands and seminatural lands (53% of fires) show weaker cycles that are still significant. Earlier work found no weekly cycle in settled areas, forests or wildlands.
- **Religion.** In Africa, the minimum is on Sunday in Christian regions and on Friday in Muslim regions. Aerosol in the Middle East and India is lower on Thursday and Friday.

**Concrete action for us (B2 + B3 + our test in C2):** our Monte Carlo test (C2) finds no weekly cycle. **Drop any day-of-week idea from thread 1.** [inference] A weekly cycle tied to local haat (market) days could exist within single beats but would need beat-level ignition records. Revisit once the field log (thread 5) has 1–2 seasons of data.

### B4. Li, Fu, Holmes, … 2023, *Remote Sensing* 15:2725, "An Analysis of Prescribed Fire Activities and Emissions in the Southeastern United States from 2013 to 2020". https://doi.org/10.3390/rs15112725 (PMC11296730). **PARTIAL** (main text; Algorithms S1–S3 are in the supplement, not read)

**Rules on FINN (VIIRS + MODIS based) fire points.**
- **Agricultural:** the dominant NLCD 30 m class within a square of the fire's burned area is cropland.
- **Wildfire:** detections clustered within **1000 m** on the same day, and linked across **consecutive days within 800 m**, that last **>1 day**. Both distances were chosen by the elbow method.
- **Prescribed:** everything else. Prescribed burns are assumed to start and end the same day.

**Validation.**
- Agricultural rule vs Florida permits: 88.8% of algorithm-flagged agricultural points were permit-agricultural, but only 65.4% of permit-agricultural points were caught.
- Wildfire rule: only 665 of 3,430 WFIGS wildfires matched, against 22,140 algorithm wildfires.
- Prescribed area vs permits: R² <0.05 per fire, >0.17 on a 4 km grid, >0.55 at state-day level.
- Prescribed burns came out as 79–89% of burned area in FL, GA and SC.

**Concrete action for us (thread 2 labels):**
- (i) Their **single-day vs multi-day** rule is the simplest managed-vs-escape separator, and we already have it: 88.6% of our VIIRS events are single-day (C1).
- (ii) But their validation shows the rule is weak per fire (R² <0.05). Use it for aggregate statistics such as the share of managed burns per beat-season, not as a per-scar truth label.
- (iii) Their 1000 m / 800 m clustering is close to our 750 m / ±1 day event rule.

### B5. Chandel, Sarwat, Najah, Dhanagare & Agarwala 2022, *Front. For. Glob. Change* 5:933807, "Evaluating methods to map burned area at 30-meter resolution in forests and agricultural areas of Central India". https://doi.org/10.3389/ffgc.2022.933807. **FULL** (about 85% of the page text, covering all methods and results)

**Data.** Landsat 5, nine scenes 1993–2011, Central India dry deciduous forest and cropland. 700 labelled points per scene in 13 classes, including burnt forest, burnt agriculture and active fire.

**Findings.**
- **No spectral index (NDVI, NBR, NDMI, NDWI, GEMI, BAI, BAIM, MIRBI) separated burnt forest from burnt agriculture.** Supervised classifiers could not separate them either.
- Forest burnt area: user's accuracy, RF 0.85 (Mar) and 0.75 (Apr); SVM 0.92 and 0.80. Agricultural burnt area: only 0.60–0.68. **FIRMS points: 0.07–0.20.**
- In the pooled RF, solar azimuth, solar elevation and month carried 21.9%, 18.9% and 12.1% of importance. Accuracy is higher in April–May than in February–March.

**Concrete action for us (threads 2, 3):**
- (i) Do **not** try to separate crop from forest burns spectrally. Separate them by **land cover** (WorldCover cropland mask, which our scar detector already applies) and **timing** (C1: crop fires peak after 15 April).
- (ii) Their finding that early-season (Feb–Mar) burnt area is mapped less accurately supports our observation that February scars are the weakest labels (C4: February recall 22%).

### B6. Vadrevu, Lasko, Giglio, Schroeder, Biswas & Justice 2019, *Sci. Rep.* 9:7422, "Trends in vegetation fires in South and Southeast Asian countries". https://doi.org/10.1038/s41598-019-43940-x (PMC6520341). **FULL**

- **India counts.** MODIS averaged 73,836 fires/yr (2003–16) and VIIRS 551,649/yr (2012–16): ×7.47.
- **Cropland share.** **47.92% of India's fires were in cropland** (ESA-CCI 300 m). This is a land-cover overlay only, with no timing or day/night separation.
- **Trends.** Fire counts are rising (Mann-Kendall p = 0.004), cropland fires especially (p = 0.006). FRP is also rising (p = 0.039).
- **Recurrence.** 17.8% of MODIS grid cells burn every year.
- **Climate.** Precipitation explains about 30% of monthly variation.

**Concrete action for us:** for national products such as FSI and FIRMS, about half the points in India are crop fires. Any national-scale training data we borrow, for example for thread 5 alert triage, must be filtered by a forest mask. Inside Ratapani the crop share is small (C1).

### B7. Morton et al. 2008, *Global Change Biology* 14:2262, "Agricultural intensification increases deforestation fire activity in Amazonia". **ABSTRACT ONLY**

- **Fire persistence:** high-confidence MODIS fires at the same 1 km location on **≥2 days per year** mark deforestation fires, where debris piles are burnt repeatedly. In Amazonia 2003–07 these were >40% of detections. Mechanised cropland clearing showed 4.6 fire-days per deforested area, against 1.7 for cattle-ranching clearing.
- **Concrete action:** our analogue is per-cell **VIIRS fire-days per season**. Multi-day persistence in one cell marks a slow spreading litter fire or a re-lit area, not a one-off managed burn. 11.4% of our events are multi-day (C1). Use `vdays` as a scar attribute (thread 2). It is not a 2-day model feature, because it is only known after the fact.

### B8. Space–time scan statistics and emerging hot spots. **ABSTRACT ONLY** (all paywalled or conference abstracts)

- **Tonini, Tuia & Ratle 2009**, IJWF 18:830–836, https://doi.org/10.1071/WF07167. SaTScan space–time permutation scan on MODIS active fires, Florida 2003–06. Three of the five most likely clusters were in northern forests, more frequent in spring and summer. Two were in southern agriculture and Everglades prairie, present all year.
- **Orozco, Tonini, Conedera & Kanevski 2012**, *GeoInformatica* 16 (Ticino 1969–2008). Anthropogenic fires cluster in the populated south, with "local hot spots arising from extemporaneous arson activities". Lightning fires form two northern mountain clusters.
- **Similipal (Odisha)**, EGU21-890: Getis-Ord Gi* plus Mann-Kendall. 186 km² is a persistent fire-hazard hotspot, with the core increasing and the buffer decreasing. This is an AHP hazard index, not raw detections.
- **Myanmar Landsat EHSA:** persistent hotspots cover the largest area, followed by oscillating ones.

**Concrete action:** we ran the equivalent on our data (C5). Gi* smoothing and EHSA classes do not beat the plain burn-frequency prior. A SaTScan run is only worth doing to find **short-lived arson-like clusters**, meaning several ignitions within ~2 km over a few days. The Hawkes kernels tested by the research thread already cover that (±0.4 points, per `research_thread_notes.md`).

### B9. FRY database (Laurent et al. 2018, *Sci. Data* 5:180132) and Global Fire Atlas (Andela et al. 2019, *ESSD* 11:529). **ABSTRACT ONLY**

Both give per-patch shape traits from MODIS burned area at 500 m: ellipse axes, elongation, complexity indices. The Fire Atlas notes that agricultural and human-dominated landscapes have many small fires, while arid and boreal regions are dominated by a few large ones. Neither has a cause label. At 500 m they cannot resolve our 2–25 ha scars. **Use only the method:** our patch elongation in C3 is computed the same way, from the PCA axis ratio.

### B10. VIIRS 375 m `type` attribute. (From the FIRMS attribute definitions; the FAQ page returned 403, so this is from memory of the documentation.)

The values are 0 = presumed vegetation fire, 1 = active volcano, 2 = other static land source, 3 = offshore/water. In our parquet, 8,114 points are type 0 and 3 are type 3: two at ~78.05°E 23.04°N (2017-03-27, 2021-04-16) and one at 77.41°E 22.86°N (2021-03-10, in a 26%-cropland cell). **Concrete action:** drop type ≠ 0 from every label and feature build. It costs nothing but has almost no effect.

### B11. Central-India crop burning context (news, not peer-reviewed). **PARTIAL** (article text)

- **2025:** CREAMS/IARI satellite monitoring recorded **25,144 stubble-burning incidents in MP from 1 to 23 April 2025**, the highest in India. Vidisha, a district neighbouring Raisen, had 3,037 incidents, with 545 on 23 April alone. The MP daily peak was 2,669 on 23 April.
  - Outlook Business/PTI: https://www.outlookbusiness.com/economy-and-policy/mp-records-highest-number-of-stubble-burning-incidents-in-first-3-weeks-of-april
  - Drishti IAS, 22 Apr 2025: https://www.drishtiias.com/state-pcs-current-affairs/stubble-burning-crisis-in-madhya-pradesh
- **2023:** Mongabay reports 20,998 incidents in MP between January and May 2023, 16,101 of them in April. https://india.mongabay.com/2023/06/madhya-pradesh-ranks-second-in-india-in-stubble-burning-farmers-unaware-of-government-schemes/
- **Driver:** summer moong sown straight after the wheat harvest in Narmadapuram, **Raisen**, Vidisha, Dewas, Harda and **Sehore**. Ratapani lies in Raisen and Sehore.
- **Concrete action (threads 1, 5):**
  - (i) Crop-edge cells face a second, late-April ignition pressure: wheat-residue fires escaping into the forest.
  - (ii) A `wheat_harvest_window` flag (≈10 Apr–5 May) interacting with `dist_crop_cell` is the one cause-motivated feature with a clear mechanism. Section D tests it indirectly through the split model.
  - (iii) CREAMS district-day counts (https://creams.iari.res.in) could be a daily covariate: "crop fires are being lit around Raisen today".

---

## C. What our data shows (computed this session)

Inputs: `ratapani/viirs_snpp_2013_2024.parquet` (8,117 points), `ee/worldcover.csv`, `ee/proximity.csv`, the 20 m scar rasters `research/ratapani-burn-labels/rasters/burn_<Y>.tif` (2017–2026), `burn_windows.csv`, and `scoring/pipeline_lean_pred_loso_2017_24.parquet`. Scripts are in the scratchpad (`cause_an/a1_viirs.py` … `a5_hotspots.py`). Rules: IST = UTC + 5:30. An "event" is points within 750 m on the same or adjacent day (union-find).

### C1. VIIRS by location class and by month

| Group | Points | Median FRP (MW) | p90 FRP | Night share | Share after 15 Apr | Share in Jan–Feb |
|---|---|---|---|---|---|---|
| Cells ≥20% cropland | 207 | 4.73 | 16.3 | 0.31 | **0.34** | 0.09 |
| Forest ≤1 km from crop | 1,528 | 4.57 | 12.0 | 0.23 | 0.11 | 0.16 |
| Forest interior | 6,382 | 4.03 | 10.9 | 0.30 | 0.09 | 0.20 |

- Day overpass times are 12:45–14:15 IST (5–95%, median 13:30). Night passes are 01:14–02:41 (median 01:58).
- Events: 3,617 in all. The median event is 1 point. 11.4% are multi-day and 32.1% have a night detection.

| Month | Events | With night detection | Multi-day | Median max FRP (MW) | Share of scar patches that are linear |
|---|---|---|---|---|---|
| Nov | 41 | 2% | 0% | 4.3 | – |
| Dec | 98 | 7% | 1% | 3.4 | 0% (7 patches) |
| Jan | 200 | 10% | 6% | 4.1 | **9.7%** |
| Feb | 614 | 21% | 8% | 4.1 | 4.8% |
| Mar | 1,522 | 37% | 15% | 5.1 | 3.2% |
| Apr | 980 | 39% | 11% | 5.1 | 3.5% |
| May | 148 | 39% | 11% | 5.8 | 3.6% |

- The managed rule from round 2 (`fire_management_practice.md` D2: Nov–Feb, no night, one day, max FRP ≤ the all-point median 4.2 MW) flags **379 of the 953 Nov–Feb events (40%)**.
- Elongated VIIRS events (≥3 points, axis ratio ≥3) number 279: 9 in Jan, 40 in Feb, 143 in Mar and 69 in Apr. They are mostly March runs along slopes, not winter lines [inference].

### C2. Weekly cycle test

Daily counts Jan–Jun, 2013–2024. The null shuffles daily counts within each calendar week (keeping seasonality), 1,000 times. The statistic is the weekday max−min range.

| Subset | Counts Mon…Sun | p |
|---|---|---|
| All | 1083, 1115, 1174, 1144, 1237, 988, 1169 | 0.49 |
| Crop ≥20% cells | 33, 33, 28, 26, 30, 21, 24 | 0.80 |
| Forest ≤1 km of crop | 205, 199, 229, 218, 248, 170, 229 | 0.26 |
| Interior | 845, 883, 917, 900, 959, 797, 916 | 0.78 |
| Jan–Feb only | 238, 260, 162, 246, 240, 191, 215 | 0.60 |

**No weekly cycle.** Saturday is lowest in most subsets, but nowhere near significance.

### C3. Scar patch geometry (20 m rasters, 2017–2026; a patch = 8-connected pixels with the same window-end date, ≥5 px)

- **Size.** 12,293 patches. Quartiles 3.0 / 5.0 / 10.6 ha, p90 23.7 ha, p99 99.7 ha.
- **Elongation** (PCA axis ratio): median 2.0, p90 3.55, p99 6.1.
- **Linear patches** (elongation ≥4, mean width ≤80 m, length ≥300 m): 481 patches, **3.9% of patches and 1.3% of burned area**. Median 3.2 ha, width 59 m, length 577 m. By month: January 9.7%, Feb–May 3–5%.
- [inference] Real fire lines are 6–12 m wide, so most are below the 2-ha, 20 m detector limit. The 59 m-wide "linear" patches are more likely line-plus-adjacent burns or burns along nalas. The fire-line detector proposed in `fire_management_practice.md` D1 (10 m bands, Nov–Feb composites) is still needed for the lines themselves.
- **NBR drop** (×1000, patch median): January 232, against 157–172 for Feb–May. January scars are deeper, possibly because January's detection threshold is higher (0.18 vs 0.12).
- **First-burn cell-seasons 2017–2024** (15,754 in all):
  - VIIRS-matched within 750 m and the window ±1 day: 53% of positive cell-days.
  - Night detection: 18.5%.
  - `managed_proxy` (window ends ≤20 Feb, VIIRS day-only, ≤1 VIIRS day): 850 cell-seasons.
  - Linear dominant patch: 462.
  - Crop-edge cell (≥20% crop or ≤500 m from a crop cell): 2,335.
  - Late (window end ≥15 Apr): 2,073.
  - "Spread" (a neighbour within 1 km finished burning ≤7 days before this window started): 5,931.

### C4. Recall@5 of the lean LOSO model by stratum (2017–2024, 111,022 positive cell-days; overall 28.55%)

| Stratum | Share of positives | Recall@5 |
|---|---|---|
| VIIRS-matched / not | 53% / 47% | 30.5% / 26.3% |
| Night detection / not | 18.5% / 81.5% | **34.4%** / 27.2% |
| managed_proxy / not | 4.8% / 95.2% | **23.0%** / 28.8% |
| Linear patch / not | 2.5% / 97.5% | 23.0% / 28.7% |
| Crop-edge / interior | 14.5% / 85.5% | **23.4%** / 29.4% |
| Window end ≥15 Apr / earlier | 16.7% / 83.3% | 37.3% / 26.8% |
| Spread / isolated | 40% / 60% | **33.8%** / 25.0% |
| Feb / Mar / Apr / May | 24 / 42 / 29 / 5% | 22.3 / 27.4 / 32.9 / 42.7% |
| Scar ≤2 / 2–5 / 5–10 / 10–25 ha | 31 / 34 / 21 / 14% | 19.8 / 25.9 / 33.5 / **46.4%** |
| Other seasons burned: 0 / 1 / 2–3 / ≥4 of 7 | 1.3 / 2.9 / 22 / 74% | **1.4** / 7.1 / 19.7 / 32.5% |
| Village distance ≤1 / 1–2 / 2–4 / >4 km | 3.5 / 14 / 35 / 47% | 24.1 / 25.9 / 30.0 / 28.6% |

Reading [inference]:
- **The model is a "repeat-and-spread" detector.** It does well on cells that burn most years, on large and spreading fires, and on night-active fires. It does badly on small, early, managed-looking and crop-edge burns.
- Removing managed-proxy positives from the *scoring* labels alone would raise headline recall by only 0.3 points (from 28.55 to ~28.8). They are too few to matter.
- The crop-edge gap (23.4 vs 29.4) is the largest of the cause-type gaps.

### C5. Hot-spot analyses

- **EHSA-style classes** (Getis-Ord Gi* per season on the burned indicator, 1 km window, 10 seasons, Mann-Kendall on z): sporadic 1,966 cells, none 1,458, oscillating/historical 98, new 90, emerging 2, and *no persistent class*. With ~40% of cells burning in a typical year, the indicator saturates.
- **Held-out ranking of burned cells within pseudo-beats** (season level, leave-one-season-out over 10 seasons), top-5 / top-10 / top-20 cells per beat:

| Ranking score | Top-5 | Top-10 | Top-20 |
|---|---|---|---|
| Own-cell frequency | 12.5% | 24.2% | 45.9% |
| Neighbourhood (Gi*-style) frequency | 12.2% | 23.9% | 45.5% |
| Own + 0.5 × neighbourhood | 12.7% | 24.3% | 46.3% |

  **No gain.**
- **Persistent ignition sources** (cell of the first point of each VIIRS event, 12 seasons), against a null with the same yearly counts scattered at random:

| Event starts in ≥ k seasons | Cells observed | Expected at random |
|---|---|---|
| ≥3 | 334 | 237 |
| ≥4 | 75 | 42.5 |
| ≥5 | 12 | 5.6 |
| ≥6 | 1 | 0.5 |

  The excess is real (≈1.8×) but small in absolute terms. The 12 top cells hold 1.7% of all event starts. They are slightly farther from roads (median 3.9 km vs 3.4 km) and slightly closer to villages (3.5 km vs 3.8 km). [inference] These 75–12 cells are worth showing to beat guards ("why does this spot light up most years?"). That is a thread 5 action, not a model feature.

### C6. Weather on managed-proxy days (test of the Pourmohamad 2025 "debris burns on low-danger days" idea)

Inputs: `weather_power_daily.parquet` (sanctuary-wide), with each variable expressed as the anomaly from its 31-day centred rolling median.

| Comparison | n | Median RH anomaly | Mann-Whitney p (RH) | p (temperature) | p (wind) |
|---|---|---|---|---|---|
| Nov–Feb managed-proxy vs other events | 379 vs 574 | −2.5 vs −2.75 points | 0.085 | 0.96 | 0.79 |
| February only | 219 vs 395 | – | 0.38 | – | – |

Both groups burn on slightly drier-than-normal days. Weather does **not** separate them. This is consistent with "weather sets when, not where": managed and unmanaged burns respond to the same dry spells [inference]. In March–April, events with a night detection fall on drier days than day-only events (RH anomaly −2.9 vs −1.6).

---

## D. Retraining tests: does separating causes help the 2-day model?

Setup:
- The lean pipeline (`scoring/pipeline_lean_model.py`), copied to the scratchpad with the same features, LightGBM settings and LOSO 2017–2024.
- Static inputs were rebuilt from `ee/` and `cells_static.csv`, because `static_features.parquet` and `roads_features.parquet` are not on the shared mount. The baseline here is therefore my own re-run, and variants are compared against it.
- Variants:
  1. `drop_mgd`: positive training cell-days whose first burn is `managed_proxy` or linear are removed from training. Test labels are unchanged.
  2. `timing`: adds per-cell priors from other seasons. `tp_doy` is the median first-burn day of year, `tp_early` the share of burns ending ≤28 Feb, `tp_night` the share with a VIIRS night detection, and `tp_gap` = today's day of year − `tp_doy`.
  3. `split_ce`: separate models for crop-edge cells and the rest.
  4. `timing_drop_mgd`: variants 1 and 2 together.

**Results.** Recall@5 is the share of positive cell-days caught at 5 picks per pseudo-beat per day, pooled over 2017–2024 (111,022 positive cell-days).

| Variant | All | Non-managed positives | Managed-proxy positives | Crop-edge cells | Interior | Seasons better than base |
|---|---|---|---|---|---|---|
| base (seed 0) | **28.70%** | 29.13 | 23.11 | 23.19 | 29.63 | – |
| base, second seed (control) | 28.45 | 28.87 | 23.11 | 23.14 | 29.35 | – |
| drop_mgd | 28.60 | 29.00 | 23.49 | 23.07 | 29.54 | 2/8 |
| timing | 28.79 | 29.19 | 23.60 | 23.04 | 29.76 | 5/8 |
| split_ce | 28.49 | 28.86 | 23.79 | **27.61** | 28.64 | 4/8 |
| timing_drop_mgd | 28.55 | 28.92 | 23.84 | 23.35 | 29.43 | 4/8 |

Rank blends (sum of within-day percentile ranks):

| Blend | All | Crop-edge | Interior | Seasons > base |
|---|---|---|---|---|
| base + base seed 2 (pure ensembling control) | 28.91 | 23.43 | 29.84 | – |
| base + split_ce | 29.07 | **25.22** | 29.72 | 8/8 |
| base seed 2 + split_ce | 28.98 | 24.96 | 29.66 | – |
| base + timing | **29.23** | 23.22 | 30.24 | 8/8 |
| base + base seed 2 + split_ce | 29.18 | 24.40 | 29.99 | – |

**Reading.**
- **Seed noise is about ±0.25 points.** The two base seeds differ by 0.25. Single-variant differences of ≤0.3 are noise.
- **Dropping managed-proxy positives from training does not help** (−0.1). Those labels are only 4.8% of positives, and the model already treats them as low-score. Keep them as positives, with a flag (action 2).
- **A separate crop-edge model is the one cause split with a clear effect.** On its own it raises crop-edge recall from 23.2% to 27.6% (+4.4 points), but costs the interior 1 point, so the net is −0.2. Rank-blended with the base, crop-edge recall rises to 25.2% (+2.0) at an interior cost of only ~0.1 points. Overall it is +0.16 above the pure seed-ensemble control and +0.5 above the seed-mean base.
  - [inference] The gain comes from allotting more picks to crop-edge cells late in the season, not from reordering within them (a quantile-mapped hybrid that kept the base's crop-edge share gave 28.55%).
- **Per-cell timing priors** (`tp_doy`, `tp_early`, `tp_night`, `tp_gap`): +0.1 alone, +0.3 above the ensembling control when blended. A small real gain at best.
- **Expected gain from cause separation in the 2-day model: +0.2 to +0.5 points overall, and +2 points on crop-edge cells.** That is far below the gains from better dating, spread terms or budget rules discussed in other notes. The best practical form is to keep one model, add a crop-edge sub-model, and rank-blend the two. Re-test it on 2025–26 before adopting it.

Files (scratchpad): `cause_an/a4_exp.py`, `exp_results.json`, `exp_preds.parquet`, `a4_seed2.py`, `exp_preds_seed2.parquet`.

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access / use |
|---|---|---|---|---|---|
| FIRMS VIIRS 375 m (S-NPP, NOAA-20, NOAA-21) with `type`, `daynight`, FRP | https://firms.modaps.eosdis.nasa.gov/ | 375 m, 2 passes/day/sat | 2012– | NASA open | Already used; drop `type ≠ 0`; add NOAA-20/21 for more night passes (see `fire_detection_sources.md`) |
| GK2A-AMI L1B/L2 (geostationary, covers India) | https://nmsc.kma.go.kr/enhome/html/main/main.do | 2 km IR, 10 min | 2019– | KMA, free registration | Hourly ΔTb(3.8–11.2) as in Jethva 2026; detects only larger fires; test on known big Ratapani fires to see if afternoon timing is recoverable |
| CREAMS (IARI) stubble-burning daily counts by district | https://creams.iari.res.in/ | district-day | ~2020– | Govt. portal, public dashboard | Daily crop-fire pressure covariate for Raisen and Sehore in April |
| FPA FOD 6th ed. + FPA FOD-Attributes | https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.6 ; https://doi.org/10.5194/essd-16-3045-2024 | point records | 1992–2020 | Public domain (USDA) | Method template only; 300+ attributes; cause labels |
| EGIF (Spain fire statistics) | https://servicio.mapa.gob.es/incendios/Search/Publico | record; 10 km grid before 2012 | 1968–2023 | Public | Template only |
| Prométhée (Mediterranean France) | https://www.promethee.com/ | 2 × 2 km | 1973– | Public | Template; 5/15/31 cause levels |
| Bountzouklis 2023 data | https://doi.org/10.6084/m9.figshare.22028015.v1 | 2 km cells | 1997–2020 | CC BY | Example feature table and code layout |
| ESA WorldCover 10 m | https://esa-worldcover.org | 10 m | 2020, 2021 | CC BY 4.0 | Interface areas (forest–crop within 250 m), already in `ee/worldcover.csv` at cell level |
| FRY fire-patch traits | https://doi.org/10.1038/sdata.2018.132 | 250–500 m patches | 2005–2011 | CC BY | Shape-metric definitions only |
| Global Fire Atlas | https://doi.org/10.5194/essd-11-529-2019 | 500 m | 2003–2016 | open (ORNL DAAC) | Not useful at our scale |
| Our derived tables (this session, scratchpad) | `cause_an/patches.parquet`, `patch_cells.parquet`, `pos_attrs.parquet`, `events.parquet`, `ehsa_cells.csv` | 20 m patches / 500 m cells | 2013–2026 | internal | Copy to `ratapani/` if wanted |

---

## Ranked action list (gain for the 2-day model is my estimate [inference] unless measured in D)

| # | Action | Thread | Gain | Effort |
|---|---|---|---|---|
| 1 | **Field cause log.** On each verified alert, record the cause class (mahua/tendu clearing, grazing flush, crop escape, department burn, unknown) and the ignition time-of-day class (before 12, 12–15, after 15). This is the only way to get cause labels; every published classifier needed them. | 5 | Enables everything below; no model gain until ~1–2 seasons | Low (form fields) |
| 2 | **Flag, don't drop.** Keep `managed_proxy`, `linear`, `cropedge`, `vdays`, `night` as columns on every scar label. Report recall with and without managed-proxy positives (difference ~0.3 points). | 2 → 1 | ~0 (bookkeeping); prevents mis-reading | Very low (code in `a3_strata.py`) |
| 3 | **Crop-edge sub-model, rank-blended with the main model** (measured in D: 29.07% vs 28.70% LOSO, 8/8 seasons; crop-edge recall 23.2% → 25.2%). Then add CREAMS Raisen/Sehore daily stubble-fire counts and a `wheat_harvest_window` (≈10 Apr–5 May) flag to that sub-model. Re-test on 2025–26. | 1 | +0.2–0.5 overall (measured), +2 points crop-edge; CREAMS untested | Low (sub-model); medium (CREAMS scrape) |
| 3b | Blend in the per-cell timing-prior model (`tp_doy`, `tp_early`, `tp_night`, `tp_gap`): base + timing gives 29.23%, 8/8 seasons, but about half of that is plain ensembling (two seeds give 28.91%). | 1 | +0.3 beyond ensembling | Low |
| 4 | Drop VIIRS `type ≠ 0` (3 points). | 1, 2 | 0 | Trivial |
| 5 | ~~Add an RH condition to the managed rule~~. **Tested and rejected (C6):** sanctuary-wide weather does not separate managed-proxy events from other Nov–Feb events. Revisit only with per-cell weather or field labels. | 2 | 0 | done |
| 6 | Show the 12–75 repeat-ignition cells (C5) to beat guards and ask what happens there. | 5 | Prevention value; not a model feature | Low |
| 7 | GK2A hourly test on 5–10 large Ratapani fires to see whether ignition hours are recoverable. If they are, ignition time becomes a label attribute. | 2, 5 | Unknown; mostly for alert lag | Medium-high |
| 8 | Do NOT pursue: day-of-week features (C2), EHSA/Gi* hot-spot features (C5), dropping managed burns from training labels (D), spectral crop-vs-forest separation (B5), or a cause classifier trained without field labels (A1–A4). | – | 0 | – |

---

## Reading status

| Status | Count | Sources |
|---|---|---|
| FULL | 8 | Ochoa 2026; Bountzouklis 2023; Pourmohamad 2025; Jethva 2026; Earl & Simmonds 2018; Pereira 2019; Chandel 2022 (≈85%); Vadrevu 2019 |
| PARTIAL | 2 | Li 2023 (no supplement); MP stubble-burning news (CREAMS figures) |
| ABSTRACT ONLY | 10 | Rodrigues & de la Riva 2014; Syphard & Keeley 2015; ArcGIS FPA FOD notebook; BIO Web Conf 2026; Morton 2008; Tonini 2009; Orozco 2012; Similipal EGU21-890; FRY 2018; Global Fire Atlas 2019 |

Own analyses this session: C1–C6 and D (5 LOSO variants plus a seed control, about 50 LightGBM fits).
