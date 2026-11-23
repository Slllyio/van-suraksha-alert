# How forest departments manage fire, and which practices leave traces we can map (scouting, round 3, topic: mgmt)

October 2026. Focus: Madhya Pradesh (MP) practice, national rules, tiger-reserve plans, measured effects of fire lines, early burning, watchtowers and village payments, and international practice that maps well. Earlier notes already cover these, so this note does not repeat them: the Uttarakhand split of alerts into "controlled burn" and other outcomes (field_alert_systems*.md), Schmidt et al. 2018 Cerrado and Tarimo 2015 miombo early burning (leaf_fall_phenology.md D1, D3), the iFOREST tendu and mahua work (human_fire_drivers.md), and the MPFD ArcGIS lead for compartments and fire lines (open_datasets.md).

Labels used here: **FULL** means the whole text (or every relevant chapter) was read. **PARTIAL** means some sections were read. **ABSTRACT ONLY** means only the abstract or a search summary was seen. **[inference]** marks my own reasoning or arithmetic, not something a source states.

Note on access: mpforest.gov.in, forests.ap.gov.in, forests.tn.gov.in, mahaforest.gov.in, ndrf.gov.in and tnp2k.go.id all reset or returned 503 from this container. The MP Fire Compendium (mpforest.gov.in/publicdomain/atlas/FireCompendium.pdf), the MP RTI department manual, the Tamil Nadu fire guidebook and the Maharashtra management plan therefore could **not** be read. All need a download from an Indian connection (see actions).

---

## Headline findings

1. **MP runs a very dense fire-line network, and it is burnt every winter.** The MP State CAMPA approval for 2025-26 funds **139,364 km** of fire-line creation and maintenance (Rs 18.90 crore), **4,730 fire watchers** (Rs 9.07 crore) and **21 watch towers** (Rs 1.78 crore). MP's FFPM plans describe the work as "cutting grass and other growth, cleaning, burning", in 6 m and 12 m widths. [inference] Over about 94,700 km² of recorded forest, that is about 1.5 km of line per km², or a line every ~1.4 km. A typical 25 ha cell holds ~0.37 km of line, and a burnt 6 m strip covers ~1% of the cell.
2. **The national plan (NAPFF 2018) tells states to map and digitise fire lines, record controlled burning in a database, and site watchtowers by viewshed.** Few states have done any of it. In 2017 only Telangana had digitised its fire lines (3,866 km). Only 47 of 94 surveyed officers said all required fire lines in their area were cleared, and 43 of 70 said controlled burning was not done regularly.
3. **Early burning reduces later fire roughly one-for-one in savannas, but much less in forests.** Western Arnhem Land: slope ≈ −1 (late dry-season fire fell from 29% to 12.5% of the area). Across biomes, leverage ≈ 0.039 × (mean % burnt per year). Cerrado integrated fire management: early-season share of burnt area rose from 11.2% to 29.5%, with a −62% linear trend in burnt area, though the late-season difference from controls was **not** significant.
4. **Watchtower studies measure only visibility, never outcomes.** No paper I found ties tower viewshed to smaller burnt area or faster response. Indian towers are 25–30 m tall and see 5–6 km over open ground, but only 2–3 km from valleys (Kudremukh). This is an open question that Ratapani data could answer.
5. **Village payments are written into MP plans, but the only randomised test found no effect.** MP's 2020-21 plan proposed paying 12,014 villages Rs 5,000 each for 1.5 months of fire protection. The Ministry approved 2,000 villages at Rs 7,500 each. A 75-village randomised trial in Indonesia found no significant change in fires. A Melghat (Sipna) prize scheme of Rs 10,000 to Rs 1 lakh coincided with a fall from 221 fires and 2,221 ha to 35 fires and 168 ha. That is a before/after comparison only, and the "after" year was 2020 (COVID lockdown).
6. **Our own VIIRS data already shows the signature of managed winter burns.** Of the 8,117 S-NPP points for Ratapani (2013–2024), 536 (6.6%) fall in Nov–Jan. Only **2% (Nov), 9% (Dec) and 11% (Jan)** of those are night detections, against 31–35% in Mar–May. That fits attended daytime burns that are out by night (computed this session; the interpretation is my inference).
7. **NTCA now audits tiger-reserve fire work against the reserve's Tiger Conservation Plan (TCP).** The May 2026 audit protocol scores the % of TCP fire-line km cleaned, the area of controlled burning against the TCP, the % of watchers deployed, and towers against the TCP. Ratapani became a tiger reserve in Dec 2024, so its TCP will have to list fire-line km, controlled-burn area and towers. That makes the TCP the document to request.

---

## Part A. Indian rules and money: what the department is required and funded to do

### A1. National Action Plan on Forest Fire (NAPFF), MoEFCC, April 2018. FULL
Link: https://www.moef.gov.in/uploads/pdf-uploads/pdf_68a4157b8b3d38.38401489.pdf (23 pp, 4,776 words). This host's TLS certificate fails for "www."; plain moef.gov.in works.

