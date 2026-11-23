# Literature review: how good can next-1–2-day cell-level fire prediction be? (Ratapani WLS context)

Compiled 2026-10-15. Honesty conventions:
- **Read: full text (pdftotext)**: I downloaded the PDF and read the relevant sections and tables myself. Numbers are quoted from the tables.
- **Read: full text (web summary)**: the publisher HTML full text was read through a fetch tool that summarises pages. Numbers were relayed by that tool and were not re-checked against a PDF. Tables shown only as images were not visible.
- **Abstract/snippet only**: only the abstract or a search snippet was seen. Treat these numbers as weaker evidence.
- "Derived" marks arithmetic I did myself from a paper's published numbers. Those figures are not stated in the paper.

Project baseline being judged:
- Within-beat (~38 cells) top-5 per day (≈13% of cells) catches 29–31% of burned cell-days. Random catches ~17%, so lift ≈1.8x. A perfect ranker under the 5-per-beat cap would catch ~64%.
- Within-day AUC is ~0.7–0.8.
- Weather decides *when*, not *where*. Letting the daily budget follow forecast big-fire days raises the catch from 29% to 63%.
- The VIIRS 87-division model reports ~85% of fires "in or next to" the top 10% of squares (~20% of ground), and ~56% for brand-new fires.

---

## A. Next-day fire prediction benchmarks (persistence vs new ignition)

### 1. Huot et al. 2022, "Next Day Wildfire Spread: A Machine Learning Dataset to Predict Wildfire Spreading From Remote-Sensing Data"
- **Citation:** Huot F., Hu R.L., Goyal N., Sankar T., Ihme M., Chen Y.-F. IEEE Trans. Geosci. Remote Sens. 60 (2022). arXiv:2112.02447. https://arxiv.org/abs/2112.02447
- **Read:** full text (pdftotext).
- **Task:** next-day MODIS MOD14A1 fire mask at 1 km, contiguous US, 2012–2020. Only samples that already have fire at time t were kept ("we only keep samples for which ... the 'previous fire mask' contains any fire at all"). This is a **spread/persistence** task, not ignition.
- **Metrics (test set), AUC-PR / precision / recall:**

  | Model | AUC-PR | Precision | Recall |
  |---|---|---|---|
  | Neural net | 28.4 | 33.6 | 43.1 |
  | Random forest | 22.5 | 26.3 | 46.9 |
  | Logistic regression | 19.8 | 32.5 | 35.3 |
  | Persistence | 11.5 | 35.7 | 27.3 |

- **Persistence dominates the model:**
  - Removing the previous fire mask drops AUC-PR from 28.4 to 6.8 (recall 0.2%).
  - A model using only the previous fire mask gets AUC-PR 22.9, precision 29.2, recall 49.6.
  - Every single-feature model except the fire mask had recall of zero.
  - In the random forest, the top 9 Gini features are all neighbouring previous-fire-mask pixels.
- **Coarsening the target inflates scores:**
  - Predicting "any fire in a 2x/4x/8x block" (binary) raised AUC-PR to 39.8, 53.5 and 66.3.
  - Persistence rose to 19.5, 30.6 and 41.3 at the same coarsening.
- **New ignitions separated?** No. They are excluded by design.
- **Lesson:** Most published next-day skill is "fire continues where it is burning." Counting "in or adjacent" cells is equivalent to coarsening the grid by ~3x, and that alone can more than double AUC-PR. Both the 85% figure and the 56% new-fire figure from the VIIRS model must be judged against the same adjacency rule applied to random selection and to persistence.

### 2. Bai et al. 2026, "Set Prediction for Next-Day Active Fire Forecasting" (WISP)
- **Citation:** Bai Y., Athanasiou G., Yu X., Antonopoulos D., Papoutsis I., Hantson S., Carvalhais N. arXiv:2605.10298 (preprint). https://arxiv.org/abs/2605.10298
- **Read:** full text (pdftotext), sections 3–4 and Tables 1–3.
- **Task:** predict a ranked set of next-day VIIRS fire-cluster centres on a 375 m grid. Inputs are 48 h of covariates including fire history. Test regions are 3°x3° cubes across 14 GFED regions.
- **Overall metrics:** AP@14 px (~5 km tolerance) is 21–38%. Union AUROC is 64.6–76.4.
- **Regime split (Table 3).** Hit@14 means a predicted point lands within ~5 km of a true cluster.
  - **New ignition** (no past fire, n=138): Hit@14 12.8–19.1%, AP@14 5.9–12.5%.
  - **Continued fire** (n=386): Hit@14 50.4–66.7%, AP@14 23.7–43.8%.
  - Authors' wording: "Historical fire is a strong predictive cue ... New ignition remains the hardest regime."
  - Recent fire also produces false "persistence" alarms after a fire goes out. For WISPv3, 2.97 predicted queries remain on average in the extinguished regime.
