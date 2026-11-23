# Modelling methods for rare-event, small-sample fire prediction (thread 1: 2-day model)

Scouting round 3, topic "ml", 14 Oct 2026. The question: which modelling methods could beat or add to our LightGBM 2-day model? Our numbers: about 15,000 first-burn events, 10 seasons, about 2,600 cells of 500 m, 94 beats, scored on recall at 5 picks per beat per day (29.5% vs 16.6% random). Trees currently beat CNNs, a TerraTorch/Prithvi fine-tune and AlphaEarth embeddings.

Not repeated here because earlier notes cover them: Hawkes and self-excitation features, LambdaRank, pooling other reserves, NDVI slopes and neighbourhood dryness, the leakage audit of scar-closing dates, and Phelps & Woolford recalibration (see `short_horizon_prediction*.md` and `fire-prediction-landscape.md` §3–4).

Source tags: **FULL** means the full text was downloaded (arXiv PDF → pdftotext) and its methods and results sections were read. **PARTIAL** means only some sections were read. **ABSTRACT ONLY** is what it says. My own reasoning is marked **[inference]**.

How big our problem is [inference]: 2,600 cells × about 180 season days × 10 seasons ≈ 4.7 M cell-days, of which 15,000 are positive (prevalence about 0.3%). Each day has 94 beats × 5 = 470 picks, about 18% of cells. By "data size" below I mean positives and rows, because that is what limits us.

---

## A. Tabular foundation models

### A1. TabPFN-2.5 technical report (Prior Labs 2025), arXiv 2511.08667. **FULL** (abstract, sections 1–6, licence)
https://arxiv.org/abs/2511.08667 · code: `pip install tabpfn` · https://github.com/PriorLabs/TabPFN
- Built for up to **50,000 training rows and 2,000 features**. The report also gives "strong results" up to 100 K rows on TabArena.
- Default TabPFN-2.5 has a **100% win rate against default XGBoost** on classification datasets of ≤10 K rows and ≤500 features, and **87%** on datasets up to 100 K rows. It matches AutoGluon 1.4 tuned for 4 hours. These are win rates across many datasets, not effect sizes. No dataset in the report resembles ours: none has a 0.3% positive rate inside a 4.7 M-row space-time grid.
- Hardware. The authors recommend an H100 or A100. "Integrated GPUs, MPS and CPUs are supported but only suitable for small datasets." The fit-with-cache mode costs about 6.1 KB of GPU memory per training cell, so a 50 K × 60 table is about 18 GB, which is more than a 16 GB card. The model is retrained on every `.predict()` call, so predictions should be batched in chunks of 1,000–10,000 rows.
- **Licence: TabPFN-2.5 weights are non-commercial.** "Model, derivatives and outputs cannot be used for any commercial or production purpose." That covers testing, but **not the live alert system (thread 5)** without a commercial licence.
  - [inference, from memory, verify on the repo] The older TabPFN v2 weights are under the "Prior Labs License", which is Apache-2.0 plus an attribution clause, and can be selected in the same package.
- **Concrete action for us (thread 1):** use it as an offline ensemble member, not a replacement. Build a 50 K-row context: all positives from 4–5 training seasons, plus negatives sampled **from the same beat-days** as those positives, about 1:2. Use the same feature table as LightGBM. Score held-out seasons and rank-average with LightGBM inside each beat-day. Expected effect: 0 to +1.5 points of recall [inference]. The debris-flow result (A4) suggests "tied with trees" is the likely outcome.
- **Runs on:** CPU, yes, but slowly. A full backtest of 4.7 M query rows is impractical on CPU [inference]. Restrict scoring to the Mar–Apr peak of 2–3 held-out seasons (about 600 K rows). Through torch-directml it is doubtful: DirectML is stuck at PyTorch 2.3–2.4 and TabPFN asks for ≥2.8 for speed. AMD's ROCm-on-Windows preview (PyTorch 2.8, RX 7000/9000 only) is the better GPU route if the card is on AMD's list.

### A2. TabICL (Qu, Holzmüller, Varoquaux, Le Morvan, ICML 2025), arXiv 2502.05564. **FULL** (abstract, sections 3–4)
https://arxiv.org/abs/2502.05564 · https://github.com/soda-inria/tabicl
- Pretrained on synthetic tables of up to 60 K rows. It **handles 500 K training rows × 500 features on about 20 GB of GPU memory**, with CPU and disk offload.
- On 200 TALENT datasets it is on par with TabPFNv2 and up to 10× faster. **On the 53 datasets with more than 10 K samples it beats both TabPFNv2 and CatBoost.**
- Timing: about 1.1 s per 1,000 samples on an A100. Tuning CatBoost on a CPU takes about 3 minutes.
- **Why this matters for us:** it can take far more context than TabPFN, for example all 15 K positives plus 200 K negatives.
- **Concrete action (thread 1):** this is the tabular foundation model to try first, because it is open-source (BSD-3 on the repo, [verify]) and takes a larger context. Settings: context of all positives from the training seasons plus 10–15 negatives per positive, sampled within the same beat-days; classification only. Expected effect: 0 to +1.5 points [inference].
- **Runs on:** CPU, for daily operation (2,600 rows a day is trivial) and for a peak-season backtest. A 16 GB AMD card through DirectML is untested: FlashAttention is not available there, so expect fallbacks [inference].

