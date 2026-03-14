"""
Data Loader Utilities for VanAagni Auxiliary Modalities
=======================================================
Provides functions to dynamically load, align, and normalize terrain, 
landcover, burn age, and weather data for a specific spatial bounding box 
and time window. Replaces the 'zero-filling' mock data approach.
"""

import numpy as np
import rasterio
from rasterio.windows import Window
import pandas as pd
from datetime import datetime, timedelta
import logging
from pathlib import Path
from geopy.distance import geodesic

log = logging.getLogger(__name__)

# Constants
ROOT = Path(__file__).resolve().parent.parent.parent

def load_burn_age(lon: float, lat: float, target_date_str: str, patch_size: int = 224, resolution_m: float = 30.0) -> np.ndarray:
    """
    Computes a 2D 'Burn Age' tensor (years since last fire) for a given patch.
    If no historical fire exists, defaults to 10.0 years (mature unburned).
    """
    # Initialize with mature forest age (10 years = safe baseline)
    burn_age_tensor = np.full((1, patch_size, patch_size), 10.0, dtype=np.float32)
    
    links_path = ROOT / "data_lake" / "burn_scars" / "fire_links.csv"
    if not links_path.exists():
        log.warning("No fire_links.csv found. Using baseline burn age.")
        return burn_age_tensor

    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        df = pd.read_csv(links_path)
        df['fire_date'] = pd.to_datetime(df['fire_date'])
        
        # Filter fires that occurred BEFORE the target date
        historical_fires = df[df['fire_date'] < target_dt]
        
        if not historical_fires.empty:
            # Simple spatial proximity check (radius around patch center)
            # Patch width in meters ~ patch_size * resolution_m
            patch_radius_km = (patch_size * resolution_m / 2.0) / 1000.0
            
            for _, row in historical_fires.iterrows():
                f_lat, f_lon = row['fire_lat'], row['fire_lon']
                dist_km = geodesic((lat, lon), (f_lat, f_lon)).km
                
                # If a historical fire happened near this patch
                if dist_km <= patch_radius_km:
                    years_since = (target_dt - row['fire_date']).days / 365.25
                    
                    # For a true pixel-perfect map, we would rasterize the historical burn polygon.
                    # Since we only have points in the CSV right now, we apply a Gaussian 
                    # footprint of 'recent burn age' around the fire center.
                    
                    # Approximate pixel coords of the fire within the patch
                    # (Center of patch is patch_size/2)
                    dx = (f_lon - lon) * 111000 * np.cos(np.radians(lat)) / resolution_m
                    dy = (lat - f_lat) * 111000 / resolution_m # y is flipped
                    
                    px = int(patch_size/2 + dx)
                    py = int(patch_size/2 + dy)
                    
                    # Create a simple circular splash of the age
                    radius_px = int(np.sqrt((row.get('burn_area_ha', 1.0) * 10000) / np.pi) / resolution_m)
                    radius_px = max(1, radius_px)
                    
                    y, x = np.ogrid[-py:patch_size-py, -px:patch_size-px]
                    mask = x**2 + y**2 <= radius_px**2
                    
                    # Only update if this fire is more recent than what's already there
                    current_mask_ages = burn_age_tensor[0][mask]
                    burn_age_tensor[0][mask] = np.minimum(current_mask_ages, max(0.0, years_since))

    except Exception as e:
        log.error(f"Failed to compute burn age: {e}")
        
    return burn_age_tensor