- **New ignitions separated?** Yes, explicitly.
- **Lesson:** Even at a 5 km tolerance, a state-of-the-art model finds only ~13–19% of genuinely new fire clusters, against ~50–67% for continuing fires. Reporting new-fire skill separately is correct and rare. The project's 56% for "brand-new" fires (in or next to the top 10%) is far above this, which suggests either a generous footprint or a generous "new" definition. Check it (see synthesis).

### 3. Karlsson et al. 2025, "Comparing Next-Day Wildfire Predictability of MODIS and VIIRS Satellite Data"
- **Citation:** Karlsson J., Xu Y., Berg A., Haglund L. arXiv:2503.08580 (v4, 2025). https://arxiv.org/abs/2503.08580
- **Read:** full text (pdftotext).
- **Task:** next-day fire mask, Australia. Only cells with fire on the current day were used (spread, not ignition).
- **Persistence baseline (tomorrow = today):**
  - MOD14: F1 6.56%, IoU 3.39%.
  - VNP14: F1 19.62%, IoU 10.87%.
- **U-Net models:**
  - MODIS input → MOD14 target: F1 11.96%.
  - VIIRS input → VNP14 target: F1 28.57%.
  - MODIS input → VNP14 target: F1 27.16%.
  - Training on VNP14 predicted MOD14 better (IoU 8.17%) than training on MOD14 itself (6.37%).
- **Lesson:**
  - Label quality sets the ceiling. MOD14 is "highly stochastic"; VIIRS 375 m labels are much more learnable.
  - Even for fires already burning, next-day F1 is <30% at ~1 km.
  - For the project, the VIIRS labels are the right choice for the 87-division model. The S2/Landsat scar labels with a 2–5-day date window add their own label noise, which caps achievable skill.

### 4. Prapas et al. 2021, "Deep Learning Methods for Daily Wildfire Danger Forecasting"
- **Citation:** Prapas I., Kondylatos S., Papoutsis I., Camps-Valls G., Ronco M., Fernández-Torres M.-Á., Piles Guillem M., Carvalhais N. NeurIPS 2021 workshop (Tackling Climate Change with ML). arXiv:2111.02736. https://arxiv.org/abs/2111.02736
- **Read:** full text (pdftotext).
- **Task:** Greece, 1 km daily. The target is a pixel inside an EFFIS burned area (>30 ha) whose fire started next day.
- **Negatives are easy:**
  - Two negatives per positive, "extracted from days when no fire occurred", stratified by land cover.
  - Test set (2020): 311 fire / 975 non-fire.
- **Results (test AUROC):** RF 0.898; LSTM 0.920; CNN 0.910; ConvLSTM 0.926.
- **New ignitions:** The paper notes that Huot-style fire-mask targets risk "data leakage, predicting fires that are already burning." It uses fire start dates instead.
- **Lesson:** AUROC ~0.9 here is measured against negatives taken from fire-free days. It mixes *when* (fire day vs no-fire day) with *where*, so it is not comparable to a within-day, within-beat ranking AUC of 0.7–0.8.

### 5. Kondylatos et al. 2023, "Mesogeos: A multi-purpose dataset for data-driven wildfire modeling in the Mediterranean"
- **Citation:** Kondylatos S., Prapas I., Camps-Valls G., Papoutsis I. NeurIPS 2023 Datasets & Benchmarks. arXiv:2306.05144. https://arxiv.org/abs/2306.05144
- **Read:** full text (pdftotext).
- **Task:** next-day "fire danger" at 1 km/daily, Mediterranean, 2006–2022.
  - Positives are ignition points of fires that started on day t. The ignition date is refined by intersecting EFFIS burned areas with the earliest MODIS hotspot within a 7-day buffer.
  - Negatives are sampled **outside a 62 km buffer of any fire that started that day**, at 2:1, stratified by land cover. Test set: 1369 positives / 2738 negatives.
- **Results (Table 1):** LSTM AUPRC 0.853; Transformer 0.856; GTN 0.858.
- **Lesson:**
  - With ~33% prevalence and negatives far from the day's fires, AUPRC ~0.85 is easy to reach. It says nothing about local (within-beat) discrimination.
  - The authors flag ignition-date misalignment ("some misalignments in the ignition dates may persist") as a limitation. This is the same issue as the project's 2–5-day S2 dating window.
- **Related paper not read:** Kondylatos et al. 2022, "Wildfire danger prediction and understanding with deep learning", GRL 49, e2022GL099368, https://doi.org/10.1029/2022GL099368. **Abstract only.** The full text was blocked from this environment. Same group and same negative-sampling style. The abstract claims the models beat FWI, with soil moisture and relative humidity as the top drivers.

