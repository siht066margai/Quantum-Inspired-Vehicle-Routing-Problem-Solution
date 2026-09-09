import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.graph.dynamic_graph import DynamicTrafficGraph
from backend.routing.route_analyzer import analyze_routes


class TestRouteAnalyzer(unittest.TestCase):
    def setUp(self):
        self.graph = DynamicTrafficGraph()
        self.graph.edge_metadata = {
            "safe": {"congestion_ratio": 0.05},
            "busy": {"congestion_ratio": 0.80},
        }
        self.graph.incidents = {"busy": 100.0}

    def test_recommends_lowest_dynamic_cost_then_reports_traffic_risk(self):
        dijkstra = {
            "success": True, "algorithm": "Dijkstra", "edge_path": ["safe"],
            "total_cost": 10, "total_travel_time": 10, "total_distance": 100,
            "bottleneck_count": 0, "computation_time_ms": 1,
        }
        qaoa = {
            "success": True, "algorithm": "QAOA (Qiskit statevector)", "edge_path": ["busy"],
            "total_cost": 12, "total_travel_time": 12, "total_distance": 100,
            "bottleneck_count": 1, "computation_time_ms": 100,
            "feasible_probability": 0.7, "selected_probability": 0.3,
            "qaoa_qubits": 3, "qaoa_depth": 1, "candidate_route_count": 3,
        }

        analysis = analyze_routes(self.graph, dijkstra, qaoa)

        self.assertTrue(analysis["success"])
        self.assertEqual(analysis["outcome"]["best_algorithm"], "Dijkstra")
        self.assertEqual(analysis["outcome"]["lowest_traffic_risk_algorithm"], "Dijkstra")
        self.assertEqual(analysis["algorithms"]["qaoa"]["incident_edge_count"], 1)


if __name__ == "__main__":
    unittest.main()
