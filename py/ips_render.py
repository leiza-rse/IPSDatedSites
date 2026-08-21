"""
IPS Dated Sites — two renderings of the same graph
==================================================

v1  classic  — the existing D3 figure one to one: box, whiskers with
               caps, extreme-value stubs, dashed box edges, RdYlGn colour
               ramp, gradient legend. Left untouched so that the web
               output and the print version stay consistent.

v2  modern   — the SAME encoding as v1, only set more carefully. The
               whiskers in particular keep their colour: q_start and
               q_end appear nowhere else in the picture, and a red
               whisker at the early Arretine findspots is a statement in
               its own right. What is modernised is the presentation —
               typography, spacing, a quieter grid, a BC/AD axis, a value
               table — not what is encoded.

Both take EVERY value from the graph, margins, row height and sort rule
included. Both write SVG and high-resolution JPG.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

# Byte-stable SVGs. Without this, matplotlib writes a fresh <dc:date>
# timestamp and freshly randomised element identifiers on every run, so
# that both figures ALWAYS appear modified in git. A file that is always
# modified is a file whose diff nobody reads any more — and a real change
# to a published figure then goes unnoticed.
os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
matplotlib.rcParamsDefault["svg.hashsalt"] = "ips-dated-sites"
matplotlib.rcParams["svg.hashsalt"] = "ips-dated-sites"

import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

CMAP = plt.get_cmap("RdYlGn")
NORM = Normalize(0, 1)
GREY = "#999999"
JPG_DPI = 300


# ---- second quality axis (lado:qRepetition) ------------------------------
# Half the height of the label band and twice the width of the first sketch:
# wide enough to read a difference, flat enough not to compete with the box.
REPETITION_BAR_PX = 48          # width, in figure pixels of the left margin
REPETITION_BAR_HEIGHT = 0.19    # height, in row units
REPETITION_COLOUR = "#4a6b96"

# How much wider the v1 time axis is than the web original. See the note
# in render_classic.
CLASSIC_AXIS_FACTOR = 2.0

# Height of the strip below the axis: tick labels plus the colour bar.
CLASSIC_FOOT_PX = 118


def colour(q):
    """Quality -> colour. None is a state of its own, not a failure."""
    return GREY if q is None else CMAP(NORM(q))


def year_label(v: float, era: str) -> str:
    """The source year as a calendar label."""
    y = int(round(v))
    if y < 0:
        return f"{abs(y) if era == 'historical' else abs(y) + 1} BC"
    if y == 0:
        return "1 BC" if era == "historical" else "0"
    return f"AD {y}"


def _save(fig, out_dir: Path, stem: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    svg = out_dir / f"{stem}.svg"
    fig.savefig(svg, format="svg", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    paths.append(svg)
    jpg = out_dir / f"{stem}.jpg"
    fig.savefig(jpg, format="jpg", dpi=JPG_DPI, bbox_inches="tight",
                facecolor=fig.get_facecolor(), pil_kwargs={"quality": 95})
    paths.append(jpg)
    plt.close(fig)
    return paths


# ==========================================================================
# v1 — classic
# ==========================================================================
def render_classic(fig_const: dict, rows: list[dict], era: str,
                   out_dir: Path, model: dict | None = None,
                   stem: str = "plot_v1_classic") -> list[Path]:
    n = len(rows)
    pad = fig_const["padYears"]
    stub = fig_const["extremeStubYears"]
    band = 1 - fig_const["bandPadding"]

    # The web figure is 1200 px wide because that suits a browser column.
    # In print the whisker value labels collided with the boxes, so the
    # TIME AXIS is widened by this factor while the margins stay as they
    # are: the labels then have room without the left column moving.
    #
    # A deliberate departure from the web original, and the only one in
    # v1. lado:svgWidth in the graph continues to describe the web figure,
    # which is what it was recorded from.
    plot_px = (fig_const["svgWidth"] - fig_const["marginLeft"]
               - fig_const["marginRight"])
    px_w = (fig_const["svgWidth"]
            + plot_px * (CLASSIC_AXIS_FACTOR - 1.0))
    # The web figure reserves 120 px below the axis for its own layout and
    # this reproduction then added 80 more for the legend, which left a
    # hand's width of nothing between the last row and the colour bar.
    # In print the foot only has to hold the tick labels and the bar.
    px_h = n * fig_const["rowHeight"] + fig_const["marginTop"] + CLASSIC_FOOT_PX
    fig = plt.figure(figsize=(px_w / 100, px_h / 100), dpi=100,
                     facecolor="white")

    left = fig_const["marginLeft"] / px_w
    right = 1 - fig_const["marginRight"] / px_w
    bottom = CLASSIC_FOOT_PX / px_h
    top = 1 - fig_const["marginTop"] / px_h
    ax = fig.add_axes((left, bottom, right - left, top - bottom))

    lo = min(r["effStart"] - r["uncStart"] for r in rows) - pad
    hi = max(r["effEnd"] + r["uncEnd"] for r in rows) + pad
    ax.set_xlim(lo, hi)
    ax.set_ylim(n, 0)

    ax.grid(axis="x", color="#999999", alpha=0.3, linestyle=(0, (4, 4)),
            linewidth=0.8)
    ax.set_axisbelow(True)
    if lo <= 0 <= hi:
        ax.axvline(0, color="black", alpha=0.4, linewidth=1)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_yticks([])
    ax.tick_params(axis="x", labelsize=10)

    tf = ax.get_yaxis_transform()

    # ---- second quality axis: die repetition, as a marginal bar ----------
    # qInterval already owns the box fill and qStart/qEnd own the whiskers,
    # so a third colour would compete with both. Length in the left margin
    # is the one channel still free. The bar says "hoard character", not
    # "better dated": Cologne harbour stands out because its stamps repeat,
    # not because its dating is sharper.
    bar_w = REPETITION_BAR_PX / (px_w * (right - left))
    bar_x = -0.012 - bar_w - 0.010
    label_x = bar_x - 0.012
    have_rep = any(r.get("qRepetition") is not None for r in rows)
    if not have_rep:
        bar_x = label_x = -0.012

    for i, r in enumerate(rows):
        cy = i + 0.5
        y0, y1 = cy - band / 2, cy + band / 2
        us, ue = r["uncStart"], r["uncEnd"]

        # Labels on the left: discovery site, findspot underneath
        ax.text(label_x, cy - 0.12, r["site"], transform=tf, ha="right",
                va="center", fontsize=11, color="black")
        ax.text(label_x, cy + 0.22, r["findspot"], transform=tf, ha="right",
                va="center", fontsize=9, color="#555555")

        # Repetition bar. The track is drawn even at zero, so an empty bar
        # reads as "no repetition" rather than as missing data, and the
        # half mark gives a short bar something to be short against.
        qr = r.get("qRepetition")
        if qr is not None:
            h = REPETITION_BAR_HEIGHT
            ax.add_patch(Rectangle((bar_x, cy - h / 2), bar_w, h,
                                   transform=tf, facecolor="#eef1f5",
                                   edgecolor="none", clip_on=False, zorder=2))
            ax.add_patch(Rectangle((bar_x, cy - h / 2), bar_w * qr, h,
                                   transform=tf, facecolor=REPETITION_COLOUR,
                                   edgecolor="none", clip_on=False, zorder=3))
            ax.plot([bar_x + bar_w / 2] * 2, [cy - h / 2, cy + h / 2],
                    transform=tf, color="#c4ccd6", linewidth=0.6,
                    clip_on=False, zorder=4)

        # Extreme-value stubs with caps
        ax.plot([r["minDatemin"], min(r["minDatemin"] + stub, r["effStart"])],
                [cy, cy], color="#555555", alpha=0.5, linewidth=1)
        ax.plot([max(r["maxDatemax"] - stub, r["effEnd"]), r["maxDatemax"]],
                [cy, cy], color="#555555", alpha=0.5, linewidth=1)
        for xv in (r["minDatemin"], r["maxDatemax"]):
            ax.plot([xv, xv], [cy - band * 0.15, cy + band * 0.15],
                    color="#333333", alpha=0.5, linewidth=1)

        # Whiskers with caps, coloured by q_start / q_end
        for xa, xb, q in ((r["effStart"], r["effStart"] - us, r["qStart"]),
                          (r["effEnd"], r["effEnd"] + ue, r["qEnd"])):
            c = colour(q)
            ax.plot([xa, xb], [cy, cy], color=c, linewidth=3, alpha=0.9,
                    solid_capstyle="butt")
            ax.plot([xb, xb], [cy - band * 0.25, cy + band * 0.25],
                    color=c, linewidth=3)

        # Box
        ax.add_patch(Rectangle((r["effStart"], y0),
                               r["effEnd"] - r["effStart"], band,
                               facecolor=colour(r["qInterval"]), alpha=0.8,
                               edgecolor="none", zorder=3))
        for yv in (y0, y1):
            ax.plot([r["effStart"], r["effEnd"]], [yv, yv], color="#333333",
                    linewidth=1, zorder=4)
        for xv, u in ((r["effStart"], us), (r["effEnd"], ue)):
            ax.plot([xv, xv], [y0, y1], color="#333333", linewidth=1,
                    linestyle=(0, (4, 2)) if u > 0 else "-", zorder=4)

        # Whisker-Beschriftung
        # A white plate under each label. The grey full-range stub runs
        # along the same y as the text, and without this it strikes
        # through the digits - the wider axis moved the labels apart but
        # did not move them off the stub.
        plate = dict(boxstyle="round,pad=0.18", facecolor="white",
                     edgecolor="none", alpha=0.92)
        if us > 0:
            q = f'{r["qStart"]:.2f}' if r["qStart"] is not None else "–"
            ax.annotate(f'{int(us)} (q={q})', (r["effStart"] - us, cy),
                        xytext=(-6, 0), textcoords="offset points",
                        ha="right", va="center", fontsize=9, bbox=plate,
                        zorder=8)
        if ue > 0:
            q = f'{r["qEnd"]:.2f}' if r["qEnd"] is not None else "–"
            ax.annotate(f'{int(ue)} (q={q})', (r["effEnd"] + ue, cy),
                        xytext=(6, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=9, bbox=plate,
                        zorder=8)

    # Gradientenlegende
    lax = fig.add_axes((left + (right - left - 0.21) / 2, 46 / px_h,
                        0.21, 12 / px_h))
    lax.imshow([[i / 255 for i in range(256)]], aspect="auto", cmap=CMAP,
               extent=(0, 1, 0, 1))
    lax.set_yticks([])
    lax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    lax.tick_params(labelsize=9)
    for s in lax.spines.values():
        s.set_edgecolor("black")
    lax.set_xlabel("Quality (0 = low, 1 = high)", fontsize=11, labelpad=6)

    # A heading over the bar column. Without it the strip is a decoration;
    # with it, it is a second reading of the same row.
    if have_rep:
        ax.text(bar_x + bar_w / 2, -0.35, "die\nrepetition", transform=tf,
                ha="center", va="bottom", fontsize=8, color="#5d6a78",
                linespacing=1.2, clip_on=False)

    return _save(fig, out_dir, stem)


# ==========================================================================
# v2 — modern
# ==========================================================================
# Deliberately NO new visual language. v2 shows exactly the same channels
# as v1:
#
#   Box            eff_start .. eff_end,  Fuellung = q_interval
#   Whisker        Unsicherheit links/rechts, Farbe = q_start / q_end
#   whisker cap    end of the uncertainty
#   stub + cap     min_datemin / max_datemax, the full range
#   box edge       dashed where an uncertainty applies
#
# The numbers no longer sit on the whisker but in the value table on the
# right. On the whisker they collided with the whisker itself as soon as
# the bars grew long.

INK = "#12181f"
MUTED = "#5d6a78"
FAINT = "#96a1ad"
HAIR = "#e3e7ea"
PAPER = "#ffffff"
BAND = "#f5f6f7"

# --------------------------------------------------------------------------
# Value table to the right of the time axis
# --------------------------------------------------------------------------
# Covers in full what the web application shows:
#   from the hover popup         : interval, n stamps, q(interval)
#   from the whisker labels      : year and q on BOTH sides
#                                  ("7 (q=0.71)" -> Spalten unc start / q start)
#
# With sigma added. That was NOT in the web output. It is the dispersion
# from the variance decomposition which, together with k, produces the box
# width: width = 2*k*sigma. Without it one sees how wide the box is but
# not why. To drop the column, delete the "sigma" line here — the
# positions of the others stay valid.
#
# x is in axes fractions, y in data coordinates. The rows therefore stay
# level with their bar automatically, with nothing to recompute.
TABLE_COLUMNS = [
    # (x, Ausrichtung, Kopf, Funktion)
    (1.040, "left",  "interval",
     lambda r, era: f'{year_label(r["effStart"], era)} – '
                    f'{year_label(r["effEnd"], era)}'),
    (1.350, "right", "n",         lambda r, era: f'{int(r["nStamps"])}'),
    (1.440, "right", "sigma",     lambda r, era: f'{r["sigma"]:.0f}'),
    (1.570, "right", "unc start", lambda r, era: f'{int(r["uncStart"])}'),
    (1.665, "right", "q start",
     lambda r, era: "–" if r["qStart"] is None else f'{r["qStart"]:.2f}'),
    (1.760, "right", "q int",
     lambda r, era: "–" if r["qInterval"] is None else f'{r["qInterval"]:.2f}'),
    (1.870, "right", "unc end",   lambda r, era: f'{int(r["uncEnd"])}'),
    (1.960, "right", "q end",
     lambda r, era: "–" if r["qEnd"] is None else f'{r["qEnd"]:.2f}'),
]
TAB_L, TAB_R = 1.025, 1.985


def render_modern(fig_const: dict, rows: list[dict], era: str,
                  out_dir: Path, model: dict | None = None,
                  stem: str = "plot_v2_modern") -> list[Path]:
    n = len(rows)
    pad = fig_const["padYears"]
    stub = fig_const["extremeStubYears"]

    row_h = 0.40                      # inches per row, airier than v1
    fig = plt.figure(figsize=(17.0, 1.9 + n * row_h), dpi=100,
                     facecolor=PAPER)
    # Keep the plotting area narrow: the value table sits to its right.
    # Achsenanteil 1.985 entspricht Figure-x 0.100 + 1.985*0.400 = 0.894.
    # The colour bar starts only at 0.945 and so does not collide.
    ax = fig.add_axes((0.100, 0.062, 0.400, 0.880))
    ax.set_facecolor(PAPER)

    lo = min(min(r["minDatemin"], r["effStart"] - r["uncStart"])
             for r in rows) - pad * 0.5
    hi = max(max(r["maxDatemax"], r["effEnd"] + r["uncEnd"])
             for r in rows) + pad * 0.5
    ax.set_xlim(lo, hi)
    ax.set_ylim(n - 0.5, -0.5)

    # A quiet grid: banding instead of vertical rules, fine hairlines in
    # the horizontal.
    for i in range(n):
        if i % 2:
            ax.add_patch(Rectangle((lo, i - 0.5), hi - lo, 1,
                                   facecolor=BAND, edgecolor="none",
                                   zorder=0))
    ax.grid(axis="x", color=HAIR, linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    if lo <= 0 <= hi:
        ax.axvline(0, color=FAINT, linewidth=1.0, linestyle=(0, (3, 3)),
                   zorder=2)

    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(HAIR)
    ax.set_yticks([])
    ax.tick_params(axis="x", colors=MUTED, labelsize=9.5, length=0, pad=6)
    ticks = [t for t in ax.get_xticks() if lo <= t <= hi]
    ax.set_xticks(ticks)
    ax.set_xticklabels([year_label(t, era) for t in ticks])

    bh = 0.30                          # Box height in row units
    tf = ax.get_yaxis_transform()

    # Repetition bar: same 48 px as v1, converted through this figure's
    # own axes width so it comes out the same size on paper rather than
    # the same size in axes fractions.
    m_have_rep = any(r.get("qRepetition") is not None for r in rows)
    m_bar_w = REPETITION_BAR_PX / (17.0 * 100 * 0.400)
    m_bar_x = -0.012 - m_bar_w - 0.008
    m_label_x = m_bar_x - 0.010
    if not m_have_rep:
        m_bar_x = m_label_x = -0.012

    for i, r in enumerate(rows):
        y0, y1 = i - bh / 2, i + bh / 2
        us, ue = r["uncStart"], r["uncEnd"]

        # --- Full range: stubs with caps ---
        ax.plot([r["minDatemin"], min(r["minDatemin"] + stub, r["effStart"])],
                [i, i], color=FAINT, linewidth=1.0, zorder=2)
        ax.plot([max(r["maxDatemax"] - stub, r["effEnd"]), r["maxDatemax"]],
                [i, i], color=FAINT, linewidth=1.0, zorder=2)
        for xv in (r["minDatemin"], r["maxDatemax"]):
            ax.plot([xv, xv], [i - bh * 0.42, i + bh * 0.42],
                    color=FAINT, linewidth=1.0, zorder=2)

        # --- Whisker: FARBIG nach q_start / q_end ---
        # A white halo underneath, so that the colour stays clear over the
        # banding and over the grid lines.
        for xa, xb, q in ((r["effStart"], r["effStart"] - us, r["qStart"]),
                          (r["effEnd"], r["effEnd"] + ue, r["qEnd"])):
            if xa == xb:
                continue
            c = colour(q)
            ax.plot([xa, xb], [i, i], color=PAPER, linewidth=5.0,
                    solid_capstyle="butt", zorder=3)
            ax.plot([xa, xb], [i, i], color=c, linewidth=3.0,
                    solid_capstyle="butt", zorder=4)
            ax.plot([xb, xb], [i - bh * 0.62, i + bh * 0.62],
                    color=PAPER, linewidth=5.0, zorder=3)
            ax.plot([xb, xb], [i - bh * 0.62, i + bh * 0.62],
                    color=c, linewidth=3.0, zorder=4)

        # --- Box: Fuellung nach q_interval ---
        w = max(r["effEnd"] - r["effStart"], (hi - lo) * 0.0015)
        ax.add_patch(Rectangle((r["effStart"], y0), w, bh,
                               facecolor=colour(r["qInterval"]),
                               edgecolor="none", zorder=5))
        # Edges: solid top and bottom, dashed at the sides where an
        # uncertainty applies — the same rule as v1.
        for yv in (y0, y1):
            ax.plot([r["effStart"], r["effEnd"]], [yv, yv], color=INK,
                    linewidth=0.9, zorder=6)
        for xv, u in ((r["effStart"], us), (r["effEnd"], ue)):
            ax.plot([xv, xv], [y0, y1], color=INK, linewidth=0.9,
                    linestyle=(0, (3, 2)) if u > 0 else "-", zorder=6)

        # --- Beschriftung links, hinter dem Wiederholungsbalken ---
        ax.text(m_label_x, i - 0.19, r["site"], transform=tf, ha="right",
                va="center", fontsize=10.5, color=INK)
        ax.text(m_label_x, i + 0.20, r["findspot"], transform=tf, ha="right",
                va="center", fontsize=8.4, color=MUTED)

        # --- Zweite Qualitaetsachse, wie in v1 ---
        # Same channel and same colour as the classic figure, so a reader
        # moving between the two does not have to relearn the mark. The
        # track is drawn at zero as well: an empty bar has to read as "no
        # repetition" rather than as a value that failed to arrive.
        qr = r.get("qRepetition")
        if qr is not None:
            h = REPETITION_BAR_HEIGHT * 0.65   # v2 rows are airier
            ax.add_patch(Rectangle((m_bar_x, i - h / 2), m_bar_w, h,
                                   transform=tf, facecolor=BAND,
                                   edgecolor="none", clip_on=False, zorder=3))
            ax.add_patch(Rectangle((m_bar_x, i - h / 2), m_bar_w * qr, h,
                                   transform=tf, facecolor=REPETITION_COLOUR,
                                   edgecolor="none", clip_on=False, zorder=4))
            ax.plot([m_bar_x + m_bar_w / 2] * 2, [i - h / 2, i + h / 2],
                    transform=tf, color=HAIR, linewidth=0.7,
                    clip_on=False, zorder=5)

    # ----------------------------------------------------------------
    # Wertetabelle
    # ----------------------------------------------------------------
    if m_have_rep:
        ax.text(m_bar_x + m_bar_w / 2, -0.95, "repetition", transform=tf,
                ha="center", va="center", fontsize=8.2, color=FAINT,
                clip_on=False)
    for x, ha, head, _ in TABLE_COLUMNS:
        ax.text(x, -0.95, head, transform=tf, ha=ha, va="center",
                fontsize=8.2, color=FAINT, clip_on=False)
    ax.plot([TAB_L, TAB_R], [-0.72, -0.72], transform=tf, color=HAIR,
            linewidth=0.9, clip_on=False, zorder=1)

    for i, r in enumerate(rows):
        if i % 2:   # Carry the banding through under the table
            ax.add_patch(Rectangle((TAB_L, i - 0.5), TAB_R - TAB_L, 1,
                                   transform=tf, facecolor=BAND,
                                   edgecolor="none", clip_on=False, zorder=0))
        for x, ha, _, fn in TABLE_COLUMNS:
            ax.text(x, i, fn(r, era), transform=tf, ha=ha, va="center",
                    fontsize=8.2, color=MUTED, clip_on=False, zorder=2)

    # --- Colour bar at the far right, clearly beside the table ---
    cax = fig.add_axes((0.945, 0.40, 0.008, 0.30))
    cb = fig.colorbar(ScalarMappable(norm=NORM, cmap=CMAP), cax=cax)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8.2, colors=MUTED, length=0)
    cb.set_label("quality  q   (0 = low, 1 = high)", fontsize=8.8,
                 color=MUTED, labelpad=9)
    return _save(fig, out_dir, stem)

# ==========================================================================
# v2 gauss — the same rows as a ridgeline
# ==========================================================================
# The left-hand side is identical to v2: labels, repetition bar, value
# table. Only the drawing area changes — instead of a box with whiskers,
# each row carries a curve of width sigma centred on the midpoint.
#
# WHAT THE CURVE IS, AND WHAT IT IS NOT
# -------------------------------------
# It is NOT a probability distribution over the true date. The model says
# so explicitly and this figure must not quietly say otherwise: the
# interval is a "virtual fuzzy year", not a confidence interval, and no
# claim is made about where within it the date lies.
#
# What the curve does show is the dispersion of the contributing potter
# datings, drawn to the scale sigma was measured on. Each potter
# contributes a uniform range; sigma decomposes into the mean internal
# width of those ranges plus the scatter of their midpoints. For a
# findspot with many stamps their sum approaches a bell shape, which is
# why a normal curve is a fair rendering of it — and for a findspot with
# three stamps it is a convenience, not a result.
#
# Areas are equal, not peak heights. A sharply dated findspot therefore
# gets a tall narrow curve and a vague one a low broad curve, so the
# height IS the sharpness rather than a decoration. Scaling every curve
# to the same height would have thrown away exactly the quantity the
# figure exists to show.

GAUSS_SAMPLES = 400        # points per curve
GAUSS_SPAN = 3.2           # curve drawn out to this many sigma

# The tallest curve stays just inside its own row. A ridgeline that
# overlaps looks better on a poster, but here the curves carry a measured
# quantity in their height, and two merged outlines cannot be read apart.
GAUSS_PEAK_ROWS = 0.95
GAUSS_ROW_H = 0.72         # inches per row; taller than v2 to fit the curve

# The rail below each baseline: the whole v2 box-and-whisker, slimmed. It
# restores the two channels the curve alone cannot carry - q_start and
# q_end in the whisker colours, and the grey full-range stubs.
GAUSS_RAIL_DY = 0.30       # rail centre, in row units below the baseline
GAUSS_RAIL_H = 0.15        # box height on the rail



def _spread_profile(r, np):
    """The spread of the contributing potter datings, as a curve.

    Not a Gaussian, and better for it. Each contributing potter covers a
    range [datemin, datemax]; the density at a year t is the share of
    potters whose range contains t. The export publishes the extremes of
    those ranges but not the ranges themselves, so the starts are taken as
    spread evenly over [minDatemin, maxDatemin] and the ends over
    [minDatemax, maxDatemax]. Then

        density(t) ~ P(start <= t) * P(end >= t)

    which is exactly zero at minDatemin and again at maxDatemax - the two
    grey stubs on the rail below. The curve therefore begins and ends
    where the evidence does, instead of trailing off into years no potter
    reaches.

    The shape is a plateau with ramped shoulders rather than a bell: flat
    where every potter's range overlaps, sloping where they enter and
    leave. That is what the dispersion actually looks like; a bell was
    only ever a convenience.
    """
    a0, a1 = float(r["minDatemin"]), float(r["maxDatemin"])
    b0, b1 = float(r["minDatemax"]), float(r["maxDatemax"])
    lo, hi = min(a0, b0), max(a1, b1)
    if hi <= lo:
        hi = lo + 1.0
    xs = np.linspace(lo, hi, GAUSS_SAMPLES)

    def ramp(t, u, v, rising):
        """Share of potters past u on the way to v. A step where u == v."""
        if v <= u:
            return (t >= u).astype(float) if rising else (t <= u).astype(float)
        f = np.clip((t - u) / (v - u), 0.0, 1.0)
        return f if rising else 1.0 - f

    started = ramp(xs, a0, a1, True)      # potters already producing
    running = ramp(xs, b0, b1, False)     # potters not yet finished
    dens = started * running

    # A light smoothing over the corners. The ramps meet at a point when
    # the earliest end and the latest start coincide, and a bare triangle
    # claims a precision the construction does not have. The kernel is
    # narrow enough that the curve still reaches zero at both extremes,
    # which is the property the whole profile exists for.
    k = max(3, GAUSS_SAMPLES // 7) | 1           # odd, ~14 % of the span
    win = np.hanning(k)
    dens = np.convolve(dens, win / win.sum(), mode="same")

    area = float(np.trapezoid(dens, xs)) if hasattr(np, "trapezoid") \
        else float(np.trapz(dens, xs))
    if area > 0:
        dens = dens / area                # equal areas across rows
    return xs, dens


def render_gauss(fig_const: dict, rows: list[dict], era: str,
                 out_dir: Path, model: dict | None = None,
                 stem: str = "plot_v2_gauss") -> list[Path]:
    import numpy as np

    n = len(rows)
    pad = fig_const["padYears"]
    stub = fig_const["extremeStubYears"]

    row_h = GAUSS_ROW_H
    fig = plt.figure(figsize=(17.0, 1.6 + n * row_h), dpi=100,
                     facecolor=PAPER)
    ax = fig.add_axes((0.100, 0.062, 0.400, 0.895))
    ax.set_facecolor(PAPER)

    # The axis has to hold the curve tails, not just the intervals: a
    # clipped tail looks like a truncated distribution, which is a claim
    # the figure is not making.
    # The profile is bounded by the extremes of the contributing potters,
    # so the axis only has to hold those - there are no tails to allow for.
    lo = min(float(r["minDatemin"]) for r in rows) - pad * 0.25
    hi = max(float(r["maxDatemax"]) for r in rows) + pad * 0.25
    ax.set_xlim(lo, hi)
    # Room above the top row for its curve to rise into. Only the top row
    # needs it, so the allowance is its own peak and not the global one.
    ax.set_ylim(n - 0.5, -(0.5 + GAUSS_PEAK_ROWS + 0.50))

    ax.grid(axis="x", color=HAIR, linewidth=0.8, zorder=1)
    ax.set_axisbelow(True)
    if lo <= 0 <= hi:
        ax.axvline(0, color=FAINT, linewidth=1.0, linestyle=(0, (3, 3)),
                   zorder=2)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(HAIR)
    ax.set_yticks([])
    ax.tick_params(axis="x", colors=MUTED, labelsize=9.5, length=0, pad=6)
    ticks = [t for t in ax.get_xticks() if lo <= t <= hi]
    ax.set_xticks(ticks)
    ax.set_xticklabels([year_label(t, era) for t in ticks])

    tf = ax.get_yaxis_transform()
    m_have_rep = any(r.get("qRepetition") is not None for r in rows)
    m_bar_w = REPETITION_BAR_PX / (17.0 * 100 * 0.400)
    m_bar_x = -0.012 - m_bar_w - 0.008
    m_label_x = m_bar_x - 0.010
    if not m_have_rep:
        m_bar_x = m_label_x = -0.012

    # One scale for every curve, so heights stay comparable across rows.
    # The sharpest profile sets the tallest peak.
    profiles = [_spread_profile(r, np) for r in rows]
    peak_scale = GAUSS_PEAK_ROWS / max(float(d.max()) for _x, d in profiles)

    # Back to front: a lower row's curve must not paint over the row above
    # it, which is what gives the ridgeline its depth.
    for i in range(n - 1, -1, -1):
        r = rows[i]
        xs, dens = profiles[i]
        ys = i - dens * peak_scale

        c = colour(r["qInterval"])
        ax.fill_between(xs, ys, i, facecolor=c, alpha=0.88, zorder=10 + i,
                        linewidth=0)
        ax.plot(xs, ys, color=INK, linewidth=0.9, zorder=10 + i)
        ax.plot([xs[0], xs[-1]], [i, i], color=INK, linewidth=0.9,
                zorder=10 + i)

        # ---- the rail: everything the curve cannot say -------------------
        z = 10 + i + 0.5
        ry = i + GAUSS_RAIL_DY
        rh = GAUSS_RAIL_H
        us, ue = r["uncStart"], r["uncEnd"]

        # Full range, grey, with caps. The extremes of the contributing
        # potters - the widest the evidence could possibly be read.
        ax.plot([r["minDatemin"], min(r["minDatemin"] + stub, r["effStart"])],
                [ry, ry], color=FAINT, linewidth=1.0, zorder=z)
        ax.plot([max(r["maxDatemax"] - stub, r["effEnd"]), r["maxDatemax"]],
                [ry, ry], color=FAINT, linewidth=1.0, zorder=z)
        for xv in (r["minDatemin"], r["maxDatemax"]):
            ax.plot([xv, xv], [ry - rh * 0.62, ry + rh * 0.62],
                    color=FAINT, linewidth=1.0, zorder=z)

        # Whiskers, coloured by q_start and q_end. These are the two
        # channels the curve has no room for: the curve is one width, the
        # edges have two qualities.
        for xa, xb, q in ((r["effStart"], r["effStart"] - us, r["qStart"]),
                          (r["effEnd"], r["effEnd"] + ue, r["qEnd"])):
            if xa == xb:
                continue
            wc = colour(q)
            ax.plot([xa, xb], [ry, ry], color=PAPER, linewidth=4.2, zorder=z)
            ax.plot([xa, xb], [ry, ry], color=wc, linewidth=2.6, zorder=z)
            ax.plot([xb, xb], [ry - rh * 0.75, ry + rh * 0.75], color=wc,
                    linewidth=2.6, zorder=z)

        # The published interval m +- k*sigma, as a slim box.
        ax.add_patch(Rectangle((r["effStart"], ry - rh / 2),
                               r["effEnd"] - r["effStart"], rh,
                               facecolor=c, edgecolor=INK, linewidth=0.9,
                               zorder=z + 0.1))

        # Two hairlines tying the box to the curve above it, so the reader
        # sees which part of the curve the published interval covers.
        for xv in (r["effStart"], r["effEnd"]):
            ax.plot([xv, xv], [i, ry - rh / 2], color=INK, linewidth=0.7,
                    alpha=0.45, zorder=z)

        # Row units, not inches: the taller gauss rows would otherwise pull
        # the two label lines apart until they stopped reading as one name.
        ax.text(m_label_x, i - 0.26, r["site"], transform=tf, ha="right",
                va="center", fontsize=10.5, color=INK)
        ax.text(m_label_x, i - 0.04, r["findspot"], transform=tf,
                ha="right", va="center", fontsize=8.4, color=MUTED)

        # The repetition bar sits on the rail line, so every small mark in
        # the row shares one baseline instead of floating between the
        # label lines.
        qr = r.get("qRepetition")
        if qr is not None:
            h = REPETITION_BAR_HEIGHT * 0.65
            by = i + GAUSS_RAIL_DY
            ax.add_patch(Rectangle((m_bar_x, by - h / 2), m_bar_w, h,
                                   transform=tf, facecolor=BAND,
                                   edgecolor="none", clip_on=False,
                                   zorder=3))
            ax.add_patch(Rectangle((m_bar_x, by - h / 2), m_bar_w * qr, h,
                                   transform=tf, facecolor=REPETITION_COLOUR,
                                   edgecolor="none", clip_on=False,
                                   zorder=4))
            ax.plot([m_bar_x + m_bar_w / 2] * 2, [by - h / 2, by + h / 2],
                    transform=tf, color=HAIR, linewidth=0.7,
                    clip_on=False, zorder=5)

    # ---- value table, unchanged from v2 ------------------------------
    # Just above the tallest possible curve, not a fixed row above it.
    head_y = -(0.5 + GAUSS_PEAK_ROWS + 0.30)
    if m_have_rep:
        ax.text(m_bar_x + m_bar_w / 2, head_y, "repetition", transform=tf,
                ha="center", va="center", fontsize=8.2, color=FAINT,
                clip_on=False)
    for x, ha, head, _ in TABLE_COLUMNS:
        ax.text(x, head_y, head, transform=tf, ha=ha, va="center",
                fontsize=8.2, color=FAINT, clip_on=False)
    ax.plot([TAB_L, TAB_R], [head_y + 0.23, head_y + 0.23], transform=tf,
            color=HAIR, linewidth=0.9, clip_on=False, zorder=1)
    for i, r in enumerate(rows):
        if i % 2:
            ax.add_patch(Rectangle((TAB_L, i - 0.5), TAB_R - TAB_L, 1,
                                   transform=tf, facecolor=BAND,
                                   edgecolor="none", clip_on=False, zorder=0))
        for x, ha, _, fn in TABLE_COLUMNS:
            ax.text(x, i - 0.15, fn(r, era), transform=tf, ha=ha,
                    va="center", fontsize=9, color=INK, clip_on=False)

    # No title and no caption in the image. What the curve is - and above
    # all what it is NOT - now has to be carried by the caption of
    # whatever publishes the figure. The warning matters more than the
    # title did: a bell curve read as a probability distribution says
    # something the model explicitly refuses to say.

    cax = fig.add_axes((0.945, 0.30, 0.010, 0.40))
    cb = fig.colorbar(ScalarMappable(norm=Normalize(0, 1), cmap=CMAP),
                      cax=cax)
    cb.outline.set_edgecolor(HAIR)
    cb.ax.tick_params(labelsize=8.5, colors=MUTED, length=0)
    cb.set_label("quality  q   (0 = low, 1 = high)", fontsize=8.8,
                 color=MUTED, labelpad=9)
    return _save(fig, out_dir, stem)
