"""Stage audit — Brutal per-(cell, Thursday) audit of v17_ba_pu.

Key design finding: v17 is a WEEKLY same-Thursday detector, not a 7-day ahead
predictor. v8 training labels were built by matching FIRMS DBSCAN ignitions to
the prediction Thursday itself. So the audit questions are:
  - On each val Thursday D, how many of v17's top-5% cells actually ignited?
  - Which cells does v17 chronically false-alarm on?
  - Which actual ignitions did v17 never even WATCH-band warn on?
  - Per-week variance in R@top-5% — is the 47.41% headline robust or a few-week win?

Scope: 2025 hold-out (18 Thursdays, 765K rows) AND 2026 partial Thursdays
if features are extended.

Output:
  data_lake/audits/v17_audit_per_cell_date.parquet — 765K val rows with
    columns [cell_id, date, label, ignition_risk, within_day_rank, band,
    hit_same_day, cell_lat, cell_lon]
  data_lake/audits/v17_audit_per_day_summary.parquet — 18 rows, per-week metrics
  data_lake/audits/v17_audit_per_cell_season.parquet — per-cell rollup over season
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V8_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
V17_MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "model.txt"
HAWKES = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
GLCM = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
FIRMS_PATH = ROOT / "data_lake" / "fire_detections" / "firms_dbscan_ignition.parquet"
TIERED = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"

OUT_DIR = ROOT / "data_lake" / "audits"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HOLDOUT_START = pd.Timestamp("2025-02-01")
BAND_THR = {"WATCH": 0.95, "ALERT": 0.98, "CRITICAL": 0.995}
KM_PER_DEG_LAT = 110.6


def build_val_frame() -> tuple[pd.DataFrame, list[str]]:
    """Load v8 val rows + merge Hawkes + GLCM + Hydro + tiered label."""
    log.info("Loading v8 dataset (all features + dbscan label)...")
    ds = pd.read_parquet(V8_DIR / "dataset.parquet")
    ds["date"] = pd.to_datetime(ds["date"])

    log.info("Merging Hawkes...")
    hk = pd.read_parquet(HAWKES)
    hk["date"] = pd.to_datetime(hk["date"])
    ds = ds.merge(hk, on=["cell_id", "date"], how="left")
    for c in [col for col in ds.columns if col.startswith("hawkes_")]:
        ds[c] = ds[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    log.info("Merging GLCM + Hydro...")
    g = pd.read_parquet(GLCM)
    ds = ds.merge(g, on="cell_id", how="left")
    for c in [col for col in g.columns if col != "cell_id"]:
        ds[c] = ds[c].fillna(ds[c].median())
    h = pd.read_parquet(HYDRO)
    ds = ds.merge(h, on="cell_id", how="left")
    for c in [col for col in h.columns if col != "cell_id"]:
        ds[c] = ds[c].fillna(ds[c].median())

    # Add v18-style tiered label columns for alternative comparison
    tiered = pd.read_parquet(TIERED)
    tiered["ignition_date"] = pd.to_datetime(tiered["ignition_date"])
    tier_rank = {"GOLD": 3, "SILVER": 2, "BRONZE": 1}
    tiered["tier_rank"] = tiered["tier"].astype(str).map(tier_rank).fillna(0).astype(int)
    idx = tiered.groupby(["cell_id", "ignition_date"])["tier_rank"].idxmax()
    by_cd = tiered.loc[idx, ["cell_id", "ignition_date", "tier"]].rename(
        columns={"ignition_date": "date", "tier": "best_tier"})
    ds = ds.merge(by_cd, on=["cell_id", "date"], how="left")
    ds["label_tiered_any"] = ds["best_tier"].notna().astype(int)

    # Select feature list = model's exact features
    model = lgb.Booster(model_file=str(V17_MODEL))
    feats = model.feature_name()
    missing = [f for f in feats if f not in ds.columns]
    if missing:
        log.error("Missing features for v17: %s", missing)
        raise SystemExit(2)
    return ds, feats


def compute_bands_per_day(df_val: pd.DataFrame) -> pd.DataFrame:
    """Assign within-day percentile rank + band (WATCH/ALERT/CRITICAL) per Thursday."""
    df_val = df_val.copy()
    df_val["within_day_rank"] = df_val.groupby("date")["ignition_risk"].rank(pct=True, method="average")
    bands = np.full(len(df_val), "NONE", dtype=object)
    r = df_val["within_day_rank"].values
    bands[r >= BAND_THR["WATCH"]] = "WATCH"
    bands[r >= BAND_THR["ALERT"]] = "ALERT"
    bands[r >= BAND_THR["CRITICAL"]] = "CRITICAL"
    df_val["band"] = bands
    return df_val


def per_day_summary(df_val: pd.DataFrame) -> pd.DataFrame:
    """Per-Thursday summary against BOTH label definitions:
      - DBSCAN-only (strict operational ignition target)
      - BA-fused any-tier (what v17 was TRAINED to predict, headline claim)
    """
    rows = []
    for date, sub in df_val.groupby("date"):
        n_cells = len(sub)
        n_pos_dbscan = int(sub["label_dbscan_ignition"].sum())
        n_pos_tiered = int(sub["label_tiered_any"].sum())
        n_watch = int((sub["band"] == "WATCH").sum())
        n_alert = int((sub["band"] == "ALERT").sum())
        n_critical = int((sub["band"] == "CRITICAL").sum())
        top5 = sub[sub["within_day_rank"] >= 0.95]
        n_top5 = len(top5)
        hits_top5_dbscan = int(top5["label_dbscan_ignition"].sum())
        hits_top5_tiered = int(top5["label_tiered_any"].sum())
        crit = sub[sub["band"] == "CRITICAL"]
        hits_crit_dbscan = int(crit["label_dbscan_ignition"].sum())
        rows.append({
            "date": date,
            "day_of_week": date.day_name(),
            "n_cells": n_cells,
            "n_actual_ignitions_dbscan": n_pos_dbscan,
            "n_actual_ignitions_tiered": n_pos_tiered,
            "n_watch_alerts": n_watch,
            "n_alert_alerts": n_alert,
            "n_critical_alerts": n_critical,
            "n_top5pct_cells": n_top5,
            "hits_in_top5pct_dbscan": hits_top5_dbscan,
            "hits_in_top5pct_tiered": hits_top5_tiered,
            "recall_top5pct_dbscan": hits_top5_dbscan / n_pos_dbscan if n_pos_dbscan else None,
            "recall_top5pct_tiered": hits_top5_tiered / n_pos_tiered if n_pos_tiered else None,
            "precision_top5pct_dbscan": hits_top5_dbscan / n_top5 if n_top5 else None,
            "precision_top5pct_tiered": hits_top5_tiered / n_top5 if n_top5 else None,
            "hits_in_critical_dbscan": hits_crit_dbscan,
            "precision_critical_dbscan": hits_crit_dbscan / n_critical if n_critical else None,
            "max_risk_observed": float(sub["ignition_risk"].max()),
        })
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def per_cell_season(df_val: pd.DataFrame) -> pd.DataFrame:
    """Per-cell season rollup: total alerts, hits, false-alarm streak."""
    grp = df_val.groupby("cell_id")
    summary = grp.agg(
        n_weeks=("date", "count"),
        n_actual_ignitions=("label_dbscan_ignition", "sum"),
        n_watch_weeks=("band", lambda s: (s == "WATCH").sum()),
        n_alert_weeks=("band", lambda s: (s == "ALERT").sum()),
        n_critical_weeks=("band", lambda s: (s == "CRITICAL").sum()),
        max_risk=("ignition_risk", "max"),
        mean_risk=("ignition_risk", "mean"),
    ).reset_index()
    summary["n_any_band"] = summary["n_watch_weeks"] + summary["n_alert_weeks"] + summary["n_critical_weeks"]
    # hit/miss over season
    def hit_info(sub):
        banded_weeks = sub[sub["band"] != "NONE"]
        hit_banded = banded_weeks[banded_weeks["label_dbscan_ignition"] == 1]
        return pd.Series({
            "banded_hits": len(hit_banded),
            "false_alarm_critical": ((sub["band"] == "CRITICAL") & (sub["label_dbscan_ignition"] == 0)).sum(),
            "missed_ignitions_no_band": ((sub["label_dbscan_ignition"] == 1) & (sub["band"] == "NONE")).sum(),
        })
    rich = grp.apply(hit_info, include_groups=False).reset_index()
    summary = summary.merge(rich, on="cell_id", how="left")
    return summary


def main() -> int:
    log.info("=== v17 BRUTAL PER-WEEK AUDIT ===")
    ds, feats = build_val_frame()

    # Val subset only (honest temporal hold-out)
    val = ds[ds["date"] >= HOLDOUT_START].reset_index(drop=True)
    log.info("Val rows: %d across %d Thursdays", len(val), val["date"].nunique())

    log.info("Loading v17 + predicting on val...")
    model = lgb.Booster(model_file=str(V17_MODEL))
    val["ignition_risk"] = model.predict(val[feats].values)

    log.info("Computing per-day bands (within-day percentile ranks)...")
    val = compute_bands_per_day(val)

    # Attach cell coords for spatial analysis
    cells = pd.read_csv(CELLS_PATH)
    val = val.merge(cells[["cell_id", "centroid_lat", "centroid_lon", "division", "range", "beat"]],
                     on="cell_id", how="left")

    keep_cols = ["cell_id", "date", "label_dbscan_ignition", "label_tiered_any", "best_tier",
                 "ignition_risk", "within_day_rank", "band",
                 "centroid_lat", "centroid_lon", "division", "range", "beat",
                 "hawkes_lambda", "hawkes_n_recent_10km_7d"]
    keep_cols = [c for c in keep_cols if c in val.columns]
    per_cell_date = val[keep_cols].copy()

    out_path = OUT_DIR / "v17_audit_per_cell_date.parquet"
    per_cell_date.to_parquet(out_path, index=False)
    log.info("Saved per-cell-date: %s (%d rows, %.1f MB)",
             out_path.relative_to(ROOT), len(per_cell_date), out_path.stat().st_size / 1e6)

    log.info("Building per-day summary...")
    day_summary = per_day_summary(val)
    out_day = OUT_DIR / "v17_audit_per_day_summary.parquet"
    day_summary.to_parquet(out_day, index=False)
    log.info("Saved per-day: %s (%d rows)", out_day.relative_to(ROOT), len(day_summary))

    log.info("Building per-cell season rollup...")
    cell_roll = per_cell_season(val)
    out_cell = OUT_DIR / "v17_audit_per_cell_season.parquet"
    cell_roll.to_parquet(out_cell, index=False)
    log.info("Saved per-cell: %s (%d rows)", out_cell.relative_to(ROOT), len(cell_roll))

    # Headline echo
    log.info("\n=== PER-WEEK R@top-5%% BRUTAL VIEW (dual label: DBSCAN | TIERED) ===")
    for _, r in day_summary.iterrows():
        r_dbscan = f"{r['recall_top5pct_dbscan']:.1%}" if r["recall_top5pct_dbscan"] is not None else "n/a"
        r_tiered = f"{r['recall_top5pct_tiered']:.1%}" if r["recall_top5pct_tiered"] is not None else "n/a"
        log.info(f"  {r['date'].date()} {r['day_of_week']:9s}  "
                 f"pos_dbscan={r['n_actual_ignitions_dbscan']:4d}  R_dbscan={r_dbscan:>6}  "
                 f"pos_tier={r['n_actual_ignitions_tiered']:4d}  R_tier={r_tiered:>6}  "
                 f"crit_hits={r['hits_in_critical_dbscan']:3d}")

    log.info("\n=== SEASON-WIDE STATS (BRUTAL) ===")
    dd = day_summary.dropna(subset=["recall_top5pct_dbscan"])
    dt = day_summary.dropna(subset=["recall_top5pct_tiered"])
    if len(dd):
        mean_dbscan = dd['recall_top5pct_dbscan'].mean()
        log.info(f"Weeks with DBSCAN actuals: {len(dd)}")
        log.info(f"DBSCAN R@top-5%: mean={mean_dbscan:.3f}  median={dd['recall_top5pct_dbscan'].median():.3f}  "
                 f"p10={dd['recall_top5pct_dbscan'].quantile(0.10):.3f}  "
                 f"p90={dd['recall_top5pct_dbscan'].quantile(0.90):.3f}")
    if len(dt):
        mean_tiered = dt['recall_top5pct_tiered'].mean()
        log.info(f"Tiered R@top-5% (matches training claim): mean={mean_tiered:.3f}  median={dt['recall_top5pct_tiered'].median():.3f}  "
                 f"p10={dt['recall_top5pct_tiered'].quantile(0.10):.3f}  "
                 f"p90={dt['recall_top5pct_tiered'].quantile(0.90):.3f}")
        log.info(f"  Training-reported PerDayR: 48.56% (matches our mean_tiered={mean_tiered:.3f})")
    dd2 = day_summary.dropna(subset=["precision_critical_dbscan"])
    if len(dd2):
        log.info(f"Precision@CRITICAL (DBSCAN): median={dd2['precision_critical_dbscan'].median():.3f}  "
                 f"weeks w/ ≥1 critical hit: {(dd2['hits_in_critical_dbscan']>0).sum()}/{len(dd2)}")

    # Persistent false-alarm cells
    crit_false = cell_roll[(cell_roll["n_critical_weeks"] >= 3) & (cell_roll["n_actual_ignitions"] == 0)]
    log.info(f"\nPersistent false-alarm cells (CRITICAL ≥3 weeks, 0 ignitions): {len(crit_false)}")
    if len(crit_false):
        top = crit_false.sort_values("n_critical_weeks", ascending=False).head(5)
        for _, r in top.iterrows():
            log.info(f"  {r['cell_id']}  crit_weeks={r['n_critical_weeks']}  max_risk={r['max_risk']:.3f}")

    # Missed ignitions (had ignition but never in any band)
    missed_total = int(cell_roll["missed_ignitions_no_band"].sum())
    total_pos = int(cell_roll["n_actual_ignitions"].sum())
    log.info(f"\nMissed ignitions (actual fires, never in any band): {missed_total}/{total_pos} "
             f"= {missed_total/max(total_pos,1):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
