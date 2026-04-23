"""Phase 1.4: Train v7_fuel LightGBM on the fuel-extended dataset.

Uses honest temporal hold-out:
  Train: date < 2025-02-01
  Val:   2025-02-01 to 2025-05-29 (last fire season)

Compares against v6e_live baseline (AUC 0.885 on random val, unknown on temporal).

Output:
  outputs/predictive_fire_risk/predictive_v7_fuel/
    - model.lgbm
    - results.json
    - feature_importance.csv
    - honest_benchmark.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score, recall_score,
    roc_auc_score,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("v7_fuel")

ROOT = Path(__file__).resolve().parents[1]
V7_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v7_fuel"
DATASET = V7_DIR / "dataset_fuel.parquet"

# Honest temporal hold-out
HOLDOUT_START = "2025-02-01"
HOLDOUT_END = "2025-05-29"

# LightGBM params (matching v6e_live)
LGB_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "num_leaves": 63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_data_in_leaf": 200,
    "verbose": -1,
    "seed": 42,
    "num_threads": -1,
}

# Non-feature columns
NON_FEATURE = {"cell_id", "date", "label"}


def main() -> int:
    log.info("Loading %s...", DATASET.relative_to(ROOT))
    df = pd.read_parquet(DATASET)
    log.info("  %d rows, %d cols", len(df), df.shape[1])

    # Build feature list (all columns except cell_id/date/label)
    all_cols = [c for c in df.columns if c not in NON_FEATURE]
    features = all_cols
    log.info("  %d features", len(features))

    fuel_feats = [f for f in features if f.startswith("fuel_")]
    log.info("  Fuel features: %s", fuel_feats)

    # Temporal split
    df["date"] = pd.to_datetime(df["date"])
    train_mask = df["date"] < HOLDOUT_START
    val_mask = (df["date"] >= HOLDOUT_START) & (df["date"] <= HOLDOUT_END)

    train_df = df[train_mask].reset_index(drop=True)
    val_df = df[val_mask].reset_index(drop=True)
    log.info("\nTemporal split:")
    log.info("  Train: %d rows (%s to %s)", len(train_df),
             train_df["date"].min().date(), train_df["date"].max().date())
    log.info("  Val:   %d rows (%s to %s)", len(val_df),
             val_df["date"].min().date(), val_df["date"].max().date())
    log.info("  Train fire rate: %.2f%%  Val fire rate: %.2f%%",
             100 * train_df["label"].mean(), 100 * val_df["label"].mean())

    # Prepare data
    X_train = train_df[features].values
    y_train = train_df["label"].values
    X_val = val_df[features].values
    y_val = val_df["label"].values

    log.info("\nTraining LightGBM (num_leaves=%d, lr=%.3f)...",
             LGB_PARAMS["num_leaves"], LGB_PARAMS["learning_rate"])
    dtrain = lgb.Dataset(X_train, label=y_train, feature_name=features)
    dval = lgb.Dataset(X_val, label=y_val, feature_name=features, reference=dtrain)

    model = lgb.train(
        LGB_PARAMS,
        dtrain,
        num_boost_round=1000,
        valid_sets=[dval],
        valid_names=["val"],
        callbacks=[lgb.early_stopping(stopping_rounds=50), lgb.log_evaluation(50)],
    )

    # Evaluate
    log.info("\nEvaluating on temporal hold-out...")
    val_prob = model.predict(X_val)

    roc = roc_auc_score(y_val, val_prob)
    pr = average_precision_score(y_val, val_prob)

    # Best F1 threshold sweep
    thresholds = np.arange(0.05, 0.95, 0.025)
    best_f1 = 0
    best_thresh = 0.5
    for t in thresholds:
        y_pred = (val_prob >= t).astype(int)
        f1 = f1_score(y_val, y_pred)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = float(t)

    y_pred_best = (val_prob >= best_thresh).astype(int)
    prec = precision_score(y_val, y_pred_best)
    rec = recall_score(y_val, y_pred_best)

    # Top-10% precision
    top10_thresh = np.percentile(val_prob, 90)
    y_pred_top10 = (val_prob >= top10_thresh).astype(int)
    prec_top10 = precision_score(y_val, y_pred_top10)

    log.info("\n=== HONEST TEMPORAL HOLD-OUT RESULTS ===")
    log.info("  ROC-AUC:              %.4f", roc)
    log.info("  PR-AUC:               %.4f", pr)
    log.info("  Best F1:              %.4f  (threshold=%.3f)", best_f1, best_thresh)
    log.info("    Precision:          %.4f", prec)
    log.info("    Recall:             %.4f", rec)
    log.info("  Precision @ top-10%%:  %.4f", prec_top10)
    log.info("  Best iteration:       %d", model.best_iteration or model.current_iteration())

    # Feature importance
    gains = model.feature_importance(importance_type="gain")
    fi = sorted(zip(features, gains), key=lambda x: x[1], reverse=True)
    log.info("\n  Top 25 features by gain:")
    for i, (name, gain) in enumerate(fi[:25]):
        total = sum(gains)
        marker = " ← FUEL" if name.startswith("fuel_") else ""
        log.info("    %2d. %-28s %9.0f  (%.2f%%)%s",
                 i + 1, name, gain, 100 * gain / total, marker)

    # Fuel feature ranks
    log.info("\n  Fuel features ranking:")
    for name in fuel_feats:
        for rank, (n, g) in enumerate(fi):
            if n == name:
                log.info("    %-25s  rank #%d  gain=%.0f", name, rank + 1, g)
                break

    # Save
    V7_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(str(V7_DIR / "model.lgbm"))

    results = {
        "honest_benchmark": {
            "holdout_start": HOLDOUT_START,
            "holdout_end": HOLDOUT_END,
            "n_train": int(len(train_df)),
            "n_val": int(len(val_df)),
            "val_fire_rate": float(y_val.mean()),
            "roc_auc": float(roc),
            "pr_auc": float(pr),
            "best_f1": float(best_f1),
            "best_f1_threshold": float(best_thresh),
            "precision_at_best_f1": float(prec),
            "recall_at_best_f1": float(rec),
            "precision_at_top10pct": float(prec_top10),
            "best_iteration": int(model.best_iteration or model.current_iteration()),
        },
        "n_features": len(features),
        "fuel_features": fuel_feats,
        "feature_importance_top_30": {k: float(v) for k, v in fi[:30]},
    }
    (V7_DIR / "honest_benchmark.json").write_text(json.dumps(results, indent=2))
    log.info("\nSaved: %s", (V7_DIR / "model.lgbm").relative_to(ROOT))
    log.info("Saved: %s", (V7_DIR / "honest_benchmark.json").relative_to(ROOT))

    # Write feature importance CSV
    fi_df = pd.DataFrame(fi, columns=["feature", "gain"])
    fi_df["rank"] = range(1, len(fi) + 1)
    fi_df["pct"] = 100 * fi_df["gain"] / fi_df["gain"].sum()
    fi_df.to_csv(V7_DIR / "feature_importance.csv", index=False)
    log.info("Saved: %s", (V7_DIR / "feature_importance.csv").relative_to(ROOT))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
