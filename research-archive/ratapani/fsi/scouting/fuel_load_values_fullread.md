# Fuel load values: full-read follow-up

Done 14 Oct 2026 as a follow-up to `fuel_load_values.md`. It serves the "High-resolution fuel load map" thread (`/mnt/project-files/fuel-map/`), which is rebuilding FSI's strata (forest type × canopy density × slope; classes <20, 20–40, 40–60, >60 g/ft²) for Ratapani without new field samples.

Units: 1 t/ha = 1 Mg/ha = 100 g/m² = 9.29 g/ft². FSI's class edges of 20, 40 and 60 g/ft² are **2.15, 4.31 and 6.46 t/ha**.

Lines marked **[inference]** are my reasoning, not something a paper states.

## Reading status

| # | Paper | What I read | Where |
|---|---|---|---|
| 1 | Jhariya 2017, Bhoramdeo WLS (J. For. Env. Sci. 33(4):330–341, doi 10.7747/JFES.2017.33.4.330) | **FULL TEXT** (PDF) | koreascience.or.kr/article/JAKO201706749669484.pdf |
| 2 | Saha 2002, Mendha, Gadchiroli (Curr. Sci. 82(9):1144–1147) | **FULL TEXT** (scanned PDF, read page by page) | currentscience.ac.in/Volumes/82/09/1144.pdf |
| 3 | Mondal & Sukumar 2016, Mudumalai (PLoS ONE, doi 10.1371/journal.pone.0159691) | **FULL TEXT + S2 fuel appendix** | Europe PMC XML; PLOS supplementary s002 |
| 4 | Thakur et al. 2022, Achanakmar-Amarkantak BR (Front. Env. Sci. 10:940614) | **FULL TEXT**, without supplementary tables S1–S3 | frontiersin.org |
| 5 | **Kodandapani, Cochrane & Sukumar 2008**, Forest Ecol. Manage. 256:607–617. *Not in the original note.* | **FULL TEXT** | wgbis.ces.iisc.ac.in mirror |
| 6 | Kodandapani 2013, Fire Ecology 9(2):102 | **PARTIAL**: table values from search snippets only. Springer blocks automated access | fireecology.springeropen.com |
| 7 | Labenski et al. 2023, RSE 295:113711 | **FULL TEXT** | fs.usda.gov/rm/pubs_journals/2023/rmrs_2023_labenski_p001.pdf |
| 8 | Singh, Jeganathan & Rathore 2020, Sci. Rep. 10:17638 (NDVI leaf-fall proxy, central India) | **FULL TEXT** | PMC7572383 |
| 9 | **Sharples et al. 2024**, Int. J. Wildland Fire 33:WF23120 (dead fuel moisture models). *Not in the original note.* | **PARTIAL** (HTML, without supplements) | connectsci.au |
| 10 | Li et al. 2025, RSE 318:114526 (litterfall minus decay) | **ABSTRACT ONLY**. The green OA copy at research.vu.nl sits behind Cloudflare, and Elsevier is paywalled | doi 10.1016/j.rse.2024.114526 |
| 11 | Kittur et al. 2014, J. For. Res. 25:857 (doi 10.1007/s11676-014-0471-0) | **ABSTRACT ONLY** (paywalled; the hep.com.cn PDF link is dead) | journal.hep.com.cn |
| 12 | Pande, Meshram & Banerjee 2002, Trop. Ecol. 43(2):337–344 | **ABSTRACT ONLY** (no full text online) | AGRIS |
| 13 | Tiwari et al. 2013, Raigarh teak | **ABSTRACT ONLY** | Consensus |
| 14 | Nolan et al. 2016 RSE; Resco de Dios et al. 2015 AFM | **ABSTRACT ONLY**. eScholarship and UdL return 403 | — |
| 15 | Das & Mondal 2016, J. For. Res. (teak/sal decay, West Bengal) | **SEARCH SNIPPET ONLY** | doi 10.1007/s11676-016-0208-3 |

**Seven papers were read in full** (1–5, 7, 8; for 3 that includes the fuel appendix). Two were partial (6, 9). The rest were abstract or snippet only.

---

## 1. Jhariya 2017: Bhoramdeo WLS, Chhattisgarh (FULL TEXT)

**Site and design.** The forest is tropical dry deciduous: Champion & Seth 5A/C1b dry teak, 5B/C1c and 5B/C2 sal, and E9 bamboo. The paper's ombrothermic diagram covers 2009–2013.

Four compartments were chosen by fire history from Forest Department and NRSA records:
- C126, **high fire**: burns every year, over more than 70% of its area.
- C127, **medium fire**: burns every second year, over 40–70%.
- C128, **low fire**: burns about once in 5 years, over less than 40%.
- C123, **no fire**.

Sampling covered one year with 960 samples in total: 10 quadrats of 50 × 50 cm, collected monthly for both floor and litterfall. Litter traps were stone-block-lined denuded quadrats. Samples were oven-dried at 60 °C. The south and west aspects burn more than the north and east.

**Table 1: standing forest floor by season (g/m², dry weight).**

