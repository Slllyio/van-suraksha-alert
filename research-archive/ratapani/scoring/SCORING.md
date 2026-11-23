# How the pipeline thread scores Ratapani burn-scar models

This is the rule behind the pipeline thread's "27.5% at 5 per beat per day" result (first-burn labels, best model, 14 Oct 2026).

## v2 headline (16 Oct 2026, after the prediction review): each dated fire counted once

**Why the change.** The fresh review (`research/prediction-review/REVIEW.md`) showed that the old cell-day score below counts each burn on every day of its 2-8 day scar window, so about half of its "hits" come after the fire has already happened. It also rewards listing the same cells every day. From now on the headline is the question a guard cares about: **was this square on the beat's list 1 or 2 days before the fire started?**

**Rule** (`v2/dated_once.py`, results `v2/results_dated_once.json`):
- Burns: the first burn of each square each season (scar windows say *where*), dated by the first S-NPP VIIRS point within 750 m (*which day*). Same dating as the FSI thread's true-lead v2 labels (all 5,826 of theirs match to the day), extended to 2025-26. Fire days Feb 17 to Jun 15. 5,138 burns in 2017-24, 1,773 in 2025-26. Each burn counts once.
- Lists: 5 squares per real beat (94 beats) per day.
- Live candidate pool: any square except those whose scar is confirmable by yesterday (window end + 25 days). The old scorer let models choose only from squares known to be still unburned.
- Model: the honest (leak-fixed) lean classifier. Baselines: random, and burn history (how often the square burned in other seasons).
- "Skip g": a square listed in the last g days is not listed again. This spreads the same checks over more squares.

| Rule (5 per beat per day) | Warned 1-2 days before, 2017-24 | Warned 1-2 days before, 2025-26 | Listed at least once in the 7 days before, 2017-24 |
|---|---|---|---|
| Random | 21.5% | 20.9% | 53.2% |
| Burn history only | 16.8% | 15.7% | 16.8% |
| Model, same top 5 every day (old practice) | 31.8% | 30.0% | 39.1% |
| **Model, skip squares listed yesterday** | **47.6%** | **45.0%** | 55.8% |
| Model, skip last 2 days | 40.9% | 40.6% | 66.7% |
| Model, skip last 5 days | 27.6% | 28.3% | 83.9% |
| Random, skip last 2 days | 22.8% | 21.5% | 59.3% |

- **New headline:** with yesterday's squares skipped, the model's list warns **47.6% of fires 1-2 days ahead (2.2x random) in held-out seasons, and 45.0% (2.2x) on 2025-26.** Every season 2017-26 is above random.
- Burn history alone is worse than random here, because it lists the same squares all season.
- Longer skips trade early warning for coverage. Skipping 5 days puts 84% of fires on a list at least once in the week before, but only 28% in the last 2 days.
- New starts vs spread: 25% of dated burns had a VIIRS point within 1.5 km in the 3 days before. On the other 75% (new starts) the model is just as good: 48.6% / 45.2% with skip-yesterday. So the gain is not just "next to yesterday's fire".

**Old vs new, side by side**

| | Old headline (cell-days, scorer pool) | New headline (each dated fire once, live pool) |
|---|---|---|
| Lean model / ensemble | 30.1% vs random 16.6% (1.8x); leak-fixed lean 29.0% | 31.8% vs 21.5% (1.5x), same list daily |
| Best rule | (no rotation tested) | 47.6% vs 21.5% (2.2x), skip yesterday |
| 2025-26 | 29.4% vs 15.4% | 45.0% vs 20.9% (2.2x) |

**% per square** (`v2/calib.py`, `v2/results_calib.json`). Target: this square's first burn of the season starts tomorrow or the day after. Calibrated leave-one-season-out with isotonic regression.
- The chance is small. The average square-day is 0.6% (2025-26: 0.9%). The top 1% of squares each day come true **3.4%** of the time (predicted 3.7%), which is **5.7x normal** (2025-26: 4.5%, 5.2x).
- Reliability is good up to about 5%. Above 10% the model overstates (says 16%, observed 6.7%), so the map caps at 7%.
- Skill over a plain day-of-year average is only 1.7% (Brier skill; 2025-26: 2.2%). Burn history x day-of-year has none. The model knows *where*, not *when*.
- Season totals are still off 2x in either direction (e.g. 2024 predicted 2,101 starts, observed 618; 2022 predicted 828, observed 1,977). I tried an in-season correction from the count of VIIRS points so far this season. It made skill worse (1.7% to 0.5%) and blew up 2021 (3,126 vs 1,460). Not adopted. **Show "times normal" per square, not a season-wide count.**
- Caveats: undated burns (no VIIRS point) are left out. 2025-26 dating uses near-real-time S-NPP files.

