"""
Change Detection Inference
==========================
Runs trained change detection model over full Fatehgarh AOI.
Outputs GeoTIFF change mask and PNG visualization.

Usage:
    python src/inference/detect.py \
        --config config.yaml \
        --checkpoint outputs/checkpoints/best_detect.pth \
        --year1 data/raw/hls_2022.tif \
        --year2 data/raw/hls_2023.tif \
        --output outputs/change_map_2022_2023.tif
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.utils.proj_fix import setup_proj_env; setup_proj_env()

import yaml
import logging
import argparse
import numpy as np
import torch
import rasterio
from rasterio.transform import from_bounds
from pathlib import Path
from tqdm import tqdm
from typing import Tuple, List


from src.model.vanaagni import build_vanaagni
from src.data.preprocess import load_hls_tif
from src.data.auxiliary_loader import load_spatial_auxiliary, load_7d_weather_sequence
import rasterio

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def get_device():
    """Select best available compute device (ROCm/CUDA > CPU)."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_model(cfg: dict, checkpoint_path: str, device):
    """Load VanAgni model and weights from checkpoint."""
    model = build_vanaagni(cfg).to(device)
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = ckpt.get("model_state", ckpt)
    model.load_state_dict(state)
    model.eval()
    log.info(f"✅ Model loaded from {checkpoint_path}")
    return model


def sliding_window_inference(
    model: torch.nn.Module,
    image_stack: np.ndarray,   # (T, C, H, W)
    reference_tif: str,
    target_date_str: str,
    tile_size: int = 224,
    overlap: int = 64,
    device: torch.device = None,
    num_classes: int = 5,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run multi-modal model inference using sliding window over a large image.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    T, C, H, W = image_stack.shape
    stride = tile_size - overlap

    # Accumulate predictions and hit counts
    prob_map = np.zeros((num_classes, H, W), dtype=np.float32)
    count_map = np.zeros((H, W), dtype=np.float32)

    row_starts = list(range(0, H - tile_size + 1, stride))
    col_starts = list(range(0, W - tile_size + 1, stride))

    # Ensure we cover edges
    if (H - tile_size) % stride != 0:
        row_starts.append(H - tile_size)
    if (W - tile_size) % stride != 0:
        col_starts.append(W - tile_size)

    positions = [(r, c) for r in row_starts for c in col_starts]
    log.info(f"  Running {len(positions)} multi-modal tile inferences...")
    
    with rasterio.open(reference_tif) as ref:
        transform = ref.transform

    for r, c in tqdm(positions, desc="Inference"):
        patch = image_stack[:, :, r:r + tile_size, c:c + tile_size]
        
        # Calculate center lat/lon of this specific patch for auxiliary data
        center_x = c + tile_size // 2
        center_y = r + tile_size // 2
        lon, lat = rasterio.transform.xy(transform, center_y, center_x)
        
        # Load real auxiliary data
        terrain_np, lc_np = load_spatial_auxiliary(lon, lat, patch_size=tile_size)
        weather_np = load_7d_weather_sequence(target_date_str, lon, lat)
        
        # Prepare Tensors
        patch_t = torch.from_numpy(patch[np.newaxis]).float().to(device)  # (1, T, C, H, W)
        terrain_t = torch.from_numpy(terrain_np[np.newaxis]).float().to(device)
        lc_t = torch.from_numpy(lc_np[np.newaxis]).float().to(device)
        weather_t = torch.from_numpy(weather_np[np.newaxis]).float().to(device)
        
        # Current weather (using day 3 which is T0)
        curr_weather_t = weather_t[:, 3, :]
        
        # Burn age (mocked as zeros for inference unless tracked)
        burn_age_t = torch.zeros(1, 1, tile_size, tile_size).to(device)

        with torch.no_grad():
            out = model(
                x_temporal = patch_t,
                weather_current = curr_weather_t,
                weather_7d = weather_t,
                terrain = terrain_t,
                landcover = lc_t,
                burn_age = burn_age_t
            )
            probs = torch.softmax(out["logits"], dim=1).cpu().numpy()[0]

        prob_map[:, r:r + tile_size, c:c + tile_size] += probs
        count_map[r:r + tile_size, c:c + tile_size] += 1

    # Average overlapping predictions
    count_map = np.maximum(count_map, 1)
    prob_map /= count_map[np.newaxis]

    change_mask = prob_map.argmax(axis=0).astype(np.uint8)
    return change_mask, prob_map


def save_geotiff(array: np.ndarray, reference_tif: str, out_path: str, dtype=np.uint8):
    """Save output array as GeoTIFF with spatial reference from input."""
    with rasterio.open(reference_tif) as ref:
        transform = ref.transform
        crs = ref.crs
        height, width = ref.height, ref.width

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, "w",
        driver="GTiff",
        height=height, width=width,
        count=1,
        dtype=dtype,
        crs=crs,
        transform=transform,
        compress="lzw",
    ) as dst:
        dst.write(array.astype(dtype), 1)

    log.info(f"✅ Saved: {out_path}")


