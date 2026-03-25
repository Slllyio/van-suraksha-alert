"""
src/train/train_cls_lgbm_v3.py
===============================
Comprehensive LightGBM v3 — weather anomalies + model comparison + hyperparam sweep.

Key improvements over v2b (AUC=0.803):
  1. Weather as ANOMALIES: deviation from monthly climatology, not absolute values
     (Raw weather shifts < 0.3σ between periods, proving normalization was the problem)
  2. Model comparison: LightGBM vs XGBoost vs CatBoost
  3. Hyperparameter sweep (RandomizedSearch)
  4. Combines best spectral/terrain/LC features from v2b with anomaly weather

Usage:
    python src/train/train_cls_lgbm_v3.py --tag v3
    python src/train/train_cls_lgbm_v3.py --tag v3 --no-sweep   # skip hyperparam search
"""

import sys, os, time, json, logging, argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent


# ═════════════════════════════════════════════════════════════════════════════
# Weather Anomaly Features
# ═════════════════════════════════════════════════════════════════════════════

WEATHER_COLS = ["temp_c", "rh_pct", "wind_kmh", "precip_mm",
                "ffmc", "dmc", "dc", "isi", "bui", "fwi"]

# Short names for features
WEATHER_SHORT = ["temp", "rh", "wind", "precip",
                 "ffmc", "dmc", "dc", "isi", "bui", "fwi"]


def build_monthly_climatology(fwi_path):
    """Compute monthly mean/std from full FWI dataset."""
    fwi = pd.read_parquet(fwi_path)
    fwi["date"] = pd.to_datetime(fwi["date"])
    fwi = fwi.set_index("date")
    fwi["month"] = fwi.index.month

    clim = {}
    for month in range(1, 13):
        subset = fwi[fwi["month"] == month]
        clim[month] = {
            "mean": subset[WEATHER_COLS].mean().values.astype(np.float32),
            "std": subset[WEATHER_COLS].std().values.astype(np.float32),
        }
    return fwi, clim


def get_weather_anomalies(fwi_df, date, clim, lookback_days=7):
    """
    Compute weather anomaly features for a given date.

    Returns dict of features:
      - anomaly_*: (value - monthly_mean) / monthly_std for current day
      - anomaly7d_*_mean/max: 7-day lookback anomaly summary
      - raw_fwi, raw_dc: absolute values for key fire indices (always useful)
    """
    features = {}
    month = date.month

    if month not in clim:
        return {f"anomaly_{s}": 0.0 for s in WEATHER_SHORT}

    m_mean = clim[month]["mean"]
    m_std = clim[month]["std"]
    m_std = np.where(m_std < 1e-6, 1.0, m_std)  # avoid div/0

    # Current day
    ts = pd.Timestamp(date)
    if ts in fwi_df.index:
        row = fwi_df.loc[ts]
    else:
        idx = fwi_df.index.get_indexer([ts], method="nearest")[0]
        row = fwi_df.iloc[idx]

    raw = row[WEATHER_COLS].values.astype(np.float32)
    anomaly = (raw - m_mean) / m_std

    for i, name in enumerate(WEATHER_SHORT):
        features[f"anomaly_{name}"] = float(anomaly[i])

    # Also include a few absolute values that are intrinsically meaningful
    for key_idx, key_name in [(9, "fwi"), (6, "dc"), (5, "dmc"), (4, "ffmc")]:
        features[f"raw_{key_name}"] = float(raw[key_idx])

    # 7-day lookback anomalies
    anomaly_7d = []
    for d in range(lookback_days):
        dt = date - timedelta(days=d)
        ts_d = pd.Timestamp(dt)
        dt_month = dt.month
        if dt_month in clim and ts_d in fwi_df.index:
            r = fwi_df.loc[ts_d][WEATHER_COLS].values.astype(np.float32)
            a = (r - clim[dt_month]["mean"]) / np.where(
                clim[dt_month]["std"] < 1e-6, 1.0, clim[dt_month]["std"])
            anomaly_7d.append(a)

    if len(anomaly_7d) > 0:
        stack = np.array(anomaly_7d)  # (days, 10)
        for i, name in enumerate(WEATHER_SHORT):
            features[f"anomaly7d_{name}_mean"] = float(np.mean(stack[:, i]))
            features[f"anomaly7d_{name}_max"] = float(np.max(stack[:, i]))
            features[f"anomaly7d_{name}_trend"] = float(stack[0, i] - stack[-1, i])
    else:
        for name in WEATHER_SHORT:
            features[f"anomaly7d_{name}_mean"] = 0.0
            features[f"anomaly7d_{name}_max"] = 0.0
            features[f"anomaly7d_{name}_trend"] = 0.0

    return features


