# Literature review: a 10 m surface fuel load map for Ratapani Tiger Reserve (teak litter and cured grass, no field plots)

Compiled 15 Oct 2026. Each source is tagged with how far I read it:

- **[FULL]**: I read the full text, including its tables.
- **[PARTIAL]**: I read the full text but some tables did not parse, or I read only part of it.
- **[ABSTRACT]**: I saw only the abstract or a catalogue record.
- **[SECONDARY]**: I saw only a description of the paper in another source.

All unit conversions are mine: 1 ft² = 0.0929 m², and 1 g/m² = 0.01 t/ha.

**What I could not reach.** Springer (Fire Ecology, J. Forestry Research), MDPI, PMC, ScienceDirect HTML, the Wayback Machine, the MSU thesis repository and the JTFS site all blocked automated access. The Consensus search quota was used up. The OpenAlex and Semantic Scholar APIs were rate-limited. Papers behind those sites appear below at [ABSTRACT] or [SECONDARY] level.

---

## Q1. How FSI maps fuel load

**Main source [FULL]:** Forest Survey of India (2026). *Surface Fuel Load Mapping 2023-24.* FSI Technical Information Series Vol. 3 No. 2, ISBN 978-81-979398-0-8. https://fsiforestfire.gov.in/libraries/assets/documents/Surface%20Fuel%20Load%20Mapping.pdf (publication list: https://fsiforestfire.gov.in/Home/Publication). This is FSI's only stand-alone fuel load method document. I did not check the ISFR 2019/2021/2023 fire chapters for separate fuel-load methods; the search hits for them contained no fuel-load content.

**Field sampling (Sec. 1.1, 1.3.1, pp. 2–3)**
- They used 15,114 points, which the report calls "validation points". These were "collected by ground truth teams in areas adjacent to fire affected area and in different forest stratums further supported with NFI data". All of them were used to train the model.
- "From each location, a sample of the surface fuel load has been collected" (photos on pp. 4–5). The report does not give the plot or quadrat size, the number of subsamples, the sampling season or date, or which fuel components were separated.
- Samples were oven-dried "for 3 hours at a temperature of ~50 °C". That is not the usual standard of 60–105 °C to constant weight, so residual moisture is likely.
- The glossary defines "Litter" as "woody material of trees having diameter <5 cm and >2 mm, which is not decomposed". This is not the ecological meaning of litter (leaves). It is unclear what the samples actually contained.

**Stratification and extrapolation (Sec. 1.4.2, p. 9)**
- Three layers were overlaid: 17 forest type groups (FSI Forest Type Map 2021, 1:50,000), 4 canopy-density classes (VDF ≥70%, MDF 40–70%, OF 10–40%, Scrub <10%), and 4 slope classes from SRTM 30 m (0–10°, 11–20°, 21–30°, >30°). This gives 17 × 4 × 4 = **272 strata**.
- "Those strata where values were not captured from the field were merged with the other similar strata. For each strata, the mean values of the field surface fuel load data were provided."
- The result is a **lookup-table map**: every pixel in a stratum gets that stratum's mean value.

**Classes (Table 1.4, p. 9)**

| Class | g/ft² | t/ha (my conversion) |
|---|---|---|
| Low | 0–20 | 0–2.15 |
| Moderate | 20–40 | 2.15–4.31 |
| High | 40–60 | 4.31–6.46 |
| Very High | >60 | >6.46 |

**Fuel moisture map:** IDW interpolation of 516 sample points (Sec. 1.4.4).

**What is not published**
- Per-stratum values, sample sizes or variances.
- Any accuracy assessment, independent validation or uncertainty estimate.

The conclusion (p. 15) says the calculation "cannot be carried out with high precision with single date imagery. Periodic collection of samples is a requirement."

**Values relevant to Ratapani (Table 2.14.1, pp. 46–47)**
- Madhya Pradesh has 0 km² Very High, 433 km² High, 11,637 km² Moderate and 57,492 km² Low (61.97% of the RFA is Low).
- Raisen district has 64.18 km² Moderate and 2,480.84 km² Low, so **97.5% is Low (<2.15 t/ha)**.
- Sehore district has 42.66 km² Moderate and 1,153.45 km² Low, so **96.4% is Low**.
- In other words, FSI puts nearly all of Ratapani below 2.15 t/ha. That is lower than the field measurements in Q2 (about 3–4.5 t/ha of pre-fire litter in central Indian dry deciduous forest). Possible reasons are the timing of sampling, sampling next to areas that had already burned, and the odd "litter" definition.

