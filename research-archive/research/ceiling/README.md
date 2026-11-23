# Is the fire project at its limit? (18 Oct 2026)

Akkshay asked (16:19Z): "I think our project is at its limit. Critically analyse what we can do further in any aspect."
This file is the whole answer. Numbers come from each thread's README; new numbers from this thread are in sections 3 and 4.

## 1. Short answer

- **The 2-day "where" model is at its practical limit.** Fires next to recent fires are mostly solved (79-83% caught). Brand-new fires (16-22% of fires) are the gap: 34% caught against 30% for burn history. New test (section 3): even a perfect hindsight map of this season's burns reaches only 44% of brand-new fires. So any new "where" layer could add at most about 1.6 points on all fires.
- **Spread, direction, still-burning and big-fire chance are at the data ceiling.** Two VIIRS looks a day, about 100-300 m position noise, and 375 m pixels set the limit. Every method lands within ±0.01-0.02 of the others. No model change will move these. Only a new look at the fire would, and the last free one (FILDA-2 night pixels, section 7) adds just 3-9%.
- **The biggest gain left is not a better model. It is where and when the crews look.** In Ratapani, letting the forecast set the daily number of checks raised fires caught from 29% to 63% at the same season effort. That is far more than any model change gave. The all-MP version (a statewide budget across divisions and days) has not been run yet. It needs no new data.
- **The labels limit what we can claim more than what we can predict.** VIIRS dates only about a quarter of the burns that Sentinel-3 and the scars see. In Ratapani, scoring against the cleaner burns raised the model from 1.8x to 2.15x random. The all-MP model has only been scored against VIIRS.

## 2. Each problem, its best number, and what stops it

| Problem | Best now | Simple baseline | What sets the limit | Headroom |
|---|---|---|---|---|
| 2-day fires, all MP, forward 2025-26 | 72.3% caught at 21% ground | fires nearby 49.9% | most fires are next to recent fires; already used | small |
| Same, brand-new fires only | 34.4% (forward), 39.9% (2022-24) | burn history 30.4 / 33.3% | ignition is a human choice; history is the only "where" signal | measured in section 3 |
| Daily number of checks (Ratapani) | forecast total = perfect total (60-65%) | calendar 58-60% | already at the perfect-forecast ceiling | none |
| Crew budget across MP (divisions x days) | not run | fixed share per division | nothing; just not done | **large (Ratapani: 29 -> 63%)** |
| Spread footprint, 818 unseen fires | 0.47 overlap | ring around last dots 0.46 | 2 looks/day, 230 m point error; circle at true centre only 0.60 | ~0.02 with mid-fire S2 |
| Burned by morning | AUC 0.83-0.84 | distance to nearest dot 0.84 | same | none |
| Fire stops within 24 h | AUC 0.80 | – | same | small |
| Big fire chance | AUC 0.81 | dots so far 0.61 | – | small |
| Direction (S2 mid-fire / runway) | 65% / 67% | chance 25% / 50% | S2 only for 12% of fires | none without new looks |
| Fuel load | no map | – | no fuel truth exists; Prithvi signal is stand pattern, not litter | none from current data |

## 3. Ceiling test: a perfect "where it burns this season" map

The question: if we knew, in hindsight, exactly where this season's fires would fall (but not when), how many brand-new fires would we catch?
This "oracle" map is each square's count of this season's fires, with the 11 days around the issue day removed, so the fire being predicted never counts itself. It uses the same calendar curve, the same top-10% flags, the same strict each-fire-once rule as the PC's forward test (2025-26, 87 divisions, 3 satellites). No real model can know this map, so it is an upper bound for any seasonal "where" input (fuel, people, terrain, Prithvi, anything).

Baselines reproduce the forward table exactly (history 30.4-30.5, fires nearby 49.9), so the oracle runs on the same footing.

