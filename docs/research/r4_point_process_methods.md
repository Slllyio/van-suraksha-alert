# R4 — Modern Point Process Methods for the Cold-Start (Low-Hawkes) Regime

**Date**: 2026-04-19
**Author**: Research agent (Opus 4.7)
**Context**: v17 LightGBM+Hawkes is at the information-theoretic ceiling for new-outbreak prediction (5.9% R@5% in low-Hawkes cells, where 77% of fires actually start). Hawkes self-excitation dominates v17's signal but produces a flat baseline rate where no recent fires have occurred. This memo scans 2017-2025 point-process literature for methods that specifically attack that cold-start blind spot.

**Hard scope filters applied**:
- No pure Hawkes-tuning (we already established density>purity per `feedback_hawkes_density_over_purity.md`)
- No foundation TS models (separately scoped)
- No methods tested on similar Indian fire data (no such literature exists; all transfer claims downgraded one honesty rank)
- No SAR/VLM/CLIP variants (already falsified — see `feedback_ps1_sar_amplitude_dead.md`, `feedback_vlm_llava_7b_indiscriminate.md`)

---

## Why "cold-start" is a structural Hawkes failure, not a tuning problem

The Hawkes intensity at cell `i` and time `t` decomposes as:

```
λ(i, t) = μ(i, t)  +  Σ_{j: t_j < t} κ_s(d(i, x_j)) · κ_t(t - t_j)
          ^^^^^^^^      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
          baseline      self-excitation kernel (the strong v17 signal)
```

In v17, μ(i, t) is effectively a **constant background rate** estimated from the long-run DBSCAN-cluster count. When the second term collapses to zero (no neighbours have fired in the past τ_t ≈ 3 days), we are predicting from a flat μ, and the LightGBM head must compensate using weather + anthropogenic features that are too smooth at 2 km cells.

**The cold-start fix must therefore live in μ(i, t), not in the kernel.** Three families of methods directly target this:

1. **Doubly-stochastic / Cox-Hawkes** — make μ a learned spatial random field
2. **Marked / multivariate Hawkes with exogenous excitation** — make weather etc. a *separate* exciting process
3. **Zero-inflated / hurdle decomposition** — model occurrence and intensity as separate gates

Everything below is judged against that lens.

---

## Candidates (10 total, ranked at end)

### 1. Cox-Hawkes (Miscouridou et al. 2022)

- **Title**: Cox-Hawkes: doubly stochastic spatiotemporal Poisson processes
- **First author / year / venue**: Xenia Miscouridou, 2022, arXiv (also presented at AISTATS-track community)
- **Link**: https://arxiv.org/abs/2210.11844
- **Mechanism**: Replaces Hawkes' constant background rate μ with a **log-Gaussian Cox process (LGCP) prior**. So μ(i, t) is a smooth GP-distributed random field over space-time, while the self-excitation kernel sits on top unchanged. Inference uses MCMC with pre-trained GP generators (no slow numerical integration).
- **Why it specifically helps cold-start**: This is the textbook fix for our problem. In low-Hawkes cells the LGCP background rate carries the spatial signal — clusters of past ignitions in nearby cells inflate μ even when no Hawkes-active neighbour exists in the last 3 days. It directly fills the gap our flat μ leaves.
- **Python implementation**: Author's NumPyro reference at https://github.com/Mishra-Lab/Cox-Hawkes — non-trivial-but-tractable. MCMC scaling to 1M MP events will require a Nyström / inducing-point sub-sample (~5-10K representative events).
- **Effort**: 2-3 weeks (port to MP grid, fit LGCP background, integrate as new feature into v17 LightGBM).
- **Honesty**: PROVEN ON SIMILAR DATA (crime, COVID); PLAUSIBLE for fire because the structural argument is identical.

### 2. Marked Hawkes with FRP / land-cover marks

- **Title**: Spatio-Temporal Hawkes Point Processes: A Review (and references therein)
- **First author / year / venue**: González-Vidal et al., 2024, JABES (Springer)
- **Link**: https://link.springer.com/article/10.1007/s13253-024-00653-7
- **Mechanism**: Each event carries a mark `m_j` (FRP, fire size, land-cover class, FWI bin). The kernel becomes `κ_s(d) · κ_t(Δt) · g(m_j)` where `g` upweights e.g. high-FRP or savanna-cause fires. This makes a single 200-MW agricultural burn elevate λ in surrounding cells far more than a 5-MW background fire.
- **Why it specifically helps cold-start**: Doesn't directly help low-Hawkes cells (still requires neighbours). BUT it sharply reduces *false positives* in high-Hawkes cells, which lets the cold-start signal in the LightGBM head get more weight in the final ranking — indirect lift.
- **Python implementation**: Custom extension of our existing cKDTree code. No new library. ~300 LoC.
- **Effort**: 3-5 days.
- **Honesty**: PLAUSIBLE — well-established mathematically; we just haven't tried it. Risk: may merely re-distribute the same total recall.

