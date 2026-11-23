# Fine-scale fire weather and dead fuel moisture inside a beat (scouting round 3, topic "wx", 14 Oct 2026)

**Question.** ERA5-Land (9 km) and POWER (50 km) tell us *when* fires happen. Can weather or dead-fuel moisture that varies at 10–500 m inside a ~10 km² beat tell us *where*, i.e. which 500 m cell burns in the next 2 days? This note covers terrain and canopy effects on litter moisture, microclimate models, fuel-moisture models and sensors, high-resolution Indian forecast products, and AI downscaling.

**Reading status.** **FULL** means I read the whole text. **PARTIAL** means I read the relevant sections. **ABSTRACT ONLY** means I saw only the abstract or a catalogue page. My own reasoning and arithmetic are marked **[inference]**.

**What this note does not repeat.** These are covered elsewhere:
- MODIS/VIIRS 1 km LST as a daily dryness feature: `open_datasets.md` B9.
- ECOSTRESS: `fire_detection_sources.md`.
- Nelson model code (NFDRS4 `deadfuelmoisture.cpp`, Go port): `fire_spread_models.md`.
- Sharples 2024 (first pass): `fuel_load_values_fullread.md` section 9. This note adds its coefficients.
- FWI skill: `short_horizon_prediction_fullread.md`.

---

## 0. Ratapani facts that set the ceiling (computed from our files)

I computed these from `ratapani/ee/terrain.csv` (3,614 cells) and `beats/cell_beat.csv` (94 beats):

- **Elevation** across the sanctuary is 316–627 m; the mean cell is 475 m.
- **Within-beat elevation range** (max minus min cell mean): median 114 m, inter-quartile range 70–157 m, maximum 243 m.
- **Slope**: mean cell slope is 6.5° (median 5.5°, maximum 21.5°). The steepest cell in a beat has a median slope of 12°.
- **Aspect, heat load, TPI and TWI are not in `terrain.csv`.** The model has elevation and slope (mean and s.d.) only. This is a cheap gap to close (see section 9).
- **WeatherNext 3 is reachable.** `ee/weathernext_probe.txt` confirms access to `weathernext_3_0_0_0p1deg`: 0.1°, hourly, ensemble mean and p10–p90 of 2 m dewpoint and temperature, cloud, and IMERG-calibrated rain, 2024–present. WeatherNext 2 (0.25°, 6-hourly) also works. Both are "when" sources only: about one 0.1° cell per beat.

**[inference] What these numbers mean.**
- **Lapse rate.** At 6.5 °C/km, a 114 m elevation range gives about 0.7 °C of air-temperature difference inside a typical beat.
- **That is too small to matter.** On a typical peak day (38 °C, dewpoint about 8 °C, VPD about 5.6 kPa), 0.7 °C moves VPD by about 4%. Through the VPD fuel-moisture model (section 2, coefficients for FMC < 20%), fuel moisture changes by only about 0.07 percentage points.
- **So within-beat differences in air temperature and humidity are negligible in Mar–Apr.**
- **What does vary is sunlight reaching the litter surface**, through slope, aspect and canopy (sections 1, 3 and 4).
- **But slopes are gentle.** At noon in mid-March (sun elevation about 64°), direct beam on a 6.5° south slope versus a 6.5° north slope differs by about 11%; on a 15° slope, by about 23%. By mid-April (sun at about 77°), the 15° contrast falls to about 16%. A 500 m cell average smooths aspect further.
- **Bottom line: expect small gains.** They should be largest early in the season and after rain, when some cells are still above the ignition threshold and others are not.

---

## 1. Holden & Jolly 2011. Topographic effects on fuel moisture and fire danger (FULL)

Holden ZA, Jolly WM. *Modeling topographic influences on fuel moisture and fire danger in complex terrain to improve wildland fire management decision support.* Forest Ecology and Management 262:2133–2141. https://research.fs.usda.gov/treesearch/40156 (PDF: https://research.fs.usda.gov/download/treesearch/40156.pdf)

**Design**
- 140 temperature and 57 RH iButton sensors at 2 m height on the north side of trees, inside inverted-funnel shields, logging every 90 min.
- Skalkaho Basin, Montana, 16 May–29 Sep 2009.
- 30 m DEM resampled from LiDAR.
- **Cost: about US$5,500 for the whole network, and about 2 person-months to deploy and retrieve.**

**Method: PCA downscaling.** This is the part we can copy.
- PCA is run on the sensor-by-day matrix.
- The PC **loadings** (one per sensor) are mapped to terrain with random forests. Inputs are elevation plus April–October cumulative solar radiation for Tmax and RHmin, and elevation plus a multi-scale dissection index for Tmin and RHmax.
- The PC **scores** (one per day) are regressed on a single nearby weather station.
- After the sensors are removed, the station alone plus the stored loading maps reproduce daily 30 m fields, historical or in real time.

**Numbers**
- Two PCs explained 96–98% of between-sensor variance.
- Cross-validated RMSE (10% held out, 100 runs): Tmin 1.47 °C, Tmax 2.42 °C, RHmin 7.2%, RHmax 13%.
- Lapse rate ran from 4 °C/km on overcast days to 7.5 °C/km on hot, dry days.
- On the peak-danger day, valley-bottom fuel moisture was 30% higher and ERC (Energy Release Component) 45% lower than elsewhere, because of cold-air drainage and night humidity recovery.
- The driest band was 100–200 m above the valley floor, a thermal belt above the cold-air pools.
- Early in the season, ERC was up to 100% lower on north slopes, mostly because snowmelt there was up to 28 days later. Snow has no analogue at Ratapani.

