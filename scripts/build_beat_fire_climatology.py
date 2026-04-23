"""Build per-beat × per-week-of-year FIRMS fire climatology.

Output: data_lake/fire_weather/beat_fire_climatology.parquet
Schema:
  Division, Range, Beat, week_of_year, n_years_with_fire, total_fires,
  mean_fires_per_year, max_fires_one_year, max_frp_seen, percentile_in_week

Purpose: feed `apply_climatology_watch_floor` in build_operational_alerts.py
so beats that historically burn at this week-of-year get an auto-WATCH band
even if the model's Hawkes-7d signal is silent.

Method:
  1. Load 5 years of forest-clipped FIRMS (2021-2025) high-confidence only.
  2. Spatial-join to mp_beats_wgs84 polygons (strict-within + 330 m edge).
  3. Tag each detection with ISO week-of-year of its acq_date.
  4. Group by (Beat, week_of_year) and aggregate.
  5. For each week-of-year, rank beats by total_fires → percentile.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FIRMS_CONS = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
BEATS_GEOJSON = ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"
OUT_PATH = ROOT / "data_lake" / "fire_weather" / "beat_fire_climatology.parquet"

HIGH_CONF = {"h", "n", "high", "nominal"}
HISTORY_YEARS = (2021, 2022, 2023, 2024, 2025)


def main() -> int:
    if not FIRMS_CONS.exists():
        log.error("FIRMS consolidated parquet missing: %s", FIRMS_CONS)
        return 1
    if not BEATS_GEOJSON.exists():
        log.error("Beats geojson missing: %s", BEATS_GEOJSON)
        return 1

    import geopandas as gpd
    from shapely.geometry import Point

    log.info("Loading FIRMS history...")
    df = pd.read_parquet(FIRMS_CONS)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    df["confidence"] = df["confidence"].astype(str).str.lower()
    df = df[df["confidence"].isin(HIGH_CONF)]
    df = df[df["acq_date"].dt.year.isin(HISTORY_YEARS)]
    log.info("  high-conf rows %d-%d: %d",
             min(HISTORY_YEARS), max(HISTORY_YEARS), len(df))

    log.info("Loading beat polygons...")
    beats = gpd.read_file(BEATS_GEOJSON)
    log.info("  %d beats", len(beats))

    log.info("Spatial joining (strict-within + 330 m edge tolerance)...")
    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(lon, lat) for lat, lon in zip(df["latitude"], df["longitude"])],
        crs="EPSG:4326",
    )
    inside = gpd.sjoin(gdf, beats[["Division", "Range", "Beat", "geometry"]],
                      how="inner", predicate="within")
    inside["_pass"] = 1; inside["_dist"] = 0.0
    edge = gpd.sjoin_nearest(gdf, beats[["Division", "Range", "Beat", "geometry"]],
                             how="inner", max_distance=0.003, distance_col="_dist")
    edge["_pass"] = 2
    joined = pd.concat([inside, edge], ignore_index=True)
    joined = joined.sort_values(["_pass", "_dist"]).drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first"
    )
    log.info("  attached: %d FIRMS detections to beats", len(joined))

    joined["year"] = joined["acq_date"].dt.year
    joined["week_of_year"] = joined["acq_date"].dt.isocalendar().week.astype(int)

    log.info("Aggregating per (beat, week)...")
    grp = joined.groupby(["Division", "Range", "Beat", "week_of_year"]).agg(
        total_fires=("latitude", "size"),
        n_years_with_fire=("year", "nunique"),
        max_frp_seen=("frp", lambda s: float(s.max()) if s.notna().any() else 0.0),
    ).reset_index()
    grp["mean_fires_per_year"] = (grp["total_fires"]
                                   / len(HISTORY_YEARS)).round(2)

    # Rank within each week_of_year — percentile of total_fires
    grp["percentile_in_week"] = grp.groupby("week_of_year")["total_fires"].rank(
        method="max", pct=True
    ).round(3)

    log.info("Climatology rows: %d (across %d unique weeks-of-year)",
             len(grp), grp["week_of_year"].nunique())

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    grp.to_parquet(OUT_PATH, index=False)
    log.info("Wrote %s", OUT_PATH.relative_to(ROOT))

    # Quick sanity stats
    log.info("=" * 60)
    log.info("Top-10 (Beat, week) by 5-year fire count:")
    for _, r in grp.nlargest(10, "total_fires").iterrows():
        log.info("  W%02d  %-25s/%s  %d fires (%.1f/yr) FRP=%.1f",
                 r.week_of_year, r.Division, r.Beat,
                 r.total_fires, r.mean_fires_per_year, r.max_frp_seen)

    log.info("Distribution of beats by climatological burn intensity:")
    for pct, label in [(0.99, ">99th pct"), (0.95, ">95th"), (0.90, ">90th"),
                        (0.75, ">75th"), (0.50, ">50th")]:
        n = (grp["percentile_in_week"] >= pct).sum()
        log.info("  %s : %d (beat, week) cells", label, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
