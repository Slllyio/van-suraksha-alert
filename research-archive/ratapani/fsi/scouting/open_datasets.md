# Open datasets not yet used for Ratapani: what they are, how to get them, what to try (October 2026)

Scope: open datasets that could add new cell-level (10–500 m) signal to the Ratapani threads: (1) 2-day prediction, (2) per-alert burn scars, (3) fuel map, (4) spread model, (5) live alert and field check. This note avoids items already covered elsewhere. The Global Fire Atlas, GABAM, Prithvi, PlanetScope, MCD64A1/FireCCI51 as label sources and FSI/VIIRS alerts are in `alert_burn_scars*.md` and in `fire-prediction-landscape.md` section 8. GEDI as a fuel input is in `fuel_load_values.md` M4. FWI/ECMWF skill is in `short_horizon_prediction_fullread.md`.

Reading status: **FULL** = whole paper read; **PARTIAL** = some sections; **ABSTRACT ONLY** = abstract or repository summary only. Dataset facts marked "catalog read" were checked on the provider's catalog page in October 2026. Facts marked "from memory, check" were not re-verified. My own reasoning is marked **[inference]**.

A rule that runs through the whole note **[inference]**: the 2-day model ranks cells within a beat on a given day. A daily input helps only if it varies across the ~25 ha cells of one beat. A beat is roughly 10 km². SMAP 9 km, CHIRPS 5 km, IMERG 10 km, IMD 25 km, India-WRIS 16 km and SeasFire 28 km are almost constant inside a beat. They can tell *when* (the day), which the model already gets from weather, but not *where*. So for the 2-day thread, the best new inputs are (a) finer human-access layers, (b) daily or weekly fine signals (1 km LST, 30–70 m thermal, 10 m crop or harvest state, extra night fire detections) and (c) better burn history. Coarse moisture products belong in seasonal or yearly risk, not daily ranking.

---

## Part A. Papers read for evidence of fire relevance

### A1. Niyogi et al. 2025, Satpura Tiger Reserve, MP (FULL)
*Environmental and anthropogenic influences on fire patterns in tropical dry deciduous forests.* Sci. Rep. 15:13272. https://doi.org/10.1038/s41598-025-98051-7 (CC BY)

- Site: Satpura TR, ~2,133 km², next door to Ratapani in the same Narmada-valley dry deciduous belt. Cover: 38.5% tropical deciduous forest, 35.8% scrub, 5.9% water.
- Fire data: MODIS active fire (FIRMS), Jan 2002–Dec 2021, counts per 1 km² cell. Models: Bayesian spatial zero-inflated Poisson (ZIP) and zero-inflated negative binomial (ZINB).
- Predictors and sources:
  - Slope from ASTER DEM.
  - Distance to water and "aquatic coverage" (% of the cell under water), from **OpenStreetMap** water polygons.
  - Distance to roads and road density, from Google roads digitised by hand.
  - Distance to settlements: buildings plus fields digitised from Google Earth for 2001, 2010, 2013 and 2021.
  - NPP from MOD17A2H (500 m).
  - Land cover background map: Esri 10 m LULC 2020.
- Standardised posterior coefficients, ZIP model (ZINB gave similar values):

  | Predictor | Coefficient | 95% CI |
  |---|---|---|
  | Aquatic coverage | −1.26 | −1.89 to −0.83 |
  | Distance to settlements | −0.59 | −0.82 to −0.40 |
  | Road density | −0.37 | −0.52 to −0.22 |
  | Slope | +0.29 | |
  | Distance to water | +0.24 | 0.12–0.36 |
  | Distance to roads | −0.05 | not significant |
  | NPP | +0.27 | not significant |

  ZINB values: aquatic coverage −1.26, distance to settlements −0.52, road density −0.36, distance to water +0.32.
- The authors give mahua-flower collection and tendu flushing in the buffer as the main ignition causes, with agricultural burning as an additional cause.
- What it shows: in a reserve next to ours, two water terms (water inside the cell, and distance to water) and settlement proximity are the strongest spatial terms. Road *density* is a firebreak or patrol effect and has a negative sign. Distance to roads is not significant.
- **Concrete action for us (thread 1, also 3 and 4):**
  - Add two water features per cell: dry-season water fraction and distance to dry-season water. Build them from **JRC Global Surface Water** monthly history (30 m, 1984–2021), or from Dynamic World `water` probability per season, which runs up to now.
  - Add road and track *density* as well as distance, using OSM `highway=track|path` plus forest roads you digitise.
  - Expected effect [inference]: small (+0.5–1.5 pp recall@5). The village-distance feature already takes much of the human signal. Water is the new term, and it costs almost nothing.
  - Caveat: their response variable is 1 km MODIS counts over 20 years, a static susceptibility measure rather than day-level risk.

### A2. Murthy, Sinha, Kaul & Vaidyanathan 2019, Valmiki TR (ABSTRACT ONLY)
*A fine-scale state-space model to understand drivers of forest fires in the Himalayan foothills.* For. Ecol. Manage. https://eprints.iisc.ac.in/61583/

- MODIS fires 2001–2015 at 1 km². Fire-prone areas: low-altitude sal forest and terai grassland **2.5–3 km from villages** with good road access.
- Distance to the nearest village and **village area** both had *non-linear* relationships with fire.
- **Concrete action (thread 1):** treat village size as a separate feature, not just distance. Example: building count, or built area from Google Open Buildings, within 1, 3 and 5 km of the cell. Let LightGBM learn the hump-shaped distance curve; it needs no transform. Expected effect [inference]: +0.5–1 pp. Village size should explain why some villages light far more fires than others.

### A3. Babu, Gour et al. 2023, central Western Ghats (ABSTRACT ONLY)
*Environmental drivers and spatial prediction of forest fires in the Western Ghats biodiversity hotspot, India: an ensemble machine learning approach.* For. Ecol. Manage., doi:10.1016/j.foreco.2023.121057.