**A rescaling trick worth copying.** Each day the grid is normalised to a relative index:

`RFDI = 100 × (cell − daily min) / (daily max − daily min)`

It is then rescaled so that the worst cell equals the station value. The map keeps the familiar station number and adds *where* inside the area.

**Concrete action for us**
- **Thread 1:**
  - At Ratapani, cold-air pooling and night humidity recovery in nalas and valley bottoms are the plausible within-beat signals, not snowmelt or aspect.
  - Add a cold-air-pool proxy per cell: TPI at 300 m and 1,000 m windows, or a multi-scale dissection index (cell elevation minus the mean in 3×3, 7×7 and 15×15 windows of 30 m DEM).
  - Interact it with ERA5-Land night-time wind and clear-sky flags.
- **Thread 5 (field):** a cheap iButton network plus Holden's PCA method gives us a real 30 m temperature and humidity model for Ratapani (section 10).

---

## 2. Rodrigues, Resco de Dios et al. 2024. Global test of dead fine fuel moisture models (FULL)

Rodrigues M, Resco de Dios V, Sil Â, Cunill Camprubí À, Fernandes PM. *VPD-based models of dead fine fuel moisture provide best estimates in a global dataset.* Agricultural and Forest Meteorology 346:109868. Open copy: https://zaguan.unizar.es/record/132398/files/texto_completo.pdf

**Data**
- BONFIRE database: 1,603 records of 1 h dead fuel moisture taken just before experimental fires.
- 153 experiments, 1970–2020, across 21 countries, including tropical sites.
- Records with FM above 35% were dropped.
- Calibration n = 1,049; validation n = 551, split by location (k = 3).

**Models compared**
- Operational: Simard, Van Wagner (FWI), McArthur and MK5, Nelson, FMI (Sharples 2009).
- The VPD model of Resco de Dios 2015: **FMD = FM0 + FM1·e^(−m·D)**, where D is VPD in kPa.
- Recalibrated, mixed-model, GAM, random forest and SVM versions.

**Numbers**
- Correlations with FM: RH r = 0.52, T r = −0.49, log D r = −0.56.
- Median FM in grassland was about 14%, against about 9.5% in forest, woodland and shrubland.
- Full range (4–35%), best validation results:

| Model | MAE (%) | MBE (%) | R² |
|---|---|---|---|
| SVMveg (best overall) | 3.89 | −0.94 | 0.44 |
| LMM_RH | 3.8 | −0.7 | 0.43 |
| EMP_RH_veg | 4.0 | — | 0.41 |
| FMD_veg | 4.06 | — | 0.40 |
| FMD (original) | 4.27 | — | 0.35 |
| Nelson | 4.25 | −0.47 | 0.31 |

- Below 10% FM, every model was weak. MK5 had the lowest MAE (2.36%, MBE 0.4) but R² of only 0.11. LMM_RH reached R² 0.16.
- The authors **do not recommend ML for FM**, given the small gains and extra complexity. They also say gridded ML with more predictors might be different.
- The authors name canopy cover and topographic position (solar exposure), wind, dew and fuel-bed depth as unmodelled sources of error.

**Concrete action for us**
- **Threads 1 and 4:** use a VPD exponential, refit on teak litter if we ever collect samples, or MK5 for the dry end.
- **Expectation [inference]:** Ratapani peak-season FM is probably 3–8%, where all models have R² ≤ 0.2. A fuel-moisture model will not rank cells on a peak day. Its value is on transition days (early season, after rain) when FM crosses the 15–20% ignition range.

---

## 3. Sharples et al. 2024. Simple empirical models for dead fuel moisture, with coefficients (FULL, about 90% of HTML read)

*Evaluation and comparison of simple empirical models for dead fuel moisture content.* International Journal of Wildland Fire 33(6), WF23120. https://connectsci.au/wf/article/33/6/WF23120/22131/

**Data:** ACT 10 h fuel sticks at 5 sites plus the Resco de Dios 2015 Cumberland Plains series. N = 561 days without rain (< 2 mm).

**Equations.** T is air temperature (°C), H is relative humidity (%).
- VPD = 0.6108·exp(17.27T/(T+237.3))·(1 − H/100).
- FMI = 10 − 0.25(T − H).
- FMIrel = a + b·FMI.
- FMIgen = a + b·T + c·H.
- mgen = a + b·e^(−k·VPD).

**Fitted coefficients (mean of 10-fold CV)**

| Dataset | FMIrel (a, b) | FMIgen (a, b, c) | mD (k) | mgen (a, b, k) |
|---|---|---|---|---|
| All data | 3.238, 0.688 | 10.875, −0.193, 0.165 | 0.982 | 7.803, 19.110, 0.887 |
| FMC < 20% | 5.321, 0.465 | 11.063, −0.146, 0.106 | 0.325 | 6.808, 12.245, 0.540 |
| 10–20% | 9.000, 0.304 | 14.051, −0.132, 0.058 | 0.709 | 10.003, 6.897, 0.463 |
| FMC < 10% | — | — | — | b ≈ 202, k up to ≈ 10 |

