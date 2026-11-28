# Prithvi diagnosis (Guna survey-calibrated state model), 7 Nov 2026

## 1. Label audit

**Class counts after 30 m erosion and mixed-compartment removal** (`audit_counts.csv`): forest 502,933 px (28%), open 883,810 (49%), farm 399,957 (22%).
Forest is not a small minority overall, but its share varies widely by range: Bamori 6%, Binaganj 13%, North Guna 22%, Fatehgarh 25%,
South Guna 32%, Raghogarh 48%, Maksudangarh 61%, Aron 66%. Leave-one-range-out therefore moves the class prior a lot between folds.

**Label noise** (`audit_signal_by_class.csv`, `audit_suspect.csv`). Median 2015 NDVI (post-monsoon / summer / rabi): forest 0.49 / 0.32 / 0.41,
open 0.37 / 0.27 / 0.34, farm 0.33 / 0.22 / 0.50. The three classes overlap heavily; open (BLANK) sits between forest and farm on every season.
Fixed mislabel rule, declared before any variant was scored:
- a forest pixel looks non-wooded if its post-monsoon NDVI is below 0.40;
- a farm pixel looks wooded if its post-monsoon NDVI is at least 0.60, its summer NDVI at least 0.30, and rabi minus summer below 0.10.

Result: 21.2% of forest pixels look non-wooded (106,393 px); 71 of 421 forest compartments are majority-suspect.
Only 156 farm pixels look wooded (0.04%). Open is not cleaned.
The UNDER STOCK / PLANTATION label is the noisy one, and it is exactly the class the change rule depends on.

**Spatial layout.** 454 of the 546 training patches (224 px = 6.7 km) lie more than 95% within one range, and the median patch is 100% one range.
A held-out range is therefore a contiguous, unseen area.
Per-range band means differ by up to 0.9 standard deviations (`audit_range_band_shift_z.csv`), Fatehgarh most (NIR +0.5 to +0.9 sd, SWIR1 +0.9 sd).
The pixel GBM copes with this shift (70.7%); the patch model did not.

**Alignment** (`audit_alignment.png`, 5 random patches). Compartment boundaries rasterised on the 30 m HLS grid follow the visible field and forest
edges. There is no row or column shift and the CRS is the same (MP Albers). The HLS tiles were fetched with computePixels on an explicit grid,
so the sampleRectangle flip bug does not apply here.

## 2. Recipe audit (run A)

- **Normalisation:** correct. Prithvi-EO-2.0-300M's own means and stds from its config, same band order (B02-B07), same 0-10,000 reflectance scale.
  Missing pixels were set to 0 after normalisation, and 2015 coverage inside the labelled area was complete.
- **Time axis:** correct. The 3 seasons go on the time axis (T = 3), each frame through the patch embedding, with the 3D sin-cos position table
  sliced to 3 frames. The 300M model has no temporal or location encoding, so nothing needed disabling.
- **Loss and sampling: the weak point.** Weighted cross-entropy (inverse frequency), no augmentation, a fixed set of 546 patches,
  4 fixed epochs, learning rates 1e-4 (4 blocks) and 1e-3 (head), no scheduler, no early stopping.
  Training loss fell to 0.13 (about 95% training accuracy) while held-out accuracy was 42%, which is memorisation.
- **Head and eval mode:** fine. The head has no batch norm; the encoder uses LayerNorm only; eval mode was set for prediction.
  The token layout (CLS dropped, t-major 3 x 14 x 14) matches the embedding order.

**Conclusion of steps 1-2.** There is no pipeline bug: normalisation, time axis and alignment are correct.
The likely causes, in expected order of size:
1. An over-capacity recipe without augmentation or early stopping (4 blocks, 25M trainable parameters, 546 fixed patches), so the model memorises
   training-range scenes.
2. A forest label that is 21% non-wooded, and forest shares that swing from 6% to 66% by range.
3. Spectral shift between ranges, Fatehgarh most.

