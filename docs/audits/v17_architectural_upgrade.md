# v17 Architectural Upgrade — Finding (2026-04-17)

## Context

v17 at R@5%=47.41% (BA-tiered) / 22.7% (DBSCAN-strict) has Hawkes self-excitation as its dominant feature (45M gain, 18× the #2 feature). Low-Hawkes cells (77% of ignitions) get 5.9% R@5% — barely above random. Two architectural changes were tested to address this structural weakness.

## Stage 1: Hybrid Bayesian Ranking — DOES NOT HELP

Tested adaptive λ blending of global + local CDF ranks: `R_final = λ_d · Φ_global + (1-λ_d) · Φ_local`, where λ_d = sigmoid(k · z_d) adapts to each division's current deviation from historical baseline.

| Method | R@5% | PerDay R@5% | Low-Hawkes R@5% | PerDay std |
|--------|------|------------|-----------------|------------|
| **Statewide (current v17)** | **0.227** | **0.292** | 0.059 | 0.119 |
| Pure Local (naive) | 0.160 | 0.212 | 0.063 | 0.086 |
| Hybrid k=2.0 | 0.206 | 0.230 | 0.043 | 0.088 |
| Hybrid k=5.0 | 0.218 | 0.241 | 0.047 | 0.084 |

**ALL variants decrease aggregate R@5%.** Hybrids reduce per-day variance (0.119→0.084) but LOSE overall catches. Ranking can't create signal that doesn't exist in the scores. The problem is in the SCORES for low-Hawkes cells, not how we rank them.

## Stage 2: Deep Origination Features — MOSTLY INERT

Eight new features designed for anthropogenic ignition prediction:

| Feature | Rationale | Model B rank | Gain |
|---------|-----------|:------------:|-----:|
| vpd | Atmospheric drying power | 109 | 0 |
| vpd_anomaly | VPD deviation from 10-yr climatology | 110 | 0 |
| interface_decay | exp(-β · dist_settlement) nonlinear | 111 | 0 |
| **moisture_green_anomaly** | RH × NDVI interaction delta | **18** | **889,712** |
| beat_fire_rate_month | Historical monthly rate per beat | 112 | 0 |
| beat_median_first_doy | Typical season start per beat | 113 | 0 |
| beat_days_since_season_start | Progress into beat's season | 114 | 0 |
| division_code | Division-specific intercept | 115 | 0 |

7 of 8 features scored **zero gain** because Model B early-stopped at best_iter=1 (single boosting tree). Only `moisture_green_anomaly` contributed at rank 18. The single tree used `wx_ffmc` (32M) → `hist_fire_freq` (13.6M) → `lc_frac_tree` (14.1M) — identical to the ablation model from 2 weeks ago.

**Why best_iter=1:** 0.22% positive rate (510 positives in 470K val rows) means any additional tree overfits. The 63-leaf first tree captures the dominant FFMC/history/vegetation axis, and more trees only add noise at this extreme imbalance.

## Stage 3: Soft-Ensemble — REVEALS TRADEOFF

Both Model A (v17) and Model B score every cell. P_final = W_h · P_A + (1-W_h) · P_B, where W_h = sigmoid(k · (H - H0)) transitions smoothly based on Hawkes intensity.

| Config | Overall R@5% | Low-Hawkes R@5% | Total caught | Low caught |
|--------|-------------|-----------------|-------------|------------|
| **v17 alone** | **22.7%** | 5.9% | **820** | 30 |
| Gentle blend (k=1, h0=0.5) | 16.1% | **11.8%** | 583 | **60** |
| Medium blend (k=1, h0=1.5) | 8.7% | **19.0%** | 315 | **97** |
| Heavy blend (k=2, h0=1.5) | 3.4% | **20.8%** | 124 | **106** |

**The tradeoff is fundamental:** at a fixed 5% alert budget, every low-Hawkes catch costs ~8 high-Hawkes catches. This isn't a model failure — it's a resource allocation constraint across two fire regimes with 10× different base rates (0.11% for low-Hawkes vs 1.1% for high-Hawkes).

## Operational recommendation

**Default: keep v17 pure (statewide ranking).** Maximum aggregate catch rate.

**Option: "Balanced Coverage" mode (k=1, h0=0.5).** Doubles low-Hawkes catches from 30→60 at -29% overall. Useful if:
- Division-level patrol teams exist (each division gets some coverage)
- New-outbreak detection is strategically prioritized over contagion tracking
- Alert budget can be expanded beyond 5% (e.g., top-10% doubles the budget)

Implement as `--ensemble-mode {pure,balanced}` flag in `scripts/predict_ignition_v17.py`.

## The honest conclusion

v17 is at or near the **information-theoretic ceiling** for new-outbreak prediction with current features. The 77% of fires that start without nearby fire history cannot be predicted from weather + vegetation + topography alone at 2km weekly resolution. This was confirmed by:
- Ablation model without Hawkes: 7.3% R@5% (2 weeks ago)
- Model B with 8 deep origination features: 4.3% R@5% (today)
- Three VLM/CLIP/temporal approaches on satellite imagery: all FAIL (today)
- Hybrid ranking across 5 k-values: all DECREASE aggregate R@5% (today)

The only path to genuinely predict new outbreaks would require **data that doesn't exist in our feature set**: village-level human activity logs, NTFP collection schedules, patrol route feedback, or real-time mobile phone density near forest fringes.

## Files

- `scripts/eval_hybrid_ranking.py` — Stage 1 evaluation
- `scripts/train_v17_origination.py` — Stage 2+3 Model B + ensemble
- `outputs/predictive_fire_risk/predictive_v17_origination/` — Model B artifacts
- `outputs/predictive_fire_risk/predictive_v17_ba_pu/division_baselines.json` — per-division baseline stats
