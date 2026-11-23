# Forecast-led patrol pilot: protocol (v3, 15 Oct 2026)

This is Akkshay's design (15 Oct): one sanctuary, one fire season, a frozen model. Here it is turned into a protocol and dry-run on past seasons. Section 0 is the pre-registered plan (v3, after Akkshay's two reviews of 15 Oct); it overrides anything below. The season window is 15 Feb-15 Jun, as in SCORING.md.

## 0. Pre-registered design and analysis plan (v3)

v3 follows Akkshay's second review (15 Oct). Where the sections below disagree with this one, this section wins.

### 0.1 Pilot year and lock
- The pilot runs in Ratapani, **15 Feb-15 Jun 2027**.
- The model is trained on 2017-26. The model, code, configuration, every definition in this section and the analysis code are locked by **1 Feb 2027**, before the first task. Any later change is logged as a deviation.
- The 2025 and 2026 numbers in sections 1 and 5 are a retrospective dry run only.

### 0.2 Three separate things: eligibility, classification, outcome

**1. Task eligibility** decides where checks go and is fixed at issue time.
- A cell is eligible for the ignition stream unless a VIIRS point (S-NPP, NOAA-20, NOAA-21, from FIRMS or FSI) lies within 1.5 km of it in the 3 days before issue.
- The rule is computed once, stored on the task (`near_active_fire`) and never recomputed.
- Eligibility says nothing about whether a fire found there is a start.

**2. Fire-start classification** decides what was found. It is done after the season, blind to arm.
- **Grouping into unique fires:** field reports and satellite events are grouped with the FSI thread's fire grouping (`ratapani/fsi/scouting/code/ignition/`, the version locked on 1 Feb 2027). Reports within 500 m and 2 days of each other with no satellite event count as one fire. Each fire is credited once, to the first completed inspection that found it.
- **Classes** are set by this table. There is no "or": each row is one combination of evidence.

| Field burn age | Satellite alert within 1.5 km in the 3 days before discovery | Post-season grouping | Class |
|---|---|---|---|
| Burning now / 1-2 days | None | No satellite event, or its first day is within 2 days of discovery | **Confirmed start** |
| Burning now / 1-2 days | None | Joins a fire first detected more than 2 days before discovery | Continuation |
| Burning now / 1-2 days | Yes | `first_day_of_fire` of a separate fire | **Confirmed start** (a separate nearby fire) |
| Burning now / 1-2 days | Yes | Same fire as the alert | Continuation |
| Older | Any | Any | Older burn (not a start) |
| Missing, or no valid photos | Any | Any | Unclassifiable |

- **Disagreements:** when field burn age and the grouping disagree, as in rows 2 and 3, two reviewers decide blind to arm: the range officer and the analyst, using the photos, phone times and before/after satellite chips. A third reviewer settles any split. Each case is logged with its reason.
- **Unclassifiable fires** are left out of the primary count. They are reported per arm, and a sensitivity analysis counts them all as starts and then none as starts.

**3. Primary outcome**
- **The measure:** unique confirmed starts found by completed ignition-stream inspections, per 100 ignition-stream person-hours, per arm.
- **Completed inspection:** a report with at least 2 geotagged, timestamped photos inside the cell, at least 100 m apart, plus an outcome. Arrivals without one are counted, not credited.
- **Range officer acceptance is required:** the report must be accepted at proof review (photo, GPS and time checks, including the 7% re-check). Rejected reports are excluded. Reports still unreviewed at season close count only in a sensitivity analysis, which also drops the acceptance requirement. Acceptance judges proof, not fire class, so the range officer does not need to be blind to arm.

### 0.3 Staff-hours are person-hours, measured before launch

- **Person-hours** = the sum over people of on-duty time, from logged shift start to shift end. A crew of 3 on a 6-hour shift is 18 person-hours. Vehicle or crew elapsed time is never used.
- **Components** reported per arm and stream: travel between inspections, time on site (cell entry to exit), and waiting or idle time. All come from phone positions and the shift log.
- **Stream allocation:**
  - time on site goes to the stream of the task;
  - travel goes to the stream of the next task reached;
  - the trip back goes to the last task's stream;
  - shifts with no task are "unassigned".
- **Primary denominator:** ignition-stream person-hours.
- **Sensitivities:**
  - unassigned hours split in proportion to the assigned ones;
  - total person-hours across both streams.
