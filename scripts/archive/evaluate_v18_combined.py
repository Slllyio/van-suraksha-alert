"""Pivot A v2 — Track T3 — Combined v18 + Hurdle blend evaluator (Day 7).

Evaluates four configurations on the 2025 honest hold-out:
  1. v17 baseline (from audit parquet)
  2. v18 alone (DW-augmented)
  3. v17 + Stage A blend (from T1 blend_winner)
  4. v18 + Stage A_v18 blend (T3 combined)

Pass criterion for T3:
  low-Hawkes (Hawkes_n ≤ 1) R@5% ≥ 0.10 AND overall R@5% ≥ 0.48 (BA-tiered)
  → ship as v19

Stage A_v18 should be retrained on v18 features minus Hawkes (handled by
running scripts/train_v17_hurdle_stage_a.py with --dataset v18 if added,
or by reusing the existing v17-trained Stage A — since DW features are
a tiny addition to the 107-feature base, we test both options here.)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V18_DATASET = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_dw" / "dataset.parquet"
V18_MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_dw" / "model.txt"
STAGE_A_V17 = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_hurdle_a" / "model.txt"
STAGE_A_V18 = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_hurdle_a" / "model.txt"
T1_BLEND_CONFIG = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_hurdle" / "blend_config.json"
AUDIT = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v19_combined"

HOLDOUT_START = pd.Timestamp("2025-02-01")
EPS = 1e-12

OVERALL_BA_FLOOR = 0.48      # T3 pass criterion (BA-tiered)
LOW_HAWKES_TARGET = 0.10     # T3 pass criterion (DBSCAN-strict)


def evaluate_score(df: pd.DataFrame, score_col: str) -> dict:
    """Per-day full-state top-5%, Hawkes-stratified recall."""
    overall_caught = overall_pos = 0
    low_caught = low_pos = 0
    cold_caught = cold_pos = 0
    high_caught = high_pos = 0
    overall_v17_caught = overall_v17_pos = 0
    perday_strict, perday_v17 = [], []
    for d, sub in df.groupby("date"):
        sub = sub.sort_values(score_col, ascending=False)
        n_top5 = max(1, int(len(sub) * 0.05))
        top = sub.head(n_top5)
        if sub["label_dbscan_ignition"].sum() > 0:
            perday_strict.append(int(top["label_dbscan_ignition"].sum())
                                  / int(sub["label_dbscan_ignition"].sum()))
        overall_caught += int(top["label_dbscan_ignition"].sum())
        overall_pos += int(sub["label_dbscan_ignition"].sum())
        if "label_v17" in sub.columns and sub["label_v17"].sum() > 0:
            perday_v17.append(int(top["label_v17"].sum()) / int(sub["label_v17"].sum()))
            overall_v17_caught += int(top["label_v17"].sum())
            overall_v17_pos += int(sub["label_v17"].sum())
        low_caught += int(top[(top["hawkes_n"] <= 1)
                              & (top["label_dbscan_ignition"] == 1)].shape[0])
        low_pos += int(sub[(sub["hawkes_n"] <= 1)
                           & (sub["label_dbscan_ignition"] == 1)].shape[0])
        cold_caught += int(top[(top["hawkes_n"] == 0)
                               & (top["label_dbscan_ignition"] == 1)].shape[0])
        cold_pos += int(sub[(sub["hawkes_n"] == 0)
                            & (sub["label_dbscan_ignition"] == 1)].shape[0])
        high_caught += int(top[(top["hawkes_n"] >= 3)
                               & (top["label_dbscan_ignition"] == 1)].shape[0])
        high_pos += int(sub[(sub["hawkes_n"] >= 3)
                            & (sub["label_dbscan_ignition"] == 1)].shape[0])
    return {
        "overall_dbscan_r5": overall_caught / overall_pos if overall_pos else 0.0,
        "overall_ba_tiered_r5": overall_v17_caught / overall_v17_pos if overall_v17_pos else 0.0,
        "low_hawkes_r5": low_caught / low_pos if low_pos else 0.0,
        "cold_start_r5": cold_caught / cold_pos if cold_pos else 0.0,
        "high_hawkes_r5": high_caught / high_pos if high_pos else 0.0,
        "perday_strict_r5": float(np.mean(perday_strict)) if perday_strict else 0.0,
        "perday_ba_tiered_r5": float(np.mean(perday_v17)) if perday_v17 else 0.0,
    }


def predict_with_model(model_path: Path, val: pd.DataFrame) -> np.ndarray:
    model = lgb.Booster(model_file=str(model_path))
    feats = model.feature_name()
    missing = [f for f in feats if f not in val.columns]
    if missing:
        log.warning("Model %s missing %d features in val: %s",
                    model_path.name, len(missing), missing[:5])
        return None
    return model.predict(val[feats].values)


def make_blend(p_a: np.ndarray, p_v: np.ndarray, variant: str) -> np.ndarray:
    p_a = np.clip(p_a, EPS, 1 - EPS)
    p_v = np.clip(p_v, EPS, 1 - EPS)
    if variant == "blend_geo_mean":
        return np.sqrt(p_a * p_v)
    if variant == "blend_geo_w0_3":
        return (p_a ** 0.3) * (p_v ** 0.7)
    if variant == "blend_geo_w0_5":
        return (p_a ** 0.5) * (p_v ** 0.5)
    if variant == "blend_geo_w0_7":
        return (p_a ** 0.7) * (p_v ** 0.3)
    if variant == "blend_harmonic":
        return 2.0 / (1.0 / p_a + 1.0 / p_v)
    raise ValueError(f"unknown variant: {variant}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not V18_MODEL.exists() or not V18_DATASET.exists():
        log.error("v18 model or dataset missing — train_v18_dynamic_world.py first")
        return 1

    log.info("Loading v18 dataset val...")
    df = pd.read_parquet(V18_DATASET)
    df["date"] = pd.to_datetime(df["date"])
    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Val: %d rows", len(val))

    log.info("Loading Hawkes_n from audit...")
    audit = pd.read_parquet(AUDIT, columns=["cell_id", "date", "hawkes_n_recent_10km_7d", "ignition_risk"])
    audit["date"] = pd.to_datetime(audit["date"])
    audit = audit.rename(columns={"hawkes_n_recent_10km_7d": "hawkes_n",
                                   "ignition_risk": "p_v17"})
    val = val.merge(audit, on=["cell_id", "date"], how="left")

    log.info("Predicting v18...")
    p_v18 = predict_with_model(V18_MODEL, val)
    val["p_v18"] = p_v18

    # Stage A — try v18-trained first, fall back to v17-trained
    if STAGE_A_V18.exists():
        log.info("Predicting Stage A_v18...")
        p_a = predict_with_model(STAGE_A_V18, val)
        stage_a_source = "v18_features"
    elif STAGE_A_V17.exists():
        log.info("Predicting Stage A_v17 (fallback)...")
        p_a = predict_with_model(STAGE_A_V17, val)
        stage_a_source = "v17_features"
    else:
        log.error("No Stage A model found")
        return 2
    val["p_a"] = p_a

    # Load winner blend variant from T1
    if T1_BLEND_CONFIG.exists():
        cfg = json.loads(T1_BLEND_CONFIG.read_text())
        winner_variant = cfg["variant"]
        log.info("Using T1 winner blend variant: %s", winner_variant)
    else:
        winner_variant = "blend_geo_w0_7"
        log.info("No T1 config — defaulting to %s", winner_variant)

    val["blend_v17_a"] = make_blend(val["p_a"].to_numpy(), val["p_v17"].to_numpy(), winner_variant)
    val["blend_v18_a"] = make_blend(val["p_a"].to_numpy(), val["p_v18"].to_numpy(), winner_variant)

    log.info("\n%-22s %-9s %-12s %-9s %-9s %-9s %-9s",
             "config", "DBSCAN", "BA_tiered", "low(<=1)", "cold(=0)", "high(>=3)", "perDay")
    rows = []
    for col in ["p_v17", "p_v18", "p_a", "blend_v17_a", "blend_v18_a"]:
        m = evaluate_score(val, col)
        rows.append({"config": col, "stage_a_source": stage_a_source, **m})
        log.info("%-22s %.4f    %.4f      %.4f    %.4f    %.4f    %.4f",
                 col, m["overall_dbscan_r5"], m["overall_ba_tiered_r5"],
                 m["low_hawkes_r5"], m["cold_start_r5"], m["high_hawkes_r5"],
                 m["perday_strict_r5"])

    # T3 decision: blend_v18_a's metrics vs target
    blend_v18 = next(r for r in rows if r["config"] == "blend_v18_a")
    v18_alone = next(r for r in rows if r["config"] == "p_v18")
    blend_v17 = next(r for r in rows if r["config"] == "blend_v17_a")

    pass_t3 = (blend_v18["low_hawkes_r5"] >= LOW_HAWKES_TARGET
               and blend_v18["overall_ba_tiered_r5"] >= OVERALL_BA_FLOOR)
    log.info("\n=== T3 DECISION ===")
    log.info("blend_v18_a: low_hawkes=%.4f (target %.2f), BA-tiered overall=%.4f (target %.2f)",
             blend_v18["low_hawkes_r5"], LOW_HAWKES_TARGET,
             blend_v18["overall_ba_tiered_r5"], OVERALL_BA_FLOOR)
    log.info("VERDICT: %s", "PASS — ship as v19" if pass_t3 else "FAIL — fall back to T2/T1 winner")

    # Cascade ship logic: prefer best non-failing config
    decision = {
        "winning_config": None,
        "reason": None,
        "metrics": {r["config"]: r for r in rows},
        "pass_t3": pass_t3,
    }
    if pass_t3:
        decision["winning_config"] = "v19_combined"
        decision["reason"] = "T3 pass criterion met"
    elif (v18_alone["low_hawkes_r5"] >= 0.07
          and v18_alone["overall_ba_tiered_r5"] >= 0.47):
        decision["winning_config"] = "v18_dw"
        decision["reason"] = "T2 pass: v18 alone clears low_hawkes ≥ 0.07 and BA-tiered ≥ 0.47"
    elif (blend_v17["low_hawkes_r5"] >= 0.08
          and blend_v17["overall_dbscan_r5"] >= v18_alone["overall_dbscan_r5"]):
        decision["winning_config"] = "v17_5_hurdle"
        decision["reason"] = "T1 hurdle blend clears low_hawkes ≥ 0.08"
    else:
        decision["winning_config"] = "v17_unchanged"
        decision["reason"] = "All variants fail their pass criteria; v17 stays in production"

    log.info("\nFINAL: ship %s — %s",
             decision["winning_config"], decision["reason"])

    (OUT_DIR / "decision.json").write_text(json.dumps(decision, indent=2, default=str))
    pd.DataFrame(rows).to_csv(OUT_DIR / "all_configs_eval.csv", index=False)
    log.info("Wrote: %s", (OUT_DIR / "decision.json").relative_to(ROOT))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
