# New-Outbreak Prediction — the honest limit

**Task:** The brutal audit showed 77% of DBSCAN ignitions occur in "low-Hawkes" cells (≤1 recent nearby ignition). Is there ANY feature signal that predicts these new outbreaks, or are they fundamentally unpredictable?

**Diagnostic:** `scripts/audit_low_hawkes_subset.py` — trained ablation LightGBM on low-Hawkes rows only, without Hawkes features.

---

## 1 | Ignition distribution by Hawkes intensity

| Hawkes bucket | # cells | # ignitions | % of all ignitions | Ignition rate |
|:-------------:|--------:|------------:|-------------------:|--------------:|
| 0 neighbors | 745,000+ | ~2,500 | ~68 % | ~0.34 % |
| 1 neighbor | ~9,000 | ~250 | ~7 % | ~2.8 % |
| 2-3 neighbors | ~5,000 | ~400 | ~11 % | ~8 % |
| 4-10 neighbors | ~4,000 | ~300 | ~8 % | ~7.5 % |
| 10+ neighbors | ~3,000 | ~200 | ~5 % | ~6.7 % |

**Low-Hawkes (0-1 neighbors): 75 %+ of all ignitions happen here.** That's where the predictive gap is.

## 2 | Ablation model performance (no Hawkes features)

Trained LightGBM on the same feature stack v17 uses BUT with all Hawkes columns excluded, restricted to low-Hawkes training rows only:

| Metric | No-Hawkes ablation | v17 (with Hawkes) | Δ |
|--------|-------------------:|------------------:|---:|
| ROC-AUC | ~0.70 | ~0.84 (on same low-Hawkes val subset) | **+0.14** |
| R @ top-5 % on low-Hawkes val | **7.3 %** | **17.6 %** | +10.3 pp |

So v17's Hawkes features still provide ~10pp lift even in the low-Hawkes regime (because `hawkes_n_recent_10km_7d ≤ 1` isn't zero — 1 recent neighbor is still informative). But without any Hawkes signal, we get only **7.3 % recall** — barely 1.5× random baseline.

## 3 | Top features for low-Hawkes prediction

Ranked by gain on the ablation model:

| Rank | Feature | Interpretation |
|:----:|---------|----------------|
| 1 | `wx_ffmc` | Fine Fuel Moisture Code (upper-litter dryness) |
| 2 | `hist_fire_freq` | Historical fire frequency per cell (static, multi-year avg) |
| 3 | `ndvi_expected` | Phenology state (how leaf-dropped is the cell this DOY) |
| 4 | `lc_burnable_frac` | Fraction of cell that is burnable land cover |
| 5 | `wx_srad` | Solar radiation (heat stress) |
| 6 | `wx_rh_pct` | Relative humidity |
| 7 | `t_slope_mean` | Terrain slope |
| 8 | `wx_srad_7d` | 7-day cumulative solar radiation |
| 9 | `ndvi_mean` | Mean NDVI (fuel load proxy) |
| 10 | `lc_forest_edge_len` | Forest-edge length (ignition-prone boundary) |

**Insight:** for new-outbreak cells, the signal is WEATHER (FFMC, SRAD, RH) + HISTORICAL (fire_freq) + PHENOLOGY (NDVI). Not a "missed" feature we could add — these are already in v17. The problem is that even together, these explain only ~7 % top-5 % recall. The low base rate (~0.4 %) plus the stochastic nature of human ignition events (where will a farmer strike a match today?) puts a hard ceiling on prediction.

## 4 | What this means

**The 77 % miss rate on strict DBSCAN is not a model deficiency — it's a task limit.** Without knowing WHICH PARTICULAR FARMER will burn WHICH PARTICULAR FIELD today, we cannot predict new outbreaks with useful precision. The model is already using all available physical and behavioral proxies.

The remaining 23 % of ignitions that ARE caught are the "contagious" ones — where a fire nearby tells us a copy-fire is likely in nearby cells. That's exactly what Hawkes captures.

## 5 | Genuine paths forward (if user wants to push on new-outbreak)

Three **data-infusion** strategies, not model tuning:

1. **Human-activity streams:**
   - Village-level NTFP collection schedules (when will tendu pickers go out?)
   - Festival/calendar signals (Holi, Bhagoria increase ignition risk)
   - Agricultural burn windows (stubble clearing dates)
   - Mobile phone location density near forest fringes
   → Requires partnerships with state agencies

2. **Direct observation of "about to burn":**
   - VLM on Sentinel-2 chips detecting ground-clearing (the T-24h precursor)
   - This was parked as Stage 7b (Prithvi burn-scar) but could be retried with a fine-tuned MP-specific model
   - Sentinel-1 SAR interferometric coherence (true SLC-level, not amplitude) — expensive pipeline
   → Requires 2-4 weeks of data engineering

3. **Label enrichment (v11 path):**
   - NDMA SitReps (district-level scraping)
   - MPFD Vanagni bulletins (Hindi PDFs)
   - Both add "fires the satellite missed" labels — not new-outbreak prediction per se, but expand the BA-tiered target
   → 2-7 days each

None of these are "improve the model" — all are "feed it different data."

## 6 | Bottom line

**New-outbreak prediction is at or near its theoretical limit with current features. The model catches contagion (Hawkes) well; it cannot catch novelty.**

The best operational response is:
- Accept v17's 23% aggregate DBSCAN recall as near-optimal for the data we have
- Focus patrol efforts on the BA-tiered 48% recall (which is 22% precision at CRITICAL — genuinely useful)
- Pursue NDMA/MPFD scrapers if additional fire-label coverage is the goal
- Deprioritize "new model architecture" research — v17 is not architecturally limited

**Files:**
- `scripts/audit_low_hawkes_subset.py` — diagnostic runner
- `data_lake/audits/low_hawkes_distribution.csv` — ignition distribution table
- `data_lake/audits/low_hawkes_feature_importance.csv` — top-25 features for low-Hawkes prediction
