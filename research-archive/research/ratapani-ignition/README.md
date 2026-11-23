# Where and when do new fires start in Ratapani?

A study of **new ignitions** (fires that start with nothing burning nearby), built on the burn-scar labels in `../ratapani-burn-labels/`. Done 14 Oct 2026 in the "Fire prediction research" thread, as a different angle from the pipeline thread's one-model-per-cell-day approach. Research only; no operational output.

## Why ignitions

The pipeline thread found that fires spreading from a burn nearby are almost all caught, and that brand-new fires are the open problem. So this study separates the two using the 20 m scar geometry, which only the scar labels allow, and models new ignitions as a daily rate per 500 m cell (a Poisson point process, fitted on interval-censored scar windows), with spread left for a separate model.

## Method

1. **Scar patches.** Burned pixels of one season sharing the same date window are grouped into 8-connected patches: 12,806 patches of ≥ 2 ha over 2017-2026. For each patch, the distance to the nearest burn that appeared in the 7 days before the patch's window (and up to its end) is measured at 100 m resolution. A patch is a **new ignition** if that distance is over 1 km. `patches.csv` carries the split at 0.5, 1, 2 and 5 km.
2. **Cell windows.** For every 500 m cell and every pair of consecutive clear looks (≤ 20 days apart, ≥ 50 % of the cell clear), one row: did a new-ignition patch first show in this cell in that window? Cells reached by spread in the window are left out of the fit. 1.15 M rows, 12,519 ignitions, median window 5 days.
3. **Inputs.** Static: land cover shares, elevation, slope, aspect, distance to built-up, cropland, forest edge and sanctuary boundary (ESA WorldCover, Copernicus DEM). Fuel: years since the cell last burned (from the 2017-2026 scars), share burned in the last 1 and 3 years, share burned so far this season. Daily, sanctuary-wide: NASA POWER temperature, humidity, wind, rain and dryness, calendar flags (weekend, Holi ± 3 days, mahua collection 1 Mar-15 Apr, tendu 20 Apr-25 May), and the burnt area and new ignitions of the previous 7 days from the scars themselves.
4. **Model.** LightGBM, Poisson objective, offset = log(window days), trained on 2017-2024, scored on 2025-2026.
5. **Scoring.** *Where:* each day, rank cells inside each of 68 pseudo-beats (~12 km², k-means; real beats not available) and keep the top 5. A new-ignition patch is caught if its main cell is listed on the last day it was seen unburned. *When:* Spearman correlation between the model's sanctuary-wide daily rate and the daily count of new ignitions (each patch spread over its window).

## Results, 2025-2026 held out (935 new-ignition patches)

| Ranking inside each beat | New ignitions caught at 5 cells per beat per day |
|---|---|
| Random | 12 % |
| Cell's long-run burn frequency (2017-2024) | 14 % |
| **Ignition model, all inputs** | **20 %** |
| without static landscape | 14 % |
| without fuel history | 14 % |
| without weather / calendar / activity | 19 % / 19 % / 18 % |

| Sanctuary-wide daily timing | Spearman with daily ignition count, 2025 / 2026 |
|---|---|
| Seasonal curve only (day of year) | 0.48 / 0.53 |
| **Ignition model, all inputs** | **0.72 / 0.70** |
| without weather | 0.64 / 0.65 |
| Static and fuel only (no daily inputs) | ~0 |

Weather, calendar and activity are sanctuary-wide, so they can only change *when*, not *where within a beat*. Landscape and fuel history decide *where*; weather decides *when*.

### What drives new ignitions (observed rates, 2017-2026, ignitions per 100,000 cell-days)

- **Interior, not edge.** Cells over 4 km from any village ignite twice as often as cells within 0.5 km (289 vs 144); cells touching cropland half as often as cells 1-3 km from it (139 vs 271). Higher (> 550 m: 285 vs < 400 m: 137) and steeper (> 8°: 266 vs < 2°: 126) cells ignite more. The usual "near roads and villages" story does not hold for new ignitions here; whatever starts them happens deep in the forest.
- **Fuel history is a habit, not a limit.** Cells burned 1-2 years before ignite *more* (249-284) than cells not burned since 2017 (201). Repeated burning marks places that get burned, and one or two years is enough fuel. Within a season, fuel does limit: once over half a cell has burned, new ignitions fall five-fold (278 → 55).
- **Dry, hot afternoons.** Relative humidity under 30 % triples the rate against RH over 40 % (335 vs 95); 34-38 °C maximum is the peak (411), hotter days a bit lower (May). March has the highest rate (515), January and May-June the lowest (119, 65).
- **No festival, weekend or collection-season effect.** With everything else equal, the model's rate ratio is 0.97 for weekends, 0.99 for Holi week, 1.06 for the mahua window and 0.99 for tendu. The March peak is explained by dryness and the seasonal curve, not the calendar flags.

