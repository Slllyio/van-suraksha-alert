# Machine learning for burn scars: how to get a better final scar from Sentinel-2 / Landsat (scouting round 16, topic "scarml", 16 Oct 2026)

Question from Akkshay: how can we decode the final burn scar more efficiently and more accurately than the hand-built rule behind **scar outlines v2 (2026-10-16)**?

What I read for this note: the scar `README.md`, `reference/v2_2026-10-16/MANIFEST.md` and `USE_AND_LIMITS.md`, and `mp/README.md`, plus the headings of every earlier scouting note.

**What this note does not repeat.** These sources were already read in full in `alert_burn_scars_fullread.md`, so they are only referred to here:
- FireCCISFD20 / SFD11 ATBD
- Padilla 2026 NRT S2+VIIRS
- Roteta 2021 GEE
- BAMT
- Chandel 2022 (Central India)
- Hu, Ban & Nascetti 2021
- BiAU-Net
- the Prithvi-EO-2.0 BurnScars model card
- Tienaho 2025

Others are covered elsewhere:
- **`daily_scar_dating.md`:** Pinto 2021, Li & Roy 2017, Boschetti 2019 and the HLS facts. It also holds our own result that Sentinel-3 SYN cuts scar windows to about 1-2 days.
- **`burn_dating_validation.md`:** Giglio 2018 (MCD64A1) and the latent-class / triple-collocation recipes.
- **`high_res_imagery.md`:** NICFI, PlanetScope and Wayback access.

The hands-on experiment (`burn_scar_ml_experiment.md`) belongs to another agent. Nothing here was run on our data.

Reading marks: **FULL** means the full text was obtained and every method and result section relevant here was read. **PARTIAL** means the full text was obtained but only the key sections were read, or the paper was read through code or a summariser. **ABSTRACT ONLY** means only the abstract or publisher summary was seen. My own reasoning is marked **[inference]**.

---

## Headline findings

1. **Deep change-detection models beat both index thresholds and random forests by a wide margin when the labels are good.** On Greek fires, the burnt-class F1 scores were:
   - best single index (dMIRBI): 64%
   - dNBR: 45%
   - random forest: 67%
   - SVM: 69%
   - Siamese U-Net BAM-CD: **88.5%** (FLOGA, FULL)

   On California fires, Otsu index maps reached F1 ≤ 0.29 and a plain U-Net on pre+post input about 0.71 (CaBuAr, FULL).

   Most of the gain comes from spatial context and from learned rejection of look-alikes, not from new bands.

2. **A network trained on rule labels learns the rule.** A U-Net trained on SWIR-rule masks reproduced them at IoU 0.84 (Mitra 2026). Knopp 2020 showed that a U-Net copies the "mapping style" of its labels: perimeter labels gave blobby scars with unburned islands filled in, and pixel labels gave sharp edges plus water false alarms.

   So **training on v2 outlines as they are would mostly copy v2, circle tie and growth inflation included** [inference]. A model only adds accuracy if:
   - the labels are cleaned with evidence the rule did not use (Wayback, decoys, multi-year consistency, S2/Landsat fire pixels); and
   - the model sees information the rule ignores (spatial context, the full time series).

3. **The biggest structural fix is to make the map fire-independent first, then tie patches to alerts.** Every large operational product works this way: MCD64, GABAM, USGS Landsat BA, MapBiomas Fogo, Sentinel2BAM. Each makes a per-pixel burn probability first, then seeds at high probability and grows at lower probability.
   - Landsat BA (Hawbaker 2020, FULL): seeds at P ≥ 0.96, patches < 2 ha dropped, growth into P ≥ 0.71 by random-walker segmentation.
   - GABAM (FULL): seeds at P ≥ 0.95, components < 11 px dropped, growth into P ≥ 0.5.

   Our v2 limits file already measured the cost of dropping the circle rule: background "burned" patches of about 0.5 ha per km² per image pair, and about 80% of the extra ground near fires looks real. A learned probability map plus a calibrated threshold is how to cut that background.

4. **Severity classes stay hard. Burned vs unburned does not.** Prithvi-EO-2.0 on HLS burn intensity scored mIoU about 31%. The lowest burned classes reached IoU 21-23%, while no-burn reached 73-76%.

   For our 99%-low-severity litter fires, aim for a **binary burned probability plus a sub-pixel "fraction burned"**, never severity classes.

5. **Sentinel-1 adds little for our case.** Belenguer-Plomer 2021 (FULL) found that a CNN on Sentinel-1 alone reached Dice about 0.55. Adding Sentinel-1 to Sentinel-2 did not improve accuracy where clouds were not a problem; its value is filling cloud gaps.

   Our season is dry and almost cloud-free, and C-band sees the canopy, not litter. So **SAR is not worth it for the scar thread** [inference]. Use it only if a monsoon-edge or haze gap analysis says otherwise.

6. **Dating:** the deep "sequence in, per-day probability out" design (BA-Net code, PARTIAL) dates a burn as the **argmax over days** of the per-day burned probability. Its input is a 64-day stack of daily images plus an active-fire layer.

   For us the daily layer exists: Sentinel-3 SYN, plus VIIRS and S2/Landsat fire pixels. The 20 m stack is 2-5 day. So v3 dating = per-pixel argmax of a fused per-day probability, stored as `t_star` and `dt` the MCD64 way.

7. **Validation must be design-based to be credible.** That means a stratified random sample in space and time, interpreted on independent high-resolution imagery, using combined-ratio estimators of CE, OE, Dice and relative bias (Padilla 2015, Boschetti 2016, both FULL).
   - Stratifying on activity cut the standard error of OE to 74-77% of simple random sampling, CE to 42-46%, and area to 46-47%.
   - Proportional allocation gives almost no gain.
   - Our Wayback set (511 fires with an image within 40 days, 273 of them in 2025) is the natural frame. Add NICFI monthly 4.77 m mosaics for coverage.

8. **One AMD RX 9060 XT (16 GB) is enough for everything here.**
   - The RX 9060 XT is supported in ROCm 7.0.2 on Linux (Phoronix, Oct 2025) and in AMD's PyTorch-on-Windows release based on ROCm 7.2 (Jan 2026; release-note page not reachable, so search-level only).
   - Prithvi-EO-2.0 states that all its fine-tuning runs need a single GPU.
   - A Knopp-size U-Net ran at 0.26 s per megapixel on a 2017-era Quadro P4000 (2.2 s/MP on a 6-core CPU).
   - At that speed, all-MP forest at 20 m for one Feb-Jun season is roughly **0.5-1 GPU-hour** for a U-Net, or about 5 CPU-hours. Prithvi-300M would be about 1-3 GPU-hours [inference, arithmetic below].

---

## Part A. Deep segmentation for burned area

### A1. Knopp, Wieland, Rättich & Martinis 2020, "A deep learning approach for burned area segmentation with Sentinel-2 data", *Remote Sens.* 12:2422. https://doi.org/10.3390/rs12152422 **FULL** (MDPI CDN PDF)

**Data**
- 184 Sentinel-2 scenes (mostly 2017-18), cut into 2,637 tiles of 256×256 at 10 m, split 60/20/20.
- Labels: 70% ICNF Portugal perimeters, 9% CAL FIRE and 21% DLR's own two-phase pixel masks, cleaned with a 3×3 closing and opening.
- Augmented to 6,272 training tiles (brightness ±0.2, contrast ±0.4, shift, scale ±0.5, rotation; each with p = 0.75). The average tile was 20% burned, and **single-class tiles (all burned or all unburned) were kept on purpose**.

**Model and training**
- Single post-fire L1C TOA image, no atmospheric correction.
- 5-level U-Net with batch norm, sigmoid output, binary cross-entropy.
- Adam with learning rate 1e-3, halved after 5 epochs without improvement; early stopping after 20. Batch 16, about 4 h on a Quadro P4000.
- Inference uses 10% tile overlap blended with a tapered cosine window.

**Bands (Table 2)**

