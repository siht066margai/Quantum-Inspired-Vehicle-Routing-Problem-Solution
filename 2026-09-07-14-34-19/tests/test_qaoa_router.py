import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.graph.dynamic_graph import DynamicTrafficGraph
from backend.routing.dijkstra_router import DijkstraRouter
from backend.routing.qaoa_router import QAOARouter, QISKIT_AVAILABLE


@unittest.skipUnless(QISKIT_AVAILABLE, "Qiskit is required for QAOA tests")
class TestQAOARouter(unittest.TestCase):
    def setUp(self):
        self.graph = DynamicTrafficGraph()
        for node, position in {"s": (0, 0), "a": (1, 0), "b": (1, 1), "t": (2, 0)}.items():
            self.graph.graph.add_node(node)
            self.graph.node_positions[node] = position

        self._add_edge("s", "a", "s_a", 1.0)
        self._add_edge("a", "t", "a_t", 1.0)
        self._add_edge("s", "b", "s_b", 2.0)
        self._add_edge("b", "t", "b_t", 2.0)
        self._add_edge("s", "t", "s_t", 6.0)

    def _add_edge(self, source, target, edge_id, weight):
        data = {
            "key": edge_id,
            "edge_id": edge_id,
            "weight": weight,
            "length": weight * 10,
            "travel_time": weight,
            "free_flow_tt": weight,
            "congestion_ratio": 0.0,
            "shape": [self.graph.node_positions[source], self.graph.node_positions[target]],
        }
        self.graph.graph.add_edge(source, target, **data)
        self.graph.edge_metadata[edge_id] = data

    def test_qaoa_returns_a_feasible_candidate_route(self):
        result = QAOARouter(maxiter=30, restarts=2).find_route(
            self.graph, "s", "t", candidate_count=3, reps=1, shots=128
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["qaoa_feasible"])
        self.assertEqual(result["qaoa_qubits"], 3)
        self.assertEqual(result["node_path"][0], "s")
        self.assertEqual(result["node_path"][-1], "t")
        self.assertAlmostEqual(sum(result["candidate_costs"]), result["normalization_factor"], places=4)
        self.assertEqual(result["selected_feasible_bitstring"].count("1"), 1)

    def test_dijkstra_remains_the_exact_baseline(self):
        dijkstra = DijkstraRouter().find_shortest_path(self.graph, "s", "t")
        qaoa = QAOARouter(maxiter=30, restarts=2).find_route(
            self.graph, "s", "t", candidate_count=3, reps=1, shots=128
        )

        self.assertTrue(dijkstra["success"])
        self.assertTrue(qaoa["success"])
        self.assertLessEqual(dijkstra["total_cost"], qaoa["total_cost"])


if __name__ == "__main__":
    unittest.main()
