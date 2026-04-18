# Diagnostic Stack Expansion — Prophet-Class + Adjacent Tools

**Date:** 2026-04-19
**Author:** Claude Code research pass
**Scope:** Identify libraries/models that can augment the v17 + Prophet-Season-Pulse diagnostic stack without touching the core predictor. Rank by fit, effort, payoff.

---

## 0. What already lives in the stack

- **v17 LightGBM**: per-cell next-week ignition probability (primary predictor)
- **Hawkes self-excitation**: custom cKDTree kernel over DBSCAN ignitions (feature into v17)
- **Prophet on statewide daily FRP**: seasonal baseline + drift flag (just shipped, commit `4efea59`)
- **Operational alert decorator**: trust tiers + budget caps + calendar hints + action text
- **Per-fire validation**: spatial + temporal offset analysis, precision cone tables

What's missing from the diagnostic layer:
1. Per-division seasonal baselines (Prophet covers only statewide scalar)
2. Change-point detection for season onset / regime shifts
3. Anomaly detection for "this week's pattern is unlike anything we've seen"
4. Causal impact measurement for interventions (prescribed burns, patrol campaigns)
5. Feature-distribution drift monitoring in production
6. Zero-shot forecasting as a sanity-check overlay

---

## 1. Eight candidate additions, honestly benchmarked

### A. Nixtla StatsForecast (AutoARIMA / AutoETS / AutoTheta)
- **What:** Statistical forecasting toolkit, Numba-JIT compiled. 37× faster than Prophet on 100K-series benchmark, +17% MAPE improvement per Nixtla published numbers.
- **Fit to us:** Replace Prophet for **per-division** seasonal baselines. 74 divisions → 74 parallel forecasts. Prophet would take hours; StatsForecast does it in <1 minute.
- **Effort:** 2–4 hours. Drop-in replacement for current Prophet script with per-division loop.
- **Payoff:** Per-DFO seasonal drift flag. Currently the DFO of Damoh only sees statewide drift; with this they see "Damoh is running 2σ above its own historical pattern."
- **Risk:** Low. Well-maintained, standard statistical methods.
- **Recommend:** **YES — add as `fit_statsforecast_per_division.py`**

### B. ruptures (change-point detection)
- **What:** Offline change-point detection. PELT algorithm has O(n) complexity; handles yearly + daily time series.
- **Fit to us:** Detect **season onset date** for each year (when does FRP start accelerating?) and **regime shifts** within a season (heat wave breakthrough). Answers "when did 2026 fire season actually start?" instead of relying on the calendar convention of Feb 1.
- **Effort:** 3–5 hours. Run PELT on 5 years of daily FRP, annotate onset dates, compare to calendar expectation.
- **Payoff:** One number per year — days before/after calendar Feb 1 — + a real-time alert when this year's season crosses its change-point.
- **Risk:** Low.
- **Recommend:** **YES — add as `detect_season_changepoints.py`, surface in portal**

### C. STUMPY (matrix profile anomaly detection)
- **What:** Matrix profile computes z-normalized Euclidean distance between every subsequence and its nearest neighbor. Global maximum = rarest anomaly.
- **Fit to us:** Apply to 28-day FRP subsequences across 12 years of data. Finds weeks whose FRP pattern is unlike anything we've seen before — early warning for novel regimes. Also finds **recurring motifs** — common patterns that precede bad weeks.
- **Effort:** 4–6 hours.
- **Payoff:** A "this week's fire pattern has never occurred before" tag is very operationally useful. Also surfaces cyclical motifs that might explain the weekly jump in activity pre-Holi vs post-Holi.
- **Risk:** Low. Pure NumPy compute, no dependencies.
- **Recommend:** **YES — add as `matrix_profile_anomaly.py`**

### D. Chronos / TimeGPT (foundation TS models, zero-shot)
- **What:** T5-based (Chronos) or GPT-style (TimeGPT) transformer pretrained on billions of time series. Zero-shot forecasting without local training.
- **Fit to us:** Useful mainly as a **sanity-check overlay** — "the foundation model, which has never seen MP fire data, predicts Y; our Prophet-tuned-on-MP predicts Y'. Big disagreement = worth investigating."
- **Effort:** 1–3 days. Chronos runs locally (no API). TimeGPT requires Nixtla API + key.
- **Payoff:** Mostly diagnostic / research value. Could inform whether our Prophet baseline is biased by MP-specific quirks. Published benchmarks (Parseable zero-shot study) show foundation models mostly **tie or lose** to well-tuned local models on specialized domains.
- **Risk:** Medium. The value is genuinely uncertain — zero-shot will likely agree with Prophet most of the time, and you're the one deciding which to trust when they disagree.
- **Recommend:** **DEFER** — only add after A/B/C land and we have a specific regime-shift event where we want an outside opinion.

