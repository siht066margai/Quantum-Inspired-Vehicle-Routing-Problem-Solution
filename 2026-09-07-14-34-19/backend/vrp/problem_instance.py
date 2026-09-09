from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.graph.dynamic_graph import DynamicTrafficGraph


@dataclass
class ProblemInstance:
    """
    Immutable representation of a dynamic VRP problem instance captured at simulation time t.
    Contains origin (depot/restaurant), destinations (customers), graph topology G(t),
    dynamic edge weights, vehicle capacities, customer demands, objective config, and active incidents.
    """
    origin: str
    destinations: List[str]
    graph: DynamicTrafficGraph
    vehicle_capacity: float = 100.0
    customer_demands: Dict[str, float] = field(default_factory=dict)
    objective_weights: Dict[str, float] = field(
        default_factory=lambda: {"alpha": 1.0, "beta": 0.0, "gamma": 0.0}
    )
    time_windows: Optional[Dict[str, Tuple[float, float]]] = None
    incidents: Dict[str, float] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.customer_demands:
            # Default demand of 10 units per customer if unspecified
            self.customer_demands = {dest: 10.0 for dest in self.destinations}
        if not self.incidents and self.graph:
            self.incidents = dict(self.graph.incidents)

    def is_valid(self) -> Tuple[bool, str]:
        """Validates that origin and all destinations exist in the graph network."""
        g = self.graph.graph
        if self.origin not in g:
            return False, f"Origin node '{self.origin}' not present in SUMO network graph."
        for idx, dest in enumerate(self.destinations):
            if dest not in g:
                return False, f"Destination {idx + 1} node '{dest}' not present in SUMO network graph."
        if len(self.destinations) == 0:
            return False, "At least one destination must be specified."
        return True, "Valid ProblemInstance"

    def to_dict(self) -> Dict[str, Any]:
        """Returns JSON-serializable problem instance metadata."""
        return {
            "origin": self.origin,
            "destinations": self.destinations,
            "vehicle_capacity": self.vehicle_capacity,
            "customer_demands": self.customer_demands,
            "objective_weights": self.objective_weights,
            "incident_count": len(self.incidents),
            "timestamp": self.timestamp,
        }


@dataclass
class AlgorithmResult:
    """
    Standardized algorithm result schema returned by every VRP solver (Dijkstra, QPSO, QAOA).
    Allows fair, objective, 3-way numerical and visual comparison.
    """
    algorithm: str
    status: str
    success: bool
    visit_sequence: List[str]  # e.g., ['O', 'C1', 'C2']
    node_path: List[str]
    edge_path: List[str]
    total_cost: float
    total_travel_time: float
    total_distance: float
    average_speed_ms: float
    bottleneck_count: int
    bottlenecks: List[Dict[str, Any]]
    segment_calculations: List[Dict[str, Any]]
    geometry: List[Tuple[float, float]]
    feasible: bool
    constraint_violations: List[str]
    computation_time_ms: float
    math_proof: Dict[str, Any]
    solver_details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "status": self.status,
            "success": self.success,
            "visit_sequence": self.visit_sequence,
            "node_path": self.node_path,
            "edge_path": self.edge_path,
            "total_cost": round(self.total_cost, 2),
            "total_travel_time": round(self.total_travel_time, 2),
            "total_distance": round(self.total_distance, 2),
            "average_speed_ms": round(self.average_speed_ms, 2),
            "bottleneck_count": self.bottleneck_count,
            "bottlenecks": self.bottlenecks,
            "segment_calculations": self.segment_calculations,
            "geometry": self.geometry,
            "feasible": self.feasible,
            "constraint_violations": self.constraint_violations,
            "computation_time_ms": round(self.computation_time_ms, 3),
            "math_proof": self.math_proof,
            "solver_details": self.solver_details,
            "error": self.error,
        }
