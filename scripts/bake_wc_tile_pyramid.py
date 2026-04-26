"""
Bake the ESA WorldCover 10 m raster into an XYZ tile pyramid + a
single PMTiles archive for the v4 portal `TileLayer`.

Resolution at each zoom level (web-mercator at MP latitudes ~24°N):

    z6  ~ 1.7 km / px   (~600 m / px effective with native sample)
    z7  ~ 850  m / px
    z8  ~ 425  m / px
    z9  ~ 213  m / px
    z10 ~ 107  m / px
    z11 ~  53  m / px
    z12 ~  27  m / px
    z13 ~  13  m / px   <-- target "native" zoom for 10 m WC
    z14 ~   7  m / px   (oversampled — diminishing returns)

Default config: z6-z13. Cap at z13 to stay under ~250 MB total.
Each tile is a 256x256 RGBA PNG color-coded by SB40 fuel class
(matching dashboard/v3/static/fuel_class_mp.png) with non-forest /
non-burnable pixels alpha=0.

Outputs:
  dashboard/v3/static/wc_tiles/{z}/{x}/{y}.png    — XYZ directory
  dashboard/v3/static/wc_fuel_class.pmtiles       — single-file archive
  dashboard/v3/static/wc_tiles_meta.json          — metadata for portal

Forest mask: same `data/aoi/mp_beats_wgs84.geojson` used by the
existing `_forest_clip_helper` and `bake_wc_native_png.py`. Only
forest-beat pixels are colored; everything else transparent.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from PIL import Image
from pmtiles.tile import (
    Compression, TileType, zxy_to_tileid,
)
from pmtiles.writer import Writer
from rasterio.windows import from_bounds

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
WC_TILE_DIR = REPO_ROOT / "data_lake" / "land_cover" / "worldcover_expanded"
BEATS_GEOJSON = REPO_ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"
OUT_XYZ_ROOT = REPO_ROOT / "dashboard" / "v3" / "static" / "wc_tiles"
OUT_PMTILES = REPO_ROOT / "dashboard" / "v3" / "static" / "wc_fuel_class.pmtiles"
OUT_META = REPO_ROOT / "dashboard" / "v3" / "static" / "wc_tiles_meta.json"

# AOI
LAT_MIN, LAT_MAX = 21.0, 27.0
LON_MIN, LON_MAX = 74.0, 83.0

ZOOM_MIN = 6
ZOOM_MAX = 13      # ~13 m/px at z13 — close to native 10 m WC
TILE_SIZE = 256

# Fuel-class palette — must match colors.fuelClass tokens + the
# bake_wc_native_png.py output. RGBA, alpha=0 for non-burnable.
WC_COLOR: dict[int, tuple[int, int, int, int]] = {
    10:  (31, 107, 58, 230),    # tree -> TL2 forest green
    20:  (42, 140, 140, 220),   # shrub -> SH2 teal
    30:  (236, 72, 152, 220),   # grassland -> GR2 pink
    40:  (5, 5, 5, 230),        # cropland -> GR1 black
    50:  (0, 0, 0, 0),          # built-up
    60:  (0, 0, 0, 0),          # bare
    70:  (0, 0, 0, 0),          # snow
    80:  (0, 0, 0, 0),          # water
    90:  (0, 0, 0, 0),          # wetland
    95:  (0, 0, 0, 0),          # mangrove
    100: (0, 0, 0, 0),          # moss
    0:   (0, 0, 0, 0),          # nodata
}


def _build_color_lut() -> np.ndarray:
    lut = np.zeros((256, 4), dtype=np.uint8)
    for cls, rgba in WC_COLOR.items():
        lut[cls] = rgba
    return lut


_TILE_HANDLES: dict[Path, rasterio.DatasetReader] = {}


def _open_wc_tile_for(lat: float, lon: float) -> rasterio.DatasetReader | None:
    """Find the WC source tile that covers a point. Caches handles."""
    for tile_path in WC_TILE_DIR.glob("ESA_WorldCover_10m_2021_v200_*_Map.tif"):
        if tile_path not in _TILE_HANDLES:
            _TILE_HANDLES[tile_path] = rasterio.open(tile_path)
        ds = _TILE_HANDLES[tile_path]
        b = ds.bounds
        if b.left <= lon < b.right and b.bottom <= lat < b.top:
            return ds
    return None


def _build_forest_mask_for_tile_bbox(
    tile_bbox: mercantile.LngLatBbox, beats_gdf,
) -> np.ndarray:
    """Rasterize MP forest beats inside a given tile bbox to a TILE_SIZE^2 mask.
    Returns uint8 array (1 = inside forest, 0 = outside)."""
    from rasterio.features import rasterize
    transform = rasterio.transform.from_bounds(
        tile_bbox.west, tile_bbox.south, tile_bbox.east, tile_bbox.north,
        TILE_SIZE, TILE_SIZE,
    )
    # Filter beats to those that intersect the tile bbox to avoid scanning
    # 8973 polygons per tile.
    from shapely.geometry import box as shapely_box
    bbox_geom = shapely_box(
        tile_bbox.west, tile_bbox.south, tile_bbox.east, tile_bbox.north,
    )
    candidates = beats_gdf[beats_gdf.geometry.intersects(bbox_geom)]
    if len(candidates) == 0:
        return np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
    shapes = ((geom, 1) for geom in candidates.geometry if geom is not None)
    mask = rasterize(
        shapes=shapes,
        out_shape=(TILE_SIZE, TILE_SIZE),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )
    return mask


def _render_tile(tile: mercantile.Tile, lut: np.ndarray, beats_gdf) -> Image.Image | None:
    """Render a single XYZ tile. Returns RGBA PIL Image or None if entirely outside MP / outside forest."""
    bbox = mercantile.bounds(tile)
    # Fast culling — tile entirely outside MP AOI
    if bbox.east < LON_MIN or bbox.west > LON_MAX or bbox.north < LAT_MIN or bbox.south > LAT_MAX:
        return None
    forest_mask = _build_forest_mask_for_tile_bbox(bbox, beats_gdf)
    if int(forest_mask.sum()) == 0:
        return None

    # Sample WC at TILE_SIZE x TILE_SIZE grid
    wc_classes = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
    lats = np.linspace(bbox.north, bbox.south, TILE_SIZE, endpoint=False)
    lons = np.linspace(bbox.west, bbox.east, TILE_SIZE, endpoint=False)
    # Pick the WC source tile from the tile's center first; if pixel
    # falls outside, fall back to per-pixel lookup.
    center_lat = (bbox.north + bbox.south) / 2
    center_lon = (bbox.west + bbox.east) / 2
    main_ds = _open_wc_tile_for(center_lat, center_lon)
    if main_ds is None:
        # Tile center outside any WC tile — try corners
        main_ds = _open_wc_tile_for(bbox.north, bbox.west) \
            or _open_wc_tile_for(bbox.south, bbox.east)
    if main_ds is None:
        return None

    # Fast path: read the WC window covering the tile bbox + nearest-resample
    try:
        win = from_bounds(bbox.west, bbox.south, bbox.east, bbox.north, main_ds.transform)
        arr = main_ds.read(1, window=win, boundless=True, fill_value=0)
        # Resize to TILE_SIZE x TILE_SIZE via nearest-neighbor PIL
        if arr.shape != (TILE_SIZE, TILE_SIZE):
            from PIL import Image as PILImage
            wc_classes = np.array(
                PILImage.fromarray(arr).resize((TILE_SIZE, TILE_SIZE), PILImage.NEAREST),
                dtype=np.uint8,
            )
        else:
            wc_classes = arr.astype(np.uint8)
    except (ValueError, rasterio.errors.WindowError):
        return None

    # Apply forest mask
    wc_classes = np.where(forest_mask == 1, wc_classes, 0)
    # Color via LUT
    rgba = lut[wc_classes]
    if int((rgba[..., 3] > 0).sum()) == 0:
        return None
    return Image.fromarray(rgba, mode="RGBA")


def main() -> None:
    if not WC_TILE_DIR.exists():
        print(f"[FATAL] {WC_TILE_DIR} missing")
        sys.exit(1)
    if not BEATS_GEOJSON.exists():
        print(f"[FATAL] {BEATS_GEOJSON} missing")
        sys.exit(1)

    print(f"Loading {BEATS_GEOJSON.name}…")
    import geopandas as gpd
    beats_gdf = gpd.read_file(BEATS_GEOJSON)
    print(f"  {len(beats_gdf)} beat polygons loaded")

    lut = _build_color_lut()

    OUT_XYZ_ROOT.mkdir(parents=True, exist_ok=True)
    OUT_PMTILES.parent.mkdir(parents=True, exist_ok=True)

    # Enumerate tiles to bake — only those overlapping MP AOI
    tiles_to_bake: list[mercantile.Tile] = []
    for z in range(ZOOM_MIN, ZOOM_MAX + 1):
        z_tiles = list(mercantile.tiles(LON_MIN, LAT_MIN, LON_MAX, LAT_MAX, z))
        print(f"  z{z}: {len(z_tiles):,} candidate tiles")
        tiles_to_bake.extend(z_tiles)
    print(f"Total candidate tiles z{ZOOM_MIN}-z{ZOOM_MAX}: {len(tiles_to_bake):,}")

    # Open PMTiles writer
    pmtiles_fp = open(OUT_PMTILES, "wb")
    writer = Writer(pmtiles_fp)

    n_written = 0
    n_empty = 0
    t0 = time.time()
    for i, tile in enumerate(tiles_to_bake):
        if i % 500 == 0 and i > 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(tiles_to_bake) - i) / rate if rate > 0 else 0
            print(f"  {i:>6,}/{len(tiles_to_bake):,}  written:{n_written:,} empty:{n_empty:,}  rate:{rate:.0f}/s  eta:{int(eta)}s")
        img = _render_tile(tile, lut, beats_gdf)
        if img is None:
            n_empty += 1
            continue
        # Write XYZ
        out_dir = OUT_XYZ_ROOT / str(tile.z) / str(tile.x)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{tile.y}.png"
        img.save(out_path, optimize=True)
        # Write PMTiles entry
        with open(out_path, "rb") as f:
            png_bytes = f.read()
        tileid = zxy_to_tileid(tile.z, tile.x, tile.y)
        writer.write_tile(tileid, png_bytes)
        n_written += 1

    # Finalize PMTiles
    header = {
        "tile_type": TileType.PNG,
        "tile_compression": Compression.NONE,  # PNG already compressed
        "min_zoom": ZOOM_MIN,
        "max_zoom": ZOOM_MAX,
        "min_lon_e7": int(LON_MIN * 1e7),
        "min_lat_e7": int(LAT_MIN * 1e7),
        "max_lon_e7": int(LON_MAX * 1e7),
        "max_lat_e7": int(LAT_MAX * 1e7),
        "center_zoom": (ZOOM_MIN + ZOOM_MAX) // 2,
        "center_lon_e7": int(((LON_MIN + LON_MAX) / 2) * 1e7),
        "center_lat_e7": int(((LAT_MIN + LAT_MAX) / 2) * 1e7),
    }
    metadata = {
        "name": "MP WorldCover Fuel Class Pyramid",
        "description": "ESA WorldCover 10m tiles forest-clipped + colored by SB40 class",
        "attribution": "ESA WorldCover 2021 v200",
        "format": "png",
    }
    writer.finalize(header, metadata)
    pmtiles_fp.close()

    # Sidecar metadata for portal
    pmtiles_size = OUT_PMTILES.stat().st_size
    OUT_META.write_text(json.dumps({
        "min_zoom": ZOOM_MIN,
        "max_zoom": ZOOM_MAX,
        "lon_min": LON_MIN,
        "lat_min": LAT_MIN,
        "lon_max": LON_MAX,
        "lat_max": LAT_MAX,
        "tile_size": TILE_SIZE,
        "xyz_url_template": "/static/wc_tiles/{z}/{x}/{y}.png",
        "pmtiles_url": "/static/wc_fuel_class.pmtiles",
        "pmtiles_size_bytes": pmtiles_size,
        "n_tiles_written": n_written,
        "n_tiles_empty": n_empty,
        "fuel_class_colors": {
            "TL2_forest_litter":  "#1F6B3A",
            "SH2_shrub":          "#2A8C8C",
            "GR2_grassland":      "#EC4899",
            "GR1_cropland":       "#050505",
        },
        "source": "ESA WorldCover 10 m 2021 v200 + MP forest-beats mask",
        "generated_ts": int(time.time()),
    }, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    print()
    print(f"Wrote {n_written:,} tiles ({n_empty:,} empty/skipped) in {elapsed:.0f}s")
    print(f"  XYZ root:  {OUT_XYZ_ROOT}")
    print(f"  PMTiles:   {OUT_PMTILES} ({pmtiles_size / 1e6:.1f} MB)")
    print(f"  Meta:      {OUT_META.name}")


if __name__ == "__main__":
    main()
