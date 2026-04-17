# Stage VLM.2 - CLIP Pilot - VERDICT: FAIL (CLIP-ViT-L/14 + LR @ ROC=0.562)

**Date:** 2026-04-16
**Backend:** HuggingFace `openai/clip-vit-large-patch14` image tower (768-dim projected features)
**Device:** directml:0  (DirectML disabled - `torch_directml` DLL incompatible with torch 2.11 in this env)
**Embeddings:** `data_lake/audits/clip_embeddings.parquet` (gitignored)
**Wall time:** 178s

## Hypothesis

Where LLaVA-7b text scoring failed to discriminate the same 200-cell pilot
(Mann-Whitney p=0.74, see `vlm_pilot_finding.md`), CLIP-ViT-L/14 image
embeddings - trained on 400M web image-text pairs - might still encode
visual structure correlated with imminent ignition. We bypass the text head
entirely and probe the 768-dim shared embedding with a simple linear
classifier (LR) plus a non-linear sanity check (LightGBM).

## Pilot design

- **Pairs:** Same 200-row manifest from VLM.1 (100 ignited low-Hawkes 2025 cells +
  100 matched controls). Of these, **200 chips were actually on disk**
  (15 chips were never fetched in the original VLM.1 run). Per-class kept:
  ignited=100, control=100.
- **Imagery:** 224 x 224 px Sentinel-2 RGB chips, 6.7 km field of view, from
  [D-14, D-1] before each cell's "decision day" D.
- **Embedding:** `CLIPModel.from_pretrained("openai/clip-vit-large-patch14").get_image_features(...)`,
  CPU forward pass.
- **Classifier (CV):** 5-fold StratifiedKFold, StandardScaler -> balanced LogisticRegression
  (lbfgs, C=1.0, max_iter=2000), random_state=42.
- **Classifier (sanity):** LightGBM with `is_unbalance=True`, 80/20 stratified hold-out,
  early stopping (patience=50).
- **Permutation:** 1000 label shuffles, each scored as the mean of a 5-fold
  liblinear LR (max_iter=200 for speed). One-sided p over observed mean CV ROC.

## Result

| metric | value |
|---|---:|
| fold 1 | 0.7250 |
| fold 2 | 0.6200 |
| fold 3 | 0.4650 |
| fold 4 | 0.4775 |
| fold 5 | 0.5225 |
| **5-fold mean ROC** | **0.5620** |
| **5-fold std ROC** | 0.0980 |

### LightGBM (non-linear sanity check)

- 80/20 stratified hold-out on `class_int`
- ROC = **0.4750**, best_iter = 2

Top 10 features by gain:

| feature | gain |
|---|---:|
| emb_218 | 50.3 |
| emb_625 | 27.1 |
| emb_366 | 19.4 |
| emb_239 | 9.8 |
| emb_205 | 9.2 |
| emb_464 | 4.1 |
| emb_120 | 1.8 |
| emb_743 | 1.8 |
| emb_762 | 0.0 |
| emb_761 | 0.0 |


### Permutation test

- 1000-iteration label-shuffle permutation (5-fold liblinear LR per shuffle)
- Null mean ROC = 0.4957, std = 0.0536
- One-sided p = **0.0949** (Pr[null mean ROC >= observed 0.5620])

## Verdict

| criterion | threshold | observed | result |
|---|---:|---:|---|
| 5-fold mean CV ROC | >= 0.60 | 0.5620 | FAIL |
| Permutation p (one-sided) | < 0.05 | 0.0949 | FAIL |

**OVERALL: FAIL**

## Score histograms

See `tmp/clip_score_hist.png` for the out-of-fold P(ignited)
distribution split by true class (rendered if matplotlib was available).

## Interpretation

CLIP embeddings do not separate ignited from matched controls on this 200-cell matched-pair pilot. The signal we hoped to capture (anthropogenic ground-clearing micro-patterns at 30 m effective resolution) is below CLIP's discriminative floor OR is genuinely not encoded by web-pretrained ViT features. This rules out the cheapest revival of the VLM hypothesis flagged in `vlm_pilot_finding.md` step 3.

## What it would take to revisit (if FAIL)

1. **10 m native chips, no downsample.** Send the 670 x 670 px raw chip through a
   ViT-L/14 model that supports it (not vanilla CLIP - patches are fixed 14x14).
   Would require a higher-resolution backbone (Prithvi-EO-2.0 at native, or DINOv2-ViT-g/14
   at variable input size).
2. **Domain pretraining.** Fine-tune or LoRA-adapt CLIP on a self-supervised
   Sentinel-2 corpus (e.g., SatMAE) before this probe. Cost: 1-2 GPU days.
3. **Multi-temporal.** Stack [D-14, D-7, D-1] chips and train a tiny temporal
   convnet on the resulting (3, 768) sequence. Captures change, which static
   chips cannot.

## Files

- `scripts/clip_pilot_classifier.py` - single-file pipeline (this run's source)
- `data_lake/audits/clip_embeddings.parquet` - 185 rows x (3 meta + 768 emb) cols (gitignored)
- `tmp/clip_null_roc_dist.npy` - null distribution from the permutation test
- `tmp/clip_score_hist.png` - oof score histogram
- `data_lake/audits/vlm_pilot_chips/` - same 185 chips reused from VLM.1

## Reproducibility

```bash
python scripts/clip_pilot_classifier.py        # full run, ~25 min on CPU
python scripts/clip_pilot_classifier.py --no-permute   # skip null distribution
python scripts/clip_pilot_classifier.py --limit 20 --n-perm 50   # smoke test
```

Deterministic given a fixed random seed (42) and pinned versions
(transformers==5.5.4, sklearn==1.8.0, lightgbm==4.6.0, torch==2.11.0+cpu).
HuggingFace `openai/clip-vit-large-patch14` weights pulled from cache; first run downloads ~1.7 GB.
