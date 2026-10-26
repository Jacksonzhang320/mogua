from __future__ import annotations

r"""Core citation-network plot.

Standard network template copy with DOI labels, seed highlighting,
and citation-count size mapping.
"""

import argparse
import csv
import html
import json
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import networkx as nx


FONT_SCALE = 1.0


def fs(base_size: float) -> float:
    return base_size * FONT_SCALE


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def short_author(authors: str) -> str:
    if not authors:
        return "Unknown"
    first = authors.split(";")[0].strip()
    if "," in first:
        return first.split(",", 1)[0].strip()
    return first.split()[-1] if first.split() else "Unknown"


def build_graph(nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for row in nodes:
        graph.add_node(row["Id"], **row)
    for row in edges:
        if row["Source"] in graph and row["Target"] in graph:
            graph.add_edge(row["Source"], row["Target"])
    return graph


def temporal_layout(nodes: list[dict[str, str]]) -> dict[str, tuple[float, float]]:
    groups: dict[int, list[dict[str, str]]] = {}
    fallback_year = max((int(row["Year"] or 0) for row in nodes), default=2000)
    for row in nodes:
        year = int(row["Year"] or fallback_year)
        groups.setdefault(year, []).append(row)
    positions: dict[str, tuple[float, float]] = {}
    for year, rows in sorted(groups.items()):
        rows.sort(key=lambda row: float(row["AdjustedScore"] or 0), reverse=True)
        center = (len(rows) - 1) / 2
        year_offset = ((year % 3) - 1) * 0.34
        for index, row in enumerate(rows):
            positions[row["Id"]] = (float(year), (center - index) * 1.15 + year_offset)
    return positions


def draw(nodes_path: Path, edges_path: Path, output: Path) -> tuple[Path, Path, Path]:
    nodes = read_csv(nodes_path)
    edges = read_csv(edges_path)
    if not nodes:
        raise ValueError("nodes_core.csv is empty")
    graph = build_graph(nodes, edges)
    pos = temporal_layout(nodes)

    years = [int(row["Year"] or 0) for row in nodes]
    valid_years = [year for year in years if year]
    min_year = min(valid_years) if valid_years else 2000
    max_year = max(valid_years) if valid_years else min_year + 1
    norm = mpl.colors.Normalize(vmin=min_year, vmax=max(max_year, min_year + 1))
    cmap = mpl.colormaps["viridis"]
    colors = ["#D62728" if row["IsSeed"] == "1" else cmap(norm(int(row["Year"] or min_year))) for row in nodes]
    sizes = [260 if row["IsSeed"] == "1" else 55 + 30 * math.log1p(int(row["CitedByCount"] or 0)) for row in nodes]
    labels = {
        row["Id"]: ("SEED " if row["IsSeed"] == "1" else "") + f"{short_author(row['Authors'])} {row['Year']}"
        for row in nodes
    }

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "font.size": fs(8),
            "svg.fonttype": "none",
            "savefig.dpi": 300,
        }
    )
    fig, ax = plt.subplots(figsize=(16, 10))
    nx.draw_networkx_edges(
        graph,
        pos,
        ax=ax,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=7,
        width=0.55,
        alpha=0.22,
        edge_color="#6B7280",
        connectionstyle="arc3,rad=0.035",
    )
    nx.draw_networkx_nodes(
        graph,
        pos,
        ax=ax,
        node_size=sizes,
        node_color=colors,
        linewidths=0.7,
        edgecolors="white",
        alpha=0.92,
    )
    label_pos = {node_id: (point[0] + 0.10, point[1] + 0.10) for node_id, point in pos.items()}
    nx.draw_networkx_labels(
        graph,
        label_pos,
        labels=labels,
        ax=ax,
        font_size=fs(6.2),
        font_color="#111827",
        horizontalalignment="left",
        verticalalignment="bottom",
    )
    seed = next((row for row in nodes if row["IsSeed"] == "1"), nodes[0])
    ax.set_title(
        f"Citation network core\n{seed['Title']}",
        fontsize=fs(12),
        pad=fs(12),
    )
    ax.text(
        0.01,
        0.01,
        "Arrow: citing paper → cited paper  |  Color: publication year  |  Size: citations",
        transform=ax.transAxes,
        fontsize=fs(7),
        color="#4B5563",
    )
    ax.set_axis_off()
    fig.subplots_adjust(left=0.025, right=0.985, bottom=0.045, top=0.88)
    output.parent.mkdir(parents=True, exist_ok=True)
    png = output.with_suffix(".png")
    svg = output.with_suffix(".svg")
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    plt.close(fig)

    html_path = output.with_suffix(".html")
    html_path.write_text(_build_html(nodes, edges, pos, seed), encoding="utf-8")
    return png, svg, html_path


def _build_html(
    nodes: list[dict[str, str]],
    edges: list[dict[str, str]],
    pos: dict[str, object],
    seed: dict[str, str],
) -> str:
    width, height = 1200, 850
    coords = {}
    for node_id, point in pos.items():
        coords[node_id] = {"x": 80 + (float(point[0]) + 1) * (width - 160) / 2, "y": 80 + (1 - float(point[1])) * (height - 160) / 2}
    lines = []
    for edge in edges:
        if edge["Source"] not in coords or edge["Target"] not in coords:
            continue
        a, b = coords[edge["Source"]], coords[edge["Target"]]
        lines.append(f'<line x1="{a["x"]:.1f}" y1="{a["y"]:.1f}" x2="{b["x"]:.1f}" y2="{b["y"]:.1f}"/>')
    circles = []
    for row in nodes:
        p = coords[row["Id"]]
        radius = 12 if row["IsSeed"] == "1" else min(11, 4 + math.log1p(int(row["CitedByCount"] or 0)))
        color = "#D62728" if row["IsSeed"] == "1" else "#2F6B9A"
        tip = "\n".join(
            [row["Title"], row["Authors"], f"{row['Journal']} ({row['Year']})", f"Citations: {row['CitedByCount']}", f"DOI: {row['DOI']}"]
        )
        circles.append(
            f'<a href="https://doi.org/{html.escape(row["DOI"])}" target="_blank">'
            f'<circle cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="{radius:.1f}" fill="{color}"><title>{html.escape(tip)}</title></circle></a>'
        )
    payload = json.dumps({"nodes": len(nodes), "edges": len(edges)}, ensure_ascii=False)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Citation network</title>
<style>body{{font-family:Arial,sans-serif;margin:20px;color:#111827}} svg{{border:1px solid #ddd;background:#fff}} line{{stroke:#9ca3af;stroke-width:.8;opacity:.5}} circle{{stroke:white;stroke-width:1;cursor:pointer}}</style></head>
<body><h2>{html.escape(seed['Title'])}</h2><p>{payload}. Hover for metadata; click a node to open its DOI.</p>
<svg viewBox="0 0 {width} {height}" width="100%" role="img">{''.join(lines)}{''.join(circles)}</svg></body></html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standard citation-network plot")
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font-scale", type=float, default=1.0)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    FONT_SCALE = args.font_scale
    draw(args.nodes, args.edges, args.output)
