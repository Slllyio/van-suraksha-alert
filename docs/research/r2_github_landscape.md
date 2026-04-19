# R2: GitHub Open-Source Wildfire Prediction Landscape

**Date**: 2026-04-19
**Reviewer**: Research agent
**Purpose**: Honest scan of GitHub for forest-fire / wildfire prediction repos
worth borrowing patterns from, beyond what we already shipped in v17 + v3 portal
+ Hawkes self-excitation.

## Methodology

Searched via `gh search repos` + `gh search code` across:
- `wildfire prediction`, `wildfire machine learning`, `wildfire deep learning`
- `forest fire prediction`, `fire spread CNN`, `fire spread simulation`
- `hawkes process`, `wildfire transformer`, `wildfire dataset`
- `WildfireSpreadTS`, `Mesogeos`, `SeasFire`, `FireCastNet`, `WildfireGPT`,
  `Cell2Fire`, `next_day_wildfire_spread`
- Org-level: `pyronear`, `Orion-AI-Lab`, `mitrefireline`, `fire2a`,
  `SeasFire`, `bcgov`, `cell2fire`
- Topic pages: `topic:wildfire`, `topic:wildfire-prediction`

**Filters applied**:
- Stars >= 50 OR linked from a published paper (NeurIPS, IEEE TGRS, GRL, etc.)
- Excluded UCI Algerian / Kaggle California portfolio projects
- Excluded JS / Unity game-engine "fire spread" Toy demos
- Excluded already-evaluated tier (aravind-selvam, gauravsurtani,
  IntelSoftware/ForestFirePrediction, Science Buddies)

**Result**: 15 candidates surfaced. Honest verdict on each below. Three are
truly worth deeper study (Mesogeos, WildfireSpreadTS, Orion-AI-Lab/wildfire_forecasting);
the rest are either narrowly borrowable or noted to skip.

---

## 1. Orion-AI-Lab / mesogeos — STUDY DEEP

- **URL**: https://github.com/Orion-AI-Lab/mesogeos
- **Stars / Forks**: 63 / 13
- **Last activity**: 2026-04-14 (ACTIVE)
- **Paper**: NeurIPS 2023 Datasets & Benchmarks Track (arxiv 2306.05144)
- **What it does**: Mediterranean wildfire datacube (17 variables, 2006-2022,
  daily, 1 km) with two ML benchmark tracks: (Track A) Wildfire Danger
  Forecasting and (Track B) Final Burned Area Prediction. Includes Zarr
  datacube generation + reference PyTorch dataloaders + baseline LSTM/CNN
  models.
- **Data scope**: Mediterranean basin (similar climate to dry deciduous MP
  in shoulder seasons), 17 yrs daily, ~1M+ ML samples extracted per track.
- **Architecture**: Modular — datacube generation → ML-track sample
  extraction → PyTorch Lightning training. Clean separation of concerns.
- **Verdict**: **STUDY DEEP**. Borrowable patterns:
  (a) Zarr datacube as first-class storage (we currently use scattered
      parquet/raster — Mesogeos shows clean lakehouse for fire ML).
  (b) Their "danger forecasting" track is structurally identical to our
      v17 ignition task — direct comparison of architectures (LSTM, CNN
      baselines published with metrics) gives us a calibration target.
  (c) Track B (burned-area regression) is a capability we lack — could
      bolt onto v17 cells flagged CRITICAL.
  Caveat: Mediterranean ≠ MP, so don't expect transfer learning of weights;
  borrow the *pipeline shape*, not the model.

## 2. SebastianGer / WildfireSpreadTS — STUDY DEEP

