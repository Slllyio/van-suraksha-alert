"""Phase 7 PS-3 — v13: v9 (Hawkes) + GLCM sub-pixel texture features.

The hypothesis: 2km cells with identical aggregate NDVI/land-cover fractions can
have very different ignition risk if one is a uniform dense forest and the other
is a fragmented forest-ag edge. GLCM Haralick features quantify this sub-pixel
heterogeneity. Expected uplift: +2-4 pp R@top-5% per the user's strategic note.

Output: outputs/predictive_fire_risk/predictive_v13_glcm_ignition/
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
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v13_glcm_ignition"

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

    log.info("Loading v8 dataset (DBSCAN ignition labels)...")
    df = pd.read_parquet(V8_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])

    log.info("Merging Hawkes (v9 stack)...")
    hawkes = pd.read_parquet(HAWKES_PATH)
    hawkes["date"] = pd.to_datetime(hawkes["date"])
    df = df.merge(hawkes, on=["cell_id", "date"], how="left")
    for c in [col for col in df.columns if col.startswith("hawkes_")]:
        df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    log.info("Merging GLCM texture features (NEW for v13)...")
    glcm = pd.read_parquet(GLCM_PATH)
    glcm_cols = [c for c in glcm.columns if c != "cell_id"]
    df = df.merge(glcm, on="cell_id", how="left")
    for c in glcm_cols:
        df[c] = df[c].fillna(df[c].median())
    log.info("  Added %d GLCM features", len(glcm_cols))

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and df[c].dtype.kind in "biufc"]
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    n_glcm = sum(1 for f in feats if f.startswith("glcm_") or f.startswith("ndvi_"))
    log.info("  Features: %d total (%d base + %d Hawkes + %d GLCM/NDVI)",
             len(feats), len(feats) - n_hawkes - n_glcm, n_hawkes, n_glcm)

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

    log.info("Training v13_glcm_ignition...")
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
    rec5 = float(recall_score(val_y, pred5, zero_division=0))
    rec10 = float(recall_score(val_y, pred10, zero_division=0))
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
        "model": "v13_glcm_ignition",
        "n_features": int(len(feats)),
        "n_hawkes": int(n_hawkes),
        "n_glcm": int(n_glcm),
        "best_iteration": int(model.best_iteration),
        "roc_auc": roc, "pr_auc": pr,
        "best_f1": best_f1, "best_f1_threshold": best_t,
        "precision_top5pct": prec5, "recall_top5pct": rec5,
        "recall_top10pct": rec10,
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
    n_glcm_top20 = sum(1 for f in top20 if f.startswith("glcm_") or f.startswith("ndvi_"))
    log.info("GLCM/NDVI features in top 20: %d / %d", n_glcm_top20, n_glcm)

    log.info("\n=== v13_glcm_ignition FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f", roc, pr, best_f1, rec5, perday_r5)

    log.info("\n=== Progression: v8 → v9 → v13 ===")
    log.info("v8  : ROC=0.8103 PR=0.0248 F1=0.0767 R@5%%=0.2811 PerDayR%%=0.1947")
    log.info("v9  : ROC=0.8626 PR=0.0383 F1=0.0928 R@5%%=0.3937 PerDayR%%=0.2898  [Hawkes]")
    log.info("v13 : ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f  [+ GLCM]",
             roc, pr, best_f1, rec5, perday_r5)
    log.info("Δ v9→v13: ROC=%+.4f PR=%+.4f R@5%%=%+.4f PerDayR%+.4f",
             roc - 0.8626, pr - 0.0383, rec5 - 0.3937, perday_r5 - 0.2898)

    if rec5 >= 0.4137:  # v9 + 2 pp
        log.info("\nVERDICT: PASS — GLCM texture captures fragmentation signal.")
    elif rec5 >= 0.3937:
        log.info("\nVERDICT: MARGINAL — GLCM adds slight value.")
    else:
        log.info("\nVERDICT: FAIL — GLCM redundant with existing lc_frac_* and NDVI features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
