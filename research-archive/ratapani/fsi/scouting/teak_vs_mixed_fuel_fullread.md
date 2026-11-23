# Teak-dominated vs other dry deciduous forest: fuels, fire, and how to map them (full-read pass, 14 Oct 2026)

Scope: (A) how fuels and fire differ between teak (*Tectona grandis*) stands and other or mixed dry deciduous stands; (B) how to separate teak-dominated from other dry deciduous forest by remote sensing, and which labels exist for Ratapani.

Reading status for each source: **FULL** (whole text and tables read), **PARTIAL** (some sections or tables only), **ABSTRACT** (abstract or search snippet only; numbers not checked against tables). Items marked **[inference]** are my reasoning, not the paper's.

Many publishers blocked this session: Springer/BMC, Elsevier/Cell (including OA Heliyon), MDPI, Wiley, Taylor & Francis, Cambridge, ResearchGate, JTFS (FRIM), and the Cloudflare-protected Indonesian journals. Consensus and OpenAlex had run out of quota. Overpass (OSM) and the IIRS BIS portal did not respond. Where a key paper was blocked, I say so.

New data and code from this pass:
- `data/vtm_roy2015_ratapani_5kmbuf.tif`: Roy et al. 2015 vegetation type map, clipped to the AOI plus 5 km. 60 m, EPSG:32643; class names are in the Zenodo `VegAttributes.csv`.
- `data/vtm_roy2015_grid500m.csv`: class fractions and the majority class for each of the 3,614 cells in `grid_500m.geojson`.
- `data/sdpt_v2_tile_z8_183_110-111.geojson`: WRI SDPT v2 polygons decoded from the public GFW vector tiles (z8), covering 21.9–23.2 N, 75.9–78.8 E.
- `code/teak_labels/`: `vtm_clip.py`, `vtm_grid.py`, `sdpt_tiles.py`, `fire_by_vtm.py`.

---

## Summary

**A. Fuels and fire.** No study I could read compares teak and mixed dry deciduous fuels side by side in central India with flammability tests. The evidence is indirect but points one way.

1. **Leaf fall in teak is later and more concentrated.**
   - Teak drops most of its leaves in January–March, peaking in February–March. In an 18-yr plantation in Tamil Nadu, 80% of the 9.2 t/ha/yr of leaf fall came in January–June; the February peak was 1,703 kg/ha.
   - Satpura natural teak peaks in January and March, with leaf making up 79–91% of litterfall.
   - Mixed dry deciduous stands in central India (Bhoramdeo, Achanakmar) peak in November–December.
   - Early-shedding associates (*Boswellia*, *Lannea*) are bare by October–January. *Anogeissus* and *Diospyros* hold their leaves longest.
2. **Teak litter is bulkier per leaf and makes a loose, deep bed.**
   - Teak leaves are about 30 × 20 cm, and up to 1 m on young shoots.
   - In a teak plantation burn study (Ecuador, FULL), the bed averaged 1.10 kg/m² (11 t/ha) at 13.6 cm depth. That works out to a bulk density of about 8 kg/m³ **[inference]**. Dead-fuel moisture was 12.4%.
   - Those burns gave 0.46 m flames, a spread rate of 0.48 m/min and 130 kW/m with near-zero wind.
3. **Teak leaf litter barely decays in the dry season.** In Gujarat teak, litterbags lost only 10.6% from April to June and 67.6% in a year. The paper states k = 1.31/yr, but its own table implies about 1.13/yr.
4. **Annual litterfall: teak is equal to or slightly above mixed forest.**
   - Achanakmar (FULL, other note): teak plantation 0.61 Mg/ha/month against 0.52–0.59 for mixed types; turnover K 0.62 against 0.50–0.59.
   - Satpura natural teak (ABSTRACT): 3.3–4.5 t/ha/yr.
5. **Flammability tests that separate teak leaves from other species: none found.**
   - The only Indian lab study of teak fuel (Behera et al. 2023, Odisha) was blocked by the publisher. Search snippets give teak *wood* values only: heating value 19.93 MJ/kg, volatile matter 81.9%.
   - Thai mixed deciduous forest (teak, *Lagerstroemia*, *Terminalia*, *Xylia*, bamboo; FULL) gives fire behaviour for the forest type, not for teak alone: dead leaf + grass 2.36 t/ha, head-fire spread 0.51–2.55 m/min, flame length 1.10 m, 166 kW/m. Leaf+grass moisture fell from 14% in January to about 6% in February–May.
6. **Fire frequency in Ratapani (our own data):** cells mapped as teak-mixed burn less often than cells mapped as other dry deciduous.
   - Using the Roy 2015 map on our 500 m grid with labels_v3 scar seasons 2017–2026: teak-mixed cells burned in 52% of seasons, against 62% for "dry deciduous" (non-teak) cells.
   - VIIRS detections per cell: 2.2 against 2.9.
   - Teak-mixed cells were lower in all 13 location strata (mean difference −0.12). Median first-burn day is similar (day 75 against day 72, mid-March).
7. **FSI fuel tables do not separate teak from mixed forest.** Their strata are forest-type *group* × canopy density × slope, and group 5 covers all tropical dry deciduous forest.

