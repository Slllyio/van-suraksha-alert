# Human causes and timing of fires in central Indian dry deciduous forest: what is known, and what we can compute

Scouting round 3, topic "human". Written 14 Oct 2026. Each source is marked **FULL** (I read the whole text), **PARTIAL** (I read the relevant chapters or pages) or **ABSTRACT ONLY** (abstract, landing page or a search snippet). My own reasoning is marked **[inference]**. Earlier notes already cover the mahua/tendu calendar flags, night-time burning, LST and leaf fall (short_horizon_prediction.md §7), and Mudumalai's fire return interval against distance from the boundary (fuel_load_values_fullread.md §3). I do not repeat them here.

**Bottom line.**
- **No published study gives cause shares from a villager questionnaire for MP or Chhattisgarh forest fires.** The closest is the iFOREST household survey (Korba, Chandrapur, Angul), and it shows that people under-report their own use of fire.
- **The best published support for our "interior burns more" result is national-scale.** In MODIS 2006-11 data, the more often an Indian tropical dry forest cell burned, the farther it lay from the main road network: median about 6 km for unburned cells, about 10 km for cells that burned more than 3 times (Schmerbeck & Fiener 2015, Fig. 5).
- **Several field facts explain why collectors burn deep inside the forest.** Mahua trees are scattered through the forest every 100-200 m, and families inherit allotted trees. Tendu collectors walk 5-10 km a day. NTFP catchments have a radius of about 6 km.
- **There is a confound in how we measure distance to villages.** Ratapani has 26 villages inside it and 109 around it. If our village layer holds only the outer villages, "interior" may in fact mean "near a forest village or hamlet".
- **The cheapest new features** are a full settlement layer (Google Open Buildings), cost-distance along slope and paths instead of straight-line distance, a Sentinel-2 "April green-up" map of species that flush in the hot season (mahua, tendu, kusum, achar), and per-cell timing signatures from past VIIRS detections.

---

## 1. Sources

### 1.1 IGNFA, "Tendu leaves" (Biodiversity cell, NTFP issues no. 15). FULL
https://www.ignfa.gov.in/document/biodiversity-cell-ntfp-related-issues15.pdf

What it shows. The operational tendu calendar for MP, and how the trade is organised:
- **Bush cutting / coppicing.** Tendu bushes are coppiced in **February**; cutting happens "between January and March". Pruning is "in the months of February and March". Leaves are ready **about 45 days** later. "A light burning just before sprouting stimulates the dominant leaf buds and favours a better flush."
- **Collection.** It starts in the **second fortnight of April**. MP's season runs **about 6 weeks** and begins "any time from the middle of April to the second week of May", depending on the district. It stops **10-15 days before the monsoon**.
- **Organisation.** The collection area is divided into **units**, which the MP MFP Federation sells in advance by tender. Temporary collection centres are called **phad** (phadi in Odisha, kallam in AP). MP has **more than 15,000 phads**. Each phad has a Phad Munshi (from the cooperative society) and a Forest Department **Phad Abhirakshak**. Families carry a collector card with daily entries, and are paid weekly.
- **Harda district union case study.** 8 primary societies and **165 phads** collect about 22,000 standard bags a year (2009-13 range 16,643-25,719). Societies have 13-33 phads each. Each society forms a separate sale unit.
- **Fire.** "In order to save on bush cutting cost, the area is often burnt." Bush-cutting areas are chosen "based on their convenience (e.g. near a village)". The bush-cutting budget stayed flat while wages rose, so the cut area shrank by **about a fifth**. Contractors "deliberately encourage workers to set fire… fires are kindled in tendu units **during January onwards**… almost the entire forest area in tendu units or in the vicinity, burns every year."
- **Maharashtra rule (2012 tender, condition 12).** If a fire spreads beyond **1 ha** in a tendu unit between 1 January and the auction, the unit is withdrawn from sale, and the contractor and gram panchayat get no compensation.

Concrete action for us.
- *Thread 1 (prediction).* Build a **tendu-unit / phad layer** for Raisen and Sehore. Ask DFO Raisen / the district union for the list of primary societies, phad villages and unit boundaries (likely a paper map plus the society-to-village table).
  - Features: `dist_to_nearest_phad`, `phad_density_5km`, `in_tendu_unit` and `tendu_unit_id` (a categorical feature or random effect), and `unit_bags_per_km2` (a yearly productivity proxy, as a feature).
  - Season flag for **days from 15 Jan to the local collection start** (the burning window: Jan-Mar, ideally about 45 days before plucking).
  - Expected effect: unknown. Possibly the strongest missing spatial driver for Jan-Mar ignitions [inference].
- *Thread 5 (alerts).* Each phad has a Forest Department employee (the Phad Abhirakshak) in April-May. That is a ready-made field verifier network for late-season alerts [inference].

