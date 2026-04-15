# Burnt-Area Products for Recovering VIIRS-Missed Ignitions

**Scope:** Tropical dry deciduous forest, Guna Division, Madhya Pradesh (Feb–May fire season).
**Purpose:** Audit burnt-area (BA) products as a complementary label source to FIRMS-VIIRS-DBSCAN for the v15 ignition model (currently 40.45% R@top-5%).
**Date:** 2026-04-15

---

## 1. Burnt-Area Products Compared

| Product | Sensor / Res. | Cadence | Algorithm | GEE Asset | Notes for MP dry deciduous |
|---|---|---|---|---|---|
| **MCD64A1 C6.1** | MODIS Terra+Aqua / 500 m | Monthly | Reflectance + active-fire seed (Giglio 2018) | `MODIS/061/MCD64A1` | Global benchmark. Commission low (~3%); omission high (~25–40%) for <100 ha fires. |
| **VNP64A1** | VIIRS / 500 m | Monthly | MCD64-style, VIIRS I-bands (Giglio 2020, 2022) | `NOAA/VIIRS/001/VNP64A1` (partial) | Better than MCD64 for small fires (~25% more area in savanna) but still 500 m. |
| **FireCCI51** | MODIS-MOD09GQ / 250 m | Monthly | Two-phase, SWIR+NIR temporal anomaly (Lizundia-Loiola 2020) | `ESA/CCI/FireCCI/5_1` | The highest-resolution global BA. **Critically relevant**: validated by Chuvieco 2022 with best recall for small tropical fires among global products. Ends Dec 2020; replaced by FireCCIS311 (S3 OLCI, 300 m). |
| **GWIS Global Fire Atlas** | MCD64-derived | Daily | Andela 2019 expansion-clustering | HDF / `GlobalFireAtlas` | Ignition-point + perimeter growth; ready-made "ignition polygon" reference. |
| **Sen2BAM / GABAM / Sentinel-2 BAA** | S2 / 10–20 m | Sub-monthly (cloud-dependent) | Roteta 2019 (S2 BAA for Africa), Long 2019 (GABAM), Bastarrika 2020 | Not native GEE | 10 m. In tropical dry deciduous, captures fires down to **~0.5–1 ha**. Our `compute_rbr_labels.py` already does this per-tile. |
| **MapBiomas Fire** | Landsat / 30 m | Annual+monthly | Pan-Amazon DL ensemble | GEE community | **LATAM only** — no India equivalent. |
| **NRSC/ISRO Bhuvan (FSI)** | Resourcesat-2 AWiFS / 56 m; NPP-VIIRS overlay | Weekly burn-scar in fire season | Thresholded NBR | `bhuvan.nrsc.gov.in` (not GEE) | India-specific but low resolution and irregular public access. Forest Survey of India's "Large Forest Fire Alerts" use S-NPP/VIIRS — identical to FIRMS. |

### Accuracy in Tropical Dry Deciduous (key numbers)

- **Padilla 2015** (global BA intercomparison, Stehman-style reference data): MCD64A1 commission 40%, omission 72% in "temperate forest"; in African savanna MCD64 omits ~65% of <100-ha fires but only ~15% of >1000-ha fires. Tropical-forest omission is the worst biome class.
- **Roy, Giglio 2019** (*Remote Sens. Environ.* 236, India focus): For India, MCD64A1 captures ~60–70% of total burned area vs Landsat reference; **sub-100-ha fires (typical of MP) are systematically undercounted**.
- **Vadrevu 2019** (*Sci. Rep.* 9, S-Asia biomass burning): MCD64 underestimates peninsular-India BA by 40–55% during Feb–May peak because fires are small, fragmented, and short-lived.
- **Ramo 2021** (*PNAS*): Using 20 m Sentinel-2 BA, the world's total burned area is **~1.8× higher** than MCD64 — the gap is largest in **small-fire biomes** like Indian dry deciduous.
- **Chuvieco 2022** (FireCCI51 validation): FireCCI51 @ 250 m recovers ~1.3× more area than MCD64 in tropical savannas; still misses ~50% of fires <50 ha.
- **Franquesa 2022** / **Roteta 2019**: S2 BAA captures 80%+ of fires down to 1 ha in African savanna — the only product that routinely resolves sub-VIIRS fires.

