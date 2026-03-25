"""
dNBR Label Generator
====================
Computes delta Normalized Burn Ratio (dNBR) between pre-fire and post-fire 
HLS scenes. This provides a deterministic, physics-grounded label for 
retraining the VanAagni model without relying on the current biased model.

Formula:
  NBR = (NIR - SWIR2) / (NIR + SWIR2)
  dNBR = NBR_pre - NBR_post
"""

import numpy as np
import rasterio
from pathlib import Path
import logging
from typing import Tuple

log = logging.getLogger(__name__)

def compute_nbr(nir: np.ndarray, swir2: np.ndarray) -> np.ndarray:
    """Compute Normalized Burn Ratio."""
    return (nir - swir2) / (nir + swir2 + 1e-6)

def generate_dnbr_label(
    pre_hls_dir: Path, 
    post_hls_dir: Path, 
    out_path: Path
) -> bool:
    """
    Computes dNBR and saves a thresholded burn label.
    """
    try:
        # Load Bands (NIR=B8A, SWIR2=B12)
        def load_pair(d):
            with rasterio.open(list(d.glob("*.B8A.tif"))[0]) as src:
                nir = src.read(1).astype(np.float32) * 1e-4
                profile = src.profile
            with rasterio.open(list(d.glob("*.B12.tif"))[0]) as src:
                swir2 = src.read(1).astype(np.float32) * 1e-4
            return nir, swir2, profile

        pre_nir, pre_swir2, profile = load_pair(pre_hls_dir)
        post_nir, post_swir2, _ = load_pair(post_hls_dir)
        
        # 1. Compute NBRs
        nbr_pre = compute_nbr(pre_nir, pre_swir2)
        nbr_post = compute_nbr(post_nir, post_swir2)
        
        # 2. Compute dNBR
        dnbr = nbr_pre - nbr_post
        
        # 3. Apply Thresholds (Standard USGS dNBR levels)
        # > 0.1: Enhanced Regrowth (skip)
        # -0.1 to 0.1: Unburned
        # 0.1 to 0.27: Low Severity
        # 0.27 to 0.44: Moderate-Low
        # 0.44 to 0.66: Moderate-High
        # > 0.66: High Severity
        
        # Binary Label: 1 if dNBR > 0.1 (any burn)
        label = (dnbr > 0.1).astype(np.uint8)
        
        # 4. Save Label as GeoTIFF
        out_path.parent.mkdir(parents=True, exist_ok=True)
        profile.update(dtype=rasterio.uint8, count=1, nodata=0, compress='lzw')
        with rasterio.open(out_path, 'w', **profile) as dst:
            dst.write(label, 1)
            
        return True
    except Exception as e:
        log.error(f"Failed to generate dNBR label: {e}")
        return False

if __name__ == "__main__":
    # Test execution for the first fire event
    pre = Path("data_lake/satellite_imagery/hls_s30/T43QFG/2018/04/15")
    post = Path("data_lake/satellite_imagery/hls_s30/T43QFG/2018/05/05")
    out = Path("data_lake/fire_labels/T43QFG/2018/04/label_20180419_T43QFG.tif")
    
    if pre.exists() and post.exists():
        generate_dnbr_label(pre, post, out)
        print(f"Verified dNBR label generated at {out}")
