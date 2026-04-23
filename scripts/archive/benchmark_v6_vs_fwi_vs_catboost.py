"""
benchmark_v6_vs_fwi_vs_catboost.py
===================================
One-file, no-narrative benchmark: VanAagni V6 vs FWI vs CatBoost-v6e-live
on a temporal hold-out from the already-built v6e_live dataset.

Why this design:
  - v6e_live/dataset.parquet has the exact 92-feature matrix the trained
    CatBoost expects, plus `label`, `date`, `t_slope_mean`, `wx_vpd`, `wx_fwi`.
  - Training cutoff is 2025-05-29. We hold out the LAST two months
    (2025-03-01 to 2025-04-30, fire season peak) for a temporal split.
  - CatBoost sees this window in training => its AUC is an UPPER bound.
    If V6 even approaches it, V6 is worth calibrating. If it cannot beat
    FWI alone, V6 is dead.

Outputs ROC-AUC, PR-AUC, base rate. Nothing else.

Usage:
    python scripts/benchmark_v6_vs_fwi_vs_catboost.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "dataset.parquet"
MODEL = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "model_catboost.cbm"

TEST_START = "2025-03-01"
TEST_END = "2025-04-30"

# V6 constants as Gemini wrote them (run_vanaagni_production.py)
V6_MAX_SLOPE = 90.0
V6_MAX_VPD = 4.0
V6_W_SLOPE = 0.75
V6_W_VPD = 0.25
V6_ALPHA_K = 5.0
V6_ALPHA_MID = 3.0
V6_BOOST = 0.40
V6_SLOPE_FLOOR = 0.15
V6_VPD_FLOOR = 0.85


def v6_risk(slope: np.ndarray, vpd: np.ndarray) -> np.ndarray:
    normalized_slope = slope / V6_MAX_SLOPE
    v_hat = vpd / V6_MAX_VPD
    alpha = 1.0 / (1.0 + np.exp(-V6_ALPHA_K * (vpd - V6_ALPHA_MID)))
    v_hat_boosted = v_hat + (V6_BOOST * alpha * (v_hat ** 2))
    slope_component = (V6_W_SLOPE * (1 - alpha) + V6_SLOPE_FLOOR * alpha) * normalized_slope
    vpd_component = (V6_W_VPD * (1 - alpha) + V6_VPD_FLOOR * alpha) * v_hat_boosted
    return slope_component + vpd_component


def v6_fixed_risk(slope: np.ndarray, vpd: np.ndarray) -> np.ndarray:
    """V6 with MP-appropriate normalization constants."""
    max_slope = 15.0   # 99th pct of MP forest slope ~ 13°
    max_vpd = 5.5      # 99th pct of fire-season VPD
    mid_vpd = 4.0      # shift alpha midpoint up so it does not fire at median
    normalized_slope = np.clip(slope / max_slope, 0, 1)
    v_hat = np.clip(vpd / max_vpd, 0, 1)
    alpha = 1.0 / (1.0 + np.exp(-V6_ALPHA_K * (vpd - mid_vpd)))
    v_hat_boosted = v_hat + (V6_BOOST * alpha * (v_hat ** 2))
    slope_component = (V6_W_SLOPE * (1 - alpha) + V6_SLOPE_FLOOR * alpha) * normalized_slope
    vpd_component = (V6_W_VPD * (1 - alpha) + V6_VPD_FLOOR * alpha) * v_hat_boosted
    return slope_component + vpd_component


def score(name: str, y_true: np.ndarray, y_score: np.ndarray, base_rate: float) -> dict:
    return {
        "model": name,
        "roc_auc": roc_auc_score(y_true, y_score),
        "pr_auc": average_precision_score(y_true, y_score),
        "skill_vs_base": average_precision_score(y_true, y_score) - base_rate,
    }


def main() -> None:
    if not DATASET.exists():
        raise SystemExit(f"dataset missing: {DATASET}")
    if not MODEL.exists():
        raise SystemExit(f"catboost model missing: {MODEL}")

    print(f"loading dataset: {DATASET}")
    df = pd.read_parquet(DATASET)
    print(f"  full shape: {df.shape}")

    mask = (df["date"] >= TEST_START) & (df["date"] <= TEST_END)
    test = df.loc[mask].reset_index(drop=True)
    print(f"  test window {TEST_START} .. {TEST_END}: {len(test):,} rows")

    y = test["label"].to_numpy().astype(np.int8)
    base_rate = float(y.mean())
    print(f"  fire base rate: {base_rate:.4f} ({y.sum():,}/{len(y):,})")
    print()

    # ── Feature inspection: is V6's /90 slope normalization actually broken? ──
    slope = test["t_slope_mean"].to_numpy()
    vpd = test["wx_vpd"].to_numpy()
    print("sanity check: actual MP slope distribution in test window")
    print(f"  slope  p50={np.percentile(slope,50):.2f}  p95={np.percentile(slope,95):.2f}  p99={np.percentile(slope,99):.2f}  max={slope.max():.2f}")
    print(f"  vpd    p50={np.percentile(vpd,50):.2f}  p95={np.percentile(vpd,95):.2f}  p99={np.percentile(vpd,99):.2f}  max={vpd.max():.2f}")
    print()

    # ── V6 as Gemini wrote it ──
    v6 = v6_risk(slope, vpd)
    print(f"v6 risk: p50={np.percentile(v6,50):.3f}  p95={np.percentile(v6,95):.3f}  max={v6.max():.3f}  saturated>=0.99: {(v6>=0.99).sum():,}")

    # ── V6 with sane constants ──
    v6f = v6_fixed_risk(slope, vpd)
    print(f"v6-fixed: p50={np.percentile(v6f,50):.3f}  p95={np.percentile(v6f,95):.3f}  max={v6f.max():.3f}")
    print()

    # ── CatBoost (upper-bound: model saw this window in training) ──
    print("loading catboost model...")
    from catboost import CatBoostClassifier
    cb = CatBoostClassifier()
    cb.load_model(str(MODEL))
    feat_cols = [c for c in test.columns if c not in ("cell_id", "date", "label")]
    cb_proba = cb.predict_proba(test[feat_cols])[:, 1]
    print(f"  catboost scored {len(cb_proba):,} rows on {len(feat_cols)} features")
    print()

    # ── Scores ──
    rows = [
        score("V6 (Gemini constants)", y, v6, base_rate),
        score("V6-fixed (MP-scaled)", y, v6f, base_rate),
        score("V6 slope-only", y, slope, base_rate),
        score("V6 vpd-only", y, vpd, base_rate),
        score("FWI (wx_fwi)", y, test["wx_fwi"].to_numpy(), base_rate),
        score("FFMC (wx_ffmc)", y, test["wx_ffmc"].to_numpy(), base_rate),
        score("VPD 7d max (wx_vpd_7d_max)", y, test["wx_vpd_7d_max"].to_numpy(), base_rate),
        score("days_since_last_fire (inv)", y, -test["days_since_last_fire"].to_numpy(), base_rate),
        score("CatBoost v6e-live (UPPER BOUND)", y, cb_proba, base_rate),
    ]

    out = pd.DataFrame(rows).sort_values("roc_auc", ascending=False).reset_index(drop=True)
    print("=" * 78)
    print(f"BENCHMARK: {TEST_START} to {TEST_END} | n={len(y):,} | base rate={base_rate:.3f}")
    print("=" * 78)
    print(out.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("=" * 78)
    print()
    print("Interpretation:")
    print("  - ROC-AUC 0.5 = random.  PR-AUC < base_rate = worse than guessing.")
    print("  - CatBoost is an UPPER BOUND (leakage). Any V6 variant < FWI is dead.")
    print("  - Gemini's V6 had 513 rows saturated at 1.0 in the 2026 audit.")

    out_csv = ROOT / "outputs" / "predictive_fire_risk" / "benchmark_v6_vs_fwi_vs_catboost.csv"
    out.to_csv(out_csv, index=False)
    print(f"\nwrote: {out_csv}")


if __name__ == "__main__":
    main()
