"""
VanAagni VLM Automated Auditor
==============================
Vision-Language Model agent for autonomous auditing of fire alerts.
Analyzes satellite chips (RGB/Delta) to distinguish between real forest fires
and false positives (agricultural burns, cloud artifacts, phenological noise).

Uses Google Gemini Vision API for actual image analysis.
Falls back to metadata-based heuristics when API key is unavailable.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from src.analysis import gemini_service

log = logging.getLogger(__name__)


class VLMAuditor:
    def __init__(self):
        self._gemini_available = gemini_service.is_available()
        if self._gemini_available:
            log.info("VLM Auditor: Gemini Vision API active")
        else:
            log.warning("VLM Auditor: Gemini unavailable, using metadata heuristics")

    def audit_alert(
        self,
        image_path: Path,
        alert_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyzes alert chip image + metadata to determine fire validity.
        Returns: {"verdict": str, "confidence": float, "reasoning": str, "method": str}
        """
        frp = alert_metadata.get("frp_mw", 0)
        severity = alert_metadata.get("severity", "MODERATE")
        land_cover = alert_metadata.get("land_cover", "unknown")

        # Try Gemini Vision if image exists and API is available
        if self._gemini_available and image_path.exists():
            result = self._audit_with_gemini(image_path, alert_metadata)
            if result:
                result["method"] = "gemini_vision"
                return result

        # Fallback: metadata-based heuristic (transparent about being rule-based)
        return self._audit_with_heuristics(frp, land_cover, severity)

    def _audit_with_gemini(
        self, image_path: Path, meta: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Real VLM analysis using Gemini Vision API."""
        prompt = f"""You are a Senior Forest Forensic Officer specializing in satellite remote sensing.
Analyze this satellite image of a fire alert in Guna Division, Madhya Pradesh, India.

Alert Metadata:
- Severity: {meta.get('severity', 'UNKNOWN')}
- FRP (Fire Radiative Power): {meta.get('frp_mw', 0)} MW
- Land Cover: {meta.get('land_cover', 'unknown')}
- Coordinates: {meta.get('lat', 0):.4f}N, {meta.get('lon', 0):.4f}E

Determine if this is:
1. VALID forest fire — genuine wildfire in forested/vegetated area
2. FALSE_POSITIVE — agricultural stubble burn, cloud/shadow artifact, or sensor noise
3. AMBIGUOUS — cannot determine with confidence

Return a JSON object:
{{
    "verdict": "VALID" or "FALSE_POSITIVE" or "AMBIGUOUS",
    "confidence": 0.0 to 1.0,
    "reasoning": "2-3 sentence explanation of visual evidence"
}}"""

        result = gemini_service.analyze_image_json(image_path, prompt)
        if result and "verdict" in result:
            return result
        return None

    def _audit_with_heuristics(
        self, frp: float, land_cover: str, severity: str
    ) -> Dict[str, Any]:
        """
        Rule-based fallback using fire science thresholds.
        Transparently labeled as heuristic, not AI.

        Decision tree:
          1. FRP >= 30 MW → VALID regardless of land cover (wildfire-level energy)
          2. Cropland + FRP < 10 → FALSE_POSITIVE (agricultural burn)
          3. Forest/tree + FRP >= 10 → VALID
          4. Forest/tree + FRP < 10 → AMBIGUOUS
          5. Unknown land cover + FRP 10-30 → severity-informed decision
          6. Default → AMBIGUOUS
        """
        lc = land_cover.lower() if land_cover else "unknown"

        # Rule 1: Very high FRP is a wildfire regardless of land cover.
        # FRP >= 30 MW far exceeds any agricultural or controlled burn.
        # In Guna Division, typical stubble burns produce < 10 MW.
        if frp >= 30:
            confidence = min(0.95, 0.80 + frp * 0.002)
            return {
                "verdict": "VALID",
                "confidence": round(confidence, 2),
                "reasoning": (
                    f"FRP of {frp:.1f} MW far exceeds agricultural burn thresholds (<10 MW). "
                    f"Energy output at this level indicates active wildfire regardless of "
                    f"land cover classification ('{land_cover}')."
                ),
                "method": "heuristic",
            }

        # Rule 2: Agricultural fire signature — cropland + low FRP
        if ("crop" in lc or "agri" in lc) and frp < 10:
            confidence = min(0.85, 0.60 + (10 - frp) * 0.03)
            return {
                "verdict": "FALSE_POSITIVE",
                "confidence": round(confidence, 2),
                "reasoning": (
                    f"Low FRP ({frp:.1f} MW) on cropland suggests controlled agricultural burn. "
                    f"Typical stubble fires in MP produce FRP < 10 MW."
                ),
                "method": "heuristic",
            }

        # Rule 3: Forest fire signature — forest/tree cover + moderate-high FRP
        if ("forest" in lc or "tree" in lc) and frp >= 10:
            confidence = min(0.92, 0.70 + frp * 0.003)
            return {
                "verdict": "VALID",
                "confidence": round(confidence, 2),
                "reasoning": (
                    f"FRP of {frp:.1f} MW in forested area indicates active wildfire. "
                    f"FRP > 10 MW exceeds typical agricultural burn intensity for this region."
                ),
                "method": "heuristic",
            }

        # Rule 4: Forest + low FRP — could be either
        if "forest" in lc or "tree" in lc:
            return {
                "verdict": "AMBIGUOUS",
                "confidence": 0.50,
                "reasoning": (
                    f"FRP of {frp:.1f} MW in forest-adjacent area. Low intensity could indicate "
                    f"small ground fire or edge-of-forest agricultural burn. Field verification needed."
                ),
                "method": "heuristic",
            }

        # Rule 5: Unknown land cover + moderate FRP — use severity as tiebreaker
        if frp >= 10 and severity in ("CRITICAL", "HIGH", "INFERNO"):
            confidence = min(0.85, 0.65 + frp * 0.004)
            return {
                "verdict": "VALID",
                "confidence": round(confidence, 2),
                "reasoning": (
                    f"FRP of {frp:.1f} MW with {severity} severity classification. "
                    f"Land cover '{land_cover}' unresolved, but energy output and severity "
                    f"indicate likely wildfire. Field verification recommended."
                ),
                "method": "heuristic",
            }

        # Rule 6: Default — insufficient signal
        return {
            "verdict": "AMBIGUOUS",
            "confidence": 0.40,
            "reasoning": (
                f"Land cover '{land_cover}' with FRP {frp:.1f} MW — insufficient spectral "
                f"context to classify. Recommend satellite chip review."
            ),
            "method": "heuristic",
        }


if __name__ == "__main__":
    auditor = VLMAuditor()
    mock_meta = {
        "alert_id": "GUNA-TEST-001",
        "severity": "CRITICAL",
        "frp_mw": 85.0,
        "land_cover": "Tree cover",
        "lat": 24.156,
        "lon": 77.717,
    }
    res = auditor.audit_alert(Path("outputs/last_dispatch.txt"), mock_meta)
    print(f"\nVLM AUDIT REPORT:")
    print(json.dumps(res, indent=4))
