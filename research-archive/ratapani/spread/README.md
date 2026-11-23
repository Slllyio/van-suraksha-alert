# Fire spread model for Ratapani, in the spirit of C-DAC's WRF-SFIRE forecasts

Thread "Fire spread model like C-DAC". Research only: no officer-facing outputs. Everything here lives in
`/mnt/project-files/ratapani/spread/` (scripts, results, example maps); nothing has been pushed to a repository.

**One-paragraph summary.** C-DAC runs WRF-SFIRE (a Rothermel surface-fire model coupled to a weather model) at 40 m
for 24-48 h from a satellite fire alert. We built the same kind of model for Ratapani on a 20 m grid (Rothermel spread,
elliptical wind/slope shaping, hourly ERA5-Land weather and dead-fuel moisture, the fuel-map thread's Rothermel-ready
fuel layers, roads as barriers) and tested it on every VIIRS-detected fire of 2017-2024 that left a mapped burn scar
(1,398 fires). The honest result: on Ratapani the physics forecast matches the burnt outline about as well as a plain
"grow a circle from the detection" baseline (Sorensen overlap 0.34 vs 0.35 at equal area), because the fires here are
slow litter fires whose shape is set by where the fuel is and where roads and earlier burns stop it, not by wind. What a
C-DAC-style model does add is a calibrated burnt-area size over time and a map that shows the hourly isochrones against
barriers, which is what C-DAC's own examples are really used for. The forecasts and their reality for six Ratapani fires
are in `examples/` in the same layout C-DAC uses (forecast outline on the post-fire Sentinel-2 image).

## 1. What C-DAC actually does (paper + deck), and what we copied

| | C-DAC (Kale et al. 2024; FSI deck, Sikkim) | Ours (Ratapani) |
|---|---|---|
| Fire model | WRF-SFIRE: Rothermel ROS, level-set front | Rothermel ROS, level-set-equivalent minimum-travel-time front (16-neighbour, time-dependent) |
| Fire grid | 40 m (1:20 of the 800 m WRF nest) | 20 m |
| Weather | WRF 7.2/2.4/0.8 km nests from GFS 0.25 deg, coupled | ERA5-Land hourly at the nearest of 33 points (uniform over Ratapani, see research thread); no coupling |
| Terrain | ALOS 12.5 m DEM | Copernicus GLO-30 DEM |
| Fuel | 1:10,000 LULC classes mapped to 4 Anderson models; loads from 23 field plots (grass 0.16 kg/m2, scrub 0.23-0.24, forest 0.27 at 6 cm depth) | Fuel-map thread's per-pixel Rothermel layers (1-h/10-h load, depth, extinction moisture, SAV) from the FSI strata method + Sentinel-2, per season; teak litter as TL6/FBFM9-type bed |
| Dead fuel moisture | WRF-SFIRE's own moisture model from WRF RH/T | 1/10/100-h time lags to Simard EMC with sun-lit fuel correction, hourly from ERA5 (afternoon 1-h moisture 2-4%, night 6-8%) |
| Wind | WRF 10 m wind with windrf 0.36-0.44 | Tested with ERA5 wind (waf 0.3) and without; final runs without (section 4) |
| Ignition | the FIRMS/VIIRS alert point(s) | all first-pass VIIRS S-NPP detections, snapped to burnable pixels (and to the mapped scar where available) |
| Barriers | roads/habitation added by hand per run ("fire could not cross beyond this line") | Microsoft road detections (3,763 km in the box) as non-fuel, strict no-jump rule |
| Horizon | 24-48 h hourly isochrones | same |
| Restarts | planned: every satellite pass re-seeds the run (slide 24, SUTRADHAR on PARAM Rudra) | tested: free run vs restart at every VIIRS pass |
| Run time | 2 h 11 min on 240 cores (paper); 17 min on 16 nodes (deck) for 24 h | 1-2 s per fire on one core |
| Validation | one fire (Maltim, 27 Jan 2023): forecast 1.72 km2 vs 1.07 km2 burnt (+61%), no overlap score; Sikkim deck cases unscored | 1,398 scarred fires, Sorensen overlap, area ratio, later-pass hits, restart test |

### What C-DAC's examples really show
Full notes: `/mnt/project-files/ratapani/fsi/cdac_slides/README.md` and `cdac_spread_details.md` (FSI-data thread).
- **Maltim, North Sikkim, 27 Jan 2023 (paper).** Scrub and grass on steep slopes. Forecast 1.72 km2, burnt 1.07 km2
  (+61%). The only quantitative case C-DAC has published; no shape score.
- **West Sikkim, 13 Mar 2024, 48 h run (deck).** Forecast envelope about 4 x 2.5 km from one FIRMS alert. On the 19 Mar
  Sentinel-2 image only the eastern part near the ignition is burnt; the western 3 km2 is green. C-DAC credits the gap
  to Forest Department intervention; no control run or fire line is shown. Read plainly, forecast 2-3x the burnt area.
- **Omchung RF, 12 Mar 2024, 24 h run (deck).** Three isochrone bands; "saved 0.54 km2" behind a hill road where
  photos show the FD hose line. A 15 h map was sent by WhatsApp before the formal run, and "we had some habitation layer
  so used it": non-fuel is added by hand, and re-runs happen during the day.
- **Forecast holes sit on dense forest.** With FBFM 8 (0.27 kg/m2, 6 cm) closed forest barely burns in their setup, so
  the fire runs through scrub and grass. Copied to Ratapani, where closed teak litter is the main fuel, this forecasts
  almost no spread (section 4, "C-DAC Sikkim fuels" and "fuel v2 compact").

So the transferable lessons are: (1) barriers (roads, streams, villages, fire lines) in the fuel raster as non-fuel;
(2) hourly isochrones drawn over the latest Sentinel-2 image so the gap between forecast and burnt area can be read;
(3) restart the run from every satellite pass; (4) their fuel numbers are Himalayan grass/scrub numbers and do not
transfer. All four are implemented or tested below.

## 2. How our model works (`scripts/`)

- `prep_grid.py`: 20 m grid, EPSG:32643, 1,874 x 3,972 pixels (37 x 79 km box around Ratapani): elevation, slope,
  upslope azimuth (GLO-30), ESA WorldCover class, and the burn-label rasters per season (research thread) for
  "already burnt this season" and for scoring.
- `events.py`: VIIRS S-NPP detections 2017-2024 (Jan-Jun, not low confidence) linked into events within 1.2 km and 30 h;
  1,862 events, 4,517 detections, 365 events with 2 or more passes. Passes are 2-h bins (day ~13:30 IST, night ~01:30 IST).
- The model is a surface-fire model only (no crown fire, no spotting), which matches Akkshay's note that MP teak-forest fires are
  all surface fires in fallen teak leaves; the fuel-map thread's layers describe that teak leaf-litter bed (loose-bed variant
  2.5 kg/m3 for the curled leaves, per-pixel leaf-fall fraction by month from Oct 14 22:13Z).
- `rothermel.py`: Rothermel/Albini surface fire spread with Scott-Burgan and Anderson fuel models and a per-pixel
  variant (`rothermel_px`) that takes the fuel-map thread's layers; Simard EMC and hourly 1/10/100-h dead fuel moisture.
- `engine.py`: 16-neighbour minimum-travel-time front (numba). Each hour has its own rate-of-spread field, elliptical
  length-to-breadth (Anderson) and heading from the wind/slope vector, so the front is the eikonal/level-set solution
  with time-varying speed. `strict=1` forbids jumping a one-pixel non-burnable line (roads).
- `sim.py`: per fire, builds the hourly ROS fields for the window around the detections, applies barriers and the
  already-burnt mask, sets the ignition from first-pass detections, runs the front for 48 h (or to last detection + 12 h),
  and returns arrival-time rasters. Config keys: `fuel` (worldcover classes or `rfuel` = fuel-map layers),
  `rfuel_file`, `wind`, `slope`, `ros_mult`, `waf`, `barriers`, `strict`, `ign_snap`, `cdac_params`, `hours`.
- `score.py` / `runall.sh` / `analyze.py`: scoring of every event against the scar; `restart.py` /
  `analyze_restart.py`: restart-from-every-pass test; `passpairs.py`: direction test between successive passes;
  `hybrid_data.py` / `hybrid_fit.py`: learned correction; `fsi_growth.py`: FSI large-fire archive check;
  `examples.py`: C-DAC-style example maps; `prep_fuel.py`, `prep_rfuel.py`, `prep_barriers.py`: inputs.

## 3. How we judged it

- **Scar footprint**: the season's mapped burn scar (Sentinel-2 + Landsat, research thread) within the fire's window,
  connected to the detections. 1,398 of the 1,862 events have a scar of 1 ha or more (median 23 ha).
- **Shape (Sorensen at scar area)**: the forecast's earliest-arriving pixels, as many as the scar has, against the scar,
  Sorensen = 2|A and S| / (|A| + |S|). The baseline is the same number of nearest pixels around the same ignition
  (a circle grown over burnable ground). Shape only, size removed.
- **Size (area ratio)**: forecast burnt area at last detection + 12 h divided by scar area (median), and the Sorensen of
  that footprint against the scar. 2017-21 and 2022-24 separately because the scar maps differ in sensors.
- **Later passes**: share of the fire's later VIIRS detections that fall inside the forecast front at their time,
  against an equal-area circle.
- **Restarts**: for 2-pass+ fires, hit rate on each next pass from a free run vs a run re-seeded with every detection
  up to the previous pass, with circle and persistence (375 m around the last detections) baselines.
