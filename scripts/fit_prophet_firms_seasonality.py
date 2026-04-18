"""Fit Prophet on MP statewide daily FRP history to produce a seasonal baseline.

Outputs a JSON the v3 portal consumes to display:
  - Actual daily FRP (last ~120 days)
  - 28-day rolling average
  - Prophet seasonal forecast for the ongoing season
  - Yhat confidence interval
  - Drift flag: is today's FRP > yhat_upper (elevated) or < yhat_lower (quiet)

This is a *diagnostic* layer — not used for cell-level prediction. Purpose:
give DFOs a "season pulse" view to calibrate preparedness independent of v17.
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FIRMS = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
OUT = ROOT / "outputs" / "dashboard_feed" / "seasonal_pulse.json"

TRAIN_YEARS = (2019, 2025)  # fit on 2019-01-01 .. 2025-12-31
FORECAST_DAYS_AHEAD = 60     # predict 60 days past max actual date
RECENT_WINDOW_DAYS = 120     # show last 120 days of actual data in chart


def load_daily_frp() -> pd.DataFrame:
    """Aggregate to daily statewide FRP sum + n_detections."""
    log.info("Loading FIRMS consolidated parquet...")
    f = pd.read_parquet(FIRMS, columns=["acq_date", "frp", "confidence"])
    f["acq_date"] = pd.to_datetime(f["acq_date"])
    # Accept both historical abbreviations ("n", "h") and full strings ("nominal", "high")
    # "low" / "l" are dropped as noise.
    f = f[f["confidence"].isin(["n", "h", "nominal", "high"])].copy()
    log.info("  %d high-confidence detections 2014-2026", len(f))
    daily = f.groupby("acq_date").agg(
        frp_sum=("frp", "sum"),
        frp_median=("frp", "median"),
        n_detect=("frp", "count"),
    ).reset_index()
    daily = daily.sort_values("acq_date").reset_index(drop=True)
    log.info("  Daily series: %d days, %s to %s",
             len(daily), daily["acq_date"].min().date(),
             daily["acq_date"].max().date())
    return daily


def fit_prophet(daily: pd.DataFrame):
    """Train Prophet on TRAIN_YEARS window, predict forward FORECAST_DAYS."""
    from prophet import Prophet
    train_start = pd.Timestamp(f"{TRAIN_YEARS[0]}-01-01")
    train_end = pd.Timestamp(f"{TRAIN_YEARS[1]}-12-31")
    train = daily[(daily["acq_date"] >= train_start) & (daily["acq_date"] <= train_end)].copy()
    train = train.rename(columns={"acq_date": "ds", "frp_sum": "y"})
    train = train[["ds", "y"]]
    log.info("Training Prophet on %d days (%s to %s)...",
             len(train), train["ds"].min().date(), train["ds"].max().date())

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
        interval_width=0.90,
    )
    # Log-transform to handle the heavy-tailed FRP distribution (add 1 for zeros)
    train["y_orig"] = train["y"].copy()
    train["y"] = np.log1p(train["y"])
    model.fit(train[["ds", "y"]])

    max_actual = daily["acq_date"].max()
    future_end = max_actual + pd.Timedelta(days=FORECAST_DAYS_AHEAD)
    future = pd.DataFrame({
        "ds": pd.date_range(train_start, future_end, freq="D")
    })
    log.info("Predicting %d days (up to %s)...",
             len(future), future_end.date())
    forecast = model.predict(future)
    # Back-transform
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        forecast[col] = np.expm1(forecast[col]).clip(lower=0)
    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]


def build_pulse_payload(daily: pd.DataFrame, forecast: pd.DataFrame) -> dict:
    daily = daily.copy().sort_values("acq_date")
    daily["frp_28d_rolling"] = daily["frp_sum"].rolling(28, min_periods=7).mean()

    max_actual = daily["acq_date"].max()
    chart_start = max_actual - pd.Timedelta(days=RECENT_WINDOW_DAYS)
    recent = daily[daily["acq_date"] >= chart_start].copy()

    # Merge forecast on the recent + forward window
    fc_range = forecast[
        (forecast["ds"] >= chart_start)
        & (forecast["ds"] <= max_actual + pd.Timedelta(days=FORECAST_DAYS_AHEAD))
    ].copy()

    # Drift status for today (latest actual)
    latest = daily.iloc[-1]
    latest_fc = forecast[forecast["ds"] == latest["acq_date"]]
    drift = {"status": "UNKNOWN"}
    if len(latest_fc):
        lf = latest_fc.iloc[0]
        y = float(latest["frp_sum"])
        if y > float(lf["yhat_upper"]):
            status = "ELEVATED"
        elif y < float(lf["yhat_lower"]):
            status = "QUIET"
        else:
            status = "TYPICAL"
        drift = {
            "status": status,
            "actual_frp_sum": y,
            "expected_yhat": float(lf["yhat"]),
            "expected_upper": float(lf["yhat_upper"]),
            "expected_lower": float(lf["yhat_lower"]),
            "z_vs_expected": (y - float(lf["yhat"])) / max(float(lf["yhat"]), 1e-6),
        }

    series = []
    for _, r in recent.iterrows():
        fc_row = fc_range[fc_range["ds"] == r["acq_date"]]
        yhat = float(fc_row["yhat"].iloc[0]) if len(fc_row) else None
        y_lower = float(fc_row["yhat_lower"].iloc[0]) if len(fc_row) else None
        y_upper = float(fc_row["yhat_upper"].iloc[0]) if len(fc_row) else None
        series.append({
            "date": r["acq_date"].strftime("%Y-%m-%d"),
            "frp_sum": float(r["frp_sum"]),
            "frp_28d": None if pd.isna(r["frp_28d_rolling"]) else float(r["frp_28d_rolling"]),
            "n_detect": int(r["n_detect"]),
            "yhat": yhat,
            "yhat_lower": y_lower,
            "yhat_upper": y_upper,
        })

    # Future-only forecast (past max_actual)
    future_only = []
    for _, r in fc_range[fc_range["ds"] > max_actual].iterrows():
        future_only.append({
            "date": r["ds"].strftime("%Y-%m-%d"),
            "yhat": float(r["yhat"]),
            "yhat_lower": float(r["yhat_lower"]),
            "yhat_upper": float(r["yhat_upper"]),
        })

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "train_window": {"start": f"{TRAIN_YEARS[0]}-01-01",
                         "end": f"{TRAIN_YEARS[1]}-12-31"},
        "latest_actual_date": max_actual.strftime("%Y-%m-%d"),
        "drift": drift,
        "series_recent": series,
        "forecast_forward": future_only,
    }


def main() -> int:
    if not FIRMS.exists():
        log.error("FIRMS parquet missing: %s", FIRMS)
        return 1
    daily = load_daily_frp()
    forecast = fit_prophet(daily)
    payload = build_pulse_payload(daily, forecast)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    log.info("Wrote: %s", OUT.relative_to(ROOT))
    log.info("Latest actual (%s): FRP_sum=%.0f, expected=%.0f [%.0f..%.0f], drift=%s",
             payload["latest_actual_date"],
             payload["drift"].get("actual_frp_sum", 0),
             payload["drift"].get("expected_yhat", 0),
             payload["drift"].get("expected_lower", 0),
             payload["drift"].get("expected_upper", 0),
             payload["drift"]["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
