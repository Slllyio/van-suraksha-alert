"""Stage 3 — Tier H physics-informed T0 rectification for BA clusters.

Greenlit by Stage 0 ellipse-fit pilot (90.2% defensibility). For each cluster:

  1. Cluster polygon → PCA → major axis length L_maj (pixels → meters) and
     orientation θ_burn (degrees from +x/East)
  2. Identify upwind extreme of major axis as spatial ignition point x₀
     (burns spread DOWNwind from ignition)
  3. Compute mean head-ROS via simple Rothermel-style scaling:
       ROS_head_m_per_min = ROS_base × slope_factor × wind_factor × fwi_factor
     Base ROS for MP dry-deciduous: 0.5 m/min (from Cell2Fire ceiling calibration)
  4. Back-calculate t₀:
       t₀ = t_detection − L_maj / ROS_head
       clamp to 6-hour bin (daily weather resolution floor)
       hard-cap at −48h (longer durations → cluster contained multiple events)

Output: adds columns (t0_6hr_bin, x0_rectified_lon, x0_rectified_lat, t0_confidence)
to `data_lake/fire_detections/ignition_labels_tiered_v17.parquet`.

Usage:
  python scripts/rectify_t0_heuristic.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
TIERED_PATH = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
FWI_PATH = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
OUT_PATH = TIERED_PATH  # overwrite in place with new columns

# Physical constants
BASE_ROS_M_PER_MIN = 0.5  # MP dry-deciduous point-source 24h verified in Cell2Fire
MAX_ROS_M_PER_MIN = 15.0  # physical cap
MAX_LOOKBACK_HOURS = 48    # hard cap on how early t0 can be
KM_PER_DEG_LAT = 110.6


def slope_factor(slope_deg: np.ndarray) -> np.ndarray:
    """Rothermel slope coefficient: φ_s = 5.275 × (tan(slope))² for upslope.

    Capped to prevent explosion on steep terrain.
    """
    tan_sq = np.tan(np.radians(np.clip(slope_deg, 0, 45))) ** 2
    return 1.0 + np.clip(5.275 * tan_sq, 0, 4.0)  # cap at 5x


def wind_factor(wind_kmh: np.ndarray) -> np.ndarray:
    """Rothermel wind coefficient: φ_w ≈ (0.1 × U_mi)^1.4 where U is wind speed.

    We use km/h directly with empirical coefficient for MP dry season.
    """
    wind_ms = wind_kmh / 3.6
    return 1.0 + np.clip(0.28 * (wind_ms ** 0.8), 0, 5.0)


def fwi_factor(fwi: np.ndarray) -> np.ndarray:
    """FWI scaling factor — higher FWI → more energetic fire → higher ROS."""
    return 0.5 + np.clip(fwi / 30.0, 0, 2.0)  # multiplier 0.5-2.5


def bucket_6hr(hours_offset: np.ndarray) -> np.ndarray:
    """Convert hours before detection into discrete 6hr bins (0-3).

    bin 0: detection time itself (0-6h before)
    bin 1: 6-12h before
    bin 2: 12-24h before
    bin 3: 24-48h before
    """
    abs_h = np.abs(hours_offset)
    bins = np.zeros_like(abs_h, dtype=np.int8)
    bins = np.where(abs_h > 6, 1, bins)
    bins = np.where(abs_h > 12, 2, bins)
    bins = np.where(abs_h > 24, 3, bins)
    return bins


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ros", type=float, default=BASE_ROS_M_PER_MIN)
    args = parser.parse_args()

    if not TIERED_PATH.exists():
        log.error("Missing tiered labels: %s. Run scripts/fuse_ba_firms_labels.py first.", TIERED_PATH)
        return 2

    log.info("Loading tiered labels...")
    df = pd.read_parquet(TIERED_PATH)
    df["ignition_date"] = pd.to_datetime(df["ignition_date"])
    log.info("  %d rows (%s tiers)", len(df), dict(df["tier"].value_counts()))

    log.info("Loading cells + FWI...")
    cells = pd.read_csv(CELLS_PATH)[["cell_id", "t_slope_mean", "centroid_lat", "centroid_lon"]]
    cell_slope = cells.set_index("cell_id")["t_slope_mean"].to_dict()
    fwi = pd.read_parquet(FWI_PATH) if FWI_PATH.exists() else pd.DataFrame()
    if len(fwi):
        fwi["date"] = pd.to_datetime(fwi["date"])
        fwi_by_date = fwi.set_index("date")[["fwi", "wind_kmh"]].to_dict("index")
    else:
        log.warning("FWI parquet missing — will use climatological defaults (fwi=15, wind=10)")
        fwi_by_date = {}

    log.info("Computing Tier H rectification...")

    # Only rectify GOLD + SILVER (BA-derived, have polygon geometry)
    mask = df["tier"].isin(["GOLD", "SILVER"])
    sub = df[mask].reset_index(drop=True).copy()
    if len(sub) == 0:
        log.warning("No GOLD/SILVER rows to rectify. Writing unchanged.")
        df.to_parquet(OUT_PATH, index=False)
        return 0

    # Look up slope per cell
    slope_vals = sub["cell_id"].map(cell_slope).fillna(5.0).values

    # Look up FWI + wind per date
    fwi_vals = np.full(len(sub), 15.0)
    wind_vals = np.full(len(sub), 10.0)
    for i, d in enumerate(sub["ignition_date"]):
        entry = fwi_by_date.get(d.normalize(), None)
        if entry is not None:
            fwi_vals[i] = entry["fwi"]
            wind_vals[i] = entry["wind_kmh"]

    # L_maj from aspect_ratio × sqrt(area / aspect_ratio)  [approximate from ellipse area]
    # For ellipse: area = π × a × b, aspect = a/b, so a = sqrt(area × aspect / π)
    # area in m² = area_ha × 10,000
    area_m2 = sub["area_ha"].values * 10000.0
    aspect = np.clip(sub["aspect_ratio"].values, 1.0, 10.0)
    semi_major_m = np.sqrt(area_m2 * aspect / np.pi)
    L_maj_m = 2.0 * semi_major_m  # full major axis length

    # Rothermel-style ROS (m/min)
    phi_s = slope_factor(slope_vals)
    phi_w = wind_factor(wind_vals)
    phi_fwi = fwi_factor(fwi_vals)
    ros_head = args.base_ros * phi_s * phi_w * phi_fwi
    ros_head = np.clip(ros_head, args.base_ros * 0.5, MAX_ROS_M_PER_MIN)

    # Time to traverse major axis (minutes → hours)
    duration_min = L_maj_m / ros_head
    duration_hr = duration_min / 60.0
    duration_hr = np.clip(duration_hr, 0, MAX_LOOKBACK_HOURS)

    # t0 in 6hr bins (negative offset = earlier)
    t0_bin = bucket_6hr(duration_hr)

    # t0 confidence: higher for larger clusters (more pixels → better ellipse fit)
    # & reasonable aspect (1.3-5.0 range)
    n_px_like = np.log1p(area_m2 / 25e4)  # normalized log of pixel count (500m reference)
    aspect_ok = ((aspect >= 1.3) & (aspect <= 5.0)).astype(float)
    confidence = np.clip(0.3 + 0.2 * np.tanh(n_px_like / 3.0) + 0.5 * aspect_ok, 0, 1)

    # Rectified spatial ignition point: for now, use cluster centroid
    # TODO: upwind extreme of major axis requires wind-bearing + polygon geometry
    sub["t0_6hr_bin"] = t0_bin
    sub["t0_duration_hours"] = duration_hr
    sub["t0_rectified_ros_m_per_min"] = ros_head
    sub["t0_confidence"] = confidence
    sub["x0_rectified_lon"] = sub["ignition_lon"]  # upwind-extreme TODO
    sub["x0_rectified_lat"] = sub["ignition_lat"]

    log.info("\n=== Tier H stats on GOLD+SILVER ===")
    log.info("ROS_head (m/min): median=%.2f p10=%.2f p90=%.2f", np.median(ros_head),
             np.percentile(ros_head, 10), np.percentile(ros_head, 90))
    log.info("Duration (hours): median=%.1f p10=%.1f p90=%.1f", np.median(duration_hr),
             np.percentile(duration_hr, 10), np.percentile(duration_hr, 90))
    log.info("t0_6hr_bin distribution: %s",
             pd.Series(t0_bin).value_counts().sort_index().to_dict())
    log.info("t0_confidence: median=%.2f", float(np.median(confidence)))

    # Merge back to full df (BRONZE tier gets NaN for rectification cols)
    new_cols = ["t0_6hr_bin", "t0_duration_hours", "t0_rectified_ros_m_per_min",
                "t0_confidence", "x0_rectified_lon", "x0_rectified_lat"]
    for col in new_cols:
        df[col] = np.nan if col != "t0_6hr_bin" else 0
    df.loc[mask, new_cols] = sub[new_cols].values

    df.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved → %s (%d rows, added %d Tier H columns)",
             OUT_PATH.relative_to(ROOT), len(df), len(new_cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
