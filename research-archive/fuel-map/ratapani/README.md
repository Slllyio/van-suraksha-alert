> **Status (Oct 15 2026): relative fuel index, absolute values ±50%.**
> - 86% of the pixel-to-pixel differences in v2 come from canopy cover.
> - Every conversion to t/ha is borrowed from the literature or assumed. No Ratapani plot data exists.
> - The burn history behind v2 comes from the undersized burn-label rasters.
> - The map cannot exceed 3.1 t/ha.
>
> Use it for ranking ground, not for absolute loads. A rebuild is in progress: burn history from the grown scar outlines, then a one-season litter budget with low / central / high maps at 10 m and about 1 ha (plan in `research/fuel-review/README.md` section 5). The fire-derived loads in `inversion/` and `timing/` are withdrawn.

# Ratapani surface fuel load map, 10 m (built 14 Oct 2026)

Surface fuel load (leaf litter + fine dead fuel + cured grass on the forest floor) in **g/ft²**, FSI's unit
(1 g/ft² = 0.1076 t/ha; 1 t/ha = 9.29 g/ft²). Grid: 10 m, EPSG:32643, 7544 x 3348 px, aligned with the
20 m burn-scar rasters (each 20 m pixel = 2 x 2 of these). Forest = ESA WorldCover tree, shrub and grass inside the
Ratapani AOI (775 km²). Crops, built-up, water and bare ground are nodata.

## Files

