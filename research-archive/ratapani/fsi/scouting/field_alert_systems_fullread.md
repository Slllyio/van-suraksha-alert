# Field alert systems: full read (October 2026)

This note goes deeper on `field_alert_systems.md`. For each source I record how much I actually read, the exact rules, fields and numbers worth copying, and one concrete action for us. It serves two threads. The first is the "Live fire alerts and field checks" thread (`/mnt/project-files/field-system/`). The second is the prediction threads, where field outcomes could become label corrections.

Read status key:
- **FULL**: the whole document or page.
- **PARTIAL**: the main text without its figures or forms, or a summary of the full text.
- **ABSTRACT**: the abstract only, because the full text was paywalled or blocked.

Lines marked **(inferred)** are my reading, not something the source says.

---

## 1. Uttarakhand's ground check of FSI alerts, winter 2025–26 (the source chain)

**Read:** FULL for three news articles. There are two ETV Bharat pieces and one in Garhwal Post. The PCCF letter itself is not online.
- 30 Jan 2026 tally: https://www.etvbharat.com/en/state/uttarakhand-forest-department-claims-that-most-of-fsi-forest-fire-alert-false-enn26013007036
- 2 Jan 2026 article on the letter: https://www.etvbharat.com/en/bharat/uttarakhand-forest-department-sent-letter-of-complaint-raising-objections-to-fsi-data-on-forest-fires-enn26010202147
- https://garhwalpost.in/every-heat-alert-by-fsi-not-a-forest-fire-indicator-subodh-uniyal/

**Source document:** a letter dated **31 Dec 2025** from the office of the Uttarakhand PCCF (Ranjan Kumar Mishra) to the **Director-General of FSI**. It asked FSI to:
1. Rename "Forest Fire Alerts" as **"Heat Alerts"** on the FSI website.
2. Publish **ground-verified data every month**.

The letter is not public. The figures below come from the department's statements to the press, which were made by CCF Fire Sushant Patnaik and Minister Subodh Uniyal.

**There are two snapshots. Each is a complete outcome table that sums exactly.**

| Outcome | 1 Nov–28 Dec 2025 (alerts checked in the field) | 1 Nov 2025–20 Jan 2026 (all alerts) | Difference, 29 Dec–20 Jan (derived) |
|---|---|---|---|
| Real forest fire | 64 (6.1%) | 132 (6.8%) | 68 (7.5%) |
| Completely false (no heat source found) | 377 (35.9%) | ~766 (39.2%) | 389 (43.1%) |
| Outside forest (farm or crop-residue burning, habitation, garbage dump) | 479 (45.6%) | 754 (38.6%) | 275 (30.5%) |
| Department's own controlled burn or fire-line work | 130 (12.4%) | ~300 (15.4%) | 170 (18.8%) |
| **Total** | **1,050** (out of ~1,900 alerts received) | **1,952** | 902 |

- The 1,050 checked alerts by region (as of 28 Dec) were: **Garhwal 55 real of 721 (7.6%), Kumaon 2 of 230 (0.9%), wildlife areas 7 of 99 (7.1%)**.
- By region, all 1,952 alerts split as: Garhwal ~1,200, Kumaon 498, wildlife areas 254. No per-region outcomes were given for this total.
- The 132 confirmed fires burnt **18.84 ha** in total. That is **0.14 ha per fire**, so they were tiny.
- The department also quoted a **2024 figure** (season not stated): 9% real fires, 52% false, ~5% fire drills, 4% controlled burns. The remaining ~30% is presumably outside forest, though the source doesn't say so.
- The minister's "6–7%" refers to 132 / 1,952 = 6.76%.
- There is **no month-by-month or land-type breakdown**, and nothing on how the checks were done.

**Correction to the existing note:** all its numbers are right, and the four classes sum to exactly 1,952. Add the 28 Dec snapshot, the 31 Dec letter and the 18.84 ha figure.