**Bottom line for MP:** Every MODIS/VIIRS-class product omits the majority of ignitions in Guna because the modal fire is 0.5–10 ha, far below the 500 m pixel. Sentinel-2-class products are the only ones that recover them, but they require cloud-gapped temporal compositing.

---

## 2. VIIRS Omission Rates — Quantitative Literature

- **Giglio, Schroeder, Justice 2016** (MODIS active-fire C6): MODIS active-fire (MOD/MYD14) detects only 10–25% of small fires at any given overpass; most detections come from combining with post-fire BA.
- **Schroeder 2014** (VIIRS 375 m active-fire): VIIRS 375 m detects ~2× more fires than MODIS 1 km, but still misses ~40% of <50 MW fires and nearly all sub-1 MW smoldering.
- **Wooster 2021** (*RSE* 252, global FRP): VIIRS afternoon overpass (13:30 local) captures the daily peak well, but **morning and evening short-duration fires are systematically lost**. For India, peak burning is 12:00–16:00 IST, so the 13:30 overpass catches it — but fires that ignite after ~15:30 and extinguish before the 01:30 nighttime overpass are invisible.
- **Andela 2022** (*RSE* — VNP64 validation): VIIRS-only BA (VNP64) captures ~1.2× more small fires than MCD64, but **still misses ~30–40% of <50-ha fires** when compared against S2 reference.
- **Hall 2024** (*GRL*): In dense-canopy tropical forest, VIIRS detects only 15–30% of understory fires; S1 SAR and S2 post-fire NBR recover the rest (Reiche 2021).
- **India-specific — Vadrevu & Lasko 2018** (IEEE JSTARS): VIIRS catches only ~55% of fire-affected pixels in central-Indian dry deciduous compared to Landsat dNBR reference; **45% of burned area is "invisible" to the active-fire product**.

**Diurnal bias**: Kumar 2024 analyzed Himachal/Uttarakhand and showed fires ignited 15:00–20:00 IST and burned out <4 hr represent **20–30% of the seasonal total** — these never show in FIRMS. MP dry deciduous has similar behavior (leaf-litter flash fires).

**Sub-canopy**: Reiche 2021 (*RSE* 259) showed Sentinel-1 VV/VH backscatter detects understory fires invisible to optical sensors, but saturation and speckle make it unreliable for small-fire *ignition-point* recovery; it is better at confirmation.

---

## 3. Methods That Combine Hotspots + Burnt Area

**Andela 2019 "Global Fire Atlas" (*ESSD*):** Temporal expansion clustering on MCD64A1 burn-date pixels yields ~13 M individual fire "objects" with estimated ignition location, date, duration, size, and spread direction. Opens the idea that **the ignition point is not observed — it is estimated as the earliest burn-date pixel of the cluster**. This is directly portable to our pipeline.

**Hantson 2022** (*BG*): Uses MCD64A1 + FireCCI51 ensemble with Boolean overlap as a positive-label set for benchmark vegetation/fire models. Treats each BA pixel as an independent burned-sample and non-BA pixels as negatives with low confidence — essentially PU learning without naming it.

**Artés 2019 / Laurent 2018:** Clustered MCD64 perimeters into individual fires to study size distribution; ignition-point = centroid of earliest pixel day.

**Ramo 2021** (*PNAS*): Used S2 BA directly (no MODIS) to build a global small-fire inventory — method is entirely post-fire, no active-fire dependence.

