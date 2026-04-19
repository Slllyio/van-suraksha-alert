"""Calibrate v17 ignition_risk probabilities so they reflect true ignition rates.

LightGBM raw scores are well-ranked but mis-calibrated as probabilities. After
calibration, P(ignition | score=p) ≈ p, so downstream consumers (alert budget,
trust tiers, dispatch decisions) can trust the magnitude, not just the rank.

Approach: fit two calibrators on a held-out half of the audit parquet, evaluate
both on the other half, ship the one with lower Brier score.

Outputs:
  outputs/predictive_fire_risk/predictive_v17_ba_pu/calibration.json
    {method, slope, intercept (sigmoid) or knot_x/knot_y (isotonic), brier, n}
  outputs/predictive_fire_risk/predictive_v17_ba_pu/calibration_curve.json
    reliability diagram data for the portal
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu"
OUT_CALIB = OUT_DIR / "calibration.json"
OUT_CURVE = OUT_DIR / "calibration_curve.json"
N_BINS = 15


def fit_platt(scores: np.ndarray, labels: np.ndarray) -> dict:
    """Sigmoid calibration: P(y=1) = 1 / (1 + exp(-(a*s + b))).

    Equivalent to Logistic Regression on a single feature (the score).
    """
    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=200)
    lr.fit(scores.reshape(-1, 1), labels)
    return {
        "method": "platt_sigmoid",
        "slope": float(lr.coef_[0, 0]),
        "intercept": float(lr.intercept_[0]),
    }


def apply_platt(scores: np.ndarray, params: dict) -> np.ndarray:
    z = params["slope"] * scores + params["intercept"]
    return 1.0 / (1.0 + np.exp(-z))


def fit_isotonic(scores: np.ndarray, labels: np.ndarray) -> tuple[dict, IsotonicRegression]:
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(scores, labels)
    return {
        "method": "isotonic",
        "knot_x": iso.X_thresholds_.tolist(),
        "knot_y": iso.y_thresholds_.tolist(),
    }, iso


def apply_isotonic_from_knots(scores: np.ndarray, params: dict) -> np.ndarray:
    """Reconstruct calibration via numpy interp from saved knots."""
    return np.interp(scores, params["knot_x"], params["knot_y"])


def reliability_data(scores: np.ndarray, labels: np.ndarray, n_bins: int = N_BINS) -> dict:
    frac_pos, mean_pred = calibration_curve(labels, scores, n_bins=n_bins, strategy="quantile")
    bin_counts, bin_edges = np.histogram(scores, bins=n_bins)
    return {
        "n_bins": n_bins,
        "mean_predicted": [float(x) for x in mean_pred],
        "fraction_positive": [float(x) for x in frac_pos],
        "bin_counts": [int(x) for x in bin_counts],
        "bin_edges": [float(x) for x in bin_edges],
    }


def main() -> int:
    if not AUDIT.exists():
        log.error("audit missing: %s", AUDIT); return 1

    log.info("Loading audit (raw v17 scores + DBSCAN labels)...")
    a = pd.read_parquet(AUDIT, columns=["date", "ignition_risk", "label_dbscan_ignition"])
    a["date"] = pd.to_datetime(a["date"])
    a = a.dropna(subset=["ignition_risk", "label_dbscan_ignition"])
    log.info("  %d rows, %d positives (rate %.3f%%)",
             len(a), int(a["label_dbscan_ignition"].sum()),
             100 * a["label_dbscan_ignition"].mean())

    # Time-based split: first half of season as calibration set, second half as held-out
    median_date = a["date"].quantile(0.5)
    cal_mask = a["date"] <= median_date
    cal = a[cal_mask].copy()
    val = a[~cal_mask].copy()
    log.info("  Calibration set: %d rows (date <= %s)", len(cal), median_date.date())
    log.info("  Validation set:  %d rows (date >  %s)", len(val), median_date.date())

    cal_scores = cal["ignition_risk"].to_numpy(dtype=np.float64)
    cal_labels = cal["label_dbscan_ignition"].to_numpy(dtype=np.int8)
    val_scores = val["ignition_risk"].to_numpy(dtype=np.float64)
    val_labels = val["label_dbscan_ignition"].to_numpy(dtype=np.int8)

    # Baseline: uncalibrated brier
    base_brier = float(brier_score_loss(val_labels, val_scores))
    base_logloss = float(log_loss(val_labels, np.clip(val_scores, 1e-12, 1 - 1e-12)))
    log.info("\nBaseline (no calibration) on val:")
    log.info("  Brier = %.5f  LogLoss = %.5f  mean_pred=%.4f  rate=%.4f",
             base_brier, base_logloss, val_scores.mean(), val_labels.mean())

    # Platt
    log.info("\nFitting Platt sigmoid calibration on cal set...")
    platt = fit_platt(cal_scores, cal_labels)
    val_pred_platt = apply_platt(val_scores, platt)
    platt_brier = float(brier_score_loss(val_labels, val_pred_platt))
    platt_logloss = float(log_loss(val_labels, np.clip(val_pred_platt, 1e-12, 1 - 1e-12)))
    log.info("  slope=%+.3f intercept=%+.3f  Brier=%.5f  LogLoss=%.5f",
             platt["slope"], platt["intercept"], platt_brier, platt_logloss)

    # Isotonic
    log.info("\nFitting Isotonic calibration on cal set...")
    iso_params, _ = fit_isotonic(cal_scores, cal_labels)
    val_pred_iso = apply_isotonic_from_knots(val_scores, iso_params)
    iso_brier = float(brier_score_loss(val_labels, val_pred_iso))
    iso_logloss = float(log_loss(val_labels, np.clip(val_pred_iso, 1e-12, 1 - 1e-12)))
    log.info("  knots=%d  Brier=%.5f  LogLoss=%.5f",
             len(iso_params["knot_x"]), iso_brier, iso_logloss)

    # Pick winner
    if iso_brier < platt_brier:
        winner = iso_params
        winner["brier"] = iso_brier
        winner["logloss"] = iso_logloss
        winner_pred = val_pred_iso
        log.info("\n=> ISOTONIC wins on Brier (%.5f vs Platt %.5f)", iso_brier, platt_brier)
    else:
        winner = platt
        winner["brier"] = platt_brier
        winner["logloss"] = platt_logloss
        winner_pred = val_pred_platt
        log.info("\n=> PLATT wins on Brier (%.5f vs Isotonic %.5f)", platt_brier, iso_brier)

    winner["fitted_at"] = datetime.utcnow().isoformat()
    winner["n_calibration"] = int(len(cal))
    winner["n_validation"] = int(len(val))
    winner["baseline_brier"] = base_brier
    winner["baseline_logloss"] = base_logloss
    winner["candidate_results"] = {
        "platt": {"brier": platt_brier, "logloss": platt_logloss},
        "isotonic": {"brier": iso_brier, "logloss": iso_logloss},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CALIB.write_text(json.dumps(winner, indent=2))
    log.info("Wrote: %s", OUT_CALIB.relative_to(ROOT))

    # Reliability diagram pre + post
    rel_pre = reliability_data(val_scores, val_labels)
    rel_post = reliability_data(winner_pred, val_labels)
    OUT_CURVE.write_text(json.dumps({
        "method": winner["method"],
        "n_bins": N_BINS,
        "before_calibration": rel_pre,
        "after_calibration": rel_post,
    }, indent=2))
    log.info("Wrote: %s", OUT_CURVE.relative_to(ROOT))

    # Sample table
    log.info("\nSample raw -> calibrated mapping:")
    for raw in [0.01, 0.05, 0.1, 0.2, 0.5, 0.8, 0.95, 0.99]:
        if winner["method"] == "isotonic":
            cal_p = float(np.interp(raw, winner["knot_x"], winner["knot_y"]))
        else:
            cal_p = float(1.0 / (1.0 + np.exp(-(winner["slope"] * raw + winner["intercept"]))))
        log.info("  raw %.3f -> calibrated %.4f", raw, cal_p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
