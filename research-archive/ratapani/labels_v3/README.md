# Cleaner fire labels for the 2-day Ratapani model (labels_v3)

"Cleaner fire labels" thread, 14 Oct 2026. Research only. All scores are recall at 5 picks per real beat per day (94 beats), lean ensemble (classifier + lambdarank rank-average, lean_plus BASE inputs), LOSO 2017-24 and train 2017-24 -> test 2025-26. My `main` row reproduces SCORING.md (30.3 / 29.3 vs 30.2 / 29.5).

## Label variants
Same frame as SCORING.md everywhere: issue day t positive if the cell burns on t+1 or t+2, first burn per cell-season, negatives need t+2 <= last clear look.

| Key | What it is | Positives 2017-26 |
|---|---|---|
| main | SCORING.md rule (season scar windows, every window day positive) | 135k |
| union | season windows + per-alert event scars (cells >= 0.5 ha, <= 1.5 km from the alert) | 166k |
| dstrict / dlenient | union evidence, dated by a VIIRS point <= 400 m with scar in the cell (FIRMS + FSI 2025-26); positive on d-2, d-1 only; undated burns masked / kept as windows | 19k / 118k |
| truelead | FSI thread's true-lead strict labels (v1; 2017-24 only) | 11k |
| af_high_s / af_hm_s / af_hm_l | burn-scar thread's multi-sensor dating (`fire-alert-scars/out/af/dated_first_burns.csv`, 55% of first burns dated): high = S2/Landsat active fire or VIIRS <= 400 m; hm adds VIIRS 400-750 m; _s undated masked, _l undated kept | see script |

Files: `labels_v3.parquet`, `labels_v3_af.parquet`, `season_windows.csv`, `event_windows.csv`, `dated_cells.csv`; scripts in `scripts/` (build_labels.py, build_labels_af.py, train_matrix.py).

## Result 1: training on cleaner labels does not help
LOSO recall@5 (%), rows = label trained on, columns = answer key:

| train \ key | main | union | dstrict | truelead | af_high_s | af_hm_s |
|---|---|---|---|---|---|---|
| random | 16.6 | 18.9 | 24.2 | 19.2 | 21.1 | 19.7 |
| main | **30.3** | 29.8 | 43.5 | 40.0 | **45.4** | **38.8** |
| union | 29.9 | 30.2 | 44.2 | 39.3 | | |
| dstrict | 29.5 | 30.1 | 44.8 | 39.9 | | |
| truelead | 29.3 | 29.5 | 44.0 | 40.3 | | |
| af_high_s | 29.5 | 29.4 | 43.9 | 39.8 | 44.8 | 38.4 |
| af_hm_s | 29.8 | 29.8 | 43.9 | 40.2 | 45.1 | 38.8 |
| af_hm_l | 29.6 | 29.1 | 41.8 | 38.0 | 42.7 | 37.3 |

2025-26 test shows the same: every training label lands within ~1 point of `main` on every key (full table in results/train_matrix_results.json). Day-dated positives are few (2 per burn), so they carry less training signal than the blurred windows, and that cancels out what they gain in precision.

## Result 2: the model is better than the main score says, on fires we can date
Lift over random on each key with the standard model: main 1.83x, dstrict 1.80x, truelead 2.08x, af_hm_s 1.97x, **af_high_s 2.15x** (2.13x on 2025-26). On burns dated by an active-fire pixel inside the cell, the model catches 45% at 5 per beat per day against 21% by chance. Part of the high raw numbers on strict keys is easier ranking (masked days leave fewer candidates), so read the lift, not the raw recall.

## Result 3: label error from 0.34 m imagery: weak, not usable yet
Esri Wayback (release 2026_r09, z18) has Feb-Apr 2025 Legion/WorldView imagery over 2,129 of 3,614 cells. On 826 cells (300 season-scar cells burned <= 20 days before the image, 226 alert-only scar cells, 300 no-burn cells) a cell-vs-surroundings darkness/grey index separates season-scar cells from no-burn cells only weakly (AUC 0.58) and alert-only cells not at all (0.51). Eye checks: a 3-day-old burn shows plainly (grey ground, white ash lines), older ones are hard to call. The colour-balanced mosaic and canopy hide most litter burns, so this cannot yet give scar precision/recall. Alert-only scars (what `union` adds) look no different from unburned forest, a mild warning on those. Files: results/vhr_stats.csv, classify.py, stats.py.

