# Deep Research Synthesis — 2026-04-19

**Scope:** 4 parallel researchers covering: (1) academic papers SOTA 2024-2026,
(2) GitHub fire-prediction repository landscape, (3) anthropogenic / human-caused
ignition methods, (4) point-process and Hawkes alternatives. Total ≈ 86 KB of
findings across 4 reports.

**Question:** Is there *anything* in the 2024-2026 literature, the open-source
landscape, the anthropogenic-data world, or the point-process toolbox that
attacks our 77% low-Hawkes new-outbreak gap better than Pivot A from the
prior memo?

**Headline:** Yes, and the convergent recommendation is **clearer + cheaper
than the original Pivot A.** Two approaches deserve a 1-week sprint; if they
fail, v17 + the diagnostic stack is genuinely the production ceiling.

---

## 1. Three convergent findings across all four reports

### 1.1 The architectural ceiling is real

R1 (papers) and R2 (GitHub) **independently** confirm: no peer-reviewed method
or open-source repository empirically beats LightGBM on a cold-start ignition
benchmark in dry-deciduous biomes at 2km resolution.

- R1: "Across Nature / Sci Reports / NHESS / ESSD / NeurIPS-CCAI / ICLR-ML4RS,
  no published method beats LightGBM on this regime."
- R2: "v17 is at the open-source ceiling. mesogeos (NeurIPS 2023, top peer
  comparison) does not beat our fundamentals."
- R4: "Refitting Hawkes on smaller label sets has been shown to regress
  performance; do not pursue more Hawkes tuning."

**Implication:** stop hunting for a better architecture. Hunt for missing
features or structural decomposition.

### 1.2 Satellite + weather data are exhausted

We have FIRMS (1.35M detections), Hawkes, Prithvi-EO-2.0 600M, NDVI/phenology,
GLCM texture, hydro topology, FWI, soil temp/moisture (just shipped). Both
R1 and R3 confirm there is no remaining EO modality that hasn't been tested
or that adds new signal. Foundation models, vision-language models, SAR
amplitude — all rejected with empirical evidence.

### 1.3 Two genuinely fresh paths emerge

R3 and R4 each independently identified one method that:
- specifically targets the cold-start regime
- has not been attempted in this project
- requires <1 week implementation
- has empirical validation on similar regimes
- is fully reversible if it fails

**These two methods are complementary, not competing.**

---

## 2. The Top-2 Recommendations

### 2.1 [R4 #1] Hurdle / ZINB two-stage decomposition

**Source:** Rodrigues, Manuela. *Hurdle models for analysing wildfire
occurrence patterns*. Ecological Processes 2020.

**Mechanism (in one paragraph).** Decompose v17's ignition-prediction task
into two stages: (a) a Bernoulli classifier that answers "did **anything**
ignite in this cell-day?" trained on v17's 111 features but **excluding the
Hawkes self-excitation block**; (b) v17 itself as the count / ranking model
for cells where stage (a) predicts probability above some threshold. Combine
via a weighted geometric mean. Stage (a) is *literally* the cold-start
question because it cannot rely on neighbour-fire history.

**Why this is structurally different from our prior origination model
attempt.** The prior origination Model B (commit `d134e18`) trained a
single LightGBM on the same feature space minus Hawkes and tried to
soft-ensemble with v17. It failed because Model B's ranking surface was
too smooth in low-Hawkes regions — 7 of 8 deep origination features had
zero gain; the model collapsed to weather-dominated predictions. The
hurdle differs in two key ways:
1. The Bernoulli stage models *presence/absence* (a much easier task than
   per-cell ranking), specifically for low-density regions.
2. The geometric-mean blend gives the Bernoulli stage a hard floor — it
   shifts where v17 places alerts, not what v17 ranks them.

**Effort:** 2–4 days. No new dependencies. Fully reversible (the production
v17 path is unchanged; we add a new endpoint that returns the blended
ranking for evaluation).

