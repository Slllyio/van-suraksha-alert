"""Plan B.1 — Export MP-wide HLS-L30 dry-season composite to Drive,
then sample 224×224 chips per v6e cell locally.

Strategy (avoids 42K per-cell GEE calls):
  1. Build a single dry-season median composite on GEE server-side
  2. Export to Drive as a single multi-band GeoTIFF (~4 GB at 30m, MP extent)
  3. Download, then sample chips locally per v6e cell
  4. Save chips as .npz files keyed by cell_id

Bands (Prithvi pre-training order):
  Blue, Green, Red, NIR, SWIR1, SWIR2

Year used: 2023 dry season (Feb-May), to match v6e_live training years.

Usage:
  python scripts/build_v6e_cell_chips.py --start-export   # kick off Drive export
  python scripts/build_v6e_cell_chips.py --check-export   # poll status
  python scripts/build_v6e_cell_chips.py --sample-cells   # local sampling after download
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import ee
import numpy as np
import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V6E_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live"
OUT_DIR = ROOT / "data_lake" / "v6e_chips"
COMPOSITE_PATH = OUT_DIR / "mp_hls_l30_2023_dryseason.tif"

# MP extent (slightly wider than v6e grid for safety)
MP_BOUNDS = [73.9, 21.0, 82.9, 27.0]  # [west, south, east, north]

# Chip size at 30m: 224 px × 30m = 6.72 km
CHIP_SIZE = 224
PIXEL_SCALE_M = 30


def gee_init():
    ee.Initialize(project="van-suraksha-alert")


def build_dry_season_composite(year: int = 2023) -> ee.Image:
    """Build HLS-L30 (Landsat) dry-season median composite for MP.

    Bands renamed to Prithvi order: Blue, Green, Red, NIR, SWIR1, SWIR2
    """
    aoi = ee.Geometry.Rectangle(MP_BOUNDS)

    # HLS Landsat L30 collection
    coll = (
        ee.ImageCollection("NASA/HLS/HLSL30/v002")
        .filterBounds(aoi)
        .filterDate(f"{year}-02-01", f"{year}-05-31")
        .filter(ee.Filter.lt("CLOUD_COVERAGE", 30))  # less than 30% cloud
    )

    # Quality mask: Fmask band (bit 1 = cloud, bit 2 = cloud shadow, bit 3 = snow)
    def mask_clouds(img: ee.Image) -> ee.Image:
        fmask = img.select("Fmask")
        clear = (
            fmask.bitwiseAnd(1 << 1).eq(0)  # not cloud
            .And(fmask.bitwiseAnd(1 << 2).eq(0))  # not cloud shadow
            .And(fmask.bitwiseAnd(1 << 3).eq(0))  # not snow
        )
        return img.updateMask(clear)

    masked = coll.map(mask_clouds)

    # Median composite of selected bands
    # HLS L30 bands: B1=coastal, B2=blue, B3=green, B4=red, B5=NIR, B6=SWIR1, B7=SWIR2
    # HLS surface reflectance is float 0-1 with scale factor 0.0001 (so raw values 0-10000 represent SR 0-1)
    # But in GEE the values are already in raw form (0-10000 range for valid pixels)
    composite = masked.select(["B2", "B3", "B4", "B5", "B6", "B7"]).median()
    composite = composite.rename(["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"])

    # HLS-L30 raw values are float with scale 0.0001. Multiply by 10000 then cast to uint16.
    composite = composite.multiply(10000).toUint16()
    return composite, aoi


def start_export(year: int = 2023) -> str:
    log.info("Building dry-season composite for %d...", year)
    gee_init()
    composite, aoi = build_dry_season_composite(year)

    description = f"mp_hls_l30_{year}_dryseason"
    log.info("Starting Drive export: %s", description)
    task = ee.batch.Export.image.toDrive(
        image=composite,
        description=description,
        folder="VanSurakshaExports",
        fileNamePrefix=description,
        region=aoi,
        scale=PIXEL_SCALE_M,
        crs="EPSG:4326",
        maxPixels=1e10,
        fileFormat="GeoTIFF",
        formatOptions={"cloudOptimized": True},
    )
    task.start()
    task_id = task.id
    log.info("Export task started: %s", task_id)
    log.info("Monitor with: python scripts/build_v6e_cell_chips.py --check-export %s", task_id)
    log.info("Or check Drive folder: VanSurakshaExports/")
    return task_id


def check_export(task_id: str | None = None):
    gee_init()
    if task_id:
        tasks = [ee.data.getTaskStatus(task_id)[0]]
    else:
        # Show recent tasks
        tasks = ee.data.listOperations()[:10]
        log.info("Recent tasks:")
    for t in tasks:
        if isinstance(t, dict):
            state = t.get("state", "?")
            desc = t.get("description", "?")
            tid = t.get("id", t.get("name", "?"))
            log.info("  %s | %s | %s", tid, state, desc)


def sample_cells(composite_path: Path):
    """After Drive download, sample 224×224 chips per v6e cell from the MP composite.

    Loads the full raster into memory (uint16, ~9 GB for MP at 30m × 6 bands)
    so per-cell windowed reads are O(1) memory access instead of GeoTIFF block decompression.
    """
    import rasterio
    from rasterio.transform import rowcol

    if not composite_path.exists():
        log.error("Composite not found: %s", composite_path)
        return

    log.info("Loading v6e cells.csv...")
    cells = pd.read_csv(V6E_DIR / "cells.csv")
    log.info("  %d cells", len(cells))

    log.info("Opening composite raster: %s", composite_path)
    with rasterio.open(composite_path) as src:
        log.info("  Shape: %s bands=%d dtype=%s", src.shape, src.count, src.dtypes[0])
        log.info("  Loading full raster into RAM (~%.1f GB)...",
                 src.shape[0] * src.shape[1] * src.count * 2 / 1e9)
        t0 = time.time()
        raster = src.read()  # (bands, H, W) uint16
        transform = src.transform
        H, W = src.shape
        log.info("  Loaded in %.0fs. Array shape: %s", time.time() - t0, raster.shape)

    chips_dir = OUT_DIR / "chips"
    chips_dir.mkdir(parents=True, exist_ok=True)

    n_saved = 0
    n_skipped = 0
    n_failed = 0
    t0 = time.time()
    half = CHIP_SIZE // 2

    for idx, row in cells.iterrows():
        cell_id = row["cell_id"]
        out_path = chips_dir / f"{cell_id}.npz"
        if out_path.exists():
            n_skipped += 1
            continue

        lat = float(row["centroid_lat"])
        lon = float(row["centroid_lon"])

        try:
            py, px = rowcol(transform, lon, lat)
            py, px = int(py), int(px)
            y0, y1 = py - half, py + half
            x0, x1 = px - half, px + half

            # Boundary check
            if y0 < 0 or x0 < 0 or y1 > H or x1 > W:
                # Out of bounds — pad with zeros
                data = np.zeros((raster.shape[0], CHIP_SIZE, CHIP_SIZE), dtype=np.uint16)
                src_y0 = max(0, y0); src_y1 = min(H, y1)
                src_x0 = max(0, x0); src_x1 = min(W, x1)
                if src_y1 > src_y0 and src_x1 > src_x0:
                    dst_y0 = src_y0 - y0; dst_y1 = dst_y0 + (src_y1 - src_y0)
                    dst_x0 = src_x0 - x0; dst_x1 = dst_x0 + (src_x1 - src_x0)
                    data[:, dst_y0:dst_y1, dst_x0:dst_x1] = raster[:, src_y0:src_y1, src_x0:src_x1]
            else:
                data = raster[:, y0:y1, x0:x1]  # (6, 224, 224)

            # Skip cells with mostly zero (no data)
            if (data == 0).mean() > 0.5:
                n_failed += 1
                continue

            # Save: shape (6, 1, 224, 224) for Prithvi (T=1)
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
            log.info("  %d/%d cells (%.0fs, %.0f/s, ETA %.0fs, saved=%d, skipped=%d, failed=%d)",
                     idx + 1, len(cells), elapsed, rate, eta, n_saved, n_skipped, n_failed)

    log.info("\n=== SAMPLING DONE ===")
    log.info("Total cells:   %d", len(cells))
    log.info("Saved:         %d", n_saved)
    log.info("Skipped (cached): %d", n_skipped)
    log.info("Failed:        %d", n_failed)
    log.info("Output:        %s", chips_dir.relative_to(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-export", action="store_true", help="Kick off GEE Drive export")
    ap.add_argument("--check-export", nargs="?", const=None, default=None,
                    help="Check export task status (optionally provide task ID)")
    ap.add_argument("--sample-cells", action="store_true",
                    help="Sample chips locally from downloaded composite")
    ap.add_argument("--composite-path", type=str, default=str(COMPOSITE_PATH),
                    help="Path to downloaded composite GeoTIFF")
    ap.add_argument("--year", type=int, default=2023, help="Year for composite")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.start_export:
        task_id = start_export(args.year)
        log.info("\nNext: wait for export to complete (~30-60 min on GEE)")
        log.info("Then download from Drive folder VanSurakshaExports/ to %s", COMPOSITE_PATH)
        log.info("Then run: python %s --sample-cells", Path(__file__).name)
    elif args.check_export is not None or "--check-export" in sys.argv:
        # Get task_id from positional after --check-export, or list recent if none
        idx = sys.argv.index("--check-export") if "--check-export" in sys.argv else -1
        task_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--") else None
        check_export(task_id)
    elif args.sample_cells:
        sample_cells(Path(args.composite_path))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
