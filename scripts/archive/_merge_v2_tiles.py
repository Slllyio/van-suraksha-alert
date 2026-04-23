"""Merge the 4 v2 MP HLS tiles into a single mosaic GeoTIFF."""
from pathlib import Path
import logging
import sys
import time

import rasterio
from rasterio.merge import merge as rio_merge

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

TILES_DIR = Path("data_lake/v6e_chips/_mp_hls_l30_2023_dryseason_tiles")
OUT_PATH = Path("data_lake/v6e_chips/mp_hls_l30_2023_dryseason.tif")


def main():
    tiles = sorted(TILES_DIR.glob("mp_hls_l30_2023_dryseason-*.tif"))
    log.info("Merging %d tiles:", len(tiles))
    for t in tiles:
        log.info("  %s (%.2f GB)", t.name, t.stat().st_size / 1e9)

    log.info("Opening rasters...")
    srcs = [rasterio.open(t) for t in tiles]
    log.info("Merging (this will take a few minutes for %.1f GB of data)...",
             sum(t.stat().st_size for t in tiles) / 1e9)
    t0 = time.time()
    mosaic, transform = rio_merge(srcs)
    log.info("Merged in %.0fs. Mosaic shape: %s dtype=%s",
             time.time() - t0, mosaic.shape, mosaic.dtype)

    meta = srcs[0].meta.copy()
    meta.update(
        height=mosaic.shape[1], width=mosaic.shape[2],
        transform=transform, compress="deflate", predictor=2,
        tiled=True, blockxsize=512, blockysize=512,
    )
    log.info("Writing mosaic to %s (compressed, tiled)...", OUT_PATH)
    t0 = time.time()
    with rasterio.open(OUT_PATH, "w", **meta) as dst:
        dst.write(mosaic)
    for s in srcs:
        s.close()

    log.info("Wrote in %.0fs. Size: %.2f GB", time.time() - t0, OUT_PATH.stat().st_size / 1e9)
    log.info("DONE: %s", OUT_PATH)


if __name__ == "__main__":
    main()