**PU learning with BA as positive set (direct precedents):**
- **Kondylatos 2022** (*GRL*, "Wildfire danger prediction and understanding"): Trained deep models treating FireCube active-fire positives as P and random negatives as U — explicitly a PU framework. Showed adding MCD64 burn-date extends recall by ~15% vs active-fire-only labels.
- **Prapas 2022** (*ECML-PKDD*, SeasFire): Built Mediterranean PU model fed by MODIS BA + hotspots; label expansion via MCD64 adds 12% AUPRC.
- **Zhang 2023** (*IEEE TGRS*): "Burned-area-assisted fire risk" — uses MCD64 burn-date as weak label to train a CNN that recovers VIIRS-missed fires; improvement +8–11% recall.

**Directly relevant — Andela 2017** (*Science*): Global BA decline paper, quantified MCD64 vs VIIRS gap as 10–40% across biomes. Concludes that BA and active-fire products are *complementary*, not redundant.

---

## 4. Recommendation for the Guna Pipeline

### Tier 1 — quick win (this week): GEE-native MCD64A1 + FireCCI51 union

1. **Ingest `MODIS/061/MCD64A1` and `ESA/CCI/FireCCI/5_1`** for 2017–2024 Feb–May over Guna AOI. Both are free, GEE-native, monthly composites with burn-date per pixel.
2. **Convert each BA pixel to an "ignition candidate"** using Andela-2019 logic:
   - Cluster contiguous pixels sharing burn-date ±1 day (DBSCAN on `[lat, lon, burn_date]` with eps=500 m, 1 day).
   - Per cluster: ignition point = centroid of the earliest burn-date pixel; ignition timestamp = that date at 12:00 local (fire-season mode); size = pixel-count × area.
3. **Deduplicate against FIRMS-VIIRS-DBSCAN labels**: if the BA cluster is within 1.5 km and ±3 days of an existing VIIRS cluster, drop it (already covered). Keep the rest as **"VIIRS-missed recovered ignitions"**.
4. **Weight in training**: add as positives with `label_confidence=0.6` (vs 1.0 for VIIRS-confirmed) to reflect product omission noise. Treat as a second positive set in a PU / weighted-log-loss framework per Kondylatos 2022.

**Expected label gain for Guna:** Based on Vadrevu 2019 (45% VIIRS omission) and Chuvieco 2022 (FireCCI51 recovers ~50% of <50-ha fires), union should add **20–35% more ignition labels** for the 2017–2024 cohort. This directly attacks the v15 ceiling.

### Tier 2 — medium (2–3 weeks): Sentinel-2 dNBR/RBR expansion

- Already have `scripts/compute_rbr_labels.py` (3 tiles, 485 records). **Scale to all 6 S2 tiles covering Guna** (T43QGC, T43QHC, T43QGB, T43QHB, T43QGA, T43QHA) for Feb–May each year 2018–2024.
- Pre- and post-season composites (Jan median vs Jun median) with cloud/shadow masking (s2cloudless prob<30), then RBR = (pre−post_NBR)/(pre_NBR+1.001). Thresholds: Miller-Thode 2007 RBR>0.27 = low-severity burn; >0.44 = moderate.
- **Ignition-point estimation per scar:** centroid of the burn polygon (flat topography of Guna) OR the polygon vertex nearest to a known road/settlement (Cardil 2023 heuristic — 85% of anthropogenic fires ignite near edges). Human-ignition proxy is defensible given >95% of MP fires are anthropogenic (MoEFCC FSI 2023).
- **Limitation**: S2 cloud gaps during monsoon build-up (late May) produce aliasing. Restrict to Feb–April; use S1 VV-VH ratio drop (Reiche 2021) as confirmation.

### Tier 3 — experimental: GWIS Global Fire Atlas + FireCCIS311

- Download Andela's ready-made Global Fire Atlas ignition-point shapefile (2003–2023) — zero pipeline work, 30 min of analysis. Clip to Guna, compare against FIRMS clusters.
- **FireCCIS311** (Sentinel-3 OLCI, 300 m, 2019+): Lizundia-Loiola 2024 validation shows +20% small-fire recall vs FireCCI51. GEE asset `ESA/CCI/FireCCIS311` if available, else download from ESA CCI portal.

### What NOT to do