| Component | High W | High S | High R | Med W | Med S | Med R | Low W | Low S | Low R | None W | None S | None R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Fresh leaf litter | 71.23 | 128.25 | 20.65 | 102.0 | 178.0 | 33.0 | 109.78 | 189.18 | 37.42 | 184.25 | 205.18 | 43.56 |
| Partly decayed litter | 44.45 | 26.38 | 79.04 | 66.19 | 49.40 | 101.0 | 72.68 | 64.0 | 117.0 | 86.68 | 77.0 | 129.0 |
| Wood litter | 54.24 | 75.76 | 100.0 | 76.14 | 99.25 | 119.18 | 84.36 | 106.0 | 135.11 | 103.62 | 112.64 | 152.0 |
| **Total** | 169.92 | 230.39 | 199.69 | 244.33 | 326.65 | 253.18 | 266.82 | 359.18 | 289.53 | 374.55 | 394.82 | 324.56 |

W = winter, S = summer, R = rainy.

**Table 2: annual litterfall (g/m²/yr).**

| Zone | Leaf | Wood | Total |
|---|---|---|---|
| High fire | 285.05 | 190.03 | 475.08 |
| Medium | 371.57 | 200.08 | 571.65 |
| Low | 454.99 | 214.11 | 669.10 |
| None | 529.26 | 226.83 | 756.09 |

**Table 3: seasonal litterfall (g/m²).**

| Zone | Winter leaf | Winter wood | Summer leaf | Summer wood | Rainy leaf | Rainy wood |
|---|---|---|---|---|---|---|
| High | 179.95 | 50.30 | 75.46 | 119.97 | 29.64 | 19.76 |
| Medium | 230.69 | 54.36 | 100.95 | 124.22 | 39.94 | 21.51 |
| Low | 276.56 | 57.86 | 122.94 | 130.14 | 55.49 | 26.11 |
| None | 326.61 | 60.60 | 141.40 | 139.98 | 61.25 | 26.25 |

**Table 4: turnover (Jenny 1949).** K = 0.74 (high), 0.70 (medium), 0.71 (low), 0.70 (none). Turnover time is 1.35–1.43 yr.

**Other findings.**
- Leaf fall peaks in **December** and is concentrated in **November–March**. It is negligible in June–July.
- Fresh leaf litter on the floor peaks in **April**.
- Wood litter on the floor peaks in July.
- Compared with the no-fire zone, fire cut total litterfall by 11.5% (low), 24.4% (medium) and 37.2% (high).
- Leaf is 60–70% of litterfall.

**Checks against the note.**
- "2.00–3.65 t/ha" is correct. It is the mean of the three seasonal totals: high-fire zone 2.00, no-fire zone 3.65.
- "4.75–7.56 t/ha/yr" is correct.
- The **summer (pre-monsoon) peak** is higher: **2.30–3.95 t/ha**. Of this, fresh leaf, the fine fuel that carries fire, is **1.28–2.05 t/ha**.

**Ratios derived from the tables [inference].**
- Summer total floor ÷ annual litterfall = 0.48 / 0.57 / 0.54 / 0.52, so the **peak floor is about 0.5 × annual litterfall**.
- Summer fresh leaf ÷ annual leaf fall = 0.45 / 0.48 / 0.42 / 0.39.
- Fire history sets the stratum: a site that burns every year carries about 40% less summer fresh leaf than an unburnt one (128 vs 205 g/m²).

**Concrete action for us** (fuel-map thread).
1. Add a **fire-frequency modifier** to the strata, using our 2017–2026 burn-scar count per 500 m cell. Multiply the litter load by **0.63 for cells that burn every year, 0.76 for alternate years, 0.88 for about one burn in 5 years, and 1.0 for unburnt cells**. These are the Table 2 litterfall ratios.
2. Set the **pre-fire-season (March–April) stratum value to 0.5 × the annual litterfall of the stratum**.
3. Expected effect: classes now follow the observed fire history instead of a single forest-type mean. Bhoramdeo puts the mean at about 2.3 t/ha in cells that burn every year and about 3.9 t/ha in unburnt ones. That lands on either side of FSI's 20 g/ft² (2.15 t/ha) and 40 g/ft² (4.31 t/ha) edges.

## 2. Saha 2002: Mendha, Gadchiroli, Maharashtra (FULL TEXT)

**Site.** Dry deciduous forest of *Terminalia alata*, *Pterocarpus marsupium* and *Anogeissus latifolia*. Canopy 18–20 m, rainfall 1600 mm, elevation 150–300 m, vertisols. The forest is Gond-managed and burns every year, in March. People light the fires for mahua flower collection and to flush tendu (*Diospyros melanoxylon*) leaves.

**Method.** Ten fuel plots of 0.25 m², sampled every two weeks from February to May in 1999 and 2000, and in February–March 2001. Values are **fresh weight**. Fire temperature was measured with Tempil tablets.

**Table 2: fuel load (g per 0.25 m², mean ± SE), converted to g/m² (×4).**

