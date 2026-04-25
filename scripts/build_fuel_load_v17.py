"""
Bake per-v17-cell fuel-load JSON for the portal.

For each of the ~42k v17 grid cells over MP, computes:
  - fuel_load_t_per_ha    : weighted mean dry biomass density
  - sb40_dominant         : most-common Scott & Burgan 40 fuel-model name
  - canopy_frac           : fraction of cell pixels that are WorldCover trees
  - water_frac            : excluded fraction (water + built-up + bare)

Inputs (existing):
  - data_lake/land_cover/worldcover_expanded_3div.tif  (10 m, 11 classes)
  - src/analysis/spread_predictor.py _LC_FUEL_PARAMS    (kg/m² per WC class)
  - src/analysis/cell2fire/fuel_mapping.py SB40_CODE_TO_NAME

Output:
  outputs/dashboard_feed/fuel_load_v17.json
  ~42k records · ~3 MB on the wire (gzip ~400 KB)

Used by:
  - GET /api/v2/fuel-load (Pass B endpoint, mtime-cached)
  - dashboard/v4 sidebar toggle "Fuel load (t/ha)"

Grid (matches v17_ba_pu, fitted from existing alerts):
  lat = 0.018083 * row + 21.079143
  lon = 0.019724 * col + 74.039279
  cell ~ 2 km × 2 km

Tagged disclaimers: t/ha values are derived from WorldCover × _LC_FUEL_PARAMS
(kg/m² × 10). Reference loads are coarse approximations from Reddy et al.
(2019) for MP dry-deciduous; not field-validated per cell.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
# Use the 4 raw 3°×3° WorldCover tiles that together cover all of MP
# (lat 21-27°, lon 75-81°). The pre-merged `worldcover_expanded_3div.tif`
# is a smaller central crop and misses ~80% of MP cells.
WC_TILE_DIR = REPO_ROOT / "data_lake" / "land_cover" / "worldcover_expanded"
OUT_FULL = REPO_ROOT / "outputs" / "dashboard_feed" / "fuel_load_v17.json"

# v17 grid (empirically fitted, see docs/edge_bias_brutal_analysis.md)
LAT_STEP = 0.018083
LON_STEP = 0.019724
LAT_ORIGIN = 21.079143
LON_ORIGIN = 74.039279

# MP AOI bounds (matches AOI in CLAUDE.md)
MP_LAT_MIN, MP_LAT_MAX = 21.0, 27.0
MP_LON_MIN, MP_LON_MAX = 74.0, 83.0

# WorldCover → kg/m² fuel load (mirrors src/analysis/spread_predictor.py
# _LC_FUEL_PARAMS). Multiplied by 10 here to convert to t/ha for the
# portal display (officers expect t/ha not kg/m²).
WC_FUEL_T_HA: dict[int, float] = {
    10: 15.0,  # Tree cover
    20:  8.0,  # Shrubland
    30:  3.5,  # Grassland
    40: 12.0,  # Cropland
    50:  0.0,  # Built-up
    60:  1.0,  # Barren / sparse veg
    70:  0.0,  # Snow/ice
    80:  0.0,  # Water
    90:  3.0,  # Herbaceous wetland
    95:  5.0,  # Mangrove
    100: 0.0,  # Moss/lichen
}

# Mirrors src/analysis/cell2fire/fuel_mapping.py SB40 short-names. Used for
# the portal's "dominant fuel type" tooltip.
WC_TO_SB40_NAME: dict[int, str] = {
    10: "TL2",   # Low Load Broadleaf Litter
    20: "SH2",   # Moderate Load Dry Climate Shrub
    30: "GR2",   # Low Load Dry Climate Grass
    40: "GR1",   # Short Sparse Dry Climate Grass
    50: "NB1",   # Urban (non-burnable)
    60: "NB9",   # Bare ground
    70: "NB9",
    80: "NB8",   # Water (non-burnable)
    90: "GR1",
    95: "NB9",
    100: "NB9",
}

# Tree class for canopy_frac
WC_TREE = 10
# Non-burnable classes for water_frac
WC_NON_BURNABLE = {50, 60, 70, 80, 95, 100}


def _write_atomic_json(target: Path, payload: dict) -> None:
    """Atomic write — same pattern as scripts/build_historical_burn_priors.py."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def cell_bounds(row: int, col: int) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) for the v17 cell."""
    lat = LAT_ORIGIN + row * LAT_STEP
    lon = LON_ORIGIN + col * LON_STEP
    half_lat = LAT_STEP / 2
    half_lon = LON_STEP / 2
    return (lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat)


def _aggregate_cell(arr: np.ndarray) -> dict | None:
    """Reduce a WorldCover pixel window to one cell record. Returns None
    if the window has no valid pixels."""
    flat = arr.ravel()
    flat = flat[flat != 0]  # drop nodata
    if flat.size == 0:
        return None
    fuel_per_pixel = np.array(
        [WC_FUEL_T_HA.get(int(v), 0.0) for v in flat],
        dtype=np.float32,
    )
    cls_counts = Counter(int(v) for v in flat)
    dominant_wc = cls_counts.most_common(1)[0][0]
    return {
        "fuel_load": float(fuel_per_pixel.mean()),
        "sb40_dominant": WC_TO_SB40_NAME.get(dominant_wc, "NB9"),
        "canopy_frac": float((flat == WC_TREE).mean()),
        "water_frac": float(np.isin(flat, list(WC_NON_BURNABLE)).mean()),
    }