**B. Mapping teak.**
- **Best label source: Roy et al. 2015 vegetation type map.** It is on Zenodo (CC-BY 4.0, 60 m raster, record 11615011) and I downloaded and clipped it.
  - Ratapani AOI: "Teak mixed moist deciduous" 46,268 ha (57%), "Dry deciduous" 14,432 ha (18%), "Degraded forest" 10%, "Moist deciduous" 8%, agriculture 6%.
  - These are 1:50k on-screen polygons from about 2005–2010, so treat them as weak labels.
- **WRI SDPT v2 has no teak inside Ratapani.** India's layer is just Roy's plantation classes. The nearest SDPT teak polygons are 33–34 km south of the boundary (a 39,342 ha polygon at 22.46 N 77.68 E, and a 9,561 ha one).
- **Best features (central India evidence):**
  - Panna TR (FULL preprint): Sentinel-2 composites for October, December, February and May, random forest. Overall accuracy 88.9%, kappa 0.81; "Dry teak forest" user's accuracy 85.3% and producer's accuracy 90.6%.
  - Top predictors in Panna: red-edge B5 in February, October and December; SWIR B11 in May; B6 in October.
  - Phenology: MP teak flushes 16 May–30 June (78 of 123 clones flush 1–15 June; FULL). Several associates flush before the monsoon in April–May.
  - So the most diagnostic window is **late April to early June**: teak crowns are still bare while *Diospyros*, *Madhuca*, *Terminalia* and *Butea* are flushing. February–March red-edge picks up the timing of teak leaf fall.

---

# A. Fuel differences, teak vs mixed

## A1. Thakur et al. 2022, Achanakmar-Amarkantak BR (Chhattisgarh): teak plantation vs sal-mixed, dense mixed and open mixed. **FULL (read by the fuel-load session; numbers taken from `fuel_load_values_fullread.md` §4, not re-read here)**
- **Litterfall, mean monthly:**
  - Teak plantation (TP) 0.61 Mg/ha
  - Open mixed (OMF) 0.59
  - Sal mixed (SMF) 0.59
  - Dense mixed (DMF) 0.52
  - Site mean 4.19 Mg/ha/yr. Leaves are about 64% of litterfall.
- **Timing (all types pooled):** peak in November, lowest in June, secondary peak in April–May.
- **Turnover K (Table 4):** TP 0.62, SMF 0.59, DMF 0.58, OMF 0.50.
- **Stand structure (Table 1):**
  - TP: canopy 65%, LAI 3.65, 470 trees/ha
  - DMF: canopy 80%, LAI 5.5
  - OMF: canopy 35%, LAI 2.85
- **What it means for us.** This is the only side-by-side teak vs mixed litter comparison in central India. Teak litterfall is 3–17% higher per month and turns over slightly faster. Annual totals do not justify a large teak multiplier; use about 1.05–1.15 × mixed **[inference]**. The bigger difference is timing (see A2–A4).

## A2. Pande, Meshram & Banerjee 2002, *Trop. Ecol.* 43:337–344, Satpura plateau teak (Chhindwara, MP). **ABSTRACT** (AGRIS record; full text not online)
- **Leaf fall:** 2,868 / 4,149 / 2,576 kg/ha/yr at sites I / II / III.
- **Total litterfall:** 3,305 / 4,536 / 3,276 kg/ha/yr.
- Leaf is 79–91% of litterfall.
- Peaks are in **January and March** at all sites.
- Site II was defoliated by *Hyblaea puera* and *Eutectona machaeralis*, which caused a September drop and a bimodal pattern.
- https://agris.fao.org/search/fr/records/6472425fe17b74d2224f1a37
- **What it means for us.** Natural teak in MP gives 2.6–4.1 t/ha/yr of leaf, almost all of it falling in January–March, the build-up period before the fire season. In defoliator years some leaf comes down in September and decays over the winter, which lowers the March floor **[inference]**.

## A3. Tamil Nadu (Mettupalayam) 18-yr teak plantation litterfall, *Plant Science Today* 2025, doi 10.14719/pst.7329. **FULL**
https://horizonepublishing.com/index.php/PST/article/download/7329/6613
- **Site and design:** 4 × 2 m spacing (1,250 stems/ha), 900 mm rain (80% from the NE monsoon), 1 m² traps sampled monthly.
- **Totals:** total litterfall 11,255 kg/ha/yr. Leaves 81.9%, twigs 6.5%, fruits 6.3%, flowers 5.3%. Annual leaf litter 9,216 kg/ha.
- **Leaf fall by month (Table 1):** ranged from 93 kg/ha in October to **1,703 kg/ha in February**. February and March were the highest; January 1,014, April 953, May 938, June 1,020. About 80% of leaf fall came in January–June.
- **Total litterfall by month:** highest in March (2,040 kg/ha), then February (1,780).
- **Twig fall:** peaked in March (183 kg/ha). None in August–October or January–February.
- **What it means for us.** This is a dense, young plantation, so the annual total (11 t/ha) is an upper bound and not representative of Ratapani's natural teak. The *shape* is the useful part: teak leaf fall is spread from January to June with a February–March peak, so standing teak litter keeps growing through the whole fire season. In mixed stands most leaf is already down by January **[inference]**.

