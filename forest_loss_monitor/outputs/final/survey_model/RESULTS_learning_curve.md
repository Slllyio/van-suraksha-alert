# RESULTS: label learning curve, Bamori 2022, 3 classes (14 Nov 2026)

Pre-registration: `PREREG_LEARNING_CURVE.md` (written before any run; nothing changed after). Script: `e150_learning_curve.py`.
155 Bamori polygons; cv2022 2.5 km spatial-block GroupKFold 5; the 6,623 test px are fixed. Whole polygons were subsampled inside each training fold,
stratified by class. Every model used the same subsets. The 284 / 304 sets were not used. No GEE or image requests were made.
Queue: 13:03-20:16 IST, single chain, GPU otherwise idle.

Sanity checks: at 100 %, every model reproduces its cv2022 number exactly: LightGBM 0.869 / 0.831, AlphaEarth RF 0.893 / 0.856, b223cPT 0.817 / 0.766
(identical per-epoch losses).

## Scores (pooled over 5 test folds)
Spread: ± SD over 3 subset seeds at 25 % and 50 %. At 75 % and 100 % there is one seed; the bracket gives the macro-F1 SD across the 5 folds instead.
"Polys" is the mean number of training polygons per fold.

| Model | Frac | Polys | Accuracy | Macro-F1 | Bare F1 |
|---|---|---|---|---|---|
| LightGBM HLS | 25 % | 32 | 0.846 ± 0.013 | 0.809 ± 0.013 | 0.711 ± 0.006 |
| | 50 % | 62 | 0.861 ± 0.009 | 0.821 ± 0.018 | 0.707 ± 0.040 |
| | 75 % | 92 | 0.869 | 0.832 (fold 0.091) | 0.728 |
| | 100 % | 124 | 0.869 | 0.831 (fold 0.104) | 0.727 |
| AlphaEarth RF | 25 % | 32 | 0.862 ± 0.005 | 0.813 ± 0.007 | 0.665 ± 0.016 |
| | 50 % | 62 | 0.888 ± 0.007 | 0.847 ± 0.014 | 0.721 ± 0.036 |
| | 75 % | 92 | 0.896 | 0.861 (fold 0.039) | 0.749 |
| | 100 % | 124 | 0.893 | 0.856 (fold 0.082) | 0.742 |
| AlphaEarth MLP | 25 % | 32 | 0.862 ± 0.017 | 0.822 ± 0.022 | 0.701 ± 0.036 |
| | 50 % | 62 | 0.898 ± 0.010 | 0.862 ± 0.015 | 0.760 ± 0.037 |
| | 75 % | 92 | 0.905 | 0.872 (fold 0.052) | 0.775 |
| | 100 % | 124 | 0.903 | 0.870 (fold 0.064) | 0.782 |
| Prithvi b223cPT (DW pre-train) | 25 % | 32 | 0.732 ± 0.016 | 0.664 ± 0.025 | 0.480 ± 0.069 |
| | 50 % | 62 | 0.784 ± 0.029 | 0.723 ± 0.038 | 0.537 ± 0.072 |
| | 75 % | 92 | 0.826 | 0.781 (fold 0.103) | 0.635 |
| | 100 % | 124 | 0.817 | 0.766 (fold 0.042) | 0.609 |
| Prithvi P-b22-3c (no pre-train) | 25 % | 32 | 0.687 ± 0.007 | 0.600 ± 0.024 | 0.382 ± 0.098 |
| | 50 % | 62 | 0.753 ± 0.039 | 0.672 ± 0.065 | 0.441 ± 0.124 |
| | 75 % | 92 | 0.788 | 0.717 (fold 0.083) | 0.494 |
| | 100 % | 124 | 0.796 | 0.736 (fold 0.083) | 0.552 |

## Pre-registered decision (primary: macro-F1, LightGBM minus b223cPT, points)
| Gap at | 25 % | 50 % | 75 % | 100 % |
|---|---|---|---|---|
| Macro-F1 | 14.5 (SD 1.9) | 9.8 | 5.1 | 6.6 |
| Accuracy | 11.5 (SD 1.5) | 7.7 | 4.2 | 5.2 |
| Bare F1 | 23.1 (SD 6.8) | 17.0 | 9.3 | 11.8 |

Narrowing in macro-F1 is 7.9 points. The threshold is 2 + 1.9 = 3.9 points. **Verdict: the gap is closing.** Accuracy gives the same verdict (6.3 > 3.5).
Secondary, AlphaEarth RF minus b223cPT: macro-F1 15.0 → 9.1, closing (5.9 > 4.3). Bare F1 is not closing (5.1 < 7.4).
Without pre-training, P-b22-3c is closing too (macro-F1 gap 20.8 → 9.5), but it stays about 3 points below b223cPT at every fraction.
The DW pre-train helps most when labels are scarce (+6.4 macro-F1 at 25 %, +3.0 at 100 %).

## Plain-language reading and extrapolation
- **The gap closes because LightGBM stops improving, not because Prithvi catches up.**
  - LightGBM reaches its ceiling by about 60-90 polygons: macro-F1 0.809 at 32 polygons and 0.831 at 124, about +1.2 points per doubling.
  - Prithvi is still rising, at about +5.8 points per doubling (b223cPT).
  - But its last step (92 → 124 polygons) went down slightly (0.781 → 0.766), and that is within its fold spread.
- **Straight-line extrapolation in log(polygons):**
  - Prithvi b223cPT would meet LightGBM at about 270 training polygons (about 340 in total, a bit over 2× the current 155) in both macro-F1 and accuracy.
  - It would meet AlphaEarth RF only at about 570-630 training polygons (about 4×).
- **These crossing points are optimistic for Prithvi.** The 75 → 100 % step shows its curve may already be flattening.
  If it keeps flattening, it may never cross. Bare F1 is the weakest point: 0.61 against 0.73 for LightGBM and 0.78 for the AlphaEarth MLP.
- **Practical answer:**
  - About twice as many hand polygons might bring Prithvi level with LightGBM. Even then it would not beat the AlphaEarth embeddings.
  - AlphaEarth MLP is the best model at every fraction from 50 % up (macro-F1 0.870 at 100 %). It is about as good with 62 polygons as with 124.
  - For this 3-class task, more local labels pay off least for Prithvi as a winner. They pay off mainly as a way to reach parity.

## Files (outputs/final/survey_model)
`lc_subsets.json`, `lc_runs/*.json` and `lc_runs.csv` (per run), `lc_table.csv`, `lc_decision.csv`, `lc_extrapolation.csv`,
`run_lc_*.out`, `run_queue_lc.{sh,log}`. Per-fold Prithvi test predictions are in `work/survey_model/lc_pred/`.
