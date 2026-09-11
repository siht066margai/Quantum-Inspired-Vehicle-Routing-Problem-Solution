import os
import sys
import json
import argparse
from typing import Dict, Any

# Ensure root directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.graph.dynamic_graph import DynamicTrafficGraph

def generate_html_visualization(dt_graph: DynamicTrafficGraph, output_file: str = "dynamic_graph_visualizer.html") -> str:
    """
    Generates a standalone interactive HTML visualizer for DynamicTrafficGraph.
    Renders nodes, directed edges, actual SUMO road shapes, congestion weights,
    lane counts, and incident states with HTML5 Canvas.
    """
    summary = dt_graph.get_summary_stats()
    
    # Prepare serializable graph data
    nodes_data = {}
    for node_id, pos in dt_graph.node_positions.items():
        nodes_data[node_id] = {"x": round(pos[0], 2), "y": round(pos[1], 2)}
        
    edges_data = []
    for edge_id, meta in dt_graph.edge_metadata.items():
        edges_data.append({
            "id": edge_id,
            "from": meta["from_node"],
            "to": meta["to_node"],
            "length": round(meta["length"], 2),
            "speed": round(meta["speed_limit"], 2),
            "lanes": meta["lane_count"],
            "free_flow_tt": round(meta["free_flow_tt"], 2),
            "travel_time": round(meta["travel_time"], 2),
            "weight": round(meta["weight"], 2),
            "congestion": round(meta["congestion_ratio"], 3),
            "vehicle_count": meta["vehicle_count"],
            "shape": [[round(pt[0], 2), round(pt[1], 2)] for pt in meta["shape"]],
            "has_incident": edge_id in dt_graph.incidents
        })

    # Compute bounding box
    xs = [pos[0] for pos in dt_graph.node_positions.values()]
    ys = [pos[1] for pos in dt_graph.node_positions.values()]
    bounds = {
        "min_x": min(xs) if xs else 0,
        "max_x": max(xs) if xs else 1000,
        "min_y": min(ys) if ys else 0,
        "max_y": max(ys) if ys else 1000
    }

    graph_payload = {
        "summary": summary,
        "bounds": bounds,
        "nodes": nodes_data,
        "edges": edges_data,
        "incidents": dt_graph.incidents
    }

    json_str = json.dumps(graph_payload)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DynamicTrafficGraph Visualization — G(t) = (V, E, W(t))</title>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --panel-bg: #111827;
            --border-color: #1f2937;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-amber: #f59e0b;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        header {{
            background: var(--panel-bg);
            border-bottom: 1px solid var(--border-color);
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 10;
        }}
        .header-title h1 {{
            font-size: 16px;
            font-weight: 700;
            color: var(--text-main);
            letter-spacing: 0.5px;
        }}
        .header-title span {{
            font-size: 12px;
            color: var(--accent-cyan);
            font-family: monospace;
        }}
        .stats-strip {{
            display: flex;
            gap: 16px;
        }}
        .stat-badge {{
            background: rgba(31, 41, 55, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 12px;
        }}
        .stat-badge strong {{
            color: var(--accent-cyan);
            margin-left: 4px;
        }}
        main {{
            flex: 1;
            position: relative;
            display: flex;
        }}
        #viewport {{
            flex: 1;
            height: 100%;
            cursor: grab;
            position: relative;
        }}
        #viewport:active {{
            cursor: grabbing;
        }}
        canvas {{
            display: block;
            width: 100%;
            height: 100%;
        }}
        .controls-overlay {{
            position: absolute;
            top: 16px;
            left: 16px;
            background: rgba(17, 24, 39, 0.85);
            backdrop-filter: blur(8px);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px;
            width: 280px;
            z-index: 5;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .control-group {{
            margin-bottom: 12px;
        }}
        .control-group:last-child {{
            margin-bottom: 0;
        }}
        label {{
            display: block;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 600;
        }}
        select, input {{
            width: 100%;
            background: #1f2937;
            border: 1px solid #374151;
            color: var(--text-main);
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 12px;
            outline: none;
        }}
        select:focus, input:focus {{
            border-color: var(--accent-cyan);
        }}
        .btn-row {{
            display: flex;
            gap: 6px;
            margin-top: 8px;
        }}
        .btn {{
            flex: 1;
            background: #374151;
            color: #fff;
            border: none;
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .btn:hover {{
            background: #4b5563;
        }}
        .btn-cyan {{
            background: var(--accent-cyan);
            color: #000;
            font-weight: 600;
        }}
        .btn-cyan:hover {{
            background: #22d3ee;
        }}
        .inspector-card {{
            position: absolute;
            bottom: 16px;
            right: 16px;
            background: rgba(17, 24, 39, 0.9);
            backdrop-filter: blur(8px);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px;
            width: 320px;
            z-index: 5;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            display: none;
        }}
        .inspector-card h3 {{
            font-size: 13px;
            color: var(--accent-cyan);
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .inspector-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            font-size: 11px;
        }}
        .inspector-item {{
            background: #1f2937;
            padding: 6px 8px;
            border-radius: 4px;
        }}
        .inspector-item span {{
            display: block;
            color: var(--text-muted);
            font-size: 10px;
        }}
        .inspector-item strong {{
            color: var(--text-main);
        }}
        .legend {{
            margin-top: 10px;
            font-size: 11px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .legend-bar {{
            height: 8px;
            flex: 1;
            margin: 0 8px;
            border-radius: 4px;
            background: linear-gradient(to right, #10b981, #f59e0b, #ef4444);
        }}
    </style>
</head>
<body>
    <header>
        <div class="header-title">
            <h1>DYNAMIC TRAFFIC GRAPH VISUALIZER</h1>
            <span>backend/graph/dynamic_graph.py &bull; G(t) = (V, E, W(t))</span>
        </div>
        <div class="stats-strip">
            <div class="stat-badge">Nodes: <strong id="stat-nodes">{summary['total_nodes']}</strong></div>
            <div class="stat-badge">Edges: <strong id="stat-edges">{summary['total_edges']}</strong></div>
            <div class="stat-badge">Congested: <strong id="stat-congested">{summary['congested_edge_count']}</strong></div>
            <div class="stat-badge">Incidents: <strong id="stat-incidents">{summary['incident_count']}</strong></div>
        </div>
    </header>

    <main>
        <div id="viewport">
            <canvas id="graphCanvas"></canvas>
        </div>

        <div class="controls-overlay">
            <div class="control-group">
                <label>Edge Coloring Mode</label>
                <select id="colorMode">
                    <option value="weight">Dynamic Edge Weight W(t)</option>
                    <option value="speed">Speed Limit (m/s)</option>
                    <option value="lanes">Lane Count</option>
                    <option value="length">Physical Length (m)</option>
                </select>
            </div>

            <div class="control-group">
                <label>Search Edge / Node ID</label>
                <input type="text" id="searchInput" placeholder="e.g. 23815347 or -4678120#1">
            </div>

            <div class="btn-row">
                <button class="btn btn-cyan" id="btnFit">Fit Network Bounds</button>
                <button class="btn" id="btnReset">Reset Zoom</button>
            </div>

            <div class="legend">
                <span>Low Cost / Fast</span>
                <div class="legend-bar"></div>
                <span>High Weight / Incident</span>
            </div>
        </div>

        <div class="inspector-card" id="inspector">
            <h3>
                <span id="inspectTitle">Edge Inspector</span>
                <button id="closeInspect" style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:14px;">✕</button>
            </h3>
            <div class="inspector-grid" id="inspectGrid">
                <!-- Populated dynamically -->
            </div>
        </div>
    </main>

    <script>
        const GRAPH_DATA = {json_str};

        const canvas = document.getElementById('graphCanvas');
        const ctx = canvas.getContext('2d');
        const viewport = document.getElementById('viewport');
        const colorModeSelect = document.getElementById('colorMode');
        const searchInput = document.getElementById('searchInput');
        const btnFit = document.getElementById('btnFit');
        const btnReset = document.getElementById('btnReset');
        const inspector = document.getElementById('inspector');
        const inspectTitle = document.getElementById('inspectTitle');
        const inspectGrid = document.getElementById('inspectGrid');
        const closeInspect = document.getElementById('closeInspect');

        let scale = 1;
        let offsetX = 0;
        let offsetY = 0;
        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;
        let selectedEdge = null;

        function resizeCanvas() {{
            canvas.width = viewport.clientWidth;
            canvas.height = viewport.clientHeight;
            draw();
        }}

        window.addEventListener('resize', resizeCanvas);

        function fitBounds() {{
            const b = GRAPH_DATA.bounds;
            const padding = 50;
            const dataWidth = b.max_x - b.min_x;
            const dataHeight = b.max_y - b.min_y;

            if (dataWidth <= 0 || dataHeight <= 0) return;

            const scaleX = (canvas.width - padding * 2) / dataWidth;
            const scaleY = (canvas.height - padding * 2) / dataHeight;
            scale = Math.min(scaleX, scaleY);

            // Invert Y axis for map coordinates
            offsetX = padding - b.min_x * scale;
            offsetY = canvas.height - padding + b.min_y * scale;
            draw();
        }}

        function mapToCanvas(x, y) {{
            return {{
                cx: x * scale + offsetX,
                cy: -y * scale + offsetY
            }};
        }}

        function canvasToMap(cx, cy) {{
            return {{
                x: (cx - offsetX) / scale,
                y: -(cy - offsetY) / scale
            }};
        }}

        function getEdgeColor(edge, mode) {{
            if (edge.has_incident) return '#ef4444'; // Bright Red for incident

            if (mode === 'speed') {{
                const ratio = Math.min(edge.speed / 30.0, 1.0);
                const r = Math.floor(239 * (1 - ratio));
                const g = Math.floor(185 * ratio);
                return `rgb(${{r}}, ${{g}}, 120)`;
            }} else if (mode === 'lanes') {{
                if (edge.lanes >= 3) return '#06b6d4';
                if (edge.lanes === 2) return '#3b82f6';
                return '#64748b';
            }} else if (mode === 'length') {{
                const ratio = Math.min(edge.length / 500.0, 1.0);
                return `rgb(6, ${{Math.floor(182 * (1 - ratio))}}, ${{Math.floor(212 * ratio)}})`;
            }} else {{
                const ratio = Math.min(edge.congestion * 3.0 + (edge.weight / (edge.free_flow_tt * 2.0 + 1)), 1.0);
                if (ratio > 0.6) return '#ef4444';
                if (ratio > 0.3) return '#f59e0b';
                return '#10b981';
            }}
        }}

        function draw() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const mode = colorModeSelect.value;
            const searchQuery = searchInput.value.trim().toLowerCase();

            // Draw directed Edges
            GRAPH_DATA.edges.forEach(edge => {{
                if (edge.shape && edge.shape.length >= 2) {{
                    ctx.beginPath();
                    const startP = mapToCanvas(edge.shape[0][0], edge.shape[0][1]);
                    ctx.moveTo(startP.cx, startP.cy);

                    for (let i = 1; i < edge.shape.length; i++) {{
                        const p = mapToCanvas(edge.shape[i][0], edge.shape[i][1]);
                        ctx.lineTo(p.cx, p.cy);
                    }}

                    const isMatch = searchQuery && edge.id.toLowerCase().includes(searchQuery);
                    const isSelected = selectedEdge && selectedEdge.id === edge.id;

                    if (isSelected) {{
                        ctx.strokeStyle = '#38bdf8';
                        ctx.lineWidth = Math.max(4, 2 * scale);
                    }} else if (isMatch) {{
                        ctx.strokeStyle = '#facc15';
                        ctx.lineWidth = Math.max(3, 1.5 * scale);
                    }} else {{
                        ctx.strokeStyle = getEdgeColor(edge, mode);
                        ctx.lineWidth = Math.max(1, (edge.lanes || 1) * Math.min(scale, 1.5));
                    }}

                    ctx.stroke();
                }}
            }});

            // Draw Nodes as small dots when zoomed in
            if (scale > 0.5) {{
                ctx.fillStyle = '#64748b';
                Object.entries(GRAPH_DATA.nodes).forEach(([nodeId, pos]) => {{
                    const p = mapToCanvas(pos.x, pos.y);
                    if (p.cx >= 0 && p.cx <= canvas.width && p.cy >= 0 && p.cy <= canvas.height) {{
                        ctx.beginPath();
                        ctx.arc(p.cx, p.cy, Math.min(2.5, scale * 1.5), 0, 2 * Math.PI);
                        ctx.fill();
                    }}
                }});
            }}
        }}

        // Interactivity
        viewport.addEventListener('mousedown', (e) => {{
            isDragging = true;
            dragStartX = e.clientX - offsetX;
            dragStartY = e.clientY - offsetY;
        }});

        window.addEventListener('mousemove', (e) => {{
            if (isDragging) {{
                offsetX = e.clientX - dragStartX;
                offsetY = e.clientY - dragStartY;
                draw();
            }}
        }});

        window.addEventListener('mouseup', () => {{
            isDragging = false;
        }});

        viewport.addEventListener('wheel', (e) => {{
            e.preventDefault();
            const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
            const mouseCanvasX = e.clientX;
            const mouseCanvasY = e.clientY - viewport.getBoundingClientRect().top;

            const mouseMapBefore = canvasToMap(mouseCanvasX, mouseCanvasY);
            scale *= zoomFactor;
            const mouseCanvasAfter = mapToCanvas(mouseMapBefore.x, mouseMapBefore.y);

            offsetX += (mouseCanvasX - mouseCanvasAfter.cx);
            offsetY += (mouseCanvasY - mouseCanvasAfter.cy);

            draw();
        }}, {{ passive: false }});

        // Click to Inspect Edge
        viewport.addEventListener('click', (e) => {{
            if (isDragging) return;
            const rect = viewport.getBoundingClientRect();
            const mouseCanvasX = e.clientX - rect.left;
            const mouseCanvasY = e.clientY - rect.top;
            const mapPos = canvasToMap(mouseCanvasX, mouseCanvasY);

            // Find closest edge within click threshold
            let closestEdge = null;
            let minDistance = 25.0 / scale;

            GRAPH_DATA.edges.forEach(edge => {{
                if (!edge.shape || edge.shape.length < 2) return;
                for (let i = 0; i < edge.shape.length - 1; i++) {{
                    const p1 = edge.shape[i];
                    const p2 = edge.shape[i+1];
                    const dist = distToSegment(mapPos, {{x: p1[0], y: p1[1]}}, {{x: p2[0], y: p2[1]}});
                    if (dist < minDistance) {{
                        minDistance = dist;
                        closestEdge = edge;
                    }}
                }}
            }});

            if (closestEdge) {{
                showInspector(closestEdge);
            }}
        }});

        function distToSegment(p, v, w) {{
            const l2 = (v.x - w.x)**2 + (v.y - w.y)**2;
            if (l2 === 0) return Math.hypot(p.x - v.x, p.y - v.y);
            let t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y)) / l2;
            t = Math.max(0, Math.min(1, t));
            return Math.hypot(p.x - (v.x + t * (w.x - v.x)), p.y - (v.y + t * (w.y - v.y)));
        }}

        function showInspector(edge) {{
            selectedEdge = edge;
            inspectTitle.innerText = `Edge: ${{edge.id}}`;
            inspectGrid.innerHTML = `
                <div class="inspector-item"><span>From Junction</span><strong>${{edge.from}}</strong></div>
                <div class="inspector-item"><span>To Junction</span><strong>${{edge.to}}</strong></div>
                <div class="inspector-item"><span>Length L_e</span><strong>${{edge.length}} m</strong></div>
                <div class="inspector-item"><span>Speed Limit</span><strong>${{edge.speed}} m/s</strong></div>
                <div class="inspector-item"><span>Lanes</span><strong>${{edge.lanes}}</strong></div>
                <div class="inspector-item"><span>Free-Flow Time</span><strong>${{edge.free_flow_tt}} s</strong></div>
                <div class="inspector-item"><span>Dynamic Weight W(t)</span><strong>${{edge.weight}} s</strong></div>
                <div class="inspector-item"><span>Incident Status</span><strong>${{edge.has_incident ? '⚠️ ACCIDENT ACTIVE' : 'Normal'}}</strong></div>
            `;
            inspector.style.display = 'block';
            draw();
        }}

        closeInspect.addEventListener('click', () => {{
            inspector.style.display = 'none';
            selectedEdge = null;
            draw();
        }});

        colorModeSelect.addEventListener('change', draw);
        searchInput.addEventListener('input', draw);
        btnFit.addEventListener('click', fitBounds);
        btnReset.addEventListener('click', () => {{
            scale = 1;
            offsetX = 0;
            offsetY = 0;
            fitBounds();
        }});

        // Initialize
        resizeCanvas();
        fitBounds();
    </script>
</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_file

def main():
    parser = argparse.ArgumentParser(description="Visualize DynamicTrafficGraph from backend/graph/dynamic_graph.py")
    parser.add_argument("--net-file", type=str, default="osm.net.xml.gz", help="Path to SUMO .net.xml or .net.xml.gz file")
    parser.add_argument("--output", type=str, default="dynamic_graph_visualizer.html", help="Path for output HTML visualizer")
    parser.add_argument("--inject-incident", type=str, help="Edge ID to inject test incident on")

    args = parser.parse_args()

    net_path = args.net_file
    if not os.path.isabs(net_path):
        net_path = os.path.join(ROOT_DIR, net_path)

    print(f"[*] Initializing DynamicTrafficGraph...")
    dt_graph = DynamicTrafficGraph()

    print(f"[*] Loading SUMO network from {net_path}...")
    dt_graph.load_net_file(net_path)

    if args.inject_incident:
        print(f"[!] Injecting test incident on edge '{args.inject_incident}'...")
        dt_graph.set_incident(args.inject_incident, penalty_multiplier=100.0)

    stats = dt_graph.get_summary_stats()
    print("\n--- DynamicTrafficGraph Summary Stats ---")
    print(f"  Total Nodes:          {stats['total_nodes']}")
    print(f"  Total Directed Edges: {stats['total_edges']}")
    print(f"  Congested Edges:      {stats['congested_edge_count']}")
    print(f"  Active Incidents:     {stats['incident_count']}")
    print("-------------------------------------------\n")

    out_file = args.output
    if not os.path.isabs(out_file):
        out_file = os.path.join(ROOT_DIR, out_file)

    generate_html_visualization(dt_graph, out_file)
    print(f"[+] DynamicTrafficGraph visualization exported successfully to:")
    print(f"    {out_file}")
    print("\n[i] Open this file in your web browser to interactively explore nodes, edges, road shapes, speeds, and dynamic weights!")

if __name__ == "__main__":
    main()
