"""
VanAagni Infrastructure Graph (Cascading Failure Analyzer)
==========================================================
Models the Guna Division's critical infrastructure as a topological graph.
Predicts cascading secondary disasters (e.g., grid blackouts) when fire 
nodes impact physical assets.

Uses NetworkX for dependency modeling.
"""

import networkx as nx
import logging
from typing import List, Dict, Any
from shapely.geometry import Point

log = logging.getLogger(__name__)

class InfrastructureGraph:
    def __init__(self):
        self.G = nx.DiGraph() # Directed graph for dependencies
        self._build_guna_base_graph()

    def _build_guna_base_graph(self):
        """
        Hardcodes a representative dependency graph for the Guna region.
        In a full deployment, this is loaded from PostGIS/OSM.
        """
        # --- Nodes (Assets) ---
        # Format: (id, {type, lat, lon, priority})
        assets = [
            ("SUB_GUNA_CENTRAL", {"type": "substation", "lat": 24.64, "lon": 77.32, "priority": 1}),
            ("HOSPITAL_GUNA", {"type": "hospital", "lat": 24.65, "lon": 77.33, "priority": 1}),
            ("TOWER_GOUMUKH", {"type": "telecom", "lat": 24.12, "lon": 77.45, "priority": 2}),
            ("WATER_PUMP_A", {"type": "water", "lat": 24.13, "lon": 77.46, "priority": 2}),
            ("VILLAGE_CLUSTER_SOUTH", {"type": "residential", "lat": 24.10, "lon": 77.44, "priority": 3})
        ]
        
        self.G.add_nodes_from(assets)

        # --- Edges (Dependencies) ---
        # Hospital depends on Central Substation
        self.G.add_edge("SUB_GUNA_CENTRAL", "HOSPITAL_GUNA", relation="power")
        # Goumukh Tower depends on local power (simulated)
        self.G.add_edge("SUB_GUNA_CENTRAL", "TOWER_GOUMUKH", relation="power")
        # Water Pump depends on Central Substation
        self.G.add_edge("SUB_GUNA_CENTRAL", "WATER_PUMP_A", relation="power")
        # Village depends on Telecom Tower
        self.G.add_edge("TOWER_GOUMUKH", "VILLAGE_CLUSTER_SOUTH", relation="comms")

    def simulate_cascading_failure(self, fire_polygons: List[Any]) -> Dict[str, Any]:
        """
        Determines which nodes are 'destroyed' by fire and calculates the
        cascading impact on dependent nodes.
        """
        destroyed_nodes = []
        
        # 1. Primary Destruction (Physical Fire Impact)
        for node, data in self.G.nodes(data=True):
            node_pt = Point(data['lon'], data['lat'])
            for fire in fire_polygons:
                if fire.contains(node_pt):
                    destroyed_nodes.append(node)
                    break
        
        # 2. Cascading Failure (Topological Impact)
        # Any node whose dependencies are all destroyed becomes deactivated.
        # For simplicity, we use 'any dependency destroyed' for critical infrastructure.
        active_graph = self.G.copy()
        for node in destroyed_nodes:
            if active_graph.has_node(node):
                active_graph.remove_node(node)
        
        # Identify nodes that are still in the original graph but no longer
        # reachable from their primary sources (e.g. Substation).
        # This is a simplified 'connectivity' check.
        total_lost = []
        for node in self.G.nodes():
            # If a hospital lost its path to the substation, it's 'down'
            if node != "SUB_GUNA_CENTRAL":
                try:
                    if not nx.has_path(active_graph, "SUB_GUNA_CENTRAL", node):
                        total_lost.append(node)
                except (nx.NodeNotFound, nx.NetworkXNoPath):
                    total_lost.append(node)

        return {
            "physically_destroyed": destroyed_nodes,
            "topologically_deactivated": [n for n in total_lost if n not in destroyed_nodes],
            "total_impact_count": len(set(total_lost + destroyed_nodes))
        }

if __name__ == "__main__":
    from shapely.geometry import Point
    
    graph = InfrastructureGraph()
    
    # Simulate a fire hitting the Central Substation
    fire_at_sub = Point(77.32, 24.64).buffer(0.01) # 1km radius
    
    impact = graph.simulate_cascading_failure([fire_at_sub])
    
    print("\n--- ⚡ CASCADING FAILURE ANALYSIS ---")
    print(f"Direct Fire Hits: {impact['physically_destroyed']}")
    print(f"Secondary Deactivations: {impact['topologically_deactivated']}")
    print(f"Conclusion: {impact['total_impact_count']} assets impacted by single substation failure.")
    print("-" * 40)
