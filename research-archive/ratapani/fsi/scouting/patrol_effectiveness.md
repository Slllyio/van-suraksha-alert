# Do patrols, detection and early response reduce human-caused fire starts or burned area? Evidence, effect sizes and what it means for the 2027 patrol pilot (scouting round 14, topic "patrol", 16 Oct 2026)

Scope: the published evidence on whether patrol presence deters people from lighting fires, whether faster detection and response shrinks fires, and whether patrols simply push fires elsewhere. Each source is labelled FULL, PARTIAL or ABSTRACT ONLY. My own reasoning is marked [inference]. Sources already covered in other notes are only cross-referenced: Slough et al. 2021 (Peru monitors), Cappello 2022, Moffette 2021 and Assunção 2023 (`field_alert_systems_fullread.md` §7-9); watchtower viewsheds and the Indonesian village-payment trial abstract (`fire_management_practice.md` B4-B5); MP fire-watcher budgets (`fire_management_practice.md` A2-A3).

Pilot facts used below (PROTOCOL.md §0 only): three arms (fixed 5 per beat, calendar, forecast). Primary outcome = verified new fire starts found per 100 ignition-stream person-hours. H1 = flexible vs fixed. 94 beats in blocks of 3, one season (15 Feb-15 Jun 2027), with the model locked on 1 Feb 2027.

## Headline findings

1. **The pilot's primary outcome measures detection productivity, not deterrence.** The conservation-enforcement literature (Dobson et al. 2019) shows that counts found by patrols cannot reveal deterrence, because effort and detection are tangled. We have something most patrol studies lack: **an outcome that does not depend on patrols at all**, namely satellite-dated first-day fires per beat. It should be added as a pre-registered secondary "deterrence" endpoint before the 1 Feb 2027 lock.
2. **Our own power check (computed today): one season can only see a large deterrent effect.**
   - Data: 3,483 VIIRS/scar first-day fires in 15 Feb-15 Jun, 2017-26, with 3,435 matched to the 94 pilot beats. That is 3.65 per beat-season on average (median 3), and 31% of beat-seasons have none. Beat counts correlate year to year at r = 0.63-0.83.
   - With no treatment at all, the locked arm allocation gives flexible/fixed baseline-adjusted rate ratios between **0.84 and 1.18** across 2019-26.
   - Simulated deterrence (removing a share of starts in the flexible arms, block-permutation test, one-sided 5%) gives power of **0.16 for 10%, 0.50 for 20%, 0.84 for 30% and 1.00 for 40%**.
   - So only a fall of about 30% or more in starts would show up. The literature suggests presence-only deterrence is smaller than that (points 3-4).
3. **The best-identified effects of "guardianship" on human fire starts come with enforcement, not presence alone.**
   - Galicia: arrests cut later intentional fires, with no displacement. Elasticities run from −0.29 to −0.93 in the short run and −0.46 to −1.20 in the long run. That means 1% more arrests gives about 0.3-1.2% fewer intentional fires.
   - California: sworn officers per capita reduce arson.
   - US tribal lands: prevention programmes are linked to 19-93% fewer ignitions.
   - Indonesia: in a 275-village randomised trial, villages **raised their patrol frequency and formed more fire task forces**, yet fire was unchanged: 72% of treated villages had fire against 71% of controls (MDE about 16 percentage points).
4. **Effect sizes for place-based presence are modest.**
   - Hot-spot policing meta-analysis (65 studies, 78 tests): standardised mean difference about **0.10-0.20**.
   - Philadelphia foot patrol RCT: **−23%** violent crime, and only in the top 40% of hotspots. The dose was about 80 person-hours per week per 1.3 street-miles.
   - The best dose per visit is **10-15 minutes** (Koper 1995; Sacramento RCT).
   - Brazil's Federal Brigades: **−35% net** in active fires in indigenous lands (−22.7% inside vs +12.3% outside). The effect was **−42% net at 11,043 ha per brigade member (Cerrado) and nothing significant at 81,524 ha per member (Amazon)**. This is the nearest thing to a staff-density threshold in fire.
5. **Displacement is usually smaller than the direct gain, and diffusion of benefit is slightly more common.**
   - Galicia arrests: no displacement.
   - Hot-spot meta-analysis: diffusion over displacement, d = 0.06-0.11.
   - Philadelphia: weighted displacement quotient −0.41. Some crime moved, but less than was prevented, for a net 53 crimes avoided.
   - For our pilot [inference]: the arms sit side by side in a block design. Any displacement from flexible to fixed beats would **inflate** the H1 contrast, and any diffusion would **shrink** it. Measure both with a buffer statistic on beat adjacency.
6. **Early response: the data say "faster" helps, but no study isolates arrival time for low-intensity litter fires.**
   - Bandipur TR: response time fell from 45 to under 18 minutes, alongside −73% fire incidents and −85% burned area against 2015-19 (a baseline that includes the 2019 mega-fire).
   - Similipal: villages with Community Forest Rights put fires out in 2-4 h, against "at least double" for the department.
   - Ontario: fire size when the first crew starts work is the strongest predictor of later growth (25% of fires that grew were already ≥3 ha at that point, against 3% of fires that did not grow). Crews were sent harder to fires expected to grow, which hides the effect of resources.
   - Our randomisation can break that reverse causality: the arm acts as an instrument for discovery delay.

## Part A. Deterrence and law enforcement against human-set fires

### A1. Prestemon, Butry, Chas-Amil & Touza 2019, "Net reductions or spatiotemporal displacement of intentional wildfires in response to arrests? Evidence from Spain", *IJWF* 28:397-411. https://doi.org/10.1071/WF18234. Accepted manuscript: https://eprints.whiterose.ac.uk/id/eprint/145139/. **FULL**

