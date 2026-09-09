# Technical Deep-Dive: Link-Based QAOA Vehicle Routing Solver

> **Precise Developer Specification & Internal Quantum Mathematical Pipeline**  
> *Based on research paper: Azfar, Raisuddin, Ke, Holguín-Veras (ACM Trans. Quantum Comput., 2025 / arXiv:2505.01614)*

---

## 1. Overview & Theoretical Foundation

The Quantum Approximate Optimization Algorithm (QAOA) is a hybrid quantum-classical algorithm designed to find approximate solutions to combinatorial optimization problems. In this system, QAOA is implemented strictly following **Azfar et al. (2025)** to solve the link-based Vehicle Routing Problem (VRP) on dynamic SUMO traffic graphs $G(t)$.

### Core Pipeline Architecture (Paper Fig. 1)

```
  +-------------------------------------------------------------------------+
  |  1. Sub-Graph Extraction: Local VRP links (i,j) around Depot & Customers |
  +-------------------------------------------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  2. QUBO Matrix Formulation with Flow & Customer Visit Constraints      |
  +-------------------------------------------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  3. Penalty Scaling P = 2 * sum(|w_{i,j}|) & Hamiltonian Normalization |
  +-------------------------------------------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  4. QUBO -> Pauli-Z Ising Cost Hamiltonian Transformation x_i=(I-Z_i)/2 |
  +-------------------------------------------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  5. Qiskit QAOA Circuit Synthesis |psi(gamma, beta)> (p Trotter layers)|
  +-------------------------------------------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  6. Hybrid Loop: COBYLA Classical Optimization of <psi|H_C|psi>         |
  +-------------------------------------------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |  7. Bitstring Measurement Sampling & Feasible Route Decoding            |
  +-------------------------------------------------------------------------+
```

---

## 2. Link-Based Binary Program & QUBO Formulation

### 2.1 Binary Decision Variables
Unlike node-sequencing formulations, link-based VRP defines a binary decision variable $x_{i,j} \in \{0, 1\}$ for each directed link $(i,j)$ in the reduced sub-graph:
$$x_{i,j} = \begin{cases} 1 & \text{if vehicle travels on directed link } (i,j) \\ 0 & \text{otherwise} \end{cases}$$

For $N$ directed links in the sub-graph, the problem maps onto $N$ qubits.

### 2.2 Dynamic Objective Cost Function
The objective is to minimize total dynamic travel time extracted live from SUMO:
$$\text{Cost} = \sum_{(i,j)} w_{i,j}(t) x_{i,j}$$

### 2.3 Constraint Penalties (Paper Eq. 10 & 11)

1. **Customer Visit Constraints**: Each customer node $v \in \{D_1, D_2\}$ must have exactly 1 incoming link and 1 outgoing link:
   $$\mathcal{P}_{\text{visit}} = P \sum_{v \in \text{Customers}} \left[ \left(1 - \sum_{j} x_{v,j}\right)^2 + \left(1 - \sum_{i} x_{i,v}\right)^2 \right]$$

2. **Depot Vehicle Fleet Constraints**: Exactly $k = 2$ vehicles depart and return to Depot Node $0$:
   $$\mathcal{P}_{\text{depot}} = P \left( k - \sum_{j} x_{0,j} \right)^2 + P \left( k - \sum_{i} x_{i,0} \right)^2$$

3. **Flow Conservation Constraints**: For any intermediate node $i$, inflow must equal outflow:
   $$\mathcal{P}_{\text{flow}} = P \sum_{i} \left( \sum_{j} x_{i,j} - \sum_{j} x_{j,i} \right)^2$$

4. **Subtour Elimination**: Penalizes 2-node immediate loops between customer nodes:
   $$\mathcal{P}_{\text{subtour}} = 2P \sum_{i,j} x_{i,j} x_{j,i}$$

### 2.4 Penalty Scaling & Normalization (Paper Sec 4.5)
To ensure constraint violations always yield higher energy than any feasible path, the penalty multiplier $P$ is scaled dynamically:
$$P = 2 \cdot \sum_{(i,j)} |w_{i,j}(t)|$$

The QUBO matrix $Q_{\text{sym}}$ is normalized by its maximum absolute coefficient $M_{\max} = \max(|Q_{i,j}|)$ to maintain numerical stability during quantum parameter optimization:
$$Q_{\text{norm}} = \frac{Q_{\text{sym}}}{M_{\max}}$$

---

## 3. Mapping QUBO to Pauli-$Z$ Ising Cost Hamiltonian

Each binary variable $x_i \in \{0, 1\}$ is transformed into Pauli-$Z$ spin operator $Z_i \in \{+1, -1\}$ via isomorphic mapping:
$$x_i \mapsto \frac{I - Z_i}{2}$$

