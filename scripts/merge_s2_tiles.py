"""Merge multi-tile S2 dNBR GEE exports into per-year single rasters.

GEE splits large exports into tiles (e.g., `s2_dnbr_mp_2019-0000000000-0000000000.tif`).
This script merges them into a single `s2_dnbr_mp_2019.tif` before Andela flood-fill.

Usage:
  python scripts/merge_s2_tiles.py
  python scripts/merge_s2_tiles.py --year 2019
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import rasterio
from rasterio.merge import merge as rio_merge

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data_lake" / "burnt_area"


def merge_year(year: int, delete_tiles_after: bool = False) -> int:
    tiles = sorted(SRC_DIR.glob(f"s2_dnbr_mp_{year}-*.tif"))
    out_path = SRC_DIR / f"s2_dnbr_mp_{year}.tif"
    if out_path.exists() and not tiles:
        log.info("  %s already merged", out_path.name)
        return 0
    if not tiles:
        log.warning("No tiles found for year %d", year)
        return 0

    log.info("Merging %d tiles for year %d...", len(tiles), year)
    for t in tiles:
        log.info("  %s (%.1f MB)", t.name, t.stat().st_size / 1e6)

    srcs = [rasterio.open(str(t)) for t in tiles]
    mosaic, transform = rio_merge(srcs)
    meta = srcs[0].meta.copy()
    meta.update(
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=transform,
        compress="deflate",
    )
    with rasterio.open(str(out_path), "w", **meta) as dst:
        dst.write(mosaic)
    for s in srcs:
        s.close()
    log.info("  Saved merged: %s (%.1f MB, shape=%s)",
             out_path.name, out_path.stat().st_size / 1e6, mosaic.shape)

    if delete_tiles_after:
        for t in tiles:
            t.unlink()
            log.info("  Deleted tile: %s", t.name)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--delete-tiles", action="store_true",
                        help="Delete per-tile files after successful merge")
    args = parser.parse_args()

    years = [args.year] if args.year else list(range(2019, 2027))
    total = 0
    for y in years:
        total += merge_year(y, args.delete_tiles)
    log.info("\nMerged %d years", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
