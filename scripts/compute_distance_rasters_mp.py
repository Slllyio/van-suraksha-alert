"""
scripts/compute_distance_rasters_mp.py
=======================================
Compute road distance and settlement distance rasters for all Madhya Pradesh.

Settlement source: ESA WorldCover 2021 (class 50 = built-up) — ALREADY DOWNLOADED
Road source: OpenStreetMap via osmnx (Overpass API, chunked by 1° tiles)

Output at ~500m resolution:
  data/rasters/settlement_dist_mp.tif  (distance to nearest settlement, km)
  data/rasters/road_dist_mp.tif        (distance to nearest road, km)

Usage:
    python scripts/compute_distance_rasters_mp.py
    python scripts/compute_distance_rasters_mp.py --roads-only
    python scripts/compute_distance_rasters_mp.py --settlements-only
"""

import argparse
import logging
import os
import time
from pathlib import Path

# Fix PROJ database conflict with PostgreSQL/PostGIS
_proj_path = Path(r"C:\Users\S.C.C\AppData\Local\Programs\Python\Python312\Lib\site-packages\rasterio\proj_data")
if _proj_path.exists():
    os.environ["PROJ_LIB"] = str(_proj_path)

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from scipy.ndimage import distance_transform_edt
from shapely.geometry import box

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dist_rasters")

ROOT = Path(__file__).resolve().parent.parent
WC_DIR = ROOT / "data_lake" / "terrain" / "worldcover_tiles"
OUT_DIR = ROOT / "data" / "rasters"

# MP forest bounds (with buffer)
BBOX = (74.0, 21.0, 83.0, 27.0)  # west, south, east, north
RES_DEG = 0.005  # ~500m at 24°N

# Output grid dimensions
WIDTH = int((BBOX[2] - BBOX[0]) / RES_DEG)    # 1800
HEIGHT = int((BBOX[3] - BBOX[1]) / RES_DEG)   # 1200
TRANSFORM = from_bounds(*BBOX, WIDTH, HEIGHT)

# Approximate meters per pixel at MP latitude (~24°N)
PIX_Y_M = RES_DEG * 111_000             # ~555m
PIX_X_M = RES_DEG * 111_000 * 0.9135    # ~507m (cos(24°))

PROFILE = {
    "driver": "GTiff",
    "dtype": "float32",
    "width": WIDTH,
    "height": HEIGHT,
    "count": 1,
    "crs": "EPSG:4326",
    "transform": TRANSFORM,
    "compress": "deflate",
    "predictor": 2,
}