**Findings**
- FMIrel, FMIgen and mgen were best overall.
- Below 10%, "none of the models … performed particularly well". Mean R² was about 0.05, the fitted coefficients went unphysical, and the authors read this as "no VPD signal".
- The models are calibrated on 12–19 mm (10 h) sticks, not 1 h litter.

**Concrete action for us**
- **Threads 1 and 4:** default per-cell daily FM is FMIgen or mgen with the FMC < 20% row, driven by the cell's best estimate of litter-surface T and RH (section 9). Do not expect it to separate cells below 10%.

---

## 4. Nyman, Sheridan et al. (Melbourne). Aspect, drainage and canopy effects on litter moisture (FULL MODSIM paper; ABSTRACT ONLY for three EGU abstracts and IJWF 2015)

### 4a. Nyman et al. 2015, MODSIM (FULL)
*Measurement of topographic controls on the moisture content of surface fuels in south east Australian forests.* https://mssanz.org.au/modsim2015/A4/nyman.pdf

- **Design:**
  - Instrumented litter packs (24 cm diameter, 4 cm deep, 3 Vegetronix VH400 sensors each), logging every 15 min for 3 months.
  - Paired north and south aspects along an 800–1,700 mm/yr rainfall gradient.
  - Drainage areas of 0.1, 0.3 and 2 ha.
  - LSAI (leaf and stem area index) from hemispherical photos: 1.7–5.3.
- **Main conclusions:**
  1. Aspect effects on FMC come mostly from aspect's effect on canopy cover and shading, not from the direct geometry of above-canopy radiation.
  2. Drainage position works through shading and, on south slopes, through soil moisture.
  3. The aspect effect is largest at intermediate rainfall (about 1,300 mm) and small at both the wettest (closed canopy) and the driest (already open) sites.

### 4b. EGU 2015-7363, Nyman et al. (ABSTRACT ONLY)
https://meetingorganizer.copernicus.org/EGU2015/EGU2015-7363.pdf
- Daily mean litter moisture was 0.07–1.30 kg/kg on the north (sunny) slope and 0.11–1.83 kg/kg on the south.
- Days below fibre saturation (about 0.35 kg/kg): **49 on the shaded slope and 128 on the sunny slope**.
- On the warmest day (38.9 °C), litter temperature differed by 14 °C between aspects.
- Litter was also deeper on low-radiation slopes, which adds water-holding capacity.

### 4c. EGU 2014-15609 (ABSTRACT ONLY)
https://meetingorganizer.copernicus.org/EGU2014/EGU2014-15609.pdf
- Shortwave radiation at the forest floor was **up to 6 times higher** on the sunny, sparse slope.
- On a day with 35.5 °C open air: litter was 54.3 °C on the sunny slope and 32.1 °C on the shaded slope, while air differed by less than 2 °C. Minimum litter water content was 21% against 85%.

### 4d. EGU 2015-4191 (ABSTRACT ONLY)
https://meetingorganizer.copernicus.org/EGU2015/EGU2015-4191.pdf
- Design for downscaling 5 km gridded weather with a 20 m DEM and vegetation structure.
- Stations: 5 on an aspect gradient, 7 on drainage position, 15 on elevation, 6 on canopy cover.

### 4e. Slijepcevic et al. 2018, IJWF 27:190 (ABSTRACT ONLY)
https://doi.org/10.1071/WF17049
- The aspect effect averaged about 3% FM in dry forest and 11% in moist forest.
- Top litter (first 1 cm) was about 4% wetter than bark and about 3% drier than the whole litter profile.

**Concrete action for us**
- **Thread 1.** The mechanism is "sunlight reaching litter", not "air humidity". Inside a beat, that depends on slope, aspect, canopy and leaf-off date together.
- **Why it is plausible for Ratapani [inference].**
  - In Mar–Apr the teak canopy is leafless, so under-canopy radiation approaches open-sky values everywhere teak dominates.
  - Cells with evergreen or semi-evergreen patches, riparian strips and later leaf-shedding species stay shaded.
  - That contrast, not aspect, is likely the bigger within-beat driver here.
- **Feature: daily litter-surface radiation per cell.**
  - Formula: `R_floor = R_slope(DOY, hour, slope, aspect) × τ`, with `τ = exp(−0.5 × PAI)`.
  - Take PAI from the Sentinel-2 series (SNAP LAI, or an NDVI-to-LAI fit) for the most recent clear date.
  - Sum R_floor over 10:00–16:00 IST and over the last 3 days.
- **Expected effect:** small to medium. The model already has NDVI, NDMI and slope and may learn part of this, but not the sun-geometry interaction by day of year.

---

## 5. Ohlson, Hoffman & Tinkham 2025. Fine-scale space-time structure of dead fuel moisture (FULL)

*Spatiotemporal dynamics of fine dead surface fuel moisture content in a Colorado mixed-conifer forest.* IJWF 34, WF25086. Open access. https://doi.org/10.1071/WF25086

**Design:** 80 locations in a 17.6 ha stand, sampled 21 times (about weekly) through summer, by gravimetric FMC.

