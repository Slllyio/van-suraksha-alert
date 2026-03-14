"""
Live Fuel Moisture & Dead Fuel Lag Engine
=========================================
Calculates 10-hour and 100-hour dead fuel moisture lags, and estimates live fuel 
moisture from NDVI phenology anomalies.

This provides the "Fuel Volatility" parameter for the Muhurta-2D CNN Simulator.
"""

import math
import numpy as np

def calculate_equilibrium_moisture_content(temp_c: float, rh_pct: float) -> float:
    """
    Calculates the Equilibrium Moisture Content (EMC) of dead forest fuels.
    Uses the standard USFS / Nelson model equations.
    
    temp_c: Temperature in Celsius
    rh_pct: Relative Humidity (0-100)
    Returns EMC as a percentage (e.g., 5.4%)
    """
    temp_f = (temp_c * 9/5) + 32
    rh = max(1.0, min(rh_pct, 99.0)) # Bound RH to prevent math errors
    
    if rh < 10:
        emc = 0.03229 + 0.281073 * rh - 0.000578 * rh * temp_f
    elif rh < 50:
        emc = 2.22749 + 0.160107 * rh - 0.014784 * temp_f
    else:
        emc = 21.0606 + 0.005565 * (rh ** 2) - 0.00035 * rh * temp_f - 0.483199 * rh
        
    return max(1.0, emc)

def update_dead_fuel_moisture(
    previous_moisture: float, 
    temp_c: float, 
    rh_pct: float, 
    rain_mm: float,
    lag_hours: int = 10,
    time_step_hours: float = 1.0
) -> float:
    """
    Updates the moisture content of dead fuels based on their time-lag class.
    10-hour fuels: 1/4" to 1" diameter (twigs, small branches).
    100-hour fuels: 1" to 3" diameter (dead branches).
    """
    emc = calculate_equilibrium_moisture_content(temp_c, rh_pct)
    
    # If rain occurred, apply a wetting step (simplified)
    if rain_mm > 0:
        # Very rough approximation: 1mm rain adds ~2% moisture to 10h fuels
        wetting_factor = 2.0 * (10 / lag_hours)
        moisture = previous_moisture + (rain_mm * wetting_factor)
        return min(moisture, 250.0) # Fiber saturation point
        
    # Drying/Equilibrating step
    # m_t = EMC + (m_0 - EMC) * exp(-t / lag)
    new_moisture = emc + (previous_moisture - emc) * math.exp(-time_step_hours / lag_hours)
    
    return max(1.0, new_moisture)

def compute_fuel_volatility(
    live_moisture_zscore: float, 
    moisture_10h: float, 
    moisture_100h: float
) -> float:
    """
    Fuses Live (NDVI-derived) and Dead (Weather-derived) moisture into a single 
    'Fuel Volatility' anomaly map for the CNN.
    
    Returns a normalized value where negative = dry/volatile, positive = wet/safe.
    """
    # Normalize dead fuels (assuming 5% is critically dry, 20% is damp)
    norm_10h = (moisture_10h - 12.0) / 5.0
    norm_100h = (moisture_100h - 15.0) / 5.0
    
    # Weighting: In MP's dry deciduous forests, 10h dead leaf litter is the primary driver
    # of surface fire spread, even if the canopy (live) is slightly green.
    volatility = (0.5 * norm_10h) + (0.3 * norm_100h) + (0.2 * live_moisture_zscore)
    
    return float(volatility)

if __name__ == "__main__":
    # Test the 10-hour lag logic over a hot, dry day
    m_10h = 15.0 # Starting moderately damp
    print(f"Initial 10h Moisture: {m_10h:.1f}%")
    for hour in range(1, 13): # 12 hours of 35C and 15% RH
        m_10h = update_dead_fuel_moisture(m_10h, temp_c=35, rh_pct=15, rain_mm=0, lag_hours=10)
        print(f"Hour {hour}: 10h Moisture = {m_10h:.1f}%")
        
    volatility = compute_fuel_volatility(live_moisture_zscore=-1.5, moisture_10h=m_10h, moisture_100h=10.0)
    print(f"Final Fuel Volatility Anomaly: {volatility:.2f}")
