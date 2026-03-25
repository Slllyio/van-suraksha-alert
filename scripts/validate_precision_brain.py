#!/usr/bin/env python3
"""
scripts/validate_precision_brain.py
===================================
Final validation script for the Upgraded VanAagni Brain.
Loads the high-precision weights and runs inference on a cached sample.
"""

import os
import sys
import torch
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import yaml
import rasterio

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.model.vanaagni import build_vanaagni
from src.utils.proj_fix import setup_proj_env; setup_proj_env()

# Paths
ROOT = Path(ROOT_DIR)
CONFIG_PATH = ROOT / "config.yaml"
CHECKPOINT = ROOT / "outputs" / "checkpoints" / "epoch_080_detect.pth"
CACHE_DIR = ROOT / "data" / "training" / "cache"
LABELS_DIR = ROOT / "data" / "labels" / "ai_refined"

def validate():
    print("======================================================")
    print("🌲 VanAagni Precision Brain Validation")
    print("======================================================")

    # 1. Load Config and Model
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    
    device = torch.device("cpu") # Use CPU for simple validation visualization
    print(f"Loading Model with 600M Backbone...")
    model = build_vanaagni(cfg).to(device)
    
    # 2. Load Weights
    print(f"Loading Precision Weights: {CHECKPOINT.name}")
    checkpoint_data = torch.load(CHECKPOINT, map_location=device, weights_only=False)
    
    # Check if weights are nested (common in our training script)
    if "model_state" in checkpoint_data:
        state_dict = checkpoint_data["model_state"]
    else:
        state_dict = checkpoint_data
        
    model.load_state_dict(state_dict)
    model.eval()
    print("Brain is Online.")

    # 3. Pick a sample from cache
    samples = list(CACHE_DIR.glob("*.npz"))
    if not samples:
        print("Error: No cached samples found in data/training/cache")
        return
    
    sample_path = samples[0]
    print(f"Testing on sample: {sample_path.name}")
    
    with np.load(sample_path) as data:
        hls = torch.from_numpy(data["hls"]).unsqueeze(0) # (1, T, C, H, W)
        # Transpose to (B, C, T, H, W) for Prithvi
        hls = hls.transpose(1, 2)
    
    # 4. Load REAL auxiliary data (not zero-filled placeholders)
    B, C, T, H, W = hls.shape

    # Extract lat/lon/date from sample filename for auxiliary data loading
    parts = sample_path.stem.split("_")
    val_lat = float(parts[0].replace("lat", ""))
    val_lon = float(parts[1].replace("lon", ""))
    val_date = parts[2]

    try:
        from src.data.auxiliary_loader import load_spatial_auxiliary, load_7d_weather_sequence, load_burn_age

        # Load real terrain + landcover
        terrain_np, lc_np = load_spatial_auxiliary(val_lon, val_lat, patch_size=H)
        terrain   = torch.from_numpy(terrain_np).unsqueeze(0)   # (1, 4, H, W)
        landcover = torch.from_numpy(lc_np).unsqueeze(0)        # (1, 11, H, W)

        # Load real weather
        weather_seq = load_7d_weather_sequence(val_date, val_lon, val_lat)
        if weather_seq is not None and weather_seq.ndim == 2:
            weather_7d = torch.from_numpy(weather_seq.T).unsqueeze(0).float()  # (1, 10, 7)
            weather    = torch.from_numpy(weather_seq[3]).unsqueeze(0).float() # (1, 10)
        else:
            print("  WARNING: Weather data unavailable, using zeros")
            weather    = torch.zeros(B, 10)
            weather_7d = torch.zeros(B, 10, 7)

        # Load real burn age
        burn_age_np = load_burn_age(val_lon, val_lat, val_date, patch_size=H)
        burn_age = torch.from_numpy(burn_age_np).unsqueeze(0)   # (1, 3, H, W)

        print(f"  Loaded REAL auxiliary data for ({val_lat:.2f}, {val_lon:.2f}, {val_date})")
        print(f"  Terrain range: [{terrain.min():.3f}, {terrain.max():.3f}]")
        print(f"  Weather range: [{weather.min():.3f}, {weather.max():.3f}]")

    except Exception as e:
        print(f"  WARNING: Could not load real auxiliary data: {e}")
        print(f"  Falling back to zeros — validation results will be UNRELIABLE")
        weather    = torch.zeros(B, 10)
        weather_7d = torch.zeros(B, 10, 7)
        terrain    = torch.zeros(B, 4, H, W)
        burn_age   = torch.zeros(B, 3, H, W)
        landcover  = torch.zeros(B, 11, H, W)

    # 5. Inference with real multi-modal inputs
    print("Running multi-modal inference...")
    with torch.no_grad():
        output = model(hls, weather, weather_7d, terrain, burn_age, landcover)
    
    severity = output["logits"].squeeze().numpy()
    uncertainty = torch.exp(output["log_var"]).sqrt().squeeze().numpy() # Predicted StdDev
    
    # 6. Find corresponding label
    # Tag format in cache: lat24.56_lon77.69_20230411.npz
    # Tag format in labels: label_20230411_lat24.56_lon77.69_AI.tif
    parts = sample_path.stem.split("_")
    lat_lon = f"{parts[0]}_{parts[1]}"
    date_str = parts[2]
    label_matches = list(LABELS_DIR.glob(f"label_{date_str}_{lat_lon}_AI.tif"))
    
    gt_mask = None
    if label_matches:
        with rasterio.open(label_matches[0]) as src:
            gt_mask = src.read(1)[:224, :224]
    
    # 7. Results
    print("\nResults Analysis:")
    print(f"  Severity Range:    [{severity.min():.4f}, {severity.max():.4f}]")
    print(f"  Mean Uncertainty:  {uncertainty.mean():.4f}")
    
    if gt_mask is not None:
        mse = np.mean((severity - gt_mask)**2)
        print(f"  Mean Squared Error vs SAM-EO: {mse:.4f}")

    print("\n[SUCCESS] Precision Brain successfully processed the spatial-temporal cube.")
    print("======================================================")

if __name__ == "__main__":
    validate()
