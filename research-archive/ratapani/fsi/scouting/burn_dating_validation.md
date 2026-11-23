# Burn dates and label error: how to date each scar and how to measure label quality without ground truth (scouting round 3, topic "dating", 14 Oct 2026)

For the "Cleaner fire labels" thread. This note builds on `fire_detection_sources.md` (sensors, overpass times, the "time bracket" idea in its §11), `alert_burn_scars_fullread.md` (scar algorithms) and `high_res_imagery.md`. It does not repeat them. It adds four things:
1. how the published products assign a date, and how big their date error is;
2. how fire-progression papers interpolate the day of burning, and what accuracy they get;
3. how to estimate omission, commission and date error without ground truth;
4. a fresh calculation on our own labels. This found a one-day dating bug that affects about 20% of VIIRS-dated first burns.

Reading status: **FULL 12** (Giglio 2018; MCD64A1 C6.1 user guide; Andela 2019; Parks 2014; Benali 2016; Brennan 2019; Pierdicca TCCA; Reiche 2024; Chen 2022 FEDS; Briones-Herrera 2020; Veraverbeke 2015, dating sections plus methods; FireCCI51 MODIS ATBD v2.0, dating and compositing sections). **PARTIAL 4** (VNP64A1 user guide and ATBD; Foody 2022; Jethva 2026; Humber 2018). **ABSTRACT ONLY 5** (Boschetti 2010; Scaduto 2020; Fusco 2019; Roy 2019; Boschetti 2015). Not obtained: Marsha & Larkin 2022 (proxy 502); Roy 2019 and Lizundia-Loiola 2020 full text (ScienceDirect 403, even though both are CC BY-NC-ND hybrid open access).

Inferences of my own are marked [inference]. Everything in §0 was computed by me today with `scratchpad/dating_calc/calc.py`. It reads `research/ratapani-burn-labels/burn_windows.csv` and `ratapani/viirs_snpp_2013_2024.parquet`, seasons 2017-2024, VIIRS nominal/high confidence only, using the same 750 m matching as `fsi/scripts/build_true_lead_labels.py`.

---

## 0. What our own labels say (computed today)

**Window lengths (15,754 first burns).**

| Percentile | Days |
|---|---|
| P10 | 3 |
| P25 | 5 |
| Median | 5 |
| P75 | 10 |
| P90 | 14 |

2017 has a median of 16 days; 2018-2024 are 5-6 days.

**Where in the window the first VIIRS detection falls (6,040 dated first burns, 38.3%).** Offset from `window_start` (UTC acquisition date):

| Days after window_start | 0 | 1 | 2 | 3 | 4 | 5 | 6+ |
|---|---|---|---|---|---|---|---|
| Share of first detections | 19.6% | 19.6% | 14.5% | 14.0% | 11.5% | 4.1% | 16.7% |

- The relative position (offset ÷ window length) has a median of 0.40 and an interquartile range of 0.20-0.67. Fires come early in the window more often than a uniform prior assumes.
- 68.5% of first detections are daytime (07:00-08:59 UTC, about 12:30-14:30 IST). 31.5% are night (about 20:00-21:30 UTC, about 01:30-03:00 IST).
- 84% of dated cells have VIIRS on only one day, and 10% on two consecutive days. Ratapani fires are short, so a detection date is close to the burn date.
- 1.7% of first detections fall on `window_end + 1`, the tolerance day.

**A dating bug.**
- 18.0% of daytime first detections, about 745 scars or 12.3% of all dated first burns, are on the **same date as `window_start`**. Fire seen at about 13:20 IST on the day whose 10:30-10:45 IST Landsat or Sentinel-2 look was still unburned means the fire started between those two passes, on day `window_start`.
- Another 23% of night first detections (about 440) are UTC-dated `window_start`. That pass is 01:30 IST on `window_start + 1`, so the fire was most likely lit on the afternoon of `window_start` [inference].
- `build_true_lead_labels.py` clips the fire day into (ws, we], so it moves all of these about 1,185 burns (**19.6% of dated labels**) one day late. Their two "true-lead" positive days (d-2, d-1) are then really d-1 and d. One in five strict-label positives is a nowcast, not a 2-day forecast.
- Fix: treat the window as [ws, we]. An afternoon detection on day ws counts. The burn day is the UTC `acq_date` for both day and night passes. A 13:30 IST pass has the same date in UTC and IST. A 01:30 IST pass carries the previous UTC date, which is the afternoon the fire most likely started.

**Two-source overlap (cell level, VIIRS point inside the cell, ±1 day of a scar window).**

| Measure | Value |
|---|---|
| VIIRS cell-season fire events (Jan-Jun) with a scar window in the same cell | 64.6% of 3,901 |
| Same, by VIIRS FRP: ≤3 / 3-5 / 5-8 / 8-15 / >15 MW | 55% / 67% / 72% / 74% / 81% |
| Same, by month: Jan / Feb / Mar / Apr / May | 47% / 64% / 65% / 70% / 62% |
| Scars with a VIIRS point inside their own cell | 13% (38% with the 750 m match) |
| Same, by scar size: ≤2 / 2-5 / 5-10 / 10-25 ha | 8% / 11% / 17% / 24% |

- Read as capture-recapture: about 65% is the scar map's recall of fires VIIRS can see. It is an **upper bound** for all fires, because VIIRS-visible fires are hotter and larger, and scar recall rises with FRP.
- Extending the FRP trend downward puts scar recall for sub-VIIRS fires at about 50-55% [inference].
- This matches the independent visual check (area recall 0.71, `burn-labels/README.md`). Two independent routes give similar recall, which is the kind of corroboration §B recommends.
- The naive Chapman estimate is about 30,000 fire cell-seasons (scars 15,754; VIIRS 3,901; overlap 2,044). It is biased upward, because detectability in the two sources is positively correlated and the units do not line up one-to-one. Do not use it as is; see recipe B.
- The 750 m match triples the VIIRS "recall" of scars, from 13% to 38%. Some of those dates come from a fire in a neighbouring cell [inference]. Recipe A handles this by matching to patches with a 375 m buffer.

