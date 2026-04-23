"""
scripts/train_lgbm_v5.py
========================
LightGBM v5 — Adds tpi_std3 (terrain roughness, norm_sep=0.98) and fire_density_smooth
(spatial fire clustering) to v4's 19 features for 21 total.

Root cause of v3 collapse: Over-regularization (lr: 0.02->0.01, depth: 5->4, leaves: 31->15,
lambda: 1.0->2.0). v1 had AUC=0.90 with good params. v4 reverts to v1-like capacity while
keeping only features with nonzero importance. v5 extends v4 with two new high-signal features.

Data: pixel-level training data from v1 (705K samples, temporal split).
Features: 21 features — v4's 19 pruned features plus tpi_std3 and fire_density_smooth.
Hyperparams: v1-like with slightly more capacity (depth=6) for weather features.

Usage:
    python scripts/train_lgbm_v5.py
    python scripts/train_lgbm_v5.py --sweep   # run hyperparameter search
"""

import json
import logging
import argparse
import sys
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)


# Features with nonzero importance in v1 (sorted by importance)
# plus tpi_std3 (terrain roughness) and fire_density_smooth (spatial clustering)
V5_FEATURES = [
    # Terrain (top signal — slope dominates)
    "slope_mean3", "slope_std3", "dem_mean5", "slope_mean5",
    "dem_mean3", "dem", "tpi_mean5", "tpi_mean3", "tpi_std3",
    # Infrastructure
    "road_dist_mean5", "road_dist_mean3",
    # Vegetation
    "ndvi_expected",
    # Weather anomalies (current day)
    "anomaly_precip", "anomaly_temp", "anomaly_rh",
    # Weather 7-day trends
    "anomaly7d_wind_trend", "anomaly7d_dmc_mean",
    "anomaly7d_bui_trend", "anomaly7d_temp_trend",
    # Temporal
    "doy",
    # Fire history
    "fire_density_smooth",
]


def load_data(data_path: Path):
    """Load pixel-level training data and split by temporal column."""
    log.info(f"Loading data from {data_path}")
    df = pd.read_parquet(data_path)
    log.info(f"  Total: {len(df)} samples, {df.columns.size} columns")

    # Verify all v5 features exist
    missing = [f for f in V5_FEATURES if f not in df.columns]
    if missing:
        log.error(f"Missing features: {missing}")
        sys.exit(1)

    # Use existing temporal split
    splits = {}
    for split_name in ["train", "val", "test"]:
        mask = df["split"] == split_name
        X = df.loc[mask, V5_FEATURES].copy()
        y = df.loc[mask, "label"].values.astype(int)

        # Clean infinities/nans
        X.replace([np.inf, -np.inf], np.nan, inplace=True)
        X.fillna(0.0, inplace=True)

        splits[split_name] = (X, y)
        n_fire = y.sum()
        log.info(f"  {split_name}: {len(X)} samples "
                 f"({n_fire} fire, {len(X) - n_fire} bg, "
                 f"ratio={n_fire / max(len(X), 1):.3f})")

    return splits


def train_model(X_train, y_train, scale_pos_weight, seed=42, sweep=False):
    """Train LightGBM v5 with v1-like hyperparameters."""
    import lightgbm as lgb

    # v5 params: same as v4 — revert v3 over-regularization, add capacity for weather
    params = {
        "n_estimators": 1000,
        "max_depth": 6,          # v1=5, v3=4 -> try 6 for weather features
        "num_leaves": 31,         # v1=31, v3=15 -> revert
        "learning_rate": 0.02,    # v1=0.02, v3=0.01 -> revert
        "min_child_samples": 30,  # v1=50 -> slightly reduce
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,         # v1=0.1, v3=0.5 -> revert
        "reg_lambda": 1.0,        # v1=1.0, v3=2.0 -> revert
        "scale_pos_weight": scale_pos_weight,
        "random_state": seed,
        "verbosity": -1,
        "n_jobs": -1,
    }

    if sweep:
        log.info("Running hyperparameter sweep...")
        return _run_sweep(X_train, y_train, scale_pos_weight, seed)

    log.info(f"Training LightGBM v5 with {len(V5_FEATURES)} features")
    log.info(f"  Params: depth={params['max_depth']}, leaves={params['num_leaves']}, "
             f"lr={params['learning_rate']}, spw={scale_pos_weight:.2f}")

    model = lgb.LGBMClassifier(**params)
    model.fit(X_train, y_train)

    return model, params


