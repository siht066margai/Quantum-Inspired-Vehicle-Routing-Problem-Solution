// SIH 2026 Traffic Route Optimization Visualizer & Control Application

class TrafficApp {
    constructor() {
        this.networkData = null;
        this.ws = null;
        this.statePollTimer = null;
        this.isPollingState = false;
        this.canvas = document.getElementById('traffic-map');
        this.ctx = this.canvas.getContext('2d');

        // Viewport transform (pan & zoom)
        this.zoom = 1.0;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;

        // Interaction state
        this.pickMode = null; // 'origin' | 'c1' | 'c2' | 'c3' | ... | null
        this.selectedOrigin = null;
        this.customerCount = 2; // Default 2 customer destinations (supports 1..5)
        this.selectedCustomers = [];
        this.hoveredItem = null;

        // Live simulation state
        this.simRunning = false;
        this.simPaused = false;
        this.simTime = 0.0;
        this.vehicles = [];
        this.congestedEdges = new Map(); // edge_id -> info
        this.activeRoute = null;
        this.activeIncidents = [];
        this.dijkstraResult = null;
        this.qaoaResult = null;
        this.qpsoResult = null;
        this.analysisVisible = false;
        this.analysisData = null;

        this.initUI();
        this.fetchNetworkData();
        this.connectWebSocket();
    }

    initUI() {
        // Window resize
        window.addEventListener('resize', () => this.resizeCanvas());
        this.resizeCanvas();

        // Control buttons
        document.getElementById('btn-start').addEventListener('click', () => this.sendSimCmd('start'));
        document.getElementById('btn-pause').addEventListener('click', () => this.sendSimCmd('pause'));
        document.getElementById('btn-step').addEventListener('click', () => this.sendSimCmd('step'));
        document.getElementById('btn-stop').addEventListener('click', () => this.sendSimCmd('stop'));

        // Customer controls
        this.renderCustomerControls();
        const btnAdd = document.getElementById('btn-add-customer');
        if (btnAdd) btnAdd.addEventListener('click', () => this.addCustomer());
        const btnRemove = document.getElementById('btn-remove-customer');
        if (btnRemove) btnRemove.addEventListener('click', () => this.removeCustomer());

        // Pick buttons in toolbar
        document.getElementById('btn-pick-origin').addEventListener('click', (e) => this.togglePickMode('origin', e.currentTarget));
        const btnPickCust = document.getElementById('btn-pick-customer');
        if (btnPickCust) btnPickCust.addEventListener('click', (e) => this.togglePickMode('c1', e.currentTarget));
        document.getElementById('btn-reset-view').addEventListener('click', () => this.fitBounds());

        // Route calc
        document.getElementById('btn-calc-route').addEventListener('click', () => this.calculateRoute());
        document.getElementById('btn-qaoa-route').addEventListener('click', () => this.calculateQaoaRoute());
        document.getElementById('btn-qpso-route').addEventListener('click', () => this.calculateQpsoRoute());
        document.getElementById('btn-compare-route').addEventListener('click', () => this.compareRoutes());
        document.getElementById('btn-open-analysis').addEventListener('click', () => this.openAnalysisWorkspace());
        document.getElementById('btn-close-analysis').addEventListener('click', () => this.closeAnalysisWorkspace());
        document.querySelectorAll('.analysis-tab').forEach(button => {
            button.addEventListener('click', () => this.activateAnalysisTab(button.dataset.analysisTab));
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') this.closeAnalysisWorkspace();
        });

        // Incident buttons
        document.getElementById('btn-inject-incident').addEventListener('click', () => this.injectIncident());
        document.getElementById('btn-clear-incident').addEventListener('click', () => this.clearIncident());

        // Canvas Pan / Zoom / Click
        this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvas.addEventListener('mouseup', () => this.onMouseUp());
        this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
    }

