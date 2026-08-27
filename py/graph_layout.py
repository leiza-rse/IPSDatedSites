"""
IPS Dated Sites — a small graph renderer with no external tools
===============================================================

Draws directed graphs in the idiom rdf-grapher made familiar: resources as
ellipses, literals as boxes, edge labels as predicates. Layout is a plain
layered (Sugiyama-style) arrangement — rank by longest path, order within
a rank by repeated barycentre sweeps — and the drawing is done by
matplotlib, which the pipeline already requires.

WHY NOT GRAPHVIZ
----------------
`dot` draws these better than this module does. It is also a system
package that is not present on the Windows machine where the rest of this
work happens, which turned "regenerate the figures" into "first install a
C library". A figure that cannot be regenerated where it is used is not
really generated from code; it is committed by hand with extra steps.

So the trade is deliberate: slightly worse layout, in exchange for the
whole talk folder being reproducible from `python py/...` on any machine
that can already run the pipeline. Nothing here needs a browser, a binary
or a network.

DETERMINISM
-----------
Every ordering decision falls back to a stable key, and the barycentre
sweeps run a fixed number of times rather than to convergence, so the same
graph always produces the same picture. Together with SOURCE_DATE_EPOCH and
a fixed svg.hashsalt in the caller, that makes the SVGs byte-stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import matplotlib
matplotlib.use("Agg")

# Without a fixed salt matplotlib randomises the clip-path identifiers in
# every SVG it writes, so two runs over an unchanged graph produce files
# that differ in a hundred places and agree in every pixel. Same value as
# py/ips_render.py uses for the corpus figures.
matplotlib.rcParams["svg.hashsalt"] = "ips-dated-sites"

from matplotlib.figure import Figure  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch  # noqa: E402
from matplotlib.path import Path  # noqa: E402

# Points. The whole layout is computed in typographic points and the
# figure is sized to match, so a font size here means the same thing in
# the finished file.
PAD_X, PAD_Y = 11.0, 7.0        # inside a node, around its text
NODE_SEP = 16.0                 # between nodes in the same rank
RANK_SEP = 96.0                 # between ranks, leaves room for edge labels
MARGIN = 26.0
LINE_H = 1.32                   # line spacing, multiples of the font size
LABEL_T = (0.34, 0.46, 0.26, 0.58, 0.40, 0.20, 0.66, 0.52, 0.72)
DUMMY_H = 10.0                  # the space a waypoint reserves in its rank

FONT_NODE = 9.0
FONT_EDGE = 7.6
FONT_TITLE = 12.0

INK = "#1b2430"
EDGE_COLOUR = "#5d6a78"
EDGE_TEXT = "#39434d"


@dataclass
class Node:
    key: str
    lines: list[str]
    shape: str = "ellipse"          # "ellipse" | "box" | "note"
    fill: str = "#eef1f5"
    line: str = "#8a857a"
    w: float = 0.0
    h: float = 0.0
    x: float = 0.0
    y: float = 0.0
    rank: int = 0
    order: float = 0.0


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    dashed: bool = False
    via: list[str] = field(default_factory=list)   # dummy nodes, see _route


@dataclass
class DiGraph:
    # No title. A caption belongs beside the figure, in talk/captions.yaml,
    # not burnt into the picture: a slide has its own heading, and a heading
    # inside the image competes with it and cannot be translated.
    rankdir: str = "LR"             # "LR" | "TB"
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, key, lines, **kw) -> None:
        if key not in self.nodes:
            self.nodes[key] = Node(key=key, lines=list(lines), **kw)

    def add_edge(self, src, dst, label="", dashed=False) -> None:
        self.edges.append(Edge(src, dst, label, dashed))


# --------------------------------------------------------------------------
# Measuring
# --------------------------------------------------------------------------
_RENDERER = None


def _renderer():
    """One Agg renderer, reused. At 72 dpi its pixels are points."""
    global _RENDERER
    if _RENDERER is None:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        fig = Figure(dpi=72)
        FigureCanvasAgg(fig)
        _RENDERER = fig.canvas.get_renderer()
    return _RENDERER


def _measure(text: str, size: float) -> tuple[float, float]:
    """Width and height of one line, in points."""
    w, h, _d = _renderer().get_text_width_height_descent(
        text, FontProperties(size=size), False)
    return float(w), float(h)


def _size_nodes(g: DiGraph) -> None:
    for n in g.nodes.values():
        widths, heights = [], []
        for line in n.lines:
            w, h = _measure(line, FONT_NODE)
            widths.append(w)
            heights.append(h)
        text_w = max(widths) if widths else 0.0
        text_h = (max(heights) if heights else FONT_NODE) * LINE_H * len(n.lines)
        if n.shape == "ellipse":
            # An ellipse has to be wider than its text to contain it: the
            # corners of the bounding box stick out. sqrt(2) is the exact
            # factor for a box inscribed in an ellipse.
            n.w = text_w * 1.42 + PAD_X
            n.h = text_h * 1.42 + PAD_Y
        else:
            n.w = text_w + 2 * PAD_X
            n.h = text_h + 2 * PAD_Y


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
def _rank(g: DiGraph) -> None:
    """Longest-path layering, with cycles broken by first-seen order."""
    incoming: dict[str, list[str]] = {k: [] for k in g.nodes}
    outgoing: dict[str, list[str]] = {k: [] for k in g.nodes}
    for e in g.edges:
        if e.src in g.nodes and e.dst in g.nodes:
            incoming[e.dst].append(e.src)
            outgoing[e.src].append(e.dst)

    rank: dict[str, int] = {}
    order = list(g.nodes)                 # insertion order: stable

    # Kahn's algorithm; anything left over is in a cycle and is placed
    # after whatever it depends on that was already settled.
    pending = {k: len(set(incoming[k])) for k in order}
    queue = [k for k in order if pending[k] == 0]
    while queue:
        k = queue.pop(0)
        rank[k] = max((rank[p] + 1 for p in incoming[k] if p in rank),
                      default=0)
        for d in outgoing[k]:
            pending[d] -= 1
            if pending[d] == 0:
                queue.append(d)
    for k in order:                       # cycle remnants
        if k not in rank:
            rank[k] = max((rank[p] + 1 for p in incoming[k] if p in rank),
                          default=0)
    for k, r in rank.items():
        g.nodes[k].rank = r


def _route(g: DiGraph) -> None:
    """Give every long edge a waypoint in each rank it crosses.

    Without this an edge from rank 0 to rank 4 is drawn as one straight
    line across four columns of nodes, and it goes through whatever stands
    in the way. The waypoints are ordinary nodes as far as the layout is
    concerned — they take part in the barycentre sweeps and so get pushed
    into the gaps between real nodes — but they are never drawn. This is
    the one step that separates a readable layered drawing from a pile of
    diagonals, and it is why GraphViz output looks the way it does.
    """
    made = 0
    for e in g.edges:
        if e.src not in g.nodes or e.dst not in g.nodes:
            continue
        r0, r1 = g.nodes[e.src].rank, g.nodes[e.dst].rank
        if r1 - r0 <= 1:
            continue
        for r in range(r0 + 1, r1):
            key = f"__via{made}"
            made += 1
            g.nodes[key] = Node(key=key, lines=[], shape="dummy",
                                w=1.0, h=DUMMY_H, rank=r)
            e.via.append(key)


def _segments(g: DiGraph) -> list[tuple[str, str]]:
    """Edges as they look to the layout: broken at every waypoint."""
    out = []
    for e in g.edges:
        if e.src not in g.nodes or e.dst not in g.nodes:
            continue
        chain = [e.src] + e.via + [e.dst]
        out += list(zip(chain, chain[1:]))
    return out


def _order_within_ranks(g: DiGraph, sweeps: int = 14) -> dict[int, list[str]]:
    ranks: dict[int, list[str]] = {}
    for k, n in g.nodes.items():
        ranks.setdefault(n.rank, []).append(k)

    pos = {k: float(i) for r in ranks for i, k in enumerate(ranks[r])}
    pred: dict[str, list[str]] = {k: [] for k in g.nodes}
    succ: dict[str, list[str]] = {k: [] for k in g.nodes}
    for a, b in _segments(g):
        pred[b].append(a)
        succ[a].append(b)

    for s in range(sweeps):
        neigh = pred if s % 2 == 0 else succ
        for r in sorted(ranks, reverse=(s % 2 == 1)):
            keys = ranks[r]
            bary = {}
            for k in keys:
                ns = [pos[m] for m in neigh[k] if m in pos]
                # No neighbour on that side: keep where you were, so a
                # detached node does not wander between sweeps.
                bary[k] = sum(ns) / len(ns) if ns else pos[k]
            keys.sort(key=lambda k: (bary[k], k))
            for i, k in enumerate(keys):
                pos[k] = float(i)

    for r in ranks:
        for i, k in enumerate(ranks[r]):
            g.nodes[k].order = float(i)
    return ranks


def _place(g: DiGraph, ranks: dict[int, list[str]]) -> tuple[float, float]:
    """Ranks run along the flow direction, nodes stack across it."""
    top_down = g.rankdir == "TB"

    # "across" is height in a left-to-right drawing and width in a
    # top-down one; everything below is written once in those terms.
    def across(n: Node) -> float:
        return n.w if top_down else n.h

    def along(n: Node) -> float:
        return n.h if top_down else n.w

    spans = {}
    for r in sorted(ranks):
        keys = ranks[r]
        spans[r] = (sum(across(g.nodes[k]) for k in keys)
                    + NODE_SEP * (len(keys) - 1))
    widest = max(spans.values()) if spans else 0.0

    pos_along = MARGIN
    for r in sorted(ranks):
        keys = ranks[r]
        thickness = max(along(g.nodes[k]) for k in keys)
        pos_across = (widest - spans[r]) / 2.0 + MARGIN
        for k in keys:
            n = g.nodes[k]
            if top_down:
                n.x = pos_across + n.w / 2.0
                n.y = pos_along + thickness / 2.0
            else:
                n.x = pos_along + thickness / 2.0
                n.y = pos_across + n.h / 2.0
            pos_across += across(n) + NODE_SEP
        pos_along += thickness + RANK_SEP

    extent_along = pos_along - RANK_SEP + MARGIN
    extent_across = widest + 2 * MARGIN

    if top_down:
        # Rank 0 at the top: the canvas y axis points up, so flip.
        for n in g.nodes.values():
            n.y = extent_along - n.y
        return extent_across, extent_along
    return extent_along, extent_across


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def _boundary(n: Node, towards: tuple[float, float]) -> tuple[float, float]:
    """Where an edge should meet the node outline, not its centre."""
    import math
    dx, dy = towards[0] - n.x, towards[1] - n.y
    if dx == 0 and dy == 0:
        return n.x, n.y
    if n.shape == "ellipse":
        a, b = n.w / 2.0, n.h / 2.0
        t = math.hypot(dx / a, dy / b)
        return n.x + dx / t, n.y + dy / t
    # rectangle
    a, b = n.w / 2.0, n.h / 2.0
    tx = a / abs(dx) if dx else float("inf")
    ty = b / abs(dy) if dy else float("inf")
    t = min(tx, ty)
    return n.x + dx * t, n.y + dy * t


def render(g: DiGraph, svg_path, jpg_path, dpi: int = 300) -> list:
    _size_nodes(g)
    _rank(g)
    _route(g)
    ranks = _order_within_ranks(g)
    width, height = _place(g, ranks)

    fig = Figure(figsize=(width / 72.0, height / 72.0), dpi=100)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis("off")

    # Edges first, so a node always sits on top of its own arrows.
    segments = []
    for e in g.edges:
        if e.src not in g.nodes or e.dst not in g.nodes:
            continue
        chain = [g.nodes[k] for k in ([e.src] + e.via + [e.dst])]
        pts = [(n.x, n.y) for n in chain]
        pts[0] = _boundary(chain[0], pts[1])
        pts[-1] = _boundary(chain[-1], pts[-2])

        if len(pts) == 2:
            path = Path(pts, [Path.MOVETO, Path.LINETO])
        else:
            # A quadratic through each waypoint, with the control points at
            # the waypoints themselves and the joins at their midpoints:
            # the curve then passes smoothly through the corridor the
            # layout opened for it instead of turning corners in it.
            verts = [pts[0]]
            codes = [Path.MOVETO]
            for i in range(1, len(pts) - 1):
                nxt = pts[i + 1]
                mid = ((pts[i][0] + nxt[0]) / 2.0, (pts[i][1] + nxt[1]) / 2.0)
                end = nxt if i == len(pts) - 2 else mid
                verts += [pts[i], end]
                codes += [Path.CURVE3, Path.CURVE3]
            path = Path(verts, codes)

        ax.add_patch(FancyArrowPatch(
            path=path, arrowstyle="-|>", mutation_scale=9,
            linewidth=0.9, edgecolor=EDGE_COLOUR, facecolor="none",
            linestyle="--" if e.dashed else "-", zorder=1))
        if e.label:
            segments.append((e.label, pts[0], pts[1]))

    # Edge labels, placed so they do not sit on top of one another. A label
    # rides the FIRST segment of its edge — nearest the subject, which is
    # what the reader is following — sliding along it and stepping sideways
    # if that is crowded. Node boxes count as occupied from the start,
    # because a node is drawn on top and a label under one is invisible
    # rather than merely ugly. Waypoints do not: nothing is drawn there.
    placed: list[tuple[float, float, float, float]] = [
        (n.x - n.w / 2, n.y - n.h / 2, n.x + n.w / 2, n.y + n.h / 2)
        for n in g.nodes.values() if n.shape != "dummy"
    ]

    def _overlap(box) -> float:
        """How much of this box is already taken, in square points."""
        x0, y0, x1, y1 = box
        total = 0.0
        for q0, r0, q1, r1 in placed:
            dx = min(x1, q1) - max(x0, q0)
            dy = min(y1, r1) - max(y0, r0)
            if dx > 0 and dy > 0:
                total += dx * dy
        return total

    import math

    for label, p1, p2 in segments:
        w, h = _measure(label, FONT_EDGE)
        w += 5.0
        h += 4.0
        ux, uy = p2[0] - p1[0], p2[1] - p1[1]
        norm = math.hypot(ux, uy) or 1.0
        nx, ny = -uy / norm, ux / norm

        best, best_cost = None, None
        for t in LABEL_T:
            for off in (0.0, 1.0, -1.0):
                cx = p1[0] + ux * t + nx * off * h * 1.05
                cy = p1[1] + uy * t + ny * off * h * 1.05
                box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                cost = _overlap(box)
                if cost == 0.0:
                    best, best_cost = (cx, cy, box), 0.0
                    break
                if best_cost is None or cost < best_cost:
                    best, best_cost = (cx, cy, box), cost
            if best_cost == 0.0:
                break
        cx, cy, box = best
        placed.append(box)
        ax.text(cx, cy, label, fontsize=FONT_EDGE, color=EDGE_TEXT,
                ha="center", va="center", zorder=2,
                bbox=dict(boxstyle="round,pad=0.16", facecolor="white",
                          edgecolor="none", alpha=0.92))

    for n in g.nodes.values():
        if n.shape == "dummy":
            continue
        if n.shape == "ellipse":
            ax.add_patch(Ellipse((n.x, n.y), n.w, n.h, facecolor=n.fill,
                                 edgecolor=n.line, linewidth=0.9, zorder=3))
        else:
            ax.add_patch(FancyBboxPatch(
                (n.x - n.w / 2.0, n.y - n.h / 2.0), n.w, n.h,
                boxstyle="round,pad=0,rounding_size=2.5",
                facecolor=n.fill, edgecolor=n.line, linewidth=0.9, zorder=3))
        ax.text(n.x, n.y, "\n".join(n.lines), fontsize=FONT_NODE,
                color=INK, ha="center", va="center", zorder=4,
                linespacing=LINE_H)

    fig.savefig(svg_path, format="svg", facecolor="white")
    fig.savefig(jpg_path, format="jpg", dpi=dpi, facecolor="white")
    return [svg_path, jpg_path]
