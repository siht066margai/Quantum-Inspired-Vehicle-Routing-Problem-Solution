import os
import sys
import asyncio
import json
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.graph.dynamic_graph import DynamicTrafficGraph
from backend.routing.dijkstra_router import DijkstraRouter
from backend.routing.qaoa_router import QAOARouter
from backend.routing.qpso_router import QPSORouter
from backend.routing.route_analyzer import analyze_routes
from backend.simulation.sumo_manager import SumoManager

from backend.vrp.problem_instance import ProblemInstance, AlgorithmResult
from backend.vrp.dijkstra_vrp import DijkstraVRPSolver
from backend.vrp.qpso_vrp import QPSOVRPSolver
from backend.vrp.qaoa_vrp import QAOAVRPSolver

app = FastAPI(title="SIH 2026 Traffic Route Optimization Platform")

# Global instances
NET_FILE = os.path.join(ROOT_DIR, "osm.net.xml.gz")
SUMOCFG_FILE = os.path.join(ROOT_DIR, "osm.sumocfg")

dt_graph = DynamicTrafficGraph()
# Load graph topology on server startup
dt_graph.load_net_file(NET_FILE)

router = DijkstraRouter()
qaoa_router = QAOARouter()
qpso_router = QPSORouter()
sumo_mgr = SumoManager(SUMOCFG_FILE, dt_graph)

dijkstra_vrp_solver = DijkstraVRPSolver()
qpso_vrp_solver = QPSOVRPSolver()
qaoa_vrp_solver = QAOAVRPSolver()

# WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        payload = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Background simulation runner task
sim_loop_task: Optional[asyncio.Task] = None
is_loop_running = False

# Active route state tracked for recalculation on dynamic graph updates
active_route_req: Optional[Dict[str, str]] = None
latest_route_result: Optional[Dict[str, Any]] = None
# Most-recent independent runs, indexed by origin/destination, for the analysis
# endpoint. The UI starts fresh runs before requesting an analysis.
route_algorithm_runs: Dict[tuple[str, str], Dict[str, Dict[str, Any]]] = {}