### Within-beat test: satellite fuel dryness vs terrain sunshine (14 Oct, later run)

Two per-cell, per-day inputs that can vary *inside* a beat were added to the full model:
- **Terrain sunshine**: clear-sky noon insolation index from slope and aspect for the day of year (no satellite needed).
- **Satellite fuel dryness**: the cell's latest Sentinel-2 / Landsat NDVI, NDMI and NBR within the last 30 days (`s2_cells.parquet`), plus NDMI anomaly against the cell's own 2017-2024 mean.

| Model | Strict | Lenient | Any cell | When 2025 / 2026 |
|---|---|---|---|---|
| All inputs (above) | 19.8 % | 24.8 % | 33.9 % | 0.72 / 0.70 |
| + terrain sunshine | 18.8 % | 26.5 % | 31.6 % | 0.72 / 0.70 |
| + satellite dryness | 23.7 % | 29.5 % | 38.5 % | 0.73 / 0.73 |
| **+ both** | **24.3 %** | **31.6 %** | **39.9 %** | **0.73 / 0.76** |

Satellite dryness is the first input that moves "where" by more than a couple of points; terrain sunshine alone adds nothing. Observed rates (2017-2026, per 100,000 cell-days): NDVI 0.25-0.35 (dry grass, leafless teak) ~310 vs NDVI > 0.5 (still green) 41; NBR > 0.4: 19 vs ~250 below 0.2; cells drier than their own long-run NDMI ~1.3x cells wetter than usual. Top gains in the combined model: day of year, NDVI, new ignitions last 7 days, RH, NBR, 7-day RH minimum (`results/importance_all+both.csv`, `results/results_withinbeat.json`).

## Spread model: which cells next to a fire burn next? (14 Oct)

Separate question from ignition: given a burn front in the last 7 days, which cells within 3 km of it burn in the next window? Exposed windows are 537k of 1.15M (burn rate 5.4 % vs 0.9 % unexposed). Scored on the 1,657 held-out spread patches of 2025-26, 5 cells per beat per day among exposed cells only.

| Ranking among exposed cells | Spread patches caught (strict) | AUC |
|---|---|---|
| Random | 9.4 % | |
| Closest front first | 15.4 % | |
| Front distance, size, age, downwind, slope-to-front | 17.7 % | 0.71 |
| + landscape and fuel | 22.0 % | 0.74 |
| **+ weather and sanctuary activity** | **22.9 %** | **0.78** |
| same without any wind input | 22.0 % | 0.78 |

- **Distance and freshness of the front dominate.** Observed burn per exposed cell-day: 1.5-1.6 % within 1 km of a front, 0.6 % at 2-3 km; 1.4 % when the front burned in the last day, 0.7-1.0 % when it is 2-7 days old.
- **Wind direction does nothing at this resolution.** Observed rate is 1.1-1.2 % whether the cell is upwind or downwind of the front, and the fitted rate ratio downwind vs upwind is 1.00. Slope toward the front: 1.00; 50 m higher than the front: 1.09. With 5-day label windows, 500 m cells and 9-55 km wind fields, the fire's direction over several days is not recoverable from the afternoon wind; a same-day Sentinel/VIIRS front position would be needed to test wind properly.
- Top gains: day of year, new ignitions last 7 days, RH, area burned last 7 days, mahua flag (acting as a late-season proxy, not a cause), within-season burned share. Files: `results/spread_results.json`, `results/spread_importance.csv`, `scripts/spread.py`.

## Does 9 km weather (ERA5-Land) beat one 55 km series (NASA POWER)? (14 Oct)

ERA5-Land hourly at the 33 native 0.1° points over the sanctuary (`/mnt/project-files/ratapani/ee/era5/`, daily summary `era5_daily_points.parquet`), each cell taking its nearest point. On a typical March day the spread across the sanctuary is only ~4.6 points of minimum RH, 1.5 °C of maximum temperature and 1 m/s of wind.

