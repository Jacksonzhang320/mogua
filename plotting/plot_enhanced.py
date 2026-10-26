from __future__ import annotations

r"""Mogua Enhanced Citation Network Visualizer (HTML, PNG, SVG)

Generates:
1. High-fidelity, responsive, interactive HTML network map using Vis.js.
   - Automatic modularity-based sub-cluster detection (field-agnostic).
   - Triple coloring modes: Topic Clusters, Academic Roles, and Timeline Gradient.
   - Reader detail drawer with interactive in-graph citation jumping.
   - Live search, neighbor highlighting, physics toggle, and canvas fit.
2. Publication-ready static overview figures (PNG at 300 DPI and vector SVG).
"""

import argparse
import csv
import html
import json
import math
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import networkx as nx
import networkx.algorithms.community as nx_comm
from matplotlib.lines import Line2D
from pyvis.network import Network


CLUSTER_PALETTE = [
    "#38BDF8",  # Sky Blue
    "#F472B6",  # Pink
    "#34D399",  # Emerald
    "#A78BFA",  # Purple
    "#FBBF24",  # Amber
    "#FB7185",  # Rose
    "#60A5FA",  # Blue
    "#4ADE80",  # Green
    "#C084FC",  # Violet
    "#F97316",  # Orange
]

ROLE_COLORS = {
    "seed": "#F59E0B",        # Golden Amber
    "foundation": "#3B82F6",  # Royal Blue (high citation/year classic)
    "kin": "#8B5CF6",         # Deep Purple (high bibliographic coupling / Jaccard)
    "recent": "#10B981",      # Emerald Green (recent advances)
    "connected": "#64748B",   # Slate Grey (core related work)
}