def compute_settlement_distance():
    """
    Extract built-up (class 50) from WorldCover tiles, create distance raster.
    Uses rasterio.warp.reproject for robust tile-to-grid coordinate mapping.
    """
    out_path = OUT_DIR / "settlement_dist_mp.tif"
    if out_path.exists():
        # Validate existing file isn't garbage (all zeros)
        with rasterio.open(out_path) as chk:
            sample = chk.read(1)
            if sample.max() > 0:
                log.info(f"Settlement distance already exists: {out_path}")
                return out_path
            log.warning("Existing settlement_dist is all zeros — recomputing...")

    log.info("Computing settlement distance from WorldCover (class 50 = built-up)...")

    # Initialize output raster at 500m
    settlement_mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)

    # Process each WorldCover tile
    wc_tiles = sorted(WC_DIR.glob("ESA_WorldCover_*.tif"))
    log.info(f"  Found {len(wc_tiles)} WorldCover tiles")

    for tile_path in wc_tiles:
        log.info(f"  Processing {tile_path.name}...")

        with rasterio.open(tile_path) as src:
            # Read at reduced resolution (~500m instead of 10m)
            scale = src.res[0] / RES_DEG  # ~0.0167
            tile_h = max(1, int(src.height * scale))
            tile_w = max(1, int(src.width * scale))

            tile_data = src.read(1, out_shape=(tile_h, tile_w),
                                 resampling=Resampling.mode)

            # Create built-up mask (class 50)
            tile_builtup = (tile_data == 50).astype(np.uint8)

            # Build transform for the reduced-resolution tile
            tile_transform = from_bounds(
                src.bounds.left, src.bounds.bottom,
                src.bounds.right, src.bounds.top,
                tile_w, tile_h
            )

            # Reproject tile into output grid using rasterio (robust coordinate mapping)
            tile_in_grid = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
            reproject(
                source=tile_builtup,
                destination=tile_in_grid,
                src_transform=tile_transform,
                src_crs=src.crs,
                dst_transform=TRANSFORM,
                dst_crs="EPSG:4326",
                resampling=Resampling.max,  # if ANY source pixel is built-up, mark target
            )

            settlement_mask = np.maximum(settlement_mask, tile_in_grid)

            n_tile = int(tile_builtup.sum())
            n_grid = int(tile_in_grid.sum())
            log.info(f"    Tile built-up: {n_tile} ({100*n_tile/tile_builtup.size:.1f}%), in grid: {n_grid}")

    total_builtup = int(settlement_mask.sum())
    log.info(f"  Total built-up pixels in MP grid: {total_builtup} ({100*total_builtup/settlement_mask.size:.2f}%)")

    if total_builtup == 0:
        log.error("  No built-up pixels found! Check WorldCover tiles.")
        return None

    # Distance transform (in km)
    log.info("  Computing Euclidean distance transform...")
    dist_pixels = distance_transform_edt(
        settlement_mask == 0,
        sampling=(PIX_Y_M, PIX_X_M)
    )
    dist_km = (dist_pixels / 1000.0).astype(np.float32)

    log.info(f"  Distance range: {dist_km.min():.2f} - {dist_km.max():.1f} km")
    log.info(f"  Mean distance to settlement: {dist_km.mean():.1f} km")

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **PROFILE) as dst:
        dst.write(dist_km[np.newaxis, :, :])

    log.info(f"  Saved: {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
    return out_path


def download_roads_chunked():
    """
    Download OSM driveable road network for MP using Overpass API directly.
    Uses 1° chunks with targeted query (only highway types that represent actual roads).
    Includes retry logic with exponential backoff for Overpass API flakiness.
    Returns GeoDataFrame of all road geometries.
    """
    import requests
    import pandas as pd
    from shapely.geometry import LineString

    cache_path = OUT_DIR / "osm_roads_mp.gpkg"
    if cache_path.exists():
        log.info(f"  Loading cached roads from {cache_path}...")
        return gpd.read_file(cache_path)

    log.info("Downloading OSM roads for all MP (1-degree chunks via Overpass)...")

    # Try multiple Overpass mirrors for reliability
    OVERPASS_URLS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    # Only major roads (skip footpaths/cycleway) — reduces query size
    ROAD_TYPES = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|track"

    all_roads = []
    failed_chunks = []
    lat_range = range(int(BBOX[1]), int(BBOX[3]))  # 21..26
    lon_range = range(int(BBOX[0]), int(BBOX[2]))   # 74..82

    total_chunks = len(lat_range) * len(lon_range)
    done = 0

    def fetch_chunk(lat, lon, max_retries=4):
        """Fetch roads for a 1° chunk with retry logic across mirrors."""
        query = f"""
        [out:json][timeout:180];
        way["highway"~"^({ROAD_TYPES})$"]({lat},{lon},{lat+1},{lon+1});
        out geom;
        """
        for attempt in range(max_retries):
            url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
            try:
                r = requests.post(url, data={"data": query}, timeout=200)
                r.raise_for_status()
                data = r.json()

                geometries = []
                for element in data.get("elements", []):
                    if element["type"] == "way" and "geometry" in element:
                        coords = [(n["lon"], n["lat"]) for n in element["geometry"]]
                        if len(coords) >= 2:
                            geometries.append(LineString(coords))
                return geometries

            except Exception as e:
                wait = (attempt + 1) * 10  # 10, 20, 30, 40 seconds
                if attempt < max_retries - 1:
                    log.warning(f"    Attempt {attempt+1} failed ({url.split('/')[2]}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    log.warning(f"    All {max_retries} attempts failed: {e}")
                    return None

    for lat in lat_range:
        for lon in lon_range:
            done += 1
            chunk_label = f"({lat},{lon})-({lat+1},{lon+1})"
            log.info(f"  [{done}/{total_chunks}] Downloading roads for {chunk_label}...")

            geometries = fetch_chunk(lat, lon)
            if geometries is not None and len(geometries) > 0:
                chunk_gdf = gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326")
                all_roads.append(chunk_gdf)
                log.info(f"    {len(geometries)} road segments")
            elif geometries is not None:
                log.info(f"    No roads found")
            else:
                failed_chunks.append(chunk_label)

            # Rate limit — 10 sec between chunks to avoid 429s
            time.sleep(10)

    if failed_chunks:
        log.warning(f"  Failed chunks ({len(failed_chunks)}/{total_chunks}): {failed_chunks}")

    if not all_roads:
        log.error("No road data downloaded!")
        return None

    log.info(f"  Merging {len(all_roads)} chunks...")
    roads_gdf = gpd.GeoDataFrame(pd.concat(all_roads, ignore_index=True), crs="EPSG:4326")
    log.info(f"  Total road segments: {len(roads_gdf)}")

    # Cache to disk
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    roads_gdf.to_file(cache_path, driver="GPKG")
    log.info(f"  Cached to {cache_path}")

    return roads_gdf


def download_roads_geofabrik():
    """
    Download Geofabrik India Central Zone shapefile as a fallback.
    Central Zone covers most of MP.
    """
    import requests, zipfile, io

    cache_path = OUT_DIR / "osm_roads_mp.gpkg"
    if cache_path.exists():
        log.info(f"  Loading cached roads from {cache_path}...")
        return gpd.read_file(cache_path)

    # Try to download Geofabrik India roads (the free .shp.zip for central-zone)
    url = "https://download.geofabrik.de/asia/india/central-zone-latest-free.shp.zip"
    log.info(f"Downloading Geofabrik Central Zone shapefile...")
    log.info(f"  URL: {url}")
    log.info(f"  This may take 5-10 minutes (~750 MB)...")

    shp_dir = OUT_DIR / "geofabrik_central"
    roads_shp = shp_dir / "gis_osm_roads_free_1.shp"

    if not roads_shp.exists():
        shp_dir.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, stream=True, timeout=600)
        r.raise_for_status()

        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        zip_path = shp_dir / "central-zone.shp.zip"

        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0 and downloaded % (10 * 1024 * 1024) < 65536:
                    pct = 100 * downloaded / total
                    log.info(f"    {downloaded / 1e6:.0f} / {total / 1e6:.0f} MB ({pct:.0f}%)")

        log.info(f"  Extracting roads shapefile...")
        with zipfile.ZipFile(zip_path) as zf:
            # Only extract roads files
            road_files = [f for f in zf.namelist() if "roads_free_1" in f]
            for fname in road_files:
                zf.extract(fname, shp_dir)
        log.info(f"  Extracted {len(road_files)} files")

    log.info(f"  Loading {roads_shp}...")
    roads_gdf = gpd.read_file(roads_shp, bbox=BBOX)
    log.info(f"  Roads in MP bbox: {len(roads_gdf)}")

    # Cache as GPKG for faster reloads
    roads_gdf[["geometry"]].to_file(cache_path, driver="GPKG")
    log.info(f"  Cached to {cache_path}")

    return roads_gdf


def compute_road_distance(roads_gdf):
    """
    Rasterize road geometries and compute distance transform.
    """
    out_path = OUT_DIR / "road_dist_mp.tif"
    if out_path.exists():
        log.info(f"Road distance already exists: {out_path}")
        return out_path

    log.info("Rasterizing roads and computing distance transform...")

    # Clip to bbox
    mp_box = box(*BBOX)
    roads_clipped = roads_gdf[roads_gdf.intersects(mp_box)]
    log.info(f"  Roads in MP bbox: {len(roads_clipped)}")

    # Rasterize: 1 = road pixel, 0 = no road
    shapes = [(geom, 1) for geom in roads_clipped.geometry if geom is not None and not geom.is_empty]
    log.info(f"  Rasterizing {len(shapes)} road geometries to {WIDTH}x{HEIGHT} grid...")

    road_raster = rasterize(
        shapes,
        out_shape=(HEIGHT, WIDTH),
        transform=TRANSFORM,
        fill=0,
        dtype=np.uint8,
        all_touched=True,  # Include pixels that road touches (not just centerline)
    )

    n_road = int(road_raster.sum())
    log.info(f"  Road pixels: {n_road} ({100*n_road/road_raster.size:.1f}%)")

    # Distance transform (in km)
    log.info("  Computing Euclidean distance transform...")
    dist_pixels = distance_transform_edt(
        road_raster == 0,
        sampling=(PIX_Y_M, PIX_X_M)
    )
    dist_km = (dist_pixels / 1000.0).astype(np.float32)

    log.info(f"  Distance range: {dist_km.min():.2f} - {dist_km.max():.1f} km")
    log.info(f"  Mean distance to road: {dist_km.mean():.1f} km")

    # Save
    with rasterio.open(out_path, "w", **PROFILE) as dst:
        dst.write(dist_km[np.newaxis, :, :])

    log.info(f"  Saved: {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
    return out_path


def main():
    import pandas as pd  # needed by download_roads_chunked

    parser = argparse.ArgumentParser(description="Compute MP-wide distance rasters")
    parser.add_argument("--roads-only", action="store_true")
    parser.add_argument("--settlements-only", action="store_true")
    parser.add_argument("--road-source", default="osmnx",
                        choices=["osmnx", "geofabrik"],
                        help="Road data source: osmnx (Overpass API) or geofabrik (shapefile)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Output grid: {WIDTH}x{HEIGHT} pixels at {RES_DEG}deg ({PIX_Y_M:.0f}m x {PIX_X_M:.0f}m)")
    log.info(f"Bbox: {BBOX}")

    if not args.roads_only:
        compute_settlement_distance()

    if not args.settlements_only:
        # Download roads
        if args.road_source == "geofabrik":
            roads = download_roads_geofabrik()
        else:
            import pandas as pd
            roads = download_roads_chunked()

        if roads is not None:
            compute_road_distance(roads)

    log.info("\nDone!")


if __name__ == "__main__":
    main()
