import os
import requests
import json
import logging
from typing import List, Optional
from shapely.geometry import Polygon

log = logging.getLogger(__name__)

class AISignalCorps:
    """
    Agentic dispatcher that translates tactical orders and pushes them
    via webhooks (simulating WhatsApp/SMS/Radio).
    """

    def __init__(self):
        self.webhook_url = os.environ.get("VANAAGNI_DISPATCH_WEBHOOK", None)

    def generate_evacuation_guidance(
        self, 
        lat: float, 
        lon: float, 
        danger_polys: List[Polygon]
    ) -> str:
        """
        Uses the LogisticsEngine to find a safe path out of the danger zone.
        """
        try:
            from src.analysis.logistics_engine import LogisticsEngine
            engine = LogisticsEngine(lat, lon, dist_km=10.0)
            result = engine.calculate_safe_evacuation(lat, lon, danger_polys)
            
            if "error" in result:
                return f"⚠️ LOGISTICS WARNING: {result['error']}. Maintain shelter in place."
            
            status = "CLEAN" if not result['is_compromised'] else "COMPROMISED (Smoke likely)"
            msg = f"🗺️ SAFE EVACUATION ROUTE FOUND ({result['distance_m']:.0f}m).\n"
            msg += f"Route Status: {status}\n"
            msg += f"Guidance: Exit via coordinates {result['route_geojson'][-1]}."
            return msg
        except Exception as e:
            return f"Logistics Engine unavailable: {e}"

    def translate_to_hindi(self, order: str) -> str:
        """
        Simulated translation using a local small language model (LLM).
        In a full deployment, this would ping a local Llama-3 instance.
        Here we use rule-based replacement for core tactical keywords.
        """
        # A rudimentary dictionary replacement to simulate the LLM's role
        # in a constrained environment without external API dependencies.
        translations = {
            "TACTICAL DISPATCH ORDER": "रणनीतिक प्रेषण आदेश (TDO)",
            "Location": "स्थान",
            "Fire Behavior": "अग्नि व्यवहार",
            "Intensity": "तीव्रता",
            "Spread": "फैलाव",
            "ACTION REQUIRED": "आवश्यक कार्रवाई",
            "EQUIPMENT TO MOBILIZE": "उपकरण जुटाना",
            "SAFETY DIRECTIVE": "सुरक्षा निर्देश",
            "CRITICAL": "महत्वपूर्ण",
            "INITIATE CLEARANCE OF FORWARD AREAS IMMEDIATELY": "तत्काल आगे के क्षेत्रों को खाली करना शुरू करें",
            "Defensive / Evacuation": "रक्षात्मक / निकासी",
            "Direct Attack": "सीधा हमला",
            "Indirect Attack": "परोक्ष हमला",
            "Hand tools": "हाथ के उपकरण",
            "Water tenders": "पानी के टैंकर",
            "Aerial support": "हवाई समर्थन",
        }

        hindi_order = order
        for eng, hin in translations.items():
            hindi_order = hindi_order.replace(eng, hin)
            
        return hindi_order

    def dispatch(self, tactical_order: str, severity: str):
        """
        Sends the dual-language dispatch order.
        """
        hindi_order = self.translate_to_hindi(tactical_order)
        
        payload = {
            "type": "TACTICAL_ALERT",
            "severity": severity,
            "message_en": tactical_order,
            "message_hi": hindi_order
        }

        # If a webhook is configured (e.g., Slack/Discord/WhatsApp gateway)
        if self.webhook_url:
            try:
                requests.post(self.webhook_url, json=payload, timeout=5)
                log.info("Agentic Dispatch sent successfully.")
            except Exception as e:
                log.error(f"Failed to send dispatch: {e}")
        else:
            # Fallback to local logging for the Command Horizon dashboard
            dispatch_log_path = "outputs/last_dispatch.txt"
            os.makedirs("outputs", exist_ok=True)
            with open(dispatch_log_path, "w", encoding="utf-8") as f:
                f.write("=== ENGLISH ===\n")
                f.write(tactical_order + "\n\n")
                f.write("=== HINDI ===\n")
                f.write(hindi_order + "\n")
            log.info(f"Agentic Dispatch saved locally to {dispatch_log_path}")

# Example Usage
if __name__ == "__main__":
    corps = AISignalCorps()
    
    latest_path = "data_lake/alerts/latest_alert.json"
    if os.path.exists(latest_path):
        with open(latest_path, "r", encoding="utf-8") as f:
            alert = json.load(f)
            
        for f_alert in alert.get("fires", []):
            t_order = f_alert.get("tactical_order")
            sev = f_alert.get("severity")
            if t_order:
                print(f"\n--- Dispatching for {sev} fire ---")
                corps.dispatch(t_order, sev)
                # Show the hindi order in the console for the test
                print(corps.translate_to_hindi(t_order))
    else:
        # Fallback to demo
        test_order = (
            "🚨 TACTICAL DISPATCH ORDER: GOUMUKH BEAT 🚨\n"
            "Location: 24.1230N, 77.4560E\n"
            "Fire Behavior: Intensity 9000.0 kW/m, Spread 20.0 m/min\n"
            "--------------------------------------------------\n"
            "ACTION REQUIRED: Defensive / Evacuation\n"
            "EQUIPMENT TO MOBILIZE: Aerial support, Water tenders\n"
            "SAFETY DIRECTIVE: CROWN FIRE BEHAVIOR. DO NOT DEPLOY GROUND CREWS.\n"
            "⚠️ CRITICAL: INITIATE CLEARANCE OF FORWARD AREAS IMMEDIATELY.\n"
        )
        corps.dispatch(test_order, "CRITICAL")
