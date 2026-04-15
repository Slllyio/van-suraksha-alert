"""Download MCD64 and FireCCI burnt-area exports from Drive to local.

Uses existing scripts/download_from_drive.py OAuth pattern but resolves the
Drive folder name → folder ID automatically so we don't have to hardcode IDs.

Usage:
  python scripts/download_burnt_area_exports.py                     # download all available
  python scripts/download_burnt_area_exports.py --product mcd64     # MCD64 only
  python scripts/download_burnt_area_exports.py --product firecci   # FireCCI only
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from download_from_drive import get_drive_service, download_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_lake" / "burnt_area"

FOLDER_NAMES = {
    "mcd64": "burnt_area_mcd64",
    "firecci": "burnt_area_firecci",
    "s2": "burnt_area_s2_dnbr",
}


def find_folder_id(service, folder_name: str) -> str | None:
    """Find Drive folder ID by name."""
    query = (
        f"mimeType='application/vnd.google-apps.folder' "
        f"and name='{folder_name}' and trashed=false"
    )
    res = service.files().list(q=query, fields="files(id, name)", pageSize=5).execute()
    items = res.get("files", [])
    if not items:
        return None
    return items[0]["id"]


def list_folder(service, folder_id: str) -> list[dict]:
    q = f"'{folder_id}' in parents and trashed=false"
    res = service.files().list(q=q, fields="files(id, name, size)", pageSize=200).execute()
    return res.get("files", [])


def download_folder(service, product: str) -> int:
    folder_name = FOLDER_NAMES[product]
    log.info("Looking up folder: %s", folder_name)
    folder_id = find_folder_id(service, folder_name)
    if folder_id is None:
        log.warning("Folder '%s' not yet created in Drive (no exports complete yet)", folder_name)
        return 0

    files = list_folder(service, folder_id)
    log.info("Found %d files in %s", len(files), folder_name)

    downloaded = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        name = f["name"]
        if not name.endswith(".tif"):
            continue
        out_path = OUT_DIR / name
        if out_path.exists():
            size_mb = out_path.stat().st_size / 1e6
            log.info("  EXISTS %s (%.1f MB) — skipping", name, size_mb)
            continue
        download_file(service, f["id"], out_path)
        downloaded += 1

    log.info("Downloaded %d new %s rasters → %s", downloaded, product, OUT_DIR.relative_to(ROOT))
    return downloaded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", choices=["mcd64", "firecci", "s2", "all", "both"], default="all")
    args = parser.parse_args()

    service = get_drive_service()

    total = 0
    if args.product in ("mcd64", "both", "all"):
        total += download_folder(service, "mcd64")
    if args.product in ("firecci", "both", "all"):
        total += download_folder(service, "firecci")
    if args.product in ("s2", "all"):
        total += download_folder(service, "s2")
    log.info("Total: %d rasters downloaded", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
