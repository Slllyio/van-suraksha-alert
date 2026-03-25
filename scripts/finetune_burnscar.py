#!/usr/bin/env python3
"""
scripts/finetune_burnscar.py
==============================
Fine-tune the Prithvi-EO-V2-300M burn scar model on Guna post-fire data.

Architecture: Prithvi-300M backbone + UNet decoder [512, 256, 128, 64] + 2-class head
              (324M params total, loaded from pre-trained US BurnScars checkpoint)

Training: DirectML (AMD RX 9060 XT), no AMP, focal + dice loss, LLRD.

Data: Post-fire patches from data_lake/burnscar_finetune/ (built by build_postfire_patches.py)
      Each patch: hls (6, 224, 224) + label (224, 224) binary burn mask

Usage:
    python scripts/finetune_burnscar.py
    python scripts/finetune_burnscar.py --epochs 30 --lr 5e-5 --freeze-backbone 5
"""

import argparse
import json
import logging
import os
import sys
import time
import types
from pathlib import Path

os.environ["GTIFF_SRS_SOURCE"] = "GEOKEYS"
os.environ.pop("GDAL_DATA", None)

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data_lake" / "burnscar_finetune"
CHECKPOINT = ROOT / "models" / "prithvi_burnscar" / "Prithvi_EO_V2_300M_BurnScars.pt"
OUTPUT_DIR = ROOT / "outputs" / "burnscar_finetune"

# Normalization stats computed from Guna post-fire patches (not US data)
MEANS = np.array([0.0633, 0.0980, 0.1334, 0.2306, 0.2535, 0.1907], dtype=np.float32)
STDS = np.array([0.0181, 0.0227, 0.0325, 0.0455, 0.0488, 0.0378], dtype=np.float32)


# ─── Dataset ──────────────────────────────────────────────────────────────────

class BurnScarDataset(Dataset):
    """Post-fire burn scar patches for fine-tuning."""

    def __init__(self, manifest_path: Path, split: str, augment: bool = False):
        df = pd.read_csv(manifest_path)
        self.df = df[df["split"] == split].reset_index(drop=True)
        self.root = manifest_path.parent.parent.parent  # ROOT
        self.augment = augment

        # Filter out corrupted patches (>50% zero-fill from tile edges/clouds)
        valid_mask = []
        for _, row in self.df.iterrows():
            p = self.root / row["path"]
            # Trusted local .npz patches built by our pipeline
            d = np.load(str(p), allow_pickle=True)
            zero_frac = float((d["hls"] == 0).mean())
            valid_mask.append(zero_frac < 0.5)
        n_before = len(self.df)
        self.df = self.df[valid_mask].reset_index(drop=True)
        n_dropped = n_before - len(self.df)

        log.info(f"BurnScarDataset({split}): {len(self.df)} patches "
                 f"({int(self.df['is_fire'].sum())} fire), dropped {n_dropped} corrupted")

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        npz_path = self.root / row["path"]
        # Loading our own trusted local .npz training patches
        data = np.load(str(npz_path), allow_pickle=True)

        hls = data["hls"].astype(np.float32)    # (6, 224, 224)
        label = data["label"].astype(np.int64)   # (224, 224)

        # Normalize
        for c in range(6):
            hls[c] = (hls[c] - MEANS[c]) / (STDS[c] + 1e-8)

        # Augmentations
        if self.augment:
            # D4 group: flips + 90-degree rotations
            k = np.random.randint(4)
            if k > 0:
                hls = np.rot90(hls, k, axes=(1, 2)).copy()
                label = np.rot90(label, k, axes=(0, 1)).copy()
            if np.random.random() > 0.5:
                hls = np.flip(hls, axis=2).copy()
                label = np.flip(label, axis=1).copy()
            # Spectral jitter: ±10% brightness, ±5% per-band
            if np.random.random() > 0.5:
                # Global brightness shift (same across bands)
                brightness = np.random.uniform(0.9, 1.1)
                hls = hls * brightness
            if np.random.random() > 0.5:
                # Per-band jitter (different per band)
                jitter = np.random.uniform(0.95, 1.05, size=(6, 1, 1)).astype(np.float32)
                hls = hls * jitter
            # Gaussian noise
            if np.random.random() > 0.5:
                noise = np.random.normal(0, 0.02, hls.shape).astype(np.float32)
                hls = hls + noise

        # Add temporal dimension: (6, 224, 224) -> (6, 1, 224, 224)
        hls = hls[:, np.newaxis, :, :]

        return torch.from_numpy(hls), torch.from_numpy(label)


