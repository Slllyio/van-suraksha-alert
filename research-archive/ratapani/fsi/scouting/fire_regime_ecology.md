# Fire regime and fire ecology: where fire recurs, and how to encode "fire memory" (scouting round 3, topic "regime", 14 Oct 2026)

Each source is marked **FULL** (whole text obtained and the relevant sections read), **PARTIAL** or **ABSTRACT ONLY**. My own reasoning is marked **[inference]**. Earlier notes already cover these, so they are not repeated: Kodandapani 2008 fuel loads and Mondal & Sukumar grass build-up (`fuel_load_values_fullread.md`); Hawkes and self-excitation kernels (`short_horizon_prediction*.md`); burn-scar persistence (Melchiorre & Boschetti 2018 in `high_res_imagery.md` and `leaf_fall_phenology.md`); fire lines and controlled burns (`fire_management_practice.md`); the interior-versus-village ignition gap (`human_fire_drivers.md`).

## Headline findings

1. **The pattern we see (a burn 1–2 years ago means more ignitions; a burn this season means 5× fewer) is the standard shape in frequently burned tropical systems.** The probability of burning against time since fire rises over the first 2–4 years and then falls. Three satellite fire atlases fitted this with a **discrete lognormal hazard**, which beat the Weibull: Arnhem Land (hazard peak at 2–3 yr), Cerrado (peak at 3–4 yr) and miombo (median interval 4.5 yr). Section 1 gives the exact formula and parameters.
2. **The falling tail of that curve is mostly a place effect, not a fuel effect.** Oliveira/Pereira say so directly: long-unburned patches are rare, and the ones that stay unburned are intrinsically low-hazard places. In a single cross-section, "time since fire" is therefore largely a proxy for **how ignition-prone a cell is**. Our "1–2 years ago ignites more" result is most likely the same thing: persistent human ignition sources (paths, mahua and tendu sites, fire lines, grazing routes) burn the same cells every year or two. **[inference]** Section 9 gives the test.
3. **The within-season suppression (>50% burned → 5× fewer new ignitions) is a fuel-consumption effect.** In teak and litter systems it lasts **less than a year**, because leaf fall replaces the fuel every January to March. Supporting evidence: Parks 2015 finds the fuel-break effect decays fastest in grass/surface-fuel systems (about 6 yr there, against 16 yr in conifers). Mondal & Sukumar 2016 at Mudumalai find that last year's burned fraction cuts this year's area only when the previous monsoon was weak. Their fitted crossover is at **~1,040 mm (landscape) and ~1,230 mm (1,200–1,400 mm moisture regime)** of June–October rain, and Ratapani sits near it. **[inference]**
4. **Concrete features:** (a) categorical years-since-last-burn with an explicit "never burned in record" level; (b) the cell's long-run burn rate, leave-one-year-out, as a "frailty" term; (c) burned fraction last year × previous-monsoon rain; (d) this season's burned fraction of the cell and its ring; (e) a fitted discrete-lognormal hazard λ(tsf) per stratum, used as an offset or prior. My guess is +1–3 points of recall at 5 picks per beat per day, with most of it from (b) and (d). **[inference]**
5. **Lantana does not obviously raise fire frequency.** In BRT Tiger Reserve, more frequent fire went with **lower** Lantana density: fire frequency was the best predictor, explaining 23.6% of deviance. The "fire–Lantana cycle" (Hiremath & Sundaram 2005) is still a hypothesis with no numbers. Low priority for the 2-day model.

---

## 1. Pereira Júnior, Oliveira, Pereira & Turkman 2014, *PLoS ONE* 9:e102380, "Modelling fire frequency in a Cerrado savanna protected area". **FULL**
Link: https://doi.org/10.1371/journal.pone.0102380 (OA). Copy read: https://dataserver-coids.inpe.br/queimadas/queimadas/Publicacoes-Impacto/material3os/2014_PereiraJr_etal_ModellingFire_PLoSONE_DE3os.pdf

**What it shows.** Jalapão State Park (159,225 ha), Landsat burn scars 1997–2008 classified with OBIA (≥3 images per dry season). The total area burned was 585,122 ha, almost 4× the park. 77.6% of the area burned 3–6 times, 6.4% more than 7 times, and 16.0% once or twice. Fire rotation period (FRP) is 3.0 yr and mean annual area burned is 34%. Fire intervals were modelled with a **discrete lognormal** that includes single-censored intervals (open at the start or end of the record), fitted by maximum likelihood with R `survival`. The Hollander–Proschan test never rejected the fit.

Formulas (from the paper; Φ is the standard normal CDF, t = 1, 2, … years since the last fire):
- Survival: A(t) = 1 − Φ((ln k − μ)/σ) for k ≤ t < k+1
- **Hazard (annual probability of burning given unburned until t): λ(t) = 1 − Φ((μ − ln t)/σ) / Φ((μ − ln(t−1))/σ)**, with Φ(·) = 1 for t = 1
- Median interval = smallest integer ≥ exp(μ); mode = smallest integer > exp(μ − σ²)