- **Weather is a hindcast.** Every physics run in this README is driven by ERA5-Land reanalysis for the hours the fire
  burned, so its scores are hindcast scores (what the engine does with the weather that happened), not live-forecast
  scores. A live run would use a weather forecast issued at the alert time; section 4n (the audit's fair table) marks
  the physics rows as hindcasts for that reason. The learned models use the weather at the latest pass only, which is
  available at issue time from any analysis product.
- **Ignition is never snapped to the scar in the learned models or the fair table.** The physics calibration of 4b used
  `ign_snap` (the nearest scar pixel within 750 m of the alert point) to separate the fuel question from the alert-point
  offset; the learned footprint (4i), the learned restart (4j) and the fair table (4n) use the alert points and discs
  only, as a live system would. The audit thread (research/spread-audit/) is checking this at code level.
- **Outline versions.** Every polygon score up to Oct 16 is against v1. Scar outlines v2 (2026-10-16, `reference/v2_2026-10-16/`) redraws
  the 38% of outlines that touched the 3 km chip edge on 6-12 km chips. On this thread's 1,686 S-NPP-matched fires v2 keeps the same
  fires; 221 grow by more than 1.2x (median v2 area 447 ha for those), the median fire is unchanged. Inside this thread's scoring window
  (2.6 km around the detections) sits 94% of all v2 burned area and 88% for the grown fires; 41 fires lose more than a tenth of their v2
  outline to the window, which every method shares. The fair table and the 2025-26 test are rescored on v2 (queue 32); tables say which
  version they use. The 200 m alert-circle rule is unchanged in v2, so alert-distance methods keep their head start.
- **Outline truth = scar outlines v1 (2026-10-15), error bands per its USE_AND_LIMITS.md.** The scar thread froze its grown outlines on
  Oct 15 (`fire-alert-scars/reference/v1_2026-10-15/`); the file this thread rasterised (`event_scars.geojson`) has the same sha256 as
  the frozen `firms_event_scars.geojson` (29254be0...), so every polygon score in 4i-4s is against v1. Its blind check on sub-metre
  imagery (102 readable fires) puts the false area along the edge at a median 9% of the outline (IQR 6-13%) and burned ground missed
  within 250 m at a median 22% (IQR 0-59%; 19% large, 11% medium, 88% for fires under ~20 ha). So a forecast that drew the true burn
  exactly would still score only about 0.85-0.9 Sorensen against v1 at a fire's own area, and the small fires' scores are the least
  trustworthy. The outlines' dates (1-3 weeks wide) are never used for timing here; timing comes from the VIIRS passes.

## 4. Results (1,398 scarred fires unless stated; "circle" = equal-area distance baseline)

**Audit corrections (Oct 15, from the independent check in research/spread-audit/README.md; applied here, nothing deleted).**
1. *Scar-snapped ignition in the physics (4a-4h).* Every physics run in 4a-4h, the final model included, started from the alert point
   snapped to the mapped scar (`ign_snap`), which a forecast could not do. The audit's rerun on 527 fires: snapped 0.351 vs circle 0.347;
   honest (100 m disc at the alert point) 0.275 vs 0.268. The verdict "physics ties the circle on shape" stands; both numbers were ~0.08 too
   high, and the size fit moves (end area / scar 1.9x honest against 1.0x snapped at last pass + 12 h). The learned models (4i-4l), the
   barrier runs (4m), the fair table (4n) and the honest ROS refit (4n) never snap. Read every physics Sorensen in 4a-4h as a calibration
   score, not a forecast score.
2. *Earlier same-season burns were not final at forecast time.* The burn-label rasters need a drop that persists 25 days, so scars dated
   within 25 days before a fire were not knowable on the fire day (median 68% of nearby earlier-burn pixels). The audit's honest rerun
   lowers the learned footprint from 0.516 to 0.498 (honest circle 0.453; lead 0.054 -> 0.045) and leaves the learned restart unchanged
   (85.8 vs 85.9%). The rule is now "burn final 25 days after its window end" in sim.py, footprint.py and foot_restart.py, and the
   polygon-truth models of 4i-4j are retrained with it (Oct 15, 12:50Z): the learned footprint moves from 0.517 to 0.502 at the polygon's
   area (circle 0.463 -> 0.454, physics 0.454 -> 0.442; later-pass hits 53.7 vs 36.7%; better than the circle in 72.5% of fires and in
   every season), the restart's next-pass hits from 85.9 to 85.7% (persistence 72.2; 3 h+ leads 78.3 vs 51.8%; new ground 75.9 vs 51.6%)
   and its end footprint from 0.525 to 0.515 (distance 0.462, persistence 0.434). The honest models and scores are the ones in
   `results/` now (`foot_models_grown/`, `foot_score_grown2_*`, `lrg_models/`, `lrg_score_*`); the leaky ones are archived under
   `data/leaky/`. 4j and 4k carry both sets of figures; 4n and 4s use only honest inputs.
3. *Fires were grouped with hindsight* (events_multi.py links detections over the fire's life): 7% of restart steps have a "known" set that
   only later detections tied together, and 8% of next-pass targets lie more than 1.2 km from everything known. Fair across methods, but a
   live version needs incremental attribution of each new detection to a fire.
4. *What the restart score measures.* The lead is the time to the next pass that DETECTED the fire, not the next orbit (85% of the
   steps with leads over 18 h had a pass in between that saw nothing); the score counts caught detections among fires that were seen again
   and never counts false alarms. Almost half the steps (744 of 1,527) are the 50-minute S-NPP to NOAA-20 gap, where both methods score
   ~91%; the honest headline is the 3 h+ figure, 79.0 vs 51.8% (4j), quoted next to 86.3 vs 72.4.
5. *No forward test yet:* everything is leave-one-season-out over 2017-24, so later seasons train earlier ones. A frozen 2017-24 model
   scored once on 2025 and 2026 is the next step: the 2025-26 events, outlines, fuel and dryness layers are built and the run is queued
   (section 4s).
6. *A fairer no-skill baseline:* the same area around the latest pass only scores 74.1% (persistence 72.2); the learned restart still leads
   it by 11.7 points (CI 10.3-13.1). Added to the 4j table.
7. *Not reproduced:* the 4b sentence "later passes inside the front 26.8% vs 24.9%"; analyze.py on the final model's results gives 24.3 vs
   22.8% pooled (31.8 vs 31.5 per-fire mean). The sentence is corrected below and the origin of the old figure could not be found.

### 4a. Ingredients, on WorldCover fuels (TL6-type litter under trees, GR2 grass, GS2 shrub)
| Run | Sorensen shape, physics vs circle | 24 h / 48 h forecast area (median; scar 23 ha) | Later passes inside front vs circle |
|---|---|---|---|
| wind + slope + per-class fuel, raw ignition | 0.260 vs 0.271 | 219 / 717 ha | 46 vs 47% |
| + ignition snapped to burnable/scar pixels | 0.312 vs 0.345 | 164 / 612 ha | 39 vs 41% |
| no wind | 0.340 vs 0.345 | 62 / 231 ha | 23 vs 23% |
| no slope (wind on) | 0.306 vs 0.345 | 170 / 636 ha | 39 vs 42% |
| uniform fuel (TL6 everywhere) | 0.329 vs 0.345 | 44 / 157 ha | 19 vs 20% |
| flat: no wind, no slope, uniform fuel | 0.347 vs 0.345 (tie in 37%) | 36 / 129 ha | 18 vs 18% |

Wind makes the shape worse in every comparison; removing it is the single largest gain. The physics front never beats
the circle on shape by more than noise; the "later passes" column is equal to the circle in every run (a circle of the
same area catches as many later detections as the physics front).

### 4b. Fuel calibration (no wind, snapped ignition, fuel-map thread's layers)
| Fuel | Shape vs circle | Area ratio to scar at last pass + 12 h (2017-21 / 2022-24) | Sorensen of that footprint |
|---|---|---|---|
| C-DAC Sikkim class values (grass/scrub/forest from Kale 2024 Table 2) | 0.293 vs 0.345 | 12.3 / 16.5 | 0.16 / 0.13 |
| Fuel-map v2, compact bed, with ERA5 wind | 0.298 vs 0.345 | 0.21 / 0.37 | 0.16 / 0.18 |
| Fuel-map v2, compact bed, no wind | 0.285 vs 0.345 | 0.11 / 0.18 | 0.12 / 0.14 |
| Fuel-map v2, loose bed (bulk density 2.5 kg/m3) | 0.327 vs 0.345 | 0.29 / 0.48 | 0.20 / 0.21 |
| Fuel-map v2, compact bed, ROS x3 (the earlier calibrated model) | 0.339 vs 0.345 | 0.85 / 1.36 | 0.27 / 0.28 |
| + strict road-crossing rule, no barriers | 0.340 vs 0.345 | 0.83 / 1.35 | 0.27 / 0.28 |
| + roads as barriers (`m3_barrier`) | 0.342 vs 0.345 | 0.83 / 1.34 | 0.27 / 0.28 |
| same, but per-pixel leaf-fall fraction (fuel thread's 10 m layer, band of the previous month) instead of the fixed month factors | 0.334 vs 0.345 | 0.52 / 0.89 | 0.24 / 0.25 |
| Loose bed + per-pixel leaf fall, ROS x1 | 0.311 vs 0.345 | 0.18 / 0.28 | 0.16 / 0.18 |
| Loose bed + per-pixel leaf fall, ROS x1.5 | 0.335 vs 0.345 | 0.37 / 0.59 | 0.22 / 0.23 |
| Loose bed + leaf fall interpolated to the fire's date, ROS x1 | 0.324 vs 0.345 | 0.25 / 0.40 | 0.18 / 0.20 |
| Loose bed + leaf fall interpolated, ROS x1.5 | 0.342 vs 0.345 | 0.51 / 0.85 | 0.24 / 0.25 |
| Teak-mix bed (fuel thread, Oct 14 23:16Z: bulk density 2.5 kg/m3 where the Sentinel-2 teak classifier says teak, 6 kg/m3 in other dry deciduous), same settings as the loose-bed run | 0.312 vs 0.345 | 0.20 / 0.31 | 0.16 / 0.18 |
| Teak-mix bed + leaf fall interpolated, ROS x1.5 | 0.332 vs 0.345 | 0.35 / 0.60 | 0.21 / 0.23 |
| **Loose bed + leaf fall interpolated, ROS x2, roads as barriers (`loose_lfi_m2`, the final model)** | **0.348 vs 0.345** (better in 52%) | **0.84 / 1.39** | **0.275 / 0.274** |

Engine check (after a query from the fuel-map thread): with the scalar hourly moistures `sim.py` passes, the per-pixel
Rothermel reproduces the textbook single-class values to the decimal (loose bed 0.15 kg/m2 at 2.5 kg/m3, Mx 0.25:
19.5 m/h at 2.5% moisture, 14.8 at 5%, 11.8 at 8%, 9.8 at 12%; TL6 at 6/7/8% 12.1 m/h = 0.60 ch/h; FM1 84 m/h; FM8
4.8 m/h), so the x3 below is a fuel-bed calibration, not a units error.

The fuel thread's per-pixel leaf-fall layer (Oct 14 22:13Z; share of the leaf-off drop done by month end, median 38 / 51 /
71 / 93 / 100% for Dec-Apr) replaces the fixed Jan 0.5 / Feb 0.7 / Mar 0.88 factors. Used as the previous month's band it
gives less litter than the fixed factors (forecast size falls by a third) and no better outline (0.334 vs 0.342): where
the leaves have fallen varies from pixel to pixel, but the fires do not follow it (section 4f: the litter load on the
side a fire runs is only 4% heavier than behind it).

Reading: C-DAC's fuel numbers over-forecast Ratapani by more than 10x; the fuel-map's compact litter bed under-forecasts
by 5-9x; the loose bed (the fuel thread's physically argued variant for curled teak leaves) closes about half the gap;
the leaf-fall layer interpolated to the fire's date adds a little; the rest, x2 on rate of spread, is unexplained and is
applied as a fit. Making the bed tighter where the forest is not teak (the teak-mix variant) only slows the forecast there and lowers
the outline score (0.312 against 0.327 for the loose bed everywhere; 0.332 against 0.342 with leaf fall and x1.5), so
either the mixed-forest litter is as loose as teak's or the fires are not where the classifier draws the line.
The final model is therefore: loose teak-litter bed, per-pixel leaf fall by date, no wind, ignition
snapped to fuel, roads as barriers, ROS x2. It forecasts the same size as the earlier compact-bed x3 model (median area
ratio 0.84 / 1.39) with a smaller fitted factor, and it is the first variant whose outline edges past the circle
(0.348 vs 0.345; later passes inside the front 24.3% vs 22.8% for the circle, pooled over 304 fires; an earlier draft said 26.8 vs 24.9, which the audit could not reproduce). Both numbers use the scar-snapped start (audit correction 1): with an honest 100 m disc at the alert point the audit finds 0.275 vs 0.268 on 527 fires, the same tie. Dead fuel moisture is not the
missing factor: our hourly litter moisture is already 2-4% in the afternoon (Rothermel ROS on the loose bed: 5.7 m/h at
2.5%, 4.7 at 5%, 3.7 at 8%). With several ignitions inside one detection window the fitted factor is an upper bound.
The calibrated model forecasts the right burnt-area size on average (median ratio 0.85-1.36) and the right order of
24 h growth (56 ha from a median 23 ha final scar), which is what C-DAC's one published case also reports (+61%).

**The fuel thread's per-class loads (Oct 15, `prep_grass.py`, `event_classes.py`).** The fuel thread inverted the final
model's forecasts against the scars by land-cover class and found the loose bed about right in closed teak and other
deciduous forest but 2-4x too light on grass, scrub and sparse ground (canopy under 10%: 9.8% of the vegetated pixels).
Two variants were run on all 1,398 fires: its "keep the load, lower the fit" version (ROS x1.4 with the grass/scrub load
x2.6) and the final model with the grass/scrub load x3. Note first that in this engine the rate of spread is linear in
the fuel load (checked: ROS x2 on the 1.5 t/ha loose bed and a 3.0 t/ha loose bed give identical runs), so the "x2
unexplained" of the final model is from here on stated as fuel: a loose teak-litter bed of about 3 t/ha, which is what
the fuel thread's pass-to-pass front speeds (37 m/h) and the central-Indian floor-fuel literature (2-3.5 t/ha) support.

| Fuel | Shape vs circle | Area ratio to scar at last pass + 12 h (2017-21 / 2022-24) | Sorensen of that footprint |
|---|---|---|---|
| Final model restated: 3.0 t/ha loose bed everywhere | 0.348 vs 0.345 (52%) | 0.84 / 1.39 | 0.275 / 0.274 |
| ROS x1.4 (2.1 t/ha) + grass/scrub load x2.6 | 0.340 vs 0.345 (47%) | 0.56 / 0.93 | 0.244 / 0.259 |
| ROS x2 (3.0 t/ha) + grass/scrub load x3 | 0.344 vs 0.345 (48%) | 1.16 / 1.80 | 0.286 / 0.281 |
| ROS x1.63 (2.45 t/ha) + grass/scrub load x2.5, sized right by class | 0.343 vs 0.345 (48%) | 0.73 / 1.22 | 0.264 / 0.272 |

By the scar's land cover (median area ratio / end-footprint Sorensen / share of later-pass detections inside the
forecast; final model, then the three variants):

| Scar class | Final | ROS x1.4 + grass x2.6 | ROS x2 + grass x3 | ROS x1.63 + grass x2.5 |
|---|---|---|---|---|
| closed forest (<10% grass, canopy 40%+) (852 fires, 822 later passes) | 1.38 / 0.289 / 26% | 0.79 / 0.253 / 18% | 1.58 / 0.282 / 29% | 1.03 / 0.269 / 22% |
| open forest (<10% grass, canopy <40%) (152 fires, 95 later passes) | 0.80 / 0.292 / 21% | 0.57 / 0.248 / 18% | 1.24 / 0.292 / 24% | 0.74 / 0.270 / 20% |
| mixed (329 fires, 185 later passes) | 0.51 / 0.249 / 17% | 0.44 / 0.236 / 15% | 0.92 / 0.289 / 24% | 0.56 / 0.257 / 18% |
| grass/scrub (half or more of the scar) (65 fires, 5 later passes) | 0.35 / 0.185 / 20% | 0.63 / 0.236 / 20% | 1.72 / 0.292 / 60% | 0.80 / 0.254 / 20% |

Reading: the inversion is right about size. The final model forecasts closed-forest fires 1.4x too big and grass/scrub
fires 3x too small; tripling the grass load brings the grass fires (and the mixed ones, 0.51 -> 0.92) to the right size
and lifts their footprint score most (the grass class has only 5 later passes, so its hit rate means nothing; the mixed class, 185 passes, goes 17 -> 24%), while lowering the whole-forest fit to x1.4 makes every
forest class too small again. Sizing by class is a real gain in the end footprint (0.275 -> 0.285 overall, best for
mixed and grass fires) and in later-pass hits (24 -> 28%), and it costs nothing in outline shape (0.344 vs 0.348): the
shape is still the circle's. The grass x3 overshoots (1.7x) and closed forest is still 1.6x, so a variant sized right
in both was run (`queue18.sh`: ROS x1.63, a 2.45 t/ha bed in forest, grass/scrub x2.5, about 6 t/ha): it does size
closed forest at 1.03x and grass at 0.80x, and it scores worse than the final model on the end footprint (0.266 vs
0.275) and later-pass hits (21 vs 24%). The final model's 1.4x over-forecast in closed forest was paying for its wrong
shape: a footprint that is too round catches more of a one-direction run when it is drawn too big. Honest sizes cost
overlap. What no fuel variant changes: the outline is a circle, and the run direction is not in the fuel.

**Cross-check against measured fire behaviour** (FSI thread, Oct 15, `ratapani/fsi/scouting/fire_behaviour_field_data.md`):
measured teak and dry-forest litter beds are loose, 3.4-5.1 kg/m3 (our loose bed uses 2.5, their lower bound); calm or
backing fires in such litter run 18-36 m/h and Ecuador teak fires 29-36 m/h, head fires with wind 30-160 m/h; noon dead
leaf moisture in peak season is 4-6%; field-to-predicted Rothermel ratios across five datasets are 0.7-2.6 (median 1.4).
Our final bed gives 30-39 m/h at noon moistures (the 1.5 t/ha loose bed's 15-19 m/h, doubled) and much less at
night and in the morning, which is the measured calm-fire range; the speed the model targets is the fuel thread's
footprint-corrected front speed, a median 24 m/h (IQR 10-56, 30 m/h where an advance is measurable; the 37 m/h and the
51-98 m/h quoted earlier are the uncorrected pass-to-pass figures, which carry pixel jitter), so the afternoon front
runs at the upper half of the observed range and the day's average near its median. The calibration is in the measured
range and its fitted factor is of the usual size. The polygons of 4k do not call for a faster fire, only a longer one. Two refinements they suggest, a slope cap (measured x1.4 at 10 deg, x3 at
20 deg, against x4-4.5 from the loose-bed Rothermel) and a 7-22 h moisture time lag for broadleaf litter instead of 1 h,
were not pursued: slope and wind do not steer Ratapani fires (4c), and the afternoon moisture is already at the floor.

### 4c. Does wind or slope steer Ratapani fires? (`passpairs.py`, 1,066 pass-to-pass moves over 500 m)
- Median advance 926 m between passes 12.5 h apart: 51-98 m/h (median 70), the same by day and by night (new detections
  2,838 on night passes vs 2,559 by day: these fires burn through the night).
- Direction relative to the ERA5 wind: 22% downwind, 55% across, 23.5% upwind (uniform would be 25/50/25); mean cosine
  -0.004; also uniform when the wind is 2 m/s or more; advance distance uncorrelated with wind speed (r = -0.04).
- Slope 5 deg or more: 30% of moves go downslope, 18% upslope. Litter fires here back down slopes (rolling embers, drier
  lower slopes, fire reaching ridges and then only having downhill to go) rather than run up them.
- A learned correction (LightGBM on arrival distance, physics time, wind, weather, fuel, terrain; held-out Sorensen)
  improves distance-only 0.228 to 0.252 with all features except wind; adding wind features makes it worse (0.241).
This is why the final model runs without wind: ERA5 wind over Ratapani (1-3 m/s, uniform across the sanctuary) carries
no usable steering signal at the 12 h scale we can observe. C-DAC's Sikkim fires are a different regime: grass and scrub
on steep Himalayan slopes with valley winds, where WRF's wind does matter.

### 4d. Barriers and restarts (the two C-DAC lessons)
**Roads as barriers** (Microsoft road detections rasterised to 20 m, 29,556 road pixels on forest, shrub or grass in the
box, about 1,180 ha; strict rule so the front cannot jump a one-pixel line). Shape 0.340 -> 0.342, footprint Sorensen
0.271 -> 0.271 (2017-21) and 0.275 -> 0.277 (2022-24). Barriers touch the 48 h forecast in 18% of fires, shrink it by
more than 10% in 8% and by more than 30% in 2%; in those 137 fires the end-footprint Sorensen goes 0.269 -> 0.276 and the
area ratio 1.03 -> 0.92. So roads do what C-DAC's hand-added layers do, but most Ratapani fires never reach a mapped road
within two days: the barriers that matter here, the department's fire lines and the dry stream beds, are not on any map
we have.

**Restart from every satellite pass** (`restart.py`, the slide-24 design; 365 fires seen on 2 or more passes within
48 h, 536 forecast steps, median lead 12.5 h to the next pass, 1,224 next-pass detections of which 1,021 are on new
ground more than 400 m from every earlier detection). Share of next-pass detections that fall inside the forecast:

| Forecast of the next pass | All next-pass detections | New ground only | Median forecast area |
|---|---|---|---|
| Free run from the first pass | 24.8% | 16.8% | 42 ha |
| Equal-area circle, same start | 23.9% | 16.0% | 42 ha |
| Restarted with every detection up to the previous pass | 31.5% | 20.7% | 45 ha |
| Equal-area circle around the restarted ignition | 33.8% | 22.6% | 45 ha |
| Persistence: 375 m around the previous detections | 44.5% | 33.7% | 83 ha |

With the burn-scar thread's FIRMS exports the same test runs on every sensor FSI gets (S-NPP + NOAA-20 from 2018 +
NOAA-21 from 2024, and MODIS Terra/Aqua), restricted to the sanctuary (`events_multi.py`, `restart_*_k.parquet`):

| Passes used | Fires with 2+ passes | Steps | Median lead | Next-pass hits: free / circle / restart / circle-restart / persistence | New ground: restart / persistence |
|---|---|---|---|---|---|
| S-NPP only | 365 | 536 | 12.5 h | 24.8 / 23.9 / 31.5 / 33.8 / 44.5% | 20.7 / 33.7% |
| S-NPP + NOAA-20 + NOAA-21 | 809 | 1,527 | 10.4 h | 29.4 / 29.0 / 44.7 / 50.2 / 65.8% | 20.9 / 41.7% |
| + MODIS | 882 | 1,755 | 2.5 h | 27.9 / 27.6 / 44.2 / 49.8 / 66.9% | 20.1 / 43.6% |

By lead time (three VIIRS satellites): under 3 h (744 steps, mostly the NOAA-20 pass 50 min after S-NPP) persistence
is trivial, 86%, restart 52%; 9-18 h (635 steps) free 22 / restart 36 / circle-restart 37 / persistence 46%; over 18 h
(148 steps) free 35 / restart 42 / circle-restart 40 / persistence 36%, the one range where the restarted physics beats
both baselines, by a little. Doubling the passes doubles the fires the restart design can serve (365 -> 809) and lifts
next-pass hits from 31.5% to 44.7%, but at every lead the equal-area circle around the same restarted ignition does as
well; MODIS adds few fires and 1 km pixels. End footprint for the multi-pass fires with three VIIRS satellites (n = 667):
Sorensen 0.250 free -> 0.300 restarted.

End footprint against the scar for the S-NPP multi-pass fires (n = 328): Sorensen 0.238 free -> 0.278 restarted; area
ratio 2.40 -> 3.00 (these are the long fires, where a model running at constant rate for two days over-forecasts; the FSI
archive's saturating extents in 4e say why). Restarting is worth +7 points on next-pass hits and +0.04 Sorensen, and in
the examples it is the one change that visibly improves the big fires (1466: 0.35 -> 0.50; 1613: 0.28 -> 0.37). But a
circle of the same area around the same restarted ignition does as well, and plain persistence does better at twice the
area: where the next pass will show fire is told by the last pass, not by the physics. C-DAC's planned orchestrator is
the right design; what makes it work is the pass cadence (they get S-NPP + NOAA-20/21 + MODIS, we have S-NPP only).

**Ignition as the whole VIIRS pixel footprint (Oct 15, `ign_fp` in `sim.py`, `queue17.sh`, `analyze_restart_final.py`).** The
fuel thread's timing work found that the VIIRS point lags the true front by about 380 m while the far edge of the scan x
track footprint is unbiased, and suggested lighting the whole footprint. The restart test above (365 S-NPP fires, 536
steps) was re-run on the final model with three ignition rules: the point snapped to the nearest fuel pixel (the rule
used so far), a 100 m disc around the point, and the whole footprint rectangle (scan x track, 0.4-1.6 km across; fire
797's first pass lights 119 ha this way against 13 ha with discs).

| Ignition | Median forecast area at the next pass: free / restart / persistence | Next-pass hits: free / restart / circle-restart / persistence | New ground: restart / persistence | End footprint vs scar (n = 328): Sorensen free / restart, area ratio free / restart |
|---|---|---|---|---|
| Snapped point (as above) | 49 / 52 / 83 ha | 27.0 / 34.6 / 35.3 / 44.5% | 24.1 / 33.7% | 0.241 / 0.279, 2.4x / 3.1x |
| 100 m disc | 78 / 87 / 121 ha | 33.9 / 42.4 / 42.1 / 50.9% | 31.0 / 41.1% | 0.224 / 0.257, 3.4x / 4.5x |
| Pixel footprint | 139 / 157 / 198 ha | 50.3 / 60.2 / 57.8 / 65.5% | 52.3 / 58.7% | 0.215 / 0.233, 5.2x / 6.9x |

Reading: lighting the footprint nearly doubles every hit rate, but it also nearly triples the forecast area and
over-forecasts the end footprint of these multi-pass fires 5-7x (snapped points: 2-3x). The extra hits are bought with
area, the way persistence buys its hits. The one real skill signal is in the comparison at equal area, physics against
its own equal-area circle: at leads over 18 h (102 steps) the restarted physics wins by 8.7 points with footprint
ignition (62.5 vs 53.8%) and by 5.8 with discs (48.1 vs 42.3%), against 0.5 with snapped points (43.3 vs 42.8%); at
9-18 h (379 steps) the margins are 1.5, -0.4 and 0.0. So a wide ignition lets the front's fuel-continuity shape show at
long leads, but a forecast lit from a footprint must be read as "somewhere in this 1.5 km2 pixel is burning", not as a
139 ha fire. The footprint's proper use is the one the timing work found, as the uncertainty of where the fire is; the
learned footprint and learned restart models (4i, 4j) take the point's distance as a feature and let the scars set the
reach. The free run on all 1,398 fires says the same: footprint ignition (median 27 ha lit against one pixel) forecasts
4.1x the scar's area (IQR 1.9-9.2x, against 1.0x [0.4-2.5] for the final model), the end-footprint Sorensen falls
0.275 -> 0.262 and the 48 h footprint's 0.220 -> 0.160, while later-pass hits rise 24 -> 47% (the equal-area circle
around the footprint gets 41% of them). The outline score at the scar's area drops to 0.260 for both the physics and its
circle because most scars are smaller than the footprint rectangle they start from.

### 4e. FSI's own large-fire archive as a growth check (`fsi_growth.py`)
FSI's portal export `fsi_portal/lff_mp.csv` has 386 large forest fire events inside our grid (2020-25, 298 in
Obedullahganj division), each with first and last detection and the bounding box of its detections.
- Half of them have a single detection time; 35% last 12 h or more, 22% a day or more, 14% two days or more.
- Bounding-box diagonal: median 1.6 km (q25-q75 1.3-2.3 km); box area median 121 ha.
- For the 150 that lasted 6 h or more, the box diagonal grows a median 79 m per hour of duration (q25-q75 47-144 m/h),
  the same as our pass-to-pass advance (51-98 m/h). Both are envelope growth (several fronts plus 375-750 m of pixel
  scatter), not a rate of spread of one front, which the Saha 2002 litter-fire measurements put at 100-430 m/day. The
  extent saturates: 2.2 km for 6-18 h fires, 2.65 km for 18-36 h, 2.6 km for 36-72 h, 3.6 km only for fires lasting 3
  days or more. Fires reach their size in the first day and then stall or wander; a model running at constant speed for
  48 h over-forecasts the long ones. The FSI-data thread's fuller read of the archive (`fsi/scouting/spread_from_active_fire.md`)
  adds: 64% of Ratapani large fires last one calendar day, and once a fire reaches day 2 it continues each further day
  with probability about 0.55; multi-day fires are 45% of March fires and 3% of February fires.
- 214 of our S-NPP events match an FSI event; FSI's multi-sensor (S-NPP + NOAA-20 + MODIS) box is 2.5x wider than our
  S-NPP-only detection extent (2.1 vs 0.85 km median). The missing NOAA-20 passes are the biggest gap in our pass data.

### 4f. The one-direction run: where the real scar lies relative to the first detection (`rundir.py`, `rundir_stats.py`, `teakcue.py`)
Akkshay's reading of the example maps, checked on all 1,223 scarred fires of 5 ha or more:
- Real scars are elongated: spread along the long axis is 2.1x the spread across it (q25-q75 1.6-2.9).
- The first VIIRS detections sit near one end of the scar, not its centre: median position 0.29 along the axis
  (0.5 = centre); 36% of fires are first seen in the end fifth, 24% near the middle. Night-first fires run farther
  (median 418 m vs 294 m by day).
- From the first detections the scar runs a median 330 m to its centroid (420 m for scars of 20 ha or more; over 500 m
  in 30% of fires) and reaches a median 840 m at its far end. Only 7% of scar pixels (mean; median 0%) lie more than 1 km
  from every detection of the event, so this is the fire itself, not neighbouring burns merged into the label.
- The first pass's own line of detections already lies along the final scar axis in 43% of fires (random 33%): the fire
  is caught mid-run, having come from the side where the fuel is gone, and it keeps going.

So the forecast, which grows almost evenly around the detection, is right about the size and wrong about the side.
Which cue at the first detections agrees with the direction the scar then ran (664 fires that ran over 300 m; a random
cue gives mean cosine 0.00 and 25% within 45 degrees)?

| Cue at the first detections | n | mean cosine | within 45 deg | within 90 deg |
|---|---|---|---|---|
| first pass -> second pass (needs the second pass) | 246 | +0.63 | 70% | 86% |
| away from built-up within 1 km | 72 | +0.38 | 44% | 71% |
| away from this season's earlier burns within 500 m (within 200 m) | 330 (62) | +0.19 (+0.28) | 29% (37%) | 61% (63%) |
| toward the larger burnable fuel mass within 1 km | 630 | +0.16 | 33% | 60% |
| away from the nearest non-fuel within 500 m | 488 | +0.15 | 28% | 58% |
| away from roads within 500 m | 152 | +0.14 | 24% | 61% |
| toward heavier teak leaf litter within 1 km (fuel-map 1-h load) | 664 | +0.10 | 32% | 57% |
| away from non-vegetation land cover | 337 | +0.08 | 27% | 53% |
| ERA5 wind direction (toward), first 24 h; wind >= 2 m/s | 664; 165 | +0.04; 0.00 | 30% | 53% |
| downslope at the first detections; slope >= 5 deg | 664; 346 | -0.06; -0.08 | 21%; 18% | 45% |

The litter load on the run side is only 4% heavier than on the opposite side (median ratio 1.04; heavier in 56% of
fires). Fires run away from where people and earlier burns are and into unburnt fuel; nothing in the weather or the
terrain says which way, and the second satellite pass says it best.

**How much is the direction worth, and can any cue supply it?** (`headtest2.py`) The forecast footprint is grown from the
first-pass detection pixels as a fire ellipse with the detection at its rear focus (distance along the heading divided
by k, doubled against it), sized to the scar, and scored like the circle (k = 1). Paired means on the same fires:

| Heading | Fires | Circle | Stretched k = 2 | k = 3 | Fires that ran > 300 m: circle -> k = 3 | k = 2 beats the circle in |
|---|---|---|---|---|---|---|
| True run direction (ceiling) | 1,223 | 0.293 | 0.375 | 0.393 | 0.227 -> 0.352 | 79% |
| First pass -> second pass | 306 | 0.238 | 0.255 | 0.253 | 0.214 -> 0.242 | 49% |
| Away from built-up within 1 km | 135 | 0.304 | 0.298 | 0.284 | 0.205 -> 0.224 | 41% |
| Away from this season's earlier burns | 632 | 0.323 | 0.306 | 0.284 | 0.255 -> 0.239 | 37% |
| Toward the burnable fuel mass | 1,161 | 0.294 | 0.269 | 0.250 | 0.227 -> 0.212 | 35% |
| Away from non-fuel / roads; toward teak litter load; wind; downslope | ... | 0.293-0.305 | 0.259-0.286 | 0.237-0.266 | all below the circle | 30-38% |

Scars of 20 ha or more: circle 0.334, true direction 0.412 (k = 2) and 0.428 (k = 3). So knowing the side the fire
will run is worth +0.08 to +0.10 Sorensen on every fire and +0.12 on the fires that run, the largest single gain
available to this model, larger than fuel, barriers or restarts. But every cue we can compute at the first detection
is right too rarely to use: stretching along a cue that is wrong two times in three costs more than it gains, so every
static cue scores below the plain circle, and even the second pass, right 70% of the time, gains only +0.017 as a
heading (its real value is as a restart). The fire's own heat pattern in the first pass (direction from the cooler to
the hotter pixels, 521 fires with 2+ pixels) is also uninformative (mean cosine +0.05; +0.33 in the 36 fires with a
3x FRP contrast). Akkshay's domain note applies here: these are surface fires in teak leaf litter, and the litter
load on the run side is only 4% heavier than behind, so the side is not written in the fuel map either. What is left
is the second pass, which is why the number of passes (NOAA-20/21) decides more than any physics.

**Does the pass-to-pass cue survive the VIIRS pixel footprint?** (asked by the fuel thread's timing work, Oct 15: the point
lags the true front by ~380 m, and 67% of pass-to-pass intervals show no advance beyond the earlier footprint.) Among the 246
multi-pass fires with a run over 300 m, the pass 1 → pass 2 centroid move exceeds the first-pass footprint (half-diagonal,
median 327 m) in 228; for those the run lies within 45° of the move in 72% (78% for moves over 800 m); for the 18 moves inside
the footprint, 39%. The cue is carried by real advances, not pixel jitter.

### 4g. Are the VIIRS points displaced by wind-blown smoke? No (`detoff.py`, `smoke_chip.py`, Oct 15)

Akkshay's reading of fire 797's map: the VIIRS points sit off the real burnt area, so perhaps the satellite saw smoke that the
wind had carried to one side. Tested two ways.

**Physics.** VIIRS flags a fire pixel when its 4 µm (I4) radiance stands out from the neighbourhood. Smoke is cold and nearly
transparent at 4 µm, so a detection needs flaming or glowing fuel inside the 375 m pixel. What can displace a point is the pixel
itself (the reported lat/lon is the pixel centre, up to ~190-400 m from a sub-pixel fire), geolocation (~100 m) and the scar map
stopping short of the true front.

**Fire 797 on 2 Apr 2019.** Sentinel-2 flew over at 10:46 IST while the fire burned (`examples/smoke_797_20190402.png`). Its
SWIR hot pixels (20 m) draw the flame front along the north-west edge of the scar. The VIIRS points of 01:51 IST (9 h before)
and 13:04 IST (2 h after) lie on that line, within 100-200 m. The true-colour image shows the smoke drifting west, and ERA5
agrees (wind toward 260°, 2.8 m/s): the smoke did go to the left of the run, but the points did not go with it. The points that
look "off" in `fire_2019_797.png` sit 100-550 m west of the mapped scar, where the Sentinel-2 after-image is burnt but the label
is missing (a label gap, not a sensor displacement).

**All 1,223 scarred fires, 3,504 S-NPP points** (`results/detoff_all.parquet`):

| | all points | first pass | later passes | day | night |
|---|---|---|---|---|---|
| inside the mapped scar | 31% | 34% | 25% | 37% | 20% |
| within 200 m of it | 79% | 84% | 68% | 85% | 68% |
| within half a VIIRS pixel | 88% | 92% | 78% | 92% | 81% |
| more than 500 m off | 7% | 4% | 14% | 6% | 10% |
| median distance | 45 m | 40 m | 85-113 m | 28 m | 102 m |

For the points outside the scar, the direction back to the scar relative to the ERA5 wind at that hour is 23% downwind /
50% crosswind / 27% upwind (the smoke idea predicts the points downwind of the fire, i.e. ~100% upwind offsets; random is
25 / 50 / 25). Mean cosine -0.04. The same for winds over 3 m/s (23 / 49 / 28), for points more than 300 m off (22 / 52 / 27),
day or night, first pass or later. First detection to scar centroid vs wind: cosine 0.00. Offsets are not stretched east-west
(the scan direction) either: median |E-W| = |N-S| = 60 m at every pixel size. ERA5 winds at detection hours are light
(median 2.2 m/s, 18% above 3 m/s). 18% of the outside points have a nearer burn label from another date window (median
100 m away): the scar dating splits some burns across windows.

Night points sit farther from the scar than day points (median 102 m vs 28 m): night fires are smaller and cooler, and the
scar map misses more of them.

**Wind in subsets of the run analysis (4f).** No subset of the 664 fires with a run over 300 m lines up with the ERA5
wind: within 45° of downwind 30% (random 25%) for winds under 2 m/s (499 fires), 30% for 2-3 m/s (152), 25% for 3-4 m/s (12);
29% day-detected, 32% night; 32% for scars over 20 ha; 35% for elongation over 2.5. The scar axis is within 30° of the
wind axis in 33% of fires (random 33%). The ERA5 wind over Ratapani during fires is light and carries no steering signal in
any subset; the one-direction run is fire behaviour, not a sensor artefact.

### 4h. Smoke plumes as a wind vane: does the real wind steer the fire? (`plume.py`, `plume_stats.py`, Oct 15)

If ERA5's 9 km wind is the weak link, the smoke itself is the best wind measurement we have. 273 scarred fires were
caught burning by Sentinel-2 (hot pixels in the scene at 10:45 IST, `results/midevent_scenes.parquet`). For each scene the
blue-band excess over the latest clear pre-fire image, with the scene offset taken out, is profiled in 12 sectors of 30° from
250 m to 3 km around the hot pixels; the plume direction is the sector with the highest 75th-percentile excess, and a weighted
vector mean is a second estimate (`results/plume_scenes.parquet`, pictures in `examples/plumes/`). The two agree within 30° in
67% of scenes; "clear plume" below means they agree and the best sector stands 2 (or 3) standard deviations above the rest.
Random agreement within 45° is 25%; "opposite" means within 45° of the reverse direction.

| Direction compared with the smoke | n | within 45° | opposite |
|---|---|---|---|
| ERA5 10 m wind at the scene hour, all scenes | 265 | 34% | 21% |
| ERA5, clear plumes (≥2 sd) | 125 | 38% | 20% |
| ERA5, clearest plumes (≥3 sd) | 68 | 43% | 16% |
| scar centre → active front (where the fire had got to by 10:45) | 125 | 27% | 23% |
| front → next VIIRS pass, moves over 300 m (where it went next) | 65 | 25% | 32% |
| same, clearest plumes | 36 | 17% | 36% |
| first detection → scar centre (the run of 4f) | 125 | 25% | 31% |
| VIIRS pass 1 → 2 momentum | 73 | 19% | 33% |

- ERA5 has the wind direction roughly right only for the clearest plumes (43-47% within 45°), and best at 1.5-3 m/s
  (48%); below 1.5 m/s or above 3 m/s it is near random. So ERA5 is a poor wind for Ratapani, as suspected.
- But a better wind would not rescue the forecast. Even the smoke direction does not say where the fire goes next: the
  next pass's detections lie with the smoke in 17-25% of moves and against it in 32-36%. Of the scar more than 300 m from the
  morning front, a median 9% lies downwind of the plume and 18-22% upwind. Fires here sit at the downwind edge of what has
  burnt by late morning, then spread back and sideways over the following night and day, when the wind has turned or dropped.
  Same-afternoon moves (3 h later) are 31% with / 29% against the smoke; night-and-next-day moves (13 cases) 0% with / 46%
  against.

**Where this leaves the wind question.** ERA5-Land's wind is loosely related to the real wind (smoke), and the real wind is
not related to where the scar ends up. The run direction of 4f is not a wind effect that bad wind data hid; it is the fire
backing and flanking through continuous litter after the first head run. For the Rothermel model that means wind should stay
off, as fitted, and what steers a Ratapani fire over 1-2 days is what we found in 4f: fuel continuity, roads and earlier burns,
and the previous pass.

### 4i. Reverse engineering from the scars: a learned burn footprint (`footprint.py`, `foot_stats.py`, `foot_examples.py`, Oct 15)

Akkshay's question: we know the real scars, so why not learn from them? This is the per-cell probability-of-burning map
built the data-driven way. For each of the 1,223 scarred fires (mapped scar ≥ 5 ha) every burnable 20 m pixel within 2.5 km of
the first VIIRS pass gets 38 features: distance to the nearest first-pass point and to their centroid; the physics model's
arrival time (final 4b model, ignition not snapped); the pixel's bearing relative to the ERA5 wind (at the first hour and the
24 h mean) and to the line of the first-pass points; WorldCover class, elevation, slope; distance to the nearest road, non-vegetation,
built-up area and earlier burn this season; burn history (seasons burned since 2017, burned last season); the loose-bed 1 h load,
leaf-fall fraction; the pipeline lean model's dryness score for the pixel's 500 m cell on that day and its cell's forest share;
the same quantities as differences from the detection centroid (is this pixel farther from the village, higher, drier than where
the fire is); and fire-level values (number of first-pass points, their spread, FRP, day/night, day of year, hourly weather and
1 h fuel moisture at the first detection). Label: the pixel is in the event's final scar. Training rows are an 80 m lattice
(3.5 M rows, 2.9% positive); LightGBM, 400 rounds, one model per held-out season (2017-24). Scoring is at full 20 m resolution
on every pixel of every fire with its season's held-out model (`results/foot_score_*.parquet`, `results/foot_models/`).

