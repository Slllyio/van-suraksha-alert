"""
Fire Physics & Thermodynamics Engine
====================================
Implements deterministic physics formulas for wildfire spread, intensity, 
and flame geometry calibrated for the Madhya Pradesh ecosystem.

Formulas:
- Rothermel Topographic Vector (Spread Rate adjustment)
- Byram Fireline Intensity (Energy release)
- Thomas's Law (Flame length calculation)
- Convective Indraft (Fire-induced wind)
"""

import numpy as np
from typing import Dict, Tuple

class FirePhysicsEngine:
    def __init__(self):
        # ── Fuel Constants for MP (Teak/Sal leaf litter) ──
        self.HEAT_OF_COMBUSTION = 18500.0  # kJ/kg
        self.FUEL_LOAD_DEFAULT = 0.8       # kg/m^2 (approx 8 tonnes/ha)
        self.ROTHERMEL_CONSTANT = 0.069    # a-parameter for deciduous litter

    def calculate_topographic_ros(
        self, 
        base_ros: np.ndarray, 
        slope: np.ndarray, 
        aspect: np.ndarray, 
        spread_direction: np.ndarray
    ) -> np.ndarray:
        """
        Adjusts the base Rate of Spread using the Rothermel Topographic Vector.
        
        Formula: R = R0 * exp(a * tan(theta) * cos(alpha - phi))
        theta: slope angle
        alpha: aspect (direction slope faces)
        phi: direction of fire spread
        """
        # Convert degrees to radians
        theta_rad = np.radians(slope)
        alpha_rad = np.radians(aspect)
        phi_rad = spread_direction # Already in radians from gradient
        
        # Rothermel adjustment factor
        # cos(alpha - phi) accounts for spread relative to the 'downhill' direction
        # Since aspect alpha usually points downhill, alpha - phi measures 
        # how much we are spreading 'with' the slope.
        topo_factor = np.exp(self.ROTHERMEL_CONSTANT * np.tan(theta_rad) * np.cos(alpha_rad - phi_rad))
        
        return base_ros * topo_factor

    def calculate_byram_intensity(self, ros_m_s: np.ndarray, fuel_load: float = None) -> np.ndarray:
        """
        Calculates Fireline Intensity (kW/m).
        I = H * w * r
        """
        w = fuel_load if fuel_load is not None else self.FUEL_LOAD_DEFAULT
        intensity = self.HEAT_OF_COMBUSTION * w * ros_m_s
        return intensity

    def calculate_flame_length(self, intensity: np.ndarray) -> np.ndarray:
        """
        Calculates physical flame length (meters) using Thomas's Law.
        L = 0.045 * I^0.46
        """
        # Ensure intensity is non-negative
        intensity_safe = np.maximum(0.0, intensity)
        return 0.045 * (intensity_safe ** 0.46)

    def calculate_convective_indraft(self, intensity: np.ndarray) -> np.ndarray:
        """
        Calculates fire-induced wind speed (m/s) pointing toward the fire.
        Vc = 0.5 * sqrt(I)
        """
        intensity_safe = np.maximum(0.0, intensity)
        return 0.5 * np.sqrt(intensity_safe)

if __name__ == "__main__":
    # Simple verification
    engine = FirePhysicsEngine()
    ros_test = 0.1 # 6 m/min -> 0.1 m/s
    
    intensity = engine.calculate_byram_intensity(np.array([ros_test]))
    flame_len = engine.calculate_flame_length(intensity)
    
    print(f"Intensity for {ros_test} m/s spread: {intensity[0]:.1f} kW/m")
    print(f"Predicted Flame Length: {flame_len[0]:.2f} meters")