---

## 1. Giglio et al. 2018, "The Collection 6 MODIS burned area mapping algorithm and product", RSE 217:72-85 (FULL, PMC6136150)

Link: https://doi.org/10.1016/j.rse.2018.08.005 (open copy: https://pmc.ncbi.nlm.nih.gov/articles/PMC6136150/)

**How the date is assigned.**
- The vegetation index is VI = (ρ5 − ρ7)/(ρ5 + ρ7), MODIS 1.24 and 2.13 µm.
- Two adjacent sliding windows of **W = 8 valid daily observations** (10 in C5) are moved along the series. At each position the separability is S = ΔVI / [(σpre + σpost)/2], using 10% trimmed means and SDs.
- At the maximum S, the burn date is **t\* = midpoint of the last pre-burn and the first post-burn observation**. The uncertainty is **Δt\* = the gap between those two observations**. This is exactly our scar window: MCD64's "Burn Date Uncertainty" layer is our window length.
- A pixel is rejected (tentatively unburned) if the IQR of observation dates in either window exceeds 30 days.
- The active-fire date nearest t\* is stored separately (t_f) and is used only for training and priors, not to overwrite t\*.

**Classifier.**
- Bayesian posterior ≥ 0.5 (0.6 in C5).
- Prior P_B = (0.5 − P_min)·exp(−d²/2σp²) + P_min, with P_min = 0.01 and σp = 2 km outside Africa, where d is the distance to the nearest active-fire-seeded training cell.
- Neighbours count as "temporally consistent" if |t\*(x) − t\*(x′)| ≤ 10 days. The paper says this accommodates "a practical 1- or 2-day minimum burn-date uncertainty".

**Temporal accuracy against MODIS active fires (repeating Boschetti 2010).** 44% of C6 burned cells on the same day as an active fire, and 68% within 2 days.

**Areal accuracy, preliminary Stage 2 (108 Landsat scenes).** Commission 0.24, omission 0.37.

**Concrete action for us (labels thread).**
- Store our scar date the MCD64 way: `t_star = midpoint(ws, we)` plus `dt = we − ws` per pixel, instead of a single day.
- Use the MCD64 rule "neighbour dates within 10 days count as the same fire" for patch building, tightened to ≤ 5 days for our 5-day windows [inference].
- Expected effect: honest per-label uncertainty that the model loss can down-weight.

## 2. MCD64A1 Collection 6.1 User Guide v1.1 (Giglio, Boschetti, Roy, Hoffmann, Humber, Hall) (FULL for the product, validation and known-problems sections)

Link: https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf

**Layers.**
- Burn Date: day of year 1-366; 0 = unburned, −1 = unmapped, −2 = water.
- Burn Date Uncertainty: in days.
- QA bits: bit 2 = shortened mapping period; bit 3 = relabelled by the contextual filter; bits 5-7 = why a cell was called unburned. Code 1 = observations too sparse in time, 2 = too few training samples, 3 = burn date at the limit of the series, 5 = persistent hot spot.
- First Day / Last Day: the reliable-detection period per cell.

**Stage 3 validation.**
- 558 Landsat-8 image pairs, 16 days apart, stratified random in space and time.
- Commission **40.2%**, omission **72.6%**, bias −54.1%, standard errors < 6%.
- "The large negative bias … is primarily due to the systematic underestimation of smaller burned areas."
- Cropland burns are low confidence.

**Concrete action (labels thread).**
- Pull MCD64A1 Burn Date + Uncertainty + QA for Ratapani 2017-2026 from Earth Engine (`MODIS/061/MCD64A1`).
- Use it only as a **third, nearly independent "rater"** for recipe B, not as a label. Its sources are 500 m reflectance plus MODIS thermal, which differ from our 20 m optical scars and from VIIRS.
- Expected effect: a third source makes the three-way latent-class model identifiable. With a 72.6% global omission it will see mostly our big scars, so stratify by size.

## 3. VNP64A1 (VIIRS burned area) User Guide v1.1 and ATBD v1 (PARTIAL)

Links: https://lpdaac.usgs.gov/documents/2124/VNP64_User_Guide_v1.1.pdf ; https://lpdaac.usgs.gov/documents/572/VNP64A1_ATBD_V1.pdf

- The C6 MCD64A1 algorithm with "minor modifications". VI from VIIRS M8 (1.24 µm) and M11 (2.25 µm).
- Uses **750 m M-band** reflectance and **750 m M-band active fires** (not the 375 m I-band), gridded to 500 m.
- Same five layers as MCD64A1, including Burn Date Uncertainty.
- Validation "being" done to CEOS Stage 3 against Landsat-8 pairs; no numbers given.
- Available as VNP64A1 v002 from LP DAAC (and v001 in Earth Engine as `NASA/VIIRS/002/VNP64A1` or similar; check the catalogue).

**Concrete action.** Same role as MCD64A1: an alternative third rater after 2012. Expect it to be as blind as MCD64A1 to our 2-5 ha scars [inference]. Low priority.

## 4. FireCCI51 MODIS ATBD v2.0 (Lizundia-Loiola, Pettinari, Chuvieco et al., 2018) (PARTIAL: compositing, uncertainty and date sections read)

Link: https://admin.climate.esa.int/documents/216/Fire_cci_D2.1.3_ATBD-MODIS_v2.0.pdf (paper: Lizundia-Loiola et al. 2020, RSE 236:111493, ABSTRACT; omission 67.1%, commission 54.4% over 1,200 sites)

