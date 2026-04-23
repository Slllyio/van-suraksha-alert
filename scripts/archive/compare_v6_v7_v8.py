"""Plan A.4 — Honest head-to-head: v6e_live vs v7_ignition vs v8_ignition_dbscan.

Score all three models on the same 2025-02-01 → 2025-05-29 hold-out, with two
definitions of correctness:
  (a) v6e SPREAD label (52% positive) — what v6e was trained on
  (b) DBSCAN ignition label (0.6% positive) — operational "where will today's
      new fire start" question

Also compute per-day recall@top-5% on TRUE ignitions (the operational metric
forest officers care about).

Output: outputs/predictive_fire_risk/_comparison_v6_v7_v8.json
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
    average_precision_score, f1_score, precision_score, recall_score, roc_auc_score,
)

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V6E_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live"
V7_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v7_ignition"
V8_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
OUT_PATH = ROOT / "outputs" / "predictive_fire_risk" / "_comparison_v6_v7_v8.json"

HOLDOUT_START = pd.Timestamp("2025-02-01")

LEAKAGE = {
    "days_since_last_fire", "fire_last_7d",
    "neighbor_fire_7d", "neighbor_fire_yesterday",
}
NON_FEATURES = {
    "cell_id", "date", "label", "year",
    "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp",
}


def metrics(y: np.ndarray, p: np.ndarray, label_name: str) -> dict:
    if y.sum() == 0:
        return {"label": label_name, "n": int(len(y)), "n_pos": 0, "skipped": "no positives"}
    roc = float(roc_auc_score(y, p))
    pr = float(average_precision_score(y, p))
    best_f1, best_t = 0.0, 0.5
    for t in np.arange(0.01, 0.99, 0.01):
        pred = (p >= t).astype(int)
        f1 = f1_score(y, pred, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = float(f1), float(t)
    p95 = float(np.percentile(p, 95))
    pred5 = (p >= p95).astype(int)
    return {
        "label": label_name,
        "n": int(len(y)),
        "n_pos": int(y.sum()),
        "pos_rate": float(y.mean()),
        "roc_auc": roc,
        "pr_auc": pr,
        "best_f1": best_f1,
        "best_f1_threshold": best_t,
        "precision_top5pct": float(precision_score(y, pred5, zero_division=0)),
        "recall_top5pct": float(recall_score(y, pred5, zero_division=0)),
    }


def per_day_new_ignition_recall(df: pd.DataFrame, p: np.ndarray, label_col: str = "label_dbscan_ignition") -> dict:
    """Per-day rank recall on TRUE ignitions: how many of today's true ignitions
    rank in top-5% of today's predictions?
    """
    eval_df = df[["date", label_col]].copy()
    eval_df["pred"] = p
    eval_df["date_str"] = eval_df["date"].dt.strftime("%Y-%m-%d")
    rec5_per_day = []
    rec1_per_day = []
    for date, sub in eval_df.groupby("date_str"):
        if sub[label_col].sum() == 0:
            continue
        n = len(sub)
        top5 = int(n * 0.05)
        top1 = int(n * 0.01)
        ordered = sub.sort_values("pred", ascending=False)
        true_pos_top5 = int(ordered[label_col].iloc[:top5].sum())
        true_pos_top1 = int(ordered[label_col].iloc[:top1].sum())
        n_true = int(sub[label_col].sum())
        rec5_per_day.append(true_pos_top5 / n_true)
        rec1_per_day.append(true_pos_top1 / n_true)
    return {
        "n_days_with_ignitions": len(rec5_per_day),
        "macro_recall_top1pct": float(np.mean(rec1_per_day)) if rec1_per_day else 0.0,
        "macro_recall_top5pct": float(np.mean(rec5_per_day)) if rec5_per_day else 0.0,
    }


def main() -> int:
    log.info("Loading extended dataset (v8)...")
    df = pd.read_parquet(V8_DIR / "dataset.parquet")
    df["date"] = pd.to_datetime(df["date"])
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Val: %d rows", len(val))
    log.info("  Spread positives:    %d (%.2f%%)", int(val["label"].sum()), 100 * val["label"].mean())
    log.info("  Ignition positives:  %d (%.3f%%)",
             int(val["label_dbscan_ignition"].sum()), 100 * val["label_dbscan_ignition"].mean())

    feats_v6e = [c for c in val.columns
                 if c not in NON_FEATURES and val[c].dtype.kind in "biufc"]
    feats_v7v8 = [c for c in feats_v6e if c not in LEAKAGE]
    log.info("  v6e feature count: %d, v7/v8 feature count: %d (no leakage)",
             len(feats_v6e), len(feats_v7v8))

    results = {}

    # v6e_live
    log.info("\n--- v6e_live ---")
    v6e = lgb.Booster(model_file=str(V6E_DIR / "model.lgbm"))
    v6e_features = v6e.feature_name()
    log.info("  v6e expects %d features", len(v6e_features))
    # Score with v6e_features in correct order
    v6e_p = v6e.predict(val[v6e_features].values)
    results["v6e_live"] = {
        "vs_spread_label": metrics(val["label"].values, v6e_p, "spread"),
        "vs_dbscan_ignition_label": metrics(val["label_dbscan_ignition"].values, v6e_p, "ignition_dbscan"),
        "per_day_ignition_recall": per_day_new_ignition_recall(val, v6e_p),
    }

    # v7_ignition
    log.info("\n--- v7_ignition ---")
    v7 = lgb.Booster(model_file=str(V7_DIR / "model.txt"))
    # v7 was trained without explicit feature names — use feature_list.json
    v7_features = json.loads((V7_DIR / "feature_list.json").read_text())
    log.info("  v7 expects %d features (from feature_list.json)", len(v7_features))
    v7_p = v7.predict(val[v7_features].values)
    results["v7_ignition"] = {
        "vs_spread_label": metrics(val["label"].values, v7_p, "spread"),
        "vs_dbscan_ignition_label": metrics(val["label_dbscan_ignition"].values, v7_p, "ignition_dbscan"),
        "per_day_ignition_recall": per_day_new_ignition_recall(val, v7_p),
    }

    # v8_ignition_dbscan
    log.info("\n--- v8_ignition_dbscan ---")
    v8_path = V8_DIR / "model.txt"
    if not v8_path.exists():
        log.warning("v8 model not yet trained — skipping")
    else:
        v8 = lgb.Booster(model_file=str(v8_path))
        v8_features = v8.feature_name()
        log.info("  v8 expects %d features", len(v8_features))
        v8_p = v8.predict(val[v8_features].values)
        results["v8_ignition_dbscan"] = {
            "vs_spread_label": metrics(val["label"].values, v8_p, "spread"),
            "vs_dbscan_ignition_label": metrics(val["label_dbscan_ignition"].values, v8_p, "ignition_dbscan"),
            "per_day_ignition_recall": per_day_new_ignition_recall(val, v8_p),
        }

    # Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, indent=2))
    log.info("\nSaved: %s", OUT_PATH.relative_to(ROOT))

    # Print head-to-head table
    log.info("\n=== HEAD-TO-HEAD ON 765K VAL HOLD-OUT ===")
    log.info("\nOn TRUE IGNITION labels (operational task, 0.5%% positive rate):")
    log.info("%-25s %8s %8s %8s %12s %12s %15s",
             "Model", "ROC", "PR", "F1", "P@top5%", "R@top5%", "PerDayR@5%")
    for name in ["v6e_live", "v7_ignition", "v8_ignition_dbscan"]:
        if name not in results:
            continue
        m = results[name]["vs_dbscan_ignition_label"]
        if "skipped" in m:
            continue
        pd_r = results[name]["per_day_ignition_recall"]["macro_recall_top5pct"]
        log.info("%-25s %.4f   %.4f   %.4f   %.4f       %.4f       %.4f",
                 name, m["roc_auc"], m["pr_auc"], m["best_f1"],
                 m["precision_top5pct"], m["recall_top5pct"], pd_r)

    log.info("\nOn SPREAD labels (what v6e was trained on, 36%% positive rate):")
    log.info("%-25s %8s %8s %8s", "Model", "ROC", "PR", "F1")
    for name in ["v6e_live", "v7_ignition", "v8_ignition_dbscan"]:
        if name not in results:
            continue
        m = results[name]["vs_spread_label"]
        log.info("%-25s %.4f   %.4f   %.4f", name, m["roc_auc"], m["pr_auc"], m["best_f1"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
