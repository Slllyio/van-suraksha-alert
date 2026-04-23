"""Phase 5 v10 — Train v10_behavior_ignition: v9 + calendar features + NTFP prices.

Stacks behavioral features on top of v9's Hawkes-enhanced baseline.
Uses existing synthetic NTFP prices (memory flags real scrape as untested), acknowledging
the synthetic data may just encode DOY — but at least we can measure the lift from
calendar features which are 100% real.

Output: outputs/predictive_fire_risk/predictive_v10_behavior_ignition/
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
NTFP_PRICES_PATH = ROOT / "data_lake" / "human_activity" / "ntfp_mandi_prices.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v10_behavior_ignition"

LEAKAGE_FEATURES = {
    "days_since_last_fire", "fire_last_7d",
    "neighbor_fire_7d", "neighbor_fire_yesterday",
}
NON_FEATURES = {
    "cell_id", "date", "label", "year",
    "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp",
}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def build_ntfp_features(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate NTFP prices to daily mean across districts (price is regional, not per-cell)."""
    prices_df = prices_df.copy()
    prices_df["date"] = pd.to_datetime(prices_df["date"])

    # Pivot: daily mean across districts per commodity
    agg = prices_df.groupby(["date", "commodity"])["price_rs_per_unit"].mean().unstack(fill_value=np.nan)
    agg.columns = [f"ntfp_{c}_price" for c in agg.columns]
    agg = agg.reset_index()

    # Add 7-day rolling mean + 30-day anomaly
    for c in ["ntfp_tendu_price", "ntfp_mahua_price"]:
        if c in agg.columns:
            agg[f"{c}_7d"] = agg[c].rolling(7, min_periods=1).mean()
            agg[f"{c}_30d_mean"] = agg[c].rolling(30, min_periods=1).mean()
            agg[f"{c}_anom"] = agg[c] - agg[f"{c}_30d_mean"]

    return agg


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v8 dataset...")
    df = pd.read_parquet(V8_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])
    log.info("  %d rows, %d cols", len(df), df.shape[1])

    log.info("Merging Hawkes (v9 stack)...")
    hawkes = pd.read_parquet(HAWKES_PATH)
    hawkes["date"] = pd.to_datetime(hawkes["date"])
    t0 = time.time()
    df = df.merge(hawkes, on=["cell_id", "date"], how="left")
    for c in [col for col in df.columns if col.startswith("hawkes_")]:
        df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)
    log.info("  Hawkes merge %.1fs", time.time() - t0)

    log.info("Merging calendar features...")
    cal = pd.read_parquet(CALENDAR_PATH)
    cal["date"] = pd.to_datetime(cal["date"])
    t0 = time.time()
    df = df.merge(cal, on="date", how="left")
    log.info("  Calendar merge %.1fs — added %d features", time.time() - t0,
             len([c for c in cal.columns if c != "date"]))

    log.info("Merging NTFP prices (synthetic — flagged in memory)...")
    if NTFP_PRICES_PATH.exists():
        prices = pd.read_parquet(NTFP_PRICES_PATH)
        ntfp_features = build_ntfp_features(prices)
        log.info("  NTFP aggregated: %s, %d cols", ntfp_features.shape, len(ntfp_features.columns))
        t0 = time.time()
        df = df.merge(ntfp_features, on="date", how="left")
        log.info("  NTFP merge %.1fs", time.time() - t0)
        # Fill NaN (pre-2014 or post-2025 gaps)
        for c in [col for col in ntfp_features.columns if col != "date"]:
            if c in df.columns:
                df[c] = df[c].fillna(df[c].median())
    else:
        log.warning("NTFP prices parquet not found — skipping")

    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and df[c].dtype.kind in "biufc"]
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    n_calendar = sum(1 for f in feats if f in set(cal.columns) and f != "date")
    n_ntfp = sum(1 for f in feats if f.startswith("ntfp_"))
    log.info("  Features: %d total (%d base + %d Hawkes + %d calendar + %d NTFP)",
             len(feats), len(feats) - n_hawkes - n_calendar - n_ntfp,
             n_hawkes, n_calendar, n_ntfp)

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

    log.info("Training v10_behavior_ignition...")
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
        "model": "v10_behavior_ignition",
        "n_features": int(len(feats)),
        "n_hawkes": int(n_hawkes),
        "n_calendar": int(n_calendar),
        "n_ntfp": int(n_ntfp),
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
    log.info("Top 25 features:\n%s", fi.head(25).to_string(index=False))

    # Count behavioral features in top 20
    top20 = fi.head(20)["feature"].tolist()
    n_behav_top20 = sum(1 for f in top20 if f.startswith("hawkes_") or
                        f.startswith("ntfp_") or
                        f in {"dow", "is_weekend", "is_tuesday", "is_thursday",
                              "days_to_holi", "is_holi_week", "is_holika_dahan",
                              "days_to_akshaya_tritiya", "is_akshaya_tritiya_week",
                              "is_bhagoria", "is_tendu_pre_burn", "is_mahua_collection"})
    log.info("Behavioral features in top 20: %d", n_behav_top20)

    log.info("\n=== v10_behavior_ignition FINAL ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f", roc, pr, best_f1)
    log.info("P@top-5%%=%.4f  R@top-5%%=%.4f  PerDayR@top-5%%=%.4f", prec_top5, recall_top5, perday_r5)

    log.info("\n=== Progression: v8 → v9 → v10 ===")
    log.info("v8  : ROC=0.8103 PR=0.0248 F1=0.0767 R@top-5%%=0.2811 PerDayR%%=0.1947")
    log.info("v9  : ROC=0.8626 PR=0.0383 F1=0.0928 R@top-5%%=0.3937 PerDayR%%=0.2898")
    log.info("v10 : ROC=%.4f PR=%.4f F1=%.4f R@top-5%%=%.4f PerDayR%%=%.4f",
             roc, pr, best_f1, recall_top5, perday_r5)
    log.info("Δ v9→v10: ROC=%+.4f PR=%+.4f R@top-5%%=%+.4f PerDayR%+.4f",
             roc - 0.8626, pr - 0.0383, recall_top5 - 0.3937, perday_r5 - 0.2898)

    gate = recall_top5 >= 0.3937 + 0.02  # v9 + 2pp
    if gate:
        log.info("\nVERDICT: PASS — behavioral features help. Proceed to v11 (news weak labels)")
    else:
        log.info("\nVERDICT: v10 ≤ v9 + 2pp. Calendar/NTFP saturated. Skip to v11.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
