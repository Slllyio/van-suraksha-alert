"""Stage 1a — Ingest MODIS MCD64A1 burnt-area product for MP, 2014-2026.

MCD64A1 Collection 6.1 (Giglio 2018): 500m monthly product with per-pixel
daily burn-date (0-31 within the month). Key band:
  - BurnDate: uint16, 1=Jan 1 of year, ..., 366=Dec 31, 0=no burn

We export YEARLY composites (not monthly) — GEE's composite trick is to take
the max per-pixel burn DOY across all monthly images in the year. Since each
pixel can only burn once per month and typically once per year (MP dry season
is Feb-May), the max captures the burn date cleanly.

Output: data_lake/burnt_area/mcd64_mp_{year}.tif (500m, uint16 DOY)

Usage:
  python scripts/ingest_mcd64_mp.py --queue                    # queue exports for 2014-2026
  python scripts/ingest_mcd64_mp.py --queue --year 2024        # single year
  python scripts/ingest_mcd64_mp.py --status                    # check task progress
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import ee

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ee.Initialize(project="van-suraksha-alert")

ROOT = Path(__file__).resolve().parents[1]
DRIVE_FOLDER = "burnt_area_mcd64"

MP_GEOM = (
    ee.FeatureCollection("FAO/GAUL/2015/level1")
    .filter(ee.Filter.eq("ADM1_NAME", "Madhya Pradesh"))
    .geometry()
)

YEARS = list(range(2014, 2027))  # 2014-2026 inclusive


def build_mcd64_yearly(year: int) -> ee.Image:
    """Composite yearly MCD64A1 BurnDate band for a given year.

    Take max BurnDate across all monthly images (each pixel only burns once
    per month in MP, and typically once per year in dry season Feb-May).
    """
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    col = (
        ee.ImageCollection("MODIS/061/MCD64A1")
        .filterDate(start, end)
        .select("BurnDate")
    )
    # Max captures the burn DOY (non-burn pixels are 0)
    burn_doy = col.max().toUint16().rename("burn_doy")
    # Also add an "uncertainty" band (from MCD64A1) — useful for filtering later
    unc = (
        ee.ImageCollection("MODIS/061/MCD64A1")
        .filterDate(start, end)
        .select("Uncertainty")
        .max()
        .toUint16()
        .rename("burn_uncertainty")
    )
    return burn_doy.addBands(unc).set("year", year)


def queue_exports(years: list[int]) -> int:
    log.info("Queueing MCD64A1 exports for %d years over MP (%d tasks)...", len(years), len(years))
    for year in years:
        img = build_mcd64_yearly(year).clip(MP_GEOM)
        task = ee.batch.Export.image.toDrive(
            image=img,
            description=f"mcd64_mp_{year}",
            folder=DRIVE_FOLDER,
            fileNamePrefix=f"mcd64_mp_{year}",
            region=MP_GEOM,
            scale=500,
            crs="EPSG:4326",
            maxPixels=int(2e9),
        )
        task.start()
        log.info("  %d queued (id=%s)", year, task.id[:12])
    return 0


def check_status() -> int:
    tasks = ee.batch.Task.list()[:60]
    by_state: dict[str, list[str]] = {}
    for t in tasks:
        s = t.status()
        if "mcd64_mp" in s.get("description", ""):
            by_state.setdefault(s["state"], []).append(s["description"])
    for state, descs in sorted(by_state.items()):
        log.info("[%s] %d tasks", state, len(descs))
        for d in sorted(descs)[:15]:
            log.info("  - %s", d)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--queue", action="store_true", help="Queue Drive exports")
    grp.add_argument("--status", action="store_true", help="Check task status")
    parser.add_argument("--year", type=int, default=None, help="Queue only this year")
    args = parser.parse_args()

    if args.queue:
        years = [args.year] if args.year else YEARS
        return queue_exports(years)
    return check_status()


if __name__ == "__main__":
    raise SystemExit(main())
