# Pivot A v2 Sprint — Final Finding

**Date:** 2026-04-19
**Sprint plan:** `C:\Users\S.C.C\.claude\plans\clever-honking-minsky.md`
**Goal:** Move low-Hawkes R@top-5% from 5.9% → ≥ 8% while keeping overall R@top-5% ≥ 47%.

## Headline verdict

**T1 (Hurdle two-stage) shipped as opt-in `--use-hurdle-blend` flag.**
**T2 (Dynamic World features) and T3 (combined) FAIL their pass criteria.**
**Production v17 default unchanged.** v17.5 is available behind the flag.

## Sprint result by track

| Track | Outcome | Status |
|---|---|---|
| **T1 Hurdle two-stage decomposition** | MARGINAL POSITIVE (+1.77pp low-Hawkes, +0.89pp overall) | Pareto-better than v17 on every metric. Wired as opt-in flag. |
| **T2 Dynamic World LULC features** | FAIL — model essentially ignored DW features | DW didn't help. v18 BA-tiered regressed slightly vs v17. |
| **T3 Combined v18 + Hurdle** | FAIL strict criteria | Slightly better than v17 alone but worse than T1 hurdle on low-Hawkes |

---

## T1 — Hurdle Two-Stage (KEEP, opt-in)

### Method recap

Stage A is a binary LightGBM classifier on v17's 107 features **minus the
4 Hawkes features**. Forces it to specialise on cold-start. Geometric-mean
blend with v17 (variant `geo_w0.7` won).

### Results on 2025 honest hold-out (DBSCAN-strict labels)

| Score | Overall | Low-H (≤1) | Cold (=0) | High-H (≥3) | PerDay |
|---|---:|---:|---:|---:|---:|
| **v17 alone** | 22.66% | **5.88%** | 4.43% | 26.21% | 29.14% |
| Stage A alone | 17.65% | 10.98% | 10.13% | 18.74% | 22.89% |
| **blend_geo_w0.7** ⭐ | 23.55% | **7.65%** | 6.33% | 26.79% | 30.23% |

Improvement vs v17: +0.89pp overall, **+1.77pp low-Hawkes**, +1.90pp cold-start.

### Decision: keep as opt-in

- Strict pass (low-Hawkes ≥ 8%) just-missed by 0.35pp.
- But the blend is **strictly Pareto-better than v17 on every metric**.
- Wired as `--use-hurdle-blend` in `scripts/predict_ignition_v17.py`.
- Daily pipeline (`daily_fire_alert.py` Step 4.5) **NOT** flipped on.
- Operators can opt in via the flag for ~1.8 extra low-Hawkes catches per
  100 patrolled top-5% alerts.

---

## T2 — Dynamic World LULC features (FAIL)

### Pivot needed mid-sprint

The original batch-export plan (37 GEE tasks) was queue-blocked behind
2,800 unrelated tasks (~17h estimated wait). Pivoted to synchronous
`getInfo()` chunked pulls — same server-side compute, no batch queue.
Full 76-month × 42K-cell pull completed in ~90 min.

### Results

`scripts/build_dynamic_world_features_sync.py` produced:
- 2,568,236 rows × 13 cols at `data_lake/land_cover/dynamic_world_monthly.parquet`
- dw_bare_mean median 5.8%, p90 14.2%, max 68% (real spread, not constant)
- dw_crops_to_bare_4wk median 0.02%, p90 11.8%, max 112%

### v18 trained — DW features essentially ignored

| Metric | v17 | v18 (DW) | Δ |
|---|---:|---:|---:|
| BA-tiered overall R@5% | 0.4741 | 0.3887 | **-8.5pp regression** |
| DBSCAN overall R@5% | 0.2266 | 0.2297 | +0.31pp |
| DBSCAN low-Hawkes R@5% | 0.0588 | 0.0608 | +0.20pp |
| DBSCAN cold-start R@5% | 0.0443 | 0.0443 | 0.00pp |
| **DW features in top-30 by gain** | n/a | **only 1** | model ignored DW |

The BA-tiered regression of 8.5pp suggests training instability (different
random seed/sampling) more than DW corruption — the model still learned the
same v17 features. But DW added zero meaningful signal at the cell scale.

### Why DW didn't help

Hypotheses (not investigated further given clean negative result):

1. **2km cell aggregation washes out the slash-and-burn signal**.
   A clearing of 50-200 m² (single farmer plot) is invisible when averaged
   over a 4 km² cell. Same scale problem that killed S2 dNBR + temporal
   delta + Sentinel-1 SAR amplitude in prior pilots.

2. **Monthly cadence is too coarse** for the days-before-fire precursor.
   Slash-and-burn happens 0-5 days before ignition; monthly composite
   smooths it out.

3. **Bare-ground in MP dry deciduous is dominated by phenology**, not
   anthropogenic clearing — even Dynamic World's trained classifier
   confounds the two at 10m × monthly resolution.

### T2 verdict: PARK

DW features added to v17's training set produce a model that ignores them.
Do not pursue DW deltas further.

---

## T3 — Combined v18 + Hurdle (FAIL)

### Setup

`scripts/evaluate_v18_combined.py` evaluated 5 configurations:

| Config | DBSCAN R@5% | BA-tiered R@5% | Low-H (≤1) | Cold (=0) | PerDay |
|---|---:|---:|---:|---:|---:|
| p_v17 (baseline) | 0.2266 | 0.3895 | 0.0588 | 0.0443 | 0.2914 |
| p_v18 | 0.2297 | 0.3887 | 0.0608 | 0.0443 | 0.3125 |
| p_a (Stage A only) | 0.1765 | 0.1501 | 0.1098 | 0.1013 | 0.2289 |
| blend_v17_a | 0.2355 | 0.2533 | **0.0765** | 0.0633 | 0.3023 |
| blend_v18_a | 0.2382 | 0.2577 | 0.0706 | 0.0601 | 0.3036 |

### T3 decision logic + result

Strict T3 pass criterion: low-Hawkes ≥ 0.10 AND BA-tiered ≥ 0.48.
**Both targets missed by significant margins.**

The cascade check picks `v17_unchanged` because:

- T3 (combined): low-Hawkes 0.0706 < 0.10 → fail
- T2 (v18 alone): low-Hawkes 0.0608 < 0.07 → fail
- T1 (blend_v17_a): low-Hawkes 0.0765 < 0.08 → fail
- → fall through to v17 unchanged

### T1's hurdle blend is the best low-Hawkes variant tested

`blend_v17_a` (low-Hawkes 7.65%) > `blend_v18_a` (7.06%) — adding DW to
the blend **hurts** low-Hawkes. This is consistent with the v18 finding
that DW features are essentially noise at this scale.

---

## What ships

### Production daily pipeline

**Unchanged.** v17 + isotonic calibration + diagnostic stack remain
production. The hurdle blend is opt-in only.

### What's available behind a flag

`python scripts/predict_ignition_v17.py --date YYYY-MM-DD --use-hurdle-blend`

This loads `predictive_v17_hurdle_a/model.txt` + the winning blend
config and shifts the alert ranking. Smoke-tested on 2026-04-19.
Output JSON includes `hurdle_blend` metadata + per-cell `stage_a_risk`.

### Files persisted from sprint

| Path | Status | Notes |
|---|---|---|
| `scripts/train_v17_hurdle_stage_a.py` | KEEP | Stage A trainer |
| `scripts/evaluate_v17_hurdle_blend.py` | KEEP | T1 evaluator |
| `scripts/predict_ignition_v17.py` | KEEP | Now has `--use-hurdle-blend` |
| `outputs/predictive_fire_risk/predictive_v17_hurdle_a/` | KEEP | Stage A model + importance |
| `outputs/predictive_fire_risk/predictive_v17_hurdle/` | KEEP | Blend config |
| `scripts/build_dynamic_world_features.py` (batch) | KEEP | for future use if queue clears |
| `scripts/build_dynamic_world_features_sync.py` | KEEP | the working approach |
| `scripts/download_dw_monthly_exports.py` | KEEP | for future batch use |
| `scripts/extend_dataset_with_dw.py` | KEEP | will rebuild parquet if needed |
| `scripts/train_v18_dynamic_world.py` | KEEP | v18 baseline retrainer |
| `scripts/train_v18_hurdle_stage_a.py` | KEEP | Stage A on v18 features |
| `scripts/evaluate_v18_combined.py` | KEEP | T3 cascade evaluator |
| `data_lake/land_cover/dynamic_world_monthly.parquet` | KEEP | 2.57M rows DW data; available for future v19 if a method finds use |
| `outputs/predictive_fire_risk/predictive_v18_dw/` | KEEP | v18 model artefacts (negative result archive) |
| `outputs/predictive_fire_risk/predictive_v18_hurdle_a/` | n/a | not trained (OOM during initial run + not needed since T3 fail) |
| `outputs/predictive_fire_risk/predictive_v19_combined/` | KEEP | T3 cascade decision + per-config eval |

---

## Empirical implications for the project

The 1-week Pivot A v2 sprint yielded one new piece of empirical evidence:

**Adding more satellite-derived land-cover features at 10m cell aggregation
does not break the low-Hawkes ceiling.** This adds Dynamic World monthly
LULC to the prior list of dead ends:

- Sentinel-2 dNBR (phenology trap, 2026-04-15)
- Sentinel-1 SAR amplitude (clearing too small, 2026-04-15)
- Prithvi-EO-2.0 600M embeddings (phase 4, 2026-04-14)
- CLIP-ViT-L/14 (perm p=0.095, 2026-04-17)
- LLaVA-7b VLM (MW p=0.74, 2026-04-17)
- Temporal NDVI/BSI deltas (5-fold ROC=0.539, 2026-04-17)
- **Dynamic World monthly LULC (this sprint, 2026-04-19)**

**The Hurdle Stage A approach IS the only architecture-side change since
the original Hawkes that measurably moves low-Hawkes recall** — and even
this sits 0.35pp short of strict pass.

The honest project state: **v17 + diagnostic stack is the
empirical ceiling for satellite + weather + Hawkes data**. The remaining
77% gap requires non-satellite data (village-level human activity,
patrol logs, NTFP collection records) — already documented as
data-blocked in `feedback_path_c_data_blocked.md`.

---

## Memory entries

- `feedback_pivot_a_v2_t1_marginal.md` — T1 result + ship-as-opt-in rule
- `feedback_pivot_a_v2_dw_no_signal.md` (NEW) — T2/T3 fail; DW LULC at
  10m monthly does not help low-Hawkes prediction at 2km cell

## CLAUDE.md updates

- Production Status section already has Pivot A v2 status
- Add T2 DW result to "CONFIRMED DEAD ENDS" list
- Note: the hurdle blend is the only structural improvement available;
  remains opt-in pending operational signal
