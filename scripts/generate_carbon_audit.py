"""
VanAagni Carbon Audit Tool
==========================
Generates an "Avoided Loss" audit for a historical fire event.
Compares actual burn area (observed) vs simulated spread (no intervention).
"""

import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# Project imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from src.analysis.carbon_ledger import CarbonLedger
from src.analysis.simulator import Muhurta2DSimulator
from src.analysis.micro_met import MicroMetEngine
from src.data.weather_ingest import get_gfs_wind_at_point

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("CarbonAudit")

# Paths
LINKS_CSV = ROOT / "data_lake" / "burn_scars" / "fire_links.csv"
TERRAIN_DIR = ROOT / "data_lake" / "terrain"
DEM_PATH = TERRAIN_DIR / "dem_guna_clipped.tif"
SLOPE_PATH = TERRAIN_DIR / "slope_guna_30m.tif"
ASPECT_PATH = TERRAIN_DIR / "aspect_guna_30m.tif"

def get_terrain_block(lat, lon, size=256):
    import rasterio
    if not DEM_PATH.exists():
        return None
    
    with rasterio.open(DEM_PATH) as ds_dem, \
         rasterio.open(SLOPE_PATH) as ds_slope, \
         rasterio.open(ASPECT_PATH) as ds_aspect:
        
        row, col = ds_dem.index(lon, lat)
        window = rasterio.windows.Window(col - size//2, row - size//2, size, size)
        
        dem = ds_dem.read(1, window=window, boundless=True, fill_value=0)
        slope = ds_slope.read(1, window=window, boundless=True, fill_value=0)
        aspect = ds_aspect.read(1, window=window, boundless=True, fill_value=0)
        transform = ds_dem.window_transform(window)
        
    return {'dem': dem, 'slope': slope, 'aspect': aspect, 'transform': transform}

def run_audit_for_event(fire_row: pd.Series):
    lat = fire_row['fire_lat']
    lon = fire_row['fire_lon']
    actual_ha = fire_row['burn_area_ha']
    fire_date = str(fire_row['fire_date'])[:10]
    
    log.info(f"Auditing Fire Event: {fire_date} at {lat}, {lon}")
    log.info(f"Actual Burn Area observed: {actual_ha:.2f} ha")
    
    # 1. Fetch historical weather
    try:
        wind_u, wind_v = get_gfs_wind_at_point(fire_date, lat, lon)
    except:
        wind_u, wind_v = 5.0, 2.0 # Fallback
        
    # 2. Get Terrain
    terrain = get_terrain_block(lat, lon)
    if not terrain:
        log.error("Terrain data missing. Cannot run simulation.")
        return
    
    # 3. Micro-Met
    met = MicroMetEngine()
    micro_u, micro_v = met.apply_terrain_forcing(wind_u, wind_v, terrain['dem'], terrain['slope'], terrain['aspect'])
    
    # 4. Simulation (No Intervention)
    simulator = Muhurta2DSimulator()
    grid_size = terrain['dem'].shape[0]
    y, x = np.ogrid[-grid_size//2:grid_size//2, -grid_size//2:grid_size//2]
    initial_phi = np.sqrt(x**2 + y**2) - 2
    
    # Simulate for 12 hours of unconstrained growth
    sim_time = 12 * 60 
    weather = {
        'wind_u': micro_u.mean(),
        'wind_v': micro_v.mean(),
        'fuel_anomaly': np.full_like(initial_phi, -1.5) # Extreme dry for audit
    }
    
    log.info(f"Simulating 12 hours of unconstrained spread...")
    final_phi = simulator.simulate_spread(initial_phi, terrain, weather, sim_time_minutes=sim_time, dt_minutes=10.0)
    
    # Calculate area (30m pixels)
    burned_px = (final_phi <= 0).sum()
    sim_ha = burned_px * 0.09 # 30x30m = 0.09 ha
    
    log.info(f"Simulated Unconstrained Area: {sim_ha:.2f} ha")
    
    # 5. Carbon Accounting
    ledger = CarbonLedger()
    report = ledger.perform_impact_audit(actual_scar_ha=actual_ha, simulated_no_action_ha=sim_ha)
    
    report["metadata"] = {
        "fire_date": fire_date,
        "location": [lat, lon],
        "audit_timestamp": datetime.now().isoformat()
    }
    
    # Save Report
    out_file = ROOT / "outputs" / f"carbon_audit_{fire_date}_{lat:.2f}.json"
    os.makedirs(ROOT / "outputs", exist_ok=True)
    with open(out_file, 'w') as f:
        json.dump(report, f, indent=4)
        
    print("\n====================================================")
    print("🌿 VANAAGNI CARBON AUDIT REPORT")
    print("====================================================")
    print(f"Fire Date:      {fire_date}")
    print(f"Reality:        {actual_ha:.2f} ha burned")
    print(f"No-Action Sim:  {sim_ha:.2f} ha predicted")
    print(f"Forest Saved:   {report['metrics']['avoided_burn_ha']:.2f} ha")
    print(f"CO2 Prevented:  {report['carbon_ledger']['co2_saved_avoided_tonnes']:,} tonnes")
    print(f"Economic Value: ${report['carbon_ledger']['financial_offset_value_usd']:,} USD")
    print("====================================================")
    print(f"Full report saved to: {out_file}")

if __name__ == "__main__":
    if not LINKS_CSV.exists():
        log.error("No fire links found. Generate them with scripts/link_fires_to_burnscars.py first.")
        # Simulating a row for demo
        demo_row = pd.Series({
            'fire_lat': 24.64,
            'fire_lon': 77.32,
            'burn_area_ha': 15.4,
            'fire_date': '2019-05-07'
        })
        run_audit_for_event(demo_row)
    else:
        df = pd.read_csv(LINKS_CSV)
        # Audit the largest high-confidence fire
        if 'confidence' in df.columns:
            high = df[df['confidence'] == 'HIGH']
            if not high.empty:
                idx = high['burn_area_ha'].idxmax()
                event = high.loc[idx]
                run_audit_for_event(event)
            else:
                run_audit_for_event(df.iloc[0])
        else:
            run_audit_for_event(df.iloc[0])