| Weather input | Strict | Lenient | When 2025 / 2026 | Deviance |
|---|---|---|---|---|
| POWER, one series (baseline "all") | 19.8 % | 24.8 % | 0.72 / 0.70 | 20469 |
| ERA5-Land per cell instead of POWER | 18.5 % | 26.0 % | 0.70 / 0.71 | 20255 |
| Both | 19.0 % | 26.1 % | 0.73 / 0.71 | 20366 |

Finer weather does not change *where* (differences are within the ~1-2 point noise) and does not change *when*. ERA5 fits the training data a little better (lower deviance), but that does not carry to the held-out seasons. For Ratapani the weather is effectively one number per day; the within-beat signal has to come from the fuel (satellite dryness, burn history), not the atmosphere. `results/results_era5.json`.

## One ranking for all burning: ignition + spread together (14 Oct)

Scored on every held-out 2025-26 burn (2,592 patches: 935 new, 1,657 spread; 6,973 burnt cell-windows), 5 cells per beat per day. Poisson rate of burning per cell-day, fit on every cell window.

| Ranking | All patches | New | Spread | Burnt cell-windows | Burnt area |
|---|---|---|---|---|---|
| Random | 10.4 % | 12.1 % | 9.4 % | 9.8 % | 9.7 % |
| Long-run burn frequency | 14.8 % | 13.9 % | 15.3 % | 13.9 % | 13.6 % |
| Ignition inputs only (landscape, fuel, weather, satellite dryness) | **23.3 %** | **21.5 %** | 24.3 % | 18.0 % | **25.5 %** |
| + exposure to last-week fronts (one model) | 23.1 % | 14.0 % | **28.2 %** | **18.4 %** | 24.5 % |
| Spread model near fronts, ignition model elsewhere | 22.7 % | 14.0 % | 27.5 % | 18.2 % | 24.5 % |

- Adding front exposure moves the 5 picks per beat towards cells beside fresh fires: spread caught rises 24 → 28 %, new ignitions caught falls 22 → 14 %, and the total does not move. With a fixed budget the two kinds of fire compete for the same slots.
- The combined model is well calibrated on the held-out seasons: by decile of predicted rate, predicted vs observed burns are 27 vs 31, 290 vs 293, 733 vs 737, 3396 vs 3610 (`results/combined_results.json`, `calibration_deciles`). Each cell's number is a usable % chance of burning per day.
- Top gains: new ignitions in the last 7 days (sanctuary-wide activity), day of year, area burned last 7 days, RH, NBR and NDVI, distance to front.
- Against the pipeline thread's 27.5 %: that score counts first-burn cell-days on its own grid and labels, this one counts burnt cell-windows on a 500 m grid with pseudo-beats, so the 18 % here is not a like-for-like comparison. A shared scoring file would settle it.

## The budget trade-off (14 Oct)

Same held-out 2025-26 burns, combined model rates (`scripts/budget.py`, `results/budget_results.json`).

| Picks | All patches | New | Spread | Burnt cell-windows |
|---|---|---|---|---|
| Top 3 per beat | 14.9 % | 9.0 % | 18.3 % | 11.7 % |
| Top 5 per beat | 23.1 % | 14.0 % | 28.2 % | 18.4 % |
| Top 8 per beat | 34.0 % | 22.5 % | 40.4 % | 27.6 % |
| Top 10 per beat | 39.9 % | 27.5 % | 46.8 % | 33.4 % |
| 5 per beat, 1 ignition pick + 4 spread picks | 23.1 % | 14.2 % | 28.1 % | 18.3 % |
| 5 per beat, 2 + 3 | 23.3 % | 15.7 % | 27.5 % | 18.5 % |
| 5 per beat, 3 + 2 | 23.3 % | 17.2 % | 26.8 % | 18.3 % |
| 5 per beat, 4 + 1 | 23.2 % | 19.4 % | 25.4 % | 18.0 % |
| 340 picks per day shared across beats by predicted rate (combined) | 24.7 % | 13.5 % | 31.1 % | 20.1 % |
| same, ignition-inputs model | 23.6 % | 21.1 % | 25.1 % | 18.6 % |

- At 5 picks per beat the total is flat at 23 % however the picks are split; a quota only decides *which* fires are caught (new 14 → 19 %, spread 28 → 25 %). The budget, not the model, is the ceiling.
- Recall grows almost linearly with effort: 8 picks 34 %, 10 picks 40 %. Doubling the checks nearly doubles the fires caught; there is no knee.
- Letting busy beats borrow picks from quiet ones (same total, min 1, max 15 per beat) adds 1.5 points, mostly spread fires.

### A day-shared budget beats a fixed 5 per beat (shared rule, 14 Oct)

