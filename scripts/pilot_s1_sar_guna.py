"""PS-1 Phase 7 pilot — Sentinel-1 GRD backscatter anomalies for Guna division.

Strategy: GRD products lack InSAR phase (SLC required), so true coherence is
unavailable via ee.Algorithms.CoherenceMatrix on GRD. Instead, use the RADD-style
amplitude approach:

  For each (cell, date D):
    - 12-day window VV backscatter mean/std (recent)
    - 90-day window VV backscatter mean/std (reference)
    - vh_anomaly_z = (recent_mean - ref_mean) / ref_std
    - vh_cv_drop   = recent_cv - ref_cv

Sudden backscatter drop (canopy cleared) OR variance spike (unstable scattering
from freshly disturbed soil/litter) is the T-24h precursor for anthropogenic
ignition that penetrates canopy where optical sensors cannot.

Pilot scope: Guna division only (1,008 v6e cells) × val window (2025-02-01 to
2025-05-29, sampled weekly). Server-side reduceRegions → direct getInfo, no
Drive export needed at this scale.

Exit criteria:
  - Cells within 2km × 7 days of a v8 DBSCAN ignition show vh_anomaly_z
    distribution shifted negative or |vh_anomaly_z| > control cells
  - Spearman ρ(|s1_anomaly|, is_ignition_within_7d) > 0.05 → signal exists
  - If positive: scale to MP (next script)
  - If null: pivot to SLC-based true coherence or park

Usage:
  python scripts/pilot_s1_sar_guna.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import ee
import numpy as np
import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ee.Initialize(project="van-suraksha-alert")

ROOT = Path(__file__).resolve().parents[1]
CELLS_CSV = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
GUNA_GEOJSON = ROOT / "data" / "aoi" / "guna_division.geojson"
DBSCAN_PATH = ROOT / "data_lake" / "fire_detections" / "firms_dbscan_ignition.parquet"
OUT_PATH = ROOT / "data_lake" / "sar" / "s1_pilot_guna_vh.parquet"
OUT_DIAG = ROOT / "data_lake" / "sar" / "s1_pilot_diagnostics_vh.json"

VAL_START = "2025-02-01"
VAL_END = "2025-05-29"
RECENT_DAYS = 18
REFERENCE_DAYS = 180
POL_BAND = "VH"
SAMPLE_DATES = [
    "2025-02-15", "2025-03-01", "2025-03-15", "2025-04-01",
    "2025-04-15", "2025-05-01", "2025-05-15",
]
CELL_HALF_KM = 1.0  # 2km cells → ±1km from centroid


def load_guna_geometry() -> ee.Geometry:
    with open(GUNA_GEOJSON) as f:
        gj = json.load(f)
    geom_type = gj["features"][0]["geometry"]["type"]
    coords = gj["features"][0]["geometry"]["coordinates"]
    return ee.Geometry.MultiPolygon(coords) if geom_type == "MultiPolygon" else ee.Geometry.Polygon(coords)


def s1_collection(aoi: ee.Geometry, start: ee.Date, end: ee.Date) -> ee.ImageCollection:
    """Sentinel-1 GRD with VH cross-pol, BOTH orbital passes (max coverage)."""
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", POL_BAND))
        .select(POL_BAND)
    )


def build_sar_features_image(aoi: ee.Geometry, target_date: str) -> ee.Image:
    target = ee.Date(target_date)
    recent = s1_collection(aoi, target.advance(-RECENT_DAYS, "day"), target)
    reference = s1_collection(aoi, target.advance(-REFERENCE_DAYS, "day"), target.advance(-RECENT_DAYS, "day"))

    recent_mean = recent.mean().rename("vh_recent_mean")
    recent_std = recent.reduce(ee.Reducer.stdDev()).rename("vh_recent_std")
    ref_mean = reference.mean().rename("vh_ref_mean")
    ref_std = reference.reduce(ee.Reducer.stdDev()).rename("vh_ref_std")

    vh_anomaly_z = recent_mean.subtract(ref_mean).divide(ref_std.max(0.5)).rename("vh_anomaly_z")
    cv_recent = recent_std.divide(recent_mean.abs().max(0.5)).rename("cv_recent")
    cv_ref = ref_std.divide(ref_mean.abs().max(0.5)).rename("cv_ref")
    cv_drop = cv_recent.subtract(cv_ref).rename("vh_cv_drop")

    return (
        recent_mean
        .addBands(ref_mean)
        .addBands(vh_anomaly_z)
        .addBands(cv_drop)
    )


def cells_to_fc(cells: pd.DataFrame) -> ee.FeatureCollection:
    feats = []
    half_deg = CELL_HALF_KM / 111.32  # rough km→deg at this latitude
    for _, r in cells.iterrows():
        lon, lat = float(r.centroid_lon), float(r.centroid_lat)
        rect = ee.Geometry.Rectangle([lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg])
        feats.append(ee.Feature(rect, {"cell_id": str(r.cell_id)}))
    return ee.FeatureCollection(feats)


def sample_one_date(aoi: ee.Geometry, fc: ee.FeatureCollection, target_date: str) -> pd.DataFrame:
    img = build_sar_features_image(aoi, target_date)
    sampled = img.reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean(),
        scale=30,
        tileScale=4,
    )
    info = sampled.getInfo()
    rows = []
    for f in info["features"]:
        p = f["properties"]
        rows.append({
            "cell_id": p["cell_id"],
            "target_date": target_date,
            "vh_recent_mean": p.get("vh_recent_mean"),
            "vh_ref_mean": p.get("vh_ref_mean"),
            "vh_anomaly_z": p.get("vh_anomaly_z"),
            "vh_cv_drop": p.get("vh_cv_drop"),
        })
    return pd.DataFrame(rows)


def diagnose(df: pd.DataFrame) -> dict:
    """Compare SAR features for ignition cells vs control cells."""
    if not DBSCAN_PATH.exists():
        log.warning("DBSCAN ignition file missing — skipping ignition correlation")
        return {"warning": "no DBSCAN file"}

    ign = pd.read_parquet(DBSCAN_PATH)
    ign = ign[ign["is_ignition"] == 1].copy()
    ign["acq_date"] = pd.to_datetime(ign["acq_date"])

    cells = pd.read_csv(CELLS_CSV)
    guna_cells = cells[cells["division"] == "Guna"][["cell_id", "centroid_lat", "centroid_lon"]]
    df = df.merge(guna_cells, on="cell_id", how="left")
    df["target_date"] = pd.to_datetime(df["target_date"])

    df["ignition_within_7d"] = 0
    half_km = CELL_HALF_KM
    for idx, row in df.iterrows():
        d = row["target_date"]
        nearby = ign[(ign["acq_date"] >= d) & (ign["acq_date"] <= d + pd.Timedelta(days=7))]
        if len(nearby) == 0:
            continue
        lat0, lon0 = row["centroid_lat"], row["centroid_lon"]
        dlat = (nearby["latitude"] - lat0).abs() * 111.32
        dlon = (nearby["longitude"] - lon0).abs() * 111.32 * np.cos(np.radians(lat0))
        if ((dlat <= half_km) & (dlon <= half_km)).any():
            df.at[idx, "ignition_within_7d"] = 1

    pos = df[df["ignition_within_7d"] == 1]
    neg = df[df["ignition_within_7d"] == 0]
    diag = {
        "n_total": int(len(df)),
        "n_ignition_cells_dates": int(len(pos)),
        "n_control": int(len(neg)),
        "vh_anomaly_z_pos_median": float(pos["vh_anomaly_z"].median()) if len(pos) else None,
        "vh_anomaly_z_neg_median": float(neg["vh_anomaly_z"].median()) if len(neg) else None,
        "abs_vh_anomaly_z_pos_median": float(pos["vh_anomaly_z"].abs().median()) if len(pos) else None,
        "abs_vh_anomaly_z_neg_median": float(neg["vh_anomaly_z"].abs().median()) if len(neg) else None,
        "vh_cv_drop_pos_median": float(pos["vh_cv_drop"].median()) if len(pos) else None,
        "vh_cv_drop_neg_median": float(neg["vh_cv_drop"].median()) if len(neg) else None,
    }
    if len(pos) > 5 and len(neg) > 5:
        from scipy.stats import spearmanr, mannwhitneyu
        valid = df.dropna(subset=["vh_anomaly_z"])
        rho, p = spearmanr(valid["vh_anomaly_z"].abs(), valid["ignition_within_7d"])
        diag["spearman_abs_anomaly_vs_ign_7d"] = {"rho": float(rho), "p": float(p)}
        u_stat, u_p = mannwhitneyu(pos["vh_anomaly_z"].abs().dropna(), neg["vh_anomaly_z"].abs().dropna(), alternative="greater")
        diag["mannwhitney_pos_gt_neg_abs_anomaly"] = {"u": float(u_stat), "p": float(u_p)}
    return diag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", default=SAMPLE_DATES)
    args = parser.parse_args()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading Guna geometry + cells...")
    aoi = load_guna_geometry()
    cells = pd.read_csv(CELLS_CSV)
    guna = cells[cells["division"] == "Guna"].reset_index(drop=True)
    log.info("  %d Guna cells", len(guna))

    log.info("Sanity: count S1 GRD scenes for Guna × val window")
    n = s1_collection(aoi, ee.Date(VAL_START), ee.Date(VAL_END)).size().getInfo()
    log.info("  %d S1 GRD ascending scenes over Guna in val window", n)
    if n < 5:
        log.error("Too few S1 scenes — pilot aborted")
        return 1

    fc = cells_to_fc(guna)

    all_rows = []
    for date_str in args.dates:
        log.info("Sampling SAR features for target date %s...", date_str)
        t0 = time.time()
        try:
            df_d = sample_one_date(aoi, fc, date_str)
            log.info("  got %d rows in %.0fs", len(df_d), time.time() - t0)
            all_rows.append(df_d)
        except ee.EEException as exc:
            log.error("  GEE error for %s: %s", date_str, exc)

    if not all_rows:
        log.error("No data sampled — aborting")
        return 1

    df = pd.concat(all_rows, ignore_index=True)
    df.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved %d rows × %d cols → %s", len(df), len(df.columns), OUT_PATH.relative_to(ROOT))

    log.info("\n=== Coverage stats ===")
    log.info("  Non-null vh_anomaly_z: %d (%.1f%%)", df["vh_anomaly_z"].notna().sum(), 100 * df["vh_anomaly_z"].notna().mean())
    log.info("  vh_anomaly_z: median=%.2f p10=%.2f p90=%.2f",
             df["vh_anomaly_z"].median(), df["vh_anomaly_z"].quantile(0.1), df["vh_anomaly_z"].quantile(0.9))
    log.info("  vh_cv_drop: median=%.3f p10=%.3f p90=%.3f",
             df["vh_cv_drop"].median(), df["vh_cv_drop"].quantile(0.1), df["vh_cv_drop"].quantile(0.9))

    log.info("\n=== Ignition correlation diagnosis ===")
    diag = diagnose(df)
    for k, v in diag.items():
        log.info("  %s: %s", k, v)
    OUT_DIAG.write_text(json.dumps(diag, indent=2))
    log.info("\nDiagnostics saved → %s", OUT_DIAG.relative_to(ROOT))

    log.info("\n=== VERDICT ===")
    if "spearman_abs_anomaly_vs_ign_7d" in diag:
        rho = diag["spearman_abs_anomaly_vs_ign_7d"]["rho"]
        p = diag["spearman_abs_anomaly_vs_ign_7d"]["p"]
        if abs(rho) > 0.05 and p < 0.05:
            log.info("  PASS — Spearman ρ=%.3f (p=%.3g): SAR carries ignition signal. Scale to MP.", rho, p)
        else:
            log.info("  WEAK — Spearman ρ=%.3f (p=%.3g): signal too small at GRD amplitude resolution.", rho, p)
            log.info("  Recommendation: try SLC coherence OR park PS-1.")
    else:
        log.info("  INCONCLUSIVE — too few ignition cells in pilot window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
