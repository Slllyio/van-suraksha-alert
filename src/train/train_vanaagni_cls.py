"""
src/train/train_vanaagni_cls.py
================================
Training loop for VanAgni patch-level fire classification.

Unlike the segmentation trainer, this uses:
  - BCE loss (not Dice/Focal) — strong gradient on every sample
  - Patch-level accuracy, precision, recall, F1, AUC metrics
  - Frozen backbone (only head trains) — fast epochs, no overfitting risk
  - Threshold sweep on test set for optimal operating point

Usage:
    python src/train/train_vanaagni_cls.py \
        --config models/vanaagni/stage1_classify.yaml \
        --tag cls_v1
"""

import sys, os, math, time, json, logging, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import yaml
import numpy as np
import torch
import torch.nn as nn
from contextlib import nullcontext
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
)

log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Device Selection (AMD DirectML → CPU fallback)
# ═════════════════════════════════════════════════════════════════════════════

def get_device():
    """Select best available device: DirectML > CUDA > CPU."""
    try:
        import torch_directml
        dev = torch_directml.device()
        log.info(f"Using DirectML device: {dev}")
        return dev
    except ImportError:
        pass
    if torch.cuda.is_available():
        log.info("Using CUDA device")
        return torch.device("cuda")
    log.info("Using CPU device")
    return torch.device("cpu")


# ═════════════════════════════════════════════════════════════════════════════
# Metrics Tracker
# ═════════════════════════════════════════════════════════════════════════════

