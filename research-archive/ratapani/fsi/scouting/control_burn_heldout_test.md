# Control-burn rule: held-out test (scouting round 21, topic "cb", 17 Oct 2026)

**What was tested.** The rule in `managed_early_burns.md` (code `code/early_burns/control_burn_rule.py`; live copy `field-system/app/control_burn.py`). It tags a VIIRS burn-day cluster (all points on one fire-day within 750 m) as a likely control burn when four things hold: it is day-only, nothing else burns within 1 km from 2 days before to 3 days after, it has at most 2 points, and its maximum FRP is 5 MW or less. Its precision on 15-28 Feb was given as 73%/64%.

**Short answer: no breakthrough, and the rule is weaker than claimed.**
- Held out by season, and with a fairer background, the rule is right about **half** the time on 15-28 Feb: **52%** (95% CI 44-61% across seasons). It is not right two times in three.
- The precision swings from **30% to 70%** between seasons. The 2026 forward test gives **55%** (47-61%).
- It catches only about **a quarter** of control-like burns.
- No independent truth exists yet: no field labels, no line-shaped scars, and no reserve signal.
- A learned score finds **2.4 times** as many control burns at the same precision. That is the only clear improvement, and it also tags 2.6 times as many wildfires.

Code: `code/control_burn_test/` (`t1`-`t7`). Tables and figures: `code/control_burn_test/out/`. Large intermediates are in scratch only.

**Tags.**
- DATA = computed here.
- **[inference]** = my reasoning.
- "Precision" is always an *estimate*, because no ground truth exists (section 4).

---

## 1. Terms (one phrase each)

- **Flag / tag:** the rule's four tests on a burn-day cluster.
- **Live tag:** the same tests without the "3 days after" part. This is what the field system can know on the day of the alert.
- **Background:** the flagged share of 16 Mar-31 May points in the same season. Wildfires are assumed to flag at this rate.
- **Excess precision:** (flagged share − background) ÷ flagged share. It is the share of flagged points the background cannot explain.
- **Density-matched background (new):** the background measured separately for clusters with the same number of other VIIRS points within 10 km and ±7 days. The "nothing nearby" test passes far more easily when few fires burn around.
- **Recall proxy:** the share of 1 Jan-14 Feb points that the rule flags. This is the recall *if* late-Feb control burns look like January ones.
- **Held out:** the thresholds were chosen on 12 seasons and scored on the 13th (2014-2026). 2026 (Oct 2025-Jun 2026) was also scored with a fit on 2014-25 only. This is the **forward test**.
- **CI:** 95% bootstrap interval. It resamples whole **fires**, meaning clusters chained within 1 km on consecutive days. A second interval resamples **seasons**. The season interval is the honest one: seasons differ far more than fires do.

---

## 2. Main results

### 2.1 The old precision was inflated by fire density (DATA, `out/density_matched.csv`, fig 2)

Late Feb is sparse: the median cluster has 19 other points within 10 km and ±7 days, against 51 in Mar-May. In a sparse month, isolated small fires pass the "nothing within 1 km" test more often, whatever lit them.

The test case is **June**, a placebo month (no planned burning is expected). With the r15 method, June scores 45% "precision". With the density-matched background it scores **5%** (CI −3 to 11%). Matching removes the artefact, so all numbers below use it unless marked "plain".

| Fortnight | points | flagged | plain precision (r15 method) | **density-matched precision** (CI by season) | recall proxy (CI by fire) |
|---|---|---|---|---|---|
| Jan | 9,041 | 28% | 80% | **64%** (60-66) | 24% (23-25) |
| 1-14 Feb | 17,169 | 22% | 72% | **61%** (57-65) | same |
| **15-28 Feb** | 18,834 | 18% | 66% | **52%** (44-61) | same |
| 1-15 Mar | 68,121 | 8% | 32% | **28%** (13-43) | same |
| Jun (placebo) | 7,752 | 13% | 45% | **5%** (−5 to 17) | – |

