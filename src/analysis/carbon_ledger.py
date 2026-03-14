"""
VanAagni Carbon Ledger & Avoided Loss Calculator
================================================
Quantifies the environmental and financial impact of fire suppression efforts.
By comparing the actual burn area (observed) with the unconstrained spread 
(simulated), we calculate the "Avoided Loss" in Carbon Sequestration.

Ecosystem: Dry Deciduous Forest (Madhya Pradesh)
"""

import numpy as np
import logging
from typing import Dict, Any
from pathlib import Path

log = logging.getLogger(__name__)

class CarbonLedger:
    def __init__(self):
        # ── Local Ecosystem Constants (Madhya Pradesh Dry Deciduous) ──
        # Reference: Forest Survey of India (FSI) & Local Carbon Density Studies
        self.BIOMASS_DENSITY_HA = 120.0  # Average tonnes of biomass per hectare
        self.CARBON_FRACTION = 0.47      # Biomass is ~47% carbon
        self.CO2_CONVERSION_FACTOR = 3.67 # C to CO2 conversion
        self.MARKET_PRICE_PER_TONNE_CO2 = 15.0 # USD (approx market rate for nature-based offsets)

    def calculate_co2_equivalence(self, area_ha: float) -> Dict[str, float]:
        """
        Converts a forest area into its carbon and financial equivalence.
        """
        biomass_tonnes = area_ha * self.BIOMASS_DENSITY_HA
        carbon_tonnes = biomass_tonnes * self.CARBON_FRACTION
        co2_tonnes = carbon_tonnes * self.CO2_CONVERSION_FACTOR
        financial_value = co2_tonnes * self.MARKET_PRICE_PER_TONNE_CO2
        
        return {
            "biomass_tonnes": round(biomass_tonnes, 2),
            "carbon_tonnes": round(carbon_tonnes, 2),
            "co2_tonnes": round(co2_tonnes, 2),
            "usd_value": round(financial_value, 2)
        }

    def perform_impact_audit(
        self, 
        actual_scar_ha: float, 
        simulated_no_action_ha: float
    ) -> Dict[str, Any]:
        """
        Calculates the 'Avoided Loss' by comparing reality vs no-intervention.
        """
        avoided_area_ha = max(0.0, simulated_no_action_ha - actual_scar_ha)
        
        actual_impact = self.calculate_co2_equivalence(actual_scar_ha)
        potential_impact = self.calculate_co2_equivalence(simulated_no_action_ha)
        avoided_impact = self.calculate_co2_equivalence(avoided_area_ha)
        
        report = {
            "metrics": {
                "actual_burn_ha": actual_scar_ha,
                "unconstrained_spread_ha": simulated_no_action_ha,
                "avoided_burn_ha": avoided_area_ha,
                "suppression_efficiency": round((avoided_area_ha / simulated_no_action_ha) * 100, 1) if simulated_no_action_ha > 0 else 0
            },
            "carbon_ledger": {
                "co2_emitted_actual_tonnes": actual_impact["co2_tonnes"],
                "co2_saved_avoided_tonnes": avoided_impact["co2_tonnes"],
                "financial_offset_value_usd": avoided_impact["usd_value"]
            },
            "narrative": f"Suppression efforts saved {avoided_area_ha:.1f} hectares of forest canopy, "
                         f"preventing the release of {avoided_impact['co2_tonnes']:,} tonnes of CO2."
        }
        
        return report

def generate_carbon_audit_report(report: Dict[str, Any], output_path: str):
    """
    Saves a formal audit report to the disk.
    """
    import json
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)
    log.info(f"Carbon Audit Report saved to {output_path}")

if __name__ == "__main__":
    # Test Scenario: 
    # A fire occurred in Guna. 
    # Prithvi-EO detected an actual burn scar of 12 hectares.
    # Muhurta-2D simulated that without intervention, it would have consumed 45 hectares.
    
    ledger = CarbonLedger()
    audit = ledger.perform_impact_audit(actual_scar_ha=12.0, simulated_no_action_ha=45.0)
    
    print("\n--- 🌿 VanAagni Carbon Audit Summary ---")
    print(audit["narrative"])
    print(f"Avoided Burn Area: {audit['metrics']['avoided_burn_ha']} ha")
    print(f"Estimated Carbon Value Saved: ${audit['carbon_ledger']['financial_offset_value_usd']:,} USD")
    print("-" * 40)
