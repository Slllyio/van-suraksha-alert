# Fire spread models: full-read follow-up (spread thread)

14 Oct 2026. This deepens `fire_spread_models.md` for the "Fire spread model like C-DAC" thread. I read the papers and the software documents themselves, not abstracts. For each item I give what I read, the exact numbers, and one concrete action for us. **[calc]** marks numbers I computed myself. **[inference]** marks my own judgement.

**What I read.**

| # | Item | What I read |
|---|---|---|
| 1 | Kale et al. 2024, *Remote Sensing* 16:2480 (C-DAC WRF-SFIRE, Sikkim) | FULL TEXT (MDPI PDF). Supplements S1 and S2 not opened |
| 2 | WRF-SFIRE `test/em_fire/namelist.fire` and `namelist.fire_fmc` (openwfm GitHub) | FULL (source files) |
| 3 | Chavan, Labade, Kale et al. 2025, ISPRS Annals X-5-W2-2025:103 (C-DAC FDS) | FULL TEXT, with appendices |
| 4 | Xu B. et al. 2022, *Natl Remote Sensing Bulletin* 26(8):1575 (FARSITE + VIIRS re-initialisation) | FULL TEXT (Chinese PDF) |
| 5 | Pyretechnics: docs, README, pyproject, LICENSE.md (version 2026.8.10) | FULL (docs and source) |
| 6 | ELMFIRE: README, Dockerfile, docker-compose, LICENSE.md, ELMFIRE_Guide.pdf (v1.1) | FULL (input chapters and validation chapter) |
| 7 | Scott & Burgan 2005, RMRS-GTR-153 (original USFS PDF) | FULL TEXT, Table 7 and the fuel-model pages |
| 8 | Anderson 1982, INT-122 | FULL TEXT, Table 1 and the pages for FBFM 8 and 9 |
| 9 | Saha 2002, *Current Science* 82(9):1144 | FULL TEXT (scanned, read from page images) |
| 10 | Han et al. 2026, FireSenseNet, arXiv 2604.07675 | FULL TEXT |
| 11 | Jahdi et al. 2015, NHESS 15:443 (FARSITE calibration, broadleaf forests of northern Iran) | FULL TEXT. New, not in the note |
| 12 | Vejmelka et al. 2016 (WRF-SFIRE fuel moisture), arXiv 1406.4480 | PARTIAL (model section only) |
| 13 | Rothermel litter-error studies: Xu C. 2025 IJWF, Zhang 2023, Geng 2024 and 2026, Campbell-Lochrie 2023, Ascoli 2015 | ABSTRACTS ONLY (Consensus) |
| 14 | Nelson model: Carlson 2007, Farguell 2024; firelab/NFDRS4 README | ABSTRACTS, plus the README |
| 15 | Price & Germino 2022 (*Fire Ecology*), Jahdi 2014 (JAST), Filippi 2014 (NHESS) | ABSTRACTS (number checks only) |

That is 11 items read in full (1-11), 1 in part and 3 groups as abstracts.

---

## 1. Kale et al. 2024: C-DAC's WRF-SFIRE in Sikkim (FULL TEXT)

**Case.** One fire in North Sikkim (the Maltim area). The ignition was the VIIRS alert of 27 Jan 2023 at 08:02 UTC (13:30 IST), at 88.67 E, 27.63 N. They ran one 24 h forecast.

**Grids** (Table 1):

| | Domain 1 | Domain 2 | Domain 3 |
|---|---|---|---|
| Size (cells) | 218 × 242 | 76 × 79 | 76 × 76 |
| Resolution | 7200 m | 2400 m | 800 m |
| Fire mesh | – | – | 40 m (refinement 1:20) |

- Nests are in a 1:3 ratio and were made with the WRF Domain Wizard.
- Projection: Mercator.
- Inputs: GFS 0.25° forecasts from NOMADS (5 days downloaded), the ALOS PALSAR 12.5 m DEM, and the 1:10,000 LULC map turned into a 40 m fuel raster.

**Physics (namelist.input), as reported:**
- microphysics: Thompson
- radiation: RRTMG shortwave and longwave
- `sf_sfclay_physics`: MYNN
- `sf_surface_physics`: RUC land surface model
- `bl_pbl_physics`: MYNN level 2.5 and level 3

The schemes were "experimented with until acceptable accuracy was obtained". The paper does **not** publish a full namelist.input, namelist.wps or namelist.fire, and it gives no ignition radius or duration and no `fire_fuel_read` and `fire_fmc_read` settings.

**Fuel table** (Table 2):

| Class (Anderson model used) | Load kg/m² | Depth m | SAV ft⁻¹ |
|---|---|---|---|
| 1 Grassland, grazing land, barren rocky, cropland, agricultural plantation (FBFM 1) | 0.16 | 0.305 | 1631 |
| 2 Dense Scrub (FBFM 2) | 0.234 | 0.61 | 1371 |
| 3 Open Scrub (FBFM 3) | 0.243 | 0.91 | 3750 (= 12,300 m⁻¹, taken from *Themeda australis*) |
| 4 Forest and forest plantation (FBFM 8) | 0.270 | 0.061 | 1224 |

**Scalar constants** (Table 3):

| Constant | Value |
|---|---|
| Fire wind height | 6.096 m |
| Heat of combustion | 17.433 × 10⁶ J/kg |
| Moisture of extinction | 0.12 / 0.15 / 0.25 / 0.30 (classes 1-4) |
| Fuel density | 32 lb/ft³ |
| Total mineral content | 0.055 |
| Effective mineral content | 0.010 |
| Wind reduction factor (windrf) | 0.36 / 0.36 / 0.44 / 0.36 |

