"""
Bake the ESA WorldCover 10 m raster into a single MP-wide PNG with
SB40-class color encoding for the v4 portal `BitmapLayer`.

Output: dashboard/v3/static/fuel_class_mp.png
        dashboard/v3/static/fuel_class_mp.bounds.json   (lat/lon corners)

Why a single PNG (not PMTiles):
  - PMTiles raster pyramid needs `rio-pmtiles` or external `tippecanoe`
    + a server-side range-byte serve. Not installed.
  - One ~8192x8192 PNG covers the full MP AOI at ~80 m / pixel —
    ~80x finer than the v17 2 km grid, ~6x finer than the new 500 m
    CCI grid. Browser handles directly via deck.gl `BitmapLayer`.
  - Forest pixels colored by `colors.fuelClass` SB40 hues. Non-forest
    pixels transparent (alpha=0) so terrain underneath shows through.
  - File size estimate at 8192x8192 RGBA + PNG compression: 5-15 MB.

Resolution math:
  AOI 21.0-27.0N (6°) by 74.0-83.0E (9°)
  At 8192 px wide: 9° / 8192 = ~0.0011° ~ 122 m / px on lon
  At equivalent height (8192 * 6/9 = 5461 px): 6° / 5461 = ~0.0011° ~ 122 m / px on lat
  Finer than v17 2 km cells (16x linear, 256x area) and finer than
  500 m CCI hires grid (4x linear, 16x area).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.windows import from_bounds

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
WC_TILE_DIR = REPO_ROOT / "data_lake" / "land_cover" / "worldcover_expanded"
OUT_PNG = REPO_ROOT / "dashboard" / "v3" / "static" / "fuel_class_mp.png"
OUT_BOUNDS = REPO_ROOT / "dashboard" / "v3" / "static" / "fuel_class_mp.bounds.json"

# AOI
LAT_MIN, LAT_MAX = 21.0, 27.0
LON_MIN, LON_MAX = 74.0, 83.0
WIDTH = 8192
HEIGHT = int(WIDTH * (LAT_MAX - LAT_MIN) / (LON_MAX - LON_MIN))  # ~5461

# WorldCover class -> RGBA color matched to colors.fuelClass tokens.
# Alpha 0 for non-burnable / non-forest classes so terrain shows through.
WC_COLOR: dict[int, tuple[int, int, int, int]] = {
    # Burnable + tagged on portal
    10:  (31, 107, 58, 230),    # tree -> TL2 forest green
    20:  (42, 140, 140, 220),   # shrub -> SH2 teal
    30:  (236, 72, 152, 220),   # grassland -> GR2 pink
    40:  (5, 5, 5, 230),        # cropland -> GR1 black
    # Non-burnable — transparent so terrain underneath shows
    50:  (0, 0, 0, 0),          # built-up
    60:  (0, 0, 0, 0),          # bare
    70:  (0, 0, 0, 0),          # snow
    80:  (0, 0, 0, 0),          # water
    90:  (0, 0, 0, 0),          # wetland
    95:  (0, 0, 0, 0),          # mangrove
    100: (0, 0, 0, 0),          # moss
    0:   (0, 0, 0, 0),          # nodata
}

BEATS_GEOJSON = REPO_ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"


def _build_color_lookup() -> np.ndarray:
    """Return a 256x4 uint8 LUT mapping WC class -> RGBA."""
    lut = np.zeros((256, 4), dtype=np.uint8)
    for cls, rgba in WC_COLOR.items():
        lut[cls] = rgba
    return lut


def _build_forest_mask_raster(width: int, height: int) -> np.ndarray:
    """Rasterize MP forest beats to a (height, width) uint8 mask
    matching the output PNG's spatial extent. 1 = inside forest beat."""
    print(f"[mask] rasterizing {BEATS_GEOJSON.name}…")
    import geopandas as gpd
    from rasterio.features import rasterize
    beats = gpd.read_file(BEATS_GEOJSON)
    beats = beats.to_crs("EPSG:4326")
    # Build affine transform for the output PNG's grid
    transform = rasterio.transform.from_bounds(
        LON_MIN, LAT_MIN, LON_MAX, LAT_MAX, width, height,
    )
    shapes = ((geom, 1) for geom in beats.geometry if geom is not None)
    mask = rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )
    print(f"[mask] forest pixels: {int(mask.sum()):,} / {mask.size:,} ({100.0 * mask.sum() / mask.size:.1f}%)")
    return mask