**Outline at the scar's area** (the 4b shape score, same fires; the circle and physics here use the raw detection points, no
snap to the scar):

| | learned | circle | physics | learned better than circle | than physics |
|---|---|---|---|---|---|
| all 1,223 fires | **0.363** | 0.294 | 0.299 | 75% | 71% |
| scars 5-20 ha (465) | 0.292 | 0.226 | 0.232 | 64% | 63% |
| scars 20-50 ha (385) | 0.389 | 0.318 | 0.323 | 75% | 74% |
| scars ≥ 50 ha (373) | 0.425 | 0.353 | 0.359 | 87% | 78% |
| per-fire AUC (pixel in scar vs not) | 0.943 | 0.924 | 0.877 | | |

Every held-out season gains: 2017 0.31 vs 0.27, 2018 0.43 vs 0.34, 2019 0.45 vs 0.37, 2020 0.31 vs 0.27, 2021 0.30 vs 0.22,
2022 0.33 vs 0.27, 2023 0.34 vs 0.27, 2024 0.29 vs 0.21 (learned vs circle). The +0.07 is most of the +0.08-0.10 that 4f
estimated for knowing the run side, and it comes without any wind.

**As a free forecast** (footprint = the model's own expected area, the sum of pixel chances): learned 0.320 against 0.266 for a
circle of the same area and 0.270 for the physics front cut at the same area; the physics 48 h forecast scores 0.213 because it
is far too big (median 7.8× the scar: a 48 h run assumes the fire burns for 48 h). The learned area is unbiased in the middle
(median ratio 1.08, IQR 0.55-2.12) but weak as a size forecast (log-correlation with the true area 0.31): 2.3× too big for 5-20
ha scars, 0.4× for scars over 50 ha. Size still depends on how long the fire is left to burn, which nothing at first detection
tells.

**Later passes** (306 fires with a second pass, 1,135 later detections, footprint = the learned expected area): the learned
footprint contains the later detection in 31% of cases, the equal-area circle 17%, the equal-area physics front 18%.

Examples (`examples/learned_<season>_<event>.png`, left: chance map, right: equal-area outlines): fire 830 0.65 learned vs 0.55
circle, 1466 0.45 vs 0.38, 1613 0.38 vs 0.34, 797 0.33 vs 0.23 (the chance map runs north along the forested ridge, where the
fire went, and stays out of the grassland fringe to the south, where the physics front went), 1751 0.22 vs 0.17, 1735 label
failure (0 for all). The 2.5 km window cuts the biggest scars (797 ran 4 km); a longer reach would need a second stage.

**What gives the gain** (`foot_ablate.py`, `results/foot_ablation.json`: feature groups added or removed, 4 folds of two
seasons, scored on the 80 m lattice rows, where the circle gives 0.294 and the full model 0.363, the same as at 20 m):

| features | outline |
|---|---|
| distance to the detections only (nearest point, centroid) | 0.306 |
| + fire-level (count, spread, FRP, day/night, date, weather, 1 h moisture) | 0.305 |
| + physics arrival time | 0.313 |
| + pixel statics and their differences from the detection (land cover, roads, non-forest, villages, earlier burns, burn history, fuel load, leaf fall, elevation, slope) | 0.354 |
| + dryness (lean cell score) | 0.360 |
| full (+ wind and front-line relations) | 0.363 |
| full without wind and front relations | 0.360 |
| full without dryness | 0.351 |
| full without the physics arrival time | 0.361 |

The gain is the landscape: where the continuous unburnt fuel is relative to the detections (forest edge, villages, roads, this
season's and last season's burns), then dryness (+0.01). Wind and front orientation add 0.003; the physics arrival time adds
0.002 once the landscape is in. This is the quantitative form of 4f: the run side is readable from fuel continuity when all
the cues are combined per pixel, even though no single cue beat the circle as a heading.

**Scored the Rethink thread's way** (`foot_cells.py`; its `exp_spread.py` construction reproduced exactly: a fire is the group of
VIIRS cells active on a day, candidates are the unburned 500 m cells within 1.5 km, a candidate burns when its first burn day
or a VIIRS point falls in the next 2 days; 1,386 fire-days 2017-24 with at least one burning candidate, 23,753 candidate cells,
3,811 burning). Share of burning cells caught by the top 5 cells per fire: footprint model (mean pixel chance per cell) 36%,
random 34%, nearest-distance 29%, the lean dryness score alone 46%, the Rethink thread's full model 47%, its full model plus the
footprint score 47%. Top 10: 65% / 60% / 56% / 71% / 71% / 71%. So the footprint model adds nothing to the cell question.
The two questions differ: the Rethink task masks the fire's own cells and everything already burned, so what is left is the
ring 0.5-1.5 km out, where distance carries no information (adjacent unburned cells burn *less*: they are the gaps the fire
skipped) and per-cell dryness decides. The footprint model's skill is inside that masked body: which 20 m pixels around the
detections burn, the outline and the run side. For "which cells next", use the Rethink model; for "what will this fire's scar
look like", use the footprint model; stacking them gains nothing at the cell level.

