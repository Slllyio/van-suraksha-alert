#!/usr/bin/env python3
"""
scripts/ai_label_factory_v2.py
==============================
AI-Driven Labeling Factory with Autonomous HLS Fetching.
Uses SAM-EO to generate pixel-accurate labels from FIRMS CSV points.
"""

import os
import sys

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import logging
import pandas as pd
import numpy as np
import rasterio
import torch
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple

# -- PROJ fix
from src.utils.proj_fix import setup_proj_env; setup_proj_env()

# -- SAM-EO imports
try:
    from samgeo import SamGeo
    from segment_anything import sam_model_registry, SamPredictor
except ImportError:
    print("CRITICAL: segment-geospatial or segment-anything not installed.")
    sys.exit(1)

import earthaccess

# -- Paths
ROOT      = Path(__file__).resolve().parent.parent
FIRMS_CSV = ROOT / "outputs" / "checkpoints" / "data" / "training" / "firms_guna_viirs.csv"
OUT_DIR   = ROOT / "data" / "labels" / "ai_refined"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ai_factory_v2")

class AiLabelFactory:
    def __init__(self):
        log.info("Logging into Earthdata...")
        # Use credentials from existing download script
        os.environ.setdefault("EARTHDATA_USERNAME", "akshayr11@gmail.com")
        os.environ.setdefault("EARTHDATA_PASSWORD", "40983#Akki")
        earthaccess.login(strategy="environment")
        
        # Manually handle checkpoint download since samgeo is failing with None
        checkpoint = os.path.join(ROOT, "models", "sam_vit_h_4b8939.pth")
        if not os.path.exists(checkpoint):
            log.info(f"Downloading SAM checkpoint to {checkpoint}...")
            os.makedirs(os.path.dirname(checkpoint), exist_ok=True)
            import urllib.request
            url = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth"
            urllib.request.urlretrieve(url, checkpoint)
            
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info(f"Initializing SAM on {self.device}...")
        sam = sam_model_registry["vit_h"](checkpoint=checkpoint)
        sam.to(device=self.device)
        self.predictor = SamPredictor(sam)
        log.info("SAM Predictor ready.")

    def fetch_hls_for_point(self, lat, lon, date_str):
        """Fetch HLS B12, B8A, B04 for a point and date."""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        start = dt.strftime("%Y-%m-%d")
        end = (dt + timedelta(days=5)).strftime("%Y-%m-%d")
        
        log.info(f"  Searching HLS for {start}...")
        results = earthaccess.search_data(
            short_name="HLSS30",
            cloud_cover=(0, 20),
            temporal=(start, end),
            point=(lon, lat)
        )
        
        if not results:
            return None, None
            
        # Get the first result's HTTPS links
        granule = results[0]
        links = [l for l in granule.data_links() if any(b in l for b in ["B12.tif", "B8A.tif", "B04.tif"])]
        
        if len(links) < 3:
            return None, None

        # Download locally (temporary)
        tmp_dir = ROOT / "tmp" / "hls_labels"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        files = earthaccess.download(links, str(tmp_dir))
        
        # Load and stack
        paths = {Path(f).name.split(".")[-2]: Path(f) for f in files}
        data = []
        profile = None
        for b in ["B12", "B8A", "B04"]:
            with rasterio.open(paths[b]) as src:
                # Read a 512x512 window around the fire point
                # For simplicity in this factory, we read the whole tile then crop if needed, 
                # but here we'll just read the whole tile for SAM
                data.append(src.read(1))
                if profile is None:
                    profile = src.profile.copy()
        
        stack = np.stack(data, axis=-1)
        stack = np.clip(stack / 4000 * 255, 0, 255).astype(np.uint8)
        
        return stack, profile

    def process(self, limit=5):
        df = pd.read_csv(FIRMS_CSV)
        # Filter for high confidence recent years
        df = df[df["acq_date"] >= "2023-01-01"].head(limit)
        
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        for idx, row in df.iterrows():
            lat, lon = row["latitude"], row["longitude"]
            date_str = row["acq_date"]
            
            log.info(f"Processing Fire at ({lat}, {lon}) on {date_str}")
            stack, profile = self.fetch_hls_for_point(lat, lon, date_str)
            
            if stack is None:
                log.warning("  No HLS data found.")
                continue
                
            # SAM-EO Delineation
            mask_path = "tmp_mask.tif"
            
            # Project lat/lon to pixel
            from pyproj import Transformer
            crs_str = str(profile.get("crs", "EPSG:32643"))
            transformer = Transformer.from_crs("EPSG:4326", crs_str, always_xy=True)
            x, y = transformer.transform(lon, lat)
            transform = profile["transform"]
            col = (x - transform.c) / transform.a
            row_px = (y - transform.f) / transform.e
            
            # Use lower level predictor to ensure stability
            self.predictor.set_image(stack)
            masks, scores, logits = self.predictor.predict(
                point_coords=np.array([[col, row_px]]),
                point_labels=np.array([1]),
                multimask_output=False
            )
            mask = masks[0]
            
            # Save final refined label
            tag = f"{date_str.replace('-','')}_lat{lat:.2f}_lon{lon:.2f}_AI"
            out_file = OUT_DIR / f"label_{tag}.tif"
            
            profile.update(dtype="uint8", count=1, nodata=255, compress="lzw")
            with rasterio.open(out_file, "w", **profile) as dst:
                dst.write(mask.astype(np.uint8)[np.newaxis, :, :])
                
            log.info(f"  SUCCESS -> {out_file.name}")
            
            if os.path.exists(mask_path): os.remove(mask_path)

if __name__ == "__main__":
    factory = AiLabelFactory()
    factory.process(limit=3) # start with a small batch to test Step 1
