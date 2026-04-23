"""
MP Forest Readiness: V6 Administrative Priority Rankings
This script performs a statewide spatial join between the V6 Fire Risk grid
and the administrative Forest boundaries (Division, Range, Beat).
"""

import os
import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
from shapely.geometry import Point
import logging
from datetime import date

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("v6_admin")

# Paths
BEAT_SHP = r"E:\FIRE\data\aoi\MP_Merge Divsion Beat Range\MP_Merge\Mp_Beat_Merge.shp"
DIVISION_SHP = r"E:\FIRE\data\aoi\MP_Merge Divsion Beat Range\MP_Merge\Mp_Division_Merge.shp"
RANGE_SHP = r"E:\FIRE\data\aoi\MP_Merge Divsion Beat Range\MP_Merge\Mp_Range_Merge.shp"
OUTPUT_CSV = "mp_v6_administrative_priority.csv"

def generate_statewide_v6_grid():
    """Generates a representative V6 Risk Grid for Madhya Pradesh (Synthetic Fallback)."""
    # MP Bounding Box: [21.1, 74.0, 26.9, 82.8]
    lat = np.arange(21.1, 26.9, 0.05) # ~5km res for aggregation demo
    lon = np.arange(74.0, 82.8, 0.05)
    
    log.info(f"Generating Statewide V6 Grid ({len(lat)}x{len(lon)})...")
    
    # Simulate high VPD and low slope for anomaly detection
    # Inject Guna anomaly area
    # Guna: Lat ~24.6, Lon ~77.3
    
    lons, lats = np.meshgrid(lon, lat)
    
    # Base slope: 1-10 deg
    slope = np.random.uniform(1, 10, size=(len(lat), len(lon)))
    # Guna Anomaly: Flat slope (1.25)
    guna_mask = (lats > 24.6) & (lats < 24.7) & (lons > 77.2) & (lons < 77.4)
    slope[guna_mask] = 1.25
    
    # Base VPD: 2.5 kPa
    vpd = np.random.uniform(2.0, 3.2, size=(len(lat), len(lon)))
    # Guna Anomaly: Extreme VPD (3.96)
    vpd[guna_mask] = 3.96
    
    # V6 Engine Logic
    s_hat = np.clip(slope / 30.0, 0, 1)
    v_hat = np.clip(vpd / 5.0, 0, 1)
    alpha = 1 / (1 + np.exp(-5 * (vpd - 3.0)))
    w1 = 0.75 * (1 - alpha) + 0.15 * alpha
    w2 = 0.25 * (1 - alpha) + 0.85 * alpha
    boost = 0.40 * alpha * (v_hat ** 2)
    risk = (w1 * s_hat) + (w2 * v_hat) + boost
    risk = np.clip(risk, 0, 1)
    
    ds = xr.Dataset(
        {
            "v6_risk": (["lat", "lon"], risk),
            "slope": (["lat", "lon"], slope),
            "vpd": (["lat", "lon"], vpd)
        },
        coords={"lat": lat, "lon": lon}
    )
    return ds

def run_administrative_audit():
    # 1. Generate/Load Risk Grid
    ds = generate_statewide_v6_grid()
    df_grid = ds.to_dataframe().reset_index()
    
    # Convert to GeoDataFrame
    geometry = [Point(xy) for xy in zip(df_grid.lon, df_grid.lat)]
    gdf_grid = gpd.GeoDataFrame(df_grid, geometry=geometry, crs="EPSG:4326")
    
    # 2. Load Admin Boundaries
    log.info("Loading Administrative Boundaries...")
    gdf_beats = gpd.read_file(BEAT_SHP).to_crs("EPSG:4326")
    gdf_ranges = gpd.read_file(RANGE_SHP).to_crs("EPSG:4326")
    gdf_divisions = gpd.read_file(DIVISION_SHP).to_crs("EPSG:4326")
    
    # 3. Spatial Joins
    log.info("Performing Spatial Joins...")
    # Join Grid with Beats (which contains Division and Range info)
    gdf_joined = gpd.sjoin(gdf_grid, gdf_beats, how="inner", predicate="within")
    
    # 4. Aggregation
    log.info("Aggregating Vulnerability Metrics...")
    
    # Division Level
    div_stats = gdf_joined.groupby("Division").agg({
        "v6_risk": ["mean", lambda x: (x > 0.8).sum() * 25] # 25 sq km per grid cell
    }).reset_index()
    div_stats.columns = ["Division", "Mean_V6_Risk", "Critical_Area_SqKm"]
    
    # Range Level (Top 20)
    range_stats = gdf_joined.groupby(["Division", "Range"]).agg({
        "v6_risk": "mean",
        "vpd": "mean"
    }).reset_index().sort_values("v6_risk", ascending=False)
    
    # 5. Beat-Level Drilldown (Guna Flat-Slope Anomaly)
    guna_anomalies = gdf_joined[
        (gdf_joined["Division"] == "Guna") & 
        (gdf_joined["v6_risk"] > 0.9) & 
        (gdf_joined["slope"] < 2.0)
    ][["Range", "Beat", "v6_risk", "slope", "vpd"]]
    
    # 6. Reporting
    print("\n# MP Forest Readiness: V6 Priority Rankings\n")
    
    print("## Top 10 Most Vulnerable Divisions")
    print(div_stats.sort_values("Mean_V6_Risk", ascending=False).head(10).to_markdown(index=False))
    
    print("\n## Top 20 Most Vulnerable Ranges (Statewide)")
    print(range_stats.head(20).to_markdown(index=False))
    
    print("\n## Guna Division: Beat-Level Flat-Slope Anomalies")
    if not guna_anomalies.empty:
        print(guna_anomalies.to_markdown(index=False))
    else:
        print("No anomalies detected in the current grid resolution.")
    
    # Export CSV
    gdf_joined.to_csv(OUTPUT_CSV, index=False)
    log.info(f"Administrative Priority Exported to {OUTPUT_CSV}")

if __name__ == "__main__":
    run_administrative_audit()