Same number of picks per day (68 beats x 5 = 340), but each day the picks are split between beats in proportion to each beat's summed predicted rate (at least 1, at most 15-60 per beat), instead of a flat 5 everywhere. `results/dynamic_budget_shared_rule.json`.

| | Fixed 5 per beat | Day-shared, cap 15 | Day-shared, cap 25 | Perfect-model ceiling, fixed 5 | Perfect-model ceiling, pooled 340 |
|---|---|---|---|---|---|
| Pipeline lean, LOSO 2017-24 | 28.6 % | 33.1 % | 33.4 % | 65 % | 91 % |
| Pipeline lean, 2025-26 | 26.5 % | 30.1 % | 30.4 % | 64 % | 90 % |
| Research combined, LOSO | 25.9 % | 28.3 % | 28.4 % | | |
| Research combined, 2025-26 | 24.8 % | 27.2 % | 27.2 % | | |

Sharing the day's picks across beats is worth 2.5 points for our model and 5 points for the pipeline's, with no extra checks; a cap of 15 per beat already takes nearly all of it. The cap of 5 per beat on every beat regardless of the day is itself a large part of the loss: it leaves 36 % of fires unreachable, against 10 % when the same 340 picks can go anywhere. This is a scoring and allocation question for the research, not an operational proposal.

## On the real MP beats (14 Oct, 14:40Z)

Akkshay supplied the MP beat layer; the pipeline thread mapped Ratapani to 94 real beats (`/mnt/project-files/ratapani/beats/`), now the standard unit in SCORING.md. The same predictions rescored (`results/results_real_beats_research.json`):

| Research combined model | Pseudo-68, fixed 5 | Real-94, fixed 5 | Real-94, random | Real-94, day-shared (470 picks) |
|---|---|---|---|---|
| LOSO 2017-24, main labels | 25.9 % | 27.0 % | 16.6 % | 37.8 % |
| 2025-26, main labels | 24.8 % | 26.3 % | 15.3 % | 36.8 % |
| LOSO, true 1-2 day lead (VIIRS-dated, strict) | 35.1 % | 35.6 % | 18.8 % | 50.0 % |
| LOSO, true lead, lenient | 27.5 % | 29.0 % | 17.8 % | 38.8 % |

Pipeline lean model on the same real beats: 29.5 % LOSO, 28.9 % on 2025-26, 38.9 % true-lead strict, 43.4 % day-shared. The ordering and gaps are unchanged from the pseudo-beats: the pipeline model leads by 2-3 points, both are about 1.7x random, and sharing the day's picks across beats is worth 11-14 points on real beats (they vary far more in size and fire load than the pseudo-beats did).

## Where the misses are (shared rule, 2025-26, combined model, 14 Oct)

- **The budget alone caps recall at 64-65 %.** Even a perfect model listing only cells that will burn cannot exceed 64 % (2025-26) or 65 % (2017-24) at 5 per beat per day, and 86-87 % at 10, because 36-39 % of positive cell-days fall on beat-days with more than 10 burning cells. The models' 26-28 % is 40-44 % of what the budget allows.
- **Crowded days are where it fails.** Recall is 32 % on beat-days with 1-2 burning cells and 19 % on beat-days with over 10 (which hold 39 % of positives).
- **Small and marginal fires are missed.** Scars under 1 ha: 15 % recall; 1-2 ha: 19 %; over 10 ha: 35 %. Cells with under 20 ha of eligible forest (10 % of positives): 2-10 %. Cells within 500 m of a village: 13 %; 1.5-4 km: 28 %. Below 400 m elevation: 12 %.
- **Window position and gap do not matter** (22-30 % across gap lengths and days inside the window), so cloud gaps are not the loss.
- **Per cell, 39 % of first burns are listed on at least one day of their window**, against 25 % per cell-day.

So two things would raise the number: a budget that follows the day's activity (the 5-per-beat cap costs a third of the fires on busy days, see the budget section), and better ranking among the small, low-forest, near-village burns the model currently deprioritises. The label check (`/mnt/project-files/research/ratapani-label-check/`) oversamples the missed scars to learn whether those are real fires.

### Upweighting the missed types does not help (14 Oct)

Retraining the combined model with the "hard" burns (scar under 2 ha, or cell with under 20 ha forest, or within 500 m of a village; 37 % of positives) weighted 3x: shared-rule recall@5 on 2025-26 goes 24.8 % → 24.1 %; hard positives 16.5 % → 17.7 %, easy positives 29.7 % → 27.8 %. A pure trade. The model is not biased against these fires; they are less predictable with the inputs we have. `results/combined_results_weighted.json`.

