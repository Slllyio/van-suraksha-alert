# Large fires only: can a separate model predict them better? (19 Oct 2026)

**Akkshay's ask** (comment on the size table in `ratapani/fsi/scouting/fire_lines_v2.md`): "this is important data ... make a separate thread where we can predict large fires only and lets see whether we can predict them more accurately than our current models".

## Answer
- **The 2-day list: yes.** A model trained only on 200 ha+ fires catches clearly more big fires than the all-fire list at the same number of flagged squares. The gain is biggest when the list is short.
  - Top 1% of squares: 54% of 200 ha+ fires against 41% (held out 2022-24), and 53% against 41% (2025).
  - For 500 ha+ fires: 59% against 32% (2022-24), and 59% against 40% (2025).
  - At the daily rule's workload (top 10%) the gain shrinks to +3 to +5 points, because the all-fire list already catches about 88-89% there.
- **The season map: no.** A map trained on big-fire burning only ties the all-fire map: 66.6% against 67.0% of 200 ha+ burnt forest in the top 10% of squares (2022-24), and 62.8% against 61.2% (2025).
- **The gain comes from fire size.** It does not come from targeting new starts: a model of any scar-fire start (START, the same inputs with no size information) scores 45% at the top 1%, close to the all-fire list.

## Set-up
- **Fires.** 90,447 multi-day fires statewide, 2017-25 (`scripts/l1_fires.py`). They are built from clear scar outlines (rest-of-MP history plus the 8 tiger reserves). Events are chained into one fire when their outlines are within 60 m and they are at most 4 days apart, the same rule as `fire_lines/f1_fires.py`.
  - Size = forest ha (burnt share of each 500 m square x WorldCover tree+shrub share).
  - Start = squares holding the first VIIRS look (MODIS if no VIIRS), IST date.
  - Size shares match fire_lines_v2's table: 200-500 ha fires are 4.5% of fires and 23.6% of burnt forest; 500 ha+ fires are 1.8% of fires and 28.4%.
  - Per year: 111 (2020) to 1,138 (2017) fires of 200 ha+, and 23 to 358 of 500 ha+.
- **Inputs** (`l2_samples.py`): the round-22 set on all 87 divisions, plus new scar-history inputs from earlier seasons.
  - Round-22 set (`code/system_rebuild`): recent fires at 0-50 km over 1-30 days, 5-season VIIRS history, calendar, HLS dryness, division, and static GIS (terrain, land cover, roads, villages).
  - New scar-history inputs: burnt share by all fires and by 200 ha+ and 500 ha+ fires at 0.5-7.5 km, and 200 ha+ starts within 7.5 km.
- **Models** (`l3_train.py`, LightGBM). All models share the same inputs except ALL.
  - ALL = cloud stand-in for today's list: target = a VIIRS fire point in the square in the next 2 days, round-22 inputs. It is not the PC model, which catches about 93% of 200 ha+ fires at about 10% of squares; ALL gets 88-89% at the top 10%.
  - ALLS = ALL plus the scar-history inputs.
  - BIG / B100 / B500 = target is the first look of a 200 / 100 / 500 ha+ fire in the square in the next 2 days.
  - START = first look of any scar fire.
  - TWO = START x chance of reaching 200 ha.
  - Training seasons: 2018-21, tested on 2022-24; and 2018-24, tested on 2025.
- **Score** (`l5_score.py`). Each big fire is counted once. It is caught if a first-look square, or a square next to it, is flagged 1 or 2 days before the start. Flags are the top q% of each division's square-days.
  - Ground = flagged squares plus their neighbours. ALL and BIG cover the same ground (2.6% at q=1%, 18% at q=10%).
  - Random flags spread out, so they cover 3-7x more ground. The random row is a floor, not a fair match.
  - 95% CI by resampling fires; paired bootstrap for differences (`l7_breakdown.py`).

