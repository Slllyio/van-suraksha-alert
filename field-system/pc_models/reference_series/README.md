# Reference series (as used by the live models)

| File | Content |
|---|---|
| `era5land_swvl1_daily_2017_2026.csv` | `division`, `date`, `swvl1`: ERA5-Land daily (`ECMWF/ERA5_LAND/DAILY_AGGR`) `volumetric_soil_water_layer_1`, mean over the division (mp/scripts/mp_ee.py), 2017-01-01 .. 2026-06-30 (end of the PC pull). The models use it 5 days old: `swvl1(t) = series(t - 5)` (`gfs_features.weather_table`). |
| `gfs_daily_2025-10-01_2026-06-30.csv` | `division`, `date`, `t_mean`, `t_max` (deg C), `rh_mean` (%), `wind_mean` (m/s), `prcp` (mm): Earth Engine `NOAA/GFS0P25`, 00Z run of each IST date, forecast hours 3-24 every 3 h, mean over the division's convex hull at 27.83 km (`gfs_pull.py`). No GFS run exists on Earth Engine for 2022-04-20 (outside this range). |

Both are exactly the series behind the 2025-26 feature tables and `example_2026-04-05/`; `gfs_features.weather_table`
turns them into the model's weather columns.