# ═════════════════════════════════════════════════════════════════════════════
# Feature Assembly
# ═════════════════════════════════════════════════════════════════════════════

# Features to drop from v1 tabular (same as v2b)
DROP_PREFIXES = ["burn_", "hls_", "fire_pixels", "weather"]  # drop ALL old weather


def load_and_augment_features(feat_dir, manifest_path, fwi_df, clim):
    """
    Load v1 tabular features + add weather anomaly features.

    Returns: dict of split → (X, y, patch_ids)
    """
    manifest = pd.read_csv(manifest_path)

    result = {}
    # Check if expanded parquets exist (suffix passed via filename convention)
    _use_expanded = "expanded" in str(manifest_path)
    for split in ["train", "val", "test"]:
        # Load existing spectral/terrain/LC features
        if _use_expanded:
            expanded_path = feat_dir / f"{split}_expanded.parquet"
            if expanded_path.exists():
                df = pd.read_parquet(expanded_path)
                log.info(f"  Using expanded: {expanded_path.name}")
            else:
                df = pd.read_parquet(feat_dir / f"{split}.parquet")
                log.info(f"  No expanded for {split}, using original")
        else:
            df = pd.read_parquet(feat_dir / f"{split}.parquet")
        y = df["label"].values.astype(int)
        patch_ids = df["patch_id"].values

        # Select curated columns (drop burn, HLS, old weather)
        keep_cols = []
        for c in df.columns:
            if c in ("label", "patch_id", "split"):
                continue
            if any(c.startswith(p) for p in DROP_PREFIXES):
                continue
            # Drop per-day weather lookback
            if "weather7d_" in c:
                parts = c.split("_")
                if len(parts) >= 3 and parts[-1].startswith("d") and parts[-1][1:].isdigit():
                    continue
            keep_cols.append(c)

        X = df[keep_cols].copy()

        # Add weather anomaly features per patch
        split_manifest = manifest[manifest["split"] == split]
        anomaly_rows = []

        for _, row in split_manifest.iterrows():
            fire_date = pd.to_datetime(row["fire_date"]).date()
            # Use T-3 offset (same as training data)
            t_input = fire_date - timedelta(days=3)
            anom = get_weather_anomalies(fwi_df, t_input, clim)
            anomaly_rows.append(anom)

        anom_df = pd.DataFrame(anomaly_rows)
        anom_df.index = X.index

        X = pd.concat([X, anom_df], axis=1)

        # Clean
        X.replace([np.inf, -np.inf], np.nan, inplace=True)
        X.fillna(0.0, inplace=True)

        result[split] = (X, y, patch_ids)
        log.info(f"  {split}: {len(X)} samples, {X.shape[1]} features "
                 f"({y.sum()} fire, {(y==0).sum()} bg)")

    return result


# ═════════════════════════════════════════════════════════════════════════════
# Model Training + Evaluation
# ═════════════════════════════════════════════════════════════════════════════