- **URL**: https://github.com/SebastianGer/WildfireSpreadTS
- **Stars / Forks**: 55 / 19
- **Last activity**: 2026-04-15 (ACTIVE; bug-fix maintenance ongoing)
- **Paper**: NeurIPS 2023 (openreview RgdGkPRQ03)
- **What it does**: Multi-modal time-series dataset for *next-day wildfire
  spread* prediction. 607 fires from US (2018-2021), each with 23 channels
  (VIIRS active fire, Sentinel-2, ERA5 weather, SRTM topo, land cover,
  drought) at 375 m, daily steps. Released via Zenodo with HDF5 conversion
  scripts + LightningCLI baselines (U-Net, ConvLSTM variants).
- **Data scope**: CONUS, 4 yrs, 607 fire events, ~13 GB raw. Smaller scale
  than Mesogeos but per-event resolution is much higher.
- **Architecture**: PyTorch Lightning + WandB sweeps; angle-feature bug
  documented (sin only, should be sin+cos) — author transparent about it.
- **Verdict**: **STUDY DEEP** — but for *spread*, not ignition. Borrowable:
  (a) The 23-channel multi-modal stack is the cleanest open template for
      what fields a per-event fire deserves. Compare to our 111 features —
      they have many of the same things plus lightning + drought indices
      we don't currently fuse.
  (b) HDF5 staging for fast PyTorch training — directly applicable to our
      spread tracker (currently disk-bound).
  (c) Their UNet for spread is a head-to-head comparison for our Muhurta
      ROS-UNet. Note the maintainer flagged a meaningful bug in Feb 2026 —
      go read the post-fix metrics, not the paper numbers.
  Skip if: you only care about ignition (their task is purely spread).

## 3. Orion-AI-Lab / wildfire_forecasting — BORROWABLE

- **URL**: https://github.com/Orion-AI-Lab/wildfire_forecasting
- **Stars / Forks**: 78 / 18
- **Last activity**: 2026-04-14 (ACTIVE)
- **Paper**: Geophysical Research Letters 2022 (Kondylatos et al,
  doi:10.1029/2022gl099368) — "Wildfire Danger Prediction and Understanding
  with Deep Learning"
- **What it does**: LSTM and ConvLSTM models for daily fire danger over
  Greece. Hydra-config based, PyTorch Lightning. Specifically focuses on
  *interpretability* via integrated gradients & SHAP on fire-danger
  predictions.
- **Data scope**: Greece, 2009-2020, 1km daily, ERA5 + LAI + soil moisture +
  human-activity proxies (population density, distance to roads).
- **Architecture**: GreeceFireDataModule + LSTM_fire_model. Clean Hydra +
  PyTorch Lightning idiom that scales.
- **Verdict**: **BORROWABLE — interpretability stack**. Our v17 has feature
  importance bars but we don't run integrated gradients or SHAP at the
  per-cell-day level. This repo's interpretability scripts are the cleanest
  open implementation for fire ML and are directly portable to our LightGBM
  model via SHAP (which we already use for global importance but not for
  per-prediction explanation in the portal). Could power per-cell "why is
  this CRITICAL?" tooltips in our v3 portal Tab 1.

## 4. Orion-AI-Lab / televit — NOVEL

- **URL**: https://github.com/Orion-AI-Lab/televit
- **Stars / Forks**: 36 / 7
- **Last activity**: 2026-03-29 (ACTIVE)
- **Paper**: TeleViT — Teleconnection-driven vision transformers for improved
  long-term forecasting (arxiv linked in repo)
- **What it does**: Vision transformer that ingests *teleconnection indices*
  (ENSO, NAO, IOD) alongside spatial weather grids to forecast fire activity
  weeks-to-months ahead. Tests the hypothesis that global climate modes carry
  information about regional fire seasons.
- **Data scope**: Global, monthly, decade-scale climate indices + GFED.
- **Verdict**: **NOVEL — worth study but NOT for daily ops**. Our v17 is a
  next-day model; TeleViT is a months-ahead seasonal forecaster. The
  teleconnection idea is genuinely interesting for MP because Indian Ocean
  Dipole and ENSO are known to influence pre-monsoon dryness — could bolt on
  as a *seasonal* prior (not a daily feature). Park as future work; not a
  near-term win.