Table 1 (read from the rendered page):

| Cover | % area | FRP (yr) | APAB % | μ | σ | median | mode | hazard peak (yr) |
|---|---|---|---|---|---|---|---|---|
| Shrub savanna | 58.9 | 2.72 | 37 | 0.82 | 0.66 | 3 | 2 | 4 |
| Open woodland | 18.4 | 2.75 | 36 | 0.93 | 0.69 | 3 | 2 | 4 |
| Dense woodland | 6.9 | 5.49 | 18 | 1.78 | 0.99 | 6 | 3 | 4 |
| Vereda | 5.5 | 3.02 | 33 | 0.90 | 0.80 | 3 | 2 | 3 |
| Gallery forest | 8.5 | 4.44 | 23 | 1.19 | 0.91 | 4 | 2 | 3 |
| Ciliary forest | 0.6 | 4.57 | 22 | 1.39 | 0.92 | 5 | 2 | 4 |
| Shifting cultivation | 0.8 | 3.71 | 27 | 0.86 | 0.89 | 3 | 2 | 3 |

I recomputed λ(t) from these parameters. My numbers reproduce the paper's stated peaks (0.42, 0.37, 0.33, 0.31, 0.24, 0.20, 0.13):

| t (yr) | 1 | 2 | 3 | 4 | 5 | 6 | 8 |
|---|---|---|---|---|---|---|---|
| Shrub savanna | 0.11 | 0.35 | 0.42 | 0.42 | 0.41 | 0.39 | 0.36 |
| Open woodland | 0.09 | 0.30 | 0.36 | 0.37 | 0.36 | 0.35 | 0.32 |
| Dense woodland | 0.04 | 0.10 | 0.13 | 0.13 | 0.13 | 0.13 | 0.12 |
| Shifting cultivation | 0.17 | 0.31 | 0.31 | 0.30 | 0.28 | 0.26 | 0.23 |

Two points from the paper matter for us:
- The hazard rises 3× from year 1 to year 2, which is grass fuel recovery. It falls slowly after the peak because "long unburnt patches are quite rare", and the patches that survive are the low-hazard ones.
- Land covers with the shortest FRP also have the highest hazard at every age. In other words, place-level propensity and the time-since-fire effect are tangled together.

**Concrete action for us (thread 1).**
- Fit the same discrete lognormal on Ratapani cells 2017–2026, per FSI density class or fuel stratum. Use interval censoring: the first interval is left-censored, the last one right-censored. Code: `survival::survreg(Surv(t1, t2, type="interval2") ~ stratum, dist="lognormal")` on yearly cell burn records, or a 15-line Python MLE using the formulas above.
- Add λ(tsf; μ_stratum, σ_stratum) as a feature, or as a log-offset in a calibrated model.
- Expected effect: small on its own if the tree model already sees raw tsf. Its value is smoothing for rare tsf values (5+ years) and for cells with short records. **[inference]**

## 2. Oliveira, Turkman & Pereira 2013, *IJWF* 22:479–492, "An analysis of fire frequency in tropical savannas of northern Australia, using a satellite-based fire atlas". **ABSTRACT ONLY** (the Zenodo copy was removed after a takedown; no other OA copy found)
Link: https://doi.org/10.1071/WF12021

**What it shows.** Western Arnhem Land, ~24,000 km², satellite fire atlas 1990–2008. Mean annual area burned is 36% and median fire intervals are 1–4 years. Continuous Weibull, discrete Weibull and discrete lognormal were compared, and **the discrete lognormal fitted best**, giving non-monotonic hazards that **peak at 2–3 years** and then decline. Open forest had the strongest fuel-age dependence and closed forest the weakest. "Age-specific fire incidence is much higher for older vegetation patches than suggested by earlier analysis." Choosing the model matters when inferring the hazard for long intervals that were rarely observed.

**Concrete action for us (thread 1).** Use the discrete lognormal rather than the Weibull for our time-since-fire prior. The Weibull forces a monotonic hazard and cannot reproduce our "1–2 yr up, longer down" pattern. The source is the same group as Section 1, which gives the formulas.

## 3. Mondal & Sukumar 2016, *PLoS ONE* 11:e0159691, "Fires in seasonally dry tropical forest: testing the varying constraints hypothesis across a regional rainfall gradient" (Mudumalai). **FULL**
Link: https://doi.org/10.1371/journal.pone.0159691

**What it shows.** Mudumalai, 1990–2010: yearly area burned, 13 rain gauges, 87 fuel plots. Four moisture regimes: MR1 >1,400 mm, MR2 1,200–1,400, MR3 1,000–1,200, MR4 <1,000. Mean area burned 1991–2010 was **20.1% ± 3.2%**, ranging from 49% (1991) to 0.1% (2006). By regime it was MR1 5.2%, MR2 23.6%, MR3 34.0%, MR4 8.9%, a unimodal shape against rainfall. Fuel was mainly leaf litter in MR1, with grass rising toward the drier regimes.

