"""
Dataset Classes
===============
PyTorch Dataset wrappers for change detection and temporal prediction tasks.
STRICTLY LOCAL VERSION: No web/earthaccess dependencies.
"""

import os
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from typing import Optional, Callable, Tuple
import logging
import rasterio
from pathlib import Path
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

class SatelliteAugment:
    def __init__(self, noise_std=0.02, bright_delta=0.05, band_drop_p=0.15, flip_p=0.5, rot_p=0.5):
        self.noise_std, self.bright_delta, self.band_drop_p = noise_std, bright_delta, band_drop_p
        self.flip_p, self.rot_p = flip_p, rot_p
    def __call__(self, image, label):
        if np.random.rand() < self.flip_p:
            image, label = np.flip(image, axis=-1).copy(), np.flip(label, axis=-1).copy()
        if np.random.rand() < self.flip_p:
            image, label = np.flip(image, axis=-2).copy(), np.flip(label, axis=-2).copy()
        if np.random.rand() < self.rot_p:
            k = np.random.choice([1, 2, 3])
            image, label = np.rot90(image, k=k, axes=(-2, -1)).copy(), np.rot90(label, k=k, axes=(-2, -1)).copy()
        if self.noise_std > 0:
            image = image + np.random.randn(*image.shape).astype(np.float32) * np.random.uniform(0, self.noise_std)
        image = image + np.random.uniform(-self.bright_delta, self.bright_delta, size=(1, image.shape[1], 1, 1)).astype(np.float32)
        if np.random.rand() < self.band_drop_p:
            image[:, np.random.randint(0, image.shape[1]), :, :] = 0.0
        return image, label

class AiRefinedPrecisionDataset(Dataset):
    """
    STRICTLY LOCAL Precision Dataset.
    Requires data/training/cache to be populated.
    """
    def __init__(self, labels_dir: str, augment: bool = True):
        self.labels_dir = Path(labels_dir)
        self.label_files = list(self.labels_dir.glob("label_*.tif"))
        self.augmenter = SatelliteAugment() if augment else None
        log.info(f"[AiRefinedDataset] Initialized OFFLINE with {len(self.label_files)} labels.")

    def __len__(self):
        return len(self.label_files)

    def _parse_filename(self, fname: str):
        parts = fname.replace("label_", "").replace("_AI.tif", "").split("_")
        date_str = parts[0]
        lat = float(parts[1].replace("lat", ""))
        lon = float(parts[2].replace("lon", ""))
        return date_str, lat, lon

    def __getitem__(self, idx):
        label_path = self.label_files[idx]
        date_str, lat, lon = self._parse_filename(label_path.name)
        
        sample_tag = f"lat{lat:.2f}_lon{lon:.2f}_{date_str}"
        cache_file = Path("data/training/cache") / f"{sample_tag}.npz"
        
        if cache_file.exists():
            with np.load(cache_file) as data:
                image = data["hls"].astype(np.float32)
        else:
            raise FileNotFoundError(f"CRITICAL: Cache miss for {sample_tag}. Run pre_cache agent first.")

        # Aux placeholders
        weather    = torch.zeros(10)
        weather_7d = torch.zeros(10, 7)
        terrain    = torch.zeros(4, 224, 224)
        burn_age   = torch.zeros(3, 224, 224)
        landcover  = torch.zeros(11, 224, 224)
        
        with rasterio.open(label_path) as src:
            label = src.read(1, boundless=True, fill_value=0)[:224, :224].astype(np.int64)

        if self.augmenter:
            image, label = self.augmenter(image, label)

        return {
            "hls": torch.from_numpy(image),
            "weather": weather,
            "weather_7d": weather_7d,
            "terrain": terrain,
            "burn_age": burn_age,
            "landcover": landcover,
            "label": torch.from_numpy(label)
        }

class ForestChangeDataset(Dataset):
    def __init__(self, manifest_csv: str, transform: Optional[Callable] = None, augment: bool = False, use_last_two_frames_only: bool = False, aug_cfg: Optional[dict] = None):
        self.df = pd.read_csv(manifest_csv); self.transform = transform; self.use_last_two = use_last_two_frames_only
        self.augmenter = SatelliteAugment() if augment else None
    def __len__(self): return len(self.df)
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        r = self.df.iloc[idx]; img = np.load(r["img_path"]); lbl = np.load(r["lbl_path"])
        if self.use_last_two and img.shape[0] > 2: img = img[-2:]
        if self.augmenter: img, lbl = self.augmenter(img, lbl)
        img, lbl = torch.from_numpy(img.copy()).float(), torch.from_numpy(lbl.copy()).long()
        if self.transform: img = self.transform(img)
        return img, lbl

class TemporalPredictionDataset(Dataset):
    def __init__(self, manifest_csv: str, num_time_steps: int = 6, augment: bool = False, aug_cfg: Optional[dict] = None):
        self.df = pd.read_csv(manifest_csv); self.num_time_steps = num_time_steps
        self.augmenter = SatelliteAugment() if augment else None
        self.df["pos"] = self.df["row"].astype(str) + "_" + self.df["col"].astype(str)
        self.sequences = self._build_sequences()
    def _build_sequences(self):
        s = []
        for p, g in self.df.groupby("pos"):
            g = g.sort_values("label_year")
            if len(g) < self.num_time_steps + 1: continue
            for i in range(len(g) - self.num_time_steps):
                in_r, tr = g.iloc[i: i + self.num_time_steps], g.iloc[i + self.num_time_steps]
                s.append((in_r, tr))
        return s
    def __len__(self): return len(self.sequences)
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        in_r, tr = self.sequences[idx]; fs = []
        for _, r in in_r.iterrows(): fs.append(np.load(r["img_path"])[-1])
        isq, t_l = np.stack(fs, axis=0), np.load(tr["lbl_path"])
        if self.augmenter: isq, t_l = self.augmenter(isq, t_l)
        return torch.from_numpy(isq.copy()).float(), torch.from_numpy(t_l.copy()).long()
