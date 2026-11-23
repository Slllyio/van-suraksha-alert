# Grass fuel on open ground: how much there is, when it cures, and why fires stop at it after mid-February (scouting round 13, topic "grass", 16 Oct 2026)

For the fuel-map thread (`fuel-map/ratapani/v3/README.md`, "Not done yet": grass layer under open canopy; v2 grass was 2-4x too low) and the spread, prediction and patrol threads.

Scar truth used: **scar outlines v2 (2026-10-16)**, FIRMS events (`fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson`). Cover classes are from `fuel-map/ratapani/cover_phenology_10m.tif`, resampled to 20 m by mode. Class 4 ("open grass/low cover") is 27.1% of the forest mask at 20 m.

Code and outputs are in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r13_grass_code/`: `grass_timing.py`, `grass_curing_indices.py`, `grass_grazing_proxy.py`, plus their `*_out.txt` and `*.csv`. That folder is session scratch, so copy it to `fsi/scouting/code/grass/` if you want to keep it.

Status marks: **FULL** means the whole paper or document was read. **PARTIAL** means part of it, or the guide but not the data files. **ABSTRACT ONLY** means just that. **[inference]** marks my own reasoning.

---

## Headline findings

1. **In Ratapani, open grass does burn earlier than tree cover. Then, from mid-February, it burns less.** Pooled over 2017-2026, take the open-grass pixels that have not burned yet. The share that burns in each window is 0.97% in Nov-Dec, 1.57% in Jan and 2.40% in 1-14 Feb. For deciduous tree pixels the same figures are 0.14%, 0.62% and 1.74%.
   - The hazard ratio of grass to deciduous is 1.8-2.5 before 15 February, in every distance-to-village band.
   - After 15 February the order flips. Grass hazard is 19.2% in March against 28.9% for deciduous, and 8.2% in April against 13.6% (ratio 0.52-0.79).
   - The 10th-percentile first-burn date is 4 Feb for grass and 25 Feb for deciduous trees. The medians are close: 18 Mar for grass, 22 Mar for deciduous.
   - Inside the same 500 m cell, grass and deciduous pixels burn on the same date 86% of the time, because they are the same fire. The mean grass-minus-deciduous gap is -2.7 days (95% CI -2.7 to -2.2).
2. **"Grass is still green after mid-February" is ruled out.** Open grass is browner and drier than tree pixels in every month, Oct to May.
   - Median NDVI in February: grass 0.183, deciduous 0.253. 94% of grass pixels are below NDVI 0.25 in February, and 99.8% by March.
   - Relative-greenness curing (share of the season's NDVI drop already done): grass 62% in Dec, 71% in Jan, 84% in Feb, 98% in Mar. Deciduous: 38%, 50%, 70%, 94%.
   - The Australian MODIS curing formulas, applied to our Sentinel-2 composites, put grass at 80-86% cured in December and 85-97% in February.
   - Field data from Jhansi (Sehima/Heteropogon/Themeda rangeland) give the same curve. Herbage dry-matter content is 42% in Nov, 57% in Dec, 60% in Jan and 71% in Feb, which is a whole-sward moisture of 137%, 75%, 65% and 41%. On the Scott-Burgan scale that is about 0%, 50%, 60% and 88% cured.
3. **"Grass already burned in January" explains very little.** Only 4.9% of grass pixels burn before 15 February in an average season. The earlier edge test also dropped ground already burned that season and still found the effect.
   - Some seasons had a lot of early grass burning: 31-32% of 2018 and 2021 grass burns, and 21-24% in 2019 and 2023, came before 15 Feb. Even then, most grass is still unburned in March.
4. **Grazing shows up in how much burns, not in the mid-February switch.**
   - Open grass within 1 km of buildings burns in 20.7% of pixel-seasons, against 40.9% beyond 3 km. That is a 0.51x gradient. Deciduous goes 30.7% to 53.3% (0.58x).
   - But the grass/deciduous hazard ratio after 15 Feb is 0.65-0.79 at every distance. It is no lower near villages.
   - A Sentinel-2 dry-matter index (NDTI) shows no "eaten-out near villages" signal. Near grass actually has slightly *higher* NDTI in April (0.084) than far grass (0.063).
   - Published Indian data show how large grazing removal can be:
     - On the Vindhyan plateau (Heteropogon-Chrysopogon savanna), grazed plots produced 49-99 g/m²/yr of above-ground growth, against 437-703 g/m²/yr ungrazed at the same site (Ranitali). That is an 85-90% loss.
     - At Jhansi, 9 goats/ha took standing herbage from 3.63 t/ha in November to 1.89 t/ha in February.
5. **Best explanation [inference]: class 4 is thin, patchy, early-cured grass on poor, much-grazed ground.**
   - Its Feb-Apr NDVI of 0.13-0.18 is close to bare soil. Its dry-matter index is the lowest of the vegetated classes.
   - Fire's own estimate of its fuel is 1.0-2.4 t/ha (`fuel-map/.../inversion`).
   - It is ready to burn first, so it carries the few early fires. From February the new, continuous teak and deciduous leaf litter (2-3 t/ha, spread evenly) becomes the better carrier, and fires stop where that bed thins into open ground.
   - Scar detection bias is small. A scar was found for 85.0% of FIRMS alerts with more than 60% grass within 200 m, against 89.0% for alerts with less than 10% grass.
6. **Numbers for the grass layer [inference, from sections below]:**
   - Standing load at fire time: about 1.0-1.5 t/ha central, 0.5-1.0 near villages or on heavy grazing, 1.5-2.5 on far or protected ground.
   - The October peak is roughly 1.5-2x those numbers, falling about 40-50% to February through grazing and decay. This matches Jhansi's 48% fall from November to February.
   - Curing by month: Nov 45%, Dec 60-80%, Jan 70-75%, Feb 85-90%, Mar and later 95-100%.
   - Fuel depth 10-30 cm. Bulk density about 0.7-0.8 kg/m³ (Scott-Burgan GR1 and GR2).
   - Model it as GR1 near villages and GR2 elsewhere, both dynamic, or use the CSIRO grass model with the "eaten-out" or "grazed" coefficients.

---

## Part A. Our own data (DATA, computed 16 Oct 2026)

### A1. Which class burns when (`grass_timing.py`, output `grass_timing_out.txt`, `grass_timing_windows.csv`, `grass_timing_by_season.csv`)

**Method.**
- For each season, the first-burn date of every 20 m pixel is the date of the earliest v2 FIRMS event outline that covers it. Seasons run 1 Nov to 31 Jul, 2017-2026.
- "Hazard" is the share of pixels still unburned at the start of a window that burn during it.

**Hazard (% of still-unburned pixels burning in window), 2017-2026 pooled:**

| Window | Deciduous tree | Green tree | Open grass/low | Sparse/bare |
|---|---|---|---|---|
| Nov-Dec | 0.14 | 0.03 | **0.97** | 2.10 |
| Jan | 0.62 | 0.03 | **1.57** | 1.36 |
| 1-14 Feb | 1.74 | 0.18 | **2.40** | 1.68 |
| 15-28 Feb | **3.28** | 1.33 | 2.87 | 1.61 |
| Mar | **28.86** | 25.83 | 19.18 | 12.17 |
| Apr | 13.60 | **17.39** | 8.20 | 5.23 |
| May-Jun | 1.34 | 1.16 | 0.84 | 0.49 |

- Share of each class burned per season: deciduous 42.8%, green tree 40.4%, grass 32.0%, sparse 22.6%.
- First-burn dates for grass: p10 4 Feb, p25 2 Mar, median 18 Mar, p75 29 Mar. Deciduous: 25 Feb, 10 Mar, 22 Mar, 30 Mar.
- In mixed cells (at least 20% each of deciduous and grass; 13,250 cell-seasons):
  - burned share: deciduous 37.8%, grass 32.5%;
  - burned before 15 Feb: deciduous 2.81%, grass 4.81%.
- Seasons differ a lot. Grass burns before 15 Feb, as a share of that season's grass burns: 2018 31.5%, 2021 30.7%, 2019 24.3%, 2023 21.3%. In 2020, 2022 and 2024 it was 0.7-3%.

**Caveats.**
- All pixels inside one outline share the event date, so the order within a fire is lost.
- Class 4 is defined partly by being dry in Mar-Apr (NDVI below 0.25), so "cures early" is partly built into the class.
- Jan-Feb grass scars may be under-detected. See A4: the bias is small.

### A2. Is grass still green? (`grass_timing.py`, `grass_curing_indices.py`)

**Data.** Monthly Sentinel-2 median composites from Sep 2023 to May 2025, pooled by month (`fuel-map/ratapani/work/monthly*/`). Only pixels unburned in both the 2024 and 2025 seasons are used, so burn scars do not darken the medians.

| Month | NDVI decid. | NDVI grass | NDMI decid. | NDMI grass | % grass NDVI<0.25 | Curing, MODIS "Method B", grass / decid. | MapVictoria, grass / decid. |
|---|---|---|---|---|---|---|---|
| Oct | 0.458 | 0.406 | 0.132 | 0.071 | 0.0 | 61 / 54 | 66 / 58 |
| Dec | 0.354 | 0.254 | 0.051 | -0.050 | 46 | 80 / 67 | 86 / 71 |
| Jan | 0.315 | 0.225 | 0.005 | -0.096 | 71 | | |
| Feb | 0.253 | 0.183 | -0.067 | -0.138 | 94 | 85 / 79 | 97 / 87 |
| Mar | 0.175 | 0.141 | -0.135 | -0.169 | 99.8 | | |
| Apr | 0.155 | 0.132 | -0.142 | -0.164 | 99.8 | 89 / 89 | 100 / 100 |
| May | 0.224 | 0.171 | -0.088 | -0.134 | 95 | 85 / 81 | 98 / 91 |

- Curing formulas are applied by swapping sensors: MODIS b2/b6/b7 become S2 B8A/B11/B12. They are not calibrated here, so read them as relative curves.
- Spread coefficients for grass (MODIS Method B curing put through the Cruz 2015 function): 0.38 in Oct, 0.82 in Dec, 0.89 in Feb, 0.93 in Apr.
- **Reading.** Grass is never greener than trees. It is mostly cured by December and fully cured by March. Greenness cannot explain why fires stop at it.

### A3. Grazing proxy: distance to buildings (`grass_grazing_proxy.py`)

| Class | Distance (cell to nearest Open Buildings building) | Burned % of pixel-seasons | Hazard Nov-14 Feb | Hazard 15 Feb-Mar | Hazard Apr-Jun |
|---|---|---|---|---|---|
| Deciduous | <1 km | 30.7 | 0.98 | 22.6 | 9.5 |
| Deciduous | >3 km | 53.3 | 5.25 | 36.2 | 22.8 |
| Grass | <1 km | 20.7 | 2.07 | 14.8 | 5.0 |
| Grass | >3 km | 40.9 | 9.47 | 24.9 | 13.1 |

- Grass/deciduous hazard ratio is 1.8-2.5 before 15 Feb and 0.65-0.79 from 15 Feb to March, at every distance.
- Median first-burn date for grass: 22 Mar within 1 km, 11 Mar beyond 3 km. Far grass burns earlier.
- Median NDTI for grass in April: 0.084 within 1 km, 0.063 beyond 3 km. NDVI is nearly the same at all distances.
- **Reading.**
  - Both classes burn less near villages. People also fight fires, create breaks and graze there, so this is not grazing alone.
  - The switch in mid-February happens everywhere, so grazing is not what drives it.
  - [inference] Grazing is real but not visible in 10-20 m optical indices. Low grass under heavy grazing is mixed with soil whatever its load.

### A4. Is there a scar-detection bias in grass?

For FIRMS alerts in v2 (`firms_alert_scar_lookup.csv`), I took the share of open grass within about 200 m of the alert point.

| Grass share | Alerts | Scar found |
|---|---|---|
| ≤10% | 4,750 | 89.0% |
| 10-25% | 3,940 | 88.4% |
| 25-40% | 2,780 | 87.6% |
| 40-60% | 2,298 | 86.0% |
| >60% | 1,251 | 85.0% |

- For Feb-Apr alerts only: 89.6% at ≤10% grass, 86.4% at >60%.
- **Reading.** Grass scars are about 4 points harder to find. That is too small to explain a grass share 0.83x inside scar edges against outside them (`mahua_and_deciduous_checks.md`).

---

## Part B. Measured grass loads and seasonal curves (India and similar dry tropics)

### B1. Mahanta, Pailan & Verma 2012. *Nutritional status of herbage and goats under different grazing management practices on semi-arid rangeland vegetation.* Indian J. Anim. Sci. 82(9):1046-1050. ICAR-IGFRI Jhansi. https://epubs.icar.org.in/index.php/IJAnS/article/view/23664 **FULL**

**Site and method.** 3 ha of Bundelkhand rangeland at Jhansi.
- Grasses: Cenchrus ciliaris, Chrysopogon fulvus, Dichanthium annulatum, Heteropogon contortus, Sehima nervosum and Themeda quadrivalvis.
- Grazed by 9 goats/ha for 6.5-8 h/day from November to February.
- Herbage clipped to 2.5 cm stubble in four 0.5 x 0.5 m quadrats each month.

**Table 2:**

| | Nov | Dec | Jan | Feb |
|---|---|---|---|---|
| Herbage mass, kg DM/ha | 3,631 | 2,756 | 2,326 | 1,890 |
| Grasses (%) | 83.4 | 78.7 | 73.1 | 65.4 |
| Litter (%) | 2.8 | 3.7 | 6.8 | 9.8 |
| Dry-matter content of herbage (%) | 42.2 | 57.2 | 60.4 | 70.7 |
| → moisture, % of dry weight [computed] | 137 | 75 | 65 | 41 |
| → Scott-Burgan curing equivalent [inference] | ~0% | ~50% | ~60% | ~88% |

- Herbage fell 48% from November to February, through grazing plus seasonal decline.
- The three grazing systems (continuous 2,365, rotational 2,677, deferred 2,910 kg/ha) did not differ significantly.

**Concrete action for us** (fuel map, spread):
- Use this as the shape of the grass curve from Nov to Feb: about 3.6 → 2.8 → 2.3 → 1.9 t/ha on protected, grazed rangeland in the same grass cover as central India.
- Ratapani class 4 is poorer (inversion 1.0-2.4 t/ha at fire time). So scale the curve to about 0.4-0.6x for the open forest blanks: Nov ~2.0, Dec ~1.6, Jan ~1.4, Feb ~1.1 t/ha. [inference]
- Use the moisture column as the live-herb moisture input for dynamic GR models in Dec-Feb (75% → 41%).
- Expected effect: grass fuel set right in January-February, the window when grass is the main carrier.

### B2. Pandey & Singh, ORNL DAAC "NPP Grassland: Vindhyan, India, 1986-1989, R1" (doi:10.3334/ORNLDAAC/197). Data from Pandey & Singh 1992, *Ecology* 73:2007-2021. https://daac.ornl.gov/NPP/guides/NPP_VND.html **PARTIAL**

- Data-set guide read in full. Only the sample rows of the data files were read, because the files need an Earthdata login.
- The Ecology paper itself was not read (ABSTRACT ONLY via the guide).

**Site.** Three derived savannas on the Vindhyan plateau (24.2-24.4 N, 82.9-83.1 E, 315-485 m).
- Rain 926-1,145 mm.
- Grasses: Heteropogon contortus, Chrysopogon fulvus, Bothriochloa pertusa. Three dominant perennials made up 83-94% of live shoot biomass.
- The savannas were derived from dry forest over 30-40 years of heavy uncontrolled grazing.
- Treatments: ungrazed; grazed for 30-40 years; grazed then fenced for 2-6 years.
- Monthly harvests over two annual cycles, 1-m² plots.

**Numbers.**
- Ungrazed ANPP at the three sites: 377-664 g/m²/yr. At Ranitali: 590 (1986/87), 703 (1987/88), 437 (1988/89, peak biomass only).
- Grazed ANPP at Ranitali: 99, 79 and 49 g/m²/yr, about 10-15% of ungrazed.
- Temporarily fenced: Ranitali 614 and 732; Hathinala 819.
- BNPP: ungrazed 510-727; grazed Ranitali 285-323.

**Concrete action for us** (fuel map):
- This is the best Indian measure of how far grazing can cut grass fuel on Vindhyan geology, which is Ratapani's own range.
- Long-grazed ground grows only 0.5-1.0 t/ha/yr above ground. Two to six years of protection brings it back to 6-8 t/ha/yr.
- Set a floor of about 0.5 t/ha for heavily grazed open ground near hamlets, and allow up to about 2.5 t/ha where grazing is light. [inference]
- If an Earthdata login is available, the monthly files (`vnd1_npp.txt`, `vnd2_npp.txt`) are the only monthly live/dead Indian savanna series for this geology. Pull them.

### B3. Singh & Yadava, ORNL DAAC "NPP Grassland: Kurukshetra, India, 1970-1971, R1" (doi:10.3334/ORNLDAAC/193). https://daac.ornl.gov/NPP/guides/NPP_KRK.html **PARTIAL**

- Guide read in full; monthly data behind Earthdata login.
- Site: Panicum-Dichanthium grassland, kept open by grazing and annual burning.
- Monthly harvests, 10 plots per date. Sample rows (g/m²):

  | | Live | Standing dead | Litter |
  |---|---|---|---|
  | May 1970 | 437 | 155 | 133 |
  | Jun | 773 | 203 | 123 |
  | Jul | 1,103 | 196 | 116 |

- ANPP 2,407 g/m²/yr; peak rainy-season ANPP 1,706.
- **Concrete action:** an upper bound only. This is a fertile alluvial site, about 10x Vindhyan savanna. Do not use it for Ratapani values.
- Its use is to show the live→standing dead→litter structure. In May, standing dead plus litter was 288 g/m² under annual burning.

### B4. Kar 2024. *Effect of climate on the density value and primary productivity of an Indian grassland community.* Plant Archives 24(2):1009-1016. **FULL**

- Odisha site (1,906 mm rain). Its own production figures (grass 3,290 g/m²/yr) look implausibly high and should not be used.
- Its Table 3 is a useful compilation of Indian grassland NPP (g/m²/yr):

  | Site | Grass cover | Rain (mm) | NPP |
  |---|---|---|---|
  | Varanasi | Dichanthium | 725 | 1,420 |
  | New Delhi | Heteropogon | 800 | 1,330 |
  | Kurukshetra | Panicum | 770 | 2,980 |
  | **Ujjain, MP** | Dichanthium | 1,030 | **989** |
  | **Ratlam, MP** | Sehima | 1,257 | **846** |
  | Berhampur | Aristida | 1,200-1,355 | 929-1,447 |
  | Phulbani | Heteropogon | 1,763 | 809 |

- **Concrete action:** Ujjain (Misra 1973) and Ratlam (Billore & Mall 1977) are the two MP grassland NPP studies, and they are the right source papers to find in print. The Ratlam Sehima value of 846 includes roots. If ANPP is about half, that is roughly 4 t/ha/yr above ground on ungrazed protected plots. [inference]

### B5. *Grass species composition in tropical forest of southern India* (Mudumalai; authors and year not captured in my read; check the article page). J. Threatened Taxa, article 7296. https://threatenedtaxa.org/index.php/JoTT/article/view/7296 **FULL** (via fetch)

**Method.** 1,749 plots of 1 m², 2004-2007. Grass measured as % cover, not biomass.

**Numbers.**
- Mean grass cover: dry deciduous 18.8 ± 22.5%, moist deciduous 17.5%, thorn forest 12.7%.
- Highest mean: 46% in burnt dry deciduous in the first wet season. Moist deciduous in the dry season: 27.7%.
- Dry deciduous grasses: Themeda cymbaria, T. triandra, Heteropogon contortus. Aristida and Eragrostis are taken as signs of heavy grazing in thorn forest.
- Regression r² = 0.23. Shrub density has the strongest negative effect; previous-month rain the only positive one.
- Fire had no significant effect (p = 0.49).

**Concrete action** (fuel map): Grass cover in deciduous forest is low and patchy, at about 19% mean with a large SD. Do not give the whole of class 4 a continuous grass bed. Use a continuity factor of about 0.3-0.5 in spread runs, or GR1. [inference]

### B6. Mondal & Sukumar 2016 (Mudumalai grass gain), already in `fuel_load_values_fullread.md`

Not repeated here: grass rebuilds by about 0.45-0.75 t/ha in the year after fire, plus about 0.9 t/ha per unburned year, capped near 2.5 t/ha.

That cap matches the Jhansi November peak once it is scaled to poorer ground. [inference]

### B7. Miranda, Bustamante & Miranda 2002. *The fire factor.* In: Oliveira & Marquis (eds), *The Cerrados of Brazil*, ch. 4. https://ava.icmbio.gov.br/pluginfile.php/4592/mod_data/content/19765/2002-The_Fire_Factor.pdf **FULL**

- Fine fuel (<6 mm, up to 2 m tall): 0.6-1.2 kg/m² (6-12 t/ha). The herbaceous layer is 97% of the fuel in campo sujo, 90% in cerrado sensu stricto and 85% in cerradão.
- **Table 4.1** (prescribed fires, IBGE reserve):

  | | Campo sujo | Cerrado s.s. | Cerradão |
  |---|---|---|---|
  | Herbaceous load before fire (kg/m²) | 0.64-0.96 | 0.59-1.11 | 0.50-0.75 |
  | Dead share of fuel (%) | 69-75 | 61-76 | 50-69 |
  | Consumption (%) | 91-93 | 77-97 | 75-76 |

- The herbaceous layer is 94% of the fuel consumed. Flame height in savanna fires is 0.8-2.8 m.
- **Concrete action** (spread, fuel map):
  - Use "dead share 70-75% in the late dry season" and "about 90% consumed" for open grass. Ratapani grass is also more cured than this (85-100% from February).
  - Cerrado loads are 4-8x Ratapani's. They come from less-grazed savanna with more rain and multi-year build-up, so use them as an upper bound only.

### B8. Moustakas & Davlias 2021, *Minimal effect of prescribed burning on fire spread rate and intensity in savanna ecosystems*, SERRA (arXiv 2005.07593). Uses the Kruger experimental burn plots described in Govender, Trollope & van Wilgen 2006 (J. Appl. Ecol. 43:748). **FULL** (arXiv)

- 956 plot burns over 22 years. Grass fuel load was estimated before each fire with the disc pasture meter. Moisture came from four 100 g sward samples per fire.
- Fuel load (kg/ha) = 3,227 + 241.9 x fire return interval in years. R² is only 1.9%: years since fire barely predicts load.
- Feature importance for spread rate: fuel moisture 21%, RH 15%, wind 14%, previous rain 14%, fuel load 13%, fire return interval 3.5%, season up to 6%.
- From the Govender 2006 abstract (ABSTRACT ONLY): grass fuel moisture averages 28% in winter and 88% in summer. Intensity ranged 28-17,905 kW/m; six-year intervals averaged 638 kW/m against 1,969 kW/m for shorter ones.
- **Concrete action** (spread, burn-probability maps):
  - Grass-fire spread depends on moisture and weather far more than on how long the fuel has built up.
  - In Ratapani, do not let a "time since last burn" grass term carry much weight in the spread model. Use the curing/moisture term (A2, B1) instead.
  - Expected effect: avoids over-fitting a fuel-age term that the 956-burn data say is weak.

### B9. Chand, Biradar & Kautkar 2021. *Fodder status in drought year and the practice of free range grazing in Bundelkhand region of India.* Indian J. Anim. Sci. 91(9):760-764. https://epubs.icar.org.in/index.php/IJAnS/article/view/116468 **FULL**

- 13 Bundelkhand districts in UP and MP. In the 2015-16 drought year the region was 42% short of dry matter.
- 67% of 43 farmers surveyed practise free-range grazing ("Anna Pratha"). 63% give summer fodder and water shortage as the reason.
- Livestock requirement: 7 kg DM per adult livestock unit per day. Forests supply only 3.8% of available dry matter on average (0.9-6.9% by district category).
- **Concrete action** (fuel map, grazing removal) [inference]:
  - A removal rate to test: grazing load (ALU per ha of forest fringe) x 7 kg/day x the share eaten in forest x grazing days.
  - Example: 0.5 ALU/ha, 50% of intake from the forest, 120 days gives about 0.2 t/ha per season. Heavy grazing near hamlets would be 2-5x that.
  - This puts near-village removal at 0.2-1 t/ha, the same size as the whole standing grass load. That fits the near-village 0.5-1.0 t/ha floor.
  - Cattle density per beat (livestock census by village) would turn this into a map. This is not checked against Ratapani data.

---

## Part C. Satellite methods for grass amount and curing

### C1. Chaivaranont, Evans, Liu & Sharples 2018. *Estimating grassland curing with remotely sensed data.* NHESS 18:1535-1554. https://doi.org/10.5194/nhess-18-1535-2018 **FULL**

- The operational Australian formulas, with MODIS bands (b2 858, b6 1640, b7 2130 nm):
  - **Method B** (Newnham et al. 2010): C = 237.31 - 190.14·NDVI - 142.66·(ρ7/ρ6).
  - **MapVictoria** (Martin et al. 2015): C = 113.80 - 88.41·NDVI - 67.71·GVMI, with GVMI = ((ρ2+0.1) - (ρ6+0.02)) / ((ρ2+0.1) + (ρ6+0.02)).
- Accuracy against ground curing:
  - plain NDVI: r² 0.50, RMSE 16.4%;
  - spread-based relative greenness: r² 0.62, RMSE 14.2%;
  - range-based relative greenness: r² 0.57;
  - adding microwave vegetation optical depth (VOD): r² up to 0.67 calibrated, 0.44-0.55 evaluated.
- Relative greenness was very sensitive to the time window chosen.
- Field curing by the levy-rod method: RMSE 13.5% against destructive sampling.
- McArthur Mk4 grass curing factor: f(C) = exp(-0.009432·(100-C)^1.536).
- **Concrete action** (fuel map, prediction):
  - Done here with Sentinel-2 swapped in (A2).
  - Next step: compute Method B per pixel per 5-day Sentinel-2 scene for each season, not as a pooled median. That gives a dated curing map, so "grass is X% cured on day d" becomes a feature for the 2-day model and an input for spread.
  - Use a fixed window per pixel (e.g. that season's Sep-Oct max and the 5-year May min) to avoid the window sensitivity.
  - Effort: half a day on the existing Planetary Computer pipeline (`fuel-map/ratapani/scripts/s2monthly_re.py`).

### C2. CSIRO PyroPage No. 6 (2015), *Improving the prediction of rate of fire spread in partially cured grasslands*, summarising Cruz et al. 2015 and Kidnie et al. 2015 (IJWF 24:828-848). https://research.csiro.au/pyropage/wp-content/uploads/sites/17/2016/03/CSIRO-PyroPage-Issue-6-Improved-grass-curing-function.pdf **FULL**

Also the CSIRO Spark model-library page with the model code: https://research.csiro.au/spark/resources/model-library/csiro-grassland-models **FULL**. The two IJWF papers themselves are ABSTRACT ONLY.

- Grass fires kept spreading at **20-30% curing**. The old assumption was more than 50%.
- Between 50% and 80% curing, fires spread up to 10x faster than the old functions predicted.
- Visual curing assessments over-estimate curing, because senescing but still-moist grass is counted as dead.
- Curing coefficient (Cruz 2015): 0 when C < 20; otherwise 1.036 / (1 + 103.989·exp(-0.0996·(C-20))).
- Head-fire rate of spread (km/h), wind U at 10 m in km/h:
  - U ≥ 5: (a + b·(U-5)^0.844) · moisture coefficient · curing coefficient.
  - U < 5: (a_slow + b_slow·U) · moisture coefficient · curing coefficient.
  - Pasture coefficients (a_slow, a, b_slow, b): eaten-out 0.027, 0.55, 0.1045, 0.3575; cut/grazed 0.054, 1.1, 0.209, 0.715; natural 0.054, 1.4, 0.269, 0.838.
  - Woodland multiplies by 0.5 and open forest by 0.3.
- Moisture: dead grass moisture GMf = 9.58 - 0.205·T + 0.138·RH (McArthur). The coefficient is exp(-0.108·GMf) for GMf ≤ 12; otherwise 0.684 - 0.0342·GMf (U ≤ 10) or 0.547 - 0.0228·GMf.
- **Concrete action** (spread):
  - A ready grass spread rule for the physics baseline and for features in the learned restart model.
  - Use "eaten-out" coefficients for open grass within about 1 km of hamlets and "grazed" elsewhere, with the woodland factor 0.5 under open canopy.
  - Our curing is 80-100% from December, so the curing term barely limits spread in fire season.
  - [inference] The mid-February drop in grass burning is therefore not a curing effect. It has to come from load or continuity, which supports Headline 5.

### C3. Scott & Burgan 2005. *Standard fire behavior fuel models.* USDA FS RMRS-GTR-153. https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr153.pdf **FULL** (relevant sections: dynamic models, Table 7, GR and GS pages)

**Dynamic transfer.** At live-herb moisture of 120% or more, all herb load stays live. At 30% or less it is all moved to dead. Between, it moves linearly.

**Table 2 (curing ↔ live herb moisture):**

| Curing | Live herb moisture |
|---|---|
| 0% | ≥120% |
| 25% | 98% |
| 33% | 90% |
| 50% | 75% |
| 66% | 60% |
| 75% | 53% |
| 100% | ≤30% |

**Table 7 (t/ac; x 2.24 for t/ha):**

| Model | 1-hr | 10-hr | Live herb | Live woody | Depth | Extinction moisture | SAV dead / herb (1/ft) |
|---|---|---|---|---|---|---|---|
| GR1 | 0.10 | 0 | 0.30 | 0 | 0.4 ft | 15% | 2200 / 2000 |
| GR2 | 0.10 | 0 | 1.00 | 0 | 1.0 ft | 15% | 2000 / 1800 |
| GR3 | 0.10 | 0.40 | 1.50 | 0 | 2.0 ft | 30% | 1500 / 1300 |
| GR4 | 0.25 | 0 | 1.90 | 0 | 2.0 ft | 15% | 2000 / 1800 |
| GS1 | 0.20 | 0 | 0.50 | 0.65 | 0.9 ft | 15% | 2000 / 1800 |
| GS2 | 0.50 | 0.50 | 0.60 | 1.00 | 1.5 ft | 15% | 2000 / 1800 |

- GR1 is "short, patchy, possibly heavily grazed" grass.
- In metric units: GR1 = 0.90 t/ha fine fuel over 12 cm, bulk density about 0.74 kg/m³. GR2 = 2.47 t/ha over 30 cm, about 0.81 kg/m³. [computed]

**Concrete action** (spread, fuel map):
- Class 4 within 1 km of hamlets → GR1. Elsewhere → GR2, scaled to the B1 load.
- Live-herb moisture by month from Table 2 using our curing (A2): Dec about 55-60%, Jan about 50%, Feb about 35-40%, Mar onward ≤30%.
- Under canopy, the teak-litter custom TL bed already in `fuel_load_values.md` stays as it is.

### C4. Zang et al. 2023. *The inversion modeling and aboveground biomass mapping of withered grass changes in the western grassland of Northeast China.* Front. Earth Sci. 10:1031098. https://doi.org/10.3389/feart.2022.1031098 **FULL**

- Dry-grass index DGI2 = (B11 - B12)/(B11 + B12), which is the NDTI. Correlation with field dry-grass fuel r = 0.678 (58 plots; 45 to fit, 13 to test).
- Best model: AGB (g/m²) = 12.745·exp(20.454·NDTI). Test r = 0.863, R² 0.745, RMSE 32.8 g/m².
- DGI1 (red band B4): r = -0.630.
- Monthly mean dry-grass fuel: Oct 203.8, Nov 285.7, Mar 263.7, Apr 155.6, May 90.5 g/m². Fuel falls through spring.
- **Applied to Ratapani class 4** (A2, `grass_curing_indices.csv`; uncalibrated transfer from a saline marsh):

  | | Oct | Dec | Feb | Apr | May |
  |---|---|---|---|---|---|
  | Grass NDTI | 0.183 | 0.135 | 0.099 | 0.075 | 0.089 |
  | Implied g/m² | 539 | 203 | 97 | 59 | 78 |

- The Oct and Dec values are not trustworthy, because green leaves inflate NDTI.
- The Feb-Apr values, about 0.6-1.0 t/ha, are in the right range against our inversion of 1.0-2.4 t/ha. [inference]
- **Concrete action** (fuel map): Keep NDTI in Feb-Apr as a relative grass dry-matter map within class 4. Scale it so the class mean matches the inversion's 1.0-2.4 t/ha. Do not use the Chinese absolute values.

### C5. Franke et al. 2018. *Fuel load mapping in the Brazilian Cerrado in support of integrated fire management.* Remote Sens. Environ. 217:221-232. https://dataserver-coids.inpe.br/queimadas/queimadas/Publicacoes-Impacto/documentos/2018_Franke_etal_FuelLoadmap_Cerrado_RSE.pdf **FULL**

**Method.** Mixture Tuned Matched Filtering on Landsat 8 and Sentinel-2, with three endmembers: green vegetation, dry vegetation (non-photosynthetic, NPV) and soil.

**Accuracy.**
- 120 field samples, each 5 plots of 0.5 x 0.5 m.
- Dry-vegetation score vs fine fuel: r² 0.81, RMSE 0.15 kg/m² (fuel = 1.342·score - 0.0867).
- Soil score: r² 0.65.
- Dry-vegetation plus soil together: adjusted r² 0.86, SE 0.075 kg/m².
- Representative savanna fuel 5.6 t/ha; 3.1 t/ha burned (median of 25 experiments).

**Practice.**
- Brazil's protected-area fire managers have used these maps since 2014.
- Burned-area maps are used alongside them, because high-soil pixels are ground burned earlier that season.
- Under dense canopy the maps are less reliable.

**Concrete action** (fuel map):
- The most transferable method for grass amount with no plots of our own.
- Unmix our Feb-Apr Sentinel-2 composites into green, dry-matter and soil fractions within class 4. Take endmembers from the purest pixels: bare rock/soil in sparse class 5, and teak litter under leafless canopy in March for dry matter.
- Grass load is then about (dry-matter fraction / mean dry-matter fraction) x the class mean from the inversion.
- Expected effect: separates thin grass on rock from real grass beds inside class 4. That is the difference between a barrier and a carrier for the spread model.
- Effort: 1 day.

### C6. Other satellite sources (ABSTRACT ONLY)

- **Newnham, Verbesselt, Grant & Anderson 2011**, RSE 115:1456, doi:10.1016/j.rse.2011.02.005. Relative greenness from 8-day MODIS beat plain NDVI for curing at 25 Australian sites, 2005-09.
- **Li et al. 2021**, Int. J. Digital Earth, doi:10.1080/17538947.2021.1900938, and **Li et al. 2023**, doi:10.1080/17538947.2023.2248966. The MapVictoria curing algorithm run on Landsat 8 and Sentinel-2 instead of MODIS. Finer pixels help accuracy but there is variability between satellites. Read these before trusting our sensor swap.
- **Berger et al. 2020**, IGARSS (Kruger, elib.dlr.de/139902). Random forest on wet-season Landsat 8 and Sentinel-2 NDVI mosaics, against the park's annual disc-pasture fuel surveys. "Fairly reliable" annual fuel maps, slightly better than Sentinel-1 maps. [inference] Peak-season (Sep-Oct) NDVI within class 4 is a candidate predictor of next season's grass load.
- **Sentinel-1 / C-band** (Univ. Pretoria, repository.up.ac.za/handle/2263/75773). Backscatter drops after savanna surface fires, more weakly where woody cover is above 30%. Not tested here.

---

## Part D. How fire models treat cured grass

- Scott-Burgan dynamic GR models (C3). Curing moves herb load to dead. Moisture 120% means green; 30% or less means fully cured.
- CSIRO grassland model (C2). Explicit curing coefficient: no spread below 20% curing, about 0.5 at 60%, about 0.9 at 80%, and 1.0 at 100%. Grazing state changes the coefficients: eaten-out is about 0.4-0.5x natural.
- McArthur Mk4 GFDI (C1). f(C) = exp(-0.009432(100-C)^1.536), about 0.37 at 79% curing and 1 at 100%.
- CFA Victoria *Grassland Curing Guide* (2014). https://cfa.vic.gov.au/ArticleDocuments/1727/grassland-curing-guide.pdf.aspx **PARTIAL** (curing and fire-behaviour table read).
  - 0-30% cured: no spread.
  - 40-50%: maybe, carried by last year's dead thatch. Patchy, low flames.
  - 60%: fragmented front.
  - 70% and more: spread moderate to fast.
  - Full curing takes about 6-10 weeks after seed heads fully develop.
  - Dead grass moisture is 2-35% of dry weight; live grass is 30-260%.
- **[inference] for Ratapani.** On every one of these scales, open grass is fire-ready by December. So the spread model should not use curing as the reason fires stop at grass. Use a load and continuity term (C5, B5) and the measured switch in hazard (A1) instead.

---

## Datasets and code

| Item | What | Access | Use for |
|---|---|---|---|
| `r13_grass_code/grass_timing.py` (+ csv/txt) | Hazard by cover class and window; first-burn dates; pairs within cells; distance bands; monthly NDVI/NDMI/NDTI; scar-found rate by grass share | scratchpad (copy to `fsi/scouting/code/grass/`) | prediction features, spread barrier term |
| `r13_grass_code/grass_curing_indices.py` | Method B, MapVictoria, GFDI f(C), Cruz coefficient and Zang NDTI→AGB by class and month | scratchpad | grass curing input |
| `r13_grass_code/grass_grazing_proxy.py` | NDTI and hazard by distance to buildings, grass vs deciduous | scratchpad | grazing term |
| ORNL DAAC NPP Vindhyan (ds 197), Kurukshetra (ds 193) | Monthly live, dead and litter g/m², grazed vs ungrazed | Earthdata login (free) | grass curve and grazing removal on Vindhyan geology |
| CSIRO Spark grassland model code | Curing, moisture and rate-of-spread functions | research.csiro.au/spark | spread baseline |
| Scott-Burgan GTR-153 Table 7 | GR/GS parameters, dynamic transfer | fs.usda.gov | spread fuel models |
| Sentinel-2 L2A B8A/B11/B12/B04 (Planetary Computer) | Per-scene curing and NDTI, unmixing | existing `s2monthly_re.py` | dated curing map; dry-matter fraction |
| Open Buildings cell distances | Grazing and people proxy | `fsi/scouting/data/openbuildings_cell_features.csv` | near-village grass multiplier |
| Livestock Census 2019 (village level) | Cattle, buffalo and goat counts | DAHD (not fetched) | grazing removal map (B9) |

---

## Ranked action list

| # | Action | Thread | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Grass layer v1 for class 4.** About 1.2 t/ha central at fire time. 0.6 within 1 km of buildings, 1.8 beyond 3 km. Monthly multiplier 1.8 Oct, 1.5 Dec, 1.25 Jan, 1.0 Feb-Apr (Jhansi shape, B1). Floor 0.5 (Vindhyan grazed, B2), cap 2.5 (Mondal & Sukumar). | fuel map | `cover_phenology_10m.tif`, Open Buildings distance | Fixes the 2-4x under-load. Matches the inversion's 1.0-2.4 t/ha. | 0.5 day |
| 2 | **Cover class x season window as a spread and restart feature.** Grass hazard 2x deciduous before 15 Feb and about 0.7x after (A1). | spread, burn-probability maps | class share per cell, day of season | Puts the measured switch into "where next" and stopping. Likely small but real for Jan-Feb fires. [inference] | 0.5 day |
| 3 | **Same interaction for the 2-day model.** Grass share x (day < 15 Feb), and far-grass share (>2 km from buildings) x early season. | prediction | cell features | Better early-season ranking. Jan-mid Feb is about 14% of ignitions (566 of 4,077), the hardest part of the season. Gain probably +0.5-1 point recall in that window. [inference] | 0.5 day |
| 4 | **Dated curing map** from per-scene Sentinel-2: Method B and relative greenness with a fixed per-pixel window (C1). | fuel map, prediction | S2 B8A/B11/B12/NDVI per scene | Replaces fixed month curves with year-specific curing. Explains years like 2018 and 2021 with heavy early grass burning. | 0.5-1 day |
| 5 | **Green/dry-matter/soil unmixing within class 4** (Franke method, C5), scaled to the inversion mean. | fuel map, spread | Feb-Apr S2 composites | Separates barrier ground (rock/soil) from carrier grass. Sharper spread edges. | 1 day |
| 6 | **Spread fuel models:** GR1 near villages, GR2 elsewhere, dynamic, with live-herb moisture from curing (C3). Or the CSIRO grass rate of spread with eaten-out/grazed coefficients and woodland factor 0.5 (C2). | spread physics baseline | layers 1 and 4 | A fairer physics baseline. The learned model already wins, so the gain is mainly a credible comparison. | 0.5 day |
| 7 | **Do not use curing or greenness to explain why fires stop at grass.** Use load and continuity. | spread | none | Avoids a wrong mechanism in the burn-probability maps. | 0 |
| 8 | **Early-season patrol emphasis** on open grass beyond 2 km from hamlets, 1 Jan-15 Feb. Hazard is 6.6-9.5% there against 1-3% for nearby deciduous (A3). | patrol pilot | layers 1 and 2 | More early fires seen per patrol-day. Test in the calendar-vs-forecast comparison. | 0.25 day |
| 9 | **Pull the ORNL monthly files** (Earthdata login) and search for Misra 1973 (Ujjain) and Billore & Mall 1977 (Ratlam) in print or IGFRI. | fuel map | none | Firmer monthly live/dead values for MP grass. | 1-2 h plus a login |
| 10 | **Grazing removal map** from village livestock counts: ALU x 7 kg/day x forest share x days (B9). | fuel map | Livestock Census 2019 | Turns the near/far multiplier into a mapped removal. Only worth it if 1-3 show grass matters. | 1 day |

**Not reachable this round:**
- WII Panna ungulate and biomass thesis (WII repository returned 503 and connection resets).
- ICAR height-weight paper for Sehima-Dichanthium grasses (download link broken). It would give bulk density and depth.
- Pandey & Singh 1992 *Ecology* and Govender et al. 2006 *J. Appl. Ecol.* (paywalled).
- Kanha grassland studies (WII ENVIS 2015; 1982 thesis), which exist as records only.