def _run_sweep(X_train, y_train, scale_pos_weight, seed):
    """Randomized hyperparameter search."""
    import lightgbm as lgb
    from sklearn.model_selection import RandomizedSearchCV
    from sklearn.metrics import make_scorer, roc_auc_score

    param_dist = {
        "max_depth": [4, 5, 6, 7, 8],
        "num_leaves": [15, 23, 31, 47, 63],
        "learning_rate": [0.01, 0.02, 0.03, 0.05],
        "min_child_samples": [20, 30, 50, 75],
        "subsample": [0.7, 0.8, 0.9],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9],
        "reg_alpha": [0.0, 0.05, 0.1, 0.3],
        "reg_lambda": [0.5, 1.0, 2.0, 3.0],
    }

    base = lgb.LGBMClassifier(
        n_estimators=1000,
        scale_pos_weight=scale_pos_weight,
        random_state=seed,
        verbosity=-1,
        n_jobs=-1,
    )

    scorer = make_scorer(roc_auc_score, needs_proba=True)
    search = RandomizedSearchCV(
        base, param_dist, n_iter=40,
        scoring=scorer, cv=3,
        random_state=seed, verbose=1, n_jobs=1,
    )
    search.fit(X_train, y_train)

    log.info(f"  Best CV AUC: {search.best_score_:.4f}")
    log.info(f"  Best params: {search.best_params_}")

    best_params = {**search.best_params_,
                   "n_estimators": 1000,
                   "scale_pos_weight": scale_pos_weight,
                   "random_state": seed}

    return search.best_estimator_, best_params


def evaluate(model, X, y, label=""):
    """Evaluate model and return metrics dict."""
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, f1_score,
        precision_score, recall_score, confusion_matrix,
    )

    probs = model.predict_proba(X)[:, 1]
    has_both = len(np.unique(y)) > 1

    auc_roc = roc_auc_score(y, probs) if has_both else 0.0
    auc_pr = average_precision_score(y, probs) if has_both else 0.0

    # Threshold sweep
    best_f1, best_thr = 0.0, 0.5
    sweep_results = []
    for thr in np.arange(0.05, 0.96, 0.05):
        preds = (probs >= thr).astype(int)
        f1 = f1_score(y, preds, zero_division=0)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        cm = confusion_matrix(y, preds, labels=[0, 1])
        tp, fp, fn, tn = int(cm[1, 1]), int(cm[0, 1]), int(cm[1, 0]), int(cm[0, 0])

        sweep_results.append({
            "threshold": round(float(thr), 2),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        })

        if f1 > best_f1:
            best_f1, best_thr = f1, thr

    # Metrics at best threshold
    best_preds = (probs >= best_thr).astype(int)
    cm = confusion_matrix(y, best_preds, labels=[0, 1])

    metrics = {
        "auc_roc": round(auc_roc, 4),
        "auc_pr": round(auc_pr, 4),
        "best_f1": round(best_f1, 4),
        "best_threshold": round(float(best_thr), 2),
        "tp": int(cm[1, 1]), "fp": int(cm[0, 1]),
        "fn": int(cm[1, 0]), "tn": int(cm[0, 0]),
        "n_samples": len(y),
        "n_fire": int(y.sum()),
        "threshold_sweep": sweep_results,
    }

    log.info(f"  {label}: AUC={auc_roc:.4f}  AUC-PR={auc_pr:.4f}  "
             f"F1={best_f1:.4f} (thr={best_thr:.2f})  "
             f"TP={cm[1,1]}  FP={cm[0,1]}  FN={cm[1,0]}  TN={cm[0,0]}")

    return metrics