### 6. Girtsou et al. 2021, "A Machine Learning Methodology for Next Day Wildfire Prediction"
- **Citation:** Girtsou S., Apostolakis A., Giannopoulos G., Kontoes C. IGARSS 2021, pp. 8487–8490. DOI 10.1109/IGARSS47720.2021.9554301. PDF: https://publications.beyond-eocenter.eu/DISASTERS/A_Machine_Learning_Methodology_for_Next_Day_Wildfire_Prediction.pdf
- **Read:** full text (pdftotext; 4 pages).
- **Task:** Greece, **500 m cells**, next day, 2010–2019. The hold-out test set keeps the real prevalence of **~1:100,000** fire/no-fire (386 fire cells).
- **Results:** Table 1 gives recall for no-fire (R0) and fire (R1) on the real-prevalence test set:
  - NN tuned on AUC: R0 0.42, R1 0.87.
  - RF tuned on AUC: R0 0.36, R1 0.92.
  - RF tuned on HMRb: R0 0.23, R1 0.96.
  - XGBoost tuned on AUC: R0 0.37, R1 0.89.
  - LogitBoost: R0 0.51, R1 0.71.
- **Derived (my arithmetic):**
  - At the real prevalence, the share of cells flagged ≈ 1−R0.
  - Lift = recall / share flagged:
    - NN: 0.87/0.58 ≈ 1.5x.
    - RF (AUC-tuned): 0.92/0.64 ≈ 1.4x.
    - RF (HMRb-tuned): 0.96/0.77 ≈ 1.25x.
    - LogitBoost: 0.71/0.49 ≈ 1.45x.
  - These lifts are at large flagged fractions (~50–77% of area). Lift at a 13% budget would normally be higher, but the paper does not report it.
- **New ignitions separated?** Not reported.
- **Lesson:** This is the closest public analogue in grid size and horizon (500 m, next day, real prevalence, country scale). Its operating points give lifts of only ~1.25–1.5x. The project's 1.8x **within a beat**, where the large between-region differences are already removed, does not look weak.

### 7. Alvi, Costa Saura & Epicoco 2026, "Operational evaluation of data-driven forest fire forecasting models"
- **Citation:** arXiv:2603.25469 (v2, 2026). https://arxiv.org/abs/2603.25469
- **Read:** full text (pdftotext), sections 2–3 and Table 3.
- **Task:** Greece (Mesogeos-style datacube), 1 km daily.
  - Training negatives: ratio 2:1, drawn on dates with **no fires in the whole region**, from fire-susceptible land cover.
  - Test-set recall is ~0.87–0.90 and precision ~0.73–0.78.
- **Region-wide evaluation:**
  - "Daily recall" = share of fire pixels with p>0.5. For ConvLSTM, 40% of fire days have daily recall >0.99.
  - False alarms are judged only qualitatively, from the skew of probability histograms on no-fire days.
  - The paper does **not report what fraction of the map is above 0.5 on fire days**.
- **Lesson:**
  - The paper is right that test-set precision on curated data says nothing about operational false alarms.
  - But its own "daily recall" has no area budget, so it cannot be compared with a fixed budget of k cells. Always report hit rate at a fixed budget or fixed area fraction, as the project does.

