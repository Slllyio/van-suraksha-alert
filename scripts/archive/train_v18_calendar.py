"""v18: v17 + calendar/behavioral features (festival, NTFP season, division×month).

Last untried data-side experiment. Adds ~10 new features capturing anthropogenic
activity patterns: Hindu festivals (Holi, Bhagoria, Akshaya Tritiya), NTFP
collection season kernels (tendu, mahua), and division×month interaction.

Usage:
  python scripts/train_v18_calendar.py
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
TIERED = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"
CELLS = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_calendar"

HOLDOUT_START = pd.Timestamp("2025-02-01")
LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}

# Holi dates (Purnima of Phalguna month, varies by year)
HOLI_DATES = {
    2014: "2014-03-17", 2015: "2015-03-06", 2016: "2016-03-24",
    2017: "2017-03-13", 2018: "2018-03-02", 2019: "2019-03-21",
    2020: "2020-03-10", 2021: "2021-03-29", 2022: "2022-03-18",
    2023: "2023-03-08", 2024: "2024-03-25", 2025: "2025-03-14",
    2026: "2026-03-03",
}

# Akshaya Tritiya dates (Shukla Tritiya of Vaishakha)
AKSHAYA_DATES = {
    2014: "2014-05-02", 2015: "2015-04-21", 2016: "2016-05-09",
    2017: "2017-04-28", 2018: "2018-04-18", 2019: "2019-05-07",
    2020: "2020-04-26", 2021: "2021-05-14", 2022: "2022-05-03",
    2023: "2023-04-22", 2024: "2024-05-10", 2025: "2025-04-30",
    2026: "2026-04-19",
}


def build_full_dataset() -> pd.DataFrame:
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


def add_calendar_features(ds: pd.DataFrame) -> pd.DataFrame:
    log.info("Building calendar/behavioral features...")
    year = ds["date"].dt.year
    doy = ds["date"].dt.dayofyear

    # 1. Holi features
    holi_doy = year.map({y: pd.Timestamp(d).dayofyear for y, d in HOLI_DATES.items()}).fillna(70)
    ds["days_to_holi"] = (doy - holi_doy).clip(-30, 30)
    ds["is_holi_week"] = (ds["days_to_holi"].abs() <= 3).astype(int)
    ds["is_bhagoria_week"] = ((ds["days_to_holi"] >= -10) & (ds["days_to_holi"] <= -3)).astype(int)

    # 2. Akshaya Tritiya features
    akshaya_doy = year.map({y: pd.Timestamp(d).dayofyear for y, d in AKSHAYA_DATES.items()}).fillna(120)
    ds["days_to_akshaya"] = (doy - akshaya_doy).clip(-30, 30)

    # 3. NTFP season kernels (Gaussian centered on peak collection DOY)
    tendu_peak_doy = 115  # ~April 25
    mahua_peak_doy = 85   # ~March 26
    sigma = 15  # 15-day spread
    ds["tendu_season_intensity"] = np.exp(-0.5 * ((doy - tendu_peak_doy) / sigma) ** 2)
    ds["mahua_season_intensity"] = np.exp(-0.5 * ((doy - mahua_peak_doy) / sigma) ** 2)

    # 4. Division × month interaction
    cells = pd.read_csv(CELLS)
    if "division" in cells.columns:
        cell_div = cells[["cell_id", "division"]].drop_duplicates()
        ds = ds.merge(cell_div, on="cell_id", how="left")
        ds["division_code"] = ds["division"].astype("category").cat.codes
        ds["month"] = ds["date"].dt.month
        ds["div_month_code"] = ds["division_code"] * 12 + ds["month"]
        log.info("  division×month codes: %d unique", ds["div_month_code"].nunique())
    else:
        ds["division_code"] = 0
        ds["div_month_code"] = ds["date"].dt.month

    # 5. Fire-season progress
    season_start_doy = 32  # Feb 1
    ds["fire_season_progress"] = ((doy - season_start_doy) / 120).clip(0, 1)

    new_feats = ["days_to_holi", "is_holi_week", "is_bhagoria_week", "days_to_akshaya",
                 "tendu_season_intensity", "mahua_season_intensity", "div_month_code",
                 "fire_season_progress", "division_code"]
    log.info("  Added %d calendar features: %s", len(new_feats), new_feats)
    return ds


def apply_tiered_labels(ds: pd.DataFrame) -> pd.DataFrame:
    log.info("Applying BA-tiered labels (GOLD/SILVER/BRONZE weights)...")
    tiered = pd.read_parquet(TIERED)
    tiered["date"] = pd.to_datetime(tiered.get("ignition_date", tiered.get("date")))
    tier_rank = {"GOLD": 3, "SILVER": 2, "BRONZE": 1}
    tiered["tier_rank"] = tiered["tier"].astype(str).map(tier_rank).fillna(0).astype(int)

    best = tiered.groupby(["cell_id", "date"])["tier_rank"].max().reset_index()
    best.columns = ["cell_id", "date", "best_tier"]
    ds = ds.merge(best, on=["cell_id", "date"], how="left")
    ds["best_tier"] = ds["best_tier"].fillna(0).astype(int)

    tier_weight = {3: 1.0, 2: 0.7, 1: 0.5, 0: 1.0}
    ds["label_tiered_any"] = (ds["best_tier"] > 0).astype(int) | ds["label_dbscan_ignition"].astype(int)
    ds["sample_weight"] = ds["best_tier"].map(tier_weight).fillna(1.0)
    ds.loc[ds["label_tiered_any"] == 0, "sample_weight"] = 1.0

    n_pos = int(ds["label_tiered_any"].sum())
    n_neg = len(ds) - n_pos
    log.info("  Tiered labels: %d pos / %d neg (%.2f%% positive)", n_pos, n_neg, n_pos / len(ds) * 100)
    return ds


def main() -> int:
    log.info("=== v18 CALENDAR+BEHAVIORAL FEATURES ===\n")
    t0 = time.time()

    ds = build_full_dataset()
    ds = add_calendar_features(ds)
    ds = apply_tiered_labels(ds)

    train = ds[ds["date"] < HOLDOUT_START].reset_index(drop=True)
    val = ds[ds["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("Train: %d (%d pos), Val: %d (%d pos)",
             len(train), int(train["label_tiered_any"].sum()),
             len(val), int(val["label_tiered_any"].sum()))

    feats = [c for c in ds.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and c not in ("best_tier", "sample_weight", "label_tiered_any",
                           "tier_rank", "division", "month", "range", "beat")
             and ds[c].dtype.kind in "biufc"]
    log.info("Features: %d (v17 had 111)", len(feats))

    calendar_feats = [f for f in feats if f in (
        "days_to_holi", "is_holi_week", "is_bhagoria_week", "days_to_akshaya",
        "tendu_season_intensity", "mahua_season_intensity", "div_month_code",
        "fire_season_progress", "division_code")]
    log.info("  Calendar features in model: %s", calendar_feats)

    dtrain = lgb.Dataset(
        train[feats].values, label=train["label_tiered_any"].values,
        weight=train["sample_weight"].values, feature_name=feats)
    dval = lgb.Dataset(
        val[feats].values, label=val["label_tiered_any"].values,
        weight=val["sample_weight"].values, reference=dtrain)

    params = {
        "objective": "binary", "metric": ["average_precision", "auc"],
        "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
        "feature_fraction": 0.85, "bagging_fraction": 0.85, "bagging_freq": 5,
        "is_unbalance": True, "verbose": -1,
    }
    model = lgb.train(params, dtrain, num_boost_round=1500,
                       valid_sets=[dval], valid_names=["val"],
                       callbacks=[lgb.early_stopping(75), lgb.log_evaluation(200)])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(str(OUT_DIR / "model.txt"))

    # Evaluate
    val["risk_v18"] = model.predict(val[feats].values, num_iteration=model.best_iteration)
    roc = roc_auc_score(val["label_tiered_any"], val["risk_v18"])
    pr = average_precision_score(val["label_tiered_any"], val["risk_v18"])

    val["rank_v18"] = val.groupby("date")["risk_v18"].rank(pct=True)
    top5 = val[val["rank_v18"] >= 0.95]

    # BA-tiered R@5%
    r5_tiered = top5["label_tiered_any"].sum() / max(val["label_tiered_any"].sum(), 1)

    # DBSCAN-strict R@5%
    r5_dbscan = top5["label_dbscan_ignition"].sum() / max(val["label_dbscan_ignition"].sum(), 1)

    # PerDay R@5% (tiered)
    per_day = []
    for d, g in val.groupby("date"):
        t = g[g["rank_v18"] >= 0.95]
        ti = int(g["label_tiered_any"].sum())
        ci = int(t["label_tiered_any"].sum())
        if ti > 0:
            per_day.append(ci / ti)
    pdr = float(np.mean(per_day)) if per_day else 0

    log.info("\n=== v18 RESULTS ===")
    log.info("ROC-AUC: %.4f  PR-AUC: %.4f  best_iter: %d", roc, pr, model.best_iteration)
    log.info("R@5%% (BA-tiered): %.4f", r5_tiered)
    log.info("R@5%% (DBSCAN-strict): %.4f", r5_dbscan)
    log.info("PerDayR@5%% (tiered): %.4f", pdr)

    # v17 comparison
    log.info("\n=== HEAD-TO-HEAD vs v17 ===")
    log.info("%-20s  ROC     PR      R@5%%_t  R@5%%_d  PerDay", "Model")
    log.info("%-20s  0.8815  0.1481  0.4741  0.2269  0.4856", "v17 (baseline)")
    log.info("%-20s  %.4f  %.4f  %.4f  %.4f  %.4f", "v18 (calendar)",
             roc, pr, r5_tiered, r5_dbscan, pdr)
    delta_r5 = r5_tiered - 0.4741
    log.info("Delta R@5%% (tiered): %+.4f (%+.1f%%)", delta_r5, delta_r5 * 100)

    # Feature importance
    fi = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
    }).sort_values("gain", ascending=False)
    log.info("\n--- Top 20 Features ---")
    log.info(fi.head(20).to_string(index=False))
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)

    log.info("\nCalendar features ranking:")
    for f in calendar_feats:
        row = fi[fi["feature"] == f]
        if len(row):
            rank = fi.index.get_loc(row.index[0]) + 1
            log.info("  %-30s rank=%3d gain=%.0f", f, rank, row.iloc[0]["gain"])

    # Verdict
    pass_tiered = r5_tiered >= 0.4741 + 0.01
    pass_dbscan = r5_dbscan >= 0.2269 + 0.01
    verdict = "PASS" if (pass_tiered or pass_dbscan) else "FAIL"
    log.info("\n=== VERDICT: %s ===", verdict)
    log.info("  [%s] R@5%% tiered >= 0.4841: %.4f", "PASS" if pass_tiered else "FAIL", r5_tiered)
    log.info("  [%s] R@5%% DBSCAN >= 0.2369: %.4f", "PASS" if pass_dbscan else "FAIL", r5_dbscan)

    summary = {
        "roc": roc, "pr": pr, "best_iter": model.best_iteration,
        "r5_tiered": float(r5_tiered), "r5_dbscan": float(r5_dbscan),
        "perday_r5": pdr, "n_features": len(feats),
        "delta_r5_tiered": float(delta_r5),
        "verdict": verdict, "wall_time_s": time.time() - t0,
    }
    with open(OUT_DIR / "results.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info("Saved to %s", OUT_DIR.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