**How the date is assigned.**
- Voronoi polygons around each month's MODIS hotspots give every pixel the **date of its closest hotspot (CHSD)**.
- The three minimum 250 m NIR values are searched in **10 days before and 10 after** the CHSD. The post window extends to 20, then 25 days if three or fewer valid observations are found.
- The burn date ("date of first detection", JD) is **the date of the selected post-fire NIR composite image**, not the hotspot date. "When there was a good coverage … this date differed only slightly from the date of the hotspot, but in areas with a low number of valid observations, the difference … could exceed 20 days."
- Hantson et al. 2013, cited there: hotspot commission < 3%, but omission > 25%, especially for small patches.

**Concrete action (labels).** The FireCCI dating error is the post-image lag, the same as our `window_end`. Use the Voronoi-to-hotspot idea in recipe A: give each undated scar pixel the date of the nearest thermal detection only if that detection lies inside the pixel's own optical bracket. Otherwise leave it as an interval.

## 5. Boschetti, Roy, Justice & Giglio 2010, IJWF 19:705-709, "Global assessment of the temporal reporting accuracy and precision of the MODIS burned area product" (ABSTRACT ONLY)

Link: https://doi.org/10.1071/WF09138

- Burned-area date compared with spatially coincident MODIS active fires within 90 days, over 6 years.
- Median difference 1 day. 50% of burned-area detections within 1 day of an active fire, 75% within 4 days.
- This "active fire as temporal reference" method is the standard one, reused by Giglio 2018 and Andela 2019.

**Concrete action.** Report our date error the same way: a histogram of (scar t\* − first VIIRS date) for the 6,040 dated scars. From §0, the first detection sits at a median of 0.40 of the window, so t\* (0.5) is on average about 0.1 × 5 days, roughly half a day, late [inference]. Use the **empirical offset distribution** (§0 table) as the prior over days for undated scars, instead of a uniform prior.

## 6. Andela et al. 2019, "The Global Fire Atlas of individual fire size, duration, speed and direction", ESSD 11:529-552 (FULL)

Link: https://doi.org/10.5194/essd-11-529-2019

**Method.**
- Starts from the MCD64A1 day of burn.
- An **ignition-point filter**: local minima in the burn-date field are ignition candidates. A minimum that does not progress continuously is pushed forward to the next burn date of its neighbours, 3 iterations, but never by more than the MCD64A1 Burn Date Uncertainty.
- Extinction-point outliers (clusters of 1-4 cells) are pulled back.
- A spatially varying "fire persistence" threshold (days a fire may take to cross one 500 m cell) splits fires.

**Validation of dates against VIIRS 375 m active fires (2012-2016).**

| Biome | Same day | ±1 day |
|---|---|---|
| Forests | 24% | 54% |
| Woody savannas | 35% | 67% |
| Shrublands | 41% | 80% |
| Savannas/grasslands | 40% | 75% |

- Daily growth matches US Forest Service NIROPS flights only on a 3-day running average. "Uncertainty in the burn date … is typically at least 1 d."
- "Moderate-resolution burned-area products are unable to adequately map … small fires (∼≤100 ha)."

**Concrete action (labels + spread thread).**
- Do not use the Global Fire Atlas for Ratapani; our fires are far below 100 ha.
- Copy its **local-minimum ignition filter** on our 20 m scar date field inside each patch. Where a patch's pixels have different `window_end` values, the earliest-window pixels are the ignition zone. Adjust "minima" that do not progress, but never beyond each pixel's own window. Gives an ignition location per patch for the spread thread.

## 7. Parks 2014, "Mapping day-of-burning with coarse-resolution satellite fire-detection data", IJWF 23:215-223 (FULL)

Link: https://doi.org/10.1071/WF13138 (open PDF: https://www.fs.usda.gov/rm/pubs_other/rmrs_2014_parks_s001.pdf)

**Setup.** 21 US fires, 5,000-221,000 ha; MODIS MCD14ML points within 1 km of the perimeter; earliest date per pixel kept; 10 interpolators to 30 m.

**Interpolators.**
- NN (nearest).
- ND (earliest of 3 nearest).
- AD (mean of 3).
- MAJ5 and MAJ10 (majority of 5 or 10 nearest).
- IDW with power 1, 2 or 0.5 over the 5 nearest.
- WMD (weights by both distance and date deviation).
- Averaging methods snap to the nearest date actually observed among the neighbours.
- Contiguous same-date regions ≤ 25 ha are merged into the neighbouring region (flare-ups).

**Reference.** Agency progression perimeters, re-dated to the previous day if mapped before noon.

**Accuracy (mean of 21 fires).**

| Method | Exact | ±1 recording date | ±2 |
|---|---|---|---|
| WMD (best) | 46.1% | 75.8% | 85.8% |
| ND (worst) | 42.8% | 69.4% | 80.7% |

- All of IDW, IDW.sq, IDW.half and WMD agree with each other at kappa ≥ 0.95.
- Interpolated dates averaged 0.2 recording dates **earlier** than the maps. The author attributes this to the progression maps being recorded late, not to satellite error.
- Explicitly "inappropriate for small fires (≪500 ha)". R code available from the author.

**Concrete action (labels).** Spatial interpolation of detection dates is only meaningful inside one connected patch of a few pixels. For Ratapani, use **NN within the patch, constrained to the pixel's optical bracket** (Veraverbeke's choice, §8). Do not use kriging or IDW across patches. The Parks numbers (46% exact on large fires with 4 MODIS passes a day) are a ceiling for what interpolation gives [inference].

