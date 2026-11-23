# What the satellite record says about each division (2017-25)

Built 18 Oct 2026 for Akkshay's ask: "insights which nobody knows, not even the DFO". Every claim has a null or a stability test. Plain words first; the method is at the bottom.

**Data:** 184,352 forest fire events in MP, 2017-25 season (15 Feb-15 Jun), from `fire-alert-scars/mp/` (VIIRS + MODIS points grouped into events, each joined to its burn scar and hectares). An event that has another event within 1.5 km on the day before is "the same fire continuing"; otherwise it is a **new start**.

**Stability test used throughout:** a pattern is called a division trait only when the division ranking in odd years (2017, 19, 21, 23, 25) matches the ranking in even years (Spearman correlation). 0 means noise and 1 means a fixed trait.

## Headlines

| # | Finding | Strength | What a DFO doesn't know |
|---|---|---|---|
| 1 | **Fires that are still burning next day** are a division trait: Rewa 37%, Kuno 34% against Kanha 11% and Pench 9% (state 22%). This holds after adjusting for forest share, month and fire density. | odd/even 0.91; adjusted 0.83 | In Rewa and Kuno, a fire that is seen once is twice as likely to still be going tomorrow as their forest and month predict. Kanha and Pench put theirs out (or the fires die) at half the expected rate. |
| 2 | **Fires first seen at night** are a division trait that forest, month and density don't explain at all: Ratlam 53%, Barwah 48%, Dindori 46% against Ashok Nagar 7%, Gwalior 8%, Shivpuri 9% (state 30%). | odd/even 0.92; adjusted 0.93 | In Ratlam, half the new fires start after dark (seen first by the 01:30 pass). In the Gwalior belt almost none do. This is about when people light fires, not about forest. |
| 3 | **Typical fire size** differs 10x and stays put: median scar Rewa 138 ha, Kuno 119, North Panna 81, against Ratlam 13, Sendhwa 13, Khargone 15 (state 38 ha). | odd/even 0.85 | Size goes with #1 (Spearman 0.75): divisions where fires survive the night are the divisions with big scars. |
| 4 | **Burnt last year means more likely to burn again, not less.** For each 1 km forest cell in 2025: burned last year 47%, burned 2 years ago but not last year 40%, burned earlier only 31%, never burned 2017-24 only 6% (all cells 19%). Every year looks the same. | 117,268 cells, all years | A burn does not "clean out" the fuel for next season in MP teak. Last year's scars are the best map of this year's fires. |
| 5 | **Beat edges act as firebreaks, not blind spots.** 45% of fires lie within 250 m of a beat boundary, against 49% of random forest points in the same beats. Edge fires are 0.71x the size of interior fires (smaller in 68 of 72 divisions) and carry over to the next day 4 points less often. | 68/72 divisions | There is no sign that fires on the line between two guards get ignored. Boundaries are often roads and nalas, and these stop fires. |
| 6 | **No division is getting worse or better.** Each division's share of state fires over 2017-25 moves no more than chance: 4 divisions at p < 0.05 against 3.9 expected by luck, and none survives a multiple-test correction. | 87 divisions | Bad years and good years hit the whole state together (rain). A DFO's "my division is getting worse" is the state trend, not theirs. |
| 7 | **Fires come in bursts.** In a typical division the worst 10% of days carry 62% of the season's fires. Most divisions burst on the same days as the rest of the state (sync 0.63), but the north runs on its own calendar: Madhav 0.31, Gwalior 0.33, Kuno 0.35, Sheopur 0.37. | | Northern divisions can't use the statewide "bad day" signal; their outbreaks come on different days. |
| 8 | **Same ground every year, at 1 km.** Only 16.5% of 2025 fires were on 1 km ground that had not burned in 2017-24. The chronic 500 m cells (burnt 4+ of 8 years) are 0.4% of forest and hold 1.4% of fires. | | Most fires fall on known ground, but the very worst cells are too few to patrol your way out of the problem. |
| 9 | **Burning twice in one season** (the same 500 m cell, 10+ days apart) is rare: 1.9% state, highest about 3% (Barwah, Sehore Project, Singrauli). | | Once a patch has burned this season it is mostly done for the season. Re-alerts on the same patch are usually the same fire. |
| 10 | **Weekday has no effect** (earlier test: `ratapani/fsi/scouting/weekday_festival_check.md`). Holi eve is about 1.4x. | known | |