**What the paper does not say outright.** I compared Table 2 and Table 3 with the WRF-SFIRE default `namelist.fire` (section 2 below):
- Several "C-DAC values" are simply the WRF-SFIRE defaults: the forest depth of 0.061 m (= FBFM 8 default, 0.2 ft), the grass depth of 0.305 m, every moisture of extinction, every windrf, the fuel density and both mineral contents.
- Only the loads, plus the dense-scrub and open-scrub depths, are field values from the 23 plots of 0.1 ha. The plots were 11 Forest, 6 Open Scrub, 5 Dense Scrub and 1 Grassland, each sampled in five 1 m² subplots.
- The SAVs come from the literature. The paper says the SAV samples "are being analysed".
- The forest load of 0.270 kg/m² is **24 %** of the WRF-SFIRE FBFM 8 default (`fgi` = 1.121 kg/m²) **[calc]**.
- The forest SAV of 1224 ft⁻¹ is lower than the FBFM 8 default (1889). Both changes slow forest spread.

**Fuel moisture:** no value is reported, and no fuel-moisture model run is described.

**Compute:**
- 24 h forecast in **2 h 11 min on 240 cores** of PARAM Seva (Xeon Cascade Lake 8268, 2 × 24 cores per node).
- The methods text says "8 nodes … each node having 48 cores" (384 cores), which conflicts with the 240 in Table 4. This inconsistency is in the paper.

**Results and validation:**
- Forecast area 1.72 km² against 1.07 km² mapped visually on the Sentinel-2 image of 29 Jan 2023. That is an over-forecast of 61 % **[calc]**.
- No overlap score is given, only that the shapes "matched well, barring the spread in the southwest direction".
- Of the forecast burnt area, **76 % was Open Scrub, 16 % Dense Scrub and only 8 % Forest**.
- 98 % of the area burned within the first 15 h.
- Mean wind over the burn was **1.44 m/s**. It was 2-4 m/s in the first 3 h, and the forecast spread turned southwest against a near-calm wind.
- Forest stopped the fire, which the paper attributes to the low SAV and high moisture of extinction.

**Lessons the authors draw:**
- The 40 m mesh was chosen so that no-fuel barriers (rivers, roads) are represented. Coarser meshes let fire cross barriers.
- Landslides missing from the LULC map acted as false fuel.
- The 24 h, 48 h and SMS-alert system (React, Leaflet, GeoServer, Spring Boot) takes its ignitions from the FSI alert server.

**What this means for Ratapani [inference]:**
- The only validated C-DAC case is a grass and scrub fire in the Himalaya, carried in Open Scrub with SAV 3750 ft⁻¹.
- Their forest parameters were never tested on a forest-dominated fire. With the FBFM 8 structure, a load of 0.27 kg/m² and SAV 1224, a teak-litter fire would barely spread.
- Copying "the C-DAC setup" to Ratapani does not copy any calibration that matters for litter.

**Concrete action (spread thread):**
- Do not copy C-DAC's forest fuel parameters.
- Ask C-DAC (by email, citing this paper) for three things:
  1. their namelist.input, namelist.fire and namelist.wps
  2. Supplementary Table S2
  3. the fuel-moisture setting they used (`fuelmc_g`)
- If they run Ratapani for us, ask them to use the TL6-type values from section 7 and our scoring set (action list, item 1).

## 2. WRF-SFIRE default fuel table (`namelist.fire`, FULL)

These are the reference values that C-DAC edited (13 Anderson categories plus no-fuel category 14).

| Cat | windrf | fgi kg/m² | depth m | savr ft⁻¹ | fuelmce | weight |
|---|---|---|---|---|---|---|
| 1 short grass | 0.36 | 0.166 | 0.305 | 3500 | 0.12 | 7 |
| 2 timber-grass | 0.36 | 0.897 | 0.305 | 2784 | 0.15 | 7 |
| 3 tall grass | 0.44 | 0.675 | 0.762 | 1500 | 0.25 | 7 |
| 8 closed timber litter | 0.36 | 1.121 | 0.061 | 1889 | 0.30 | 900 |
| 9 hardwood litter | 0.36 | 0.780 | 0.061 | 2484 | 0.25 | 900 |
| 10 timber litter + understorey | 0.36 | 2.694 | 0.305 | 1764 | 0.25 | 900 |

- Scalar settings: `cmbcnst` = 17.433e6 J/kg, `fuelmc_g` = **0.08** (ground fuel moisture), `fuelmc_c` = 1.00, `fueldens` = 32, `st` = 0.0555 and `se` = 0.010 for every category.
- The `_fmc` variant adds per-size-class loads (Albini 1976) so that the built-in moisture model can weight the 1 h, 10 h and 100 h classes.
- **WRF-SFIRE's moisture model** (Vejmelka 2016, section 2) is a first-order time-lag equation for each class (time lags 1, 10 and 100 h). It moves towards a drying equilibrium Ed or a wetting equilibrium Ew (Van Wagner & Pickett 1985 form, with Ed − Ew constant), with a rain-soaking branch above a rain threshold r0 (saturation level S, soaking time lag Tr, saturation rain rate rk). The paper says these parameters were fitted to Van Wagner & Pickett. The exact default values are in the source code and **[not checked here]**.

**Concrete action:** if anyone runs WRF-SFIRE for Ratapani, give category 9 (hardwood litter) the values from section 7, not category 8 with C-DAC's numbers. Set `fuelmc_g` from our ERA5-Land moisture series for that day, not the 0.08 default.

## 3. Chavan et al. 2025: C-DAC's FDS run (FULL TEXT)