### 1.2 iFOREST, "Forest fires and tendu leaf collection in India: an evidence-based analysis" (2023; PDF re-uploaded Aug 2025). PARTIAL (chapters 3-4 and Annexure 3 read in full)
https://iforest.global/wp-content/uploads/2025/08/Forest-fires-and-tendu-leaf-collection-in-India-An-evidence-based-analysis.pdf · Chhattisgarh factsheet: https://iforest.global/wp-content/uploads/2025/08/Factsheet-Forest-Fires-Climate-Change-and-Tendu-Patta-An-Evidence-based-Analysis-for-Chhattisgarh.pdf

What it shows.
- **Satellite part (weak method).** They used MODIS fire points 2011-21 within a **1,000 m buffer** of **1,615 ISRO "tendu sample points"** (Maharashtra 594, Chhattisgarh 411, Odisha 610). That gives **1,551 "tendu-linked" fire points** (Odisha 788, Maharashtra 554, Chhattisgarh 209). The reported "correlation" is 0.81 for Maharashtra, 0.75 for Chhattisgarh and 0.83 for Odisha (yearly values mostly >0.8, about 0.7 in 2012 and 2020).
  - They also built a tendu MaxEnt SDM on WorldClim and overlaid it with MCD64A1 burned area.
  - Tendu range from the SDM: 22,904 km² (CG), 16,957 km² (OD), 13,233 km² (MH).
  - Burned area in tendu-prevalent forest 2011-21: **13,905 km²** (CG 6,120; MH 4,767; OD 3,018). Peak months are **Feb-May**.
  - Maharashtra fire points dropped sharply after the **2012 fire rule**, rose after 2015, and fell to near zero in 2020 (COVID lockdown).
  - [inference] This is overlap with tendu range, not attribution. It has no control for non-tendu forest of the same type.
- **Household surveys (useful).** One district in each of three states, with **about 381-385 households each**. Villages were chosen from the list of phadis; in Angul, every 30th phadi.
  - Tendu villages lie **50-2,000 m** (Chandrapur), **100-1,200 m** (Angul) and **200-3,000 m** (Korba, Chhattisgarh) from the forest. On average **409-1,025 people per village** collect tendu.
  - **Angul:** **378 of 381** said their own tendu collection uses no fire. 62 blamed others (mahua and tendu collectors, Forest Department staff, neighbouring villages); 52 of those blamed the Forest Department. 103 said fire is beneficial for tendu.
  - **Chandrapur:** **47.7%** said tendu collection involves fire. 57 said it is beneficial, 154 said it is not.
  - **Korba (CG):** **18.6%** said tendu involves fire; of those asked who sets the fires, **70% said tendu collectors**. 32% acknowledged that collectors set fires. Only 7% saw a benefit (new leaf flush).
  - **95%** (Korba) named animal attacks, and also "long distances", as the main hardships of collection.
  - **Bidar** (where collection was banned): **75%** of ex-collectors acknowledged using fire for tendu.
- **Other facts.**
  - Chandrapur recorded 2,083 fire incidents between Jan 2012 and Jul 2022.
  - The MP and CG governments pay for bush cutting through the primary cooperative societies.
  - Maharashtra pays about ₹100/day for bush cutting, and spent about ₹350 M in crop year 2021.

Concrete action for us.
- *Thread 1.* Do not expect village interviews to name causes: self-reporting drops to about 1% where fire use is illegal (Angul) [inference]. **Design the field questionnaire (thread 5) to ask about *other* villages' practices and about timing and location, not about self.**
- The **"phad list → villages"** route is how iFOREST sampled. We can do the same for Raisen.
- The SDM and 1 km buffer approach is too coarse for 500 m cells. Use it only as a regional prior.

### 1.3 Niyogi, Niyogi, Banerjee, Verma & Choure 2025, *Sci. Rep.* 15:13272, "Environmental and anthropogenic influences on fire patterns in tropical dry deciduous forests" (Satpura TR, MP). FULL
https://www.nature.com/articles/s41598-025-98051-7 (CC BY-NC-ND; R code in the supplement)

What it shows.
- **Data and set-up.** MODIS MCD14DL 2002-21, **March-May only** (almost all fires fall then), on a **1 km grid of 1,538 cells** over the core area (1,339 km²).
  - Settlements were hand-digitised from Google Earth, including croplands, for 2001, 2010, 2013 and 2021.
  - Roads were digitised as the Google roads layer; water bodies came from OSM.
  - Models: Bayesian **zero-inflated Poisson and zero-inflated negative binomial with Leroux CAR priors** (CARBayes; rstan with 4 chains × 2,000 iterations).
- **ZINB posterior means (95% CI), standardised:**

  | Covariate | Mean | 95% CI |
  |---|---|---|
  | Slope | +0.25 | 0.14, 0.36 |
  | Distance to water | **+0.32** | 0.22, 0.41 |
  | Distance to roads | −0.01 | n.s. |
  | Aquatic cover | −1.26 | |
  | **Distance to settlements** | **−0.52** | −0.65, −0.39 |
  | NPP (previous year) | +0.28 | n.s. |
  | **Road density** | **−0.36** | −0.50, −0.21 |

  The ZIP model gave similar values (distance to settlement −0.59).
