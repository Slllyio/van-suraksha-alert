# Where and when each burn started: ignition points from scars and fire detections (scouting round 10, topic "ignition", 15 Oct 2026)

For the 2-day prediction and "Rethink the 2-day question" threads, which need to tell new ignitions from spread and currently use crude rules (for example "no burn within 1 km in the previous week"). This note builds on `burn_dating_validation.md` (Andela 2019, Parks 2014 and Benali 2016 are already read in full there and are not repeated in full here), `spread_from_active_fire.md`, `cold_start_cells.md`, `fire_barrier_maps.md`, `daily_scar_dating.md` and `fire-alert-scars/README.md`.

Outputs:
- `data/ignition_points.csv`: one row per event scar (5,669 rows; 5,645 with detections), with the estimated ignition point, time and uncertainty, a one-or-several-ignitions flag, and a scar-based "first day of fire / later day of fire" role for each event.
- `code/ignition/`: `prep.py` (link detections to scars), `ign.py` (estimators), `run.py` (all scars), `final.py` (table), `valaf.py` (real-data check), `synth.py` + `synth_summary.py` (synthetic check), `dist.py` (roads, streams, villages against random points), `crude_check.py`.

Marks: **FULL** = whole text read; **PARTIAL** = the method and results sections read; **ABSTRACT ONLY**. My own reasoning is marked [inference].

---

## Headline findings

