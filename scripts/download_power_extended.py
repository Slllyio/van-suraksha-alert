"""
scripts/download_power_extended.py
===================================
Download additional NASA POWER variables for all MP grid points:
  - GWETTOP: Surface Soil Wetness (0-5cm), 0-1 scale
  - GWETROOT: Root Zone Soil Wetness (0-1m), 0-1 scale
  - TS: Earth Skin Temperature (°C) — satellite-derived LST proxy
  - ALLSKY_SFC_SW_DWN: Solar Radiation (kW-hr/m²/day)

These are appended as new columns to the existing MP gridded weather parquet.
Resume-safe: skips already-downloaded grid points.

Usage:
    python scripts/download_power_extended.py
"""

import argparse
import logging
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("power_extended")

ROOT = Path(__file__).resolve().parent.parent
BASE_WX_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_mp_gridded.parquet"
OUT_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_mp_extended.parquet"

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

EXTRA_PARAMS = "GWETTOP,GWETROOT,TS,ALLSKY_SFC_SW_DWN"


def fetch_power_extended(lat, lon, start_year, end_year):
    """Fetch additional NASA POWER variables for one grid point."""
    params = {
        "parameters": EXTRA_PARAMS,
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": f"{start_year}0101",
        "end": f"{end_year}1231",
        "format": "JSON",
        "time-standard": "LST",
    }

    r = requests.get(NASA_POWER_URL, params=params, timeout=120)
    r.raise_for_status()
    data = r.json()

    props = data["properties"]["parameter"]
    gwettop = props.get("GWETTOP", {})
    gwetroot = props.get("GWETROOT", {})
    ts = props.get("TS", {})
    srad = props.get("ALLSKY_SFC_SW_DWN", {})

    rows = []
    for date_str in gwettop:
        if len(date_str) != 8:
            continue
        d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]))
        rows.append({
            "date": d,
            "soil_moisture_surface": float(gwettop.get(date_str, -999)),
            "soil_moisture_rootzone": float(gwetroot.get(date_str, -999)),
            "surface_temp_c": float(ts.get(date_str, -999)),
            "solar_radiation": float(srad.get(date_str, -999)),
        })

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.replace(-999.0, np.nan).replace(-999, np.nan)

    # Forward/back fill missing values
    for col in ["soil_moisture_surface", "soil_moisture_rootzone", "surface_temp_c"]:
        df[col] = df[col].ffill().bfill()
    df["solar_radiation"] = df["solar_radiation"].fillna(0.0)

    return df


def main():
    parser = argparse.ArgumentParser(description="Download extended NASA POWER variables for MP grid")
    parser.add_argument("--start-year", type=int, default=2013)
    parser.add_argument("--end-year", type=int, default=2025)
    args = parser.parse_args()

    # Load existing base weather to get grid points
    if not BASE_WX_PATH.exists():
        log.error(f"Base weather file not found: {BASE_WX_PATH}")
        log.error("Run download_weather_mp.py first!")
        return

    base = pd.read_parquet(BASE_WX_PATH)
    grid_points = base.groupby("grid_id").first()[["grid_lat", "grid_lon"]].reset_index()
    log.info(f"Grid points: {len(grid_points)}")
    log.info(f"Period: {args.start_year}-{args.end_year}")
    log.info(f"Extra parameters: {EXTRA_PARAMS}")

    # Load existing extended data for resume
    existing_ids = set()
    all_frames = []
    if OUT_PATH.exists():
        existing = pd.read_parquet(OUT_PATH)
        existing["date"] = pd.to_datetime(existing["date"])
        existing_ids = set(existing["grid_id"].unique())
        all_frames.append(existing)
        log.info(f"Resuming: {len(existing_ids)} grid points already downloaded")

    done = 0
    failed = 0
    for i, row in grid_points.iterrows():
        gid = row["grid_id"]
        lat = row["grid_lat"]
        lon = row["grid_lon"]

        if gid in existing_ids:
            done += 1
            continue

        log.info(f"[{done+1}/{len(grid_points)}] Fetching {gid} ({lat}N, {lon}E)...")

        try:
            df = fetch_power_extended(lat, lon, args.start_year, args.end_year)
            df["grid_id"] = gid
            df["grid_lat"] = lat
            df["grid_lon"] = lon
            all_frames.append(df)
            done += 1

            sm_range = f"SM: {df['soil_moisture_surface'].min():.2f}-{df['soil_moisture_surface'].max():.2f}"
            ts_range = f"TS: {df['surface_temp_c'].min():.0f}-{df['surface_temp_c'].max():.0f}°C"
            log.info(f"  {len(df)} days ({sm_range}, {ts_range})")

            # Checkpoint every 10 points
            if done % 10 == 0:
                combined = pd.concat(all_frames, ignore_index=True)
                OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                combined.to_parquet(OUT_PATH, index=False)
                log.info(f"  Checkpoint: {combined['grid_id'].nunique()} points saved")

        except Exception as e:
            log.error(f"  FAILED: {e}")
            failed += 1

        # Rate limit
        time.sleep(2.5)

    # Final save
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        combined.to_parquet(OUT_PATH, index=False)
        n_pts = combined["grid_id"].nunique()
        log.info(f"\nDone! {n_pts} grid points, {len(combined):,} total rows")
        log.info(f"Failed: {failed}")
        log.info(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    main()