- **Monthly NB model (whole core as one unit):** Tmax +0.295 per °C (p<1e-15), previous month's fire count +0.012 (p=0.0002), previous month's rain −0.0035 (p=0.06).
- **Interpretation.** Fires are near settlements and **far from water**. **Road density is negative**: the authors read roads as **firebreaks**, and access in the open forest does not depend on roads. Hotspots sit close to croplands and built-up areas. Buffer villagers burn litter for mahua and tendu. The authors also mention poachers using fire as a diversion.

Concrete action for us.
- *Thread 1.* Two features are cheap to add.
  - **`dist_to_water`**: JRC GSW occurrence >25% or OSM water. A positive effect fits the "interior" signal if interior uplands are far from the Kolar/Barna reservoirs and streams [inference].
  - **`road_length_in_cell`** as a separate feature from `dist_to_road`: roads can act as firebreaks.
- The Satpura sign for settlements is **opposite** to ours. Their settlements include **enclaves inside the core**. So if we add hamlets and forest villages (§3.1), our sign may flip too [inference].
- The previous-month fire count is a strong temporal term. We already have burn history, so this is a check only.

### 1.4 Schmerbeck & Fiener 2015, *Environmental Management* 56:355-372, "Wildfires, ecosystem services, and biodiversity in tropical dry forest in India". PARTIAL (pp. 357-361 read as page images; the PDF is scanned)
https://opus.bibliothek.uni-augsburg.de/opus4/files/42804/42804.pdf · doi:10.1007/s00267-015-0502-4

What it shows.
- **Interior burns more (Fig. 5).** In all-India tropical dry forest (TDF), distance to the next **main road** rises with MODIS burn frequency over 7 years (2006-11, FSI 1 km fire points). Medians are about **6 km (unburned), ~8, ~9, ~9.5, ~10 km (>3 burns)**. The authors' reading: "burned TDF areas can be found in larger distances to the main road network than the mean TDF distance… an increase in human burning activity in more remote, less developed areas."
- **MP numbers (Fig. 1).** MP has 48,804 km² of TDF (15.83% of the state). It burned **651 km²/yr (1.33%/yr)** by FSI MODIS 2006-11. India as a whole: about 1.4%/yr, "a conservative estimate".
- **Annual FSI fire counts in TDF:** 2006 1,582; 2007 1,797; 2008 2,335; 2009 3,202; 2010 2,792; 2011 1,485.
- **Topography and climate.** Burned TDF lies slightly **higher and steeper** than unburned TDF. Burning needs a dry spell of at least 2 months (<60 mm/month). On average, fires came after 5.7 ± 1.4 dry months.
- **Fire-assisted products (Table 2,** from village surveys by Kohli 2010 in AP, Roveta 2008 in Karnataka and Schmerbeck 2003 in Tamil Nadu):
  - honey (fire-induced flowering, smoking bees out of hives)
  - thatch, brooms, edible tubers
  - fruit and seed yield of amla, harra, achar (*Buchanania*)
  - beedi (tendu) leaves, leaf cups, gum, bark, roots
  - ash fertiliser, fodder grass, "inducing rain", **"accessibility and safety"** (clearing paths, seeing snakes)
  - **fuelwood**: low-intensity fire top-kills small trees, and they are later collected as dry wood. In Kohli's survey of **557 households in 14 villages**, fuelwood was the second most frequently named forest product.
- Tendu is burned **"in the dry season (mainly April-May)"**, and mahua floors are burned so fallen flowers are easier to collect.

Concrete action for us.
- *Thread 1.* This is the closest published precedent for our ~2× interior effect. It suggests remoteness is itself a driver: less surveillance, more pasture and hunting burns. Use `dist_to_main_road` (NH-46 / SH and paved district roads only) as a separate feature from `dist_to_any_track` [inference: the national pattern is about the main road network].
- Add a **"remoteness" feature** as cost-distance from paved roads (§3.2).
- Expected gain: small, but it makes the interior effect explainable to the Forest Department.

### 1.5 Pradeep Mishra (IFS, ex-DFO Dewas and South Shahdol), Down To Earth, 13 Nov 2025, "True forest fire management must begin… with understanding the people who light them". FULL
https://www.downtoearth.org.in/natural-disasters/true-forest-fire-management-must-begin-not-with-extinguishing-flames-but-with-understanding-the-people-who-light-them

