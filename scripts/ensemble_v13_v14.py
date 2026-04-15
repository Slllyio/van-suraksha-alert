"""Phase 7 ensemble — average v13 (GLCM) + v14 (Hydro) predictions.

Hypothesis: v13 has best R@5% (40.18%), v14 has best PerDayR (32.6%). Their
feature importances overlap heavily but differ on GLCM vs hydro. A simple
rank-average may capture BOTH metrics.

Tests three blends: 0.5/0.5, geometric mean, and rank-mean (calibration-invariant).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, precision_score, recall_score, roc_auc_score,
)

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V13_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v13_glcm_ignition"
V14_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v14_hydro_ignition"
V8_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
HAWKES_PATH = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO_PATH = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v15_ensemble"

HOLDOUT_START = pd.Timestamp("2025-02-01")


def score_at_top_pct(val_y: np.ndarray, p: np.ndarray, top_pct: float = 5.0) -> tuple[float, float]:
    """Return (recall, precision) at top N% threshold."""
    thr = float(np.percentile(p, 100 - top_pct))
    pred = (p >= thr).astype(int)
    return float(recall_score(val_y, pred, zero_division=0)), float(precision_score(val_y, pred, zero_division=0))


def per_day_recall(dates: pd.Series, labels: np.ndarray, probs: np.ndarray, top_pct: float = 5.0) -> float:
    df = pd.DataFrame({"date_str": dates.dt.strftime("%Y-%m-%d"), "label": labels, "pred": probs})
    rec = []
    for _, sub in df.groupby("date_str"):
        if sub["label"].sum() == 0:
            continue
        n_top = max(1, int(len(sub) * top_pct / 100.0))
        ordered = sub.sort_values("pred", ascending=False)
        rec.append(int(ordered["label"].iloc[:n_top].sum()) / sub["label"].sum())
    return float(np.mean(rec)) if rec else 0.0


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v8 dataset + merging all feature layers...")
    df = pd.read_parquet(V8_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])

    for path, name in [(HAWKES_PATH, "Hawkes"), (GLCM_PATH, "GLCM"), (HYDRO_PATH, "Hydro")]:
        layer = pd.read_parquet(path)
        if "date" in layer.columns:
            layer["date"] = pd.to_datetime(layer["date"])
            df = df.merge(layer, on=["cell_id", "date"], how="left")
        else:
            df = df.merge(layer, on="cell_id", how="left")
        log.info("  %s merged: %d rows", name, len(df))

    # Fill NaN
    for c in df.columns:
        if c in ("cell_id", "date"):
            continue
        if df[c].dtype.kind in "biufc":
            fill = 50.0 if c == "hawkes_nearest_ign_14d_km" else df[c].median()
            df[c] = df[c].fillna(fill)

    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    val_y = val["label_dbscan_ignition"].values.astype(int)
    log.info("  Val: %d rows, %d ignitions", len(val), int(val_y.sum()))

    log.info("Loading v13 + v14 models...")
    m13 = lgb.Booster(model_file=str(V13_DIR / "model.txt"))
    m14 = lgb.Booster(model_file=str(V14_DIR / "model.txt"))

    feats_13 = m13.feature_name()
    feats_14 = m14.feature_name()
    log.info("  v13 features: %d, v14 features: %d", len(feats_13), len(feats_14))

    p13 = m13.predict(val[feats_13].values)
    p14 = m14.predict(val[feats_14].values)

    # Convert to ranks (percentile) for rank-based ensemble
    from scipy.stats import rankdata
    r13 = rankdata(p13, method="average") / len(p13)
    r14 = rankdata(p14, method="average") / len(p14)

    results = {}
    for name, p in [
        ("v13_alone", p13),
        ("v14_alone", p14),
        ("mean_prob_0.5_0.5", 0.5 * p13 + 0.5 * p14),
        ("geo_mean_prob", np.sqrt(np.maximum(p13, 1e-12) * np.maximum(p14, 1e-12))),
        ("rank_mean_0.5_0.5", 0.5 * r13 + 0.5 * r14),
        ("rank_max", np.maximum(r13, r14)),
        ("rank_min", np.minimum(r13, r14)),
    ]:
        roc = float(roc_auc_score(val_y, p))
        pr = float(average_precision_score(val_y, p))
        rec5, prec5 = score_at_top_pct(val_y, p, 5.0)
        rec10, _ = score_at_top_pct(val_y, p, 10.0)
        perday = per_day_recall(val["date"], val_y, p, 5.0)
        results[name] = {
            "roc_auc": roc, "pr_auc": pr,
            "recall_top5pct": rec5, "precision_top5pct": prec5,
            "recall_top10pct": rec10,
            "perday_recall_top5pct": perday,
        }
        log.info("  %-22s ROC=%.4f PR=%.4f R@5%%=%.4f PerDayR%%=%.4f",
                 name, roc, pr, rec5, perday)

    (OUT_DIR / "ensemble_results.json").write_text(json.dumps(results, indent=2))
    log.info("\nSaved: %s", (OUT_DIR / "ensemble_results.json").relative_to(ROOT))

    log.info("\n=== BEST PER METRIC ===")
    for metric in ["recall_top5pct", "perday_recall_top5pct", "roc_auc", "pr_auc"]:
        best_name = max(results.keys(), key=lambda k: results[k][metric])
        log.info("  %s: %s = %.4f", metric, best_name, results[best_name][metric])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
