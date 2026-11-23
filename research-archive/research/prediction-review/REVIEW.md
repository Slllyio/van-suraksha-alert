# Fresh review of the fire prediction work (15 Oct 2026)

Independent review, written by a new thread that did not build any of the models. I re-ran the numbers from the saved data and code instead of trusting write-ups. Nothing owned by other threads was edited. Scripts are in `scripts/`, numbers in `results/`.

Words used:
- **Cell**: a 500 m square (25 ha). Ratapani has 3,614.
- **Beat**: one guard's patrol area. Ratapani has 94, about 38 cells each.
- **Scar window**: the gap between two clear satellite images. A burn scar is known to have happened somewhere inside it, usually a 5-8 day gap.
- **Cell-day**: one cell on one day. The main score counts these.
- **LOSO**: train on all seasons but one, test on the one left out, repeat.
- **Lift**: how many times better than picking at random.

---

## 1. What the prediction system can actually do today

**In one line:** it is a good daily map of *which squares tend to burn this time of year and look dry now*. It is not yet a forecast of *which square will catch fire in the next 2 days*.

What the evidence shows:

| Question | Answer | Evidence |
|---|---|---|
| Does the main score reproduce? | **Yes.** 30.1% of burned cell-days in each beat's top 5, against 16.6% random (LOSO); 29.4% vs 15.4% on 2025-26. The leak-fixed model gives 29.0% / 28.8%. | `results/check1.json`, `results/check3_scores.json` |
| How much of that is just "this square burned in other years"? | **Most of it.** Ranking cells only by how often they burned in other seasons gives **24.1%** (2025-26: 22.9%). Weather, calendar and terrain add about 1.5 points. Per-cell dryness adds about 3.5-4.5 points. | `check1.json` (prior_tb), `check3_scores.json` (nodry 25.5 / 24.3) |
| Can it tell *when* a cell will burn? | **No.** It lists a cell just as often 3+ days before the fire (30%), 1-2 days before (32%) and after the fire already happened (34%). Random is 16% for all three. | `check1.json` (ens_hit_rate_*) |
| How many "2-day positives" are real forecasts? | **About half.** 50.5% of positive cell-days come *after* the VIIRS fire date, because the scar window is wider than 2 days. | `check1.json` (dated positives) |
| Ranking quality within a day | Within-day AUC 0.69 (LOSO), only 0.01 above burn history alone (0.67). On 2025-26: 0.68 vs 0.63. | `check1.json` (within_day_auc) |
| Are the % chances right? | **On average yes, season by season no.** Across all cell-days, a predicted 7.5% comes true 8.2% of the time. But a season can be off 2-3x (2024: predicted 5.2%, observed 1.6%; 2018: 6.3% vs 10.4%). Brier skill over a plain day-of-year average is only **5-6%**. No cell ever gets more than about a 1 in 3 chance. | `results/check6.json` |
| Would it hold up live? | **Slightly lower but still about 2x random.** The scorer lets the model pick only from cells it knows are not yet burned. A live system cannot know that for 25 days. In a live-style pool, about 10% of picks land on cells that already burned, and the score drops from 29.0% to **25.8%** (random 12.6%). | `check6.json` (livepool) |

**A cheap fix the review found.** The current rule lists the same top cells every day. Because the model has no timing skill, re-listing a cell adds little. A rule that skips any cell listed in the previous 2 days:
- warns **44%** of VIIRS-dated burns 1-2 days before the fire, against **34%** for the current rule and 26% random;
- puts a check on **76%** of burns at least once before the fire day (current rule 50%);
- lowers the cell-day score (30% to 24%), because that score rewards listing the same cell again.

So the official score has been steering the work toward a rule that is worse at warning guards. (`results/check5.json`, `results/check4.json`)

---

## 2. Which claims hold, which don't, which can't be checked