## 8. Veraverbeke et al. 2015, "Daily burned area and carbon emissions from boreal fires in Alaska", Biogeosciences 12:3579 (FULL for the methods)

Link: https://doi.org/10.5194/bg-12-3579-2015

- Day of burning per pixel = **date of the nearest MODIS active fire, excluding detections with view zenith > 40°**. Best of the variants they tested, "within-1-day accuracy for most pixels" (their Fig. S3).
- Binned at local solar time.
- Day of burning was then the key predictor of below-ground carbon consumption. This is why dating matters for downstream models.

**Concrete action (labels).** Add a **scan-angle filter** to the VIIRS matching: drop or down-weight VIIRS points with `scan` > 0.8 km (the edge of swath, where the 375 m pixel grows to about 0.8 × 0.8 km). Geolocation and footprint there cover several of our cells [inference]. The VIIRS parquet has `scan` and `track`.

## 9. Scaduto, Chen & Jin 2020, "Satellite-based fire progression mapping: a comprehensive assessment for large fires in northern California", IEEE JSTARS 13:5102-5114 (ABSTRACT ONLY; HKU repository blocked by Cloudflare)

- 42 fires over 2,000 ha (2017-18) against NIROPS daily perimeters.
- **Natural neighbour** interpolation of combined MODIS + VIIRS was best for daily area (R² 0.70, RMSE about 1,250 acres; 2-day window R² 0.83).
- VIIRS 375 m alone was spatially best (kappa 0.55): **61% of pixels on the correct day, plus 25% within ±1 day**.

**Concrete action.** Supports using all VIIRS platforms (not only S-NPP) and combining sensors before interpolating. Combining improved day-level agreement over MODIS alone.

## 10. Briones-Herrera et al. 2020, "Near real-time automated early mapping of the perimeter of large forest fires from the aggregation of VIIRS and MODIS active fires in Mexico", Remote Sens. 12:2061 (FULL)

Link: https://doi.org/10.3390/rs12122061 (open PDF: USC Minerva)

- Convex hulls of monthly VIIRS + MODIS points, minimum 3 points, tested at aggregation distances of 750, 1,000, 1,125 and 1,500 m against MCD64A1 perimeters (fires averaged 2,305 ha).
- Best for individual fires: **1,125 m** (coefficient closest to 1, bias −9 ha). 750-1,000 m underestimate and 1,500 m overestimates.
- Monthly totals: R² 0.94 at 750-1,000 m.
- Three example fires checked with Sentinel-2 dNBRcorr > 100, a threshold from 100 field plots.

**Concrete action (labels).** Small value for us; our fires are under 25 ha. It does support a **1,125 m (three VIIRS pixels) linking distance** when grouping VIIRS detections into one fire event for recipe B's counts.

## 11. Chen et al. 2022, "California wildfire spread derived using VIIRS satellite observations and an object-based tracking system" (FEDS), Scientific Data 9:249 (FULL)

Link: https://doi.org/10.1038/s41597-022-01343-0

- Every 12-hour VIIRS 375 m pass: points clustered with a ball tree, distance thresholds depending on land cover.
- A cluster joins an active fire object if it falls within that object's buffer.
- An object stays active if it has any detection in the past **5 days**.
- Perimeter = **alpha shape, α = 1 km**, buffered by 187.5 m (half a VIIRS pixel).
- Against FRAP 2018: precision, recall, IoU and F1 of 0.71-0.93 per fire; area ratio 1.09.
- FEDS "recorded a much greater number of small fires" than FRAP.

**Concrete action (spread + labels).** Use the FEDS **5-day activity rule** and land-cover distance thresholds to link detections across overpasses into fire objects. Then attach each scar patch to at most one fire object. This gives "same fire" identity across cells for the spread thread.

## 12. Benali et al. 2016, "Determining fire dates and locating ignition points with satellite data", Remote Sens. 8:326 (FULL; mdpi-res CDN copy)

Link: https://doi.org/10.3390/rs8040326

This is the only paper read here that validates satellite fire dates against **agency fire records** (5 regions: Alaska, Portugal, Greece, California, SE Australia).

**Method.**
- MODIS active fires inside each mapped perimeter are clustered in time: minimum gap minG = 2 days, maximum gap maxG = 9 days, minimum density minD = 85% (fitted by multi-objective optimisation).
- Clear-sky quality flags decide whether a gap is real (perimeter fully seen, no fire) or cloud.
- Start date = first detection, end date = last.
- **Temporal uncertainty of the ignition = hours back to the last clear-sky overpass that saw the whole perimeter, capped at 72 h.** Example: a night Terra first detection with a clear Aqua afternoon look before it gives about 7 h.

**Database cleaning before validation.**
- They removed records with negative duration, more than 6 months' duration, missing or garbled hours, records outside any perimeter (an optimal 2 km buffer), and records more than 3 days off.
- The agency records had real errors: duplicate records months apart, and points kilometres outside the fire.

**Results.**
- Only **23% of fires (77% of burnt area)** could be dated. "For most fires smaller than 500 ha it was not possible to estimate the start/end dates."
- Start-date agreement MEF 0.91; end-date MEF 0.73.
- Ignitions within **12 h and 2 km** of the reported ones.
- The satellite uncertainties (most under 12 h and under 30% of the fire area) were generally **larger** than the disagreement with records.
- About 60% of perimeters had their ignition narrowed to under 33% of the burnt area.

**Concrete action (labels + field system).** This is the template for recipe A's uncertainty term. Its "last clear non-detecting overpass" is the same as `fire_detection_sources.md` §11's bracket, now with a published definition and a validation protocol. When MP field registers arrive, validate the same way:
- clean the registers with Benali's 5 rules;
- buffer each record 2 km;
- report MEF and lag in hours.

