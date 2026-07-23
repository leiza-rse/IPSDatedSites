"""
IPS Dated Sites — zwei Darstellungen desselben Graphen
======================================================

v1  classic  — 1:1 der bestehenden D3-Abbildung: Box, Whisker mit Kappen,
               Extremwert-Stubs, gestrichelte Boxkanten, Farbrampe
               RdYlGn, Gradientenlegende. Bleibt unangetastet, damit
               Webausgabe und Druckfassung konsistent sind.

v2  modern   — DIESELBE Kodierung wie v1, nur sauberer gesetzt.
               Insbesondere behalten die Whisker ihre Farbe: q_start und
               q_end stehen an keiner anderen Stelle im Bild, ein roter
               Whisker an den fruehen arretinischen Fundstellen ist eine
               eigene Aussage. Modernisiert wird die Machart — Typografie,
               Abstaende, ruhigeres Raster, BC/AD-Achse, Wertetabelle —
               nicht das, was kodiert ist.

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
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

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
                   out_dir: Path, model: dict | None = None,
                   stem: str = "plot_v1_classic") -> list[Path]:
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

    tf = ax.get_yaxis_transform()
    for i, r in enumerate(rows):
        cy = i + 0.5
        y0, y1 = cy - band / 2, cy + band / 2
        us, ue = r["uncStart"], r["uncEnd"]

        # Beschriftung links: Fundplatz, darunter Fundstelle
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
# Bewusst KEINE neue Bildsprache. v2 zeigt exakt dieselben Kanaele wie v1:
#
#   Box            eff_start .. eff_end,  Fuellung = q_interval
#   Whisker        Unsicherheit links/rechts, Farbe = q_start / q_end
#   Whisker-Kappe  Ende der Unsicherheit
#   Stub + Kappe   min_datemin / max_datemax, der Vollbereich
#   Boxkante       gestrichelt, wo eine Unsicherheit anliegt
#
# Die Zahlen stehen nicht mehr am Whisker, sondern rechts in der
# Wertetabelle. Am Whisker kollidierten sie mit dem Whisker selbst,
# sobald die Balken lang wurden.

INK = "#12181f"
MUTED = "#5d6a78"
FAINT = "#96a1ad"
HAIR = "#e3e7ea"
PAPER = "#ffffff"
BAND = "#f5f6f7"

# --------------------------------------------------------------------------
# Wertetabelle rechts der Zeitachse
# --------------------------------------------------------------------------
# Deckt vollstaendig ab, was die Webanwendung zeigt:
#   aus dem Hover-Popup          : interval, n stamps, q(interval)
#   aus der Whisker-Beschriftung : Jahreszahl und q auf BEIDEN Seiten
#                                  ("7 (q=0.71)" -> Spalten unc start / q start)
#
# Ergaenzt um sigma. Das stand NICHT in der Webausgabe. Es ist die
# Streuung aus der Varianzzerlegung, die zusammen mit k die Boxbreite
# erzeugt: Breite = 2*k*sigma. Ohne sie sieht man, wie breit die Box ist,
# aber nicht warum. Wer die Spalte nicht will, loescht hier die Zeile
# mit "sigma" — die Positionen der uebrigen bleiben gueltig.
#
# x steht in Achsenanteilen, y in Datenkoordinaten. Dadurch bleiben die
# Zeilen automatisch auf Hoehe ihres Balkens, ohne Nachrechnen.
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

    row_h = 0.40                      # Zoll je Zeile, luftiger als v1
    fig = plt.figure(figsize=(17.0, 1.9 + n * row_h), dpi=100,
                     facecolor=PAPER)
    # Plotflaeche schmal halten: rechts steht die Wertetabelle.
    # Achsenanteil 1.985 entspricht Figure-x 0.100 + 1.985*0.400 = 0.894.
    # Die Farbleiste sitzt erst bei 0.945 und kollidiert damit nicht.
    ax = fig.add_axes((0.100, 0.062, 0.400, 0.880))
    ax.set_facecolor(PAPER)

    lo = min(min(r["minDatemin"], r["effStart"] - r["uncStart"])
             for r in rows) - pad * 0.5
    hi = max(max(r["maxDatemax"], r["effEnd"] + r["uncEnd"])
             for r in rows) + pad * 0.5
    ax.set_xlim(lo, hi)
    ax.set_ylim(n - 0.5, -0.5)

    # Ruhiges Raster: Zebra statt Gitternetz in der Vertikalen,
    # feine Haarlinien in der Horizontalen.
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

    bh = 0.30                          # Boxhoehe in Zeileneinheiten
    tf = ax.get_yaxis_transform()

    for i, r in enumerate(rows):
        y0, y1 = i - bh / 2, i + bh / 2
        us, ue = r["uncStart"], r["uncEnd"]

        # --- Vollbereich: Stubs mit Kappen ---
        ax.plot([r["minDatemin"], min(r["minDatemin"] + stub, r["effStart"])],
                [i, i], color=FAINT, linewidth=1.0, zorder=2)
        ax.plot([max(r["maxDatemax"] - stub, r["effEnd"]), r["maxDatemax"]],
                [i, i], color=FAINT, linewidth=1.0, zorder=2)
        for xv in (r["minDatemin"], r["maxDatemax"]):
            ax.plot([xv, xv], [i - bh * 0.42, i + bh * 0.42],
                    color=FAINT, linewidth=1.0, zorder=2)

        # --- Whisker: FARBIG nach q_start / q_end ---
        # Weisser Halo darunter, damit die Farbe auch ueber dem Zebra und
        # ueber den Rasterlinien klar bleibt.
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
        # Kanten: oben/unten durchgezogen, seitlich gestrichelt wo eine
        # Unsicherheit anliegt — dieselbe Regel wie v1.
        for yv in (y0, y1):
            ax.plot([r["effStart"], r["effEnd"]], [yv, yv], color=INK,
                    linewidth=0.9, zorder=6)
        for xv, u in ((r["effStart"], us), (r["effEnd"], ue)):
            ax.plot([xv, xv], [y0, y1], color=INK, linewidth=0.9,
                    linestyle=(0, (3, 2)) if u > 0 else "-", zorder=6)

        # --- Beschriftung links ---
        ax.text(-0.012, i - 0.19, r["site"], transform=tf, ha="right",
                va="center", fontsize=10.5, color=INK)
        ax.text(-0.012, i + 0.20, r["findspot"], transform=tf, ha="right",
                va="center", fontsize=8.4, color=MUTED)

    # ----------------------------------------------------------------
    # Wertetabelle
    # ----------------------------------------------------------------
    for x, ha, head, _ in TABLE_COLUMNS:
        ax.text(x, -0.95, head, transform=tf, ha=ha, va="center",
                fontsize=8.2, color=FAINT, clip_on=False)
    ax.plot([TAB_L, TAB_R], [-0.72, -0.72], transform=tf, color=HAIR,
            linewidth=0.9, clip_on=False, zorder=1)

    for i, r in enumerate(rows):
        if i % 2:   # Zebra bis unter die Tabelle durchziehen
            ax.add_patch(Rectangle((TAB_L, i - 0.5), TAB_R - TAB_L, 1,
                                   transform=tf, facecolor=BAND,
                                   edgecolor="none", clip_on=False, zorder=0))
        for x, ha, _, fn in TABLE_COLUMNS:
            ax.text(x, i, fn(r, era), transform=tf, ha=ha, va="center",
                    fontsize=8.2, color=MUTED, clip_on=False, zorder=2)

    # --- Farbleiste ganz rechts, klar neben der Tabelle ---
    cax = fig.add_axes((0.945, 0.40, 0.008, 0.30))
    cb = fig.colorbar(ScalarMappable(norm=NORM, cmap=CMAP), cax=cax)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8.2, colors=MUTED, length=0)
    cb.set_label("quality  q   (0 = low, 1 = high)", fontsize=8.8,
                 color=MUTED, labelpad=9)
    return _save(fig, out_dir, stem)