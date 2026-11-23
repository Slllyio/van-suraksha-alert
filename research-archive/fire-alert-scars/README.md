# Burn scar for every fire alert (Ratapani, 2017-2026)

Built 14 Oct 2026 in the "Burn scar for every fire alert" thread. For each satellite fire alert (the MODIS and VIIRS detections FSI forwards), the burn scar it left, from free Sentinel-2 L2A + Landsat 8/9 (Microsoft Planetary Computer). Research output, not an operational product.

## Main files

| File | What it is |
|---|---|
| `alert_scar_lookup.csv` | **One row per alert inside Ratapani** (15,048 alerts, Jan 2017 to May 2026). Join on `(latitude, longitude, acq_date, acq_time, sensor)` or on `event_id`. Columns below. |
| `event_scars.geojson` | One scar polygon (EPSG:4326) per fire event with a scar. |
| `out/event_scars.csv` | Per event results (same fields, polygon as GeoJSON text). |
| `out/alert_scars.csv`, `out/scars.geojson` | The cheaper link to the research thread's season scar maps (scars >= 2 ha), kept for comparison (`map_*` columns in the lookup). |
| `alerts/` | Raw FIRMS points in the Ratapani bbox + 2 km. 2017-2025 from FIRMS yearly India files (MODIS, VIIRS S-NPP, NOAA-20). `*_2026.csv` from Earth Engine LANCE rasters (Dec 2025 - Jun 2026, ~95% of FIRMS counts, no scan/track); their Dec 2025 rows are skipped because the 2025 files hold them. NOAA-21 has no yearly files. |
| `live/` | Ledger written by `scripts/live.py` for new alerts. |

An **event** is all alerts on the same day within 1 km of each other (6,152 events). The scar is found once per event, seeded from a VIIRS point when there is one.

### Lookup columns

- `scar_found`: `yes`, `faint`, `none_visible` or `unknown`. **`none_visible` does not mean false alert**: the fire may be under 0.5 ha, under a green canopy, or burned only litter. Field systems confirm fires of ~0.15 ha that no 20 m sensor can see. `unknown` = not yet run, or no clear image.
- `scar_status`: `scar`, `scar_faint`, `no_scar_seen`, `waiting` (no clear image after the alert yet), `no_pre`, `no_clear_image`, `error`.
- `scar_ha`: connected burned area (ha) seen between `pre_date` and `post_date`, within a 3 km x 3 km chip around the alert. It can include neighbouring fires from the same image gap. `touches_chip_edge` = the scar runs beyond the chip, so the area is a lower bound.
- `scar_ha_core`: area that passed the strict first-pass test (2026 events only).
- `severity`: from the median relative NBR drop, USGS-style bands (low < 0.27 <= moderate < 0.44 <= high). 99% are low, matching FSI's > 99% low-severity burnt area for Raisen/Sehore 2023-24.
- `link_conf`: `high` (scar within 100 m of the alert point), `medium` (100-200 m), `low` (faint scar).
- `pre_date`, `post_date`, `gap_days`: the image pair (median gap 5 days). The fire burned in (pre_date, post_date]; the alert gives the day. `check_date`: later image confirming the drop held; `persist_checked` False = provisional.
- `beat_uid`, `division`, `range`, `beat`: MP Forest Department beat of the alert point.

## Method (`scripts/alert_scar.py`)

