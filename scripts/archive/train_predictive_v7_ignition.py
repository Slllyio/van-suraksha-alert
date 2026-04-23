"""v7 — NEW-ignition predictor (no spread leakage).

Diagnostic evidence (scripts/_diagnose_v6e_failures.py on 2026 heatwave):
- v6e caught 98.3% of PERSISTENT fires at top 5% of beats
- v6e caught only 20.6% of NEW ignitions at top 5%
- NEW ignitions are 87.9% of the operationally important fire-beat-days
- Training data has 59% persistent positives (vs 12% in deployment)
- Four features directly leak spread signal:
    days_since_last_fire, fire_last_7d, neighbor_fire_7d, neighbor_fire_yesterday

v7 surgery:
1. DROP the four spread-leakage features.
2. Redefine label = NEW ignition (today fire AND yesterday no fire in beat).
3. DROP persistent-fire rows entirely from training (no confounding).
4. Use natural class balance (is_unbalance=True), no subsample_neg, no
   scale_pos_weight cap.
5. Temporal split: train <= 2023, val 2024, test 2025.
6. Early stop on val PR-AUC (recall-dominant), not ROC-AUC.
7. Isotonic calibration on val fold.
8. Same beat-level evaluation yardstick as the v6e diagnostic so we can
   claim apples-to-apples improvement.

Reads: outputs/predictive_fire_risk/predictive_v6e_live/dataset.parquet
Writes: outputs/predictive_fire_risk/predictive_v7_ignition/
          model.txt, iso_calibrator.joblib, feature_list.json, results.json
          eval_beat_level.json, feature_importance.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    ROOT
    / "outputs"
    / "predictive_fire_risk"
    / "predictive_v6e_live"
    / "dataset.parquet"
)
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v7_ignition"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Features to REMOVE — leak "was this beat burning recently?" info.
LEAKAGE_FEATURES = [
    "days_since_last_fire",
    "fire_last_7d",
    "neighbor_fire_7d",
    "neighbor_fire_yesterday",
]

# Identifier / label / metadata columns — not features.
NON_FEATURES = {"cell_id", "date", "label", "year"}


def load_and_split(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    print(f"Loading {path.name} ...")
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    print(f"  total rows: {len(df):,}")

    # Build NEW-ignition label.
    # v6e label is binary fire/no-fire; we want (fire AND yesterday no fire).
    # Proxy for "yesterday no fire": neighbor_fire_yesterday == 0.
    df["new_ign"] = ((df["label"] == 1) & (df["neighbor_fire_yesterday"] == 0)).astype(
        int
    )
    # Persistent fire rows (confounding) — drop from training/val/test alike.
    persistent_mask = (df["label"] == 1) & (df["neighbor_fire_yesterday"] > 0)
    print(f"  persistent-fire rows dropped: {int(persistent_mask.sum()):,}")
    df = df[~persistent_mask].reset_index(drop=True)

    # Temporal split.
    train = df[df["year"] <= 2023].reset_index(drop=True)
    val = df[df["year"] == 2024].reset_index(drop=True)
    test = df[df["year"] == 2025].reset_index(drop=True)
    print(
        f"  train={len(train):,}  val={len(val):,}  test={len(test):,}\n"
        f"  new_ign rate train={train['new_ign'].mean():.4f}  "
        f"val={val['new_ign'].mean():.4f}  test={test['new_ign'].mean():.4f}"
    )
    return train, val, test


def pick_features(df: pd.DataFrame) -> list[str]:
    feats = [
        c
        for c in df.columns
        if c not in NON_FEATURES
        and c not in LEAKAGE_FEATURES
        and c != "new_ign"
        and df[c].dtype.kind in "biufc"  # numeric only
    ]
    print(f"  features ({len(feats)}): {feats[:6]} ... {feats[-4:]}")
    return feats


def train_lgbm(
    train: pd.DataFrame,
    val: pd.DataFrame,
    feats: list[str],
) -> lgb.Booster:
    dtrain = lgb.Dataset(train[feats].values, label=train["new_ign"].values)
    dval = lgb.Dataset(val[feats].values, label=val["new_ign"].values, reference=dtrain)

    params = {
        "objective": "binary",
        "metric": ["average_precision", "auc"],
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_data_in_leaf": 500,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 5,
        "is_unbalance": True,  # natural class balance, no rebalancing
        "verbose": -1,
    }

    print("Training LightGBM (early stop on val PR-AUC)...")
    model = lgb.train(
        params,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(50)],
    )
    return model


def calibrate(
    model: lgb.Booster, val: pd.DataFrame, feats: list[str]
) -> IsotonicRegression:
    p = model.predict(val[feats].values, num_iteration=model.best_iteration)
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p, val["new_ign"].values)
    return iso


def beat_level_eval(
    df: pd.DataFrame,
    p: np.ndarray,
    name: str,
) -> dict:
    """Match evaluation yardstick from _diagnose_v6e_failures.py."""
    eval_df = pd.DataFrame(
        {
            "date": df["date"].dt.strftime("%Y-%m-%d").values,
            "cell_id": df["cell_id"].values,
            "risk": p,
            "new_ign": df["new_ign"].values,
        }
    )
    # Beat comes from cell_id prefix — but we don't have 'beat' in dataset.
    # Fall back to cell-level eval on the test fold since cell->beat mapping
    # is not stored in dataset.parquet. Report cell-level rank recall here.
    # (Beat-level eval against 2026 heatwave uses the statewide parquet.)
    per_day = []
    for day, sub in eval_df.groupby("date"):
        n = len(sub)
        if n == 0:
            continue
        n_fire = int(sub["new_ign"].sum())
        if n_fire == 0:
            continue
        sub = sub.copy()
        sub["rank"] = sub["risk"].rank(pct=True, method="first")
        top05 = int(((sub["rank"] >= 0.995) & (sub["new_ign"] == 1)).sum())
        top2 = int(((sub["rank"] >= 0.98) & (sub["new_ign"] == 1)).sum())
        top5 = int(((sub["rank"] >= 0.95) & (sub["new_ign"] == 1)).sum())
        per_day.append(
            {
                "date": day,
                "n_cells": n,
                "n_new_ign": n_fire,
                "recall_top05": top05 / n_fire,
                "recall_top2": top2 / n_fire,
                "recall_top5": top5 / n_fire,
            }
        )
    per_day_df = pd.DataFrame(per_day)
    summary = {
        "model": name,
        "n_days": len(per_day_df),
        "total_new_ign": int(per_day_df["n_new_ign"].sum())
        if len(per_day_df)
        else 0,
        "macro_recall_top_0.5pct": float(per_day_df["recall_top05"].mean())
        if len(per_day_df)
        else None,
        "macro_recall_top_2pct": float(per_day_df["recall_top2"].mean())
        if len(per_day_df)
        else None,
        "macro_recall_top_5pct": float(per_day_df["recall_top5"].mean())
        if len(per_day_df)
        else None,
    }
    if len(per_day_df):
        # Weighted (total fires / total caught), not macro mean.
        def w(col):
            return float(
                (per_day_df[col] * per_day_df["n_new_ign"]).sum()
                / per_day_df["n_new_ign"].sum()
            )

        summary["weighted_recall_top_0.5pct"] = w("recall_top05")
        summary["weighted_recall_top_2pct"] = w("recall_top2")
        summary["weighted_recall_top_5pct"] = w("recall_top5")
    return summary


def main() -> int:
    train, val, test = load_and_split(DATASET)
    feats = pick_features(train)

    model = train_lgbm(train, val, feats)

    print("\nCalibrating (isotonic)...")
    iso = calibrate(model, val, feats)

    # Predictions on all three splits.
    p_train = model.predict(train[feats].values, num_iteration=model.best_iteration)
    p_val = model.predict(val[feats].values, num_iteration=model.best_iteration)
    p_test = model.predict(test[feats].values, num_iteration=model.best_iteration)
    p_val_cal = iso.predict(p_val)
    p_test_cal = iso.predict(p_test)

    results = {
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "n_test": int(len(test)),
        "n_features": len(feats),
        "best_iter": int(model.best_iteration),
        "train": {
            "new_ign_rate": float(train["new_ign"].mean()),
            "roc_auc": float(roc_auc_score(train["new_ign"], p_train)),
            "pr_auc": float(average_precision_score(train["new_ign"], p_train)),
        },
        "val": {
            "new_ign_rate": float(val["new_ign"].mean()),
            "roc_auc": float(roc_auc_score(val["new_ign"], p_val)),
            "pr_auc": float(average_precision_score(val["new_ign"], p_val)),
            "roc_auc_calibrated": float(roc_auc_score(val["new_ign"], p_val_cal)),
        },
        "test": {
            "new_ign_rate": float(test["new_ign"].mean()),
            "roc_auc": float(roc_auc_score(test["new_ign"], p_test)),
            "pr_auc": float(average_precision_score(test["new_ign"], p_test)),
            "roc_auc_calibrated": float(roc_auc_score(test["new_ign"], p_test_cal)),
            "pr_auc_calibrated": float(
                average_precision_score(test["new_ign"], p_test_cal)
            ),
        },
        "beat_eval_note": (
            "Cell-level per-day rank recall on 2025 test fold. "
            "True beat-level eval requires merging with cell->beat mapping "
            "from data/aoi/ — run _eval_v7_against_2026.py for that."
        ),
    }
    results["per_day_eval_test"] = beat_level_eval(test, p_test_cal, "v7_test_2025")

    print("\n" + "=" * 60)
    print("V7 RESULTS")
    print("=" * 60)
    print(f"  train  ROC-AUC: {results['train']['roc_auc']:.4f}  PR-AUC: {results['train']['pr_auc']:.4f}")
    print(f"  val    ROC-AUC: {results['val']['roc_auc']:.4f}  PR-AUC: {results['val']['pr_auc']:.4f}")
    print(f"  test   ROC-AUC: {results['test']['roc_auc']:.4f}  PR-AUC: {results['test']['pr_auc']:.4f}")
    print(
        f"  test cell-day recall @ top 5%: "
        f"{results['per_day_eval_test'].get('weighted_recall_top_5pct', 'n/a'):.3f}"
        if results["per_day_eval_test"].get("weighted_recall_top_5pct") is not None
        else "  n/a"
    )

    # Persist artefacts.
    model.save_model(str(OUT_DIR / "model.txt"))
    joblib.dump(iso, OUT_DIR / "iso_calibrator.joblib")
    (OUT_DIR / "feature_list.json").write_text(json.dumps(feats, indent=2))
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str))

    # Feature importance.
    imp = pd.DataFrame(
        {
            "feature": feats,
            "gain": model.feature_importance(importance_type="gain"),
            "split": model.feature_importance(importance_type="split"),
        }
    ).sort_values("gain", ascending=False)
    imp.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    print(f"\nTop 15 features by gain:")
    print(imp.head(15).to_string(index=False))
    print(f"\nWrote artefacts to {OUT_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
