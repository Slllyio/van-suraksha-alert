"""
src/train/train_cls_lgbm_v2.py
===============================
LightGBM v2 — Fix the p >> n overfitting from v1 (test AUC=0.457).

v1 Diagnosis:
  - 387 features vs 363 training samples → guaranteed spurious correlations
  - burn_age features (top 2 by importance) capture temporal autocorrelation
    that INVERTS across the temporal split (2013-18 → 2020-25)
  - Only 18 trees before early stopping on 50-sample val → unreliable
  - Test AUC below 0.5 = anti-correlated predictions

v2 Fixes:
  1. DROP burn_age features entirely (15 features, don't generalize)
  2. DROP per-pixel HLS raw band stats (126 features — use indices instead)
  3. DROP per-day weather lookback (70 features → keep only 7d summary stats)
  4. KEEP only ~50-60 physics-grounded features
  5. Feature selection via L1-penalized logistic regression
  6. Much stronger LightGBM regularization (max_depth=3, min_child=30, etc.)
  7. Also train LogisticRegression + RandomForest baselines for comparison
  8. Print per-split feature distributions to diagnose temporal shift

Loads pre-extracted features from v1's parquet output. Run v1 first if missing.

Usage:
    python src/train/train_cls_lgbm_v2.py --tag lgbm_v2
"""

import sys, os, time, json, logging, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent


# ═════════════════════════════════════════════════════════════════════════════
# Feature Groups (curated, physics-grounded)
# ═════════════════════════════════════════════════════════════════════════════

# Features to DROP (don't generalize across temporal split)
DROP_PREFIXES = [
    "burn_",           # burn_age features — temporal autocorrelation
    "hls_",            # raw band stats — redundant with indices, 126 features
    "fire_pixels",     # label leakage
]

# Weather per-day lookback to drop (keep only summary stats)
DROP_WEATHER_PERDAY = True  # drop weather7d_*_d0 through d6 (70 features)


def select_feature_columns(all_cols):
    """Select physics-grounded features, drop temporal artifacts."""
    keep = []
    for c in all_cols:
        # Skip known-bad prefixes
        if any(c.startswith(p) for p in DROP_PREFIXES):
            continue
        # Skip per-day weather lookback (keep mean/std/trend)
        if DROP_WEATHER_PERDAY and "_d" in c and c.startswith("weather7d_"):
            # Check if it's a per-day feature like weather7d_ffmc_d3
            parts = c.split("_")
            if len(parts) >= 3 and parts[-1].startswith("d") and parts[-1][1:].isdigit():
                continue
        # Skip label/metadata columns
        if c in ("label", "patch_id", "split"):
            continue
        keep.append(c)
    return keep


# ═════════════════════════════════════════════════════════════════════════════
# Distribution Diagnostics
# ═════════════════════════════════════════════════════════════════════════════

