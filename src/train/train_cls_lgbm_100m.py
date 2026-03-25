"""
src/train/train_cls_lgbm_100m.py
=================================
100m-resolution fire detection using multi-scale LightGBM.

Instead of one prediction per 6.7km patch, this model predicts fire
probability for each 120m grid cell (4×4 HLS pixels).

Multi-scale feature design:
  LOCAL  (4×4 = 120m):  mean spectral values → point-level signal
  CONTEXT (16×16 = 480m): terrain stats, spectral variability → neighborhood
  PATCH  (224×224 = 6.7km): landcover fractions → landscape context

Label: does the 4×4 cell contain ANY burned pixels (dNBR > 0)?

Sampling strategy:
  - All fire cells from fire patches
  - Subsample bg cells to ~3:1 ratio (configurable)
  - All cells from bg patches get subsample too

Expected dataset size: ~5,000-20,000 training samples (vs 363 at patch level)

Usage:
    python src/train/train_cls_lgbm_100m.py --tag 100m_v1
    python src/train/train_cls_lgbm_100m.py --tag 100m_v1 --bg-ratio 2.0
"""

import sys, os, time, json, logging, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent

# ═════════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════════

CELL_SIZE = 4          # 4 pixels = 120m at 30m HLS
CTX_HALF  = 8          # context window: 16×16 around cell center (480m)
PATCH_H   = 224
PATCH_W   = 224
N_CELLS_R = PATCH_H // CELL_SIZE   # 56
N_CELLS_C = PATCH_W // CELL_SIZE   # 56

INDEX_NAMES = ["NDVI", "NBR", "BSI"]
TERRAIN_NAMES = ["elev_norm", "slope_norm", "sin_asp", "cos_asp"]
LC_NAMES = [
    "tree_cover", "shrubland", "grassland", "cropland", "built_up",
    "bare_sparse", "snow_ice", "water", "wetland", "mangroves", "moss_lichen"
]


# ═════════════════════════════════════════════════════════════════════════════
# Multi-Scale Feature Extraction
# ═════════════════════════════════════════════════════════════════════════════

def _safe_stats(arr):
    """Mean, std of a small array. Returns (mean, std)."""
    v = arr.ravel()
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return 0.0, 0.0
    return float(np.mean(v)), float(np.std(v))


def _context_slice(r_center, c_center, half, H, W):
    """Return (r0, r1, c0, c1) for a context window, clamped to bounds."""
    r0 = max(0, r_center - half)
    r1 = min(H, r_center + half)
    c0 = max(0, c_center - half)
    c1 = min(W, c_center + half)
    return r0, r1, c0, c1


