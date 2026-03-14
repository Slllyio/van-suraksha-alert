"""
VanAagni Predictive Maintenance AI
==================================
Anomaly detection engine for the Virtual Sensor Network (VSN) and future 
physical IoT nodes. Monitors for sensor drift, battery degradation, and 
hardware failures to prevent false-positive fire alerts.

Uses a Temporal Z-Score Outlier Detection method.
"""

import numpy as np
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger(__name__)

@dataclass
class SensorHealth:
    node_id: str
    status: str # 'HEALTHY', 'DRIFT_DETECTED', 'CRITICAL_FAILURE'
    confidence: float
    message: str

class MaintenanceAI:
    def __init__(self, drift_threshold: float = 3.5):
        self.drift_threshold = drift_threshold
        # Stores recent history for each node to calculate baseline
        self.node_history: Dict[str, List[float]] = {}

    def ingest_telemetry(self, node_id: str, temperature: float) -> SensorHealth:
        """
        Analyzes a single telemetry packet for anomalies.
        """
        if node_id not in self.node_history:
            self.node_history[node_id] = []
        
        history = self.node_history[node_id]
        history.append(temperature)
        
        # Keep only the last 24 readings (e.g., 24 hours)
        if len(history) > 24:
            history.pop(0)
            
        # ── Intelligence Level 1: Statistical Outlier Detection ──
        if len(history) < 5:
            return SensorHealth(node_id, "HEALTHY", 1.0, "Establishing baseline...")

        mean = np.mean(history[:-1])
        std = np.std(history[:-1]) + 0.1 # Prevent div by zero
        
        z_score = abs(temperature - mean) / std
        
        if z_score > self.drift_threshold:
            # Check for physically impossible jumps (e.g., 20C jump in 1 min)
            delta = abs(temperature - history[-2])
            if delta > 15.0:
                return SensorHealth(
                    node_id, "CRITICAL_FAILURE", 0.98, 
                    f"Sensor hardware failure suspected. Extreme jump ({delta}C) detected."
                )
            else:
                return SensorHealth(
                    node_id, "DRIFT_DETECTED", 0.85, 
                    f"Predictive maintenance required. Node values drifting from baseline (Z={z_score:.1f})."
                )
        
        return SensorHealth(node_id, "HEALTHY", 0.99, "Normal diurnal operation.")

if __name__ == "__main__":
    # Test Scenario
    ai = MaintenanceAI()
    node = "NODE_42_SOUTH"
    
    # Simulate normal readings
    for t in [25, 26, 27, 26, 25, 24]:
        status = ai.ingest_telemetry(node, t)
        print(f"Node {node} at {t}C: {status.status}")
        
    # Simulate an anomaly (Sensor drift)
    status = ai.ingest_telemetry(node, 45.0)
    print(f"\nANOMALY DETECTED!")
    print(f"Node: {status.node_id}")
    print(f"Status: {status.status}")
    print(f"Message: {status.message}")
