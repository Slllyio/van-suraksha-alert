# Leaf fall and dryness phenology as a fire-timing signal (scouting, round 3)

Scope: leaf-fall timing of teak and the dry deciduous community; satellite phenology products and smoothing methods; near-real-time "fraction of canopy dropped" and "days since leaf fall"; published links between leaf fall or greenness decline and fire; whether early-season fires are held back by green understory; and how to tell leaf fall from burn. Written 14 Oct 2026.

Reading status key: **FULL** = whole text read; **PARTIAL** = parts of the full text read; **ABSTRACT ONLY** = abstract or index record only. My own reasoning is marked **[inference]**.

Overlap with existing notes:
- The AD (annual deciduousness) metric of Singh & Jeganathan 2020 is already in `fuel_load_values_fullread.md` §8.
- So are the Saha fuel build-up curve and the Mudumalai phenology.
- The leaf-fall negative class and NBR detrending for scars are in `alert_burn_scars_fullread.md` §9.

These are not repeated here; this note builds on them.

---

## Headline findings

1. **Nobody has published a per-pixel "leaf-fall date leads to fire date" lag for India, Southeast Asia, the Cerrado or miombo.** I searched for this in many forms. The closest evidence:
   - month-level co-timing (Cambodia, Mudumalai, Satpura);
   - one global model in which a recent greenness drop (low now, high a month ago) raises burnt area (Kuhn-Régnier 2021).

   Ratapani's own VIIRS dates plus S2/HLS can measure this lag directly. That would be a new result (§C).
2. **Ground dates for teak leaf fall in western central India: 10 Feb 2004, 6 Mar 2014, 23 Mar 2016.** This is the date when crown leaf cover fell below 5%. A wet monsoon year delayed it by 24 days on the ground (37 days by MODIS) (Malhi 2021). In other words, the previous monsoon moves the date by about a month.
3. **Leakage risk.** Offline smoothing (Whittaker, Savitzky–Golay, TIMESAT) uses observations after the forecast date. Any smoothed NDVI feature in the 2-day model must therefore be computed in "hindcast" mode, using only data available at the time. BOKU's operational Kenya system shows how (Klisch & Atzberger 2016).
4. **Feature recipe to copy.** The MCD12Q2 product defines senescence onset, midpoint and dormancy as the dates the smoothed EVI2 crosses 90%, 50% and 15% of the greendown amplitude. "Fraction dropped" = (peak − now) / (peak − dormant floor) is the same quantity, and is the same idea as Australia's operational grass "curing" from Relative Greenness.
5. **Burn vs leaf fall.**
   - Leaf fall is a smooth decline over weeks; senescence lasted 39 days in a Gir PhenoCam record (abstract only). Fire is a step change between two looks a few days apart.
   - Fire darkens NIR, which dry vegetation does not.
   - NDVI separates burns poorly over dry senescent vegetation. The 20 m NIR, red-edge and SWIR bands separate best (Huang 2016).
   - Burn signals in South and Southeast Asia fade fastest of any region; the global median persistence is 29 days (Melchiorre & Boschetti 2018).

---

## A. Field phenology of the species (timing and drivers)

### A1. Malhi et al. 2021, *Remote Sensing* 13:3343. Teak phenology from MODIS NDVI, validated on the ground. **FULL**
Link: https://www.mdpi.com/2072-4292/13/17/3343

- **Site and method.**
  - Dry deciduous teak forest, Narmada district, Gujarat (21.86 N, 73.56 E).
  - Ground data: ten 30 × 30 m teak patches, visited every 20–25 days from May 2013 to April 2014, plus a 2003–04 report.
  - Crown score: 1 = phenophase present on <5% of crown (counted as "leaf fall"), 2 = 5–25% (leaf initiation), 3 = >25% (maximum greenness).
- **Satellite.** MODIS NDVI at 500 m and 16 days, smoothed with Tukey running medians. RMSE was 0.042, better than single or double exponential smoothing. SOS and EOS were taken as the days of maximum and minimum NDVI ratio (derivative method).
- **Dates (Table 1).**

  | Year | Ground EOS (leaf fall, <5% crown) | MODIS EOS | Ground SOS | MODIS SOS |
  |---|---|---|---|---|
  | 2003–04 | 10 Feb | 13 Feb | 22 Jul | 28 Jul |
  | 2013–14 | 6 Mar | 22 Mar | 30 Jul | 11 Aug |
  | 2015–16 | 23 Mar | — | 1 Aug | — |

- **Shifts.**
  - In 2013–14, SOS was 14 days later and EOS 37 days later by satellite; in situ leaf fall was 24 days later.
  - Season length grew from 200 to 224 days.
  - 2013 was a strong monsoon year **[inference from the regional record, not stated in the paper]**.
- **Concrete action for us (2-day model, fuel map).**
  - Expect Ratapani teak (about 23° N, 1,100–1,200 mm rain) to reach its leafless state between mid-February and late March, varying by year by about ±3–5 weeks.
  - Model this year-to-year shift explicitly. Use a per-year "d50 anomaly" (see §F), or at minimum the previous monsoon's total and withdrawal date as season-level inputs.
  - Expected effect: better early-season (Feb–Mar) ranking in years with early or late leaf fall.

### A2. Singh & Kushwaha 2006, *Annals of Botany* (PMC2803360). Deciduousness classes at Hathinala, Vindhyan dry tropical forest. **FULL** (PMC HTML)
Link: https://pmc.ncbi.nlm.nih.gov/articles/PMC2803360/

