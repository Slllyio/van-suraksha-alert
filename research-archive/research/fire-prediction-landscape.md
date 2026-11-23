# 2-day, 500 m fire prediction: what others do, and what it means for Ratapani

Research note, 13 Oct 2026. Discussion only; no code or data in the pipeline thread was touched.

## 1. Ratapani numbers that frame everything

From `ratapani/viirs_snpp_2013_2024.parquet` (VIIRS S-NPP, 2013 to 2024, Feb to May, binned to ~500 m; approximate, not snapped to `grid_500m.geojson`):

| What | Value |
|---|---|
| Season | 87% of detections fall in Feb to Apr; March alone is 49% |
| Base rate | about 0.13% of cell-days have a detection (1 in ~770); about 0.26% for a 2-day window |
| Same 500 m cell burned in the previous 2 days | 2% of fire cell-days |
| Detection within 1 km in previous 2 days | 30% |
| Detection within 2 km in previous 2 days | 45% |
| Fire cell-day in a cell that also burned in an earlier year | 59% |

Implications:
- Roughly half of tomorrow's fire cells sit next to a fire that is already burning. That half is a **spread** problem, and a "where is it moving" signal beats any weather model there. The other half are **new ignitions**, which are mostly human (mahua, tendu, grazing, clearing) and driven by place and calendar more than weather.
- At a 0.26% base rate, even a very good model will have modest precision. If an officer gets a list of the top 5% of cells (about 180 cells), a model with AUC around 0.9 typically catches something like 40 to 60% of fires with precision in single digits to low teens. That is normal for this problem, and the delivery design should assume it.

## 2. What the field has published

**Next-day spread (deep learning on image stacks).** Next Day Wildfire Spread (NDWS) and WildfireSpreadTS are the standard benchmarks. Swin U-Net results show that pretrained (ImageNet) weights and multi-day input both matter a lot [1]. Best spread scores are still low (IoU around 0.3) because fire pixels are sparse and imbalanced [2]. A 2026 benchmark argues the metric chosen decides which model "wins" [3]. All are US/Canada, large fires, not human-ignited surface fires.

**Sub-km next-day active fire forecasting.** An EGU 2026 poster uses diffusion models on ERA5 plus VIIRS at sub-km resolution [4]. Closest in framing to us, but preliminary.

**Operational fire-activity forecasts.** ECMWF's Probability of Fire (PoF) is now operational globally at ~9 km, daily, out to 10 days, ML-based, using fuel moisture, fuel load, human presence and lightning [5][6]. Their key finding: fuel/vegetation moisture data quality mattered most, and fire-weather indices alone flagged broad areas but missed ignition hotspots. PoF is a ready-made coarse prior we could ingest, if we can get access.

**Global seasonal.** SeasFire datacube (0.25°, 8-day) and FireCastNet (GraphCast-style GNN) forecast burned area weeks to months out [7][8]. Too coarse for us, useful for regional context.

**India.** Most work is susceptibility mapping (static "where tends to burn"), not daily forecasting: six-algorithm MODIS comparison with AUC around 0.9 [9]; AHP risk zoning in Khandwa and North Betul showing fires cluster near roads and villages [10]; a Melghat tiger reserve distribution model [11]. A 2026 Odisha conference paper attempts next-day high-res probability [12]. Human drivers named consistently: mahua and tendu collection, grazing-land clearing, crop residue burning [13][14]. I found no published daily 500 m forecast for a central Indian reserve, so Ratapani would be new ground.

## 3. Pretrained geospatial models

| Model | What it gives us | Evidence for fire |
|---|---|---|
| AlphaEarth Foundations (annual 10 m embeddings, 2017 to 2024) | Static per-cell "what kind of place is this" features, replacing hand-made land cover, roads, terrain | Victoria susceptibility models ROC-AUC above 0.92 and transferred to new regions far better than physical variables (about 25% drop for physical vs ±4% for embeddings) [15]. Weaker than Sentinel-2 for burn scar mapping [16] |
| Prithvi-EO-2.0 (NASA/IBM, HLS) | Fine-tuneable encoder for Sentinel-2/Landsat stacks, e.g. fuel state before the season | Strong at burn-scar segmentation; LoRA fine-tuning transfers well [17][18]. Not tested on forecasting |
| TimesFM / WeatherNext | Already in the pipeline plan thread | Weather is the weaker half of the signal here (see 1) |