Everything below this section is the old rule, kept for comparison. Don't quote its numbers as the headline.

## Labels

`scar_labels.py H MODE` (copy in this folder) builds the labels from the research thread's `burn_windows.csv` and `clear_calendar.parquet`. The standard setting is H = 2 and MODE = `first`.

- **Grid:** the 3,614 cells of `/mnt/project-files/ratapani/grid_500m.geojson`, indexed by `cell_id`.
- **Seasons:** 2017 to 2024. Issue days run Feb 1 to Jun 20 of each season (`season` = months 2 to 6).
- **Positive:** issue day t is positive for a cell when a burn window (ws, we] with burned = 1 overlaps (t, t+2]. That covers every t in [ws-1, we-1].
- **Valid (scored) cell-days:**
  - A cell-day counts only when t+2 is no later than the cell's last clear look that season (clear_frac >= 0.5).
  - MODE `first`: only the first burn window per cell-season counts. All days after its window end are masked.
  - Masked cell-days are neither positive nor negative.
- **Coverage:** about 55% of season cell-days are valid, with a base rate of 4.65%.

## Pseudo-beats

There are 68 k-means clusters of cell centroids, each about 12 km² with 39 to 74 cells. They are built with sklearn KMeans(68, n_init=4, random_state=0) on the full 500 m box centroids in EPSG:32643, with cells kept in grid-building order. The assignment is in `pseudo_beats_pipeline.csv` (cell_id, pseudo_beat).

## Metric: recall at 5 per beat per day

The metric is computed separately on each held-out season, then pooled over all of them:

```
for each issue day t, for each pseudo-beat b:
    candidates = cells of b that are valid on t
    listed     = top 5 candidates by score
    hits      += number of listed cells that are positive on t
total = number of valid positive cell-days, summed over t
recall    = hits / total
precision = hits / (5 x 68 x days)   # invalid cells sort last but still count when a beat has fewer than 5 valid cells
```

**The unit is the positive cell-day, not the cell-window.** A scar whose window spans 5 days creates up to 6 positive issue days. Catching it on 3 of them counts 3 of 6. Long windows (cloudy spells) therefore carry more weight than short ones.

## Validation

Leave-one-season-out over 2017 to 2024. Each season is predicted by a model trained on the other 7. The burn-history prior is also rebuilt without the held-out season.

## Other numbers reported

- **AUC and PR-AUC:** over all valid cell-days.
- **where-AUC:** the mean over days of the within-day AUC across valid cells.
- **Recall at 10 per beat:** the same rule with 10 cells listed per beat per day.

## Code

The code is in the container at `/tmp/claude-0/tr/scr/research.py`: `beat_metrics()` (lines ~167-177), `set_labels()` and `loso()`. It is not in a shared location yet.

## Differences to check against the research thread's 18%

- **Counting unit:** cell-days (here) vs cell-windows.
- **Held-out seasons:** LOSO 2017-2024 (here) vs 2025-26.
- **Positive rule:** all first burns (here) vs ignitions plus spread.
- **Pseudo-beats:** check whether both threads use the same 68 clusters.

A cell-window version is easy to add: count a window as caught if its cell was listed on any issue day in [ws-1, we-1]. The pipeline thread can report both if the research thread prefers windows.

## Secondary number: day-shared budget (added 14 Oct)

Akkshay's budget is up to 5 checks per beat per day, so the fixed 5-per-beat recall above stays the headline. As a secondary research number, report the research thread's day-shared allocation. It uses the same 340 picks per day (5 x 68), split across beats in proportion to each beat's summed predicted rate, with at least 1 and at most 15-25 per beat. It breaks the per-beat cap, so it shows what a looser rule would gain, not what beats can do today. See `/mnt/project-files/research/ratapani-ignition/results/dynamic_budget_shared_rule.json`.

