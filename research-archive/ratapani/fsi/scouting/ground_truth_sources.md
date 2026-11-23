# Ground-truth fire records for India, MP and Ratapani: what exists, how to get it, how to use it (gt thread, October 2026)

Scope: records made on the ground, or by officials, that could check or correct our Sentinel-2/Landsat burn-scar labels and their VIIRS dates. That means state fire registers, annual reports, audits, Parliament answers, management plans, FSI feedback and FSI products, news, and research datasets. I prioritised Ratapani, Raisen, Sehore, Bhopal and MP.

Reading status: **FULL** = the whole document, or the whole relevant section, was read from the PDF or page. **PARTIAL** = relevant sections only. **ABSTRACT/SNIPPET** = search snippet or summary only. My own reasoning is marked **[inference]**.

Downloaded files (scratchpad, not shared): `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r3_gt/`. This includes the FSI CSVs described in section 1 (`fsi_pts_{obedullaganj,raisen,sehore,bhopal}.csv` and `lff_mp.csv`). Re-download them into the project if you want to keep them; the commands are given below.

---

## Headline findings

1. **FSI now tags every alert with Division, Range, Block, Beat and forest Compartment number. Since 1 November 2025 these alerts can be downloaded freely as CSV.** For Obedullaganj, Raisen, Sehore and Bhopal divisions (1 Nov 2025 to 14 Oct 2026) I got 1,722, 1,195, 1,644 and 309 rows. Every row carries a `Compartment_No`. Obedullaganj alone covers 130 beats and 376 beat×compartment pairs. This is the official compartment key for our cells, and we have nothing better short of the shapefile.
2. **FSI's Large Forest Fire (LFF) archive for MP downloads as CSV with first and last detection times and a bounding box per event.** It has 7,536 MP events from 2019 to 2025. 1,054 of them fall in Obedullaganj, Raisen, Sehore and Bhopal divisions, and 685 fall inside a box around Ratapani. This is a free check on the dating and extent of our largest scars.
3. **FSI's 2023-24 Burnt Area Report (Sentinel-2 dNBR, with ground checks) gives district figures.** Raisen had 261.12 km² burnt (259.85 km² of it "low"), Sehore 122.70 km², Bhopal 23.63 km². Raisen had the largest area of low-severity burn in MP. Field teams visited 674 burnt patches nationally and 668 were correct. This is the only independent, field-checked burnt-area number at district level, and we can compare our 2024 labels with it.
4. **Officially "recorded" fires in India badly undercount area, and their dates are unreliable.**
   - Recorded MP fires average about 5 ha each (21,869 ha from 4,067 fires in 2007-08; 8,636 ha from 1,737 cases in 13 audited divisions, 2014-18).
   - Recorded MP state totals are 10-25 times smaller than FSI's mapped burnt area [inference: the years differ].
   - The CAG found in Uttarakhand that fires were entered in registers 1-4 days late, that 71 of 73 incidents in one division were missing from the control-room register, and that there was "massive under reporting of burnt area".
   - So registers can tell us **where (compartment) and what cause**, but not **how much area** or **which exact day**.
5. **The "17,142 / 15,878 MP fire incidents" figures in SFRI's 2024-25 report are FSI SNPP-VIIRS detections, not ground records.** 15,878 matches FSI's VIIRS count for MP in 2023-24 exactly. The same applies to almost every Parliament answer since 2018 (FSI MODIS/VIIRS counts). Do not use them as ground truth.
6. **Ratapani's own plans exist but are not public.**
   - There is a Ratapani WLS Management Plan for 2008-09 to 2017-18 (CAG 2022). It lapsed in 2018-19.
   - SFRI Jabalpur supplied data for "preparation of Tiger Conservation Plan for proposed Ratapani Tiger Reserve" to the Sehore, Raisen and Obedullaganj divisions (ARR 2024-25).
   - The CAG found that **Obedullaganj Division did not prepare Fire Plans** during 2014-19.
   - Akkshay will need to request these documents.

---

## 1. FSI Forest Fire portal: beat- and compartment-tagged alerts (FULL: portal pages, API and CSVs fetched directly)

Link: https://fsiforestfire.gov.in/FirePointSearch. This page loads; most other Indian government sites timed out from our container.

