"""
VanAagni LLM Forensic Reporting Agent
=====================================
The "Cognitive Reporter" for Level 6 autonomy.
Consumes telemetry from the Carbon Ledger, Physics Engine, and Dispatch Agent
to generate a legally-defensible, professional After-Action Report (AAR).

This replaces manual bureaucratic paperwork for Forest Officers.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

log = logging.getLogger(__name__)

class ForensicReportingAgent:
    def __init__(self, division_name: str = "Guna"):
        self.division = division_name
        self.report_header = f"GOVERNMENT OF MADHYA PRADESH\nFOREST DEPARTMENT: {division_name.upper()} DIVISION\n"

    def draft_aar(
        self, 
        alert_data: Dict[str, Any], 
        audit_data: Dict[str, Any], 
        dispatch_logs: str
    ) -> str:
        """
        Assembles a multi-section forensic report using 'Reasoning Assembly'.
        In a full deployment, this payload is sent to Llama-3/GPT-4 for 
        nuanced narrative generation.
        """
        
        fire_date = alert_data.get("target_date", "Unknown")
        severity = alert_data.get("bulletin_severity", "Unknown")
        
        # 1. Executive Summary Assembly
        summary = f"INCIDENT REPORT: FA-{fire_date}-{self.division[:3].upper()}\n"
        summary += f"Date of Incident: {fire_date}\n"
        summary += f"Initial Classification: {severity} THREAT\n"
        summary += "-" * 40 + "\n"
        
        # 2. Forensic Physics Analysis
        metrics = audit_data.get("metrics", {})
        physics = f"SECTION I: SPATIO-TEMPORAL ANALYSIS\n"
        physics += f"- Actual Burnt Area: {metrics.get('actual_burn_ha', 0):.2f} Ha (Verified via Prithvi-EO-2.0)\n"
        physics += f"- Simulated Unconstrained Spread: {metrics.get('unconstrained_spread_ha', 0):.2f} Ha (Muhurta-2D PDE Engine)\n"
        physics += f"- Suppression Efficiency: {metrics.get('suppression_efficiency', 0)}%\n\n"
        
        # 3. Carbon & Economic Impact
        carbon = audit_data.get("carbon_ledger", {})
        economy = f"SECTION II: ENVIRONMENTAL & ECONOMIC IMPACT\n"
        economy += f"- Avoided Carbon Release: {carbon.get('co2_saved_avoided_tonnes', 0):,} Tonnes CO2e\n"
        economy += f"- Estimated Economic Value Protected: ${carbon.get('financial_offset_value_usd', 0):,} USD\n\n"
        
        # 4. Tactical Narrative (Ingesting Dispatch Logs)
        tactical = f"SECTION III: TACTICAL INTERVENTION CHRONOLOGY\n"
        tactical += "The AISignalCorps Agent issued the following directives during the engagement:\n"
        # We extract the English part of the log
        log_lines = dispatch_logs.split("=== HINDI ===")[0].replace("=== ENGLISH ===", "").strip()
        tactical += f"{log_lines}\n\n"
        
        # 5. Formal Legal Conclusion
        conclusion = f"SECTION IV: FINAL CONCLUSION\n"
        conclusion += f"Based on the delta between PIML (Physics-Informed ML) simulations and actual observed burn scars, "
        conclusion += f"it is concluded that the timely intervention of the forest beat teams, guided by VanAagni's "
        conclusion += f"prescriptive metrics, prevented an additional {metrics.get('avoided_burn_ha', 0):.2f} Ha of forest loss. "
        conclusion += f"The incident is now classified as CLOSED/SUCCESSFUL.\n"
        
        # Assemble Final Report
        full_report = self.report_header + "\n" + summary + "\n" + physics + economy + tactical + conclusion
        return full_report

def save_forensic_report(report_text: str, fire_date: str):
    """Saves the final report to the outputs directory."""
    out_dir = Path("outputs/forensic_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"AAR_{fire_date}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_text)
    return filename

if __name__ == "__main__":
    # Test Scenario
    agent = ForensicReportingAgent()
    
    # Mock data ingestion
    mock_alert = {"target_date": "2019-05-07", "bulletin_severity": "CRITICAL"}
    mock_audit = {
        "metrics": {"actual_burn_ha": 15.0, "unconstrained_spread_ha": 65.0, "avoided_burn_ha": 50.0, "suppression_efficiency": 76.9},
        "carbon_ledger": {"co2_saved_avoided_tonnes": 3200, "financial_offset_value_usd": 48000}
    }
    mock_dispatch = "=== ENGLISH ===\n🚨 TACTICAL DISPATCH ORDER: GOUMUKH BEAT 🚨\nACTION REQUIRED: Defensive / Evacuation\n..."
    
    report = agent.draft_aar(mock_alert, mock_audit, mock_dispatch)
    print(report)
    
    path = save_forensic_report(report, "2019-05-07")
    print(f"\nReport archived at: {path}")
