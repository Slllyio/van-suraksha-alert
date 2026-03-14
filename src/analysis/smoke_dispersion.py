"""
Neural Smoke Dispersion (Gaussian Plume)
========================================
Implements a 2D Gaussian Plume Model to predict the surface concentration 
of PM2.5 smoke downwind from an active fire event.
"""

import numpy as np

def calculate_dispersion_coefficients(x_downwind: float, stability_class: str = 'D'):
    """
    Calculates Briggs dispersion coefficients (sigma_y, sigma_z) for open country.
    x_downwind: distance from fire in meters
    stability_class: Pasquill stability (A=Very Unstable, D=Neutral, F=Very Stable)
    """
    x = max(1.0, x_downwind)
    
    # Briggs coefficients for open country
    if stability_class == 'A':
        sy = 0.22 * x / np.sqrt(1 + 0.0001 * x)
        sz = 0.20 * x
    elif stability_class == 'B':
        sy = 0.16 * x / np.sqrt(1 + 0.0001 * x)
        sz = 0.12 * x
    elif stability_class == 'C':
        sy = 0.11 * x / np.sqrt(1 + 0.0001 * x)
        sz = 0.08 * x / np.sqrt(1 + 0.0002 * x)
    elif stability_class == 'D': # Neutral, common during high winds
        sy = 0.08 * x / np.sqrt(1 + 0.0001 * x)
        sz = 0.06 * x / np.sqrt(1 + 0.0015 * x)
    else: # E/F Stable (nighttime)
        sy = 0.04 * x / np.sqrt(1 + 0.0001 * x)
        sz = 0.016 * x / (1 + 0.0003 * x)
        
    return sy, max(1.0, sz)

def gaussian_plume_concentration(
    x: float, 
    y: float, 
    z: float, 
    Q: float, 
    u: float, 
    H: float, 
    stability_class: str = 'D'
) -> float:
    """
    Calculates the PM2.5 concentration (ug/m^3) at a specific point (x, y, z).
    
    x: downwind distance (m)
    y: crosswind distance (m)
    z: height above ground (m) - typically 2m for human breathing zone
    Q: Emission rate of PM2.5 (ug/s)
    u: Wind speed (m/s)
    H: Effective release height of smoke plume (m)
    """
    if x <= 0:
        return 0.0 # Upwind or at source
        
    sy, sz = calculate_dispersion_coefficients(x, stability_class)
    
    # Wind speed must be > 0
    u = max(0.5, u)
    
    term1 = Q / (2 * np.pi * u * sy * sz)
    term2 = np.exp(-(y**2) / (2 * sy**2))
    term3 = np.exp(-(z - H)**2 / (2 * sz**2)) + np.exp(-(z + H)**2 / (2 * sz**2))
    
    return term1 * term2 * term3

def estimate_emission_rate_from_frp(frp_mw: float) -> float:
    """
    Estimates PM2.5 emission rate (ug/s) from Fire Radiative Power (MW).
    Based on FRP to Biomass Consumption equations.
    """
    # Simplified empirical factor: 1 MW FRP ~ 0.02 kg/s of PM2.5
    pm25_kg_s = frp_mw * 0.02
    return pm25_kg_s * 1e9 # convert to ug/s

if __name__ == "__main__":
    # Test a 50 MW fire with 5 m/s wind
    Q = estimate_emission_rate_from_frp(50.0)
    wind = 5.0
    
    print(f"Smoke Dispersion Test (50 MW Fire, {wind} m/s Wind)")
    print("-" * 50)
    
    for dist_km in [1, 2, 5, 10]:
        x = dist_km * 1000
        conc = gaussian_plume_concentration(x, y=0, z=2, Q=Q, u=wind, H=50, stability_class='D')
        
        # AQI Context
        if conc > 250: severity = "LETHAL (AQI > 500)"
        elif conc > 100: severity = "HAZARDOUS"
        elif conc > 35: severity = "UNHEALTHY"
        else: severity = "MODERATE"
            
        print(f"  {dist_km:2d} km downwind: {conc:8.1f} ug/m3  => {severity}")