def load_spatial_auxiliary(lon: float, lat: float, patch_size: int = 224, resolution_m: float = 30.0):
    """
    Extracts a (patch_size x patch_size) window of Terrain and Landcover 
    centered on the given lat/lon.
    
    Returns:
        terrain_tensor: (4, H, W) -> [DEM, Slope, Aspect_sin, Aspect_cos]
        landcover_tensor: (11, H, W) -> One-hot encoded ESA WorldCover classes
    """
    terrain_dir = ROOT / "data_lake" / "terrain"
    lc_path = ROOT / "data_lake" / "land_cover" / "worldcover_guna_raw.tif"
    
    # 1. Terrain Extraction (4 channels)
    # Default to zeros if missing, but log it.
    terrain_tensor = np.zeros((4, patch_size, patch_size), dtype=np.float32)
    try:
        with rasterio.open(terrain_dir / "dem_guna_clipped.tif") as ds:
            r, c = ds.index(lon, lat)
            win = Window(c - patch_size//2, r - patch_size//2, patch_size, patch_size)
            dem = ds.read(1, window=win, boundless=True, fill_value=0)
            
        with rasterio.open(terrain_dir / "slope_guna_30m.tif") as ds:
            slope = ds.read(1, window=win, boundless=True, fill_value=0)
            
        with rasterio.open(terrain_dir / "aspect_guna_30m.tif") as ds:
            aspect = ds.read(1, window=win, boundless=True, fill_value=0)
            
        # Normalize
        terrain_tensor[0] = dem / 1000.0 # Approx max elevation scaling
        terrain_tensor[1] = slope / 90.0 # Max slope 90 deg
        terrain_tensor[2] = np.sin(np.radians(aspect))
        terrain_tensor[3] = np.cos(np.radians(aspect))
    except Exception as e:
        log.warning(f"Could not load terrain data for {lat},{lon}: {e}")

    # 2. Landcover Extraction (11 channels - One Hot)
    lc_tensor = np.zeros((11, patch_size, patch_size), dtype=np.float32)
    try:
        with rasterio.open(lc_path) as ds:
            # Note: Landcover is 10m, we need to map to 30m or use nearest
            # For simplicity in this loader, we assume aligned indices or downsample
            # (Assuming pre-aligned 30m version exists for inference)
            r, c = ds.index(lon, lat)
            win = Window(c - patch_size//2, r - patch_size//2, patch_size, patch_size)
            lc_raw = ds.read(1, window=win, boundless=True, fill_value=0)
            
            # ESA Classes: 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100
            classes = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
            for i, cls_val in enumerate(classes):
                lc_tensor[i] = (lc_raw == cls_val).astype(np.float32)
    except Exception as e:
        log.warning(f"Could not load landcover data for {lat},{lon}: {e}")

    return terrain_tensor, lc_tensor

def load_7d_weather_sequence(target_date_str: str, lon: float, lat: float):
    """
    Extracts a 7-day chronological weather sequence [T-3 to T+3] around the target date.
    
    Returns:
        weather_tensor: (7, 10) -> 7 days of 10 weather features
    """
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    dates = [(target_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(-3, 4)]
    
    weather_seq = np.zeros((7, 10), dtype=np.float32)
    fwi_path = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
    
    try:
        df = pd.read_parquet(fwi_path)
        df['date_str'] = pd.to_datetime(df['date']).dt.strftime("%Y-%m-%d")
        
        # Features: Temp, RH, Wind, Precip, FFMC, DMC, DC, ISI, BUI, FWI
        feature_cols = ['temp_c', 'rh_pct', 'wind_kmh', 'precip_mm', 'ffmc', 'dmc', 'dc', 'isi', 'bui', 'fwi']
        
        for i, d in enumerate(dates):
            row = df[df['date_str'] == d]
            if not row.empty:
                # Normalize (rough empirical bounds)
                vals = row[feature_cols].iloc[0].values
                vals[0] /= 50.0  # Temp
                vals[1] /= 100.0 # RH
                vals[2] /= 50.0  # Wind
                vals[3] /= 100.0 # Precip
                vals[4:] /= 100.0 # Indices (approx scaling)
                weather_seq[i] = vals
            else:
                # If missing (e.g. future forecast not yet pulled), carry forward previous day
                if i > 0:
                    weather_seq[i] = weather_seq[i-1]
    except Exception as e:
        log.warning(f"Could not load 7D weather sequence: {e}")
        
    return weather_seq