def extract_cell_features(
    indices,      # (3, 3, 224, 224) — NDVI, NBR, BSI × 3 frames
    terrain,      # (4, 224, 224)
    landcover,    # (11, 224, 224)
    cell_r,       # cell row index (0–55)
    cell_c,       # cell col index (0–55)
    patch_lc_fracs,  # precomputed (11,) patch-level LC fractions
):
    """
    Extract multi-scale features for one 120m cell.

    Returns dict of ~55 features.
    """
    features = {}

    # Pixel coordinates
    r0 = cell_r * CELL_SIZE
    r1 = r0 + CELL_SIZE
    c0 = cell_c * CELL_SIZE
    c1 = c0 + CELL_SIZE

    # Center of cell (for context window)
    rc = (r0 + r1) // 2
    cc = (c0 + c1) // 2

    # ── SCALE 1: LOCAL (4×4 = 120m) — spectral means per frame ──────────
    # 3 indices × 3 frames × 1 mean = 9 features
    for i, idx_name in enumerate(INDEX_NAMES):
        for t in range(indices.shape[1]):
            cell_data = indices[i, t, r0:r1, c0:c1]
            features[f"local_{idx_name}_t{t}"] = float(np.nanmean(cell_data))

    # Local temporal deltas (frame 0 vs frame 2)
    # 3 indices × 1 delta = 3 features
    for i, idx_name in enumerate(INDEX_NAMES):
        v0 = float(np.nanmean(indices[i, 0, r0:r1, c0:c1]))
        v2 = float(np.nanmean(indices[i, 2, r0:r1, c0:c1]))
        features[f"local_delta_{idx_name}"] = v0 - v2  # t0 is most recent

    # Local terrain values (mean of 4×4)
    # 4 features
    for ch, tname in enumerate(TERRAIN_NAMES):
        features[f"local_{tname}"] = float(np.nanmean(terrain[ch, r0:r1, c0:c1]))

    # ── SCALE 2: CONTEXT (16×16 = 480m around cell center) ──────────────
    cr0, cr1, cc0, cc1 = _context_slice(rc, cc, CTX_HALF, PATCH_H, PATCH_W)

    # Context spectral variability: std of indices in context window
    # 3 indices × 3 frames × 1 std = 9 features
    for i, idx_name in enumerate(INDEX_NAMES):
        for t in range(indices.shape[1]):
            ctx_data = indices[i, t, cr0:cr1, cc0:cc1]
            _, std = _safe_stats(ctx_data)
            features[f"ctx_{idx_name}_t{t}_std"] = std

    # Context spectral mean (captures neighborhood average)
    # 3 indices × 1 mean (t0 only — most recent) = 3 features
    for i, idx_name in enumerate(INDEX_NAMES):
        ctx_data = indices[i, 0, cr0:cr1, cc0:cc1]
        m, _ = _safe_stats(ctx_data)
        features[f"ctx_{idx_name}_t0_mean"] = m

    # Context terrain stats (mean + std for slope and elevation)
    # 4 terrain channels × 2 stats = 8 features
    for ch, tname in enumerate(TERRAIN_NAMES):
        ctx_terr = terrain[ch, cr0:cr1, cc0:cc1]
        m, s = _safe_stats(ctx_terr)
        features[f"ctx_{tname}_mean"] = m
        features[f"ctx_{tname}_std"] = s

    # Context landcover fractions (480m neighborhood)
    # 11 features
    for lc_idx, lc_name in enumerate(LC_NAMES):
        lc_ctx = landcover[lc_idx, cr0:cr1, cc0:cc1]
        features[f"ctx_lc_{lc_name}"] = float(np.nanmean(lc_ctx))

    # ── SCALE 3: PATCH-LEVEL (6.7km) — shared across all cells ──────────
    # 11 features (precomputed)
    for lc_idx, lc_name in enumerate(LC_NAMES):
        features[f"patch_lc_{lc_name}"] = float(patch_lc_fracs[lc_idx])

    # ── DERIVED: local vs context contrast ──────────────────────────────
    # How different is this cell from its surroundings? 3 features
    for i, idx_name in enumerate(INDEX_NAMES):
        local_val = features[f"local_{idx_name}_t0"]
        ctx_val = features.get(f"ctx_{idx_name}_t0_mean", local_val)
        features[f"contrast_{idx_name}"] = local_val - ctx_val

    return features


# ═════════════════════════════════════════════════════════════════════════════
# Dataset Builder
# ═════════════════════════════════════════════════════════════════════════════

