"""
scripts/download_weather_mp.py
================================
Download NASA POWER daily weather for a grid covering all Madhya Pradesh forests.

Grid: 0.5° spacing across MP (lat 21-27, lon 74-83)
  - 13 lat × 19 lon = 247 grid points
  - Each cell at 2km resolution is max ~35km from a grid point

Saves incrementally. Resume-safe (skips already-downloaded points).

Output: data_lake/fire_weather/nasa_power_mp_gridded.parquet

Usage:
    python scripts/download_weather_mp.py
    python scripts/download_weather_mp.py --start-year 2020  # start from later year
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
log = logging.getLogger("mp_weather")

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data_lake" / "fire_weather" / "nasa_power_mp_gridded.parquet"

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# MP forest bounds: lat ~21.0-26.9, lon ~74.0-82.9
# Grid at 0.5° spacing
MP_GRID_LATS = np.arange(21.0, 27.5, 0.5).tolist()  # 21.0, 21.5, ..., 27.0
MP_GRID_LONS = np.arange(74.0, 83.5, 0.5).tolist()  # 74.0, 74.5, ..., 83.0


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
    parser = argparse.ArgumentParser(description="Download MP-wide gridded NASA POWER weather")
    parser.add_argument("--start-year", type=int, default=2013)
    parser.add_argument("--end-year", type=int, default=2025)
    args = parser.parse_args()

    grid_points = [(lat, lon) for lat in MP_GRID_LATS for lon in MP_GRID_LONS]
    log.info(f"Grid: {len(grid_points)} points ({len(MP_GRID_LATS)} lat × {len(MP_GRID_LONS)} lon)")
    log.info(f"Period: {args.start_year}-{args.end_year}")

    # Load existing data for resume
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
    for i, (lat, lon) in enumerate(grid_points):
        grid_id = f"g_{lat:.2f}_{lon:.2f}"

        if grid_id in existing_ids:
            done += 1
            continue

        log.info(f"[{i+1}/{len(grid_points)}] Fetching {grid_id} ({lat}N, {lon}E)...")

        try:
            df = fetch_power_point(lat, lon, args.start_year, args.end_year)
            df["grid_id"] = grid_id
            df["grid_lat"] = lat
            df["grid_lon"] = lon
            all_frames.append(df)
            done += 1
            log.info(f"  {len(df)} days (T: {df['temp_c'].min():.0f}-{df['temp_c'].max():.0f}°C)")

            # Save every 10 points
            if done % 10 == 0:
                combined = pd.concat(all_frames, ignore_index=True)
                OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                combined.to_parquet(OUT_PATH, index=False)
                log.info(f"  Checkpoint saved: {combined['grid_id'].nunique()} points")

        except Exception as e:
            log.error(f"  FAILED: {e}")
            failed += 1

        # Rate limit: NASA POWER allows ~30 req/min
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