## 13. Brennan et al. 2019, "Theoretical uncertainties for global satellite-derived burned area estimates", Biogeosciences 16:3147 (FULL)

Link: https://doi.org/10.5194/bg-16-3147-2019

**Method.**
- **Multiplicative triple collocation**: ln(X_i) = α_i + β_i ln(T) + ε_i, with each product's random-error variance taken from the sample covariance matrix of the three log-series (McColl et al. 2014).
- Products: MCD64, MCD45, FireCCI50, aggregated to 1° and 16-day bins.
- Logs are needed because burned-area errors are heteroscedastic.

**Results.**
- Global mean annual BA 3.76 ± 0.15 Mkm² (MCD64), 3.70 ± 0.17 (FireCCI50), 3.31 ± 0.18 (MCD45); relative uncertainty 4-5.5%; 8-10% in Africa and Australia.
- About 40% of land cells got no estimate.
- The relative error of the TC estimate itself ≈ **√(5/n)** for n collocated samples (Zwieback 2012), about 33% for their record length.
- The biggest caveat is error cross-correlation (shared MODIS inputs, shared cloud gaps, similar thresholds). A reviewer noted that products with 60-80% omission make the "truth" in TC itself a product-specific concept.

**Concrete action (labels, recipe B).** Triple collocation on **burned hectares per beat per fortnight**, with three sources:
1. our S2/Landsat scar map;
2. a thermal-based area (VIIRS, all three platforms, points × a fixed area per point, or FEDS-style alpha hulls);
3. FSI/MCD64A1 burnt area.

With 94 beats × about 12 fortnights × 8 seasons ≈ 9,000 samples (many zeros; use only beat-fortnights where all three are positive, as Brennan did), √(5/n) gives a few percent relative error on the error estimates. Outputs: each source's random-error variance, plus β (the multiplicative bias).

## 14. Pierdicca et al. (INGV), "Triple collocation to assess classification accuracy without a ground truth in case of earthquake damage assessment", IEEE TGRS (author manuscript, FULL)

Link: https://www.earth-prints.org/bitstream/2122/12123/4/TripleCollClassification2-5Settembre2016_v3.pdf

- Extends triple collocation to **categorical maps (TCCA)**.
- With three classifiers whose errors are **conditionally independent** given the true class, the pairwise confusion matrices XY, XZ and YZ (plus the 3-way table) fix each system's normalised confusion matrix and the class prevalence. For 2 classes it reduces to one polynomial in the prevalence p (their Appendix B).
- Applied to L'Aquila collapsed buildings: two ground surveys (92.7% raw agreement but kappa 0.36) and a VHR classification. Showed the "ground truth" survey was not the most accurate system.

**Concrete action (labels, recipe B).** Exactly our binary "burned in this cell-window?" problem with three raters. The 2×2×2 agreement table has 7 free cells, and the binary latent-class model has 7 parameters: prevalence plus 3 sensitivities and 3 specificities. So it is exactly identified (the Hui-Walter / Dawid-Skene setting).

## 15. Foody 2022, "Global and local assessment of image classification quality on an overall and per-class basis without ground reference data", Remote Sens. 14:5380 (PARTIAL: abstract, methods, discussion)

Link: https://doi.org/10.3390/rs14215380

- A latent class analysis of 4 classifications (LEM software, fit by the L2 statistic, conditional dependence checked with CONDEP) gives a full estimated confusion matrix per classifier. It also gives a **per-pixel posterior** usable as a local quality map, with intermediate values at field edges.

**Concrete action (labels).** The same model with covariates gives a per-label confidence weight for the fire model's loss. Python options: `crowd-kit` (Dawid-Skene) or a 30-line EM; R: `poLCA`, `randomLCA`.

## 16. Reiche et al. 2024, "Integrating satellite-based forest disturbance alerts improves detection timeliness and confidence", Environ. Res. Lett. 19:054011 (FULL)

Link: https://doi.org/10.1088/1748-9326/ad2d82 (Earth Engine code public)

This is the closest published precedent for fusing several sensors' first detections into one dated label.

**Systems and rules.**
- RADD (Sentinel-1), GLAD-S2 and GLAD-L, 10 sites of 1° in the Amazon, 2021.
- **Integrated date = earliest detection among systems.**
- Ruleset-1: "highest" confidence if ≥ 2 systems detect.
- Ruleset-2: highest if 3 systems detect, or 2 with at least one high.

**Results.**

| Measure | Value |
|---|---|
| Producer's accuracy (all classes, 3 systems integrated) | 97% (70.3-100% by site) |
| Single systems: GLAD-S2 / RADD / GLAD-L | 85.7% / 60.2% / 38.3% |
| User's accuracy, all classes (3 integrated) | 89.5% (errors add up) |
| User's accuracy, high + highest classes | 96.6% |
| User's accuracy, highest class (2+ systems agree) | **100%**, no false detections |
| Producer's accuracy, highest class | only 57% (ruleset-1) / 50% (ruleset-2) |

- Detection came days to months earlier. Reaching highest confidence took about 45 days (ruleset-1) or 73 days (ruleset-2) after the first detection.
- A **spatial neighbourhood rule** (40-100 m) raised confidence but **raised false detections**.

**Concrete action (labels).** Use the same three-tier confidence on our labels:
- tier 1 = optical scar only;
- tier 2 = scar + one thermal sensor;
- tier 3 = scar + 2 or more thermal sensors (or + MCD64).

Train on all tiers, but score and calibrate on tier 3 to get an almost commission-free subset. The paper suggests tier 3 is close to error-free but covers about half the events. Avoid large neighbourhood buffers when promoting tiers. This argues against the 750 m match (§0).

## 17. Jethva et al. 2026, "Timing the flames: geostationary satellite detection of diurnally shifting stubble burning in northwestern India", Remote Sens. 18 (NASA NTRS manuscript, PARTIAL)

