"""Pivot A v2 — Track T2 — Dynamic World monthly LULC features.

SERVER-SIDE-FIRST design (per feedback_serverside_first.md):
  - All monthly aggregation, delta computation, and feature derivation
    happens INSIDE Google Earth Engine.
  - We export ONLY the final crisp feature table per (cell, year, month):
        dw_bare_mean, dw_bare_max, dw_crops_mean, dw_trees_mean,
        dw_bare_delta_4wk, dw_crops_to_bare_4wk, dw_trees_delta_4wk
  - One Drive export per YEAR (instead of per month) → 6-7 exports total
    instead of 76. Much less Drive churn, much smaller local footprint.

Why this attacks the cold-start gap:
  - Dynamic World's `bare` class is a TRAINED classifier — distinguishes
    bare ground from leaf-off forest (the phenology trap that killed our
    raw S2 dNBR experiments per memory feedback_s2_dnbr_phenology_trap.md).
  - Slash-and-burn precursor signal = surge in bare-ground probability
    BEFORE FIRMS detects the fire. The crops_to_bare delta isolates this
    from natural seasonal trees-to-bare leaf-drop.

Usage:
  python scripts/build_dynamic_world_features.py --test         # 2024 only, 100 cells, fast smoke
  python scripts/build_dynamic_world_features.py --year 2024    # all 42K cells, one year
  python scripts/build_dynamic_world_features.py --full         # 2020-current, all cells, 6-7 yearly exports
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
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"

GEE_PROJECT = "van-suraksha-alert"
DRIVE_FOLDER = "VanSurakshaExports"
FILENAME_PREFIX = "dw_features"

# MP bounding box from compute_fwi.py
MP_BBOX_COORDS = [74.0, 21.0, 83.0, 27.0]
DW_BANDS_KEEP = ["bare", "crops", "trees"]


def init_ee() -> None:
    ee.Initialize(project=GEE_PROJECT)
    log.info("GEE initialised (project=%s)", GEE_PROJECT)


def load_cell_centroids(limit: int | None = None) -> ee.FeatureCollection:
    cells = pd.read_csv(CELLS_PATH, usecols=["cell_id", "centroid_lat", "centroid_lon"])
    if limit is not None:
        cells = cells.head(limit)
    log.info("Loaded %d cell centroids", len(cells))
    feats = []
    for _, r in cells.iterrows():
        feats.append(ee.Feature(
            ee.Geometry.Point([float(r["centroid_lon"]), float(r["centroid_lat"])]),
            {"cell_id": str(r["cell_id"])},
        ))
    return ee.FeatureCollection(feats)


def monthly_mean_image(year: int, month: int, mp_bbox: ee.Geometry) -> ee.Image:
    """Mean of DW class probabilities over a calendar month, MP-bounded."""
    next_y = year + (1 if month == 12 else 0)
    next_m = 1 if month == 12 else month + 1
    start = ee.Date(f"{year:04d}-{month:02d}-01")
    end = ee.Date(f"{next_y:04d}-{next_m:02d}-01")
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
          .filterDate(start, end)
          .filterBounds(mp_bbox))
    return dw.select(DW_BANDS_KEEP).mean()


def monthly_bare_max_image(year: int, month: int, mp_bbox: ee.Geometry) -> ee.Image:
    """Max-pixel bare probability over the month — catches small clearings."""
    next_y = year + (1 if month == 12 else 0)
    next_m = 1 if month == 12 else month + 1
    start = ee.Date(f"{year:04d}-{month:02d}-01")
    end = ee.Date(f"{next_y:04d}-{next_m:02d}-01")
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
          .filterDate(start, end)
          .filterBounds(mp_bbox))
    return dw.select("bare").max()


def build_year_feature_table(year: int, cells_fc: ee.FeatureCollection,
                              mp_bbox: ee.Geometry) -> ee.FeatureCollection:
    """For one calendar year, build a (cell × month) feature table SERVER-SIDE.

    Final columns per row: cell_id, year, month, dw_bare_mean, dw_bare_max,
    dw_crops_mean, dw_trees_mean, dw_bare_delta_4wk, dw_crops_to_bare_4wk,
    dw_trees_delta_4wk.
    """
    tables = []
    # Pre-compute previous month (Dec of year-1) for the Jan delta seed
    seed_mean = monthly_mean_image(year - 1, 12, mp_bbox)

    for month in range(1, 13):
        cur_mean = monthly_mean_image(year, month, mp_bbox)
        cur_bare_max = monthly_bare_max_image(year, month, mp_bbox)
        prev_mean = (seed_mean if month == 1
                     else monthly_mean_image(year, month - 1, mp_bbox))

        # Server-side feature image
        bare_mean = cur_mean.select("bare").rename("dw_bare_mean")
        crops_mean = cur_mean.select("crops").rename("dw_crops_mean")
        trees_mean = cur_mean.select("trees").rename("dw_trees_mean")
        bare_max = cur_bare_max.rename("dw_bare_max")

        bare_delta = (cur_mean.select("bare")
                      .subtract(prev_mean.select("bare"))
                      .rename("dw_bare_delta_4wk"))
        crops_delta = (cur_mean.select("crops")
                       .subtract(prev_mean.select("crops"))
                       .rename("dw_crops_delta_tmp"))
        trees_delta = (cur_mean.select("trees")
                       .subtract(prev_mean.select("trees"))
                       .rename("dw_trees_delta_4wk"))
        # crops_to_bare = bare_delta − crops_delta (positive = transition crops→bare)
        crops_to_bare = (bare_delta.subtract(crops_delta).rename("dw_crops_to_bare_4wk"))

        feature_img = (bare_mean
                       .addBands(bare_max)
                       .addBands(crops_mean)
                       .addBands(trees_mean)
                       .addBands(bare_delta)
                       .addBands(trees_delta)
                       .addBands(crops_to_bare))

        sampled = feature_img.sampleRegions(
            collection=cells_fc,
            scale=10,
            tileScale=4,
            geometries=False,
        )
        # Add year+month as constant properties
        sampled = sampled.map(lambda f: f.set({"year": year, "month": month}))
        tables.append(sampled)

    # Server-side concatenate the 12 monthly tables into one yearly table
    return ee.FeatureCollection(tables).flatten()


def submit_year_export(year: int, cells_fc: ee.FeatureCollection,
                        mp_bbox: ee.Geometry) -> ee.batch.Task:
    table = build_year_feature_table(year, cells_fc, mp_bbox)
    name = f"{FILENAME_PREFIX}_{year:04d}"
    task = ee.batch.Export.table.toDrive(
        collection=table,
        description=name,
        folder=DRIVE_FOLDER,
        fileNamePrefix=name,
        fileFormat="CSV",
        selectors=["cell_id", "year", "month",
                   "dw_bare_mean", "dw_bare_max", "dw_crops_mean", "dw_trees_mean",
                   "dw_bare_delta_4wk", "dw_trees_delta_4wk", "dw_crops_to_bare_4wk"],
    )
    task.start()
    return task


def years_to_run(args) -> list[int]:
    if args.test:
        return [2024]
    if args.year is not None:
        return [args.year]
    if args.full:
        cur = pd.Timestamp.today()
        return list(range(2020, cur.year + 1))
    raise ValueError("Specify --test, --full, or --year YYYY")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true",
                    help="Smoke test: 2024 only, --cell-limit defaults to 100")
    ap.add_argument("--full", action="store_true",
                    help="2020 through current year (6-7 yearly exports)")
    ap.add_argument("--year", type=int, default=None,
                    help="Single year")
    ap.add_argument("--cell-limit", type=int, default=None,
                    help="Limit cells (for fast smoke test)")
    args = ap.parse_args()

    if args.test and args.cell_limit is None:
        args.cell_limit = 100

    init_ee()
    mp_bbox = ee.Geometry.Rectangle(MP_BBOX_COORDS)

    years = years_to_run(args)
    log.info("Planning %d yearly exports for years: %s", len(years), years)

    cells_fc = load_cell_centroids(limit=args.cell_limit)

    submitted = []
    for y in years:
        try:
            task = submit_year_export(y, cells_fc, mp_bbox)
            submitted.append({"year": y, "filename": f"{FILENAME_PREFIX}_{y:04d}",
                              "task_id": task.id})
            log.info("  submitted %d (task_id=%s)", y, task.id)
        except Exception as e:
            log.error("  FAILED to submit %d: %s", y, e)
        time.sleep(1.0)

    if submitted:
        out_path = ROOT / "tmp" / "dw_export_tasks.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(submitted).to_csv(out_path, index=False)
        log.info("Saved task list to %s", out_path.relative_to(ROOT))

    log.info("\nSubmitted %d/%d yearly exports. Monitor at:",
             len(submitted), len(years))
    log.info("  https://code.earthengine.google.com/tasks")
    log.info("Outputs land in Drive folder: %s as %s_YYYY.csv",
             DRIVE_FOLDER, FILENAME_PREFIX)
    log.info("Run scripts/download_dw_monthly_exports.py to fetch + concatenate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
