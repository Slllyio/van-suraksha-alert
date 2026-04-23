"""Phase 5 v9.3 — Train v9_hawkes_ignition LightGBM on v8 features + Hawkes intensity.

Merges Hawkes λ features (hawkes_lambda, hawkes_lambda_log, hawkes_n_recent_10km_7d,
hawkes_nearest_ign_14d_km) into v8 dataset and trains LightGBM with v8-style params.

Gate: v9 R@top-5% on new ignitions ≥ v8's 28.11% + 2pp = 30.11%.

Output: outputs/predictive_fire_risk/predictive_v9_hawkes_ignition/
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
V8_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
HAWKES_PATH = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v9_hawkes_ignition"

LEAKAGE_FEATURES = {
    "days_since_last_fire", "fire_last_7d",
    "neighbor_fire_7d", "neighbor_fire_yesterday",
}
NON_FEATURES = {
    "cell_id", "date", "label", "year",
    "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp",
}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v8 dataset (DBSCAN ignition labels + 84 base features)...")
    df = pd.read_parquet(V8_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])
    log.info("  %d rows, %d cols", len(df), df.shape[1])

    log.info("Loading Hawkes intensity features...")
    hawkes = pd.read_parquet(HAWKES_PATH)
    hawkes["date"] = pd.to_datetime(hawkes["date"])
    hawkes_cols = [c for c in hawkes.columns if c.startswith("hawkes_")]
    log.info("  %d rows, %d Hawkes cols: %s", len(hawkes), len(hawkes_cols), hawkes_cols)

    log.info("Merging Hawkes onto v8 dataset...")
    t0 = time.time()
    df = df.merge(hawkes, on=["cell_id", "date"], how="left")
    n_matched = int(df[hawkes_cols[0]].notna().sum())
    log.info("  Merge in %.1fs: %d/%d rows matched (%.1f%%)",
             time.time() - t0, n_matched, len(df), 100 * n_matched / len(df))
    # Fill any unmatched rows with 0 (no past ignitions in lookback)
    for c in hawkes_cols:
        if c == "hawkes_nearest_ign_14d_km":
            df[c] = df[c].fillna(50.0)  # max distance cap
        else:
            df[c] = df[c].fillna(0)

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and df[c].dtype.kind in "biufc"]
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    log.info("  Features: %d total (%d base + %d Hawkes)",
             len(feats), len(feats) - n_hawkes, n_hawkes)

    train_mask = df["date"] < HOLDOUT_START
    val_mask = df["date"] >= HOLDOUT_START
    train = df[train_mask].reset_index(drop=True)
    val = df[val_mask].reset_index(drop=True)
    log.info("  Train: %d rows, %d ignitions (%.3f%%)",
             len(train), int(train["label_dbscan_ignition"].sum()),
             100 * train["label_dbscan_ignition"].mean())
    log.info("  Val:   %d rows, %d ignitions (%.3f%%)",
             len(val), int(val["label_dbscan_ignition"].sum()),
             100 * val["label_dbscan_ignition"].mean())

    dtrain = lgb.Dataset(train[feats].values, label=train["label_dbscan_ignition"].values, feature_name=feats)
    dval = lgb.Dataset(val[feats].values, label=val["label_dbscan_ignition"].values, reference=dtrain)

    # Same v8-style params
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

    log.info("Training v9_hawkes_ignition...")
    t0 = time.time()
    model = lgb.train(
        params, dtrain, num_boost_round=2000,
        valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(50)],
    )
    log.info("Training done in %.0fs, best_iter=%d", time.time() - t0, model.best_iteration)

    model.save_model(str(OUT_DIR / "model.txt"))

    val_p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    val_y = val["label_dbscan_ignition"].values

    roc = float(roc_auc_score(val_y, val_p))
    pr = float(average_precision_score(val_y, val_p))

    best_f1, best_t = 0.0, 0.5
    for t in np.arange(0.01, 0.99, 0.01):
        f1 = f1_score(val_y, (val_p >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = float(f1), float(t)

    p95 = float(np.percentile(val_p, 95))
    p90 = float(np.percentile(val_p, 90))
    pred_top5 = (val_p >= p95).astype(int)
    pred_top10 = (val_p >= p90).astype(int)
    prec_top5 = float(precision_score(val_y, pred_top5, zero_division=0))
    recall_top5 = float(recall_score(val_y, pred_top5, zero_division=0))
    prec_top10 = float(precision_score(val_y, pred_top10, zero_division=0))
    recall_top10 = float(recall_score(val_y, pred_top10, zero_division=0))

    # Per-day rank recall
    eval_df = val[["date", "label_dbscan_ignition"]].copy()
    eval_df["pred"] = val_p
    eval_df["date_str"] = eval_df["date"].dt.strftime("%Y-%m-%d")
    rec5_per_day = []
    for _, sub in eval_df.groupby("date_str"):
        if sub["label_dbscan_ignition"].sum() == 0:
            continue
        n_top5 = int(len(sub) * 0.05)
        ordered = sub.sort_values("pred", ascending=False)
        recall = int(ordered["label_dbscan_ignition"].iloc[:n_top5].sum()) / sub["label_dbscan_ignition"].sum()
        rec5_per_day.append(recall)
    perday_r5 = float(np.mean(rec5_per_day)) if rec5_per_day else 0.0

    results = {
        "model": "v9_hawkes_ignition",
        "n_features": int(len(feats)),
        "n_hawkes_features": int(n_hawkes),
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "best_iteration": int(model.best_iteration),
        "val_pos_rate": float(val_y.mean()),
        "roc_auc": roc, "pr_auc": pr,
        "best_f1": best_f1, "best_f1_threshold": best_t,
        "precision_top5pct": prec_top5, "recall_top5pct": recall_top5,
        "precision_top10pct": prec_top10, "recall_top10pct": recall_top10,
        "perday_recall_top5pct": perday_r5,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
        "split": model.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False)
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    log.info("Top 20 features:\n%s", fi.head(20).to_string(index=False))
    hawkes_ranks = fi.reset_index(drop=True)
    hawkes_in_top20 = int((hawkes_ranks["feature"].str.startswith("hawkes_")).iloc[:20].sum())
    log.info("Hawkes features in top 20: %d / %d", hawkes_in_top20, n_hawkes)

    log.info("\n=== v9_hawkes_ignition FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f", roc, pr, best_f1)
    log.info("P@top-5%%=%.4f  R@top-5%%=%.4f  PerDayR@top-5%%=%.4f",
             prec_top5, recall_top5, perday_r5)
    log.info("P@top-10%%=%.4f R@top-10%%=%.4f", prec_top10, recall_top10)

    log.info("\n=== vs v8_ignition_dbscan (same labels, no Hawkes) ===")
    log.info("v8 : ROC=0.8103 PR=0.0248 F1=0.0767 R@top-5%%=0.2811 PerDayR@5%%=0.1947")
    log.info("v9 : ROC=%.4f PR=%.4f F1=%.4f R@top-5%%=%.4f PerDayR@5%%=%.4f",
             roc, pr, best_f1, recall_top5, perday_r5)
    log.info("delta: ROC=%+.4f PR=%+.4f F1=%+.4f R@top-5%%=%+.4f PerDayR%+.4f",
             roc - 0.8103, pr - 0.0248, best_f1 - 0.0767,
             recall_top5 - 0.2811, perday_r5 - 0.1947)

    gate_r5 = recall_top5 >= 0.3011
    gate_perday = perday_r5 >= 0.2147
    if gate_r5 and gate_perday:
        log.info("\nVERDICT: PASS — Hawkes helps. PROMOTE to v9, proceed to v10 (behavioral features)")
    elif gate_r5 or gate_perday:
        log.info("\nVERDICT: PARTIAL — one gate passed. Consider ensemble, proceed cautiously")
    else:
        log.info("\nVERDICT: FAIL — Hawkes does not lift ignition above v8. Grid-search bandwidths or skip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
