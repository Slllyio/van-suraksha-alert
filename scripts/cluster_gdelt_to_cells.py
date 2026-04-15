"""Stage V11.2 — Cluster GDELT MP fire events to v6e (cell_id, date).

Input: `data_lake/weak_labels/gdelt_mp_fire_events.parquet` from Stage V11.1
Output: `data_lake/weak_labels/gdelt_cell_events.parquet`
  Columns: cell_id, date, n_articles, n_event_codes_distinct,
           num_mentions_sum, avg_tone_mean, source_urls (semicolon-joined, capped)

Spatial matching: nearest v6e cell centroid via KDTree in km space.
Temporal: keep event at its SQLDATE (fire article date); optionally shift
by ±1-3 days to account for "article published 1-3 days after event"
— leave as published-date for now, fusion step handles tolerance.

Usage:
  python scripts/cluster_gdelt_to_cells.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
GDELT_IN = ROOT / "data_lake" / "weak_labels" / "gdelt_mp_fire_events.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_PATH = ROOT / "data_lake" / "weak_labels" / "gdelt_cell_events.parquet"

KM_PER_DEG_LAT = 110.6
MAX_URL_JOIN_PER_CELL = 5  # cap URL string to first 5 per cell/date


def main() -> int:
    if not GDELT_IN.exists():
        log.error("Missing GDELT events: %s. Run scripts/ingest_gdelt_events_mp.py first.", GDELT_IN)
        return 2

    log.info("Loading GDELT MP fire events...")
    gd = pd.read_parquet(GDELT_IN)
    gd["sqldate"] = pd.to_datetime(gd["sqldate"])
    log.info("  %d events", len(gd))

    log.info("Loading v6e cells + building KDTree...")
    cells = pd.read_csv(CELLS_PATH)
    cells_km = np.column_stack([
        cells["centroid_lon"].values * np.cos(np.radians(cells["centroid_lat"].values)) * KM_PER_DEG_LAT,
        cells["centroid_lat"].values * KM_PER_DEG_LAT,
    ])
    tree = cKDTree(cells_km)

    gd_km = np.column_stack([
        gd["action_lon"].values * np.cos(np.radians(gd["action_lat"].values)) * KM_PER_DEG_LAT,
        gd["action_lat"].values * KM_PER_DEG_LAT,
    ])
    _, cell_idx = tree.query(gd_km, k=1)
    gd["cell_id"] = cells["cell_id"].values[cell_idx]
    # Nearest-cell distance for diagnostic (QC sanity)
    gd["cell_distance_km"] = np.linalg.norm(gd_km - cells_km[cell_idx], axis=1)

    log.info("  Cell-match stats — distance_km: median=%.1f p90=%.1f max=%.1f",
             gd["cell_distance_km"].median(),
             gd["cell_distance_km"].quantile(0.9),
             gd["cell_distance_km"].max())

    # QC: drop matches farther than 5 km (outside cell footprint + tolerance)
    before = len(gd)
    gd = gd[gd["cell_distance_km"] <= 5.0].reset_index(drop=True)
    log.info("  Kept %d/%d events within 5 km of nearest cell", len(gd), before)

    log.info("Grouping to (cell_id, date)...")
    grouped = gd.groupby(["cell_id", "sqldate"]).agg(
        n_articles=("event_id", "count"),
        n_event_codes_distinct=("event_code", "nunique"),
        num_mentions_sum=("num_mentions", "sum"),
        avg_tone_mean=("avg_tone", "mean"),
        source_urls=("source_url", lambda s: ";".join(sorted(set(s))[:MAX_URL_JOIN_PER_CELL])),
    ).reset_index()
    grouped = grouped.rename(columns={"sqldate": "date"})

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_parquet(OUT_PATH, index=False)

    log.info("\n=== GDELT CELL×DATE EVENTS ===")
    log.info("Unique (cell, date) events: %d", len(grouped))
    log.info("Unique cells with any event: %d", grouped["cell_id"].nunique())
    log.info("Unique dates: %d", grouped["date"].nunique())
    log.info("Articles/(cell,date): median=%d p90=%d max=%d",
             int(grouped["n_articles"].median()),
             int(grouped["n_articles"].quantile(0.9)),
             int(grouped["n_articles"].max()))
    log.info("Events per year:\n%s",
             grouped.groupby(grouped["date"].dt.year).size().to_string())
    log.info("\nSaved: %s (%.1f MB)", OUT_PATH.relative_to(ROOT), OUT_PATH.stat().st_size / 1e6)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