### 4j. Learned restart: from every pass so far, where will the next pass show fire, and where does the fire end? (`foot_restart.py`, `analyze_lr.py`, `lr_examples.py`, Oct 15)
The learned footprint of 4i uses the first pass only. This repeats the idea at every pass, the way C-DAC's orchestrator
restarts the physics: 809 fires seen on 2 or more VIIRS passes within 48 h (S-NPP + NOAA-20 + NOAA-21, the
multi-satellite set of 4d), 1,527 forecast steps with a median lead of 10.4 h to the next
pass, and 667 of the fires with a mapped scar for the end footprint. No physics inside. Every burnable 20 m pixel
within 2.5 km of any detection so far gets: distances to all, the latest and the first detections and their centroids;
its bearing relative to the first-to-latest centroid move (the 4f momentum cue) and to the latest pass's axis; the
landscape statics and deltas of 4i; the lean dryness on the latest pass's day; the ERA5 weather at the latest pass's
hour; FRP, elapsed time, the lead to the next pass (known from the orbit), and how far the fire has run. Two LightGBM
heads per held-out season: "next" (label: pixel within 240 m of a next-pass detection; held-out AUC 0.90-0.93) and
"end" (pixel in the final raster scar; 0.85-0.92). Baselines at the same area: persistence (475 m around every known
detection, the 375 m of 4d around 100 m ignition discs) and the plain distance ranking, which is persistence at any
area. A detection is "hit" when the forecast has a pixel within 240 m of it, as in 4d.

| Forecast of the next pass | Median area | All 3,803 next-pass detections | New ground (2,185 detections > 400 m from every earlier one) | Leads 9-18 h (635 steps) | Leads > 18 h (148 steps) |
|---|---|---|---|---|---|
| Persistence, 475 m around every detection so far | 137 ha | 72.4% | 51.9% | 54.3% | 42.4% |
| Learned (next-pass head), same area | 137 ha | 86.3% | 77.0% | 79.8% | 81.1% |
| Learned (end-scar head), same area | 137 ha | 87.4% | 78.3% | 79.8% | 78.1% |
| Distance ranking, half the area | 69 ha | 60.5% | 31.3% | 36.9% | 24.9% |
| Learned, half the area | 69 ha | 78.7% | 65.4% | 68.7% | 71.0% |
| Distance ranking, the learned model's own expected area | 43 ha | 53.4% | 20.0% | 27.6% | 19.9% |
| Learned, its own expected area | 43 ha | 69.5% | 53.7% | 56.5% | 60.6% |

By how much had been seen: after pass 1: 72.5 -> 86.0%; after pass 2: 67.7 -> 82.4%; after pass 3: 73.9 -> 88.3%; after pass 4 or later: 76.2 -> 89.9%. Pixel-level AUC for the next pass 0.923 against 0.901 for distance
alone. Leads under 3 h (744 steps, the NOAA-20 pass 50 min after S-NPP) are 90.8% for
persistence and 92.0% learned.

Read with audit corrections 3, 4 and 6: the "lead" is the time to the next pass that detected the fire; the hit rate counts caught
detections among fires seen again and never false alarms; and the 744 short steps carry no information (90.8 vs 92.0%), so the number
to quote beside 86.3 vs 72.4 is **79.0 vs 51.8% for leads of 3 h and more** (polygon run: 79.0 vs 51.8, latest-pass circle 56.2). The
audit's fairer no-skill rule, the same area around the latest pass only, scores 74.1% at the persistence area (persistence 72.2);
the learned restart leads it by 11.7 points (CI 10.3-13.1) and on new ground by 76.3 vs 55.6. The known set at each step comes from
hindsight grouping of the detections (7% of steps are tied together only by later detections), which is fair across methods but is
not what a live system would have.

**End footprint** with every pass known (n = 667, scar median 37 ha): at the scar's area the
learned end head scores Sorensen 0.338 against 0.259 for the distance ranking and 0.257 for the
persistence disc (learned better in 76% of fires; every season: 2017 0.22 vs 0.18, 2018 0.45 vs 0.34, 2019 0.49 vs 0.38, 2020 0.26 vs 0.22, 2021 0.27 vs 0.18, 2022 0.30 vs 0.24, 2023 0.33 vs 0.28, 2024 0.28 vs 0.20); at its own
expected area (45 ha) 0.297 against 0.234. The restarted physics of 4d
reached 0.300 on the same multi-satellite fires.

