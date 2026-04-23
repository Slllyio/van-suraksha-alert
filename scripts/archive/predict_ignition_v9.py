"""Production deployment helper for v9_hawkes_ignition.

Loads v9 model + computes daily Hawkes intensity from last 30 days of FIRMS,
then scores every cell for tomorrow. Outputs JSON for dashboard ingestion.

Usage (in daily_fire_alert.py):
  python scripts/predict_ignition_v9.py --date 2026-04-15
  python scripts/predict_ignition_v9.py --date 2026-04-15 --output dashboard_feed/ignition_risk.json
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
V9_MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v9_hawkes_ignition" / "model.txt"
V8_DATASET = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan" / "dataset.parquet"
FIRMS_PATH = ROOT / "data_lake" / "fire_detections" / "firms_dbscan_ignition.parquet"
HAWKES_PARAMS = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_params.json"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"

KM_PER_DEG_LAT = 110.6
KM_PER_DEG_LON = 101.4
SEARCH_RADIUS_KM = 30.0


def compute_hawkes_for_date(target_date: pd.Timestamp, ign_df: pd.DataFrame, cells_df: pd.DataFrame,
                            params: dict) -> pd.DataFrame:
    """Compute Hawkes features for all cells on a target date using past ignitions.

    Returns DataFrame with [cell_id, hawkes_lambda, hawkes_lambda_log,
    hawkes_n_recent_10km_7d, hawkes_nearest_ign_14d_km].
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


