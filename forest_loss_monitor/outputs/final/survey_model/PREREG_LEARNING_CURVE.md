# PREREG: label learning curve, Bamori 2022, 3 classes (written 14 Nov 2026, before any run)

## Question
Does Prithvi close the gap to LightGBM (and to AlphaEarth) as the number of local training labels grows?

## Data and folds (unchanged from cv2022)
- Labels: the 155 hand-drawn Bamori 2022 polygons, 3 classes (1 woodland, 2 bare, 3 cropland; `TO3` coding).
  Per class: 29 woodland, 19 bare, 107 cropland.
- Folds: the cv2022 2.5 km spatial-block GroupKFold 5 (`lab2022_folds.json`).
- Test pixels: the fixed 6,623 test px (`lab2022_test.csv`). They never change with the fraction.
- The 284 / 304 sets are not used anywhere.

## Subsets
- For test fold f, the training pool is every polygon with fold != f.
- Whole polygons are subsampled from the pool at 25 / 50 / 75 / 100 %, stratified by class:
  for each class, a random permutation of its pool polygons, keep the first max(1, round(fraction x n_class)).
  Subsets are nested within a seed (25 ⊂ 50 ⊂ 75 ⊂ 100).
- Seeds: 3 subset seeds (0, 1, 2) at 25 % and 50 %; seed 0 only at 75 % and 100 %. The permutation RNG is `default_rng(1000 x seed + f)`.
- Every model gets exactly the same subset polygons for each (fraction, seed, fold). Subsets are written once to `lc_subsets.json`.
- Model seeds stay fixed (SEED = 7), so the only thing that varies across seeds is which polygons are used.

## Models (settings frozen; identical to cv2022 except the training polygons)
1. **Prithvi b223cPT** (primary Prithvi arm): the e121 P-b22-3c recipe (blocks 23-24 + norm + head, 2,000-crop block-22 bank,
   1,000 crops / epoch, lr 1e-5 / 1e-4 cosine, max 15 epochs, patience 3), initialised from the T0 DW pre-train (`prithvi_dwpt.pt`).
   - As in cv2022, Prithvi trains on the subset polygons outside folds f and vf = (f+1) mod 5,
     and early-stops on the test px of the subset polygons in fold vf. So it sees the same polygons as the CPU models, no more.
   - At 100 % this is exactly the cv2022 protocol (sanity check: about 0.817 acc3).
   - Note: `prithvi_dwpt.pt` was rewritten on 8 Nov 23:29 by a re-run of the same T0 recipe (51 DW tiles, seed 7).
     Its zero-shot scores equal the original 19:23 run (acc3 0.693, macro-F1 0.496, R_bare 0.0), so it is treated as the T0 checkpoint.
2. **Prithvi P-b22-3c** (no pre-train): same, without the PT init. Runs last, only if time allows.
3. **LightGBM**, HLS 2022 features (`e107.feats`, `model("C")`), up to 80 px per training polygon (`e116.train_px`).
4. **AlphaEarth RF** 2022 (500 trees, balanced) and **AlphaEarth MLP** 2022 (`model("B")`), same px sampling.

## Metrics
Per (model, fraction), pooled over the 5 test folds: accuracy, macro-F1 (3 classes) and bare F1 (F1 of class 2).
Spread: SD and min-max across the 3 seeds at 25 % and 50 %. At 75 % and 100 % (one seed) the SD across the 5 folds is reported instead, labelled as fold spread.

## Decision rule (fixed now)
- Primary metric: **macro-F1**. Accuracy gets the same rule as a secondary.
- Gap = LightGBM minus Prithvi b223cPT, computed per seed on the same subsets.
- Narrowing = mean gap at 25 % (3 seeds) minus gap at 100 %.
- **The gap is closing only if narrowing > 2.0 points + SD of the gap across the 3 seeds at 25 %.**
  Otherwise the gap is not closing.
- The same rule is applied to the AlphaEarth RF minus Prithvi gap, as a secondary.

## Extrapolation (descriptive only, not part of the decision)
Fit metric = a + b x log2(training polygons) per model on the fraction means. Report where the Prithvi and LightGBM lines would cross,
in polygons, and say plainly whether that is within reach of a feasible labelling effort. Curves that are linear in log usually flatten,
so a crossing estimate is optimistic for the model that rises more slowly.

## Not changed after seeing results
Fractions, seeds, recipes, epochs, the validation rule and the decision rule above.
Script: `forest_loss_monitor/scripts/e150_learning_curve.py` (worktree competent-engelbart-9ecd52), run against the pipeline in `E:/FIRE/forest_loss_monitor/scripts`.
