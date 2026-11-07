# Forest loss in Madhya Pradesh 2018-2025: methods, v1 (frozen 8 Nov 2026)

Scope: past loss only, recorded forest (8,973 beats, 9.32 million ha), baseline 2017, loss years 2018-2025. No forecasting.
v1 settings below are frozen; any change after this date is a v2 and must be re-scored on all label sets.

## 1. What is reported

| Item | Source | Role |
|---|---|---|
| **Official loss area** (by state, zone, division, range) | Blind stratified sample, labelled from yearly 10 m strips | Headline figure with 95% range |
| Tree loss map (clearing, tree-to-shrub) | Rules below | Patrol layer; not summed for the headline |
| New farmland (crop and fallow together; active crop as an attribute) | Embedding new-crop map (Guna thread), sample-adjusted | Headline component |
| Reservoir flooding | Water rule below | Masked, reported separately |

Combined loss = tree loss + new farmland, counted once: a new-farmland patch that is also tree loss goes under tree loss with the flag "now cropped".

## 2. Design by zone

| Zone (by division) | Area (ha) | Tree-loss method |
|---|---|---|
| Mixed dry deciduous | 3,011,397 | Wide net + time-series filter |
| Teak | 3,581,792 | Wide net + time-series filter |
| Plantation (MPRVVN, FDC) | 350,755 | Wide net + time-series filter |
| Sal | 2,373,516 | LandTrendr on annual leaf-on composites (30 m) |