def main() -> None:
    tiles = sorted(WC_TILE_DIR.glob("ESA_WorldCover_10m_2021_v200_*_Map.tif"))
    if not tiles:
        print(f"[FATAL] No WorldCover tiles in {WC_TILE_DIR}")
        sys.exit(1)
    print(f"Found {len(tiles)} WorldCover tiles:")
    for t in tiles:
        print(f"  {t.name}")

    # cell_id → record (multiple tiles may overlap a cell; we accumulate
    # pixel windows and aggregate once at the end)
    cell_pixels: dict[tuple[int, int], list[np.ndarray]] = {}

    for tile in tiles:
        with rasterio.open(tile) as ds:
            wc_bounds = ds.bounds
            print(f"\n  {tile.name}  bounds {wc_bounds}")
            lat_min = max(MP_LAT_MIN, wc_bounds.bottom)
            lat_max = min(MP_LAT_MAX, wc_bounds.top)
            lon_min = max(MP_LON_MIN, wc_bounds.left)
            lon_max = min(MP_LON_MAX, wc_bounds.right)
            row_min = max(0, int((lat_min - LAT_ORIGIN) / LAT_STEP))
            row_max = int((lat_max - LAT_ORIGIN) / LAT_STEP) + 1
            col_min = max(0, int((lon_min - LON_ORIGIN) / LON_STEP))
            col_max = int((lon_max - LON_ORIGIN) / LON_STEP) + 1
            tile_cells = (row_max - row_min) * (col_max - col_min)
            print(f"    v17 cells in this tile: {tile_cells:,}")

            for row in range(row_min, row_max):
                if row % 50 == 0 and row > row_min:
                    print(f"    row {row}/{row_max}  (cells so far: {len(cell_pixels):,})")
                for col in range(col_min, col_max):
                    w, s, e, n = cell_bounds(row, col)
                    if e < wc_bounds.left or w > wc_bounds.right:
                        continue
                    if n < wc_bounds.bottom or s > wc_bounds.top:
                        continue
                    try:
                        win = from_bounds(w, s, e, n, ds.transform)
                        arr = ds.read(1, window=win, boundless=False, fill_value=0)
                    except (ValueError, rasterio.errors.WindowError):
                        continue
                    if arr.size == 0:
                        continue
                    cell_pixels.setdefault((row, col), []).append(arr)

    print(f"\nAggregating {len(cell_pixels):,} cells from accumulated pixel windows…")
    records = []
    for (row, col), arr_list in cell_pixels.items():
        # Concat all pixel windows for this cell (handles tile-boundary cells).
        try:
            combined = np.concatenate([a.ravel() for a in arr_list])
        except ValueError:
            continue
        agg = _aggregate_cell(combined.reshape(1, -1))
        if agg is None:
            continue
        lat_c = LAT_ORIGIN + row * LAT_STEP
        lon_c = LON_ORIGIN + col * LON_STEP
        records.append({
            "cell_id": f"r{row:04d}_c{col:04d}",
            "lat": round(lat_c, 6),
            "lon": round(lon_c, 6),
            "fuel_load_t_per_ha": round(agg["fuel_load"], 2),
            "sb40_dominant": agg["sb40_dominant"],
            "canopy_frac": round(agg["canopy_frac"], 3),
            "water_frac": round(agg["water_frac"], 3),
        })

    # Sort by fuel_load desc — heaviest cells first (useful for the portal's
    # "show top N heavy-fuel cells" pattern).
    records.sort(key=lambda r: r["fuel_load_t_per_ha"], reverse=True)

    payload = {
        "metadata": {
            "source_tiles": [str(t.relative_to(REPO_ROOT)) for t in tiles],
            "source_class_mapping": "_LC_FUEL_PARAMS in src/analysis/spread_predictor.py × 10",
            "sb40_reference": "src/analysis/cell2fire/fuel_mapping.py",
            "grid": {
                "lat_step": LAT_STEP,
                "lon_step": LON_STEP,
                "lat_origin": LAT_ORIGIN,
                "lon_origin": LON_ORIGIN,
                "cell_size_km": 2.0,
            },
            "n_records": len(records),
            "fuel_load_summary_t_per_ha": {
                "min":     round(min(r["fuel_load_t_per_ha"] for r in records), 2) if records else 0,
                "max":     round(max(r["fuel_load_t_per_ha"] for r in records), 2) if records else 0,
                "mean":    round(sum(r["fuel_load_t_per_ha"] for r in records) / max(1, len(records)), 2),
                "p50":     round(sorted(r["fuel_load_t_per_ha"] for r in records)[len(records)//2], 2) if records else 0,
            },
            "disclaimer": (
                "fuel_load_t_per_ha is derived from ESA WorldCover × Reddy et al "
                "(2019) reference loads. Coarse approximation; not field-validated "
                "per cell. Use for relative comparisons, not absolute biomass claims."
            ),
        },
        "records": records,
    }
    _write_atomic_json(OUT_FULL, payload)

    md = payload["metadata"]
    print()
    print(f"Wrote {OUT_FULL.name} ({OUT_FULL.stat().st_size / 1e6:.2f} MB) — {len(records):,} records")
    print(f"  fuel_load t/ha — min: {md['fuel_load_summary_t_per_ha']['min']} · "
          f"p50: {md['fuel_load_summary_t_per_ha']['p50']} · "
          f"mean: {md['fuel_load_summary_t_per_ha']['mean']} · "
          f"max: {md['fuel_load_summary_t_per_ha']['max']}")
    sb40_dist = Counter(r["sb40_dominant"] for r in records).most_common()
    print(f"  Dominant SB40 distribution: {dict(sb40_dist)}")


if __name__ == "__main__":
    main()
