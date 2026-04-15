"""Task 1 — v17 threshold sweep to find operationally-meaningful band boundaries.

Current calibration (99.5% CRITICAL, 98% ALERT, 95% WATCH) was inherited from
v15's spread task (52% positive rate). v17 operates on ignition task (0.47%
positive rate) so thresholds are mis-scaled — CRITICAL has 3% precision.

This script sweeps rank percentiles and finds "best" thresholds by multiple
criteria, outputs the Pareto frontier.

Reads:
  data_lake/audits/v17_audit_per_cell_date.parquet (from audit_v17_per_week.py)

Writes:
  data_lake/audits/v17_threshold_sweep.parquet
  docs/audits/figures/T1_pr_frontier.png
  docs/audits/figures/T2_f1_curves.png
  docs/audits/figures/T3_operational_bands.png
"""
from __future__ import annotations

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
AUDIT_PCD = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
OUT_SWEEP = ROOT / "data_lake" / "audits" / "v17_threshold_sweep.parquet"
FIG_DIR = ROOT / "docs" / "audits" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({"figure.dpi": 140, "savefig.dpi": 150, "font.size": 11, "axes.titleweight": "bold"})

THRESHOLDS_PCT = [50, 60, 70, 80, 85, 90, 92, 93, 94, 95, 96, 97, 97.5, 98, 98.5, 99, 99.5, 99.8]


def compute_threshold_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """For each threshold, compute per-week metrics + aggregate summary."""
    rows = []
    for t in THRESHOLDS_PCT:
        t_frac = t / 100.0
        alert_mask = df["within_day_rank"] >= t_frac
        alerts = df[alert_mask]
        n_alerts_per_week = alerts.groupby("date").size().mean()

        # DBSCAN label
        per_week = df.groupby("date").apply(
            lambda s: pd.Series({
                "n_cells": len(s),
                "n_alerts": int((s["within_day_rank"] >= t_frac).sum()),
                "n_positives_dbscan": int(s["label_dbscan_ignition"].sum()),
                "n_positives_tiered": int(s["label_tiered_any"].sum()),
                "hits_dbscan": int(((s["within_day_rank"] >= t_frac) & (s["label_dbscan_ignition"] == 1)).sum()),
                "hits_tiered": int(((s["within_day_rank"] >= t_frac) & (s["label_tiered_any"] == 1)).sum()),
            }),
            include_groups=False,
        ).reset_index()
        per_week["recall_dbscan"] = per_week["hits_dbscan"] / per_week["n_positives_dbscan"].replace(0, np.nan)
        per_week["recall_tiered"] = per_week["hits_tiered"] / per_week["n_positives_tiered"].replace(0, np.nan)
        per_week["precision_dbscan"] = per_week["hits_dbscan"] / per_week["n_alerts"].replace(0, np.nan)
        per_week["precision_tiered"] = per_week["hits_tiered"] / per_week["n_alerts"].replace(0, np.nan)
        per_week["f1_dbscan"] = 2 * per_week["recall_dbscan"] * per_week["precision_dbscan"] / (
            (per_week["recall_dbscan"] + per_week["precision_dbscan"]).replace(0, np.nan))

        total_pos_d = per_week["n_positives_dbscan"].sum()
        total_pos_t = per_week["n_positives_tiered"].sum()
        total_hits_d = per_week["hits_dbscan"].sum()
        total_hits_t = per_week["hits_tiered"].sum()
        total_alerts = per_week["n_alerts"].sum()

        rows.append({
            "threshold_pct": t,
            "n_alerts_per_week_mean": float(n_alerts_per_week),
            "n_alerts_total": int(total_alerts),
            # Aggregate (season-wide)
            "recall_dbscan_agg": total_hits_d / total_pos_d if total_pos_d else None,
            "precision_dbscan_agg": total_hits_d / total_alerts if total_alerts else None,
            "recall_tiered_agg": total_hits_t / total_pos_t if total_pos_t else None,
            "precision_tiered_agg": total_hits_t / total_alerts if total_alerts else None,
            "f1_dbscan_agg": (
                2 * (total_hits_d / total_pos_d) * (total_hits_d / total_alerts)
                / ((total_hits_d / total_pos_d) + (total_hits_d / total_alerts))
                if total_alerts and total_pos_d and (total_hits_d / total_pos_d + total_hits_d / total_alerts) > 0
                else None
            ),
            # Per-week medians (robust to outliers)
            "recall_dbscan_median": per_week["recall_dbscan"].median(),
            "precision_dbscan_median": per_week["precision_dbscan"].median(),
            "recall_dbscan_p10": per_week["recall_dbscan"].quantile(0.10),
            "recall_dbscan_p90": per_week["recall_dbscan"].quantile(0.90),
            "f1_dbscan_median": per_week["f1_dbscan"].median(),
        })
    return pd.DataFrame(rows)


