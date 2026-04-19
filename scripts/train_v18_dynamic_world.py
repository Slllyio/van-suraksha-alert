"""Pivot A v2 — Track T2 — v18 trainer (v17 features + 7 DW features).

Same training regime as train_v17_ba_pu.py but pulls from
predictive_v18_dw/dataset.parquet (built by extend_dataset_with_dw.py).

Pass criterion (per plan):
  - low-Hawkes R@5% (Hawkes_n ≤ 1) ≥ 0.07
  - overall R@5% ≥ 0.47 (BA-tiered) — NOT enforced in this script,
    surfaced in the audit/eval downstream
  - At least one DW feature in top-30 by gain
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
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_dw"

LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}
LEAKY_V17 = {"best_tier", "label_tier", "cluster_count",
             "is_bronze_unlabeled", "is_tier_gold", "is_tier_silver", "is_tier_bronze",
             "t0_6hr_bin", "t0_duration_hours", "t0_rectified_ros_m_per_min",
             "t0_confidence", "x0_rectified_lon", "x0_rectified_lat"}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not DATASET.exists():
        log.error("v18 dataset missing: %s. Run extend_dataset_with_dw.py first.", DATASET)
        return 1

    log.info("Loading v18 dataset...")
    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])

    if "label_v17" not in df.columns:
        log.error("label_v17 not present — extend_dataset_with_dw.py must merge tiered labels.")
        return 2

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and c not in LEAKY_V17
             and c not in ("label_v17", "weight_v17", "month")
             and df[c].dtype.kind in "biufc"]

    n_dw = sum(1 for f in feats if f.startswith("dw_"))
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    n_glcm = sum(1 for f in feats if f.startswith("glcm_") or f.startswith("ndvi_"))
    n_hydro = sum(1 for f in feats if f.startswith("hydro_"))
    log.info("v18 features: %d total (%d Hawkes + %d GLCM/NDVI + %d Hydro + %d DW)",
             len(feats), n_hawkes, n_glcm, n_hydro, n_dw)

    train = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("Train: %d rows (%d label_v17 pos), Val: %d rows (%d label_v17 pos, %d DBSCAN-strict pos)",
             len(train), int(train["label_v17"].sum()),
             len(val), int(val["label_v17"].sum()),
             int(val["label_dbscan_ignition"].sum()))

    dtrain = lgb.Dataset(train[feats].values,
                         label=train["label_v17"].values,
                         weight=train["weight_v17"].values,
                         feature_name=feats)
    dval = lgb.Dataset(val[feats].values,
                       label=val["label_v17"].values,
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

    log.info("Training v18_dw...")
    t0 = time.time()
    model = lgb.train(
        params, dtrain, num_boost_round=3000,
        valid_sets=[dtrain, dval], valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(100)],
    )
    log.info("Training done in %.0fs, best_iter=%d", time.time() - t0, model.best_iteration)
    model.save_model(str(OUT_DIR / "model.txt"))

    val_p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    val_y_v17 = val["label_v17"].values
    val_y_strict = val["label_dbscan_ignition"].values
    hawkes_n = val["hawkes_n_recent_10km_7d"].values if "hawkes_n_recent_10km_7d" in val.columns else None

    roc = float(roc_auc_score(val_y_v17, val_p))
    pr = float(average_precision_score(val_y_v17, val_p))
    best_f1, best_t = 0.0, 0.5
    for t in np.arange(0.01, 0.99, 0.01):
        f1 = f1_score(val_y_v17, (val_p >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = float(f1), float(t)

    eval_df = val[["date", "label_v17", "label_dbscan_ignition"]].copy()
    eval_df["pred"] = val_p
    if hawkes_n is not None:
        eval_df["hawkes_n"] = hawkes_n

    # Per-day BA-tiered + DBSCAN-strict R@5%
    perday_v17, perday_strict = [], []
    overall_v17_caught = overall_v17_pos = 0
    overall_strict_caught = overall_strict_pos = 0
    low_strict_caught = low_strict_pos = 0      # Hawkes_n <= 1
    cold_strict_caught = cold_strict_pos = 0    # Hawkes_n == 0
    for d, sub in eval_df.groupby("date"):
        n_top5 = max(1, int(len(sub) * 0.05))
        top = sub.nlargest(n_top5, "pred")
        if sub["label_v17"].sum() > 0:
            perday_v17.append(int(top["label_v17"].sum()) / sub["label_v17"].sum())
        if sub["label_dbscan_ignition"].sum() > 0:
            perday_strict.append(int(top["label_dbscan_ignition"].sum())
                                  / sub["label_dbscan_ignition"].sum())
        overall_v17_caught += int(top["label_v17"].sum()); overall_v17_pos += int(sub["label_v17"].sum())
        overall_strict_caught += int(top["label_dbscan_ignition"].sum())
        overall_strict_pos += int(sub["label_dbscan_ignition"].sum())
        if "hawkes_n" in sub.columns:
            low_strict_caught += int(top[(top["hawkes_n"] <= 1)
                                         & (top["label_dbscan_ignition"] == 1)].shape[0])
            low_strict_pos += int(sub[(sub["hawkes_n"] <= 1)
                                      & (sub["label_dbscan_ignition"] == 1)].shape[0])
            cold_strict_caught += int(top[(top["hawkes_n"] == 0)
                                          & (top["label_dbscan_ignition"] == 1)].shape[0])
            cold_strict_pos += int(sub[(sub["hawkes_n"] == 0)
                                       & (sub["label_dbscan_ignition"] == 1)].shape[0])

    overall_v17_r5 = overall_v17_caught / overall_v17_pos if overall_v17_pos else 0.0
    overall_strict_r5 = overall_strict_caught / overall_strict_pos if overall_strict_pos else 0.0
    low_strict_r5 = low_strict_caught / low_strict_pos if low_strict_pos else 0.0
    cold_strict_r5 = cold_strict_caught / cold_strict_pos if cold_strict_pos else 0.0
    perday_v17_r5 = float(np.mean(perday_v17)) if perday_v17 else 0.0
    perday_strict_r5 = float(np.mean(perday_strict)) if perday_strict else 0.0

    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
        "split": model.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False)
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)

    dw_in_top30 = int(fi.head(30)["feature"].str.startswith("dw_").sum())
    log.info("\nFeature importance — top 15:")
    for _, r in fi.head(15).iterrows():
        log.info("    %-40s gain=%12.0f split=%4d", r["feature"], r["gain"], r["split"])
    log.info("DW features in top-30 by gain: %d", dw_in_top30)

    results = {
        "model": "v18_dw",
        "n_features": int(len(feats)),
        "n_hawkes": n_hawkes, "n_glcm": n_glcm, "n_hydro": n_hydro, "n_dw": n_dw,
        "best_iteration": int(model.best_iteration),
        "roc_auc": roc, "pr_auc": pr,
        "best_f1": best_f1, "best_f1_threshold": best_t,
        "ba_tiered_overall_r5": overall_v17_r5,
        "dbscan_strict_overall_r5": overall_strict_r5,
        "dbscan_strict_low_hawkes_r5": low_strict_r5,
        "dbscan_strict_cold_start_r5": cold_strict_r5,
        "perday_ba_tiered_r5": perday_v17_r5,
        "perday_dbscan_strict_r5": perday_strict_r5,
        "dw_features_in_top30": dw_in_top30,
        "v17_baseline_ba_tiered_r5": 0.4741,
        "v17_baseline_dbscan_strict_r5": 0.2266,
        "v17_baseline_low_hawkes_r5": 0.0588,
        "v17_baseline_cold_start_r5": 0.0443,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    log.info("\n=== v18_dw FINAL ===")
    log.info("BA-tiered  overall R@5%%: %.4f  (v17 baseline 0.4741)", overall_v17_r5)
    log.info("DBSCAN     overall R@5%%: %.4f  (v17 baseline 0.2266)", overall_strict_r5)
    log.info("DBSCAN low-Hawkes R@5%%: %.4f  (v17 baseline 0.0588, target 0.07)", low_strict_r5)
    log.info("DBSCAN cold-start R@5%%: %.4f  (v17 baseline 0.0443)", cold_strict_r5)
    log.info("DW features in top-30: %d", dw_in_top30)

    pass_t2 = (low_strict_r5 >= 0.07
               and overall_v17_r5 >= 0.47
               and dw_in_top30 >= 1)
    log.info("T2 PASS: low_hawkes ≥ 0.07 AND BA-tiered overall ≥ 0.47 AND ≥1 DW in top-30")
    log.info("VERDICT: %s", "PASS — ship v18 as production" if pass_t2 else "FAIL — do not ship")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