**Pass criterion:** low-Hawkes R@top-5% ≥ 8 % (vs current 5.9 %), AND
overall R@top-5% ≥ 47 % (no overall regression).

### 2.2 [R3 #1] Dynamic World monthly LULC delta features

**Source:** Brown et al. *Dynamic World, Near real-time global 10 m land
use land cover mapping*. Scientific Data 2022. Available as a free Google
Earth Engine ImageCollection, updated monthly.

**Mechanism.** Dynamic World is a trained 9-class probabilistic land-cover
classifier (water / trees / grass / flooded vegetation / crops / shrub /
built / bare / snow) at 10 m. For each v6e cell, compute the **change in
bare-ground probability** over the prior 4-week window. Slash-and-burn
land clearing — the dominant low-Hawkes ignition cause in MP — appears as
a measurable surge in bare-ground probability *before* the fire is
detected by FIRMS.

**Why this is different from our prior dNBR / BSI / temporal-delta
experiments.** Those used raw spectral indices computed at a single time
point and were dominated by phenology in MP's dry-deciduous forest
(memory `feedback_s2_dnbr_phenology_trap.md`). Dynamic World is a
**trained classifier** that explicitly distinguishes bare ground from
seasonal leaf-drop. Its bare-ground class is what we tried and failed to
extract from raw bands.

**Effort:** 2–3 days. GEE is already in our pipeline. Add a per-month
sampling job, append a small parquet, retrain v17 with 2 new features
(or treat as a calibration-only signal first).

**Pass criterion:** SHAP gain of `bare_ground_delta_4wk` features in the
top 30 at retraining, AND low-Hawkes R@top-5% ≥ 7 % (vs 5.9 %).

### 2.3 Why these two together (not either alone)

The two recommendations attack the same gap from orthogonal angles:

- The **hurdle decomposition** changes how we *combine* existing
  knowledge for the cold-start regime. It costs no new data.
- **Dynamic World features** change what we *observe* in the cold-start
  regime. It adds new data without changing architecture.

If only one works, we have a +2-3 pp uplift. If both work, the gains
plausibly compound to +5-6 pp because they target different mechanisms
(one structural, one observational). If both fail, we have empirical
evidence that the v17 + diagnostic stack is the actual ceiling.

---

## 3. The Sprint Plan (1 week, gated)

### Day 1-2: Hurdle Stage (a) Bernoulli classifier
- Build `scripts/train_v17_hurdle_stage_a.py`
- Same feature set as v17 minus Hawkes block (4 features)
- Same train/val temporal split
- LightGBM binary classifier (any-ignition-in-cell-day)
- Save `outputs/predictive_fire_risk/predictive_v17_hurdle_a/model.txt`

### Day 3: Hurdle blend + evaluation
- `scripts/evaluate_v17_hurdle_blend.py`
- Compute geometric mean of stage (a) probability × v17 ignition_risk
- Re-rank, re-band
- Honest metric on the same 2025 hold-out: overall R@5%, low-Hawkes R@5%,
  per-day R@5%
- Decision: if low-Hawkes R@5% ≥ 8 % AND overall ≥ 47 %, ship as v17.5

### Day 4-5: Dynamic World feature ingest
- `scripts/build_dynamic_world_features.py`
- GEE export of 10m DW probabilities for MP centroid grid, monthly
  2020-2026
- Aggregate to 2km cells: `bare_ground_prob_mean`, `bare_ground_prob_max`,
  `bare_ground_delta_4wk`, `cropland_prob_mean`, `cropland_to_bare_4wk`
- Save `data_lake/land_cover/dynamic_world_monthly.parquet`

### Day 6-7: Retrain v17 with DW features
- `scripts/train_v18_dynamic_world.py`
- v17's 111 features + 5 DW features = 116
- Same training regime
- Decision: if any DW feature in top-30 by gain AND low-Hawkes R@5% ≥ 7 %,
  ship; else document and accept.

