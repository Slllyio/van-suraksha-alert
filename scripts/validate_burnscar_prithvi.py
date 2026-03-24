"""
Validate Prithvi-EO-V2-300M-BurnScars predictions against RBR ground truth.

Compares the 1,447 pre-existing burn scar prediction masks (binary, 30m)
against our spectral RBR labels embedded in training patches (.npz, trusted local data).

For each fire patch (val+test splits):
  1. Load ground truth label from .npz (RBR > 0 = fire)
  2. Find the closest post-fire burn scar prediction TIF (5-60 days after fire)
  3. Crop the prediction to the patch window
  4. Compute precision, recall, F1, IoU

Usage:
    python scripts/validate_burnscar_prithvi.py
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parent.parent
BURNSCAR_DIR = ROOT / "data_lake" / "burn_scars" / "hls_s30"
MANIFEST = ROOT / "data_lake" / "training_patches_v5" / "manifest.csv"


def find_burnscar_tif(tile: str, fire_date: str, min_gap: int = 5, max_gap: int = 60):
    """Find the closest post-fire burn scar prediction TIF."""
    tile_dir = BURNSCAR_DIR / tile
    if not tile_dir.exists():
        return None

    fd = datetime.strptime(fire_date, "%Y-%m-%d")
    candidates = []

    for tif_path in tile_dir.rglob("*.tif"):
        fname = tif_path.name
        parts = fname.split(".")
        if len(parts) < 4:
            continue
        doy_str = parts[3][:7]  # e.g. 2017080
        try:
            scene_dt = datetime.strptime(doy_str, "%Y%j")
            gap = (scene_dt - fd).days
            if min_gap <= gap <= max_gap:
                candidates.append((gap, tif_path))
        except ValueError:
            continue

    if not candidates:
        return None
    candidates.sort()
    return candidates[0]  # closest post-fire scene


def load_patch_gt(npz_path: str):
    """Load binary ground truth from trusted local .npz patch (RBR > 0 = fire)."""
    # These are our own training patches built by build_training_dataset.py
    data = np.load(npz_path, allow_pickle=True)
    meta = json.loads(str(data["meta"]))
    raw_label = data["label"].astype(np.float32)

    # Binary: fire where RBR > 0, ignore NaN
    gt = np.zeros(raw_label.shape, dtype=np.int32)
    gt[raw_label > 0.0] = 1
    gt[np.isnan(raw_label)] = -1  # ignore

    window = meta["window"]  # [row, col, height, width]
    return gt, window, meta


def crop_prediction(tif_path: str, window: list):
    """Crop burn scar prediction TIF to patch window [row, col, h, w]."""
    row, col, h, w = window
    with rasterio.open(tif_path) as src:
        raster_h, raster_w = src.height, src.width
        if row + h > raster_h or col + w > raster_w:
            return None
        rio_window = rasterio.windows.Window(col, row, w, h)
        pred = src.read(1, window=rio_window)
    return pred.astype(np.int32)


def compute_metrics(gt: np.ndarray, pred: np.ndarray):
    """Compute binary classification metrics, ignoring pixels where gt == -1."""
    valid = gt >= 0
    if not valid.any():
        return None

    g = gt[valid]
    p = pred[valid]

    tp = ((g == 1) & (p == 1)).sum()
    fp = ((g == 0) & (p == 1)).sum()
    fn = ((g == 1) & (p == 0)).sum()
    tn = ((g == 0) & (p == 0)).sum()

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)
    iou = tp / max(tp + fp + fn, 1)
    accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)

    return {
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "iou": float(iou),
        "accuracy": float(accuracy),
        "fire_pixels_gt": int((g == 1).sum()),
        "fire_pixels_pred": int((p == 1).sum()),
        "total_valid": int(valid.sum()),
    }


def main():
    manifest = pd.read_csv(MANIFEST)

    # Validate on val + test splits only (not train)
    eval_df = manifest[
        (manifest["split"].isin(["val", "test"]))
        & (manifest["is_fire"] == 1)
        & (manifest["has_spectral"] == 1)
    ].copy()

    print(f"Evaluating {len(eval_df)} fire patches (val+test, spectral-only)")
    print(f"Burn scar TIF directory: {BURNSCAR_DIR}")
    print(f"{'='*70}")

    results = []
    no_match = 0
    crop_fail = 0

    for _, row in eval_df.iterrows():
        npz_path = ROOT / row["path"]
        gt, window, meta = load_patch_gt(str(npz_path))
        fire_date = meta["fire_date"][:10]
        tile = meta["tile"]

        match = find_burnscar_tif(tile, fire_date)
        if match is None:
            no_match += 1
            continue

        gap, tif_path = match
        pred = crop_prediction(str(tif_path), window)
        if pred is None:
            crop_fail += 1
            continue

        if pred.shape != gt.shape:
            crop_fail += 1
            continue

        metrics = compute_metrics(gt, pred)
        if metrics is None:
            continue

        metrics["patch_id"] = row["patch_id"]
        metrics["tile"] = tile
        metrics["fire_date"] = fire_date
        metrics["gap_days"] = gap
        metrics["tier"] = row["tier"]
        metrics["rbr_max"] = row["rbr_max"]
        results.append(metrics)

    print(f"\nMatched: {len(results)} | No burn scar TIF: {no_match} | Crop failed: {crop_fail}")
    print(f"{'='*70}")

    if not results:
        print("No results to analyze!")
        return

    df = pd.DataFrame(results)

    # Overall metrics (pixel-level aggregation)
    total_tp = df["tp"].sum()
    total_fp = df["fp"].sum()
    total_fn = df["fn"].sum()
    total_tn = df["tn"].sum()

    overall_p = total_tp / max(total_tp + total_fp, 1)
    overall_r = total_tp / max(total_tp + total_fn, 1)
    overall_f1 = 2 * overall_p * overall_r / max(overall_p + overall_r, 1e-8)
    overall_iou = total_tp / max(total_tp + total_fp + total_fn, 1)
    overall_acc = (total_tp + total_tn) / max(total_tp + total_tn + total_fp + total_fn, 1)

    print(f"\n{'='*70}")
    print(f"OVERALL RESULTS (pixel-level, {len(results)} patches)")
    print(f"{'='*70}")
    print(f"  Precision : {overall_p:.4f}")
    print(f"  Recall    : {overall_r:.4f}")
    print(f"  F1        : {overall_f1:.4f}")
    print(f"  IoU       : {overall_iou:.4f}")
    print(f"  Accuracy  : {overall_acc:.4f}")
    print(f"  TP={total_tp:,}  FP={total_fp:,}  FN={total_fn:,}  TN={total_tn:,}")

    # Per-tier breakdown
    print(f"\n{'='*70}")
    print(f"PER-TIER BREAKDOWN")
    print(f"{'='*70}")
    for tier in ["GOLD", "SILVER", "BRONZE"]:
        tdf = df[df["tier"] == tier]
        if tdf.empty:
            continue
        tp = tdf["tp"].sum()
        fp = tdf["fp"].sum()
        fn = tdf["fn"].sum()
        p = tp / max(tp + fp, 1)
        r = tp / max(tp + fn, 1)
        f1 = 2 * p * r / max(p + r, 1e-8)
        print(f"  {tier:10s}: P={p:.3f}  R={r:.3f}  F1={f1:.3f}  (n={len(tdf)} patches)")

    # Per-patch stats
    print(f"\n{'='*70}")
    print(f"PER-PATCH F1 DISTRIBUTION")
    print(f"{'='*70}")
    print(f"  Mean F1   : {df['f1'].mean():.4f}")
    print(f"  Median F1 : {df['f1'].median():.4f}")
    print(f"  Std F1    : {df['f1'].std():.4f}")
    print(f"  Min F1    : {df['f1'].min():.4f}")
    print(f"  Max F1    : {df['f1'].max():.4f}")
    print(f"  F1 > 0.5  : {(df['f1'] > 0.5).sum()} / {len(df)} ({(df['f1'] > 0.5).mean()*100:.1f}%)")
    print(f"  F1 > 0.3  : {(df['f1'] > 0.3).sum()} / {len(df)} ({(df['f1'] > 0.3).mean()*100:.1f}%)")
    print(f"  F1 == 0   : {(df['f1'] == 0).sum()} / {len(df)} ({(df['f1'] == 0).mean()*100:.1f}%)")

    # Gap analysis
    print(f"\n{'='*70}")
    print(f"TEMPORAL GAP ANALYSIS (scene date vs fire date)")
    print(f"{'='*70}")
    for gap_range, label in [((5, 15), "5-15d"), ((15, 30), "15-30d"), ((30, 60), "30-60d")]:
        gdf = df[(df["gap_days"] >= gap_range[0]) & (df["gap_days"] < gap_range[1])]
        if gdf.empty:
            continue
        print(f"  {label:8s}: mean_F1={gdf['f1'].mean():.3f}  n={len(gdf)}")

    # Severity analysis (does model detect high-severity fires better?)
    print(f"\n{'='*70}")
    print(f"SEVERITY ANALYSIS (RBR max)")
    print(f"{'='*70}")
    for rbr_range, label in [((0, 0.15), "Low RBR<0.15"), ((0.15, 0.4), "Med 0.15-0.4"), ((0.4, 1.0), "High RBR>0.4")]:
        rdf = df[(df["rbr_max"] >= rbr_range[0]) & (df["rbr_max"] < rbr_range[1])]
        if rdf.empty:
            continue
        print(f"  {label:16s}: mean_F1={rdf['f1'].mean():.3f}  mean_recall={rdf['recall'].mean():.3f}  n={len(rdf)}")

    # Save results
    out_path = ROOT / "outputs" / "burnscar_validation.csv"
    df.to_csv(out_path, index=False)
    print(f"\nDetailed results saved to: {out_path}")


if __name__ == "__main__":
    main()