## Other checks
- VIIRS point <= 300 m vs first season-scar window (Feb-Jun, 2017-26): 51% inside the window, 17% after it (reburn/spread), 8% before its start (median 17 days early: an earlier fire with no >= 0.5 ha scar, or a late-dated scar, as in the spread thread's smoke cases), 24% with no scar.
- Leads received, not yet used: FSI thread's true_lead_labels_v2 (day = window_start fix; my labels never had that clip), NOAA-20 archive (+33% fire cell-days), managed-burn tags, label-blind cells with <= 2 ha mappable forest.

## Bottom line
Label noise is not what holds the 2-day cell model at ~30%. Training on any cleaner label gives the same model. Cleaner labels are worth keeping as an **answer key**: on the best-dated fires the model is 2.1x random, not 1.8x.

## Undersized season rasters (spread thread, 15 Oct)
Yes, `main` and every dated variant inherit the season rasters (burn_windows.csv). `union` is already the polygon-informed version: it adds per-alert scar polygon cells (>= 0.5 ha, <= 1.5 km from the alert). 26% of polygon cell-seasons (5,218 in Feb-Jun) have no season window at all, and union has 23% more positive cell-days (166k vs 135k). Effect on the answer key: the lean model scores 30.2% on union vs 18.9% random (1.60x), below main's 1.83x; training on union instead of main changes scores by under 1 pt on every key. The 0.34 m imagery check could not tell polygon-only cells from unburned forest (AUC 0.51), though that check is weak overall. So a polygon-informed key adds real burns but makes the task harder, not the model better. A surround-free re-mapping of the rasters was not run here.

## Soft burn dates from the FSI thread (15 Oct)

Source: `ratapani/fsi/scouting/data/daily_dating/soft_dates.csv`. It narrows the first burn window of each cell-season using daily 300 m Sentinel-3 images (2019-23 and 2026), Landsat 7 (2017-23) and MCD64A1. 43% of burns were narrowed, and the mean window width fell from 6.5 to 4.6 days.

Keys are built by `scripts/build_labels_soft.py` and written to `labels_v3_soft.parquet`:
- `soft_all`: every burn, using its narrowed interval where one exists.
- `soft_n`: narrowed burns only.
- `soft_s3`: Sentinel-3-dated burns only.

`train_matrix.py` now merges these keys automatically. Results are in `results/train_matrix_soft_results.json`.

Recall@5 on the 94 beats. "Lift" is model recall divided by random recall.

| Key | Positives (LOSO) | Model LOSO | Random LOSO | Lift LOSO | Model 2025-26 | Random 2025-26 | Lift 2025-26 |
|---|---|---|---|---|---|---|---|
| main | 111,022 | 30.3 | 16.6 | 1.82x | 29.3 | 15.5 | 1.89x |
| soft_all | 91,967 | 30.7 | 17.1 | 1.79x | 28.8 | 15.6 | 1.85x |
| soft_n | 41,596 | 35.5 | 18.1 | 1.96x | 36.8 | 17.3 | 2.13x |
| soft_s3 | 14,090 | 40.4 | 19.6 | 2.07x | 37.8 | 22.4 | 1.69x |
| af_high_s (reference) | 9,685 | 45.4 | 21.1 | 2.15x | 38.6 | 18.1 | 2.13x |

Training on `soft_all` instead of `main` changes nothing. Scored against the main key it gives 29.9 vs 30.3 (LOSO), and 29.1 vs 29.3 (2025-26). This matches every earlier label variant: sharper dates make the answer key fairer, but they do not teach the model anything new.

As an answer key, the narrowed dates show the model to be about 2x random. The original windows show 1.8x. That is close to the VIIRS-dated key (2.15x), and it covers 4x as many burns, including fires VIIRS never saw. The 2025-26 Sentinel-3 test is small: 907 positives in 2026 only.