### E. NeuralProphet
- **What:** Prophet-compatible API with AR + lagged-covariate support. Better short-term accuracy, slightly harder to explain.
- **Fit to us:** Replaces current Prophet with one that can incorporate FWI as a covariate. Prophet can't use FWI directly; NeuralProphet can.
- **Effort:** 1 day swap.
- **Payoff:** +15–25% MAPE improvement vs Prophet (per the library's own benchmarks). May reduce drift-flag false positives by better incorporating weather regime.
- **Risk:** Medium. Adds PyTorch dependency to the daily pipeline. Slightly less stable than vanilla Prophet.
- **Recommend:** **LATER** — only if current Prophet starts misfiring. It currently ships with a reasonable [1,662 … 32,359] band; the uncertainty is dominated by FRP heavy-tails, not model choice.

### F. Darts (unified forecasting interface)
- **What:** Wraps ARIMA + Prophet + N-BEATS + TFT + many deep models behind one API. Also has anomaly-detection modules.
- **Fit to us:** Makes it trivial to A/B different forecasters in one script. Not valuable unless we're seriously hunting for the best seasonal baseline (we're not — Prophet works).
- **Effort:** 0.5 day to integrate.
- **Payoff:** Mostly code-ergonomics. Doesn't add unique capability.
- **Recommend:** **SKIP** for now. Revisit only if we decide to rebuild the forecasting layer.

### G. Temporal Fusion Transformer (TFT)
- **What:** Multi-horizon multivariate transformer with interpretability head (variable importance + attention visualization). Handles static + time-varying-known + time-varying-unknown covariates.
- **Fit to us:** Could theoretically replace v17's tabular architecture with a unified TS-transformer that ingests the Hawkes + weather + NDVI directly. But: we tried spatial CNN in Phase 3 and it lost; Phase 4 Plan B confirmed LightGBM dominates for this task. TFT is structurally closer to CNN than to LightGBM.
- **Effort:** 5–10 days.
- **Payoff:** Uncertain. Prior phase work suggests architectures richer than GBDT don't help at the 2km cell resolution.
- **Recommend:** **SKIP** — the v17 architecture ceiling has been established via 3 independent experiments (fuel features, GFS, MV-CNN). TFT is unlikely to break it and would duplicate existing work.

### H. CausalImpact (Bayesian structural time series)
- **What:** Compares a post-intervention outcome against a synthetic-control counterfactual built from correlated time series. Google-originated, R and Python implementations.
- **Fit to us:** If MP Forest Dept runs a patrol-intensification campaign or prescribed burn, CausalImpact can answer **"did this reduce fire incidence, or was it just luck with weather?"** Uses neighboring divisions as controls.
- **Effort:** 3–5 days to build a proper harness, one-off per intervention.
- **Payoff:** Operationally high — turns the portal into a post-intervention evaluator. Also lets us measure "how much did the model itself contribute to reduced fire days" over time.
- **Risk:** Medium. Needs a well-defined intervention event and good parallel controls.
- **Recommend:** **SHELF until we have an intervention to measure.** Add to roadmap, don't build speculatively. First intervention opportunity: new beat-boundary layer rollout (2026-04-18 onwards) — we can measure whether patrol response changed.

### I. Alibi Detect (feature drift monitor)
- **What:** Multivariate drift detectors (KS test, MMD, learned). Production-oriented: reference window + live window.
- **Fit to us:** Monitor whether the 111-feature distribution fed into v17 is drifting from the 2014-2024 training window. Currently we have a minimal `v17_drift_log.parquet` but no formal PSI/KS test.
- **Effort:** 1–2 days.
- **Payoff:** Catch broken feature pipelines or climate regime shifts early — before they silently degrade v17's accuracy.
- **Risk:** Low.
- **Recommend:** **YES — add as `monitor_v17_feature_drift.py`, daily cron**. Higher-value than D/E/F/G for operational reliability.

### J. tick / pyhawkes (better Hawkes calibration)
- **What:** Professional Hawkes estimation — tick has parametric + non-parametric estimators, pyhawkes has Bayesian network-structured Hawkes.
- **Fit to us:** Our current Hawkes is a hand-rolled cKDTree kernel with literature priors (τ_t=3d, τ_s=5km). A proper parameter fit might improve the kernel.
- **Effort:** 2–3 days.
- **Payoff:** Uncertain. Prior memory `feedback_hawkes_density_over_purity.md` says v17.2 regressed when we tried to "improve" Hawkes by re-fitting on GOLD+SILVER ignitions — the DBSCAN density dominated label purity. A proper tick-fit could either help or repeat this failure.
- **Risk:** Medium. Non-trivial validation bar.
- **Recommend:** **DEFER** — only if Path C (Hindi label enrichment from prior memo) delivers new labels worth refitting around.

---

## 2. Scorecard