def find_operational_thresholds(sweep: pd.DataFrame) -> dict:
    """Pick CRITICAL/ALERT/WATCH based on operational goals."""
    d = sweep.sort_values("threshold_pct", ascending=False).reset_index(drop=True)

    # CRITICAL: first threshold where precision_dbscan_agg >= 0.10
    crit_candidates = d[d["precision_dbscan_agg"] >= 0.10]
    crit = crit_candidates.iloc[-1] if len(crit_candidates) else d.iloc[0]  # highest-precision if none meet 10%

    # ALERT: threshold where recall_dbscan_agg >= 0.40 (catch 40% of fires)
    alert_candidates = d[d["recall_dbscan_agg"] >= 0.40]
    alert = alert_candidates.iloc[0] if len(alert_candidates) else d.iloc[-1]  # lowest threshold if none meet 40%

    # WATCH: threshold where recall_dbscan_agg >= 0.70 (catch 70% of fires)
    watch_candidates = d[d["recall_dbscan_agg"] >= 0.70]
    watch = watch_candidates.iloc[0] if len(watch_candidates) else d.iloc[-1]

    # F1-optimal
    d_valid = d.dropna(subset=["f1_dbscan_agg"])
    f1_optimal = d_valid.loc[d_valid["f1_dbscan_agg"].idxmax()] if len(d_valid) else d.iloc[0]

    return {
        "CRITICAL_new": {
            "threshold_pct": float(crit["threshold_pct"]),
            "precision_dbscan": float(crit["precision_dbscan_agg"]),
            "recall_dbscan": float(crit["recall_dbscan_agg"]),
            "n_alerts_per_week": float(crit["n_alerts_per_week_mean"]),
            "criterion": "first where DBSCAN precision >= 10%",
        },
        "ALERT_new": {
            "threshold_pct": float(alert["threshold_pct"]),
            "precision_dbscan": float(alert["precision_dbscan_agg"]),
            "recall_dbscan": float(alert["recall_dbscan_agg"]),
            "n_alerts_per_week": float(alert["n_alerts_per_week_mean"]),
            "criterion": "threshold where DBSCAN recall >= 40%",
        },
        "WATCH_new": {
            "threshold_pct": float(watch["threshold_pct"]),
            "precision_dbscan": float(watch["precision_dbscan_agg"]),
            "recall_dbscan": float(watch["recall_dbscan_agg"]),
            "n_alerts_per_week": float(watch["n_alerts_per_week_mean"]),
            "criterion": "threshold where DBSCAN recall >= 70%",
        },
        "F1_optimal": {
            "threshold_pct": float(f1_optimal["threshold_pct"]),
            "f1_dbscan": float(f1_optimal["f1_dbscan_agg"]),
            "precision_dbscan": float(f1_optimal["precision_dbscan_agg"]),
            "recall_dbscan": float(f1_optimal["recall_dbscan_agg"]),
        },
    }


