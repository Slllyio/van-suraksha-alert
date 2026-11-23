# First burns in cells with no fire history ("cold start"): own data, literature, and what to do (scouting round 7, 14 Oct 2026)

Question: how do we predict the first burn in a cell that has never burned (or rarely burns)? The literature topics are fuel build-up since the last fire, contact with recently burned patches, roads and fire lines as barriers, contagion from neighbours, and regime shifts. I did the analysis on our own data first, because it changes what is worth chasing.

Not repeated here: Parks 2015, Pereira Jr 2014, the fuel-age and "burned 1-2 years ago ignites more" work (`fire_regime_ecology.md`); Narayanaraj & Wimberly 2012 on roads and ignitions, plus the Open Buildings Temporal and Microsoft roads data (`access_paths.md`, `open_datasets.md`); fire-line practice and the NAPFF/MP budget numbers (`fire_management_practice.md`); and Hawkes contagion kernels (`short_horizon_prediction*.md`, and the research thread found no gain from them).

Scripts are in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/` (a1-a10). Those scripts live only in a temporary scratch folder, so copy them to `fsi/scouting/code/` if you want to keep them. All "our data" numbers come from `burn_windows.csv` (burned = 1), `true_lead_labels_v2.parquet`, the lean classifier's LOSO predictions (`scoring/pipeline_lean_pred_loso_2017_24.parquet`) and the lean ensemble, all scored on real beats with 5 picks per beat per day.

## Headline findings

1. **Cold cells are a small share of the problem: 0.4-1.5% of positives.**
   - "LOSO-cold" cells are cells that did not burn in any of the other 7 training seasons, which is what the model's burn-history prior sees. They hold 1,405 of 110,000 main-rule positive cell-days (1.3%), 82 of 11,285 strict true-lead positives (0.7%) and 1,194 lenient positives (1.5%).
   - Cells cold on past seasons only (2020 onward) hold 828 main positives (0.7%).
   - Even a perfect cold-start fix cannot move overall recall@5 by more than about 1 point.
2. **The low recall there is a correct budget trade-off, not a model failure.**
   - Lean recall@5 in LOSO-cold cells is 8.6% on the main rule, against 24.8% for random. On past-only cold cells from 2020 it is 5.3% against 20.9% (strict true-lead: 8.0% against 26.0%). This is the "1.4%" problem.
   - But the model is **calibrated** in these cells: mean prediction 0.0051 against an observed rate of 0.0051, and 0.0069 against 0.0065 for past-only cold cells.
   - It also **ranks them well among themselves**: AUC 0.82 on the main rule and 0.91 on strict labels.
   - Their burn rate is 6-8 times lower than in other cells, so they rightly lose the 5 picks to cells with history. Random looks better only because it ignores that.
3. **Who the never-burned cells are.**
   - 224 cells never burned in 2017-2026. A further 186 were still unburned in 2020 but burned later. Median values for the 224 that never burn, then for the 186 that do:

     | | Never burn (224) | Burn later (186) |
     |---|---|---|
     | Eligible forest area (`elig_ha`) | 3.4 ha | 16.3 ha |
     | Cropland share (`wc_crop`) | 0.60 | 0.03 |
     | Forest fraction | 0.44 | 0.92 |
     | Distance to the nearest Open Buildings building | 440 m | 860 m |

   - Burn rate per season among no-history cells rises with eligible area: 0.5% at ≤2 ha, 5.8% at 2-5 ha, 8-11% at 5-15 ha and 17% above 20 ha.
   - **Most "never burned" cells are crop-edge cells with too little mappable forest to show a 0.5 ha scar.** Part of this is a detectability artefact of the label, not fire-proof forest.
4. **When a cold forest cell does burn, it is almost always spread from a neighbour.**
   - 93% of first burns in no-history cells (94% where `elig_ha` ≥10) had a cell within 1 km whose first-burn window ended in the 7 days before, or inside, the cell's own window.
   - The share of a cell's 1 km neighbours burned that season separates burners from non-burners at AUC 0.81 at season level. No first burn happened where no neighbour burned that season (0 of 677 cell-seasons).
   - Cold-cell first burns come later in the season: 51% in April against 32% for all first burns.
   - With daily inputs known by t-1, the neighbour signal only reaches AUC 0.60 (`nbs`) and 0.60 (`nb7`), well below lean's 0.84 within the same rows. A logistic re-rank of cold rows on lean + neighbours + `elig_ha` changed recall@5 by +0.01 points overall (28.91 → 28.92), +0.7 points in cold cells on the main rule and -0.6 on lenient labels. Not worth it.
5. **The literature agrees on the mechanism: recent burns stop fires, and long-unburned places burn last.**
   - Price et al. 2014: 92% of points with a same-year scar within 500 m are fire boundaries.
   - Holsinger 2016: burns 1-5 years old impede spread most.
   - Collins 2009: fires under 9 years apart almost never reburn.
   - Krawchuk 2016: refugia are predictable from terrain only under moderate fire weather, AUC 0.77, falling to 0.63-0.68 under high fire weather.
   - In Ratapani litter fuel resets every year with leaf fall, so only the within-season "already burned" barrier applies. Lean already has it (`nb*_season`, own first-burn masking) [inference].
6. **What gives small but real gains:**
   - A spatially smoothed history prior: a 50/50 blend of the cell's own burn frequency and its 1 km neighbours' raises season-level AUC from 0.656 to 0.666. This follows Opitz 2020's Matérn spatial effect with year-to-year AR(1) ρ 0.89.
   - Treating very low `elig_ha` cells as label-blind in the field system.
   - Roads, TPI (valley/ridge position) and fire lines **did not** show a barrier effect at 500 m on our data.

## Part A. Own-data analysis (DATA)

### A1. How many cold cells, and how often they burn (`a1_history.py`)
- Cells burned per season (≥0.5 ha): 2017 2,094; 2018 2,861; 2019 2,821; 2020 1,145; 2021 1,723; 2022 2,220; 2023 1,576; 2024 1,314; 2025 2,056; 2026 2,197 (of 3,614).
- Seasons burned per cell, out of 10: 0 → 224 cells, 1 → 161, 2 → 195, 3 → 243, 4 → 316, 5 → 412, 6 → 523, 7 → 600, 8 → 509, 9 → 317, 10 → 114.
- Past-only no-history cells, and how many burned that season:

  | Season | No-history cells | Burned that season | Rate | Rate in cells with history |
  |---|---|---|---|---|
  | 2020 | 410 | 34 | 8% | 35% |
  | 2021 | 376 | 17 | 5% | 53% |
  | 2022 | 359 | 59 | 16% | 66% |
  | 2023 | 300 | 12 | 4% | 47% |
  | 2024 | 288 | 27 | 9% | 39% |
  | 2025 | 261 | 17 | 7% | 61% |
  | 2026 | 244 | 20 | 8% | 65% |

- The highest cold-cell rate came in a high-activity year (2022, 16%) [inference: dry years push fire into marginal cells, as Alencar 2015 finds for drought years in Amazonia].
- **No regime shift:** first-ever burns per season do not trend upward (34, 17, 59, 12, 27, 17, 20 for 2020-2026).

### A2. Recall by history class (`a2_recall.py`, `a6_losocold.py`; seasons 2019-24, lean classifier unless noted)

| Cells (by burn count in the other 7 LOSO seasons) | Main-rule positives (share) | Lean recall@5 | Random | Strict true-lead positives | Lean / random (strict) |
|---|---|---|---|---|---|
| 0 (LOSO-cold) | 1,405 (1.3%) | 8.6% | 24.8% | 82 (0.7%) | 15.9% / 31.7% |
| 1 | 3,206 (2.9%) | 12.9% | 23.5% | 226 (2.0%) | 16.8% / 30.5% |
| 2 | 7,871 (7.1%) | 23.6% | 22.2% | 710 (6.3%) | 31.5% / 25.6% |
| ≥3 | 98,540 (88.8%) | 30.8% | 15.8% | 10,267 (91.0%) | 40.8% / 19.1% |

- The lean ensemble behaves the same way (11.6% against 12.7% for the classifier on past-only cold cells 2019-24).
- Calibration in LOSO-cold cells by month (prediction / observed rate):

  | Month | Predicted | Observed |
  |---|---|---|
  | Feb | 0.0041 | 0.0046 |
  | Mar | 0.0069 | 0.0095 |
  | Apr | 0.0078 | 0.0067 |
  | May | 0.0027 | 0.0010 |

  There is no systematic seasonal bias to correct.
- **Caveat for live use:** the LOSO prior uses future seasons, so in LOSO a cell that burns only in 2023 is "warm" when 2020 is scored. Operationally the prior only uses the past, so the live cold set is larger in early years. From 2025 it is about 250 cells of 3,614.

### A3. Profile of no-history cells that burn against those that stay unburned (2020-26, 2,238 cell-seasons, 186 burns; `a3_profile.py`, `a4_bins.py`)
- AUC of each input at season level, with medians for cells that burn and cells that stay unburned:

  | Input | AUC | Median, burns | Median, stays unburned |
  |---|---|---|---|
  | Share of 1 km neighbours burned this season (descriptive, not a forecast) | 0.81 | 0.50 | 0.17 |
  | `elig_ha` | 0.74 | 16.3 | 4.8 |
  | Distance to cropland (`d_crop`) | 0.69 | 179 m | 68 m |
  | Cropland share (`wc_crop`) | 0.32 (inverse) | | |
  | Terrain roughness | 0.66 | | |
  | Slope | 0.66 | 4.1° | 2.8° |
  | Grass share | 0.64 | | |
  | Distance to nearest building (`d_ob`) | 0.63 | 863 m | 492 m |
  | Forest fraction | 0.63 | | |
  | Sub-threshold scar area in earlier seasons (`sub_ha_prior`) | 0.60 | | |
  | Earlier VIIRS points in the cell | 0.57 | | |
  | Pre-season NDVI (Jan-Feb median) | 0.54 | | |
  | Distance to a cell burned last season | 0.50 | | |
  | Share of 1 km neighbours burned last season | 0.50 | | |
  | VIIRS 2013-16 count | 0.52 | | |
  | Number of clear looks | 0.51 | | |

- **Burn rate by share of 1 km neighbours burned this season:** 0% when none (n = 677), 5% for 0-25%, 13% for 25-50%, 25% for 50-75% and 31% above 75%.
- **Burn rate by distance to the nearest building:** 5% within 250 m, 9% at 250-500 m, 14% at 0.5-1 km, 16% at 1-2 km and 20% beyond 2 km. This repeats the "interior burns more" finding.
- **Burn rate by slope:** 3% at ≤2°, 8.5% at 2-4°, 12% at 4-10° and 15% above 10°.
- Contact with last season's scars (distance, neighbour share) carries **no** information (AUC 0.50). Fuel recovery after a burn is not a limit at the one-year scale here, which fits the annual litter reset [inference].

### A4. Re-rank tests that did not help
- **Contagion re-rank (`a5_rerank.py`):** a LOSO logistic re-score of cold rows on logit(lean), the neighbour share burned so far, neighbour scars in the last 7 days and `elig_ha`.
  - Main rule: overall 28.91 → 28.92; cold cells 12.65 → 13.51; cold cells 2020+ 5.31 → 6.04.
  - Lenient: overall 30.64 → 30.65; cold cells 12.95 → 11.31.
  - No real gain.
- **Eligible-area weighting (`a7_elig.py`, `a8_eligrerank.py`):** cells with ≤10 ha of eligible forest take 22.5% of top-5 picks and hit 0.7-2.8% of the time, against 9.2% in cells with 10-30 ha.
  - 10.1% of all picks are such cells in beat-days with more than 5 candidates, but only 3.5% of picks leave a >10 ha candidate unpicked. Most of these picks are **forced** by small fringe beats.
  - Multiplying lean by (elig/15)^a for a = 0.25-2 gives 29.49-29.53% against 29.49%, which is noise.
- **Roads as barriers (`a10_roadbarrier.py`):** among cells (elig ≥15 ha) with a rook neighbour scar in the last 7 days, cells with a mapped road (OSM + Microsoft) burn **more**, not less (13.7% against 11.5%). Unexposed cells with a road burn 4.3% against 5.3% without. At 500 m with 5-day windows, roads act as ignition paths rather than barriers [inference].
- **Topographic position (`a9_smooth_tpi.py`):** ridge cells (TPI at 2 km, top fifth) burn in 68% of seasons, against 53% for valley cells (bottom fifth). But adding TPI (1 and 2 km) to own + neighbour history + elevation + slope leaves season-grouped CV AUC at 0.654. The signal is already in elevation and slope.
- **Smoothed history prior (`a9_smooth_tpi.py`, cells with elig ≥10 ha, season-level burn AUC):** own frequency 0.656; 1 km neighbour frequency 0.651; blends 0.25 → 0.663, 0.5 → 0.666, 0.75 → 0.663. In LOSO-cold forest cells the neighbour frequency alone gives AUC 0.59. This is the one prior change with a measurable lift (see Action 2).

## Part B. Sources

### B1. Krawchuk, Haire, Coop, Parisien, Whitman, Chong & Miller 2016, "Topographic and fire weather controls of fire refugia in forested ecosystems of northwestern North America", *Ecosphere* 7(12):e01632. **FULL**
Link: https://research.fs.usda.gov/treesearch/56427 (PDF), DOI 10.1002/ecs2.1632. Code and data: https://www.sciencebase.gov/catalog/item/5810e721e4b0f497e797a5b5
- **Data and models.** Seven fires (2001-2014, 999-129,284 ha). Refugia were defined as unburned or low-severity pixels, mapped at 30 m. Boosted regression trees (gbm; learning rate 0.001, tree complexity 5, bag fraction 0.5, ≥1,000 trees) were fit on terrain metrics only.
- **Strata.** Nine models: terrain ruggedness FLAT / MODERATE / RUGGED × fire weather BENIGN (FWI 0-13) / MODERATE (>13-29) / HIGH (>29).
- **Accuracy.** AUC ranges from 0.63 (flat terrain, any weather) to 0.77 (moderate terrain, moderate weather). Deviance explained ranges from 4% (FLAT-HIGH) to 50% (RUGGED-BENIGN).
- **Which terrain metrics matter.** Catchment slope is the top variable, ranked in the top three in 8 of 9 models; refugia are likelier where catchment slope is low. The next most important are local aspect (north-facing), relative position, topographic wetness (wetter areas give more refugia) and convergence (a concave response).
- **Weather.** Under high fire weather, refugia become both rarer and less predictable.
- **Concrete action for us.**
  - *Thread 1:* the "never-burn" cells are refugia in this sense. Our own data says flat, low-roughness, crop-mixed cells stay unburned (slope AUC 0.66), consistent with Krawchuk's flat-terrain result. A topographic wetness index per cell (from the Copernicus DEM already used for slope) is the one terrain input we do not yet have. Expected gain ≤0.2 points [inference]: TPI added nothing (A4), and elevation and slope carry most of it.
  - *Thread 4 (spread):* refugia probability falls under high FWI. If the spread model uses a burn probability per cell, make it depend on the day's dryness, not only on terrain.

### B2. Morton, Le Page, DeFries, Collatz & Hurtt 2013, "Understorey fire frequency and the fate of burned forests in southern Amazonia", *Phil. Trans. R. Soc. B* 368:20120163. **FULL** (PMC3638429, read through the fetch tool)
- **Mapping.** Burn Damage and Recovery time-series algorithm on MODIS; only understorey fires larger than 50 ha; 1999-2010.
- **Area burned.** Understorey fires burned 85,500 km² (2.8% of forest).
- **First fires dominate.** Repeat fires were 16% of understorey fire area (24% in Mato Grosso). By 2010, 73% of fire-damaged forest had not burned in 1999-2009, so first-time burns dominate every year. Under 10% of the area burned in 2005 burned again by 2010.
- **Return intervals and edges.**
  - Mean return interval is 3.7 years where forest burned more than once, 245 years in edge forest (<5 km from non-forest) and 422 years over all forest.
  - Most burned forest lies within 1 km of an edge, and 74% of repeat fires are within 1 km. Forest more than 2 km from an edge carries 16% of annual fire.
  - Fires spread at 0.1-0.5 m/min, so fires more than 2 km in may burn for over a week.
- **Weather.** Low night-time humidity (AIRS RH <60% in ≥6 of 8 years) marks the high-fire arc. The repeat-burn share rises with the number of high-fire years (R² 0.27).
- **Concrete action for us.**
  - *Thread 1 (validation framing):* in a landscape like the Amazon, first fires dominate and edges matter. Ratapani is the opposite: 89% of positives fall in cells that burned in ≥3 of the other 7 seasons, and interiors burn more. This confirms that our regime is a **recurrent-fire** regime, where history is the main input and cold start is a minor tail.
  - *Thread 5:* Morton's "fires >2 km in burn for over a week" fits our finding that cold-cell first burns are spread from neighbours (93%). When a fire is reported beside a never-burned forest cell, keep that cell on watch for about 7 days [inference].

### B3. Alencar, Brando, Asner & Putz 2015, "Landscape fragmentation, severe drought, and the new Amazon forest fire regime", *Ecological Applications* 25:1493-1505. **FULL** (author manuscript on the INPE server)
Link: https://dataserver-coids.inpe.br/queimadas/queimadas/Publicacoes-Impacto/material3os/2015_Alencar_etal_Drought&FireAMZ_ESA_DE3os.pdf
- **Data.** 6 million ha; annual Landsat fire scars 1983-2007 and hot pixels 1992-2007.
- **Share of forest burned, once and repeatedly.**

  | | Dense forest | Open forest | Transitional forest |
  |---|---|---|---|
  | Share burned over 24 years | 15% | 44% | 46% |
  | Share of burned area burned only once | 72% | 45% | 30% |
  | Share burned twice | 20% | 24% | 22% |
  | Mean number of repeated fires | 1.4 | 2.3 | 3.1 |
  | Fire rotation (no deforestation) | 82 yr | 15 yr | 11 yr |
  | Most consecutive burn years | 3 | 9 | 6 |

- **Highest recurrence.** Up to 12 burns in 24 years in transitional forest, on 0.5% of the burned area.
- **Settlements, savanna edges and season.** 78% of consecutive fires in open forest were within 10 km of a settlement; recurrent fires in transitional forest sit on savanna borders. In drought years the fire season ends about a month later, with larger scars and more area burned late.
- **Concrete action for us.**
  - *Thread 1:* Ratapani's cold-cell first burns are also late (51% in April against 32% overall), and the cold-cell burn rate peaked in the high-activity 2022 season (16%). An interaction of "cold cell × days since season start × sanctuary dryness" is the published mechanism. Our calibration check (A2) shows lean already gets the month pattern right, so expect ≤0.1 points [inference].
  - *Thread 3 (fuel map):* report fire rotation per forest stratum as Alencar does. Ours is about 1-2 years for most cells (median 6 of 10 seasons burned), which tells the fuel map that time since fire is almost always 0-1 years.

### B4. Holsinger, Parks & Miller 2016, "Weather, fuels, and topography impede wildland fire spread in western US landscapes", *Forest Ecology and Management* 380:59-69. **FULL**
Link: https://research.fs.usda.gov/treesearch/52447
- **Method.** Matched case-control logistic regression: fire-edge samples every 3 km along each perimeter (a 1% sample), matched to samples in the fire's core (the inner 50% of area). Four study areas.
- **Previous burns.** Burns 1-5 years old were moderately to highly influential in all areas and were the top variable in all but the most northern area. Influence fell with age (6-10 and 11-15 year classes). In the frequent-fire Southwest area, older burns even had a positive coefficient.
- **Topography.** |TPI| at 2 km (valley bottom or ridge) was the most influential topographic variable everywhere: edges sit at high |TPI|, cores at mid-slope.
- **Other inputs.** NDVI was lower at edges in two areas. Roads were deliberately not tested as a cause: they lie along valleys and ridges and give suppression access, which confounds them.
- **Concrete action for us.**
  - *Thread 4:* make same-season scars and the fire's age the main barrier inputs.
  - *Thread 1:* I tested |TPI2k| in Ratapani (A4). It does not mark cells that stay unburned (AUC 0.51 among all forest cells) and adds nothing over elevation and slope. Drop it for thread 1, but keep it as a spread-stop candidate for thread 4, where it should be tested on 20 m scar edges, not on 500 m cells.

### B5. Opitz, Bonneu & Gabriel 2020, "Point-process based Bayesian modeling of space-time structures of forest fire occurrences in Mediterranean France", arXiv:2002.12318 (*Spatial Statistics* 2020). **FULL**
- **Model.** A log-Gaussian Cox process on a 2 km DFCI grid (about 40,000 km², 1995-2018, monthly), fitted with INLA-SPDE. 33 covariates, including the mean and standard deviation of land cover inside each cell, and forest-building and forest-path interfaces.
- **Random effects.** A Matérn spatial field with yearly AR(1) dependence. Each extension (one spatial field, then yearly replicates, then AR(1)) raised the marginal likelihood by more than 1,000 (model 1: -4,200; model 2: -3,000; model 3: -1,200, relative to model 4).
- **Fitted parameters.** Spatial range 20 km (sd 1 km); field sd 1.36; year-to-year autocorrelation 0.89; a 40% intensity decline over 24 years. Over 91% of positive cell-months have exactly one fire.
- **Covariates.** Positive: forest-building interface, total road length, slope. Negative: secondary roads and paths.
- **Concrete action for us** (thread 1). The prior `log((count+0.5)/(n+1))` treats each cell independently, so a cold cell gets the global floor whatever its neighbours do. Replace it with, or add, a **spatially smoothed prior**:
  - Simplest form: 0.5 × own frequency + 0.5 × the mean over 1 km neighbours, built from training seasons only. On our data this lifts season-level AUC from 0.656 to 0.666 (A4).
  - Better form: kernel weights with a 1-2 km bandwidth, plus an AR(1) weight on recent seasons (ρ ≈ 0.9 means recent years count most).
  - Expected gain: +0.1 to +0.4 points recall@5 overall, mostly in cells with 0-2 burns [inference]. Effort: low (one feature).

### B6. Price, Borah & Maier 2014, "Role of weather and fuel in stopping fire spread in tropical savannas", *Austral Ecology* 39:135-144. **ABSTRACT ONLY** (UOW repository returned 403)
- **Data.** Nine large late-dry-season fires in Arnhem Land.
- **Recent burns.** Where any same-year burn lay within 500 m, the point was a fire boundary with 92% likelihood.
- **Other barriers.** Roads, rivers and topography had small but significant effects; weather had only a small effect. About half the boundaries had no clear cause at the scale analysed.
- **Concrete action for us** (thread 4). Same-season scars are the dominant barrier, roads secondary. This matches our A4 road result.

### B7. Collins, Miller, Thode, Kelly, van Wagtendonk & Stephens 2009, "Interactions among wildland fires in a long-established Sierra Nevada natural fire area", *Ecosystems* 12:114-128. **ABSTRACT ONLY** (the Berkeley lab PDF link now returns 404; no Unpaywall copy)
- 19 fires over 31 years. When successive adjacent fires were less than 9 years apart and burning index was below 34.9, the later fire was very unlikely to burn into the earlier footprint. Prichard 2017 summarises the reduced-severity window as 11-17 years.
- **Concrete action for us** (thread 4). Our fuel resets every year, so the equivalent window is "earlier in the same season". Same-season scars act as barriers in the spread model; scars from last season do not (A3: AUC 0.50) [inference].

### B8. Teske, Seielstad & Queen 2012, "Characterizing fire-on-fire interactions in three large wilderness areas", *Fire Ecology* 8(2):82-106. **PARTIAL** (abstract and results)
Link: https://nwfirescience.org/sites/default/files/publications/fireecology.0802082.pdf
- **How often fires meet.** Less than 3% of the available perimeter was ever met by a later fire.
- **Breaching.** About 80% of the edge that was met was breached, with at least 40 ha reburned. Reburns were mostly small (40-405 ha) and became rarer as time between fires grew.
- **Reburn share.** About 7 ha reburned per 100 ha burned (Selway-Bitterroot). Only 0.9%, 1.0% and 7.3% of the three wildernesses burned more than once.
- **Concrete action for us** (thread 4). Treat previous scars as **partial** barriers (lower spread probability), not hard walls.

### B9. Prichard, Stevens-Rumann & Hessburg 2017, "Tamm Review: Shifting global fire regimes: lessons from reburns and research needs", *Forest Ecology and Management* 396:217-233. **PARTIAL** (Tables 1-3, sections 2-3 read)
Link: https://research.fs.usda.gov/treesearch/54770
- **Table 2, how long past fires act as barriers:** up to 6 years in southwest mixed conifer; 14-18 years in Rocky Mountains mixed conifer; up to 35 years in the interior Pacific Northwest.
- **Table 2, fuel breaks (Syphard 2011a,b).** Fuel breaks worked 46% of the time, alongside suppression.
- **African savannas.** Grass recovers within weeks once rain returns. Because human ignitions are everywhere, area burned is set by fuel continuity, and agriculture and roads fragment it (citing Archibald 2009).
- **Research gap.** Asia is almost unstudied.
- **Recommended metrics (Table 3):** barrier duration (years), percent of perimeter breached, and interactions with weather, topography and vegetation.
- **Concrete action for us** (thread 4 validation). Report "percent of an earlier scar's edge breached within the same season" as a spread-model check. It is computable from our 20 m rasters (band 1 = window end date) [inference].

### B10. Meddens, Kolden, Lutz, Abatzoglou & Hudak 2018, "Spatiotemporal patterns of unburned areas within fire perimeters in the northwestern United States from 1984 to 2014", *Ecosphere* 9:e02029. **PARTIAL** (abstract, methods, first results)
- 2,298 fires; unburned islands mapped from Landsat (method from Meddens 2016, RSE 186:275-285, with 89% accuracy).
- Mean unburned share 9.6% (sd 10.6%); 701,188 patches; no trend over 30 years. Data are on ScienceBase.
- **Concrete action for us** (thread 2). Our scar labels drop patches under 2 ha, so unburned islands inside a scar and cells that are "never burned" for lack of detectable area (A3) are both label limits. When verifying alerts in the field, record "unburned inside the perimeter" as its own class, so the label error (7.4% of "unburned" pixels actually burned in the blind check) can be split into true refugia and missed fire [inference].

### B11. Cano-Crespo, Oliveira, Boit, Cardoso & Thonicke 2015, "Forest edge burning in the Brazilian Amazon promoted by escaping fires from managed pastures", *JGR Biogeosciences* 120:2095-2107. **PARTIAL** (PIK repository PDF; abstract, methods, results figures)
Link: https://publications.pik-potsdam.de/pubman/item/item_20509_3/component/file_20510/6977.pdf
- **Method.** Escape fires are attributed by **adjacency plus date order**: a burned forest edge next to a burned managed area, with the active fire in the managed area earlier.
- **Results.** Up to 52% of burned forest edges were adjacent to burned pastures. Deforestation fire was only 1-7% of burned area, and spatial overlap of deforestation with burned area averaged 8%.
- **Concrete action for us** (threads 2 and 5). Use the same adjacency + date rule to tag each cold-cell first burn as "spread-in" or "own ignition". On our data the rule tags 93% as spread-in (A3). Only the remaining ~7% (about 13 cell-seasons in 7 years) are true cold ignitions, too few to model.

### B12. Awadhiya 2017, "Fire breakers: novel devices for the control of forest surface fires", *Indian Forester* 143(8):737-744 (Mandla and Balaghat, MP). **ABSTRACT ONLY** (the PDF link returns an empty file)
- Field observations in MP found four ways traditional fire lines fail:
  - "bleeding": adjacent patches burn;
  - "infiltration": vegetation grows into the line;
  - "repopulation": fuel returns on the line;
  - "mosaicking": patches of fuel left on the line.
- The last three restore fuel continuity, so lines often fail as breaks. The proposed fire breakers were tested only in simulation. There are no numbers in the abstract.
- **Concrete action for us** (thread 4). Do not model MP fire lines as hard non-burnable strips. This is the first MP evidence on the point, and it matches our A4 result that cell-level roads do not stop spread. Use a reduced spread probability across a line, scaled by whether the line was cleared that winter (the clearing-status idea in `fire_management_practice.md`).

### B13. Narayanaraj & Wimberly 2011, "Influences of forest roads on the spatial pattern of wildfire boundaries", *IJWF* 20:792-803. **ABSTRACT ONLY**
- Six fires in the Wenatchee NF; matched case-control design. In 4 of 6 fires, boundaries were significantly closer to roads than random control points. Where significant, roads outweighed terrain and vegetation. Holsinger 2016 notes that suppression access confounds this.
- **Concrete action for us** (thread 4). The road-boundary effect is a suppression effect. In Ratapani's largely unsuppressed small litter fires, expect roads to matter less than same-season scars (A4).

### B14. Syphard, Keeley & Brennan 2011, "Factors affecting fuel break effectiveness in the control of large fires on the Los Padres National Forest", *IJWF* 20:764-775. **ABSTRACT ONLY**
- Over 28 years, fires stopped at fuel breaks 46% of the time, almost always because of suppression. Access for firefighters, smaller fires and longer breaks had direct effects; maintenance and younger vegetation helped indirectly, through access.
- **Concrete action for us** (thread 5). Fire lines pay off as **access routes** for the verification crew more than as barriers. Rank field checks so that targets reachable from a fire line or road come first when two cells score alike [inference].

### B15. Crime-forecasting analogues: Bowers, Johnson & Pease 2004, "Prospective hot-spotting", *Br. J. Criminology* 44:641-658, and Caplan, Kennedy & Miller 2011, "Risk terrain modeling", *Justice Quarterly* 28:360-381. **ABSTRACT ONLY** (both)
- **Bowers et al.** Homes within about 400 m of a burgled home stay at higher risk for up to two months. The prospective map is a sum of recent events weighted down as their predictive power fades. That is the near-repeat analogue of our "neighbour burned in the last 7 days".
- **Caplan et al.** Risk terrain maps built from environmental layers forecast shootings at places with no prior events better than retrospective hot spots, over two six-month periods.
- **Concrete action for us** (thread 1). Both ideas are already in lean (neighbour scars of the last 7 days and of the season; static landscape layers). The research thread's Hawkes test found nothing extra. No new action; they confirm the design.

## Datasets

| Name | Link | Resolution | Years | Licence | How to access |
|---|---|---|---|---|---|
| Our burn windows (scar labels) | `/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv`, `rasters/burn_<season>.tif` | 500 m cells; 20 m rasters | 2017-2026 | project | shared mount |
| Eligible forest area per cell (`elig_ha`) | `/mnt/project-files/research/ratapani-ignition/cells_static.csv` | 500 m | static | project | shared mount; **not in the lean inputs yet** |
| Krawchuk 2016 refugia code and data | https://www.sciencebase.gov/catalog/item/5810e721e4b0f497e797a5b5 | 30 m | 2001-2014 fires (Canada) | US public domain | download; R gbm scripts as a template for a refugia BRT |
| Unburned areas within fire perimeters (Meddens 2018) | ScienceBase item 5abbe351e4b081f61abd5b77; doi 10.1002/ecs2.2029 | 30 m | 1984-2014 (NW USA) | US public domain | download (method reference only) |
| Copernicus DEM GLO-30, for a topographic wetness index | Earth Engine `COPERNICUS/DEM/GLO30` | 30 m | static | Copernicus free licence | GEE export, mean TWI per 500 m cell |
| R-INLA (SPDE spatial fields, Opitz 2020) | https://www.r-inla.org | n/a | n/a | GPL | R package; needed only for a full spatial-prior model; the kernel-smoothed prior needs nothing new |

## Ranked action list (gain and effort are my estimates [inference] unless measured)

1. **Stop treating cold-start recall as a target, and report it as a calibrated tail.** Thread 1 and SCORING notes.
   - Cold cells are 0.7-1.5% of positives. Lean is calibrated there (0.0051 predicted against 0.0051 observed) and ranks them at AUC 0.82-0.91 among themselves.
   - Add a line to SCORING.md: "recall in no-history cells is expected to be below random under a fixed 5-per-beat budget."
   - Gain: saves effort. Effort: minutes.
2. **Add a spatially smoothed burn-history prior** (thread 1).
   - Inputs: training-season burn counts. Use 0.5 × own + 0.5 × 1 km neighbour mean, or a 1-2 km kernel with AR(1) season weights (ρ ≈ 0.9, Opitz 2020).
   - Measured: season-level AUC 0.656 → 0.666.
   - Expected: +0.1 to +0.4 points recall@5, mostly in cells with 0-2 burns. Effort: low (one feature in `pipeline_lean_model.py`'s `prior()`).
3. **Add `elig_ha` (mappable forest per cell) as a lean input, and flag cells with ≤2 ha as label-blind** (threads 1 and 5).
   - These cells burn 0.5% per season and are often "never burned" only because a 0.5 ha scar cannot show.
   - Measured: post-hoc weighting gives 0 points under fixed 5 per beat, because those picks are forced in fringe beats.
   - Under the day-shared budget, or for field crews, skipping them saves checks: 3.5% of picks hit at 0.7% [inference: small gain in shared-budget recall].
   - Effort: low.
4. **Same-season scars as partial barriers in the spread model** (thread 4).
   - Evidence: Price 2014 (92% of boundaries within 500 m of a same-year scar), Holsinger 2016 (burns 1-5 years old dominate), Teske 2012 (80% of met edges breached, reburns small).
   - Use a spread probability multiplier of about 0.2-0.5 into pixels already burned this season [inference: starting value, calibrate on 20 m rasters]. Do not use last season's scars (A3: no effect) or roads (A4: no barrier effect at cell scale). Treat MP fire lines as leaky (Awadhiya 2017).
   - Gain: medium for spread realism. Effort: medium.
5. **"Spread-in watch" for never-burned forest cells in the alert system** (thread 5).
   - 93-94% of cold-forest first burns had a neighbour within 1 km burning in the previous 7 days or the same window.
   - When an alert lands within 1 km of a cell with no burn history and ≥10 ha of eligible forest, list that cell for 7 days as a low-cost add-on check.
   - Gain: small (about 20 cell-seasons a year) but these are cells crews would never otherwise visit. Effort: low.
6. **Spread-in or own-ignition tag on every first burn** (threads 2 and 1 diagnostics).
   - Use Cano-Crespo's adjacency + date rule on our windows.
   - Gives a clean split of "true cold ignitions" (about 7% of cold first burns) for future work, and a validation set for the research thread's new-ignition model.
   - Effort: low.
7. **Topographic wetness index per cell** (threads 1 and 3).
   - Krawchuk's refugia predictor. TPI added nothing (A4), so expect ≤0.2 points. Effort: low-medium (GEE export).
8. **Percent of earlier same-season scar edges breached**, as a spread-model check (thread 4).
   - Prichard 2017's recommended metric, computable from band 1 of the 20 m rasters. Effort: medium.

Not recommended (tested here, no gain):
- the contagion re-rank of cold rows (A4: +0.01 points);
- eligible-area weighting of the lean score under fixed 5 per beat (A4: within ±0.04 points);
- road-in-cell as a barrier (A4: the opposite sign);
- TPI as a burn-frequency input (A4: CV AUC unchanged);
- "distance to last season's scar" (A3: AUC 0.50).

## Reading status
- **FULL 5:** Krawchuk 2016; Morton 2013; Alencar 2015; Holsinger 2016; Opitz 2020.
- **PARTIAL 4:** Teske 2012; Prichard 2017; Meddens 2018; Cano-Crespo 2015.
- **ABSTRACT ONLY 7:** Price 2014; Collins 2009; Awadhiya 2017; Narayanaraj & Wimberly 2011; Syphard 2011; Bowers 2004; Caplan 2011.
- **Not obtained:**
  - Collins 2009 full text (lab link dead);
  - Price 2014 (UOW 403);
  - Awadhiya 2017 PDF (empty response);
  - Jain et al. 2021 *GeoHealth* (Central India fire 2001-2020) and Sahu et al. 2024 (Khandwa/North Betul MODIS trends), found by search but not opened; worth a look for MP-wide recurrence statistics.
