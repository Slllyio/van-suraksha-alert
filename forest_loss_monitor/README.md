# Forest loss in Madhya Pradesh's recorded forest, 2018-2025

> **Read this first (5 Nov 2026). The figures further down are superseded; do not use them.**
> The 11,509 ha map and the 5,000-10,000 ha estimate below came from an AlphaEarth model that caught 1% of the owner's losses on the owner's
> Guna reference, and my own labels caught only 14 of 55 of those losses. The 26% precision and 54% recall below rest on those weak labels.
>
> **Current method:** the owner's e_Netra rule at 10 m (`e32`, `e33`), extended with a 2023-25 window, a shrub-to-crop class, a water mask and an approximate year.
>
> | Test | Precision | Recall |
> |---|---:|---:|
> | Owner's Guna reference, 10 m map, 281 of 284 points | 56% (32-89) | 48% (31-77) |
> | Round-2 random points, my weak labels, rule at points | 17% (9-27) | 48% (28-72) |
>
> - **Rough state figure, from points only:** about 15,300 ha flagged, not error-corrected, inflated by a 50 m box, and missing most scrub-to-farm conversion. True area is unknown and may be much larger: the owner marked 6 of 180 random Guna forest points as loss.
> - **Known misses:** only 29 of 222 Bamori polygons get any flagged pixel. Dynamic World rates most of them as non-forest before the change, so a separate rabi-cycle signal is being tested (`e39`).
> - **Year of change is weak:** 27 of 50 fellings fall within a year of the recorded date, which is itself an estimate.
> - **Accuracy outside Guna rests on my weak labels only.**
> - **State map incomplete:** 630 of about 3,220 chunks. The GEE project hit its monthly limit (Restricted Mode), which slows all work on the project until 1 December unless the tier changes.
> - **Parivesh records:** 1,036 approved MP proposals, 543 with polygons, 379 whose polygon area is within 0.5-2x of the approved area, 292 of those centred inside recorded forest. Approval does not prove felling. Not yet scored.
>
> Everything below describes the earlier AlphaEarth route and is kept as a record.

**Status: an indicative map, not a pin-point one.** Use the state and zone totals below with their ranges. Treat individual mapped patches and beat figures as leads to check on imagery or in the field: about 1 in 4 mapped pixels was real loss in independent testing.

## Key numbers

| Quantity | Value |
|---|---|
| Recorded forest (8,973 beats) | 9.32 million ha |
| Mapped loss 2018-2025 (final map, water mask applied) | 11,509 ha, not area-corrected |
| Small patches, 0.5-2.25 ha, kept apart | 506 ha; 0 of 40 checked points were real, so do not use this class |
| **Best estimate of true loss** | **about 5,000-10,000 ha, about 0.05-0.11% of recorded forest, see below** |
| Precision of the final map, round 2 | 26% (95% range 19-34%) |
| Recall of the final map, round 2 | 54% (95% range 35-82%), probably too high, see limits |

The best-estimate range comes from two sample rounds. Round 2 gave 5,328 ha (3,050-7,606) with fixed chip years. Round 1 gave 9,863 ha (7,052-12,674) on an earlier map, with chip years that hinted at the map class.

### Mapped loss per year (ha, not area-corrected)

| Year | Clearing | Partial | Total |
|---|---:|---:|---:|
| 2018 | 549 | 1,200 | 1,750 |
| 2019 | 656 | 742 | 1,398 |
| 2020 | 539 | 568 | 1,107 |
| 2021 | 646 | 721 | 1,367 |
| 2022 | 711 | 987 | 1,697 |
| 2023 | 1,192 | 881 | 2,073 |
| 2024 | 854 | 785 | 1,640 |
| 2025 | 262 | 216 | 478 |

Do not read this as a trend. The clearing/partial split was not separately validated. 2025 has no following-year embedding, so it is less certain and low by construction.

### Largest mapped areas

- **Districts:** Singrauli 2,307 ha, Hoshangabad 1,025, Balaghat 863, Burhanpur 678, Mandla 677.
- **Divisions:** Singrauli 2,279 ha, Hoshangabad 1,022, Burhanpur 676, Lamta_Proj_N_Balaghat 418, Lamta_Proj_S_Balaghat 372.
- **Beats:** Navanagar 369 ha, Duddhichua 333, Amlori 237 (all Singrauli, Waidhan range), North_Bhavsa 219 (Burhanpur), Jamani 218 (Hoshangabad).
- **Forest zones:** teak 3,463 ha, sal 3,453, mixed dry deciduous 2,769, MPRVVN plantation divisions 1,824, reported as their own category.

### Comparison with other sources

- **Hansen GFC v1.13:** 3,182 ha for 2018-2025 inside recorded forest at any canopy, 1,981 ha at canopy 10% or more. Hansen scored 21% precision and 10% recall on the same points. Its 10% canopy layer covers only 2.14 of the 9.32 million ha.
- **FSI ISFR 2023:** reports a net fall of 612 km² (61,241 ha) in MP's forest plus tree cover over 2021-2023, per secondary sources; I did not check the official report. This is not comparable with these numbers: it is a net change at 1 ha mapping scale, it includes land outside recorded forest, and it covers forest and tree cover together. The size of the gap is still large and unexplained, so it should be looked into.

## Accuracy by forest zone, final map, round 2

| Zone | Points | Real loss points | Precision | Recall |
|---|---:|---:|---:|---:|
| Sal belt | 129 | 25 | 52% (38-66) | 66% (41-100) |
| Plantation divisions | 43 | 4 | 21% (5-42) | 100%, only 4 points |
| Teak belt | 179 | 7 | 17% (5-29) | 47% (14-100) |
| Mixed dry deciduous | 159 | 4 | 3% (0-11) | 8% (0-100) |