**Data and model:**
- Galicia, 1999-2014, 108,527 fires burning 431,956 ha, of which 81% were intentional.
- 313 municipalities. The models use the 113 municipalities with ≥200 intentional fires.
- Daily counts are modelled with negative binomial models (fixed or random effects, plus pooled and zero-inflated variants) and AR(1).
- Arrests (by the Guardia Civil and local police) enter as running sums over t-1..t-365 and t-366..t-545. They are counted in the municipality and in rings at 10, 15 and 25 km.

**Results:**
- Every arrest lag and every ring is negative and significant at α ≤ 0.01. Arrests therefore **reduce** fires in neighbouring areas; they do not displace them.
- **Arrest elasticities, total intentional fires:**
  - short run −0.93 (FE) and −0.92 (RE), and −0.29 to −0.51 with the alternative estimators;
  - long run −1.20 and −1.18, and −0.46 to −0.73.
- Agricultural fires respond more (FE and RE: −1.68 short run, −2.25 long run).
- Fire on day t-1 adds 0.22 (log scale) to day t.
- Saturdays, Sundays and holidays have significantly more intentional fires.
- Fires peak in Feb-Apr.
- Election periods add about 3-8% to intentional fires, with a spike on the "silence day" before the vote.

**Concrete action for us:**
- **Thread 5 (pilot):** the deterrence that works in Galicia comes from enforcement people can see and hear about (arrests), over ≥1 year and ≥25 km. A one-season, presence-only contrast between neighbouring beats is the weakest form of guardianship [inference].
  - Log every **visible enforcement event**: warnings, seizures, FIRs and village meetings, each with date and beat.
  - Report them per arm as a "guardianship dose".
  - Pre-register that a deterrence effect, if any, is expected mainly where these events cluster.
- **Thread 1 (2-day model):**
  - Add `n_firs_or_offence_cases_last_365d_within_10km` if the range offices' offence registers (POR/FIR logs) can be digitised for 2017-26.
  - Expected effect: small but signed. Effort: medium (paper records).

### A2. Prestemon, Abt, Butry, Scranton et al. 2012, JFSP final report 09-1-9-2, "A Fire Prevention Effectiveness Assessment for Multiple Ownerships" (the basis of Abt et al. 2015, *IJWF* 24:749-762). https://www.bia.gov/sites/default/files/dup/assets/public/pdf/idc-021761.pdf. **FULL** (report). The journal paper itself is ABSTRACT ONLY.

**Data and model:**
- 19 Bureau of Indian Affairs units, monthly panel 1996-2009.
- Prevention programmes started at different times on different units, none before 2005.
- The treatment is a 0/1 indicator for a programme being present.
- Fixed effects for year, month and unit, plus weather and fire history.
- A **control function** corrects for the simultaneity between effort and fires.

**Results:**
- Fewer ignitions for every human cause: **2-128 fewer per month per unit, or 19% to 93%**.
- The largest effects were on campfire escapes, arson and child-set fires. Smoking, equipment and miscellaneous fires showed little effect.
- The authors could not separate individual activities (education, engineering, enforcement) because the activity records were inconsistent.

**Concrete action for us:**
- **Thread 5:** this is the clearest warning that effort data decide whether an evaluation succeeds. The pilot's person-hour logs (protocol §0.3) are the right fix.
- Add one record per day per beat: **any non-inspection prevention activity**, such as village meetings, announcements or controlled burning, so that prevention is not confused with patrol.
- Effort: low. Gain: makes any later cost-per-fire-avoided figure possible.
- [inference] The staggered-start design is a model for a **multi-year roll-out**. If the forecast arm is adopted range by range after 2027, stagger it by range and analyse it as a staggered difference-in-differences with satellite first-day fires as the outcome.

### A3. Prestemon & Butry 2010, "Wildland arson: a research assessment", USDA FS GTR PNW-802 vol. 2, pp. 271-283. https://www.fs.usda.gov/pnw/pubs/gtr802/Vol2/pnw_gtr802_prestemon02.pdf. **FULL**. Also Prestemon & Butry, "Wildland arson management" (book chapter), https://research.fs.usda.gov/download/treesearch/32961.pdf. **PARTIAL** (findings sections).

- **California, daily Poisson AR(p) models (4 national forests, 1994-2002):**
  - Arson clusters in time, with AR(1) = 0.26-0.49 and significant lags up to AR(5).
  - Lagged law-enforcement officers per capita has mixed signs (−17.09 Cleveland, +13.67 Sierra) at 15% significance.
- **California, annual fixed-effects panel (18 forests, 1993-2002):** sworn officers per capita at t-1 = **−655 (SE 195)**, p < 0.01.
- **Florida:** arson clusters for up to **11 days** within a census tract and its neighbours, and law enforcement is negatively related to arson.
- If Florida retail wages in 2001 had been at their 1982 level, arson ignitions per capita would have been 93% higher.
- The authors also say it "may not be clear that reducing wildland arson ignitions results in large-scale and long-run reductions in the amount of area burned."

**Concrete action for us:**
- **Thread 5 analysis:** report deterrence on **counts of starts** and on **scar area** separately. Fewer starts need not mean less area. When fires are fewer, those left can burn more cells, especially in high-fuel beats [inference].
- **Thread 1:** temporal contagion of 5-11 days matches our near-repeat findings (`fire_jumps_and_nearby_starts.md`).
  - This is also why 26% of first-day fires fall inside the pilot's excluded zone (1.5 km / 3 days).
  - Pre-register a sensitivity analysis that widens the window to **7-11 days** for the "excluded zone" share, as the arson literature suggests.

### A4. Dobson, Milner-Gulland, Beale, Ibbett & Keane 2019, "Detecting deterrence from patrol data", *Conservation Biology* 33:665-675. https://doi.org/10.1111/cobi.13222. OA: https://eprints.whiterose.ac.uk/id/eprint/135800/. **FULL**