**Related FSI report [PARTIAL]:** *Forest Fire Risk Zonation of India 2023-24* (Vol. 3 No. 3, 2026). Its risk layers are forest density, forest type (FTM 2023), elevation, slope, aspect (ASTER 30 m), biotic influence, grazing (IDW) and soil (Sec. 1.4.2). The fuel load map is not one of them. Layers were weighted "based on the analysis of archived forest fire detections"; no accuracy figures are given. Madhya Pradesh has the most area in the High risk class even though its fuel load is mostly Low.

---

## Q2. Measured forest-floor fuel in Indian dry deciduous and teak forests

| Study | Site / forest | Method | Key numbers |
|---|---|---|---|
| **Saha 2002**, Curr. Sci. 82(9):1144–1147 [FULL; scanned pages read as images]. https://www.currentscience.ac.in/Volumes/82/09/1144.pdf | Mendha, Gadchiroli, Maharashtra; dry deciduous forest (*Terminalia*, *Pterocarpus*, *Anogeissus*); annual March fires | 10 quadrats of 0.25 m², sampled every two weeks Feb–May, 1999–2001 | **Table 2 (g per 0.25 m² ± SE):** Feb 73.8±4.1 / 72.7±5.3 / 92.6±19.9; Mar 91.8±4.9 / 95±5.1 / 112.5±6.2; Apr 104.4±3.4 / 100.4±3.0; May 106±2.9 / 107±3.4. That is **Feb ≈2.9–3.7 t/ha, Mar 3.7–4.5, Apr–May 4.0–4.3 t/ha**. Load rose until mid-April and then levelled off. >75% of leaf fall was complete by late March. Leaf litter is the main fuel. Fire-protected plots "had no fuel-load accumulation from the previous year, the leaf litter had decomposed". Fire return interval was 1 yr. Flame height 55±11.6 cm (1999) and 60±6 cm (2001), never above 75 cm. Burn time of a 9 m² plot was 10–12.8 min. |
| **Jhariya 2017**, J. For. Environ. Sci. 33(4):330–341, doi:10.7747/JFES.2017.33.4.330 [FULL] | Bhoramdeo WLS, Chhattisgarh; dry deciduous forest; high/medium/low/no-fire zones | Forest floor: random 50×50 cm quadrats. Litterfall: 10 traps of 50×50 cm, monthly | **Table 1, summer (Apr–mid-June) forest floor, fresh + partly decayed + wood (g/m²):** high-fire 128+26+76 = **230 (2.3 t/ha)**; medium 178+49+99 = **327**; low 189+64+106 = **359**; no-fire 205+77+113 = **395 (3.95 t/ha)**. Fresh leaf litter alone was 1.28–2.05 t/ha. **Table 2, annual litterfall (g/m²/yr):** high-fire 475 (285 of it leaf), medium 572, low 669, no-fire 756 (529 of it leaf). In other words, frequent fire cut litterfall by 37% and summer floor fuel by 42%. Turnover k = 0.70–0.74; turnover time 1.35–1.43 yr. **Caution:** the reported SEs (about ±1–2 g/m² on means of 100–200 g/m² with n = 10) imply a CV of about 3%, which is not credible for litter. Treat these as means only. |
| **Kittur, Swamy, Bargali & Jhariya 2014**, J. For. Res. 25(4):857–866, doi:10.1007/s11676-014-0471-0 [ABSTRACT] | Achanakmar–Amarkantak, Chhattisgarh; moist deciduous forest | Not stated in the abstract | Total floor fuel 2.2–3.38 Mg/ha, mostly duff/litter and twigs. Net change in fuel load was positive in high/medium fire-frequency zones and negative in low/no-fire zones. |
| **Pande & Meshram 2002**, Trop. Ecol. 43(2):337–344 [ABSTRACT, via AGRIS: https://agris.fao.org/search/fr/records/6472425fe17b74d2224f1a37] | Chhindwara, Satpura plateau, MP; teak forest | Litter traps | Annual leaf fall 2,576 / 2,868 / 4,149 kg/ha; total litterfall 3,276 / 3,305 / 4,536 kg/ha (the highest site was defoliated by *Hyblaea*). Peak fall Jan–Mar. Leaves were 79–91% of litter. |
| **Mondal & Sukumar 2014**, Curr. Sci. 107(9):1590–1594 [FULL] https://www.currentscience.ac.in/Volumes/107/09/1590.pdf | Mudumalai (teak litter) and BRT (*Anogeissus*), southern India; roadside controlled burns, 9 Feb–12 Mar 2010 | 135 points, each a 1×1 m quadrat harvested next to a fire-temperature sensor | Fuel ranged **63 to 1,081 g/m² (0.6–10.8 t/ha)** between points. 81% of points were more than half litter. Fuel moisture 0.5–86% (75% of points ≤17%). Fire temperature correlated with fuel load at r = 0.35. |
| Mondal & Sukumar 2016, PLoS ONE (PMC4956259) [ABSTRACT/SECONDARY] | Mudumalai | Rainfall of the previous wet season used as a proxy for fuel | No fuel measurements. |
| Kodandapani et al. 2013, Fire Ecology 9(2):102, doi:10.4996/fireecology.0902102 [SECONDARY: search summary of the table; Springer blocked] | Nilgiri and Sathyamangalam landscapes | 0.5 ha belt transects | Total fuels in dry deciduous forest 21.3 vs 12.3 Mg/ha; mostly 100-h and 1000-h wood. Litter values were not retrieved. Nilgiri fire rotation 7.1 yr. |
| Kodandapani, Cochrane & Sukumar 2008, For. Ecol. Manage. 256:607 | Western Ghats | Not retrieved | No fuel numbers retrieved. |

**Not found:** Thakur 2022 (Achanakmar), Verma & Jayakumar, Saha & Howe 2003 (seen only as a citation), and any measured fuel load study from Satpura, Pench, Kanha, Panna, Melghat, Tadoba or Bandipur.

**Synthesis for a pixel value**
- **Pre-fire-season litter load** in central Indian dry deciduous and teak forest is about **2.3–4.5 t/ha in March–April**, with a central value of about 3.5 t/ha (Saha; Jhariya; Kittur).
- **Annual leaf litterfall** is 2.6–5.3 t/ha/yr. Total litterfall is 3.3–7.6 t/ha/yr.
- **Carry-over between years is close to zero.** Monsoon decomposition clears the floor (Saha 2002; k ≈ 0.7 per year in Jhariya). The fuel bed is therefore essentially *this year's leaf fall minus dry-season decay minus anything already burned*.
- **Repeated burning** lowers both standing fuel (−42%) and litterfall (−37%) (Jhariya 2017). Fire date matters: a March fire leaves only the roughly 25% of leaves that have not yet fallen (Saha 2002).
- **Point-to-point variability** is large:
  - 0.6–10.8 t/ha across 135 one-m² quadrats (Mondal & Sukumar).
  - CV 54% across 15 quadrats of 0.25 m² in a teak plantation (Ramos-Rodríguez et al. 2026, Q5).
  - CV 2001-Feb ≈ 68% (Saha Table 2: SE 19.9 → SD ≈ 63 on a mean of 93). The other months imply 10–17%, but those are means of biweekly samples.
  - Keane et al. 2012 (Q3) found litter+duff CV of 45–89% at 1 m² across six US sites.
- **Realistic uncertainty:** a point value carries ±50–70% (1σ). A well-modelled stand mean (1 ha or more) carries perhaps ±25–40%, which is my judgement and not a published validation.

---

## Q3. How good can a satellite-only surface fuel map be?

**(a) Fuel classifications and LANDFIRE**

*Keane, Herynk, Toney, Urbanski, Lutes & Ottmar 2013*, For. Ecol. Manage. 305:248–263 [FULL]. https://www.fs.usda.gov/rm/pubs_other/rmrs_2013_keane_r003.pdf
- They used n = 13,138 FIA plots. Most fuel components in all three classifications had **R² < 0.30**.
- LANDFIRE FLM map class agreement with plot-keyed class was **25% (Khat 0.098)**. FCCS was 34% (Khat 0.33) and FTG was 64% (Khat 0.54); the authors say the last two "reflect the accuracy of the vegetation layers rather than the fuel maps".
- Mapped versus measured loadings: **R² < 0.1** for FLM, with slopes below 0.24.
- Litter bias was above 148% of the mean, and RMSE was above 0.5 kg/m² (Sec. 3.1–3.2; Tables 4, 6, 7).
- The authors say accuracies "will always be low unless they are applied at the finest scale of variability (probably 1–5 m patch sizes)" (p. 256).
- Earlier map evaluations they cite: Anderson fuel model maps were 10–44% accurate (Keane et al. 1998). Brandis & Jacobson (2003) got R² 0.01–0.79 with Landsat.

*Keane, Gray & Bacciu 2012*, RMRS-RP-98 [FULL]. https://www.fs.usda.gov/rm/pubs/rmrs_rp098.pdf
- Fuel loading CV is "two to three times the mean".
- Table 7: litter+duff CV 45–89% across sites.
- **Table 12: litter+duff semivariogram range 0.45–2.54 m.** Fine fuels vary at 1–5 m, coarse fuels at 10–150 m and canopy fuels at 100–500 m.
- Litter+duff Moran's I was ≤0.22, meaning weak spatial structure.

**(b) Remote sensing of litter and surface fuel**

*Labenski et al. 2023*, Remote Sens. Environ. 295:113711 [FULL]. https://research.fs.usda.gov/download/treesearch/66562.pdf
- Setup: 119 plots of 176.6 m² each, very dense airborne lidar plus Sentinel-2, random forest.
- **Litter load R² = 0.27, RMSE 2.57 t/ha. Using the forest-type average instead gave RMSE 2.83 t/ha**, so remote sensing improved on it by only 9% (Tables 6, 7).
- Dead 1-h fuels: R² 0.41.
- Litter predictions came from canopy proxies (lidar height p10, early-spring NDVI), not from seeing the floor.
- The authors say similar accuracy "could be obtained using average values based on forest type". Fire behaviour was most sensitive to errors in litter and shrub loads.
- Their Table 1 reviews other studies; variance explained is usually 12–57% for surface fuels from Landsat or Sentinel-2:
  - Reich 2004 (Landsat): 34–45%.
  - Arellano-Pérez 2018 (Sentinel-2, total surface fuel): 12%.
  - Jin & Chen 2012: 5–57%.
  - Duff 2013: 30–51%.
  - Bright 2017 (lidar + Landsat time series): 24–32%.
  - Franke 2018 (Cerrado, open savanna, non-photosynthetic-vegetation fraction): 86%.

*Bright et al. 2017*, Forests 8:322 [PARTIAL; search summary of full text]: surface fuels R² 0.16–0.32 with lidar + Landsat time series, 119 plots.

*Chávez-Durán et al. 2024*, Fire 7(11):408 [ABSTRACT via DOAJ/UAH repository]: UAV multispectral data, litter R² 0.32, RMSE 0.53 Mg/ha.

*Gale, Cary, van Dijk & Yebra 2021*, Remote Sens. Environ. 255:112282 [ABSTRACT]: the literature is weighted toward overstorey, and surface fuels get little attention.

Arroyo et al. 2008 and Chuvieco et al. 2020: **not accessed.**

**(c) The canopy problem**
- Optical and lidar sensors see the canopy, not the litter. In closed stands, litter maps work only through canopy-to-litterfall proxies (Labenski 2023; Keane 2013).
- Teak forest helps here. In the dry season, from Feb to May, the canopy is largely leafless, so Sentinel-2 SWIR can see part of the floor. Measures of dry non-photosynthetic material in SWIR, such as non-photosynthetic vegetation cover fractions, worked in open Cerrado (86%, Franke 2018 as cited in Labenski).
- Even then, cover fraction is not load: about 3 t/ha versus 6 t/ha of teak leaves can both look like 100% litter cover.

**Spatial grain**
- Fine fuel varies at 0.5–5 m.
- Above about 10–30 m, what can be predicted is the stand-level mean, set by species, canopy, fire history and topography. Below that, the variation is unstructured noise.
- A 10 m pixel averages out most microscale noise. Assuming a ~1–2 m autocorrelation range, the pixel-mean CV falls to roughly 6–12%; this is my derivation, not published. Most real pixel-to-pixel signal at 10 m therefore comes from stand drivers that change over tens to hundreds of metres.

---

## Q4. Inferring fuel from fire radiative energy or fire behaviour

**Fire radiative energy coefficients**
- Wooster, Roberts, Perry & Kaufman 2005 (JGR 110, D24311): **0.368 ± 0.015 kg/MJ**, from laboratory *Miscanthus* burns. Verified as quoted in Freeborn et al. 2008.
- Freeborn et al. 2008, JGR 113, D01301 [FULL] https://research.fs.usda.gov/download/treesearch/32776.pdf: 44 lab fires gave a slope of **0.453 ± 0.068 kg/MJ** (95% CI), r² = 0.88. FRE per kg consumed was 1.29–4.18 MJ/kg, which is 12 ± 3% of the higher heating value. So the coefficient itself is uncertain by about ±20–25% between studies, before any satellite errors.

**Satellite biases**
- Freeborn, Wooster & Roberts 2011 (RSE 115) [ABSTRACT]: MODIS-based FRE was 0.72 times SEVIRI FRE corrected for low-resolution detection bias, which is about a 28% low bias, linked to the MODIS bow-tie effect and summing method. With 2–4 polar overpasses a day, FRE must be integrated over an assumed diurnal cycle.
- Roberts et al. 2018, RSE 217:158–171 [FULL abstract, author's accepted manuscript] https://kclpure.kcl.ac.uk/ws/files/101481820/Investigating_the_impact_of_ROBERTS_Accepted13August2018_GREEN_AAM.pdf: the canopy intercepts surface-fire FRP. Interception is **6% at 5% cover and LAI <1, up to 92% at 95% cover and LAI ~8**. Correcting with MODIS LAI and tree cover raised annual African FRE by 15%. Leafless teak in March–April is close to the low-interception case.
- Small, low-intensity litter fires are often below detection. At about 3.5 t/ha consumed, the energy density is roughly 0.35 kg/m² ÷ 0.368 kg/MJ ≈ 1 MJ/m², and a 0.5 m/min front takes hours to cross a 375 m VIIRS pixel.
- The Kumar/Roy paper the brief named was not found.

**Conclusion on FRE:** it can give fuel *consumed*, aggregated over burned areas of km² size, with errors of about a factor of 2. It cannot give pre-fire load at 10 m.

**Fire-spread data assimilation**
- Rochoux et al. 2014, NHESS 14:2951–2973 [FULL] https://nhess.copernicus.org/articles/14/2951/2014/: they estimated spatially uniform wind and fuel parameters (moisture Mv, surface-to-volume ratio σv) with an ensemble Kalman filter. In one experiment they rewrote Rothermel as ROS = P·δv, "tak[ing] advantage of the proportionality between the ROS and the fuel layer thickness". The single coefficient P "encompasses different uncertainties that are not distinguished". This shows directly that load or depth is not separately identifiable from front positions.
- Zhang, Collin, Moireau, Trouvé & Rochoux 2019 (Fire Safety J. 105:286–299, RxCADRE S5) [ABSTRACT]: the parameter step estimated **wind**, not fuel.

**Rothermel (1972) algebra (my derivation from the standard equations)**
- The spread equation is R = I_R·ξ·(1+φw+φs)/(ρb·ε·Q_ig), with I_R = Γ′·w_n·h·η_M·η_s and ρb = w0/δ.
- Substituting gives R = δ·[Γ′(1−S_T)h·η_M·η_s·ξ(1+φw+φs)/(ε·Q_ig)]. Here Γ′, ξ and φw depend only on the packing ratio β and σ.
- **So at fixed bulk density, ROS is proportional to load** (because ROS ∝ depth), and load multiplies the moisture damping η_M and the wind and slope factor.
- From ROS alone, load is confounded with moisture, wind and bulk density. Varying load at fixed depth changes β and gives a non-monotonic response around the optimum β.
- Byram's intensity I = H·w·r. Flame length plus ROS can recover *consumed* load if the heat content H is known.

**Field evidence that ROS does not reveal load**
- Ramos-Rodríguez et al. 2026 (teak, Q5): fuel dry weight vs ROS r = −0.05 (p = 0.85). Fuel dry weight vs fireline intensity r = 0.80 and vs heat per unit area r = 0.975 (Table 5).
- This matches the Rothermel algebra: at near-zero wind, depth (r = 0.37, ns) and moisture (r = 0.53) mattered more for spread than load.

---

## Q5. Measured litter-fire behaviour in teak and Asian dry forests

**Ramos-Rodríguez et al. 2026**, Rev. For. Mesoam. Kurú 23(52):50–63, doi:10.18845/rfmk.v23i52.8442 [FULL] https://revistas.tec.ac.cr/index.php/kuru/article/view/8442
- Setup: teak plantation in Manabí, Ecuador; 15 plots of 2×10 m burned with the wind; one 50×50 cm load sample per plot.
- **Table 2 (fuel and weather):**
  - Load 0.56–2.31 kg/m², mean **1.10 ± 0.59 kg/m² (11 t/ha, CV 54%)**. This is much heavier than central Indian floors; it is a plantation.
  - Fuel depth 7.7–21.7 cm.
  - Fuel moisture 7.4–19.7%.
  - Wind about 0.06 m/s.
  - RH 51–64%.
- **Table 3 (fire behaviour):**
  - ROS 0.0045–0.0119 m/s (**0.27–0.71 m/min**, mean 0.48).
  - Flame height 0.35–0.70 m.
  - Fireline intensity **51–421 kW/m** (mean 130).
  - Heat per unit area 1,937–8,453 kcal/m².

**Saha 2002 (Gadchiroli)**
- Measured: flame height 0.55–0.60 m. A 9 m² plot burned in about 10–13 min.
- Derived by me: about 0.25–0.3 m/min. Byram's flame-length relation gives **about 70–85 kW/m**.

**Thai Forest Fire Control Division** [SECONDARY, page blocked; via search summary] https://www.dnp.go.th/forestfire/Eng/description.htm
- Dry dipterocarp fuel 4–5 t/ha; mixed deciduous about 5 t/ha.
- Spread about 2–4 m/min in "fair" conditions.

**Wanthongchai (APN report)** [SECONDARY]: about 166 kW/m in deciduous forest at Doi Suthep-Pui.

**Not found:** field measurements of ROS in sal forest or in Kerala teak.

---

## Q6. Existing fuel-load products covering India

| Product | Resolution | Content | Use as a check |
|---|---|---|---|
| FSI Surface Fuel Load 2023-24 | Strata built from 1:50k type map, LISS-III-based density map (23.5 m) and 30 m slope; district tables | 4 classes, g/ft² | Only India-specific product. No validation, no published per-stratum values. Ratapani districts are about 97% "Low". Could be obtained from FSI. |
| McNorton & Di Giuseppe 2024, Biogeosciences 21:279–300 [FULL text downloaded, read in part]; CDS/EWDS "derived-fire-fuel-biomass" https://ewds.climate.copernicus.eu/datasets/derived-fire-fuel-biomass | **~9 km, daily**, 2003– (paper covers 2010–2019) | Live/dead × foliage/wood loads, built from ESA-CCI biomass plus modelled seasonality | Gives a regional-scale seasonal envelope only. Not usable at 10 m. |
| Pettinari & Chuvieco 2016, Biogeosciences 13:2061–2076 [PARTIAL]; PANGAEA doi:10.1594/PANGAEA.849808 | GlobCover ~300 m base, compared at 0.5° | 274 FCCS fuelbeds with generic loadings | Generic tropical fuelbed loadings. Weak. |
| GFED5 / van Wees et al. 2022 (500 m fuel consumption) [SECONDARY] | 500 m | Modelled litter and fuel pools via CASA | Gives an order-of-magnitude check on consumption. |
| NRSC/ISRO | none found | Fire alerts and burned area only | None. |

---

## Q7. Credible high-resolution approaches without plots, and minimum field effort

**Process (Olson-type) model.** This is the most defensible approach for this system, because carry-over is about zero.
- Model: L(t) = Σ leaf fall since leaf flush × e^(−k·Δt) during the dry season, reset to near zero at each fire and at monsoon decay.
- Inputs that can be had without plots:
  - Leaf-fall amount, scaled by canopy and teak share (Pande & Meshram; Jhariya: 2.6–5.3 t/ha/yr leaf).
  - Leaf-fall timing from the Sentinel-2 NDVI/NDMI decline (>75% fallen by late March per Saha).
  - Time and date of last fire from Sentinel-2/Landsat burned-area history and VIIRS.
  - A dry-season k value (litter turnover ≈0.7/yr overall; most decay happens in the monsoon).
- Brandis & Jacobson 2003 (IJWF 12:185) [ABSTRACT]: a canopy-turnover-to-litter "biomass method" reproduced field litter. A vegetation-class plus fire-history method overestimated.
- The Olson negative-exponential model is the operational standard in Australia [SECONDARY].

**Classification approaches** (forest-type lookup, like FSI): Labenski 2023 shows a forest-type average is nearly as accurate as RF on lidar + Sentinel-2 for litter.

**Minimum field effort, if any becomes possible**
- Sikkink & Keane 2008 (IJWF 17:363–379) [ABSTRACT]: planar intersect ranked best for woody fuels and needed about 1.5 km of transect. Photoload was close.
- Keane & Gray 2013 [ABSTRACT]: photoload is poor at high loads, and a fixed-area microplot was slightly more accurate.
- **For litter, harvest quadrats (0.25–1 m²) are the standard** (Saha; Jhariya; Mondal & Sukumar).
- Sample size n = (t·CV/E)². With CV ≈ 60%:
  - ±20% at 95% confidence needs about **36 quadrats per stratum**.
  - ±30% needs about 16.
  - ±10% needs about 144.
- Taking 4–5 quadrats per site at 8–10 sites per stratum also captures between-site variance.
- A depth × bulk-density shortcut (13-point depth, as in FIREMON) can multiply sample numbers cheaply once bulk density is calibrated.

---

## So what for a 10 m Ratapani map

**1. Realistic accuracy**
- No study anywhere has shown pixel-level litter load prediction better than R² ≈ 0.3–0.4 from satellite data, even with dense lidar and plots. Without plots, it cannot be validated at all.
- An honest product states the stand or stratum mean (about 3–4.5 t/ha pre-fire in unburnt teak/mixed dry deciduous forest; about 2–2.5 t/ha in annually burnt stands) with **±40–60% (1σ) uncertainty**.

**2. Appropriate grain**
- Compute at 10 m to follow Sentinel-2 phenology and burn scars, but **interpret and report at ≥1 ha or per stand/compartment**.
- Fine-fuel variance below 5 m is noise. The 10 m signal is real only where it reflects fire history (burned / unburned this season), canopy and teak density, and leaf-fall timing.

**3. What can be claimed**
- A relative, dynamic map of *available litter fuel*, driven by litterfall, phenology and time since fire, with literature-based bounds.
- Classes such as burned-this-season, low, moderate and high are defensible.
- Absolute t/ha per pixel is not defensible.
- FSI's map can be cited as the only national product, with its limits stated: lookup table, no validation, "Low" for about 97% of Raisen and Sehore.

**4. What cannot be claimed**
- Validated pixel accuracy.
- Fuel load inferred from FRP (it gives consumption, at km scale, ±factor 2).
- Load inverted from spread rate (not identifiable from wind, moisture or bulk density).
- Grass load from optical data under trees.

**5. Ranked steps, most credible first**
1. Build a Sentinel-2 / Landsat / VIIRS **burn history** (date of last fire per pixel, every year). This is the strongest single fuel driver here: an annual fire reset with near-zero carry-over.
2. Build a **litterfall × phenology model**:
   - Leaf-fall date and fraction from the dry-season NDVI/NDMI decline.
   - Annual leaf fall scaled by canopy cover and teak share (FSI forest type/density maps, Sentinel-2 classification).
   - Bounds from the literature (2.6–5.3 t/ha/yr; pre-fire floor 2.3–4.5 t/ha).
   - Monte Carlo propagation of parameter ranges to give per-pixel uncertainty.
3. Add **dry-season floor exposure** (SWIR non-photosynthetic cover) as a check on litter presence, and separately on cured grass in openings. Treat it as an index, not as t/ha.
4. Cross-check against FSI district classes, the CAMS/ECMWF 9 km dead foliage load and GFED 500 m consumption. Report any disagreement openly.
5. Consistency check with fire behaviour: where VIIRS fires occur, compare implied intensity and consumption with the modelled fuel (FRE × 0.37–0.45 kg/MJ, with the canopy-interception caveat). Use this only as a sanity check.
6. Whenever field access opens: about 36 litter quadrats of 0.25 m² per major stratum (burnt vs unburnt × teak-dominant vs mixed), taken in late March–April, plus depth readings. This alone would turn the map from a model-based estimate into a validated one.

---

## Sources (URLs read or attempted)

- [FSI Surface Fuel Load Mapping 2023-24](https://fsiforestfire.gov.in/libraries/assets/documents/Surface%20Fuel%20Load%20Mapping.pdf)
- [FSI Forest Fire Risk Zonation 2023-24](https://fsiforestfire.gov.in/libraries/assets/documents/Forest%20Fire%20Risk%20Zone%20Mapping.pdf)
- [FSI publications page](https://fsiforestfire.gov.in/Home/Publication)
- [Keane et al. 2013 FEM](https://www.fs.usda.gov/rm/pubs_other/rmrs_2013_keane_r003.pdf)
- [Keane, Gray & Bacciu 2012 RMRS-RP-98](https://www.fs.usda.gov/rm/pubs/rmrs_rp098.pdf)
- [Labenski et al. 2023 RSE](https://research.fs.usda.gov/download/treesearch/66562.pdf)
- [Bright et al. 2017](https://www.fs.usda.gov/rm/pubs_journals/2017/rmrs_2017_bright_c001.pdf)
- [Saha 2002 Curr Sci](https://www.currentscience.ac.in/Volumes/82/09/1144.pdf)
- [Mondal & Sukumar 2014 Curr Sci](https://www.currentscience.ac.in/Volumes/107/09/1590.pdf)
- [Jhariya 2017 JFES](https://www.koreascience.or.kr/article/JAKO201706749669484.page)
- [Kittur et al. 2014](https://journal.hep.com.cn/jfr/EN/10.1007/s11676-014-0471-0)
- [Pande & Meshram 2002 (AGRIS)](https://agris.fao.org/search/fr/records/6472425fe17b74d2224f1a37)
- [Kodandapani et al. 2013 Fire Ecology](https://fireecology.springeropen.com/articles/10.4996/fireecology.0902102)
- [Freeborn et al. 2008 JGR](https://research.fs.usda.gov/download/treesearch/32776.pdf)
- [Freeborn et al. 2011 abstract](https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=03761)
- [Roberts et al. 2018 RSE](https://kclpure.kcl.ac.uk/ws/files/101481820/Investigating_the_impact_of_ROBERTS_Accepted13August2018_GREEN_AAM.pdf)
- [Rochoux et al. 2014 NHESS](https://nhess.copernicus.org/articles/14/2951/2014/)
- [Zhang et al. 2019](https://researchportal.ip-paris.fr/fr/publications/state-parameter-estimation-approach-for-data-driven-wildland-fire/)
- [Ramos-Rodríguez et al. 2026 Kurú](https://revistas.tec.ac.cr/index.php/kuru/article/view/8442)
- [McNorton & Di Giuseppe 2024](https://bg.copernicus.org/articles/21/279/2024/)
- [CDS fuel dataset](https://ewds.climate.copernicus.eu/datasets/derived-fire-fuel-biomass)
- [Pettinari & Chuvieco 2016](https://bg.copernicus.org/articles/13/2061/2016/)
- [Chávez-Durán et al. 2024 (repository)](https://ebuah.uah.es/dspace/handle/10017/67640)
- [Gale et al. 2021 (ANU)](https://researchportalplus.anu.edu.au/en/publications/forest-fire-fuel-through-the-lens-of-remote-sensing-review-of-app/)
- [Brandis & Jacobson 2003](https://publish.csiro.au/wf/WF03032)
- [Sikkink & Keane 2008](https://research.fs.usda.gov/treesearch/30826)
- [Keane & Gray 2013](https://research.fs.usda.gov/treesearch/46777)
- [Thai DNP fire page](https://www.dnp.go.th/forestfire/Eng/description.htm)