The model is a quasi-binomial GLM (logit) of the proportion burned. Inputs are **burn.prev.prop** (the fraction burned the previous year), **wet** (May–October rain of the previous year, mm, a fuel-load proxy that correlated with measured fuel at 87 plots) and **earlydry** (November–December rain, mm, a fuel-moisture proxy).

Coefficients (logit):
- **Landscape** (r = 0.55): intercept −4.121; burn.prev.prop **−20.73** (p 0.083); wet 0.004; earlydry 0.070; burn.prev.prop:wet **+0.020** (p 0.074); wet:earlydry −0.00008 (p 0.090).
- **MR2, 1,200–1,400 mm** (closest to Ratapani's rainfall): intercept −2.217; burn.prev.prop **−42.99** (p 0.011); wet 0.002; earlydry 0.092; burn.prev.prop:wet **+0.035** (p 0.011); wet:earlydry −0.00009.
- **MR3, 1,000–1,200 mm:** intercept −7.412; wet 0.008; earlydry 0.073; wet:earlydry −0.00008. Last year's burn dropped out.
- **MR1:** only earlydry −0.015 survived. **MR4:** wet +0.026, earlydry +0.122, wet:earlydry −0.0002.

How it reads:
- After a weak monsoon, a big burn last year means less fire this year, because fuel is not replaced.
- After a strong monsoon, the sign flips: with ~50% burned the previous year, this year's area **increases** with wet-season rain.
- The previous-burn slope is −20.73 + 0.020·wet, which is zero at wet ≈ 1,036 mm for the landscape and ≈ 1,228 mm for MR2 (43.0/0.035). **[inference from their coefficients]**
- Low November–December rain means more burning in the litter-dominated regimes.

**Concrete action for us (threads 1 and 4).**
- Add the interaction feature `burned_frac_last_season × JJASO_rain_last_monsoon` per cell. Build it from IMD 0.25° or CHIRPS rainfall, plus `ND_rain` (November–December).
- Ratapani's monsoon (~1,100–1,250 mm) is close to the crossover. That means previous-year burning should have a **weak or positive** effect in normal-to-wet years and a negative one only after dry monsoons. This agrees with our "1–2 years ago ignites more" result. **[inference]**
- Check it in our data: split the year-to-year transition by the previous monsoon tercile.
- For thread 4, use earlydry as a season-level dryness prior.

## 4. Parks, Holsinger, Miller & Nelson 2015, *Ecological Applications* 25:1478–1492, "Wildland fire as a self-regulating mechanism: the role of previous burns and weather in limiting fire progression". **FULL** (methods and results read)
Link: https://research.fs.usda.gov/treesearch/49463 (PDF). Data: USFS RDS-2015-0021/22/23.

**What it shows.** Four US wilderness areas, 1972–2012; 1,038 fires (437 large). Method:
- Pixels along the perimeters where a later fire met an earlier one were labelled **LIMITING** (the later fire stopped within 375 m of the old edge) or **NOT LIMITING**.
- A logistic regression of that label on years between fires, using a 1% subsample with a 2,500-model ensemble to handle spatial autocorrelation.
- Interactions older than 25 years were dropped.

Results:
- A previous burn acts as a fuel break (P > 0.30) for **~6 yr in the grass and surface-fuel Gila (GAL)** against ~16 yr in the three northern conifer areas. Large fires in the north were >75% effective for 4 years and ~50% at 11 years.
- ROC is 0.72–0.82 (all fires) and 0.77–0.87 (large fires).
- Weather matters: in CCE, 10 years after fire, P(limiting) = 0.97 at median ERC but 0.30 at the 99th-percentile ERC. Fuel-break longevity was 10 yr under extreme conditions against 24 yr under moderate ones.
- In GAL, "rapid growth and accumulation of fine fuels during wet years erases the effects of the previous fire".

**Concrete action for us (threads 1 and 4).**
- Copy the design for **within-season** memory. For each new ignition or burn-day, compute days since the neighbouring cell burned and fit P(stops at old edge) against days and dryness.
- For thread 4 (spread), make burned-this-season pixels non-burnable. Release them at the next leaf fall, or after ~30–60 days if regrowth or new litter is detected. That is my guess for teak litter, not a published number. **[inference]**
- For thread 1, interact `frac_cell_burned_this_season` with a dryness index. Expect the suppression to weaken on the hottest, driest days, as ERC did here. **[inference]**

## 5. Kodandapani, Cochrane & Sukumar 2008, *Forest Ecol. Manage.* 256:607–617 (Nilgiri landscape). **FULL** (new regime details only; the fuel numbers are in `fuel_load_values_fullread.md`)
Link: https://doi.org/10.1016/j.foreco.2008.05.006. Copy: wgbis.ces.iisc.ac.in (issue53 bibliography PDF)

**What it shows.**
- Seven years of supervised-classification burn maps, 85–95% accurate.
- **Mean area burned:** dry deciduous 17,000 ± 8,700 ha/yr (FRI 6 yr); dry thorn 3,200 ± 3,180 (FRI 10 yr); moist deciduous 770 ± 930 (FRI 20 yr). Whole landscape 21,600 ± 9,700 ha (FRI 7 yr).
- ≥50% of fire polygons each year fell in dry deciduous forest.
- **Mean fire size:** moist deciduous 10 ha; dry thorn about 2× that; dry deciduous about 4× (≈40 ha). Largest fire 9,900 ha (1996, dry deciduous).
- **Area never burned in 7 yr:** 33% of dry deciduous, 56% of thorn, 70% of moist deciduous.
- **Burned more than once:** 34% of dry deciduous, 18% of thorn. The maximum was 7 burns in 7 years, on small areas.
- **FRI against distance from the landscape boundary follows a negative exponential (F1,11 = 15.67, r² = 0.63, p = 0.003).** FRI is >10 yr within 5 km of the boundary and shorter further in, so **the interior burns more often**.
- Fire-frequency classes (1 fire / 2–5 / >5 in 16 yr) went with a 50% and 60% loss of species diversity and ~30% fewer saplings.
- Dry deciduous fires are larger because of compact, continuous grass fuel. Leaf fall and fine-fuel curing run from January to early March.

**Concrete action for us (thread 1).**
- The interior-burns-more pattern matches Ratapani's interior cells, which ignite ~2× more (`human_fire_drivers.md`). Add **distance to sanctuary boundary** (not only distance to village) as a separate feature, and fit FRI(d) = a·exp(−b·d) on our 2017–2026 scars as a check.
- Use the 34%-reburned and 33%-never-burned fractions as a sanity check of our own frequency map. A large departure would point to label problems. **[inference]**

## 6. Kodandapani, Cochrane & Sukumar 2004, *Conservation Biology* 18:1553–1561, "Conservation threat of increasing fire frequencies in the Western Ghats". **ABSTRACT ONLY** (paywalled; IISc ePrint restricted)
Link: https://doi.org/10.1111/j.1523-1739.2004.00433.x

**What it shows.** Ground maps of every fire in Mudumalai Wildlife Sanctuary, 1989–2002, plus imagery. Sanctuary FRI is **3.3 yr**, and every vegetation type is under 7 yr. Fire frequency increased ~3× over 80 years, and the estimated FRI for the Western Ghats is ~5 yr. `ground_truth_sources.md` cites 2.7 yr from another snippet; the abstract says 3.3.

**Concrete action for us.** Use it as a benchmark only. If Ratapani's 2017–2026 scar record gives an FRI far above 3–6 yr for dry teak, suspect missed small litter fires (thread 2), not a truly gentler regime. **[inference]**

## 7. van Wilgen et al. 2022, *Fire Ecology* 18:13, "An analysis of the recent fire regimes in the Angolan catchment of the Okavango Delta" (miombo). **FULL**
Link: https://doi.org/10.1186/s42408-022-00138-3. OA copy: researcharchive.lincoln.ac.nz (bitstream 2a3443a3…)

**What it shows.**
- MCD64A1 C6, 2000–2020. Per-pixel intervals, with open-tailed intervals treated as censored. Weibull median interval MEI = b·(ln 2)^(1/c), with b the scale and c the shape.
- **Median FRI:** open woodland and grassland 1.85 yr (0.57% never burned); short bushland 2.23 yr (0.69%); **miombo 4.50 yr (13.9% never burned)**.
- Miombo burns in August–September; 78.3% of its burned area is in the late dry season.
- Human population density did **not** change FRI. It did change how much miombo is flammable at all: **11.5% unburned where people live against 19.0% where they don't**.
- Woodland clearing increased grass biomass by 20–50% (citing Chidumayo & Kwibisa 2003).

**Concrete action for us (thread 1).** The same split probably holds in Ratapani: people decide **which cells are in the burnable set**, and fuel and weather decide the interval within it. Encode both a "ever burned 2017–2025" flag and, separately, the interval and tsf for burnable cells. Cells never burned in 9 years should get their own category, not tsf = 9+. **[inference]**

## 8. Sundaram, Hiremath & Krishnaswamy 2015, *NeoBiota* 25:27–46, "Factors influencing the local scale colonisation and change in density of *Lantana camara* in South India" (BRT Tiger Reserve). **FULL**
Link: https://doi.org/10.3897/neobiota.25.8354

**What it shows.**
- Lantana surveys from 1997 and 2008.
- Fire maps for 10 of 11 years: roads driven every April–May and burns marked on 1:50,000 sheets, plus 17 fixed vantage points. A grid cell counted as burned only if its centre burned.
- **Colonisation** was driven by propagule pressure (nearby Lantana).
- **Change in density** was best explained by **fire frequency**, which accounted for **23.6% of deviance** with the highest summed Akaike weight. The effect was **negative**: more fire, less Lantana gain. Plots: 22 unburned, 19 burned once, 6 twice, 4 three times.
- Soliga early dry-season burning (to clear understorey, collect NTFP and keep trails open) is part of the regime there. Suppressing fire probably raised invasibility.

**Concrete action for us (threads 3 and 4).** Do not add a Lantana-raises-ignition term to the 2-day model. For the fuel map, Lantana thickets probably mark long-unburned cells (a low burn-count area). Their fuel is green and woody shrub fuel that burns only under extreme conditions. Map them as a separate fuel class if field crews flag them, since GEDI or Sentinel-1 shrub signal is suggested in `fuel_load_values_fullread.md`. Gain for 2-day prediction is about zero. **[inference]**

## 9. Hiremath & Sundaram 2005, *Conservation and Society* 3(1):26–42, "The fire–Lantana cycle hypothesis in Indian forests". **PARTIAL** (only the magazine version on currentconservation.org; the ATREE PDF did not download)
Link: https://archived.atree.org/node/1060

**What it shows.** A hypothesis with no numbers. More frequent fires degrade the forest and favour Lantana, which resprouts after burning, and Lantana then fuels more and hotter fires. The authors say empirical data on fire frequency and severity effects in Indian dry forests are lacking. Section 8 later tested part of it and found the opposite sign for density.

**Concrete action.** None for thread 1. Use it in the report as context only.

## 10. Ratnam, Chengappa, Machado, Nataraj, Osuri & Sankaran 2019, *Frontiers in Ecology and Evolution* 7:8, "Functional traits of trees from dry deciduous 'forests' of southern India suggest seasonal drought and fire are important drivers". **FULL** (6 pp)
Link: https://doi.org/10.3389/fevo.2019.00008

**What it shows.** Relative bark thickness is 8.75 ± 0.47% in dry deciduous trees against 4.26 ± 0.26% in evergreen trees (χ² = 50.0, p < 0.0001). Dry deciduous trees also have lower SLA, lower height-to-diameter ratio and higher wood density. Together with a C4 grass understorey, the authors argue southern dry deciduous "forests" are mesic savannas. They summarise: return intervals of 1–6 yr, and 10–50% of these landscapes burn each year.

**Concrete action for us (thread 1).** This supports borrowing the savanna hazard curves from Sections 1, 2 and 7, rather than forest curves (conifer or boreal decades-long fuel breaks). Where Ratapani has grass under an open canopy (FSI open forest, blanks), expect the savanna-like rise of hazard from year 1 to years 2–3. Under closed teak with litter only, expect a flat curve. **[inference]**

## 11. Murphy & Russell-Smith 2010, *IJWF* 19:46–51, "Fire severity in a northern Australian savanna landscape: the importance of time since previous fire". **ABSTRACT ONLY** (figshare copy embargoed)
Link: https://doi.org/10.1071/WF08202

**What it shows.** A 10-year fire history. From 1 to 5 years after a fire, P(next fire is "severe") rose from **3% to 8%** for early dry-season fires and from **21% to 43%** for late dry-season fires. The rise was not confined to the first 2–3 years. Lowering fire frequency raises severity: a negative feedback between frequency and severity.

**Concrete action for us (threads 2 and 4).** Expect larger, higher-dNBR scars in cells with long tsf, especially after mid-March. Use tsf as an input to the scar-size prior (thread 2) and to the fuel or intensity multiplier in the spread model (thread 4). **[inference]**

## 12. Fernandes, Loureiro, Magalhães, Ferreira & Fernandes 2012, *IJWF* 21:380–384, "Fuel age, weather and burn probability in Portugal". **ABSTRACT ONLY** (the UTAD OA copy is behind a bot check)
Link: https://doi.org/10.1071/WF10063

**What it shows.** Fire atlas 1975–2008; survival analysis of fires 1998–2008. FRI is 23–52 yr and median fire-free interval 18–47 yr. The hazard rises **near-linearly** with fuel age, which the authors call moderate dependence. **More severe weather (larger fires, or extreme fire danger) reduced fuel-age dependency and selected older fuels.** Using only complete intervals inflated the fuel-age dependency compared with including censored intervals.

**Concrete action for us (thread 1).**
- Include censored intervals when fitting Section 1. If we use complete intervals only, we will overstate the tsf effect.
- Add `tsf × dryness` (VPD or FWI percentile) so the tree can learn that dry days override fuel memory.

## 13. Percival, Sato, Razanaparany, Harilalao, Razafiarison & Kitajima 2023, bioRxiv 2023.09.12.557329, "Non fire-adapted dry forest of north-western Madagascar: escalating and devastating trends revealed by remote-sensing data". **ABSTRACT ONLY** (bioRxiv returned 429; abstract via Europe PMC PPR725462)

**What it shows.** Ankarafantsika National Park; 3,052 ha of intact dry forest; Landsat 1985–2021 plus GEDI. There was no fire before 2014, then six fires in 2014–2021 with area growing exponentially. The October 2021 fire burned 1,052 ha, and **59% of it had burned at least once 2–4 years earlier** (60% of those twice, in 2017 and 2019). The first fire sharply cut cover and height, with negligible recovery within 4 years. "The likelihood for an initial burn to trigger subsequent fires within a few years was high."

**Concrete action for us.** This is the closest published dry-forest analogue to our "burned 1–2 years ago ignites more" result. The mechanism they propose is structural (an opened canopy and dead fuel), not ignition-driven. Section 16 gives the test that separates the two. **[inference]**

## 14. Archibald, Roy, van Wilgen & Scholes 2009, *Global Change Biology* 15:613–630, "What limits fire?" and Archibald, Scholes, Roy, Roberts & Boschetti 2010, *IJWF* 19:861–878, "Southern African fire regimes as revealed by remote sensing". **ABSTRACT ONLY**
Links: https://doi.org/10.1111/j.1365-2486.2008.01754.x and https://doi.org/10.1071/WF10008

**What they show.**
- 2009: random forest on MODIS 500 m burned fraction, R² = 0.68. Top drivers were tree cover, **rainfall in the previous 2 years** and rainfall seasonality. Human variables mattered only in some climates, often with the opposite sign to "more people, more fire". There was **no evidence that ignitions limited total burned area** at that scale.
- 2010: return time and FRP respond less to people than fire size and annual area do. People mostly make fires smaller and more numerous.

**Concrete action for us (thread 1).**
- Add 2-year antecedent rainfall (year-level) to the season-level baseline.
- At the 500 m, 2-day scale ignitions **are** limiting for us (>95% human-caused). Expect people to shape fire **size**, giving many small fires near villages, more than fire **return time**. This fits the Ratapani picture of small fires near villages and larger ones inside. **[inference]**

## 15. Hantson, Pueyo & Chuvieco 2015, *Global Ecol. Biogeogr.* 24:77–86, and 2016, *IJWF* 25:403–412, global fire size distributions. **ABSTRACT ONLY**
Links: https://doi.org/10.1111/geb.12246 and https://doi.org/10.1071/WF15108

**What they show.** On MCD45 2002–2010 at 2° cells, a power law fitted 93% of cells with significant fire. The exponent depends on precipitation and evapotranspiration, cropland cover and population density: more people means a steeper exponent, i.e. relatively more small fires. The 2016 paper finds the power law is not universal, and a **lognormal** fits better in many regions.

**Concrete action for us (threads 2 and 4).**
- Fit both a power law (above x_min) and a lognormal to our per-alert scar areas (Sentinel-2 or Landsat, 2017–2026). MLE for the power law: α = 1 + n / Σ ln(x_i / x_min), with x_min chosen by the KS distance. Compare by likelihood ratio.
- Use the fitted distribution as the size prior for the scar from each alert (thread 2) and to check spread-model output (thread 4).
- A steeper exponent near villages is a testable prediction. **[inference]**

## 16. What explains the "burned 1–2 years ago ignites more" effect? Candidate causes, ranked, with a test for each **[inference throughout, built from Sections 1–15]**

| # | Explanation | Support | Test on our data | If true, do this |
|---|---|---|---|---|
| A | **Place frailty (persistent ignition sources):** the same paths, NTFP trees, grazing routes and people burn the same cells every 1–2 yr | Pereira Jr / Oliveira on the falling tail; Similipal 26% of grids burned every year in 10 (Saranya 2014, abstract snippet); van Wilgen on "people set the burnable set" | Add the cell's leave-one-year-out burn rate (burns in 2017–2026 excluding the target year ÷ years observed). If the tsf = 1–2 effect shrinks by more than half, A dominates. Also refit with cell fixed effects (conditional logit within cell): a frailty-only effect vanishes there | Keep the long-run rate as the main memory feature, and drop or shrink tsf |
| B | **Annual fire-line and controlled burns** counted as "fires" | `fire_management_practice.md` D1–D2 | Mask cells crossed by detected fire lines, or with a burn date before 15 February. Recompute the lag effect | Remove from labels, or add a flag |
| C | **Post-fire grass and herb flush:** more fine fuel and continuity in years 1–3 | Hazard rises 3× from year 1 to year 2 in savannas (Section 1); MR3 grass build-up | Split by FSI canopy density: the effect should be larger in open forest and blanks than in very dense forest | Interact tsf with canopy density or dry-season NDVI of the understorey |
| D | **Fire-opened canopy and dead wood:** a drier microclimate and more dead fuel | Percival 2023; Kodandapani 2008 sapling losses | Effect larger where the previous fire's dNBR was high, or where post-fire NDVI dropped in the next wet season | Add the previous scar's dNBR and the change in wet-season NDVI |
| E | **Label artefact:** old scars or edges re-detected, or the dating spills into the next season | Scar persistence notes | Restrict to new ignitions ≥1 km from last year's scar edge. The effect should persist if real | Fix labels in thread 2 |
| F | **Neighbourhood:** last year's burn adjoins this year's ignition corridor | Hawkes notes | Replace the cell's own lag with a ring (500 m to 1.5 km) lag. Compare SHAP | Keep both |

The within-season 5× suppression has a different cause: fuel consumed this season, which is Parks's fuel break with a very short life. Keep it as `frac_cell_burned_this_season` and `frac_ring_burned_this_season`. Add `days_since_cell_last_burned_this_season` so the model can learn a release if litter keeps falling into April. **[inference]**

## 17. Similipal and central India recurrence (search-level evidence)
- **Saranya, Reddy, Prasada Rao & Jha 2014, *Environ. Monit. Assess.* 186:3283**, "Decadal time-scale monitoring of forest fires in Similipal Biosphere Reserve" (Resourcesat-1 AWiFS, 2004–2013). **ABSTRACT ONLY / snippet.** 2,175.9 km² (59.6% of vegetation) burned at least once. **1,211 grid cells (26%) burned in all 10 years.** The anomaly year was 2009, with 1,014.7 km². https://doi.org/10.1007/s10661-014-3619-7
- **Ranjan et al. 2024, *Tropical Ecology*** (MODIS 2003–2021, Getis-Ord Gi*). **ABSTRACT ONLY.** Hotspots cover 225 km² by FRP and 108 km² by burned area, with a 30 km² overlap, clustered near named villages (Ligirda, Debasthali, Bhanjbasa, Kiajhari).
- **Concrete action (thread 1):** 26% of grid cells burning every year is extreme place frailty (explanation A above). Check what share of Ratapani cells burned in ≥7 of 9 seasons. If it is large, a simple "chronic cell" flag plus the beat ranking may carry much of the recall at low cost. **[inference]**

## 18. Other sources checked (ABSTRACT ONLY or snippet)
- **Alvarado et al. 2017, *Ecological Indicators* 78:270** (Serra do Cipó, Landsat 1984–2014): the regime is **moisture-limited**, unlike fuel-limited African savannas. It supports interacting memory with dryness. https://doi.org/10.1016/j.ecolind.2017.02.037
- **Laris 2002, *Human Ecology*; Laris 2005, *RSE*** (Mali): early-season mosaic burning is widespread, mostly small fires, eventually >50% of the landscape. Coarse products missed ~90% of burned area. Early patches stop late fires, the same within-season suppression as ours. https://doi.org/10.1023/A:1015685529180
- **Serra do Tombador, *Remote Sensing* 6:9873 (2014)**: the annual probability of fire recurrence is highest in the reserve's buffer zone. The MDPI page was blocked (403).
- **Uhl & Kauffman 1990 / Cochrane 1999** (cited via a USDA review): in moist tropical forest, once burned means more likely to burn again, through dead fuel and an open canopy. This supports explanation D.

---

## Feature specification (thread 1), ready to code

All features are computed from scars closed **before** the issue day, so there is no leakage.

| Feature | Definition | Source of the idea | Expected value |
|---|---|---|---|
| `tsf_cat` | Seasons since the cell's last burn: {this season, 1, 2, 3, 4–5, 6+, never in record}. "Never" is its own level | Sections 1, 2, 7 | Already partly in the model; makes the U-shape explicit |
| `burn_rate_loo` | Burns in 2017–2026 excluding the target season ÷ seasons observed | Section 16 A | Probably the strongest single memory term |
| `ever_burned` | Any burn 2017–2026, excluding the target season | Section 7 | Separates burnable from never-burnable cells |
| `lambda_tsf` | Discrete lognormal hazard λ(tsf; μ_s, σ_s) fitted per stratum with censoring | Section 1 | Smooths sparse tsf values; useful as an offset in a calibrated model |
| `prev_burn_x_monsoon` | Burned fraction last season × June–October rain of the last monsoon (IMD or CHIRPS) | Section 3 | Sign changes near 1,040–1,230 mm |
| `nd_rain` | November–December rain | Section 3 | Season-level fuel-moisture prior |
| `rain_2yr` | Rain over the previous 2 years | Section 14 | Season-level prior |
| `frac_cell_burned_ts`, `frac_ring_burned_ts` | Fraction burned so far this season, in the cell and in its 1.5 km ring | Section 4 and our 5× result | Already strong; add the ring version |
| `days_since_cell_burn_ts` | Days since the cell last burned this season | Section 4 | Lets the model learn how quickly fuel is released again |
| `tsf_x_dryness` | tsf_cat interacted with a VPD or FWI percentile (or left for the trees to find) | Sections 4, 12 | Dry days override memory |
| `dist_boundary` | Distance to the sanctuary boundary | Section 5 | FRI falls with distance into the interior |
| `prev_scar_dnbr` | dNBR of the last scar in the cell | Sections 11, 16 D | Severity memory; tests explanation D |

## Datasets

| Name | Link | Resolution | Years | Licence | Access | Use |
|---|---|---|---|---|---|---|
| MODIS MCD64A1 C6.1 burned area | https://lpdaac.usgs.gov/products/mcd64a1v061/ | 500 m, monthly | 2000– | NASA open | Earth Engine `MODIS/061/MCD64A1` | Long-run burn rate before 2017 (`burn_rate_loo` back to 2001); coarse, misses small fires |
| VIIRS VNP64A1 burned area | https://lpdaac.usgs.gov/products/vnp64a1v002/ | 500 m | 2012– | NASA open | LP DAAC / Earth Engine (check the asset name) | Cross-check of the record |
| Global Fire Atlas (Andela et al. 2019, *ESSD* 11:529) | https://doi.org/10.3334/ORNLDAAC/1642 | Per fire, from 500 m | 2003–2016 (extensions exist) | Open, ORNL DAAC (from memory) | Download shapefiles | Fire size, duration and spread speed in MP for the thread 4 check |
| GlobFire (Artés et al. 2019, *Sci. Data* 6:296) | https://doi.org/10.1038/s41597-019-0312-2 | Fire patches from MCD64A1 | 2001– | CC-BY (from memory) | Earth Engine community assets / PANGAEA | Fire size distribution for central India |
| FRY fire-patch database (Laurent et al. 2018, *Sci. Data* 5:180132) | https://doi.org/10.1038/sdata.2018.132 | Patches from MCD64A1 and FireCCI | 2005–2011 | Open (from memory) | Download | Size and shape traits |
| GABAM 30 m annual burned area (Long et al. 2019) | https://doi.org/10.3390/rs11050489 | 30 m, annual | 2000– (years vary) | Open (from memory) | Zenodo / Casearth | Pre-2017 Landsat-scale burn history for tsf back-fill |
| IMD gridded rainfall | https://www.imdpune.gov.in/ | 0.25°, daily | 1901– | Free for research | Download | June–October and November–December rain for Section 3 features |
| CHIRPS v2 | https://www.chc.ucsb.edu/data/chirps | 0.05°, daily | 1981– | Public domain | Earth Engine `UCSB-CHG/CHIRPS/DAILY` | Same, finer grid |
| USFS fire-progression atlases (Parks 2015) | https://www.fs.usda.gov/rds/archive/Product/RDS-2015-0021 | 30 m | 1972–2012 | Public | Download | Method template only |

"From memory" means the licence or link was not re-checked this session.

## Reading status
- **FULL (7):** Pereira Júnior 2014; Mondal & Sukumar 2016; Parks 2015; Kodandapani 2008 (regime sections, new to these notes); van Wilgen 2022; Sundaram 2015; Ratnam 2019.
- **PARTIAL (1):** Hiremath & Sundaram 2005 (magazine version).
- **ABSTRACT ONLY (≈14):** Oliveira 2013; Kodandapani 2004; Murphy & Russell-Smith 2010; Fernandes 2012; Percival 2023; Archibald 2009 and 2010; Hantson 2015 and 2016; Saranya 2014; Ranjan 2024; Alvarado 2017; Laris 2002/2005; Serra do Tombador 2014.
- **Blocked:** Springer (Fire Ecology HTML), Elsevier, MDPI, UTAD, OpenPrairie (Cloudflare), ULisboa thesis repository. Consensus search quota was exhausted.

## Ranked action list (gain and effort are my estimates [inference])

| Rank | Action | Thread | Inputs | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Decompose the "1–2 years ago" effect.** Add `burn_rate_loo` and `ever_burned`, then refit. Run the cell-fixed-effect check, the fire-line mask and the ≥1 km-from-old-edge restriction (Section 16 A, B, E) | 1, 2 | Existing scars, fire-line layer | Tells us whether memory is place or fuel. +1–2 pts recall if place frailty is under-used now; also catches label artefacts | 0.5–1 day |
| 2 | **Ring and day versions of within-season burn:** `frac_ring_burned_ts` and `days_since_cell_burn_ts`, interacted with dryness | 1 | Scars closed before the issue day | +0.5–1.5 pts (extends the 5× effect to neighbours) | 0.5 day |
| 3 | **Mondal-style interaction:** burned fraction last season × last monsoon rain, plus November–December rain and 2-yr rain | 1 | IMD or CHIRPS | Small for "where"; helps season-level calibration and dry-monsoon years | 0.5 day |
| 4 | **Fit discrete lognormal hazards per stratum** with censoring; add `lambda_tsf` or use it as an offset | 1 | 2017–2026 cell burns (back-fill with MCD64A1 or GABAM before 2017) | +0–1 pt; better calibration for cells with sparse history | 1 day |
| 5 | **Fit fire-size distributions** (power law against lognormal) on our scars, and by distance to village | 2, 4 | Per-alert scars | Size prior for alert-to-scar; validation for spread | 0.5 day |
| 6 | **Severity memory:** `prev_scar_dnbr` and tsf in the scar-size and intensity priors | 2, 4 | dNBR per scar | Small | 0.5 day |
| 7 | **Chronic-cell flag** (burned in ≥7 of 9 seasons), shown to field staff in thread 5 | 1, 5 | Scars | Operational: a simple map officers trust | 2 h |
| 8 | **Lantana fuel class** only if field crews map it | 3 | Field data | About zero for thread 1 | n/a |