1. Read a 3 km chip at 20 m around the alert for every Sentinel-2 and Landsat 8/9 scene from 30 days before to 40 days after. Clouds masked with a buffer; Sentinel-2 scaled to Landsat, -1000 offset handled for baseline >= 04.00.
2. `pre` = last look on or before the alert day with >= 70% of the alert area clear; `post` = first such look after; `check` = a later look within 25 days.
3. Pass 1: a pixel is burned when its NBR drop beats the chip's median drop by >= 0.10 (0.15 in January), NIR darkens relative to the chip, and the drop still holds at `check`. Keep connected patches >= 0.5 ha within 200 m of a VIIRS alert (600 m for MODIS).
4. Pass 2 (after FireCCI's two-phase design): learn this fire's own drop from the pass-1 core and grow into connected pixels dropping at least half as much (min 0.05).
5. If pass 1 finds nothing, accept a fainter persistent drop (>= 0.07, patch >= 1 ha) as `scar_faint`.

## How good is it

Tested on 300 historic alerts and 200 control points (same dates, moved 3 km into forest with no alert within 1.5 km / 15 days). Script `scripts/eval_chip.py`, results `out/eval_chip_v2.csv`.

| | scar | faint | none |
|---|---|---|---|
| Alerts the season maps also link to a scar | 95.5% | 3.0% | 1.5% |
| Alerts the season maps had as no scar | 69.3% | 15.1% | 15.7% |
| Control points (no alert) | 5.0% | 1.5% | 93.5% |

So about 93% of found scars are real rather than chance (controls sit in quieter forest, so this is a best case). The scar areas of the 13 control "scars" were mostly > 3 ha after growth: growth inflates false scars as well as true ones.

Full run, 2017-2025 alerts: 89% yes, 5% faint, 5% none visible. January is weakest (64% yes, 26% faint: leaf fall and haze), March-May 90-93% yes. Sensors agree (MODIS 91%, S-NPP 89%, NOAA-20 88%). Event scars: 17 under 1 ha, 202 of 1-3 ha, 591 of 3-10 ha, 4,369 over 10 ha.

The season-map link alone (`match_scars.py`) is much noisier: control points get a scar within 300 m 18% of the time vs 72% for alerts, and beyond 300 m alerts match no more often than controls, so those links were dropped.

**Check against FSI's Large Forest Fire archive** (`ratapani/fsi/fsi_portal/lff_mp.csv`, 2020-2025): of the 235 large fires inside Ratapani, 231 (98%) have one of our scars on the same days inside their box, and 4 have none visible. Where matched (240 LFF in the wider box), our image pair brackets FSI's first detection 93% of the time, and our scars cover a median of 99% of FSI's bounding box. Our scars are wider (median 2.2 km across vs 1.25 km), because a scar takes in all burned ground connected to it within the image gap.

**2026 caveat:** 2026 alerts come from Earth Engine raster centroids, not the true FIRMS points, so they can sit up to ~190 m off. Only 76% get a clear scar (19% none visible) vs 89% in 2017-2025. The FSI-alert run below uses FSI's true points for the same season.

**Not checked:** no ground truth. FSI does not publish its scar polygons, and the field-check thread's guard reports are the first independent check this can get.

## FSI's own 2025-26 alerts

`fsi/fsi_alert_scar_lookup.csv`: one row per alert FSI sent for Obedullahganj, Raisen, Sehore and Bhopal divisions, 1 Nov 2025 to 12 Oct 2026 (3,104 alerts, 1,997 events, from the open FSI Fire Point Search exports in `ratapani/fsi/fsi_portal/`). Keyed by `fsi_alert_id` and FSI's own `acq_date`, `acq_time`, `latitude`, `longitude`, with FSI's Division / Range / Beat / Compartment_No, plus the same scar columns as the main lookup. Event results: `fsi/fsi_alert_events.csv`. Script: `scripts/fsi_alerts.py`.

Jan-Jun 2026: 81% of FSI alerts have a clear scar, 4% faint, 15% none visible. By division: Obedullahganj (Ratapani) 90%, Bhopal 77%, Sehore 78%, Raisen 74%; the other divisions have more cropland and open scrub. January is again weakest (19 clear of 89). Using FSI's true points brings Ratapani 2026 back to the 2017-2025 level, which supports the centroid-offset explanation for the Earth Engine 2026 points.

**Position fix (14 Oct, late):** FSI's VIIRS feed was S-NPP from Nov 2025 to 26 Apr 2026, and those FSI positions sit a median 250 m from NASA's (field-alerts thread). The 231 non-MODIS events from those months that had no scar at 200 m were re-run with a 400 m radius (`scripts/fsi_rematch.py`; rows carry `radius_m` = 400): 60 gained a scar and 14 a faint one. That changed 133 alert rows (112 none_visible to yes, 21 to faint). A wider radius also catches more chance scars, so treat these gains as medium confidence.

## New alerts

`python scripts/live.py [aoi.geojson] [outdir]` pulls the FIRMS 7-day South Asia feeds (MODIS, S-NPP, NOAA-20, NOAA-21; public, no key), groups alerts into events, finds each scar, tags the beat, and re-checks events still `waiting` or provisional on later runs (gives up after 45 days). Tested 14 Oct 2026: one Ratapani alert on 11 Oct, 9.8 ha scar, provisional. Any AOI works (e.g. all of MP), but run time is ~10-15 s per event.

## Scripts

`get_alerts.sh` (download), `match_scars.py` (season-map link + beats), `alert_scar.py` (per-alert finder), `eval_chip.py` / `eval_rerun.py` (tests), `run_all.py` (all historic events, resumable), `build_lookup.py` (lookup + polygons), `live.py` (new alerts).

## Dating burns to the day (Sentinel-2 / Landsat active fire, 14 Oct)

`scripts/af_scan.py` looks for fire pixels in every Sentinel-2 and Landsat 8/9 scene over Ratapani (Gui 2026 hot-pixel test, Schroeder 2016 for Landsat), 2017-2026: 43,230 pixels on 340 dates. In 2023, 61% of them sit on a scar whose window holds that day, against 0% when the date is moved 30 days. 59% of fire-pixel clusters have no FIRMS alert within 1 km on that day or the next: small fires VIIRS misses.

`scripts/af_link.py` and `scripts/dated_labels.py` date the research thread's first burns (20,007 cell-seasons, 2017-2026): `out/af/dated_first_burns.csv`, `out/af/af_summary.json`.

| Day source | First burns dated |
|---|---|
| VIIRS S-NPP only | 40% |
| + NOAA-20 and MODIS | 54% |
| + Sentinel-2 / Landsat fire pixels | 55% |

Fire pixels date 4.9% of first burns, but only 1.4% that FIRMS could not, because a fire must be burning at the ~10:30 overpass. Where both exist, the fire-pixel day matches the earliest FIRMS day 36% of the time and is within 1 day 83% of the time.

## Improvements tested 15 Oct

**FSI points in the live run.** `live.py` now also reads FSI's open Fire Point Search portal (Madhya Pradesh, last 7 days; needs a browser User-Agent), so FSI-only alerts get a scar. FSI points join a NASA event within 1 km on the same day, else start their own (`sensor` = fsi-viirs / fsi-modis; 400 m radius for FSI S-NPP points before 27 Apr 2026). Test on a box around Obedullahganj, Sehore and Raisen (8-14 Oct): 22 FSI alerts, 18 joined NASA events, 4 formed an FSI-only event. A failed re-check now keeps the previous result (`last_error`), and a provisional scar is kept when a later run finds no new clear image.

**Splitting merged scars** (`scripts/split_scars.py` -> `out/event_scars_split.csv`). Alerts and Sentinel-2/Landsat fire pixels are chained into fires (within 1.5 km and 1 day, transitively); each scar pixel goes to the nearest seed burning in the image gap, and an event keeps the pixels of its own fire. 19% of scars lose more than 10% of their area; median scar 50 -> 43 ha. So most of our scars' width is the fire itself (multi-day runs), not neighbouring fires: FSI's large-fire boxes span only the detection points. Against those boxes (`scripts/eval_split_lff.py`, 216 fires) the split changes little (box covered 45 -> 44%, ground more than 500 m outside the box 3.6 -> 2.8%). Not yet checked against independent truth. Fuel thread (fuel-map/ratapani/timing/) found VIIRS points lag the true edge by ~380 m and that the full pixel footprint fits better; a footprint-based split is a possible refinement.

**High-res check (Esri Wayback, 0.3-0.5 m)** (`wayback/`: footprints.py, match.py, sample.py, render.py, measure.py; chips in `wayback/chips/`, answer key `wayback/key.csv`, eye notes `wayback/eye.csv`). 511 of our fires have a Wayback image 1-40 days after the fire (273 of them in 2025). Blind sample: 231 real outlines plus 41 decoys (the same outline moved 3 km to forest with no alert within 1.5 km / 30 days, on the same image). Measure: is the ground inside the outline darker than a 150 m ring outside it (fresh teak-litter burns show dark grey-blue on this imagery)?

| Days from fire to image | real vs decoy AUC | "yes" scars clearly darker* | "faint" scars clearly darker* | decoys clearly darker* |
|---|---|---|---|---|
| 1-3 | 0.91 | 81% (37) | - (1) | 0% (6) |
| 4-7 | 0.90 | 76% (55) | 86% (7) | 8% (13) |
| 8-15 | 0.78 | 76% (54) | 12% (8) | 23% (13) |
| 16-40 | 0.84 | 58% (36) | 33% (12) | 0% (9) |

*darker than 90% of decoys. Burns under canopy can be real and still not show, so these are lower bounds. Eye check of 21 fresh chips before unblinding: both decoys read as unburned; of 19 real outlines, 13 sit on a visible burn, 3 sit on a burn that runs well beyond the outline (edges under-mapped, as the spread thread found), 1 faint outline is ~200 m off the burn, 2 unclear. Four "none visible" alerts: 2 show no burn, 2 unclear. Bottom line: a "yes" scar is on real burned ground about 4 times in 5; the main error is a scar drawn smaller than the burn; "faint" scars are only sometimes real and should read as "possible".

**Growing scars to the later image** (`alert_scar.py` `grow_to_check`, now on by default; test `wayback/grow_eval.py`). The fire is often still spreading at `post_date`, so the scar is now also grown into connected ground that has dropped by the later check look (same threshold as pass 2). On 182 Wayback-checked scars the median area goes 62 -> 84 ha. The added ground is darker than the surroundings on the high-res image 86% of the time, against 42% for ground next to the scar that was not added: it is mostly real burn. `scar_ha_post` keeps the area at the first image. Historic rerun done (`scripts/regrow.py` -> `out/event_scars_grown.csv`): median growth x1.10, 20% grow by more than half. 6% (341 scars) would grow more than 3x, mostly a small scar joining a large later burn, probably another fire; those keep their first-image scar and carry `grew_into_large_burn`. `out/event_scars.csv`, `event_scars.geojson` and the lookup now use the grown scars (old file: `out/event_scars_pre_grow.csv`).

**January baseline: no gain** (`scripts/jan_baseline.py` -> `out/jan_baseline.csv`). For 124 January alerts and 63 control points, each pixel's drop was compared with its own drop over the same dates in 3-4 other years. Share with a scar (core test, 0.5 ha, touching the 200 m disk):

| | chip-relative 0.15 (current Jan rule) | chip-relative 0.10 | baseline 0.15 | baseline 0.10 | baseline 0.07 |
|---|---|---|---|---|---|
| alerts now "yes" | 93% | 95% | 90% | 95% | 95% |
| alerts now "faint" | 2% | 69% | 5% | 69% | 93% |
| alerts now "none visible" | 6% | 16% | 9% | 16% | 38% |
| control points | 4.8% | 12.7% | 4.8% | 14.3% | 15.9% |

The per-pixel baseline separates alerts from controls no better than the chip-relative drop, so leaf-fall patchiness is not what weakens January. January burns are simply lighter (thin early litter, controlled burns on fire lines), and any lower threshold lets in as many chance drops as real scars. The 0.15 January threshold stays; "faint" remains the honest label.

## Next ideas (from the scouting notes in `ratapani/fsi/scouting/`)

Sentinel-2 / Landsat active-fire rules (Gui 2026, Schroeder 2016) to date scars to the day; B12 < 0.07 shadow mask; dMIRBI / dNBR2 tests; a 5-year NBR baseline against January leaf fall.