## A4. Jhariya 2017 (Bhoramdeo, mixed dry deciduous with teak) and Kittur et al. 2014 (Chhattisgarh moist deciduous). **FULL / ABSTRACT** (read by the fuel-load session)
- **Bhoramdeo:**
  - Litterfall 4.75–7.56 t/ha/yr, peaking in **December** (November–March).
  - Forest floor in summer 2.30–3.95 t/ha; turnover K 0.70–0.74.
  - Fire cut litterfall by 11.5% / 24.4% / 37.2% in low / medium / high fire zones.
- **Kittur 2014:** forest floor 2.2–3.38 Mg/ha (abstract only; doi 10.1007/s11676-014-0471-0, still paywalled).
- **What it means for us.** Mixed stands peak about two months earlier than teak (December against February–March). Fire cuts litterfall, so frequently burnt cells carry less fuel.

## A5. Jana 2025, teak leaf litter decomposition, Dang forest, Gujarat (*IJSR* 14(6):1699). **FULL**
https://www.ijsr.net/archive/v14i6/SR25621170241.pdf
- **Design:** freshly fallen teak leaves collected in April 2007; nylon bags on the forest floor, April 2007 to March 2008. Rain about 1,999 mm; stand dominated by teak, *Terminalia tomentosa* and *Dalbergia latifolia*.
- **Table 1, mass remaining (of 50 g):** May 47.5, June 44.7, July 42.6, August 34.5, September 29.4, … April 2008 16.2 g. That is 10.6% lost by end of June and 67.6% lost after one year.
- **Table 2:** k = 1.31/yr, turnover time 323 days, t50 = 224 days, t95 = 2.65 yr.
- **Check:** −ln(16.2/50) = **1.13/yr**, so the stated 1.31 does not match the table, and the text also gives 0.88 in one place.
- **Comparison values quoted in the paper:** teak plantation k = 2.97 and savanna k = 2.74 (Singh 1978); Gir dry deciduous k = 0.92 (Subrahmanyam 1997).
- **What it means for us.** Teak leaves that fall in February–April lose only about 5–11% of their mass before the monsoon. This gives teak plots near-zero in-season decay. A carry-over of about 30% of last year's leaf into the next dry season is reasonable at 1,000–2,000 mm rain (k ≈ 1.1–1.3), and smaller in annually burnt cells **[inference]**.

## A6. Teak leaf morphology. Orwa et al., Agroforestree Database, *Tectona grandis* factsheet. **FULL** (6-page factsheet)
https://apps.worldagroforestry.org/treedb/AFTPDFS/Tectona_grandis.PDF
- Leaves are "very large … about 30 × 20 cm but young leaves up to 1 m long". They are "shed for 3–4 months during the later half of the dry season".
- Flowers are in large terminal panicles about 45 cm long, at the top of the crown, during the rainy season. In Thailand teak flowers June–September and fruits November–January.
- Natural stands are "often covered with bamboo"; teak "generally occurs scattered but can form almost pure stands".
- **Trait gaps:** I found no SLA, thickness or surface-area-to-volume figures for teak *litter* that I could read. Chaturvedi & Raghubanshi 2018 (*Int. J. Hydrology* 2:00112, **FULL**) measured leaf area and SLA for *Buchanania*, *Diospyros*, *Lagerstroemia* and *Terminalia tomentosa* in the Vindhyan region, but not teak.
  - Their SLA–soil moisture fits (Fig. 2): *Buchanania* 63.3 + 2.66·SMC, *Diospyros* 60.6 + 4.36·SMC, *Lagerstroemia* 120 + 5.11·SMC (cm²/g, SMC in % by volume).
  - *Terminalia tomentosa* had the largest leaves and *Diospyros* the smallest.
- **What it means for us [inference].** A teak leaf has 10–30× the area of a *Diospyros* or *Anogeissus* leaf. Dry teak leaves curl and stack loosely, so the bed is deep and porous (see A7 for 8 kg/m³). Loose beds of big curled leaves dry fast and ventilate well. Expect quick drying after rain (short time-lag), high spread for the load, and flaming that dies quickly. This matches the "big curled leaf" class in global litter-flammability work (Grootemaat et al.; Burton et al. 2021 *J. Ecol.*, not read here). Treat teak litter as **lower bulk density and deeper** than mixed small-leaf litter, for example 8–15 kg/m³ for teak against roughly 20–40 kg/m³ for small-leaf mixed litter. The mixed figure is a guess, unmeasured in central India; Gaikwad & Kumar 2024 used 25–75 kg/m³ beds of Indian broadleaf litter in the lab.

