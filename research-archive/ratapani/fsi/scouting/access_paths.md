# Human access into the forest at fine scale: paths, walking time and fire (scouting, round 3)

Written 14 Oct 2026. Topic: how to measure how easily people reach each 500 m cell. Our data show interior cells ignite more than village-edge cells, and collectors walk 4-8 km a day.

This note does not repeat `human_fire_drivers.md` (Schmerbeck Fig. 5, Niyogi 2025 Satpura, Tadoba GPS walks, the first Tobler sketch) or `open_datasets.md` (OSM, GHSL). It adds three things:

- Checks I ran on the actual Ratapani data (OSM, Microsoft road detections, Google Open Buildings, our labels).
- Full-text reads of the method papers.
- An exact recipe for walking time.

Source tags: **FULL** = full text read; **PARTIAL** = parts read; **ABSTRACT ONLY**; **DATA** = I downloaded and analysed the dataset myself. My own reasoning is marked [inference].

---

## Headline findings

1. **OSM is almost empty inside Ratapani, so our current `dist_track` feature is broken.** I queried OSM through Overpass on 14 Oct 2026. Inside the 813 km² sanctuary polygon it holds:
   - 0.4 km of `highway=track` and 0.1 km of `path` in total.
   - 52 km of all highway types, mostly NH-46 trunk.
   - 1 building and 6 place nodes.

   In `ee/proximity.csv`, `dist_track` has a median of **10.5 km**, and its 90th percentile is 19 km. No real Ratapani cell is 10 km from a track [inference]. The feature is measuring distance to the few tracks OSM happens to hold outside the sanctuary.
2. **The Microsoft ML road detections add 2.5× more road inside the sanctuary than OSM, and they are free.** The 2025-04-28 release has 293 road segments and **132 km** inside the polygon (0.16 km/km²), compared with 52 km in OSM. Most detected widths are 6-14 m, so these are forest roads and fire lines wide enough for a vehicle. Footpaths are not in it.

   Effect on distance from forest cells to the nearest mapped road (non-footway):

   | | Median distance | Cells farther than 2 km | Cells farther than 3 km |
   |---|---|---|---|
   | OSM only | 3.8 km | 76% | 62% |
   | OSM + Microsoft | 1.05 km | 24% | 12% |
3. **Google Open Buildings v3 finds 6,224 buildings inside the sanctuary** (3,841 with confidence ≥0.75). OSM has 1. These are interior forest hamlets, and our village layer misses many of them:
   - I built hamlet clusters: ≥5 buildings with confidence ≥0.75 in one 250 m bin.
   - For **63% of forest cells**, the nearest Open Buildings hamlet is more than 1 km closer than our current `dist_village` says.
   - The Spearman correlation between the two distance measures is only 0.38.
4. **The interior effect survives correct hamlets, and its shape is a ramp that flattens out, not a hump.**
   - Data: our labels (`true_lead_labels.parquet`, `pos`, `valid_strict`, 2017-24) on 3,261 forest cells (forest_frac ≥0.5).
   - Burn rate per valid cell-day rises steadily with distance to the nearest Open Buildings hamlet: **0.23% at 0-0.5 km, 0.43% at 0.5-1 km, 0.57% at 1-1.5 km, 0.75% at 1.5-2 km, 1.01% at 2-3 km, 1.18% at 3-4 km, 1.17% beyond 4 km.** That is a 5× ramp that flattens after about 3 km.
   - The number of buildings within 4 km is the strongest single correlate: Spearman −0.47 with the cell burn rate. The figure for Open Buildings distance is +0.43. For our current `dist_village` it is only +0.26, and for `dist_road` +0.33.
   - **The current LightGBM (pipeline_lean, LOSO predictions) under-predicts remote cells.** The ratio observed/predicted climbs from 0.095 near hamlets to 0.187 at 3-4 km. Its Spearman correlation with buildings-within-4-km is −0.19.

   So the model has not fully absorbed the gradient, and an Open Buildings density feature should add information [inference].
   - Caveat: these labels have a base rate of 0.49%, against 4.65% for the scoring labels in `scoring/SCORING.md`. Rerun the table on the scoring labels before acting.
   - Caveat: at the cell scale, nowhere in Ratapani is people-free. The hump reported in the literature sits at 1-1.5 km and would be inside our first two bins.
5. **The theory predicts that burning moves inward as the forest edge is used up.** Albers' illegal-extraction model, made spatial in the level-set paper (§2): benefit rises with depth into the forest (the edge is depleted), while cost rises with walking time and patrol risk. The extractor goes to the depth where benefit minus cost is greatest.
   - This fits "interior ignites more" if tendu, mahua or grass quality rises with depth [inference].
   - It means walking time, not straight-line distance, is the right axis, with patrol coverage as a second cost.

---

## Part A. What I measured on our own area (DATA)

### A1. OpenStreetMap inside Ratapani (DATA, Overpass mirror maps.mail.ru, 14 Oct 2026)
- Query: all `highway=*` ways, plus place, building, water and landuse features, in the box 22.80-23.30 N, 77.45-78.20 E. I clipped them to `ratapani_aoi.geojson` by testing each segment midpoint (pure Python).
- Length inside the sanctuary:

  | Highway class | km | Note |
  |---|---|---|
  | trunk | 27.7 | concrete/asphalt (NH-46) |
  | tertiary | 10.4 | |
  | secondary | 8.9 | |
  | bridleway | 2.4 | |
  | footway | 1.0 | |
  | unclassified | 0.6 | |
  | track | 0.4 | |
  | path | 0.1 | |
