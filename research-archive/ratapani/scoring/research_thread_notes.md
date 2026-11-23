# Research thread: scoring under SCORING.md, and a cell-window variant

Written by the "Fire prediction research" thread, 14 Oct 2026. Scorer: `/mnt/project-files/research/ratapani-ignition/scripts/pipeline_score.py` (re-implements SCORING.md: H = 2, MODE first, valid = t+2 <= last clear look, 68 pipeline pseudo-beats, issue days Feb 1 - Jun 20; labels extended to 2025-2026 from the same burn_windows.csv / clear_calendar.parquet).

## Research-thread combined model (ignition + spread Poisson rate), trained 2017-2024, scored 2025-2026

| | recall@5 | precision@5 | recall@10 |
|---|---|---|---|
| Random | 13.8 % | 3.6 % | 27.3 % |
| Combined model | 24.8 % | 6.6 % | 44.4 % |
| Ignition inputs only | 24.9 % | 6.6 % | 44.1 % |

606,578 valid cell-days, 24,297 positives (base rate 4.0 %). Per season recall@5: 24.8 % (2025), 24.9 % (2026). Full numbers: `/mnt/project-files/research/ratapani-ignition/results/pipeline_rule_2025_26.json`.

Leave-one-season-out 2017-2024 of the same model (done): recall@5 **25.9 %** (random 14.8 %), precision@5 7.9 %, recall@10 45.1 %; per season 2017 26.3, 2018 29.0, 2019 27.3, 2020 20.1, 2021 25.6, 2022 25.2, 2023 22.3, 2024 25.4. Base rate 4.65 %, matching SCORING.md. File: `/mnt/project-files/research/ratapani-ignition/results/pipeline_rule_loso.json`. So the pipeline's 27.5 % and this 25.9 % are now on the same rule. Grid and beats check: both threads use the 3,614-cell grid; the research thread's own k-means beats agree with `pseudo_beats_pipeline.csv` at adjusted Rand 0.95, and the scorer above uses the pipeline's file.

## Proposed cell-window variant (optional second number)

Unit = first burn window per cell-season (ws, we]. A window is caught if its cell is listed in its beat on **any** issue day in [ws-1, we-1] on which the cell is valid. Recall = windows caught / windows. This weights each scar once, whatever the cloud gap, and is what the research thread's "strict/lenient" patch scores approximate. Precision stays as in SCORING.md.

## Ensemble check (research thread, 14 Oct, `/mnt/project-files/research/ratapani-ignition/results/ensemble_results.json`)

Rank-average of pipeline_lean and the research combined model, per beat-day: LOSO 28.1 % (pipeline alone 28.5 %, research 25.9 %); 2025-26 27.0 % (26.5 %, 24.8 %). Top-5 picks overlap 45-46 %, within-beat Spearman 0.54-0.56. No complementary signal: the pipeline model already carries what the research model finds.

## Oct 14 15:45Z: additions on the lean model (research thread)

Rebuilt lean in research/ratapani-ignition/scripts/lean_plus.py: 29.8% LOSO / 28.7% 2025-26 on real beats (yours 29.5 / 28.9). Hawkes self-exciting kernels (τ 2/7/21 d, σ 1/3/8 km), dryness slopes + neighbour means + within-beat rank, and lambdarank each land within ±0.4 of base. Only consistent lift: rank-average of the classifier and a lambdarank model on the same features, +0.4 to +0.8 on every split (30.4 / 29.5, recall@10 49.6 vs 49.0). Cheap to add if you want it. Full table: research/ratapani-ignition/README.md, results/lean_plus_results.json. Leak audit: your lean code is clean.
