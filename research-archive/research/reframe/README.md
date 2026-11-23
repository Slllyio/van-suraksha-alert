# Rethinking the 2-day question (Ratapani, 14 Oct 2026)

This is research, not a product. The aim was to test whether a different 2-day question carries more predictable signal than "which 25 ha cell burns". Every number below is leave-one-season-out over 2017-24 ("LOSO"), plus a model trained on 2017-24 and tested on 2025-26. All % chances are isotonic-calibrated using held-out predictions from other seasons only. Scripts are in `scripts/` and numbers are in `results/*.json`.

## Headline

**Changing when checks happen beats changing where they happen.** Officers keep the same number of checks per season, but do more of them on the days the model forecasts as big fire days and fewer on quiet days. That more than doubles the catch at the same total effort.

| Check rule (same season total: 5 × 94 beats a day on average) | Main labels LOSO | Main labels 2025-26 | True-lead labels LOSO | Burns caught at least once, LOSO |
|---|---|---|---|---|
| Random, 5 per beat per day | 16.6% | 15.3% | 18.8% | – |
| **Today's rule:** 5 per beat per day (lean model) | 29.5% | 28.9% | 38.9% | 42.6% |
| Same daily total, shared across beats | 43.4% | 40.3% | 57.6% | 58.8% |
| Daily total follows the calendar only (seasonal curve) | 57.9% | 60.0% | 74.6% | 70.8% |
| **Daily total follows the 2-day fire forecast, shared across beats** | **63.1%** | **63.7%** | **79.9%** | **77.7%** |
| Daily total follows the forecast, split evenly across beats | 43.1% | 45.9% | 57.6% | 59.4% |
| Perfect model, daily total follows true burning | 94.8% | 98.2% | – | – |

How the forecast rule works:
- Each day's total is today's forecast of new burning in the next 2 days, divided by the training seasons' average. It is limited to between 0.25× and 3× normal and rescaled so the average stays at 470 checks a day.
- Nothing from later in the season is used (`scripts/exp_budget.py`, `scale_nopeek`).
- On peak days this means up to about 15 checks per beat, and in quiet weeks about 1.

**With a ceiling on checks per beat per day** (forecast-driven daily total, checks still go to the top cells across the sanctuary, `results/budget_caps.json`):

| Max checks per beat per day | 5 | 8 | 10 | 15 | 25 | no limit |
|---|---|---|---|---|---|---|
| Catch, LOSO / 2025-26 | 28.4 / 27.4% | 39.2 / 38.3% | 44.7 / 44.0% | 54.1 / 54.0% | 61.3 / 62.0% | 63.1 / 63.7% |
| Checks actually used per day (of 470) | 274 | 348 | 384 | 441 | 471 | 472 |

A ceiling of 10 checks per beat per day still gives about 44%, against 29.5% for today's fixed 5. It also uses fewer checks overall, because the busy beats hit the ceiling on peak days.

**Most of the gain is the calendar.** Concentrating checks in the weeks that burn (mid-March to April) takes the catch from 29.5% to about 58-60%. The daily forecast adds another 4-5 points on top. The gain holds on the clean true-lead labels and when each burn counts only once, so it is not an artefact of blurred scar dates (`results/budget_robustness.json`).

## Question by question

### 1. Is the next 2 days a big fire day for the sanctuary? Yes, and this is predictable (`results/big_day.json`)

"Big" means the top 20% of days by new burning.

| Target | Model | AUC | Brier skill vs base rate | Share of the period's burning on the model's top 20% of days (ceiling) |
|---|---|---|---|---|
| New burned cells, LOSO | calendar only | 0.83 | 0.21 | 43% (72%) |
| | **full model** | **0.88** | **0.32** | **52%** |
| New burned cells, 2025-26 | full model | 0.89 | 0.38 | 62% (73%) |
| VIIRS points, LOSO | full model | 0.92 | 0.48 | 65% (76%) |

Notes:
- **Signal source:** almost all of the skill over the calendar comes from sanctuary activity in the last 1-7 days. Persistence alone matches the full model. Weather adds a little on its own and nothing on top of activity.
- **Calibration:** the % chances follow the observed rates. For example, when the model says 42%, 46% of those days were big.
- **Count forecast** (Poisson model with negative-binomial intervals): the 80% intervals contain the true count on 83-89% of days and the 95% intervals on 93-97%. That passes the Ontario-style coverage check. Spearman correlation with the true count is 0.78-0.83, against 0.69-0.80 for the calendar alone.

### 2. Which beats burn in the next 2 or 7 days? Mostly climatology (`results/beats.json`)

| Beat-day target | Calendar + beat size + beat history: AUC | FSI 2021 fire-prone map | Full model: AUC | New burned cells inside the top 10 of 94 beats a day (ceiling) |
|---|---|---|---|---|
| Any burn in 2 days, LOSO | 0.82 | 0.82 | 0.84 | 31% vs 27% calendar (77%) |
| Any burn in 2 days, 2025-26 | 0.84 | 0.84 | 0.85 | 32% vs 26% (74%) |
| Any burn in 7 days, LOSO | 0.84 | 0.84 | 0.85 | 30% vs 26% (58%) |

Notes:
- The beat-level % chances are well calibrated. Predicted 0.40 against observed 0.41 for 7 days; above 0.7 they are too high.
- **The beat question carries little signal beyond "big beats, in peak season, that burned in past years".** Recent activity and the lean model add only 2-5 points.
- Splitting checks across beats by the beat model's chance (40.7%) does no better than splitting by summed cell scores (43.4%).

