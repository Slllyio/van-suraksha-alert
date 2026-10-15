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

## Update: Prithvi (rounds 14–15) — new best
**LightGBM + leaf-fall + Prithvi-EO-2.0-300M embeddings of HLS imagery, pre-season (Oct–Dec) *and* in-season
(the 3 complete months before each issue month)** — `scripts/research_r15_prithvi_inseason.py`.
LOYO 2014–2024, same counting as rounds 1–12 (top 10% of cells flagged, 3×3 tolerance):

| Satellite embedding | Fires caught | Brand-new fires | Worst / best year |
|---|---|---|---|
| none | 75.7% | 42.7% | 64 / 86% |
| AlphaEarth (annual) | 76.9% | 45.0% | 68 / 85% |
| Prithvi pre-season | 77.3–77.9% | 44–45% | 65 / 89% |
| Prithvi in-season | 78.6% | 46.6% | 66 / 88% |
| **Prithvi pre + in-season** | **80.0%** | **48.3%** | **68 / 89%** |

Pre + in-season Prithvi beats AlphaEarth in 10 of 11 held-out years (+3.1 pts overall; largest gains in the harder
recent years 2021 +7.8, 2023 +4.8). In-season windows use only complete months before the issue date (no target leakage).
The ground-covered numbers below were measured with the AlphaEarth model and are expected to rise accordingly.
HLS imagery: monthly medians of HLSL30+HLSS30 (Fmask cloud/shadow removed), 30 m, `scripts/hls_pull*.py`; each 500 m
cell takes the Prithvi token (16 px = 480 m) under its centroid; PCA-16 per embedding set.

## Headline (rounds 1–13)
Best model (before Prithvi): **LightGBM, 255 leaves × 600 rounds, + leaf-fall features** (`scripts/research_r8.py`).
Leave-one-year-out 2013–2024, risk-proportional daily area (more on bad days), measured by **ground actually
covered** (flagged cells + their 8 neighbours, i.e. ~1.5 km patrol reach):

| Ground covered (season avg) | Fires caught | Brand-new fires caught |
|---|---|---|
| 10% | 51% | ~21% |
| 20% | 71% | ~41% |
| 30% | 81% | ~54% |

- Transfer: unseen strip of the AOI **and** unseen 3-year block → 73% vs 76% (same counting as rounds 1–10), so the model carries to new ground.
- Calibrated risk (nested isotonic, r11) matches observed rates: e.g. "within 1.5 km" predicted 6.7% → observed 6.8%, 13.1% → 12.9%. Realistic per-cell 2-day risk rarely exceeds 5–6% (background 0.2%); within 1.5 km tops out ~13–20% (background 1.2%). Suggest reporting % within 1.5 km plus "× normal".
- Horizon (r5): 1-day 75%, 2-day 73%, 3-day 72% (same counting), so skill fades slowly.
- No gain from: bigger LightGBM (511 leaves), CNN (67% LOYO, and ensembling lowers skill), FWI indices, forecast weather beyond +1–2 pts, smoothing the risk map (hurts), spread-out greedy selection (±1 pt).
- Remaining gap = brand-new ignitions; needs new information (NOAA-20 VIIRS, finer human-activity layers, more sanctuaries).

> **Counting note:** rounds 1–12 report "top 10% of cells flagged" with a 3×3 catch tolerance, so the ground
> effectively covered was larger than 10%. Model-vs-model comparisons in those rounds are valid (same counting);
> round 13 gives the honest area numbers above.

## Findings by round
"Caught" = a fire cell with a flagged cell within 1 cell (1.5 km window; VIIRS geolocation ≈ 375 m).
Numbers are leave-one-year-out over 2013–2024 unless stated; areas in items 1–7 are flagged-cell shares (see note above).

1. **Flag ~10% of the AOI's cells over the season, more on bad days and less on quiet ones** → **74% of fires caught**. A fixed 10% every day reaches 60–62%. Simple rules ("fire nearby last week", burn history) ≈ 30%.
2. **Fire types** (by what burned nearby in the 7 days before): continuing (within 1.5 km, last 3 d) ≈25% of fire cells, ~95% caught; nearby (within 5 km, 7 d) ≈55%, ~75% caught; **brand-new ≈15–20%, ~35% caught** (46% of fires in 2023, which explains that year's weak score).
3. **What data helps** (dynamic 10%): fire history 64% → +terrain/land cover/access 71% (land cover +4, terrain +3, roads/villages/pop +3) → +MODIS 72% → +AlphaEarth 72% → +weather 73% → +next-2-day weather (ERA5 as an oracle forecast) 74%.
4. **Resolution:** coarsening to 1 km / 2 km does not raise recall for the same area, so 500 m costs nothing.
5. **Label check:** brand-new fires are not noisier labels than continuing ones; ~89% of all fire cell-days are single VIIRS pixels, and only 11–16% re-burn within 3 days. Fires are small and short-lived, which caps exact-cell 2-day skill.
6. **New-ignition add-on model:** 8% main model + 2% new-fire model (9.2% area) → 71.6% of all fires, **48% of brand-new fires** (vs 37%). Drivers: NDVI (leaf fall/litter), season, AOI activity, time since last burn, humidity/rain, distance to roads, tracks and cropland.
7. **AOI-wide 2-day alert** (2023–24 test): ROC-AUC 0.86; "very high" days hold 94.5% of fire cells, "normal" days 1.8%.

8. **r5** horizon: t+1 75.1%, t+1..t+2 72.6%, t+1..t+3 71.5%, t+2 only 70.3%. Leaf-fall features +1.1 (new fires +1.6).
9. **r6** model family: logistic 68.7%, LightGBM small 69.9% / default 72.6% / large 75.6% (new 43.9%). Spatial strip hold-out 76.9% (72–82% per strip); dropping cell climatology changes nothing.
10. **r7/r10** CNN (dilated, whole-AOI raster): matched LightGBM on one split but 67.3% under LOYO; ensembles 72–74% (worse than LightGBM alone).
11. **r8** large + leaf 76.4% (new 45.6%) = best; XL 76.2%; strict strip+years 73.1% (60–88%).
12. **r9** FWI/FFMC/DMC/DC/ISI/BUI from ERA5: 75.8–75.9% (no gain). `results/r9/fwi_era5.csv` = daily FWI 2012–2024.
13. **r11** nested isotonic calibration (see headline). **r12** smoothing the risk map: 64–71% (hurts). **r13** honest covered-area table (headline) and greedy spread selection (±1 pt).

14. **r14** Prithvi-EO-2.0-300M on pre-season HLS (Oct–Dec): 77.9% vs AlphaEarth 76.9% vs none 75.7% (2014–2024).
15. **r15** + in-season Prithvi windows (3 complete months before each issue month): pre + in-season **80.0%**, new fires 48.3%; beats AlphaEarth in 10/11 years.

## Open research directions
- Prithvi-600M-TL (cached locally), fine-tuning Prithvi on the fire target, ground-covered re-measurement with the Prithvi model.
- Add NOAA-20 VIIRS (2018+) for more overpasses and cleaner labels.
- Finer human-activity layers (villages, cattle routes, mahua/NTFP collection areas).
- More sanctuaries for more training days (also what a deep spatial model would need).