    renderCustomerControls() {
        const container = document.getElementById('customer-selects-container');
        if (!container) return;
        container.innerHTML = '';

        for (let i = 1; i <= this.customerCount; i++) {
            const div = document.createElement('div');
            div.className = 'form-group customer-group';
            div.setAttribute('data-dest-index', i);
            div.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <label for="dest${i}-select" style="margin: 0;">Customer ${i} (C${i}):</label>
                    <button type="button" class="btn btn-outline btn-sm btn-pick-cust" data-cust-index="${i}" style="padding: 1px 6px; font-size: 10px;">📍 Pick C${i}</button>
                </div>
                <select id="dest${i}-select" class="form-control customer-select"></select>
            `;
            container.appendChild(div);
        }

        // Attach click handlers to customer pick buttons
        container.querySelectorAll('.btn-pick-cust').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.dataset.custIndex, 10);
                this.togglePickMode(`c${idx}`, e.currentTarget);
            });
        });

        // Update VRP badge
        const badge = document.getElementById('vrp-scenario-badge');
        if (badge) {
            badge.innerText = `1 Source + ${this.customerCount} Customers`;
        }
    }

    addCustomer() {
        if (this.customerCount < 5) {
            this.customerCount++;
            this.renderCustomerControls();
            this.populateSelects();
            this.requestRender();
        }
    }

    removeCustomer() {
        if (this.customerCount > 1) {
            this.customerCount--;
            this.renderCustomerControls();
            this.populateSelects();
            this.requestRender();
        }
    }

    resizeCanvas() {
        const viewport = this.canvas.parentElement;
        this.canvas.width = viewport.clientWidth;
        this.canvas.height = viewport.clientHeight;
        this.requestRender();
    }

    async fetchNetworkData() {
        try {
            const res = await fetch('/api/network');
            this.networkData = await res.json();
            this.populateSelects();
            this.fitBounds();
        } catch (err) {
            console.error("Error fetching network data:", err);
        }
    }

    populateSelects() {
        if (!this.networkData) return;

        const originSelect = document.getElementById('origin-select');
        const edgeSelect = document.getElementById('incident-edge-select');

        if (originSelect) originSelect.innerHTML = '';
        if (edgeSelect) edgeSelect.innerHTML = '';

        const nodeKeys = Object.keys(this.networkData.nodes);
        nodeKeys.sort();

        nodeKeys.forEach((nid) => {
            if (originSelect) originSelect.add(new Option(`Junction ${nid}`, nid));
        });

        const defaultCustomerIndices = [5, 12, 18, 25, 30];

        for (let i = 1; i <= this.customerCount; i++) {
            const destSelect = document.getElementById(`dest${i}-select`);
            if (!destSelect) continue;
            const currentVal = destSelect.value;
            destSelect.innerHTML = '';
            nodeKeys.forEach((nid) => {
                destSelect.add(new Option(`Junction ${nid}`, nid));
            });

            if (currentVal && nodeKeys.includes(currentVal)) {
                destSelect.value = currentVal;
            } else if (nodeKeys.length > 0) {
                const defIdx = defaultCustomerIndices[i - 1] || Math.min(i * 5, nodeKeys.length - 1);
                destSelect.selectedIndex = Math.min(defIdx, nodeKeys.length - 1);
            }
        }

        if (nodeKeys.length > 0 && originSelect && !this.selectedOrigin) {
            originSelect.selectedIndex = 0;
            this.selectedOrigin = originSelect.value;
        }

        if (this.networkData.edges && edgeSelect) {
            this.networkData.edges.forEach(edge => {
                const opt = new Option(`Road ${edge.id} (${Math.round(edge.length)}m)`, edge.id);
                edgeSelect.add(opt);
            });
        }

        this.updateSelectedCustomers();
    }

    updateSelectedCustomers() {
        this.selectedCustomers = [];
        for (let i = 1; i <= this.customerCount; i++) {
            const el = document.getElementById(`dest${i}-select`);
            this.selectedCustomers.push(el ? el.value : null);
        }
    }

    fitBounds() {
        if (!this.networkData || !this.networkData.bounds) return;
        const b = this.networkData.bounds;
        const width = b.max_x - b.min_x;
        const height = b.max_y - b.min_y;

        const scaleX = (this.canvas.width - 80) / width;
        const scaleY = (this.canvas.height - 80) / height;

        this.zoom = Math.min(scaleX, scaleY);
        this.panX = 40 - b.min_x * this.zoom;
        this.panY = this.canvas.height - 40 + b.min_y * this.zoom; // flip Y for standard cartesian
        this.requestRender();
    }

    worldToScreen(x, y) {
        const screenX = x * this.zoom + this.panX;
        const screenY = this.panY - y * this.zoom;
        return { x: screenX, y: screenY };
    }

    screenToWorld(sx, sy) {
        const wx = (sx - this.panX) / this.zoom;
        const wy = (this.panY - sy) / this.zoom;
        return { x: wx, y: wy };
    }

    connectWebSocket() {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.stopStatePolling();
            document.getElementById('ws-indicator').className = 'dot online';
            document.getElementById('ws-status-text').innerText = 'Connected';
        };

        this.ws.onclose = () => {
            document.getElementById('ws-indicator').className = 'dot offline';
            document.getElementById('ws-status-text').innerText = 'Disconnected';
            this.startStatePolling();
            setTimeout(() => this.connectWebSocket(), 3000);
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'sim_update') {
                    this.onSimUpdate(msg);
                }
            } catch (e) {
                console.error("Error parsing WS msg:", e);
            }
        };
    }

    startStatePolling() {
        if (this.statePollTimer) return;
        this.fetchSimState();
        this.statePollTimer = setInterval(() => this.fetchSimState(), 500);
    }

    stopStatePolling() {
        if (!this.statePollTimer) return;
        clearInterval(this.statePollTimer);
        this.statePollTimer = null;
    }

    async fetchSimState() {
        if (this.isPollingState) return;
        this.isPollingState = true;
        try {
            const response = await fetch('/api/sim/state');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            this.onSimUpdate(await response.json());
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                document.getElementById('ws-indicator').className = 'dot online';
                document.getElementById('ws-status-text').innerText = 'HTTP fallback';
            }
        } catch (error) {
            console.warn('Live-state fallback unavailable:', error);
        } finally {
            this.isPollingState = false;
        }
    }

    sendSimCmd(cmd) {
        fetch(`/api/sim/${cmd}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (cmd === 'start') {
                    this.simRunning = true;
                    this.simPaused = false;
                } else if (cmd === 'pause') {
                    this.simPaused = !this.simPaused;
                } else if (cmd === 'stop') {
                    this.simRunning = false;
                    this.simPaused = false;
                }
                this.updateSimStatusUI();
            });
    }

    updateSimStatusUI() {
        const ind = document.getElementById('sim-indicator');
        const txt = document.getElementById('sim-status-text');

        document.getElementById('btn-start').disabled = this.simRunning && !this.simPaused;
        document.getElementById('btn-pause').disabled = !this.simRunning;
        document.getElementById('btn-step').disabled = !this.simRunning || !this.simPaused;
        document.getElementById('btn-stop').disabled = !this.simRunning;

        if (this.simRunning) {
            if (this.simPaused) {
                ind.className = 'dot offline';
                txt.innerText = 'SUMO Paused';
            } else {
                ind.className = 'dot running';
                txt.innerText = 'SUMO Simulating';
            }
        } else {
            ind.className = 'dot stopped';
            txt.innerText = 'SUMO Idle';
        }
    }

    onSimUpdate(msg) {
        this.simRunning = msg.running !== false;
        this.simPaused = Boolean(msg.paused);
        this.updateSimStatusUI();

        this.simTime = msg.sim_time;
        document.getElementById('sim-clock').innerText = `${this.simTime.toFixed(1)}s`;

        this.vehicles = msg.vehicles || [];

        // Update congested edges map
        this.congestedEdges.clear();
        (msg.congested_edges || []).forEach(e => {
            this.congestedEdges.set(e.id, e);
        });

        this.activeIncidents = msg.active_incidents || [];
        if (msg.active_route) {
            this.activeRoute = msg.active_route;
            this.updateRouteResultsUI(msg.active_route);
            if (this.analysisVisible && (msg.active_route.analysis || msg.active_route.dijkstra)) {
                this.renderAnalysisWorkspace(msg.active_route);
            }
        }

        // Live stats UI
        document.getElementById('stat-active').innerText = msg.active_vehicles || 0;
        document.getElementById('stat-arrived').innerText = msg.arrived_vehicles || 0;
        document.getElementById('stat-congested').innerText = this.congestedEdges.size;
        document.getElementById('stat-incidents').innerText = this.activeIncidents.length;

        this.updateIncidentsListUI();
        this.updateCausalChainUI();
        this.requestRender();
    }

    updateCausalChainUI() {
        const hasIncidents = this.activeIncidents.length > 0;
        const hasCongestion = this.congestedEdges.size > 0;
        const hasRoute = !!this.activeRoute;

        document.getElementById('step-1').className = `chain-step ${this.simRunning ? 'active' : ''}`;
        document.getElementById('step-2').className = `chain-step ${hasCongestion || hasIncidents ? 'active' : ''}`;
        document.getElementById('step-3').className = `chain-step ${hasCongestion || hasIncidents ? 'active' : ''}`;
        document.getElementById('step-4').className = `chain-step ${hasRoute ? 'active' : ''}`;
    }

    togglePickMode(mode, btn) {
        if (this.pickMode === mode) {
            this.pickMode = null;
            if (btn) btn.classList.remove('active');
        } else {
            document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
            this.pickMode = mode;
            if (btn) btn.classList.add('active');
        }
    }

    getVRPRequest() {
        const origin = document.getElementById('origin-select')?.value;
        const destinations = [];

        for (let i = 1; i <= this.customerCount; i++) {
            const el = document.getElementById(`dest${i}-select`);
            const val = el ? el.value : null;
            if (val && !destinations.includes(val)) {
                destinations.push(val);
            }
        }

        if (!origin || destinations.length === 0) return null;

        this.selectedOrigin = origin;
        this.selectedCustomers = destinations;

        return {
            origin_node: origin,
            destination_nodes: destinations
        };
    }

    calculateRoute() {
        const req = this.getVRPRequest();
        if (!req) return;
        this.analysisVisible = false;

        this.postJson('/api/vrp/dijkstra', req)
        .then(data => {
            if (data.success) {
                this.dijkstraResult = data;
                this.qaoaResult = null;
                this.activeRoute = data;
                this.updateRouteResultsUI(data);
                this.clearAnalysisWorkspace();
                this.requestRender();
            } else {
                alert(`VRP Error: ${data.error}`);
            }
        })
        .catch(err => alert(`VRP Error: ${err.message}`));
    }

    calculateQaoaRoute() {
        const req = this.getVRPRequest();
        if (!req) return;

        this.postJson('/api/vrp/qaoa', { ...req, reps: 1, shots: 1024 })
        .then(data => {
            if (data.success) {
                this.qaoaResult = data;
                this.activeRoute = data;
                this.clearAnalysisWorkspace();
                this.updateRouteResultsUI(data);
                this.requestRender();
            } else {
                alert(`QAOA VRP Error: ${data.error}`);
            }
        })
        .catch(err => alert(`QAOA VRP Error: ${err.message}`));
    }

    calculateQpsoRoute() {
        const req = this.getVRPRequest();
        if (!req) return;

        this.postJson('/api/vrp/qpso', { ...req, num_particles: 40, max_iter: 50 })
        .then(data => {
            if (data.success) {
                this.qpsoResult = data;
                this.activeRoute = data;
                this.clearAnalysisWorkspace();
                this.updateRouteResultsUI(data);
                this.requestRender();
            } else {
                alert(`QPSO VRP Error: ${data.error}`);
            }
        })
        .catch(err => alert(`QPSO VRP Error: ${err.message}`));
    }

    async compareRoutes() {
        const req = this.getVRPRequest();
        if (!req) return;

        const button = document.getElementById('btn-compare-route');
        button.disabled = true;
        button.innerText = '⚡ Running 3-Algorithm VRP Solvers...';

        try {
            const result = await this.postJson('/api/vrp/compare', { ...req, reps: 1, shots: 1024, num_particles: 40, max_iter: 50 });
            this.dijkstraResult = result.dijkstra;
            this.qaoaResult = result.qaoa;
            this.qpsoResult = result.qpso;

            const selectedRoute = result.qpso?.success ? result.qpso : (result.qaoa?.success ? result.qaoa : result.dijkstra);
            if (selectedRoute && selectedRoute.success) {
                this.activeRoute = selectedRoute;
                this.updateRouteResultsUI(selectedRoute);
                this.renderAnalysisWorkspace(result);
                this.analysisVisible = true;
                document.getElementById('route-results').classList.add('hidden');
                document.getElementById('btn-open-analysis').classList.remove('hidden');
                this.openAnalysisWorkspace();
                this.requestRender();
            } else {
                alert(`VRP Routing Error: ${result.error || 'No feasible route found'}`);
            }
        } catch (err) {
            alert(`Unable to run 3-algorithm VRP comparison: ${err.message}`);
        } finally {
            button.disabled = false;
            button.innerText = 'Run 3-Algorithm VRP Comparison';
        }
    }

    async postJson(url, body) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Request failed');
        return data;
    }

    updateRouteResultsUI(res) {
        if (!res || !res.success) return;
        const el = document.getElementById('route-results');
        if (!this.analysisVisible) el.classList.remove('hidden');

        const visitSeqStr = Array.isArray(res.visit_sequence) ? res.visit_sequence.join(' → ') : 'O → C1 → C2';
        const snapTime = res.snapshot_timestamp !== undefined ? res.snapshot_timestamp : (res.problem?.timestamp !== undefined ? res.problem.timestamp : this.simTime);

        document.getElementById('r-status').innerText = res.algorithm;
        const snapEl = document.getElementById('r-timestamp');
        if (snapEl) snapEl.innerText = `t = ${snapTime.toFixed(1)} s`;

        const rSeq = document.getElementById('r-sequence');
        if (rSeq) rSeq.innerText = visitSeqStr;
        document.getElementById('r-tt').innerText = `${res.total_travel_time} s`;
        document.getElementById('r-dist').innerText = `${res.total_distance} m`;
        document.getElementById('r-speed').innerText = `${res.average_speed_ms} m/s`;
        document.getElementById('r-comp').innerText = `${res.computation_time_ms} ms`;
        document.getElementById('r-bottlenecks').innerText = res.bottleneck_count;
    }

    renderAnalysisWorkspace(data) {
        this.analysisData = data;
        const analysis = data.analysis || {};
        const outcome = analysis.outcome || {};
        const dijkstra = analysis.algorithms?.dijkstra || data.dijkstra || {};
        const qaoa = analysis.algorithms?.qaoa || data.qaoa || {};
        const qpso = analysis.algorithms?.qpso || data.qpso || {};
        const dijkstraRaw = data.dijkstra || {};
        const qaoaRaw = data.qaoa || {};
        const qpsoRaw = data.qpso || {};

        const snapTime = data.snapshot_timestamp !== undefined ? data.snapshot_timestamp : (data.problem?.timestamp !== undefined ? data.problem.timestamp : this.simTime);
        this.setText('snapshot-time-val', `t = ${snapTime.toFixed(1)}s`);
        this.setText('sync-info-time', `t = ${snapTime.toFixed(1)}s`);

        const numCustomers = outcome.num_customers || data.problem?.destinations?.length || this.customerCount;
        const permsCount = outcome.permutation_count || (numCustomers === 2 ? 2 : (numCustomers === 3 ? 6 : (numCustomers === 4 ? 24 : 120)));
        this.setText('perms-count-badge', `${permsCount} Candidate Permutations (N=${numCustomers})`);

        const seqStr = dijkstraRaw.visit_sequence ? dijkstraRaw.visit_sequence.join(' → ') : (dijkstraRaw.origin_node ? `${dijkstraRaw.origin_node} → ${dijkstraRaw.destination_node}` : `VRP ${numCustomers}-Customer Scenario`);
        this.setText('analysis-route-label', `${seqStr} • Captured at t = ${snapTime.toFixed(1)}s`);
        this.setText('a-basis', analysis.comparison_basis || '');

        // Sequence row with baseline matching status badges
        const dSeq = dijkstraRaw.visit_sequence ? dijkstraRaw.visit_sequence.join(' → ') : '—';
        const qSeq = qaoaRaw.visit_sequence ? qaoaRaw.visit_sequence.join(' → ') : '—';
        const qpsoSeq = qpsoRaw.visit_sequence ? qpsoRaw.visit_sequence.join(' → ') : '—';

        const qMatched = outcome.qaoa_matched_baseline !== undefined ? outcome.qaoa_matched_baseline : (qSeq === dSeq && qaoaRaw.success);
        const qpsoMatched = outcome.qpso_matched_baseline !== undefined ? outcome.qpso_matched_baseline : (qpsoSeq === dSeq && qpsoRaw.success);

        const dSeqEl = document.getElementById('a-d-seq');
        if (dSeqEl) dSeqEl.innerHTML = `<strong>${dSeq}</strong> <span class="badge badge-info" style="font-size: 9px; margin-left: 4px;">Ground-Truth Baseline</span>`;

        const qSeqEl = document.getElementById('a-q-seq');
        if (qSeqEl) {
            qSeqEl.innerHTML = `<strong>${qSeq}</strong> ${qMatched ? '<span class="badge badge-success" style="font-size: 9px; margin-left: 4px;">✓ Matched Baseline</span>' : '<span class="badge badge-warning" style="font-size: 9px; margin-left: 4px;">Sub-optimal</span>'}`;
        }

        const qpsoSeqEl = document.getElementById('a-qpso-seq');
        if (qpsoSeqEl) {
            qpsoSeqEl.innerHTML = `<strong>${qpsoSeq}</strong> ${qpsoMatched ? '<span class="badge badge-success" style="font-size: 9px; margin-left: 4px;">✓ Matched Baseline</span>' : '<span class="badge badge-warning" style="font-size: 9px; margin-left: 4px;">Sub-optimal</span>'}`;
        }

        // Tab 1: Overview comparison table
        this.fillOverviewColumn('d', dijkstra);
        this.fillOverviewColumn('q', qaoa);
        this.fillOverviewColumn('qpso', qpso);

        // Tab 2: Dijkstra Proofs & Segment Calculations Table
        this.renderSegmentCalculationsTable('dijkstra-segments-body', dijkstraRaw.segment_calculations || []);

        // Tab 3: QAOA Details & Proofs
        const qaoaDetails = qaoaRaw.solver_details || qaoaRaw;
        this.setText('q-backend', qaoaDetails.execution_backend || 'Qiskit simulator');
        this.setText('q-circuit-size', qaoaRaw.success ? `${qaoaDetails.qaoa_qubits || 4} qubits • p = ${qaoaDetails.qaoa_depth || 1}` : 'No feasible QAOA result');
        this.setText('q-optimizer', qaoaDetails.optimizer || 'COBYLA');
        this.setText('q-evaluations', this.formatValue(qaoaDetails.optimizer_evaluations, 0));
        this.setText('q-penalty-val', this.formatValue(qaoaDetails.penalty_multiplier_P, 2));
        this.setText('q-norm-val', this.formatValue(qaoaDetails.normalization_factor, 4));
        this.setText('q-selection-summary', qaoaRaw.success
            ? `Selected bitstring ${qaoaDetails.selected_feasible_bitstring || '0101'} with ${(Number(qaoaDetails.selected_probability || 0) * 100).toFixed(2)}% probability.`
            : 'No feasible QAOA sample was returned.');
        this.renderSampleCounts(qaoaDetails.sample_counts || {});
        this.renderQaoaQubitsTable(qaoaDetails.qubo_details);
        this.renderSegmentCalculationsTable('qaoa-segments-body', qaoaRaw.segment_calculations || []);

        // Tab 4: QPSO Swarm Details & Proofs
        const qpsoDetails = qpsoRaw.solver_details || qpsoRaw;
        this.setText('qpso-particles-val', qpsoDetails.particles_M || qpsoRaw.qpso_particles || 40);
        this.setText('qpso-iterations-val', qpsoDetails.iterations_T || qpsoRaw.qpso_iterations || 50);
        this.setText('qpso-dim-val', qpsoDetails.dimensions_D || numCustomers);
        this.setText('qpso-alpha-val', qpsoDetails.final_alpha || qpsoRaw.final_alpha || '-');
        this.renderQpsoRankTable(qpsoDetails);
        this.renderSegmentCalculationsTable('qpso-segments-body', qpsoRaw.segment_calculations || []);

        // Tab 5: Route Evidence Audit
        this.renderRouteEvidence('d', dijkstraRaw);
        this.renderRouteEvidence('q', qaoaRaw);
        this.renderRouteEvidence('qpso', qpsoRaw);

        // Trigger KaTeX math rendering
        this.renderKaTeX();
    }

    renderKaTeX() {
        if (window.renderMathInElement) {
            try {
                window.renderMathInElement(document.getElementById('analysis-workspace'), {
                    delimiters: [
                        { left: '$$', right: '$$', display: true },
                        { left: '\\(', right: '\\)', display: false },
                        { left: '$', right: '$', display: false }
                    ],
                    throwOnError: false
                });
            } catch (e) {
                console.warn("KaTeX rendering error:", e);
            }
        }
    }

    renderSegmentCalculationsTable(tableBodyId, segments) {
        const tbody = document.getElementById(tableBodyId);
        if (!tbody) return;
        tbody.replaceChildren();

        if (!Array.isArray(segments) || segments.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="none-text">No segment calculation data available.</td></tr>';
            return;
        }

        segments.forEach((seg, idx) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${idx + 1}</td>
                <td><strong>${seg.edge_id}</strong></td>
                <td>${seg.from_node}</td>
                <td>${seg.to_node}</td>
                <td>${seg.length_m} m</td>
                <td>${seg.speed_limit_ms} m/s</td>
                <td>${(seg.congestion_ratio * 100).toFixed(1)}%</td>
                <td>${seg.travel_time_s} s</td>
                <td>${seg.accumulated_distance_m} m</td>
                <td>${seg.accumulated_time_s} s</td>
            `;
            tbody.appendChild(tr);
        });
    }

    renderQaoaQubitsTable(quboDetails) {
        const tbody = document.getElementById('qaoa-qubits-body');
        if (!tbody) return;
        tbody.replaceChildren();

        const vars = quboDetails?.qubit_variables || quboDetails?.link_variables || [];
        if (vars.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="none-text">No QAOA decision variable data.</td></tr>';
            return;
        }

        const isingTerms = quboDetails?.ising_hamiltonian || [];
        const isingMap = new Map();
        isingTerms.forEach(item => {
            if (item.type === 'linear') {
                isingMap.set(item.qubit, item.term);
            }
        });

        vars.forEach(v => {
            const tr = document.createElement('tr');
            const isingTermStr = isingMap.get(v.var_index) || '-';
            const desc = v.description || `Link ${v.link}`;
            const sumoEdge = v.customer ? `Step ${v.position}` : `Road ${v.sumo_edge || '-'}`;
            const weightStr = v.weight !== undefined ? `${v.weight} s` : (v.customer ? `Cust ${v.customer}` : '-');
            tr.innerHTML = `
                <td>q_${v.var_index}</td>
                <td>${desc}</td>
                <td>${sumoEdge}</td>
                <td>${weightStr}</td>
                <td><code>${isingTermStr}</code></td>
            `;
            tbody.appendChild(tr);
        });
    }

    renderQpsoRankTable(swarmDetails) {
        const tbody = document.getElementById('qpso-rank-body');
        if (!tbody) return;
        tbody.replaceChildren();

        const rankTable = swarmDetails?.rank_discretization_table || [];
        if (rankTable.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="none-text">No QPSO particle data.</td></tr>';
            return;
        }

        rankTable.forEach(row => {
            const tr = document.createElement('tr');
            const custNode = row.customer_node || row.node;
            const roleText = row.visit_rank ? `Visit Rank ${row.visit_rank}` : (row.is_terminal ? (row.dimension_index === 0 ? 'Depot / Origin' : 'Destination') : 'Intermediate Node');
            tr.innerHTML = `
                <td>Dim ${row.dimension_index}</td>
                <td>Junction ${custNode}</td>
                <td>${row.gbest_value}</td>
                <td>${row.mbest_value}</td>
                <td>${roleText}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    fillOverviewColumn(prefix, result) {
        const isAvailable = result && (result.available !== undefined ? result.available : (result.success || result.feasible));
        if (!isAvailable) {
            this.setText(`a-${prefix}-cost`, '—');
            this.setText(`a-${prefix}-time`, '—');
            this.setText(`a-${prefix}-dist`, '—');
            this.setText(`a-${prefix}-speed`, '—');
            this.setText(`a-${prefix}-congestion`, '—');
            this.setText(`a-${prefix}-events`, '—');
            this.setText(`a-${prefix}-compute`, '—');
            return;
        }

        const cost = result.total_cost !== undefined ? result.total_cost : result.dynamic_cost;
        const timeSec = result.total_travel_time !== undefined ? result.total_travel_time : result.travel_time_seconds;
        const distM = result.total_distance !== undefined ? result.total_distance : result.distance_metres;
        const speed = result.average_speed_ms !== undefined ? result.average_speed_ms : 0;
        const bottlenecks = result.bottleneck_count !== undefined ? result.bottleneck_count : 0;
        const computeMs = result.computation_time_ms !== undefined ? result.computation_time_ms : 0;

        let avgCongestion = result.average_congestion_percent;
        if (avgCongestion === undefined && Array.isArray(result.segment_calculations) && result.segment_calculations.length > 0) {
            const sumCong = result.segment_calculations.reduce((acc, seg) => acc + (seg.congestion_ratio || 0), 0);
            avgCongestion = (sumCong / result.segment_calculations.length) * 100.0;
        }
        if (avgCongestion === undefined) avgCongestion = 0;

        const incidentCount = result.incident_edge_count !== undefined ? result.incident_edge_count : (result.bottlenecks ? result.bottlenecks.filter(b => b.is_incident).length : 0);

        this.setText(`a-${prefix}-cost`, this.formatValue(cost, 2));
        this.setText(`a-${prefix}-time`, `${this.formatValue(timeSec, 1)} s`);
        this.setText(`a-${prefix}-dist`, `${this.formatValue(distM, 0)} m`);
        this.setText(`a-${prefix}-speed`, `${this.formatValue(speed, 2)} m/s`);
        this.setText(`a-${prefix}-congestion`, `${this.formatValue(avgCongestion, 1)}%`);
        this.setText(`a-${prefix}-events`, `${bottlenecks} / ${incidentCount}`);
        this.setText(`a-${prefix}-compute`, `${this.formatValue(computeMs, 2)} ms`);
    }

    renderSampleCounts(counts) {
        const target = document.getElementById('q-samples');
        if (!target) return;
        target.replaceChildren();
        const rows = Object.entries(counts);
        const maxCount = Math.max(...rows.map(([, count]) => Number(count)), 1);
        if (!rows.length) {
            target.textContent = 'No sampled outcomes returned.';
            return;
        }
        rows.forEach(([bitstring, count]) => {
            const row = document.createElement('div');
            row.className = 'sample-row';
            const label = document.createElement('code');
            label.textContent = bitstring;
            const track = document.createElement('span');
            track.className = 'sample-track';
            const fill = document.createElement('span');
            fill.className = 'sample-fill';
            fill.style.width = `${(Number(count) / maxCount) * 100}%`;
            track.append(fill);
            const total = document.createElement('strong');
            total.textContent = `${count} shots`;
            row.append(label, track, total);
            target.append(row);
        });
    }

    renderRouteEvidence(prefix, result) {
        const edgePath = Array.isArray(result.edge_path) ? result.edge_path : [];
        const visitSeqStr = Array.isArray(result.visit_sequence) ? result.visit_sequence.join(' → ') : '';
        const dist = result.total_distance !== undefined ? result.total_distance : result.distance_metres;
        const timeSec = result.total_travel_time !== undefined ? result.total_travel_time : result.travel_time_seconds;

        this.setText(`${prefix}-route-summary`, result.success
            ? `${visitSeqStr ? visitSeqStr + ' • ' : ''}${edgePath.length} road segments • ${this.formatValue(dist, 0)} m • ${this.formatValue(timeSec, 1)} s`
            : (result.error || 'Route unavailable.'));
        const target = document.getElementById(`${prefix}-route-alerts`);
        if (!target) return;
        target.replaceChildren();
        const alerts = Array.isArray(result.bottlenecks) ? result.bottlenecks : [];
        if (!alerts.length) {
            target.textContent = 'No traffic alerts on this route.';
            return;
        }
        alerts.forEach(alert => {
            const item = document.createElement('span');
            item.className = alert.is_incident ? 'route-alert incident' : 'route-alert';
            item.textContent = `${alert.edge_id} • ${Math.round((alert.congestion_ratio || 0) * 100)}%${alert.is_incident ? ' • incident' : ''}`;
            target.append(item);
        });
    }

    activateAnalysisTab(tabName) {
        if (!tabName) return;
        document.querySelectorAll('.analysis-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.analysisTab === tabName);
        });
        document.querySelectorAll('.analysis-panel').forEach(panel => {
            panel.classList.toggle('active', panel.dataset.analysisPanel === tabName);
        });
        this.renderKaTeX();
    }

    openAnalysisWorkspace() {
        if (!this.analysisData) return;
        this.analysisVisible = true;
        document.getElementById('analysis-workspace').classList.remove('hidden');
        document.body.classList.add('analysis-open');
        this.activateAnalysisTab('overview');
    }

    closeAnalysisWorkspace() {
        this.analysisVisible = false;
        document.getElementById('analysis-workspace').classList.add('hidden');
        document.body.classList.remove('analysis-open');
        if (this.activeRoute) {
            document.getElementById('route-results').classList.remove('hidden');
        }
    }

    clearAnalysisWorkspace() {
        this.analysisVisible = false;
        this.analysisData = null;
        this.closeAnalysisWorkspace();
        document.getElementById('btn-open-analysis').classList.add('hidden');
    }

    setText(id, value) {
        const target = document.getElementById(id);
        if (target) target.textContent = value === undefined || value === null ? '—' : String(value);
    }

    formatValue(value, decimals = 2) {
        const number = Number(value);
        return Number.isFinite(number) ? number.toFixed(decimals) : '—';
    }

    injectIncident() {
        const edgeId = document.getElementById('incident-edge-select').value;
        if (!edgeId) return;

        fetch('/api/incident/inject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ edge_id: edgeId, speed_factor: 0.02 })
        })
        .then(res => res.json())
        .then(data => {
            if (data.updated_route) {
                this.activeRoute = data.updated_route;
                this.updateRouteResultsUI(data.updated_route);
                if (this.analysisVisible && (data.updated_route.analysis || data.updated_route.dijkstra)) {
                    this.renderAnalysisWorkspace(data.updated_route);
                }
            }
        });
    }

    clearIncident() {
        const edgeId = document.getElementById('incident-edge-select').value;
        if (!edgeId) return;

        fetch('/api/incident/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ edge_id: edgeId })
        })
        .then(res => res.json())
        .then(data => {
            if (data.updated_route) {
                this.activeRoute = data.updated_route;
                this.updateRouteResultsUI(data.updated_route);
                if (this.analysisVisible && (data.updated_route.analysis || data.updated_route.dijkstra)) {
                    this.renderAnalysisWorkspace(data.updated_route);
                }
            }
        });
    }

    updateIncidentsListUI() {
        const ul = document.getElementById('incidents-ul');
        if (this.activeIncidents.length === 0) {
            ul.innerHTML = '<li class="none-text">No active bottlenecks</li>';
            return;
        }

        ul.innerHTML = '';
        this.activeIncidents.forEach(edgeId => {
            const li = document.createElement('li');
            li.innerHTML = `<span>Road ${edgeId} (Blocked)</span>`;
            ul.appendChild(li);
        });
    }

    // Canvas Events
    onMouseDown(e) {
        if (e.button === 0) { // Left click
            const rect = this.canvas.getBoundingClientRect();
            const sx = e.clientX - rect.left;
            const sy = e.clientY - rect.top;

            if (this.pickMode) {
                this.handleNodePick(sx, sy);
            } else {
                this.isDragging = true;
                this.dragStartX = sx - this.panX;
                this.dragStartY = sy - this.panY;
            }
        }
    }

    onMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;

        if (this.isDragging) {
            this.panX = sx - this.dragStartX;
            this.panY = sy - this.dragStartY;
            this.requestRender();
        } else {
            this.checkHover(sx, sy);
        }
    }

    onMouseUp() {
        this.isDragging = false;
    }

    onWheel(e) {
        e.preventDefault();
        const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;

        const rect = this.canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;

        const wx = (sx - this.panX) / this.zoom;
        const wy = (this.panY - sy) / this.zoom;

        this.zoom *= zoomFactor;
        this.panX = sx - wx * this.zoom;
        this.panY = sy + wy * this.zoom;

        this.requestRender();
    }

    handleNodePick(sx, sy) {
        if (!this.networkData) return;
        const clickWorld = this.screenToWorld(sx, sy);

        let closestNode = null;
        let minDist = Infinity;

        for (const [nid, pos] of Object.entries(this.networkData.nodes)) {
            const dx = pos.x - clickWorld.x;
            const dy = pos.y - clickWorld.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < minDist) {
                minDist = dist;
                closestNode = nid;
            }
        }

        if (closestNode && minDist < 300 / this.zoom) {
            if (this.pickMode === 'origin') {
                this.selectedOrigin = closestNode;
                const el = document.getElementById('origin-select');
                if (el) el.value = closestNode;
            } else if (this.pickMode && this.pickMode.startsWith('c')) {
                const cIdx = parseInt(this.pickMode.substring(1), 10);
                const el = document.getElementById(`dest${cIdx}-select`);
                if (el) el.value = closestNode;
                if (this.selectedCustomers.length >= cIdx) {
                    this.selectedCustomers[cIdx - 1] = closestNode;
                }
            }
            this.pickMode = null;
            document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
            this.calculateRoute();
        }
    }

    checkHover(sx, sy) {
        if (!this.networkData) return;
        const wPos = this.screenToWorld(sx, sy);

        const infoBox = document.getElementById('hover-info');
        infoBox.innerText = `X: ${Math.round(wPos.x)}, Y: ${Math.round(wPos.y)}`;
    }

    requestRender() {
        requestAnimationFrame(() => this.render());
    }

    render() {
        const ctx = this.ctx;
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        if (!this.networkData) {
            ctx.fillStyle = '#9CA3AF';
            ctx.font = '14px Inter';
            ctx.fillText('Loading Pune SUMO Network Topology...', 20, 30);
            return;
        }

        // 1. Draw Road Edges
        ctx.lineWidth = Math.max(1, 2 * (this.zoom / 1.5));

        this.networkData.edges.forEach(edge => {
            if (!edge.shape || edge.shape.length < 2) return;

            const isIncident = this.activeIncidents.includes(edge.id);
            const congData = this.congestedEdges.get(edge.id);

            ctx.beginPath();
            const start = this.worldToScreen(edge.shape[0][0], edge.shape[0][1]);
            ctx.moveTo(start.x, start.y);

            for (let i = 1; i < edge.shape.length; i++) {
                const pt = this.worldToScreen(edge.shape[i][0], edge.shape[i][1]);
                ctx.lineTo(pt.x, pt.y);
            }

            if (isIncident) {
                ctx.strokeStyle = '#EF4444';
                ctx.lineWidth = Math.max(3, 4 * (this.zoom / 1.5));
            } else if (congData && congData.congestion_ratio > 0.1) {
                const c = congData.congestion_ratio;
                ctx.strokeStyle = c > 0.5 ? '#F59E0B' : '#10B981';
                ctx.lineWidth = Math.max(2, 3 * (this.zoom / 1.5));
            } else {
                ctx.strokeStyle = '#232834';
                ctx.lineWidth = Math.max(1, 1.5 * (this.zoom / 1.5));
            }

            ctx.stroke();
        });

        // 2. Draw Active Route Line
        if (this.activeRoute && this.activeRoute.geometry) {
            const geom = this.activeRoute.geometry;
            if (geom.length > 1) {
                ctx.beginPath();
                const first = this.worldToScreen(geom[0][0], geom[0][1]);
                ctx.moveTo(first.x, first.y);

                for (let i = 1; i < geom.length; i++) {
                    const pt = this.worldToScreen(geom[i][0], geom[i][1]);
                    ctx.lineTo(pt.x, pt.y);
                }

                ctx.strokeStyle = '#06B6D4';
                ctx.lineWidth = Math.max(4, 6 * (this.zoom / 1.5));
                ctx.shadowColor = '#06B6D4';
                ctx.shadowBlur = 10;
                ctx.stroke();
                ctx.shadowBlur = 0; // reset
            }
        }

        // 3. Draw Active Vehicles
        this.vehicles.forEach(v => {
            const pt = this.worldToScreen(v.x, v.y);
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, Math.max(3, 4 * (this.zoom / 1.5)), 0, 2 * Math.PI);

            if (v.type.includes('bus') || v.type.includes('truck')) {
                ctx.fillStyle = '#F59E0B';
            } else if (v.type.includes('bike')) {
                ctx.fillStyle = '#10B981';
            } else {
                ctx.fillStyle = '#3B82F6';
            }
            ctx.fill();
        });

        // 4. Draw Origin (O) and Customer Markers (C1, C2, C3...)
        if (this.selectedOrigin && this.networkData.nodes[this.selectedOrigin]) {
            const pos = this.networkData.nodes[this.selectedOrigin];
            const pt = this.worldToScreen(pos.x, pos.y);
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 10, 0, 2 * Math.PI);
            ctx.fillStyle = '#3B82F6'; // Blue
            ctx.fill();
            ctx.strokeStyle = '#FFFFFF';
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.fillStyle = '#FFFFFF';
            ctx.font = 'bold 11px Inter';
            ctx.textAlign = 'center';
            ctx.fillText('O', pt.x, pt.y + 4);
        }

        const custColors = ['#10B981', '#EC4899', '#F59E0B', '#8B5CF6', '#06B6D4'];

        for (let i = 1; i <= this.customerCount; i++) {
            const el = document.getElementById(`dest${i}-select`);
            const cNode = el ? el.value : (this.selectedCustomers[i - 1]);
            if (cNode && this.networkData.nodes[cNode]) {
                const pos = this.networkData.nodes[cNode];
                const pt = this.worldToScreen(pos.x, pos.y);
                const color = custColors[(i - 1) % custColors.length];

                ctx.beginPath();
                ctx.arc(pt.x, pt.y, 10, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.strokeStyle = '#FFFFFF';
                ctx.lineWidth = 2;
                ctx.stroke();
                ctx.fillStyle = '#FFFFFF';
                ctx.font = 'bold 10px Inter';
                ctx.textAlign = 'center';
                ctx.fillText(`C${i}`, pt.x, pt.y + 4);
            }
        }
    }
}

// Start app on DOM load
window.addEventListener('DOMContentLoaded', () => {
    window.app = new TrafficApp();
});
