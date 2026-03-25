"""
src/data/vanaagni_dataset.py
============================
PyTorch Dataset + DataLoader factory for VanAgni fire-prediction training.

Supports two modes:
  - **Classification** (num_classes >= 2): label is long (H,W), 0-4 severity
  - **Regression**     (num_classes == 1): label is float32 (H,W), continuous dNBR

Each sample is a dict of tensors:
  hls         float32  (6, T, H, W)   Normalised HLS S30 bands x T temporal frames
  indices     float32  (3, T, H, W)   NDVI, NBR, BSI per frame
  weather     float32  (10,)          Current-day FWI weather (normalised)
  weather_7d  float32  (10, 7)        7-day look-back weather window
  terrain     float32  (4, H, W)      elev_norm, slope_norm, sin_asp, cos_asp
  burn_age    float32  (3, H, W)      recent / high-risk / mature fuel-recovery
  landcover   float32  (11, H, W)     ESA WorldCover one-hot (11 classes)
  label       float32/long (H, W)     Regression: continuous dNBR (NaN=ignore)
                                       Classification: 0-4 severity (-1=ignore)
  weight      float32  (H, W)         Per-pixel loss weight (tier-based)
  patch_id    str                      Unique identifier for this patch
  tier        str                      GOLD / SILVER / BRONZE / VIIRS_ONLY / NEGATIVE

Usage:
    from src.data.vanaagni_dataset import get_dataloaders

    train_dl, val_dl, test_dl = get_dataloaders(
        manifest_path="data_lake/training_patches/manifest.csv",
        batch_size=4,
    )

    for batch in train_dl:
        hls    = batch["hls"]          # (B, 6, 3, 224, 224)
        label  = batch["label"]        # (B, 224, 224)
        weight = batch["weight"]       # (B, 224, 224)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from torch import Tensor
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler


# ── Repository root (two levels up from this file) ────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Tier → training weight multiplier for weighted sampling ───────────────────
TIER_SAMPLE_WEIGHTS = {
    "GOLD":       3.0,
    "SILVER":     2.0,
    "BRONZE":     1.5,
    "VIIRS_ONLY": 1.0,
    "NEGATIVE":   1.0,
}

# Fire-vs-negative imbalance upsampling factor
FIRE_OVERSAMPLE = 5.0


class VanAgniDataset(Dataset):
    """
    Loads pre-built .npz patch files produced by build_training_dataset.py.

    Parameters
    ----------
    manifest_path : path to manifest.csv (output of build_training_dataset.py)
    split         : "train" | "val" | "test"
    augment       : apply D4 random augmentation (enabled only for train split)
    min_fire_pixels : skip fire patches with fewer than this many fire pixels
    exclude_tiers : list of tier strings to exclude (e.g. ["VIIRS_ONLY"])
    include_negatives : whether to include NEGATIVE patches
    """

    # Guna-specific RBR severity thresholds (derived from spectral data analysis)
    # See scripts/analyze_real_rbr.py for rationale
    GUNA_THRESHOLDS = {
        # num_classes → list of RBR boundaries between classes
        2: [],                         # binary: fire (RBR>0) / no-fire
        4: [0.01, 0.12, 0.30],        # Guna 4-class: unburned / ground_litter / active_surface / severe
        5: [0.05, 0.15, 0.30, 0.50],  # Parks et al. 2014 (legacy, not recommended for Guna)
    }

    GUNA_CLASS_NAMES = {
        2: ["no_fire", "fire"],
        4: ["unburned", "ground_litter", "active_surface", "severe"],
        5: ["no_burn", "very_low", "low", "moderate", "high"],
    }

    def __init__(
        self,
        manifest_path: str | Path,
        split: str = "train",
        augment: bool = True,
        min_fire_pixels: int = 0,
        exclude_tiers: Optional[List[str]] = None,
        include_negatives: bool = True,
        binary_mode: bool = False,
        regression: bool = False,
        cache_dir: Optional[str | Path] = None,
        spectral_only: bool = False,
        num_classes: int = 5,
        dilate_fire: bool = False,
        dilation_radius: int = 8,
        boundary_ignore_radius: int = 0,
    ) -> None:
        self.split   = split
        self.augment = augment and (split == "train")
        self.binary_mode = binary_mode
        self.regression  = regression
        self.num_classes = num_classes
        self.dilate_fire = dilate_fire
        self.dilation_radius = dilation_radius
        self.boundary_ignore_radius = boundary_ignore_radius
        self.root    = _ROOT
        self.cache_dir = Path(cache_dir) if cache_dir else None

        df = pd.read_csv(manifest_path)
        df = df[df["split"] == split].copy()

        if exclude_tiers:
            df = df[~df["tier"].isin(exclude_tiers)]

        if not include_negatives:
            df = df[df["is_fire"] == 1]

        if min_fire_pixels > 0:
            mask = (df["fire_pixels"] >= min_fire_pixels) | (df["is_fire"] == 0)
            df = df[mask]

        # Filter to spectral-only patches (real RBR labels, not 0.10 fallback)
        if spectral_only and "has_spectral" in df.columns:
            # Keep patches with real spectral labels + all negative patches
            df = df[(df["has_spectral"] == 1) | (df["is_fire"] == 0)]

        self.df = df.reset_index(drop=True)

        # Index fire patches for copy-paste augmentation (train only)
        self._fire_indices = list(
            self.df.index[self.df["is_fire"] == 1]
        ) if self.augment else []

        n_fire = int(self.df["is_fire"].sum())
        n_neg  = len(self.df) - n_fire
        spectral_tag = " [spectral-only]" if spectral_only else ""
        print(
            f"VanAgniDataset [{split:5s}]: {len(self.df):5d} patches  "
            f"({n_fire} fire / {n_neg} negative)  "
            f"augment={self.augment}  num_classes={num_classes}{spectral_tag}"
        )

    # ── Dataset protocol ──────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> Dict[str, Tensor | str]:
        row  = self.df.iloc[idx]
        path = self.root / row["path"]

        # np.load with allow_pickle for .npz metadata field
        data = np.load(str(path), allow_pickle=True)

        weather    = data["weather"].astype(np.float32)    # (10,)
        weather_7d = data["weather_7d"].astype(np.float32) # (10, 7)
        terrain    = data["terrain"].astype(np.float32)    # (4, H, W)
        burn_age   = data["burn_age"].astype(np.float32)   # (3, H, W)
        landcover  = data["landcover"].astype(np.float32)  # (11, H, W)
        weight     = data["weight"].astype(np.float32)     # (H, W)

        # Load cached backbone features if available
        patch_id = str(row["patch_id"])
        cached_feat = None
        if self.cache_dir is not None:
            cache_path = self.cache_dir / f"{patch_id}.npy"
            if cache_path.exists():
                cached_feat = np.load(str(cache_path))  # (197, 1280)

        if cached_feat is None:
            hls     = data["hls"].astype(np.float32)      # (6, T, H, W)
            indices = data["indices"].astype(np.float32)   # (3, T, H, W)
        else:
            # Cached mode: dummy HLS (not used in cached forward)
            hls     = np.zeros((6, 3, 1, 1), dtype=np.float32)
            indices = np.zeros((3, 3, 1, 1), dtype=np.float32)

        if self.regression:
            label = data["label"].astype(np.float32)
        elif self.binary_mode or self.num_classes == 2:
            # Binary fire/no-fire: any RBR > 0 = fire
            raw = data["label"].astype(np.float32)
            label = np.zeros(raw.shape, dtype=np.int64)
            label[raw > 0.0] = 1       # fire
            label[np.isnan(raw)] = -1   # ignore

            # -- Handling sparse fire labels at ViT backbone resolution -----------
            # Fire is only 0.8% of pixels — ViT 14×14 cells span 16×16px each.
            # Two strategies (boundary_ignore preferred over dilation):
            #
            # A) boundary_ignore_radius > 0:  Create an ignore zone around fire.
            #    Fire pixels stay as class 1, distant bg stays class 0, and the
            #    boundary ring becomes -1 (ignored).  The model learns precise
            #    fire locations but isn't penalized for ViT-scale imprecision.
            #    Same labels for train/val/test — no distribution mismatch.
            #
            # B) dilate_fire (legacy):  Expand fire labels to match ViT scale.
            #    Creates train/test distribution mismatch — not recommended.
            if self.boundary_ignore_radius > 0:
                from scipy.ndimage import binary_dilation as _bd
                fire_mask = (label == 1)
                if fire_mask.any():
                    k = 2 * self.boundary_ignore_radius + 1
                    _struct = np.ones((k, k), dtype=bool)
                    dilated = _bd(fire_mask, structure=_struct)
                    # Boundary zone: dilated ring around fire → ignore
                    boundary = dilated & (label == 0)
                    label[boundary] = -1
            elif self.dilate_fire:
                from scipy.ndimage import binary_dilation as _bd
                fire_mask = (label == 1)
                if fire_mask.any():
                    k = 2 * self.dilation_radius + 1
                    _struct = np.ones((k, k), dtype=bool)
                    dilated = _bd(fire_mask, structure=_struct)
                    label[(dilated) & (label == 0)] = 1
        else:
            # Multi-class severity: use threshold table for num_classes
            raw = data["label"].astype(np.float32)
            thresholds = self.GUNA_THRESHOLDS.get(
                self.num_classes,
                self.GUNA_THRESHOLDS[5]  # fallback to Parks
            )
            label = np.zeros(raw.shape, dtype=np.int64)  # default: class 0
            for cls_idx, thresh in enumerate(thresholds, start=1):
                label[raw >= thresh] = cls_idx
            label[np.isnan(raw)] = -1  # ignore (nodata)

        # ── Augmentation pipeline (train only) ────────────────────────────
        if self.augment:
            # 1. Copy-paste fire regions (50% prob, only if fire patches exist)
            if (self._fire_indices
                    and cached_feat is None
                    and np.random.random() < 0.5):
                hls, indices, label, weight = self._copy_paste_fire(
                    hls, indices, label, weight
                )

            # 2. Random scale crop (30% prob) — adds scale diversity
            if cached_feat is None and np.random.random() < 0.3:
                hls, indices, terrain, burn_age, landcover, label, weight = (
                    _random_scale_crop(
                        hls, indices, terrain, burn_age, landcover, label, weight
                    )
                )

            # 3. D4 geometric augmentation (always)
            k       = int(np.random.randint(0, 4))    # rotation steps
            do_flip = bool(np.random.random() < 0.5)  # horizontal flip

            terrain   = _rot_flip_3d(terrain,   k, do_flip)
            burn_age  = _rot_flip_3d(burn_age,  k, do_flip)
            landcover = _rot_flip_3d(landcover, k, do_flip)
            label     = _rot_flip_2d(label,     k, do_flip)
            weight    = _rot_flip_2d(weight,    k, do_flip)

            if cached_feat is not None:
                # Augment cached features: CLS token stays, spatial tokens rotated
                cached_feat = _rot_flip_tokens(cached_feat, k, do_flip)
            else:
                hls     = _rot_flip_4d(hls,     k, do_flip)
                indices = _rot_flip_4d(indices, k, do_flip)
                hls = _spectral_augment(hls)

        sample = {
            "hls":        torch.from_numpy(hls),
            "indices":    torch.from_numpy(indices),
            "weather":    torch.from_numpy(weather),
            "weather_7d": torch.from_numpy(weather_7d),
            "terrain":    torch.from_numpy(terrain),
            "burn_age":   torch.from_numpy(burn_age),
            "landcover":  torch.from_numpy(landcover),
            "label":      torch.from_numpy(label),
            "weight":     torch.from_numpy(weight),
            "patch_id":   patch_id,
            "tier":       str(row["tier"]),
        }

        if cached_feat is not None:
            sample["cached_feat"] = torch.from_numpy(cached_feat)

        return sample

    # ── Copy-paste fire augmentation ────────────────────────────────────────

    def _copy_paste_fire(
        self,
        hls: np.ndarray,
        indices: np.ndarray,
        label: np.ndarray,
        weight: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract fire regions from a random fire patch and paste onto this sample.

        Picks a random fire sample, finds connected fire components via
        scipy.ndimage.label, selects the largest one, and composites it
        onto the current sample (overwriting HLS, indices, label, weight
        at fire pixel locations).
        """
        from scipy.ndimage import label as nd_label

        # Pick a random fire sample
        donor_idx = self._fire_indices[
            np.random.randint(len(self._fire_indices))
        ]
        donor_row = self.df.iloc[donor_idx]
        # Load our own .npz training patches (trusted local data)
        donor_data = np.load(
            str(self.root / donor_row["path"]), allow_pickle=True
        )

        # Build donor binary label
        donor_raw = donor_data["label"].astype(np.float32)
        donor_fire_mask = (donor_raw > 0.0) & (~np.isnan(donor_raw))

        if not donor_fire_mask.any():
            return hls, indices, label, weight

        # Find largest connected fire component
        labeled_arr, n_components = nd_label(donor_fire_mask)
        if n_components == 0:
            return hls, indices, label, weight

        # Pick the largest component
        component_sizes = np.bincount(labeled_arr.ravel())[1:]  # skip background
        largest_id = np.argmax(component_sizes) + 1
        paste_mask = (labeled_arr == largest_id)

        # Apply D4 transform to donor fire region for diversity
        dk = int(np.random.randint(0, 4))
        dflip = bool(np.random.random() < 0.5)
        paste_mask = _rot_flip_2d(
            paste_mask.astype(np.int64), dk, dflip
        ).astype(bool)

        donor_hls = _rot_flip_4d(
            donor_data["hls"].astype(np.float32), dk, dflip
        )
        donor_indices = _rot_flip_4d(
            donor_data["indices"].astype(np.float32), dk, dflip
        )

        # Paste: overwrite target at fire locations
        hls[:, :, paste_mask] = donor_hls[:, :, paste_mask]
        indices[:, :, paste_mask] = donor_indices[:, :, paste_mask]
        label[paste_mask] = 1  # fire
        weight[paste_mask] = 1.0

        return hls, indices, label, weight

    # ── Weighted sampler ──────────────────────────────────────────────────────

    def make_sampler(self, fire_oversample: float = FIRE_OVERSAMPLE) -> WeightedRandomSampler:
        """
        Returns a WeightedRandomSampler that:
          1. Upsamples fire patches by fire_oversample × over negative patches
          2. Further weights fire patches by their tier (GOLD > SILVER > BRONZE …)
        """
        sample_w = np.ones(len(self.df), dtype=np.float64)

        for i, row in self.df.iterrows():
            tier      = str(row.get("tier", "NEGATIVE"))
            is_fire   = int(row.get("is_fire", 0))
            tier_mult = TIER_SAMPLE_WEIGHTS.get(tier, 1.0)
            fire_mult = fire_oversample if is_fire else 1.0
            sample_w[i] = tier_mult * fire_mult

        return WeightedRandomSampler(
            weights     = torch.DoubleTensor(sample_w),
            num_samples = len(sample_w),
            replacement = True,
        )

    # ── Convenience: per-split class counts ───────────────────────────────────

    def class_counts(self) -> Dict[str, int]:
        """Return {tier: count} for all patches in this split."""
        return self.df["tier"].value_counts().to_dict()