**Method:** a simulation of offences, detection and patrol effort under flat, rising and falling effort, with and without outside changes in offending. CPUE = offences detected per unit of patrol effort.

**Results:**
- The usual **CPUE-against-effort** plot is **not a reliable** sign of deterrence.
- **ΔCPUE against Δeffort** (first differences) identifies deterrence reliably, provided the **time lag between patrol and offender response is roughly known** and detection does not saturate.
- Do not pool offence types whose signs persist for different lengths of time.

Also cited in the paper:
- Philadelphia foot-patrol RCT: the effect was restricted to the top 40% of baseline-crime areas.
- Many patrol-effort studies found no impact.
- Evidence for displacement of every kind is limited.

**Concrete action for us (thread 5):**
- (a) **Never read "starts found per hour" as deterrence.** In the pilot write-up, describe it as detection yield. The protocol already avoids claiming deterrence; keep it that way.
- (b) **Add an outcome that does not depend on patrols:** satellite first-day fires per beat (the ignition-point pipeline, `code/ignition/`, locked version). Analyse it with the same block-randomisation inference (protocol §0.5), offset by the beat's 2017-26 mean.
- (c) Pre-specify the **lag window** for residual deterrence: days 1-7 after an inspection of a beat. Run the ΔCPUE-Δeffort plot weekly per arm as a descriptive check.
- (d) Do not pool fire types with different satellite persistence. Score "burning now" and "older burn" detections separately, which the protocol table already allows.

### A5. Edwards, Falcon, Hadiwidjaja, Higgins, Naylor & Sumarto 2020, "Fight fire with finance: a randomized field experiment to curtail land-clearing fire in Indonesia", TNP2K WP 55-e/2020. https://novafrica.org/wp-content/uploads/2021/03/2021.04.14_Ryan-Edwards.pdf. **FULL** (main text: design, behaviour, fire results and power). Published version: Falcon et al. 2022, *Agriculture* 12:1040, https://doi.org/10.3390/agriculture12071040, ABSTRACT ONLY (the MDPI PDF was blocked).

**Design:**
- 275 fire-prone villages in 4 West Kalimantan districts: 75 treated, 200 controls (the controls oversampled for power), 2018 dry season.
- Treatment had three parts:
  - training and facilitation;
  - Rp 10 million (~US$750) up front;
  - **Rp 150 million (~US$10,800)** if MODIS detected no hotspot inside the village plus a 500 m buffer from 1 July to 31 Oct.
- Leniency rules: confidence <50 dropped, pre-registered swidden burns excluded, and villages with ≤3 hotspots checked by hand on imagery.

**Results:**
- **Behaviour:** treated villages were **20% more likely to have a fire-prevention task force**. They had more task-force groups and members, and **patrolled more often**. They were no more likely to call in Manggala Agni.
- **Fire:**
  - **72% of treated vs 71% of control villages had hotspots**, with about 5 hotspots per village in both groups. A change of 2 or more hotspots can be ruled out.
  - Results hold with VIIRS and other confidence filters.
  - The only significant effect came in **July, the first month**, and then faded.
  - Days to first hotspot: mean 47 and median 42 for controls; 47 and 43 for treated villages.
  - 21 of 75 villages won the payment.
- **Power:** MDE about 16 percentage points on the probability of fire (baseline about 70%), or a 40% change in hotspot count.
- **Explanations:** the payment was too small against the value of land (land NPV $3,835-9,630 per ha against $614-994 in carbon credits), and collective action failed. Leadership drove the few successes.

**Concrete action for us:**
- **Thread 5:** this is a randomised test showing **more patrolling without fewer fires**. Plan the pilot write-up so that a null on deterrence is expected and publishable. The pilot's case rests on detection yield (H1), and the deterrence endpoint is exploratory.
- **Thread 5:** copy the **monthly effect breakdown**. Report the deterrence endpoint by fortnight. Edwards found the effect only in month 1, which is novelty decay.
- **Thread 1 / FSI:** copy the leniency rules (confidence filter, buffer, pre-registered managed burns, manual image check below 3 detections) for any village-level outcome built from VIIRS.

### A6. Watts, Tacconi, Hapsari, Irawan, Sloan & Widiastomo 2019, "Incentivizing compliance: evaluating the effectiveness of targeted village incentives for reducing burning in Indonesia", *Forest Policy and Economics* 108:101956. https://doi.org/10.1016/j.forpol.2019.101956. OA via the ANU repository. **FULL**

**Design:** APRIL's Fire Free Village Programme, Riau, launched 28 July 2015. Rewards: IDR 100 million if no land burned, IDR 50 million if <2 ha burned, nothing above 2 ha. Also a village crew leader, awareness work and farming support.

**Results:**
- 6 programme and 6 non-programme villages, compared with hotspots and burn scars for 2013-17.
- In the 2015 El Niño year, programme villages had **40% fewer fires and the others 23% more**.
- Fire fell almost to zero everywhere after 2016.
- In interviews:
  - 50% of programme villages cited the 2015 Presidential Instruction;
  - 58% cited the 2014 police ban (Maklumat Kapolda);
  - 50% cited fear of prosecution;
  - 50% cited the programme itself.
- The authors' conclusion: incentives worked mainly as a channel for **making the law and its enforcement known**.

**Concrete action for us:** the evidence again points to **perceived enforcement**.
- **Thread 5:** record whether each beat had a **pre-season awareness meeting** announcing fines or FIRs (yes/no, date), so the flexible-vs-fixed contrast is not confounded with uneven awareness work.
- Effort: low.

### A7. Jack, Jayachandran, Kala & Pande 2023, "Money (not) to burn: payments for ecosystem services to reduce crop residue burning", Princeton GCEPS WP 307. https://gceps.princeton.edu/wp-content/uploads/2023/03/wp307_Jayachandran-et-al_money_not_to_burn_23mar.pdf. Published in *AER: Insights*. **PARTIAL** (design, monitoring and main results read)