- **What Jan/Feb mean.** Even in January, only about 64% of *flagged* points stand out from wildfire behaviour. The rule tags *all* Oct-14 Feb points as `pre_season_control` regardless of the flag. Whether that is right depends on Akkshay's premise, which this data cannot test.
- **[inference]** The density-matched figure may still be slightly high. Late-Feb fuels are moister than Mar-May fuels, which makes wildfires smaller too. Matching on density cannot remove that.

### 2.2 Held out by season (DATA, `out/loso_folds.csv`, `out/season_density.csv`, fig 1)

| Season | 15-28 Feb points | plain | **density-matched** (CI by fire) |
|---|---|---|---|
| 2014 | 126 | 50% | 36% (2-56) |
| 2015 | 131 | 57% | 37% (16-49) |
| 2016 | 1,972 | 43% | 30% (18-41) |
| 2017 | 1,045 | 71% | 56% (49-62) |
| 2018 | 967 | 80% | 68% (63-73) |
| 2019 | 888 | 81% | 70% (63-74) |
| 2020 | 325 | 70% | 45% (31-54) |
| 2021 | 2,931 | 71% | 56% (50-62) |
| 2022 | 639 | 85% | 66% (61-73) |
| 2023 | 3,295 | 38% | **31%** (19-38) |
| 2024 | 1,556 | 62% | 44% (34-53) |
| 2025 | 3,150 | 77% | 63% (58-68) |
| **2026 (forward)** | 1,809 | 65% | **55%** (47-61) |

- **The thresholds are stable.** When the threshold search runs on each set of 12 seasons, its training estimate is always 65-70%. The rule itself is not over-fitted.
- **The seasons are not stable.** 2016 and 2023 fall to about 30%. 2023 was the year of early leaf fall and early fire everywhere (`managed_early_burns.md` item 9). **[inference]** In such a year, late-Feb wildfires look like January fires, so the flag cannot tell them apart.
- **By satellite era** (plain method): 56% with S-NPP only (2014-17), 77% with two satellites (2018-22), and 61% with three (2023-26). The ≤2-point and "nothing nearby" tests change meaning as satellites are added. Any re-fit should be checked by era.

### 2.3 By division group, 15-28 Feb (DATA, `out/density_matched_groups.csv`)

| Group | points | current rule precision (CI) | learned score precision (CI) |
|---|---|---|---|
| Tiger reserves + Ratapani + Kuno | 2,515 | 54% (46-59) | 50% (43-54) |
| Sal-belt territorial divisions | 1,036 | **43%** (31-50) | **59%** (53-64) |
| Teak territorial divisions | 7,947 | 53% (48-57) | 47% (44-51) |
| Other (dry, degraded, north) | 7,336 | 58% (55-61) | 50% (48-53) |

- The rule is weakest in the sal belt. That is where r15 expected late burning to matter most.
- In 1-15 Mar, every group sits at 23-36%. Extending the rule into March is still not justified.

### 2.4 What the live tag costs (DATA, `out/live_tag.csv`, `out/lff_tag.csv`)

- **Wildfires in late Feb.** The live tag marks 19.6% of 15-28 Feb points. By the density-matched background, about **1,800 of them (2014-26) are wildfires**: 9.6% of all late-Feb points.
- **Share of real wildfires tagged.** This is between **10% and 16%**, depending on how much of late Feb is control burning (0-39%). **[inference]** The upper bound comes from the January recall proxy.
- **Fires that later grew.** Of fires that started 15-28 Feb and grew to ≥3 days or ≥10 points, **6.6%** (22 of 332) carried the live tag on their first day.
- **FSI large fires.** FSI's own Large Forest Fire archive (2019-25) is a set of known real wildfires. **3.4%** (8 of 232) of those starting 15-28 Feb carried the tag on their first day.
- **Flips.** 8.6% of late-Feb live tags are cleared at the 3-day recheck.
- **Outside the window.** The tests alone would mark 6.9% of Mar-May wildfire points, but the tag is limited to 15-28 Feb.