| Bands | Accuracy | Kappa | Note |
|---|---|---|---|
| All 13 | 0.97 | 0.90 | |
| B2, B3, B4, B8, B11, B12 | 0.96 | — | Chosen as the final set |
| RGB only | — | 0.75 | Clearly worse |

**Final test (545 tiles)**

| Model | OA | Kappa | Precision | Recall | F1 | Inference |
|---|---|---|---|---|---|---|
| U-Net | 0.98 | 0.94 | 0.95 | 0.95 | 0.95 | 2.20 s/MP CPU, **0.26 s/MP GPU** |
| Random forest | 0.96 | 0.87 | 0.93 | 0.87 | 0.90 | 3.80 s/MP |

- On three independent EMS fires, precision was 0.77-0.96 and recall 0.97-0.99. The full chain took 193 s per scene.
- False alarms came from volcanic rock, dark water, agricultural fields and open-cast mines. The model also over-merged: unburned forest islands of up to 4 ha were filled in.

**Label lessons (section 4)**
- A model trained only on perimeter labels gives gradual probability edges and fills holes.
- A model trained only on pixel masks gives sharp edges but flags water as burned.
- Removing single-class tiles raised the false burned probability on fields and airports.
- The authors conclude: "the neural network always learns by imitation … misclassifications in the inputs will be reproduced."

**Concrete action for us (scar thread)**
1. If we train a scar U-Net, keep **all-unburned decoy chips and all-burned interior chips** in training. The decoys are the 3 km-shifted controls and the Wayback decoys.
2. Use **pixel-level labels** (pass-1 core pixels), not grown outlines, to avoid filled-in islands. Grown outlines are already known to swallow ground: small scars miss 88% of nearby burned ground, and growth inflates false scars.
3. Expose the probability threshold to users, as Knopp does: 0.5 by default, higher for "clearly burned".
4. Inputs: post image plus pre image (see A3), B2, B3, B4, B8A, B11 and B12 at 20 m.
5. **Expected effect [inference]:** a cleaner edge and fewer shadow and crop-edge false scars. A single-date model will not separate old from new burns in our two-season landscape, so use it only bi-temporally.

---

### A2. Jakubik et al. 2023, "Foundation models for generalist geospatial artificial intelligence" (Prithvi-EO-1.0-100M), arXiv:2310.18660. **PARTIAL** (all burn-scar sections, fine-tuning set-up and tables read)

**Data**
- HLS burn scars: MTBS perimeters 2018-21, CONUS.
- The image is the first HLS scene more than 1 month but less than 3 months after the fire start (fully grown, not yet recovered), with ≤ 10% cloud. 805 scenes of 512×512.

**Fine-tuning**
- Neck of four ConvTranspose2D layers plus one conv layer.
- Batch 4, 50 epochs, learning rate 1.3e-5, unweighted Dice loss.

**Results (Table 3)**

| Model | Fire-scar IoU | Fire-scar F1 | mIoU |
|---|---|---|---|
| U-Net (DeepLabV3) | 71.01 | — | — |
| ViT-base | 69.04 | — | — |
| Prithvi, not pretrained | 72.26 | 83.89 | 84.01 |
| **Prithvi, pretrained** | **73.62** | 84.81 | 84.84 |

- **Data efficiency:** cutting the fine-tuning set from 540 to 135 images gave "comparable" performance (Fig. 10b).
- A frozen encoder was worse than updating the encoder.

**Concrete action for us**
- Pretraining buys about 1.4-2.6 IoU points at most. It matters mainly because we will have few clean labels (hundreds of chips).
- The 1-3-month post-fire image rule is **wrong for us**: litter scars fade within weeks (Wayback AUC drops from 0.91 at 1-3 days to 0.84 at 16-40 days). Use post images 1-15 days after.

---

### A3. Szwarcman et al. 2024/25, "Prithvi-EO-2.0: a versatile multi-temporal foundation model for Earth observation applications", arXiv:2412.02732. **PARTIAL** (burn-scar and burn-intensity tasks, training set-up, compute)

**Model**
- ViT with 300M or 600M parameters.
- MAE pretraining on 4.2M HLS samples with 4 time steps, at 30 m. TL variants add time and location embeddings.
- Pretraining took about 21,000 A100-hours (300M), but "**all fine-tuning experiments … require a single GPU**."

**Wildfire scar fine-tune**
- Images resized to 448, random crop 224, flips, UPerNet decoder, cross-entropy, 50 epochs (early stopping after 20), 10 learning-rate / weight-decay trials, 10 seeds.

| Model | Scar IoU (sd) | mIoU |
|---|---|---|
| Prithvi-EO-1.0-100M | 76.8 (1.4) | 86.9 |
| Prithvi-EO-2.0-300M | 79.9 (0.8) | 88.6 |
| Prithvi-EO-2.0-300M-TL | 81.1 (1.6) | 89.3 |
| **Prithvi-EO-2.0-600M (and -TL)** | **83.2 (1.1)** | 90.5 |

The Hugging Face 300M checkpoint card (earlier note) reports burned IoU 87.52 on its own split.

**Burn intensity (5,692 BAER chips of 224, pre / during / post triplets, LoRA fine-tune)**
- Learning rates 5e-4 (encoder) and 5e-5 (decoder), cosine schedule, weight decay 0.05.

| Model | mIoU | IoU no-burn | Low-severity classes (IoU1 / IoU2) |
|---|---|---|---|
| U-Net | 26.3 | 67.5 | — |
| Prithvi-300M | 31.2 | 73.3 | 22.7 / 22.3 |
| Prithvi-600M | 31.1 | 75.9 | — |

The authors blame smoke in the "during" image and speckled small high-severity islands inside low-severity labels.

**Concrete action for us**
1. If we use a foundation model, use **Prithvi-EO-2.0-300M-TL with T = 2-4 (pre, post, check, plus a same-season image from an earlier year), LoRA**, and a binary head. The same-year baseline handles leaf fall, as the Tienaho detrending does.
2. Skip severity. Binary burned is learnable; low-severity classes are at IoU about 22% even for the best model.
3. **Expected effect [inference]:** a small gain over a well-trained U-Net (+3-6 IoU points in their tables). Mainly label efficiency.

---

### A4. Sdraka et al. 2024, "FLOGA: a machine learning ready dataset, a benchmark and a novel deep learning model for burnt area mapping with Sentinel-2", IEEE JSTARS, arXiv:2311.03339. **FULL**

**Data**
- 326 Greek fires, 2017-21, from 22 ha to 45,284 ha.
- Pre- and post-fire L2A S2 plus MODIS. Labels are Hellenic Fire Service perimeters (semi-automatic plus photo-interpretation).
- Split 60/20/20 by event, with **an equal number of all-unburned patches**: 826 training, 189 validation and 152 test patches.

**Results: burnt-class F1 (precision / recall), Table V**

| Group | Method | Burnt F1 (P / R) |
|---|---|---|
| Single global index thresholds | dNBR | 45.1 (34.0 / 67.1) |
| | dNBR2 | 52.8 |
| | **dMIRBI** | **64.1** (58.3 / 71.1) |
| | RdNBR | 46.4 |
| | RBR | 44.6 |
| | dBAIS2 | 31.0 |
| | dNDVI | 45.9 |
| | dNDWI | 32.2 |
| Classic ML | RF | 67.4 |
| | XGBoost | 61.5 |
| | SVM | 68.9 |
| | MLP | 56.5 |
| Change-detection deep learning | FC-EF-Diff | 71.2 |
| | FC-EF-Conc | 72.2 |
| | ADHR-CDNet | 83.6 |
| | ChangeFormer | 85.7 |
| | SNUNet-CD | 86.5 |
| | **BAM-CD** | **88.5** (85.6 / 91.6; IoU 79.3) |

- **All indices** suffer high commission. In the ML ablation, using all features (bands, indices, differenced indices) beat differenced indices alone (RF F1 67.4 vs 59.4).

