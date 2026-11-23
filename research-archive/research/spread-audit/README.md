# Spread audit: an independent code-level check of the Ratapani spread work

Thread "Spread audit" (Oct 15 2026), answering priority 1 of the external audit Akkshay pasted. Second pair of eyes on
`ratapani/spread/` (written by the "Fire spread model like C-DAC" thread). Nothing under `ratapani/spread/` was edited;
its scripts were imported read only (md5 of every script at audit time: `results/spread_scripts_md5_at_audit.txt`).

## In plain words: can we trust the results?

- **Learned restart** (the "where will the next satellite pass see this fire" model): **yes, it holds up.** Rerunning it
  from the saved models reproduces every one of 1,435 forecast steps exactly. No future information that matters gets into
  it: removing the one suspect input changes nothing. Its lead over the simple "circle around past detections" rule
  (persistence) is 13.7 points (95% range 12.1 to 15.3), and it still wins by 11.7 points against a fairer rule
  I added, "circle around the latest pass only".
- **Learned footprint** (the "what will this fire's final burn outline look like" model, from the first pass): **mostly
  yes, about a sixth of its lead is borrowed from the future.** It uses "ground already burned earlier this season" from burn maps that
  are only final 25 days after a burn. Using only burns final by the fire day lowers it 0.018. It still beats the circle:
  0.498 vs 0.453 (lead 0.045, range 0.039 to 0.051, was 0.054). Swapping the future weather it saw for a forecast
  made from yesterday's weather changes nothing.
- **Physics model**: **its headline used the answer.** Every physics run in README 4a-4b (including the final model) put the
  starting point on the mapped burn scar ("ignition snapped to the scar"). That raises both the physics and its circle
  baseline by about 0.08 overlap. The verdict "physics is no better than a circle" still stands without it (0.275 vs 0.268).
  The size fit changes: with an honest start the final model's footprint is 1.9x the scar, not 1.0x.
- The headline numbers themselves all reproduce, and they stay clearly above zero with honest, fire-by-fire error bars.

Terms: *Sorensen* = overlap score between a forecast area and the true burn, 0 to 1. *Persistence / circle* = the
no-skill rule "fire stays near where it was seen", given the same area as the model. *Leakage* = an input that would
not have been known when the forecast was issued. *Bootstrap by fire* = error bars made by resampling whole fires, so
many detections of one fire are not counted as independent evidence.

## 1. Headline numbers, reproduced, with 95% ranges bootstrapped by fire (`scripts/boot_headlines.py`, `results/boot_headlines.json`)

| Claim (README) | Recomputed | 95% range of the gap |
|---|---|---|
| Restart, next pass at persistence area: 86.3 vs 72.4% (809 fires, 3,803 detections) | 86.3 vs 72.4 | +12.3 to +15.5 |
| same, polygon run (lrg, 738 fires): 85.9 vs 72.2 | 85.9 vs 72.2 | +12.0 to +15.3 |
| leads > 18 h: 81.1 vs 42.4 (148 steps, 148 fires) | 81.1 vs 42.4 | +31.5 to +46.1 |
| leads < 3 h (744 of 1,527 steps, the NOAA-20 pass 50 min after S-NPP) | 92.0 vs 90.8 | +0.1 to +2.3 |
| new ground: 77.0 vs 51.9 | 77.0 vs 51.9 | +22.7 to +27.6 |
| Restart end footprint on polygons: 0.525 vs 0.462 distance | 0.525 vs 0.462 | +0.057 to +0.070 |
| Learned footprint on polygons: 0.517 vs 0.463 circle (1,214 fires) | 0.516 vs 0.462 | +0.049 to +0.060 |
| its later-pass hits 55 vs 38% | 55.1 vs 37.9 (285 fires) | +14.5 to +20.5 |
| Physics final: 0.348 vs 0.345 (1,398 fires) | 0.348 vs 0.345 | -0.001 to +0.006 (a tie) |
| Physics "later passes 26.8 vs 24.9%" (4b text) | **not reproduced** from `res_loose_lfi_m2.parquet`: 24.3 vs 22.8 pooled, 31.8 vs 31.5 per-fire mean | |

Almost half the restart steps (744) are the 50-minute S-NPP to NOAA-20 gap, where both methods score ~91%. The whole gain
is at leads of 9 h and more (79.0 vs 51.8 at 3 h+). Quote it that way.

## 2. Rerun from the saved models (`scripts/audit_restart.py`, `scripts/audit_footprint.py`, physics via the spread `score.py`)

All runs used the spread thread's own code and saved models on a local copy of `data_shared/`. Reproduction: restart
1,435 / 1,435 steps identical; footprint 1,214 / 1,214 fires identical; physics 117 / 117 sampled fires identical.

### Learned restart (`results/audit_restart_steps.parquet`, 738 fires, polygon run)
| At the persistence area | Next-pass hits | Gap |
|---|---|---|
| Persistence (475 m around every detection so far) | 72.2% | |
| **New baseline: same area around the latest pass only** | 74.1% | +1.9 over persistence (+0.9 to +2.9) |
| Learned, as published | 85.9% | **+11.7 over latest-pass (+10.3 to +13.1)** |
| Learned, earlier-burn input limited to burns final by the fire day | 85.8% | -0.0 (-0.4 to +0.3): no leak |
| Learned, dryness score removed | 83.2% | -2.6 (-3.5 to -1.9) |

Leads of 3 h and more: learned 79.0, latest-pass 56.2, persistence 51.8. New ground: learned 76.3 vs latest-pass 55.6.