- Ensemble ML, 10 m susceptibility map. Land use/land cover and **distance to agricultural fields and to settlements** were the key determinants. 26.5% of the area came out high or very high risk.
- **Action (thread 1):** add distance to cropland edge as a feature, separate from distance to houses. Cropland can come from Dynamic World `crops`, Esri 10 m annual LULC or WorldCover. Agricultural edges are where crop-residue fires escape. Chandel et al. 2022 (already in our notes) found 55% of biomass burning in MP is on cropland.

### A4. Debnath, Kiran Chand, Rajashekar & Murthy 2011, Central India (FULL, short workshop paper)
*Analysis of multi-temporal satellite data for forest fire characterisation over Central Indian region.* ISPRS Archives XXXVIII-8/W20:71. https://isprs-archives.copernicus.org/articles/XXXVIII-8-W20/71/2011/

- MODIS fires 2001–2010 against MODIS LST and EVI on a 5 × 5 km grid, and IMD interpolated air temperature.
- Fire density vs mean air temperature: exponential fit, **R = 0.78**. Fire rises with LST and falls with EVI. March is the peak month, and 2009 was the worst year.
- **Action (thread 1):** this is weak evidence: coarse and correlational. It does support testing *within-reserve* LST at 1 km (see B9) as a daily dryness and leaf-fall signal.

### A5. Vadrevu et al. 2019, fire trends in South and Southeast Asia (FULL)
*Trends in vegetation fires in South and Southeast Asian countries.* Sci. Rep. 9:7422. https://doi.org/10.1038/s41598-019-43940-x

- India has the largest annual fire counts in the region: 73,836 per year from MODIS and 551,649 from VIIRS 375 m (2012–2016). The fire trend is significant (p = 0.004), and FRP is rising (p = 0.039).
- **47.9% of India's fires are on cropland.** 17.8% of India's 10′ grid cells burn every year.
- Precipitation explained **30%** of the year-to-year variation in India's fires. Temperature correlated poorly.
- **Action:** context only. It supports using a rain-based seasonal prior (CHIRPS, IMERG) for yearly fire load, not for daily "where".

### A6. Vadrevu et al. 2024, night fires in South and Southeast Asia (FULL)
*Trends in nighttime fires in South/Southeast Asian countries.* Atmosphere 15:85. https://doi.org/10.3390/atmos15010085

- VIIRS 375 m, 2012–2022: **~28.3% of South Asia's fire detections are at night** (18.98% in Southeast Asia). India's night-fire trend is positive but not significant, and the peak month for night fires is March.
- Sentinel-3 SLSTR night detections were **92–98 times fewer** than VIIRS. SLSTR is of no use to us.
- Cites a global MODIS figure: 10.4% of detections are at night. Cropland fires are 89–95% daytime.
- **Action (threads 1, 2, 5):** split our VIIRS labels and history by day (13:30) and night (01:30) pass. Night detections in forest point to slow litter fires still burning after dark. They may need their own history feature: "night detection in this cell in the last N days". They are also the best target for FILDA-2 (A7).

### A7. Zhou et al. 2023, FILDA-2 night fire detection (FULL)
*Enhancement of nighttime fire detection and combustion efficiency characterization using Suomi-NPP and NOAA-20 VIIRS.* IEEE TGRS 61:4402420. https://arroma.uiowa.edu/docs/publication/paper_pdf/2023/zhou_meng_et_al_2023.pdf