| Year | Feb | Mar | Apr | May |
|---|---|---|---|---|
| 1999 | 73.76 ± 4.07 (**295**) | 91.81 ± 4.93 (**367**) | 104.35 ± 3.35 (**417**) | 106 ± 2.9 (**424**) |
| 2000 | 72.67 ± 5.3 (**291**) | 95 ± 5.12 (**380**) | 100.37 ± 3.01 (**401**) | 107 ± 3.43 (**428**) |
| 2001 | 92.6 ± 19.91 (**370**) | 112.5 ± 6.21 (**450**) | NA | NA |

**Findings.**
- Fuel rises from February to April and levels off by mid-April. The month effect is F(3,72) = 13.98, p < 0.0001.
- More than 75% of leaf fall is complete by late March.
- In 2001 the monsoon withdrew early and 2000 rainfall was below average. Shedding was then complete by late March, and the February–March loads were 25% higher.
- **Plots protected from fire carried no litter over from the previous year: the old litter had decomposed.** This is the author's personal observation.
- Burnt sites accumulate about a quarter of the litter that unburnt sites do.
- Flame height was 55 ± 11.6 cm (1999) and 60 ± 6 cm (2001), never above 75 cm.
- Surface temperatures ranged from 45 to 510 °C, with a coefficient of variation of 19%, 13.4% and 20%.
- Plot burn time was 10–12.8 minutes. Juvenile exposure had a median of 12 s and ranged from 0 to 35 s.

**Checks against the note.** "Flames 55–60 cm" and "75% of leaf shed by late March" are correct. The g/m² values were missing from the note and are now in the table above.

**Concrete action for us** (fuel-map thread, and fire-spread work).
1. Use the Saha curve as the **in-season build-up shape for dry deciduous forest**: February = 0.70, March = 0.88, April = 0.97, May = 1.00 of the season peak (means of 1999 and 2000).
2. Treat these as fresh-weight values, roughly 3–4.5 t/ha. Dry weight in a dry season is about 10–15% lower **[inference]**.
3. **Reset carry-over to zero at each monsoon.** Saha's observation and the Egunjobi teak result in section 10 both support a single-season accumulation model.
4. Shift a "dry year" one month earlier: when the previous monsoon is weak or withdraws early, use the March value for February.

## 3. Mondal & Sukumar 2016: Mudumalai (FULL TEXT plus S2 appendix)

**Fuel method (S2 appendix).** Plots sit on a 1.5 km grid, **87 locations**. The first sampling ran from December 2003 to February 2004, then again in February 2005 and February 2006. Each plot is 20 × 20 m with four 1 × 1 m quadrats at the corners. Grass was air-dried. **Leaf litter was weighed fresh in the field**, and total fuel = grass dry weight + litter fresh weight.

**Table A: grass biomass in plots unburnt 2004–2006 (44 plots).**

| Moisture regime | MR1 ≥ 1400 mm | MR2 1200–1400 | MR3 1000–1200 | MR4 ≤ 1000 |
|---|---|---|---|---|
| Forest type | moist deciduous / semi-evergreen | degraded moist / dry deciduous | dry dipterocarp / dry deciduous | dry thorn |
| Grass 2004 (g/m²) | 47.5 | 45.4 | 74.3 | 45.1 |
| Grass 2006 (g/m²) | 58.8 | 120.8 | **251.8** | 65.9 |
| Gain over 2 yr (g/m²) | 11.4 | 75.4 | **177.5** | 20.8 |
| Gain per yr (g/m²/yr) | 5.7 | 37.7 | **88.8** | 10.2 |
| Plots | 9 | 15 | 14 | 6 |

**Fuel versus rainfall.** Total fuel correlates with the previous wet season's rainfall (May–October): r = 0.32 (p = 0.004) for 2003→2004 and r = 0.28 (p = 0.015) for 2004→2005, but r = −0.09 (not significant) for 2005→2006. Total fuel at a plot ranges up to about 1000 g/m², and up to 2000 g/m² in 2006 (read from Figure C).

**Fire models (main text).** These are quasi-binomial GLMs of the proportion burnt, fitted to 1990–2010 data. Rainfall is in mm. "earlydry" is November–December rain; "wet" is the previous May–October rain.
- **Landscape:** logit p = −4.121 − 20.73·prevBurn + 0.004·wet + 0.070·earlydry + 0.020·prevBurn·wet − 0.00008·wet·earlydry. Correlation with observed area: r = 0.55.
- **MR3 (1000–1200 mm, closest to Ratapani):** logit p = −7.412 + 0.008·wet + 0.073·earlydry − 0.00008·wet·earlydry. r = 0.47.
- **MR4:** −19.75 + 0.026·wet + 0.122·earlydry − 0.0002·wet·earlydry. r = 0.89.
- **MR2:** r = 0.83.
- **MR1:** only earlydry is retained, with coefficient −0.015.
- Mean area burnt was 20.1% per year, a mean fire interval of 4.9 yr. By regime the interval is 19.2 / 4.2 / 2.9 / 11.6 yr for MR1–MR4.

**Phenology.** Trees start shedding in December and are bare by February. Fires run from January to April, with the peak in February–March.

**Checks against the note.** The 75 g/m² (MR2) and 177.5 g/m² (MR3) two-year grass gains are correct. Note that these come from *unburnt* plots only. Standing grass after two unburnt years reached 2.5 t/ha in MR3.