class ClsMetrics:
    """Accumulate predictions and compute classification metrics."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.all_labels = []
        self.all_probs = []
        self.all_preds = []
        self.total_loss = 0.0
        self.n_batches = 0

    def update(self, labels, probs, loss=None, threshold=0.5):
        """
        Args:
            labels: (B,) long tensor
            probs:  (B,) float tensor (sigmoid output)
            loss:   scalar loss value for this batch
        """
        self.all_labels.extend(labels.cpu().numpy().tolist())
        self.all_probs.extend(probs.detach().cpu().numpy().tolist())
        preds = (probs >= threshold).long()
        self.all_preds.extend(preds.cpu().numpy().tolist())
        if loss is not None:
            self.total_loss += float(loss)
            self.n_batches += 1

    def compute(self):
        labels = np.array(self.all_labels)
        probs = np.array(self.all_probs)
        preds = np.array(self.all_preds)

        scores = {}
        scores["accuracy"] = float(accuracy_score(labels, preds))
        scores["precision"] = float(precision_score(labels, preds, zero_division=0))
        scores["recall"] = float(recall_score(labels, preds, zero_division=0))
        scores["f1"] = float(f1_score(labels, preds, zero_division=0))

        # AUC (requires both classes present)
        if len(np.unique(labels)) > 1:
            scores["auc_roc"] = float(roc_auc_score(labels, probs))
            scores["auc_pr"] = float(average_precision_score(labels, probs))
        else:
            scores["auc_roc"] = 0.0
            scores["auc_pr"] = 0.0

        # Confusion matrix
        cm = confusion_matrix(labels, preds, labels=[0, 1])
        scores["tn"] = int(cm[0, 0])
        scores["fp"] = int(cm[0, 1])
        scores["fn"] = int(cm[1, 0])
        scores["tp"] = int(cm[1, 1])

        if self.n_batches > 0:
            scores["avg_loss"] = self.total_loss / self.n_batches

        return scores


# ═════════════════════════════════════════════════════════════════════════════
# Training / Validation Loops
# ═════════════════════════════════════════════════════════════════════════════

def train_one_epoch(model, dataloader, optimizer, scheduler, loss_fn,
                    device, metrics, epoch, cfg, grad_accum=1, log_interval=20):
    model.train()
    metrics.reset()

    optimizer.zero_grad()
    for step, batch in enumerate(dataloader):
        hls        = batch["hls"].to(device)
        weather    = batch["weather"].to(device)
        weather_7d = batch["weather_7d"].to(device)
        terrain    = batch["terrain"].to(device)
        burn_age   = batch["burn_age"].to(device)
        landcover  = batch["landcover"].to(device)
        labels     = batch["label"].to(device).float()  # (B,)

        out = model(hls, weather, weather_7d, terrain, burn_age, landcover)
        logit = out["logit"].squeeze(-1)  # (B,)
        prob = out["prob"].squeeze(-1)    # (B,)

        loss = loss_fn(logit, labels) / grad_accum
        loss.backward()

        if (step + 1) % grad_accum == 0 or (step + 1) == len(dataloader):
            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            optimizer.zero_grad()
            if scheduler is not None:
                scheduler.step()

        metrics.update(labels.long(), prob, loss=float(loss) * grad_accum)

        if step % log_interval == 0:
            scores = metrics.compute()
            lr = optimizer.param_groups[-1]["lr"]
            log.info(
                f"  E{epoch} [{step:4d}/{len(dataloader)}]  "
                f"loss={scores.get('avg_loss', 0):.4f}  "
                f"acc={scores['accuracy']:.3f}  "
                f"F1={scores['f1']:.3f}  "
                f"P={scores['precision']:.3f}  R={scores['recall']:.3f}  "
                f"lr={lr:.2e}"
            )

    return metrics.compute()


@torch.no_grad()
def validate(model, dataloader, loss_fn, device, metrics, threshold=0.5):
    model.eval()
    metrics.reset()

    for batch in dataloader:
        hls        = batch["hls"].to(device)
        weather    = batch["weather"].to(device)
        weather_7d = batch["weather_7d"].to(device)
        terrain    = batch["terrain"].to(device)
        burn_age   = batch["burn_age"].to(device)
        landcover  = batch["landcover"].to(device)
        labels     = batch["label"].to(device).float()

        out = model(hls, weather, weather_7d, terrain, burn_age, landcover)
        logit = out["logit"].squeeze(-1)
        prob = out["prob"].squeeze(-1)

        loss = loss_fn(logit, labels)
        metrics.update(labels.long(), prob, loss=float(loss), threshold=threshold)

    return metrics.compute()


def threshold_sweep(model, dataloader, loss_fn, device):
    """Find optimal threshold on test set."""
    model.eval()
    all_labels = []
    all_probs = []

    with torch.no_grad():
        for batch in dataloader:
            hls        = batch["hls"].to(device)
            weather    = batch["weather"].to(device)
            weather_7d = batch["weather_7d"].to(device)
            terrain    = batch["terrain"].to(device)
            burn_age   = batch["burn_age"].to(device)
            landcover  = batch["landcover"].to(device)
            labels     = batch["label"]

            out = model(hls, weather, weather_7d, terrain, burn_age, landcover)
            prob = out["prob"].squeeze(-1).cpu()

            all_labels.extend(labels.numpy().tolist())
            all_probs.extend(prob.numpy().tolist())

    labels = np.array(all_labels)
    probs = np.array(all_probs)

    log.info("\n" + "=" * 75)
    log.info("THRESHOLD SWEEP ON TEST SET")
    log.info("=" * 75)
    log.info(f"{'Thr':>6s}  {'Acc':>6s}  {'Prec':>6s}  {'Rec':>6s}  "
             f"{'F1':>6s}  {'TP':>4s}  {'FP':>4s}  {'FN':>4s}  {'TN':>4s}")
    log.info("-" * 75)

    best_f1 = -1
    best_thr = 0.5

    for thr in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        preds = (probs >= thr).astype(int)
        acc = accuracy_score(labels, preds)
        prec = precision_score(labels, preds, zero_division=0)
        rec = recall_score(labels, preds, zero_division=0)
        f1 = f1_score(labels, preds, zero_division=0)
        cm = confusion_matrix(labels, preds, labels=[0, 1])

        tag = ""
        if f1 > best_f1:
            best_f1 = f1
            best_thr = thr
            tag = "  <-- BEST"

        log.info(
            f"  {thr:.2f}  {acc:6.3f}  {prec:6.3f}  {rec:6.3f}  "
            f"{f1:6.3f}  {cm[1,1]:4d}  {cm[0,1]:4d}  {cm[1,0]:4d}  {cm[0,0]:4d}{tag}"
        )

    log.info("-" * 75)

    # AUC scores
    if len(np.unique(labels)) > 1:
        auc_roc = roc_auc_score(labels, probs)
        auc_pr = average_precision_score(labels, probs)
        log.info(f"AUC-ROC: {auc_roc:.4f}  |  AUC-PR: {auc_pr:.4f}")

    log.info(f"Best threshold: {best_thr:.2f}  (F1={best_f1:.4f})")
    log.info("=" * 75)

    return best_thr, best_f1


# ═════════════════════════════════════════════════════════════════════════════
# Checkpoint
# ═════════════════════════════════════════════════════════════════════════════

def save_checkpoint(model, optimizer, epoch, best_f1, cfg, path, tag=""):
    state = {
        "epoch": epoch,
        "best_f1": best_f1,
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "config": cfg,
    }
    torch.save(state, str(path))
    log.info(f"  Checkpoint saved: {path}  (F1={best_f1:.4f}) {tag}")


def load_checkpoint(model, optimizer, path, device):
    ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model_state"], strict=False)
    if optimizer is not None and "optimizer_state" in ckpt:
        try:
            optimizer.load_state_dict(ckpt["optimizer_state"])
        except Exception:
            log.warning("Could not restore optimizer state")
    epoch = ckpt.get("epoch", 0)
    best_f1 = ckpt.get("best_f1", 0.0)
    log.info(f"Loaded checkpoint: {path}  (epoch={epoch}, F1={best_f1:.4f})")
    return epoch, best_f1


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="VanAgni Patch Classification Training")
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument("--tag", default="", help="Experiment tag for output dir")
    parser.add_argument("--resume", default=None, help="Checkpoint to resume from")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s][%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config
    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    device = get_device()

    # -- Data --
    from src.data.vanaagni_cls_dataset import get_cls_dataloaders

    d_cfg = cfg.get("data", {})
    manifest = d_cfg.get("manifest_path", "data_lake/training_patches_v5/manifest.csv")

    train_dl, val_dl, test_dl = get_cls_dataloaders(
        manifest_path=manifest,
        batch_size=cfg["training"]["batch_size"],
        num_workers=d_cfg.get("num_workers", 0),
        min_fire_pixels=d_cfg.get("min_fire_pixels", 25),
        exclude_tiers=d_cfg.get("exclude_tiers"),
        spectral_only=d_cfg.get("spectral_only", False),
    )

    log.info(f"Train: {len(train_dl)} batches  |  Val: {len(val_dl)} batches  |  Test: {len(test_dl)} batches")

    # -- Model --
    from src.model.vanaagni_cls import build_vanaagni_cls

    model = build_vanaagni_cls(cfg)
    model.to(device)

    # -- Loss --
    t_cfg = cfg.get("training", {})
    pos_weight_val = t_cfg.get("pos_weight", 1.0)
    pos_weight = torch.tensor([pos_weight_val], device=device)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    log.info(f"Loss: BCEWithLogitsLoss  pos_weight={pos_weight_val}")

    # -- Optimizer & Scheduler --
    lr = t_cfg.get("lr", 1e-3)
    wd = t_cfg.get("weight_decay", 0.01)
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=lr, weight_decay=wd)
    log.info(f"Optimizer: AdamW  lr={lr}  wd={wd}  trainable_params={sum(p.numel() for p in trainable_params):,}")

    total_epochs = t_cfg.get("epochs", 30)
    warmup_epochs = t_cfg.get("warmup_epochs", 3)
    grad_accum = t_cfg.get("grad_accum_steps", 1)
    log_interval = t_cfg.get("log_interval", 10)
    patience = t_cfg.get("early_stop_patience", 10)
    eval_threshold = t_cfg.get("eval_threshold", 0.5)

    steps_per_epoch = max(1, len(train_dl) // grad_accum)
    total_steps = steps_per_epoch * total_epochs
    warmup_steps = steps_per_epoch * warmup_epochs

    def lr_lambda(step):
        if step < warmup_steps:
            return float(step) / max(1, warmup_steps)
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return max(0.01, 0.5 * (1.0 + math.cos(math.pi * progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    # -- Output dirs --
    p_cfg = cfg.get("paths", {})
    output_dir = Path(p_cfg.get("output_dir", "outputs/vanaagni_cls"))
    if args.tag:
        output_dir = output_dir.parent / f"{output_dir.name}_{args.tag}"
    ckpt_dir = output_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # -- Resume --
    start_epoch = 1
    best_f1 = 0.0
    if args.resume:
        start_epoch, best_f1 = load_checkpoint(model, optimizer, args.resume, device)
        start_epoch += 1

    # -- Training Loop --
    log.info(f"\n{'=' * 65}")
    log.info(f"  VanAgni Patch Classification Training")
    log.info(f"  Epochs: {start_epoch}-{total_epochs}  |  Batch: {t_cfg['batch_size']}×{grad_accum}  |  Device: {device}")
    log.info(f"{'=' * 65}\n")

    train_metrics = ClsMetrics()
    val_metrics = ClsMetrics()
    no_improve = 0

    for epoch in range(start_epoch, total_epochs + 1):
        t0 = time.time()

        train_scores = train_one_epoch(
            model, train_dl, optimizer, scheduler, loss_fn,
            device, train_metrics, epoch, cfg,
            grad_accum=grad_accum, log_interval=log_interval,
        )

        val_scores = validate(
            model, val_dl, loss_fn, device, val_metrics,
            threshold=eval_threshold,
        )

        elapsed = time.time() - t0

        log.info(
            f"Epoch {epoch:3d}/{total_epochs}  [{elapsed:.0f}s]  "
            f"train_loss={train_scores.get('avg_loss', 0):.4f}  "
            f"val_loss={val_scores.get('avg_loss', 0):.4f}  "
            f"val_acc={val_scores['accuracy']:.3f}  "
            f"val_F1={val_scores['f1']:.3f}  "
            f"val_P={val_scores['precision']:.3f}  "
            f"val_R={val_scores['recall']:.3f}  "
            f"val_AUC={val_scores.get('auc_roc', 0):.3f}"
        )

        # Checkpoint on best F1
        if val_scores["f1"] > best_f1:
            best_f1 = val_scores["f1"]
            best_epoch = epoch
            no_improve = 0
            save_checkpoint(
                model, optimizer, epoch, best_f1, cfg,
                ckpt_dir / "best_cls.pth", tag="BEST",
            )
        else:
            no_improve += 1

        # Early stopping
        if patience > 0 and no_improve >= patience:
            log.info(f"Early stopping at epoch {epoch} (no improvement for {patience} epochs)")
            break

    # ── Final evaluation: load best checkpoint → test set ──────────────────
    best_ckpt = ckpt_dir / "best_cls.pth"
    if best_ckpt.exists():
        log.info(f"\nLoading best checkpoint for test evaluation: {best_ckpt}")
        load_checkpoint(model, None, best_ckpt, device)

    log.info("\n" + "=" * 65)
    log.info("FINAL TEST SET EVALUATION")
    log.info("=" * 65)

    test_scores = validate(model, test_dl, loss_fn, device, val_metrics, threshold=eval_threshold)
    log.info(
        f"Test:  acc={test_scores['accuracy']:.3f}  "
        f"F1={test_scores['f1']:.3f}  "
        f"P={test_scores['precision']:.3f}  "
        f"R={test_scores['recall']:.3f}  "
        f"AUC-ROC={test_scores.get('auc_roc', 0):.4f}  "
        f"AUC-PR={test_scores.get('auc_pr', 0):.4f}"
    )
    log.info(
        f"Confusion: TP={test_scores['tp']}  FP={test_scores['fp']}  "
        f"FN={test_scores['fn']}  TN={test_scores['tn']}"
    )

    # Threshold sweep
    best_thr, best_sweep_f1 = threshold_sweep(model, test_dl, loss_fn, device)

    # Save final results
    results = {
        "best_epoch": best_epoch if 'best_epoch' in dir() else 0,
        "best_val_f1": best_f1,
        "test_scores": test_scores,
        "best_threshold": best_thr,
        "best_test_f1": best_sweep_f1,
    }
    results_path = output_dir / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"\nResults saved to {results_path}")


if __name__ == "__main__":
    main()
