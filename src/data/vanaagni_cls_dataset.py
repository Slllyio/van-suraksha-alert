"""
src/data/vanaagni_cls_dataset.py
================================
Patch-level classification dataset for VanAgni fire detection.

Instead of pixel-level segmentation (which fails with ViT's 16×16 spatial
resolution), this dataset returns a single binary label per patch:
    1 = patch contains fire    (is_fire == 1 in manifest)
    0 = no fire in patch

Each sample returns the same inputs as VanAgniDataset (hls, weather, terrain,
etc.) but the label is a scalar, not a spatial map.

Usage:
    from src.data.vanaagni_cls_dataset import get_cls_dataloaders
    train_dl, val_dl, test_dl = get_cls_dataloaders("data_lake/training_patches_v5/manifest.csv")
"""

import numpy as np
import pandas as pd
import torch
from torch import Tensor
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent.parent

# Tier-based quality weighting
TIER_SAMPLE_WEIGHTS = {
    "GOLD":       3.0,
    "SILVER":     2.0,
    "BRONZE":     1.5,
    "VIIRS_ONLY": 1.0,
    "NEGATIVE":   1.0,
}


class VanAgniClsDataset(Dataset):
    """
    Patch-level fire classification dataset.

    Returns dict with:
      hls         float32 (6, T, H, W)
      indices     float32 (3, T, H, W)
      weather     float32 (10,)
      weather_7d  float32 (10, 7)
      terrain     float32 (4, H, W)
      burn_age    float32 (3, H, W)
      landcover   float32 (11, H, W)
      label       long    scalar 0 or 1
      fire_frac   float32 scalar (fraction of fire pixels — for analysis)
      patch_id    str
      tier        str
    """

    def __init__(
        self,
        manifest_path: str | Path,
        split: str = "train",
        augment: bool = True,
        min_fire_pixels: int = 0,
        exclude_tiers: Optional[List[str]] = None,
        spectral_only: bool = False,
    ) -> None:
        self.split = split
        self.augment = augment and (split == "train")
        self.root = _ROOT

        df = pd.read_csv(manifest_path)
        df = df[df["split"] == split].copy()

        if exclude_tiers:
            df = df[~df["tier"].isin(exclude_tiers)]

        if min_fire_pixels > 0:
            mask = (df["fire_pixels"] >= min_fire_pixels) | (df["is_fire"] == 0)
            df = df[mask]

        if spectral_only and "has_spectral" in df.columns:
            df = df[(df["has_spectral"] == 1) | (df["is_fire"] == 0)]

        self.df = df.reset_index(drop=True)

        n_fire = int(self.df["is_fire"].sum())
        n_neg = len(self.df) - n_fire
        print(
            f"VanAgniClsDataset [{split:5s}]: {len(self.df):4d} patches  "
            f"({n_fire} fire / {n_neg} negative)  augment={self.augment}"
        )

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> Dict[str, Tensor | str]:
        row = self.df.iloc[idx]
        path = self.root / row["path"]
        data = np.load(str(path), allow_pickle=True)

        weather    = data["weather"].astype(np.float32)
        weather_7d = data["weather_7d"].astype(np.float32)
        terrain    = data["terrain"].astype(np.float32)
        burn_age   = data["burn_age"].astype(np.float32)
        landcover  = data["landcover"].astype(np.float32)
        hls        = data["hls"].astype(np.float32)
        indices    = data["indices"].astype(np.float32)

        # Patch-level label from manifest (no pixel-level processing needed)
        label = int(row["is_fire"])

        # Fire fraction for analysis (how much of patch is fire)
        fire_pixels = int(row.get("fire_pixels", 0))
        total_pixels = hls.shape[-2] * hls.shape[-1]  # H * W
        fire_frac = fire_pixels / total_pixels if total_pixels > 0 else 0.0

        # D4 augmentation (train only)
        if self.augment:
            k = int(np.random.randint(0, 4))
            do_flip = bool(np.random.random() < 0.5)

            hls       = _rot_flip_4d(hls, k, do_flip)
            indices   = _rot_flip_4d(indices, k, do_flip)
            terrain   = _rot_flip_3d(terrain, k, do_flip)
            burn_age  = _rot_flip_3d(burn_age, k, do_flip)
            landcover = _rot_flip_3d(landcover, k, do_flip)
            hls = _spectral_augment(hls)

        return {
            "hls":        torch.from_numpy(hls),
            "indices":    torch.from_numpy(indices),
            "weather":    torch.from_numpy(weather),
            "weather_7d": torch.from_numpy(weather_7d),
            "terrain":    torch.from_numpy(terrain),
            "burn_age":   torch.from_numpy(burn_age),
            "landcover":  torch.from_numpy(landcover),
            "label":      torch.tensor(label, dtype=torch.long),
            "fire_frac":  torch.tensor(fire_frac, dtype=torch.float32),
            "patch_id":   str(row["patch_id"]),
            "tier":       str(row["tier"]),
        }

    def make_sampler(self) -> WeightedRandomSampler:
        """Tier-weighted sampler (no fire oversampling needed — classes are balanced)."""
        sample_w = np.ones(len(self.df), dtype=np.float64)
        for i, row in self.df.iterrows():
            tier = str(row.get("tier", "NEGATIVE"))
            sample_w[i] = TIER_SAMPLE_WEIGHTS.get(tier, 1.0)

        return WeightedRandomSampler(
            weights=torch.DoubleTensor(sample_w),
            num_samples=len(sample_w),
            replacement=True,
        )