## 5. d-michail / firecastnet — NOVEL (paper-fresh)

- **URL**: https://github.com/d-michail/firecastnet
- **Stars / Forks**: 12 / 1
- **Last activity**: 2026-04-10 (ACTIVE)
- **Paper**: "FireCastNet: Earth-as-a-Graph for Seasonal Fire Prediction"
  (linked from SeasFire ecosystem)
- **What it does**: Graph neural network treating Earth as a connected
  system; node = grid cell, edges = climatological teleconnections. Uses
  the SeasFire datacube. Includes baselines (GRU, ConvGRU, ConvLSTM, UTAE)
  as fair comparisons in the same Lightning CLI harness.
- **Data scope**: Global seasonal, via SeasFire cube.
- **Verdict**: **NOVEL — keep on radar, not for production**. Below the
  50-star threshold but explicitly paper-linked and uses an interesting
  graph-based approach we have not tried. The graph topology (climate
  teleconnections as edges) is the genuinely new idea. Worth one read of
  the paper; the code is too research-staged to lift directly.

## 6. SeasFire / seasfire-datacube — BORROWABLE

- **URL**: https://github.com/SeasFire/seasfire-datacube
- **Stars / Forks**: 38 / 6
- **Last activity**: 2026-02-21 (ACTIVE)
- **Paper**: Zenodo dataset (doi:10.5281/zenodo.13834057), used by FireCastNet
- **What it does**: Open global Zarr datacube for seasonal fire modeling.
  17 years of climate + fire + vegetation variables. Designed as a shared
  benchmark substrate.
- **Data scope**: Global, 2001-2021, 0.25° (too coarse for our 2 km cells
  but good for context).
- **Verdict**: **BORROWABLE — the Zarr packaging recipe**. Same takeaway as
  Mesogeos: this is the clean open template for "how to publish a fire ML
  datacube." If we ever package our MP corpus for external researchers,
  copy this layout. Not useful for daily ops directly (resolution mismatch).

## 7. lautenberger / elmfire — BORROWABLE (numerical)

- **URL**: https://github.com/lautenberger/elmfire
- **Stars / Forks**: 59 / 42
- **Last activity**: 2026-04-19 (VERY ACTIVE — daily commits)
- **Paper**: Lautenberger 2013, Fire Safety Journal (foundational paper)
- **What it does**: Eulerian level-set fire spread model used operationally
  at Pyrecast.org for forecasting most large CONUS fires. Fortran core,
  Python orchestration. Production-grade Rothermel + level-set physics
  with realistic atmospheric coupling.
- **Data scope**: CONUS operational; landscape-level rasters in/out.
- **Verdict**: **BORROWABLE — physics validation**. Our spread predictor
  uses Cell2Fire + a custom level-set with the saturation fix
  (`level_set_saturation_fix.md`). ELMFIRE is the more mature, peer-reviewed
  level-set implementation and is currently in *daily production use*. Worth
  cross-referencing our base-ROS computation against ELMFIRE's. Their
  treatment of Byram-derived intensity vs sustainable ROS is the canonical
  reference. NOT recommended to replace Cell2Fire — instead use ELMFIRE
  source as a correctness oracle for our level-set physics.

## 8. mitrefireline / simfire (+ simharness) — NOVEL

- **URL**: https://github.com/mitrefireline/simfire
- **Stars / Forks**: 50 / 10 (simfire) + 18 / 1 (simharness)
- **Last activity**: 2026-04-12 (ACTIVE)
- **Paper**: MITRE Fireline org (no single paper but multiple workshop papers)
- **What it does**: Open-source wildfire simulator designed to be an *RL
  training environment* — paired with simharness which trains agents to
  fight wildfires (firebreak placement, suppression dispatch). Built on
  real landscape data.