| Claim | Verdict | Notes |
|---|---|---|
| Lean model 29.0% vs 16.6% random | **Holds** | Reproduced exactly. Read as "1.8x random", and know that 24% of it is burn history. |
| Leak fix (~0.5 pt) | **Holds** | Reproduced (29.0 / 28.8). |
| Perfect-model ceiling ~64% at 5 per beat | **Holds** | 63.6% reproduced. The reason: 66% of burned cell-days sit on beat-days with more than 5 burning cells, 39% with more than 10. One big fire fills a beat. |
| "Dryness is the only input that matters" | **Partly holds** | It is the only *in-season* input that matters (+3.5-4.5). But "where it burned before" is worth twice as much (+7.5 over random). |
| "28-30% of fires in the next 2 days" | **Misleading as worded** | It is 30% of burned *cell-days*, half of which are after the fire. On real 1-2 day warnings of dated burns it is 34% (random 26%), i.e. 1.3x random, not 1.8x. Counting each burn once, the current rule catches 41% vs **62% for random rotation**. |
| "When to check" 29.5% to 63% | **Direction holds, size not reproduced** | My own rebuild of the calendar rule gives **50-52%** (theirs 58-60% calendar, 63% forecast). Same direction, smaller gain. Two parts of it: spreading the same 470 checks across the whole sanctuary instead of 5 per beat gives 37.5%, and moving them into peak weeks gives the rest. With random cells, the calendar rule gives 30%: the gain needs both. Their own new-ignition check (first-day fires listed 1-2 days before: fixed 27%, calendar 48%, forecast 50%) is the honest version. The differences between my rebuild and theirs (smoothing, caps) are not resolved. It also asks guards to do up to 3x more checks on peak days, which nobody has tested. |
| Big-fire day AUC 0.88 | **Not re-derived** | Its own write-up says persistence (last 1-7 days of fire) gives the whole skill. Plausible and consistent with literature. |
| MP division models ~85% of fire points in top 10% of squares | **Can't be checked from here, and simple rules get far less** | The model and its scoring code are on Akkshay's PC. I rebuilt the stated rule on the all-MP VIIRS archive (next-day fire squares, 2022-24, 81 divisions): history-only gets **45%**, history + last-week fires **52%**, both covering about 23% of ground. So either the PC model is much better than any simple rule, or its rule differs (horizon, counting fire points vs squares, same-day inputs). This gap is too large to accept without the PC's script and predictions. Also: random flags covering 10% of squares spread to **55%** of ground once neighbours count, so "~20% of ground" must be measured per run, not assumed. And NOAA-21 starts in March 2023, so test years have a third satellite that training years lacked (more points, more persistence). |
| "84.6% vs 31.5%" side by side | **Not comparable** | The report says so, and that is right. Fire points (each hot pixel, many per big fire, on any day it burns) vs first-burn scar cell-days, in-or-next-to vs exact cell, top 10% of a division vs 5 per beat. |
| True-lead labels give 40.7% vs 20.0% | **Holds but is a different key** | Masking after-fire days raises both model and random. Compare lifts, not raw %. |
| af_high_s key 44% | **Different key** | Undated burns are dropped, which makes ranking easier. Lift only. |

**Mixed answer keys.** The project now has at least six: main scar cell-days, true-lead strict, true-lead lenient, af_high_s, "burns caught once", VIIRS fire points (MP), and new-fire VIIRS points. The report's executive summary puts 29.5%, 63% and 84.6% next to each other. They should never share a sentence without saying each key, and the lift over random on that key.

---

## 3. Where the work drifted from the aim

The aim (Akkshay, 13 Oct): predict fires at 25 ha "very accurately and with good recall", using new data and pretrained models, with % chances, scored on top-ranked beat capture and lead time. Akkshay's 15 Oct note adds a high-resolution fuel load map as the first step.

