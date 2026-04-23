"""Plan B.5 — Train v9_prithvi LightGBM with Prithvi PCA embeddings as additive features.

Loads v6e_live dataset.parquet, merges Prithvi PCA-reduced embeddings on cell_id,
trains LightGBM on the same SPREAD label as v6e_live for direct comparison.

Output: outputs/predictive_fire_risk/predictive_v9_prithvi/
  - model.lgbm
  - results.json
  - feature_importance.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score, roc_auc_score,
)

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V6E_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v9_prithvi"

# Spread leakage features kept here since v6e was trained without them
LEAKAGE_FEATURES = {
    "days_since_last_fire", "fire_last_7d",
    "neighbor_fire_7d", "neighbor_fire_yesterday",
}
NON_FEATURES = {"cell_id", "date", "label", "year"}

HOLDOUT_START = pd.Timestamp("2025-02-01")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embeddings", default=str(ROOT / "data_lake" / "v6e_chips" / "embeddings_prithvi_pca128.parquet"))
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v6e_live dataset.parquet...")
    df = pd.read_parquet(V6E_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])
    log.info("  %d rows, %d cols", len(df), df.shape[1])

    log.info("Loading Prithvi PCA embeddings: %s", args.embeddings)
    emb = pd.read_parquet(args.embeddings)
    pca_cols = [c for c in emb.columns if c.startswith("prithvi_pca_")]
    log.info("  %d cells with embeddings, %d PCA dims", len(emb), len(pca_cols))

    log.info("Merging embeddings on cell_id (NaN for cells without chips)...")
    df = df.merge(emb, on="cell_id", how="left")
    n_with_emb = int(df[pca_cols[0]].notna().sum()) if pca_cols else 0
    log.info("  After merge: %d / %d rows have embeddings (%.1f%%)",
             n_with_emb, len(df), 100 * n_with_emb / len(df))

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and df[c].dtype.kind in "biufc"]
    log.info("  Features: %d total (%d original + %d Prithvi PCA)",
             len(feats), len(feats) - len(pca_cols), len(pca_cols))

    train_mask = df["date"] < HOLDOUT_START
    val_mask = df["date"] >= HOLDOUT_START
    train = df[train_mask].reset_index(drop=True)
    val = df[val_mask].reset_index(drop=True)
    log.info("  Train: %d rows (label rate %.1f%%)", len(train), 100 * train["label"].mean())
    log.info("  Val:   %d rows (label rate %.1f%%)", len(val), 100 * val["label"].mean())

    log.info("Building LightGBM datasets...")
    dtrain = lgb.Dataset(train[feats].values, label=train["label"].values, feature_name=feats)
    dval = lgb.Dataset(val[feats].values, label=val["label"].values, reference=dtrain)

    # Matched v6e_live hyperparams (from scripts/train_predictive_fire_risk.py):
    # max_depth=6, num_leaves=63, learning_rate=0.01, subsample=0.7, colsample_bytree=0.7
    params = {
        "objective": "binary",
        "metric": ["auc", "average_precision"],
        "learning_rate": 0.01,           # match v6e (was 0.05)
        "num_leaves": 63,                # match v6e
        "max_depth": 6,                  # match v6e
        "subsample": 0.7,                # match v6e
        "colsample_bytree": 0.7,         # match v6e
        "verbose": -1,
    }

    log.info("Training LightGBM (early stop on val AUC)...")
    t0 = time.time()
    model = lgb.train(
        params, dtrain, num_boost_round=2000,
        valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(50)],
    )
    log.info("Training done in %.0fs, best_iter=%d", time.time() - t0, model.best_iteration)

    model.save_model(str(OUT_DIR / "model.lgbm"))

    val_p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    val_y = val["label"].values

    roc = float(roc_auc_score(val_y, val_p))
    pr = float(average_precision_score(val_y, val_p))

    best_f1, best_t = 0.0, 0.5
    for t in np.arange(0.05, 0.95, 0.025):
        f1 = f1_score(val_y, (val_p >= t).astype(int))
        if f1 > best_f1:
            best_f1, best_t = float(f1), float(t)

    p90 = float(np.percentile(val_p, 90))
    pred10 = (val_p >= p90).astype(int)
    p10 = float(precision_score(val_y, pred10, zero_division=0))

    results = {
        "model": "v9_prithvi",
        "n_features": int(len(feats)),
        "n_prithvi_features": int(len(pca_cols)),
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "best_iteration": int(model.best_iteration),
        "roc_auc": roc, "pr_auc": pr,
        "best_f1": best_f1, "best_f1_threshold": best_t,
        "precision_top10pct": p10,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
        "split": model.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False)
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    log.info("Top 15 features:\n%s", fi.head(15).to_string(index=False))

    # Count Prithvi features in top 50
    top50 = fi.head(50)["feature"].tolist()
    n_pca_in_top50 = sum(1 for f in top50 if f.startswith("prithvi_pca_"))
    log.info("\nPrithvi PCA features in top 50: %d / %d", n_pca_in_top50, len(pca_cols))

    log.info("\n=== v9_prithvi FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f P@10=%.4f", roc, pr, best_f1, p10)
    log.info("\n=== vs v6e_live ===")
    log.info("v6e: ROC=0.9150 PR=0.8855 F1=0.7888 P@10=0.9927")
    log.info("v9 : ROC=%.4f PR=%.4f F1=%.4f P@10=%.4f", roc, pr, best_f1, p10)
    log.info("delta: ROC=%+.4f PR=%+.4f F1=%+.4f P@10=%+.4f",
             roc - 0.9150, pr - 0.8855, best_f1 - 0.7888, p10 - 0.9927)
    if roc - 0.9150 >= 0.005 and pr - 0.8855 >= 0.005:
        log.info("VERDICT: PROMOTE v9_prithvi")
    elif roc - 0.9150 >= 0:
        log.info("VERDICT: NEUTRAL — Prithvi adds marginal value, keep both")
    else:
        log.info("VERDICT: FAIL — Prithvi embeddings dont help v6e_live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
