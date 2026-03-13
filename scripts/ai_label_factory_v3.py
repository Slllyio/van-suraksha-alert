#!/usr/bin/env python3
"""
scripts/ai_label_factory_v3.py
==============================
High-Confidence Smart Sampling AI Label Factory.
Clusters 58k fire points into events and uses SAM-EO for precision labels.
Focus: Guna Fire Season (March 1 - June 1), 2020-2025.
"""

import os
import sys

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import logging
import pandas as pd
import numpy as np
import rasterio
import torch
from pathlib import Path
from datetime import datetime, timedelta
from sklearn.cluster import DBSCAN
from segment_anything import sam_model_registry, SamPredictor
import earthaccess

# -- PROJ fix
from src.utils.proj_fix import setup_proj_env; setup_proj_env()

# -- Paths
ROOT      = Path(ROOT_DIR)
FIRMS_CSV = ROOT / "outputs" / "checkpoints" / "data" / "training" / "firms_guna_viirs.csv"
OUT_DIR   = ROOT / "data" / "labels" / "ai_refined"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ai_factory_v3")

class AiLabelFactoryV3:
    def __init__(self):
        log.info("Logging into Earthdata...")
        os.environ.setdefault("EARTHDATA_USERNAME", "akshayr11@gmail.com")
        os.environ.setdefault("EARTHDATA_PASSWORD", "40983#Akki")
        earthaccess.login(strategy="environment")
        
        checkpoint = ROOT / "models" / "sam_vit_h_4b8939.pth"
        if not checkpoint.exists():
            log.info(f"Downloading SAM checkpoint to {checkpoint}...")
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            import urllib.request
            url = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth"
            urllib.request.urlretrieve(url, str(checkpoint))
            
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info(f"Initializing SAM on {self.device}...")
        sam = sam_model_registry["vit_h"](checkpoint=str(checkpoint))
        sam.to(device=self.device)
        self.predictor = SamPredictor(sam)
        log.info("SAM Predictor ready.")

    def cluster_and_sample(self, min_year=2020):
        log.info(f"Sampling high-confidence events from {min_year}-2025...")
        df = pd.read_csv(FIRMS_CSV)
        df["acq_date"] = pd.to_datetime(df["acq_date"])
        
        # Filter: Guna Fire Season (March 1 - June 1) + Recent Years
        mask = (df["acq_date"].dt.year >= min_year) & \
               (df["acq_date"].dt.month >= 3) & \
               (df["acq_date"].dt.month <= 6)
        df = df[mask].copy()
        
        # DBSCAN Spatial Clustering (eps=0.01 is ~1.1km at equator)
        coords = df[["latitude", "longitude"]].values
        db = DBSCAN(eps=0.01, min_samples=3).fit(coords)
        df["cluster"] = db.labels_
        
        # Keep only clustered points (ignore noise -1) and pick top 3 FRP per cluster
        events = df[df["cluster"] != -1].copy()
        sampled = events.sort_values("frp", ascending=False).groupby("cluster").head(3)
        
        log.info(f"Clustered {len(df)} points into {df['cluster'].nunique()} events.")
        log.info(f"Sampled {len(sampled)} target points for SAM-EO refinement.")
        return sampled

    def fetch_hls_for_point(self, lat, lon, date_dt):
        """Fetch HLS B12, B8A, B04 for a point and date."""
        start = date_dt.strftime("%Y-%m-%d")
        end = (date_dt + timedelta(days=5)).strftime("%Y-%m-%d")
        
        results = earthaccess.search_data(
            short_name="HLSS30",
            cloud_cover=(0, 20),
            temporal=(start, end),
            point=(lon, lat)
        )
        
        if not results: return None, None
            
        granule = results[0]
        links = [l for l in granule.data_links() if any(b in l for b in ["B12.tif", "B8A.tif", "B04.tif"])]
        if len(links) < 3: return None, None

        tmp_dir = ROOT / "tmp" / "hls_labels"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        files = earthaccess.download(links, str(tmp_dir))
        
        paths = {Path(f).name.split(".")[-2]: Path(f) for f in files}
        data = []; profile = None
        for b in ["B12", "B8A", "B04"]:
            with rasterio.open(paths[b]) as src:
                data.append(src.read(1))
                if profile is None: profile = src.profile.copy()
        
        stack = np.stack(data, axis=-1)
        stack = np.clip(stack / 4000 * 255, 0, 255).astype(np.uint8)
        return stack, profile

    def run(self, max_labels=100):
        sampled = self.cluster_and_sample()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        for idx, row in sampled.iterrows():
            if success_count >= max_labels: break
            
            lat, lon, dt = row["latitude"], row["longitude"], row["acq_date"]
            log.info(f"[{success_count+1}/{max_labels}] Delineating: {dt.date()} at ({lat}, {lon}) FRP={row['frp']}")
            
            try:
                stack, profile = self.fetch_hls_for_point(lat, lon, dt)
                if stack is None: continue
                
                # Project point
                from pyproj import Transformer
                crs_str = str(profile.get("crs", "EPSG:32643"))
                transformer = Transformer.from_crs("EPSG:4326", crs_str, always_xy=True)
                x, y = transformer.transform(lon, lat)
                tr = profile["transform"]
                col, row_px = (x - tr.c) / tr.a, (y - tr.f) / tr.e
                
                # SAM predict
                self.predictor.set_image(stack)
                masks, _, _ = self.predictor.predict(
                    point_coords=np.array([[col, row_px]]),
                    point_labels=np.array([1]),
                    multimask_output=False
                )
                
                # Save
                tag = f"{dt.strftime('%Y%m%d')}_lat{lat:.2f}_lon{lon:.2f}_AI"
                out_file = OUT_DIR / f"label_{tag}.tif"
                profile.update(dtype="uint8", count=1, nodata=255, compress="lzw")
                with rasterio.open(out_file, "w", **profile) as dst:
                    dst.write(masks[0].astype(np.uint8)[np.newaxis, :, :])
                
                success_count += 1
                log.info(f"  Saved AI Label: {out_file.name}")
            except Exception as e:
                log.error(f"  Error processing point: {e}")

if __name__ == "__main__":
    factory = AiLabelFactoryV3()
    # Processing first 100 high-confidence diverse events as the 'Golden Dataset'
    factory.run(max_labels=100)