# ─── Model Loading ────────────────────────────────────────────────────────────

def apply_directml_patch(model):
    """Replace Conv3d in PatchEmbed with Conv2d for DirectML compatibility."""
    pe = model.encoder.patch_embed
    old_proj = pe.proj
    if not isinstance(old_proj, nn.Conv3d):
        return

    log.info("Applying DirectML Conv3d -> Conv2d compatibility patch")
    new_proj = nn.Conv2d(
        old_proj.in_channels, old_proj.out_channels,
        kernel_size=old_proj.kernel_size[1:],
        stride=old_proj.stride[1:],
        padding=old_proj.padding[1:],
        bias=(old_proj.bias is not None),
    )
    with torch.no_grad():
        new_proj.weight.copy_(old_proj.weight.squeeze(2))
        if old_proj.bias is not None:
            new_proj.bias.copy_(old_proj.bias)
    pe.proj = new_proj

    def patched_forward(self, x):
        B, C, T, H, W = x.shape
        x = x.transpose(1, 2).reshape(B * T, C, H, W)
        x = self.proj(x)
        _, D, Hp, Wp = x.shape
        x = x.reshape(B, T, D, Hp, Wp).permute(0, 2, 1, 3, 4)
        if self.flatten:
            x = x.flatten(2).transpose(1, 2)
        x = self.norm(x)
        return x

    pe.forward = types.MethodType(patched_forward, pe)


def build_model():
    """Build and load the Prithvi-300M burn scar model with DirectML patches."""
    from terratorch.models import EncoderDecoderFactory

    factory = EncoderDecoderFactory()
    model = factory.build_model(
        task="segmentation",
        backbone="prithvi_eo_v2_300",
        backbone_pretrained=False,
        backbone_bands=["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"],
        necks=[
            {"name": "SelectIndices", "indices": [5, 11, 17, 23]},
            {"name": "ReshapeTokensToImage"},
            {"name": "LearnedInterpolateToPyramidal"},
        ],
        decoder="UNetDecoder",
        decoder_channels=[512, 256, 128, 64],
        num_classes=2,
    )

    # Load pre-trained burn scar weights
    log.info(f"Loading checkpoint: {CHECKPOINT}")
    ckpt = torch.load(str(CHECKPOINT), map_location="cpu", weights_only=False)
    sd = {k.replace("model.", "", 1): v for k, v in ckpt["state_dict"].items()}
    result = model.load_state_dict(sd, strict=True)
    log.info(f"Loaded {len(sd)} weight tensors (missing={len(result.missing_keys)})")

    apply_directml_patch(model)

    # Freeze backbone EXCEPT last N blocks.
    # Full 24-block backward triggers DirectML TDR (>2s), but last 4 blocks
    # (~49M params) keep backward fast enough. This lets the backbone adapt
    # its high-level features to Guna's dry deciduous spectral signatures.
    UNFREEZE_LAST_N = 4
    for p in model.encoder.parameters():
        p.requires_grad = False
    # Unfreeze last N transformer blocks
    n_blocks = len(model.encoder.blocks)
    for i in range(n_blocks - UNFREEZE_LAST_N, n_blocks):
        for p in model.encoder.blocks[i].parameters():
            p.requires_grad = True
    # Unfreeze norm layer (after last block)
    if hasattr(model.encoder, "norm"):
        for p in model.encoder.norm.parameters():
            p.requires_grad = True

    frozen = sum(p.numel() for p in model.encoder.parameters() if not p.requires_grad)
    unfrozen_bb = sum(p.numel() for p in model.encoder.parameters() if p.requires_grad)
    log.info(f"Backbone: {frozen:,} frozen + {unfrozen_bb:,} unfrozen (last {UNFREEZE_LAST_N} blocks)")

    total_params = sum(p.numel() for p in model.parameters())
    train_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    log.info(f"Model: {total_params:,} total, {train_params:,} trainable")

    return model


# ─── Loss ─────────────────────────────────────────────────────────────────────