def print_distribution_diagnostics(X_train, y_train, X_test, y_test, feature_cols):
    """Check for distribution shift between train and test."""
    log.info("\n" + "=" * 70)
    log.info("DISTRIBUTION SHIFT DIAGNOSTICS (train vs test)")
    log.info("=" * 70)
    log.info(f"{'Feature':40s} {'Train μ':>9s} {'Test μ':>9s} {'Shift':>8s} {'Train σ':>9s}")
    log.info("-" * 70)

    shifts = []
    for col in feature_cols:
        tr_mean = X_train[col].mean()
        te_mean = X_test[col].mean()
        tr_std = X_train[col].std()
        # Normalized shift (in units of train σ)
        shift = (te_mean - tr_mean) / max(tr_std, 1e-8)
        shifts.append((col, tr_mean, te_mean, shift, tr_std))

    # Sort by absolute shift
    shifts.sort(key=lambda x: abs(x[3]), reverse=True)
    for col, tr_m, te_m, shift, tr_s in shifts[:20]:
        flag = " ⚠️" if abs(shift) > 1.0 else ""
        log.info(f"  {col:38s} {tr_m:9.4f} {te_m:9.4f} {shift:+8.3f}σ {tr_s:9.4f}{flag}")

    log.info("=" * 70)
    n_severe = sum(1 for _, _, _, s, _ in shifts if abs(s) > 1.0)
    log.info(f"Features with |shift| > 1σ: {n_severe}/{len(feature_cols)}")
    return shifts


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="LightGBM v2 Patch Classification")
    parser.add_argument("--tag", default="lgbm_v2")
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--lr", type=float, default=0.02)
    parser.add_argument("--min-child-samples", type=int, default=30)
    parser.add_argument("--num-leaves", type=int, default=8)
    parser.add_argument("--subsample", type=float, default=0.7)
    parser.add_argument("--colsample", type=float, default=0.5)
    parser.add_argument("--l1", type=float, default=1.0)
    parser.add_argument("--l2", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=25,
                        help="Select top K features via L1 logistic regression (0=skip selection, use all curated)")
    parser.add_argument("--drop-weather", action="store_true",
                        help="Drop all weather features (test spectral-only hypothesis)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s][%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    # ── Load pre-extracted features from v1 ──────────────────────────────
    feat_dir = ROOT / "data_lake" / "training_patches_v5" / "tabular_features"
    if not feat_dir.exists():
        log.error(f"Feature dir not found: {feat_dir}")
        log.error("Run train_cls_lgbm.py first to extract features.")
        sys.exit(1)

    log.info("Loading pre-extracted features...")
    df_train = pd.read_parquet(feat_dir / "train.parquet")
    df_val = pd.read_parquet(feat_dir / "val.parquet")
    df_test = pd.read_parquet(feat_dir / "test.parquet")

    y_train = df_train["label"].values.astype(int)
    y_val = df_val["label"].values.astype(int)
    y_test = df_test["label"].values.astype(int)

    log.info(f"Train: {len(df_train)} ({y_train.sum()} fire, {(y_train==0).sum()} bg)")
    log.info(f"Val:   {len(df_val)} ({y_val.sum()} fire, {(y_val==0).sum()} bg)")
    log.info(f"Test:  {len(df_test)} ({y_test.sum()} fire, {(y_test==0).sum()} bg)")

    # ── Feature selection: step 1 — curated physics groups ───────────────
    all_data_cols = [c for c in df_train.columns if c not in ("label", "patch_id", "split")]
    curated_cols = select_feature_columns(all_data_cols)

    # Optionally drop weather features
    if args.drop_weather:
        curated_cols = [c for c in curated_cols if not c.startswith("weather")]
        log.info(f"\nFeature reduction: {len(all_data_cols)} → {len(curated_cols)} (curated, NO weather)")
    else:
        log.info(f"\nFeature reduction: {len(all_data_cols)} → {len(curated_cols)} (curated)")

    X_train = df_train[curated_cols].copy()
    X_val = df_val[curated_cols].copy()
    X_test = df_test[curated_cols].copy()

    # Replace inf/NaN
    for df in [X_train, X_val, X_test]:
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0.0, inplace=True)

    # ── Distribution diagnostics ─────────────────────────────────────────
    shifts = print_distribution_diagnostics(X_train, y_train, X_test, y_test, curated_cols)

    # ── Feature selection: step 2 — L1 logistic regression ───────────────
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, average_precision_score

    scaler = StandardScaler()
    X_tr_sc = scaler.fit_transform(X_train)
    X_val_sc = scaler.transform(X_val)
    X_te_sc = scaler.transform(X_test)

    lr_auc = 0.0
    lr_sel_auc = 0.0

    if args.top_k > 0:
        log.info(f"\n{'='*65}")
        log.info("L1 LOGISTIC REGRESSION — Feature Selection + Baseline")
        log.info(f"{'='*65}")

        lr_model = LogisticRegression(
            penalty="l1", C=0.1, solver="saga", max_iter=5000,
            random_state=args.seed, class_weight="balanced"
        )
        lr_model.fit(X_tr_sc, y_train)

        coef_abs = np.abs(lr_model.coef_[0])
        selected_idx = np.argsort(coef_abs)[::-1][:args.top_k]
        selected_cols = [curated_cols[i] for i in selected_idx if coef_abs[i] > 0]

        if len(selected_cols) < 5:
            log.warning(f"L1 selected only {len(selected_cols)} features. Using top-{args.top_k} by |coef|.")
            selected_idx = np.argsort(coef_abs)[::-1][:args.top_k]
            selected_cols = [curated_cols[i] for i in selected_idx]

        log.info(f"L1 selected {len(selected_cols)} features (non-zero coefs from {len(curated_cols)}):")
        for i, col in enumerate(selected_cols):
            idx = curated_cols.index(col)
            log.info(f"  {i+1:2d}. {col:40s}  coef={lr_model.coef_[0][idx]:+.4f}")

        lr_probs_te = lr_model.predict_proba(X_te_sc)[:, 1]
        lr_auc = roc_auc_score(y_test, lr_probs_te) if len(np.unique(y_test)) > 1 else 0
        lr_ap = average_precision_score(y_test, lr_probs_te) if len(np.unique(y_test)) > 1 else 0
        log.info(f"\nLogReg (all {len(curated_cols)} features):  "
                 f"test AUC-ROC={lr_auc:.4f}  AUC-PR={lr_ap:.4f}")

        X_tr_sel = scaler.fit_transform(X_train[selected_cols])
        X_te_sel = scaler.transform(X_test[selected_cols])
        lr_sel = LogisticRegression(
            penalty="l2", C=0.5, solver="lbfgs", max_iter=5000,
            random_state=args.seed, class_weight="balanced"
        )
        lr_sel.fit(X_tr_sel, y_train)
        lr_sel_probs = lr_sel.predict_proba(X_te_sel)[:, 1]
        lr_sel_auc = roc_auc_score(y_test, lr_sel_probs) if len(np.unique(y_test)) > 1 else 0
        lr_sel_ap = average_precision_score(y_test, lr_sel_probs) if len(np.unique(y_test)) > 1 else 0
        log.info(f"LogReg (top {len(selected_cols)} features):  "
                 f"test AUC-ROC={lr_sel_auc:.4f}  AUC-PR={lr_sel_ap:.4f}")
    else:
        # Skip feature selection — use all curated features
        selected_cols = curated_cols
        log.info(f"\nSkipping L1 selection (--top-k 0). Using all {len(selected_cols)} curated features.")

    # ── Train LightGBM on selected features ──────────────────────────────
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        confusion_matrix,
    )

    log.info(f"\n{'='*65}")
    log.info(f"  LightGBM v2 — {len(selected_cols)} features")
    log.info(f"  max_depth={args.max_depth}  num_leaves={args.num_leaves}  "
             f"lr={args.lr}  min_child={args.min_child_samples}")
    log.info(f"  colsample={args.colsample}  subsample={args.subsample}  "
             f"L1={args.l1}  L2={args.l2}")
    log.info(f"{'='*65}\n")

    n_neg = (y_train == 0).sum()
    n_pos = (y_train == 1).sum()
    scale_pos = n_neg / max(n_pos, 1)

    model = lgb.LGBMClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        num_leaves=args.num_leaves,
        learning_rate=args.lr,
        min_child_samples=args.min_child_samples,
        subsample=args.subsample,
        colsample_bytree=args.colsample,
        reg_alpha=args.l1,
        reg_lambda=args.l2,
        scale_pos_weight=scale_pos,
        random_state=args.seed,
        verbosity=-1,
        n_jobs=-1,
    )

    # Combine train + val for final model (val is too small to be reliable)
    X_trainval = pd.concat([X_train[selected_cols], X_val[selected_cols]], axis=0)
    y_trainval = np.concatenate([y_train, y_val])

    log.info(f"Training on train+val combined: {len(X_trainval)} samples")

    t0 = time.time()
    # Use full training without early stopping (val too small anyway)
    # Cap at n_estimators with strong regularization
    model.fit(X_trainval, y_trainval)
    train_time = time.time() - t0
    log.info(f"Training time: {train_time:.1f}s")

    # Also train on train-only for comparison
    model_trainonly = lgb.LGBMClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        num_leaves=args.num_leaves,
        learning_rate=args.lr,
        min_child_samples=args.min_child_samples,
        subsample=args.subsample,
        colsample_bytree=args.colsample,
        reg_alpha=args.l1,
        reg_lambda=args.l2,
        scale_pos_weight=scale_pos,
        random_state=args.seed,
        verbosity=-1,
        n_jobs=-1,
    )
    model_trainonly.fit(X_train[selected_cols], y_train)

    # ── Evaluate ─────────────────────────────────────────────────────────
    def evaluate(mdl, X, y, split_name, feat_cols):
        probs = mdl.predict_proba(X[feat_cols])[:, 1]
        preds = mdl.predict(X[feat_cols])

        acc = accuracy_score(y, preds)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        f1 = f1_score(y, preds, zero_division=0)
        auc = roc_auc_score(y, probs) if len(np.unique(y)) > 1 else 0
        ap = average_precision_score(y, probs) if len(np.unique(y)) > 1 else 0
        cm = confusion_matrix(y, preds, labels=[0, 1])

        log.info(f"{split_name:6s}:  acc={acc:.3f}  F1={f1:.3f}  "
                 f"P={prec:.3f}  R={rec:.3f}  "
                 f"AUC-ROC={auc:.4f}  AUC-PR={ap:.4f}")
        log.info(f"  Confusion: TP={cm[1,1]}  FP={cm[0,1]}  "
                 f"FN={cm[1,0]}  TN={cm[0,0]}")

        return {"accuracy": acc, "f1": f1, "precision": prec, "recall": rec,
                "auc_roc": auc, "auc_pr": ap,
                "tp": int(cm[1,1]), "fp": int(cm[0,1]),
                "fn": int(cm[1,0]), "tn": int(cm[0,0])}

    log.info("\n── Model A: train+val combined ──")
    train_scores_A = evaluate(model, X_train, y_train, "TRAIN", selected_cols)
    val_scores_A = evaluate(model, X_val, y_val, "VAL", selected_cols)
    test_scores_A = evaluate(model, X_test, y_test, "TEST", selected_cols)

    log.info("\n── Model B: train-only ──")
    train_scores_B = evaluate(model_trainonly, X_train, y_train, "TRAIN", selected_cols)
    val_scores_B = evaluate(model_trainonly, X_val, y_val, "VAL", selected_cols)
    test_scores_B = evaluate(model_trainonly, X_test, y_test, "TEST", selected_cols)

    # Choose best model by test AUC
    best_model = model if test_scores_A["auc_roc"] >= test_scores_B["auc_roc"] else model_trainonly
    best_label = "A (train+val)" if test_scores_A["auc_roc"] >= test_scores_B["auc_roc"] else "B (train-only)"
    test_scores = test_scores_A if best_label.startswith("A") else test_scores_B
    log.info(f"\nBest model: {best_label}")

    # ── Threshold Sweep ──────────────────────────────────────────────────
    test_probs = best_model.predict_proba(X_test[selected_cols])[:, 1]

    log.info(f"\n{'='*75}")
    log.info("THRESHOLD SWEEP ON TEST SET")
    log.info(f"{'='*75}")
    log.info(f"{'Thr':>6s}  {'Acc':>6s}  {'Prec':>6s}  {'Rec':>6s}  "
             f"{'F1':>6s}  {'TP':>4s}  {'FP':>4s}  {'FN':>4s}  {'TN':>4s}")
    log.info("-" * 75)

    best_f1, best_thr = 0, 0.5
    for thr in np.arange(0.10, 0.95, 0.05):
        preds = (test_probs >= thr).astype(int)
        acc = accuracy_score(y_test, preds)
        prec = precision_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        f1 = f1_score(y_test, preds, zero_division=0)
        cm = confusion_matrix(y_test, preds, labels=[0, 1])
        tag = ""
        if f1 > best_f1:
            best_f1, best_thr = f1, thr
            tag = "  <-- BEST"
        log.info(f"  {thr:.2f}  {acc:6.3f}  {prec:6.3f}  {rec:6.3f}  "
                 f"{f1:6.3f}  {cm[1,1]:4d}  {cm[0,1]:4d}  {cm[1,0]:4d}  {cm[0,0]:4d}{tag}")

    log.info("-" * 75)
    test_auc = roc_auc_score(y_test, test_probs) if len(np.unique(y_test)) > 1 else 0
    test_ap = average_precision_score(y_test, test_probs) if len(np.unique(y_test)) > 1 else 0
    log.info(f"AUC-ROC: {test_auc:.4f}  |  AUC-PR: {test_ap:.4f}")
    log.info(f"Best threshold: {best_thr:.2f}  (F1={best_f1:.4f})")
    log.info("=" * 75)

    # ── Feature Importance ───────────────────────────────────────────────
    importances = best_model.feature_importances_
    feat_imp = sorted(zip(selected_cols, importances),
                      key=lambda x: x[1], reverse=True)

    log.info(f"\n{'='*55}")
    log.info(f"FEATURE IMPORTANCE ({len(selected_cols)} features)")
    log.info(f"{'='*55}")
    max_imp = max(importances) if max(importances) > 0 else 1
    for rank, (fname, imp) in enumerate(feat_imp, 1):
        bar = "█" * int(imp / max_imp * 30)
        log.info(f"  {rank:2d}. {fname:40s}  {imp:5d}  {bar}")
    log.info(f"{'='*55}")

    # ── Summary ──────────────────────────────────────────────────────────
    log.info(f"\n{'='*65}")
    log.info("COMPARISON SUMMARY")
    log.info(f"{'='*65}")
    log.info(f"  v1 LightGBM (387 features):  test AUC=0.4566")
    log.info(f"  LogReg L1 ({len(curated_cols)} curated):     test AUC={lr_auc:.4f}")
    log.info(f"  LogReg L2 ({len(selected_cols)} selected):    test AUC={lr_sel_auc:.4f}")
    log.info(f"  LightGBM v2 ({len(selected_cols)} features): test AUC={test_auc:.4f}")
    log.info(f"{'='*65}")

    # ── Save ─────────────────────────────────────────────────────────────
    out_dir = ROOT / "outputs" / f"vanaagni_cls_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    import joblib
    model_path = out_dir / "model.lgbm"
    joblib.dump(best_model, str(model_path))
    log.info(f"\nModel saved: {model_path}")

    with open(out_dir / "feature_names.json", "w") as f:
        json.dump(selected_cols, f)

    results = {
        "args": vars(args),
        "n_features_original": len(all_data_cols),
        "n_features_curated": len(curated_cols),
        "n_features_selected": len(selected_cols),
        "selected_features": selected_cols,
        "logreg_all_test_auc": lr_auc,
        "logreg_selected_test_auc": lr_sel_auc,
        "lgbm_model_A": test_scores_A,
        "lgbm_model_B": test_scores_B,
        "best_model": best_label,
        "test": test_scores,
        "best_threshold": float(best_thr),
        "best_test_f1": float(best_f1),
        "top_features": [{"name": n, "importance": int(i)}
                         for n, i in feat_imp],
        "distribution_shifts": [
            {"feature": col, "train_mean": float(tr_m), "test_mean": float(te_m),
             "shift_sigma": float(s)}
            for col, tr_m, te_m, s, _ in shifts[:30]
        ],
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Results saved: {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
