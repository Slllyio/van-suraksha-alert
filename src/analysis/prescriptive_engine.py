"""
Prescriptive AI Engine for VanAagni
===================================
Transitions the system from "Predictive" (what will happen) to "Prescriptive"
(what actions the Forest Department must take).

This engine fuses physics-based fire behavior metrics (Rate of Spread, 
Byram Intensity) with operational logistics to generate tactical 
suppression plans.
"""

import math
from typing import Dict, Any

# -------------------------------------------------------------------------
# Physics-Informed Wildfire Metrics
# -------------------------------------------------------------------------

def calculate_byram_intensity(
    ros_km_h: float, 
    fuel_load_tonnes_ha: float = 10.0, 
    heat_of_combustion_kj_kg: float = 18000.0
) -> float:
    """
    Calculates Byram's Fireline Intensity (I = H * w * r).
    Determines the difficulty of frontal attack.
    
    Parameters:
    -----------
    ros_km_h : Rate of spread in km/h
    fuel_load_tonnes_ha : Available fuel (default 10 t/ha for dry deciduous)
    heat_of_combustion_kj_kg : Default 18,000 kJ/kg for woody biomass
    
    Returns:
    --------
    Intensity in kW/m
    """
    # Convert ROS from km/h to m/s
    ros_m_s = (ros_km_h * 1000) / 3600.0
    
    # Convert fuel load from tonnes/ha to kg/m^2
    # 1 tonne = 1000 kg, 1 ha = 10,000 m^2 -> 1 t/ha = 0.1 kg/m^2
    w_kg_m2 = fuel_load_tonnes_ha * 0.1
    
    # I = H * w * r
    intensity_kw_m = heat_of_combustion_kj_kg * w_kg_m2 * ros_m_s
    return round(intensity_kw_m, 2)


def van_wagner_crown_fire(
    intensity_kw_m: float,
    cbh_m: float = 5.0,
    fmc_pct: float = 100.0,
) -> Dict[str, Any]:
    """
    Van Wagner (1977) crown fire initiation criteria.

    Determines if surface fire intensity is sufficient to ignite the canopy.

    Parameters:
    -----------
    intensity_kw_m : Byram fireline intensity (kW/m)
    cbh_m : Canopy base height in metres (default 5m for MP teak/sal)
    fmc_pct : Foliar moisture content % (default 100% for fire season)

    Returns:
    --------
    dict with crown fire assessment
    """
    # Critical intensity for crown fire initiation (Van Wagner 1977):
    # I_c = (0.01 * CBH * (460 + 25.9 * FMC))^1.5
    i_critical = (0.01 * cbh_m * (460 + 25.9 * fmc_pct)) ** 1.5

    is_crowning = intensity_kw_m >= i_critical
    crown_fraction = min(1.0, intensity_kw_m / i_critical) if i_critical > 0 else 0.0

    if crown_fraction < 0.5:
        fire_type = "SURFACE"
    elif crown_fraction < 1.0:
        fire_type = "INTERMITTENT_CROWN"
    else:
        fire_type = "ACTIVE_CROWN"

    return {
        "fire_type": fire_type,
        "is_crowning": is_crowning,
        "crown_fraction": round(crown_fraction, 3),
        "critical_intensity_kw_m": round(i_critical, 1),
        "cbh_m": cbh_m,
        "fmc_pct": fmc_pct,
    }


