"""Stage 1b — Ingest ESA FireCCI51 burnt-area product for MP, 2014-2020.

ESA FireCCI51: 250m monthly product, superseded by FireCCIS311 (300m). We use
the 250m FireCCI51 for the 2014-2020 overlap window with MCD64. Band:
  - BurnDate: day-of-year (1-366), 0=no burn
  - ConfidenceLevel: 0-100

FireCCI51 archive ENDS 2020 — for 2021-2026 we rely on MCD64 + Sentinel-2 dNBR.

Output: data_lake/burnt_area/firecci_mp_{year}.tif (250m, uint16 DOY)

Usage:
  python scripts/ingest_firecci51_mp.py --queue
  python scripts/ingest_firecci51_mp.py --status
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
DRIVE_FOLDER = "burnt_area_firecci"

MP_GEOM = (
    ee.FeatureCollection("FAO/GAUL/2015/level1")
    .filter(ee.Filter.eq("ADM1_NAME", "Madhya Pradesh"))
    .geometry()
)

YEARS = list(range(2014, 2021))  # 2014-2020 (FireCCI51 archive ends 2020)


def build_firecci_yearly(year: int) -> ee.Image:
    """Composite yearly FireCCI51 BurnDate + ConfidenceLevel for a given year."""
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    col = ee.ImageCollection("ESA/CCI/FireCCI/5_1").filterDate(start, end)
    burn_doy = col.select("BurnDate").max().toUint16().rename("burn_doy")
    conf = col.select("ConfidenceLevel").max().toUint16().rename("burn_confidence")
    lc = col.select("LandCover").mode().toUint16().rename("land_cover")
    return burn_doy.addBands(conf).addBands(lc).set("year", year)


def queue_exports(years: list[int]) -> int:
    log.info("Queueing FireCCI51 exports for %d years over MP...", len(years))
    for year in years:
        img = build_firecci_yearly(year).clip(MP_GEOM)
        task = ee.batch.Export.image.toDrive(
            image=img,
            description=f"firecci_mp_{year}",
            folder=DRIVE_FOLDER,
            fileNamePrefix=f"firecci_mp_{year}",
            region=MP_GEOM,
            scale=250,
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
        if "firecci_mp" in s.get("description", ""):
            by_state.setdefault(s["state"], []).append(s["description"])
    for state, descs in sorted(by_state.items()):
        log.info("[%s] %d tasks", state, len(descs))
        for d in sorted(descs)[:15]:
            log.info("  - %s", d)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--queue", action="store_true")
    grp.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.queue:
        return queue_exports(YEARS)
    return check_status()


if __name__ == "__main__":
    raise SystemExit(main())
