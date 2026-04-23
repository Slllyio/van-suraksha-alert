"""Ingest ERA5 daily weather per MP forest division via Open-Meteo Archive.

Fixes the 11-month-stale-weather problem in v17.6:
  - The v8 base feature dataset is frozen at 2025-05-29.
  - `apply_live_weather_overrides()` (predict_ignition_v17.py) replaces 10
    direct wx_* columns with live FWI but the OTHER 28 derived wx_* columns
    (rolling 7d/14d/30d means, anomalies, VPD, soil, LST, srad) stay frozen.
  - This script pulls ERA5 daily values from Open-Meteo Archive (free, no
    auth, ECMWF-derived, ~9 km resolution) at each division centroid,
    computes the rolling stats + anomalies, and writes a parquet that
    predict_ignition_v17.py can join on `division`.

Output: data_lake/fire_weather/era5_per_division_daily.parquet
  Schema (per (division, date)):
    division, date,
    air_temp_c, air_temp_max, air_temp_min, dtr,
    rh_pct, dewpoint_c, vpd_kpa,
    wind_kmh_max,
    precip_mm,
    srad_mj,
    soil_moisture_0_7cm, soil_moisture_7_28cm,
    et0_mm,
    -- Rolling stats:
    precip_7d, precip_14d, precip_30d, consecutive_dry,
    temp_7d_mean, rh_7d_min, wind_7d_max, vpd_7d_max,
    -- Anomalies (vs 2020-2024 climatology for same DOY):
    temp_anom, rh_anom, wind_anom, precip_anom

Usage:
  python scripts/ingest_era5_per_division.py
  python scripts/ingest_era5_per_division.py --start 2020-01-01 --end 2026-04-23
"""
from __future__ import annotations
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
CELLS_CSV = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_PATH = ROOT / "data_lake" / "fire_weather" / "era5_per_division_daily.parquet"

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# Variables we pull (Open-Meteo names → our standard names)
DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "relative_humidity_2m_mean",
    "dewpoint_2m_mean",
    "wind_speed_10m_max",
    "precipitation_sum",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "soil_moisture_0_to_7cm_mean",
    "soil_moisture_7_to_28cm_mean",
    "vapour_pressure_deficit_max",
]