### 8. Pádua, Levada & Valente 2026, "A Retrospective Benchmark of Spatiotemporal Covariates for Daily Active-Fire Detection in Cerrado Conservation Units"
- **Citation:** arXiv:2606.04170 (stat.AP, preprint). https://arxiv.org/abs/2606.04170
- **Read:** full text (pdftotext), methods and results sections.
- **Task:** Cerrado (Minas Gerais), daily point-dates.
  - Labels: INPE AQUA_M-T hotspots. Pseudo-absences at 1:10 for training and 1:100 for held-out protected areas.
  - Same-day covariates, so this is **not a prospective forecast** (authors' own caveat).
  - Uses environmental memory (weather/vegetation moving averages, EWMAs) but **no fire-history features**.
- **Results:**
  - Temporal cross-validation, Stage 4: AUC-PR 0.30–0.31 against a no-skill 0.091 (≈3.3x). AUC-ROC 0.786–0.792.
  - Held-out protected areas at 1:100: AUC-PR 0.049–0.10 at Stage 4 (no-skill ~0.010). AUC-ROC 0.78–0.89.
  - Results are unstable across stages; the RF peaked at Stage 3 with AUC-PR 0.262.
- **Lesson:**
  - In a tropical, human-ignition savanna, daily occurrence AUC-ROC of ~0.78–0.79 is what honest (temporally split) evaluation gives without fire-history persistence.
  - Spatial transfer to a new reserve is unstable. The project's 0.7–0.8 within-day AUC is in this range.

### 9. Pourmohamad et al. 2026, "Predictive Understanding of Wildfire Ignitions Across the Western United States"
- **Citation:** Pourmohamad Y., Abatzoglou J.T., Fleishman E., Belval E., Short K.C., Williamson M., Perlmutter M., Seydi S.T., Sadegh M. Earth's Future 14, e2025EF006935 (2026). https://doi.org/10.1029/2025EF006935
- **Read:** full text (pdftotext), methods, Table 1 and discussion.
- **Task:** daily ignition probability, western US, 2000–2020, more than 500,000 ignitions (FPA-FOD), XGBoost. Results are reported for all causes, human-caused and lightning separately. Maps are at 1 km.
- **Absence designs:**
  - "Hyper-sampled" absences come from a uniform 4 km grid.
  - "TSS-4" absences are taken on the same date as an ignition, within 4 km of it.
- **Results (Table 1):**
  - Model trained on hyper-sampled absences, human-caused ignitions: test precision 96.75%, recall 78.30%.
  - On TSS-4 absences, the same model correctly rejects only 67.15% of same-day absences within 4 km of ignitions (66.60% for all causes).
  - In the 2020 test year (COVID behaviour shift), recall for human-caused ignitions fell to 23.12% (precision 72.69%).
- **Lesson:**
  - Headline accuracy depends on easy, far-away negatives. **Local, same-day discrimination is the hard part**, and it is exactly the within-beat problem.
  - Human ignition patterns can change from year to year (2020), so check skill year by year.
- **Note:** precision of 96% in a 98.9%-absence sample is an artefact of how the sample was built, not real-world precision.

### 10. Keeping, Harrison & Prentice 2024, "Modelling the daily probability of wildfire occurrence in the contiguous United States"
- **Citation:** Environ. Res. Lett. 19, 024036. https://doi.org/10.1088/1748-9326/ad21b0
- **Read:** full text (pdftotext), abstract, methods and evaluation; not every figure.
- **Task:** daily probability at 0.1° (~10 km), all causes, generalised linear model (GLM) ensemble.
- **Results:**
  - AUC 0.85–0.88.
  - The authors found "compression" of predicted probabilities, a calibration problem that they had to correct explicitly.
- **Lesson:** AUC ~0.85+ at 10 km, pooled over the continent and the whole year, is mostly between-region and seasonal discrimination. Within a 38-cell beat on one day, those sources of variance are gone, so lower AUCs are expected.

---

## B. Human-caused fire occurrence prediction (statistical tradition), calibration and evaluation

### 11. Taylor, Woolford, Dean & Martell 2013, "Wildfire Prediction to Inform Fire Management: Statistical Science Challenges"
- **Citation:** Statistical Science 28(4): 586–615. arXiv:1312.6481. https://arxiv.org/abs/1312.6481
- **Read:** full text (pdftotext), section 2 (fire occurrence) and parts of the discussion.
- **Key points:**
  - At 1 km² x daily voxels, "fires are very rare events." Ignition locations are "inherently random."
  - The standard approach is a logistic GAM approximating a point process.
  - Case–control (response-based) sampling of non-fire voxels "induces a deterministic offset" of log(π1/π0) to the intercept. This offset is required to recover calibrated probabilities.
  - Lightning-fire models "should have greater temporal and spatial specificity" than human-caused models "because the ignition process can be observed."
  - Operational human-caused models (e.g. British Columbia, Magnussen & Taylor 2012) work at **20 km (400 km²) daily cells** and predict counts per cell.
- **Lesson:**
  - The operational community targets daily *counts per region*. Weather drives these well; exact human-ignition locations are not expected to be predictable at 1 km.
  - The project's "weather decides when, not where" finding is the textbook expectation.

### 12. Preisler, Brillinger, Burgan & Benoit 2004, "Probability based models for estimation of wildfire risk"
- **Citation:** Int. J. Wildland Fire 13: 133–142. https://doi.org/10.1071/WF02061. Free PDF: https://research.fs.usda.gov/treesearch/33048
- **Read:** full text (pdftotext).
- **Task:** Oregon federal lands, **1 km² x day voxels**, 1989–1996, logistic GAM with a spatial location smooth, fitted on a sample of non-fire voxels.
- **Results:**
  - Probabilities per voxel-day are tiny. The maximum July 1996 large-fire probability was 0.0004.
  - Validation is done by summing voxel probabilities into expected counts per district-month. They compare these with observed counts using Poisson-binomial bounds (1 of 48 cases above the 99th-percentile bound, 2.1%).
  - The location term stayed highly significant after weather covariates were included, which the authors read as missing spatially explicit drivers.
  - Standard errors were large.
- **New ignitions:** no recent-fire covariate was used; all fires were treated as occurrences.
- **Lesson:** The classic approach evaluates 1 km daily probabilities by **aggregate calibration** (expected vs observed counts per area and period), not by per-cell hits. This is a good extra check for the project's beat-day totals.

### 13. Phelps & Woolford 2021a, "Guidelines for effective evaluation and comparison of wildland fire occurrence prediction models"
- **Citation:** Int. J. Wildland Fire 30(4): 225–240. https://doi.org/10.1071/WF20134. OA at https://connectsci.au/wf/article/30/4/225/21799/
- **Read:** full text (web summary). Main text was read; tables were images and not visible.
- **Task:** human-caused fires, Lac La Biche (Alberta), ~23,000 km².
  - **10 x 10 km daily voxels**, 1996–2016. Training 1996–2011 (about 900,000 voxels, 550 with fire); test 2012–16 (291,312 voxels, 193 fires, ≈0.066% prevalence).
- **Findings:**
  - Models chosen on balanced test sets "grossly overestimated" season-long fire numbers on the real-prevalence test set.
  - Model rankings reversed between balanced and real-prevalence test sets.
  - From worst to best model, AUC-ROC changed 24% but AUC-PR changed 795%. RF vs NN: 1.5% vs 69%.
  - Swapping just two predictions changed AUC-PR noticeably.
  - Recommended:
    - test on the most recent full seasons at real prevalence;
    - prefer AUC-PR and the logarithmic score over accuracy, MAE or ROC;
    - check calibration;
    - show spatial and temporal plots;
    - report variability.
  - "Very few FOP studies have used metrics to assess calibration."
- **Lesson:**
  - The project already tests on real prevalence and a fixed budget, which is the right approach.
  - Add the log score and calibration (expected vs observed per beat-day and per day), plus confidence intervals. With only a few hundred burned cell-days, a 29% vs 31% difference is likely noise.

### 14. Phelps & Woolford 2021b, "Comparing calibrated statistical and machine learning methods for wildland fire occurrence prediction: a case study of human-caused fires in Lac La Biche, Alberta, Canada"
- **Citation:** Int. J. Wildland Fire 30(11): 850–870. https://doi.org/10.1071/WF20139
- **Read:** full text (web summary). Main text read; Table 2 (the numbers) was an image and not visible.
- **Methods:**
  - Logistic regression and GAM use an intercept offset −log(π) for undersampling.
  - Bagged trees and RF are calibrated with Platt scaling (a GAM as the scaling model, cross-validated by year).
  - The NN uses the Dal Pozzolo et al. (2015) correction.
- **Results:**
  - Null-model AUC-PR was 6.6e-4.
  - The logistic GAM ranked first on AUC-PR (the authors warn the curve has a spike from two top predictions) and had the best log score.
  - No model was significantly best on calibration metrics.
  - Conclusion: "logistic GAMs can perform just as well as machine learning models for FOP."
- **Lesson:**
  - For human-caused daily occurrence, ML has shown no consistent advantage over a well-specified GAM.
  - The usual calibration tools are: offsets for case–control sampling, Platt or GAM scaling fitted by year, and summing calibrated probabilities to expected counts.
  - Small gains from switching model class should not be expected.

### 15. Gholami et al. 2018, "Adversary models account for imperfect crime data: Forecasting and planning against real-world poachers" (patrol-allocation analogue)
- **Citation:** Gholami S., McCarthy S., Dilkina B., Plumptre A., Tambe M., Driciru M., Wanyama F., Rwetsiba A., Nsubuga M., Mabonga J., Okwir T., Ford B., Fang F. AAMAS 2018. PDF: https://www.cais.usc.edu/wp-content/uploads/2018/01/sgholami_aamas18.pdf
- **Read:** full text (pdftotext), results tables and field-test section.
- **Task:** predict human illegal activity (snares) in **1 km cells**, 3-month steps, Uganda protected areas (MFPA ~5000 km², QEPA ~2500 km²). Labels depend on ranger patrol effort, so negatives are unreliable.
- **Results:**
  - Previous state-of-the-art test AUC was 0.56–0.74.
  - The imperfect-observation-aware ensemble reached AUC 0.80–0.93.
  - QEPA precision stayed low (0.12–0.21).
  - In field tests, high-risk 3x3 km areas yielded more observations per unit of effort than low-risk areas. Example for Feb–Apr: high, 10 observations in 9 areas; low, 2 in 18.
  - Rangers had been covering areas "nearly uniformly."
- **Lesson:**
  - This is the closest "where to patrol for human-caused events" analogue.
  - Location prediction of human activity at 1 km gives AUC ~0.7 unless observation bias is modelled.
  - Concentrating patrols on the top-ranked areas gave measurably more finds per unit effort in the field.
  - The project's burn-scar labels do not depend on patrols, but VIIRS omission (canopy, cloud, small fires) is a similar detection-bias problem.

### 16. McFayden et al. 2020, "Risk assessment for wildland fire aerial detection patrol route planning in Ontario, Canada"
- **Citation:** Int. J. Wildland Fire 29(1). https://doi.org/10.1071/WF19084
- **Read:** **abstract/snippet only.**
- **Content:**
  - A daily, fine-scale, expert-calibrated risk index combining occurrence prediction (human and lightning), fire behaviour, impact and the likelihood that the public detects the fire.
  - It is used to plan detection patrol routes.
  - Looking back, past patrols tended to pass over higher-index areas.
- **Lesson:**
  - Operational agencies turn daily occurrence forecasts into **effort allocation** (how much effort today, and where).
  - They also weight by detection gap: places where others would not see the fire. The project could weight cells by "unlikely to be reported by villagers/watchers."

---

## C. Labels: burned-area and active-fire products, date uncertainty

### 17. Giglio, Boschetti, Roy, Humber & Justice 2018, "The Collection 6 MODIS burned area mapping algorithm and product"
- **Citation:** Remote Sens. Environ. 217: 72–85. PMC6136150. https://pmc.ncbi.nlm.nih.gov/articles/PMC6136150/
- **Read:** full text (web summary) of the body.
- **Date accuracy:**
  - Compared against MODIS active fires, 44% of burned cells were detected on the same day as an active fire, and 68% within 2 days.
  - A per-pixel burn-date uncertainty layer is provided.
- **Detection accuracy:**
  - Omission error 0.37, commission error 0.24 (Landsat validation; non-probability sample, "indicative only").
  - Heritage products "often fail to map small (≲100 ha) burns."
- **Lesson:**
  - Even the best-validated burned-area product dates only ~2/3 of burns within ±2 days.
  - Small fires are often missed. Surface litter fires in teak are typically small and patchy.
  - Next-1–2-day evaluation on scar labels is limited by label timing: some "misses" are dating errors.

### 18. Roteta et al. 2019, "Development of a Sentinel-2 burned area algorithm: Generation of a small fire database for sub-Saharan Africa"
- **Citation:** Remote Sens. Environ. 222: 1–17. https://doi.org/10.1016/j.rse.2018.12.011
- **Read:** **abstract/snippet only.**
- **Content:**
  - The 20 m S2 product: omission 26.5%, commission 19.3%, Dice 77%.
  - MCD64A1 C6 over the same area: omission 59.6%, Dice 53.6%.
  - The S2 product found ~80% more burned area, mostly burns smaller than 100 ha.
- **Related (snippet only, not read):** a Landsat-8 + Sentinel-2A burned-area algorithm for Southern Africa (Roy et al., RSE 2019) reported the day of burning on average **~3 days later** than MODIS, because of the lower revisit frequency.
- **Lesson:**
  - S2 and Landsat scars catch the small fires that MODIS misses, at the cost of dating uncertainty of several days.
  - The project's 2–5-day window is consistent with this.
  - Use a "within ±k days" scoring rule matched to each scar's own uncertainty window rather than a fixed day.

---

## D. Indian and other dry-tropical / human-ignition context

### 19. Niyogi et al. 2025, "Environmental and anthropogenic influences on fire patterns in tropical dry deciduous forests" (Satpura Tiger Reserve, MP)
- **Citation:** Niyogi V.S., Niyogi R., Banerjee S., Verma N., Choure K. Scientific Reports 15: 13272 (2025). https://doi.org/10.1038/s41598-025-98051-7
- **Read:** full text (pdftotext), methods and results.
- **Task:** Satpura TR core (MP, close to Ratapani), 1 km² grid (1538 cells), MODIS active fire 2002–2021, March–May season.
  - Fire counts are modelled with negative binomial (monthly) and CAR Bayesian spatial models.
  - No predictive skill metric is reported.
- **Findings:**
  - The previous month's fire counts have a significant positive effect (coef 0.0122, p=0.00015). Previous-month rainfall has a weak negative effect.
  - Hotspots cluster near settlements and cropland. Road density and distance to settlement are negatively associated with fire counts.
  - **Hotspots move between consecutive 5-year periods.**
- **Lesson:**
  - Same ecosystem and state. Fire is clustered and tied to human access, but long-term hotspots drift.
  - Burn-history features should be recency-weighted. This supports the project's finding that burn history plus seasonality form the core baseline.

### 20. Jain, Saxena, Sharma & Sonwani 2021, "Investigation of Forest Fire Activity Changes Over the Central India Domain Using Satellite Observations During 2001–2020"
- **Citation:** GeoHealth 5(12): e2021GH000528. PMC8696561. https://pmc.ncbi.nlm.nih.gov/articles/PMC8696561/
- **Read:** full text (web summary).
- **Task:** central India (17.5–21.5°N, 78.5–82.5°E: parts of Chhattisgarh, Odisha, Telangana and Maharashtra; MP is not included). MODIS active fires 2001–2020.
- **Findings:**
  - The season runs February–June. About 70% of yearly fires occur in March–April.
  - Fire counts roughly doubled between 2001–05 and 2006–20.
  - Monthly correlations with fire counts:
    - soil moisture r = −0.521;
    - evapotranspiration r = −0.558;
    - NDVI r = −0.519;
    - precipitation r = −0.364;
    - air temperature r = 0.107, not significant.
  - Cites ">95%" anthropogenic origin for Indian forest fires.
- **Lesson:** Vegetation and soil dryness track fire much more closely than temperature. This is consistent with per-cell NBR/NDVI change being the one covariate that adds skill in the project.

### 21. Mondal & Sukumar 2016, "Fires in Seasonally Dry Tropical Forest: Testing the Varying Constraints Hypothesis across a Regional Rainfall Gradient"
- **Citation:** PLoS ONE 11(7): e0159691. https://doi.org/10.1371/journal.pone.0159691 (PMC4956259)
- **Read:** full text (web summary).
- **Task:** Mudumalai (Tamil Nadu), ground-mapped burnt area 1990–2010. Quasi-binomial GLM of the annual proportion burnt.
- **Findings:**
  - Mean 20.1% of the landscape burnt per year; mean fire interval 4.9 years.
  - Previous year's burnt area has a negative effect (coef −20.73, p=0.083), interacting with wet-season rainfall. The authors interpret this as reduced fuel and fuel connectivity.
  - Drier regimes are fuel-limited; wetter ones are moisture-limited.
- **Lesson:**
  - In Indian dry deciduous forest, recent burning *depletes fuel*.
  - "Already burned this season" should *reduce* a cell's next-day probability. Exclude or down-weight cells burned within the season, and do not count them as candidates.
  - This also bears on the fuel-load-map aim: fuel accumulation since the last burn is a legitimate predictor.

### Also consulted (low relevance, short notes)

- **Eaturu & Vadrevu 2025**, Sci. Rep., "Evaluation of machine learning and deep learning algorithms for fire prediction in Southeast Asia", https://doi.org/10.1038/s41598-025-00628-9 (PMC12122932).
  - Read: full text (web summary).
  - Monthly VIIRS counts on ~9 km cells. The best model beat a seasonal-persistence baseline in every country, but several models did worse than persistence in some countries.
  - Not daily; relevant only as a reminder to always report a persistence baseline.
- **Barbosa et al. 2026**, Forests 17: 437, Cerrado–Amazon fire danger indices.
  - Read: full text (pdftotext), skimmed.
  - Weather-index skill scores (up to 0.74) are computed with a 50 km radius around stations, i.e. they measure *when* at regional scale.
- **Vieira et al. 2026**, REIC (SBC), ConvLSTM daily active fires in the Cerrado.
  - **Abstract/snippet only**; the PDF download failed.
  - Reported pixel AUC-ROC ≈0.89 at ≈0.03% positive prevalence, and the authors note "difficulty predicting rare ignitions." Split by new vs persistent fires is unknown.

---

## E. Synthesis

### E1. Is ~1.8x lift at ~13% area, and within-day AUC 0.7–0.8, in line with the literature?

**In line, arguably at the upper end for this exact task. It is not below the literature.** Reasons:

1. **The high published numbers mostly measure different, easier questions:**
   - AUROC 0.90–0.93 (Prapas 2021) and AUPRC 0.85 (Mesogeos) come from negatives on no-fire days or >62 km from any fire, at 1:2 balance.
   - AUC 0.85–0.88 (Keeping 2024) comes from pooling across a continent and a full year at 10 km.
   - Precision ~96% (Pourmohamad 2026) comes from uniform far-away absences.
   - All of these measure *when* and *which region*. The project's within-beat, within-day metric deliberately removes both.
2. **Honest local or real-prevalence evaluations land where the project is:**
   - Pourmohamad's model rejects only ~67% of same-day absences within 4 km of an ignition.
   - Pádua 2026 (Cerrado, temporally split): AUC-ROC ≈0.78–0.79, AUC-PR ≈3.3x no-skill.
   - Gholami 2018 (1 km, human activity): AUC 0.56–0.74 for standard models.
   - WISP union AUROC: 0.65–0.76.
   - Girtsou 2021 (500 m, next day, real prevalence): operating points imply only ~1.25–1.5x lift (derived), even including between-region variance.
   - A within-day AUC of 0.7–0.8 matches these.
3. **New ignitions are much harder than persistence:**
   - WISP: Hit@14 (5 km) is 13–19% for new ignitions vs 50–67% for continuing fires.
   - Huot: removing the previous fire mask cuts AUC-PR from 28.4 to 6.8.
   - Most published "next-day" skill is persistence of burning fires.
   - Human-caused ignition location at ≤1 km/daily is described as inherently random (Taylor 2013). Operational agencies predict human-caused counts on 10–20 km cells (Phelps & Woolford; Magnussen & Taylor).
4. **Label noise caps the score:**
   - MODIS burned area dates only 68% of burns within 2 days (Giglio 2018). S2/L8 dating lags by several days.
   - MOD14 next-day F1 is only ~12% vs ~29% for VNP14 (Karlsson 2025).
   - With S2 scars dated within 2–5-day windows, part of the remaining "miss" is timing error, not ranking error.

**Caveat:** no paper found reports the project's exact metric (top-k of ~38 cells per administrative beat per day). The comparison is by analogy. The judgment that 1.8x is "upper-end" is my reading, not a literature number.

### E2. The VIIRS division model claims need re-checking

- "~85% of fires in or next to the top 10% of squares (~20% of ground)" depends heavily on the adjacency rule.
  - Huot shows that coarsening by 2–8x raises AUC-PR from 28 to 40–66 for the model, and from 11.5 to 19.5–41 for persistence alone.
  - Each top cell plus its 8 neighbours can cover up to 9x its own area. The real area of "top 10% ∪ neighbours" must be measured, not assumed to be 20%.
  - Apply the same in-or-adjacent rule to a random ranking and to a "fire in last 7 days within 1 cell" persistence ranking.
- "~56% for brand-new fires" is far above WISP's 13–19% at 5 km tolerance.
  - The metrics differ (10 point queries per region vs a 10% area budget), so this is not a contradiction.
  - But it should be reproduced with:
    - the measured footprint area;
    - a random baseline under the same rule;
    - a stricter "new" definition (e.g. no VIIRS within 5 km in the past 14–30 days, *and* no S2 scar adjacent).
- Do not compare the 85%/56% (VIIRS, adjacency, 10% area) with the 29–31% (scar labels, exact cell, 5 of 38, 1–2 days) as if they measured the same thing. They use different answer keys, footprints and budgets.

### E3. Best realistic ceiling

- The hard ceiling under the 5-per-beat cap is ~64% (the project's own perfect-oracle number).
- On *where* (fixed daily budget), the literature gives no reason to expect a large jump from 29–31%:
  - Human-ignition location is weakly predictable at ≤1 km daily.
  - GAMs match ML for human-caused fire occurrence (Phelps & Woolford 2021b).
  - My judgment, not a published figure: a realistic reach with better features and labels is the mid-30s % (≈2.0–2.2x lift). Larger gains would most likely be label artefacts or leakage.
- The large lever is *when*. Varying the daily budget with forecast fire activity (29% → 63% in the project) is consistent with the literature:
  - Weather and fire-danger indices explain daily and regional *counts* well (Taylor 2013; Preisler 2004; operational Canadian practice; McFayden 2020 daily route planning).
  - It is the operationally established use of fire-danger forecasts.

### E4. Methods that have shown gains over a "burn history + day-of-year" baseline

1. **Recent active fire nearby (persistence/spread), for the spread part of the problem.** This is the largest single gain in every next-day study (Huot, WISP, Karlsson). Score new vs continuing fires separately so persistence does not hide weak ignition skill.
2. **Per-cell dryness and fuel state:**
   - NDVI/NBR change, soil moisture, evapotranspiration (Jain 2021 correlations).
   - Fuel accumulation since the last burn (Mondal & Sukumar).
   - Antecedent memory features (Pádua 2026: AUC-PR rose from 0.24 to 0.31 when moving averages were added).
   - This matches the project's finding.
3. **Human-access covariates:** distance to settlement/cropland, roads, NTFP collection zones (Satpura 2025; Pourmohamad 2026). Expect modest gains, and they drift over years.
4. **Better labels:**
   - VNP14 over MOD14 (Karlsson).
   - Fusing S2 scars with VIIRS first detections to tighten dates (the Mesogeos-style ignition-date refinement).
   - Score with tolerance windows matched to each scar's dating uncertainty.
5. **Calibration and aggregation:**
   - Intercept offsets for case–control sampling; Platt or GAM scaling fitted by year (Phelps & Woolford 2021b; Taylor 2013).
   - Check reliability by summing calibrated cell probabilities to expected beat-day and day counts, then comparing with observed counts (Preisler 2004).
   - Use log score and AUC-PR with year-wise confidence intervals.
6. **Allocation designs:**
   - Concentrating patrol effort on top-ranked units gave more finds per unit effort in field tests (Gholami 2018).
   - Daily effort-allocation frameworks weight occurrence risk by the chance that nobody else would detect or report the fire (McFayden 2020).
   - Flexible "when" budgets are where the project's largest gain already comes from.

### E5. Evaluation hygiene checklist for the project

- Use one answer key per comparison. Do not mix VIIRS-point metrics with scar-cell metrics.
- Report hit rate at a fixed *measured* area fraction, alongside random and persistence baselines under identical footprint rules (exact cell vs in-or-adjacent).
- Split new ignitions from continuing or nearby fires, with a strict "new" definition.
- Remove cells already burned this season from the candidate pool, or report results both with and without them.
- Evaluate year by year (2020-type behavioural shocks), with bootstrap confidence intervals over beat-days.
- Check calibration with expected vs observed counts per day and per beat.
