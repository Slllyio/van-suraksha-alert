"""
scripts/download_worldcover.py
==============================
Download ESA WorldCover 2021 (10m) for the Guna Division AOI.

The WorldCover raster provides land cover class fractions used by
`train_predictive_fire_risk.py::add_cell_landcover()`.

Classes: 10=tree, 20=shrub, 30=grass, 40=crop, 50=built, 60=bare, 80=water

Source: ESA WorldCover 2021 v200 (AWS Open Data)
  https://esa-worldcover.s3.eu-central-1.amazonaws.com/

Usage:
    python scripts/download_worldcover.py
"""

import os
import sys
import json
import logging
import tempfile
from pathlib import Path

import numpy as np
import requests
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask as rio_mask
from shapely.geometry import shape
from shapely.ops import unary_union

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
AOI_PATH = ROOT / "data" / "aoi" / "gunafinal.geojson"
OUT_PATH = ROOT / "data_lake" / "terrain" / "worldcover_guna_raw.tif"

# ESA WorldCover 2021 v200 tiles on AWS (public, no auth)
# Tile naming: ESA_WorldCover_10m_2021_v200_N{lat}E{lon}_Map.tif
# Each tile covers 3°×3°
BASE_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"


def get_aoi_bounds():
    """Load AOI and return (minx, miny, maxx, maxy) plus geometry list."""
    with open(AOI_PATH) as f:
        geojson = json.load(f)

    polys = []
    for feat in geojson["features"]:
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        polys.append(geom)

    aoi_union = unary_union(polys)
    bounds = aoi_union.bounds
    log.info(f"AOI bounds: {bounds}")
    return bounds, [aoi_union]


def get_required_tiles(bounds):
    """
    Determine which WorldCover tiles cover the AOI.
    Tiles are named by their SW corner: N{lat}E{lon} (3° steps).
    """
    minx, miny, maxx, maxy = bounds

    # WorldCover tiles start at multiples of 3
    lat_start = int(np.floor(miny / 3) * 3)
    lat_end = int(np.floor(maxy / 3) * 3)
    lon_start = int(np.floor(minx / 3) * 3)
    lon_end = int(np.floor(maxx / 3) * 3)

    tiles = []
    for lat in range(lat_start, lat_end + 1, 3):
        for lon in range(lon_start, lon_end + 1, 3):
            lat_prefix = "N" if lat >= 0 else "S"
            lon_prefix = "E" if lon >= 0 else "W"
            tile_name = (
                f"ESA_WorldCover_10m_2021_v200_"
                f"{lat_prefix}{abs(lat):02d}{lon_prefix}{abs(lon):03d}_Map.tif"
            )
            tiles.append(tile_name)

    log.info(f"Required tiles: {tiles}")
    return tiles


def download_tile(tile_name, out_dir):
    """Download a single WorldCover tile from AWS."""
    url = f"{BASE_URL}/{tile_name}"
    out_file = out_dir / tile_name

    if out_file.exists():
        log.info(f"  Already cached: {tile_name}")
        return out_file

    log.info(f"  Downloading: {url}")
    resp = requests.get(url, stream=True, timeout=300)

    if resp.status_code == 404:
        log.warning(f"  Tile not found (404): {tile_name}")
        return None
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(out_file, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                print(f"\r    {pct:.0f}% ({downloaded/1e6:.1f} MB)", end="", flush=True)
    print()

    log.info(f"  Saved: {out_file} ({out_file.stat().st_size / 1e6:.1f} MB)")
    return out_file


def clip_and_save(tile_paths, aoi_geometries, out_path):
    """Merge tiles, clip to AOI, and save output raster."""
    log.info("Merging and clipping tiles to AOI...")

    # Open all tile rasters
    src_files = [rasterio.open(p) for p in tile_paths]

    if len(src_files) == 1:
        mosaic = src_files[0].read(1)
        out_transform = src_files[0].transform
        out_meta = src_files[0].meta.copy()
    else:
        mosaic, out_transform = merge(src_files)
        mosaic = mosaic[0]  # single band
        out_meta = src_files[0].meta.copy()
        out_meta.update({
            "height": mosaic.shape[0],
            "width": mosaic.shape[1],
            "transform": out_transform,
        })

    # Close source files
    for s in src_files:
        s.close()

    # Write merged to temp, then clip
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    out_meta.update({"driver": "GTiff", "count": 1})
    with rasterio.open(tmp_path, "w", **out_meta) as dst:
        dst.write(mosaic, 1)

    # Clip to AOI
    with rasterio.open(tmp_path) as src:
        clipped, clip_transform = rio_mask(
            src, aoi_geometries, crop=True, all_touched=True, nodata=0
        )
        clip_meta = src.meta.copy()
        clip_meta.update({
            "height": clipped.shape[1],
            "width": clipped.shape[2],
            "transform": clip_transform,
            "compress": "lzw",
        })

    # Save final output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **clip_meta) as dst:
        dst.write(clipped)

    # Cleanup temp
    os.unlink(tmp_path)

    log.info(f"Output: {out_path}")
    log.info(f"  Shape: {clipped.shape[1]}×{clipped.shape[2]} pixels")
    log.info(f"  Size: {out_path.stat().st_size / 1e6:.1f} MB")

    # Report class distribution
    data = clipped[0]
    total_valid = (data > 0).sum()
    if total_valid > 0:
        class_map = {10: "tree", 20: "shrub", 30: "grass", 40: "crop",
                     50: "built", 60: "bare", 80: "water"}
        log.info("  Class distribution:")
        for val, name in sorted(class_map.items()):
            count = (data == val).sum()
            pct = count / total_valid * 100
            log.info(f"    {val:3d} ({name:6s}): {count:10d} pixels ({pct:.1f}%)")


def main():
    if OUT_PATH.exists():
        log.info(f"WorldCover raster already exists: {OUT_PATH}")
        log.info("  Delete it to re-download.")
        return

    bounds, aoi_geoms = get_aoi_bounds()
    tiles = get_required_tiles(bounds)

    # Cache directory for raw tiles
    cache_dir = ROOT / "data_lake" / "terrain" / "worldcover_tiles"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Download tiles
    tile_paths = []
    for tile_name in tiles:
        path = download_tile(tile_name, cache_dir)
        if path is not None:
            tile_paths.append(path)

    if not tile_paths:
        log.error("No tiles downloaded — cannot create WorldCover raster")
        sys.exit(1)

    # Clip and save
    clip_and_save(tile_paths, aoi_geoms, OUT_PATH)
    log.info("Done!")


if __name__ == "__main__":
    main()
