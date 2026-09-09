import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.graph.dynamic_graph import DynamicTrafficGraph
from backend.vrp.problem_instance import ProblemInstance, AlgorithmResult
from backend.vrp.dijkstra_vrp import DijkstraVRPSolver
from backend.vrp.qpso_vrp import QPSOVRPSolver
from backend.vrp.qaoa_vrp import QAOAVRPSolver
from backend.vrp.vrp_evaluator import VRPEvaluator


class TestVRPPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.net_file = os.path.join(ROOT_DIR, "osm.net.xml.gz")
        cls.dt_graph = DynamicTrafficGraph()
        cls.dt_graph.load_net_file(cls.net_file)
        cls.dijkstra_solver = DijkstraVRPSolver()
        cls.qpso_solver = QPSOVRPSolver(num_particles=20, max_iter=20)
        cls.qaoa_solver = QAOAVRPSolver(maxiter=15, restarts=1)

    def test_vrp_problem_instance_creation(self):
        """Verify ProblemInstance construction and node validation on SUMO network graph."""
        nodes = list(self.dt_graph.graph.nodes())
        origin = nodes[0]
        c1 = nodes[5]
        c2 = nodes[12]

        prob = ProblemInstance(
            origin=origin,
            destinations=[c1, c2],
            graph=self.dt_graph,
            vehicle_capacity=100.0,
        )

        is_valid, msg = prob.is_valid()
        self.assertTrue(is_valid)
        self.assertEqual(prob.origin, origin)
        self.assertEqual(len(prob.destinations), 2)
        self.assertIn(c1, prob.customer_demands)

    def test_dijkstra_vrp_solver(self):
        """Verify Dijkstra exact VRP sequence enumeration (O -> C1 -> C2 vs O -> C2 -> C1)."""
        nodes = list(self.dt_graph.graph.nodes())
        origin = nodes[0]
        c1 = nodes[5]
        c2 = nodes[10]

        prob = ProblemInstance(origin=origin, destinations=[c1, c2], graph=self.dt_graph)
        res = self.dijkstra_solver.solve(prob)

        self.assertTrue(res.success)
        self.assertEqual(res.algorithm, "Dijkstra VRP (Exact Baseline)")
        self.assertEqual(res.visit_sequence[0], origin)
        self.assertSetEqual(set(res.visit_sequence[1:]), {c1, c2})
        self.assertGreater(res.total_distance, 0)
        self.assertGreater(res.total_travel_time, 0)
        self.assertIn("candidate_permutations_count", res.solver_details)
        self.assertEqual(res.solver_details["candidate_permutations_count"], 2)

    def test_qpso_vrp_solver(self):
        """Verify QPSO discrete VRP swarm solver (quantum updates & rank discretization)."""
        nodes = list(self.dt_graph.graph.nodes())
        origin = nodes[0]
        c1 = nodes[5]
        c2 = nodes[10]

        prob = ProblemInstance(origin=origin, destinations=[c1, c2], graph=self.dt_graph)
        res = self.qpso_solver.solve(prob)

        self.assertTrue(res.success)
        self.assertIn("QPSO", res.algorithm)
        self.assertEqual(res.visit_sequence[0], origin)
        self.assertSetEqual(set(res.visit_sequence[1:]), {c1, c2})
        self.assertGreater(res.total_distance, 0)
        self.assertEqual(res.solver_details["particles_M"], 20)
        self.assertIn("rank_discretization_table", res.solver_details)

    def test_qaoa_vrp_solver(self):
        """Verify QAOA VRP solver (QUBO/Ising formulation, circuit synthesis, bitstring decoding)."""
        nodes = list(self.dt_graph.graph.nodes())
        origin = nodes[0]
        c1 = nodes[3]
        c2 = nodes[6]

        prob = ProblemInstance(origin=origin, destinations=[c1, c2], graph=self.dt_graph)
        res = self.qaoa_solver.solve(prob, reps=1, shots=512)

        self.assertTrue(res.success)
        self.assertIn("QAOA", res.algorithm)
        self.assertEqual(res.visit_sequence[0], origin)
        self.assertSetEqual(set(res.visit_sequence[1:]), {c1, c2})
        self.assertGreater(res.total_distance, 0)
        self.assertEqual(res.solver_details["qaoa_qubits"], 4)  # 2x2 position decision matrix
        self.assertIn("penalty_multiplier_P", res.solver_details)

    def test_dynamic_traffic_reaction(self):
        """Verify that traffic changes and incidents alter dynamic graph weights and re-optimize route cost."""
        nodes = list(self.dt_graph.graph.nodes())
        origin = nodes[0]
        c1 = nodes[5]
        c2 = nodes[10]

        prob_before = ProblemInstance(origin=origin, destinations=[c1, c2], graph=self.dt_graph)
        res_before = self.dijkstra_solver.solve(prob_before)

        # Inject an incident on an edge of the active route
        target_edge = res_before.edge_path[0]
        self.dt_graph.set_incident(target_edge, penalty_multiplier=500.0)

        # Re-evaluate
        prob_after = ProblemInstance(origin=origin, destinations=[c1, c2], graph=self.dt_graph)
        res_after = self.dijkstra_solver.solve(prob_after)

        self.assertTrue(res_after.success)
        # Cost must increase significantly due to heavy incident penalty
        self.assertGreater(res_after.total_cost, res_before.total_cost)

        # Clear incident for cleanup
        self.dt_graph.clear_incident(target_edge)

    def test_no_hardcoding(self):
        """Verify that solver solves for arbitrary user-selected node choices without pre-canned routes."""
        nodes = list(self.dt_graph.graph.nodes())
        # Pick 3 different arbitrary nodes
        origin = nodes[15]
        c1 = nodes[25]
        c2 = nodes[35]

        prob = ProblemInstance(origin=origin, destinations=[c1, c2], graph=self.dt_graph)
        res = self.dijkstra_solver.solve(prob)

        self.assertTrue(res.success)
        self.assertEqual(res.visit_sequence[0], origin)
        self.assertSetEqual(set(res.visit_sequence[1:]), {c1, c2})

    def test_algorithm_independence(self):
        """Verify that changing QPSO parameters does not alter Dijkstra execution."""
        nodes = list(self.dt_graph.graph.nodes())
        origin = nodes[0]
        c1 = nodes[5]
        c2 = nodes[10]

        prob = ProblemInstance(origin=origin, destinations=[c1, c2], graph=self.dt_graph)

        dijkstra_1 = self.dijkstra_solver.solve(prob)
        # Run QPSO with different parameters
        _ = self.qpso_solver.solve(prob, num_particles=10, max_iter=5)
        dijkstra_2 = self.dijkstra_solver.solve(prob)

        self.assertEqual(dijkstra_1.total_cost, dijkstra_2.total_cost)
        self.assertEqual(dijkstra_1.visit_sequence, dijkstra_2.visit_sequence)


if __name__ == "__main__":
    unittest.main()
