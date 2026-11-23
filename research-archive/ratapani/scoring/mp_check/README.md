# All-MP division models vs simple rules (16 Oct 2026)

The PC's result was 80.5% of fire square-days caught (van-suraksha-alert PR #1, commit 65cea5b, mp/results/all_divisions.csv).
I rebuilt the PC's exact scoring rule from its code (mp_all_eval.py + mp_features.py) and ran rules that use no model.
The rebuild matches the PC: 246,767 vs 246,790 fire square-days, and 430,678 vs 430,776 squares, across all 87 divisions.

**Rule.** Test days are Jan-May of 2022-24. Fires come from 3 satellites. A target is a fire in the square on day t+1 or t+2.
The flagged squares are the top 10% of all the division's test square-days, using one cut-off across the three seasons.
A fire counts as caught if its square, or any of the 8 squares around it, is flagged that day.

| Rule (no model) | Fires caught | New fires caught | Ground flagged or next to a flag |
|---|---|---|---|
| Random squares | 56.7% | 56.3% | 55% |
| Burned before (2019-21) | 44.9% | 35.2% | 22% |
| Burned before x usual fire days of the year | 58.8% | 35.9% | 17% |
| Fires within 1.5 km in the last 7 days | 62.8% | 14.5% | 18% |
| **PC model** | **80.5%** | **46.8%** | not reported |

"New fire" means no fire within 5 km over the past 7 days.

**What it means**
- The model beats the best simple rule in 84 of 87 divisions, by about 18 points overall. This is a real gain, not a quirk of the counting.
- The counting is loose. Random flags already score 57%, because the "next to" rule spreads 10% of squares over 55% of the ground.
- Most counted fires are fires that are already burning.
- For new fires, the model scores 47%. Random scores 56%, but only because random flags cover far more ground.
- To judge new fires fairly, the PC must report how much ground its flags cover. My rough guess is about 18%, like the simple rules, which would make it about 2.5x random. This is not yet checked.
- Three divisions do worse than random: Shajapur (26 fires), Rajgarh (54) and Mandsaur (275). All have few fires to learn from.

**Still open**
- The model's ground share.
- Counting each fire once.
- The S-NPP + NOAA-20 only rerun. NOAA-21 starts in March 2023, so it appears only in the test years.

Script: mp_simple_rules.py. Per-division table: simple_rules_by_division.csv.

## Same check on your season (15 Feb - 31 May), likely control burns dropped (16 Oct, 20:00Z)
Only fire targets dated 15 Feb - 31 May count. Fires before that still feed the "recent fires" input.
On 15-28 Feb, points were dropped when they formed a day-only cluster of 2 or fewer points, with max FRP of 5 MW or less and nothing else within 1 km on days -2 to +3.
That dropped 5,640 of 24,645 points (23%). Target square-days fell from 246,767 to 232,862.
Run with `MPV=season python3 mp_simple_rules.py`. Outputs: `*_season.csv` / `*_season.json`.

| Rule (no model) | Fires caught | New fires | Ground flagged or next to a flag |
|---|---|---|---|
| Random squares | 56.8% | 55.6% | 55% |
| Burned before | 44.9% | 35.0% | 22% |
| Burned before x usual fire days | 53.2% | 31.8% | 18% |
| Fires nearby in the last 7 days | 58.9% | 9.0% | 17% |

On this window the bar is about 59%, down from 63%. The PC model's season score must beat this.

## Final PC results vs simple rules, each fire once (17 Oct, after PC commit 4cb67686)
I rebuilt the PC's officer scoring from `mp_officer_eval.py` and `mp_seasonal.py`, using its seasonal rules and 3 satellites.
The rebuild matches the PC: 50,997 fires vs 50,991, and 232,862 fire square-days vs 232,874.
"Strict" means one of the fire's first-day squares was flagged, or next to a flag, 1-2 days before its first day.

| Rule | Fires caught (strict) | Beat episodes (strict) | Ground flagged or next to a flag | Flagged beats per range per day |
|---|---|---|---|---|
| Random squares | 82.6% | 97.4% | 54% | 7.4 |
| Burned before | 40.8% | 66.0% | 23% | 4.0 |
| Burned before x usual fire days | 50.5% | 62.2% | 17.5% | 2.7 |
| Fires nearby in the last 7 days | 54.7% | 68.7% | 17% | 2.9 |
| **PC model (own; borrow if weak)** | **73.2%** | **81.6%** | **20%** | **3.0** |