| Rule (2025-26, strict, each fire once) | Brand-new fires | Other fires | All fires | Ground flagged or next to a flag |
|---|---|---|---|---|
| Burn history 2019-24 | 30.5 | 39.9 | 38.4 | 22% |
| History x calendar | 27.1 | 49.2 | 45.7 | 17% |
| Hindsight: other fires this season (own 11 days removed) | 27.1 | 45.8 | 42.9 | 19% |
| **Hindsight: every fire this season, the fire itself included** | **44.3** | 66.4 | 63.0 | 18.5% |
| PC model (forward) | 34.4 | 79.2 | 72.3 | 21% |

What it says:
- **Knowing where else it burns this season does not help brand-new fires at all** (27.1, the same as history x calendar). A brand-new fire lands where nothing else burns that season. Fires do not cluster within a season at 1.5 km beyond the days around them.
- **Even a perfect map of this season's burns, including the fire being predicted, reaches only 44% of brand-new fires.** That map is impossible: it already knows the answer. The rest of the gap is *which day*, and a human start has no day signal we have found (no weekday effect, Holi eve 1.4x, no weather signal beyond recent activity).
- So the most any "where" input (fuel, people, Prithvi, terrain) could ever add on brand-new fires is about 10 points (34 -> 44). Brand-new fires are 16% of fires, so that is at most about 1.6 points on all fires. A realistic input would get a fraction of that.
- **Verdict: the 2-day "where" model is at its practical limit.** Further "where" layers are not worth the effort.

## 4. Can pooled start points beat cell history on brand-new fires?

Burn history counts every fire square-day in a 3x3 block. Brand-new fires are human starts, and starts are rarer and noisier than burned squares. Pooling past **start points** (a fire square-day with no fire within 1.5 km in the 3 days before) over 2 km or 5 km could find the "habit" of a village edge better than 500 m history.

| Rule | Brand-new fires | All fires | Ground | Brand-new caught per % of ground |
|---|---|---|---|---|
| Burn history (3x3) | 30.5 | 38.4 | 22.2% | 1.37 |
| Start points, 2 km kernel | 15.9 | 31.4 | 11.6% | 1.37 |
| Start points, 5 km kernel | 12.6 | 27.1 | 10.7% | 1.18 |
| History + 2 km starts (rank mix) | 19.0 | 34.5 | 12.9% | 1.47 |

- The smooth kernel flags less ground, so raw numbers are not comparable. Per unit of ground the 2 km start kernel ties burn history (1.37 vs 1.37), and the mix is only slightly better (1.47). The 5 km kernel is worse.
- **Verdict: no real gain.** Pooling start points does not find a "village habit" that cell history misses. This closes the last cheap "where" idea.

## 5. Ranked list of what is left

Ranked by realistic gain, with the reason.

| # | What | Realistic gain | Why | Where it runs |
|---|---|---|---|---|
| ~~1~~ | ~~FILDA-2 night fire pixels~~ | **Tested 18 Oct: dead end (section 7).** It adds 3-9% night pixels in MP forest and misses a third of what FIRMS sees. | | |
| 2 | **Statewide crew budget across divisions and days** | Possibly large on "fires caught per patrol-day". Within a division the scoring already puts flags on heavy days. Across divisions nothing has been tried. | In Ratapani, shifting checks to heavy days was the single biggest gain in the project (29 -> 63%). Whether crews can move between divisions is a question for officials. | PC (queued after the quiet-share run). It should go **ahead of** the Prithvi fine-tune. |
| 3 | **Score the all-MP model against burn scars, not only VIIRS** | It changes the claim, not the system. Ratapani went from 1.8x to 2.15x random on cleaner burns. It also shows whether "brand-new" fires were really brand-new, or had neighbours VIIRS missed. | VIIRS dates about 1 in 4 of the burns Sentinel-3 and the scars see. The model may be better, or worse, on the fires it never saw. | Cloud once the scar history 2017-25 finishes, plus the PC's saved predictions (1.95 GB). |
| 4 | Brand-new fires: quiet-square share (running) | Already found: +7-12 on brand-new at the same overall score | Uses the existing model; no new inputs | PC, running |
| 5 | Prithvi fine-tune | At most +0.01 AUC on season burn share; nothing on the 2-day list | The frozen model already showed the ceiling (sections above) | PC, only when idle |
| 6 | More "where" inputs (villages, footpaths, SHRUG, start kernels) | At most ~1.6 points on all fires even with a perfect map (section 3); start kernels gave none (section 4) | Ceiling measured | Stop |

