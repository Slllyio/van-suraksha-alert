"""Move A — v15 × v17 ensemble experiment.

v15 = sqrt(prob_v13_glcm × prob_v14_hydro)   [trained on DBSCAN labels]
v17 = single LightGBM trained on BA-augmented tiered PU labels

Tests whether combining them with 7 ensemble strategies produces a further
operational lift. Evaluates on BOTH label sets (DBSCAN and BA-PU) to avoid
label-mismatch artefacts.

Stopping rule: if best ensemble beats v17 alone by >= 1 pp R@top-5% on v17's
BA-PU labels, ship as v17.1 (new production).

Usage:
  python scripts/ensemble_v15_v17.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.metrics import (
    average_precision_score, precision_score, recall_score, roc_auc_score,
)

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V13 = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v13_glcm_ignition"
V14 = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v14_hydro_ignition"
V17 = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu"
V8 = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
HAWKES = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
GLCM = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
TIERED = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"
OUT = ROOT / "outputs" / "predictive_fire_risk" / "ensemble_v15_v17"

HOLDOUT_START = pd.Timestamp("2025-02-01")


def score_top_pct(y: np.ndarray, p: np.ndarray, pct: float = 5.0) -> tuple[float, float]:
    thr = float(np.percentile(p, 100 - pct))
    pred = (p >= thr).astype(int)
    return (
        float(recall_score(y, pred, zero_division=0)),
        float(precision_score(y, pred, zero_division=0)),
    )


def per_day_recall(dates: pd.Series, y: np.ndarray, p: np.ndarray, pct: float = 5.0) -> float:
    df = pd.DataFrame({"date_str": dates.dt.strftime("%Y-%m-%d"), "y": y, "p": p})
    recs = []
    for _, sub in df.groupby("date_str"):
        if sub["y"].sum() == 0:
            continue
        n_top = max(1, int(len(sub) * pct / 100.0))
        ordered = sub.sort_values("p", ascending=False)
        recs.append(int(ordered["y"].iloc[:n_top].sum()) / sub["y"].sum())
    return float(np.mean(recs)) if recs else 0.0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    log.info("Loading v8 base dataset + Hawkes + GLCM + Hydro...")
    df = pd.read_parquet(V8 / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])

    hawkes = pd.read_parquet(HAWKES)
    hawkes["date"] = pd.to_datetime(hawkes["date"])
    df = df.merge(hawkes, on=["cell_id", "date"], how="left")
    for c in [col for col in df.columns if col.startswith("hawkes_")]:
        df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    glcm = pd.read_parquet(GLCM)
    df = df.merge(glcm, on="cell_id", how="left")
    for c in [col for col in glcm.columns if col != "cell_id"]:
        df[c] = df[c].fillna(df[c].median())

    hydro = pd.read_parquet(HYDRO)
    df = df.merge(hydro, on="cell_id", how="left")
    for c in [col for col in hydro.columns if col != "cell_id"]:
        df[c] = df[c].fillna(df[c].median())

    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Val: %d rows", len(val))

    log.info("Loading v13, v14, v17 models...")
    m13 = lgb.Booster(model_file=str(V13 / "model.txt"))
    m14 = lgb.Booster(model_file=str(V14 / "model.txt"))
    m17 = lgb.Booster(model_file=str(V17 / "model.txt"))

    p13 = m13.predict(val[m13.feature_name()].values)
    p14 = m14.predict(val[m14.feature_name()].values)
    p17 = m17.predict(val[m17.feature_name()].values)

    # v15 = geo-mean(v13, v14)
    p15 = np.sqrt(np.maximum(p13, 1e-12) * np.maximum(p14, 1e-12))

    log.info("  v13 range [%.4f, %.4f], v14 range [%.4f, %.4f]", p13.min(), p13.max(), p14.min(), p14.max())
    log.info("  v15 (geo) range [%.4f, %.4f], v17 range [%.4f, %.4f]",
             p15.min(), p15.max(), p17.min(), p17.max())

    # Build two label sets
    y_dbscan = val["label_dbscan_ignition"].values.astype(int)
    log.info("DBSCAN positives in val: %d", int(y_dbscan.sum()))

    # v17 labels (GOLD/SILVER/BRONZE positives)
    tiered = pd.read_parquet(TIERED)
    tiered["ignition_date"] = pd.to_datetime(tiered["ignition_date"])
    tiered_labels = tiered.groupby(["cell_id", "ignition_date"]).size().reset_index(name="n")
    tiered_labels = tiered_labels.rename(columns={"ignition_date": "date"})
    val_with_v17 = val[["cell_id", "date"]].merge(tiered_labels, on=["cell_id", "date"], how="left")
    y_v17 = (val_with_v17["n"].fillna(0) > 0).astype(int).values
    log.info("v17 BA-augmented positives in val: %d", int(y_v17.sum()))

    # Rank versions for rank-based ensembles
    r15 = rankdata(p15, method="average") / len(p15)
    r17 = rankdata(p17, method="average") / len(p17)

    strategies = {
        "v15_alone": p15,
        "v17_alone": p17,
        "mean_prob_0.5_0.5": 0.5 * p15 + 0.5 * p17,
        "geo_mean": np.sqrt(np.maximum(p15, 1e-12) * np.maximum(p17, 1e-12)),
        "rank_mean": 0.5 * r15 + 0.5 * r17,
        "rank_max": np.maximum(r15, r17),
        "rank_min": np.minimum(r15, r17),
        "geo_mean_3way_v13_v14_v17": np.cbrt(
            np.maximum(p13, 1e-12) * np.maximum(p14, 1e-12) * np.maximum(p17, 1e-12)
        ),
    }

    results = {}
    for y_name, y in [("dbscan_labels", y_dbscan), ("v17_ba_labels", y_v17)]:
        log.info("\n=== Evaluating on %s (n_pos=%d) ===", y_name, int(y.sum()))
        results[y_name] = {}
        for name, p in strategies.items():
            roc = float(roc_auc_score(y, p))
            pr = float(average_precision_score(y, p))
            rec5, prec5 = score_top_pct(y, p, 5.0)
            perday = per_day_recall(val["date"], y, p, 5.0)
            results[y_name][name] = {
                "roc_auc": roc, "pr_auc": pr,
                "recall_top5pct": rec5, "precision_top5pct": prec5,
                "perday_recall_top5pct": perday,
            }
            log.info("  %-30s ROC=%.4f PR=%.4f R@5%%=%.4f PerDayR%%=%.4f",
                     name, roc, pr, rec5, perday)

    (OUT / "ensemble_results.json").write_text(json.dumps(results, indent=2))
    log.info("\nSaved: %s", (OUT / "ensemble_results.json").relative_to(ROOT))

    log.info("\n=== BEST PER METRIC (on v17 BA labels — the operational label set) ===")
    for metric in ["roc_auc", "pr_auc", "recall_top5pct", "perday_recall_top5pct"]:
        best = max(results["v17_ba_labels"].keys(), key=lambda k: results["v17_ba_labels"][k][metric])
        v17_val = results["v17_ba_labels"]["v17_alone"][metric]
        best_val = results["v17_ba_labels"][best][metric]
        delta = best_val - v17_val
        marker = "  *** beats v17 alone ***" if delta > 0 else ""
        log.info("  %s:  %s = %.4f  (v17_alone=%.4f, Δ=%+.4f)%s",
                 metric, best, best_val, v17_val, delta, marker)

    log.info("\n=== STOPPING RULE ===")
    v17_r5 = results["v17_ba_labels"]["v17_alone"]["recall_top5pct"]
    best_r5_name = max(results["v17_ba_labels"].keys(),
                       key=lambda k: results["v17_ba_labels"][k]["recall_top5pct"])
    best_r5_val = results["v17_ba_labels"][best_r5_name]["recall_top5pct"]
    delta_pp = (best_r5_val - v17_r5) * 100
    if delta_pp >= 1.0:
        log.info("  SHIP — best ensemble '%s' beats v17 by %.2f pp R@top-5%% (v17=%.4f, best=%.4f)",
                 best_r5_name, delta_pp, v17_r5, best_r5_val)
    else:
        log.info("  SKIP — best ensemble '%s' only beats v17 by %.2f pp (< 1 pp threshold); keep v17 alone",
                 best_r5_name, delta_pp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
