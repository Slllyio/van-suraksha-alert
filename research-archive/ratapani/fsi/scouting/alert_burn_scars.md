# Burn scar for each fire alert: published methods, datasets and tools

**For:** the "Burn scar for every fire alert" thread (`fire-alert-scars/`).
**Compiled:** 14 Oct 2026, from web and Consensus paper searches.

**Notes already cover these, so they are not repeated here:**
- FSI's method: `fsi/burnt_area_method.md`.
- Prithvi-EO-2.0, PlanetScope (Vadrevu), NRSC Sariska, GABAM v3, MCD64A1/FireCCI51 as benchmarks: `research/fire-prediction-landscape.md` §8.

**What the thread has built so far:**
- `alert_scar.py` builds a 3 km Sentinel-2 + Landsat chip for each alert. It compares the last clear look before the alert with the first clear look after it.
- A pixel counts as burned when its NBR drop beats the chip's median drop and NIR darkens. A later look must confirm the drop has held.
- The scar is every connected patch that touches the alert disk.
- `match_scars.py` links alerts to the season scar rasters. `live.py` keeps a running ledger of alerts and their scars.
- Current label quality: about 83% precision and 71% recall.

**How to read this file:**
- "Use for us" lines are my suggestions.
- Anything marked *(inference)* is my reasoning and is not stated in the source.
- Accuracy terms:
  - **CE** (commission error): share of mapped burns that are false.
  - **OE** (omission error): share of real burns that were missed.
  - **Dice:** overlap between the map and the reference, from 0 to 100%.

---

## A. Algorithms that grow burned area from active-fire seeds

