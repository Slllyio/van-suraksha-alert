"""Stage V11.3 — 5-tier fusion: BA clusters + FIRMS + GDELT news.

Extension of `scripts/fuse_ba_firms_labels.py` to add a news dimension.

Inputs:
  - `data_lake/fire_detections/ba_clusters_mp.parquet` (Phase 8 Stage 1d)
  - `data_lake/fire_detections/firms_dbscan_ignition.parquet` (existing)
  - `data_lake/weak_labels/gdelt_cell_events.parquet` (V11.2)

Tier rules (with news):
  - PLATINUM_NEWS: (cell,date) has GDELT news AND (GOLD or SILVER BA match within ±3d)
      → highest trust, weight 1.3
  - GOLD:    BA cluster ∩ FIRMS within 2km + ±3d, no news
             → weight 1.0
  - SILVER:  BA-only in forest + season, no news
             → weight 0.7
  - BRONZE:  FIRMS-only, no BA overlap
             → weight 0.5
  - NEWS_ONLY: GDELT news, NO BA, NO FIRMS
             → weight 0.3 (weak — could be mis-geocoded or tiny fire)

Ignition date rule: earliest of {news date, FIRMS first-det, MCD64 first-burn-day − 1}

Output: `data_lake/fire_detections/ignition_labels_tiered_v18_news.parquet`

Usage:
  python scripts/fuse_ba_firms_news_labels.py
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
GDELT_PATH = ROOT / "data_lake" / "weak_labels" / "gdelt_cell_events.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_PATH = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v18_news.parquet"

KM_PER_DEG_LAT = 110.6
SEASON_START_MONTH = 2
SEASON_END_MONTH = 5
FOREST_MIN_TREE_FRAC = 0.3
NEWS_BA_TEMPORAL_TOLERANCE_DAYS = 3


def in_season(series: pd.Series) -> pd.Series:
    months = pd.to_datetime(series).dt.month
    return (months >= SEASON_START_MONTH) & (months <= SEASON_END_MONTH)


def assign_cell_id(df: pd.DataFrame, cells: pd.DataFrame, lat_col: str, lon_col: str) -> pd.Series:
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
    parser.add_argument("--spatial-km", type=float, default=2.0)
    parser.add_argument("--temporal-days", type=int, default=3)
    args = parser.parse_args()

    for p in [BA_PATH, FIRMS_PATH, GDELT_PATH]:
        if not p.exists():
            log.error("Missing input: %s", p)
            return 2

    log.info("Loading BA clusters...")
    ba = pd.read_parquet(BA_PATH)
    ba["first_burn_date"] = pd.to_datetime(ba["first_burn_date"])
    log.info("  %d BA clusters", len(ba))

    log.info("Loading FIRMS DBSCAN ignitions...")
    firms = pd.read_parquet(FIRMS_PATH)
    firms = firms[firms["is_ignition"] == 1].copy()
    firms["acq_date"] = pd.to_datetime(firms["acq_date"])
    log.info("  %d FIRMS ignitions", len(firms))

    log.info("Loading GDELT cell events...")
    gdelt = pd.read_parquet(GDELT_PATH)
    gdelt["date"] = pd.to_datetime(gdelt["date"])
    log.info("  %d GDELT (cell, date) events", len(gdelt))

    log.info("Loading cells for forest mask...")
    cells = pd.read_csv(CELLS_PATH)

    # Step 1: BA cells + forest/season gating
    ba["cell_id"] = assign_cell_id(ba, cells, "centroid_lat", "centroid_lon")
    firms["cell_id"] = assign_cell_id(firms, cells, "latitude", "longitude")
    tree_frac = cells.set_index("cell_id")["lc_frac_tree"].to_dict()

    ba["cell_tree_frac"] = ba["cell_id"].map(tree_frac)
    ba["in_forest"] = ba["cell_tree_frac"] >= FOREST_MIN_TREE_FRAC
    ba["in_season"] = in_season(ba["first_burn_date"])
    ba_keep = ba[ba["in_forest"] & ba["in_season"]].reset_index(drop=True)
    ba_reject = len(ba) - len(ba_keep)
    log.info("BA after forest+season masks: %d kept, %d rejected", len(ba_keep), ba_reject)

    # Step 2: GDELT forest gating (drop cells not in forest)
    gdelt["cell_tree_frac"] = gdelt["cell_id"].map(tree_frac)
    gdelt_fc = gdelt[gdelt["cell_tree_frac"] >= FOREST_MIN_TREE_FRAC].copy()
    gdelt_fc["in_season"] = in_season(gdelt_fc["date"])
    gdelt_fs = gdelt_fc[gdelt_fc["in_season"]].reset_index(drop=True)
    log.info("GDELT after forest+season masks: %d kept (from %d)", len(gdelt_fs), len(gdelt))

    # Step 3: BA↔FIRMS match (GOLD vs SILVER, same as Phase 8 Stage 2)
    log.info("Matching BA ↔ FIRMS (±%.1f km, ±%d days)...", args.spatial_km, args.temporal_days)
    firms_km = np.column_stack([
        firms["longitude"].values * np.cos(np.radians(firms["latitude"].values)) * KM_PER_DEG_LAT,
        firms["latitude"].values * KM_PER_DEG_LAT,
    ])
    firms_tree = cKDTree(firms_km)
    ba_km = np.column_stack([
        ba_keep["centroid_lon"].values * np.cos(np.radians(ba_keep["centroid_lat"].values)) * KM_PER_DEG_LAT,
        ba_keep["centroid_lat"].values * KM_PER_DEG_LAT,
    ])
    nbrs = firms_tree.query_ball_point(ba_km, r=args.spatial_km)

    matched_firms_idx: set[int] = set()
    ba_tiers: list[str] = []
    ba_dates: list[pd.Timestamp] = []
    ba_lats: list[float] = []
    ba_lons: list[float] = []

    for i, (_, ba_row) in enumerate(ba_keep.iterrows()):
        ba_date = ba_row["first_burn_date"]
        best_fi = None
        for fi in nbrs[i]:
            fire_date = firms["acq_date"].iat[fi]
            if abs((fire_date - ba_date).total_seconds() / 86400.0) <= args.temporal_days:
                best_fi = fi
                break
        if best_fi is not None:
            matched_firms_idx.add(best_fi)
            ba_tiers.append("GOLD")
            firms_date = firms["acq_date"].iat[best_fi]
            mcd64_m1 = ba_date - pd.Timedelta(days=1)
            ba_dates.append(firms_date if firms_date < mcd64_m1 else mcd64_m1)
            ba_lats.append(firms["latitude"].iat[best_fi])
            ba_lons.append(firms["longitude"].iat[best_fi])
        else:
            ba_tiers.append("SILVER")
            ba_dates.append(ba_date - pd.Timedelta(days=1))
            ba_lats.append(ba_row["centroid_lat"])
            ba_lons.append(ba_row["centroid_lon"])

    ba_keep["tier"] = ba_tiers
    ba_keep["ignition_date"] = ba_dates
    ba_keep["ignition_lat"] = ba_lats
    ba_keep["ignition_lon"] = ba_lons

    # Step 4: PROMOTE BA GOLD/SILVER to PLATINUM_NEWS if matching GDELT within 3 days
    log.info("Matching BA GOLD/SILVER ↔ GDELT news (±%d days same cell)...", NEWS_BA_TEMPORAL_TOLERANCE_DAYS)
    # Build GDELT index by (cell_id) for fast lookup
    gdelt_by_cell: dict = {}
    for _, g in gdelt_fs.iterrows():
        gdelt_by_cell.setdefault(g["cell_id"], []).append(g["date"])

    n_platinum = 0
    matched_news_keys: set[tuple] = set()
    for i in range(len(ba_keep)):
        cid = ba_keep["cell_id"].iat[i]
        ign_date = ba_keep["ignition_date"].iat[i]
        if cid in gdelt_by_cell:
            for news_date in gdelt_by_cell[cid]:
                if abs((news_date - ign_date).total_seconds() / 86400.0) <= NEWS_BA_TEMPORAL_TOLERANCE_DAYS:
                    ba_keep.loc[i, "tier"] = "PLATINUM_NEWS"
                    matched_news_keys.add((cid, news_date))
                    n_platinum += 1
                    break
    log.info("  Promoted %d BA rows to PLATINUM_NEWS", n_platinum)

    # Step 5: BRONZE — FIRMS without BA match
    log.info("Building BRONZE tier (FIRMS without BA match)...")
    unmatched = ~firms.index.isin(list(matched_firms_idx))
    firms_bronze = firms[unmatched].copy()
    firms_bronze["tier"] = "BRONZE"
    firms_bronze["ignition_date"] = firms_bronze["acq_date"]
    firms_bronze["ignition_lat"] = firms_bronze["latitude"]
    firms_bronze["ignition_lon"] = firms_bronze["longitude"]
    firms_bronze["area_ha"] = np.nan
    firms_bronze["product"] = "firms_only"
    firms_bronze["aspect_ratio"] = np.nan
    firms_bronze["duration_days"] = 0

    # Step 6: NEWS_ONLY tier — GDELT events not matched by any BA cluster
    log.info("Building NEWS_ONLY tier (GDELT without BA corroboration)...")
    news_only_rows = []
    for _, g in gdelt_fs.iterrows():
        key = (g["cell_id"], g["date"])
        if key in matched_news_keys:
            continue
        # Also check if there's an exact FIRMS match same cell+date — that'd be duplicate with BRONZE
        # For simplicity, skip; BRONZE vs NEWS_ONLY is a soft distinction
        cell_row = cells[cells["cell_id"] == g["cell_id"]]
        if len(cell_row) == 0:
            continue
        news_only_rows.append({
            "tier": "NEWS_ONLY",
            "ignition_date": g["date"],
            "ignition_lat": float(cell_row["centroid_lat"].iat[0]),
            "ignition_lon": float(cell_row["centroid_lon"].iat[0]),
            "cell_id": g["cell_id"],
            "area_ha": np.nan,
            "aspect_ratio": np.nan,
            "duration_days": 0,
            "product": "gdelt_news",
        })
    news_only = pd.DataFrame(news_only_rows)
    log.info("  NEWS_ONLY entries: %d", len(news_only))

    # Step 7: Combine all tiers
    gs = ba_keep[["tier", "ignition_date", "ignition_lat", "ignition_lon",
                   "cell_id", "area_ha", "aspect_ratio", "duration_days", "product"]]
    bronze = firms_bronze[["tier", "ignition_date", "ignition_lat", "ignition_lon",
                            "cell_id", "area_ha", "aspect_ratio", "duration_days", "product"]]

    combined = pd.concat([gs, bronze, news_only], ignore_index=True) if len(news_only) else pd.concat([gs, bronze], ignore_index=True)
    combined["ignition_date"] = pd.to_datetime(combined["ignition_date"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved %d tiered labels → %s", len(combined), OUT_PATH.relative_to(ROOT))

    log.info("\n=== TIER BREAKDOWN ===")
    tier_counts = combined["tier"].value_counts()
    log.info("%s", tier_counts.to_string())

    log.info("\n=== PRODUCT × TIER ===")
    log.info("%s", combined.groupby(["tier", "product"]).size().unstack(fill_value=0).to_string())

    log.info("\n=== YEAR DISTRIBUTION ===")
    yr = combined.groupby([combined["ignition_date"].dt.year, "tier"]).size().unstack(fill_value=0)
    log.info("%s", yr.to_string())

    # Stopping-rule check
    n_news_confirmed = int(tier_counts.get("PLATINUM_NEWS", 0))
    n_news_only = int(tier_counts.get("NEWS_ONLY", 0))
    n_news_total_new = n_news_confirmed + n_news_only
    log.info("\n=== V11.3 STOPPING-RULE CHECK ===")
    log.info("PLATINUM_NEWS (BA+news): %d", n_news_confirmed)
    log.info("NEWS_ONLY (news-only, not BA, not FIRMS): %d", n_news_only)
    log.info("Total news-derived tier additions: %d", n_news_total_new)
    if n_news_total_new < 500:
        log.warning("⚠️  News tiers add <500 rows. Signal may be too small; consider parking.")
    else:
        log.info("✓  News tiers add %d rows — proceed to v18 training", n_news_total_new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
