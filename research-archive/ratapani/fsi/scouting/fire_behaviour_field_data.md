# Measured fire behaviour in dry deciduous, teak and similar litter fires: field and lab numbers, and how they compare with ours (scouting round 9, topic "behaviour", 15 Oct 2026)

> **Correction (15 Oct 2026, FSI thread): which front speed to compare against.** The "VIIRS median of 70 m/h" used in this note comes from the spread thread (ratapani/spread/README.md: median advance 926 m between passes 12.5 h apart, 51-98 m/h). That README itself calls it envelope growth: several fronts plus 375-750 m of pixel jitter. The fuel thread's pixel-footprint-corrected pass-to-pass speed (fuel-map/ratapani/timing/README.md) is the better observed number: a median of 24 m/h (IQR 10-56, 90th percentile 136), or 30 m/h (IQR 12-62) where advance is measurable at all.
> **Update (09:45Z, fuel thread):** the 24 m/h was measured inside the research burn-label rasters, which are about 2.4x smaller than the grown scar outlines that are now the project standard. Treat 24 m/h as a lower bound, superseded. Early back-simulation on the grown outlines points to the 70-100 m/h envelope. The final speed will come from the fuel thread; until then the comparison below is provisional.
> **Spread thread (09:45Z, its README 4b):** the model targets 24-30 m/h. Its final loose bed (2.5 kg/m3, 3.0 t/ha, ROS x2) runs 30-39 m/h at noon and less at night. On the grown outlines it reaches the scar area after a median 26 h, so it reads them as longer fires, not faster ones. The fuel thread's back-simulation is still to report.
> Read against the corrected numbers:
> - The observed fronts sit at the slow end of the field range. They match calm or backing fires (12-36 m/h) and damp-teak head fires (29-36 m/h), not the Thai afternoon head fires.
> - Junpen's 62-72 m/h at 4-6% moisture is an afternoon head-fire peak. A 12-h average including slow night spread would be lower.
> - The fuel thread's back-simulation suggests spread must be about 2-3x faster to fill the larger grown scars, which would land near 70. That gap (observed fronts vs grown scar size) is for the fuel and spread threads to reconcile. Possible causes are fires that started before VIIRS saw them, several fronts, or human relighting [inference].
> - The Rothermel conclusion changes. On a 4 kg/m3 bed, calm, at 5% moisture, this note's check gives 15-18 m/h, which is already close to the corrected 24 m/h. A large multiplier is needed only to reach the scar-filling ~70 m/h.

Scope: measured rate of spread (ROS), flame length, fireline intensity, residence time, burn-out, moisture thresholds, slope and fuel consumption from field burns and lab litter beds, plus pre-fire litter loads in central and eastern India. **This note does not repeat** the sources already read in `teak_vs_mixed_fuel_fullread.md` (Ramos-Rodríguez 2026 Ecuador teak, Junpen 2013 Thailand, Chernkhunthod/Akaakara, Saharjo 2017 Java), `fire_spread_models_fullread.md` §8 (Saha 2002 Gadchiroli) or `fuel_load_values*.md` (Jhariya 2017, Kittur 2014 abstract, Kodandapani). Those numbers do appear in the summary table, marked "see note".