## 1. Still burning the next day (new starts only)

The question: of the fires that are new, what share has another fire event within 1.5 km on the following day? For the null, the same test on a random day 7 days later gives 4.8%. "Expected" adjusts for each division's forest share, month mix and fire density (logistic model); 42% of the spread between divisions comes from those factors, and the rest is the division itself.

| Division | New fires | Observed % | Expected % | Extra |
|---|---|---|---|---|
| Rewa | 851 | 36.8 | 19.9 | +16.9 |
| Kuno Palpur | 466 | 33.7 | 17.7 | +16.0 |
| North Panna | 1,100 | 29.5 | 19.8 | +9.7 |
| Katni | 1,179 | 27.8 | 20.2 | +7.7 |
| South Betul | 2,060 | 28.0 | 20.4 | +7.5 |
| Satpura TR | 917 | 28.7 | 21.6 | +7.1 |
| ... | | | | |
| BTR | 2,499 | 16.9 | 23.4 | −6.5 |
| North Shahdol | 1,954 | 13.9 | 20.5 | −6.6 |
| Kanha TR | 1,460 | 11.3 | 21.2 | −9.9 |
| Pench TR | 453 | 8.8 | 19.9 | −11.1 |

Read: three of the four lowest are tiger reserves with fire crews (Kanha, Pench, Bandhavgarh). Rewa, Kuno and North Panna are fringe and dry-deciduous divisions where a fire is let run or isn't reached. Whether that is suppression or fuel, the satellite can't say. It is consistent with crews, but that is inferred. Full table: `div_still_burning_adjusted.csv`.

## 2. First seen at night

The share of VIIRS new starts whose first sighting is the ~01:30 IST pass rather than the ~13:30 pass. Forest, month and density explain none of the spread (adjusted stability 0.93).

| Highest | % night | Expected | | Lowest | % night | Expected |
|---|---|---|---|---|---|---|
| Ratlam | 53.0 | 24.7 | | Ashok Nagar | 7.0 | 28.1 |
| Barwah | 48.1 | 28.8 | | Gwalior | 7.9 | 26.3 |
| Dindori | 45.5 | 31.5 | | Chhindwara Proj | 8.1 | 25.9 |
| South Betul | 43.2 | 29.2 | | Shivpuri | 8.7 | 27.3 |
| South Chhindwara | 42.8 | 29.7 | | BTR | 11.0 | 30.5 |
| Mohgaon Dindori | 42.1 | 29.1 | | Barghat Proj | 12.7 | 31.4 |

Read: the western and southern tribal belt (Ratlam, Barwah, Dindori, Betul, Chhindwara) lights or keeps fires in the evening. In the Gwalior–Shivpuri belt, fires start and end in daylight. For night-heavy divisions, the 01:30 pass is the main first sighting, so the morning list matters more there. Caveat: a night sighting can also be a day fire that the 13:30 pass missed (one pass in two misses a burning fire). That would affect every division equally, so it can't make a fixed difference this large. Table: `div_night_first_adjusted.csv`.

## 3. Hectares per fire

| Largest median scar | ha | Top 5% of fires hold | | Smallest | ha |
|---|---|---|---|---|---|
| Rewa | 138 | 20% of ha | | Ratlam | 13 |
| Kuno Palpur | 119 | 22% | | Sendhwa | 13 |
| North Panna | 81 | 23% | | Chhindwara Proj | 14 |
| Damoh | 76 | 26% | | Khargone | 15 |
| Khandwa | 75 | 25% | | Mohgaon E Mandla | 17 |

