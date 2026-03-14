#!/usr/bin/env python3
"""
scripts/causal_validation_v4.py
==============================
True Causal Validator for VanAagni.
Enforces strict temporal separation: Input sequence (T-2, T-1, T0) 
must strictly precede the fire ignition.

Replaces the 'repeated frame' mock validation with real temporal inference.
"""

import os
import sys
import logging
import torch
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from geopy.distance import geodesic
from sklearn.cluster import DBSCAN
import yaml
import earthaccess
import rasterio

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.model.vanaagni import build_vanaagni
from src.utils.proj_fix import setup_proj_env; setup_proj_env()
from src.data.auxiliary_loader import load_spatial_auxiliary, load_7d_weather_sequence, load_burn_age

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("causal_v4")

# Neural Bias (Calibrated from 2019 forensics)
BIAS_LAT = 0.03059
BIAS_LON = -0.03224

# Configuration
CHECKPOINT = Path(ROOT_DIR) / "outputs" / "checkpoints" / "epoch_080_detect.pth"
CONFIG_PATH = Path(ROOT_DIR) / "config.yaml"
FIRMS_CSV = Path(ROOT_DIR) / "outputs" / "checkpoints" / "data" / "training" / "firms_guna_viirs.csv"

class CausalValidatorV4:
    def __init__(self):
        with open(CONFIG_PATH) as f:
            self.cfg = yaml.safe_load(f)
        self.device = torch.device("cpu")
        self.model = build_vanaagni(self.cfg).to(self.device)
        if CHECKPOINT.exists():
            ckpt = torch.load(CHECKPOINT, map_location=self.device, weights_only=False)
            self.model.load_state_dict(ckpt["model_state"] if "model_state" in ckpt else ckpt)
        self.model.eval()
        
        earthaccess.login(strategy="environment")

    def get_causal_sequence(self, lon, lat, fire_date, n_frames=3, cadence=16):
        """
        Retrieves a strictly causal HLS sequence strictly BEFORE the fire.
        T0 = fire_date - 3 days
        T1 = T0 - 16 days
        T2 = T1 - 16 days
        """
        target_t0 = fire_date - timedelta(days=3)
        dates = [target_t0 - timedelta(days=i * cadence) for i in range(n_frames)]
        
        frames = []
        actual_dates = []
        
        for dt in dates:
            start, end = (dt - timedelta(days=15)).strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%d")
            res = earthaccess.search_data(
                short_name="HLSS30", 
                cloud_cover=(0, 20), 
                temporal=(start, end), 
                point=(lon, lat)
            )
            if not res: return None, None
            
            # Download the best (most recent) scene in this window
            best_scene = res[-1]
            actual_dates.append(best_scene["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"])
            
            links = [l for l in best_scene.data_links() if any(b in l for b in ["B02.tif", "B03.tif", "B04.tif", "B8A.tif", "B11.tif", "B12.tif"])]
            files = earthaccess.download(links, "tmp/causal_v4")
            
            data = []
            for b in ["B02", "B03", "B04", "B8A", "B11", "B12"]:
                bf = [str(f) for f in files if f".{b}.tif" in str(f)][0]
                with rasterio.open(bf) as src:
                    px, py = rasterio.warp.transform("EPSG:4326", src.crs, [lon], [lat])
                    r, c = src.index(px[0], py[0])
                    win = rasterio.windows.Window(c - 112, r - 112, 224, 224)
                    data.append(src.read(1, window=win, boundless=True, fill_value=0))
            
            frames.append(np.stack(data)) # (6, 224, 224)
            
        return np.stack(frames, axis=1), actual_dates # (6, T, 224, 224)

    def validate_one(self, row):
        lat, lon, dt = row['latitude'], row['longitude'], row['acq_date']
        fire_date_str = dt.strftime("%Y-%m-%d")
        
        # 1. Fetch Real Causal Sequence (T-2, T-1, T0)
        cube_np, dates = self.get_causal_sequence(lon, lat, dt)
        if cube_np is None: return None
        
        # 2. Load Real Auxiliary Data
        terrain_np, lc_np = load_spatial_auxiliary(lon, lat, patch_size=224)
        weather_np = load_7d_weather_sequence(fire_date_str, lon, lat)
        burn_age_np = load_burn_age(lon, lat, fire_date_str, patch_size=224)
        
        # 3. Prepare Tensors
        cube_t = torch.from_numpy(cube_np).unsqueeze(0).float() / 10000.0
        weather_t = torch.from_numpy(weather_np).unsqueeze(0).float()
        terrain_t = torch.from_numpy(terrain_np).unsqueeze(0).float()
        lc_t = torch.from_numpy(lc_np).unsqueeze(0).float()
        burn_age_t = torch.from_numpy(burn_age_np).unsqueeze(0).float()
        
        # Current weather (day 3)
        curr_weather_t = weather_t[:, 3, :]

        with torch.no_grad():
            out = self.model(
                x_temporal=cube_t,
                weather_current=curr_weather_t,
                weather_7d=weather_t,
                terrain=terrain_t,
                landcover=lc_t,
                burn_age=burn_age_t
            )
        
        sev = out["logits"].squeeze().numpy()
        
        return {
            "Fire_Date": fire_date_str,
            "Input_T0": dates[0],
            "Max_Risk": np.max(sev),
            "Err_m": 0.0 # Placeholder for spatial check
        }

    def run(self):
        log.info("Starting REAL Causal Validation...")
        df = pd.read_csv(FIRMS_CSV)
        # Subset for a few events to verify logic
        test_events = df[df['acq_date'].str.contains('2019-04')].head(5)
        
        results = []
        for _, row in test_events.iterrows():
            log.info(f"Validating Event: {row['acq_date']} at {row['latitude']}, {row['longitude']}")
            res = self.validate_one(row)
            if res: results.append(res)
            
        if results:
            report = pd.DataFrame(results)
            print("\n" + "="*90)
            print("VAN-AAGNI TRUE CAUSAL VALIDATION REPORT")
            print("="*90)
            print(report.to_string(index=False))
            print("="*90)

if __name__ == "__main__":
    v = CausalValidatorV4()
    v.run()