def main() -> None:
    tiles = sorted(WC_TILE_DIR.glob("ESA_WorldCover_10m_2021_v200_*_Map.tif"))
    if not tiles:
        print(f"[FATAL] No WorldCover tiles in {WC_TILE_DIR}")
        sys.exit(1)
    print(f"Found {len(tiles)} WC tiles. Output: {WIDTH}x{HEIGHT} px, ~{(LON_MAX - LON_MIN) / WIDTH * 111000:.0f} m/px")

    # Allocate full-MP class array (uint8).
    wc_classes = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)

    # For each tile, read its window into the full-MP grid via rasterio's
    # boundless read on a target-aligned window.
    target_transform = rasterio.transform.from_bounds(
        LON_MIN, LAT_MIN, LON_MAX, LAT_MAX, WIDTH, HEIGHT,
    )
    target_x_step = (LON_MAX - LON_MIN) / WIDTH
    target_y_step = (LAT_MAX - LAT_MIN) / HEIGHT

    for tile_path in tiles:
        with rasterio.open(tile_path) as ds:
            b = ds.bounds
            # Compute target pixel range that covers this tile
            col_lo = max(0, int((b.left - LON_MIN) / target_x_step))
            col_hi = min(WIDTH, int((b.right - LON_MIN) / target_x_step) + 1)
            # Note: PNG rows are top-down (y decreases as row increases)
            row_lo = max(0, int((LAT_MAX - b.top) / target_y_step))
            row_hi = min(HEIGHT, int((LAT_MAX - b.bottom) / target_y_step) + 1)
            print(f"  {tile_path.name}: target rows [{row_lo}:{row_hi}], cols [{col_lo}:{col_hi}]")
            # For each target pixel in the tile's footprint, sample the
            # most-common WC class in the underlying source window.
            # Coarse but fast: nearest-neighbor at the target pixel center.
            # For 80 m target pixels over a 10 m source, we lose mode
            # precision but gain massive speed vs windowed sjoin.
            for ti, target_row in enumerate(range(row_lo, row_hi)):
                if ti % 200 == 0:
                    print(f"    target_row {target_row}/{row_hi}")
                target_lat = LAT_MAX - (target_row + 0.5) * target_y_step
                target_lons = LON_MIN + (np.arange(col_lo, col_hi) + 0.5) * target_x_step
                # Source pixel coords from target lat/lon
                src_col = ((target_lons - b.left) / ds.res[0]).astype(int)
                src_row = int((b.top - target_lat) / ds.res[1])
                if src_row < 0 or src_row >= ds.height:
                    continue
                # Mask src_col within source bounds
                in_bounds = (src_col >= 0) & (src_col < ds.width)
                if not in_bounds.any():
                    continue
                # Bulk-read the row
                row_arr = ds.read(1, window=((src_row, src_row + 1), (0, ds.width)))[0]
                # Assign nearest pixel
                wc_classes[target_row, col_lo:col_hi][in_bounds] = row_arr[src_col[in_bounds]]

    # Apply forest mask — only render pixels inside MP forest beats.
    print("[mask] building forest mask…")
    forest_mask = _build_forest_mask_raster(WIDTH, HEIGHT)
    wc_classes_masked = np.where(forest_mask == 1, wc_classes, 0)

    # Color via LUT
    print("[color] applying WC -> RGBA lookup…")
    lut = _build_color_lookup()
    rgba = lut[wc_classes_masked]
    print(f"[color] non-zero RGBA pixels: {int((rgba[..., 3] > 0).sum()):,}")

    # Save PNG
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    print(f"[png] writing {OUT_PNG}")
    Image.fromarray(rgba, mode="RGBA").save(OUT_PNG, optimize=True)
    sz_mb = OUT_PNG.stat().st_size / 1e6
    print(f"[png] saved {OUT_PNG} ({sz_mb:.2f} MB)")

    # Bounds sidecar — used by frontend BitmapLayer
    bounds_payload = {
        "lon_min": LON_MIN,
        "lat_min": LAT_MIN,
        "lon_max": LON_MAX,
        "lat_max": LAT_MAX,
        "width_px": WIDTH,
        "height_px": HEIGHT,
        "approx_m_per_px": int((LON_MAX - LON_MIN) / WIDTH * 111000),
        "fuel_class_colors": {
            "TL2_forest_litter":  "#1F6B3A",
            "SH2_shrub":          "#2A8C8C",
            "GR2_grassland":      "#EC4899",
            "GR1_cropland":       "#050505",
        },
        "source": "ESA WorldCover 10 m 2021 v200 + MP forest-beats mask",
    }
    with open(OUT_BOUNDS, "w", encoding="utf-8") as f:
        json.dump(bounds_payload, f, indent=2)
    print(f"[bounds] wrote {OUT_BOUNDS.name}")


if __name__ == "__main__":
    main()