| Branch | Useful or detour? | Why |
|---|---|---|
| Burn-scar labels, scoring file, real beats | **Useful, essential** | Without them nothing could be compared. But the scar-window rule is what makes half the positives after-fire days, and nobody changed the headline metric when this was found (14 Oct). |
| Pretrained models (AlphaEarth, Prithvi), deep nets, WeatherNext, wind | **Useful negatives** | Tested fairly, added nothing. That answers Akkshay's original question: these do not help at this size of data. |
| Cleaner labels, true-lead labels | **Useful** | Showed that most "misses" are fuzzy dates, and that there is no timing skill. This should have changed the metric. |
| "When to check" (reframe) | **Useful, but a change of question** | It answers "how should a beat spend a season's checks", not "which square burns". It is real and probably the most useful finding for the Forest Department, but it is mostly the season calendar. |
| Patrol pilot protocol (v1-v3) | **Premature** | A detailed 2027 trial plan was written before the model it tests has any timing skill, and for a field trial that cannot happen now. |
| Spread models, C-DAC physics, spread audit | **Detour from prediction** | Spread is a different problem (where an existing fire goes in hours). Interesting, and the audit was good practice, but it consumed much of the effort. |
| Burn scar for every alert, all-MP scars, field app | **Detour** (a product) | Useful for officials, but it is monitoring after the fact, not prediction. Akkshay said "research, not product". |
| Fuel load map | **Delivered early, then drifted** | A 10 m fuel load map exists (`fuel-map/ratapani/`, built 14 Oct; one map per season 2018-26, mean 1.46 t/ha). It is built from literature litterfall rates, canopy and years since burn, with no measured fuel anywhere in it. The fire-based check (`inversion/`) says the map is about right for forest but 2-4x too low on grass and scrub, and the map has not been revised since. After that the fuel thread moved to fire timing and speed. As a 2-day input the map alone scored 18-23% (random 16.6%) and adds nothing on top of the model. |
| All-MP division models on the PC | **Jump in scale before the method was settled** | Moved to all MP on a different answer key (VIIRS points) and a different metric before the Ratapani question was answered. Its headline cannot be checked from the project folder. |

