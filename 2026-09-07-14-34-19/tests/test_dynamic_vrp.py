import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.api import server
from backend.api.server import (
    VRPRequest,
    QPSOVRPRequest,
    QAOAVRPRequest,
    CompareVRPRequest,
    run_active_vrp_solver,
    dt_graph,
)


class TestDynamicVRPRerouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = list(dt_graph.node_positions.keys())
        cls.origin = cls.nodes[0]
        cls.c1 = cls.nodes[2]
        cls.c2 = cls.nodes[5]

    def test_active_vrp_req_dijkstra(self):
        """Test active_vrp_req update and solver execution for Dijkstra VRP."""
        req = VRPRequest(
            origin_node=self.origin,
            destination_nodes=[self.c1, self.c2],
            vehicle_capacity=100.0,
        )
        res = server.solve_vrp_dijkstra(req)
        self.assertTrue(res.get("success"))

        self.assertIsNotNone(server.active_vrp_req)
        self.assertEqual(server.active_vrp_req["algorithm"], "dijkstra")
        self.assertEqual(server.active_vrp_req["origin"], self.origin)
        self.assertEqual(server.active_vrp_req["destinations"], [self.c1, self.c2])

        # Execute run_active_vrp_solver manually and verify
        recalculated = run_active_vrp_solver()
        self.assertIsNotNone(recalculated)
        self.assertTrue(recalculated.get("success"))
        self.assertEqual(server.latest_route_result, recalculated)

    def test_active_vrp_req_qpso(self):
        """Test active_vrp_req update and solver execution for QPSO VRP."""
        req = QPSOVRPRequest(
            origin_node=self.origin,
            destination_nodes=[self.c1, self.c2],
            num_particles=20,
            max_iter=10,
        )
        res = server.solve_vrp_qpso(req)
        self.assertTrue(res.get("success"))

        self.assertEqual(server.active_vrp_req["algorithm"], "qpso")
        self.assertEqual(server.active_vrp_req["num_particles"], 20)
        self.assertEqual(server.active_vrp_req["max_iter"], 10)

        recalculated = run_active_vrp_solver()
        self.assertIsNotNone(recalculated)
        self.assertTrue(recalculated.get("success"))

    def test_active_vrp_req_qaoa(self):
        """Test active_vrp_req update and solver execution for QAOA VRP."""
        req = QAOAVRPRequest(
            origin_node=self.origin,
            destination_nodes=[self.c1, self.c2],
            reps=1,
            shots=256,
        )
        res = server.solve_vrp_qaoa(req)
        self.assertTrue(res.get("success"))

        self.assertEqual(server.active_vrp_req["algorithm"], "qaoa")
        self.assertEqual(server.active_vrp_req["reps"], 1)

        recalculated = run_active_vrp_solver()
        self.assertIsNotNone(recalculated)
        self.assertTrue(recalculated.get("success"))

    def test_active_vrp_req_compare(self):
        """Test active_vrp_req update and solver execution for 3-Way Compare VRP."""
        req = CompareVRPRequest(
            origin_node=self.origin,
            destination_nodes=[self.c1, self.c2],
            reps=1,
            shots=256,
            num_particles=20,
            max_iter=10,
        )
        res = server.compare_vrp_algorithms(req)
        self.assertTrue(res.get("success"))
        self.assertIn("dijkstra", res)
        self.assertIn("qpso", res)
        self.assertIn("qaoa", res)

        self.assertEqual(server.active_vrp_req["algorithm"], "compare")

        recalculated = run_active_vrp_solver()
        self.assertIsNotNone(recalculated)
        self.assertTrue(recalculated.get("success"))
        self.assertIn("dijkstra", recalculated)

    def test_incident_recalculates_active_vrp(self):
        """Test that incident injection & clearing dynamically recalculates active VRP route."""
        req = VRPRequest(
            origin_node=self.origin,
            destination_nodes=[self.c1, self.c2],
        )
        res_before = server.solve_vrp_dijkstra(req)

        edge_id = res_before["edge_path"][0]
        dt_graph.set_incident(edge_id, penalty_multiplier=500.0)

        res_after = run_active_vrp_solver()
        self.assertIsNotNone(res_after)
        self.assertTrue(res_after.get("success"))
        self.assertGreater(res_after["total_cost"], res_before["total_cost"])

        dt_graph.clear_incident(edge_id)
        res_cleared = run_active_vrp_solver()
        self.assertEqual(res_cleared["total_cost"], res_before["total_cost"])

    def test_algorithm_switching(self):
        """Test switching active solver algorithm updates active_vrp_req state dynamically."""
        req_d = VRPRequest(origin_node=self.origin, destination_nodes=[self.c1])
        server.solve_vrp_dijkstra(req_d)
        self.assertEqual(server.active_vrp_req["algorithm"], "dijkstra")

        req_q = QAOAVRPRequest(origin_node=self.origin, destination_nodes=[self.c1], reps=1, shots=128)
        server.solve_vrp_qaoa(req_q)
        self.assertEqual(server.active_vrp_req["algorithm"], "qaoa")

        req_qp = QPSOVRPRequest(origin_node=self.origin, destination_nodes=[self.c1], num_particles=10, max_iter=5)
        server.solve_vrp_qpso(req_qp)
        self.assertEqual(server.active_vrp_req["algorithm"], "qpso")

        req_c = CompareVRPRequest(origin_node=self.origin, destination_nodes=[self.c1], reps=1, shots=128, num_particles=10, max_iter=5)
        server.compare_vrp_algorithms(req_c)
        self.assertEqual(server.active_vrp_req["algorithm"], "compare")

    def test_single_destination_vrp(self):
        """Test active VRP solver with single destination (point-to-point routing)."""
        req = VRPRequest(origin_node=self.origin, destination_nodes=[self.c1])
        res = server.solve_vrp_dijkstra(req)
        self.assertTrue(res.get("success"))
        self.assertEqual(res["visit_sequence"], [self.origin, self.c1])

        recalculated = run_active_vrp_solver()
        self.assertIsNotNone(recalculated)
        self.assertTrue(recalculated.get("success"))
        self.assertEqual(recalculated["visit_sequence"], [self.origin, self.c1])


if __name__ == "__main__":
    unittest.main()
