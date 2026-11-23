# Mapping where people collect forest produce in fire season, from satellites only: mahua, tendu and other people-in-forest proxies (scouting round 12, topic "mahua", 15-16 Oct 2026)

This note is about **mapping methods and data**. It does not repeat the mahua and tendu calendar or collector behaviour, which are in `human_fire_drivers.md` and `short_horizon_prediction.md`. It also skips the vegetation-type map (Roy 2015), SDPT and the teak-label sources (`teak_vs_mixed_fuel_fullread.md` B6), and the work on OSM, Microsoft roads, Open Buildings, walking time and livestock census (`access_paths.md`). Night lights are covered in `open_datasets.md` B7.

Status marks: **FULL** means I read the full text or the whole document; **PARTIAL** means I read some sections; **ABSTRACT ONLY** means I read the abstract or search snippets only. Anything marked [inference] is my own reasoning.

## Headline findings

1. **No published map of mahua or tendu trees exists at any scale useful to us.** I found no paper that maps *Madhuca* or *Diospyros* trees or stands from Sentinel-2, PlanetScope, LISS or hyperspectral data, in MP or anywhere else. Searches covered Google-type web search, Crossref, and species, sensor and state names. Consensus, OpenAlex and Semantic Scholar were rate-limited from here. The only "mahua maps" are climate-niche MaxEnt maps at km scale (B11), which are useless inside one sanctuary. The species-level remote-sensing work in India reaches only about 60-70% accuracy, even with AVIRIS-NG hyperspectral data (B12). So any mahua or tendu layer for Ratapani has to be built by us, as a proxy.
2. **We built that proxy, a hot-season green-up map, and it carries a real but modest fire signal (DATA, A1).**
   - Inputs: Sentinel-2 L2A from Planetary Computer, keyless, 2019-2026, 359 scenes. Each pixel's NDVI change from early March to 15 Apr-10 May, taken relative to the forest median that year, with same-season burned pixels masked.
   - Pixels that green up against the seasonal drying in at least half the years are "persistent flushers". This is the class tendu, mahua, achar, kusum and sal belong to.
   - The per-cell share of flusher pixels has Spearman **+0.27** with burn frequency 2017-2026 (2,939 forest cells).
   - It stays positive after controlling for:
     - access (distance to Open Buildings hamlets and buildings within 4 km): partial **+0.22**;
     - February and April greenness: **+0.21**;
     - elevation, slope and relief: **+0.12**;
     - all of these together: **+0.14**.
   - It is positive inside every vegetation class (+0.21 to +0.28).
   - Flusher cells also burn earlier: the change in green-up has Spearman **-0.31** with first-burn day.
   - It adds almost nothing once a cell's own fire history is in the model: leave-one-season-out AUC 0.701 becomes 0.702. Without history, AUC goes from 0.641 to 0.653.
   - So it is a **cold-start and all-MP feature**, not a fix for the Ratapani cell-model ceiling.
3. **A within-cell test shows only weak reverse causation (A1.6).** After a cell burns, its next-season flusher share rises by 0.008. Across cells the share ranges from 0.002 to 0.42, so post-fire resprouting explains little of the spatial pattern. A high-flush year does not predict more burning the next season (45.3% vs 46.1%).
4. **The official 2026 tendu phad list is online and machine-readable (B1, A3).**
   - The MP MFP Federation's `Phad2026.pdf` lists every lot (unit), primary society and phad (collection-centre village) in MP. It is in Krutidev legacy font, and I wrote a converter.
   - The four unions around Ratapani (Obaidullaganj, Raisen, Sehore, Bhopal) have **63 lots and 1,044 phad entries**.
   - Obaidullaganj alone has 15 societies and 167 phads, including Bhojpur, Ashapuri, Chiklod, Delawadi-area villages and "Mahuakheda".
   - Matching names to OSM villages placed 307 phads (266 unique points). Distance to the nearest phad does **not** add anything beyond distance to hamlets (partial +0.00).
   - Phads are simply villages. Their value is the **unit (lot) and society boundaries**, and the yearly bags per unit, not the points.
5. **A 10 m Sentinel-1/2 species map of a deciduous tree (sal) already exists for India (B6).** It reports 93% overall accuracy from random forest with phenology features. In Ratapani it flags only 0.5% of pixels, which are scattered and uncorrelated with our flusher map (rho 0.015). It is useful as a recipe and an off-the-shelf layer, not as a mahua map.
6. **Tendu bush management leaves a ground-level, not a canopy, signature (B2).** In the Gadchiroli plots, fire-only plots had **79 ± 76** root sprouts per 200 m², against 171 ± 126 in control plots and 366 ± 194 in pruned plots. Tendu leaves flush in late April to early May. [inference] A May (not April) Sentinel-2 or PlanetScope window, read at ground level under bare teak, is the right place to look for tendu bush patches.
7. **People-in-forest proxies beyond what we already have are weak.**
   - Cattle can be counted only from imagery at 40 cm or finer (B14).
   - Sentinel-2 grazing-pressure models need paddock ground truth.
   - No study links village- or cell-level mahua or tendu density to satellite fire counts. The only quantitative link I found is administrative: the World Bank and MP FD claim **~95% fewer fire incidents** in eight net-using villages, including **Budhni (Sehore), next to Ratapani** (B8). No satellite check of that claim exists, and we can run one.

---

## Part A. Our own tests (DATA, computed 15-16 Oct 2026)