## A7. Ramos-Rodríguez et al. 2026, controlled burns in a teak plantation, Manabí, Ecuador (*Rev. For. Mesoam. Kurú* 23(52):50–). **FULL**
https://revistas.tec.ac.cr/index.php/kuru/article/download/8442/8230/30998, doi 10.18845/rfmk.v23i52.8442
- **Design:** 15 plots of 2 × 10 m in one teak plantation; tropical savanna climate (Aw), 700–1,500 mm rain, wind-driven head fires.
- **Fuel (Cuadro 2):**
  - Dry load before burning: mean **1.10 kg/m²** (0.56–2.31).
  - Bed depth: mean **13.57 cm** (7.67–21.67).
  - Moisture: mean **12.41%** (7.43–19.65).
- **Weather:** 29.8–34.7 °C, RH 50.9–64.3%, wind 0.06 m/s.
- **Fire (Cuadro 3):**
  - Flame height 0.46 m (0.35–0.70)
  - Spread 0.0080 m/s, i.e. 0.48 m/min (0.27–0.71 m/min)
  - Intensity 31.06 kcal/m/s (129.9 kW/m; range 51–421 kW/m)
  - Lethal scorch height 4.04 m
  - Heat per unit area 3,906 kcal/m²
- **Correlations:** dry load correlated with intensity (r = 0.804) and heat per area (r = 0.975). Moisture correlated negatively with heat per area (r = −0.593). Weather variables were not significant.
- **Bulk density [inference]:** 1.10 kg/m² ÷ 0.136 m ≈ **8 kg/m³**. Per plot the range is about 4 kg/m³ (plot 3: 0.76 / 0.197) to 17 kg/m³ (plot 10: 2.20 / 0.133).
- **What it means for us.** This is the only measured teak litter-bed depth and load with fire behaviour that I could read in full. It gives a Rothermel-style teak bed of depth about 0.10–0.15 m and very low packing. Load is 11 t/ha here; Ratapani would be lower, about 2–5 t/ha, so depth would be about 3–8 cm **[inference]**. Flames under 0.7 m and spread under 1 m/min in still air agree with Saha 2002's 55–60 cm flames in Gadchiroli.
- Earlier work from the same group (Ecuador, Jipijapa; Revista Cubana de Ciencias Forestales 2018, **ABSTRACT**): total teak plantation fuel was 11.17 t/ha, and prescription windows gave flame lengths of 0.54–0.76 m.

## A8. Junpen et al. 2013, experimental fires in deciduous forest, Doi Suthep-Pui, northern Thailand (*ScienceAsia* 39:535–545). **FULL**
https://www.scienceasia.org/2013.39.n5/scias39_535.pdf
- **Design:** 80 plots, January–May of 2008 and 2009, in mixed deciduous forest (MDF: *Lagerstroemia*, *Terminalia mucronata*, *Tectona grandis*, *Xylia*, *Pterocarpus*, bamboo) and dry dipterocarp forest. The results **do not separate MDF from DDF**.
- **Fuel (Table 2):**
  - Dead leaves + grass (FLG): 2.36 t/ha (1.15–3.38)
  - Twigs + undergrowth: 1.52
  - Overall: 3.88 t/ha
  - FLG is 41–89% of the total
- **Fire (Table 3):**
  - Head fire: 1.37 m/min (0.51–2.55), flame length 1.10 m (0.39–2.03), 166 kW/m (39–380)
  - Back fire: 0.30 m/min
  - Flank fire: 0.46 m/min
- **Combustion efficiency (Table 4):** dead leaves 0.98, grass 0.94, twigs 0.54, undergrowth 0.49, overall 0.80. Heating value used: 18,330 kJ/kg.
- **Moisture of dead leaves + grass by month (Fig. 2):** January 14.0%, February 5.96%, March 6.23%, April and May 6.70%.
- **Models:**
  - ROS = 1.657·exp(0.018·S)·exp(−0.080·M_LG), R² 0.88
  - ROS = 0.251·exp(0.024·S)·exp(0.439·F_LG), R² 0.87 (valid for F_LG 1–4 t/ha)
- **FFCD field-fire table (Table 6):** Kanchanaburi F_LG 3.39 t/ha, observed ROS 2.81 m/min; Chiang Mai 3.46 t/ha, 1.72 m/min.
- **What it means for us.** Teak-bearing deciduous forest at 2–4 t/ha of leaf + grass burns at about 0.5–2.5 m/min with flames of about 1 m. The S and M_LG model is a ready check for our spread thread. Note that 1-hr moisture drops to 6% by February, so the teak floor is fire-ready as soon as leaves are down.

## A9. Chernkhunthod & Hioki 2020 (Doi Suthep MDF; two papers) and Chaiyo & Garivait 2015 (Ratchaburi MDF). **PARTIAL / ABSTRACT**
- **Floristics paper, *J. Jpn. Soc. Reveget. Tech.* 46:202 (FULL):**
  - Thai MDF splits into a *Tectona grandis* type and a *Lagerstroemia calyculata* type (Bunyavejchewin 1983).
  - Quoting Akaakara 2015: MDF fuel 2.5–4.0 t/ha, mainly dry litter and dead grass; spread 2–4 m/min; flames 30–100 cm; 109–119 kW/m.
  - In the high-fire-frequency plot, teak had an IVI of 11.49. Bamboo (*Dendrocalamus membranaceus*) was 360 culms/ha in the low-frequency plot and 200 in the high-frequency plot.
  - https://www.jstage.jst.go.jp/article/jjsrt/46/2/46_202/_pdf
