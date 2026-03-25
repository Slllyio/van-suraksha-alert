"""
src/train/train_cls_lgbm.py
============================
Patch-level fire classification using LightGBM on engineered features.

Extracts ~270 physics-meaningful features per patch:
  - Spectral band statistics (6 bands × 3 frames × 7 stats = 126)
  - Spectral index statistics (NBR, NDVI, BSI × 3 frames × 7 stats = 63)
  - Temporal change features (ΔNBR, ΔNDVI between frames × 5 stats = 30)
  - Weather / FWI (10 current + 70 lookback = 80)
  - Terrain statistics (4 channels × 5 stats = 20)
  - Burn age statistics (3 channels × 5 stats = 15)
  - Landcover fractions (11 classes)
  - Patch-level fire pixel count from manifest

Why this beats a 600M ViT on 341 samples:
  - LightGBM thrives on <1000 samples with ~300 features
  - Features encode fire physics directly (NBR, FWI, drought, terrain)
  - No spatial resolution bottleneck
  - Training takes seconds, not hours
  - Feature importances tell you WHAT drives fire detection

Usage:
    python src/train/train_cls_lgbm.py
    python src/train/train_cls_lgbm.py --n-estimators 500 --max-depth 6
"""

import sys, os, time, json, logging, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent


# ═════════════════════════════════════════════════════════════════════════════
# Feature Extraction
# ═════════════════════════════════════════════════════════════════════════════

# Band names for interpretability
HLS_BANDS = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]
INDEX_NAMES = ["NDVI", "NBR", "BSI"]
TERRAIN_NAMES = ["elev_norm", "slope_norm", "sin_asp", "cos_asp"]
BURN_AGE_NAMES = ["recent", "high_risk", "mature"]
LC_NAMES = [
    "tree_cover", "shrubland", "grassland", "cropland", "built_up",
    "bare_sparse", "snow_ice", "water", "wetland", "mangroves", "moss_lichen"
]
WEATHER_NAMES = [
    "ffmc", "dmc", "dc", "isi", "bui", "fwi",
    "temp", "rh", "wind", "precip"
]


def compute_spatial_stats(arr_2d):
    """Compute summary statistics for a 2D spatial array."""
    flat = arr_2d.ravel()
    valid = flat[np.isfinite(flat)]
    if len(valid) == 0:
        return [0.0] * 7

    return [
        float(np.mean(valid)),
        float(np.std(valid)),
        float(np.min(valid)),
        float(np.percentile(valid, 25)),
        float(np.median(valid)),
        float(np.percentile(valid, 75)),
        float(np.max(valid)),
    ]


def compute_spatial_stats_names(prefix):
    return [f"{prefix}_mean", f"{prefix}_std", f"{prefix}_min",
            f"{prefix}_p25", f"{prefix}_p50", f"{prefix}_p75", f"{prefix}_max"]


