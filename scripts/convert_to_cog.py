"""
Convert GeoTIFFs to Cloud-Optimized GeoTIFFs (COGs)
====================================================
Adds internal tiling and overview pyramids for fast tile serving via TiTiler.

Usage::

    python scripts/convert_to_cog.py                          # convert all data/rasters/*.tif
    python scripts/convert_to_cog.py data/rasters/dem_30m.tif # convert specific file
    python scripts/convert_to_cog.py --check                  # audit without converting
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

RASTER_DIRS = [
    Path("E:/FIRE/data/rasters"),
    Path("E:/FIRE/data/labels"),
    Path("E:/FIRE/data/state"),
]


def is_cog(path: Path) -> bool:
    """Check if a GeoTIFF is already Cloud-Optimized (tiled + overviews)."""
    with rasterio.open(path) as src:
        return src.is_tiled and len(src.overviews(1)) > 0


def convert_to_cog(src_path: Path, dst_path: Path | None = None) -> Path:
    """
    Convert a GeoTIFF to COG format with tiling and overviews.

    Overwrites in-place if dst_path is None.
    """
    if dst_path is None:
        dst_path = src_path.with_suffix(".cog.tif")

    with rasterio.open(src_path) as src:
        profile = src.profile.copy()

        # COG profile: tiled, deflate compressed
        profile.update(
            driver="GTiff",
            tiled=True,
            blockxsize=512,
            blockysize=512,
            compress="deflate",
            predictor=2 if profile.get("dtype", "float32") in ("int16", "int32", "uint16", "uint8") else 3,
        )

        # Compute appropriate overview levels
        max_dim = max(src.height, src.width)
        overviews = []
        level = 2
        while max_dim // level >= 256:
            overviews.append(level)
            level *= 2

        # Write COG
        with rasterio.open(dst_path, "w", **profile) as dst:
            for i in range(1, src.count + 1):
                data = src.read(i)
                dst.write(data, i)

            # Build overviews
            if overviews:
                dst.build_overviews(overviews, Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")

        log.info("  COG → %s  (overviews: %s)", dst_path.name, overviews)

    return dst_path


def main():
    parser = argparse.ArgumentParser(description="Convert GeoTIFFs to COG format")
    parser.add_argument("files", nargs="*", help="Specific files to convert")
    parser.add_argument("--check", action="store_true", help="Audit only, don't convert")
    parser.add_argument("--in-place", action="store_true", help="Replace originals (creates .bak)")
    args = parser.parse_args()

    if args.files:
        tifs = [Path(f) for f in args.files]
    else:
        tifs = []
        for d in RASTER_DIRS:
            if d.exists():
                tifs.extend(d.glob("*.tif"))

    cog_count = 0
    need_convert = 0

    for tif in sorted(tifs):
        if tif.suffix == ".cog" or ".cog." in tif.name:
            continue

        if is_cog(tif):
            log.info("[OK]  %s — already COG", tif.name)
            cog_count += 1
        else:
            with rasterio.open(tif) as src:
                log.info("[FIX] %s — tiled=%s, overviews=%d, %s",
                         tif.name, src.is_tiled, len(src.overviews(1)), src.shape)
            need_convert += 1

            if not args.check:
                convert_to_cog(tif)

    log.info("\nSummary: %d COG-ready, %d need conversion", cog_count, need_convert)

    if args.check and need_convert > 0:
        log.info("Run without --check to convert.")


if __name__ == "__main__":
    main()
