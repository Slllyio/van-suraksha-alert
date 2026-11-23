# MP burn history 2017-25 on the shared 500 m grid (19 Oct 2026)

Built from the finished MP scar history (clear scars only, 15 Feb-15 Jun, mines/industry removed), on the all-MP grid used by the prediction work (`ratapani/mp_grid`: EPSG:32643, X0 399000, Y1 2996000, 1829 x 1332 cells, cell = row * 1829 + col). Scripts: `../scripts/burn_history.py`, `../scripts/burn_history_check.py`.

## Files
- `cell_year.parquet`: one row per cell and season with any burn. `burned` = share of the 500 m cell inside a scar; `burned_forest` = share burned on forest ground (ESA WorldCover 2021 tree or shrub); `forest` = forest share of the cell.
- `cell_burn_history.csv`: all 373,681 beat cells. `years_burned` = seasons 2017-25 with at least 10% of the cell burned on forest ground; `last_burned` (0 = never); `mean_forest_share_burned`; `beat_uid`.
- `forest_ha_by_year.csv`, `check.csv`.

## Forest-only burned area
| season | all ground (ha) | forest ground (ha) |
|---|---|---|
| 2017 | 996,693 | 783,426 |
| 2018 | 1,067,774 | 800,930 |
| 2019 | 591,727 | 442,309 |
| 2020 | 210,798 | 136,245 |
| 2021 | 1,167,136 | 819,488 |
| 2022 | 1,024,732 | 765,908 |
| 2023 | 393,488 | 280,634 |
| 2024 | 349,166 | 242,615 |
| 2025 | 1,087,653 | 744,767 |

65-79% of the scar ground is tree or shrub; the rest is grass, open ground and farm edge next to forest. Use the forest column for official totals. 40% of beat cells burned at least once in 9 seasons; 436 cells burned in all 9.

## Does it help "burned before"?
For each season 2019-25, cells are ranked by their earlier seasons only, and we count how much of that season's burning falls in the top 10% of cells. Two answers to "what burned this season": scars, and any S-NPP fire point (the second does not come from the scars, so it is the fair test).

| ranking from earlier seasons | catches scar burning (top 10%) | catches S-NPP fire cells (top 10%) | AUC on S-NPP cells |
|---|---|---|---|
| VIIRS fire years 2014 onwards (today's "burned before") | 29.4% | 26.6% | 0.670 |
| VIIRS fire years 2017 onwards | 27.5% | 25.0% | 0.644 |
| Scar years 2017 onwards | 39.8% | 26.5% | 0.670 |
| Scars + VIIRS 2014 onwards | 40.2% | 27.8% | 0.712 |

- On the fair test, scar years from 2017 equal VIIRS years from 2014 even with three fewer seasons, and beat VIIRS over the same seasons (25.0 -> 26.5%).
- Adding scar years to the VIIRS history adds about 1.2 points of fire cells caught in the top 10% (better in 6 of 7 seasons) and lifts AUC 0.670 -> 0.712. Small but steady.
- On scar labels the gain is much bigger (29 -> 40%), but part of that is the same source predicting itself, so it is not counted as proof.

## Burned area three ways (19 Oct 2026)
Same clear scars, counted once on a 20 m grid (scripts/burn_three_ways.py, burned_ha_three_ways.csv). Hectares:

| season | all scar ground | WorldCover tree/shrub | inside beats | beats and WorldCover |
|---|---|---|---|---|
| 2017 | 996,693 | 783,426 | 946,664 | 756,532 |
| 2018 | 1,067,774 | 800,930 | 1,011,465 | 769,345 |
| 2019 | 591,727 | 442,309 | 562,525 | 427,901 |
| 2020 | 210,798 | 136,245 | 197,885 | 133,588 |
| 2021 | 1,167,136 | 819,488 | 1,092,502 | 786,481 |
| 2022 | 1,024,732 | 765,908 | 958,792 | 734,839 |
| 2023 | 393,488 | 280,634 | 369,032 | 270,176 |
| 2024 | 349,166 | 242,615 | 328,331 | 234,307 |
| 2025 | 1,087,653 | 744,767 | 1,010,836 | 714,422 |

93-95% of scar ground lies inside beats, because the scar finder only follows alerts inside forest land. The cut comes from cover: about a quarter to a third of burned ground inside beats is open or grassy land with no tree or shrub cover. "Beats and WorldCover" (66-76% of scar ground) is the strictest number, meaning burned forest cover on forest department land.

## What the burned ground inside beats is (19 Oct 2026)
WorldCover 2021 class of each burned 20 m pixel inside beats (scripts/burn_cover_classes.py, burned_inside_beats_by_cover.csv). Share of burned ground:

| class | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| tree | 74% | 71% | 70% | 59% | 66% | 70% | 67% | 61% | 61% |
| shrub | 6% | 5% | 6% | 9% | 6% | 7% | 7% | 11% | 10% |
| grass | 19% | 23% | 23% | 30% | 26% | 22% | 25% | 27% | 28% |
| farmland | 1% | 1% | 1% | 2% | 2% | 1% | 2% | 2% | 1% |
| water, built, bare | under 0.5% | | | | | | | | |

Almost all of the cut ground is WorldCover "grass", and only 1-2% is farmland. In WorldCover a pixel only counts as tree when canopy cover is at least 10%. Inside MP beats, most "grass" is likely open, degraded or very sparse forest and grassy blanks, not pasture. This has not been checked on the ground. For that reason the tree+shrub figure is a lower bound on burned forest, and "inside beats" is the upper bound.
