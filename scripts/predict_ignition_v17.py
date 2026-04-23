"""Production deployment helper for v17_ba_pu.

v17 trained with BA-augmented tiered labels (GOLD+SILVER+BRONZE weighted PU):
  R@top-5%       = 47.41% (vs v15 40.45%, +6.96 pp, +17% relative)
  PerDayR@top-5% = 48.56% (vs v15 33.10%, +15.46 pp, +46% relative)
  PR-AUC         = 0.1481 (vs v15 0.0380, 3.9× improvement)
  ROC-AUC        = 0.8815 (vs v15 0.8646, +0.017)

Architecture: single-model LightGBM (no ensemble). 111 features = v8 base (84) +
Hawkes (4) + GLCM (19) + Hydro (6). Features are identical to what v13/v14 used;
the gain comes from the LABEL SET — BA-corroborated tiered positives.

Mirrors `scripts/archive/predict_ignition_v15.py` JSON schema so `daily_fire_alert.py`
can swap models by switching which script it calls. (v15 was archived 2026-04-23
along with v9 and other older variants — see scripts/archive/NOTES.md.)

Usage:
  python scripts/predict_ignition_v17.py --date 2026-04-15
  python scripts/predict_ignition_v17.py --date 2026-04-15 \
      --output outputs/dashboard_feed/ignition_risk_v17.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V17_MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "model.txt"
V8_DATASET = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan" / "dataset.parquet"
FIRMS_PATH = ROOT / "data_lake" / "fire_detections" / "firms_dbscan_ignition.parquet"
HAWKES_PARAMS = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_params.json"
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO_PATH = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
CALIBRATION_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "calibration.json"
HURDLE_STAGE_A_MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_hurdle_a" / "model.txt"
HURDLE_BLEND_CONFIG = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_hurdle" / "blend_config.json"

# Live weather + per-beat history overrides (added 2026-04-23)
FWI_DAILY_PARQUET = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
SOIL_DAILY_PARQUET = ROOT / "data_lake" / "fire_weather" / "soil_daily.parquet"
BEAT_CLIMATOLOGY_PARQUET = ROOT / "data_lake" / "fire_weather" / "beat_fire_climatology.parquet"
ERA5_PER_DIVISION_PARQUET = ROOT / "data_lake" / "fire_weather" / "era5_per_division_daily.parquet"

# Per-beat-history boost: final_risk = blend_risk * (1 + BETA * percentile_in_week).
# BETA=0.30 means top-percentile beats get a 30% bump; bottom-percentile beats get 0%.
# Tuned to be material but not to overwrite the model's own ranking.
BEAT_HISTORY_BOOST_BETA = 0.30

# Map FWI parquet columns -> model wx_* feature names (10 directly available)
FWI_TO_WX = {
    "temp_c":   "wx_temp_c",
    "rh_pct":   "wx_rh_pct",
    "wind_kmh": "wx_wind_kmh",
    "precip_mm": "wx_precip_mm",
    "ffmc":     "wx_ffmc",
    "dmc":      "wx_dmc",
    "dc":       "wx_dc",
    "isi":      "wx_isi",
    "bui":      "wx_bui",
    "fwi":      "wx_fwi",
}

# Map ERA5 per-division (Open-Meteo) columns -> model wx_* feature names.
# These cover the 21 derived wx_* features that FWI alone can't provide
# (rolling 7d/14d/30d aggregates, anomalies, soil moisture, srad, VPD).
ERA5_TO_WX = {
    "air_temp_c":          "wx_temp_c",
    "rh_pct":              "wx_rh_pct",
    "wind_kmh_max":        "wx_wind_kmh",
    "precip_mm":           "wx_precip_mm",
    "precip_7d":           "wx_precip_7d",
    "precip_14d":          "wx_precip_14d",
    "precip_30d":          "wx_precip_30d",
    "consecutive_dry":     "wx_consecutive_dry",
    "temp_7d_mean":        "wx_temp_7d_mean",
    "rh_7d_min":           "wx_rh_7d_min",
    "wind_7d_max":         "wx_wind_7d_max",
    "vpd_kpa":             "wx_vpd",
    "vpd_7d_max":          "wx_vpd_7d_max",
    "dtr":                 "wx_dtr",
    "temp_anom":           "wx_anom_temp_c",
    "rh_anom":             "wx_anom_rh_pct",
    "wind_anom":           "wx_anom_wind_kmh",
    "precip_anom":         "wx_anom_precip_mm",
    "soil_moisture_0_7cm": "wx_sm_surface",
    "soil_moisture_7_28cm": "wx_sm_rootzone",
    "srad_mj":             "wx_srad",
}


def _load_hurdle_blend() -> tuple[lgb.Booster | None, dict | None]:
    """Returns (Stage A model, blend config) or (None, None) if missing."""
    if not HURDLE_STAGE_A_MODEL.exists() or not HURDLE_BLEND_CONFIG.exists():
        return None, None
    try:
        model_a = lgb.Booster(model_file=str(HURDLE_STAGE_A_MODEL))
        cfg = json.loads(HURDLE_BLEND_CONFIG.read_text())
        return model_a, cfg
    except Exception:
        return None, None


def _apply_hurdle_blend(p_v17: np.ndarray, p_a: np.ndarray, variant: str) -> np.ndarray:
    """Same blend formulas as scripts/evaluate_v17_hurdle_blend.py."""
    eps = 1e-12
    p_a = np.clip(p_a, eps, 1 - eps)
    p_v = np.clip(p_v17, eps, 1 - eps)
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
    return p_v17  # unknown variant — fall through


def _load_calibration() -> dict | None:
    if not CALIBRATION_PATH.exists():
        return None
    try:
        return json.loads(CALIBRATION_PATH.read_text())
    except Exception:
        return None


def _apply_calibration(scores: np.ndarray, params: dict | None) -> np.ndarray:
    if params is None:
        return scores
    if params.get("method") == "isotonic":
        return np.interp(scores, params["knot_x"], params["knot_y"])
    if params.get("method") == "platt_sigmoid":
        z = params["slope"] * scores + params["intercept"]
        return 1.0 / (1.0 + np.exp(-z))
    return scores

KM_PER_DEG_LAT = 110.6
KM_PER_DEG_LON = 101.4
SEARCH_RADIUS_KM = 30.0


def compute_hawkes_for_date(target_date: pd.Timestamp, ign_df: pd.DataFrame, cells_df: pd.DataFrame,
                            params: dict) -> pd.DataFrame:
    """Compute Hawkes intensity for all cells on target date.

    Identical logic to scripts/archive/predict_ignition_v9.py and
    scripts/archive/predict_ignition_v15.py — duplicated here to keep
    production scripts self-contained.
    """
    tau_t = params["tau_t_days"]
    tau_s = params["tau_s_km"]
    lookback = params["lookback_days"]
    count_window = params["count_window_days"]
    count_radius = params["count_radius_km"]

    cutoff = target_date - timedelta(days=int(lookback))
    past = ign_df[(ign_df["acq_date"] >= cutoff) & (ign_df["acq_date"] < target_date)].copy()
    log.info("  Past ignitions in lookback window: %d", len(past))

    n_cells = len(cells_df)
    cell_coords = cells_df[["x_km", "y_km"]].values

    if len(past) == 0:
        return pd.DataFrame({
            "cell_id": cells_df["cell_id"].values,
            "hawkes_lambda": np.zeros(n_cells, dtype=np.float32),
            "hawkes_lambda_log": np.zeros(n_cells, dtype=np.float32),
            "hawkes_n_recent_10km_7d": np.zeros(n_cells, dtype=np.int32),
            "hawkes_nearest_ign_14d_km": np.full(n_cells, 50.0, dtype=np.float32),
        })

    past["x_km"] = past["longitude"] * KM_PER_DEG_LON
    past["y_km"] = past["latitude"] * KM_PER_DEG_LAT
    past_x = past["x_km"].values
    past_y = past["y_km"].values
    past_dts = ((target_date - past["acq_date"]) / np.timedelta64(1, "D")).astype(np.float32).values

    tree = cKDTree(np.stack([past_x, past_y], axis=1))

    lam = np.zeros(n_cells, dtype=np.float32)
    n_recent = np.zeros(n_cells, dtype=np.int32)
    nearest_14d = np.full(n_cells, 50.0, dtype=np.float32)

    neighbors_per_cell = tree.query_ball_point(cell_coords, r=SEARCH_RADIUS_KM)
    for ci in range(n_cells):
        nbrs = neighbors_per_cell[ci]
        if not nbrs:
            continue
        nbr_dts = past_dts[nbrs]
        nbr_dx = cell_coords[ci, 0] - past_x[nbrs]
        nbr_dy = cell_coords[ci, 1] - past_y[nbrs]
        nbr_dists = np.sqrt(nbr_dx * nbr_dx + nbr_dy * nbr_dy)

        weights = np.exp(-nbr_dts / tau_t) * np.exp(-nbr_dists / tau_s)
        lam[ci] = weights.sum()

        mask_count = (nbr_dts <= count_window) & (nbr_dists <= count_radius)
        n_recent[ci] = int(mask_count.sum())

        mask_14d = nbr_dts <= 14
        if mask_14d.any():
            nearest_14d[ci] = float(nbr_dists[mask_14d].min())

    return pd.DataFrame({
        "cell_id": cells_df["cell_id"].values,
        "hawkes_lambda": lam,
        "hawkes_lambda_log": np.log1p(lam),
        "hawkes_n_recent_10km_7d": n_recent,
        "hawkes_nearest_ign_14d_km": nearest_14d,
    })


def load_rolling_history(dashboard_dir: Path, target_date: pd.Timestamp,
                         model_tag: str, window_days: int = 7) -> np.ndarray:
    history = []
    for i in range(1, window_days + 1):
        prior = target_date - timedelta(days=i)
        dated = dashboard_dir / f"ignition_risk_{model_tag}_{prior.strftime('%Y-%m-%d')}.json"
        if not dated.exists():
            continue
        try:
            payload = json.loads(dated.read_text())
            for a in payload.get("alerts_all_cells", payload.get("alerts", [])):
                r = a.get("ignition_risk")
                if r is not None:
                    history.append(float(r))
        except Exception:
            continue
    return np.asarray(history, dtype=np.float32)


def compute_rank_bands(probs: np.ndarray, rolling_history: np.ndarray,
                       band_thresholds: tuple[float, float, float] = (0.95, 0.98, 0.995)
                       ) -> tuple[np.ndarray, np.ndarray, dict]:
    if rolling_history.size > 0:
        reference = np.concatenate([probs, rolling_history])
        mode = f"rolling_{rolling_history.size}_pts_plus_today"
    else:
        reference = probs
        mode = "within_day_fallback"

    watch_thr = float(np.quantile(reference, band_thresholds[0]))
    alert_thr = float(np.quantile(reference, band_thresholds[1]))
    crit_thr = float(np.quantile(reference, band_thresholds[2]))

    ref_sorted = np.sort(reference)
    ranks = np.searchsorted(ref_sorted, probs, side="right") / len(ref_sorted)

    bands = np.zeros(len(probs), dtype=np.int8)
    bands[probs >= watch_thr] = 1
    bands[probs >= alert_thr] = 2
    bands[probs >= crit_thr] = 3

    meta = {
        "mode": mode,
        "reference_size": int(len(reference)),
        "rolling_history_size": int(rolling_history.size),
        "today_size": int(probs.size),
        "watch_threshold": watch_thr,
        "alert_threshold": alert_thr,
        "critical_threshold": crit_thr,
        "n_watch": int((bands == 1).sum()),
        "n_alert": int((bands == 2).sum()),
        "n_critical": int((bands == 3).sum()),
    }
    return ranks, bands, meta


def apply_live_weather_overrides(df: pd.DataFrame, cells: pd.DataFrame,
                                  target_date: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Replace stale wx_* columns in df with live values from FWI + ERA5 sources.

    Two-stage override:
      Stage 1 (statewide FWI): 10 wx_* columns from `fwi_daily.parquet`
              (single statewide value broadcast to all cells)
      Stage 2 (per-division ERA5): 21 wx_* columns from
              `era5_per_division_daily.parquet`, joined on `division`
              for spatial variation.

    The v8 base dataset is frozen at 2025-05-29 -- without these overrides
    every 2026 prediction inherits 11-month-stale weather. Combined the two
    overrides cover 31 of the 38 wx_* columns. The 7 still-frozen columns
    (wx_fuel_dryness, wx_heat_streak, wx_lst, wx_lst_7d_max,
    wx_lst_air_diff, wx_sm_*_7d_min, wx_sm_*_30d, wx_sm_anomaly) need
    different data sources and stay at v8 frozen values for now.

    Returns (updated_df, override_meta) where override_meta documents what
    was applied for the per-prediction JSON output.
    """
    if not FWI_DAILY_PARQUET.exists():
        return df, {"applied": False, "reason": "fwi_daily.parquet missing"}
    fwi = pd.read_parquet(FWI_DAILY_PARQUET)
    fwi["date"] = pd.to_datetime(fwi["date"]).dt.date
    target = target_date.date()
    match = fwi[fwi["date"] == target]
    if match.empty:
        match = fwi[fwi["date"] <= target].tail(1)
    if match.empty:
        return df, {"applied": False, "reason": f"no FWI row at or before {target}"}
    row = match.iloc[0]
    fwi_date = row["date"]

    # ---- Stage 1: statewide FWI override (10 columns) ----
    fwi_overrides = {}
    fwi_deltas = {}
    for fwi_col, wx_col in FWI_TO_WX.items():
        if wx_col not in df.columns or fwi_col not in row.index:
            continue
        old_median = float(df[wx_col].median()) if df[wx_col].notna().any() else None
        new_value = float(row[fwi_col])
        df[wx_col] = new_value  # broadcast statewide value to all cells
        fwi_overrides[wx_col] = new_value
        if old_median is not None:
            fwi_deltas[wx_col] = round(new_value - old_median, 3)

    # ---- Stage 1b: FWI-derived rolling stats (7 cols, computed on the fly) ----
    # Uses the full fwi_daily history to compute precip rolls + temp/RH/wind
    # rolling stats + VPD via Magnus formula. These would normally come from
    # the v8 frozen dataset and ERA5 per-cell -- this is a statewide stand-in
    # that's still much fresher than v8's 2025-05-29 frozen values.
    fwi_rolling_overrides = {}
    fwi_history = fwi[fwi["date"] <= target].sort_values("date").reset_index(drop=True)
    if len(fwi_history) >= 7:
        # Precip rolling sums (last 7d/14d/30d ending at target)
        for window, wx_col in [(7, "wx_precip_7d"), (14, "wx_precip_14d"), (30, "wx_precip_30d")]:
            if wx_col in df.columns:
                v = float(fwi_history.tail(window)["precip_mm"].sum())
                df[wx_col] = v
                fwi_rolling_overrides[wx_col] = round(v, 3)

        # Temperature 7d mean
        if "wx_temp_7d_mean" in df.columns:
            v = float(fwi_history.tail(7)["temp_c"].mean())
            df["wx_temp_7d_mean"] = v
            fwi_rolling_overrides["wx_temp_7d_mean"] = round(v, 3)

        # RH 7d min
        if "wx_rh_7d_min" in df.columns:
            v = float(fwi_history.tail(7)["rh_pct"].min())
            df["wx_rh_7d_min"] = v
            fwi_rolling_overrides["wx_rh_7d_min"] = round(v, 3)

        # Wind 7d max
        if "wx_wind_7d_max" in df.columns:
            v = float(fwi_history.tail(7)["wind_kmh"].max())
            df["wx_wind_7d_max"] = v
            fwi_rolling_overrides["wx_wind_7d_max"] = round(v, 3)

        # VPD via Magnus formula at target_date conditions
        if "wx_vpd" in df.columns:
            t = float(row["temp_c"])
            rh = float(row["rh_pct"])
            es = 0.6108 * np.exp(17.27 * t / (t + 237.3))
            vpd = float(es * (1 - rh / 100))
            df["wx_vpd"] = vpd
            fwi_rolling_overrides["wx_vpd"] = round(vpd, 4)

        # VPD 7d max (compute per day, take max)
        if "wx_vpd_7d_max" in df.columns and len(fwi_history) >= 7:
            recent = fwi_history.tail(7).copy()
            es_arr = 0.6108 * np.exp(17.27 * recent["temp_c"] / (recent["temp_c"] + 237.3))
            vpd_arr = es_arr * (1 - recent["rh_pct"] / 100)
            v = float(vpd_arr.max())
            df["wx_vpd_7d_max"] = v
            fwi_rolling_overrides["wx_vpd_7d_max"] = round(v, 4)

        # Consecutive dry days (count back from target)
        if "wx_consecutive_dry" in df.columns:
            recent = fwi_history.tail(60)["precip_mm"].iloc[::-1].to_numpy()  # reverse
            n = 0
            for p in recent:
                if p > 0.5:
                    break
                n += 1
            df["wx_consecutive_dry"] = float(n)
            fwi_rolling_overrides["wx_consecutive_dry"] = n

    # ---- Stage 1c: soil_daily.parquet override (2 cols) ----
    soil_overrides = {}
    soil_meta = {"applied": False}
    if SOIL_DAILY_PARQUET.exists():
        try:
            soil = pd.read_parquet(SOIL_DAILY_PARQUET)
            soil["date"] = pd.to_datetime(soil["date"]).dt.date
            soil_match = soil[soil["date"] == target]
            if soil_match.empty:
                soil_match = soil[soil["date"] <= target].tail(1)
            if not soil_match.empty:
                srow = soil_match.iloc[0]
                if "wx_sm_surface" in df.columns and "soil_moisture_0_to_7cm_mean" in srow.index:
                    df["wx_sm_surface"] = float(srow["soil_moisture_0_to_7cm_mean"])
                    soil_overrides["wx_sm_surface"] = round(float(srow["soil_moisture_0_to_7cm_mean"]), 4)
                if "wx_sm_rootzone" in df.columns and "soil_moisture_7_to_28cm_mean" in srow.index:
                    df["wx_sm_rootzone"] = float(srow["soil_moisture_7_to_28cm_mean"])
                    soil_overrides["wx_sm_rootzone"] = round(float(srow["soil_moisture_7_to_28cm_mean"]), 4)
                if "wx_sm_anomaly" in df.columns and "soil_moisture_anomaly" in srow.index:
                    df["wx_sm_anomaly"] = float(srow["soil_moisture_anomaly"])
                    soil_overrides["wx_sm_anomaly"] = round(float(srow["soil_moisture_anomaly"]), 4)
                soil_meta = {"applied": True, "soil_date_used": str(srow["date"]),
                             "n_columns_overridden": len(soil_overrides),
                             "overrides": soil_overrides}
        except Exception as exc:
            soil_meta = {"applied": False, "reason": f"soil load failed: {exc}"}

    # ---- Stage 2: per-division ERA5 override (up to 21 columns) ----
    era5_meta = {"applied": False, "reason": "era5_per_division_daily.parquet missing"}
    if ERA5_PER_DIVISION_PARQUET.exists():
        try:
            era5 = pd.read_parquet(ERA5_PER_DIVISION_PARQUET)
            era5["date"] = pd.to_datetime(era5["date"]).dt.date
            era5_today = era5[era5["date"] == target]
            if era5_today.empty:
                era5_today = era5[era5["date"] <= target]
                era5_today = era5_today.sort_values("date").groupby("division").tail(1)
            era5_today = era5_today.set_index("division")
        except Exception as exc:
            era5_meta = {"applied": False, "reason": f"era5 load failed: {exc}"}
            era5_today = None

        if era5_today is not None and len(era5_today) > 0:
            # Merge cell -> division -> ERA5 row
            cell_to_div = dict(zip(cells["cell_id"].astype(str),
                                   cells["division"].astype(str)))
            df["_division"] = df["cell_id"].map(cell_to_div)

            era5_overrides = []
            era5_n_cells_updated = 0
            for era5_col, wx_col in ERA5_TO_WX.items():
                if wx_col not in df.columns or era5_col not in era5_today.columns:
                    continue
                era5_col_lookup = era5_today[era5_col].to_dict()
                new_vals = df["_division"].map(era5_col_lookup)
                # Only override cells whose division has ERA5 data
                mask = new_vals.notna()
                if mask.any():
                    df.loc[mask, wx_col] = new_vals[mask].astype(float)
                    era5_overrides.append(wx_col)
                    era5_n_cells_updated = max(era5_n_cells_updated, int(mask.sum()))
            df = df.drop(columns=["_division"])

            era5_meta = {
                "applied": True,
                "era5_date_used": str(era5_today["date"].iloc[0])
                                  if "date" in era5_today.columns
                                  else str(target),
                "n_columns_overridden": len(era5_overrides),
                "n_cells_updated_per_col_max": era5_n_cells_updated,
                "n_divisions_in_era5_table": int(len(era5_today)),
                "columns": era5_overrides,
            }

    n_total = (len(fwi_overrides) + len(fwi_rolling_overrides) + len(soil_overrides)
               + (era5_meta.get("n_columns_overridden", 0) if era5_meta.get("applied") else 0))
    return df, {
        "applied": True,
        "fwi_stage": {
            "fwi_date_used": str(fwi_date),
            "n_columns_overridden": len(fwi_overrides),
            "overrides": fwi_overrides,
            "deltas_vs_v8_frozen": fwi_deltas,
        },
        "fwi_rolling_stage": {
            "applied": bool(fwi_rolling_overrides),
            "n_columns_overridden": len(fwi_rolling_overrides),
            "overrides": fwi_rolling_overrides,
            "note": ("derived from fwi_daily.parquet history; statewide values "
                     "broadcast to all cells (no per-cell weather raster needed)"),
        },
        "soil_stage": soil_meta,
        "era5_stage": era5_meta,
        "n_total_wx_columns_overridden": n_total,
        "note": (
            f"Coverage: {n_total} wx_* columns from live data. "
            "Still frozen at v8 2025-05-29: wx_fuel_dryness, wx_heat_streak, "
            "wx_lst*, wx_sm_*_7d_min, wx_sm_*_30d (these need a per-cell "
            "weather raster + LST source not currently available)."
        ),
    }


