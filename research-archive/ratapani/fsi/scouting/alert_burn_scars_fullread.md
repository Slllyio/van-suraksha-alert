# Burn scar for each fire alert: full-text read of the key papers

**For:** the "Burn scar for every fire alert" thread (`fire-alert-scars/`, `alert_scar.py`).
**Builds on:** `fsi/scouting/alert_burn_scars.md`. Its wrong numbers were fixed in place.
**Compiled:** 14 Oct 2026.

**Our current method, as the baseline for every action below:**
- The test is the NBR drop against a 1.5 km surround (the chip median).
- Scars under 2 ha are dropped.
- Precision is about 83% and recall about 71%.
- It is weakest in Jan-Feb, during leaf fall.

**How each source was read:**

| # | Source | What I read |
|---|---|---|
| 1 | FireCCISFD20 algorithm document (ESA Fire_cci D2.1.4 ATBD, Roteta 2021), the exact method behind Chuvieco et al. 2022 | **FULL TEXT** |
| 2 | FireCCISFD11 algorithm document (D2.1.2 ATBD, Bastarrika & Roteta 2018), the method of Roteta et al. 2019 RSE | **FULL TEXT** (skimmed for differences from #1) |
| 3 | Roteta et al. 2019 RSE 222:1-17 and Chuvieco et al. 2022 STOTEN 845:157139 | **ABSTRACT ONLY** (the Elsevier pages block automated download). The method is fully covered by #1 and #2. |
| 4 | Padilla et al. 2026, *Fire* 9:195 (near-real-time Sentinel-2 + VIIRS) | **FULL TEXT** |
| 5 | Roteta et al. 2021, *Remote Sens.* 13:4298 (preliminary global Earth Engine algorithm, the precursor of Sentinel2BAM) | **FULL TEXT** |
| 6 | Roteta et al. 2021, *Remote Sens.* 13:816 (BAMT tools) | **FULL TEXT** |
| 7 | Chandel et al. 2022, *Front. For. Glob. Change* 5:933807 (Central India) | **FULL TEXT** (the tables extracted badly; the prose was read) |
| 8 | Hu, Ban & Nascetti 2021, *Remote Sens.* 13:1509 | **FULL TEXT** |
| 9 | Sui et al. 2024, BiAU-Net, *JAG* 132:104034 | **FULL TEXT** (Glasgow eprint) |
| 10 | Tienaho 2025, *Dissertationes Forestales* 373 (study III: Sentinel-2 NBR breakpoints) | **FULL TEXT** |
| 11 | Prithvi-EO-2.0-300M-BurnScars model card, fine-tuning config, and HLS Burn Scars dataset card | **FULL** (model card, config and dataset card) |
| 12 | Bastarrika et al. 2024, Sentinel2BAM, ISPRS J. 218:232-245 | **ABSTRACT ONLY.** The publisher, the EHU repository and ResearchGate all blocked download. Numbers come from the abstract plus Padilla 2026, which cites it. |
| 13 | Roy et al. 2019 RSE 231:111254 | **ABSTRACT ONLY** (paywalled for automated access; no repository copy found) |
| 14 | Liu et al. 2023 RSE 296:113753 | **ABSTRACT ONLY** (closed access) |
| 15 | Ren et al. 2026 *JAG*, doi 10.1016/j.jag.2026.105163 | **ABSTRACT ONLY.** It is open access, but ScienceDirect blocked the fetch. |

**Count:** 10 sources read in full (items 1, 2 and 4-11). The 6 papers in items 3 and 12-15 were read as abstracts only.

**Downloaded files:** the PDFs and extracted text are in the session scratchpad under `papers_scars/`. Re-fetch from the links below if needed.

---

## 1. FireCCISFD20 / FireCCISFD11: the exact two-phase algorithm (ATBD D2.1.4, 2021; D2.1.2, 2018)

**Links:**
- [D2.1.4 ATBD (FireCCISFD20)](https://admin.climate.esa.int/documents/1611/Fire_cci_D2.1.4_ATBD_SFD_v1.0.pdf)
- [D2.1.2 ATBD (FireCCISFD11)](https://admin.climate.esa.int/documents/221/Fire_cci_D2.1.2_ATBD_SFD_S2_v1.0_2ESR4Of.pdf)

This document is the closest published recipe to `alert_scar.py`. Every rule below is copied from the ATBD and can go straight into code.

**Inputs**
- Sentinel-2 L2A reflectance divided by 10000, at 20 m. Only three bands are used: B8A (NIR), B11 (SWIR-short) and B12 (SWIR-long).
- `NBR2 = (B11 - B12) / (B11 + B12)`
- `MIRBI = 10*B12 - 9.8*B11 + 2`
- Six variables in total: the post-fire value [t] and the change [t] - [t-i] of MIRBI, NBR2 and NIR.
- The pre-image partner is the most recent of the previous four scenes that is clear. They never look back more than 40 days, because commission rose when older scenes were compared.

**"Not burnable" mask (Table 1)**
- Masked SCL classes: 0, 1, 6 (water), 8, 9 and 10 (cloud medium, cloud high, cirrus), and 11 (snow).
- Classes 8, 9 and 10 are dilated by **5 pixels (100 m)**.
- Post image only: also mask **B12 < 0.07**. Cloud shadows have lower long-SWIR reflectance than burns, so this is their shadow filter. They deliberately do *not* mask SCL "dark area" or low-probability cloud, because that removes too many real burns.
- Process a pair only if at least **5 km² (12,500 pixels)** is unmasked and at least one hotspot falls in the interval.

**Stage 0, initially burned (IB), Table 2.** All seven rules must hold:
1. MIRBI_t > mean(MIRBI_t)
2. MIRBI_t - MIRBI_t-i > **0.25**
3. NBR2_t < mean(NBR2_t)
4. NBR2_t - NBR2_t-i < **-0.05**
5. NIR_t < mean(NIR_t)
6. NIR_t - NIR_t-i < **-0.01**
7. not masked

The means are taken over the unmasked post-image pixels of the tile.

**Confirmation by active fires: IB becomes IBC (confirmed) or IBNC (not confirmed)**
- IB pixels are labelled into regions with 8-connectivity.
- Only regions **> 30 ha (750 pixels)** are tested against hotspots in [t-i, t].
- Hotspot dilation:
  - SFD20 (VIIRS) uses **19 pixels = 380 m diameter**. The limitations section words this as "no hotspot closer than 180 m to IB".
  - SFD11 (MODIS) used **50 pixels = 1 km diameter**.
- The overview paragraph of the SFD20 document still says "1 km diameter", copied from v1. Section 5.3.5 gives 380 m and is the operative number.

**Seeds (Table 3)**
- IBC statistics set the seed rules.
- Use the **5th percentile of IBC** where burned is higher (MIRBI_t, dMIRBI) and the **95th percentile** where burned is lower (NBR2_t, dNBR2, NIR_t, dNIR).
- All six rules must hold, plus "not masked".

**Second stage probability (SEPB)**
- Separability: `M = |mu_IBC - mu_IBNC| / (sigma_IBC + sigma_IBNC)` on dMIRBI, dNBR2 and dNIR.
- **Case a**, if any M > **0.75**: confirmed and unconfirmed burns differ, so IBNC counts as background.
  - `MIRBI_memb = s-curve(P90 of INB+IBNC dMIRBI, P50 of IBC dMIRBI)`
  - `NBR2_memb = z-curve(P10 of INB+IBNC dNBR2, P50 of IBC dNBR2)`
- **Case b**, if all M < 0.75: unconfirmed IB is treated as burned too.
  - The background is INB only.
  - The burned upper bound is the P50 of IBC+IBNC.
- `SEPB = MIRBI_memb × NBR2_memb`. Only dMIRBI and dNBR2 are used here; NIR is not.

**Growing (hysteresis on a continuous map)**
- A pixel's final burn probability Pb is the *highest* SEPB threshold at which the pixel is still 8-connected to a seed.
- The best cut was **Pb ≈ 5%** (their Fig. 7). It was rescaled to 50% for users with this lookup:

  | Raw Pb | Rescaled |
  |---|---|
  | 0-4% | 0-40% (one step per 1%) |
  | 5-14% | 50% |
  | 14-23% | 60% |
  | 23-32% | 70% |
  | 32-41% | 80% |
  | 41-50% | 90% |
  | ≥ 50% | 100% |

**Sentinel-2A and Sentinel-2B handled separately (new in SFD20)**
- Comparing a 2A image with a 2B image raised commission from **22.9% to 30.5%**, because of sub-pixel misregistration between the satellites and cloud shadows.
- The fix: build a burned map from each satellite on its own. Keep a pixel only if the other satellite's map also has it on the closest earlier or the closest later date.

**Accuracy**
- ATBD internal test, 26 tiles: OE **13.5%**, CE **7.8%**, Dice **89.3%**.
- Published independent validation (Chuvieco 2022 abstract): OE **8.5%**, CE **15.0%**, Dice **87.7%**. 92.5% of fires were detected within 10 days. Total burned area 4.8 Mkm²: +80% versus FireCCI51 and +120% versus MCD64A1.
- **Failure cases:**
  - Sites with only small burns among cropland: tile 31PBQ had 1.4 km² of burns, OE 82%, CE 44%.
  - Cloud edges not masked by Sen2Cor.
  - No hotspot in the interval means 100% omission.

**Concrete action for us (alert-scar thread)**
- Implement `two_phase.py` as a drop-in pass 2 for `alert_scar.py`.
- Compute the seven IB rules per alert chip with the fixed thresholds above. Use the means of each Sentinel-2 date over the whole Ratapani AOI, not over a 3 km chip.
- **Do not copy the 30 ha region rule.** Our scars are 0.5-10 ha. Instead:
  - mark an IB region confirmed if any of its pixels is within **190 m (the 380 m-diameter disk)** of a VIIRS alert in [t-i, t];
  - keep regions of 2 pixels (0.08 ha) or more.
- **Pool the IBC and IBNC statistics** (P5/P95 seeds, P10/P50/P90 sigmoids) over all alert chips in a 10-day window, not per chip. One chip has too few confirmed pixels for stable percentiles. *(inference)*
- Apply the SEPB hysteresis growth at a raw threshold of 0.05.
- Add the **post-image B12 < 0.07 shadow mask** and the **5-pixel cloud dilation**.
- Build each date's map per sensor (S2A, S2B, S2C, L8, L9 each alone), then cross-confirm with another sensor's adjacent date.
- Validate on the ~400 hand-checked points. Report precision and recall by month and by size class.
- **Expected effect** *(inference)*:
  - recall from 71% to 76-80%, from the looser grow threshold and the pooled seeds;
  - precision roughly held or slightly higher in Jan-Feb, from the B12 shadow mask and the cross-sensor check.
- **Effort:** about 2 days.

---

## 2. Padilla et al. 2026: near-real-time Sentinel-2 + VIIRS (FULL TEXT)

**Link:** [Fire 9(5):195](https://doi.org/10.3390/fire9050195), CC BY. Data are "available on request"; no code was released.

**Network**
- Inputs per pixel time series: B4, B8A, B12, NDVI and NBR2.
- NDVI was added specifically to cut false positives from crop harvest.
- Architecture:
  - 3 Conv1D layers over the spectral axis (64, 96 and 64 filters, kernel 5);
  - then 3 Conv1D layers over the time axis (same filters, kernel 5, or the series length if shorter);
  - then a bidirectional LSTM with 64 units and a sigmoid dense output.
- Training settings: dropout 0.2, Adam with learning rate 1e-4, batch 64, MSE loss. Training stops when MSE improves by less than 1e-6 over 50 epochs.
- 18 networks, one for each series length (t_max) from 2 to 20. Each has up to 210k parameters.

**Training labels**
- There are no hand labels.
- A linear spectral-mixture model of fire effects, applied to BRDF-normalised reflectance just before and just after each VIIRS detection, gives:
  - the burned fraction `f_b`;
  - the probability `prob(f_b > 0.1)`.
- A series is discarded if the largest `f_b` is not at the first look after the fire.
- Training, validation and test sets: 58,485 / 12,938 / 10,385 burned samples, each with an equal number of unburned samples. Unburned samples come from more than 20 km and 40 days from any fire.

**Active-fire fusion**
- `AFdensity` = VIIRS detections smoothed with a **Gaussian kernel, sigma = 2 km and 4 days**, accumulated over the gap between image dates.
- A logistic regression combines `prob(f_b > 0.1)` and `AFdensity` into `prob(b)`.
- ROC AUC: **0.972** for the monthly (non-time-critical, NTC) product, **0.968** for the daily near-real-time (NRT) product.
- Cut thresholds were picked by sweeping 0-1 in steps of 0.05 for the best Dice: **0.25 for NTC, 0.5 for NRT**. Accuracy is flat near the chosen value.
- Pixels more than 20 km and 40 days from any fire are skipped. This costs less than 0.2% omission.

**Other rules**
- Masking follows Roteta 2019 and adds SCL cloud shadow, plus **B12 < 0.07**.
- Only VIIRS detections typed "vegetation fire" are used. Detections over urban land are dropped.

**Accuracy, 2019 global validation (Table 2, Dice / CE / OE %)**

| Product | Dice | CE | OE |
|---|---|---|---|
| Monthly (NTC) | 87.2 | 13.2 | 12.5 |
| Daily, 10-day update | 85.4 | 13.6 | 15.5 |
| Daily, 5-day update | 84.7 | 13.7 | 16.7 |
| Daily, day 0 | 82.7 | 15.0 | 19.5 |
| CLMS BA 300 m | 75.6 | 23.0 | 25.7 |
| FireCCIS311 | 68.7 | 19.0 | 40.4 |
| MCD64 | 60.3 | 17.2 | 52.5 |

- Sentinel2BAM (Bastarrika 2024) scored **Dice 81.8%** on the same reference set.
- Gains from waiting:
  - day 0 to day 5: **+2.0 Dice**, mostly fewer cloud-shadow false positives;
  - day 5 to day 10: **+0.7 Dice**.
- Tropical savanna and tropical forest matched the global figures. Boreal forest and xeric biomes were worse.

**Concrete action for us (alert-scar thread, and `live.py` statuses)**
1. Add an `af_density` raster to each chip: a Gaussian KDE of FSI/FIRMS alerts with sigma 2 km and 4 days.
2. Fit a two-variable logistic regression, `burned ~ spectral_prob + af_density`, on the 400 checked points. The spectral probability is our current relative-dNBR score or the SEPB from section 1.
3. Pick the cut by a Dice sweep in steps of 0.05.
4. Turn `live.py` into a three-step ledger with confirmation at 0, 5 and 10 days:
   - **provisional** at the first post look;
   - **confirmed** at the 5-day update;
   - **final** at the 10-day update.
5. Expected effect: Padilla's latency curve suggests about 2 Dice points between the provisional and 5-day maps. The AF-density term mainly helps precision near crop edges *(inference)*.

**Effort:** 1 day.

---

## 3. Roteta et al. 2021, preliminary global Earth Engine algorithm (FULL TEXT): per-tile Otsu thresholds

**Link:** [Remote Sens. 13:4298](https://doi.org/10.3390/rs13214298)

**Choosing the image pair**
- For each pixel, take each pair of consecutive images that brackets an active fire. MODIS MCD14DL detections with confidence of 80% or less are dropped.
- If several pairs qualify, choose the one with the **largest NBR drop**.

**Candidate (BC) thresholds**
- **Otsu** threshold computed per band over the tile.
- Floors, so a threshold is never closer to 0 than: **dNBR -0.05, dNBR2 -0.05, dMIRBI +0.25, dNIR -0.02**.
- The mean of the post period minus the mean of the pre period must also exceed **half** the Otsu threshold. This is a persistence check.
- **Votes needed:**
  - 3 of 4 change bands (dNBR, dNBR2, dMIRBI, dNIR);
  - 2 of 3 post-fire bands (NBR, NBR2, MIRBI);
  - post-fire red reflectance below its Otsu threshold is **mandatory**.
- **Cropland** (MCD12Q1): both change thresholds are multiplied by 2.
- Extra masks used only during sampling: Blue > 0.15 or B12 < 0.05.
- Minimums per tile: hotspots must cover at least 5 km², and candidates at least 1 km².

**Probability curve**
- The sigmoid runs from the 5th percentile of unburned values to the midpoint between that and the 95th percentile of burned values. The curve is pushed toward the unburned side so that low-severity burns are not lost.
- In croplands the 100% point is set at the burned **median**, which makes cropland stricter.

**Objects**
- Earth Engine **SNIC** superpixels: 8-connectivity, compactness 0, seed spacing 10 pixels.
- An object is burned if its mean probability is above 50%.

**Accuracy, 50 global sites, 2019**

| Product | CE | OE | Dice |
|---|---|---|---|
| Sentinel-2 at 10 m | 9.0 | 26.8 | 81.1 |
| Sentinel-2 at 20 m | 9.3 | 27.9 | 80.3 |
| Landsat at 30 m | 11.2 | 34.8 | 75.2 |
| FireCCI51 | 19.1 | 50.0 | 61.8 |
| MCD64A1 | 18.3 | 57.4 | 56.0 |

**Concrete action for us:** two cheap upgrades to the current test.
1. Swap the chip median for **Otsu plus fixed floors**, computed on each date's chip stack over the whole AOI.
2. **Double the thresholds in the cropland mask** (agricultural fringe of Ratapani).

Also take the "largest NBR drop among bracketing pairs" rule for choosing dates.

Expected effect *(inference)*: fewer false scars on harvested fields in March-April, which is a precision gain on crop-edge alerts.

**Effort:** half a day.

---

## 4. BAMT, Roteta et al. 2021 (FULL TEXT): open code for the classifier and for reference perimeters

**Links:** [Remote Sens. 13:816](https://doi.org/10.3390/rs13040816) · **code: https://github.com/ekhiroteta/BAMT** (Earth Engine Code Editor scripts, with the study data in the same repo)

**Random forest settings:** 500 trees, minimum leaf population 10. Other settings are Earth Engine defaults: sqrt(variables) per split, bag fraction 0.5.

**Burned-area map tool**
- Grow from **seeds**: pixels whose probability is above the mean of the per-polygon mean probabilities of the burned training polygons.
- Keep 4-connected patches with probability above 50% that contain a seed.

**Reference perimeter (RP) tool**
- Uses the same steps, with a more permissive seed: the **minimum** of the per-polygon mean probabilities.
- Works at 10 m.

**Accuracy**
- Southeast Australia 2019-20: OE and CE **under 12%**, from about 90 training samples.
- Canada: 40% omission against the CWFIS perimeters, mostly from clouds.

**Concrete action for us (validation)**
- Run the RP tool on 2 Sentinel-2 dates per fortnight for one season (2024 or 2025) across Ratapani.
- Digitise about 30 burned and 30 unburned polygons per date pair. Include **leaf-fall forest** and **harvested crop** as unburned.
- Use the resulting 10 m perimeters as a wall-to-wall reference. This replaces the point-only 400-sample check.
- **Effort:** 2-3 days of clicking. **Gain:** honest precision and recall for each size class.

---

## 5. Chandel et al. 2022, Central India (FULL TEXT), with corrections to the earlier note

**Link:** [Front. For. Glob. Change 5:933807](https://doi.org/10.3389/ffgc.2022.933807)

**Study design**
- 9 Landsat-5 TOA scenes from 1993-2011 (Feb-May), Central India. WRS path 143-145, row 44-45.
- 700 random points per scene, at least 1 km apart, hand-labelled into 13 classes. The classes include **"forest area with leaf fallen off"**, shadow, water, old burns, and burned or unburned forest and agriculture.
- 500 points for calibration, 200 for validation.

**What was compared**
- **FIRMS here means MODIS MCD14DL 1 km**, not VIIRS. It caught under 20% of burned area in every condition.
- Random forest search ranges: trees 100-1000, variables per split 1-10, bag fraction 0.1-1.0.
- SVM: linear, polynomial and RBF kernels.

**Findings**
- Spectral indices had **higher importance than raw bands**. **NDMI, MIRBI, NDVI and NBR** were the most consistently important, then NDWI and GEMI.
- **Adding elevation, hillshade and slope did not consistently increase accuracy.**
- Month and sun-azimuth effects (pooled model): **accuracy for forest burns did not vary systematically with month or azimuth.** The drop at high azimuth and early in the season applied to *agricultural* burns.
- The authors still note that April leaf fall lowers forest biomass, and with it NBR separability.
- Random forest beat 80% in April but over-predicted rare classes. Water and shadow were confused with burns. The authors advise favouring low commission.

**Corrections to the earlier note (E1)**
- The note said this paper confirms our weak Jan-Feb months and points to sun angle and terrain shadow. That is wrong for forest fires. The month and azimuth effect was in cropland burns, and hillshade did not help.
- It still supports the index set, and adding leaf-fall forest as an explicit negative class.

**Concrete action for us:** in the per-season random forest (rank 1 in the earlier note), use these features:
- dNBR, dNBR2, dMIRBI, dNIR;
- post-fire NDMI, MIRBI, NDVI and NBR.

Add a **"leaf-fall, unburned"** hard-negative class sampled from Jan-Feb forest with no alert within 2 km and 20 days. Do not spend time on a hillshade covariate.

**Effort:** part of the random forest build.

---

## 6. Hu, Ban & Nascetti 2021 (FULL TEXT), with a correction

**Link:** [Remote Sens. 13:1509](https://doi.org/10.3390/rs13081509)

**Setup**
- Single-date post-fire Sentinel-2 or Landsat-8.
- LightGBM and AdaBoost ranked **B12, B11 and B8A** as the top three features, so the deep-learning inputs were a 3-band B12/B11/B8A composite.

**Models compared**
- Deep learning: U-Net, HRNet, Fast-SCNN, DeepLabv3+.
- Machine learning: LightGBM, KNN, random forest.

**Results**
- Deep learning generally beat classic machine learning.
- The exception was the **dispersed, patchy Trängslet fire**, where every machine-learning method beat every deep-learning method (kappa about **0.88**). A plain NBR threshold reached kappa above 0.86 there.
- HRNet transferred best from Sentinel-2 to Landsat-8.

**Correction to the earlier note (C5):** "classic machine learning does better on scattered burns" holds for one test site of three, not as a general finding.

**Concrete action for us:** start any CNN with B12/B11/B8A. Keep a pixel random forest as the baseline that a CNN must beat on scars under 3 ha.

---

## 7. BiAU-Net, Sui et al. 2024 (FULL TEXT)

**Links:** [JAG 132:104034](https://doi.org/10.1016/j.jag.2024.104034) · **code and data: https://github.com/TangSui122/Bi-temporal-Wildfire-Burnt-Area-Detection**

**Input and training**
- Pre- and post-fire Sentinel-2 **B12, B11, B8A** as two inputs, 256×256 tiles.
- Attention gates at every up-sampling step.
- Loss: **Dice loss + focal loss**.
- Batch 6, 50 epochs. Learning rate starts at 0.1 and is halved between epochs 30 and 50.
- Training data: 278 tiles (91%) from one fire (Chico, California), with 28 tiles held out for validation.

**Ablation at Chico (F1)**

| Model | F1 |
|---|---|
| FireCCI51 baseline | 0.910 |
| U-Net, BCE loss | 0.799 |
| Bi-temporal U-Net, BCE loss | 0.952 |
| Bi-temporal U-Net, Dice + focal loss | 0.925 |
| BiAU-Net, BCE loss | 0.952 |
| BiAU-Net, Dice + focal loss | **0.961** |

**Other test sites (F1)**

| Site | Baseline | BiAU-Net |
|---|---|---|
| Bredbo | 0.678 | 0.939 |
| Nairobi | 0.487 | 0.793 |

- Averaged over the five sites, F1 is **+19.9%** above FireCCI51. Kappa is +29.9% and MCC +28.3%.
- The bi-temporal input gave the biggest single gain.
- In Tarragona, the bi-temporal input alone *hurt*, and attention gates recovered it.

**Concrete action for us (later, rank 5):**
- Fork the repo.
- Feed our chips at 20 m as pre and post B12/B11/B8A stacks of 128×128 or 256×256.
- Use labels from section 1 plus the BAMT reference perimeters.
- Keep Dice + focal loss.
- Judge it against the random forest by size class. Expect gains mostly at scar edges *(inference)*.

---

## 8. Prithvi-EO-2.0-300M-BurnScars (model card, config and dataset card read in full)

**Links:** [model](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M-BurnScars) · [dataset](https://huggingface.co/datasets/ibm-nasa-geospatial/hls_burn_scars)

**Data**
- **Single date**: post-fire only, not a pre/post pair.
- 6 HLS bands: B02, B03, B04, B8A, B11, B12.
- 804 chips of 512×512 from the contiguous US, 2018-2021. Labels from MTBS.
- Class balance: 11% burned, 88% unburned, 1% no data.

**Accuracy:** test IoU for the burned class **87.52**, mIoU 93.00 (validation 84.28 / 90.95).

**Training config**
- TerraTorch, UNetDecoder with channels [512, 256, 128, 64].
- AdamW with learning rate 1e-4, ReduceLROnPlateau (factor 0.5, patience 4), early stopping with patience 15.
- Batch 8, bf16, D4 augmentation.
- Normalisation means: 0.0333, 0.0570, 0.0589, 0.2323, 0.1973, 0.1194.
- Normalisation stds: 0.0227, 0.0268, 0.0400, 0.0779, 0.0871, 0.0724.

**Licences (corrected):** the **model is Apache-2.0**. The **dataset is CC-BY-4.0**.

**Concrete action for us:**
- Run the checkpoint as is on 50 post-fire Ratapani HLS chips as a zero-shot check. Expect poor recall on scars under 3 ha.
- Fine-tune only after the labels from sections 1 and 4 exist.
- The pre-trained backbone takes 4 time steps, so a pre+post fine-tune is possible.

---

## 9. Tienaho 2025, surface fires under canopy (FULL TEXT, study III)

**Link:** [Dissertationes Forestales 373](https://doi.org/10.14214/df.373)

**Breakpoint recipe**
1. Gather Sentinel-2 NBR for each 10 m pixel, keeping scenes with up to 95% cloud (clear pixels only).
2. Smooth with a **30-day Gaussian moving average**, then interpolate daily.
3. **Subtract the mean NBR of the 5 previous years** to remove the seasonal trend.
4. Average three change points:
   - change in mean, from MATLAB `findchangepts`;
   - change in slope, from the same function;
   - the day of the steepest negative first derivative of the detrended series.

**Results**
- **4 of 7** low-intensity controlled burns were detected, and their dates matched the burn dates.
- Detected sites averaged **53% canopy cover**; the missed sites averaged **72%**.
- dNBR correlated with the ground-vegetation volume loss measured by laser scanning: r = -0.5, R² = 0.25. Adding canopy cover raised R² to 0.50, and adding site as well raised it to 0.84.

**Correction to the earlier note (D5):** "found most of them" means 4 of 7.

**Concrete action for us:** this is the **leaf-fall fix**.
1. For each alert pixel, build a daily NBR series for the fire year (from S2 + Landsat, with 30-day Gaussian smoothing).
2. Subtract the same day-of-year mean of the previous 5 years.
3. Require a detrended drop beyond the 2-sigma inter-annual spread *(inference)*, centred within ±10 days of the alert.
4. Use Python `ruptures` (PELT, mean/slope model) or the steepest-slope day.

- Normal Jan-Feb leaf fall is present in the 5-year mean, so it cancels out.
- Flag scars where canopy cover is above about 70% as "low detectability" instead of "no scar".
- **Expected effect** *(inference)*: the largest precision gain in Jan-Feb.
- **Effort:** 1-2 days, using the existing chip stacks.

---

## 10. Papers read as abstracts only: what is verified

**Bastarrika et al. 2024, Sentinel2BAM**
- Random forest trained by VIIRS and MODIS active fires on 5-day NBR composites, then a quarterly time-series and object step. 576 tiles, 2019.
- Against EMSR21 (21 Copernicus Emergency Service perimeters): **CE 10.3%, OE 7.6%**.
- Against GlobalL105 (Landsat): **CE 22.5%, OE 13.4%**. FireCCI51 scored CE 20.8% / OE 46.5%, and MCD64A1 CE 17.5% / OE 53.1%.
- Global Dice 81.8% on the C3S 2019 reference set (cited by Padilla 2026).
- No public code found. The method is closest to Roteta 2021 (section 3) plus BAMT's random forest (section 4).
- The earlier note's claim about tropical-forest cropland confusion could not be checked.

**Roy et al. 2019**
- Random forest *change regression*, trained on **synthetic fire-effect spectra**, applied to Landsat-8 + Sentinel-2A data adjusted for viewing and sun angle (NBAR) at 30 m.
- Rolling 3-month windows map the central month.
- Temporal consistency checks remove non-fire changes. Region growing reduces omission.
- Output per pixel: burn day and f·cc (burned fraction × combustion completeness).
- Burn dates average **3 days later** than MCD64A1.
- Validation against visual Sentinel-2 maps in 30 km boxes: **OE 0.24, CE 0.06**, relative bias -0.19.
- No active fires are used at all.
- Thresholds for seeding and growing were not available (full text not read).

**Liu et al. 2023**
- Candidates come from single-date, two-date and short-series tests.
- Confirmation uses MODIS, VIIRS, Landsat OLI and Sentinel-2 MSI active fires.
- An inter-annual series rescues candidates that no active fire confirmed.
- Dice was about **7% better than LBA_CU** (US) and about **9% better than FireCCISFD20** (Africa).
- Rules and distances not available.

**Ren et al. 2026 (Amur basin)**
- Active fires plus a **smoothed EBAI** (Enhanced Burned Area Index) on Sentinel-2 series. EBAI responds to an abrupt departure from pre-fire reflectance and a short post-fire anomaly.
- Product: monthly 10 m maps for 2020-2023.
- Accuracy: **CE 7.65-8.46%, OE 9.43-13.02%, Dice 89.94-91.21%**.
- Formula not seen. The earlier note's list of features (MIRBI, NBR2, a B11/B12 index) is unverified.

**Roteta et al. 2019 (SFD11):** **Dice 77%, OE 26.5%, CE 19.3%**. MCD64A1: Dice 53.6%, OE 59.6%, CE 20.4%. All confirmed.

---

## Verified numbers

| Claim in the earlier note | Status | Correct value and source |
|---|---|---|
| A3 SFD11: Dice 77, OE 26.5, CE 19.3; MCD64A1: 53.6 / 59.6 / 20.4 | ✔ | Roteta 2019 abstract |
| A4 SFD20: OE 8.5, CE 15.0, Dice 87.7; 92.5% within 10 days | ✔ | Chuvieco 2022 abstract. The ATBD's internal test gives OE 13.5, CE 7.8, Dice 89.3 |
| A4 "omission cut from 26% to 8.5% by VIIRS plus double revisit" | ✔ (numbers) | The ATBD also shows mixing S2A and S2B raised CE from 22.9% to 30.5% until the per-satellite merge was added |
| A5 Sentinel2BAM CE 10-23, OE 8-13 | ≈ | CE 10.3 / OE 7.6 (EMSR21) and CE 22.5 / OE 13.4 (GlobalL105); global Dice 81.8 |
| A5 FireCCI51 OE 46.5, MCD64A1 OE 53.1 | ✔ | Bastarrika 2024 abstract |
| A6 Dice 82.7 / 84.7 / 85.4 / 87.2 | ✔ | Padilla 2026, Table 2 |
| A7 Liu: about 7-9% better Dice | ✔ | 7% vs LBA_CU, 9% vs FireCCISFD20 |
| A8 Ren: CE about 8, OE 9-13, Dice about 90 | ✔ | CE 7.65-8.46, OE 9.43-13.02, Dice 89.94-91.21. The feature list is unverified |
| A9 Roy: OE 0.24, CE 0.06, 3 days later | ✔ | Roy 2019 abstract. Region growing confirmed; uses no active fires |
| B1 BAMT: CE and OE under 12% in Australia | ✔ | Plus code at github.com/ekhiroteta/BAMT |
| C1 Prithvi: 804 chips, IoU 87.5, Apache-2.0 | partly | The model is Apache-2.0 but the **dataset is CC-BY-4.0**. The model is **single-date** (post-fire only) |
| C4 BiAU-Net: F1 about 20 points better than FireCCI51 | ≈ | +19.9% F1 averaged over 5 sites. Code is public |
| C5 Hu: classic machine learning beats deep learning on scattered burns | ✘ (overgeneralised) | Only at 1 of 3 test sites (Trängslet, kappa about 0.88); deep learning won at the other two |
| D5 Tienaho: breakpoint analysis found most fires | ≈ | 4 of 7 sites. Missed sites had about 72% canopy cover vs 53% |
| E1 Chandel: weak Feb-Mar, varies with sun azimuth, "confirms our Jan-Feb weakness" | ✘ for forest | The month and azimuth effect was in **agricultural** burns; forest-fire accuracy did not vary systematically. Hillshade did not help. "FIRMS" was MODIS 1 km |
| FireCCI SFD confirmation region | new | IB regions over 30 ha; hotspot dilation 380 m diameter (VIIRS) or 1 km (MODIS) |

**Exact formulas to use in code** (reflectance 0-1; Sentinel-2 L2A from processing baseline 04.00 onward needs the BOA_ADD_OFFSET of -1000 removed before dividing by 10000, or every fixed threshold above shifts. This is a standard L2A detail, not from these papers.)

```
NBR   = (B8A - B12) / (B8A + B12)        # 20 m; B8 at 10 m is also used
NBR2  = (B11 - B12) / (B11 + B12)
MIRBI = 10*B12 - 9.8*B11 + 2
NDMI  = (B8A - B11) / (B8A + B11)
M     = |mu_b - mu_u| / (sigma_b + sigma_u)   # separability, use > 1 (or 0.75 for the IBC/IBNC test)
IB    : dMIRBI > 0.25 & dNBR2 < -0.05 & dNIR < -0.01 & post below the scene mean on all three
mask  : SCL in {0,1,6,8,9,10,11} (8/9/10 dilated 5 px) | B12_post < 0.07
```

---

## Ranked action list

| Rank | Action (thread) | Inputs and settings | Expected gain | Effort |
|---|---|---|---|---|
| 1 | **Two-phase SFD20 port as pass 2** (alert-scar) | Section 1 rules; IBC within 190 m of a VIIRS alert; percentiles pooled over AOI chips in 10-day windows; raw SEPB grow cut 0.05; 8-connectivity; no 30 ha rule | Recall 71% → ~76-80%, precision held *(inference)* | 2 days |
| 2 | **Leaf-fall detrending and breakpoint test** (alert-scar, Jan-Feb) | Section 9: 30-day Gaussian NBR, minus the 5-year same-day-of-year mean, change point within ±10 days of the alert; flag canopy over ~70% as low detectability | Biggest Jan-Feb precision gain; perhaps 83% → ~87% overall *(inference)* | 1-2 days |
| 3 | **Shadow and sensor hygiene** (alert-scar) | Post-image B12 < 0.07 mask; 5-pixel cloud dilation; per-sensor maps cross-confirmed by another sensor's adjacent date; L2A offset check | Fewer shadow false scars. In the ATBD, mixing satellites cost 7.6 points of CE | 0.5 day |
| 4 | **Active-fire density plus logistic fusion, and 0/5/10-day statuses** (alert-scar, `live.py`) | Gaussian KDE with sigma 2 km and 4 days; logistic on (spectral probability, AF density); Dice sweep in 0.05 steps | About +2 Dice from provisional to 5-day status; precision on crop edges | 1 day |
| 5 | **Otsu thresholds with floors and doubled cropland thresholds** (alert-scar) | Section 3 floors (dNBR -0.05, dNBR2 -0.05, dMIRBI 0.25, dNIR -0.02); ×2 in cropland; date pair = largest NBR drop | Precision on agricultural-edge alerts | 0.5 day |
| 6 | **Per-season random forest with Chandel features and a leaf-fall negative class** (alert-scar) | 500 trees, minimum leaf 10; dNBR, dNBR2, dMIRBI, dNIR plus post NDMI, MIRBI, NDVI, NBR; seeds and >50% growth as in BAMT | Recall gain similar to rank 1; can replace rank 1 if it wins on the reference set | 2 days |
| 7 | **BAMT reference perimeters for one season** (validation) | Section 4 RP tool, 10 m, per fortnight; include leaf-fall and harvest as negatives | Honest accuracy by size class (<1, 1-3, >3 ha) | 2-3 days |
| 8 | **BiAU-Net fine-tune** (alert-scar, later) | Public repo; B12/B11/B8A pre and post; Dice + focal loss; labels from ranks 1 and 7 | Uncertain; mainly better edges | 3-5 days |
| 9 | **Prithvi zero-shot check** (alert-scar, later) | Single-date HLS, 6 bands, published normalisation | Probably low on small scars; a cheap check | 0.5 day |