**Concrete action for us** (fuel-map thread, and the short-horizon / season-severity thread).
1. Add a grass term for open and low-density strata (FSI open forest, scrub, blanks): **0.45–0.75 t/ha in a year after fire, plus 0.9 t/ha for each further unburnt year, capped at about 2.5 t/ha**. These are the MR3 values, applied using our time-since-burn layer.
2. Season severity: fit the MR3-form logistic to Ratapani's yearly burnt fraction for 2017–2026. Use CHIRPS or IMD gridded rain for May–October (previous year) and November–December. Ten years is too few to fit four terms freely, so fix the signs and use the Mudumalai MR3 coefficients as priors.
3. Expected effect: a pre-season (January) forecast of the year's burnt fraction, and a per-year scaling for the fuel map.

## 4. Thakur et al. 2022: Achanakmar-Amarkantak BR (FULL TEXT, no supplements)

**Design.** Four stand types, each in a 0.8 ha permanent plot, sampled monthly from **2015 to 2019 (5 years)**. Standing litter was collected in three 0.5 × 0.5 m sub-quadrats in 20 × 20 m plots, 15 plots per type (60 in total). Rainfall is 1050–1500 mm. Elevation 505–720 m.

**Table 1: stand structure (useful for canopy-density strata).**

| Type | Trees/ha | Basal area (m²/ha) | Canopy cover % | LAI | Height (m) |
|---|---|---|---|---|---|
| Teak plantation (TP) | 470 | 28.81 | 65 | 3.65 | 15 |
| Sal mixed (SMF) | 652.5 | 34.12 | 75 | 6.2 | 22 |
| Dense mixed (DMF) | 587.5 | 29.05 | 80 | 5.5 | 18 |
| Open mixed (OMF) | 467.5 | 9.26 | 35 | 2.85 | 12 |

**Results.**
- Mean annual litterfall is 4.19 ± 0.305 Mg/ha/yr.
- Mean monthly litterfall: DMF 0.52, OMF 0.59, SMF 0.59, TP 0.61 Mg/ha. Monthly values range from 0.12 to 0.83 Mg/ha.
- Litterfall peaks in **November** and is lowest in **June**. The secondary peak is in April–May.
- Seasons: winter (November–February) about 40%, summer (March–June) about 30%, rainy (July–October) about 30%.
- Leaves are about 64% of litterfall.
- **Turnover K (Table 4): TP 0.62, SMF 0.59, DMF 0.58, OMF 0.50.** Turnover time is 1.61–1.98 yr.
- Correlations with litterfall (Table 5): **NDVI r = 0.68**, SAVI 0.65, NDMI 0.43. The imagery is Landsat.
- Weather model: ln(LF) declines with rainfall and temperature, R² = 0.92 (rain), 0.89 (temperature), 0.93 (both). The fitted coefficients were lost in the HTML.

**Checks against the note.**
- **Correction:** the note says the paper "contradicts itself on whether it has 1 or 5 years". It does not. It has 5 years (2015–2019). The one-year study it mentions is an earlier paper, Thakur et al. 2014.
- The note's "turnover is 70–92%/yr" leaves out this site's **50–62%**.

**Concrete action for us** (fuel-map thread).
1. Use **NDVI (r = 0.68) rather than NDMI** as the canopy-strength scaler for annual litterfall in the M3 layer.
2. Use **K = 0.5 for open mixed and 0.6 for teak and closed mixed** when converting annual litterfall to a steady-state floor (see section 10).
3. Use the Table 1 LAI-to-cover pairs (cover 35% → LAI 2.85; 65–80% → 3.65–6.2) to map S2 canopy cover to peak LAI for the M3 leaf-loss term.

## 5. Kodandapani, Cochrane & Sukumar 2008: Nilgiri landscape (FULL TEXT; missed by the note)

**Method.** 29 belt transects of 500 × 10 m. Fuel was measured by **modified planar intercept** on 10.5 m lines every 25 m, in size classes 0–0.6 cm (1-hr), 0.6–2.5 cm (10-hr), 2.5–7.6 cm (100-hr) and over 7.6 cm (1000-hr). Grass and litter were sampled in 1 m² quadrats and oven-dried at 100 °C for 24 h. Leaf fall and curing run from January to early March. Fire-frequency classes cover 1989–2005: low = 1 fire, moderate = 2–5, high = more than 5.

**Table 1: tropical dry deciduous forest (mean (SD), Mg/ha).**

| Fire frequency | 1-hr | 10-hr | 100-hr | 1000-hr | Total | Canopy % | Basal area (m²/ha) |
|---|---|---|---|---|---|---|---|
| Low (n = 3) | 1.2 (0.15) | 0.8 (0.5) | 3.8 (2.2) | 17.5 (5.5) | 23.4 (6.3) | 56 | 17 |
| Moderate (n = 5) | 1.4 (0.8) | 1.2 (0.7) | 3.3 (5.5) | 16 (20.7) | 16 (21) | 67 | 27 |
| High (n = 9) | 1.5 (0.7) | 1.2 (0.5) | 3.2 (3.8) | 14.3 (16) | 20.2 (18.5) | 66 | 24 |

