# Fire spread tables for machine learning: column guide (16 Oct 2026)

Built by `scripts/b9_ml_table.py`. The quick test is in `scripts/b10_ml_test.py`, with results in `ml_test.json`.
- **Fires:** all 964 Ratapani fires from 2017-26 with 2 or more VIIRS looks. The 146 big fires have `big` = 1.
- **Scar truth:** scar outlines v2 (2026-10-16).
- **Bearings:** compass degrees, 0 = north and 90 = east.
- **Times:** UTC unless the column says IST.

## Which table for which question
| Table | Rows | Use it for |
|---|---|---|
| `fires_ml.csv` | 964 fires | Overall spread rate and direction per fire, and what the fire's ground was like. |
| `steps_ml.csv` | 2,095 look-to-look steps (1,792 with new burning) | Rate and direction step by step. One fire has several steps, so split train and test **by fire or season**, never by row. |
| `sectors_ml.csv` | 14,336 = steps x 8 compass sectors | **"Does terrain or fuel decide the direction?"** Each row is one direction from where the fire was, with what lies 300-1500 m out that way. The target says if the new burning went there. Split by season. |

## How rate and direction are measured
- A **look** is VIIRS detections within 2 h of each other (S-NPP, NOAA-20 and NOAA-21 pass within ~50 min). There are about 2 looks a day, near 01:30 and 13:30 IST.
- **New burning** at a look is its detections more than 400 m from every earlier detection of the fire.
- **`bearing_deg`** runs from the centre of everything seen so far to the centre of the new burning.
- **`advance_beyond_m`** is how far the new burning sits beyond the earlier detections.
- **`rate_m_per_h`** = `advance_beyond_m` / `gap_h`. Treat it as an **upper bound**, for two reasons. A VIIRS block is 375 m wide, with ~300 m position error. And a new front lit nearby also counts as spread. Mid-fire photos give 20-30 m/h.