def fetch_division(division: str, lat: float, lon: float,
                   start_date: str, end_date: str,
                   timeout: int = 60, max_retries: int = 5) -> pd.DataFrame | None:
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "timezone": "Asia/Kolkata",
    }
    backoff = 5
    for attempt in range(max_retries):
        try:
            resp = requests.get(OPEN_METEO_ARCHIVE, params=params, timeout=timeout)
        except Exception as exc:
            log.warning("  %-30s network error (%s) -- retry in %ds",
                        division, type(exc).__name__, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 90)
            continue
        if resp.status_code == 429:
            # Per-minute limit hit; respect Retry-After header if present
            wait = int(resp.headers.get("Retry-After", "65"))
            log.info("  %-30s 429 rate-limited -- sleep %ds", division, wait)
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            log.warning("  %-30s FAIL HTTP %d: %s",
                        division, resp.status_code, resp.text[:120])
            return None
        break
    else:
        log.warning("  %-30s FAIL after %d retries", division, max_retries)
        return None
    j = resp.json()
    daily = j.get("daily", {})
    if not daily or "time" not in daily:
        log.warning("  %-30s FAIL no daily data", division)
        return None
    df = pd.DataFrame(daily)
    df["division"] = division
    df["date"] = pd.to_datetime(df["time"])
    df = df.drop(columns=["time"])
    return df


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Add rolling stats + anomalies + VPD per (division, date)."""
    df = df.sort_values(["division", "date"]).reset_index(drop=True)

    # Rename long Open-Meteo names → short names
    df = df.rename(columns={
        "temperature_2m_max":             "air_temp_max",
        "temperature_2m_min":             "air_temp_min",
        "temperature_2m_mean":            "air_temp_c",
        "relative_humidity_2m_mean":      "rh_pct",
        "dewpoint_2m_mean":               "dewpoint_c",
        "wind_speed_10m_max":             "wind_kmh_max",
        "precipitation_sum":              "precip_mm",
        "shortwave_radiation_sum":        "srad_mj",
        "et0_fao_evapotranspiration":     "et0_mm",
        "soil_moisture_0_to_7cm_mean":    "soil_moisture_0_7cm",
        "soil_moisture_7_to_28cm_mean":   "soil_moisture_7_28cm",
        "vapour_pressure_deficit_max":    "vpd_kpa",
    })
    df["dtr"] = df["air_temp_max"] - df["air_temp_min"]

    # Rolling stats per division
    g = df.groupby("division", group_keys=False)
    df["precip_7d"]  = g["precip_mm"].apply(lambda s: s.rolling(7, min_periods=1).sum())
    df["precip_14d"] = g["precip_mm"].apply(lambda s: s.rolling(14, min_periods=1).sum())
    df["precip_30d"] = g["precip_mm"].apply(lambda s: s.rolling(30, min_periods=1).sum())

    # Consecutive dry days: cumulative count that resets on precip > 0.5 mm
    def _consec_dry(s: pd.Series) -> pd.Series:
        dry = (s <= 0.5).astype(int)
        # Cumulative count that resets on wet day
        groups = (~dry.astype(bool)).cumsum()
        return dry.groupby(groups).cumsum()

    df["consecutive_dry"] = g["precip_mm"].apply(_consec_dry)

    df["temp_7d_mean"] = g["air_temp_c"].apply(lambda s: s.rolling(7, min_periods=1).mean())
    df["rh_7d_min"]    = g["rh_pct"].apply(lambda s: s.rolling(7, min_periods=1).min())
    df["wind_7d_max"]  = g["wind_kmh_max"].apply(lambda s: s.rolling(7, min_periods=1).max())
    df["vpd_7d_max"]   = g["vpd_kpa"].apply(lambda s: s.rolling(7, min_periods=1).max())

    # Anomalies vs (division, day-of-year) using 2024-2025 as climatology baseline.
    # Using 2 years is thinner than ideal but lets the ingest finish in minutes
    # rather than hours when Open-Meteo rate-limits the long history.
    clim_period = df[df["date"].dt.year.between(2024, 2025)].copy()
    clim_period["doy"] = clim_period["date"].dt.dayofyear
    clim = clim_period.groupby(["division", "doy"]).agg(
        temp_clim=("air_temp_c", "mean"),
        rh_clim=("rh_pct", "mean"),
        wind_clim=("wind_kmh_max", "mean"),
        precip_clim=("precip_mm", "mean"),
    ).reset_index()
    df["doy"] = df["date"].dt.dayofyear
    df = df.merge(clim, on=["division", "doy"], how="left")
    df["temp_anom"]   = df["air_temp_c"] - df["temp_clim"]
    df["rh_anom"]     = df["rh_pct"] - df["rh_clim"]
    df["wind_anom"]   = df["wind_kmh_max"] - df["wind_clim"]
    df["precip_anom"] = df["precip_mm"] - df["precip_clim"]

    df = df.drop(columns=["doy", "temp_clim", "rh_clim", "wind_clim", "precip_clim"])
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01",
                    help="Default 2024-01-01 = 2.5 yrs (enough for 30d-rolling + 2024-25 anomalies)")
    ap.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit to first N divisions (for smoke testing)")
    ap.add_argument("--throttle", type=float, default=2.0,
                    help="Seconds between API calls. Open-Meteo Archive's "
                         "free tier rate-limits ~30 calls/min for this endpoint; "
                         "2.0s = 30/min, safely under.")
    args = ap.parse_args()

    log.info("Loading division centroids from cells.csv...")
    cells = pd.read_csv(CELLS_CSV)
    centroids = cells.groupby("division").agg(
        lat=("centroid_lat", "mean"),
        lon=("centroid_lon", "mean"),
        n_cells=("cell_id", "size"),
    ).reset_index()
    if args.limit:
        centroids = centroids.head(args.limit)
    log.info("  %d divisions", len(centroids))
    log.info("Window: %s -> %s", args.start, args.end)

    frames = []
    n_ok = 0
    n_fail = 0
    t0 = time.time()
    for i, row in enumerate(centroids.itertuples(index=False), 1):
        div = row.division
        df_div = fetch_division(div, row.lat, row.lon, args.start, args.end)
        if df_div is None or df_div.empty:
            n_fail += 1
            continue
        frames.append(df_div)
        n_ok += 1
        if i % 10 == 0 or i == len(centroids):
            elapsed = time.time() - t0
            log.info("  [%3d/%3d] %s ok in %.1fs (%d rows total so far)",
                     i, len(centroids), div, elapsed, sum(len(f) for f in frames))
        time.sleep(args.throttle)

    log.info("Fetched %d divisions OK, %d failed.", n_ok, n_fail)
    if not frames:
        log.error("Nothing fetched.")
        return 1

    df = pd.concat(frames, ignore_index=True)
    log.info("Combined: %d rows × %d cols", len(df), len(df.columns))

    log.info("Computing derived features (rolling, anomalies, VPD)...")
    df = add_derived(df)
    log.info("After derivations: %d rows × %d cols", len(df), len(df.columns))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    log.info("Wrote %s", OUT_PATH.relative_to(ROOT))

    # Quick sanity check: latest date per division
    latest = df.groupby("division")["date"].max().describe()
    log.info("Latest-date distribution across divisions:")
    log.info("  min   = %s", latest["min"])
    log.info("  max   = %s", latest["max"])
    log.info("  mean  = %s", latest["mean"])

    # Sample stats
    today_window = df[df["date"] >= pd.Timestamp.now() - pd.Timedelta(days=7)]
    if len(today_window):
        log.info("Last-week sample:")
        log.info("  air_temp_c    range [%.1f, %.1f]",
                 today_window["air_temp_c"].min(), today_window["air_temp_c"].max())
        log.info("  rh_pct        range [%.0f, %.0f]",
                 today_window["rh_pct"].min(), today_window["rh_pct"].max())
        log.info("  wind_kmh_max  range [%.1f, %.1f]",
                 today_window["wind_kmh_max"].min(), today_window["wind_kmh_max"].max())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