- **Data scope**: CONUS landscapes, gym-style episodes.
- **Verdict**: **NOVEL — keep on radar for prescriptive engine**. Our
  prescriptive_engine.py currently uses heuristics. SimHarness shows what a
  RL-trained dispatch policy looks like. NOT borrowable today — our action
  space (patrol vs awareness vs dispatch at division level) is much smaller
  than theirs (continuous firebreak geometry). But if we ever want to learn
  optimal beat-level patrol routing under v17 forecasts, this is the
  reference implementation.

## 9. cell2fire / Cell2Fire — ALREADY USED

- **URL**: https://github.com/cell2fire/Cell2Fire
- **Stars / Forks**: 76 / 34
- **Last activity**: 2026-03-31 (ACTIVE)
- **Paper**: Pais et al, multiple Forest Ecology & Management publications
- **What it does**: Cell-based forest fire growth model; predecessor to the
  fire2a fork we already integrated.
- **Verdict**: **SKIP — already integrated** via fire2a/C2FSB; see
  `cell2fire_integration.md` memory note. Ceiling diagnosis already
  resolved 2026-04-08 (220 ha was true 24 h point-source, not a bug). No
  new borrowable signal.

## 10. bcgov / wps — BORROWABLE (operational stack)

- **URL**: https://github.com/bcgov/wps
- **Stars / Forks**: 65 / 10
- **Last activity**: 2026-04-16 (VERY ACTIVE — production system)
- **Paper**: None (operational government code)
- **What it does**: British Columbia Government's full Wildfire Predictive
  Services stack. FastAPI backend, React frontend, Postgres DB, Docker
  compose, codecov-tested. Powers C-HAINES, hourly/daily FWI, fire-danger
  forecasts that BC firefighters actually use. Production-grade.
- **Data scope**: British Columbia (similar scale to MP — sub-national
  government deployment).
- **Verdict**: **BORROWABLE — operational architecture patterns**. Our v3
  portal is good but bcgov/wps is the most directly comparable production
  fire-forecasting government deployment we'll find on GitHub. Specifically
  worth studying:
  (a) Their devcontainer + docker-compose setup (we're brittle on that).
  (b) Their alerting workflow (REST API + frontend handoff).
  (c) Their FWI calculator (cross-check our `compute_fwi.py` Open-Meteo
      patch against a peer-reviewed reference implementation).
  Don't borrow models; borrow the *deployment shape*.

## 11. pyronear / pyro-vision (org: pyronear) — BORROWABLE (alerting stack)

- **URL**: https://github.com/pyronear (umbrella org, 65 stars on
  pyro-vision, 27 on pyro-risks, 25 on pyro-api)
- **Stars / Forks**: 65 / 24 (pyro-vision)
- **Last activity**: 2026-04-17 (VERY ACTIVE — pyro-api, pyro-engine
  updated this month)
- **Paper**: Multiple workshop publications (Hi-Paris collab)
- **What it does**: Open-source umbrella for tower-camera based wildfire
  detection across France. Edge inference (Raspberry Pi), centralized
  alert API (FastAPI + Postgres), data pipelines (`pyro-risks` for risk
  modeling).
- **Data scope**: France-wide tower cameras, edge inference at scale.
- **Verdict**: **BORROWABLE — alert API + edge architecture**. Different
  modality (RGB camera vs satellite) but the *alert lifecycle* (detection
  → API → operator triage → resolution) is the same shape we need. Their
  pyro-api FastAPI patterns + alert state machine are directly portable
  to our portal backend. pyro-risks is also worth a read for their risk
  feature engineering on French weather.

## 12. project-araia / WildfireGPT — NOVEL

- **URL**: https://github.com/project-araia/WildfireGPT
- **Stars / Forks**: 17 / 7
- **Last activity**: 2026-03-30 (ACTIVE)
- **Paper**: npj Climate Action 2025 (open access, 19 July 2025)
- **What it does**: Multi-agent RAG system for wildfire hazard adaptation
  using GPT-4. Indexes climate-projection data + historical fire records
  and answers planner-style questions about wildfire risk under climate
  change.