Evergreen pockets (Pachmarhi, Amarkantak) follow their division's zone. A phenology test did not separate sal from deciduous, so zones are division-based.
Rollout order (owner's decision): Guna first, then divisions outward by distance from Guna.

## 3. Inputs (stored per pixel; no re-fetch to change settings)
- Sentinel-2 surface reflectance, Oct-Nov composites 2017-2025 at 10 m: NDVI, NBR, bare-soil index. Cloud mask from the scene classification band.
- Dynamic World window means (2017-19, 2022-24, 2019-21, 2023-25, monsoon 2017-19 and 2024) at 30 m.
- Dynamic World annual trees 2017-2025 at 30 m (loss-year sidecar).
- JRC surface water (occurrence >= 5%).
- LandTrendr attributes for sal (year, magnitude, NDVI before and after).
- All Earth Engine reads use computePixels on an explicit grid. sampleRectangle returned tiles upside down (south to north). That voided the scrub-to-farm sweep (section 8); every other layer was checked by correlation against independent signals and is correctly oriented.

## 4. Rules (v1)
**Deciduous and teak, wide net:** woody before (DW trees + shrub >= 0.40); tree drop >= 0.06 and NDVI drop >= 0.05 between windows; plus the recent path (monsoon tree drop >= 0.17) and the shrub-to-crop path; water masked.
**Time-series filter (default, "more recall"):** a single break fitted to yearly Oct-Nov NDVI; pass if the NBR fall at the break is >= 0.15 and at least 3 passing pixels lie in the 5 x 5 box.
**Sal:** LandTrendr loss with magnitude >= 2000, NDVI fall >= 2000, NDVI before >= 3500, year 2018-2025 (values x 10,000).
**Classes:** clearing (later DW crops, bare or built >= trees and shrub) and tree-to-shrub (other tree loss).
**Minimum patch:** 0.1 ha (10 pixels, 8-connected); 0.5 ha reporting view.
**Reservoir flooding (not loss):** a patch is masked when >= 30% of its pixels show water (Oct-Nov NDVI < 0.05) in 2 consecutive later seasons and no water in 2017-18.
**High-confidence flag (not a filter):** DW trees <= 0.10 in the year after the loss year. As a filter it cut Guna tree loss from 2,441 ha to 125 ha and removed every tree loss found in the blind sample. It is kept only as an attribute.
**Views kept from the same data:** balanced (NDVI fall >= 0.15 and NBR fall >= 0.20, 5 px); maximum recall (90% net with window NBR and bare-soil triggers, NDVI fall >= 0.10, 1 px).
**Not in v1:**
- Cumulative NBR trigger (fall >= 0.15 over any 3 years, woody gate). In Guna it added 22,068 ha; recall at the points went from 55% to 79% while precision fell from 56% to 13%.
- Scrub-to-farm layer (retired; section 8).

## 5. Loss year
- **Primary:** the Dynamic World year, the first year annual DW trees fall below 0.30 after having been at or above it.
  On the owner's 51 dated fellings it is exact for 23 and within 1 year for 35 (mean error 1.02 years). **The 0.30 threshold was chosen on these same 51 fellings, so this figure is optimistic.**
- **Attributes:** fitted break minus 1 (within 1 year for 34 of 51; it cannot be later than 2023) and, for farmland, the first winter-crop year.
- DW trees are high in 2017 almost everywhere, which inflates 2018 counts.
- Cropping follows clearing by about 2 years (Bamori histories: 61% of cleared pixels had no rabi crop by 2025), so first-crop years run late.
- Against the other thread's persistent-loss rasters, the years agree exactly for 7-9% of shared area and within 1 year for 35-36%; our year is earlier in about two thirds of cases.
- Sal: the LandTrendr year (not checked against dates).

## 6. Official area: blind stratified sample
Strata: map flag (tree loss or new-crop map) / net fired only / quiet, crossed with old field 2017-19 (DW crops dominant) and distance to 2017 farmland (< 200 m, 200-500 m, > 500 m).
About 300 spots per zone at first, then per division for the divisions with the most loss. Spots are labelled blind (no map, no stratum) from yearly Oct-Nov 10 m NDVI strips and annual DW trees.

**Guna (304 spots, 222,959 ha of forest):**
- tree loss that did not become farmland: 1,491 ha (816-2,167), 0.67%;
- new farmland on 2015 forest land: 5,910 ha (5,200-6,600, Guna thread);
- overlap: 484 ha;
- combined: **6,917 ha (5,944-7,890), 3.10% of forest**;
- mapped tree loss alongside: 2,460 ha.

No loss was found in the 105 quiet spots. If quiet land has a small loss rate the estimate is low (1 in 50 old-field quiet spots would add about 2,000 ha).

## 7. Accuracy (label set and protocol with every number)

| Label set | What | Protocol | Precision | Recall |
|---|---|---|---|---|
| Owner's 284 Guna reference points, area-weighted (truth = any loss) | v1 tree loss, full Guna map | fixed | 56% | 55% |
| same | Tree loss + new-crop map | fixed | 52% | 68% |
| same | Earlier operating point, rule on the point table | fixed setting chosen on these points | 66% | 68% |
| same | Balanced view / maximum-recall view | fixed | 65% / 23% | 55% / 66% |
| 304-spot blind sample (stratified weights) | Tree loss vs my clearing labels | fixed | 27% | 65% |
| same | Tree loss + new-crop map, any loss | fixed | 43% | 81% |
| Owner's 51 dated fellings | Tree loss | fixed | | 51 of 51 |
| Owner's 222 Bamori polygons | Tree loss + new-crop map | fixed | | 86% of polygons, 59% of area |
| Bamori range raster (other thread, confirmed 2019-24) | Tree loss | fixed | 61% of our area inside theirs | 33% of theirs |
| Fatehgarh range raster | Tree loss | fixed | 68% | 34% |
| same rasters, by their loss type | Tree loss | fixed | | abrupt types 35-68%; gradual types 10-20% |
| My sal points (148, 35 real) | LandTrendr | held out by beat | 55% (26-85) | 55% (29-71) |
| 20 LandTrendr patches in Satna and Singrauli, my reading | LandTrendr | fixed | 45% | n/a |
| My 510 + 510 statewide points (30 m chip labels) | Rule | fixed | 18% | 42% |

Ranges are 95% bootstrap ranges by beat.
End state of our tree-loss patches in the other thread's 2022 classes: clearing 84-87% open (crops, fallow, bare); tree-to-shrub 41-47% still forest. Tree-to-shrub is the weak class.

## 8. Tried and withdrawn
- **Scrub-to-farm layer:** retired. The Earth Engine sweep returned every 300-row tile upside down (sampleRectangle). After a local repair (exact match to computePixels) it scored 22% precision and 2% recall at the 284 points. All scrub-to-farm areas from the earlier interim tables (including the scrub part of the 832-chunk interim) are void; the tree-loss parts stand.
- **Survey-calibrated state models** (2015 stock survey, Guna):
  - state accuracy held out by range: LightGBM 70.7%, AlphaEarth MLP 68.5%;
  - turned into change maps, both reach 11-18% precision at the 284 points and give 30,000-60,000 ha for Guna, against about 6,900 ha from the sample;
  - kept as context only (2015 old-field mask, UNDER STOCK vs BLANK split);
  - Prithvi: work moved to its own thread after two DirectML bugs were found (bilinear interpolation and cross-entropy with ignored pixels both give wrong results on the AMD GPU); see `outputs/final/survey_model/`.
- Cumulative NBR trigger and DW next-year confirmation as filters (section 4).
- AlphaEarth embedding change model (recall 1% on Guna). AlphaEarth and Prithvi features in a learned filter (no gain). Learned filter on Guna labels (does not transfer).
- Lower NBR thresholds 0.10 and 0.12; the persistent moderate-fall trigger; the regional-anomaly date correction; post-state checks on LandTrendr; a two-year loss-year band.
- The "53% / 56%" operating point (it mixed settings across folds) and the "82% / 59%" LandTrendr figure (the held-out figure is 55% / 55%).

## 9. Caveats
- **Label quality:** the owner's labels come from Google Earth, mine from 30 m chips. Statewide precision on my labels is a floor.
- **Dynamic World at 30 m:** patch edges are coarser than 10 m.
- **Sal rate:** about half of LandTrendr flags in the two hotspot districts were unchanged land, so the mapped sal rate is likely about twice the true rate.
- **Gradual loss is the main blind spot** (10-20% recall on gradual types).
- **Coverage:** totals cover finished chunks only until the run completes.