### 2.5 Can a better rule beat it? (DATA, `out/learned_vs_rule.csv`, fig 3; all held out by season)

| Candidate | flagged pts, 15-28 Feb | precision (density-matched, CI by fire) | est. control caught | recall proxy | wildfire pts tagged |
|---|---|---|---|---|---|
| Current rule | 3,367 | 52% (51-55) | 1,760 | 24% | 1,610 |
| Current live tag (no future test) | 3,683 | 51% (49-54) | 1,880 | 26% | 1,800 |
| Threshold refit (grid of 1,792 variants) | 4,334 | 46% (43-48) | 1,980 | 31% | 2,350 |
| **Learned score**, all features | 8,440 | 50% (48-52) | **4,190** | **57%** | 4,250 |
| Learned score, live features only | 7,738 | 64% plain* | 4,960 plain* | 53% | – |

\*Plain method only. The density-matched figure was not computed for this row; expect about 13 points lower, as for the others.

- **Learned score.** A gradient-boosted classifier trained on Jan-14 Feb (label 1) against 16 Mar-May (label 0). Its features are cluster size, number of satellites, FRP, day-only, night neighbour, nearest other point on each day from −3 to +3, hour of the day pass, and distance to road, track and beat edge. Its threshold is chosen on training seasons. The 2026 forward test gives 58% (53-61) against 55% for the rule, with 3.3 times as many tags.
- **The future test (+1 to +3 days) adds almost nothing.** The best live-only refit equals the full refit. The live tag loses only 1 point of precision.
- **Time of day** (earliest day pass before 13:30 IST) was in the grid and was never chosen. VIIRS day passes fall 12:00-14:30 IST, so they cannot show the hour a fire was lit.
- **The refit hit the grid edge.** It always picked ≤4 points and a 2 km radius. Its precision is lower, so it is not a better rule. It just tags more.
- **Verdict.** Nothing beats the rule on precision. The learned score is the only candidate that clearly catches more at about the same precision. It also tags about 2.6 times as many wildfires.

---

## 3. Independent truth: what exists and what it says

### 3a. Burn scars at 20-30 m (DATA, `t4_scars.py`, `t5_scar_tests.py`, `out/scar_*.csv`, fig 4)

**Data used.**
- Ratapani outlines v2: 5,741 events linked to our clusters, including 714 from Jan-14 Feb.
- All-MP 15 Feb-15 Jun scars: 58,885 events linked. Outlines were readable for the tiger-reserve and sample runs only. The rest-of-MP history geometry file was being written during this run, and only 5,032 of its rows could be read.

**Shape measures.**
- **Strip index:** the share of scar area left after a 30 m inward buffer. A strip under 60 m wide scores about 0.
- **Line alignment:** the share of the outline within 30 m of a beat boundary (`ratapani/beats/mp_beats.geojson`) or an Overture road. Overture roads stand in for OSM, because Overpass is blocked here.
- **Decoy:** the same outline moved 2-4 km, to give the chance level of alignment.

| Ratapani, flagged events | Jan-14 Feb | 15-28 Feb | 16 Mar-May |
|---|---|---|---|
| events with outline | 197 | 107 | 234 |
| clear scar found | 67% | 88% | 84% |
| median scar ha | 12.9 | 17.1 | 22.8 |
| strip-like (index < 0.25) | 46% | 28% | 20% |
| outline within 30 m of beat boundary (decoy) | 8.9% (4.9%) | 9.7% (5.2%) | 11.8% (4.9%) |
| outline within 30 m of road (decoy) | 0.2% (1.9%) | 0.1% (0.6%) | 0.9% (1.2%) |

