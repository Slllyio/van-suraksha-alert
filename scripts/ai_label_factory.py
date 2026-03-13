#!/usr/bin/env python3
"""
scripts/ai_label_factory.py
===========================
The AI-Driven Labeling Factory (Stage 4).
Uses Segment Anything Model (SAM) for Geospatial Data (samgeo)
to convert noisy VIIRS fire points into precise 30m burn scar polygons.

Logic:
  1. Load VIIRS detections from fire_links.csv
  2. For VIIRS_ONLY events, fetch multispectral HLS bands (B12, B8A, B04)
  3. Prompt SAM-EO with the VIIRS point as a "Positive" seed
  4. Generate a sharp, high-resolution burn scar mask
  5. Save as a GOLD-tier equivalent label for VanAagni training.
"""

import os
import sys
import json
import logging
import argparse
import numpy as np
import pandas as pd
import torch
import rasterio
from pathlib import Path
from datetime import datetime, timedelta

# -- PROJ fix
from src.utils.proj_fix import setup_proj_env; setup_proj_env()

# -- SAM-EO imports
try:
    from samgeo import SamGeo
    from samgeo.text_sam import LangSAM
except ImportError:
    print("CRITICAL: segment-geospatial (samgeo) not installed. Run: pip install segment-geospatial")
    sys.exit(1)

# -- Paths
ROOT      = Path(__file__).resolve().parent.parent
DATA_LAKE = ROOT / "data_lake"
HLS_DIR   = DATA_LAKE / "satellite_imagery" / "hls_s30"
LINKS_CSV = DATA_LAKE / "burn_scars" / "fire_links.csv"
OUT_DIR   = DATA_LAKE / "fire_labels_ai"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ai_factory")

class SamLabelFactory:
    def __init__(self, model_type="vit_h", checkpoint=None):
        log.info(f"Initializing SAM-EO ({model_type})...")
        # samgeo handles automatic checkpoint download if not provided
        self.sam = SamGeo(
            model_type=model_type,
            checkpoint=checkpoint,
            sam_kwargs=None,
        )
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info(f"SAM-EO ready on {self.device}")

    def get_hls_stack(self, tile, date_str):
        """Find and stack B12, B8A, B04 for a given tile and date."""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        folder = HLS_DIR / tile / str(dt.year) / f"{dt.month:02d}" / f"{dt.day:02d}"
        
        # We need SWIR2 (B12), NIR (B8A), and Red (B04) for burn scar contrast
        bands = ["B12", "B8A", "B04"]
        paths = {}
        for b in bands:
            matches = list(folder.glob(f"*.{b}.tif"))
            if matches:
                paths[b] = matches[0]
        
        if len(paths) < 3:
            return None, None

        # Read and stack
        data = []
        profile = None
        for b in bands:
            with rasterio.open(paths[b]) as src:
                data.append(src.read(1))
                if profile is None:
                    profile = src.profile.copy()
        
        # Stack as RGB-like for SAM (H, W, 3)
        stack = np.stack(data, axis=-1)
        # Normalise to 0-255 for SAM
        stack = np.clip(stack / 4000 * 255, 0, 255).astype(np.uint8)
        
        return stack, profile

    def delineate(self, stack, profile, lat, lon):
        """Run SAM-EO with a point prompt."""
        from pyproj import Transformer
        crs_str = str(profile.get("crs", "EPSG:32643"))
        transformer = Transformer.from_crs("EPSG:4326", crs_str, always_xy=True)
        x_utm, y_utm = transformer.transform(lon, lat)
        
        transform = profile["transform"]
        col = (x_utm - transform.c) / transform.a
        row = (y_utm - transform.f) / transform.e
        
        # Points format: [[x, y]]
        points = [[col, row]]
        point_labels = [1] # 1 = positive
        
        # SAM predict
        mask_path = "tmp_sam_mask.tif"
        self.sam.predict(
            image=stack, 
            point_coords=points, 
            point_labels=point_labels, 
            output=mask_path,
            index=1 # first mask
        )
        
        with rasterio.open(mask_path) as src:
            mask = src.read(1)
        
        if os.path.exists(mask_path):
            os.remove(mask_path)
            
        return mask

def main():
    if not LINKS_CSV.exists():
        log.error(f"Links CSV not found: {LINKS_CSV}")
        return

    df = pd.read_csv(LINKS_CSV)
    # Filter for VIIRS_ONLY or low-confidence events that need AI refinement
    targets = df[df["spatial_hit"] == False].copy()
    
    if len(targets) == 0:
        log.info("No VIIRS_ONLY targets found for refinement.")
        return

    factory = SamLabelFactory()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for idx, row in targets.iterrows():
        tile = row["tile"]
        date_str = row["scene_date"]
        lat, lon = row["fire_lat"], row["fire_lon"]
        
        log.info(f"Processing {tile} {date_str} at ({lat}, {lon})")
        
        stack, profile = factory.get_hls_stack(tile, date_str)
        if stack is None:
            log.warning(f"  Skipping: HLS spectral data missing for {tile} {date_str}")
            continue
            
        mask = factory.delineate(stack, profile, lat, lon)
        
        # Save high-precision AI label
        tag = f"{datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y%m%d')}_{tile}_AI"
        out_path = OUT_DIR / f"label_{tag}.tif"
        
        profile.update(dtype="uint8", count=1, nodata=255, compress="lzw")
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(mask.astype(np.uint8)[np.newaxis, :, :])
            
        log.info(f"  Success: AI Label saved -> {out_path.name}")

if __name__ == "__main__":
    main()