def save_outputs(model, params, val_metrics, test_metrics, out_dir: Path):
    """Save model, params, feature importance, and results."""
    import joblib

    out_dir.mkdir(parents=True, exist_ok=True)

    # Model
    joblib.dump(model, str(out_dir / "model.pkl"))
    log.info(f"  Model saved: {out_dir / 'model.pkl'}")

    # Params
    serializable_params = {k: (float(v) if isinstance(v, (np.floating,)) else v)
                           for k, v in params.items()}
    with open(out_dir / "params.json", "w") as f:
        json.dump(serializable_params, f, indent=2, default=str)

    # Feature importance
    importances = model.feature_importances_
    feat_imp = sorted(zip(V5_FEATURES, importances),
                      key=lambda x: x[1], reverse=True)

    imp_df = pd.DataFrame(feat_imp, columns=["feature", "importance"])
    imp_df.to_csv(out_dir / "feature_importance.csv", index=False)

    log.info(f"\n  TOP FEATURES:")
    total_imp = max(sum(importances), 1)
    for rank, (fname, imp) in enumerate(feat_imp[:10], 1):
        pct = imp / total_imp * 100
        bar = "#" * int(pct / 2)
        log.info(f"    {rank:2d}. {fname:30s}  {imp:10.1f}  ({pct:5.1f}%)  {bar}")

    # Weather contribution
    weather_feats = [f for f in V5_FEATURES if "anomaly" in f]
    weather_imp = sum(model.feature_importances_[V5_FEATURES.index(f)]
                      for f in weather_feats if f in V5_FEATURES)
    weather_pct = weather_imp / total_imp * 100
    log.info(f"\n  Weather features contribution: {weather_pct:.1f}%")

    # Feature names
    with open(out_dir / "feature_names.json", "w") as f:
        json.dump(V5_FEATURES, f, indent=2)

    # Results
    results = {
        "model_version": "v5",
        "n_features": len(V5_FEATURES),
        "features": V5_FEATURES,
        "params": serializable_params,
        "val": val_metrics,
        "test": test_metrics,
        "weather_importance_pct": round(weather_pct, 2),
        "feature_importance": [{"name": n, "importance": float(i)}
                               for n, i in feat_imp],
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    log.info(f"  Results saved: {out_dir / 'results.json'}")


def main():
    parser = argparse.ArgumentParser(description="Train LightGBM v5")
    parser.add_argument("--sweep", action="store_true", help="Run hyperparameter sweep")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s][%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    log.info("=" * 65)
    log.info("LightGBM v5 — v4 + tpi_std3 + fire_density_smooth (21 features)")
    log.info("=" * 65)

    # Load data
    data_path = ROOT / "outputs" / "pixel_lgbm" / "pixel_lgbm_v1" / "training_data.parquet"
    if not data_path.exists():
        log.error(f"Training data not found: {data_path}")
        sys.exit(1)

    splits = load_data(data_path)
    X_train, y_train = splits["train"]
    X_val, y_val = splits["val"]
    X_test, y_test = splits["test"]

    # Compute class weight
    n_neg = (y_train == 0).sum()
    n_pos = (y_train == 1).sum()
    scale_pos_weight = n_neg / max(n_pos, 1)
    log.info(f"\n  scale_pos_weight = {scale_pos_weight:.2f} "
             f"(neg={n_neg}, pos={n_pos})")

    # Train
    log.info(f"\n{'=' * 65}")
    log.info("TRAINING")
    log.info(f"{'=' * 65}")
    model, params = train_model(X_train, y_train, scale_pos_weight,
                                seed=args.seed, sweep=args.sweep)

    # Evaluate
    log.info(f"\n{'=' * 65}")
    log.info("EVALUATION")
    log.info(f"{'=' * 65}")
    val_metrics = evaluate(model, X_val, y_val, "Val")
    test_metrics = evaluate(model, X_test, y_test, "Test")

    # Compare with baselines
    log.info(f"\n{'=' * 65}")
    log.info("COMPARISON")
    log.info(f"{'=' * 65}")
    log.info(f"  v1 baseline:  AUC=0.9002  F1=0.598 (thr=0.20)")
    log.info(f"  v3 baseline:  AUC=0.61    F1=0.000 (collapsed)")
    log.info(f"  v4 baseline:  AUC=0.9140  F1=0.621 (thr=0.60)")
    log.info(f"  v5 (this):    AUC={test_metrics['auc_roc']:.4f}  "
             f"F1={test_metrics['best_f1']:.3f} (thr={test_metrics['best_threshold']:.2f})")

    delta_auc = test_metrics["auc_roc"] - 0.9140
    log.info(f"  Delta vs v4:  AUC {delta_auc:+.4f}")

    # Save
    out_dir = ROOT / "outputs" / "pixel_lgbm" / "pixel_lgbm_v5"
    save_outputs(model, params, val_metrics, test_metrics, out_dir)

    log.info(f"\n{'=' * 65}")
    log.info("DONE")
    log.info(f"{'=' * 65}")


if __name__ == "__main__":
    main()
