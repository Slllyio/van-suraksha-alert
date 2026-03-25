"""
Dataset Classes
===============
PyTorch Dataset wrappers for change detection and temporal prediction tasks.
STRICTLY LOCAL VERSION: No web/earthaccess dependencies.

FIX (2026-03-14): Replaced zero-filled auxiliary placeholders with real data
loading from data_lake via auxiliary_loader. All auxiliary channels (weather,
terrain, burn_age, landcover) now load real on-disk data.
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

# Project root for auxiliary data resolution
_DATASET_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_real_auxiliary(lat: float, lon: float, date_str: str, patch_size: int = 224):
    """
    Load real auxiliary data (weather, terrain, burn_age, landcover) from data_lake.
    Falls back to zeros with a WARNING if data is unavailable — never silently.

    Returns:
        weather:    (10,) float32
        weather_7d: (10, 7) float32
        terrain:    (4, H, W) float32
        burn_age:   (3, H, W) float32
        landcover:  (11, H, W) float32
    """
    weather    = np.zeros(10, dtype=np.float32)
    weather_7d = np.zeros((10, 7), dtype=np.float32)
    terrain    = np.zeros((4, patch_size, patch_size), dtype=np.float32)
    burn_age   = np.zeros((3, patch_size, patch_size), dtype=np.float32)
    landcover  = np.zeros((11, patch_size, patch_size), dtype=np.float32)

    # Try importing the real auxiliary loader (available in full project)
    try:
        from src.data.auxiliary_loader import (
            load_spatial_auxiliary,
            load_7d_weather_sequence,
            load_burn_age,
        )

        # Terrain + Landcover
        try:
            terrain_np, lc_np = load_spatial_auxiliary(lon, lat, patch_size=patch_size)
            terrain = terrain_np.astype(np.float32)
            landcover = lc_np.astype(np.float32)
        except Exception as e:
            log.warning(f"Terrain/LC load failed for ({lat:.2f}, {lon:.2f}): {e}")

        # Weather (7-day sequence → current = day index 3)
        try:
            weather_seq = load_7d_weather_sequence(date_str, lon, lat)
            if weather_seq is not None and weather_seq.shape == (7, 10):
                weather_7d = weather_seq.T.astype(np.float32)  # (10, 7)
                weather = weather_seq[3].astype(np.float32)    # current day
            elif weather_seq is not None:
                weather_7d = weather_seq.astype(np.float32) if weather_seq.ndim == 2 else weather_7d
        except Exception as e:
            log.warning(f"Weather load failed for {date_str} ({lat:.2f}, {lon:.2f}): {e}")

        # Burn age
        try:
            burn_age = load_burn_age(lon, lat, date_str, patch_size=patch_size).astype(np.float32)
        except Exception as e:
            log.warning(f"Burn age load failed for {date_str} ({lat:.2f}, {lon:.2f}): {e}")

    except ImportError:
        log.warning(
            "auxiliary_loader not available — using zero-filled auxiliary data. "
            "This WILL degrade model performance. Install full project dependencies."
        )

    return weather, weather_7d, terrain, burn_age, landcover

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

        # Load REAL auxiliary data from data_lake (no more zero-fill placeholders)
        weather_np, weather_7d_np, terrain_np, burn_age_np, landcover_np = \
            _load_real_auxiliary(lat, lon, date_str, patch_size=224)

        weather    = torch.from_numpy(weather_np)
        weather_7d = torch.from_numpy(weather_7d_np)
        terrain    = torch.from_numpy(terrain_np)
        burn_age   = torch.from_numpy(burn_age_np)
        landcover  = torch.from_numpy(landcover_np)

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