What it says (exact):
- **Risk zones** must be reviewed "at least once every five years". Listed factors: forest type as a fuel proxy, optional field fuel load, distance to roads, habitations, farmland, transmission lines and railways, terrain, social dependence, fire history ("Fire records prior to 2003 may be geo-referenced"), sacred sites, and bamboo flowering.
- Working Plan Officers turn the risk zones into "creation of additional fire lines, watch towers and other infrastructure" in the Annual Plan of Operations (APO).
- **§6.1(iii) Watchtowers:** states "shall perform an assessment of the efficacy of the existing network of watchtowers", and "propose new locations for fire watchtowers based on coverage, visibility, ignition sources".
- **§6.1(vi):** FSI reviews alert verification, and MoEFCC monitors it "in the month of December every year".
- **§6.2:** IT cells must inventory and map "watchtowers, ground crew stations, controls rooms and fire lines" plus natural fire breaks.
- **§6.3 Fire lines:** "SFDs may undertake the mapping and digitizing of the location of existing fire lines and other infrastructure such as roads, transmission lines, and rail lines that may function as fire breaks." This should be followed by a review of maintenance status, and new lines should be placed "on a scientific basis considering their potential efficacy". "Plantations should not be raised on existing or proposed fire lines."
- **§6.4 Control burning:** (i) prioritise areas through risk zonation, (ii) "Monitoring of the performance of control burning at the Circle level, and integration of monitoring data into a database maintained by the SFDs", (iii) release funds "prior to the onset of the peak fire season", and (iv) states should write their own guidelines for controlled and prescribed burns.
- **§4:** communities "could also be incentivized ... in the form of money, rewards, social recognition, preference in Government schemes". Each JFMC micro-plan must have a fire chapter listing vulnerable areas and water sources.
- **§5.2:** encourages forest-floor biomass removal (pine needles, dead bamboo, women's SHGs).

**Concrete action for us** (field system, thread 5; prediction, thread 1). The plan obliges MP to hold three things we need: a digitised fire-line layer (§6.3), a circle-level database of controlled burns (§6.4ii), and a tower inventory (§6.2). Ask the Ratapani/Obaidullaganj DFO and the MP IT cell (who run FAMS) for exactly these, citing the section numbers. If they do not exist, our derived layers (Part D) fill a stated national requirement. That is a strong reason for the department to engage.

### A2. MP Forest Fire Prevention & Management (FFPM) Annual Plans of Operation, MoEFCC sanction orders. FULL (each order read in full)
- 2019-20 General works: https://moef.gov.in/uploads/2019/08/1MP2019-20.pdf
- 2019-20 Tribal Sub-Plan (TSP) works: https://moef.gov.in/uploads/2019/08/41mp.pdf
- 2020-21 Scheduled Caste Sub-Plan (SCSP) works: https://moef.gov.in/uploads/2019/08/SCSP-MP.pdf
- 2024-25 ad-hoc release: https://moef.gov.in/uploads/2024/05/FPD-Sanction-MP-FFPM-16052024.pdf
- 2023-24 TSP (Rs 231 lakh; annexure not machine-readable): https://moef.gov.in/uploads/2023/07/FPD%20Sanction%20Madhya%20Pradesh%20(TSP%20Works).pdf

Exact numbers:

| Item | 2019-20 General | 2019-20 TSP | 2020-21 SCSP (proposed → recommended) |
|---|---|---|---|
| Fire-line maintenance, 6 m wide | 20,000 km at Rs 881/km (3.35 man-days/km) | 1,980 km | 17,626 km → 1,500 km at Rs 1,082/km |
| Fire-line maintenance, 12 m wide | 7,000 km at Rs 1,394/km (5.3 man-days/km) | 1,454 km | 10,724 km → 1,500 km at Rs 1,711/km |
| Fire watchers | 2,000 for **45 days** at Rs 295/day (Rs 265.5 lakh) | 264 ("in all the 63 territorial divisions and 8 wildlife areas of MP for 45 days") | 1,578 → 553 at Rs 323/day for 45 days |
| Village/community incentive | – | – | 12,014 villages at Rs 5,000 ("for 1 1/2 month") → 2,000 at Rs 7,500 (Rs 150 lakh) |
| Camper fire-patrol vehicles | – | – | 116 → 61, "for 1 1/2 month" |
| Total APO | Rs 620.49 lakh | Rs 86.63 lakh | Rs 1,963 lakh proposed → Rs 392.87 lakh |

- The work item reads "Fire line maintenance (cutting grass and other growth cleaning, Burning)". **Burning is part of the fire-line job.**
- Every order requires "satellite photographs of physical deliverables with date and latitude-longitude coordinates before and after implementation". Watcher and fire-line wages must be paid by Direct Benefit Transfer (DBT), with supporting documents. Water-tank sites must be reported with GPS. Quarterly progress reports use "annexure-VII of operational guidelines".
- Outcome indicators are set by FSI from satellite data: "Number of forest fires" and "Total estimated area affected".
- 2024-25: an ad-hoc Rs 99 lakh limited to (a) equipment, (b) "Maintenance of fire lines and creation of fire lines during fire season", (c) fire watchers, and (d) "Incentivizing Villages/Communities ... during fire season".

**Concrete action for us** (threads 1, 2, 5).
1. **The geotagged before/after photos and DBT records already exist** for every km of fire line and every watcher. Request the Raisen/Obaidullaganj division share of these. Photos with dates and coordinates give a ground-truth set of fire-line locations and burn dates, which can train and validate the linear-burn detector (D1). DBT watcher records give, by village, who watched and for which dates, which feeds the watcher feature (D4).
2. Watchers are paid for **45 days**, not the whole Jan–Jun season. Find out which 45 days (likely mid-March to April, the peak). Then add a calendar flag `watchers_on` to the 2-day model. [inference] Expected effect: small. Its main use is to explain why detection lag and scar size may change at the window's edges.
3. Of the 12,014 villages proposed for incentives, only 2,000 were funded. If the list of funded villages for our area can be obtained, it is a natural treatment/control split for testing whether payments change burnt area near those villages (see C3).

### A3. MP State CAMPA Annual Plan approval 2025-26 (National CAMPA, 15 May 2025). FULL (forest-protection section)
Link: https://nationalcampa.nic.in/dashboard/SanctionPDF/682d7bd5ac4b5.pdf
- Item 5(2)f, Forest fire prevention and control: "Fire line (creation & maintenance) **139364 km**, Rs 18.90 crore, Approved". "Fire watchers **4730 Nos.**, Rs 9.07 crore, Approved". Fire equipment Rs 0.60 crore. "watch towers **21 Nos**, Rs 1.78 crore". Fire training Rs 0.30 crore. "Lidar Technology-Dhar" Rs 3.00 crore, Deferred.
- The whole State CAMPA approval is Rs 1,038.54 crore, against Rs 1,478.38 crore proposed.

[inference] Rs 18.90 crore / 139,364 km = Rs 1,356 per km, which matches the FFPM unit rates for 6–12 m lines. So this is mostly annual maintenance, with each line cleared and burnt once a year. Rs 9.07 crore / 4,730 is about Rs 19,200 per watcher, or ~60 days at Rs 320. That again means a short engagement, not the whole season. Rs 1.78 crore / 21 is about Rs 8.5 lakh per tower.

**Concrete action for us** (thread 1, 2, 4). The density of ~1.5 km of line per km² means fire lines are not a rare feature. They criss-cross the sanctuary at roughly compartment scale. Two consequences:
- **Spread model (thread 4):** fire lines should be non-burnable strips that are 6 m or 12 m wide. Mark each strip as cleared or not cleared for that year, because only about half are actually cleared (A5).
- **Burn-scar labels (thread 2):** each winter, ~1% of every cell may burn as a deliberate linear strip. A scar or VIIRS point in Nov–Feb that sits on a straight line is more likely to be a fire-line burn than a wildfire (D2).

### A4. NTCA Forest Fire Audit Protocol, State compliance table, May 2026. FULL (2 pp)
Link: https://ntca.gov.in/wp-content/uploads/2026/05/annexure-pdf.pdf

There are 20 indicators scored 2.5/5/7.5/10. Those that relate to mapping:
- **A1** "% of fire lines (km) as per TCP cleaned & maintained": ≤50% / 51–80% / 81–100%.
- **A2** "% of road side area cleaned vs total fire prone area".
- **A3** "Area under controlled burning vs TCP prescribed extent".
- **A8/A9** fire-prone mapping "using slope, aspect, land cover, AI models etc.". The top score needs "Risk mapping + sensitivity analysis models for spatio-temporal patterns".
- **B1** satellite and drone/PTZ detection. **B2** "% of forest watchers deployed vs approved/required strength". **B3** "Number & condition of fire watch towers vs TCP approval".
- **C3** JFMC/EDC involvement, with the top score at "engaged with incentives/awards".
- **D1** systematic incident records "(location, date, cause, extent, damage, action) via field reports & M-STrIPES".

**Concrete action for us** (threads 1, 5). Ratapani is now a tiger reserve, so it will be audited on this sheet. Three of our outputs map directly onto it:
- the 2-day risk map maps onto A8/A9 ("spatio-temporal modelling" gets the top score);
- a satellite check of which TCP fire lines actually burned or were cleared this winter maps onto A1/A3;
- the field-verification log (location, date, cause, extent, action) maps onto D1. The log should export in an M-STrIPES-compatible format.

This gives the field system a reason to exist that managers are scored on. Also request the Ratapani TCP (or its draft) for fire-line km, prescribed controlled-burn area, towers and watcher strength.

### A5. World Bank and MoEFCC 2018, "Strengthening Forest Fire Management in India". PARTIAL (all fire-line, controlled-burning, detection, community and MP sections read in full; 234 pp)
Link: https://documents1.worldbank.org/curated/en/333281529301442991/pdf/127284-Forest-Fire-Prevention-Management-8Oct2018.pdf (CC BY 3.0 IGO). The "/ar/" mirror URL returns 404.

Numbers:
- **Fire lines are often not cleared:** "Only half of the officers responding ... said that the fire lines required in their area were all clear (47 of 94)". The share answering yes by state was Jharkhand 10%, Odisha 29%, Assam 33%, Chhattisgarh 57% and Meghalaya 64% (Fig. 2.4, n = 93).
- **Length of fire lines (Table 2.5):** Chhattisgarh 91,001 km in working plans and 91,001 km maintained yearly, 0 km digitised. Uttarakhand 16,443 km. Kerala 15,000 km maintained yearly. Telangana 3,866 km, all digitised (the only state). MP did not return the data sheet.
- **Controlled burning:** "nearly two-thirds said that controlled burning was not regularly performed (43 of 70)". Lack of resources was the main reason everywhere.
- **Watchtowers:** of 74 field officers, 40 had towers or crew stations, and 31 of those 40 said all were working. All asked for more. Jharkhand example: 6 of 117 guard posts filled and watchers cut to 6, "resulting in watchtowers remaining unstaffed and thus useless".
- **Watcher wages:** 30 of 66 officers reported delays or shortages in watcher pay.
- **Kerala:** VSS paid Rs 1,000 per hectare protected (150–200 ha per VSS, so Rs 1.5–2 lakh). **Odisha:** best VSS per district gets Rs 20 lakh, best in state Rs 200 lakh. **JFM:** a 2006 study found fires fell 40% at JFM sites in MP, Chhattisgarh and Jharkhand (secondary citation, not verified).
- **MP FAMS (Box 2.6), launched 2007:** a year after rollout, "average time to extinguish fires fell from 11-12 hours to 2-4 hours, and the average area burnt per fire dropped from 12.9 hectares to 7.1 hectares ... to a low of 3.0 hectares in 2016". MP's IT cell checks the next overpass when no field feedback arrives.
- **Raisen field visit (Box 3.2, Jan 2017):** villagers collect honey, mahua and tendu. They are "employed by the forest department ... to help maintain check dams and fire lines ... particularly during the lean season between planting and harvest". Plantation work pays Rs 200/day. "Residents say they have been trained ... to remain with the fires they set". Tendu is pruned, not burnt, "in February and March about 6 weeks prior to harvesting".
- 2017-18 national FFPM outputs: "maintenance of 70,000 km of fire lines and construction of 60 field crew stations".

**Concrete action for us.**
- **Thread 2/4:** never assume a fire line is cleared. Infer each line's status yearly from imagery (D1), and treat an uncleared line as burnable.
- **Thread 1:** fire lines are cut and burnt by local labour in the lean season. Villages that supply that labour also have members who are trained to "remain with" their own fires. That may explain some winter detections near villages that are not wildfires [inference].
- **Thread 5:** the FAMS 12.9 → 7.1 ha drop is the benchmark of what an alert system did before. Report our system's mean area per verified fire in the same units, so managers can compare.

### A6. WII Management Effectiveness Evaluation of Tiger Reserves 2014. PARTIAL (keyword search of 315k words; reserve sections for MP and Maharashtra read)
Link: https://www.wii.gov.in/uploads/media/pdf/mee/MEE_TR_site_evaluation_report_2014.pdf

Fire-line networks and staffing as reported:

| Reserve | Fire lines | Other |
|---|---|---|
| Pench (MP) | "protection from fire (1074 km fire line)" | – |
| Sanjay-Dubri (MP) | "about 2050 km fire lines are cleared on annual basis" | annual Fire Control Plan |
| Kanha (MP) | – | "seasonal deployment of 96 fire protection" labour. Early burning is practised and "controlled fire" is used as a tool |
| Bandhavgarh (MP) | – | "90 seasonal labours are deployed for fire"; no burning in gaur areas |
| Satpura (MP) | fire lines traced yearly | fire squads at vulnerable sites |
| Melghat (Maha) | "fire line maintenance is done directly by EDC through MOU with Range" | only 1.3% of the area burnt in 2012-13 |
| Dudhwa (UP) | 666.92 km, **30 m and 16.5 m** wide | watchers 15 Feb–15 Jun |
| Sariska | 320 km, 5 m wide | per-range km listed |
| Parambikulam | 42 lines, 425.9 km (31.8 km at 10.4 m, 394.1 km at 5.2 m) | – |
| Nagarhole | 1,278 → 1,714 → 1,790 km over three periods | – |
| Nagarjunsagar-Srisailam | 512 km built by locals | 350 fire watchers for 5 months at Rs 5k/month |

**Concrete action for us** (thread 4, thread 2). Widths across Indian reserves range from 3 m to 30 m, with 5–6 m and 10–12 m most common. Use 6 m and 12 m as the two burnable-barrier classes for MP. For a sanity check [inference]: Pench MP (~1,180 km²) has 1074 km, about 0.9 km/km², and Sanjay-Dubri (~1,675 km²) has ~1.2 km/km². So Ratapani (1,271 km² as a tiger reserve) likely has ~1,100–1,900 km of fire line. The detector in D1 should find a network of roughly that length. If it finds a tenth of that, it is missing most lines.

### A7. Other Indian sources (search-level or short reads)
- **Hitavada, 15 Jul 2020, Nagpur Circle (Maharashtra).** FULL (news). Fire-line "cutting and burning in fire prone areas" was finished "by February 15". There were five-year fire-alert sensitivity maps to beat level, 24×7 response units with a 20–25 min target, prosecutions, and nylon nets for mahua collection in a Gondia/Nagpur pilot. Feb–Jun fires: 743 cases and 2,018.6 ha (2019) → 174 cases and 308.2 ha (2020), i.e. −77% and −85%. [inference] 2020 was the COVID lockdown year, so this cannot be credited to the measures. https://www.thehitavada.com/Encyc/2020/7/15/Significant-reduction-in-forest-fires-in-Nagpur-Circle.html
- **Melghat, Sipna Wildlife Division.** ABSTRACT ONLY (search summary of a Hitavada 3 Jul 2020 report). Cash prizes of "Rs 10,000 to Rs 1 lakh" to villages: 221 cases and 2,221 ha the year before → 35 cases and 168 ha. This is the same 2020 confounder. The Anghar Mukt Abhiyan ran in 113 buffer villages, and Melghat fires fell from 379 (2016) to 221 (2021). https://thehitavada.com/Encyc/2020/7/3/Less-damage-due-to-forest-fires-in-Maharashtra-this-year.amp.html
- **Bandipur 2019 inquiry.** ABSTRACT ONLY (news). Lines "should be at least 10 metres" but were 3–5 m in stretches, and missing in places despite records of ~2,500 km. Karnataka: 5–6 fire lines per beat, minimum 20 ft. https://www.deccanherald.com/amp/story/india/karnataka/laxity-led-to-bandipur-forest-loss-of-12k-acres-725574.html
- **Kanha.** ABSTRACT ONLY (2013 news via search). "Early burning of grasslands as per plan" in winter, also in Bandhavgarh. Roadside lines are made by burning fallen leaves and stepped up in March.
- **Uttarakhand amicus report (NGT OA 425/2023).** ABSTRACT ONLY. The fire season is 15 Feb–15 Jun, and the working plan's "methods of annual control burning" are meant for outside the season.
- **Chandigarh State Action Plan on Forest Fire 2026.** FULL (skimmed). It copies NAPFF clause by clause, which shows each state is expected to issue a SAPFF. FSI's SAPFF list (https://fsiforestfire.gov.in/SAPFF/) currently holds only Chandigarh. **The MP SAPFF is not posted, so ask for it.**
- **Satendra & Kaushik 2013, NIDM Disaster & Development 7(1-2).** FULL, low value: general gap list, no widths or dates. https://nidm.gov.in/journal/PDF/Journal/2_Dec_2013/2_Dec_2013i.pdf
- **MP fire season and schedule.** Not found in any readable source. From the pieces above [inference], the likely MP schedule is: fire lines cut Nov–Dec, burnt Dec to mid-Feb (Nagpur's deadline is 15 Feb), watchers for 45–60 days around the Mar–Apr peak, and tendu pruned Feb–Mar. Confirm from the MP Fire Compendium, the Obaidullaganj/Raisen working plan, or the Ratapani TCP.

---

## Part B. Measured effects of management (research)

### B1. Price, Russell-Smith & Watt 2012, IJWF 21:297-305, western Arnhem Land. FULL
Link (author copy): https://ro.uow.edu.au/scipapers/4739 (PDF via https://ndownloader.figshare.com/files/50487963)
- 24,000 km². Landsat fire history 1990–2009 (up to 4 scenes a year, hybrid automatic and manual). Early dry season (EDS) means up to 31 July, mostly prescribed. Late dry season (LDS) means mostly wildfires.
- **Unit of analysis: 57 blocks of 20 × 20 km × 19 years (n = 1,083).** The block size was chosen to be larger than nearly all fires: only 0.02% of fire polygons were bigger, but they held 47% of the area. The model was a GLMM with block as a random effect. Terms: EDS, EDS², last year's EDS and LDS, vegetation, period and zone. A spatially lagged response was added.
- After 2005: EDS rose from 8.7% to 17.4% of area, LDS fell from 29.1% to 12.5%, and total fell from 37.7% to 29.9%. The LDS change was not significant at whole-area scale (n = 19, p = 0.060) but was significant across two zones (p = 0.018).
- **EDS slope = −0.987, with +0.007 on EDS², giving a combined slope ≈ −0.8 until EDS reaches 26%.** Last year's fires also suppress LDS: slope −0.35 for last year's LDS and −0.23 for last year's EDS. The slope was −1.18 with zero cases removed. Semivariogram: autocorrelation is strong below 10 km and absent above 20 km.
- LDS frequency increases with distance to roads and decreases with elevation, slope and drainage density (r² = 0.55).

**Concrete action for us (thread 1, season-level; thread 4).** Run the same "leverage" regression for Ratapani.
- Unit: beat (94) or 2 × 2 km block, by year (2017–2026).
- Response: Mar–May burnt fraction (from our dated scars).
- Predictors: Nov–Feb burnt fraction (the early and fire-line burns), previous year's late and early burnt fraction, year fixed effects (weather), and a spatial lag.
- Settings: GLMM with a beta or logit-normal family and beat as a random effect.

The result answers the project question "does early burning reduce later fires here?" directly from our labels. If the slope is clearly negative, add `early_burnt_frac_this_season` (beat and cell) to the 2-day model as a fuel-removal feature. [inference] Expected: much weaker than −1, because teak litter keeps falling through Mar–Apr and refuels burnt patches (leaf_fall_phenology.md). Price 2015 (B2) also predicts low leverage where the annual burnt fraction is low.

### B2. Price et al. 2015, IJWF, "Global patterns in fire leverage". PARTIAL (abstract, introduction, results)
Link: https://www.uv.es/jgpausas/papers/Price-2015-IJWF_fire-leverage.pdf
- Leverage is the unit reduction in unplanned fire area per unit of previous fire. Across 10 cases: Portugal ≈ 0.9 (0.896, 8-year window; 0.446 after correction), Sandy Desert 0.337, savannas ≈ 1, SW Australian eucalypt forest ≈ 0.25, Sydney 0.33, California chaparral 0. Most other new cases showed no leverage.
- **Leverage rises by 0.039 for each 1% of mean annual area burnt (r² = 0.92 without two outliers).** "approximately 30% of the tropical savanna burns each year (leverage = 1), compared with 5% of eucalypt forest (0.25) and 2% of California chaparral (0)."
- Simulations (Price 2012, Forest Science 58:606, ABSTRACT ONLY): "Long linear (gridded) barriers are far more effective than patch barriers, but gaps in the grid lead to large reductions in leverage".

**Concrete action for us.** [inference] Plug Ratapani's mean annual burnt fraction (from our scars) into 0.039 × % to get a prior for B1. For example, 15% a year gives an expected leverage of ~0.6. The simulation finding argues that the *continuity* of the fire-line grid matters more than its total km. So compute a gap metric for the detected network (D1): the % of compartment edges with a burnt line. Then test whether beats with a more complete grid have smaller mean scar size (thread 2 outcome).

### B3. Franke et al. 2024, Environ. Res. Lett. 19:034020, Cerrado integrated fire management (MIF). FULL
Link: https://doi.org/10.1088/1748-9326/ad2820 (CC BY 4.0)
- Design: 4 protected areas with MIF and prescribed burning since 2014/15, compared with 4 control areas without it. Savanna share was 95.1% vs 96.2%, and cropland was masked. Data: MODIS MCD14ML hotspots 2013–2019 and MCD64A1 500 m burnt area 2001–2019. Seasons: EDS = May–Jun, MDS = Jul–Aug, LDS = Sep–Oct.
- EDS hotspots +137% versus 2014. The EDS share of burnt area went from **11.2% → 29.5%** and the M/LDS share from **85.1% → 67.7%**. Annual burnt area in MIF areas fell along a linear trend of **−62% (R² = 0.77)**, while controls showed no clear trend (R² = 0.34). Means for 2014–2019: 24.6% burnt per year in MIF areas against 12.3% in controls (pre-MIF it was 33.4% against 19.0%, because the most-burnt areas were chosen for MIF).
- GLMM (year as covariate, protected area as random effect): EDS burnt area is significantly higher in MIF areas (exp. estimate 16.6). **The M/LDS difference is not significant**, which the authors read as success, since MIF areas used to burn more.
- Fuel maps: unmixing of green vegetation, non-photosynthetic vegetation and soil on 32-day highest-NDVI Landsat 8/S2 mosaics in Google Earth Engine. Regression on 99 field plots of 50 × 50 m, adjusted r² = 0.91. Forest is masked because canopy hides the surface fuel.

**Concrete action for us.** Copy the **paired control-treatment design** for any management comparison in Ratapani. For example, compare beats or compartments with complete versus patchy fire-line burning, or tiger-reserve core versus surrounding territorial forest after 2024. Use matched controls observed in the same years, so the weather cancels out. Treat a "−62% trend" style result with care: in Franke the significant effect is only the *seasonal shift*. For thread 3, the fuel method is open-savanna only and masks forest. Our teak canopy is leafless in Mar–Apr, so the unmixing could work then (already noted in fuel_load_values.md, not repeated).

### B4. Watchtower viewshed studies
**B4a. Coşkun, Toprak et al. 2023, Fire 6:305, Antalya, Türkiye. PARTIAL (abstract, introduction, methods).** https://www.mdpi.com/2571-6255/6/8/305
- 49 towers and 2,504 fires (2008–2021), of which 78.6% started inside forest. ArcGIS Viewshed run with observer height 10 m, 360°, radius 20 km. The Turkish standard (GDoF Communiqué 285) asks for ≥70% visibility and ≤25 km between towers, and assumes 100 m of smoke. Towers are 5–10 m tall and cover 15 km without binoculars and 20 km with them. They tested two scenarios, 0 m smoke and 100 m smoke. At 100 m only 3 towers see >70% of the area (2 for forest, 7 for fire locations). At 0 m none do.
- Related Turkish results: 56% of the area visible (59% of forest), 70% with roads added (Isparta 2020); 42% of 205,258 ha (Ilgaz); 73% → 81% with new towers (Western Black Sea).

**B4b. Kudremukh NP, Karnataka (Esri India 2012 paper). FULL** (9 pp). https://wgbis.ces.iisc.ac.in/biodiversity/sahyadri_enews/newsletter/issue53/bibliography/307-forest-fire-and-its-management-in-kudremukh-national-park-western-ghats-india-using.PDF
- 5 towers, **25–30 m tall**. Views reach "5 to 6 km radius" in open grassland and "2 to 3 km" if the tower sits in a valley (park staff). Burnt areas were 2,185 ha (2001) and 1,243 ha (2002) from Landsat. "major recurrently fire-affected areas could not be located ... with the existing towers". The percentage itself is missing from the PDF ("Only -%").

**B4c. A 2022 J. Tropical Forestry & Environment paper** (study area not confirmed) kept 13 towers and proposed 27, using fire frequency plus viewshed. ABSTRACT ONLY. https://journals.sjp.ac.lk/index.php/JTFE/article/view/5597

**No study measured outcomes** such as response time, fire size or burnt area against visibility.

**Concrete action for us (threads 1, 2, 5).** Compute a tower viewshed for Ratapani (D4) and **test the outcome ourselves**. Use the per-alert scar area from thread 2 and the VIIRS-to-arrival time from field reports. Compare cells inside and outside the viewshed, controlling for slope, distance to road and fuel. This would be a first. [inference] For litter fires under a teak canopy, the "0 m smoke" case is unrealistic because flames are hidden by trees. Use a target height of canopy (≈15–20 m) plus 10–30 m of smoke, and test the 2–3 km and 5–6 km radii from Kudremukh.

### B5. Village payments
- **Indonesia, West Kalimantan, randomised trial 2018** (Edwards, Falcon, Hadiwidjaja, Higgins, Naylor, Sumarto). ABSTRACT ONLY (Mongabay 2020 summary, AEA registry, TNP2K working-paper listing). 75 villages received training, a small grant, and a large end-of-season payment if satellite data showed no fire. Rp 10 million (~US$750) went up front, and the total was about US$10,800. "While program villages increase fire prevention efforts, we find no evidence of any large or statistically significant differences in fire outcomes". The authors blame a payment too small to compete with oil palm, and collective-action failure. https://news.mongabay.com/2020/12/conditional-cash-payment-fire-village-west-kalimantan-indonesia-study ; https://www.socialscienceregistry.org/trials/3222
- India sources: A2 (MP incentive item), A5 (Kerala, Odisha, JFM 40%) and A7 (Sipna). None is a controlled comparison.

**Concrete action for us (thread 1, analysis; thread 5).** If the list of MP villages paid under the FFPM/CAMPA incentive (or EDC fire-protection MOUs after the TR notification) can be obtained with years, run a difference-in-differences: burnt area within 2–3 km of paid versus unpaid villages, before and after. Use matched pairs, as in Franke B3, and include the 2020 lockdown year as a separate dummy. For the 2-day model, add `village_paid_this_year` to the existing village-distance features only if the test shows an effect. [inference] Prior: weak, given the Indonesia null.

### B6. Australian prescribed-burn mapping that we can copy
- **NAFI fire scars (Charles Darwin University).** PARTIAL (metadata pages). Monthly 250 m MODIS fire scars from 2000 and Sentinel-2 "HiRes" layers. Each pixel is tagged with "the month that covers the largest part of the date interval in which the burnt pixel was detected". Before 2000, Landsat pixels are attributed early or late. Mapping is semi-automatic with "close manual editing", validated by aerial and ground transects. https://www.firenorth.org.au/nafi3/views/help/metadata.html ; TERN record https://portal.tern.org.au/metadata/eadcf179-9c82-5112-a117-23ca99d5f361
- Agency fire histories carry an explicit **burn-type attribute** (prescribed vs wildfire). Examples: WA DBCA Fire History (DBCA-060, data.wa.gov.au) and Victoria's fire history layer (DataVic). [Not opened this session; the attribute names are from my prior knowledge and need checking.]

**Concrete action for us (thread 2).** Adopt the NAFI convention: give each scar a **season class** (Nov–Feb "early/managed window" vs Mar–Jun "main season"), and date it by the majority of its detection interval. Keep a separate `burn_type` field (wildfire / probable controlled / probable fire-line / unknown), as in the agency layers. The WA/Victoria layers are a labelled source for a prescribed-vs-wild shape classifier only if we find our own labels too few. [inference] Transfer from eucalypt to teak is doubtful, so this is low priority.

---

## Part C. What our own VIIRS data says (computed this session from `ratapani/viirs_snpp_2013_2024.parquet`)

| Month | VIIRS points | median FRP (MW) | night share |
|---|---|---|---|
| Oct | 9 | 4.8 | 0.00 |
| Nov | 59 | 4.1 | 0.02 |
| Dec | 140 | 3.4 | 0.09 |
| Jan | 337 | 4.0 | 0.11 |
| Feb | 1,231 | 3.8 | 0.21 |
| Mar | 3,955 | 4.1 | 0.31 |
| Apr | 2,083 | 4.5 | 0.32 |
| May | 297 | 4.5 | 0.35 |

- Nov–Jan points by year: 34, 17, 18, 43, 50, **127 (2018)**, 55, 48, **89 (2021)**, 12, 27, 16 (2013–2024). The year-to-year swings may reflect fire-line budgets or schedules [inference].
- [inference] Winter fires are almost never seen at night. Night detections need fires still burning at ~01:30. Attended burns of fire lines and fields that are put out or burn out by evening would leave this exact signature. **Night share is a cheap per-cluster flag for "managed burn".** A Nov–Feb cluster seen only by day, low FRP, and lined up along a straight path is a candidate controlled or fire-line burn.

---

## Part D. Features, label corrections and how each thread should use them

### D1. Detected fire-line network (yearly)
- **Input:** Sentinel-2 L2A for 2017–2026, 10 m bands (B4, B8) and 20 m bands (B8A, B11, B12). Pre-composite from 1–30 Nov (median, cloud-masked). Post-composites at 15 Jan and 20 Feb, taking the minimum NBR (or the max of BAIS2/MIRBI) over the window.
- **Steps:**
  1. Compute dNBR plus a 10 m NIR drop (dB8). These are more sensitive to 6 m strips than 20 m SWIR [inference: a 6 m strip fills ~60% of a 10 m pixel but ~30% of a 20 m one].
  2. Threshold with Otsu per tile (see alert_burn_scars_fullread.md §3).
  3. Thin the burnt mask to 1-pixel centrelines.
  4. Keep connected parts with length ≥300 m, mean width ≤3 pixels at 10 m, and elongation (length / √area) ≥10.
  5. Snap them to OSM tracks and roads, and to compartment boundaries if MPFD supplies them.
  6. Stack the years. A centreline found in ≥3 of 9 years is a **permanent fire line**. Found in a given year means **burnt/maintained that year**.
- **Check:** the total length should come out at the order of 1,000–2,000 km (A3, A6). Validate against the geotagged FFPM/CAMPA photos (A2) or a GPS walk of 5–10 km with a beat guard.
- **Features (thread 1):** `dist_fireline_m`, `fireline_km_per_km2` (cell), `fireline_burnt_this_season` (fraction of the cell's line length burnt before 20 Feb), and beat-level `grid_completeness` (fraction of permanent lines burnt this year, after B2).
- [inference] Expected gain: small for "where tomorrow", because lines remove only ~1% of a cell's fuel. Larger for thread 2/4: lines bound scars and set spread barriers. It is also useful for thread 5, since lines are the walking routes staff use.
- **Spread model (thread 4):** non-burnable strips 6 m or 12 m wide where the line was burnt or cleared that year. Treat unmaintained lines as normal fuel. Compare simulated and observed scar edges along lines.

### D2. Label corrections for controlled and fire-line burns (thread 2, which feeds thread 1)
- **Rule set** [inference, assembled from A2, A5, A7, C and field_alert_systems.md]. Mark a scar or VIIRS cluster `probable_managed` if it meets all four conditions:
  1. the date is 1 Nov–20 Feb, AND
  2. it is elongated (elongation ≥10) or ≥70% of it lies within 20 m of a permanent fire line, road or compartment edge, AND
  3. it has no night detection, AND
  4. the cluster's FRP is ≤ the median.

  Mark it `probable_managed_patch` if it is a compact patch in grassland or along a village edge in Dec–Jan with no night detection. That pattern fits Kanha-style early grassland burning.
- **Use:**
  - (a) Do **not** count `probable_managed` as a wildfire positive in the 2-day model's training labels. Drop it, or train with a separate class.
  - (b) Do keep it as a *fuel-removed* input (D3).
  - (c) In scoring, report recall with and without these labels.
- **Check:** Uttarakhand found 12–19% of winter alerts were department burns (field_alert_systems_fullread.md). If our rule tags far more or far less than ~15% of Nov–Feb detections, tune it.
- **Field system:** add a planned-burn and fire-line register, as already proposed in field_alert_systems.md. Pre-fill it with the D1 network so guards tick lines as "cut", "burnt" and the date, instead of drawing them.

### D3. Early-season fuel removal (thread 1, threads 3/4)
- `early_burnt_frac_beat` and `early_burnt_frac_cell`: the share of area burnt from 1 Nov to the prediction date by managed or early fires.
- `days_since_burn_this_season` (cell).
- First test the B1 leverage regression. Add the feature only if the beat-year slope is negative with a confidence interval excluding 0. Expect a weak effect, because litter keeps falling (leaf_fall_phenology.md).

### D4. Watchtowers and watchers (threads 1, 2, 5)
- **Tower locations:** ask the DFO (NAPFF §6.2 requires an inventory). Meanwhile search OSM (`man_made=tower` + `tower:type=observation`), use Google Earth VHR, and check the TCP.
- **Viewshed:** Copernicus GLO-30 DEM. Observer height 15 m and 25 m (Indian towers are 25–30 m). Target height = canopy (~15 m) + smoke (10–30 m). Radius 3 km and 6 km (Kudremukh). Compute with `gdal_viewshed` or GRASS `r.viewshed`.
- **Features:** `visible_from_tower` (any), `n_towers_visible`, `dist_tower_km`, plus a `tower_staffed` calendar flag once watcher dates are known.
- **Test:** do in-viewshed fires have smaller per-alert scar area or shorter report lag? Use matched cells. This is a first outcome test (B4).
- **Field system:** record "who detected first" (already proposed) together with the tower ID. That turns each report into a tower-performance data point.

### D5. Calendar and management flags (thread 1)
`fireline_burning_window` (Nov–15/20 Feb), `watchers_on` (45–60-day window, dates to confirm), `tendu_pruning` (Feb–Mar, from A5), and `post_TR_notification` (from Dec 2024: new tiger-reserve staffing and the TCP). [inference] Expected gain: small. They mainly guard against the model learning management artefacts as fire risk.

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| MP FFPM APO sanction orders (fire-line km, watchers, village incentives) | https://moef.gov.in/uploads/2019/08/1MP2019-20.pdf and sibling URLs in A2 | state, by item | 2019-20 onward | Govt. of India public document | Direct PDF |
| MP State CAMPA APO approval 2025-26 | https://nationalcampa.nic.in/dashboard/SanctionPDF/682d7bd5ac4b5.pdf | state, by item | 2025-26 (other years on the same dashboard) | public document | Direct PDF |
| NTCA Forest Fire Audit Protocol | https://ntca.gov.in/wp-content/uploads/2026/05/annexure-pdf.pdf | per tiger reserve | 2026 season | public document | Direct PDF |
| NAPFF 2018 | https://www.moef.gov.in/uploads/pdf-uploads/pdf_68a4157b8b3d38.38401489.pdf | national | 2018 | public document | Direct PDF |
| World Bank/MoEFCC 2018 report | https://documents1.worldbank.org/curated/en/333281529301442991/pdf/127284-Forest-Fire-Prevention-Management-8Oct2018.pdf | state | 2003–2017 data | CC BY 3.0 IGO | Direct PDF |
| WII MEE 2014 tiger reserves | https://www.wii.gov.in/uploads/media/pdf/mee/MEE_TR_site_evaluation_report_2014.pdf | per reserve | 2014 | public document | Direct PDF |
| MP Fire Compendium 2016–2022 | https://mpforest.gov.in/publicdomain/atlas/FireCompendium.pdf | division | 2016–2022 | MPFD | **Blocked from here.** Download from India |
| Ratapani TCP, Raisen/Obaidullaganj working plans, MP SAPFF, fire-line/compartment layers, tower inventory, controlled-burn register, FFPM geotagged photos, DBT watcher lists | DFO Obaidullaganj / MPFD IT cell; MPFD ArcGIS server (open_datasets.md) | line/point/polygon | various | departmental | Request letter citing NAPFF §6.2–6.4 |
| Sentinel-2 L2A | Copernicus / GEE `COPERNICUS/S2_SR_HARMONIZED` | 10/20 m | 2017– | free (Copernicus) | GEE or CDSE |
| Copernicus DEM GLO-30 | https://dataspace.copernicus.eu (also GEE `COPERNICUS/DEM/GLO30`) | 30 m | static | free licence | GEE/download |
| OpenStreetMap towers and tracks | https://overpass-turbo.eu | vector | current | ODbL | Overpass query |
| VIIRS S-NPP (ours) | `ratapani/viirs_snpp_2013_2024.parquet` | 375 m | 2013–2024 | NASA open | local |
| NAFI fire scars (method reference) | https://www.firenorth.org.au/nafi3/ ; TERN record above | 250 m MODIS; S2 HiRes | 2000– | TERN-hosted (check, likely CC BY 4.0) | download |
| WA DBCA Fire History (burn-type attribute) | data.wa.gov.au, "DBCA-060" | polygons | 1937– | check (likely CC BY 4.0) | download |
| Arnhem Land fire history data (Price 2012 inputs) | via Darwin Centre for Bushfire Research / NAFI | Landsat polygons | 1990–2009 | check | request |
| MapBiomas Fogo (Brazil, monthly burnt area) | https://plataforma.brasil.mapbiomas.org | 30 m | 1985– | check (MapBiomas open) | GEE/download |

---

## Reading status
- **FULL (13):** NAPFF 2018; MP FFPM orders (2019-20 General, 2019-20 TSP, 2020-21 SCSP, 2024-25 ad-hoc); MP CAMPA 2025-26 (fire section); NTCA audit protocol 2026; Franke et al. 2024; Price et al. 2012; Kudremukh viewshed paper; NIDM 2013; Hitavada Nagpur 2020; Chandigarh SAPFF 2026.
- **PARTIAL (5):** World Bank 2018 (all relevant chapters); WII MEE 2014 (keyword sections); Price et al. 2015; Antalya towers 2023; NAFI metadata.
- **ABSTRACT ONLY / search-level:** Indonesia payment RCT; Price 2012 Forest Science; Melghat Sipna prizes; Bandipur inquiry; Kanha early burning; Uttarakhand NGT amicus; JTFE 2022 towers; Isparta/Ilgaz/Plinius tower studies.
- **Not reachable:** MP Fire Compendium, MP RTI manual, AP fire-tracing circular, TN fire guidebook, Maharashtra TR management plan, NDRF forest-fire manual, Pench TCP buffer chapters.

---

## Ranked action list (gain and effort are my estimates [inference])

| # | Action | Thread | Gain | Effort |
|---|---|---|---|---|
| 1 | **Label clean-up:** tag Nov–Feb managed burns (straight lines along tracks, daytime only, low FRP; D2). Retrain the 2-day model with them removed, or as a separate class, and report recall both ways. | 2 → 1 | Medium: cleaner positives; ~5–15% of winter labels affected; also removes a false "near road and village" signal | Low (1–2 days on existing scars and VIIRS) |
| 2 | **Fire-line detector from Nov–Feb Sentinel-2 dNBR** (D1). Build the permanent network, the yearly "burnt this winter" status, and distance/density features. Check it against the expected ~1,000–2,000 km. | 2, 4, 1, 5 | Medium for scars and spread (barriers, scar edges); small for 2-day | Medium (3–5 days in GEE) |
| 3 | **Data request letter to DFO Obaidullaganj / MPFD IT cell / Ratapani TR**, citing NAPFF §6.2–6.4 and the NTCA audit items. Ask for: TCP or draft TCP, fire-line and compartment layer, tower list, controlled-burn register, FFPM/CAMPA geotagged before/after photos, watcher DBT dates by village, funded incentive villages, MP SAPFF and Fire Compendium. | all | High if granted: ground truth for #1, #2, #5, #6 | Low effort, slow turnaround |
| 4 | **Leverage regression** (B1/B2 method): beat-year Mar–May burnt fraction against Nov–Feb burnt fraction, with year effects and a spatial lag. Decide whether early-burn features belong in the model. | 1 (season), 4 | Medium (answers "does early burning help here?"; cheap feature if yes) | Low (1 day) |
| 5 | **Watchtower viewshed** (D4) from GLO-30 once tower points are in hand, plus the first outcome test (scar size and report lag inside vs outside the viewshed). | 5, 2, 1 | Medium for field-system design and a publishable result; small for prediction | Low–medium (1–2 days after locations) |
| 6 | **Field-system fields:** a fire-line maintenance tick-list pre-filled from #2, a planned-burn register, tower ID in "who detected first", watcher roster dates, and log export in NTCA D1 / M-STrIPES fields. | 5 | Medium (audit-aligned, so more likely to be used) | Low |
| 7 | **Calendar flags** (`fireline_burning_window`, `watchers_on`, `tendu_pruning`, `post_TR`). | 1 | Small | Very low once dates are confirmed |
| 8 | **Village-incentive difference-in-differences** once the paid-village list is obtained (matched pairs, 2020 dummy). | 1 (analysis), 5 | Small–uncertain (Indonesia null) | Medium |
| 9 | **Grid-completeness metric** (B2: gaps reduce leverage). Test against mean scar size by beat. | 2, 4 | Small–medium | Low after #2 |
