# Ratapani fuel map v3 (2026-10-16): leaf litter, one-season budget

Built per research/fuel-review/README.md section 5 (steps 1-4). Replaces v2 for any new use. It is a RELATIVE map: where litter is more or less, with borrowed absolute values (+/-50%). Fire-derived loads (inversion/, timing/, ignition/) are withdrawn as fuel estimates.

## Files
| file | what |
|---|---|
| burn_seasons_bitmask_10m.tif, burn_count_10m.tif, last_burn_day_10m.tif | burn history 2017-2026 from scar outlines v1 (2026-10-15). 85% of the sanctuary burned at least once; mean 3.3 seasons. |
| litter_potential_{low,central,high}_10m.tif | end-April litter if the ground did not burn this season (t/ha x 100) |
| litter_potential_central_1ha.tif | same, 1 ha squares (t/ha) |
| litter_2026_{15feb,15mar,15apr,15may}_central_10m.tif | litter on that date in 2026, set back to zero where a fire passed earlier that season |
| litter_v3_summary.csv | numbers below |
| litter_v3_overview.png | picture |
| burnhist_v3.py, litter_v3.py | code; inputs in ../work/ |

## Numbers (forest pixels, t/ha)
| map | median | 90th pct | mean under closed canopy |
|---|---|---|---|
| potential low | 1.1 | 1.9 | 1.8 |
| potential central | 1.3 | 2.3 | 2.1 |
| potential high | 1.8 | 3.0 | 2.8 |
| 15 Apr 2026 central | 0.6 | 2.1 | 1.5 (29% of forest already burned that season) |

Published pre-fire litter in Indian dry deciduous / teak forest is about 2.3-4.5 t/ha (Chhattisgarh 2.2-3.4, Odisha 1.3-6.5). Our closed-canopy values sit at the low end of that (central 2.1, high 2.8); open forest is lower because this map has no grass.

## What is measured, borrowed, assumed
| part | status | source |
|---|---|---|
| where the canopy is, how much leaf it sheds, when it sheds (per 10 m pixel) | measured | Sentinel-2 NDVI, monthly Dec-Apr |
| where and when it burned 2017-2026 | measured (outlines lean small) | scar outlines v1, USE_AND_LIMITS.md |
| annual litterfall 4.75 / 5.75 / 7.6 t/ha/yr | borrowed | Jhariya (Chhattisgarh dry deciduous) |
| about half of annual litterfall is on the floor before the monsoon | borrowed | Jhariya |
| frequently burned stands drop less litter (x0.63 to x1.0) | borrowed curve | Jhariya litterfall ratios |
| closed canopy = 70% S2 cover | assumed | |
| no slope effect, no decomposition inside the dry season, no grass | assumed / left out | |

## Grass layer (added 2026-10-16, grass_v3.py)
Numbers from the FSI thread's scouting note (ratapani/fsi/scouting/grass_fuel_load.md): Jhansi rangeland 3.6 t/ha in Nov falling to 1.9 in Feb; grazed Vindhyan plots grow 85-90% less; Ratapani open grass near villages burns half as often.
- grass = 0.6 t/ha within 1 km of buildings rising to 1.8 beyond 3 km (floor 0.5, cap 2.5) x open share of the pixel; 1.8x higher in Nov falling to 1x by 15 Feb; zero after a fire that season. Low/high = x0.6 / x1.4.
- Files: grass_potential_{low,central,high}_10m.tif, grass_2026_15apr_central_10m.tif, fuel_total_potential_central_10m.tif, fuel_total_2026_15apr_central_10m.tif (litter + grass), grass_v3_summary.csv.
- Result (central): open ground now carries ~0.9 t/ha of grass, ~1.2 t/ha total fuel (was ~0.3 from litter alone); closed forest unchanged ~2.1. Forest median total 1.8 t/ha.
- Measured: canopy openness, distance to buildings (Open Buildings). Borrowed: grass amounts and Nov-Feb fall. Assumed: straight-line change with distance, no regrowth after a dry-season fire.
- Burn history still uses scar outlines v1; v2 (2026-10-16) now exists and can replace it in a rerun.

