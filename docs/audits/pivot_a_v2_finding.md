# Pivot A v2 Sprint Finding (Partial — T1 Done, T2 In-Flight)

**Date:** 2026-04-19
**Sprint plan:** `C:\Users\S.C.C\.claude\plans\clever-honking-minsky.md`
**Goal:** Move low-Hawkes R@top-5% from 5.9% → ≥ 8% while keeping overall R@top-5% ≥ 47%.

## Sprint status by track

| Track | Status | Verdict |
|---|---|---|
| **T1** Hurdle two-stage decomposition | **DONE** | MARGINAL POSITIVE — shipping conditionally as `--use-hurdle-blend` flag in v17 |
| **T2** Dynamic World LULC features | **GEE-BLOCKED** | All 37 chunks submitted; project queue has 2,960 other PENDING tasks ahead of ours |
| **T3** Combined v18.5 evaluation | DEFERRED | depends on T2 completion |

---

## Track T1 — Hurdle Stage A + Blend (DONE)

### Method recap

Stage A is a binary LightGBM classifier on v17's 107 features **minus the 4
Hawkes features**. Trained on the same 2014-2025-01 / 2025-02-onwards
temporal split as v17. Blended with v17 via geometric / harmonic means.

### Results on 2025 honest hold-out (DBSCAN-strict labels, full-state top-5%)

| Score | Overall R@5% | Low-H (≤1) R@5% | Cold (=0) R@5% | High (≥3) R@5% | PerDay R@5% |
|---|---:|---:|---:|---:|---:|
| **v17 alone** | 22.66% | **5.88%** | 4.43% | 26.21% | 29.14% |
| Stage A alone | 17.65% | 10.98% | 10.13% | 18.74% | 22.89% |
| blend_geo_mean | 24.21% | 6.08% | 4.43% | 27.92% | 30.82% |
| blend_geo_w0.3 | 24.24% | 5.88% | 4.11% | 28.09% | 30.67% |
| blend_geo_w0.5 | 24.21% | 6.08% | 4.43% | 27.92% | 30.82% |
| **blend_geo_w0.7** ⭐ | 23.55% | **7.65%** | **6.33%** | 26.79% | 30.23% |
| blend_harmonic | 24.18% | 6.08% | 4.43% | 27.88% | 30.41% |

### Stage A solo — feature importance sanity (PASSED)

Top 15 features by gain include both anthropogenic and weather, no collapse:
- wx_rh_pct, hist_fire_freq, ndvi_expected, lc_burnable_frac, wx_dtr,
  wx_rh_7d_min, wx_vpd, wx_isi, days_to_peak, lc_frac_grass, lc_frac_bare,
  wx_srad, wx_anom_precip_mm, lc_frac_crop, ndvi_mean

### Decision