## 2-day list: big fires caught, 200 ha+ (held out 2022-24, 1,311 fires / 2025, 768 fires)
| flagged squares | ground | all-fire list (ALL) | big-fire model (BIG) | gain, 95% CI | any-start model (START) | VIIRS history only |
|---|---|---|---|---|---|---|
| top 1% | 2.6% | 41.0 / 40.9 | **54.2 / 52.9** | +13.3 (10.5-15.9) / +12.0 (8.1-15.9) | 44.8 / 45.4 | 19.3 / 19.8 |
| top 2% | 4.7% | 55.4 / 55.9 | **67.5 / 67.7** | +12.1 / +11.9 | 58.5 / 58.3 | 29.8 / 27.2 |
| top 5% | 10% | 76.3 / 78.4 | **82.8 / 84.6** | +6.5 / +6.3 | 76.1 / 77.6 | 49.0 / 47.8 |
| top 10% | 18% | 88.4 / 89.1 | **91.6 / 93.6** | +3.2 / +4.6 | 88.0 / 90.9 | 68.0 / 65.1 |
| top 20% | 32% | 95.8 / 97.8 | 97.2 / 98.4 | +1.4 / +0.7 | 95.9 / 97.4 | 83.9 / 81.2 |

**500 ha+ (368 / 192 fires)**, top 1%: ALL 32.1 / 39.6 against BIG 58.7 / 58.8 (+26.6, CI 21-32 / +19.3, CI 12-27). At the top 5%: 74.5 / 76.0 against 85.6 / 88.5.

**100 ha+ (2,751 / 1,660 fires)**, top 1%: ALL 41.3 / 40.2 against BIG 49.4 / 46.0 (+8.1 / +5.7). The B100 model gets 51.3 / 51.0.

**The bigger the fire, the bigger the gain** (top 1%, all test years): 200-500 ha +8.6 points, 500-1,000 ha +23.5, 1,000 ha+ +26.1 (from 26% to 52%).

**Every test season gains** (top 1%): 2022 +15.3, 2023 +10.9, 2024 +8.7, 2025 +12.0.

**By season phase** (top 1%):

| phase | fires | ALL | BIG | gain |
|---|---|---|---|---|
| 15 Feb-15 Mar | 264 | 29.9 | 49.2 | +19.3 |
| 16 Mar-15 Apr | 1,436 | 45.5 | 59.4 | +13.9 |
| 16-30 Apr | 314 | 35.0 | 38.5 | +3.5 |
| May | 65 | 13.8 | 20.0 | +6.2 |

Late fires stay hard. At the top 5% the late-April gain is +8.6.

**By division** (top 1%, 48 divisions with 15 or more big fires): BIG is better in 40, worse in 6, median +12 points. Large gains: Sehore +30, Khandwa +27, Chhatarpur +22, Dindori +20, South Chhindwara +18. Small or none: North Betul -3, Burhanpur +5, South Seoni +6 (`results/by_division.csv`).

**Hit rate per flagged square** (how often a flagged square-day gets a 200 ha+ first look in its 3x3 within 2 days):

| list | 2022-24 | 2025 | average square |
|---|---|---|---|
| BIG, top 1% | 0.57% (1 in 175) | 1.06% (1 in 95) | 0.03-0.05% |
| ALL, top 1% | 0.40% | 0.67% | 0.03-0.05% |

BIG's top 1% is about 19x the average square. Even so, nearly every flagged square-day sees no big fire. This list is for watch and readiness, not for sending a crew to each square.

**What BIG uses** (`results/importance_held.csv`): division, history x the division's usual fire rate for that date, division activity today and over the last 7 days, scar burning within 3.5 km, and big-fire scar burning within 3.5-7.5 km. Distance to villages, major roads and elevation count about twice as much as in ALL. [inference] Big fires start in remote, often-burnt blocks of forest on active days in a busy division. The all-fire list instead rewards squares next to fires already burning.

## Season map (which squares burn in big fires this season), `l6_season.py`
Share of the season's 200 ha+ forest burning that falls in the top 10% of squares, statewide. Inputs come from earlier seasons plus static GIS.

| ranking | 2022-24 | 2025 |
|---|---|---|
| all-fire map | 67.0 | 61.2 |
| big-fire-only map | 66.6 | 62.8 |
| 500 ha+ map | 61.4 | 59.4 |
| past big-fire scars alone | 67.4 | 59.3 |
| past scars, all fires | 65.6 | 57.0 |
| VIIRS history | 55.5 | 46.9 |

Within about a point of each other: where big fires burn over a season is where fires burn. The all-fire map is the better map for all burning (51.8% against 48.1% at the top 10%). Full table: `results/season_map_summary.csv`.


## Fair check: the PC's real models, 2025 (added 20 Oct, `scripts/l8_pc2025.py`, `results/catch_curves_pc2025.csv`)
The PC's 87 live division models were run on every square-day of 2025, the only season they were not trained on. The scores were rebuilt in the cloud with the PC's exact feature builder (`field-system/pc_models`) and the live-alerts thread's cloud inputs: GFS, MODIS, and ERA5 soil moisture where the PC used ERA5-Land. On 5 Apr 2026 these inputs reproduce the PC scores at r 0.99 and 88-93% of the same top squares. Each list is ranked per division, the same way as every other row in this study.

