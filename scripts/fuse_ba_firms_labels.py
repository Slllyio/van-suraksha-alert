"""Stage 2 — Fuse BA clusters with FIRMS DBSCAN ignitions into tiered v17 labels.

Takes two inputs:
  - `data_lake/fire_detections/ba_clusters_mp.parquet` from Stage 1d (Andela flood-fill)
  - `data_lake/fire_detections/firms_dbscan_ignition.parquet` from existing pipeline

Applies user-locked design rules:
  3. Forest mask (Dynamic World `lc_frac_tree > 0.3`) AND season mask (Feb-May)
  2. Ignition date rule: FIRMS first-detection if predates MCD64 first-burn-day, else MCD64 day − 1

Produces tiered labels:
  - GOLD:   BA cluster ∩ FIRMS ignition (within 2 km + ±3 days)
  - SILVER: BA cluster WITHOUT FIRMS overlap, in forest + season
  - BRONZE: FIRMS ignition WITHOUT BA overlap
  - Rejected: BA cluster in non-forest OR out-of-season

Output: `data_lake/fire_detections/ignition_labels_tiered_v17.parquet`

Usage:
  python scripts/fuse_ba_firms_labels.py
  python scripts/fuse_ba_firms_labels.py --spatial-km 2 --temporal-days 3
"""
from __future__ import annotations

import argparse
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
BA_PATH = ROOT / "data_lake" / "fire_detections" / "ba_clusters_mp.parquet"
FIRMS_PATH = ROOT / "data_lake" / "fire_detections" / "firms_dbscan_ignition.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_PATH = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"

KM_PER_DEG_LAT = 110.6
# Season gate: February 1 through May 31
SEASON_START_MONTH = 2
SEASON_END_MONTH = 5
FOREST_MIN_TREE_FRAC = 0.3


def in_season(series: pd.Series) -> pd.Series:
    months = pd.to_datetime(series).dt.month
    return (months >= SEASON_START_MONTH) & (months <= SEASON_END_MONTH)