- **No line signal.** Scars do not hug roads, at about or below the chance level. Beat-boundary alignment is about twice the decoy in *every* class, including Mar-May wildfires. **[inference]** Beat boundaries often follow ridges, streams and roads, where fires stop. The alignment does not separate control from wildfire, in Ratapani or MP-wide (MP: 6-7% against 4-7% decoy in all classes).
- **Shape gives weak independent evidence.** A season-held-out classifier using only shape and alignment separates flagged January scars from flagged Mar-May scars with **AUC 0.60** (0.54-0.65). Alignment alone gives 0.53.
- **Mixture estimate.** The strip index puts the share of flagged late-Feb Ratapani scars that look like January ones at **31%** (CI −9 to 69%). This is consistent with the 52%, but too wide to confirm or refute it.
- **[inference] Strip-likeness is partly seasonal.** Unflagged late-Feb scars are also thinner than Mar-May scars (MP: 25% against 10% strip-like). Early-season burns are patchier whoever lights them.
- **No 6-12 m fire-line strip is visible at 20 m.** Fire lines themselves cannot be tested with these scars.
- **Scar at a 3-day lag.** A post-fire image exists within 3 days for 61-67% of events, within 5 days for 87%, and within 10 days for 97%.
- **Adding a scar condition** (strip-like, aligned, small, or no clear scar) does not consistently raise the density-matched contrast between late Feb and Mar-May. The ratios are 0.7-1.5, with opposite signs in Ratapani and MP-wide. **Not recommended.**

### 3b. FSI feedback labels: none exist in our files (DATA, checked)

- **Portal exports.** `ratapani/fsi/fsi_portal/` has date, time, sensor, location and beat/compartment columns only. There is no fire-type or cause field.
- **Large-fire archive.** `lff_mp.csv` has no cause field.
- **Scar tables.** `fire-alert-scars/fsi/*` adds scars only.
- **FSI feedback archive.** It sits behind a login, and MP sent 14 feedbacks in Oct 2026 (`ground_truth_sources.md` §4).
- **Field system.** Its visit form already offers the cause "Controlled burning / fire line" (`field-system/README.md`). Its data folder holds no visit records yet.
- **Result:** zero alerts labelled controlled, prescribed or fire line are available to test against.

### 3c. Kuno, Satpura and Kanha planned-burn years (DATA, `t3_natexp.py`, `out/natexp.csv`)

**Design.** A "burn year" is a season with ≥20% of Oct-Jun points before 15 Feb:
- Kuno: 2016, 2021, 2023, 2025, 2026.
- Satpura: 2023, 2024, 2026.
- Kanha: 2014, 2015, 2019, 2023.

