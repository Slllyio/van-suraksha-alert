"""Stage V11.1 — Download GDELT Events 2.0 raw ZIPs, filter to MP fire events.

GDELT publishes daily `YYYYMMDD.export.CSV.zip` files at
`http://data.gdeltproject.org/events/` (the JSON API at api.gdeltproject.org
is blocked from this machine, but the raw ZIP host works).

Pipeline:
  1. For each dry-season day (Feb-May) 2015-2026, download the zip to tmp/
  2. Extract to CSV in memory, filter to:
       - ActionGeo_CountryCode == "IN" (col 52, 1-indexed)
       - ActionGeo_ADM1Code == "IN35" (col 53) — ISO code for Madhya Pradesh
       - URL or event text contains fire keyword ("fire", "burn", "forest",
         "wildfire", Hindi approximations)
  3. Concatenate all days → single parquet

Output: data_lake/weak_labels/gdelt_mp_fire_events.parquet
  Columns: event_id, sqldate (YYYYMMDD), event_code, goldstein, num_mentions,
           action_geo_adm1 (IN35), action_geo_lat, action_geo_lon,
           date_added, source_url

Schema ref (58 columns): https://www.gdeltproject.org/data/lookups/CSV.header.historical.txt
Per-day file size: 3-8 MB zipped. Full Feb-May 2015-2026 = 121 days × 12 years
= ~1,452 days × ~5 MB = ~7 GB download total, ~50 MB parquet after filter.

Usage:
  python scripts/ingest_gdelt_events_mp.py --year 2024          # single year
  python scripts/ingest_gdelt_events_mp.py                       # all years
  python scripts/ingest_gdelt_events_mp.py --dry-run             # list files
"""
from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from datetime import date, timedelta
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data_lake" / "weak_labels" / "gdelt_mp_fire_events.parquet"
TMP_DIR = ROOT / "tmp" / "gdelt_cache"

GDELT_BASE = "http://data.gdeltproject.org/events"
MP_ADM1 = "IN35"  # Madhya Pradesh ISO 3166-2 code

# Keep only these GDELT 2.0 columns (1-indexed position : name)
COL_POSITIONS = {
    1: "event_id",
    2: "sqldate",
    27: "event_code",
    28: "event_base_code",
    29: "event_root_code",
    31: "goldstein",
    32: "num_mentions",
    34: "num_articles",
    35: "avg_tone",
    52: "action_country",
    53: "action_adm1",
    54: "action_lat",
    55: "action_lon",
    57: "date_added",
    58: "source_url",
}

FIRE_KEYWORDS = ["fire", "burn", "forest", "wildfire", "blaze",
                 # Hindi transliterations in URL or title
                 "aag", "jungle", "van", "आग", "जंगल"]


def fire_season_dates(year: int) -> list[date]:
    """Return all dates in Feb 1 - May 31 of given year (dry fire season)."""
    start = date(year, 2, 1)
    end = date(year, 5, 31)
    out = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def download_day(day: date) -> Path | None:
    """Download one day's CSV zip, cached. Return path or None if 404."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{GDELT_BASE}/{day.strftime('%Y%m%d')}.export.CSV.zip"
    cache = TMP_DIR / f"{day.strftime('%Y%m%d')}.export.CSV.zip"
    if cache.exists() and cache.stat().st_size > 10000:
        return cache
    r = requests.get(url, stream=True, timeout=60)
    if r.status_code != 200:
        log.debug("  404 %s", url)
        return None
    cache.write_bytes(r.content)
    return cache


def filter_day(zip_path: Path) -> pd.DataFrame:
    """Read one day's zipped CSV, filter to MP fire events, return DataFrame."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n.endswith(".CSV") or n.endswith(".csv") or n.endswith(".export.csv")]
        if not names:
            # The file is named e.g. 20240401.export.CSV
            names = zf.namelist()
        with zf.open(names[0]) as f:
            data = f.read().decode("utf-8", errors="replace")

    rows = []
    max_col = max(COL_POSITIONS.keys())
    for line in data.splitlines():
        parts = line.split("\t")
        if len(parts) < max_col:
            continue
        # Fast path: country code + MP ADM1
        if parts[51] != "IN" or parts[52] != MP_ADM1:  # 0-indexed 51 and 52
            continue
        # Keyword filter on source URL (quick) — col 57 (0-idx) = col 58 (1-idx)
        url_lower = parts[57].lower()
        if not any(kw in url_lower for kw in FIRE_KEYWORDS):
            continue
        row = {name: parts[pos - 1] for pos, name in COL_POSITIONS.items()}
        rows.append(row)

    return pd.DataFrame(rows)


