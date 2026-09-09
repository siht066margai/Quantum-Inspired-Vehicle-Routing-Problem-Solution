# Real-Time Dynamic Vehicle Routing Problem (VRP) Platform: Dijkstra, QAOA & QPSO

> **A Hybrid Quantum & Classical Routing Architecture Powered by SUMO Traffic Simulation**

---

## 1. Executive Summary & System Architecture

This repository implements an end-to-end, zero-hardcoding Vehicle Routing Problem (VRP) platform that integrates real-time traffic dynamics from the **SUMO (Simulation of Urban MObility)** traffic simulator into three routing optimization engines:
1. **Dijkstra's Algorithm**: Classical time-dependent single-source shortest path tree baseline.
2. **QAOA (Quantum Approximate Optimization Algorithm)**: Link-based gate-based quantum routing algorithm based on Azfar et al. (*ACM Trans. Quantum Comput.*, 2025).
3. **QPSO (Quantum-Behaved Particle Swarm Optimization)**: Delta-potential well swarm intelligence optimizer based on Herrera et al. (*Pesquisa Operacional*, 2015).

### High-Level System Architecture

```
                                 +-----------------------------------+
                                 |   SUMO Traffic Simulator (TraCI)  |
                                 +-----------------------------------+
                                                   |
                                     Live Vehicle Speeds & Density
                                                   v
                                 +-----------------------------------+
                                 |    DynamicTrafficGraph (G(t))     |
                                 |  w_e(t) = (L_e / v_e) * (1 + p_e) |
                                 +-----------------------------------+
                                                   |
                   +-------------------------------+-------------------------------+
                   |                               |                               |
                   v                               v                               v
     +---------------------------+   +---------------------------+   +---------------------------+
     |     Dijkstra Router       |   |        QAOA Router        |   |        QPSO Router        |
     | (Priority Queue / Heap)   |   | (Qiskit Statevector/QUBO) |   | (Delta-Potential Swarm)   |
     +---------------------------+   +---------------------------+   +---------------------------+
                   |                               |                               |
                   +-------------------------------+-------------------------------+
                                                   |
                                    JSON Response & Proof Artifacts
                                                   v
                                 +-----------------------------------+
                                 |    FastAPI Web Server Backend     |
                                 |          (server.py)              |
                                 +-----------------------------------+
                                                   |
                                            HTTP REST / WebSocket
                                                   v
                                 +-----------------------------------+
                                 |  HTML5 Canvas Frontend Dashboard  |
                                 |     (Red / Orange / Pink Map)     |
                                 +-----------------------------------+
```

---

## 2. Core Project Objectives & Principles

* **Zero Hardcoded Constants**: All edge weights, travel times, speeds, and bottlenecks are dynamically extracted from live SUMO network state $G(t)$ at runtime.
* **Rigorous Theoretical Compliance**:
  * QAOA follows Azfar et al. (2025) link-based VRP formulation, penalty scaling $P = 2 \sum |w_{i,j}|$, Ising transformation, Trotterized ansatz circuits, and COBYLA parameter tuning.
  * QPSO follows Herrera et al. (2015) delta-potential well wavefunction collapse, $mbest$ calculation, $\alpha(t)$ linear decay ($1.0 \to 0.5$), and Rank Discretization (SPV).
* **Multi-Vehicle Fleet Support**: Solves 2-vehicle Zomato distribution VRP (Depot Node $0 \to$ Customer $1$ & Customer $2 \to$ Depot Return) satisfying flow conservation ($\sum_j x_{0,j} = 2, \sum_i x_{i,0} = 2$).
* **Transparent Ground-Truth Proofs**: Displays step-by-step mathematical proofs and relaxation/quantum state traces across a 5-tab analysis UI workspace.

---

## 3. Tech Stack & Repository Structure

### Technical Stack
* **Language**: Python 3.11+
* **Quantum Computing**: Qiskit 1.0+ (`qiskit.QuantumCircuit`, `qiskit.quantum_info.Statevector`)
* **Numerical & Optimization**: NumPy, SciPy (`scipy.optimize.minimize` via COBYLA)
* **Graph Mechanics**: NetworkX 3.0+
* **Simulation Engine**: SUMO (`sumolib`, `traci`)
* **Backend Framework**: FastAPI, Uvicorn, WebSockets
* **Frontend**: Vanilla JavaScript (ES6+), HTML5 Canvas, GitHub Markdown CSS