def generate_tactical_prescription(
    intensity_kw_m: float,
    ros_km_h: float,
    fwi_value: float,
    land_cover: str
) -> Dict[str, Any]:
    """
    Translates physical fire metrics into a prescriptive operational strategy.
    Incorporates Van Wagner crown fire criteria and standard suppression thresholds.
    """
    ros_m_min = (ros_km_h * 1000) / 60.0

    # Van Wagner crown fire assessment (for forested land cover)
    crown = van_wagner_crown_fire(intensity_kw_m)

    prescription = {
        "intensity_kw_m": intensity_kw_m,
        "ros_m_min": round(ros_m_min, 2),
        "fire_type": crown["fire_type"],
        "crown_fraction": crown["crown_fraction"],
        "critical_intensity_kw_m": crown["critical_intensity_kw_m"],
        "attack_mode": "",
        "required_equipment": [],
        "safety_warning": "",
        "evacuation_trigger": False,
    }

    # 1. Direct vs Indirect Attack based on Byram Intensity
    if intensity_kw_m < 346:
        prescription["attack_mode"] = "Direct Attack (Frontal)"
        prescription["required_equipment"] = ["Hand tools (Pulaski, McLeod)", "Knapsack sprayers"]
        prescription["safety_warning"] = "Low intensity ground fire. Safe for ground crews at the fire head."

    elif 346 <= intensity_kw_m < 1730:
        prescription["attack_mode"] = "Parallel Attack (Flanks)"
        prescription["required_equipment"] = ["Pump engines", "Hose lines", "Hand tools"]
        prescription["safety_warning"] = "Fire too intense for direct head attack. Attack flanks. Watch for spotting."

    elif 1730 <= intensity_kw_m < 3460:
        prescription["attack_mode"] = "Indirect Attack"
        prescription["required_equipment"] = ["Heavy machinery (Bulldozers/Tractors)", "Water tenders"]
        prescription["safety_warning"] = "Extreme heat and smoke. Ground crews must fall back to construct firelines ahead of the front."

    else:  # > 3460 kW/m
        prescription["attack_mode"] = "Defensive / Evacuation"
        prescription["required_equipment"] = ["Aerial support (if available)", "Backfiring equipment"]
        prescription["safety_warning"] = "EXTREME FIRE. High heat radiation prevents direct approach. Fall back to natural barriers."
        prescription["evacuation_trigger"] = True

    # 2. Crown fire escalation — Van Wagner override
    if crown["is_crowning"] and land_cover not in ("Cropland", "Grassland"):
        prescription["attack_mode"] = "Defensive / Evacuation"
        prescription["required_equipment"] = ["Aerial support (if available)", "Backfiring equipment"]
        prescription["safety_warning"] = (
            f"CROWN FIRE ({crown['fire_type'].replace('_', ' ')}). "
            f"Intensity {intensity_kw_m:.0f} kW/m exceeds Van Wagner threshold "
            f"({crown['critical_intensity_kw_m']:.0f} kW/m). "
            "DO NOT DEPLOY GROUND CREWS under the canopy."
        )
        prescription["evacuation_trigger"] = True

    # 3. Adjust for Rate of Spread & Weather (FWI)
    if ros_m_min > 100.0:  # NWCG PMS 410-1: fast-moving front = 100+ m/min (~6 km/h)
        prescription["safety_warning"] += " FAST MOVING FRONT! Establish escape routes."

    if fwi_value >= 38.0:  # Extreme Danger
        prescription["safety_warning"] += " EXTREME ATMOSPHERIC INSTABILITY (High FWI). Expect sudden wind shifts."

    # 4. Contextual Overrides
    if land_cover == "Cropland" and intensity_kw_m < 1730:
        prescription["attack_mode"] = "Containment"
        prescription["required_equipment"] = ["Tractors with disc harrows"]
        prescription["safety_warning"] = "Stubble fire. Ploughs needed to cut mineral earth breaks."

    return prescription


def draft_ai_dispatch_order(
    beat_name: str, 
    coords: tuple, 
    prescription: Dict[str, Any]
) -> str:
    """
    Generates a natural language dispatch order suitable for WhatsApp/Radio transmission.
    (This is the deterministic precursor to an LLM-Agent).
    """
    lat, lon = coords
    
    order = f"🚨 TACTICAL DISPATCH ORDER: {beat_name.upper()} BEAT 🚨\n"
    order += f"Location: {lat:.4f}N, {lon:.4f}E\n"
    order += f"Fire Behavior: Intensity {prescription['intensity_kw_m']} kW/m, Spread {prescription['ros_m_min']} m/min\n"
    order += f"--------------------------------------------------\n"
    order += f"ACTION REQUIRED: {prescription['attack_mode']}\n"
    order += f"EQUIPMENT TO MOBILIZE: {', '.join(prescription['required_equipment'])}\n"
    order += f"SAFETY DIRECTIVE: {prescription['safety_warning']}\n"
    
    if prescription['evacuation_trigger']:
        order += f"⚠️ CRITICAL: INITIATE CLEARANCE OF FORWARD AREAS IMMEDIATELY.\n"
        
    return order

# -------------------------------------------------------------------------
# Test execution
# -------------------------------------------------------------------------
if __name__ == "__main__":
    # Simulated scenario: Fast-moving forest fire during severe drought
    intensity = calculate_byram_intensity(ros_km_h=1.2, fuel_load_tonnes_ha=15.0)
    rx = generate_tactical_prescription(intensity, ros_km_h=1.2, fwi_value=42.0, land_cover="Tree cover")
    dispatch = draft_ai_dispatch_order("Goumukh", (24.123, 77.456), rx)
    
    print(dispatch)