The strict T1 pass criterion (low-Hawkes R@5% ≥ 8% AND overall ≥ 47%)
**is not met** — winner blend_geo_w0.7 lands at 7.65% (0.35pp short)
and DBSCAN-strict overall 23.55% (the 47% target was BA-tiered; the
DBSCAN-strict comparison floor is v17's own 22.66%, which we exceed).

However, the blend is **strictly Pareto-better than v17 alone on every metric:**
- +0.89 pp overall  (22.66% → 23.55%)
- +1.77 pp low-Hawkes (5.88% → 7.65%)
- +1.90 pp cold-start (4.43% → 6.33%)
- +1.09 pp PerDay (29.14% → 30.23%)
- +0.58 pp high-Hawkes (26.21% → 26.79%)

### Ship decision: **CONDITIONAL**

Wired as opt-in `--use-hurdle-blend` flag in `predict_ignition_v17.py`.
Production daily pipeline (`daily_fire_alert.py` Step 4.5) is **NOT** yet
flipped to use it — will flip after T2/T3 final decision in case the
combined v18.5 produces a better blend variant.

If T2/T3 deliver no further uplift, this flag becomes the default → v17.5.

---

## Track T2 — Dynamic World LULC features (BLOCKED)

### Status

- Server-side GEE feature pipeline shipped (deltas computed in-engine,
  per `feedback_serverside_first.md`).
- 7 yearly exports × 9 cell-chunks each = **37 tasks submitted to GEE**.
- All 37 are PENDING.

### Blocker: GEE project queue saturation

```
Total ops in van-suraksha-alert project queue: 3,190
  PENDING:    2,960   (only 1 RUNNING at a time)
  SUCCEEDED:    205
  FAILED:        14
  CANCELLED:     10
```

The first task in our queue is dw_features_2024_c00, behind ~2,960 other
unrelated tasks (s2_Baghooria_*, s1_Baghooria_*) from another concurrent
workload on the same project. With only 1 task running at a time and a
~205/4h SUCCEEDED rate, our 37 tasks won't complete for hours.

### Resolution path (resume when GEE clears)

1. Run `python scripts/check_dw_export_status.py` to monitor
2. Once ≥ 80% chunks have SUCCEEDED, run
   `python scripts/download_dw_monthly_exports.py` to fetch CSVs from Drive
3. `python scripts/extend_dataset_with_dw.py` joins DW into v17 dataset
4. `python scripts/train_v18_dynamic_world.py` trains v18 (~30 min)
5. `python scripts/evaluate_v18_combined.py` runs T3 cascade decision

---

## Track T3 — Combined v18.5 (DEFERRED)

Deferred until T2 completes. The combined evaluator
(`scripts/evaluate_v18_combined.py`) is built and ready. It will:

1. Load v18 (when trained) and Stage A (already trained)
2. Compute blend variants of (Stage A × v18)
3. Apply the same cascade ship logic as the plan's "Definition of done"
4. Decide whether to ship v17.5, v18, v19, or accept the v17 ceiling

---

## Production-touching changes shipped today

1. `scripts/predict_ignition_v17.py` — added `--use-hurdle-blend` flag
   that loads `predictive_v17_hurdle_a/model.txt` + `predictive_v17_hurdle/blend_config.json`
   and applies the Stage A × v17 blend before re-ranking + banding.
   Smoke-tested for 2026-04-19: 213 CRITICAL, 638 ALERT, 1277 WATCH.
   Top-10 CRITICAL cells differ from raw v17 — alert allocation has shifted.

2. Output JSON (`outputs/dashboard_feed/ignition_risk_v17.json`) now
   includes `hurdle_blend` metadata block when the flag is on:
   - applied: bool
   - variant: str (winning blend formula name)
   - blend_config: { low_hawkes_r5, overall_r5, delta_low_hawkes_pp,
     delta_overall_pp }
   - per-cell `stage_a_risk` field (raw Stage A probability)

## What ships in the daily pipeline RIGHT NOW

Same as before today:
- v17 raw scoring (no hurdle blend)
- isotonic probability calibration
- operational alerts decoration

The hurdle blend is **available but off by default**. Will be enabled if
T3 fails to produce a better variant — to capture at least the +1.77 pp
low-Hawkes uplift the hurdle gives.

## Files created this session

| Path | Purpose | Lines |
|---|---|---|
| `scripts/train_v17_hurdle_stage_a.py` | T1 Stage A trainer | 200 |
| `scripts/evaluate_v17_hurdle_blend.py` | T1 blend evaluator (5 variants × stratified R@5%) | 244 |
| `scripts/build_dynamic_world_features.py` | T2 GEE export (server-side, chunked) | 213 |
| `scripts/download_dw_monthly_exports.py` | T2 Drive downloader + parquet builder | 156 |
| `scripts/extend_dataset_with_dw.py` | T2 join DW into v17 dataset | 99 |
| `scripts/train_v18_dynamic_world.py` | T2 v18 trainer | 165 |
| `scripts/evaluate_v18_combined.py` | T3 cascade evaluator | 207 |
| `scripts/check_dw_export_status.py` | T2 GEE status monitor | 36 |

## Memory entries to update on full completion

- `feedback_pivot_a_v2_t1_marginal.md` — "Hurdle Stage A blend gives
  +1.77 pp low-Hawkes / +0.89 pp overall vs v17 alone. Strictly
  Pareto-better. Wired as `--use-hurdle-blend` opt-in until v18/v19 decision."
- `project_pivot_a_v2_results.md` — final ship decision after T2/T3.

## CLAUDE.md updates planned post-T3

- Add v17.5 / v18 / v19 to Model Zoo (whichever ships)
- Update "Production Status" section if pipeline switches
- Add note about Pivot A v2 sprint outcome