| flagged squares | PC models, 200 ha+ | big-fire model, 200 ha+ | gain (95% CI) | PC models, 500 ha+ | big-fire model, 500 ha+ | gain (95% CI) |
|---|---|---|---|---|---|---|
| top 1% | 40.5 | **52.9** | +12.4 (8.5-16.5) | 45.8 | **58.9** | +13.0 (5.7-20.8) |
| top 2% | 56.6 | **67.8** | +11.2 (7.4-15.1) | 56.8 | **73.4** | +16.7 (9.9-23.4) |
| top 5% | 78.8 | **84.6** | +5.9 (2.9-8.9) | 77.1 | **88.5** | +11.5 (5.2-17.7) |
| top 10% | 89.7 | **93.6** | +3.9 (1.7-6.1) | 88.5 | **95.8** | +7.3 (3.1-12.0) |

- The PC models score the same as the cloud copy (ALL) on big fires, within a point at every budget. The PC flags also cover a little more ground (3.2% against 2.6% at the top 1%, 21% against 18% at the top 10%). So the comparison above favours the PC, not the big-fire model.
- By phase, top 1%, 200 ha+: before 15 Mar 32% -> 56%; 16 Mar-15 Apr 48% -> 58%; 16-30 Apr 30% -> 37%.
- The ~93% of 200 ha+ fires quoted for the daily list is the live rule's own count: statewide pool plus quiet reserve, at about 22% ground. Ranked within each division at 10%, the PC models catch 89.7%.
- Caveats: one season (768 fires of 200 ha+, 192 of 500 ha+); soil moisture from ERA5 instead of ERA5-Land.

## How this relates to the big-fire chance at alert (AUC 0.81)
That model scores a fire after its first detection. This model scores squares before any fire. They chain: the BIG list says where a big fire is likely to start in the next 2 days; once a dot appears, the at-alert chance says whether this fire is the one.


## At alert: does the pre-fire size score beat the app's big-fire points? (added 20 Oct, `scripts/l10_atalert.py`)

**Correction (20 Oct, 10:20Z), itself narrowed on 21 Oct (see the scar-truth section below): on VIIRS truth the size score alone does not beat the app's real points; the two together do.** The live alerts thread re-ran this on the app's own replay of new fires (`field-system/docs/big_fire_replay/`, VIIRS truth: big = 200 ha+ of distinct VIIRS cells, the app's real points). Combination fitted on 2025, tested on 2026 (280 fires past 200 ha):

| score at first look | AUC 2025 | AUC 2026 | day's top 10% of new fires, share of big fires, 2026 |
|---|---|---|---|
| app points | 0.78 | 0.80 | 42% |
| size score | 0.80 | 0.84 | 39% |
| **points + size score** | | **0.87** | **52%** |

I re-checked the 2025 column here (16,622 replay fires): points 0.78, size score 0.79. Later check (21 Oct): the app's real points also score only 0.70-0.73 on scar truth, so the table below was not a rebuild artefact; the two truths reward different things. Use the combination, which is best or equal on both. Live alerts is building it and has asked Akkshay to confirm.

2025 scar fires starting 15 Feb-31 May (15,029 fires; 764 of 200 ha+, 191 of 500 ha+). For each fire, two things known at its first look:
- the app's big-fire points (`field-system/app/big_fire.py` items, rebuilt from the VIIRS archive; farmland from the 500 m square's farm share instead of WorldCover 1 km);
- the size score (SIZE model, chance a start here reaches 200 ha) of the start square from the day before, already computed for every square each night.

| score at first look | AUC 200 ha+ (95% CI) | AUC 500 ha+ |
|---|---|---|
| app points | 0.70 (0.68-0.72) | 0.72 |
| **size score** | **0.84 (0.82-0.85)** | **0.90** |
| big-fire watch score | 0.81 | 0.85 |
| PC daily score | 0.65 | 0.68 |
| points + size score (5-fold CV) | 0.84 | 0.90 |

Share of big fires among each day's top-ranked new fires (median 96 new fires a day):

