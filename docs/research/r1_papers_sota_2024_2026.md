# R1 — Wildfire Ignition Prediction SoTA 2024-2026: 12 Genuine New Candidates

**Author:** Research agent
**Date:** 2026-04-19
**Audience:** v17 production team (MP fire EWS, JwalaNetra)
**Purpose:** Identify 2024-2026 academic papers that present **genuinely new** ignition-prediction approaches relative to the v17 rejected list (VLM/CLIP/SAR/GFS/fuel/hybrid-Bayes/origination-2-model/calendar-tier/GDELT/S2-dNBR-peak-green/foundation-TS), with explicit fit-to-MP and effort estimates.

## Executive summary

After scanning Nature, Scientific Reports, ESSD, NHESS, ScienceDirect (Ecological Informatics, Remote Sensing of Environment), arXiv (cs.LG / cs.CV / stat.AP), AGU JGR-ML, ICLR-ML4RS, NeurIPS-CCAI 2024-2025, and recent Springer/Wiley journals, I found 12 candidates worth a one-page consideration each. Of these, **only 3 plausibly transfer to the MP low-Hawkes / new-outbreak gap** and pass the "won't repeat the rejected list" filter:

1. **FPA-FOD-Attributes (Pourmohamad et al., ESSD 2024)** — a 270-attribute *feature recipe*, not a model. Lets us audit whether v17's anthropogenic feature stack is incomplete (specifically: GDP per capita, social vulnerability, fire-station evacuation time, wildland-urban interface metrics — none of which we currently use). Cheap to test (days, not weeks).
2. **Gelabert et al., NHESS 2025** — pan-European human-ignition assessment at 100 m using WUI / WAI / WGI distance-to-interface features and an explicit autocorrelation-control RF. Their feature engineering (3 distinct interface types, not just "distance to road") is the only paper in the set that gives a clean playbook for the low-Hawkes problem. AUC 0.70-0.89 across regions; methodology is directly portable to MP's village-forest interface.
3. **Causal GNN for Wildfire (Zhao et al., ICLR 2024 ML4RS)** — PCMCI-derived causal adjacency on top of GNN. The novelty for us is *removing spurious correlation links* before model training, which is a structurally different defence against the Hawkes-dominance trap than ranking blends (which we already proved fail). Worth a 2-week pilot.

The other 9 candidates are listed for completeness with honest "probably won't transfer" notes. **No paper in 2024-2026 reports a method that empirically beats LightGBM on a low-Hawkes / cold-start ignition benchmark in dry deciduous biomes.** The structural problem is not solved upstream of us.

---

## Candidate 1: FPA-FOD-Attributes — 270-attribute feature recipe for human-caused ignition

| Field | Value |
|---|---|
| Title | Physical, social, and biological attributes for improved understanding and prediction of wildfires: FPA FOD-Attributes dataset |
| Authors | Pourmohamad et al. |
| Year / Venue | 2024, Earth System Science Data (ESSD) Vol. 16, p. 3045 |
| Link | https://essd.copernicus.org/articles/16/3045/2024/ |

**Mechanism:** Augments the 2.3M-record FPA-FOD US wildfire database with 270 covariates spanning 4 categories: physical (weather, topography, infrastructure), biological (land cover, NDVI), social (population density, **Social Vulnerability Index full sub-components, Climate & Economic Justice Screening tool, GDP per capita, global human modification index, distance to roads/trails — primary/secondary/local separately, fire-station proximity at 1/5/10/20 km, evacuation time to medical facilities**), and administrative.

**Reported metric:** None — this is a dataset paper. 4-step validation matched all 100 sampled fires to source values.

**Fit to MP:** STRONG conceptual fit, MEDIUM data fit. The novelty for v17 is the social vulnerability + economic distress + fine-grained road class features — most of these have OSM / Indian Census equivalents we have *not* assembled. Fire-station / NTFP-collection-centre proximity (Indian analogue) is a plausible low-Hawkes feature.

**Why it might transfer:** Anthropogenic ignition is the dominant MP driver; the v17 stack has roads + population but is missing economic-distress, sub-class road, and protective-infrastructure proximity. These features specifically correlate with the cold-start regime (poor villages near forest fringe with no fire-station coverage).

