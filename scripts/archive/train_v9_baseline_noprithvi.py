"""Train a CLEAN baseline with v9 hyperparams but NO Prithvi features.
This gives the apples-to-apples comparison for Prithvi's true value.

Same features, same hyperparams, same split as v9_prithvi — just without the 128 Prithvi PCA columns.
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
    average_precision_score, f1_score, precision_score, roc_auc_score,
)

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V6E_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v9_baseline_noprithvi"

LEAKAGE_FEATURES = {
    "days_since_last_fire", "fire_last_7d",
    "neighbor_fire_7d", "neighbor_fire_yesterday",
}
NON_FEATURES = {"cell_id", "date", "label", "year"}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v6e_live dataset.parquet (NO Prithvi merge)...")
    df = pd.read_parquet(V6E_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])
    log.info("  %d rows, %d cols", len(df), df.shape[1])

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and df[c].dtype.kind in "biufc"]
    log.info("  Features: %d (no Prithvi, no leakage)", len(feats))

    train_mask = df["date"] < HOLDOUT_START
    val_mask = df["date"] >= HOLDOUT_START
    train = df[train_mask].reset_index(drop=True)
    val = df[val_mask].reset_index(drop=True)
    log.info("  Train: %d rows (label rate %.1f%%)", len(train), 100 * train["label"].mean())
    log.info("  Val:   %d rows (label rate %.1f%%)", len(val), 100 * val["label"].mean())

    dtrain = lgb.Dataset(train[feats].values, label=train["label"].values, feature_name=feats)
    dval = lgb.Dataset(val[feats].values, label=val["label"].values, reference=dtrain)

    params = {
        "objective": "binary",
        "metric": ["auc", "average_precision"],
        "learning_rate": 0.01,
        "num_leaves": 63,
        "max_depth": 6,
        "subsample": 0.7,
        "colsample_bytree": 0.7,
        "verbose": -1,
    }

    log.info("Training LightGBM (same config as v9_prithvi, no Prithvi features)...")
    t0 = time.time()
    model = lgb.train(
        params, dtrain, num_boost_round=2000,
        valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(100)],
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
        "model": "v9_baseline_noprithvi",
        "n_features": int(len(feats)),
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "best_iteration": int(model.best_iteration),
        "roc_auc": roc, "pr_auc": pr,
        "best_f1": best_f1, "best_f1_threshold": best_t,
        "precision_top10pct": p10,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    log.info("\n=== v9_baseline_noprithvi (clean baseline, same config as v9_prithvi) ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f P@10=%.4f", roc, pr, best_f1, p10)
    log.info("\n=== vs v9_prithvi (with Prithvi features) ===")
    log.info("v9_prithvi (with):    ROC=0.8582 PR=0.7840 F1=0.7198 P@10=0.9069")
    log.info("v9_baseline (without): ROC=%.4f PR=%.4f F1=%.4f P@10=%.4f", roc, pr, best_f1, p10)
    log.info("\n=== HONEST VERDICT for Prithvi embeddings ===")
    delta_roc = 0.8582 - roc
    delta_pr = 0.7840 - pr
    if delta_roc >= 0.003:
        log.info("Prithvi HELPS: +%.4f ROC, +%.4f PR — promote v9_prithvi", delta_roc, delta_pr)
    elif delta_roc <= -0.003:
        log.info("Prithvi HURTS: %.4f ROC, %.4f PR — discard", delta_roc, delta_pr)
    else:
        log.info("Prithvi NEUTRAL: %+.4f ROC, %+.4f PR — discard (adds complexity without gain)", delta_roc, delta_pr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