### Learned footprint (`results/audit_footprint_fires.parquet`, 1,214 fires, polygon truth)
| | Sorensen at the polygon's area |
|---|---|
| As published | 0.516 (circle 0.462) |
| Weather after the first detection replaced by the previous day's (physics re-run, wind features rebuilt) | 0.516 (change -0.000) |
| + earlier-burn input and physics' burned-fuel mask limited to burns final by the fire day | **0.498 (change -0.018, -0.021 to -0.015)**; honest circle 0.453 |

Its own-size forecast grows from 98 to 111 ha (truth 96 ha) under the honest version.

### Physics, final model with and without scar-snapped ignition (`results/audit_physics_nosnap.parquet`, 527 fires, raster scars)
| | Physics | Circle | Median size / scar at last pass + 12 h | at 48 h |
|---|---|---|---|---|
| Snapped to the scar (as published) | 0.351 | 0.347 | 0.99x | 7.1x |
| Not snapped (100 m disc at the alert point) | 0.275 | 0.268 | 1.88x | 9.2x |

Part of the size change is that the honest start lights a 100 m disc while the snap lights one pixel, so it is not all
leakage. Either way the size calibration (ROS x2 = 3.0 t/ha) was fitted with a start the forecast could not have known.

## 3. Findings, in order of importance

1. **Physics used the scar to place the fire's start (confirmed leak).** `sim.ignition_mask` with `ign_snap` moves each
   first-pass point to the nearest mapped-scar pixel within 750 m. `ign_snap: true` is in every config of queue3-queue18
   (README 4a "+ ignition snapped", all of 4b including `loose_lfi_m2`, the snapped-point restarts in 4d). Effect: +0.08
   overlap for physics and circle alike. The physics-vs-circle verdict survives; the absolute numbers and the size calibration
   do not. The learned models do NOT snap (`footprint.CFG ign_snap=False`; the restart has no physics).
2. **Same-season "earlier burn" input is not fully known at forecast time (small leak).** The burn-label rule
   (`research/ratapani-burn-labels/README.md` step 3) needs the NBR drop to persist 25 days. So a scar dated before the
   fire may only be confirmed by images after it. For the median fire with any earlier burns nearby, 68% of those pixels are in that window. Cost:
   footprint -0.018, restart 0. Affects `d_prev`/`dd_prev` (`footprint.py:96`, `foot_restart.py` fire_static) and the
   physics consumed-fuel mask (`sim.py` preburn).
3. **Fire events are grouped with hindsight.** `events_multi.py` links detections over the fire's whole life
   (1.2 km / 30 h single linkage). In 7% of restart steps the "known" detections are separate clusters tied together only
   by later detections. 8% of next-pass target detections are more than 1.2 km from everything known. Both models and
   persistence see the same groups, so the comparison is fair. A live system would need to assign each new detection
   to a fire as it arrives.
4. **"Lead time known from the orbit" is really "time to the next pass that saw this fire".** 85% of steps with leads
   over 18 h had at least one satellite pass in between that saw nothing of the fire (34% at 9-18 h). This is not a leak
   if a forecast is issued for every pass. But the restart score only counts fires that were seen again (it measures
   how many detections were caught, never false alarms). The README wording should say so.
5. **No forward-in-time test.** Every spread model is leave-one-season-out on 2017-24. The model for 2017 trains on 2018-24,
   and features and settings were picked looking at all eight seasons. The spread models have never been run on 2025-26.
   The cleanest next check: freeze models trained on 2017-24 and score 2025 and 2026 once.
6. **Dryness input carries a possible label-informed filter (owner: pipeline thread).** `ratapani/scoring/pipeline_lean_model.py:40`
   drops Sentinel-2 looks that fall inside a cell's known burn window before building the dryness features. That window
   is only known after the burn. Removing the dryness score entirely costs the restart 2.6 points, so any effect is at
   most that. Not tested further here.
7. **Hindcast weather.** The physics and the footprint's physics feature use ERA5-Land after the first detection.
   For the learned footprint this does not matter (persistence weather: no change). The physics was not retested.
   ERA5-Land arrives about 5 days late, so a live system needs forecast weather.
8. Minor: overlap "at the scar's area" gives every method the true size (shape test only; the "own area" columns are the real
   forecast). `foot_restart.py build` skips scars under 1 ha but `score` keeps them, so training and test fires differ slightly.
   Every comparison uses only fires that left a mapped scar.

Checked and clean: grown outlines are used only as the answer key, never as inputs, barriers or start points in the
headline runs (the barrier features of 4m, which use polygon dates, are off in all headline models). Train/test split is by season, with the
same fires and truth for every method in each table. Equal-area matching is the same pixel count inside the same mask for
model and baselines. LightGBM held-out models are per season as claimed.

## Files
- `scripts/boot_headlines.py`: headline numbers + fire bootstrap from the spread thread's saved results
- `scripts/check_events.py`: event grouping and lead-time checks -> `results/check_events.json`
- `scripts/audit_restart.py`, `scripts/audit_footprint.py`: reruns with extra baselines and leak checks
- `scripts/summarize_audit.py` -> `results/audit_summary.json`
- Rerun: copy `ratapani/spread/data_shared/` to a local dir, set `SPREAD_DATA` to it, `SCAR_GROWN=1` (+`GROWN_STORE=grown_scars_viirs.pkl` for the restart), run each script with `k/4` shards. ~1 h on 4 cores.

## Note added after the audit (Oct 15, 12:35Z)
The scar thread has frozen the grown outlines this audit scored against: `fire-alert-scars/reference/v1_2026-10-15/` (MANIFEST.md with sha256, USE_AND_LIMITS.md). Its blind check of 102 readable fires puts false area along the edge at a median 9% and missed burned ground within 250 m at a median 22% (88% for small fires). So the answer key itself has a few-points noise floor in overlap. The model-vs-circle gaps above (about +0.05) compare methods on the same truth and are not affected by that.