**Design:** Punjab RCT. Payment for not burning, with part paid up front versus all paid after verification.

**Results:**
- Upfront contracts raised compliance by **8-12 percentage points** (about 10 pp).
- Satellite-measured burning showed the same.
- Standard pay-after contracts were **inframarginal**: they paid people who would not have burned anyway.

**Measurement lessons:**
- **720 spot checks** were made on a random field for 50% of farmers.
- Spot checks not timed to harvest only tell you about burning in the few days before the visit.
- Monitoring visits had to be **requested by the farmer** at the right moment.
- Burning was mapped from PlanetScope (3 m) and Sentinel-2 (20 m). The authors call MODIS and VIIRS "inappropriate" for small fields.
- Balanced-accuracy classifiers were trained on visit labels.
- Monitoring cost was about Rs 300 per field.

**Concrete action for us:**
- **Thread 5:** an inspection that finds "no fire" says nothing beyond a few days. Treat "no fire found" as **censored information**, not as a confirmed negative, in any cell-level analysis.
- **Thread 2:** the pilot's photo-and-GPS inspections are labelled ground truth for small scars. Store them as training labels for the scar classifier: positives from "older burn" and "burning now", negatives only from same-day "no burn" visits.

## Part B. Brigades, community fire programmes and watchers (fire-specific programme evaluations)

### B1. Falleiro et al. 2026, "Wildfire protection in indigenous lands of Brazil: the role of fire brigades programs", *Humanities and Social Sciences Communications* 13:87. https://doi.org/10.1057/s41599-025-06390-7. **FULL**

**Design:**
- 42 indigenous lands, 25.36 million ha.
- Before-after-control-impact comparison: 2003-12 (before the Federal Brigades, BRIFs) against 2014-23 (after), with 2013 as a transition year.
- Active fires (INPE reference satellite) counted only in the wildfire season, to leave out early prescribed burns.
- Chi-square tests. Pre-period counts were balanced (p = 0.60-0.77).

**Results (Table 2):**

| Biome | ha per brigade member | BRIF lands, 2003-12 → 2014-23 | Lands without BRIF | Net |
|---|---|---|---|---|
| Cerrado + Amazon | 46,283 | 32,337 → 25,005 (**−22.7%**) | 32,264 → 36,234 (+12.3%) | −35% |
| Cerrado | **11,043** | 23,353 → 16,190 (**−30.7%**) | +11.3% | −42% |
| Amazon | **81,524** | 8,984 → 8,815 (−1.9%, n.s.) | +14.9% | about −17% |

- Earlier, the Critical Municipalities brigade programme saw +5.7% fires, against −20.7% in the same areas under BRIF.
- **2023 cost:** 100 brigades and 2,093 members, USD 17.8 million, or **USD 1.02 per ha**. Hiring for **6 months a year** cost USD 6.76 million, and PPE USD 1,284.60 per member.
- The authors credit **prescribed burning (early-season fuel management)** as the most important activity in the Cerrado, more than suppression.

**Concrete action for us:**
- **Thread 5 (staffing scale):**
  - The Cerrado effect came with **1 seasonal member per 110 km²**. The Amazon had no effect at 1 per 815 km².
  - [inference] Ratapani's grid covers about 903 km² (3,614 cells of 25 ha) in 94 beats (about 9.6 km² per beat).
  - Express each arm's budget as **person-hours per km² per week** so the pilot can be placed on this scale.
  - Report alongside the result that BRIF's gain came with early burning, which the pilot does not change.
- **Thread 1:** copy the design: count fires in the wildfire season only, with prescribed burns removed. Our managed-burn flag (`events.parquet` `managed_flag`) already does this.

### B2. Bandipur Tiger Reserve, ADB Institute case study 2025-9 (Dec 2025), "Community-based forest fire prevention and management in Bandipur Tiger Reserve, Karnataka, India". https://www.adb.org/sites/default/files/publication/1108101/adbi-community-based-forest-fire-prevention-and-management-bandipur-tiger-reserve-karnataka-india.pdf. **FULL**

**Setting and before:**
- 1,036.2 km² (872.2 core and 164.0 buffer), dry deciduous with Lantana. 149 villages and about 138,000 people.
- The 2019 fire burned 3,160 ha.
- Before the programme:
  - about 145 guards and rangers;
  - 15 watchtowers;
  - **response 45-60 min**;
  - fire lines covering 2,807 of the 3,565 km needed;
  - 40% of the reserve >5 km from a road;
  - radio coverage over 65% of the area.

**Programme:**
- Each village ran a static and a mobile camp of **8-12 tribal fire watchers**.
- Now **540 trained watchers**, 12 fire tenders, 32 quick-response vehicles and 54 blowers.
- 19 towers renovated and 10 added, seeing about 85% of the area.
- A "Bandipur Fire Watch" app with >600 users.
- Stipends of about ₹5.03 million a year (Jan-May).
- Roll-out from 5 pilot villages (2021-22) to all 100 villages (2023-24).

**Reported results (2020-23 against 2015-19):**
- **Fire incidents −73%, burned area −85%, response time 45 → under 18 min.**
- There is no control area.
- [inference] The baseline includes the 2019 mega-fire, so regression to the mean inflates the change.

**Concrete action for us:**
- **Thread 5 (density benchmark):** 540 watchers per 1,036 km² is about **0.52 per km²** in season. Compute the pilot's person-hours per km² per arm for comparison.
- Quote Bandipur only as an upper bound with no control.
- **Thread 5 outcome:** Bandipur's measurable gain was response time. The pilot's time-to-discovery (protocol §0.6) is the matching measure. Keep it as a named secondary outcome with a pre-set target (for example a median under 24 h from estimated ignition to discovery for confirmed starts) [inference].