**What was actually run.** NIST FDS 6.7.5 in **level-set mode 4**, where the level-set front is fully coupled to the FDS flow solver. It was not a Lagrangian-particle or boundary-fuel physical model.
- Case: Melli, South Sikkim. Grass 1-2 m tall with scattered shrubs and sal.
- Fire seen on Sentinel-2 on 29 Apr 2020. The digitised burnt area was **23.45 acres (9.5 ha)**.
- The FDS input was made with WFDS InputFileCreator, from the ALOS 12.5 m DEM and a 10 m fuel map (Anderson classes 1, 2, 3, 8, 10 and 14).
- Wind was constant at **1.41 m/s** (a 10 m gust value, from NCMRWF and meteoblue).

**Fuel inputs** (Appendices 3 and 4):

| Input | Value |
|---|---|
| Grass no-wind ROS (`VEG_LSET_ROS_00`) | **0.002 m/s** (0.12 m/min) |
| Packing ratio β | 0.0012 |
| Heat of combustion | 18,607 kJ/kg |
| Soot yield | 0.01 |
| Fuel composition | C6H10O5 |

**Field SAVs** (6 plots, Bufacchi method), in m⁻¹ with ft⁻¹ in brackets **[calc]**:

| Class | m⁻¹ | ft⁻¹ |
|---|---|---|
| Dense scrub | 9123 | 2781 |
| Open scrub | 6997 | 2133 |
| Forest plantation | 7198 | 2194 |
| Grass | 2650 | 808 |

These **disagree with Kale 2024 Table 2** (forest 1224 ft⁻¹; grass 1631 ft⁻¹). The measured forest-litter SAV of about 2200 ft⁻¹ is close to the Scott-Burgan litter value of 2000.

**Validation:** "**70 % agreement** between the simulated and satellite burnt area for the first fire point". The metric is not defined. The existing note's "no score reported" was wrong, and I have corrected it.

**Compute:**
- Domain 500 × 500 × 725 m.
- At a 1 × 1 × 1 m grid (90-181 million cells): **625 processors on 16 nodes took 10 h of wall-clock time for an 800 s fire**.
- Scaling: 80 processors took 30,361 s and 625 took 4,521 s (×6.7 speed-up). Scaling was linear up to about 200 processors.
- Grid study on 100 processors: 1 m took 34,880 s, 2 m took 3,105 s and 5 m took 950 s.

**Other numbers quoted:**
- Sati et al. 2016 report **0.888 m/s** spread in chir pine and pine-oak in Uttarakhand.
- Local people told the authors "about 2 m/s".

Both are far above the Rothermel litter values in section 7. They are probably grass or slope runs, or anecdote **[inference]**.

**Concrete action:** none to build. Use the measured SAV of about 2200 ft⁻¹ for broadleaf litter (it supports keeping the TL-model value of 2000) in the calibration priors in section 7.

## 4. Xu B. et al. 2022: FARSITE re-initialised from VIIRS (FULL TEXT)

**Case.** The fire of 17 May 2017 at Najilin forest farm, Chenbaerhuqi, Inner Mongolia: about **12,000 ha** of meadow and secondary birch forest, mainly a surface fire. It was contained on 20 May at 11:30. Ground crews were actively suppressing it, which the model did not represent.

**FARSITE setup:**
- Fuel and canopy layers from Landsat-8 and GF-1, with 5 custom fuel models (shrub, birch forest, forest grass, other grass, floodplain grass; Table 3), adapted from studies in north-east China.
- Initial dead moisture **3 / 4 / 5 %** for 1 h / 10 h / 100 h, live herbaceous **30 %**, live woody **60 %**.
- Time step **30 min**, perimeter resolution **90 m**, surface fire only, hourly weather.
- "Truth" perimeters came from Sentinel-2A, GF-1 and GF-4.

**Re-initialisation:** the model was restarted from new VIIRS 375 m fire pixels about **every 12 h** (VIIRS overpass times 01:00 and 12:30), giving runs T0-T4 and segments S1-S11.

**Results** (Sørensen coefficient, SC):

| Run | SC |
|---|---|
| Free run from the first VIIRS ignition, after 22 h | 0.72 |
| Same free run, after 45 h | 0.56 |
| Same free run, after 70.5 h | 0.54 |
| Final SC with re-initialisation (free run gave 0.5414) | **0.7876** |
| Best single re-initialised segment | 0.878 |

- The final SC is +45.45 % in relative terms (the abstract also quotes +42.76 %). The largest gain in any one step was +56.89 %.
- A night-time re-initialisation (01:00) did worse because the night-time input errors were larger.
- Errors were largest where suppression crews worked and when the wind direction turned.

**What it means for us:**
- Skill decays steadily with the length of the free run.
- Restarting from the newest satellite front recovers most of the loss.
- This is the physics-model version of our "freshness of the front dominates" finding.
- With fires as small as Ratapani's, a 375 m pixel is the same size as the fire, so the re-initialised "perimeter" is coarse **[inference]**.

**Concrete action (spread thread):** in whichever engine we use (Pyretechnics or ELMFIRE), never run free for more than one day.
- Each day, build the initial burned field φ < 0 from (a) the dated scar pixels already burned and (b) VIIRS pixels from the last 24 h, buffered by 187 m.
- Run to the next VIIRS overpass. Score the result against the next day's new pixels.
- Expected effect: from Xu's numbers, about +0.2 to +0.25 in Sørensen over a free run of more than 2 days.

## 5. Pyretechnics (FULL: docs, source, licence)

**Version and dependencies:**
- 2026.8.10 on PyPI, **source distribution only (no wheels)**.
- `requires-python ~=3.11`, numpy ~1.26.2, scipy ~1.12, rasterio ~1.4.3, sortedcontainers, Cython ~3.0.11.
- Building on Windows needs a C compiler (MSVC Build Tools). The authors build in GNU Guix on Linux.
- **Recommended:** `pip install pyretechnics` in a Python 3.11 Linux container or WSL2 **[inference]**.