def run_detection(cfg: dict, checkpoint: str, tif_paths: List[str],
                   output_path: str, num_frames: int = None):
    """
    Full inference pipeline: load imagery → run model → save outputs.

    Args:
        cfg: Config dict
        checkpoint: Path to trained model checkpoint
        tif_paths: List of HLS GeoTIF paths (chronological, length >= num_frames)
        output_path: Output change mask GeoTIFF path
        num_frames: Number of time frames (defaults to model's num_time_steps)
    """
    # Use the same T as training (model was trained with this many frames)
    if num_frames is None:
        num_frames = cfg["model"].get("num_frames", cfg["model"].get("num_time_steps", 3))
    log.info(f"Using {num_frames} time frames (matches training config)")

    device = get_device()
    log.info(f"🖥️  Running on: {device}")

    # Load model
    model = load_model(cfg, checkpoint, device)

    # Load and normalize imagery
    log.info(f"📂 Loading {len(tif_paths)} imagery files...")
    frames = [load_hls_tif(p) for p in tif_paths[-num_frames:]]  # (C, H, W) each
    image_stack = np.stack(frames, axis=0)  # (T, C, H, W)
    log.info(f"  Image stack shape: {image_stack.shape}")

    # Run sliding window inference
    change_mask, prob_map = sliding_window_inference(
        model=model,
        image_stack=image_stack,
        tile_size=cfg["model"]["img_size"],
        overlap=64,
        device=device,
        num_classes=cfg["model"]["num_classes"],
    )

    # Save change mask GeoTIFF
    reference_tif = tif_paths[-1]
    save_geotiff(change_mask, reference_tif, output_path)

    # Save probability map for visualization
    prob_out = output_path.replace(".tif", "_prob.tif")
    save_geotiff((prob_map[1] * 255).astype(np.uint8), reference_tif, prob_out, dtype=np.uint8)

    # Summary stats
    total_pixels = change_mask.size
    changed = change_mask.sum()
    log.info(f"\n📊 Change Detection Results:")
    log.info(f"   Total pixels: {total_pixels:,}")
    log.info(f"   Changed pixels (forest loss): {changed:,} ({100*changed/total_pixels:.2f}%)")

    # Estimate area (assuming 30m resolution)
    area_ha = changed * 900 / 10000
    log.info(f"   Estimated deforested area: {area_ha:.1f} ha")

    return change_mask, prob_map


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--input", nargs="+", help="Input HLS GeoTIFF paths (chronological)")
    parser.add_argument("--output", default="outputs/change_map.tif")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    if args.input:
        tif_paths = args.input
    else:
        # Auto-detect from raw data dir
        import glob
        raw_dir = cfg["paths"]["raw_dir"]
        tif_paths = sorted(glob.glob(os.path.join(raw_dir, "hls_*.tif")))
        log.info(f"Auto-detected {len(tif_paths)} input files")

    run_detection(cfg, args.checkpoint, tif_paths, args.output)