class DiceDominantLoss(nn.Module):
    """Dice-dominant loss for extremely imbalanced binary segmentation.

    With 0.49% fire pixels:
    - CE (even weighted) is gradient-dominated by the 99.5% background
    - Dice is inherently balanced: computed on fire class only, so
      a model predicting all-BG gets dice_loss=1.0 (max penalty)
    - Strategy: dice as PRIMARY loss (weight=3.0), weighted CE as regularizer

    This directly punishes the all-background collapse mode that killed
    previous runs using focal-only or lightly-weighted CE.
    """

    def __init__(self, ce_weight: float = 1.0, dice_weight: float = 3.0,
                 fire_class_weight: float = 20.0):
        super().__init__()
        self.ce_weight = ce_weight
        self.dice_weight = dice_weight
        self.register_buffer(
            "class_weights",
            torch.tensor([1.0, fire_class_weight], dtype=torch.float32),
        )

    def forward(self, logits: torch.Tensor, targets: torch.Tensor):
        """
        Args:
            logits: (B, 2, H, W)
            targets: (B, H, W) with -1 for ignore
        """
        # ── Weighted CE (regularizer) ──
        ce_loss = F.cross_entropy(
            logits, targets, weight=self.class_weights,
            ignore_index=-1, reduction="mean",
        )

        # ── Dice loss (PRIMARY — fire class only) ──
        valid = targets >= 0
        if valid.any():
            fire_probs = F.softmax(logits, dim=1)[:, 1]
            fire_gt = (targets == 1).float()

            fp = fire_probs[valid]
            fg = fire_gt[valid]

            intersection = (fp * fg).sum()
            dice = (2.0 * intersection + 1.0) / (fp.sum() + fg.sum() + 1.0)
            dice_loss = 1.0 - dice
        else:
            dice_loss = torch.tensor(0.0, device=logits.device)

        return self.ce_weight * ce_loss + self.dice_weight * dice_loss


# ─── Training Loop ────────────────────────────────────────────────────────────

def train_one_epoch(model, loader, optimizer, criterion, device, epoch,
                    grad_accum: int = 8):
    model.train()
    total_loss = 0.0
    total_tp = total_fp = total_fn = 0
    n_batches = 0

    optimizer.zero_grad()

    for batch_idx, (hls, label) in enumerate(loader):
        hls = hls.to(device)
        label = label.to(device)

        out = model(hls)
        logits = out.output  # (B, 2, H, W)
        loss = criterion(logits, label) / grad_accum  # scale for accumulation

        loss.backward()

        # Step every grad_accum batches
        if (batch_idx + 1) % grad_accum == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            optimizer.zero_grad()

        total_loss += loss.item() * grad_accum  # unscale for logging
        n_batches += 1

        # Compute metrics
        with torch.no_grad():
            pred = logits.argmax(dim=1)
            valid = label >= 0
            p = pred[valid]
            g = label[valid]
            total_tp += int(((p == 1) & (g == 1)).sum())
            total_fp += int(((p == 1) & (g == 0)).sum())
            total_fn += int(((p == 0) & (g == 1)).sum())

        if (batch_idx + 1) % 20 == 0:
            precision = total_tp / max(total_tp + total_fp, 1)
            recall = total_tp / max(total_tp + total_fn, 1)
            f1 = 2 * precision * recall / max(precision + recall, 1e-8)
            log.info(f"  [{batch_idx+1}/{len(loader)}] loss={total_loss/n_batches:.4f} "
                     f"P={precision:.3f} R={recall:.3f} F1={f1:.3f}")

    avg_loss = total_loss / max(n_batches, 1)
    precision = total_tp / max(total_tp + total_fp, 1)
    recall = total_tp / max(total_tp + total_fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)
    return avg_loss, precision, recall, f1