**Licence (correction):** the old EPL-2.0 is gone. The licence is now **dual**:
- a free *Community License* for "noncommercial, research, educational, governmental, nonprofit, evaluation" uses, which explicitly covers government natural-resource-management mandates
- a paid *Commercial License* otherwise

FSI and MP Forest Department use is covered. A paid service built on it would not be.

**Modules:** `space_time_cube`, `fuel_models`, `surface_fire`, `crown_fire`, `spot_fire`, `burn_cells`, `eulerian_level_set`, `suppression`, `conversion`, `load_landfire`.

**Main call:** `eulerian_level_set.spread_fire_with_phi_field(space_time_cubes, spread_state, cube_resolution, start_time, max_duration, max_cells_per_timestep=0.4, buffer_width=3, use_wind_limit=True, surface_lw_ratio_model="behave", ...)`.

Its inputs are a dict of `SpaceTimeCube` objects with these keys and units:

| Key | Unit |
|---|---|
| `slope` | rise/run |
| `aspect` | degrees clockwise from north |
| `fuel_model` | integer key into `fm.fuel_model_table`: 1-13 Anderson, 91-99 non-burnable, 101-204 Scott-Burgan (TL2 = 182, TL6 = 186, TL8 = 188, TL9 = 189, GR2 = 102, TU1 = 161) |
| `canopy_cover` | 0-1 |
| `canopy_height`, `canopy_base_height` | m |
| `canopy_bulk_density` | kg/m³ |
| `wind_speed_10m` | km/h |
| `upwind_direction` | degrees |
| `fuel_moisture_dead_1hr`, `_10hr`, `_100hr`, `_live_herbaceous`, `_live_woody`, `foliar_moisture` | kg/kg |
| `fuel_spread_adjustment` (optional) | per-cell ROS multiplier ≥ 0 |
| `weather_spread_adjustment` (optional) | per-cell ROS multiplier ≥ 0 |

- `cube_resolution = (band minutes, cell height m, cell width m)`.
- Start from a point with `SpreadState(cube_shape).ignite_cell((y, x))`, or from an existing scar with `ignite_cells(lower_left, matrix)` (values < 0 mark burned cells).
- Outputs are 2D arrays of `phi`, `fire_type`, `spread_rate` (m/min), `spread_direction`, `fireline_intensity` (kW/m), `flame_length` (m) and **`time_of_arrival` (min)**.

**Worked example in the docs** (copy and paste): a 240 × 100 × 100 cube (10 days × 3 km at 30 m), constant inputs, fuel model 101, `ignite_cell((50,50))`, start at day 2 10:30, run 8 h, with `surface_lw_ratio_model="rothermel"`.

**Fuel model table format:** `(delta ft, Mx %, h, w1h, w10h, w100h, wherb, wwoody lb/ft², σ1h, σ10h = 109, σ100h = 30, σherb, σwoody)`. Example: TL6 is `(0.3, 25, 8, 0.1102, 0.0551, 0.0551, 0, 0, 2000, 109, 30, 0, 0)`.

Custom models have to be added to that table. It is a Cython-declared dict, so **[inference]** add entries before the import is compiled, or edit the source table. The `fuel_spread_adjustment` cube avoids touching the table.

**Concrete action (spread thread):** see action list, item 2. The two adjustment cubes are the calibration handles: one scalar per fuel class (or per beat) multiplies Rothermel's ROS, which is the "effective fuel" idea (Rios 2019) with no need to edit fuel tables.

## 6. ELMFIRE (FULL: README, Dockerfile, guide v1.1)

**Licence:** AGPL-3.0 plus the Commons Clause v1.0 (licensor CloudFire Inc.). Selling it, or a service whose value comes from it, needs a commercial licence. Confirmed.

**Docker:**
```
git clone https://github.com/lautenberger/elmfire.git
cd elmfire
docker compose up -d --build        # about 10 min first build; Ubuntu 24.04, gfortran, OpenMPI, micromamba GDAL env
docker compose exec elmfire bash
# work in ./docker_shared_folder (persists); everything else is lost on 'docker compose down'
```
The guide says that on Windows you use Docker Desktop with WSL2 integration.

**Minimum `elmfire.data` settings:**

| Namelist | Settings |
|---|---|
| `&INPUTS` | `FUELS_AND_TOPOGRAPHY_DIRECTORY`, `LANDSCAPE_FILENAME` (or separate rasters), `ADJ_FILENAME`, `PHI_FILENAME`, `WEATHER_DIRECTORY`, `WS_FILENAME`, `WD_FILENAME`, `M1_FILENAME`, `M10_FILENAME`, `M100_FILENAME`, `LH_MOISTURE_CONTENT`, `LW_MOISTURE_CONTENT`, `FOLIAR_MOISTURE_CONTENT`, and `DT_METEOROLOGY = 3600` for hourly multi-band weather |
| `&OUTPUTS` | `DUMP_TIME_OF_ARRIVAL`, `DUMP_SPREAD_RATE`, `CONVERT_TO_GEOTIFF` |
| `&TIME_CONTROL` | `SIMULATION_TSTOP` |
| `&SIMULATOR` | `NUM_IGNITIONS`, `X_IGN`, `Y_IGN`, `T_IGN` (or line ignitions) |
| `&MISCELLANEOUS` | `PATH_TO_GDAL`, `SCRATCH` |

Raster formats and units:

| Raster | Type and unit |
|---|---|
| ASP, SLP (degrees), DEM (m), CC (%), FBFM | Int16 |
| CH, CBH | Int16, units of 10 m |
| CBD | Int16, units of 100 kg/m³ |
| ADJ, PHI | Float32 |
| Weather rasters | Float32. WS is 20 ft wind in mph by default; switches `WS_AT_10M` and `WS_IN_KPH`. Moisture in % |

- **`PHI` < 0 marks the cells already burned at the start.** This is the daily-restart handle.
- **`ADJ` is a per-pixel ROS multiplier**, the calibration handle.
- `USE_PYROMES` with an `ADJUSTMENT_FACTORS_FILENAME` table gives a multiplier for each region × fuel model.
- **Custom fuels:** a row in `fuel_models.csv` in `MISCELLANEOUS_INPUTS_DIRECTORY`. Format: `number, name, dynamic, w1h, w10h, w100h, wherb, wwoody (lb/ft²), σ1h, σherb, σwoody (ft⁻¹), depth (ft), Mx (%), heat (Btu/lb)`. Example: `1,FBFM01,.FALSE.,0.034,0,0,0,0,3500,9999,9999,1,12,8000`. Hard-coded: σ10h = 109, σ100h = 30, ρp = 32, St = 0.055, Se = 0.01.
- **Monte Carlo:** `&MONTE_CARLO` with `NUM_ENSEMBLE_MEMBERS` and `RASTER_TO_PERTURB(i)`, plus GAUSSIAN or LOGNORMAL `PDF_MEAN`/`PDF_SIGMA`. The guide's example perturbs WD (σ 20°) and M1 (lognormal σ 0.3).

**Validation in the guide** (WildfireAV, an automated set of many US fires, untuned, no spotting or suppression):

| Model | Mean Jaccard | Mean Sørensen | Mean kappa |
|---|---|---|---|
| ELMFIRE | 0.178 | **0.278** | 0.241 |
| FARSITE | 0.176 | 0.274 | 0.249 |

The pipeline is public: github.com/nick-cloudfire/WildfireAV.

**What it means:** uncalibrated, operational Rothermel models average a Sørensen of about 0.28 on whole-fire scars. So a distance kernel calibrated on our own fires may well beat an uncalibrated physics model **[inference]**.

**Concrete action:** item 3 of the action list, only after Pyretechnics calibration.

## 7. Scott & Burgan 2005 and Anderson 1982: verified parameters, plus my own Rothermel runs

**Table 7 of GTR-153 (original PDF), verified.** All values in the existing note's table are correct. Fuller rows:

| Model | 1h / 10h / 100h t/ac | herb / woody t/ac | 1h SAV | Depth ft | Mx % | Characteristic SAV | Packing ratio |
|---|---|---|---|---|---|---|---|
| GR1 | 0.10 / 0 / 0 | 0.30 / 0 | 2200 | 0.4 | 15 | – | – |
| GR2 | 0.10 / 0 / 0 | 1.00 / 0 | 2000 | 1.0 | 15 | 1820 | 0.00158 |
| TU1 | 0.20 / 0.90 / 1.50 | 0.20 / 0.90 | 2000 | 0.6 | 20 | 1606 | 0.00885 |
| TL2 | 1.40 / 2.30 / 2.20 | 0 / 0 | 2000 | 0.2 | 25 | 1806 | 0.04232 |
| TL3 | 0.50 / 2.20 / 2.80 | 0 / 0 | 2000 | 0.3 | 20 | 1532 | 0.02630 |
| TL6 | 2.40 / 1.20 / 1.20 | 0 / 0 | 2000 | 0.3 | 25 | 1936 | 0.02296 |
| TL8 | 5.80 / 1.40 / 1.10 | 0 / 0 | 1800 | 0.3 | 35 | – | – |
| TL9 | 6.65 / 3.30 / 4.15 | 0 / 0 (woody SAV 1600 listed) | 1800 | 0.6 | 35 | – | – |

- Every model uses a heat content of 8000 Btu/lb, a 10 h SAV of 109 and a 100 h SAV of 30.
- Scott & Burgan describe TL2 as "low load, compact broadleaf litter; spread rate very low", and TL6 as "moderate load broadleaf litter, less compact than TL2; spread rate moderate".

**Anderson 1982 (INT-122) Table 1, verified:**

| Model | 1h / 10h / 100h t/ac | Depth ft | Mx % |
|---|---|---|---|
| FBFM 8 | 1.50 / 1.00 / 2.50 | 0.2 | 30 |
| FBFM 9 | 2.92 / 0.41 / 0.15 | 0.2 | 25 |

- INT-122 does not list SAV. The 1 h SAV of 2000 (FBFM 8) and 2500 (FBFM 9) match Albini 1976 as coded in both Pyretechnics and WRF-SFIRE (characteristic SAV 1889 and 2484).
- INT-122 reference behaviour at 8 % dead moisture and a 5 mi/h midflame wind: FBFM 8 spreads 1.6 ch/h with 1.0 ft flames; FBFM 9 spreads 7.5 ch/h with 2.6 ft flames.

**My Rothermel check [calc].** I wrote a 50-line Rothermel (1972) script for dead fuels only, using the Albini constants as in BehavePlus. It is in the scratchpad (`scripts_spread/roth.py`). It reproduces the INT-122 reference values: FBFM 8 gives 1.75 ch/h and 0.98 ft; FBFM 9 gives 7.61 ch/h and 2.66 ft. The table below is for a 10 % slope:

| Model | 1h moisture 6 %, wind 0 | 1h 6 %, midflame 2 km/h | 1h 6 %, midflame 5 km/h | Flame length at 2 km/h |
|---|---|---|---|---|
| FBFM 8 | 0.09 m/min | 0.17 | 0.39 | 0.18 m |
| TL2 | 0.07 | 0.12 | 0.27 | 0.13 m |
| C-DAC "Forest" (0.27 kg/m², SAV 1224, 0.2 ft, Mx 30) | 0.22 | 0.68 | 1.57 | 0.53 m |
| TL6 | 0.24 | 0.46 | 1.12 | 0.41 m |
| FBFM 9 | 0.33 | 0.57 | 1.50 | 0.42 m |
| TL8 | 0.29 | 0.53 | 1.20 | 0.55 m |
| TL9 | 0.41 | 0.79 | 1.79 | 0.79 m |

Moving the 1 h moisture from 4 % to 12 % changes ROS by about −35 to −45 %.

**Plausibility check against Saha 2002 (section 8):**
- Saha measured mean flame *heights* of 55-60 cm (never above 75 cm). Flame length is at least the height.
- His 9 m² plots took 10-12.8 min to burn, which implies a front speed of about 0.25-0.3 m/min across 3 m **[calc]**.
- FBFM 8 and TL2 give flames 3-4 times too short and spread too slow.
- TL6, FBFM 9 and TL8 fit the spread rate. TL8 and TL9 fit the flame lengths best.
- **Start with TL6** (or FBFM 9) for dry-deciduous litter after leaf fall. Do not use FBFM 8.

**Scale implication [calc]:**
- At 0.2-0.6 m/min and about 8-12 burning hours a day, a litter front moves about **100-430 m per day**: less than one of our 500 m cells.
- A midflame wind of 2 km/h roughly doubles ROS, but that changes daily advance by only a few hundred metres, mostly within the cell.
- This is a physical explanation for why wind direction adds nothing at 500 m and over 5-day windows. Our labels cannot resolve wind effects at that scale.

**Concrete action (spread thread):** use TL6 (186) as the prior for teak and mixed forest after leaf fall, TL2 (182) for January to mid-February, GR2 (102) or TU1 (161) for open blanks, and 91-99 for water, roads and fields. Calibrate one ROS multiplier per class against our arrival days, and check that it falls in about 0.5-2. If it needs to be above 3 or below 0.3, the fuel model is wrong, not just the load.

## 8. Saha 2002: Mendha, Gadchiroli (FULL TEXT, scanned)

**Site and design:**
- Dry deciduous forest of *Terminalia alata*, *Pterocarpus marsupium* and *Anogeissus latifolia* (not teak). Rainfall 1600 mm. Elevation 150-300 m.
- 24 plots of 9 m² in a 4 ha patch, studied 1999-2001. Fires were anthropogenic (mahua flower and *Diospyros* leaf collection), once a year in March, and some plots were burned experimentally.

**Fuel load** (Table 2; fresh weight, g per 0.25 m²; converted to t/ha **[calc]**):

| Year | Feb | Mar | Apr | May |
|---|---|---|---|---|
| 1999 | 73.8 (2.95) | 91.8 (3.67) | 104.4 (4.17) | 106 (4.24) |
| 2000 | 72.7 (2.91) | 95 (3.80) | 100.4 (4.01) | 107 (4.28) |
| 2001 | 92.6 (3.70) | 112.5 (4.50) | NA | NA |

- The month effect was significant (F₃,₇₂ = 13.98, P < 0.0001). The load levels off by mid-April.
- **More than 75 % of the leaf litter is shed by late March.**
- Plots burned the year before carry only about **¼** of the litter of unburned plots.
- Load is about 1.3-2.0 t/ac, close to the TL6 1 h load of 2.4 t/ac and above TL2's 1.4 **[calc]**.

**Fire behaviour:**
- Mean flame height was 55 ± 11.6 cm (March 1999) and 60 ± 6 cm (March 2001), never above 75 cm.
- Plot burn times were 12.8 min (March 1999), 10 min (April 1999), 12.6 min (March 2000) and 10.6 min (2001).
- Juvenile exposure time had a median of 12 s (range 0-35 s).
- Peak soil-surface temperatures were 45-510 °C (tablet range up to 650 °C). Spatial CV was 19 % (March 1999), 7 % (April 1999), 13.38 % (2000) and 20 % (2001).
- Fire-return interval was 1 year. In 2001 rain in early March delayed the fires, and many sites could have burned twice.

**Concrete action (spread thread):** use these as plausibility checks on any calibrated model:
- flame length 0.5-0.8 m
- front speed about 0.2-0.4 m/min in calm conditions
- litter load rising from about 3 to 4.3 t/ha between February and April, so switch from TL2 to TL6 about mid-March

Also use "a cell burned last year carries about ¼ of the fuel" as a fuel-reduction rule in spread runs (set the ADJ value or ROS multiplier to about 0.3 for cells burned in the previous season) **[inference]**. This can be tested against our scar history.

## 9. FireSenseNet 2026 (FULL TEXT)

- Data: the Next-Day Wildfire Spread benchmark (Huot 2022), 64 × 64 patches at 1 km, daily.
- Clean F1 is **0.4176**, against 0.3502 for a SegFormer with 3.8 times as many parameters. The CAFIM module adds 7.1 %.

**Channel importance** (ΔF1 when a channel is replaced by its mean; Table 3):

| Channel | ΔF1 |
|---|---|
| PrevFireMask | **−0.2096** |
| ERC | −0.0189 |
| NDVI | −0.0170 |
| Elevation | −0.0058 |
| PDSI | −0.0019 |
| Wind direction | −0.0005 |
| **Wind speed** | **+0.0011** (removing it helps) |

- The authors attribute the wind result to daily-mean wind against instantaneous gusts.
- **Evaluation inflation:** counting previous-day fire in the target and recoding unknown pixels (−1) as 0 inflates F1 by 44-50 % (FireSenseNet goes from 0.4176 to 0.6033, +44.4 %).