| top of the day's new fires | points, 200 ha+ | size score, 200 ha+ | points, 500 ha+ | size score, 500 ha+ |
|---|---|---|---|---|
| top 5% | 18.5 | 25.1 | 22.5 | 37.2 |
| top 10% | 28.0 | 42.5 | 31.9 | 56.0 |
| top 20% | 45.3 | 65.6 | 48.7 | 79.6 |

Same count as the app's 12+ points line (1,046 fires in 2025): 12+ points holds 23% of 200 ha+ fires, the top 1,046 by size score hold 37%.

- (Superseded, see correction above.) Here, on scar truth with the rebuilt points, adding the points to the size score added nothing.
- The points scored 0.78-0.80 in the app's own replay (`docs/big_fire_replay`) on a different alert set and truth. On scar truth here they score 0.70, so part of the gap may be this rebuild.
- One season only; 2026 scars will allow a second check.

## Second forward season, 2026, on VIIRS truth (added 20 Oct, `scripts/l11_viirs_truth.py`, `results/catch_curves_viirs_truth.csv`)
2026 has no burn scars yet, so big fires were taken from the app's replay (`field-system/docs/big_fire_replay/`): new fires whose VIIRS cells within 7 days add up to 200 ha+ (280 in 2026, 751 in 2025). Same scoring rule, one first-look square per fire, models trained 2018-24.

| top of each division's squares | 2025 ALL / BIG | 2026 ALL / BIG |
|---|---|---|
| 1% | 36.6 / 39.0 | 41.1 / 39.3 |
| 2% | 53.7 / 52.3 | 52.9 / 54.6 |
| 5% | 76.2 / 71.8 | 74.3 / 70.7 |
| 10% | 89.1 / 86.0 | 87.9 / 80.0 |

**On VIIRS truth the big-fire list does not beat the all-fire list, in 2025 or 2026.** It is not a 2026 failure: on 2025 the same list beats ALL by 12 points on scar truth and ties it on VIIRS truth.

The two truths are mostly different fires. Of 2025's 768 scar fires of 200 ha+, 35% are also 200 ha+ on VIIRS truth, and the other way round is also 35%. VIIRS truth counts fires with many hot-spot cells (long or hot burning, the thing ALL is trained on); scar truth counts burnt forest. The big-fire model was trained on scar truth, so its lead holds only where "big" means burnt forest.

- What it means: the gain is for burnt forest area. 2026 scars (next section) confirm it.
- The at-alert combination (points + size score) was tested on VIIRS truth by live alerts; the points table itself was fitted on scar truth. Both truths agree that the combination beats the points alone.

## 2026 on burn scars: the watch list holds (added 21 Oct, `scripts/l12_scars2026_prep.py`, `l13_fires2026.py`, `l5_score.py` with LF_YEARS=2026, `results/catch_curves_2026.csv`)
2026 scars were built with the 2017-25 method (fire-alert-scars/mp, same three satellites, 15 Feb-15 Jun, inside beats, forest events): 19,019 events, 87% clear scar (16,468), chained into 12,117 fires; 368 of 200 ha+ and 84 of 500 ha+ (a quiet year, like 2023-24). Files in this session's scratch (`scars2026/`). Models trained 2018-24, so 2026 is a second unseen season.

| top of each division's squares | 200 ha+: ALL | BIG | gain (95% CI) | 500 ha+: ALL | BIG | gain (95% CI) |
|---|---|---|---|---|---|---|
| 1% | 43.2 | **56.3** | +13.0 (7.1-18.5) | 40.5 | **64.3** | +23.8 (11.9-33.4) |
| 2% | 59.2 | **67.9** | +8.7 (3.8-13.3) | 59.5 | **73.8** | +14.3 (6.0-22.6) |
| 5% | 78.8 | 81.8 | +3.0 (-0.8-6.8) | 82.1 | 83.3 | +1.2 |
| 10% | 88.6 | 91.0 | +2.4 (-0.3-5.2) | 91.7 | 94.1 | +2.4 |

Same picture as 2022-25: a clear gain at the watch list's size (top 1-2%), little at the daily list's size. The 2026 tie on VIIRS truth (section above) was the truth, not the model.

## At alert on burn scars with the app's real points (added 21 Oct, `scripts/l14_atalert_2026.py`, `results/at_alert_scar_truth.csv`)
Each scar fire is matched to the app replay's new fire at its start (within 1.5 km, +-1 day), so the points are the app's own, not a rebuild. Combination fitted on 2025, tested on 2026.

