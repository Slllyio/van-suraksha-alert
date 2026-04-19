"""Download Dynamic World monthly CSVs from Drive once GEE tasks complete.

Companion to scripts/build_dynamic_world_features.py. Polls GEE task status
every 60s, downloads completed exports, and concatenates into a single parquet
under data_lake/land_cover/dynamic_world_monthly.parquet (with derived
delta features).

Auth: uses the same `van-suraksha-alert` GEE project + Google credentials
already in use by other GEE scripts.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import ee
import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
TASKS_CSV = ROOT / "tmp" / "dw_export_tasks.csv"
DOWNLOAD_DIR = ROOT / "tmp" / "dw_monthly"
OUT_PARQUET = ROOT / "data_lake" / "land_cover" / "dynamic_world_monthly.parquet"
DRIVE_FOLDER = "VanSurakshaExports"

GEE_PROJECT = "van-suraksha-alert"


def init_ee():
    ee.Initialize(project=GEE_PROJECT)


def poll_task_status(task_id: str) -> str:
    try:
        info = ee.data.getOperation("projects/earthengine-legacy/operations/" + task_id)
        return info.get("metadata", {}).get("state", "UNKNOWN")
    except Exception:
        # Fall back to legacy API
        try:
            tasks = ee.data.listOperations()
            for t in tasks:
                if t.get("name", "").endswith(task_id):
                    return t.get("metadata", {}).get("state", "UNKNOWN")
        except Exception:
            pass
        return "UNKNOWN"


def download_drive_csv(filename: str, dest: Path) -> bool:
    """Try to download via PyDrive2 if available; else instruct user to fetch manually."""
    try:
        from pydrive2.auth import GoogleAuth
        from pydrive2.drive import GoogleDrive

        gauth = GoogleAuth()
        gauth.LocalWebserverAuth()
        drive = GoogleDrive(gauth)
    except ImportError:
        log.warning(
            "PyDrive2 not installed. Manually download %s.csv from Drive folder %s "
            "to %s, then re-run this script with --skip-download.",
            filename, DRIVE_FOLDER, dest,
        )
        return False

    folder_query = f"title='{DRIVE_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    folders = drive.ListFile({"q": folder_query}).GetList()
    if not folders:
        log.error("Drive folder %s not found", DRIVE_FOLDER)
        return False
    folder_id = folders[0]["id"]

    file_query = f"'{folder_id}' in parents and title='{filename}.csv' and trashed=false"
    files = drive.ListFile({"q": file_query}).GetList()
    if not files:
        log.warning("File %s.csv not found in Drive folder %s", filename, DRIVE_FOLDER)
        return False
    files[0].GetContentFile(str(dest))
    return True


def build_parquet(download_dir: Path) -> int:
    csvs = sorted(download_dir.glob("dw_monthly_*.csv"))
    log.info("Concatenating %d monthly CSVs...", len(csvs))
    if not csvs:
        log.error("No monthly CSVs found at %s", download_dir)
        return 1

    frames = []
    for f in csvs:
        # Filename pattern: dw_monthly_YYYY_MM.csv
        parts = f.stem.split("_")
        year = int(parts[2])
        month = int(parts[3])
        df = pd.read_csv(f)
        df["year"] = year
        df["month"] = month
        df["date"] = pd.Timestamp(year, month, 1)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    log.info("Raw monthly frame: %d rows × %d cols", len(raw), len(raw.columns))

    # Compute per-cell deltas
    raw = raw.sort_values(["cell_id", "date"]).reset_index(drop=True)
    base_cols = [c for c in ("dw_bare_mean", "dw_crops_mean", "dw_trees_mean",
                             "dw_grass_mean", "dw_built_mean", "dw_bare_max")
                 if c in raw.columns]
    log.info("Available DW columns: %s", base_cols)

    # 4-week (1-month) delta per cell
    grp = raw.groupby("cell_id")
    for col in ("dw_bare_mean", "dw_crops_mean", "dw_trees_mean"):
        if col in raw.columns:
            raw[f"{col}_delta_4wk"] = grp[col].diff().fillna(0)

    # Combined slash-and-burn signal: crop loss + bare gain
    if "dw_crops_mean_delta_4wk" in raw and "dw_bare_mean_delta_4wk" in raw:
        # Strong positive = transition from crops to bare = slash-and-burn
        raw["dw_crops_to_bare_4wk"] = raw["dw_bare_mean_delta_4wk"] - raw["dw_crops_mean_delta_4wk"]

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(OUT_PARQUET, index=False)
    log.info("Wrote: %s (%d rows × %d cols)",
             OUT_PARQUET.relative_to(ROOT), len(raw), len(raw.columns))

    # Sanity print
    if "dw_bare_mean" in raw.columns:
        log.info("dw_bare_mean stats: min=%.4f median=%.4f max=%.4f",
                 raw["dw_bare_mean"].min(), raw["dw_bare_mean"].median(), raw["dw_bare_mean"].max())
    if "dw_crops_to_bare_4wk" in raw.columns:
        log.info("dw_crops_to_bare_4wk stats: min=%.4f p90=%.4f max=%.4f",
                 raw["dw_crops_to_bare_4wk"].min(),
                 raw["dw_crops_to_bare_4wk"].quantile(0.9),
                 raw["dw_crops_to_bare_4wk"].max())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true",
                    help="Skip Drive download, just rebuild parquet from CSVs in download_dir")
    ap.add_argument("--poll-interval", type=int, default=60,
                    help="Seconds between status polls")
    args = ap.parse_args()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if args.skip_download:
        log.info("Skipping download, building parquet from %s", DOWNLOAD_DIR)
        return build_parquet(DOWNLOAD_DIR)

    if not TASKS_CSV.exists():
        log.error("Task list not found: %s. Run build_dynamic_world_features.py first.", TASKS_CSV)
        return 1

    init_ee()
    tasks = pd.read_csv(TASKS_CSV)
    log.info("Polling %d tasks (interval=%ds)...", len(tasks), args.poll_interval)

    while True:
        states = {t: poll_task_status(t) for t in tasks["task_id"].astype(str)}
        complete = sum(1 for s in states.values() if s == "SUCCEEDED")
        failed = sum(1 for s in states.values() if s in ("FAILED", "CANCELLED"))
        running = len(states) - complete - failed
        log.info("  status: %d complete / %d running / %d failed",
                 complete, running, failed)
        if running == 0:
            break
        time.sleep(args.poll_interval)

    # Download
    for _, row in tasks.iterrows():
        local = DOWNLOAD_DIR / f"{row['filename']}.csv"
        if local.exists():
            log.info("  skip %s (already downloaded)", local.name)
            continue
        ok = download_drive_csv(row["filename"], local)
        if ok:
            log.info("  downloaded %s", local.name)

    return build_parquet(DOWNLOAD_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