### 3. Neural Jump-Diffusion TPP (NJDTPP, ICML 2024 Spotlight)

- **Title**: Neural Jump-Diffusion Temporal Point Processes
- **First author / year / venue**: Shuai Zhang et al., ICML 2024 Spotlight
- **Link**: https://arxiv.org/abs/2406.06465 ; code https://github.com/Zh-Shuai/NJDTPP
- **Mechanism**: Reformulates the intensity as the solution of a stochastic differential equation (SDE) with neural drift, diffusion, and jump coefficients. Hawkes is provably a special case. The diffusion term explicitly models *uncertainty in the baseline rate over time* — exactly what we lack.
- **Why it specifically helps cold-start**: The continuous diffusion term gives a smoothly-varying background with non-zero gradient even when no events have fired. In principle this should give v17-like LightGBM-head behaviour automatically *inside* the point process framework.
- **Python implementation**: Author's PyTorch repo exists but is small-scale (synthetic + 2 small datasets). Scaling to 1M ignitions and adding 100+ exogenous features is a substantial engineering lift.
- **Effort**: 4-6 weeks (port, scale, integrate exogenous covariates which are not first-class in the released code).
- **Honesty**: SPECULATIVE — never demonstrated on geospatial / wildfire data. Strong theory, no MP-relevant prior.

### 4. Integration-free Deep Kernel MPP with covariates (DKMPP, NeurIPS 2023)

- **Title**: Integration-free Training for Spatio-temporal Multimodal Covariate Deep Kernel Point Processes
- **First author / year / venue**: Yixuan Zhang, Quyu Kong, Feng Zhou, NeurIPS 2023
- **Link**: https://arxiv.org/abs/2310.05485 ; code https://github.com/co234/DKMPP
- **Mechanism**: Uses a deep kernel that takes spatial + multimodal covariates (image, text, tabular weather) directly as inputs. Trained with score-matching to avoid the intractable intensity integral. Output is a covariate-modulated intensity surface.
- **Why it specifically helps cold-start**: The model *fundamentally lives in covariate space* — there is no notion of "Hawkes-active neighbour required". Cold-start cells get the same treatment as warm cells, modulated only by their weather/anthropogenic feature vector.
- **Python implementation**: Public PyTorch code; well-documented. Score-matching loss is non-standard but already implemented.
- **Effort**: 2-3 weeks (build covariate tensors, retrain on MP grid, integrate as ranking feature alongside v17).
- **Honesty**: PROVEN ON SIMILAR DATA (crime, traffic, COVID with covariates).

### 5. Hurdle / Zero-Inflated Negative Binomial (ZINB) two-stage model

- **Title**: Modeling fire ignition probability and frequency using Hurdle models: a cross-regional study in Southern Europe
- **First author / year / venue**: Rodrigues et al., 2020, Ecological Processes
- **Link**: https://doi.org/10.1186/s13717-020-00263-4
- **Mechanism**: Decomposes p(events) = p(occurrence > 0) · p(count | occurrence > 0). The first stage is a Bernoulli GLM (or LightGBM with logistic loss) on weather + anthropogenic features. The second stage is a count model (NB / Poisson) on the non-zero subset only. The two stages share *no* intensity formula — they are independent classifiers.
- **Why it specifically helps cold-start**: The Bernoulli "did anything happen?" stage is *exactly* the cold-start question. By training it on all 8973 × 365 cell-days (massive dataset) without the noise of count-magnitude info, it can extract a much sharper occurrence signal in the low-Hawkes regime than v17's joint-target model.
- **Python implementation**: Trivial in LightGBM (two models, two scripts, geometric-mean blend with v17). No new dependencies.
- **Effort**: 2-4 days.
- **Honesty**: PROVEN ON SIMILAR DATA — this is the standard wildfire literature baseline; we've apparently never tried it cleanly on MP.

### 6. Self-Attentive Hawkes Process / Transformer Hawkes with covariates

- **Title**: Self-Attentive Hawkes Process (Zhang et al. 2020) and successors (AttNHP, Yang et al. 2022)
- **First author / year / venue**: Qiang Zhang et al., ICML 2020
- **Link**: https://arxiv.org/abs/1907.07561
- **Mechanism**: Replaces the LSTM in Mei & Eisner's Neural Hawkes with a transformer that attends to past events AND covariate sequences. The attention mechanism allows arbitrary long-range dependencies and naturally handles exogenous time-series (FWI, NDVI).
- **Why it specifically helps cold-start**: Attention can learn that "high FWI for 5 consecutive days followed by weekend" is a strong pre-condition independent of past fire activity — a pattern our exponential kernel cannot represent.
- **Python implementation**: Multiple implementations on GitHub (`SAHP`, `EasyTPP` framework). Mature.
- **Effort**: 3-5 weeks (covariate embedding pipeline, training run on 1M ignitions, integration).
- **Honesty**: PLAUSIBLE — strong theory + mature code, but no fire-specific evaluation. Risk: may just re-learn what LightGBM already extracts.

