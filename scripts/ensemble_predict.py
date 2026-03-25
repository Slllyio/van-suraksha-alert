"""
scripts/ensemble_predict.py
============================
Ensemble Prediction -- Grid-Based Predictive Fire Risk.

Auto-discovers trained LightGBM models in outputs/predictive_fire_risk/,
runs each on the same target date, and combines predictions using a
configurable ensemble strategy to produce a final per-cell risk map.

Usage:
    # Predict tomorrow (auto-select top-3 predictive_* models by test AUC)
    python scripts/ensemble_predict.py --predict 2026-03-27

    # Specify models explicitly
    python scripts/ensemble_predict.py --predict 2026-03-27 \\
        --models predictive_v3_gridded predictive_v3_no_leak

    # Use rank-average strategy
    python scripts/ensemble_predict.py --predict 2026-03-27 --strategy rank_avg

    # List available models and their metrics
    python scripts/ensemble_predict.py --list
"""

# ── PROJ/GDAL env fix (must precede other imports) ──────────────────────────
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from src.utils.proj_fix import setup_proj_env; setup_proj_env()
del _os, _sys
# ────────────────────────────────────────────────────────────────────────────

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PRED_DIR = ROOT / "outputs" / "predictive_fire_risk"

# Risk level thresholds (must match train_predictive_fire_risk.py)
RISK_THRESHOLDS = {
    "CRITICAL": 0.45,
    "HIGH":     0.25,
    "MODERATE": 0.10,
    "LOW":      0.00,
}

# Models with different feature spaces should not be mixed in ensemble
MP_WIDE_PREFIX = "mp_wide"


# ── Model Registry ────────────────────────────────────────────────────────────

def _load_results(results_path: Path) -> dict:
    """Load results.json, returning empty dict on any failure."""
    try:
        with open(results_path) as fh:
            return json.load(fh)
    except Exception as exc:
        log.warning(f"Cannot read {results_path}: {exc}")
        return {}


def discover_models(prefix_filter: Optional[str] = None) -> Dict[str, dict]:
    """
    Scan PRED_DIR for subdirectories that contain a model.lgbm file.

    Returns a mapping of model_name -> registry entry with keys:
        path        Path to model.lgbm
        dir         Parent directory
        test_auc    float (0.0 if not found)
        val_auc     float
        test_f1     float
        results     full results dict
    """
    if not PRED_DIR.exists():
        log.error(f"Predictive model directory not found: {PRED_DIR}")
        return {}

    registry: Dict[str, dict] = {}
    for model_lgbm in sorted(PRED_DIR.glob("*/model.lgbm")):
        model_dir = model_lgbm.parent
        name = model_dir.name

        if prefix_filter and not name.startswith(prefix_filter):
            continue

        results = _load_results(model_dir / "results.json")
        test_metrics = results.get("test", {})
        val_metrics  = results.get("val", {})

        registry[name] = {
            "path":     model_lgbm,
            "dir":      model_dir,
            "test_auc": float(test_metrics.get("auc_roc", 0.0)),
            "val_auc":  float(val_metrics.get("auc_roc", 0.0)),
            "test_f1":  float(test_metrics.get("best_f1", 0.0)),
            "results":  results,
        }

    return registry