**Why it might not:** The dataset itself is US-only. We must rebuild the equivalent feature stack from Indian sources (Census 2011, MoSPI district economic data, NHAI road network, OSM). The published validation does not include any predictive benchmark, so we have no apples-to-apples uplift estimate.

**Effort:** **3-5 days.** Identify ~20 highest-IG analogues, query OSM + Indian Census APIs, recompute at 2 km × week, run LightGBM SHAP audit. If any single feature contributes > 1% gain on low-Hawkes recall in cross-validated SHAP, escalate to a v18 candidate.

**Novelty:** **NEW.** Not on the rejected list. Distinct from GDELT (which was article-level; this is structural-demographic).

---

## Candidate 2: Pan-European human-ignition likelihood — Gelabert et al. NHESS 2025

| Field | Value |
|---|---|
| Title | Assessing human-caused wildfire ignition likelihood across Europe |
| Authors | Gelabert et al. (12 co-authors) |
| Year / Venue | 2025, Natural Hazards and Earth System Sciences (NHESS) Vol. 25, p. 4713 |
| Link | https://nhess.copernicus.org/articles/25/4713/2025/ |

**Mechanism:** Random Forest at 100 m resolution on 5 European pilot sites with 1000 bootstrap realisations each. Three distinct *interface* features (not just road distance): distance to **WUI** (wildland-urban), **WAI** (wildland-agricultural), **WGI** (wildland-grassland). Adds an Autocorrelation Control (AC) term using Euclidean Distance Features to debias spatially clustered training labels. Site-specific and pooled "full model" both reported.

**Reported metric:** AUC 0.70-0.89 per pilot; full model 0.81 globally / 0.61-0.85 locally. Fire-weather dominates north; **human factors dominate Mediterranean** (the regime that most resembles MP).

**Fit to MP:** STRONG. The wildland-agricultural interface is precisely where ~90 % of MP fires originate (NTFP collection, stubble burn, land clearing). v17 has a generic "distance to settlement" but does not distinguish WUI vs WAI vs WGI. The interface-typology features are computable from existing ESA WorldCover + DigitalGlobe building footprints + MP Census village shapefiles.

**Why it might transfer:** This is the only 2024-2026 paper that explicitly handles the same regime (Mediterranean dry summer, agricultural fringe ignitions, low fire density per cell). The autocorrelation control is also a quiet correction we should consider given MP's heavily clustered Hawkes signal.

**Why it might not:** AUC 0.81 is below v17's effective AUC. We must trust that the *feature-engineering* logic transfers even if the model doesn't. Mediterranean fuel structure differs (chaparral vs teak/sal/tendu); the WUI taxonomy may need re-derivation from MP-specific village morphology.

**Effort:** **1-2 weeks.** (a) Derive WUI/WAI/WGI from MP WorldCover + Census + OSM at 100 m, (b) aggregate to 2 km cell with multiple radial statistics, (c) add as v17 candidate features, (d) low-Hawkes-only ablation.

**Novelty:** **NEW.** v17 has *settlement distance* but not the typology-stratified interface logic. Distinct from GDELT (no news data) and from the South Korea paper (no local linear-regression GWR component, just RF).

---

## Candidate 3: Causal GNN for Wildfire Danger — Zhao et al. ICLR 2024 ML4RS

| Field | Value |
|---|---|
| Title | Causal Graph Neural Networks for Wildfire Danger Prediction |
| Authors | Zhao, Prapas, Karasante, Xiong, Papoutsis, Camps-Valls, Zhu |
| Year / Venue | 2024, ICLR ML4RS workshop (also arXiv 2403.08414) |
| Link | https://arxiv.org/abs/2403.08414 |

**Mechanism:** PCMCI causal-discovery algorithm derives a *causal adjacency matrix* over input variables; this matrix replaces the dense adjacency in a GNN. The intent is to remove **spurious correlation edges** so that highly-correlated covariates don't dominate the message-passing.

**Reported metric:** "Superior performance" forecasting wildfire patterns in European boreal + Mediterranean biomes. Workshop paper — exact numbers thin in the public version.

**Fit to MP:** MEDIUM. The novelty addresses *exactly* our v17 pathology: weather + Hawkes correlate strongly with the BA-tier label and dominate the gradient, leaving anthropogenic signal as residual. Causal pruning of edges may give the rare-event drivers a louder voice.

