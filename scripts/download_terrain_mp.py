"""
scripts/download_terrain_mp.py
===============================
Download Copernicus DEM 30m for all Madhya Pradesh, compute slope + TPI.

Covers: lat 21-27°N, lon 74-83°E (54 tiles).
Source: AWS Open Data (free, no auth).

Output:
  data/rasters/dem_mp_30m.tif
  data/rasters/slope_mp_30m.tif
  data/rasters/tpi_mp_30m.tif

Usage:
    python scripts/download_terrain_mp.py
"""

import logging
import subprocess
import sys
from pathlib import Path

import numpy as np
import requests
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("terrain_mp")

ROOT = Path(__file__).resolve().parent.parent
TILE_DIR = ROOT / "data_lake" / "terrain" / "copernicus_dem_30m_mp"
OUT_DIR = ROOT / "data" / "rasters"

# MP forest bounds: lat ~21-27, lon ~74-83
LATS = range(21, 27)   # N21 through N26 (each tile covers +1°)
LONS = range(74, 83)   # E074 through E082

# AWS Copernicus DEM 30m public bucket
BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_url(lat, lon):
    """Construct the download URL for a Copernicus DEM tile."""
    tile_name = f"Copernicus_DSM_COG_10_N{lat:02d}_00_E0{lon:02d}_00_DEM"
    return f"{BASE_URL}/{tile_name}/{tile_name}.tif"


def download_tile(lat, lon, out_dir):
    """Download a single DEM tile. Returns path or None if failed."""
    tile_name = f"Copernicus_DSM_COG_10_N{lat:02d}_00_E0{lon:02d}_00_DEM.tif"
    out_path = out_dir / tile_name

    if out_path.exists() and out_path.stat().st_size > 1_000_000:
        return out_path

    url = tile_url(lat, lon)
    try:
        r = requests.get(url, stream=True, timeout=120)
        if r.status_code == 404:
            log.warning(f"  Tile N{lat:02d}_E0{lon:02d} not found (ocean/no data)")
            return None
        r.raise_for_status()

        total = int(r.headers.get("content-length", 0))
        with open(out_path, "wb") as f:
            with tqdm(total=total, unit="B", unit_scale=True, desc=tile_name[:40], leave=False) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))

        log.info(f"  Downloaded {tile_name}: {out_path.stat().st_size / 1e6:.1f} MB")
        return out_path
    except Exception as e:
        log.error(f"  Failed N{lat:02d}_E0{lon:02d}: {e}")
        if out_path.exists():
            out_path.unlink()
        return None


def merge_tiles(tile_paths, output_path):
    """Merge multiple DEM tiles into a single raster using GDAL."""
    import rasterio
    from rasterio.merge import merge

    log.info(f"Merging {len(tile_paths)} tiles into {output_path.name}...")

    datasets = [rasterio.open(p) for p in tile_paths]
    mosaic, out_transform = merge(datasets)

    profile = datasets[0].profile.copy()
    profile.update({
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_transform,
        "compress": "deflate",
        "predictor": 2,
    })

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mosaic)

    for ds in datasets:
        ds.close()

    log.info(f"  Merged DEM: {mosaic.shape[1]}×{mosaic.shape[2]}, {output_path.stat().st_size / 1e6:.0f} MB")
    return output_path


def compute_slope(dem_path, slope_path):
    """Compute slope from DEM using GDAL CLI or manual fallback."""
    log.info("Computing slope from DEM...")
    try:
        cmd = [
            "gdaldem", "slope", str(dem_path), str(slope_path),
            "-p",           # percent slope
            "-co", "COMPRESS=DEFLATE",
            "-co", "PREDICTOR=2",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"gdaldem failed: {result.stderr}")
        log.info(f"  Slope computed: {slope_path.stat().st_size / 1e6:.0f} MB")
        return slope_path
    except (FileNotFoundError, RuntimeError) as e:
        log.warning(f"  GDAL CLI unavailable ({e}), computing slope manually...")
        return _compute_slope_manual(dem_path, slope_path)