## 6. What is not worth more effort

- **More model types on the same inputs.** Hawkes kernels, lambdarank, neural nets, per-division second models, a separate new-fire model: each landed within ±0.5 point. The quota of quiet-square flags gives what the new-fire model gave.
- **More weather or vegetation layers for "which square".** FWI/KBDI, ERA5, WeatherNext, NDVI/LST, AlphaEarth, Sentinel-1, GEDI: none added anything. Weather drives *how many* fires a day, which the recent-activity count already captures.
- **Prithvi fine-tune on the PC.** The best case is the frozen result: +0.016 AUC on "burns wholesale this season" and nothing on the 2-day model (20.0 vs 19.9). The trained 30 m head was no better than frozen. Fine-tuning the last 8 layers may add a little to the season score. It cannot reach the 2-day list, because the season score itself adds nothing there. It should run only when the PC is otherwise idle.
- **More spread modelling.** Every method sits at 0.46-0.49 overlap on unseen fires; the circle at the true centre reaches only 0.60. Without a third look per day, nothing moves this.
- **Extra satellites already tried.** Geostationary, ECOSTRESS, MODIS extra looks, raw VIIRS masks and now FILDA-2 (section 7) are all dead ends. Sentinel-3 SLSTR adds about 1% more dated burns.

## 7. FILDA-2 night fire pixels: tested, dead end (18 Oct)

FILDA-2 is NASA's night fire product that adds the VIIRS Day/Night Band (flame light) to the I-bands. The paper reports +25% night fire pixels worldwide, with India among the biggest gainers. It was the only untried satellite-physics lever, so I pulled it for all of MP (VNP47IMG S-NPP + VJ147IMG NOAA-20, LP DAAC, 15 Feb-31 May; 479 granules in 2025, 463 in 2026). I compared it with FIRMS night points from the same satellite and overpass (within 20 min and 750 m), on forest cells only, with gas flares removed.

| Season | FIRMS night pixels (S-NPP + NOAA-20) | FILDA-2 night pixels | FIRMS pixels FILDA-2 also has | FILDA-2 pixels FIRMS lacks |
|---|---|---|---|---|
| 2025 | 25,833 | 17,941 | 66% | 721 (**+2.8%**) |
| 2026 | 11,989 | 8,924 | 63% | 1,080 (**+9.0%**) |

Where the extra pixels fall (2025 / 2026): next to a fire FIRMS saw before and after (dark-gap fill) 205 / 234; before FIRMS first saw that fire (up to 12 h earlier) 203 / 379; after FIRMS last saw it 235 / 276; nowhere near any FIRMS fire 78 / 191.

- In MP forest, FILDA-2 sees *fewer* night fires than the operational product, not more. Our litter fires are weak (median 1.5 MW), and the flame-light test does not help at that size.
- The useful part, earlier first sightings, is 200-380 pixels a season against ~27,000 fires. That is under 1.5%.
- **Verdict: not worth adding** to labels, alerts, still-burning or spread. With this, every free sensor that looks at MP at night has been tried.

Files: `filda/pull_filda.py`, `filda/compare_filda.py`, `filda/filda_YEAR.csv` (all MP pixels), `filda/compare_YEAR.json`, `filda/extra_YEAR.csv`.

## 8. Simple rules on a burn-scar answer key (18 Oct, Akkshay "do 1 n 2")

The key is in `scar_key/` (`build_scar_key.py`, `scar_rules.py`). It covers 73,050 forest fire events from the scar thread, 15 Feb-31 May 2022-25, and 86% have a clear scar. Each event's squares are its alert square plus every 500 m square at least 10% under its scar outline (median 4 squares). An event is caught if one of its squares is near a flag on day -1 or -2. The flags are the same as in the earlier simple-rule checks.

