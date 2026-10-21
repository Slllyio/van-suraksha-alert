# Cloud input series for daily_run.py (no PC, no Earth Engine)

Built 19 Oct 2026 by the live-alerts thread with `field-system/scripts/cloud_series.py` (readers in `field-system/app/cloud_*.py`).
All 87 divisions. Season S = 1 Oct (S-1) to 30 Jun S.

| File | What | Source | Check vs the PC (Shivpuri + Ujjain, 2025-26) |
|---|---|---|---|
| `gfs_daily_<S>.csv` | division, date, t_mean, t_max, rh_mean, wind_mean, prcp: the same columns as the PC's gfs_daily | NOAA GFS 0.25 deg on AWS, 00Z run, hours 3-24, hull-weighted | r 0.9998 / 0.9996 / 0.999 / 0.996 / 0.97; mean abs gap 0.1 C, 0.5% RH, 0.09 m/s, 0.09 mm |
| `swvl1_<S>.csv` | division, date, swvl1 | **ERA5** (Google ARCO), not ERA5-Land | r 0.91-0.96 vs ERA5-Land; Shivpuri 5 Apr 0.171 vs 0.190 (biggest single gap, ~5% of top squares change). Use PIPELINE's soil_map fit when it exists |
| `modis_<S>.npz` | cells, dates (composite start, 1 Sep S-1 .. 31 May S), ndvi, ndmi (x1e4), lst ((K-250) x50); int16, -32768 = none | MOD09A1 / MOD11A2 from Planetary Computer, NASA LP DAAC where PC lacks a composite | on 5 Apr 2026: every MODIS input r 0.985-0.9999, median gap <= 0.003 (lst 0.009 K) |

Load MODIS for one division: `from app.cloud_inputs import modis_frames; sr, lst = modis_frames("modis_2026.npz", cells, 2026)`
then use sr/lst exactly as the `sr_<division>.parquet` / `lst_<division>.parquet` that `build_day_features.modis()` reads.
Weather: `gfs_features.weather_table(gfs[gfs.division == dv].set_index("date"), sw[sw.division == dv].set_index("date").swvl1)`.

Scoring check (5 Apr 2026, PC builder, PC fire_celldays + HLS npz, these cloud inputs): raw score r 0.991 (Shivpuri),
0.998 (Ujjain); 88% / 93% of each division's top-n squares the same as from the PC's own table.