### Sentinel-1 radar cannot tighten the scar dates (14 Oct)

Pulled Sentinel-1 GRD over the grid from Earth Engine (`E:\FIRE\ratapani\ee\s1\pull_s1.py`, per-cell VV/VH per acquisition). Ratapani is covered by a single descending track (relative orbit 63) at a 12-day revisit: 15 acquisitions between 10 Dec 2016 and 8 Jun 2017, none ascending. A 12-day radar gap is wider than the optical windows (median 5 days), so radar cannot narrow burn dates here. Pull stopped after the 2017 season; the file stays at `/mnt/project-files/ratapani/ee/s1/s1_cells_2017.csv` for reference. Day-level dating has to come from VIIRS (the FSI-data thread is building scar-plus-VIIRS labels) or from ground records.

### Wind, retested with day-dated fronts (14 Oct, 15:00Z)

The earlier wind test used 5-day scar windows. This one uses VIIRS-dated fronts: issue day t, front = VIIRS detections on day t within 3 km, outcome = the cell's VIIRS-dated first burn is on t+1 (5,826 dated first burns 2017-24; 112,437 exposed cell-days, 2,446 burns). Wind = afternoon mean direction on t (the spread afternoon) and on t+1, from POWER and from the nearest ERA5-Land point. `scripts/wind_viirs.py`, `results/wind_viirs.json`.

- **Distance to the front is everything:** 17.7 % of cells within 500 m of a front burn next day, 5.0 % at 0.5-1 km, 2.4 % at 1-1.5 km, 0.8 % at 2-3 km.
- **Downwind vs upwind: no difference.** Burn rate 2.2 % downwind (cos > 0.5) vs 2.3 % upwind, 8.6 % vs 8.7 % within 1 km, for both wind sources and both days. Only on the windiest quarter of days, using the next day's wind, is there a hint (3.3-3.6 % downwind vs 2.1-2.4 % upwind), too weak and too late to use.
- Adding wind to a distance-plus-front-count model lowers held-out AUC (0.778 without wind, 0.748-0.768 with).

So wind direction does not steer which cell burns next at 500 m resolution even with day-level dating. Fire spread at Ratapani is governed by distance and fuel, with afternoon wind from the 9-55 km models not informative at this scale. This closes the wind question for the research phase.

### Timing skill with forecast-quality weather (14 Oct, 15:10Z)

The "when" result used the actual weather of each day. A 2-day forecast only has the weather known at issue. Scoring the same ignition model with every weather input persisted from 1, 2 or 3 days earlier (`results/when_persistence.json`):

| Weather input | New ignitions caught (strict) | When, Spearman 2025 / 2026 |
|---|---|---|
| Actual, same day | 19.8 % | 0.72 / 0.70 |
| Persisted 1 day | 18.3 % | 0.72 / 0.69 |
| Persisted 2 days | 18.8 % | 0.73 / 0.68 |
| Persisted 3 days | 19.5 % | 0.71 / 0.67 |

Two-day-old weather loses at most 0.02 of timing correlation and 1 point of recall. Dry-season weather at Ratapani changes slowly, and the model already leans on 7-day and 30-day summaries (RH minimum, temperature, rain), so a weather forecast is not needed for the 2-day horizon; persistence is enough. This also means WeatherNext or any forecast model has little to add here.

## Compared with the pipeline thread (like-for-like, 14 Oct)

Both threads' models scored with one rule (`/mnt/project-files/ratapani/scoring/SCORING.md`: first-burn positive cell-days, 2-day horizon, valid only while the cell is still seen, the pipeline's 68 pseudo-beats, 5 per beat per issue day Feb 1 to Jun 20; our `scripts/pipeline_score.py` reproduces its 4.65 % base rate and the pipeline thread used it too).

| Model | LOSO 2017-2024 recall@5 | 2025-26 recall@5 | LOSO recall@10 |
|---|---|---|---|
| Random | 14.8 % | 13.8 % | 29.1 % |
| This thread, combined ignition + spread (Poisson on scar patches) | 25.9 % | 24.8 % | 45.1 % |
| Pipeline thread, lean burn-scar LightGBM (per cell-day) | **28.5 %** | **26.5 %** | 48.9 % |
| Rank-average of the two | 28.1 % | 27.0 % | 48.2 % |

