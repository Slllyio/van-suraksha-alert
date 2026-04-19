"""Pivot A v2 — Track T1 — Hurdle Blend Evaluator (Day 2).

Loads:
  - v17 raw scores from data_lake/audits/v17_audit_per_cell_date.parquet
    (col: ignition_risk → 'p_v17')
  - Stage A predictions on the same val rows by re-scoring with the model
    saved at outputs/predictive_fire_risk/predictive_v17_hurdle_a/model.txt
  - Hawkes_n per cell-date (already in audit) for low/high-Hawkes stratification

Computes 5 blend variants of (p_v17, p_a):
  geo_mean        sqrt(p_a * p_v17)
  geo_w0.3        p_a^0.3 * p_v17^0.7
  geo_w0.5        sqrt(p_a * p_v17)            == geo_mean
  geo_w0.7        p_a^0.7 * p_v17^0.3
  harmonic        2 / (1/p_a + 1/p_v17)

For each variant: re-rank within day → compute
  - overall R@top-5%
  - low-Hawkes R@top-5% (Hawkes_n ≤ 1)
  - high-Hawkes R@top-5% (Hawkes_n ≥ 3)
  - per-day R@top-5% (mean over prediction Thursdays)

Pick winner by max(low_hawkes_r5) subject to overall_r5 ≥ 0.47.
Save winning blend config + per-cell predictions.
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
AUDIT = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
V8_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO_PATH = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
STAGE_A_MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_hurdle_a" / "model.txt"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_hurdle"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PARQUET = ROOT / "data_lake" / "audits" / "v17_hurdle_blend_results.parquet"

LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}
HOLDOUT_START = pd.Timestamp("2025-02-01")

OVERALL_FLOOR = 0.47        # hard gate per plan
LOW_HAWKES_TARGET = 0.08    # T1 ship criterion
EPS = 1e-12


def load_val_features() -> pd.DataFrame:
    """Rebuild Stage A's val matrix exactly the way Stage A trainer did."""
    log.info("Loading v8 base dataset...")
    ds = pd.read_parquet(V8_DIR / "dataset.parquet")
    ds["date"] = pd.to_datetime(ds["date"])

    df = ds.copy()
    if GLCM_PATH.exists():
        glcm = pd.read_parquet(GLCM_PATH)
        df = df.merge(glcm, on="cell_id", how="left")
        for c in [col for col in glcm.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())
    if HYDRO_PATH.exists():
        hydro = pd.read_parquet(HYDRO_PATH)
        df = df.merge(hydro, on="cell_id", how="left")
        for c in [col for col in hydro.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())

    val = df[df["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("  Val: %d rows (%d pos)", len(val), int(val["label_dbscan_ignition"].sum()))
    return val


def predict_stage_a(val: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    log.info("Loading Stage A model...")
    model = lgb.Booster(model_file=str(STAGE_A_MODEL))
    feats = model.feature_name()
    n_hawkes = sum(1 for f in feats if f.startswith("hawkes_"))
    assert n_hawkes == 0, "Stage A model has Hawkes features — abort"
    log.info("  Stage A model loaded (%d features, 0 Hawkes)", len(feats))

    missing = [f for f in feats if f not in val.columns]
    if missing:
        log.error("Missing val features: %s", missing[:10])
        sys.exit(2)

    log.info("Predicting Stage A on val...")
    p_a = model.predict(val[feats].values)
    val_out = val[["cell_id", "date", "label_dbscan_ignition"]].copy()
    val_out["p_a"] = p_a
    return val_out, feats


def join_v17_scores(val_out: pd.DataFrame) -> pd.DataFrame:
    log.info("Joining v17 audit scores + Hawkes_n...")
    audit = pd.read_parquet(
        AUDIT,
        columns=["cell_id", "date", "ignition_risk",
                 "hawkes_n_recent_10km_7d", "hawkes_lambda"],
    )
    audit["date"] = pd.to_datetime(audit["date"])
    audit = audit.rename(columns={"ignition_risk": "p_v17",
                                   "hawkes_n_recent_10km_7d": "hawkes_n"})
    merged = val_out.merge(audit, on=["cell_id", "date"], how="inner")
    log.info("  After audit join: %d rows (Stage A had %d)",
             len(merged), len(val_out))
    return merged


def compute_blends(df: pd.DataFrame) -> pd.DataFrame:
    p_a = np.clip(df["p_a"].to_numpy(), EPS, 1 - EPS)
    p_v = np.clip(df["p_v17"].to_numpy(), EPS, 1 - EPS)
    df = df.copy()
    df["blend_geo_mean"] = np.sqrt(p_a * p_v)
    df["blend_geo_w0_3"] = (p_a ** 0.3) * (p_v ** 0.7)
    df["blend_geo_w0_5"] = (p_a ** 0.5) * (p_v ** 0.5)
    df["blend_geo_w0_7"] = (p_a ** 0.7) * (p_v ** 0.3)
    df["blend_harmonic"] = 2.0 / (1.0 / p_a + 1.0 / p_v)
    return df


def evaluate_score(df: pd.DataFrame, score_col: str) -> dict:
    """Per-day full-state top-5%, with stratified recall by Hawkes regime.

    Important: the FULL state is ranked by `score_col` per day, top-5% of FULL
    cells selected, then we count how many low-Hawkes / high-Hawkes positives
    fell into THAT top-5%. This matches the synthesis memo's 5.9% framing.
    """
    df = df[["date", "label_dbscan_ignition", "hawkes_n", score_col]].copy()
    overall_caught, overall_pos = 0, 0
    low_caught, low_pos = 0, 0
    high_caught, high_pos = 0, 0
    low_caught_strict, low_pos_strict = 0, 0  # Hawkes_n == 0 (matches memo's 5.9%)
    per_day_recalls = []

    for d, sub in df.groupby("date"):
        sub = sub.sort_values(score_col, ascending=False)
        n_top5 = max(1, int(len(sub) * 0.05))
        top = sub.head(n_top5)
        pos_today = int(sub["label_dbscan_ignition"].sum())
        if pos_today == 0:
            continue
        per_day_recalls.append(int(top["label_dbscan_ignition"].sum()) / pos_today)
        overall_caught += int(top["label_dbscan_ignition"].sum())
        overall_pos += pos_today

        # Low-Hawkes (≤1) positives across all rows; how many caught in full-state top-5%?
        low_pos_rows_today = sub[(sub["hawkes_n"] <= 1) & (sub["label_dbscan_ignition"] == 1)]
        low_caught_today = int(top[(top["hawkes_n"] <= 1)
                                   & (top["label_dbscan_ignition"] == 1)].shape[0])
        low_caught += low_caught_today
        low_pos += int(len(low_pos_rows_today))

        # Strict cold-start (Hawkes_n == 0)
        cold_pos_today = sub[(sub["hawkes_n"] == 0) & (sub["label_dbscan_ignition"] == 1)]
        cold_caught_today = int(top[(top["hawkes_n"] == 0)
                                    & (top["label_dbscan_ignition"] == 1)].shape[0])
        low_caught_strict += cold_caught_today
        low_pos_strict += int(len(cold_pos_today))

        high_pos_rows_today = sub[(sub["hawkes_n"] >= 3) & (sub["label_dbscan_ignition"] == 1)]
        high_caught_today = int(top[(top["hawkes_n"] >= 3)
                                    & (top["label_dbscan_ignition"] == 1)].shape[0])
        high_caught += high_caught_today
        high_pos += int(len(high_pos_rows_today))

    return {
        "overall_r5": overall_caught / overall_pos if overall_pos else 0.0,
        "low_hawkes_r5": low_caught / low_pos if low_pos else 0.0,
        "low_hawkes_strict_r5": low_caught_strict / low_pos_strict if low_pos_strict else 0.0,
        "high_hawkes_r5": high_caught / high_pos if high_pos else 0.0,
        "perday_r5": float(np.mean(per_day_recalls)) if per_day_recalls else 0.0,
        "n_overall_caught": overall_caught,
        "n_overall_pos": overall_pos,
        "n_low_caught": low_caught,
        "n_low_pos": low_pos,
        "n_low_strict_caught": low_caught_strict,
        "n_low_strict_pos": low_pos_strict,
    }


def main() -> int:
    val = load_val_features()
    val_out, _ = predict_stage_a(val)
    merged = join_v17_scores(val_out)
    merged = compute_blends(merged)

    score_cols = ["p_v17", "p_a",
                  "blend_geo_mean", "blend_geo_w0_3", "blend_geo_w0_5",
                  "blend_geo_w0_7", "blend_harmonic"]

    log.info("\n%-22s %-8s %-9s %-9s %-9s %-9s",
             "score", "overall", "low(<=1)", "cold(=0)", "high(>=3)", "perday")
    rows = []
    for col in score_cols:
        m = evaluate_score(merged, col)
        rows.append({"variant": col, **m})
        log.info("%-22s %.4f   %.4f    %.4f    %.4f    %.4f",
                 col, m["overall_r5"], m["low_hawkes_r5"],
                 m["low_hawkes_strict_r5"], m["high_hawkes_r5"], m["perday_r5"])

    df_eval = pd.DataFrame(rows)
    df_eval.to_csv(OUT_DIR / "blend_variants_eval.csv", index=False)

    # Pick winner: max low-Hawkes R@5% subject to overall ≥ floor
    blend_only = df_eval[df_eval["variant"].str.startswith("blend_")].copy()
    eligible = blend_only[blend_only["overall_r5"] >= OVERALL_FLOOR]
    if eligible.empty:
        log.warning("\nNO blend variant meets overall_r5 ≥ %.2f", OVERALL_FLOOR)
        winner = blend_only.loc[blend_only["low_hawkes_r5"].idxmax()]
    else:
        winner = eligible.loc[eligible["low_hawkes_r5"].idxmax()]

    log.info("\n=== WINNER ===")
    log.info("variant: %s", winner["variant"])
    log.info("overall_r5  = %.4f  (floor %.4f)", winner["overall_r5"], OVERALL_FLOOR)
    log.info("low_hawkes  = %.4f  (target %.4f)", winner["low_hawkes_r5"], LOW_HAWKES_TARGET)
    log.info("high_hawkes = %.4f", winner["high_hawkes_r5"])
    log.info("perday_r5   = %.4f", winner["perday_r5"])

    # Compare against v17 alone
    v17_row = df_eval[df_eval["variant"] == "p_v17"].iloc[0]
    delta_overall = winner["overall_r5"] - v17_row["overall_r5"]
    delta_low = winner["low_hawkes_r5"] - v17_row["low_hawkes_r5"]
    log.info("\nDelta vs v17 alone:")
    log.info("  overall:    %+.4f pp  (v17=%.4f)", delta_overall, v17_row["overall_r5"])
    log.info("  low-Hawkes: %+.4f pp  (v17=%.4f)", delta_low, v17_row["low_hawkes_r5"])

    pass_t1 = (winner["low_hawkes_r5"] >= LOW_HAWKES_TARGET
               and winner["overall_r5"] >= OVERALL_FLOOR)
    log.info("\nT1 PASS CRITERION: low_hawkes_r5 ≥ %.2f AND overall_r5 ≥ %.2f",
             LOW_HAWKES_TARGET, OVERALL_FLOOR)
    log.info("T1 verdict: %s", "PASS — ship as v17.5" if pass_t1 else "FAIL — do not ship")

    # Save winning blend config
    config = {
        "variant": winner["variant"],
        "overall_r5": float(winner["overall_r5"]),
        "low_hawkes_r5": float(winner["low_hawkes_r5"]),
        "high_hawkes_r5": float(winner["high_hawkes_r5"]),
        "perday_r5": float(winner["perday_r5"]),
        "v17_baseline_overall_r5": float(v17_row["overall_r5"]),
        "v17_baseline_low_hawkes_r5": float(v17_row["low_hawkes_r5"]),
        "v17_baseline_perday_r5": float(v17_row["perday_r5"]),
        "delta_overall_pp": float(delta_overall),
        "delta_low_hawkes_pp": float(delta_low),
        "t1_pass_criterion_overall_floor": OVERALL_FLOOR,
        "t1_pass_criterion_low_hawkes_target": LOW_HAWKES_TARGET,
        "t1_passed": bool(pass_t1),
    }
    (OUT_DIR / "blend_config.json").write_text(json.dumps(config, indent=2))
    log.info("Wrote: %s", (OUT_DIR / "blend_config.json").relative_to(ROOT))

    # Persist the winning blend's per-cell predictions for downstream use
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    keep_cols = ["cell_id", "date", "label_dbscan_ignition", "hawkes_n",
                 "p_v17", "p_a", winner["variant"]]
    out = merged[keep_cols].copy()
    out = out.rename(columns={winner["variant"]: "blend_winner"})
    out.to_parquet(OUT_PARQUET, index=False)
    log.info("Wrote: %s (%d rows)", OUT_PARQUET.relative_to(ROOT), len(out))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
