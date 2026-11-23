# Time of day of Ratapani fires, what the 01:30/13:30 passes miss, and how to tell Forest Department burns apart (scouting round 7, topic "diurnal", 14 Oct 2026)

Scope: (a) the time of day of fires in central Indian dry deciduous forest, what the polar passes miss, and whether a 13:30 fire started that morning; (b) controlled and fire-line burning in MP and how to separate it from wildfire in satellite data.

What is already covered elsewhere, so not repeated here:
- Geostationary products (IODC SEVIRI, INSAT-3D/3DR/3DS, FY-4, Himawari, GK2A), their pixel sizes at Ratapani and FIRMS geostationary access: `fire_detection_sources.md` §1-5, 11.
- Jethva 2026 (GK2A, NW India stubble): `fire_cause_signatures.md` B1 and `burn_dating_validation.md` §17.
- Fire-line rules, the FFPM/CAMPA budgets, the World Bank 2018 report, the `probable_managed` label rule and the Uttarakhand 12-19% figure: `fire_management_practice.md` Parts A and D, `field_alert_systems*.md`.
- Weekly cycle (none found), linear scar share (3.9% of patches) and night share by month: `fire_cause_signatures.md` C1-C3.

Sources marked FULL, PARTIAL or ABSTRACT ONLY. My own reasoning is marked [inference]. Scripts: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_diurnal/`. Clipped FIRMS files (MODIS 2013-2025, NOAA-20 2018-2025, Ratapani AOI): `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r7_diurnal/modis_aoi.parquet` and `n20_aoi.parquet`. These are scratch files, so copy them if you want to keep them.

## Headline findings

1. **A fire seen at 13:30 almost always started that same day.** Only 3-6% of daytime VIIRS alerts in the FSI 2025-26 export, and 10-17% in our S-NPP 2013-2024 record, had a detection within 0.75-1.5 km at the 01:30 pass the night before. In Nov-Feb the figure is 0-5%. [inference] For a 13:30 detection, the ignition window is roughly 02:00-13:30, and the diurnal cycle puts most of that in the late morning.
2. **Many fires start after the 13:30 pass.** 61-81% of S-NPP 01:30 detections, and 83-90% of FSI 2025-26 night alerts, had no 13:30 detection nearby that afternoon. 26% of FSI "large fire events" around Ratapani (149 of 566) were first seen at night. The Aqua MODIS pass, which had drifted to about 15:18 IST by 2025-26, saw fires that VIIRS had not seen at about 13:30 in 62-75% of cases. A 2.5-hour gap is enough for a new fire to start.
3. **The literature puts the India burning peak late.** Giglio's TRMM-VIRS analysis gives India a peak at **16:30 local time, a median at 16:18 and an IQR of 3.0 h**. That is the latest peak of the 15 tropical regions except Brazilian cropland and eastern Australia. Deciduous woodland in Africa has a narrow diurnal window of 2-4 h (Roberts 2009). [inference] The 13:30 pass therefore samples the rising limb of the cycle. Fires lit after about 14:00 that die before 01:30 are never seen by S-NPP.
4. **Winter fires are lit late in the morning or at midday, and are out by night.** Aqua (13:40 IST) caught 83-87% of Jan-Feb MODIS daytime detections. Terra (11:05 IST) caught only 13-17%. In April the split is about even (Aqua 57%). The night share is 0-9% Nov-Feb, against 28-41% Mar-May (FSI 2025-26). [inference] This fits crews who light fire lines during working hours and put them out or let them burn out by evening. It strengthens the "daytime only" condition in the existing `probable_managed` rule.
5. **Winter detections hug the sanctuary boundary, not roads.** Nov-Jan daytime VIIRS points: 43% within 1 km of the AOI boundary, against 29-30% in Feb-Apr and 37% for random points. Within 375 m of a Microsoft-detected road: 12%, against 16% for random points. [inference] Boundary fire lines, plus field-edge and village burning, are a better winter signature than roads.
6. **Adding NOAA-20 adds about 33% more fire cell-days than S-NPP alone** (2018-2024, measured with a neighbour-tolerant 500 m match). S-NPP and NOAA-20 agree on only 65% of daytime points (56% in Nov-Feb). MODIS adds only 2% more. NOAA-20 and MODIS can be downloaded **without a MAP_KEY** from the FIRMS country archive.
7. [inference, toy model] With ignitions peaking around 13:00-14:00 and median burning times of 4-8 h, which matches our observed 28% night share and the 60-80% of night detections that have no day detection, **about 30-60% of fires are not burning at either S-NPP pass**. That is a ceiling on label recall for any single-satellite label, before any detection-probability loss.

---

## Part A. What our own data shows (DATA, computed 14 Oct 2026)

### A1. Pass-to-pass persistence in S-NPP VIIRS 2013-2024 (`viirs_snpp_2013_2024.parquet`, 5,815 day and 2,302 night points)

A night point on UTC date D is the 01:00-03:00 IST pass that follows the 13:30 pass of D. The value is the share of points that have a point from the other pass within the given radius.

| Test | 750 m | 1.5 km | Mar-Apr (1.5 km) | Nov-Feb (1.5 km) |
|---|---|---|---|---|
| Night point has a day point that afternoon | 18.6% | 39.0% | 40.3% | 33.0% |
| Day point has a night point the night before | 9.9% | 17.4% | 21.0% | 7.9% |
| Day point still burning at 01:30 (same UTC date) | 7.6% | 17.8% | 21.5% | 7.4% |
| Day point seen again at next 13:30 | 4.2% | 16.0% | 18.6% | 9.4% |
| Night point seen at the next 13:30 | 24.2% | 39.9% | 41.1% | 38.0% |

[inference] A litter-fire front moves about 0.5-2 m/min, so it can cover 0.4-1.4 km in 12 h. The 1.5 km column is the fairer one for "same fire". Even then, most fires appear at only one pass.

### A2. FSI portal alerts, Nov 2025 to Oct 2026 (`fsi_portal/fsi_pts_*.csv` plus `obd_2026.csv`, 3,104 unique points)

- Sources: 2,810 VIIRS points and 294 MODIS points.
  - VIIRS day times run 12:30-14:35 IST and mix S-NPP, NOAA-20 and NOAA-21. VIIRS night times run 01:00-03:59 IST.
  - **MODIS points are all Aqua.** Day passes fall at 14:42-15:54 IST (median 15:18), and 4 night points fall at 03:36-03:54. That is Aqua's drifted orbit. There are **no Terra morning alerts** in the 2025-26 FSI feed.
- Night share of VIIRS alerts by month: Nov 6/70 (8.6%), Dec 0/32, Jan 0/79, Feb 12/298 (4.0%), Mar 307/1105 (27.8%), Apr 403/974 (41.4%), May 85/217 (39.2%).
- Cross-pass checks (all at 750 m / 1.5 km):
  - An Aqua (~15:18) alert had a VIIRS day alert the same date: 25.5% / 37.9%. By season: Mar-Jun 29% / 42%, Nov-Feb 17% / 28%.
  - A VIIRS day alert had a VIIRS alert at 01:00-03:59 that morning: 3.3% / 6.2%. In Nov-Feb: 0% / 0.9%.
  - A VIIRS night alert had any day alert the previous afternoon: 10.3% / 16.9%.
- Winter compartments: 564 Nov-Feb alerts fell in 349 compartments, 1.6 per compartment. The top 10 compartments hold 11%, against 5.1% in Mar-Jun. 62.5% of compartments with a winter alert also had a spring alert. [inference] The winter burns are spread thin, not repeated on a few lines.

### A3. FSI "large forest fire" events (`lff_mp.csv`, MP 2019-2025)

- **MP (7,536 events).**
  - First-detection hour: 12:00-14:59 in 74%, and 01:00-02:59 IST (night pass) in 26%.
  - 62% are single-detection events.
  - Duration p75 is 23.7 h, p90 58.5 h, p95 72.7 h.
  - Night first-detection share by month: Jan 2%, Feb 13%, Mar 27%, Apr 28%, May 22%, Nov 7%, Dec 0%.
- **Ratapani box 77.2-78.1 E, 22.7-23.3 N (566 events).**
  - 149 events (26.3%) were first detected at night.
  - 59.5% are single-detection events.
  - Duration p90 is 60 h.
  - Night first-detection share by month: Feb 9%, Mar 31%, Apr 24%, May 50% (n = 18), and 0% in Nov-Jan (n = 13).

### A4. Terra vs Aqua MODIS inside the AOI, 2013-2025 (FIRMS country archive, 1,242 points)

- Overpass times (median IST):
  - Terra ran at 10:59-11:20 in 2013-2022, then drifted to 10:44 (2023), 10:24 (2024) and 10:07 (2025).
  - Aqua ran at 13:39-13:52, then drifted to 14:08 (2024) and 14:42 (2025).
- Aqua share of daytime MODIS points, Aqua / (Aqua + Terra), all years:

| Month | Jan | Feb | Mar | Apr | May | Nov | Dec |
|---|---|---|---|---|---|---|---|
| Aqua share | 0.87 | 0.83 | 0.70 | 0.57 | 0.54 | 0.77 | 0.77 |
| n | 85 | 233 | 548 | 240 | 13 | 13 | 35 |

  For 2013-2021 only (before the drift): Jan 0.89, Feb 0.85, Mar 0.70, Apr 0.62.
- On the 52 days when both satellites detected fires:
  - Only 34% of Terra points (Mar-Jun) had an Aqua point within 1.5 km 2.5 h later. Nov-Feb: 15%.
  - Only 20% of Aqua points had been seen by Terra. Nov-Feb: 13%.
- Night share of MODIS points is 0% in Nov-Jan, 2% in Feb and 8% in Mar-Apr.
- Median FRP: Aqua 18.2 MW vs Terra 13.7 MW in Mar-Jun. Aqua 11.1 MW vs Terra 12.7 MW in Nov-Feb.
- Caveat [inference]: winter morning haze and fog over central India lowers Terra's detection rate, which inflates the Jan-Feb Aqua share somewhat. The co-location numbers are also capped by MODIS's own detection probability (Giglio 2006 thesis: Pd = 0.45 for Indian scenes). Treat these numbers as directional only.

### A5. NOAA-20 against S-NPP inside the AOI, 2018-2024

- Counts: NOAA-20 has 4,732 points (5,589 including 2025) and S-NPP has 5,370. The night share is 30.8% for NOAA-20 and 27.9% for S-NPP.
- Day-pass agreement, on the 388 days when both detected: 64.8% of NOAA-20 points have an S-NPP point within 750 m, and 65.6% the other way round. By season: Nov-Feb 56% / 55%, Mar-Jun 67% / 68%. Night-pass agreement: 70% / 75%.
- **Fire cell-days (about 500 m cells)**: S-NPP 4,802, NOAA-20 4,260.
  - NOAA-20 cell-days with no S-NPP detection in the 3×3 neighbourhood on the same date: **1,575 (+32.8%)**.
  - MODIS adds 168 more (+2.2%). Of these, 64 are Terra-only (morning).

### A6. Distance of VIIRS points (S-NPP + NOAA-20) to Microsoft roads and to the AOI boundary

| Group | n | median FRP (MW) | median distance to road (m) | share ≤375 m from road | median distance to boundary (m) | share ≤1 km from boundary |
|---|---|---|---|---|---|---|
| Nov-Jan day | 786 | 4.1 | 1,322 | 12.2% | 1,199 | **43.3%** |
| Feb day | 1,545 | 4.5 | 1,236 | 11.5% | 1,730 | 29.4% |
| Mar-Apr day | 7,046 | 5.9 | 1,127 | 16.0% | 1,646 | 29.8% |
| Mar-Apr night | 3,405 | 1.5 | 1,246 | 9.9% | 1,635 | 29.8% |
| Random points in AOI | 60k | – | 1,066 | 16.2% | 1,399 | 37.4% |

(The Microsoft roads file is `scouting/data/ms_roads_rata.tsv`.)

### A7. Toy model: what share of fires is never active at a 13:30 or 01:30 pass (`sim.py`) [inference]

- Setup: ignition hour ~ Normal(μ, σ); burn duration lognormal with median D. A fire counts as "seen" if it is active at either pass.
- The settings that reproduce our observed night share (0.28-0.31) and night-only share (0.6-0.8) are μ = 13-14 h, σ = 1.5-2.5 h, D = 4-8 h.
- Under those settings, **30-59% of fires are active at neither pass.** With D = 2 h the share is 55-72%.
- This is before any detection-probability loss.

---

## Part B. Literature

### B1. Giglio, L. 2006. *Characterization of the global satellite fire record* (PhD dissertation, University of Maryland), chapters 3 and 5. The basis of Giglio 2007, RSE 108:407. https://dataserver-coids.inpe.br/queimadas/queimadas/Publicacoes-Impacto/material3os/2006_Giglio_GlobalDetection_UMaryland_DE3os.pdf **PARTIAL** (246 pp; chapter 3 validation tables and all of chapter 5 on the diurnal cycle read)

**What it shows**
- 7.2 years of TRMM VIRS data, corrected for cloud and overpass bias, covering 15 regions.
- **India: peak 16.5 ± 0.2 h, median 16.30 ± 0.09 h, IQR 3.0 ± 0.2 h** (local solar time). Dominant land cover is woody savanna, cropland and evergreen broadleaf.
- Other regions for comparison: Southeast Asia peak 15.0 h; Central Africa 13.42 h (IQR 1.3); Southern Africa West 14.9 h; Brazil rainforest 13.6 h (IQR 1.9); SE USA 14.0 h (IQR 3.41).
- Across regions, peak burning falls at 13:00-18:30. Heavily forested regions peak earlier.
- IQR rises as tree cover falls (r = 0.81). Fine herbaceous fuel lets people burn at any hour, so the cycle is set by human activity.
- Chapter 3: MODIS probability of detection against ASTER was **0.45 for India**, against 0.8-0.9 elsewhere. Half of Indian fire clusters were three ASTER 30 m pixels or smaller. The probability of false alarm was 9×10⁻⁸.

**Concrete action for us**
- Thread "Cleaner fire labels" and thread 2 (dating): replace the generic "12:00-17:00 peak" diurnal prior in `burn_dating_validation.md` step 6 with this curve as the starting prior: Gaussian-like, peak about 16:30 local (about 16:50 IST at 77.5 E), IQR 3 h. Then refit it to Ratapani once IODC data are in (action 3).
- Threads 1 and 5: when an alert's VIIRS time is 13:30, treat the fire as likely to keep growing for about 3 h. Field teams dispatched after the FIRMS NRT latency of about 3 h will arrive near the diurnal peak.

### B2. Giglio, Csiszar & Justice 2006, "Global distribution and seasonality of active fires as observed with the Terra and Aqua MODIS sensors", JGR 111:G02016. https://dataserver-coids.inpe.br/queimadas/queimadas/Publicacoes-Impacto/material3os/2006_Giglio_etal_GlobalDistribuiton_JGR_DE3os.pdf **FULL**

**What it shows**
- 90% of tropical MODIS fire pixels are detected by day. So the Aqua fraction, Aqua / (Aqua + Terra), measures the mid-morning to early-afternoon cycle.
- The paper defines three classes:
  - about 100% Aqua: rainforest, where no morning fire is seen;
  - **about 75% Aqua: "predominantly early afternoon fire activity"**, typical of Southeast Asia and southern Africa;
  - about 50%: multi-day fires that burn for days to weeks.
- Terra and Aqua monthly series correlate at about 0.9 in most regions.
- India and Southeast Asia contribute "relatively low FRP".

**Concrete action for us**
- Thread "Cleaner fire labels": our Ratapani Aqua fraction (A4) is 0.83-0.87 in Jan-Feb, which is "afternoon-only, short fires". In April it is 0.57, close to "multi-day fires". Add a monthly `diurnal_class` note to the label documentation.
- Thread 1: add a feature `aqua_frac_beat_month`, the 2013-2021 Aqua share per beat. It measures how morning-active a beat is (persistent, overnight fires vs fresh afternoon ignitions). Expected gain is small. Test it as one LOSO feature.

### B3. Andela, Kaiser, van der Werf & Wooster 2015, "New fire diurnal cycle characterizations to improve fire radiative energy assessments made from MODIS observations", ACP 15:8831-8846. https://acp.copernicus.org/articles/15/8831/2015/ **FULL**

**What it shows**
- Hourly SEVIRI FRP at 0.1° for 2010-2012 in Africa and the Mediterranean, fitted to a Gaussian: ρ(t) = ρbase + (ρpeak − ρbase)·exp(−(t − hpeak)²/2σ²).
- Fitted parameters by land cover (Table 1):

| Land cover | σ (h) | hpeak | ρpeak / MODIS mean daytime FRP |
|---|---|---|---|
| Tropical forest | 0.85 | 13.34 | 3.03 |
| Woody savanna | 0.94 | 13.21 | 3.07 |
| Savanna | 1.09 | 13.08 | 2.88 |
| Cropland | 0.95 | 13.33 | 2.94 |
| Shrubland | 1.35 | 13.16 | 2.87 |

- **Peak FRP is about 3 times the FRP seen at the MODIS pass.**
- Where cloud is frequent and activity peaks in the late afternoon, **over 50% of FRE came on days with no SEVIRI fire at MODIS overpass times**.
- Assuming persistence between passes over-estimated FRE (163% overall; 179% in tropical forest). The climatological diurnal approach gave 97% overall.
- At 0.1° daily resolution, the simple persistence model gave the best correlations.

**Concrete action for us**
- Thread 4 (spread) and thread 3 (fuel): VIIRS FRP at 13:30 understates peak intensity by about 3 times. If spread or fuel-consumption calibration uses VIIRS FRP, scale it by the diurnal shape rather than assuming constant burning.
- Thread 2: their result that over 50% of FRE is missed on late-peak days supports dating scars with the multi-sensor time bracket rather than one pass.

### B4. Roberts, Wooster, Perry et al. 2009, "Annual and diurnal African biomass burning temporal dynamics", Biogeosciences 6:849-866. https://bg.copernicus.org/articles/6/849/2009/ **PARTIAL** (diurnal, validation and land-cover sections read)

**What it shows**
- SEVIRI 15-min fire pixels for Africa, 2004.
- Fire activity is low between midnight and 07:00 local time, rises quickly, and **peaks around 14:00**.
- **Deciduous forest and woodland have the narrowest diurnal width, 2-4 h.** Open grassland is 4-8 h wide, with mid-morning and mid-afternoon peaks.
- Mean per-pixel FRP peaks in the early afternoon at about twice the night-time value.
- SEVIRI false alarms are 6-8% of fire pixels, carrying 4-6% of FRP. Fires are detectable when they cover 0.01-0.1% of a pixel.

**Concrete action for us**
- Thread "Cleaner fire labels" [inference]: a 2-4 h burning window means a litter fire lit at 14:00 is usually out before the 01:30 pass. Our 28% night share therefore says a sizeable minority of fires creep for 12 h or more. Night detection is a good marker of a long-burning, "real" wildfire, and absent night detection a weak marker of a short, managed burn.
- Thread 5: patrol windows. Most fires appear in the 3-5 h after late morning. Put staff on lookout or patrol from about 11:00 to 18:00 in Mar-Apr.

### B5. Nowell, Holmes, Robertson, Teske & Hiers 2018, "A new picture of fire extent, variability, and drought interaction in prescribed fire landscapes", GRL 45 (PMC6474124). https://pmc.ncbi.nlm.nih.gov/articles/PMC6474124 **FULL** (all but the last 6% of the page, which holds references and the supplement link)

**What it shows**
- Florida, 2004-2015. Permitted burn records (OBAs) are checked against mapped fires: 95.4% of 4,300 mapped prescribed fires matched a permit, with median location error 0.7-0.8 km.
- Total fire area is 9.9×10⁵ ha/yr, and **92% of it is prescribed**.
- Satellites detect only about 25% of it: GFED 27%, BAECV 24%, HMS 28%. The under-count is about 5× where small fires dominate and about 2.7× where large fires dominate.
- Most prescribed fires are under 20 ha.
- Prescribed burning peaks Dec-Apr. It has a strong weekday cycle: 3,400 ha/day Tue-Thu against 1,000-1,500 at weekends. Wildfire has no weekly cycle.
- Prescribed burning is postponed in drought: prescribed area vs KBDI R² 0.28. Wildfire and prescribed anomalies anticorrelate (R = −0.53).

**Concrete action for us**
- Thread "Cleaner fire labels": our previous weekly-cycle test found nothing, on all fires. Redo it on the **Nov-Feb day-only, no-night-detection subset**, with S-NPP and NOAA-20 combined so n is roughly doubled. Department burns would show a Sunday dip. If p < 0.1, add "weekday" as a fifth weak condition to `probable_managed`.
- Thread 1: test whether winter fire counts fall in dry weeks (Nowell's drought postponement). Expect no effect [inference], because MP fire-line burning is calendar-driven.

### B6. Liu, Hu, Yu, Waller, Tian, Ruminski & Robertson 2015, "Evaluating satellite based fire detection in GA" (Emory/Georgia Tech AQAST workshop slides). https://hires.ce.gatech.edu/documents/AQAST-Workshop-2015/Liu-Evaluating%20Satellite%20Based%20Fire%20Detection%20in%20GA.pdf **FULL** (slides)

**What it shows**
- NOAA HMS (GOES, MODIS and AVHRR merged) against Georgia 2011 permit and wildfire records: the **detection rate is about 12%**. 80% of Georgia fires are under 0.2 km². Fire size is the strongest control.
- 22% of permits lack an accurate location.
- Detection is higher in winter and spring, when larger burns occur.

**Concrete action for us**
- Thread 5: when the department's planned-burn register exists, expect only about 10-30% of logged burns under 20 ha to be visible in VIIRS [inference, scaled from the 12% HMS rate and the about 25% in Nowell]. Do not use "no satellite alert" as proof that a planned burn did not happen.

### B7. Debnath, Kiran Chand, Rajashekar & Murthy 2011, "Analysis of multi-temporal satellite data for forest fire characterisation over Central Indian region", ISPRS Archives XXXVIII-8/W20:71-75. https://isprs-archives.copernicus.org/articles/XXXVIII-8-W20/71/2011/ **FULL** (5 pp)

**What it shows**
- MODIS Terra and Aqua fires (confidence > 50%) in MP, Chhattisgarh, Jharkhand and Odisha, 2003-2010.
- March is the peak month, then April.
- In non-Sal (dry deciduous) forest, fire density rises steeply after Julian day 49 (18 Feb). Sal forest rises steadily.
- Leaf fall runs from February to March-April. Fire is related exponentially to temperature (R = 0.78), and LST tracks EVI dryness (R² = 0.86).
- No time-of-day analysis.

**Concrete action for us**
- Thread "Cleaner fire labels": use 18-20 Feb as a data-backed end date for the "managed window". This matches the existing `fireline_burning_window` (Nov to 15-20 Feb). After that date, treat linear day-only burns as possible wildfire along lines, not department burns.

### B8. Mishra, P. (IFS, MP) 2025, "True forest fire management must begin… with understanding the people who light them", Down To Earth. https://www.downtoearth.org.in/amp/story/natural-disasters/true-forest-fire-management-must-begin-not-with-extinguishing-flames-but-with-understanding-the-people-who-light-them **FULL** (opinion piece from a serving MP officer, with data)

**What it shows**
- Dewas division, about 2,000 km² and 870 compartments: about 9,000 FIRMS fires over 2016-2025. About 20 compartments are "very high" and 170 "high" (kernel density, 2 km radius, 250 m cells).
- The season starts in November and peaks Feb-Apr.
- Mahua litter is burnt in March. Nylon nets handed out through JFMCs and the Green India Mission worked only briefly.
- **Surface fires ignite 5-6 weeks before tendu collection, in the patches later harvested.**
- Fire lines are repaired before the season. MP runs the **SimplyFire** web portal.
- There is no mention of department burning or of the time of day.

**Concrete action for us**
- Thread 1: the tendu lead (5-6 weeks before collection) gives a dated feature. With collection in late April to May in Raisen and Sehore, `tendu_prep_window` falls from about mid-March to mid-April in tendu phad units. This was already proposed in `human_fire_drivers.md`; here it gains a lead time.
- Thread 5: ask MPFD for SimplyFire's verified-alert records, with fields for cause, controlled burn and time reported. That is the only route to ground-truth ignition hours.

### B9. Singh, Pradhan, Shukla, Pandya & Sharma 2025, "Active fire detection using Indian geostationary satellite INSAT-3DS", Remote Sens. Earth Syst. Sci. 8:1014-1027. https://doi.org/10.1007/s41976-025-00233-4 **ABSTRACT ONLY** (paywalled; Unpaywall says not OA)

**What it shows**
- A contextual algorithm on 4 km MIR and TIR imagery every 30 min.
- **The probability of detecting high-confidence MODIS fires is 45.31%.**

**Concrete action for us**
- Thread 2 [inference]: INSAT-3DS will see under half of the fires MODIS sees. MODIS in turn sees about 15 fires per 100 NOAA-20 daytime points at Ratapani (A5 year table, 2019-2022). So INSAT-3DS will catch only a few percent of Ratapani VIIRS fires. Use it, as with IODC, only to time the largest fires.

### B10. Williamson, Price, Henderson & Bowman 2013, "Satellite-based comparison of fire intensity and smoke plumes from prescribed fires and wildfires in south-eastern Australia", IJWF 22:121-129. https://doi.org/10.1071/WF11165 **ABSTRACT ONLY** (UTAS copy under permanent embargo)

**What it shows**
- MODIS FRP matched to agency fire databases around Melbourne and Sydney.
- **Wildfires have more extreme FRP than prescribed burns.** Wildfire smoke plumes average about 6 times the size of prescribed-burn plumes.

**Concrete action for us**
- Thread "Cleaner fire labels": supports the "FRP ≤ median" condition in `probable_managed`. In our data the Nov-Jan median day FRP is 4.1 MW, against 5.9 MW in Mar-Apr (A6). The difference is real but small, so FRP should stay a weak, secondary condition.

### B11. Kulkarni & Mehta (WRCS), Melghat Tiger Reserve, mahua collection sheets, Indian Forester. https://indianforester.co.in/index.php/indianforester/article/view/154919 **ABSTRACT ONLY** (search snippet only)

**What it shows**
- Sari-cloth sheets under mahua trees removed the need to burn litter. Daily collection time fell from about 6.78 h to about 1.58 h.

**Concrete action for us**
- Threads 1 and 5 [inference]: mahua flowers drop before dawn and are collected in the morning, so mahua burns are likely lit early, from the morning into midday. That would put them at the Terra pass or in the gap before 13:30. A beat-level Terra share in March (B2 action) is a cheap proxy for mahua-type burning. Check it against known mahua-dense beats.

### B12. Other sources checked

- **Uttarakhand, Nov 2025 to Jan 2026** (ETV Bharat; also NGT amicus report OA 425/2023): of 1,952 alerts, 766 were false, 754 were outside forest and **about 300 (15%) were the department's own controlled burns**. One controlled burn on 11 Mar 2023 was logged only in a paper register. The working-plan fire season is 15 Feb-June. This is already in `field_alert_systems_fullread.md`; it is listed here only to note that 15 Feb is a second, independent anchor for the end of the managed window. **PARTIAL**
- **MP Fire Compendium 2016-2022** (Awadhiya, mpforest.gov.in) and the **mpforest atlas page**: still blocked from this container (connection reset / 503). **Not read.**
- **AP forest fire circular** (forests.ap.gov.in): 503. **Not read.**
- **Giglio 2007 RSE**: **ABSTRACT ONLY**, but its content is in B1.
- **Andela 2015 ACPD discussion and reviews**: not needed.
- **Himawari-8 diurnal studies** (SE Australia 2021; Xu 2017): **ABSTRACT ONLY**. Not useful at Ratapani's 74° view zenith.
- I found no paper giving ignition hours for human-set fires in Indian forests (several searches). **This is an open gap.** Our own pass-persistence numbers (Part A) are the best evidence available.

---

## Part C. How the pieces fit together for each thread [inference]

- **Labels ("Cleaner fire labels", thread 2).**
  - For a day detection, the burn date = the IST date of that detection. This is correct in ≥90% of cases (A1, A2).
  - For a night-only detection (01:00-03:59 IST on IST date D+1), the burn date = D, the previous afternoon. The current rule already uses the UTC `acq_date`, which equals D. Keep it.
  - Night detections that also have a next-day 13:30 detection (24-40%) are multi-day fires. Date the scar to D and flag `multi_day`.
  - About a third to a half of fires are seen at neither pass. Adding NOAA-20 (+33% cell-days) is the largest cheap fix.
- **Managed-burn flag.** Strengthen `probable_managed` with these conditions:
  - (i) date 1 Nov-18/20 Feb;
  - (ii) day-only, with no night detection within 1.5 km on D or D+1;
  - (iii) within 1 km of the sanctuary boundary, or elongated, or on a permanent fire line;
  - (iv) FRP at or below the season median;
  - (v) optionally a weekday, if B5's retest shows a Sunday dip.

  Report the share tagged. Uttarakhand's 15% is the reference.
- **Prediction (thread 1).** Ignition is concentrated after about 11:00, peaking at about 14:00-17:00. A 2-day forecast issued in the evening for "tomorrow and the day after" has the right granularity; nothing finer is needed. A beat-level `aqua_frac` and `night_share` from 2013-2021 describe how persistent fires are in each beat.
- **Alerts and field work (thread 5).**
  - Day alerts (12:30-14:30 passes, FIRMS within about 3 h): the fire is probably still burning when the alert arrives at 15:30-17:30. Send someone the same evening.
  - Night alerts (01:00-03:59): the fire was lit the previous afternoon or evening and is still alive at 01:30. These are the long-burning fires. Verify at first light.
  - Winter day alerts that touch the boundary or a fire line: first check the department's own burn register before dispatching.

---

## Datasets

| Name | Link | Resolution | Years | Licence | How to access |
|---|---|---|---|---|---|
| FIRMS country archive, MODIS C6.1 (Terra and Aqua) | https://firms.modaps.eosdis.nasa.gov/data/country/modis/YYYY/modis_YYYY_India.csv | 1 km, 4 passes/day | 2000-2025 (2026 not yet) | NASA open | **No MAP_KEY needed.** Plain curl, then clip to the bbox with awk (done here, 13 files) |
| FIRMS country archive, VIIRS NOAA-20 | …/data/country/viirs-jpss1/YYYY/viirs-jpss1_YYYY_India.csv | 375 m, 2 passes/day | 2018-2025 | NASA open | Same, no key. 5,589 AOI points |
| FIRMS country archive, VIIRS S-NPP | …/data/country/viirs-snpp/YYYY/viirs-snpp_YYYY_India.csv | 375 m | 2012-2025 | NASA open | Same. Use it to extend our parquet to 2025 |
| FIRMS NOAA-21 | FIRMS Area API (MAP_KEY) | 375 m | 2023- | NASA open | **Not** in the country archive (404 for viirs-jpss2). Needs the API |
| FSI fire points with beat and compartment | `ratapani/fsi/fsi_portal/fsi_pts_*.csv` | point | Nov 2025- | FSI open portal | Local. Has Fire_Time; MODIS is Aqua only |
| FSI large forest fire events | `ratapani/fsi/fsi_portal/lff_mp.csv` | event box | 2019-2025 | FSI open portal | Local. First and last detection to the minute |
| LSA SAF MSG-IODC FRP-PIXEL | https://lsa-saf.eumetsat.int/data/products/fire-products/ | 3 km (about 14 km² here), 15 min | 2017- | EUMETSAT, free registration | HDF5. The only route to an hourly diurnal cycle over Ratapani (see `fire_detection_sources.md` §2) |
| INSAT-3DS 3SIMG_L2P_FIR | https://mosdac.gov.in | 4 km, 30 min | 2024- | ISRO, registration | KML per slot. POD 45% vs MODIS (B9) |
| GK2A AMI L1B (for the Jethva ΔTb method) | https://nmsc.kma.go.kr | 2 km at nadir, 10 min | 2019- | KMA, free registration | Large fires only |
| TRMM VIRS diurnal fire climatology (Giglio) | Giglio 2006 thesis, Table 5.2 | regional | 1998-2005 | Publication | Use the India row as the prior |
| MP Fire Compendium 2016-2022; SimplyFire records | mpforest.gov.in/publicdomain/atlas/ | division / compartment | 2016- | MPFD (CC licence on the compendium) | **Blocked from this container.** Download from an Indian connection, or request from MPFD |
| Microsoft road detections (clipped) | `scouting/data/ms_roads_rata.tsv` | line | 2025 release | ODbL | Local |

---

## Ranked action list

Gain and effort are my estimates [inference] unless marked as measured.

| # | Action | Thread | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Add NOAA-20 (2018-2025) and S-NPP 2025 to the label build and the dating pipeline**, pulled from the keyless FIRMS country archive | Labels, 1, 2 | Country CSVs, AOI clip, `type == 0`, dedupe within 375 m per pass | **+33% fire cell-days (measured).** Recall labels get denser; the dated-scar share should rise by several points | 0.5 day |
| 2 | Strengthen `probable_managed` with the boundary and no-night conditions | Labels → 1 | Date ≤ 20 Feb; no night detection within 1.5 km on D/D+1; ≤1 km of the AOI boundary or elongated or on a fire line; FRP ≤ median. Report the tagged share (target about 15%) | Cleaner positives. Small direct recall change (earlier test: about 0.3 pt), but more honest scoring | 0.5 day |
| 3 | Pull IODC FRP-PIXEL for Jan-Jun 2018-2026 and fit a Ratapani diurnal curve (Andela Gaussian: hpeak, σ) for the top fires | 2, 5, 4 | LSA SAF, 5 km match to VIIRS-dated scars | Replaces the borrowed India prior (16:30, IQR 3 h) with a local one. Hour-of-burn for the largest about 5% of fires | 1-2 days |
| 4 | Store `pass_pattern` per scar: day-only / night-only / day+night / multi-day. Date night-only scars to the previous IST afternoon (current UTC rule, keep it) | Labels, 4 | Rules in Part C | Removes about 1-day errors on the 25-40% of points that persist. Gives the spread model a duration class | 0.5 day |
| 5 | Beat-level `aqua_frac` (2013-2021) and `night_share` as static features | 1 | MODIS AOI file; S-NPP | Small, possibly 0-0.5 pt recall@5. Test in LOSO | 0.5 day |
| 6 | Retest the weekly cycle on the winter managed subset (S-NPP + NOAA-20) | Labels | Nov-Feb, day-only, no night detection | If positive, a fifth managed-burn condition | 2 h |
| 7 | Field rule for verification timing: day alerts the same evening; night alerts at first light; winter boundary or line alerts checked against the burn register first | 5 | Part C | Fewer wasted trips; better verified-label rate | Writing only |
| 8 | Get the MP Fire Compendium and SimplyFire records from an Indian connection or from MPFD | 5, labels | — | Only source of ground-truth cause and time | Slow; low effort for us |
| 9 | Use the diurnal shape when converting VIIRS FRP to intensity or energy (peak about 3× the pass value) | 3, 4 | Andela Table 1 | Avoids under-calibrating spread intensity | 0.5 day |

## Reading status

**FULL 6:** Giglio et al. 2006 JGR; Andela et al. 2015 ACP; Nowell et al. 2018 GRL; Liu et al. 2015 GA slides; Debnath et al. 2011 ISPRS; Mishra 2025 DTE.

**PARTIAL 3:** Giglio 2006 thesis (chapters 3 and 5); Roberts et al. 2009 Biogeosciences; Uttarakhand ETV/NGT reports.

**ABSTRACT ONLY 5:** Singh et al. 2025 INSAT-3DS; Williamson et al. 2013; Kulkarni & Mehta (Melghat); Giglio 2007 RSE; Himawari diurnal studies.

**Blocked:** MP Fire Compendium; mpforest atlas page; AP circular.

**Data analyses:** 7 (A1-A7) on S-NPP, NOAA-20, MODIS and the FSI exports.

> Note (14 Oct 2026): FSI VIIRS alerts were S-NPP until 26 Apr 2026 and NOAA-21 after; Nov-Apr FSI positions sit a median 0.25 km off FIRMS, so FSI-to-FIRMS joins in this note need a radius of about 0.4 km.

> Update (round 8, geostationary_fire_timing.md): GK2A over Ratapani shows local burning peaks around 12:00-13:15 IST, not the 16:30 India-wide prior used above; the "missed by both S-NPP passes" estimate drops to about 20-45%.
