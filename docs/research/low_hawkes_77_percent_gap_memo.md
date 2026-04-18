# Attacking the 77% Gap — Low-Hawkes New-Outbreak Fire Prediction

**Date:** 2026-04-19
**Author:** Claude Code research pass, no code yet
**Audience:** engineering + forest-dept stakeholders
**Scope:** the structural gap where v17 is near-random (5.9% R@top-5% on low-Hawkes cells where 77% of real fires start)

---

## 1. The problem in one paragraph

v17 (`model.txt`) catches 47.41% of next-week ignitions in its top-5% rank band, but that number is **carried by fire contagion** (Hawkes self-excitation). When we split the 2025 hold-out by Hawkes regime (`data_lake/audits/low_hawkes_distribution.csv`):

| Hawkes_n | Share of fires | R@top-5% | Median spatial offset |
|---|---:|---:|---:|
| 0 | 22% of test fires but **77% of new outbreaks** | 5.9% | 43 km |
| 1–2 | 15% | 15% | 19 km |
| 3–9 | 27% | 23% | 16 km |
| ≥10 | 36% | 44% | 12 km |

The Hawkes kernel dominates the model's predictive surface. Where Hawkes has no neighbours to anchor on, v17 falls back on weather + anthropogenic-distance priors that place alerts too broadly. The gap is not a tuning issue; it is an information gap. Tabular features we have do not uniquely identify which low-Hawkes cell will host tomorrow's new outbreak.

## 2. Three candidate paths and what prior art says about each

### Path A — MiroFish / OASIS behavioral simulator

**What it is.** MiroFish is an open-source multi-agent prediction engine (Python + Flask + Neo4j + Ollama + Vue) built on top of **OASIS** (CAMEL-AI, arXiv 2411.11581 — "Open Agent Social Interaction Simulations with One Million Agents"). You feed it a seed document; it extracts entities via **GraphRAG**, instantiates agents with personalities + memory, and runs them through a social-media-style simulation. A ReportAgent synthesizes emergent outcomes.

**How it *could* fit our problem.**
- The 77% gap is fundamentally about **human decisions** (NTFP collection, festival bonfires, stubble burn timing, land clearing).
- If we seed MiroFish with: MP forest village demographics + weekly Vanagni bulletins + NTFP price series + festival calendar + weather forecast, agents could simulate emergent anthropogenic pressure per division.
- Output: a per-division "pressure index" for next 7 days → fed as a new feature to v17.

**Honest blockers.**

| Blocker | Severity |
|---|---|
| OASIS' default action space (23 social-media actions: post / like / repost / follow) has **no fire-relevant verbs**. Custom action-space design is weeks of prompt engineering. | HIGH |
| LLM-based agents at 1M scale need 24GB VRAM (qwen2.5:32b). Our AMD RX 9060 XT is 16GB → downgrade to qwen2.5:7b, which tanks agent-reasoning quality. | MEDIUM |
| **No ground-truth village-level fire logs to calibrate or validate the simulation.** Prior project ABM attempt (`src/model/ignition_abm.py`, memory `abm_deep_research.md`) failed on exactly this — "inverted biomass, circular VIIRS seeding, wrong validation target." MiroFish does not fix the data problem, only the simulation framework. | **CRITICAL** |
| OASIS cites social-media replication (polarization, information spread) as proven use; **zero published cases** of physical-ignition prediction via OASIS/MiroFish. We'd be first movers without a reference baseline. | MEDIUM |
| Simulating 1000 villagers × 7 days × ~10 action steps ≈ 70K LLM calls/week. At local qwen2.5:7b (~2s/call on 16GB GPU) = ~40 hours compute per weekly prediction. Not operationally tractable. | HIGH |

**Realistic expected outcome.** The framework will produce *plausible-looking* predictions that are untestable against ground truth. You get a qualitative narrative ("Bhagoria-adjacent cells with high NTFP dependence and low employment are likely pressure points") but no measurable R@top-5% uplift because there's nothing to calibrate against.

**Verdict.** Intellectually interesting, 10-day experiment at best, very low probability of moving R@top-5%. Only pursue if the deliverable is *narrative forecasts* for field officers, not numeric risk scores.

---

### Path B — Two-model (Hawkes + origination) architecture with soft hand-off

**What it is.** A well-established idea in self-exciting-point-process literature: model fire contagion (Hawkes-dominated) and fire origination (Hawkes-independent) separately, blend via a soft gate on Hawkes-intensity. For cells with Hawkes_n≥3 trust the main v17; for low-Hawkes cells trust a specialized model that *never sees* Hawkes features.

**Prior work on this project.** We already tried this. `scripts/train_v17_origination.py` + `docs/audits/v17_architectural_upgrade.md`, committed d134e18. Direct results from `outputs/predictive_fire_risk/predictive_v17_origination/results.json`:

| Configuration | Overall R@5% | Low-Hawkes R@5% | Total caught |
|---|---:|---:|---:|
| v17 alone (statewide) | 22.7% | 5.9% | ~820 |
| Best soft-ensemble (k=1.0, h0=0.5) | **16.1%** | 11.8% | 583 |
| Maximum low-Hawkes attempt (k=1.0, h0=1.5) | 8.7% | 19.0% | ~300 |

The tradeoff was real but brutal: doubling low-Hawkes recall (60 vs 45 fires) **cost 237 overall catches**. Model B on low-Hawkes only hit R@5%=4.3% — **worse than v17 itself at 5.9%.** Model B's best_iter=1 (immediate overfit), PR-AUC=0.004 (essentially random on the low-Hawkes subset).

**Why prior attempt failed.** Feature importance from `data_lake/audits/low_hawkes_feature_importance.csv`: even in the low-Hawkes slice, the dominant features were `wx_ffmc`, `hist_fire_freq`, `ndvi_expected`, `lc_burnable_frac`. The model learned "hot dry forest will burn somewhere" — but couldn't say **which cell**. Weather priors are spatially too smooth at 2km resolution to discriminate between adjacent cells.

**What a second attempt would need to be different.**
- Genuinely new features that carry spatial discriminating power in low-Hawkes regime:
  - Distance to mahua-cluster centroids (already have species SDM)
  - Village fringe index (cell is within 500m of census-2011 habitation polygon)
  - NTFP pressure index (tendu/mahua price anomaly × DOY-to-peak)
  - Festival adjacency (days to Holi / Akshaya / Bhagoria) — tried in v18, weakened BA-tiered recall
  - Real NTFP mandi prices (currently synthetic per memory `project_species_mapping_v2.md`)
- A different target: predict *new-ignition* cells, not *any* fire, to remove the contagion signal from the training distribution.
- A different loss: down-weight contagion fires in the training set entirely.

**Realistic expected outcome.** +2–4 pp low-Hawkes R@5% (5.9% → 8–10%) possible but small operationally. The underlying information gap is not closed by feature engineering alone. This path is well understood and has been explored; second attempt needs NEW data to break even.

**Verdict.** Well-understood boring path. Low probability of +5pp total uplift; a realistic +2pp with 3–5 days of work. Main value: already-known blind spot is at least partially covered, making the model's honest weakness table less bad.

---

### Path C — Hindi-language weak-label enrichment (NDMA + MPFD)

**What it is.** The VIIRS satellite label pipeline misses ~35–45% of MP burn area per Vadrevu & Lasko 2018 (sub-pixel, cloud-occluded, sub-canopy). Many missed fires ARE reported in Hindi-language NDMA situation reports and MP Forest Department Vanagni bulletins. Building a scraper + Hindi NER + Nominatim village-geocoder adds a parallel label source that biases training toward exactly the anthropogenic small-fire regime we're missing.

**Literature evidence.** Dolatabadi 2024 IJWF (reported in prior plan) achieved +0.09 AP on Australian fires by adding GDELT news events as PU-learning weak labels. For our problem:
- NDMA SitRep PDFs (ndma.gov.in) — daily reports during fire season with district + village names
- MPFD Vanagni bulletins (mpforest.gov.in) — daily Hindi PDFs, village-level
- VANAAGNI 3.0 (FSI national geo-portal, fsiforestfire.gov.in) — same VIIRS we already use, not additive
- FSI ISFR 2023 — annual, too coarse

**Prior work on this project.**
- GDELT article-level geocoding pilot: 0% yield. `scripts/pilot_gdelt_geocode.py` + memory `feedback_gdelt_district_centroid_geocoding.md`. Failure mode: GDELT's ActionGeo is district-centroid only; village-level location extraction from news HTML gave 68% dead links, 88% non-fire articles after keyword filtering.
- **NDMA/MPFD PDF scraping: never attempted.** These are proper published PDFs with structured village references.

**Key technical challenges.**

| Step | Time estimate | Risk |
|---|---|---|
| Scrape NDMA daily SitReps 2014-2026 | 1-2 days | LOW — static PDFs, polite scraping |
| Scrape MPFD Vanagni daily bulletins 2014-2026 | 2-3 days | MEDIUM — site structure may vary by year |
| Hindi OCR + NER for fire-mention sentences | 3-5 days | MEDIUM — IndicBERT + spaCy-Devanagari work; some hand-validation needed |
| Nominatim geocoding of extracted village names | 2 days | MEDIUM — long-tail village names may fail; fallback to district-level |
| Tier-aware PU retraining with NEWS_CONFIRMED positives | 2 days | LOW — existing v17 trainer has tier support |

Total: **10–14 days**.

**What the uplift would look like.** If Dolatabadi 2024's +0.09 AP transfers:
- v17 PR-AUC 0.148 → 0.24 (+60% relative)
- Low-Hawkes R@top-5% most-likely-to-improve arm (because news reports are biased toward unusual/anthropogenic fires in remote low-Hawkes regions). Expected: 5.9% → 10-18%.