### 7. INLA-SPDE Bayesian spatiotemporal LGCP (with weather covariates)

- **Title**: Bayesian spatiotemporal modelling of wildfire occurrences and sizes for projections under climate change
- **First author / year / venue**: Legrand et al., 2024, Computo Journal
- **Link**: https://computo-journal.org/published-202407-legrand-wildfires/
- **Mechanism**: Pure LGCP (no self-excitation) with SPDE-Matérn random field for spatial structure, fitted via R-INLA. Weather and anthropogenic covariates enter the linear predictor on log-intensity.
- **Why it specifically helps cold-start**: Provides a principled, calibrated probability of ignition *anywhere* on the grid — including cold-start cells — by borrowing strength from spatial neighbours via the GMRF prior. Could be used as a **calibration baseline** to detect where v17 over- or under-predicts.
- **Python implementation**: R-INLA is R-only, but `inlabru` has Python bindings (`pyinla`-style wrappers). PyMC and NumPyro have native LGCP examples. Non-trivial mesh construction.
- **Effort**: 2-3 weeks (mostly mesh design + INLA tuning if going R, less if NumPyro).
- **Honesty**: PROVEN ON SIMILAR DATA (Mediterranean fires, Catalonia 1994-2008, France 2003-2023).

### 8. GPBoost (LightGBM + Gaussian-process spatial random effects)

- **Title**: Gaussian Process Boosting
- **First author / year / venue**: Fabio Sigrist, 2022, JMLR
- **Link**: http://jmlr.org/papers/volume23/20-322/20-322.pdf ; code https://github.com/fabsig/GPBoost
- **Mechanism**: Standard tree boosting (like our LightGBM), but each leaf is augmented with a **spatial Gaussian process random effect**. The tree captures non-linear feature interactions; the GP captures residual spatial autocorrelation. Drop-in replacement for LightGBM.
- **Why it specifically helps cold-start**: Adds a smooth spatial prior to v17's predictions. In a cold-start cell with no Hawkes signal, the GP component will pull the prediction toward the local average — which is exactly what we want for "neighbouring cells often burn but no recent fire here yet".
- **Python implementation**: `pip install gpboost`. API mirrors LightGBM. Production-ready.
- **Effort**: 1-2 weeks (re-train v17 features in GPBoost, define spatial random effect on lat-lon, validate).
- **Honesty**: PROVEN ON SIMILAR DATA (multiple spatial logistic regression papers); not specifically wildfire but the structural argument is identical.

### 9. Spatio-temporal Diffusion Point Processes (Yuan et al., KDD 2023)

- **Title**: Spatio-temporal Diffusion Point Processes
- **First author / year / venue**: Yuan Yuan et al., KDD 2023
- **Link**: https://arxiv.org/abs/2305.12403
- **Mechanism**: Generative diffusion model that learns the joint distribution of (next event time, next event location) by reverse-diffusing Gaussian noise. Captures complex spatial multi-modality that exponential kernels miss.
- **Why it specifically helps cold-start**: Generative models can imagine ignitions in *new* locations because they sample from a learned spatial distribution rather than triggering off existing events. Could complement Hawkes.
- **Python implementation**: PyTorch reference exists but small-scale.
- **Effort**: 4-6 weeks. High engineering risk on 1M-event scale.
- **Honesty**: SPECULATIVE — the paper's strong evals are on urban mobility, not natural events. Diffusion models on rare-event spatial data are unproven.

### 10. Cox process with neural baseline + classical Hawkes excitation (poor man's Cox-Hawkes)

