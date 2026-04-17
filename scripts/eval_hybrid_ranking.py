"""Stage 1: Hybrid Bayesian Ranking — adaptive λ blending of global + local CDF.

For each cell i in division d:
    R_final(i,d) = λ_d · Φ_global(S_i) + (1-λ_d) · Φ_local(S_i | d)

Where λ_d = sigmoid(k · z_d), z_d = (mean_score_d_today - baseline_mean_d) / baseline_std_d.

- Division in outlier fire event → λ→1 → trust global rank (don't suppress legit alerts)
- Division in quiet week → λ→0 → trust local rank (elevate subtle anomalies)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit as sigmoid
from sklearn.metrics import roc_auc_score

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
BASELINE_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "division_baselines.json"


def build_division_baselines(audit: pd.DataFrame) -> dict:
    """Compute per-division baseline mean+std of daily mean scores.

    Uses leave-one-out across val dates: for each date, baseline is computed
    from the OTHER dates. This prevents leakage.
    """
    per_div_date = audit.groupby(["division", "date"])["ignition_risk"].mean().reset_index()
    per_div_date.columns = ["division", "date", "daily_mean"]

    baselines = {}
    for div in per_div_date["division"].unique():
        sub = per_div_date[per_div_date["division"] == div]
        baselines[div] = {
            "mean": float(sub["daily_mean"].mean()),
            "std": float(sub["daily_mean"].std()),
            "n_dates": int(len(sub)),
            "n_cells_per_date": int(len(audit[audit["division"] == div]) / max(len(sub), 1)),
        }
    return baselines


def compute_hybrid_rank(audit: pd.DataFrame, baselines: dict, k: float = 2.0) -> pd.Series:
    """Compute R_final = λ_d · Φ_global + (1-λ_d) · Φ_local for each row."""
    result = pd.Series(np.zeros(len(audit)), index=audit.index)

    for date, day_group in audit.groupby("date"):
        phi_global = day_group["ignition_risk"].rank(pct=True)

        for div, div_group in day_group.groupby("division"):
            phi_local = div_group["ignition_risk"].rank(pct=True)

            bl = baselines.get(div, {"mean": 0.1, "std": 0.05})
            div_mean_today = div_group["ignition_risk"].mean()
            std = max(bl["std"], 1e-6)
            z_d = (div_mean_today - bl["mean"]) / std
            lambda_d = float(sigmoid(k * z_d))

            r_final = lambda_d * phi_global.loc[div_group.index] + (1 - lambda_d) * phi_local
            result.loc[div_group.index] = r_final

    return result


def evaluate(audit: pd.DataFrame, rank_col: str, label_col: str, top_pct: float = 0.95) -> dict:
    """Compute R@top-5%, per-day R@5%, precision at bands."""
    top = audit[audit[rank_col] >= top_pct]
    total_ign = int(audit[label_col].sum())
    caught = int(top[label_col].sum())
    r_at_5 = caught / total_ign if total_ign else 0

    per_day = []
    for d, g in audit.groupby("date"):
        t = g[g[rank_col] >= top_pct]
        ti = int(g[label_col].sum())
        ci = int(t[label_col].sum())
        if ti > 0:
            per_day.append(ci / ti)
    mean_pdr = float(np.mean(per_day)) if per_day else 0
    std_pdr = float(np.std(per_day)) if per_day else 0

    low_h = audit[audit["hawkes_n_recent_10km_7d"] <= 1]
    low_top = low_h[low_h[rank_col] >= top_pct]
    low_total = int(low_h[label_col].sum())
    low_caught = int(low_top[label_col].sum())
    low_r = low_caught / low_total if low_total else 0

    return {
        "R_at_5pct": r_at_5,
        "caught": caught,
        "total": total_ign,
        "perday_mean": mean_pdr,
        "perday_std": std_pdr,
        "low_hawkes_R_at_5pct": low_r,
        "low_hawkes_caught": low_caught,
        "low_hawkes_total": low_total,
    }


def main() -> int:
    log.info("=== HYBRID BAYESIAN RANKING EVALUATION ===\n")

    audit = pd.read_parquet(AUDIT_PATH)
    audit["date"] = pd.to_datetime(audit["date"])
    log.info("Loaded %d rows, %d dates, %d divisions",
             len(audit), audit["date"].nunique(), audit["division"].nunique())

    # Build baselines
    baselines = build_division_baselines(audit)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        json.dump(baselines, f, indent=2)
    log.info("Saved division baselines to %s (%d divisions)", BASELINE_PATH.name, len(baselines))

    # Evaluate STATEWIDE ranking (current v17 behavior)
    log.info("\n--- STATEWIDE ranking (current v17) ---")
    statewide = evaluate(audit, "within_day_rank", "label_dbscan_ignition")
    log.info("  R@5%%: %.4f (%d/%d)", statewide["R_at_5pct"], statewide["caught"], statewide["total"])
    log.info("  PerDay R@5%%: %.4f ± %.4f", statewide["perday_mean"], statewide["perday_std"])
    log.info("  Low-Hawkes R@5%%: %.4f (%d/%d)", statewide["low_hawkes_R_at_5pct"],
             statewide["low_hawkes_caught"], statewide["low_hawkes_total"])

    # Evaluate PURE LOCAL ranking (naive per-division — the flawed approach)
    log.info("\n--- PURE LOCAL ranking (per-division, naive) ---")
    audit["local_rank"] = audit.groupby(["date", "division"])["ignition_risk"].rank(pct=True)
    local = evaluate(audit, "local_rank", "label_dbscan_ignition")
    log.info("  R@5%%: %.4f (%d/%d)", local["R_at_5pct"], local["caught"], local["total"])
    log.info("  PerDay R@5%%: %.4f ± %.4f", local["perday_mean"], local["perday_std"])
    log.info("  Low-Hawkes R@5%%: %.4f (%d/%d)", local["low_hawkes_R_at_5pct"],
             local["low_hawkes_caught"], local["low_hawkes_total"])

    # Evaluate HYBRID ranking at different k values
    for k in [1.0, 1.5, 2.0, 3.0, 5.0]:
        log.info("\n--- HYBRID ranking (k=%.1f) ---", k)
        audit[f"hybrid_rank_k{k}"] = compute_hybrid_rank(audit, baselines, k=k)
        hybrid = evaluate(audit, f"hybrid_rank_k{k}", "label_dbscan_ignition")
        log.info("  R@5%%: %.4f (%d/%d)", hybrid["R_at_5pct"], hybrid["caught"], hybrid["total"])
        log.info("  PerDay R@5%%: %.4f ± %.4f", hybrid["perday_mean"], hybrid["perday_std"])
        log.info("  Low-Hawkes R@5%%: %.4f (%d/%d)", hybrid["low_hawkes_R_at_5pct"],
                 hybrid["low_hawkes_caught"], hybrid["low_hawkes_total"])

    # Summary comparison
    log.info("\n=== SUMMARY ===")
    log.info("%-25s  R@5%%   PerDay  LowH_R@5%%  PerDay_std", "Method")
    log.info("%-25s  %.3f  %.3f   %.3f       %.3f", "Statewide (current)",
             statewide["R_at_5pct"], statewide["perday_mean"],
             statewide["low_hawkes_R_at_5pct"], statewide["perday_std"])
    log.info("%-25s  %.3f  %.3f   %.3f       %.3f", "Pure Local (naive)",
             local["R_at_5pct"], local["perday_mean"],
             local["low_hawkes_R_at_5pct"], local["perday_std"])
    for k in [1.0, 1.5, 2.0, 3.0, 5.0]:
        h = evaluate(audit, f"hybrid_rank_k{k}", "label_dbscan_ignition")
        log.info("%-25s  %.3f  %.3f   %.3f       %.3f", f"Hybrid k={k}",
                 h["R_at_5pct"], h["perday_mean"],
                 h["low_hawkes_R_at_5pct"], h["perday_std"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
