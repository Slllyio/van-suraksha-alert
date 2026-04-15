"""Phase 7 PS-1 — v16: v9 (Hawkes) + Sentinel-1 SAR amplitude anomaly features.

Adds GRD-derived backscatter anomaly features that penetrate canopy:
  - vv_recent_mean       : 12-day VV mean (dB-scale)
  - vv_ref_mean          : 90-day VV reference mean
  - vv_anomaly_z         : (recent - ref) / ref_std  (sudden brightness shift)
  - vv_cv_drop           : recent CV - ref CV       (unstable scattering signature)

Theory: anthropogenic clearing/raking changes ground-surface roughness within
the canopy, which alters VV backscatter even when optical sensors see only
intact canopy. This is the only feature family that can see understory
disturbance in dry deciduous MP forest.

Output: outputs/predictive_fire_risk/predictive_v16_sar_coherence/
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
SAR_PATH = ROOT / "data_lake" / "sar" / "s1_features_per_cell_date.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v16_sar_coherence"

LEAKAGE_FEATURES = {
    "days_since_last_fire", "fire_last_7d",
    "neighbor_fire_7d", "neighbor_fire_yesterday",
}
NON_FEATURES = {
    "cell_id", "date", "label", "year",
    "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp",
}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v8 dataset...")
    df = pd.read_parquet(V8_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])

    log.info("Merging Hawkes...")
    hawkes = pd.read_parquet(HAWKES_PATH)
    hawkes["date"] = pd.to_datetime(hawkes["date"])
    df = df.merge(hawkes, on=["cell_id", "date"], how="left")
    for c in [col for col in df.columns if col.startswith("hawkes_")]:
        df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    log.info("Merging SAR features (NEW for v16)...")
    if not SAR_PATH.exists():
        log.error("Missing SAR features at %s. Build with scripts/build_sar_features_mp.py first.", SAR_PATH)
        return 2
    sar = pd.read_parquet(SAR_PATH)
    sar["date"] = pd.to_datetime(sar["date"])
    df = df.merge(sar, on=["cell_id", "date"], how="left")
    sar_cols = [c for c in sar.columns if c.startswith("vv_")]
    for c in sar_cols:
        df[c] = df[c].fillna(df[c].median())
    log.info("  Added %d SAR features", len(sar_cols))

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and df[c].dtype.kind in "biufc"]
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    n_sar = sum(1 for f in feats if f.startswith("vv_"))
    log.info("  Features: %d total (base + %d Hawkes + %d SAR)", len(feats), n_hawkes, n_sar)

    train = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)

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

    log.info("Training v16_sar_coherence...")
    t0 = time.time()
    model = lgb.train(
        params, dtrain, num_boost_round=2000,
        valid_sets=[dtrain, dval], valid_names=["train", "val"],
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
    pred5 = (val_p >= p95).astype(int)
    rec5 = float(recall_score(val_y, pred5, zero_division=0))
    prec5 = float(precision_score(val_y, pred5, zero_division=0))

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
        "model": "v16_sar_coherence",
        "n_features": int(len(feats)),
        "n_hawkes": n_hawkes, "n_sar": n_sar,
        "best_iteration": int(model.best_iteration),
        "roc_auc": roc, "pr_auc": pr,
        "best_f1": best_f1, "best_f1_threshold": best_t,
        "precision_top5pct": prec5, "recall_top5pct": rec5,
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

    n_sar_top20 = sum(1 for f in fi.head(20)["feature"].tolist() if f.startswith("vv_"))
    log.info("SAR features in top 20: %d / %d", n_sar_top20, n_sar)

    log.info("\n=== v16_sar_coherence FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f", roc, pr, best_f1, rec5, perday_r5)

    log.info("\n=== Progression: v9 → v15 → v16 ===")
    log.info("v9   : ROC=0.8626 PR=0.0383 F1=0.0928 R@5%%=0.3937 PerDayR%%=0.2898")
    log.info("v15  : ROC=0.8646 PR=0.0?   F1=0.0?   R@5%%=0.4045 PerDayR%%=0.3310  [v13×v14 ensemble]")
    log.info("v16  : ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f  [+ SAR]",
             roc, pr, best_f1, rec5, perday_r5)
    log.info("Δ v9→v16: R@5%%=%+.4f PerDayR%+.4f", rec5 - 0.3937, perday_r5 - 0.2898)

    if rec5 >= 0.4150:
        log.info("\nVERDICT: PASS — SAR understory signal carries through")
    elif rec5 >= 0.3937:
        log.info("\nVERDICT: MARGINAL — SAR adds incremental value, ensemble may help")
    else:
        log.info("\nVERDICT: FAIL — SAR amplitude too noisy at 2km cell aggregation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