**What it uses.** The next-pass head leans on the distance to the latest pass, the distance to any detection, the lead
time, dryness (lean, and the pixel's dryness relative to the fire), then wind speed, FRP and the bearing relative to the
wind; the end head on distance, dryness, day of season, distance to earlier burns, elevation, last year's burn, leaf
fall, FRP, fuel load and roads. The momentum cue ranks below all of these. Maps for four fires with 3-5 passes:
`examples/learned_restart/restart_<season>_<event>.png` (one panel per pass: what was known, the learned area and the
persistence disc at the same area, where the next pass showed fire; last panel the end footprint).

**Feature-group ablation** (`foot_restart_ablate.py`: the next-pass head retrained without one group at a time on half
the lattice rows, seasons held out; share of next-pass pixels captured at the persistence count, persistence itself
47.7%):

| Next-pass head | Features | AUC | Captured at the persistence count |
|---|---|---|---|
| all features | 46 | 0.913 | 59.4% |
| no weather | 41 | 0.914 | 59.6% |
| no momentum/axis | 41 | 0.914 | 59.4% |
| no landscape | 28 | 0.914 | 59.1% |
| no dryness | 43 | 0.911 | 58.3% |
| no FRP/time | 37 | 0.912 | 59.1% |
| distances and lead only | 6 | 0.901 | 55.1% |

Most of the gain over persistence is in the first six features: how far a fire gets by the next pass is a function of
the lead time and of where the last pass put it, and a learned distance decay beats a fixed 475 m disc by 7 points.
Dryness adds one point, the landscape and FRP a fraction each, and the weather and the momentum cue add nothing, which
matches 4c, 4g and 4h.

Reading: this is the first model in this thread that says where the fire goes next better than "near where it was".
At the persistence area it puts 86.3% of next-pass detections inside the forecast against 72.4% for
persistence, at half that area it still matches persistence (78.7% at 69 ha), and
the gain is largest exactly where the physics restart and persistence fail: long leads (81.1 against
42.4% beyond 18 h) and new ground (77.0 against 51.9%). The next-pass head is
trained on VIIRS alone, so the label question of 4k does not touch it; the end head is trained on the raster labels and
is rescored on the grown outlines in 4k. The learned restart and the learned footprint are the two pieces to carry
forward; the physics keeps its uses (size, isochrones against barriers, intensity).

**Retrained with the polygon end labels** (`SCAR_GROWN=1 GROWN_STORE=grown_scars_viirs.pkl`, models `lrg_models/`, scores `lrg_score_*`,
Oct 15, after Akkshay's go-ahead in 4k): 738 fires with a grown outline, 1,435 steps. The next-pass head is unchanged within noise (85.9%
against 72.2% persistence at the persistence area; 78.1% at half the area; 68.8 against 53.2% at the expected area; held-out AUC 0.953).
The end head, now trained on the outlines (held-out AUC 0.87-0.93), scores 0.525 Sorensen at the polygon's area against 0.462 for the
distance ranking and 0.434 for persistence (median polygon 119 ha; the raster-label version scored 0.338 against 0.259 on 37 ha scars),
and 0.472 against 0.428 at its own expected area, which is right-sized (117 ha against 119). That is the same gain over the circle as the
first-pass footprint of 4i on the outlines (0.517 against 0.463): knowing every pass so far fixes where the fire is, and the end head adds
the same landscape-and-dryness margin on top.
*Honest retrain (audit item 2, the earlier-burn rule; Oct 15; these are the figures in `lrg_models/` and `lrg_score_*` now):* next-pass
hits 85.7% against 72.2% persistence at the persistence area (78.2% at half the area; 3 h+ leads 78.3 against 51.8%; new ground 75.9
against 51.6%); end footprint 0.515 at the polygon's area against 0.462 (distance) and 0.434 (persistence), and 0.464 against 0.426 at its
own expected area (119 ha). So the next-pass head loses nothing and the end head 0.01: the leaked "earlier burn" pixels were telling it
a little about where the fire would stop.

**Far-side distances** (`FAR_SIDE=1`, models `lrf_models/`, scores `lrf_score_*`; Akkshay's "try", Oct 15): the distance to the latest pass is
measured from the far edge of each VIIRS pixel footprint (the side away from the earlier passes, where the fuel thread's timing work puts
the true front) as well as from the pixel centre. The model takes it as its third feature, but the scores do not move: next-pass hits
85.7% against 85.9% at the persistence area, 79.0 against 78.1% at half the area, 69.8 against 68.8% at the expected area, end footprint
0.525 both. The learned distance decay already absorbs the ~380 m centre-to-front lag; the far side matters for reading a bearing (4l),
not for the restart.

### 4k. Which scar is the truth? The scar thread's grown outlines against the burn-label rasters (`grown.py`, `grown_check.py`, `grown_examples.py`, Oct 15)
Everything above scores against the research thread's burn-label rasters (research/ratapani-burn-labels, 20 m, each
pixel dated by its clear-look window). The scar thread's per-alert outlines, grown on Oct 15 into the ground burned by
the next clear image, were matched to this thread's fires through the alert lookup: 1,214 of the 1,223 footprint-model
fires have one (83 flagged as kept at the first-image outline because growing would have merged them into a larger
later burn).

- **Size.** Median 96 ha (polygon) against 28.5 ha (raster label) for the same fires; ratio quartiles 1.4 / 2.4 / 5.1,
  rising with the number of passes (2.3x for one pass, 3.5x for three or more). The pre-grow polygons are already 78 ha
  and agree with the grown ones (Sorensen 0.92), so the gap is between the two methods, not the growing. The raster label
  sits inside the polygon (median 100% of its pixels), and the polygon's extra ground is 51 ha per fire at a median 580 m
  from the first pass (the raster label's pixels: 390 m); only 3% of it lies beyond the footprint model's 2.5 km reach.
- **What the rasters say about that extra ground** (`results/grown_check.parquet`): 85% of it is never marked burned in
  any window of the season, so it is not a dating or connectivity cut; 11% is burned with a window overlapping the fire
  but in a patch the 400 m rule did not connect; 4% is a later burn (median 6 days later); 0.2% an earlier one.
- **What the images say** (`examples/grown/outlines_<event>.png`: first clear Sentinel-2 look after the last detection,
  last clear look before the fire, NBR drop between them, both outlines). Fire 942 (Apr 2020, 4 passes): the polygon's
  743 ha is dark burnt ground in SWIR with a median NBR drop of 0.27 (raster label 0.32, the surroundings 0.15) and was
  unburnt a month earlier; the raster label is 112 ha of scattered patches inside it, and the VIIRS passes march across
  the polygon, not the patches. Fires 1221, 1464, 808 and 1735 read the same way (polygon-only NBR drop 0.19-0.24
  against 0.07-0.15 around them). Fire 797 is the exception: the raster label (1,064 ha) is larger than the polygon (764 ha).
- **Why the rasters miss it.** Their rule needs a clear look at most 20 days earlier (fire 942's looks are 30 days apart)
  and an NBR drop 0.12 above the surrounding 1.5 km, which a large burn removes by burning its own surroundings, so the
  interiors of big fires fail the test and only their edges and small patches pass. The research thread's own blind check
  found 7.4% of pixels labelled unburned had in fact burned; at the sanctuary's burned fraction that is more ground than
  the labels contain. The fuel inversion and the calibration in 4b rest on these rasters; the 2-day scoring labels do too, but the Cleaner fire
  labels thread had already tested that side (labels_v3/README.md, "Undersized season rasters"): at the 500 m cell level the
  polygons add about a quarter more burned cell-days, its "union" labels include them, and retraining on them moves the
  2-day scores by under 1 point, so the undercount matters for fire sizes, spread and fuel, not for the cell scores.
- **For this thread.** Against the polygons the final physics model's footprint at last pass + 12 h covers 0.29x the
  scar (IQR 0.13-0.64), not 1.0x; the 24 h free run covers 0.61x and the 48 h run 1.9x, and the free run reaches the
  polygon's area after a median 26 h (IQR 15-34 h; 25 h for single-pass fires, 36 h for fires seen on three or more
  passes; 24% of fires need more than 48 h). So the 3.0 t/ha bed sizes the fires right against the polygons too, if they
  are allowed to burn about a day after the first detection: it was the stop rule (last pass + 12 h), fitted to the
  under-sized labels, that was too short, which also matches the fuel thread's timing work (87% of the scar burnt within
  24 h of the first alert, fronts of 24-37 m/h). The learned footprint and learned restart are rescored and retrained
  on the polygons below (`queue20.sh`-`queue22.sh`). Akkshay (Oct 15 09:01Z): go ahead, the outlines are this thread's
  scar truth for sizes and spread; the 2-day cell scores are unaffected (labels thread, under 1 point).

**Rescoring the raster-trained footprint model on the outlines** (`SCAR_GROWN=1 footprint.py score`, 1,213 fires,
polygon median 96 ha): at the polygon's area the learned footprint scores 0.497, the circle 0.463 and the physics
0.454 (on the raster labels: 0.363 / 0.294 / 0.299). Every method rises because a bigger truth is easier to overlap at
its own area, and the learned model's margin over the circle shrinks from +0.07 to +0.03: trained on patchy labels it
learned the patches, and by pixel ranking the circle is now slightly ahead (AUC 0.921 against 0.915). Its expected
area stays 32 ha against a 96 ha truth, so at its own area it scores 0.328, and the 48 h physics run, 1.9x too big on
the rasters, is now the best free forecast at 0.378. The season-held-out margin is still positive in every season
(2017 0.47 vs 0.44 ... 2019 0.54 vs 0.49). The retrained model on the outlines follows.

**Retrained on the outlines** (`SCAR_GROWN=1 footprint.py build/train/score`, models in `results/foot_models_grown/`,
scores `foot_score_grown2_*`): at the polygon's area the learned footprint scores 0.517 against 0.463 for the circle and
0.454 for the physics (better than the circle in 73% of fires and in every season, 2017 0.49 vs 0.44 to 2019 0.56 vs
0.49); its expected area is now 98 ha against a 96 ha truth, so at its own area it scores 0.446 against 0.407 (circle)
and 0.410 (physics at the same area) and 0.378 for the 48 h physics run; AUC 0.935 against 0.921; later-pass hits 55%
against 38% (circle) and 41% (physics). *Honest retrain (audit item 2, Oct 15; the figures in `results/foot_models_grown/` and
`foot_score_grown2_*` now):* 0.502 against 0.454 (circle) and 0.442 (physics) at the polygon's area; 0.435 against 0.401 at its own
area (98 ha against 96); AUC 0.933 against 0.920; later-pass hits 53.7% against 36.7% (circle) and 39.9% (physics); better than the
circle in 72.5% of fires and in every season (2017 0.47 vs 0.44 to 2020 0.54 vs 0.50). Top features by gain: distance to the nearest
detection, physics arrival time, lean dryness, day of year, distance to the centroid, wind speed at the first pass. With the bigger truth the physics arrival time becomes the model's second
feature after distance (then reach, dryness, day of season, FRP): the fires run far enough that how long the physics
needs to get there starts to matter, which it did not on the patchy labels.

### 4l. Can the run direction be read from the first pass? (`direction_cues.py`, Oct 15, Akkshay's question)
Akkshay's point: fires are caught midway (ignition a median 15 h before the first alert, the point about 380 m
behind the front, 4k), so the fire is already running one way when VIIRS first sees it, and a model that knew that way
would draw the right outline. On the polygon truth the median scar centroid is 403 m from the first-pass
centroid, the polygons are 1.9x longer than wide, and the first pass sits at position
0.31 along the long axis (0 = at an end, 0.5 = the middle); the raster and polygon run directions agree within
45 degrees in 70% of fires. Every cue that is known at the first pass was tested on the 765 fires
whose polygon centroid lies at least 300 m from the first pass (a direction exists), as the share of fires where the
cue points within 45 degrees of the true run (random 25%; the mean cosine is 0 for no information, 1 for perfect):

| Cue at the first pass | Fires | Within 45 deg | Within 90 deg | Mean cosine |
|---|---|---|---|---|
| Toward the fuel mass within 1 km | 729 | 38% | 68% | +0.29 |
| Away from this season's earlier burns | 401 | 35% | 67% | +0.28 |
| Away from the nearest village | 79 | 35% | 68% | +0.30 |
| Away from non-fuel ground (edge) | 564 | 33% | 64% | +0.23 |
| FRP-weighted shift of the first-pass cluster (head is hotter) | 133 | 38% | 59% | +0.17 |
| Brightness-weighted shift | 83 | 30% | 54% | +0.09 |
| Toward the hottest pixel | 313 | 29% | 50% | +0.04 |
| Heavier litter load | 765 | 31% | 57% | +0.11 |
| Away from the nearest road | 176 | 29% | 58% | +0.11 |
| Away from non-vegetation land cover | 381 | 28% | 54% | +0.08 |
| ERA5 wind over the next 24 h | 765 | 26% | 50% | +0.00 |
| Downslope | 765 | 22% | 47% | -0.05 |
| Pass 1 to pass 2 move (known only after the second pass) | 257 | 63% | 85% | +0.59 |

The orientation of the first-pass cluster (an axis, so two possible ends; random 50%) points along the run in
51% of the 333 fires with a cluster wider than 100 m: it carries nothing. The hottest pixel and the
brightness-weighted shift carry nothing; the FRP-weighted shift of a multi-pixel first pass is the only within-cluster
cue above chance, 38% on 133 fires, and it is weak. The landscape cues are the strongest things known at the first
pass, and they are all weak alone: toward the fuel mass 38%, away from earlier burns and villages 35%, away from the
non-fuel edge 33%. The one strong cue is the move between the first two passes, 63% on the polygons (70% on the raster
labels), which is only known once the second pass is in; that is what the learned restart (4j) uses, and its ablation
says the position of the latest pass carries it.

So, at the first pass, nothing in the VIIRS data alone gives the direction: a single pass is a snapshot of the hot
front with no memory of where it came from, and the burnt ground behind it is invisible at 4 um. What machine learning
can do, and does in 4i, is combine the weak landscape cues with dryness and fuel into a footprint that is right more
often than the circle (0.52 against 0.46 on the polygons, better in 73% of fires). The direction accuracy of that
learned footprint (its centroid against the true run) is being scored now and goes here when it lands (`queue23.sh`,
`foot_score_dir_*`). Two cues not yet available: the fuel thread's back-simulated ignition point per fire (the
vector from the fitted start to the first detection is a direction known before the second pass; the fit is running in
fuel-map/ratapani/timing/) and the pixel far side, which cuts the point's lag from ~380 m to ~130 m and should sharpen
the pass-to-pass bearing; both are tests for the learned footprint once the fuel thread's fit lands.

**Two more tries (Akkshay, 09:58Z "try"; `direction_cues2.py`).** (1) A start point back-fitted from the first pass
alone: a front that has run for hours should bow outward in the direction of travel, so for the 112 fires whose first
pass has three or more pixels forming an arc (not a line), a circle was fitted through the pixel centres (median radius
360 m) and the direction from its centre to the cluster taken as the heading. Result: 25% within 45 degrees, exactly
random, mean cosine -0.03. The hot pixels of a first pass are not a clean front; they are whatever was burning across
the pixel footprints at that minute, and their curvature says nothing about where the fire came from. A start point
from VIIRS alone is therefore not available; the fuel thread's back-fit uses mid-fire images as well, and stays the
cue to test when it lands. (2) Pixel far sides for the pass-to-pass bearing: each second-pass point moved to the edge of
its scan x track footprint farthest from the first-pass centroid (the fuel thread's unbiased edge). Bearing within
45 degrees of the polygon run, 257 fires: centre 62.6%, far side 65.4%, near side (control) 59.9%. The gain sits where
it should, on short moves: 300-800 m moves 50.9 -> 57.4% (n = 108), moves over 800 m 75.0 -> 74.3% (n = 136), so the
far side is the right way to take a pass-to-pass bearing when the move is about a pixel long, and it changes nothing
for the long runs. It goes into the learned restart's distance features as a next step.

**The fuel thread's back-fitted start points** (`ignition_cue.py`, fuel-map/ratapani/ignition/ignition_fits_partial.csv,
174 fires so far of 809; the fit uses the engine with a per-fire speed factor, the VIIRS footprints at their pass times
and the grown polygon as the target). Caution first: these starts were fitted with every pass and the final scar, so a
"start to first detection" bearing from them is not a forecast; it is a ceiling. Even so it fails: on the 115 fires with
a polygon run of 300 m or more, the bearing from the fitted start (median 350 m from the first pass, 5.5 h earlier) to
the first-pass centroid points within 45 degrees of the true run in 21%, below random, mean cosine -0.11; restricting
to well-constrained starts (spread under 500 m) 22%. The fitted start more often lies between the first detection and
the bulk of the scar than behind the detection: the first pass catches the fire on a flank, not at its tail, and the
fire runs from where it was lit, inside the eventual scar, in the direction the landscape allows, not away from the
first alert. The fuel thread will rerun the fit with pass 1 only (no later passes, no scar) as the fair test, but a
cue that fails with the answer in hand cannot pass without it.