### B3. Mongabay India, 7 Apr 2022, "One year of Similipal forest fire: the hits and misses". https://india.mongabay.com/2022/04/one-year-of-similipal-forest-fire-the-hits-and-misses/. **FULL**

**2021:**
- The fire burned for about 10 days over about one third of the tiger reserve.
- It became public only about a week after it was first reported.
- The state's claim on 5 March that the fire was under control was contradicted by NASA satellite images.

**2022:**
- More than 500 fire blowers, **320 fire watchers** and 720 regular protection assistants.
- 130 vulnerable villages trained, against about 45 villages inside and hundreds on the edge.
- A 24x7 control room and drones.
- An independent survey by the NGO Vasundhara: **Community Forest Rights villages put fires out in 2-4 h, and the administration took "at least double"**.
- Villages fine non-responders up to ₹5,000.

**Concrete action for us:**
- **Thread 5:** this is evidence that **local responders cut time-to-control by at least half**.
- If village volunteers are used in 2027, put them in the **response stream equally in all arms** (as the protocol already does for response visits). That way they cannot confound H1.
- Log their arrival times with the same person-hour rules (§0.3).

### B4. Other community-programme evidence (weak designs)

- **Nepal, Tachibana & Adhikari 2009, *Land Economics* 85:107-131.** ABSTRACT ONLY. 101 randomly sampled Middle Hills forests. Forest condition improved through **reduced fire occurrence** under user groups, with self-selection into official support controlled for. No fire numbers in the abstract.
- **Nepal, Salyan district MODIS 2001-17.** ABSTRACT ONLY. Says community forest user group (CFUG) fire practices were effective, but has no comparison group.
- **Nepal, Bagmati 2014-24 (J. Forest and Livelihood).** ABSTRACT ONLY. 92.87% of fires fall in the pre-monsoon season, and the paper says CFUG effectiveness is limited by resources. Only 67 of about 19,000 CFUGs are equipped and trained for firefighting (news figure).
- **Indonesia MPA (Masyarakat Peduli Api).** No quantitative evaluation found. The Indonesian studies (Bali, Papua Barat, Ogan Komering Ilir, Palangka Raya) are perception or SWOT studies.
  - The OKI study describes **Manggala Agni independent patrols (5 people for 10 days) and integrated patrols with MPA (30 days)**, with about 99% of fires human-caused. ABSTRACT ONLY.
  - The Edwards trial (A5) is the only randomised evidence, and patrols there did not change fire.
- **India JFM / van suraksha samitis / fire watchers.** No controlled comparison found.
  - CAG Karnataka 2017 and parliamentary answers describe watchers (Feb-May) without any evaluation.
  - An Inderscience review says few of the about 62,900 forest protection committees function.
  - Nilgiri Biosphere Reserve (NRSC and Andhra University, Landsat 1973-2014) shows burnt area and fire frequency falling over 1989-2014, credited to JFM and department plans, with no counterfactual. ABSTRACT ONLY (Mongabay).
- **Ghana fire volunteer squads.** Only perception studies were found (Tain II, 438 respondents; Dormaa and Atebubu). ABSTRACT ONLY.
- **Portugal GNR patrols.** 210 mobile patrols a day in 2026, and 268 a day rising to 2,300 at high risk in 2023, with 230 lookout posts and 143 cameras. A Portuguese thesis (comum.rcaap.pt) finds **video surveillance detects few ignitions compared with other sources**. No causal estimate exists. ABSTRACT ONLY.
- **Spain, Galicia army "Centinela Gallego" patrols (since 2007).** Only Ministry of Defence activity counts exist (for example ">100 sightings" in 2020). No evaluation.

**Concrete action for us:** no published Indian evaluation exists, so **the pilot would be the first randomised evaluation of fire-watcher or patrol allocation in India** [inference]. Write it up as such, and register it (the AEA RCT registry or OSF) before 1 Feb 2027. Effort: low. Gain: credibility and a citable design.

## Part C. Place-based patrol presence: dose, effect size and displacement (crime and poaching analogues)

### C1. Braga, Turchan, Papachristos & Hureau 2019, "Hot spots policing of small geographic areas effects on crime", *Campbell Systematic Reviews* 15:e1046. https://doi.org/10.1002/cl2.1046 (PMC8356500). **PARTIAL** (full text read via Europe PMC: results, displacement and moderator sections)

**Coverage:** 65 studies with 78 tests (27 RCTs and 38 quasi-experiments).

**Crime effect (standardised mean difference d):**
- **0.197** using the largest effect per study and **0.104** using the smallest.
- Violent crime: d = 0.102 (44 studies).
- Problem-oriented approaches: 0.164.
- Stronger quasi-experiments: 0.158.

**Displacement and diffusion (40 tests):** diffusion beats displacement, d = **0.110** (largest) and **0.062** (smallest).

**Fidelity notes:**
- Dallas: time spent at hot spots rose "except for the last 2 weeks ... officer fatigue".
- Directed patrol reduced residents' trust in one RCT.

**Concrete action for us:**
- **Thread 5:** use d of about 0.1-0.2 as the **prior** for any presence-only deterrence. That prior is below the about 30% our one-season deterrence endpoint can detect (headline 2). State this in the pre-registration so a null is read correctly.
- **Fatigue:** track inspections per person-day by fortnight per arm. A fall in late May would mirror Dallas.

### C2. Ratcliffe, Taniguchi, Groff & Wood 2011, "The Philadelphia Foot Patrol Experiment: a randomized controlled trial of police patrol effectiveness in violent crime hotspots", *Criminology* 49:795-831. Full paper: https://liberalarts.acquiadev.temple.edu/sites/liberalarts/files/images/PFPE_full_paper.pdf. **FULL**

**Design:**
- 120 hotspots in a randomised block design (pairs): 60 targets, each averaging 14.7 intersections and 1.3 miles of street.
- Two officer pairs per target, working 10:00-18:00 or 18:00-02:00, Tuesday to Saturday.
- 12 weeks, giving a theoretical **57,600 patrol hours**. [inference] That is about **80 person-hours per target per week**.