- The model beats the best simple rule by about 18 points on fires and 13 on beats, for about the same workload.
- Per division (87, strict, 3 satellites, seasonal rules): the model beats the best simple rule by more than 5 points in 84 divisions, ties in 2 (Bhind, Ujjain), and is worse in 1 (Shajapur, 8 fires: 62.5 vs 75%). Median gain +17.5 points; fire-weighted +17.8. On beats it beats "fires nearby" in 80 of 87. See `model_vs_simple_events_by_division.csv`.
- Random only looks good because it spreads flags over half the ground: 7.4 beats per range per day instead of 3.
- Strict and loose are close (73 vs 75%) because most fires are seen on one day only. That gap does not show the model catches fires before they start.
- S-NPP + NOAA-20 scores about 1 point higher. Most likely the extra small NOAA-21 fires are harder to catch, rather than a train/test satellite mismatch.
- **Not yet tested: brand-new fires (far from any recent fire).** The "fires nearby" rule gets most of its score from fires next to recent fires. The model's new-fire score on this rule has not been reported.

## Brand-new fires: the bar for the model (17 Oct)

Script `mp_simple_events_new.py`, out `simple_events_new_summary.json`, `simple_events_new_by_division.csv`. Same scoring as above (each fire once, STRICT = flagged or next to a flag on day -1/-2 before the first day, season rules, 3 satellites). A fire is **brand-new** when no detection of any kind (control burns and pre-15 Feb fires included, up to 5 km outside the division too) lies within 5 km of its first-day squares in the 7 days before. Same definition as the PC run.

11,284 of 50,997 fires (22%) are brand-new.

| Rule | Brand-new strict | Brand-new loose | Other fires strict | All fires strict | Ground flagged or next to a flag |
|---|---|---|---|---|---|
| Random | 81.6 | 82.4 | 82.9 | 82.6 | 54% |
| Burned before | **33.3** | 33.9 | 42.9 | 40.8 | 23% |
| Burned before x time of year | 32.2 | 32.6 | 55.7 | 50.5 | 17.5% |
| Fires nearby, last 7 days | 11.4 | 17.9 | **67.0** | 54.7 | 17% |

- "Fires nearby" gets almost all its score from fires next to recent fires (67%); on brand-new fires it falls to 11%.
- On brand-new fires the best simple rule is burn history, about 33% at 17-23% of the ground.
- The model's brand-new score is pending from the PC. To count as skill on new fires it has to beat ~33%, not 11%.
- Caveat (from research/fuel-from-heat/README.md, "Crown blocking measured by viewing angle"): in March, fires under leafy closed canopy are detected only ~35% as often on slant passes (>56 deg) as straight down. So some Feb-Mar closed-forest fires are missing from the labels and from the "nearby"/"burned before" history, and a few "brand-new" fires may have had unseen neighbours. This hits model and simple rules alike; it is a label caveat, not a reason to change the comparison. A check (labels weighted by view angle, h13_view_angle.py) is possible if wanted.

### Model on brand-new fires (PC, 17 Oct, commit cecbcddf on PR #1)

