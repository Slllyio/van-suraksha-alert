"""Task 2a — Diagnostic on low-Hawkes cells (the 77% miss zone).

77% of DBSCAN ignitions land in cells where no recent nearby ignitions exist
(hawkes_n_recent_10km_7d ≤ 1). v17's Hawkes-dominant feature set can't see
these. Are there any OTHER signals that predict these new outbreaks?

Pipeline:
  1. Load v17 audit per-cell-date
  2. Subset to low-Hawkes rows (count <= 1)
  3. Compute v17 recall @ various thresholds on this subset alone
  4. Train ablation model: features EXCEPT hawkes_* → see which features matter
  5. Report feature importances specific to new-outbreak prediction
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V8_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
V17_MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "model.txt"
HAWKES = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
GLCM = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
AUDIT_PCD = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"

HOLDOUT_START = pd.Timestamp("2025-02-01")
LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}


def build_full_dataset():
    log.info("Loading v8 + Hawkes + GLCM + Hydro...")
    ds = pd.read_parquet(V8_DIR / "dataset.parquet")
    ds["date"] = pd.to_datetime(ds["date"])
    hk = pd.read_parquet(HAWKES)
    hk["date"] = pd.to_datetime(hk["date"])
    ds = ds.merge(hk, on=["cell_id", "date"], how="left")
    for c in [col for col in ds.columns if col.startswith("hawkes_")]:
        ds[c] = ds[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)
    g = pd.read_parquet(GLCM)
    ds = ds.merge(g, on="cell_id", how="left")
    for c in [col for col in g.columns if col != "cell_id"]:
        ds[c] = ds[c].fillna(ds[c].median())
    h = pd.read_parquet(HYDRO)
    ds = ds.merge(h, on="cell_id", how="left")
    for c in [col for col in h.columns if col != "cell_id"]:
        ds[c] = ds[c].fillna(ds[c].median())
    return ds


def main() -> int:
    log.info("=== LOW-HAWKES NEW-OUTBREAK DIAGNOSTIC ===\n")

    audit = pd.read_parquet(AUDIT_PCD)
    audit["date"] = pd.to_datetime(audit["date"])
    log.info("Loaded audit: %d val rows", len(audit))

    # ---- Diagnostic 1: what fraction of ignitions happen in low-Hawkes cells?
    log.info("\n--- Stage 1: Ignition distribution by Hawkes intensity ---")
    audit["hawkes_bucket"] = pd.cut(audit["hawkes_n_recent_10km_7d"],
                                      bins=[-0.1, 0, 1, 3, 10, 1e6],
                                      labels=["0", "1", "2-3", "4-10", "10+"])
    by_bucket = audit.groupby("hawkes_bucket", observed=False).agg(
        n_cells=("cell_id", "count"),
        n_ignitions=("label_dbscan_ignition", "sum"),
        mean_v17_risk=("ignition_risk", "mean"),
        p95_v17_risk=("ignition_risk", lambda s: s.quantile(0.95)),
    ).reset_index()
    by_bucket["ignition_rate_pct"] = by_bucket["n_ignitions"] / by_bucket["n_cells"] * 100
    by_bucket["pct_of_all_ignitions"] = by_bucket["n_ignitions"] / audit["label_dbscan_ignition"].sum() * 100
    log.info("\n%s", by_bucket.to_string(index=False))

    low_hawkes_pct_ign = by_bucket[by_bucket["hawkes_bucket"].astype(str).isin(["0", "1"])]["pct_of_all_ignitions"].sum()
    log.info("\n  >>> %.1f%% of DBSCAN ignitions occur in LOW-HAWKES cells (count <= 1)", low_hawkes_pct_ign)

    # ---- Diagnostic 2: v17 recall on low-Hawkes subset
    log.info("\n--- Stage 2: v17 recall on low-Hawkes subset alone ---")
    low_h = audit[audit["hawkes_n_recent_10km_7d"] <= 1].copy()
    low_h["within_day_rank_subset"] = low_h.groupby("date")["ignition_risk"].rank(pct=True)
    for thr in [0.50, 0.80, 0.90, 0.95, 0.99]:
        alerts = low_h[low_h["within_day_rank_subset"] >= thr]
        hits = alerts["label_dbscan_ignition"].sum()
        total = low_h["label_dbscan_ignition"].sum()
        recall = hits / total if total else 0
        log.info(f"  top-{(1-thr)*100:.0f}% of low-Hawkes cells: alerts={len(alerts):6d}  recall={recall:.1%}")

    # ---- Diagnostic 3: build a fresh LightGBM on low-Hawkes only, see which features matter
    log.info("\n--- Stage 3: Training ablation model on low-Hawkes only ---")
    ds = build_full_dataset()
    # Train on low-Hawkes rows pre-2025-02-01; val on low-Hawkes rows 2025-02-01 onwards
    low_mask = ds["hawkes_n_recent_10km_7d"] <= 1
    log.info("  Low-Hawkes total rows: %d / %d (%.0f%%)", low_mask.sum(), len(ds), 100 * low_mask.mean())
    train = ds[low_mask & (ds["date"] < HOLDOUT_START)].reset_index(drop=True)
    val = ds[low_mask & (ds["date"] >= HOLDOUT_START)].reset_index(drop=True)
    log.info("  Train: %d (%d pos), Val: %d (%d pos)",
             len(train), int(train["label_dbscan_ignition"].sum()),
             len(val), int(val["label_dbscan_ignition"].sum()))

    # Feature list (exclude Hawkes — what signal remains?)
    feats = [c for c in ds.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and not c.startswith("hawkes_")  # ABLATE Hawkes
             and ds[c].dtype.kind in "biufc"]
    log.info("  Features used (no Hawkes): %d", len(feats))

    dtrain = lgb.Dataset(train[feats].values, label=train["label_dbscan_ignition"].values, feature_name=feats)
    dval = lgb.Dataset(val[feats].values, label=val["label_dbscan_ignition"].values, reference=dtrain)
    params = {
        "objective": "binary", "metric": ["average_precision", "auc"],
        "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
        "feature_fraction": 0.85, "bagging_fraction": 0.85, "bagging_freq": 5,
        "is_unbalance": True, "verbose": -1,
    }
    model = lgb.train(params, dtrain, num_boost_round=1500,
                       valid_sets=[dval], valid_names=["val"],
                       callbacks=[lgb.early_stopping(75), lgb.log_evaluation(200)])

    # Predict + per-day recall
    val["risk_no_hawkes"] = model.predict(val[feats].values, num_iteration=model.best_iteration)
    roc = roc_auc_score(val["label_dbscan_ignition"], val["risk_no_hawkes"])
    pr = average_precision_score(val["label_dbscan_ignition"], val["risk_no_hawkes"])
    log.info("\n  Low-Hawkes ablation model on val: ROC=%.4f  PR=%.4f  best_iter=%d",
             roc, pr, model.best_iteration)

    # Per-date recall
    val["rank_within_day"] = val.groupby("date")["risk_no_hawkes"].rank(pct=True)
    top5 = val[val["rank_within_day"] >= 0.95]
    r5 = top5["label_dbscan_ignition"].sum() / max(val["label_dbscan_ignition"].sum(), 1)
    log.info("  Low-Hawkes top-5%% recall (no-Hawkes model): %.1%%", r5 * 100)

    # v17 recall on same subset for comparison
    v17_top5_low = low_h[low_h["within_day_rank_subset"] >= 0.95]
    v17_r5_low = v17_top5_low["label_dbscan_ignition"].sum() / max(low_h["label_dbscan_ignition"].sum(), 1)
    log.info("  Low-Hawkes top-5%% recall (v17 WITH Hawkes):  %.1%%", v17_r5_low * 100)

    # Feature importance
    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
        "split": model.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False).head(25)
    log.info("\n--- Top 25 features for LOW-HAWKES ignitions (no Hawkes available) ---\n%s",
             fi.to_string(index=False))

    # Save outputs
    out_dir = ROOT / "data_lake" / "audits"
    by_bucket.to_csv(out_dir / "low_hawkes_distribution.csv", index=False)
    fi.to_csv(out_dir / "low_hawkes_feature_importance.csv", index=False)
    log.info("\nSaved:")
    log.info("  %s", (out_dir / "low_hawkes_distribution.csv").relative_to(ROOT))
    log.info("  %s", (out_dir / "low_hawkes_feature_importance.csv").relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
