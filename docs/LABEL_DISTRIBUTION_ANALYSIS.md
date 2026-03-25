# VanAgni Training Patches Label Distribution Analysis

**Analysis Date**: 2026-03-15
**Dataset**: `data_lake/training_patches_v3/` (1,040 patches across train/val/test)
**Total Pixels Analyzed**: 52,183,040

## Overview

The training patches contain continuous Relative Burn Ratio (RBR) labels in the range [−0.23, 0.58]. These have been mapped to a 5-class severity schema for this analysis:

| Class | Name | RBR Range | Global Count | Global % | Train % | Val % | Test % |
|-------|------|-----------|--------------|----------|---------|--------|--------|
| 0 | **no_burn** | < 0.05 | 36,012,059 | 69.01% | 63.03% | 86.81% | 80.49% |
| 1 | **very_low** | [0.05, 0.15) | 15,735,367 | 30.15% | 36.17% | 12.98% | 18.42% |
| 2 | **low** | [0.15, 0.30) | 371,767 | 0.71% | 0.71% | 0.21% | 0.86% |
| 3 | **moderate** | [0.30, 0.50) | 63,483 | 0.12% | 0.09% | 0.01% | 0.23% |
| 4 | **high** | ≥ 0.50 | 364 | **0.0007%** | 0.0009% | 0.00% | 0.0003% |

## Key Findings

### 1. **Extreme Class Imbalance**
- **Imbalance ratio (max/min)**: 98,934.2x (class 0 vs class 4)
- Class 0 (no_burn) dominates with 69% of all pixels
- Classes 3 and 4 are severely underrepresented (0.13% combined)

### 2. **Split Characteristics**

#### Train Split (708 patches, 35.5M pixels)
- Most balanced distribution (63% class 0, 36% class 1)
- Contains most class 2+ samples (250K + 32K + 324)
- Suitable for learning burn severity gradients

#### Val Split (67 patches, 3.4M pixels)
- Heavily skewed toward no_burn (87%)
- Very few class 2+ samples (7K + 334)
- Risk of misleading validation metrics for rare classes

#### Test Split (265 patches, 13.3M pixels)
- Intermediate imbalance (80% class 0)
- Better representation than val for severity classes
- 114K class 2 pixels, 30K class 3 pixels

### 3. **Patch-Level Statistics**
- Each patch is 224×224 = 50,176 pixels
- Fire patches show 15–43% burn area (any RBR > 0)
- Background patches are ~99.8% no_burn

## Implications for Model Training

### Critical Issues
1. **Binary/Multiclass Tradeoff**:
   - The 99,900:1 ratio suggests the network will prioritize no_burn
   - Cross-entropy will suffer from vanishing gradients for rare classes
   - **Recommendation**: Use class weights or focal loss (α > 2, γ > 1)

2. **Validation Unreliable for Severity**:
   - Val set has only 7,336 pixels (< 0.2%) in classes 2+
   - Cannot reliably measure precision/recall for moderate/high severity
   - **Recommendation**: Use train-split stratified k-fold or weighted metrics

3. **No Class 4 Samples in Val/Test**:
   - Impossible to evaluate highest severity class generalization
   - **Recommendation**: Manually reserve 10–20 high-RBR patches for test evaluation

### Suggested Mitigations
1. **Loss Function**: Use Focal Loss with γ=2, α=[0.01, 0.15, 0.3, 0.3, 0.24]
2. **Sampling Strategy**: Oversample classes 2–4 during training (5–10x)
3. **Metrics**: Use weighted F1, precision@recall for imbalanced evaluation
4. **Threshold Tuning**: Separate thresholds per class (not uniform 0.5)

## Data Quality Notes

- All 1,040 patches processed without corruption
- Labels are continuous RBR, not pre-binned—allows flexible class boundaries
- Negative RBR values (min = −0.23) suggest preprocessing artifacts; no impact on 5-class schema
- Manifest.csv correctly tracks tier (GOLD/NEGATIVE) and fire/background status

## Reproduction
```bash
python analyze_label_distribution.py
```

Script generates:
- Global class distribution (counts + percentages)
- Per-split breakdowns
- Imbalance ratio analysis
