"""Stage V11.4 — v18 PU training with GDELT news-augmented tiered labels.

Identical to `scripts/train_v17_ba_pu.py` except:
  - TIERED_PATH → `ignition_labels_tiered_v18_news.parquet` (5 tiers now)
  - Tier weights extended for PLATINUM_NEWS (1.3) and NEWS_ONLY (0.3)
  - Output: predictive_v18_news_pu/

CRITICAL: keep DBSCAN-based Hawkes (not v17 re-fit) per feedback_hawkes_density_over_purity.md.
Features identical to v17's 111.

Stopping rule: v18 R@top-5% >= v17 + 2 pp (i.e. >= 49.41%) else park.

Usage:
  python scripts/train_v18_news_pu.py
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
TIERED_PATH = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v18_news.parquet"
HAWKES_PATH = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO_PATH = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_news_pu"

LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}
LEAKY_V17 = {
    "best_tier", "label_tier", "cluster_count", "is_bronze_unlabeled",
    "is_tier_gold", "is_tier_silver", "is_tier_bronze",
    "is_tier_platinum_news", "is_tier_news_only",
    "t0_6hr_bin", "t0_duration_hours", "t0_rectified_ros_m_per_min",
    "t0_confidence", "x0_rectified_lon", "x0_rectified_lat",
}
HOLDOUT_START = pd.Timestamp("2025-02-01")

TIER_LABEL = {
    "PLATINUM_NEWS": 1, "GOLD": 1, "SILVER": 1, "BRONZE": 1, "NEWS_ONLY": 1, "none": 0,
}
TIER_WEIGHT = {
    "PLATINUM_NEWS": 1.3,  # news + BA corroboration
    "GOLD": 1.0,           # BA + FIRMS
    "SILVER": 0.7,         # BA only
    "BRONZE": 0.5,         # FIRMS only
    "NEWS_ONLY": 0.3,      # news only — weakest
    "none": 1.0,           # background
}


def build_v18_labels(base_df: pd.DataFrame, tiered: pd.DataFrame) -> pd.DataFrame:
    base_df["date"] = pd.to_datetime(base_df["date"])
    tiered["ignition_date"] = pd.to_datetime(tiered["ignition_date"])

    # When the same (cell, date) has multiple tiers, pick the BEST (highest weight)
    tier_rank = {"PLATINUM_NEWS": 5, "GOLD": 4, "SILVER": 3, "BRONZE": 2, "NEWS_ONLY": 1}
    tiered["tier_rank"] = tiered["tier"].map(tier_rank).fillna(0)
    idx = tiered.groupby(["cell_id", "ignition_date"])["tier_rank"].idxmax()
    by_cd = tiered.loc[idx, ["cell_id", "ignition_date", "tier"]].rename(
        columns={"ignition_date": "date", "tier": "best_tier"})

    merged = base_df.merge(by_cd, on=["cell_id", "date"], how="left")
    merged["best_tier"] = merged["best_tier"].astype(str).replace("nan", "none")
    merged["label_v18"] = merged["best_tier"].map(TIER_LABEL).fillna(0).astype(int)
    merged["weight_v18"] = merged["best_tier"].map(TIER_WEIGHT).fillna(1.0)
    merged["label_tier"] = merged["best_tier"]
    return merged


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not TIERED_PATH.exists():
        log.error("Missing tiered labels %s. Run V11.3 first.", TIERED_PATH)
        return 2

    log.info("Loading v8 base dataset...")
    ds = pd.read_parquet(V8_DIR / "dataset.parquet")
    ds["date"] = pd.to_datetime(ds["date"])

    log.info("Loading v18 tiered labels (5-tier with news)...")
    tiered = pd.read_parquet(TIERED_PATH)
    log.info("  %d tier rows; breakdown: %s", len(tiered), dict(tiered["tier"].value_counts()))

    log.info("Merging v18 labels → (cell, date)...")
    df = build_v18_labels(ds, tiered)
    n_pos = int((df["label_v18"] == 1).sum())
    log.info("  label_v18==1: %d positives (v17 had ~44,482)", n_pos)

    log.info("Merging Hawkes (DBSCAN-based, NOT re-fit — per feedback_hawkes_density_over_purity)...")
    hawkes = pd.read_parquet(HAWKES_PATH)
    hawkes["date"] = pd.to_datetime(hawkes["date"])
    df = df.merge(hawkes, on=["cell_id", "date"], how="left")
    for c in [col for col in df.columns if col.startswith("hawkes_")]:
        df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    log.info("Merging GLCM + Hydro...")
    glcm = pd.read_parquet(GLCM_PATH)
    df = df.merge(glcm, on="cell_id", how="left")
    for c in [col for col in glcm.columns if col != "cell_id"]:
        df[c] = df[c].fillna(df[c].median())
    hydro = pd.read_parquet(HYDRO_PATH)
    df = df.merge(hydro, on="cell_id", how="left")
    for c in [col for col in hydro.columns if col != "cell_id"]:
        df[c] = df[c].fillna(df[c].median())

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and c not in LEAKY_V17
             and c not in ("label_v18", "weight_v18")
             and df[c].dtype.kind in "biufc"]
    log.info("  Features: %d total (same 111 as v17)", len(feats))

    train = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Train: %d rows (%d pos), Val: %d rows (%d pos)",
             len(train), int(train["label_v18"].sum()),
             len(val), int(val["label_v18"].sum()))

    dtrain = lgb.Dataset(train[feats].values,
                          label=train["label_v18"].values,
                          weight=train["weight_v18"].values,
                          feature_name=feats)
    dval = lgb.Dataset(val[feats].values, label=val["label_v18"].values, reference=dtrain)

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

    log.info("Training v18_news_pu...")
    t0 = time.time()
    model = lgb.train(params, dtrain, num_boost_round=3000,
                       valid_sets=[dtrain, dval], valid_names=["train", "val"],
                       callbacks=[lgb.early_stopping(100), lgb.log_evaluation(200)])
    log.info("Done in %.0fs, best_iter=%d", time.time() - t0, model.best_iteration)
    model.save_model(str(OUT_DIR / "model.txt"))

    val_p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    val_y = val["label_v18"].values
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

    eval_df = val[["date", "label_v18"]].copy()
    eval_df["pred"] = val_p
    eval_df["date_str"] = eval_df["date"].dt.strftime("%Y-%m-%d")
    per_day = []
    for _, sub in eval_df.groupby("date_str"):
        if sub["label_v18"].sum() == 0:
            continue
        n_top5 = int(len(sub) * 0.05)
        ordered = sub.sort_values("pred", ascending=False)
        per_day.append(int(ordered["label_v18"].iloc[:n_top5].sum()) / sub["label_v18"].sum())
    perday_r5 = float(np.mean(per_day)) if per_day else 0.0

    results = {
        "model": "v18_news_pu",
        "n_features": int(len(feats)),
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
    log.info("Top 15 features:\n%s", fi.head(15).to_string(index=False))

    log.info("\n=== v18_news_pu FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f", roc, pr, best_f1, rec5, perday_r5)
    log.info("\n=== Progression: v15 → v17 → v18 ===")
    log.info("v15   : ROC=0.8646 PR=0.0380 R@5%%=0.4045 PerDayR%%=0.3310")
    log.info("v17   : ROC=0.8815 PR=0.1481 R@5%%=0.4741 PerDayR%%=0.4856  [BA-PU]")
    log.info("v18   : ROC=%.4f PR=%.4f R@5%%=%.4f PerDayR%%=%.4f  [BA-PU + GDELT news]",
             roc, pr, rec5, perday_r5)
    log.info("Δ v17→v18: R@5%%=%+.4f PerDayR%+.4f", rec5 - 0.4741, perday_r5 - 0.4856)

    if rec5 >= 0.4941:
        log.info("\nVERDICT: PASS (>=+2pp) — GDELT news unlocks structural ceiling-breaker")
    elif rec5 >= 0.4741:
        log.info("\nVERDICT: MARGINAL — below 2pp threshold; keep v17 as production")
    else:
        log.info("\nVERDICT: REGRESSION — v18 worse than v17, investigate noise from NEWS_ONLY tier")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