- **Fuel paper, *Landsc. Ecol. Eng.* 16:289, doi 10.1007/s11355-020-00419-6 (ABSTRACT):** litter dominates; fire consumes 60–70% of fuel; fuel recovers in about 2 years.
- **Chaiyo & Garivait 2015 (ABSTRACT):** MDF leaf litter 5.31 ± 1.51 t/ha, of which 3.23 ± 1.87 consumed. Litter mixes tree and bamboo leaves, and bamboo leaf has the lower heating value.
- **What it means for us.** Bamboo-rich mixed stands carry leaf litter of lower heat content. Teak-type MDF is not reported separately anywhere I could read.

## A10. Saharjo & Putra 2017, fire management in KPH Madiun (Perhutani teak, East Java), *J. Silvikultur Tropika* 8(3):183–190. **FULL**
https://journal.ipb.ac.id/index.php/jsilvik/article/download/20691/14219
- KPH Madiun covers 31,219.7 ha, of which 27,483.6 ha is teak.
- 2011–2015: **71 fires burned 104.5 ha**, all surface fires, mostly in teak. Fires peak June–October (the Javan dry season); the fuel is "serasah daun jati dan semak belukar" (teak leaf litter and shrubs).
- 2014 had the most fires; it was also the driest year (387 mm).
- Causes from interviews: land clearing 43%, social conflict 15%.
- **What it means for us.** Perhutani teak landscapes burn often but in small patches: about 1.5 ha per fire, and 0.07%/yr of the teak area. No fuel numbers.

## A11. Behera, Prusty, Behera & Kale 2023, "Characterizing fuel flammability in a tropical dry community forest in Eastern India…", *Tropical Ecology*, doi 10.1007/s42965-023-00309-6. **ABSTRACT / SNIPPET** (Springer blocked)
- Snippet values for teak **wood**: moisture 5.08%, volatile matter 81.91%, heating value 19.93 MJ/kg. Sal, bamboo and grass were also tested.
- **What it means for us.** This is the only Indian lab study I found that includes teak. Fetch the full text by hand; it may hold leaf-litter ignition data.

## A12. Gaikwad & Kumar 2024, *Fire Safety Journal* 144:104106 (cone calorimeter, Indian broadleaf litter vs pine). **ABSTRACT**
- Broadleaf litter ignited earlier and burned longer than pine but with a lower heat release rate; species not named. Beds of 25–75 kg/m³.

## A13. Fire frequency, teak vs mixed, in Ratapani itself (our own data, this pass). **COMPUTED**
Script: `code/teak_labels/fire_by_vtm.py`. Inputs: `data/vtm_roy2015_grid500m.csv`, `labels_v3/labels_v3.parquet` (`pos_main`, seasons 2017–2026), `data/viirs_cells.parquet`.

**By majority Roy-2015 class:**

| Majority class | Cells | Share of seasons burned | Ever burned | VIIRS detections per cell | Median first-burn day |
|---|---|---|---|---|---|
| Teak mixed moist deciduous | 2,081 | 0.520 | 0.960 | 2.16 | 75 |
| Dry deciduous (non-teak) | 577 | 0.623 | 0.981 | 2.88 | 72 |
| Moist deciduous | 267 | 0.615 | 0.970 | 2.62 | 79.5 |
| Degraded forest | 335 | 0.599 | 0.967 | 3.01 | 71 |
| Agriculture | 319 | 0.224 | 0.655 | 0.72 | 85 |

- **Pure cells only (class fraction ≥ 0.8):** teak-mixed 0.519 (n = 1,285), dry deciduous 0.634 (n = 216).
- **By location strata:** I took cells with forest fraction ≥ 0.9 and split them into 5 longitude × 3 latitude strata. Teak-mixed was lower than dry deciduous in **13 of 13** strata, mean difference −0.116.
- **Caveats:** the map polygons are 1:50k and about 15 years old. "Dry deciduous" may mark more open, grassier or more accessible stands, so this is an association, not a fuel effect. I did not control for distance to villages or roads.
- **What it means for us.** Being teak-mixed is a modest negative predictor of burning: about 10 points fewer burned seasons. This is the opposite of a "teak is more flammable" prior. A likely mechanism is that teak stands in Ratapani are more closed and less grassy, and their litter arrives later (February–April), so they become available later than *Boswellia*/*Lannea*/grassy dry deciduous patches **[inference]**. First-burn timing differs by only about 3 days at the median, so the effect is mostly in *whether* a cell burns, not when.

## A14. FSI fuel tables and ICFRE

- FSI's 2024 fuel-load atlas uses 17 forest-type *groups* × 4 canopy classes × 4 slope classes. Group 5, Tropical Dry Deciduous, covers both teak and mixed dry deciduous, so **no teak/mixed split** exists. See `../fuel_load_tables.md`.
- No ICFRE or MP Forest Department table separating teak from mixed fuel turned up.
- ICFRE-TFRI Jabalpur has teak phenology work (A2, B4); a fuel table might sit in TFRI reports, but none is online.