**Fair start point (Oct 16; fuel thread's `ignition_fits_fair.csv`, first detecting pass and the quiet passes before it only, 788 fires):**
the bearing from the fitted start point to the first-pass centroid, used as the run direction, falls within 45 degrees of the real run in
24.8% of 303 fires with a usable run (random 25%; within 90 degrees 51%). The fuel thread's own reading agrees: start time anywhere 0-12 h
before the first alert, start place within ~640 m of the first footprint, speed not identifiable. So the start point is a prior box, not a
direction cue, and the leaky full-pass fit (21% above) must not be used as a forecast input. Start-time and start-point work now sits
with this thread.

**Does the learned footprint read the direction?** (`foot_score_dir_*`, `direction_learned.json`; the polygon-trained 4i model, first pass
only, 1,213 fires, of which 768 with a polygon run of 300 m or more.) Its bearing from the first-pass centroid to the centroid of its
forecast footprint is within 45 degrees of the real run in **55.5%** of those fires (within 90 degrees 78%), against 36.8% for the
equal-area circle and 36.6% for the physics restart (random 25%). It gets better the farther the fire ran: 54% for runs of 300-800 m, 61%
for 800-1,500 m, 67% beyond 1,500 m (18 fires). At its own expected area the figure is 50%. *Honest retrain (audit item 2;
`direction_learned_honest.json`, from the honest `foot_score_grown2_*`):* within 45 degrees in 51.8% of the 768 fires (within 90 degrees
78.5%) against 30.9% for the circle and 32.0% for the physics; 49% for runs of 300-800 m, 61% for 800-1,500 m, 72% beyond 1,500 m; at
its own area 47%; run length still cautious (median 167 m against 550 m real, correlation 0.23). The leaked earlier-burn pixels were
worth about 4 points of bearing, so part of the "away from earlier burns" cue in the table above was hindsight. So the model does combine the weak single cues
of the table above (fuel ahead, earlier burns and villages behind, dryness) into a usable direction more often than not, which is where its
0.517-against-0.463 shape gain comes from (0.502 against 0.454 after the honest retrain, see the next paragraph); but it is cautious about the length of the run (median 180 m against 400 m real, correlation
0.22): it leans the right way without committing to how far. The first-to-second-pass move (63%) is still the best single cue once a second
pass exists, and the learned restart carries it.

### 4m. Barriers from the FSI thread: leaky roads, streams and the fires' own edges (`prep_barriers2.py`, `barrier_phys.py`, `footprint.py` with `BARRIERS=1`, Oct 15)

**What arrived.** The FSI scouting thread (`ratapani/fsi/scouting/fire_barrier_maps.md`) could reach no fire-line map (the department's GIS
resets, Van Agni is blocked by the proxy, FSI has no map service). It built the best open layer instead, `scouting/data/barriers_ratapani.geojson`,
and measured on 3,640 event scars how often each kind of line holds a fire that reaches it, against the same lines shifted 300-1,000 m
("stop probability"; the second number is for fires that started more than 1 km from the line, which rules out roadside ignitions):

| Line | Stop probability, all fires | started > 1 km away | km in the model box |
|---|---|---|---|
| OSM roads | 0.69 | 0.78 | 1,274 |
| Railway | 0.75 | 0.76 | 182 |
| Microsoft roads >= 10 m | 0.47 | 0.68 | 1,082 |
| Microsoft roads 7-10 m | 0.30 | 0.47 | 575 |
| TomTom roads | 0.26 | 0.59 | 813 |
| DEM stream, catchment >= 25 km2 | 0.72 | 0.83 | 373 |
| DEM stream, 5-25 km2 | 0.45 | 0.56 | 515 |
| DEM stream, 1-5 km2 | 0.29 | 0.31 | 885 |
| DEM stream, 0.25-1 km2 | 0.20 | 0.20 | 2,704 |
| Power lines, ridges | 0.00 | 0.13 / 0.00 | 191 |

Roads were crossed in 39% of contacts, so they are leaky, not walls; small streams hold in January-February (0.68) and hardly after
(0.3). Earlier scars of the same season stop later fires (edge enrichment 1.29x), but the research thread's season burn maps must not be
used for that: they miss 66% of the event-scar pixels (the same undercount as 4k). Pixels that were an in-forest scar edge in 5 or more of
10 seasons form a 1,160 km network (1.43 km/km2, about the fire-line density MP budgets imply) that predicts held-out scar edges better
than any mapped line (1.33x, 1.95x for edges running along it) but holds weakly (0.19): a zone of frequent stopping, not a barrier. At least
~80% of scar edge is more than 30 m from any mapped line, so most of the shape still comes from fuel and burning conditions.

**What we did with it.** `prep_barriers2.py` puts the layer on the 20 m grid (`data/barriers2.npz`): a segment id and the two stop
probabilities per segment, the highest stop probability of the lines through each pixel, road / big-stream / small-stream masks, and, per
held-out season, the recurrent-edge counts rebuilt from `event_scars.geojson` using the other nine seasons only (the layer's own
`recurrent_scar_edge` class is built from all ten seasons and would leak), plus the earliest alert day of any event polygon covering the
pixel ("burned earlier this season" from the polygons rather than the rasters). Two tests, both on the polygon truth of 4k:

1. *Learned footprint + barrier features* (`BARRIERS=1`, models `foot_models_bar/`, scores `foot_score_bar_*`): sixteen features added to the
   4i set: stop probability at the pixel and compounded over the distinct lines that a straight path from the nearest first-pass detection
   crosses (`pstop_path`, `pstop_max_path`, `n_cross`), recurrent-edge count and ratio at the pixel and along the path, distances to the nearest
   big stream and any road, distance to and crossing of ground burned earlier this season by the polygons.
2. *Physics with leaky lines* (`barrier_phys.py`, `barrier_phys_*`): the 3.0 t/ha bed with (a) no barriers, (b) Microsoft roads as walls (the
   model so far), (c) every segment whose far-fire stop probability is >= 0.5 as a wall (OSM and TomTom roads, roads >= 10 m, rail, streams
   >= 5 km2), (d) every mapped line as a wall, (e) three random draws in which each segment holds with its own probability, pixels ranked by
   their mean arrival time, (f) as (b) plus the polygons' earlier same-season burns as consumed fuel. Scored at the polygon's area (shape
   only), as a free run at 26 h and 48 h, and on later-pass hits.
3. *The department's own line types* (FSI thread addendum, Oct 15 12:00Z, `fsi/scouting/data/admin_lines/`): Akkshay listed compartment
   lines, district lines, range and beat boundaries, roads and railways. The FSI thread drew division (for district), range and beat
   boundaries from the MP beat map and measured them with its 60 m hold test: stop 0.16, 0.14 and 0.08 (roads 0.37 and rail 0.75 in the same
   run), and scar edges only 1.0-1.2x enriched within 30 m of them, i.e. almost random lines. They are in the layer as weak barriers with
   those values (168 division parts, 232 km; 64 range, 128 km; 624 beat, 706 km), so they enter the footprint's path features and the
   physics variants (d) and (e); (c) ignores them. No compartment map exists, so the recurrent-edge network stays the stand-in for the
   working-plan fire lines. Note that the recurrent-edge counts for a season come from the other nine seasons' polygons (2017-2026, later
   ones included), the same hindsight as leave-one-season-out training; they are off in the forward test of 4s.

4. *Deciduous cover against open ground* (FSI thread, Oct 16, Akkshay's idea; `fsi/scouting/mahua_and_deciduous_checks.md`): on the v1
   outlines, 40 m inside the edge is 66.4% deciduous tree cover against 61.7% just outside (shifted-outline null 61.2 vs 61.3), and open
   grass or low cover 23.7% against 28.5% (null 28.8 vs 28.8); green-in-dry-season trees and this week's leaf-fall fraction make no
   difference. So fires stay in deciduous tree cover and tend to stop where it gives way to open ground (caveat: grass scars may show less
   in Sentinel-2). It holds on scar outlines v2 (65.7 vs 60.4% deciduous; open 23.6 vs 29.0%; nulls flat). Next test after the queue: open grass/low cover as a weak barrier in the physics, and the cover class at the pixel and
   along the path in the learned footprint (it already has WorldCover class and forest share, which carry part of this).
   FSI follow-up (`fsi/scouting/grass_fuel_load.md`): open grass burns at 2x the deciduous rate before ~15 Feb and ~0.7x after (already
   85-97% cured in Feb), so the test gives it a date-dependent weight: carrier before 15 Feb, weak barrier after (GR1/GR2 0.9/2.5 t/ha if
   physics needs a grass bed).

5. *Other water layers* (Earth Engine dataset thread, low priority): MERIT Hydro or JRC Global Surface Water. The stream classes here are
   already DEM-derived by catchment, not OSM; JRC surface water would add ponds and reservoirs as hard stops. Needs an Earth Engine export,
   so it waits until the barrier runs show whether streams matter at all.

**Results.** (pending: queue 25/26)

**Barrier results (Oct 17; 1,214 fires, outlines v1; `barrier_phys_*`, `foot_score_bar_*`; fire bootstrap 95% ranges).**

Physics, compared with no barriers (shape score at the outline's area; free-run score at 26 h):

| Barrier rule | Shape | At 26 h | Ranking (AUC) |
|---|---|---|---|
| Microsoft roads hard (current) | +0.001 (0 to +0.003) | +0.002 | -0.002 |
| Lines that stop >= 50% of far fires hard | +0.001 | +0.002 | -0.005 |
| Every mapped line hard (incl. admin lines) | **-0.024** (-0.030 to -0.019) | -0.011 | -0.062 |
| Each line holds with its own chance | +0.003 (0 to +0.005) | 0.000 | -0.002 |
| Roads + ground burned earlier this season as no fuel | **+0.024** (+0.020 to +0.028) | +0.022 | 0.000 |
| Roads + wind (ERA5-Land) | -0.008 (-0.013 to -0.002) | **-0.031** | +0.022 |

So mapped lines barely change physics. Making every line a wall hurts. Wind makes the free run worse again (it blows fires 2x too big at
48 h) although it ranks pixels slightly better. Treating ground burned earlier this season as no fuel is the one helpful rule (+0.024).
That rule uses the day each earlier outline became known, minus 2 days. Part of the gain may come from how outlines are drawn: a new
outline cannot cover ground that was already black. The big-fire continuity thread found earlier burns did not stop big fires, so
this needs the photo test before it is trusted.

Learned footprint with the barrier inputs: 0.529 vs 0.502 without (+0.027, +0.022 to +0.031), ranking AUC +0.008. The top barrier
inputs are distance to any road, the path's stop chance and the fire's own edge history from other seasons. That edge history
includes later seasons, so I reran without it (`queue34.sh`, `foot_score_bar_norecur_*`): 0.527, still +0.025 (+0.021 to +0.029) over no
barrier inputs. The edge history adds +0.002 (0 to +0.004). The gain comes from distance to any road, the line-crossing stop chance and
known earlier burns this season, all of which are known at forecast time.

**Grid-size sensitivity (audit item 4, Oct 17; `grid_sens.py`, `grid_sens_{20,40,60}_*`; 1,213 fires, first pass, final physics).**
Rerunning on 40 m and 60 m blocks barely changes anything: burned area at 26 h 130 / 127 / 126 ha and at 48 h 308 / 305 / 304 ha (20 / 40 /
60 m); per-fire shape scores keep their order (rank correlation 0.97-0.99). Coarser grids score ~0.01-0.015 higher, but the equal-area
circle gains the same (0.446 / 0.462 / 0.465), so physics stays level with the circle at every grid size. The 20 m grid is not driving
any result; 40-60 m would run 4-9x faster with no loss.

**Directional ring (Oct 17; `dir_ring.py`, `dir_ring.json`; lead from the big-fires thread).** This uses dots only: 404 looks on 214 VIIRS
fires with 3+ looks. Momentum is the move from all earlier dots to the latest look's new dots (91% of looks have one). Each rule ranks a
40 m lattice, plus a lean toward the momentum whose weight is picked leaving one season out. Next dots caught within 24 h:

| Area | Closest to dots | ...leaning | 600 m ring | ...leaning |
|---|---|---|---|---|
| 25 ha | 16.5% | 19.4% (+2.9, CI +0.6 to +7.5) | 50.0% | 50.0% (weight 0 chosen) |
| 100 ha | 32.0% | 39.6% (+7.6, +1.6 to +10.9) | 58.4% | 58.4% (weight 0 chosen) |
| ~137 ha | 57.7% | 62.8% (+5.1, -0.9 to +7.4) | 75.7% | 75.4% (-0.3, -1.9 to +0.2) |

48 h gives the same picture. Momentum helps the plain distance rule because it pushes that rule outward. It adds nothing to the ring,
which already sits where the next dots land. Momentum is real but already contained in the ring's geometry; the ring stays the
no-learning rule for next dots.

**Fire speed sweep with an honest start (Oct 17; `ros_sweep.py`, `ros_sweep_*`; 1,214 fires; 100 m discs at the first dots, roads, no
wind).** Median over fires, by speed multiplier on the 1.5 t/ha loose litter bed:

| Speed x | Hours to reach the outline's size | Shape at outline size | Free run at 26 h | Free run at 48 h |
|---|---|---|---|---|
| 1 | 27 | 0.37 | 0.31 | 0.39 |
| 1.5 | 24 | 0.43 | 0.38 | 0.39 |
| 2 | 21 | 0.45 | 0.39 | 0.37 |
| 2.5 | 18 | 0.46 | 0.39 | 0.32 |
| 3 | 15 | 0.46 | 0.38 | 0.28 |

The equal-area circle scores 0.457 on shape. x2 stays the best single setting: at 26 h it matches x2.5 and it is safer at 48 h. Physics
never beats the circle on shape. Read the multiplier as a speed calibration only, not as fuel load (the fuel thread withdrew that link).

**Open grass by date (Oct 17; FSI hypothesis: carrier before 15 Feb, weak barrier after; footprint rows, ground 100-800 m from the first
dots, 1,214 fires, outlines v1).** Share of ground that ends up inside the outline:

| Period | Trees | Shrub | Grass | Crop | Grass / trees (fire bootstrap) |
|---|---|---|---|---|---|
| Before 15 Feb (154 fires) | 15% | 23% | 27% | 24% | 1.72 (1.45 to 2.03) |
| 15 Feb-31 Mar (728) | 34% | 33% | 27% | 24% | 0.79 (0.75 to 0.84) |
| April (299) | 38% | 34% | 26% | 17% | 0.70 (0.62 to 0.78) |
| May-June (33) | 26% | 29% | 23% | 10% | 0.88 (0.63 to 1.18) |

The FSI idea holds. Before 15 Feb, grass carries fire 1.7x more than trees; these are mostly planned burns, per Akkshay. In the fire
season, grass burns about a quarter less than trees and crop fields less still. That fits the continuity thread's finding that fire
edges sit where tree cover thins. Two caveats: outlines may miss light burns on open ground, and staff put out fires near villages,
where grass is common. The learned models already have cover type and date as inputs, so they can use this pattern. Physics treats
grass as a fixed fuel; giving it a lower in-season weight is a possible tweak, but physics already only ties the circle.

### 4n-pre. What the fresh spread review (research/spread-review/, Oct 15 16:34Z) changes
- **Burn-count leak check (Oct 16, after the big-fires thread found one in its own features).** No layer here counts the current
  season: `nburn_hist` and `last_burn` loop over seasons before s only (`foot_restart.py` `fire_static`, `footprint.py`), `d_prev` uses
  only this season's burns ended 26+ days before the fire's first day, and the fuel layers `rothermel_season_<Y>` are built from prior
  seasons only (fuel-map/ratapani/scripts/rothermel.py:62). Nothing to fix.
- **Two looks a day.** All three VIIRS satellites pass within ~50 min of each other at ~01:30 and ~13:30, so the 6 h and 12 h horizons below
  mostly contain zero or one new look; a horizon counts only when a look fell in it, which is stated per row.
- **A fairer no-learning baseline: the 600 m ring.** "The next points will be ~600 m from the latest ones" scores 67% against 51% for
  persistence at gaps of 10 h or more in the review's rebuild (same radius picked in every held-out season). It is now a method (`ring`) in
  the fair table and in the calibration, and the learned models are judged against it rather than against persistence. On the review's
  reading about 60% of the learned restart's gain over persistence at long gaps is this geometry; the remaining gain is what dryness and
  landscape add.
- **Shape matters less than the starting place.** A circle of the true size at the true centre scores 0.60 against the outlines; at the first
  VIIRS point 0.42; every model here scores ~0.50. The footprint gains of 4i/4j are real but small against that ceiling.
- **The outline truth has three limits** beyond the 9%/22% error bands: it is dated to a ~10-day image window, a patch counts only if it
  touches a circle around a VIIRS point (so distance-to-alert methods get a head start), and 64-91% of the multi-look fires touch the 3 km
  chip edge (the big fires are clipped). End-footprint differences of ~0.05 are near what this truth can resolve.
- **Physics speed fits sit on the edge of their search grid.** The "7x" speed is not reliable; 20-30 m/h and a start ~3 h before an
  afternoon first alert hold up. Physics is kept for flame size and intensity only.

### 4n. The audit's fair table: every method on the same fires, the same truth and fixed leads (`fair_table.py`, `fair_summary.py`, Oct 15)
Akkshay's external audit (Oct 15) asked for one comparison in which persistence, an equal-area circle, a distance-only learned model,
physics only, the learned footprint, the learned restart and physics plus a learned correction are scored on the same fires, the same
outline truth, at fixed lead times and at several forecast-area budgets including one small enough for a crew to check. Set-up:
- **Fires and issue times.** The multi-satellite fires with a grown outline (the 4j set): a forecast is issued at every VIIRS pass k with
  only the detections up to that pass; the horizons are 6, 12, 24 and 48 h after the pass.
- **Truths.** (a) The detections of any satellite in the next h hours (a hit = forecast pixel within 240 m), counted only when the box
  had at least one overpass in the window; "new ground" = detections more than 400 m from everything known. (b) The final grown outline
  (scar outlines v1, 2026-10-15).
  (c) The fuel thread's mid-fire Sentinel-2/Landsat snapshots of burned-so-far (fuel-map/ratapani/timing/chips, inside the raster scar
  only), where one falls within 48 h of the issue time.
- **Methods.** pers = distance from all known detections (persistence at any area); circ = distance from the latest pass; dist = LightGBM
  on five distances and the lead only; phys = Rothermel restart from every known detection with the 3.0 t/ha bed and roads, ERA5-Land
  HINDCAST weather, no scar snapping, ranked by arrival time; lr = the 4j learned restart with its lead feature set to the horizon;
  lrh = the same features with one head per horizon; lrp = lrh plus the physics arrival time and reach; lfoot = the 4i learned footprint
  from the first pass (polygon-trained), shown at k = 1 and kept unchanged at later passes as a reference. All heads leave-one-season-out.
- **Budgets.** 10, 25, 50, 100 and 200 ha, the persistence area (475 m around the known detections, median ~137 ha) and, for the outline,
  the outline's own area. Intervals are 95% bootstrap intervals over fires (500 draws).

**Results.** (pending: queue 27)


**Results (Oct 16, 737 fires, 2017-24 held out by season, truth scar outlines v1 for the end; `fair_score_*`, `fair_summary.json`,
`fair_vs_ring.json`).** Share of the detections in the next h hours that fall inside the forecast (only steps with a look in the window;
two looks a day, so 12 h is "the next look"), with 95% ranges from resampling whole fires for learned restart minus ring:

| Lead | Area | Persistence | Circle on latest pass | 600 m ring | Physics (hindcast) | Learned restart | Restart minus ring |
|---|---|---|---|---|---|---|---|
| 12 h | 25 ha | 47% | 49% | 47% | 31% | 47% | 0 (-3 to +4) |
| 12 h | ~137 ha (persistence area) | 73% | 76% | 74% | 72% | 84% | +10 (+9 to +12) |
| 24 h | 25 ha | 29% | 30% | 43% | 19% | 40% | **-3 (-5 to -1)** |
| 24 h | ~137 ha | 55% | 59% | 64% | 54% | 75% | +11 (+10 to +12) |
| 24 h | 100 ha | 41% | 44% | 52% | 34% | 62% | +10 (+8 to +12) |
| 48 h | 25 ha | 22% | 23% | 36% | 15% | 34% | **-2 (-4 to 0)** |
| 48 h | ~137 ha | 44% | 49% | 54% | 43% | 64% | +10 (+9 to +12) |

**Mid-fire photos as truth (the review thread's independent check):** the first run's photo scores are void. The fuel thread's chips
index the burn rasters without this grid's 100-pixel pad, so every photo was compared 2 km off (fixed Oct 16 in `fair_table.py`; the
fixed chips sit 86-100% inside the outlines). The photo truth is rescored in queue 32 together with outlines v2, with persistence
("ground closest to any detection") as the baseline the review found hardest to beat on photos. No model is called the winner until then.
The review thread's calibrated distance table (`research/spread-review/HONEST_TESTS.md`: chance a spot is burned by next morning 19% inside
the pixel, 16% at 0-200 m, 13% at 200-300 m, 9% at 300-400 m, 6% at 400-500 m, 3% at 500-700 m, ~1.5% beyond) falls steadily with
distance to the nearest detection, so at a fixed area it picks the same ground as persistence (persistence breaks its within-band ties by
exact distance). Persistence in the photo rescore therefore is that table for every area-budget score; a model counts as better only if it
beats it there.

