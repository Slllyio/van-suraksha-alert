"""
src/train/train_cls_cached.py
==============================
Ultra-fast patch classification training on precomputed backbone features.

No backbone in GPU memory. Each sample is ~15 KB (vs 50 MB raw patch).
Epochs take 1-3 seconds. Enables rapid experimentation with head architectures,
loss functions, and feature combinations.

Precompute features first:
    python scripts/cache_cls_features.py

Then train:
    python src/train/train_cls_cached.py --tag cached_v1

Features per sample:
    cls_feat       (1280,)   CLS token from Prithvi 600M
    pool_feat      (1280,)   Mean-pooled spatial tokens
    weather        (10,)     Current-day FWI weather
    weather_7d     (10, 7)   7-day lookback
    terrain_global (18,)     Spatial-avg terrain+lc+burn_age
"""

import sys, os, math, time, json, logging, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
)

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent


# ═════════════════════════════════════════════════════════════════════════════
# Dataset: loads precomputed features (no backbone needed)
# ═════════════════════════════════════════════════════════════════════════════

class CachedClsDataset(Dataset):
    """Load precomputed backbone features for patch classification."""

    def __init__(self, manifest_path, cache_dir, split="train",
                 min_fire_pixels=25):
        df = pd.read_csv(manifest_path)
        df = df[df["split"] == split].copy()

        if min_fire_pixels > 0:
            mask = (df["fire_pixels"] >= min_fire_pixels) | (df["is_fire"] == 0)
            df = df[mask]

        self.df = df.reset_index(drop=True)
        self.cache_dir = Path(cache_dir)

        # Verify all files exist
        missing = []
        for _, row in self.df.iterrows():
            path = self.cache_dir / f"{row['patch_id']}.npz"
            if not path.exists():
                missing.append(str(row["patch_id"]))
        if missing:
            log.warning(f"Missing {len(missing)} cached features! "
                        f"Run scripts/cache_cls_features.py first.")
            # Filter to existing
            self.df = self.df[
                self.df["patch_id"].apply(
                    lambda pid: (self.cache_dir / f"{pid}.npz").exists()
                )
            ].reset_index(drop=True)

        n_fire = int(self.df["is_fire"].sum())
        n_neg = len(self.df) - n_fire
        print(f"CachedClsDataset [{split:5s}]: {len(self.df):4d} patches  "
              f"({n_fire} fire / {n_neg} negative)")

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        path = self.cache_dir / f"{row['patch_id']}.npz"
        data = np.load(str(path), allow_pickle=True)

        return {
            "cls_feat":       torch.from_numpy(data["cls_feat"].astype(np.float32)),
            "pool_feat":      torch.from_numpy(data["pool_feat"].astype(np.float32)),
            "weather":        torch.from_numpy(data["weather"].astype(np.float32)),
            "weather_7d":     torch.from_numpy(data["weather_7d"].astype(np.float32)),
            "terrain_global": torch.from_numpy(data["terrain_global"].astype(np.float32)),
            "label":          torch.tensor(int(row["is_fire"]), dtype=torch.long),
            "patch_id":       str(row["patch_id"]),
        }

    def make_sampler(self):
        """Tier-weighted sampler."""
        TIER_W = {"GOLD": 3.0, "SILVER": 2.0, "BRONZE": 1.5,
                  "VIIRS_ONLY": 1.0, "NEGATIVE": 1.0}
        w = np.array([TIER_W.get(str(r.get("tier", "NEGATIVE")), 1.0)
                       for _, r in self.df.iterrows()])
        return WeightedRandomSampler(torch.DoubleTensor(w), len(w), replacement=True)


# ═════════════════════════════════════════════════════════════════════════════
# Model: lightweight MLP head (no backbone!)
# ═════════════════════════════════════════════════════════════════════════════

