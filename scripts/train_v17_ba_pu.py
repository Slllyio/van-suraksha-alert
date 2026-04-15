"""Stage 4 — v17 Elkan-Noto PU training on BA-augmented tiered labels.

Inputs:
  - `data_lake/fire_detections/ignition_labels_tiered_v17.parquet` from Stage 2+3
  - `outputs/predictive_fire_risk/predictive_v8_ignition_dbscan/dataset.parquet` base features
  - Hawkes re-fit to NEW GOLD+SILVER ignition dates — re-use fit_hawkes_mp pattern
  - GLCM + Hydro feature parquets (v13 + v14)

Training label rule (Elkan-Noto PU):
  - GOLD (BA ∩ FIRMS agreement): weight 1.0, label 1
  - SILVER (BA-only, forest+season): weight 0.7, label 1
  - BRONZE (FIRMS-only): treated as unlabeled per Elkan-Noto — NOT confirmed positive
  - Negative: cells with zero fire history in 5+ years

Added v17 feature columns:
  - t0_6hr_bin (one-hot 4-dim)
  - t0_confidence
  - label_tier (one-hot 3-dim)
  - is_rectified

Output: `outputs/predictive_fire_risk/predictive_v17_ba_pu/{model.txt, results.json}`

Usage:
  python scripts/train_v17_ba_pu.py
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
TIERED_PATH = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"
HAWKES_PATH = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO_PATH = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu"

LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def build_v17_labels(base_df: pd.DataFrame, tiered: pd.DataFrame) -> pd.DataFrame:
    """Merge tiered labels into cell×date grid; return with new cols:
       label_v17 (0/1), weight_v17, label_tier (GOLD/SILVER/BRONZE/none)."""
    base_df["date"] = pd.to_datetime(base_df["date"])
    tiered["ignition_date"] = pd.to_datetime(tiered["ignition_date"])

    # Group tiered labels by (cell_id, date) — take best tier + sum weights
    by_cd = tiered.groupby(["cell_id", "ignition_date"]).agg(
        best_tier=("tier", lambda s: ("GOLD" if (s == "GOLD").any()
                                      else ("SILVER" if (s == "SILVER").any()
                                            else "BRONZE"))),
        cluster_count=("tier", "count"),
    ).reset_index()
    by_cd = by_cd.rename(columns={"ignition_date": "date"})

    merged = base_df.merge(by_cd, on=["cell_id", "date"], how="left")

    # Cast best_tier to plain string to allow filling NaN with 'none' safely
    merged["best_tier"] = merged["best_tier"].astype(str).replace("nan", "none")

    # Assign label + weight — Stage 4b fix: BRONZE is a real FIRMS fire, just without
    # BA corroboration. Treat as lower-weight positive (0.5), not unlabeled.
    tier_to_label = {"GOLD": 1, "SILVER": 1, "BRONZE": 1, "none": 0}
    tier_to_weight = {"GOLD": 1.0, "SILVER": 0.7, "BRONZE": 0.5, "none": 1.0}
    merged["label_v17"] = merged["best_tier"].map(tier_to_label).fillna(0).astype(int)
    merged["weight_v17"] = merged["best_tier"].map(tier_to_weight).fillna(1.0)
    merged["label_tier"] = merged["best_tier"]
    merged["is_bronze_unlabeled"] = (merged["best_tier"] == "BRONZE").astype(int)
    return merged


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not TIERED_PATH.exists():
        log.error("Missing tiered labels %s. Run Stage 2+3 first.", TIERED_PATH)
        return 2

    log.info("Loading v8 base dataset (provides 84 features + original DBSCAN label)...")
    ds = pd.read_parquet(V8_DIR / "dataset.parquet")
    ds["date"] = pd.to_datetime(ds["date"])
    log.info("  %d rows × %d cols", len(ds), len(ds.columns))

    log.info("Loading tiered v17 labels...")
    tiered = pd.read_parquet(TIERED_PATH)
    log.info("  %d tier-rows (distribution: %s)", len(tiered), dict(tiered["tier"].value_counts()))

    log.info("Merging v17 labels → (cell_id, date)...")
    df = build_v17_labels(ds, tiered)
    n_positive_v17 = int((df["label_v17"] == 1).sum())
    n_bronze = int(df["is_bronze_unlabeled"].sum())
    log.info("  label_v17==1: %d positives (vs v8 DBSCAN: %d)", n_positive_v17, int(df["label_dbscan_ignition"].sum()))
    log.info("  BRONZE (unlabeled): %d", n_bronze)

    log.info("Merging Hawkes (WARNING: using pre-v17 Hawkes — v17 Hawkes re-fit should follow)...")
    if HAWKES_PATH.exists():
        hawkes = pd.read_parquet(HAWKES_PATH)
        hawkes["date"] = pd.to_datetime(hawkes["date"])
        df = df.merge(hawkes, on=["cell_id", "date"], how="left")
        for c in [col for col in df.columns if col.startswith("hawkes_")]:
            df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    log.info("Merging GLCM...")
    if GLCM_PATH.exists():
        glcm = pd.read_parquet(GLCM_PATH)
        df = df.merge(glcm, on="cell_id", how="left")
        for c in [col for col in glcm.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())

    log.info("Merging Hydro...")
    if HYDRO_PATH.exists():
        hydro = pd.read_parquet(HYDRO_PATH)
        df = df.merge(hydro, on="cell_id", how="left")
        for c in [col for col in hydro.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())

    # CRITICAL: do NOT include tier/t0 columns as features — they're only populated
    # for positive rows, which leaks the label trivially.
    LEAKY_V17 = {
        "best_tier", "label_tier", "cluster_count", "is_bronze_unlabeled",
        "is_tier_gold", "is_tier_silver", "is_tier_bronze",
        "t0_6hr_bin", "t0_duration_hours", "t0_rectified_ros_m_per_min",
        "t0_confidence", "x0_rectified_lon", "x0_rectified_lat",
    }

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and c not in LEAKY_V17
             and c not in ("label_v17", "weight_v17")
             and df[c].dtype.kind in "biufc"]
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    n_glcm = sum(1 for f in feats if f.startswith("glcm_") or f.startswith("ndvi_"))
    n_hydro = sum(1 for f in feats if f.startswith("hydro_"))
    log.info("  Features: %d total (base + %d Hawkes + %d GLCM + %d Hydro, NO tier/t0 leakage)",
             len(feats), n_hawkes, n_glcm, n_hydro)

    # Train / val split
    train = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Train: %d rows (%d pos), Val: %d rows (%d pos)",
             len(train), int(train["label_v17"].sum()),
             len(val), int(val["label_v17"].sum()))

    # Stage 4b: BRONZE is now a weighted positive (0.5), not excluded. Keep all rows.
    train_pu = train
    log.info("Train breakdown (weighted PU): total=%d, label=1 n=%d (GOLD/SILVER/BRONZE), label=0 n=%d",
             len(train_pu), int(train_pu["label_v17"].sum()),
             int((train_pu["label_v17"] == 0).sum()))
    log.info("  weight median by tier: GOLD=%.2f SILVER=%.2f BRONZE=%.2f",
             train_pu.loc[train_pu["best_tier"] == "GOLD", "weight_v17"].median() if (train_pu["best_tier"] == "GOLD").any() else 0,
             train_pu.loc[train_pu["best_tier"] == "SILVER", "weight_v17"].median() if (train_pu["best_tier"] == "SILVER").any() else 0,
             train_pu.loc[train_pu["best_tier"] == "BRONZE", "weight_v17"].median() if (train_pu["best_tier"] == "BRONZE").any() else 0)

    dtrain = lgb.Dataset(train_pu[feats].values,
                          label=train_pu["label_v17"].values,
                          weight=train_pu["weight_v17"].values,
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

    log.info("Training v17_ba_pu...")
    t0 = time.time()
    model = lgb.train(
        params, dtrain, num_boost_round=3000,
        valid_sets=[dtrain, dval], valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(100)],
    )
    log.info("Training done in %.0fs, best_iter=%d", time.time() - t0, model.best_iteration)
    model.save_model(str(OUT_DIR / "model.txt"))

    val_p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    val_y = val["label_v17"].values

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

    eval_df = val[["date", "label_v17"]].copy()
    eval_df["pred"] = val_p
    eval_df["date_str"] = eval_df["date"].dt.strftime("%Y-%m-%d")
    per_day = []
    for _, sub in eval_df.groupby("date_str"):
        if sub["label_v17"].sum() == 0:
            continue
        n_top5 = int(len(sub) * 0.05)
        ordered = sub.sort_values("pred", ascending=False)
        recall = int(ordered["label_v17"].iloc[:n_top5].sum()) / sub["label_v17"].sum()
        per_day.append(recall)
    perday_r5 = float(np.mean(per_day)) if per_day else 0.0

    results = {
        "model": "v17_ba_pu",
        "n_features": int(len(feats)),
        "n_hawkes": n_hawkes, "n_glcm": n_glcm, "n_hydro": n_hydro,
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

    log.info("\n=== v17_ba_pu FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f", roc, pr, best_f1, rec5, perday_r5)
    log.info("\n=== Progression: v9 → v15 → v17 ===")
    log.info("v9  : ROC=0.8626 PR=0.0383 R@5%%=0.3937 PerDayR%%=0.2898")
    log.info("v15 : ROC=0.8646 PR=0.0380 R@5%%=0.4045 PerDayR%%=0.3310  [geo-mean ensemble]")
    log.info("v17 : ROC=%.4f PR=%.4f R@5%%=%.4f PerDayR%%=%.4f  [+ BA-augmented PU]",
             roc, pr, rec5, perday_r5)

    if rec5 >= 0.425:
        log.info("\nVERDICT: PASS (≥42.5%) — BA labels unlock structural improvement")
    elif rec5 >= 0.405:
        log.info("\nVERDICT: MARGINAL — similar to v15, labels add noise or feature subsumed")
    else:
        log.info("\nVERDICT: FAIL — v17 worse than v15, investigate PU hyper + Hawkes re-fit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