| | Brand-new fires (22%) | Other fires | All fires |
|---|---|---|---|
| PC model, 3 satellites | **39.9** | 82.7 | 73.2 |
| PC model, S-NPP + NOAA-20 | 41.8 | 84.0 | 74.2 |
| Fires nearby (PC's run / this check) | 8.0 / 11.4 | 65.2 / 67.0 | 52.6 / 54.7 |
| Burned before (this check) | **33.3** | 42.9 | 40.8 |

- On brand-new fires the model beats the best simple rule (burned before) by about 7 points, 39.9 vs 33.3, on slightly less ground (20% vs 23%). That's real but modest; the "5x" against fires nearby compares with a rule that is blind there by construction.
- Most of the model's lead overall (73 vs 55) comes from fires near recent fires (83 vs 67), where it combines "nearby" with history and dryness.
- PC "fires nearby" differs slightly from this check (8.0 vs 11.4 on new fires) because of tie-breaking details; both say the rule is nearly blind there.
- Saved predictions per square per day stay on the PC: E:\FIRE\mp\results_officer\predictions_3sat\ and predictions_s20\ (1.95 GB).

## Slant-view misses under leafy canopy (17 Oct, Akkshay "do it")

Scripts `mp_va_detections.py` (view angle from FIRMS track, h13 formula; Hansen 2000 tree cover around each pixel), `mp_va_weights.py`, `mp_va_score.py`. Outputs `va_weights_summary.json`, `va_score_summary.json`, `va_score_by_division.csv`. Hansen tiles and per-detection tables are kept outside the shared folder (/tmp/claude-0/hansen, /tmp/claude-0/va); rebuild with the first script.

- **Closed canopy** means Hansen tree cover of 10% or more. On Ratapani detections this matches the canopy map's 50% or more with precision 0.84 and recall 0.62. Correction applies to closed canopy in Feb-Mar only.
- **Detection relative to straight down** (heat thread, leafy crowns): 30-45 deg 0.76, 45-56 deg 0.68, >56 deg 0.35.
  - WORST: every closed Feb-Mar fire is under leafy crowns.
  - MIX: 54% are leafy.
- A fire square-day counts as seen through its best look of the day.

**How many fires are missed (3 satellites, 2022-24 season):**
- Closed-canopy Feb-Mar fires are 7% of fire square-days.
- Of those, 35% had no look closer than 30 deg, and 5% were seen only beyond 56 deg.
- Estimated missing: 17% of closed Feb-Mar fire square-days (WORST) or 7% (MIX). That is **1.4% (WORST) or 0.5% (MIX) of all fire square-days**.
- S-NPP + NOAA-20 is about the same (1.6 / 0.6%). NOAA-21 adds little because it only started in 2023. S-NPP alone misses more (2.3 / 0.9%).

**Does the score move?** No. Each fire is counted once, strict scoring:

| Rule | As before | Labels weighted (WORST) | Labels weighted (MIX) | Slant-only fires dropped | History weighted too |
|---|---|---|---|---|---|
| Burned before | 40.8 | 40.9 | 40.8 | 40.8 | 40.2 |
| Burned before x time of year | 50.5 | 50.6 | 50.5 | 50.4 | 50.5 |
| Fires nearby, last 7 days | 54.7 | 54.8 | 54.8 | 54.7 | 54.6 |

- Only 1,503 of 50,997 fires (2.9%) had a slant-only best first-day look in closed Feb-Mar canopy. Weighting adds 1.5% to the fire count (WORST).
- The model's score can therefore shift by at most about 1 point, so 73.2 vs 54.7 stands.
- Those slant-only fires are, if anything, caught more often by every rule (fires nearby 65%, burned before 48%), because they sit in the forest blocks that burn every year.
- Rebuilding the history from weighted counts changes nothing (within 0.6 point).

## Forward test bar: simple rules on 2025-26 (17 Oct)

`FWD=1 python3 mp_simple_events_new.py` (history from 2019-24, scored on the 2025 and 2026 seasons, same seasonal rules, strict each-fire-once, 3 satellites). Out: `simple_events_new_summary_fwd.json`, `simple_events_new_by_division_fwd.csv`. 54,033 fires, of which 8,379 are brand-new (16%); 46,079 beat episodes.

| Rule | All fires | Brand-new | Other fires | Beat episodes | Ground flagged or next to a flag | Beats per range per day |
|---|---|---|---|---|---|---|
| Random | 82.8 | 81.7 | 83.0 | 97.5 | 54% | 7.4 |
| Burned before | 38.4 | **30.4** | 39.9 | 62.4 | 22% | 3.8 |
| Burned before x time of year | 45.7 | 27.1 | 49.1 | 59.4 | 17% | 2.6 |
| Fires nearby, last 7 days | **49.9** | 5.4 | 58.0 | **64.3** | 16% | 2.6 |

The simple rules score 4-5 points lower than on 2022-24 (fires nearby 49.9 vs 54.7). The model's forward score should be compared with these numbers, not with the 2022-24 ones.

### Forward test result: model frozen on 2019-24, scored on 2025-26 (PC, 17 Oct, commit 4fd3e29f on PR #1)

| | Model | Fires nearby (this check / PC) | Burned before (this check) |
|---|---|---|---|
| All fires, strict | **72.3** | 49.9 / 47.9 | 38.4 |
| Brand-new fires (16%) | **34.4** | 5.4 / 4.2 | 30.4 |
| Other fires | 79.2 | 58.0 / 55.9 | 39.9 |
| Beat episodes, strict | 82.5 | 64.3 / 62.6 | 62.4 |
| Ground flagged or next to a flag | 21.4% | 15.6% | 22% |
| Beats per range per day | 3.2 | 2.6 | 3.8 |

- Fire counts agree (54,114 PC vs 54,033 here).
- The model holds on unseen seasons: 72.3 vs 73.2 on 2022-24. Its lead over the best simple rule is +22 points on all fires and +18 on beats.
- On brand-new fires the lead over "burned before" is thin: +4 points (34.4 vs 30.4), down from +7 on 2022-24.
- 2025: 74.6%; 2026: 69.3%. S-NPP has no data after 27 Apr 2026.
- Still not a live-ready number: weather is ERA5 (~5-day lag) and the 10% cut-off is pooled over the whole season.

### Forward bar with a daily cut-off (no hindsight), 2025-26

`FWD=1 DAILY=1 python3 mp_simple_events_new.py`: each division flags its top 10% of squares **every day**, instead of the top 10% of all square-days of the season. Out: `simple_events_new_summary_fwd_daily.json`.

| Rule | All fires | Brand-new | Beat episodes | Ground flagged or next to a flag | Beats per range per day |
|---|---|---|---|---|---|
| Random | 82.9 | 81.9 | 97.5 | 54% | 7.4 |
| Burned before | 38.5 | 30.5 | **62.5** | 22% | 3.9 |
| Burned before x time of year | 38.6 | 30.7 | 62.4 | 22% | 3.9 |
| Fires nearby, last 7 days | **38.8** | 12.3 | 56.6 | 18% | 3.2 |

- "Fires nearby" falls from 49.9 to 38.8 under a daily cut-off. The season-pooled cut-off handed busy days extra flags, which mostly helped rules that track current fires. The model's pooled 72.3 likely drops for the same reason, so its live-ready score must be compared with these daily-cut-off numbers.
- With a fixed daily share, "x time of year" adds nothing over plain burn history: every square on a given day gets the same calendar factor.

## Live-ready model vs simple rules at the same ground (2026 season, 17 Oct)

The PC's live-ready runs (commit ba63d40d): same-day GFS weather scores the same as ERA5 (72.3% on 2025-26; ERA5 as it really arrives, 5 days late, 71.1%). For a daily flag rule without hindsight, scored on 2026 with the size calibrated on 2025, the recommended "danger-scaled daily share" flags 11.6% of squares on average.

Simple rules here: `FWD=2026 DAILY=1 QFLAG=q python3 mp_simple_events_new.py` flags the top (1-q) of each division's squares every day, on 2026 only (24,043 fires, 4,486 brand-new). Out: `simple_events_new_summary_fwd2026_daily_q*.json`.

| 2026, strict | All fires | Brand-new | Beat episodes | Ground flagged or next to a flag | Beats per range per day |
|---|---|---|---|---|---|
| **Model, danger-scaled daily share** | **69.3** | **44.3** | **83.1** | 27% | 4.2 |
| Model, top 10% of division daily | 63.2 | 41.3 | 81.2 | 28% | 4.7 |
| Fires nearby, top 15% daily | 50.3 | 23.1 | 69.6 | 26% | 4.2 |
| Burned before, top 15% daily | 48.1 | 40.2 | 71.4 | 30% | 4.6 |
| Fires nearby, top 10% daily | 39.8 | 13.2 | 57.9 | 18% | 3.2 |
| Burned before, top 10% daily | 37.5 | 30.1 | 60.8 | 22% | 3.7 |
| Random, top 10% daily | 82.5 | 82.0 | 97.7 | 54% | 7.4 |

- At the same ground (about 27%) and workload (about 4.2 beats per range per day), the live-ready model leads the best simple rule by **+19 points on all fires** (69.3 vs 50.3) and **+12 on beat episodes** (83.1 vs 71.4).
- On brand-new fires it leads "burned before" by only **+4** (44.3 vs 40.2). This matches every earlier test: the model's edge on new fires is thin.
- The model's flags spread over more ground than the rules' flags (10% of squares cover 28% of the ground, against 18-22% for the rules). That's why the comparison is made at equal ground, not equal square count.

## GIS inputs + brand-new-fire head on the PC's 87-division model (18 Oct)

Akkshay 04:15Z. Static table `ratapani/mp_grid/static_gis_v1.parquet` (sent to the PC on vanagni branch `data/static-gis-2026-10-18`), recipe section 6 of `ratapani/fsi/scouting/system_rebuild_satellite_gis_ml.md`, PC's own LightGBM settings for every row. Strict, each fire once, flag share matched to the current model's ground. PC commit 64d9d1dd (van-suraksha-alert PR #1, `mp/results/officer/gis_held*.csv`, `gis_fwd*.csv`).

| | Held-out 2022-24 all / new / beats | Forward 2025-26 all / new / beats |
|---|---|---|
| current | 73.2 / 39.9 / 81.6 | 72.3 / 35.2 / 82.6 |
| + GIS | 73.2 / 40.5 / 82.2 | 72.4 / 36.0 / 82.9 |
| + GIS + per-division new-fire head | 73.2 / 37.2 / 82.1 | 72.4 / 31.9 / 82.7 |
| burned before (30% ground, not matched) | 53.1 / 44.8 / 77.7 | 49.0 / 39.5 / 74.1 |

GIS: small real gain, keep. Per-division head: hurts new fires ~3 pts (likely overfit on few clear-day fires per division; cloud test pooled). Isotonic calibration on previous season: forward Brier skill -0.72 -> +0.014. Next option: one pooled head over 87 divisions.

### Pooled new-fire head (one model over all 87 divisions, division as input; PC commit 9c02b918)

| matched ground | Held-out all / new / continuing / beats | Forward all / new / continuing / beats |
|---|---|---|
| + GIS | 73.2 / 40.5 / 82.5 / 82.2 | 72.4 / 36.0 / 79.1 / 82.9 |
| + GIS + pooled head | 70.7 / 55.6 / 75.0 / 82.0 | 68.7 / 58.1 / 70.6 / 82.7 |

Net: +1,704 / +1,853 brand-new caught, -3,011 / -3,879 continuing. New fires better in 85/87 divisions held-out, 166/174 division-seasons forward. A trade, not a free gain. Open check: same share of flags given to clear squares using the +GIS score alone (is it ranking skill or just budget moved to quiet squares?), plus the blend curve.

### Equal-share control and quiet-square share curve (PC commit 42f5d6cc, share_curve.png in PR #1)

Control: same daily count of flags on clear squares as the pooled run, picked by the +GIS score: 70.2 / 55.0 held-out, 68.4 / 58.8 forward (pooled 70.7 / 55.6, 68.7 / 58.1). The pooled head's gain is the flag budget moved to quiet squares, not better ranking.

| clear-square share (of pooled count) | held-out all / new | forward all / new |
|---|---|---|
| +GIS own choice | 73.2 / 40.5 | 72.4 / 36.0 |
| 25% | 73.9 / 42.2 | 72.4 / 40.9 |
| 50% | 73.4 / 47.8 | 71.6 / 48.1 |
| 75% | 72.6 / 52.6 | 70.6 / 53.3 |
| 100% (pooled) | 70.7 / 55.6 | 68.7 / 58.1 |

Free zone 25-50% (about a quarter of daily flags on quiet squares): all fires level, new fires +7-12, beats best (83-84%). Next: fixed 20/25/30% reserved share with the +GIS score, no second model.

### Equal-share control and quiet-square share curve (PC commit 42f5d6cc, share_curve.png in PR #1)

Control: same daily count of flags on clear squares as the pooled run, picked by the +GIS score: 70.2 / 55.0 held-out, 68.4 / 58.8 forward (pooled 70.7 / 55.6, 68.7 / 58.1). The pooled head's gain is the flag budget moved to quiet squares, not better ranking.

| clear-square share (of pooled count) | held-out all / new | forward all / new |
|---|---|---|
| +GIS own choice | 73.2 / 40.5 | 72.4 / 36.0 |
| 25% | 73.9 / 42.2 | 72.4 / 40.9 |
| 50% | 73.4 / 47.8 | 71.6 / 48.1 |
| 75% | 72.6 / 52.6 | 70.6 / 53.3 |
| 100% (pooled) | 70.7 / 55.6 | 68.7 / 58.1 |

Free zone 25-50% (about a quarter of daily flags on quiet squares): all fires level, new fires +7-12, beats best (83-84%). Next: fixed 20/25/30% reserved share with the +GIS score, no second model.

### Fixed quiet-square reserve, no second model (PC commit 63ef5d47, mp/results/officer/quiet_*)

Strict, each fire once, matched ground (all / brand-new / continuing / beats):

| Rule | Held-out 2022-24 | Forward 2025-26 |
|---|---|---|
| +GIS | 73.2 / 40.5 / 82.5 / 82.2 | 72.4 / 36.0 / 79.1 / 82.9 |
| +GIS daily counts + 20% quiet | 72.5 / 42.8 / 80.9 / 82.0 | 70.9 / 44.1 / 75.8 / 83.2 |
| +GIS daily counts + 25% quiet | 72.1 / 44.8 / 79.9 / 82.1 | 70.4 / 46.5 / 74.8 / 83.3 |
| +GIS daily counts + 30% quiet | 71.7 / 46.4 / 78.8 / 82.1 | 70.0 / 48.4 / 73.9 / 83.1 |
| danger-scaled count, no reserve | 64.6 / 37.8 / 72.2 / 78.7 | 65.5 / 38.9 / 70.4 / 80.7 |
| danger-scaled + 25% quiet | 65.1 / 45.5 / 70.7 / 80.5 | 63.8 / 49.9 / 66.4 / 81.2 |

**CORRECTION to "Live-ready model vs simple rules" (17 Oct):** the danger-scaled daily flag count was compared to the hindsight top-10% rule at more ground (27% vs 22%). At matched ground it loses 8-9 points of all fires. Its comparison against simple rules at the same ground (69.3 vs 50.3 on 2026) still stands, but a live daily count without hindsight remains open. Next idea: fixed calibrated-probability cut from last season.

## Statewide crew budget at the same daily total (PC job A, 18 Oct, commit c0200ae5 on van-suraksha-alert PR #1, mp/results/officer/state_*)

Same statewide flags each day for every rule (sum of the danger-scaled per-division counts), squares ranked by the +GIS calibrated %, one scale per rule so ground equals the current model's. Strict, each fire once. All / brand-new / beats; fires per 100 flags.

| Rule | Held-out 2022-24 | Forward 2025 | Forward 2026 |
|---|---|---|---|
| current (top 10% per division, hindsight) | 73.2 / 39.9 / 81.6; 0.27 | 74.3 / 34.3 / 84.1; 0.49 | 69.7 / 35.9 / 80.6; 0.36 |
| per-division danger counts | 64.8 / 37.9 / 78.7; 0.29 | 66.3 / 39.9 / 81.3; 0.50 | 62.9 / 38.2 / 78.8; 0.38 |
| statewide pool | 73.0 / 40.7 / 81.3; 0.26 | 73.8 / 37.7 / 83.4; 0.46 | 70.6 / 38.3 / 81.4; 0.36 |
| 50% floor + pool | 71.0 / 39.5 / 81.7; 0.29 | 73.0 / 37.9 / 84.9; 0.51 | 69.2 / 37.7 / 81.9; 0.38 |

Divisions losing over half their flags: pool 25 / 28 / 23, floor 0. Same 14 every time: Barwani, Bhind, Datiya, Jhabua, Kanha TR, Morena, Neemuch, PTR, Rajgarh, Satpura TR, Shajapur, Sidhi, Tikamgarh, Ujjain (mostly low-fire).
Reading: pooling statewide wins back the 8 points per-division live counts lose and matches the hindsight rule (forward 72.4 vs 72.3) with no season knowledge. 50% floor stays within 1-2 points of the pool. Caveat: calibration fitted on each division's other test seasons (mild hindsight); live it would be last season's.

## Combined live rule, no hindsight (PC, 18 Oct ~20:50Z, commit f04ce30c on PR #1, mp/results/officer/live_*)

Same statewide daily total. Each division keeps 50% of its danger-scaled count as a floor (25% of it to quiet squares, rest to other squares, by +GIS); remainder pooled across MP by calibrated %, 25% to quiet squares. Calibration fitted only on the previous season, so only held-out 2023-24 and forward 2026 are scorable. One scale factor matches current ground. Strict, each fire once. All / brand-new / continuing / beats; fires per 100 flags.

| Rule | Held-out 2023-24 | Forward 2026 |
|---|---|---|
| current (top 10% of season, hindsight) | 72.1 / 41.9 / 82.4 / 81.3; 0.23 | 69.7 / 35.9 / 77.5 / 80.6; 0.36 |
| per-division counts | 65.8 / 39.7 / 74.7 / 80.4; 0.26 | 62.9 / 38.2 / 68.6 / 78.8; 0.38 |
| floor50 + pool | 71.6 / 41.4 / 81.9 / 82.8; 0.24 | 69.2 / 37.7 / 76.4 / 81.9; 0.38 |
| LIVE: floor50 + pool + 25% quiet | 71.1 / 45.8 / 79.7 / 83.2; 0.24 | 67.5 / 47.6 / 72.1 / 82.3; 0.38 |

Reading: live rule gives up 1.0 / 2.2 points of all fires vs hindsight, gains 3.9 / 11.7 brand-new and 1.9 / 1.7 beats, same or better fires per 100 flags. First version with every input from the past, so it can run unchanged in a 2027 shadow trial. A floor fill bug (3-5 tiny quiet divisions under half) was fixed before these numbers.

## Live rule on the burn-scar key with bootstrap 95% intervals (PC, 19 Oct ~12:30Z, commit ae0de1d0 on PR #1, mp/results/officer/livescar_*)

Same live rule (pool + 50% floor + 25% quiet, matched ground), each division-season scored separately, 2,000 bootstrap draws of division-seasons, paired difference vs current (hindsight top-10%).

Held-out 2023-24 (strict no hindsight): current / live / live - current
- all fires VIIRS 72.1 (70.5-73.6) / 71.1 (68.3-73.8) / -1.0 (-4.1 to +1.8)
- brand-new VIIRS 41.9 / 45.8 / +3.9 (+0.3 to +7.6)
- beats 81.3 / 83.2 / +1.9 (-0.3 to +4.1)
- scar-confirmed all 79.4 / 77.9 / -1.5 (-4.4 to +1.5); brand-new 47.0 / 50.5 / +3.6 (-0.6 to +7.7)
- no scar seen all 69.3 / 68.3 / -1.0 (-4.6 to +2.5); brand-new 35.1 / 38.5 / +3.5 (-1.6 to +8.6)

Forward 2025 (calibrated on 2026, NOT strictly no-hindsight; forward model has no out-of-sample 2024):
- all VIIRS 74.3 / 69.9 / -4.4 (-7.6 to -1.1); brand-new 34.3 / 54.2 / +19.9 (+15.5 to +24.3); beats 84.1 / 84.6 / +0.5 (-1.7 to +2.6)
- scar-confirmed all 83.0 / 78.4 / -4.6 (-7.5 to -1.8); brand-new 39.4 / 58.2 / +18.8 (+13.9 to +23.8)
- no scar seen all 73.8 / 67.2 / -6.6 (-9.7 to -3.2); brand-new 28.8 / 42.5 / +13.7 (+6.9 to +20.6)

Forward 2026 VIIRS only (no 2026 scar key): all -2.2 (-5.8 to +0.9), brand-new +11.8 (+7.7 to +15.5), beats +1.7 (-1.0 to +4.0). Fires per 100 flags equal within intervals every year.
Reading: brand-new gain real; all-fire cost within noise in 2023-24 and 2026, clearly ~-4.5 in 2025 (the year with the largest brand-new gain). Scar key agrees with VIIRS key.
