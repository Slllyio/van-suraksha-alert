# Live division models and daily scoring script (PC)

The 87 +GIS division models behind the live rule (`mp/results/officer/live_*`, `field-system/pc_check/`):
LightGBM binary, trained on 2019-24 sampled cell-days (all fire cell-days + 3% of others) with the GFS weather of the
issue day; weak divisions (< 1000 own training fire cell-days) are trained on own data x3 + neighbouring divisions x1.
Target: a fire (VIIRS S-NPP / NOAA-20 / NOAA-21, type 0, seasonal rules) in the square on day +1 or +2.

| Path | What |
|---|---|
| `live_score.py` | standalone daily script (numpy, pandas, lightgbm): one issue day -> score, calibrated %, quiet, flag per square |
| `meta.json` | per division: feature list, weak / borrowed neighbours, check result; LightGBM params; live-rule constants (k, floor, quiet, share) |
| `calibration/<division>.json` | isotonic map fitted on the 2025 season: `pct = 100 * numpy.interp(score, x, y)` |
| `models/<division>.txt` | LightGBM model text files (about 1.2 GB in all; delivered separately because of size, see below) |

Checks done on the PC:
- Every saved model, reloaded, reproduces the stored 2026 +GIS scores exactly (max abs difference 0 for all 87).
- `live_score.py` run on the saved models with the 2026-04-05 feature tables and season state reproduces
  `field-system/pc_check/live_flags_2026-04-05.parquet` exactly: 430,776 squares, 23,858 flags, 0 disagreements,
  every division's count identical (pct differs by < 1e-7).

Inputs per issue day (see the script's docstring): one parquet per division with `cell` (mp_grid cell), `quiet` (no
type-0 detection within 5 km on days t-6..t) and every feature in `meta.json[divisions][<division>][features]` (same
definitions as the training tables: fire history and neighbourhood counts, GFS weather, MODIS / HLS dryness,
AlphaEarth, terrain, access and the 33 static GIS inputs), plus `season_state.csv` (running daily mean score per
division; start the season without it). The script writes the flags, per-division counts and the next state file.
