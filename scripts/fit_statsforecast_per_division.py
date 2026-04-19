"""Per-division seasonal baselines using Nixtla StatsForecast AutoARIMA.

For each of ~87 MP forest divisions, fit AutoARIMA on 2019-2025 daily FRP
and report drift status (ELEVATED / TYPICAL / QUIET) for the latest day.

Why per-division: the statewide Prophet baseline doesn't tell a DFO whether
THEIR division is anomalous. Numba-compiled AutoARIMA handles 87 divisions
in well under a minute.
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FIRMS = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
CELLS = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT = ROOT / "outputs" / "dashboard_feed" / "division_pulse.json"

TRAIN_START = "2019-01-01"
MIN_DAYS_FOR_FIT = 400   # need enough data per division
FORECAST_HORIZON = 14    # days forward to forecast


def assign_firms_to_division(firms: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """Each FIRMS detection -> nearest cell's division."""
    log.info("Spatially joining %d FIRMS to %d cells...", len(firms), len(cells))
    cell_coords_rad = np.deg2rad(cells[["centroid_lat", "centroid_lon"]].to_numpy())
    tree = BallTree(cell_coords_rad, metric="haversine")
    fire_coords = np.deg2rad(firms[["latitude", "longitude"]].to_numpy())
    _, idx = tree.query(fire_coords, k=1)
    firms = firms.copy()
    firms["division"] = cells["division"].iloc[idx.ravel()].values
    return firms


def fit_division(group: pd.DataFrame) -> dict | None:
    """Fit AutoARIMA on one division's daily FRP series."""
    from statsforecast import StatsForecast
    from statsforecast.models import AutoARIMA

    group = group.sort_values("ds").reset_index(drop=True)
    if len(group) < MIN_DAYS_FOR_FIT:
        return None
    # Log transform for heavy-tailed FRP
    group["y_raw"] = group["y"].copy()
    group["y"] = np.log1p(group["y"])

    sf = StatsForecast(
        models=[AutoARIMA(season_length=7)],  # weekly seasonality
        freq="D",
        n_jobs=1,
    )
    try:
        # single series -> unique_id required
        df = group[["ds", "y"]].copy()
        df["unique_id"] = "series"
        df = df[["unique_id", "ds", "y"]]
        forecast = sf.forecast(df=df, h=FORECAST_HORIZON, level=[90])
        forecast = forecast.rename(columns={
            "AutoARIMA": "yhat",
            "AutoARIMA-lo-90": "yhat_lower",
            "AutoARIMA-hi-90": "yhat_upper",
        })
        for c in ("yhat", "yhat_lower", "yhat_upper"):
            forecast[c] = np.expm1(forecast[c]).clip(lower=0)
    except Exception as e:
        log.debug("fit failed: %s", e)
        return None

    # In-sample last day: compute residual vs actual
    latest_actual = group.iloc[-1]
    # For drift flag we compare forecast-at-last-date's uncertainty vs latest actual
    # Simpler: use 7-day rolling mean of actual and compare with forecast[0]
    last7_mean = float(np.expm1(group["y"].tail(7).mean()))
    y_raw = float(latest_actual["y_raw"])
    first_fc = forecast.iloc[0]
    expected = float(first_fc["yhat"])
    upper = float(first_fc["yhat_upper"])
    lower = float(first_fc["yhat_lower"])
    if y_raw > upper:
        status = "ELEVATED"
    elif y_raw < lower:
        status = "QUIET"
    else:
        status = "TYPICAL"

    return {
        "latest_actual_date": latest_actual["ds"].strftime("%Y-%m-%d"),
        "latest_actual_frp": y_raw,
        "last7_mean_frp": last7_mean,
        "expected_yhat": expected,
        "expected_lower": lower,
        "expected_upper": upper,
        "drift_status": status,
        "z_vs_expected": (y_raw - expected) / max(expected, 1.0),
        "forecast_next_14d": forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]
            .to_dict(orient="records"),
        "n_training_days": int(len(group)),
    }


def main() -> int:
    if not FIRMS.exists():
        log.error("FIRMS missing: %s", FIRMS); return 1
    if not CELLS.exists():
        log.error("Cells CSV missing: %s", CELLS); return 1

    log.info("Loading FIRMS...")
    f = pd.read_parquet(FIRMS, columns=["latitude", "longitude", "acq_date",
                                        "frp", "confidence"])
    f["acq_date"] = pd.to_datetime(f["acq_date"])
    f = f[f["confidence"].isin(["n", "h", "nominal", "high"])].copy()
    f = f[f["acq_date"] >= pd.Timestamp(TRAIN_START)].copy()
    log.info("  %d high-conf detections since %s", len(f), TRAIN_START)

    log.info("Loading cells grid...")
    cells = pd.read_csv(CELLS, usecols=["centroid_lat", "centroid_lon", "division"])

    f = assign_firms_to_division(f, cells)
    log.info("  Assigned to %d unique divisions", f["division"].nunique())

    # Daily aggregation per division
    daily = f.groupby(["division", "acq_date"]).agg(
        frp_sum=("frp", "sum"), n_detect=("frp", "count")
    ).reset_index()
    daily = daily.rename(columns={"acq_date": "ds", "frp_sum": "y"})

    # Fill gaps with zeros so the AutoARIMA sees a continuous series per division
    all_dates = pd.date_range(daily["ds"].min(), daily["ds"].max(), freq="D")
    filled_frames = []
    for div, grp in daily.groupby("division"):
        g = grp.set_index("ds").reindex(all_dates, fill_value=0)
        g["ds"] = g.index
        g["division"] = div
        filled_frames.append(g.reset_index(drop=True))
    daily = pd.concat(filled_frames, ignore_index=True)

    results: dict[str, dict] = {}
    divisions = sorted(daily["division"].unique())
    log.info("Fitting AutoARIMA for %d divisions...", len(divisions))
    for i, div in enumerate(divisions, 1):
        grp = daily[daily["division"] == div]
        r = fit_division(grp)
        if r is not None:
            results[div] = r
        if i % 10 == 0:
            log.info("  ... %d/%d divisions fit", i, len(divisions))

    elevated = sum(1 for v in results.values() if v["drift_status"] == "ELEVATED")
    quiet = sum(1 for v in results.values() if v["drift_status"] == "QUIET")
    typical = sum(1 for v in results.values() if v["drift_status"] == "TYPICAL")
    log.info("  drift tags: ELEVATED=%d  TYPICAL=%d  QUIET=%d  (total %d)",
             elevated, typical, quiet, len(results))

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "model": "AutoARIMA (Nixtla StatsForecast)",
        "train_window_start": TRAIN_START,
        "n_divisions_fit": len(results),
        "summary": {"ELEVATED": elevated, "TYPICAL": typical, "QUIET": quiet},
        "divisions": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    log.info("Wrote: %s", OUT.relative_to(ROOT))

    log.info("Sample top-5 elevated divisions:")
    by_z = sorted(results.items(),
                  key=lambda kv: -kv[1]["z_vs_expected"])
    for div, v in by_z[:5]:
        log.info("  %-25s %-9s z=%+.2f actual=%.0f exp=%.0f",
                 div, v["drift_status"], v["z_vs_expected"],
                 v["latest_actual_frp"], v["expected_yhat"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