# ═════════════════════════════════════════════════════════════════════════════
# D4 Augmentation Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _rot_flip_4d(arr: np.ndarray, k: int, flip: bool) -> np.ndarray:
    """Rotate + flip a (C, T, H, W) array in the H×W plane."""
    arr = np.rot90(arr, k=k, axes=(-2, -1))
    if flip:
        arr = np.flip(arr, axis=-1)
    return np.ascontiguousarray(arr)


def _rot_flip_3d(arr: np.ndarray, k: int, flip: bool) -> np.ndarray:
    """Rotate + flip a (C, H, W) array in the H×W plane."""
    arr = np.rot90(arr, k=k, axes=(-2, -1))
    if flip:
        arr = np.flip(arr, axis=-1)
    return np.ascontiguousarray(arr)


def _rot_flip_2d(arr: np.ndarray, k: int, flip: bool) -> np.ndarray:
    """Rotate + flip a (H, W) array."""
    arr = np.rot90(arr, k=k, axes=(-2, -1))
    if flip:
        arr = np.flip(arr, axis=-1)
    return np.ascontiguousarray(arr)


def _rot_flip_tokens(feat: np.ndarray, k: int, flip: bool,
                     num_frames: int = 3) -> np.ndarray:
    """Rotate + flip cached ViT tokens in spatial plane.

    feat: (N_tokens, embed_dim) — e.g. (769, 1280) for 600M with T=3.
          Token 0 = CLS (position-invariant).
          Tokens 1.. = T * H * W spatial tokens (e.g. 3 * 16 * 16 = 768).

    We reshape spatial tokens to (T, H, W, D), apply D4 transform per frame
    in the (H, W) plane, then flatten back. CLS token passes through unchanged.
    """
    cls_token = feat[:1]         # (1, D)
    spatial   = feat[1:]         # (T*H*W, D)
    D = spatial.shape[-1]
    n_spatial = spatial.shape[0]

    # Derive per-frame grid: n_spatial = T * H * W, H == W
    per_frame = n_spatial // num_frames
    grid_h = int(np.sqrt(per_frame))
    assert grid_h * grid_h == per_frame, (
        f"Spatial tokens {n_spatial} / {num_frames} frames = {per_frame}, "
        f"not a perfect square (sqrt={np.sqrt(per_frame):.2f})"
    )

    grid = spatial.reshape(num_frames, grid_h, grid_h, D)  # (T, H, W, D)

    # rot90 in the (H, W) plane per frame, same k as label
    grid = np.rot90(grid, k=k, axes=(1, 2))
    if flip:
        grid = np.flip(grid, axis=2)  # flip along W

    spatial = np.ascontiguousarray(grid.reshape(-1, D))  # (T*H*W, D)
    return np.concatenate([cls_token, spatial], axis=0)   # (1+T*H*W, D)