If the flag tracks the burning programme, burn years should show more flagged excess in 15-28 Feb. The comparison is a difference in differences: (reserve's burn years − its other years) − (rest of MP in the same two sets of seasons).

| Reserve | late-Feb excess share: burn years vs other years | Difference in differences (CI) |
|---|---|---|
| Kuno | −0.3% vs +3.3% | +5.9 pt (−4.9 to +12.5) |
| Satpura | 29% vs 22% | +11.7 pt (−16.6 to +38.8) |
| Kanha | 11% vs 11% | +3.4 pt (−25.6 to +36.8) |

- **Not supportive, and not informative.** Late-Feb point counts are tiny: 20-100 points a reserve over all seasons. All intervals include zero.
- **Kuno's burn-year January points are flagged less** (8% against 20%). These are block burns that the rule cannot see (r15 item 5).

---

## 4. What this means

1. **The 64-73% figure should be retired.** The honest held-out estimate for 15-28 Feb is **about 50%** (season range 30-70%; 2026 forward test 55%). It is still an excess-based estimate: it assumes wildfires flag at the same rate as Mar-May wildfires with the same fire density. Weather may still bias it upward.
2. **The rule catches only about a quarter of control-like burns** (recall proxy 24%). Most late-Feb control burning that VIIRS sees is not tagged.
3. **Thresholds do not matter much.** The refits moved precision and coverage only a few points, and time of day never helped. The 3-day wait buys about 1 point of precision.
4. **Independent truth is still missing.** Scars at 20-30 m show no fire-line or road signal. FSI cause labels are not available to us. The reserve natural experiment is too small to say anything.
5. **[inference] The only route to measured precision is field labels.** The field system's visit form already has the right cause field.

---

## 5. Recommendations

### Field thread (live tag, `field-system/app/control_burn.py`; not edited here, read only)

1. **Keep the tag officials-only and never let it suppress or delay an alert.** It marks roughly 1 wildfire for every control burn. It marked 3.4% of FSI-archive large fires and 6.6% of late-Feb fires that went on to grow, on their first day.
2. **Change the wording.** "about 2 in 3 such alerts are" should become "**about half** of such alerts are control burns (30-70% by season); 1 in 10 real wildfires in late Feb also gets this tag". Keep "provisional for 3 days": 8.6% of tags clear at the recheck.
3. **Turn 2027 into the truth test.** For every tagged 15-28 Feb alert, and an equal random sample of untagged late-Feb alerts, make the cause field compulsory ("Controlled burning / fire line", wildfire, other) and keep the photo.
   - MP-wide, the rule tags about 300-500 points per season, so one season gives measured precision and recall with ±5-point CIs.
   - Ratapani alone has too few, about 10-20 tags per season.
4. **Do not switch the live tag to the learned score.** It would catch 2.4 times more control burns but tag 2.6 times more wildfires. For an alert, a missed wildfire costs more than a wasted check.

### Pipeline thread (labels and scoring)

1. **Do not drop `likely_control` points from training positives.** At about 50% precision, dropping 15-28 Feb flagged points (about 3,370 in 2014-26) removes about as many wildfires (1,610) as control burns (1,760). Either way it is only 0.5% of season positives.
   - Option A: keep the points and add the flag (or the learned score `p_learned`) as a feature.
   - Option B: down-weight them to 0.5.
   - Score recall with and without, as before.
2. **Keep `pre_season_control` for Oct-14 Feb as it is.** That rests on Akkshay's premise and the 15 Feb target window, not on this rule. Keep `early_burnt_cell_this_season` as an input. The −33% later-odds result does not depend on the flag's precision.
3. **Use the density-matched background for any future excess-over-background estimate.** The plain method gives June fires 45% "control" precision, and the matched method gives 5%.
4. **Optional:** use the held-out learned score (2.4 times the coverage) as a soft "control-likeness" feature in 15-28 Feb. Do not use it as a filter. Re-check it by satellite era, because the 3-satellite seasons differ.
5. **Not worth doing now:** a scar-shape add-on, road or beat-boundary distance at 30 m, time of day, or extending the rule into March.

---

## 6. Caveats

- No ground truth. Every precision figure is an estimate under a stated assumption, and the density-matched one is the more conservative.
- The recall proxy assumes late-Feb control burns flag like Jan-14 Feb fires.
- MP scar outlines cover tiger reserves and the sample only. The rest-of-MP history geometry was mid-write, with 5,032 rows readable. Ratapani 2026 alerts were matched to our points by nearest point within 400 m, because the 2026 inputs are Earth Engine centroids.
- Oct-Dec points lack NOAA-21. That does not touch the 15-28 Feb results.
- The learned-score threshold was chosen with the plain estimator. Choosing it on the density-matched one would raise its precision a little and lower its coverage.

## 7. Files

- **Code:**
  - `t1_clusters.py`: cluster features and fire IDs.
  - `t2_heldout.py`: held-out grid, live tag, learned score, plain bias checks.
  - `t2b_density.py`: density-matched background, placebo, season bootstrap.
  - `t2c_season.py`: per-season table and forward test.
  - `t3_natexp.py`: reserve natural experiment.
  - `t4_scars.py`, `t5_scar_tests.py`: scar shape and alignment.
  - `t6_lff.py`: FSI large fires.
  - `t7_figs.py`: figures and mixture estimate.
- **Figures:**
  - `out/fig1_season_precision.png`: per-season precision.
  - `out/fig2_fortnight_placebo.png`: fortnights and the June placebo.
  - `out/fig3_rules.png`: rule against learned score.
  - `out/fig4_scars.png`: scar strip share and line alignment.
