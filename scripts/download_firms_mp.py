"""
scripts/download_firms_mp.py
=============================
Download FIRMS fire detections for ALL of Madhya Pradesh (2014-2025).

This gives us ~100x more training data than Guna alone, enabling the
25ha grid predictive model to learn generalizable fire patterns.

Sources:
  - VIIRS_SNPP_SP:  375m resolution, Jan 2012 – present
  - Free NRT data:  No key needed (last 7 days only)

For historical data you need a free FIRMS MAP_KEY:
  1. Go to https://firms.modaps.eosdis.nasa.gov/api/area/
  2. Click "Get MAP_KEY" → key is emailed instantly
  3. Set: export FIRMS_MAP_KEY=<your_key>
  4. Run: python scripts/download_firms_mp.py

Usage:
    python scripts/download_firms_mp.py                     # Download historical (needs key)
    python scripts/download_firms_mp.py --nrt-only          # Download NRT 7-day (no key needed)
    python scripts/download_firms_mp.py --start 2020-01-01  # Resume from date
"""

import io
import os
import sys
import time
import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import urllib.request
import urllib.error
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs"

# Madhya Pradesh bounding box (with small buffer)
MP_BBOX = "73.95,21.00,82.90,26.90"
MP_BOUNDS = (73.95, 21.00, 82.90, 26.90)

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
NRT_BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv"
CHUNK_DAYS = 5
SLEEP_BETWEEN = 0.15

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("firms_mp")