## A15. Understorey and other items. **ABSTRACT / snippets only**
- **Saha & Howe 2003**, *Ecology* 84:3118–3123 (doi 10.1890/02-3051). **ABSTRACT** (Wiley and ResearchGate blocked).
  - About a century of annual surface fire in central Indian dry deciduous forest has favoured 7 root-sprouting tree species. Juvenile root-sprouters rose in burnt plots and fell in protected plots.
  - The abstract has no teak-specific fuel numbers. Teak is itself a vigorous sprouter, consistent with teak persisting under annual burning **[inference]**.
- **Lantana:** in Kodayar (Tamil Nadu), exotics, mostly *Lantana*, made up a larger importance share in teak plantations than in natural forest (about 35% vs 17%; snippet). Lone et al. 2025 (*Frontiers*, MP) found *Lantana*-invaded dry deciduous sites had more understorey and litter carbon (snippet). Neither is a central-India teak vs mixed comparison.
- **Fire in teak plantations vs natural forest:** a 2022 MODIS study of central India found fire "negligible in plantations" (snippet). Commentary pieces claim teak is fire-prone. No controlled comparison was found.
- **Rothermel or Behave fuel model calibrated for teak:** none found. Two empirical alternatives:
  - The Ecuador burns (A7) give the parameter set for a custom TL-type teak model: depth about 0.1 m, 1-hr load as measured, low packing, 25% extinction moisture **[inference]**.
  - The Thai regression models (A8) give spread directly.

---

# B. Remote sensing of teak-dominated vs other dry deciduous forest

## B1. Pokhariya, Krishnamurthy, Ramesh & Kumar 2025/2026, Panna Tiger Reserve (MP). Research Square preprint; published version *Environ. Monit. Assess.* 2026, doi 10.1007/s10661-026-15125-3. **FULL** (preprint)
https://www.researchsquare.com/article/rs-7939381/latest.pdf
- **Data:**
  - Sentinel-2 SR in GEE, clouds < 10%.
  - Bands B2, B3, B4, B8 (10 m) and B5, B6, B7, B8A, B11, B12 (20 m), all resampled to 20 m.
  - Monthly images for **October 2022, December 2022, February 2023 and May 2023**. Monsoon images were excluded because "canopy cover is uniformly green".
- **Reference points:** 958 in total: 153 field plots of 20 × 20 m (26 of them in dry teak forest) plus random field points and Google Earth interpretation. Split 70/30.
- **Classifier:** smileRandomForest.
- **Accuracy (Table 1):** overall 88.9%, kappa 0.81.
  - **Dry teak forest: UA 85.26%, PA 90.62%, F1 87.86**, area 136.5 km².
  - Northern dry mixed deciduous: UA 89.35%, PA 85.89%.
  - Dry bamboo brakes: F1 89.43.
  - *Anogeissus pendula* forest: F1 92.74.
  - *Boswellia* forest: F1 51.23, merged into mixed.
- **Variable importance (Online Resource 1, not seen):** the text names the top 5 as **B5 (red-edge 1) in February, October and December; B11 (SWIR1) in May; B6 in October**.
- **Phenology notes from the paper (citing Krishen 2013):** "*Tectona grandis* begins leaf shedding in November, and new leaf emergence occurs in April and June". *Anogeissus latifolia* turns coppery in November and yellows and sheds by January. *Diospyros melanoxylon* "remains largely evergreen". In May the landscape is mostly brown, with green patches only along water bodies and ridges.
- **Dry teak forest composition:** teak IVI 137.19, *Diospyros* 46.26; 518 trees/ha.
- **Data access:** plot data are "available upon reasonable request", not public.
- **What it means for us.** This is the closest analogue to Ratapani (MP, dry deciduous, natural teak) and shows S2 can separate teak-dominated from mixed stands at about 85–90% per class. Copy the design: four dry-season composites plus red-edge, with SWIR in May. Ask the WII authors for the Panna plots as transfer training data.

## B2. Teak phenology timing, central India and nearby: field sources.

| Event | Teak | Associates | Source (status) |
|---|---|---|---|
| Leaf flush | **16 May–30 June** in MP. Of 123 clones, 18 flush 16–31 May, 78 flush 1–15 June, 27 flush 16–30 June (2002–04, Seoni TSO) | Pre-monsoon flush in Apr–May for *Diospyros* (Singh & Kushwaha 2006); "all deciduous species" in the Vindhyan region flush in May–June (Kushwaha & Singh 2005 abstract) | Roychoudhury et al. 2020, *Plants & Environment* 2(1):13–30, **FULL**, https://doi.org/10.22271/2582-3744.2020.mar.13 |
| Leaf fall | Starts November; peaks January–March (Satpura); leafless (< 5% cover) on 10 Feb 2004, 6 Mar 2014 and 23 Mar 2016 in Gujarat dry teak | *Boswellia*, *Lannea*: leafless by about Oct–Jan, > 4 months. *Terminalia*, *Lagerstroemia*: 2–4 months. *Anogeissus*, *Diospyros*: < 2 months | Pande 2002 (ABSTRACT); Malhi 2021 (FULL, in `leaf_fall_phenology.md`); Singh & Kushwaha 2006 (FULL, in `leaf_fall_phenology.md`); Panna B1 |
| Leafless period | About 3–4 months in the late dry season (Agroforestree), i.e. about March to late May/June in MP | *Diospyros* nearly evergreen; *Anogeissus* short; *Butea* bare in Jan–Mar and flowers orange in Feb–Mar (common knowledge, no source read) | A6, B1 |
| Flowering | Large whitish terminal panicles in the rainy season: June–September in Thailand | — | A6 |
| Leaf colour before fall | Teak leaves turn brown and stay attached while drying (no source read) | *Anogeissus* turns coppery in Nov; *A. pendula* purple-red in Oct | B1 |

