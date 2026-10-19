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
| `models/<division>.txt.xz` | LightGBM models, shrunk and xz-compressed (198 MB in all; Git LFS). Shrinking only removed fields LightGBM never reads to predict (tree_sizes, split gains, internal values/weights/counts, leaf weights/counts, feature importances); scores are bit-identical. Load: `lightgbm.Booster(model_str=lzma.decompress(open(f, "rb").read()).decode())` (done by `live_score.py`) |

Checks done on the PC:
- Every saved model, reloaded, reproduces the stored 2026 +GIS scores exactly (max abs difference 0 for all 87).
- `live_score.py` run on the shrunk models (`models/*.txt.xz`) with the 2026-04-05 feature tables and season state reproduces
  `field-system/pc_check/live_flags_2026-04-05.parquet` exactly: 430,776 squares, 23,858 flags, 0 disagreements,
  every division's count identical (pct differs by < 1e-7).

## Inputs for cloud scoring

| Path | What |
|---|---|
| `static_inputs.parquet` (Git LFS, 56 MB) | one row per square of every division grid (430,776; a boundary square appears once per division): `cell`, `division`, `ae00`-`ae15` exactly as the live models use them in the 2026 season (the division's own PCA-16 of AlphaEarth, fitted on 2017-2024, applied to the 2025 embedding), terrain (`elev_m_*`, `slope_deg_*`), WorldCover (`wc_*`, plus `forest_frac` = `wc_10`), population (`pop_*`) and proximity (`dist_*`, `depth_in_forest`). A column is empty for divisions whose model does not use it (e.g. `wc_90`, dropped where constant). Checked: equal to the 2026-04-05 tables (0 difference) |
| `gfs_features.py` | GFS (+ ERA5-Land soil moisture 5 days old) -> the weather columns (`tmax`, `rh`, `vpd_max`, `wind`, `prcp_mm`, `swvl1`, `prcp_7`, `prcp_30`, `dry_days`, `vpd_3`) and the two interactions (`spread_vpd`, `dry_nearfire`). Self-check: reproduces the stored 2026-04-05 values exactly for both example divisions |
| `gfs_pull.py` | the Earth Engine pull that made the daily GFS series (00Z run of the issue day, hours 3-24, division convex hull) |
| `example_2026-04-05/` | full 2026-04-05 feature tables for Shivpuri (largest, 13,798 squares) and Ujjain (smallest, 239), with `cell` and `quiet`; their GFS and ERA5 soil-moisture series since 1 Oct 2025; the season state before 5 Apr. `python gfs_features.py Shivpuri example_2026-04-05/gfs_daily_Shivpuri_Ujjain.csv example_2026-04-05/era5land_swvl1_Shivpuri.csv example_2026-04-05/Shivpuri.parquet` prints 0 differences |

The 33 static GIS columns (`elev` ... `beat_5k`) are `ratapani/mp_grid/static_gis_v1.parquet` joined on `cell`.
## Daily feature builder (no PC pipeline needed)

| Path | What |
|---|---|
| `daily_run.py` | one command per issue day: builds every division's table, then runs `live_score.py` (usage in its docstring) |
| `build_day_features.py` | every model column for one division and day from raw inputs: fire history (`cell_d*`, `nb3/nb7_d*`, `aoi_d*`, `dsl`, `fdist_d*`, `clim_cell`, `clim_nb7`), early burns (`early_*`), `quiet`, MODIS (`ndvi`, `ndmi`, `lst_k`, anomalies, `ndmi_d16`, `*_chg16/32`, `ndvi_peak`, `leaf_loss`), HLS dryness (`hls_*`, from the season's `mp_dry_<season>.npz`), `doy`, static + GIS columns, weather (via `gfs_features.py`) and the interactions; same float32 arithmetic as the pipeline |
| `fire_celldays.parquet` (Git LFS, 5 MB) | the fire history the models saw: one row per (IST date, row, col) with a VIIRS type-0 detection, 2014-01 .. 2026-06, all satellites. Append new days with `make_fire_celldays.to_celldays(firms_rows)` (`daily_run.py --firms`). History back to 2014 is needed (burn climatology since 2014; days since last fire up to 400) |
| `modis_clim.parquet` (Git LFS, 48 MB) | per division and cell, the MODIS as-of climatology (2013-12 .. 2024) per 14-day bin 3-10 for `ndvi`, `ndmi`, `lst_k` (used by the anomalies); `make_modis_clim.py` made it |
| `static_inputs.parquet` | now also carries `slope_deg_mean_f64` (the original float64 slope; `spread_slope` is formed with it, as in the pipeline) |
| `make_fire_celldays.py`, `make_modis_clim.py`, `build_static.py` | how the three tables were made |

### New season: AlphaEarth step (`make_static_season.py`, `ae_pca.npz`)
Season S uses the AlphaEarth embedding of year S-1 through each division's own PCA-16. `ae_pca.npz` holds the 87 PCAs
exactly as the live models use them (mean and components; fitted on 2017-2024, `save_ae_pca.py`); applied to the 2025
embedding they reproduce `ae00`-`ae15` of `static_inputs.parquet` exactly (0 difference, all 87 divisions).
`python make_static_season.py --season 2027 --models .` pulls the 2026 embedding from Earth Engine and writes
`static_inputs_2027.parquet`; `--season 2026 --check` rebuilds the 2026 values from a fresh pull (0 difference on the
divisions tested). As of 19 Oct 2026 Earth Engine has AlphaEarth only up to 2025, so the 2027 file cannot be built yet;
the script stops with that message until Google publishes 2026. For 2027 also use `static_inputs_2027.parquet` in
`daily_run.py --models` (copy it over `static_inputs.parquet` or point a separate models folder at it).

MODIS composites (MOD09A1 ndvi/ndmi, MOD11A2 lst_k; `mp/scripts/mp_ee.py` pulls them per division) are needed from 1 Sep of
the previous year (the `ndvi_peak` window); GFS and ERA5 soil moisture from 1 Oct of the previous year.

Checks (2026-04-05, all 87 divisions, built from raw inputs only: fire cell-days, MODIS composites, HLS npz, GFS, ERA5
soil moisture, static tables):
- every one of the 128 feature columns and `quiet` is identical to the pipeline's tables in all 87 divisions (0 difference);
- scored with `live_score.py`: 23,858 flags, 0 disagreements with `field-system/pc_check`, raw scores identical;
- the same through the one-command `daily_run.py`.

Inputs per issue day (see the script's docstring): one parquet per division with `cell` (mp_grid cell), `quiet` (no
type-0 detection within 5 km on days t-6..t) and every feature in `meta.json[divisions][<division>][features]` (same
definitions as the training tables: fire history and neighbourhood counts, GFS weather, MODIS / HLS dryness,
AlphaEarth, terrain, access and the 33 static GIS inputs), plus `season_state.csv` (running daily mean score per
division; start the season without it). The script writes the flags, per-division counts and the next state file.
