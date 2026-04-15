"""Stage H.4 — v17 daily field-validation backtest.

For each prediction date D where we have a dated v17 JSON, compare the top-5%
cells flagged by v17 on date D against the actual FIRMS DBSCAN ignitions that
occurred in [D, D+7]. Computes:
  - Observed R@top-5% (of actual ignitions, how many in the v17 top-5%?)
  - Observed precision-at-CRITICAL-band (of CRITICAL cells, how many ignited?)
  - Observed lead time (hours between v17 prediction and first ignition in cell)

Output: `data_lake/alerts/v17_validation_rolling.parquet`
  Columns: prediction_date, n_top5pct, n_actual_ignitions_d_to_d7,
           n_catches_in_top5pct, observed_recall_top5pct,
           n_critical_alerts, n_critical_hits, observed_precision_critical,
           lead_time_hours_median

Intended to be called daily (or as periodic backtest) with --days 30.

Usage:
  python scripts/validate_v17_daily.py --days 30
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
FIRMS_PATH = ROOT / "data_lake" / "fire_detections" / "firms_dbscan_ignition.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_PATH = ROOT / "data_lake" / "alerts" / "v17_validation_rolling.parquet"

KM_PER_DEG_LAT = 110.6
LOOKAHEAD_DAYS = 7
CELL_MATCH_KM = 2.0


def build_firms_cell_date_index(firms_df: pd.DataFrame, cells_df: pd.DataFrame) -> dict:
    """Build lookup: (cell_id, date) → list of ignition datetimes in that cell."""
    cells_km = np.column_stack([
        cells_df["centroid_lon"].values * np.cos(np.radians(cells_df["centroid_lat"].values)) * KM_PER_DEG_LAT,
        cells_df["centroid_lat"].values * KM_PER_DEG_LAT,
    ])
    tree = cKDTree(cells_km)

    firms_km = np.column_stack([
        firms_df["longitude"].values * np.cos(np.radians(firms_df["latitude"].values)) * KM_PER_DEG_LAT,
        firms_df["latitude"].values * KM_PER_DEG_LAT,
    ])
    _, idx = tree.query(firms_km, k=1)
    firms_df = firms_df.copy()
    firms_df["cell_id"] = cells_df["cell_id"].values[idx]
    firms_df["date"] = firms_df["acq_date"].dt.date
    return firms_df


def validate_one_date(pred_date: pd.Timestamp, firms_enriched: pd.DataFrame) -> dict | None:
    """Compute validation metrics for one prediction date."""
    dated_file = FEED_DIR / f"ignition_risk_v17_{pred_date.strftime('%Y-%m-%d')}.json"
    if not dated_file.exists():
        return None
    try:
        payload = json.loads(dated_file.read_text())
    except Exception as e:
        log.warning("  failed to load %s: %s", dated_file.name, e)
        return None

    all_cells = payload.get("alerts_all_cells", [])
    if not all_cells:
        return None
    df_pred = pd.DataFrame(all_cells)
    df_pred["risk_rank"] = df_pred["ignition_risk"].rank(pct=True, ascending=True)

    # Top 5% cells
    top5 = df_pred[df_pred["risk_rank"] >= 0.95]["cell_id"].tolist()
    n_top5 = len(top5)

    # Banded alerts
    banded = payload.get("banded_alerts", [])
    critical = [b["cell_id"] for b in banded if b.get("band") == "CRITICAL"]
    n_critical = len(critical)

    # Actual ignitions in [D, D+7]
    window_start = pred_date.date()
    window_end = (pred_date + pd.Timedelta(days=LOOKAHEAD_DAYS)).date()
    actual = firms_enriched[
        (firms_enriched["date"] >= window_start) & (firms_enriched["date"] <= window_end)
    ]
    actual_cells = set(actual["cell_id"].tolist())
    n_actual = len(actual_cells)

    catches_top5 = len(set(top5) & actual_cells)
    catches_critical = len(set(critical) & actual_cells)

    # Lead time: for critical cells that did ignite, how many hours ahead did we predict?
    critical_hits = actual[actual["cell_id"].isin(critical)]
    if len(critical_hits):
        hit_times = pd.to_datetime(
            critical_hits["acq_date"].astype(str) + " " + critical_hits["acq_time"].astype(str).str.zfill(4),
            format="%Y-%m-%d %H%M", errors="coerce",
        )
        lead_hours = ((hit_times - pred_date).dt.total_seconds() / 3600.0).dropna()
        lead_median = float(lead_hours.median()) if len(lead_hours) else None
    else:
        lead_median = None

    return {
        "prediction_date": pred_date.strftime("%Y-%m-%d"),
        "n_top5pct": n_top5,
        "n_actual_ignitions_d_to_d7": n_actual,
        "n_catches_in_top5pct": catches_top5,
        "observed_recall_top5pct": (catches_top5 / n_actual) if n_actual else None,
        "n_critical_alerts": n_critical,
        "n_critical_hits": catches_critical,
        "observed_precision_critical": (catches_critical / n_critical) if n_critical else None,
        "lead_time_hours_median": lead_median,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--end-date", type=str, default=None, help="End date for backtest (default: today)")
    args = parser.parse_args()

    end = pd.Timestamp(args.end_date) if args.end_date else pd.Timestamp.now().normalize()
    start = end - pd.Timedelta(days=args.days)
    log.info("Validating v17 predictions: %s → %s (window %d days + %d lookahead)",
             start.date(), end.date(), args.days, LOOKAHEAD_DAYS)

    log.info("Loading FIRMS DBSCAN + cells...")
    firms = pd.read_parquet(FIRMS_PATH)
    firms = firms[firms["is_ignition"] == 1].copy()
    firms["acq_date"] = pd.to_datetime(firms["acq_date"])
    cells = pd.read_csv(CELLS_PATH)
    firms_enriched = build_firms_cell_date_index(firms, cells)
    log.info("  %d ignitions loaded + cell-indexed", len(firms_enriched))

    rows = []
    dates = pd.date_range(start, end, freq="D")
    for d in dates:
        res = validate_one_date(d, firms_enriched)
        if res is not None:
            rows.append(res)
    if not rows:
        log.warning("No dated v17 JSONs found in %s for window %s → %s",
                    FEED_DIR, start.date(), end.date())
        return 0

    df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    log.info("\n=== v17 FIELD VALIDATION ===")
    log.info("%d dates with predictions", len(df))
    if df["observed_recall_top5pct"].notna().any():
        log.info("R@top-5%% observed — median=%.3f p25=%.3f p75=%.3f",
                 df["observed_recall_top5pct"].median(),
                 df["observed_recall_top5pct"].quantile(0.25),
                 df["observed_recall_top5pct"].quantile(0.75))
    if df["observed_precision_critical"].notna().any():
        log.info("Precision@CRITICAL — median=%.3f",
                 df["observed_precision_critical"].median())
    if df["lead_time_hours_median"].notna().any():
        log.info("Lead time (hours) — median=%.1f", df["lead_time_hours_median"].median())
    log.info("\nSaved: %s", OUT_PATH.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