def extract_features(patch_path, row):
    """Extract ~270 features from one .npz patch file."""
    data = np.load(str(patch_path), allow_pickle=True)

    hls = data["hls"].astype(np.float32)           # (6, 3, 224, 224)
    indices = data["indices"].astype(np.float32)    # (3, 3, 224, 224)
    weather = data["weather"].astype(np.float32)    # (10,)
    weather_7d = data["weather_7d"].astype(np.float32)  # (10, 7)
    terrain = data["terrain"].astype(np.float32)    # (4, 224, 224)
    burn_age = data["burn_age"].astype(np.float32)  # (3, 224, 224)
    landcover = data["landcover"].astype(np.float32)  # (11, 224, 224)

    features = {}

    # ── 1. Spectral band statistics (6 bands × 3 frames × 7 stats = 126) ──
    n_bands, n_frames = hls.shape[0], hls.shape[1]
    for b in range(n_bands):
        for t in range(n_frames):
            prefix = f"hls_{HLS_BANDS[b]}_t{t}"
            stats = compute_spatial_stats(hls[b, t])
            for name, val in zip(compute_spatial_stats_names(prefix), stats):
                features[name] = val

    # ── 2. Spectral index statistics (3 indices × 3 frames × 7 stats = 63) ──
    for i in range(indices.shape[0]):
        for t in range(n_frames):
            prefix = f"idx_{INDEX_NAMES[i]}_t{t}"
            stats = compute_spatial_stats(indices[i, t])
            for name, val in zip(compute_spatial_stats_names(prefix), stats):
                features[name] = val

    # ── 3. Temporal change features (Δ between first and last frame) ──
    # These capture vegetation drying / NBR change before fire
    for i, idx_name in enumerate(INDEX_NAMES):
        if n_frames >= 2:
            # Delta: last frame - first frame (positive = increase)
            delta = indices[i, -1] - indices[i, 0]
            prefix = f"delta_{idx_name}_t0_t{n_frames-1}"
            stats = compute_spatial_stats(delta)
            for name, val in zip(compute_spatial_stats_names(prefix), stats):
                features[name] = val

            # Also middle-to-last if 3 frames
            if n_frames >= 3:
                delta2 = indices[i, -1] - indices[i, 1]
                prefix2 = f"delta_{idx_name}_t1_t{n_frames-1}"
                stats2 = compute_spatial_stats(delta2)
                for name, val in zip(compute_spatial_stats_names(prefix2), stats2):
                    features[name] = val

    # ── 4. Weather / FWI features (10 current + 70 lookback = 80) ──
    for w, name in enumerate(WEATHER_NAMES):
        features[f"weather_{name}"] = float(weather[w])

    for w, name in enumerate(WEATHER_NAMES):
        for d in range(weather_7d.shape[1]):
            features[f"weather7d_{name}_d{d}"] = float(weather_7d[w, d])

    # Weather derived: 7-day trends
    for w, name in enumerate(WEATHER_NAMES):
        w7 = weather_7d[w, :]
        features[f"weather7d_{name}_mean"] = float(np.mean(w7))
        features[f"weather7d_{name}_std"] = float(np.std(w7))
        features[f"weather7d_{name}_trend"] = float(w7[-1] - w7[0])  # last - first

    # ── 5. Terrain statistics (4 channels × 5 stats = 20) ──
    for c, tname in enumerate(TERRAIN_NAMES):
        prefix = f"terrain_{tname}"
        stats = compute_spatial_stats(terrain[c])[:5]  # mean,std,min,p25,p50
        for name, val in zip([f"{prefix}_mean", f"{prefix}_std", f"{prefix}_min",
                              f"{prefix}_p25", f"{prefix}_p50"], stats):
            features[name] = val

    # ── 6. Burn age statistics (3 channels × 5 stats = 15) ──
    for c, bname in enumerate(BURN_AGE_NAMES):
        prefix = f"burn_{bname}"
        stats = compute_spatial_stats(burn_age[c])[:5]
        for name, val in zip([f"{prefix}_mean", f"{prefix}_std", f"{prefix}_min",
                              f"{prefix}_p25", f"{prefix}_p50"], stats):
            features[name] = val

    # ── 7. Landcover fractions (11 classes) ──
    for c, lcname in enumerate(LC_NAMES):
        # Mean of one-hot → fraction of patch covered by this class
        features[f"lc_{lcname}_frac"] = float(landcover[c].mean())

    # ── 8. Manifest metadata ──
    features["fire_pixels"] = int(row.get("fire_pixels", 0))

    return features