def apply_beat_history_boost(df: pd.DataFrame, cells: pd.DataFrame,
                              target_date: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Multiply ignition_risk by (1 + BETA * percentile_in_week) per cell's beat.

    Looks up `beat_fire_climatology.parquet` for the target date's ISO week.
    Cells whose beat has high historical fire frequency get a gentle boost
    (BETA=0.30 means top-percentile beats get +30%, bottom-percentile +0%).
    This injects a per-beat-history signal into the model output without
    touching the model itself -- a post-prediction decoration in the same
    spirit as the operational coverage + climatology floors.

    Requires `cells` DataFrame to carry `division` and `beat` columns to
    join against the climatology parquet.

    Returns (updated_df, boost_meta).
    """
    if not BEAT_CLIMATOLOGY_PARQUET.exists():
        return df, {"applied": False, "reason": "beat_fire_climatology.parquet missing"}
    if "division" not in cells.columns or "beat" not in cells.columns:
        return df, {"applied": False, "reason": "cells.csv lacks division/beat columns"}

    clim = pd.read_parquet(BEAT_CLIMATOLOGY_PARQUET)
    target_woy = int(pd.Timestamp(target_date).isocalendar().week)
    week_clim = clim[clim["week_of_year"] == target_woy].copy()
    if week_clim.empty:
        return df, {"applied": False, "reason": f"no climatology rows for week {target_woy}"}

    # Build per-cell percentile by joining cells -> beat -> climatology
    cell_beat = cells[["cell_id", "division", "beat"]].copy()
    cell_beat = cell_beat.rename(columns={"division": "Division", "beat": "Beat"})
    cell_clim = cell_beat.merge(
        week_clim[["Division", "Beat", "percentile_in_week"]],
        on=["Division", "Beat"], how="left",
    )
    cell_clim["percentile_in_week"] = cell_clim["percentile_in_week"].fillna(0.0)
    pct_lookup = dict(zip(cell_clim["cell_id"], cell_clim["percentile_in_week"]))

    pcts = df["cell_id"].map(pct_lookup).fillna(0.0).to_numpy()
    boost = 1.0 + BEAT_HISTORY_BOOST_BETA * pcts
    df["beat_history_pctile"] = pcts
    df["beat_history_boost"] = boost
    pre_min, pre_max = float(df["ignition_risk"].min()), float(df["ignition_risk"].max())
    df["ignition_risk"] = df["ignition_risk"] * boost
    post_min, post_max = float(df["ignition_risk"].min()), float(df["ignition_risk"].max())

    n_boosted = int((pcts > 0).sum())
    return df, {
        "applied": True,
        "beta": BEAT_HISTORY_BOOST_BETA,
        "week_of_year": target_woy,
        "n_cells_with_history": n_boosted,
        "n_cells_no_history": int(len(pcts) - n_boosted),
        "max_boost": round(float(boost.max()), 3),
        "pre_boost_risk_range": [round(pre_min, 4), round(pre_max, 4)],
        "post_boost_risk_range": [round(post_min, 4), round(post_max, 4)],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Target prediction date (YYYY-MM-DD). Default: tomorrow.")
    ap.add_argument("--top-pct", type=float, default=5.0)
    ap.add_argument("--rank-window-days", type=int, default=7)
    ap.add_argument("--output", default=str(ROOT / "outputs" / "dashboard_feed" / "ignition_risk_v17.json"))
    ap.add_argument("--use-hurdle-blend", action="store_true",
                    help="Apply Hurdle Stage A blend (Pivot A v2 T1 winner). "
                         "Re-ranks cells by blend(Stage A × v17). Marginal positive in eval.")
    ap.add_argument("--use-live-weather", action="store_true",
                    help="Override 10 stale wx_* columns from v8 dataset (frozen 2025-05-29) "
                         "with today's fwi_daily.parquet values. Recommended.")
    ap.add_argument("--use-beat-history", action="store_true",
                    help="Apply post-prediction multiplier from per-beat 5-year fire climatology. "
                         "Boosts cells in historically-burning beats (BETA=0.30). Recommended.")
    args = ap.parse_args()

    target_date = pd.Timestamp(args.date) if args.date else pd.Timestamp(datetime.now().date() + timedelta(days=1))
    log.info("v17_ba_pu ignition prediction for %s", target_date.date())

    log.info("Loading v17 model + Hawkes params...")
    model = lgb.Booster(model_file=str(V17_MODEL))
    feat_names = model.feature_name()
    log.info("  Model: %d features", len(feat_names))
    params = json.loads(HAWKES_PARAMS.read_text())

    log.info("Loading FIRMS DBSCAN ignitions...")
    ign = pd.read_parquet(FIRMS_PATH)
    ign["acq_date"] = pd.to_datetime(ign["acq_date"])
    ign = ign[ign["is_ignition"] == 1].reset_index(drop=True)
    log.info("  %d ignitions in archive", len(ign))

    log.info("Loading cells...")
    cells = pd.read_csv(CELLS_PATH)
    cells["x_km"] = cells["centroid_lon"] * KM_PER_DEG_LON
    cells["y_km"] = cells["centroid_lat"] * KM_PER_DEG_LAT
    log.info("  %d cells", len(cells))

    log.info("Computing Hawkes features...")
    t0 = time.time()
    hawkes_df = compute_hawkes_for_date(target_date, ign, cells, params)
    log.info("  Done in %.1fs", time.time() - t0)

    log.info("Loading base features from v8 dataset (most recent date as proxy)...")
    ds = pd.read_parquet(V8_DATASET)
    ds["date"] = pd.to_datetime(ds["date"])
    most_recent = ds["date"].max()
    log.info("  Using base features from %s", most_recent.date())
    base = ds[ds["date"] == most_recent].drop(
        columns=["date", "label", "label_dbscan_ignition", "n_ignitions", "n_dets", "max_frp"],
        errors="ignore",
    )
    log.info("  %d base feature rows", len(base))

    weather_meta = {"applied": False, "reason": "flag not set"}
    if args.use_live_weather:
        log.info("Applying live weather override (--use-live-weather)...")
        base, weather_meta = apply_live_weather_overrides(base, cells, target_date)
        if weather_meta.get("applied"):
            fwi_stage = weather_meta.get("fwi_stage", {})
            era5_stage = weather_meta.get("era5_stage", {})
            log.info("  FWI stage:  %d cols from %s",
                     fwi_stage.get("n_columns_overridden", 0),
                     fwi_stage.get("fwi_date_used", "?"))
            if era5_stage.get("applied"):
                log.info("  ERA5 stage: %d cols across %d divisions",
                         era5_stage.get("n_columns_overridden", 0),
                         era5_stage.get("n_divisions_in_era5_table", 0))
            else:
                log.info("  ERA5 stage: skipped (%s)", era5_stage.get("reason", "?"))
        else:
            log.warning("  Skipped: %s", weather_meta.get("reason"))

    df = base.merge(hawkes_df, on="cell_id", how="left")
    for c in ["hawkes_lambda", "hawkes_lambda_log", "hawkes_n_recent_10km_7d"]:
        df[c] = df[c].fillna(0)
    df["hawkes_nearest_ign_14d_km"] = df["hawkes_nearest_ign_14d_km"].fillna(50.0)

    log.info("Merging GLCM...")
    glcm = pd.read_parquet(GLCM_PATH)
    df = df.merge(glcm, on="cell_id", how="left")
    for c in [col for col in glcm.columns if col != "cell_id"]:
        df[c] = df[c].fillna(df[c].median())

    log.info("Merging Hydro...")
    hydro = pd.read_parquet(HYDRO_PATH)
    df = df.merge(hydro, on="cell_id", how="left")
    for c in [col for col in hydro.columns if col != "cell_id"]:
        df[c] = df[c].fillna(df[c].median())

    missing = [f for f in feat_names if f not in df.columns]
    if missing:
        log.error("Missing features: %s", missing)
        return 2

    log.info("Predicting...")
    probs = model.predict(df[feat_names].values)
    df["ignition_risk"] = probs
    log.info("  Raw risk range [%.4f, %.4f]", probs.min(), probs.max())

    hurdle_meta = None
    if args.use_hurdle_blend:
        stage_a, blend_cfg = _load_hurdle_blend()
        if stage_a is not None and blend_cfg is not None:
            stage_a_feats = stage_a.feature_name()
            missing_a = [f for f in stage_a_feats if f not in df.columns]
            if missing_a:
                log.warning("Hurdle blend skipped — Stage A missing %d features in df: %s",
                            len(missing_a), missing_a[:5])
            else:
                p_a = stage_a.predict(df[stage_a_feats].values)
                variant = blend_cfg.get("variant", "blend_geo_w0_7")
                df["stage_a_risk"] = p_a
                blended = _apply_hurdle_blend(probs, p_a, variant)
                df["ignition_risk"] = blended  # downstream rank/band uses this
                probs = blended
                hurdle_meta = {
                    "applied": True,
                    "variant": variant,
                    "blend_config": {k: blend_cfg.get(k) for k in
                                     ("low_hawkes_r5", "overall_r5",
                                      "delta_low_hawkes_pp", "delta_overall_pp")},
                }
                log.info("  Hurdle blend applied (variant=%s); blended range [%.4f, %.4f]",
                         variant, blended.min(), blended.max())
        else:
            log.warning("--use-hurdle-blend requested but Stage A or blend_config missing; "
                        "falling back to raw v17 probs.")

    # Per-beat history boost — applied AFTER hurdle blend, BEFORE banding,
    # so the boosted scores drive both rank-bands and banded_alerts ordering.
    beat_history_meta = {"applied": False, "reason": "flag not set"}
    if args.use_beat_history:
        log.info("Applying per-beat historical boost (--use-beat-history)...")
        df, beat_history_meta = apply_beat_history_boost(df, cells, target_date)
        if beat_history_meta["applied"]:
            log.info("  Boosted %d cells with history (range -> %s); %d cells unchanged",
                     beat_history_meta["n_cells_with_history"],
                     beat_history_meta["post_boost_risk_range"],
                     beat_history_meta["n_cells_no_history"])
            probs = df["ignition_risk"].values  # downstream rank/band uses this
        else:
            log.warning("  Skipped: %s", beat_history_meta["reason"])

    calib_params = _load_calibration()
    if calib_params is not None:
        df["calibrated_risk"] = _apply_calibration(probs, calib_params)
        log.info("  Calibrated risk range [%.4f, %.4f] (method=%s)",
                 df["calibrated_risk"].min(), df["calibrated_risk"].max(),
                 calib_params.get("method"))
    else:
        df["calibrated_risk"] = probs
        log.info("  No calibration JSON found — using raw scores")

    dashboard_dir = Path(args.output).parent
    rolling_history = (
        load_rolling_history(dashboard_dir, target_date, "v17", window_days=args.rank_window_days)
        if args.rank_window_days > 0 else np.array([], dtype=np.float32)
    )
    ranks, bands, rank_meta = compute_rank_bands(probs, rolling_history)
    df["rank"] = ranks
    df["band"] = bands

    log.info("  Bands: CRITICAL=%d ALERT=%d WATCH=%d",
             rank_meta["n_critical"], rank_meta["n_alert"], rank_meta["n_watch"])

    legacy_threshold = float(np.percentile(probs, 100 - args.top_pct))
    df["alert_legacy"] = (probs >= legacy_threshold).astype(int)

    cell_lookup = cells.set_index("cell_id")[["centroid_lat", "centroid_lon"]].to_dict("index")
    BAND_NAMES = {0: "NONE", 1: "WATCH", 2: "ALERT", 3: "CRITICAL"}

    banded_alerts = []
    for _, row in df[df["band"] > 0].sort_values("ignition_risk", ascending=False).iterrows():
        cid = row["cell_id"]
        if cid in cell_lookup:
            alert = {
                "cell_id": cid,
                "lat": cell_lookup[cid]["centroid_lat"],
                "lon": cell_lookup[cid]["centroid_lon"],
                "ignition_risk": float(row["ignition_risk"]),
                "calibrated_risk": float(row["calibrated_risk"]),
                "rank": float(row["rank"]),
                "band": BAND_NAMES[int(row["band"])],
                "hawkes_n_recent_10km_7d": int(row["hawkes_n_recent_10km_7d"]),
                "hawkes_lambda": float(row["hawkes_lambda"]),
            }
            if "stage_a_risk" in row:
                alert["stage_a_risk"] = float(row["stage_a_risk"])
            banded_alerts.append(alert)

    alerts_all_cells = [
        {"cell_id": cid, "ignition_risk": float(r)}
        for cid, r in zip(df["cell_id"].values, probs)
    ]

    out = {
        "model": "v17_ba_pu",
        "training_labels": "BA-augmented tiered PU (GOLD/SILVER/BRONZE weighted positives)",
        "prediction_date": target_date.strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "n_cells_total": int(len(df)),
        "rank_calibration": rank_meta,
        "hurdle_blend": hurdle_meta,
        "live_weather": weather_meta,
        "beat_history_boost": beat_history_meta,
        "probability_calibration": (
            {k: calib_params[k] for k in ("method", "brier", "logloss",
                                          "baseline_brier", "n_calibration",
                                          "n_validation") if k in calib_params}
            if calib_params else None
        ),
        "legacy_top_pct": {
            "top_pct": args.top_pct,
            "threshold": legacy_threshold,
            "n_cells": int(df["alert_legacy"].sum()),
        },
        "metrics_on_validation": {
            "roc_auc": 0.8815,
            "pr_auc": 0.1481,
            "recall_top5pct": 0.4741,
            "perday_recall_top5pct": 0.4856,
            "vs_v15_delta_recall_top5pct": 0.0696,
            "vs_v15_delta_perday_recall_top5pct": 0.1546,
        },
        "banded_alerts": banded_alerts,
        "alerts_all_cells": alerts_all_cells,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("Saved: %s", out_path)

    dated_path = out_path.parent / f"ignition_risk_v17_{target_date.strftime('%Y-%m-%d')}.json"
    dated_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("Saved dated copy: %s", dated_path)

    log.info("\n=== TOP 10 BANDED IGNITION ALERTS (v17) ===")
    for a in banded_alerts[:10]:
        log.info("  [%s] %s lat=%.3f lon=%.3f risk=%.4f rank=%.4f n_recent=%d",
                 a["band"], a["cell_id"], a["lat"], a["lon"],
                 a["ignition_risk"], a["rank"], a["hawkes_n_recent_10km_7d"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