| File | What |
|---|---|
| `fuel_fsi_strata_10m.tif` | **A. FSI method.** Forest type group x canopy density x slope class, each stratum given one value. |
| `fsi_strata_code_10m.tif` | Stratum code GCS: G = forest type group (5), C = canopy class 0 scrub / 1 open / 2 mod. dense / 3 very dense, S = slope class 0-3. |
| `fuel_continuous_peak_10m.tif` | **B. Satellite-continuous**, peak season (Mar-Apr), for ground not yet burned this season. Main layer. |
| `fuel_season_<Y>_peak_10m.tif` | **C.** B adjusted for each season 2018-2026 using our burn scars: no carry-over litter and less grass where the previous season burned. |
| `canopy_cover_10m.tif`, `canopy_density_1ha_10m.tif` | Tree canopy cover (%) per 10 m pixel, and averaged over 1 ha (FSI's definition, used for the classes). |
| `fuel_cells_static.csv`, `fuel_cells_season.csv` | Same maps averaged to the 3,614 x 500 m scoring cells (`cell_id`). |
| `fuel_model_test.json` | 2-day model test (below). |
| `fuel_maps_overview.png`, `fuel_zoom_4km.png` | Quick looks. |
| `scripts/` | Full rebuild: `layers.py` → `chm.py` → `s2leafon.py` + `s2dry_masked.py` → `canopy_s2.py` → `build_map.py` → `cellfeat.py` → `fuel_model_test.py`. |

All rasters are uint16: **value x 0.1** = g/ft² (or % cover); 65535 = nodata.

## Version 2 (14 Oct, after full reading of the field papers)

v2 replaces v1. Every layer listed above was rebuilt by `scripts/build_v2.py`, and `burn_frequency_2017_2026_10m.tif` was added. The v1 numbers are kept at the bottom of this file for the record.

### Model, per 10 m pixel, April peak of season Y

```
floor = 0.5 x LF_closed x cover_eff x shed_rel x freq_factor x slope_mult
grass = grass_tsf(years since last burn) x (1 - cover30) x vigour x slope_mult
fuel  = floor + grass                       (t/ha; x 9.29 = g/ft2)
```

Terms:
- **0.5 x annual litterfall.** The pre-monsoon floor is about half the annual litterfall. This is the ratio of summer floor to annual litterfall in all 4 fire zones of Bhoramdeo WLS, Chhattisgarh (Jhariya 2017, full text). The 0.5 already includes decay, so there is no separate carry-over term. Saha 2002 found that unburnt plots carry no litter across the monsoon.
- **LF_closed = 5.0 t/ha/yr.** Leaf and wood litterfall for a closed, unburnt stand. Measured values from the papers:
  - Bhoramdeo: 7.6, at a wetter site.
  - Achanakmar-Amarkantak: 4.2 (Thakur 2022).
  - Satpura teak: 3.3-4.5, leaf only (Pande & Meshram 2002).
- **cover_eff.** Canopy cover within 30 m, divided by 0.7 and capped at 1. Cover comes from Sentinel-2, trained on 1 m tree heights.
- **shed_rel.** This pixel's Mar-Apr greenness loss relative to the Ratapani mean, clipped to 0.5-1.5. Burned pixels are masked from the dry-season image.
- **freq_factor.** Set from the share of seasons in which the stand burned (60 m smoothing; Jhariya Table 2 litterfall ratios):

| Burn frequency | freq_factor |
|---|---|
| Never | 1.0 |
| About 1 year in 5 | 0.88 |
| Every 2nd year | 0.76 |
| Every year | 0.63 |

  The frequency is shrunk toward 1-in-5 with 2 pseudo-seasons.
- **grass_tsf.** Cured grass on open ground (Mondal & Sukumar 2016, Mudumalai MR3, the rainfall band closest to Ratapani). Pixels with no burn on record count as 5 or more years. The slope multipliers (1 / 0.95 / 0.85 / 0.75) are an assumption.

| Years since last burn | Grass (t/ha) |
|---|---|
| 1 | 0.6 |
| Each further year | +0.9 |
| Cap | 2.5 |

- **Monthly build-up** (Saha 2002, Gadchiroli): multiply the April value by the factor for the month. The rasters carry these factors as a tag. The January value is an inference.

| Month | Jan | Feb | Mar | Apr | May |
|---|---|---|---|---|---|
| Share of April | 0.5 | 0.70 | 0.88 | 1.0 | 1.0 |

### Which file to use

| File | Burn history used | Use it for |
|---|---|---|
| `fuel_continuous_peak_10m.tif` | All seasons 2017-2026 | Description only. **Do not use it to train a model**: it has seen the fires. |
| `fuel_season_<Y>_peak_10m.tif`, `rothermel/rothermel_season_<Y>_20m.tif` | Seasons before Y only | Models and spread runs |
| `fuel_fsi_strata_10m.tif` | Same as the continuous map | FSI 16-stratum version (Group 5 x 4 canopy x 4 slope). Each stratum gets the mean of the continuous map, so its classes match FSI's method. |

### Results

Ratapani mean is 1.46 t/ha (13.6 g/ft2). In FSI classes:

| Map | Low | Moderate |
|---|---|---|
| Continuous | 78% | 22% |
| FSI strata | 95.5% | 4.5% |

- FSI's Raisen and Sehore districts are 96-99% Low, so the stratum version now matches FSI.
- The continuous map shows the Moderate patches that a stratum mean averages away: dense, rarely burnt teak on gentle slopes.

FSI-strata values in g/ft2 (`summary.json`):

| Canopy | 0-10° | 10-20° | 20-30° | >30° |
|---|---|---|---|---|
| Scrub | 3.1 | 3.4 | 2.4 | 2.8 |
| Open | 10.5 | 10.7 | 9.6 | 7.8 |
| Mod. dense | 18.6 | 19.4 | 17.4 | 15.1 |
| Very dense | 19.6 | 20.5 | 18.3 | 15.5 |

### Rothermel layers (`rothermel/`)

The files:
- `rothermel_peak_10m.tif` and `rothermel_peak_20m.tif`, built from all seasons.
- `rothermel_season_<Y>_20m.tif` for 2018-2026, built from prior seasons only.
- The 20 m files sit exactly on the burn-scar raster grid.

Each file is an 8-band float32 GeoTIFF in SI units at the April peak, NaN outside burnable forest:

| Band | Name | Unit | How |
|---|---|---|---|
| 1 | `w_1h` | kg/m² | 75% of floor (fresh and partly decayed leaf), plus cured grass |
| 2 | `w_10h` | kg/m² | 25% of floor (wood litter; Jhariya Table 1 summer) |
| 3 | `w_100h` | kg/m² | 0 (not estimated) |
| 4 | `w_live_herb` | kg/m² | Green share of grass in Mar-Apr; near 0 |
| 5 | `depth_m` | m | Load-weighted: litter bulk density 6 kg/m³ (Scott-Burgan TL6), grass 0.8 kg/m³ (GR2) |
| 6 | `mx_dead` | fraction | Moisture of extinction, load-weighted: litter 0.25, grass 0.15 |
| 7 | `sav_1h` | 1/m | 6562 |
| 8 | `sb_model` | code | Closest Scott-Burgan model: 91 NB (<0.03 kg/m²), 101 GR1, 102 GR2, 181 TL1 (litter <0.15 kg/m²), 182 TL2 (<0.3), 186 TL6 |

Ratapani peak means:
- `w_1h` 0.117 kg/m², `w_10h` 0.029 kg/m².
- Bed depth 2.9 cm; mx_dead 0.225.
- Models: TL2 39%, TL1 39%, GR1 13%, NB 9%.

These are thin, patchy broadleaf litter beds.

For the spread model:
- **Month.** Multiply loads and depth by the month factor above.
- **Burns earlier in the same season.** Mark pixels from `research/ratapani-burn-labels/rasters/burn_<Y>.tif` as NB from their window_end day.
- **Fuel moisture.** Not included; take it from weather (e.g. VPD-based dead fuel moisture, Sharples 2024).
- **Uncertainty.** Absolute loads are uncertain by about ±30-40% until Ratapani floor samples exist.

### 2-day model test (v2)

Same test as before: LOSO 2017-24, scored on the real beats at 5 picks per beat per day. Only the season maps are used, because they see prior-season burns only. Season 2017 has no prior map, so it is missing in the "alone" row. Results are in `fuel_model_test_v2.json`.

| Ranking | Main rule | True 2-day leads |
|---|---|---|
| Random | 16.6% | 18.8% |
| Season fuel map alone | 18.4% | 22.7% |
| Lean model | 29.5% | 38.9% |
| Lean, restacked (control) | 29.1% | 38.4% |
| Lean + season fuel (total, floor, grass) | 28.8% | 38.1% |

v2 does no better than v1 as a 2-day input. Fuel load still does not tell us where fires start beyond what burn history and dryness already show. Its use is physical: spread rate, intensity and fuel-removal planning.


## FSI's own inputs from the Van Agni portal (14 Oct)

The Van Agni portal (vanagniportal.fsiforestfire.gov.in) has no fuel load layer. Its map service does serve FSI's Forest Cover Map 2023 and Forest Type Map 2021 at about 24 m, as coloured images; classes were decoded from colour (scrub = red and the forest type name are inferred, since the portal legend is empty).

| File | What |
|---|---|
| fsi_fcm_2023_10m.tif | FSI canopy class: 1 VDF, 2 MDF, 3 OF, 4 scrub, 5 water, 0 non-forest |
| fsi_ftm_2021_10m.tif | FSI forest type: 90% of Ratapani is one class (read as tropical dry deciduous, matching our Group 5 assumption) |
| fuel_fsi_strata_fsicanopy_10m.tif | FSI strata map built on FSI's canopy classes x slope (value x 0.1 = g/ft2) |

Inside Ratapani, FSI says 14.6% VDF / 44.9% MDF / 29.8% OF / 9.5% non-forest. Our Sentinel-2 canopy says 14.7 / 33.0 / 33.5 / 18.8. Same class per pixel 48%, within one class 85%; we call more land non-forest and less MDF. On FSI's canopy the strata map is 100% Low (mean 14.2 g/ft2), as FSI's own Ratapani rating would be. Script: scripts/fsi_inputs.py.

Also pulled FSI's fire-prone map (fire_prone_2021) as fsi_fire_prone_2021_10m.tif (1 less ... 5 extremely prone; names inferred from colour). The portal's WCS returns rendered RGB, not raw class codes. Against our burn scars 2017-2026 it ranks well: share of each class burned per season 8.5% / 12.7% / 16.5% / 20.6% / 24.3% (classes cover 4 / 14 / 35 / 41 / 6% of Ratapani).

## Cover classes from the monthly time series (14 Oct, experimental)

cover_phenology_10m.tif: rule-based classes from monthly Sentinel-2 NDVI (Sep-May, 2023-24 + 2024-25) and the S2 canopy cover. Share of the forest mask: deciduous tree 50.5%, green in Mar-Apr under canopy 7.2%, open + green in dry season 0.3%, open grass/low cover 26.8%, sparse/bare 15.3%.

Photo check: 6 points per class on Esri imagery from Feb-Apr 2025, about 0.6 m (cover_check/class1-5.jpg; zoom 19 is not served here). Deciduous and green-crown classes look right. Class 3 points all fell on one irrigated wheat field, so it is crop leaking into the forest mask, not shrub. Class 4 and some class 5 points show a dense, low dark-green mat in April, which could be shrub or grass; at 0.6 m and with no height data under 3 m the two cannot be told apart. No shrub fuel model has been added; doing so needs field notes or sub-metre height (lidar or drone).

## Teak litter as the default surface fuel (14 Oct, Akkshay: teak leaves are the main fuel, all fires are surface fires)

- **Default Rothermel layers for spread are now rothermel/loosebed/**: same loads, teak leaf litter as a loose bed (2.5 kg/m3, coded TL6), surface fuel only. The compact rothermel/ files stay for comparison. Against 1,398 scarred fires the loose bed raised forecast area x2.6 (spread thread).
- **leaf_fall_fraction_10m.tif** (bands Dec, Jan, Feb, Mar, Apr; 0-100): how much of each pixel's leaf-on to dry-season NDVI drop has happened by the end of each month. Multiply the April peak litter by it to get the litter on the ground that month, per pixel. Median over deciduous forest: Dec 30%, Jan 42%, Feb 65%, Mar 91%, Apr 100%, close to the fixed curve used so far (Jan .5, Feb .7, Mar .88). Half the canopy is down by Jan in 23% of the deciduous area, by Feb in 59%, by Mar in 12%. Caveat: the NDVI drop also includes grass curing under the canopy.
- **Teak share per pixel is not mapped.** FSI's forest type map gives one dry deciduous class for 90% of Ratapani, and teak vs mixed dry deciduous cannot be told apart from Sentinel-2 phenology without labelled stands (working plan compartment data from the Forest Department would give it). Litterfall values already use teak figures (Pande & Meshram teak 3.3-4.5 t/ha/yr).

## Teak vs other deciduous (14 Oct)

- teak_probability_10m.tif (0-100): chance a pixel is teak-mixed rather than other dry deciduous. LightGBM on monthly Sentinel-2 NDVI/NDMI (Oct-May) plus red-edge/SWIR (Oct, Dec, Feb, Apr, May), trained on weak labels from the Roy et al. 2015 vegetation type map (60 m, ~2005-10 polygons; teak mixed moist deciduous vs dry + moist deciduous, interior pixels only). 4 km spatial-block CV: AUC 0.81, balanced accuracy 0.70 (NDVI/NDMI alone 0.74). Top features: December red-edge NDRE, Oct/Feb SWIR B12. Other deciduous keeps leaves longer into Jan-Feb and greens in May; teak stays bare until the June monsoon.
- teak_share_cells.csv: per 500 m cell, share of forest pixels with probability > 0.5 and mean probability. Correlation with the 2005-10 map's teak fraction across 3,368 cells: 0.52. Training base rate is 70% teak, so read probabilities relative to each other.
- rothermel/teakmix/: litter bulk density 2.5 kg/m3 for teak, 6 for other deciduous, by probability (assumption based on leaf size; loads unchanged because litterfall is about equal). Spread-thread test on 1,398 fires: outline overlap 0.312 vs 0.327 for the uniform loose bed (0.332 vs 0.342 in the calibrated setup), so it does not help. Use rothermel/loosebed/ everywhere. Spread's final model: loose bed + leaf_fall_fraction interpolated to the fire date + ROS x2, outline 0.348 vs circle 0.345.
- Literature (ratapani/fsi/scouting/teak_vs_mixed_fuel_fullread.md): teak litterfall about equal to mixed; leaf fall later and concentrated (Jan-Mar, Feb peak); leaves barely decay in the dry season; beds deep and loose. In Ratapani, cells mapped teak-mixed burned in 52% of seasons vs 62% for other dry deciduous (association only).

## Fuel loads back-solved from real fires (15 Oct)

See inversion/README.md. Spread runs against the 1,398 scars and VIIRS fire radiative energy give per-class intervals at fire time: closed teak 1.1-2.5 t/ha, closed other deciduous 1.1-2.9, open forest 0.9-4.3 (weak), grass/scrub/sparse 1.0-2.4. Teak and other deciduous cannot be separated by fire. The map underloads grass/scrub/sparse land by about 2-4x (map 0.6 t/ha).

## Next

- **All of MP.** Same scripts, run per district tile.
  - Canopy needs the Sentinel-2 model retrained per region. Teak/sal Group 3 forests (Balaghat, Mandla) need their own values.
  - Earth Engine is the practical route at that scale.
- **Embeddings.** AlphaEarth 10 m embeddings (Earth Engine) are the natural way to spread real floor samples once any exist. Without samples, they would only copy this map.

## v1 record (superseded)

v1 used a stratum table built from the literature and a continuous map with a litter carry-over term and no burn-frequency term.
- About half of Ratapani came out Moderate.
- In the 2-day model (LOSO, real beats, 5 per beat per day), the continuous map alone scored 20.2% (random 16.6%; true leads 25.4% vs 18.8%).
- Added to the lean model it scored 29.0%, against 29.1% for the control (`fuel_model_test.json`).
