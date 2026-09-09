# Technical Deep-Dive: Quantum-Behaved Particle Swarm Optimization (QPSO)

> **Precise Developer Specification & Internal Working of the QPSO Swarm Engine**  
> *Based on research paper: Herrera, Coelho, Steiner (Pesquisa Operacional 35(3), 2015 / pp. 1-20)*

---

## 1. Overview & Theoretical Quantum Foundation

Quantum-Behaved Particle Swarm Optimization (QPSO) is a quantum-inspired global optimization metaheuristic based on quantum mechanics wavefunctions rather than Newtonian classical mechanics. Formulated according to **Herrera et al. (2015)**, QPSO eliminates classical velocity vectors completely. Instead, particles move within a quantum delta-potential well centered at a local attractor point.

### Key Conceptual Differences from Classical PSO

| Feature | Classical PSO | QPSO (Herrera et al., 2015) |
| :--- | :--- | :--- |
| **Trajectory Model** | Deterministic Newtonian position & velocity updates | Stochastic quantum wavefunction probability density $|\psi(x,t)|^2$ |
| **Velocity Vector $\mathbf{v}_i$** | Explicitly tracked and bounded ($v_{\min} \le v \le v_{\max}$) | **None** (Eliminated; search space covered probabilistically) |
| **Global Search Capability** | Can trap in local minima if velocities decay | Guarantees global convergence in search space $\mathbb{R}^D$ |
| **Core Parameter** | Inertia weight $w$, acceleration coefficients $c_1, c_2$ | Contraction-Expansion coefficient $\alpha(t)$ ($1.0 \to 0.5$) |

---

## 2. Quantum Physics Derivation (Delta-Potential Well)

In QPSO, each particle $i$ exists in a 1D delta-potential well centered at attractor $p_{i,d}$. The particle's quantum state is governed by the time-independent Schrödinger equation:
$$\frac{d^2 \psi(x)}{dx^2} + \frac{2m}{\hbar^2} \left[ E + \gamma \delta(x - p_{i,d}) \right] \psi(x) = 0$$

Solving for wavefunction $\psi(x)$ yields an exponential probability density distribution:
$$Q(x) = |\psi(x)|^2 = \frac{1}{L} \exp\left( -\frac{2|x - p_{i,d}|}{L} \right)$$

where $L$ is the characteristic length of the potential field:
$$L = 2 \cdot \alpha(t) \cdot |mbest_d - x_{i,d}(t)|$$

Using the inverse transform sampling method ($u \sim U(0,1)$), integrating probability density $Q(x)$ yields the exact position collapse update equation without velocity.

---

## 3. Mathematical Equations & Swarm Update Pipeline

```
                               +-----------------------------------+
                               |  Initialize Swarm M x D in [-2, 2]|
                               |  Set pbest_i = x_i, Evaluate fit  |
                               +-----------------------------------+
                                                 |
                                                 v
                               +-----------------------------------+
                               |  Calculate mbest_d (Eq. 11)       |
                               |  mbest_d = (1/M) * sum pbest_{i,d}|
                               +-----------------------------------+
                                                 |
                                                 v
                               +-----------------------------------+
                               |  Update Alpha(t) Decay (Sec 4)    |
                               |  alpha(t) = 1.0 -> 0.5            |
                               +-----------------------------------+
                                                 |
                                                 v
                               +-----------------------------------+
                               |  For each particle i & dim d:     |
                               |   1. Compute LIP p_{i,d}          |
                               |   2. Generate u ~ U(0, 1)         |
                               |   3. Position Wave Collapse Update|
                               +-----------------------------------+
                                                 |
                                                 v
                               +-----------------------------------+
                               |  Apply Rank Discretization (SPV)  |
                               |  Sort x_i -> Discrete Node Tour pi|
                               +-----------------------------------+
                                                 |
                                                 v
                               +-----------------------------------+
                               |  Evaluate Dynamic SUMO Cost &     |
                               |  Update pbest_i and gbest         |
                               +-----------------------------------+
```

### 3.1 Mean-Best Position $mbest$ (Paper Eq. 11)
The mean-best position $\mathbf{mbest} \in \mathbb{R}^D$ represents the center of mass of personal best positions across all $M$ particles in the swarm:
$$mbest_d = \frac{1}{M} \sum_{i=1}^{M} pbest_{i,d}, \quad \forall d \in \{1, 2, \dots, D\}$$

