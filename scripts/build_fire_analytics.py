"""
Build Fire Analytics - Van Suraksha / JwalaNetra
=================================================
Mines 13 years of FIRMS VIIRS SNPP Standard Product fire detection data
(2013-2025) to generate operational fire analytics for Guna Division, MP.

Outputs
-------
  outputs/analytics/fire_heat_map.parquet   - 500m x 500m grid fire density
  outputs/analytics/fire_climatology.json   - per-range/beat/month stats
  outputs/analytics/top_fire_prone_beats.csv - top 20 most fire-prone beats

Usage
-----
  python scripts/build_fire_analytics.py
  python scripts/build_fire_analytics.py --output-dir /path/to/out
"""

from __future__ import annotations

import argparse
import json
import os as _os
import sys as _sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from src.utils.proj_fix import setup_proj_env  # noqa: E402

setup_proj_env()
import geopandas as gpd  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
FIRMS_DIR = ROOT / "data_lake" / "fire_detections" / "firms_viirs_snpp_sp"
BEATS_FILE = ROOT / "data" / "aoi" / "gunafinal.geojson"

YEARS = list(range(2013, 2026))   # 2013-2025 inclusive
N_YEARS = len(YEARS)              # 13
CURRENT_YEAR = YEARS[-1]          # 2025
BBOX = (76.45, 23.80, 77.85, 24.95)  # lon_min, lat_min, lon_max, lat_max
GRID_DEG = 0.0045                 # ~500 m at lat ~24 N
UTM_CRS = "EPSG:32644"            # UTM zone 44N - covers Guna Division


# ---------------------------------------------------------------------------
# Step 1 - Load FIRMS annual parquets
# ---------------------------------------------------------------------------

def load_firms_data() -> pd.DataFrame:
    """Concatenate all annual VIIRS SNPP SP parquets, clip to Guna bbox.

    Returns DataFrame with columns: latitude, longitude, frp, confidence,
    year, month (plus original FIRMS columns).
    """
    frames: list[pd.DataFrame] = []
    lon_min, lat_min, lon_max, lat_max = BBOX

    for yr in YEARS:
        path = FIRMS_DIR / f"viirs_snpp_sp_{yr}_annual.parquet"
        if not path.exists():
            print(f"  [WARN] Missing: {path.name} - skipping year {yr}")
            continue
        df = pd.read_parquet(path)
        if df.empty:
            continue
        mask = (
            (df["longitude"] >= lon_min) & (df["longitude"] <= lon_max)
            & (df["latitude"] >= lat_min) & (df["latitude"] <= lat_max)
        )
        df = df[mask].copy()
        if df.empty:
            continue
        df["year"] = yr
        frames.append(df)

    if not frames:
        raise RuntimeError(
            f"No VIIRS data found in {FIRMS_DIR}. "
            "Run scripts/download_firms_historical.py first."
        )

    all_df = pd.concat(frames, ignore_index=True)
    all_df["acq_date"] = pd.to_datetime(all_df["acq_date"], errors="coerce")
    all_df.dropna(subset=["acq_date", "latitude", "longitude"], inplace=True)
    all_df["month"] = all_df["acq_date"].dt.month.astype(np.int8)
    all_df["frp"] = pd.to_numeric(all_df["frp"], errors="coerce").fillna(0.0)

    print(f"  Loaded {len(all_df):,} detections across {len(frames)} year files")
    return all_df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 2 - Spatial join: assign each detection to a beat
# ---------------------------------------------------------------------------