- **Launch gate:** a 2-week shakedown, 25 Jan-7 Feb 2027, in all beats. Launch needs:
  - at least 95% of shifts with start, end and crew size;
  - at least 90% of on-duty time covered by phone positions with gaps under 30 minutes;
  - no arm with more than 5% unassigned hours.
- If the gate fails, the pilot does not start until the logs are fixed. Arm budgets are recalibrated once, from shakedown travel times, before 15 Feb.

### 0.4 Hypotheses, in order

- **H1, the main operational question:** flexible allocation (the calendar and forecast arms together) finds more confirmed starts per 100 person-hours than fixed 5 per beat. The statistic is the log rate ratio of the pooled flexible arms against the fixed arm.
- **H1a / H1b:** calendar vs fixed and forecast vs fixed, each tested only if H1 holds, with Holm correction.
- **H2, secondary and descriptive:** forecast vs calendar, does the fire forecast add value beyond seasonality. It is reported with its interval, and no superiority claim is made unless the interval excludes 1. The dry run says one season is unlikely to separate them.

### 0.5 Statistical methods

**Randomisation inference respecting the blocks**
- Beats were randomised in blocks of 3, sorted by past burning (`beat_arms.csv` `block`; block 32 is one beat).
- The p-value comes from 10,000 re-draws of arm labels within blocks, recomputing the statistic each time.
- The 95% interval comes from inverting this test over a multiplicative effect.

**Supporting estimate**
- A negative-binomial model per beat: confirmed starts ~ arm + block, with offset log(ignition person-hours).

**Spatial sensitivity**
1. Cluster bootstrap resampling forest ranges (the RID part of `beat_uid`) instead of beats.
2. Drop beats that share a boundary with a beat of another arm in which a cross-beat fire or a suppression action occurred.
3. Report Moran's I of beat-level residuals over beat adjacency.

**Spillover:** each fire records whether it crosses a beat boundary, the beats it touches, and any suppression action and time. These are listed per arm.

### 0.6 Where first-day fires are found (both streams)

Reported per arm:
- **(a)** confirmed starts found by ignition-stream inspections;
- **(b)** confirmed starts found by response-stream visits;
- **(c)** confirmed starts found by chance finds;
- **(d)** the total of (a) to (c), against all first-day fires in the post-season grouping (satellite plus field).

This shows whether flexible allocation improves early detection overall or only moves where fires are found. The dry run found that 26% of first-day fires fall inside the excluded zone (section 5), so (b) matters.

