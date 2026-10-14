# Earth Engine exports for the Ratapani 500 m grid (project: van-suraksha-alert)

Grid: `grid_500m.geojson` (3,700-odd 500 m cells, `cell_id` is the join key). AOI: `ratapani_aoi.geojson`.
Write every output as CSV into `E:\FIRE\ratapani\ee\` with a `cell_id` column.

1. **AlphaEarth annual embeddings** `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`, years 2017-2024: per cell the mean of all 64 bands (A00-A63). One file per year: `alphaearth_<year>.csv` (cell_id, A00..A63). Use reduceRegions with ee.Reducer.mean() at scale 10 m (or 20 m if it times out), export to Drive then download, or getInfo in batches of ~500 cells.
2. **MODIS fuel series** per cell, 2012-10-01 to 2024-12-31: `MODIS/061/MOD09A1` 8-day surface reflectance → NDVI (b2,b1) and NDMI (b2,b6) means per cell per composite; `MODIS/061/MOD11A2` 8-day LST_Day_1km. Files: `modis_ndvi_ndmi.csv` (date, cell_id, ndvi, ndmi), `modis_lst.csv` (date, cell_id, lst_k).
3. **ERA5-Land daily** `ECMWF/ERA5_LAND/DAILY_AGGR` 2012-10-01 to 2024-12-31 for the AOI mean: temperature_2m (max, mean), dewpoint_2m, u/v 10 m wind, total_precipitation_sum, volumetric_soil_water_layer_1. File: `era5land_daily.csv`. Also the 06 UTC values from `ECMWF/ERA5_LAND/HOURLY` if feasible: `era5land_06utc.csv`.
4. **Static**: `USGS/SRTMGL1_003` elevation and slope per cell → `terrain.csv`; `ESA/WorldCover/v200` class fractions per cell → `worldcover.csv`; `JRC/GHSL/P2023A/GHS_POP` 2020 mean per cell → `population.csv`.
5. **WeatherNext probe**: does the project have access to `projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p1deg` and `weathernext_2_0_0`? List the first init time and the latest. Write `weathernext_probe.txt`.

Report back which files were written, their row counts, and anything that failed.
