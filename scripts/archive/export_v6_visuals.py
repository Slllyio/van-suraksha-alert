import os
import json
import logging
import pandas as pd
import numpy as np
import xarray as xr
import geopandas as gpd
from shapely.geometry import Point
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def export_v6_corrections(ds_results: xr.Dataset, divisions_shp: str, output_geojson: str):
    """
    Filters, groups by division, and exports V6 corrections to GeoJSON.
    """
    log.info("Starting V6 Correction Export...")
    
    # 1. Convert Xarray to Dataframe
    df = ds_results.to_dataframe().reset_index()
    
    # 2. Reconstruct Old_Risk (Static Baseline)
    # Using the same normalization/weights as the audit
    df['old_risk'] = (0.75 * np.clip(df['slope']/30.0, 0, 1)) + (0.25 * np.clip(df['vpd']/5.0, 0, 1))
    
    # 3. Apply the CRITICAL FILTER
    # Old_Risk < 0.3 (False Negative or Weak Signal)
    # V6_Risk > 0.8 (Critical heatwave ignition detected by non-linear logic)
    corrections = df[(df['old_risk'] < 0.3) & (df['v6_risk'] > 0.8)].copy()
    
    if corrections.empty:
        log.warning("No anomalies found matching the filter (Old < 0.3, V6 > 0.8). Check simulation data.")
        return
    
    log.info(f"Found {len(corrections)} corrected grid-cells.")

    # 4. Geospatial Processing (Spatial Join with Divisions)
    log.info("Performing spatial join with Forest Divisions...")
    gdf_pts = gpd.GeoDataFrame(
        corrections, 
        geometry=gpd.points_from_xy(corrections.lon, corrections.lat),
        crs="EPSG:4326"
    )
    
    try:
        divisions = gpd.read_file(divisions_shp)
        # Ensure CRS match
        if divisions.crs != "EPSG:4326":
            divisions = divisions.to_crs("EPSG:4326")
            
        # Join points to polygons
        joined = gpd.sjoin(gdf_pts, divisions, how="left", predicate="within")
        
        # Extract the division name from the 'Division' column
        if 'Division' in joined.columns:
            joined = joined[['time', 'lat', 'lon', 'v6_risk', 'old_risk', 'vpd', 'Division', 'geometry']]
            joined = joined.rename(columns={'Division': 'forest_division'})
        else:
            log.warning("Column 'Division' not found in joined data.")
            joined = joined[['time', 'lat', 'lon', 'v6_risk', 'old_risk', 'vpd', 'geometry']]
        
    except Exception as e:
        log.error(f"Spatial join failed: {e}")
        # Fallback to coordinate-only GeoJSON
        joined = gdf_pts[['time', 'lat', 'lon', 'v6_risk', 'old_risk', 'vpd', 'geometry']].copy()

    # 5. Export to GeoJSON
    # Simplify time for JSON compatibility
    joined.loc[:, 'time'] = joined['time'].astype(str)
    
    log.info(f"Saving to {output_geojson}...")
    joined.to_file(output_geojson, driver='GeoJSON')
    log.info("Export Complete.")

if __name__ == "__main__":
    # This logic assumes the simulation results are available in memory or re-run
    # For framework demonstration, we re-use the main logic from the simulation script
    from scripts.mp_statewide_v6_simulation import run_simulation, fetch_terrain_pystac
    
    lat_min, lon_min, lat_max, lon_max = 21.1, 74.0, 26.9, 82.8
    bbox_stac = [lon_min, lat_min, lon_max, lat_max] 
    
    # 1. Re-generate or Load Results
    ds_terrain = fetch_terrain_pystac(bbox_stac, resolution=0.1) # Coarser for speed
    
    time_steps = pd.date_range("2026-03-15", "2026-04-07", freq="D")
    # Simulate the April Jump
    temps = np.concatenate([np.linspace(298, 305, 17), np.linspace(312, 318, 7)]) 
    t2m_3d = np.broadcast_to(temps[:, None, None], (len(time_steps), len(ds_terrain.lat), len(ds_terrain.lon)))
    d2m_3d = np.random.uniform(280, 282, size=(len(time_steps), len(ds_terrain.lat), len(ds_terrain.lon)))
    
    ds_weather = xr.Dataset(
        {"t2m": (["time", "lat", "lon"], t2m_3d), "d2m": (["time", "lat", "lon"], d2m_3d)},
        coords={"time": time_steps, "lat": ds_terrain.lat, "lon": ds_terrain.lon}
    )
    
    ds_results = run_simulation(ds_weather, ds_terrain)
    
    # 2. Run Export
    shp_path = "data/aoi/MP_Merge Divsion Beat Range/MP_Merge/Mp_Division_Merge.shp"
    export_v6_corrections(ds_results, shp_path, "v6_heatwave_corrections.geojson")
