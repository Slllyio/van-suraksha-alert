# Ratapani burn-scar labels, 2017 to 2026 fire seasons

Dated burn scars at 20 m for Ratapani, built from free Sentinel-2 L2A and Landsat 8/9 C2 L2 (Microsoft Planetary Computer). No VIIRS, Planet or field data. Built 13 Oct 2026 in the "Fire prediction research" thread.

## Files

| File | What it is |
|---|---|
| `burn_windows.csv` | One row per season, 500 m cell and date window: `window_start` (last clear look, not yet burned), `window_end` (first clear look showing the scar), `burned_ha`, `burned` (1 if ≥ 0.5 ha). The burn happened in (start, end]. Use for window labels. |
| `cell_season.csv` | Per season and cell: total burned ha and the first window. |
| `clear_calendar.parquet` | Per season, date and cell: share of the cell's forest seen clear (`clear_frac`), with sensor. Tells a model which cells were actually observed unburned on which days. |
| `rasters/burn_<season>.tif` | 20 m GeoTIFF, EPSG:32643. Band 1 = window_end day of year, band 2 = window_start day of year (negative = December), band 3 = NBR anomaly drop x1000. -999 = no scar. |
| `burn_scars_2017_2026.png` | Overview map, coloured by month the scar appeared. |
| `validation/` | Blind check: `key.csv` (sampled points + detector answer), `judged.csv` (visual verdict: 1 burned, 0 not, 9 unsure), two example sheets. |
| `scripts/` | `fetch.py` (download), `detect.py` (scar detection), `rollup.py` (cell labels), `mkkey.py` + `rerender.py` + `validate.py` (validation). |

Joins to `/mnt/project-files/ratapani/grid_500m.geojson` on `cell_id`. Season *Y* = 1 Dec *Y-1* to 20 Jun *Y*; burns are only dated from 1 Jan.

## Method

1. All Sentinel-2 and Landsat 8/9 scenes under 60% cloud, reprojected to one 20 m grid. Clouds are masked with a ~1 km buffer. Sen2Cor's "dark area" and "cloud shadow" classes are kept away from clouds, because fresh scars get labelled that way. Sentinel-2 is scaled onto Landsat reflectance.
2. Only ESA WorldCover tree, shrub and grass pixels (cropland, built-up and water excluded).
3. A pixel burns at a clear look when its NBR drop since the previous clear look (≤ 20 days earlier) is at least 0.12 more than the drop of the surrounding ~1.5 km (0.18 in January), NIR darkens relative to the surroundings, and the drop persists over the next 25 days. Comparing against the surroundings removes leaf fall and haze that affect whole hillsides at once.
4. Scars smaller than 50 pixels (2 ha) that appeared on the same date are dropped. Tiny isolated drops were mostly false alarms in tuning.

## Accuracy

Blind visual check of 400 pixels (200 flagged burned, 200 not, 20 per class per season). Each was judged on false-colour chips before and after the window plus its NBR time series against its surroundings. 24 were unsure.

| Measure | Value |
|---|---|
| Precision (flagged pixels that really burned) | **0.83** (156 of 187) |
| Unburned pixels that actually burned in the window | 7.4% (14 of 189) |
| Recall, area-weighted | **~0.71** |
| Median date window | 5 days (16 days in 2017, when Sentinel-2 coverage is thin) |

Caveats:
- The judge was Claude, the same agent that built the detector, using the same imagery. This is not independent ground truth. Treat the numbers as an estimate (±~5 points on precision).
- Misses are mostly light ground fires in March, plus scars under 2 ha by design. False alarms are spread through Feb to Apr, mostly drying grass edges and haze.
- 2017 is weaker: only Landsat 8 plus a sparse Sentinel-2 archive, so windows are wide.
- Some January 2024 specks come from a hazy 13 Jan image and are likely false.
- No scars under the canopy that leave the crown green can be seen by any optical satellite.

## Prithvi-EO-2.0 check (14 Oct 2026)

Fine-tuned Prithvi-EO-2.0 100M (before/after image pair, 6 bands) on 3,000 Ratapani chips labelled by this detector, on Akkshay's AMD GPU (scripts in `prithvi/`, model at `E:\FIRE\ratapani_burn\model\best.pt`). Scored on the same 376 judged points:

| | Precision | Area recall |
|---|---|---|
| Detector (these labels) | 0.83 | 0.71 |
| Prithvi, p ≥ 0.4 | 0.86 | 0.71 |
| Prithvi, p ≥ 0.6 | 0.87 | 0.60 |

The models disagree on only 22 points: Prithvi fixes 12 and breaks 10. The gain is inside the check's noise, so the detector labels stay as the labels. Per-point scores: `prithvi/results/eval_points.csv`.
