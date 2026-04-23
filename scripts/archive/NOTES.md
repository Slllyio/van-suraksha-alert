# scripts/archive/ — older experimental + superseded scripts

This directory holds scripts that are kept for **lineage / reproducibility / postmortem**
reasons but are NOT called by any production pipeline. They are NOT deleted because:

1. The Model Zoo in [`CLAUDE.md`](../../CLAUDE.md) cites their results
2. They are referenced in [`docs/audits/`](../../docs/audits/) postmortems
3. Past papers + figures (notebooks/, paper/) load their outputs

**Never `rm -rf` this directory without first checking if any docs/notebooks/paper rely on it.**

## Archive policy (set 2026-04-23)

A script belongs in `scripts/archive/` if and only if:
- It is **not referenced** by any of:
  - `scripts/daily_fire_alert.py` (daily orchestrator)
  - `scripts/ci_static_ops_checks.py` (23-check CI gate)
  - `scripts/test_operational_pipeline.py` (23-check portal+schema gate)
  - `scripts/run_2026_backfill.py` / `scripts/validate_2026_season.py` / `scripts/generate_2026_season_report.py`
  - `scripts/build_operational_alerts.py` / `scripts/predict_ignition_v17.py` / `scripts/verify_daily_run_artefacts.py`
  - `dashboard/v3/serve.py`
  - `Makefile` / `.github/workflows/*` / `config.yaml` / `CLAUDE.md` / `README.md`
- AND it falls into one of these categories:
  - Leading-`_` debug/diagnostic scripts (`_debug_*`, `_validate_*`, `_eval_*`, `_smoke_test_*`, etc.)
  - Older versioned ablations (v4-v16 trainers, v6/v6e/v7/v8/v9/v15 predictors, v18 dynamic-world ablations)
  - Postmortem analysis scripts (`forensic_v6_evidence.py`, `production_fire_audit_v6_real.py`, etc.)

Production-touching v17.5 / 2026 scripts stay in `scripts/` root.

## What's in here (categorized)

### Leading-`_` debug + analysis (~30 files)
`_abm_*`, `_check_*`, `_compare_*`, `_debug_cell2fire_*`, `_eval_v7_*`, `_eval_v8_*`,
`_smoke_test_*`, `_validate_*`, `_threshold_calibration_fix.py`, `_naive_baseline_test.py`,
`_diagnose_v6e_failures.py`, `_deep_audit_100m.py`, etc.

### Older versioned ablations (training + evaluation)
- LightGBM trainers: `train_lgbm_v4.py`, `train_lgbm_v5.py`
- v6/v6e family: `train_v6e_*` (kept under v6e_live since baseline), `build_v6e_cell_chips.py`,
  `extract_prithvi_embeddings_v6e.py`, `benchmark_v6_vs_fwi_vs_catboost.py`, `forensic_v6_evidence.py`,
  `production_fire_audit_v6_real.py`, `compare_v6_v7_v8.py`, `mp_v6_administrative_rankings.py`,
  `export_v6_visuals.py`
- v7/v8 ignition trainers: `train_predictive_v7_ignition.py`, `train_predictive_v8_ntfp.py`,
  `train_v7_fuel.py`, `train_v8_ignition_dbscan.py`
- v9-v16 trainers: `train_v9_*`, `train_v10_*`, `train_v11_friction_hawkes.py`,
  `train_v12_graph_hawkes.py`, `train_v13_glcm_ignition.py`, `train_v14_hydro_ignition.py`,
  `train_v16_sar_coherence.py`
- v17 origination + ablations: `train_v17_2_ba_pu_newhawkes.py`, `train_v17_origination.py`
- v18 PARKED ablations (Pivot A v2 T2/T3 failures): `train_v18_calendar.py`,
  `train_v18_dynamic_world.py`, `train_v18_hurdle_stage_a.py`, `train_v18_news_pu.py`,
  `evaluate_v18_combined.py`
- Older predictors: `predict_ignition_v9.py`, `predict_ignition_v15.py`
- Earlier validators: `exhaustive_2019_validation_v2.py`, `exhaustive_2019_validation_v3.py`,
  `causal_validation_v4.py`
- Earlier label factory: `ai_label_factory_v2.py` (v3 stays in `scripts/`)

## How to "un-archive" a script

If you need to revive one (e.g. for a paper rebuttal):

```bash
git mv scripts/archive/<file>.py scripts/
# update any docs that referenced scripts/archive/<file>.py
git commit -m "revive: <file>.py for <reason>"
```

Don't symlink — that creates platform-specific breakage (Windows ≠ Unix link semantics).