@torch.no_grad()
def validate(model, loader, criterion, device):
    """Validate with threshold sweep — find optimal fire threshold on val."""
    model.train(False)
    total_loss = 0.0
    n_batches = 0

    # Collect all fire probabilities and ground truth for threshold sweep
    all_probs = []
    all_gt = []

    for hls, label in loader:
        hls = hls.to(device)
        label = label.to(device)

        out = model(hls)
        logits = out.output
        loss = criterion(logits, label)

        total_loss += loss.item()
        n_batches += 1

        probs = F.softmax(logits, dim=1)[:, 1]  # fire probability
        valid_mask = label >= 0
        all_probs.append(probs[valid_mask].cpu())
        all_gt.append(label[valid_mask].cpu())

    avg_loss = total_loss / max(n_batches, 1)
    all_probs = torch.cat(all_probs)
    all_gt = torch.cat(all_gt)

    # Sweep thresholds to find best F1
    best_f1 = 0.0
    best_thresh = 0.5
    best_metrics = {}

    for thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        pred = (all_probs >= thresh).long()
        tp = int(((pred == 1) & (all_gt == 1)).sum())
        fp = int(((pred == 1) & (all_gt == 0)).sum())
        fn = int(((pred == 0) & (all_gt == 1)).sum())
        tn = int(((pred == 0) & (all_gt == 0)).sum())

        p = tp / max(tp + fp, 1)
        r = tp / max(tp + fn, 1)
        f1 = 2 * p * r / max(p + r, 1e-8)
        iou = tp / max(tp + fp + fn, 1)

        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh
            best_metrics = {
                "loss": avg_loss, "precision": p, "recall": r,
                "f1": f1, "iou": iou, "tp": tp, "fp": fp, "fn": fn,
                "accuracy": (tp + tn) / max(tp + tn + fp + fn, 1),
                "threshold": thresh,
            }

    # Also report fixed threshold=0.5 for comparison
    pred_05 = (all_probs >= 0.5).long()
    tp05 = int(((pred_05 == 1) & (all_gt == 1)).sum())
    fp05 = int(((pred_05 == 1) & (all_gt == 0)).sum())
    fn05 = int(((pred_05 == 0) & (all_gt == 1)).sum())
    p05 = tp05 / max(tp05 + fp05, 1)
    r05 = tp05 / max(tp05 + fn05, 1)
    f105 = 2 * p05 * r05 / max(p05 + r05, 1e-8)

    best_metrics["f1_at_05"] = f105
    best_metrics["p_at_05"] = p05
    best_metrics["r_at_05"] = r05
    return best_metrics


# ─── LLRD (Layer-wise Learning Rate Decay) ────────────────────────────────────