def select_top_models(
    registry: Dict[str, dict],
    n: int = 3,
    exclude_prefix: str = MP_WIDE_PREFIX,
) -> List[str]:
    """
    Return the top-n model names ranked by test AUC,
    excluding any that begin with *exclude_prefix* and any whose
    feature count differs from the newest model (feature-incompatible).
    """
    import lightgbm as lgb

    candidates = {
        name: entry
        for name, entry in registry.items()
        if not name.startswith(exclude_prefix)
    }
    if not candidates:
        return []

    # Load feature counts and filter to compatible models.
    feat_counts: Dict[str, int] = {}
    for name, entry in candidates.items():
        try:
            feat_counts[name] = lgb.Booster(model_file=str(entry["path"])).num_feature()
        except Exception:
            pass

    if not feat_counts:
        return []

    # Reference: feature count of the newest model (trained with current code).
    newest = max(feat_counts, key=lambda k: candidates[k]["path"].stat().st_mtime)
    ref_n = feat_counts[newest]
    compatible = {k for k, v in feat_counts.items() if v == ref_n}

    if len(compatible) < len(feat_counts):
        excluded = set(feat_counts) - compatible
        log.info(f"Excluded {len(excluded)} feature-incompatible model(s): {excluded} "
                 f"(need {ref_n} features)")

    ranked = sorted(compatible, key=lambda k: candidates[k]["test_auc"], reverse=True)
    selected = ranked[:n]
    log.info(f"Auto-selected top-{n} models by test AUC: {selected}")
    return selected


def print_model_table(registry: Dict[str, dict]) -> None:
    """Print a formatted table of all discovered models and their metrics."""
    if not registry:
        print("No models found in", PRED_DIR)
        return

    col_w = max(len(n) for n in registry) + 2
    header = f"{'Model':<{col_w}}  {'Val AUC':>8}  {'Test AUC':>9}  {'Test F1':>8}"
    print(header)
    print("-" * len(header))
    for name in sorted(registry, key=lambda k: registry[k]["test_auc"], reverse=True):
        e = registry[name]
        print(
            f"{name:<{col_w}}  {e['val_auc']:>8.4f}  {e['test_auc']:>9.4f}  {e['test_f1']:>8.4f}"
        )


# ── Per-Model Prediction ──────────────────────────────────────────────────────

def run_single_model(
    model_name: str,
    entry: dict,
    target: date,
) -> Optional[pd.DataFrame]:
    """
    Call predict_tomorrow from train_predictive_fire_risk with the given model.

    Returns a DataFrame with at least columns:
        cell_id, lat, lon, beat, range, risk_score
    Returns None on failure (so the ensemble continues with remaining models).
    """
    # Import lazily: the training script performs heavy setup at module level
    try:
        from scripts.train_predictive_fire_risk import predict_tomorrow
    except ImportError as exc:
        log.error(f"Cannot import predict_tomorrow: {exc}")
        return None

    log.info(f"Running {model_name} (test_auc={entry['test_auc']:.4f}) ...")
    try:
        df = predict_tomorrow(model_path=entry["path"], target_date=target)
        if df is None or df.empty:
            log.warning(f"  {model_name}: returned empty DataFrame")
            return None
        log.info(f"  {model_name}: {len(df)} cells scored")
        return df[["cell_id", "lat", "lon", "beat", "range", "risk_score"]].copy()
    except Exception as exc:
        log.error(f"  {model_name}: prediction failed: {exc}", exc_info=True)
        return None


# ── Ensemble Strategies ───────────────────────────────────────────────────────

def _weighted_avg(
    score_cols: List[str],
    weights: Dict[str, float],
    merged: pd.DataFrame,
) -> pd.Series:
    """
    Weighted average of raw risk scores, weights proportional to test AUC.
    Each model's weight is its test AUC minus 0.5 (chance level), floored at 0.
    """
    total = sum(weights[col] for col in score_cols)
    if total == 0:
        total = 1.0
    ensemble = sum(merged[col] * (weights[col] / total) for col in score_cols)
    return ensemble


def _rank_avg(score_cols: List[str], merged: pd.DataFrame) -> pd.Series:
    """
    Average of per-model rank percentiles (0-1).
    More robust to calibration differences between models.
    """
    percentile_frames = [
        merged[col].rank(pct=True, method="average") for col in score_cols
    ]
    return sum(percentile_frames) / len(percentile_frames)


def _max_score(score_cols: List[str], merged: pd.DataFrame) -> pd.Series:
    """Most conservative strategy: take the maximum score across all models."""
    return merged[score_cols].max(axis=1)