ROLE_LABELS = {
    "seed": "🌱 Seed Paper",
    "foundation": "🏛️ Foundation Classic",
    "kin": "🧬 Direct Kin (High Overlap)",
    "recent": "🚀 Recent Advance",
    "connected": "📄 Connected Work",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def first_author(authors: str) -> str:
    if not authors:
        return "Unknown"
    first = authors.split(";")[0].strip()
    if "," in first:
        return first.split(",", 1)[0].strip()
    words = first.split()
    return words[-1] if words else "Unknown"


def node_label(row: dict[str, str]) -> str:
    author = first_author(row.get("Authors", ""))
    year = row.get("Year", "")
    is_seed = row.get("IsSeed") == "1"
    if is_seed:
        return f"⭐ {author} ({year})"
    return f"{author} ({year})"


def node_size(row: dict[str, str]) -> float:
    cites = max(0, int(float(row.get("CitedByCount") or 0)))
    # Logarithmic scaling between 16 and 42
    return 16.0 + math.log1p(cites) * 2.8


def detect_communities(graph: nx.DiGraph) -> dict[str, int]:
    """Detect topical sub-clusters using modularity optimization on undirected graph."""
    undir = graph.to_undirected()
    if undir.number_of_nodes() == 0:
        return {}
    try:
        comms = list(nx_comm.greedy_modularity_communities(undir))
        node_comm = {}
        for idx, c in enumerate(comms):
            for node_id in c:
                node_comm[node_id] = idx
        return node_comm
    except Exception:
        return {node_id: 0 for node_id in graph.nodes}


def assign_roles(nodes: list[dict[str, str]]) -> dict[str, str]:
    """Classify papers into academic roles based on metrics."""
    roles: dict[str, str] = {}
    current_year = 2026
    non_seeds = [n for n in nodes if n.get("IsSeed") != "1"]

    # Sort candidates
    by_cpy = sorted(non_seeds, key=lambda x: float(x.get("CitationPerYear", 0) or 0), reverse=True)
    by_sim = sorted(non_seeds, key=lambda x: float(x.get("Similarity", 0) or 0), reverse=True)

    top_foundations = {n["Id"] for n in by_cpy[:max(3, len(non_seeds) // 6)] if float(n.get("CitationPerYear", 0) or 0) > 15}
    top_kin = {n["Id"] for n in by_sim[:max(4, len(non_seeds) // 5)] if float(n.get("Similarity", 0) or 0) > 0.05}

    for row in nodes:
        nid = row["Id"]
        if row.get("IsSeed") == "1":
            roles[nid] = "seed"
        elif nid in top_foundations:
            roles[nid] = "foundation"
        elif nid in top_kin:
            roles[nid] = "kin"
        elif row.get("Year") and row["Year"].isdigit() and int(row["Year"]) >= current_year - 3:
            roles[nid] = "recent"
        else:
            roles[nid] = "connected"
    return roles


def year_gradient_color(year_str: str, min_year: int, max_year: int) -> str:
    """Return color hex along a timeline gradient (Blue -> Emerald -> Amber)."""
    try:
        y = int(year_str)
    except Exception:
        y = min_year
    span = max(1, max_year - min_year)
    norm = min(1.0, max(0.0, (y - min_year) / span))
    # Interpolate: 0.0 -> #3B82F6, 0.5 -> #10B981, 1.0 -> #F59E0B
    if norm < 0.5:
        t = norm / 0.5
        r = int(59 + t * (16 - 59))
        g = int(130 + t * (185 - 130))
        b = int(246 + t * (129 - 246))
    else:
        t = (norm - 0.5) / 0.5
        r = int(16 + t * (245 - 16))
        g = int(185 + t * (158 - 185))
        b = int(129 + t * (11 - 129))
    return f"#{r:02x}{g:02x}{b:02x}"


def build_graph(nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for row in nodes:
        graph.add_node(row["Id"], row=row)
    for edge in edges:
        if edge["Source"] in graph and edge["Target"] in graph:
            graph.add_edge(edge["Source"], edge["Target"])
    return graph


def write_interactive(
    graph: nx.DiGraph,
    output_html: Path,
    title: str,
) -> None:
    nodes_rows = [attrs["row"] for _, attrs in graph.nodes(data=True)]
    communities = detect_communities(graph)
    roles = assign_roles(nodes_rows)

    # Calculate years
    years = [int(r["Year"]) for r in nodes_rows if r.get("Year") and r["Year"].isdigit()]
    min_year = min(years) if years else 2000
    max_year = max(years) if years else 2026

    # Cluster summary
    cluster_counts: dict[int, int] = {}
    for cid in communities.values():
        cluster_counts[cid] = cluster_counts.get(cid, 0) + 1

    nodes_info: dict[str, dict[str, Any]] = {}
    node_color_maps: dict[str, dict[str, str]] = {}

    net = Network(
        height="100vh",
        width="100%",
        notebook=False,
        directed=True,
        bgcolor="#0F172A",
        font_color="#F8FAFC",
        cdn_resources="in_line",
    )

    for node_id, attrs in graph.nodes(data=True):
        row = attrs["row"]
        comm_id = communities.get(node_id, 0)
        role = roles.get(node_id, "connected")
        is_seed = role == "seed"

        comm_color = CLUSTER_PALETTE[comm_id % len(CLUSTER_PALETTE)]
        role_color = ROLE_COLORS[role]
        year_color = year_gradient_color(row.get("Year", ""), min_year, max_year)

        node_color_maps[node_id] = {
            "cluster": comm_color,
            "role": role_color,
            "year": year_color,
        }

        # Initial color follows cluster, unless seed
        init_bg = "#F59E0B" if is_seed else comm_color
        init_border = "#FFFFFF" if is_seed else "#E2E8F0"

        outgoing = list(graph.successors(node_id))
        incoming = list(graph.predecessors(node_id))

        net.add_node(
            node_id,
            label=node_label(row),
            shape="star" if is_seed else "dot",
            size=max(28.0, node_size(row) + 8.0) if is_seed else node_size(row),
            color={
                "background": init_bg,
                "border": init_border,
                "highlight": {"background": "#FBBF24", "border": "#FFFFFF"},
                "hover": {"background": "#FCD34D", "border": "#FFFFFF"},
            },
            borderWidth=3.0 if is_seed else 1.5,
            font={
                "size": 13,
                "face": "system-ui, -apple-system, sans-serif",
                "color": "#F8FAFC",
                "strokeWidth": 3.5,
                "strokeColor": "#0F172A",
                "multi": True,
            },
            title="",  # custom drawer replaces default tooltip
        )

        nodes_info[node_id] = {
            "id": node_id,
            "title": row.get("Title", "Untitled"),
            "journal": row.get("Journal", "Unknown Venue"),
            "authors": row.get("Authors", "Unknown Authors"),
            "year": row.get("Year", "N/A"),
            "citations": row.get("CitedByCount", "0"),
            "cpy": f"{float(row.get('CitationPerYear', 0) or 0):.1f}",
            "similarity": f"{float(row.get('Similarity', 0) or 0):.1%}",
            "doi": row.get("DOI", ""),
            "oa_url": row.get("OA_URL", ""),
            "role": role,
            "role_label": ROLE_LABELS[role],
            "cluster": comm_id + 1,
            "outgoing": outgoing,
            "incoming": incoming,
        }

    for source, target in graph.edges():
        net.add_edge(
            source,
            target,
            color={"color": "rgba(148, 163, 184, 0.28)", "highlight": "#F59E0B", "hover": "#38BDF8"},
            width=1.2,
            arrows={"to": {"enabled": True, "scaleFactor": 0.45}},
        )

    options = {
        "physics": {
            "enabled": True,
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
                "gravitationalConstant": -60,
                "centralGravity": 0.012,
                "springLength": 110,
                "springConstant": 0.08,
                "damping": 0.45,
                "avoidOverlap": 0.75,
            },
            "stabilization": {
                "enabled": True,
                "iterations": 250,
                "updateInterval": 25,
                "fit": True,
            },
        },
        "interaction": {
            "hover": True,
            "tooltipDelay": 80,
            "navigationButtons": False,
            "keyboard": True,
            "multiselect": True,
        },
    }
    net.set_options(json.dumps(options))

    html_text = net.generate_html()
    extras = build_extras(title, nodes_info, node_color_maps, cluster_counts, min_year, max_year)
    html_text = html_text.replace("</body>", extras + "</body>")

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_text, encoding="utf-8")


def build_extras(
    title: str,
    nodes_info: dict[str, dict[str, Any]],
    node_color_maps: dict[str, dict[str, str]],
    cluster_counts: dict[int, int],
    min_year: int,
    max_year: int,
) -> str:
    # Build cluster legend items
    cluster_legend_html = "".join(
        f'<div class="legend-item"><span class="swatch" style="background:{CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)]}"></span><span>Topic Cluster {cid + 1}</span><span class="count">{count}</span></div>'
        for cid, count in sorted(cluster_counts.items())
    )

    # Build role legend items
    role_legend_html = "".join(
        f'<div class="legend-item"><span class="swatch" style="background:{color}"></span><span>{label}</span></div>'
        for role_key, color in ROLE_COLORS.items()
        for label in [ROLE_LABELS[role_key]]
    )

    total_nodes = len(nodes_info)
    total_edges = sum(len(n["outgoing"]) for n in nodes_info.values())

    return f"""
<style>
  :root {{
    --bg-dark: #0F172A;
    --card-bg: rgba(30, 41, 59, 0.92);
    --border-color: rgba(71, 85, 105, 0.6);
    --text-primary: #F8FAFC;
    --text-secondary: #94A3B8;
    --accent-amber: #F59E0B;
    --accent-blue: #38BDF8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg-dark);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    overflow: hidden;
    height: 100vh;
  }}
  #mynetwork {{
    position: absolute;
    top: 64px;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100% !important;
    height: calc(100vh - 64px) !important;
    border: none !important;
  }}

  /* Top Navigation Bar */
  #topbar {{
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 64px;
    background: rgba(15, 23, 42, 0.95);
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    z-index: 1000;
    backdrop-filter: blur(12px);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
    flex: 1;
  }}
  .logo {{
    font-size: 20px;
    font-weight: 800;
    background: linear-gradient(135deg, #F59E0B 0%, #F43F5E 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
    flex: none;
  }}
  .paper-meta {{
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 10px;
  }}
  .paper-meta h1 {{
    font-size: 15px;
    font-weight: 600;
    color: #F8FAFC;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 460px;
  }}
  .stats-pill {{
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 9999px;
    background: rgba(56, 189, 248, 0.15);
    color: var(--accent-blue);
    border: 1px solid rgba(56, 189, 248, 0.3);
    white-space: nowrap;
    flex: none;
  }}

  /* Action Controls */
  .controls {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex: none;
  }}
  .search-box {{
    position: relative;
    display: flex;
    align-items: center;
  }}
  .search-box input {{
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid var(--border-color);
    color: #FFF;
    font-size: 13px;
    padding: 7px 12px 7px 32px;
    border-radius: 8px;
    width: 200px;
    transition: all 0.2s;
  }}
  .search-box input:focus {{
    outline: none;
    border-color: var(--accent-blue);
    width: 260px;
    background: rgba(30, 41, 59, 1);
  }}
  .search-icon {{
    position: absolute;
    left: 10px;
    color: var(--text-secondary);
    font-size: 13px;
    pointer-events: none;
  }}
  .btn {{
    background: rgba(30, 41, 59, 0.85);
    color: #F8FAFC;
    border: 1px solid var(--border-color);
    padding: 7px 12px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s ease;
  }}
  .btn:hover {{
    background: #334155;
    border-color: #64748B;
  }}
  .btn.active {{
    background: #2563EB;
    border-color: #3B82F6;
  }}

  /* Floating Legend Panel */
  #legend-panel {{
    position: absolute;
    left: 20px;
    top: 84px;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 14px 16px;
    width: 220px;
    z-index: 900;
    backdrop-filter: blur(12px);
    box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    cursor: move;
  }}
  .legend-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(71, 85, 105, 0.4);
  }}
  .legend-header h3 {{
    font-size: 12px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .mode-select {{
    background: rgba(15, 23, 42, 0.7);
    color: #F8FAFC;
    border: 1px solid var(--border-color);
    font-size: 11px;
    padding: 3px 6px;
    border-radius: 6px;
    cursor: pointer;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 6px 0;
    font-size: 11px;
    color: #CBD5E1;
  }}
  .legend-item .count {{
    margin-left: auto;
    color: var(--text-secondary);
    font-weight: 600;
  }}
  .swatch {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex: none;
    border: 1px solid rgba(255,255,255,0.4);
  }}

  /* Floating Paper Detail Drawer */
  #detail-drawer {{
    position: absolute;
    right: 20px;
    top: 84px;
    bottom: 20px;
    width: 380px;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    padding: 18px 20px;
    z-index: 900;
    backdrop-filter: blur(14px);
    box-shadow: 0 14px 35px rgba(0,0,0,0.45);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .drawer-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }}
  .badge {{
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 6px;
    background: rgba(245, 158, 11, 0.15);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.3);
  }}
  .drawer-content {{
    flex: 1;
    overflow-y: auto;
    padding-right: 4px;
  }}
  .drawer-content::-webkit-scrollbar {{
    width: 5px;
  }}
  .drawer-content::-webkit-scrollbar-thumb {{
    background: #475569;
    border-radius: 4px;
  }}
  .card-title {{
    font-size: 15px;
    font-weight: 700;
    line-height: 1.4;
    color: #FFF;
    margin-bottom: 10px;
  }}
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    background: rgba(15, 23, 42, 0.5);
    padding: 10px;
    border-radius: 8px;
    margin-bottom: 14px;
  }}
  .meta-item {{
    font-size: 11px;
  }}
  .meta-label {{
    color: var(--text-secondary);
    display: block;
    margin-bottom: 2px;
  }}
  .meta-val {{
    color: #F8FAFC;
    font-weight: 600;
  }}
  .links-row {{
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
  }}
  .link-pill {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    padding: 5px 10px;
    background: #1E293B;
    border: 1px solid var(--border-color);
    color: var(--accent-blue);
    text-decoration: none;
    border-radius: 6px;
    font-weight: 500;
  }}
  .link-pill:hover {{
    background: #334155;
    color: #FFF;
  }}
  .connections-section {{
    border-top: 1px solid rgba(71, 85, 105, 0.4);
    padding-top: 12px;
  }}
  .connections-section h4 {{
    font-size: 11px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    margin-bottom: 8px;
  }}
  .conn-list {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .conn-item {{
    font-size: 11px;
    line-height: 1.35;
    padding: 6px 8px;
    border-radius: 6px;
    background: rgba(15, 23, 42, 0.4);
    cursor: pointer;
    transition: background 0.15s;
    color: #CBD5E1;
  }}
  .conn-item:hover {{
    background: rgba(56, 189, 248, 0.15);
    color: #38BDF8;
  }}
  .empty-state {{
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    text-align: center;
    gap: 10px;
    font-size: 13px;
  }}
</style>

<!-- Topbar -->
<div id="topbar">
  <div class="brand">
    <div class="logo">MOGUA · 摸瓜</div>
    <div class="paper-meta">
      <h1 title="{html.escape(title)}">{html.escape(title)}</h1>
      <span class="stats-pill">{total_nodes} Papers · {total_edges} Citations</span>
    </div>
  </div>
  <div class="controls">
    <div class="search-box">
      <span class="search-icon">🔍</span>
      <input type="text" id="paper-search" placeholder="Search author, title..." autocomplete="off">
    </div>
    <button class="btn" id="btn-fit" title="Fit network to view">🎯 Fit</button>
    <button class="btn" id="btn-physics" title="Toggle physics simulation">⏸ Freeze</button>
    <button class="btn" id="btn-reset" title="Reset highlight">🔄 Reset</button>
  </div>
</div>

<!-- Floating Legend -->
<div id="legend-panel">
  <div class="legend-header">
    <h3>Color Mode</h3>
    <select id="color-mode-select" class="mode-select">
      <option value="cluster">🌐 Clusters</option>
      <option value="role">🏷️ Roles</option>
      <option value="year">📅 Timeline</option>
    </select>
  </div>
  <div id="legend-cluster-view">
    <div class="legend-item"><span class="swatch" style="background:#F59E0B"></span><span>⭐ Seed Paper</span></div>
    {cluster_legend_html}
  </div>
  <div id="legend-role-view" style="display:none;">
    {role_legend_html}
  </div>
  <div id="legend-year-view" style="display:none;">
    <div class="legend-item"><span class="swatch" style="background:#3B82F6"></span><span>Earliest ({min_year})</span></div>
    <div class="legend-item"><span class="swatch" style="background:#10B981"></span><span>Mid-era</span></div>
    <div class="legend-item"><span class="swatch" style="background:#F59E0B"></span><span>Recent ({max_year})</span></div>
  </div>
</div>

<!-- Floating Detail Drawer -->
<div id="detail-drawer">
  <div class="drawer-header">
    <span class="badge" id="paper-badge">Select a paper</span>
    <span style="font-size:11px;color:#94A3B8;">ESC to clear</span>
  </div>
  <div class="drawer-content" id="drawer-body">
    <div class="empty-state">
      <div style="font-size:28px;">📄</div>
      <div>Click or hover over any paper node to inspect full metadata, metrics, and in-graph citations.</div>
    </div>
  </div>
</div>

<script>
const paperInfo = {json.dumps(nodes_info, ensure_ascii=False)};
const colorMaps = {json.dumps(node_color_maps, ensure_ascii=False)};
let activeMode = 'cluster';
let physicsFrozen = false;

network.once('stabilizationIterationsDone', () => {{
  network.fit({{ animation: {{ duration: 700, easingFunction: 'easeInOutQuad' }} }});
  // Auto-freeze after stabilization to keep map neat and steady
  network.setOptions({{ physics: {{ enabled: false }} }});
  physicsFrozen = true;
  document.getElementById('btn-physics').textContent = '▶ Physics';
}});

// Node Selection & Hover
network.on('click', params => {{
  if (params.nodes.length > 0) {{
    renderDrawer(params.nodes[0]);
    highlightNeighbors(params.nodes[0]);
  }} else {{
    resetHighlight();
  }}
}});

network.on('hoverNode', params => {{
  renderDrawer(params.node);
  highlightNeighbors(params.node);
}});

function esc(str) {{
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}}

function renderDrawer(nodeId) {{
  const d = paperInfo[nodeId];
  if (!d) return;

  document.getElementById('paper-badge').textContent = d.role_label;

  let outList = d.outgoing.map(id => {{
    const target = paperInfo[id];
    const name = target ? `${{target.title}} (${{target.year}})` : id;
    return `<div class="conn-item" onclick="focusNode('${{id}}')">→ ${{esc(name)}}</div>`;
  }}).join('');

  let inList = d.incoming.map(id => {{
    const source = paperInfo[id];
    const name = source ? `${{source.title}} (${{source.year}})` : id;
    return `<div class="conn-item" onclick="focusNode('${{id}}')">← ${{esc(name)}}</div>`;
  }}).join('');

  if (!outList) outList = '<div style="color:#64748B;font-size:11px;">None in core network</div>';
  if (!inList) inList = '<div style="color:#64748B;font-size:11px;">None in core network</div>';

  let oaBtn = d.oa_url ? `<a class="link-pill" target="_blank" href="${{esc(d.oa_url)}}">📥 PDF (Open Access)</a>` : '';
  let doiBtn = d.doi ? `<a class="link-pill" target="_blank" href="https://doi.org/${{esc(d.doi)}}">🔗 DOI: ${{esc(d.doi)}}</a>` : '';

  document.getElementById('drawer-body').innerHTML = `
    <div class="card-title">${{esc(d.title)}}</div>
    <div style="font-size:11px;color:#94A3B8;margin-bottom:12px;">${{esc(d.authors)}}</div>
    <div class="meta-grid">
      <div class="meta-item"><span class="meta-label">Journal</span><span class="meta-val">${{esc(d.journal)}}</span></div>
      <div class="meta-item"><span class="meta-label">Year</span><span class="meta-val">${{esc(d.year)}}</span></div>
      <div class="meta-item"><span class="meta-label">Total Citations</span><span class="meta-val">${{esc(d.citations)}}</span></div>
      <div class="meta-item"><span class="meta-label">Citations / Year</span><span class="meta-val">${{esc(d.cpy)}}</span></div>
      <div class="meta-item"><span class="meta-label">Jaccard Overlap</span><span class="meta-val">${{esc(d.similarity)}}</span></div>
      <div class="meta-item"><span class="meta-label">Cluster</span><span class="meta-val">#${{d.cluster}}</span></div>
    </div>
    <div class="links-row">
      ${{doiBtn}}
      ${{oaBtn}}
    </div>
    <div class="connections-section">
      <h4>Direct Citations in this Graph</h4>
      <div style="margin-bottom:10px;">
        <span style="font-size:10px;color:#38BDF8;font-weight:600;">CITES (${{d.outgoing.length}})</span>
        <div class="conn-list" style="margin-top:4px;">${{outList}}</div>
      </div>
      <div>
        <span style="font-size:10px;color:#34D399;font-weight:600;">CITED BY (${{d.incoming.length}})</span>
        <div class="conn-list" style="margin-top:4px;">${{inList}}</div>
      </div>
    </div>
  `;
}}

function focusNode(id) {{
  network.selectNodes([id]);
  renderDrawer(id);
  highlightNeighbors(id);
  network.focus(id, {{ scale: 1.15, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
}}

function highlightNeighbors(id) {{
  const target = paperInfo[id];
  if (!target) return;
  const keep = new Set([id, ...target.outgoing, ...target.incoming]);

  network.body.data.nodes.getIds().forEach(nid => {{
    network.body.data.nodes.update({{ id: nid, opacity: keep.has(nid) ? 1.0 : 0.12 }});
  }});

  network.body.data.edges.getIds().forEach(eid => {{
    const edge = network.body.data.edges.get(eid);
    const isOutgoing = edge.from === id;
    const isIncoming = edge.to === id;
    if (isOutgoing) {{
      network.body.data.edges.update({{ id: eid, color: {{ color: '#38BDF8', opacity: 1.0 }}, width: 2.4 }});
    }} else if (isIncoming) {{
      network.body.data.edges.update({{ id: eid, color: {{ color: '#34D399', opacity: 1.0 }}, width: 2.4 }});
    }} else {{
      network.body.data.edges.update({{ id: eid, color: {{ color: 'rgba(148, 163, 184, 0.08)', opacity: 0.08 }}, width: 0.6 }});
    }}
  }});
}}

function resetHighlight() {{
  network.body.data.nodes.getIds().forEach(nid => {{
    network.body.data.nodes.update({{ id: nid, opacity: 1.0 }});
  }});
  network.body.data.edges.getIds().forEach(eid => {{
    network.body.data.edges.update({{ id: eid, color: {{ color: 'rgba(148, 163, 184, 0.28)', opacity: 0.4 }}, width: 1.2 }});
  }});
}}

// Color Mode Switcher
document.getElementById('color-mode-select').onchange = (e) => {{
  activeMode = e.target.value;
  document.getElementById('legend-cluster-view').style.display = activeMode === 'cluster' ? 'block' : 'none';
  document.getElementById('legend-role-view').style.display = activeMode === 'role' ? 'block' : 'none';
  document.getElementById('legend-year-view').style.display = activeMode === 'year' ? 'block' : 'none';

  network.body.data.nodes.getIds().forEach(nid => {{
    const isSeed = paperInfo[nid]?.role === 'seed';
    let bg = isSeed ? '#F59E0B' : colorMaps[nid][activeMode];
    network.body.data.nodes.update({{ id: nid, color: {{ background: bg, border: isSeed ? '#FFFFFF' : '#E2E8F0' }} }});
  }});
}};

// Controls
document.getElementById('btn-fit').onclick = () => network.fit({{ animation: true }});

document.getElementById('btn-physics').onclick = () => {{
  physicsFrozen = !physicsFrozen;
  network.setOptions({{ physics: {{ enabled: !physicsFrozen }} }});
  document.getElementById('btn-physics').textContent = physicsFrozen ? '▶ Physics' : '⏸ Freeze';
}};

document.getElementById('btn-reset').onclick = resetHighlight;

// Search Input
const searchInput = document.getElementById('paper-search');
searchInput.addEventListener('input', (e) => {{
  const query = e.target.value.trim().toLowerCase();
  if (!query) {{
    resetHighlight();
    return;
  }}
  const matched = new Set();
  Object.values(paperInfo).forEach(p => {{
    if (p.title.toLowerCase().includes(query) || p.authors.toLowerCase().includes(query) || p.journal.toLowerCase().includes(query)) {{
      matched.add(p.id);
    }}
  }});

  network.body.data.nodes.getIds().forEach(nid => {{
    network.body.data.nodes.update({{ id: nid, opacity: matched.has(nid) ? 1.0 : 0.12 }});
  }});
}});

// Keyboard Shortcuts
window.addEventListener('keydown', (e) => {{
  if (e.key === 'Escape') {{
    searchInput.value = '';
    resetHighlight();
  }}
}});

// Make Legend Draggable
function makeDraggable(el) {{
  let active = false, dx = 0, dy = 0;
  el.onmousedown = (e) => {{
    if (['SELECT', 'INPUT', 'A', 'BUTTON'].includes(e.target.tagName)) return;
    active = true;
    dx = e.clientX - el.offsetLeft;
    dy = e.clientY - el.offsetTop;
  }};
  document.addEventListener('mousemove', (e) => {{
    if (active) {{
      el.style.left = (e.clientX - dx) + 'px';
      el.style.top = (e.clientY - dy) + 'px';
      el.style.right = 'auto';
    }}
  }});
  document.addEventListener('mouseup', () => active = false);
}}
makeDraggable(document.getElementById('legend-panel'));
</script>
"""


def write_static(graph: nx.DiGraph, output_stem: Path, title: str) -> tuple[Path, Path]:
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans", "Arial", "Helvetica"],
        "axes.unicode_minus": False,
        "font.size": 8,
        "svg.fonttype": "none",
        "savefig.dpi": 300,
    })
    pos = nx.kamada_kawai_layout(graph, weight=None, scale=1.0)
    rows = {node_id: attrs["row"] for node_id, attrs in graph.nodes(data=True)}
    communities = detect_communities(graph)

    regular = [node_id for node_id, row in rows.items() if row.get("IsSeed") != "1"]
    seeds = [node_id for node_id, row in rows.items() if row.get("IsSeed") == "1"]

    colors = [CLUSTER_PALETTE[communities.get(nid, 0) % len(CLUSTER_PALETTE)] for nid in regular]
    sizes = [38 + 18 * math.log1p(int(float(rows[node_id].get("CitedByCount") or 0))) for node_id in regular]

    fig, ax = plt.subplots(figsize=(14, 9.5), facecolor="#0F172A")
    ax.set_facecolor("#0F172A")

    nx.draw_networkx_edges(
        graph,
        pos,
        ax=ax,
        arrows=True,
        arrowsize=8,
        width=0.65,
        alpha=0.25,
        edge_color="#94A3B8",
        connectionstyle="arc3,rad=.06",
    )
    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=regular,
        node_color=colors,
        node_size=sizes,
        edgecolors="#F8FAFC",
        linewidths=0.8,
        ax=ax,
    )
    if seeds:
        nx.draw_networkx_nodes(
            graph,
            pos,
            nodelist=seeds,
            node_color="#F59E0B",
            node_shape="*",
            node_size=820,
            edgecolors="#FFFFFF",
            linewidths=1.8,
            ax=ax,
        )

    # Label seed + top adjusted-score papers
    ranked = sorted(regular, key=lambda nid: float(rows[nid].get("AdjustedScore") or 0), reverse=True)[:8]
    labels = {nid: f"{first_author(rows[nid].get('Authors',''))} ({rows[nid].get('Year','')})" for nid in ranked}
    labels.update({nid: "[SEED]" for nid in seeds})

    nx.draw_networkx_labels(
        graph,
        pos,
        labels=labels,
        ax=ax,
        font_size=7.5,
        font_color="#FFFFFF",
        bbox={"boxstyle": "round,pad=.22", "facecolor": "#0F172A", "edgecolor": "#334155", "alpha": 0.85},
    )

    cluster_counts: dict[int, int] = {}
    for cid in communities.values():
        cluster_counts[cid] = cluster_counts.get(cid, 0) + 1

    handles = [
        Line2D([0], [0], marker="o", linestyle="", markersize=7, markerfacecolor=CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)], markeredgecolor="#F8FAFC", label=f"Cluster {cid+1} ({cnt})")
        for cid, cnt in sorted(cluster_counts.items())[:6]
    ]
    handles.insert(0, Line2D([0], [0], marker="*", linestyle="", markersize=11, markerfacecolor="#F59E0B", markeredgecolor="#FFFFFF", label="Seed Paper"))

    ax.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.04),
        ncol=min(7, len(handles)),
        frameon=False,
        fontsize=7.5,
        labelcolor="#E2E8F0",
    )
    ax.set_title(title, fontsize=13, color="#FFFFFF", pad=18, fontweight="bold")
    ax.text(0.01, 0.01, "Arrow: citing -> cited | Generated by Mogua", transform=ax.transAxes, fontsize=7.5, color="#64748B")
    ax.set_axis_off()

    fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.08)
    png = output_stem.with_suffix(".png")
    svg = output_stem.with_suffix(".svg")
    fig.savefig(png, facecolor=fig.get_facecolor(), bbox_inches="tight")
    fig.savefig(svg, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return png, svg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mogua Enhanced Citation-Network Visualization")
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output stem for HTML/PNG/SVG")
    parser.add_argument("--font-scale", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    nodes = read_rows(args.nodes)
    edges = read_rows(args.edges)
    if not nodes:
        raise ValueError("nodes CSV is empty")
    graph = build_graph(nodes, edges)
    seed = next((row for row in nodes if row.get("IsSeed") == "1"), nodes[0])
    title = seed.get("Title") or "Core Citation Network"

    write_interactive(graph, args.output.with_suffix(".html"), title)
    write_static(graph, args.output, title)
    print(json.dumps({"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