**What it records:**
- Fire date and time (IST), source (VIIRS or MODIS), latitude and longitude.
- State, District, Circle, Division, Range, Block, Beat and **Compartment_No**.
- Coverage: 1 November 2025 to today (the form's minimum date is 2025-11-01; a March 2024 query returned no rows).

**How to get it (no login):**
- The ID lookups are open JSON endpoints:
  - `/Circles/GetCirclesByState?stateId=20` (MP = 20, Bhopal Circle = 90)
  - `/Divisions/GetDivisionsByCircle?circleId=90`: Bhopal 389, Raisen 391, **Obedullaganj 392**, Sehore 393, Rajgarh 373, Vidisha 385
  - `/Ranges/GetRangesByDivision?divisionId=392`: Bamhori, Bari, Barkhera, Bineka, Chiklod, Chilwaha, Dahod, Delawari, Goharganj, Sultanpur
  - `/Blocks/GetBlocksByRange?rangeId=…` and `/Beats/GetBeatsByBlock?blockId=…`
- CSV download: `https://fsiforestfire.gov.in/FirePointSearch/DownloadCsv?FromDate=2025-11-01&ToDate=2026-10-14&Source=Both&State=20&Circle=90&Division=392`

**What I found (Obedullaganj, 2025-26 season):**
- 1,722 rows, of which 1,114 are unique (date, time, lat, lon). Each point is repeated about 1.5 times.
- VIIRS 1,391 rows, MODIS 331.
- By month: Feb 175, **Mar 803, Apr 506**, May 95.
- Overpass hours: 12-15 h IST, plus 01-02 h at night.
- Busiest beats: Jawra (Dahod) 29, Khajuri (Delawari) 28, Kumhariya (Dahod) 27, South Sajoli (Bineka) 27, North and South Mathar (Delawari) 24 and 22.
- Raisen 1,195 rows (859 unique), Sehore 1,644 (994 unique), Bhopal 309 (206 unique). In Raisen, April (505) is busier than March (323).

**Concrete actions for us:**
- *Threads 1, 2, 5 (compartment key):*
  - Download all four divisions each season (and Dewas, Vidisha, Rajgarh for a regional view).
  - Spatially join FSI points to our 500 m cells. Each cell then inherits the beat name and compartment number FSI uses [inference: points near boundaries may map to two compartments].
  - Use that key for: (a) reporting predictions as "Beat X, Compartment Y", the unit DFOs act on; (b) merging any register Akkshay obtains (sections 6-7); (c) checking our 94-beat polygons against FSI's beat names.
- *Thread 1 (operational baseline):* FSI alerts are what officers already receive. Score our 2-day model against "FSI alerts in the same beat in the last 2 days" as a naive baseline. Our recall should beat it.
- *Thread 5:* duplicate rows (same time and point) show FSI sends the same alert to several admin units or sensors. Deduplicate before counting "alerts per beat".

## 2. FSI Large Forest Fire archive (FULL: portal and CSV)

Link: https://fsiforestfire.gov.in/LFF_Archival/Search. Export is a POST to `/LFF_Archival/DownloadCsv` with FromDate, ToDate, SelectedState and the anti-forgery token from the search page.

**What it records:**
- The definition: at least 3 contiguous SNPP-VIIRS pixels, about 40 ha or more, tracked across passes, with 3 days' wait for re-ignition (portal text).
- Fields: first and last detection (`YYYYMMDD_HHMM`), District, Circle, Division, Range, Fire name, an inside point, and a bounding box (min/max lon and lat).

**What I found (MP):**
- 7,536 events: 2019: 5, 2020: 566, 2021: 7, 2022: 2,074, 2023: 1,137, 2024: 960, 2025: 2,787. Coverage of 2019 and 2021 is clearly patchy.
- Obedullaganj 434, Raisen 321, Sehore 224, Bhopal 75.
- In a box of 22.7-23.35 °N, 77.2-78.3 °E [inference: roughly Ratapani plus margin]: 685 events.
  - Median duration 0 h (a single pass).
  - 167 events lasted more than 24 h; the longest was 337 h.
  - Bounding box median about 1.2 km², 90th percentile about 5.2 km².

**Concrete actions for us:**
- *Thread 2 (dating check):* for each LFF event inside Ratapani, check that a scar of ours overlaps its bounding box, and that our VIIRS-derived date falls between first and last detection. Expect agreement above 90%, because these are our own VIIRS pixels clustered. A failure points to a bug in our scar–alert matching.
- *Thread 4 (spread):* the 167 multi-day events give first/last times and boxes. That is a crude growth-rate check for the spread model (box size divided by duration).
- *Thread 1:* add a cell feature "an LFF event touched this cell in the last N years" [inference: small gain at best; it overlaps burn history].

## 3. FSI Archival fire points, 2004 to 30 June 2025 (FULL: queried)

Link: https://fsiforestfire.gov.in/ArchivalData/Search (POST with token). The result is a table and CSV with Date, Sensor, Lon, Lat, State, Year, ACQTIME. There are no admin tags.

**What it is:** FSI's forest-masked MODIS/VIIRS list, meaning only the points FSI treated as forest fires. A test query (MP, VIIRS, 1-5 March 2024) gave 118 records.

**Concrete action:**
- *Thread 2 / labels:* join with our `viirs_snpp_2013_2024.parquet`.
  - VIIRS points that FSI dropped are likely non-forest (agriculture or village edge).
  - Points FSI kept but where we found no scar are candidate missed scars.
  - Cheap to do. It tells us which of our scars came from points FSI itself calls non-forest [inference].

## 4. FSI feedback system and feedback statistics (FULL: FAQ PDF and live feedback abstract)

Links: https://fsiforestfire.gov.in/Home/NRT_Feedback · FAQ: https://fsiforestfire.gov.in/libraries/assets/documents/FAQ.pdf

**What it records:**
- Every SMS alert carries a feedback link. The user reports "Fire observed: yes/no", area burnt (ha) and remarks (FAQ Q25).
- Agricultural fires are still to be marked "yes" with a note (Q26).
- Points with repeated "industrial" or "revenue land" feedback are manually masked out (Q28).
- Feedback is "used to carry out analysis of types and causes".

**Live abstract (season 1 to 14 October 2026 only, the only window shown):** MP had 88 detections, 116 alerts generated and **14 feedbacks (12%)**. India had 501 alerts and 24 feedbacks. No archive of past feedback is public.

**Concrete action (needs Akkshay):**
- Email forestfiremonitoring@gmail.com (FSI, Forest Geo-informatics Division), or ask through the Ratapani DFO, for **all NRT feedback records for Obedullaganj, Raisen and Sehore divisions, 2017-2026**: alert ID, point, date, fire yes/no, area, remarks.
- Even a few hundred records would give: (a) a field-confirmed false-alarm rate for VIIRS in Ratapani; (b) field area per alert, to check our scar sizes; (c) cause remarks. Thread 2 (scar sizes) and thread 1 (label noise).
- Expect low coverage: around 12% of alerts get feedback, and the CAG found Uttarakhand "did not submit feedback" (section 9).

## 5. FSI technical reports 2023-24: burnt area, fuel load, risk zonation (PARTIAL: methods and MP chapters read)

Index: https://fsiforestfire.gov.in/Home/Publication. All three PDFs downloaded directly from `/libraries/assets/documents/`.

### 5a. Assessment of Forest Fire Burnt Area Report 2023-24 (FSI TIS Vol. 3 No. 1, 2026)

**Method:**
- Sentinel-2 pre/post-fire dNBR, guided by FSI VIIRS/MODIS detections from November 2023 to June 2024.
- Three severity classes. FSI's own "low" class is the largest and is defined as "only the forest floor is burnt". That is our fire type.

**Ground truth:**
- 674 burnt patches visited with state forest staff; 668 correct (99.1%).
- Separate accuracy assessment on 13,365 Landsat-OLI-interpreted points: overall accuracy 98.90%, kappa 0.98.
  - Low burnt: producer's accuracy 99.41%, user's accuracy 97.78%.
  - Moderate: producer's 86.39%, user's 94.29%.
  - Severe: 73.33% / 73.33%.

**MP numbers:**
- 15,878 SNPP-VIIRS detections and 1,592 MODIS.
- Burnt 3,172.13 km² (3.42% of RFA). Low 3,132.86, moderate 38.14, severe 1.13 km².
- Large-fire detections: 1,130 in 2022-23, 962 in 2023-24.

**District table (VIIRS detections 2022-23 → 2023-24; burnt km² in 2023-24):**

| District | Detections 2022-23 | Detections 2023-24 | Burnt km² (total) | Low | Moderate |
|---|---|---|---|---|---|
| Raisen | 1,352 | 1,696 | 261.12 | 259.85 | 1.27 |
| Sehore | 632 | 1,136 | 122.70 | 120.27 | 2.41 |
| Bhopal | 98 | 123 | 23.63 | 21.92 | 1.71 |
| Dewas | 981 | 1,265 | 261.93 | 249.27 | 12.66 |
| Vidisha | 320 | 394 | 80.72 | 79.82 | 0.90 |

- "Dewas followed by Raisen, Sheopur and Balaghat are the most fire-affected districts. Raisen district has reported the highest area under low burnt severity class."
- Area per VIIRS detection [inference]: Raisen 15.4 ha, Sehore 10.8 ha, Bhopal 19.2 ha.

**Concrete actions:**
- *Thread 2 (label check):* sum our 2023-24 scar area inside the Raisen and Sehore district parts of Ratapani. Compare area per VIIRS detection with FSI's 15.4 and 10.8 ha.
  - If ours is much smaller (say under 5 ha per detection), our scar growth is too conservative.
  - If it is much larger, we are labelling leaf fall.
- *Thread 2:* ask FSI for the **2023-24 burnt-area polygons** for Raisen and Sehore. They are rendered on the Van Agni geoportal, https://vanagniportal.fsiforestfire.gov.in, which was unreachable from here. A polygon-to-polygon comparison would be the best independent check of our 2024 labels. The ask goes to FSI FGD.

### 5b. Surface Fuel Load Mapping 2023-24 (FSI TIS Vol. 3 No. 2)

**Method:**
- Field samples of surface fuel, oven-dried for 3 h at about 50 °C, plus NFI data.
- 272 strata (17 forest types × 4 density classes × 4 slope classes). Each stratum gets its field mean.
- Fuel moisture map interpolated (IDW) from 516 sample locations.
- Classes: Low below 20 g/ft² (below 2.15 t/ha) [inference: 1 g/ft² = 0.1076 t/ha]; Moderate 20-40 g/ft² (2.15-4.3 t/ha); High 40-60; Very High above 60.

**Results:**
- MP RFA: 61.97% low, 12.54% moderate, 0.47% high.
- Raisen RFA: 2,480.84 km² low, 64.18 km² moderate.
- Sehore: 1,153.45 km² low, 42.66 km² moderate.
- Bhopal: 253.57 km² low, 1.54 km² moderate.

**Concrete action, thread 3:**
- FSI's map puts almost all of Ratapani below 2.15 t/ha. That sits at the low end of the published central-Indian litter loads in `fuel_load_values*.md` [inference: FSI probably sampled after leaf fall or after fire].
- Ask FSI for the **raw field fuel samples (location, date, dry weight) in MP**. These are free ground-truth points for the fuel map.

### 5c. Forest Fire Risk Zonation of India 2023-24 (FSI TIS Vol. 3 No. 3)

**Method:**
- Log-linear models on **NFI plot-level field variables, with "forest fire incidence" recorded in the plot as the dependent variable**.
- Layers: forest type, altitude, aspect, slope (30 m ASTER DEM), grazing incidence (IDW), soil, and biotic influence (roads and habitation). Weights come from archived detections and ground truth.

**Results:**
- Raisen RFA: very high risk 38.65 km², high 949.01, moderate 1,401.75, low 170.60.
- Sehore RFA: 15.62 / 511.47 / 601.37 / 77.16.

**Concrete actions:**
- *Thread 1:* ask FSI for **NFI plot records of fire evidence in Raisen and Sehore** (plot location, survey date, fire present/absent, grazing). These are independent field observations of burning, made without satellites. A few dozen plots could test whether our burn-frequency labels agree with field evidence [inference: plot locations are normally confidential, so request through the DFO].
- *Thread 1:* use the FSI risk class as a benchmark. Our model should beat the FSI static risk class at ranking cells.

## 6. CAG Report No. 1 of 2022, MP: Performance Audit on Wildlife Conservation and Habitats (PARTIAL: section 4.6 and the plan tables read)

PDF (direct, via the CAG CDN): https://d7i5wg8xwe4hf.cloudfront.net/uploads/download_audit_report/2022/Report%20No.%201%20of%202022_Wildlife_English_GoMP-063285595a90d71.70599081.pdf. The audit covers 2014-15 to 2018-19, and Ratapani and Singhori (Obedullaganj) were among the audited units.

**Fire findings:**
- "An area of **8,636 ha** of forest was affected by fire in **1,737 cases**, during 2014-18 in 12 out of the 13 audited Divisions." That is 5.0 ha per recorded case [inference].
- 1,15,189 km of fire-lines were cleaned or burnt over 2014-19.
- **"Madhav National Park, Nauradehi Wildlife Sanctuary and Obedullaganj Division did not prepare Fire Plans."**
- 12 of 13 divisions used only fire-beaters.
- In Nauradehi only 30% of fire-watcher wages were spent in 2018-19, the year it had its highest burnt area (394.50 ha).

**Plan status:**
- **Ratapani WLS Management Plan: 2008-09 to 2017-18; "No Management Plan for one year (2018-19) after expiry."**
- Research areas, budget needs and patrolling plans had not been identified for Ratapani.
- Earlier research titles at Ratapani include "Ecological Status of Ratapani WLS" and Delawari Range studies.

**Concrete actions (needs Akkshay):**
- Request the **Ratapani WLS Management Plan 2008-18** and any successor or the TCP. Indian management plans normally carry a fire chapter with fire-prone compartments, fire-line maps, past fire records by compartment and year, and causes [inference, from the standard MP/NTCA plan format]. Uses:
  - Thread 1: a compartment-level fire history covering 2008-17, before our labels start. This is a direct check of our "interior cells burn about 2× more" result.
  - Thread 5: the list of fire-prone compartments.
- The 5 ha per recorded case gives a sanity check on recorded sizes (section 10).

## 7. MP SFRI Jabalpur Annual Research Report 2024-25 (PARTIAL: director's note, fire projects and wildlife projects read)

Link: https://www.mpsfri.org/files/ARR_2024-25.pdf (downloaded directly).

- Director's note: "In the year 2022-23, 17142 fire incidents and in the year 2023-24, 15878 fire incidents occurred… approximately 37% of state's forest cover remains vulnerable." As noted above, 15,878 equals FSI's SNPP-VIIRS count for MP in 2023-24, so these are satellite detections.
- New projects funded by PCCF (Protection):
  - **"Developing A New Danger Rating System"** (Rs 3.43 lakh). Its outputs include a localised FFDRS and a "division-wise map… on forest fire prone area"; no activities yet.
  - "Criteria for laying fire lines and their effective width".
  - "Assessment of impact of fire on vegetation, invasive plants and forest fauna of MP".
  - A Hindi-titled study on the role of JFMCs in forest fire management.
- Wildlife division: SFRI analysed herbivore and carnivore data "sent to Sehore, Raisen, Obedullahganj Forest Divisions… **by preparation of Tiger Conservation Plan for proposed Ratapani Tiger Reserve**". So the TCP drafting draws on SFRI data.
- Also: the Ratapani-Kheoni tiger studies (7,210 km²; a tiger sign survey over 5,312 km² from December 2018 to April 2019, with beat-wise data on 10 km² grids).

**Concrete actions:**
- *Thread 1/5 (collaboration):* SFRI is building an MP fire danger rating system and division-wise fire-prone maps with PCCF (Protection) money and has done no work yet. Our Ratapani model and data could be offered to them. The contact is through PCCF Protection or the SFRI Director.
- Ask SFRI whether the Ratapani TCP draft has a fire chapter (needs Akkshay).

## 8. Uttarakhand CAG audits (FULL: 2017 paragraph 1.7; FULL: 2022 overview)

### 8a. CAG Uttarakhand Report No. 1 of 2017, paragraph 1.7 "Prevention of forest fires"

Chapter 1 PDF: https://d7i5wg8xwe4hf.cloudfront.net/uploads/download_audit_report/2017/Chapter_1_Social_General_and_Economic_Sectors_Non_PSUs_Uttarakhand_Report_No_1_of_2017.pdf

**State recorded incidents and area (source: Uttarakhand Forest Statistics):**

| Year | Incidents | Area (ha) |
|---|---|---|
| 2013 | 245 | 384.05 |
| 2014 | 515 | 930.33 |
| 2015 | 412 | 701.61 |
| 2016 | 2,074 | 4,433.75 |

That is about 1.6-2.1 ha per recorded incident.

**Recording failures (Table 1.7.4 and text):**
- CCF and divisional figures for 2016 disagree by 14 incidents and 38.2 ha.
- **71 of 73 incidents in Rudraprayag were missing from the Master Control Room register.**
- In Bageshwar and Almora, fires were "recorded on the succeeding date and in some cases after three to four days".
- In Uttarkashi, 14 of 15 (2015) and 71 (2016) incidents were missing from the register.
- Response times could not be measured because registers did not record when a report was received.

### 8b. CAG Uttarakhand 2022, "Subject Specific Compliance Audit on Effective Use of RS/GIS in Forest Fire Management" (paragraph 2.2.10)

Overview PDF: https://d7i5wg8xwe4hf.cloudfront.net/uploads/download_audit_report/2022/4-Overview-06421358cb164f6.97717371.pdf

Findings:
- The fire risk zonation was not used to allocate resources.
- "The Department did not submit feedback to FSI."
- Feedback in the departmental Forest Fire Report Management System had "serious inaccuracies… doubt whether ground truthing of alerts was actually being done".
- "Massive under reporting of burnt area" compared with independent expert data.
- Burnt area was assessed manually despite a 2015 agreement with NRSC.
- The full paragraph was not located.

**Concrete actions:**
- *Thread 2 (how to use registers):* treat any register from Obedullaganj as **presence/compartment/cause data with ±3-day date error and area undercounted by an order of magnitude**. In a merge, match register fires to our scars with a date window of at least −1 to +4 days, and never use register area as a label.
- *Thread 5:* the field app should timestamp reports automatically. This is the specific failure the CAG documented.

## 9. Recorded vs mapped area: how far apart (assembled from several sources) [inference throughout]

**Recorded MP totals:**
- 2007-08: 21,869 ha in 4,067 fires (Deccan Herald 2009, citing the MP Forest Department; SNIPPET). 5.4 ha per fire. Kanha TR had the most fires (125).
- 2014-2017: 95, 12, 118 and 1,033 incidents (MP FD website via Hitavada 2019; FULL article). 2017: 13,809 ha. Bhopal Circle: 1,264 incidents from January 2014 to 2017.
- 2008-2012: 1.57 lakh ha in total (PCCF forest-offence reports, via CAG Economic Sector report 2013 and Business Standard; SNIPPET).

**FSI mapped MP 2023-24:** 317,213 ha. Recorded state totals are therefore about 15-25 times smaller [years differ].

**Uttarakhand:** the 2023-24 season was recorded as about 1,145-1,316 ha in 910-998 incidents up to May 2024 (Sitrep and PTI; SNIPPET). FSI mapped 1,808.90 km² = 180,890 ha, a factor of about 140.

**Maharashtra:** 2023 recorded 12,921.6 ha in 5,274 incidents. The 2019-23 total was 37,403 incidents and 1,28,315 ha (RTI via Hitavada 2024; FULL article). FSI 2023-24 mapped 409,504 ha.

**Melghat, Sipna division:** 221 cases and 2,221 ha before an incentive scheme, 35 cases and 168 ha after (Hitavada 2020; SNIPPET). About 10 and 4.8 ha per case.

**Concrete action, thread 2:** the size distribution of our Ratapani scars should sit **well above** recorded per-incident sizes (2-5 ha) and **near** FSI's area per detection (11-15 ha in Raisen and Sehore). If our median scar is around 25 ha (one cell), we are consistent with FSI. Registers cannot be used to say we over-label.

## 10. Parliament answers (SNIPPET: eparlib, sansad and rsdebate were unreachable from here)

- Lok Sabha AU1861 (21 December 2018): MP fire counts 294 (2015), 2,675 (2016), 4,781 (2017). The question asks about the "top 20 districts in Central India", but the district list was not seen.
- Lok Sabha AU1863 (30 July 2021): November 2020 to June 2021, 3,45,989 alerts nationally. Odisha 51,968, **MP 47,795**, Chhattisgarh 38,106.
- Rajya Sabha PQ 266 U1156 (5 December 2024), PQ 267 U1640 (13 March 2025) and PQ 265 Q1934 (8 August 2024; also data.gov.in "State/UT-wise Number of Forest Fires Detected by FSI using SNPP-VIIRS 2019-20 to 2023-24"): all are **FSI SNPP-VIIRS state counts**.
- Parliamentary Standing Committee (PRS summary, 7 August 2026; FULL page): "only about **12.5%** of FSI alerts in Uttarakhand matched actual fires". This is the same figure as in `field_alert_systems_fullread.md` §1. Also: chir pine areas account for about 57% of western-Himalayan incidents.

**Use:** almost none for validation, because these are satellite counts. The one possible exception is the top-20-districts list in the 2018 answer. Akkshay could fetch it from https://eparlib.nic.in/bitstream/123456789/802357/1/AU1861.pdf from an Indian connection.

## 11. data.gov.in and Dataful (SNIPPET / page summary)

- data.gov.in: "Forest Fire Incidences across all the States of India 2008 to 2011" (from ISFR 2011, MODIS-based), and the SNPP-VIIRS state series 2018-19 to 2023-24. All are state level and satellite derived.
- Dataful collection 916 (MoEFCC): 8 tables, including "Season- and State-wise Number of Forest Fires in Tiger Reserves 2019-2024", large fires by duration, and burnt extent 2023-24. All are marked "Exclusive" (paid). Ratapani was only notified as a tiger reserve in December 2024, so it is not in the TR table [inference].
- **Use:** low. State-level satellite counts only.

## 12. Uttarakhand daily bulletins (SNIPPET: forest.uk.gov.in was unreachable)

**What they record:** daily and cumulative incidents and ha, split Garhwal / Kumaon / wildlife areas and Reserve / Civil-Soyam. The season runs 15 February to 15 June.

**Examples:**
- April 2026: 162 incidents, 154.62 ha (0.95 ha per incident).
- 2026 to date: 394 incidents, 331.12 ha.
- 2024: 24 incidents and 23.75 ha in one day; 998 incidents and 1,316 ha since 1 November.

**Use:** none directly for Ratapani. It is a template for what an MP daily bulletin could hold (thread 5).

## 13. Odisha District Forest Fire Action Plans (PARTIAL: Rayagada DFAP 2026 read)

Link: https://odishaforest.in/admin/data/ckeditor/images/170220262524066526_Rayagada_dist.,.pdf (168 pages, public).

**What it records:**
- Five years of FSI fire points (2021-25) split **inside forest block vs non-forest**. The non-forest share is 19-30% per year and over 33% in 2025.
- **Beat-wise tables of incidents, fire months, risk class and "main cause"**, with beat-level actions.
- Fire-line km per year: 660 → 855 → 1,200.
- Over 80% of incidents fall in March-April.
- Causes: mahua collection, podu cultivation, grazing, crop-residue burning, intentional fires, poaching.
- 42% vacancy in frontline staff.

OFMS season data is covered in `field_alert_systems_fullread.md` §2 and not repeated here.

**Concrete actions:**
- *Thread 5:* the DFAP beat table (beat, incidents, peak month, risk, main cause, action) is the format to produce for Ratapani from our model.
- Ask whether MP divisions make an equivalent "Agni Suraksha Yojana". The CAG says Obedullaganj did not, in 2014-19.
- *Thread 2:* Odisha's 19-33% of FSI points falling outside forest blocks is a useful prior for how many VIIRS points near Ratapani's fringe are not forest fires [inference].

## 14. MEE reports and tiger-reserve plans (PARTIAL)

- MEE of Tiger Reserves 2010-11 (https://mee-tr.wii.gov.in/meenu_files/MEE_TigerMEETR2010.pdf): Ratapani appears only as a *proposed* reserve.
- MEE of National Parks and Sanctuaries 2018-19 (PIB PDF, 13,914 lines searched): **Ratapani is not evaluated.** Singhori WLS (Obedullaganj, 288 km², score 56.03% "Fair") is evaluated: 22 villages inside, 195 on the periphery, felling is the main threat, fire is not discussed in detail.
- Ratapani was notified as MP's 8th tiger reserve on 2 December 2024: 1,271.465 km², about 763 km² core and 507 km² buffer. I found no approved TCP online. A 2015 NGT note lists a "TCP of Raisen, Sehore, Obaidullaganj and Bhopal areas" as pending. The next NTCA MEE cycle should include Ratapani [inference].
- KBA/BirdLife factsheet: "forest fires, natural and man-made, are a major problem in summer". The sanctuary is about 70 × 15 km.

**Use:** none yet. Watch for the first MEE of Ratapani TR and its TCP (needs Akkshay).

## 15. Research datasets with field-mapped fire records in India (SNIPPET/ABSTRACT)

- **Kodandapani, Cochrane & Sukumar 2004** (Conservation Biology): ground maps of *every* fire in Mudumalai WLS, 1989-2002, from forest-department records combined with imagery. Fire return interval 2.7 years for the sanctuary, under 7 years in all forest types. Kodandapani's 2006 thesis compares this with a 1910s dataset and finds about a three-fold rise. This shows that south Indian forest departments kept compartment-level fire maps; MP's management plans probably did the same [inference].
- **Melghat TR fire frequency 2014-2020** (J. Tropical Forestry & Environment; ABSTRACT): Landsat scars, January-June. 35% never burnt; 0.52% (1,053.64 ha) burnt all 7 years; 1.49% burnt 6 times; about 34% burnt once. The authors used this to propose 27 new watchtowers.
- **Kalaranjini et al. 2020** (InGARSS, doi 10.1109/InGARSS48198.2020.9358979), cited by Chandel et al. 2022: "MODIS and VIIRS based products are only able to identify **5.64%** of fire incidents" in Uttarakhand. The ground source is unknown and the original was not read.
- **Chandel et al. 2022** (FFGC 5:933807): checked here only for its reference data. It used visually interpreted Landsat points (700 per scene × 9 scenes), with **no field GPS** (already covered in `alert_burn_scars_fullread.md` §5).
- **NRSC DMSP fire reports**, e.g. the Sariska 2022 brief (https://www.nrsc.gov.in/sites/default/files/pdf/DMSP/sariska_2022fires_brief_report.pdf, not read): event reports with field-verified burnt-area photos. None found for MP.
- **I found no public dataset of GPS-walked fire perimeters for any Indian dry deciduous forest.** The nearest are FSI's 674 verified patches (not published as data) and Odisha/Uttarakhand registers.

## 16. News databases (SNIPPET)

- theanalysis.org.in, "Compilation of fire incident news in MP 2024": a Google Drive file of clippings. The page does not separate forest from urban fires, and Ratapani does not appear in the page text.
- Searches in English and Hindi ("रातापानी… आग") found **no news report of a specific Ratapani fire with area**. Ratapani fires are small and do not make news [inference].
- **Use:** none for labels.

---

## What Akkshay needs to request (none of this is online)

| Item | From whom | Route | What we get | Thread |
|---|---|---|---|---|
| Fire register / daily fire reports (date, compartment, beat, area, cause, report time), 2017-2026 | DFO Obedullaganj (now Ratapani TR Field Director / Deputy Director), DFO Raisen, DFO Sehore | Letter, or RTI (PIO at each DFO office) | Compartment-level presence and cause; date ±3 days | 1, 2 |
| Ratapani WLS Management Plan 2008-09 to 2017-18, and the draft TCP (2024-26) | Field Director Ratapani TR; PCCF Wildlife Bhopal; SFRI Jabalpur | Letter or RTI | Fire chapter, fire-prone compartments, fire-line map, historic fire table | 1, 5 |
| Obedullaganj / Raisen / Sehore working plans, fire-protection chapter | Working Plan Officer, Bhopal circle | Letter | Compartment fire history, fire-line network | 1, 4 |
| Compartment and beat shapefile | DFO / MP FD IT cell (mpforest.gov.in atlas) | Letter | Exact compartment polygons to replace the point-derived key | all |
| FSI NRT feedback records for the three divisions, 2017-2026 | FSI FGD, forestfiremonitoring@gmail.com | Email, with the DFO's support | Field "fire yes/no", ha, remarks per alert | 2 |
| FSI 2023-24 burnt-area polygons, and the field fuel samples, for Raisen/Sehore | FSI FGD | Email | Independent scar polygons; fuel ground truth | 2, 3 |
| NFI plot fire-evidence records, Raisen/Sehore | FSI (NFI division) | Formal request | Field fire presence per plot | 1 |
| MP FD division-wise annual fire incidents and ha (the website series quoted for 2014-17) | PCCF (Protection) Bhopal | RTI | Year × division baseline | 1 |
| Lok Sabha AU1861 (2018) district annexure | eparlib.nic.in | Open from an Indian IP | Top-20 central-India districts | low |

## Datasets table

| Name | Link | Resolution / unit | Years | Licence | Access |
|---|---|---|---|---|---|
| FSI Fire Point Search (beat + compartment tagged) | fsiforestfire.gov.in/FirePointSearch | Point; admin tags down to Beat and Compartment_No | 1 Nov 2025 onward | Government of India public portal, no licence stated | Free CSV: `/FirePointSearch/DownloadCsv?…&State=20&Circle=90&Division=392` |
| FSI Large Forest Fire archive | fsiforestfire.gov.in/LFF_Archival/Search | Event (≥3 VIIRS px, ≥~40 ha) with first/last time and bbox | 2019-2025 (patchy 2019, 2021) | as above | Free CSV (POST with token) |
| FSI archival fire points (forest-masked) | fsiforestfire.gov.in/ArchivalData/Search | Point, no admin tags | Dec 2004 to Jun 2025 | as above | Free table/CSV (POST with token) |
| FSI NRT feedback abstract | fsiforestfire.gov.in/Home/NRT_Feedback | State counts | Current season only | as above | Free view; history on request |
| FSI Burnt Area Report 2023-24 | fsiforestfire.gov.in/libraries/assets/documents/Forest%20Fire%20Burnt%20Area%20Mapping.pdf | District tables; S2 dNBR maps | Nov 2023 to Jun 2024 | © FSI | Free PDF; polygons on request |
| FSI Surface Fuel Load Mapping 2023-24 | …/Surface%20Fuel%20Load%20Mapping.pdf | District × 4 classes; 272 strata | 2023-24 | © FSI | Free PDF; samples on request |
| FSI Forest Fire Risk Zonation 2023-24 | …/Forest%20Fire%20Risk%20Zone%20Mapping.pdf | District × 4 classes | 2023-24 | © FSI | Free PDF |
| CAG MP Report 1 of 2022 (wildlife) | d7i5wg8xwe4hf.cloudfront.net/…/Report%20No.%201%20of%202022_Wildlife_English_GoMP-….pdf | Audited divisions | 2014-19 | Public report | Free PDF |
| CAG Uttarakhand 2017 Ch. 1 and 2022 overview | d7i5wg8xwe4hf.cloudfront.net/uploads/download_audit_report/… | Division | 2013-16; about 2017-21 | Public | Free PDF |
| MP SFRI ARR 2024-25 | mpsfri.org/files/ARR_2024-25.pdf | Project list | 2024-25 | Public | Free PDF |
| Odisha District Forest Fire Action Plans | odishaforest.in (e.g. Rayagada DFAP 2026) | Beat tables | 2021-2025 | Public | Free PDF |
| Ratapani WLS Management Plan 2008-18 / TCP | not online | Compartment | 2008-2018 / draft | Government | Request (letter or RTI) |
| Division fire registers | not online | Compartment, date, ha, cause | n/a | Government | Request (letter or RTI) |

## Ranked action list (gain vs effort) [gains are my estimates]

1. **Build the cell → beat → compartment key from FSI Fire Point Search CSVs** (all four divisions, 2025-26). Spatially join to our 500 m grid, and report predictions and alerts by FSI beat and compartment name.
   - Gain: high for threads 1, 5 and every later register merge. It makes the output speak the DFOs' language.
   - Effort: about 0.5 day; the script calls are above. Re-pull each season.
2. **Check our 2023-24 labels against FSI's district burnt area.** Compare area per VIIRS detection: FSI has Raisen 15.4 ha and Sehore 10.8 ha. Compare also our low-severity share.
   - Gain: medium-high. It is the only field-checked independent check available today (668 of 674 patches correct).
   - Effort: about 2 h.
3. **Check scar–alert matching on FSI LFF events** (685 near Ratapani): overlap with the bounding box, and our date between first and last detection.
   - Gain: medium (catches dating bugs; thread 2), plus growth-rate data for thread 4.
   - Effort: about 2 h.
4. **Send the request package** (table above), led by the Ratapani TR Field Director: register, management plan 2008-18, draft TCP, compartment shapefile, FSI feedback.
   - Gain: potentially the highest of all (compartment fire history to 2008, causes, a true field false-alarm rate).
   - Effort: low for us; slow (weeks to months) and uncertain for Akkshay.
5. **Join FSI's forest-masked archival points (2013-2025) with our VIIRS parquet.** Flag scars that came only from points FSI dropped as non-forest; review or down-weight them in training.
   - Gain: medium for label noise at the fringe. Odisha shows 19-33% of points outside forest blocks.
   - Effort: about 0.5 day; the pull is per date range and needs a token.
6. **When registers arrive, merge them with a date window of −1 to +4 days and use them for presence and cause only, never for area.**
   - Gain: medium.
   - Effort: depends on format (likely scanned Hindi tables).
7. **Ask FSI for its 2023-24 burnt-area polygons and field fuel samples** for Raisen and Sehore.
   - Gain: medium (polygon-level check for thread 2; field fuel for thread 3).
   - Effort: low for us; FSI's response is uncertain.
8. **Offer the model to SFRI's new MP fire-danger-rating project** (PCCF Protection funded; no work done yet).
   - Gain: adoption and a route into division records.
   - Effort: one letter.
9. **Use FSI's 2023-24 risk zonation and alerts as baselines.** The 2-day model should beat "FSI alert in the beat in the last 2 days" and the FSI static risk class.
   - Gain: low-medium (it makes a credible case to officers).
   - Effort: about 2 h.
10. Low value: Parliament answers, data.gov.in and Dataful tables, news clippings. All are state-level satellite counts or lack location.

## Reading tally

- FULL (whole document or whole relevant section): 9.
  - FSI portal pages, APIs and CSV exports (Fire Point Search, LFF archive, archival points, feedback abstract)
  - FSI FAQ
  - CAG Uttarakhand 2017 paragraph 1.7
  - CAG Uttarakhand 2022 overview
  - PRS committee summary
  - Hitavada 2019 (MP) and Hitavada 2024 (Maharashtra RTI)
  - Chandel 2022 reference check
  - MEE 2018-19 (text-searched in full)
- PARTIAL: 6.
  - FSI Burnt Area 2023-24
  - FSI Fuel Load 2023-24
  - FSI Risk Zonation 2023-24
  - CAG MP 2022
  - SFRI ARR 2024-25
  - Odisha Rayagada DFAP 2026
- SNIPPET/ABSTRACT: about 15. These are the Parliament answers, the Uttarakhand bulletins, the Melghat paper, Kodandapani, Kalaranjini, Dataful, the Deccan Herald 2009 piece and Business Standard 2014.
- Not reachable from the container: mpforest.gov.in, eparlib/sansad PDFs, forest.uk.gov.in, the HP FIRE portal (forestfire.hp.gov.in, which has daily division reports), the Van Agni geoportal, data.gov.in and the Wayback Machine.
