"""Generate brutal audit figures for v17 per-week audit on 2025 hold-out.

Reads:
  data_lake/audits/v17_audit_per_day_summary.parquet
  data_lake/audits/v17_audit_per_cell_date.parquet
  data_lake/audits/v17_audit_per_cell_season.parquet

Outputs:
  docs/audits/figures/A*.png  (8 brutal figures)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "data_lake" / "audits"
FIG_DIR = ROOT / "docs" / "audits" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({
    "figure.dpi": 140, "savefig.dpi": 150, "font.size": 11,
    "axes.titleweight": "bold", "axes.titlesize": 12,
})

TRAINING_CLAIM_PERDAYR = 0.4856
TRAINING_CLAIM_RTOP5 = 0.4741


def fig_A1_perweek_recall():
    """A1: Per-week R@top-5% BOTH label definitions + training claim line."""
    day = pd.read_parquet(AUDITS / "v17_audit_per_day_summary.parquet")
    day["date"] = pd.to_datetime(day["date"])
    fig, ax = plt.subplots(figsize=(12, 5.5))
    x = day["date"]
    ax.plot(x, day["recall_top5pct_tiered"] * 100, marker="o", lw=2, label="R@top-5% (BA-tiered labels, training-style)")
    ax.plot(x, day["recall_top5pct_dbscan"] * 100, marker="s", lw=2, color="#d62626",
            label="R@top-5% (DBSCAN labels, strict operational)")
    ax.axhline(TRAINING_CLAIM_PERDAYR * 100, color="#1f77b4", ls="--", alpha=0.7,
               label=f"Training claim: PerDayR = {TRAINING_CLAIM_PERDAYR*100:.1f}%")
    ax.axhline(day["recall_top5pct_dbscan"].mean() * 100, color="#d62626", ls=":", alpha=0.7,
               label=f"DBSCAN season mean: {day['recall_top5pct_dbscan'].mean()*100:.1f}%")
    ax.set_ylabel("R @ top-5% (%)")
    ax.set_xlabel("Prediction Thursday (2025 hold-out)")
    ax.set_title("A1 — Per-week R@top-5% reveals 17pp gap between training claim and strict-label reality")
    ax.set_ylim(0, 75)
    ax.legend(loc="lower left", framealpha=0.9)
    for i, (d, r) in enumerate(zip(day["date"], day["recall_top5pct_dbscan"])):
        if r < 0.15:
            ax.annotate(f"{r*100:.0f}%", (d, r * 100), textcoords="offset points",
                        xytext=(0, -15), ha="center", fontsize=9, color="#d62626", fontweight="bold")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A1_perweek_recall.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A1 saved")


def fig_A2_precision_critical():
    """A2: Precision at CRITICAL band per week — the 2% reality."""
    day = pd.read_parquet(AUDITS / "v17_audit_per_day_summary.parquet")
    day["date"] = pd.to_datetime(day["date"])
    fig, ax = plt.subplots(figsize=(12, 5.5))
    x = day["date"]
    ax.bar(x, day["precision_critical_dbscan"] * 100, width=5, color="#d62626", alpha=0.7, label="CRITICAL precision (DBSCAN)")
    ax.bar(x, day["precision_top5pct_dbscan"] * 100, width=5, color="#ff7f0e", alpha=0.5, label="Top-5% precision (DBSCAN)")
    ax.set_ylabel("Precision (%)")
    ax.set_xlabel("Prediction Thursday")
    ax.set_title("A2 — CRITICAL-band precision hovers around 2% \u2014 98% of our most-urgent alerts never ignite")
    ax.axhline(5, color="#555", ls=":", alpha=0.5, label="5% baseline (top-5% = random guess ceiling)")
    ax.legend(loc="upper right")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A2_precision_critical.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A2 saved")


def fig_A3_band_vs_ignitions():
    """A3: Stacked bars — ignitions by band per week, showing how many we caught in which band."""
    per_cell = pd.read_parquet(AUDITS / "v17_audit_per_cell_date.parquet")
    per_cell["date"] = pd.to_datetime(per_cell["date"])
    # For each date, count ignitions in each band
    hits = per_cell[per_cell["label_dbscan_ignition"] == 1].copy()
    by_date_band = hits.groupby(["date", "band"]).size().unstack(fill_value=0)
    for col in ("NONE", "WATCH", "ALERT", "CRITICAL"):
        if col not in by_date_band.columns:
            by_date_band[col] = 0
    by_date_band = by_date_band[["NONE", "WATCH", "ALERT", "CRITICAL"]]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    dates = by_date_band.index
    bottom = np.zeros(len(dates))
    colors = {"NONE": "#999", "WATCH": "#facc15", "ALERT": "#ea580c", "CRITICAL": "#b91c1c"}
    for band in ["NONE", "WATCH", "ALERT", "CRITICAL"]:
        vals = by_date_band[band].values
        ax.bar(dates, vals, bottom=bottom, width=5, label=f"{band} ({vals.sum()} total)",
               color=colors[band], edgecolor="white", linewidth=0.5)
        bottom += vals
    ax.set_ylabel("Actual DBSCAN ignitions that week")
    ax.set_xlabel("Prediction Thursday")
    ax.set_title("A3 — Where did actual ignitions land? Most fell in NONE band (77% missed)")
    ax.legend(loc="upper left", framealpha=0.9)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A3_band_vs_ignitions.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A3 saved")


def fig_A4_perweek_variance_distribution():
    """A4: Distribution of per-week R@top-5% as violin — shows the variance brutally."""
    day = pd.read_parquet(AUDITS / "v17_audit_per_day_summary.parquet")
    fig, ax = plt.subplots(figsize=(9, 6))
    data = [
        day["recall_top5pct_dbscan"].dropna() * 100,
        day["recall_top5pct_tiered"].dropna() * 100,
    ]
    parts = ax.violinplot(data, positions=[0, 1], widths=0.8, showmeans=True, showmedians=True)
    for pc, color in zip(parts['bodies'], ["#d62626", "#1f77b4"]):
        pc.set_facecolor(color); pc.set_alpha(0.5)
    # Individual points
    for i, d in enumerate(data):
        ax.scatter([i] * len(d) + np.random.normal(0, 0.05, len(d)), d, color="black", s=20, alpha=0.6)
    ax.axhline(TRAINING_CLAIM_PERDAYR * 100, color="#1f77b4", ls="--", alpha=0.7, label=f"Training PerDayR claim {TRAINING_CLAIM_PERDAYR*100:.1f}%")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["DBSCAN (strict)", "BA-tiered (training)"])
    ax.set_ylabel("R @ top-5% per week (%)")
    ax.set_title("A4 — Per-week recall distribution. DBSCAN median 30.3%, range 7.3\u201357.8%")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A4_variance_distribution.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A4 saved")


def fig_A5_persistent_false_alarms():
    """A5: Chronic false-alarm cells — map + histogram."""
    cell_roll = pd.read_parquet(AUDITS / "v17_audit_per_cell_season.parquet")
    per_cell = pd.read_parquet(AUDITS / "v17_audit_per_cell_date.parquet")
    coords = per_cell.groupby("cell_id")[["centroid_lat", "centroid_lon"]].first().reset_index()
    cell_roll = cell_roll.merge(coords, on="cell_id", how="left")

    false_crit = cell_roll[(cell_roll["n_critical_weeks"] >= 3) & (cell_roll["n_actual_ignitions"] == 0)]
    true_crit = cell_roll[(cell_roll["n_critical_weeks"] >= 3) & (cell_roll["n_actual_ignitions"] >= 1)]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    ax = axes[0]
    ax.scatter(cell_roll["centroid_lon"], cell_roll["centroid_lat"], s=2, color="lightgray", alpha=0.3, label="All 42K MP cells")
    ax.scatter(false_crit["centroid_lon"], false_crit["centroid_lat"], s=20, color="#d62626",
               label=f"False-alarm (CRITICAL \u22653 weeks, 0 igns): {len(false_crit)}")
    ax.scatter(true_crit["centroid_lon"], true_crit["centroid_lat"], s=15, color="#2ca02c",
               label=f"True-alarm (CRITICAL \u22653 weeks, \u22651 ign): {len(true_crit)}")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_title("A5a \u2014 Geography of chronic CRITICAL alerts (red = false, green = true)")
    ax.legend(loc="lower right", framealpha=0.9, fontsize=9)

    ax = axes[1]
    bins = np.arange(0, 20, 1)
    ax.hist(false_crit["n_critical_weeks"], bins=bins, color="#d62626", alpha=0.7, label=f"False alarmers ({len(false_crit)})")
    ax.hist(true_crit["n_critical_weeks"], bins=bins, color="#2ca02c", alpha=0.7, label=f"True alarmers ({len(true_crit)})")
    ax.set_xlabel("CRITICAL weeks in season (0-18)"); ax.set_ylabel("# cells")
    ax.set_title("A5b \u2014 CRITICAL-week persistence: 5 cells hit CRITICAL all 18 weeks with ZERO ignitions")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A5_false_alarms.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A5 saved")


def fig_A6_missed_fire_map():
    """A6: Where did actual ignitions fall but model missed them?"""
    per_cell = pd.read_parquet(AUDITS / "v17_audit_per_cell_date.parquet")
    fires = per_cell[per_cell["label_dbscan_ignition"] == 1].copy()
    caught = fires[fires["band"] != "NONE"]
    missed = fires[fires["band"] == "NONE"]
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.scatter(per_cell.groupby("cell_id")["centroid_lon"].first(),
               per_cell.groupby("cell_id")["centroid_lat"].first(),
               s=0.5, color="lightgray", alpha=0.2, label="All cells (42K)")
    ax.scatter(missed["centroid_lon"], missed["centroid_lat"], s=18, color="#d62626", alpha=0.5,
               label=f"Missed: {len(missed)} ignitions (NONE band)")
    ax.scatter(caught["centroid_lon"], caught["centroid_lat"], s=18, color="#2ca02c", alpha=0.8,
               label=f"Caught: {len(caught)} ignitions (any band)")
    miss_rate = len(missed) / max(len(fires), 1)
    ax.set_title(f"A6 \u2014 Spatial audit: {len(missed)}/{len(fires)} ({miss_rate:.1%}) of 2025 ignitions NOT in any band on ignition week")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.legend(loc="upper left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A6_missed_fire_map.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A6 saved")


def fig_A7_hawkes_dependency():
    """A7: Risk-score vs actual-ignition by Hawkes intensity bin."""
    per_cell = pd.read_parquet(AUDITS / "v17_audit_per_cell_date.parquet")
    per_cell["hawkes_bin"] = pd.cut(per_cell["hawkes_n_recent_10km_7d"],
                                     bins=[-0.1, 0, 1, 3, 10, 100], labels=["0", "1", "2-3", "4-10", "10+"])
    grp = per_cell.groupby("hawkes_bin", observed=False).agg(
        n_cells=("cell_id", "count"),
        n_ignitions=("label_dbscan_ignition", "sum"),
        mean_risk=("ignition_risk", "mean"),
        mean_rank=("within_day_rank", "mean"),
    ).reset_index()
    grp["ignition_rate"] = grp["n_ignitions"] / grp["n_cells"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    ax = axes[0]
    ax.bar(grp["hawkes_bin"].astype(str), grp["mean_risk"], color="#1f77b4", alpha=0.8, label="Mean v17 risk")
    ax2 = ax.twinx()
    ax2.plot(grp["hawkes_bin"].astype(str), grp["ignition_rate"] * 100, "o-", color="#d62626", lw=2, label="Actual ignition rate")
    ax.set_xlabel("Hawkes recent-10km-7d count")
    ax.set_ylabel("Mean v17 risk", color="#1f77b4")
    ax2.set_ylabel("Ignition rate (%)", color="#d62626")
    ax.set_title("A7a \u2014 v17 risk tracks Hawkes count closely; model is effectively a Hawkes detector")
    ax = axes[1]
    ax.bar(grp["hawkes_bin"].astype(str), grp["n_cells"] / 1000, color="#666", alpha=0.7)
    ax.set_xlabel("Hawkes recent-10km-7d count")
    ax.set_ylabel("# cell-dates (thousands)")
    ax.set_title("A7b \u2014 Most cells have 0 recent-Hawkes ignitions \u2014 Hawkes is sparse signal")
    for i, row in grp.iterrows():
        ax.text(i, row["n_cells"] / 1000, f'{row["n_ignitions"]} ign', ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A7_hawkes_dependency.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A7 saved")


def fig_A8_rank_calibration():
    """A8: Calibration plot \u2014 predicted rank vs empirical hit rate."""
    per_cell = pd.read_parquet(AUDITS / "v17_audit_per_cell_date.parquet")
    per_cell["rank_bin"] = pd.cut(per_cell["within_day_rank"],
                                    bins=np.arange(0, 1.05, 0.05), labels=[f"{i*5}-{(i+1)*5}" for i in range(20)])
    grp = per_cell.groupby("rank_bin", observed=False).agg(
        n=("cell_id", "count"),
        hits=("label_dbscan_ignition", "sum"),
    ).reset_index()
    grp["hit_rate"] = grp["hits"] / grp["n"]
    grp["rank_midpoint"] = [(i + 0.5) * 5 for i in range(20)]

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(grp["rank_midpoint"], grp["hit_rate"] * 100, width=4, color="#1f77b4", alpha=0.75, edgecolor="#222")
    for i, row in grp.iterrows():
        if row["hit_rate"] > 0.001:
            ax.text(row["rank_midpoint"], row["hit_rate"] * 100, f"{row['hit_rate']*100:.1f}%",
                    ha="center", va="bottom", fontsize=8)
    # Bands
    ax.axvspan(95, 98, alpha=0.15, color="yellow", label="WATCH (95-98%)")
    ax.axvspan(98, 99.5, alpha=0.25, color="orange", label="ALERT (98-99.5%)")
    ax.axvspan(99.5, 100, alpha=0.35, color="red", label="CRITICAL (\u226599.5%)")
    ax.set_xlabel("Within-day rank percentile (%)")
    ax.set_ylabel("Empirical DBSCAN ignition rate (%)")
    ax.set_title("A8 \u2014 Calibration: does rank percentile predict actual ignition? (Ideal = monotonic increasing)")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.set_xlim(0, 100); ax.set_ylim(0, ax.get_ylim()[1])
    fig.tight_layout()
    fig.savefig(FIG_DIR / "A8_rank_calibration.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  A8 saved")


def main() -> int:
    log.info("Generating 8 audit figures \u2192 %s", FIG_DIR.relative_to(ROOT))
    np.random.seed(42)
    fig_A1_perweek_recall()
    fig_A2_precision_critical()
    fig_A3_band_vs_ignitions()
    fig_A4_perweek_variance_distribution()
    fig_A5_persistent_false_alarms()
    fig_A6_missed_fire_map()
    fig_A7_hawkes_dependency()
    fig_A8_rank_calibration()
    pngs = sorted(FIG_DIR.glob("A*.png"))
    log.info("\n%d figures saved:", len(pngs))
    for p in pngs:
        log.info("  %s (%.0f KB)", p.name, p.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
