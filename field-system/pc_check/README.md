# PC check files: live daily rule, 2026 (floor50_quiet35)

Flags from the no-hindsight live rule behind `mp/results/officer/live_fwd*` (statewide pool + 50% division floor +
35% quiet-square reserve, same statewide daily total, calibration on 2025 only, scale k = 0.5874 matched to the current
model's 2026 ground). Recomputed deterministically; ground 21.9% as in the published run.

`live_flags_<date>.parquet` (12 Mar, 5 Apr, 10 May 2026; remade at 35% on 21 Oct, the 25% dumps were replaced), one row per square of every division grid
(430,776 rows; a square on a division boundary appears once per division grid that holds it):

| column | meaning |
|---|---|
| cell | mp_grid cell = row * 1829 + col (EPSG:32643, X0 399000, Y1 2996000, 500 m) |
| division | division whose model scored the square |
| pct | calibrated probability (%) of a detected fire in the square on day +1 or +2 (isotonic per division, fitted on 2025) |
| score | raw +GIS model score |
| quiet | 1 = no type-0 detection within 5 km (+-10 cells) on days t-6..t |
| flag | 1 = picked by the rule that morning |

`division_counts.csv`: per day and division, `squares`, `quiet_squares`, `own_count` (the division's danger-scaled count,
round(k x share x squares)), `floor` (half of it), `flags` (what the rule gave the division: floor plus its share of the
statewide pool) and `quiet_flags`. Each day the flags sum to the sum of `own_count`; about 35% fall on quiet squares;
no division is below its floor.
