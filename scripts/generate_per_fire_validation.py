"""Per-fire validation of v17 predictions against actual fires.

For every actual fire in the 2025 honest temporal hold-out:
  - Find v17's prediction for its cell on the Thursday prediction date
  - Compute SPATIAL OFFSET: km to nearest CRITICAL / ALERT / top-5% cell
  - Compute TEMPORAL OFFSET: lead time (hours) from prediction issuance to actual acq_datetime
  - Record band, rank, Hawkes context, division

Also spot-check 2026 fire season where v17 predictions exist.

Outputs:
  data_lake/audits/validation_per_fire_2025.csv          # every fire with offsets
  data_lake/audits/validation_per_day_2025.csv           # daily roll-up
  data_lake/audits/validation_per_division_2025.csv      # division roll-up
  docs/audits/v17_per_fire_validation.md                 # narrative report
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.neighbors import BallTree

sys.stdout.reconfigure(line_buffering=True)
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
FIRMS_DIR = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs"
OUT_FIRE = ROOT / "data_lake" / "audits" / "validation_per_fire_2025.csv"
OUT_DAY = ROOT / "data_lake" / "audits" / "validation_per_day_2025.csv"
OUT_DIV = ROOT / "data_lake" / "audits" / "validation_per_division_2025.csv"
OUT_REPORT = ROOT / "docs" / "audits" / "v17_per_fire_validation.md"

EARTH_R_KM = 6371.0


def load_firms_2025():
    """Load 2025 FIRMS VIIRS detections covering Feb-May."""
    files = sorted(FIRMS_DIR.glob("2025/viirs_mp_2025_*.parquet"))
    print(f"Found {len(files)} FIRMS 2025 files")
    dfs = []
    for f in files:
        d = pd.read_parquet(f, columns=["latitude", "longitude", "acq_date", "acq_time", "confidence", "frp"])
        dfs.append(d)
    firms = pd.concat(dfs, ignore_index=True).drop_duplicates()
    firms["acq_date"] = pd.to_datetime(firms["acq_date"])
    firms = firms[(firms["acq_date"] >= "2025-02-02") & (firms["acq_date"] <= "2025-06-05")]
    print(f"  2025 fire-season FIRMS detections: {len(firms):,}")
    return firms


def build_prediction_tree(preds_day: pd.DataFrame, band_filter: str | list[str] | None = None) -> BallTree | None:
    """Build BallTree for predictions on a single day, optionally filtered by band."""
    d = preds_day
    if band_filter is not None:
        if isinstance(band_filter, str):
            d = d[d["band"] == band_filter]
        else:
            d = d[d["band"].isin(band_filter)]
    if len(d) == 0:
        return None, None
    coords_rad = np.deg2rad(d[["centroid_lat", "centroid_lon"]].to_numpy())
    tree = BallTree(coords_rad, metric="haversine")
    return tree, d.reset_index(drop=True)


def main() -> int:
    print("=" * 72)
    print("V17 PER-FIRE VALIDATION — 2025 HONEST TEMPORAL HOLD-OUT")
    print("=" * 72)
    print()

    print("Loading v17 audit (765K cell-date predictions)...")
    audit = pd.read_parquet(AUDIT)
    audit["date"] = pd.to_datetime(audit["date"])
    print(f"  Audit: {len(audit):,} rows, {audit['date'].nunique()} prediction Thursdays")
    print(f"  Date range: {audit['date'].min().date()} to {audit['date'].max().date()}")
    print()

    print("Loading FIRMS 2025 detections...")
    firms = load_firms_2025()
    print()

    # Actual fire cells (from audit)
    fires = audit[audit["label_dbscan_ignition"] == 1].copy()
    print(f"Actual fires in audit window: {len(fires):,}")
    print(f"  Unique prediction Thursdays: {fires['date'].nunique()}")
    print(f"  Unique divisions: {fires['division'].nunique()}")
    print()

    # For each fire cell, look up its actual FIRMS acq_datetime within [D, D+7]
    print("Matching each fire cell to earliest FIRMS detection in [D, D+7d]...")
    fire_coords_rad = np.deg2rad(firms[["latitude", "longitude"]].to_numpy())
    firms_tree = BallTree(fire_coords_rad, metric="haversine")

    fires = fires.reset_index(drop=True)
    actual_dates = []
    actual_lats = []
    actual_lons = []
    actual_frps = []
    spatial_km_to_detection = []

    TOL_RAD = 5.0 / EARTH_R_KM  # 5 km radius for cell-to-FIRMS match
    for i, row in fires.iterrows():
        cell_coord = np.deg2rad([[row["centroid_lat"], row["centroid_lon"]]])
        # Find FIRMS within 5km of this cell
        inds = firms_tree.query_radius(cell_coord, r=TOL_RAD)[0]
        if len(inds) == 0:
            actual_dates.append(pd.NaT)
            actual_lats.append(np.nan); actual_lons.append(np.nan); actual_frps.append(np.nan)
            spatial_km_to_detection.append(np.nan)
            continue
        cand = firms.iloc[inds]
        # Window: [date, date + 7d]
        window = cand[(cand["acq_date"] >= row["date"]) & (cand["acq_date"] <= row["date"] + pd.Timedelta(days=7))]
        if len(window) == 0:
            actual_dates.append(pd.NaT)
            actual_lats.append(np.nan); actual_lons.append(np.nan); actual_frps.append(np.nan)
            spatial_km_to_detection.append(np.nan)
            continue
        # Earliest detection within window
        first = window.sort_values("acq_date").iloc[0]
        actual_dates.append(first["acq_date"])
        actual_lats.append(first["latitude"])
        actual_lons.append(first["longitude"])
        actual_frps.append(first["frp"])
        # Haversine km between cell centroid and FIRMS detection
        lat1, lon1 = np.deg2rad(row["centroid_lat"]), np.deg2rad(row["centroid_lon"])
        lat2, lon2 = np.deg2rad(first["latitude"]), np.deg2rad(first["longitude"])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
        spatial_km_to_detection.append(2 * EARTH_R_KM * np.arcsin(np.sqrt(a)))
        if (i+1) % 500 == 0:
            print(f"  ... matched {i+1}/{len(fires)}")

    fires["actual_acq_date"] = actual_dates
    fires["actual_lat"] = actual_lats
    fires["actual_lon"] = actual_lons
    fires["actual_frp"] = actual_frps
    fires["km_pred_cell_to_firms"] = spatial_km_to_detection
    fires["temporal_offset_days"] = (fires["actual_acq_date"] - fires["date"]).dt.total_seconds() / 86400
    matched = fires["actual_acq_date"].notna().sum()
    print(f"  Matched to FIRMS: {matched:,}/{len(fires):,} ({100*matched/len(fires):.1f}%)")
    print()

    # For each fire, compute SPATIAL OFFSET to nearest CRITICAL/ALERT/WATCH cell that day
    print("Computing spatial offset from each fire to nearest alerted cell on prediction date...")
    dist_to_critical = []
    dist_to_alert = []
    dist_to_watch = []
    dist_to_top5pct = []

    for d, day_fires in fires.groupby("date"):
        preds_day = audit[audit["date"] == d]
        # Trees for each band level
        tree_crit, crit_df = build_prediction_tree(preds_day, "CRITICAL")
        tree_alert, alert_df = build_prediction_tree(preds_day, ["CRITICAL", "ALERT"])
        tree_watch, watch_df = build_prediction_tree(preds_day, ["CRITICAL", "ALERT", "WATCH"])
        # Top-5% rank
        top5 = preds_day[preds_day["within_day_rank"] >= 0.95]
        tree_top5, top5_df = (BallTree(np.deg2rad(top5[["centroid_lat","centroid_lon"]].to_numpy()), metric="haversine"), top5) if len(top5) > 0 else (None, None)

        fire_coords = np.deg2rad(day_fires[["centroid_lat", "centroid_lon"]].to_numpy())

        def nearest_km(tree):
            if tree is None:
                return np.full(len(fire_coords), np.nan)
            dist_rad, _ = tree.query(fire_coords, k=1)
            return dist_rad.ravel() * EARTH_R_KM

        dc = nearest_km(tree_crit)
        da = nearest_km(tree_alert)
        dw = nearest_km(tree_watch)
        dt = nearest_km(tree_top5)

        for idx, i in enumerate(day_fires.index):
            dist_to_critical.append((i, dc[idx]))
            dist_to_alert.append((i, da[idx]))
            dist_to_watch.append((i, dw[idx]))
            dist_to_top5pct.append((i, dt[idx]))

    for col, data in [("km_to_nearest_CRITICAL", dist_to_critical),
                      ("km_to_nearest_ALERT_or_CRIT", dist_to_alert),
                      ("km_to_nearest_WATCH_or_above", dist_to_watch),
                      ("km_to_nearest_top5pct", dist_to_top5pct)]:
        s = pd.Series({i: v for i, v in data})
        fires[col] = s

    print("  Done.\n")

    # Per-fire output (CSV)
    out_fire = fires[[
        "cell_id", "date", "actual_acq_date", "temporal_offset_days",
        "centroid_lat", "centroid_lon", "actual_lat", "actual_lon", "actual_frp",
        "km_pred_cell_to_firms",
        "division", "range", "beat",
        "ignition_risk", "within_day_rank", "band",
        "hawkes_lambda", "hawkes_n_recent_10km_7d",
        "best_tier",
        "km_to_nearest_CRITICAL", "km_to_nearest_ALERT_or_CRIT",
        "km_to_nearest_WATCH_or_above", "km_to_nearest_top5pct",
    ]].copy()
    out_fire["prediction_date"] = out_fire["date"]
    out_fire.drop(columns=["date"], inplace=True)
    cols_first = ["prediction_date", "actual_acq_date", "temporal_offset_days"]
    out_fire = out_fire[cols_first + [c for c in out_fire.columns if c not in cols_first]]
    out_fire.to_csv(OUT_FIRE, index=False)
    print(f"Wrote per-fire validation: {OUT_FIRE.relative_to(ROOT)} ({len(out_fire):,} rows)")

    # Per-day summary
    daily = fires.groupby("date").agg(
        n_fires=("cell_id", "count"),
        n_critical_hits=("band", lambda x: (x == "CRITICAL").sum()),
        n_alert_hits=("band", lambda x: (x.isin(["CRITICAL","ALERT"])).sum()),
        n_watch_hits=("band", lambda x: (x.isin(["CRITICAL","ALERT","WATCH"])).sum()),
        n_top5pct_hits=("within_day_rank", lambda x: (x >= 0.95).sum()),
        median_rank=("within_day_rank", "median"),
        mean_rank=("within_day_rank", "mean"),
        median_km_to_CRITICAL=("km_to_nearest_CRITICAL", "median"),
        median_km_to_ALERT=("km_to_nearest_ALERT_or_CRIT", "median"),
        median_km_to_top5pct=("km_to_nearest_top5pct", "median"),
        median_temporal_offset_days=("temporal_offset_days", "median"),
        median_hawkes_n=("hawkes_n_recent_10km_7d", "median"),
    ).reset_index()
    daily["recall_at_top5pct"] = daily["n_top5pct_hits"] / daily["n_fires"]
    daily["recall_at_CRITICAL"] = daily["n_critical_hits"] / daily["n_fires"]
    daily["recall_at_ALERT_or_above"] = daily["n_alert_hits"] / daily["n_fires"]
    daily.to_csv(OUT_DAY, index=False)
    print(f"Wrote per-day summary: {OUT_DAY.relative_to(ROOT)} ({len(daily)} rows)")

    # Per-division summary
    divsum = fires.groupby("division").agg(
        n_fires=("cell_id", "count"),
        n_critical_hits=("band", lambda x: (x == "CRITICAL").sum()),
        n_alert_hits=("band", lambda x: (x.isin(["CRITICAL","ALERT"])).sum()),
        n_top5pct_hits=("within_day_rank", lambda x: (x >= 0.95).sum()),
        mean_rank=("within_day_rank", "mean"),
        median_km_to_top5pct=("km_to_nearest_top5pct", "median"),
        median_km_to_CRITICAL=("km_to_nearest_CRITICAL", "median"),
        median_hawkes_n=("hawkes_n_recent_10km_7d", "median"),
        frac_low_hawkes=("hawkes_n_recent_10km_7d", lambda x: (x <= 1).mean()),
    ).reset_index()
    divsum["recall_at_top5pct"] = divsum["n_top5pct_hits"] / divsum["n_fires"]
    divsum["recall_at_CRITICAL"] = divsum["n_critical_hits"] / divsum["n_fires"]
    divsum["recall_at_ALERT_or_above"] = divsum["n_alert_hits"] / divsum["n_fires"]
    divsum = divsum.sort_values("n_fires", ascending=False)
    divsum.to_csv(OUT_DIV, index=False)
    print(f"Wrote per-division summary: {OUT_DIV.relative_to(ROOT)} ({len(divsum)} rows)")
    print()

    # Narrative report
    print("Writing narrative report...")
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# v17 Per-Fire Validation — 2025 Fire Season Hold-Out\n\n")
        f.write(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Window:** {fires['date'].min().date()} to {fires['date'].max().date()} ")
        f.write(f"({fires['date'].nunique()} prediction Thursdays)\n\n")
        f.write("Every FIRMS DBSCAN ignition that occurred within 7 days of each v17 prediction date ")
        f.write("is matched to the model's output for its cell. We report (a) how confident v17 was ")
        f.write("(band + within-day rank), (b) how far away the nearest CRITICAL / ALERT / top-5% ")
        f.write("cell was in km, and (c) the temporal lead-time from prediction issuance to actual ")
        f.write("fire detection.\n\n")

        f.write("## Headline numbers\n\n")
        n_fires = len(fires)
        n_matched = fires["actual_acq_date"].notna().sum()
        n_crit = (fires["band"] == "CRITICAL").sum()
        n_alert = fires["band"].isin(["CRITICAL","ALERT"]).sum()
        n_watch = fires["band"].isin(["CRITICAL","ALERT","WATCH"]).sum()
        n_top5 = (fires["within_day_rank"] >= 0.95).sum()
        n_miss_blind = (fires["within_day_rank"] < 0.50).sum()
        f.write(f"| Metric | Count | Pct |\n|---|---:|---:|\n")
        f.write(f"| Total actual fires (DBSCAN ignitions) | {n_fires:,} | 100.0% |\n")
        f.write(f"| Matched to FIRMS acq_datetime | {n_matched:,} | {100*n_matched/n_fires:.1f}% |\n")
        f.write(f"| Flagged CRITICAL | {n_crit:,} | {100*n_crit/n_fires:.1f}% |\n")
        f.write(f"| Flagged ALERT or above | {n_alert:,} | {100*n_alert/n_fires:.1f}% |\n")
        f.write(f"| Flagged WATCH or above | {n_watch:,} | {100*n_watch/n_fires:.1f}% |\n")
        f.write(f"| In top 5% rank | {n_top5:,} | {100*n_top5/n_fires:.1f}% |\n")
        f.write(f"| Below median rank (model blind) | {n_miss_blind:,} | {100*n_miss_blind/n_fires:.1f}% |\n\n")

        f.write("## Spatial offset distribution\n\n")
        f.write("Distance from each actual fire cell to nearest alerted cell on the prediction date.\n\n")
        f.write("| Percentile | km to CRITICAL | km to ALERT+ | km to top-5% |\n|---|---:|---:|---:|\n")
        for p in [10, 25, 50, 75, 90, 95]:
            c = np.nanpercentile(fires["km_to_nearest_CRITICAL"], p)
            a = np.nanpercentile(fires["km_to_nearest_ALERT_or_CRIT"], p)
            t = np.nanpercentile(fires["km_to_nearest_top5pct"], p)
            f.write(f"| p{p} | {c:.1f} | {a:.1f} | {t:.1f} |\n")
        f.write("\n")

        f.write("## Temporal offset distribution\n\n")
        f.write("Lead time from v17's prediction Thursday to the actual FIRMS detection. ")
        f.write("Negative = fire detected BEFORE prediction (shouldn't happen if pipeline correct); ")
        f.write("0-7 days = within-window; the 7-day forecast horizon.\n\n")
        valid_t = fires["temporal_offset_days"].dropna()
        f.write(f"- Matches with timestamp: **{len(valid_t):,}**\n")
        f.write(f"- Median lead time: **{valid_t.median():.1f} days**\n")
        f.write(f"- Mean lead time: **{valid_t.mean():.1f} days**\n")
        f.write(f"- p10 / p25 / p50 / p75 / p90: "
                f"{valid_t.quantile(0.10):.1f} / {valid_t.quantile(0.25):.1f} / "
                f"{valid_t.quantile(0.50):.1f} / {valid_t.quantile(0.75):.1f} / "
                f"{valid_t.quantile(0.90):.1f} days\n\n")

        f.write("## Per-day summary\n\n")
        f.write("| Date | #fires | #top5% | Recall@5% | #CRIT | Med km→CRIT | Med km→top5% |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for _, r in daily.iterrows():
            f.write(f"| {r['date'].strftime('%Y-%m-%d')} | {int(r['n_fires'])} | "
                    f"{int(r['n_top5pct_hits'])} | {r['recall_at_top5pct']:.1%} | "
                    f"{int(r['n_critical_hits'])} | {r['median_km_to_CRITICAL']:.1f} | "
                    f"{r['median_km_to_top5pct']:.1f} |\n")
        f.write("\n")

        f.write("## Top-20 divisions by fire count\n\n")
        f.write("| Division | #fires | R@5% | R@ALERT+ | Med km→top5% | Mean rank | % low-Hawkes |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for _, r in divsum.head(20).iterrows():
            f.write(f"| {r['division']} | {int(r['n_fires'])} | {r['recall_at_top5pct']:.1%} | "
                    f"{r['recall_at_ALERT_or_above']:.1%} | {r['median_km_to_top5pct']:.1f} | "
                    f"{r['mean_rank']:.3f} | {r['frac_low_hawkes']:.1%} |\n")
        f.write("\n")

        f.write("## How to read this\n\n")
        f.write("- **km to CRITICAL** = for a given actual fire, how far away was the nearest cell ")
        f.write("v17 flagged CRITICAL? 0 = the fire cell itself was CRITICAL. >20 km = model was looking ")
        f.write("at a different region entirely.\n")
        f.write("- **Temporal offset (days)** = positive lead time. v17 issues Thursday; fire detected ")
        f.write("N days later. If median is 2-4 days the model is giving usable advance notice. If it's ")
        f.write("close to 0 or negative, v17 is reacting, not predicting.\n")
        f.write("- **Recall@5%** varies wildly by division because Hawkes self-excitation dominates. ")
        f.write("Divisions with recent fire activity get tight spatial/temporal offsets; quiet ")
        f.write("divisions with sudden outbreaks are frequently missed.\n\n")

    print(f"Wrote narrative: {OUT_REPORT.relative_to(ROOT)}")
    print()
    print("=" * 72)
    print("HEADLINE: Per-fire validation complete.")
    print(f"  Total fires: {n_fires}, in top-5%: {n_top5} ({100*n_top5/n_fires:.1f}%)")
    print(f"  Median km to top-5% cell: {fires['km_to_nearest_top5pct'].median():.1f}")
    print(f"  Median lead time: {valid_t.median():.1f} days")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