My read: AlphaEarth is the best-supported pretrained input for the "new ignition" half. It is annual, so it captures place, not day; the daily signal has to come from recent fire, calendar and weather.

## 4. Rare events: precision vs recall

What careful papers do:
- Report PR-AUC/average precision and recall at a fixed alert budget, not accuracy or ROC-AUC alone. Accuracy above 90% is trivial when nothing burns [19].
- Split by time (hold out whole seasons) and group folds by day so neighbouring cells on the same day don't leak [20]. Spatial blocking matters too because fires cluster.
- If undersampling negatives, recalibrate probabilities afterwards; otherwise precision looks inflated against the real base rate [19][20].
- Warning from the spread benchmark: models tuned for maximum recall over-predicted burned area by up to 5,500x [3]. Recall needs a budget.

Suggested framing for us: pick the alert budget with officers (for example "top 50 cells per range per 2 days"), then maximise recall inside it. Score against a persistence baseline (fire within 2 km in the last 2 days) and the existing fire-memory model, not against FWI only.

## 5. How results reach officers today

Forest Survey of India's FAST 3.0 sends VIIRS/MODIS detections by SMS and email to registered field staff (about 130k to 214k users), email within ~5 minutes of NRSC data, SMS in 30 to 60 minutes [21][22]. Its pre-fire alerts are weekly, on 5 km grids [23]. So the gap our product fills is clear: **2-day horizon at 500 m, instead of weekly at 5 km.** Officers already trust SMS from FSI, and a KML/map layer per beat would fit what they use.

## 6. Open questions for discussion

1. **What counts as a fire?** VIIRS misses small, cool understory fires [24]. Do we add Sentinel-2 burn scars (5-day revisit) as labels, or accept "VIIRS-visible fire" as the target?
2. **Spread vs ignition.** Do we build two heads (near an active fire / no active fire nearby) or one model? The 45% neighbour-persistence share argues for treating them separately.
3. **Alert budget.** How many cells can a range officer realistically check or patrol in 2 days? This sets the threshold more than any metric does.
4. **Human calendar data.** Can the forest department share mahua/tendu collection dates, village locations, or past FIR/fire records? These are likely the strongest ignition predictors and no satellite gives them.
5. **ECMWF PoF access.** Worth requesting as a coarse daily prior?
6. **Delivery.** SMS list of cell IDs with lat/long, a daily KML, or a WhatsApp map image? Who receives it: DFO, range officer, beat guard?

## Sources