def apply_ensemble(
    predictions: Dict[str, pd.DataFrame],
    registry_entries: Dict[str, dict],
    strategy: str,
) -> pd.DataFrame:
    """
    Merge per-model predictions and compute ensemble_score.

    Returns a new DataFrame with columns:
        cell_id, lat, lon, beat, range,
        ensemble_score, risk_level,
        <model_name>_score (one per model)
    """
    if not predictions:
        raise ValueError("No predictions to ensemble.")

    # Merge all models on cell_id (inner join to keep only cells scored by all)
    base_cols = ["cell_id", "lat", "lon", "beat", "range"]
    merged: Optional[pd.DataFrame] = None

    score_cols: List[str] = []
    for model_name, df in predictions.items():
        col = f"{model_name}_score"
        score_cols.append(col)
        df_renamed = df.rename(columns={"risk_score": col})

        if merged is None:
            merged = df_renamed[base_cols + [col]].copy()
        else:
            merged = merged.merge(
                df_renamed[["cell_id", col]],
                on="cell_id",
                how="inner",
            )

    assert merged is not None

    # Fill any NaN scores (cell absent in one model) with 0
    merged = merged.copy()
    for col in score_cols:
        merged[col] = merged[col].fillna(0.0)

    if strategy == "weighted_avg":
        weights = {
            f"{name}_score": max(entry["test_auc"] - 0.5, 0.0)
            for name, entry in registry_entries.items()
            if f"{name}_score" in score_cols
        }
        ensemble_scores = _weighted_avg(score_cols, weights, merged)
        log.info("Weights used in weighted_avg:")
        total_w = sum(weights.values()) or 1.0
        for col in score_cols:
            log.info(f"  {col}: {weights[col] / total_w:.4f}")

    elif strategy == "rank_avg":
        ensemble_scores = _rank_avg(score_cols, merged)

    elif strategy == "max":
        ensemble_scores = _max_score(score_cols, merged)

    else:
        raise ValueError(f"Unknown ensemble strategy: '{strategy}'")

    result = merged.assign(ensemble_score=ensemble_scores)

    # Assign risk levels to ensemble_score
    result = result.assign(
        risk_level=pd.cut(
            result["ensemble_score"],
            bins=[-1e-9, RISK_THRESHOLDS["MODERATE"], RISK_THRESHOLDS["HIGH"],
                  RISK_THRESHOLDS["CRITICAL"], float("inf")],
            labels=["LOW", "MODERATE", "HIGH", "CRITICAL"],
            right=False,
        ).astype(str),
    )

    return result


# ── Output Helpers ────────────────────────────────────────────────────────────

