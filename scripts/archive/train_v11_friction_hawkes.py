"""Phase 5 v11 — v9 (Hawkes) + Friction features + Calendar (best of v10).

Tests if "Human Friction" (Tobler walk-time from settlements) provides hard spatial
prior that v9 lacks. Hypothesis: cells > 4 hours walk should have near-zero ignition
rate; this helps the model down-weight false positives in inaccessible terrain.

Output: outputs/predictive_fire_risk/predictive_v11_friction_hawkes/
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
CALENDAR_PATH = ROOT / "data_lake" / "human_activity" / "calendar_features.parquet"
FRICTION_PATH = ROOT / "data_lake" / "human_activity" / "friction_features.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v11_friction_hawkes"

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

    log.info("Loading v8 dataset...")
    df = pd.read_parquet(V8_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])

    log.info("Merging Hawkes (v9 stack)...")
    hawkes = pd.read_parquet(HAWKES_PATH)
    hawkes["date"] = pd.to_datetime(hawkes["date"])
    df = df.merge(hawkes, on=["cell_id", "date"], how="left")
    for c in [col for col in df.columns if col.startswith("hawkes_")]:
        df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    log.info("Merging calendar (top-helper from v10)...")
    cal = pd.read_parquet(CALENDAR_PATH)
    cal["date"] = pd.to_datetime(cal["date"])
    df = df.merge(cal, on="date", how="left")

    log.info("Merging FRICTION (NEW v11)...")
    fric = pd.read_parquet(FRICTION_PATH)
    df = df.merge(fric, on="cell_id", how="left")
    n_fric_cols = len([c for c in fric.columns if c != "cell_id"])
    log.info("  Added %d friction features", n_fric_cols)

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and df[c].dtype.kind in "biufc"]
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    n_friction = sum(1 for f in feats if f.startswith("friction_"))
    n_cal = sum(1 for f in feats if f in set(cal.columns) and f != "date")
    log.info("  Features: %d total (%d base + %d Hawkes + %d calendar + %d friction)",
             len(feats), len(feats) - n_hawkes - n_friction - n_cal,
             n_hawkes, n_cal, n_friction)

    train = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Train: %d rows, Val: %d rows", len(train), len(val))

    dtrain = lgb.Dataset(train[feats].values, label=train["label_dbscan_ignition"].values, feature_name=feats)
    dval = lgb.Dataset(val[feats].values, label=val["label_dbscan_ignition"].values, reference=dtrain)

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

    log.info("Training v11_friction_hawkes...")
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
    pred5 = (val_p >= p95).astype(int)
    pred10 = (val_p >= p90).astype(int)
    prec5 = float(precision_score(val_y, pred5, zero_division=0))
    rec5 = float(recall_score(val_y, pred5, zero_division=0))
    prec10 = float(precision_score(val_y, pred10, zero_division=0))
    rec10 = float(recall_score(val_y, pred10, zero_division=0))

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
        "model": "v11_friction_hawkes",
        "n_features": int(len(feats)),
        "n_hawkes": int(n_hawkes),
        "n_friction": int(n_friction),
        "n_cal": int(n_cal),
        "best_iteration": int(model.best_iteration),
        "roc_auc": roc, "pr_auc": pr,
        "best_f1": best_f1, "best_f1_threshold": best_t,
        "precision_top5pct": prec5, "recall_top5pct": rec5,
        "precision_top10pct": prec10, "recall_top10pct": rec10,
        "perday_recall_top5pct": perday_r5,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
        "split": model.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False)
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    log.info("Top 25 features:\n%s", fi.head(25).to_string(index=False))

    top20 = fi.head(20)["feature"].tolist()
    n_friction_top20 = sum(1 for f in top20 if f.startswith("friction_"))
    log.info("Friction features in top 20: %d / %d", n_friction_top20, n_friction)

    log.info("\n=== v11_friction_hawkes FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f", roc, pr, best_f1)
    log.info("R@top-5%%=%.4f  PerDayR@top-5%%=%.4f", rec5, perday_r5)

    log.info("\n=== Progression: v8 → v9 → v10 → v11 ===")
    log.info("v8  : ROC=0.8103 PR=0.0248 F1=0.0767 R@5%%=0.2811 PerDayR%%=0.1947")
    log.info("v9  : ROC=0.8626 PR=0.0383 F1=0.0928 R@5%%=0.3937 PerDayR%%=0.2898  [Hawkes]")
    log.info("v10 : ROC=0.8611 PR=0.0358 F1=0.0864 R@5%%=0.3965 PerDayR%%=0.3024  [+ Calendar]")
    log.info("v11 : ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f  [+ Friction]",
             roc, pr, best_f1, rec5, perday_r5)
    log.info("Δ v9→v11: ROC=%+.4f PR=%+.4f R@top-5%%=%+.4f PerDayR%+.4f",
             roc - 0.8626, pr - 0.0383, rec5 - 0.3937, perday_r5 - 0.2898)

    if rec5 >= 0.4137:  # v9 + 2pp
        log.info("\nVERDICT: PASS — Friction adds value. v11 is new operational best")
    elif rec5 > 0.3937:
        log.info("\nVERDICT: MARGINAL — v11 slightly above v9; consider keeping for ensemble")
    else:
        log.info("\nVERDICT: FAIL — Friction redundant with existing dist_settlement features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