def download_nrt():
    """Download NRT 7-day file (no API key needed) and filter to MP."""
    url = f"{NRT_BASE}/SUOMI_VIIRS_C2_South_Asia_7d.csv"
    log.info(f"Downloading NRT 7-day South Asia file...")

    req = urllib.request.Request(url, headers={"User-Agent": "JwalaNetra/2.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read().decode("utf-8", errors="replace")

    df = pd.read_csv(io.StringIO(data))
    log.info(f"  Total South Asia detections: {len(df)}")

    # Filter to MP
    w, s, e, n = MP_BOUNDS
    mp = df[(df["latitude"] >= s) & (df["latitude"] <= n) &
            (df["longitude"] >= w) & (df["longitude"] <= e)].reset_index(drop=True)
    log.info(f"  MP detections: {len(mp)}")

    # Standardize columns to match our format
    mp = mp.rename(columns={"acq_date": "acq_date"})

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "nrt_7d.parquet"
    mp.to_parquet(out_path, index=False)
    log.info(f"  Saved to {out_path}")
    return mp


def download_historical(api_key, start_date, end_date, fire_season_only=True):
    """Download historical FIRMS data via API in 5-day chunks.

    If fire_season_only=True, only download Jan-Jun (fire season + shoulder).
    This cuts API calls by ~50% since Jul-Dec has <5% of fires.
    """
    log.info(f"Downloading FIRMS VIIRS_SNPP_SP for MP: {start_date} to {end_date}")
    log.info(f"  Bbox: {MP_BBOX}")
    log.info(f"  Fire season only: {fire_season_only}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    d = start_date
    total_detections = 0
    total_chunks = 0
    total_skipped = 0
    failed_chunks = 0

    while d <= end_date:
        # Skip non-fire months to speed up download
        if fire_season_only and d.month in {7, 8, 9}:
            d = date(d.year, 10, 1) if d.month < 10 else date(d.year + 1, 1, 1)
            total_skipped += 1
            continue

        chunk_end = min(d + timedelta(days=CHUNK_DAYS - 1), end_date)
        out_path = OUT_DIR / str(d.year) / f"viirs_mp_{d.strftime('%Y_%m_%d')}_{CHUNK_DAYS}d.parquet"

        if out_path.exists():
            d += timedelta(days=CHUNK_DAYS)
            continue

        url = f"{FIRMS_BASE}/{api_key}/VIIRS_SNPP_SP/{MP_BBOX}/{CHUNK_DAYS}/{d.isoformat()}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JwalaNetra/2.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", errors="replace")

            lines = [l for l in raw.strip().split("\n") if l.strip()]
            if len(lines) <= 1:
                d += timedelta(days=CHUNK_DAYS)
                continue

            df = pd.read_csv(io.StringIO(raw))
            w, s, e, n = MP_BOUNDS
            df = df[(df["latitude"] >= s) & (df["latitude"] <= n) &
                    (df["longitude"] >= w) & (df["longitude"] <= e)].reset_index(drop=True)

            if len(df) > 0:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(out_path, index=False)
                total_detections += len(df)

            total_chunks += 1
            if total_chunks % 50 == 0:
                log.info(f"  {d} | chunks={total_chunks} | detections={total_detections:,}")

        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning(f"  Rate limited at {d}, sleeping 60s...")
                time.sleep(60)
                continue
            log.warning(f"  HTTP {e.code} at {d}")
            failed_chunks += 1
        except Exception as e:
            log.warning(f"  Error at {d}: {e}")
            failed_chunks += 1

        time.sleep(SLEEP_BETWEEN)
        d += timedelta(days=CHUNK_DAYS)

    log.info(f"\nDownload complete!")
    log.info(f"  Total chunks: {total_chunks}")
    log.info(f"  Failed: {failed_chunks}")
    log.info(f"  Total detections: {total_detections:,}")
    log.info(f"  Output: {OUT_DIR}")


def consolidate():
    """Consolidate all downloaded parquet files into yearly summaries."""
    if not OUT_DIR.exists():
        log.warning("No data to consolidate")
        return

    all_frames = []
    for f in sorted(OUT_DIR.glob("**/*.parquet")):
        df = pd.read_parquet(f)
        if len(df) > 0:
            all_frames.append(df)

    if not all_frames:
        log.warning("No data found")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    combined["acq_date"] = pd.to_datetime(combined["acq_date"])
    combined = combined.drop_duplicates(subset=["latitude", "longitude", "acq_date", "acq_time"])
    # Fix mixed types from NRT vs historical (e.g. version column)
    for col in combined.columns:
        if combined[col].dtype == object:
            combined[col] = combined[col].astype(str)

    log.info(f"\nConsolidated MP FIRMS data:")
    log.info(f"  Total detections: {len(combined):,}")
    log.info(f"  Date range: {combined['acq_date'].min().date()} to {combined['acq_date'].max().date()}")
    log.info(f"  Lat range: {combined['latitude'].min():.2f} to {combined['latitude'].max():.2f}")
    log.info(f"  Lon range: {combined['longitude'].min():.2f} to {combined['longitude'].max():.2f}")

    # Save consolidated
    out_path = OUT_DIR / "firms_mp_consolidated.parquet"
    combined.to_parquet(out_path, index=False)
    log.info(f"  Saved to: {out_path}")

    # Per-year stats
    combined["year"] = combined["acq_date"].dt.year
    for yr, grp in combined.groupby("year"):
        log.info(f"  {yr}: {len(grp):,} detections")


def main():
    parser = argparse.ArgumentParser(description="Download FIRMS data for all of Madhya Pradesh")
    parser.add_argument("--nrt-only", action="store_true",
                        help="Download only NRT 7-day data (no API key needed)")
    parser.add_argument("--start", type=str, default="2014-01-01",
                        help="Start date (default: 2014-01-01)")
    parser.add_argument("--end", type=str, default="2025-12-31",
                        help="End date (default: 2025-12-31)")
    parser.add_argument("--consolidate", action="store_true",
                        help="Just consolidate existing downloads")
    args = parser.parse_args()

    if args.consolidate:
        consolidate()
        return

    if args.nrt_only:
        mp = download_nrt()
        consolidate()
        return

    api_key = os.environ.get("FIRMS_MAP_KEY", "")
    if not api_key:
        print("\n" + "=" * 60)
        print("FIRMS_MAP_KEY not set!")
        print("=" * 60)
        print("\nTo download historical data:")
        print("  1. Go to: https://firms.modaps.eosdis.nasa.gov/api/area/")
        print("  2. Click 'Get MAP_KEY' (free, instant)")
        print("  3. Set:   export FIRMS_MAP_KEY=<your_key>")
        print("  4. Run:   python scripts/download_firms_mp.py")
        print("\nMeanwhile, downloading NRT 7-day data (no key needed)...")
        download_nrt()
        consolidate()
        return

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    download_historical(api_key, start, end)
    consolidate()


if __name__ == "__main__":
    main()