### 3. Will a burning area spread, and where? A modest signal (`results/spread.json`)

Each fire is a group of VIIRS cells (S-NPP, NOAA-20 and NOAA-21) active on a day. "New ground" means cells within 1.5 km that have not burned yet this season.

- **Will it spread** (any new cell burns in the next 2 days): 34-41% of fires spread. AUC is 0.68-0.73, against 0.60-0.63 for the calendar. Brier skill over the calendar is +7-12%, and the chances are calibrated.
- **Where:** checking the model's top 5 cells around each fire catches 46% of the new burning in 2017-24 and 43% in 2025-26. That compares with 34% / 30% at random, 36% / 31% by nearest distance, and an 87% / 83% ceiling.

Notes:
- Once ground that has already burned is masked, distance to the fire barely matters inside 1.5 km. Adjacent unburned cells burn slightly *less* often (4% against 7%), probably because they are the gaps a fire skipped.
- Per-cell dryness (the lean score) is what ranks the cells.
- A night-detection flag (suggested by the FSI thread's scouting, `ratapani/fsi/scouting/spread_from_active_fire.md`) adds about +0.5-1 point. It is included in the numbers above.
- **Direction cues do not hold up at 2 days.** Both were tested as the cosine between a cell's bearing from the fire and the fire's recent shift. The 2017-24 and 2025-26 changes below are to the top-5 catch.

  | Shift measured from | 2017-24 | 2025-26 |
  |---|---|---|
  | Latest two satellite passes (the spread thread's best cue) | +0.5 | -1.5 |
  | Last 3 days of detections | +1.3 | -0.9 |

  Neither cue is in the numbers above.

### 4. FSI's 2021 fire-prone map as a baseline

Within Ratapani the map ranks areas sensibly: least-prone ground burned 8.5% a season and extremely prone ground 24%. But it adds nothing over the calendar plus beat size and history:
- Beats: AUC 0.82 for both.
- Spread "where": AUC 0.52, against 0.72-0.75 for the model.

The per-cell mean class is in `results/cell_fsi_prone.csv`.

## Pushing the cell ranking further (15 Oct)

A headroom check (`scripts/headroom.py`, `results/headroom.json`) showed that the daily total is already as good as a perfect forecast: swapping in the true day total gives 60-65%, about the same as the forecast's 63-64%. A perfect cell ranking under the forecast total gives about 100%. So the only remaining lever is which cells get checked across the sanctuary each day.

`scripts/pooled_ranker.py` trains a sanctuary-wide cell ranker. Its inputs are the lean score plus inputs from recent fires: distance to the nearest VIIRS point (all satellites) in the last 1, 3 and 7 days, points within 1.5 km, share of the 1.5 km ring already seen burned, the beat's recent points, the cell's burn history in other seasons, forest share, the FSI class and day of year. It uses a LightGBM classifier and a lambdarank model with the day as the query, then averages their ranks. Checks follow the forecast-driven daily total with no peeking, as above.

| Labels | Lean score | Ranker |
|---|---|---|
| Main labels, LOSO | 63.1% | **69.2%** (up every season, +1.6 to +17 pts) |
| Main labels, 2025-26 | 63.7% | **72.1%** |
| Fixed 5 per beat per day, LOSO / 2025-26 | 29.5 / 28.9% | 34.6 / 34.6% |
| Burns caught at least once, LOSO / 2025-26 | 77.7 / 76.6% | 89.1 / 90.0% |
| **True-lead strict labels, LOSO** | 79.9% | **81.4%** |

**Caution:** on the clean true-lead labels the gain shrinks to +1.5 points. Most of the gain on the main labels comes from checking cells next to a fire seen in the last few days. Many of those cells are probably already burning or burned, and their scar window was dated late. The ranker is a better tool for "where is fire on the ground in the next 2 days" (including fires already started) than for "where will a new fire start". Distance to fires in the last 7 days is the strongest input after the lean score. Results: `results/pooled_ranker.json` and `results/pooled_ranker_robustness.json`.

## What this means

- **The 2-day signal is mostly temporal.** At sanctuary level the model knows well which days will be big (AUC about 0.9). Within a day it knows only modestly which cells or beats will burn.
- **A cell-level model is worth most when paired with a flexible daily budget.**
  - Fixed 5 per beat per day caps the catch at a 64% ceiling. A daily budget that follows the forecast lifts the ceiling to about 95% and the model to about 63%.
  - Keeping a per-beat cap but letting it rise and fall with the forecast still gives 43-46%, with no cross-beat sharing.
- **Not tested: field practicality.** A 3× surge on peak days is a staffing question, not a modelling one.

## Caveats

- **Labels:**
  - Main labels are first burns from the scar windows, with the burn day taken from VIIRS where one falls inside the window (68% of burns) and the window midpoint otherwise.
  - VIIRS targets use S-NPP only, so the sensor is the same every season.
- **Big-day threshold:** the 80th percentile of training seasons.
- **Calibration:** maps are fitted on other seasons' held-out predictions. In LOSO those predictions come from models that saw the held-out season, a small optimism in calibration only, not in AUC or catch.
- **Lean scores:** this work uses the shared parquet predictions (`ratapani/scoring/pipeline_lean_pred_*.parquet`). It has not been rerun on the v2 road features.
