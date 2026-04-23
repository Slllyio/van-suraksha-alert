"""Plan A.3 — Train LightGBM v8_ignition_dbscan on DBSCAN ignition labels.

Same 92 features as v6e_live MINUS spread-leakage features. Labels are TRUE
ignitions only (no spread/continuation contamination). Compare honestly to v6e_live
and v7_ignition on the same temporal hold-out (2025-02-01 onwards).

Class imbalance: 0.63% positive rate (29K ignitions / 4.65M rows).
Use `is_unbalance=True` for LightGBM, optimize for PR-AUC and recall@top-5%.

Output: outputs/predictive_fire_risk/predictive_v8_ignition_dbscan/
  - model.txt
  - results.json
  - feature_importance.csv
  - eval_vs_v6e_v7.json (head-to-head)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score, recall_score, roc_auc_score,
)

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan" / "dataset.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"

# Spread-leakage features — drop, since they tell the model "fire is already here"
LEAKAGE_FEATURES = {
    "days_since_last_fire", "fire_last_7d",
    "neighbor_fire_7d", "neighbor_fire_yesterday",
}

# Non-features
NON_FEATURES = {
    "cell_id", "date", "label", "year",
    "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp",
}

HOLDOUT_START = pd.Timestamp("2025-02-01")


def main() -> int:
    log.info("Loading dataset...")
    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])
    log.info("  %d rows, %d cols", len(df), df.shape[1])

    # Pick numeric features (exclude string-typed columns and metadata)
    feats = [
        c for c in df.columns
        if c not in NON_FEATURES
        and c not in LEAKAGE_FEATURES
        and df[c].dtype.kind in "biufc"  # numeric only
    ]
    log.info("  %d features (4 leakage + %d metadata excluded)",
             len(feats), len(NON_FEATURES))

    # Temporal split
    train_mask = df["date"] < HOLDOUT_START
    val_mask = df["date"] >= HOLDOUT_START
    train = df[train_mask].reset_index(drop=True)
    val = df[val_mask].reset_index(drop=True)
    log.info("  Train: %d rows, %d positives (%.3f%%)",
             len(train), int(train["label_dbscan_ignition"].sum()),
             100 * train["label_dbscan_ignition"].mean())
    log.info("  Val:   %d rows, %d positives (%.3f%%)",
             len(val), int(val["label_dbscan_ignition"].sum()),
             100 * val["label_dbscan_ignition"].mean())

    # LightGBM training
    log.info("Building LightGBM datasets...")
    dtrain = lgb.Dataset(
        train[feats].values, label=train["label_dbscan_ignition"].values,
        feature_name=feats,
    )
    dval = lgb.Dataset(
        val[feats].values, label=val["label_dbscan_ignition"].values,
        reference=dtrain,
    )

    params = {
        "objective": "binary",
        "metric": ["average_precision", "auc"],
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_data_in_leaf": 200,  # smaller than v7's 500 since positive rate is 8x lower
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 5,
        "is_unbalance": True,  # handle 0.63% positive rate
        "verbose": -1,
    }

    log.info("Training LightGBM (early stop on val PR-AUC, max 2000 rounds)...")
    t0 = time.time()
    model = lgb.train(
        params,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(50)],
    )
    log.info("Training done in %.0fs, best_iter=%d", time.time() - t0, model.best_iteration)

    # Save model
    model.save_model(str(OUT_DIR / "model.txt"))
    log.info("Saved model.txt")

    # Score validation
    val_p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    val_y = val["label_dbscan_ignition"].values

    roc = float(roc_auc_score(val_y, val_p))
    pr = float(average_precision_score(val_y, val_p))

    # Best F1 sweep
    best_f1, best_t = 0.0, 0.5
    for t in np.arange(0.01, 0.99, 0.01):
        pred = (val_p >= t).astype(int)
        f1 = f1_score(val_y, pred, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = float(f1), float(t)

    # Precision/recall at top 5% and top 10%
    p95 = float(np.percentile(val_p, 95))  # top 5%
    p90 = float(np.percentile(val_p, 90))  # top 10%
    pred_top5 = (val_p >= p95).astype(int)
    pred_top10 = (val_p >= p90).astype(int)
    prec_top5 = float(precision_score(val_y, pred_top5, zero_division=0))
    prec_top10 = float(precision_score(val_y, pred_top10, zero_division=0))
    recall_top5 = float(recall_score(val_y, pred_top5, zero_division=0))
    recall_top10 = float(recall_score(val_y, pred_top10, zero_division=0))

    results = {
        "model": "v8_ignition_dbscan",
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "n_features": int(len(feats)),
        "best_iteration": int(model.best_iteration),
        "train_pos_rate": float(train["label_dbscan_ignition"].mean()),
        "val_pos_rate": float(val["label_dbscan_ignition"].mean()),
        "roc_auc": roc,
        "pr_auc": pr,
        "best_f1": best_f1,
        "best_f1_threshold": best_t,
        "precision_top5pct": prec_top5,
        "recall_top5pct": recall_top5,
        "precision_top10pct": prec_top10,
        "recall_top10pct": recall_top10,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))
    log.info("Saved results.json")

    # Feature importance
    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
        "split": model.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False)
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    log.info("Saved feature_importance.csv")
    log.info("Top 10 features:\n%s", fi.head(10).to_string(index=False))

    log.info("\n=== v8_ignition_dbscan FINAL (honest temporal hold-out) ===")
    log.info("  ROC-AUC:       %.4f", roc)
    log.info("  PR-AUC:        %.4f", pr)
    log.info("  Best F1:       %.4f (t=%.2f)", best_f1, best_t)
    log.info("  Precision@top-5%%: %.4f", prec_top5)
    log.info("  Recall@top-5%%:    %.4f", recall_top5)
    log.info("  Precision@top-10%%: %.4f", prec_top10)
    log.info("  Recall@top-10%%:    %.4f", recall_top10)

    log.info("\n=== vs v6e_live (SPREAD task) ===")
    log.info("  v6e_live ROC=0.9150 PR=0.8855 F1=0.7888 — but on SPREAD labels (different task)")
    log.info("  v8_ignition ROC=%.4f PR=%.4f F1=%.4f — on TRUE ignition labels (operational task)",
             roc, pr, best_f1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