Link: https://ntrs.nasa.gov/citations/20260005893

- **GK2A-AMI** (128.2°E) sees India every **10 minutes**, but at about 4 km pixels over NW India because of the slant view.
- 3.8-11.2 µm brightness-temperature difference, normalised to the 09-11 IST mean; L2 cloud mask `gk2a_ami_le2_cld_fd020ge`. Data via the KMA NMSC API: https://nmsc.kma.go.kr
- Stubble-burning peaks moved from about 13:00-14:00 IST to **16:00-17:00 IST** after 2022. MODIS and VIIRS fire counts fell 20-71% while aerosols rose: "underreported by polar-orbiting satellites".

**Concrete action (labels).** Two lessons:
1. Diurnal timing of human fires can shift away from the 13:30 pass. Ratapani's 13:30 detection share should be checked against Meteosat IODC hourly data before assuming the ignition-hour prior is fixed.
2. GK2A is a second free 10-minute geostationary source over central India. Ratapani is about 51° east of the sub-satellite point, so the view zenith is roughly 60°+ and the pixel is several km [inference]. It is useful for hour-of-burn only for the largest fires, as with IODC.

## 18. Fusco et al. 2019, RSE 220:30-40, "Detection rates and biases of fire observations from MODIS and agency reports in the conterminous United States" (ABSTRACT ONLY)

- Nearly 250,000 agency-reported fires (FPA-FOD) against MODIS burned area and active fires.
- MODIS detected only **3.5-23.4%** of agency fires > 1 ha, rising with size. Agency records captured **23.5-48%** of MODIS detections.
- Neither source is complete, so both must be treated as imperfect raters, which is the premise of recipe B.

## 19. Other sources checked

- **Roy et al. 2019**, RSE 231:111254, combined Landsat-8 + Sentinel-2 burned area (ABSTRACT ONLY).
  - Random-forest change regression on NBAR reflectance, trained on synthetic spectra, rolling over 3 months to map the central month.
  - Reports the day of burning at burned pixels, with region growing to cut omission from sparse observations. No date-error numbers obtained.
  - Hybrid OA: worth a retry from a non-proxied browser.
- **Boschetti et al. 2015**, RSE 161:27, MODIS-Landsat fusion (ABSTRACT ONLY).
  - Landsat change candidates confirmed by MODIS active fires; validated against MTBS; underestimates area.
  - The same "thermal confirms optical" logic as our tiers.
- **Humber et al. 2018**, IJDE, intercomparison of four products (PARTIAL).
  - Uses space-time "voxels" and heat maps of burned-area dates against MCD14ML. Totals agree, but timing and location differ widely at fine scales.
  - Use voxel (beat × fortnight) agreement matrices to report our cross-source agreement.
- **Marsha & Larkin 2022**, Fire: 2,699 ground fires 2017-19. No single satellite product (HMS, GOES-16, MODIS, VIIRS) estimated burned area best; they recommend an ensemble (search snippet only).

---

## A. Recipe: per-patch burn-date interval with uncertainty

Inputs:
- `rasters/burn_<season>.tif` (per-pixel `ws`, `we`, NBR drop);
- `clear_calendar.parquet`;
- all thermal detections: VIIRS S-NPP + NOAA-20 (2018-) + NOAA-21 (2023-) 375 m from the FIRMS archive (`VNP14IMGTDL`/`VJ114IMG`/`VJ214IMG`, standard archive SP); MODIS C6.1 (Terra and Aqua, 1 km); Sentinel-3 SLSTR FRP (2020-); our own S2/Landsat active-fire rule (from `fire_detection_sources.md` §8-9); optionally Meteosat IODC FRP-PIXEL (hourly).
- For each sensor we also need the **list of overpasses that observed the patch clear** (FIRMS has no "observed, no fire" record). Approximate it with the orbit times: VIIRS swath ±56° covers Ratapani at every pass, with cloud from VIIRS/MODIS cloud masks or ERA5 cloud cover if needed [inference].

**Step 1. Patches.** Connected 20 m scar pixels (8-neighbour) whose `we` dates differ by ≤ 5 days; MCD64 uses 10 days, but our windows are shorter. Drop patches under 2 ha as now, or keep them flagged.

**Step 2. Optical bracket per pixel, then per patch.**
- t0 = the `ws` image time: S2 about 10:40 IST, Landsat about 10:30 IST.
- t1 = the `we` image time.
- Patch bracket = [min t0, max t1], with the core interval [max t0, min t1] when non-empty.
- Store the MCD64-style `t_star` = midpoint and `dt` = t1 − t0.

**Step 3. Thermal matching.**
- A detection belongs to a patch if its footprint centre lies within patch + 375 m (VIIRS), patch + 1 km (MODIS), patch + 1 km (SLSTR, about 1 km pixel) or patch + 3 km (IODC).
- VIIRS with `scan` > 0.8 km is down-weighted (Veraverbeke uses view zenith ≤ 40°).
- Accept detections in [t0 − 0 h, t1 + 24 h]: allow the afternoon of `ws` (§0 bug) and one day after `we` (smouldering).
- Link detections within 1,125 m and 5 days into one event (Briones-Herrera; FEDS).