def _random_scale_crop(
    hls: np.ndarray,        # (6, T, H, W)
    indices: np.ndarray,    # (3, T, H, W)
    terrain: np.ndarray,    # (4, H, W)
    burn_age: np.ndarray,   # (3, H, W)
    landcover: np.ndarray,  # (11, H, W)
    label: np.ndarray,      # (H, W)
    weight: np.ndarray,     # (H, W)
    scale_range: Tuple[float, float] = (0.75, 1.0),
) -> Tuple[np.ndarray, ...]:
    """Random crop at a smaller scale, then resize back to original size.

    Adds scale diversity: the model sees the same fire at different
    apparent sizes. Uses nearest-neighbor for label/weight to avoid
    interpolation artifacts on discrete classes.
    """
    from scipy.ndimage import zoom as nd_zoom

    H, W = label.shape
    scale = np.random.uniform(*scale_range)
    crop_h, crop_w = int(H * scale), int(W * scale)

    # Random crop origin
    y0 = np.random.randint(0, H - crop_h + 1)
    x0 = np.random.randint(0, W - crop_w + 1)

    # Zoom factors to resize crop back to (H, W)
    zy, zx = H / crop_h, W / crop_w

    def _crop_zoom_4d(arr: np.ndarray) -> np.ndarray:
        cropped = arr[:, :, y0:y0+crop_h, x0:x0+crop_w]
        return nd_zoom(cropped, (1, 1, zy, zx), order=1)

    def _crop_zoom_3d(arr: np.ndarray) -> np.ndarray:
        cropped = arr[:, y0:y0+crop_h, x0:x0+crop_w]
        return nd_zoom(cropped, (1, zy, zx), order=1)

    def _crop_zoom_2d_nearest(arr: np.ndarray) -> np.ndarray:
        cropped = arr[y0:y0+crop_h, x0:x0+crop_w]
        return nd_zoom(cropped, (zy, zx), order=0)  # nearest for labels

    return (
        _crop_zoom_4d(hls),
        _crop_zoom_4d(indices),
        _crop_zoom_3d(terrain),
        _crop_zoom_3d(burn_age),
        _crop_zoom_3d(landcover),
        _crop_zoom_2d_nearest(label),
        _crop_zoom_2d_nearest(weight),
    )