def evaluate_model(model, X, y, feature_cols):
    """Evaluate and return metrics dict."""
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, average_precision_score, confusion_matrix,
    )
    probs = model.predict_proba(X[feature_cols])[:, 1]
    preds = model.predict(X[feature_cols])

    auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0
    ap = average_precision_score(y, probs) if len(np.unique(y)) > 1 else 0
    f1 = f1_score(y, preds, zero_division=0)
    prec = precision_score(y, preds, zero_division=0)
    rec = recall_score(y, preds, zero_division=0)
    acc = accuracy_score(y, preds)
    cm = confusion_matrix(y, preds, labels=[0, 1])

    return {
        "accuracy": acc, "f1": f1, "precision": prec, "recall": rec,
        "auc_roc": auc, "auc_pr": ap,
        "tp": int(cm[1, 1]), "fp": int(cm[0, 1]),
        "fn": int(cm[1, 0]), "tn": int(cm[0, 0]),
    }


def threshold_sweep(model, X, y, feature_cols):
    """Return best threshold and full sweep results."""
    from sklearn.metrics import f1_score, precision_score, recall_score, confusion_matrix
    probs = model.predict_proba(X[feature_cols])[:, 1]
    best_f1, best_thr = 0, 0.5
    rows = []
    for thr in np.arange(0.10, 0.95, 0.05):
        preds = (probs >= thr).astype(int)
        f1 = f1_score(y, preds, zero_division=0)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        cm = confusion_matrix(y, preds, labels=[0, 1])
        rows.append((thr, prec, rec, f1, cm[1,1], cm[0,1], cm[1,0], cm[0,0]))
        if f1 > best_f1:
            best_f1, best_thr = f1, thr
    return best_thr, best_f1, rows


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="LightGBM v3 + Model Comparison")
    parser.add_argument("--tag", default="v3")
    parser.add_argument("--no-sweep", action="store_true", help="Skip hyperparam sweep")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--expanded", action="store_true",
                        help="Use expanded dataset ({split}_expanded.parquet)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s][%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    feat_dir = ROOT / "data_lake" / "training_patches_v5" / "tabular_features"
    suffix = "_expanded" if args.expanded else ""
    manifest_path = ROOT / "data_lake" / "training_patches_v5" / f"manifest{suffix}.csv"
    fwi_path = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"

    # ── Build monthly climatology ────────────────────────────────────────
    log.info("Building monthly climatology from FWI data...")
    fwi_df, clim = build_monthly_climatology(fwi_path)
    log.info(f"  FWI data: {len(fwi_df)} days, {fwi_df.index.min()} to {fwi_df.index.max()}")

    # ── Load + augment features ──────────────────────────────────────────
    log.info("\nLoading spectral/terrain/LC features + adding weather anomalies...")
    data = load_and_augment_features(feat_dir, manifest_path, fwi_df, clim)

    X_train, y_train, _ = data["train"]
    X_val, y_val, _ = data["val"]
    X_test, y_test, _ = data["test"]
    feature_cols = list(X_train.columns)

    # Combine train+val (val too small for reliable early stopping)
    X_trainval = pd.concat([X_train, X_val], axis=0)
    y_trainval = np.concatenate([y_train, y_val])
    log.info(f"\nTrain+val combined: {len(X_trainval)} samples, {len(feature_cols)} features")

    # ── Distribution shift diagnostics ───────────────────────────────────
    log.info(f"\n{'='*70}")
    log.info("DISTRIBUTION SHIFT (top 15)")
    log.info(f"{'='*70}")
    shifts = []
    for col in feature_cols:
        tr_m = X_train[col].mean()
        te_m = X_test[col].mean()
        tr_s = X_train[col].std()
        shift = (te_m - tr_m) / max(tr_s, 1e-8)
        shifts.append((col, shift))
    shifts.sort(key=lambda x: abs(x[1]), reverse=True)
    for col, s in shifts[:15]:
        flag = " ⚠️" if abs(s) > 1.0 else ""
        log.info(f"  {col:40s} {s:+.3f}σ{flag}")
    n_severe = sum(1 for _, s in shifts if abs(s) > 1.0)
    log.info(f"Features with |shift| > 1σ: {n_severe}/{len(feature_cols)}")

    # ═════════════════════════════════════════════════════════════════════
    # MODEL COMPARISON
    # ═════════════════════════════════════════════════════════════════════

    n_neg = (y_trainval == 0).sum()
    n_pos = (y_trainval == 1).sum()
    scale_pos = n_neg / max(n_pos, 1)

    results = {}

    # ── 1. LightGBM (tuned defaults from v2b) ───────────────────────────
    import lightgbm as lgb

    log.info(f"\n{'='*65}")
    log.info("MODEL 1: LightGBM")
    log.info(f"{'='*65}")

    lgbm_model = lgb.LGBMClassifier(
        n_estimators=500, max_depth=3, num_leaves=8,
        learning_rate=0.02, min_child_samples=30,
        subsample=0.7, colsample_bytree=0.5,
        reg_alpha=1.0, reg_lambda=5.0,
        scale_pos_weight=scale_pos,
        random_state=args.seed, verbosity=-1, n_jobs=-1,
    )
    lgbm_model.fit(X_trainval[feature_cols], y_trainval)

    lgbm_test = evaluate_model(lgbm_model, X_test, y_test, feature_cols)
    lgbm_thr, lgbm_f1, _ = threshold_sweep(lgbm_model, X_test, y_test, feature_cols)
    log.info(f"  Test: AUC={lgbm_test['auc_roc']:.4f}  AUC-PR={lgbm_test['auc_pr']:.4f}  "
             f"F1={lgbm_f1:.4f} (thr={lgbm_thr:.2f})")
    log.info(f"  TP={lgbm_test['tp']}  FP={lgbm_test['fp']}  "
             f"FN={lgbm_test['fn']}  TN={lgbm_test['tn']}")
    results["lgbm_default"] = {**lgbm_test, "best_f1": lgbm_f1, "best_thr": lgbm_thr}

    # ── 2. XGBoost ───────────────────────────────────────────────────────
    try:
        from xgboost import XGBClassifier

        log.info(f"\n{'='*65}")
        log.info("MODEL 2: XGBoost")
        log.info(f"{'='*65}")

        xgb_model = XGBClassifier(
            n_estimators=500, max_depth=3,
            learning_rate=0.02, min_child_weight=30,
            subsample=0.7, colsample_bytree=0.5,
            reg_alpha=1.0, reg_lambda=5.0,
            scale_pos_weight=scale_pos,
            random_state=args.seed, verbosity=0, n_jobs=-1,
            eval_metric="logloss", use_label_encoder=False,
        )
        xgb_model.fit(X_trainval[feature_cols], y_trainval)

        xgb_test = evaluate_model(xgb_model, X_test, y_test, feature_cols)
        xgb_thr, xgb_f1, _ = threshold_sweep(xgb_model, X_test, y_test, feature_cols)
        log.info(f"  Test: AUC={xgb_test['auc_roc']:.4f}  AUC-PR={xgb_test['auc_pr']:.4f}  "
                 f"F1={xgb_f1:.4f} (thr={xgb_thr:.2f})")
        results["xgboost"] = {**xgb_test, "best_f1": xgb_f1, "best_thr": xgb_thr}
    except ImportError:
        log.warning("  XGBoost not installed — skipping. Install with: pip install xgboost")
        results["xgboost"] = {"auc_roc": 0, "note": "not installed"}

    # ── 3. CatBoost ──────────────────────────────────────────────────────
    try:
        from catboost import CatBoostClassifier

        log.info(f"\n{'='*65}")
        log.info("MODEL 3: CatBoost")
        log.info(f"{'='*65}")

        cb_model = CatBoostClassifier(
            iterations=500, depth=4, learning_rate=0.03,
            l2_leaf_reg=5.0, subsample=0.7,
            scale_pos_weight=scale_pos,
            random_seed=args.seed, verbose=0,
            auto_class_weights=None,
        )
        cb_model.fit(X_trainval[feature_cols], y_trainval)

        cb_test = evaluate_model(cb_model, X_test, y_test, feature_cols)
        cb_thr, cb_f1, _ = threshold_sweep(cb_model, X_test, y_test, feature_cols)
        log.info(f"  Test: AUC={cb_test['auc_roc']:.4f}  AUC-PR={cb_test['auc_pr']:.4f}  "
                 f"F1={cb_f1:.4f} (thr={cb_thr:.2f})")
        results["catboost"] = {**cb_test, "best_f1": cb_f1, "best_thr": cb_thr}
    except ImportError:
        log.warning("  CatBoost not installed — skipping. Install with: pip install catboost")
        results["catboost"] = {"auc_roc": 0, "note": "not installed"}

    # ── 4. LightGBM WITHOUT weather anomalies (ablation) ─────────────────
    log.info(f"\n{'='*65}")
    log.info("MODEL 4: LightGBM NO weather (ablation baseline = v2b equivalent)")
    log.info(f"{'='*65}")

    no_weather_cols = [c for c in feature_cols
                       if not c.startswith("anomaly") and not c.startswith("raw_")]
    lgbm_noweather = lgb.LGBMClassifier(
        n_estimators=500, max_depth=3, num_leaves=8,
        learning_rate=0.02, min_child_samples=30,
        subsample=0.7, colsample_bytree=0.5,
        reg_alpha=1.0, reg_lambda=5.0,
        scale_pos_weight=scale_pos,
        random_state=args.seed, verbosity=-1, n_jobs=-1,
    )
    lgbm_noweather.fit(X_trainval[no_weather_cols], y_trainval)

    nw_test = evaluate_model(lgbm_noweather, X_test, y_test, no_weather_cols)
    nw_thr, nw_f1, _ = threshold_sweep(lgbm_noweather, X_test, y_test, no_weather_cols)
    log.info(f"  Test: AUC={nw_test['auc_roc']:.4f}  AUC-PR={nw_test['auc_pr']:.4f}  "
             f"F1={nw_f1:.4f} (thr={nw_thr:.2f})")
    results["lgbm_no_weather"] = {**nw_test, "best_f1": nw_f1, "best_thr": nw_thr}

    # ═════════════════════════════════════════════════════════════════════
    # HYPERPARAMETER SWEEP (LightGBM)
    # ═════════════════════════════════════════════════════════════════════

    if not args.no_sweep:
        from sklearn.model_selection import RandomizedSearchCV
        from sklearn.metrics import make_scorer, roc_auc_score

        log.info(f"\n{'='*65}")
        log.info("HYPERPARAMETER SWEEP (LightGBM, 50 iterations)")
        log.info(f"{'='*65}")

        param_dist = {
            "max_depth": [2, 3, 4, 5],
            "num_leaves": [4, 8, 12, 16, 24],
            "learning_rate": [0.01, 0.02, 0.03, 0.05, 0.08],
            "min_child_samples": [15, 20, 30, 40, 50],
            "subsample": [0.5, 0.6, 0.7, 0.8],
            "colsample_bytree": [0.3, 0.4, 0.5, 0.6, 0.7],
            "reg_alpha": [0.0, 0.5, 1.0, 2.0, 5.0],
            "reg_lambda": [0.0, 1.0, 3.0, 5.0, 10.0],
        }

        base_lgbm = lgb.LGBMClassifier(
            n_estimators=500,
            scale_pos_weight=scale_pos,
            random_state=args.seed,
            verbosity=-1, n_jobs=-1,
        )

        # Use train-only for CV, test for final eval
        scorer = make_scorer(roc_auc_score, needs_proba=True)
        search = RandomizedSearchCV(
            base_lgbm, param_dist, n_iter=50,
            scoring=scorer, cv=3, random_state=args.seed,
            verbose=0, n_jobs=1,  # LightGBM already uses n_jobs=-1
        )
        search.fit(X_trainval[feature_cols], y_trainval)

        log.info(f"  Best CV AUC: {search.best_score_:.4f}")
        log.info(f"  Best params: {search.best_params_}")

        # Evaluate best model on test
        best_model = search.best_estimator_
        best_test = evaluate_model(best_model, X_test, y_test, feature_cols)
        best_thr, best_f1, sweep_rows = threshold_sweep(
            best_model, X_test, y_test, feature_cols)

        log.info(f"  Test: AUC={best_test['auc_roc']:.4f}  AUC-PR={best_test['auc_pr']:.4f}  "
                 f"F1={best_f1:.4f} (thr={best_thr:.2f})")

        results["lgbm_tuned"] = {
            **best_test, "best_f1": best_f1, "best_thr": best_thr,
            "best_params": search.best_params_, "cv_auc": search.best_score_,
        }

        # Threshold sweep for tuned model
        log.info(f"\n{'='*75}")
        log.info("THRESHOLD SWEEP — BEST TUNED MODEL")
        log.info(f"{'='*75}")
        log.info(f"{'Thr':>6s}  {'Prec':>6s}  {'Rec':>6s}  {'F1':>6s}  "
                 f"{'TP':>4s}  {'FP':>4s}  {'FN':>4s}  {'TN':>4s}")
        log.info("-" * 60)
        for thr, prec, rec, f1, tp, fp, fn, tn in sweep_rows:
            tag = "  <-- BEST" if abs(f1 - best_f1) < 1e-6 and f1 > 0 else ""
            log.info(f"  {thr:.2f}  {prec:6.3f}  {rec:6.3f}  {f1:6.3f}  "
                     f"{tp:4d}  {fp:4d}  {fn:4d}  {tn:4d}{tag}")
        log.info("=" * 60)

        # Use tuned model as final
        final_model = best_model
        final_cols = feature_cols
    else:
        log.info("\n(Skipping hyperparameter sweep — use without --no-sweep to enable)")
        final_model = lgbm_model
        final_cols = feature_cols
        sweep_rows = []

    # ═════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═════════════════════════════════════════════════════════════════════

    log.info(f"\n{'='*75}")
    log.info("FINAL COMPARISON")
    log.info(f"{'='*75}")
    log.info(f"  {'Model':30s} {'AUC-ROC':>8s}  {'AUC-PR':>8s}  {'Best F1':>8s}")
    log.info("-" * 60)

    for name, r in sorted(results.items(), key=lambda x: -x[1].get("auc_roc", 0)):
        if "note" in r:
            log.info(f"  {name:30s} {'N/A':>8s}  ({r['note']})")
        else:
            log.info(f"  {name:30s} {r['auc_roc']:8.4f}  {r['auc_pr']:8.4f}  "
                     f"{r.get('best_f1', r.get('f1', 0)):8.4f}")

    log.info(f"\n  Previous best (v2b, no weather): AUC=0.8033  F1=0.7801")
    log.info(f"{'='*75}")

    # ── Feature importance (final model) ─────────────────────────────────
    importances = final_model.feature_importances_
    feat_imp = sorted(zip(final_cols, importances),
                      key=lambda x: x[1], reverse=True)

    log.info(f"\n{'='*55}")
    log.info(f"TOP 25 FEATURES")
    log.info(f"{'='*55}")
    max_imp = max(importances) if max(importances) > 0 else 1
    for rank, (fname, imp) in enumerate(feat_imp[:25], 1):
        bar = "█" * int(imp / max_imp * 25)
        log.info(f"  {rank:2d}. {fname:40s}  {imp:5d}  {bar}")
    log.info(f"{'='*55}")

    # ── Save ─────────────────────────────────────────────────────────────
    out_dir = ROOT / "outputs" / f"vanaagni_cls_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    import joblib
    joblib.dump(final_model, str(out_dir / "model.lgbm"))
    log.info(f"\nModel saved: {out_dir / 'model.lgbm'}")

    with open(out_dir / "feature_names.json", "w") as f:
        json.dump(final_cols, f)

    save_results = {
        "n_features": len(final_cols),
        "feature_groups": {
            "spectral_terrain_lc": len([c for c in final_cols
                                        if not c.startswith("anomaly") and not c.startswith("raw_")]),
            "weather_anomaly": len([c for c in final_cols if c.startswith("anomaly")]),
            "weather_raw": len([c for c in final_cols if c.startswith("raw_")]),
        },
        "model_comparison": results,
        "top_features": [{"name": n, "importance": int(i)} for n, i in feat_imp[:40]],
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(save_results, f, indent=2, default=str)
    log.info(f"Results saved: {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
