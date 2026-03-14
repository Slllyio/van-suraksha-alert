"""
VanAagni Temporal Acceleration Analyzer
=======================================
Calculates the second derivative of fire growth (Acceleration) to detect
impending "Blow-up" events. 

Standard EWS only monitors velocity (Rate of Spread). This module monitors 
if that velocity is increasing exponentially, which is a precursor to 
extreme fire behavior.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

log = logging.getLogger(__name__)

@dataclass
class AccelerationEvent:
    acceleration_km_h2: float
    velocity_current_km_h: float
    is_blowup: bool
    confidence: float

class AccelerationAnalyzer:
    def __init__(self, blowup_threshold: float = 0.5):
        """
        blowup_threshold: km/h^2 acceleration that triggers a blow-up warning.
        """
        self.blowup_threshold = blowup_threshold

    def analyze_trend(self, spread_history: List[Any]) -> Optional[AccelerationEvent]:
        """
        Analyzes a sequence of SpreadStats to find acceleration.
        
        Formula: a = (V_final - V_initial) / Delta_T
        """
        if len(spread_history) < 2:
            return None
            
        # Get the two most recent spread segments
        s1 = spread_history[-2] # Previous segment
        s2 = spread_history[-1] # Current segment
        
        v_initial = s1.cros_km_h
        v_final = s2.cros_km_h
        dt = s2.dt_hours
        
        if dt <= 0:
            return None
            
        # Acceleration in km/h^2
        accel = (v_final - v_initial) / dt
        
        is_blowup = accel > self.blowup_threshold
        
        return AccelerationEvent(
            acceleration_km_h2 = round(accel, 4),
            velocity_current_km_h = round(v_final, 4),
            is_blowup = is_blowup,
            confidence = 0.85 # Heuristic for now
        )

    def get_prescriptive_warning(self, event: AccelerationEvent) -> str:
        """
        Generates a tactical warning based on the acceleration.
        """
        if not event.is_blowup:
            return "Stable spread detected. Maintain current suppression strategy."
            
        if event.acceleration_km_h2 > 1.0:
            return "⚠️ CRITICAL: EXPONENTIAL BLOW-UP DETECTED. Immediate withdrawal of ground crews from the front. Erratic fire behavior imminent."
        else:
            return "📈 WARNING: Fire is accelerating. Increase fireline width and monitor for spotting across barriers."

if __name__ == "__main__":
    # Test Scenario
    # Segment 1: spreading at 0.5 km/h
    # Segment 2: 12 hours later, spreading at 1.2 km/h
    
    class MockSpread:
        def __init__(self, cros, dt):
            self.cros_km_h = cros
            self.dt_hours = dt
            
    history = [MockSpread(0.5, 12), MockSpread(1.2, 12)]
    
    analyzer = AccelerationAnalyzer(blowup_threshold=0.05)
    event = analyzer.analyze_trend(history)
    
    if event:
        print(f"Acceleration: {event.acceleration_km_h2} km/h^2")
        print(f"Blow-up? {'YES' if event.is_blowup else 'NO'}")
        print(f"Directive: {analyzer.get_prescriptive_warning(event)}")
