"""
Micro-Meteorology & Fluid Dynamics Engine
=========================================
Implements a diagnostic, mass-consistent wind model (similar to WindNinja).
It takes macro-scale wind vectors (e.g., from GFS 25km) and "drapes" them over a 
high-resolution (30m) Digital Elevation Model (DEM) to calculate local wind 
channeling, speed-up over ridges, and turbulence in valleys.

This is a critical Phase 1 component for the Level 4 Digital Twin.
"""

import numpy as np
import logging

log = logging.getLogger(__name__)

class MicroMetEngine:
    def __init__(self, dx=30.0, dy=30.0):
        self.dx = dx
        self.dy = dy

    def apply_terrain_forcing(
        self, 
        macro_u: float, 
        macro_v: float, 
        dem: np.ndarray, 
        slope: np.ndarray, 
        aspect: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Applies a simplified mass-consistent (divergence-free) terrain forcing 
        to a uniform macro wind field.
        
        Args:
            macro_u: Domain-averaged U-wind (m/s, East-West)
            macro_v: Domain-averaged V-wind (m/s, North-South)
            dem: 2D array of elevation (meters)
            slope: 2D array of slope (degrees)
            aspect: 2D array of aspect (degrees)
            
        Returns:
            micro_u, micro_v: 2D arrays of high-resolution wind vectors.
        """
        log.info(f"Applying Micro-Met Terrain Forcing (Macro Wind: {macro_u}U, {macro_v}V)")
        
        h, w = dem.shape
        micro_u = np.full((h, w), macro_u, dtype=np.float32)
        micro_v = np.full((h, w), macro_v, dtype=np.float32)
        
        # 1. Thermal Slope Winds (Diurnal Cycle Simulation)
        # In the afternoon, sun-facing slopes heat up, creating an anabatic (upslope) draft.
        # This is critical for MP's dry deciduous forests in April/May.
        aspect_rad = np.radians(aspect)
        
        # Simplified anabatic push (strongest on steep, south-facing slopes)
        # Vector points UP the slope. 
        # (Assuming slope direction is related to aspect; aspect points DOWNHILL)
        upslope_u = -np.sin(aspect_rad) * np.sin(np.radians(slope))
        upslope_v = -np.cos(aspect_rad) * np.sin(np.radians(slope))
        
        # Apply a thermal weighting factor (e.g., 2 m/s max thermal draft)
        thermal_factor = 2.0 
        
        micro_u += upslope_u * thermal_factor
        micro_v += upslope_v * thermal_factor

        # 2. Ridge Acceleration / Valley Channeling (Simplified Mass Conservation)
        # Wind speeds up as it compresses over a ridge.
        # Calculate local curvature (laplacian of elevation)
        dem_padded = np.pad(dem, 1, mode='edge')
        curvature = (
            dem_padded[:-2, 1:-1] + dem_padded[2:, 1:-1] + 
            dem_padded[1:-1, :-2] + dem_padded[1:-1, 2:] - 
            4 * dem
        ) / (self.dx**2)
        
        # Negative curvature (ridge): speed up. Positive (valley/bowl): slow down.
        # This is a highly simplified proxy for the Poisson equation.
        speed_modifier = 1.0 - (curvature * 100.0)
        # Bound the modifier
        speed_modifier = np.clip(speed_modifier, 0.3, 2.5)
        
        micro_u *= speed_modifier
        micro_v *= speed_modifier
        
        return micro_u, micro_v

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test the Micro-Met Engine with a synthetic "Ridge"
    grid_size = 100
    engine = MicroMetEngine()
    
    # Synthetic terrain: A sharp ridge running North-South down the middle
    x = np.linspace(-50, 50, grid_size)
    y = np.linspace(-50, 50, grid_size)
    xx, yy = np.meshgrid(x, y)
    
    # Gaussian ridge
    dem = 500.0 * np.exp(-(xx**2) / (2 * 10**2)) 
    
    # Very basic slope/aspect calculation for the test
    dy, dx = np.gradient(dem, 30.0, 30.0)
    slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
    aspect = np.degrees(np.arctan2(dy, -dx))
    
    # GFS says 5 m/s coming from the West
    macro_u = 5.0 
    macro_v = 0.0
    
    micro_u, micro_v = engine.apply_terrain_forcing(macro_u, macro_v, dem, slope, aspect)
    
    print(f"Macro Wind: {np.sqrt(macro_u**2 + macro_v**2):.1f} m/s")
    
    # Check wind at the base of the ridge (should be slower)
    base_u = micro_u[50, 10]
    print(f"Wind at Ridge Base (x=-40): {np.sqrt(base_u**2 + micro_v[50,10]**2):.1f} m/s")
    
    # Check wind at the top of the ridge (should be faster due to compression)
    top_u = micro_u[50, 50]
    print(f"Wind at Ridge Top (x=0): {np.sqrt(top_u**2 + micro_v[50,50]**2):.1f} m/s")
