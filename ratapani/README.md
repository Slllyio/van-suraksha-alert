# Ratapani pilot — 2-day fire outlook at 500 m (research)

Pilot AOI: Ratapani (MP). Question: **which 500 m cells will have a VIIRS fire on the next 1–2 days?**
Grid: `data/grid_500m.geojson` (3,614 cells, key `cell_id`). Labels: VIIRS S-NPP 375 m, 2013–2024 (`data/viirs_snpp_2013_2024.parquet`).
Season scored: issue dates Jan–May (97% of detections). This is research, not a product.

## Contents
| Path | What |
|---|---|
| `data/ratapani_ee.zip` (Git LFS) | Earth Engine pulls, CSV per cell (`cell_id`): AlphaEarth 2017–24, MODIS NDVI/NDMI + LST 8-day 2012-10→2024-12, ERA5-Land daily + 06 UTC (AOI mean), terrain, WorldCover, GHSL population, OSM proximity, WeatherNext probe |
| `scripts/` | `ee_export.py` / `wn_probe.py` / `proximity_local.py` (data) → `build_features.py` / `features_v2.py` (cell-day table) → `train_eval.py`, `train_v2.py`, `research_r3*.py`, `research_r4.py` (experiments) |
| `results/` | Metrics JSON/CSV for each round |
| `models/` | LightGBM text models from rounds 1–2 |

Scripts use absolute paths under `E:\FIRE\ratapani` (unzip `data/ratapani_ee.zip` there so CSVs land in `ratapani/ee/`). The large cell-day tables (~300 MB parquet) are not committed; rebuild with `build_features.py` then `features_v2.py`.

## Findings so far
"Caught" = a fire cell with a flagged cell within 1 cell (1.5 km window; VIIRS geolocation ≈ 375 m).
Numbers are leave-one-year-out over 2013–2024 unless stated.

1. **Flag ~10% of the AOI over the season, more on bad days and less on quiet ones** → **74% of fires caught**. A fixed 10% every day reaches 60–62%. Simple rules ("fire nearby last week", burn history) ≈ 30%.
2. **Fire types** (by what burned nearby in the 7 days before): continuing (within 1.5 km, last 3 d) ≈25% of fire cells, ~95% caught; nearby (within 5 km, 7 d) ≈55%, ~75% caught; **brand-new ≈15–20%, ~35% caught** (46% of fires in 2023, which explains that year's weak score).
3. **What data helps** (dynamic 10%): fire history 64% → +terrain/land cover/access 71% (land cover +4, terrain +3, roads/villages/pop +3) → +MODIS 72% → +AlphaEarth 72% → +weather 73% → +next-2-day weather (ERA5 as an oracle forecast) 74%.
4. **Resolution:** coarsening to 1 km / 2 km does not raise recall for the same area, so 500 m costs nothing.
5. **Label check:** brand-new fires are not noisier labels than continuing ones; ~89% of all fire cell-days are single VIIRS pixels, and only 11–16% re-burn within 3 days. Fires are small and short-lived, which caps exact-cell 2-day skill.
6. **New-ignition add-on model:** 8% main model + 2% new-fire model (9.2% area) → 71.6% of all fires, **48% of brand-new fires** (vs 37%). Drivers: NDVI (leaf fall/litter), season, AOI activity, time since last burn, humidity/rain, distance to roads, tracks and cropland.
7. **AOI-wide 2-day alert** (2023–24 test): ROC-AUC 0.86; "very high" days hold 94.5% of fire cells, "normal" days 1.8%.

## Open research directions
- Add NOAA-20 VIIRS (2018+) for more overpasses and cleaner labels.
- Compare 1 / 2 / 3-day horizons.
- Per-cell leaf-fall timing (NDVI drop rate) as a dry-litter signal.