def _spectral_augment(hls: np.ndarray) -> np.ndarray:
    """Apply spectral augmentations to HLS bands (6, T, H, W).

    Three augmentations applied sequentially:
      1. Gaussian noise (sigma=0.01, ~1% of reflectance)
      2. Per-band brightness shift (uniform +/-3%)
      3. Band dropout: zero one band with 10% probability
    """
    # 1. Gaussian noise
    noise = np.random.normal(0, 0.01, hls.shape).astype(np.float32)
    hls = hls + noise

    # 2. Per-band brightness shift
    for b in range(hls.shape[0]):
        shift = np.random.uniform(-0.03, 0.03)
        hls[b] += shift

    # 3. Band dropout (zero one band entirely)
    if np.random.random() < 0.1:
        band_idx = np.random.randint(0, hls.shape[0])
        hls[band_idx] = 0.0

    return hls


# ═════════════════════════════════════════════════════════════════════════════
# Custom Collate (handles string fields)
# ═════════════════════════════════════════════════════════════════════════════

def vanaagni_collate(batch: List[dict]) -> dict:
    """
    Collate list of sample dicts into a batched dict.
    Tensor fields are stacked; string fields (patch_id, tier) remain as lists.
    """
    keys = batch[0].keys()
    out  = {}
    for k in keys:
        vals = [s[k] for s in batch]
        if isinstance(vals[0], Tensor):
            out[k] = torch.stack(vals, dim=0)
        else:
            out[k] = vals  # list of strings
    return out


