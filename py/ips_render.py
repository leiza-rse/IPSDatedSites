"""
IPS Dated Sites — zwei Darstellungen desselben Graphen
======================================================

v1  classic  — 1:1 der bestehenden D3-Abbildung: Box, Whisker mit Kappen,
               Extremwert-Stubs, gestrichelte Boxkanten, Farbrampe
               RdYlGn, Gradientenlegende.

v2  modern   — dieselben Daten, andere Sprache: Kapselform statt Box,
               heller Vollbereich im Hintergrund, Mittelpunktmarke,
               Zebra-Zeilen, reduzierte Achsen, Direktbeschriftung,
               BC/AD-Achse, Farbleiste rechts.

Beide beziehen JEDEN Wert aus dem Graphen, auch Randbreiten, Zeilenhoehe
und Sortierregel. Beide schreiben SVG und hochaufloesendes JPG.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

# Byte-stabile SVGs. Ohne das schreibt matplotlib bei jedem Lauf einen
# neuen <dc:date>-Zeitstempel und neu gewuerfelte Element-IDs, sodass
# beide Abbildungen in git IMMER als geaendert erscheinen. Eine Datei,
# die immer geaendert ist, ist eine Datei, deren Diff niemand mehr liest
# — und dann faellt eine echte Aenderung an einer publizierten Abbildung
# nicht mehr auf.
os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
matplotlib.rcParamsDefault["svg.hashsalt"] = "ips-dated-sites"
matplotlib.rcParams["svg.hashsalt"] = "ips-dated-sites"
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.patches import FancyBboxPatch, Rectangle

CMAP = plt.get_cmap("RdYlGn")
NORM = Normalize(0, 1)
GREY = "#999999"
JPG_DPI = 300


def colour(q):
    """Qualitaet -> Farbe. None ist ein eigener Zustand, kein Fehlerfall."""
    return GREY if q is None else CMAP(NORM(q))


def year_label(v: float, era: str) -> str:
    """Jahreszahl der Quelle als Kalenderlabel."""
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
                   out_dir: Path, stem: str = "plot_v1_classic") -> list[Path]:
    n = len(rows)
    pad = fig_const["padYears"]
    stub = fig_const["extremeStubYears"]
    band = 1 - fig_const["bandPadding"]

    px_w = fig_const["svgWidth"]
    px_h = (n * fig_const["rowHeight"] + fig_const["marginTop"]
            + fig_const["marginBottom"] + 80)
    fig = plt.figure(figsize=(px_w / 100, px_h / 100), dpi=100,
                     facecolor="white")

    left = fig_const["marginLeft"] / px_w
    right = 1 - fig_const["marginRight"] / px_w
    bottom = (fig_const["marginBottom"] + 80) / px_h
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

    for i, r in enumerate(rows):
        cy = i + 0.5
        y0, y1 = cy - band / 2, cy + band / 2
        us, ue = r["uncStart"], r["uncEnd"]

        # Beschriftung links: Fundplatz, darunter Fundstelle
        tf = ax.get_yaxis_transform()
        ax.text(-0.012, cy - 0.12, r["site"], transform=tf, ha="right",
                va="center", fontsize=11, color="black")
        ax.text(-0.012, cy + 0.22, r["findspot"], transform=tf, ha="right",
                va="center", fontsize=9, color="#555555")

        # Extremwert-Stubs mit Kappen
        ax.plot([r["minDatemin"], min(r["minDatemin"] + stub, r["effStart"])],
                [cy, cy], color="#555555", alpha=0.5, linewidth=1)
        ax.plot([max(r["maxDatemax"] - stub, r["effEnd"]), r["maxDatemax"]],
                [cy, cy], color="#555555", alpha=0.5, linewidth=1)
        for xv in (r["minDatemin"], r["maxDatemax"]):
            ax.plot([xv, xv], [cy - band * 0.15, cy + band * 0.15],
                    color="#333333", alpha=0.5, linewidth=1)

        # Whisker mit Kappen, eingefaerbt nach q_start / q_end
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
        if us > 0:
            q = f'{r["qStart"]:.2f}' if r["qStart"] is not None else "–"
            ax.annotate(f'{int(us)} (q={q})', (r["effStart"] - us, cy),
                        xytext=(-4, 0), textcoords="offset points",
                        ha="right", va="center", fontsize=9)
        if ue > 0:
            q = f'{r["qEnd"]:.2f}' if r["qEnd"] is not None else "–"
            ax.annotate(f'{int(ue)} (q={q})', (r["effEnd"] + ue, cy),
                        xytext=(4, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=9)

    # Gradientenlegende
    lax = fig.add_axes((left + (right - left - 0.21) / 2, 24 / px_h,
                        0.21, 12 / px_h))
    lax.imshow([[i / 255 for i in range(256)]], aspect="auto", cmap=CMAP,
               extent=(0, 1, 0, 1))
    lax.set_yticks([])
    lax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    lax.tick_params(labelsize=9)
    for s in lax.spines.values():
        s.set_edgecolor("black")
    lax.set_xlabel("Quality (0 = low, 1 = high)", fontsize=11, labelpad=6)

    fig.suptitle("Archaeological sites dated by potters", fontsize=14,
                 x=left, ha="left", y=1 - 6 / px_h)
    return _save(fig, out_dir, stem)


# ==========================================================================
# v2 — modern
# ==========================================================================
INK = "#1b2430"
MUTED = "#6b7785"
HAIR = "#dfe4ea"


def render_modern(fig_const: dict, rows: list[dict], era: str,
                  out_dir: Path, model: dict | None = None,
                  stem: str = "plot_v2_modern") -> list[Path]:
    n = len(rows)
    pad = fig_const["padYears"]

    fig = plt.figure(figsize=(13.5, 1.7 + n * 0.42), dpi=100,
                     facecolor="#fbfbfa")
    ax = fig.add_axes((0.235, 0.075, 0.645, 0.845))
    ax.set_facecolor("#fbfbfa")

    lo = min(r["minDatemin"] for r in rows) - pad * 0.35
    hi = max(r["maxDatemax"] for r in rows) + pad * 0.35
    ax.set_xlim(lo, hi)
    ax.set_ylim(n - 0.4, -0.6)

    # Zebra-Zeilen statt Gitternetz in der Vertikalen
    for i in range(n):
        if i % 2 == 0:
            ax.add_patch(Rectangle((lo, i - 0.5), hi - lo, 1,
                                   facecolor="#f2f3f1", edgecolor="none",
                                   zorder=0))
    ax.grid(axis="x", color=HAIR, linewidth=0.9, zorder=1)
    ax.set_axisbelow(True)
    if lo <= 0 <= hi:
        ax.axvline(0, color=MUTED, linewidth=1, linestyle=(0, (2, 3)),
                   zorder=2)

    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(HAIR)
    ax.set_yticks([])
    ax.tick_params(axis="x", colors=MUTED, labelsize=10, length=0)
    ticks = [t for t in ax.get_xticks() if lo <= t <= hi]
    ax.set_xticks(ticks)
    ax.set_xticklabels([year_label(t, era) for t in ticks])

    for i, r in enumerate(rows):
        # Vollbereich der Einzeldatierungen, blass im Hintergrund
        ax.plot([r["minDatemin"], r["maxDatemax"]], [i, i], color="#c9cfd6",
                linewidth=1.1, solid_capstyle="round", zorder=2)
        for xv in (r["minDatemin"], r["maxDatemax"]):
            ax.plot([xv], [i], marker="|", color="#c9cfd6", markersize=6,
                    zorder=2)

        # Unsicherheitsband (visual only) als duenne Linie
        us, ue = r["uncStart"], r["uncEnd"]
        if us or ue:
            ax.plot([r["effStart"] - us, r["effEnd"] + ue], [i, i],
                    color=MUTED, alpha=0.35, linewidth=0.9, zorder=3)

        # Das Intervall als Kapsel
        c = colour(r["qInterval"])
        w = max(r["effEnd"] - r["effStart"], 0.5)
        ax.add_patch(FancyBboxPatch(
            (r["effStart"], i - 0.17), w, 0.34,
            boxstyle="round,pad=0,rounding_size=0.17",
            mutation_aspect=(hi - lo) / (n * 2.2),
            facecolor=c, edgecolor="white", linewidth=1.1, zorder=4))

        # Mittelpunkt
        mid = (r["effStart"] + r["effEnd"]) / 2
        ax.plot([mid], [i], marker="o", markersize=3.2, color="white",
                markeredgecolor="none", zorder=5)

        # Beschriftung links
        tf = ax.get_yaxis_transform()
        ax.text(-0.014, i - 0.17, r["site"], transform=tf, ha="right",
                va="center", fontsize=10.5, color=INK, fontweight="medium")
        ax.text(-0.014, i + 0.21, r["findspot"], transform=tf, ha="right",
                va="center", fontsize=8.5, color=MUTED)

        # Direktbeschriftung rechts: Spanne, n, Die-Wiederholung
        rep = "" if not r["nDies"] else \
            f"  ·  {r['nStamps']/r['nDies']:.1f}×/die"
        ax.annotate(
            f'{year_label(r["effStart"], era)} – {year_label(r["effEnd"], era)}'
            f'   n={int(r["nStamps"])}{rep}',
            (max(r["maxDatemax"], r["effEnd"] + ue), i),
            xytext=(8, 0), textcoords="offset points", ha="left",
            va="center", fontsize=8.5, color=MUTED, zorder=6)

    # Farbleiste rechts
    cax = fig.add_axes((0.905, 0.42, 0.011, 0.32))
    cb = fig.colorbar(ScalarMappable(norm=NORM, cmap=CMAP), cax=cax)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8.5, colors=MUTED, length=0)
    cb.set_label("dating sharpness  q", fontsize=9, color=MUTED, labelpad=8)

    # Kopf
    fig.text(0.235, 0.975, "Findspots dated by samian potters' stamps",
             fontsize=15, color=INK, ha="left", va="top")
    sub = ("Capsule = virtual fuzzy year  m ± k·σ   ·   "
           "thin line = full range of contributing stamps   ·   "
           "colour = dating sharpness")
    if model:
        sub += (f"\nk = {model['kMax']:.1f} − "
                f"({model['kMax']:.1f}−{model['kMin']:.1f})"
                f"(1−e^(−n/{model['tau']:.0f}))   ·   w = {model['w']:.1f}")
    fig.text(0.235, 0.947, sub, fontsize=8.6, color=MUTED, ha="left",
             va="top", linespacing=1.5)
    return _save(fig, out_dir, stem)