| 2026 (7,461 fires) | AUC 200 ha+ | day's top 10%, share of 200 ha+ | AUC 500 ha+ | day's top 10%, 500 ha+ |
|---|---|---|---|---|
| app points | 0.73 | 28% | 0.70 | 19% |
| size score | 0.87 | 43% | 0.88 | 53% |
| points + size score | 0.87 | 45% | 0.88 | 52% |

2025 (fit year): points 0.70, size 0.84, combined 0.84. **So my first at-alert result was right for burnt forest: the app's real points score 0.70-0.73 on scar truth too.** The gap with live alerts' check is the truth, not my rebuild. On VIIRS truth the points do well (0.80) and the combination is best (0.87). On scar truth the size score does nearly all the work and the combination equals it. The combination live alerts built is best or equal on both, so it stays.

## Late season and the live rule (added 21 Oct, `scripts/l15`-`l20`, `results/late_diag.csv`, `flag_timing.csv`, `flag_blend.csv`, `late_fixes.csv`, `live_rule_2026.csv`)
**Why late fires are missed.** Of 510 big fires starting 16 Apr-31 May (2022-26), 41% are caught at the top 1%, against 58% before 16 Apr.
- The missed late fires are not low-scored: median rank in their division that day is the 90th percentile, just under the cut.
- The season rule puts flags where scores peak (late March-early April). In 2025, 16-30 Apr got 13% of the flags for 21% of the big fires; in 2026 the two matched (30% / 32%) and the late catch was 62%.
- Burnt ground earlier in the season does not separate missed from caught (median 6% burnt within 2.5 km for both). Missed late fires have fewer fires burning nearby (1 vs 2 in 3 days within 10 km): isolated starts.

**Fixes tested** (top 1%, 200 ha+, each paired with the current list):

| fix | 2022-24 all / late | 2025 all / late | 2026 all / late |
|---|---|---|---|
| flags spread evenly by day | -13 / +7 | -13 / -1 | -11 / -15 |
| half day-adjusted rank (score / day mean^0.5) | +2.9 / +7.9 | +0.8 / +7.9 | +0.8 / -0.8 |
| late rows weighted x3 | -0.2 / +0.5 | -1.8 / -4.3 | -1.6 / -6.1 |
| separate model from 16 Apr | +0.5 / -1.9 | -1.7 / -3.7 | -3.8 / -12.9 |

New models make late fires worse. The day-adjusted rank helps the late season in weak years but not in 2026, and adds about a point overall.

**The live rule matters more.** A live engine sees one day at a time. `watch/big_watch.py` flagged the top 1% of each division's squares *every day*, which is the "spread evenly by day" row: about 11-13 points worse than the tested season rule. The fix is a fixed score cut per division taken from the previous season (`watch/cuts_2025.json`), so busy days get more flags and quiet days fewer. 2026, all 200 ha+ fires, cuts from 2025:

| rule | top 1%: 200 ha+ / 500 ha+ / from 16 Apr | ground | top 2%: 200 ha+ / 500 ha+ |
|---|---|---|---|
| daily top 1% (engine before 21 Oct) | 45.7 / 52.4 / 47.0 | 3.5% | 55.7 / 60.7 |
| **2025 cut** | **63.6 / 65.5 / 63.6** | 3.3% | **73.9 / 79.8** |
| 2025 cut, day-adjusted | 60.9 / 64.3 / 62.9 | 3.3% | 73.6 / 79.8 |
| 2026's own season (hindsight) | 56.2 / 64.3 / 57.6 | 2.7% | 67.9 / 73.8 |

The 2025 cut catches 18 points more than the daily rule on less ground. It flags about 30% more squares than the hindsight row because 2026 scored higher than 2025, so compare it with the daily row, which covers more ground. The engine now writes `top1_cut` / `top2_cut` beside the old `top1` / `top2` columns; the app still reads the old ones. Refresh the cuts each June from the season just ended.

## Caveats
- ALL is a cloud stand-in. The PC's real models were checked on 2025 (section above); they score the same as ALL.
- Fire sizes partly reflect suppression. A fire crews stopped at 150 ha counts as "not big".
- Scar labels start in 2017, so the scar-history inputs see only 1-4 earlier seasons in training.
- The 2026 season has no scars yet, so 2025 is the only forward test.

## Files
- `scripts/` l1-l7.
- `results/`: catch_curves.csv, paired.csv, by_phase / by_year / by_size / by_division.csv, season_map_*.csv, importance_*.csv, fires_table.csv (one row per fire).
- Big intermediates (fires.pkl, daily samples, score cubes) are in this session's scratch only.