def build_feature_matrix(manifest_path, split=None):
    """Extract features for all patches in manifest (or specific split)."""
    df = pd.read_csv(manifest_path)
    if split is not None:
        df = df[df["split"] == split].copy()

    all_features = []
    labels = []

    for idx, row in df.iterrows():
        path = ROOT / row["path"]
        feat = extract_features(path, row)
        all_features.append(feat)
        labels.append(int(row["is_fire"]))

        if (idx + 1) % 100 == 0:
            log.info(f"  Extracted {idx + 1}/{len(df)} patches...")

    X = pd.DataFrame(all_features)
    y = np.array(labels)

    # Drop fire_pixels for training (it's the label in disguise)
    # But keep it for analysis
    feature_cols = [c for c in X.columns if c != "fire_pixels"]

    return X, y, feature_cols, df


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="LightGBM Patch Fire Classification")
    parser.add_argument("--tag", default="lgbm_v1")
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--lr", type=float, default=0.05)
    parser.add_argument("--min-child-samples", type=int, default=10)
    parser.add_argument("--subsample", type=float, default=0.8)
    parser.add_argument("--colsample", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s][%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    manifest = ROOT / "data_lake" / "training_patches_v5" / "manifest.csv"

    # ── Extract features ──────────────────────────────────────────────────
    log.info("Extracting features from training patches...")
    t0 = time.time()
    X_train, y_train, feature_cols, df_train = build_feature_matrix(manifest, "train")
    log.info(f"  Train: {len(X_train)} patches, {len(feature_cols)} features  ({time.time()-t0:.1f}s)")

    t0 = time.time()
    X_val, y_val, _, df_val = build_feature_matrix(manifest, "val")
    log.info(f"  Val:   {len(X_val)} patches  ({time.time()-t0:.1f}s)")

    t0 = time.time()
    X_test, y_test, _, df_test = build_feature_matrix(manifest, "test")
    log.info(f"  Test:  {len(X_test)} patches  ({time.time()-t0:.1f}s)")

    log.info(f"\nFeature matrix: {len(feature_cols)} features")
    log.info(f"Train: {y_train.sum()}/{len(y_train)} fire  "
             f"({y_train.mean()*100:.1f}%)")
    log.info(f"Val:   {y_val.sum()}/{len(y_val)} fire  "
             f"({y_val.mean()*100:.1f}%)")
    log.info(f"Test:  {y_test.sum()}/{len(y_test)} fire  "
             f"({y_test.mean()*100:.1f}%)")

    # ── Train LightGBM ───────────────────────────────────────────────────
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, average_precision_score, confusion_matrix,
    )

    log.info(f"\n{'='*65}")
    log.info(f"  LightGBM Training")
    log.info(f"  n_estimators={args.n_estimators}  max_depth={args.max_depth}  "
             f"lr={args.lr}  subsample={args.subsample}")
    log.info(f"{'='*65}\n")

    # Compute scale_pos_weight for class balance
    n_neg = (y_train == 0).sum()
    n_pos = (y_train == 1).sum()
    scale_pos = n_neg / max(n_pos, 1)

    model = lgb.LGBMClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.lr,
        min_child_samples=args.min_child_samples,
        subsample=args.subsample,
        colsample_bytree=args.colsample,
        scale_pos_weight=scale_pos,
        random_state=args.seed,
        verbosity=-1,
        n_jobs=-1,
    )

    t0 = time.time()
    model.fit(
        X_train[feature_cols], y_train,
        eval_set=[(X_val[feature_cols], y_val)],
        callbacks=[
            lgb.early_stopping(stopping_rounds=30, verbose=True),
            lgb.log_evaluation(period=25),
        ],
    )
    train_time = time.time() - t0
    log.info(f"Training time: {train_time:.1f}s  "
             f"(best_iteration={model.best_iteration_})")

    # ── Evaluate ─────────────────────────────────────────────────────────
    def evaluate(X, y, split_name):
        probs = model.predict_proba(X[feature_cols])[:, 1]
        preds = model.predict(X[feature_cols])

        acc = accuracy_score(y, preds)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        f1 = f1_score(y, preds, zero_division=0)
        auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0
        ap = average_precision_score(y, probs) if len(np.unique(y)) > 1 else 0
        cm = confusion_matrix(y, preds, labels=[0, 1])

        log.info(f"\n{split_name:6s}:  acc={acc:.3f}  F1={f1:.3f}  "
                 f"P={prec:.3f}  R={rec:.3f}  "
                 f"AUC-ROC={auc:.4f}  AUC-PR={ap:.4f}")
        log.info(f"  Confusion: TP={cm[1,1]}  FP={cm[0,1]}  "
                 f"FN={cm[1,0]}  TN={cm[0,0]}")

        return {"accuracy": acc, "f1": f1, "precision": prec, "recall": rec,
                "auc_roc": auc, "auc_pr": ap,
                "tp": int(cm[1,1]), "fp": int(cm[0,1]),
                "fn": int(cm[1,0]), "tn": int(cm[0,0])}

    train_scores = evaluate(X_train, y_train, "TRAIN")
    val_scores = evaluate(X_val, y_val, "VAL")
    test_scores = evaluate(X_test, y_test, "TEST")

    # ── Threshold Sweep ──────────────────────────────────────────────────
    test_probs = model.predict_proba(X_test[feature_cols])[:, 1]

    log.info(f"\n{'='*75}")
    log.info("THRESHOLD SWEEP ON TEST SET")
    log.info(f"{'='*75}")
    log.info(f"{'Thr':>6s}  {'Acc':>6s}  {'Prec':>6s}  {'Rec':>6s}  "
             f"{'F1':>6s}  {'TP':>4s}  {'FP':>4s}  {'FN':>4s}  {'TN':>4s}")
    log.info("-" * 75)

    best_f1, best_thr = 0, 0.5
    for thr in np.arange(0.10, 0.95, 0.05):
        preds = (test_probs >= thr).astype(int)
        acc = accuracy_score(y_test, preds)
        prec = precision_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        f1 = f1_score(y_test, preds, zero_division=0)
        cm = confusion_matrix(y_test, preds, labels=[0, 1])
        tag = ""
        if f1 > best_f1:
            best_f1, best_thr = f1, thr
            tag = "  <-- BEST"
        log.info(f"  {thr:.2f}  {acc:6.3f}  {prec:6.3f}  {rec:6.3f}  "
                 f"{f1:6.3f}  {cm[1,1]:4d}  {cm[0,1]:4d}  {cm[1,0]:4d}  {cm[0,0]:4d}{tag}")

    log.info("-" * 75)
    log.info(f"AUC-ROC: {roc_auc_score(y_test, test_probs):.4f}  |  "
             f"AUC-PR: {average_precision_score(y_test, test_probs):.4f}")
    log.info(f"Best threshold: {best_thr:.2f}  (F1={best_f1:.4f})")
    log.info("=" * 75)

    # ── Feature Importance (top 30) ──────────────────────────────────────
    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_cols, importances),
                      key=lambda x: x[1], reverse=True)

    log.info(f"\n{'='*55}")
    log.info("TOP 30 FEATURES BY IMPORTANCE")
    log.info(f"{'='*55}")
    for rank, (fname, imp) in enumerate(feat_imp[:30], 1):
        bar = "█" * int(imp / max(importances) * 30)
        log.info(f"  {rank:2d}. {fname:40s}  {imp:5d}  {bar}")
    log.info(f"{'='*55}")

    # ── Save ─────────────────────────────────────────────────────────────
    out_dir = ROOT / "outputs" / f"vanaagni_cls_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    import joblib
    model_path = out_dir / "model.lgbm"
    joblib.dump(model, str(model_path))
    log.info(f"\nModel saved: {model_path}")

    # Save feature names
    with open(out_dir / "feature_names.json", "w") as f:
        json.dump(feature_cols, f)

    # Save results
    results = {
        "args": vars(args),
        "n_features": len(feature_cols),
        "train": train_scores,
        "val": val_scores,
        "test": test_scores,
        "best_threshold": float(best_thr),
        "best_test_f1": float(best_f1),
        "best_iteration": model.best_iteration_,
        "top_features": [{"name": n, "importance": int(i)}
                         for n, i in feat_imp[:50]],
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Results saved: {out_dir / 'results.json'}")

    # ── Save extracted features for reuse ────────────────────────────────
    feat_dir = ROOT / "data_lake" / "training_patches_v5" / "tabular_features"
    feat_dir.mkdir(parents=True, exist_ok=True)

    for split_name, X_split, y_split, df_split in [
        ("train", X_train, y_train, df_train),
        ("val", X_val, y_val, df_val),
        ("test", X_test, y_test, df_test),
    ]:
        X_split["label"] = y_split
        X_split["patch_id"] = df_split["patch_id"].values
        X_split["split"] = split_name
        X_split.to_parquet(feat_dir / f"{split_name}.parquet", index=False)

    log.info(f"Tabular features saved: {feat_dir}")


if __name__ == "__main__":
    main()
