"""Pivot A v2 — Track T2 — Synchronous Dynamic World feature pull.

Workaround for GEE batch-queue saturation (project queue had 2,756 PENDING
tasks ahead of ours). Instead of submitting 37 batch exports and waiting
~17h, we pull DW monthly probabilities synchronously via getInfo() in
1000-cell chunks. Same server-side compute, just no batch queue.

Estimated wallclock: ~1-2 hours total (76 months × 43 chunks × ~1s/call).

Output: same as the batch path —
  data_lake/land_cover/dynamic_world_monthly.parquet

Schema: cell_id, year, month, dw_bare_mean, dw_bare_max, dw_crops_mean,
        dw_trees_mean, dw_grass_mean (deltas computed downstream).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ee
import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_PARQUET = ROOT / "data_lake" / "land_cover" / "dynamic_world_monthly.parquet"
TMP_DIR = ROOT / "tmp" / "dw_sync"

GEE_PROJECT = "van-suraksha-alert"
MP_BBOX_COORDS = [74.0, 21.0, 83.0, 27.0]
DW_BANDS = ["bare", "crops", "trees", "grass"]
CHUNK_SIZE = 1000  # cells per getInfo call (stays well under 10MB)


def init_ee() -> None:
    ee.Initialize(project=GEE_PROJECT)


def monthly_image(year: int, month: int, mp_bbox: ee.Geometry) -> ee.Image:
    next_y = year + (1 if month == 12 else 0)
    next_m = 1 if month == 12 else month + 1
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
          .filterDate(f"{year:04d}-{month:02d}-01", f"{next_y:04d}-{next_m:02d}-01")
          .filterBounds(mp_bbox))
    mean_img = dw.select(DW_BANDS).mean()
    bare_max = dw.select(["bare"]).max().rename("bare_max")
    return mean_img.addBands(bare_max)


def sample_chunk(img: ee.Image, chunk_pylist: list, year: int, month: int) -> list[dict]:
    """Sync sample one chunk via getInfo()."""
    fc = ee.FeatureCollection(chunk_pylist)
    sampled = img.sampleRegions(collection=fc, scale=10, tileScale=4, geometries=False)
    info = sampled.getInfo()
    rows = []
    for feat in info.get("features", []):
        props = feat.get("properties", {})
        rows.append({
            "cell_id": props.get("cell_id"),
            "year": year,
            "month": month,
            "dw_bare_mean": props.get("bare"),
            "dw_bare_max": props.get("bare_max"),
            "dw_crops_mean": props.get("crops"),
            "dw_trees_mean": props.get("trees"),
            "dw_grass_mean": props.get("grass"),
        })
    return rows


def chunk_list(lst: list, size: int) -> list[list]:
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def fetch_month(year: int, month: int, chunks: list[list], mp_bbox: ee.Geometry,
                month_idx: int, total_months: int) -> pd.DataFrame:
    img = monthly_image(year, month, mp_bbox)
    all_rows = []
    t0 = time.time()
    for i, ch in enumerate(chunks):
        attempts = 0
        while attempts < 3:
            try:
                rows = sample_chunk(img, ch, year, month)
                all_rows.extend(rows)
                break
            except Exception as e:
                attempts += 1
                wait = 2 ** attempts
                log.warning("  %d-%02d chunk %d retry %d after %s", year, month, i, attempts, str(e)[:60])
                time.sleep(wait)
        else:
            log.error("  %d-%02d chunk %d FAILED after 3 attempts", year, month, i)
    elapsed = time.time() - t0
    log.info("[%d/%d] %d-%02d  %d rows  %.1fs",
             month_idx + 1, total_months, year, month, len(all_rows), elapsed)
    return pd.DataFrame(all_rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2020)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--end-month", type=int, default=4, help="last month of end-year (inclusive)")
    ap.add_argument("--cell-limit", type=int, default=None, help="for smoke test")
    ap.add_argument("--max-workers", type=int, default=4, help="parallel monthly fetches")
    args = ap.parse_args()

    init_ee()
    mp_bbox = ee.Geometry.Rectangle(MP_BBOX_COORDS)

    log.info("Loading v6e cells...")
    cells = pd.read_csv(CELLS_PATH, usecols=["cell_id", "centroid_lat", "centroid_lon"])
    if args.cell_limit:
        cells = cells.head(args.cell_limit)
    log.info("  %d cells", len(cells))
    feats = [ee.Feature(ee.Geometry.Point([float(r.centroid_lon), float(r.centroid_lat)]),
                        {"cell_id": str(r.cell_id)})
             for _, r in cells.iterrows()]
    chunks = chunk_list(feats, CHUNK_SIZE)
    log.info("  %d chunks of %d cells each", len(chunks), CHUNK_SIZE)

    months = []
    for y in range(args.start_year, args.end_year + 1):
        m_end = 12 if y < args.end_year else args.end_month
        for m in range(1, m_end + 1):
            months.append((y, m))
    log.info("  %d months: %s..%s", len(months), months[0], months[-1])

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    all_dfs = []
    log.info("Fetching with %d parallel workers...", args.max_workers)
    with ThreadPoolExecutor(max_workers=args.max_workers) as exe:
        futures = {
            exe.submit(fetch_month, y, m, chunks, mp_bbox, idx, len(months)): (y, m, idx)
            for idx, (y, m) in enumerate(months)
        }
        for fut in as_completed(futures):
            y, m, idx = futures[fut]
            try:
                df_m = fut.result()
                if len(df_m):
                    df_m.to_csv(TMP_DIR / f"dw_{y:04d}_{m:02d}.csv", index=False)
                    all_dfs.append(df_m)
            except Exception as e:
                log.error("Month %d-%02d failed entirely: %s", y, m, e)

    log.info("Concatenating %d monthly frames...", len(all_dfs))
    raw = pd.concat(all_dfs, ignore_index=True)
    raw["date"] = pd.to_datetime(raw[["year", "month"]].assign(day=1))
    raw = raw.sort_values(["cell_id", "date"]).reset_index(drop=True)

    # Compute deltas per cell
    grp = raw.groupby("cell_id")
    for col in ("dw_bare_mean", "dw_crops_mean", "dw_trees_mean"):
        if col in raw.columns:
            raw[f"{col}_delta_4wk"] = grp[col].diff().fillna(0)
    if "dw_crops_mean_delta_4wk" in raw and "dw_bare_mean_delta_4wk" in raw:
        raw["dw_crops_to_bare_4wk"] = raw["dw_bare_mean_delta_4wk"] - raw["dw_crops_mean_delta_4wk"]

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(OUT_PARQUET, index=False)
    log.info("Wrote: %s (%d rows × %d cols)",
             OUT_PARQUET.relative_to(ROOT), len(raw), len(raw.columns))

    # Sanity print
    if "dw_bare_mean" in raw.columns:
        log.info("dw_bare_mean stats: median=%.4f p90=%.4f max=%.4f",
                 raw["dw_bare_mean"].median(),
                 raw["dw_bare_mean"].quantile(0.9),
                 raw["dw_bare_mean"].max())
    if "dw_crops_to_bare_4wk" in raw.columns:
        log.info("dw_crops_to_bare_4wk: median=%.4f p90=%.4f max=%.4f",
                 raw["dw_crops_to_bare_4wk"].median(),
                 raw["dw_crops_to_bare_4wk"].quantile(0.9),
                 raw["dw_crops_to_bare_4wk"].max())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
