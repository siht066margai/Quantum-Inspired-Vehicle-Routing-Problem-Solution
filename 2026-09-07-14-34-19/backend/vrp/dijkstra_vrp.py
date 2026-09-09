from __future__ import annotations

import time
import itertools
from typing import Any, Dict, List, Optional

from backend.vrp.problem_instance import ProblemInstance, AlgorithmResult
from backend.vrp.vrp_evaluator import VRPEvaluator


class DijkstraVRPSolver:
    """
    Computes exact baseline optimal customer visit sequence and shortest physical route
    for 1-Source + N-Destination VRP by evaluating candidate permutations on dynamic graph G(t).
    """

    def solve(self, problem: ProblemInstance) -> AlgorithmResult:
        started = time.perf_counter()
        is_valid, msg = problem.is_valid()
        if not is_valid:
            return AlgorithmResult(
                algorithm="Dijkstra VRP (Exact Baseline)",
                status="error",
                success=False,
                visit_sequence=[],
                node_path=[],
                edge_path=[],
                total_cost=0.0,
                total_travel_time=0.0,
                total_distance=0.0,
                average_speed_ms=0.0,
                bottleneck_count=0,
                bottlenecks=[],
                segment_calculations=[],
                geometry=[],
                feasible=False,
                constraint_violations=[msg],
                computation_time_ms=(time.perf_counter() - started) * 1000,
                math_proof={},
                error=msg,
            )

        origin = problem.origin
        destinations = problem.destinations

        # 1. Enumerate candidate customer visit permutations
        # For 2 destinations: [C1, C2] -> Sequence A: O -> C1 -> C2, Sequence B: O -> C2 -> C1
        candidate_permutations = list(itertools.permutations(destinations))

        best_result: Optional[AlgorithmResult] = None
        min_cost = float("inf")
        permutation_evaluations: List[Dict[str, Any]] = []

        # 2. Evaluate each permutation on dynamic graph G(t)
        for perm in candidate_permutations:
            visit_seq = [origin] + list(perm)
            res = VRPEvaluator.evaluate_sequence(
                problem,
                visit_seq,
                algorithm_name="Dijkstra VRP (Exact Baseline)",
                computation_time_ms=0.0,
            )

            permutation_evaluations.append({
                "sequence": " -> ".join(visit_seq),
                "total_cost": round(res.total_cost, 2),
                "travel_time_s": round(res.total_travel_time, 2),
                "distance_m": round(res.total_distance, 2),
                "feasible": res.feasible,
            })

            if res.feasible and res.total_cost < min_cost:
                min_cost = res.total_cost
                best_result = res

        elapsed_ms = (time.perf_counter() - started) * 1000

        if best_result is None:
            return AlgorithmResult(
                algorithm="Dijkstra VRP (Exact Baseline)",
                status="infeasible",
                success=False,
                visit_sequence=[],
                node_path=[],
                edge_path=[],
                total_cost=0.0,
                total_travel_time=0.0,
                total_distance=0.0,
                average_speed_ms=0.0,
                bottleneck_count=0,
                bottlenecks=[],
                segment_calculations=[],
                geometry=[],
                feasible=False,
                constraint_violations=["No feasible route found across any customer sequence."],
                computation_time_ms=elapsed_ms,
                math_proof={},
                error="No feasible route found across any customer sequence.",
            )

        math_proof = {
            "algorithm_name": "Exact Dijkstra VRP Sequence Enumerator & Path Solver",
            "optimization_principle": "Best Sequence = argmin_{pi} [ sum_{k=1}^N d(C_{pi(k-1)}, C_{pi(k)}) ]",
            "evaluated_sequences": len(candidate_permutations),
            "dynamic_graph_state": "W(t) = alpha * T_e(t) + beta * D_e + gamma * C_e(t)",
            "selected_sequence": " -> ".join(best_result.visit_sequence),
        }

        solver_details = {
            "candidate_permutations_count": len(candidate_permutations),
            "permutation_evaluations": permutation_evaluations,
            "optimal_sequence": best_result.visit_sequence,
        }

        best_result.computation_time_ms = elapsed_ms
        best_result.math_proof = math_proof
        best_result.solver_details = solver_details
        return best_result