- **Lean model:** 33.4% on held-out seasons and 30.4% on 2025-26, up from 28.6% and 26.5% at a fixed 5 per beat.
- **Ceiling with fixed 5 per beat:** a perfect model reaches 65%, because 36-39% of positive cell-days fall on beat-days with more than 10 burning cells.
- **Ceiling with pooled picks:** a perfect model reaches 90%.

## True-lead variant (added 14 Oct, after the FSI thread's check)

Scar windows are 2-5 days wide, so the main rule also counts days after the fire happened but before the next clear image showed it. On 6,064 first burns where VIIRS dates the fire inside the window, those after-fire days are 49% of positive cell-days. Only 25% are true 1-2 day leads (`/mnt/project-files/ratapani/fsi/README.md`, check 3).

True-lead rule, reported beside the main rule:
- Fire day d is the first VIIRS detection within 750 m of the cell inside its first-burn window (ws, we], allowing ±1 day.
- **Positive:** issue days t = d-2 and d-1, when the cell is valid.
- **Masked:** every other day of that window, from ws-1 to we-1.
- **Strict version:** windows with no VIIRS date are masked entirely.
- **Lenient version:** windows with no VIIRS date keep the main rule.
- Negatives, valid days, beats and the 5-per-beat budget are unchanged.

The FSI thread is building these combined labels (scar for where, VIIRS for which day). The pipeline thread will score its models on them when they land, and retrain on true-lead positives to see whether that adds any timing skill. On the FSI thread's first cut, the lean model catches 30.5% on true-lead days, 29.0% on days 3+ ahead and 32.7% on after-fire days. The random baseline is about 15% for all three, so the lift holds on true forecasts but there is no timing skill inside a window.

## Real beats (added 14 Oct)

Akkshay supplied the MP beat layer (E:\MP_Merge\Mp_Beat_Merge.shp, 8,973 beats). 97 beats touch Ratapani. Each 500 m cell is assigned to the beat covering most of it, which leaves 94 beats with 1 to 100 cells each (mean 38). Most are in Obedullahganj division; a few fringe beats are in Sehore and Bhopal.

Files in `/mnt/project-files/ratapani/beats/`:
- `cell_beat.csv`: cell_id to beat_uid, where beat_uid = DID-RID-BID.
- `beats_table.csv`: division, range, beat name, beat area and area inside the AOI.
- `score_beats.py` and `results_real_beats.json`: the scorer and its results.

Beat outlines are on Akkshay's PC at E:\FIRE\ratapani\beats_ratapani.geojson.

**Real beats replace the 68 pseudo-beats as the main scoring unit from now on.** The rule is unchanged: 5 picks per beat per day among valid cells. Fringe beats with fewer than 5 valid cells use fewer picks, so the total is about 400 picks a day instead of 330. In the shared-budget version, the 5 x 94 = 470 daily picks are split by each beat's summed score, with 1 to 25 per beat.

Lean model results (recall@5, LOSO 2017-24 unless noted):

| Labels | Pseudo-68 fixed | Real-94 fixed | Real-94 random | Real-94 shared |
|---|---|---|---|---|
| Main | 28.6% | 29.5% | 16.6% | 43.4% |
| Main, 2025-26 test | 26.5% | 28.9% | 15.3% | 40.3% |
| True-lead strict | 38.0% | 38.9% | 18.8% | 57.6% |
| True-lead lenient | 30.4% | 31.7% | 17.8% | 43.7% |

The shared budget does much better on real beats because real beats vary much more in size and fire load than the pseudo-beats do. It still breaks the 5-per-beat cap, so it stays a secondary number.

## Current baseline to beat (added 14 Oct, late)

From now on the reference model is the **lean ensemble**. It is a rank average, per issue day, of two models:
- the lean LightGBM classifier (`pipeline_lean_model.py`)
- a LightGBM lambdarank model on the same 47 inputs. Each beat-day is one query, and the truncation level is 8.

The research thread built it in `/mnt/project-files/research/ratapani-ignition/scripts/lean_plus.py`, and the results are in `results/lean_plus_results.json`. Its leak audit found the lean inputs clean.

Recall at 5 per beat per day on the 94 real beats:

| Model | LOSO 2017-24 | 2025-26 | LOSO recall@10 |
|---|---|---|---|
| Lean classifier | 29.8% | 28.7% | 49.0% |
| **Lean ensemble (classifier + lambdarank)** | **30.2%** | **29.5%** | **49.5%** |
| Lean ensemble, roads v2 (current reference) | 30.1% | 29.4% | n/a |

