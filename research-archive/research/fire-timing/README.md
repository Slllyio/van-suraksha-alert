# Fire timing by division: use and train accordingly (20 Oct 2026)
Akkshay (06:16Z 20 Oct): peak fire time differs across MP; use and train accordingly. All cloud; the PC runs the full daily-model version (with weather) separately.

## 1. Timing differs (scripts/t1_division_peak.py, results/t1_*)
Date by which half of a division's season burnt area (burn scars 2022-25, 15 Feb-31 May) has burnt:
- Early (SW, Narmada belt): Alirajpur, Burhanpur, Sehore, Dewas, Dhar, Lamta 19-24 Mar; 1-12% burns after 15 Apr.
- Mid (most of MP): 28 Mar-8 Apr.
- Late (north, east): Panna TR 9 Apr, North Betul and Dindori 12 Apr, Anuppur 15 Apr, Sanjay Dubri 18 Apr, Kuno 19 Apr, Shivpuri 21 Apr, Gwalior 23 Apr; 45-65% after 15 Apr.
- Moderately stable (even vs odd years 0.61). The whole season also shifts each year: MP half-burnt 30 Mar 2022, 7 Apr 2023, 3 Apr 2024, 29 Mar 2025 (~8 days), as big as the gap between mid divisions.

## 2. Timing does not tell where a later image helps (t2_gain_vs_timing.py)
Across the 10 test regions, the gain from the March image or from mid-season dryness has no relation to the region's late share (rank -0.4 to +0.3, shuffle p 0.28-0.81). Satpura (mid) gained most from March; Dindori (late) gained nothing.

## 3. Season map trained by timing (t3_timing_train.py, results/t3_*)
Burnt ha in top 20% squares, region held out, per phase:

| Model | Caught |
|---|---|
| one pooled model | 42.6% |
| + region timing as an input | 43.6% (+1.0, CI -0.9..+2.8, 7/10 regions) |
| trained mainly on similar-timing regions | 41.8% (-0.8) |
| separate model per phase | 40.3% (-2.3) |

## 4. Daily 2-day model trained by timing, lean cloud version (d1_regime.py, results/d1_*)
No weather (2019-24 weather is only on the PC); fire history, terrain, access; train 2019-24, test 2025-26 every 2nd day; top 10% of each division's squares per day; strict (same square).

| Model | All fires | Brand-new fires |
|---|---|---|
| one model per division | 32.1% | 14.4% |
| one statewide model | 34.6% | 9.4% |
| one model per timing group | 34.7% | 10.0% |
| statewide + timing inputs | 34.7% | 9.8% |
| per timing group + timing inputs | 34.7% | 10.9% |

Pooling beats per-division models (+2.5 pts, 70-75 of 86 divisions) but loses brand-new fires (-3.5 to -5); timing groups or timing inputs add ~0.1 over plain pooling. Groups here came from VIIRS fire squares 2017-24 (2 early, 64 mid, 21 late), coarser than the scar calendar.

## 5. March image inside the full season model (fuel-map/prithvi/scripts/mid_stack.py, results/mid_stack.json)
Target = squares not burnt by 15 Mar burning 4 ha+ later; full model = access, terrain, burn history, Feb Prithvi, PC GPU Feb score. Adding the PC 5-image March score: +0.003 AUC after 15 Mar (CI -0.004..+0.009), late 0.000; only Satpura late +0.05, Khandwa +0.03. Mid-March HLS dryness instead: -0.03.

## Verdict
- Use accordingly: yes, by calendar. Start season map and alerts by ~20 Feb in early divisions, early March in mid, late March in late; no model change.
- Train accordingly: one pooled model that knows the division and date beats splitting by timing group or phase; timing inputs add ~+1 pt on the season map, ~0 on the daily model. Live weather matters more, because the year shift is as big as the regional one.
- Mid-March re-score: real only on images alone; once burn history and access are in, it adds nothing (Satpura late the one exception).

## 6. Full daily model with weather on the PC (vanagni commit b25184f, prithvi_finetune/analysis/regime_test/)
87 divisions, train 2019-21, test 2022-24, 246,790 test fires, top 10% flags, fires caught / brand-new fires caught:

| Model | All MP | Early (7) | Mid (71) | Late (9) |
|---|---|---|---|---|
| own-division (today) | 80.5 / 46.8 | 77.7 / 37.8 | 81.0 / 47.4 | 78.8 / 59.3 |
| statewide | 79.7 / 41.5 | 76.3 / 31.7 | 80.4 / 42.0 | 78.2 / 56.7 |
| statewide + days since usual start | 79.7 / 41.5 | 76.4 / 31.1 | 80.3 / 42.0 | 78.1 / 57.1 |
| one model per calendar group | 79.6 / 42.0 | 76.3 / 33.2 | 80.2 / 42.1 | 80.5 / 60.3 |

Own-division models stay best (+1 all fires, +5 brand-new). The calendar-group model wins in the late group and in the smallest quarter of divisions (+2.6, 11 of 22; Shajapur, Mandsaur, Tikamgarh), which suggested a fallback for small divisions. Sections 7-8 test that; it did not hold up live.

## 7. Clean check of the small-division fallback (vanagni commit 393e5e3, regime_test/confirm/)
Rule fixed before results: a division with fewer than 400 training fires (2019-22) uses its calendar-group model, else its own. Train 2019-22, test 2023-24.
- 10 divisions fall back: Shajapur, Morena, Ujjain, Rajgarh, Bhind, Datiya, Mandsaur, Tikamgarh, Barwani, Mohgaon.
- On those 10: fires caught 68.1% -> 73.7% (+5.5), brand-new 58.6% -> 60.5%; better in 6 of 10 (Shajapur 42->81, Morena 73->91, Ujjain 72->85, Mandsaur 38->60; worse Rajgarh, Bhind, Barwani, Mohgaon). Few test fires (1,173 in all).
- MP-wide unchanged (77.6 / 46.8). Late group +2.0 again.
(Superseded by section 8: the +5.5 was mostly chance on few fires.)

## 8. Live-rule check by the pipeline (Slllyio/van-suraksha-alert PR #1, livefb_*), 20 Oct
Same 10 divisions, the live training years and live rule:
- Held-out years: fires caught 58.0% -> 59.2% with the group model.
- 2026 season: 60.9% -> 58.0%; brand-new fires 46.9% -> 42.7%.
- Statewide: no change.

Verdict: NO fallback. Every division keeps its own model; the clean-check gain was chance on ~1,200 fires. Alert start dates by calendar group still stand (early ~20 Feb, mid early March, late from late March).

## 9. Quiet-square share of the daily list (20-21 Oct)
Live-rule curve, all 87 divisions (vanagni commit c04a9e1, prithvi_finetune/analysis/live_quiet_curve/); 2026 / held-out 2023-24:

| Quiet share | All fires | Brand-new | Beats |
|---|---|---|---|
| 25% (old) | 67.5 / 71.1 | 47.6 / 45.8 | 82.3 / 83.2 |
| **35% (chosen)** | **65.4 / 69.5** | **52.3 / 49.6** | **81.3 / 83.0** |
| 50% | 61.7 / 66.1 | 57.9 / 54.0 | 79.3 / 81.4 |
| 75% | 53.0 / 57.2 | 65.0 / 60.4 | 72.8 / 75.8 |

Akkshay chose 35% on 21 Oct (06:57Z). The live alerts thread applies it to the app, nightly runner and DAILY_RULE_SPEC. An earlier simple-setup table (fixed 10% per division) understated the cost and should not be used.