**Concrete action for us** (field thread, and a label prior for the prediction threads):
1. Use these four classes as our closed outcome list: `fire_in_forest`, `no_fire_found`, `fire_outside_forest`, `controlled_burn`. Add `burnt_fire_out` (Schroeder's point) and `could_not_reach`.
2. Make the weekly export the same shape as this table (rows = outcomes, columns = period), so it can go straight into a letter to FSI.
3. For the prediction threads, treat the two winter snapshots as the **prior on how often an off-season VIIRS/MODIS point in a forest polygon is a real forest fire: about 6–8%**. In practice, do not use November–January FSI points as positive fire labels unless a burn scar confirms them.
4. Expect a higher share in the March–May peak (the 2024 figure was 9% real). The only real number for Ratapani will be our own.

---

## 2. Odisha OFMS season report 2026 and how OFMS works

**Read:** FULL for the 7-page OFMS report PDF (https://odishaforest.in/admin/data/ckeditor/images/300620262723599780_Firepointsummary_report_1782820992.pdf). NRSC deck: search snippet only, because the PDF still returns 404.

**Report layout. These are the exact column headers, worth copying:**

`Circle | Division | FSI Fire Points | Inside FB | Inside FB Responded (%) | Outside FB | Outside FB Responded (%) | Total Area Affected as Responded (In Ha) | Total Large Firepoint | Total Large Firepoint Responded (%) | Total Responded (%)`

Here FB means forest block. Rows are sorted by FSI fire points, descending.

**State total, 1 Jan–30 Jun 2026:**

| Measure | Value |
|---|---|
| FSI fire points | 20,841 |
| Inside forest blocks | 20,037, of which 20,033 responded (99.98%) |
| Outside forest blocks | 804, of which 802 responded (99.75%) |
| Large fire points | 2,885, all responded (100%) |
| All points responded | 20,835 (99.97%) |
| Total area affected (ha) | **3,056.16** |

The existing note left out the area total. Average burnt area per point is 3,056 / 20,841 = **0.15 ha**, about the same as Uttarakhand's 0.14 ha per confirmed fire.

**Division spread.** The top divisions by points were:

| Division | Points | Area affected (ha) | Large fire points |
|---|---|---|---|
| Balliguda | 2,349 | 26.39 | 209 |
| Rayagada | 1,576 | 124.04 | 214 |
| Nabarangpur | 1,295 | 249.54 | 294 |
| Kalahandi North | 1,209 | **799.12** | 63 |

Outside-forest share ranges from ~1% to **32%** (Bamra WL: 96 of 298). The report has **no outcome split**, which confirms the existing note. "Area affected" is the only field-measured number in it.

**System rules:**
- FSI alerts arrive by API and are routed by geoprocessing to the beat guard's phone. About 8,000 phones are registered.
- Navigation works offline. Staff upload geotagged photos and the action taken.
- **The point is marked "attended" once the phone is within 200 m of the FSI point.** This rests on one source only: the NRSC deck, via search snippet.
- A search snippet gives the 2025 season as **29,694 of 29,709 responded**. That works out to 99.95%; the note says 99.94%. The difference is rounding, so I left it.

**Concrete action for us** (field thread):
1. Copy the 11-column layout for the range-level weekly sheet, but split "Responded" into our outcome classes.
2. Add a column for **median burnt area per confirmed fire**.
3. **(inferred)** Both Indian states put the median confirmed fire at 0.1–0.2 ha. That is far below Sentinel-2's practical burn-scar floor (about 0.5–1 ha), so most field-confirmed fires will have no scar. The prediction threads should not treat a missing scar as proof of a false alert.

---

## 3. FSI FAST 3.0 Technical Information Series Vol. I No. 2 (2019): the official rules

**Read:** FULL, 20 pages (https://fsiforestfire.gov.in/libraries/assets/documents/technical-information-series-v1-n2.pdf). Note that `fsiforestfire.gov.in/document/faq.pdf` now returns 404.

**This is new: the existing note didn't cover it.** Exact rules:

**Forest filter.** NRSC sends all thermal anomalies. FSI keeps a point if it falls inside **Recorded Forest Area boundaries plus forest cover**. It then adds State, District, Division, Range, **Beat** and Compartment.

**Custom mask** (industry, mining, volcanoes, solar panels):
- Areas are digitised by hand from Google Earth.
- They are found from **consecutive VIIRS detections at the same place** and from the **fire-point feedback reports**.
- A **500 m buffer** is added around each masked area.
- Findings: industrial fires appear "in a clump", and **solar panels** also trigger detections.

**Large fire** (Large Forest Fire Monitoring Programme):
- A large fire is a clump of **at least 3 SNPP forest-fire polygons in close proximity**.
- Detections in later passes within "a pre-defined vicinity" continue under the same name, which is based on the range or district.
- A large fire is tracked **until it dies out, plus 3 more days**.
- The vicinity distance is not published.

**Edge-of-beat rule.** The point stands for the centre of the 375 m pixel. If that pixel straddles a range or beat boundary, the alert goes to **every adjacent beat**.

**Feedback fields** (the "feedback tree", whose figure is not machine-readable):
- whether the fire actually occurred
- area burnt (ha)
- **Type of Land**
- **Type of Fire**
- **Cause of Fire**
- **Fire Details**
- free remarks

Feedback is sent through the SMS link or the nodal officer login.

**Other figures:**
- Latency from detection to user is **1–1.5 h**.
- Only **6 overpasses a day** are used.
- The WMS layer shows the last **3 days in 3 colours**. This is the source of Maharashtra's colour-by-age map.
- FSI's own guidance: "use … for strategic purposes and not … for tactical firefighting purposes fully."

**Concrete action for us** (field thread):
1. Name our export fields `fire_occurred` (Y/N), `area_burnt_ha`, `type_of_land`, `type_of_fire`, `cause_of_fire` and `fire_details`, so a row can be pasted into FSI feedback.
2. Run our own large-fire flag the same way: **3 or more VIIRS points within one connected cluster** (use 750 m, which is 2 pixels, as our stated vicinity, since FSI publishes none). Keep it open until 3 fire-free days have passed. Large fires get their own line in the report.
3. Send boundary-straddling alerts to both beats, and record which guard closed the alert.
4. Build our own mask the FSI way: points detected on **3 or more days in a dry-season month** at the same 375 m pixel, plus a 500 m buffer, reviewed by hand. See items 5 and 6 for numeric rules.

---

## 4. Sweden: Dybbroe et al. 2026, J. Pyrogeography, plus the SMHI 2021 and 2022 slides

**Read:**
- Paper: **ABSTRACT** (DOI 10.1016/j.pyro.2026.100004). The licence is CC BY-NC-ND (gold OA), but ScienceDirect, the Elsevier API and DiVA all refused this container.
- SMHI/MSB slides from 2021 (EUMETSAT workshop) and 2022 (Lisbon): **FULL**.

**Numbers in the paper's abstract.** The existing note's figures are right.
- Average end-to-end latency, from overpass to alert, is **17 min**.
- **Verified false alarms were about 10% of detections since 2022.** Most came from solar-panel arrays, large greenhouses and large metal farmhouse roofs.
- **29% of wildfire detections raised the alarm before any other means of detection.**
- Validation used experimental wood-crib fires and the **41 brightest wildfires of 2023**. Pixel temperature falls as forest timber density rises.

**Rules in the slides. None of these are in the existing note.**

**Post-filter.** Drop detections inside:
- **populated areas**
- **industrial areas + 500 m**
- **industrial buildings + 500 m**

All are applied as shapefiles. There is also a spatial and temporal filter on repeat alerts, which merges multiple alarms for one event.

**Matching rule for validation** (2018 season analysis): fire-registry records are matched to VIIRS within a **750 m search radius** and **Δt < 36** (hours, by context).

**2022 season:**
- **386 detections → 189 events**, about 2 detections per event.
- **39** of those events were confirmed vegetation fires with firefighting.
- **26%** of those 39 were detected before the first call to SOS Alarm.
- About 10% of events were likely greenhouses, farm buildings or solar panels.

**2020 test:** **6 of 28** fires were detected earlier by satellite. **110** unique detections were evaluated, **39** of them by rescue services, using a "Yes / No / Don't know" outcome.

**Location accuracy:** VIIRS geolocation is better than 50 m. Fire-location error is **under about 250 m**, except at the swath edges.

**Verification imagery:** Sentinel-2 band 8 (842 nm), False Colour Urban and SWIR, to find active fires and recent scars.

**Concrete action for us** (field thread, with a helper for the prediction threads):
1. Add a **mask layer** before alerts reach phones: OSM or Bhuvan settlement polygons, plus industrial sites, brick kilns, solar farms and stone crushers, each with a **500 m buffer**.
2. **Merge alerts into events.** Points within 750 m and 36 h become one field task, so that 2 detections don't create 2 trips. Sweden's ratio of about 2 detections per event suggests this could roughly halve field tasks. **(inferred)** for Ratapani.
3. Use the same **750 m / 36 h** rule when matching field reports to VIIRS points for label work.
4. Add a "Don't know" outcome only for remote reviewers, never for field staff.

---

## 5. Indonesia: Sofan, Yulianto & Sakti 2022, ISPRS IJGI 11:601, the "13% static mask"

**Read:** FULL, 16 pages (https://www.mdpi.com/2220-9964/11/12/601, CC BY).

**Data:** VIIRS VNP14IMGML monthly files, 2012–2020. The work uses the product's own **`type` field**:

| `type` | Meaning |
|---|---|
| 0 | Presumed vegetation fire |
| 1 | Active volcano |
| 2 | Other static land source |
| 3 | Offshore or over water |

**Method:**
1. Apply a **1 km dissolved buffer** to points of types 1–3 to form clusters. This gave **33 volcano clusters** (21,893 points), **156 static-source clusters** (24,288 points) and **6,003 water clusters** (43,849 points).
2. Measure distance from each point to the nearest feature, using the median per island.
3. Draw multiple ring buffers around volcanoes, roads, settlements, water bodies and coastlines, using those medians.

**Median distances for static sources (type 2):** **642 m to settlements** and **112 m to roads**. For settlements in Kalimantan and Sumatra they used the first quartile instead (0 m and 78 m). Type-3 points were a median **366 m** from water bodies.

**Result on 2021 data:**
- **54,411 VIIRS points → 7,139 removed (13%)**, leaving 47,272.
- **2,142** of the removed points (30%) were checked on high-resolution imagery: **user accuracy 97%**.
- The errors were real fires on peatland near rivers.

**Character of false points:**
- **More than 90% were "nominal" confidence.** Mean pixel area was **0.21 km²**.
- FRP differs significantly between types (Tukey test, 95%).
- The six main static sources: industrial and mining areas, industrial roofs, open mines, gas flares, agricultural areas, industrial chimneys.

The existing note's 13% is **correct**. Add the 97% accuracy and the `type` field.

**Concrete action for us** (field thread, and label cleaning for the prediction threads):
1. **Use `type`** where we pull archive VIIRS (the FIRMS archive / VNP14IMGML has it; the NRT feed does not). Drop `type ≠ 0` from the label set and from historical analysis.
2. For NRT alerts, apply a **static zone mask**: 642 m around settlement polygons and 112 m around main roads, inside or bordering the sanctuary.
3. **Measure the effect** on 2017–2026 Ratapani VIIRS: count points removed and check how many of them have a dated Sentinel-2 scar.
   - If scar overlap among removed points is **below 10%**, adopt the mask.
   - If it is higher, the settlement buffer is too large for dry deciduous forest fringes, where farm fires really do spread into forest. Shrink it to 300 m.

---

## 6. Gao, Sun & Miao 2026, Remote Sensing 18:904: a persistent-heat-source mask with numeric rules (found on the way)

**Read:** FULL text, by search; I didn't read every equation (https://doi.org/10.3390/rs18060904, CC BY).

**Persistent mask (PFM), worked out on a 0.004° grid (about 400 m, matching VIIRS 375 m).** These rules can be copied directly:
- A **hit-day** is a cell-day with at least one VIIRS detection.
- A **year counts as active** if the cell has **10 or more hit-days** in it.
- The cell is persistent if it was **active in at least 2 of 3 years** (2022–2024) **and** its intensity is at or above the 60th percentile.
- **Seasonality gate:** the normalised month-of-year entropy **H_norm must be at least 0.60**, computed only where there are 15 or more hits.
  - H_norm = ln M / ln 12 for M evenly used months, so 0.60 means roughly **5 or more months** of activity.
  - This screens out seasonal crop burning and keeps year-round sources.
- A short-term mask (SHM) catches newly appearing static sources from night-time I4/I5 stability.

**Results** (N = 3,435 validation cases):
- False-positive rate fell from **88.6% to 22.7%** in industrial and urban areas, and from **100% to 57.3%** at volcanoes.
- Forest and grassland fires were unaffected (**F1 ≈ 0.999**).
- Omission for fragmented crop-residue burning fell from **11.2% to 1.3%**.
- Validation labels counted a fire as real where **ΔNBR ≥ 0.10**. 47.5% of mask polygons had a point-of-interest (factory, flare, etc.) within 2 km.

**Concrete action for us** (field thread mask, and label cleaning):
1. Apply these rules to the 2017–2026 VIIRS archive within 10 km of Ratapani: 10 hit-days per year, active 2 of 3 years, H_norm ≥ 0.60.
2. **(inferred)** Forest fire cells in Ratapani burn only in February–May. With 4 months or fewer, H_norm is about 0.56 or below, so they will fail the entropy gate and stay in. **Brick kilns, which run October–June (8–9 months), will be flagged.** Industry and kilns go into the mask automatically.
3. Expected effect: removal of most repeat non-forest points around the Mandideep and Obaidullaganj industrial belt, without touching forest fire labels. Check this by confirming that no masked cell has a Sentinel-2 scar.

---

## 7. Slough, Kopas & Urpelainen 2021, PNAS 118:e2015171118

**Read:** PARTIAL, a summary of the full text on PMC (PMC8307376). The PDF and the Europe PMC XML were blocked.

**Design:**
- 76 Native Communities in Peru: **39 treated, 37 control**, block-randomised by public lottery.
- 36 treated communities complied.
- **3 monitors per community** were trained, used a smartphone mapping app, received **monthly** GFW/Geobosques (Landsat 30 m) alerts, and were **paid for conducting monthly patrols**. Pay depended on patrolling, not on outcomes. The amount is not in the main text.

**Effects** (intent to treat):

| Group / period | Change in forest loss | 95% CI | p (one-tailed) |
|---|---|---|---|
| Year 1 | **−8.4 ha** (−52% vs the control mean) | [−19.4, 2.6] | 0.06 |
| Year 2 | −3.3 ha | [−13.6, 7.0] | 0.26 |
| Two years combined | −37% | — | — |
| High-threat half, year 1 | **−22.0 ha** | [−46.3, 2.3] | 0.04 |
| Low-threat half | No effect (floor effect) | — | — |

**Monitoring data:**
- **8,107 reports** in total.
- Per community: median **195**, range 16–699.
- Reports rose by about **2 per month** and doubled in year 1.
- **+0.83 reports per km patrolled per month.**
- Each record holds monitor ID, date and coordinates.
- The share of alerts verified is **not reported**.

The existing note ("about 8 ha, imprecise, largest where threat was highest") is **correct**.

**Concrete action for us** (field thread):
- Our weekly per-beat table should include **reports per guard per month** and **km of route tracks per month**, which are Slough's two activity measures.
- **(inferred)** Expect report volume to roughly double over the first season as staff learn the app. Don't judge adoption in month 1.

---

## 8. Cappello et al. 2022, Remote Sensing 14:4284 (Peru PNCB)

**Read:** FULL, 18 pages (https://doi.org/10.3390/rs14174284). The forms in Appendix A and B are images only.

**Numbers:**
- **445 satellite alerts** (Landsat 8, 30 m, 8-day revisit) and **1,853 community observations** from 45 communities in 6 regions.
- **95% of observations were routine patrols. Only about 5% responded to alerts**, from 8 communities.
- **Response lag:** only **23** field observations could be tied to an alert. These were all on paper.

| Lag from alert to field visit | Observations |
|---|---|
| 20 days | 8 |
| About 60 days | 10 |
| 110–125 days | 5 |

- **Location check:** each alert point was given a **15 m buffer**. All 49 alert-driven observations fell **within 4 km** of an alert, and many sat exactly on the alert coordinates.
- **Labels:** satellite alerts called 76.4% of cases "new plantation". Field reports called 42.3% "open plantation" and **26.8% "undefined"**, and listed 9 driver classes against the satellite's 5.
- **Paper forms ask for:** location, land cover, type of deforestation, recorder details, photos and other information. Routine and alert-driven patrols use **separate forms**. The mobile version uses **ODK**.
- Communities with phones produced more alert-driven reports.

The existing note's wording "faster data and a higher response rate" is the **paper's own claim**. The measured lag figures above are all from paper reports, so the "faster" part has no numbers behind it.

**Concrete action for us** (field thread):
1. Keep **two report types**, `alert_response` and `routine_patrol`, so patrol sightings are not counted as alert outcomes.
2. Put a hard **time limit** on alert tasks: close as `not_visited_in_time` after **72 h**. Peru's 20–125-day lags show what happens with no limit.
3. Flag reports whose location equals the alert point to within 1 m. That means the guard typed the coordinates instead of standing there.

---

## 9. Moffette et al. 2021 (Nature Climate Change 11:172) and Assunção et al. 2023 (AEJ Applied 15:125)

**Read:** ABSTRACT for both. Nature is paywalled and the AEA page was not fetched. A CPI working-paper version exists: https://www.climatepolicyinitiative.org/wp-content/uploads/2021/12/WP003-DETERing-Deforestation-in-the-Amazon.pdf

**Moffette et al.:**
- GLAD alert **subscriptions** in 22 tropical countries cut the probability of deforestation in **Africa by 18%** compared with 2011–2016 levels.
- The cut was larger in protected areas and concessions.
- There was **no effect on other continents**, and alerts merely being *available* had no effect.
- Value: **US$149–696 million** at the social cost of carbon.

**Assunção et al.:**
- Cloud cover over the DETER alert system is used as an instrument for enforcement (fines).
- Deforestation in **2007–2011 was 75% smaller** than it would have been without fines. The working paper said 73%.
- No leakage to neighbouring areas.

The existing note's claims are **correct**.

**Concrete action for us** (field thread): the evidence supports a **named recipient** for each alert and a visible enforcement or response record. Record `assigned_to` at the moment of push, and report per beat. Nothing further to copy.

---

## 10. Data models to copy: Forest Watcher, ODK, KoboToolbox, PMAY

### 10a. Forest Watcher (WRI) server schema

**Read:** FULL source code of `wri/fw_forms`, files `app/src/models/answersModel.js`, `reportsModel.js` and `questionnaireModel.js`, via raw.githubusercontent.com. The field manual PDF has only 623 words and holds no schema.

`Answer` (one field report) has these fields:

| Field | Meaning |
|---|---|
| `report` | Template ID |
| `reportName` | |
| `templateName` | |
| `fullName` | |
| `username` | |
| `organization` | |
| `teamId` | |
| `areaOfInterest` | |
| `areaOfInterestName` | |
| `language` | |
| **`userPosition`** | Where the phone was |
| **`clickedPosition`** | The alert or pin the user chose |
| `startDate` | |
| `endDate` | |
| **`layer`** | Which alert dataset, e.g. VIIRS |
| `user` | |
| `responses` | Name/value pairs |
| `createdAt` | |

**Template questions** carry: `type`, `label` (per language), `name`, `defaultValue`, `values`, `required`, `order`, `childQuestions` and `conditions` (show if name = value).

**Action for us:** store **both `user_lat/lon` and `alert_lat/lon`** in each report, plus `alert_layer` (VIIRS-SNPP, VIIRS-NOAA20, NOAA21, MODIS, FSI). Their distance is the key fraud and accuracy check.

### 10b. ODK Collect audit

**Read:** FULL (https://docs.getodk.org/form-audit-log/).
- `audit.csv` columns: `event`, `node`, `start`, `end`, `latitude`, `longitude`, `accuracy`, `old-value`, `new-value`, plus `user` and `change-reason` when switched on.
- Location settings, all three required: `location-priority` (`high-accuracy` / `balanced` ≈100 m / `low-power` ≈10 km / `no-power`), `location-min-interval` (s) and `location-max-age` (s), where max-age ≥ min-interval. Example: `location-priority=balanced location-min-interval=60 location-max-age=120`.
- **When a mock provider is detected, accuracy is set to 0**, which is the confirmed mock-location flag.
- `track-changes-reasons=on-form-edit` forces a reason for any edit.
- `identify-user=true` forces the user's name to be entered.
- Logged events include `location tracking enabled/disabled` and `location providers enabled/disabled`.

### 10c. KoboToolbox metadata

**Read:** FULL (https://support.kobotoolbox.org/metadata_xls.html).
- Fields: `start`, `end`, `today`, `deviceid`, `username`, `phonenumber`, `email`, **`start-geopoint`**, **`background-geopoint`** (records the fix when a named trigger question is answered) and `audit`.
- **In web forms, `deviceid` resets with each new browser window, and `audit` is not supported.** A browser-only app therefore cannot get a stable device ID this way. `_submitted_by` is the trustworthy account field, not the editable `username`.

### 10d. PMAY geotag rules

**Read:** FULL for the PMAY-U geotagging advisory (https://pmay-urban.gov.in/uploads/guidelines/PDF-Geo-tagging-Final%20Advisory%20GIS.pdf). PARTIAL for the 2016 PMAY-U operational guidelines. The PMAY-G framework PDF returned 401.

Rules that can be copied:
- Capture location **only when the app shows GPS accuracy under 10 m**.
- Take **2 photos per stage**, waiting **10–20 s** after saving each one while standing still.
- Take repeat-stage photos from **nearly the same coordinates** as the earlier stage.
- Record the side the photo was taken from (Left / Right / Centre / Rear) and the capture point (roof centre / house centre / door step / rear).
- Fields captured automatically with no user input: **observer name, organisation, mobile number, device unique ID, date-time stamp, photo coordinates**.
- Photos are 640×480, **300–600 KB**.
- A supervisor must **moderate each photo within 4 days**. Each stage must be geotagged **within 5 days** of completion.
- Up to **50 images per surveyor per day**.

**PMAY-G sampling:** Parliament answers (search results; Rajya Sabha PQ 267, 7 Feb 2025) state that **block officers inspect about 10% and district officers 2% of houses at each stage**. That confirms the existing note's "secondary source" figure. A 2025 CAG audit found the monitoring units mostly not set up.

**Concrete action for us** (field thread):
1. **Accuracy gate:** block "submit" until the browser fix has accuracy of 30 m or better. 10 m is unrealistic under canopy **(inferred)**. Store the accuracy value, and flag `accuracy == 0` (ODK's mock sign).
2. Require 2 photos at least 10 s apart.
3. Auto-fill device and user fields.
4. Set a ranger moderation limit of **4 days**.
5. Run a random in-person re-check of 10% at range level and 2% at division level (the PMAY-G ratios).
6. Since a browser cannot give a stable device ID, set our own UUID in the app's local storage on first login. **(inferred)**

---

## 11. Sources checked briefly, or not reachable

- **Tamil Nadu** RTFFMS page. **PARTIAL** (search snippet; the page returned 503 twice).
  - Dashboard fields: **Fire Alert ID, Location, Division, Attended By, Rejected By, Accepted/Rejected status, GPS reading of the affected area, burnt area (ha), type of forest land, Fire Extinguish Timing**.
  - The page partly contains placeholder filler text, so treat it as intent rather than proof of operation.
  - "91% of large fires controlled within 24 h" is **based on FSI data for 2022** (2023 press release).
  - Action: add `attended_by`, `rejected_by` and `fire_out_time` to our schema.
- **Madhya Pradesh AI forest alert system** (April 2025). New, and in our own state; summarised from Drishti and APAC (news only).
  - It alerts on **land-use change, not fire**. It uses GEE (NDVI/SAVI/EVI plus SAR, 3 dates) and a custom AI model.
  - Alerts are **polygons** sent to a field app. Staff confirm with **GPS-tagged photos and voice notes**. The DFO dashboard groups alerts **by beat and field post**.
  - Pilot divisions: Shivpuri, Guna, Vidisha, Burhanpur, Khandwa. Ratapani's divisions are not among them.
  - Action: ask MP Forest Department whether fire alerts could use the same app and beat login list, so staff don't need a second app.
- **M-STrIPES** (WII/NTCA). A secondary source (Indian Masterminds feature) says it records "**forest fires**" along with patrol tracks. Fire field definitions were not found. The existing note's "I didn't find a source confirming M-STrIPES handles fire" can be softened.
- **Indonesia SiPongi / Manggala Agni.**
  - A KSDAE bulletin (FULL, 2 pages) shows daily ground checks driven by hotspots of **confidence ≥ 80%** (Terra/Aqua, LAPAN and NASA).
  - SiPongi confidence classes, per Databoks quoting SiPongi: low 0–29, medium 30–79, high 80–100.
  - The SiPongi Mobile guide, which has a groundcheck section, was unreachable (DNS failure).
- **Odisha per-point fire report** (`odishaforestgis.in/ofms/uploads/firepoint/source/FIRE_REPORT.pdf`). The search snippet shows a per-point verification column with values like "Verified th fire points which falls in paddy field" and "No Fire Found". **The link now returns 404.** This would be the per-point outcome table we want. Ask Odisha for the current export.
- **VIIRS night-time "low" confidence.** An arXiv preprint (2510.26816, not peer reviewed) finds **0 of 6.0 M night-time detections are 'low' confidence** (2023). **(inferred)** This follows from the VIIRS algorithm's design, where 'low' is a daytime sun-glint class. For the prediction threads: **do not filter night points by `confidence == low`**. The filter removes only daytime points, which biases day versus night label counts.
- **India-specific VIIRS commission study.** None found that compares FSI or VIIRS alerts against field checks, apart from the Uttarakhand department figures. Coskuner 2022 (Turkey; 375 m buffer; VIIRS overall detection accuracy 1.3–25.6% by land cover) is the closest method. The page returned 503, so it was not re-read.
- **SMART data model.** No public fire-category schema was found. Models are per site, exported as XML from SMART Desktop. Ask WCS India or WII for a sample.

---

## Verified numbers

| Claim in `field_alert_systems.md` | Status | Exact value and source |
|---|---|---|
| Uttarakhand: 1,952 alerts, 132 real, 766 false, 754 outside, ~300 controlled | Correct | Sums to exactly 1,952. 132 fires = 18.84 ha. ETV Bharat, 30 Jan 2026 |
| Uttarakhand: source document | Found (letter not public) | PCCF letter to DG FSI, 31 Dec 2025. 1,050 checked: 64/377/479/130 |
| Odisha 2026: 20,841 / 20,037 / 804 / 2,885 / 99.97% | Correct | OFMS PDF. Also 3,056.16 ha affected |
| Odisha 2025: 99.94% | Roughly right | Search snippet 29,694/29,709 = 99.95% (rounding) |
| Odisha: 200 m auto-attended | Single source | NRSC deck (snippet; PDF 404) |
| Sweden: 17 min, ~10% false, 29% first | Correct | Abstract, Dybbroe et al. 2026 |
| Sweden mask | New | Populated areas, plus industrial areas and buildings + 500 m (SMHI 2021, 2022) |
| Sofan 2022: mask removed 13% | Correct | 7,139 of 54,411 (2021 data). User accuracy 97% |
| Slough 2021: ~8 ha year 1 | Correct | −8.4 ha, CI [−19.4, 2.6], −52%. High threat −22.0 ha |
| Moffette 2021: subscriptions −18% Africa | Correct | Abstract |
| Cappello 2022: 1,853 reports, 445 alerts | Correct | Plus: only 5% alert-driven; lags 20–125 days |
| Assunção 2023 | Correct | 75% less deforestation 2007–2011 because of fines |
| PMAY-G 10% block / 2% district | Confirmed (Parliament answer, via search) | Per construction stage |
| FSI large fire | New | 3 or more SNPP polygons close together; tracked until out, + 3 days |
| FSI mask | New | Manual digitising, consecutive VIIRS points, feedback, + 500 m buffer |
| FSI latency | New | 1–1.5 h, 6 overpasses a day |

---

## Ranked actions

| # | Action | Thread | Expected gain | Effort |
|---|---|---|---|---|
| 1 | Use the closed outcome list (`fire_in_forest`, `no_fire_found`, `fire_outside_forest`, `controlled_burn`, `burnt_fire_out`, `could_not_reach`) plus FSI's feedback fields (`fire_occurred`, `area_burnt_ha`, `type_of_land`, `type_of_fire`, `cause_of_fire`, `fire_details`) | Field, Prediction | Our results become directly comparable with Uttarakhand's table, can be pasted back to FSI, and become label corrections | Low, a schema change |
| 2 | Merge alerts into events (750 m, 36 h) and run a large-fire flag (3+ points, open until 3 fire-free days) | Field | About half as many field tasks (Sweden: 386 detections → 189 events) | Low |
| 3 | Mask before dispatch: settlements, industry, kilns, solar farms + 500 m (FSI, SMHI), plus Gao's persistence rule (10 hit-days per year, 2 of 3 years, H_norm ≥ 0.60) built from the 2017–2026 archive | Field, Prediction | 10–15% fewer false tasks (Sweden ~10%, Sofan 13% at 97% accuracy); a cleaner label archive | Medium, about a day of GIS work |
| 4 | Drop VIIRS archive points with `type ≠ 0` from labels. Don't filter on `confidence == low` (it is daytime only) | Prediction | Removes static-source false positives; avoids a day/night bias | Low |
| 5 | Location proof: store `user_lat/lon` and `alert_lat/lon`, GPS accuracy (submit at 30 m or better; flag 0), 2 photos at least 10 s apart, automatic 200 m "reached" timestamp, a local UUID per device, and edit reasons | Field | Fake reports harder to file; distance becomes measurable | Medium |
| 6 | A 72 h deadline on tasks; separate `alert_response` and `routine_patrol` forms; flag reports whose coordinates equal the alert point | Field | Avoids Peru's 20–125-day lags and mixing patrol data into alert outcomes | Low |
| 7 | Weekly per-beat sheet in Odisha's 11-column layout, plus outcome split, median burnt ha, reports per guard and km of tracks | Field | Accountability for named recipients (Moffette, Slough) | Low |
| 8 | Ranger moderates within 4 days; random in-person re-check of 10% (range) and 2% (division) | Field | Audit consistent with PMAY-G | Low |
| 9 | Treat off-season (Nov–Jan) FSI points as about 6–8% real; no positive label without a scar or field confirmation. Remember that confirmed fires are only about 0.15 ha, so most will have no Sentinel-2 scar | Prediction | Fewer false-positive labels, and no wrong "false alert" relabelling | Low |
| 10 | Ask (a) Odisha for the per-point FIRE_REPORT export, (b) Uttarakhand for the 31 Dec letter and month tables, (c) MP for the AI alert app and beat login list, (d) WII for an M-STrIPES fire sample | Both | Real per-point ground-truth tables; possibly reuse MP's app | Low (emails) |