## 3. Pre-declared variants (fixed before scoring; all leave-one-range-out on the same held-out test pixels as A, B, C)

- **a. Frozen Prithvi + linear per-pixel head.** All 24 blocks frozen; a 1x1 linear map from the 3-frame token features (3 x 1024) to 3 classes,
  bilinearly upsampled to pixels. Weighted CE, Adam lr 1e-3, 3 epochs over the 546 cached patches.
- **b. Fine-tuned, fixed recipe.**
  - Blocks 1-22 frozen; blocks 23-24 plus the segmentation head trained.
  - Training crops: a bank of 6,000 random 224 px crops with random flips and rotations (8 dihedral transforms) from the 2015 raster, drawn once
    for compute reasons; 3,000 crops sampled per epoch.
  - Weighted CE; lr 1e-5 (blocks) and 1e-4 (head) with cosine decay over 15 epochs.
  - Early stopping, patience 3, on an inner validation range: the next range alphabetically after the held-out one.
  - Final model: all ranges, with the epoch count set to the median of the early-stopping epochs across folds.
- **c.** Same as b, trained on cleaned labels (suspect pixels dropped).
- **d.** LightGBM (model C settings) on cleaned labels.

Test pixels are the original labels for every variant; cleaned-label test figures are reported as a second view.
The change rule and scoring are unchanged from the head-to-head (`e110_survey_score.py`).

## 4. DirectML bug 1: bilinear upsampling (real, but not the main cause)

`F.interpolate(mode="bilinear", align_corners=False)` on the AMD RX 9060 XT (torch-directml, torch 2.4.1) disagrees with CPU by 89% (forward) and 91% (gradient).
`nn.Upsample(bilinear, align_corners=False)` is off by 34%, and bilinear downsampling by 220%.
Both Prithvi heads (run A and variant a) upsample tokens to pixels with this op, so their outputs and gradients were wrong. That explains:
- A memorising training scenes (89% in-sample) but collapsing to "farm" on held-out ranges;
- the linear probe failing even on its own training ranges (46%).

What was checked and is fine:
- encoder on DirectML vs CPU: 1.4e-6 relative difference after block 1, 3.5e-6 after block 20; the token cache matches CPU (4e-4, fp16);
- normalisation, time axis, alignment (section 1-2);
- a logistic probe on pure 480 m tokens reaches **77.5%** leave-one-range-out (LightGBM per pixel 70.7%), so the backbone features are good.

Fix: `up_bilinear()` in `e108_prithvi_net.py` does bilinear upsampling as two matrix products with interpolation matrices built on CPU.
It matches CPU F.interpolate to 6e-8 (forward) and 5e-7 (backward). All Prithvi runs (A, a, b, c, and the new variant e, the token probe) are rerun with the fix.
The invalid first results are kept in `invalid_bilinear_bug/`.

### Other ops tested on DirectML vs CPU (forward / backward relative difference)
| op | result |
|---|---|
| interpolate bilinear, align_corners=False (up or down) | **BROKEN** (0.89-2.2) |
| nn.Upsample bilinear, align_corners=False | **BROKEN** (0.34) |
| interpolate bilinear, align_corners=True | ok (1e-6) |
| interpolate nearest, bicubic | ok |
| grid_sample bilinear | ok (1e-6) |
| avg_pool2d ceil_mode, max_pool2d, adaptive_avg_pool2d | ok |
| ConvTranspose2d, pixel_shuffle, GELU, scaled_dot_product_attention | ok |
| Conv3d | not supported on DirectML (hence the Conv2d shim) |

### Earlier runs on this PC
- **forest_loss_monitor e67_prithvi.py (frozen Prithvi features, 5 Nov; 36-38% precision / 53-62% recall at the Guna points), e63_cascade.py, e65_prithvi_chips.py:**
  unaffected. They ran on CPU (no DirectML device) and pooled token means with no interpolation.