**Why it might transfer:** This is the only 2024-2026 method that targets the *correlated-covariate-dominance* problem at architecture level (not feature level, which is what hybrid Bayesian ranking attempted and failed). PCMCI is well-documented (Tigramite library). The pipeline is feature-domain-agnostic.

**Why it might not:** Workshop paper, not full venue. GNN architecture imposes a different inductive bias than LightGBM; MP has only ~21 K GOLD+SILVER labels, which may be too few for stable GNN training (we saw this in v17.2 Hawkes regression). Likely needs to be hybridised: PCMCI-pruned feature set fed back into LightGBM, not full GNN replacement.

**Effort:** **2 weeks.** (a) Run PCMCI on 111 v17 features against label, (b) drop edges with conditional-independence p > 0.05, (c) retrain v17 LightGBM with surviving feature subset and a *causally-spurious feature mask* applied during inference, (d) low-Hawkes ablation. If no gain, kill quickly.

**Novelty:** **NEW.** Distinct from hybrid Bayesian ranking (which was a *posterior* blend, not a *prior* feature-selection); distinct from soft-ensemble (which was an output blend).

---

## Candidate 4: Predicting wildfires triggered by human-caused ignition (S. Korea) — Heo & Ahn 2026

| Field | Value |
|---|---|
| Title | Predicting wildfires triggered by human-caused ignition: A spatial framework integrating AI models |
| Authors | Heo, Ahn |
| Year / Venue | 2026, Ecological Informatics Vol. 94 |
| Link | https://www.sciencedirect.com/science/article/pii/S1574954126000464 |

**Mechanism:** Three-model fusion (Random Forest + GAM + GWR) on 3,703 Korean human-caused fires 2001-2025. Identifies operational thresholds (e.g. ignition probability spikes below 15 % humidity, NDVI 0.2-0.4, wind ~15 m/s, building proximity).

**Reported metric:** RF AUC 0.829. High-risk zone (≥0.70) covers 16.96 % of S. Korea.

