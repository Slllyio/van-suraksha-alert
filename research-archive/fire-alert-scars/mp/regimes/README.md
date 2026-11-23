# Fire regimes of MP beat squares from the 2017-25 scars (19 Oct 2026)

Akkshay asked whether pattern-finding ML on the statewide scars shows anything new. This covers "fire regimes": how each 500 m beat square burns over 9 seasons. "What stops a fire" is already covered by the fire-lines work (ratapani/fsi/scouting/fire_lines_v2.md), and "what makes a fire big" by the "Predicting large fires only" thread.

Scripts are in ../scripts/: regime_cells.py (per square and season: first burn day and size of the biggest fire reaching it) and regimes.py (clusters and tests). A season "burn" means at least 10% of the square burned on forest ground (WorldCover tree or shrub), 15 Feb-15 Jun.

## 1. No sharp regimes, one main gradient
A Gaussian mixture on seven traits per square (years burned, share burned, usual burn date, date spread, fire size, share of big fires, longest run of burning years) never settles: BIC keeps falling up to 10 groups. The groups split on counts (burned once vs every year, big fire vs small) rather than forming natural types. MP squares lie along one gradient, from rarely burnt to chronically burnt. Reading the 10 groups (regime_profiles.csv):

| type | squares | years burned of 9 | usual burn date | fire size |
|---|---|---|---|---|
| Chronic burners (groups 2, 5, 8) | 23,255 | 5-7, in runs of 3-5 years | 24-27 Mar, earliest | mixed |
| Regular burners (6, 7) | 43,619 | 3-4 | 30-31 Mar | mixed |
| Occasional, big fires (0) | 11,860 | 2-3 | 31 Mar | every fire 200 ha+ |
| Occasional, small fires (1, 3) | 24,716 | 2 | 4 Apr | small |
| Once, big fire (4) | 16,107 | 1 | 4 Apr | 200 ha+ |
| Once, small late fire (9) | 31,828 | 1 | 7 Apr, latest | small |
| Not burnt 2017-25 | about 222,000 | 0 | | |

Squares that burn more often burn earlier in the season: chronic burners about two weeks before one-off squares. Per-square groups are in cell_regime.csv, and each division's mix is in regime_by_division.csv.

## 2. Do regime traits help next season's ranking? A little.
LightGBM was trained on earlier seasons only. The label is any S-NPP point in the square, which does not come from the scars. Base = years burned (scars and VIIRS since 2014), seasons since the last burn, forest share. Regime = base plus share burned, timing, fire size and run length (test.csv).

| season | top 10% base | top 10% regime | AUC base | AUC regime |
|---|---|---|---|---|
| 2020 | 23.3% | 28.3% | 0.699 | 0.713 |
| 2021 | 17.7% | 17.9% | 0.703 | 0.697 |
| 2022 | 26.9% | 28.1% | 0.755 | 0.764 |
| 2023 | 28.1% | 27.2% | 0.747 | 0.747 |
| 2024 | 22.5% | 27.1% | 0.738 | 0.746 |
| 2025 | 22.0% | 23.3% | 0.741 | 0.741 |
| mean | 23.4% | 25.3% | 0.730 | 0.735 |

That is +1.9 points of top-10% capture, better in 4 of 6 seasons, about the same in 2021 and worse in 2023. It is a small but real "burned before" upgrade for season-level ranking. It has not been tested inside the 2-day model.

## 3. A square's usual burn date does not beat the division calendar
The rank correlation between a square's usual burn date and the date it burns next season is 0.27-0.42. The division's usual date does as well or better: 0.27-0.49, and it is closer in 5 of 7 seasons (median error 6-9.5 days vs 8-12; timing_test.csv). When in the season fires come is a division and weather matter, not a property of each square.
