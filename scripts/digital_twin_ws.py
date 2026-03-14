import json
import logging
import asyncio
import numpy as np
import torch
import rasterio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List

# Project imports
ROOT = Path(__file__).resolve().parent.parent
import sys
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from src.analysis.simulator import Muhurta2DSimulator
from src.analysis.micro_met import MicroMetEngine
from src.analysis.fire_dynamics import FireEventTracker
from src.data.weather_ingest import get_gfs_wind_at_point
from src.analysis.fire_physics import FirePhysicsEngine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("DigitalTwinWS")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Load Terrain Rasters for Guna (30m)
TERRAIN_DIR = ROOT / "data_lake" / "terrain"
DEM_PATH = TERRAIN_DIR / "dem_guna_clipped.tif"
SLOPE_PATH = TERRAIN_DIR / "slope_guna_30m.tif"
ASPECT_PATH = TERRAIN_DIR / "aspect_guna_30m.tif"

def get_local_terrain_block(lat, lon, size=128):
    """Extracts a local NxN block of terrain centered at lat/lon."""
    if not DEM_PATH.exists():
        log.warning("Terrain data not found. Using flat fallback.")
        return {
            'dem': np.zeros((size, size)),
            'slope': np.zeros((size, size)),
            'aspect': np.zeros((size, size)),
            'transform': None
        }
    
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

@app.websocket("/ws/simulate")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    log.info("Client connected to Digital Twin Simulation")
    
    try:
        # 1. Initialize Simulator
        # Use trained weights if available
        ckpt = ROOT / "models" / "muhurta" / "ros_unet_v1.pth"
        simulator = Muhurta2DSimulator(model_path=str(ckpt) if ckpt.exists() else None)
        met_engine = MicroMetEngine()
        
        while True:
            # 2. Wait for simulation parameters
            data = await websocket.receive_text()
            params = json.loads(data)
            
            lat = params.get('lat', 24.640)
            lon = params.get('lon', 77.320)
            sim_date = params.get('date') # ISO date string e.g. "2019-04-14"
            
            # Use real GFS wind if date is provided, else use manual/default
            if sim_date:
                log.info(f"Fetching real GFS wind for {sim_date} at {lat}, {lon}")
                wind_u, wind_v = get_gfs_wind_at_point(sim_date, lat, lon)
                log.info(f"Real GFS Wind: {wind_u:.2f}U, {wind_v:.2f}V")
            else:
                wind_u = params.get('wind_u', 5.0)
                wind_v = params.get('wind_v', 2.0)
            
            log.info(f"Triggering Real-Time Simulation at {lat}, {lon}")
            
            # 3. Get Terrain Context
            terrain_data = get_local_terrain_block(lat, lon)
            transform = terrain_data['transform']
            grid_size = terrain_data['dem'].shape[0]
            
            # 4. Handle Human Interventions (Firelines & Backfires)
            interventions = params.get('interventions', [])
            
            # Rasterize firelines (ROS = 0)
            fireline_mask = np.zeros((grid_size, grid_size), dtype=np.uint8)
            # Rasterize backfires (Phi = -1)
            backfire_mask = np.zeros((grid_size, grid_size), dtype=np.uint8)
            
            from rasterio import features
            for inter in interventions:
                geom = inter.get('geometry')
                itype = inter.get('type') # 'FIRELINE' or 'BACKFIRE'
                if not geom: continue
                
                if itype == 'FIRELINE':
                    # Value 1 means non-burnable
                    features.rasterize([geom], out=fireline_mask, transform=transform, default_value=1)
                elif itype == 'BACKFIRE':
                    # Value 1 means ignited
                    features.rasterize([geom], out=backfire_mask, transform=transform, default_value=1)

            # 5. Generate Micro-Met Wind Field
            micro_u, micro_v = met_engine.apply_terrain_forcing(
                wind_u, wind_v, 
                terrain_data['dem'], terrain_data['slope'], terrain_data['aspect']
            )
            
            # 6. Initialize Fire (Small circle at center of block)
            y, x = np.ogrid[-grid_size//2:grid_size//2, -grid_size//2:grid_size//2]
            initial_phi = np.sqrt(x**2 + y**2) - 2 # 2 pixel radius
            
            # Apply initial backfires to phi
            if backfire_mask.any():
                initial_phi[backfire_mask == 1] = -1.0
                
            phi_current = initial_phi.copy()
            
            # 7. Run Iterative Simulation Loop & Stream Coordinates
            for t in range(0, 60, 10): # 1 hour total
                weather = {
                    'wind_u': micro_u.mean(),
                    'wind_v': micro_v.mean(),
                    'fuel_anomaly': np.full_like(phi_current, -1.0) # Dry
                }
                
                # ── Physics-Informed Iteration ──
                # Returns updated phi and the spatial ROS field
                phi_next, ros_field = simulator.simulate_spread(
                    phi_current, terrain_data, weather, sim_time_minutes=10, dt_minutes=2.0
                )
                
                # Calculate Physics Metrics for the current front
                # Convert m/min to m/s for physics engine
                ros_ms = ros_field / 60.0
                intensity_field = simulator.physics.calculate_byram_intensity(ros_ms)
                flame_height_field = simulator.physics.calculate_flame_length(intensity_field)
                
                # Extract mean values for the burning front (where phi ~ 0)
                # For streaming, we send the peak values encountered on the front
                active_mask = (phi_current <= 0).astype(bool)
                peak_intensity = float(np.max(intensity_field[active_mask])) if active_mask.any() else 0.0
                peak_flame_height = float(np.max(flame_height_field[active_mask])) if active_mask.any() else 0.0
                
                phi_current = phi_next
                
                # Apply backfires mid-simulation
                if backfire_mask.any():
                    phi_current[backfire_mask == 1] = -1.0
                
                # ── Convert Phi to GeoJSON Polygon Coordinates ──
                from rasterio import features
                mask = (phi_current <= 0).astype(np.uint8)
                polys = []
                for geom, val in features.shapes(mask, mask=mask, transform=transform):
                    coords = geom['coordinates'][0]
                    polys.append(coords)
                
                # Stream coordinates and high-fidelity physics to frontend
                await websocket.send_json({
                    "time_elapsed": t + 10,
                    "polygons": polys,
                    "intensity_kw_m": peak_intensity,
                    "flame_height_m": peak_flame_height,
                    "ros_m_min": float(np.max(ros_field[active_mask])) if active_mask.any() else 0.0
                })
                
                await asyncio.sleep(0.5) 
                
            log.info("Simulation segment completed.")

    except WebSocketDisconnect:
        log.info("Client disconnected")
    except Exception as e:
        log.error(f"Simulation Error: {e}")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
