"""PS-1 Phase 7 — MP-wide Sentinel-1 SAR amplitude features per (cell, date).

Scales the Guna pilot to all 42,542 v6e cells × val-window dates. Two-stage:
  1. Export per-target-date SAR feature stacks to Drive (one image per date)
  2. Local sampling at v6e cell centroids → parquet

Output: data_lake/sar/s1_features_per_cell_date.parquet

Run only AFTER pilot validates the signal. Quotas:
  - ~36 export tasks (val window: weekly cadence Feb-May 2025) × ~80MB each ≈ 3 GB
  - Each export: 5-15 min wall time on GEE
  - Total wall: ~2-4 hours from queue to download

Usage:
  python scripts/build_sar_features_mp.py --queue          # start exports
  python scripts/build_sar_features_mp.py --status          # check progress
  python scripts/build_sar_features_mp.py --sample <dir>    # sample local rasters
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import ee
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ee.Initialize(project="van-suraksha-alert")

ROOT = Path(__file__).resolve().parents[1]
CELLS_CSV = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_PATH = ROOT / "data_lake" / "sar" / "s1_features_per_cell_date.parquet"
DRIVE_FOLDER = "s1_sar_mp"

VAL_START = pd.Timestamp("2025-02-01")
VAL_END = pd.Timestamp("2025-05-29")
RECENT_DAYS = 12
REFERENCE_DAYS = 90
SCALE_M = 100  # downsample to 100m to keep export size manageable

MP_GEOM = (
    ee.FeatureCollection("FAO/GAUL/2015/level1")
    .filter(ee.Filter.eq("ADM1_NAME", "Madhya Pradesh"))
    .geometry()
)


def s1_collection(start: ee.Date, end: ee.Date) -> ee.ImageCollection:
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(MP_GEOM)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
        .select("VV")
    )


def build_sar_image(target_date: str) -> ee.Image:
    target = ee.Date(target_date)
    recent = s1_collection(target.advance(-RECENT_DAYS, "day"), target)
    reference = s1_collection(target.advance(-REFERENCE_DAYS, "day"), target.advance(-RECENT_DAYS, "day"))

    recent_mean = recent.mean().rename("vv_recent_mean")
    recent_std = recent.reduce(ee.Reducer.stdDev()).rename("vv_recent_std")
    ref_mean = reference.mean().rename("vv_ref_mean")
    ref_std = reference.reduce(ee.Reducer.stdDev()).rename("vv_ref_std")

    vv_anomaly_z = recent_mean.subtract(ref_mean).divide(ref_std.max(0.5)).rename("vv_anomaly_z")
    cv_recent = recent_std.divide(recent_mean.abs().max(0.5)).rename("cv_recent")
    cv_ref = ref_std.divide(ref_mean.abs().max(0.5)).rename("cv_ref")
    cv_drop = cv_recent.subtract(cv_ref).rename("vv_cv_drop")

    return (
        recent_mean
        .addBands(ref_mean)
        .addBands(vv_anomaly_z)
        .addBands(cv_drop)
        .toFloat()
    )


def target_dates() -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(VAL_START, VAL_END, freq="7D")]


def queue_exports() -> int:
    log.info("Queueing %d MP-wide SAR exports...", len(target_dates()))
    for date_str in target_dates():
        img = build_sar_image(date_str).clip(MP_GEOM)
        task = ee.batch.Export.image.toDrive(
            image=img,
            description=f"s1_sar_mp_{date_str}",
            folder=DRIVE_FOLDER,
            fileNamePrefix=f"s1_sar_mp_{date_str}",
            region=MP_GEOM,
            scale=SCALE_M,
            crs="EPSG:4326",
            maxPixels=int(2e10),
        )
        task.start()
        log.info("  %s queued (id=%s)", date_str, task.id[:12])
    return 0


def check_status() -> int:
    tasks = ee.batch.Task.list()[:60]
    by_state: dict[str, list[str]] = {}
    for t in tasks:
        s = t.status()
        if "s1_sar_mp" in s.get("description", ""):
            by_state.setdefault(s["state"], []).append(s["description"])
    for state, descs in by_state.items():
        log.info("[%s] %d tasks", state, len(descs))
        for d in descs[:5]:
            log.info("  - %s", d)
    return 0


def sample_rasters(rasters_dir: str) -> int:
    rdir = Path(rasters_dir)
    files = sorted(rdir.glob("s1_sar_mp_*.tif"))
    if not files:
        log.error("No s1_sar_mp_*.tif files found in %s", rasters_dir)
        return 1
    log.info("Found %d SAR rasters", len(files))

    cells = pd.read_csv(CELLS_CSV)
    log.info("  %d cells to sample", len(cells))

    rows = []
    for f in files:
        date_str = f.stem.replace("s1_sar_mp_", "")
        with rasterio.open(f) as src:
            transform = src.transform
            H, W = src.shape
            band_data = [src.read(i + 1) for i in range(src.count)]
            band_names = src.descriptions or ["vv_recent_mean", "vv_ref_mean", "vv_anomaly_z", "vv_cv_drop"]

            pix = [rowcol(transform, lon, lat) for lon, lat in zip(cells["centroid_lon"], cells["centroid_lat"])]
            pr = np.array([min(max(r, 0), H - 1) for r, c in pix])
            pc = np.array([min(max(c, 0), W - 1) for r, c in pix])
            for cid, r, c in zip(cells["cell_id"], pr, pc):
                row = {"cell_id": cid, "date": date_str}
                for name, arr in zip(band_names, band_data):
                    row[name] = float(arr[r, c]) if not np.isnan(arr[r, c]) else None
                rows.append(row)
        log.info("  sampled %s", f.name)

    df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved %d rows × %d cols → %s", len(df), len(df.columns), OUT_PATH.relative_to(ROOT))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--queue", action="store_true", help="Queue Drive exports")
    grp.add_argument("--status", action="store_true", help="Check task status")
    grp.add_argument("--sample", type=str, help="Sample local downloaded rasters dir")
    args = parser.parse_args()

    if args.queue:
        return queue_exports()
    if args.status:
        return check_status()
    return sample_rasters(args.sample)


if __name__ == "__main__":
    raise SystemExit(main())