The lift is small (+0.4 to +0.8) but it shows up on every split. Year-to-year spread is about ±2 points, so a new idea should beat the ensemble on most seasons, not only on the pooled number.

These additions gave nothing beyond noise on top of the lean classifier: Hawkes self-exciting kernels, dryness slopes, neighbour means and lambdarank on its own. Adding them to the ensemble reaches 30.4%, which is not worth the extra inputs.

## Beat check against FSI's own tags (added 14 Oct)

FSI's Fire Point Search alerts carry the beat and compartment that FSI assigns. I compared 1,068 of these alerts (Nov 2025 onward), covering 512 grid cells, with `cell_beat.csv`. The script is `beats/fsi_beat_key.py`. The results are in `beats/cell_fsi_key.csv` (cell to FSI division, range, beat and compartment) and `beats/fsi_key_check.json`.

- **Interior cells:** cells away from beat borders agree 100% (263 cells).
- **Border cells:** cells on a beat border agree 77%. A 500 m cell can straddle two beats, and FSI tags each point with the beat it falls in.
- **Verdict:** `cell_beat.csv` is consistent with FSI's beat layer and stays as the scoring key.
- **Compartments:** these are now known for the 512 cells that had alerts (244 compartments). Covering the rest of the sanctuary would need the compartment polygons (MPFD server, login required).

## Road distance fix (added 14 Oct, late)

Scouting found that OpenStreetMap holds almost no forest roads inside Ratapani. That left the old road inputs measuring the wrong thing: the lean model's `dist_road_km` had a median of 3.1 km, and the research thread's `dist_track` a median of 10.5 km.

`features/roads_features_v2.parquet` combines OSM with Microsoft Road Detections. These are 25,239 segments from the 2025-04-28 Southern Asia file, covering 77.25-78.15 E and 22.75-23.25 N, so they reach the west edge of the grid. The raw extract is in `features/ms_roads_77.25-78.15E_22.75-23.25N.tsv`, and the script is `features/roads_v2.py`.
- `dist_road_km` is the distance to the nearest road of either source. Its median falls to 0.81 km.
- `road_km_in_cell` takes the larger of the two sources' road lengths, so roads mapped by both are not counted twice.

Effect on the lean classifier (real beats, recall at 5): 29.5% to 29.6% on LOSO, and 28.9% to 28.9% on 2025-26. The fix corrects the input but does not change the score. Use v2 from now on. `dist_track` in `ee/proximity.csv` should be replaced by v2's `dist_road_km`.

## True-lead labels v2 (added 14 Oct, late)

The FSI thread fixed a one-day dating bug, so use `/mnt/project-files/ratapani/fsi/true_lead_labels_v2.parquet` from now on. Burns detected on a window's first day had been dated one day late; 1,123 of 5,826 dated cells move one day earlier. The rule above is unchanged.

Rescored on real beats, LOSO 2017-24, recall at 5 per beat per day (script `beats/truelead_v2.py`, results `beats/results_truelead_v2.json`):

| Labels | Lean classifier | Lean ensemble | Random |
|---|---|---|---|
| True-lead strict, v1 | 38.9% | 40.1% | 18.8% |
| **True-lead strict, v2** | **39.5%** | **40.7%** | 20.0% |
| True-lead lenient, v1 | 31.7% | 32.4% | 17.8% |
| **True-lead lenient, v2** | **31.9%** | **32.6%** | 18.0% |

The fix moves every number up by less than one point. The lift over random stays about 20 points on strict labels.

## Second answer key: best-dated burns (added 14 Oct, late)

The "Cleaner fire labels" thread showed that training on cleaner labels does not move the score (see `ratapani/labels_v3/README.md`). Its best-dated labels do make a sharper **answer key**, so from now on every model is reported on two keys:

1. **main**: the rule at the top of this file. It stays the headline.
2. **af_high_s**: `labels_v3/labels_v3_af.parquet`, columns `pos_af_high_s` and `valid_af_high_s`. Burns are dated by a Sentinel-2 or Landsat active-fire pixel, or a VIIRS point within 400 m, inside the cell. Only the 2 days before that date count as positive, and undated burns are masked.