1. **The scar-based split of new fire against continuing fire differs from the crude rule for about a quarter of events.**
   - I grouped events whose scars overlap and share the same earliest detection: 5,645 events collapse to 4,215 fires.
   - 4,249 events (75%) fall on the day their fire was first seen. 1,396 (25%) are a later day of a fire that was already burning.
   - The crude rule (no FIRMS point within 1 km in the previous 7 days, checked at the event's own point and time) calls 40% of events "spread". It disagrees with the scar-based role in 26% of events:
     - It calls 1,158 of 4,233 first-day events (27%) "spread".
     - It calls 284 of 1,387 later-day events (20%) "new".
   - Look at the first-day events the crude rule calls spread. Only 20% have an earlier detection within 200 m of the scar in the previous 48 h, which could be spread across an image gap. The median earlier detection is 260 m outside the scar and 48 h older, so most of these are separate nearby fires [inference].
2. **About half of ignitions lie inside the first-detected pixel, and no more.** Three independent routes give the same answer:
   - **Real data.** 483 scars have a Sentinel-2/Landsat fire pixel (20-30 m, about 10:45 IST) seen before the first FIRMS point, a median 2.5 h earlier. Only 54% of those fire pixels lie inside the first FIRMS footprint (63% when the FIRMS point is on the same day). The fire was already burning there before VIIRS saw it. The ignition lies further back again, so it falls inside the first pixel at most about this often [inference].
   - **Synthetic test.** I grew fires from known points across 460 real scar shapes and sampled them with the real overpass schedule. The truth fell inside the first-pass footprint 53-54% of the time.
   - **The production posterior.** Its mean P(inside first footprint) is 0.54 over all scars. It is well calibrated in the synthetic test: predicted 0.2 / 0.34 / 0.55 / 0.86, observed 0.20 / 0.34 / 0.55 / 0.86.
3. **Ignition time is better than the "first detection" rule, but only by hours.**
   - The posterior median ignition is a median 3.5 h before the first detection (10th-90th percentile 1.5-13 h). The 90% interval is a median 8 h wide.
   - In the synthetic test the time error is 1.5 h median absolute, against 4.1 h for taking the first-detection time. The 90% intervals cover the truth 80% of the time.
   - On real data, the 10:45 fire pixel falls after the posterior's 5% ignition time in 83% of cases.
4. **Location is only 300-400 m good, whatever the method.**
   - **Synthetic median error:** first-detection centroid 299 m; footprint ∩ scar centroid (Benali) 235 m; kinematic posterior 200 m; random point in the scar 595 m.
   - **Real data:** all three estimators sit 350-375 m (median) from the earlier fire pixel. The kinematic estimator is closer than the plain first detection only 52% of the time. The synthetic gain does not carry over to real data.
   - **The stated radii are over-confident.** The synthetic R90 covers 73% and the real-data proxy 40%. The table therefore carries `ign_r90_cal_m` = 2.8 × R90 (median 808 m).
5. **Estimated ignitions are not closer to roads, streams, villages or barrier lines than random points in the same scars.**
   - Median distances (estimate against random in-scar points): roads 1,124 vs 1,105 m; streams 243 vs 234 m; cropland 513 vs 512 m; nearest building (Open Buildings `d_ob`) 1,885 vs 1,905 m. The estimates are the same or slightly further.
   - The share within 300 m of a road is 10.3% vs 11.3%. Of streams it is 61% vs 64%.
   - The estimates sit further from the outer scar edge than random points (106 vs 78 m), and the first-pixel centroid does the same. This is an estimator artefact: estimators average towards the middle of the scar [inference].
   - With 300-800 m position error, a road or path effect inside a 50 ha scar cannot be seen. The 500 m-cell ignition model in `research/ratapani-ignition/` is already at the finest scale these data support.
6. **Telling one ignition from several merged ones is weak from detections alone.**
   - The table flag combines three tests: a kinematic test (fronts slower than 60 m per burning hour cannot link the detections), a misfit test (the best single-ignition fit leaves at least 2 detections more than 3 h off) and the rival-fire seeds from `split_scars.py`.
   - Results: 3,908 likely single (69%), 1,315 possibly merged (23%), 422 likely merged (7%). Later-day events are flagged far more often: 19% likely merged against 4% for first-day events.
   - In the synthetic test the detection-only tests flag 19% of true two-ignition scars and 15% of single ones. That is almost no discrimination. Treat `ignitions_flag` as "evidence of complexity", not as a count.
7. **A data-convention problem the dating code should fix.** The "pre" image is not a hard lower bound on ignition: 93% of the fire pixels seen before the first FIRMS point are on the scar's own pre image. The fire was already burning at the 10:45 look, but no scar showed yet. The estimator now allows ignition up to 8 h before the pre look, at a penalty. Before this fix, 86% of real cases were inconsistent.

---

## Part A. Our own tests (DATA, computed 15 Oct 2026)

### A1. Inputs and linking (`prep.py`)

- **Scars.** `fire-alert-scars/event_scars.geojson`: 5,669 grown scars, median 61 ha. The window runs from the `pre_date` look (taken as 05:15 UTC) to the `post_date` look.
- **FIRMS points.** The raw files in `fire-alert-scars/alerts/`: S-NPP, NOAA-20 and MODIS 2017-2026, plus NOAA-21 2024-2026, which is missing from `alert_scar_lookup.csv`. Vegetation type only.
  - Each point is made a footprint rectangle of scan × track: VIIRS half-size about 190-300 m, MODIS about 500-1,000 m.
  - 2026 Earth Engine rows lack scan/track, so they get 0.45 × 0.42 km (VIIRS) and 1.2 × 1.1 km (MODIS).
- **Fire pixels.** `out/af/af_pixels_clean.csv` (Sentinel-2/Landsat 20-30 m) are used as tiny footprints.
- **Links.** A detection belongs to a scar when its footprint intersects the scar and its time is in the window. This gives 49,130 links; detections per scar median 4 (IQR 2-10, P90 20). 24 scars have none. All detections are used, not only the event's own same-day alerts, so a multi-day fire's later events see the fire's earlier detections.
- **Pass catalogue.** 6,431 passes. Any FIRMS detection in the box, grouped within 20 minutes per sensor, counts as a pass. Overpasses with no fire anywhere in the box are missed, so the "empty passes" that set the earliest likely start are undercounted [inference].
- **Optical date evidence.**
  - Per 20 m pixel, from `research/ratapani-burn-labels/rasters/burn_<season>.tif` (window start and end day of year):
    - ground first seen unburned after the first detection gets weight 0.15;
    - ground already burned at a look before the first detection gets weight 2.
  - Per 500 m cell, from `soft_dates.csv`: a cell whose narrowed date starts after the first detection's day gets weight 0.2. This applies only when that cell's first-burn window contains the fire.

### A2. Estimators (`ign.py`)

- **E0 "first detection".** The mean point of the earliest pass, where sensors within 1 h count as one pass. This is the rule used by FIRED (mean of first-day pixels) and Shaddy 2025 (mean of first detections).
- **E1 "footprint".** The centroid of (earliest-pass footprints ∩ scar), which is Benali 2016's ignition area. Its median area is 13.3 ha, a median 35% of the scar (IQR 13-65%); Benali got under 33% for about 60% of perimeters. The radius is √(area/π), median 206 m.
- **E2 "kinematic".** A grid posterior over candidate points x (40 m grid, coarser for big scars), ignition time t0 (0.5 h steps, back to 48 h before the first detection) and spread rate v (20-300 m per burning hour; lognormal prior, median 80, from the litter-fire ROS of 30-160 m/h in `fire_behaviour_field_data.md`).
  - **Burning clock.** One hour counts fully from 09:00 to 18:00 IST and 0.3 otherwise.
  - **Consistency rule.** A detection at time t_i is consistent if the front has reached the nearest part of the footprint and has not passed its far edge more than 2 h earlier. Misses are scored as Gaussian errors with σ 0.75 h.
  - **Ignition-hour prior.** 85% N(11:00 IST, 2.5 h) plus 15% flat, from the GK2A curve in `geostationary_fire_timing.md`: activity starts at 08:00-09:00 IST and peaks at 11:30-13:30.
  - **Empty passes.** Every pass between t0 and the first detection multiplies by (1 − 0.35), the Haley/Farguell 2018 idea that non-detections carry information.
  - **Pre look.** A t0 before the pre look is allowed at ×0.3 (finding 7).
  - **Simplification.** Distances are straight-line, not around unburned gaps.
  - **Outputs.** Posterior-mean point snapped into the scar, MAP point, R50/R90 radii, P(inside first footprint), median and 5-95% ignition time, median v, worst residual.
- **Minimum number of ignitions** (`min_ignitions`). Detections are linked when a front at ≤ vmax per burning hour could join their footprints. Same-pass pixels are linked when a fire lit after the last empty pass could reach both. Run at vmax 150 (the measured upper ROS) and at vmax 60.

Run time: 1 min 48 s for all 5,669 scars on 4 cores.

### A3. Per-scar results (`data/ignition_points.csv`, 5,645 scars with detections)

| Quantity | Median | IQR or other |
|---|---|---|
| Detections per scar (cap 60) | 4 | 2-10; 23% have only one |
| Detections in the earliest pass | 2 | 44% have one |
| Days with detections | 1 | 56% one day, 22% two, 10% three |
| First sensor | S-NPP 43%, NOAA-20 32%, MODIS 9%, S2 fire pixel 9%, NOAA-21 7% | |
| First detection, IST hour | 13:00-14:59 for 48%; 01:00-02:59 for 22%; 10:00-11:59 (Terra / S2) for 13% | |
| Ignition before first detection | 3.5 h | P10 1.5 h, P90 13 h |
| Width of the 90% ignition-time interval | 8 h | IQR 5.5-15.5 h |
| R50 / R90 / calibrated R90 | 165 / 288 / 808 m | |
| P(inside first-pass footprint) | 0.59 (mean 0.54) | VIIRS S-NPP 0.54, NOAA-20 0.59, MODIS 0.71 (bigger pixel) |
| Spread rate fitted, per burning hour | 65 m | IQR 45-95 m |

- The posterior ignition hours pile up at 08:00-11:59 IST (57%). This largely restates the hour prior, so it is not an independent finding [inference].
- The fitted spread rate is mostly the prior too. Per-scar v is weakly identified.

### A4. Real-data check against earlier Sentinel-2/Landsat fire pixels (`valaf.py`, estimators run on FIRMS only)

| Measure (n = 483 scars) | Value |
|---|---|
| Lag from fire pixel to first FIRMS point | median 2.5 h (IQR 2.2-3.0); 84% same day |
| Fire pixel inside first FIRMS footprint | 54.2% (same-day subset, n = 404: 62.9%) |
| Fire pixel within E1 radius | 39.1% |
| Distance estimate → fire pixel, median (P75) | E0 360 (581) m; E1 351 (594) m; E2 374 (623) m; E2 MAP 409 (642) m |
| E2 closer than E0 | 51.6% |
| Fire pixel within E2 R50 / R90 | 14.7% / 39.8% |
| Fire pixel after E2's 5% ignition time | 82.6% (14.1% before the pre-look fix) |

- The fire pixel is the front at about 10:45 IST, not the ignition. So these distances mix estimator error with real spread. Even so, they set the real-world scale of error at about 350 m [inference].
- The 46% of fire pixels that lie outside the first footprint are partly geolocation error, partly real spread, and partly a second fire inside a merged scar [inference].

### A5. Synthetic check on real scar shapes (`synth.py`, `synth_summary.py`)

**Set-up:**
- 500 real scars of 2-400 ha.
- The true ignition is uniform in the scar, or within 120 m of its edge ("edge" run, 300 scars), at an hour drawn from the prior.
- Spread v is lognormal (median 80 per burning hour) and direction-dependent (eccentricity 0-0.6, so the model is deliberately wrong in shape).
- Passes: S-NPP and NOAA-20 at about 13:30/12:40 and 01:30/00:40 IST, with p_detect 0.35 by day and 0.30 by night. Aqua and Terra at p 0.08-0.12.
- Pixel grids get a random phase and off-nadir stretch, plus 70 m (VIIRS) or 300 m (MODIS) geolocation noise.
- Two-ignition scars add a second fire lit 0-30 h later at least 400 m away.

| Measure | Uniform ignitions (n = 460) | Edge ignitions (n = 281) |
|---|---|---|
| Error E0 / E1 / E2 / E2 MAP / random point, median | 299 / 235 / 200 / 243 / 595 m | 345 / 233 / 200 / 226 / 537 m |
| E2 error P90 | 425 m | 402 m |
| Truth inside first-pass footprint | 53.5% | 53.0% |
| Coverage of R50 / R90 / E1 radius | 40% / 73% / 52% | 38% / 73% / 52% |
| Factor on R90 for 90% coverage | 3.2 | 2.4 |
| Ignition-time error, E2 median absolute (first-detection rule) | 1.5 h (4.1 h) | 1.5 h (4.0 h) |
| 90% time interval coverage | 80% | 80% |
| Two-ignition scars flagged / single scars flagged | 19% / 15% | 17% / 15% |

- E2's error grows with scar size (113 m under 10 ha, 243 m over 100 ha) and with spread rate.
- This test uses my own fire model, so it is optimistic. The real-data check (A4) shows no gain of E2 over E0 [inference].

### A6. Roads, streams, villages, barriers: estimate against random points in the same scar (`dist.py`)

**Method:**
- For each scar, E2, E1 and E0 are compared with 20 random 40 m candidates inside the same scar.
- Each estimate is paired with the scar's random median, and a sign test is run.
- **Lines:**
  - roads: all Microsoft roads from `ms_roads_rata.tsv` plus the road classes in `barriers_ratapani.geojson`;
  - streams: all DEM streams, and those of 1 km² catchment or more;
  - all barrier lines;
  - recurrent scar edges.
- **Settlement and land cover:**
  - WorldCover cropland, built-up and non-forest, by 20 m distance transform;
  - Open Buildings cell features (`d_ob`, `bld4`), cell level.

All scars (n = 5,645; E2):

| Feature | Median, estimate | Median, random | Share of scars where the estimate is closer | Within 300 m: estimate / random |
|---|---|---|---|---|
| Road (any) | 1,124 m | 1,105 m | 0.485 (p 0.03) | 10.3% / 11.3% |
| OSM road | 3,659 m | 3,665 m | 0.49 | 1.5% / 1.5% |
| Stream (any) | 243 m | 234 m | 0.46 (p < 0.001) | 61% / 64% |
| Stream ≥1 km² | 526 m | 518 m | 0.47 | 25% / 27% |
| Any barrier line | 113 m | 103 m | 0.44 | 91% / 92% |
| Cropland (WorldCover) | 513 m | 512 m | 0.50 | 28% / 28% |
| Built-up (WorldCover) | 3,222 m | 3,209 m | 0.50 | 1% / 1% |
| Nearest building (Open Buildings, cell) | 1,885 m | 1,905 m | 0.50 | 1.3% / 1.4% |
| Outer scar edge (holes filled) | 106 m | 78 m | 0.32 | (within 100 m: 47% / 63%) |

- E1 and E0 give the same picture. The well-localised subset (R90 ≤ 300 m, n = 2,907) and the single-ignition subset show no road, stream or settlement effect either. For the well-localised subset the share closer is 0.48-0.52 for every feature.
- **Reading.** Ignitions are not detectably nearer roads or villages than the rest of the scar. The test cannot resolve effects below the ~350 m error. It also cannot test the forest-path network, because paths are not mapped (`access_paths.md`) [inference].

### A7. New fire against continuing fire (`final.py`, `crude_check.py`)

| | Crude rule "new" | Crude rule "spread" | Total |
|---|---|---|---|
| Scar says first day of fire | 3,075 | 1,158 | 4,233 |
| Scar says later day of fire | 284 | 1,103 | 1,387 |

- Agreement is 74%.
- **Caveat.** "First day of fire" means the first day any detection hit this scar's window. A fire that started in the previous optical window, outside this scar, is invisible to it. The 20% of crude-rule disagreements with an earlier detection within 200 m and 48 h are the candidates for this [inference].

---

## Part B. Sources

### B1. Benali, Russo, Sá, Pinto, Price, Koutsias & Pereira 2016, "Determining fire dates and locating ignition points with satellite data", *Remote Sens.* 8:326. https://doi.org/10.3390/rs8040326 **FULL** (re-read §2.4 and the results; summary in `burn_dating_validation.md` §12)

**Ignition rule:**
- The ignition is the first MODIS detection(s) inside the perimeter, represented as an area: the part of the pixel footprint inside the perimeter.
- A detection counts if at least 5% of its footprint overlaps the perimeter.
- Spatial uncertainty is the ignition area as a share of the burnt area.
- Temporal uncertainty is the hours back to the last clear overpass, capped at 72 h.

**Results:**
- Satellite ignitions were mostly **later** than reported.
- 50%, 65% and 81% were within 6, 12 and 24 h.
- About 75% were within 2 km. The mean distance was about **800 m**, and 95% fell between 90 and 2,200 m.
- These are fires over about 200 ha with 1 km MODIS pixels.

**Action.** This is our E1, run at 375 m.
- Our real-data proxy error (about 350 m) is about half of Benali's 800 m. That is plausible for VIIRS against MODIS [inference].
- When MP field registers arrive, validate as Benali did: buffer 2 km, report lag in hours and distance (thread: field alert systems).

### B2. Oom, Silva, Bistinas & Pereira 2016, "Highlighting biome-specific sensitivity of fire size distributions to time-gap parameter using a new algorithm for fire event individuation", *Remote Sens.* 8:663. https://doi.org/10.3390/rs8080663 (CentAUR PDF) **FULL**

**Algorithm (MODIS 1 km active fires, 2003 global; 4,477,192 detections):**
1. Fire patches are 8-connected same-date pixels.
2. A directed graph links adjacent patches whose dates differ by no more than the time gap. Edge weight is the number of adjacent pixel pairs.
3. **A "point of ignition" is any patch with no earlier connected patch.**
4. Every other patch is assigned one earlier parent, at random with probability proportional to edge weight. This traces each patch to a unique ignition.

**Results:**
- Clusters: 2,101,171 with a 2-day gap, 1,900,092 with 8 days, 1,764,628 with 14 days.
- Single-pixel clusters: 65.9%, 62.2% and 59.5% respectively.
- Sensitivity to the gap is largest in African savannas, where "coalescence of flame fronts with distinct ignition locations and dates" is common.

**Action.** The graph of local minima with a probabilistic parent assignment is a clean way to count ignitions inside a merged scar. Run it on the 20 m scar date field once the Sentinel-3 daily dates are attached to sub-areas of a scar (thread: Cleaner fire labels) [inference]. Our detection-only flag cannot do this (A5).

### B3. Balch, St. Denis, Mahood et al. 2020, "FIRED (Fire Events Delineation): an open, flexible algorithm and database of US fire events derived from the MODIS burned area product (2001-2019)", *Remote Sens.* 12:3498. https://doi.org/10.3390/rs12213498 (mdpi-res PDF) **FULL**

**Method:**
- An MCD64A1 space-time cube with a moving 3-D window.
- Parameters were optimised over 225 combinations (1-15 days × 1-15 pixels) against 13,741 MTBS perimeters. The best was **5 pixels (2,315 m) and 11 days**.
- **The ignition point is "the average location of all pixels occurring on the first day of the event"** (Figure 4 caption). This is our E0.

**Results:**
- 3.3 times more events than MTBS.
- Area R² = 0.92 overall, but below 0.6 for fires under 50,000 ha.
- Intra-year reburns were 0.48% of pixels in CONUS, and 5% in the Florida tile.

**Action.** The FIRED ignition is the crudest of our three estimators. Its 11-day and 2.3 km linking is far too coarse for Ratapani's 1-day, 60 ha fires; do not use it to define events. The `fire_group` in our table (overlapping scars with the same first detection) is the local equivalent.

### B4. Kalantar, Ueda & Al-Najjar 2026, "A spatiotemporal evaluation framework for MODIS-derived fire events", *ISPRS Annals* XI-3-2026:151. **PARTIAL** (abstract, introduction and method)

- Evaluates FIRED events and ignitions against MTBS, 2001-2020.
- Mean IoU 0.54, F-score 0.701, overall accuracy 0.77, precision 0.90, **recall 0.57**.
- Cites Andela 2018 duration agreement with MTBS/VIIRS at R² 0.3-0.5.

**Action.** None for Ratapani beyond confirming that burned-area-derived ignitions and dates are moderate even for big US fires.

### B5. Artés, Oom, de Rigo, Durrant, Maianti, Libertà & San-Miguel-Ayanz 2019, "A global wildfire dataset for the analysis of fire regimes and fire behaviour" (GlobFire), *Sci. Data* 6:296. https://doi.org/10.1038/s41597-019-0312-2 **PARTIAL** (method and comparison sections)

- An MCD64A1 graph and R-tree with DBSCAN over minimum distances between burnt patches.
- It explicitly allows **"wildfires with several initial ignition points"**, merging non-contiguous patches such as spotting.
- GlobFire merges more than the Global Fire Atlas, and the Global Fire Atlas splits more than EFFIS.

**Action.** Confirms that "one scar = one ignition" is a choice, not a fact. Keep `ignitions_flag` alongside any per-scar ignition.

### B6. Andela, Morton, Schroeder, Chen, Brando & Randerson 2022, "Tracking and classifying Amazon fire events in near real time", *Science Advances* 8:eabd2713 (PMC9337759 full-text XML). **FULL**

**Method:**
- VIIRS 375 m points are gridded to **0.005° (about 550 m)**, a size chosen "to accommodate typical understory forest fire spread rates of 100 to 400 m day⁻¹".
- The earliest detection is kept per cell.
- The Global Fire Atlas filter is applied "to remove inconsistencies in the estimated burn date within each fire to identify the ignition location".
- A fire may spread into a neighbouring cell for **at most 5 days** after that cell's last detection.

**Results:**
- Every event gets an ignition location, start date and duration.
- About 3,000 understory forest fires gave 12% of detections.
- Against MAAP, 64% of forest fires were correctly typed. More than 95% of detections were correctly typed within a week.

**Action.** This is the closest published analogue to Ratapani's understory litter fires, and its 100-400 m/day matches our 100-430 m/day.
- A 550 m earliest-detection grid is a defensible way to mark "new fire" cells in near real time.
- Use its ≤5-day persistence for linking spread (threads: 2-day prediction, spread).

### B7. Haley, Farguell Caus, Kochanski, Schranz & Mandel 2018, "Data likelihood of active fires satellite detection and applications to ignition estimation and data assimilation", *Advances in Forest Fire Research 2018* (arXiv 1808.03318). **FULL**

**Method:**
- The likelihood of the detection and **non-detection** pattern is a function of fire arrival time.
- Heat release decays with a 2 h time constant.
- Detection is a logistic function of heat fraction (50% at 1% heat, 0.1% false alarms).
- A Gaussian geolocation kernel is used, σ = 2 km for MODIS-scale pixels.
- Ignition is the maximum over a grid of WRF-SFIRE runs.

**Results:**
- Synthetic test: correct place, but ignition time **too early** (t = 20 against a true 30), because earlier ignitions explain the detections more easily.
- Hill experiment: correct place and time from 300 runs.
- **Patch Springs Fire 2013** (1,000 runs on a 10 × 10, 500 m grid × 10 times): the estimate is **nearly 3 km** from the official ignition point.

**Action.** E2 is a cheap analytic version of this (no fire model). It keeps their non-detection factor. Their early-time bias is countered here by the ignition-hour prior and the pre-image penalty.

### B8. Shaddy, Binder, Dasgupta, Qin, Haley, Farguell, Hilburn, Mallia, Kochanski, Mandel & Oberai 2025, "Generative algorithms for wildfire progression reconstruction from multi-modal satellite active fire measurements and terrain height", arXiv 2506.10404 (*Remote Sens.* 18:227, 2026). **FULL**

**Method:**
- A conditional GAN is trained on WRF-SFIRE runs with a synthetic VIIRS observation operator:
  - 375 m box coarsening;
  - 4 passes, each pixel kept with probability 1/2;
  - detection window 6-12 h;
  - ignition-time error U(0, 2 h).
- **Ignition time** is the earliest GOES detection within ±1 h of the reported start, in a 12.8 km domain.
- **Ignition location** is the mean of detections in the first 4 h.

**Results:**
- On 5 US fires, Sørensen-Dice 0.81 (0.85 without Tennant), POD 0.83, FAR 0.20.
- Terrain changed arrival times by less than 30 min in 97% of pixels.

**Action.** The observation-operator recipe is close to my `synth.py`. A geostationary first detection (GK2A, `geostationary_fire_timing.md`) is the missing ingredient that would cut our 8 h ignition-time interval (thread: geo timing / Cleaner fire labels).

### B9. Hackett, de Andrade Moral & Markham 2026, "A method to identify wildfire ignition points and propagation durations from burn scars using genetic algorithms", *Fire Technology* (CC BY). https://doi.org/10.1007/s10694-025-01859-y **ABSTRACT ONLY** (the Springer PDF redirects to a login from this container)

- The Wildfire Source Genetic Algorithm fits ignition points and duration to a burn scar using a forward simulator.
- It was tested on 20 simulated scars.
- **Relative distance error 0 to 1.25 times the scar diameter**, with lower error for larger fires.
- They note that a region enclosed by non-fuel can be reproduced from any point inside it.

**Action.** The scar shape alone hardly fixes the ignition. Detection timing is what carries the information. This is consistent with our E2 gaining only about 100 m over E0 in synthetic tests [inference].

### B10. Taylor, Walsworth & Anderson 2024, "Mapping variable wildfire source areas through inverse modeling", *Fire* 7:454. **PARTIAL** (abstract, introduction)

- Reverses wind, the hourly weather sequence, slope and aspect in Prometheus to grow "source areas" backwards from a community.
- Works "for practical purposes", with caution over non-fuel and complex perimeters.
- Prefers time-evolving models over minimum-travel-time inversion when weather changes.

**Action.** Backward spread is for protection planning, not dating. For our scars a minimum-travel-time back-propagation would be equivalent to E2's distance-over-rate step with fuel and slope costs. Low priority, since terrain hardly mattered in B8 [inference].

### B11. Laurent, Mouillot, Yue, Ciais, Moreno & Nogueira 2018, "FRY, a global database of fire patch functional traits derived from space-borne burned area products", *Sci. Data* 5:180132. **PARTIAL**

- Flood-fill with temporal cut-offs of 3, 5, 9 and 14 days.
- Increasing the cut-off yields larger, longer and more complex patches without changing the main conclusions.
- Patches are grown from seed pixels.
- No ignition point is published.

### B12. Mahood, Lindrooth, Cook & Balch 2022, "Country-level fire perimeter datasets (2001-2021)", *Sci. Data* 9:458. **PARTIAL**

- FIRED per country with `ig_date` and `ig_utm_x/y` columns.
- Notes that the Global Fire Atlas and others "search for local minima to identify various ignition locations".
- I found no India dataset in the text.

### B13. Already read in earlier notes, cross-referenced

- **Andela et al. 2019, Global Fire Atlas, ESSD 11:529. FULL** (`burn_dating_validation.md` §6, `spread_from_active_fire.md` B2):
  - local-minimum ignition filter with 3 iterations, never moving a date beyond the burn-date uncertainty;
  - persistence 4-10 days;
  - "unable to adequately map … small fires (≲100 ha)".
- **Parks 2014, IJWF 23:215. FULL** (`burn_dating_validation.md` §7):
  - the best interpolator is WMD, with 46.1% / 75.8% / 85.8% exact / ±1 / ±2 days;
  - "inappropriate for small fires (≪500 ha)".

### B14. Not obtained

- Archibald & Roy 2009, "Identifying individual fires from satellite-derived burned area data", IGARSS. Closed; no abstract served.
- Archibald, Scholes, Roy, Roberts & Boschetti 2010, IJWF 19:861. Closed.
- Frantz, Stellmes, Röder & Hill 2016, "Fire spread from MODIS burned area data", IJWF 25:1228. Closed. ISPRS 2026 describes it as a multilevel object method that extracts ignition points.
- Sá et al. 2017, RSE 190:302, "Evaluating fire growth simulations using satellite active fire data". Listed as bronze OA, but there was no PDF link.
- Downloaded but not read: Mandel et al. 2018 (arXiv 1804.03995) and Farguell 2022 (arXiv 2204.00686), both on assimilation by the same group as B7.

---

## Datasets

| File | What |
|---|---|
| `data/ignition_points.csv` | One row per event scar. Key columns below. |
| `fire-alert-scars/alerts/viirs-noaa21_*.csv` | NOAA-21 points 2024-2026, used here but absent from `alert_scar_lookup.csv` |
| Scratch (not shared): `scratchpad/r10_*` | Prep pickles, estimator runs (`r10_all.csv`, `r10_firms.csv`), synthetic runs, `r10_dist_points.parquet` |

`ignition_points.csv` columns:

- **Grouping and role:** `fire_group` and `n_events_in_group` (events sharing a scar and first detection); `event_role` (`first_day_of_fire` / `later_day_of_fire`).
- **Detections:** `n_det`, `n_firms`, `n_af`; `first_src`, `first_sensor`; `n_first` (detections in the earliest pass); `n_days`.
- **Times, all IST:** `t_first_ist` (first detection); `t_ign_med_ist`, `t_ign_05_ist`, `t_ign_95_ist` (ignition time); `t_lo_soft_ist` (last pass before the first detection).
- **Kinematic ignition point (E2):** `ign_lat`, `ign_lon`; `ign_r50_m`, `ign_r90_m`; **`ign_r90_cal_m`** (use this one); `p_in_first_fp`.
- **Benali ignition area (E1):** `fp_lat`, `fp_lon`, `fp_r_m`, `fp_area_ha`.
- **First-detection centroid (E0):** `first_det_lat`, `first_det_lon`.
- **Fit diagnostics:** `v_med_m_per_burn_h`, `max_resid_h`, `n_resid_gt2h`, `n_ign_v60`, `n_ign_v150`.
- **Rival fires (from `split_scars.py`):** `split_share_kept`, `n_rival_fires`.
- **Flags:** `merge_evidence` (three digits: kinematic, misfit, rival); `ignitions_flag`; `crude_rule_new`.

Coordinates are WGS84 and times are IST.

---

## Ranked action list (gain and effort are my estimates [inference] unless measured)

| # | Action | Thread that uses it | Evidence | Effort |
|---|---|---|---|---|
| 1 | **Replace the crude "no burn within 1 km in 7 days" new-ignition rule with `event_role` from `ignition_points.csv`** (join on `event_id`). Treat `later_day_of_fire` events as spread and `first_day_of_fire` events as new. The rule disagrees on 26% of events: it calls 27% of first-day fires "spread" and 20% of continuing fires "new". | 2-day prediction; Rethink the 2-day question | A7 (measured) | 1 h |
| 2 | **Change the window convention so a fire can be burning at the "pre" look.** 93% of pre-FIRMS fire pixels sit on the pre image. Let a day-0 afternoon or a pre-image fire pixel count as inside the window, as already done for `window_start` in `true_lead_labels_v2`, and check `af_link.py` / `dated_labels.py` for the same clip. | Cleaner fire labels; 2-day prediction | Finding 7, A4 | 2 h |
| 3 | **Use the 2-day target's time anchor `t_ign_med_ist`** (median 3.5 h before the first detection; 90% interval 8 h) rather than the first-detection day only where it changes the day. A first detection at 01:30 IST usually means a start the previous afternoon. | 2-day prediction; Cleaner fire labels | A3, A5 (time MAE 1.5 h vs 4.1 h, synthetic) | 2 h |
| 4 | **Do not build ignition-point features finer than about 500 m** (distance to road, path or village at the ignition point). Ignition points carry about 350 m real error (calibrated R90 about 800 m). They show no road, stream or village preference against random in-scar points. Keep the cell-level ignition model in `research/ratapani-ignition/`. Use `p_in_first_fp` and the posterior to split an ignition between the two or three cells it may lie in, instead of the patch's "main cell". | Fire prediction research (ignition model); human fire drivers | A6, A4 | 0 h (avoids wasted work); weighting 3 h |
| 5 | **Report starts as "within about 300 m of the first pixel, about a 50% chance inside it"** in live alerts. Use `ign_r90_cal_m` for any search radius given to guards. | Field alert systems; Burn scar for every fire alert (`live.py`) | Findings 2 and 4 | 1 h |
| 6 | **Seed spread simulations at the E2 point and `t_ign_med`, with `ign_r90_cal_m` as the ignition jitter.** Use fires flagged `likely_single` only (69%). | Spread model thread | A3, A5 | 2 h |
| 7 | **Count ignitions in merged scars from the scar's own date field, not from detections.** Apply Oom 2016's local-minimum graph to the Sentinel-3 daily dates (`daily_scar_dating.md`) inside each scar. Detections alone flag 19% of true two-ignition scars against 15% of single ones. | Cleaner fire labels; Burn scar for every fire alert (`split_scars.py`) | A5, B2 | 1 day |
| 8 | **Add a geostationary first-detection time (GK2A, 10-30 min).** It would cut the 8 h ignition-time interval, as Shaddy 2025 does with GOES. | Geo timing; Cleaner fire labels | B8, `geostationary_fire_timing.md` | 2-3 days |
| 9 | **Validate against MP fire registers when they arrive**, Benali-style: 2 km buffer, lag in hours, distance in metres. Benali's MODIS benchmark is a mean of 800 m and 65% within 12 h. | Ground truth / field alert systems | B1 | 1 day once data exist |

## Reading status

- **FULL:**
  - read this round: Benali 2016 (re-read), Oom 2016, Balch 2020 (FIRED), Andela 2022, Haley/Farguell 2018, Shaddy 2025;
  - already read in earlier notes: Andela 2019, Parks 2014.
- **PARTIAL:** Kalantar 2026 (ISPRS), Artés 2019 (GlobFire), Taylor 2024, Laurent 2018 (FRY), Mahood 2022.
- **ABSTRACT ONLY:** Hackett 2026.
- **Not obtained:** Archibald & Roy 2009, Archibald 2010, Frantz 2016, Sá 2017.
- **Downloaded, not read:** Mandel 2018, Farguell 2022.
- Downloads are in `scratchpad/papers_r10_ign/`.