### 3.2 Learning Inclination Point (LIP) $p_{i,d}$ (Algorithm 1)
Each particle is drawn toward a local attractor point $p_{i,d}$ combining its personal best $pbest_{i,d}$ and the swarm global best $gbest_d$:
$$p_{i,d} = \frac{\varphi_1 \cdot pbest_{i,d} + \varphi_2 \cdot gbest_d}{\varphi_1 + \varphi_2}, \quad \varphi_1, \varphi_2 \sim U(0, 1)$$

### 3.3 Linear Contraction-Expansion Decay $\alpha(t)$ (Paper Sec 4)
The parameter $\alpha(t)$ controls convergence speed and exploration range. It decays linearly over maximum iterations $T_{\max}$:
$$\alpha(t) = \alpha_{\text{start}} - \left( \frac{t}{T_{\max} - 1} \right) \cdot (\alpha_{\text{start}} - \alpha_{\text{end}})$$

where $\alpha_{\text{start}} = 1.0$ (high exploration) down to $\alpha_{\text{end}} = 0.5$ (fine-tuned convergence).

### 3.4 Quantum Position Wave Collapse Update Equation (Paper Eq. 13)
The continuous coordinate $x_{i,d}(t+1)$ collapses probabilistically based on uniform random sample $u \sim U(0,1)$:
$$x_{i,d}(t+1) = \begin{cases} p_{i,d} - \alpha(t) \cdot |mbest_d - x_{i,d}(t)| \cdot \ln\left(\frac{1}{u}\right) & \text{if } r > 0.5 \\ p_{i,d} + \alpha(t) \cdot |mbest_d - x_{i,d}(t)| \cdot \ln\left(\frac{1}{u}\right) & \text{if } r \le 0.5 \end{cases}$$

where $r \sim U(0,1)$.

---

## 4. Rank Discretization Rule (Small-Position-Value / SPV)

Because road routing involves discrete node permutations $\pi = \langle v_0, v_1, \dots, v_k \rangle$, continuous particle coordinates $\mathbf{x}_i \in \mathbb{R}^D$ are mapped onto discrete tours using the **Rank Discretization Rule** (Herrera et al. 2015, Sec 3.3, pp. 14-15):

1. **Fixed Endpoints**: Depot Node $0$ is fixed at position index $0$, and Destination Node $D$ is fixed at the terminal position index $D-1$.
2. **Intermediate Ranking**: Continuous values $\{x_{i,1}, x_{i,2}, \dots, x_{i,D-2}\}$ for intermediate candidate nodes are extracted.
3. **Ascending Sort Order**: Sorting the continuous vector in ascending order defines the sequence of visit for candidate nodes:
   $$\text{Rank}(x_{i,d_1}) < \text{Rank}(x_{i,d_2}) \implies \text{Node } d_1 \text{ visited before Node } d_2$$

---

## 5. Dynamic SUMO Fitness Function Evaluation

For a candidate discrete node sequence $\pi = \langle s = v_0, v_1, v_2, \dots, v_k = t \rangle$, fitness $f(\mathbf{x}_i)$ is computed dynamically from real-time SUMO edge weights $w_{u,v}(t)$:

$$f(\mathbf{x}_i) = \sum_{j=0}^{k-1} w_{v_j, v_{j+1}}(t) + \mathcal{P}_{\text{disconnected}}$$

where $\mathcal{P}_{\text{disconnected}} = 1000.0$ if no direct edge exists between consecutive nodes $v_j$ and $v_{j+1}$ on SUMO network $G(t)$.

---

## 6. Developer Code Mapping

In [`backend/routing/qpso_router.py`](file:///c:/SIH_Traffic_Project/2026-09-07-14-34-19/backend/routing/qpso_router.py):
* `find_route(...)` (Lines 57-212): Primary solver iteration loop.
* `x = rng.uniform(-2.0, 2.0, size=(M, D))` (Line 95): Continuous swarm initialization.
* `mbest = np.mean(pbest, axis=0)` (Line 114): Computes mean best position across population $M$.
* `p_id = (fi1 * pbest[i, d] + fi2 * gbest[d]) / denom` (Line 127): Calculates Learning Inclination Point (LIP).
* `x[i, d] = p_id +/- alpha_t * diff * ln_u` (Lines 135-137): Quantum wave collapse position update (Eq. 13).
* `_discretize_to_node_tour(...)` (Lines 246-268): Implements Small-Position-Value (SPV) rank discretization rule.