def load_rolling_history(dashboard_dir: Path, target_date: pd.Timestamp, window_days: int = 7) -> np.ndarray:
    """Load raw ignition_risk values from the past N days for rolling-window rank calibration.

    Returns a flat array of all historical predictions in [target_date - window_days, target_date - 1 day].
    Returns empty array if no history found (caller falls back to within-day ranks).
    """
    history = []
    for i in range(1, window_days + 1):
        prior = target_date - timedelta(days=i)
        # File naming convention: ignition_risk_v9_YYYY-MM-DD.json OR ignition_risk_v9.json (today's)
        dated = dashboard_dir / f"ignition_risk_v9_{prior.strftime('%Y-%m-%d')}.json"
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
                       band_thresholds: tuple[float, float, float] = (0.95, 0.98, 0.995)) -> tuple[np.ndarray, np.ndarray, dict]:
    """Compute rank-based alert bands using a rolling reference distribution.

    Args:
        probs: today's model probabilities (n_cells,)
        rolling_history: flat array of past N days' probabilities; if empty, falls back to today-only
        band_thresholds: (watch_pct, alert_pct, critical_pct) as fractions 0-1

    Returns:
        ranks: per-cell percentile rank within the reference distribution (0-1)
        bands: per-cell band code (0=none, 1=WATCH, 2=ALERT, 3=CRITICAL)
        meta: dict with reference distribution stats
    """
    # Combine today + rolling history into reference distribution.
    # Today's predictions MUST be in the reference so self-rank is well-defined.
    if rolling_history.size > 0:
        reference = np.concatenate([probs, rolling_history])
        mode = f"rolling_{rolling_history.size}_pts_plus_today"
    else:
        reference = probs
        mode = "within_day_fallback"

    # Compute absolute thresholds at each band cut-off
    watch_thr = float(np.quantile(reference, band_thresholds[0]))
    alert_thr = float(np.quantile(reference, band_thresholds[1]))
    crit_thr = float(np.quantile(reference, band_thresholds[2]))

    # Rank each cell: percentile position within reference
    ref_sorted = np.sort(reference)
    ranks = np.searchsorted(ref_sorted, probs, side="right") / len(ref_sorted)

    # Assign bands
    bands = np.zeros(len(probs), dtype=np.int8)
    bands[probs >= watch_thr] = 1   # WATCH
    bands[probs >= alert_thr] = 2   # ALERT
    bands[probs >= crit_thr] = 3    # CRITICAL

    meta = {
        "mode": mode,
        "reference_size": int(len(reference)),
        "rolling_history_size": int(rolling_history.size),
        "today_size": int(probs.size),
        "watch_threshold": watch_thr,
        "alert_threshold": alert_thr,
        "critical_threshold": crit_thr,
        "n_watch": int(((bands == 1)).sum()),
        "n_alert": int(((bands == 2)).sum()),
        "n_critical": int(((bands == 3)).sum()),
    }
    return ranks, bands, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Target prediction date (YYYY-MM-DD). Default: tomorrow.")
    ap.add_argument("--top-pct", type=float, default=5.0, help="Output top N%% of cells by risk (legacy absolute mode)")
    ap.add_argument("--rank-window-days", type=int, default=7,
                    help="Rolling window in days for rank-based banding (PS-4). 0 = disable rank mode.")
    ap.add_argument("--output", default=str(ROOT / "outputs" / "dashboard_feed" / "ignition_risk_v9.json"))
    args = ap.parse_args()

    target_date = pd.Timestamp(args.date) if args.date else pd.Timestamp(datetime.now().date() + timedelta(days=1))
    log.info("v9_hawkes_ignition prediction for %s", target_date.date())

    log.info("Loading v9 model + Hawkes params...")
    model = lgb.Booster(model_file=str(V9_MODEL))
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

    log.info("Computing Hawkes features for %s...", target_date.date())
    t0 = time.time()
    hawkes_df = compute_hawkes_for_date(target_date, ign, cells, params)
    log.info("  Done in %.1fs", time.time() - t0)

    log.info("Loading base features from v8 dataset (most recent date as proxy for today)...")
    # In production, base features (weather, NDVI etc.) should come from a daily refresh.
    # Here we use the most recent available date in v8 dataset as a stand-in.
    ds = pd.read_parquet(V8_DATASET)
    ds["date"] = pd.to_datetime(ds["date"])
    most_recent = ds["date"].max()
    log.info("  Using base features from %s as stand-in for production daily refresh", most_recent.date())
    base = ds[ds["date"] == most_recent].drop(columns=["date", "label", "label_dbscan_ignition",
                                                        "n_ignitions", "n_dets", "max_frp"], errors="ignore")
    log.info("  %d base feature rows", len(base))

    log.info("Merging Hawkes features...")
    df = base.merge(hawkes_df, on="cell_id", how="left")
    for c in ["hawkes_lambda", "hawkes_lambda_log", "hawkes_n_recent_10km_7d"]:
        df[c] = df[c].fillna(0)
    df["hawkes_nearest_ign_14d_km"] = df["hawkes_nearest_ign_14d_km"].fillna(50.0)

    # Predict
    log.info("Predicting...")
    X = df[feat_names].values
    probs = model.predict(X)
    df["ignition_risk"] = probs

    # --- PS-4: Rank-based banding over rolling 7-day window ---
    dashboard_dir = Path(args.output).parent
    rolling_history = (
        load_rolling_history(dashboard_dir, target_date, window_days=args.rank_window_days)
        if args.rank_window_days > 0 else np.array([], dtype=np.float32)
    )
    ranks, bands, rank_meta = compute_rank_bands(probs, rolling_history)
    df["rank"] = ranks
    df["band"] = bands

    log.info("  Rank mode: %s (reference N=%d)", rank_meta["mode"], rank_meta["reference_size"])
    log.info("  Bands: CRITICAL=%d ALERT=%d WATCH=%d",
             rank_meta["n_critical"], rank_meta["n_alert"], rank_meta["n_watch"])
    log.info("  Thresholds: watch=%.4f alert=%.4f critical=%.4f",
             rank_meta["watch_threshold"], rank_meta["alert_threshold"], rank_meta["critical_threshold"])

    # --- Legacy absolute top-N% (kept for backward compat) ---
    legacy_threshold = float(np.percentile(probs, 100 - args.top_pct))
    df["alert_legacy"] = (probs >= legacy_threshold).astype(int)
    log.info("  Legacy top-%.0f%% threshold: %.4f (%d cells)",
             args.top_pct, legacy_threshold, int(df["alert_legacy"].sum()))

    # Output both the banded alerts and the full cell list (for rolling history reuse)
    cell_lookup = cells.set_index("cell_id")[["centroid_lat", "centroid_lon"]].to_dict("index")
    BAND_NAMES = {0: "NONE", 1: "WATCH", 2: "ALERT", 3: "CRITICAL"}

    banded_alerts = []
    for _, row in df[df["band"] > 0].sort_values("ignition_risk", ascending=False).iterrows():
        cid = row["cell_id"]
        if cid in cell_lookup:
            banded_alerts.append({
                "cell_id": cid,
                "lat": cell_lookup[cid]["centroid_lat"],
                "lon": cell_lookup[cid]["centroid_lon"],
                "ignition_risk": float(row["ignition_risk"]),
                "rank": float(row["rank"]),
                "band": BAND_NAMES[int(row["band"])],
                "hawkes_n_recent_10km_7d": int(row["hawkes_n_recent_10km_7d"]),
                "hawkes_lambda": float(row["hawkes_lambda"]),
            })

    # Include ALL cells' raw risk in a separate key so tomorrow's run can use it for rolling reference
    alerts_all_cells = [
        {"cell_id": cid, "ignition_risk": float(r)}
        for cid, r in zip(df["cell_id"].values, probs)
    ]

    out = {
        "model": "v9_hawkes_ignition",
        "prediction_date": target_date.strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "n_cells_total": int(len(df)),
        "rank_calibration": rank_meta,
        "legacy_top_pct": {
            "top_pct": args.top_pct,
            "threshold": legacy_threshold,
            "n_cells": int(df["alert_legacy"].sum()),
        },
        "metrics_on_validation": {
            "roc_auc": 0.8626,
            "pr_auc": 0.0383,
            "recall_top5pct": 0.3937,
            "perday_recall_top5pct": 0.2898,
        },
        "banded_alerts": banded_alerts,
        "alerts_all_cells": alerts_all_cells,  # for rolling-window reuse
    }

    # Write BOTH latest + dated copy so rolling window can find past runs
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("Saved: %s", out_path)

    dated_path = out_path.parent / f"ignition_risk_v9_{target_date.strftime('%Y-%m-%d')}.json"
    dated_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("Saved dated copy: %s", dated_path)
    log.info("\n=== TOP 10 BANDED IGNITION ALERTS ===")
    for a in banded_alerts[:10]:
        log.info("  [%s] %s lat=%.3f lon=%.3f risk=%.4f rank=%.4f n_recent_10km_7d=%d",
                 a["band"], a["cell_id"], a["lat"], a["lon"],
                 a["ignition_risk"], a["rank"], a["hawkes_n_recent_10km_7d"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
