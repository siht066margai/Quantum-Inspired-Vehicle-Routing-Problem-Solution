from __future__ import annotations

import time
import networkx as nx
from typing import Any, Dict, List, Optional, Tuple

from backend.vrp.problem_instance import ProblemInstance, AlgorithmResult


class VRPEvaluator:
    """
    Common evaluator engine for evaluating candidate VRP customer visit sequences
    on dynamic SUMO graph G(t). Evaluates cost, feasibility, metrics, bottlenecks,
    and road-level geometry identically across all algorithms.
    """

    @staticmethod
    def evaluate_sequence(
        problem: ProblemInstance,
        visit_sequence: List[str],
        algorithm_name: str = "Common Evaluator",
        computation_time_ms: float = 0.0,
        solver_details: Optional[Dict[str, Any]] = None,
        math_proof: Optional[Dict[str, Any]] = None,
    ) -> AlgorithmResult:
        """
        Evaluates a customer visit sequence (e.g. ['O', 'C1', 'C2']) on problem.graph G(t).
        """
        started = time.perf_counter()
        dt_graph = problem.graph
        g = dt_graph.graph

        constraint_violations: List[str] = []
        is_feasible = True

        # 1. Verify sequence structure
        if not visit_sequence or visit_sequence[0] != problem.origin:
            constraint_violations.append(f"Route must start at origin depot '{problem.origin}'.")
            is_feasible = False

        visited_customers = set(visit_sequence[1:])
        required_customers = set(problem.destinations)
        if visited_customers != required_customers:
            missing = required_customers - visited_customers
            if missing:
                constraint_violations.append(f"Missing required customers: {list(missing)}.")
                is_feasible = False

        # 2. Capacity constraint check
        total_demand = sum(problem.customer_demands.get(c, 0.0) for c in problem.destinations)
        if total_demand > problem.vehicle_capacity:
            constraint_violations.append(
                f"Total demand ({total_demand}) exceeds vehicle capacity ({problem.vehicle_capacity})."
            )
            is_feasible = False

        # 3. Path reconstruction & metric accumulation across legs
        full_node_path: List[str] = []
        full_edge_path: List[str] = []
        full_geometry: List[Tuple[float, float]] = []
        segment_calculations: List[Dict[str, Any]] = []
        bottlenecks: List[Dict[str, Any]] = []

        total_travel_time = 0.0
        total_distance = 0.0
        total_cost = 0.0

        for idx in range(len(visit_sequence) - 1):
            u_node = visit_sequence[idx]
            v_node = visit_sequence[idx + 1]

            if u_node not in g or v_node not in g:
                constraint_violations.append(f"Leg node ({u_node} -> {v_node}) not in graph.")
                is_feasible = False
                break

            try:
                leg_nodes = nx.dijkstra_path(g, u_node, v_node, weight="weight")
            except nx.NetworkXNoPath:
                constraint_violations.append(f"No path found between leg {u_node} -> {v_node}.")
                is_feasible = False
                break

            # Concatenate leg nodes avoiding duplicates at junctions
            if not full_node_path:
                full_node_path.extend(leg_nodes)
            else:
                full_node_path.extend(leg_nodes[1:])

            # Add geometry for starting node of first leg
            if not full_geometry:
                start_pos = dt_graph.node_positions.get(leg_nodes[0])
                if start_pos:
                    full_geometry.append(start_pos)

            # Traverse leg edges
            for i in range(len(leg_nodes) - 1):
                curr_u = leg_nodes[i]
                curr_v = leg_nodes[i + 1]

                edge_attrs = g[curr_u][curr_v]
                edge_id = edge_attrs.get("key", edge_attrs.get("edge_id", ""))
                full_edge_path.append(edge_id)

                edge_data = dt_graph.get_edge_data(edge_id) or edge_attrs
                length = float(edge_data.get("length", 0.0))
                tt = float(edge_data.get("travel_time", edge_data.get("free_flow_tt", 0.0)))
                speed = float(edge_data.get("speed_limit", edge_data.get("mean_speed", 13.89)))
                w = float(edge_data.get("weight", tt))
                cong = float(edge_data.get("congestion_ratio", 0.0))

                total_distance += length
                total_travel_time += tt
                total_cost += w

                segment_calculations.append({
                    "leg_index": idx + 1,
                    "leg_segment": f"{u_node} -> {v_node}",
                    "edge_id": edge_id,
                    "from_node": curr_u,
                    "to_node": curr_v,
                    "length_m": round(length, 2),
                    "speed_limit_ms": round(speed, 2),
                    "congestion_ratio": round(cong, 3),
                    "travel_time_s": round(tt, 2),
                    "accumulated_distance_m": round(total_distance, 2),
                    "accumulated_time_s": round(total_travel_time, 2),
                })

                if cong > 0.3 or edge_id in dt_graph.incidents:
                    bottlenecks.append({
                        "edge_id": edge_id,
                        "congestion_ratio": cong,
                        "is_incident": edge_id in dt_graph.incidents,
                    })

                shape = edge_data.get("shape", [])
                for p in shape:
                    pt = (float(p[0]), float(p[1]))
                    if not full_geometry or full_geometry[-1] != pt:
                        full_geometry.append(pt)

        eval_elapsed_ms = (time.perf_counter() - started) * 1000
        total_comp_ms = computation_time_ms + eval_elapsed_ms

        avg_speed = total_distance / max(total_travel_time, 0.1)

        default_proof = {
            "evaluation_engine": "Common Dynamic Graph VRP Evaluator",
            "cost_function": "f(R) = alpha * T(R) + beta * D(R) + gamma * C(R)",
            "sequence_evaluated": " -> ".join(visit_sequence),
            "total_distance_formula": "Total Distance = sum_{e in Path} L_e",
            "total_travel_time_formula": "Total Travel Time = sum_{e in Path} T_e(t)",
        }

        return AlgorithmResult(
            algorithm=algorithm_name,
            status="feasible" if is_feasible else "infeasible",
            success=is_feasible,
            visit_sequence=visit_sequence,
            node_path=full_node_path,
            edge_path=full_edge_path,
            total_cost=total_cost,
            total_travel_time=total_travel_time,
            total_distance=total_distance,
            average_speed_ms=avg_speed,
            bottleneck_count=len(bottlenecks),
            bottlenecks=bottlenecks,
            segment_calculations=segment_calculations,
            geometry=full_geometry,
            feasible=is_feasible,
            constraint_violations=constraint_violations,
            computation_time_ms=total_comp_ms,
            math_proof=math_proof or default_proof,
            solver_details=solver_details or {},
            error=None if is_feasible else "; ".join(constraint_violations),
        )