Scripts are in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r12_mahua_code/` and outputs in its `out/` subfolder. They are scratch files, not copied into the project. Copy `out/flush_20m.tif`, `out/flush_cells.csv` and `out/phads_geocoded.csv` into `fsi/scouting/data/` if they are to be kept.

### A1. Hot-season green-up ("flusher") map vs first burns

**A1.1 Inputs.**
- **Imagery:** Sentinel-2 L2A from the Planetary Computer STAC, keyless with SAS tokens (`stac_list.py`). Tiles 43QGF, 43QHF and 44QKL, eo:cloud_cover < 20.
- **Windows each year 2019-2026:** Feb (1-28 Feb), Mar (1-25 Mar) and late Apr (15 Apr-10 May).
- **Scenes:** the 3 least-cloudy dates per window, all tiles; 359 items listed, about 9-18 tile-scenes used per window.
- **Grid:** reprojected onto the 20 m burn-label grid (EPSG:32643).
- **Indices and masking** (`greenup.py`):
  - NDVI from B04/B08 (read at the 20 m overview) and NDRE from B05/B8A.
  - SCL classes 4 and 5 only.
  - Processing-baseline ≥ 04.00 offset of −1000 applied.
  - Per-window median.

**A1.2 Feature construction** (`flush_cells.py`):
- **Forest mask:** Roy 2015 VTM classes 23/25/26/102/106/120/135, which removes agriculture (irrigated summer crops would look like "flush"), water and settlement.
- **Burn mask:** pixels with a same-season scar starting before day 135 are masked. Masked share of forest per year: 2019 21%, 2020 5%, 2021 7%, 2022 12%, 2023 7%, 2024 4%, 2025 10%, 2026 13%.
- **Anomaly:** `dNDVI_aprmar` minus the forest-wide median of that year, which removes the seasonal drying. The median raw change was −0.054 in 2019, −0.059 in 2020, −0.041 in 2021, −0.053 in 2022, −0.024 in 2023, +0.037 in 2024, −0.105 in 2025 and −0.007 in 2026.
- **Persistent flusher:** anomaly > +0.05 in ≥ 50% of observed years, needing ≥ 3 years.
- **Per 500 m cell:** `flush_frac` (share of flusher pixels), `dam_mean` (mean Apr−Mar anomaly), `daf_mean` (Apr−Feb), `dre_mean` (NDRE), `apr_ndvi` and `feb_ndvi`.
- Raster: `out/flush_20m.tif`, 5 bands.

**A1.3 Results** (`compare.py`). Forest cells are those with forest_frac ≥ 0.8 and ≥ 300 valid pixels: n = 2,939. The outcome is burn frequency = seasons with ≥ 1 ha burned out of 10 (2017-2026, `cell_season.csv`).

| Feature | Spearman with burn frequency | Spearman with first-burn day (burned cells) |
|---|---|---|
| `flush_frac` | **+0.273** | −0.174 |
| `dam_mean` (Apr−Mar anomaly) | +0.102 | **−0.305** |
| `dam_p90` | +0.230 | |
| `daf_mean` (Apr−Feb anomaly) | −0.082 | −0.282 |
| `dre_mean` | +0.126 | |
| `feb_ndvi` | +0.094 | +0.298 |
| `d_ob` (distance to hamlet) | +0.392 | −0.270 |
| `bld4` (buildings within 4 km) | −0.349 | |

By `flush_frac` decile (0 = least flush):

| Decile | flush_frac | burn freq | mean first-burn DOY | median d_ob (m) |
|---|---|---|---|---|
| 0 | 0.002 | 0.440 | 79.5 | 1,183 |
| 2 | 0.016 | 0.537 | 75.3 | 1,597 |
| 4 | 0.040 | 0.602 | 73.0 | 1,813 |
| 6 | 0.087 | 0.634 | 71.8 | 1,915 |
| 8 | 0.209 | 0.653 | 71.8 | 2,144 |
| 9 | 0.424 | 0.655 | 70.2 | 1,887 |

That is a 49% higher burn frequency from the bottom to the top decile, and first burns about 9 days earlier.

**A1.4 Confounds checked.**

| Control (rank partial correlation of `flush_frac` with burn freq) | partial rho |
|---|---|
| Feb NDVI | +0.281 |
| d_ob + bld4 (access) | +0.224 |
| Feb NDVI + Apr NDVI + d_ob + bld4 | +0.213 |
| Elevation + slope + relief (`topo_check.py`; DEM from `barrier_extra/dem_utm30.tif`) | **+0.118** |
| Topography + greenness + access | **+0.141** |

- Elevation is the main confound: rho with flush is +0.50, and with burn frequency +0.32.
- The quick-look map shows flushers along the banded sandstone ridges in the east. [inference] This is probably partly a real ecological link: tendu, achar and *Anogeissus* dominate rocky ridges, and Ratapani's ridges burn more.
- Within VTM classes, rho(flush_frac, burn freq) is +0.275 (teak-mixed, n = 1,826), +0.245 (dry deciduous, 523), +0.226 (moist deciduous, 246) and +0.209 (degraded, 308).

**A1.5 Robustness to the burn mask.** Same-season burns lower April NDVI, so burned cells should look less flushy, which biases the test against us. Masking them could instead leave only unburnable, greener pixels, which could bias it for us. The unmasked version (`flush_cells2.py nomask`, `compare_nomask.py`) still gives rho +0.178, with partials of +0.127 given access and +0.181 given greenness and access. So the sign is not a masking artefact.

**A1.6 Reverse causation** (`reverse_check.py`; 27,460 cell-years with ≥ 100 valid pixels).
- The within-cell, year-demeaned flusher share is +0.0040 in seasons after a burn against −0.0044 otherwise. That difference of 0.008 is about 9% of the mean share.
- Post-fire resprout flush exists, but it is small next to the cross-cell range.
- A within-cell high-flush year (top quartile) gives P(burn next season) of 45.3%, against 46.1% otherwise. The signal is spatial, not year-to-year.

**A1.7 Predictive value** (leave-one-season-out logistic regression, 10 seasons; outcome = cell burned ≥ 1 ha that season).

| Features | Mean AUC |
|---|---|
| Fire history (other seasons) + Feb/Apr NDVI + d_ob + bld4 + forest_frac | 0.7010 |
| … + flush_frac, dam_mean, daf_mean | 0.7020 |
| No history: NDVI + access + forest_frac | 0.6410 |
| No history + flush features | **0.6533** |

**A1.8 What this is and is not [inference].**
- The flusher class at 20 m is a mix of species that leaf out before the monsoon: *Diospyros*, *Madhuca*, *Buchanania*, *Schleichera*, *Terminalia* and *Shorea*. It also picks up riparian evergreen pixels.
- It is not a mahua map. Mahua crowns, about 12 m tall and 10-15 m across, cover about 1 pixel each.
- Separating mahua would need three things:
  - its distinct timing: leafless late Feb-Mar, flowering in Mar-Apr on bare crowns, a red-copper flush in early April, then green by late April;
  - a March "flower-on-bare-crown" brightness test;
  - about 50 labelled crowns from VHR imagery (Google Earth / Esri Wayback for Mar-Apr), which counts as "satellite only", not field data.

### A2. Patra et al. 2025 10 m Sal map clipped to Ratapani (`sal_window.py`)
- The map was read in place over HTTP (COG, EPSG:4326, about 10 m). Over the Ratapani box, 105,552 of 27.5 M pixels are "sal", about 1,056 ha.
- 1,746 of 3,614 cells have some sal pixels, but only 15 cells exceed 10%. The mean fraction is 0.48%.
- Spearman with burn frequency is −0.066, and with our flusher share +0.015.
- [inference] These are mostly scattered false positives. Sal is not a Ratapani dominant, and Roy 2015 has no sal classes inside the AOI. Do not use it as a feature here. For the all-MP model it is a valid 10 m species layer in the eastern sal belt (Mandla, Dindori, Balaghat, Shahdol, Sidhi).

### A3. Tendu phad list 2026: parsing, geocoding, test (`krutidev.py`, `phads.py`, `geocode_phads.py`, `phad_test.py`)
- **Parsing:**
  - `Phad2026.pdf` (MP MFP Federation, notice no. ते.प.(2026)-I dated 05/12/2025, 20 pp) was converted with pdftotext, then Krutidev→Unicode with my substitution table plus i-matra and reph reordering. Conversion checked on औबेदुल्लागंज, रायसेन, सीहोर, भोपाल, चिकलोद, गौहरगंज and बेगमगंज.
  - There are 63 lots in the 4 unions:

    | Union | Lots | Phad entries |
    |---|---|---|
    | Obaidullaganj | 15 (lots 247-261) | 167 |
    | Raisen | 25 | 408 |
    | Sehore | 15 | 284 |
    | Bhopal | 8 | 185 |

  - Obaidullaganj societies are Badi, Bamhori, Bhagdei, Diyawadi, Bhartipur, Chilwaha, Sultanpur, Vineka, Bagaspur, Chiklod, Tilendi, Bhojpur, Gauharganj, Barkheda and Dahod.
  - Sehore includes Budhni, Rehti, Shahganj and Lakdui.
- **Geocoding:**
  - Names were matched to 1,391 named OSM place nodes (Overpass via maps.mail.ru) by consonant-skeleton similarity, anchored to the matched society village (within 20 km). Thresholds: 0.85 when anchored, 0.92 when not.
  - 50 of 63 societies were anchored, and 307 of 1,044 phads matched (Obaidullaganj 46%, Sehore 31%, Raisen 30%, Bhopal 11%). Spot-check precision is about 85-90%.
  - Misses come from OSM's thin village coverage. Census-2011 village points (SHRUG or LGD) would lift this to most phads.
- **Test** (266 unique phad points):
  - Distance to the nearest phad: rho with burn frequency +0.156, with first-burn day −0.096.
  - Phads within 5 km: rho −0.165.
  - **Partial given d_ob + bld4: +0.001 and −0.019.** Burn frequency rises from 0.44 within 1 km of a phad to 0.62 beyond 6 km. That is the same "interior burns more" ramp as for hamlets.
- **Productivity numbers from the 2025 godown lot list** (`LOTLIST2526CAN.pdf`, actual / standard bags):

  | Lot | Unit | Actual bags | Standard bags |
  |---|---|---|---|
  | 257/2025 | Tilendi (unit 712) | 1,019 | 783.2 |
  | 259/2025 | Gauharganj (unit 713) | 1,451 | 1,108.6 |
  | 218/2025 | Sehore, Siddiqganj | 2,718 | 2,027.7 |
  | 219/2025 | Sehore, Metwada | 1,562 | 1,194.7 |
  | 222/2025 | Sehore, Ahmadpur | 1,608 | 1,429.5 |

  This list covers only godowned and cancelled lots. The full per-unit yields are in the lot list of the main tender, which is not posted now.

### A4. Farmland-tree crowns covering Ratapani (Brandt et al. 2024 data, B3)
- Zenodo record 11393984 (v2, 90 files) holds the full archive. Ratapani falls in grid id "86,25", file `ps2_PSScene_2018-2022_00086_00025_196_454_…`, inside `group_71.zip` (1.70 GB). Not downloaded.
- It covers trees on cropland, urban and bare land only (the WorldCover farmland class), not forest. It is useful only for the fringe villages, where much mahua stands on farm bunds. [inference] Our labels are forest, so the gain is small.

---

## Part B. Sources

### B1. MP State Minor Forest Produce (Trading & Development) Co-operative Federation: tendu patta pages, `Phad2026.pdf`, `LOTLIST2526CAN.pdf`, `LOTLISTCAN.pdf`, `MahuaandMFP.pdf`. http://www.mfpfederation.org/content/lot_list.asp **FULL** (documents; reachable from the container on 15 Oct 2026, though `human_fire_drivers.md` had found it unreachable)
- **What it shows:**
  - MP produces about **25 lakh standard bags** of tendu a year, about 25% of India's output. A standard bag in MP is 1,000 bundles of 50 leaves.
  - "Tendu plants are pruned in the months of February and March and the mature leaves are collected after about 45 days."
  - The phad list gives lot, union, society and every phad name for collection year 2026. The godown lot lists give actual and standard bags per lot for 2025.
  - The mahua document is an e-auction of MSP-procured mahua by district union, not spatial data.
- **Concrete action:**
  - **Thread 1, all-MP model:** the phad list is a statewide, yearly, free census of where tendu collection happens. Use the count of phads per forest division and per FSI grid square (after geocoding) as a division-level feature, `tendu_phads_per_km2_forest`.
  - **Thread 1, Ratapani:** use society/lot membership of the nearest village as a categorical feature or random effect.
  - **Thread 5:** each phad has a Phad Abhirakshak in April-May. The list gives their village names, ready for routing patrols.
  - Expected effect [inference]: small in Ratapani (A3 shows the points add nothing beyond hamlets). Possibly useful between divisions in the 87-division model, where tendu intensity varies several-fold.

### B2. Datye, Hiremath, Joshi & Lele 2023, "Silvicultural Practices in the Management of *Diospyros melanoxylon* (Tendu) Leaf Production: Options and Trade-offs", *Economic Botany* 77:1-18. https://doi.org/10.1007/s12231-023-09572-z (PMC10088608) **FULL**
- **Setting:** northern Gadchiroli, Maharashtra, March-May 2020; 10 × 20 m plots with three 2 × 2 m subplots for leaf counts.
- **Results:**
  - Root sprouts per 200 m²: pruning **366 ± 194** (n = 25), control 171 ± 126 (n = 25), pruning-with-fire 307 ± 201 (n = 7), fire-only **79 ± 76** (n = 7). Kruskal-Wallis χ² = 22.28.
  - Leaves per sprout did not differ between treatments: about 4 (s.d. 5.8), range 0-37.
  - Fire alone did not raise leaf production; pruning did.
  - Tendu leaves are shed in Feb-Mar and new leaves emerge in late April or early May. "Most tree species are … leafless in early April."
  - Collectible leaves are 10-30 cm long.
- **Concrete action (thread 3 fuel; thread 1 features) [inference]:**
  - Tendu "bush" patches are dense root-sucker stands below 1-2 m, flushing in **late April-May** under a still-bare teak canopy.
  - Add a **10-31 May** Sentinel-2 window to `greenup.py` and compute `dNDVI_may−mar`. Tendu bush should appear as a ground-level green-up in otherwise bare teak cells, a separate signal from the April crown flush of mahua.
  - Effort: one more run of the A1 pipeline, about 1 hour.
  - It also implies that collectors' fires are not agronomically needed. Thread 5 messaging can quote this.

### B3. Brandt, Gominski, Reiner, Kariryaa, Guthula, Ciais, Tong, Zhang, Govindarajulu, Ortiz-Gonzalo & Fensholt 2024, "Severe decline in large farmland trees in India over the past decade", *Nature Sustainability* 7:860-868. https://doi.org/10.1038/s41893-024-01356-0 **FULL**
- **Method:**
  - Heatmap-based CNN detection of individual tree-crown centres on country-wide mosaics: RapidEye 5 m (2010/11) and PlanetScope 3 m (2018-2022). The PlanetScope model used about 130,000 point labels over 918 areas; RapidEye about 100,000 over 791.
  - Mosaics were built from images between senescence and mid-greendown in deciduous areas, with sun elevation below 50° so trees cast shadows.
  - Crown segmentation used 52,000 Indian crown labels.
- **Accuracy:** F1 0.63-0.65 at a 20 m radius and 0.67-0.69 at 50 m (precision 0.83, recall 0.61). Trees with crowns under 10-20 m² are under-detected.
- **Results:**
  - 0.6 billion farmland trees, 0.6 trees/ha on average and up to 22/ha in Chhattisgarh.
  - About 11 ± 2% of large trees (about 96 m² crown) from 2010/11 had gone by 2018.
  - 5.3 M large trees (2.7/km²) vanished in 2018-2022.
  - Loss hotspots include eastern MP around Indore.
  - *Madhuca longifolia* is named as a remnant forest tree in farmland, but species are not mapped.
- **Data and code:**
  - Data: Zenodo 10978154 (example) and 11393984 (full); viewer https://rs-cph.projects.earthengine.app/view/tree. Non-commercial research use with Planet attribution.
  - Code: crown segmentation at https://doi.org/10.5281/zenodo.3978185 and https://github.com/sizhuoli/TreeCountSegHeight.
- **Concrete action:**
  - **Thread 1 fringe cells:** download `group_71.zip` (A4) and count large farmland crowns (confidence > 0.7, about 67 m²) within 2 km of each forest-edge cell, as `large_farm_trees_2km`. [inference] Large isolated farmland trees in MP are disproportionately mahua (and mango or neem near houses).
  - **Mahua mapping inside forest:** the same detector trained on our own March PlanetScope images of bare crowns could count large leafless crowns. Labels come from VHR imagery. Effort is high: Planet access plus labelling.

### B4. Wang, Song, Liddell, Morellato, Lee, Yang, Alberton, Detto, Ma, Zhao, Yeung, Zhang, Ng, Nelson, Huete & Wu 2023, "An ecologically-constrained deep learning model for tropical leaf phenology monitoring using PlanetScope satellites" (IG-ECAE), *RSE* 286:113429. https://www.osti.gov/servlets/purl/1913816 (accepted manuscript) **FULL**
- **Method:**
  - Candidate endmembers from 4-band PlanetScope:
    - leafy = intersection of the top 5% of NDVI, EVI, GLI and GRDI;
    - leafless = intersection of the bottom 5% of the same four indices;
    - shade = top 5% of the shadow index and bottom 5% of NIR.
  - An autoencoder (batch 1,024, learning rate 1e-5, stop when the change in MSE is below 5e-6) refines them under ecological constraints: NIR leafy > leafless > shade, and red leafless > leafy > shade.
  - Linear unmixing follows, with shade reassigned in proportion.
  - Images are cross-calibrated to BRDF-adjusted MCD43A1 by histogram matching.
- **Results:**
  - Deciduousness (leafless fraction) against WorldView-2 at 90 m patches: **r² = 0.89, RMSE 0.14** across 9 sites; within sites r² 0.45-0.91.
  - Against phenocams: r² 0.62-0.96.
  - The constraints raised r² from 0.36 to 0.89, against the unconstrained version.
  - The authors say 10 m Sentinel-2 is probably too coarse for crown work. Code was "to be shared on GitHub".
- **Concrete action:**
  - **Threads 1 and 3:** a per-pixel "leafless fraction" time series is what separates mahua from teak, since their leafless windows differ. With PlanetScope (Education and Research access, see `high_res_imagery.md` §2), compute the leafless fraction weekly from February to May. Mahua crowns are leafless from late Feb to mid-Mar and leafy by mid-April; teak is leafless from March to June.
  - **Fallback on Sentinel-2 [inference]:** the same index-guided endmember trick on S2 20 m data, using SWIR as an extra band to separate bark from litter.
  - Expected effect: a cleaner species proxy than A1, at the cost of Planet access.

### B5. Wang, Yang, Detto, Nelson, Chen, Guan, Wu, Yan & Wu 2020, "Multi-scale integration of satellite remote sensing improves characterization of dry-season green-up in an Amazon tropical evergreen forest", *RSE* (accepted manuscript, BNL-215923-2020). https://www.osti.gov/pages/servlets/purl/1618402 **PARTIAL** (abstract, methods and key results read)
- PlanetScope alone is unreliable for phenology. Cross-calibration to MODIS, then green-vegetation / non-photosynthetic-vegetation / shade unmixing, tracked the phenocam fraction of leafless crowns at Tapajós: **R² = 0.82** (2018) and 0.73 (2019); against field LAI, R² 0.81 and 0.72. Crown-level NPV trends varied widely between crowns.
- **Concrete action (thread 1):** if we use PlanetScope for crown phenology, do the MODIS (or HLS) cross-calibration step first. Otherwise sensor-to-sensor jumps will look like flush.

### B6. Patra, Bhumika & Thomas 2025, "High resolution distribution map of *Shorea robusta* in India", Zenodo 15086956 (dataset, 26 Mar 2025). https://zenodo.org/records/15086956 **PARTIAL** (dataset description read; raster read directly)
- **What it is:** a 10 m Sentinel-1/2 random-forest map built with "phenological characteristics and structural parameters". It reports 93% overall accuracy, trained and validated with ground truth in four states. The file is a 2.5 GB GeoTIFF, uint8 0/1, tiled 128 × 128, readable window by window over HTTP. Ratapani numbers are in A2.
- **Concrete action:**
  - **All-MP model:** add `sal_frac` per FSI square or division. Sal forests have a different fire regime from teak, so it is a cheap stratifier. Effort: 1 hour (window read per division).
  - **Method:** the same recipe (S1 + S2 phenology metrics + RF, ground truth from VHR imagery) is the most direct published template for a mahua or tendu classifier.

### B7. Tripathi, Behera & Roy 2017, "Optimized grid representation of plant species richness in India — Utility of an existing national database in integrated ecological analysis", *PLoS ONE* 12:e0173774. https://doi.org/10.1371/journal.pone.0173774 **FULL**
- This is the BCLL field database: **15,529 nested quadrats** (0.04 ha tree plots) over 100 vegetation types. At 1°, grids hold 6 to 137 plots. Maximum richness is 59 species per quadrat, 623 per 1° grid and 1,244 per 2° grid.
- Only grid-level richness tables are published. The figshare files are S1/S2 Figs and S1-S3 Tables in docx. **Plot-level species lists (which would give tendu and mahua presence) are not public.**
- **Concrete action:** none from public data. Ask IIRS for BCLL plot records in Raisen, Sehore and Bhopal (1:50k sheets 55E, 55F). Each plot with *Madhuca* or *Diospyros* present is a georeferenced label for A1, and a label from someone else's field data, not ours.

### B8. World Bank 2022, "Preventing forest fires: One flower at a time" (feature, 7 Dec 2022; Ecosystem Services Improvement Project P133803). https://www.worldbank.org/en/news/feature/2022/12/07/preventing-forest-fires-one-flower-at-a-time **FULL**
- **Claims:**
  - Nets were introduced in **8 MP villages**, including Kupwa (North Betul), Khatpura and **Budhni (Sehore)**. The MP FD has given free nets since **2020**.
  - About 5-6 mahua trees per family; about 100 kg of flowers per tree per season.
  - The price rose from Rs 15-20/kg to Rs 55-60/kg (MSP Rs 35/kg). Production doubled since 2018, and 100 quintals were exported in 2021.
  - DFO North Betul says fire incidents fell **by almost 95%**, and "an estimated 18,000 hectares" of fire were prevented over two years.
  - No measurement method is given, and no satellite data is used.
- **Concrete action (thread 5, with thread 2 data):** a ready evaluation for the patrol pilot.
  - Take scar area and first-burn dates within 3 km of Budhni-area villages and of the North Betul villages (scars exist only for Ratapani; for Betul use VIIRS/FSI points) for 2017-2019 against 2021-2026.
  - Use a difference-in-differences design against matched non-net villages.
  - If the 95% holds, mapping mahua trees is the targeting layer for nets. If not, that is a useful negative result for the department.
  - Effort: half a day for the Ratapani side.

### B9. Liu, Zhang, Wang, Ciais, Zhang, Penuelas, Nath, Jacquet, Wu, Ding, Li, Huang, Song, Ni & Niu 2025, "Mapping previously undetected trees reveals overlooked changes in pan-tropical tree cover", *Nature Communications* 16 (PMC12216519). https://doi.org/10.1038/s41467-025-60662-z **PARTIAL** (abstract, results and accuracy read)
- Automatic tree-cover mapping from Planet images under 5 m, 2015-2022, counting woody crowns > 5 m. Overall accuracy 97.31% and F1 0.977. Previously undetected tree cover is 17.31 ± 1.78% of the pan-tropical total. Data: Zenodo 10.5281/zenodo.14892757.
- **Concrete action:** none for species. It is a possible 3-5 m tree-cover mask for the all-MP fuel thread (3) if the Zenodo grid covers India at full resolution. Unchecked.

### B10. Kar, Lowe, Chaudhary & Dwivedi 2024, "Examining spatial and social characteristics of customary trees owned by villagers on public forestlands in Jharkhand, India", *Trees, Forests and People* 18:100661. https://doi.org/10.1016/j.tfp.2024.100661 **ABSTRACT ONLY** (ScienceDirect and the UGA thesis PDF both returned 403)
- In one village (Sahritola), households protect and manage **more than 18,000 trees** on public forestland, including asan, sal and **mahua**. Over 80% are individually owned and about 20% shared. Over 60% of households own 100-500 trees. Trees were GPS-mapped and analysed with Moran's I. The companion paper is *Forest Policy and Economics* 2025, 10.1016/j.forpol.2025.103442.
- **Concrete action [inference]:** confirms that every mahua tree has an owner and a fixed location, so the burning is at fixed points year after year. That supports a static per-cell mahua feature (A1) and the "same cells burn every March" pattern. Get the full text by hand for distance-from-house distributions. They would set the kernel width for `mahua_near_hamlet`.

### B11. Climate-niche maps of mahua and other NTFPs. **ABSTRACT ONLY**
- Saraf et al. 2024, *Environ. Monit. Assess.* 196:727 (10.1007/s10661-024-12876-9): MaxEnt for *Aegle*, *Buchanania*, *Madhuca*, *Phyllanthus* and *Terminalia bellirica* under RCP 2.6/8.5 for the 2050s and 2070s. Suitable area is projected to **shrink** for *Madhuca*. The BSIP PDF link returned 404.
- "Appraisal of the potential habitat distribution of *Madhuca longifolia* … pan-India", *Modeling Earth Systems and Environment* 2023 (10.1007/s40808-023-01913-0; not OA): MaxEnt, with the highest suitability in **Jharkhand** and a southward shift under all four RCPs for 2041-2060.
- **Concrete action:** none for Ratapani (km scale, climate only). For the all-MP model, a division-level mahua suitability score is a weak proxy at best. The phad and MSP procurement tables (B1) measure use directly and should be preferred.

### B12. Indian species-level hyperspectral mapping (AVIRIS-NG, ISRO-NASA 2016 campaign). **ABSTRACT ONLY**
- Shimoga and Mudumalai dry deciduous forest: "the accuracy achieved for species classification is moderate (60%) due to intermixing". *Anogeissus latifolia* dominates about 40% of the area and *Tectona grandis* 27.5% (ResearchGate 332369622).
- Mudumalai: 92.37% for forest *types* by SVM, but species failed under dense canopies (*J. Asia-Pacific Biodiversity*, S2287884X20300935; 403 from here).
- Bhitarkanika mangroves: AVIRIS-NG random forest 55%, rising to about 70% with vegetation indices and narrow bands (*Remote Sens.* 13:2027).
- **Concrete action:** a reality check. Even 5 m, 5 nm hyperspectral data gets about 60% on species in mixed dry deciduous forest. A Sentinel-2 "mahua" class will be a fuzzy proxy, so use it as a continuous feature, never as a hard mask.

### B13. Flowering and timing-window methods for species mapping. **ABSTRACT ONLY**
- *Acacia* invaders, KwaZulu-Natal (*JAG* 2020, S0303243420303548): Sentinel-2 indices give > 80% overall accuracy when the windows are the **peak flowering** month (September) and the green-up month (December) plus a dry-season scene. Window timing mattered more than the number of scenes.
- Orchard flowering index (*Remote Sens.* 18:1825, 2026, 10.3390/rs18111825): a modified flowering index built from in-situ spectra raised planted-forest F1 from **0.751 to 0.843** against tree crops.
- Lopes et al. 2016 (*RSE*; Central Amazon): unexpanded red young leaves have EVI similar to leafless crowns. **Mahua's copper-red flush will look "leafless" to NDVI** for 1-2 weeks [inference from the snippet].
- Drone flowering monitoring of tropical trees over 2 years: flowers at UA 95.3%, PA 85.8% (*ISPRS J.* S0924271623001399).
- **Concrete action (thread 1 mahua proxy):**
  - Add a **late-March "flower" window** (20 Mar-5 Apr). Mahua's cream flowers sit on bare crowns, then fall to the ground as a carpet under the tree.
  - Test a visible-brightness / red-edge index, (B03+B04)/2 − B02, or the orchard index, on crowns that are bare in Feb and green by early May.
  - In A1 terms, mahua = high `dam` (April green-up) + low `daf` (still bare in Feb relative to April) + a late-March brightness peak.
  - Effort: 2-3 hours for one more window. Validation needs about 50 VHR-marked crowns.

### B14. Other people-in-forest proxies.
- **Laradji, Rodriguez, Kalaitzis, Vazquez, Young, Davey & Lacoste 2020, "Counting Cows: Tracking Illegal Cattle Ranching From High-Resolution Satellite Imagery", arXiv 2011.07369. PARTIAL**
  - Maxar WorldView-3 at **40 cm**: 903 cattle images, with LCFCN and CSRNet counting.
  - Feasible only at sub-metre resolution and under open sky. [inference] Not usable under Ratapani canopy, and too costly.
- **"Estimating Grazing Pressure from Satellite Time Series Without Reliance on Total Production", *Remote Sens.* 17:3781 (2025). ABSTRACT ONLY** (MDPI 403)
  - Sentinel-2 time series trained on paddock grazing records, 10 m maps, 10-fold CV. It needs ground truth we do not have.
- **"Remote sensing assessment of vegetation and moisture stress along a seasonal cattle migration corridor in central India", *Environ. Monit. Assess.* 2026, 10.1007/s10661-026-15922-w. ABSTRACT ONLY**
  - Landsat 8/9 NDVI, SAVI, NDMI and LST with **GPS-collared cattle** on a central Indian migration route.
  - It means collar data on seasonal cattle movement exists for central India. Ask the authors for the track (who and where are not in the snippet).
- **Bandhavgarh forage study** (*J. Arid Environ.* 2011, S0140196311002746, ABSTRACT ONLY): cattle relied heavily on woody plants. **Pench grazing study** (2025, 10.1007/s44274-025-00216-8, ABSTRACT ONLY): a second-hand claim that more than 78% of forest area is under grazing pressure.
- **Night lights:** see `open_datasets.md` B7 and `short_horizon_prediction.md` §7. Nothing new. [inference] Black Marble at 500 m cannot see camps or collectors; any in-forest "light" in March-April is fire itself.
- **Concrete action:** no new layer from this group. Keep the livestock census and walking time (`access_paths.md`). Spend the effort on A1 extensions and B8 instead.

### B15. Species composition and fire, field evidence. **ABSTRACT ONLY**
- Saha & Howe 2003, *Ecology* 84:3118-3123 (10.1890/02-3051; not OA): a 1 ha plot burned annually by villagers for about 40 years (705 adults censused), against plots with fire excluded. Juveniles and adults are dominated by clonal root sprouters (tendu is one).
- A Panna TR fire-frequency biomass study (ResearchGate 363586810): *D. melanoxylon* is the **second-largest biomass contributor (8.1%)** across fire-frequency classes.
- **Concrete action [inference]:** tendu dominance is partly a product of repeated fire, which fits the small post-burn flush effect in A1.6. It strengthens the case for treating `flush_frac` as "site of the human fire regime" rather than as a cause.

### B16. Searched, nothing usable found
- Published mahua or tendu tree maps, or NTFP potential maps from satellite, for MP, Chhattisgarh, Jharkhand or Odisha. Only the Gujarat GIS/logistic NTFP model (*Agroforestry Systems* 2025, 10.1007/s10457-025-01186-9, ABSTRACT ONLY) turned up, with 65.43% and 70.37% accuracy.
- Bhuvan or FSI species layers.
- Odisha Kendu Leaf portal map (kenduleaves.odisha.gov.in; connection reset from here; the map is made by ORSAC).
- Any study with numbers linking mapped mahua or tendu density to fire occurrence.
- Palash (*Butea*) flowering detection from satellite.

---

## Datasets and code

| Item | Where | Resolution, years | Access | Use |
|---|---|---|---|---|
| Hot-season flusher map (ours) | scratch `r12_mahua_code/out/flush_20m.tif` (5 bands), `flush_cells.csv` | 20 m; 2019-2026 multi-year | built here, from Planetary Computer S2 L2A (keyless) | thread 1 static feature `flush_frac`, `dam_mean`, `daf_mean`; thread 3 fuel strata |
| Per-year composites | scratch `out/gu_<year>.npz` (Feb/Mar/Apr NDVI and NDRE medians) | 20 m | built here | extra windows, year-specific features |
| MP MFP Federation phad list 2026, godown lot lists | http://www.mfpfederation.org/content/Phad2026.pdf, `LOTLIST2526CAN.pdf`, `LOTLISTCAN.pdf` | all MP, lot / society / phad | public PDF (Krutidev font) | all-MP division feature; patrol contacts |
| Parsed and geocoded phads (4 unions) | scratch `out/phads_ratapani_unions.csv` (1,044 rows), `out/phads_geocoded.csv` (307 located) | village points | built here | phad-distance features; society IDs |
| Krutidev→Unicode converter | scratch `r12_mahua_code/krutidev.py` | n/a | ours | any MP FD legacy-font PDF |
| Sal 10 m map (Patra et al. 2025) | Zenodo 15086956, `Shorea_robusta_Distribution_India_10m.tif` (2.5 GB COG) | 10 m, about 2023 | open; HTTP window reads work | all-MP stratifier; Ratapani clip in scratch `out/sal_ratapani.tif` |
| Farmland trees India 2018-2022 (Brandt 2024) | Zenodo 11393984, Ratapani in `group_71.zip` (1.70 GB) | PlanetScope crown points | non-commercial research | fringe mahua proxy |
| Crown segmentation / counting code | zenodo 3978185; github.com/sizhuoli/TreeCountSegHeight | | open | mahua crown counting on March imagery |
| Pan-tropical tree cover < 5 m (Liu 2025) | Zenodo 14892757 | < 5 m | open | fuel/tree mask (unchecked) |
| BCLL plot database (IIRS) | bis.iirs.gov.in; on request | 15,529 × 0.04 ha plots | request | mahua/tendu presence labels |
| OSM place nodes | Overpass at maps.mail.ru (the other mirrors failed) | points | open | geocoding (weak coverage) |
| IG-ECAE (Wang 2023) | code "on GitHub upon acceptance" (not found) | PlanetScope 3 m | method | leafless-fraction series |

## Ranked action list (gains are my estimates [inference] unless measured)

| # | Action | Thread | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|---|
| 1 | **Add `flush_frac`, `dam_mean`, `daf_mean` as static cell features and as a cold-start prior** | 1 | `out/flush_cells.csv`; join on `cell_id`. For the all-MP model, rerun `greenup.py` + `flush_cells.py` per division on the VIIRS grid (same windows; mask with VNP64/FSI points instead of scars) | Measured: LOSO AUC +0.012 without history, +0.001 with it. Expect a small recall gain for cold-start cells (`cold_start_cells.md`) and for all-MP squares without fire history | Low (Ratapani: done; MP: about 1 day of compute) |
| 2 | **Test the "95% fewer fires" net claim at Budhni and in North Betul with our scars/VIIRS** | 5 (with 2) | Village points (OSM / Open Buildings); burned ha within 3 km, 2017-19 vs 2021-26; difference-in-differences against matched villages | Decides whether mahua mapping plus nets is worth piloting | Low-medium (half a day) |
| 3 | **Add a May window (10-31 May) and a late-March flower window (20 Mar-5 Apr)** to separate tendu bush (ground flush under bare teak) from mahua (April crown flush, March flowering) | 1, 3 | `stac_list.py` / `greenup.py` with extra windows; features `dNDVI_may−mar`, `bright_mar` = (B03+B04)/2 − B02 anomaly | Turns one mixed "flusher" class into two species proxies; unknown gain | Low (2-3 h compute) |
| 4 | **Label about 50-100 mahua crowns and about 50 tendu bush patches on Google Earth / Esri Wayback March-April VHR imagery**, then train an RF on the per-pixel phenology stack (Patra 2025 recipe) | 1, 3 | 20 m features from all windows plus SWIR; labels from VHR imagery only; output a mahua probability map | The first real mahua layer; enables thread 5 net targeting | Medium (1-2 days of labelling) |
| 5 | **All-MP: phads per km² of forest per division, plus sal_frac** | 1 (87 divisions) | Phad2026 statewide, parsed with `phads.py` (drop the union filter), geocoded to census villages; Sal map window reads | A between-division intensity term; per-division models are local, so it may matter only in pooled or hierarchical variants | Medium (geocoding is the bottleneck) |
| 6 | Control for elevation and relief in any use of `flush_frac` | 1 | `topo_cells.csv` | Avoids crediting ridges to "mahua"; partial drops from 0.27 to 0.12-0.14 | Trivial |
| 7 | PlanetScope leafless-fraction series (IG-ECAE) for crown-level mahua timing | 1, 3 | Planet E&R access; weekly Feb-May; MODIS/HLS cross-calibration first (B5) | Best possible species proxy without field data | High |
| 8 | Fringe farmland mahua: count large farm crowns within 2 km (Brandt data) | 1 | `group_71.zip`, confidence > 0.7 | Small (forest labels) | Medium (1.7 GB download) |
| 9 | Ask IIRS for BCLL plots, and the Raisen/Sehore unions for unit boundaries and bags per unit | 1 | Formal request | Labels and productivity; slow | Low for us, slow turnaround |
| 10 | Do not pursue: night lights, cattle counting from imagery, MaxEnt mahua maps, phad-point distance in Ratapani | n/a | n/a | Measured or argued null | n/a |

## Reading status

- **FULL (7):**
  - MP MFP Federation documents (phad list 2026, lot lists, tendu page);
  - Datye et al. 2023;
  - Brandt et al. 2024;
  - Wang et al. 2023 (IG-ECAE);
  - Tripathi et al. 2017;
  - World Bank 2022 feature;
  - Zenodo record for Brandt data (file inventory).
- **PARTIAL (4):** Wang et al. 2020; Patra et al. 2025 dataset; Liu et al. 2025; Laradji et al. 2020.
- **ABSTRACT ONLY (about 14):**
  - Kar et al. 2024; Saraf et al. 2024; MESE 2023 mahua MaxEnt;
  - AVIRIS-NG Shimoga, Mudumalai and Bhitarkanika;
  - *Acacia* KZN 2020; orchard flowering index 2026; Lopes 2016; drone flowering 2023;
  - grazing pressure 2025; central India cattle corridor 2026;
  - Saha & Howe 2003; Panna fire-biomass study; Gujarat NTFP 2025.
- **Unreachable:**
  - ScienceDirect (403);
  - the UGA thesis (bot wall);
  - the BSIP PDF (404);
  - the Odisha KL portal (connection reset);
  - Consensus (monthly quota used up);
  - OpenAlex and Semantic Scholar (rate-limited).