**Risks.**
1. Hindi NER on Vanagni's OCR'd text may be noisier than expected; quality hit
2. Village names are ambiguous (many Bhopur / Ramnagar entries in India); geocoding often lands at district HQ anyway
3. News coverage is biased toward large + politically-salient fires, which may be a DIFFERENT subset than small anthropogenic new outbreaks

**Verdict.** Highest expected-value path. Structurally breaks the VIIRS label ceiling. Real risk that the subset of fires found in Hindi PDFs overlaps heavily with what VIIRS already caught (big fires that spread visibly). Needs a pilot (scrape 30 days, manually inspect 100 extracted events) before full commitment.

---

## 3. Side-by-side scorecard

| Dimension | A. MiroFish | B. Two-model v2 | C. Hindi label enrichment |
|---|:-:|:-:|:-:|
| Expected R@top-5% uplift | ≈0 pp (no ground truth) | +2-4 pp | +5-12 pp (per lit) |
| Calendar time | 10 days | 3-5 days | 10-14 days |
| Novelty vs prior attempts | 100% new | Retry with new features | 100% new |
| Hardware fit | marginal (needs qwen2.5:7b fallback) | fits | fits |
| Validation feasible? | **No** — no village-level ground truth | Yes, same 2025 hold-out | Yes, native-VIIRS hold-out |
| Operational deliverable | Narrative forecasts only | New banded alerts | Structurally better labels |
| Reproducibility | External tool churn | Fully in-repo | Mostly in-repo |
| Dependency on external services | Ollama + Neo4j | none | NDMA + MPFD + Nominatim |

## 4. Recommendation

**Primary recommendation: Path C (Hindi label enrichment) + a narrow slice of Path B as insurance.**

Rationale:
1. Path C is the only one with a published baseline ("+0.09 AP" on similar work) and a clear mechanism to break the VIIRS-invisible-fire ceiling that constrains Path B.
2. Before committing 10–14 days, run a **3-day pilot**: scrape 30 days of NDMA SitReps + 30 days of MPFD Vanagni, manually inspect 50 extracted events per source. Decide ship-or-kill on:
   - ≥ 30% of extracted fires geocode to village-level (not district centroid)
   - ≥ 30% of those village-level fires are NOT already in the FIRMS DBSCAN set
3. If pilot passes, commit full scrape + Hindi NER + retrain.
4. If pilot fails, fall back to Path B with new behavioural-feature investment (NTFP real prices, census-2011 habitation proximity) — accept the modest +2pp and ship.

**MiroFish (Path A) is parked** for this problem. It could have a separate use case as a narrative-level what-if tool for DFOs but not as a mechanism to raise R@top-5%.

## 5. Immediate next step if approved

Build `scripts/pilot_ndma_mpfd_scraper.py`:

1. Fetch NDMA SitRep index for 2025 fire season (Feb-May)
2. Download PDF list
3. OCR + regex for "forest fire" / "जंगल की आग" / village-like tokens
4. Geocode via Nominatim with MP bounding-box
5. Compare against our existing FIRMS DBSCAN set for (cell_id, week)
6. Report: new-fires-recovered rate, village-level-localization rate, geographic skew

If and only if this pilot passes, proceed to full v19 training with PU-weighted NEWS_CONFIRMED tier.

---

## 6. Sources

- MiroFish architecture: [MiroFish AI engine — DEV community overview](https://dev.to/arshtechpro/mirofish-the-open-source-ai-engine-that-builds-digital-worlds-to-predict-the-future-ki8)
- MiroFish offline stack: [nikmcfly/MiroFish-Offline (GitHub)](https://github.com/nikmcfly/MiroFish-Offline)
- OASIS paper: [arXiv 2411.11581 — Open Agent Social Interaction Simulations with One Million Agents](https://arxiv.org/abs/2411.11581)
- OASIS repo: [camel-ai/oasis (GitHub)](https://github.com/camel-ai/oasis)
- India anthropogenic wildfire drivers: [Anthropogenic dry deciduous fire patterns (Nature Scientific Reports 2025)](https://www.nature.com/articles/s41598-025-98051-7)
- FSI VanAgni portal (VIIRS dashboard; not additive to our FIRMS source): [fsiforestfire.gov.in via ISFR 2023 Drishti summary](https://www.drishtiias.com/daily-updates/daily-news-analysis/18th-india-state-of-forest-report-2023)
- NDMA forest-fire policy docs (starting points for SitRep scraper): [NDMA Reports index](https://ndma.gov.in/Reference_Material/NDMAReports)
- Prior project data: `scripts/train_v17_origination.py`, `outputs/predictive_fire_risk/predictive_v17_origination/results.json`, `scripts/pilot_gdelt_geocode.py`, `memory/feedback_gdelt_district_centroid_geocoding.md`, `memory/abm_deep_research.md`