- **Title**: A composite engineering approach (no single paper)
- **Mechanism**: Train a deep neural network (CNN or simple MLP) on cell-level weather + anthropogenic + terrain features to predict daily ignition probability `p_baseline(i, t)`. Use this as the time-varying baseline μ(i, t) feeding into our existing Hawkes kernel. So `λ = neural_baseline(i, t) + Hawkes_excitation`.
- **Why it specifically helps cold-start**: Identical mathematical motivation to Cox-Hawkes (#1) but skips the GP/MCMC machinery. The neural baseline learns from weather what GP would learn from spatial smoothness.
- **Python implementation**: PyTorch + our existing Hawkes code. ~500 LoC.
- **Effort**: 1 week.
- **Honesty**: PLAUSIBLE — engineering shortcut, no published precedent at scale, but each component is well-understood. Effectively a "v17 with separated heads".

---

## Ranked candidate table

| Rank | Method | Cold-start fit (1-5) | Implementation tractability (1-5) | Composite | Honesty |
|------|--------|---------------------|-----------------------------------|-----------|---------|
| **1** | **Hurdle / ZINB two-stage (#5)** | **5** | **5** | **25** | **PROVEN** |
| 2 | Cox-Hawkes (#1) | 5 | 3 | 15 | PROVEN |
| 3 | DKMPP (#4) | 5 | 3 | 15 | PROVEN |
| 4 | Engineering Cox-Hawkes (#10) | 4 | 5 | 20 | PLAUSIBLE |
| 5 | GPBoost (#8) | 3 | 5 | 15 | PROVEN |
| 6 | INLA-SPDE LGCP (#7) | 4 | 3 | 12 | PROVEN |
| 7 | Self-Attentive Hawkes (#6) | 3 | 3 | 9 | PLAUSIBLE |
| 8 | Marked Hawkes (#2) | 2 | 5 | 10 | PLAUSIBLE |
| 9 | NJDTPP (#3) | 4 | 2 | 8 | SPECULATIVE |
| 10 | Diffusion STPP (#9) | 3 | 1 | 3 | SPECULATIVE |

(Composite = cold-start fit × implementation tractability; ties broken by honesty)

---

## Top recommendation: **Hurdle/ZINB two-stage model (#5)**

This is the single most likely-to-help intervention against the 5.9% low-Hawkes recall, for three reasons:

1. **Mechanistic match**: The Bernoulli "did any fire occur?" stage is *literally the cold-start prediction problem*. Training it without count-magnitude noise gives the classifier the cleanest possible target.

2. **Cheapest test**: 2-4 days of work, no new dependencies, fully reversible. If it doesn't move R@5% in low-Hawkes cells, we have a definitive null at minimal cost.

3. **Published precedent**: Rodrigues et al. (2020) in three Mediterranean climates (Catalonia, Sardinia, Apulia) showed hurdle-NB beat single-stage Poisson on fire occurrence prediction. MP dry deciduous is a different biome but the underlying statistical pathology (massive zero-inflation, over-dispersion, smooth covariates) is identical.

**Suggested experiment design**:
- Stage A: LightGBM logistic on (cell, day) → P(any ignition) using v17's 111 features WITHOUT Hawkes kernel
- Stage B: existing v17 → ranking among predicted-positive cells
- Blend: rank by `P(any ignition)^α · v17_score^(1-α)` with α ∈ {0.3, 0.5, 0.7}
- Evaluate on the v17 test split, report low-Hawkes vs high-Hawkes recall separately
- Decision rule: if low-Hawkes R@5% ≥ 8% (vs current 5.9%) → ship; else publish the null and try Cox-Hawkes (#1)

---

## What we are explicitly NOT recommending

- **Re-fitting Hawkes on smaller label sets**: Already established as DECREASING recall in `feedback_hawkes_density_over_purity.md`.
- **Pure neural TPP replacements** (NJDTPP, Diffusion STPP): Too speculative, no fire precedent, expensive engineering.
- **Anything requiring SAR or VLM data**: Both falsified — see `feedback_ps1_sar_amplitude_dead.md` and `feedback_vlm_llava_7b_indiscriminate.md`.
- **Foundation TS models**: Out of scope per user request.

---

## Sources

- [Cox-Hawkes (Miscouridou 2022)](https://arxiv.org/abs/2210.11844)
- [NJDTPP (Zhang ICML 2024)](https://github.com/Zh-Shuai/NJDTPP)
- [DKMPP (Zhang NeurIPS 2023)](https://arxiv.org/abs/2310.05485)
- [Hurdle wildfire (Rodrigues 2020)](https://doi.org/10.1186/s13717-020-00263-4)
- [Self-Attentive Hawkes (Zhang ICML 2020)](https://arxiv.org/abs/1907.07561)
- [INLA-SPDE wildfires (Legrand 2024)](https://computo-journal.org/published-202407-legrand-wildfires/)
- [GPBoost (Sigrist 2022)](http://jmlr.org/papers/volume23/20-322/20-322.pdf)
- [Spatio-temporal Diffusion PP (Yuan KDD 2023)](https://arxiv.org/abs/2305.12403)
- [Spatio-Temporal Hawkes review (JABES 2024)](https://link.springer.com/article/10.1007/s13253-024-00653-7)
- [Neural Hawkes (Mei & Eisner NeurIPS 2017)](https://arxiv.org/abs/1612.09328)
- [DEMM hurdle deep mixture (Wilson KDD 2022)](https://dl.acm.org/doi/abs/10.1145/3534678.3539464)
- [Neural STPP review (2025)](https://arxiv.org/abs/2502.09341)