Substituting this transformation into $H_{\text{QUBO}} = x^T Q x + c^T x$ yields the Ising Cost Hamiltonian $H_C$:
$$H_C = c_0 I + \sum_{i=0}^{n-1} h_i Z_i + \sum_{0 \le i < j < n} J_{i,j} Z_i Z_j$$

where:
* Linear field coefficients: $h_i = \frac{c_i}{2} + \frac{Q_{i,i}}{4} + \sum_{j \neq i} \frac{Q_{i,j} + Q_{j,i}}{4}$
* Two-qubit coupling coefficients: $J_{i,j} = \frac{Q_{i,j} + Q_{j,i}}{4}$

---

## 4. Qiskit QAOA Circuit Synthesis & Variational Loop

### 4.1 Quantum State Initialization
The circuit begins in an equal superposition over all $2^n$ basis states using Hadamard gates:
$$|\psi_0\rangle = H^{\otimes n} |0\rangle^{\otimes n} = \frac{1}{\sqrt{2^n}} \sum_{x \in \{0,1\}^n} |x\rangle$$

### 4.2 Parameterized Unitary Ansatz $|\psi(\boldsymbol{\gamma}, \boldsymbol{\beta})\rangle$
For $p$ layers (depth $p=1$), the state is evolved under alternating cost and mixer Hamiltonians:
$$|\psi(\boldsymbol{\gamma}, \boldsymbol{\beta})\rangle = \prod_{l=1}^{p} e^{-i \beta_l H_M} e^{-i \gamma_l H_C} |\psi_0\rangle$$

1. **Cost Unitary $e^{-i \gamma_l H_C}$**:
   * Single-qubit phase rotation $R_z(2 \gamma h_i)$ for linear terms $h_i Z_i$.
   * Two-qubit entangling block $\text{CNOT}(i,j) \to R_z(2 \gamma J_{i,j}) \to \text{CNOT}(i,j)$ for coupling terms $J_{i,j} Z_i Z_j$.
2. **Mixer Unitary $e^{-i \beta_l H_M}$**:
   * Transverse-field mixer $H_M = \sum_{i=0}^{n-1} X_i$ implemented using single-qubit $R_x(2 \beta_l)$ gates across all qubits.

### 4.3 COBYLA Variational Loop
The classical optimizer COBYLA (`scipy.optimize.minimize`) updates variational angles $(\boldsymbol{\gamma}, \boldsymbol{\beta})$ to minimize expectation value $E(\boldsymbol{\gamma}, \boldsymbol{\beta})$:
$$E(\boldsymbol{\gamma}, \boldsymbol{\beta}) = \langle \psi(\boldsymbol{\gamma}, \boldsymbol{\beta}) | H_C | \psi(\boldsymbol{\gamma}, \boldsymbol{\beta}) \rangle = \sum_{x \in \{0,1\}^n} P(x) \cdot E_{\text{QUBO}}(x)$$

---

## 5. Measurement Sampling & Feasible Route Decoding

1. **Probability Distribution**: Computes statevector probabilities $P(x) = |\langle x | \psi(\boldsymbol{\gamma}, \boldsymbol{\beta}) \rangle|^2$.
2. **Bitstring Ranking**: Sorts bitstrings by measurement probability in descending order.
3. **Feasibility Filtering**:
   * Iterates through top bitstrings $x = (x_0, x_1, \dots, x_{n-1})$.
   * Decodes active links where $x_k = 1$.
   * Checks adjacency graph for contiguous depot-to-customer round-trip paths free of disconnected subtours.
4. **Metric Extraction**: Computes exact dynamic travel times on SUMO graph for the decoded feasible route.

---

## 6. Developer Code Mapping

In [`backend/routing/qaoa_router.py`](file:///c:/SIH_Traffic_Project/2026-09-07-14-34-19/backend/routing/qaoa_router.py):
* `find_route(...)` (Lines 60-231): Primary solver pipeline.
* `_build_vrp_qubo(...)` (Lines 315-395): Builds $Q$ matrix, applies $P = 2 \sum |w_{i,j}|$, and enforces flow/fleet constraints.
* `_qubo_to_ising(...)` (Lines 396-422): Converts QUBO to $h_i$ and $J_{i,j}$ Ising parameters.
* `_synthesize_qaoa_circuit(...)` (Lines 483-520): Constructs Qiskit quantum circuit with $R_z$, $\text{CNOT}$, and $R_x$ gates.
* `_optimize_qaoa_parameters(...)` (Lines 438-482): COBYLA optimization loop.
* `_decode_bitstring_to_tour(...)` (Lines 521-569): Decodes measurement bitstrings into valid road tours.