- Other features inside: 9 water polygons, 3 river ways, 1 stream way, 3 village and 3 hamlet nodes, 4 residential landuse polygons, 1 building.
- The overpass-api.de and kumi mirrors failed (reset or timeout). **maps.mail.ru/osm/tools/overpass/api/interpreter works from the container.**
- **Concrete action (thread 1):**
  - Drop or rebuild `dist_track`.
  - OSM is useful here only for the main roads and the large reservoirs.

### A2. Microsoft Road Detections inside Ratapani (DATA + FULL read of the GitHub page)
- Source: https://github.com/microsoft/RoadDetections, release 2025-04-28, `Southern_Asia.zip` (1.47 GB). Format: TSV with an ISO3 code and a GeoJSON LineString per road, plus a `WidthMeters` property. Licence ODbL.
- Method:
  - Imagery: Bing Maps (Maxar, Airbus). The vintage is not stated.
  - Model: UNet-ResNet trained on 20,000 labelled tiles at 1 m.
  - Pixel scores: precision 85.2%, recall 82.8%.
  - APLS scores: precision 87.5%, recall 79.3%.
  - After conflation, filtering and QC the pipeline reports 95% precision.
- My extraction: I streamed the zip and filtered `IND` rows to the bounding box. funzip ended with a "length error", so the regional file may be cut short. I kept 16,791 segments covering the whole box.
- Inside the AOI: 293 segments and 132 km of road.

  | Width class (m) | 6-7 | 8-9 | 10-11 | 12-13 | 14-15 | 16-17 | 18+ |
  |---|---|---|---|---|---|---|---|
  | km | 21.9 | 46.1 | 6.9 | 19.2 | 13.8 | 11.6 | 12.4 |