Read the lift over random, not the raw recall: the masked days leave fewer candidates, which makes ranking easier on this key.

**Scorer:** `beats/score_keys.py <pred.parquet>` scores a prediction file on both keys next to the lean ensemble, the deep model, and their rank blend.

Joint 9-reserve deep model (seasons 2018/20/22/24, real beats, recall at 5):

| | main key | af_high_s key |
|---|---|---|
| random | 16.2% | 19.9% |
| lean ensemble (roads v2) | 30.1% | 44.2% |
| joint deep model | 30.0% | 39.1% |
| **deep + lean ensemble** | **31.4%** | **44.2%** |

Full LOSO 2017-24 (all 8 seasons, added once the odd seasons finished): main key 30.1% lean ensemble, 30.0% deep, **31.3% blend** (blend higher in all 8 seasons); af_high_s key 44.6% lean ensemble, 39.6% deep, 44.5% blend. Predictions: `/tmp/claude-0/tr/pred_pooled_joint_*.parquet` (pipeline container; copied to `beats/pred_pooled_joint_loso.parquet`).

On the main key the blend gains 1.2 points and improves every season. On the best-dated key the deep model alone is 5 points weaker and the blend adds nothing. The deep model's gain is in spreading risk over the blurry scar windows, not in picking the actual fire day. Check this key before calling any deep model an improvement.


## In-season Prithvi (Oct 15)

Prithvi-EO-2.0-300M-TL, frozen. Each 10-day step d from Feb 11 to Jun 21, 2017-2026, sees three HLS composites (d-20, d-10, d; each is the median of clear looks in the 15 days before), plus time and location. The cell embedding (1024-d) is reduced to 16 PCA components, which keep 61% of the variance. Features are the latest step at or before t-1 and the change over about 30 days. Same lean classifier, same seeds, with and without these features. Real beats, 5 per beat per day.

| | Main key LOSO | Main key 2025-26 | af_high_s LOSO | af_high_s 2025-26 |
|---|---|---|---|---|
| Lean classifier | 29.6% | 28.9% | 43.9% | 38.4% |
| + Prithvi | 29.6% | 28.7% | 44.2% | 38.5% |
| Lean ensemble + classifier (rank sum) | 30.2% | 29.5% | 44.8% | 39.7% |
| Lean ensemble + Prithvi classifier | 30.4% | 29.5% | 45.3% | 39.1% |

Prithvi takes 16% of the model's split gain but adds no recall. Per season it is up in 3 of 8 and down in 5. It mostly duplicates the per-cell S2/Landsat dryness inputs (nbr/ndvi change over 30 days). The PC round 15 gain (+3 points over AlphaEarth with VIIRS fire-point counting) came from a model with no per-cell in-season dryness. Pack: `ratapani/prithvi_dyn/prithvi_dyn_pca16.npz` (steps, X[140, 3614, 16]). Scripts are in the same folder. A/B script: pipeline container `scr/prithvi_ab.py`, copied to `ratapani/prithvi_dyn/prithvi_ab.py`.

Substitution check: the same classifier with all per-cell dryness inputs (s2d_*) removed scores 25.5% LOSO and 23.9% on 2025-26 (main key), and 35.3% / 32.2% on af_high_s. Adding Prithvi to that model gives 27.8% / 27.2% (main) and 41.1% / 35.4% (af_high_s). So Prithvi recovers about half of what the dryness inputs give (2.3 of 4.2 points on the main key). It reads the same drying signal, but less well than the per-cell indices from clear looks.