What it shows.
- **Data and scale.** FIRMS MODIS+VIIRS 2016-25, analysed in ArcGIS Pro, show more than 2,000 forest fires a year in western MP.
- **Season.** It starts in **November**, rises from December, peaks **Feb-Apr**, and drops sharply in June. Monthly mean temperature peaks later (Apr-May), so **fires lead temperature** [an inference by the author, consistent with human timing].
- **Mahua.** Mahua blooms in **March**. Women and elders burn dry leaves under the trees. Nylon nets were distributed through JFMCs and the Green India Mission, and fires "lowered briefly before old habits returned".
- **Tendu (Dewas).** Surface fires start **5-6 weeks before collection, in the same patches later harvested**. The author reports (unverified) that contractors encourage the burning.
- **Dewas division.** About 2,000 km² of forest had about **9,000 fires** in 2016-25, many recurring in the same patches. Kernel density (2 km search radius, 250 m cells) gives **5 high-density clusters near village-forest boundaries**. Of **870 compartments**, about **20 are "very high"** and about **170 "high"** by mean fire density per km².
- **Other causes named:**
  - retaliation over forest-offence enforcement, compensation delays, and disputes with staff
  - hiding illicit felling or encroachment
  - clearing weeds before fuelwood collection
  - cigarettes and picnics
- MP has a **"SimplyFire" web portal**.

Concrete action for us.
- *Threads 1 and 5.* The 5-6 week lead before tendu collection gives a concrete **timing window**: if Raisen collection starts about 1-10 May, tendu-linked burning should cluster about **mid-March to early April** [inference]. Compute `days_to_local_tendu_start`, using the yearly start date from the Raisen district union.
- **Compartment-level fire density** is the unit the DFO thinks in. Report our predictions aggregated to compartments too.
- Ask for the MP SimplyFire portal's records: they may contain field-verified causes.
- The author is a good contact for a Dewas-style cause analysis.

### 1.6 People's Archive of Rural India, "Slowly dropped the mahua in Umaria" (Bandhavgarh buffer, MP). FULL
https://ruralindiaonline.org/en/articles/slowly-dropped-the-mahua-in-umaria/