- **Site.** About 1,035 mm rain, 85% of it in the monsoon, with 7–8 dry months. Day maximum is 20 °C in January and 42 °C in June. Monthly counts were made on 160 tagged twigs on ten trees per species, over two annual cycles.
- **Deciduousness classes (the species list is the useful part for us).**

  | Class | Species |
  |---|---|
  | Semi-evergreen | *Shorea robusta* |
  | <2 months deciduous | *Diospyros melanoxylon*, *Anogeissus latifolia*, *Hardwickia binata* |
  | 2–4 months deciduous | *Terminalia tomentosa*, *Lagerstroemia parviflora*, *Acacia catechu* |
  | >4 months deciduous | *Boswellia serrata*, *Lannea coromandelica* |

- **Timing details.**
  - *Boswellia* and *Lannea* flower on leafless twigs in December–March, about 1–3 months after leaf fall ends. Their leaf fall therefore ends around October–January, early in the dry season.
  - *Diospyros* flushes and flowers in the hot dry period (April–May).
  - The leafless period reflects "an integrated effect of seasonal drought, tree characteristics and soil moisture conditions".
- **Concrete action for us (fuel map, 2-day model) [inference].**
  - The community does not drop leaves at once. *Boswellia* and *Lannea* patches go bare first (Nov–Jan). Teak and *Terminalia*/*Lagerstroemia* follow (Jan–Mar). *Anogeissus* and *Diospyros* stay leafy longest.
  - Fraction dropped per 500 m cell therefore depends on species mix. A *Boswellia*-rich ridge can carry dry litter two months before a teak valley.
  - Use per-pixel d50 (not a calendar flag) to capture this.
  - The companion paper Kushwaha et al. 2010 (*Ann. For. Sci.* 67:310; 24 species, leaf-fall start and end dates) was blocked by bot walls at HAL, Springer and AFS. It holds the exact per-species dates and is worth fetching by hand: https://hal.science/hal-00883607. **ABSTRACT ONLY**

### A3. Pande et al. 2002 (Satpura teak litterfall). Ghosh et al. 2020 (teak and rainfall). Patasaraiya et al. 2021 (Satpura teak). **ABSTRACT ONLY**
Links:
- Ghosh: https://doi.org/10.1007/s10661-019-7680-0
- Patasaraiya: *Forest Science* 67(2):192–204

What the abstracts say:
- Pande: leaf fall peaks in **January and March**; a defoliator outbreak caused September leaf fall (already in the fuel note).
- Ghosh: MODIS EVI 2000–2013 with TIMESAT. Teak SOS falls in July–August. Moist teak's season is about 48 days longer than dry teak's. Pre-season rainfall vs SOS gives R² = 0.57–0.72. The abstract says nothing about EOS and rainfall.
- Patasaraiya: teak NDVI responds more to maximum temperature than to rainfall.

**Concrete action for us [inference]:**
- Add March–April maximum temperature (ERA5/POWER, already in the model) as an interaction with fraction dropped.
- Hot spells speed the last stage of leaf drop and litter drying.

### A4. Western Ghats leaf phenology drivers, 2025 (*ScienceDirect* S2666719325000871). **ABSTRACT ONLY**
- MODIS NDVI and PhenoCam.
- Leaf fall in tropical semi-evergreen forest advanced 13 days per decade. Dry deciduous and thorn forest seasons lengthened by 7 days per decade.
- Senescence is driven mainly by maximum temperature and PAR.
- Use for us: climate drift in leaf-fall timing means a fixed calendar feature will decay. Per-year satellite timing avoids this.

### A5. SeasonWatch citizen phenology (NCF), GBIF dataset d85d848d-791e-4055-bda5-32c16619ab21. **Data accessed directly**
Links:
- Dataset: https://www.gbif.org/dataset/d85d848d-791e-4055-bda5-32c16619ab21
- Paper: Ramaswami et al. 2021, *Current Science*; bioRxiv 10.1101/2020.08.28.271155

**Record counts:**
- There are **42,724 teak records** nationally.
- 256 are in Madhya Pradesh.
- 28 fall in a Bhopal-area box (22.5–23.8 N, 77–78.6 E).

Each record has a weekly-style score of None / Few / Many for `leavesFresh`, `leavesMature` and `leavesOld` (dying leaves), plus flowers and fruits.

My quick tabulation of 634 teak records in 18–26 N, 72–84 E (all years). These are mostly roadside or campus trees, so they are probably later than forest trees:

| Half-month | n | Share with no mature leaves | Share with "Many" old leaves |
|---|---|---|---|
| early Jan | 19 | 0.00 | 0.32 |
| late Jan | 17 | 0.12 | 0.47 |
| early Feb | 49 | 0.10 | 0.35 |
| early Mar | 14 | 0.21 | 0.21 |
| late Mar | 54 | 0.39 | 0.39 |
| early Apr | 29 | 0.66 | 0.69 |
| late Apr | 38 | 0.66 | 0.74 |
| early May | 15 | 0.47 | 0.27 |
| late Jun | 18 | 0.17 | 0.22 (fresh leaves 1.00) |

**Concrete action for us (validation of satellite d50):**
- Use SeasonWatch as an independent check that our S2 "d50" for teak-dominated pixels falls in March, not December.
- Also recruit beat guards to log the same three-level leaf score on 5–10 marked trees per beat. The SeasonWatch protocol is free to copy.
- Training-free, low effort. Urban trees are irrigated and late, so treat this as an upper bound **[inference]**.

### A6. Indian PhenoCam work. **PARTIAL** (Jose et al. 2023, *Remote Sensing* 15:5642, review) and **ABSTRACT ONLY** (Gir and Dalma studies)
Links:
- Review: https://doi.org/10.3390/rs15245642
- Gir: https://sciforum.net/paper/29183 (also *Current Science*)

Points:
- There is no permanent PhenoCam network in India.
- 37 ground phenology sites are known (31 short-term, 6 long-term).
- In MP, a digital camera was used in **Madhav National Park** (Parihar et al. 2013).
- PhenoCam vs satellite correlation in deciduous forest is about r = 0.87 on average (n = 4). For leaf fall it is r = 0.96 (n = 2).

Gir (Gujarat dry deciduous; Oct 2022 – May 2024; conference abstract):
- green-up lasted **164 days**;
- senescence lasted **39 days**;
- satellite phenophases (Sentinel-2) missed periods because of cloud, but PhenoCam tracked the rains.

**Concrete action for us (field system thread):**
- One cheap trail camera, pointed at canopy and floor in 2–3 Ratapani beats, would give daily ground truth of canopy drop and litter cover. It would also calibrate the S2 "fraction dropped".
- A 39-day senescence means 15-day slopes are the right time scale for leaf-fall features **[inference]**.

---

## B. Satellite phenology products and methods

### B1. MCD12Q2 v6.1 User Guide (Gray, Sulla-Menashe & Friedl 2022). **FULL**
Link: https://lpdaac.usgs.gov/documents/1417/MCD12Q2_User_Guide_V61.pdf

**Method:**
- Input is MODIS **NBAR-EVI2** at 500 m.
- Each product year uses a three-year series.
- The dormant value is the 5th percentile across the three years. It falls back to the central year if it differs by >25% from that year's 10th percentile.
- A **penalized cubic smoothing spline** is fitted, weighted by MCD43A2 QA.

**Valid cycle:**
- amplitude ≥ **0.1 EVI2** and ≥ **35%** of the three-year max − min;
- the cycle end is searched from 30 days after the peak up to 185 days.

**Dates:**
- Greenup, midgreenup and maturity are the first dates crossing 15%, 50% and 90% of the greenup amplitude.
- **Senescence, midgreendown and dormancy are the last dates crossing 90%, 50% and 15% of the greendown amplitude** (peak − segment end).
- QA = 80% data completeness ± 2 weeks around the date, plus 20% spline R².

**Concrete action for us (2-day model):**
- Copy the 90/50/15% definitions exactly for our 30 m HLS series (§F).
- Use MCD12Q2 MidGreendown at 500 m (2001 onward) as a free, ready prior. It gives per-cell multi-year mean and SD of leaf-fall date, exactly at our 500 m cell size.
- Effort: under half a day in Earth Engine (`MODIS/061/MCD12Q2`).
- Expected: a climatology feature, plus "this year's anomaly" once HLS is in.

### B2. VIIRS VNP22Q2 Global Land Surface Phenology, User Guide C2 (Zhang et al.). **FULL**
Link: https://viirsland.gsfc.nasa.gov/PDF/VIIRS_GLSP_UserGuide_C2.pdf

**Method:**
- 500 m, from 3-day VIIRS NBAR EVI2.
- Uses a hybrid piecewise logistic model; transitions are found from the rate of change in curvature, not from amplitude thresholds.

**Layers:**
- `Onset_Greenness_Decrease`, `Date_Mid_Senescence_Phase` and `Onset_Greenness_Minimum`;
- `Rate_Greenness_Decrease` (EVI2 per day);
- **PGQ** (proportion of good-quality 3-day observations around each date);
- climatology-fill share codes (0% to >31%).

**Version status:** V1 was decommissioned on 31 Jul 2025; use V2 (2013 onward).

**Concrete action for us:**
- `Rate_Greenness_Decrease` per 500 m cell per year is a ready "speed of leaf drop" input. Test it as a season-level feature.
- Use PGQ to drop cell-years with poor data.
- Effort: low.

### B3. MSLSP30NA (Bolton et al. 2020, RSE 240:111685). User Guide V1 **FULL**; paper not reachable (ScienceDirect bot wall)
Link: https://lpdaac.usgs.gov/documents/652/MSLSP_User_Guide_V1.pdf

- 30 m phenology from HLS, **North America only** (cannot be used directly).
- Definitions on HLS EVI2:
  - OGI = 15%;
  - 50% greenness increase;
  - OGMx = 90%;
  - **OGD = 10% decrease**;
  - **50% decrease**;
  - **OGMn = 85% decrease**.
- Gaps are filled with good values from the year before or after.
- Known issues: low data density gives low quality; disturbance can cause "premature senescence or dormancy detection" (this is the burn/leaf-fall confusion seen from the phenology side).
- **Concrete action for us:** the HLS thresholds 10/50/85% and the adjacent-year gap fill are the 30 m recipe to copy. Mask burned pixels before fitting, so a fire is not read as early dormancy.

### B4. Klisch & Atzberger 2016, *Remote Sensing* 8:267. Operational near-real-time Whittaker filtering (BOKU, Kenya NDMA). **FULL**
Link: https://doi.org/10.3390/rs8040267

**Two regimes:**
- **Offline smoothing**: uses past and future data.
- **NRT filtering**: estimates the current state from data available so far.

**Settings:**
- Whittaker smoother on MODIS MOD/MYD13 NDVI, interpolated to daily, with values stored every Monday.
- Quality weights: VI usefulness 1–3 → 1.0; 4–7 → 0.8 / 0.6 / 0.4 / 0.2; 8–9 → 0.

**NRT step (every weekend):**
- uses only the **past 175 days** of observations;
- needs **≥10 MOD+MYD observations** in that window, otherwise falls back to the pixel's NDVI climatology;
- the change between consecutive Mondays is **constrained** by the pixel's weekly climatological statistics.

**Outputs:**
- Six versions of each week are stored: consolidation 0–4 weeks, plus the final value at **13 weeks**.
- Each has a modelled per-pixel uncertainty.
- The whole archive was **hindcast** to 2001 by simulating the data availability of the time.

**Accuracy:**
- Filtered values approach the final smoothed value as consolidation increases. Large differences coincide with large modelled uncertainty.
- Downstream, 3-monthly VCI vs FEWS NET: R² = 0.89, RMSE ≈ 6%.

**Concrete action for us (2-day model; this is the most important method item):**
1. Recompute every NDVI, NDMI or NBR feature as a **0-day-consolidation NRT value**: Whittaker over the trailing window ending on the forecast date, never touching later images.
2. Store, for each cell-day, the number of clear observations in the last 30 days and the age of the newest clear observation. Use these as uncertainty inputs or as filters.
3. If the current model's per-cell NDVI came from composites or smoothing that included images after the prediction date, the 29.5% recall is optimistic. Check this first.

Expected: possibly a small *drop* in measured recall (honest leakage-free baseline), then a sound base for the phenology features. Effort: 1–2 days.

### B5. HLS v2.0 User Guide (LP DAAC). **PARTIAL** (processing sections)
Link: https://lpdaac.usgs.gov/documents/1698/HLS_User_Guide_V2.pdf

What HLS does:
- Atmospheric correction with LaSRC.
- Cloud masking with Fmask 4.7 (bits 1–5: cloud, adjacent, shadow, snow, water). Cloud and shadow are dilated, and the dilated area is labelled "adjacent".
- **NBAR by the c-factor method** (Roy et al. 2016): view zenith set to 0; the solar zenith angle is set per tile per day.
- Sentinel-2 bandpasses are adjusted to Landsat OLI.
- Average revisit is **1.6 days** with Landsat 8/9 and Sentinel-2A/B/C.

**Concrete action for us:**
- Use HLS S30+L30 (not raw S2 L2A) for all phenology time series. NBAR and bandpass adjustment remove the sensor and view-angle zigzag that otherwise looks like a few days of leaf change.
- Weight = 1 if QA bits 1–3 are 0, else 0.
- Keep 10/20 m S2 L2A for the burn-scar shapes (thread 2).

### B6. Smoothing parameters for irregular HLS series (vi-phenology pipeline docs, Conklin 2026). **FULL** (software documentation, not peer-reviewed)
Link: https://vi-phenology.readthedocs.io/en/latest/smoothing.html

Setup:
- Whittaker on a daily grid solves (W + λDᵀD)z = Wy.
- D is the 2nd-order difference matrix.
- W = 1 on observation dates and 0 elsewhere.

Lambda guide: λ = 10–50 is tight; **100 is the default and balanced**; 300–1000 is very smooth.

Smooth on observation dates first, then interpolate, to avoid artefacts at gap edges. Savitzky–Golay is the alternative: bin to the median spacing, window 15 days, polynomial order 3.

**Concrete action for us [inference]:**
- Use a daily-grid Whittaker with λ = 100 for NDVI and NDMI in Oct–Jun.
- Check λ by leave-one-out on clear observations in 2–3 test beats. The Whittaker allows fast generalised cross-validation (Eilers 2003).
- λ = 100 on a daily grid will flatten a step of under about 10 days. This is good for leaf fall but blurs fire: compute burn features on raw clear observations, not the smoothed curve.

### B7. TIMESAT on HLS in the Cerrado: Effects of precipitation and fire on LSP, *Remote Sensing* 17:2077 (2025). **FULL**
Link: https://doi.org/10.3390/rs17122077

**Method:**
- TIMESAT 3.3 on MOD13Q1 and on HLS v2.0.
- HLS was **resampled to 5-day spacing** by interpolation and gap fill.
- MODIS weights: good 1.0, marginal 0.5, cloudy 0.
- Savitzky–Golay was the best noise filter in TIMESAT for this site.
- 13 metrics were computed, including EOS, base level, amplitude and **RDES (rate of decrease at end of season)**. EOS used the 20% and 80% levels.

**Results:**
- Rainy-season rain correlates positively with AMP, **EOS**, LSI, SSI and RIBS. The largest correlations are in woodland, e.g. SSI r = +0.585; LSI in grassland r = +0.575. So wetter seasons mean a later season end.
- Fire changes the phenology of the burn year *and the next year*: BL, VES, SSI, VSS, EOS and AMP. Burned grassland is greener in the following cycle.

**Concrete action for us:**
- (2-day model) Burned-last-year cells will show different greendown timing. Keep the burn history inputs, and add an interaction with d50.
- (Fuel map) The same rule as Malhi: a wet monsoon means later and slower leaf fall.

### B8. Singh & Jeganathan 2024, *Advances in Space Research* 73:2969. Random forest for monthly fire in MP and Chhattisgarh. **ABSTRACT ONLY**
Link: https://doi.org/10.1016/j.asr.2023.12.054

- Monthly RF on 20 years of data, using temperature, rain, radiation, NDVI, soil moisture, **litter availability**, ET and terrain.
- Accuracy for 2018–2020 was 86.46% (MP) and 93.78% (CG).
- "Negative anomalies" of NDVI and rainfall amplified fire risk.
- Fires per year rose from about 1,200 (MP, 2001–05) to about 2,800 (2016–20).

**Concrete action for us:**
- The NDVI *anomaly against climatology* (not the raw value) is what carried signal in the nearest regional model.
- Ask the authors (BIT Mesra) how "litter availability" was built. It is probably their AD leaf-fall proxy.

---

## C. Leaf fall, greenness decline and fire: what is (and is not) published

### C1. Kuhn-Régnier et al. 2021, *Biogeosciences* 18:3861. Antecedent vegetation and drought as global drivers of burnt area. **FULL**
Link: https://doi.org/10.5194/bg-18-3861-2021

**Method:**
- Random forest on monthly 0.5° burnt area.
- Antecedent FAPAR, LAI, VOD, SIF and dry days at lags of 1, 3, 6, 9, 12, 18 and 24 months.
- Antecedent values are entered as *differences from the current month*.

**Results:**
- Out-of-sample R² rose from **0.579 to 0.701** when antecedent vegetation was added.
- Lags of a year or more added nothing.
- **Current FAPAR has a negative effect and antecedent FAPAR a positive one, strongest at 1 month and lasting up to 6 months.**
- The combined effect is positive "if FAPAR is low while FAPAR 1 M is high". That is a recent drop in greenness, which is what leaf fall produces.
- Dry days: the current month starts to matter at more than about 10 dry days; the previous month needs more than about 20.
- Fuel-limited biomes respond over about 4 months; moisture-limited biomes respond to current conditions.

**Concrete action for us (2-day model).** Encode the drop explicitly as dNDVI30 = NDVI(t−30) − NDVI(t), and also as fraction dropped (§F).
- These carry the "was green, now bare" signal that a single NDVI value cannot.
- Expected **+0.5 to 1.5 pts** recall at 5 picks per beat per day, mostly in February–March **[inference]**. The global gain was large, but at monthly 0.5° scale where seasonality dominates. Within a beat-day most of that seasonality is already absorbed.

### C2. Niyogi et al. 2025, *Scientific Reports* 15 (2025). Fire patterns in Satpura Tiger Reserve, MP. **FULL**
Link: https://doi.org/10.1038/s41598-025-98051-7

- MODIS MCD14DL, 2002–2021, 1 km grid.
- "Almost all" fires fall in **March–May**, so only those months were modelled.
- Monthly negative binomial model:
  - maximum temperature β = +0.295 (p < 10⁻¹⁵);
  - previous month's fire count β = +0.012 (p = 0.00015);
  - previous month's rain β = −0.0035 (p = 0.063);
  - current month's rain not significant.
- Spatial CAR model: slope and distance to water raise fire; settlement distance, road density and water cover lower it. **Previous-year NPP was positive but not significant.**
- Ignitions are linked to mahua flower collection and tendu leaf flush.
- **Concrete action for us:** this confirms that in a teak landscape 100 km from Ratapani, the season starts *after* teak leaf fall (Feb–Mar). Productivity (NPP) alone does not predict where fires happen. This argues for timing features (when this cell dropped its leaves) over amount features.

### C3. Month-level co-timing of leaf fall and fire in other deciduous regions. **ABSTRACT ONLY / PARTIAL**

**Cambodia (AVHRR, 1990s).** Hazeportal summary of Geocarto Int. 13(3), 1998.
- Deciduous forest fires peak in **January–February, when leaf fall peaks**.
- Other land covers peak in March–April.
- This is the only source that states the coincidence directly.

**Myanmar.** Biswas, Lasko & Vadrevu 2015, IEEE JSTARS 8:2273.
- MODIS 2003–2012; peak in March; forests are 41.3% of burnt area.
- Deciduous-forest burnt area vs GPP r = 0.49.

**Mudumalai** (from the fuel note): shedding starts in December, trees are bare by February, fires run January–April with the peak in **February–March**.

**Thailand dry dipterocarp forest.** Fires run December–April "when trees shed their leaves", and litter is the main fuel. Doi Suthep fuel load peaks in March–April, and litter moisture bottoms at 5% in April (AGRIS record). The Kanjanavanit 1992 SOAS thesis on DDF fire timing and fuel preparation is listed as full text, but eprints.soas.ac.uk was blocked from here.

**Concrete action for us [inference].**
- Across these regions, the fire peak trails peak leaf fall by about 0–2 months.
- It trails earlier where grass or early-shedding species dominate (Cambodia), and later where teak dominates (Satpura, Ratapani).
- No paper gives a pixel-level lag in days. **Our own measurement is the deliverable** (ranked action 2).

### C4. Global analogues for the timing signal. **ABSTRACT ONLY**

**Earlier peak photosynthesis timing** (NSR 2024, PMC11418649):
- Each day of earlier peak timing goes with **+0.021%** global burnt fraction (about 2.2 Mha).
- An early end to the green phase lengthens the exposed-fuel period.

**Italy** ("Does vegetation phenology matter?", EuJRS 48, 2015): fires select low-NDVI sites in May–October but high-NDVI sites in November–April. The sign of the NDVI effect flips by season.
- Concrete action [inference]: let LightGBM learn the interaction of NDVI with day of season (the existing calendar input). Better still, replace raw NDVI with fraction dropped, which is comparable across dates.

---

## D. Do green understory and moist fuels hold back early-season fires?

### D1. Schmidt et al. 2018, *J. Applied Ecology* 55:2094. Integrated fire management in the Cerrado. **FULL**
Link: https://doi.org/10.1111/1365-2664.13118 (PDF: INPE server)

- Natural and early dry season (EDS) fires are "rarely large in forest areas due to high humidity and the absence of a continuous grass layer".
- Managers identified a **"safe-burning window"**: conditions in which EDS fires "stop before reaching fire-sensitive vegetation due to natural high humidity and lower temperature … especially after sunset".
- Prescribed EDS fires were designed to "go extinct naturally" without crews. Most were under 50 ha in year 1.
- Results:
  - late dry season burnt area fell **40–57%** in three years, while total burnt area did not fall significantly;
  - the largest wildfire at SGTES fell from more than 85,000 ha (2014) to under 32,000 ha (2016);
  - firefighting cost had been more than USD 500,000 per year before the programme.
- Rainy-season burning happens in dry spells, December–February.

**Concrete action for us [inference]:**
- (Spread model) Add a night-time extinction rule early in the season. If litter is incomplete and green understory is present (fraction dropped < 0.5), fires stop at dusk when RH rises.
- (2-day model) Expect early-season (Jan–Feb) VIIRS detections to be fewer and smaller per ignition. The predicted chance that an ignition becomes a detectable fire should rise with fraction dropped.

### D2. N'Dri et al. 2018, Lamto, Côte d'Ivoire (*Fire Ecology*); West African working-landscape fires 2020 (*Fire Ecology*, doi 10.1186/s42408-020-00085-x). **ABSTRACT ONLY**
- Lamto: early-season fires spread more slowly and were less intense than mid- or late-season fires, because grass height, fresh fuel load and **moisture** were higher.
- Working landscapes (97 fires): fire type and wind mattered more than season.
- Use for us: there is support for lower early-season intensity, but the season effect can be smaller than wind or ignition type in human-managed landscapes.

### D3. Tarimo et al. 2015, *Carbon Balance and Management* 10:18 (PMC4518077). Miombo, Tanzania. **FULL**
Link: https://doi.org/10.1186/s13021-015-0029-2

- MODIS 2001–2013 and Landsat 1972–2011.
- Up to **50.6%** of woodland burns each year. Return interval is 2.7 years from MODIS and 2.1 years from Landsat.
- Wet miombo (>1,000 mm) has an **early** dry-season fire peak (July). Dry miombo peaks late.
- Late-season fires within 1 km of an early burn showed **no significant reduction in FRP** compared with those farther away (95% level).
- Burned area was mapped by fuzzy classification on **BAIML and MIRBI**.
- **Concrete action for us:** do not assume an early fire nearby lowers later intensity. As a 2-day model feature, "burnt earlier this season within 1 km" should be learned, not hard-coded. The scar-index pair BAIML + MIRBI is a second candidate set for thread 2.

### D4. Mondal & Sukumar 2014, IJWF 23 (WF13002), Mudumalai. **ABSTRACT ONLY**
- Fire days were more likely with low early dry-season rain, low humidity and high temperature, which favour ignition of litter and grass on the forest floor.
- Use for us: "days since last rain ≥ 2 mm" in Dec–Feb is the moisture complement to leaf fall (already suggested in the fuel note).

**Summary for Ratapani [inference].**
- Moderate evidence that early-season fires are limited by moister, greener fuels and higher night humidity. This comes from Cerrado managers, a West African experiment and Mudumalai weather.
- No direct evidence on teak understory.
- The testable form is: P(fire | ignition pressure) rises with fraction dropped and with days since last rain.

---

## E. Telling leaf fall from burn (burn-scar thread)

### E1. Huang et al. 2016, *Remote Sensing* 8:873. Sentinel-2 burned/unburned separability. **FULL**
Link: https://doi.org/10.3390/rs8100873

- Five pre/post S2A pairs, assessed with transformed divergence and decision trees.
- The best bands are the **20 m NIR (B8A), SWIR (B11, B12) and red-edge (B5, B6)**.
- NDVI gives "poor burned–unburned discrimination over dry senescent vegetation"; separability was lowest at the Guinea woody-savanna site in the dry season.
- Index performance varied by site.
- Atmospheric correction mattered only for the visible bands.
- The NIR rationale: green *and dry* vegetation are both brighter in NIR than black char.
- **Concrete action for us:** a leaf-fall pixel loses red-edge/NIR contrast but stays bright in NIR and SWIR1. A burn darkens NIR. Use **dB8A < 0** together with dB11 ≤ 0 as a necessary condition for "burn". Leaf fall usually *raises* B4 and B11 as bright dry litter appears **[inference from the dry-vegetation vs char spectra]**.

### E2. Melchiorre & Boschetti 2018, *Remote Sensing* 10:750. Burn-signal persistence. **PARTIAL**
Link: https://doi.org/10.3390/rs10050750

- MODIS NBAR NBR around MCD64A1 burns, 2003–2016.
- Global **median persistence is 29 days**; **86.6%** of burnt area is separable for at most 48 days.
- Persistence was shortest in boreal regions and **South and South-East Asia**. Most tropical ecoregions have medians of 16–48 days.
- **Concrete action for us [inference]:** in Ratapani, ongoing teak leaf fall drops fresh litter on scars within weeks. Pair each VIIRS alert with an S2/HLS look within about 10–15 days. Treat "no scar seen" after 20 or more days as missing, not as negative.

### E3. Filipponi 2018, *Proceedings* 2:364. BAIS2. **FULL**
Link: https://doi.org/10.3390/ecrs-2-05177

- BAIS2 = (1 − √(B6·B7·B8A / B4)) × ((B12 − B8A) / √(B12 + B8A) + 1).
- Separability index (|μb − μu| / (σb + σu)): BAIS2 0.865 vs NBR 0.848; dBAIS2 1.337 vs dNBR 1.324.
- Very dark pixels (water, shadow) cause commission errors. Use difference indices on dense time series to date fires.
- **Concrete action for us:** add dBAIS2 to the scar classifier's index set. Expect only a small gain (separability +0.01) **[inference]**.

### E4. Trigg & Flasse 2001 (MIRBI). Libonati et al. 2011 (MIR/NIR in Cerrado). **ABSTRACT ONLY / PARTIAL**
- MIRBI = 10·SWIR2 − 9.8·SWIR1 + 2. It was designed to respond strongly to burning but weakly to natural variation, including dryness, in savanna.
- Libonati's index needs the 3.9 µm band (MODIS/VIIRS), which S2 does not have.
- Use for us: MIRBI on S2 (B12, B11) is a cheap litter-insensitive companion to NBR.

### E5. Operational rules to separate leaf fall from burn [inference, assembled from E1–E4, B1, B6 and the existing scar notes]

| Test | Leaf fall (unburned) | Fresh burn |
|---|---|---|
| Speed | Smooth decline over about 2–6 weeks (Gir senescence 39 d) | Step between two clear looks ≤ 5–10 d apart |
| NIR (B8A) | Small decline, often with a rise in red (B4) | Clear drop (char) |
| SWIR1 (B11) | Stable or up (dry litter is bright) | Down or stable |
| MIRBI (10·B12 − 9.8·B11 + 2) | Small change | Up |
| Total brightness (B4+B8A+B11) | Up | Down |
| Neighbours | Same-species pixels nearby decline together | Contiguous patch differs from neighbours on the same date |
| Persistence | Floor stays bright until monsoon | Fades in about 16–48 d as new litter and ash removal mask it |

Implementation:
1. Use the NRT Whittaker curve (λ = 100) of *unburned* forest pixels in the same beat as the expected leaf-fall decline for the interval between two looks.
2. Flag a burn when the pixel's raw dNBR is greater than that expected decline + 3 × the beat's robust SD, **and** dB8A < −0.02, **and** brightness falls.
3. Mask phenology fitting on flagged pixels so fires are not read as early dormancy (the MSLSP caveat).

---

## F. Feature definitions to copy (2-day model), with settings

All features come from HLS v2.0 S30+L30 NBAR at 30 m. Use forest pixels inside each 500 m cell, and summarise per cell as the median plus the share of pixels above a threshold. Compute everything **only from observations on or before forecast day t** (hindcast mode, §B4).

**Preprocessing:**
- Clear = QA bits 1–3 equal to 0; weights 1/0.
- Daily-grid Whittaker, λ = 100, 2nd-order penalty, trailing 175-day window.
- Require ≥ 8 clear looks in the window **[inference: HLS has about 3× the MODIS look rate, but on the forest floor; Klisch used ≥10 MODIS looks]**. Otherwise use the cell's day-of-year climatology and set a flag.
- Fit NDVI and NDMI ((B8A − B11)/(B8A + B11)).

| Feature | Definition | Notes |
|---|---|---|
| `ndvi_peak` | 95th percentile of smoothed NDVI, 15 Aug – 31 Oct of the preceding monsoon | This year's wet-season peak |
| `ndvi_floor` | Cell's median of annual 5th-percentile NDVI over Mar–May, 2017–2025, unburned pixels only | Dormant floor (MCD12Q2-style) |
| `frac_dropped` | (ndvi_peak − NDVI_s(t)) / (ndvi_peak − ndvi_floor), clipped to [−0.2, 1.2] | Same as "relative greenness" curing (Newnham 2011) |
| `d10`, `d50`, `d85` | First date after the peak when frac_dropped ≥ 0.10 / 0.50 / 0.85 (MSLSP thresholds; MCD12Q2 uses 0.10/0.50/0.85 of the drop as 90/50/15% of amplitude) | Dates, from data up to t only |
| `days_since_d50` | t − d50 (missing before d50) | The "fire follows leaf fall" clock |
| `slope15`, `slope30` | (NDVI_s(t) − NDVI_s(t−15)) / 15, and the same over 30 days | Fits the 39-day senescence time scale |
| `dndvi30` | NDVI_s(t−30) − NDVI_s(t) | Kuhn-Régnier "low now, high 1 month ago" |
| `frac_dropped_anom` | frac_dropped(t) − the cell's median frac_dropped on the same day of year (2017–2025) | Early or late year; anomaly carried the MP/CG signal (B8) |
| `share_px_d50` | Share of the cell's forest pixels already past d50 | Within-cell species mix (A2) |
| `ndmi_drop` | Same as frac_dropped, on NDMI | Litter and canopy dryness |
| `rank_in_beat` | Within-beat daily rank of frac_dropped and days_since_d50 | Fits the 5-picks-per-beat objective |
| Season-level | Jun–Sep rain, monsoon withdrawal date, Oct–Nov rain (IMD/ERA5); MCD12Q2 MidGreendown climatology and SD; VNP22Q2 `Rate_Greenness_Decrease` | Wet monsoon → later d50 (A1, B7) |
| QA | Clear looks in the last 30 days; days since the newest clear look | Lets the model discount stale values |

**Expected gain [inference].** About **+0.5 to 2 pts** recall at 5 picks per beat per day over 29.5%. Most of it should come in February–early March and in years with anomalous leaf-fall timing. The current per-cell NDVI already carries part of this signal. If the existing NDVI turns out to be leaky (B4), the honest baseline may first fall by a similar amount.

**Test design:**
- Season-blocked cross-validation; report Jan–Feb, Mar and Apr–Jun recall separately.
- Check feature value with a drop-column test, not split gain.

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| HLS S30/L30 v2.0 (NBAR, bandpass-adjusted) | https://lpdaac.usgs.gov/products/hlss30v002/ | 30 m, about 1.6 d combined | L30 2013–, S30 2015– | NASA open | LP DAAC / AWS `nasa-hlss30`; GEE `NASA/HLS/HLSS30/v002`, `HLSL30/v002` |
| Sentinel-2 L2A | https://dataspace.copernicus.eu | 10–20 m, 5 d | 2017– (L2A) | Copernicus open | GEE `COPERNICUS/S2_SR_HARMONIZED` |
| MCD12Q2 v6.1 Land Cover Dynamics | https://lpdaac.usgs.gov/documents/1417/MCD12Q2_User_Guide_V61.pdf | 500 m, annual | 2001– (check latest year) | NASA open | GEE `MODIS/061/MCD12Q2` |
| VNP22Q2 v2 VIIRS phenology | https://www.earthdata.nasa.gov/data/catalog/lpcloud-vnp22q2-002 | 500 m, annual | 2013– | NASA open | LP DAAC; GEE `NOAA/VIIRS/001/VNP22Q2` (check v2) |
| MOD13Q1 / MYD13Q1 NDVI | LP DAAC | 250 m, 16 d (8 d combined) | 2000– | NASA open | GEE |
| MSLSP30NA (method reference only) | https://lpdaac.usgs.gov/documents/652/MSLSP_User_Guide_V1.pdf | 30 m | 2016– | NASA open | North America only |
| SeasonWatch tree phenology | https://www.gbif.org/dataset/d85d848d-791e-4055-bda5-32c16619ab21 | Point (tree) | 2011– | See GBIF page (could not read the licence field; check) | GBIF API; leaf state in MeasurementOrFact |
| FIRMS VIIRS 375 m | https://firms.modaps.eosdis.nasa.gov | 375 m | 2012– | NASA open | Already in use |
| Sentinel-1 GRD (cloud-free backup for canopy state) | Copernicus | 10–20 m, 6–12 d | 2015– | Open | GEE `COPERNICUS/S1_GRD` |
| IMD gridded rain / ERA5-Land | imdpune.gov.in / CDS | 0.25° / 0.1° | 1901– / 1950– | Open | For monsoon total and withdrawal date |

---

## Sources checked but not readable

These were checked but could not be read from here:
- **Bolton et al. 2020, RSE.** ScienceDirect bot wall.
- **Kushwaha et al. 2010, *Ann. For. Sci.*** HAL, Springer and AFS all bot-walled. It has the exact per-species leaf-fall dates; fetch it by hand.
- **Kanjanavanit 1992 SOAS thesis.** Host unreachable.
- **Western Ghats 2025 phenology.** ScienceDirect.
- **Newnham et al. 2011 and Martin et al. 2015** (curing algorithms). Not open.
- **Elliott et al. 2006** (Asian monsoon forest leaf flushing). Bot wall.
- **Gir PhenoCam paper.** sciforum and i-scholar blocked.

---

## Ranked action list

| Rank | Action | Thread | Inputs and settings | Expected effect | Effort |
|---|---|---|---|---|---|
| 1 | **Leakage audit, then rebuild NDVI/NDMI/NBR features in NRT hindcast mode** | 2-day | §B4: trailing 175-d Whittaker, λ = 100 on a daily grid, HLS QA weights, ≥8 looks or climatology fallback; store looks-in-30-d and age of newest look | Honest baseline. Prevents an inflated 29.5%. Base for everything below | 1–2 days |
| 2 | **Measure Ratapani's own "fire follows leaf fall" lag** | 2-day, spread | For each cell-season, d50 from rank 1. Hazard of first VIIRS/scar date against days_since_d50 for burned vs unburned cells, 2017–2026. Report median lag and its spread by stratum | A new result, not found published. Tells us whether days_since_d50 should be a feature or a season gate | 1 day |
| 3 | **Add the §F phenology features** (frac_dropped, d50, days_since_d50, slope15/30, dndvi30, anomaly, share_px_d50, rank_in_beat) | 2-day | §F table; drop-column test with season-blocked CV | +0.5 to 2 pts recall at 5 picks per beat per day **[inference]**, concentrated in Feb–Mar | 2 days |
| 4 | **Season-level leaf-fall priors** | 2-day, fuel | MCD12Q2 MidGreendown mean and SD per 500 m cell; VNP22Q2 rate of greenness decrease; previous monsoon total and withdrawal date | Captures 3–5-week year-to-year shifts (Malhi: +24–37 d in a wet year) | 0.5 day |
| 5 | **Leaf-fall vs burn rules in the scar pipeline** | Burn scars | §E5: raw-look step test against the beat's unburned Whittaker decline + 3 SD; dB8A < −0.02; brightness falls; MIRBI and dBAIS2 added; first post-alert look within 10–15 d | Fewer Jan–Mar false scars; fewer "no scar" misses from late looks | 1–2 days |
| 6 | **Early-season extinction rule** | Spread | Night-time stop when frac_dropped < 0.5 and RH recovers (Cerrado "safe-burning window") | More realistic Jan–Feb fire sizes | 0.5 day |
| 7 | **Ground phenology in 2–3 beats** | Field system | 5–10 marked trees per beat, SeasonWatch 3-level leaf score every 2 weeks, Nov–May; optional trail camera on canopy and floor | Calibrates frac_dropped. Cheap | Setup 1 day, then guard time |
| 8 | **Get Kushwaha et al. 2010 by hand** | Fuel, 2-day | 24-species leaf-fall start and end dates | Per-species timing for the fuel strata | 1 hour |