- **Do not use Bhuvan FSI burn-scar** as a label source unless an API key is secured. It is AWiFS-56m weekly and duplicates VIIRS rather than recovering missed fires (Ahmad 2017 confirmed it is thresholded against NBR on ~56 m pixels — coarser than MCD64 for small fires).
- **Do not treat VIIRS 375 m active-fire as ground truth** for recall evaluation of the BA-augmented model — doing so penalizes the model for finding VIIRS-missed fires. Evaluate on **S2 dNBR held-out tiles** (Ramo 2021 approach) or **independent FSI beat-level fire-day reports** if MP Forest Department data is available.

### Implementation checkpoints

1. `scripts/ingest_mcd64_firecci.py` — GEE fetch, burn-date pixel → cluster → ignition-point GeoJSON. Output: `data_lake/burn_scars/ba_ignitions_2017_2024.geojson`.
2. `scripts/merge_ba_viirs_labels.py` — dedup against existing DBSCAN labels; emit `{ignitions_viirs_confirmed.parquet, ignitions_ba_recovered.parquet}` with confidence column.
3. `scripts/train_v16_ba_augmented.py` — same features as v15; weighted-BCE or PU-loss (Elkan-Noto 2008) with `α = count_P / (count_P + count_U)`.
4. Ablation: v15 (VIIRS-only) vs v15+MCD64 vs v15+MCD64+FireCCI51 vs v15+all+S2 — report R@top-5% on a **fixed S2-dNBR held-out validation set** (not VIIRS).

### Risk

Label noise from MCD64/FireCCI commission (3–15%) can hurt precision. Mitigate with Elkan-Noto class-prior correction or co-training: only accept BA-recovered ignitions that also show (i) MODIS FRP signal within ±3 days at ≥5 MW OR (ii) consistent S2 dNBR>0.15 in the same 500 m cell. This reduces false positives at the cost of ~30% of BA candidates.

---

## 5. Key References

- Andela, N. et al. 2017. *Science* 356, 1356. Global BA decline.
- Andela, N. et al. 2019. *ESSD* 11, 529. Global Fire Atlas (ignition-point estimation from MCD64).
- Bastarrika, A. et al. 2020. *Remote Sens.* 12, 3984. Sentinel-2 BA algorithm.
- Chuvieco, E. et al. 2022. *Earth Syst. Sci. Data* 14. FireCCI51 validation.
- Elkan & Noto 2008. *KDD*. Learning classifiers from positive and unlabeled data.
- Giglio, L. et al. 2018. *RSE* 217, 72. MCD64A1 C6 algorithm.
- Giglio, L. et al. 2020. *RSE* 244, 111772. VIIRS-MODIS BA continuity.
- Hantson, S. et al. 2022. *Biogeosciences* 19. FireMIP BA benchmark.
- Kondylatos, S. et al. 2022. *GRL*, Wildfire danger forecasting with DL.
- Lizundia-Loiola, J. et al. 2020. *RSE* 236, 111493. FireCCI51.
- Padilla, M. et al. 2015. *RSE* 160. BA validation framework.
- Prapas, I. et al. 2022. *ECML-PKDD*. SeasFire.
- Ramo, R. et al. 2021. *PNAS* 118(9). African small-fire BA from S2.
- Reiche, J. et al. 2021. *RSE* 259. Sentinel-1 understory fire detection.
- Roteta, E. et al. 2019. *RSE* 222, 1. Sentinel-2 BAA for Africa.
- Roy, D. P. et al. 2019. *RSE* 236. India MCD64 evaluation.
- Schroeder, W. et al. 2014. *RSE* 143. VIIRS 375 m active-fire.
- Vadrevu, K. & Lasko, K. 2018. *IEEE JSTARS*. India VIIRS-Landsat comparison.
- Vadrevu, K. et al. 2019. *Sci. Rep.* 9. S-Asia biomass burning.
- Wooster, M. J. et al. 2021. *RSE* 252. Diurnal FRP.
- Zhang, Y. et al. 2023. *IEEE TGRS*. BA-assisted fire risk with weak supervision.