# ═════════════════════════════════════════════════════════════════════════════
# DataLoader Factory
# ═════════════════════════════════════════════════════════════════════════════

def get_dataloaders(
    manifest_path: str | Path,
    batch_size: int = 4,
    num_workers: int = 4,
    fire_oversample: float = FIRE_OVERSAMPLE,
    exclude_tiers: Optional[List[str]] = None,
    min_fire_pixels: int = 25,
    pin_memory: bool = True,
    prefetch_factor: int = 2,
    binary_mode: bool = False,
    regression: bool = False,
    cache_dir: Optional[str | Path] = None,
    spectral_only: bool = False,
    num_classes: int = 5,
    dilate_fire: bool = False,
    dilation_radius: int = 8,
    boundary_ignore_radius: int = 0,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Build train / val / test DataLoaders.

    Parameters
    ----------
    manifest_path   : path to manifest.csv from build_training_dataset.py
    batch_size      : samples per GPU batch
    num_workers     : parallel DataLoader workers
    fire_oversample : ratio for upsampling fire patches in training
    exclude_tiers   : optional list of tiers to exclude
    min_fire_pixels : minimum fire pixels required for positive patches
    pin_memory      : pin CPU tensors to CUDA-pinned memory
    prefetch_factor : DataLoader prefetch depth per worker
    regression      : if True, labels are float32 dNBR (continuous regression)
    spectral_only   : if True, filter to patches with real spectral RBR labels
    num_classes     : number of severity classes (2=binary, 4=Guna, 5=Parks)
    dilate_fire     : if True, dilate binary fire labels (train+val only, NOT test)
    dilation_radius : radius in pixels for fire label dilation
    boundary_ignore_radius : if >0, create ignore zone around fire (all splits)

    Returns
    -------
    (train_dl, val_dl, test_dl)
    """
    _ds_kwargs = dict(
        exclude_tiers  = exclude_tiers,
        binary_mode    = binary_mode,
        regression     = regression,
        cache_dir      = cache_dir,
        spectral_only  = spectral_only,
        num_classes    = num_classes,
        boundary_ignore_radius = boundary_ignore_radius,
    )

    train_ds = VanAgniDataset(
        manifest_path,
        split          = "train",
        augment        = True,
        min_fire_pixels= min_fire_pixels,
        dilate_fire    = dilate_fire,
        dilation_radius= dilation_radius,
        **_ds_kwargs,
    )
    val_ds = VanAgniDataset(
        manifest_path,
        split          = "val",
        augment        = False,
        min_fire_pixels= 0,
        dilate_fire    = dilate_fire,
        dilation_radius= dilation_radius,
        **_ds_kwargs,
    )
    test_ds = VanAgniDataset(
        manifest_path,
        split          = "test",
        augment        = False,
        min_fire_pixels= 0,
        dilate_fire    = False,
        dilation_radius= 0,
        **_ds_kwargs,
    )

    # Weighted sampler for training (fire-aware upsampling)
    train_sampler = train_ds.make_sampler(fire_oversample=fire_oversample)

    _dl_kwargs = dict(
        batch_size     = batch_size,
        num_workers    = num_workers,
        pin_memory     = pin_memory,
        collate_fn     = vanaagni_collate,
        persistent_workers = (num_workers > 0),
    )
    if num_workers > 0:
        _dl_kwargs["prefetch_factor"] = prefetch_factor

    train_dl = DataLoader(train_ds, sampler=train_sampler, **_dl_kwargs)
    val_dl   = DataLoader(val_ds,   shuffle=False,         **_dl_kwargs)
    test_dl  = DataLoader(test_ds,  shuffle=False,         **_dl_kwargs)

    return train_dl, val_dl, test_dl


# ═════════════════════════════════════════════════════════════════════════════
# Batch Inspector (debugging / logging)
# ═════════════════════════════════════════════════════════════════════════════

def inspect_batch(batch: dict, verbose: bool = True) -> None:
    """Print shapes, dtypes and value ranges for a batch dict."""
    print("-" * 55)
    for k, v in batch.items():
        if isinstance(v, Tensor):
            lo = float(v[v != -1].min()) if (v != -1).any() else float("nan")
            hi = float(v[v != -1].max()) if (v != -1).any() else float("nan")
            print(f"  {k:12s}  shape={str(tuple(v.shape)):25s}  "
                  f"dtype={str(v.dtype):15s}  range=[{lo:.3f}, {hi:.3f}]")
        elif isinstance(v, list):
            print(f"  {k:12s}  list[{len(v)}]  e.g. '{v[0]}'")
    print("-" * 55)


# ═════════════════════════════════════════════════════════════════════════════
# Quick Smoke-Test
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    manifest = _ROOT / "data_lake" / "training_patches" / "manifest.csv"
    if not manifest.exists():
        print(f"Manifest not found: {manifest}")
        print("Run  python scripts/build_training_dataset.py  first.")
        sys.exit(1)

    train_dl, val_dl, test_dl = get_dataloaders(
        manifest_path  = manifest,
        batch_size     = 2,
        num_workers    = 0,   # 0 for quick test
        pin_memory     = False,
    )

    print(f"\nTrain batches : {len(train_dl)}")
    print(f"Val   batches : {len(val_dl)}")
    print(f"Test  batches : {len(test_dl)}")

    print("\nSampling one training batch …")
    batch = next(iter(train_dl))
    inspect_batch(batch)

    print("\nLabel class distribution in batch:")
    lbl = batch["label"]
    fire_px = int((lbl == 1).sum())
    bg_px   = int((lbl == 0).sum())
    ign_px  = int((lbl == -1).sum())
    total   = fire_px + bg_px + ign_px
    print(f"  fire={fire_px} ({fire_px/total*100:.1f}%)  "
          f"bg={bg_px} ({bg_px/total*100:.1f}%)  "
          f"ignore={ign_px}")
    print(f"  Tier : {batch['tier']}")
    print("\nDataset smoke-test PASSED")