Where hallucination-like errors came from (from the corrections log and this review): numbers quoted from earlier runs after the rules changed (29.5 vs 29.0, 76% vs "20% of ground"), numbers from different keys placed side by side, "inferred, not rerun" statements later quoted as results (the ensemble's leak drop), and claims that live only on the PC.

---

## 4. Literature: is our ceiling real?

**Yes, the "where" ceiling is real.** Full notes on 21 papers are in `LITERATURE.md`. Three of them (Kondylatos 2022, Roteta 2019, McFayden 2020) were read as abstracts only, and a few numbers came through a page-summary tool and are marked as such there.

- **The high published scores come from easier tests.** Examples: AUC 0.93 (Prapas 2021), PR-AUC 0.85 (Mesogeos), "96% precision" (Pourmohamad 2026). Their "no fire" examples come from far-away places or fire-free days, so they measure *which region* and *which day*. Our within-beat, within-day test removes both on purpose.
- **Tests set up like ours land in the same range or lower.** Within-day AUC on Cerrado reserves with a proper time split is 0.78-0.79 (Pádua 2026). Next-day 500 m in Greece, at real fire rates, gives lifts of about 1.25-1.5x (our arithmetic from Girtsou 2021). Our 1.8x at 13% of the beat is at the upper end, not below it.
- **Published next-day skill is mostly fire that is already burning.** In the Next Day Wildfire Spread data, removing yesterday's fire map drops the score from 28.4 to 6.8 (Huot 2022). For brand-new fires, the 2026 set-prediction model lands within ~5 km only 13-19% of the time (Bai 2026). Statistical work treats the exact place of a human-caused start, at 1 km and daily, as close to random (Taylor 2013). Agencies forecast *counts* of human fires per 10-20 km area and day instead.
- **Labels cap the score.** The best-validated burned-area product dates only 68% of burns within 2 days (Giglio 2018). That fits our finding that half our "2-day positives" are after the fire.
- **"When" is where agencies get their value.** Daily danger forecasts are used to scale how much effort goes out each day (Preisler 2004, McFayden 2020). That matches the reframe thread's direction.
- **What has added skill over burn history plus calendar:**
  - recent nearby fire, scored separately from new fires;
  - per-cell dryness (NBR/NDVI change, soil moisture);
  - **fuel depletion**: ground burned recently is *less* likely to burn (Mondal & Sukumar 2016);
  - human-access features: settlements and cropland (Satpura TR in MP, Niyogi 2025).
  
  A well-built simple statistical model (logistic GAM) matched machine learning on human-caused fires (Phelps & Woolford 2021b).
- **Realistic reach for "where"** at 5 per beat per day is the mid-30s % (about 2-2.2x random). This is the literature agent's judgment, not a published figure. A much bigger jump should be suspected as a leak or a labelling artefact.
- **The MP "~56% of brand-new fires"** is far above anything comparable in the literature (13-19% within 5 km). The metrics differ, so it is not a contradiction, but it needs the checks in section 2 before anyone repeats it.

---

## 5. Ranked plan back to the original aim

1. **Fix the target before anything else (1 day).** Score on VIIRS-dated first burns, counted once per burn: "was this square listed 1-2 days before the fire started?" Keep scars for where and size, VIIRS for the day. Report lift over random and over burn history, every time. Retire cell-day recall as the headline.
2. **Adopt the no-repeat rotation (1 day).** It already lifts real warnings from 34% to 44% with no new data. Tune the gap (1-5 days) and blend rotation with model score.
3. **Calibrated % per cell, done honestly (2-3 days).** Predict "chance this square starts burning in the next 2 days" on the dated-burn key, with leave-season-out isotonic calibration, plus a season-level correction from the first weeks of the season (the 2-3x season error is the biggest calibration problem). Report reliability and Brier skill against day-of-year and burn-history baselines. Show two numbers per square: % chance, and times-normal.
4. **Separate new starts from spread near a known fire (2 days).** About a quarter to a third of positives sit within 1.5 km of a VIIRS fire in the last 3 days, where the base rate is 5x higher. Two simple heads (near-fire, far-from-fire), each scored separately. The far-from-fire head is the true ignition forecast.
5. **Finish the fuel load map (fuel thread owns it).** Fold the fire-based corrections back into the 10 m map (grass and scrub 2-4x higher), add an in-season leaf-fall term so it changes week by week, publish it with honest error ranges, and freeze it as v1. Then test it once more as an input to point 4's far-from-fire ignition head, where litter should matter most.
6. **Human-activity inputs (the main untested lever).** Mahua areas from satellite (flowering signal, village distance), tendu phad timing, festival and market days. The literature and FSI scouting both say people decide where fires start.
7. **Ask the PC thread for the MP rule and predictions**, and score its 84.6% against history-only and persistence-only on the same rule. Only then roll out.
8. **Pause** the pilot protocol, spread refinements and new product work until points 1-4 land.

---

## How to re-run

All scripts only read other threads' files and write to `results/`.

| Script | What it checks | Output |
|---|---|---|
| `scripts/check1_existing.py` | Reproduces the headline; burn-history baseline; ceiling; window widths; after-fire days; near-recent-fire split; within-day AUC | `results/check1.json` |
| `scripts/check2_mp_baselines.py` | Simple rules under the MP "top 10% + neighbours" rule, all-MP VIIRS 2022-24 | `results/check2_mp.json` |
| `scripts/check3_honest_allcells.py` | Leak-fixed lean model, with and without dryness, predicting every cell-day | `results/pred_allcells_*.parquet`, `results/check3_scores.json` |
| `scripts/check4_when_and_rotation.py` | Independent rebuild of the calendar "when" rule; no-repeat rotation | `results/check4.json` |
| `scripts/check5_rotation_before_fire.py` | Warnings before VIIRS-dated fire days, by rule | `results/check5.json` |
| `scripts/check6_calibration_livepool.py` | Reliability, Brier skill, season errors; live candidate pool | `results/check6.json` |