def plot_pr_frontier(sweep: pd.DataFrame, ops: dict):
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.plot(sweep["recall_dbscan_agg"] * 100, sweep["precision_dbscan_agg"] * 100,
            "o-", color="#d62626", lw=2, label="DBSCAN labels (strict ignition)")
    ax.plot(sweep["recall_tiered_agg"] * 100, sweep["precision_tiered_agg"] * 100,
            "s-", color="#1f77b4", lw=2, label="BA-tiered labels (training target)")
    for _, r in sweep.iterrows():
        ax.annotate(f"{r['threshold_pct']:.0f}%", (r["recall_dbscan_agg"] * 100, r["precision_dbscan_agg"] * 100),
                    textcoords="offset points", xytext=(5, -5), fontsize=8, color="#d62626")
    # Mark current calibration
    for band_name, cal_t in [("CRITICAL (99.5%)", 99.5), ("ALERT (98%)", 98), ("WATCH (95%)", 95)]:
        cur = sweep[abs(sweep["threshold_pct"] - cal_t) < 0.01]
        if len(cur):
            c = cur.iloc[0]
            ax.scatter([c["recall_dbscan_agg"] * 100], [c["precision_dbscan_agg"] * 100],
                       color="#ff9500", s=200, marker="*", edgecolor="black", linewidth=1.5,
                       label=f"CURRENT {band_name}", zorder=5)
    # Mark proposed operational thresholds
    for name, info in ops.items():
        if name == "F1_optimal":
            continue
        ax.scatter([info["recall_dbscan"] * 100], [info["precision_dbscan"] * 100],
                   color="#2ca02c", s=200, marker="^", edgecolor="black", linewidth=1.5,
                   label=f"PROPOSED {name} @{info['threshold_pct']:.1f}%", zorder=5)
    ax.axhline(10, color="#888", ls="--", alpha=0.5, label="10% precision line (operational utility)")
    ax.axvline(50, color="#888", ls=":", alpha=0.5, label="50% recall line")
    ax.set_xlabel("Recall (% of actual ignitions caught)")
    ax.set_ylabel("Precision (% of alerts that are real)")
    ax.set_title("T1 — Precision-Recall frontier across rank percentile thresholds\n"
                 "Current CRITICAL is stuck in low-recall / low-precision dead zone")
    ax.set_xlim(-2, 110)
    ax.set_ylim(-0.5, max(sweep["precision_dbscan_agg"].max() * 110, 15))
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "T1_pr_frontier.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  T1 saved")


def plot_f1_curves(sweep: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(sweep["threshold_pct"], sweep["f1_dbscan_agg"], "o-", color="#d62626", lw=2, label="Aggregate F1 (DBSCAN)")
    ax.plot(sweep["threshold_pct"], sweep["f1_dbscan_median"], "s--", color="#d62626", lw=1.5, alpha=0.6,
            label="Median per-week F1 (DBSCAN)")
    ax.axvline(99.5, color="#ff9500", ls="--", alpha=0.7, label="Current CRITICAL (99.5%)")
    ax.axvline(95, color="#1f77b4", ls="--", alpha=0.7, label="Current WATCH (95%)")
    # Highlight F1 optimum
    best_idx = sweep["f1_dbscan_agg"].idxmax()
    best = sweep.loc[best_idx]
    ax.scatter([best["threshold_pct"]], [best["f1_dbscan_agg"]], s=200, marker="*", color="#2ca02c",
               edgecolor="black", linewidth=1.5, zorder=5, label=f"F1-optimal @{best['threshold_pct']:.1f}%")
    ax.set_xlabel("Rank percentile threshold")
    ax.set_ylabel("F1 (DBSCAN labels)")
    ax.set_title("T2 — F1 score across thresholds: F1-optimum is MUCH lower than current CRITICAL")
    ax.legend(loc="upper left")
    ax.invert_xaxis()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "T2_f1_curves.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  T2 saved")


