# Cloud replay of the officials' 2-day list (20 Oct 2026)

Script: scripts/cloud_replay.py. All 87 divisions, 5 PC check days. Cloud GFS, ERA5 soil (not ERA5-Land) and MODIS
(pc_models/cloud_series) replace the PC's Earth Engine inputs. Everything else is the PC's: builder, fire history, HLS npz,
models, calibration, and each division's own_count from pc_check/division_counts.csv.

| day | PC flags | same squares | score r | fire squares (next 2 days) | caught PC | caught cloud |
|---|---|---|---|---|---|---|
| 12 Mar | 85,505 | 93.7% | 0.990 | 2,541 | 75.8% | 76.0% |
| 17 Mar | 84,275 | 92.7% | 0.985 | 2,076 | 74.1% | 74.3% |
| 5 Apr | 23,354 | 90.3% | 0.991 | 673 | 25.0% | 25.4% |
| 22 Apr | 64,155 | 91.4% | 0.986 | 2,741 | 48.7% | 48.6% |
| 10 May | 10,592 | 85.8% | 0.983 | 324 | 17.3% | 17.3% |
| all | | 92.2% | | 8,355 | 60.1% | 60.2% |

About 8% of the squares change, but the list catches the same fires. Not yet covered: HLS from the cloud (PC npz used here),
and the own_count running state (PC's taken as given). Raw output: replay_days.csv, replay.json.

## Every input from the cloud (all_cloud/)
This run adds cloud HLS (app/cloud_hls.step_fast, NASA LP DAAC, 4-7 min per statewide step, r 0.98-0.99 vs PC) and
PIPELINE's ERA5 -> ERA5-Land soil map (pc_models/soil_map/). Fire history is still the PC's fire_celldays (cloud VIIRS
matched it 20/21 exact) and own_count is still the PC's.

| day | same squares | caught PC | caught cloud |
|---|---|---|---|
| 12 Mar | 94.4% | 75.8% | 76.5% |
| 17 Mar | 93.1% | 74.1% | 74.3% |
| 5 Apr | 87.7% | 25.0% | 25.3% |
| 22 Apr | 90.5% | 48.7% | 48.9% |
| 10 May | 86.0% | 17.3% | 17.9% |
| all (8,355 fire squares) | 92.1% | 60.1% | 60.5% |

Built with scripts/cloud_hls_season.py. The npz is kept out of the shared folder (space) and rebuilds in about 1 h.

## Evening runner with real input ages (scripts/cloud_daily.py --replay)
Same 5 days, everything from the cloud, scored by the runner itself. Rule counts are the PC's.

| input ages (MODIS days from composite start, soil days, HLS days late) | caught | same squares as PC |
|---|---|---|
| model's own (9, 5, 0) | 60.5% | 92.2% |
| MODIS 21 days | 59.9% | 82.2% |
| soil 15 days | 60.4% | 91.4% |
| HLS 10 days late | 60.4% | 86.2% |
| all three (real life) | 58.5% | 78.1% |
| PC, model's own ages | 60.1% | |

Real-life ages cost about 2 points on these 5 days, mostly from MODIS. PIPELINE's full-season rescore puts the cost at about
1 point (66.7/47.3/82.1 vs 67.5/47.6/82.3), so no retrain.