Grass is 14% of total fuel and litter 8% in dry deciduous forest, so roughly **2.8 t/ha grass and 1.6 t/ha litter [inference, from about 20 t/ha total]**.

The text and the table disagree on the total: the text says "16 t/ha for moderate to 23.4 for high", while the table puts 23.4 under *low*.

**Table 2: dry thorn forest.** Total 3.6–6.3 Mg/ha; 1-hr 0.5–0.9; canopy 33–40%; grass 7% and litter 4% of the total.

**Table 3: moist deciduous forest.** Unburnt: 54.3 Mg/ha total, 1-hr 2.9, 1000-hr 47. Burnt: 46.5 Mg/ha total, 100-hr 12.

**Fire regime.** Fire return interval is 6 yr in dry deciduous, 10 yr in thorn and 20 yr in moist deciduous forest. Return interval against distance from the park boundary follows a negative exponential, r² = 0.63.

**Concrete action for us** (fire-spread thread).
- The note's custom TL model sets 10-hr and 100-hr at about 0.5–1 t/ha. Mudumalai dry deciduous measures **10-hr 0.8–1.2 and 100-hr 3.2–3.8 t/ha** by planar intercept.
- For FlamMap or Rothermel runs, use 1-hr = litter + 1-hr wood (1.6 + 1.3 ≈ 3 t/ha), 10-hr = 1.0 and 100-hr = 3.5 t/ha. Run a sensitivity test with 100-hr at 1 t/ha. This should have little effect on spread rate, since 100-hr fuel barely drives Rothermel spread **[inference]**.

## 6. Kodandapani 2013, Fire Ecology 9(2):102 (PARTIAL)

These come from table snippets:
- Dry deciduous, Nilgiri (1996–2005): total **21.3 ± 17**, 1000-hr **15.3 ± 15** Mg/ha.
- Dry deciduous, Sathyamangalam (1997–2012): total **12.3 ± 8**, 1000-hr **2.0 ± 2.8** Mg/ha.
- The Nilgiri 1000-hr fuel is significantly higher at p < 0.01, and the total at p < 0.05.
- Mean fire rotation is **7.1 yr in the Nilgiri** landscape and **44.1 yr in Sathyamangalam**.

The note's 1-hr values (1.44 and 0.68) and its moist and thorn totals could not be checked; I could not open the full text. Nothing that was checked is wrong.

**Concrete action:** none beyond section 5. Use it only as a range check.

## 7. Labenski et al. 2023: south-west Germany, lidar + S2 (FULL TEXT)

**Design.** 119 circular plots (radius 7.5 m, 176.6 m²). Random forest models with VSURF feature selection and leave-one-out validation.

**Table 6 (best model, all predictors).**

| Component | R² | RMSE (t/ha) |
|---|---|---|
| Litter | **0.27** | 2.57 |
| Dead 1-hr | **0.41** | 0.42 |
| Herb | 0.55 | 0.30 |
| Fine shrub | 0.39 | 0.49 |
| Woody shrub | 0.64 | 2.08 |
| Fuelbed depth | 0.44 | 0.16 m |

With spectral predictors only, litter R² was 0.12–0.15.

**Table 7: RF against forest-type means (RMSE, t/ha).**

| Component | RF | Type mean | Gain |
|---|---|---|---|
| Litter | 2.57 | 2.83 | **9%** |
| Dead 1-hr | 0.42 | 0.45 | **7%** |
| Herb | 0.30 | 0.44 | 32% |
| Fine shrub | 0.49 | 0.65 | 25% |
| Woody shrub | 2.08 | 3.49 | 40% |

Mapped litter loads were 2.8–9.9 t/ha. Data are available only on request.

**Checks against the note.** "Litter R² 0.27–0.41" mixes two components: litter is 0.27 and dead 1-hr is 0.41. "No better than forest-type means" should read "only 7–9% better".

**Concrete action for us** (fuel-map thread).
1. This confirms that, **without plots, forest-type stratum means are within about 10% of the best remote-sensing litter model**. Our M1 strata are the right baseline.
2. Spend remote-sensing effort on the **understorey (grass and shrub, including Lantana), where RF beat the stratum means by 25–40%**. Use S2 dry-season greenness and a GEDI or S1 shrub signal.

## 8. Singh, Jeganathan & Rathore 2020: NDVI leaf-fall proxy, central India (FULL TEXT)

**Metric.** Annual deciduousness:

AD = [(NDVImax − NDVImin) / NDVImax] × (NDVImean / Sc), with **Sc = 0.005**.

Inputs are MOD13Q1 at 250 m and 16 days, 2001–2018, quality flags 0–1 only, with MOD44B VCF for tree cover.

**Table 1 (2011, a normal rainfall year).**
- Dry deciduous pixels: NDVI min 0.19–0.26, max 0.56–0.71, mean 0.36–0.43. **AD 43.6–55.1** (old metric 54–71).
- Moist deciduous pixels: AD 56–67.