- **Time to discovery** (discovery time minus the FSI method's estimated ignition time) is reported for (a) to (c).
- **The 1.5 km / 3-day rule is the locked primary configuration.** Other thresholds (0.75 km / 1 day and 3 km / 7 days) are sensitivity analyses on satellite data only, and do not change the field experiment.

### 0.7 Other locked items

- **Two streams:**
  - The ignition stream is what differs between arms (dryness ranking; the arm sets the daily total; ineligible cells are never sent).
  - The response stream is identical in every arm (the existing satellite-alert visits).
- **The recent-fire ranker** runs in shadow mode only. It is scored on the response stream and never quoted as ignition prediction.
- **Wording:** the eligibility class is "no nearby recent VIIRS detection". "Fire start" is used only for the classification in 0.2.
- **Reproducibility record on every task:** model hash, code commit, config hash and data cutoff time.
- **Satellite stand-in outcomes** are secondary: burned cell-days found, the measure used in the dry run.

### 0.8 What one season can show (`scripts/pilot_power.py`, `results/pilot_power.json`)

This is a dry run of the ignition stream: real arms, equal hours per arm, satellite stand-in (burned cell-days, not field fires), and a beat bootstrap within arm. The locked analysis in 0.5 will use block randomisation inference instead.

| Rate ratio, 95% interval | 2025 | 2026 |
|---|---|---|
| Calendar vs fixed | 2.05 (1.57-2.78) | 1.90 (1.39-2.62) |
| Forecast vs fixed | 2.53 (1.89-3.54) | 1.88 (1.39-2.63) |
| Forecast vs calendar | 1.23 (0.97-1.57) | 0.99 (0.72-1.34) |

- H1 should be answerable in one season.
- H2 should not.
- Field counts will be smaller, so the intervals will be wider. If H1's interval includes 1, the result is read alongside the retrospective evidence, and a second season decides.

### 0.9 Exploratory: fewer fires lit, and displacement (added 16 Oct, Akkshay's choice on the FSI thread's decision card)

These are **exploratory**. The primary outcome (0.2) and H1/H2 (0.4) are unchanged. The primary measures detection only. A satellite fire count does not depend on what patrols report, so it can show deterrence (Dobson et al. 2019; evidence in `ratapani/fsi/scouting/patrol_effectiveness.md`).

**E1, deterrence**
- **Measure:** satellite (VIIRS) first-day fires per beat, per arm, 15 Feb-15 Jun 2027. Fires are grouped with the locked FSI fire grouping and assigned to the beat of the ignition point.
- **Statistic:** the rate ratio of the flexible arms against the fixed arm, by the same block randomisation inference as 0.5, with offset log(`forest_km2` in `beat_arms.csv`: forest fraction × 0.25 km² summed over the beat's cells).
- **What it can detect:** with the locked `beat_arms.csv` and no treatment effect, 2017-26 seasons spread from 0.84 to 1.18. Power is 0.16 for a 10% drop, 0.50 for 20%, 0.84 for 30% and 1.00 for 40% (`ratapani/fsi/scouting/code/patrol/deter_power.py`, 3,435 first-day fires).
- **Reading:** only a large effect will show in one season.

**E2, displacement**
- **Measure:** first-day fires in beats that border flexible-arm beats, against beats that border fixed-arm beats. Beats bordering both are reported separately.
- **Why:** spillover can bias H1 either way. Fires pushed into neighbours inflate the contrast, and patrols reducing fires next door shrink it.
- **Reporting:** with E1 and the spatial sensitivities in 0.5.

**Optional dose measures** (recorded, not tested)
- **Per completed inspection:** minutes on site (from `site_entry_utc` and `site_exit_utc`), people met, and warnings given or FIRs/POR registered.
- **Effort per arm:** person-hours per km² of forest per week.

Not adopted: randomised visits to random cells. Akkshay chose the option without them.

## 1. Dry run on 2025 and 2026 (`scripts/retro_pilot.py`, `results/retro_pilot.json`)

**Setup**
- **Model:** trained on 2017-24 only and never refitted. The daily forecast and the cell scores are both made with no look ahead.
- **Same staff-hours:** each rule's season total of checks is scaled until its staff-hours equal today's fixed 5 per beat per day (about 32,000-33,000 hours a season).
- **Staff-hours per beat-day:** a nearest-neighbour round trip from the beat centre through the day's checks. That is straight-line distance × 1.4 at 15 km/h, plus 0.5 h on site per check. Crews work in the beat they check.
- **Fire classes:** each burn is classed by what was known on the issue day.
  - **Near active fire:** a VIIRS point within 1.5 km in the last 3 days.
  - **New ignition:** no such point.
  - About half of all burned cell-days fall in each class.

**Results** (2025 / 2026, same staff-hours)

| Rule | Checks a day | New ignitions found | Near-active-fire burns found | All burns | Checks with no burn in 2 days |
|---|---|---|---|---|---|
| Random, 5 per beat | 423 / 405 | 16 / 17% | 14 / 16% | 15 / 17% | 96% |
| **Today: fixed 5 per beat** (dryness model) | 423 / 405 | 30 / 30% | 27 / 29% | 28 / 29% | 93% |
| Calendar sets the daily total, dryness model | 456 / 438 | 53 / 56% | 65 / 62% | 59 / 59% | 87% |
| **Forecast sets the daily total, dryness model** | 457 / 439 | **54 / 56%** | 68 / 70% | 61 / 63% | 86% |
| Forecast sets the daily total, recent-fire ranker | 460 / 441 | 46 / 52% | **92 / 95%** | **69 / 73%** | 85% |

**What it shows**
- **The same staff-hours roughly double what is found.** The cause is concentrating checks in the weeks that burn and sharing them across beats. Sanctuary-wide checks also cluster, so the same hours buy about 8% more checks.
- **For new ignitions the calendar does almost all of the work.** The daily forecast adds about 0-1 point over the calendar curve. It helps more on burns near active fire.
- **The recent-fire ranker is a different tool.** It finds 92-95% of burns near active fire, but fewer new ignitions, because it spends checks next to fires already seen. Step 3 of the design is therefore essential: score the two classes separately, or both arms look better than they are.
- **About 85-93% of checks find no burn within 2 days.** This holds under every rule, because a 25 ha cell rarely burns in a given 2 days. Officers need to expect this.

**Recommended split for the pilot**
- **Ignition list (no nearby recent VIIRS detection):** a calendar-led or forecast-led daily total with the dryness model, excluding cells within 1.5 km of a fire seen in the last 3 days.
- **Active-fire surroundings:** handled by the existing alert visits in the field app, plus the recent-fire ranker for the cells around them. Count these separately.

## 2. Design

- **Arms:** randomise the 94 beats into three arms, stratified by past burning:
  1. fixed 5 per beat per day;
  2. calendar-only daily total, shared across that arm's beats;
  3. forecast-led daily total, shared across that arm's beats.
- **Same staff-hours:** each arm's season staff-hours equal 5 checks per beat per day under the hours formula above, then are corrected with real logged travel after the first 2 weeks.
- **Why beat arms:** they run all three rules in the same weather on the same days. Alternating weeks would confound the rules with the fire calendar.
- **Frozen inputs:** everything is locked by 1 Feb 2027 (section 0). Lists are issued each evening for the next 2 days.
- **Ignition stream only differs by arm:** cells within 1.5 km of a VIIRS point in the last 3 days go to the response stream in every arm (v2 supersedes the v1 "send and flag" rule).
- **Scoring after the season:** follow the primary endpoint and secondary outcomes in section 0, using logged staff-hours.

## 3. Step 5 records in the field app (`field-system/INTEGRATION.md`, "Patrol pilot")

Everything listed in the v1 gap table has now been built by the field thread:
- predicted-cell tasks with arm, version record and the near-active flag;
- burn age;
- the "nothing found" outcome;
- the crew-day shift log;
- per-stream hours;
- chance finds;
- auto-links to alerts;
- the inspection-evidence rule;
- the per-arm season report and the missed-alerts list.

The v3 changes in sections 0.2, 0.3 and 0.6 have been sent to the field thread.

Field label checks are not possible yet (Akkshay, 14 Oct), so this protocol is for when they are.

## 4. Answers to the field thread's open points (`field-system/PILOT_GAPS.md`)

- **Arm assignment:** per beat. The table is `pilot/beat_arms.csv` (beat_uid, block, cells, burned cells per season 2017-24, arm).
  - Beats were sorted by past burning and randomised in blocks of 3 (seed 20261015).
  - The arms have 31-32 beats each, 1,155-1,237 cells, and 647-666 burned cells a season.
  - Task `arm` comes from the beat. A chance find takes the arm of the beat it falls in.
- **Cell polygon:** the 500 m grid cell. For Ratapani that is `ratapani/grid_500m.geojson` `cell_id`; MP-wide it is the mp_grid cell. Store `cell_id` on the task as well as the polygon.
- **Reached:** the phone must be inside the cell, not just near its edge. A 25 ha cell can be checked from anywhere inside it.
- **Near active fire (v2):** these cells are not sent as ignition-stream tasks in any arm. They are covered by the response stream. Keep the flag on any task, fixed at issue time.
- **Due window:** lists are issued in the evening of day t, and the window is day t+1 06:00 to day t+2 19:30 IST. Store `issue_date`.
- **model_hash:** the SHA-256 of the frozen model file(s). It is the same for every task in the season.

## 5. Check against fire-level ignition points (`scripts/ignition_check.py`, `results/ignition_check.json`)

This uses the FSI thread's ignition points (`ratapani/fsi/scouting/ignition_points.md`). There, events are grouped into fires, and `event_role` marks the first day of each fire. There are 4,194 first-day fires from 2017 to 2026.

**How the ignition-stream rule sorts them** (no VIIRS within 1.5 km in the last 3 days):
- 26% of real first-day fires fall inside the excluded zone. Most are separate fires started near another fire.
- Only 8% of later-day events would be called new.

**First-day fires whose ignition cell was on an ignition list issued 1-2 days before** (2025-26, 725 fires):

| Rule | First-day fires listed |
|---|---|
| Fixed 5 per beat | 27% |
| Calendar total | 48% |
| Forecast total | 50% |

The ranking of the arms holds on real fire starts.

Scoring follows section 0.2 (fire-start classification table) and 0.6 (first-day fires by stream). The 1.5 km rule only decides eligibility.
