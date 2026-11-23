# Earth Engine datasets that could help (16 Oct 2026)

Akkshay asked: "search various databases in GEE which can help us".

What I did: I read the live Earth Engine catalogue listing (all 1,164 entries, `earthengine-stac`). I checked each candidate's exact ID, pixel size and dates there. I compared the list with what the project already used and tested, and with the FSI thread's earlier scouting note (`ratapani/fsi/scouting/open_datasets.md`, `high_res_imagery.md`). I ran one real check (ECOSTRESS, section 3). **Nothing below has been tested against our scores yet.** "Could add" means a reason to test, not a gain.

## 1. Plain answer

- **2-day "where" map:** it is at a ceiling. Every extra layer tried so far added nothing (fuel, mahua, AlphaEarth, OSM, weather, Prithvi, MODIS LST). The catalogue has nothing that changes this. The one exception worth a single test is **weak divisions with little fire history** (cold start). There, village size from Open Buildings may help, the way mahua might.
- **Spread and big fires:** the main limit is that we only see fires twice a day. **ECOSTRESS** (70 m heat images from the Space Station, taken at changing hours of the day) is the one new source in Earth Engine that could add looks at other hours. I counted about 11 useful passes per season over Ratapani (section 3). That is the best new lead.
- **Fuel map:** right now it is mostly canopy cover. **GEDI** laser shots measure how much vegetation sits in the low layer under the trees. It is the only satellite measurement that looks under the canopy, so it is the honest independent check.
- **Burn scars:** **Planet NICFI** monthly 4.8 m images could show small scars that 10–20 m Sentinel-2 misses. It needs a free sign-up.

## 2. Already used or tested (not new)

| Data | Result |
|---|---|
| Sentinel-2, Landsat, HLS dryness | Dryness is the only input group that matters for the 2-day map (−4.4 points without it) |
| FIRMS / VIIRS / MODIS fire points | The core inputs. In Earth Engine, LANCE VIIRS runs about 2 days behind public FIRMS, and NOAA-21 is missing |
| ERA5-Land, NASA POWER, FWI, KBDI, WeatherNext | Add 2 points or less at 2 days. KBDI saturates by mid-March |
| MODIS NDVI/NDMI and LST (8–16 day) | 27.8 vs 27.5, so no gain |
| AlphaEarth 64-d embeddings | Made the score worse (26.4 vs 27.5) |
| ESA WorldCover, SRTM terrain, GHSL population, OSM proximity | No gain |
| Prithvi on HLS | Copies S2 dryness |
| Sentinel-1 radar | Can't date scars (12-day revisit) |
| MCD64A1 burned area 2001–16 | Pulled to the PC. The long-run prior has not been tested |
| Meta/WRI 1 m canopy height | Used in the fuel map (`fuel-map/ratapani/scripts/chm.py`) |
| Google Open Buildings v3 | Used for the grass layer (distance to buildings) |

## 3. The one check I ran: ECOSTRESS passes over Ratapani

ECOSTRESS rides on the Space Station, so it passes at a different hour each time. I asked NASA's public index for every ECOSTRESS 70 m temperature tile over Ratapani in the fire season (15 Feb–15 Jun, 2019–2026). I then compared the pass times with our VIIRS fire points.

| | Count |
|---|---|
| Passes over Ratapani, 8 seasons | 369 (about 46 per season) |
| Passes with a VIIRS fire in Ratapani within ±3 h | 126 |
| …of those, at hours when VIIRS does not look | **88 (about 11 per season; 4–19 per season)** |
| Hours of those 88 (IST) | Mostly 10:00–12:00 and 15:00–17:00, a few at 22:00–05:00 |

What this does **not** show yet: whether the tile was cloud-free, whether it covered the fire's exact spot, and whether a 70 m hot patch is visible. The temperature product may mark very hot fire pixels as bad data. All of that needs a look in Earth Engine on the PC.

How to test it: on the 88 passes, look for hot 70 m patches within 1 km of VIIRS points from the same day. If they are there, add them as extra "dots" and rescore the honest distance map on the mid-fire photos. The baseline is AUC 0.84 from VIIRS dots alone (`research/spread-review/HONEST_TESTS.md`). Count it a gain only if it beats 0.84.

Files: `ecostress_passes_ratapani.csv` (one row per pass), `ecostress_cmr_query.py`, `ecostress_match_viirs.py`.

## 4. New candidates, with a test for each

Resolution and dates are from the catalogue. "Rating" is my guess before testing.