def _downsample_dem(dem_path, output_path, factor=8):
    """Downsample DEM by given factor (30m * 8 = 240m). Memory-safe."""
    import rasterio
    from rasterio.enums import Resampling

    log.info(f"  Downsampling DEM by {factor}x for slope/TPI computation...")

    with rasterio.open(dem_path) as src:
        new_h = src.height // factor
        new_w = src.width // factor
        data = src.read(1, out_shape=(new_h, new_w), resampling=Resampling.average).astype(np.float32)
        data[data < -1000] = np.nan

        new_transform = src.transform * src.transform.scale(factor, factor)
        profile = src.profile.copy()
        profile.update({
            "height": new_h, "width": new_w,
            "transform": new_transform,
            "dtype": "float32",
            "compress": "deflate", "predictor": 2,
        })

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data[np.newaxis, :, :])

    log.info(f"  Downsampled: {new_h}×{new_w} ({output_path.stat().st_size / 1e6:.0f} MB)")
    return output_path, data, profile


def _compute_slope_manual(dem_path, slope_path):
    """Compute slope manually from downsampled DEM."""
    import rasterio
    log.info("  Computing slope manually...")

    # Downsample to ~240m for memory safety
    ds_path = dem_path.parent / "dem_mp_240m.tif"
    ds_path_obj, dem, profile = _downsample_dem(dem_path, ds_path)

    res_m = abs(profile["transform"].a) * 111320  # meters per degree
    dy, dx = np.gradient(np.nan_to_num(dem, nan=0.0), res_m)
    slope_pct = np.sqrt(dx**2 + dy**2) * 100
    slope_pct = np.nan_to_num(slope_pct, nan=0.0).astype(np.float32)

    with rasterio.open(slope_path, "w", **profile) as dst:
        dst.write(slope_pct[np.newaxis, :, :])

    log.info(f"  Slope computed: {slope_path.stat().st_size / 1e6:.0f} MB")
    return slope_path


def compute_tpi(dem_path, tpi_path, window=5):
    """Compute Topographic Position Index from downsampled DEM."""
    import rasterio
    from scipy.ndimage import uniform_filter

    log.info(f"Computing TPI (window={window})...")

    # Use downsampled DEM if available, otherwise downsample
    ds_path = dem_path.parent / "dem_mp_240m.tif"
    if ds_path.exists():
        with rasterio.open(ds_path) as src:
            dem = src.read(1).astype(np.float32)
            dem[dem < -1000] = np.nan
            profile = src.profile.copy()
    else:
        ds_path_obj, dem, profile = _downsample_dem(dem_path, ds_path)

    # TPI = elevation - mean(neighborhood elevation)
    mean_elev = uniform_filter(np.nan_to_num(dem, nan=0.0), size=window)
    tpi = dem - mean_elev
    tpi = np.nan_to_num(tpi, nan=0.0).astype(np.float32)

    profile.update({"dtype": "float32"})
    with rasterio.open(tpi_path, "w", **profile) as dst:
        dst.write(tpi[np.newaxis, :, :])

    log.info(f"  TPI computed: {tpi_path.stat().st_size / 1e6:.0f} MB")
    return tpi_path


def main():
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Download tiles
    n_total = len(LATS) * len(LONS)
    log.info(f"Downloading {n_total} Copernicus DEM 30m tiles for MP...")

    tile_paths = []
    for lat in LATS:
        for lon in LONS:
            path = download_tile(lat, lon, TILE_DIR)
            if path is not None:
                tile_paths.append(path)

    log.info(f"\nDownloaded {len(tile_paths)}/{n_total} tiles")

    if not tile_paths:
        log.error("No tiles downloaded!")
        return

    # Step 2: Merge tiles
    dem_path = OUT_DIR / "dem_mp_30m.tif"
    if not dem_path.exists():
        merge_tiles(tile_paths, dem_path)
    else:
        log.info(f"DEM already exists: {dem_path}")

    # Step 3: Compute slope
    slope_path = OUT_DIR / "slope_mp_30m.tif"
    if not slope_path.exists():
        compute_slope(dem_path, slope_path)
    else:
        log.info(f"Slope already exists: {slope_path}")

    # Step 4: Compute TPI
    tpi_path = OUT_DIR / "tpi_mp_30m.tif"
    if not tpi_path.exists():
        compute_tpi(dem_path, tpi_path)
    else:
        log.info(f"TPI already exists: {tpi_path}")

    log.info(f"\nDone! MP-wide terrain rasters saved to {OUT_DIR}")
    log.info(f"  DEM:   {dem_path}")
    log.info(f"  Slope: {slope_path}")
    log.info(f"  TPI:   {tpi_path}")


if __name__ == "__main__":
    main()
