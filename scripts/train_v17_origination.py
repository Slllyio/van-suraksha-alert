"""Train Model B: origination specialist for low-Hawkes cells.

Model A (v17) dominates contagion prediction but fails at new-outbreak origination
(5.9% R@5% on low-Hawkes cells). Model B is trained specifically on low-Hawkes
rows WITHOUT Hawkes features, with deep origination features:
  - VPD anomaly (atmosphere's drying power vs 10-year climatology)
  - Settlement interface exponential decay
  - Moisture-greenness interaction delta
  - Beat-level phenological priors

Soft-ensemble at prediction time: P_final = W_h * P_A + (1-W_h) * P_B
where W_h = sigmoid(k * (H - H0)) transitions smoothly as Hawkes intensity grows.
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
from scipy.special import expit as sigmoid
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
FIRMS = ROOT / "data_lake" / "fire_detections" / "firms_dbscan_ignition.parquet"
FWI_DAILY = ROOT / "data_lake" / "fire_weather" / "fwi_daily.csv"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_origination"

HOLDOUT_START = pd.Timestamp("2025-02-01")
LEAKAGE_FEATURES = {"days_since_last_fire", "fire_last_7d",
                    "neighbor_fire_7d", "neighbor_fire_yesterday"}
NON_FEATURES = {"cell_id", "date", "label", "year",
                "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"}


def build_full_dataset() -> pd.DataFrame:
    """Load v8 dataset + Hawkes + GLCM + Hydro (reused from audit_low_hawkes_subset.py)."""
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


def add_deep_origination_features(ds: pd.DataFrame) -> pd.DataFrame:
    """Add VPD anomaly, interface decay, moisture-greenness delta, beat priors."""
    log.info("Building deep origination features...")

    # 1. VPD anomaly
    if "wx_temp_mean" in ds.columns and "wx_rh_pct" in ds.columns:
        t = ds["wx_temp_mean"].clip(-40, 50)
        rh = ds["wx_rh_pct"].clip(0, 100)
        e_s = 0.6108 * np.exp(17.27 * t / (t + 237.3))
        ds["vpd"] = e_s * (1 - rh / 100)

        doy = ds["date"].dt.dayofyear
        vpd_clim = ds.groupby(doy)["vpd"].transform("mean")
        ds["vpd_anomaly"] = ds["vpd"] - vpd_clim
        log.info("  VPD anomaly: mean=%.3f, std=%.3f", ds["vpd_anomaly"].mean(), ds["vpd_anomaly"].std())
    else:
        log.warning("  wx_temp_mean or wx_rh_pct missing — skipping VPD")
        ds["vpd"] = 0
        ds["vpd_anomaly"] = 0

    # 2. Settlement interface exponential decay
    if "ha_dist_settlement" in ds.columns:
        beta = 0.001
        ds["interface_decay"] = np.exp(-beta * ds["ha_dist_settlement"])
        log.info("  Interface decay: mean=%.3f", ds["interface_decay"].mean())
    else:
        ds["interface_decay"] = 0.5

    # 3. Moisture-greenness interaction
    if "wx_rh_pct" in ds.columns and "ndvi_expected" in ds.columns:
        ds["moisture_green"] = (ds["wx_rh_pct"] / 100) * ds["ndvi_expected"]
        mg_clim = ds.groupby(ds["date"].dt.dayofyear)["moisture_green"].transform("mean")
        ds["moisture_green_anomaly"] = ds["moisture_green"] - mg_clim
        log.info("  Moisture-greenness anomaly: mean=%.4f", ds["moisture_green_anomaly"].mean())
    else:
        ds["moisture_green"] = 0
        ds["moisture_green_anomaly"] = 0

    # 4. Beat-level phenological priors
    firms = pd.read_parquet(FIRMS)
    firms["date"] = pd.to_datetime(firms.get("acq_date", firms.get("date")))
    firms["month"] = firms["date"].dt.month

    cells = pd.read_csv(ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv")
    cell_beat = cells[["cell_id", "beat"]].drop_duplicates() if "beat" in cells.columns else None

    if cell_beat is not None and "cell_id" in firms.columns:
        firms_cells = firms.merge(cell_beat, on="cell_id", how="left")
        firms_cells = firms_cells[firms_cells["is_ignition"] == 1]

        beat_month = firms_cells.groupby(["beat", "month"]).size().reset_index(name="fire_count")
        beat_total = beat_month.groupby("beat")["fire_count"].sum().reset_index(name="total_fires")
        beat_month = beat_month.merge(beat_total, on="beat")
        beat_month["fire_rate_month"] = beat_month["fire_count"] / beat_month["total_fires"]

        ds["month"] = ds["date"].dt.month
        ds = ds.merge(cell_beat, on="cell_id", how="left")
        ds = ds.merge(beat_month[["beat", "month", "fire_rate_month"]],
                      on=["beat", "month"], how="left")
        ds["beat_fire_rate_month"] = ds["fire_rate_month"].fillna(0)
        ds.drop(columns=["fire_rate_month"], inplace=True, errors="ignore")

        beat_first_doy = firms_cells.groupby("beat")["date"].apply(
            lambda x: x.dt.dayofyear.median()
        ).reset_index(name="beat_median_first_doy")
        ds = ds.merge(beat_first_doy, on="beat", how="left")
        ds["beat_median_first_doy"] = ds["beat_median_first_doy"].fillna(90)
        ds["beat_days_since_season_start"] = (ds["date"].dt.dayofyear - ds["beat_median_first_doy"]).clip(lower=0)
        log.info("  Beat priors: fire_rate_month mean=%.4f, days_since_start mean=%.1f",
                 ds["beat_fire_rate_month"].mean(), ds["beat_days_since_season_start"].mean())
    else:
        log.warning("  Beat info unavailable — using fallback priors")
        ds["beat_fire_rate_month"] = 0
        ds["beat_median_first_doy"] = 90
        ds["beat_days_since_season_start"] = 0

    # 5. Division one-hot (gives Model B division-specific intercepts)
    if "division" not in ds.columns:
        cells_div = cells[["cell_id", "division"]].drop_duplicates() if "division" in cells.columns else None
        if cells_div is not None:
            ds = ds.merge(cells_div, on="cell_id", how="left")
    if "division" in ds.columns:
        ds["division_code"] = ds["division"].astype("category").cat.codes
        log.info("  Division codes: %d unique", ds["division_code"].nunique())

    return ds


def main() -> int:
    log.info("=== MODEL B: ORIGINATION SPECIALIST ===\n")
    t0 = time.time()

    ds = build_full_dataset()
    ds = add_deep_origination_features(ds)

    # Filter to low-Hawkes rows for MODEL B training
    low_mask = ds["hawkes_n_recent_10km_7d"] <= 1
    log.info("\nLow-Hawkes: %d/%d rows (%.0f%%)", low_mask.sum(), len(ds), 100 * low_mask.mean())

    train = ds[low_mask & (ds["date"] < HOLDOUT_START)].reset_index(drop=True)
    val = ds[low_mask & (ds["date"] >= HOLDOUT_START)].reset_index(drop=True)
    log.info("Train: %d (%d pos), Val: %d (%d pos)",
             len(train), int(train["label_dbscan_ignition"].sum()),
             len(val), int(val["label_dbscan_ignition"].sum()))

    # Feature list: everything EXCEPT Hawkes + leakage + non-features
    feats = [c for c in ds.columns
             if c not in NON_FEATURES
             and c not in LEAKAGE_FEATURES
             and not c.startswith("hawkes_")
             and c not in ("beat", "division", "month", "range", "fire_count",
                           "total_fires", "moisture_green")
             and ds[c].dtype.kind in "biufc"]
    log.info("Features (no Hawkes): %d", len(feats))
    log.info("  New features: %s",
             [f for f in feats if f in ("vpd", "vpd_anomaly", "interface_decay",
                                         "moisture_green_anomaly", "beat_fire_rate_month",
                                         "beat_median_first_doy", "beat_days_since_season_start",
                                         "division_code")])

    dtrain = lgb.Dataset(train[feats].values, label=train["label_dbscan_ignition"].values, feature_name=feats)
    dval = lgb.Dataset(val[feats].values, label=val["label_dbscan_ignition"].values, reference=dtrain)
    params = {
        "objective": "binary", "metric": ["average_precision", "auc"],
        "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
        "feature_fraction": 0.85, "bagging_fraction": 0.85, "bagging_freq": 5,
        "is_unbalance": True, "verbose": -1,
    }
    model_b = lgb.train(params, dtrain, num_boost_round=1500,
                         valid_sets=[dval], valid_names=["val"],
                         callbacks=[lgb.early_stopping(75), lgb.log_evaluation(200)])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model_b.save_model(str(OUT_DIR / "model.txt"))

    # Evaluate Model B alone on low-Hawkes val
    val["risk_b"] = model_b.predict(val[feats].values, num_iteration=model_b.best_iteration)
    roc_b = roc_auc_score(val["label_dbscan_ignition"], val["risk_b"])
    pr_b = average_precision_score(val["label_dbscan_ignition"], val["risk_b"])
    log.info("\nModel B (low-Hawkes only): ROC=%.4f  PR=%.4f  best_iter=%d",
             roc_b, pr_b, model_b.best_iteration)

    val["rank_b"] = val.groupby("date")["risk_b"].rank(pct=True)
    top5_b = val[val["rank_b"] >= 0.95]
    r5_b = top5_b["label_dbscan_ignition"].sum() / max(val["label_dbscan_ignition"].sum(), 1)
    log.info("Model B R@5%%: %.4f (%d/%d)", r5_b,
             int(top5_b["label_dbscan_ignition"].sum()),
             int(val["label_dbscan_ignition"].sum()))

    # ---- SOFT ENSEMBLE on FULL val (all rows, not just low-Hawkes) ----
    log.info("\n--- SOFT ENSEMBLE EVALUATION ---")
    full_val = ds[ds["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("Full val: %d rows (%d DBSCAN ignitions)",
             len(full_val), int(full_val["label_dbscan_ignition"].sum()))

    # Model A (v17) predictions
    model_a = lgb.Booster(model_file=str(V17_MODEL))
    feats_a = model_a.feature_name()
    missing_a = [f for f in feats_a if f not in full_val.columns]
    if missing_a:
        log.warning("Model A missing features: %s — filling with 0", missing_a[:5])
        for f in missing_a:
            full_val[f] = 0
    p_a = model_a.predict(full_val[feats_a].values)

    # Model B predictions on ALL cells (not just low-Hawkes)
    missing_b = [f for f in feats if f not in full_val.columns]
    if missing_b:
        for f in missing_b:
            full_val[f] = 0
    p_b = model_b.predict(full_val[feats].values, num_iteration=model_b.best_iteration)

    # Soft ensemble: W_h = sigmoid(k * (H - H0))
    H = full_val["hawkes_n_recent_10km_7d"].values
    results = {}
    for k_val in [1.0, 2.0, 3.0]:
        for h0 in [0.5, 1.0, 1.5, 2.0]:
            w_h = sigmoid(k_val * (H - h0))
            p_final = w_h * p_a + (1 - w_h) * p_b

            full_val["risk_ensemble"] = p_final
            full_val["rank_ensemble"] = full_val.groupby("date")["risk_ensemble"].rank(pct=True)

            top5 = full_val[full_val["rank_ensemble"] >= 0.95]
            total_ign = int(full_val["label_dbscan_ignition"].sum())
            caught = int(top5["label_dbscan_ignition"].sum())
            r5 = caught / total_ign if total_ign else 0

            low_h_mask = full_val["hawkes_n_recent_10km_7d"] <= 1
            low_h_top5 = full_val[low_h_mask & (full_val["rank_ensemble"] >= 0.95)]
            low_h_total = int(full_val[low_h_mask]["label_dbscan_ignition"].sum())
            low_h_caught = int(low_h_top5["label_dbscan_ignition"].sum())
            low_r5 = low_h_caught / low_h_total if low_h_total else 0

            per_day = []
            for d, g in full_val.groupby("date"):
                t = g[g["rank_ensemble"] >= 0.95]
                ti = int(g["label_dbscan_ignition"].sum())
                ci = int(t["label_dbscan_ignition"].sum())
                if ti > 0:
                    per_day.append(ci / ti)
            pdr = float(np.mean(per_day)) if per_day else 0

            key = f"k={k_val}_h0={h0}"
            results[key] = {"R5": r5, "PerDay": pdr, "LowH_R5": low_r5,
                            "caught": caught, "low_caught": low_h_caught}

    # Also evaluate Model A alone (statewide baseline)
    full_val["risk_a"] = p_a
    full_val["rank_a"] = full_val.groupby("date")["risk_a"].rank(pct=True)
    top5_a = full_val[full_val["rank_a"] >= 0.95]
    r5_a = top5_a["label_dbscan_ignition"].sum() / max(full_val["label_dbscan_ignition"].sum(), 1)
    low_a = full_val[(full_val["hawkes_n_recent_10km_7d"] <= 1) & (full_val["rank_a"] >= 0.95)]
    low_r5_a = low_a["label_dbscan_ignition"].sum() / max(full_val[full_val["hawkes_n_recent_10km_7d"] <= 1]["label_dbscan_ignition"].sum(), 1)

    log.info("\n=== ENSEMBLE GRID SEARCH ===")
    log.info("%-20s  R@5%%   PerDay  LowH_R@5%%  caught/total  low_caught/low_total", "Config")
    log.info("%-20s  %.3f  %.3f   %.3f       %d/%d         %d/%d", "Model A only (v17)",
             r5_a, 0, low_r5_a,
             int(top5_a["label_dbscan_ignition"].sum()), int(full_val["label_dbscan_ignition"].sum()),
             int(low_a["label_dbscan_ignition"].sum()),
             int(full_val[full_val["hawkes_n_recent_10km_7d"] <= 1]["label_dbscan_ignition"].sum()))
    for key, res in sorted(results.items(), key=lambda x: -x[1]["R5"]):
        log.info("%-20s  %.3f  %.3f   %.3f       %d            %d",
                 key, res["R5"], res["PerDay"], res["LowH_R5"], res["caught"], res["low_caught"])

    # Feature importance for Model B
    fi = pd.DataFrame({
        "feature": feats,
        "gain": model_b.feature_importance(importance_type="gain"),
    }).sort_values("gain", ascending=False)
    log.info("\n--- Model B Top 15 Features ---")
    log.info(fi.head(15).to_string(index=False))
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)

    # Save results
    best_key = max(results, key=lambda k: results[k]["R5"])
    best = results[best_key]
    summary = {
        "model_b_roc": roc_b, "model_b_pr": pr_b, "model_b_best_iter": model_b.best_iteration,
        "model_b_r5_low_hawkes": float(r5_b),
        "model_a_r5_statewide": float(r5_a), "model_a_r5_low_hawkes": float(low_r5_a),
        "best_ensemble": best_key, "best_r5": best["R5"], "best_perday": best["PerDay"],
        "best_low_hawkes_r5": best["LowH_R5"],
        "all_results": results,
        "n_features": len(feats),
        "wall_time_s": time.time() - t0,
    }
    with open(OUT_DIR / "results.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info("\nSaved model + results to %s", OUT_DIR.relative_to(ROOT))
    log.info("Wall time: %.1fs", time.time() - t0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