The two models only share 45 % of their top-5 picks (within-beat Spearman 0.54-0.56), yet averaging them gains nothing over the pipeline model alone. Two independently built approaches, with different units, labels handling and features, land within 2-3 points, and their disagreement is noise rather than complementary signal. On these labels and this budget, about a quarter to 28 % of first burns are catchable from fuel, history, weather and recent activity; the ceiling is the data and the budget, not the modelling route. Files: `results/pipeline_rule_loso.json`, `results/pipeline_rule_2025_26.json`, `results/ensemble_results.json`; pipeline files under `/mnt/project-files/ratapani/scoring/`.

## Limits

- Scar labels were judged by Claude (precision ~0.83, recall ~0.71); a new ignition under 2 ha, or one that only shows after it has spread, is counted as spread or missed.
- Date windows (median 5 days) blur the day of ignition; "when" results are at that resolution.
- Pseudo-beats, not real beats. Weather is one sanctuary-wide series (ERA5-Land per cell tested, no gain).
- Two held-out seasons; the 2025/2026 timing correlations differ by up to 0.1 between model variants, which is the noise level.

## Files

| File | What |
|---|---|
| `patches.csv` | 12,806 scar patches: season, window, ha, centroid (row/col on the 20 m grid), distance and date of the nearest prior burn, new-ignition flags at 0.5/1/2/5 km |
| `cells_static.csv`, `fuel_age.csv`, `cell_px.npy` | Per-cell landscape inputs, pseudo-beat id, per-season fuel history; cell id per 20 m AOI pixel |
| `weather_power_2017_2026.csv`, `daily_drivers.csv` | NASA POWER daily weather with afternoon wind direction (`wd_pm`, from hourly data), and the daily driver table |
| `results/results.json`, `results/importance_gain.csv` | Scores above, feature gains |
| `scripts/` | `patches.py`, `cells.py`, `build_windows.py`, `model.py` |

