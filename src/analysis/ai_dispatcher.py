"""
VanAagni AI Signal Corps — Tactical Dispatcher
================================================
Translates tactical fire dispatch orders to Hindi using Google Gemini.
Pushes dual-language orders via webhooks (WhatsApp/SMS/Radio).

Falls back to a basic dictionary replacement when LLM is unavailable.
"""

import os
import json
import logging
from typing import List, Optional

from src.analysis import gemini_service

log = logging.getLogger(__name__)


class AISignalCorps:
    """
    Agentic dispatcher that translates tactical orders using Gemini LLM
    and pushes them via webhooks.
    """

    def __init__(self):
        self.webhook_url = os.environ.get("VANAAGNI_DISPATCH_WEBHOOK", None)
        self._gemini_available = gemini_service.is_available()
        if self._gemini_available:
            log.info("AI Dispatcher: Gemini translation active")
        else:
            log.info("AI Dispatcher: Using rule-based translation fallback")

    def generate_evacuation_guidance(
        self,
        lat: float,
        lon: float,
        danger_polys: list,
    ) -> str:
        """Uses the LogisticsEngine to find a safe path out of the danger zone."""
        try:
            from src.analysis.logistics_engine import LogisticsEngine

            engine = LogisticsEngine(lat, lon, dist_km=10.0)
            result = engine.calculate_safe_evacuation(lat, lon, danger_polys)

            if "error" in result:
                return f"LOGISTICS WARNING: {result['error']}. Maintain shelter in place."

            status = (
                "CLEAN" if not result["is_compromised"] else "COMPROMISED (Smoke likely)"
            )
            msg = f"SAFE EVACUATION ROUTE FOUND ({result['distance_m']:.0f}m).\n"
            msg += f"Route Status: {status}\n"
            msg += f"Guidance: Exit via coordinates {result['route_geojson'][-1]}."
            return msg
        except Exception as e:
            return f"Logistics Engine unavailable: {e}"

    def translate_to_hindi(self, order: str) -> str:
        """Translate dispatch order to Hindi using Gemini LLM."""
        # Try Gemini first
        if self._gemini_available:
            result = gemini_service.translate_to_hindi(order)
            if result:
                return result

        # Fallback: rule-based replacement for core tactical terms
        return self._rule_based_translate(order)

    def _rule_based_translate(self, order: str) -> str:
        """Basic dictionary replacement for when LLM is unavailable."""
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
            "INITIATE CLEARANCE OF FORWARD AREAS IMMEDIATELY": (
                "तत्काल आगे के क्षेत्रों को खाली करना शुरू करें"
            ),
            "Defensive / Evacuation": "रक्षात्मक / निकासी",
            "Direct Attack": "सीधा हमला",
            "Indirect Attack": "परोक्ष हमला",
            "Hand tools": "हाथ के उपकरण",
            "Water tenders": "पानी के टैंकर",
            "Aerial support": "हवाई समर्थन",
            "CROWN FIRE BEHAVIOR": "शिखर अग्नि व्यवहार",
            "DO NOT DEPLOY GROUND CREWS": "जमीनी दल तैनात न करें",
            "FAST MOVING FRONT": "तेज गति का अग्नि मोर्चा",
        }

        hindi_order = order
        for eng, hin in translations.items():
            hindi_order = hindi_order.replace(eng, hin)

        return hindi_order

    def dispatch(self, tactical_order: str, severity: str) -> dict:
        """Sends dual-language dispatch order. Returns dispatch result."""
        hindi_order = self.translate_to_hindi(tactical_order)
        method = "gemini" if self._gemini_available else "rule_based"

        payload = {
            "type": "TACTICAL_ALERT",
            "severity": severity,
            "message_en": tactical_order,
            "message_hi": hindi_order,
            "translation_method": method,
        }

        # If a webhook is configured (Slack/Discord/WhatsApp gateway)
        if self.webhook_url:
            try:
                import requests

                requests.post(self.webhook_url, json=payload, timeout=5)
                log.info("Agentic Dispatch sent via webhook.")
            except Exception as e:
                log.error(f"Failed to send dispatch: {e}")

        # Always save locally for the Command Horizon dashboard
        dispatch_log_path = "outputs/last_dispatch.txt"
        os.makedirs("outputs", exist_ok=True)
        with open(dispatch_log_path, "w", encoding="utf-8") as f:
            f.write(f"=== ENGLISH === (translation: {method})\n")
            f.write(tactical_order + "\n\n")
            f.write("=== HINDI ===\n")
            f.write(hindi_order + "\n")
        log.info(f"Dispatch saved to {dispatch_log_path}")

        return payload


if __name__ == "__main__":
    corps = AISignalCorps()
    test_order = (
        "TACTICAL DISPATCH ORDER: GOUMUKH BEAT\n"
        "Location: 24.1230N, 77.4560E\n"
        "Fire Behavior: Intensity 9000.0 kW/m, Spread 20.0 m/min\n"
        "--------------------------------------------------\n"
        "ACTION REQUIRED: Defensive / Evacuation\n"
        "EQUIPMENT TO MOBILIZE: Aerial support, Water tenders\n"
        "SAFETY DIRECTIVE: CROWN FIRE BEHAVIOR. DO NOT DEPLOY GROUND CREWS.\n"
        "CRITICAL: INITIATE CLEARANCE OF FORWARD AREAS IMMEDIATELY.\n"
    )
    result = corps.dispatch(test_order, "CRITICAL")
    print("\n--- Hindi Translation ---")
    print(result["message_hi"])
    print(f"\n(Method: {result['translation_method']})")
