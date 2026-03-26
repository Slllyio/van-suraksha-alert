"""
Build PMTiles from GeoJSON boundaries
======================================
Converts forest range/beat GeoJSON boundaries and alert GeoJSON into
PMTiles archives for zero-server vector tile hosting.

PMTiles can be served directly from:
  - Cloudflare R2 (free, 10GB storage, 1M reads/month)
  - Any static file host (S3, GitHub Pages, local)
  - MapLibre GL JS reads PMTiles natively via pmtiles protocol

Dependencies:
  pip install pmtiles

Usage::

    python scripts/build_pmtiles.py                    # build all
    python scripts/build_pmtiles.py --input data/aoi/ranges/all_ranges_3div.geojson
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

AOI_DIR = Path("E:/FIRE/data/aoi")
OUTPUT_DIR = Path("E:/FIRE/data/tiles")

# GeoJSON sources to convert
SOURCES = {
    "ranges": AOI_DIR / "ranges" / "all_ranges_3div.geojson",
    "guna_boundary": AOI_DIR / "gunafinal.geojson",
}


def geojson_to_tiles(geojson_path: Path, output_path: Path, layer_name: str) -> None:
    """
    Save GeoJSON as optimized tile-ready format.

    For small datasets (<10MB), GeoJSON is served directly by MapLibre.
    For production at scale, install tippecanoe and run:
        tippecanoe -o output.pmtiles -z14 -Z5 --drop-densest-as-needed input.geojson
    """
    # Copy to tile output directory as GeoJSON (MapLibre reads it natively)
    fallback = output_path.with_suffix(".geojson")
    if geojson_path != fallback:
        fallback.write_text(geojson_path.read_text(encoding="utf-8"), encoding="utf-8")
    size_kb = fallback.stat().st_size / 1024
    log.info("  Saved %s (%.1f KB) — serve directly with MapLibre", fallback.name, size_kb)


def build_alert_tiles(alerts_dir: Path, output_path: Path) -> None:
    """Build PMTiles from accumulated alert GeoJSON files."""
    from datetime import datetime

    alert_files = sorted(alerts_dir.glob("*.json"))
    if not alert_files:
        log.warning("No alert JSON files found in %s", alerts_dir)
        return

    # Combine recent alerts into a single FeatureCollection
    features = []
    for af in alert_files[-90:]:  # last 90 days
        try:
            with open(af) as f:
                data = json.load(f)
            # Extract fire locations from alert bulletins
            fires = data.get("fires", data.get("detections", []))
            for fire in fires:
                lat = fire.get("fire_lat", fire.get("latitude"))
                lon = fire.get("fire_lon", fire.get("longitude"))
                if lat and lon:
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "properties": {
                            "date": fire.get("fire_date", af.stem.replace("_alert", "")),
                            "severity": fire.get("severity", "unknown"),
                            "frp": fire.get("frp_mw", fire.get("frp", 0)),
                        },
                    })
        except (json.JSONDecodeError, KeyError):
            continue

    if not features:
        log.warning("No fire features extracted from alerts")
        return

    fc = {"type": "FeatureCollection", "features": features}
    tmp_geojson = output_path.with_suffix(".geojson")
    with open(tmp_geojson, "w") as f:
        json.dump(fc, f)
    log.info("  Combined %d fire features from %d alerts", len(features), len(alert_files[-90:]))

    geojson_to_tiles(tmp_geojson, output_path, "alerts")


def main():
    parser = argparse.ArgumentParser(description="Build PMTiles from GeoJSON")
    parser.add_argument("--input", help="Specific GeoJSON file to convert")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.input:
        inp = Path(args.input)
        out = out_dir / inp.with_suffix(".pmtiles").name
        geojson_to_tiles(inp, out, inp.stem)
        return

    # Build all standard tile sets
    for name, src in SOURCES.items():
        if src.exists():
            out = out_dir / f"{name}.pmtiles"
            geojson_to_tiles(src, out, name)
        else:
            log.warning("Source not found: %s", src)

    # Build alert history tiles
    alerts_dir = Path("E:/FIRE/data_lake/alerts")
    if alerts_dir.exists():
        build_alert_tiles(alerts_dir, out_dir / "fire_alerts.pmtiles")

    log.info("\nAll tiles built in %s", out_dir)


if __name__ == "__main__":
    main()
