"""Dissolve the 8,973 MP forest beat polygons into 87 division polygons and
write a compact GeoJSON at ``data/aoi/mp_divisions_dissolved.geojson`` plus
a Shapely-simplified copy at ``.simplified.geojson`` for map rendering.

The resulting file is ~2-5 MB (vs. 179 MB for the beat-level original) and
is the default `/api/v2/division-boundaries` response — backed by the new
`_load_division_boundaries()` helper in `dashboard/v3/serve.py`.

Run once when the beat geojson changes. Re-running is idempotent.

    python scripts/build_division_boundaries.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEATS = ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"
OUT_DISSOLVED = ROOT / "data" / "aoi" / "mp_divisions_dissolved.geojson"
OUT_SIMPLIFIED = ROOT / "data" / "aoi" / "mp_divisions_simplified.geojson"


def main() -> int:
    # Windows cp1252 default codepage can't encode the characters in some of
    # our print() lines; force UTF-8 so the script runs under the default
    # `python scripts/build_division_boundaries.py` invocation.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    import geopandas as gpd  # heavyweight but already a project dep

    if not BEATS.exists():
        print(f"ERROR: {BEATS} missing", file=sys.stderr)
        return 2

    print(f"reading {BEATS.name} ({BEATS.stat().st_size // (1024*1024)} MB)...")
    gdf = gpd.read_file(BEATS)
    print(f"  loaded: {len(gdf):,} features, CRS={gdf.crs}")

    if "Division" not in gdf.columns:
        print("ERROR: expected `Division` column in beats geojson", file=sys.stderr)
        return 2

    print("dissolving by Division (8,973 → 87 MultiPolygons)...")
    dissolved = (
        gdf.dissolve(by="Division", aggfunc={"Range": "nunique", "Beat": "count"})
        .reset_index()
        .rename(columns={"Range": "n_ranges", "Beat": "n_beats"})
    )
    print(f"  dissolved: {len(dissolved)} divisions")

    OUT_DISSOLVED.parent.mkdir(parents=True, exist_ok=True)
    dissolved.to_file(OUT_DISSOLVED, driver="GeoJSON")
    print(
        f"wrote {OUT_DISSOLVED.name} "
        f"({OUT_DISSOLVED.stat().st_size // (1024*1024)} MB)"
    )

    # Simplify at 0.001° (~111 m) — keeps shape, good for zoom >= 8.
    print("simplifying (tolerance 0.001° ≈ 111 m)...")
    simplified = dissolved.copy()
    simplified["geometry"] = simplified.geometry.simplify(
        tolerance=0.001, preserve_topology=True
    )
    simplified.to_file(OUT_SIMPLIFIED, driver="GeoJSON")
    print(
        f"wrote {OUT_SIMPLIFIED.name} "
        f"({OUT_SIMPLIFIED.stat().st_size // 1024} KB)"
    )

    # Ultra-simplified (~1 km tolerance) for state-level overview at zoom 5-7.
    # This is the v4 default — ~2-4 MB on the wire.
    print("ultra-simplifying (tolerance 0.01° ≈ 1.1 km)...")
    ultra = dissolved.copy()
    ultra["geometry"] = ultra.geometry.simplify(
        tolerance=0.01, preserve_topology=True
    )
    ultra_path = ROOT / "data" / "aoi" / "mp_divisions_ultra.geojson"
    ultra.to_file(ultra_path, driver="GeoJSON")
    print(
        f"wrote {ultra_path.name} "
        f"({ultra_path.stat().st_size // 1024} KB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