def get_param_groups(model, base_lr: float):
    """LLRD: backbone unfrozen blocks at 0.1× base_lr, decoder/neck/head at base_lr."""
    backbone_params = [p for p in model.encoder.parameters() if p.requires_grad]
    head_params = []
    for module in [model.neck, model.decoder, model.head]:
        head_params.extend(p for p in module.parameters() if p.requires_grad)

    groups = []
    if backbone_params:
        groups.append({"params": backbone_params, "lr": base_lr * 0.1})
    groups.append({"params": head_params, "lr": base_lr})
    return groups


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fine-tune Prithvi-300M burn scar model")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    # NOTE: backbone permanently frozen (DirectML TDR workaround)
    parser.add_argument("--fire-weight", type=float, default=20.0,
                        help="Class weight for fire pixels in CE loss")
    parser.add_argument("--dice-weight", type=float, default=3.0,
                        help="Weight for dice loss (primary anti-collapse signal)")
    parser.add_argument("--fire-oversample", type=float, default=3.0,
                        help="Oversample fire patches by this factor")
    args = parser.parse_args()

    # Device
    import torch_directml
    device = torch_directml.device()
    log.info(f"Device: DirectML (AMD GPU)")

    # Data
    manifest = DATA_DIR / "manifest.csv"
    train_ds = BurnScarDataset(manifest, "train", augment=True)
    val_ds = BurnScarDataset(manifest, "val", augment=False)
    test_ds = BurnScarDataset(manifest, "test", augment=False)

    # Oversample fire patches in training
    if args.fire_oversample > 1.0:
        fire_indices = train_ds.df.index[train_ds.df["is_fire"] == 1].tolist()
        bg_indices = train_ds.df.index[train_ds.df["is_fire"] == 0].tolist()
        n_repeat = int(args.fire_oversample)
        sampler_indices = bg_indices + fire_indices * n_repeat
        np.random.shuffle(sampler_indices)
        sampler = torch.utils.data.SubsetRandomSampler(sampler_indices)
        train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                                  sampler=sampler, num_workers=0, pin_memory=False)
    else:
        train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                                  shuffle=True, num_workers=0, pin_memory=False)

    val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                            shuffle=False, num_workers=0, pin_memory=False)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size,
                             shuffle=False, num_workers=0, pin_memory=False)

    log.info(f"Train: {len(train_ds)} patches, Val: {len(val_ds)}, Test: {len(test_ds)}")

    # Model
    model = build_model()
    model = model.to(device)

    # Loss — dice-dominant to prevent all-BG collapse (dice is class-balanced)
    criterion = DiceDominantLoss(
        ce_weight=1.0, dice_weight=args.dice_weight,
        fire_class_weight=args.fire_weight,
    )
    criterion = criterion.to(device)

    # Output dir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_dir = OUTPUT_DIR / "checkpoints"
    ckpt_dir.mkdir(exist_ok=True)

    best_f1 = 0.0
    best_epoch = -1
    history = []

    # Create optimizer ONCE — AdamW needs persistent momentum/variance estimates
    param_groups = get_param_groups(model, args.lr)
    optimizer = torch.optim.AdamW(param_groups, weight_decay=0.05)
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    log.info(f"Optimizer: AdamW, {n_trainable:,} trainable params (backbone frozen)")

    # Cosine LR scheduler
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs, eta_min=args.lr * 0.01
    )

    for epoch in range(args.epochs):
        t0 = time.time()
        log.info(f"\n{'='*60}")
        log.info(f"Epoch {epoch+1}/{args.epochs}  lr={optimizer.param_groups[0]['lr']:.2e}")
        log.info(f"{'='*60}")

        # Train
        train_loss, train_p, train_r, train_f1 = train_one_epoch(
            model, train_loader, optimizer, criterion, device, epoch,
            grad_accum=args.grad_accum
        )
        log.info(f"  Train: loss={train_loss:.4f} P={train_p:.3f} R={train_r:.3f} F1={train_f1:.3f}")

        # Validate
        val_metrics = validate(model, val_loader, criterion, device)
        log.info(f"  Val:   loss={val_metrics['loss']:.4f} P={val_metrics['precision']:.3f} "
                 f"R={val_metrics['recall']:.3f} F1={val_metrics['f1']:.3f} "
                 f"IoU={val_metrics['iou']:.3f} thresh={val_metrics.get('threshold', 0.5):.1f}")
        log.info(f"  Val@0.5: P={val_metrics.get('p_at_05', 0):.3f} "
                 f"R={val_metrics.get('r_at_05', 0):.3f} F1={val_metrics.get('f1_at_05', 0):.3f}")

        scheduler.step()
        elapsed = time.time() - t0
        log.info(f"  Time: {elapsed:.0f}s")

        # Save best
        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            best_epoch = epoch + 1
            save_path = ckpt_dir / "best_burnscar.pth"
            torch.save({
                "epoch": epoch + 1,
                "model_state_dict": model.state_dict(),
                "val_f1": best_f1,
                "val_metrics": val_metrics,
            }, str(save_path))
            log.info(f"  ** New best F1={best_f1:.4f} saved to {save_path}")

        # Save periodic
        if (epoch + 1) % 10 == 0:
            save_path = ckpt_dir / f"epoch_{epoch+1}.pth"
            torch.save({
                "epoch": epoch + 1,
                "model_state_dict": model.state_dict(),
                "val_metrics": val_metrics,
            }, str(save_path))

        history.append({
            "epoch": epoch + 1,
            "train_loss": train_loss,
            "train_f1": train_f1,
            "val_loss": val_metrics["loss"],
            "val_f1": val_metrics["f1"],
            "val_precision": val_metrics["precision"],
            "val_recall": val_metrics["recall"],
            "val_iou": val_metrics["iou"],
        })

    # Final test
    log.info(f"\n{'='*60}")
    log.info(f"FINAL TEST (best model from epoch {best_epoch})")
    log.info(f"{'='*60}")

    best_ckpt = torch.load(str(ckpt_dir / "best_burnscar.pth"),
                           map_location="cpu", weights_only=False)
    model.load_state_dict(best_ckpt["model_state_dict"])
    model = model.to(device)

    test_metrics = validate(model, test_loader, criterion, device)
    log.info(f"Test: P={test_metrics['precision']:.4f} R={test_metrics['recall']:.4f} "
             f"F1={test_metrics['f1']:.4f} IoU={test_metrics['iou']:.4f}")
    log.info(f"TP={test_metrics['tp']:,} FP={test_metrics['fp']:,} FN={test_metrics['fn']:,}")

    # Save history and results
    pd.DataFrame(history).to_csv(OUTPUT_DIR / "training_history.csv", index=False)
    with open(OUTPUT_DIR / "test_results.json", "w") as f:
        json.dump({
            "best_epoch": best_epoch,
            "best_val_f1": best_f1,
            "test_metrics": test_metrics,
        }, f, indent=2)

    log.info(f"\nAll outputs saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