On new ground only (detections more than 400 m from everything known) at 24 h: restart 69%, ring 58%, persistence 38% at the
persistence area; at 25 ha the ring wins 44% against 38%. At 6 h (mostly the second satellite ~50 min later) every distance method is at
~90% and nothing beats sitting on the latest points.
- **The learned restart beats the 600 m ring by about 10 points whenever the area is 100 ha or more**, at every lead of 12 h and longer,
  with fire-level ranges well clear of zero. So the review's point holds (the ring takes persistence from 55% to 64% at 24 h, about half
  the gap), and the learned model adds another 11 on top.
- **At a crew-sized area (25 ha, about 0.25 km2) the plain ring is as good or slightly better** at 24 and 48 h. The learned model spends
  small budgets on the latest points; the ring spends them where new fire appears. A small-area product should start from the ring.
- The per-horizon heads (lrh) and physics-assisted heads (lrp) score within 1-3 points of the restart; adding the physics arrival time
  does not help. Physics alone is the worst method at every lead and area. The first-pass footprint (lfoot) is below persistence for the
  next looks: it forecasts the final burn, not where fire is now.
- **End footprint** at the outline's own area, issued at the last pass: restart end head 0.515, physics-assisted 0.512, distance-only
  0.478, persistence 0.462, first-pass footprint 0.456, physics 0.446, circle 0.386, ring 0.215 (the ring is a next-look rule, not an
  end rule). Averaged over every issue time: 0.488 / 0.486 / 0.448 / 0.438 / 0.456 / 0.429 / 0.403 / 0.221.

### 4o. Calibrated chances of burning within 12/24/48 h: moved to the review thread (Oct 15 16:44Z)
Akkshay asked the "Fresh critical review of spread model" thread to build the calibrated per-cell burn chances, scored against the 600 m
rule; it writes in `research/spread-review/`. This thread does not build them, to avoid doing it twice. `calib.py` and the fair table's
calibration lattice (`fair_score_*_cal.parquet`) stay available to that thread.

### 4p. Is the fire still going? Stopping, and "no detection" against "fire out" (`stopping.py`, `redetection_gaps.json`, Oct 15)
**How often does a pass miss a fire that is burning?** Measured from the detection record alone (all 2,439 multi-satellite fires): take
every overpass of the box (any satellite that detected something in the box on that pass) that fell between a fire's first and last
detection, i.e. while the fire was certainly still burning. **44% of those passes did not detect the fire** (2,045 passes, 500 fires):
41% by day, 46% at night; 60% for fires whose strongest detection was under 5 MW, 46% for 5-15 MW, 33% for 15-50 MW, 20% above 50 MW;
S-NPP 44%, NOAA-20 43%, NOAA-21 47%. Of the 2,022 re-detections of a fire, 25% came after at least one missed pass, 11% after two, 5% after
three; the median gap between successive detections is 0.85 h (two satellites ~50 min apart) and the 90th percentile 13 h, and 21% of
re-detections came more than 12 h after the previous one. (Gaps beyond about a day cannot appear here because the event clustering
itself would start a new fire, so the long tail is truncated by construction.) So one silent pass says little: a small fire is more likely
to have been missed than to have gone out, and even a strong one is missed one pass in five. Any "fire out" rule must count the passes
missed, the fire's FRP and the time of day, not the silence alone.

**What the FSI thread found on the same question** (`fsi/scouting/fire_stopping_and_tracking.md`, Oct 15 16:18Z; its own code in
`fsi/scouting/code/stopping/`): an "is it still alive" model on all 15,561 in-sanctuary VIIRS detections (season held out) scores AUC
0.796 against 0.679 for "passes since last seen" alone, calibrated within 1-2 points; daily weather adds 0.01. Re-detection after one
silent pass depends on the time of day of the last detection: 40-75% after a night detection (by FRP band), 20-58% after a day one.
Fire durations depend heavily on the grouping rule (1 km / 48 h: 58% single-pass, multi-pass median 12 h; 750 m / 24 h: 62% and 1.7 h),
so every stopping number here states its rule: this thread's fires are S-NPP, NOAA-20, NOAA-21 and MODIS detections linked within 1.2 km
and 30 h. Weather is weak for stopping (next-day RH AUC 0.57; next-day rain cuts re-detection from 49 to 31%); fuel running out ends
most fires. Its suggested states, after NASA's FEDS: active, "sleeper" after about 12 h without a detection, dead after 48 h; in this
thread's record 21% of re-detections come after a silence of more than 12 h and 1.5% after more than 24 h (truncated by the 30 h link).
Its recipe for the 6/12/24/48 h maps, P(alive) x "where next" with isotonic calibration per lead, seasons held out, scores in rings
around the fire, results by fire age and the previous-footprint trap, is what 4o follows: the per-lead heads learn P(detection) directly,
and 4o reports them beyond the 475 m persistence ring and by fire age as well.

**"Brighter" and "fainter", not "strong" and "weak" (Akkshay asked, Oct 16 18:04Z).** FRP of a detection is the heat from one 375 m
pixel at one moment; it depends on how much of the pixel burns, viewing angle, canopy and smoke. Against independent measures it says almost
nothing about the fire on the ground: Spearman 0.13 with the scar's burn darkness (rdnbr, 12,202 VIIRS alerts with a scar) and 0.05 with
the scar's area; the first-look FRP of 1,927 fires has 0.09 with the v2/v1 outline area. It does predict whether the next pass sees the
fire again. FRP bands in this README mean brighter or fainter detections, used only for how much a silent pass means.

**People put fires out (Akkshay, Oct 16 17:57Z).** Forest staff extinguish fires soon after an alert, and some fires that never got one.
Check (`suppression_proxy.parquet`, 2,913 fires Feb-Jun 2017-26, distance from the first detection to the nearest road or village/cropland
pixel): fires starting within 250 m of a road or village are seen at only one look 80% of the time, against 75% at 250-750 m and 72% at
0.75-1.5 km; mean looks 1.35 against 1.59; median outline 56 ha against 91 ha. The gap holds inside each FRP band of the first detection.
Only 1% of fires start more than 1.5 km from both. The 2026 season (FSI portal alerts with beat tags from Nov 2025) does not stand out
(74% single-look against 77% in 2017-24). This fits suppression near access, but the same pattern would come from broken, grazed fuel and
crop edges near villages, and this data cannot separate the two. What it changes:
- Every "stop" in this README (barrier stop probabilities, the stopping model, the deciduous-to-grass edge) is "stop, by any cause",
  people included. The FSI road values (0.30-0.78) mix "the road stops fire" with "crews reach the fire from the road".
- For forecasting this is fine: the models learn what fires do under today's patrols. For physics and fuel it is not: stopping and size
  cannot be read as fuel or barrier effects, which is one more reason the physics speed and fuel fits are not identifiable.
- Small fires put out early may leave no VIIRS detection and no scar at all, so the fire set under-counts them near villages.
- A clean test needs the department's suppression record (which fires were attended, when) or FSI alert-to-visit times; the field app's
  logged visits would give it from 2027.

Outside Ratapani (FSI thread, all-MP forest types): bamboo and sal fires are seen at night 35-51% of the time against 25% for dry mixed
forest, with fainter detections (2.8-3.7 MW against ~5), so any sleeper/dead timing carried to those forests should be longer.

(stopping model: pending the fair table rows)

### 4q. Grid size: 20 m against 40 m and 60 m (`grid_sens.py`, Oct 15)
(pending: queue 28)

### 4r. Wind by regime (`wind_regime.py`, `barrier_phys.py` variant `ms_wind`, Oct 15)
(pending: queue 26)

### 4s. Forward test: models frozen on 2017-24, scored once on the 2025 and 2026 fires (`events_multi.py`, `grown_multi.py`, `queue31.sh`, Oct 15)
The audit's item 5. Everything above is leave-one-season-out on 2017-24: the model for a season never saw that season, but the features
and settings were chosen looking at all eight. The forward test removes that: every head (restart next and end, the fair table's distance
and learned heads, the footprint) is fitted once on all of 2017-24 (the `*_all.txt` models), then scored on the 2025 and 2026 seasons,
which nothing in this thread had used before. Set-up:
- **Fires.** The 4j event builder on the 2025 and 2026 alert files (S-NPP, NOAA-20, NOAA-21, MODIS; 1.2 km / 30 h linkage): 705 fires
  (379 in 2025, 326 in 2026). The 2026 files are near-real-time exports without scan and track; the MODIS 2026 rows carry no time and
  are dropped.
- **Truth.** The scar thread's grown outlines (v1, 2026-10-15) matched through the S-NPP detections, the rule of the 2017-24 store (`grown_multi.py`
  rebuilds that store pixel for pixel): 379 fires have an outline (219 in 2025, 160 in 2026), 236 of them with two or more passes, which
  is the restart's and the fair table's set. Matching through NOAA-20 and MODIS detections as well would give 527 (`grown_scars_2526_all.pkl`,
  unused).
- **Inputs.** The fuel thread's loose-bed layers for 2025 and 2026, the pipeline's lean dryness scores for 2025-26 (its frozen model,
  Feb-Jun, the same 3,607 cells), ERA5-Land hindcast hours, the burn rasters' earlier-burn days under the honest rule. No barrier features.
  No mid-fire snapshots exist for 2025-26, so that truth is absent.
- **Scores.** The 4j next-pass and end scores (`lrg_score_2526_*`) and the whole fair table (`fair_score_2526_*`); the calibration of 4o
  is fitted on the 2017-24 held-out predictions only and applied to 2025-26; the stopping model of 4p is fitted on 2017-24 only.