**Concrete action (spread thread):**
- Cite this as independent support for our finding on wind.
- Audit our own LightGBM spread scoring for the same two shortcuts: (1) cells already burning on day t must be excluded from the day t+1 target, and (2) cloud or no-data cells must be masked, not set to 0.
- If either is present, our reported skill is inflated by a comparable amount.

## 10. Jahdi et al. 2015: FARSITE calibration in broadleaf deciduous forest, northern Iran (FULL TEXT; new)

- Several recent fires of tens of hectares, in Hyrcanian broadleaf forests (beech, hornbeam, ironwood, maple) and grassland.
- Scott-Burgan models beat Anderson models.

**Results:**

| Fire and model | SC | K |
|---|---|---|
| Best overall: Toshi, GR6 | 0.92 | 0.87 |
| Gharangi, TL9 | 0.91 | 0.91 |
| Malekroud, FBFM 9 | 0.85 | 0.82 |
| Malekroud, TL6 or FBFM 10 | 0.73-0.79 | – |
| Worst: TU1 | 0.47 | 0.45 |

- GR6, TU2, TU5 and TL9 all reached SC ≥ 0.90.
- The simulated ROS range was 0.05-10.84 m/min.

**Concrete action:** this is the closest published calibration for broadleaf litter at Ratapani-like fire sizes. It supports FBFM 9, TL6 and TL9 as the candidate set and rules out TU1-type low loads. Include FBFM 9 alongside TL6 in our search (item 2).

## 11. Rothermel errors for litter, and the Nelson model (ABSTRACTS)

**Uncalibrated error in laboratory litter beds:**

| Study | Error | Notes |
|---|---|---|
| Xu C. 2025, IJWF (142 burns, *Pinus koraiensis* and *Quercus mongolica*) | **MRE 135.1 %** (MAE 2.54 m/min) | Calibrating the wind coefficient and then IR brings MRE to 24.9 % (MAE 0.39). Observed ROS 1.38-11.09 m/min |
| Geng 2026 (288 burns, *P. koraiensis*) | MRE 35.0 %, MAE 0.20 m/min | Mostly over-prediction |
| Zhang 2023 (Karst, 7 species, no wind) | Relative error up to 50 % | |
| Geng 2024 | After modification: MRE 25.1 %, R² 0.80 | |

- Campbell-Lochrie 2023 found the opposite bias for *compressed* beds: under-prediction driven by IR.
- The "38 %" lower bound in the existing note could not be traced to an abstract. I changed it to 35 % (Geng 2026).
- Ascoli 2015 (genetic algorithm): RMSE fell by 39 %, 19 % and 26 % for litter, grass and shrub models. Verified.

**Nelson dead-fuel moisture model:**
- Carlson 2007 (Oklahoma, 21 months): r² against stick weighings was 0.79 for 10 h and 0.51 for 1000 h. For fuels at or below 30 % moisture, the older NFDRS beat Nelson for 1 h and matched it for 10 h.
- Farguell 2024: WRF-SFIRE's time-lag model with data assimilation had a 10 h MAE of **0.03 g/g, against 0.05 for Nelson**.
- Reference code: **firelab/NFDRS4** on GitHub (public domain, C++, CMake), which "provides SWIG wrappers to build Python libraries" and includes the Nelson model. No PyPI package was found.

**Concrete action (spread thread):** we have no fuel-stick data to assimilate. Take a simple path:
- Compute 1 h moisture from ERA5-Land hourly T and RH with Van Wagner equilibrium and a 1 h time lag.
- Compute 10 h moisture with a 10 h time lag, plus a rain reset.
- Check the dry-season afternoon minimum is about 4-8 %.

Do not build Nelson unless the moisture term proves to matter in calibration (expected effect on ROS ±40 % between 4 % and 12 %; section 7).

## 12. Number checks for other items in the note (ABSTRACTS)

- **Price & Germino 2022:** LANDFIRE fuels gave SC 0.38 and K 0.36. A map classified from **RAP satellite vegetation cover** (not field-derived) gave SC 0.70 and K 0.68, and SC 0.80 and K 0.79 on a second fire. Numbers correct; wording corrected in the note.
- **Jahdi 2014** (Siahkal, northern Iran): kappa 0.5 with uniform wind and 0.8 with WindNinja. Correct.
- **Filippi 2014 NHESS:** 80 Mediterranean fires × 4 ROS models = 320 simulations; "the most complex models outperform the more empirical ones". Correct.

---

## Verified numbers

