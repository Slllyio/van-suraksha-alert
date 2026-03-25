"""
VanAagni Stage 2 Severity Inference
====================================
Runs 4-class severity classification with a confidence-based threshold.
Prioritizes precision by only flagging fire if confidence exceeds threshold.

Usage:
    python src/inference/severity.py \
        --config models/vanaagni/stage2_severity.yaml \
        --checkpoint outputs/vanaagni_stage2/checkpoints/best_vanaagni.pth \
        --input data/raw/hls_T0.tif data/raw/hls_T1.tif data/raw/hls_T2.tif \
        --threshold 0.7 \
        --output outputs/vanaagni_stage2/severity_map.tif
"""

import sys, os
from datetime import datetime
from pathlib import Path
import argparse
import yaml
import logging
import numpy as np
import torch
import rasterio
from tqdm import tqdm
from typing import Tuple, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.utils.proj_fix import setup_proj_env; setup_proj_env()
from src.model.vanaagni import build_vanaagni
from src.data.preprocess import load_hls_tif
from src.data.auxiliary_loader import load_spatial_auxiliary, load_7d_weather_sequence, load_burn_age
from src.inference.detect import save_geotiff, get_device, load_model

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

@torch.no_grad()
def sliding_window_severity(
    model: torch.nn.Module,
    image_stack: np.ndarray,
    reference_tif: str,
    target_date_str: str,
    tile_size: int = 224,
    overlap: int = 64,
    device: torch.device = None,
    num_classes: int = 4,
    threshold: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run Stage 2 inference with confidence thresholding."""
    T, C, H, W = image_stack.shape
    stride = tile_size - overlap

    # Accumulate probabilities
    prob_map = np.zeros((num_classes, H, W), dtype=np.float32)
    count_map = np.zeros((H, W), dtype=np.float32)

    row_starts = list(range(0, H - tile_size + 1, stride))
    col_starts = list(range(0, W - tile_size + 1, stride))
    if (H - tile_size) % stride != 0: row_starts.append(H - tile_size)
    if (W - tile_size) % stride != 0: col_starts.append(W - tile_size)

    positions = [(r, c) for r in row_starts for c in col_starts]
    
    with rasterio.open(reference_tif) as ref:
        transform = ref.transform

    log.info(f"  Processing {len(positions)} tiles with threshold={threshold}...")
    
    for r, c in tqdm(positions, desc="Severity"):
        patch = image_stack[:, :, r:r + tile_size, c:c + tile_size]
        center_x, center_y = c + tile_size // 2, r + tile_size // 2
        lon, lat = rasterio.transform.xy(transform, center_y, center_x)
        
        # Auxiliary data
        terrain_np, lc_np = load_spatial_auxiliary(lon, lat, patch_size=tile_size)
        weather_np = load_7d_weather_sequence(target_date_str, lon, lat)
        burn_age_np = load_burn_age(lon, lat, target_date_str, patch_size=tile_size)
        
        # Tensors
        patch_t = torch.from_numpy(patch[np.newaxis]).float().to(device).permute(0, 2, 1, 3, 4)
        terrain_t = torch.from_numpy(terrain_np[np.newaxis]).float().to(device)
        lc_t = torch.from_numpy(lc_np[np.newaxis]).float().to(device)
        burn_age_t = torch.from_numpy(burn_age_np[np.newaxis]).float().to(device)
        
        if weather_np is not None:
            weather_7d_t = torch.from_numpy(weather_np.T[np.newaxis]).float().to(device)
            curr_weather_t = torch.from_numpy(weather_np[3:4]).float().to(device)
        else:
            weather_7d_t = torch.zeros(1, 10, 7).to(device)
            curr_weather_t = torch.zeros(1, 10).to(device)

        out = model(patch_t, curr_weather_t, weather_7d_t, terrain_t, burn_age_t, lc_t)
        probs = torch.softmax(out["logits"], dim=1).cpu().numpy()[0]

        prob_map[:, r:r + tile_size, c:c + tile_size] += probs
        count_map[r:r + tile_size, c:c + tile_size] += 1

    # Average
    prob_map /= np.maximum(count_map, 1)
    
    # Apply Threshold: sum of fire classes (1, 2, 3) must exceed threshold
    fire_prob_sum = prob_map[1:].sum(axis=0)
    is_fire = (fire_prob_sum >= threshold)
    
    # Base prediction is argmax
    severity_mask = prob_map.argmax(axis=0).astype(np.uint8)
    
    # Force unburned (0) where fire confidence is low
    severity_mask[~is_fire] = 0
    
    return severity_mask, prob_map

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--input", nargs="+", required=True, help="3 HLS GeoTIFFs (T-2, T-1, T0)")
    parser.add_argument("--threshold", type=float, default=0.5, help="Confidence threshold for fire (0-1)")
    parser.add_argument("--output", default="outputs/severity_map.tif")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    device = get_device()
    model = load_model(cfg, args.checkpoint, device)
    
    # Load frames
    frames = [load_hls_tif(p) for p in args.input[-3:]]
    image_stack = np.stack(frames, axis=0)
    
    reference_tif = args.input[-1]
    target_date_str = datetime.now().strftime("%Y-%m-%d") # Default
    
    severity_mask, prob_map = sliding_window_severity(
        model, image_stack, reference_tif, target_date_str,
        tile_size=cfg["model"]["img_size"],
        device=device, threshold=args.threshold
    )
    
    save_geotiff(severity_mask, reference_tif, args.output)
    
    # Save confidence map (any fire)
    conf_path = args.output.replace(".tif", "_confidence.tif")
    fire_conf = prob_map[1:].sum(axis=0)
    save_geotiff((fire_conf * 255).astype(np.uint8), reference_tif, conf_path)
    
    log.info(f"Done. Severity mask: {args.output}")
    log.info(f"Confidence map: {conf_path}")

if __name__ == "__main__":
    main()
