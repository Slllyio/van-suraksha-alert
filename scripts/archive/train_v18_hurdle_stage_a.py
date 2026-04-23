"""Pivot A v2 — Track T3 — Stage A retrained on v18 feature set.

Same Stage A pattern as scripts/train_v17_hurdle_stage_a.py but reads from
the v18 dataset (which has v17's 111 features + 9 DW features = 120
non-Hawkes features after dropping the 4 Hawkes columns).

Used by scripts/evaluate_v18_combined.py to compute T3's blend(v18, Stage A_v18).
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
DATASET = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_dw" / "dataset.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_hurdle_a"

LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}
LEAKY_V17 = {"best_tier", "label_tier", "cluster_count",
             "is_bronze_unlabeled", "is_tier_gold", "is_tier_silver", "is_tier_bronze"}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not DATASET.exists():
        log.error("v18 dataset missing: %s", DATASET); return 1

    log.info("Loading v18 dataset...")
    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and c not in LEAKY_V17
             and c not in ("label_v17", "weight_v17", "month")
             and not c.startswith("hawkes_")
             and df[c].dtype.kind in "biufc"]
    n_dw = sum(1 for f in feats if f.startswith("dw_"))
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    log.info("Stage A_v18 features: %d total (%d DW, %d Hawkes [must be 0])",
             len(feats), n_dw, n_hawkes)
    assert n_hawkes == 0, "Hawkes leaked into Stage A_v18"

    train = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("Train: %d (%d pos), Val: %d (%d pos)",
             len(train), int(train["label_dbscan_ignition"].sum()),
             len(val), int(val["label_dbscan_ignition"].sum()))

    dtrain = lgb.Dataset(train[feats].values,
                         label=train["label_dbscan_ignition"].values,
                         feature_name=feats)
    dval = lgb.Dataset(val[feats].values,
                       label=val["label_dbscan_ignition"].values,
                       reference=dtrain)

    params = {
        "objective": "binary",
        "metric": ["average_precision", "auc"],
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 5,
        "is_unbalance": True,
        "verbose": -1,
    }

    log.info("Training Stage A_v18...")
    t0 = time.time()
    model = lgb.train(params, dtrain, num_boost_round=3000,
                      valid_sets=[dtrain, dval], valid_names=["train", "val"],
                      callbacks=[lgb.early_stopping(100), lgb.log_evaluation(200)])
    log.info("Training done in %.0fs, best_iter=%d", time.time() - t0, model.best_iteration)
    model.save_model(str(OUT_DIR / "model.txt"))

    val_p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    val_y = val["label_dbscan_ignition"].values
    roc = float(roc_auc_score(val_y, val_p))
    pr = float(average_precision_score(val_y, val_p))
    p95 = float(np.percentile(val_p, 95))
    pred5 = (val_p >= p95).astype(int)
    rec5 = float(recall_score(val_y, pred5, zero_division=0))

    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
        "split": model.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False)
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    dw_in_top30 = int(fi.head(30)["feature"].str.startswith("dw_").sum())
    log.info("Stage A_v18: ROC=%.4f PR=%.4f R@5%%=%.4f", roc, pr, rec5)
    log.info("DW features in top-30: %d", dw_in_top30)
    log.info("Top-15 features:")
    for _, r in fi.head(15).iterrows():
        log.info("  %-40s gain=%12.0f", r["feature"], r["gain"])

    (OUT_DIR / "results.json").write_text(json.dumps({
        "model": "v18_hurdle_stage_a", "n_features": len(feats), "n_dw": n_dw,
        "best_iteration": int(model.best_iteration),
        "roc_auc": roc, "pr_auc": pr, "recall_top5pct": rec5,
        "dw_features_in_top30": dw_in_top30,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
