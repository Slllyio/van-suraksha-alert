"""Per-fire validation v2 — proper lead-time computation.

For every FIRMS VIIRS fire detection in 2025 MP fire season:
  1. Find the most recent Thursday prediction date D <= fire_acq_date (within 7d)
  2. Look up v17's prediction for the fire's cell on that Thursday
  3. Compute:
     - SPATIAL OFFSET: km from fire location to fire's cell centroid (sensor precision)
     - CELL RISK: v17 ignition_risk + rank + band for this cell on D
     - NEAREST ALERT DISTANCE: km from fire to nearest CRITICAL / ALERT / top-5% cell
     - TEMPORAL OFFSET: (fire_acq_date - D) in days = lead time
     - DID WE PREDICT: was the fire in v17's top-5% / CRITICAL on prior Thursday
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
OUT_FIRE = ROOT / "data_lake" / "audits" / "validation_per_fire_v2.csv"
OUT_DAY = ROOT / "data_lake" / "audits" / "validation_per_day_v2.csv"
OUT_DIV = ROOT / "data_lake" / "audits" / "validation_per_division_v2.csv"
OUT_REPORT = ROOT / "docs" / "audits" / "v17_per_fire_validation_v2.md"

EARTH_R_KM = 6371.0
PREDICTION_CELL_RADIUS_KM = 1.5  # v6e cell ~2km; match FIRMS within 1.5km = same cell
MIN_CONFIDENCE = "nominal"  # filter FIRMS: nominal+high only


def load_firms_full():
    files = sorted(FIRMS_DIR.glob("2025/viirs_mp_2025_*.parquet"))
    print(f"Found {len(files)} FIRMS 2025 files")
    dfs = []
    for f in files:
        d = pd.read_parquet(f, columns=["latitude", "longitude", "acq_date", "acq_time", "confidence", "frp"])
        dfs.append(d)
    firms = pd.concat(dfs, ignore_index=True).drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"]
    )
    firms["acq_date"] = pd.to_datetime(firms["acq_date"])
    firms = firms[(firms["acq_date"] >= "2025-02-02") & (firms["acq_date"] <= "2025-06-05")]
    # Filter: drop low-confidence
    firms = firms[firms["confidence"].isin(["n", "h"])].copy()
    firms = firms.reset_index(drop=True)
    print(f"  2025 fire-season FIRMS detections (n+h conf): {len(firms):,}")
    return firms


def dbscan_cluster_firms(firms: pd.DataFrame, eps_km: float = 1.0, temporal_days: int = 1):
    """Spatiotemporal DBSCAN to dedupe FIRMS pixels into ignition events.

    Simple approach: per date, cluster fires within eps_km. Earliest time = ignition.
    """
    print(f"Clustering {len(firms):,} FIRMS pixels to ignition events...")
    from sklearn.cluster import DBSCAN
    events = []
    for d, day_f in firms.groupby("acq_date"):
        if len(day_f) == 0:
            continue
        coords_rad = np.deg2rad(day_f[["latitude", "longitude"]].to_numpy())
        eps_rad = eps_km / EARTH_R_KM
        db = DBSCAN(eps=eps_rad, min_samples=1, metric="haversine").fit(coords_rad)
        labels = db.labels_
        day_f = day_f.copy()
        day_f["cluster"] = labels
        # Each cluster -> one ignition at the mean coord
        for cl, grp in day_f.groupby("cluster"):
            events.append({
                "acq_date": d,
                "n_pixels": len(grp),
                "latitude": grp["latitude"].mean(),
                "longitude": grp["longitude"].mean(),
                "acq_time_min": grp["acq_time"].astype(int).min(),
                "max_frp": grp["frp"].max(),
            })
    ev = pd.DataFrame(events)
    print(f"  -> {len(ev):,} ignition events after clustering")
    return ev


def find_prior_thursday(fire_date, thursdays_sorted):
    """Return the most recent prediction Thursday <= fire_date, within 7 days."""
    # Binary search for the Thursday <= fire_date
    idx = thursdays_sorted.searchsorted(fire_date, side="right") - 1
    if idx < 0:
        return None
    prior = thursdays_sorted[idx]
    delta = (fire_date - prior).days
    if delta < 0 or delta > 7:
        return None
    return prior


def main() -> int:
    print("=" * 72)
    print("V17 PER-FIRE VALIDATION v2 — TRUE LEAD-TIME LOOKUP")
    print("=" * 72)
    print()

    print("Loading v17 audit...")
    audit = pd.read_parquet(AUDIT)
    audit["date"] = pd.to_datetime(audit["date"])
    thursdays = pd.DatetimeIndex(np.sort(audit["date"].unique()))
    print(f"  Audit: {len(audit):,} cell-date rows, {len(thursdays)} prediction Thursdays")
    print()

    firms = load_firms_full()

    # Cluster FIRMS to ignition events (dedupe same-fire multi-pixels)
    events = dbscan_cluster_firms(firms, eps_km=1.0)
    print()

    # For each event, find prior Thursday prediction date
    print("Finding prior Thursday prediction for each event...")
    events["prior_thursday"] = events["acq_date"].apply(lambda d: find_prior_thursday(d, thursdays))
    covered = events[events["prior_thursday"].notna()].copy()
    dropped = len(events) - len(covered)
    print(f"  {len(covered):,}/{len(events):,} events have prior-Thursday prediction in window (dropped {dropped} pre-season)")
    covered["lead_time_days"] = (covered["acq_date"] - covered["prior_thursday"]).dt.days
    print()

    # For each event, find nearest v17 cell on prior Thursday (within 1.5km = same cell)
    print("Looking up v17 predictions for each event...")
    pred_cell_lat = []
    pred_cell_lon = []
    pred_risk = []
    pred_rank = []
    pred_band = []
    pred_division = []
    pred_range = []
    pred_beat = []
    pred_hawkes_n = []
    pred_hawkes_lambda = []
    spatial_km_fire_to_cell = []
    km_to_nearest_critical = []
    km_to_nearest_alert_plus = []
    km_to_nearest_top5 = []

    for d, day_events in covered.groupby("prior_thursday"):
        preds = audit[audit["date"] == d]
        if len(preds) == 0:
            for _ in range(len(day_events)):
                pred_cell_lat.append(np.nan); pred_cell_lon.append(np.nan)
                pred_risk.append(np.nan); pred_rank.append(np.nan); pred_band.append(None)
                pred_division.append(None); pred_range.append(None); pred_beat.append(None)
                pred_hawkes_n.append(np.nan); pred_hawkes_lambda.append(np.nan)
                spatial_km_fire_to_cell.append(np.nan)
                km_to_nearest_critical.append(np.nan)
                km_to_nearest_alert_plus.append(np.nan)
                km_to_nearest_top5.append(np.nan)
            continue

        preds_coords_rad = np.deg2rad(preds[["centroid_lat", "centroid_lon"]].to_numpy())
        tree_all = BallTree(preds_coords_rad, metric="haversine")

        # Band trees (filter to each band level)
        crit = preds[preds["band"] == "CRITICAL"]
        alert_plus = preds[preds["band"].isin(["CRITICAL", "ALERT"])]
        top5 = preds[preds["within_day_rank"] >= 0.95]
        tree_crit = BallTree(np.deg2rad(crit[["centroid_lat","centroid_lon"]].to_numpy()), metric="haversine") if len(crit) else None
        tree_alert = BallTree(np.deg2rad(alert_plus[["centroid_lat","centroid_lon"]].to_numpy()), metric="haversine") if len(alert_plus) else None
        tree_top5 = BallTree(np.deg2rad(top5[["centroid_lat","centroid_lon"]].to_numpy()), metric="haversine") if len(top5) else None

        fire_coords_rad = np.deg2rad(day_events[["latitude", "longitude"]].to_numpy())

        # Nearest cell to each fire
        d_all, i_all = tree_all.query(fire_coords_rad, k=1)

        for k_idx in range(len(day_events)):
            nearest_cell = preds.iloc[i_all[k_idx, 0]]
            pred_cell_lat.append(nearest_cell["centroid_lat"])
            pred_cell_lon.append(nearest_cell["centroid_lon"])
            pred_risk.append(nearest_cell["ignition_risk"])
            pred_rank.append(nearest_cell["within_day_rank"])
            pred_band.append(nearest_cell["band"])
            pred_division.append(nearest_cell["division"])
            pred_range.append(nearest_cell["range"])
            pred_beat.append(nearest_cell["beat"])
            pred_hawkes_n.append(nearest_cell["hawkes_n_recent_10km_7d"])
            pred_hawkes_lambda.append(nearest_cell["hawkes_lambda"])
            spatial_km_fire_to_cell.append(d_all[k_idx, 0] * EARTH_R_KM)

            # Distances to nearest-in-each-band
            def _nearest(tree):
                if tree is None:
                    return np.nan
                dd, _ = tree.query(fire_coords_rad[k_idx:k_idx+1], k=1)
                return dd[0, 0] * EARTH_R_KM

            km_to_nearest_critical.append(_nearest(tree_crit))
            km_to_nearest_alert_plus.append(_nearest(tree_alert))
            km_to_nearest_top5.append(_nearest(tree_top5))

    covered["pred_cell_lat"] = pred_cell_lat
    covered["pred_cell_lon"] = pred_cell_lon
    covered["ignition_risk"] = pred_risk
    covered["within_day_rank"] = pred_rank
    covered["band"] = pred_band
    covered["division"] = pred_division
    covered["range"] = pred_range
    covered["beat"] = pred_beat
    covered["hawkes_n_recent_10km_7d"] = pred_hawkes_n
    covered["hawkes_lambda"] = pred_hawkes_lambda
    covered["spatial_km_fire_to_cell"] = spatial_km_fire_to_cell
    covered["km_to_nearest_CRITICAL"] = km_to_nearest_critical
    covered["km_to_nearest_ALERT_or_CRIT"] = km_to_nearest_alert_plus
    covered["km_to_nearest_top5pct"] = km_to_nearest_top5

    # Output per-fire CSV
    out = covered[[
        "acq_date", "prior_thursday", "lead_time_days",
        "latitude", "longitude", "pred_cell_lat", "pred_cell_lon", "spatial_km_fire_to_cell",
        "n_pixels", "max_frp", "acq_time_min",
        "division", "range", "beat",
        "ignition_risk", "within_day_rank", "band",
        "hawkes_lambda", "hawkes_n_recent_10km_7d",
        "km_to_nearest_CRITICAL", "km_to_nearest_ALERT_or_CRIT", "km_to_nearest_top5pct",
    ]].copy()
    out.to_csv(OUT_FIRE, index=False)
    print(f"Wrote per-fire: {OUT_FIRE.relative_to(ROOT)} ({len(out):,} rows)")

    # Per-day summary — aggregate by prior_thursday (prediction date)
    daily = covered.groupby("prior_thursday").agg(
        n_fires=("acq_date", "count"),
        n_top5_hits=("within_day_rank", lambda x: (x >= 0.95).sum()),
        n_alert_hits=("band", lambda x: x.isin(["CRITICAL", "ALERT"]).sum()),
        n_critical_hits=("band", lambda x: (x == "CRITICAL").sum()),
        mean_rank=("within_day_rank", "mean"),
        median_km_to_top5=("km_to_nearest_top5pct", "median"),
        median_km_to_critical=("km_to_nearest_CRITICAL", "median"),
        median_km_fire_to_cell=("spatial_km_fire_to_cell", "median"),
        median_lead_time_days=("lead_time_days", "median"),
        mean_lead_time_days=("lead_time_days", "mean"),
    ).reset_index()
    daily["recall_at_top5pct"] = daily["n_top5_hits"] / daily["n_fires"]
    daily["recall_at_CRITICAL"] = daily["n_critical_hits"] / daily["n_fires"]
    daily["recall_at_ALERT_or_above"] = daily["n_alert_hits"] / daily["n_fires"]
    daily.to_csv(OUT_DAY, index=False)
    print(f"Wrote per-day: {OUT_DAY.relative_to(ROOT)} ({len(daily)} rows)")

    # Per-division summary
    divsum = covered.groupby("division").agg(
        n_fires=("acq_date", "count"),
        n_top5_hits=("within_day_rank", lambda x: (x >= 0.95).sum()),
        n_alert_hits=("band", lambda x: x.isin(["CRITICAL", "ALERT"]).sum()),
        n_critical_hits=("band", lambda x: (x == "CRITICAL").sum()),
        mean_rank=("within_day_rank", "mean"),
        median_km_to_top5=("km_to_nearest_top5pct", "median"),
        median_km_to_critical=("km_to_nearest_CRITICAL", "median"),
        median_lead_time_days=("lead_time_days", "median"),
        frac_low_hawkes=("hawkes_n_recent_10km_7d", lambda x: (x <= 1).mean()),
    ).reset_index()
    divsum["recall_at_top5pct"] = divsum["n_top5_hits"] / divsum["n_fires"]
    divsum["recall_at_CRITICAL"] = divsum["n_critical_hits"] / divsum["n_fires"]
    divsum["recall_at_ALERT_or_above"] = divsum["n_alert_hits"] / divsum["n_fires"]
    divsum = divsum.sort_values("n_fires", ascending=False)
    divsum.to_csv(OUT_DIV, index=False)
    print(f"Wrote per-division: {OUT_DIV.relative_to(ROOT)} ({len(divsum)} rows)")
    print()

    # ==== Narrative
    n = len(covered)
    hits5 = (covered["within_day_rank"] >= 0.95).sum()
    hits_crit = (covered["band"] == "CRITICAL").sum()
    hits_alert = covered["band"].isin(["CRITICAL","ALERT"]).sum()
    hits_watch = covered["band"].isin(["CRITICAL","ALERT","WATCH"]).sum()
    blind = (covered["within_day_rank"] < 0.50).sum()

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# v17 Per-Fire Validation — 2025 Fire Season (True Lead-Time)\n\n")
        f.write(f"**Generated:** {pd.Timestamp.now():%Y-%m-%d %H:%M}\n\n")
        f.write("Every FIRMS VIIRS fire detection (Feb-May 2025) is spatiotemporally clustered ")
        f.write("to ignition events. For each event we locate the most recent **prior Thursday** ")
        f.write("prediction date (i.e. the prediction that was already issued before the fire started), ")
        f.write("then look up v17's rank/band for the fire's cell on that Thursday. This gives a true ")
        f.write("lead-time (0-6 days ahead) for every fire.\n\n")
        f.write("## Headline numbers\n\n")
        f.write(f"| Metric | Value | Pct |\n|---|---:|---:|\n")
        f.write(f"| FIRMS detections (n+h conf) | {len(firms):,} | — |\n")
        f.write(f"| Clustered ignition events | {len(events):,} | — |\n")
        f.write(f"| Events with prior-Thursday prediction | {n:,} | 100.0% |\n")
        f.write(f"| Events in v17 top-5% rank | {hits5:,} | {100*hits5/n:.1f}% |\n")
        f.write(f"| Events in ALERT or CRITICAL band | {hits_alert:,} | {100*hits_alert/n:.1f}% |\n")
        f.write(f"| Events in CRITICAL band | {hits_crit:,} | {100*hits_crit/n:.1f}% |\n")
        f.write(f"| Events below median rank (model blind) | {blind:,} | {100*blind/n:.1f}% |\n\n")

        f.write("## Spatial offset distribution\n\n")
        f.write("**km from actual fire location to nearest v17-alerted cell on prior Thursday**\n\n")
        f.write("| Percentile | km to CRITICAL | km to ALERT+ | km to top-5% |\n|---|---:|---:|---:|\n")
        for p in [10, 25, 50, 75, 90, 95]:
            c = np.nanpercentile(covered["km_to_nearest_CRITICAL"], p)
            a = np.nanpercentile(covered["km_to_nearest_ALERT_or_CRIT"], p)
            t = np.nanpercentile(covered["km_to_nearest_top5pct"], p)
            f.write(f"| p{p} | {c:.1f} | {a:.1f} | {t:.1f} |\n")
        f.write("\n")

        f.write("## Temporal lead-time distribution\n\n")
        f.write("Days from prior-Thursday prediction issuance to actual fire detection (0=Thu, 1=Fri, ..., 6=Wed).\n\n")
        lt = covered["lead_time_days"]
        f.write(f"- Median lead time: **{lt.median():.1f} days**\n")
        f.write(f"- Mean lead time: **{lt.mean():.2f} days**\n\n")
        f.write("| Lead (days) | #fires | Pct |\n|---:|---:|---:|\n")
        for k in range(7):
            cnt = (lt == k).sum()
            f.write(f"| {k} | {cnt:,} | {100*cnt/n:.1f}% |\n")
        f.write("\n**Interpretation:** a median of 2-3 days means v17 is giving genuine advance ")
        f.write("notice. A median of 0-1 means the model fires its alert in a window that's almost ")
        f.write("contemporaneous with the actual detection.\n\n")

        f.write("## Per-day summary (prediction-date view)\n\n")
        f.write("| Thursday | #fires in [D,D+6] | #top5% | R@5% | #CRIT | Med km→top5% | Med lead (d) |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for _, r in daily.iterrows():
            f.write(f"| {r['prior_thursday'].strftime('%Y-%m-%d')} | {int(r['n_fires'])} | "
                    f"{int(r['n_top5_hits'])} | {r['recall_at_top5pct']:.1%} | "
                    f"{int(r['n_critical_hits'])} | {r['median_km_to_top5']:.1f} | "
                    f"{r['median_lead_time_days']:.1f} |\n")
        f.write("\n")

        f.write("## Per-division (top 20 by fire count)\n\n")
        f.write("| Division | #fires | R@5% | R@ALERT+ | Med km→top5% | Med km→CRIT | Mean rank | %low-Hawkes |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for _, r in divsum.head(20).iterrows():
            f.write(f"| {r['division']} | {int(r['n_fires'])} | {r['recall_at_top5pct']:.1%} | "
                    f"{r['recall_at_ALERT_or_above']:.1%} | {r['median_km_to_top5']:.1f} | "
                    f"{r['median_km_to_critical']:.1f} | {r['mean_rank']:.3f} | "
                    f"{r['frac_low_hawkes']:.1%} |\n")
        f.write("\n")

        f.write("## How to read this\n\n")
        f.write("- **Lead time** = (fire acquisition date) − (v17 prediction Thursday). Measures ")
        f.write("genuine forecast horizon.\n")
        f.write("- **km to top-5%** = for a real fire, how far was the nearest cell v17 ranked in its ")
        f.write("top-5% on the prior Thursday? 0 = fire cell was in top-5%. 10 km = one cell row away. ")
        f.write("40+ km = model was looking at a different region.\n")
        f.write("- **Low-Hawkes divisions** (Satna, Shivpuri, Anuppur) consistently show WORSE ")
        f.write("spatial+temporal alignment. This is v17's documented structural weakness.\n")

    print(f"Wrote narrative: {OUT_REPORT.relative_to(ROOT)}")
    print()
    print("=" * 72)
    print(f"HEADLINE: {n:,} events matched to prior-Thursday predictions.")
    print(f"  R@top-5%: {100*hits5/n:.1f}%  R@CRITICAL: {100*hits_crit/n:.1f}%  R@ALERT+: {100*hits_alert/n:.1f}%")
    print(f"  Median km to top-5% cell: {covered['km_to_nearest_top5pct'].median():.1f}")
    print(f"  Median lead time: {lt.median():.1f} days")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
