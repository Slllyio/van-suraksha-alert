# R3 — Anthropogenic Ignition Prediction Methods & Data Sources

**Date**: 2026-04-19
**Author**: Research scan (deep literature + Indian govt data audit)
**Trigger**: v17 ceiling at R@5%=47.41% (BA-tiered) / 22.7% (DBSCAN). 77% of new outbreaks fall in low-Hawkes cells where the model is near-random. Visual-precursor path (VLM/CLIP/dNBR delta) is dead. Need data **outside** the current satellite-weather feature set.
**Mandate**: Find data sources and modelling methods plausibly additive to v17 for anthropogenic ignition in MP dry deciduous (NTFP/festival/agri-clearing fires).

---

## Executive framing

The literature converges on one consistent finding: **for human-caused fires, distance-to-roads, distance-to-settlements, population density, land-use patches and (where available) socio-economic indices are the dominant predictors** — far stronger than weather (Janiec; Vilar; NHESS 2025 Europe-wide; the 2026 Upper-Ravi Himalaya GeoAI). v17 already encodes the top three of these as static rasters. The marginal gains the literature reports come from **temporal animation** of human activity (mobility, market, calendar) and **finer-scale settlement geometry** than what static distance-to-village can encode.

Honest bound from prior art: even the best Indian-Himalaya GeoAI stack (Upper Ravi 2026 study, ensemble of RF+XGBoost+LightGBM+CatBoost+stacking, 16 anthropogenic+biophysical features) hits AUC=0.95 — but on a much smaller AOI with a richer label set. Whether that translates to MP statewide R@5% uplift is unproven. Realistic best-case for any single new feature class on top of v17: **+1 to +3 pp** on R@5%. The "+10 pp" gap to a hypothetical 60% R@5% model probably requires **two or three** of these in combination.

---

## A. Anthropogenic ignition modelling literature

### A1. NHESS 2025 — "Assessing human-caused wildfire ignition likelihood across Europe"
- **Source**: NHESS 25:4713, 2025 (open access)
- **What it offers**: Pan-European RF+GAM+GWR ensemble on 3,703 georeferenced human-caused wildfires (2001–2025) with high-resolution climatic, land-use, vegetation, and demographic data. Reports AUC=0.829 with explicit feature decomposition; importantly, isolates which **human-mobility / land-use proxies survive** when seasonality and weather are controlled. Their feature ranking is directly portable as a "what should v18 try next" checklist.
- **Accessibility**: Free (Copernicus open access). Code repo public.
- **MP-specific?**: No — Europe. But methodology and feature decomposition transferable.
- **Estimated uplift**: +1.0 pp R@5% (mostly methodological — confirms feature ranking).
- **Effort**: 2 days to read, replicate feature list, port relevant features.

### A2. Upper Ravi Himalaya GeoAI Framework (Scientific Reports 2026)
- **Source**: Nature Sci Reports s41598-026-46924-w
- **What it offers**: First explicit **Indian Himalaya** GeoAI for wildfire susceptibility. 16 conditioning factors mixing biophysical+anthropogenic. Stacking ensemble (RF+XGB+LGBM+CatBoost) → AUC=0.95. Confirms that for Indian dry-deciduous-adjacent terrain, **anthropogenic factors outrank climate**. SHAP plots in supplement give a defensible "expected feature importance ordering" we can cross-check v17 against.
- **Accessibility**: Free (Nature OA).
- **MP-specific?**: Himalayan, not central-Indian deciduous, but closer than Europe. NTFP-economy parallels.
- **Estimated uplift**: +1.5 pp R@5% as a feature-engineering benchmark; potentially +2–3 pp if their stacking architecture beats single-LGBM v17.
- **Effort**: 3–5 days to replicate feature stack with our covariates.

