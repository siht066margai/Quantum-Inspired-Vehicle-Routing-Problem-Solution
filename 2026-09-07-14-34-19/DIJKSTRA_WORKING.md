# Technical Deep-Dive: Time-Dependent Dynamic Dijkstra's Algorithm

> **Precise Developer Specification & Internal Working of the Classical Routing Engine**

---

## 1. Algorithmic Overview & Mathematical Formulation

Dijkstra's algorithm is the exact classical baseline routing engine used in the system. It operates on a directed, time-dependent dynamic graph $G(t) = (V, E, W(t))$, where $V$ represents intersections (nodes), $E$ represents road segments (directed edges), and $W(t) = \{w_{u,v}(t) \mid (u,v) \in E\}$ represents the dynamic travel cost at time step $t$.

### 1.1 Dynamic Edge Weight Function

The weight $w_{u,v}(t)$ of edge $e = (u,v)$ is computed dynamically from real-time SUMO simulation parameters without hardcoded values:

$$w_{u,v}(t) = \text{Travel Time}_{u,v}(t) = \frac{\text{Length}_{u,v}}{\max(\text{Speed}_{u,v}(t), 0.1)} \times \left( 1 + \text{CongestionPenalty}_{u,v}(t) \right)$$

where:
* $\text{Length}_{u,v}$ is the physical length of the road segment in meters.
* $\text{Speed}_{u,v}(t)$ is the current mean vehicle speed on the segment in $\text{m/s}$.
* $\text{CongestionPenalty}_{u,v}(t) = \max\left(0, \frac{\rho_{u,v}(t) - \rho_{\text{free}}}{\rho_{\text{max}}}\right)$ accounts for vehicle density $\rho_{u,v}(t)$.

---

## 2. Core Data Structures

The router implemented in [`backend/routing/dijkstra_router.py`](file:///c:/SIH_Traffic_Project/2026-09-07-14-34-19/backend/routing/dijkstra_router.py) uses NetworkX's optimized binary min-heap implementation (`nx.dijkstra_path`):

1. **Distance Map $\text{dist}[v]$**: Stores the minimum tentative travel time from origin $s$ to node $v \in V$. Initialized to $\text{dist}[s] = 0$ and $\text{dist}[v] = \infty, \forall v \neq s$.
2. **Predecessor Map $\pi[v]$**: Tracks the preceding node on the shortest path to node $v$, enabling path reconstruction via backward tracking.
3. **Priority Queue $\mathcal{Q}$**: Min-heap storing tuples $(d, u)$ ordered by current minimum tentative distance $d = \text{dist}[u]$.

---

## 3. Execution Pipeline & Internal Step-by-Step Flow

```
                           +-----------------------------------+
                           |   Initialize dist[s]=0, dist[v]=inf|
                           |   Push (0, s) into Min-Heap Q     |
                           +-----------------------------------+
                                             |
                                             v
                           +-----------------------------------+
                           |    Pop node u with min dist[u]    |
                           |            from Heap Q            |
                           +-----------------------------------+
                                             |
                                 Is u == destination node?
                                 /                       \
                             (YES)                       (NO)
                              /                             \
                             v                               v
            +----------------------------------+   +-----------------------------------+
            | Reconstruct Path via Predecessor |   |  For each neighbor v in Adj(u):   |
            | Map pi[v] backwards from dest    |   |    w = edge_weight(u, v, t)       |
            +----------------------------------+   |    if dist[u] + w < dist[v]:      |
                                                   |      dist[v] = dist[u] + w        |
                                                   |      pi[v] = u                    |
                                                   |      Push/Decrease-Key (dist[v], v)|
                                                   +-----------------------------------+
                                                                     |
                                                                     v
                                                            Repeat until Q is empty
```

### 3.1 Detailed Step Walkthrough

1. **Graph Access**: Retrieves the active `nx.DiGraph` instance from `DynamicTrafficGraph`.
2. **Node Validation**: Verifies that `origin_node` ($s$) and `destination_node` ($t$) exist in $V$.
3. **Min-Heap Extraction**:
   * Extracts node $u \in V$ with the smallest tentative distance $\text{dist}[u]$ from priority queue $\mathcal{Q}$.
4. **Edge Relaxation**:
   * For every directed outgoing edge $(u, v) \in E$, evaluates whether passing through $u$ offers a faster path to $v$:
     $$\text{if } \text{dist}[u] + w_{u,v}(t) < \text{dist}[v] \implies \begin{cases} \text{dist}[v] \leftarrow \text{dist}[u] + w_{u,v}(t) \\ \pi[v] \leftarrow u \\ \text{Push } (\text{dist}[v], v) \text{ to } \mathcal{Q} \end{cases}$$
5. **Path & Metric Reconstruction**:
   * Traces back from $t$ to $s$ using $\pi[v]$ to form node sequence $P = \langle s = v_0, v_1, v_2, \dots, v_k = t \rangle$.
   * Maps node pairs $(v_i, v_{i+1})$ to SUMO edge IDs and extracts segment length $L_e$, travel time $T_e$, and congestion ratios.

---

## 4. Multi-Vehicle Zomato VRP Routing Logic

For the 2-vehicle fleet delivery scenario (Depot Node $0 \to$ Customer $1$ & Customer $2 \to$ Depot Node $0$):
* **Vehicle 1 Path**: Computes $P_{1, \text{out}} = \text{Dijkstra}(0 \to D_1)$ and $P_{1, \text{in}} = \text{Dijkstra}(D_1 \to 0)$. Concatenates into round trip $R_1 = P_{1, \text{out}} \cup P_{1, \text{in}}$.
* **Vehicle 2 Path**: Computes $P_{2, \text{out}} = \text{Dijkstra}(0 \to D_2)$ and $P_{2, \text{in}} = \text{Dijkstra}(D_2 \to 0)$. Concatenates into round trip $R_2 = P_{2, \text{out}} \cup P_{2, \text{in}}$.
* **Combined Fleet Metrics**:
  $$\text{Total Travel Time} = \sum_{e \in R_1} w_e(t) + \sum_{e \in R_2} w_e(t)$$

---

## 5. Computational Complexity Analysis

| Metric | Complexity | Explanation |
| :--- | :--- | :--- |
| **Time Complexity** | $\mathcal{O}(|E| + |V| \log |V|)$ | Standard binary min-heap implementation over NetworkX graph $|V|$ nodes and $|E|$ edges. |
| **Space Complexity** | $\mathcal{O}(|V| + |E|)$ | Memory required to store distance array, predecessor map, and heap elements. |
| **Multi-Vehicle VRP Time** | $\mathcal{O}(K \cdot (|E| + |V| \log |V|))$ | Executed $2 \cdot K$ times for $K$ vehicles round trips. |

---

## 6. Developer Code Mapping

In [`backend/routing/dijkstra_router.py`](file:///c:/SIH_Traffic_Project/2026-09-07-14-34-19/backend/routing/dijkstra_router.py):
* `find_shortest_path(...)` (Lines 14-131): Primary entry point.
* `nx.dijkstra_path(g, origin_node, destination_node, weight=weight_key)` (Line 35): Executes binary heap path extraction.
* `segment_calculations` (Lines 77-87): Populates edge-by-edge ground truth proofs for UI display.
* `math_proof` (Lines 105-112): Formulates JSON response containing exact mathematical relaxation equations.