def save_outputs(
    result: pd.DataFrame,
    target: date,
    model_names: List[str],
    registry_entries: Dict[str, dict],
    strategy: str,
) -> Tuple[Path, Path]:
    """
    Write the risk map CSV and ensemble summary JSON to PRED_DIR.

    Returns (csv_path, summary_path).
    """
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    date_str = target.isoformat()

    # Risk map: same schema as single-model output
    csv_cols = ["cell_id", "lat", "lon", "beat", "range", "ensemble_score", "risk_level"]
    csv_path = PRED_DIR / f"risk_map_{date_str}.csv"
    (
        result[csv_cols]
        .rename(columns={"ensemble_score": "risk_score"})
        .to_csv(csv_path, index=False)
    )
    log.info(f"Risk map saved: {csv_path}")

    # Summary JSON
    level_counts = result["risk_level"].value_counts().to_dict()
    top10 = (
        result.nlargest(10, "ensemble_score")[
            ["cell_id", "beat", "range", "ensemble_score", "risk_level"]
        ]
        .to_dict(orient="records")
    )

    summary = {
        "target_date": date_str,
        "strategy": strategy,
        "n_cells": int(len(result)),
        "risk_counts": {lvl: int(level_counts.get(lvl, 0))
                        for lvl in ["CRITICAL", "HIGH", "MODERATE", "LOW"]},
        "top_10": top10,
        "models": {
            name: {
                "test_auc": registry_entries[name]["test_auc"],
                "val_auc":  registry_entries[name]["val_auc"],
                "test_f1":  registry_entries[name]["test_f1"],
            }
            for name in model_names
        },
    }
    summary_path = PRED_DIR / f"risk_map_{date_str}_ensemble_summary.json"
    with open(summary_path, "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    log.info(f"Ensemble summary saved: {summary_path}")

    return csv_path, summary_path


def log_risk_summary(result: pd.DataFrame, target: date) -> None:
    """Print a concise risk breakdown to the logger."""
    log.info(f"\nEnsemble risk forecast for {target}:")
    log.info(f"  Total cells scored : {len(result)}")
    for level in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        n = (result["risk_level"] == level).sum()
        log.info(f"  {level:10s}: {n:5d} cells")

    top5 = result.nlargest(5, "ensemble_score")
    log.info("  Top 5 cells:")
    for _, row in top5.iterrows():
        log.info(
            f"    {row['cell_id']:12s}  beat={row['beat']:20s}  "
            f"score={row['ensemble_score']:.4f}  level={row['risk_level']}"
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensemble Predictive Fire Risk (grid-based LightGBM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mutex = parser.add_mutually_exclusive_group(required=True)
    mutex.add_argument(
        "--predict", metavar="YYYY-MM-DD",
        help="Generate ensemble risk map for this date.",
    )
    mutex.add_argument(
        "--list", action="store_true",
        help="List all discovered models with their metrics.",
    )
    parser.add_argument(
        "--models", nargs="+", metavar="MODEL_NAME",
        help=(
            "Explicit model directory names inside outputs/predictive_fire_risk/. "
            "Default: auto-select top 3 predictive_* models by test AUC."
        ),
    )
    parser.add_argument(
        "--strategy", default="weighted_avg",
        choices=["weighted_avg", "rank_avg", "max"],
        help="Ensemble strategy (default: weighted_avg).",
    )
    parser.add_argument(
        "--top-n", type=int, default=3, metavar="N",
        help="Number of models to auto-select when --models is not given (default: 3).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # ── List mode ────────────────────────────────────────────────────────────
    if args.list:
        registry = discover_models()
        print_model_table(registry)
        return 0

    # ── Predict mode ─────────────────────────────────────────────────────────
    try:
        target = date.fromisoformat(args.predict)
    except ValueError:
        log.error(f"Invalid date '{args.predict}'. Use YYYY-MM-DD format.")
        return 1

    # Discover all available models
    full_registry = discover_models()
    if not full_registry:
        log.error(f"No trained models found in {PRED_DIR}")
        return 1

    # Resolve which models to use
    if args.models:
        selected_names = args.models
        missing = [n for n in selected_names if n not in full_registry]
        if missing:
            log.error(f"Models not found: {missing}")
            log.error(f"Available: {sorted(full_registry)}")
            return 1
    else:
        selected_names = select_top_models(full_registry, n=args.top_n)
        if not selected_names:
            log.error("No eligible models found after filtering. Use --models to specify explicitly.")
            return 1

    selected_registry = {name: full_registry[name] for name in selected_names}
    log.info(f"Ensemble: {len(selected_names)} models, strategy='{args.strategy}', target={target}")

    # Run predictions
    predictions: Dict[str, pd.DataFrame] = {}
    for name in selected_names:
        df = run_single_model(name, selected_registry[name], target)
        if df is not None:
            predictions[name] = df

    if len(predictions) < 1:
        log.error("All model predictions failed. Cannot produce ensemble.")
        return 1

    if len(predictions) < len(selected_names):
        failed = set(selected_names) - set(predictions)
        log.warning(f"Proceeding with {len(predictions)} models; failed: {failed}")

    # Compute ensemble
    result = apply_ensemble(predictions, selected_registry, args.strategy)

    # Report and save
    log_risk_summary(result, target)
    csv_path, summary_path = save_outputs(
        result, target, list(predictions.keys()), selected_registry, args.strategy
    )

    log.info(f"Done. CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
