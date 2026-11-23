# Earth Engine export: ERA5-Land at native 9 km grid points over Ratapani (project: van-suraksha-alert)

Purpose: replace the single sanctuary-wide NASA POWER series (55 km) with ERA5-Land hourly at every 0.1° grid point that touches the sanctuary, for Dec 2016 to Jun 2026. Both the pipeline thread's model and the ignition study will join on `(date, hour, point_id)` and take the nearest point per cell.

Write outputs as CSV into `E:\FIRE\ratapani\ee\`.

1. **Grid points.** Collection `ECMWF/ERA5_LAND/HOURLY`. Take the pixel centres of its 0.1° grid that fall within the AOI (`ratapani_aoi.geojson`) buffered by 10 km; expect roughly 20 points. Export `era5land_points.csv` (point_id, lon, lat).
2. **Hourly values, Dec 1 of each year to Jun 30 of the next, 2016-12-01 to 2026-06-30**, at those points, bands:
   `temperature_2m`, `dewpoint_temperature_2m`, `u_component_of_wind_10m`, `v_component_of_wind_10m`, `total_precipitation_hourly`, `volumetric_soil_water_layer_1`, `surface_solar_radiation_downwards_hourly`.
   File: `era5land_hourly_points.csv` (datetime_utc, point_id, the 7 bands). About 20 points × 10 seasons × 212 days × 24 h = 1 M rows; export via Drive as one task per season (`era5land_hourly_<season>.csv`) if a single task times out.
3. **Daily summary** at the same points, same dates, as a convenience: tmax, tmin, rh_min (from dewpoint at the hour of tmax), wind speed and direction averaged 06-12 UTC, rain sum, soil water at 06 UTC. File: `era5land_daily_points.csv`. If easier, skip this; it can be derived from 2.
4. Optional, if the project has access: `projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p1deg`, ensemble mean of 2 m temperature, 2 m relative humidity (or dewpoint), 10 m wind at lead times 24 h and 48 h, initialised 00 UTC daily, for the same points, 2024-01-01 to 2026-06-30. File: `weathernext3_points_24h_48h.csv`. This is the operational source later; not needed for training.

Report back the files written, their row counts and the number of grid points.

---
Addendum (research thread, 14 Oct 2026): Sentinel-1 GRD per-cell backscatter pull running on Akkshay's PC (`E:\FIRE\ratapani\ee\s1\pull_s1.py`, output `s1_cells_<season>.csv`, mean VV/VH dB per 500 m cell per acquisition, Dec-Jun 2017-2026). Purpose: tighter scar dating than optical windows. Will be copied to `/mnt/project-files/ratapani/ee/s1/` (research thread owns).