**BAM-CD architecture**
- Siamese ResNet-101 encoders (shared weights) on pre and post images, with concatenated features.
- Decoder with channel and spatial attention, skip connections, all 10 m and 20 m bands resampled to 20 m.
- 83.7M parameters, Adam with learning rate 1e-3. **Plain BCE beat focal, Dice and BCE+Dice**; the Dice-based losses were unstable.

**Code and licences**
- Code: https://github.com/Orion-AI-Lab/FLOGA (MIT).
- Weights for v1 and v2 (pseudo-Siamese, heavier augmentation) are on Dropbox, linked from the README.
- GeoTIFF data: https://huggingface.co/datasets/orion-ai-lab/FLOGA-GeoTIFFs (CC-BY-4.0).

**Concrete action for us (scar thread)**
1. **dMIRBI is the best single index here, about 20 F1 points above dNBR.** Add it, with dNBR2, to the pass-1 rule as a second vote. A cheap test is to recompute the Wayback real-vs-decoy AUC using dMIRBI instead of the relative dNBR.
2. For a learned model, a **bi-temporal Siamese U-Net** (BAM-CD v2 weights, or a ResNet-34 Siamese U-Net from `segmentation_models_pytorch`) is the right family. Fine-tune on our chips with BCE.
3. **Expected effect [inference]:** if our labels were as clean as FLOGA's, about +20 F1 points over our rule-like index baseline. With our noisy labels, perhaps +5-10. The gain is capped by label quality (headline 2).

---

### A5. Rege Cambrin, Colomba & Garza 2024, "CaBuAr: California burned areas dataset for delineation", IEEE GRSM, arXiv:2401.11519. **FULL**

**Data**
- S2 L2A pre and post at 20 m (12 bands, 512×512), CAL FIRE perimeters, fires from 2015.
- Hugging Face `DarthReca/california_burned_areas`, licence **CDLA-Permissive-2.0**.

**Results**

| Method | F1 | IoU | Note |
|---|---|---|---|
| Otsu on NBR / NBR2 / BAI / BAIS2 (and differenced) | ≤ 0.29 | — | Separability index ≤ 0.35 |
| U-Net, post only | about 0.69 | — | |
| U-Net, pre+post as 24 channels | **about 0.71** | about 0.58 | Best |

- Model sizes: U-Net 31M parameters, SegFormer-B0 3.8M, SegFormer-B3 47M. **U-Net was best in every setting; SegFormer-B3 did not justify its size.**
- Adding the pre-fire image to the indices did not help Otsu.

**Concrete action for us:** a plain U-Net with stacked pre+post channels is a sound, cheap baseline before any foundation model. Its 31M parameters fit easily in 16 GB.

---

### A6. Seydi, Hasanlou & Chanussot 2022, "Burnt-Net" (single post-fire S2, morphological layers). **ABSTRACT ONLY** (no open copy found)
Reported overall accuracy above 97% on single post-fire S2. No class-level F1 was visible and no code was found. It adds nothing over A1 and A4 for us.

### A7. Mitra, Narimani & Farajpoor 2026, "A Sentinel-2 benchmark dataset for deep-learning active-fire segmentation across 25 California wildfires", arXiv:2609.16199. **FULL** (short data paper)

**Data and method**
- 2,148 B12/B11/B8A chips of 512×512. Masks come from a SWIR brightness and NIR contrast rule plus constrained growth; fire labels cover 0.0766% of cells.
- Split by incident: 18 training fires, 3 validation, 4 test.

**Results**
- A ResNet-34 U-Net **trained on the rule labels** reproduced them at pooled test IoU 0.837 (precision 0.897, recall 0.926). The best threshold, picked on validation, was 0.99.
- A blind analyst review of 233 test chips: chip agreement 89.7%, and 88.5% of rule components overlapped an analyst fire. About 30% of rule-positive chips were visually unconfirmed, but those held only about 1% of rule-positive pixels.
- Licences: CC-BY-4.0 data (Zenodo 10.5281/zenodo.22713948), MIT code.

**Concrete action for us:** this measures what happens if we train on our own rule. The model matches the rule at IoU about 0.84 and inherits its errors. Score any learned scar model against **independent** checks (Wayback blind set, decoys), never against v2.

---

## Part B. Per-pixel probability and dating from dense time series

### B1. Hawbaker et al. 2020, "The Landsat Burned Area algorithm and products for the conterminous United States", *RSE* 244:111801. https://doi.org/10.1016/j.rse.2020.111801 **FULL** (author PDF via bobscapes.org)

**Training points**
- Burned points: 1 per 100 burned MTBS pixels, up to 1,500 per tile, each checked by eye.
- Unburned points: 1 per 1,000 pixels per NLCD class, up to 100 per class per tile.
- For each point, 12 random unburned observations are kept, plus only the **first** burned observation. 100 FMask cloud, shadow, water and snow pixels per year are added as negatives.
- Total: 127,776 points, split 50/50.

**Model**
- Gradient-boosted regression trees. Grid: learning rate 0.1 / 0.05 / 0.01 and splits 1 / 3 / 5 / 7, starting from 2,000 trees and pruned to the smallest count at the maximum AUC.
- **Stepwise forward predictor selection** on AUC. Candidates correlated ≥ 0.95 with a chosen predictor are dropped; selection stops when AUC gains < 0.001.
- Predictor types: scene values, a "reference" (pre-disturbance summary) and change values.
- Top predictors: **NBRT1 = (NIR − SWIR2·Thermal)/(NIR + SWIR2·Thermal)** and its 3-year lagged mean, VI6T (NIR/thermal), VI45 and NDVI. More than half include thermal.

**Classification (per scene)**
1. Seed: P ≥ 0.96.
2. Drop patches < 2 ha (22 px).
3. Grow by random-walker into P ≥ 0.71.
4. Drop pixels < 0.90 inside fires, to keep within-fire patchiness.
5. Remove annual burns that persist over years.

**Accuracy**

| Reference | Omission | Commission |
|---|---|---|
| High-resolution commercial imagery | 19% | 41% |
| Landsat pairs (crops and pasture excluded) | 40% | 28% |

The relative bias stayed positive (+39%) because commission exceeded omission.

