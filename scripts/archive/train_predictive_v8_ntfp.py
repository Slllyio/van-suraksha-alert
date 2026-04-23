"""v8 — v7 + grounded Mahua/Tendu niche probabilities as features.

Delta vs v7:
  - Adds `mahua_prob_grounded` and `tendu_prob_grounded` per cell.
  - Everything else (label = NEW ignition, LEAKAGE_FEATURES drop, temporal
    split, LightGBM params, isotonic calibration) is identical to v7.

The niche probs come from LightGBM niche models trained on real GBIF/iNat
presence points vs MP background, NOT from the old legacy `ha_mahua_zone`
/`ha_tendu_zone` proxy flags (which cover 55% and 96% of MP respectively
and carry no discriminative signal).

Reads:
  outputs/predictive_fire_risk/predictive_v6e_live/dataset.parquet
  outputs/ntfp_niche/mp_cell_predictions.parquet
Writes:
  outputs/predictive_fire_risk/predictive_v8_ntfp/
    model.txt, iso_calibrator.joblib, feature_list.json, results.json
    feature_importance.csv
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
NICHE_PARQUET = ROOT / "outputs" / "ntfp_niche" / "mp_cell_predictions.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ntfp"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Identical to v7.
LEAKAGE_FEATURES = [
    "days_since_last_fire",
    "fire_last_7d",
    "neighbor_fire_7d",
    "neighbor_fire_yesterday",
]
NON_FEATURES = {"cell_id", "date", "label", "year"}

# New features added in v8.
NEW_FEATURES = ["mahua_prob_grounded", "tendu_prob_grounded"]


def load_and_split(
    dataset_path: Path, niche_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    print(f"Loading {dataset_path.name} ...")
    df = pd.read_parquet(dataset_path)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    print(f"  total rows: {len(df):,}")

    print(f"Loading niche probs from {niche_path.name} ...")
    niche = pd.read_parquet(niche_path)[["cell_id"] + NEW_FEATURES]
    print(f"  {len(niche):,} cells with niche probs")
    df = df.merge(niche, on="cell_id", how="left")
    missing = int(df[NEW_FEATURES[0]].isna().sum())
    print(f"  rows with missing niche after merge: {missing:,}")
    if missing > 0:
        for c in NEW_FEATURES:
            df[c] = df[c].fillna(df[c].median())

    # NEW-ignition label (same as v7).
    df["new_ign"] = ((df["label"] == 1) & (df["neighbor_fire_yesterday"] == 0)).astype(
        int
    )
    persistent_mask = (df["label"] == 1) & (df["neighbor_fire_yesterday"] > 0)
    print(f"  persistent-fire rows dropped: {int(persistent_mask.sum()):,}")
    df = df[~persistent_mask].reset_index(drop=True)

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
        and df[c].dtype.kind in "biufc"
    ]
    for f in NEW_FEATURES:
        assert f in feats, f"new feature {f} not in feature list"
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
        "is_unbalance": True,
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


def cell_day_recall(df: pd.DataFrame, p: np.ndarray, name: str) -> dict:
    eval_df = pd.DataFrame(
        {
            "date": df["date"].dt.strftime("%Y-%m-%d").values,
            "cell_id": df["cell_id"].values,
            "risk": p,
            "new_ign": df["new_ign"].values,
        }
    )
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
        per_day.append(
            {
                "date": day,
                "n_cells": n,
                "n_new_ign": n_fire,
                "recall_top05": (
                    ((sub["rank"] >= 0.995) & (sub["new_ign"] == 1)).sum() / n_fire
                ),
                "recall_top2": (
                    ((sub["rank"] >= 0.98) & (sub["new_ign"] == 1)).sum() / n_fire
                ),
                "recall_top5": (
                    ((sub["rank"] >= 0.95) & (sub["new_ign"] == 1)).sum() / n_fire
                ),
            }
        )
    per_day_df = pd.DataFrame(per_day)
    summary = {
        "model": name,
        "n_days": len(per_day_df),
        "total_new_ign": int(per_day_df["n_new_ign"].sum()) if len(per_day_df) else 0,
    }
    if len(per_day_df):
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
    train, val, test = load_and_split(DATASET, NICHE_PARQUET)
    feats = pick_features(train)

    model = train_lgbm(train, val, feats)

    print("\nCalibrating (isotonic)...")
    iso = calibrate(model, val, feats)

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
    }
    results["per_day_eval_test"] = cell_day_recall(test, p_test_cal, "v8_test_2025")

    print("\n" + "=" * 60)
    print("V8 RESULTS (v7 + mahua/tendu grounded niche probs)")
    print("=" * 60)
    print(f"  train  ROC-AUC: {results['train']['roc_auc']:.4f}  PR-AUC: {results['train']['pr_auc']:.4f}")
    print(f"  val    ROC-AUC: {results['val']['roc_auc']:.4f}  PR-AUC: {results['val']['pr_auc']:.4f}")
    print(f"  test   ROC-AUC: {results['test']['roc_auc']:.4f}  PR-AUC: {results['test']['pr_auc']:.4f}")
    w5 = results["per_day_eval_test"].get("weighted_recall_top_5pct")
    if w5 is not None:
        print(f"  test cell-day recall @ top 5%: {w5:.3f}")

    model.save_model(str(OUT_DIR / "model.txt"))
    joblib.dump(iso, OUT_DIR / "iso_calibrator.joblib")
    (OUT_DIR / "feature_list.json").write_text(json.dumps(feats, indent=2))
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str))

    imp = pd.DataFrame(
        {
            "feature": feats,
            "gain": model.feature_importance(importance_type="gain"),
            "split": model.feature_importance(importance_type="split"),
        }
    ).sort_values("gain", ascending=False)
    imp.to_csv(OUT_DIR / "feature_importance.csv", index=False)
    print("\nTop 20 features by gain:")
    print(imp.head(20).to_string(index=False))
    niche_rank_mahua = int(imp.reset_index(drop=True).query("feature == 'mahua_prob_grounded'").index[0]) + 1
    niche_rank_tendu = int(imp.reset_index(drop=True).query("feature == 'tendu_prob_grounded'").index[0]) + 1
    print(f"\n  mahua_prob_grounded rank: {niche_rank_mahua} / {len(feats)}")
    print(f"  tendu_prob_grounded rank: {niche_rank_tendu} / {len(feats)}")
    print(f"\nWrote artefacts to {OUT_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
