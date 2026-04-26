"""
Shared offline forest-clip helper for build scripts.

Filters per-v17-cell records to those whose centroid falls inside an
MP forest beat polygon. Same source + semantics as the runtime
`_clip_fires_to_forest()` in `dashboard/v3/serve.py:429` (strict
`within` predicate + 333 m edge-tolerance via projected-CRS sjoin).

Used by every `scripts/build_*.py` that produces a layer JSON for
`outputs/dashboard_feed/`. Per the user design rule documented at
`~/.claude/projects/e--FIRE/memory/feedback_clip_to_forest.md`,
NO new spatial layer ships without going through this helper.

Usage:
    from _forest_clip_helper import filter_records_to_forest
    records_in_forest = filter_records_to_forest(all_records)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BEATS_GEOJSON = REPO_ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"
PROJECTED_CRS = "EPSG:32644"  # UTM zone 44N — meters; matches runtime path
EDGE_TOLERANCE_M = 333.0      # half-pixel of FIRMS VIIRS scan width

# Lazy-load the projected beats GeoDataFrame once per process.
_BEATS_PROJ = None


def _load_beats_projected():
    """Read + project beats once per process. Returns None if the
    geojson is missing (callers should treat as 'no clipping')."""
    global _BEATS_PROJ
    if _BEATS_PROJ is not None:
        return _BEATS_PROJ
    if not BEATS_GEOJSON.exists():
        print(f"[forest-clip] WARN: {BEATS_GEOJSON} missing — no clip applied")
        return None
    import geopandas as gpd  # heavy; lazy
    print(f"[forest-clip] loading {BEATS_GEOJSON.name} ({BEATS_GEOJSON.stat().st_size / 1e6:.1f} MB)…")
    beats = gpd.read_file(BEATS_GEOJSON)
    print(f"[forest-clip] {len(beats)} beat polygons; reprojecting to {PROJECTED_CRS}")
    _BEATS_PROJ = beats.to_crs(PROJECTED_CRS)
    return _BEATS_PROJ


def filter_records_to_forest(
    records: list[dict[str, Any]],
    lat_key: str = "lat",
    lon_key: str = "lon",
    edge_tolerance_m: float = EDGE_TOLERANCE_M,
) -> list[dict[str, Any]]:
    """Return the subset of `records` whose (lat, lon) centroids fall
    inside an MP forest beat polygon.

    Two-pass clip (mirrors `dashboard/v3/serve.py:_clip_fires_to_forest`):
      Pass 1 — strict `within` containment
      Pass 2 — `sjoin_nearest` with `max_distance=edge_tolerance_m`
                (~333 m) to catch cells whose centroid sits just
                outside the polygon due to shapefile simplification.

    Returns the records list (NOT a deep copy) — mutation-free filter.
    """
    if not records:
        return records
    beats = _load_beats_projected()
    if beats is None:
        return records

    import geopandas as gpd
    from shapely.geometry import Point

    n_in = len(records)
    print(f"[forest-clip] filtering {n_in:,} records…")

    pts = gpd.GeoDataFrame(
        {"_idx": range(n_in)},
        geometry=[Point(r[lon_key], r[lat_key]) for r in records],
        crs="EPSG:4326",
    ).to_crs(PROJECTED_CRS)
    beats_subset = beats[["geometry"]]

    # Pass 1: strict within
    inside = gpd.sjoin(pts, beats_subset, how="inner", predicate="within")
    keep_idx = set(inside["_idx"].tolist())

    # Pass 2: edge tolerance
    if edge_tolerance_m > 0:
        edge = gpd.sjoin_nearest(
            pts, beats_subset, how="inner",
            max_distance=edge_tolerance_m, distance_col="_dist",
        )
        keep_idx |= set(edge["_idx"].tolist())

    out = [records[i] for i in sorted(keep_idx)]
    print(f"[forest-clip] kept {len(out):,} / {n_in:,} ({100.0 * len(out) / n_in:.1f}%) inside forest beats")
    return out


if __name__ == "__main__":
    # Smoke test
    sample = [
        {"lat": 23.21, "lon": 77.49, "name": "Bhopal-area forest"},
        {"lat": 23.26, "lon": 77.41, "name": "Bhopal city center (urban)"},
        {"lat": 22.46, "lon": 79.68, "name": "Pench TR (forest)"},
        {"lat": 22.72, "lon": 75.86, "name": "Indore (urban)"},
    ]
    filtered = filter_records_to_forest(sample)
    print("\nForest-only:")
    for r in filtered:
        print(f"  {r['name']}: {r['lat']:.2f}, {r['lon']:.2f}")