**Concrete action for us (scar thread, stage 1 of v3)**
1. Replace the fixed "0.10 above chip median" rule with a **per-look LightGBM burn probability**. LightGBM is already in the project stack.
2. Features: NBR, NBR2, MIRBI, NDVI, B8A, B11, B12 at the look; the same minus the pixel's own **3-5-year same-day-of-year baseline** (the "reference" idea, which also absorbs leaf fall); the same minus the previous clear look; and the chip-relative drop.
3. For Landsat 8/9 only, add **NBRT1** from TIRS (B10) [inference: litter fires leave warm black ground, the same physics as Hawbaker's top predictor].
4. Then seed, grow and drop with *calibrated* thresholds tuned on the Wayback set (the 0.96 / 0.71 / 2 ha pattern).
5. **Expected effect [inference]:** fewer chance patches when the circle rule is lifted. The aim is to bring the 0.5 ha/km² control background toward 0.1-0.2 at the same recall. Measure it with `check/no_circle.py`.

---

### B2. Long et al. 2019, "30 m resolution global annual burned area mapping based on Landsat images and Google Earth Engine" (GABAM 2015), *Remote Sens.* 11:489 (arXiv:1805.02579 version). **FULL**

**Training and features**
- 12,881 hand-collected samples (6,735 burned, 6,146 unburned) from 120 stratified-random Landsat-8 scenes.
- Random forest with 100 trees in probability mode.
- 14 features: 6 bands plus NBR, NBR2, BAI, MIRBI, NDVI, GEMI, SAVI and NDMI. RF importance ranked **NBR2, BAI, MIRBI, SAVI** highest; NIR and SWIR2 were the most useful raw bands.

**Per-pixel annual logic**
- Take p_max over the year's looks, its date t1 and NDVI1/NBR1 on that date.
- Keep the pixel only if all four hold:
  - max NDVI over two years > 0.2;
  - max NDVI − NDVI1 > 0.2;
  - min NBR of the previous year − NBR1 > 0.1;
  - green-up date t2 < t1, or t2 − t1 < 100 days.
- Seeds at p_max ≥ 0.95; components < 11 px dropped; 8-connected growth into p ≥ 0.5.

**Accuracy**
- Global: CE 13.17%, OE 30.13%.
- **Broadleaf deciduous forest: CE 23.6%, OE 34.9%.**
- The reasons for omission are fast tropical recovery and weakly burned pixels inside perimeters.
- Data: https://vapd.gitlab.io/post/gabam2015/

**Concrete action for us:** the **"NBR below last year's minimum NBR by > 0.1"** test is a cheap, fire-independent leaf-fall guard for January-February. Normal leaf fall happens every year, so it does not push NBR below the previous year's minimum [inference]. Add it as a third gate next to the persistence check. Expected effect: fewer January false scars, at some loss in recall where the previous year also burned.

---

### B3. Alencar et al. 2022, "Long-term Landsat-based monthly burned area dataset for the Brazilian biomes using deep learning" (MapBiomas Fogo collection 1), *Remote Sens.* 14:2510. **FULL**

**Method**
- Annual quality mosaic from the **minimum-NBR look per pixel**, keeping that look's bands (Red, NIR, SWIR1, SWIR2) and its **date**, which becomes the burn month.
- A deep MLP classifier per biome region: learning rate 0.001, batch 1,000, 7,000 iterations. 154,261 Landsat scenes (about 108 TB) processed on Earth Engine.

**Accuracy**
- Overall 89.35%; user's accuracy 93.2%, producer's 85.13%; omission 14.87%, commission 6.80%. The validation used segment-interpreted grid cells with weighting.
- Omission was linked to **low-intensity understory fires**, mainly in the Amazon. Commission came from crop stubble and dry lagoons.
- Classifying single images instead of the annual minimum-NBR mosaic gained only 1.2%.

**Concrete action for us:** a **seasonal minimum-NBR composite plus its date** is a cheap fire-independent first map for all-MP. One composite per season instead of one chip per alert gives orders of magnitude fewer reads [inference]. It is coarse for dating; use it for the "where", and BA-Net-style daily fusion (B4) for the "when".

---

### B4. Pinto, Libonati, Trigo, Trigo & DaCamara 2020, "A deep learning approach for mapping and dating burned areas using temporal sequences of satellite images" (BA-Net), *ISPRS J.* 160:260-274. **PARTIAL** (abstract plus the open code `mnpinto/banet`: `models.py`, `predict.py`, `nrt.py`, `data.py` read; paper not open)

**From the code**
- `BA_Net(in_ch=4, n_classes=1, sequence_len=64)`. Inputs: VIIRS Red, NIR, MIR reflectance plus an active-fire layer, on a 64-day daily sequence.
- Space-time U-Net: the first block is a 7×7 spatial conv, a 7-day temporal conv and an LSTM; then 3×3 spatial and 7/5/3-day temporal convs. Channels 32-64-128-256-256, dropout 0.2, 128-px tiles with 100-px steps.
- Output is a **burned probability per pixel per day**:
  - burned area = max over days ≥ threshold (0.5 monthly; 0.05-0.1 in near-real-time);
  - **burn date = argmax over days**.
- Near-real-time mode re-runs daily on the last 64 days.

**From the abstract:** competitive with MCD64A1 and FireCCI51 in area despite 750 m input, better dating, and works at low burned fractions. An earlier note quotes the paper as giving date uncertainty below 2 days for over 90% of pixels.

**Code and licence:** https://github.com/mnpinto/banet (`pip install banet`). Pretrained weights for VIIRS are linked; the training set is about 160 GB. I did not check the licence.

**Concrete action for us (dating, stage 3 of v3)**
1. Build a per-pixel daily evidence stack over each scar window (5-10 days). Layers:
   - Sentinel-3 SYN 300 m daily NBR drop (our own tests show it narrows windows to about 1-2 days);
   - VIIRS / MODIS / NOAA-20 detections as distance kernels;
   - S2/Landsat fire pixels.
2. Take the **argmax day** of a small fused model: first a logistic model, later a BA-Net-style 1D temporal CNN.
3. Train it on the 54-55% of first burns that already carry a FIRMS / fire-pixel day.
4. Store `t_star` and `dt`.
5. **Expected effect [inference]:** "right day" goes from 37% (uniform guess) to the 74-81% seen with S3 alone, a little higher with fusion.

---

### B5. Zhao et al. 2019, "Detecting change-point, trend, and seasonality in satellite time series data … a Bayesian ensemble algorithm" (BEAST), *RSE* 232:111181. **ABSTRACT ONLY** (the publisher returned 403 and the NVA repository is JavaScript-only)
BEAST averages many piecewise trend-plus-harmonic models and returns a **probability of a change point at every date**, with uncertainty. Package: `Rbeast` for R, Python and Matlab.

**Concrete action [inference]:** BEAST's per-date change-point probability is a ready-made "probability the burn happened on day d" feature for B4. Run it on the 5-year S2/Landsat NBR series per scar pixel. It is slow per pixel, so run it on scar pixels only.

### B6. Yan, He, Wang, Zhang, Liang & Zhang 2022, "Inter-comparison of four models for detecting forest fire disturbance from MOD13A2 time series", *Remote Sens.* 14:1446. **FULL**
- On a benchmark of dated Chinese fires using 16-day MODIS NDVI, successful detection was:
  - BFAST 96.2% (BIC-based breakpoints);
  - Prophet 87.9%;
  - CCDC and LandTrendr lower.
- Shared problems: overfitting and **detection delay**.

**Concrete action:** for **dating**, any breakpoint method on a 16-day series is far coarser than our 5-day windows. Breakpoint methods only help as a **yes/no persistence feature**, not as a dater [inference]. Do not spend effort on CCDC or LandTrendr for dates.

---

## Part C. Learning from weak and noisy labels without circularity

### C1. Mithal, Nayak, Khandelwal, Kumar et al. 2018, "Mapping burned areas in tropical forests using a novel machine learning framework" (RAPT), *Remote Sens.* 10:69. **FULL**

**Stage 1**
- A classifier trained with **active fires as noisy labels**: 20,000 active-fire and 20,000 no-fire pixels per tile, positives only in active-fire clusters > 10 pixels.
- Model: "SeqRep", a 55-weight network over 46 time steps × 7 MODIS bands. It learns both the scar signature and the fire season.
- Threshold chosen to maximise user's × producer's accuracy, with a noise-robust estimate of both.

**Stage 2:** confident burn = scar classifier **and** an active fire in the same year.

**Stage 3:** grow into scar-classifier pixels within 5 MODIS pixels of a confident burn (results unchanged for 5-10).

**Validation:** 19 Landsat reference maps (BAMS). User's accuracy: RAPT 53%, MCD64 61%. **Producer's accuracy: RAPT 55%, MCD64 27%.** RAPT found about 3× the MCD64 burned area.

**Concrete action for us:** this is exactly our set-up (VIIRS as noisy positives). The lesson: **use the alerts to pick training positives and to confirm, but let the classifier find the scar**. Then the alert tie can be applied afterwards as a separate, documented step. Pick the threshold by maximising precision × recall on the independent Wayback set, not on v2.

---

### C2. Northcutt, Jiang & Chuang 2021, "Confident learning: estimating uncertainty in dataset labels", *JAIR* 70:1373 (arXiv:1911.00068). **PARTIAL** (method sections 2-3 and abstract)
- Inputs are **out-of-sample (cross-validated) predicted probabilities** plus noisy labels.
- Method: per-class thresholds t_j (mean predicted probability of class j among items labelled j), a "confident joint" count matrix, then pruning by class or by noise rate.
- Open-source package `cleanlab`.

**Concrete action for us**
1. Run a 5-fold, **beat-blocked** cross-validated pixel or patch classifier on v2 labels.
2. Use `cleanlab.find_label_issues` to flag v2 pixels whose label disagrees confidently with the model.
3. Send the top flagged patches to Wayback eye-checks first (see C5).
4. **Expected effect [inference]:** the 10% of "yes" scars that are decoy-like, and the over-grown margins, get found and removed before training. This targets the "growth inflates false scars" weakness.

### C3. Kiryo, Niu, du Plessis & Sugiyama 2017, "Positive-unlabeled learning with non-negative risk estimator" (nnPU), NeurIPS (arXiv:1703.00593). **PARTIAL** (sections 2-3, the estimator and algorithm)
- Estimator: R̃pu(g) = π_p·R̂p⁺(g) + max{0, R̂u⁻(g) − π_p·R̂p⁻(g)}. The non-negativity clamp stops flexible deep models overfitting, which the unbiased uPU estimator does.
- It needs the class prior π_p (the burned share among unlabeled pixels).

**Concrete action:** our setting is PU.
- Positives: Wayback-confirmed and core scar pixels.
- Unlabeled: everything else in the chip. A ring next to a scar is **not** a clean negative (small scars miss 88% of nearby burned ground).
- Train the U-Net with an nnPU loss instead of BCE, with π_p from the no-circle burned share near fires. That share is (31.7 − 23.9)/π·1 km² ≈ 2.5% of ground within 1 km of fires, plus a 0.5 ha/km² background [inference].
- Use true negatives only from decoy chips and multi-year-unburned pixels.

### C4. Elkan & Noto 2008, "Learning classifiers from only positive and unlabeled data", KDD. **PARTIAL** (Lemma 1 and estimators)
- Under "selected completely at random", p(y=1|x) = p(s=1|x)/c, where c = p(s=1|y=1) is estimated as the mean classifier score on held-out labelled positives (estimator e1).

**Concrete action:** a cheap PU correction for the LightGBM stage-1 model.
1. Train labelled (scar core) vs the rest.
2. Divide scores by c estimated on held-out cores.
3. The labelled set is *not* selected at random (cores sit near alerts, big fires and strong drops), so treat c as a lower bound and stratify it by canopy and month [inference].

### C5. Ruzicka, D'Aronco, Wegner & Schindler 2020, "Deep active learning in remote sensing for data efficient change detection", arXiv:2008.11201. **PARTIAL** (method and results)
- Set-up: a ResNet-34 Siamese change model.
- Acquisition = **variance or entropy across an explicit ensemble** (or Monte Carlo batch-norm). Start from 25 + 25 tiles, add 100 per round.
- **Only 1.02% of the pool (850 pairs) had to be annotated** to match a model trained on the full annotated set. Explicit ensembles were somewhat better than the Monte Carlo variant.

**Concrete action (Wayback active learning loop)**
1. Train 5 model seeds.
2. Rank unlabelled fire chips that have a Wayback image within 15 days by ensemble disagreement.
3. Akkshay or an agent eye-labels 50 per round on the 0.3-0.5 m image, with the existing blind protocol and 15% decoys mixed in.
4. Retrain and repeat 5-6 rounds, about 300 chips in all.
5. **Expected effect [inference]:** most of the value of a full hand-labelled set for about 1-2% of the effort. Every labelled chip is also an independent validation point if a held-out random share is kept (Part F).

### C6. Guo, Pleiss, Sun & Weinberger 2017, "On calibration of modern neural networks", ICML (arXiv:1706.04599). **PARTIAL** (sections 1-4)
- Deep networks are over-confident, and expected calibration error (ECE) grows with model capacity.
- **Temperature scaling, a single parameter T fitted on held-out data, is surprisingly effective.** It does not change the ranking.
- Report ECE with reliability diagrams.

**Concrete action:** the per-pixel burned probability we publish must be calibrated on the independent Wayback validation strata. Use temperature scaling for the network, isotonic regression for LightGBM, and per-month or per-canopy-class calibration if ECE differs. Then a published "0.7" means about 70% of such pixels are burned on high-resolution checks.

### How to avoid circularity (synthesis) [inference]
1. **Inputs to the scar model never include VIIRS or the alert circle.** Alerts are used only to (a) choose where to sample positives and (b) attach patches to alerts *after* mapping.
2. **Scoring never uses v2 or any VIIRS-derived label.** Use only:
   - the Wayback blind set;
   - NICFI / PlanetScope eye-checks;
   - decoys (shifted outlines);
   - S2/Landsat fire pixels with no FIRMS alert (59% of fire-pixel clusters have none). This is an independent positive set for small fires.
3. **Spatial-block cross-validation by beat and by year**, so neighbouring pixels of one fire never sit in both train and test.
4. Keep a frozen **"v2-agreement" score** separate from the **"truth" score**. A model that raises v2-agreement but not truth is copying the rule (A7).

---

## Part D. Sub-pixel fraction and indices for litter fires under canopy

### D1. Smith, Lentile, Hudak & Morgan 2007, "Evaluation of linear spectral unmixing and dNBR for predicting post-fire recovery in a North American ponderosa pine forest", *IJRS* 28:5159. **FULL** (USFS Treesearch PDF)
- Method: three-endmember linear unmixing (green vegetation, senesced vegetation, char), sum-to-one constrained, on Landsat. Spectra came from a lab and field library resampled to Landsat bands.

| Predicting | Char fraction | dNBR |
|---|---|---|
| % live trees one year after | r² 0.56 (SE 28.0) | r² 0.55 |
| Organic litter weight | r² 0.55, **SE 4.78 g/m²** | r² 0.52, SE 8.01 g/m² |

- Where litter fell below 1 g/m², the minimum char fraction was 0.98.

**Concrete action for us (fuel and scar threads):** a 3-endmember unmix (green leaf, dry teak litter, char/ash) on post-fire S2 gives a per-pixel **fraction burned**, which is what "partly burned 20 m pixel under canopy" means.
- **No field data are needed.** Endmembers can come from the image: char from the darkest core pixels of fresh large scars, litter from unburned March forest floor in canopy gaps, green from April-May flushers.
- **Expected effect [inference]:** a continuous litter-consumption layer for the fuel thread, and a better "faint" decision. The gain is mainly in SE, not in r².

### D2. Ngadze, Mpakairi, Kavhu, Ndaimani & Maremba 2020, "Exploring the utility of Sentinel-2 MSI and Landsat 8 OLI in burned area mapping for a heterogenous savannah landscape", *PLoS ONE* 15:e0232962 (PMC7252594). **FULL**

| Site | S2 (OA / kappa / TSS) | L8 (OA / kappa / TSS) |
|---|---|---|
| Site 1 | 0.86 / 0.74 / 0.76 | **0.92 / 0.85 / 0.84** |
| Site 2 | **0.89 / 0.67 / 0.64** | 0.85 / 0.50 / 0.41 |

- Random forest on single post-fire images, Zimbabwe savanna.
- The top bands were NIR, red and **red-edge** (site 1) and blue (site 2). The Landsat thermal band was third most important at site 1.
- S2 overestimated burned area against field perimeters. Accuracy was highest for images closest to the burn date.

**Concrete action:** add S2 red-edge B5/B6 and Landsat thermal B10 as candidate features in the stage-1 LightGBM, and let the stepwise AUC selection (B1) decide. Expected effect: small.

### D3. Rahmi & Febrianti 2020, "Pemanfaatan data Sentinel-2 untuk analisis indeks area terbakar" (Sentinel-2 burned-area indices), *Jurnal Penginderaan Jauh Indonesia* 2(1). **FULL** (Indonesian)
- Separability index test of NBR, NBR2, MIRBI and BAIS2:
  - **MIRBI best separates burned from bare land**, smoky or not;
  - NBR best separates burned from vegetation and built-up land;
  - NBR2 best for smoke-covered burns.
- BAIS2 means: burned 0.92, smoky burned 0.76, bare land 0.68 (barely separable), vegetation 0.24.

**Concrete action:** with FLOGA (A4), use **dMIRBI against bare or crop-edge confusion** and **dNBR2 under haze** (January, March-April smoke) [inference]. Do not use BAIS2: it is the weakest in FLOGA and confused with bare soil here.

### D4. Indian studies checked
- **Mamgain, Karnatak, Roy & Chauhan 2022**, ISPRS Annals V-3-2022:533 (Uttarakhand, S2 NBR burnt area 2016-21). **ABSTRACT ONLY** read in practice; correlations with LST, rain and NDVI only.
- **Mamgain, Karnatak & Roy 2023**, ISPRS Archives XLVIII-M-3-2023:285. **FULL**
  - Fuzzy overlay of 11 Landsat-8 indices (including NBRT) and 10 S2 indices.
  - "Accuracy" against MODIS/VIIRS points: L8 66.25%, S2 59.79%, combined 79.66%.
  - **Validated against active-fire points, so circular for our purpose.** Do not copy.
- **Lohar, Panhalkar & Patil 2022**, *Disaster Advances* 15(1) (Chandoli NP, Maharashtra scrub forest, one 2017 fire). **FULL**
  - S2 OBIA OA 84%, kappa 0.795; L8 OA 82%.
  - dNDVI and RdNBR best among 6 indices.
  - Estimated burnt area close to the 194 ha recorded.
  - Single fire, so weak evidence.
- **Bar, Parida & Pandey 2020**, *RSASE* 18:100324 (Uttarakhand, L8 + S2 on GEE). **ABSTRACT ONLY**
  - Burned area agreed with FireCCI (R² 0.71-0.93) and MCD64A1 (R² 0.62-0.91).
  - Indices: dNBR, dNDVI, dNDWI, dSWIR.
- **Vadrevu:** the most relevant paper, Balakavi, Vadrevu & Lasko 2025 (Bandipur, VHR + deep learning), is already FULL in `high_res_imagery.md`. Nothing new found for Odisha, Telangana or Tamil Nadu with design-based validation.

**Bottom line [inference]:** **no Indian study validates S2 burned area in dry deciduous forest against independent high-resolution reference with a probability sample.** Chandel 2022 (earlier note) is the closest. Our Wayback check is already stronger than the published Indian work. A design-based v3 validation would be the first of its kind for central India.

### D5. Suwanprasit & Shahnawaz 2024, "Mapping burned areas in Thailand using Sentinel-2 imagery and OBIA techniques", *Sci. Rep.* 14:9609. **FULL**
- One S2 L1C scene (27 Feb 2018), eCognition multiresolution segmentation at scale 50, NDVI rules.
- "85.2% accurate" against 500 random burned points from GISTDA. Only burned points were tested, so there is no commission estimate.
- Nothing to copy, except the warning that **burned-only reference points give a meaningless accuracy.**

---

## Part E. SAR and high-resolution checks

### E1. Belenguer-Plomer, Tanase, Chuvieco & Bovolo 2021, "CNN-based burned area mapping using radar and optical data", *RSE* 260:112468. **FULL** (author PDF, UniTN repository)

**Set-up**
- S1 VV, VH and VH/VV: the two images before each S1 interval plus all images up to 180 days after.
- S2 composites with gap-filling up to 30 days, at 40 m, with NBR, NDVI, NDWI and MIRBI.
- CNN with 1D (spectral) or 2D (spatial) convolution. More hidden layers only added compute time.

**Results**
- S1-only CNN: average Dice 0.55 ± 0.17 (Reed-Xiaoli detector 0.57).
- S2-only: Dice about 0.7.
- **S1+S2 stacking did not beat S2 alone except in crops** (crops: Dice 0.44 vs 0.42 optical, 0.37 SAR).
- The gain is wall-to-wall coverage: in tile 52LCH cloud gaps covered 17.6% of the area.
- Mismatched sensor dates explained the worst omission (OE 0.65 when hotspots fell between S2 looks).

**Concrete action:** **skip S1 for scars** [inference: dry season, low cloud; C-band backscatter is dominated by the canopy, which litter fires do not change]. Revisit only if a haze-gap count shows more than about 10% of alerts with no clear optical look within 15 days. The existing `no_clear_image` / `waiting` status counts answer this.

### E2. NICFI, PlanetScope, Wayback (see `high_res_imagery.md`)
No new source read; that note has the access facts. How they fit v3 [inference]:
- **Wayback** (0.3-0.5 m): the primary validation and active-learning image. 511 fires have a Wayback image within 40 days.
- **NICFI monthly mosaics** (4.77 m, 2020-): the second interpreter for the sampled strata where Wayback is absent. Monthly compositing blurs dates, so use it only for "burned within the month", not for edges.
- **PlanetScope scenes** (3 m, near-daily, Education & Research or ESA TPM quota): edges and dates for a small set of about 50 sampled fires. This gives a real day-level check of the dating stage.

---

## Part F. Accuracy assessment design

### F1. Padilla et al. 2015, "Comparing the accuracies of remote sensing global burned area products using stratified random sampling and estimation", *RSE* 160:114-121 (figshare author copy). **FULL**
- **Design:** 103 Thiessen scene areas (TSAs) by stratified random sampling. Strata were Olson biomes, then burned-area activity, with larger samples where burned area is high. Reference perimeters came from multi-temporal Landsat TM/ETM+ pairs.
- **Error matrix:** built from the **proportion of area** of agreement in each pixel.
- **Metrics:**
  - commission error Ce = P12/P1+;
  - omission error Oe = P21/P+1;
  - **Dice = 2P11/(2P11 + P12 + P21)**;
  - bias and relative bias.
  - All are estimated with the **stratified combined ratio estimator**, with standard errors and paired tests between products.
- **Results:** all six global products had Ce > 40% and Oe > 65%; the standard error of Dice was < 5%.

### F2. Boschetti, Stehman & Roy 2016, "A stratified random sampling design in space and time for regional to global scale burned area product validation", *RSE* 186:465-478 (PMC6220344). **FULL** (body read via the PMC page)
- **Sampling unit:** a "voxel" = TSA × 16-day Landsat interval (178,917 voxels for 2008).
- **Strata:** biome × fire activity. "High" is the top 20% of voxels by MODIS active-fire area, holding about 80% of fire area.
- **Allocation:**
  - 50/50 high/low (EQ) gave standard errors, relative to simple random sampling, of OA 37%, OE 77%, CE 46%, area 47%;
  - optimal allocation was barely better (36 / 74 / 42 / 46%);
  - **proportional allocation gave almost no gain.**
- **Estimators:** combined ratio estimators (Eqs. 14-15) and total burned area (Eq. 19-21).
- Reference: visual interpretation of two Landsat-class images, or semi-automatic mapping with full manual checking.

**Concrete action: validation design for scar v3 (and v2 as a baseline)** [inference, built from F1 and F2]
- **Unit:** a 1 km² square × one image-pair window (about 5 days), so the reference interpreter sees the same window the product maps.
- **Frame:** squares in Ratapani forest with a Wayback (or NICFI) image within 15 days of the window end.
- **Strata (product-based, so commission is estimated well):**
  - S1: square holds ≥ 0.5 ha of v3 burned;
  - S2: no v3 burn but an alert within 2 km;
  - S3: no v3 burn and no alert within 2 km (the omission stratum, where FIRMS misses small fires).
  - Cross with month (Jan-Feb / Mar-Apr / May-Jun) and canopy (< 50%, 50-70%, > 70%).
- **Allocation:** about 50% S1, 25% S2, 25% S3, not proportional (Boschetti: proportional gives nothing). About 300 squares give Dice SE ≈ 3-5 points (Padilla's < 5% at 103 units).
- **Interpretation:** blind (product hidden), on the 0.3-0.5 m image. Digitise burned polygons fully in the square, not "inside vs ring" as in the v2 check.
- **Report:** Ce, Oe, Dice, relative bias, ±SE, by month and canopy, for v2, v3 and FSI-style "box" outputs.
- **Expected effect:** the first honest omission number. Today's only omission evidence is "small scars miss 88% of nearby burned ground".

---

## Part G. Compute on one RX 9060 XT (16 GB) [inference unless cited]

**Support**
- ROCm 7.0.2 (Linux) lists the RX 9060 XT (gfx1200) as supported, and hipBLAS supports gfx1200 (Phoronix, Oct 2025).
- AMD's "PyTorch on Windows" release notes for ROCm 7.2 (21 Jan 2026) list the RX 9060 XT (search snippet; the AMD page returned 503).
- DirectML is legacy and covers fewer ops. Use **Linux ROCm PyTorch**, or WSL2 if AMD's ROCm-on-WSL path supports gfx1200 (check AMD's support matrix; not verified).

**Arithmetic**
- Assumption: MP forest is about 77,500 km² (ISFR order of magnitude, not re-checked). At 20 m that is about 194 MP per date.
- One Feb-Jun season ≈ 24 S2 dates + 15 Landsat 8/9 dates ≈ 40 pairs ≈ 7,800 MP.

| Task | Rate | Time per season or run |
|---|---|---|
| U-Net (Knopp size) inference, all MP | 0.26 s/MP on a P4000 (RX 9060 XT is about 4-5× the P4000's FP32) | **~0.5 h GPU**; ~5 h on a 6-core CPU at 2.2 s/MP |
| Per-alert chips, all MP (184,352 forest events × 3 looks × 0.0225 MP) | | ≈ 12,400 MP ≈ 1 h GPU |
| Prithvi-EO-2.0-300M, T = 4 at 224 px (about 0.25-0.3 TFLOP per chip ≈ 5 TFLOP/MP; ~15 TFLOP/s achieved in bf16) | | ≈ 0.3 s/MP → **1-3 h per all-MP season** |
| Fine-tune Prithvi-300M with LoRA on about 1,000 chips (batch 4-8, bf16, gradient checkpointing) | | Fits in 16 GB; ~1-3 h per run |
| Fine-tune a U-Net or Siamese ResNet-34 | | < 1 h |
| Stage-1 LightGBM on ~10⁶ pixel-looks | CPU | Minutes |

**Conclusion:** compute is not the bottleneck. Labels and validation are. The current per-alert chip pipeline runs at about 45 events per minute and is I/O-bound on Planetary Computer reads. A seasonal wall-to-wall S2/HLS composite per MP tile would remove the per-alert re-reads.

---

## Pipeline v3 (recommended) [inference, built from the sources above]

| Stage | What | Model and settings | Labels / inputs | Source basis | Expected change in output |
|---|---|---|---|---|---|
| 0 | Data cube per S2 tile-season (Dec-Jul) | All clear S2 L2A (offset fixed) + Landsat 8/9 SR + TIRS, at 20 m; SCL mask dilated 5 px; B12 < 0.07 shadow mask; per-pixel 3-5-year same-day-of-year baseline | — | Hawbaker "reference" predictors; Tienaho; earlier hygiene note | One read per tile-season instead of per alert; enables wall-to-wall |
| 1 | Fire-independent per-look burn probability | LightGBM. Features: NBR, NBR2, **MIRBI**, NDVI, B5, B8A, B11, B12, NBRT1 (Landsat); minus the 5-year baseline; minus the previous look; chip-relative drop. Stepwise AUC selection; isotonic calibration. PU correction (Elkan-Noto c) | Positives: v2 **pass-1 core** pixels after cleanlab pruning + Wayback-confirmed. Negatives: decoy/control chips, multi-year-unburned pixels, cloud and shadow pixels | B1, B2, A4, C2, C4 | A probability for every pixel and look; no circle needed. Control background expected to fall well below today's 0.5 ha/km² at equal recall (to be measured) |
| 2 | Spatial segmentation of the season's burns | **Siamese U-Net (ResNet-34) or BAM-CD v2 fine-tune**, BCE (or nnPU) loss; inputs: pre, post and check-look 6 bands + stage-1 probability; tiles 256×256 at 20 m; keep single-class tiles. Upgrade path: Prithvi-EO-2.0-300M-TL, LoRA, T = 4 | Stage-1 high-confidence pixels (P > 0.9 burned, < 0.1 unburned); **ignore** the 0.1-0.9 band and a 40 m edge buffer in the loss; 5 seeds; **active learning** on Wayback by ensemble disagreement (~300 chips) | A1, A3, A4, A5, C3, C5 | Cleaner edges, fewer filled holes, fewer shadow and crop false scars. Recovers burned ground next to small scars (today 88% missed) |
| 3 | Per-pixel burn date | Argmax over days of a fused daily probability. Logistic first: S3 SYN daily dNBR, VIIRS/MODIS/NOAA-20 kernel, S2/Landsat fire pixels, BEAST change probability. Later a BA-Net-style 1D temporal CNN | Trained on the ~55% of first burns with a FIRMS / fire-pixel day | B4, B5, `daily_scar_dating.md` | `t_star` + `dt` per pixel. The 5-10-day window drops to 1-2 days for most pixels (S3 tests: 74-81% right day) |
| 4 | Fire objects and alert tie | Connected burned pixels → patches; split by date (|Δt| ≤ 2 days) and distance to seeds (existing `split_scars`). **Then** attach to alerts within 200 m / 600 m. Keep both products: (a) fire-independent seasonal map for spread scoring; (b) alert-tied scars for officials | — | MCD64 temporal consistency rule; v2 limits file | Ends the circularity for the spread thread; officials keep the alert link |
| 5 | Calibration and uncertainty | Temperature / isotonic per month × canopy stratum; ensemble variance → `p_sd`; three statuses: burned (P ≥ t_hi), possible (t_lo ≤ P < t_hi), unburned | Wayback validation strata (held out) | C6, C5 | Published "probability burned" that means what it says; "faint" becomes a calibrated "possible" |
| 6 | Validation | Stratified random squares × window, blind full digitising on Wayback/NICFI, combined-ratio estimators: Ce, Oe, Dice, relB ± SE by month and canopy; v2 vs v3 side by side | Independent only | F1, F2 | First design-based omission and commission for central-Indian litter fires |

**Gains to expect, with sources**
- Learned bi-temporal model vs index rule: +20-24 F1 points in FLOGA and about +40 in CaBuAr, with clean labels.
- U-Net over RF: +5 F1 (Knopp).
- Foundation model over U-Net: +3-6 IoU (Prithvi-2).
- Noisy-label classifier with active-fire confirmation: producer's accuracy 55% vs 27% for a threshold product (RAPT).
- Active learning: about 1% of labels for full-set accuracy (Ruzicka).
- **[inference] For us:** after label cleaning, the realistic target is Wayback-checked precision 81% → about 88-90%, and much lower omission next to small scars. January stays weakest; the "possible" class carries it honestly.

---

## Datasets, models and code

| Item | What | Licence | Link | Use for us |
|---|---|---|---|---|
| HLS Burn Scars | 804 HLS chips of 512², CONUS 2018-21, MTBS masks | CC-BY-4.0 | https://huggingface.co/datasets/ibm-nasa-geospatial/hls_burn_scars | Pretraining or extra negatives; big severe fires, so domain shift |
| Prithvi-EO-2.0-300M-BurnScars | Fine-tuned ViT-300M + UPerNet, 6 HLS bands, single date | Apache-2.0 | https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M-BurnScars | Zero-shot check; starting weights |
| Prithvi-EO-1.0-100M-burn-scar | 100M version | Apache-2.0 | https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-1.0-100M-burn-scar | Lighter baseline |
| Prithvi-EO-2.0 backbones (300M/600M, TL) | Multi-temporal encoder, T = 4 | Apache-2.0 | huggingface.co/ibm-nasa-geospatial (TerraTorch) | Pre/post/check fine-tune with LoRA |
| FLOGA (GeoTIFF version) | 326 Greek fires, S2 pre/post + MODIS, expert labels | CC-BY-4.0 (data), MIT (code) | https://huggingface.co/datasets/orion-ai-lab/FLOGA-GeoTIFFs ; https://github.com/Orion-AI-Lab/FLOGA | Pretraining a Siamese model; BAM-CD v1 and v2 weights (Dropbox links in README) |
| CaBuAr | California S2 pre/post, CAL FIRE masks | CDLA-Permissive-2.0 | https://huggingface.co/datasets/DarthReca/california_burned_areas | U-Net baseline pretraining |
| S2 California active-fire set (Mitra 2026) | Rule labels + analyst review | CC-BY-4.0 / MIT | Zenodo 10.5281/zenodo.22713948 | Template for "rule labels + blind review" design |
| BA-Net | Space-time U-Net + LSTM, daily VIIRS, per-day probability | not checked | https://github.com/mnpinto/banet | Dating-stage architecture |
| GABAM 2015 | 30 m global annual burned area | not checked | https://vapd.gitlab.io/post/gabam2015/ | Not for MP dates (annual); method only |
| USGS Landsat BA (CONUS) | GBRM burn probability per scene | public domain (USGS) | ScienceBase doi 10.5066/P9QKHKTQ | Method template only |
| MapBiomas Fogo | Monthly Landsat burned area, Brazil, deep MLP | CC-BY (MapBiomas) | brasil.mapbiomas.org (ATBDs collections 3-5) | Min-NBR composite + date idea |
| cleanlab | Confident-learning label-issue finder | AGPL-3.0 (check before bundling) | https://github.com/cleanlab/cleanlab | Prune v2 labels |
| nnPU reference code | PU loss | MIT (authors' repo, not checked) | github.com/kiryor/nnPUlearning | PU loss for the U-Net |
| Rbeast | Bayesian change point | not checked | CRAN / PyPI `Rbeast` | Change-probability feature for dating |
| TerraTorch | Fine-tuning toolkit for Prithvi | Apache-2.0 | github.com/IBM/terratorch | Pure PyTorch, so it runs on ROCm in principle (not tested) |
| segmentation_models_pytorch | U-Net / Siamese encoders | MIT | github.com/qubvel-org/segmentation_models.pytorch | Stage-2 baseline |

---

## Reading status

| Source | Status |
|---|---|
| Knopp 2020 | FULL |
| Prithvi-EO-1.0 (Jakubik 2023) | PARTIAL (burn-scar sections, set-up, tables) |
| Prithvi-EO-2.0 (Szwarcman) | PARTIAL (burn tasks, compute) |
| FLOGA (Sdraka 2024) | FULL |
| CaBuAr (Rege Cambrin 2024) | FULL |
| Mitra 2026 S2 active-fire benchmark | FULL |
| Seydi 2022 Burnt-Net | ABSTRACT ONLY |
| Hawbaker 2020 | FULL |
| GABAM (Long 2019) | FULL |
| MapBiomas (Alencar 2022) | FULL |
| BA-Net (Pinto 2020) | PARTIAL (abstract + code) |
| BEAST (Zhao 2019) | ABSTRACT ONLY |
| Yan 2022 four-model comparison | FULL |
| RAPT (Mithal 2018) | FULL |
| Confident learning (Northcutt 2021) | PARTIAL |
| nnPU (Kiryo 2017) | PARTIAL |
| Elkan & Noto 2008 | PARTIAL |
| Ruzicka 2020 | PARTIAL |
| Guo 2017 | PARTIAL |
| Smith 2007 | FULL |
| Ngadze 2020 | FULL |
| Rahmi 2020 | FULL |
| Mamgain 2022 | ABSTRACT ONLY |
| Mamgain 2023 | FULL |
| Lohar 2022 | FULL |
| Bar 2020 | ABSTRACT ONLY |
| Suwanprasit 2024 | FULL |
| Belenguer-Plomer 2021 | FULL |
| Padilla 2015 | FULL |
| Boschetti 2016 | FULL |
| Roteta 2019 | ABSTRACT ONLY (repository blocked by a captcha; numbers already verified in `alert_burn_scars_fullread.md`) |
| AMD ROCm support | PARTIAL (news and search level) |

**Tally:** 18 FULL, 8 PARTIAL, 5 ABSTRACT ONLY (Seydi, Zhao, Mamgain 2022, Bar, Roteta); 31 sources in all, plus the ROCm news. Downloaded PDFs are in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r16_lit/` (session scratch, not kept).

---

## Ranked action list (scar thread unless noted)

| Rank | Action | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|
| 1 | **Design-based validation set** (needed to score anything below) | Stratified 1 km² × window squares (S1 product-burned / S2 alert-near / S3 alert-far × month × canopy), ~300 squares, 50/25/25 allocation, blind full digitising on Wayback (NICFI fallback); combined-ratio Ce, Oe, Dice, relB ± SE | First honest omission and commission for v2; the reference every later change is scored on | 3-4 days (mostly eye work) |
| 2 | **Add dMIRBI and dNBR2 votes plus the GABAM "below last year's minimum NBR" gate to the current rule** | dMIRBI > 0.25 and dNBR2 < −0.05 as an extra vote; NBR_post < min(NBR, previous year) − 0.1; re-run the Wayback real-vs-decoy AUC and `no_circle.py` | FLOGA: dMIRBI F1 64 vs dNBR 45. Expect fewer decoy-like and January scars [inference] | 0.5-1 day |
| 3 | **Stage-1 LightGBM per-look probability, fire-independent** | B1 features incl. 5-year baseline, NBRT1 for Landsat; positives = cleaned pass-1 cores; negatives = decoys and multi-year-unburned; beat × year blocked CV; isotonic calibration; seed / grow / drop thresholds tuned on rank-1 strata | Control background 0.5 ha/km² → aim ≤ 0.2 at equal recall; gives the fire-independent map the spread thread asked for | 2-3 days |
| 4 | **cleanlab pass over v2 labels** (before any network) | Out-of-fold probabilities from rank 3; flag and send the top 100 issues to Wayback eye-check | Removes the ~10% decoy-like "yes" scars and over-grown margins from training | 0.5 day |
| 5 | **Dating stage: argmax-day fusion** (scar + spread threads) | S3 SYN daily dNBR + VIIRS kernel + fire pixels (+ BEAST probability); logistic; store `t_star`, `dt` | Right day 37% → ~75-80%+ (S3 tests); 5-10-day windows → 1-2 days | 2 days |
| 6 | **Siamese U-Net (ResNet-34) bi-temporal fine-tune with an ignore band and active learning** | Pre/post/check 6 bands + stage-1 probability; BCE or nnPU; 5 seeds; 6 rounds × 50 Wayback chips by ensemble disagreement; RX 9060 XT on Linux ROCm | Better edges, recovers burned ground next to small scars; Wayback precision 81% → ~88-90% [inference] | 4-6 days |
| 7 | **Calibrated probability product with three statuses** (live alerts + officials) | Temperature / isotonic per month × canopy on held-out rank-1 strata; ensemble SD; burned / possible / unburned | "Faint" becomes a calibrated "possible"; probabilities officials can trust | 1 day |
| 8 | **Char / litter / green unmixing fraction** (fuel + scar) | 3 image-derived endmembers on post S2; sum-to-one least squares | Continuous litter-consumption layer; better faint decisions under canopy (Smith 2007: SE 4.78 vs 8.01 g/m²) | 1-2 days |
| 9 | **Prithvi-EO-2.0-300M-TL, LoRA, T = 4** (only if rank 6 plateaus) | TerraTorch, binary head, 224 crops, published normalisation | +3-6 IoU over U-Net in Prithvi-2 tables; mainly label efficiency | 2-3 days |
| 10 | **Seasonal min-NBR composite plus date for all-MP** (all-MP scars) | Per S2 tile-season, NBR minimum and its date, stage-1 model applied once | Cuts the per-alert re-reads (now ~45 events/min, 2-3 days for the rest of MP) to one pass per tile; coarse dates | 1-2 days |
| 11 | Sentinel-1 | Only if more than 10% of alerts have no clear optical look within 15 days | Belenguer-Plomer: no gain over S2 when cloud-free | Skip for now |