| Data (Earth Engine ID) | Pixel, dates | What it could add | For | Test against | Rating |
|---|---|---|---|---|---|
| ECOSTRESS LST `NASA/ECOSTRESS/L2T_LSTE/V2` | 70 m, Jul 2018–now, changing hours | Fire looks at hours VIIRS misses | Spread, big fires | Honest distance map, photo AUC 0.84 | **Best new lead** |
| GEDI L2B `LARSE/GEDI/GEDI02_B_002_MONTHLY` (also L2A, L4A) | 25 m laser shots, Mar 2019–Jul 2025, sparse tracks | Vegetation density in the low layer (0–5 m), under the canopy | Fuel map | Within the same canopy class, does the map's ranking match GEDI's low-layer density? The S2 SWIR check gave about 0 | Medium |
| Planet NICFI `projects/planet-nicfi/assets/basemaps/asia` | 4.8 m, monthly; the catalogue lists mosaics up to Sep 2026 (the FSI note said monthly only to Jan 2025, so check which months exist) | Small scars missed by S2; sharper scar edges | Burn scars | On alerts S2 calls `none_visible`, how many show a scar? Today 81% of "yes" scars are real | Medium; needs sign-up |
| Open Buildings Temporal `GOOGLE/Research/open-buildings-temporal/v1` | 4 m, yearly 2016–2023 | Village size and growth, matched to the year | 2-day map, weak divisions only | Leave-one-division-out on Shajapur, Rajgarh and Mandsaur against today's division model | Low–medium |
| Dynamic World `GOOGLE/DYNAMICWORLD/V1` | 10 m, every S2 scene, 2015–now | Harvest date at the forest edge (crops turning to bare ground). Grass probability for the grass layer | Start places; fuel grass layer | Do starts within 500 m of farmland rise in the weeks after harvest, compared with the calendar alone? | Low–medium |
| MERIT Hydro `MERIT/Hydro/v1_0_1`; JRC surface water `JRC/GSW1_4/*` | 90 m and 30 m | Small streams and dry-season water that OSM misses | Spread barriers | Fire stop rate at MERIT streams vs OSM streams (now 20–72%) | Low–medium |
| Heat load (CHILI) `CSP/ERGo/1_0/Global/ALOS_CHILI` | 90 m, static | Sun-facing slopes that dry earlier | Fuel; start places | Burn frequency vs CHILI within the same canopy class | Low; very cheap |
| Cloud Score+ `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | 10 m, per S2 scene | Better cloud masks, so more usable looks | Scars, dryness | Share of usable S2 looks gained over the current masks | Low (plumbing) |
| Daily LST: MODIS `MODIS/061/MOD11A1`, `MYD11A1`; VIIRS night `NASA/VIIRS/002/VNP21A1N` | 1 km, daily, 2000/2012–now | Day-to-day heat and dryness | 2-day map | Lean ensemble on SCORING.md v2 | Low (8-day LST already gave nothing) |
| Burned area: VIIRS `NASA/VIIRS/002/VNP64A1`, FireCCI51 `ESA/CCI/FireCCI/5_1`, GlobFire `JRC/GWIS/GlobFire/v2/DailyPerimeters` | 500 m / 250 m; 2012–Aug 2026 / 2001–20 / 2001–20 | Older burn history; daily growth outlines of large fires | Long-run prior; big-fires comparison | Past-burn frequency alone (24%) | Low; too coarse for small fires |

## 5. In the catalogue but not worth time

- **Geostationary fire data (GOES 16–19):** the catalogue has it only over the Americas. It has no INSAT or Himawari. There is no 15-minute fire data for India in Earth Engine.
- **Sentinel-5P smoke and CO** (about 5 km), **SMAP soil moisture** (9 km), **GCOM-C LST** (4.6 km): too coarse for beats.
- **ESA CCI biomass (100 m), PALSAR-2 radar, Hansen tree-cover loss:** they measure trees, not litter. Our litter fires seldom kill the canopy.
- **Black Marble night lights `NASA/VIIRS/002/VNP46A2`:** fires make the lights noisy. The better night-fire product (FILDA-2) is not in Earth Engine.

## 6. Correction to an earlier note

`ratapani/fsi/scouting/open_datasets.md` (B10) says ECOSTRESS is "not in the main GEE catalog". It is now: `NASA/ECOSTRESS/L2T_LSTE/V2`, Jul 2018 to 15 Oct 2026.