def assign_cell_id(df: pd.DataFrame, cells: pd.DataFrame, lat_col: str, lon_col: str) -> pd.Series:
    """For each row in df, assign the nearest v6e cell_id via KDTree in km."""
    cells_km = np.column_stack([
        cells["centroid_lon"].values * np.cos(np.radians(cells["centroid_lat"].values)) * KM_PER_DEG_LAT,
        cells["centroid_lat"].values * KM_PER_DEG_LAT,
    ])
    tree = cKDTree(cells_km)

    src_km = np.column_stack([
        df[lon_col].values * np.cos(np.radians(df[lat_col].values)) * KM_PER_DEG_LAT,
        df[lat_col].values * KM_PER_DEG_LAT,
    ])
    _, idx = tree.query(src_km, k=1)
    return cells["cell_id"].values[idx]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spatial-km", type=float, default=2.0,
                        help="Spatial tolerance for BA↔FIRMS match")
    parser.add_argument("--temporal-days", type=int, default=3,
                        help="Temporal tolerance for BA↔FIRMS match")
    args = parser.parse_args()

    if not BA_PATH.exists():
        log.error("Missing BA clusters: %s. Run scripts/andela_floodfill_mp.py first.", BA_PATH)
        return 2

    log.info("Loading BA clusters from %s...", BA_PATH.relative_to(ROOT))
    ba = pd.read_parquet(BA_PATH)
    ba["first_burn_date"] = pd.to_datetime(ba["first_burn_date"])
    log.info("  %d BA clusters (product mix: %s)",
             len(ba), dict(ba["product"].value_counts()))

    log.info("Loading FIRMS DBSCAN ignitions...")
    firms = pd.read_parquet(FIRMS_PATH)
    firms = firms[firms["is_ignition"] == 1].copy()
    firms["acq_date"] = pd.to_datetime(firms["acq_date"])
    log.info("  %d FIRMS DBSCAN ignitions", len(firms))

    log.info("Loading v6e cells (for forest mask + cell_id join)...")
    cells = pd.read_csv(CELLS_PATH)
    log.info("  %d cells", len(cells))

    # Step 1: Assign cell_id to each BA cluster + each FIRMS ignition
    log.info("Step 1 — Assigning v6e cell_id to BA + FIRMS points...")
    ba["cell_id"] = assign_cell_id(ba, cells, "centroid_lat", "centroid_lon")
    firms["cell_id"] = assign_cell_id(firms, cells, "latitude", "longitude")

    # Step 2: Attach forest fraction per cell
    cells_tree_frac = cells.set_index("cell_id")["lc_frac_tree"].to_dict()
    ba["cell_tree_frac"] = ba["cell_id"].map(cells_tree_frac)
    firms["cell_tree_frac"] = firms["cell_id"].map(cells_tree_frac)

    # Step 3: Season + forest masks for BA
    ba["in_forest"] = ba["cell_tree_frac"] >= FOREST_MIN_TREE_FRAC
    ba["in_season"] = in_season(ba["first_burn_date"])
    ba_keep = ba[ba["in_forest"] & ba["in_season"]].reset_index(drop=True)
    ba_reject = ba[~(ba["in_forest"] & ba["in_season"])].reset_index(drop=True)
    log.info("BA after forest + season masks: %d kept, %d rejected", len(ba_keep), len(ba_reject))

    # Step 4: Spatial+temporal cross-reference BA ↔ FIRMS via KDTree
    log.info("Step 4 — Cross-referencing BA clusters with FIRMS ignitions "
             "(tolerances: ±%.1f km, ±%d days)...", args.spatial_km, args.temporal_days)
    firms_km = np.column_stack([
        firms["longitude"].values * np.cos(np.radians(firms["latitude"].values)) * KM_PER_DEG_LAT,
        firms["latitude"].values * KM_PER_DEG_LAT,
    ])
    firms_tree = cKDTree(firms_km)

    ba_km = np.column_stack([
        ba_keep["centroid_lon"].values * np.cos(np.radians(ba_keep["centroid_lat"].values)) * KM_PER_DEG_LAT,
        ba_keep["centroid_lat"].values * KM_PER_DEG_LAT,
    ])
    # Neighbors within spatial tolerance
    nbrs = firms_tree.query_ball_point(ba_km, r=args.spatial_km)

    matched_firms_idx: set[int] = set()
    tiers: list[str] = []
    ignition_dates: list[pd.Timestamp] = []
    matched_firms_lats: list[float] = []
    matched_firms_lons: list[float] = []

    for i, (_, ba_row) in enumerate(ba_keep.iterrows()):
        ba_date = ba_row["first_burn_date"]
        candidate_indices = nbrs[i]
        best_firms_idx = None
        for fi in candidate_indices:
            fire_date = firms["acq_date"].iat[fi]
            dt_days = abs((fire_date - ba_date).total_seconds() / 86400.0)
            if dt_days <= args.temporal_days:
                best_firms_idx = fi
                break  # first in-window match

        if best_firms_idx is not None:
            matched_firms_idx.add(best_firms_idx)
            tiers.append("GOLD")
            firms_date = firms["acq_date"].iat[best_firms_idx]
            mcd64_minus1 = ba_date - pd.Timedelta(days=1)
            ign_date = firms_date if firms_date < mcd64_minus1 else mcd64_minus1
            ignition_dates.append(ign_date)
            matched_firms_lats.append(firms["latitude"].iat[best_firms_idx])
            matched_firms_lons.append(firms["longitude"].iat[best_firms_idx])
        else:
            tiers.append("SILVER")
            ignition_dates.append(ba_date - pd.Timedelta(days=1))
            matched_firms_lats.append(np.nan)
            matched_firms_lons.append(np.nan)

    ba_keep["tier"] = tiers
    ba_keep["ignition_date"] = ignition_dates
    ba_keep["ignition_lat"] = np.where(ba_keep["tier"] == "GOLD",
                                        matched_firms_lats, ba_keep["centroid_lat"])
    ba_keep["ignition_lon"] = np.where(ba_keep["tier"] == "GOLD",
                                        matched_firms_lons, ba_keep["centroid_lon"])
    ba_keep["matched_firms_idx"] = np.where(
        ba_keep["tier"] == "GOLD",
        [i if t == "GOLD" else -1 for i, t in zip(range(len(ba_keep)), tiers)],
        -1,
    )

    # Step 5: BRONZE tier — FIRMS ignitions that didn't match any BA cluster
    log.info("Step 5 — Identifying BRONZE tier (FIRMS without BA overlap)...")
    unmatched = ~firms.index.isin(list(matched_firms_idx))
    firms_bronze = firms[unmatched].copy()
    firms_bronze["tier"] = "BRONZE"
    firms_bronze["ignition_date"] = firms_bronze["acq_date"]
    firms_bronze["ignition_lat"] = firms_bronze["latitude"]
    firms_bronze["ignition_lon"] = firms_bronze["longitude"]
    firms_bronze["area_ha"] = np.nan
    firms_bronze["product"] = "firms_only"

    log.info("Step 6 — Assembling final tiered labels table...")
    gold_silver = ba_keep[[
        "tier", "ignition_date", "ignition_lat", "ignition_lon",
        "cell_id", "area_ha", "aspect_ratio", "duration_days", "product",
    ]].copy()
    bronze = firms_bronze[[
        "tier", "ignition_date", "ignition_lat", "ignition_lon",
        "cell_id", "area_ha", "product",
    ]].copy()
    bronze["aspect_ratio"] = np.nan
    bronze["duration_days"] = 0

    combined = pd.concat([gold_silver, bronze], ignore_index=True)
    combined["ignition_date"] = pd.to_datetime(combined["ignition_date"])
    combined["tier"] = combined["tier"].astype("category")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved %d tiered ignition labels → %s", len(combined), OUT_PATH.relative_to(ROOT))

    log.info("\n=== TIER BREAKDOWN ===")
    log.info("%s", combined["tier"].value_counts().to_string())
    log.info("\n=== PRODUCT BREAKDOWN ===")
    log.info("%s", combined.groupby(["tier", "product"]).size().unstack(fill_value=0).to_string())

    log.info("\n=== SANITY ===")
    log.info("Rejected BA (non-forest or out-of-season): %d", len(ba_reject))
    gold_silver_total = (combined["tier"].isin(["GOLD", "SILVER"])).sum()
    firms_total = len(firms)
    log.info("GOLD+SILVER: %d, FIRMS DBSCAN: %d, ratio: %.2fx", gold_silver_total, firms_total, gold_silver_total / max(firms_total, 1))

    log.info("\n=== YEAR DISTRIBUTION (GOLD+SILVER) ===")
    gs = combined[combined["tier"].isin(["GOLD", "SILVER"])]
    log.info("%s", gs.groupby([gs["ignition_date"].dt.year, "tier"]).size().unstack(fill_value=0).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
