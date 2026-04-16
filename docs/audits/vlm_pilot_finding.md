# Stage VLM.1 Pilot — VERDICT: FAIL (LLaVA-7b cannot discriminate MP precursors)

**Date:** 2026-04-16
**Backend:** Ollama / LLaVA-7b @ temperature 0.4
**Output:** `data_lake/audits/vlm_pilot_scores.parquet` (200 rows, 100% valid)

## Hypothesis

A zero-shot Vision-Language Model can detect anthropogenic ground-clearing patterns in pre-fire Sentinel-2 imagery (leaf-litter raking, brush-cutting, geometric bare-soil patches around mahua/tendu trees, agricultural burn preparation). If true, ignited low-Hawkes cells would score systematically HIGHER than matched controls in the 14 days before ignition, giving us a precursor signal that v17's tabular features cannot see.

## Pilot design

- **Pairs:** 100 ignited low-Hawkes cells from 2025 hold-out (Hawkes neighbors ≤ 1) + 100 matched controls (same beat, same Thursday, no ignition). Selection in `scripts/pilot_vlm_precursor.py:select_pilot_pairs`.
- **Imagery:** least-cloudy Sentinel-2 RGB scene from [D-14, D-1], 6.7 km × 6.7 km @ 224 × 224 px via GEE `getThumbURL`. 200/200 chips fetched (100% availability).
- **Scoring:** local LLaVA-7b via Ollama, `format=json`, `temperature=0.4`, `seed=42`.
- **Statistics:** Mann-Whitney U (one-sided ignited > control), Spearman ρ(score, class), mean delta.

(Original Gemini 2.5 Flash run hit free-tier daily quota at 16/100 ignited; pivoted to local Ollama with interleaved sampling + resume-from-cache. See execution log in plan file.)

## Result

| Class   | n  | mean  | median | std  |
|---------|---:|------:|-------:|-----:|
| Ignited | 100 | **5.39** | 6.0   | 3.00 |
| Control | 100 | **5.68** | 6.0   | 2.96 |

Control mean is **slightly HIGHER** than ignited — opposite of the hypothesized direction.

| Exit criterion       | Threshold | Observed | Result |
|----------------------|----------:|---------:|--------|
| Mean delta (ig − ct) | ≥ +2.0    | **−0.29** | **FAIL** |
| Mann-Whitney U p-value (ig > ct) | < 0.01 | **0.7375** | **FAIL** |
| Spearman ρ(score, class)         | ≥ 0.10 | **−0.045** | **FAIL** |

**ALL THREE criteria FAIL.** No statistical signal whatsoever.

## Score histograms — almost identical between classes

```
        0    2    3    4    6    7    8    9    | total
ignited 8   20    9    1   20    4   22   16    | 100
control 8   17    7    0   21    7   22   18    | 100
```

LLaVA produces a bimodal distribution (~30% at 0-3, ~60% at 6-9, gap at 4-5). But the ratio is **functionally identical** between ignited and control. The score is image-agnostic.

## Evidence strings — LLaVA generates VERBATIM-identical reasoning for both classes

Top-scored ignited (score=9, n=5):
> "The image shows a large area of cleared land with geometric bare patches and signs of human intervention beyond natural dry-season phenology"

Top-scored control (score=9):
> "The image shows a large area of cleared land with geometric bare patches and signs of human intervention beyond natural dry-season phenology"

**The evidence text is identical, character for character, between ignited and control cells.** LLaVA-7b has memorized 5-6 templated responses for this prompt format and emits them based on a coarse internal classifier of the chip into "lots-of-bare-soil" vs "lots-of-vegetation" — but that coarse classifier is uncorrelated with whether the cell will ignite in the next 7 days.

Low-scored ignited cells (LLaVA "disagrees" with the ignition):
> "No evidence of anthropogenic ground-clearing activity consistent with imminent forest fire in this Sentinel-2 satellite image." (score=0, repeated across many low-scored cells)

This is the same templated low-score response.

## Why this fails (mechanistic reading)

1. **Resolution gap.** A single farmer's mahua-grove clearing is ~5-50 m². At Sentinel-2's 10 m native resolution downsampled to 30 m/pixel in our 224×224 chip, that's <1 pixel of disturbance per clearing. LLaVA can see the FOREST but not individual clearings.

2. **VLM template anchoring.** LLaVA-7b is trained on web image-text pairs. Its "satellite imagery + score this property 0-10" response distribution is shaped by training-data priors, NOT by careful per-image grounding. At temperature 0.4 it samples within a handful of templated responses, applying them by gist of the chip (forested vs cleared) rather than by the specific micro-pattern we asked about.

3. **Pre-fire vs. post-fire asymmetry.** The chips are from [D-14, D-1] — BEFORE ignition. Whatever ground-clearing activity occurred would be subtle, recent, and small. The dramatic visual change (burn scar, ash) only appears AFTER. LLaVA might detect post-fire scars but cannot distinguish pre-fire precursor activity from baseline rural land use.

## Verdict — PARK the VLM hypothesis at this tier

The hypothesis "open 7B-class VLMs can zero-shot detect MP fire precursors at 30 m Sentinel-2" is **falsified.** Effect size is not just below the exit criterion — it's the wrong sign.

## What it would take to revisit

1. **Finer resolution (10m native, no downsample).** Send LLaVA the 670 × 670 px native chip instead of 224 × 224. ~2x compute per call; tractable on Ollama. But unclear that LLaVA's vision encoder benefits — its CLIP-style projector likely re-downsamples internally.

2. **Frontier-class VLM (Gemini Pro, GPT-4o, Claude Vision).** These have richer visual reasoning and might pick up signals LLaVA misses. Cost: $50-200 for a 200-cell pilot. Not justified without independent evidence (e.g., paper showing 4o discriminates pre-fire chips on similar tasks).

3. **CLIP embeddings + trained classifier.** Skip text scores entirely. Compute CLIP-ViT-L/14 embeddings on each chip locally (~5 min for 200 chips), train a logistic regression on the 200-pair labels. CLIP encodes generic visual features — if there's ANY discriminating signal in the chips, this would find it. Falsifiable in 1-2 hours of work.

4. **Domain-fine-tuned VLM.** Fine-tune LLaVA on a labeled dataset of "ground-clearing visible / not visible" pre-fire chips. Requires 500-1000 manually-labeled chips. ~1 week of work. Out of scope for a pilot.

**Recommended next step: NONE on the VLM path.** The marginal expected uplift over v17's 47.41% R@5% is too uncertain relative to the work. Better to focus on data-infusion paths the new-outbreak research already identified (NDMA/MPFD scrapers, AgMarkNet NTFP prices, calendar features).

## Files

- `scripts/pilot_vlm_precursor.py` — pilot runner (Ollama backend, interleaved sampling, resume-from-cache)
- `data_lake/audits/vlm_pilot_scores.parquet` — 200 rows with `vlm_backend=ollama`
- `data_lake/audits/vlm_pilot_chips/` — 200 cached PNG chips, untouched after this run
- `tmp/vlm_pilot_ollama.log` — full run log

## Reproducibility

```
ollama serve   # daemon
python scripts/pilot_vlm_precursor.py --backend ollama --n-pairs 100 --no-resume
```

Deterministic except for ollama's internal sampling at temperature 0.4 (we set seed=42 but Ollama's seed support is best-effort across builds). Expect mean delta ∈ [−1, +1], p > 0.5 on any re-run.