class FireClsHead(nn.Module):
    """
    Lightweight classification head operating on cached features.

    Input features:
        cls_feat       (B, 1280)
        pool_feat      (B, 1280)
        weather        (B, 10)
        weather_7d     (B, 10, 7)
        terrain_global (B, 18)

    Architecture:
        [cls_feat | pool_feat | weather_enc | terrain_global] → MLP → 1 logit
    """

    def __init__(self, embed_dim=1280, weather_dim=10, terrain_dim=18,
                 hidden=256, dropout=0.3):
        super().__init__()

        # Weather encoder: (10,) current + (10,7) lookback → (32,)
        self.weather_mlp = nn.Sequential(
            nn.Linear(weather_dim + weather_dim * 7, 64),
            nn.GELU(),
            nn.Linear(64, 32),
        )

        # Total: cls (1280) + pool (1280) + weather (32) + terrain (18) = 2610
        feat_dim = embed_dim * 2 + 32 + terrain_dim

        self.head = nn.Sequential(
            nn.LayerNorm(feat_dim),
            nn.Linear(feat_dim, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden // 2, 1),
        )

        # Bias init
        with torch.no_grad():
            fire_prior = 0.59
            self.head[-1].bias.data.fill_(math.log(fire_prior / (1 - fire_prior)))

        n_params = sum(p.numel() for p in self.parameters())
        log.info(f"FireClsHead: {n_params:,} params  (feat_dim={feat_dim})")

    def forward(self, cls_feat, pool_feat, weather, weather_7d, terrain_global):
        # Flatten weather_7d: (B, 10, 7) → (B, 70)
        B = weather.shape[0]
        w7_flat = weather_7d.reshape(B, -1)
        w_cat = torch.cat([weather, w7_flat], dim=1)  # (B, 80)
        w_enc = self.weather_mlp(w_cat)  # (B, 32)

        feat = torch.cat([cls_feat, pool_feat, w_enc, terrain_global], dim=1)
        logit = self.head(feat)  # (B, 1)
        return {"logit": logit, "prob": torch.sigmoid(logit)}


# ═════════════════════════════════════════════════════════════════════════════
# Metrics
# ═════════════════════════════════════════════════════════════════════════════

class Metrics:
    def __init__(self):
        self.reset()

    def reset(self):
        self.labels = []
        self.probs = []
        self.total_loss = 0.0
        self.n = 0

    def update(self, labels, probs, loss=None):
        self.labels.extend(labels.cpu().numpy().tolist())
        self.probs.extend(probs.detach().cpu().numpy().tolist())
        if loss is not None:
            self.total_loss += float(loss)
            self.n += 1

    def compute(self, threshold=0.5):
        y = np.array(self.labels)
        p = np.array(self.probs)
        preds = (p >= threshold).astype(int)

        s = {}
        s["accuracy"] = float(accuracy_score(y, preds))
        s["precision"] = float(precision_score(y, preds, zero_division=0))
        s["recall"] = float(recall_score(y, preds, zero_division=0))
        s["f1"] = float(f1_score(y, preds, zero_division=0))

        if len(np.unique(y)) > 1:
            s["auc_roc"] = float(roc_auc_score(y, p))
            s["auc_pr"] = float(average_precision_score(y, p))
        else:
            s["auc_roc"] = 0.0
            s["auc_pr"] = 0.0

        cm = confusion_matrix(y, preds, labels=[0, 1])
        s["tn"], s["fp"], s["fn"], s["tp"] = int(cm[0,0]), int(cm[0,1]), int(cm[1,0]), int(cm[1,1])

        if self.n > 0:
            s["avg_loss"] = self.total_loss / self.n
        return s


# ═════════════════════════════════════════════════════════════════════════════
# Training
# ═════════════════════════════════════════════════════════════════════════════

def train_epoch(model, dl, optimizer, scheduler, loss_fn, device, metrics):
    model.train()
    metrics.reset()
    for batch in dl:
        cls_f = batch["cls_feat"].to(device)
        pool_f = batch["pool_feat"].to(device)
        w = batch["weather"].to(device)
        w7 = batch["weather_7d"].to(device)
        t = batch["terrain_global"].to(device)
        labels = batch["label"].to(device).float()

        out = model(cls_f, pool_f, w, w7, t)
        logit = out["logit"].squeeze(-1)
        loss = loss_fn(logit, labels)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if scheduler:
            scheduler.step()

        metrics.update(labels.long(), out["prob"].squeeze(-1), loss)

    return metrics.compute()


@torch.no_grad()
def eval_epoch(model, dl, loss_fn, device, metrics, threshold=0.5):
    model.eval()
    metrics.reset()
    for batch in dl:
        cls_f = batch["cls_feat"].to(device)
        pool_f = batch["pool_feat"].to(device)
        w = batch["weather"].to(device)
        w7 = batch["weather_7d"].to(device)
        t = batch["terrain_global"].to(device)
        labels = batch["label"].to(device).float()

        out = model(cls_f, pool_f, w, w7, t)
        logit = out["logit"].squeeze(-1)
        loss = loss_fn(logit, labels)
        metrics.update(labels.long(), out["prob"].squeeze(-1), loss)

    return metrics.compute(threshold)


def threshold_sweep(model, dl, device):
    model.eval()
    all_labels, all_probs = [], []
    with torch.no_grad():
        for batch in dl:
            cls_f = batch["cls_feat"].to(device)
            pool_f = batch["pool_feat"].to(device)
            w = batch["weather"].to(device)
            w7 = batch["weather_7d"].to(device)
            t = batch["terrain_global"].to(device)
            out = model(cls_f, pool_f, w, w7, t)
            all_labels.extend(batch["label"].numpy().tolist())
            all_probs.extend(out["prob"].squeeze(-1).cpu().numpy().tolist())

    y = np.array(all_labels)
    p = np.array(all_probs)

    log.info("\n" + "=" * 75)
    log.info("THRESHOLD SWEEP ON TEST SET")
    log.info("=" * 75)
    log.info(f"{'Thr':>6s}  {'Acc':>6s}  {'Prec':>6s}  {'Rec':>6s}  "
             f"{'F1':>6s}  {'TP':>4s}  {'FP':>4s}  {'FN':>4s}  {'TN':>4s}")
    log.info("-" * 75)

    best_f1, best_thr = -1, 0.5
    for thr in np.arange(0.1, 0.95, 0.05):
        preds = (p >= thr).astype(int)
        acc = accuracy_score(y, preds)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        f1 = f1_score(y, preds, zero_division=0)
        cm = confusion_matrix(y, preds, labels=[0, 1])
        tag = ""
        if f1 > best_f1:
            best_f1, best_thr = f1, thr
            tag = "  <-- BEST"
        log.info(f"  {thr:.2f}  {acc:6.3f}  {prec:6.3f}  {rec:6.3f}  "
                 f"{f1:6.3f}  {cm[1,1]:4d}  {cm[0,1]:4d}  {cm[1,0]:4d}  {cm[0,0]:4d}{tag}")

    log.info("-" * 75)
    if len(np.unique(y)) > 1:
        log.info(f"AUC-ROC: {roc_auc_score(y, p):.4f}  |  AUC-PR: {average_precision_score(y, p):.4f}")
    log.info(f"Best threshold: {best_thr:.2f}  (F1={best_f1:.4f})")
    log.info("=" * 75)
    return best_thr, best_f1


# ═════════════════════════════════════════════════════════════════════════════
# Linear Probe (diagnostic: are features separable at all?)
# ═════════════════════════════════════════════════════════════════════════════

def run_linear_probe(train_dl, val_dl, test_dl, device):
    """Quick sanity check: logistic regression on CLS features alone."""
    log.info("\n" + "=" * 65)
    log.info("LINEAR PROBE DIAGNOSTIC (CLS token only)")
    log.info("=" * 65)

    X_train, y_train = [], []
    for batch in train_dl:
        X_train.append(batch["cls_feat"].numpy())
        y_train.append(batch["label"].numpy())
    X_train = np.vstack(X_train)
    y_train = np.concatenate(y_train)

    X_test, y_test = [], []
    for batch in test_dl:
        X_test.append(batch["cls_feat"].numpy())
        y_test.append(batch["label"].numpy())
    X_test = np.vstack(X_test)
    y_test = np.concatenate(y_test)

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        clf = LogisticRegression(max_iter=1000, C=1.0)
        clf.fit(X_train_s, y_train)

        train_acc = clf.score(X_train_s, y_train)
        test_probs = clf.predict_proba(X_test_s)[:, 1]
        test_preds = clf.predict(X_test_s)
        test_acc = accuracy_score(y_test, test_preds)
        test_f1 = f1_score(y_test, test_preds)
        test_auc = roc_auc_score(y_test, test_probs) if len(np.unique(y_test)) > 1 else 0

        log.info(f"  Train acc:  {train_acc:.3f}")
        log.info(f"  Test  acc:  {test_acc:.3f}")
        log.info(f"  Test  F1:   {test_f1:.3f}")
        log.info(f"  Test  AUC:  {test_auc:.3f}")

        if test_auc < 0.60:
            log.info("  ⚠ CLS features are NOT discriminative — backbone needs fine-tuning")
        elif test_auc < 0.75:
            log.info("  ⚡ CLS features are weakly discriminative — MLP head can help")
        else:
            log.info("  ✓ CLS features are discriminative — MLP training should work well")

    except ImportError:
        log.warning("  sklearn not installed, skipping linear probe")

    log.info("=" * 65 + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="cached_v1")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden", type=int, default=256)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--no-linear-probe", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s][%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    manifest = ROOT / "data_lake" / "training_patches_v5" / "manifest.csv"
    cache_dir = ROOT / "data_lake" / "training_patches_v5" / "cls_features"

    if not cache_dir.exists():
        log.error(f"Cache dir not found: {cache_dir}")
        log.error("Run: python scripts/cache_cls_features.py")
        sys.exit(1)

    # Data
    train_ds = CachedClsDataset(manifest, cache_dir, "train", min_fire_pixels=25)
    val_ds = CachedClsDataset(manifest, cache_dir, "val", min_fire_pixels=0)
    test_ds = CachedClsDataset(manifest, cache_dir, "test", min_fire_pixels=0)

    train_dl = DataLoader(train_ds, batch_size=args.batch_size,
                          sampler=train_ds.make_sampler(), num_workers=0)
    val_dl = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)
    test_dl = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    log.info(f"Train: {len(train_ds)} | Val: {len(val_ds)} | Test: {len(test_ds)}")

    device = torch.device("cpu")  # Head is tiny, CPU is fine (avoids DML overhead)
    log.info(f"Training on: {device}  (head-only, no backbone)")

    # Linear probe diagnostic
    if not args.no_linear_probe:
        run_linear_probe(train_dl, val_dl, test_dl, device)

    # Model
    model = FireClsHead(
        embed_dim=1280, hidden=args.hidden, dropout=args.dropout,
    ).to(device)

    # Loss
    loss_fn = nn.BCEWithLogitsLoss()

    # Optimizer + scheduler
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(train_dl) * args.epochs
    warmup_steps = len(train_dl) * 5

    def lr_lambda(step):
        if step < warmup_steps:
            return float(step) / max(1, warmup_steps)
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return max(0.01, 0.5 * (1 + math.cos(math.pi * progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    # Output
    out_dir = ROOT / "outputs" / f"vanaagni_cls_{args.tag}"
    ckpt_dir = out_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Train
    log.info(f"\n{'='*65}")
    log.info(f"  Cached Feature Training  |  {args.epochs} epochs  |  lr={args.lr}")
    log.info(f"{'='*65}\n")

    metrics = Metrics()
    best_f1, best_epoch, no_improve = 0.0, 0, 0

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()

        train_s = train_epoch(model, train_dl, optimizer, scheduler, loss_fn, device, metrics)
        val_s = eval_epoch(model, val_dl, loss_fn, device, metrics)
        elapsed = time.time() - t0

        log.info(
            f"E{epoch:3d}/{args.epochs}  [{elapsed:.1f}s]  "
            f"trn_loss={train_s.get('avg_loss',0):.4f}  "
            f"val_loss={val_s.get('avg_loss',0):.4f}  "
            f"val_acc={val_s['accuracy']:.3f}  "
            f"val_F1={val_s['f1']:.3f}  "
            f"val_P={val_s['precision']:.3f}  val_R={val_s['recall']:.3f}  "
            f"val_AUC={val_s.get('auc_roc',0):.3f}"
        )

        if val_s["f1"] > best_f1:
            best_f1 = val_s["f1"]
            best_epoch = epoch
            no_improve = 0
            torch.save({
                "epoch": epoch, "best_f1": best_f1,
                "model_state": model.state_dict(),
                "args": vars(args),
            }, ckpt_dir / "best_cls.pth")
            log.info(f"  → BEST (F1={best_f1:.4f})")
        else:
            no_improve += 1

        if args.patience > 0 and no_improve >= args.patience:
            log.info(f"Early stopping at epoch {epoch}")
            break

    # Load best and evaluate test
    ckpt = torch.load(ckpt_dir / "best_cls.pth", weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    log.info(f"\nLoaded best checkpoint (epoch {best_epoch}, val_F1={best_f1:.4f})")

    test_s = eval_epoch(model, test_dl, loss_fn, device, metrics)
    log.info(f"\nTEST:  acc={test_s['accuracy']:.3f}  F1={test_s['f1']:.3f}  "
             f"P={test_s['precision']:.3f}  R={test_s['recall']:.3f}  "
             f"AUC-ROC={test_s.get('auc_roc',0):.4f}  AUC-PR={test_s.get('auc_pr',0):.4f}")
    log.info(f"Confusion: TP={test_s['tp']}  FP={test_s['fp']}  "
             f"FN={test_s['fn']}  TN={test_s['tn']}")

    best_thr, best_f1_test = threshold_sweep(model, test_dl, device)

    # Save results
    results = {
        "best_epoch": best_epoch,
        "best_val_f1": best_f1,
        "test": test_s,
        "best_threshold": float(best_thr),
        "best_test_f1": float(best_f1_test),
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"\nResults → {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