- **Fire project (E:\FIRE, read-only here, not changed): affected and should be re-verified.**
  - `src/train/train_vanaagni.py` selects DirectML and uses 6 bilinear (align_corners=False) interpolations for logits, dNBR and fire-logit resizing.
  - `src/model/vanaagni.py` has one in the final upsample; `prithvi_ft/src/model/vanaagni.py` uses bilinear throughout.
  - `src/model/change_head.py`, `prediction_head.py` and `film_layers.py` use nn.Upsample / interpolate bilinear (align_corners=False).
  - `src/model/presto_wrapper.py` has one.
  - `ros_unet.py` uses align_corners=True and is fine.
  - Any VanAagni / Prithvi fire model trained or evaluated on DirectML (including VanAagni v1.0, P 80.6% / R 69.6%) should be re-evaluated on CPU.
    A quick check is to score the frozen checkpoint once on CPU and once on DirectML and compare.


## 5. DirectML bug 2: cross-entropy with ignore_index (the main cause)

After the bilinear fix, A (fine-tuned) still scored 42.4% held-out (forest 10%, open 10%, farm 99%) and a (linear probe) 42.1%.
`F.cross_entropy(..., ignore_index=-1)`, with or without class weights, gives wrong gradients on DirectML: 51-61% relative error against CPU.
Plain cross-entropy with no ignore index is exact (5e-8).
Every dense Prithvi run marks unlabelled pixels -1, which is most of each 224 px patch, so the gradients pushed toward the wrong class.
`F.one_hot` also fails on DirectML (scatter error).

Fix: `masked_ce()` in `e108_prithvi_net.py`, built from log_softmax and a one-hot made by comparing against arange.
It matches CPU F.cross_entropy(weight, ignore_index=-1) to 9e-8 in the gradient. It is now used in `e109_prithvi_survey.py` and `e112_prithvi_variants.py`.
**No dense Prithvi variant has been rerun with both fixes yet.**

## 6. Results so far (leave-one-range-out, same 501,193 held-out test pixels)

| variant | state | overall | forest R / P | open R / P | farm R / P |
|---|---|---|---|---|---|
| C LightGBM, HLS 2015 | valid | 70.7% | 55 / 61 | 70 / 68 | 81 / 79 |
| d LightGBM, cleaned labels | valid | 70.6% | 57 / 60 | 69 / 68 | 81 / 80 |
| B AlphaEarth MLP (2017 proxy) | valid | 68.5% | 53 / 55 | 66 / 66 | 81 / 78 |
| e Prithvi frozen token probe (CPU sklearn, 480 m output) | valid | 64.2% (66.1% on cleaned test pixels) | 59 / 51 | 60 / 66 | 73 / 71 |
| A Prithvi fine-tuned, first run | invalid (both bugs) | 41.7% | | | |
| A after the bilinear fix only | invalid (CE bug) | 42.4% | 10 / 47 | 10 / 80 | 99 / 40 |
| a frozen + linear head | invalid (CE bug) | 42.1% | 25 / 64 | 2 / 80 | 99 / 40 |
| b, c | not run (b was stopped during its first fold) | | | | |

The token-level probe on pure tokens (more than 90% one class) reaches 77.5% leave-one-range-out, so the backbone features carry the signal.
Change head-to-head so far (from the first run, all models invalid for A): see `invalid_bilinear_bug/head_to_head.csv`. Only B and C are valid there.

## 7. What remains (for the Prithvi thread)
1. Rerun A, a, b, c with both fixes: `e109_prithvi_survey.py cv`, `final`; `e112_prithvi_variants.py cv a`, `final a`; `bank` (the 6,000-crop bank in `work/survey_model/prithvi_bank22` is already built), `cv b`, `final b`, `cv c`, `final c`. `final e` is done (`states_Ae.npz`).
2. Score everything: `e110_survey_score.py` (includes A, Aa, Ab, Ac, Ae, B, C, Cc).
3. Re-verify the fire project's DirectML models (VanAagni etc.) against CPU (section 4).