### A3. Correcting class imbalance in prior-data fitted networks (McDowell, Stromberg, Sankar 2026), arXiv 2605.21742. **FULL**
https://arxiv.org/abs/2605.21742
- TabPFN-2.5 on 11 OpenML-CC18 binary tasks, with minority prevalence of 0.05–0.5 and contexts of 100–1,000 rows.
- With an imbalanced context the model is **not badly calibrated, just biased toward the majority class**. Its ROC AUC also falls as imbalance grows: on kr-vs-kp with N = 25, AUC is **0.877 at a 50% minority share and 0.746 at 10%**.
- Two fixes work best. **Thresholding at τ = π₁** is best overall. **Downsampling the majority class to 1:1** is about as good, gives the best worst-class accuracy, and cuts compute, because cost grows quadratically with context size. Oversampling and synthetic upsampling were worse.
- **Concrete action (thread 1):** for any TabPFN or TabICL run, **balance the context near 1:1 to 1:3 by downsampling negatives**. Do not oversample positives. For ranking within a beat-day, no threshold correction is needed, because the order of scores is unchanged.

### A4. Post-wildfire debris-flow prediction: 15 models including TabPFN-2.5 (Ledingham et al. 2026), arXiv 2608.05265. **FULL** (results sections)
https://arxiv.org/abs/2608.05265
- 1,550 basin-storm observations from the USGS western-US dataset, 50 repeated stratified outer folds.
- Threat score (CSI): **TabPFN 0.637, ExtraTrees 0.636, CatBoost 0.622, XGBoost 0.621, Random Forest 0.620**, with fold standard deviation 0.045–0.054. **The TabPFN "win" is +0.016 over XGBoost, which is inside the fold noise.**
- After synthetic augmentation (TabPFN's unsupervised generator), the top five fall within 0.005 of each other: CatBoost 0.643, TabPFN 0.641, RF 0.641, XGBoost 0.640. Augmentation helped deep models most (+0.041) and did nothing useful for trees.
- **Concrete action:** keep expectations low. This is the closest hazard-domain test of a tabular foundation model, and it is a tie with tuned trees. Do **not** use TabPFN synthetic augmentation for LightGBM.

### A5. TabArena (Erickson et al. 2025), arXiv 2506.16791. **PARTIAL** (abstract, sections 1–4)
https://arxiv.org/abs/2506.16791 · https://tabarena.ai
- Findings:
  - (A) Ensembling tuned hyperparameter configurations of one model gives the best single-model performance.
  - (B) Tuned and ensembled deep models now match or beat GBDTs.
  - (C) **Foundation models dominate on small data** without tuning.
  - (D) **Ensembles across model families are the overall state of the art.**
  - Benchmarks use 8-fold CV ensembles.
- **Concrete action (thread 1):** the cheapest gain from this literature does not need a foundation model. Rank-average **5–10 LightGBM models trained with different seeds and hyperparameters** (bagged over seasons), plus one dissimilar model (a logistic GAM, or TabICL). Expected effect: +0.3 to +1 point [inference].

### A6. Grinsztajn, Oyallon & Varoquaux 2022, "Why do tree-based models still outperform deep learning on tabular data?", arXiv 2207.08815. **PARTIAL**
https://arxiv.org/abs/2207.08815
- On 45 datasets of about 10 K rows, trees stay state of the art. The reasons: neural nets are hurt by **uninformative features**, are biased toward smooth functions while targets are irregular, and are rotation-invariant.
- This explains our result that the deep CNN and AlphaEarth added nothing [inference]. Each adds many weakly informative inputs.
- **Concrete action:** before any neural or foundation model is tested, **prune the feature set to the top 30–60 features by LightGBM gain or SHAP**. This applies to TabPFN and TabICL too, because their cost scales with features.

### A7. TabPFN-TS (Hoo et al. 2025), arXiv 2501.02945, and CARTE (Kim et al. 2024), arXiv 2402.16785. **PARTIAL** (abstracts and intros)
- **TabPFN-TS** turns forecasting into tabular regression with calendar features (11 M parameters). It is state of the art on covariate-informed forecasting in GIFT-Eval and fev-bench. It forecasts series values, so it is not a ranking classifier.
  - Possible use (thread 1, weather): forecasting a beat-level daily *count* of new ignitions, as a "when" signal to feed LightGBM. Low priority.
- **CARTE** is a graph-transformer for tables with string entries and unmatched schemas. It helps when columns are text or categorical and there are related source tables. **Not useful for us**: our features are numeric.

---

## B. Geospatial foundation models

### B1. Prithvi-EO-2.0 (Szwarcman et al. 2024/2026), arXiv 2412.02732. **FULL** (wildfire sections)
https://arxiv.org/abs/2412.02732 · https://github.com/NASA-IMPACT/Prithvi-EO-2.0 · TerraTorch
- Wildfire scar mapping (HLS, US fires 2018–2021, UPerNet head), burn-scar IoU:
  - Prithvi-EO-1.0-100M: **76.8**
  - 2.0-300M: **79.9**
  - 2.0-300M-TL: **81.1**
  - 2.0-600M: **83.2**
- These are segmentation of a scar that already exists. Nothing in the paper tests forecasting.
- **Concrete action:** for thread 2 (per-alert burn scars) only; already covered in `alert_burn_scars_fullread.md` §8. For thread 1, no evidence of gain.

### B2. PANGAEA benchmark (Marsocci et al. 2025), arXiv 2412.04204. **FULL** (results and discussion)
https://arxiv.org/abs/2412.04204 · https://github.com/VMarsocci/pangaea-bench
- On HLS Burn Scars, the **supervised UNet trained from scratch gets 84.51% mIoU**, the best of all. Prithvi (v1) gets 83.62, CROMA 82.42, DOFA 80.63, SatlasNet 79.96.
- The authors' summary: "learning the features through convolution is the best approach for one-class datasets". On regression tasks with a domain gap, foundation models were worse than supervised baselines.
- Foundation models gain ground only with **10% of the labels**: UNet's top-2 count falls from 6 to 2 while CROMA's rises to 6.
- **Concrete action:** this is independent confirmation of our own finding. For simple one-class targets with plenty of labels, a small CNN or tree model is as good. Do not spend more on foundation-model fine-tuning for thread 1.

### B3. ExEBench (Zhao et al. 2025), arXiv 2505.08529. **PARTIAL** (fire task)
https://arxiv.org/abs/2505.08529
- Fire task = HLS burn-scar segmentation. With a frozen encoder, Prithvi-2 scores best, because its pretraining data comes from the same source. Prithvi-2 is about 10% better than Prithvi-1. A **climate-pretrained model (ClimaX) failed**, producing a uniform mask. U-Net from scratch reached IoU 84.51.
- Pretrained weights mainly sped up convergence.
- **Concrete action:** none for thread 1. A weather or climate foundation model does not transfer to surface imagery.

### B4. LoRA adaptation of geospatial foundation models for wildfire mapping (Shibli et al., KTH 2026), arXiv 2605.04989. **PARTIAL**
https://arxiv.org/abs/2605.04989
- 3,820 US/Canada fire events, 2017–2023, Sentinel-2, MTBS/NBAC labels. TerraMind, DINOv3 and Prithvi-v2 compared.
- **Prithvi-v2 with LoRA (rank 8, α = 1) was the most accurate overall**, training 0.5–1% of parameters, and generalised best across domains.
- **Concrete action (thread 2 only):** if the Prithvi burn-scar model is fine-tuned again for Ratapani, use LoRA r = 8 rather than full fine-tuning.

### B5. Presto (Tseng et al. 2023/24), arXiv 2304.14065. **FULL** (results, appendix A)
https://arxiv.org/abs/2304.14065 · https://github.com/nasaharvest/presto
- A pixel time-series transformer with **402 K parameters**. Inputs are monthly S1, S2, ERA5, DEM and Dynamic World. Fine-tuning took **under 6 minutes on a 2017 MacBook Pro CPU**.
- **Live fuel moisture (western US, geographically separate test), RMSE:**
  - **Random Forest 23.84**
  - Presto fine-tuned 25.28
  - Presto embeddings + RF 25.98
  - Linear regression 28.20
  - The plain random forest won.
- Algae blooms: Presto fine-tuned 0.815 vs RF 1.249, so Presto won there.
- **Concrete action (threads 1 and 3):** Presto is the only geospatial foundation model that is cheap enough to try (CPU). Expect little.
  - Settings: per cell, 12 monthly composites of the previous year plus the current season to date (S2 bands, ERA5 temperature and precipitation, DEM). Extract the 128-dimensional embedding, reduce it to 8–16 components with PCA, and add them to LightGBM.
  - Expected effect: 0 to +0.5 points [inference]. Its own fuel-moisture result says a random forest on raw bands is as good.

### B6. Galileo (Tseng, Fuller et al. 2025), arXiv 2502.09356. **PARTIAL**
https://arxiv.org/abs/2502.09356 · https://github.com/nasaharvest/galileo
- One model covering S1, S2, elevation, weather and pseudo-labels, for both images and pixel time series. It outranks Presto and AnySat on pixel time-series tasks (CropHarvest, Breizhcrops). It ranks above CROMA, SatMAE, DOFA and Prithvi 2.0 in average rank across 11 benchmarks. Sizes: ViT-Nano, -Tiny, -Base.
- No fire task.
- **Concrete action:** only as a drop-in replacement for Presto in B5 if Presto shows any signal. The Nano and Tiny versions run on CPU.

### B7. AnySat (arXiv 2412.14123), TerraMind (arXiv 2504.11171), DOFA (arXiv 2403.15356). **PARTIAL** (headline and compute only)
- AnySat: about 125 M parameters in total; pretraining took 1,760 H100 GPU-hours and fine-tuning 10–40 h.
- TerraMind-B: pretraining took 9,216 A100 GPU-hours.
- DOFA: wavelength-conditioned multi-sensor. In PANGAEA it scored 80.63 on burn scars, below UNet.
- None was tested on fire forecasting.
- **Concrete action:** skip for thread 1.

### B8. Annual embeddings (Tessera and AlphaEarth) for burned area (Knezevic, Coomes et al. 2026), arXiv 2609.25731. **PARTIAL** (abstract, section 2)
https://arxiv.org/abs/2609.25731 · Tessera: https://github.com/ucam-eo/geotessera
- **Tessera** gives 128-dimensional annual embeddings at 10 m for 2017–2025. It encoded wildfire disturbance strongly: even linear models separated burned from unburned pixels. **The signal was weaker in AlphaEarth.**
- Results: F1 = 0.90 for all same-year fires in benchmark scenes; 97% of California reference burned area recovered with no California training data; transfer from the US to 88 European fires gave F1 = 0.88; ignition date recovered with MAE 13 days.
- **Concrete action:**
  - Thread 2 (burn scars): try **Tessera year-t embeddings as a cheap scar classifier**. It may beat AlphaEarth for leaf-fall versus burn confusion.
  - Thread 1: only **year t−1** embeddings may be used (year t contains the fires themselves, which is leakage). Expect about 0, as with AlphaEarth [inference].
  - India coverage still needs checking with `geotessera`.

---

## C. Weather foundation models

### C1. Prithvi WxC (Schmude et al. 2024), arXiv 2409.13598. **PARTIAL**
https://arxiv.org/abs/2409.13598 · weights on Hugging Face (ibm-nasa-geospatial)
- **2.3 billion parameters**, trained on MERRA-2. Downstream tasks: downscaling, gravity-wave flux, hurricane track. **No fire-danger task** anywhere in the paper.

### C2. Aurora, GraphCast/WeatherNext, AIFS (searches; no fire-danger paper found). **ABSTRACT ONLY / searches**
- I found no paper that computes FWI or fire danger from Aurora, GraphCast, WeatherNext, AIFS or Prithvi-WxC. Searched 14 Oct 2026, standard and extended web search.
- The nearest items:
  - A NASA project fine-tuned Aurora for **wildfire NO₂**, not ignition (NTRS 20260005025).
  - GraphCast was downscaled with WRF for the Marshall Fire windstorm (Weather & Forecasting 40(1), 2025).
  - ECMWF AIFS (0.25°) has been operational since 25 Feb 2025, and its ensemble since July 2025. Raw 10 m wind from AIFS is less skilful than from the IFS ensemble (arXiv 2606.02508).
- **Concrete action (thread 1):**
  - **Do not fine-tune a weather foundation model.** It needs A100-class GPUs and has no tested fire benefit, and our own finding is that weather sets *when*, not *where*.
  - If forecast weather is needed for an honest 2-day issue (see the earlier leakage note), take ready-made forecast fields (ECMWF open data, IFS or AIFS) at 0.25°. Compute day+1/day+2 VPD, RH minimum, temperature maximum and 3-day rain. Add them as sanctuary-wide "when" features.
  - Expected effect: 0 to +0.5 points. This is about the honesty of the evaluation more than about gain.
- **Runs on:** CPU, because only downloaded fields are used.

---

## D. Spatio-temporal deep models (ConvLSTM, GNN) for fire forecasting

### D1. Prapas et al. 2021, "Deep learning methods for daily wildfire danger forecasting" (Greece FireCube), arXiv 2111.02736. **FULL**
https://arxiv.org/abs/2111.02736
- Data: a 1 km × 1 day datacube for Greece, 2009–2020. Train 2009–18, validate 2019, test 2020. All positives, **2 negatives per positive** stratified by land cover, so the test set is near-balanced.
- Test 2020:

  | Model | Precision | Recall | F1 | AUROC |
  |---|---|---|---|---|
  | RF (pixel features only) | 0.832 | 0.508 | 0.631 | 0.898 |
  | LSTM | — | 0.762 | 0.751 | 0.920 |
  | CNN | — | 0.553 | 0.63 | 0.910 |
  | ConvLSTM | — | 0.646 | 0.714 | 0.926 |

- **The random forest got no temporal or neighbourhood features**, so the comparison is "context vs no context", not "deep vs trees".
- **Concrete action:** trees need explicit lag and neighbourhood features. That is what we do already; the gains here come from context, not from the architecture [inference]. No ConvLSTM experiment is needed.

### D2. Michail et al. 2024, "Seasonal fire prediction using spatio-temporal deep neural networks" (SeasFire), arXiv 2404.06437. **FULL**
https://arxiv.org/abs/2404.06437
- Global 0.25°, 8-day steps, 2001–2021. Naive baselines ("any previous year had fire in this period" and "majority of years") reach **AUPRC 0.35 and 0.39**.
- At the next step: **ConvLSTM 0.74, T-GCN 0.69, GRU 0.64**. ConvLSTM with a 36-step (288-day) history and radius 5 (11×11 neighbourhood). Gains from a wider radius saturate quickly: AUPRC 0.726–0.731 for r = 1–5.
- **Concrete action (thread 1):** long histories matter. Add features for **the same calendar window in each of the last 3–9 seasons** (burned or not, per cell and per 3×3 block), plus the fraction of past seasons burned by this date. Settings: ±7-day window around the issue date. Expected effect: +0.5 to +1.5 points [inference]. Low cost.

### D3. FireCastNet (Michail et al. 2025), arXiv 2502.01550. **PARTIAL**
https://github.com/seasfire/firecastnet
- A 3D-convolution encoder plus GraphCast-style graph on the SeasFire cube, at 1° and 8-day steps, up to 6 months ahead. Global naive baselines: "any-fire" AUPRC 0.174 and "majority" 0.3211. It beats GRU, Conv-GRU, ConvLSTM, U-TAE and TeleViT.
- **Not usable at 500 m with 15 K events.**

### D4. Causal GNN for wildfire danger (Zhao et al. 2024, ICLR ML4RS), arXiv 2403.08414. **FULL**
https://arxiv.org/abs/2403.08414
- SeasFire, Mediterranean, 8-day horizon, positive rate about **1.1%**. AUPRC (%):
  - LSTM 32.9
  - GRU 34.6
  - GNN with correlation graph 30.5
  - fully connected GNN 29.1
  - **causal GNN (PCMCI graph) 34.6**
  - The causal GNN only **ties the GRU**.
- In the boreal zone (positive rate 0.0737%) all deep models were weak. Training negatives were resampled to 5:1.
- **Concrete action:** none. No gain over a simple recurrent net, let alone trees.

### D5. Mesogeos (Kondylatos et al. 2023), arXiv 2306.05144. **FULL** (tracks and results)
https://github.com/Orion-AI-Lab/mesogeos
- Mediterranean datacube, 1 km, daily, 2006–2022. Danger track: 25,722 samples (8,574 positives, **1:2 negatives**). AUPRC: LSTM 0.853, Transformer 0.856, GTN 0.858.
- **These AUPRCs come from near-balanced test sets and cannot be compared with our recall@budget.** The burned-area-size track gained only slightly over an "ignition only" input.
- **Concrete action:** a caution only. Never report balanced-test AUPRC to the project lead.

### D6. Conformal risk control for wildfire spread (Dayan 2026, Imperial), arXiv 2603.22331. **FULL**
https://arxiv.org/abs/2603.22331 · https://github.com/baljinnyamday/wildfire-evacuation-crc
- NDWS dataset: 18,545 patches of 64×64 pixels with 12 channels, about 5% fire pixels; split 70/15/15 (calibration 2,781).
- AUROC: **LightGBM 0.854, Tiny U-Net 0.969, ResGNN-UNet 0.964**.
  - LightGBM was trained per pixel on a 5% subsample **with no neighbourhood features**.
  - The GNN adds nothing over the U-Net.
- Conformal risk control picks the threshold that keeps the false-negative rate at or below 5%:
  - All models reach ≥94% coverage.
  - LightGBM must flag **62.6%** of pixels; the U-Net **14.9%**; the GNN 15.1%.
- The patches were split at random, so neighbouring days and patches can leak.
- **Concrete actions:**
  - (i) Thread 1: the U-Net beat LightGBM here only because LightGBM lacked spatial context. We already carry neighbourhood features; confirm that 3×3 and 5×5 lags of recent burns and dryness are in.
  - (ii) Thread 5: CRC is a simple recipe for turning "catch 80% of new fires" into a budget. On a calibration season, sort the scores of true positives and take the ⌈α(m+1)⌉-th lowest as the threshold λ. The flagged set size is the patrol budget needed. Use it to **set picks per beat or per day from a target recall**, instead of a fixed 5 [inference].

---

## E. Survival and time-to-event framing

### E1. Moradian et al. 2021, "Dynamic estimation with random forests for discrete-time survival data", arXiv 2103.01355. **FULL**
https://arxiv.org/abs/2103.01355
- Discrete-time hazard with time-varying covariates, using a person-period (here: cell-day) expansion. It compares one **global** model pooled over all time points with separate **local** per-time models.
- Weaker signal, less data, more censoring and weaker covariate autocorrelation **favour the global pooled fit**.
- **Concrete action (thread 1), probably the cheapest real gain:** our target is a *first burn per season*, so this is literally a discrete-time hazard problem. Steps:
  - (a) **Drop a cell from the risk set (training and picks) once it has burned this season.** If burned cells stay among the candidates, some of our 5 picks are wasted on cells that cannot have a first burn. Check how often that happens.
  - (b) Add "days since season start", "days since this cell last burned (any season)" and "has the cell already been censored by the scar-closing image".
  - (c) Keep one global pooled LightGBM, as Moradian recommends for weak signals, rather than per-month models.
  - Expected effect: 0 to +3 points, depending on how many picks currently land on already-burned cells [inference]. Effort is low.

### E2. Spatial survival and point-process ignition models. **ABSTRACT ONLY**
- Gelfand's spatial survival models with time-varying covariates for Cape Floristic fires (seminar abstract).
- A convolutional non-homogeneous Poisson process for power-line ignition (Wei, Qiu & Liu; Technometrics; tandf figshare 26018128).
- Neither gives numbers against tree baselines. The Hawkes point-process work is already in the earlier note.

---

## F. Imbalance tricks: what actually helps ranking

### F1. Elor & Averbuch-Elor 2022, "To SMOTE, or not to SMOTE?", arXiv 2201.08528. **FULL** (sections 1–4)
https://arxiv.org/abs/2201.08528
- 73 imbalanced datasets. For strong classifiers (**LightGBM, XGBoost, CatBoost**):
  - **balancing (SMOTE or oversampling) does not improve prediction**;
  - unbalanced strong classifiers beat balanced weak ones;
  - optimising the decision threshold gives the same result as balancing and is cheaper.
- ROC AUC is shown to be a proper scoring rule under common assumptions.
- **Concrete action:** no SMOTE and no oversampling for LightGBM. Positive weighting (`scale_pos_weight`) only for speed or stability, not for ranking.

### F2. He et al. 2014, "Practical lessons from predicting clicks on ads at Facebook" (ADKDD). **FULL**
https://quinonero.net/Publications/predicting-clicks-facebook.pdf
- Boosted trees on very rare positives. **Negative downsampling** was tested at rates {0.1, 0.01, 0.001, 0.0001}. The **best normalised entropy came at a rate of 0.025**: downsampling *improved* the model, not just its speed.
- Recalibration: **q = p / (p + (1 − p)/w)**, where w is the negative sampling rate.
- **Concrete action (thread 1):**
  - Train LightGBM on all positives plus **negatives sampled at w ≈ 0.02–0.1** (1:5 to 1:30), repeated over 5 seeds and rank-averaged (bagging over negative samples).
  - Uniform w leaves the within-beat-day *order* unchanged, so recall@5 needs no correction. Apply the formula only when probabilities are shown to officers or combined with another model.
  - Also sample negatives within the same beat-days ("case-control within the query") so the model learns *where within a day* rather than *which day*.
  - Expected effect: 0 to +1 point, plus faster iteration [inference].

### F3. Imbalance-XGBoost: focal and weighted losses (Wang et al. 2020), arXiv 1908.01672. **FULL**
https://github.com/jhwjhw0123/Imbalance-XGBoost
- Focal and weighted cross-entropy losses for XGBoost, tested on small UCI sets with imbalance up to 42:1. Gains appear only in threshold metrics (F1, MCC), for example ozone F1 0.217 → 0.266–0.273. Ranking quality (AUC) is unchanged.
- **Concrete action:** skip focal loss. It changes the operating point, not the ranking. LambdaRank (earlier note) is the ranking-aware objective to test.

---

## G. Evaluation and leakage in space-time cross-validation

### G1. kNNDM CV (Linnenbrink, Milà, Ludwig & Meyer 2024), GMD 17:5897. **FULL**
https://doi.org/10.5194/gmd-17-5897-2024 · R `CAST::knndm`, `blockCV::cv_knndm`
- The right CV mimics the **distance between prediction and training locations**.
  - Random 10-fold CV is reliable for random samples but fails for clustered ones.
  - Spatial 10-fold CV **overestimated error**: it was too pessimistic and the most variable.
  - kNNDM matched the true error in most designs.
- **Concrete action (thread 1), and an important correction to an earlier suggestion:** we predict **the same 2,600 cells in future seasons**. The prediction-to-training distance is therefore zero in space and positive in time.
  - The matching validation is **season-out (forward) CV with no spatial blocking**. A 3 km spatial buffer (as in the AlphaEarth fire study) would answer a question we are not asking, "new reserve", and make every model look worse.
  - Keep spatial blocking only for the transfer experiment (pooling other reserves).
  - Within a season, use **a gap of at least 7 days** between training and test days if any within-season split is used, so that lag features cannot see the target fire [inference].

### G2. Palisades Fire structure-loss GeoAI (2026), arXiv 2608.22293. **PARTIAL**
https://arxiv.org/abs/2608.22293
- 9,883 inspected structures. Gradient boosting under **random CV: ROC-AUC 0.921 → under 1 km spatial blocking: 0.753 ± 0.060**, with Brier score 0.213. The logistic model degraded less and was better calibrated under blocking.
- **Use for us:** this shows how much optimism random CV can carry: 0.17 AUC on a clustered target. It is the reason never to report a random-split number. It does not argue for spatial blocking in our same-cell setting (see G1).

### G3. Cerrado daily active-fire benchmark (Pádua, Levada & Valente 2026), arXiv 2606.04170. **FULL**
https://arxiv.org/abs/2606.04170 · https://github.com/julianopadua/cerrado-wildfire-prediction-reproducibility
- The closest to us in setting: protected areas, a dry season (May–Oct), human-dominated ignitions, Google Earth Engine features.
  - Data: MODIS Aqua detections for Cerrado in Minas Gerais, 2019–2025. Detections within 3 km and 3 days were merged into one event head.
  - Model triad: logistic regression, RF and XGBoost, under 5-fold time-series CV.
  - Test: two **held-out conservation units at 1:100 prevalence** (no-skill AUPRC about 0.010).
- Nested feature stages, CV AUPRC with a no-skill rate of about 0.091:

  | Stage | Features added | LR | RF | XGB |
  |---|---|---|---|---|
  | 1 | ERA5-Land weather | 0.241 | 0.235 | 0.229 |
  | 2 | + MODIS surface | 0.258 | 0.252 | 0.246 |
  | 3 | + terrain and built-up proximity | 0.261 | 0.274 | 0.264 |
  | 4 | **+ causal EWMA "memory" features** | **0.307** | **0.300** | **0.303** |

  - Stage 4 adds EWMAs of temperature, humidity, precipitation, NDVI, water stress and LST, at **half-lives of 3, 7 and 15 days**, with α = 1 − 2^(−1/h).
- So the memory features added **+0.04 to +0.05 AUPRC (about +17%)**. **Logistic regression was as good as XGBoost**, a sign that the signal is mostly monotone and the data small.
- On held-out units, RF at stage 4 reached AUPRC 0.100 against 0.061 for XGBoost (no-skill 0.010). XGBoost there gave recall 0.947 at precision 0.018, a "flag everything" behaviour.
- Caveat: stages 1–3 use same-day covariates, so this is not a true forecast (the authors say so).
- **Concrete actions (thread 1):**
  - (i) Add **causal EWMAs at half-lives of 3, 7 and 15 days** for Tmax, RH minimum, VPD, rain, NDMI and LST. Use values up to t−1 only. Expected effect: +0.5 to +2 points [inference]. This overlaps only partly with the "30/60-day slopes" in the earlier note.
  - (ii) Add a **plain logistic or GAM model** to the ensemble. Here it matched the boosted trees.

---

## Datasets and benchmarks table

| Name | Link | Resolution | Years | Licence | Access | Use for us |
|---|---|---|---|---|---|---|
| Cerrado daily active-fire benchmark + pipeline | github.com/julianopadua/cerrado-wildfire-prediction-reproducibility | point-day, MODIS 1 km | 2019–2025 | see repo | git clone; GEE scripts | Template for EWMA memory features and a held-out-area protocol |
| Next Day Wildfire Spread (NDWS) | kaggle.com/datasets/fantineh/next-day-wildfire-spread | 1 km, 64×64 patches, daily | 2012–2020 (US) | CC BY 4.0 [verify] | Kaggle / TFRecord | Sanity-test code (CRC, U-Net vs LightGBM) |
| SeasFire datacube | github.com/SeasFire (Zenodo link in repo) | 0.25°, 8-day | 2001–2021 | CC BY 4.0 [verify] | Zarr from Zenodo | None directly (too coarse); a source of global baselines |
| Mesogeos | github.com/Orion-AI-Lab/mesogeos | 1 km, daily | 2006–2022 (Mediterranean) | CC BY 4.0 [verify] | Zarr download | Negative-sampling designs to avoid |
| Greece FireCube (Prapas 2021) | arXiv 2111.02736 → Zenodo link in paper | 1 km, daily | 2009–2020 | open [verify] | Zenodo | Comparison protocol |
| HLS Burn Scars | huggingface.co/datasets/ibm-nasa-geospatial/hls_burn_scars | 30 m, 512×512 chips | 2018–2021 (US) | CC BY 4.0 | HF datasets | Thread 2 only |
| Tessera annual embeddings | github.com/ucam-eo/geotessera | 10 m, 128-d per year | 2017–2025 | see repo | `pip install geotessera` | Thread 2 scar classifier; thread 1 (t−1 only) |
| TabArena benchmark | tabarena.ai | — | living | Apache-2.0 [verify] | pip | Model-choice evidence |
| TabPFN-2.5 weights | huggingface.co/Prior-Labs/tabpfn_2_5 | — | 2025 | **non-commercial** | HF login, pip `tabpfn` | Offline test only |
| TabICL | github.com/soda-inria/tabicl | — | 2025 | BSD-3 [verify] | pip `tabicl` | Tabular foundation model allowed in production |
| Presto | github.com/nasaharvest/presto | pixel time series, 10 m, monthly | — | MIT [verify] | pip / git | CPU embedding test |

---

## Ranked action list for the 2-day model (by expected gain; all gains are my estimates [inference])

| # | Action | Source | Expected gain (recall@5 points) | Effort | Hardware |
|---|---|---|---|---|---|
| 1 | **Discrete-time hazard risk set**: remove cells already burned this season from training and from picks; add days-since-season-start and days-since-last-burn | E1 (Moradian); first-burn target | 0 to +3 (depends on current wasted picks; measure first) | Very low | CPU |
| 2 | **Causal EWMA memory features**, half-lives 3/7/15 days, for Tmax, RH minimum, VPD, rain, NDMI, LST (values up to t−1) | G3 (Cerrado: +0.04–0.05 AUPRC, +17%) | +0.5 to +2 | Low | CPU |
| 3 | **Same-calendar-window history**: burned in the ±7-day window around this date in each of the last 3–9 seasons, per cell and per 3×3 block | D2 (ConvLSTM gains came from 36-step history) | +0.5 to +1.5 | Low | CPU |
| 4 | **Negative-bagged LightGBM ensemble**: all positives + negatives at w ≈ 0.02–0.1, sampled within beat-days, 5–10 seeds/hyperparameter sets, rank-averaged; plus a logistic GAM member | F2 (Facebook best at w = 0.025), A5 (TabArena), G3 (LR = XGB) | +0.3 to +1 | Low | CPU |
| 5 | **Budget from target recall (CRC)**: on a calibration season, find the threshold giving ≥X% recall and set picks per beat or day from it, instead of a fixed 5 per beat | D6 | +1 to +3 in total recall at the same total picks, if beats may get unequal picks; 0 if 5 per beat is fixed | Low | CPU |
| 6 | **TabICL (then TabPFN v2) as an ensemble member**: pruned top 30–60 features, context near 1:1–1:3 sampled within beat-days, scored on the Mar–Apr peak of held-out seasons | A2, A3, A1, A4 | 0 to +1.5 (A4 suggests a tie) | Medium | CPU (slow); GPU via ROCm-Windows if supported; DirectML doubtful |
| 7 | **Validation protocol fix**: season-out forward CV with no spatial buffer (same cells are deployed); ≥7-day gap for any within-season split; block bootstrap over beat-days for CIs; never quote random-split or balanced-test AUPRC | G1, G2, D5 | 0 (keeps comparisons honest; stops spatial buffers understating skill) | Low | CPU |
| 8 | Presto (or Galileo-Nano) per-cell embeddings → PCA 8–16 → LightGBM | B5, B6 | 0 to +0.5 | Medium | CPU |
| 9 | Forecast weather fields (ECMWF open data, IFS/AIFS) for day+1/+2 as "when" features | C2 | 0 to +0.5 (mainly honesty) | Medium | CPU |
| 10 | **Do not pursue**: ConvLSTM/GNN, fine-tuning Prithvi-EO, Prithvi-WxC or Aurora, SMOTE, focal loss, CARTE, TabPFN synthetic augmentation | D1–D4, B1–B3, C1, F1, F3, A4, A7 | ~0; trees with explicit context features already capture what these add at our data size | — | — |

Reading status: 17 sources read **FULL**, with methods and results sections: 2606.04170, 2603.22331, 2511.08667, 2605.21742, 2608.05265, 2502.05564, 2412.02732 (fire parts), 2412.04204, 2304.14065, 2111.02736, 2404.06437, 2403.08414, 2306.05144, 2103.01355, 2201.08528, Facebook ADKDD 2014, kNNDM GMD 2024, plus 1908.01672. Another 11 were read **PARTIAL**. The weather foundation model / fire danger link is a search-only negative result.

All PDFs are in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r3_ml/`, which is session scratch and not kept.