**ANOVA, dry deciduous with VCF < 30%.** AD = 57.6 in the dry year (2002), 61.0 in the normal year (2011) and 64.5 in the wet year (2013). **Wet years shed more leaf.**

Across all forest: 36.85% of the area is in the "very high" deciduousness class (AD > 60) on the long-term mean.

**Concrete action for us** (fuel-map thread).
1. Compute AD per year from Sentinel-2 NDVI at 20 m (December–April minimum against the October maximum) using the same formula and Sc.
2. Use **AD / mean AD** as a per-pixel, per-year multiplier on the stratum's annual leaf fall.
3. Expected effect: a ±10% year-to-year signal plus within-stratum spatial texture. It costs little, since the S2 stack is already used for burn scars.

## 9. Sharples et al. 2024: simple dead fuel moisture models (PARTIAL; missed by the note)

**Data.** 10-hr fuel sticks (12–19 mm) at NSW and ACT eucalypt sites, 25–1230 m elevation, from 2013 and 2017–2020. VPD (kPa) = 0.6108·exp(17.27T/(T+237.3))·(1 − H/100).

**Fitted models (all data, D1).**
- FMIrel: FMC = 3.238 + 0.688·FMI, with FMI = 10 − 0.25·(T − H).
- FMIgen: FMC = 10.875 − 0.193·T + 0.165·H.
- m_gen: FMC = 7.803 + 19.110·exp(−0.887·VPD).
- For the dry subset (FMC < 20%, D2): m_gen = 6.808 + 12.245·exp(−0.540·VPD); FMIrel = 5.321 + 0.465·FMI.

**Results.** The authors' conclusion is that the "relaxed and generalised" models are best and that simple T − H models do as well as VPD models. The Resco de Dios original (m_D) had the largest errors on D1. No model was reliable below 10% FMC. The models do not apply to dew, rain or 1-hr fuels.

**Nolan 2016 (abstract only).** The VPD exponential model works with MODIS-LST-derived VPD, which beats a model that adds precipitable water. Resco de Dios 2015 (abstract) reports MAE 3.7% overall, 2.9% when FMC < 20% and 1.8% when FMC < 10%. I could not retrieve the original coefficients.

**Concrete action for us** (short-horizon / daily danger thread).
1. Compute a daily 13:00 local-time **FMIrel or m_gen dead fuel moisture** from ERA5-Land T and RH, using the D2 coefficients for the dry season.
2. Note that these models give 10-hr moisture, not litter moisture. Treat the output as a relative index, and add days-since-rain over 2 mm as a reset.
3. Expected effect: a daily dryness covariate for the VIIRS-dated burn model. Its gain over raw VPD is likely small, so test it as a feature ablation.

## 10. Decay constants and the steady-state link (several sources)

| Source | Site | Constant | Kind |
|---|---|---|---|
| Jhariya 2017 | Bhoramdeo, dry deciduous | K = 0.70–0.74 | Jenny K = annual litterfall ÷ (litterfall + minimum floor) |
| Thakur 2022 | AABR | K = 0.50 (open) to 0.62 (teak plantation) | Jenny K |
| Jha 2010 (abstract) | Tarai teak | 54% mass loss in 6 months from July, so **k ≈ 1.55/yr** within the monsoon half-year **[inference]** | litterbag |
| Das & Mondal 2016 (snippet, unverified) | West Bengal | teak **k = 2.70 ± 0.50/yr**; sal 2.41 ± 0.30/yr | litterbag, Olson |
| Rajagopal et al. 2005 (snippet) | 30-yr teak plantation | k = 0.697 (bag) vs 1.638 (no bag); 19.4% of mass left after 1 yr without a bag | Olson; units unconfirmed |
| Egunjobi 1974 (abstract) | Nigeria, dry-zone teak | annual litterfall fully mineralised in under 6 months; 63–75% falls in December–March | — |
| Tiwari 2013 (abstract) | Raigarh teak | reports "decomposition 11.08–13.87 Mg/ha/yr", which is larger than its own litterfall of 6.00–7.67 Mg/ha/yr. **Internally inconsistent; do not use.** | — |

**[inference] How these fit together for M3.** Floor biomass is a seasonal pulse, not a steady state:
1. Leaf input arrives from November to April.
2. Almost no decay happens in the dry months.
3. Fast monsoon decay (k ≈ 1.5–2.7/yr while wet) clears most of each year's input before the next November.

A workable model:

- L(t) = Σ inputs since 1 November × (1 − dry-season loss of about 5–10%/month) + carry-over.
- carry-over = previous-year L(April) × exp(−k_wet × 0.33 yr), with k_wet ≈ 2 for teak and about 2.5 for mixed. That leaves about 50% of the woody part and about 20–40% of leaf.
- Reset L to the fire-consumption residual after a burn: the Jhariya high-fire zone has about 63% of the unburnt floor.

The Jenny K values (0.5–0.74) mean that the minimum floor (in the rainy season) is about 0.35–1.0 × annual litterfall. The Jhariya rainy-season floor of 2.0–3.2 t/ha is mostly wood and partly decayed litter, not fine fuel.

## 11. Pande 2002, Kittur 2014, Tiwari 2013 (ABSTRACT ONLY)

