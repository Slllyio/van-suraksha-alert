#!/usr/bin/env python3
"""
Download Protomaps PMTiles basemap extract for offline use.

Downloads a regional PMTiles extract covering the Guna Division area
for offline map rendering in the JvalaNetra dashboard.

Usage:
    python scripts/download_basemap.py
    python scripts/download_basemap.py --bbox 76.45,23.80,77.85,24.95
"""

import argparse
import logging
import os
import struct
import sys
from pathlib import Path

import requests
from tqdm import tqdm

log = logging.getLogger(__name__)

# Guna Division bounding box (minlon, minlat, maxlon, maxlat)
GUNA_BBOX = (76.45, 23.80, 77.85, 24.95)

# Protomaps sources
PLANET_PMTILES_URL = "https://build.protomaps.com/20240610.pmtiles"
INDIA_EXTRACT_URL = "https://build.protomaps.com/20240610_india.pmtiles"
# Alternative: use pmtiles.io extract API
EXTRACT_API_URL = "https://app.protomaps.com/downloads/extract"

DEFAULT_OUTPUT = "data/tiles/pmtiles/india-guna.pmtiles"


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> bool:
    """Download a file with progress bar."""
    log.info("Downloading %s -> %s", url, dest)
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as pbar:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                pbar.update(len(chunk))

        log.info("Downloaded %.1f MB to %s", dest.stat().st_size / 1e6, dest)
        return True
    except Exception as e:
        log.error("Download failed: %s", e)
        if dest.exists():
            dest.unlink()
        return False


def try_pmtiles_extract(bbox: tuple, output: Path, max_zoom: int = 14) -> bool:
    """
    Try to extract a regional subset from the planet PMTiles file
    using HTTP range requests. This avoids downloading the full planet file.
    """
    try:
        from pmtiles.reader import Reader as PMTilesReader
        from pmtiles.writer import Writer as PMTilesWriter
    except ImportError:
        log.warning("pmtiles package not installed; skipping range extract")
        return False

    log.info("Attempting PMTiles range extract for bbox=%s, max_zoom=%d", bbox, max_zoom)
    minlon, minlat, maxlon, maxlat = bbox

    try:
        # Use pmtiles HTTP reader for range requests
        import io

        class HTTPSource:
            """HTTP range-request source for PMTiles reader."""

            def __init__(self, url: str):
                self.url = url
                self.session = requests.Session()
                # Get file size
                head = self.session.head(url, timeout=30)
                head.raise_for_status()
                self.length = int(head.headers.get("content-length", 0))

            def get(self, offset: int, length: int) -> bytes:
                headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
                resp = self.session.get(self.url, headers=headers, timeout=60)
                resp.raise_for_status()
                return resp.content

        source = HTTPSource(PLANET_PMTILES_URL)
        log.info("Planet PMTiles file size: %.1f GB", source.length / 1e9)

        # This approach works but is slow for large extracts.
        # For a small bbox like Guna, it should be manageable.
        reader = PMTilesReader(source)
        header = reader.header()

        output.parent.mkdir(parents=True, exist_ok=True)

        # Collect tiles within bbox
        tiles_written = 0
        with open(output, "wb") as f:
            writer = PMTilesWriter(f)
            for tile in reader.get_range(max_zoom):
                z, x, y = tile.z, tile.x, tile.y
                # Convert tile coords to lat/lon and check bbox
                n = 2 ** z
                lon1 = x / n * 360.0 - 180.0
                lat1 = 180.0 / 3.14159 * (2.0 * (3.14159 / 4.0 + 0.5 * (3.14159 * (1 - 2 * y / n))).atan() - 3.14159 / 2)
                lon2 = (x + 1) / n * 360.0 - 180.0

                # Simplified bbox check
                if lon2 < minlon or lon1 > maxlon:
                    continue
                writer.write_tile(z, x, y, tile.data)
                tiles_written += 1

            writer.finalize(header)

        log.info("Extracted %d tiles to %s", tiles_written, output)
        return tiles_written > 0

    except Exception as e:
        log.warning("PMTiles range extract failed: %s", e)
        if output.exists():
            output.unlink()
        return False


def try_india_extract(output: Path) -> bool:
    """Download the India regional extract from Protomaps."""
    log.info("Trying India regional extract...")
    return download_file(INDIA_EXTRACT_URL, output)


def try_protomaps_api_extract(bbox: tuple, output: Path) -> bool:
    """
    Use Protomaps extract API to get a small bbox extract.
    Falls back to direct download if API is unavailable.
    """
    minlon, minlat, maxlon, maxlat = bbox
    url = (
        f"https://app.protomaps.com/downloads/small_extract"
        f"?bbox={minlon},{minlat},{maxlon},{maxlat}"
    )
    log.info("Trying Protomaps extract API: %s", url)
    return download_file(url, output)


def main():
    parser = argparse.ArgumentParser(
        description="Download Protomaps PMTiles basemap for offline use"
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help="Output PMTiles file path (default: %(default)s)",
    )
    parser.add_argument(
        "--bbox",
        default=",".join(str(x) for x in GUNA_BBOX),
        help="Bounding box: minlon,minlat,maxlon,maxlat (default: Guna Division)",
    )
    parser.add_argument(
        "--max-zoom",
        type=int,
        default=14,
        help="Maximum zoom level to extract (default: 14)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if output file exists",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    output = Path(args.output)
    bbox = tuple(float(x) for x in args.bbox.split(","))

    if len(bbox) != 4:
        log.error("Invalid bbox: expected 4 values, got %d", len(bbox))
        sys.exit(1)

    if output.exists() and not args.force:
        log.info("Output already exists: %s (%.1f MB). Use --force to re-download.",
                 output, output.stat().st_size / 1e6)
        return

    output.parent.mkdir(parents=True, exist_ok=True)

    # Strategy 1: Try Protomaps extract API for small bbox
    if try_protomaps_api_extract(bbox, output):
        log.info("SUCCESS: Downloaded via Protomaps extract API")
        return

    # Strategy 2: Try HTTP range extract from planet PMTiles
    if try_pmtiles_extract(bbox, output, args.max_zoom):
        log.info("SUCCESS: Extracted from planet PMTiles via range requests")
        return

    # Strategy 3: Download full India extract
    if try_india_extract(output):
        log.info("SUCCESS: Downloaded India regional extract")
        return

    log.error(
        "All download strategies failed. Please download manually from "
        "https://protomaps.com/downloads and place the file at %s",
        output,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