What it shows.
- **Mahua trees are "scattered in the forest, roughly every 100-200 m"** in the Bandhavgarh buffer. Each family in Parasi village holds **inherited allotments of a few trees** (Mani Singh's family has 5). The trees are marked with a rag during the season.
- **Timing.** The season "begins in early April, almost immediately after Holi" and lasts **2-3 weeks**; one year picking ended after 15 days. Picking runs from about 05:00 to noon.
- Pickers **sweep** dry leaves under the trees. Deer eat flowers that fall at night, so people go early. Rising heat makes flowers fall earlier in the morning.
- Yields are about 100-300 kg per family per season, at ₹35-50/kg.

Concrete action for us.
- *Thread 1.* Mahua trees are **inside the forest, not only on village land**. That is a direct mechanism for interior ignitions in a buffer-type landscape like Ratapani: each family walks to its own trees, often far from the village.
- Our feature should be **mahua density** (§3.3), not "distance to village".
- The season is **anchored to the lunar calendar (Holi)** as well as temperature. Add `days_since_holi` (Holi dates by year: 2017-03-13, 2018-03-02, 2019-03-21, 2020-03-10, 2021-03-29, 2022-03-18, 2023-03-08, 2024-03-25, 2025-03-14, 2026-03-04; check against the panchang). Holi moves by up to about 4 weeks between years, so it can be separated from day of year [inference].

### 1.7 Mongabay India commentary, Nov 2023, "Erratic weather, altered social dynamics disrupt mahua economy in eastern India". FULL
https://india.mongabay.com/2023/11/commentary-erratic-weather-altered-social-dynamics-disrupt-mahua-economy-in-eastern-india/

What it shows.
- Flowering starts at the **end of March**.
- In sunny weather flowers drop mostly **before about 10:00**. Under cloud, or after a slight fall in temperature and humidity, they fall almost all day.
- Collection runs from 04:00 to 10:00-11:00. Each mature tree yields **60-80 kg**. Flowers are sun-dried for 3-5 days.
- **Most trees grow on private land or commons (agroforestry)** in the Jharkhand and West Bengal setting. Prices fell from ₹65-70/kg (2021) to ₹20-22/kg (2023).

Concrete action for us.
- *Thread 1.* Where mahua is mainly on farm land (the Jharkhand pattern), mahua fires sit at the forest edge. Where it is scattered in forest (the Bandhavgarh pattern), they sit inside. Ratapani needs mapping to tell which applies [inference].
- Price falls may reduce collection effort in some years. A yearly mahua price series (MP MFP Federation minimum support price, MSP) is a cheap yearly covariate, but there are only 9-10 seasons, so it is weak [inference].

### 1.8 The Mooknayak, 2023, "From mahua collection to Magra Snan: the threat of forest fires in south Rajasthan". FULL
https://en.themooknayak.com/environment/from-mahua-collection-to-magra-snan-the-threat-of-forest-fires-in-south-rajasthan

What it shows.
- Collectors **set fallen leaves alight "so the flowers are easier to find the next morning"**, which implies burning in the day or evening, after collection.
- Udaipur tribal residents **burn forests after Holi**.
- **Magra Snan** is a vow-fulfilment ritual of offering fire to the hill god "Magra Bavji", cited as a leading cause in south Rajasthan.
- Grazing burns aim at "softer grass". Honey-collecting communities also set fires.
- The season runs from mid-March to the end of June.

Concrete action for us.
- *Threads 1 and 5.* If mahua burns are lit **after the morning pick**, they would show up in the **13:30 VIIRS/Aqua pass**, and in the **01:30 pass if they smoulder**. Compute, per cell, the share of past detections at night vs by day (§3.5).
- For the field form (thread 5), add the question "what time of day was it lit?" [inference].

### 1.9 Singh & Kushwaha 2006, *Annals of Botany* 97:265-276, "Diversity of flowering and fruiting phenology of trees in a tropical deciduous forest in India" (Hathinala, Vindhyan dry forest). PARTIAL (HTML text searched for the target species)
https://pmc.ncbi.nlm.nih.gov/articles/PMC2803360

What it shows.
- ***Diospyros melanoxylon* (tendu)** is a "<2-months-deciduous" species with a **leafless period of 33 days**. It **flushes leaves in the hot-dry season and flowers on the new shoots in summer (March-June)**, possibly cued by increasing day length and/or temperature. The lag from leaf flush to flowering is 0.8 months.
- It has the **most synchronous flowering** of the species studied (asynchrony index 0.12).
- The paper does not include mahua. The source for mahua (Kushwaha & Singh 2005, *Current Science* 89:964) is a scanned PDF that I could not extract.

Concrete action for us.
- *Threads 1 and 3.* Tendu (and mahua, kusum, achar, sal) **leaf out in March-April while teak and most associates are still leafless**.
- So a Sentinel-2 **"hot-season green-up" index** per 10 m pixel (NDVI or NDRE of 20 Apr-10 May minus 1-20 Mar) separates these species' crowns from teak.
- The per-cell **fraction of green-up pixels** is a proxy for the density of NTFP species that drive burning (§3.3).
- Expected effect: unknown, possibly the missing spatial term. Effort: 1 day in GEE [inference].

### 1.10 Kulkarni & Mehta 2020, *Indian Forester*, mahua collection sheets in Melghat TR. ABSTRACT ONLY
https://indianforester.co.in/index.php/indianforester/article/view/154919

- Mahua is "collected by burning the undergrowth under mahua trees, often causing forest fire".
- Collection sheets made from old saris cut **daily collection time from 6.78 ± 0.79 h to 1.58 ± 0.29 h**, and reduced wild-animal encounters.
- Action: none for modelling. For thread 5, the Forest Department can target net or sheet distribution to the cells our mahua map flags.

### 1.11 Jha, Jana, Negi & Negi 2018, *Open Ecology Journal* 11:62 (Pauri Garhwal). FULL
https://openenvironmentalresearchjournal.com/VOLUME/11/PAGE/62/FULLTEXT/

- 211 households in 20 villages, each interviewed three times (pre-, during and post-season). No cause shares from respondents.
- It cites Semwal 1996: **63% intentional, 37% accidental** in the Garhwal hills.
- Use: a survey-design template only (three rounds, 30-minute interviews, 35 indicators).

### 1.12 Hitavada (6 Jul 2023) on the iFOREST Maharashtra study. FULL
https://thehitavada.com/Encyc/2023/7/6/Tendu-collection-process-a-reason-behind-forest-fires-in-Maharashtra-Study.html

- Survey in Chandrapur: 385 households in 7 villages; about ₹8,000 earned for **13 days** of collection.
- Maharashtra had **34,025 fire points in Nov 2020-Jun 2021** (about 10% of India).
- The figures duplicate §1.2. It confirms that the collection season is short (about 2 weeks of work per household).

### 1.13 Other leads, ABSTRACT ONLY or snippets

- **Tadoba "Tendu patta" research note** (Maharashtra Forest Department): GPS-tracked collectors in the core walked **3.6-8.2 km/day** (27.8 km over 5 days, 26-28 May). In the buffer, 6.9-8 km/day. "Collectors travel daily around 5 to 10 km." https://mytadoba.mahaforest.gov.in/frontend/assets/img/pdf/research/Tendu%20patta.pdf (server unreachable, only the snippet read). Action: use **5-10 km walking range** as the plausible ignition reach from a village for tendu (cost-distance, §3.2).
- **ICFRE/MoSPI 2007 NTFP sample survey:** "each village gets its share from around **6 km radius**". https://www.mospi.gov.in/sites/default/files/publication_reports/nad10_2007_icfre_final%20(1).pdf. Odisha (Nabarangpur): **46% go 6-10 km**, 10% go ≥16 km. A survey of 90 collectors (region not stated): 35.6% go 4-6 km, 23.3% >9 km.
- **Sahu, Khan & Madguni 2024**, *Env. Monit. Assess.*, Khandwa and North Betul (MP). AHP with 10 factors and 22 years of MODIS. Moran's I is 0.043 (Khandwa) and 0.096 (North Betul). About 45% and 50% of the area is high or very high risk. https://link.springer.com/article/10.1007/s10661-024-12960-0. AHP weights are expert opinion, so they are of little use.
- **Ray et al. 2023**, *Sustainability* 15:7046, Chhattisgarh MODIS 2005-21: fires rose from 1,487 to 3,074 a year; **88.9% fall in Mar-May**; monthly fires go from 61 ± 82 in January to 2,571 ± 2,702 in March. https://doi.org/10.3390/su15097046
- **Kumar, Kumar & Biswal 2023**, *Indian Forester* 149(5), Barsuan range (Bonai, Odisha): semi-structured questionnaire in 6 villages; fires are set for livelihood, NTFPs and food. No percentages in the abstract. https://indianforester.co.in/index.php/indianforester/article/view/169034
- **Vadrevu & Eaturu 2024**, *Atmosphere*: VIIRS 375 m shows **about 28% of South Asian fires at night**, and night fires in India are trending up (not significant).
- **Yunnan (Forests 15:661, 2024):** the fire-settlement relationship turns from negative to positive with distance and flattens beyond **about 3 km**. https://doi.org/10.3390/f15040661 Action: fit `dist_to_settlement` with a monotone spline, or cap it at 3-5 km.
- **NESAC NE India:** maximum fires at **1,000-1,500 m** from built-up areas and minimum at 2,500-3,000 m; maximum at 50-100 m from roads. https://nesac.gov.in/assets/resources/2020/12/Forest-Fire-Assessment-in-NER.pdf
- **Garai et al. 2021** MaxEnt for mahua (eastern India): about 29,550 km² suitable, 72% of it in Jharkhand and 17% in Chhattisgarh. This is regional only, and too coarse for us.
- **Remote Sensing 18:1825 (2026)**, Landsat-Sentinel flowering index (MOFI) to separate tree crops from planted forest: peak flowering in March-April gives a distinct signal. https://doi.org/10.3390/rs18111825. Possible method template for mapping mahua flowering (not read).
- **INSAT-3D/3DR/3DS fire product (MOSDAC):** 4 km resolution, every 15-30 minutes. INSAT-3DS stubble fires in Punjab start at about 15:00 IST and peak at **16:30 IST**, so MODIS and VIIRS miss many fires after 16:00. https://link.springer.com/article/10.1007/s41976-025-00233-4
- **Ratapani KBA factsheet:** **26 villages inside, 109 around** the sanctuary. https://www.keybiodiversityareas.org/site/factsheet/18314
- **Similipal reporting** (Mongabay 2021-22): villagers say "there is not a single mahua tree inside the core… only around the Adivasi villages". Areas with Community Forest Rights (CFR) under the Forest Rights Act were the least damaged. This is the opposite spatial pattern to Bandhavgarh, which shows mahua placement varies by landscape.

---

## 2. Why do Ratapani's interior cells ignite about 2× more than cells near villages? Candidate explanations, with a test for each

| # | Explanation | Evidence | Test with our data |
|---|---|---|---|
| A | **Village layer misses forest villages, hamlets and cattle camps** (26 villages inside the sanctuary) | KBA factsheet; Satpura's settlement layer included enclaves and croplands and got the negative sign | Rebuild `dist_to_settlement` from **Google Open Buildings v3** (and its 2016-23 temporal version), clustered into hamlets of ≥3 buildings. Check whether the interior effect shrinks or flips |
| B | **Collectors walk deep**: mahua trees every 100-200 m inside the forest, tendu 5-10 km/day, NTFP radius about 6 km | PARI, Tadoba GPS, ICFRE | Replace Euclidean distance with **slope-weighted cost-distance (walking hours)** from every hamlet. Ignition should peak at about 1-3 h walking, not at 0 h |
| C | **Fuel depletion near villages**: grazing, fuelwood and litter removal, and early small fires (Jan-Feb) leave less fuel by March-April | Kodandapani/Mudumalai negative exponential; detection misses concentrate near villages (our earlier note) | Compare the month of first burn and pre-season NDVI/NBR by distance band. If near-village cells burn earlier and smaller, it is fuel or detection, not fewer ignitions |
| D | **Spread, not ignition**: fires lit at the edge run uphill into unbroken interior forest. Burn-scar labels count every burned cell | Satpura slope +; Schmerbeck burned TDF is higher and steeper | Use **only the first-detected cell of each fire event** (earliest VIIRS pixel per connected scar) as the ignition label, then recompute the distance curve |
| E | **Remoteness = less surveillance**: deliberate burns (grazing, hunting, retaliation) happen where staff do not go | Schmerbeck Fig. 5 (burned cells 6 → 10 km from main roads); Mishra (retaliation) | Add `dist_to_beat_or_range_office`, `dist_to_patrol_camp` and cost-distance to paved roads. If the interior effect moves to these features, it is about surveillance |
| F | **Waterholes, cattle and wildlife**: interior grazing camps near seasonal water, honey and hunting | Mooknayak; Schmerbeck Table 2. Satpura shows the opposite sign, far from water = more fire | Add `dist_to_seasonal_water` (JRC GSW seasonality 1-9 months) and the count of check-dams and saucers (from the Forest Department) |
| G | **Roads as firebreaks**: road density is negative in Satpura | Niyogi 2025 | Add `road_length_in_cell`, separately from distance to road |

[inference] A and D are the cheapest to test and the most likely to change the sign. B is the best new feature even if the sign stays.

---

## 3. Feature ideas we can compute (thread 1 unless noted)

1. **Full settlement layer** (fixes confound A).
   - Source: Google Open Buildings v3 polygons (GEE `GOOGLE/Research/open-buildings/v3/polygons`, confidence ≥0.7), plus the 2016-2023 temporal raster (`GOOGLE/Research/open-buildings-temporal/v1`) for yearly building presence.
   - Features: `dist_to_hamlet` (DBSCAN with eps 100 m, min 3 buildings), `n_buildings_5km`, and building growth.
   - Effort: 0.5 day.
2. **Walking-time cost-distance** (B and E).
   - Cost surface: Tobler's hiking function on the SRTM/ALOS 30 m slope, ×0.5 on OSM tracks and paths, ×0.2 on roads, and impassable on reservoirs.
   - Features: `walk_h_from_nearest_hamlet`, `walk_h_from_nearest_phad`, `walk_h_from_paved_road`.
   - Fit as splines and expect a hump at 1-3 h [inference].
   - Paths: OSM (Overpass returned errors from here, so pull a Geofabrik `central-zone` extract). Alternatively, detect trails from 2023-26 Sentinel-2 or Google satellite basemaps; or a crude version: least-cost corridors between hamlets and water points ("path density").
3. **Hot-season green-up map: the NTFP-species proxy** (mahua, tendu, kusum, achar, sal).
   - S2 L2A 10 m. `ΔNDRE = median(20 Apr-10 May) − median(1-20 Mar)`, computed per year and then the multi-year median.
   - Optional: a flowering signal for mahua in late March, when crowns are leafless with cream flowers. Try a brightness/visible-band index on leafless crowns and validate against about 50 GPS-marked mahua trees from a field visit.
   - Features: `frac_greenup_pixels`, `n_large_greenup_crowns`.
   - Thread 3 bonus: it separates teak litter from mixed-species litter.
4. **Tendu units and phads.**
   - Inputs: the society, phad and village list, and unit boundaries, from the Raisen/Sehore district unions (DFO Raisen = managing director).
   - Features: `dist_to_phad`, `in_unit`, unit productivity (std bags/km²), the yearly collection start date, and `days_to_tendu_start` (window −60 to 0 days).
5. **Per-cell timing signatures from past VIIRS** (built only from training years).
   - Features: `share_night_detections` (01:30 vs 13:30), the cell's median day of year of first detection, and `early_burner` (median before 1 March).
   - These separate fire-line and tendu cells (Jan-Mar) from mahua cells (late Mar-Apr) and grazing cells (Apr-May) [inference].
   - Also compute the Terra (10:30) vs Aqua (13:30) share from MODIS 2002-26 for a longer record.
6. **Lunar and festival calendar.** `days_since_holi` (dates in §1.6), plus Akshaya Tritiya (marriage season, April-May labour demand) and the local weekly haat day of the nearest market village (ask the range office). Calendar flags gave nothing before, but they were Gregorian; Holi moves by about 4 weeks between years, so it is worth one run [inference].
7. **Water and roads.** `dist_to_seasonal_water` (JRC GSW, 30 m, 1984-2021) and `road_length_in_cell` (OSM).
8. **Railway.** `dist_to_rail`. The Bhopal-Itarsi line runs through the Budni/Barkheda ghat section along Ratapani's south. No Indian study quantifies rail ignitions; the only reports I found are about steam engines in Himachal. Expect a narrow 0-200 m effect, if any [inference].
9. **Event-level ignition labels** (test D). For each connected burn scar, the earliest VIIRS pixel is the ignition cell. Train a separate ignition model, so new-ignition and spread risk are scored apart.

---

## 4. Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| Google Open Buildings v3 | https://sites.research.google/open-buildings/ | building polygons | ~2022-23 | CC BY 4.0 / ODbL | GEE `GOOGLE/Research/open-buildings/v3/polygons` |
| Open Buildings 2.5D Temporal | same site | 4 m effective, yearly | 2016-2023 | CC BY 4.0 | GEE `GOOGLE/Research/open-buildings-temporal/v1` |
| OpenStreetMap (paths, tracks, rail, water, place nodes) | https://download.geofabrik.de/asia/india.html | vector | current | ODbL | Geofabrik extract; Overpass blocked from here |
| JRC Global Surface Water | https://global-surface-water.appspot.com | 30 m | 1984-2021 | free, citation | GEE `JRC/GSW1_4/GlobalSurfaceWater` |
| Sentinel-2 L2A | Copernicus | 10-20 m, 5-day | 2017- | free | GEE `COPERNICUS/S2_SR_HARMONIZED` |
| FIRMS VIIRS 375 m (S-NPP, NOAA-20/21) and MODIS | https://firms.modaps.eosdis.nasa.gov | 375 m / 1 km | 2012- / 2000- | free | archive download (we have it) |
| INSAT-3D/3DR/3DS fire (IMAGER L2P FIR) | https://www.mosdac.gov.in | 4 km, 15-30 min | 2016- | free, registration | MOSDAC order; fire timing of day |
| IIRS Biodiversity Information System: vegetation type map 1:50k (Roy et al. 2015, 15,565 ground points) and BCLL field-plot species data (source of iFOREST's "tendu sample points") | http://bis.iirs.gov.in · paper: https://ris.utwente.nl/ws/files/276818546/New_vegetation_type_map_of_India_prepared_using_satellite_remote_sensing_comparison_with_global_vegetation_maps_and_utilities.pdf | 1:50k; plots 0.04 ha | ~2008-2012 | government, request | portal (often down) or request to IIRS. Check plots in Raisen/Sehore for *Madhuca* and *Diospyros* |
| MP tendu units, primary societies, phad list, yearly collection dates and bags | MP State MFP Federation (mfpfederation.org, unreachable from here); DFO Raisen as district-union MD | unit polygons / phad points | yearly | government | written request via the project's Forest Department contact |
| MP Forest compartment map and compartment-wise fire records (SimplyFire portal) | MP Forest Department | compartment | 2016- | government | request (Mishra used it for Dewas) |
| Ratapani village list (26 inside, 109 around) | KBA factsheet / management plan | point | current | — | management plan from the Ratapani Tiger Reserve office |
| Holi / festival dates | any panchang | daily | all | public | hand table (in §1.6) |
| Mahua MaxEnt (Garai et al. 2021) | (paper) | ~1 km | — | — | email the authors; regional prior only |

---

## 5. Ranked action list

| Rank | Action | Thread | Expected gain | Effort |
|---|---|---|---|---|
| 1 | Rebuild the settlement layer from Open Buildings (hamlets inside the sanctuary) and redo the distance-to-village curve | 1 | Could flip or explain the interior effect; +0.5-2 pts recall [inference] | 0.5 day |
| 2 | Event-level ignition labels (first VIIRS pixel per scar); recompute the distance curve and train an ignition-only model | 1, 4 | Separates spread from ignition; clarifies the interior effect; +0-1.5 pts | 1 day |
| 3 | Walking-time cost-distance from hamlets, roads and (later) phads, fitted as splines | 1 | +0.5-1.5 pts; directly tests "collectors walk deep" | 1 day |
| 4 | Sentinel-2 hot-season green-up fraction (NTFP-species proxy), with ~50 GPS mahua and tendu trees from the field team for checking | 1, 3 | Unknown, possibly the missing spatial driver; +0-2 pts | 1-2 days plus a field visit |
| 5 | Per-cell VIIRS timing signatures (night share, median first-burn day of year, early-burner flag) from training years only | 1 | +0.3-1 pt; also labels the likely cause type for alerts | 0.5 day |
| 6 | Request tendu units, phads and collection dates (Raisen/Sehore district unions) and SimplyFire records | 1, 5 | Potentially large for Jan-Apr ignitions; needs data | Low effort for us, slow turnaround |
| 7 | Add `dist_to_seasonal_water` and `road_length_in_cell` (Satpura signs) | 1 | +0-0.5 pt | 2 h |
| 8 | `days_since_holi` and `days_to_tendu_start` instead of Gregorian flags | 1 | +0-0.5 pt | 2 h |
| 9 | Field questionnaire (thread 5) asking about others' practices, time of day, place and month, sampled from phad villages (the iFOREST design); Angul self-reports show direct questions fail | 5 | Ground truth on causes | Medium |
| 10 | Report predictions aggregated to compartments (the DFO's unit, as in the Dewas analysis) | 5 | Adoption | Low |

Sources read in full: 10 (IGNFA tendu; iFOREST chapters 3-4 and annex; Niyogi 2025; DTE Mishra 2025; PARI Umaria; Mongabay mahua commentary; Mooknayak; Jha 2018; Hitavada; FES workshop proceedings, which had nothing usable). Partial: 2 (Schmerbeck & Fiener 2015 pp. 357-361; Singh & Kushwaha 2006). Abstract or snippet only: about 14.