- **Pande 2002.** All note numbers check against the abstract. Leaf fall is 2,868 / 4,149 / 2,576 kg/ha/yr (sites I/II/III), and total litterfall is 3,305 / 4,536 / 3,276. Leaf is 79–91%. Peaks are in January and March at all sites. Site II was attacked by *Hyblaea puera* and *Eutectona machaeralis*, which caused a September leaf drop and a bimodal pattern. Full text is not online.
- **Kittur 2014.** Moist deciduous forest in Chhattisgarh. Total forest-floor fuel is **2.2–3.38 Mg/ha**, mostly duff litter plus small branches and twigs. The net fuel change was positive in high- and medium-frequency zones and negative in low- and no-fire zones. This matches the note.
- **Tiwari 2013.** Floor litter mass is 5.03 ± 0.25 (2010) to 6.54 ± 0.31 Mg/ha (2006). Leaf litter is 881–1370 g/m²/yr, and **total litterfall 6.00 ± 0.33 (2011) to 7.67 ± 0.31 Mg/ha/yr (2009)**; the note did not have the total. 70–90% falls in the dry season. This matches the note, but see the decay inconsistency in section 10.

## 12. Li et al. 2025, RSE (ABSTRACT ONLY)

Validated on 105 plots in Liangshan, China: R² 0.67, RMSE 2.56 Mg/ha, rRMSE 31.6%. The method uses a 20-year Landsat time series, foliage fuel load from a radiative transfer model, and weather-driven decay. The note is correct.

Two papers I did not read in full but that do the same thing:
- Hudak et al. 2023 (Ecol. Model.) runs an Olson accumulation-decay model at 5 m from lidar crowns, with pixel RMSD 0.21 kg/m² (2.1 t/ha).
- Wessollek & Forkel (EGU 2023) run a 333 m data-model fusion using LAI and GEDI with Harmon 2020 decay rates; the abstract gives no metrics.

---

## Verified numbers

| Quantity | Value | Status | Source |
|---|---|---|---|
| Bhoramdeo floor, seasonal mean | 2.00–3.65 t/ha | ✔ correct | Jhariya 2017, Table 1 |
| Bhoramdeo floor, summer peak | 2.30–3.95 t/ha (fresh leaf 1.28–2.05) | new | Jhariya 2017, Table 1 |
| Bhoramdeo litterfall | 4.75–7.56 t/ha/yr | ✔ | Jhariya 2017, Table 2 |
| Bhoramdeo turnover K / time | 0.70–0.74 / 1.35–1.43 yr | ✔ | Jhariya 2017, Table 4 |
| Fire cut to litterfall (low / medium / high) | −11.5 / −24.4 / −37.2% | new | Jhariya 2017 |
| Gadchiroli fuel, Feb→May | 291–295 → 424–428 g/m² fresh weight; 2001: 370 → 450 (Feb→Mar) | new | Saha 2002, Table 2 |
| Gadchiroli flame height | 55 ± 11.6 cm, 60 ± 6 cm, never above 75 cm | ✔ | Saha 2002 |
| Mudumalai grass gain over 2 yr | MR2 75.4, MR3 177.5 g/m² (unburnt plots only) | ✔ | Mondal & Sukumar, S2 Table A |
| Mudumalai standing grass, 2006 | MR3 251.8 g/m² | new | same |
| AABR litterfall | 4.19 ± 0.305 Mg/ha/yr; peak November, low June | ✔ | Thakur 2022 |
| AABR record length | **5 yr (2015–2019)** | ✘ the note said "contradicts itself on 1 or 5 years"; corrected | Thakur 2022 |
| AABR turnover K | 0.50–0.62 | new; widens the note's "70–92%" | Thakur 2022, Table 4 |
| Litterfall correlation with NDVI / SAVI / NDMI | r = 0.68 / 0.65 / 0.43 | new | Thakur 2022, Table 5 |
| Mudumalai dry deciduous 1-hr / 10-hr / 100-hr | 1.2–1.5 / 0.8–1.2 / 3.2–3.8 Mg/ha | new | Kodandapani 2008, Table 1 |
| Nilgiri dry deciduous total / 1000-hr | 21.3 ± 17 / 15.3 ± 15 | ✔ (from snippet) | Kodandapani 2013 |
| Labenski litter R² | 0.27 (dead 1-hr 0.41) | ✘ the note gave the range 0.27–0.41 for litter; clarified | Labenski 2023, Table 6 |
| Labenski RF vs stratum mean | litter only 9% lower RMSE | ✘ the note said "no better"; clarified | Labenski 2023, Table 7 |
| Chhindwara leaf fall | 2.58–4.15 t/ha/yr; total 3.28–4.54 | ✔ | Pande 2002 (abstract) |
| Kittur floor fuel | 2.2–3.38 Mg/ha | ✔ | Kittur 2014 (abstract) |
| Raigarh floor | 5.03–6.54 Mg/ha; litterfall 6.00–7.67 Mg/ha/yr | ✔ plus the litterfall total | Tiwari 2013 (abstract) |
| Li 2025 validation | R² 0.67, RMSE 2.56 Mg/ha, n = 105 | ✔ | abstract |
| Central India deciduousness (AD) | dry deciduous 43.6–55.1 in 2011; 57.6 / 61.0 / 64.5 in dry / normal / wet years | new | Singh 2020 |
| Sagar leaf litter | 4.959 t/ha/yr | ✔ | Prasad 1985 (abstract) |
| Ranchi monthly teak litterfall (January 1.52, February 1.56) | not verified; no full text found | ? | Toppo 2021 |

