"""
VanAagni Evacuation Guardian (Logistics AI)
===========================================
Calculates optimal evacuation routes for forest villages by integrating
OpenStreetMap (OSM) road networks with live smoke dispersion plumes and 
active fire boundaries.

Uses OSMnx for graph analytics and NetworkX for A* pathfinding with 
dynamic 'danger-weights'.
"""

import osmnx as ox
import networkx as nx
import numpy as np
import logging
from shapely.geometry import Point, Polygon
from typing import List, Tuple, Dict, Any

log = logging.getLogger(__name__)

class LogisticsEngine:
    def __init__(self, lat: float, lon: float, dist_km: float = 10.0):
        """
        Initializes the road network graph around a specific location.
        """
        self.center_point = (lat, lon)
        log.info(f"Downloading road network for {lat}, {lon} (Radius: {dist_km}km)...")
        # Download 'drive' network (cars/trucks)
        try:
            self.graph = ox.graph_from_point(self.center_point, dist=dist_km * 1000, network_type='drive')
            # Project to UTM for accurate distance and spatial operations
            self.graph_projected = ox.project_graph(self.graph)
            log.info("Road network loaded and projected.")
        except Exception as e:
            log.error(f"Failed to load OSM network: {e}")
            self.graph = None

    def calculate_safe_evacuation(
        self, 
        start_lat: float, 
        start_lon: float, 
        danger_polygons: List[Polygon],
        exit_points: List[Tuple[float, float]] = None
    ) -> Dict[str, Any]:
        """
        Finds the safest route from start to an exit point, penalizing roads 
        that intersect with smoke or fire zones.
        """
        if self.graph is None:
            return {"error": "Graph not initialized"}

        # 1. Find nearest nodes to start/end
        orig_node = ox.nearest_nodes(self.graph, start_lon, start_lat)
        
        # If no exit points provided, find a node on the edge of our graph
        if not exit_points:
            # Simple fallback: pick a node at the boundary of the bbox
            exit_node = list(self.graph.nodes())[-1] 
        else:
            exit_node = ox.nearest_nodes(self.graph, exit_points[0][1], exit_points[0][0])

        # 2. Update Edge Weights based on 'Friction' (Danger)
        # Standard weight is length (meters). Danger zones multiply this length.
        for u, v, k, data in self.graph.edges(data=True, keys=True):
            edge_geom = data.get('geometry', None)
            if not edge_geom:
                # Approximate geometry as straight line
                u_data = self.graph.nodes[u]
                v_data = self.graph.nodes[v]
                edge_geom = Polygon([(u_data['x'], u_data['y']), (v_data['x'], v_data['y'])])

            weight_multiplier = 1.0
            for danger_zone in danger_polygons:
                if danger_zone.intersects(edge_geom):
                    weight_multiplier += 50.0 # High penalty for dangerous roads
            
            data['danger_weight'] = data['length'] * weight_multiplier

        # 3. Pathfinding (A* with danger weighting)
        try:
            route = nx.shortest_path(self.graph, orig_node, exit_node, weight='danger_weight')
            route_coords = [[self.graph.nodes[node]['y'], self.graph.nodes[node]['x']] for node in route]
            
            # Check if route is 'clean' (no danger zones)
            total_danger = sum([self.graph.get_edge_data(route[i], route[i+1])[0].get('danger_weight', 0) for i in range(len(route)-1)])
            is_compromised = total_danger > sum([self.graph.get_edge_data(route[i], route[i+1])[0]['length'] for i in range(len(route)-1)]) * 5

            return {
                "route_geojson": route_coords,
                "is_compromised": is_compromised,
                "distance_m": sum([self.graph.get_edge_data(route[i], route[i+1])[0]['length'] for i in range(len(route)-1)])
            }
        except nx.NetworkXNoPath:
            return {"error": "No safe evacuation route found. Shelter in place advised."}

if __name__ == "__main__":
    # Test execution for Guna
    lat, lon = 24.64, 77.32
    engine = LogisticsEngine(lat, lon, dist_km=5)
    
    # Create a dummy 'Danger Zone' (Fire/Smoke)
    danger_zone = Point(77.325, 24.645).buffer(0.005) # ~500m radius
    
    result = engine.calculate_safe_evacuation(lat, lon, [danger_zone])
    if "error" in result:
        print(f"FAILED: {result['error']}")
    else:
        print(f"SUCCESS: Evacuation route found ({result['distance_m']:.0f} meters)")
        print(f"Compromised by smoke? {'YES' if result['is_compromised'] else 'NO'}")