**Results:**
- Violent crime **−23%** relative to controls (ratio 0.77), significant only in the top 40% of pre-treatment violence.
- Weighted displacement quotient = −0.41, a buffer displacement measure of 0.11. Some crime was displaced, but less than the benefit, for a **net 53 violent crimes prevented**.
- Pedestrian stops in target areas rose 64%, and the foot officers made 90% of that rise.
- Officers drifted outside their beats: foot officers produced 3.6% of activity in **control** areas.

**Concrete action for us (thread 5):**
1. **Effects only in the top 40%:** pre-register a subgroup analysis by past burning (the blocks are already sorted by `burned_cells_per_season_2017_24`). Expect any deterrence in the upper blocks only.
2. **Displacement statistic:** compute WDQ with beats as targets and **adjacent beats of the fixed arm as buffers**, using satellite first-day fires. Formula: WDQ = (B1/C1 − B0/C0) / (A1/C1 − A0/C0), where A = target, B = buffer, C = control and 0/1 = before/during. Use 2024-26 as "before".
3. **Contamination:** staff walk through other beats. Count inspections and position-log minutes **inside beats of another arm** (from §0.3 phone positions) and report them per arm, as Philadelphia did (3.6%).
4. **Dose:** the primary result came with about 80 person-hours per week on about 1.3 street-miles. A beat of about 9.6 km² is a far larger target [inference]. Report person-hours per km² per week per arm.

### C3. Koper 1995 (Minneapolis) and Telep, Mitchell & Weisburd 2014 (Sacramento RCT). Sources: the Koper summary (https://www.iadlest.org/...KoperHotSpots.pdf, blocked) and the CrimeSolutions programme page (https://crimesolutions.ojp.gov/ratedprograms/crime-hot-spots-intervention-sacramento-calif). **ABSTRACT ONLY** for Koper; the CrimeSolutions page was read **FULL**.

**Koper 1995:**
- Residual deterrence rises with stop length up to **10-15 min** (peak 14-15 min), with diminishing returns after that.
- A 10-minute threshold is needed to beat a drive-through.

**Sacramento RCT:**
- 21 treatment and 21 control hot spots, 90 days.
- Visits of **12-16 min, once every 2 h**, in random order: 7,095 visits (about 79 a day; 223-559 per hot spot).
- Part 1 crime: treated hot spots −1.67 incidents against +1.24 for controls (significant).
- Property crime: −35.3% against +25.3%.
- No significant displacement into two-block catchments.

**Concrete action for us (thread 5):**
- Record **time on site per inspection** (cell entry to exit, already in §0.3).
- Pre-register an exploratory dose test: whether satellite first-day fires within 1 km in the next 1-7 days fall more after inspections longer than 15 min.
- [inference] For forest cells, the deterrent unit is probably "being seen near the village path or tendu/mahua routes", not cell coverage. Log whether people were met (number met, purpose) on each inspection.

### C4. Wildlife ranger-patrol analogues

- **Moore, Plumptre et al. 2021, "Optimal allocation of law enforcement patrol effort to mitigate poaching activities", *Ecological Applications* e2337, Nyungwe NP, Rwanda (about 1,019 km²).** ABSTRACT ONLY.
  - A 5% cut in poaching risk needs **622 patrol events (1 km² each) per year** (US$49,760).
  - A 50% cut needs **8,558** (US$684,640).
  - A 60% cut needs 15,560 (US$1.24 million).
  - The 2006-16 allocation achieved about 30% risk reduction, against about 50% for the optimal allocation on the same budget.
  - Data: Dryad doi:10.5061/dryad.4xgxd2583.
- **Moore et al. 2018, *J. Applied Ecology* 55:99-107 (Nyungwe).** ABSTRACT ONLY. Detected poaching fell by up to 57% where patrols increased at high-risk sites.
- **Hilborn et al. 2006, *Science* 314:1266 (Serengeti).** ABSTRACT ONLY. Patrol collapse after 1977 brought more poaching. Patrols since the mid-1980s ("10-20 patrols a day" against "≤60 a year") let wildlife recover. The authors relied on arrests per patrol as a catch-per-effort index, which Dobson (A4) shows is fragile.
- **Jachmann 2008, *Biol. Conserv.* 141:89-99 (Ghana, 9 protected areas).** ABSTRACT ONLY. Publishing staff performance raised patrol effort, and detected poaching fell in savanna sites but not forest sites. The effort unit is "effective patrol days" on foot away from roads.
- **Harvard thesis/paper, "On the Effect of Ranger Patrols on Deterring Poaching: A Bayesian Approach for Causal Inference Using Field Tests as an Instrument" (dash.harvard.edu/handle/1/37371767).** ABSTRACT ONLY (title and snippet; PDF not served). Rangers were sent to **randomly chosen sites in Uganda**, and those random visits were used as an instrument.