### Combined evaluation (end of week)
- Run both v17.5 (hurdle) and v18 (DW) plus v18 + hurdle blend on same hold-out
- Decision matrix:

| Variant | Low-Hawkes R@5% target | Overall R@5% target | Action if pass |
|---|---:|---:|---|
| v17.5 (hurdle alone) | ≥ 8 % | ≥ 47 % | ship as new ignition model |
| v18 (DW alone) | ≥ 7 % | ≥ 47 % | retrain weekly, treat as v17 successor |
| v18.5 (DW + hurdle) | ≥ 10 % | ≥ 48 % | ship as v19 |
| All fail | — | — | accept v17 as ceiling, proceed to portal polish |

---

## 4. Explicitly REJECTED from this synthesis

| Candidate | Why rejected |
|---|---|
| Festival features as standalone tier (original Pivot A) | Already trained as v18; DBSCAN +1.8pp but BA-tiered -11.9pp. Net loss. |
| Real AgMarkNet NTFP prices | R3 confirms ≈0 coverage — "tendu/mahua trade is mostly off-mandi via MFP-Federation tendering." Data exists in name only. |
| Mobile CDR / telecom partnership | DPDP-Act blocks academic use. Not feasible in 2026. |
| Hindi regional newspaper scraping | 12-20 days, anti-bot defences, paywalls, OCR for Hindi articles. R3 explicitly down-ranked. |
| Cox-Hawkes (R4 #2) | 2-3 weeks, NumPyro implementation, requires inducing-point sub-sampling for 1M events. Defer until hurdle baseline established. |
| DKMPP deep MPP (R4 #3) | 2-3 weeks PyTorch implementation. Defer for the same reason. |
| FPA-FOD-Attributes (R1 #1) | Designed for US data; the equivalent Indian socioeconomic features come from Meta HRSL + SHRUG which are already covered by R3 #2 (folded into the DW sprint). |
| WUI/WAI/WGI (R1 #2) | 1-2 weeks; the per-cell wildland-interface typology is essentially a finer version of `lc_forest_edge_len` we already have. Marginal incremental signal. |
| Causal GNN / PCMCI (R1 #3) | 2 weeks; targets correlated-feature pruning, not new-outbreak prediction. Save for if hurdle + DW both fail. |
| TS-SatFire / WildfireSpreadTS / mesogeos (R2 top picks) | These are *spread* prediction tasks at next-day granularity. We already have Cell2Fire + Muhurta ROS-UNet for spread. Wrong task. |
| WildfireGPT / LLM frameworks | Not a prediction model — it's an LLM-based query interface for wildfire info. Doesn't address our gap. |
| FireCastNet | Seasonal forecasting at country scale. Wrong scale. |

## 5. Decision

**Proceed with the 1-week sprint** (Hurdle + Dynamic World) as Pivot A v2.
Both candidates are:

1. Specifically designed to attack the cold-start / new-outbreak regime
2. Empirically validated on similar fire-prediction tasks
3. Implementable in <5 days each
4. Fully reversible (production v17 unchanged during pilot)
5. Independent of the data-blocked Path C plan

If both fail, we have run **the rigorous experiment** that proves v17 +
diagnostic stack is the ceiling. The negative result is itself shippable:
it tells the project (and any future reviewers) that the 47% R@top-5%
ceiling is a fundamental property of the available data, not an
implementation gap.

**Estimated calendar time:** 1 week for the sprint; one extra day for
synthesis and finding doc.

## 6. Reports cited

- [r1 — papers SOTA 2024-2026](r1_papers_sota_2024_2026.md)
- [r2 — GitHub repos landscape](r2_github_landscape.md)
- [r3 — anthropogenic methods + open data](r3_anthropogenic_methods.md)
- [r4 — point process methods](r4_point_process_methods.md)

Each report contains its own ranked candidate table, sources, and
decision criteria. This synthesis distils the cross-cutting recommendations.