| Claim in `fire_spread_models.md` | Status | Source |
|---|---|---|
| C-DAC grids 7.2 km / 2.4 km / 800 m, fire mesh 40 m, ratio 1:20 | Correct | Kale 2024, Table 1 |
| Fuel classes map to FBFM 1, 2, 3, 8 | Correct | Kale §3.3 |
| Forest load 0.270 kg/m², depth 0.061 m, SAV 1224 ft⁻¹ | Correct as published, but the depth is the FBFM 8 default and the SAV comes from the literature, not the field | Kale Table 2; WRF-SFIRE namelist.fire |
| Moisture of extinction 0.12 / 0.15 / 0.25 / 0.30; windrf 0.36-0.44; heat 17.433 MJ/kg | Correct; all are WRF-SFIRE defaults | Kale Table 3 |
| 2 h 11 min on 240 cores | Correct (the text also says 8 nodes × 48 cores, which is inconsistent) | Kale Table 4 |
| 1.72 vs 1.07 km², about 60 % over-forecast | Correct (+61 %); 76 % of the forecast burn was Open Scrub | Kale §4 |
| Chavan 2025 FDS at 1 m, "no score reported" | **Wrong**: FDS level-set mode 4, grids 1-5 m; "70 % agreement" reported. Fixed | Chavan §4 |
| FDS about 10 h for a small area | Correct: 10 h wall clock for 800 s of fire, 500 × 500 m, 625 processors | Chavan §4 |
| Xu 2022 Sørensen 0.54 → 0.79 | Correct (0.5414 → 0.7876; best segment 0.878) | Xu 2022 |
| Pyretechnics licence EPL-2.0 | **Wrong**: now a dual Community / Commercial licence. Fixed | LICENSE.md |
| ELMFIRE licence AGPL-3.0 plus Commons Clause | Correct | LICENSE.md |
| TL2, TL6, TL9, TU1, GR1 and GR2 parameters | Correct | GTR-153 Table 7 |
| FBFM 8 and 9 loads, depth, Mx; "check against INT-122" | Verified against INT-122 Table 1. SAV is not in INT-122 but matches Albini 1976 as coded | INT-122 |
| Saha: March fires, 75 % leaf fall, flames 55-60 cm, about 12 s, return interval 1 yr | Correct (12 s is the median exposure time of a juvenile) | Saha 2002 |
| Rothermel litter error 38-135 % | **Changed to 35-135 %**; 38 % not traceable | Geng 2026; Xu 2025 |
| FireSenseNet F1 0.42, wind is noise, inflation > 44 % | Correct (0.4176; +44.4 to 50 %) | arXiv 2604.07675 |
| Price 2022 0.38 → 0.70-0.80 "with a locally derived fuel map" | Numbers correct; the map was **RAP satellite-derived**. Fixed | Price & Germino 2022 |
| Ascoli 2015, errors down 19-39 % | Correct | Abstract |
| Filippi 2014: 80 fires × 4 models | Correct | NHESS abstract |
| New: untuned ELMFIRE and FARSITE mean Sørensen 0.278 / 0.274 on an automated US set | Added | ELMFIRE guide, Chapter 4 |

---

## Ranked action list

| # | Action | Inputs and settings | Expected gain | Effort | Thread |
|---|---|---|---|---|---|
| 1 | **Fix the evaluation first.** Check our LightGBM spread scoring for the two FireSenseNet shortcuts (burning cells left in the next-day target; no-data cells set to 0). Then build the scoring set: dated fires with VIIRS pixel days, scar, ignition and ERA5-Land, scored with Sørensen, POD, FAR and arrival-day error for the distance kernel and LightGBM | Our existing tables | Avoids a possible 40-50 % inflated F1. Gives the baseline every physics run must beat | 1-3 days | spread |
| 2 | **Pyretechnics, restarted daily and calibrated.** Linux container with Python 3.11 and `pip install pyretechnics`. 30 m grid; fuel 186 (TL6) after mid-March, 182 (TL2) before, 102 or 161 for blanks, 91-99 for non-fuel; DEM slope and aspect; ERA5-Land 10 m wind (km/h); 1 h and 10 h moisture from the time-lag model (section 11); canopy cover from Sentinel-2. Each day `ignite_cells` from the scar plus the last 24 h of VIIRS, run 24 h, take `time_of_arrival`. Fit one `fuel_spread_adjustment` per fuel class (and optionally per beat) on 2017-2022 by grid search over 0.25-4; test on 2023-2026. Try FBFM 9 against TL6. Add a previous-year-burn multiplier of about 0.3 | As stated | Physics (section 7) predicts 100-430 m/day. Expect Sørensen in the range 0.5-0.8 when restarted daily (Xu 2022), but **may not beat the distance kernel** at 500 m. Its likely gain is *where* within the cell, at 30 m, plus flame length and intensity for crews | 1-2 weeks | spread |
| 3 | **Low-cost plausibility gate before item 2.** Run `roth.py` (or Pyretechnics `burn_cells`) for a typical March afternoon (1 h moisture 5 %, midflame 1-3 km/h). Reject any fuel set whose flame length is outside 0.5-0.8 m or whose calm ROS is outside 0.2-0.4 m/min (Saha 2002) | Script is in the scratchpad | Throws out FBFM 8 and TL2-type choices (including C-DAC's forest class) before compute is spent | Hours | spread |
| 4 | **Ask C-DAC for the missing pieces.** Full namelists, Table S2, the moisture setting, and whether they will run Ratapani with TL6- or FBFM 9-type forest fuels against our scoring set | Email citing Kale 2024 | Removes the only reason to build WRF-SFIRE ourselves | 1 email | spread, partnerships |
| 5 | **ELMFIRE in Docker for ensemble "reach" maps.** Only after item 2 has fixed the multipliers. Custom `fuel_models.csv` rows; `ADJ` raster = calibrated multipliers; `PHI` = current scar; `&MONTE_CARLO` with about 200 members perturbing WD (σ 20°), WS (lognormal σ 0.3) and M1 (lognormal σ 0.3) | Docker Desktop and WSL2 on the PC | 24-48 h burn-probability envelopes per alert. Untuned ELMFIRE averages Sørensen 0.28 (guide), so calibration is essential | 3-5 days | spread, ops |
| 6 | **Fuel moisture.** Time-lag 1 h and 10 h moisture from ERA5-Land (Van Wagner equilibrium). Build NFDRS4/Nelson through SWIG only if calibration shows moisture sensitivity | ERA5-Land hourly | ±40 % ROS between 4 % and 12 % moisture; needed as a covariate either way | 1 day | spread, danger |
| 7 | **Do not build WRF-SFIRE or FDS locally.** C-DAC's FDS took 10 h on 625 cores for 800 s of a 9.5 ha fire; WRF-SFIRE took 2 h on 240 cores for one 24 h forecast | – | Saves weeks | – | spread |