- Combines the VIIRS Day/Night Band (visible light from flames) with the I-bands and uses dynamic contextual thresholds. Global test, Aug–Oct 2019: **25.37% more night fire pixels** than the operational VIIRS I-band product (AF-I), and 32.27% more at the swath edge. No significant omission of fires that AF-I detects.
- Also retrieves a per-pixel modified combustion efficiency (MCE = 0.017 ln VEF + 1), which flags smouldering against flaming fire.
- The authors name **India** among the regions that gain most extra night detections, attributed to more small or prescribed fires.
- Data: LP DAAC released Version 2 FILDA-2 products in March 2025 for both S-NPP and NOAA-20 (https://www.earthdata.nasa.gov/data/alerts-outages/viirs-version-2-fire-light-detection-algorithm-2-parameter-data-products). The NOAA-20 750 m swath product is VJ147MOD; check the 375 m product name on LP DAAC. Format: HDF/netCDF swath files, not in GEE.
- **Concrete action (thread 2 labels, thread 5 alerts):**
  1. Download FILDA-2 night detections for Ratapani, 2019–2026.
  2. Count how many fall on our dated S2/Landsat scars that VIIRS AF-I missed.
  3. If they add ≥10% more dated scars, use them for date assignment and as an extra history feature.
  - Expected effect [inference]: better dating of small night-burning litter fires, which are exactly the type VIIRS misses. Effort: moderate (swath processing).
  - MCE (smouldering vs flaming) could later help the spread thread.

### A8. Pirotti, Adedipe & Leblon 2023, Sentinel-1 vs canopy dryness (FULL)
*Sentinel-1 response to canopy moisture in Mediterranean forests before and after fire events.* Remote Sens. 15:823. https://doi.org/10.3390/rs15030823

- 276 S1 scenes (2018–2020), ~500 km² of Portugal, closed (>90%) canopy, backscatter grouped by Drought Code (DC) class.
- Backscatter falls with local incidence angle (R² 0.32–0.44), so normalise for angle first.
- From wettest (DC 0–1) to driest (DC 100–1000), mean backscatter falls only **~1.4 dB in VV and ~0.7 dB in VH**. Contrast is weak between "dry" and "extremely dry" (DC 10–100 vs 100–1000). Burnt canopy is more visible in VH. VH recovers about **360 days** after fire.
- **Action:**
  - For the 2-day thread: low value [inference]. Ratapani's Jan–Jun season sits entirely in the "dry to extremely dry" range, where C-band is least sensitive. Repeat is also ~12 days since S1B failed in Dec 2021; S1C has flown since 2025.
  - Better uses: a cloud-free leaf-fall timing signal (VH drops as the canopy sheds), and a check on burn scars (VH change) in a hazy April.
  - Effort: moderate. Inputs: GEE `COPERNICUS/S1_GRD`, IW, VV+VH, angle-normalised, 30 m.

### A9. Sazib, Bolten & Mladenova 2021, SMAP and fire (FULL)
*Leveraging NASA SMAP for assessing fire susceptibility and potential impacts over Australia and California.* IEEE JSTARS. https://ntrs.nasa.gov/citations/20220006865

- Monthly SMAP soil moisture anomalies at 0.25°, 2015–2019, against monthly fire counts, using Spearman lag correlation. The correlation is negative and strongest at short lags. Anomalies fall in the months before fire, which suggests **1–2 month lead time**.
- **Action:** seasonal or yearly only. Example: a "pre-season root-zone anomaly" for each year at reserve level, to scale expected fire load. No cell-level value for us.

### A10. Other papers checked (ABSTRACT ONLY)
- **Goffin et al. 2024, Chile** (Remote Sens. 16:2457). A SMAP threshold of 0.14 m³/m³ flagged megafire-prone areas: 54.1% recall, 75.9% precision. Weaker in 2023. Not relevant to small litter fires.
- **Zhu et al. 2024, ECOSTRESS, SE Australia Black Summer** (Remote Sens. Ecol. Conserv., doi:10.1002/rse2.422). Inputs: ECOSTRESS 70 m WUE, ESI and ET, plus vegetation indices, rain and topography. Their models predicted **>90% of fire occurrences one week ahead**. WUE was the top predictor; fire-affected areas had WUE > 2 g C kg⁻¹ H₂O. ESI and slope were also significant. Caveat: large, climate-driven fires, and the headline number is probably not a precision-controlled metric.
- **Suresh Babu et al., Uttarakhand MODIS fire danger index** (ESSOAr preprint 10.1002/essoar.10500754.1). A daily satellite-only index: a static layer plus dynamic LST, perpendicular moisture index and modified NDFI. Accuracy 72–91%, overall 81.27%, against MODIS active fire. It shows that daily MODIS LST-based dryness has been tried in India; we could copy its daily dynamic components.
- **Sharma, Gupta & Fatima 2022** (IJWF, doi:10.1071/WF22016). All-India susceptibility, six ML methods: SVM AUC 0.908, ANN 0.903. The full text was unreachable (503).
- **Singh & Jeganathan 2024, MP and Chhattisgarh.** Monthly random forest over 20 years with soil moisture, ET, litter and NDVI. Accuracy 86% in MP and 94% in CG. Negative NDVI and rainfall anomalies raise fire risk. MP fire counts rose from ~1,200 to 2,800 per year (2001–05 vs 2016–20).
- **Banerjee, Das & John 2021, NE India terai** (Agric. For. Meteorol. 304:108411). Roads and grassland NPP dominate; dry-season rain reduces fire.
- **East et al. 2023, GEDI after Amazon understorey fire** (Remote Sens. 15:696). GEDI may **not** detect 2–3 m canopy-height changes. For Ratapani's low-intensity litter fires, GEDI is not a burn detector; use it only for static structure.
- **Percival et al. 2024, Madagascar dry forest, GEDI:** the first fire sharply reduced cover and height, and later fires added little. Static structure differs between repeatedly burnt and unburnt dry forest.
- **Vignesh et al. 2017** (ACRS, Nilgiris/Kanyakumari): monthly VIIRS DNB radiance correlated with fire counts. Fires leak into night-light products, so mask fire nights before using night lights as a socio-economic layer.
- **CHIRPS vs IMD evaluations.** In the Mahanadi basin (Theor. Appl. Climatol., doi:10.1007/s00704-022-04002-x), CHIRPS was best for daily values in winter and pre-monsoon, i.e. our fire season. A Sci. Rep. 2024 comparison ranked APHRODITE > MSWEP > CHIRPS against IMD across India.

### A11. Roy et al. 2015, vegetation type map of India (FULL)
*New vegetation type map of India prepared using satellite remote sensing.* IJAEOG 39:142–159. https://ris.utwente.nl/ws/files/276818546/ (accepted manuscript)

- Seamless 1:50,000 map from IRS LISS-III (23.5 m), multi-season imagery, interpreted on screen. **100 classes** in 9 broad categories.
- Classes include "tropical dry deciduous", "**tropical teak mixed dry deciduous**", "tropical teak mixed moist deciduous", "tropical sal mixed dry deciduous", "dry deciduous scrub" and teak plantations.
- Accuracy **90%** against 15,565 ground points.
- Access: the paper says the map is on the IIRS Biodiversity Information System portal (http://bis.iirs.gov.in). That host **did not respond** from here in Oct 2026; try from India, or ask IIRS. NRSC/Bhuvan licence terms apply, so assume view or research use only.
- **Action (threads 1, 3, 4):** if you can get it, use it to split cells into teak-mixed dry deciduous, other dry deciduous, scrub and plantation as a categorical feature. Earlier "fuel strata gave nothing", so expect little for thread 1 [inference]. Its main value is as a fuel-model stratum for the spread model (thread 4) and the fuel map (thread 3).

---

## Part B. Datasets, one by one (resolution, years, licence, access, feature idea, expected value)

Expected values are my estimates [inference] unless stated.

### Human access and ignition pressure (best bet for thread 1)

**B1. Google Open Buildings v3 polygons and Open Buildings 2.5D Temporal**
- v3 polygons: `GOOGLE/Research/open-buildings/v3/polygons` (FeatureCollection, imagery ~2022–23, confidence score per building; CC BY 4.0 or ODbL). From memory, check.
- Temporal: `GOOGLE/Research/open-buildings-temporal/v1`. Catalog read. Annual 2016–2023, 4 m effective (0.5 m raster), from Sentinel-2. Bands: `building_presence`, `building_fractional_count`, `building_height`. Covers South Asia. CC BY 4.0 or ODbL. Confidence values are uncalibrated, so use them for ranking or thresholds only.
- **Feature idea:**
  - Per cell, building count within 1, 3 and 5 km.
  - "Village size" of the nearest village.
  - Building growth 2016→2023.
  - The share of buildings on the uphill or upwind side.
  - Year-matched values: use the temporal layer of the right year, so 2017 labels see 2017 buildings.
- **Value:** medium. The village-distance feature exists already, but village *size* and *growth* are new (A2 found village area non-linear). Effort: low (GEE).

**B2. OpenStreetMap paths, tracks and water (Geofabrik India extract, HOT Export Tool)**
- ODbL, continuously updated. Sources: https://download.geofabrik.de/asia/india.html and https://export.hotosm.org. My Overpass query timed out, so OSM completeness inside Ratapani is unknown.
- **Feature idea:**
  - Distance to and density of `highway=track|path|unclassified`.
  - Water features (A1).
  - Footpaths connecting villages across the forest. People walk these to collect mahua and tendu, and to graze cattle.
- **Value:** medium if mapped, low if OSM is empty there. First check coverage against the latest Google or Bing imagery. If coverage is poor, digitise the main footpaths once (about 1–2 days) and use them for all years. Effort: low to medium.

**B3. SHRUG (Development Data Lab), village census and polygons**
- https://www.devdatalab.org/shrug_download/. Version 2.2 released Aug 2026. CC BY-NC-SA 4.0 (non-commercial, share-alike). Polygons for ~600k villages; the provider warns of positional errors up to ~1 km.
- Modules, per docs.devdatalab.org:
  - Population Census Abstract and Village Directory: 1991, 2001, 2011.
  - SECC 2012.
  - Mission Antyodaya village facilities 2020.
  - Economic Census: 1990, 1998, 2005, 2013.
  - Night lights: DMSP 1992–2013, VIIRS 2012–2021.
  - MODIS VCF forest cover.
  - PMGSY roads.
  - Facebook Relative Wealth 2021 and Facebook population 2021.
- **Feature idea:**
  - Weight each village's ignition pressure by its Scheduled Tribe share, its share of cultivators and agricultural labourers, its forest area (Village Directory land use), and Mission Antyodaya fuel or livelihood fields.
  - Then make a "pressure-weighted distance" for each cell: Σ village pressure × exp(−d/2 km).
- **Value:** medium for thread 1. It separates high-dependence tribal hamlets from larger agricultural villages; the evidence is in A1–A3 plus field knowledge of mahua collection. Effort: medium (joins).

**B4. LGD (Local Government Directory) village codes**
- https://lgdirectory.gov.in. Codes and names only, no geometry. Use it to link SHRUG/census villages to current names and panchayats, so beat staff recognise the village names in alerts (thread 5). Value: low, but useful.

**B5. WorldPop, GHSL, Meta HRSL population**
- WorldPop 100 m, 2000–2020 (`WorldPop/GP/100m/pop`), CC BY 4.0. A newer 2015–2030 release exists; check. From memory, check.
- GHSL GHS-POP and GHS-BUILT-S, 100 m in 5-year epochs 1975–2030; GHS-BUILT-S also at 10 m for 2018 (`JRC/GHSL/P2023A/...`). CC BY 4.0. From memory, check.
- Meta HRSL 30 m (`projects/sat-io/open-datasets/hrsl/hrslpop`), CC BY. Catalog read.
- **Value:** low once Open Buildings is in, because population is modelled from buildings. Use HRSL only if Open Buildings misses hamlets under trees.

**B6. Meta Relative Wealth Index**
- 2.4 km, ~2021, CC0 (`projects/sat-io/open-datasets/facebook/relative_wealth_index`). Catalog read. India is also inside SHRUG.
- **Feature:** wealth of the nearest villages, a proxy for forest dependence. Value: low to medium. Too coarse for cell level; use it as a village attribute.

**B7. VIIRS Black Marble night lights (VNP46A2 daily, VNP46A3/A4 monthly and annual)**
- `NASA/VIIRS/002/VNP46A2`. Catalog read. 500 m, daily, 2012–present. Free; cite Román et al. 2018.
- Two uses:
  - (a) **Socio-economic:** an annual electrified-settlement mask. Mask fire nights first (A10, Vignesh 2017).
  - (b) **Fire signal:** a sudden lit pixel inside the forest on a moonless night is often a fire. This is the physics behind FILDA-2 (A7).
- **Value:** low for (a), since Open Buildings is better. For (b), use FILDA-2 rather than reinventing it.

**B8. MGNREGA works (Geo-MGNREGA on Bhuvan) and MP Forest Department GIS**
- Geo-MGNREGA: ~30 million geotagged assets with photos (Bhuvan, https://bhuvan-app2.nrsc.gov.in/mgnrega/). No documented bulk export or licence.
- MP Forest Department: an ArcGIS REST directory exists at https://gis.mpforest.gov.in/server/rest/services/GISDATA. Search results list `MPFD_Forest_Boundaries_update_2023`, `MPFD_Forest_Boundaries`, a compartment layer for the Narmada buffer and `Beat_ratlam`. It returned 503 or timed out from this container, probably blocked outside India.
- **Action:**
  - Try the MPFD server from an Indian connection. Look for compartment boundaries, fire lines and water holes in the Raisen and Obaidullaganj divisions. Fire lines and compartments matter for threads 4 and 5.
  - Geo-MGNREGA: download only works near Ratapani, such as plantations, check dams and farm ponds, for wet spots and work-site activity. Value: low to medium, effort high.

### Daily and weekly fine-scale dryness and phenology (thread 1 "where on which day")

**B9. MODIS and VIIRS land surface temperature**
- Products:
  - MOD11A1 (Terra 10:30/22:30) and MYD11A1 (Aqua 13:30/01:30): 1 km, 2000/2002–present. `MODIS/061/MOD11A1`, `MODIS/061/MYD11A1`. From memory, check.
  - VIIRS VNP21A1D (day) and VNP21A1N (night): 1 km, 2012–present. Catalog read.
  - Free (NASA).
- **Feature idea:**
  1. Per cell, standardised day-LST anomaly vs that pixel's own Jan–Jun climatology, from day t−1 and t−2.
  2. Day–night LST difference. A large difference means dry surface and little transpiration (a dryness and leaf-fall proxy).
  3. LST minus air temperature (ERA5) as a canopy-stress index.
  - Ratapani covers ~900 km², about 900 MODIS pixels, so a beat gets about 10 pixels. That gives real "where" variation within a beat each day.
- Evidence: A4 (Central India, R = 0.78 with air temperature) and the Uttarakhand daily MODIS fire-danger index (81% overall accuracy, A10).
- **Value:** medium. It is the cheapest truly daily, sub-beat dryness signal. Effort: low (GEE). Gaps from cloud are few in Mar–Apr.

**B10. Landsat 8/9 surface temperature (Collection 2 ST) and ECOSTRESS**
- Landsat ST_B10: 30 m (100 m native), with L8 and L9 together roughly every 8 days, 2013–present. GEE `LANDSAT/LC0{8,9}/C02/T1_L2`. Free.
- ECOSTRESS (ISS): 70 m LST, ET, ESI and WUE (Collection 2 L2T/L3T/L4T), 2018–present. Overpass times are irregular and the revisit varies from 1 to 5 days. Free (LP DAAC, AppEEARS). Now in the main Earth Engine catalog as NASA/ECOSTRESS/L2T_LSTE/V2 (corrected 16 Oct; see research/gee-datasets/README.md, which counts ~11 useful passes per season over Ratapani).
- **Feature idea:**
  - Cell "hotness rank" within its beat from the latest clear scene, carried forward.
  - ECOSTRESS ESI or WUE in the 1–3 weeks before the day, after Zhu 2024 (A10).
- **Value:** Landsat ST is low to medium; it is 30 m but only ~8-day, so it is a weekly feature. ECOSTRESS is uncertain. Random overpass hours make LST hard to compare across days, but ESI and WUE are normalised. Test it on 2019–2026 only. Effort: medium.

**B11. Dynamic World (10 m, per Sentinel-2 scene)**
- `GOOGLE/DYNAMICWORLD/V1`. Catalog read. 2015-06 to present. Per-scene probabilities for water, trees, grass, flooded vegetation, crops, shrub & scrub, built, bare and snow. CC BY 4.0.
- **Feature ideas:**
  1. **Harvest clock:** for each crop pixel near the forest edge, the date `crops` probability drops and `bare` rises. Wheat and gram harvests in MP fall in March–April. Fresh harvest next to a forest cell is a dynamic "where and when" signal for residue fires escaping into the forest.
  2. **Scene-level "bare" jump inside forest:** a cheap burn and leaf-fall candidate for thread 2.
  3. Per-season water probability for the A1 water features.
- **Value:** medium for idea 1 [inference]. It is novel, and it targets the cropland-edge ignitions that A3 and Chandel 2022 point to. Effort: low to medium.

**B12. ESA WorldCover and Esri 10 m annual LULC**
- WorldCover: 10 m, 2020 (v100) and 2021 (v200). `ESA/WorldCover/v200`. CC BY 4.0.
- Esri/Impact Observatory 10 m annual LULC 2017–2024: `projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS`. CC BY 4.0. From memory, check. Satpura (A1) used the 2020 version.
- **Feature:** year-matched shares of crop, grass and scrub in and around each cell (Esri annual series matches label years 2017–2024). Value: low to medium. Effort: low.

**B13. MODIS land surface phenology (MCD12Q2) and LAI (MCD15A3H)**
- MCD12Q2: 500 m, yearly, 2001–2023 or so. Gives greenup, maturity, senescence and dormancy dates. `MODIS/061/MCD12Q2`. From memory, check.
- MCD15A3H: LAI, 4-day, 500 m.
- **Feature:** this year's senescence or dormancy date minus the cell's normal date. An early leaf fall means early litter. Also a 4-day LAI drop rate. S2 NDVI already does this better at 10 m, so expect little unless S2 gaps are the problem. Value: low. Effort: low.

**B14. Sentinel-1 GRD**
- 10 m, 2015–present. About 6–12 day repeat; one satellite only from 2022 until S1C. `COPERNICUS/S1_GRD`. Copernicus free licence.
- Use: leaf-fall timing and a burn check when optical images are hazy (A8). Value for thread 1: low. For thread 2: low to medium. Effort: medium.

### Rain and soil moisture (seasonal or yearly, not within-beat)

**B15. CHIRPS daily**
- 0.05° (~5.5 km), 1981–present. GEE `UCSB-CHG/CHIRPS/DAILY`. CHC's licence is public domain or CC0-style; from memory, check.
- **Feature:** days since the last ≥5 mm rain, and Jan–Feb rain total. A10 found it the best daily product in winter and pre-monsoon (Mahanadi).
- **Value:** better than POWER 0.5° for timing. Thunderstorm and western-disturbance rain is patchy, and a 5 km grid gives Ratapani ~30 pixels, so there is *some* "where". Effort: low.

**B16. GPM IMERG (V07) and IMD gridded data**
- IMERG: 0.1°, half-hourly, 2000–present. `NASA/GPM_L3/IMERG_V07`. Free. The Late run arrives in ~14 h, so it suits the live system (thread 5).
- IMD gridded rain: 0.25°, daily, 1901–present (Pai et al. 2014). IMD gridded temperature: 1° (check whether a finer version is out). Free for research via IMD Pune or the `imdlib` Python package.
- IMD station data: through the IMD Data Supply Portal; free or charged depending on user; there is no open API.
- **Value:** IMERG low to medium for live use. IMD gridded data is low (coarse), but it is the official reference for checks.

**B17. SMAP soil moisture**
- SMAP L4 surface and root zone: 9 km, 3-hourly, 2015–present. GEE `NASA/SMAP/SPL4SMGP/...`; check the current version.
- SMAP/Sentinel-1 L2: 3 km (SPL2SMAP_S).
- NSIDC-0779: SMAP downscaled to **1 km** daily using MODIS LST, Apr 2015–Sep 2022 only (fixed record). Weaker in dense vegetation and rugged terrain. NSIDC, free.
- Evidence: A9 (1–2 month lead at 0.25°) and Goffin 2024.
- **Value:** low for daily ranking. Use a pre-season root-zone anomaly as a yearly scaling input.

**B18. India-WRIS / NRSC VIC soil moisture and ET**
- 9 arc-minutes (~16 km), daily, 2013–present (plus 1976–2005). Bhuvan, India-WRIS and AIKosh. Open Government Licence – India. Value: low (coarse).

### Canopy structure (threads 3, 4; static input for thread 1)

**B19. GEDI L2A, L2B, L4A, L4B**
- `LARSE/GEDI/GEDI02_A_002_MONTHLY` (relative height metrics), `LARSE/GEDI/GEDI02_B_002_MONTHLY` and `GEDI04_A_002_MONTHLY` (above-ground biomass density).
- L2B was catalog read: 25 m footprints rasterised; 2019-03 to 2025. Bands include `cover`, `pai`, `fhd_normal` and plant area volume density (PAVD) in 5 m layers `pavd_z0…`. Public domain.
- GEDI L4B: gridded biomass, 1 km.
- **Feature:** canopy cover and low-stratum (0–5 m) PAVD. Footprints are sparse, so map them to cells with S2 and S1 by random forest (as in `fuel_load_values.md` M4).
- Use: shading (litter drying) and wind reduction for the spread model. Not a burn detector (East 2023, A10).
- **Value:** medium for thread 4, low for thread 1 ("fuel strata gave nothing"). Effort: medium.

**B20. ETH and Meta canopy height**
- ETH (Lang et al. 2023): 10 m, 2020. `users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1` plus an SD layer. CC BY 4.0. Catalog read.
- Meta (Tolan et al. 2024): 1 m, imagery 2009–2020 (80% from 2018–20). `projects/sat-io/open-datasets/facebook/meta-canopy-height`. CC BY 4.0. MAE 2.8 m (catalog read).
- **Feature:** per-cell canopy gap fraction from Meta 1 m (share of pixels <2 m), and mean height.
  - Gap fraction separates open teak scrub, where grass and litter dry fast, from closed stands.
  - Better than NDVI for canopy openness in the leafless season.
- **Value:** low to medium for thread 1, medium for threads 3 and 4. Effort: low.

### Vegetation type maps

**B21. Roy et al. 2015 / IIRS BIS vegetation types, 1:50k** (see A11)
- 100 classes, 90% accuracy. Portal unreachable from here. Value: medium for threads 3 and 4 if obtainable.

**B22. FSI forest type and forest cover maps**
- FSI forest type atlas (Champion & Seth types at 1:50k, 2011).
- ISFR forest canopy density classes (very dense, moderately dense, open, scrub) at 23.5 m, every two years.
- Not openly downloadable. FSI supplies digital data on request, possibly for a fee.
- Since you work with FSI, ask for the Raisen/Sehore canopy density tiles 2017–2023 and the forest type polygons. Value: medium as a stratum for threads 3 and 4. Effort: an email.

**B23. Bhuvan thematic layers (LULC 1:50k for 2005-06, 2011-12, 2015-16; wasteland atlas)**
- WMS, view only under NRSC data policy. Value: low, since Esri, Dynamic World and WorldCover cover the same ground openly.

### Burned area, fire records and disturbance (threads 1 history, 2)

**B24. MODIS active fire archive (MCD14ML, FIRMS archive 2000/2001–present) and MCD64A1**
- MCD14ML: 1 km. FIRMS archive download is free. MCD64A1: 500 m monthly, `MODIS/061/MCD64A1`.
- **Feature:** a 2001–2016 fire frequency per 1 km cell, as a long-run prior *before* our 2017 label start. This captures habitual burning sites that a 9-year window may under-sample. Satpura (A1) found 20-year MODIS counts strongly spatially structured.
- **Value:** medium, for very low effort.

**B25. FireCCI51, GlobFire, VNP64A1, Global Fire Atlas, FireCCIS2**
- FireCCI51: 250 m, 2001–2020 (`ESA/CCI/FireCCI/5_1`).
- GlobFire v2: per-fire final and daily perimeters from MCD64A1, 2001–2020, CC BY 4.0 (`JRC/GWIS/GlobFire/v2/FinalPerimeters`, `/DailyPerimeters`). Catalog read.
- VNP64A1: VIIRS 500 m burned area, 2012–present, LP DAAC.
- Global Fire Atlas: covered in the burn-scars note.
- FireCCISFD20 (Sentinel-2 small fires) covers sub-Saharan Africa 2019 only, so not India.
- These are known to miss small Central-India woodland fires (Chandel 2022: FIRMS <20% detection).
- **Value:** low. Use them only for the long-run prior in B24, and for "big fire year" flags.

**B26. Global Forest Watch tree-cover loss and fire-driven loss; GLAD/DIST alerts**
- Hansen GFC: 30 m, 2001–2024, `UMD/hansen/global_forest_change_2024_v1_12`, CC BY 4.0.
- Fire-driven loss (Tyukavina 2022, GLAD).
- OPERA DIST-ALERT/DIST-ANN-HLS: 30 m, global from 2023. GEE `OPERA/DIST/L3_DIST-ANN-HLS/V1` (catalog lists 2023–2025). Public domain (NASA/JPL).
- **Value:** low for low-intensity litter fires, which seldom remove canopy. DIST-ALERT is a free 30 m "vegetation decrease" stream from HLS. It could be a cheap cross-check for thread 2 scars from 2023 on. Run one comparison on 2024–2026 scars. Effort: low.

**B27. SeasFire cube**
- 0.25°, 8-day, 2001–2021, 54–59 variables, Zarr on Zenodo (v0.3 doi:10.5281/zenodo.8055879; check the licence on the record).
- **Value:** none for cell-level work. At most a regional check on yearly drivers.

**B28. CEMS/GWIS fire danger reanalysis (FWI from ERA5)**
- 0.25°, daily, 1940–present, Copernicus CDS, Copernicus licence. From memory, check. Covered by the existing FWI notes. Value: low for "where".

**B29. Surface water: JRC Global Surface Water**
- 30 m, 1984–2021, monthly history and occurrence. `JRC/GSW1_4/MonthlyHistory`, `JRC/GSW1_4/GlobalSurfaceWater`. Free with attribution (EC JRC/Google). From memory, check.
- **Feature:** dry-season (Mar–May) water presence within the cell, and distance to it. The strongest terms in the neighbouring reserve (A1).
- **Value:** medium for very low effort. Add Dynamic World water for 2022–2026.

---

## Datasets table

| Name | Link / access | Resolution | Years | Licence | How to access |
|---|---|---|---|---|---|
| Google Open Buildings v3 | developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings_v3_polygons | polygons | ~2022–23 imagery | CC BY 4.0 / ODbL | GEE `GOOGLE/Research/open-buildings/v3/polygons` |
| Open Buildings 2.5D Temporal | .../GOOGLE_Research_open-buildings-temporal_v1 | 4 m effective | 2016–2023 annual | CC BY 4.0 / ODbL | GEE `GOOGLE/Research/open-buildings-temporal/v1` |
| OpenStreetMap | download.geofabrik.de/asia/india.html; export.hotosm.org | vector | live | ODbL | Geofabrik PBF, HOT export, Overpass |
| SHRUG 2.2 (census PCA/VD 1991–2011, SECC, Mission Antyodaya 2020, VIIRS NTL, polygons, RWI) | devdatalab.org/shrug_download | village / shrid | 1991–2021 | CC BY-NC-SA 4.0 | download (registration) |
| LGD village directory | lgdirectory.gov.in | codes only | current | Govt. of India | download CSV |
| WorldPop | worldpop.org | 100 m | 2000–2020 (+ newer release) | CC BY 4.0 | GEE `WorldPop/GP/100m/pop` |
| GHSL GHS-POP / GHS-BUILT-S | ghsl.jrc.ec.europa.eu | 100 m; 10 m (2018) | 1975–2030 epochs | CC BY 4.0 | GEE `JRC/GHSL/P2023A/...` |
| Meta HRSL | gee-community-catalog.org/projects/hrsl | 30 m | ~2016–2020 | CC BY | GEE `projects/sat-io/open-datasets/hrsl/hrslpop` |
| Meta Relative Wealth Index | gee-community-catalog.org/projects/rwi | 2.4 km | ~2021 | CC0 | GEE `projects/sat-io/open-datasets/facebook/relative_wealth_index`; also in SHRUG |
| VIIRS Black Marble VNP46A2 | ladsweb / GEE | 500 m daily | 2012–present | NASA open | GEE `NASA/VIIRS/002/VNP46A2` |
| FILDA-2 night fire product | LP DAAC (VNP47*/VJ147*) | 375/750 m swath | ~2012/2018–present | NASA open | LP DAAC / Earthdata download |
| Geo-MGNREGA assets | bhuvan-app2.nrsc.gov.in/mgnrega | points | 2016–present | unclear | web view; no bulk export found |
| MP Forest Dept ArcGIS REST | gis.mpforest.gov.in/server/rest/services/GISDATA | vector | 2023 update | unclear | try from an Indian IP |
| MODIS LST MOD11A1/MYD11A1 | LP DAAC / GEE | 1 km daily (4 passes) | 2000/2002–present | NASA open | GEE `MODIS/061/MOD11A1`, `MYD11A1` |
| VIIRS LST VNP21A1D/N | LP DAAC / GEE | 1 km daily | 2012–present | NASA open | GEE `NASA/VIIRS/002/VNP21A1D` |
| Landsat 8/9 C2 surface temperature | USGS / GEE | 30 m (100 m native), ~8 days | 2013–present | public domain | GEE `LANDSAT/LC08|LC09/C02/T1_L2` |
| ECOSTRESS C2 (LST, ET, ESI, WUE) | LP DAAC, AppEEARS | 70 m, irregular | 2018–present | NASA open | AppEEARS point/area requests |
| Dynamic World | GEE catalog | 10 m per S2 scene | 2015-06–present | CC BY 4.0 | GEE `GOOGLE/DYNAMICWORLD/V1` |
| ESA WorldCover | esa-worldcover.org | 10 m | 2020, 2021 | CC BY 4.0 | GEE `ESA/WorldCover/v200` |
| Esri/IO 10 m annual LULC | livingatlas.arcgis.com | 10 m | 2017–2024 | CC BY 4.0 | GEE `projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS` |
| MCD12Q2 phenology; MCD15A3H LAI | LP DAAC / GEE | 500 m | 2001–present | NASA open | GEE `MODIS/061/MCD12Q2`, `MODIS/061/MCD15A3H` |
| Sentinel-1 GRD | Copernicus / GEE | 10 m, 6–12 days | 2014–present | Copernicus free | GEE `COPERNICUS/S1_GRD` |
| CHIRPS daily | chc.ucsb.edu | 0.05° | 1981–present | public domain (check) | GEE `UCSB-CHG/CHIRPS/DAILY` |
| GPM IMERG V07 | GES DISC / GEE | 0.1°, 30 min | 2000–present | NASA open | GEE `NASA/GPM_L3/IMERG_V07` |
| IMD gridded rain / temperature | imdpune.gov.in; `imdlib` | 0.25° rain; 1° temp | 1901–present / 1951–present | free for research | imdlib or IMD site |
| IMD station data | dsp.imdpune.gov.in | stations | varies | IMD policy (fee for some) | Data Supply Portal request |
| SMAP L4 / SPL2SMAP_S | NSIDC / GEE | 9 km / 3 km | 2015–present | NASA open | GEE `NASA/SMAP/SPL4SMGP/...` |
| SMAP 1 km downscaled (NSIDC-0779) | nsidc.org/data/nsidc-0779 | 1 km daily | 2015-04 – 2022-09 | NASA open | NSIDC download |
| India-WRIS / NRSC VIC soil moisture and ET | indiawris.gov.in; Bhuvan; AIKosh | 9′ (~16 km) daily | 2013–present | OGL-India | portal download |
| GEDI L2A/L2B/L4A (+ L4B 1 km) | LP DAAC / ORNL / GEE | 25 m footprints | 2019–2025 (gap 2023–24) | public domain | GEE `LARSE/GEDI/GEDI02_B_002_MONTHLY` etc. |
| ETH canopy height 2020 | langnico.github.io/globalcanopyheight | 10 m | 2020 | CC BY 4.0 | GEE `users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1` |
| Meta canopy height | gee-community-catalog.org/projects/meta_trees | 1 m | 2009–2020 imagery | CC BY 4.0 | GEE `projects/sat-io/open-datasets/facebook/meta-canopy-height` |
| Roy et al. 2015 vegetation types | bis.iirs.gov.in (unreachable Oct 2026) | 1:50k (23.5 m source) | ~2005–2010 imagery | NRSC/IIRS terms | portal or request to IIRS |
| FSI forest type / ISFR canopy density | fsi.nic.in | 1:50k / 23.5 m | 2011; biennial | FSI terms | request to FSI |
| Bhuvan LULC 50k, wasteland atlas | bhuvan.nrsc.gov.in | 1:50k | 2005–16; 2019 | view only | WMS |
| MODIS active fire (MCD14ML) | firms.modaps.eosdis.nasa.gov/download | 1 km points | 2000–present | NASA open | FIRMS archive download |
| MCD64A1 | LP DAAC / GEE | 500 m monthly | 2000–present | NASA open | GEE `MODIS/061/MCD64A1` |
| FireCCI51 | climate.esa.int | 250 m | 2001–2020 | ESA CCI (free) | GEE `ESA/CCI/FireCCI/5_1` |
| GlobFire v2 | GEE catalog | per-fire polygons | 2001–2020 | CC BY 4.0 | GEE `JRC/GWIS/GlobFire/v2/FinalPerimeters` |
| VNP64A1 | LP DAAC | 500 m monthly | 2012–present | NASA open | LP DAAC |
| Hansen GFC + fire-loss | glad.umd.edu | 30 m annual | 2001–2024 | CC BY 4.0 | GEE `UMD/hansen/global_forest_change_2024_v1_12` |
| OPERA DIST-ALERT / DIST-ANN | LP DAAC / GEE | 30 m | 2023–present | public domain | GEE `OPERA/DIST/L3_DIST-ANN-HLS/V1` |
| JRC Global Surface Water | global-surface-water.appspot.com | 30 m monthly | 1984–2021 | free, attribution | GEE `JRC/GSW1_4/MonthlyHistory` |
| SeasFire cube v0.3 | doi:10.5281/zenodo.8055879 | 0.25°, 8-day | 2001–2021 | check Zenodo | Zarr download |
| CEMS fire danger reanalysis | cds.climate.copernicus.eu | 0.25° daily | 1940–present | Copernicus licence | CDS API |

---

## Ranked action list (gain vs effort; gains are my estimates [inference])

1. **Water features from JRC GSW + Dynamic World** (thread 1). Dry-season water fraction and distance to water per cell. Strongest terms in the next-door reserve (A1). Gain small to medium; effort very low (half a day in GEE).
2. **Village size and growth from Open Buildings Temporal** (thread 1). Year-matched building counts within 1, 3 and 5 km, plus nearest-village size. Gain small to medium (+0.5–1.5 pp recall@5); effort low.
3. **Long-run fire prior 2001–2016 from MODIS MCD14ML / MCD64A1** (thread 1). Fire frequency per cell before the label period. Gain small to medium; effort very low.
4. **Daily 1 km LST anomaly and day–night LST difference** (MYD11A1 + VNP21A1D/N, days t−1 and t−2; thread 1). The only cheap daily dryness signal that varies within a beat. Gain uncertain, maybe +0.5–2 pp; effort low.
5. **Harvest clock from Dynamic World `crops`→`bare`** along the forest edge (thread 1). A dynamic, place-specific ignition signal for residue-fire escapes. Gain uncertain, possibly medium near the edge; effort medium.
6. **FILDA-2 night detections** (threads 2 and 5, and a history feature for thread 1). About 25% more night fire pixels globally, with India among the biggest gainers (A7). Gain: better dates for small night-burning litter fires. Effort medium (swath files).
7. **Day/night split of VIIRS history** (thread 1). About 28% of South Asian detections are at night (A6). Gain small; effort very low.
8. **SHRUG pressure-weighted village distance** (tribal share, cultivators, forest land, RWI; thread 1). Gain small to medium; effort medium; licence non-commercial.
9. **OSM / digitised footpath density** (thread 1, and access routes for thread 5). Check OSM coverage first. Gain small to medium; effort low to medium.
10. **Canopy openness from Meta 1 m and ETH 10 m height, plus GEDI cover and PAVD** (threads 3 and 4; static test in thread 1). Gain medium for spread and fuel; effort low to medium.
11. **Request FSI canopy-density tiles and forest-type polygons; try the IIRS BIS vegetation map and the MPFD ArcGIS server from India** (threads 3, 4 and 5: compartments, fire lines). Gain medium for strata and field logistics; effort is emails and access.
12. **CHIRPS "days since ≥5 mm rain"** to replace POWER rain; **IMERG Late** for the live system (threads 1 and 5). Gain small; effort low.
13. **OPERA DIST-ALERT cross-check of 2024–2026 scars** (thread 2). Gain small; effort low.
14. **ECOSTRESS ESI/WUE test, 2019–2026** (thread 1). Evidence from Australia only (A10, abstract). Gain uncertain; effort medium.
15. Low priority, not worth time now: SMAP / NSIDC-0779 / India-WRIS soil moisture (seasonal only), Sentinel-1 backscatter for litter moisture (weak in the dry range, A8), SeasFire, GlobFire, FireCCI51, VNP64A1 (too coarse for small fires), GFW loss (litter fires leave the canopy), Bhuvan WMS layers, Black Marble as a socio-economic layer (fires contaminate it; Open Buildings is better).

### Reading tally
- FULL: 8 papers (Niyogi 2025; Pirotti 2023; Sazib 2021; Roy 2015; Debnath 2011; Vadrevu 2019; Vadrevu 2024; Zhou 2023 FILDA-2).
- ABSTRACT ONLY: ~12 papers.
- Catalog or documentation pages read: 12.