def process_year(year: int, dry_run: bool = False) -> pd.DataFrame:
    days = fire_season_dates(year)
    log.info("Year %d: %d dry-season days", year, len(days))
    year_rows = []
    n_downloaded = 0
    n_filtered = 0
    for i, day in enumerate(days):
        if dry_run:
            log.info("  would download %s", day)
            continue
        zp = download_day(day)
        if zp is None:
            continue
        n_downloaded += 1
        df = filter_day(zp)
        n_filtered += len(df)
        if len(df):
            year_rows.append(df)
        if (i + 1) % 10 == 0:
            log.info("  %d/%d days, %d dl'd, %d MP fire events so far",
                     i + 1, len(days), n_downloaded, n_filtered)
    if dry_run or not year_rows:
        return pd.DataFrame()
    out = pd.concat(year_rows, ignore_index=True)
    log.info("  Year %d: %d downloaded, %d MP fire events", year, n_downloaded, len(out))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=None,
                        help="Process single year (default: 2015-2026)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    years = [args.year] if args.year else list(range(2015, 2027))

    log.info("Processing %d years of GDELT raw ZIPs (fire season Feb-May only)", len(years))
    all_rows = []
    for y in years:
        df = process_year(y, args.dry_run)
        if len(df):
            all_rows.append(df)

    if args.dry_run:
        log.info("Dry run done. Would process %d years × ~121 days each", len(years))
        return 0

    if not all_rows:
        log.error("No MP fire events extracted!")
        return 1

    combined = pd.concat(all_rows, ignore_index=True)
    # Type conversions
    combined["sqldate"] = pd.to_datetime(combined["sqldate"], format="%Y%m%d", errors="coerce")
    combined["action_lat"] = pd.to_numeric(combined["action_lat"], errors="coerce")
    combined["action_lon"] = pd.to_numeric(combined["action_lon"], errors="coerce")
    combined["goldstein"] = pd.to_numeric(combined["goldstein"], errors="coerce")
    combined["num_mentions"] = pd.to_numeric(combined["num_mentions"], errors="coerce").fillna(0).astype(int)
    combined["num_articles"] = pd.to_numeric(combined["num_articles"], errors="coerce").fillna(0).astype(int)
    combined["avg_tone"] = pd.to_numeric(combined["avg_tone"], errors="coerce")

    # Drop rows with invalid lat/lon (defensive — shouldn't happen after ADM1 filter)
    combined = combined.dropna(subset=["action_lat", "action_lon", "sqldate"])
    combined = combined[(combined["action_lat"].between(21.0, 27.5))
                         & (combined["action_lon"].between(73.5, 83.5))]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out_path, index=False)

    log.info("\n=== GDELT MP FIRE EVENTS ===")
    log.info("Total events: %d", len(combined))
    log.info("Years: %s", dict(combined["sqldate"].dt.year.value_counts().sort_index()))
    log.info("Top event codes: %s", dict(combined["event_code"].value_counts().head(10)))
    log.info("Lat range: [%.2f, %.2f], Lon range: [%.2f, %.2f]",
             combined["action_lat"].min(), combined["action_lat"].max(),
             combined["action_lon"].min(), combined["action_lon"].max())
    log.info("\nSaved: %s (%.1f MB)", out_path.relative_to(ROOT), out_path.stat().st_size / 1e6)

    # Sanity check for stopping rule
    if len(combined) < 1000:
        log.warning("\n⚠️  STOPPING RULE: MP GDELT fire events = %d < 1000. "
                    "Coverage too sparse. Consider parking v11.", len(combined))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