## Not done yet
SWIR exposed-litter check (review step 6). Comparison with FSI / CAMS / FCCS (step 7). Plot data from FSI would turn this into absolute values (step 5, Akkshay's).

## Test: does burn darkness show fuel load? (2026-10-16, Akkshay's idea) - No, not here
5,669 scar outlines v1 with their median relative NBR drop (rdnbr_median) vs litter map, cover, date, size, burned-last-year (severity_vs_litter.csv).
- Darkness vs litter: rank correlation -0.07 (none). Holding canopy fixed: +1 t/ha litter -> +0.017 darker, vs a typical fire-to-fire spread of 0.042: tiny.
- What darkness does follow: canopy (more canopy hides the char, -0.07 per full cover), bigger fires, and ground that burned the previous year shows DARKER, the opposite of a fuel signal.
- 99% of scars are "low severity" and darkness spans only 0.12-0.17 (quartiles). In surface fires under a canopy the satellite sees the canopy and the char/ash colour, not how many kg burned.

Side note (FSI thread, 2026-10-16): fire radiative power on scar outlines v2 implies about 1.0 t/ha burned (median 3.83 ha per MW summed FRP, assumed 3 h per detection). An inference only; consistent with the low end of this map (forest median 1.3 t/ha), not used to set it.

## Check against satellite dry-matter signal (2026-10-16, review step 6)
Sentinel-2 SWIR tillage index NDTI = (B11-B12)/(B11+B12), monthly medians 2023-25 (work/monthly_re), on forest pixels unburnt in the 2024 and 2025 seasons (3.9 M pixels). swir_check.csv.
| month | map vs NDTI | canopy vs NDTI | map vs NDTI at the same canopy | same, 1 ha squares |
|---|---|---|---|---|
| Feb | 0.79 | 0.85 | -0.04 | -0.03 |
| Apr | 0.43 | 0.51 | -0.13 | -0.15 |
| May | 0.66 | 0.74 | -0.14 | -0.16 |
(rank correlations; litter map; "same canopy" = average within 10 canopy bands)
Plain: the satellite agrees with the map only because both follow the canopy. Everything the map adds on top of canopy (how much each patch sheds, burn history, grass) gets no support from this signal; with grass added the within-canopy agreement is -0.3, i.e. where we put more grass (far from villages) the dry-matter index is slightly lower. NDTI also responds to bare branches, bark and soil, so it is not a clean litter measure; this is a check, not a calibration.

## Comparison with the global fuel map (2026-10-16, review step 7)
Global Fuelbed Dataset (Pettinari & Chuvieco 2016, FCCS fuelbeds, ~300 m, PANGAEA doi:10.1594/PANGAEA.849808, CC-BY-NC-SA). Over the Ratapani box (27,615 pixels):
| fuelbed | land cover it assumes | share |
|---|---|---|
| 2013 | soybean crop | 53% |
| 2023 | crop/vegetation mosaic (60% grass, 8% trees) | 40% |
| 2033 | vegetation/crop mosaic (24% trees) | 2% |
| 2140 | grassland (10 t/ha grass) | 1% |
| 2061a | broadleaf deciduous forest | 0.1% |
It takes land cover from GlobCover 2009 and puts nearly all of the sanctuary into soybean or crop mosaics. Litter is given only as depth (1.3-2.5 cm) and cover, not t/ha. So it cannot check our map. CAMS fuel products (~9 km, 1-2 cells over the sanctuary, needs a registered key) were not pulled; at that size they can't check a 1 ha map either.

## Check against GEDI under-canopy laser (2026-10-16)
GEDI L2B monthly shots (25 m, quality flag 1, sensitivity >0.95), 63,077 shots 2019-04 to 2025-04, 28,610 inside the forest mask. Exported on Akkshay's PC (gedi/export_gedi_l2b.py), compared in gedi/gedi_compare.py. Measure: pavd_z0 = plant density in the 0-5 m layer.
- Sanity: GEDI's canopy cover vs ours: rank correlation 0.53 (the shots land in the right places).
- Fuel map vs GEDI low layer: 0.31 overall, but at the same canopy level 0.04 (all months) and -0.01 (bare-tree months Feb-May). Litter + grass: 0.06 / 0.00.
- Ground burned more often has slightly MORE low vegetation (median 0.024 never burned -> 0.040 burned 5+ seasons), ~0.06 once canopy is held fixed; no sign of the fuel reduction the map assumes for frequent burning.
Plain: like the SWIR check, GEDI agrees with the map only through canopy. Caveat: GEDI's lowest layer is mostly bushes and saplings; dry leaves on the ground sit below what it can separate from the ground return. So this cannot prove the litter detail wrong, only that no satellite we have confirms it.