### File & Directory Structure

```
SIH_Traffic_Project/
├── README.md                      # Main system architecture & project guide
├── DIJKSTRA_WORKING.md            # Technical deep-dive into Dijkstra's Algorithm
├── QAOA_WORKING.md                # Technical deep-dive into QAOA (Azfar et al. 2025)
├── QPSO_WORKING.md                # Technical deep-dive into QPSO (Herrera et al. 2015)
├── requirements.txt               # Python dependencies
├── backend/
│   ├── api/
│   │   └── server.py              # FastAPI REST API & WebSocket endpoints
│   ├── graph/
│   │   └── dynamic_graph.py       # SUMO graph wrapper & dynamic weight calculator
│   └── routing/
│       ├── dijkstra_router.py     # Classical Dijkstra shortest path router
│       ├── qaoa_router.py         # Quantum QAOA link-VRP solver
│       ├── qpso_router.py         # Quantum-behaved particle swarm router
│       └── route_analyzer.py      # Comparative 3-way route analyzer
├── frontend/
│   ├── index.html                 # Main dashboard UI HTML
│   ├── styles.css                 # Custom styling & tab layouts
│   └── app.js                     # Interactive canvas map & API client
├── tests/
│   └── test_pipeline.py           # Comprehensive automated unit tests
└── osm.sumocfg                    # SUMO network configuration
```

---

## 4. API Specifications

### 1. `POST /api/route/dijkstra`
Computes classical shortest path using priority queue graph relaxation.
* **Payload**: `{"origin_node": "0", "destination_node": "D1", "destination_node_2": "D2", "num_vehicles": 2}`
* **Response**: Path nodes, edge IDs, total travel time (s), total distance (m), segment breakdown, and math proofs.

### 2. `POST /api/route/qaoa`
Executes link-based QAOA variational quantum circuit optimization.
* **Payload**: `{"origin_node": "0", "destination_node": "D1", "num_vehicles": 2, "reps": 1}`
* **Response**: Qubit count, QUBO matrix, Ising Hamiltonian coefficients, COBYLA loss history, bitstring measurement probabilities, decoded routes, and math proofs.

### 3. `POST /api/route/qpso`
Executes quantum-behaved particle swarm continuous search.
* **Payload**: `{"origin_node": "0", "destination_node": "D1", "num_particles": 40, "max_iter": 50}`
* **Response**: Particle count $M$, iterations $T$, $gbest$ vector, $mbest$ vector, $\alpha(t)$ decay trace, SPV rank table, discretized tour, and math proofs.

### 4. `POST /api/route/compare`
Executes all three algorithms concurrently on identical SUMO graph state $G(t)$ and returns comparative metrics.

---

## 5. Setup & Execution Guide

### Prerequisites
1. Installed Python 3.11+ environment.
2. Virtual environment created with required packages:
   ```powershell
   cd C:\SIH_Traffic_Project\2026-09-07-14-34-19
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

### Launching the Application
Run the Uvicorn server **from the project root directory**:
```powershell
cd C:\SIH_Traffic_Project\2026-09-07-14-34-19
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
```
Open your web browser to **`http://127.0.0.1:8000`**.

### Running Automated Verification Tests
```powershell
python tests/test_pipeline.py
```

---

## 6. Future Scope & Research Roadmap

1. **Hardware Execution on IBM Quantum**: Transition QAOA circuit execution from `qiskit.quantum_info.Statevector` to IBM Quantum hardware (e.g., `ibm_brisbane`, `ibm_kyiv`) via `qiskit-ibm-runtime` with error mitigation (Zero-Noise Extrapolation / Readout Error Mitigation).
2. **Dynamic VRP with Time Windows (VRPTW)**: Incorporate soft/hard delivery time windows $[a_i, b_i]$ for customer orders into the QUBO penalty matrix $H_C$.
3. **Hybrid RL Quantum Mixers**: Replace fixed X-mixer Hamiltonians $H_M = \sum X_i$ in QAOA with parameterized, reinforcement-learning driven domain-preserving mixers to restrict quantum evolution strictly within the feasible search subspace.
4. **Multi-Depot Dynamic Fleet Coordination**: Expand QPSO and QAOA formulations to handle multiple distribution hubs operating simultaneously across macro-urban SUMO city networks.