- With OSM, the median distance from a forest cell to the nearest road vertex falls from 3.8 km to 1.05 km.
- Caveat: my bounding box started at 77.45 E, but the 500 m grid reaches 77.34 E. Cells on the west edge got distances that are too large. Re-extract with a box starting at 77.30 E.
- **Concrete action (thread 1, thread 5):**
  - Rebuild `dist_track` as the distance to OSM ∪ Microsoft roads.
  - Add `road_len_in_cell` (Niyogi's firebreak sign).
  - Add the Microsoft width as a "vehicle access" class (≥8 m means jeep-able [inference]).
  - Thread 5: these are the routes by which the field team reaches an alert.
  - Expected effect: +0.3-1 pt of recall at 5/beat [inference]. Distance to roads is weak in Satpura and Montana, but our current version is broken, so fixing it is cheap.

### A3. Google Open Buildings v3 inside Ratapani (DATA)
- Source: `https://storage.googleapis.com/open-buildings-data/v3/points_s2_level_6_gzip_no_header/{397d,397f}_buildings.csv.gz`, 68 + 38 MB.
  - Ratapani sits in S2 level-6 cells 397d and 397f. I computed this with a pure-Python S2 token function, now in the scratchpad.
  - Columns: lat, lon, area_m², confidence, plus code. Licence CC BY-4.0 / ODbL.
- Inside the AOI: 6,224 buildings. By confidence: 0.6-0.7: 2,383; 0.7-0.8: 2,658; 0.8-0.9: 1,183.
- Hamlet clusters: 208 bins of 250 m with ≥5 buildings at confidence ≥0.75, and 45 bins with ≥20.
- Per-cell features (forest cells only) are in `scratchpad/ob/openbuildings_cell_features.csv`:
  - `d_ob`: distance to the nearest hamlet cluster.
  - `bld2`, `bld4`: buildings at confidence ≥0.75 in hamlet clusters within 2 km and 4 km.
  - `nham4`: number of hamlet clusters within 4 km.
- Burn rate vs these features (labels: `true_lead_labels.parquet`, `valid_strict`; predictions: `pipeline_lean_pred_loso_2017_24.parquet`):

  | d_ob | Cells | Burn rate per valid cell-day | Observed/predicted |
  |---|---|---|---|
  | 0-0.5 km | 327 | 0.23% | 0.095 |
  | 0.5-1 km | 558 | 0.43% | 0.121 |
  | 1-1.5 km | 571 | 0.57% | 0.130 |
  | 1.5-2 km | 550 | 0.75% | 0.146 |
  | 2-3 km | 815 | 1.01% | 0.171 |
  | 3-4 km | 357 | 1.18% | 0.187 |
  | >4 km | 83 | 1.17% | 0.178 |

  The observed/predicted ratio is not calibrated, because the model was trained on different labels. Only the trend in that column matters.

  | Buildings within 4 km | 0 | 1-20 | 21-100 | 101-300 | 301-1000 | >1000 |
  |---|---|---|---|---|---|---|
  | Burn rate | 0.99% | 1.10% | 0.92% | 0.78% | 0.45% | 0.16% |

  Spearman correlations with the per-cell burn rate (and with the model residual):

  | Feature | Burn rate | Model residual |
  |---|---|---|
  | `bld4` | −0.47 | −0.19 |
  | `nham4` | −0.47 | −0.14 |
  | `d_ob` | +0.43 | +0.14 |
  | `dist_road` | +0.33 | +0.06 |
  | `dist_boundary` | +0.30 | +0.15 |
  | `dist_village` | +0.26 | +0.12 |
- Interpretation [inference]:
  - Fire is **lowest where many people live close by**: grazed-out grass, constant trampling, fuel taken for firewood, people quick to put out fires.
  - It rises to a plateau 3+ km from any hamlet.
  - This matches Schmerbeck's all-India pattern (median 6 km for unburned cells vs 10 km for frequently burned ones). It also matches the Bhadra result: firewood collectors walk 0.5-0.9 km, so the near ring is degraded with less litter (§B6).
  - **Check for false positives:** some "buildings" in the forest may be rock outcrops or machans. Before using the clusters, inspect 20 random interior clusters on Google satellite imagery.
- **Concrete action (thread 1):**
  - Add `bld4` (or the kernel version in §C) and `d_ob` to LightGBM.
  - Replace `dist_village` with the Open Buildings clusters.
  - Expected effect: **+0.5-2 pts of recall at 5/beat** [inference]. The residual correlation of −0.19 is the largest unexplained spatial signal I have seen in these notes. Part of it is between beats, though, and the metric ranks cells within a beat, so the gain within beats will be smaller.
  - **Open Buildings 2.5D Temporal** (annual 2016-2023, presence, count and height, 4 m effective) can give a building count for each year, to follow hamlet growth or relocation. It is on Earth Engine as `GOOGLE/Research/open-buildings-temporal/v1`.

---

## Part B. Sources

### B1. Arnold, Fernandez, Jia, Parkinson, Tonne, Yaniv, Bertozzi & Osher 2018, "Modeling environmental crime in protected areas using the level set method", arXiv:1808.03228. **FULL**
https://arxiv.org/abs/1808.03228
- **Albers (2010) model:**
  - An extractor chooses a depth d.
  - Profit is P(d) = B(d) − C(d), where B is the benefit (concave and increasing with depth) and C is the walking cost.
  - With patrols: P(d) = (1 − Ψ(d))·B(d) − C(d), where Ψ is the cumulative chance of being detected.
  - Extraction concentrates on a ring at the best depth d*. **That is a theoretical hump in distance.**
- **Level-set version:** a front starts at the boundary and moves with normal speed 1 / (1/v(x,y) + α·ψ(x,y)·B(x0,y0)).
  - v is the walking speed from terrain.
  - ψ is the patrol density, and α weights it.
  - The patrol penalty grows with the benefit carried, because a caught extractor loses it.
- **Walking speed (Irmischer & Clarke 2018, as written in the paper):**
  - v = 0.11 + exp(−(100s + 2)² / 1800) m/s, where s is rise over run. This peaks at about 1.11 m/s at a 2% downhill grade and never falls below 0.11 m/s.
  - The authors' modified version falls to zero: **v = 1.11·exp(−(100s + 2)² / 2345)**. It matches the original for grades below 60%.
- Study areas: Yosemite and Kangaroo Island. The paper uses real elevation data, solves the equation with fast-marching or level-set numerics, and optimises patrols to minimise the area affected.
- **Concrete action (thread 1, thread 5):**
  - Use v = 1.11·exp(−(100s+2)²/2345) as an alternative to Tobler in the friction surface (§C).
  - Add a patrol-cost term once M-STrIPES tracks exist (B10).
  - Test for an interior ring: fit `walk_min` as a spline. If the burn rate peaks and then falls at long walking times, the Albers ring is present. Our Euclidean test (A3) shows a plateau, not a fall [inference].

### B2. Gholami/Xu et al. 2019, "Stay ahead of poachers: illegal wildlife poaching prediction and patrol planning under uncertainty with field test evaluations" (PAWS), arXiv:1903.06669. **FULL**
https://arxiv.org/abs/1903.06669
- **Setup:**
  - Grid: 1 × 1 km cells. MFNP 4,613 cells, QEPA 2,522, SWS 3,750 (Cambodia).
  - Time step: 3 months.
  - Features: 19-22 static features, all encoded as distances (to rivers, roads, the park boundary, villages and patrol posts), plus elevation, forest cover and ecological features. Latitude and longitude are deliberately left out.
  - Plus last period's patrol effort c(t−1,n), in km patrolled per cell. Average effort is 1.75-3.96 km per cell per quarter.
- **Label noise:** detection rises with patrol effort, so a negative label is reliable only where effort is high. iWare-E trains an ensemble of weak learners, each on data filtered to effort ≥ θ, with θ set at effort percentiles.
- **Results:**
  - iWare-E raises AUC by 0.100 on average over plain bagging.
  - The Gaussian-process version reaches average AUC 0.784 (MFNP) and 0.757 (SWS).
  - Field tests found about 3× more snares in predicted high-risk areas, and 38 attacked cells.
- **What transfers to us:** our burn-scar labels do not depend on patrols, so the label-noise machinery is not needed. Two ideas do carry over [inference]:
  - **Distance to patrol posts and patrol effort** are standard features.
  - Encoding everything as distances, without coordinates, guards against overfitting.
- **Concrete action (thread 1):**
  - Add `dist_beat_chowki` (beat guard post) and `dist_range_office`. The posts can be digitised from the working plan or asked from the DFO.
  - When patrol GPS tracks are available, add `patrol_km_per_cell_prev_season`.
  - Expected effect: unknown. This is the cleanest test of the "remoteness = less surveillance" explanation [inference].

### B3. Sloan, Talkhani, Huang, Engert & Laurance 2024, "Mapping remote roads using artificial intelligence and satellite imagery", *Remote Sensing* 16:839. **FULL**
https://doi.org/10.3390/rs16050839
- Area: remote, semi-forested equatorial Asia-Pacific.
- Training data: **200 "screenshots" of free high-resolution imagery** at an effective 5 m pixel (1920 × 886 px each, from the Australian elevation portal, which is equivalent to Google Earth). Roads were digitised with a fixed-width pen in Photoshop, then tiled to 256 × 256 with augmentation, giving 8,904 tiles split 80/10/10.
- Models: UNet, ResNet-34 and ResNet-34+.
- Results: **F1 72% (UNet) to 81% (ResNet-34)**, mIoU 43-58%.
- Context: road-mapping studies in the Amazon and Asia-Pacific regularly find **2-13× more road length than government or OSM databases**. In Ratapani, Microsoft vs OSM gives 2.5× (A2).
- **Concrete action (thread 1, thread 5):**
  - This is a proven low-cost route to a **footpath and cattle-track map**: screenshots at about 1-5 m (Google or Bing; check the terms of use, or use our PlanetScope or 0.5 m imagery if we have them), about 200 labelled images, and a ResNet-34 U-Net.
  - Paths under a dry-deciduous canopy are most visible in March-May, when the canopy is leafless [inference]. Label on imagery from that season.
  - Effort: 3-5 days.

### B4. Botelho et al. 2022, "Mapping roads in the Brazilian Amazon with artificial intelligence and Sentinel-2", *Remote Sensing* 14:3625. **ABSTRACT ONLY** (MDPI returned 403; facts from the abstract and the Imazon page)
- Method: modified U-Net on 2020 Sentinel-2, run on Microsoft Planetary Computer, trained on an earlier road map digitised from Landsat.
- Results: recall 65%, precision 71% (the authors say these are understated). 3.46 million km of roads mapped. 41% of forest is cut or within 10 km of a road.
- **Concrete action:** Sentinel-2 at 10 m can detect logging roads 4-8 m wide. Footpaths 0.5-1.5 m wide are below its resolution, except where trampled soil makes a bright line [inference]. Use it only for annual change in forest roads, not for paths.

### B5. Bastani et al. 2018, "RoadTracer: automatic extraction of road networks from aerial images", CVPR (arXiv:1802.03680). **PARTIAL**
- Approach: iterative graph construction, where a CNN decides the next step from Google imagery at 60 cm/pixel.
- Result: at a 5% error rate it captured **45% more junctions** than segmentation (0.58 vs 0.40), across 15 cities.
- Context from the paper: OSM error vs TorontoCity was 14%, and OSM recall 0.86.
- Code: https://github.com/mitroadmaps/roadtracer
- **Concrete action:** low priority. RoadTracer and SpaceNet are tuned to urban roads. For forest paths, segmentation plus skeletonisation (B3) is simpler. Use RoadTracer-style graph tracing only if path connectivity matters for routing (thread 5) [inference].

### B6. Karanth, Curran & Reuning-Scherer 2006, "Village size and forest disturbance in Bhadra Wildlife Sanctuary, Western Ghats, India", *Biological Conservation* 128:147-157. **FULL**
- **Design:** 13 villages in a 492 km² sanctuary, 6 surveyed ecologically.
  - 30 transects of 1 km from the village edge.
  - 6 points at 200 m spacing, each a 15 m radius plot.
  - 10 indicators scored 0-3: fire intensity, cut stems, cut bamboo, tree notches, exposed soil, exotic weeds, **human trails**, understorey cover, bamboo regeneration, lopped trees.
- **Numbers:**
  - Firewood walk: **0.54-0.93 km (mean 0.75 km)**.
  - Cattle per household: 2-12; cattle per village: 55-1,021.
  - **Correlation between cattle-trail and human-trail abundance: 0.98.** This justifies one "path" layer for both [inference].
  - First principal component loadings: human trails **0.46** (the highest), fire intensity 0.22.
  - A quadratic GLM in distance × village size class gave R² = 0.60 (adjusted 0.57).
  - Disturbance starts to fall at about 400 m for small villages and about 800 m for medium and large ones.
  - **Overlap zones reachable from 2+ villages were the most disturbed.**
  - The 6 villages used an average of 23.7 km² intensively (95% limits 17.5-28.9). Total footprint 41-52 km², which is 8-10% of the sanctuary.
- **Concrete action (thread 1):**
  - Add `n_hamlets_within_60min_walk` (the overlap effect) and village size (number of buildings).
  - Fire was low-weight in Bhadra, where daily use degrades the forest; our near-hamlet cells burn least (A3), consistent with that [inference].
  - Village size should also scale how far the disturbed zone reaches: about 0.4 km for 15-30 households, about 0.8+ km for 60-130. In §C this is the kernel radius parameter.

### B7. NESAC 2020, "Forest fire assessment in NER" (North Eastern Space Applications Centre, MODIS 2001-2013). **FULL**
https://nesac.gov.in/assets/resources/2020/12/Forest-Fire-Assessment-in-NER.pdf
- **Distance to built-up:**
  - Maximum fire count at **1,000-1,500 m** for NER as a whole. By state: 500-1,000 m in Arunachal, Assam and Meghalaya; 1,000-1,500 m in Manipur and Nagaland; 1,500-2,000 m in Mizoram and Tripura.
  - Minimum at 2,500-3,000 m (or at 0-500 m in Manipur, Mizoram and Tripura).
- **Distance to road:** maximum at 50-100 m, minimum at 150-200 m.
- **Distance to water:** maximum beyond 1,000 m, minimum at 0-100 m.
- **Caveat:** these are raw fire counts per distance band, not normalised by the area of each band. The area of a ring grows with distance, and the outer bands are cut off by the next village. So the "hump" may be partly an area artefact [inference]. Shifting cultivation in NER also differs from our litter fires.
- **Concrete action:** when we report our own curve, always normalise by valid cell-days (as in A3). Do not treat NESAC's hump as evidence for Ratapani.

### B8. Jiménez-Ruano, Jolly, Freeborn et al. 2022, "Spatial predictions of human and natural-caused wildfire likelihood across Montana (USA)", *Forests* 13:1200. **FULL**
https://research.fs.usda.gov/treesearch/65053
- Data: 30 m rasters of slope, maximum NDVI and Euclidean distance to primary and secondary roads.
- Models: GLM and GAM, each with and without spatial smoothing s(x,y).
- Results:
  - Spatial GAM AUC: 0.84 for natural ignitions, 0.89 for human ignitions.
  - Without spatial terms, GLM and GAM AUCs differ by ≤0.01. GAMs gain ≥0.03 only where the response bends.
  - Human ignitions: a strong, nonlinear, **monotonic** rise in probability toward roads, especially within 5 km. Most ignitions lie within 2.5 km of a road.
- **What transfers:** road distance alone is crude, and a spatial smooth soaks up much of the effect. Our LightGBM with burn history already plays the role of the spatial smooth, which is why distance features gain little [inference]. No hump.

### B9. Weiss et al. 2020, "Global maps of travel time to healthcare facilities", *Nature Medicine* 26:1835-1838. **FULL**
https://www.nature.com/articles/s41591-020-1059-1
- Walking-only friction surface:
  - **Every road pixel is walked at 5 km/h.**
  - Water is crossed at 1 km/h (wetland or swimming).
  - Off-road speeds by land cover and slope come from Weiss 2018 (*Nature* 553:333). That table is paywalled and I could not verify it.
- Results: 91.1% of the world's people are within 1 h of care by motorised transport, but only 56.7% on foot.
- **Data:** Earth Engine `projects/malariaatlasproject/assets/accessibility/friction_surface_2019_v5_1_walking_only`, in minutes per metre at 927.67 m pixels, licence CC BY 4.0.
- **Concrete action:**
  - At 1 km, the MAP walking surface is too coarse for ranking within a beat. Use it only as a sanity check on our 30 m surface. If our times disagree with MAP by more than 2× at 1 km, a parameter is off [inference].
  - Adopt its two rules: roads at 5 km/h, and water at 1 km/h (or impassable for the Kolar and Barna reservoirs).

### B10. JRC Global Accessibility Map, data-sources page (Nelson 2008). **FULL**
https://forobs.jrc.ec.europa.eu/gam/sources
The only fully published land-cover walking friction table I found.

- **Land cover (minutes per km, GLC2000 classes):**

  | Class | Minutes per km | Speed |
  |---|---|---|
  | Broadleaved deciduous closed tree cover | 60 | 1.0 km/h |
  | Broadleaved deciduous open | 48 | 1.25 km/h |
  | Tree / other natural vegetation mosaic | 48 | |
  | Burnt tree cover | 48 | |
  | Shrub (evergreen or deciduous) | 36 | 1.67 km/h |
  | Herbaceous | 36 | |
  | Cultivated | 36 | |
  | Cropland mosaics | 36 | |
  | Sparse herbaceous or shrub | 24 | 2.5 km/h |
  | Bare | 24 | |
  | Flooded shrub or herbaceous | 60 | |
  | Artificial surfaces | 2 | |

- Tracks: 10 km/h (6 min/km), by vehicle.
- **Slope:** v = v0·e^(−k·s), with v0 = 5 km/h, k = 3.0, and s = gradient (m/m), the same uphill and downhill (van Wagtendonk & Benedict 1980). The friction multiplier is v0 / v.
- **Concrete action:**
  - Use these values as the "conservative" variant of our land-cover friction.
  - They are probably too slow for leafless teak forest in March-April, where locals walk at 3-4 km/h on known lines [inference]. Hence the variants in §C.

### B11. Irmischer & Clarke 2018, "Measuring and modeling the speed of human navigation", *Cartography and Geographic Information Science* 45:177-186. **PARTIAL** (formula read in B1 and in the movecost documentation)
- Fitted on GPS data from 200 subjects. Their dissertation says it predicts route completion time within 10%.
- Formula: v = 0.11 + exp(−(100s+2)²/1800) m/s, for slopes up to 45°.
- Tobler's hiking function for comparison: W = 6·exp(−3.5·|S + 0.05|) km/h. It peaks at 6 km/h on a 5% downhill. Tobler's off-path multiplier of 0.6 is the standard rule (Tobler 1993, *NCGIA Technical Report* 93-1).
- R package `movecost` implements Tobler, Tobler off-path, Irmischer-Clarke (on and off path) and others, all anisotropic.
- **Concrete action:** compute walking time under Tobler and under the modified Irmischer-Clarke, and keep whichever gives the better recall. The two differ mostly above 30% grade, which matters only on the Vindhyan scarps [inference].

### B12. Faulkner, Stevens, Romañach, Lindsey & Le Comber 2018, "A spatial approach to combatting wildlife crime", *Conservation Biology* 32:685-693. **ABSTRACT ONLY**
https://doi.org/10.1111/cobi.13027
- Data: Savé Valley Conservancy, Zimbabwe; >10,000 illegal-hunting incidents; 6,454 animals killed; 8 years.
- Method: geographic profiling (criminology) applied to snare locations. It identified hunters' home villages, and accuracy improved with a "commuter" adjustment, because hunters live outside and hunt inside.
- **Concrete action:** reverse the logic for thread 5. Given a season's burn scars, a geographic profile (a Rossmo-type kernel with a buffer zone) points to the hamlets most likely responsible. This is useful for targeting awareness work, and for checking that our access kernel puts weight on the right villages [inference].

### B13. Benítez-López et al. 2017, "The impact of hunting on tropical mammal and bird populations", *Science* 356:180-183. **ABSTRACT ONLY**
- Meta-analysis of 176 studies. Hunted areas hold 58% fewer birds and 83% fewer mammals.
- Depletion reaches **7 km (birds) and 40 km (mammals)** from access points (roads and settlements).
- **Concrete action:** none direct. It shows that access-driven pressure extends kilometres from roads and settlements, consistent with an access kernel 3-8 km wide rather than a 500 m edge effect [inference].

### B14. Bistinas et al. 2013 (*PLoS ONE* 8:e81188) and Knorr et al. 2014 (*Biogeosciences* 11:1085). **ABSTRACT ONLY**
- Bistinas: burned area rises with population density at low density and falls above a threshold that differs by region. It rises in rangelands and falls in croplands.
- Knorr: globally, rising density mostly reduces fire. Only in sparsely populated areas does fire frequency rise, by 10-20% from 0 to 0.1 people/km². Fire is essentially suppressed above 100 people/km².
- **This is the published hump**, but along a population-density axis at coarse scale.
- **Concrete action:** our A3 table is the cell-scale version. The near-hamlet suppression matches the "high density suppresses" limb. Ratapani cells probably never reach the "too few people to ignite" limb [inference].

### B15. Narayanaraj & Wimberly 2012, "Influences of forest roads on the spatial patterns of human- and lightning-caused wildfire ignitions", *Applied Geography* 32:878-888. **ABSTRACT ONLY**
- Case-control logistic regression, eastern Cascades.
- Human ignitions: near roads, in high road density, near the wildland-urban interface.
- Roads limit fire size more than they add ignitions.
- **Concrete action (thread 4):** treat Microsoft roads and fire lines as barriers in the spread model.

### B16. Wang et al. 2023, "Scalable label-efficient footpath network generation using remote sensing data and self-supervised learning", arXiv:2309.09446. **PARTIAL**
- Method: self-supervised pretraining (BYOL/DINO style) on unlabelled aerial imagery, then a U-Net on a small labelled set, then mask → polygons → network.
- Area: urban Melbourne, MetroMap aerial imagery.
- Code: https://github.com/WennyXY/FootpathSeg
- **Concrete action:** self-supervised pretraining could cut labelling for forest trails to about 50 images [inference]. Try it only if B3's 200-image route is too costly.

### B17. Other leads (not read, or not useful)
- **Bhattacharya et al. 2025**, *Frontiers in Conservation Science* (Sikkim black bear, Circuitscape). PARTIAL. Circuitscape with settlements and roads as resistance, for an animal. I found **no study that uses Circuitscape for human movement into forest**.
  - [inference] Circuitscape's "current density" between hamlets (sources) and attractors (waterholes, tendu phads, mahua stands) gives a "path-use likelihood" layer that spreads flow across many near-optimal routes. That is a better stand-in for footpath density than a single least-cost path.
  - Tools: Circuitscape.jl (Julia) or Omniscape. Run it on the §C friction surface at 30-90 m.
- **Gelabert et al. 2025**, NHESS 25:4713 (Europe, 100 m Random Forest). Distance to the wildland-urban interface was the top human variable. ABSTRACT ONLY.
- **Piosphere literature** (Australia, Argentine Chaco). Distance to permanent water is the standard proxy for accumulated livestock pressure, and the relationship is non-linear. ABSTRACT ONLY. I found no km-scale decay curve for Indian cattle.
- **Southern Western Ghats NTFP survey** (786 households). Distance to the reserve limits subsistence harvesting but not commercial harvesting. Tendu is commercial, which fits deep collection [inference]. ABSTRACT ONLY.
- **Sirsi, Karnataka.** 35.6% of tribal collectors travelled 4-6 km into the forest for NTFPs. Snippet only.

---

## Part C. The exact recipe: walking time from every hamlet to every 500 m cell

Work at 30 m, then aggregate to 500 m. All inputs are free.

**1. DEM and slope.**
- DEM: Copernicus GLO-30 (`COPERNICUS/DEM/GLO30` on Earth Engine) or our SRTM. Resample to a 30 m grid in EPSG:32643, with a 5 km buffer around the AOI so that outside hamlets count.
- Directional slope S (rise over run) for each of the 8 neighbour moves.
- Two speed functions; keep both:
  - Tobler: v_T(S) = 6·exp(−3.5·|S + 0.05|) km/h.
  - Modified Irmischer-Clarke: v_IC(S) = 4.0·exp(−(100S + 2)² / 2345) km/h. This is 1.11 m/s converted to km/h.
- Slope factor: f(S) = v(S) / v(0).

**2. Base speed by land cover (flat ground, km/h).** Use ESA WorldCover 10 m, majority-resampled to 30 m. Three variants:

| WorldCover class | A "local, dry season" [inference] | B JRC/Nelson (B10) | C uniform |
|---|---|---|---|
| 10 tree cover | 3.0 | 1.0 | 4.0 |
| 20 shrubland | 3.0 | 1.67 | 4.0 |
| 30 grassland | 3.5 | 1.67 | 4.0 |
| 40 cropland (post-harvest, Mar-Apr) | 4.0 | 1.67 | 4.0 |
| 50 built-up | 5.0 | 30 (vehicle); use 5 | 4.0 |
| 60 bare/sparse | 4.0 | 2.5 | 4.0 |
| 80 permanent water | impassable (Kolar, Barna and large tanks); 1.0 for streams under 30 m wide | impassable | impassable |
| 90 herbaceous wetland | 1.0 | 1.0 | 1.0 |

**3. Path and road bonuses** (these replace the land-cover speed where present):
- OSM ∪ Microsoft roads (A2), rasterised with a 15 m buffer: **5.0 km/h**, as in Weiss's walking-only rule. Slope still applies, at half strength [inference: roads are graded].
- Footpaths and cattle tracks, digitised or detected (B3): **4.5 km/h**. Until they exist, use the Circuitscape current-density proxy (B17) as a soft bonus: speed × (1 + 0.5 × current percentile) [inference].
- Fire lines (from the beat maps, if digitised): 4.5 km/h.
- Optional off-path rule: multiply forest classes by 0.6 (Tobler's off-path factor) in variant A, if not already slow.

**4. Cost raster.** Time to cross a cell (minutes) = 0.03 km × √2 (diagonal moves) / (base × f(S)) × 60. Tools, in order of preference:
- **GRASS `r.walk`**: anisotropic. Its default is Naismith-Langmuir, but its coefficients can be set to a Tobler-like curve.
- `skimage.graph.MCP_Geometric` on an isotropic cost (use |S| from the steepest-slope DEM).
- R `movecost` / `gdistance::accCost` with an anisotropic transition matrix: the most faithful option, but slow at 30 m over about 1,500 km².

**5. Sources.**
- (a) Open Buildings hamlet clusters (A3): ≥5 buildings at confidence ≥0.75 per 250 m bin, weighted by building count N_h. Check 20 at random.
- (b) Census village points (2011 census village boundaries or Bhuvan) for villages outside the AOI.
- (c) Road entry points: road pixels, for outsiders arriving by bike.
- (d) Later: tendu phads (collection centres, from the MP Minor Forest Produce Federation) and beat chowkis.

Run one cost-distance per source class. For the kernel feature, run one per hamlet, or approximate by running per cluster of nearby hamlets (about 200 runs at 30 m; feasible).

**6. Per-cell features** (500 m cell = 17 × 17 pixels at 30 m; take the mean and the 10th percentile):
- `walk_min_hamlet`: walking time from the nearest hamlet.
- `access_kernel`: Σ_h N_h·exp(−t_h/τ) for τ = 30, 60 and 120 min. This is the "people who can reach this cell easily" measure. In A3, the raw building count within 4 km was the strongest correlate (−0.47).
- `n_hamlets_60min`: the overlap effect (Bhadra).
- `walk_min_road`.
- `walk_min_water`: water in Mar-May from JRC GSW monthly or a Sentinel-2 NDWI composite (see Part D).
- `walk_min_chowki`, when digitised.
- `walk_min_hamlet − euclid_min`: the "terrain detour". High values mean cells that look near but are hard to reach [inference].
- Each variant (A, B, C × Tobler or Irmischer-Clarke) becomes a separate column. LightGBM chooses, and we report gain or SHAP for each.

**7. Validation.**
- Field team GPS tracks (thread 5), plus M-STrIPES patrol tracks if the reserve shares them.
- Ratapani was notified as a tiger reserve in Dec 2024, so M-STrIPES patrolling should now be required.
- Check that the median speed along real tracks is close to the model speed for the same pixels. Tune the base speeds by a single scale factor.
- Tadoba GPS collectors (3.6-8.2 km/day) mean a daily reach of about 2-4 km out and back. That is about 45-90 min one way at 3 km/h, which sets τ ≈ 60 min [inference].

**8. Expected effect on the 2-day model** [inference throughout]:
- Static features cannot help "when". They can help "where" within a beat.
- A3 suggests the current model leaves an access-related residual: Spearman −0.19 against buildings within 4 km.
- Fixing `dist_track` (Microsoft roads) plus an Open Buildings kernel: **+0.5-2 pts of recall at 5/beat** (from about 29.5%).
- Full walking time on top: another +0-1 pt. Its main value is explanation and patrol planning (thread 5).
- **A hump is not expected.** Our Euclidean curve rises and then flattens at 3-4 km. If walking time shows a fall beyond about 90-120 min, that would be the Albers ring.

---

## Part D. Attractors: grazing and water

- **Livestock, village level:** the 20th Livestock Census (2019) gives village-wise cattle, buffalo, goats and sheep for Madhya Pradesh. A repackaged copy is at https://dataful.in/datasets/19140 (source: Ministry of Fisheries, Animal Husbandry & Dairying).
  - Join to census village codes for Raisen and Sehore districts.
  - Use cattle per hamlet as the weight N_h in `access_kernel_cattle`, separate from people. Bhadra's cattle-trail vs human-trail r = 0.98 suggests one path layer; but cattle graze closer, so use τ ≈ 30 min [inference].
  - Expected effect: small, but it separates "grazing burns" (fresh grass after fire) from "collection burns".
- **Gridded alternative:** FAO GLW4 (2015/2020, about 10 km). Too coarse within a beat; useful only between beats.
- **Waterholes:** JRC Global Surface Water monthly history (30 m, to 2021; `JRC/GSW1_4/MonthlyHistory`) for Mar-May water presence. Sentinel-2 MNDWI in Mar-May composites for 2017-2026 catches small ponds and check dams under 30 m. Saucer waterholes in the MP forest department's tiger-reserve plans can be asked from the DFO.
  - Niyogi 2025 (Satpura, in `human_fire_drivers.md`) found distance to water **positive** (fires far from water) and aquatic cover negative. So water acts as a firebreak or a moisture effect, not a fire attractor, at 1 km scale.
  - Run water both as an attractor (cattle walk to it, paths converge) and as moisture. Test `walk_min_water` with a spline and `water_frac_in_cell` separately.

---

## Datasets

| Name | Link | Resolution | Years | Licence | Access |
|---|---|---|---|---|---|
| Microsoft Road Detections | https://github.com/microsoft/RoadDetections (`Southern_Asia.zip`, 1.47 GB) | vector, width attribute; about 1 m imagery | imagery vintage varies; release 2025-04-28 | ODbL | stream zip, filter `IND` + bbox (done; scratchpad `papers_r3_access/ms_roads_rata.tsv`) |
| Google Open Buildings v3 | https://sites.research.google/open-buildings/ ; `gs://open-buildings-data/v3/points_s2_level_6_gzip_no_header/397d,397f` | building points/polygons, ≥0.6 conf | imagery about 2016-2023 | CC BY 4.0 / ODbL | HTTPS from storage.googleapis.com (done; `scratchpad/ob/`); EE `GOOGLE/Research/open-buildings/v3/polygons` |
| Open Buildings 2.5D Temporal | EE `GOOGLE/Research/open-buildings-temporal/v1` | 4 m effective raster | annual 2016-2023 | CC BY 4.0 | Earth Engine |
| OpenStreetMap | Overpass `https://maps.mail.ru/osm/tools/overpass/api/interpreter`; Geofabrik | vector | live | ODbL | works from the container; nearly empty inside Ratapani |
| MAP walking-only friction 2019 | EE `projects/malariaatlasproject/assets/accessibility/friction_surface_2019_v5_1_walking_only` | 927 m | 2019 | CC BY 4.0 | Earth Engine |
| MAP walking-only travel time to healthcare | EE `.../accessibility_to_healthcare_2019_walking_only` | 927 m | 2019 | CC BY 4.0 | Earth Engine (sanity check only) |
| JRC GAM friction table | https://forobs.jrc.ec.europa.eu/gam/sources | table | 2000 | open | web page |
| GRIP global roads (Meijer et al. 2018, ERL 13:064006) | https://www.globio.info/download-grip-dataset | vector + 5 arcmin density | about 2015 | open (cite) | download; for India mostly derived from OSM, so expect no gain over A2 [inference] |
| Copernicus DEM GLO-30 | EE `COPERNICUS/DEM/GLO30` | 30 m | 2011-15 | free | Earth Engine |
| ESA WorldCover | EE `ESA/WorldCover/v200` | 10 m | 2020, 2021 | CC BY 4.0 | already in `ee/worldcover.csv` (fractions); need the raster for friction |
| JRC Global Surface Water | EE `JRC/GSW1_4/MonthlyHistory` | 30 m | 1984-2021 | free | Earth Engine |
| 20th Livestock Census, MP, village-wise | https://dataful.in/datasets/19140 | village | 2019 | Govt. open data (via Dataful) | download; join on census village code |
| M-STrIPES patrol tracks | NTCA / Ratapani TR management | GPS tracks | from 2025 (TR notified Dec 2024) | restricted | ask the DFO / field director |
| movecost (R) | https://CRAN.R-project.org/package=movecost | n/a | n/a | GPL | anisotropic Tobler / Irmischer-Clarke |
| GRASS r.walk | https://grass.osgeo.org/grass-stable/manuals/r.walk.html | n/a | n/a | GPL | anisotropic walking cost |
| Circuitscape.jl / Omniscape | https://circuitscape.org | n/a | n/a | MIT | path-use likelihood between hamlets and attractors |
| FootpathSeg code | https://github.com/WennyXY/FootpathSeg | n/a | n/a | see repo | self-supervised footpath U-Net |
| RoadTracer code | https://github.com/mitroadmaps/roadtracer | n/a | n/a | see repo | graph road tracing |

Scratch files from this round (not in the project folder):
- `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/ob/openbuildings_cell_features.csv`: `cell_id`, `d_ob`, `bld2`, `bld4`, `nham4` for forest cells.
- `scratchpad/papers_r3_access/ms_roads_rata.tsv`: Microsoft roads in the bounding box.
- `scratchpad/papers_r3_access/hw_geom.json`: OSM highways.
- `scratchpad/s2tok.py`: S2 token function.
- `scratchpad/osm_cov.py`: AOI clip and length functions.

---

## Ranked action list

| # | Action | Thread | Expected gain [inference] | Effort |
|---|---|---|---|---|
| 1 | Replace `dist_village` with Open Buildings hamlet clusters. Add `bld4` / `access_kernel` (Euclidean first) to LightGBM. Rerun A3 on the scoring labels. | 1 | **+0.5-2 pts recall at 5/beat**; largest residual signal found (ρ = −0.19) | 0.5 day (features already in scratchpad) |
| 2 | Rebuild `dist_track` from OSM ∪ Microsoft roads (re-extract with the box starting at 77.30 E). Add `road_len_in_cell` and a width class. | 1, 4, 5 | +0.3-1 pt; fixes a broken feature | 0.5 day |
| 3 | 30 m walking-time surface (§C, variants A/B/C × Tobler/IC). Features: `walk_min_hamlet`, `access_kernel` (τ = 30/60/120 min), `n_hamlets_60min`, `walk_min_road`, terrain detour. | 1, 5 | +0-1 pt on top of #1; tests the Albers ring | 2 days |
| 4 | Spot-check 20 interior Open Buildings clusters on imagery (false positives: rocks, machans). | 1 | protects #1 | 1 h |
| 5 | Ask the DFO for beat chowki locations, fire lines and (from 2025) M-STrIPES patrol tracks. Add `walk_min_chowki` and `patrol_km_prev_season`; use the tracks to calibrate speeds. | 1, 5 | unknown; the decisive test of "remoteness = no surveillance" | 1 day plus waiting |
| 6 | Footpath and cattle-track map: about 200 dry-season high-res screenshots, ResNet-34 U-Net (Sloan 2024 recipe, F1 72-81%). Feed in as a 4.5 km/h path bonus. | 1, 4, 5 | +0-0.5 pt for the model; high value for field routing | 3-5 days |
| 7 | Village livestock (20th census) as a second kernel weight; Mar-May water from Sentinel-2 MNDWI as `walk_min_water`. | 1 | +0-0.5 pt | 1 day |
| 8 | Circuitscape current density between hamlets and attractors as a path-use proxy, until #6 exists. | 1 | +0-0.3 pt | 1-2 days |
| 9 | Geographic profile from each season's scars back to likely source hamlets, for awareness targeting (Faulkner 2018 logic). | 5 | operational | 1 day |
| 10 | Spread model: treat Microsoft roads ≥6 m and fire lines as barriers. | 4 | better perimeters | 0.5 day |

Sources: 9 read in full (B1, B2, B3, B6, B7, B8, B9, the JRC GAM page in B10, and the Microsoft RoadDetections page), 4 partial (B5, B11, B16, Bhattacharya 2025), 6 abstract or snippet only. 3 datasets analysed directly (OSM, Microsoft roads, Open Buildings) against our labels.
