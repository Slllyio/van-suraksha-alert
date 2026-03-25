"""
scripts/download_gridded_weather.py
====================================
Download NASA POWER daily weather for a grid of points across Guna Division.

Instead of a single weather station for all 9,901 cells, this creates a
~15-point weather grid at 0.25 degree spacing. Each cell then uses weather
from its nearest grid point, capturing spatial variation in temperature,
humidity, wind, and precipitation across the 2,475 km2 division.

Grid: 5 lat x 3 lon = 15 points at 0.25 degree spacing
  Lat: 24.0, 24.25, 24.5, 24.75, 25.0
  Lon: 76.9, 77.15, 77.4

Output: data_lake/fire_weather/nasa_power_gridded.parquet
        Columns: grid_id, lat, lon, date, temp_c, rh_pct, wind_kmh, precip_mm

Usage:
    python scripts/download_gridded_weather.py
    python scripts/download_gridded_weather.py --start 2020  # resume from year
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
log = logging.getLogger("gridded_weather")

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_gridded.parquet"

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Guna AOI bounds: lat 23.89-25.11, lon 76.80-77.49
# Grid at 0.25 degree spacing with small buffer
GRID_LATS = [24.0, 24.25, 24.5, 24.75, 25.0]
GRID_LONS = [76.9, 77.15, 77.4]


def fetch_power_point(lat, lon, start_year, end_year):
    """Fetch NASA POWER daily weather for one grid point."""
    params = {
        "parameters": "T2M,T2M_MAX,T2M_MIN,RH2M,WS2M,PRECTOTCORR",
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
    t2m = props["T2M"]
    t2m_max = props.get("T2M_MAX", {})
    t2m_min = props.get("T2M_MIN", {})
    rh2m = props["RH2M"]
    ws2m = props["WS2M"]
    precip = props["PRECTOTCORR"]

    rows = []
    for date_str, temp in t2m.items():
        if len(date_str) != 8:
            continue
        d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]))
        rows.append({
            "date": d,
            "temp_c": float(t2m.get(date_str, -999)),
            "temp_max_c": float(t2m_max.get(date_str, -999)),
            "temp_min_c": float(t2m_min.get(date_str, -999)),
            "rh_pct": float(rh2m.get(date_str, -999)),
            "wind_kmh": float(ws2m.get(date_str, -999)) * 3.6,
            "precip_mm": float(precip.get(date_str, -999)),
        })

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.replace(-999.0, np.nan).replace(-999, np.nan)
    for col in ["temp_c", "temp_max_c", "temp_min_c", "rh_pct", "wind_kmh"]:
        df[col] = df[col].ffill().bfill()
    df["precip_mm"] = df["precip_mm"].fillna(0.0)

    return df


def main():
    parser = argparse.ArgumentParser(description="Download gridded NASA POWER weather")
    parser.add_argument("--start", type=int, default=2013, help="Start year")
    parser.add_argument("--end", type=int, default=2026, help="End year")
    args = parser.parse_args()

    grid_points = [(lat, lon) for lat in GRID_LATS for lon in GRID_LONS]
    log.info(f"Grid: {len(grid_points)} points ({len(GRID_LATS)} lat x {len(GRID_LONS)} lon)")
    log.info(f"Period: {args.start}-{args.end}")

    # Check for existing data to resume/extend
    existing = None
    if OUT_PATH.exists():
        existing = pd.read_parquet(OUT_PATH)
        existing["date"] = pd.to_datetime(existing["date"])
        existing_ids = set(existing["grid_id"].unique())
        existing_max_date = existing["date"].max()
        log.info(f"Existing data: {len(existing_ids)} grid points, up to {existing_max_date.date()}")
    else:
        existing_ids = set()
        existing_max_date = None

    # Determine if we need to extend existing data with new years
    need_extend = (existing_max_date is not None
                   and existing_max_date.year < args.end
                   and len(existing_ids) == len(grid_points))

    all_frames = []
    if existing is not None:
        all_frames.append(existing)

    for i, (lat, lon) in enumerate(grid_points):
        grid_id = f"g_{lat:.2f}_{lon:.2f}"

        if grid_id in existing_ids and not need_extend:
            log.info(f"[{i+1}/{len(grid_points)}] {grid_id} — already downloaded, skip")
            continue

        # If extending, only fetch the new year range
        fetch_start = args.start
        if need_extend and grid_id in existing_ids:
            fetch_start = existing_max_date.year + 1
            if fetch_start > args.end:
                log.info(f"[{i+1}/{len(grid_points)}] {grid_id} — already up to date")
                continue
            log.info(f"[{i+1}/{len(grid_points)}] Extending {grid_id} ({fetch_start}-{args.end})...")

        if not need_extend:
            log.info(f"[{i+1}/{len(grid_points)}] Fetching {grid_id} ({lat}N, {lon}E)...")

        try:
            df = fetch_power_point(lat, lon, fetch_start, args.end)
            df["grid_id"] = grid_id
            df["grid_lat"] = lat
            df["grid_lon"] = lon
            all_frames.append(df)
            log.info(f"  {len(df)} days fetched (T: {df['temp_c'].min():.0f}-{df['temp_c'].max():.0f}C)")

            # Save incrementally
            combined = pd.concat(all_frames, ignore_index=True)
            OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            combined.to_parquet(OUT_PATH, index=False)

        except Exception as e:
            log.error(f"  FAILED: {e}")

        # Rate limit: NASA POWER allows ~30 req/min
        time.sleep(3)

    # Final save
    combined = pd.concat(all_frames, ignore_index=True)
    combined.to_parquet(OUT_PATH, index=False)

    n_points = combined["grid_id"].nunique()
    n_days = combined.groupby("grid_id").size().mean()
    log.info(f"\nDone! {n_points} grid points x {n_days:.0f} days = {len(combined):,} rows")
    log.info(f"Saved: {OUT_PATH}")

    # Show grid summary
    for gid, grp in combined.groupby("grid_id"):
        log.info(f"  {gid}: {len(grp)} days, "
                 f"T={grp['temp_c'].mean():.1f}C, "
                 f"RH={grp['rh_pct'].mean():.0f}%, "
                 f"P={grp['precip_mm'].sum():.0f}mm total")


if __name__ == "__main__":
    main()