- **Data scope**: US wildfire archive + downscaled climate projections.
- **Verdict**: **NOVEL — keep for citizen-portal layer**. Below 50 stars but
  paper-linked and recently published. Our v3 portal is operator-facing;
  WildfireGPT shows what a public-facing/long-form-question interface looks
  like. NOT useful for production prediction — useful as a *companion*
  layer for forest officers asking "why is risk elevated this week?" in
  natural language, backed by retrieval over our drift logs + validation
  reports. Don't fork; copy the architecture pattern.

## 13. HakamShams / LOAN — STUDY (paper-linked architecture)

- **URL**: https://github.com/HakamShams/LOAN
- **Stars / Forks**: 18 / 1
- **Last activity**: 2025-11-06
- **Paper**: IEEE TGRS 2023 (Shams Eddin et al, doi:10.1109/TGRS.2023.3285401)
- **What it does**: "Location-aware Adaptive Normalization" — a
  conditional batch-norm variant where the normalization parameters are
  predicted from spatial-context embeddings. Applied to FireCube dataset
  for daily wildfire-danger forecasting.
- **Data scope**: Global FireCube (similar to SeasFire scale).
- **Verdict**: **STUDY** — below 50 stars but paper-linked and the
  architectural idea is novel. Location-aware adaptive normalization could
  help our v17 in a specific way: MP has 87 forest divisions with very
  different local climates (Bundelkhand vs. Satpura vs. Vindhya). Standard
  batch-norm collapses these. LOAN's per-location norm parameters could be
  the right inductive bias if we ever swap LightGBM for a neural model. NOT
  applicable to LightGBM directly. Park as a candidate if/when we revisit
  v8-style neural ignition.

## 14. nachi-hebbar / Forest-Fire-Prediction-Website — SKIP

- **URL**: https://github.com/nachi-hebbar/Forest-Fire-Prediction-Website
- **Stars / Forks**: 150 / 165
- **Last activity**: 2026-02-21
- **What it does**: Flask + sklearn website predicting fire from
  oxygen/temperature/humidity inputs. The sole reason for 150 stars is it
  is a popular YouTube tutorial.
- **Verdict**: **SKIP**. Same tier as the already-rejected aravind-selvam.
  High stars but zero technical novelty over our v17. Listed only because
  star-count metric flags it; do not invest time.

## 15. Orion-AI-Lab / igarss24_DL4NH — BORROWABLE (educational)

- **URL**: https://github.com/Orion-AI-Lab/igarss24_DL4NH
- **Stars / Forks**: 31 / 4
- **Last activity**: 2025-09-08
- **Paper**: IGARSS 2024 Tutorial materials
- **What it does**: Hands-on tutorial for "Deep Learning Advances for
  Monitoring and Forecasting Natural Hazards". Notebooks covering wildfire
  + flood + landslide prediction with the Mesogeos / KuroSiwo data.
- **Verdict**: **BORROWABLE for onboarding**. Useful as a teaching reference
  if we onboard new collaborators on the EO + DL stack. Also a curated
  bibliography of recent papers in the space.

---

## Honorable Mentions (searched, evaluated, dismissed)