Night-pass dating check (Oct 15, after the fuel thread's timing fit; script beats/night_first.py): of 12,407 VIIRS-dated first burns (af key source), the earliest VIIRS detection within 750 m is a night pass for 33% (31% for high-confidence). For after-midnight night firsts (4,057), the label day equals the UTC date (the previous IST day, which suits the ~15 h ignition lead) in 52% of cases and the IST date in 34%. So about 11% of all VIIRS-dated burns may be keyed one day late. That shifts which issue days are positive by a day for those burns, but it does not add or remove burns.

## Season window: Feb 15 to Jun 15 (Akkshay, Oct 15)

Akkshay: the real fire season is Feb 15 to Jun 15, and January fires are not of interest. From now on, report the score on issue days Feb 15 to Jun 15 alongside the Feb 1 to Jun 20 window used above, and use Feb 15 to Jun 15 for the all-MP model. Training may still use Feb 1 to Jun 20 days. Script: `beats/window_check.py`.

| Lean ensemble, real beats, 5 per beat per day | Feb 1 - Jun 20 | Feb 15 - Jun 15 |
|---|---|---|
| LOSO 2017-24 | 30.1% (random 16.6%) | **31.5%** (random 17.6%) |
| 2025-26 | 29.4% (random 15.3%) | **29.2%** (random 15.4%) |

The Feb 15 to Jun 15 window holds 83% of positive cell-days in 2017-24 and 96% in 2025-26. The lift over random is the same in both windows (1.8x to 1.9x).

## Leak check: scars counted before they were confirmable (Oct 15, from the spread audit)

The lean model's "scars already seen" inputs (`aoi_new7`, `aoi_season`, `nb1/nb2_new7`, `nb1/nb2_season`) counted a scar from its `window_end`, the first clear image showing it. But the burn-label detector only calls a pixel burned if the NBR drop persists over the next 25 days (`research/ratapani-burn-labels/README.md` step 3), so on day t some of those scars were not yet confirmable. The dryness inputs also dropped clear looks that fall inside a later burn window, which uses the future label.

Retrained the lean classifier (`lag_check.py`) with scars counted only from `window_end` + lag. Real 94 beats, 5 per beat per day, full Feb 1-Jun 20 window:

| Lean classifier | Main LOSO | Main 2025-26 | af_high_s LOSO | af_high_s 2025-26 |
|---|---|---|---|---|
| As before (lag 0) | 29.5 | 28.9 | 44.1 | 39.1 |
| Lag 7 days | 29.4 | 28.7 | 43.6 | 38.3 |
| Lag 25 days | 29.0 | 28.7 | 42.8 | 40.1 |
| **Lag 25 + keep all clear looks (honest)** | **29.0** | **28.6** | **43.1** | **39.7** |
| No seen-scar inputs at all, keep all looks | 29.3 | 28.7 | 43.6 | 38.1 |

- The leak was small: about 0.3-0.5 points on the main key and about 1 point on af_high_s LOSO; 2025-26 af went up, so the change is within noise there.
- Once honest, the seen-scar inputs add nothing: dropping them scores the same. Their apparent value came from the early look.
- The burn-history prior is built from whole other seasons, so the 25-day lag does not apply to it. (In LOSO it includes later seasons by design; the 2025-26 test uses only 2017-24.)
- The lean ensemble's ranker uses the same inputs; inferred, not rerun: expect a similar ~0.5 point drop. Headline numbers elsewhere in this file are the lag-0 versions; read them as about half a point high.
- Rule from now on: any "already burned this season" input uses scars from `window_end` + 25 days, or provisional detections that a live system would actually have.

## Fuel map v3 and mahua as inputs, on the v2 rule (16 Oct)

`v2/fuel_cells.py` puts fuel map v3 on the 500 m grid by day: litter from canopy x shed amount x leaf-fall timing x burn factor from prior seasons only, with no in-season resets. `v2/fuel_mahua_model.py` is the honest lean model plus fuel (litter now, end-April potential, leaf-fall share), plus mahua (FSI "flusher" share and green-up stats), or both, with and without burn history. Scored with `v2/score_v2.py` (each dated fire counted once, warned 1-2 days before, 5 per beat):

| Model | Same list daily, 2017-24 / 2025-26 | Skip yesterday, 2017-24 / 2025-26 |
|---|---|---|
| Base (honest lean) | 31.8 / 30.0 | 47.6 / 45.0 |
| + fuel | 31.9 / 30.4 | 47.0 / 44.2 |
| + mahua | 32.3 / 30.6 | 47.7 / 45.3 |
| + fuel + mahua | 31.0 / 29.6 | 47.5 / 44.6 |
| No burn history | 31.8 / 30.9 | 47.4 / 44.8 |
| No burn history + fuel + mahua | 32.1 / 30.6 | 47.9 / 44.0 |

**Neither the fuel map nor mahua adds anything, even without burn history** (all within ±0.8 points, which is run-to-run noise). The model's own per-square dryness and burn prior already carry what they know. This matches the FSI thread's AUC check (mahua +0.001 with history). Fuel stays useful for fire behaviour (spread, intensity), not for predicting where fire starts.
