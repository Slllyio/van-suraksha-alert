"""
VanAagni SAR-Sight (Cloud Penetration Engine)
=============================================
Uses Sentinel-1 Synthetic Aperture Radar (SAR) backscatter to estimate 
soil and fuel moisture when optical sensors (HLS/Sentinel-2) are 
blocked by clouds or smoke.

Radar signals (C-band) penetrate clouds. VH and VV backscatter intensities
are sensitive to moisture-driven changes in the dielectric constant of 
vegetation and soil.
"""

import numpy as np
import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

class SARSightEngine:
    def __init__(self):
        # ── Local Calibration for MP Dry Deciduous ──
        # These dB thresholds are empirical proxies for Guna's soil/litter moisture.
        self.VH_MIN_DB = -25.0  # Extremely dry
        self.VH_MAX_DB = -12.0  # Saturated/Flood
        
    def estimate_moisture_proxy(self, vv_db: float, vh_db: float) -> Dict[str, float]:
        """
        Calculates a moisture proxy based on VV and VH backscatter.
        Generally, higher backscatter (less negative dB) = higher moisture.
        
        RVI (Radar Vegetation Index) proxy for moisture/biomass:
        4 * vh / (vv + vh)  [using linear units]
        """
        # Convert dB to Linear Power
        vv_lin = 10**(vv_db / 10.0)
        vh_lin = 10**(vh_db / 10.0)
        
        # 1. Radar Vegetation Index (RVI) - proxy for moisture/volume
        rvi = (4.0 * vh_lin) / (vv_lin + vh_lin)
        
        # 2. Moisture Score (0.0 to 1.0)
        # Normalized VH is a robust proxy for surface dielectric (moisture)
        moisture_score = (vh_db - self.VH_MIN_DB) / (self.VH_MAX_DB - self.VH_MIN_DB)
        moisture_score = np.clip(moisture_score, 0.0, 1.0)
        
        return {
            "radar_moisture_index": round(float(moisture_score), 3),
            "rvi": round(float(rvi), 3),
            "is_volatile": moisture_score < 0.2, # < -22dB VH usually means bone-dry
            "penetration_depth_mm": round(50 * (1 - moisture_score), 1) # Approximation
        }

    def detect_structural_loss(self, vh_t0: float, vh_t1: float) -> bool:
        """
        Detects if canopy was physically removed (structural change).
        Radar is immune to leaf-drop phenology.
        """
        # A drop of > 2.0 dB in VH usually indicates stem removal
        return (vh_t0 - vh_t1) >= 2.0

if __name__ == "__main__":
    # Test Scenario
    engine = SARSightEngine()
    
    # Bone dry soil (Common in Guna in May)
    dry = engine.estimate_moisture_proxy(vv_db=-15.0, vh_db=-23.0)
    print(f"DRY SCENARIO: Moisture Index={dry['radar_moisture_index']} | Volatile? {dry['is_volatile']}")
    
    # Post-monsoon moist soil
    wet = engine.estimate_moisture_proxy(vv_db=-10.0, vh_db=-14.0)
    print(f"WET SCENARIO: Moisture Index={wet['radar_moisture_index']} | Volatile? {wet['is_volatile']}")