`outputs/validation2/accuracy_by_stratum.csv` also has canopy density, slope and aspect groups. Their ranges are wide, and most groups hold under 10 real-loss points, so read them as rough.

## Limits

1. **The total is not bounded from above.** 130 points across the 9.2 million ha mapped as stable found no real loss. That many points cannot rule out thin or small losses over so large an area. A true rate of 2% in those strata (about 180,000 ha) would still give no hits about 7% of the time. The time-series sweep below did not find hidden loss, but it is weak evidence. Recall is overstated for the same reason.
2. **Labels come from one interpreter.** I labelled false-colour 30 m chips by eye. No field data or very-high-resolution imagery was used, and NICFI time series were not accessible on this account. Partial canopy loss and thin corridors are the hardest cases. Round 1 labels have a known blinding flaw. Please correct labels with `review.html`, then rerun `e14_accuracy.py`.
3. **Sample selection.** Model training labels came from 10 chosen tiles, and enriched chips, not a random sample. Reported accuracy comes from random validation samples only.
4. **The water mask was added after round 2.** It is a fixed outside rule with no tuning, but its 26% precision was measured on the same round 2 sample; without it the figure was 20%.
5. **Mining and farmland.** New mines and roads are clearly detected. Farmland inside forest polygons remains the largest false alarm, at 31 of 80 points in the clearing class before the water mask.
6. **Year assignment.** Annual embeddings give the year of change only approximately. Round 2 labels check whether change happened, not the year.

## Method

Final map: `e6` downloads AlphaEarth Satellite Embeddings (2017-2025, 64 bands, resampled to the 30 m equal-area grid). `e4` and `e16` fit a logistic model on the change between year t-1, t and t+1. `e7` scores every forest pixel. `anomalies.py` removes the regional year shift, which caused a false 15,000 ha spike in 2023. `e8` applies the score, tree-cover drop, core patch of at least 2.25 ha and water mask (JRC max extent, plus 1 pixel). Pixels are exactly 0.09 ha, so areas need no correction. `06` writes tables and maps.

Time series were tested at points and did not enter the map, see below.

## Time-series test

CCDC used Landsat 8/9 and Sentinel-2, 2015-2025, with lambda 0.002 and breakpoint bands NBR, NDMI and SWIR1. Thresholds were set on round 1 and tested on round 2 only. Runtime was about 30 minutes for 1,020 points. LandTrendr at points took minutes.

| Round 2 | All: precision | All: recall | Deciduous: precision | Deciduous: recall |
|---|---:|---:|---:|---:|
| AlphaEarth + water mask | 26% (19-34) | 54% (35-82) | 11% (4-19) | 28% (9-88) |
| AlphaEarth + CCDC confirm | 27% (18-36) | 41% (26-65) | 11% (2-21) | 21% (5-66) |
| CCDC alone | 11% (4-21) | 14% (6-28) | 9% (0-25) | 11% (0-39) |
| Hansen | 21% (6-51) | 10% (3-21) | 0% | 0% |

- **Result:** time series did not beat AlphaEarth in deciduous forest, so CCDC was left out of the map. Deciduous has only 11 real-loss test points, so this is weak evidence either way.
- **LandTrendr:** 82% precision and 59% recall in the sal belt (n=90). This looks promising but is measured on the 36 of 57 tiles with composites, with almost no teak.
- **Stable-pixel sweep:** 450 random stable pixels at forest edges, near mapped change and in the interior. CCDC flagged 1, which is ambiguous on imagery. Of 46 points viewed, none showed clear loss.
- **BFAST-lite:** not run, because it is not available in Earth Engine.
- **Prithvi:** an option in `prithvi/prithvi_ft`, but it needs fine-tuning and HLS downloads, so it is slower.

## Outputs

- `outputs/rasters/`: Cloud Optimized GeoTIFFs: `mp_loss_year`, `mp_loss_class` (1 clearing, 2 partial, 3 small), `mp_loss_recovery` (1 recovered, 2 persistent, 3 unknown), `mp_loss_score_x1000`.
- `outputs/tables/`: year x class CSVs for state, district, division, range, beat and forest zone, with totals and cause hints. Burned area and plantation division are hints, not causes.
- `outputs/maps/`: yearly chart, district and division maps, year-of-loss map, small multiples.
- `outputs/validation2/`: sample key, labels, accuracy, area estimates, KML. `review.html` with its images is kept locally only.
- `outputs/timeseries/`: method comparison and sweep results.

Raw embeddings (56 GB) stay in `work/` and are not in git. GEE assets are in `projects/van-suraksha-alert/assets/forest_loss_monitor`.

## Rerun

```bash
cd forest_loss_monitor/scripts
python 01_prep_boundaries.py
python e6_fetch_embeddings.py all 32
python e9_fetch_aux.py
python e17_water.py
python e4_model_export.py
python e16_refit.py
python e7_score.py v3
python anomalies.py v3
python e8_classify.py v3
python 06_stats_maps.py
FLM_VAL=validation2 python e14_accuracy.py --water
```

`e16_refit.py` needs the labelled points in `outputs/calibration_emb/stage2_points.parquet`, made by `e15_stage2.py`. Self-checks: `python e8_classify.py --selftest`, `python e14_accuracy.py --selftest`, `python e19_ts_eval.py --selftest`.

LandTrendr scripts `02` to `05` remain from the first route. The state composites were cancelled at 36 of 57 tiles.