**Fit to MP:** OVERLAPPING. The framework is interesting but each component overlaps something we have. RF ≈ what v17 uses. GAM is a thresholding tool — useful for *interpretability* not for *recall lift*. GWR is geographically-weighted regression — risk of being just a spatial-prior re-skin (and we've already shown spatial reweighting via Hybrid Bayesian λ-blend FAILS on MP).

**Why it might not transfer:** AUC 0.829 < v17 effective AUC. The "novelty" is GAM-derived thresholds + GWR — the GWR component is *exactly* the kind of geographically-adaptive blending that already failed for us (the rejected list explicitly calls out hybrid Bayesian ranking variants).

**Effort:** GAM threshold extraction = 1 day; GWR = 1-2 weeks but high probability of duplicating our rejected blend results.

**Novelty:** **OVERLAPPING.** GWR is conceptually adjacent to the failed adaptive λ-blend.

---

## Candidate 5: Geospatial Awareness Layer for LLM Wildfire Agents — Chen et al. arXiv 2025

| Field | Value |
|---|---|
| Title | Empowering LLM Agents with Geospatial Awareness: Toward Grounded Reasoning for Wildfire Response |
| Authors | Chen, Li, Ma, Hu, Zhu, Deng, Yu |
| Year / Venue | 2025-10, arXiv 2510.12061 |
| Link | https://arxiv.org/abs/2510.12061 |

**Mechanism:** A "Geospatial Awareness Layer" wrapper around LLM agents that auto-retrieves infrastructure / demographic / terrain / weather data from external geodatabases and feeds it as a *contextual perception script* to the LLM. Targeted at *response* (resource allocation), not *prediction*.

**Reported metric:** "Geospatially grounded agents outperform baselines" on real wildfire scenarios — abstract gives no quantitative numbers.

**Fit to MP:** WEAK for ignition prediction (this is a downstream-decision tool, not a predictor). MEDIUM for the v3 portal dispatcher tab, where it could replace our hand-coded action-recommendation logic.

**Why it might not transfer to ignition:** It is not an ignition model. It is a wildfire-response orchestration tool. Out of scope for the low-Hawkes problem.

**Effort:** Not applicable for ignition uplift. 1 week if we instead rebuild the v3 dispatcher recommendations on top of the GAL pattern.

**Novelty:** **NEW** but **WRONG TASK** for the brief.

---

## Candidate 6: FireCastNet — Earth-as-Graph for Seasonal Fire Prediction — Michail et al. 2025

| Field | Value |
|---|---|
| Title | FireCastNet: earth-as-a-graph for seasonal fire prediction |
| Authors | Michail, Davalas, Chafis, Panagiotou, Prapas, Kondylatos, Bountos, Papoutsis |
| Year / Venue | 2025, Scientific Reports / arXiv 2502.01550 |
| Link | https://www.nature.com/articles/s41598-025-30645-7 |

**Mechanism:** 3D-conv encoder + GraphCast-based GNN over the SeasFire datacube (59 vars, 0.25° resolution, 8-day cadence). Predicts global burned area patterns up to 6 months ahead.

**Reported metric:** Outperforms GRU/Conv-GRU/Conv-LSTM/U-TAE/TeleViT baselines on global BA forecasting.

**Fit to MP:** WEAK. Resolution is **0.25° (~28 km)** and cadence **8 days**, vs our 2 km × week. The model is built for *seasonal* forecasting, which is the wrong horizon. The 6-month-ahead skill, even if real, gives us at best a March-prior-November signal — which we already approximate with phenology + climate priors.

**Why it might not transfer:** Resolution mismatch is fundamental. SeasFire human-related variables are mostly Population × LULC, which v17 already has at 2 km. The GNN architecture would need a complete reinit at our resolution and we'd lose the foundation-pretraining advantage.

**Effort:** > 4 weeks for any meaningful pilot.

**Novelty:** **OVERLAPPING** in both data (population/LULC are the human vars) and method (GNN with no anthropogenic-specific structure).

---

## Candidate 7: Global lightning-ignited wildfires (explainable ML) — Pérez-Invernón et al. Sci Reports 2025

| Field | Value |
|---|---|
| Title | Global lightning-ignited wildfires prediction and climate change projections based on explainable ML models |
| Authors | Pérez-Invernón et al. |
| Year / Venue | 2025, Scientific Reports / arXiv 2409.10046 |
| Link | https://www.nature.com/articles/s41598-025-92171-w |

**Mechanism:** Separate predictive models for lightning-caused vs anthropogenic wildfires globally, with SHAP-based explainability. The explicit insight: anthropogenic and natural fires need *dedicated* fire-weather indices.

**Fit to MP:** WEAK as a model, MEDIUM as a *philosophy*. MP has near-zero lightning ignition (dry season is pre-monsoon); we're already implicitly anthropogenic-only. This paper validates that decision but doesn't give us a new method.

**Effort:** Read paper (1 hour), borrow the SHAP audit pattern (already done), nothing else.

**Novelty:** **DUPLICATE.** MP is already a single-cause regime; the lightning/anthro split is a US/Europe insight.

---

## Candidate 8: WildfireGPT — Tailored LLM for Wildfire Analysis — Xie et al. NeurIPS-CCAI 2024

| Field | Value |
|---|---|
| Title | WildfireGPT: Tailored Large Language Model for Wildfire Analysis |
| Authors | Xie et al. (Argonne / U. Penn) |
| Year / Venue | 2024, NeurIPS Climate Change AI workshop / arXiv 2402.07877 |
| Link | https://arxiv.org/abs/2402.07877 |

**Mechanism:** Multi-agent RAG over wildfire literature + FWI projections + 2015-2023 Wildland Fire records + paleofire DB + Census poverty/housing data. Designed as an *advisory* / report-generation tool.

**Reported metric:** "Performs well in correctness and relevance"; the follow-up evaluation paper (Springer Nat Hazards 2025) explicitly says it lacks the "specialized training, real-time data integration, and algorithmic precision required for reliable wildfire forecasting."

**Fit to MP:** WEAK for ignition. Useful only as a *user-facing assistant* on top of v17 outputs — but the v3 portal already serves that need with structured cards.

**Effort:** Not worth pursuing for predictive uplift.

**Novelty:** **DUPLICATE** — falls into the same VLM/LLM rejected family (LLaVA-7b, CLIP) for predictive use. Different deployment surface, same fundamental "LLMs don't predict satellite-physical signal" failure mode.

---

## Candidate 9: Spatial Uncertainty Quantification for Wildfire — Kondylatos et al. 2025

| Field | Value |
|---|---|
| Title | Spatial Uncertainty Quantification in Wildfire Forecasting for Climate-Resilient Emergency Planning |
| Authors | Kondylatos et al. |
| Year / Venue | 2025-10, arXiv 2510.09666 |
| Link | https://arxiv.org/abs/2510.09666 |

**Mechanism:** MC dropout + Deep Ensembles + BNNs to quantify epistemic uncertainty around fire-spread predictions. Identifies 20-60 m uncertainty buffer zones.

**Fit to MP:** WEAK for ignition (this is a *spread* tool); MEDIUM for v17 confidence-banded outputs already on the v3 portal. Doesn't address the cold-start gap.

**Effort:** 1 week to add MC-dropout-style stochastic LightGBM (bagging) for confidence intervals.

**Novelty:** **OVERLAPPING.** Confidence ring on the v3 portal already provides per-cell band; deep ensembling would refine but not solve the new-outbreak recall gap.

---

## Candidate 10: TS-SatFire — multi-task satellite time-series for fire — Yang et al. Sci Data 2025

| Field | Value |
|---|---|
| Title | TS-SatFire: A Multi-Task Satellite Image Time-Series Dataset for Wildfire Detection and Prediction |
| Authors | Yang et al. |
| Year / Venue | 2025, Scientific Data |
| Link | https://www.nature.com/articles/s41597-025-06271-3 |

**Mechanism:** Multi-task EO benchmark (detection + prediction) for foundation-model training.

**Fit to MP:** WEAK directly. Useful only as a *cross-region pretraining corpus* for any future foundation-model pilot — but Prithvi-EO 600M already failed on our task.

**Effort:** > 2 weeks just to load and align with our LightGBM stack.

**Novelty:** **OVERLAPPING** with the rejected Prithvi-EO line.

---

## Candidate 11: Granger-Causal Inference for Climate Attribution — Hoffman et al. arXiv 2024

| Field | Value |
|---|---|
| Title | Granger causal inference for climate change attribution |
| Authors | Hoffman et al. |
| Year / Venue | 2024, arXiv 2408.16004 |
| Link | https://arxiv.org/abs/2408.16004 |

**Mechanism:** Formal Granger-causal framework for trend / event attribution. Avoids expensive counterfactual climate-model runs.

**Fit to MP:** WEAK as a predictor. MEDIUM as a downstream attribution tool (e.g., "what fraction of 2026-04-22 alert spike is attributable to anthropogenic vs climatological drivers?"). Does not directly add ignition recall.

**Effort:** 1-2 weeks for an attribution post-hoc layer; nil for prediction uplift.

**Novelty:** **NEW** as a downstream tool; **WRONG TASK** for the recall gap.

---

## Candidate 12: State of Wildfires 2024-2025 — ESSD Copernicus

| Field | Value |
|---|---|
| Title | State of Wildfires 2024-2025 |
| Authors | Jones et al. (multi-author consortium) |
| Year / Venue | 2025, ESSD Vol. 17 p. 5377 |
| Link | https://essd.copernicus.org/articles/17/5377/2025/ |

**Mechanism:** Annual global fire-season summary with attribution analyses (e.g., "extreme fire weather in NE Amazonia 30-70× more likely under climate change"). Counterfactual scenarios driven by natural-only forcing.

**Fit to MP:** WEAK as a predictor. Useful as background literature only; no methodological contribution at our spatial / temporal scale that we don't already have.

**Novelty:** **DUPLICATE** of climate-attribution literature; not an ignition-prediction method.

---

## Final ranked table (top → bottom by fit × feasibility for the low-Hawkes / new-outbreak gap)

| Rank | Candidate | Novelty | Effort | Fit to MP | Decision |
|------|-----------|---------|--------|-----------|----------|
| 1 | **FPA-FOD-Attributes 270-feature recipe** (Pourmohamad 2024 ESSD) | NEW | 3-5 days | STRONG | **PILOT** — Indian-equivalent stack from OSM + Census 2011 + MoSPI + NHAI; SHAP audit on low-Hawkes subset |
| 2 | **Pan-EU human-ignition WUI/WAI/WGI** (Gelabert 2025 NHESS) | NEW | 1-2 weeks | STRONG | **PILOT** — derive 3-class interface features at 100 m for MP; aggregate to 2 km; ablation on low-Hawkes cells |
| 3 | **Causal GNN / PCMCI feature pruning** (Zhao 2024 ICLR-ML4RS) | NEW | 2 weeks | MEDIUM | **PILOT (if 1 + 2 fail)** — PCMCI on v17's 111 features, prune spurious edges, retrain LightGBM |
| 4 | LLM Geospatial Awareness Layer (Chen 2025 arXiv) | NEW | 1 week | LOW (wrong task) | DEFER — re-evaluate for v3 portal dispatcher only |
| 5 | Spatial UQ for Wildfire (Kondylatos 2025) | OVERLAPPING | 1 week | LOW | DEFER — confidence ring already serves portal need |
| 6 | S. Korea RF+GAM+GWR (Heo 2026 Ecol Inf) | OVERLAPPING | 1-2 weeks | LOW (overlaps failed blend) | REJECT — GWR component duplicates rejected hybrid-Bayes blend |
| 7 | WildfireGPT (Xie 2024 NeurIPS-CCAI) | DUPLICATE | n/a | LOW | REJECT — already-rejected LLM-on-fire family |
| 8 | FireCastNet (Michail 2025 Sci Rep) | OVERLAPPING | > 4 weeks | LOW (resolution mismatch) | REJECT |
| 9 | TS-SatFire benchmark (Yang 2025 Sci Data) | OVERLAPPING | > 2 weeks | LOW | REJECT — Prithvi-EO line already failed |
| 10 | Granger-causal attribution (Hoffman 2024 arXiv) | NEW | 1-2 weeks | LOW (downstream not predictive) | DEFER — attribution tool, not predictor |
| 11 | Lightning-ignited fire prediction (Pérez-Invernón 2025 Sci Rep) | DUPLICATE | n/a | LOW (MP has no lightning regime) | REJECT |
| 12 | State of Wildfires 2024-25 (Jones 2025 ESSD) | DUPLICATE | n/a | LOW | REJECT — review article |

---

## Recommended next steps (concrete)

1. **Week 1 — Pilot 1 (FPA-FOD-Attributes Indian-equivalent).**
   - Pull OSM (highway / building / amenity), Indian Census 2011 village shapefile, MoSPI district SDP per capita, NHAI road class layer.
   - Build the ~20 highest-IG analogue features at 2 km × week.
   - Run SHAP on the existing v17 LightGBM with these features appended.
   - **Kill criterion:** if no single new feature contributes ≥ 1 % low-Hawkes recall in 5-fold CV, stop.

2. **Week 2-3 — Pilot 2 (WUI/WAI/WGI typology).**
   - Derive 3 interface masks from ESA WorldCover 10 m + MP village polygons.
   - Compute distance + density at 100 m, aggregate to 2 km with mean / min / area-fraction statistics.
   - Append to v17 candidate set; full retrain; low-Hawkes ablation.

3. **Week 4-5 — Pilot 3 (Causal feature pruning, only if 1 + 2 produce sub-1pp lifts).**
   - PCMCI causal-discovery on the 111 v17 features against BA-tier label.
   - Mask spurious edges; retrain.

4. **Hard rule:** none of the above changes how we currently rank — we continue to ship v17. These are *additive* features / *replacement* feature subsets, not architecture rewrites.

---

## Honest summary

**The 2024-2026 academic literature does not contain a published method that empirically beats LightGBM on the new-outbreak prediction task in dry-deciduous biomes at 2 km resolution.** Every credible improvement either (a) targets fire spread / response rather than ignition, (b) targets seasonal / global rather than weekly / cell scale, or (c) is a method that already lost to v17 in our internal trials (CLIP, foundation EO, hybrid Bayesian blends). The genuine remaining headroom is in **anthropogenic feature engineering** — specifically socio-economic distress proxies, fine-grained interface typology (WUI vs WAI vs WGI), and protective-infrastructure proximity. These are days-not-weeks of work and pose minimal risk to v17 as production.