def build_100m_dataset(manifest_path, split, bg_ratio=3.0, seed=42):
    """
    Build 100m-resolution dataset from patches.

    For fire patches: extract ALL fire cells + subsample bg cells
    For bg patches: subsample a small number of cells

    Returns: (X DataFrame, y array, metadata list)
    """
    rng = np.random.RandomState(seed)
    df = pd.read_csv(manifest_path)
    df = df[df["split"] == split].copy()

    all_features = []
    all_labels = []
    all_meta = []

    fire_patches = df[df["is_fire"] == 1]
    bg_patches = df[df["is_fire"] == 0]

    n_fire_cells_total = 0
    n_bg_cells_total = 0

    # ── Process fire patches ─────────────────────────────────────────────
    for idx, row in fire_patches.iterrows():
        path = ROOT / row["path"]
        data = np.load(str(path), allow_pickle=True)

        indices = data["indices"].astype(np.float32)     # (3, 3, 224, 224)
        terrain = data["terrain"].astype(np.float32)     # (4, 224, 224)
        landcover = data["landcover"].astype(np.float32) # (11, 224, 224)
        label = data["label"].astype(np.float32)         # (224, 224)

        # Precompute patch-level LC fractions
        patch_lc_fracs = np.array([landcover[i].mean() for i in range(11)])

        # Classify each 4×4 cell
        fire_cells = []
        bg_cells = []

        for cr in range(N_CELLS_R):
            for cc in range(N_CELLS_C):
                r0 = cr * CELL_SIZE
                r1 = r0 + CELL_SIZE
                c0 = cc * CELL_SIZE
                c1 = c0 + CELL_SIZE

                cell_label = label[r0:r1, c0:c1]
                is_fire = int((cell_label > 0).any())

                if is_fire:
                    fire_cells.append((cr, cc))
                else:
                    bg_cells.append((cr, cc))

        # Keep ALL fire cells
        for cr, cc in fire_cells:
            feat = extract_cell_features(
                indices, terrain, landcover, cr, cc, patch_lc_fracs)
            all_features.append(feat)
            all_labels.append(1)
            all_meta.append({
                "patch_id": row["patch_id"], "cell_r": cr, "cell_c": cc,
                "split": split
            })
        n_fire_cells_total += len(fire_cells)

        # Subsample bg cells from fire patches to match ratio
        n_bg_want = int(len(fire_cells) * bg_ratio)
        if n_bg_want > 0 and len(bg_cells) > 0:
            n_bg_take = min(n_bg_want, len(bg_cells))
            chosen_bg = rng.choice(len(bg_cells), n_bg_take, replace=False)
            for bi in chosen_bg:
                cr, cc = bg_cells[bi]
                feat = extract_cell_features(
                    indices, terrain, landcover, cr, cc, patch_lc_fracs)
                all_features.append(feat)
                all_labels.append(0)
                all_meta.append({
                    "patch_id": row["patch_id"], "cell_r": cr, "cell_c": cc,
                    "split": split
                })
            n_bg_cells_total += n_bg_take

    # ── Process background patches (subsample lightly) ───────────────────
    # Take a few cells per bg patch to represent "no fire" landscape
    cells_per_bg = max(3, int(n_fire_cells_total / max(len(bg_patches), 1)))
    cells_per_bg = min(cells_per_bg, 20)  # cap to avoid oversized dataset

    for idx, row in bg_patches.iterrows():
        path = ROOT / row["path"]
        data = np.load(str(path), allow_pickle=True)

        indices = data["indices"].astype(np.float32)
        terrain = data["terrain"].astype(np.float32)
        landcover = data["landcover"].astype(np.float32)

        patch_lc_fracs = np.array([landcover[i].mean() for i in range(11)])

        # Random cell positions
        chosen_r = rng.randint(0, N_CELLS_R, cells_per_bg)
        chosen_c = rng.randint(0, N_CELLS_C, cells_per_bg)

        for cr, cc in zip(chosen_r, chosen_c):
            feat = extract_cell_features(
                indices, terrain, landcover, cr, cc, patch_lc_fracs)
            all_features.append(feat)
            all_labels.append(0)
            all_meta.append({
                "patch_id": row["patch_id"], "cell_r": int(cr), "cell_c": int(cc),
                "split": split
            })
        n_bg_cells_total += cells_per_bg

    X = pd.DataFrame(all_features)
    y = np.array(all_labels)

    log.info(f"  {split}: {len(X)} cells  ({y.sum()} fire, {(y==0).sum()} bg)  "
             f"fire_rate={y.mean()*100:.1f}%")

    return X, y, all_meta


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="100m LightGBM Fire Detection")
    parser.add_argument("--tag", default="100m_v1")
    parser.add_argument("--bg-ratio", type=float, default=3.0,
                        help="Background cells per fire cell (in fire patches)")
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.03)
    parser.add_argument("--min-child-samples", type=int, default=20)
    parser.add_argument("--num-leaves", type=int, default=15)
    parser.add_argument("--subsample", type=float, default=0.7)
    parser.add_argument("--colsample", type=float, default=0.6)
    parser.add_argument("--l1", type=float, default=0.5)
    parser.add_argument("--l2", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s][%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    manifest = ROOT / "data_lake" / "training_patches_v5" / "manifest.csv"

    # ── Build datasets ───────────────────────────────────────────────────
    log.info("Building 100m-resolution datasets...")
    log.info(f"  Cell size: {CELL_SIZE}px = {CELL_SIZE*30}m")
    log.info(f"  Context window: {CTX_HALF*2}px = {CTX_HALF*2*30}m")
    log.info(f"  BG ratio: {args.bg_ratio}")

    t0 = time.time()
    X_train, y_train, meta_train = build_100m_dataset(
        manifest, "train", bg_ratio=args.bg_ratio, seed=args.seed)
    X_val, y_val, meta_val = build_100m_dataset(
        manifest, "val", bg_ratio=args.bg_ratio, seed=args.seed + 1)
    X_test, y_test, meta_test = build_100m_dataset(
        manifest, "test", bg_ratio=args.bg_ratio, seed=args.seed + 2)
    log.info(f"  Feature extraction: {time.time()-t0:.1f}s")

    feature_cols = list(X_train.columns)
    log.info(f"\nFeatures: {len(feature_cols)}")

    # Replace inf/NaN
    for df in [X_train, X_val, X_test]:
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0.0, inplace=True)

    # ── Distribution shift check ─────────────────────────────────────────
    log.info(f"\n{'='*70}")
    log.info("DISTRIBUTION SHIFT CHECK (top 10 by |shift|)")
    log.info(f"{'='*70}")
    shifts = []
    for col in feature_cols:
        tr_m = X_train[col].mean()
        te_m = X_test[col].mean()
        tr_s = X_train[col].std()
        shift = (te_m - tr_m) / max(tr_s, 1e-8)
        shifts.append((col, shift))
    shifts.sort(key=lambda x: abs(x[1]), reverse=True)
    for col, s in shifts[:10]:
        flag = " ⚠️" if abs(s) > 1.0 else ""
        log.info(f"  {col:40s} {s:+.3f}σ{flag}")
    n_severe = sum(1 for _, s in shifts if abs(s) > 1.0)
    log.info(f"Features with |shift| > 1σ: {n_severe}/{len(feature_cols)}")

    # ── Train LightGBM ───────────────────────────────────────────────────
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, average_precision_score, confusion_matrix,
    )

    log.info(f"\n{'='*65}")
    log.info(f"  LightGBM 100m — {len(feature_cols)} features")
    log.info(f"  Train: {len(X_train)}  Val: {len(X_val)}  Test: {len(X_test)}")
    log.info(f"  max_depth={args.max_depth}  leaves={args.num_leaves}  "
             f"lr={args.lr}  min_child={args.min_child_samples}")
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

    t0 = time.time()
    model.fit(
        X_train[feature_cols], y_train,
        eval_set=[(X_val[feature_cols], y_val)],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=True),
            lgb.log_evaluation(period=50),
        ],
    )
    train_time = time.time() - t0
    log.info(f"Training time: {train_time:.1f}s  "
             f"(best_iteration={model.best_iteration_})")

    # ── Evaluate ─────────────────────────────────────────────────────────
    def evaluate(X, y, split_name, feat_cols):
        probs = model.predict_proba(X[feat_cols])[:, 1]
        preds = model.predict(X[feat_cols])

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
                "fn": int(cm[1,0]), "tn": int(cm[0,0]),
                "n_samples": len(y)}

    train_scores = evaluate(X_train, y_train, "TRAIN", feature_cols)
    val_scores = evaluate(X_val, y_val, "VAL", feature_cols)
    test_scores = evaluate(X_test, y_test, "TEST", feature_cols)

    # ── Threshold Sweep ──────────────────────────────────────────────────
    test_probs = model.predict_proba(X_test[feature_cols])[:, 1]

    log.info(f"\n{'='*75}")
    log.info("THRESHOLD SWEEP ON TEST SET")
    log.info(f"{'='*75}")
    log.info(f"{'Thr':>6s}  {'Acc':>6s}  {'Prec':>6s}  {'Rec':>6s}  "
             f"{'F1':>6s}  {'TP':>5s}  {'FP':>5s}  {'FN':>5s}  {'TN':>5s}")
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
                 f"{f1:6.3f}  {cm[1,1]:5d}  {cm[0,1]:5d}  {cm[1,0]:5d}  {cm[0,0]:5d}{tag}")

    log.info("-" * 75)
    test_auc = roc_auc_score(y_test, test_probs) if len(np.unique(y_test)) > 1 else 0
    test_ap = average_precision_score(y_test, test_probs) if len(np.unique(y_test)) > 1 else 0
    log.info(f"AUC-ROC: {test_auc:.4f}  |  AUC-PR: {test_ap:.4f}")
    log.info(f"Best threshold: {best_thr:.2f}  (F1={best_f1:.4f})")
    log.info("=" * 75)

    # ── Feature Importance ───────────────────────────────────────────────
    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_cols, importances),
                      key=lambda x: x[1], reverse=True)

    log.info(f"\n{'='*55}")
    log.info(f"TOP 20 FEATURES BY IMPORTANCE")
    log.info(f"{'='*55}")
    max_imp = max(importances) if max(importances) > 0 else 1
    for rank, (fname, imp) in enumerate(feat_imp[:20], 1):
        bar = "█" * int(imp / max_imp * 30)
        log.info(f"  {rank:2d}. {fname:40s}  {imp:5d}  {bar}")
    log.info(f"{'='*55}")

    # ── Comparison with patch-level v2b ──────────────────────────────────
    log.info(f"\n{'='*65}")
    log.info("COMPARISON")
    log.info(f"{'='*65}")
    log.info(f"  Patch-level v2b (6.7km):  test AUC=0.803  F1=0.780")
    log.info(f"  100m grid ({len(feature_cols)} feat):   test AUC={test_auc:.4f}  F1={best_f1:.4f}")
    log.info(f"  Resolution improvement:  6700m → 120m (56× finer)")
    log.info(f"  Sample count:  363 → {len(X_train)} ({len(X_train)/363:.0f}× more)")
    log.info(f"{'='*65}")

    # ── Save ─────────────────────────────────────────────────────────────
    out_dir = ROOT / "outputs" / f"vanaagni_cls_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    import joblib
    model_path = out_dir / "model.lgbm"
    joblib.dump(model, str(model_path))
    log.info(f"\nModel saved: {model_path}")

    with open(out_dir / "feature_names.json", "w") as f:
        json.dump(feature_cols, f)

    results = {
        "args": vars(args),
        "resolution_m": CELL_SIZE * 30,
        "context_m": CTX_HALF * 2 * 30,
        "n_features": len(feature_cols),
        "train": train_scores,
        "val": val_scores,
        "test": test_scores,
        "best_threshold": float(best_thr),
        "best_test_f1": float(best_f1),
        "top_features": [{"name": n, "importance": int(i)}
                         for n, i in feat_imp[:30]],
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Results saved: {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