def assign_beats(df: pd.DataFrame, beats_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Attach BEAT and RANGE columns via point-in-polygon join.

    Fires outside all polygons get a nearest-neighbour fallback up to 0.01
    degrees (~1 km). Remaining unmatched detections are labelled 'UNASSIGNED'.
    """
    gdf_pts = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )
    beat_cols = beats_gdf[["BEAT", "RANGE", "geometry"]].copy()

    # Primary: strict point-in-polygon
    joined = gpd.sjoin(gdf_pts, beat_cols, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    unmatched_mask = joined["BEAT"].isna()

    # Fallback: nearest polygon within ~1 km
    if unmatched_mask.any():
        unmatched_pts = gdf_pts[unmatched_mask.values]
        fallback = gpd.sjoin_nearest(
            unmatched_pts, beat_cols, how="left", max_distance=0.01
        )
        fallback = fallback[~fallback.index.duplicated(keep="first")]
        joined.loc[unmatched_mask, "BEAT"] = fallback["BEAT"].values
        joined.loc[unmatched_mask, "RANGE"] = fallback["RANGE"].values

    joined["BEAT"] = joined["BEAT"].fillna("UNASSIGNED")
    joined["RANGE"] = joined["RANGE"].fillna("UNASSIGNED")

    result = df.copy()
    result["BEAT"] = joined["BEAT"].values
    result["RANGE"] = joined["RANGE"].values
    n_assigned = (result["BEAT"] != "UNASSIGNED").sum()
    print(f"  Spatial join: {n_assigned:,}/{len(result):,} detections assigned to beats")
    return result


# ---------------------------------------------------------------------------
# Step 3 - 500m x 500m heat map grid
# ---------------------------------------------------------------------------

def build_heat_map(df: pd.DataFrame) -> pd.DataFrame:
    """Build a 500-m grid of fire statistics over Guna Division.

    Returns DataFrame with columns: cell_id, lat, lon, fire_count, mean_frp,
    max_frp, fire_years, fire_return_interval, peak_month, fire_density_per_km2.
    Only cells with at least one detection are included.
    """
    lon_min, lat_min, lon_max, lat_max = BBOX
    lon_bins = np.arange(lon_min, lon_max + GRID_DEG, GRID_DEG)
    lat_bins = np.arange(lat_min, lat_max + GRID_DEG, GRID_DEG)
    n_lon = len(lon_bins) - 1
    n_lat = len(lat_bins) - 1

    work = df.copy()
    work["cx"] = (np.digitize(work["longitude"], lon_bins) - 1).clip(0, n_lon - 1)
    work["cy"] = (np.digitize(work["latitude"],  lat_bins) - 1).clip(0, n_lat - 1)
    work["cell_id"] = work["cy"] * n_lon + work["cx"]
    work["cell_lon"] = lon_bins[work["cx"]] + GRID_DEG / 2
    work["cell_lat"] = lat_bins[work["cy"]] + GRID_DEG / 2

    agg = (
        work.groupby("cell_id")
        .agg(
            fire_count=("frp", "count"),
            sum_frp=("frp", "sum"),
            max_frp=("frp", "max"),
            lat=("cell_lat", "first"),
            lon=("cell_lon", "first"),
        )
        .reset_index()
    )
    agg["mean_frp"] = np.where(
        agg["fire_count"] > 0, agg["sum_frp"] / agg["fire_count"], 0.0
    )

    # Distinct years with at least one fire per cell
    fire_years_per_cell = (
        work.groupby(["cell_id", "year"])
        .size()
        .reset_index(name="_n")
        .groupby("cell_id")["year"]
        .nunique()
        .rename("fire_years")
    )
    agg = agg.merge(fire_years_per_cell, on="cell_id", how="left")
    agg["fire_years"] = agg["fire_years"].fillna(0).astype(int)
    agg["fire_return_interval"] = np.where(
        agg["fire_years"] > 0, N_YEARS / agg["fire_years"], float("nan")
    )

    # Peak month: month with highest cumulative detections in that cell
    monthly_per_cell = (
        work.groupby(["cell_id", "month"]).size().unstack(fill_value=0)
    )
    agg["peak_month"] = (
        monthly_per_cell.idxmax(axis=1).reindex(agg["cell_id"]).values
    )

    # Approximate cell area (lat-corrected) for density calculation
    lat_rad = np.radians(agg["lat"])
    cell_area_km2 = (GRID_DEG * 111.0) * (GRID_DEG * 111.0 * np.cos(lat_rad))
    agg["fire_density_per_km2"] = agg["fire_count"] / cell_area_km2

    return agg[[
        "cell_id", "lat", "lon", "fire_count", "mean_frp", "max_frp",
        "fire_years", "fire_return_interval", "peak_month", "fire_density_per_km2",
    ]].sort_values("cell_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 4 - Climatology helpers
# ---------------------------------------------------------------------------

def _trend_slope(annual_counts: pd.Series) -> float:
    """Return fires/year linear trend slope. Returns 0.0 if < 2 points."""
    yrs = np.array(annual_counts.index, dtype=float)
    vals = annual_counts.values.astype(float)
    if len(yrs) < 2:
        return 0.0
    return round(float(np.polyfit(yrs, vals, 1)[0]), 4)


def _monthly_avg(df_sub: pd.DataFrame) -> list[float]:
    """Return list[12] of mean fires per month, averaged across all years."""
    monthly = (
        df_sub.groupby(["year", "month"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=range(1, 13), fill_value=0)
    )
    means = monthly.mean(axis=0)
    return [round(float(means[m]), 2) for m in range(1, 13)]


def _annual_series(df_sub: pd.DataFrame) -> pd.Series:
    """Annual totals zero-filled for years with no detections."""
    return df_sub.groupby("year").size().reindex(YEARS, fill_value=0)


# ---------------------------------------------------------------------------
# Step 4 - Build full climatology
# ---------------------------------------------------------------------------

def build_climatology(
    df: pd.DataFrame,
    beats_gdf: gpd.GeoDataFrame,
) -> dict[str, Any]:
    """Compute fire climatology: by_range, by_beat, by_month, annual_totals.

    Only detections assigned to a named beat (BEAT != 'UNASSIGNED') contribute
    to the range/beat breakdowns. All detections count in total_detections.
    """
    assigned = df[df["BEAT"] != "UNASSIGNED"]

    # ---- by_range --------------------------------------------------------
    by_range: dict[str, Any] = {}
    for rng, rdf in assigned.groupby("RANGE"):
        ann = _annual_series(rdf)
        mavg = _monthly_avg(rdf)
        beat_fires = rdf.groupby("BEAT").size().sort_values(ascending=False).head(5)
        by_range[str(rng)] = {
            "total_fires": int(len(rdf)),
            "mean_annual": round(float(ann.mean()), 2),
            "peak_month": int(mavg.index(max(mavg)) + 1),
            "monthly_avg": mavg,
            "trend_slope": _trend_slope(ann),
            "top_beats": [{"beat": b, "fires": int(n)} for b, n in beat_fires.items()],
        }

    # ---- by_beat ---------------------------------------------------------
    by_beat: dict[str, Any] = {}
    for beat, bdf in assigned.groupby("BEAT"):
        ann = _annual_series(bdf)
        years_with_fire = int((ann > 0).sum())
        mavg = _monthly_avg(bdf)
        current_fires = float(ann.get(CURRENT_YEAR, 0))
        prior_mean = float(ann[ann.index != CURRENT_YEAR].mean())
        by_beat[str(beat)] = {
            "range": str(bdf["RANGE"].iloc[0]),
            "total_fires": int(len(bdf)),
            "mean_annual": round(float(ann.mean()), 2),
            "peak_month": int(mavg.index(max(mavg)) + 1),
            "monthly_avg": mavg,
            "fire_return_years": round(N_YEARS / max(years_with_fire, 1), 2),
            "trend_slope": _trend_slope(ann),
            "anomaly_current_year": (
                round(current_fires / prior_mean, 3) if prior_mean > 0 else 0.0
            ),
        }

    # ---- by_month --------------------------------------------------------
    monthly_annual = (
        assigned.groupby(["year", "month"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=range(1, 13), fill_value=0)
    )
    by_month: dict[str, Any] = {
        str(m): {
            "avg_fires": round(float(monthly_annual[m].mean()), 2),
            "std": round(float(monthly_annual[m].std()), 2),
        }
        for m in range(1, 13)
    }

    # ---- annual_totals ---------------------------------------------------
    annual_totals: dict[str, int] = {
        str(yr): int((assigned["year"] == yr).sum()) for yr in YEARS
    }

    return {
        "generated": datetime.now(tz=timezone.utc).isoformat(),
        "period": f"{YEARS[0]}-{YEARS[-1]}",
        "total_detections": int(len(df)),
        "by_range": by_range,
        "by_beat": by_beat,
        "by_month": by_month,
        "annual_totals": annual_totals,
    }


# ---------------------------------------------------------------------------
# Step 5 - Top 20 fire-prone beats
# ---------------------------------------------------------------------------

def build_top_beats(
    clim: dict[str, Any],
    beats_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Rank all beats with detected fires by fire density, return top 20.

    Returns DataFrame with columns: rank, beat, range, total_fires,
    fire_density_per_km2, mean_annual, peak_month, trend.
    """
    beats_utm = beats_gdf.to_crs(UTM_CRS)
    beat_areas: pd.Series = (
        beats_utm.assign(area_km2=beats_utm.area / 1e6)
        .groupby("BEAT")["area_km2"]
        .sum()
    )
    mean_area = float(beat_areas.mean())
    rows = []
    for beat, stats in clim["by_beat"].items():
        area = float(beat_areas.get(beat, mean_area))
        rows.append(
            {
                "beat": beat,
                "range": stats["range"],
                "total_fires": stats["total_fires"],
                "fire_density_per_km2": round(
                    stats["total_fires"] / area if area > 0 else 0.0, 4
                ),
                "mean_annual": stats["mean_annual"],
                "peak_month": stats["peak_month"],
                "trend": stats["trend_slope"],
            }
        )

    top = (
        pd.DataFrame(rows)
        .sort_values("fire_density_per_km2", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )
    top.insert(0, "rank", top.index + 1)
    return top


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(
    df: pd.DataFrame,
    clim: dict[str, Any],
    top: pd.DataFrame,
) -> None:
    """Print key analytics to stdout."""
    print("\n" + "=" * 60)
    print("FIRE ANALYTICS SUMMARY - Guna Division (2013-2025)")
    print("=" * 60)
    print(f"  Total detections loaded  : {clim['total_detections']:,}")
    print(f"  Detections assigned beat : {(df['BEAT'] != 'UNASSIGNED').sum():,}")
    print(f"  Unique ranges            : {len(clim['by_range'])}")
    print(f"  Unique beats with fires  : {len(clim['by_beat'])}")
    print()
    print("Annual totals:")
    for yr, n in clim["annual_totals"].items():
        bar = "#" * min(n // 5 + 1, 50) if n > 0 else ""
        print(f"  {yr}: {n:>5}  {bar}")
    print()
    month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    max_avg = max(s["avg_fires"] for s in clim["by_month"].values()) or 1.0
    print("Peak fire month distribution (avg fires):")
    for m, stats in clim["by_month"].items():
        bar_len = int(stats["avg_fires"] / max_avg * 30 + 0.5)
        bar = "#" * bar_len if stats["avg_fires"] > 0 else ""
        print(f"  {month_names[int(m)-1]}: {stats['avg_fires']:>6.1f}  {bar}")
    print()
    print("Top 10 fire-prone beats by density:")
    for _, row in top.head(10).iterrows():
        print(
            f"  {int(row['rank']):>2}. {row['beat']:<20} "
            f"[{row['range']:<12}]  "
            f"density={row['fire_density_per_km2']:.3f}/km2  "
            f"total={int(row['total_fires'])}"
        )
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for CLI execution."""
    parser = argparse.ArgumentParser(
        description="Build fire analytics from FIRMS VIIRS SNPP SP data"
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "outputs" / "analytics"),
        help="Output directory (default: outputs/analytics)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\nVan Suraksha - Fire Analytics Builder")
    print(f"  Data source : {FIRMS_DIR}")
    print(f"  Output dir  : {out_dir}")
    print(f"  Period      : {YEARS[0]}-{YEARS[-1]}  ({N_YEARS} years)")
    print(f"  Bbox        : lon {BBOX[0]}-{BBOX[2]}, lat {BBOX[1]}-{BBOX[3]}")

    print("\n[1/5] Loading FIRMS annual parquets ...")
    df = load_firms_data()

    print("[2/5] Loading beat boundaries ...")
    beats_gdf = gpd.read_file(BEATS_FILE)
    print(
        f"  {len(beats_gdf)} polygons, "
        f"{beats_gdf['BEAT'].nunique()} unique beats, "
        f"{beats_gdf['RANGE'].nunique()} ranges"
    )

    print("[3/5] Assigning detections to beats ...")
    df = assign_beats(df, beats_gdf)

    print("[4/5] Building 500m heat map grid ...")
    heat_map = build_heat_map(df)
    heat_path = out_dir / "fire_heat_map.parquet"
    heat_map.to_parquet(heat_path, index=False)
    print(f"  {len(heat_map):,} grid cells with fires -> {heat_path}")

    print("[5/5] Computing climatology ...")
    clim = build_climatology(df, beats_gdf)
    clim_path = out_dir / "fire_climatology.json"
    clim_path.write_text(
        json.dumps(clim, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  {len(clim['by_range'])} ranges, {len(clim['by_beat'])} beats -> {clim_path}")

    top = build_top_beats(clim, beats_gdf)
    top_path = out_dir / "top_fire_prone_beats.csv"
    top.to_csv(top_path, index=False)
    print(f"  Top 20 beats -> {top_path}")

    print_summary(df, clim, top)


if __name__ == "__main__":
    main()
