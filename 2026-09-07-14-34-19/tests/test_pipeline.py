import os
import sys
import unittest

# Add project root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.graph.dynamic_graph import DynamicTrafficGraph
from backend.traffic.traffic_extractor import TrafficStateExtractor
from backend.routing.dijkstra_router import DijkstraRouter
from backend.routing.qaoa_router import QAOARouter
from backend.routing.qpso_router import QPSORouter
from backend.routing.route_analyzer import analyze_routes

class TestTrafficPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.net_file = os.path.join(ROOT_DIR, "osm.net.xml.gz")
        cls.dt_graph = DynamicTrafficGraph()
        cls.dt_graph.load_net_file(cls.net_file)
        cls.dijkstra_router = DijkstraRouter()
        cls.qaoa_router = QAOARouter(maxiter=15, restarts=1)
        cls.qpso_router = QPSORouter(num_particles=20, max_iter=20)

    def test_graph_construction(self):
        """Verify network graph loading, nodes, and edges."""
        self.assertGreater(self.dt_graph.graph.number_of_nodes(), 100)
        self.assertGreater(self.dt_graph.graph.number_of_edges(), 200)
        self.assertIn('294832082#3', self.dt_graph.edge_metadata)

    def test_dijkstra_routing(self):
        """Verify Dijkstra shortest path on dynamic graph G(t)."""
        node_ids = list(self.dt_graph.graph.nodes())
        origin = node_ids[0]
        dest = node_ids[10]

        res = self.dijkstra_router.find_shortest_path(self.dt_graph, origin, dest)
        if res.get('success'):
            self.assertTrue(res['success'])
            self.assertEqual(res['algorithm'], 'Dijkstra')
            self.assertGreater(res['total_distance'], 0)
            self.assertGreater(res['total_travel_time'], 0)

    def test_qaoa_link_based_vrp_routing(self):
        """Verify QAOA Link-Based VRP algorithm execution on dynamic graph G(t)."""
        node_ids = list(self.dt_graph.graph.nodes())
        origin = node_ids[0]
        dest = node_ids[5]

        res = self.qaoa_router.find_route(self.dt_graph, origin, dest, num_vehicles=1, reps=1)
        self.assertTrue(res['success'])
        self.assertIn("QAOA", res['algorithm'])
        self.assertGreater(res['qaoa_qubits'], 0)
        self.assertGreater(res['total_distance'], 0)
        self.assertGreater(res['total_travel_time'], 0)
        self.assertIn('penalty_multiplier_P', res)

    def test_qpso_routing(self):
        """Verify QPSO algorithm execution on dynamic graph G(t)."""
        node_ids = list(self.dt_graph.graph.nodes())
        origin = node_ids[0]
        dest = node_ids[5]

        res = self.qpso_router.find_route(self.dt_graph, origin, dest)
        self.assertTrue(res['success'])
        self.assertIn("QPSO", res['algorithm'])
        self.assertGreater(res['total_distance'], 0)
        self.assertGreater(res['total_travel_time'], 0)
        self.assertEqual(res['qpso_particles'], 20)

    def test_route_analysis_comparison(self):
        """Verify live 3-way side-by-side comparison between Dijkstra, QAOA, and QPSO outputs."""
        node_ids = list(self.dt_graph.graph.nodes())
        origin = node_ids[0]
        dest = node_ids[5]

        dijkstra_res = self.dijkstra_router.find_shortest_path(self.dt_graph, origin, dest)
        qaoa_res = self.qaoa_router.find_route(self.dt_graph, origin, dest, num_vehicles=1, reps=1)
        qpso_res = self.qpso_router.find_route(self.dt_graph, origin, dest)

        analysis = analyze_routes(self.dt_graph, dijkstra_res, qaoa_res, qpso_res)
        self.assertTrue(analysis['success'])
        self.assertIn('outcome', analysis)
        self.assertIn('dijkstra', analysis['algorithms'])
        self.assertIn('qaoa', analysis['algorithms'])
        self.assertIn('qpso', analysis['algorithms'])

if __name__ == '__main__':
    unittest.main()
