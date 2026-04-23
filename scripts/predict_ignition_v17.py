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
BEAT_CLIMATOLOGY_PARQUET = ROOT / "data_lake" / "fire_weather" / "beat_fire_climatology.parquet"

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


def apply_live_weather_overrides(df: pd.DataFrame, target_date: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Replace 10 stale wx_* columns in df with TODAY's FWI values.

    The v8 base dataset is frozen at 2025-05-29. Without this override, every
    prediction inherits ~11-month-stale weather. Replacing the 10 directly-
    mappable columns with the live `fwi_daily.parquet` value for `target_date`
    (or the most-recent prior date if missing) restores topical fire weather
    inputs to the model. The 28 derived wx_* features (rolling means, anomalies,
    soil moisture, LST) stay at v8 frozen values -- recomputing them needs a
    weather raster we don't have fresh; this is a best-effort partial.

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

    overrides_applied = {}
    deltas = {}
    for fwi_col, wx_col in FWI_TO_WX.items():
        if wx_col not in df.columns or fwi_col not in row.index:
            continue
        old_median = float(df[wx_col].median()) if df[wx_col].notna().any() else None
        new_value = float(row[fwi_col])
        df[wx_col] = new_value  # broadcast statewide value to all cells
        overrides_applied[wx_col] = new_value
        if old_median is not None:
            deltas[wx_col] = round(new_value - old_median, 3)

    return df, {
        "applied": True,
        "fwi_date_used": str(fwi_date),
        "n_columns_overridden": len(overrides_applied),
        "overrides": overrides_applied,
        "deltas_vs_v8_frozen": deltas,
        "note": ("28 derived wx_* columns (rolling means, soil, LST) still come "
                 "from v8 frozen 2025-05-29 -- not recomputable without weather raster"),
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
        base, weather_meta = apply_live_weather_overrides(base, target_date)
        if weather_meta["applied"]:
            log.info("  Overrode %d wx_* columns with FWI from %s",
                     weather_meta["n_columns_overridden"], weather_meta["fwi_date_used"])
            log.info("  Sample deltas vs v8: %s",
                     {k: v for k, v in list(weather_meta["deltas_vs_v8_frozen"].items())[:5]})
        else:
            log.warning("  Skipped: %s", weather_meta["reason"])

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