| Tool | Fit | Effort | Payoff | Risk | Rank |
|---|:-:|:-:|:-:|:-:|:-:|
| **A. Nixtla StatsForecast** | High | 2–4h | Medium | Low | **1** |
| **I. Alibi Detect drift** | High | 1–2d | Medium | Low | **2** |
| **C. STUMPY matrix profile** | Medium-High | 4–6h | Medium | Low | **3** |
| **B. ruptures changepoints** | Medium | 3–5h | Medium | Low | **4** |
| H. CausalImpact | Medium | 3–5d | High (when used) | Medium | Shelf |
| J. tick/pyhawkes | Low | 2–3d | Uncertain | Medium | Defer |
| D. Chronos/TimeGPT | Low | 1–3d | Uncertain | Medium | Defer |
| E. NeuralProphet | Low | 1d | Small | Medium | Later |
| F. Darts | Low | 0.5d | Small | Low | Skip |
| G. TFT | Low | 5–10d | Uncertain | Medium | Skip |

## 3. Recommended 1-week sprint

**Ship in order:**

1. **StatsForecast per-division Prophet-class baselines** (2–4 hours)
   - 74 divisions × 12 years → AutoARIMA in parallel via Numba
   - Endpoint: `/api/division-pulse`
   - Portal: extend Tab 2 (Divisions) cards with division-level drift tag (ELEVATED/TYPICAL/QUIET)

2. **Alibi Detect v17 feature drift** (1–2 days)
   - KS test on top-10 feature distributions, weekly vs 2020-2024 reference
   - Endpoint: `/api/feature-drift`
   - Portal: new "System Health" card in Tab 3

3. **STUMPY anomaly on 28-day FRP subsequences** (4–6 hours)
   - Matrix profile across 12-year daily FRP series
   - Tag current week as NEW_REGIME if matrix profile distance exceeds historical p99
   - Portal: add tag to existing Season Pulse chart

4. **ruptures change-point detection for season onset** (3–5 hours)
   - PELT on yearly FRP series → onset date per year
   - Portal: "2026 season started March 8 (10 days earlier than 5-year median)"

Total: ~3 work days. All additive to the existing stack; zero risk to v17 or the production alert path. Each deliverable is independent and shippable on its own — no big-bang rewrite.

**Parked for explicit trigger:**
- CausalImpact (wait for a real intervention)
- tick/pyhawkes (wait for new labels from NDMA/MPFD path)
- Chronos/TimeGPT (wait for a specific regime-shift event we want an outside opinion on)

**Skipped:**
- NeuralProphet, Darts, TFT — either duplicate existing capability or repeat prior phase failures

## 4. What this does NOT solve

Nothing in this memo attacks the 77% low-Hawkes gap. These are all **diagnostic/operational** augmentations — they improve how well staff can **read** the system and **trust** its output, not what the system **predicts**. The 77% gap recommendation (Path C — Hindi NDMA/MPFD enrichment) from the prior memo `docs/research/low_hawkes_77_percent_gap_memo.md` remains unchanged.

## Sources

- Prophet benchmarks: [NeuralProphet comparison — Towards Data Science](https://towardsdatascience.com/prophet-vs-neuralprophet-fc717ab7a9d8/), [NeuralProphet paper arXiv 2111.15397](https://arxiv.org/abs/2111.15397)
- Nixtla: [StatsForecast AutoARIMA vs Prophet experiment](https://nixtlaverse.nixtla.io/statsforecast/docs/experiments/autoarima_vs_prophet.html), [Nixtla StatsForecast repo](https://github.com/Nixtla/statsforecast)
- Foundation TS models: [Chronos — Towards Data Science](https://towardsdatascience.com/chronos-the-rise-of-foundation-models-for-time-series-forecasting-aaeba62d9da3/), [FPP Python ch.15](https://otexts.com/fpppy/nbs/15-foundation-models.html)
- ruptures: [ruptures docs + PELT](https://centre-borelli.github.io/ruptures-docs/), [deepcharles/ruptures repo](https://github.com/deepcharles/ruptures)
- STUMPY: [Tutorial + Matrix Profile](https://stumpy.readthedocs.io/en/latest/Tutorial_The_Matrix_Profile.html), [stumpy-dev/stumpy repo](https://github.com/stumpy-dev/stumpy)
- CausalImpact: [Google CausalImpact overview](https://google.github.io/CausalImpact/CausalImpact.html), [tfp-causalimpact PyPI](https://pypi.org/project/tfp-causalimpact/)
- Alibi Detect: [SeldonIO/alibi-detect repo](https://github.com/SeldonIO/alibi-detect), [drift monitoring real-time with Alibi-Detect — Medium](https://medium.com/@myakalarajkumar1998/real-time-drift-detection-in-forecast-models-with-alibi-detect-a2b4762badf5)
- Darts: [unit8co/darts repo](https://github.com/unit8co/darts), [Darts docs](https://unit8co.github.io/darts/)
- TFT: [pytorch-forecasting docs](https://pytorch-forecasting.readthedocs.io/en/v1.4.0/tutorials/stallion.html)
- Hawkes libraries: [tick docs](https://x-datainitiative.github.io/tick/modules/hawkes.html), [slinderman/pyhawkes repo](https://github.com/slinderman/pyhawkes), [tick paper JMLR](https://www.jmlr.org/papers/volume18/17-381/17-381.pdf)
- N-BEATS/N-HiTS: [OpenReview N-BEATS](https://openreview.net/forum?id=r1ecqn4YwB)