**Numbers**
- Median FMC was 9%, 34% and 14% in early, mid and late summer.
- 14%, 55% and 19% of observations were above the 30% moisture of extinction.
- **About 85% of spatial semivariance occurs within the first 10 m.** About 80% of temporal semivariance occurs within 20 days.
- A GAM explained 35.4% of deviance (adjusted R² 0.33). Its terms were understory cover, canopy cover in a 2 m radius, McCune & Keon heat load index (folded aspect `180 − |aspect − 180|`, 1 m DEM) and 6-day antecedent rain.
- Expected FMC rises from about 10% to about 18% across the understory-cover range, and from about 11% to about 16% with canopy cover. It falls from about 16% to about 12% across the heat-load range.
- Spatial variability shrinks in dry periods.

**Concrete action for us**
- **Threads 1 and 4 (a warning).** Most fuel-moisture variance is at 1–10 m scales. A 500 m cell mean averages it out.
- **What survives at 500 m** is the systematic part: heat load, canopy, understory green cover. That part is about 4–6 FM points in Ohlson's data, and smaller when it is dry.
- **Spread thread:** the within-stand patchiness justifies a stochastic FM field (e.g. ±2–4% noise at 10–30 m) in spread runs.

---

## 6. Dorph et al. 2022. Does fuel moisture predict where ignitions happen? (FULL)

Dorph A, Marshall E, Parkins KA, Penman TD. *Modelling ignition probability for human- and lightning-caused wildfires in Victoria, Australia.* NHESS 22:3487–3499. https://nhess.copernicus.org/articles/22/3487/2022/

**Design**
- Random forests on infrastructure, topography, climate, soil moisture, live FM (annual) and dead FM (annual, Nolan 2016b method), plus local FFDI.
- Ignitions 2000–2019 against random points.

**Numbers**
- Human-caused models classified 86.4% and 90.3% of points correctly, in the matrix and in native forest.
- **Human-caused ignitions were driven by infrastructure and local weather.**
- Dead FM mattered for both causes, with a **threshold: ignition probability is elevated below about 20% dead FM and near zero above it.**
- Live FM had little effect.
- The authors say adding FM did not raise accuracy much compared with similar studies (AUC 84.6–88.3 elsewhere).

**Concrete action for us**
- **Thread 1:** this is the best evidence I found that fuel moisture enters an ignition-location model.
- **But it is weak support for *within-beat* weather.** The FM layer was coarse, and human fires were driven by access.
- **Use the 20% threshold as a feature shape:** a per-cell flag "estimated dead FM < 20% on day t−1, t", or hours since dropping below 20%.

---

## 7. microclimf / microclimc (Maclean) and related tools: mechanistic under-canopy microclimate (FULL preprint of microclimf; PARTIAL R guide)

### 7a. Maclean (2025/26), microclimf (FULL, EcoEvoRxiv preprint)
https://ecoevorxiv.org/repository/view/9159/ . Published version: doi 10.1111/2041-210x.70253 (not read). Code: https://github.com/ilyamaclean/microclimf (GPL-2; install with `devtools::install_github("ilyamaclean/microclimf")`).

**What it does**
- Hourly gridded temperature, humidity, wind and radiation above, within and below canopy and in soil.
- Two-stream radiation (Dickinson–Sellers) with terrain shading and slopes.
- Simplified Lagrangian below-canopy transfer.
- Soil moisture distributed by topographic wetness (`soilmdistribute`).
- Terrain wind sheltering (`wind`).

**Validation**
- Finland, 150 TOMST loggers at 15 cm height: RMSE 2.9 °C overall (2.2–3.2 °C by site).
- **70 tropical forest sites (Trew et al. 2024): RMSE 2.73 °C, better than the raw macroclimate difference (3.62 °C).**
- Spain 1.105 °C, Cornwall 0.690 °C.
- 36 under-canopy loggers at 1 m: 1.477 °C (macroclimate 1.765 °C).
- Humidity validation is not reported in the sections I read.

**Inputs**
1. Hourly forcing as one series or a coarse grid: T, humidity, pressure, wind, radiation, rain. ERA5-Land works.
2. DEM.
3. Soil type or ground reflectance.
4. Vegetation height and plant area index, static or seasonal.

The companion `microclimdata` package downloads inputs globally.

**Workflow and settings**
```r
mp  <- runpointmodel(climdata, reqhgt = 0.05, dtm, vegp, soilc)   # point model at area centre
mout <- runmicro(mp, reqhgt = 0.05, vegp, soilc, dtm)             # grid, 5 cm above ground
# or runbioclim / runbioclim_big for summary variables; mosaicblend for tiles
```
- `reqhgt` is the output height in metres. Negative values mean below ground.
- Outputs are `terra` multi-layer rasters: air and leaf temperature, RH, wind, radiation, soil temperature.

