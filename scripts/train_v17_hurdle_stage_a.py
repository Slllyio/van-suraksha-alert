"""Pivot A v2 — Track T1 — Hurdle Stage A Bernoulli classifier.

Trains a strict-binary "did anything ignite in this cell-day?" classifier
using v17's feature set MINUS the 4 Hawkes features. Stage B is v17 itself
(loaded externally). The blend of Stage A × v17 is evaluated separately
in scripts/evaluate_v17_hurdle_blend.py.

Why no Hawkes here: forcing Stage A to learn presence/absence WITHOUT
neighbour-fire history makes it specialise on cold-start ignition cells,
exactly the regime where v17 is near-random (5.9% R@top-5%).

Differs structurally from prior failed origination model (commit d134e18):
- Prior: per-cell ranking with custom sigmoid-handoff ensemble → fail.
- Hurdle: presence/absence binary classifier with geometric-mean blend.
  The blend rewards agreement between Stage A and v17, not handoff.

Inputs (same as v17, minus the Hawkes merge):
  outputs/predictive_fire_risk/predictive_v8_ignition_dbscan/dataset.parquet
  data_lake/human_activity/glcm_texture_per_cell.parquet
  data_lake/human_activity/hydro_features_per_cell.parquet

Output:
  outputs/predictive_fire_risk/predictive_v17_hurdle_a/{model.txt,
                                                        results.json,
                                                        feature_importance.csv}
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
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO_PATH = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_hurdle_a"

# Same exclusions as v17 trainer (no Hawkes features added to df at all)
LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}
HOLDOUT_START = pd.Timestamp("2025-02-01")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v8 base dataset (84 base features + DBSCAN binary label)...")
    ds = pd.read_parquet(V8_DIR / "dataset.parquet")
    ds["date"] = pd.to_datetime(ds["date"])
    log.info("  %d rows × %d cols", len(ds), len(ds.columns))

    df = ds.copy()

    log.info("Merging GLCM (texture features)...")
    if GLCM_PATH.exists():
        glcm = pd.read_parquet(GLCM_PATH)
        df = df.merge(glcm, on="cell_id", how="left")
        for c in [col for col in glcm.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())

    log.info("Merging Hydro (drainage topology features)...")
    if HYDRO_PATH.exists():
        hydro = pd.read_parquet(HYDRO_PATH)
        df = df.merge(hydro, on="cell_id", how="left")
        for c in [col for col in hydro.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())

    # CRITICAL: do NOT load Hawkes parquet. Stage A is forced to predict
    # ignition presence WITHOUT neighbour-fire history.
    feats = [c for c in df.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and not c.startswith("hawkes_")
             and df[c].dtype.kind in "biufc"]
    n_glcm = sum(1 for f in feats if f.startswith("glcm_") or f.startswith("ndvi_"))
    n_hydro = sum(1 for f in feats if f.startswith("hydro_"))
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    log.info("  Stage A features: %d total (%d GLCM/NDVI + %d Hydro + %d Hawkes [must be 0])",
             len(feats), n_glcm, n_hydro, n_hawkes)
    assert n_hawkes == 0, "Hawkes features leaked into Stage A — abort"

    train = df[df["date"] < HOLDOUT_START].reset_index(drop=True)
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Train: %d rows (%d pos, rate %.3f%%)",
             len(train), int(train["label_dbscan_ignition"].sum()),
             100 * train["label_dbscan_ignition"].mean())
    log.info("  Val:   %d rows (%d pos, rate %.3f%%)",
             len(val), int(val["label_dbscan_ignition"].sum()),
             100 * val["label_dbscan_ignition"].mean())

    dtrain = lgb.Dataset(train[feats].values,
                         label=train["label_dbscan_ignition"].values,
                         feature_name=feats)
    dval = lgb.Dataset(val[feats].values,
                       label=val["label_dbscan_ignition"].values,
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

    log.info("Training Stage A...")
    t0 = time.time()
    model = lgb.train(
        params, dtrain, num_boost_round=3000,
        valid_sets=[dtrain, dval], valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(100)],
    )
    log.info("Training done in %.0fs, best_iter=%d",
             time.time() - t0, model.best_iteration)
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
    per_day = []
    for _, sub in eval_df.groupby("date_str"):
        if sub["label_dbscan_ignition"].sum() == 0:
            continue
        n_top5 = max(1, int(len(sub) * 0.05))
        ordered = sub.sort_values("pred", ascending=False)
        recall = (int(ordered["label_dbscan_ignition"].iloc[:n_top5].sum())
                  / sub["label_dbscan_ignition"].sum())
        per_day.append(recall)
    perday_r5 = float(np.mean(per_day)) if per_day else 0.0

    results = {
        "model": "v17_hurdle_stage_a",
        "n_features": int(len(feats)),
        "n_hawkes_features": int(n_hawkes),  # MUST be 0
        "best_iteration": int(model.best_iteration),
        "label_strategy": "strict_binary_dbscan_ignition",
        "weights": "uniform_1.0",
        "holdout_start": HOLDOUT_START.strftime("%Y-%m-%d"),
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "n_train_pos": int(train["label_dbscan_ignition"].sum()),
        "n_val_pos": int(val["label_dbscan_ignition"].sum()),
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

    # Sanity check per plan's pass criterion: top 30 must include at least
    # one anthropogenic + one weather feature; not weather-only collapse.
    top30 = fi.head(30)
    has_anthro = any(f.startswith("ha_") or f.startswith("lc_")
                     for f in top30["feature"])
    has_weather = any(f.startswith("wx_") or f in {"ffmc", "dmc", "dc",
                                                   "isi", "bui", "fwi"}
                      for f in top30["feature"])
    log.info("\nFeature importance sanity:")
    log.info("  Top-30 includes ≥1 anthropogenic feature: %s", has_anthro)
    log.info("  Top-30 includes ≥1 weather feature: %s", has_weather)
    log.info("  Top 15 by gain:")
    for _, r in fi.head(15).iterrows():
        log.info("    %-40s gain=%12.0f split=%4d", r["feature"], r["gain"], r["split"])

    log.info("\n=== Stage A FINAL (no Hawkes) ===")
    log.info("ROC=%.4f PR=%.4f F1=%.4f R@5%%=%.4f PerDayR%%=%.4f",
             roc, pr, best_f1, rec5, perday_r5)
    log.info("Pass criterion: PR-AUC > 0.005 AND top-30 has both anthropogenic & weather")
    if pr > 0.005 and has_anthro and has_weather:
        log.info("VERDICT: PASS — proceed to Day 2 blend evaluation")
    else:
        log.info("VERDICT: FAIL — Stage A is too weak or collapsed; revisit before blend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