**Concrete action for us (thread 5):**
- [inference] Nyungwe implies about **8.4 one-km² patrol visits per km² per year** for a 50% cut in risk.
- In Ratapani's 15 Feb-15 Jun season (120 days), 94 beats × 5 inspections a day (the fixed arm) is about 56,000 inspections, or about **60 visits per km² per season** if spread over about 903 km². That is far above the Nyungwe level.
- So the pilot is not under-dosed for presence. The open question is **where and when**, which is what H1 tests.
- Copy the Harvard idea: **randomise a small share of the ignition-stream picks** (for example 1 of every 5 daily picks drawn at random from eligible cells in the beat's top 30% by dryness). This gives exogenous visits that can estimate residual deterrence. Compare satellite first-day fires within 1 km over the next 1-7 days for randomly visited against randomly not-visited eligible cells. It can also estimate the discovery-delay effect on scar size (D2).
  - Cost: about 20% of picks lose their ranking.
  - From the current dry run, about 20% of forecast picks would give up part of the forecast's ranking advantage [inference]. The lean model's top-5 recall gain over random is 31.8% vs 21.5%, so the expected loss in H1 power is small but should be re-run in `scripts/pilot_power.py` before the lock.

## Part D. Detection and early response: does arriving sooner shrink the fire?

### D1. Tremblay, Duchesne & Cumming 2018, "Survival analysis and classification methods for forest fire size", *PLoS ONE* 13:e0189860. https://doi.org/10.1371/journal.pone.0189860. **PARTIAL** (full text via Europe PMC; methods and results sections read)

**Data:** 889 lightning fires in Alberta. Detection methods: 216 by air, 488 by lookout tower, 185 unplanned. Initial attack by helicopter crews of 4-7 in 615 cases.

**Results:**
- 629 fires did not grow between the first crew's start of work and the "being held" stage; most of these ended below 1 ha.
- 260 fires did grow. Of those, **25% were already ≥3 ha when the crew started work, against 3%** of the fires that did not grow.
- The growth-probability model links growth to time of day of initial attack, log size at initial attack, Fire Weather Index (FWI) and response time.
- The effect of initial-attack method was not significant. The authors explain it by **reverse causality**: agencies send more resources to fires they expect to grow.

**Concrete action for us:**
- **Thread 4 (fire stopping) and thread 5:**
  - Fire-level analyses of "discovery delay → scar area" are confounded in the same way. Guards go first to fires that look big or are near roads.
  - Use the **arm** (randomised) or the randomised picks (C4) as the instrument: fires in flexible-arm beats should be discovered earlier. The arm-level difference in median scar area (v2 scars), divided by the arm-level difference in median discovery delay, gives a Wald estimate of hectares saved per hour of earlier discovery.
  - Inputs: v2 scar outlines (`fire-alert-scars/reference/v2_2026-10-16/`), the FSI method's ignition-time estimate, and discovery time.
  - Expected effect: small per fire. The 44% VIIRS miss rate means many fires are never seen by satellite before they go out [inference].
- **Thread 4:** add "size at first field contact" (estimated by the guard, or from the scar at the next clear image) as a predictor in the fire-stopping model, matching Tremblay's strongest variable.

### D2. Plucinski 2019, "Contain and control: wildfire suppression effectiveness at incidents and across landscapes", *Current Forestry Reports* 5:20-40 (doi:10.1007/s40725-019-00085-4), via CSIRO PyroPage 22 (Apr 2019). https://research.csiro.au/pyropage/ ... Issue-22. **FULL** (PyroPage, 2 pp). The review itself is ABSTRACT ONLY.

**Related abstracts:**
- Plucinski 2013, *IJWF* (Australian grassfires): escape is defined as ≥100 ha or ≥4 h to contain. The best predictors were **initial fire area and Grassland Fire Danger Index**; response time was weaker.
- Plucinski et al. 2012 (aircraft): initial attack (IA) success = contained within 8 h of detection. Aerial and ground response time, near-surface fuel hazard, wind and area at IA were the most important.
- Korkola et al. 2024, *IJWF* WF24104 (Ontario): 26,171 fires over 30 years and eight success definitions. The definition did not change model performance much.
- Alberta's IA standard: action before the fire passes 2 ha, and held by 10:00 the next day.

**Concrete action for us:**
- **Thread 4:** adopt a written **"held" definition for litter fires**, so that "stopping" can be scored from the field app. Example: no active edge at the next visit, and no VIIRS detection within 1 km on the next two passes [inference].
- Pre-register **response failure** (no visit before the fire passes X ha or Y h) separately from **containment failure**, as in the Arienti and Korkola definitions.

## Part E. Lessons for the pilot's outcome: measuring deterrence, not only detection

**E1. Our computed check** (the method below was run from a scratchpad script; the numbers are in the headline):
- Inputs:
  - `fsi/scouting/data/ignition_points.csv`, with `event_role == first_day_of_fire`, status ok, 15 Feb-15 Jun;
  - `grid_500m.geojson` and `beats/cell_beat.csv`;
  - `research/reframe/pilot/beat_arms.csv`.
- Statistic: log of (flexible starts ÷ flexible two-season baseline) ÷ (fixed starts ÷ fixed baseline).
- p-values from re-drawing arms within blocks (300 re-draws), with simulated thinning of flexible-arm starts.
- Results:
  - The null rate ratio by season is 1.18, 0.84, 0.94, 1.01, 1.16, 1.03, 0.98, 0.88 for 2019-26.
  - Power is 0.16, 0.50, 0.84 and 1.00 at 10%, 20%, 30% and 40% deterrence.
- [inference] The fixed arm also patrols every day, so the true contrast is about *where and when* staff are present, not *whether*. A realistic deterrence contrast is far below 30%.
- **Conclusion: report deterrence as exploratory, with its interval. Do not make a claim.**

**E2. Six design additions to lock by 1 Feb 2027** [inference, from A1-D2]:
1. **A deterrence endpoint that does not depend on patrols:** satellite first-day fires per beat by arm, with the 2017-26 beat mean as offset. Use the same block-randomisation inference, plus a top-40% subgroup (C2).
2. **A displacement/diffusion statistic:** WDQ using adjacent fixed-arm beats as buffers (C2), and the same test on calendar against forecast neighbours.
3. **A residual-deterrence window:** satellite starts within 1 km of inspected cells in days 1-7 against days −7 to −1. A random 20% of picks gives a clean estimate (C3, C4).
4. **Dose records:** time on site, people met, warnings, FIRs and awareness meetings (A1, A6, C3).
5. **An instrumented size effect:** arm-level Wald estimate of scar area against discovery delay (D1).
6. **A fortnightly breakdown** to catch novelty and fatigue (A5, C1).

## Datasets and code

| Item | What it gives us | Where | Status |
|---|---|---|---|
| BRIF Tables 2, 7-12 (Falleiro et al. 2026) | Fire counts per indigenous land before and after, ha per brigade member, cost lines | https://doi.org/10.1057/s41599-025-06390-7 (OA, CC-BY) | read |
| Indonesia fire-prevention RCT data (Edwards/Falcon) | Village hotspot outcomes, behaviour survey | Stanford FSE page https://fse.fsi.stanford.edu/node/29939 (no direct link found) | lead |
| Punjab PES replication data (Jack et al.) | Spot-check and satellite burn labels, RCT code | Linked from J-PAL https://povertyactionlab.org/node/7800491 | lead |
| Nyungwe patrol-allocation data (Moore et al. 2021) | Patrol events against occupancy-based risk, optimisation code | Dryad doi:10.5061/dryad.4xgxd2583 | lead |
| Dobson et al. 2019 simulation | Patrol–offender model for testing ΔCPUE-ΔE | Supplement of doi:10.1111/cobi.13222 (OA) | lead |
| Hot-spot policing meta-analysis data | Effect sizes per study, displacement tests | Campbell review e1046, appendices | read |
| WDQ formula (Bowers & Johnson 2003) | Displacement or diffusion statistic | As used in the PFPE paper | read; formula in C2 |
| Our deterrence power check | Null and simulated rate ratios per season | Method in E1; inputs listed there | computed today |

## Reading status

- **FULL (11):**
  - Prestemon et al. 2019 (Galicia arrests)
  - JFSP 09-1-9-2 report (tribal prevention)
  - Prestemon & Butry 2010 GTR-802
  - Watts et al. 2019
  - Edwards et al. 2020 (main text)
  - Falleiro et al. 2026 (BRIF)
  - Dobson et al. 2019
  - Ratcliffe et al. 2011 (PFPE)
  - ADB Bandipur case 2025
  - CSIRO PyroPage 22
  - Mongabay Similipal 2022
- **PARTIAL:**
  - Prestemon & Butry "Wildland arson management" chapter
  - Jack et al. 2023
  - Braga et al. 2019
  - Tremblay et al. 2018
  - Chas-Amil et al. 2015 (read; no patrol content)
  - CrimeSolutions Sacramento page
- **ABSTRACT ONLY:**
  - Falcon et al. 2022
  - Abt et al. 2015
  - Tachibana & Adhikari 2009
  - Moore et al. 2018 and 2021
  - Hilborn et al. 2006
  - Jachmann 2008
  - Koper 1995
  - Plucinski 2013 and 2019
  - Korkola et al. 2024
  - the Harvard Uganda instrument paper
  - Nepal Salyan and Bagmati studies
  - the Indonesian MPA studies
  - Ghana volunteer studies
  - Portuguese GNR thesis and news
  - Kadiwéu brigade study (−80% fire frequency and −53% burned area in high-frequency areas, via search snippet only)
- **Not reachable:** the MDPI PDF of Falcon 2022 (403); Wiley PDFs (Moore 2018); the Harvard DASH PDF; the Korkola PDF.

## Ranked action list (gain and effort are my estimates [inference])

| # | Action | Thread | Gain | Effort |
|---|---|---|---|---|
| 1 | Add a pre-registered **deterrence endpoint that does not depend on patrols** (satellite first-day fires per beat, block-randomisation inference, top-40% subgroup), labelled exploratory, with today's power figures (power about 0.5 at 20%, 0.84 at 30%) | 5 | High: stops detection gains being misread as deterrence, and the reverse | Low |
| 2 | **Randomise about 20% of ignition-stream picks** among eligible top-dryness cells. This gives a clean residual-deterrence estimate (days 1-7) and an instrument for discovery delay → scar area. Re-run `pilot_power.py` for the H1 cost first | 5, 4 | High: the only way to get a causal "does a visit stop the next fire" number | Medium |
| 3 | **WDQ displacement/diffusion test** on beat adjacency (fixed-arm buffers), plus contamination minutes from phone positions in beats of other arms | 5 | Medium-high: guards against H1 bias from spillover | Low |
| 4 | **Dose and guardianship log:** minutes on site, people met, warnings, FIRs, awareness meetings per beat per day | 5, 1 | Medium: lets deterrence be tied to visible enforcement (Galicia, Riau) | Low |
| 5 | Report each arm's budget as **person-hours per km² per week**, set against the BRIF (1 per 110 km² effective, 1 per 815 km² not), Bandipur (0.52 watchers per km²) and Nyungwe (about 8.4 visits per km² per year for −50% risk) benchmarks | 5 | Medium: makes results transferable to other MP divisions (thread 1's 87-division model) | Low |
| 6 | **Arm-instrumented estimate of scar area against discovery delay** (v2 scars, FSI ignition-time estimate) | 4, 2 | Medium: first causal "ha saved per hour" for litter fires | Medium |
| 7 | Written **"held" and "response failure" definitions** for litter fires in the field app | 4, 5 | Medium | Low |
| 8 | Report the deterrence endpoint by **fortnight** (novelty decay in Edwards; fatigue in Dallas) | 5 | Low-medium | Low |
| 9 | Register the pilot (OSF or the AEA registry) before 1 Feb 2027 as the first randomised evaluation of fire-patrol allocation in India | 5 | Medium (credibility) | Low |
| 10 | Digitise the range offences register (POR/FIR) for 2017-26 and test `offence_cases_last_365d_within_10km` as a 2-day-model feature | 1 | Low-medium | Medium-high |
| 11 | Sensitivity analysis widening the excluded-zone window to 7-11 days (arson contagion length) | 5 | Low | Low |
| 12 | Store pilot inspections as scar-classifier labels: positives from burns found, negatives only from same-day "no burn" visits (Jack et al. censoring lesson) | 2 | Low-medium | Low |