| Repo | Stars | Why dismissed |
|---|---|---|
| google-research/google-research (next_day_wildfire_spread sub-dir) | 35k overall | The fire sub-dir is a paper artifact (Huot et al 2022); useful as a known-good Earth Engine export pipeline but not a standalone repo. Already cited extensively in the WildfireSpreadTS paper. |
| cheng-kang/wildfire | 177 | False positive — JS comment plugin, unrelated. |
| AlirezaShamsoshoara/Reinforcement_Learning_Team_Q_learning... | 81 | UAV spectrum management, fire is incidental. |
| yueureka/WildFireDetection | 83 | Per-pixel U-Net detection on satellite — same task as our VanAagni v1.0 already shipped. |
| aiformankind/wildfire-dataset | 26 | Smoke/flame *image* datasets for vision detection, not predictive modeling. |
| OmdenaAI/DehradunIndiaChapter_ForestFirePredictionandEarlyWarningSystem | 7 | India-specific (Uttarakhand) but very early-stage; mostly EDA notebooks. Worth a 30-min skim only because India-specific repos are rare. |
| MatteoM95/CEMS-Wildfire-Dataset | 16 | Sentinel-2 image dataset for burn-scar segmentation, not predictive. |
| slinderman/pyhawkes (248 stars), HongtengXu/Hawkes-Process-Toolkit (117) | various | Generic Hawkes libraries — we already implemented our spatiotemporal Hawkes from scratch using cKDTree per `project_phase5_hawkes_win.md`; these libraries are designed for 1D event streams, not gridded fire data. |
| IBM/ImpactMesh | 12 | Multi-modal flood + fire dataset, but only 12 stars and very fresh; revisit in 6 months. |
| SusuXu-s-Lab/FLARE | 9 | LLM for *post*-wildfire evacuation decisions, not prediction. |

---

## Cross-Cutting Observations

1. **No India-specific production repo exists.** Omdena/Dehradun is the
   only India-tagged hit and is early-stage. MP-scale daily operational
   ignition forecasting via gradient boosting + Hawkes is, on this
   evidence, ours alone in the open-source landscape.

2. **No anthropogenic / behavioural data integration in any starred repo.**
   Every serious project (Mesogeos, WildfireSpreadTS, FireCastNet,
   wildfire_forecasting) uses only weather + vegetation + topo + ignition
   history. None integrate village-level human activity, NTFP collection
   schedules, or patrol logs. This validates our memory finding
   (`feedback_gdelt_district_centroid_geocoding.md`): the data does not
   exist openly. Our v17 ceiling is the open-source ceiling.

3. **The Hawkes-on-fire combination is rare in starred code.** The 248-star
   pyhawkes and 117-star Hawkes-Process-Toolkit are general Hawkes libs;
   no fire-specific Hawkes implementation surfaced above 5 stars. Our
   spatiotemporal Hawkes (Phase 5 v9 win, +11pp) appears to be a
   genuinely original combination in production fire ML.

4. **Multi-modal fusion is the dominant frontier.** WildfireSpreadTS (23
   channels), Mesogeos (17 variables), SeasFire (similar), all push the
   "more modalities" hypothesis. v17's 111 features is comparable in
   *count* but our modality breadth is narrower. The strongest borrowable
   single feature class missing from v17 vs these benchmarks: **drought
   indices beyond FWI** (PDSI, EDDI) and **lightning density**, both of
   which Mesogeos and WildfireSpreadTS include.

5. **Production engineering quality varies wildly.** bcgov/wps and pyronear
   are the only two with truly production-grade engineering (CI, code
   coverage, devcontainers, OpenAPI specs). Our v3 portal is in the same
   tier as these — a credible reason to publish our work.

---

## Recommended Next Actions (in priority order)

1. **Read Mesogeos paper + clone** to extract their interpretability +
   per-cell-day attribution scripts. Borrow for our v3 portal Tab 1
   tooltips. (~1 day)

2. **Clone WildfireSpreadTS** and benchmark our spread tracker (Muhurta
   ROS-UNet) against their post-bug-fix UNet on their dataset. Will
   reveal whether our smooth_l1 fix is enough or if we have an
   architectural gap. (~2 days)

3. **Read elmfire source** for level-set base-ROS reference. Compare
   against our `level_set_saturation_fix.md` Byram-derived patch.
   Probably confirms our fix; may surface edge cases. (~half day)

4. **Skim bcgov/wps deployment + alerting code** for portal architecture
   patterns we should adopt before public release. (~half day)

5. **Park** TeleViT, FireCastNet, LOAN as future-work references. None
   address our daily-ignition task; they address seasonal forecasting
   or normalization tricks for neural models we are not currently
   training.

6. **Do not** invest in any of the Algerian-dataset / Kaggle-California
   tier projects. The honorable mentions table above is the audit trail.