### 7b. Maclean, Soifer & Klinges, "The ecologist's guide to microclimate modelling and thermal biology in R" (PARTIAL)
https://ecoevorxiv.org/repository/object/13225/download/23381/
- Tutorial with the `microclimlearn` and `micropoint` packages.
- Key point for us: inputs must be **hourly**. Daily means bias results (Jensen's inequality).

### 7c. Other tools (ABSTRACT ONLY or from memory)
- **Trew et al. 2024, Nature Climate Change 14:753.** Hourly below-canopy temperature at 300,000 tropical forest points, 1990–2019, with microclimf.
- **De Frenne et al. 2019, Nat. Ecol. Evol. 3:744.** 98 paired sites: canopy buffering of maximum temperature grows as open-air temperature rises.
- **ForestTemp (Haesen et al. 2021, GCB).** 25 m monthly sub-canopy offsets, **Europe only**. Not usable for India.
- **ForEdgeClim v1.0 (Van de Walle et al. 2026, GMD 19:4661).** 3D edge-to-core model; headline only. Edge effects could matter at village-forest edges [inference].

**Concrete action for us**
- **Thread 1 (medium effort, small expected gain).** Run microclimf for one season as a test.
- **Settings:**
  - Forcing: our ERA5-Land hourly points.
  - Grid: 30 m (SRTM or ALOS DEM).
  - Vegetation height: from the GEDI-derived canopy height map.
  - PAI: from monthly Sentinel-2 LAI (leaf-off in Mar–Apr).
  - Height: `reqhgt = 0.05`.
  - Hours: 10:00–16:00 IST only.
- **Outputs to summarise to 500 m:** daily max T(5 cm), min RH(5 cm), VPD(5 cm) and floor shortwave. Take the cell mean and the 90th percentile.
- **Test:** do these add rank-skill over NDVI × slope?
- **Caution [inference]:** most of microclimf's spatial signal at Ratapani will be PAI × sun geometry, which a much cheaper radiation-only feature (section 9, item 1) captures. Run the cheap version first. Only run microclimf if the cheap version shows signal.

---

## 8. Fuel moisture sensors: 10 h sticks and alternatives (FULL)

### 8a. Cawson et al. 2020, IJWF 29:548 (FULL, plus corrigendum)
*Estimation of surface dead fine fuel moisture using automated fuel moisture sticks across a range of forests worldwide.* https://doi.org/10.1071/WF19061 (open via Minerva Access)

- **Data:** 27 sites, 570 paired samples, 9 forest-fuel categories (pine, beech, chestnut, eucalypt). No tropical sites.
- **All data:** surface FFMC = −32.03 + 4.68 × stick moisture; R² 0.54, RMSE 46.
- **Dry range (FFMC < 35%):** FFMC = 5.10 + 0.86 × stick; R² 0.18, RMSE 7.
- **Fuel-specific fits:** median R² 0.70 (range 0.55–0.87).
- **Sticks generally underestimate litter moisture** and need a calibration for each fuel. The authors call them a "coarse indicator".

### 8b. Zhao, Yebra, Cary & Hughes 2026, IJWF 35(4), WF25174 (FULL via publisher HTML)
*Evaluation of a 10-h fuel stick and a moisture meter for measuring fine dead fuel moisture and response times.* https://doi.org/10.1071/WF25174

Lab test at 22 °C, RH 6–95%:

| Fuel | Instrument | R² | MAE (%) | MBE (%) | RMSE (%) |
|---|---|---|---|---|---|
| Eucalypt litter | Wiltronics meter | 0.96 | 1.76 | −1.32 | 2.65 |
| Eucalypt litter | 10 h stick | 0.93 | 3.01 | −2.75 | 3.47 |
| Cured grass | Wiltronics meter | 0.92 | 2.07 | 0.43 | 2.61 |
| Cured grass | 10 h stick | 0.89 | 3.96 | −3.47 | 4.44 |

- 10 h stick response times: 19.7 h when wetting, 8.9 h when drying.
- Litter response times: 11.2 h wetting, 2.8 h drying.

**Concrete action for us**
- **Thread 5:** if Ratapani installs any fuel-moisture sensing, put sticks in pairs (sunny open vs shaded, ridge vs nala).
- Calibrate against oven-dried teak leaf litter: at least 30 samples, 105 °C. Matthews 2010 shows that < 105 °C under-reads, as cited in Rodrigues 2024.
- A 10 h stick lags litter by hours, so read it at 14:00 IST.
- A handheld meter (Wiltronics-type) is the cheaper way for field staff to spot-check litter in the 9–16% range [inference: price and availability in India not checked].

---

## 9. What to compute per 500 m cell (concrete feature list for thread 1)

All are computed on 30 m pixels first, then summarised to the cell as the mean and the 90th percentile. Ranked by expected value per effort **[inference throughout]**.

1. **Static terrain additions** (missing today):
   - `northness = cos(aspect)` and `eastness = sin(aspect)`.
   - McCune & Keon heat load index (folded about 225° for the hot south-west, eq. 3 of McCune & Keon 2002, latitude 23.2°).
   - TPI at 300 m and 1,000 m.
   - Multi-scale dissection (Holden).
   - TWI from a 30 m DEM, with flow accumulation from `richdem` or `whitebox`.
   - Effort: under 1 day.
2. **Daily floor radiation.**
   - `R_floor(t) = Σ_{10–16 h} R_beam·cos(incidence) + R_diffuse·SVF`, multiplied by `τ = exp(−0.5·PAI_S2)`.
   - Take R_beam and R_diffuse from ERA5-Land `surface_solar_radiation_downwards_hourly`, split into beam and diffuse with a clearness-index model (e.g. Erbs). Compute incidence from sun position on day t.
   - Use the last 1-day and 3-day sums.
   - Effort: 1–2 days.
3. **Cell litter-surface temperature and RH proxy.**
   - `T_s = T_air + c·R_floor`, with c ≈ 0.02–0.03 K per W/m² as a starting value. Tune c so the 38 °C-air sunny-litter case gives about 50–55 °C, matching Nyman's 54 °C at 35 °C air.
   - `RH_s = e_a / e_s(T_s)`, using ERA5-Land dewpoint for e_a.
   - Effort: half a day after item 2.
4. **Cell dead FM (daily minimum).**
   - FMIgen (`11.063 − 0.146·T_s + 0.106·RH_s`) or mgen (`6.808 + 12.245·e^(−0.540·VPD_s)`), using the FMC < 20% coefficients from section 3.
   - Plus a time-lag drying bucket after rain, with the Nelson or Matthews physics if time allows: wetting time constant about 11 h and drying about 3 h for litter (Zhao 2026).
   - Rain from ERA5-Land or WeatherNext IMERG-calibrated rain.
   - Effort: 1–2 days.
5. **Threshold features.**
   - `FM_cell < 20%` flag (Dorph 2022).
   - `days since FM_cell first < 20%` this season.
   - `FM_cell − beat median FM_cell`. This is the within-beat rank, which is what the 2-day ranker needs.
6. **Night recovery proxy.** TPI-low cells × (night clear sky and calm wind from ERA5-Land, 18–00 UTC) gives a cold-air-pool, high-humidity flag (Holden 2011). Effort: half a day.
7. **Optional mechanistic run.** microclimf at 30 m, `reqhgt = 0.05`, one season, outputs as in section 7. Effort: 1–2 weeks of setup and compute.

**Expected gain for the 2-day "where" problem**

My estimate [inference] is **+0 to +2 percentage points of recall at 5 picks per beat per day** over the current 29.5%. The gain should be concentrated in:
- January–February;
- the 3–10 days after rain;
- beats with real slopes (beat slope maximum above 12°, about half of the beats).

**Reasons for the low ceiling:**
- Within-beat air temperature and humidity differences are about 0.7 °C (section 0).
- Peak-season FM is below 10%, where no model has skill (sections 2 and 3).
- Most FM variance is below 10 m (section 5).
- Human access drives location (Dorph 2022; `human_fire_drivers.md`).

**How to test cheaply:**
- Add items 1–5 and retrain LightGBM with the same LOSO split (leave one season out).
- Report recall separately for (a) Jan–Feb, (b) post-rain windows, (c) Mar–Apr dry days.
- A gain only in (a) or (b) is still useful operationally, because those are the days when spending patrol effort on location matters most.

---

## 10. A field microclimate network for Ratapani (thread 5, also yields training data for thread 1)

[inference, built on Holden & Jolly 2011 and the Nyman design]

- **Loggers:**
  - 30–40 temperature/RH loggers (iButton DS1923-class or similar) in radiation shields at 0.3 m, plus 10–20 temperature-only loggers placed in the litter.
  - Stratify by canopy (leafless teak vs evergreen or riparian), position (nala bottom, mid-slope, ridge) and aspect (N vs S where slopes exceed 10°).
  - 2–3 beats, Jan–Jun 2027.
- **Fuel moisture:** 6–10 paired 10 h sticks, or weekly meter readings plus 30+ oven-dry teak litter samples for calibration.
- **Analysis:** Holden's PCA downscaling. Map loadings to TPI, dissection, floor radiation and PAI; regress scores on ERA5-Land or the nearest IMD AWS (Bhopal).
- **Reference cost:** Holden's 140 T + 57 RH network cost about US$5,500 and took about 2 person-months.
- **Output:** a validated 30 m daily Tmax, RHmin and night-recovery model for Ratapani. Without it, items 3 and 4 in section 9 stay uncalibrated guesses.

---

## 11. TOPOFIRE (Holden et al. 2019, BAMS 100:1607). An operational topographic fire-danger system (FULL)

https://par.nsf.gov/servlets/purl/10192094 . Live system: https://topofire.dbs.umt.edu

- **Daily ~250 m (8 arc-second) grids** of temperature, dewpoint and downward shortwave for the US.
- Built from CFSR plus URMA (US surface analysis), plus GOES radiation, terrain covariates (local lapse rates, radiation × soil moisture interaction, cold-air drainage potential) and bias correction against MADIS stations each morning.
- The grids feed NFDRS fuel moistures and ERC, normalised to a 2001–17 climatology as percentiles.
- 4-day forecasts come from NDFD.
- **Note for the spread thread:** FARSITE's built-in topographic fuel conditioning uses a fixed 6.0 °C/km lapse rate and 8 aspect classes, applied only for the 2 weeks before ignition.

**Concrete action for us**
- **Thread 5:** TOPOFIRE shows the deliverable form: a daily relative fire-danger map inside the area, anchored to one station value (see also Holden 2011's RFDI).
- For a beat officer: "today's beat FWI from WeatherNext" plus "where inside the beat it is driest", from section 9 items 2–5.

---

## 12. High-resolution forecast and reanalysis products over India

**[inference] Common point:** none of these resolves a 500 m cell. At 3–6 km there are 1–4 grid points per beat. They improve "when", and possibly between-beat contrasts and patchy pre-monsoon showers, not within-beat ranking.

| Product | Resolution and run | Archive and access | Status of my check |
|---|---|---|---|
| **NCUM-G** (NCMRWF global UM) | 12 km, 70 levels, 10-day, 4 cycles/day, hybrid 4DVar | Charts only on ncmrwf.gov.in; files on request | NCMRWF IWM8 slides, Mar 2025 (FULL) |
| **NCUM-R** regional | 4 km India (operational year-round). 1.5 km Delhi and 330 m Delhi run in winter for fog only | Charts; no public file archive found | NCMRWF 2022 write-up via search summary (PARTIAL); 4.05 km domain details in IWM8 slides |
| **NCUM-R ensemble** | 4 km, 12 members, 3-day (experimental since 2019) | Not public | IWM8 slides (FULL) |
| **NEPS-G** global ensemble | 12 km, 22 members (since 2018) | Not public | IWM8 slides |
| **NCUM 6 km global** (experimental) and **BharatFS** (IITM/IMD) | 6 km global tropics, 10-day, operational since 26 May 2025 | "BharatFS portal" (real-time outputs); data policy not found | IITM Newsletter July 2025 (PARTIAL) |
| **IMD GFS T1534** | ~12 km | nwp.imd.gov.in charts; no open GRIB found | Search only |
| **IMD WRF** | 27/9/3 km nests | IMD web charts; 3 km files not public | MoES 2017 parliamentary answer (search only) |
| **IMDAA reanalysis** | 0.12° (~12 km), hourly 2D, 3-hourly 3D, 1979–2020; "IMDAA-like" products after 2020 from NCUM-G 12 km | **https://rds.ncmrwf.gov.in**: register, verify e-mail, submit request; 4,650+ users | IWM8 slides (FULL); dashboard (search) |
| **WeatherNext 3** (Google) | 0.1°, hourly, ensemble percentiles, 2024– | Earth Engine `projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p1deg` (**our access confirmed**) | `ee/weathernext_probe.txt` |
| **INSAT-3DR LST** (`3RIMG_L2B_LST`) | 4 km, half-hourly, since 11 Oct 2016 | MOSDAC, registered research users (doi 10.19038/SAC/10/3RIMG_L2B_LST); INSAT-3DS daily min/max LST `3SIMG_L3B_LST` | Catalogue entry via search (ABSTRACT ONLY) |
| **IMD Bhopal S-band Doppler radar** | ~1 km reflectivity, every 10–15 min; Ratapani is about 30–60 km away | Viewable on IMD urban met pages; raw volumes by request (PyScanCf reads IMD files) | Search only |

**Concrete actions**
- **Thread 1 ("when", low effort):** none of the NWP products beats WeatherNext 3, which we already have, for operations. Use IMDAA hourly (1979–2020) only if we want a longer climatology for FWI percentiles than ERA5-Land.
- **Thread 1 ("where", rain only):**
  - Pre-monsoon (Apr–Jun) thunderstorm showers are km-scale, and a shower resets litter moisture for 1–3 days.
  - The Bhopal radar is the only source that could map which beats got wet. A test: request DWR Bhopal volumes for 2–3 seasons and compute daily rain-or-no-rain per cell. Check whether fires avoid recently wetted cells.
  - Expected gain: small, May–June only [inference].
- **Thread 5:** INSAT-3DR half-hourly LST could time the afternoon heating peak, but 4 km is not "where".

---

## 13. AI weather downscaling in India (searches; ABSTRACT ONLY)

- **CorrDiff** (Mardani et al., arXiv 2309.15214; NVIDIA PhysicsNeMo `examples/weather/corrdiff`):
  - Trained 25 km ERA5 → 2 km WRF over Taiwan.
  - At least 22× faster and about 1,300× more energy-efficient than the numerical model.
  - Time coherence is not guaranteed.
  - **I found no Indian application.**
- **Indian ML downscaling** is almost all rainfall to 0.25° (DeepSD, SR-GAN on IMD data: arXiv 2011.11313, 2207.00808).
- **Benchmarks:** IndiaWeatherBench (arXiv 2509.00653, IMDAA-based, code at `tung-nd/IndiaWeatherBench`) and a Pangu-on-IMDAA forecaster (arXiv 2503.12956) work at about 12 km.
- **Google–IMD:** no WeatherNext–IMD partnership found. The 2020 Google–ClimaCell "CBAM India" 2 km model was announced but its status is unknown.

**Concrete action for us**
- None for "where". km-scale AI downscaling would at best reproduce 2–4 km structure, still coarser than a cell. Terrain and canopy physics (section 9) is the route to sub-km detail. Do not spend effort here.

---

## 14. Other sources checked

- **Nolan et al. 2016, RSE (ABSTRACT ONLY).** VPD from MODIS gave dead suspended FM with MAE < 3.9%, against < 6.0% from gridded weather. VPD was under-predicted where LAI is low.
  - Action: a MODIS-LST VPD variant fits `open_datasets.md` B9. Use LST minus air temperature as an extra input to item 3 in section 9.
- **Resco de Dios et al. 2015, AFM 203:64 (ABSTRACT ONLY).** Built on 10 h fuel sticks (1.9 cm dowels) logging every 30 min. MAE 3.7% overall, 2.9% below 20% FM and 1.8% below 10% FM.
- **Matthews 2006, IJWF 15:155 "Koba" (ABSTRACT ONLY).** First complete process-based litter-layer model (energy and water budgets). Right at minimum and maximum in dry mallee; over-predicts surface wetting in rain.
- **Indian aspect or fire studies (ABSTRACT ONLY).**
  - An eastern India frequency-ratio study (Remote Sensing 2023, 15:1340) found west and south-west aspects and moderate slopes most fire-susceptible.
  - Jhariya 2017 (in `fuel_load_values_fullread.md`): south and west aspects burn more at Bhoramdeo.
  - **No Indian study measuring litter moisture by aspect or canopy was found.**

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| ERA5-Land hourly | `ECMWF/ERA5_LAND/HOURLY` (GEE) | 0.1°, hourly | 1950– | Copernicus free | Already exported (`ee/era5land_*`) |
| WeatherNext 3 | `projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p1deg` | 0.1°, hourly, ensemble percentiles | 2024– | Google terms (research) | GEE, access confirmed |
| IMDAA | https://rds.ncmrwf.gov.in | 0.12°, hourly 2D | 1979–2020 (+ IMDAA-like) | Free, registration | Register, then request |
| NCUM-G / NCUM-R / NEPS | ncmrwf.gov.in | 12 km / 4 km | operational | Not open | Charts; formal request |
| BharatFS | IITM/IMD BharatFS portal | 6 km | May 2025– | Not stated | Portal; request files |
| INSAT-3DR LST `3RIMG_L2B_LST` | https://mosdac.gov.in/doi/190 | 4 km, 30 min | Oct 2016– | Research use, registered | MOSDAC order |
| IMD DWR Bhopal | mausam.imd.gov.in | ~1 km, 10–15 min | ~2010s– | IMD policy | Request to RMC; PyScanCf to read |
| microclimf + microclimdata | github.com/ilyamaclean/microclimf | user grid (1–30 m) | — | GPL-2 | `devtools::install_github` |
| BONFIRE fuel moisture database | via Rodrigues 2024 / Fernandes | 1,603 records | 1970–2020 | See paper | For FM model refits |
| Sentinel-2 L2A (for PAI / LAI) | `COPERNICUS/S2_SR_HARMONIZED` | 10–20 m | 2017– | Free | GEE |
| SRTM / ALOS DEM | GEE | 30 m | static | Free | GEE (aspect, HLI, TPI, TWI) |

---

## Ranked action list

Gain estimates are mine [inference]. "Recall" means recall at 5 picks per beat per day.

| # | Action | Thread | Expected gain | Effort |
|---|---|---|---|---|
| 1 | Add aspect (northness, eastness), McCune–Keon heat load, TPI 300/1,000 m, multi-scale dissection and TWI per cell (30 m → 500 m mean and p90) | 1, 4 | 0–1 pp recall; also fills the missing-aspect gap | < 1 day |
| 2 | Daily floor radiation `R_floor` (ERA5-Land SSRD split into beam and diffuse × incidence on slope × exp(−0.5·PAI_S2)), 1-day and 3-day sums | 1 | 0–1.5 pp, mostly Jan–Feb and teak vs non-teak cells | 1–2 days |
| 3 | Cell litter-surface T and RH proxy, then FMIgen or mgen dead FM (FMC < 20% coefficients), drying bucket after rain, FM < 20% flags, within-beat FM rank | 1, 4 | 0–1 pp overall; possibly more on post-rain days | 1–2 days |
| 4 | Evaluate gain by period (Jan–Feb, post-rain, Mar–Apr dry) in LOSO | 1 | Tells us whether "where-weather" is worth more work | half a day |
| 5 | Field network: 30–40 T/RH loggers plus litter-temperature loggers in 2–3 beats, Jan–Jun 2027, plus 30+ oven-dry teak litter samples; Holden PCA downscaling | 5 → 1, 4 | Calibrates items 2–3; gives the first measured teak-litter FM series in central India | ~US$5–6k and 2 person-months (Holden benchmark) |
| 6 | Use WeatherNext 3 ensemble (24/48 h) for the beat-level "when" and a TOPOFIRE-style relative map for "where" in the officer alert | 5 | Better alert framing | 1–2 days |
| 7 | Bhopal DWR rain-or-no-rain per cell for Apr–Jun; test fire avoidance of recently wetted cells | 1 | Small, May–June only | 1–2 weeks (data request is the bottleneck) |
| 8 | microclimf 30 m run (`reqhgt = 0.05`, 10–16 h, one season); test daily Tmax, RHmin and VPD at 5 cm | 1 | Probably ≤ items 2+3; run only if they show signal | 1–2 weeks |
| 9 | Spread runs: stochastic FM field ±2–4% at 10–30 m, plus aspect and canopy adjustment instead of FARSITE's 8-class rule | 4 | Realistic patchiness | 1 day |
| 10 | IMDAA, NCUM, BharatFS, IMD WRF, CorrDiff for "where" | — | ~0 at 500 m | skip |

**Reading tally:**
- **FULL (11):** Holden & Jolly 2011; Rodrigues et al. 2024; Sharples et al. 2024; Nyman et al. 2015 MODSIM; Ohlson et al. 2025; Dorph et al. 2022; microclimf preprint; Cawson et al. 2020; Zhao et al. 2026; TOPOFIRE 2019; NCMRWF IWM8 slides 2025.
- **PARTIAL (2):** Maclean et al. R guide; IITM Newsletter July 2025.
- **ABSTRACT ONLY or catalogue (about 14):** three EGU abstracts, Slijepcevic 2018, Resco de Dios 2015, Nolan 2016, Matthews 2006, De Frenne 2019, ForestTemp, Trew 2024, CorrDiff, MOSDAC LST entry, IndiaWeatherBench, eastern India FR study.