## Monthly build-up for dry deciduous teak in central India

This merges three sources:
- Jhariya: leaf fall peaks in December, concentrated in November–March.
- Pande: peaks in January and March.
- Saha: standing load at 0.70 / 0.88 / 0.97 / 1.00 of peak in February / March / April / May.

| Month | Share of annual leaf fall (Jhariya + Thakur + Pande, **[inference]**) | Standing fine fuel, fraction of the April peak |
|---|---|---|
| Nov | 0.12 | 0.15 **[inference]** |
| Dec | 0.20 | 0.35 **[inference]** |
| Jan | 0.20 | 0.55 **[inference]** |
| Feb | 0.18 | **0.70** (Saha) |
| Mar | 0.15 | **0.88** (Saha) |
| Apr | 0.07 | **0.97–1.00** (Saha) |
| May–Oct | 0.08 | decays to about 0.1–0.3 carry-over |

For Ratapani **[inference]**: peak fine fuel (April) ≈ 0.45 × annual leaf fall (Jhariya ratio) + grass + fine wood. In teak with leaf fall of 2.6–5.0 t/ha/yr, that gives about **1.2–2.3 t/ha of fine leaf litter, or about 2.3–4 t/ha of total floor**. This sits mostly in FSI's 20–40 g/ft² band (2.15–4.31 t/ha), not in "<20".

---

## Ranked action list

| Rank | Action | Thread | Expected gain | Effort |
|---|---|---|---|---|
| 1 | **Fill the strata with a summer floor value of 0.5 × annual litterfall, scaled by burn frequency** (0.63 / 0.76 / 0.88 / 1.0 from Jhariya Table 2, using our 2017–2026 burn count per cell). Teak: litterfall 4–5 → about 2.4 t/ha in yearly-burnt cells and 3.9 in unburnt. | fuel-map | Moves many cells from FSI "Low" to the 20–40 g/ft² band, consistent with fire history. Highest value per hour. | 0.5 day |
| 2 | **Monthly multiplier from the Saha/Jhariya curve** (table above), with a monsoon reset and the curve shifted a month earlier in years with an early monsoon withdrawal. | fuel-map, short-horizon | Turns the static map into a monthly product for January–May at no field cost. | 0.5 day |
| 3 | **Grass term for open strata and blanks: 0.45–0.75 t/ha in the year after a burn, plus 0.9 t/ha for each unburnt year, capped at about 2.5** (Mondal & Sukumar MR3), using time-since-burn. | fuel-map, fire-spread | Adds the fine fuel component that carries spread in open forest. Labenski shows understorey is where remote sensing adds value (25–40% over stratum means). | 0.5 day |
| 4 | **S2 per-pixel annual deciduousness (Singh 2020 formula, Sc = 0.005) as a ± multiplier on leaf fall within each stratum**; NDVI over NDMI (Thakur r = 0.68 vs 0.43). | fuel-map | Texture within strata plus a ±10% year signal. It cannot be validated without plots. | 1–2 days |
| 5 | **Season-severity logistic of MR3 form (previous May–October rain, November–December rain, previous-year burnt fraction)** fitted to Ratapani yearly burnt fraction for 2017–2026, with Mudumalai coefficients as priors. | short-horizon | A pre-season (January) forecast of the year's burnt area. Mudumalai r = 0.47–0.89. With n = 10 years, treat it as indicative. | 1 day |
| 6 | **Daily dead fuel moisture: FMIrel (5.321 + 0.465·FMI) or m_gen D2 from ERA5-Land**, plus days-since-rain, as a feature in the VIIRS burn-date model. Ablate against raw VPD. | short-horizon | Small, probably under 0.01 AUC over VPD **[inference]**. | 0.5 day |
| 7 | **Fire-behaviour fuel model for teak and mixed forest: 1-hr ≈ 2–3, 10-hr ≈ 1.0, 100-hr ≈ 3.5 t/ha** (Kodandapani 2008 planar intercept), TL6 depth, 25% extinction. Run sensitivity with 100-hr at 1 t/ha. | fire-spread | Grounds the custom TL model in measured Indian dry deciduous fuels. | 0.5 day |
| 8 | Skip remote-sensing regression of litter without plots: Labenski shows only a 9% RMSE gain over type means even with lidar. If plots are ever collected, put them in **grass and shrub** strata first. | fuel-map | Avoids wasted effort. | — |
| 9 | Ask the Li 2025 authors (Veraverbeke, VU Amsterdam) or the VU repository for the PDF and code. Their RTM-based foliage fuel load and decay function are the missing pieces of a full M3. | fuel-map | Would let us replace the rule-based M3 with a published one. | email |