**A1. MODIS MCD64A1 Collection 6 algorithm (Giglio et al. 2018)**
- Link: [paper, RSE 217:72-85](https://doi.org/10.1016/j.rse.2018.08.005) · [C6.1 user guide](https://LPDAAC.USGS.GOV/documents/1006/MCD64_User_Guide_V61.pdf)
- Uses dynamic thresholds on a SWIR burn index plus a "temporal texture" measure.
- Cumulative active-fire maps choose the burned and unburned training pixels for each tile and set the prior probabilities.
- Each pixel gets a burn day: 44% match the active-fire day exactly, and 68% fall within 2 days.
- Use for us: copy the logic, not the product. Train thresholds locally from alert pixels against pixels with no alert in the same chip and season, instead of using one fixed relative-dNBR cut.

**A3. FireCCI small-fire algorithm, first version (Bastarrika/Roteta et al. 2019)**
- Link: [RSE 2019](https://consensus.app/papers/details/2e633030fb0f5974a925410d90ee2ea2/?utm_source=claude_desktop)
- Runs in two passes on Sentinel-2 SWIR and NIR at 20 m, seeded by MODIS active fires:
  - pass 1 makes a rough burned map;
  - statistics from that map, per tile, set the thresholds for pass 2.
- Africa 2016 accuracy:

  | Product | Dice | OE | CE |
  |---|---|---|---|
  | This algorithm | 77% | 26.5% | 19.3% |
  | MCD64A1 | 53.6% | 59.6% | 20.4% |

- Use for us: this two-pass, tile-statistics design is the closest published match to `alert_scar.py`. Pass 2 is what we lack: we use the chip median as the background instead of statistics learned from confirmed burns.

**A4. FireCCISFD20, the Sentinel-2 small-fire dataset for Africa, 2019 (Chuvieco et al. 2022)**
- Link: [STOTEN 2022](https://consensus.app/papers/details/3d036c528d42510b88e89816029bdeeb/?utm_source=claude_desktop) · [ESA release note](https://climate.esa.int/en/news-events/new-version-of-small-fire-database-released)
- Same algorithm as A3, but with Sentinel-2 A+B (one look every 5 days instead of 10) and VIIRS 375 m seeds instead of MODIS.
- Accuracy: OE 8.5%, CE 15.0%, Dice 87.7%. 92.5% of fires were detected within 10 days.
- Use for us: moving from MODIS to VIIRS seeds and doubling the revisit cut omission from 26% to 8.5%. That supports seeding from VIIRS and using every Sentinel-2 + Landsat look, which we already do.

**A5. Sentinel2BAM, global Sentinel-2 + VIIRS/MODIS in Earth Engine (Bastarrika et al. 2024)**
- Link: [ISPRS J. 218:232-245](https://consensus.app/papers/details/1e4c30aab40e500cba27198ef1631628/?utm_source=claude_desktop)
- A Random Forest is trained by active fires on 5-day NBR composites. A time-series, object-based step then fixes the scars each quarter.
- Accuracy: CE 10.3% / OE 7.6% (EMSR21) and CE 22.5% / OE 13.4% (Landsat GlobalL105); global Dice 81.8% (per Padilla 2026). For comparison, FireCCI51 has OE 46.5% and MCD64A1 has OE 53.1%.
- Tropical forest fires have higher CE, mostly from cropland confusion.
- I found no public code link.
- Use for us: the best template for a per-alert classifier. Train a small random forest per season with alert pixels as "burned" and no-alert forest as "unburned", then apply it inside each alert chip. Our crop and forest edges are the expected source of false scars.

**A6. Global near-real-time Sentinel-2 + VIIRS burned area (Padilla et al. 2026)**
- Link: [Fire 2026](https://consensus.app/papers/details/bcad8956830f58d28ddb9bc9ef74e90b/?utm_source=claude_desktop)
- A neural network predicts a burn probability time series. It is combined with the density of active fires in space and time.
- Accuracy gets better the longer you wait:

  | Wait after the fire | Dice |
  |---|---|
  | 0 days | 82.7% |
  | 5 days | 84.7% |
  | 10 days | 85.4% |
  | 45 days (monthly) | 87.2% |

- Use for us: confirms that "alert density near a pixel" is a strong feature. It also gives a model for issuing a provisional scar now and a firmer one 5-10 days later, like our `waiting` status.

**A7. Sentinel-2 time-series burned area with several active-fire sources (Liu et al. 2023)**
- Link: [RSE 2023](https://consensus.app/papers/details/bba964136daf54dda5f02fce9acfed10/?utm_source=claude_desktop)
- Finds candidates at three time scales: one date, two dates, and a short series.
- Candidates are confirmed with MODIS, VIIRS, Landsat and Sentinel-2 active fires. A year-on-year series rescues candidates that no active fire confirmed.
- About 7-9% better Dice than FireCCISFD20 and the US Landsat product (LBA_CU).
- Use for us: the year-on-year check is a cheap test against leaf fall. A real scar departs from the same date in other years; normal leaf fall does not.

**A8. Forest burned area at 10 m with active fires and the EBAI index (Ren et al. 2026, Amur basin)**
- Link: [JAG 2026](https://consensus.app/papers/details/64eb9757cc855d5dadb92926005cbaa8/?utm_source=claude_desktop)
- Targets false alarms from shadows and phenology directly. Uses MIRBI, NBR2 and a B11/B12 index as features.
- EBAI scores a sudden departure from pre-fire reflectance followed by a short-lived post-fire anomaly.
- Accuracy: CE about 8%, OE 9-13%, Dice about 90%.
- Use for us: add MIRBI and NBR2 to the chip test, and use the "sudden drop, then partial recovery" shape to separate burns from leaf fall, which declines gradually. *(inference: that leaf fall is gradual in teak)*

**A9. Combined Landsat-8 + Sentinel-2 burned area (Roy et al. 2019)**
- Link: [RSE 2019](https://consensus.app/papers/details/e9a56069c2d3529c9fc8c1a2657967ef/?utm_source=claude_desktop)
- A random forest change regression on harmonised, BRDF-adjusted reflectance.
- Temporal consistency checks remove non-fire changes. Region growing recovers missed edges.
- Gives a burn day for each pixel. Its dates average 3 days later than MCD64A1's.
- Results: OE 0.24, CE 0.06.
- Use for us: region growing from the alert-disk core is a principled version of our "connected patch touching the disk". Use a looser threshold for growing than for seeding.

## B. Ready-made products and tools

**B1. BAMT, Burned Area Mapping Tools for Earth Engine (Roteta, Bastarrika et al. 2021)**
- Link: [Remote Sensing 13(4):816](https://consensus.app/papers/details/da62a1f760675bd3a38c4a90eb246507/?utm_source=claude_desktop)
- Four scripts for the Earth Engine Code Editor:
  - supervised burned-area mapping;
  - two stratified sampling tools for choosing validation scenes and dates;
  - a "reference perimeter" tool.
- CE and OE were under 12% in Australia.
- Use for us: the sampling and reference-perimeter tools are the quickest way to build an independent validation set better than our 400 points. Good for one season.

**B2. FireCCIS2.v1, the first global Sentinel-2 burned area at 20 m (EGU 2026 abstract)**
- Link: [EGU26-16760](https://meetingorganizer.copernicus.org/EGU26/EGU26-16760.html)
- Over 8 Mkm² burned in 2023, more than double MCD64A1 and VNP64A1.
- No accuracy figures, download link or minimum mapping unit yet.
- Use for us: once released, an independent 20 m comparison for 2023 over Ratapani. Check back.

**B3. GlobFire, fire events built from MCD64A1 (Artés et al. 2019, JRC/GWIS)**
- Link: [Earth Engine final perimeters](https://developers.google.com/earth-engine/datasets/catalog/JRC_GWIS_GlobFire_v2_FinalPerimeters) · [daily perimeters](https://developers.google.com/earth-engine/datasets/catalog/JRC_GWIS_GlobFire_v2_DailyPerimeters)
- A graph of burned patches in space and time gives each fire an ID, a start and end date, and daily perimeters. Covers 2001-2021.
- Use for us: its graph method is how to give each fire event its own ID, which we can apply to our 20 m scars. Its 500 m perimeters are too coarse to use directly.

**B4. Global Fire Atlas (Andela et al. 2019) and its VIIRS update**
- Link: [ESSD 2019](https://essd.copernicus.org/articles/11/529/2019/) · [Earth Engine community catalog](https://gee-community-catalog.org/projects/gfa/) · [EGU2024 slides (VIIRS version)](https://sense4fire.geo.tu-dresden.de/images/documents/EGU2024_Andela_Friday_BG87.pdf)
- Splits MCD64A1 into individual fires with ignition point, size, duration, and spread speed and direction. Covers 2003-2016, later extended to 2023.
- The slides say a version built on VIIRS 375 m active fires detects understory fires better.
- Use for us: borrow its ignition and spread logic to order alerts within one event, so the first alert becomes the ignition and later ones show spread.

**B5. FEDS, Fire Events Data Suite (Chen et al. 2022, NASA)**
- Link: [Sci. Data 9:249](https://doi.org/10.1038/s41597-022-01343-0) · [live perimeter service](https://gis.earthdata.nasa.gov/image/rest/services/FireTracking/Fire_Events_Data_Suite_Fire_Perimeters_NRT/MapServer/0)
- Clusters VIIRS 375 m pixels into fire objects every 12 hours. Each object gets an ID, a perimeter, an active front and new fire pixels.
- Covers only the US and Canada, and only clusters over about 4 km². NASA calls it experimental.
- Use for us: the closest existing "alert ID → polygon" system. Its clustering code is a model for our 1 km same-day event grouping, which could be extended across days *(inference)*. The perimeters themselves don't fit our under-3 ha fires.

## C. Deep learning models and training sets

**C1. Prithvi-EO-2.0-300M-BurnScars model card and the HLS Burn Scars dataset**
- Link: [model](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M-BurnScars) · [dataset](https://huggingface.co/datasets/ibm-nasa-geospatial/hls_burn_scars)
- 6 HLS bands. 804 chips of 512×512 from the contiguous US, 2018-2021, labelled from MTBS perimeters.
- Burned-class test IoU 87.5%. Model Apache-2.0; dataset CC-BY-4.0. Single-date (post-fire only) input.
- Use for us: a starting checkpoint. US training scars are large, so expect poor recall on our small scars until it is fine-tuned on Ratapani chips *(inference)*.

**C2. CaBuAr, California burned areas (Politecnico di Torino, 2023/24)**
- Link: [arXiv 2401.11519](https://arxiv.org/html/2401.11519v1) · [Hugging Face](https://huggingface.co/datasets/DarthReca/california_burned_areas/raw/af1578503fcc93744e3a101a9c9eafb2a56b692c/README.md)
- Pre- and post-fire Sentinel-2 L2A pairs at 20 m, 2015-2022, with CAL FIRE masks. Baselines: index thresholds, U-Net and SegFormer.
- Use for us: extra pre-training pairs for a two-date model. Same large-fire bias as C1.

**C4. Two-date U-Net with attention (BiAU-Net, Sui et al. 2024)**
- Link: [JAG 2024](https://consensus.app/papers/details/27bdfb8fa04451c0a158339a8c6b0687/?utm_source=claude_desktop)
- Takes pre- and post-fire Sentinel-2 as two inputs. Its loss function is designed around class imbalance, edges and small scars.
- Trained at 1 site, it generalised to 5 continents. F1 was 19.9% better than FireCCI51, averaged over 5 sites. Code: github.com/TangSui122/Bi-temporal-Wildfire-Burnt-Area-Detection.
- Use for us: the right design for alert chips, because we already have pre and post images. Better suited than single-date models (Knopp 2020, Hu 2021).

**C5. Single-date U-Nets (Knopp et al. 2020; Hu et al. 2021)**
- Link: [Knopp 2020](https://consensus.app/papers/details/5704078b298f5ec6a0c24386a3acc0a0/?utm_source=claude_desktop) · [Hu 2021](https://consensus.app/papers/details/b0bf08adf5e35969b7e291c2dea4bba6/?utm_source=claude_desktop)
- Use only the post-fire image. Hu found classic machine learning beat deep learning on the one scattered, patchy test fire (Trängslet, kappa about 0.88); deep learning won at the other two sites.
- Use for us: a warning sign. Our fires are scattered litter burns, so a pixel random forest may match a CNN.

## D. Small fires, understory fires and leaf-fall confusion

**D1. Small fires in Africa (Ramo et al. 2021, PNAS)**
- Link: [PNAS](https://consensus.app/papers/details/cf7e2875344e5f26bfdd72c65bc4ee85/?utm_source=claude_desktop)
- Sentinel-2 found 80% more burned area than MODIS. Fires under 100 ha burned 2.02 Mkm²; MODIS caught only 0.13 Mkm² of that.
- Use for us: grounds for not trusting any 500 m product in Ratapani.

**D2. MODIS accuracy by fire size (Campagnolo et al. 2020, Cerrado)**
- Link: [RSE 2020](https://consensus.app/papers/details/15625c45ecdf52c39ef7b7034618e5e9/?utm_source=claude_desktop)
- Dice is about 80% for fires over 500 ha but under 36% for fires under 250 ha.
- Use for us: always report our accuracy by scar size class. Validation that ignores size is misleading.

**D3. Small forest fires under 25 ha (Qarallah et al. 2022, Jordan)**
- Link: [Forests 2022](https://consensus.app/papers/details/730ff1ef0d1b5c1786eaac1c68fb0a46/?utm_source=claude_desktop)
- Sentinel-2 beat Landsat-8 by 7-26% in overlap with field perimeters. Mixed edge pixels made up 8-14% of the scar for Sentinel-2 and 31-52% for Landsat.
- dNBR severity classes were under 70% accurate.
- Use for us: for scars under 3 ha, weight Sentinel-2 above Landsat. Don't trust severity classes on small scars.

**D5. Low-severity understory fires under canopy (Gibson et al. 2020; Tienaho et al. 2025)**
- Link: [Gibson RSE 2020](https://consensus.app/papers/details/775dd5f7d9de5cf3aedcefbfb20d32b3/?utm_source=claude_desktop) · [Tienaho 2025](https://consensus.app/papers/details/9af73728141e5c9d823aac743c45564d/?utm_source=claude_desktop)
- Gibson: dense canopy and steep terrain cause under-prediction of burnt understory.
- Tienaho: dense canopy hides surface fires from dNBR. Breakpoint analysis of the NBR time series found 4 of 7 (missed sites averaged 72% canopy cover vs 53%).
- Use for us: explains part of our `no_scar_seen` cases. Litter fires before leaf flush under teak canopy may not show *(inference)*. Try a breakpoint test on the full NBR series of each chip.

**D7. Indonesia national monthly Sentinel-2 burned area (Gaveau et al. 2021, 2026; Vetrita et al. 2024)**
- Link: [ESSD 2021](https://consensus.app/papers/details/eab265af9f3e577cad4452fcfc4ce12f/?utm_source=claude_desktop) · [PLOS One 2026](https://consensus.app/papers/details/05f29785678b5d368f061961c102842a/?utm_source=claude_desktop) · [Vetrita 2024](https://consensus.app/papers/details/fa1455783c075c5294fe453ee27c2a3a/?utm_source=claude_desktop)
- Random forest on Sentinel-2 in Earth Engine, with FIRMS hotspots to cut false positives. Monthly 20 m maps published on Nusantara Atlas.
- 2021 accuracy:

  | Map | User's accuracy | Producer's accuracy |
  |---|---|---|
  | Sentinel-2 map | 97.9% | 75.6% |
  | Official Landsat map | 95.1% | 49.5% |

- Use for us: the nearest operational example of what FSI could run. It shows hotspots are used to filter, not to delineate.

**D8. Thai deciduous forests (Suwanprasit et al. 2024 and others)**
- Link: [Sci. Rep. 2024 (OBIA)](https://consensus.app/papers/details/a0e346c548c05c249f5df18660dda70a/?utm_source=claude_desktop) · [Mae Ka RBR study](https://ijg.journals.publicknowledgeproject.org/index.php/journal/article/view/5138)
- Object-based mapping reached 85% accuracy. Monthly RBR reached 90.6% overall accuracy.
- None of these tested leaf-shedding confusion explicitly.
- Use for us: try RBR or RdNBR alongside dNBR. No published leaf-fall fix was found for dry deciduous forest. That is a gap we could fill.

## E. India-specific studies

**E1. Chandel et al. 2022, 30 m burned area in Central India (forest and farmland)**
- Link: [Front. For. Glob. Change, doi 10.3389/ffgc.2022.933807](https://doi.org/10.3389/ffgc.2022.933807)
- FIRMS points capture under 20% of the burned area. A Landsat random forest reached over 80% in April.
- Accuracy is lower in Feb-Mar than in Apr-May, and varies with the sun's azimuth. Full text: this applies to agricultural burns; forest-burn accuracy did not vary systematically, and hillshade did not consistently help. "FIRMS" here is MODIS 1 km.
- Spectral indices reduce commission error. The exact site is not in the abstract.
- Use for us: the closest landscape match. It supports the index set (NDMI, MIRBI, NDVI, NBR most important) and a "leaf-fall forest" negative class. It does not confirm a sun-angle cause for forest scars, so skip the hillshade covariate. See `alert_burn_scars_fullread.md`.

**E2. Melghat fire-frequency mapping (Mani & Varghese 2022)**
- Link: [JTFE 2022](https://journals.sjp.ac.lk/index.php/JTFE/article/view/5597)
- Landsat scars for 2014-2020, January to June. 35% of the reserve never burned and about 0.5% burned every year.
- Used to plan watchtowers: 13 kept and 27 proposed.
- Use for us: a model for an officer-facing product built from scar frequency.

**E3. Uttarakhand, Himalaya (Bar et al. 2020; Mamgain et al. 2022, 2023; Singh et al. 2026)**
- Link: [Bar 2020](https://consensus.app/papers/details/b5d0fac102c758f0bcc9f867fe7409c0/?utm_source=claude_desktop) · [Mamgain 2023 fuzzy](https://consensus.app/papers/details/701bdbd81cbf567eba72ee5f5b6d7ce1/?utm_source=claude_desktop) · [Singh 2026](https://consensus.app/papers/details/849ba34391b75e84a4c57d91babc19fe/?utm_source=claude_desktop)
- Fuzzy combination of Landsat-8 and Sentinel-2:

  | Input | Accuracy against active-fire points |
  |---|---|
  | Landsat-8 only | 66% |
  | Sentinel-2 only | 60% |
  | Both combined | 80% |

- Singh: 74-92% of MODIS/VIIRS points fall in Sentinel-2 dNBR burnt classes.
- Use for us: combining sensors helps. But validating against active-fire points is circular, so don't copy that method.

**E4. Other Indian sites: Chandoli (Lohar et al. 2021), Mizoram (Gupta et al. 2024), Konkathi et al. 2021**
- Link: [Lohar 2021](https://consensus.app/papers/details/8ecd3a0324595cb4850f62abd409fda7/?utm_source=claude_desktop) · [Gupta 2024](https://consensus.app/papers/details/5d5a6a6c47d15bb7b9c4094456681dea/?utm_source=claude_desktop) · [Konkathi 2021](https://consensus.app/papers/details/f39e7316caa75e8eb0e0f2cfdec37ee7/?utm_source=claude_desktop)
- Chandoli: object-based Sentinel-2 mapping was 84% accurate against a 194 ha forest-department figure.
- Mizoram: RdNBR AUC 85%, RBR 84%, dNBR 82%.
- Konkathi: RdNBR also beat dNBR.
- Use for us: RdNBR, which scales the drop by pre-fire NBR, is worth testing. Low-NBR leafless teak in March may otherwise under-score *(inference)*.

- **Searched, nothing found:** no Sentinel-2 burned-area study for Similipal 2021 or for Achanakmar.

---

## Ranked top 5 to try (gains are my estimates unless noted)

1. **A classifier trained on alert seeds instead of a fixed threshold** (A3, A5 and A1 logic)
   - Each season, train a random forest on dNBR, NBR2, MIRBI, RdNBR, the NIR drop and the date-of-year anomaly.
   - Positives: pixels at alert centres that already pass the current test. Negatives: no-alert forest from the same dates.
   - Run it inside each chip as pass 2 of the two-pass design.
   - Expected gain: recall from about 71% to about 80% at similar precision. Published two-pass and random-forest designs reach OE 8-13% against our about 29%, though in larger fires *(inference)*.

2. **Region growing from the alert core, with a stricter seed and a looser grow threshold** (A9, A1)
   - Expected gain: recovers scar edges and partly burned pixels. Mainly improves the area estimate for scars under 3 ha, and modestly improves recall *(inference)*.

3. **Leaf-fall and shadow filters** (A7 year-on-year anomaly, A8 sudden-drop shape, E1 sun-angle covariate)
   - Require the post-fire NBR to fall below this pixel's own NBR on the same day of year in other years, and the drop to be sudden.
   - Expected gain: the biggest precision gain in Jan-Feb and on north-facing slopes. Perhaps 83% to about 88% overall *(inference)*.

4. **Event IDs across days** (B3 GlobFire graph, B5 FEDS clustering, B4 ignition logic)
   - Link alerts across consecutive days within about 1.5 km and their scars into one event, with an ignition alert, spread order and a final polygon.
   - Expected gain: no accuracy change. It gives the alert→polygon ledger officers need, and stops double-counting multi-day fires.

5. **Fine-tune a two-date CNN on Ratapani chips** (C4 BiAU-Net design, C1 Prithvi or C2 CaBuAr pre-training)
   - Use labels from steps 1-3 plus about 400 points checked by eye.
   - Expected gain: uncertain. Hu 2021 (C5) found pixel machine learning does as well on scattered burns. Try it only after steps 1-3, and judge it by scar size class (D2).

**Validation upgrade, applies to all five:**
- Use the BAMT sampling and reference-perimeter tools (B1) to draw stratified reference scars for one season.
- Report accuracy by size class: under 1 ha, 1-3 ha, and over 3 ha.
- Compare with FireCCIS2 2023 (B2) when it is released.