**Results (Oct 16, 236 fires: 136 in 2025, 100 in 2026; models frozen on 2017-24; outlines v1; `fair_score_2526_*`,
`fair_vs_ring_2526.json`).** The 2017-24 ordering holds on seasons nothing here had seen:

| Lead | Area | Persistence | 600 m ring | Physics (hindcast) | Learned restart | Restart minus ring |
|---|---|---|---|---|---|---|
| 24 h | 25 ha | 29% | 41% | 18% | 40% | -1 (-5 to +2) |
| 24 h | ~137 ha | 58% | 64% | 57% | 77% | +12 (+10 to +15) |
| 24 h | 100 ha | 41% | 49% | 33% | 62% | +13 (+11 to +16) |
| 48 h | 25 ha | 21% | 32% | 13% | 31% | -1 (-4 to +2) |
| 48 h | ~137 ha | 43% | 52% | 43% | 63% | +12 (+9 to +14) |

End footprint at the outline's area from the last pass: restart 0.522, physics-assisted 0.520, distance-only 0.484, persistence 0.457,
first-pass footprint 0.449, physics 0.437. So the restart's lead over the ring at 100 ha and more is not a product of tuning on 2017-24;
at a crew-sized 25 ha the ring and the restart tie. The photo truth is absent for 2025-26 (no mid-fire chips).

### 4t. Rescore on mid-fire photos (chip offset fixed) and scar outlines v2 (Oct 16, `fair_score_v2_*`, `fair_score_2526_v2_*`)
**Photos (independent of the fire dots).** 150 Sentinel-2/Landsat scenes on 142 fires 2017-24, median 21 h after the forecast. Truth =
ground burned by photo time inside the photo's clear area (this includes ground already burned at forecast time). Share of it caught:

| Area | Stays where seen | Physics | Learned footprint | Circle | Learned restart | 600 m ring |
|---|---|---|---|---|---|---|
| 25 ha | 10.3% | 10.7% | 12.1% | 9.2% | 4.9% | 3.2% |
| 100 ha | 32.0% | 32.4% | 33.1% | 27.5% | 17.3% | 12.7% |
| ~137 ha (persistence area) | 61.6% | 60.1% | 56.1% | 51.1% | 38.1% | 33.8% |

Fire-level bootstrap at the persistence area, minus persistence: physics -1.4 (-3.0 to +0.1), learned footprint -5.4 (-8.4 to -2.4),
learned restart -23.8 (-31 to -17), ring -28 (-35 to -21). At 25 ha the learned footprint is +1.8 (+0.8 to +3.1) over persistence.
**So the learned restart and the ring, which win at predicting where the next satellite dots appear (4n, 4s), lose badly on what the
ground actually looks like.** They push the forecast out to where new dots tend to show up and leave out the ground beside the dots that is
burning. For "which ground is burned by tomorrow", the closest-to-dots rule (and the review's distance table) is the honest answer,
matching research/spread-review/HONEST_TESTS.md. No model here beats it by more than a point or two. The photo truth counts ground burned
before the forecast too, which favours persistence; the new-ground score below removes that.

**New ground only (Oct 17, `fair_snap_*`, `SNAP_ONLY=1`; 138 photos on 133 fires).** Truth = photo-burned ground more than 450 m from every
dot known at forecast time; each method ranks only that ground. Share caught:

| Area | Closest to dots | Physics | Learned footprint | 600 m ring | Learned restart | Learned restart + lead time |
|---|---|---|---|---|---|---|
| 25 ha | 8.1% | 8.3% | 12.0% | 6.0% | 9.7% | 10.7% |
| 100 ha | 25.4% | 24.9% | 29.0% | 23.5% | 30.0% | 30.6% |
| ~137 ha | 46.2% | 43.1% | 41.7% | 45.7% | 53.0% | 56.0% |

Minus closest-to-dots (fire bootstrap): learned restart +4.7 at 100 ha (+0.6 to +8.0), with lead time +5.3 (+2.2 to +8.4); learned
footprint +4.0 at 25 ha (+2.5 to +5.9); ring -1.8 (-4.4 to 0); physics -0.5 (-2.8 to +1.9). The full-photo numbers above reproduced
exactly in this rerun. **Summary:** next to the fire, "closest to the dots" is the answer. Out beyond 450 m, the learned models pick
which ground burns next a few points better than distance alone; physics and the ring do not. This matches the review's 0.82 vs 0.78
on new ground (HONEST_TESTS.md).

**Outlines v2 (end footprint, Sorensen at the persistence area).** 2017-24: learned end 0.417, distance-only 0.391, persistence 0.390,
learned footprint 0.385, physics 0.382, ring 0.220. 2025-26: 0.443 / 0.418 / 0.413 / 0.395 / 0.404 / 0.235. Same order as on v1. The
next-dot scores do not depend on the outlines and are unchanged.

### 4u. Stopping model (Oct 17, `stopping.py`, `stopping.json`; 2,171 steps on 737 fires, LOSO 2017-24)
Question: after a satellite look, will the fire be seen again (any dot), or seen on new ground, within the next 6/12/24/48 h? Fires are
grouped by `events_multi.py` (S-NPP, NOAA-20, NOAA-21 and MODIS dots linked within 1.2 km and 30 h). "Not seen again" means stopped
**for any reason**: burned out, hit a barrier, or put out by forest staff (see the suppression note, 4p). Results do not separate these.

| Within | Seen again (base) | Ranking (AUC) | Better than the base rate (Brier skill) | New ground (base) | AUC | Brier skill |
|---|---|---|---|---|---|---|
| 6 h | 69% | 0.72 | 12% | 33% | 0.57 | -7% (worse than base) |
| 12 h | 61% | 0.74 | 16% | 39% | 0.64 | 4% |
| 24 h | 70% | 0.81 | 24% | 54% | 0.70 | 11% |
| 48 h | 70% | 0.84 | 27% | 56% | 0.72 | 13% |

The strongest inputs are bookkeeping: how many looks so far and hours since the first dot (fires seen at several looks keep going);
then the brightness of the last detection, fuel/cover and wind. **A look that sees nothing is weak evidence of a stop:** while a fire is
still burning (dots before and after), a single satellite misses it 44% of the time (60% under 5 MW, 20% over 50 MW; day 41%, night 46%).
Fires last seen at night are re-seen slightly more often (72% vs 68% at 24 h). Used as a gate on the 24 h forecast, dropping fires with
under 30% chance of being seen again saves 11% of the area and loses 5% of the next dots. Telling which fires will grow onto new ground
is much harder (AUC 0.70 at 24 h, near nothing at 6 h).

### 4v. C-DAC-style fire fronts on the real burn scars (Oct 17; `cdac_fronts.py`, `cdac_fronts/`)
Akkshay asked for burn-scar fronts like C-DAC's, matched with real scars. `cdac_fronts/cdac_fronts_atlas.pdf` has one page for each of the
146 big fires, the same set and order as the big-fires atlas. **Left:** the C-DAC-style forecast. It is our physics (speed x2, roads,
no wind, hindcast ERA5-Land) started from the first VIIRS look only, with the ground burned by +6/12/24/48 h shaded. **Right:** what
really happened. This is the fire-continuity thread's blend map inside the scar outline v2, using every VIIRS look, shaded with the
same hours. The red line on both is the real scar. Scores are in `cdac_fronts_scores.csv`.

Overlap between the forecast and the real burned ground, median over 146 fires (1 = perfect): at 12 h 0.51, at 24 h 0.44, at 48 h
0.43. The 48 h forecast against the whole scar scores 0.40 and covers 40% of it. At 24 h the forecast is about the right size (median
0.93x real); at 48 h it is too big (1.4x) and in the wrong places. 36% of fires reach 0.5 or more at 24 h and 12% stay below 0.2. The
forecast cannot catch the new fronts that appear 1 km+ away on later days, which 60% of big fires have. Caveats: the "real" timing
inside the scar is itself rebuilt from the satellite looks (84% right on photos), and physics on the same fires only ties a plain
circle (4b, 4n).

### 4w. Unseen-fire validation of the front forecast (Oct 17; full report unseen_validation/README.md)
On 818 fires outside the 146 (2,246 forecasts), the 146-fire growth model over-forecasts 2.5x (12x under 50 ha) and its stop chance
is badly calibrated. Retrained on all fires with each season held out, the stop chance is honest (said 12/29/51/69/86%, happened
3/29/52/64/80%; AUC 0.80). The 24 h map does not improve: unseen overlap ~0.47, and "dots + 24 ha per active front" (0.477) matches
or beats the tool. New-front placement inside a fire is still distance only (39% vs model 36%). Corrections: per-front growth within
2x is 39% (not 70%; scoring bug); demo area mismatch fixed.

## 5. Example maps (`examples/fire_<season>_<event>.png`, C-DAC layout)
Left: hillshade, roads (black), non-forest (blue), the forecast isochrones from the first detection (6/12/24/48 h), the
mapped scar outline and every VIIRS pass. Middle and right: Sentinel-2 false colour before and after the fire with the
forecast burnt area to last detection + 12 h (yellow), the scar (dashed) and the detections.
All six maps use the final model (loose teak-litter bed, leaf fall by date, ROS x2, roads as barriers, no wind).

| Figure | Fire | What it shows |
|---|---|---|
| `fire_2019_830.png` | 5 Apr 2019, 13 detections on 4 passes, scar 360 ha | The best case. Forecast to last pass + 12 h 479 ha covers the main burn north of the road (Sorensen 0.55, restart 0.55); the fire crossed the road southward on day 2, which neither run does. |
| `fire_2022_1466.png` | 27 Mar 2022, 31 detections on 5 passes, scar 341 ha | The fire ran 3-4 km north-west in a day while the ERA5 wind (1 m/s) blew south-east. The free forecast (216 ha, 0.34) stays at the ignition; restarting from every pass gives 757 ha (0.51). The 1 Apr image shows the whole hill burnt; the scar map is patchy there and 540 ha of it is dated after the event. |
| `fire_2023_1613.png` | 28 Feb 2023, 17 detections on 6 passes, scar 311 ha | Three-day fire along ridges, north-west then south-west, roughly with the ERA5 wind for once. Free 128 ha (0.24), restart 233 ha (0.34). |
| `fire_2019_797.png` | 30 Mar 2019, 28 detections on 6 passes, scar 1,064 ha | A 5 km run north over three days, across a 2.6 m/s wind blowing east. Free forecast 522 ha (0.21) never leaves the south end; restart 961 ha (0.27). The 7 Apr image shows a burn larger than the mapped scar. |
| `fire_2024_1751.png` | 19 Mar 2024, 14 detections on 4 passes, scar 71 ha | Looks like an over-forecast (375 ha against 71 ha mapped), but the 21 Mar image shows burnt ground well beyond the mapped scar. The fire moved east across a southerly wind. |
| `fire_2024_1735.png` | 15 Mar 2024, 20 detections on 7 passes, scar 17 ha | The scar map almost misses this fire (its labels are dated 1-3 weeks late); the 21 Mar image shows the whole hill range burnt, covering the 565 ha forecast. The Sorensen of 0.03 is a label failure, not a model failure. |

Two things the examples make plain. First, the direction a Ratapani fire takes over the next day is not the ERA5
wind direction (four of the six fires moved across or against it), which is why the final model runs without wind and
why restarting from every pass helps more than any physics ingredient. Second, the burn-scar labels under-map or
mis-date some of the biggest fires (2022 patchy, 2024 dated late), so the 2022-24 area ratio of 1.34 overstates the
model's over-forecast; the research thread has been told which fires.

## 6. What this says about a "precise" spread model for Ratapani
1. **Size, yes; shape, not beyond a circle.** The calibrated Rothermel model (loose teak-litter bed, leaf fall by date,
   ROS x2) forecasts burnt area within a factor of about 1.4 on the median fire, and a fire's 24 h growth to the right
   order. Its outline is no better than a circle
   grown over burnable ground, because on Ratapani neither wind nor slope steers the fire in any way we can measure.
2. **What steers the fire is on the map, not in the weather:** fuel continuity (unburnt litter vs this season's earlier
   burns, fields, rock), roads and streams, and the fire lines and beat boundaries the department burns. C-DAC's Sikkim
   examples make the same point in their own way (hand-added habitation and road layers, "saved" areas behind roads).
3. **The restart design is right.** Re-seeding from every pass is cheap for us (seconds) and is where C-DAC is heading
   (slide 24). The missing ingredient is the passes themselves: NOAA-20/21 VIIRS and MODIS, which FSI has and we do not.
4. **C-DAC's fuel numbers do not transfer.** Their forest fuel (6 cm, 0.27 kg/m2) makes closed forest nearly
   non-burnable; here closed teak forest is where the fires are.

## 7. What is still missing, and the next experiments
- **Hypotheses from the big-fire threads to test on all fires (Oct 16; research/big-fires/, research/fire-continuity/).** (a) A ring
  that leans the way new burning last moved (momentum picks the right one of 8 directions 19% vs 12.5% chance; wind and slope add
  nothing). (b) Stopping and barriers: edges sit where tree cover thins (52% vs 64% trees) and on slightly lower ground (drainage lines);
  ground burned earlier the same season did not stop big fires. (c) Reach: ~40% of each look's new burning is beyond 600 m of anything
  burned before and 60% of big fires show fronts >1 km apart, so the ring's single radius caps what it can catch.
- ~~NOAA-20/21 would double the passes (every ~6 h)~~ **Wrong (spread review, Oct 15):** NOAA-20 and NOAA-21 pass 25-50 min after
  S-NPP, so Ratapani still gets two looks a day (~01:30 and ~13:30 IST). The extra satellites add second looks at the same times (a
  silent first look is less often final), not new times of day. Their detections are in use since 4j.
- **Fire lines and this year's controlled burns** are unmapped (MP burns ~1.5 km of 6-12 m lines per km2); Sentinel-2
  early-season (Dec-Jan) burn detection at 10 m could map them as barriers.
- **Streams, reservoirs and villages** as barriers (we only have roads): WorldCover water and built classes are already
  non-fuel; the dry stream beds are not.
- **FSI large-fire durations** could set a fire's stopping time instead of "last detection + 12 h".
- **Van Agni / FSI large-fire outlines** (if FSI shares them) would give a second, independent scar set.
- **Spread-day yes/no instead of rate** (Wang 2014 calls 240 m or more of progression a spread day; our litter fronts
  straddle that), and **a probability-of-burning-within-1-2-days output** per cell (Canada's FireSTARR) rather than one
  perimeter, which also fits Akkshay's ask for calibrated chances. The restart test's persistence row says the data for
  this is there.
- **Learned front correction** on top of the physics (section 4c) gains 0.03 Sorensen; worth revisiting once fire
  lines and more passes exist, not before.

**Oct 15 additions to the list.**
- The scar thread is re-drawing all ~5,300 historic scars grown to the next clear image (median 62 → 84 ha; the added ground is
  real burn 86% of the time). The footprint model (4i) trains and scores on the research thread's burn-label rasters, which
  date scars by window; when the grown outlines land in a raster form, retrain and rescore on them, since a model trained on
  outlines drawn too small will under-call the far side of the run.
- The fuel thread's timing work (fuel-map/ratapani/timing/) shows the VIIRS point lags the true front by ~380 m and the far edge
  of the pixel footprint is unbiased; a footprint-ignition test for free runs and restarts is in 4d. A joint back-fit of
  ignition point and time per fire (fuel thread's observation set + this engine's `engine.arrival`) is agreed and starts when
  Akkshay confirms; the engine and data files are shared in `data_shared/` (set `SPREAD_DATA`).
