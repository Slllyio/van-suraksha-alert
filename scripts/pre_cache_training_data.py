#!/usr/bin/env python3
"""
scripts/pre_cache_training_data.py
==================================
Pre-caches and crops HLS imagery for the 89 precision labels.
Converts slow network fetching into fast local .npz loading.
"""

import os
import sys
import logging
import numpy as np
import rasterio
import torch
import earthaccess
from pathlib import Path
from datetime import datetime, timedelta
from pyproj import Transformer

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.utils.proj_fix import setup_proj_env; setup_proj_env()

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("pre_cache")

# Paths
ROOT       = Path(ROOT_DIR)
LABELS_DIR = ROOT / "data" / "labels" / "ai_refined"
CACHE_DIR  = ROOT / "data" / "training" / "cache"

class PreCacheAgent:
    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("EARTHDATA_USERNAME", "akshayr11@gmail.com")
        os.environ.setdefault("EARTHDATA_PASSWORD", "40983#Akki")
        earthaccess.login(strategy="environment")
        self.label_files = list(LABELS_DIR.glob("label_*.tif"))

    def _parse_filename(self, fname: str):
        parts = fname.replace("label_", "").replace("_AI.tif", "").split("_")
        date_str = parts[0]
        lat = float(parts[1].replace("lat", ""))
        lon = float(parts[2].replace("lon", ""))
        return date_str, lat, lon

    def fetch_and_crop(self, lat, lon, dt, idx, total):
        sample_tag = f"lat{lat:.2f}_lon{lon:.2f}_{dt.strftime('%Y%m%d')}"
        out_path = CACHE_DIR / f"{sample_tag}.npz"
        
        if out_path.exists():
            log.info(f"[{idx}/{total}] Already cached: {sample_tag}")
            return

        log.info(f"[{idx}/{total}] Caching {sample_tag}...")
        frames = []
        for i in range(3):
            target_dt = dt - timedelta(days=i*16)
            start = (target_dt - timedelta(days=5)).strftime("%Y-%m-%d")
            end = (target_dt + timedelta(days=5)).strftime("%Y-%m-%d")
            
            results = earthaccess.search_data(
                short_name="HLSS30", cloud_cover=(0, 20),
                temporal=(start, end), point=(lon, lat)
            )
            
            if results:
                links = [l for l in results[0].data_links() if any(b in l for b in ["B02.tif", "B03.tif", "B04.tif", "B8A.tif", "B11.tif", "B12.tif"])]
                files = earthaccess.download(links, "tmp/hls_cache")
                
                data = []
                for b in ["B02", "B03", "B04", "B8A", "B11", "B12"]:
                    b_file = [str(f) for f in files if f".{b}.tif" in str(f)][0]
                    with rasterio.open(b_file) as src:
                        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                        px, py = transformer.transform(lon, lat)
                        row, col = src.index(px, py)
                        window = rasterio.windows.Window(col - 112, row - 112, 224, 224)
                        data.append(src.read(1, window=window, boundless=True, fill_value=0))
                frames.append(np.stack(data))
            else:
                frames.append(np.zeros((6, 224, 224)))

        # Save as (T, C, H, W)
        image_seq = np.stack(frames).astype(np.float32) / 10000.0
        np.savez_compressed(out_path, hls=image_seq)
        log.info(f"  Saved -> {out_path.name}")

    def run(self):
        total = len(self.label_files)
        for i, lbl_path in enumerate(self.label_files):
            date_str, lat, lon = self._parse_filename(lbl_path.name)
            dt = datetime.strptime(date_str, "%Y%m%d")
            try:
                self.fetch_and_crop(lat, lon, dt, i+1, total)
            except Exception as e:
                log.error(f"  Failed {lbl_path.name}: {e}")

if __name__ == "__main__":
    agent = PreCacheAgent()
    agent.run()