def _simulation_update_payload(step_res: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the single live-state shape used by WebSocket and HTTP fallback clients."""
    state = step_res or sumo_mgr.get_snapshot()
    vehicles = sumo_mgr.get_vehicle_states() if state.get('running') else []
    congested_edges = [
        {
            'id': edge['edge_id'],
            'congestion_ratio': edge['congestion_ratio'],
            'vehicle_count': edge['vehicle_count'],
            'mean_speed': round(edge['mean_speed'], 2),
            'travel_time': round(edge['travel_time'], 1),
        }
        for edge in dt_graph.edge_metadata.values()
        if edge['congestion_ratio'] > 0.1 or edge['edge_id'] in dt_graph.incidents
    ]
    return {
        'type': 'sim_update',
        'running': state.get('running', False),
        'paused': state.get('paused', False),
        'sim_time': state.get('sim_time', 0),
        'active_vehicles': state.get('active_count', 0),
        'loaded_vehicles': state.get('loaded_count', 0),
        'arrived_vehicles': state.get('arrived_count', 0),
        'expected_vehicles': state.get('expected_count', 0),
        'vehicles': vehicles,
        'congested_edges': congested_edges[:50],
        'active_route': latest_route_result,
        'active_incidents': list(sumo_mgr.active_incidents.keys()),
        'stats': dt_graph.get_summary_stats(),
    }

# Pydantic schemas
class RouteRequest(BaseModel):
    origin_node: str
    destination_node: str

class QAOARouteRequest(RouteRequest):
    candidate_count: int = 3
    reps: int = 1
    shots: int = 1024

class QPSORouteRequest(RouteRequest):
    num_particles: int = 40
    max_iter: int = 50

class IncidentRequest(BaseModel):
    edge_id: str
    speed_factor: float = 0.05

class ClearIncidentRequest(BaseModel):
    edge_id: str

class RerouteRequest(BaseModel):
    vehicle_id: str
    edge_path: List[str]

class ResolveNodeRequest(BaseModel):
    x: float
    y: float

class VRPRequest(BaseModel):
    origin_node: str
    destination_nodes: List[str]
    alpha: float = 1.0
    beta: float = 0.0
    gamma: float = 0.0
    vehicle_capacity: float = 100.0

class QAOAVRPRequest(VRPRequest):
    reps: int = 1
    shots: int = 1024

class QPSOVRPRequest(VRPRequest):
    num_particles: int = 40
    max_iter: int = 50

# API Endpoints
@app.get("/api/network")
def get_network():
    """
    Returns full network topology (nodes, edges, boundaries) for frontend canvas visualization.
    """
    # Sample nodes & edges to avoid huge JSON payload if required, or send full geometry
    edges_payload = []
    for edge_id, meta in dt_graph.edge_metadata.items():
        edges_payload.append({
            'id': edge_id,
            'from': meta['from_node'],
            'to': meta['to_node'],
            'length': meta['length'],
            'speed': meta['speed_limit'],
            'shape': meta['shape']
        })

    nodes_payload = {
        node_id: {'x': pos[0], 'y': pos[1]}
        for node_id, pos in dt_graph.node_positions.items()
    }

    # Bounding box
    xs = [p[0] for p in dt_graph.node_positions.values()]
    ys = [p[1] for p in dt_graph.node_positions.values()]
    bounds = {
        'min_x': min(xs) if xs else 0,
        'max_x': max(xs) if xs else 2800,
        'min_y': min(ys) if ys else 0,
        'max_y': max(ys) if ys else 2600
    }

    return {
        'bounds': bounds,
        'nodes': nodes_payload,
        'edges': edges_payload,
        'stats': dt_graph.get_summary_stats()
    }

@app.post("/api/sim/start")
def start_sim(gui: bool = True):
    success = sumo_mgr.start(use_gui=gui)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start SUMO/TraCI.")
    return {"status": "started", "gui": gui}

@app.post("/api/sim/pause")
def pause_sim():
    sumo_mgr.is_paused = not sumo_mgr.is_paused
    return {"status": "paused" if sumo_mgr.is_paused else "resumed"}

@app.post("/api/sim/step")
def step_sim():
    step_data = sumo_mgr.step()
    return step_data

@app.post("/api/sim/stop")
def stop_sim():
    sumo_mgr.stop()
    return {"status": "stopped"}


@app.get("/api/sim/state")
def get_sim_state():
    """HTTP fallback for live dashboard data when a WebSocket is interrupted."""
    return _simulation_update_payload()

def _route_key(req: RouteRequest) -> tuple[str, str]:
    return (req.origin_node, req.destination_node)

def _record_route_run(req: RouteRequest, algorithm: str, result: Dict[str, Any]) -> None:
    route_algorithm_runs.setdefault(_route_key(req), {})[algorithm] = result

def _run_dijkstra(req: RouteRequest) -> Dict[str, Any]:
    result = router.find_shortest_path(dt_graph, req.origin_node, req.destination_node)
    _record_route_run(req, 'dijkstra', result)
    return result

def _run_qaoa(req: QAOARouteRequest) -> Dict[str, Any]:
    result = qaoa_router.find_route(
        dt_graph,
        req.origin_node,
        req.destination_node,
        num_vehicles=1,
        reps=min(max(req.reps, 1), 2),
        shots=min(max(req.shots, 128), 4096),
    )
    _record_route_run(req, 'qaoa', result)
    return result

def _run_qpso(req: QPSORouteRequest) -> Dict[str, Any]:
    result = qpso_router.find_route(
        dt_graph,
        req.origin_node,
        req.destination_node,
        num_particles=req.num_particles,
        max_iter=req.max_iter,
    )
    _record_route_run(req, 'qpso', result)
    return result

@app.post("/api/route/dijkstra")
@app.post("/api/route/calculate", include_in_schema=False)
def calculate_dijkstra_route(req: RouteRequest):
    """Run only the exact Dijkstra baseline on the current traffic snapshot."""
    global active_route_req, latest_route_result
    active_route_req = {'origin': req.origin_node, 'destination': req.destination_node}
    res = _run_dijkstra(req)
    latest_route_result = res
    return res

@app.post("/api/route/qaoa")
def calculate_qaoa_route(req: QAOARouteRequest):
    """Run only the Qiskit QAOA route-selection circuit on the current snapshot."""
    global active_route_req, latest_route_result
    active_route_req = {'origin': req.origin_node, 'destination': req.destination_node}
    qaoa_result = _run_qaoa(req)
    if qaoa_result.get('success'):
        latest_route_result = qaoa_result
    return qaoa_result

@app.post("/api/route/qpso")
def calculate_qpso_route(req: QPSORouteRequest):
    """Run Quantum-Behaved Particle Swarm Optimization (QPSO) route solver."""
    global active_route_req, latest_route_result
    active_route_req = {'origin': req.origin_node, 'destination': req.destination_node}
    qpso_result = _run_qpso(req)
    if qpso_result.get('success'):
        latest_route_result = qpso_result
    return qpso_result

@app.post("/api/route/analysis")
def analyze_route_algorithms(req: RouteRequest):
    """Compare Dijkstra, QAOA, and QPSO results with live traffic evidence."""
    runs = route_algorithm_runs.get(_route_key(req), {})
    dijkstra_result = runs.get('dijkstra')
    qaoa_result = runs.get('qaoa')
    qpso_result = runs.get('qpso')
    if dijkstra_result is None and qaoa_result is None and qpso_result is None:
        raise HTTPException(
            status_code=409,
            detail="Run at least one routing algorithm before analysis.",
        )
    return {
        'success': True,
        'dijkstra': dijkstra_result,
        'qaoa': qaoa_result,
        'qpso': qpso_result,
        'analysis': analyze_routes(dt_graph, dijkstra_result or {}, qaoa_result or {}, qpso_result or {}),
    }

@app.post("/api/route/compare", include_in_schema=False)
def compare_route_algorithms(req: QAOARouteRequest):
    """3-Way combined comparison endpoint executing Dijkstra, QAOA, and QPSO."""
    global active_route_req, latest_route_result
    active_route_req = {'origin': req.origin_node, 'destination': req.destination_node}

    dijkstra_result = _run_dijkstra(req)
    qaoa_result = _run_qaoa(req)
    qpso_req = QPSORouteRequest(origin_node=req.origin_node, destination_node=req.destination_node)
    qpso_result = _run_qpso(qpso_req)

    latest_route_result = qpso_result if qpso_result.get('success') else (qaoa_result if qaoa_result.get('success') else dijkstra_result)
    return {
        'success': dijkstra_result.get('success', False) or qaoa_result.get('success', False) or qpso_result.get('success', False),
        'dijkstra': dijkstra_result,
        'qaoa': qaoa_result,
        'qpso': qpso_result,
        'analysis': analyze_routes(dt_graph, dijkstra_result, qaoa_result, qpso_result),
    }

@app.post("/api/incident/inject")
def inject_incident(req: IncidentRequest):
    success = sumo_mgr.inject_incident(req.edge_id, req.speed_factor)
    if not success:
        raise HTTPException(status_code=400, detail=f"Invalid edge_id or SUMO not running: {req.edge_id}")

    # Recalculate route if active
    global latest_route_result
    route_algorithm_runs.clear()
    if active_route_req:
        latest_route_result = router.find_shortest_path(
            dt_graph, active_route_req['origin'], active_route_req['destination']
        )

    return {
        "status": "incident_injected",
        "edge_id": req.edge_id,
        "updated_route": latest_route_result
    }

@app.post("/api/incident/clear")
def clear_incident(req: ClearIncidentRequest):
    success = sumo_mgr.clear_incident(req.edge_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"No active incident found for: {req.edge_id}")

    global latest_route_result
    route_algorithm_runs.clear()
    if active_route_req:
        latest_route_result = router.find_shortest_path(
            dt_graph, active_route_req['origin'], active_route_req['destination']
        )

    return {
        "status": "incident_cleared",
        "edge_id": req.edge_id,
        "updated_route": latest_route_result
    }

@app.post("/api/vehicle/reroute")
def reroute_vehicle(req: RerouteRequest):
    success = sumo_mgr.reroute_vehicle(req.vehicle_id, req.edge_path)
    return {"status": "rerouted" if success else "failed", "vehicle_id": req.vehicle_id}

@app.post("/api/network/resolve-node")
def resolve_nearest_node(req: ResolveNodeRequest):
    """
    Converts map/canvas click coordinate (x, y) into nearest valid SUMO routing node.
    """
    if not dt_graph.node_positions:
        raise HTTPException(status_code=400, detail="Graph topology not loaded.")

    closest_node = None
    min_dist = float("inf")
    for node_id, pos in dt_graph.node_positions.items():
        dx = pos[0] - req.x
        dy = pos[1] - req.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < min_dist:
            min_dist = dist
            closest_node = node_id

    if not closest_node:
        raise HTTPException(status_code=404, detail="No node found near specified coordinate.")

    pos = dt_graph.node_positions[closest_node]
    return {
        "resolved_node": closest_node,
        "x": pos[0],
        "y": pos[1],
        "distance": round(min_dist, 2)
    }

def _build_vrp_problem_instance(req: VRPRequest) -> ProblemInstance:
    return ProblemInstance(
        origin=req.origin_node,
        destinations=req.destination_nodes,
        graph=dt_graph,
        vehicle_capacity=req.vehicle_capacity,
        objective_weights={"alpha": req.alpha, "beta": req.beta, "gamma": req.gamma},
        timestamp=sumo_mgr.get_snapshot().get("sim_time", 0.0)
    )

@app.post("/api/vrp/dijkstra")
def solve_vrp_dijkstra(req: VRPRequest):
    """Runs Dijkstra exact VRP solver on live snapshot G(t)."""
    prob = _build_vrp_problem_instance(req)
    res = dijkstra_vrp_solver.solve(prob)
    global latest_route_result
    latest_route_result = res.to_dict()
    return res.to_dict()

@app.post("/api/vrp/qpso")
def solve_vrp_qpso(req: QPSOVRPRequest):
    """Runs QPSO VRP swarm solver on live snapshot G(t)."""
    prob = _build_vrp_problem_instance(req)
    res = qpso_vrp_solver.solve(prob, num_particles=req.num_particles, max_iter=req.max_iter)
    global latest_route_result
    latest_route_result = res.to_dict()
    return res.to_dict()

@app.post("/api/vrp/qaoa")
def solve_vrp_qaoa(req: QAOAVRPRequest):
    """Runs QAOA VRP quantum solver on live snapshot G(t)."""
    prob = _build_vrp_problem_instance(req)
    res = qaoa_vrp_solver.solve(prob, reps=req.reps, shots=req.shots)
    global latest_route_result
    latest_route_result = res.to_dict()
    return res.to_dict()

@app.post("/api/vrp/compare")
def compare_vrp_algorithms(req: QAOAVRPRequest):
    """Runs 3-Way independent VRP comparison across Dijkstra, QPSO, and QAOA on snapshot G(t)."""
    prob = _build_vrp_problem_instance(req)
    dijkstra_res = dijkstra_vrp_solver.solve(prob)

    qpso_req = QPSOVRPRequest(
        origin_node=req.origin_node,
        destination_nodes=req.destination_nodes,
        alpha=req.alpha,
        beta=req.beta,
        gamma=req.gamma,
        vehicle_capacity=req.vehicle_capacity
    )
    qpso_res = qpso_vrp_solver.solve(prob, num_particles=qpso_req.num_particles, max_iter=qpso_req.max_iter)
    qaoa_res = qaoa_vrp_solver.solve(prob, reps=req.reps, shots=req.shots)

    global latest_route_result
    latest_route_result = (
        qpso_res.to_dict() if qpso_res.success else (
            qaoa_res.to_dict() if qaoa_res.success else dijkstra_res.to_dict()
        )
    )

    algos = {
        "dijkstra": dijkstra_res.to_dict(),
        "qaoa": qaoa_res.to_dict(),
        "qpso": qpso_res.to_dict()
    }
    valid_algos = {k: v for k, v in algos.items() if v.get("success")}

    outcome = {}
    if valid_algos:
        lowest_cost = min(valid_algos.items(), key=lambda x: x[1]["total_cost"])[0]
        lowest_time = min(valid_algos.items(), key=lambda x: x[1]["total_travel_time"])[0]
        fastest_compute = min(valid_algos.items(), key=lambda x: x[1]["computation_time_ms"])[0]
        outcome = {
            "lowest_cost_algorithm": lowest_cost,
            "lowest_travel_time_algorithm": lowest_time,
            "fastest_computation_algorithm": fastest_compute,
        }

    return {
        "success": bool(valid_algos),
        "problem": prob.to_dict(),
        "dijkstra": dijkstra_res.to_dict(),
        "qaoa": qaoa_res.to_dict(),
        "qpso": qpso_res.to_dict(),
        "analysis": {
            "comparison_basis": (
                "Dynamic VRP route cost, travel time, distance, speed, and computation latency "
                "derived strictly from live algorithm executions on single SUMO traffic snapshot G(t)."
            ),
            "outcome": outcome,
            "algorithms": algos,
        }
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection open and read optional incoming client messages
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                cmd = msg.get("command")
                if cmd == "start":
                    sumo_mgr.start(use_gui=msg.get("gui", True))
                elif cmd == "pause":
                    sumo_mgr.is_paused = not sumo_mgr.is_paused
                elif cmd == "step":
                    sumo_mgr.step()
                elif cmd == "stop":
                    sumo_mgr.stop()
            except Exception as e:
                print(f"Error processing WS command: {e}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

async def simulation_loop():
    """
    Background worker loop advancing SUMO step by step and broadcasting state updates.
    """
    global latest_route_result
    while True:
        if sumo_mgr.is_running and not sumo_mgr.is_paused:
            step_res = sumo_mgr.step()

            # Recalculate route automatically on dynamic graph changes if route active
            if active_route_req and step_res.get('sim_time', 0) % 5 == 0:
                latest_route_result = router.find_shortest_path(
                    dt_graph, active_route_req['origin'], active_route_req['destination']
                )

            await ws_manager.broadcast(_simulation_update_payload(step_res))

        await asyncio.sleep(sumo_mgr.step_delay_sec)

@app.on_event("startup")
async def startup_event():
    global sim_loop_task
    sim_loop_task = asyncio.create_task(simulation_loop())

@app.on_event("shutdown")
async def shutdown_event():
    sumo_mgr.stop()
    if sim_loop_task:
        sim_loop_task.cancel()

# Mount static frontend directory
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def read_root():
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Frontend index.html not found</h1>"