Forward 2025:

| Rule | VIIRS key | Alert square, scar-confirmed | Scar squares, scar-confirmed | Same, brand-new | Ground |
|---|---|---|---|---|---|
| Random | 82.8 | 80.9 | 92.9 | 90.4 | 54% |
| Burned before | 38.4 | 43.8 | 54.3 | 41.4 | 22% |
| Burned before x time of year | 45.7 | 56.5 | 62.7 | 34.5 | 17% |
| Fires nearby, last 7 days | 49.9 | 65.2 | 70.4 | 7.5 | 16% |

- Scar-confirmed fires score the same as all alerts on their alert square (43.8 vs 43.7 for burned before). So false alerts are not what pulls the scores down.
- Counting every square under the scar lifts every rule, random included (81 -> 93), because the target is bigger. **Quote the "alert square, scar-confirmed" key, not the scar-squares key.**
- The model's numbers on this key need the PC, because predictions stay there. The spec is `scar_key/PC_TASKS.md`, also on vanagni branch `claude/project-thread-v0whah` (draft PR #9), together with job A, the statewide crew budget.
**Model on the scar key (PC, 18 Oct 19:00Z, PR #1 `mp/results/officer/scar_*`).** Strict scoring, all fires / brand-new; event counts match this key within 0.1%.

| Key | Period | Model | Fires nearby | Burned before |
|---|---|---|---|---|
| Scar-confirmed | 2022-24 | **81.8 / 44.9** | 65.2 / 11.7 | 44.8 / 36.3 |
| Scar-confirmed | 2025 | **83.0 / 39.4** | 65.2 / 5.9 | 43.8 / 33.8 |
| VIIRS | 2022-24 | 73.2 / 39.9 | 54.7 / 11.4 | 40.8 / 33.3 |
| VIIRS | 2025 | 74.3 / 34.3 | 49.9 / 5.4 | 38.4 / 30.4 |

Ground used: model 20-21%, fires nearby 16-17%, burned before 22-23%. Fires with no scar are caught 72-74%.
- **On real, scar-confirmed fires the model catches about 8 in 10.** That is 17-18 points above the best simple rule, the same lead as on the VIIRS key. On brand-new fires it catches 39-45%, 5-9 points above burn history.
- Every rule scores higher on scar-confirmed fires. Part of the VIIRS key's "misses" are alerts with no burn on the ground.
- Honest headline: **about 82% of scar-confirmed fires and about 40-45% of brand-new ones, flagged 1-2 days ahead on about a fifth of the ground.**

## 9. Pre-season outlook per division: tested, no use (18 Oct)

The question: can anything known by 1 Feb (or 15 Feb) say which divisions, or which years, will have a busy season, so crews are placed early?
- Data: S-NPP detections 15 Feb-31 May, 2015-2026, 87 divisions. NASA POWER monthly rain, max temperature and root-zone soil wetness at each division centre. Early fires 1 Jan-14 Feb.
- Test: leave one season out. Scripts and outputs are in `outlook/`.

| What it tries to predict | Best pre-season input | Result |
|---|---|---|
| Which divisions are busy | the division's long-run average | Its top 20 divisions hold 56% of fires. A perfect pick holds 60%. Last season, weather and early fires add nothing (55-56%). |
| How busy MP is this year | January max temperature | Error factor 1.39 vs 1.53 for "average year" (12 seasons, LOYO r 0.48): weak, not reliable |
| Same | March rain (in-season, not known in January) | r 0.85, error factor 1.29 |

The statewide total swings 6x between years (7,500 in 2015 to 57,000 in 2021). Most of the swing comes from March-April rain, which is not known before the season. The daily forecast already picks it up through recent fire activity.
**Verdict:** there is no useful pre-season outlook. Placing crews by each division's long-run average is already within 4 points of perfect.

## 10. Statewide crew budget (PC job A, 18 Oct 19:30Z, PR #1 `mp/results/officer/state_*`)

Every rule has the same number of flags across MP each day, at equal ground. Strict scoring.

| Rule | All fires (held-out / 2025 / 2026) | Brand-new |
|---|---|---|
| Hindsight: top 10% per division over the whole season | 73 / 74 / 70 | 34-40 |
| Live: each division sets its own daily count | 65 / 66 / 63 | 38-40 |
| **Live: statewide pool** | **73 / 74 / 71** | 38-41 |
| Live: pool with a 50% division floor | 71 / 73 / 69 | 38-40 |

- A live rule must set each day's count without hindsight, and that cost 8-9 points (73 to 65). Pooling the day's flags across MP wins all of it back, with no hindsight.
- The full pool takes almost all flags away from 14 quiet divisions every year, so the PC recommends the 50% floor. It keeps 6-8 of the 8-9 points and still gives every division at least half its usual checks.
- Caveat: calibration used a little hindsight. Live, it would use last season's.
- **Verdict:** this is the largest operational gain left, and it is now measured: **+6 to +8 points of fires caught for the same daily workload**, by letting busy divisions borrow checks from quiet ones.

## 11. Combined live rule, no hindsight (PC, 18 Oct 20:41Z, PR #1 `mp/results/officer/live_*`)

The rule combines the statewide pool, a 50% division floor and a 25% quiet-square reserve. It is calibrated on the previous season only. It is scored strict, at the same daily total and the same ground, on 2023-24 and 2026 (2022 and 2025 have no earlier season to calibrate from).

| Rule | All fires (2023-24 / 2026) | Brand-new | Beats |
|---|---|---|---|
| Hindsight top 10% per division | 72 / 70 | 42 / 36 | 81 / 81 |
| **Live combined rule** | **71 / 68** | **46 / 48** | **83 / 82** |

**Verdict:** this is the final live rule. It costs 1-2 points on all fires and gains 4-12 points on brand-new fires and about 2 points on beats. Fires per 100 flags are the same or better. The spec for the live alert app is in `DAILY_RULE_SPEC.md`.

## 12. Burn-scar history instead of VIIRS history: tested, dead end (19 Oct)

Idea: the scar outlines (152,432 fires 2017-25, complete since 19 Oct) show burnt ground better than VIIRS dots. So "burned before" taken from the scars might pick quiet-place fires better. Test: `scar_hist/` (`build_scar_cells.py`, `score.py`, from `starts.py`). It uses the same strict scoring, top 10% pooled per division, and the same past years as the VIIRS rule. Squares count as burnt when 10% or more lies under a scar.

| Rule | All fires held-out / 2025-26 | Brand-new | Beats |
|---|---|---|---|
| VIIRS history (current rule) | **40.9 / 38.5** | **33.3 / 30.5** | **66.1 / 62.4** |
| Scar history, same years | 39.3 / 34.3 | 31.7 / 27.7 | 63.3 / 55.5 |
| Scar history, all years from 2017 | 36.8 / 33.5 | 29.7 / 26.2 | 58.2 / 54.0 |
| VIIRS + scar history (rank sum) | 37.0 / 34.2 | 29.9 / 26.2 | 60.1 / 55.4 |

**Verdict:** scar history is worse than VIIRS history on every measure (by 2 to 7 points), brand-new fires included. Adding it to VIIRS history makes things worse too. A likely reason (not tested): VIIRS dots mark where fires start and come back, and that is what predicts the next fire. Scars also cover ground that burnt once and then had little fuel left. Don't give it to the PC model.

## Files

- `oracle.py`, `oracle2.py` (section 3), `starts.py` (section 4): copies of `ratapani/scoring/mp_check/mp_simple_events_new.py` with new rules; run with `FWD=1`.
- Outputs: `oracle_summary_fwd.json`, `oracle2_summary_fwd.json`, `oracle*_by_division_fwd.csv`, `starts_summary_fwd.json`, `starts_by_division_fwd.csv`.