# ═════════════════════════════════════════════════════════════════════════════
# Augmentation helpers (same as vanaagni_dataset.py)
# ═════════════════════════════════════════════════════════════════════════════

def _rot_flip_4d(arr, k, flip):
    arr = np.rot90(arr, k=k, axes=(-2, -1))
    if flip:
        arr = np.flip(arr, axis=-1)
    return np.ascontiguousarray(arr)

def _rot_flip_3d(arr, k, flip):
    arr = np.rot90(arr, k=k, axes=(-2, -1))
    if flip:
        arr = np.flip(arr, axis=-1)
    return np.ascontiguousarray(arr)

def _spectral_augment(hls):
    noise = np.random.normal(0, 0.01, hls.shape).astype(np.float32)
    hls = hls + noise
    for b in range(hls.shape[0]):
        shift = np.random.uniform(-0.03, 0.03)
        hls[b] += shift
    if np.random.random() < 0.1:
        band_idx = np.random.randint(0, hls.shape[0])
        hls[band_idx] = 0.0
    return hls


# ═════════════════════════════════════════════════════════════════════════════
# Collate (handles string fields)
# ═════════════════════════════════════════════════════════════════════════════

def cls_collate(batch):
    keys = batch[0].keys()
    out = {}
    for k in keys:
        vals = [s[k] for s in batch]
        if isinstance(vals[0], Tensor):
            out[k] = torch.stack(vals, dim=0)
        else:
            out[k] = vals
    return out


# ═════════════════════════════════════════════════════════════════════════════
# DataLoader Factory
# ═════════════════════════════════════════════════════════════════════════════

def get_cls_dataloaders(
    manifest_path: str | Path,
    batch_size: int = 8,
    num_workers: int = 4,
    exclude_tiers: Optional[List[str]] = None,
    min_fire_pixels: int = 25,
    pin_memory: bool = True,
    spectral_only: bool = False,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """Build train / val / test DataLoaders for patch classification."""

    common = dict(
        exclude_tiers=exclude_tiers,
        spectral_only=spectral_only,
    )

    train_ds = VanAgniClsDataset(
        manifest_path, split="train", augment=True,
        min_fire_pixels=min_fire_pixels, **common,
    )
    val_ds = VanAgniClsDataset(
        manifest_path, split="val", augment=False,
        min_fire_pixels=0, **common,
    )
    test_ds = VanAgniClsDataset(
        manifest_path, split="test", augment=False,
        min_fire_pixels=0, **common,
    )

    train_sampler = train_ds.make_sampler()

    dl_kwargs = dict(
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=pin_memory,
        collate_fn=cls_collate,
        persistent_workers=(num_workers > 0),
    )
    if num_workers > 0:
        dl_kwargs["prefetch_factor"] = 2

    train_dl = DataLoader(train_ds, sampler=train_sampler, **dl_kwargs)
    val_dl   = DataLoader(val_ds, shuffle=False, **dl_kwargs)
    test_dl  = DataLoader(test_ds, shuffle=False, **dl_kwargs)

    return train_dl, val_dl, test_dl