Across the state, the top 5% of fires hold 31% of burnt hectares. Small-fire divisions are the more lopsided ones (Khargone 32%): a few fires there do most of the damage. Table: `div_hectares.csv`.

## 4. Burnt last year → burns again (1 km cells, 2025)

| Cell history before 2025 | Burned in 2025 |
|---|---|
| Burned 2024 | 46.7% |
| Burned 2023, not 2024 | 40.4% |
| Burned only earlier (2017-22) | 30.6% |
| Never burned 2017-24 | 5.9% |
| All forest cells | 18.9% |

This is the same pattern that makes "burned before" a strong baseline in the model work (memory: burned-before catches 44% of scar-confirmed fires). What is new here is the direction: there is no fuel-recovery dip the year after a burn.

## 5. Beat edges

| | Within 250 m of a beat edge |
|---|---|
| Fire start points | 44.7% |
| Random forest points, same beats | 49.0% |

Edge fires: scar size 0.71x interior; next-day carry-over 4.2 points lower; edge higher in only 9 of 86 divisions. Script `d3_controls.py`, distances `edge_dist.parquet`.

## 6-7. Trend and outbreak days

- `div_trend_share.csv`: Kendall trend of each division's share. The biggest apparent declines are Satpura TR, West Chhindwara and North Betul, with q = 0.44 for all of them, which means noise.
- `div_outbreak_days.csv`: share of fires on the worst 10% of days, and the day-to-day correlation with the rest of the state.

## What this changes for the system

- **Brief and big-fire points:** the division trait in #1 and #3 could be one more input to "may become a big fire" (Rewa or Kuno fires survive). Not tested yet in the big-fire model.
- **List timing:** in night-start divisions (#2) the 01:30 pass gives the first sighting for about half the fires. The 4 pm list already includes it, so no change is needed.
- **Pre-season planning:** #4 says last season's scars are the best "where" map for fire lines (fire-line planning thread).

## Method and caveats

- Scripts: `d1_base.py` (events table), `d2_insights.py`, `d3_controls.py`. Outputs are the CSVs and JSON files in this folder.
- Events are satellite sightings, not ground truth. 84% of real fires leave a scar, and January fires are excluded by the season window.
- "Still burning" can mean a new fire lit nearby the next day. The 1.5 km, 1-day rule can't separate that from the same fire.
- The suppression explanations (#1, #5) are inferred and not measured. There are no crew logs (2027 field data is off the table).
- 1 km and 500 m cells: VIIRS position error (~230 m median) inflates "new ground" at 500 m (46.7%), so 1 km is the honest scale.

## Test: does the division habit improve big-fire points? (19 Oct 2026) — no

`d4_bigfire.py`, results in `results_bigfire.json`.

**Set-up.**
- The traits are the share of a division's new fires still burning the next day (#1) and its typical scar size (#3). Each uses only seasons before the test season, shrunk toward the MP figure.
- Each trait was added to the app's big-fire points (which already carry the ±3 "many / few big fires" division item).
- Weights were fitted on one season and scored on the other: the 2025 and 2026 replays, VIIRS truth 200 ha+.
- Null: the traits were shuffled across divisions 200 times.

| | 2025 AUC | 2026 AUC | Big fires in top 10 a day (2025 / 2026) |
|---|---|---|---|
| App points | 0.784 | 0.803 | 19.8 / 28.2% |
| + still-burning habit | 0.782 | 0.801 | 19.6 / 27.5% |
| + typical size | 0.785 (p 0.25) | 0.804 (p 0.12) | |
| + both | 0.781 | 0.802 | 19.4 / 28.6% |

**Verdict.** No gain beyond the shuffled null. The points' division item already carries what these traits know. Keep the traits as briefing facts for DFOs, not as a scoring input.