## fires_ml.csv
| Columns | Meaning |
|---|---|
| fire, big, season, date_start, date_end, doy_start | Ids and dates. |
| first_look_ist, first_look_hour_ist, first_look_night | Time of the first VIIRS detection (IST), and whether it came on a night pass. |
| lat, lon, x_utm43n, y_utm43n | Scar centre. |
| scar_area_ha, n_events, still_at_edge | Scar size (union of the fire's day-events) and how many day-events were joined. |
| duration_h, n_looks | Hours from the first to the last VIIRS detection, and the number of looks. |
| n_det_viirs, n_det_modis, n_snpp, n_noaa20, n_noaa21, night_det_share | Detection counts by sensor, and the share of detections at night. |
| all_* | Every alert field over the whole fire. first_* is the same for the first look only. |
| all_/first_ n_det, n_viirs, n_modis | Counts. |
| all_/first_ frp_sum, frp_mean, frp_max (MW) | Fire radiative power. |
| all_/first_ ti4_mean, ti4_max, ti5_mean, ti4_minus_ti5 (K) | VIIRS brightness at 3.7 µm and 11 µm, and the gap between them (fire contrast). |
| all_/first_ conf_high_share, conf_low_share | Share of VIIRS detections with confidence h or l. |
| all_/first_ pix_km2_mean | Real pixel area (scan x track). It grows toward the swath edge. |
| all_/first_ dozier_p_median, dozier_Tf_median | Two-channel split: the burning fraction of the pixel and the fire temperature (K). Rough, because the background is estimated. |
| all_/first_ frp_area_m2_sum | Burning area implied by FRP at 800 K. |
| modis_brightness_mean, modis_t31_mean | MODIS 4 µm and 11 µm brightness (K), where MODIS saw the fire. |
| frp_per_ha | Total FRP divided by scar area. |
| **rate_median_m_per_h, rate_max_m_per_h, advance_median_m, n_growth_steps** | **Spread rate** over the fire's growth steps. |
| growth_ha_per_h | Scar area divided by duration. |
| **spread_dir_deg** | **Spread direction**: the average bearing of the growth steps, weighted by advance. |
| spread_dir_consistency | 0 = new burning went every way; 1 = always the same way. |
| dir_first_to_scar_centre_deg, dist_first_to_scar_centre_m, max_reach_from_first_m | From the first detection to the scar centre, and the farthest detection. |
| scar_length_m, scar_elongation, scar_axis_deg | Scar long axis: length, long/short ratio, axis direction (0-180). |
| first_pos_along_axis, scar_share_behind_first | Where the first detection sits along the scar (0 = back end, 1 = front), and the share of scar behind it. |
| elev_mean, elev_relief, slope_mean, slope_share_gt5 | Terrain over the scar (SRTM, 20 m): m, m (95th minus 5th percentile), degrees, share. |
| upslope_az_first, slope_first | Terrain at the first detection. |
| canopy_mean (%), teak_mean (% probability) | Canopy and teak over the scar. |
| litter_v3_mean, grass_v3_mean, fuel_total_v3_mean (t/ha) | Fuel map v3, end-April potential. It is a **relative** map (±50%) and mostly follows canopy. |
| burn_count_mean | Seasons burned 2017-26 (fuel map v3). **Includes the fire's own season, so it leaks the answer. Do not use it to predict.** |
| burn_prior_mean | Seasons burned **before** this fire's season (from the 20 m burn labels). Safe to use. |
| wc_tree, wc_shrub, wc_grass, wc_crop | ESA WorldCover shares over the scar. |
| d_building_first_m, hamlets_4km_first, d_road_first_m, d_village_first_m, depth_in_forest_first_m | People and access at the first detection, on the 500 m grid (Open Buildings, OSM). |
| wx_* | ERA5-Land daily mean over the whole sanctuary on the first-detection day: tmax, tmean (°C), RH (%), wind speed (m/s), wind toward (°), soil water, rain over the last 7 and 30 days (mm). |
| cos_dir_upslope, cos_dir_wind | +1 = spread went straight uphill or downwind; −1 = straight downhill or upwind. |
| ahead_minus_behind_* | The 300-1500 m sector in the spread direction minus the opposite sector. Covers elevation, slope, canopy, teak, litter, grass, fuel, burn count, land cover, burned earlier this season, own fire already burning, building and road distance. These use the answer (the direction), so they **explain** a direction. Never use them to **predict** one. |

## steps_ml.csv
| Columns | Meaning |
|---|---|
| fire, big, season, k | k = look number in the fire. |
| t_utc, t_ist, hour_ist, night | Time of the look. |
| gap_h | Hours since the previous detection. |
| n_new_det, new_ground | New-burning detections at this look, and whether there were any. |
| **bearing_deg, move_m, advance_beyond_m, rate_m_per_h** | **Direction and rate** of this step (see above). |
| prev_bearing_deg, cos_prev | The previous step's bearing, and how far this one agrees with it. |
| look_*, prevlook_* | Every alert field (as in fires_ml) for this look and for the previous look. |
| slope_here, elev_here, upslope_az_here, cos_upslope | Terrain where the fire was, and the step's alignment with uphill. |
| wx_*, cos_wind | Weather on the day, and the step's alignment with the wind. |
| ahead_minus_behind_* | As in fires_ml, around this step. These describe the step; don't use them to predict it. |

## sectors_ml.csv (the direction-learning table)
| Columns | Meaning |
|---|---|
| fire, big, season, k, sector, sector_bearing | Sector 0 = north (337.5-22.5°), 1 = NE, and so on. |
| **target_main** | **1 if the new burning's centre lies in this sector.** Exactly one per step. |
| target_new_burning, target_share | Any new-burning detection in the sector, and the share of them that fell there. |
| gap_h, night | Of the step. |
| cos_prev, cos_from_first | The sector against the previous step's bearing, and against the direction from the first detection. Known at forecast time. |
| cos_upslope, cos_wind, wind_ms | The sector against uphill (at the fire) and against the ERA5 wind. |
| elev_diff, slope | Mean elevation of the sector minus elevation at the fire (m), and mean slope. |
| canopy, teak, litter_v3, grass_v3, fuel_total_v3, wc_tree, wc_open, wc_nonfuel | Fuel and land cover in the sector. |
| burn_count | Seasons burned 2017-26 (fuel map v3). **Leaks**: it counts this fire itself. Not for prediction. |
| burn_prior | Seasons burned before this fire's season. Use this one. |
| burned_this_season_before | Share of the sector already burned this season by other fires (raster burn labels, start day before this step). |
| own_fire_already | Share of the sector within 400 m of this fire's earlier detections. |
| d_building, d_road | Mean distance (m). |

The sampling points sit at 6 distances (300-1500 m) x 5 angles across the 45° sector.

## Quick honest test (`ml_test.json`)
Every model is trained without the season it is tested on (LightGBM, kept small).

**Rate** (867 fires): no column group predicts the median rate better than "the median of other seasons".

| model | error vs baseline |
|---|---|
| all columns | 2% better |
| terrain alone | 2% worse |
| fuel alone | 2% worse |
| weather | 4% worse |
| first-look alert fields | 6% worse |

The strongest single link is terrain relief (Spearman +0.24). The measured rate is noisy (see above), which caps what any model can find.

**Direction** (1,792 steps, which of 8 sectors gets the new burning):

| rule or model | right sector (random 12.5%) | within one sector (random 37.5%) |
|---|---|---|
| same way as last step | 20.0% | 49.1% |
| uphill (highest sector) | 15.3% | 43.1% |
| downhill | 9.5% | 33.3% |
| most canopy | 13.5% | 39.5% |
| most litter (v3) | 12.9% | 39.0% |
| most grass (v3) | 11.1% | 37.1% |
| away from buildings | 14.3% | 43.5% |
| downwind | 11.7% | 35.6% |
| model: terrain | 15.2% | 41.6% |
| model: fuel + canopy | 17.8% | 44.1% |
| model: terrain + fuel + burnt + people + wind | 20.1% | 48.9% |
| **model: history + everything** | **24.0%** | **55.4%** |

- Terrain and fuel together are about as good as "keep going the same way".
- Adding them on top of the fire's own history gives the best result: about 2 times random for the exact sector.
- Fires run slightly **uphill** and **away from villages**.
- The litter and grass maps alone carry almost nothing.

**On neural networks.** With ~1,800 steps and ~150 big fires, a neural network will learn the noise. A small tree model (as here) or a logistic model on the sector table is the safer first step. Score anything new against "same way as last step", season by season.

## Added 20:20Z: front speed from all passes (big fires only, in fires_ml.csv)
| Columns | Meaning |
|---|---|
| front_viirs_passes, front_all_passes | Number of single-satellite passes used. |
| front_viirs_speed_m_per_h, front_all_speed_m_per_h | Robust (Theil-Sen) slope of front distance from the start area against time, over every pass. "all" adds MODIS and Sentinel-2/Landsat. **This is the better rate column** (median 25 m/h, which matches the photos). |
| front_*_speed_lo / _hi / _ci_width | 95% range of that slope. |

Every detection as its own row: `../detections.csv`. Every pass as its own row: `../passes.csv`.
