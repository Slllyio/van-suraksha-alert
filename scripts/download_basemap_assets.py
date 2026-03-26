#!/usr/bin/env python3
"""
Download basemap assets for offline PMTiles rendering.

Downloads:
  - Protomaps glyph PBF fonts for text labels
  - Protomaps sprites for map icons
  - pmtiles.js JavaScript library for browser-side PMTiles loading

Usage:
    python scripts/download_basemap_assets.py
"""

import argparse
import logging
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import requests
from tqdm import tqdm

log = logging.getLogger(__name__)

# Asset URLs
PMTILES_JS_CDN = "https://unpkg.com/pmtiles@3.2.0/dist/pmtiles.js"
PROTOMAPS_FONTS_URL = "https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.zip"
PROTOMAPS_SPRITES_URL = "https://protomaps.github.io/basemaps-assets/sprites"

# Sprite files to download
SPRITE_FILES = [
    "light.json", "light.png", "light@2x.json", "light@2x.png",
    "dark.json", "dark.png", "dark@2x.json", "dark@2x.png",
]

# Font stacks commonly used by Protomaps styles
FONT_STACKS = [
    "Noto Sans Regular",
    "Noto Sans Medium",
    "Noto Sans Bold",
    "Noto Sans Italic",
]

DEFAULT_ASSETS_DIR = "data/tiles/basemap-assets"
DEFAULT_STATIC_DIR = "dashboard/static"


def download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Download a single file with progress bar."""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True,
            desc=desc or dest.name, leave=False,
        ) as pbar:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
                pbar.update(len(chunk))
        return True
    except Exception as e:
        log.error("Failed to download %s: %s", url, e)
        return False


def download_pmtiles_js(static_dir: Path) -> bool:
    """Download pmtiles.js for browser-side PMTiles loading."""
    dest = static_dir / "pmtiles.js"
    if dest.exists():
        log.info("pmtiles.js already exists at %s", dest)
        return True
    log.info("Downloading pmtiles.js...")
    return download_file(PMTILES_JS_CDN, dest, "pmtiles.js")


def download_sprites(assets_dir: Path) -> int:
    """Download Protomaps sprite sheets."""
    sprites_dir = assets_dir / "sprites"
    sprites_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    for fname in SPRITE_FILES:
        dest = sprites_dir / fname
        if dest.exists():
            log.debug("Sprite %s already exists", fname)
            downloaded += 1
            continue
        url = f"{PROTOMAPS_SPRITES_URL}/{fname}"
        if download_file(url, dest, fname):
            downloaded += 1

    log.info("Downloaded %d/%d sprite files", downloaded, len(SPRITE_FILES))
    return downloaded


def download_fonts(assets_dir: Path) -> int:
    """
    Download Protomaps font glyphs (PBF files).

    Font glyphs are organized as: fonts/{stack_name}/{range}.pbf
    where range is like 0-255, 256-511, etc.
    """
    fonts_dir = assets_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    total_downloaded = 0
    # PBF glyph ranges (0-65535 in blocks of 256)
    ranges = [f"{i*256}-{i*256+255}" for i in range(256)]

    for stack in FONT_STACKS:
        stack_dir = fonts_dir / stack
        stack_dir.mkdir(parents=True, exist_ok=True)

        # Download only commonly used ranges (0-8191 covers Latin + Devanagari)
        important_ranges = ranges[:32]  # 0-8191

        for r in tqdm(important_ranges, desc=f"Fonts: {stack}", leave=False):
            dest = stack_dir / f"{r}.pbf"
            if dest.exists():
                total_downloaded += 1
                continue

            # Try protomaps CDN font endpoint
            url = f"https://protomaps.github.io/basemaps-assets/fonts/{stack}/{r}.pbf"
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    dest.write_bytes(resp.content)
                    total_downloaded += 1
                else:
                    # Not all ranges have glyphs; this is normal
                    pass
            except Exception:
                pass

    log.info("Downloaded %d font PBF files across %d stacks", total_downloaded, len(FONT_STACKS))
    return total_downloaded


def main():
    parser = argparse.ArgumentParser(
        description="Download basemap assets for offline PMTiles rendering"
    )
    parser.add_argument(
        "--assets-dir",
        default=DEFAULT_ASSETS_DIR,
        help="Output directory for fonts and sprites (default: %(default)s)",
    )
    parser.add_argument(
        "--static-dir",
        default=DEFAULT_STATIC_DIR,
        help="Dashboard static directory for pmtiles.js (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-fonts",
        action="store_true",
        help="Skip font download (large, slow)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    assets_dir = Path(args.assets_dir)
    static_dir = Path(args.static_dir)

    ok = True

    # 1. Download pmtiles.js
    if not download_pmtiles_js(static_dir):
        ok = False

    # 2. Download sprites
    if download_sprites(assets_dir) == 0:
        ok = False

    # 3. Download fonts (optional, slow)
    if not args.skip_fonts:
        download_fonts(assets_dir)
    else:
        log.info("Skipping font download (--skip-fonts)")

    if ok:
        log.info("All basemap assets downloaded successfully")
        log.info("  Assets: %s", assets_dir)
        log.info("  Static: %s", static_dir)
    else:
        log.warning("Some assets failed to download — maps may lack labels/icons")
        sys.exit(1)


if __name__ == "__main__":
    main()