def plot_operational_bands(sweep: pd.DataFrame, ops: dict):
    fig, ax = plt.subplots(figsize=(12, 6))
    # precision + recall vs threshold
    x = sweep["threshold_pct"].values
    ax.plot(x, sweep["recall_dbscan_agg"] * 100, "o-", lw=2, color="#d62626", label="Recall (DBSCAN)")
    ax.plot(x, sweep["precision_dbscan_agg"] * 100, "s-", lw=2, color="#1f77b4", label="Precision (DBSCAN)")
    # Proposed bands
    for name, info, color in [
        ("PROPOSED WATCH", ops["WATCH_new"], "#facc15"),
        ("PROPOSED ALERT", ops["ALERT_new"], "#ea580c"),
        ("PROPOSED CRITICAL", ops["CRITICAL_new"], "#b91c1c"),
    ]:
        ax.axvline(info["threshold_pct"], ls="--", color=color, alpha=0.8, lw=2,
                   label=f"{name} @{info['threshold_pct']:.1f}% (R={info['recall_dbscan']:.0%}, P={info['precision_dbscan']:.0%})")
    # Current bands
    for cal_t, label in [(99.5, "current CRITICAL"), (98, "current ALERT"), (95, "current WATCH")]:
        ax.axvline(cal_t, ls=":", color="gray", alpha=0.5)
    ax.set_xlabel("Rank percentile threshold")
    ax.set_ylabel("% (recall or precision)")
    ax.set_title("T3 — Proposed operational bands vs current mis-calibrated bands")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=9)
    ax.invert_xaxis()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "T3_operational_bands.png", bbox_inches="tight")
    plt.close(fig)
    log.info("  T3 saved")


def main() -> int:
    log.info("Loading per-cell-date audit...")
    df = pd.read_parquet(AUDIT_PCD)
    df["date"] = pd.to_datetime(df["date"])
    log.info("  %d rows, %d weeks", len(df), df["date"].nunique())

    log.info("Computing metrics for %d threshold candidates...", len(THRESHOLDS_PCT))
    sweep = compute_threshold_metrics(df)
    OUT_SWEEP.parent.mkdir(parents=True, exist_ok=True)
    sweep.to_parquet(OUT_SWEEP, index=False)
    log.info("Saved: %s", OUT_SWEEP.relative_to(ROOT))

    log.info("\n=== THRESHOLD SWEEP RESULTS (DBSCAN aggregate) ===")
    log.info(f"{'thr%':>5} {'n_alerts/wk':>12} {'Recall':>8} {'Prec':>8} {'F1':>8} {'Prec_tier':>10}")
    for _, r in sweep.iterrows():
        log.info(f"{r['threshold_pct']:>5.1f} {r['n_alerts_per_week_mean']:>12.0f} "
                 f"{r['recall_dbscan_agg']*100:>7.1f}% {r['precision_dbscan_agg']*100:>7.1f}% "
                 f"{(r['f1_dbscan_agg'] or 0)*100:>7.1f}% {r['precision_tiered_agg']*100:>9.1f}%")

    ops = find_operational_thresholds(sweep)
    log.info("\n=== PROPOSED OPERATIONAL BANDS ===")
    for name, info in ops.items():
        log.info(f"  {name}: threshold={info['threshold_pct']:.1f}%  "
                 f"R_dbscan={info.get('recall_dbscan', 0):.1%}  "
                 f"P_dbscan={info.get('precision_dbscan', 0):.1%}  "
                 f"{info.get('criterion', '')}")

    log.info("\nGenerating figures...")
    plot_pr_frontier(sweep, ops)
    plot_f1_curves(sweep)
    plot_operational_bands(sweep, ops)

    # Save ops recommendation as JSON
    import json
    ops_json = ROOT / "data_lake" / "audits" / "v17_proposed_thresholds.json"
    ops_json.write_text(json.dumps(ops, indent=2))
    log.info("Saved: %s", ops_json.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
