#!/usr/bin/env python3
"""Render a Cube.dev semantic model graph to a PNG.

Reads a JSON spec from stdin (see SKILL.md for the schema) and writes a dark-themed
directed-graph PNG to --output. Layout is automatic: the fact spine sits centered;
dimensions are evenly distributed in a ring around it.
"""

import argparse
import json
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

INDIGO = "#6366f1"
SKY = "#0ea5e9"
BG = "#0f1117"
NODE_FILL = "#1e293b"
TITLE_FG = "#f1f5f9"
SUB_FG = "#94a3b8"
LEGEND_FG = "#64748b"

W, H = 13.0, 7.0
SPINE_CENTER = (W / 2, H / 2)
DIM_RADIUS_X = 4.6
DIM_RADIUS_Y = 2.2


def draw_node(ax, cx, cy, w, h, title, subtitle_lines, tag, border, tag_color):
    box = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.05", linewidth=2,
        edgecolor=border, facecolor=NODE_FILL, zorder=3,
    )
    ax.add_patch(box)
    ax.text(cx, cy + h / 2 - 0.28, tag, ha="center", va="top",
            fontsize=7.5, fontweight="bold", color=tag_color,
            fontfamily="monospace", zorder=4)
    ax.text(cx, cy + 0.12, title, ha="center", va="center",
            fontsize=9.5, fontweight="bold", color=TITLE_FG, zorder=4)
    for i, line in enumerate(subtitle_lines):
        ax.text(cx, cy - 0.32 - i * 0.32, line, ha="center", va="center",
                fontsize=8, color=SUB_FG, zorder=4)


def draw_edge(ax, x1, y1, x2, y2, label, from_card, to_card, color):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="->", color=color, lw=1.8,
                        connectionstyle="arc3,rad=0.0"),
        zorder=2,
    )
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(-dy, dx) or 1.0
    ox, oy = -dy / length * 0.22, dx / length * 0.22
    ax.text(mx + ox, my + oy, label, ha="center", va="center",
            fontsize=7.5, color=LEGEND_FG, zorder=4)
    # cardinality markers near each endpoint
    ax.text(x1 + dx * 0.08, y1 + dy * 0.08 + 0.18, from_card,
            ha="center", va="center", fontsize=11, fontweight="bold",
            color=SUB_FG, zorder=5)
    ax.text(x2 - dx * 0.08, y2 - dy * 0.08 + 0.18, to_card,
            ha="center", va="center", fontsize=11, fontweight="bold",
            color=SUB_FG, zorder=5)


def fact_subtitle_lines(spine):
    lines = [f"PK: {spine['pk']}"] if spine.get("pk") else []
    fks = spine.get("fks") or []
    # pack FKs two per line
    for i in range(0, len(fks), 2):
        chunk = fks[i:i + 2]
        lines.append("FK: " + "  ·  ".join(chunk))
    return lines


def dim_subtitle_lines(dim):
    lines = []
    if dim.get("pk"):
        lines.append(f"PK: {dim['pk']}")
    if dim.get("extras"):
        lines.append("  ·  ".join(dim["extras"]))
    return lines


def dim_position(i, n):
    # Distribute dims evenly around an ellipse centered on the spine.
    # Start from the left (angle = π) and go clockwise so a single dim sits left.
    angle = math.pi - (2 * math.pi * i / n)
    cx = SPINE_CENTER[0] + DIM_RADIUS_X * math.cos(angle)
    cy = SPINE_CENTER[1] + DIM_RADIUS_Y * math.sin(angle)
    return cx, cy


def edge_endpoints(src, dst, src_w=3.0, src_h=1.6, dst_w=3.2, dst_h=2.0):
    # Stop the arrow at the bounding boxes so it doesn't overlap node text.
    sx, sy = src
    dx, dy = dst
    vx, vy = dx - sx, dy - sy
    length = math.hypot(vx, vy) or 1.0
    ux, uy = vx / length, vy / length
    # rough rectangular inset — works fine for the box sizes we use
    src_inset = max(src_w / 2 * abs(ux), src_h / 2 * abs(uy))
    dst_inset = max(dst_w / 2 * abs(ux), dst_h / 2 * abs(uy))
    return (sx + ux * src_inset, sy + uy * src_inset,
            dx - ux * dst_inset, dy - uy * dst_inset)


def render(spec, output_path):
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    spine = spec["fact_spine"]
    dims = spec.get("dimensions", [])
    edges = spec.get("edges", [])

    # nodes
    draw_node(ax, *SPINE_CENTER, 3.2, 2.0,
              spine["name"], fact_subtitle_lines(spine),
              "FACT SPINE", INDIGO, "#818cf8")

    positions = {spine["name"]: SPINE_CENTER}
    n = max(len(dims), 1)
    for i, dim in enumerate(dims):
        cx, cy = dim_position(i, n)
        positions[dim["name"]] = (cx, cy)
        draw_node(ax, cx, cy, 3.0, 1.6,
                  dim["name"], dim_subtitle_lines(dim),
                  "DIMENSION", SKY, "#38bdf8")

    # edges
    for e in edges:
        src = positions.get(e["from"])
        dst = positions.get(e["to"])
        if not src or not dst:
            continue
        x1, y1, x2, y2 = edge_endpoints(src, dst)
        draw_edge(ax, x1, y1, x2, y2,
                  e.get("label", ""),
                  e.get("from_card", "1"),
                  e.get("to_card", "∞"),
                  SKY)

    # title
    ax.text(W / 2, H - 0.3, spec.get("title", "Semantic Model"),
            ha="center", va="center", fontsize=12,
            fontweight="bold", color="#e2e8f0")

    # legend
    for i, (col, lbl) in enumerate([(INDIGO, "Fact spine"),
                                    (SKY, "Dimension / edge")]):
        lx = 4.0 + i * 2.8
        ax.plot([lx, lx + 0.5], [0.35, 0.35], color=col, lw=2.5)
        ax.text(lx + 0.65, 0.35, lbl, va="center", fontsize=8, color=LEGEND_FG)
    ax.text(10.5, 0.35, "1 = one side   ∞ = many side",
            va="center", fontsize=8, color=LEGEND_FG)

    plt.tight_layout(pad=0.3)
    plt.savefig(output_path, dpi=160, bbox_inches="tight", facecolor=BG)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Path to write the PNG.")
    parser.add_argument("--input", default="-",
                        help="JSON spec path, or '-' for stdin (default).")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input).read()
    spec = json.loads(raw)
    render(spec, args.output)


if __name__ == "__main__":
    main()