Not done yet: the spread model (contagion from yesterday's fronts given wind, slope and fuel). The afternoon wind series is ready for it.

## Leakage audit (Oct 14, coordinator's list item 1)

Checked both model stacks for same-day information.

- **Pipeline lean model**: clean. S2 dryness uses the look before issue day t (looks inside burn windows dropped); scars-seen features use scars known by t−1; burn prior is leave-season-out.
- **Research spread exposure**: used scar patches whose window had closed by t itself (same-day images). Rerun with a one-day lag (`LEAKSAFE=1`, `spread.py`), results in `results/leak_audit.json`:

| combined model, 2025-26, recall@5 | leaky | leak-safe |
|---|---|---|
| own rule, all burns | 23.1% | 22.8% |
| own rule, new ignitions | 14.0% | 20.2% |
| own rule, spread burns | 28.2% | 24.2% |
| SCORING.md rule, 94 real beats | 26.3% | 26.3% |

The leak moved hits between the "new" and "spread" buckets but did not change the total: every headline number for the research model stands. `LEAKSAFE=1` is now the default for anything new.

## Additions on top of the pipeline's lean model (Oct 14, coordinator's list items 2-4)

Rebuilt the pipeline's lean model in `scripts/lean_plus.py` (same inputs, same LightGBM settings) and added features on top, so gains are comparable. Scored under SCORING.md on the 94 real beats, LOSO 2017-24 and 2025-26 test. Results in `results/lean_plus_results.json`.

| config | LOSO recall@5 | 2025-26 recall@5 | LOSO recall@10 |
|---|---|---|---|
| lean base (rebuilt; pipeline reports 29.5 / 28.9) | 29.8% | 28.7% | 49.0% |
| + Hawkes self-exciting kernels (τ 2/7/21 d × σ 1/3/8 km, all scars and new-ignition scars) + ring counts | 29.5% | 28.9% | 48.7% |
| + dryness slopes (60-day NBR/NDVI change, days since NDVI<0.35), 3×3 and 5×5 neighbour means, within-beat dryness rank | 29.6% | 29.2% | 48.7% |
| + both | 29.9% | 29.0% | 49.1% |
| lambdarank (query = beat-day, truncation 8), base features | 29.6% | 28.7% | 48.6% |
| lambdarank, base + both | 29.5% | 29.0% | 48.7% |
| rank-average of classifier and lambdarank, base | 30.2% | 29.5% | 49.5% |
| rank-average, base + both | **30.4%** | **29.5%** | **49.6%** |

Season-to-season spread of a single config is about ±2 points (2020 is 25%, 2018-19 are 32%), so none of the single additions is distinguishable from the base. The rank-average of classifier and lambdarank is the only consistent lift (+0.4 to +0.8 on every split, recall@10 too); it is cheap and worth carrying but it is not a step change. The Hawkes kernel `hx_all_t7_s3` (7-day memory, 3 km) becomes the top-gain feature when added, i.e. it replaces the existing scars-seen counts rather than adding information. Dryness slopes likewise reshuffle gain between NBR change features without moving recall.

Conclusion: local self-excitation and dryness trend are already captured by the lean model's scars-seen and 30-day S2 features; ranking losses add under a point. The remaining lever at a fixed 5 picks per beat per day is still the label (true ignition day and place) and the budget shape, not the model.

### Custom pairwise loss on pairs straddling rank 5 (`scripts/lean_pair.py`)

Per the full-read scouting note, a loss focused on the cut-off rather than stock lambdarank: at each boosting round, within each beat-day with a burn, only pairs where exactly one of (burning cell, non-burning cell) sits in the current top 5 contribute a pairwise logistic loss. Same base features, 300 rounds. Results in `results/lean_pair_results.json`.

| config | LOSO recall@5 | 2025-26 recall@5 |
|---|---|---|
| lean base | 29.8% | 28.7% |
| straddle-5 pairwise loss | 29.5% | 29.0% |
| rank-average with the classifier | 30.1% | 29.4% |

Identical to stock lambdarank (29.6 / 28.7, rank-average 30.2 / 29.5). The loss shape is not the limit.

### Observation-quality variants (`scripts/lean_obsq.py`)

Under the shared rule a burn dated to a long gap between clear images becomes many positive cell-days (median window 6 days, 90th percentile 16). PAWS-style idea: trust the well-observed labels more. Results in `results/lean_obsq_results.json`.

| training variant | LOSO recall@5 | 2025-26 recall@5 |
|---|---|---|
| lean base | 29.8% | 28.7% |
| every burn weighted equally (1 / its positive days) | 29.9% | 29.2% |
| positives only from windows ≤ 5 days | 28.6% | 27.8% |
| positives only from windows ≤ 4 days | 25.9% | 25.6% |
| positives only from windows ≤ 8 days | 29.0% | 28.0% |
| rank-average of base, ≤4 and ≤8 models | 29.6% | 29.3% |

Dropping the loosely dated burns costs recall: the scoring rule credits those wide-window days too, and fewer positives means a weaker model. Equal weight per burn is neutral. No lift.

### Where this leaves the scouting list

Of the ranked actions in `/mnt/project-files/ratapani/fsi/scouting/short_horizon_prediction_fullread.md`: Hawkes kernels and burned-fraction rings, the rank-5 pairwise loss, and the observation-quality ensemble are now tested with no gain beyond noise. The two left untested are a GAM partner (a weaker learner than LightGBM on the same inputs, and the ensemble checks above show the model class is not the limit) and drought-code percentiles for timing (the pipeline thread found FWI indices add nothing, and persisted weather already matches actual weather at 2 days). Model-side work on these labels is at its ceiling; the next real step is a better label (true ignition day and place) or a different budget shape.

## Scouting round 3 feature groups on the lean model (Oct 14 evening, `scripts/round3.py`)

Tested on the lean base plus the classifier+lambdarank rank-average (now the shared baseline), 94 real beats, SCORING.md. All features use values up to t−1 only; climatologies and histories are leave-season-out. Results in `results/round3_results.json`.

**Leakage check first.** The lean NDVI/NDMI/NBR features are the last clear look before t (forward-filled, no smoothing), so they cannot see the future. The scouting note's 175-day past-only Whittaker recipe is therefore not needed for honesty; it was not added.

| config | classifier LOSO / 2025-26 | rank-average LOSO / 2025-26 |
|---|---|---|
| lean base | 29.8 / 28.7 | 30.2 / 29.5 |
| + phenology (frac dropped, days since 10/50/85% green-down, slopes 15/30 d, anomaly vs same-DOY median, NDMI drop, within-beat ranks, looks in 30 d, age of newest look) | 29.9 / 29.0 | 30.4 / 29.7 |
| + weather memory (EWMA half-lives 3/7/15 d of Tmax, RH, rain; NDMI 7/15 d) | 29.6 / 28.8 | 30.2 / 29.4 |
| + same ±7-day calendar window burned in other training seasons, cell and 3×3 block | 30.0 / 28.8 | 30.4 / 29.9 |
| + days since Holi | 29.8 / 28.7 | 30.2 / 29.3 |
| + per-cell VIIRS signature from other years (night share, median first-detection DOY, early burner, detections/yr) | 29.6 / 28.9 | 30.2 / 29.6 |
| + all five groups | 29.9 / 29.3 | **30.7 / 29.7** |

All within the ±2-point season spread. The all-groups rank-average is +0.5 LOSO / +0.2 test over the baseline; the features that take gain (3×3 same-window history, 15-day RH memory, days since 10% green-down) replace existing features rather than add information.

**New result: the leaf-fall-to-fire lag in Ratapani.** Day of 50% green-down (d50) per cell from past-only NDVI against the cell's previous-monsoon MODIS peak and leave-season-out dry-season floor. At the start of a cell's first burn window, days since d50 is median 81 (IQR 63–101) and the canopy is 84% dropped (IQR 78–91%). First-burn hazard per valid cell-day by days since d50:

| days since d50 | ≤0 | 1–7 | 8–14 | 15–21 | 22–35 | 36–50 | 51–70 | 71–100 | >100 |
|---|---|---|---|---|---|---|---|---|---|
| positive rate | 0.6% | 1.9% | 2.8% | 3.8% | 5.3% | 6.1% | 6.6% | 6.8% | 2.9% |

and by fraction dropped: <0.4: 0.2%, 0.4–0.6: 1.3%, 0.6–0.8: 4.3%, 0.8–1.0: 6.2%. So fire risk rises about tenfold from green-down to 2–3 months after it, then falls as the season ends. This is a clean, so far unpublished number for a central-Indian teak forest, but for the 2-day model it is already carried by the NDVI and NBR features (adding it explicitly changes nothing).

**Already-burned cells.** Under SCORING.md a cell leaves the valid set once its first scar closes, so no pick can land on an already-burned cell (checked: 0 of 3.0 M valid rows). The time-to-event framing is already in place.

**Not tested here (need Earth Engine pulls or data we do not have):** Open Buildings settlements and walking distance, JRC/Dynamic World water, 2001-16 MODIS fire frequency, daily LST anomaly (the MODIS LST on hand is 8-day and ends 2024), Sentinel-2 Apr/May green-up. TabICL/TabPFN not run (3 M rows, 4 CPU cores). Items 4-5 of the small-data list (bagging) are in the next section.

## Status (Oct 14, 18:20Z): feature hunting on the 2-day cell model stopped

Akkshay's decision: the model is at its ceiling on these labels, so two new threads take over: "Cleaner fire labels" (alert-dated scars as labels; `scripts/lean_alertlab.py` handed over, unrun) and "Rethink the 2-day question" (beat-week, big fire days, spread from active fires; budget, when-model and spread scripts handed over). Round 4 feature notes (fine-scale terrain and litter moisture in `scripts/round4.py`, controlled-burn filter in `scripts/managed.py`) were written but not run. The negative-bagging run (`scripts/lean_bag.py`) finishes below.

### Negative-bagged ensemble (`scripts/lean_bag.py`, finished after the stop)

All positives plus negatives sampled at a low rate, 5 seeds, within-beat-day rank-averaged. Base features, real beats. Results in `results/lean_bag_results.json`.

| training variant | LOSO recall@5 | 2025-26 recall@5 |
|---|---|---|
| lean base (25% negatives, one fit) | 29.8% | 28.7% |
| 2.5% negatives, 5 seeds | 30.2% | 28.8% |
| 2.5% negatives sampled only from beat-days with a burn, 5 seeds | 30.4% | 29.7% |
| 10% negatives, 5 seeds | 30.3% | 29.1% |

Same size of lift as the classifier+lambdarank rank-average (+0.4 to +1.0), and from the same mechanism: averaging several rankings. Within-query negative sampling is the best cheap single-model recipe found; it does not change the ceiling.

### Roads v2 (Oct 14, 21:40Z)

`lean_plus.py` now takes `dist_road_km`, `dist_major_road_km` and `road_km_in_cell` from the pipeline's `scoring/features/roads_features_v2.parquet` (Microsoft Road Detections + OSM) instead of the Earth Engine proximity road/track distances. Rerun: classifier 29.7 / 28.7, lambdarank 29.3 / 28.7, rank-average 30.1 / 29.4 (before: 29.8 / 28.7, 29.6 / 28.7, 30.2 / 29.5). A correctness fix, no score change. Ensemble predictions for every valid cell-day are in `results/lean_ensemble_pred.parquet` (`lean_clf`, `lean_rank`, `lean_ensemble`) for like-for-like comparisons.