**Step 4. Interval.**
- Earliest = the later of t0 and the last clear pass that saw the patch with no detection, from any sensor (Benali's uncertainty definition).
- Latest = the earliest detection time, or t1 if there is none.
- If detected: burn day = UTC `acq_date` of the first detection for both 13:30 and 01:30 passes (§0). Uncertainty in hours = latest − earliest (Benali caps at 72 h).

**Step 5. Day distribution for undetected patches (the 62%).**
P(day d) ∝ prior(d) × Π over clear passes o on day d of (1 − p_s · a(o − h)), where:
- prior(d) = the §0 empirical offset distribution (≈ 0.20, 0.20, 0.15, 0.14, 0.12 for days 0-4 of a 5-day window) × the fire-weather prior already in the model;
- p_s = the per-pass detection probability of sensor s for Ratapani fires (estimate it as in B2);
- a(·) = the probability that the fire is still active at the pass. Use 84% one-day and 10% two-day persistence (§0); litter fires burn a few hours [inference].

Output per patch: `fire_day_map`, P(fire_day = d) for each d, the 50% and 90% interval, `n_sensors_detected`, `tier`.

**Step 6. Hour (optional, big fires only).** Inside the detection day, use the first IODC or GK2A hot pixel, or else the diurnal prior (12:00-17:00 IST peak). Benali reports about 12 h typical uncertainty with polar sensors only.

**Step 7. Use in the model.** The strict true-lead label becomes soft: target at t = Σ_d P(d) · 1[d − t ∈ {1, 2}]. Use weighted loss or drop patches with a 90% interval longer than 3 days.

**Expected improvement** [inference, with stated basis]:
- The §0 fix alone moves about 1,185 of 6,040 dated labels (19.6%) to the correct day. These are the most common error in the strict positives, and the change is free.
- Adding NOAA-20/21 VIIRS: about 50 minutes apart in the same orbit, partly independent views of the same fire. If per-pass detection is p ≈ 0.4, two passes take the dated share to about 1 − 0.6² ≈ 64% of what one pass achieves twice. Expect the dated share of first burns to rise from 38% to roughly 45-50%; 2018-2024 only, and the 2025-26 seasons need the NOAA files anyway.
- SLSTR night (22:00) and S2/Landsat active fires each add a few percent.
- The probabilistic prior turns the remaining undated windows from "5 equal days" into a distribution with about 40% mass on the first two days (§0).

**Validation without ground truth.**
1. Leave-one-sensor-out: for patches with detections from 2+ sensors, hide the earliest sensor and check whether the recipe's interval contains the hidden detection. Report exact / ±1 / ±2 day agreement as in Parks.
2. Against MP fire registers and FSI feedback records when obtained, using Benali's cleaning rules, a 2 km buffer, MEF and lag in hours.

## B. Recipe: label recall and precision from sensor overlap

**B1. Units.** Use "fire events" at cell × window level (or patch level), Jan-Jun, 2018-2024, so that NOAA-20 exists. Stratify by:
- month (Jan, Feb, Mar, Apr, May-Jun);
- scar size class (≤2, 2-5, 5-10, >10 ha);
- FRP class (when thermal);
- pre-fire NDVI.

**B2. Per-pass thermal detection probability (two-source capture-recapture).**
- S-NPP and NOAA-20 view the same fires about 50 minutes apart.
- For fires known to be active (patches with a scar and detections on that day): p_SNPP ≈ (#both)/(#NOAA-20), and p_N20 ≈ (#both)/(#S-NPP).
- Do it per FRP and size stratum, so that heterogeneity in detectability, which biases Lincoln-Petersen, is absorbed. The two sensors are near-identical, so the estimate is of detectability given the fire, not of fire occurrence.
- This gives the p_s that recipe A step 5 needs.

**B3. Scar recall (from thermal).**
- Recall_scar ≈ P(scar | thermal event) per stratum. Today: 64.6% overall; 55-81% across FRP classes; 47% in January (§0).
- Thermal-visible fires are biased large and hot. Report this as an upper bound, and extrapolate the FRP trend to the smallest class for a central estimate (about 50-55%).
- Cross-check against the visual blind-check area recall (0.71).

**B4. Precision and recall jointly (three-rater latent class).**
- Raters per cell-window:
  - R1 = Sentinel-2-only scar map;
  - R2 = Landsat-only scar map (per-sensor maps, as `alert_burn_scars_fullread.md` already suggests building);
  - R3 = any thermal detection (VIIRS × 3 + MODIS + SLSTR).
- An alternative R3 is MCD64A1 for patches over 10 ha.
- Fit the binary Dawid-Skene / Hui-Walter model by EM per stratum (TCCA, Pierdicca). It gives each rater's sensitivity and specificity, the burn prevalence, and a per-cell-window posterior P(burned) usable as a label weight (Foody).
- Caveat: R1 and R2 share physics (optical NBR), so their errors are positively correlated (dark shadows, haze, light ground fires both miss). This biases recall estimates upward.
- Mitigation:
  - fit with stratum covariates;
  - check conditional dependence on the 376 judged points;
  - add a 4th rater (MCD64A1 or Prithvi) and fit a model with one pairwise dependence term (4 raters allow this).

**B5. Area-error variances (triple collocation).** §13 on beat × fortnight burned hectares: scar map vs thermal-derived area vs FSI burnt-area or MCD64A1. Log-transform and keep only cells with all three positive. Gives each source's random error and β (multiplicative bias).

**B6. Date error.**
- For tier 2-3 labels: distribution of (first thermal detection − scar t\*), as in Boschetti 2010 and Giglio 2018.
- For all labels: the posterior interval width from A.
- Report the share within 0, ±1 and ±2 days.

**B7. Ground anchor.** The 376 visually judged points stay as the small reference set. Estimate the latent-class outputs' bias on them, then apply the correction elsewhere.

**Expected improvement** [inference]:
- Per-stratum precision and recall replace one global 0.83/0.71 pair. We should see January and the < 2 ha class as the weak cells, consistent with §0 and the README.
- Down-weighting labels with posterior < 0.5, and making tier-3 labels the scoring set, should cut label noise in the scoring target the most where it matters (Jan-Feb, small scars).
- The size of the model gain is unknown. A sensible test is to retrain the lean LightGBM with soft labels and weights, and score on tier-3 true-lead labels only.

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| MCD64A1 C6.1 (Burn Date, Uncertainty, QA, First/Last Day) | https://lpdaac.usgs.gov/products/mcd64a1v061/ | 500 m, daily dates, monthly files | Nov 2000- | NASA open | Earth Engine `MODIS/061/MCD64A1`; LP DAAC (Earthdata login) |
| VNP64A1 v002 | https://lpdaac.usgs.gov/products/vnp64a1v002/ | 500 m (750 m inputs) | 2012- | NASA open | LP DAAC; check the Earth Engine catalogue |
| FireCCI51 (BurnDate, ConfidenceLevel) | https://developers.google.com/earth-engine/datasets/catalog/ESA_CCI_FireCCI_5_1 | 250 m | 2001-2020 | ESA CCI open | Earth Engine `ESA/CCI/FireCCI/5_1` |
| VIIRS 375 m active fires, S-NPP / NOAA-20 / NOAA-21 (archive SP + NRT) | https://firms.modaps.eosdis.nasa.gov/download/ | 375 m, 2 passes/day/satellite | 2012- / 2018- / 2023- | NASA open | FIRMS archive download (MAP_KEY), country = India, by satellite |
| MODIS C6.1 active fires (MCD14ML) | FIRMS, as above | 1 km | 2000- | NASA open | FIRMS archive |
| Sentinel-3 SLSTR FRP (NRT/NTC) | Copernicus Data Space | ~1 km, ~10:00 / 22:00 | 2020- | Copernicus open | CDSE or FIRMS (if listed) |
| Meteosat IODC FRP-PIXEL | LSA SAF (see `fire_detection_sources.md` §2) | ~3-4 km at India, 15 min | 2017- | EUMETSAT open | LSA SAF registration |
| GK2A AMI L1B 3.8/11.2 µm + cloud mask | https://nmsc.kma.go.kr | ~2 km nadir, several km at India, 10 min | 2019- | KMA, free registration | NMSC API |
| Global Fire Atlas (for method only) | https://doi.org/10.5194/essd-11-529-2019 | 500 m | 2003-2016 | CC BY | ORNL DAAC |
| FEDS code/data (California) | https://doi.org/10.1038/s41597-022-01343-0 | 375 m based | 2012-2020 | CC BY | Zenodo/GitHub linked in the paper |
| Reiche 2024 alert-integration Earth Engine code | https://doi.org/10.1088/1748-9326/ad2d82 | n/a | n/a | open | Code link in the paper |

---

## Ranked action list

| # | Action | Thread | Gain (my estimate) | Effort |
|---|---|---|---|---|
| 1 | **Fix the clip in `build_true_lead_labels.py`**: allow fire day = `ws` when the first VIIRS is the afternoon of `ws` (or night of ws→ws+1). Use the UTC `acq_date` as the burn day for both passes. Rebuild the strict and lenient labels and re-score. | labels, 1 | Corrects ~19.6% of dated labels, which are now 1 day late (positives then include same-day nowcasts) | 1 h | DONE 14 Oct: v2 file built; pipeline re-scored strict lean 39.5% (v1 38.9%), ensemble 40.7%, random 20.0%; SCORING.md uses v2.
| 2 | Match VIIRS to **patches + 375 m buffer, scan ≤ 0.8 km**, instead of 750 m around the cell centre. Report how many dates change. | labels | Removes neighbour-fire dates. Today the cell-level match is 13% vs 38% at 750 m. | 0.5 day |
| 3 | Add **NOAA-20/21** (and MODIS, SLSTR) to dating with the bracket rule (recipe A steps 3-4), and store `n_sensors` and `tier`. | labels, 1 | Dated share 38% → ~45-50%; tier-3 near-commission-free subset (Reiche) | 1 day |
| 4 | **S-NPP vs NOAA-20 capture-recapture** for per-pass detection probability by FRP and size (B2). | labels | Gives p_s for the undated-day posterior; also a recall estimate for the live alerts | 0.5 day |
| 5 | **Soft labels for undated windows**: §0 empirical prior × pass non-detections (A step 5); retrain the lean model with weights. | 1 | Cleaner true-lead target; unknown gain, test against tier-3 scoring | 1 day |
| 6 | **Three-rater latent class** (S2-only, Landsat-only, thermal) per stratum; per-label posterior P(burned). | labels | Per-month and per-size precision and recall without field data; label weights | 1-2 days (needs per-sensor maps) |
| 7 | Pull **MCD64A1 + FireCCI51** for Ratapani from Earth Engine as extra raters, and for **triple collocation** on beat-fortnight hectares. | labels | Error variance per source; corroboration of scar recall | 0.5 day |
| 8 | Store **MCD64-style `t_star` and `dt`** per pixel in the scar rasters; apply the local-minimum ignition filter (Andela) inside patches. | labels, 4 | Ignition zones per patch for the spread thread | 1 day |
| 9 | Field-register validation protocol (Benali): cleaning rules, 2 km buffer, MEF, lag in hours. Run it when MP registers or FSI feedback arrive. | 5, labels | The only true date-error measure | 0.5 day once data exist |
| 10 | Check Ratapani's diurnal fire cycle with IODC (and GK2A) before trusting the 13:30 snapshot as the typical time. | labels, 5 | Guards against the NW-India-style afternoon shift | 1 day |

Not worth doing for Ratapani: Global Fire Atlas or MCD64A1 as labels (they miss fires under 100 ha); kriging or IDW of day-of-burning across patches (Parks: "inappropriate for small fires ≪500 ha"); Briones-style convex hulls (built for fires over 1,000 ha).
