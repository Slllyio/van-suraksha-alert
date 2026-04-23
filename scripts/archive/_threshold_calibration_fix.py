"""
Threshold provenance + calibration fix for the 2026 heatwave statewide run.

Context
-------
Earlier analyses used `risk > 0.5` as a "high risk" cutoff. That was an arbitrary
pick on my part, and it is wrong for operational use. This script:

1. Documents where 0.5 actually came from (training-time sweep default).
2. Shows the prior shift: v6e was trained on a rebalanced 52/48 set but runs on
   a ~0.2% prevalence state, which compresses deployment probabilities.
3. Applies Saerens et al. (2002) prior correction to un-shift the probs.
4. Ranks cells per day and computes top-K% recall with ±6 km tolerance (the
   only metric that actually matters for a fire dispatch UI).
5. Writes a JSON recommendation with the usable operational thresholds.

No synthetic data. Reads only the outputs produced by
mp_statewide_simulation_2026.py.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_lake" / "statewide_2026_heatwave"
PRED_PATH = OUT_DIR / "all_predictions.parquet"
OUT_JSON = OUT_DIR / "threshold_calibration.json"

# Training-set priors recovered from dataset.parquet inspection.
# v6e: 4,650,823 rows / 2,444,420 positives → 0.5256
# v3:  trained without downsampling, scale_pos_weight=200 (near-raw prior)
TRAIN_PRIOR_V6E = 0.5256
TRAIN_PRIOR_V3 = None  # compressed logits; Saerens doesn't apply the same way

# Spatial tolerance for recall (meters). 6 km matches the FIRMS pixel footprint
# blur + 2 km cell granularity uncertainty.
TOLERANCE_M = 6_000
DEG_PER_M = 1.0 / 111_320.0
TOL_DEG = TOLERANCE_M * DEG_PER_M


def saerens_correct(p: np.ndarray, train_prior: float, test_prior: float) -> np.ndarray:
    """Saerens et al. 2002 prior correction.

    p_adj = (p/train) * test / ((p/train)*test + ((1-p)/(1-train))*(1-test))

    Collapses to a sigmoid shift in logit space.
    """
    p = np.clip(p, 1e-9, 1 - 1e-9)
    num = (p / train_prior) * test_prior
    den = num + ((1.0 - p) / (1.0 - train_prior)) * (1.0 - test_prior)
    return num / den


def per_day_topk_recall(
    df: pd.DataFrame,
    risk_col: str,
    k_fracs: list[float],
) -> dict:
    """For each day rank cells by risk, pick top-K%, then count fires within
    `TOLERANCE_M` of any selected cell using a cKDTree Chebyshev query."""
    results: dict[str, dict] = {}
    for frac in k_fracs:
        total_fire = 0
        caught = 0
        day_rows = []
        for day, sub in df.groupby("date"):
            n = len(sub)
            k = max(1, int(round(n * frac)))
            top = sub.nlargest(k, risk_col)
            fires = sub[sub["fire"] > 0]
            n_fire = len(fires)
            if n_fire == 0:
                continue
            # Chebyshev (p=inf) tolerance in degrees ~ square box of 6 km.
            if len(top) > 0:
                tree = cKDTree(top[["lon", "lat"]].to_numpy())
                dists, _ = tree.query(
                    fires[["lon", "lat"]].to_numpy(),
                    k=1,
                    p=float("inf"),
                    distance_upper_bound=TOL_DEG,
                )
                day_caught = int(np.isfinite(dists).sum())
            else:
                day_caught = 0
            total_fire += n_fire
            caught += day_caught
            day_rows.append(
                {
                    "date": str(day),
                    "n_cells": n,
                    "top_k": k,
                    "n_fire": n_fire,
                    "caught": day_caught,
                }
            )
        recall = caught / total_fire if total_fire > 0 else None
        results[f"top_{frac*100:.1f}pct"] = {
            "fraction": frac,
            "total_fire": total_fire,
            "caught": caught,
            "recall": recall,
            "days": day_rows,
        }
    return results


def fire_score_percentile(df: pd.DataFrame, risk_col: str) -> dict:
    """Where do fire cells land in the per-day score distribution?"""
    ranks = []
    for day, sub in df.groupby("date"):
        sub = sub.copy()
        sub["rank_pct"] = sub[risk_col].rank(pct=True)
        fires = sub[sub["fire"] > 0]
        if len(fires) > 0:
            ranks.extend(fires["rank_pct"].tolist())
    if not ranks:
        return {"n": 0}
    arr = np.asarray(ranks)
    return {
        "n_fire_rows": int(len(arr)),
        "mean_percentile": float(arr.mean()),
        "median_percentile": float(np.median(arr)),
        "p25_percentile": float(np.percentile(arr, 25)),
        "p75_percentile": float(np.percentile(arr, 75)),
        "frac_above_p90": float((arr >= 0.90).mean()),
        "frac_above_p95": float((arr >= 0.95).mean()),
        "frac_above_p99": float((arr >= 0.99).mean()),
    }


def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def main() -> int:
    print(f"Loading {PRED_PATH.name} ...")
    df = pd.read_parquet(PRED_PATH)
    print(f"  rows: {len(df):,}  days: {df['date'].nunique()}")

    # Drop the 7-day FIRMS gap (Mar 25 - Mar 31) where there are zero fires
    # regardless of model.
    # The simulation writes columns `risk_v6e_live`, `risk_v3_no_leak`,
    # `actual_fire`, `actual_frp_sum`. Alias to the short names used below.
    df = df.rename(
        columns={
            "risk_v6e_live": "v6e_live_risk",
            "risk_v3_no_leak": "v3_no_leak_risk",
            "actual_fire": "fire",
        }
    )

    valid_days = (
        df.groupby("date")["fire"].sum().loc[lambda s: s > 0].index.tolist()
    )
    df = df[df["date"].isin(valid_days)].reset_index(drop=True)
    print(f"  valid days (fires > 0): {len(valid_days)}")

    report: dict = {
        "inputs": {
            "predictions": str(PRED_PATH.relative_to(ROOT)),
            "n_rows_valid_days": int(len(df)),
            "n_valid_days": len(valid_days),
            "valid_days": [str(d) for d in valid_days],
        },
        "threshold_provenance": {
            "claim_0_5_came_from": "arbitrary choice in earlier ad-hoc analysis",
            "training_default_fallback": 0.5,  # line 2449 of train_predictive_fire_risk.py
            "v6e_best_f1_threshold_training": 0.495,
            "v6e_train_positive_prior": TRAIN_PRIOR_V6E,
            "v6e_train_positive_prior_source": (
                "dataset.parquet @ outputs/predictive_fire_risk/predictive_v6e_live/"
                " — 4,650,823 rows, 2,444,420 positives"
            ),
            "v6e_subsample_neg_train": 10.0,
            "v6e_scale_pos_weight_train": 200.0,
            "v3_best_f1_threshold_training": 0.04,
            "v3_scale_pos_weight_train": 200.0,
            "deployment_positive_prior_estimate": 0.002,
            "prior_shift_ratio_v6e": TRAIN_PRIOR_V6E / 0.002,
            "note": (
                "v6e was trained on a rebalanced 52/48 set. Its raw sigmoid "
                "outputs are calibrated for that distribution. In deployment "
                "the prior is ~0.2% fires — a ~260x prior shift — so raw "
                "probabilities are systematically compressed toward 0. "
                "Using 0.5 in deployment kills recall by construction."
            ),
        },
    }

    # -------------------------------------------------------------------- v6e
    v6_raw = df["v6e_live_risk"].to_numpy()
    v6_adj = saerens_correct(v6_raw, TRAIN_PRIOR_V6E, test_prior=0.002)
    df["v6e_live_risk_adj"] = v6_adj

    fire_mask = df["fire"] > 0
    report["v6e_raw"] = {
        "fire_mean": float(v6_raw[fire_mask].mean()),
        "fire_median": float(np.median(v6_raw[fire_mask])),
        "nonfire_mean": float(v6_raw[~fire_mask].mean()),
        "nonfire_median": float(np.median(v6_raw[~fire_mask])),
        "ratio_mean": float(v6_raw[fire_mask].mean() / v6_raw[~fire_mask].mean()),
        "frac_fire_above_0_5": float((v6_raw[fire_mask] >= 0.5).mean()),
        "frac_fire_above_0_1": float((v6_raw[fire_mask] >= 0.1).mean()),
        "frac_fire_above_0_05": float((v6_raw[fire_mask] >= 0.05).mean()),
    }
    report["v6e_saerens_corrected"] = {
        "fire_mean": float(v6_adj[fire_mask].mean()),
        "fire_median": float(np.median(v6_adj[fire_mask])),
        "nonfire_mean": float(v6_adj[~fire_mask].mean()),
        "nonfire_median": float(np.median(v6_adj[~fire_mask])),
        "ratio_mean": float(
            v6_adj[fire_mask].mean() / max(v6_adj[~fire_mask].mean(), 1e-12)
        ),
        "frac_fire_above_0_5": float((v6_adj[fire_mask] >= 0.5).mean()),
        "frac_fire_above_0_1": float((v6_adj[fire_mask] >= 0.1).mean()),
        "frac_fire_above_0_05": float((v6_adj[fire_mask] >= 0.05).mean()),
    }

    # Percentile rank of fire cells under the raw v6e score (monotone equivalent
    # to the Saerens-adjusted score — rank is invariant to monotonic transforms).
    report["v6e_fire_rank_distribution"] = fire_score_percentile(df, "v6e_live_risk")

    # Per-day top-K% recall at operational fractions.
    report["v6e_per_day_topk"] = per_day_topk_recall(
        df,
        risk_col="v6e_live_risk",
        k_fracs=[0.005, 0.01, 0.02, 0.05, 0.10],
    )

    # --------------------------------------------------------------------- v3
    v3_raw = df["v3_no_leak_risk"].to_numpy()
    report["v3_raw"] = {
        "fire_mean": float(v3_raw[fire_mask].mean()),
        "nonfire_mean": float(v3_raw[~fire_mask].mean()),
        "ratio_mean": float(
            v3_raw[fire_mask].mean() / max(v3_raw[~fire_mask].mean(), 1e-12)
        ),
        "distinct_values": int(len(np.unique(v3_raw))),
        "note": "v3 is a 1-tree stub (confirmed earlier); do not use.",
    }

    # ----------------------------------------------------- recommendation
    # Pick the per-day top-K% that gives >= 50% recall with smallest k.
    v6_topk = report["v6e_per_day_topk"]
    best_k = None
    for key, row in v6_topk.items():
        r = row["recall"]
        if r is not None and r >= 0.50:
            best_k = (key, row)
            break
    if best_k is None:
        best_k = list(v6_topk.items())[-1]

    report["recommendation"] = {
        "operational_mode": "per_day_percentile_rank",
        "reason": (
            "v6e is miscalibrated for deployment (prior-shifted). Fire cells "
            "sit in the top few percent of daily risk but their raw probs stay "
            "below 0.15. Fixed probability thresholds (0.3/0.5/etc.) are "
            "misleading; per-day top-K% ranking is distribution-free and "
            "matches the dispatch workflow of 'send crews to the N highest-"
            "risk beats today'."
        ),
        "primary_operating_point": {
            "rank_fraction": best_k[1]["fraction"],
            "description": f"top {best_k[1]['fraction']*100:.1f}% cells per day",
            "recall_with_6km_tolerance": best_k[1]["recall"],
            "caught_over_total": f"{best_k[1]['caught']}/{best_k[1]['total_fire']}",
        },
        "fallback_fixed_threshold": {
            "saerens_corrected_v6e": 0.5,
            "raw_v6e_equivalent_estimate": float(
                np.percentile(v6_raw[fire_mask], 25)
            ),
            "description": (
                "If you must pick a single probability cutoff on raw v6e "
                "scores, the 25th percentile of fire-cell risks is a sane "
                "lower bound (75% of fires sit above it). Use 0.5 on "
                "Saerens-corrected scores if you want a calibrated cutoff."
            ),
        },
        "do_not_use": {
            "threshold_0_5_on_raw_v6e": "essentially zero recall",
            "v3_no_leak": "1-tree stub, AUC ~0.48",
        },
    }

    OUT_JSON.write_text(json.dumps(sanitize(report), indent=2))
    print(f"\nWrote {OUT_JSON.relative_to(ROOT)}")
    # Compact screen summary
    print("\n=== threshold provenance ===")
    print(f"  v6e train prior:  {TRAIN_PRIOR_V6E:.3f}")
    print(f"  v6e best_f1 thr:  0.495 (training distribution)")
    print(f"  v3  best_f1 thr:  0.04")
    print(f"  fire-cell raw mean v6e:  {v6_raw[fire_mask].mean():.4f}")
    print(f"  non-fire  raw mean v6e:  {v6_raw[~fire_mask].mean():.4f}")
    print(f"  fire-cell Saerens mean:  {v6_adj[fire_mask].mean():.4f}")
    print(f"  non-fire  Saerens mean:  {v6_adj[~fire_mask].mean():.4f}")
    print("\n=== per-day top-K% recall (6 km tolerance) ===")
    for key, row in v6_topk.items():
        r = row["recall"]
        print(
            f"  {key:>12s}: caught {row['caught']}/{row['total_fire']} "
            f"= {r*100:.1f}%" if r is not None else f"  {key}: n/a"
        )
    rec = report["recommendation"]["primary_operating_point"]
    print(
        f"\nRECOMMENDED: {rec['description']} "
        f"-> {rec['recall_with_6km_tolerance']*100:.1f}% recall"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
