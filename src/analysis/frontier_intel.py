"""
VanAagni Frontier Intelligence Head
===================================
The unified reasoning engine for Level 5 software autonomy.
Synchronizes SAR-Sight, Evacuation Guardian, and Acceleration Tracking.
"""

import logging
from typing import List, Dict, Any, Optional
from shapely.geometry import Polygon

from src.analysis.sar_sight import SARSightEngine
from src.analysis.logistics_engine import LogisticsEngine
from src.analysis.acceleration_analyzer import AccelerationAnalyzer, AccelerationEvent

log = logging.getLogger(__name__)

class FrontierIntelligenceHead:
    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon
        self.sar_engine = SARSightEngine()
        self.accel_analyzer = AccelerationAnalyzer()
        # Logistics engine is lazily initialized due to OSM download overhead
        self._logistics_engine = None

    def get_logistics(self):
        if self._logistics_engine is None:
            self._logistics_engine = LogisticsEngine(self.lat, self.lon)
        return self._logistics_engine

    def compute_all_weather_moisture(self, cloud_mask_pct: float, vv_db: float, vh_db: float) -> Dict[str, Any]:
        """
        Pivots to SAR if optical data is blocked.
        """
        if cloud_mask_pct > 30.0:
            log.info(f"Cloud mask {cloud_mask_pct}%: Pivoting to SAR-Sight.")
            return self.sar_engine.estimate_moisture_proxy(vv_db, vh_db)
        else:
            return {"status": "Optical data clear", "source": "HLS"}

    def run_evacuation_audit(self, danger_polys: List[Polygon]) -> Dict[str, Any]:
        """
        Calculates safe routes out of the division.
        """
        log.info("Running Evacuation Guardian Logistics Audit...")
        engine = self.get_logistics()
        return engine.calculate_safe_evacuation(self.lat, self.lon, danger_polys)

    def analyze_fire_acceleration(self, spread_history: List[Any]) -> Dict[str, Any]:
        """
        Checks if the fire is in a 'Blow-up' phase.
        """
        event = self.accel_analyzer.analyze_trend(spread_history)
        if event:
            return {
                "acceleration": event.acceleration_km_h2,
                "is_blowup": event.is_blowup,
                "tactical_directive": self.accel_analyzer.get_prescriptive_warning(event)
            }
        return {"status": "Insufficient history for acceleration analysis"}

if __name__ == "__main__":
    # Test execution
    intel = FrontierIntelligenceHead(24.64, 77.32)
    
    # 1. All-weather check
    moisture = intel.compute_all_weather_moisture(cloud_mask_pct=85.0, vv_db=-12.0, vh_db=-24.0)
    print(f"SAR Moisture Result: {moisture}")
    
    # 2. Acceleration check (mock)
    class MockSpread:
        def __init__(self, cros, dt):
            self.cros_km_h = cros
            self.dt_hours = dt
    history = [MockSpread(0.2, 12), MockSpread(1.5, 12)]
    accel = intel.analyze_fire_acceleration(history)
    print(f"Acceleration Analysis: {accel['tactical_directive']}")