### A3. Down-To-Earth Dewas reportage + MP forest-fire socio-fire literature
- **Source**: DTE 2025 ("forests fires move with people, not weather"), MPSFRI Jabalpur, ResearchGate "Forest Fire Characterization MP"
- **What it offers**: **Qualitative ground truth** that in Dewas (one of MP's biggest tendu producers) surface fires ignite 5–6 weeks **before** the official tendu collection season opens, in the exact patches that will be harvested. Mahua-base fires peak Mar–Apr. This is the empirical foundation for any tendu-zone × calendar interaction feature.
- **Accessibility**: Free.
- **MP-specific?**: Yes — Dewas + statewide.
- **Estimated uplift**: 0 directly (it's qualitative), but it **redirects** what features to engineer. We already have a tendu-zone proxy and Mahua kernel; what we don't have is the **5-week pre-collection lead window** as an interaction.
- **Effort**: 4 hours (read + design 1–2 derived features).

---

## B. Human-activity data sources potentially usable for MP

### B1. Meta High Resolution Settlement Layer (HRSL) — 30m population
- **Source**: research.facebook.com / HDX / AWS Open Data
- **What it offers**: 1-arcsec (~30 m) population grid for India, built from DigitalGlobe imagery + computer-vision-detected building footprints, proportionally allocated from Census 2011 totals. **At 30 m vs WorldPop's 100 m, the forest-edge population gradient is ~10× sharper.** Could materially improve our distance-to-settlement and population-pressure features at the 2km cell because we'd be aggregating real building footprints, not interpolated census totals.
- **Accessibility**: Free, public. ⚠️ **No longer updated as of 2024** — we get the historical snapshot only, but for slow-changing rural settlement geometry that's tolerable.
- **MP-specific?**: India coverage included.
- **Estimated uplift**: +1 to +2 pp R@5% — direct replacement for our distance-to-settlement layer with a sharper one. Recomputed `pop_within_2km` / `built_fraction` features should be additive even after dist-to-settlement saturates.
- **Effort**: 1 day (download + zonal stats over 2 km cells).

### B2. WorldPop India 100m gridded population — yearly 2015–2030
- **Source**: hub.worldpop.org / GEE WorldPop_GP_100m_pop
- **What it offers**: **Time-varying** 100m population (yearly to 2030 projections). Coarser than HRSL but updated annually — gives the **year-over-year demographic pressure** signal HRSL cannot. Best used jointly with HRSL: HRSL for static high-res building footprints, WorldPop for inter-annual change.
- **Accessibility**: Free, GEE-native (server-side processing easy).
- **MP-specific?**: Yes.
- **Estimated uplift**: +0.5 pp marginal on top of HRSL.
- **Effort**: Half-day in GEE.

### B3. Dynamic World V1 — 10 m monthly land-cover change
- **Source**: Google/WRI, GEE GOOGLE/DYNAMICWORLD/V1
- **What it offers**: Per-pixel probability of 9 LULC classes (incl. **bare ground, crops, built, grass**) at 10 m every Sentinel-2 revisit (5–10 days). For anthropogenic ignition, the **bare-ground probability rising in the 4–8 weeks pre-fire** in cropland-adjacent forest is a candidate signature for slash-and-burn / agricultural clearing. We tested raw S2 dNBR/BSI and got null; Dynamic World aggregates Sentinel-2 with a trained classifier and may see what raw bands miss. This is the **missing temporal animation** of land use that complements static settlement layers.
- **Accessibility**: Free, GEE-native.
- **MP-specific?**: Yes (global).
- **Estimated uplift**: +1 to +3 pp R@5% — speculative, but unlike VLM/CLIP this is a **trained classifier** with known performance on bare-ground detection. Worth a focused test on the **low-Hawkes cells specifically** (where v17 gap is).
- **Effort**: 2–3 days (build per-cell rolling probability features for 4 LULC classes, Δ12-week, Δ4-week).

### B4. AgMarkNet — daily mandi prices for tendu / mahua / kendu
- **Source**: agmarknet.gov.in + data.gov.in API
- **What it offers**: Daily wholesale modal/min/max prices from regulated MP mandis for forest-collected commodities. Realised NTFP prices in February–April should correlate with collection intensity — and therefore with the Dewas mechanism above. We already tested **synthetic** NTFP price proxies; this is the **real** signal.
- **Accessibility**: Free, public API. ⚠️ **Coverage caveat**: tendu and mahua are tribal-economy commodities, mostly procured through state tendering (LAMPS/MFP Federation), NOT mandis — so AgMarkNet coverage of these specifically is sparse. The pricing signal that DOES exist on mandis may lag by weeks. Verify before committing.
- **MP-specific?**: Yes.
- **Estimated uplift**: +0.5 to +1.5 pp **if** coverage exists; very plausibly 0 if MFP-Fed handles all tendu off-mandi (likely scenario).
- **Effort**: 1 day to verify coverage; if good, 2 days to build features.

### B5. SHRUG / DataMeet Census 2011 village polygons
- **Source**: docs.devdatalab.org SHRUG v2.1 / projects.datameet.org / India Geodata
- **What it offers**: Open shapefile of all 600,000+ Census 2011 villages of India + 600k+ habitation/hamlet point locations (PMGSY + National Habitation Survey). At MP-statewide scale, this gives us **per-cell village count, mean village population, area-weighted SC/ST fraction, area-weighted literacy rate, and forest-dependency flag** as static features. Distance-to-nearest-village is a degenerate feature; **village density and demographics within 2 km** is much richer.
- **Accessibility**: Free (ODbL).
- **MP-specific?**: Yes (national).
- **Estimated uplift**: +1 to +2 pp R@5% — strongly suggested by the European NHESS and Vilar literatures.
- **Effort**: 1–2 days (zonal stats + join).

### B6. Crop-residue burning fire footprint (NASA VIIRS NRT) — already in our stack
- **Source**: VIIRS active fires (we have the 1.35M historical rows already).
- **What it offers**: Skipping — we already have this via FIRMS. Point is: **crop-residue burning specifically as a pre-fire-season indicator** has NOT been engineered. MP is now #2 in stubble burning (11% of post-monsoon fires nationally) and the 2012–2020 trend is +185%. A `crop_burn_density_within_5km_last_60days` feature would capture the agricultural-burning culture of the cell — a strong proxy for "this cell's farmers use fire as a tool".
- **Accessibility**: Already have.
- **Estimated uplift**: +0.5 pp.
- **Effort**: 4 hours.

---

## C. Causal inference for fire attribution

### C1. Causal forest (Athey grf) for treatment-effect estimation
- **Source**: grf-labs.github.io/grf; Rehill methodological review 2025 (133 papers)
- **What it offers**: Heterogeneous treatment-effect estimation. Concretely: estimate the **conditional ATE of "village within 2 km has SHG / has been visited by JFM patrol last week"** on ignition probability, conditional on cell covariates. This is **not a feature** — it's a **policy-evaluation tool** that tells us which interventions move ignition risk for which cells. More valuable for the alert-action layer than for raw R@5%.
- **Accessibility**: Free R/Python `grf` package, mature.
- **MP-specific?**: Methodology only.
- **Estimated uplift**: 0 pp on R@5% directly (causal forests are not better predictors than RF/LGBM for prediction — Rehill 2025 confirms). But indirect uplift via better treatment selection in the dispatcher.
- **Effort**: 1 week if we have a treatment indicator (we don't yet).

### C2. Causal-graph wildfire framework (Hannart-Pearl-Otto-Naveau-Ghil; ICLR-MLRS 2024 Causal GNN for Wildfire)
- **Source**: PNAS 1510507113 (data fusion); ml-for-rs.github.io/iclr2024 paper 16
- **What it offers**: Formal SCM-based attribution of fire occurrences to driver factors (climate vs ignition vs fuel) with counterfactual estimands. The ICLR-MLRS Causal GNN paper specifically uses graph structure for wildfire attribution. **Practically**: lets us decompose "this v17 alert was driven by X% Hawkes recency, Y% NTFP-zone, Z% wind" — a **trust / explainability layer** for the v3 portal, not a raw recall booster.
- **Accessibility**: Code partially open.
- **MP-specific?**: No — adapt.
- **Estimated uplift**: 0 pp R@5%; **high indirect value** for forest-officer trust in low-Hawkes alerts (where v17 is currently weakest and least trusted).
- **Effort**: 2 weeks to scaffold.

---

## D. Behavioural simulation alternatives

### D1. Pattern-Oriented Modelling (POM) for human ignition behaviour
- **Source**: PMC3223804 (Grimm et al. POM); ABM-in-Ecology chapters; Indonesian PeatFire dry-days-before-ignition rule
- **What it offers**: Multi-criteria calibration of behavioural rules against multiple observed patterns simultaneously. For MP we have 3 candidate patterns: (a) Dewas 5-week pre-collection ignition lead, (b) Mahua March–April peak, (c) ~75% of ignitions within 2 km of forest fringe. POM would let us calibrate a small (3–5 rule) behavioural ignition model per beat that matches all three. This is **NOT classical ABM** (we already parked those — see `feedback_v6e_live_at_ceiling.md`); it's **rule-discovery via multi-pattern fitting**, output as a per-cell behavioural-risk score.
- **Accessibility**: Methodology free; data inputs we have.
- **MP-specific?**: Methodology; we'd build the MP instantiation.
- **Estimated uplift**: Speculative +1 pp R@5% as a per-cell prior. Most useful in **low-Hawkes cells specifically** — exactly the gap.
- **Effort**: 1–2 weeks (genuinely the hardest item on this list to scope).

### D2. Survey-based behavioural calibration (proxy: livelihood/forest-dependency surveys)
- **Source**: Forest Survey of India ISFR 2019 Vol-II MP (per-district forest-dependency stats); IISFR Jabalpur Forest Utilization Division datasets; SHRUG socioeconomic merge
- **What it offers**: Per-village/per-beat **NTFP collector counts, SC/ST fraction, fuelwood-dependent household counts** (where reported). Direct input to a behavioural prior at cell level. ISFR is published; SHRUG merges Census + DISE + SECC. These are **all already-collected** survey datasets we just haven't joined.
- **Accessibility**: ISFR free (PDF, needs scraping); SHRUG free (CSV).
- **MP-specific?**: Yes — ISFR has explicit MP volume.
- **Estimated uplift**: +0.5 to +1.5 pp R@5%.
- **Effort**: 3–5 days (scraping + spatial joins).

---

## Hard-NO / parked

- **Mobile-phone CDR partnership**: Industry literature exists (Telangana sandbox, Cuebiq EU), but Indian telcos do not share CDR for academic forest research absent multi-month MoUs and DPDP-Act privacy clearance. Effectively unavailable.
- **OSM forest-fringe features**: Coverage in MP rural is too sparse to be reliable. OSM India is patchy outside cities.
- **JFM committee fire incident logs**: FRIENVIS database referenced but not openly published as structured data; effectively unavailable.
- **Indian Institute of Soil & Water Conservation beat-level data**: Not openly catalogued; would need RTI / MoU. Park.
- **Hindi Twitter/news geocoding**: Same fundamental problem as GDELT — village-level NER yield is too low to materially help (we already saw 0% village yield in GDELT). Indian news fire reports cluster at district HQ centroids.
- **Shram Bharati / community fire logs**: Community-reported logs exist in pockets (NGO-run) but no statewide standardised feed.

---

## Top recommendations — one per category to actually pursue

| Category | Pick | Why |
|----------|------|-----|
| **A. Literature** | **A2 — Upper Ravi Himalaya GeoAI** | Closest to MP context; gives concrete feature ranking + stacking architecture to test against v17 single-LGBM. |
| **B. Data source** | **B3 — Dynamic World V1** monthly LULC | Only candidate that is (a) free, (b) MP-statewide, (c) **temporally animated**, (d) directly probes the slash-and-burn hypothesis at 10 m — and we have NOT tested it. Highest realistic uplift potential. |
| **C. Causal** | **C2 — Causal GNN attribution** for portal trust layer | Doesn't move R@5% but addresses the v3-portal weakness ("officers don't trust low-Hawkes alerts"); high product value. |
| **D. Behavioural** | **D2 — Survey-based ISFR + SHRUG join** | Lowest-risk, highest-yield: data already exists, methodology is mature, directly encodes the Dewas mechanism (NTFP-collector density). Build before any POM/ABM work. |

---

## Ranked candidate table — feasibility × expected uplift

| # | Candidate | Cat | Free? | MP-ready? | Uplift (pp R@5%) | Effort | Score* |
|---|-----------|-----|-------|-----------|------------------|--------|--------|
| 1 | **B3 Dynamic World monthly LULC** | B | yes | yes | +1.0 to +3.0 | 2–3 d | **9** |
| 2 | **D2 ISFR + SHRUG socioeconomic join** | D | yes | yes | +0.5 to +1.5 | 3–5 d | **8** |
| 3 | **B5 SHRUG village polygons + density** | B | yes | yes | +1.0 to +2.0 | 1–2 d | **8** |
| 4 | **B1 HRSL 30 m population** | B | yes | yes | +1.0 to +2.0 | 1 d | **8** |
| 5 | **A2 Upper Ravi GeoAI replication** | A | yes | partial | +1.5 (mostly architecture) | 3–5 d | **7** |
| 6 | **B6 Crop-burn density feature** | B | yes (have) | yes | +0.5 | 4 h | **7** |
| 7 | A3 Dewas tendu pre-collection feature | A | yes | yes | +0.5 | 4 h | 6 |
| 8 | A1 NHESS 2025 feature ranking port | A | yes | partial | +1.0 | 2 d | 6 |
| 9 | B4 AgMarkNet NTFP prices | B | yes | partial | 0 to +1.5 (coverage risk) | 1 d verify + 2 d | 5 |
| 10 | B2 WorldPop yearly population | B | yes | yes | +0.5 (after HRSL) | 0.5 d | 5 |
| 11 | C2 Causal GNN attribution (portal trust) | C | partial | no | 0 R@5%; high product value | 2 wk | 4 |
| 12 | D1 POM per-beat behavioural rules | D | yes | build | +1.0 (speculative, low-Hawkes only) | 1–2 wk | 3 |

*Score = ⌈Uplift_max × Feasibility⌉ on 0–10. Feasibility weights free + MP-ready + low-effort.

---

## Recommended sequencing

**Sprint 1 (1 week)**: B6 (crop-burn density, 4 h) → B1 (HRSL, 1 d) → B5 (SHRUG village density, 1–2 d) → A3 (Dewas tendu lead window, 4 h). All cheap, all direct feature additions to v18 candidate. Stop and re-train v18; honest measure on the **low-Hawkes subset** specifically.

**Sprint 2 (1 week)**: B3 Dynamic World monthly LULC (the headline experiment) on the v18 stack from Sprint 1. This is the single highest-EV item.

**Sprint 3 (parallel, 1 week)**: D2 ISFR + SHRUG socioeconomic join.

**Sprint 4 (deferred)**: A2 architecture replication (only if Sprints 1–3 break the ceiling and we want a structural upgrade) and C2 (portal trust layer, product-side, doesn't block).

If after Sprints 1–3 we have not crossed +3 pp R@5% on the **low-Hawkes subset**, the conclusion will be that the information needed to predict anthropogenic ignition in low-Hawkes cells **is not in any of the data sources surveyed here** — and the next move is RTI / MoU for non-public data (mobile CDR or LAMPS/MFP-Fed tendu collection logs), or accepting v17 as the permanent ceiling.

---

## Sources

- NHESS 2025 — [Assessing human-caused wildfire ignition likelihood across Europe](https://nhess.copernicus.org/articles/25/4713/2025/)
- Sci Reports 2026 — [Explainable GeoAI framework, Upper Ravi Indian Himalaya](https://www.nature.com/articles/s41598-026-46924-w)
- ScienceDirect 2026 — [Predicting wildfires triggered by human-caused ignition: spatial AI framework](https://www.sciencedirect.com/science/article/pii/S1574954126000464)
- Down To Earth 2025 — [Forest fire mitigation strategies in MP should prioritise tribal communities](https://www.downtoearth.org.in/forests/forest-fire-mitigation-strategies-in-madhya-pradesh-should-prioritise-tribal-communities-90493)
- DTE 2025 — [Forest fire management must begin with understanding the people who light them](https://www.downtoearth.org.in/natural-disasters/true-forest-fire-management-must-begin-not-with-extinguishing-flames-but-with-understanding-the-people-who-light-them)
- ResearchGate — [Forest Fire Characterization MP, Meteorology and Topography](https://www.researchgate.net/publication/373602643_Forest_Fire_Characterization_with_Relation_to_Meteorology_and_Topography_Parameters_in_Madhya_Pradesh_India)
- Mongabay 2023 — [Madhya Pradesh stubble burning unnoticed behind Punjab](https://india.mongabay.com/2023/08/behind-punjabs-smoke-screen-madhya-pradeshs-stubble-burning-problem-goes-unnoticed/)
- Meta — [HRSL High Resolution Settlement Layer downloads](https://research.facebook.com/downloads/high-resolution-settlement-layer-hrsl/)
- HDX — [HRSL India 30m population](https://data.humdata.org/dataset/pakistan-india_all-files-high-resolution-population-density-maps)
- WorldPop — [India 100m population hub](https://hub.worldpop.org/geodata/summary?id=6527)
- GEE — [Dynamic World V1 catalog](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)
- AgMarkNet — [Portal](https://agmarknet.gov.in/) and [data.gov.in mandi prices](https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi)
- SHRUG v2.1 — [Open shapefiles](https://docs.devdatalab.org/SHRUG-Construction-Details/shrug-open-source-polygons/)
- DataMeet — [Indian Village Boundaries](https://projects.datameet.org/indian_village_boundaries/)
- FSI — [ISFR 2019 Vol-II Madhya Pradesh PDF](https://fsi.nic.in/isfr19/vol2/isfr-2019-vol-ii-madhya-pradesh.pdf)
- MPSFRI Jabalpur — [Forest Utilization Division](https://www.mpsfri.org/index.php/forest-utilization-division)
- grf-labs — [Generalized Random Forests / causal_forest](https://grf-labs.github.io/grf/)
- Rehill 2025 — [How Do Applied Researchers Use the Causal Forest? Methodological Review](https://onlinelibrary.wiley.com/doi/full/10.1111/insr.12610)
- ICLR-MLRS 2024 — [Causal Graph Neural Networks for Wildfire](https://ml-for-rs.github.io/iclr2024/camera_ready/papers/16.pdf)
- PNAS — [Causal inference and the data-fusion problem (Pearl/Bareinboim)](https://www.pnas.org/doi/10.1073/pnas.1510507113)
- Grimm et al. — [Pattern-oriented modelling: a 'multi-scope' for predictive systems ecology](https://pmc.ncbi.nlm.nih.gov/articles/PMC3223804/)
- PeatFire — [Agent-based fire model in tropical peatland](https://connectsci.au/wf/article/30/2/71/21749/PeatFire-an-agent-based-model-to-simulate-fire)
- Springer — [Logistic regression models for human-caused wildfire risk (Vilar foundational)](https://link.springer.com/article/10.1007/s10342-011-0488-2)
- Springer 2022 — [MaxEnt anthropogenic vs natural ignition susceptibility](https://link.springer.com/article/10.1007/s11676-022-01502-4)
- Frontiers 2024 — [Carbon stock loss in Uttarakhand fires (tribal community context)](https://www.frontiersin.org/journals/forests-and-global-change/articles/10.3389/ffgc.2024.1352265/full)
- Anaxee 2025 — [Madhya Pradesh Forest Economy: NTFP, Carbon Credits & Digital MRV](https://anaxee.com/forest-economy-madhya-pradesh-ntfp-carbon/)
