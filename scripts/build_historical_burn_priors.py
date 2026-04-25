"""
Build per-cell historical burn priors for v17 grid.

Used by:
  - Mitigation 2 (Coverage diagnostic) — overlay past-5-year burnt density
    + show interior blind-spots (cells that historically burned but have
    no current v17 alert).
  - Mitigation 3 (Interior monitor override) — sidebar toggle that
    promotes any cell with `n_seasons_burned >= 3` to WATCH.

Output: outputs/dashboard_feed/historical_burn_priors.json

Each record:
    {
      "cell_id": "r0118_c0175",
      "lat": 23.213,
      "lon": 77.491,
      "total_fires_5y": 47,
      "n_seasons_burned": 4,
      "seasons_burned": [2021, 2023, 2024, 2025]
    }

Grid (matches v17_ba_pu, derived empirically by fitting cell_id vs lat/lon
over 1,570 banded alerts on 2026-04-24):
    lat = 0.018083 * row + 21.079143
    lon = 0.019724 * col + 74.039279
    cell size: ~2 km
"""

from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
VIIRS_DIR = REPO_ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs"
OUTPUT_FULL = REPO_ROOT / "outputs" / "dashboard_feed" / "historical_burn_priors.json"
# Slim variant for the client — only cells with 3+ seasons burned
# (Mitigation 3 promotion candidates). ~27k records × ~80 B = ~2 MB.
OUTPUT_SLIM = REPO_ROOT / "outputs" / "dashboard_feed" / "historical_burn_priors_3plus.json"
# Density grid for HeatmapLayer — every cell with >=2 fires, only
# {lat, lon, w} per record. ~50k records × ~40 B = ~2 MB.
OUTPUT_DENSITY = REPO_ROOT / "outputs" / "dashboard_feed" / "historical_burn_density.json"

# v17 grid (empirically fitted)
LAT_STEP = 0.018083
LON_STEP = 0.019724
LAT_ORIGIN = 21.079143
LON_ORIGIN = 74.039279

# Fire-season months (Feb-May per CLAUDE.md "Fire Season")
FIRE_MONTHS = {2, 3, 4, 5}

# 5 most recent complete fire seasons
SEASONS = [2021, 2022, 2023, 2024, 2025]


def cell_id_for(lat: float, lon: float) -> tuple[str, int, int]:
    """Snap (lat, lon) to nearest v17 grid cell."""
    row = round((lat - LAT_ORIGIN) / LAT_STEP)
    col = round((lon - LON_ORIGIN) / LON_STEP)
    return f"r{row:04d}_c{col:04d}", row, col


def cell_center(row: int, col: int) -> tuple[float, float]:
    return LAT_ORIGIN + row * LAT_STEP, LON_ORIGIN + col * LON_STEP


def load_season(year: int) -> pd.DataFrame:
    """Load all VIIRS detections for a fire season (Feb-May of given year)."""
    pattern = str(VIIRS_DIR / str(year) / "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"  [WARN] no VIIRS files for {year} (looked in {pattern})")
        return pd.DataFrame()
    dfs = [pd.read_parquet(f) for f in files]
    df = pd.concat(dfs, ignore_index=True)
    if "acq_date" in df.columns:
        df["acq_date"] = pd.to_datetime(df["acq_date"], errors="coerce")
        df = df[df["acq_date"].dt.month.isin(FIRE_MONTHS)]
    return df


def main() -> None:
    print(f"Building historical burn priors for {len(SEASONS)} seasons: {SEASONS}")
    print(f"Reading from: {VIIRS_DIR}")

    # cell_id -> {seasons: set, total: int}
    aggregated: dict[str, dict] = defaultdict(
        lambda: {"seasons": set(), "total": 0, "row": 0, "col": 0}
    )

    for season in SEASONS:
        df = load_season(season)
        if df.empty:
            continue
        print(f"  {season}: {len(df):>7,} fire-season VIIRS detections")
        for lat, lon in zip(df["latitude"].to_numpy(), df["longitude"].to_numpy()):
            cell_id, row, col = cell_id_for(float(lat), float(lon))
            entry = aggregated[cell_id]
            entry["seasons"].add(season)
            entry["total"] += 1
            entry["row"] = row
            entry["col"] = col

    # Materialize records
    records = []
    for cell_id, entry in aggregated.items():
        lat, lon = cell_center(entry["row"], entry["col"])
        # Skip cells outside MP bbox (FIRMS sometimes catches strays)
        if not (21.0 <= lat <= 27.0 and 74.0 <= lon <= 83.0):
            continue
        seasons_sorted = sorted(entry["seasons"])
        records.append(
            {
                "cell_id": cell_id,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "total_fires_5y": int(entry["total"]),
                "n_seasons_burned": len(seasons_sorted),
                "seasons_burned": seasons_sorted,
            }
        )

    # Sort by total_fires desc
    records.sort(key=lambda r: r["total_fires_5y"], reverse=True)

    payload = {
        "metadata": {
            "seasons": SEASONS,
            "fire_months": sorted(FIRE_MONTHS),
            "grid": {
                "lat_step": LAT_STEP,
                "lon_step": LON_STEP,
                "lat_origin": LAT_ORIGIN,
                "lon_origin": LON_ORIGIN,
                "cell_size_km": 2.0,
            },
            "n_cells_total": len(records),
            "n_cells_3plus_seasons": sum(1 for r in records if r["n_seasons_burned"] >= 3),
            "n_cells_5_seasons": sum(1 for r in records if r["n_seasons_burned"] == 5),
        },
        "records": records,
    }

    OUTPUT_FULL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FULL, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))

    # Slim variant — only cells with 3+ seasons burned (Mitigation 3
    # promotion candidates). Wire-friendly subset for the override toggle.
    slim_records = [r for r in records if r["n_seasons_burned"] >= 3]
    slim_payload = {
        "metadata": {
            **payload["metadata"],
            "filter": "n_seasons_burned >= 3",
            "n_records": len(slim_records),
        },
        "records": slim_records,
    }
    with open(OUTPUT_SLIM, "w", encoding="utf-8") as f:
        json.dump(slim_payload, f, separators=(",", ":"))

    # Density variant for HeatmapLayer — only [lat, lon, weight] per
    # cell with ≥2 fires. Drops single-detection noise.
    density_points = [
        {"lat": r["lat"], "lon": r["lon"], "w": r["total_fires_5y"]}
        for r in records
        if r["total_fires_5y"] >= 2
    ]
    density_payload = {
        "metadata": {
            "seasons": SEASONS,
            "filter": "total_fires_5y >= 2",
            "n_points": len(density_points),
        },
        "points": density_points,
    }
    with open(OUTPUT_DENSITY, "w", encoding="utf-8") as f:
        json.dump(density_payload, f, separators=(",", ":"))

    md = payload["metadata"]
    print()
    print(f"Wrote {OUTPUT_FULL.name} ({OUTPUT_FULL.stat().st_size / 1e6:.2f} MB)")
    print(f"Wrote {OUTPUT_SLIM.name} ({OUTPUT_SLIM.stat().st_size / 1e6:.2f} MB) — {len(slim_records):,} records")
    print(f"Wrote {OUTPUT_DENSITY.name} ({OUTPUT_DENSITY.stat().st_size / 1e6:.2f} MB) — {len(density_points):,} points")
    print(f"  cells with at least 1 burn:  {md['n_cells_total']:>6,}")
    print(f"  cells with 3+ seasons burned: {md['n_cells_3plus_seasons']:>6,}")
    print(f"  cells with all 5 seasons:    {md['n_cells_5_seasons']:>6,}")


if __name__ == "__main__":
    main()