Reading marks: **FULL** = whole text read; **PARTIAL** = the sections holding the numbers were read; **ABSTRACT ONLY** = abstract or snippet only. Anything marked [inference] is my reasoning, not a measured value. Scripts are in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9code_behaviour/` (`rothermel_check.py`, `teak_beds.py`, `kk.py` for the Krishikosh thesis repository, `upw.sh`, `s2.sh`).

## Headline findings

1. **Teak litter beds are loose, as the fuel thread assumed.** Ten measured teak-plantation beds (Ecuador 2019) had a bulk density of **3.4–5.1 kg/m³** (mean 4.1), a load of 0.58 kg/m² and a depth of 14 cm. A Thai dry dipterocarp bed comes out at about 3.7 kg/m³ (4.64 t/ha dead fuel over 12.6 cm). Lab litter beds pressed to field thickness were 2.2–5.3 kg/m³. Our 2.5 kg/m³ is at the low end but within the measured range. A "compact" bed (≥8 kg/m³) is not what teak forests carry.
2. **Measured head-fire ROS in teak-bearing deciduous forest is 0.5–2.6 m/min (30–160 m/h)** under light wind and 4–12% dead fuel moisture. Means: Thai dry dipterocarp 1.89 m/min, Thai mixed deciduous 1.37 m/min, teak plantation 0.48–0.61 m/min (wetter fuel, near calm). The Junpen (2013) moisture–slope model, fitted on 80 Thai plots, gives **62–72 m/h at 4–6% moisture on flat ground**, close to the spread thread's envelope median of 70 m/h (but see the correction above: the pixel-corrected front median is 24 m/h). Calm or backing fires are 0.2–0.5 m/min (12–30 m/h), close to the fuel thread's 24 m/h.
3. **Rothermel with teak-like inputs under-predicts field ROS by about ×1.4 (range ×0.7–2.6) across 5 datasets** [my own runs]. A single multiplier near 1.5–2.5 on a loose bed is consistent with field data. The spread thread's ×3 on a compact bed is partly correcting the packing, not only the model.
4. **Moisture.** Measured dead leaf moisture at burn time was 4–6% (Odisha, noon, dry mixed deciduous), 6.0–6.7% (northern Thailand, February–May) and 7–25% (Thai dry dipterocarp, January–March). **Sustained spread stopped above roughly 8–20%** in field tests: 8.4% in closed Thai deciduous forest early in the season, 9–20% in seasonal evergreen forest litter, 13.5% early and 23% late in the season in Amazon litter. Broadleaf litter beds dry with a **time-lag of 7–22 h**, not 1 h.
5. **Slope.** Litter-bed burns gave ×1.43 at 10° and ×3.0 at 20°. Junpen's model gives ×1.37 and ×1.93. My Rothermel run on a loose bed gives ×1.7–1.8 and ×4.0–4.5, so it **overstates slope at 20° by about 1.5×**.
6. **Consumption, residence time and patchiness.** Leaf litter is 80–99% consumed (twigs about 50%, duff about 88% in Chhattisgarh). The ground stays above 60 °C for 8–14 min in Thai dry dipterocarp burns. Inside the perimeter, only **60–68% of the area burns in early dry-season miombo fires, against 82–96% late in the season**.
7. **Indian measured fire behaviour is almost absent from the peer-reviewed literature.** The best Indian numbers found are in two university theses on Krishikosh: Odisha (Sahoo 2020) and Chhattisgarh (Kittur 2010, Jhariya 2010). Their numbers are listed below with caveats.

---

## Part A. Field burns in teak, dry dipterocarp and mixed deciduous forest

### A1. Himmapan, Kaitpraneet & Boonyawat 2006. *Behavior of burning fire in dry deciduous dipterocarp forest at Huai Kha Khaeng Wildlife Sanctuary.* Thai J. For. 25:112–124. **FULL**
Link: https://li01.tci-thaijo.org/index.php/tjf/article/download/255942/174792
- **Site and forest:** Huai Kha Khaeng WS, Uthai Thani, Thailand. Dry deciduous dipterocarp forest: grass, litter and undergrowth on nearly flat ground.
- **Design:** 12 plots of 30 × 30 m, 3 per month, burned January–April in 2003 and again in 2004 (the same plots re-burned). Point ignition at the centre. ROS was read every 2 min in 8 directions. Intensity and flame length come from Byram's equations, with heat yield 4,457 cal/g minus 667 cal/g radiation loss.
- **Fuel and weather (Table 1), 2003 vs 2004:**

| | Jan | Feb | Mar | Apr |
|---|---|---|---|---|
| Fuel load 2003 (t/ha) | 6.58 | 5.15 | 7.60 | 8.10 |
| Fuel load 2004 (t/ha) | 3.92 | 5.90 | 5.42 | 4.76 |
| Fuel moisture 2003 (%) | 54.3 | 58.7 | 31.2 | 59.0 |
| Fuel moisture 2004 (%) | 55.5 | 39.8 | 49.3 | 26.7 |
| Fuel height 2003 (cm) | 42.6 | 36.5 | 38.3 | 26.2 |
| Fuel height 2004 (cm) | 39.7 | 23.3 | 19.8 | 23.9 |

  - Moisture here mixes live undergrowth with dead fuel.
  - Air temperature 32–43 °C, RH 73–89%, wind 0–3.3 mph.
- **Fire (Table 2), mean and range:**

| | 2003 | 2004 |
|---|---|---|
| ROS (m/min) | 0.47 (0.22–0.77) | 0.44 (0.18–0.92) |
| Fireline intensity (kW/m) | 66.2 (27.6–152) | 44.3 (16.9–93.2) |
| Byram flame length (m) | 0.54 (0.37–0.80) | 0.45 (0.29–0.64) |
| Observed flame height (m) | 0.45 (0.19–1.80) | 0.37 (0.11–0.88) |

  - Monthly ROS in 2003 was 0.48, 0.56, 0.45 and 0.40 m/min for January to April.
  - Head-fire intensity was 1.5–2× back-fire intensity (84.6 vs 51.1 kW/m in 2003, 59.9 vs 33.3 in 2004).
  - Flame temperature averaged 136 °C (30–536 °C) in 2003 and 262 °C in 2004.
- **Correlations:**
  - Intensity vs total fuel load r = 0.758.
  - Flame length vs load r = 0.728.
  - ROS vs grass height r = 0.44.
  - ROS vs litter load r = −0.53.
- **Other numbers quoted in the paper:**
  - Natural fires at HKK in 2001–02 averaged 298 kW/m with 0.85 m flames.
  - Doi Suthep dry dipterocarp: ROS 0.28–6.41 m/min, mean 1.72.
  - Sakaerat, February: 2.0 m/min.
  - Kanchanaburi head fire: 2.81 m/min. The worst fire reached **6.96 m/min on a 45% slope**, and head fires ran **4.9× faster than rear fires** (Akaakara 2002).
- **For us:** a plot burned the year before carried about 25–40% less fuel and had lower intensity in every month. This matches Saha's "burned last year carries ¼ of the litter" rule. Rain a few days before a burn cut intensity noticeably.

### A2. Wiriya & Kaitpraneet 2009. *Fire behavior in dry deciduous dipterocarp forest at Huai Kha Khaeng WS.* Kasetsart J. (Nat. Sci.) 43:41–47. **FULL**
Link: https://li01.tci-thaijo.org/index.php/anres/article/download/244777/167251/841507
- **Design:** 21 plots of 200 × 200 m with a point ignition in the centre. ROS is the forward (head) spread.
- **Per-plot table (Table 1), mean (min–max):**

| Variable | Mean (min–max) |
|---|---|
| ROS (m/min) | **1.89** (0.57–3.94) |
| Fireline intensity (kW/m) | **190** (36–372) |
| Flame length (m) | **0.86** (0.41–1.22) |
| Dead fuel load (t/ha) | **4.64** (2.88–7.70) |
| Live fuel load (t/ha) | 0.73 (0.27–1.71) |
| Dead fuel moisture (%) | **12.4** (7–25) |
| Live fuel moisture (%) | 84.8 (43–122) |
| Fuel bed depth (cm) | **12.6** (5–25) |
| Air temperature (°C) | 34.4 (27–39) |
| RH (%) | 58.2 (37–75) |
| Wind (km/h) | **3.55** (1.41–5.47) |

- **Fitted models** (ROS in m/min):
  - wind: ROS = 0.3565·e^(0.4261·W), W in km/h, R² 0.74
  - depth: ROS = 0.2382·D^0.8078, D in cm, R² 0.62
  - live moisture: ROS = 7.1459·e^(−0.0175·M_live), R² 0.39
- **Bulk density [inference]:** about 4.64 t/ha ÷ 12.6 cm ≈ 3.7 kg/m³ dead fuel.
- **Also quoted:** another HKK study gave 0.95 m/min, 227 kW/m and 1.15 m; Sompoh (1998) gave 110.7 kW/m and 0.70 m.
- **Operational line:** a hand line at least 4 m wide holds these fires.
- **For us:** these are the closest analogue to fires that are pushed by light wind on a deep, loose, leafy bed. The wind model is very steep (×3.7 from 2 to 5 km/h). Do not extrapolate it beyond 5.5 km/h.

### A3. Sasirat, Diloksumpun & Wanthongchai 2014. *Application development for predicting fire spread rate in deciduous dipterocarp forest at HKK.* Thai J. For. 33(2):40–51. **PARTIAL** (English abstract and figures; the body is in Thai)
Link: https://li01.tci-thaijo.org/index.php/tjf/article/download/255439/174407/932503
- A web cellular-automaton app that drives each cell with the Wiriya (2009) ROS model, a slope layer and a monthly fuel layer from Landsat-5. It uses a Moore neighbourhood with √2·a for diagonal steps.
- The authors say the fuel layer was weak (few data) and the app has no weather input.
- **For us:** a working precedent for "empirical ROS equation inside a CA on a fuel raster", which is what our spread thread does. It has no validation numbers.

### A4. Ramos Rodríguez, Pico Coronel, Jiménez González et al. 2019. *Comportamiento del fuego a escala experimental en una plantación de Tectona grandis en Jipijapa, Manabí, Ecuador.* Rev. Bras. Ciênc. Agrár. 14(1):e5607. **FULL** (Tables 3–5 read from the page images)
Link: http://www.agraria.pro.br/ojs32/index.php/RBCA/article/download/v14i1a5607/244 (doi 10.5039/agraria.v14i1a5607)
- **Site:** 16-yr-old teak plantation, dry tropical coast of Ecuador. Ten plots of 2 × 5 m burned as head fires (wind-driven).
- **Weather (Table 3):** 27–31.8 °C (mean 29.9), RH 56–77% (mean 65.7), wind at 0.5 m 0.3–1.4 m/s (mean 0.72).
- **Fuel (Table 4):**
  - Dry load before burning 0.50–0.72 kg/m² (mean **0.58**); after burning 0.12.
  - Consumed **0.46 kg/m², 80%** (61–87%).
  - Bed depth 12–16.7 cm (mean **14.2**), 5.65 cm after the burn. Burn depth 8.6 cm.
  - Fuel moisture 10.1–12.0% (mean **11.2%**).
  - **Bulk density 3.4–5.1 kg/m³, mean 4.1** [calc, `teak_beds.py`].
- **Fire (Table 5):**
  - Flame height 0.36–0.86 m (mean **0.57**).
  - ROS 0.0076–0.0167 m/s (mean 0.0101), i.e. **27–60 m/h, mean 36 m/h**.
  - Intensity 41–105 kW/m (mean **69**).
  - Lethal scorch height 1.21–3.18 m.
  - Heat per unit area 1,158–2,117 kcal/m².
  - Plot burn times were 5–11 min (10 m² plots).
- **Constants and correlations:**
  - Heat of combustion used: 16,720 kJ/kg dry, giving 13,214–15,322 kJ/kg wet.
  - ROS vs intensity r = 0.85; flame height vs intensity r = 0.84. Weather variables were not significant.
- **Companion paper:** Ramos Rodríguez et al. 2018, *Rev. Cubana Cienc. For.* 6(2):184–194 (**ABSTRACT ONLY**; host down). Total plantation fuel was 11.17 t/ha. The prescription window was flame 0.54–0.76 m, ROS **0.016–0.033 m/s (58–119 m/h)**, intensity 16.4–33.9 kcal/m/s (69–142 kW/m) and scorch height 1.38–4.20 m.

### A5. Johnson, L. A. 2006. *Fire, seasonally dry evergreen forest and conservation, Huai Kha Khaeng WS, Thailand.* PhD thesis, University of Victoria. **PARTIAL** (chapter 4 on test fires and the literature review of moisture thresholds read)
Link: https://dspace.library.uvic.ca/bitstreams/3e65ad95-4e19-485f-8707-c7f702b886ff/download
- **Design:** 77 point-ignition test fires in seasonal evergreen forest litter, end of February to late April 2001. Litter moisture ranged from 7.4% to over 50% (mean 23.2 ± 1.2%).
- **Results:**
  - Only 5 fires spread 40 cm or more, all at ≤19.7% moisture.
  - **ROS of these fires was 0.15 ± 0.03 m/min.**
  - Moisture threshold ranges for spread: seasonal evergreen litter 9.0–19.7%, bamboo 7.7–13.6%, banana leaves 9.2–12.1%, grass 9.6–20.1%.
  - Fires spread at higher moisture late in the season (April) than early (February). Litter at 12% failed in February, while litter at 20% burned in April.
  - Loads of 5.3 and 7.1 t/ha did not carry fire in some subplots.
- **Earlier studies quoted:**
  - **Kanjanavanit (1992), closed deciduous forest at HKK, January:** sustained spread of 15 cm or more needed **leaf litter moisture below 8.4% and a litter depth of at least 5 leaves**.
  - Carvalho et al. (2003), Brazil: spread sustained at ≤13.5% moisture, ROS 0.16–0.26 m/min, flames 15–30 cm.
  - Uhl & Kauffman (1990) and Holdsworth & Uhl (1997), Amazon, early dry season: threshold 12%.
  - Ray et al. (2005), Paragominas, late dry season: **threshold 23%**, load 4.2 ± 0.2 t/ha, ROS 0.076 ± 0.019 m/min.
  - Negreiros (2004), Alta Floresta: maximum ROS 0.12–0.29 m/min at 10.5–26.5% moisture, with no clean moisture relationship.
- **For us:** the moisture of extinction for broadleaf litter is not one number. It rises through the season, and closed, shaded litter needs to be drier than open litter. Our Mx and our dryness index should be allowed to vary by month.

### A6. Wanthongchai, Goldammer & Bauhus 2011. *Effects of fire frequency on prescribed fire behaviour and soil temperatures in dry dipterocarp forests.* IJWF 20:35–45. **ABSTRACT ONLY** (paywalled)
Link: https://connectsci.au/wf/article/20/1/35/129036
- Plots with 0, 1, 2 and 7 fires in the past 10 years. Fine fuel rose with time since fire and levelled off by about 7 years.
- ROS, flame height and intensity did not differ between fire histories.
- **Ground-level temperature stayed above 60 °C for about 14, 12 and 8 min** in rarely, infrequently and frequently burned plots. At 2 and 5 cm soil depth it was below 1 min.
- **For us:** this is a residence-time proxy. A litter fire keeps a given spot hot for about 10 min.

### A7. Cruz, Hoffman & Fernandes 2025. *Global synthesis of quantification of fire behaviour characteristics in forests and shrublands.* Curr. For. Rep. 11:8. **PARTIAL** (tropical, deciduous and litter sections and tables read)
Link: https://link.springer.com/content/pdf/10.1007/s40725-024-00241-5.pdf
- In tropical evergreen broadleaf litter, "rates of spread and flame heights **never exceed 1.0 m/min and 1.0 m**, even … when low (<10%) litter moisture content combines with significant wind".
- Deciduous tropical forests carry more fuel, often with grass, and are less sheltered, so they reach **up to 4 m/min and 1.5 m flames** (Thai dry dipterocarp; Wiriya's range was 0.6–3.9 m/min).
- No Indian field fire-behaviour study is listed.

## Part B. India (theses and short papers)

### B1. Sahoo, A. 2020. *Forest fire crisis in different forest types and some approaches towards its management.* MSc thesis, College of Forestry, OUAT, Bhubaneswar. **PARTIAL** (methods, Tables 5A, 5B and 7 read)
Links: record https://krishikosh.egranth.ac.in/items/c1fdb74e-9a63-499c-a032-7f1ed6f2ec98 · PDF https://krishikosh.egranth.ac.in/server/api/core/bitstreams/cfc2b64f-b2ee-4d85-9466-1d1ef076cf00/content
- **Sites:** 8 forest divisions of Odisha (Athamalik, Khandapada, Kamakhyanagar, Keonjhar, Kaniha, Narasingpur, Begunia, Dhuannali), 2019–20. Four forest types, including **dry mixed deciduous forest (D3)** with sal, piasal, mahua, char, jamun and teak at Dhuannali.
- **Design:** small fuel beds of separate fuels (sal leaves, jamun leaves, mixed with wild date, understorey) laid in the forest. Ignition at 12 noon and 3 pm with jute sticks. Spread was timed from a centre point to a pole 1–3 ft away.
- **Results for D3 at 12 noon:**
  - Temperature 41–42 °C. Wind 3–5 m/s, read from a phone weather app.
  - **Fuel moisture 4–6% for leaves and 8–10% for mixed fuel.**
  - Flame height **0.73–0.94 m (leaves)** and 0.98–1.55 m (mixed or understorey).
  - At 3 pm, D3 flames were 0.69–1.03 m for leaves.
- **Caveats:**
  - "Rate of spread" is reported as an area rate (18–35 m²/min) over a 1–3 ft radius, so it cannot be compared with linear ROS.
  - The "fire intensity" column (750–3,358 kW/m) is back-calculated from flame height and wind with a constant of 0.003. It is not a measurement, so ignore it.
- **Fuel loads (Table 7), D3:**
  - Current-year fuel load **1.30–6.53 t/ha** across 7 sites (about 3.8 mean [calc]).
  - Previous years' cumulative load 2.95–7.59 t/ha.
  - Fuel moisture in December–January 9–26%.
  - Dry peninsular sal (D1) current-year load was 1.86–5.07 t/ha.
- **For us:** the only Indian measurement I found of **dead leaf moisture at 4–6% at noon in the peak season**, which supports the spread thread's 4–6%. Flames under about 1 m in leaf beds. Fuel loads of about 1.3–6.5 t/ha in dry mixed deciduous forest of eastern India.

### B2. Kittur, B. 2010. *Analysis of vegetational structure, diversity and fuel load in fire affected areas of tropical moist deciduous forests in Chhattisgarh.* MSc thesis, IGKV Raipur. **PARTIAL** (fuel chapter and Table 4.9). This is the full text behind the Kittur et al. 2014 abstract.
Link: https://krishikosh.egranth.ac.in/server/api/core/bitstreams/4b475a80-7de9-4e03-970d-43016c79dc00/content (text) · record https://krishikosh.egranth.ac.in/items/5eec3044-3e4d-453a-81b7-643c3f7f3580
- **Site:** Achanakmar-Amarkantak Biosphere Reserve, 2009–10. Pre-fire season sampled January–February, post-fire season May–June, with 1 × 1 m quadrats in 20 × 20 m plots.
- **Table 4.9 (Mg/ha):**

| Zone | Pre-fire duff | Pre-fire wood | Pre-fire total | Post-fire duff | Post-fire wood | Post-fire total |
|---|---|---|---|---|---|---|
| High fire | 1.82 | 0.46 | 2.28 | **0.218** | 1.67 | 1.89 |
| Medium | 1.77 | 0.74 | 2.51 | **0.26** | 1.88 | 2.14 |
| Low | 1.77 | 0.43 | 2.20 | 0.76 | 1.55 | 2.31 |
| None | 2.62 | 0.76 | 3.38 | 3.25 | 0.96 | 4.21 |

- **Consumption [inference]:** "duff" here is the leaf, grass, flower and twig litter layer. In the burned zones it fell by **about 86–88%** between seasons, while it rose 24% in the unburned zone. Wood litter increased after the fires, from post-fire twig fall.

### B3. Jhariya, M. K. 2010. *Analysis of vegetational structure, diversity and fuel load in fire affected areas of tropical dry deciduous forests in Chhattisgarh.* MSc thesis, IGKV Raipur. **PARTIAL** (fuel section)
Link: https://krishikosh.egranth.ac.in/server/api/core/bitstreams/aaf990ab-955f-4f00-9620-618f5a9f1faa/content · record https://krishikosh.egranth.ac.in/items/f51b4390-c9b9-4741-90fa-01dcc56098c4
- **Site:** Bhoramdeo WLS (dry deciduous, with teak).
- **Table 4.10:**
  - Pre-fire total fuel load **11.95–12.75 t/ha** (duff 8.2–10.4, wood 1.55–3.85).
  - Post-fire **4.85–5.77 t/ha**.
  - Net drop 6.3–7.1 t/ha in **all** zones, including the unburned zone (6.28).
- **Caution [inference]:** these totals are about 4× the 2.0–3.65 t/ha "seasonal mean" in the published Jhariya 2017 paper (`fuel_load_values_fullread.md` §1). The equal drop in the unburned zone means the pre- to post-season change is mostly decay, trampling or collection, not fire. The duff class probably includes partly decomposed organic matter that does not carry a flaming front. Do not use 12 t/ha as available fuel.

### B4. Mondal & Sukumar, Current Science (controlled burns, Mudumalai and BRT, February–March 2010). **ABSTRACT ONLY** (i-scholar host unreachable)
Link: https://i-scholar.in/index.php/CURS/article/view/88106
- Forest Department controlled burns measured with temperature-indicating lacquers.
- Ground-level temperatures were <79 to 760 °C, higher with heavier fuel load and higher air temperature and lower at high RH. Fuel moisture and wind had no detectable effect.
- Soil at 1 cm reached up to 302 °C.

### B5. Other Indian items checked (no usable fire-behaviour numbers)
- **Patela 2021**, IGKV MSc thesis "Effect of fire on biomass, carbon accumulation and regeneration in tropical dry deciduous forest": it has a litter mass table (4.8), but Krishikosh truncates the text file at 100 KB. The 4.6 MB original is at https://krishikosh.egranth.ac.in/server/api/core/bitstreams/030145be-8769-4018-9599-0687c6e8f220/content (not read).
- **Jhariya 2014**, IGKV PhD thesis (T-3065): 77 MB scanned PDF, not read. https://krishikosh.egranth.ac.in/server/api/core/bitstreams/a73fac5f-40eb-4d1c-8e0c-70605106ff0d/content
- **Singh 2020** (OUAT, Eastern Ghats) and **Maravi 2022** (BHU, "Effect of forest fire on soil chemical characteristics in Madhya Pradesh") hold no fire-behaviour numbers in the text that is available.
- **KAU 2023** (Wadakkancherry) is about soils only.
- **KFRI Research Report 223** (Menon et al. 2001, "Fire related ecosystem dynamics of the moist-deciduous forest of the Western Ghats", 69 pp): title only; the KFRI site is dynamic and I found no PDF.
- **IISc thesis 2005/2732** (Mudumalai fire ecology): returned 403.
- **Behera et al. 2023** (Trop. Ecol., lab flammability, eastern India) and **Gaikwad & Kumar 2024** (Fire Safety J. 144:104106, cone calorimeter on Indian broadleaf litter at 25–75 kg/m³): paywalled. Gaikwad's abstract says broadleaf litter ignites earlier and burns longer than pine litter, with lower heat release rate, and heat release rate falls as bed density rises.

## Part C. Lab litter beds

### C1. Kreye, Kane & Varner 2023. *Multivariate roles of litter traits on moisture and flammability of temperate northeastern North American tree species.* Fire Ecology 19:21. **FULL**
Link: https://fireecology.springeropen.com/counter/pdf/10.1186/s42408-023-00176-5.pdf
- **Design:** 17 species. Beds of 15 g oven-dry litter over 20 × 20 cm, burned in still air at RH 51–70%.
- **Broadleaf beds:**
  - **Bulk density 6–12 kg/m³**, packing ratio 0.020–0.088.
  - Leaf SA:V 25–68 cm⁻¹. Teak leaves are bigger and flatter than any species tested [inference].
  - **Drying time-lag 7–22 h**: oaks 7–14 h, maples and hickories 9–22 h. Pines were 7–10 h.
  - Saturation moisture 258–461%.
  - Flame height 51–76 cm.
  - Flaming time 32–61 s; smouldering 114–302 s.
  - **Consumption 81–92%.**
- **For us:** a broadleaf litter bed is a 10-h fuel by response time, not a 1-h fuel. Overnight RH recovery wets the top leaves, but the bed lags by hours [inference].

### C2. Ortiz-Mendoza, González-Tagle, Pérez-Salicrup et al. 2024. *Fire behavior and litter layer consumption in pine-fir and pine-oak forests.* Rev. Mex. Cienc. For. 15(86). **FULL** (HTML)
Link: https://cienciasforestales.inifap.gob.mx/index.php/forestales/article/download/1485/3716?inline=1 (doi 10.29298/rmcf.v15i86.1485)
- **Design:** field-collected litter re-laid on a 225 × 50 cm tilting table at field thickness. Burned outdoors in January–February at 29 °C, RH 35% and wind 2.24 km/h. Six replicates per slope.
- **Beds:** 0.3–0.7 kg/m², thickness 10.8–15.0 mm, **bulk density 2.2–5.3 kg/m³**.
- **ROS by slope:**

| Slope | ROS (m/min) | Flame length (m) | Intensity (kW/m) |
|---|---|---|---|
| 0° | 0.30 | 0.11 | 28.5 |
| 10° | 0.43 | 0.16 | 31.7 |
| 20° | 0.91 | 0.18 | 94.4 |

  - **Slope multipliers: ×1.43 at 10° and ×3.0 at 20°.**
  - Pine-oak beds ran 0.65 m/min against 0.41 for pine-fir. The oak beds burned intermittently, leaving unburned islands.
- **Consumption:** burn efficiency 0.45–0.60. Charred residue 0.016–0.017 kg/m².

### C3. Krieger Filho, Bufacchi, Santos et al. 2017. *Probability of surface fire spread in Brazilian rainforest fuels from outdoor experimental measurements.* Eur. J. For. Res. 136:217–232. **FULL**
Link: https://repositorio.unesp.br/bitstream/11449/170058/1/2-s2.0-85028247135.pdf
- **Design:** 72 point-ignited no-wind fires at 18 sites in Rondônia. 49% propagated.
- **Propagated vs self-extinguished fires:**

| | Propagated | Self-extinguished |
|---|---|---|
| Litter height (cm) | **3.6** | **1.6** |
| Bulk density (kg/m³) | **31.6** | **48.4** |
| Load (kg/m²) | 0.89 | 0.75 |
| Litter moisture (dry basis) | 0.26 | 0.28 |

  - ROS of the propagated fires was **0.151 ± 0.012 m/min (9 m/h)**.
  - Residue fraction 0.44 (about 56% consumed).
  - Logistic model: βH = 0.16·LMC + 0.19·LH (as printed), sensitivity 71%, specificity 84%.
- **For us:** a dense, thin bed (≥30 kg/m³) spreads only about 9 m/h in still air, or self-extinguishes. This is what "compact" means in the field, and it is far from teak.

### C4. Burton, Filkov, Pickering, Penman & Cawson 2023. *Quantifying litter bed ignitability: comparison of a laboratory and field method.* Fire 6:24. **PARTIAL**
Link: https://mdpi-res.com/d_attachment/fire/fire-06-00024/article_deploy/fire-06-00024.pdf
- Eucalypt litter, firebrand ignition.
- **Sustained ignition was highest when near-surface fuel moisture was below 15%** and litter cover was below 87%.
- Lab and field results agreed within ±25% for 62% of successful ignitions.
- Ignition tests here ran at 14–38 °C, RH 20–100%, litter moisture 12–257%. Marginal relevance (spotting, not spread).

## Part D. Savannas and other dry tropical systems (contrast cases)

### D1. Russell-Smith, Yates, Vernooij et al. 2024. *Framework for a savanna burning emissions abatement methodology applicable to fire-prone miombo woodlands in southern Africa.* IJWF 33, WF23193. **PARTIAL** (methods and results, first half of the HTML)
Link: https://connectsci.au/wf/article/doi/10.1071/WF23193
- **Sites:** Botswana and Zambia, 2019–2023. Woodland (WDL) below and above 1,000 mm rain, and open woodland (OWDL).
- **Fine fuel (grass + litter) by years since fire, early dry season, WDL <1000 mm:** 2.16, 2.50, 2.72, 2.88, 3.02, 3.14 t/ha for 1–6+ yr. Late season is about 10% higher.
- Litter is 55–66% of fine fuel early in the season and **76–85% late**.
- **Fine-fuel consumption:**

| | Early dry season | Late dry season |
|---|---|---|
| OWDL | 65.9 ± 2.5% | 76.4 ± 4.0% |
| WDL <1000 mm | 63.8 ± 2.8% | 70.0 ± 2.6% |
| WDL >1000 mm | 33.6 ± 10.4% | 73.0 ± 1.3% |
| CWD 6–50 mm, all types | 3.5–10.2% | 8.7–21.2% |

- **Burnt patchiness, i.e. share of the area inside the perimeter that burned:**

| | Early dry season | Late dry season |
|---|---|---|
| OWDL | 67.5% | 81.9% |
| WDL <1000 mm | 68.1% | 94.3% |
| WDL >1000 mm | 39.9% | 96.3% |

- **For us:** early-season (cooler, moister) fires leave about a third of the area inside a scar unburned. A scar label is not 100% burned area, especially in January–February [inference].

### D2. Ryan, C. M. 2009. *Carbon cycling, fire and phenology in a tropical savanna woodland in Nhambita, Mozambique.* PhD thesis, Edinburgh (chapter "How does fire intensity and frequency affect miombo woodland tree populations and biomass?", published as Ryan & Williams 2011, Ecol. Appl. 21:48). **PARTIAL**
Link: https://biblioteca.biofund.org.mz/wp-content/uploads/2019/01/1548837589-F1000.Carbon%20Cycling,%20Fire%20and%20Phenology%20in%20a%20Tropical%20Savanna%20Woodland%20in%20Nhambita.pdf
- **Design:** seven experimental burns, 6–19 September 2007, lit at 08:09–15:34 to span RH 14–65%, wind 0.5–2 m/s and air temperature 21–34 °C.
- **Result:** plot-mean Byram intensity **360–3,800 kW/m**. Hoffa et al. (1999) found 25–5,300 kW/m across the Zambian dry season.
- Dry closed-canopy sand forest has no grass, and "any fires that do occur are very low intensity litter fires".
- Thermocouples at 0.15 m gave a temperature–time integral as the intensity metric.
- **For us:** grass is what makes miombo fires 10–50× more intense than our litter fires. Time of day alone moved intensity by an order of magnitude.

### D3. Hoffa et al. 1999 (JGR 104:13841, Zambia) and Gambiza et al. 2005 (Zimbabwe, *Baikiaea* woodland). **ABSTRACT ONLY**
- **Hoffa:** across June–August, miombo grass moisture fell from 119% to 33%, fuel consumed rose from 1% to 47%, and intensity rose from about 25 to 5,274 kW/m. The PDF is behind a Cloudflare check.
- **Gambiza:** 15 early-season fires, intensity 25–1,341 kW/m, **ROS 0.01–0.35 m/s (0.6–21 m/min)**. Grass load and wind raised ROS; RH and fuel moisture lowered it; **litter load had no effect**. Scorch height can be used to reconstruct intensity.

### D4. Miranda, Bustamante & Miranda 2002. *The fire factor.* Chapter 4 in *The Cerrados of Brazil*. **FULL** (chapter)
Link: https://ava.icmbio.gov.br/pluginfile.php/4592/mod_data/content/19765/2002-The_Fire_Factor.pdf
- **Fine fuel before fire:**
  - Campo sujo 0.67–0.99 kg/m², cerrado s.s. 0.65–1.25, **cerradão (closed woodland) 0.58–0.89**.
  - Cerradão is 50–69% dead fuel; its herbaceous layer is 85% of fuel.
- **Consumption:** campo sujo 91–93%, cerrado 77–97%, **cerradão 75–76%**.
- **Fire temperatures:** 85–840 °C. Time above 60 °C was 90–270 s at 1 cm, 90–200 s at 60 cm and 20–70 s at 160 cm.
- Soil heating is negligible below 5 cm (≤3 °C).

### D5. Gomes, Miranda, Silvério & Bustamante 2020. *Effects and behaviour of experimental fires in grasslands, savannas, and forests of the Brazilian Cerrado.* For. Ecol. Manage. 458:117804. **ABSTRACT ONLY**
- 65 experimental plots. Forests had lower ROS, intensity, fine-fuel consumption and combustion factor than savannas.
- **VPD was the main driver of ROS and intensity in every vegetation type**; fine-fuel load drove heat release and consumption.
- The full numbers are probably in Gomes' 2018 UnB thesis (https://repositorioantigo.bce.unb.br/bitstream/10482/32603/1/2018_Let%c3%adciaGomesdaSilva.pdf). The server returned 503 and has an incomplete TLS chain (I fixed the chain; the server was still down).

### D6. Rodríguez-Trejo, Pulido-Luna, Martínez-Muñoz et al. 2018. *Análisis comparativo de quemas prescritas aplicadas a encinares tropicales.* Agrociencia 52:783–801. **PARTIAL** (abstract, weather, Table 1)
Link: https://www.scielo.org.mx/pdf/agro/v52n6/2521-9766-agro-52-06-783.pdf
- **Site:** tropical oak woodland, Chiapas (Aw2 climate, 1,200–1,500 mm). Six plots: three heading fires (with wind and slope) and three backing fires.
- **Weather:** heading 27.4 °C, RH 60.2%, wind 4.77 km/h; backing 31.2 °C, RH 52%, 3.97 km/h.
- **Fire:**
  - **Heading ROS 3.63 m/min, backing 0.59 m/min (ratio 6.2).**
  - Flame length 0.91 and 0.72 m; a nearby wildfire reached 1.94 m.
- **Fuel:**
  - **Leaf litter 2.67 (backing) and 4.88 (heading) t/ha, consumed 99.3% and 95.2%.**
  - Fermentation layer 10.7–14.0 t/ha, consumed 92%.
  - Total fuel 28–36 t/ha, consumed 87.5–92.7%; the wildfire consumed 97.2%.

## Part E. Night, heat content, and other single numbers

- **Night burning. Balch et al. 2022, Nature 602:442 (ABSTRACT plus the Earth Lab summary).** Each land-cover type has a VPD threshold below which night fire detections become rare. Night burning is common: 16.3% of burnable land had ≥25% of detections at night, and up to 38% in temperate conifer forest. Flammable night hours rose 36% from 1979 to 2020. The threshold values are only in figures I could not read. **No field measurement of night ROS in deciduous litter was found.** The closest are Wanthongchai's 8–14 min hot residence and Ryan's tenfold change in intensity between morning and afternoon burns.
- **Heat content of teak and Thai deciduous fuels:**
  - teak leaf briquettes 17.5 MJ/kg (search snippet, UGM study)
  - Thai dry dipterocarp fuel 18.65 MJ/kg by bomb calorimeter (Sompoh 1998, quoted in A1)
  - Junpen 2013 used 18.33 MJ/kg
  - Ecuador teak papers used 16.72 MJ/kg dry
  - teak wood 17.5–19.1 MJ/kg
- **Gadchiroli (Saha 2002, see note):** plot burn times 10–12.8 min per 9 m², flames 0.55–0.60 m, juvenile exposure median 12 s.

---

## Summary table of measured values

ROS is head fire unless marked. "m/h" = m/min × 60. BD = bulk density.

| Source | Site / forest | Fuel load (t/ha) | Depth, BD | Dead MC (%) | Wind | ROS (m/min) | ROS (m/h) | Flame (m) | Intensity (kW/m) | Consumption | Mark |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Himmapan 2006 | HKK Thailand, dry dipterocarp | 3.9–8.1 | fuel height 20–43 cm | 27–59 (mixed live) | 0–3.3 mph | 0.44–0.47 (0.18–0.92), all directions | 26–28 | 0.37–0.54 (max 1.8) | 44–66 (17–152) | – | FULL |
| Wiriya 2009 | HKK, dry dipterocarp | 4.64 dead + 0.73 live | 12.6 cm, ~3.7 kg/m³ | 12.4 (7–25) | 3.55 km/h | **1.89 (0.57–3.94)** | 113 (34–236) | 0.86 (0.41–1.22) | 190 (36–372) | – | FULL |
| Junpen 2013 (see note) | N Thailand mixed deciduous + dry dipterocarp | 2.36 leaf+grass, 3.88 total | – | 6.0–6.7 (Feb–May) | – | **1.37 (0.51–2.55)**; back 0.30 | 82 | 1.10 | 166 (39–380) | leaves 0.98, twigs 0.54, overall 0.80 | FULL |
| Akaakara (quoted) | Thai dry dipterocarp | 2.5–4.0 | – | – | – | 1.72 (0.28–6.41); 2.81 Kanchanaburi; 6.96 on 45% slope | 103 | 0.3–1.0 | 109–298 | 60–70% | ABSTRACT |
| Ramos-Rodríguez 2019 | Ecuador teak plantation | 5.8 | 14.2 cm, **4.1 kg/m³** | 11.2 | 0.72 m/s at 0.5 m | 0.61 (0.46–1.0) | 36 (27–60) | 0.57 | 69 (41–105) | 80% | FULL |
| Ramos-Rodríguez 2026 (see note) | Ecuador teak | 11.0 | 13.6 cm, ~8 kg/m³ | 12.4 | 0.06 m/s | 0.48 (0.27–0.71) | 29 | 0.46 | 130 (51–421) | – | FULL |
| Saha 2002 (see note) | Gadchiroli, dry deciduous (not teak) | 2.9–4.5 fresh weight | – | – | calm | ~0.2–0.4 [inferred in earlier note] | 12–24 | 0.55–0.60 | – | – | FULL |
| Sahoo 2020 | Odisha dry mixed deciduous | 1.3–6.5 current year | – | **4–6 leaves at noon** | 3–5 m/s (app) | area rate only | – | 0.69–1.03 (leaf beds) | (not measured) | – | PARTIAL |
| Kittur 2010 | Achanakmar, Chhattisgarh | 2.2–3.4 pre-fire | – | – | – | – | – | – | – | litter layer ~86–88% | PARTIAL |
| Jhariya 2010 | Bhoramdeo, Chhattisgarh | 12–12.8 pre, 4.9–5.8 post (includes humus?) | – | – | – | – | – | – | – | drop also in unburned zone | PARTIAL |
| Johnson 2006 | HKK seasonal evergreen litter | 5.3–7.1 (no spread) | – | spread ≤19.7 | calm | 0.15 | 9 | – | – | – | PARTIAL |
| Krieger Filho 2017 | Amazon litter | 8.9 | 3.6 cm, **32 kg/m³** (extinguished at 48) | 26 (dry basis) | none | 0.15 | 9 | – | – | 56% | FULL |
| Ortiz-Mendoza 2024 | Mexico pine-oak and pine-fir litter, table burns | 3–7 | 11–15 mm, **2.2–5.3 kg/m³** | – | 2.2 km/h | 0.30 (0°), 0.43 (10°), 0.91 (20°) | 18–55 | 0.11–0.18 | 28–94 | 45–60% | FULL |
| Kreye 2023 | Lab broadleaf beds | 3.75 | **6–12 kg/m³** | oven-dry | none | – | – | 0.51–0.76 (height) | – | 81–92% | FULL |
| Rodríguez-Trejo 2018 | Chiapas tropical oak | litter 2.7–4.9 (total 28–36) | – | – | 4–5 km/h | head 3.63, back 0.59 | 218 / 35 | 0.91 / 0.72 | – | litter 95–99% | PARTIAL |
| Russell-Smith 2024 | Miombo, Zambia/Botswana | fine 2.2–3.9 | – | – | – | – | – | – | – | fine 34–76%; patchiness 40–96% | PARTIAL |
| Ryan 2009 / Hoffa 1999 / Gambiza 2005 | Miombo / *Baikiaea* (grass) | – | – | grass 33–119 | 0.5–2 m/s | 0.6–21 | 36–1260 | – | 25–5,300 | 1–47% (Hoffa) | PARTIAL / ABSTRACT |
| Miranda 2002 | Cerradão | 5.8–8.9 fine | – | – | – | – | – | – | – | 75–76% | FULL |

## How this compares with our numbers

| Our number | Literature | Verdict [inference] |
|---|---|---|
| Fuel thread floor fuel ~2–3 t/ha; v2 map mean 1.46 t/ha | Dry deciduous and teak-bearing forest: 2.2–3.4 (Chhattisgarh), 2.4–4.6 (Thailand, fine dead), 1.3–6.5 (Odisha D3), 2.9–4.5 (Gadchiroli, fresh weight) | 2–3 t/ha is central. 1.46 is at the low end; it is plausible only if much of the map was burned the year before (×0.25–0.75 per Saha and Himmapan) or has little leaf fall. Check the v2 mean in cells that did not burn the previous year: it should be about 2–3. |
| Loose bed 2.5 kg/m³ | Teak 3.4–5.1 (mean 4.1) and about 8; Thai dry dipterocarp about 3.7; table-burn litter 2.2–5.3; lab broadleaf 6–12; Amazon 32–48 | Supported as a lower bound. **Use 4 kg/m³ as the central teak value, with 2.5–8 as the range.** "Compact" (≥10) is not supported for teak. |
| VIIRS fronts 51–98 m/h (median 70); FSI large fires 79 m/h | Head fires 30–160 m/h (Thai means 82–113); teak 29–36 m/h in damp, calm conditions; Junpen at 4–6% moisture, flat: 62–72 m/h; at 10% slope: 74–86 m/h | Our fronts sit inside the measured head-fire range. They are in fact faster than a 12-h mean should be unless fires keep spreading at night or are relit. A day at 1.4 m/min for 8 h plus a night at 0.3 m/min for 4 h gives 62 m/h. VIIRS fronts may also include several fronts or relighting (human). |
| Fuel thread fronts ~24 m/h | Calm or backing fires 18–36 m/h (Himmapan all-direction mean 26–28; Ortiz flat 18; teak 29–36) | Looks like calm, flat, backing or flanking behaviour. A good no-wind baseline, but too slow for head-fire runs on peak-season days. |
| Rothermel needs ×3 on a compact bed | My Rothermel run (σ = 6,000 /m, Mx 0.30, 18.6 MJ/kg) against 5 field datasets: obs/pred 0.7, 1.1, 1.4, 1.4, 2.6 (median 1.4). At 2.5 t/ha, 4 kg/m³ and 5% moisture, calm: 15–18 m/h; with 0.5 m/s midflame wind: 37–44 m/h | ×3 is about what a compact bed needs. **On the measured loose bed, ×1.5–2 plus a little midflame wind reaches 70 m/h.** Wind under the canopy matters more than the multiplier. |
| Dead fuel moisture 4–6% | Odisha noon leaves 4–6%; Thailand February–May 6.0–6.7%; Thai dry dipterocarp burns 7–25% (mean 12); teak burns 10–12% | Supported for peak-season afternoons. Use 8–12% for mornings or January. |
| Implied intensity and flames | At 1.46–3 t/ha, 70 m/h, 80% consumed: 41–84 kW/m, Byram flames 0.43–0.59 m | Matches field flames of 0.45–0.9 m and intensities of 44–190 kW/m. |

Script output: `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9code_behaviour/rothermel_check.py`. This is my own single-class Rothermel. The spread thread's parameters may differ, so compare with its own runs before acting.

## Ranked action list

### Spread thread
1. **Add the Junpen (2013) empirical ROS as a zero-calibration baseline.** ROS = 1.657·e^(0.018·S%)·e^(−0.080·M%) m/min, run hourly from the moisture series. Score it against the 1,066 VIIRS pass pairs alongside calibrated Rothermel. It already gives 62–72 m/h at 4–6% moisture with no tuning. Gain: high; effort: low.
2. **Re-fit the Rothermel multiplier on a loose teak bed** (4 kg/m³, depth = load ÷ 4, σ about 6,000 /m, Mx 0.25–0.30). Expect ×1.5–2.5 rather than ×3. Also fit a small midflame wind (0.3–0.7 m/s) instead of zero, because the field ROS that matches 70 m/h had light wind. Gain: high; effort: low.
3. **Cap the slope factor at the measured values:** about ×1.4 at 10° and ×3 at 20° (Ortiz-Mendoza), or use Junpen's e^(0.018·S%). On a loose bed, Rothermel's φs gives ×4–4.5 at 20° and will over-steer fires uphill. Gain: medium; effort: low.
4. **Split each 12-h pass interval into day and night ROS** using a moisture model with a 10–14 h response time for litter (Kreye time-lags 7–22 h) and a moisture of extinction near 20–25% that rises through the season (Johnson: 8.4% in closed deciduous forest early in the season, about 20% in April). This tests whether fires that "continue at night" explain VIIRS fronts above 60 m/h. Gain: medium; effort: medium.
5. **Treat scars as partly burned:** about 65% of the area burns inside early-season perimeters and 85–95% late in the season (miombo). Use this when scoring burned area or when inverting fuel from scar size. Gain: medium; effort: low.
6. **Use the measured Thai models as a sanity range.** Head:back ratio 4.9 (Akaakara) or about 6 (Chiapas oak); head intensity 1.5–2× back. Wiriya's wind model is too steep beyond 5 km/h, so do not use it as a wind factor. Gain: low; effort: low.

### Fuel thread
1. **Check the v2 mean of 1.46 t/ha against literature loads of 2–3 t/ha**, split into cells burned last year and cells not burned. Apply a 0.25–0.75 carry-over factor for burned-last-year cells (Saha ¼; Himmapan year-2 loads −25 to −40%). Gain: high; effort: low.
2. **Set the bed prior to 4 kg/m³** (range 2.5–8) and depth to load ÷ ρb, giving 3.5–7 cm at 1.5–3 t/ha. This is measured for teak (Ecuador 2019 per-plot table) and consistent with Thai dry dipterocarp and the table burns. Gain: high; effort: low.
3. **Fix the constants:**
   - heat content 18.0–18.6 MJ/kg dry (16.7 as a lower bound)
   - consumption 0.8–0.95 for leaf litter, about 0.5 for twigs, about 0.88 for the litter layer (Kittur)
   - dead fuel moisture 4–6% at peak-season noon, 8–12% in January and mornings

   Gain: medium; effort: low.
4. **Read the Indian theses not yet opened on Krishikosh:** Patela 2021 (IGKV; litter mass table 4.8; 4.6 MB PDF), Jhariya 2014 PhD (77 MB scan), and the IGKV sister theses. They are the only central-Indian pre- and post-fire load data with consumption. Use `kk.py search` to find more; the API is open. Gain: medium; effort: medium.
5. **Do not use Jhariya 2010's 12 t/ha** as available fuel. Its pre- to post-season drop is the same in unburned zones, so it is mostly decay. Gain: avoids an error; effort: none.
6. **Leads I could not open:**
   - Gomes 2018 UnB thesis (Cerrado forest fire behaviour; server 503)
   - Wanthongchai 2011 tables (paywall)
   - KFRI RR 223 (Western Ghats moist deciduous fire dynamics)
   - Thai RFD "Effect of burning fire on fuel bed" (forest.go.th PDF behind Cloudflare)
   - Ramos-Rodríguez group's Sancán controlled-burn paper (cfores.upr.edu.cu/index.php/cfores/article/view/831; host down)
   - Mondal & Sukumar Current Science controlled burns (i-scholar unreachable)

## Reading status

| Source | Status |
|---|---|
| Himmapan 2006; Wiriya 2009; Ramos-Rodríguez 2019; Kreye 2023; Ortiz-Mendoza 2024; Krieger Filho 2017; Miranda 2002 | FULL |
| Sasirat 2014; Johnson 2006; Cruz 2025; Sahoo 2020; Kittur 2010; Jhariya 2010; Rodríguez-Trejo 2018; Russell-Smith 2024; Ryan 2009; Burton 2023 | PARTIAL |
| Wanthongchai 2011; Gomes 2020; Hoffa 1999; Gambiza 2005; Ramos-Rodríguez 2018; Mondal & Sukumar (Current Science); Balch 2022; Behera 2023; Gaikwad 2024; Guo 2026 (J. For. Res., lab slope and moisture) | ABSTRACT ONLY |
| KFRI RR 223; Gomes 2018 thesis; Patela 2021; Jhariya 2014; Thai RFD fuel-bed PDF; IISc 2005/2732; MSU theses | Not obtained |