[1] [Lahrichi et al., Swin U-Net on WildfireSpreadTS (arXiv 2502.12003)](https://arxiv.org/abs/2502.12003v1)
[2] [Attention U-Net next-day prediction thesis](https://drepo.sdl.edu.sa/items/df5dd762-98b5-4acd-a4a4-913ad6fcdb9b)
[3] [WildfireSpreadBench: The Metric Decides the Model (arXiv 2609.22191)](https://arxiv.org/pdf/2609.22191)
[4] [EGU26-18849, sub-km next-day active fire forecasting](https://meetingorganizer.copernicus.org/EGU26/EGU26-18849.html)
[5] [ECMWF: Scientists present new ML tool for improved fire prediction](https://www.ecmwf.int/en/about/media-centre/news/2025/scientists-present-new-ml-tool-improved-fire-prediction)
[6] [EGU25-17607, first year of ECMWF operational fire prediction](https://meetingorganizer.copernicus.org/EGU25/EGU25-17607.html)
[7] [SeasFire cube, Scientific Data](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11876342/)
[8] [FireCastNet (arXiv 2502.01550)](https://arxiv.org/html/2502.01550v2)
[9] [Sharma et al., six ML algorithms for Indian forest fire susceptibility, IJWF](https://publish.csiro.au/WF/fulltext/WF22016)
[10] [Down To Earth: Khandwa and North Betul fire risk study](https://www.downtoearth.org.in/amp/story/wildlife-biodiversity/central-indian-forests-in-khandwa-and-north-betul-at-high-risk-of-fires-study-warns)
[11] [Verma et al., Melghat predictive distribution modelling (BioBR)](https://revistaeletronica.icmbio.gov.br/index.php/BioBR/article/download/1187/873/6024)
[12] [Next-day fire probability, ASEC 2026 (sciforum)](https://sciforum.net/paper/view/27921)
[13] [Fire risk assessment in a hotspot, Env. Monitoring and Assessment 2024](https://link.springer.com/article/10.1007/s10661-024-12960-0)
[14] [Down To Earth: understanding the people who light fires (western MP)](https://www.downtoearth.org.in/amp/story/natural-disasters/true-forest-fire-management-must-begin-not-with-extinguishing-flames-but-with-understanding-the-people-who-light-them)
[15] [Evaluating AlphaEarth embeddings for wildfire susceptibility (arXiv 2608.12663)](https://arxiv.org/pdf/2608.12663)
[16] [Annual EO embeddings and burned area mapping (arXiv 2609.25731)](https://arxiv.org/pdf/2609.25731)
[17] [Prithvi foundation model (arXiv 2310.18660)](https://arxiv.org/pdf/2310.18660)
[18] [Prithvi-EO-2.0, IBM Research](https://research.ibm.com/publications/from-pixels-to-predictions-prithvi-eo-20-for-land-disaster-and-ecosystem-intelligence)
[19] [A Machine Learning Methodology for Next Day Wildfire Prediction](https://publications.beyond-eocenter.eu/DISASTERS/A_Machine_Learning_Methodology_for_Next_Day_Wildfire_Prediction.pdf)
[20] [Cyprus ML fire risk model, ESA LPS25 poster](https://lps25.esa.int/lps25-presentations/poster/Development%20and%20Optimization%20of%20a%20Machine%20Learning%20Fire%20Risk%20Prediction%20Model%20Using%20Multimodal%20Geospatial%20and%20Climate%20Data%20in%20Cyprus.pdf)
[21] [FSI forest fire FAQ](https://fsiforestfire.gov.in/document/faq.pdf)
[22] [Down To Earth: Odisha recorded the most forest fires](https://www.downtoearth.org.in/amp/story/environment/odisha-recorded-the-most-forest-fires-in-india-last-season-78129)
[23] [ITTO: FSI fire alert types](https://www.itto.int/direct/topics/topics_pdf_download/topics_id=7812&no=4)
[24] [NRSC/NDRC webinar minutes on VIIRS in India](https://directreadout.sci.gsfc.nasa.gov/ndrc_documents/NDRC9_Webinar_Minutes_2019.05.15.pdf)

Several sources are preprints, posters or press summaries; their numbers are the authors' claims and were not re-verified here.

## 7. Update after Akkshay's answers (13 Oct)

Decisions: labels are **burn scars, not VIIRS**; budget is **5 checks per beat per day** (10 per beat over the 2-day window).

What changes:
- **Metric:** recall of burned cells within the top 5 cells per beat per day. Needs beat boundaries; I don't have them. If Ratapani's ~900 km² grid (3,614 cells, 3,261 mostly forest) holds 60 to 90 beats (inferred, not checked), each beat has 40 to 60 cells, so 10 checks over 2 days covers roughly 15 to 25% of a beat. That is a generous budget compared with the "top 5% statewide" framing in section 1.
- **Labels:** Sentinel-2 (10 to 20 m, 5-day revisit) plus Landsat 8/9 (30 m) give a clear look every 2 to 3 days in the dry season (inferred from combined revisit; Feb to May is mostly cloud-free). The closest existing product, FireCCI's Sentinel-2 Small Fire Database, mapped about 80% more burned area than MODIS MCD64A1 in Africa with ~26% omission and ~19% commission [25][26]; nothing equivalent exists for India, so we'd build our own. A Central India study found global products do poorly on small fires in open woodland, which supports this choice [27].
- **Two traps:** (1) a scar's date is only known to the gap between clear images, which is about the same as or wider than the 2-day horizon; (2) dry deciduous leaf fall in Feb to Apr lowers NBR too, so a loose dNBR threshold flags unburned forest as burned [28]. Char-specific SWIR indices or a fine-tuned burn-scar model (Prithvi-EO-2.0 was built for this) plus field-checked samples are needed.
- **Cell label:** decide what fraction of a 500 m cell must be scarred to count as "burned" (for example any scar ≥ 0.5 ha, or ≥ 5% of the cell).

[25] [Fire_cci Small Fire Database](https://geogra.uah.es/fire_cci/fireccisfd11.php)
[26] [ESA: new version of the Small Fire Database](https://climate.esa.int/en/news-events/new-version-of-small-fire-database-released)
[27] [Central India burned-area evaluation, Frontiers in Forests and Global Change 2022](https://doaj.org/article/10663738fd534c26b7991e5c6c52cd31)
[28] [Digital Earth Africa: burnt area mapping with Sentinel-2](https://docs.digitalearthafrica.org/en/latest/sandbox/notebooks/Real_world_examples/Burnt_area_mapping.html)

**Decided (13 Oct):** window labels. Keep the 2-day forecast and train on each scar's date window between clear images, with no VIIRS used even for dating. In practice the model predicts a daily burn probability per cell. The training loss scores the chance that the cell burned at some point in the observed window, so a scar seen between day t and day t+4 is credited to that whole window rather than to one guessed day.

## 8. Datasets for precise burn-scar labels (13 Oct)

No ready-made, dated, 10 m burn-scar product exists for India, so the labels need to be built. Recommended layers, most to least important:

| Layer | Resolution / timing | Role | Notes |
|---|---|---|---|
| Sentinel-2 L2A (2016+) + Landsat 8/9, or NASA HLS (harmonised) | 10 to 30 m; clear view every ~2 to 3 days in the dry season | **Main label source**: our own scar maps with a date window per scar | Free in Earth Engine. Copes with Ratapani's ~900 km² easily |
| Prithvi-EO-2.0 BurnScars model (IBM/NASA, HLS) | 30 m | **Detector** to turn the imagery into scar masks | Trained on US scars; needs fine-tuning on Ratapani samples to handle leaf fall [29][30]. A ~20k-scene training set is on Hugging Face [31] |
| PlanetScope | ~3 m, near daily | **Precision check**: sharpen scar edges and dates on a sample, measure the S2 map's error | Free E&R Basic tier needs a university email: 3,000 km²/month, 30-day delay [32]. NICFI tropical mosaics are monthly and ended July 2025 [33]. A PlanetScope study in India found 5% more burnt area than Landsat and 9% more than Sentinel-2 [34] |
| Field GPS polygons from the forest dept; NRSC/Bhuvan event maps | ground truth | **Validation** and the leaf-fall vs. burn check | NRSC's Sariska 2022 map gave 1 km² from AWiFS vs 11.3 km² from Sentinel-2, so sensor choice matters a lot [35] |
| GABAM v3 (Landsat, annual, 2014 to 2024) | 30 m, annual only | **Sanity check** on yearly totals; no dates | Zenodo, Dec 2025 release [36] |
| MCD64A1 (500 m), FireCCI51 (250 m) | coarse | Benchmark only | Known to miss small woodland fires in Central India [27] |

[29] [Prithvi-EO-2.0 paper (arXiv 2412.02732)](https://arxiv.org/pdf/2412.02732)
[30] [IBM-NASA geospatial on Hugging Face](https://huggingface.co/ibm-nasa-geospatial)
[31] [Prithvi burn-scar training dataset (Hugging Face)](https://huggingface.co/datasets/fireviewer/prithvi-burnscars-training-dataset-v1)
[32] [Planet Education and Research program](https://www.planet.com:443/markets/education-and-research)
[33] [NICFI basemaps, Asia (Earth Engine catalog)](https://developers.google.cn/earth-engine/datasets/catalog/projects_planet-nicfi_assets_basemaps_asia?hl=pt-br)
[34] [Vadrevu, PlanetScope burnt-area pilot (NASA CSDA)](https://www.earthdata.nasa.gov/sites/default/files/imported/CSDAP-Pilot-Vadrevu.pdf)
[35] [NRSC Sariska 2022 fire report](https://www.nrsc.gov.in/sites/default/files/pdf/DMSP/sariska_2022fires_brief_report.pdf)
[36] [GABAM 2014-2024 (Zenodo)](https://zenodo.org/records/17707433)

**Decided (13 Oct), no Planet access and no field polygons available:** Sentinel-2 + Landsat 8/9 (HLS) in Earth Engine for the 2017 to 2026 seasons. Burn indices seed the candidate scars. Prithvi-EO-2.0 BurnScars is fine-tuned on Ratapani chips. Validation uses about 400 stratified points checked by eye on before/after Sentinel-2 SWIR composites, plus dated Google Earth high-res imagery where it exists. A scar must show char and no quick green-up, which filters out leaf fall. A cell counts as burned if 0.5 ha or more of it is scarred. VIIRS is not used.
