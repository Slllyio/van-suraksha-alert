"""Sample 224x224 chips per v6e cell directly from the 4 v2 HLS tiles.

Avoids the merge step — opens all 4 tiles, determines which tile contains
each cell based on lat/lon bounds, reads chip from that tile (with cross-tile
stitching if the chip crosses tile boundaries).
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol
from rasterio.windows import Window, bounds as window_bounds

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
TILES_DIR = ROOT / "data_lake" / "v6e_chips" / "_mp_hls_l30_2023_dryseason_tiles"
V6E_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live"
CHIPS_DIR = ROOT / "data_lake" / "v6e_chips" / "chips"
CHIP_SIZE = 224


def main() -> int:
    CHIPS_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Opening all 4 tiles...")
    tile_paths = sorted(TILES_DIR.glob("mp_hls_l30_2023_dryseason-*.tif"))
    tiles = []
    for tp in tile_paths:
        src = rasterio.open(tp)
        b = src.bounds
        log.info("  %s shape=%s bounds=(%.3f,%.3f,%.3f,%.3f)",
                 tp.name, src.shape, b.left, b.bottom, b.right, b.top)
        tiles.append((src, b))

    log.info("Loading cells...")
    cells = pd.read_csv(V6E_DIR / "cells.csv")
    log.info("  %d cells", len(cells))

    def find_containing_tile(lat: float, lon: float):
        """Return the tile whose bounds contain the point. Returns None if none does."""
        for src, b in tiles:
            if b.left <= lon <= b.right and b.bottom <= lat <= b.top:
                return src, b
        return None, None

    half = CHIP_SIZE // 2
    n_saved = 0
    n_skipped = 0
    n_failed = 0
    n_crossed = 0  # chip crosses tile boundary — needs stitching
    t0 = time.time()

    for idx, row in cells.iterrows():
        cell_id = row["cell_id"]
        out_path = CHIPS_DIR / f"{cell_id}.npz"
        if out_path.exists():
            n_skipped += 1
            continue

        lat = float(row["centroid_lat"])
        lon = float(row["centroid_lon"])

        src, b = find_containing_tile(lat, lon)
        if src is None:
            n_failed += 1
            continue

        try:
            py, px = rowcol(src.transform, lon, lat)
            py, px = int(py), int(px)
            H, W = src.shape

            y0, y1 = py - half, py + half
            x0, x1 = px - half, px + half

            # Check if chip fully inside this tile
            if y0 >= 0 and x0 >= 0 and y1 <= H and x1 <= W:
                data = src.read(window=Window(x0, y0, CHIP_SIZE, CHIP_SIZE))
            else:
                # Chip crosses tile boundary — build composite from all tiles
                n_crossed += 1
                # Compute lat/lon bounds of the desired chip
                # Use this tile's transform to go px->lat/lon
                transform = src.transform
                pixel_w = transform.a
                pixel_h = transform.e  # negative
                chip_left = transform.c + x0 * pixel_w
                chip_right = transform.c + x1 * pixel_w
                chip_top = transform.f + y0 * pixel_h  # pixel_h is negative, top = f + y0*e
                chip_bottom = transform.f + y1 * pixel_h

                # Allocate output (bands, H, W)
                data = np.zeros((src.count, CHIP_SIZE, CHIP_SIZE), dtype=np.uint16)

                for s, sb in tiles:
                    # Intersection between chip bounds and tile bounds
                    int_left = max(chip_left, sb.left)
                    int_right = min(chip_right, sb.right)
                    int_top = min(chip_top, sb.top)
                    int_bottom = max(chip_bottom, sb.bottom)
                    if int_right <= int_left or int_top <= int_bottom:
                        continue
                    # Convert intersection to pixel coords in source tile
                    s_py0, s_px0 = rowcol(s.transform, int_left, int_top)
                    s_py1, s_px1 = rowcol(s.transform, int_right, int_bottom)
                    s_py0, s_py1 = int(min(s_py0, s_py1)), int(max(s_py0, s_py1))
                    s_px0, s_px1 = int(min(s_px0, s_px1)), int(max(s_px0, s_px1))
                    s_w = max(1, s_px1 - s_px0)
                    s_h = max(1, s_py1 - s_py0)
                    # Read from source
                    sub = s.read(window=Window(s_px0, s_py0, s_w, s_h))
                    # Compute destination location in output array
                    d_py0, d_px0 = rowcol(transform, int_left, int_top)
                    d_py0 = int(d_py0) - y0
                    d_px0 = int(d_px0) - x0
                    d_py0, d_px0 = max(0, d_py0), max(0, d_px0)
                    d_py1 = min(CHIP_SIZE, d_py0 + sub.shape[1])
                    d_px1 = min(CHIP_SIZE, d_px0 + sub.shape[2])
                    dh = d_py1 - d_py0
                    dw = d_px1 - d_px0
                    if dh > 0 and dw > 0:
                        data[:, d_py0:d_py1, d_px0:d_px1] = sub[:, :dh, :dw]

            # Skip if chip is mostly empty
            if data.shape[1:] != (CHIP_SIZE, CHIP_SIZE):
                n_failed += 1
                continue
            # For cloud-masked: some pixels may be 0 but should be rare now with multiply(10000) fix
            nonzero_frac = (data > 0).mean()
            if nonzero_frac < 0.10:  # less than 10% valid
                n_failed += 1
                continue

            hls = data[:, np.newaxis, :, :].astype(np.float32) / 10000.0
            np.savez_compressed(out_path, hls=hls, cell_id=cell_id)
            n_saved += 1
        except Exception as e:
            n_failed += 1
            if n_failed < 5:
                log.warning("  Failed %s: %s", cell_id, e)

        if (idx + 1) % 1000 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            eta = (len(cells) - idx - 1) / max(rate, 0.01)
            log.info("  %d/%d cells (%.0fs, %.0f/s, ETA %.0fs, saved=%d failed=%d crossed=%d)",
                     idx + 1, len(cells), elapsed, rate, eta, n_saved, n_failed, n_crossed)

    for src, _ in tiles:
        src.close()

    log.info("\n=== SAMPLING DONE ===")
    log.info("Saved: %d / %d", n_saved, len(cells))
    log.info("Skipped (cached): %d", n_skipped)
    log.info("Failed: %d", n_failed)
    log.info("Boundary-crossing chips: %d", n_crossed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
