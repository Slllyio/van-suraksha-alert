# Stage VLM.2 Pilot -- VERDICT: FAIL (5-fold ROC = 0.539 +/- 0.048)

**Date:** 2026-04-17
**Source pairs:** `data_lake/audits/vlm_pilot_scores.parquet` (100 ignited / 100 control low-Hawkes 2025 hold-out)
**Modelling subset:** 188/200 cells with both T-30 and T0 chips
**Chip pixels:** 64x64 | **Cloud max:** 60%

## Hypothesis

Stage VLM.1 showed a single Sentinel-2 RGB chip has no LLaVA-discriminable pre-fire signal (mean delta -0.29, p=0.74, rho=-0.045). VLM.2 tests a different cut on the same imagery: instead of asking a VLM to score one chip, we compute scalar pixel-level indices (NDVI, NDWI, bare-soil ratio, RGB norm) on TWO chips (T0 = D-14..D-1, T-30 = D-37..D-31), take their deltas, and feed the resulting tabular features to LightGBM.

## Pilot design

- **Source:** 200 (cell, date, class) rows reused from VLM.1 pilot.
- **Imagery:** Sentinel-2 SR Harmonized via `getDownloadURL` (NPY format, raw uint16 reflectance scaled to [0,1]). Bands: B2 (Blue), B3 (Green), B4 (Red), B8 (NIR).
- **Windows:** T0 = [D-14, D-1], T-30 = [D-37, D-31]. Least-cloudy scene per window with `CLOUDY_PIXEL_PERCENTAGE <= 60`.
- **Chip size:** 64x64 over a 6.7 km x 6.7 km footprint (~104 m/px). Downsampled vs VLM.1's 224x224 to keep 400 GEE fetches tractable; for scalar mean/fraction features the loss is small.
- **Indices:** NDVI = (NIR-R)/(NIR+R); NDWI = (G-NIR)/(G+NIR); bare-soil ratio = R/(R+G+B) (proxy for SWIR-based BSI, since SWIR not fetched in this pilot).
- **Model:** LightGBM binary, `is_unbalance=True`, n=300, num_leaves=15, min_data_in_leaf=5, lr=0.05. 5-fold StratifiedKFold(random_state=42).

## Result -- per-fold ROC AUC

| Fold | ROC AUC |
|------|--------:|
| fold 1 | 0.5956 |
| fold 2 | 0.5319 |
| fold 3 | 0.5900 |
| fold 4 | 0.4708 |
| fold 5 | 0.5088 |
| **mean +/- std** | **0.5394 +/- 0.0478** |

## Feature importance (gain, summed across folds)

| Feature | Gain |
|---------|-----:|
| bsi_delta | 1311.7 |
| ndvi_t0_mean | 1174.5 |
| bsi_t0_mean | 1127.2 |
| bsi_t30_mean | 1073.9 |
| ndwi_delta | 1041.3 |
| ndwi_t0_mean | 1009.5 |
| frac_pix_ndvi_drop_gt_0p1 | 1006.4 |
| ndvi_t30_mean | 944.1 |
| ndwi_t30_mean | 721.4 |
| rgb_mean_delta | 703.8 |
| ndvi_delta | 575.6 |

## Verdict

- **Mean CV ROC >= 0.60:** 0.539 -> **FAIL**
- **>= 1 delta feature in top 3:** top3 = ['bsi_delta', 'ndvi_t0_mean', 'bsi_t0_mean'] -> **PASS**

**Overall verdict: FAIL**

## What it would take to revisit (if FAIL)

1. **Full 224x224 chips** (matches VLM.1 footprint, captures more spatial heterogeneity).
2. **Add B11/B12 SWIR bands** for true BSI = ((SWIR1+R) - (NIR+B)) / ((SWIR1+R) + (NIR+B)) and NBR = (NIR-SWIR2)/(NIR+SWIR2).
3. **Cell-block spatial CV** (matched ignited/control may be geographically close, inflating CV ROC).
4. **Per-pixel CNN on the delta tensor** instead of scalar mean features -- preserves spatial information our 11 scalars discard.

## Files

- `scripts/pilot_temporal_delta.py`
- `data_lake/audits/temporal_delta_features.parquet` (200 rows)
- `data_lake/audits/temporal_chips/` (npz cache, ~376 files)

## Reproducibility

```
python scripts/pilot_temporal_delta.py --cloud-max 60 --chip-pixels 64
```