- **Bhadra WLS, Karnataka (Nanda et al. 2013, *Afr. J. Plant Sci.* 7:170, FULL):** dry deciduous community leaf fall peaks in December–January; flush starts in February and peaks in April; teak is named among the species in both the January leaf-fall peak and the April flush peak. This is southern India, so it is earlier than MP.
- **What it means for us [inference].**
  - The **April–May "flush gap"** is the sharpest teak signal in MP. Teak is still bare and grey until late May or June, while *Diospyros*, *Madhuca*, *Terminalia*, *Buchanania* and *Schleichera* put out new leaves before the monsoon. Expected signal: low NDVI and NDRE, high SWIR1/SWIR2 reflectance, and bright bark/soil in teak pixels. This fits B11-May being a top predictor in Panna.
  - The second signal is the **February–March red-edge decline**: teak senescence and leaf fall versus *Anogeissus* and *Diospyros*, which still hold leaves.
  - The **monsoon flowering** of teak (Aug–Sep, white canopy tops) is mostly hidden by cloud. Sentinel-1 or PlanetScope gaps might catch it, but it is untested.
  - Teak does **not** keep its leaves into January–February in MP; that is the *Anogeissus*/*Diospyros* signal.

## B3. Malhi et al. 2021 (Gujarat teak MODIS phenology) and Ghosh et al. 2020 / Patasaraiya et al. 2021. **FULL / ABSTRACT** (read by the phenology session; see `leaf_fall_phenology.md` A1, A3)
- MODIS phenology dates for teak; start of season in July–August. In wet years leaf fall comes up to 24 days later on the ground and 37 days later by MODIS.
- **What it means for us.** Single-year composites move by ±3–5 weeks. Use multi-year medians or per-year harmonic fits, not fixed calendar months, when transferring Panna's model.

## B4. Ashiagbor et al. 2025, *Heliyon* (teak mapping with vegetation phenology, Ghana forest–savannah transition), doi 10.1016/j.heliyon.2025.e44180. **TITLE ONLY** (CC-BY gold OA, but Cell/Elsevier and PMC all blocked or unindexed from here)
- The title confirms phenology-based teak mapping in a comparable seasonal climate. Fetch by hand for features and accuracy.

## B5. Other teak mapping and plantation papers. **ABSTRACT / snippets**
- **Poortinga et al. 2019**, *Remote Sens.* 11:831 (Myanmar plantations; Landsat-8 + S2 + S1, random forest; accuracy "up to 91%" after error filtering). MDPI blocked; whether teak is a separate class is unconfirmed.
- **Myanmar Bago Yoma** (Canadian J. For. Res., doi 10.1139/cjfr-2018-0508): Landsat change mapping in the "home of teak". Not species mapping.
- **Indonesian teak growing-stock mapping** (*Jurnal Sylva Scienteae* 5(3), 2022): Cloudflare-blocked.
- **Indian temporal-CNN forest classification** (Int. J. Digital Earth 2025, doi 10.1080/17538947.2025.2457953): about 74% accuracy with S1/S2 in two Indian regions (snippet); teak class unknown.
- **What it means for us.** No better-documented teak classifier than Panna turned up. Southeast Asian work maps plantations, not teak within natural mixed forest.

## B6. Label sources for teak in MP and Ratapani

| Source | Downloadable? | Resolution | Covers Ratapani? | Notes |
|---|---|---|---|---|
| **Roy et al. 2015 Vegetation Type Map of India** (IIRS/DOS BCLL) | **Yes**: Zenodo record 11615011 (CC-BY 4.0), `VegetationTypeMap_India.7z` (58.6 MB → 5.1 GB GeoTIFF) + `VegAttributes.csv` | 60 m raster (from 1:50k LISS-III on-screen polygons, about 2005–2010); stated accuracy 90% (15,565 points) | **Yes.** AOI: Teak mixed moist deciduous (class 25) 46,268 ha (56.9%); Dry deciduous (26) 14,432 ha (17.7%); Degraded forest (106) 8,276 ha (10.2%); Moist deciduous (23) 6,476 ha (8.0%); Agriculture 4,980; Water 731; Scrub 121 ha. No "Teak mixed dry deciduous" (28) or "Teak" plantation (37) pixels inside the AOI | Clipped: `data/vtm_roy2015_ratapani_5kmbuf.tif`; grid: `data/vtm_roy2015_grid500m.csv` (majority: teak-mixed 2,081 cells, dry deciduous 577, degraded 335, agriculture 319, moist deciduous 267). Coarse polygons; use as weak labels or strata, not as pixel truth. The "moist" label for Ratapani teak is odd for 1,100–1,200 mm rain. |
| **WRI SDPT v2** (GFW `gfw_planted_forests` v20231128) | Polygons via the public GFW vector tiles (decoded here). SQL query needs an API key. Raster versions on S3 (`gfw-data-lake`) | Vector (India = Roy 2015 plantation polygons, "Manual polygon delineation", imagery 2010–12); 30 m raster | **No teak inside or within 33 km.** Nearest: Teak 39,342 ha polygon at 22.46 N 77.68 E (33.3 km south of the boundary) and a 9,561 ha one at 22.60 N 78.07 E. Only a 32 ha "Mixed plantation" lies 1.9 km away | SDPT India covers 1,395 kha against FAO's 13,269 kha (−90%; SDPT tech note Table). Useful as *out-of-area* teak plantation labels only. `data/sdpt_v2_tile_z8_183_110-111.geojson` |
| **Panna TR plots** (WII; B1) | On request only | 20 × 20 m plots, 26 dry-teak | No (Panna, about 250 km NE) | Best transferable field labels in MP; ask the authors |
| **SeasonWatch / GBIF teak points** | Yes (GBIF API) | Points | 6 records in 22.7–23.3 N, 77.2–78.2 E (3 SeasonWatch; mostly urban Bhopal/roadside); 127 in 21.5–24.5 N, 76–80 E | Not usable as forest labels; phenology check only (see `leaf_fall_phenology.md` A5) |
| **OSM species tags** | Overpass did not respond (proxy closed the tunnel twice) | — | Untested | OSM rarely carries `species=Tectona grandis` on forest polygons in India **[inference]**; low priority |
| **FSI Forest Type Map** (Champion & Seth, 1:50k, Atlas 2011/2020) | Not public (FSI request) | 1:50k | Yes | Would split 5A/C1b dry teak from 5A/C3 southern dry mixed; worth a formal request with the fuel-table request |
| **Bhuvan / IIRS BIS portal** | `bis.iirs.gov.in` did not respond; Bhuvan WMS layer not found | — | — | The Zenodo copy makes this unnecessary |
| **MP Forest Dept compartment / working-plan maps** (teak working circles) | Not online | Compartment | Yes | The richest truth if the Ratapani/Obaidullaganj DFO will share it |

**Recommendation for B.** Do not trust the 1:50k VTM polygons pixel by pixel. Instead:
1. Draw training points from the *interiors* of VTM teak-mixed and dry-deciduous polygons (for example ≥ 300 m from a class edge).
2. Check about 200 of them on Google Earth or Esri Wayback dry-season imagery. Teak is easy to see in March–May VHR imagery: large grey-brown crowns, bare, often with huge leaves on the ground.
3. Train an S2 random forest on Panna-style features:
   - October, December, February, April–May composites
   - B5/B6/B7 red-edge, B11/B12 SWIR, NDVI/NDRE/NDMI
   - per-pixel phenology metrics: date of 50% greenness loss, date of green-up onset (teak ≥ late May), and April–May greenness relative to February
   - GLCM texture on B8 for bamboo
4. Expect about 85–90% class accuracy (Panna).

---

## What to do with this (fuel map and spread threads)

1. **Stratify fuels by VTM class now**, with the grid CSV. For teak-mixed cells **[inference]**:
   - Leaf litter accrues from about day 30 to day 140 (February to mid-May), not from day 335.
   - Bed depth about 5–8 cm and bulk density about 10 kg/m³ at 3–5 t/ha.
   - Near-zero in-season decay (A5).
   For dry deciduous cells, use the earlier build-up (November–January) and denser small-leaf litter, plus a grass term in open cells.
2. **Add `vtm_teakmix_frac` as a static feature** in the 2-day model. The burn frequency gap (A13) is modest but consistent across all 13 strata. Then check whether it adds anything beyond canopy cover and leaf-fall timing.
3. **Build an S2 teak-fraction layer** (B6 recommendation) to replace the coarse VTM polygons. The April–May "teak still bare" signal doubles as a fuel-availability flag: bare teak crowns mean full litter and maximum sun on the floor.
4. **Spread model:** a custom teak litter model built from the Ecuador burns (A7), checked against the Thai regressions (A8) at 2–4 t/ha and 6% moisture: expect 0.5–2.5 m/min and flames of about 0.5–1.1 m.
5. **Fetch by hand** (blocked here): Behera et al. 2023 (*Trop. Ecol.*, teak/sal/bamboo/grass flammability); Kushwaha et al. 2010 *Ann. For. Sci.* 67:310 (per-species leaf-fall dates); Ashiagbor 2025 *Heliyon*; Saha & Howe 2003; Kittur 2014; Chernkhunthod & Hioki 2020 *LEE*; Poortinga 2019. Ask WII for the Panna plot data.
