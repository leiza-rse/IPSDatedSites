"""
IPS Dated Sites — calibration panels
====================================

    python py/make_calibration_panels.py

Two figures of five panels each, one panel per findspot, ordered by
chronological midpoint within its figure. Drawn in the same idiom, but kept
apart because they answer different questions:

  * the five ceramic-independent reference ensembles against which tau was
    calibrated — Dangstetten, Oberaden, Velsen I, Pompeii, Inchtuthil. Each
    carries its terminus as a vertical line, so the reader can see for
    himself whether the modelled interval contains it. That is the whole
    calibration argument, made visible rather than asserted.

  * five further findspots of archaeological interest, spanning the rest of
    the range. No terminus to draw here: these are findspots the model dates,
    not findspots that test it.

Keeping them on separate sheets matters more than it looks. Side by side on
one sheet the five references read as five ordinary examples among ten, and
the calibration argument — every terminus falls inside its interval — stops
being the point of the figure. Apart, the first sheet makes exactly one claim
and can be pointed at.

WHERE THE NUMBERS COME FROM
---------------------------
The termini are NOT restated here. They are read from CALIBRATION_REFERENCES
in py/ips_rdf_export.py, which is what the RDF export publishes as
lado:calibratedAgainst. One list, one place to correct.

The findspot rows come from the same CSV as every other figure, so a panel
cannot disagree with the main plot.

WHAT IS ENCODED, AND WHAT IS ONLY PRESENTATION
----------------------------------------------
Encoding is unchanged from the main figures and must stay that way: box fill
is q_interval, whisker colours are q_start and q_end, the thin line behind is
the full extreme range min_datemin..max_datemax. Only the layout is new.

Each panel carries its own axis. A shared axis across a span from 11 BC to
AD 230 would compress the early ensembles — Dangstetten's interval is nine
years wide — into something narrower than the line drawn for it. The price is
that panels are not directly comparable by eye, so each one states its own
scale in years beneath the axis.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

# Byte-stable SVGs, exactly as ips_render does. Without it every rebuild
# shows the figure as modified and the diff stops being read.
os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
matplotlib.rcParamsDefault["svg.hashsalt"] = "ips-dated-sites"
matplotlib.rcParams["svg.hashsalt"] = "ips-dated-sites"

import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py"))

from ips_rdf_export import CALIBRATION_REFERENCES  # noqa: E402
import ips_render  # noqa: E402

CMAP = plt.get_cmap("RdYlGn")
NORM = Normalize(0, 1)
GREY = "#999999"
JPG_DPI = 300

INK = "#1b2430"
INK_SOFT = "#46525f"
RULE = "#d9d3c6"
SLIP = "#9e3b26"          # samian slip: the terminus marker
PAPER = "#fbfaf7"

# The five further findspots. Four were named by Allard on 2026-08-25;
# Wroxeter is our proposal for the fifth and is marked as such in the
# figure caption until it is confirmed. It was chosen because Allard has
# himself cited the Wroxeter gutter when explaining why later intervals
# widen, and because its midpoint falls within a year of Eschenz — two
# contemporary assemblages of very different size (16 stamps against 31)
# make the effect of n on k legible without any further explanation.
COMPARISON = [
    ("Nijmegen", "Barbarossastraat"),
    ("Wroxeter", "gutter"),
    ("Eschenz", "shop"),
    ("London", "New Fresh Wharf: quay"),
    ("Langenhain", "store"),
]

PROPOSED = {("Wroxeter", "gutter")}


def calibration_title() -> str:
    """Title that states the size of the calibration basis honestly.

    "Five reference ensembles" was true until one of them was set aside; a
    title that keeps saying five while the criterion uses four is the kind of
    small untruth that survives into a caption and then into a citation.
    """
    n = len(CALIBRATION_REFERENCES)
    contested = sum(1 for r in CALIBRATION_REFERENCES if r[4])
    if not contested:
        return (f"The calibration set — {n} ceramic-independent reference "
                "ensembles")
    return (f"The calibration set — {n - contested} references the criterion "
            f"rests on, and {contested} shown but excluded")


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(v):
    if v is None:
        return None
    v = str(v).strip()
    if v == "" or v.lower() in {"null", "nan"}:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def colour(q):
    return GREY if q is None else CMAP(NORM(q))


def select(rows: list[dict]) -> list[dict]:
    """The ten panels, ordered by midpoint, with their role attached."""
    index = {(r["the_site"], r["the_findspot"]): r for r in rows}

    chosen, missing = [], []
    for site, findspot, terminus, why, contested in CALIBRATION_REFERENCES:
        row = index.get((site, findspot))
        if row is None:
            missing.append(f"{site} — {findspot}")
            continue
        chosen.append({**row, "_role": "reference", "_terminus": terminus,
                       "_why": why, "_contested": contested})

    for site, findspot in COMPARISON:
        row = index.get((site, findspot))
        if row is None:
            missing.append(f"{site} — {findspot}")
            continue
        chosen.append({**row, "_role": "comparison", "_terminus": None,
                       "_why": None, "_contested": False})

    if missing:
        # Loudly, not silently: a panel figure that quietly drops a
        # reference ensemble would still look complete.
        raise SystemExit(
            "  !!  not in the data: " + "; ".join(missing) + "\n"
            "      Has a findspot label changed, or is this an older export?")

    chosen.sort(key=lambda r: num(r["midpoint_year"]))
    return chosen


def draw_panel(ax, r: dict, era: str) -> None:
    role = r["_role"]
    eff_start, eff_end = num(r["eff_start"]), num(r["eff_end"])
    unc_a, unc_b = num(r["unc_start_years"]) or 0, num(r["unc_end_years"]) or 0
    lo_ext, hi_ext = num(r["min_datemin"]), num(r["max_datemax"])
    terminus = r["_terminus"]

    # Domain: everything the panel draws, plus a tenth on each side.
    marks = [eff_start - unc_a, eff_end + unc_b, lo_ext, hi_ext]
    if terminus is not None:
        marks.append(float(terminus))
    lo, hi = min(marks), max(marks)
    pad = max((hi - lo) * 0.10, 2.0)
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_ylim(0, 1)

    y = 0.46
    h = 0.30

    # full extreme range, behind everything
    ax.plot([lo_ext, hi_ext], [y, y], color="#555555", lw=0.9, alpha=0.5,
            zorder=1, solid_capstyle="butt")
    for x in (lo_ext, hi_ext):
        ax.plot([x, x], [y - h * 0.42, y + h * 0.42], color="#333333",
                lw=0.9, alpha=0.5, zorder=1)

    # whiskers — colour carries q_start / q_end, as in the main figures
    ax.plot([eff_start - unc_a, eff_start], [y, y],
            color=colour(num(r["q_start"])), lw=2.6, zorder=2,
            solid_capstyle="butt")
    ax.plot([eff_end, eff_end + unc_b], [y, y],
            color=colour(num(r["q_end"])), lw=2.6, zorder=2,
            solid_capstyle="butt")
    ax.plot([eff_start - unc_a] * 2, [y - h * 0.5, y + h * 0.5],
            color=colour(num(r["q_start"])), lw=2.6, zorder=2)
    ax.plot([eff_end + unc_b] * 2, [y - h * 0.5, y + h * 0.5],
            color=colour(num(r["q_end"])), lw=2.6, zorder=2)

    # the box — fill carries q_interval
    ax.add_patch(plt.Rectangle(
        (eff_start, y - h / 2), max(eff_end - eff_start, 1e-6), h,
        facecolor=colour(num(r["q_interval"])), edgecolor="#333333",
        lw=0.8, alpha=0.85, zorder=3))

    # the independent terminus, for the five references
    if terminus is not None:
        inside = eff_start <= terminus <= eff_end
        contested = r.get("_contested", False)
        # A contested terminus is drawn thinner and paler: still shown,
        # because the reader should see the case, but visibly not carrying
        # the same weight as one the calibration criterion rests on.
        ax.axvline(terminus, color=SLIP, lw=1.0 if contested else 1.6,
                   alpha=0.55 if contested else 1.0, zorder=4,
                   ls="-" if inside else (0, (3, 2)))
        # In the clear band between the box and the axis: above the box it
        # collides with the header at the early findspots, below it with the
        # tick labels.
        ax.text(terminus, 0.13, ips_render.year_label(terminus, era),
                ha="center", va="bottom", fontsize=7.4, color=SLIP,
                fontweight="bold", zorder=5)

    # header and footer
    title = f"{r['the_site']} — {r['the_findspot']}"
    if (r["the_site"], r["the_findspot"]) in PROPOSED:
        title += "  *"
    ax.text(0.0, 1.30, title, transform=ax.transAxes, ha="left", va="top",
            fontsize=9.4, fontweight="bold", color=INK)

    facts = (f"n = {r['count_stamps']}    k = {r['k_eff']}    "
             f"σ = {r['sigma_eff']} a    "
             f"{ips_render.year_label(eff_start, era)} – "
             f"{ips_render.year_label(eff_end, era)}"
             f"    ({round(eff_end - eff_start, 1)} a)")
    ax.text(0.0, 1.12, facts, transform=ax.transAxes, ha="left", va="top",
            fontsize=7.6, color=INK_SOFT, family="monospace")

    if role == "reference":
        why = r["_why"]
        if r.get("_contested"):
            why += "  ·  excluded from the calibration"
        ax.text(1.0, 1.30, why, transform=ax.transAxes, ha="right",
                va="top", fontsize=7.4, color=SLIP, style="italic",
                alpha=0.7 if r.get("_contested") else 1.0)

    # Calendar labels on the axis too. Bare numbers next to a header that
    # reads "12 BC – 3 BC" invite the reader to mistake -12 for a year.
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda v, _pos: ips_render.year_label(v, era)))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=7, steps=[1, 2, 5, 10]))
    ax.tick_params(axis="x", labelsize=7.4, colors=INK_SOFT, length=3)
    ax.set_yticks([])
    for side in ("top", "left", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.set_facecolor(PAPER if role == "reference" else "#ffffff")
    if role == "reference":
        ax.set_facecolor("#f6e8e3")   # slip tint: the calibration set


def render(rows: list[dict], out_dir: Path, era: str, stem: str,
           title: str) -> list[Path]:
    n = len(rows)
    height = 1.42 * n + 1.6
    fig = plt.figure(figsize=(13.0, height), dpi=100, facecolor="white")

    # The title band and the legend band are reserved in INCHES, not in
    # figure fractions. With five panels instead of ten the sheet is little
    # more than half as tall, and a fractional reserve shrinks with it: the
    # title then sits on the first panel's header and the legend on the last
    # panel's tick labels.
    # The legend band grows with the number of entries. A contested
    # reference adds a fourth line, which at the old fixed reserve landed on
    # the last panel's tick labels.
    n_legend = 1 + (2 if any(r["_terminus"] is not None for r in rows) else 0) \
                 + (1 if any(r.get("_contested") for r in rows) else 0)
    TOP_IN = 0.80
    BOTTOM_IN = 0.55 + 0.18 * n_legend
    gs = fig.add_gridspec(n, 1, hspace=1.05, left=0.055, right=0.975,
                          top=1 - TOP_IN / height,
                          bottom=BOTTOM_IN / height)

    for i, r in enumerate(rows):
        draw_panel(fig.add_subplot(gs[i]), r, era)

    fig.suptitle(title, fontsize=12.5, fontweight="bold", color=INK,
                 y=1 - 0.28 / height)

    handles = []
    if any(r["_terminus"] is not None for r in rows):
        handles += [
            Line2D([], [], color=SLIP, lw=1.6,
                   label="independent terminus, inside the modelled interval"),
            Line2D([], [], color=SLIP, lw=1.6, ls=(0, (3, 2)),
                   label="independent terminus, outside it"),
        ]
        if any(r.get("_contested") for r in rows):
            handles += [
                Line2D([], [], color=SLIP, lw=1.0, alpha=0.55,
                       label="contested terminus, shown but excluded from "
                             "the calibration criterion"),
        ]
    handles.append(
        Line2D([], [], color="#555555", lw=0.9, alpha=0.5,
               label="full range of contributing potter dates"))
    fig.legend(handles=handles, loc="lower left",
               bbox_to_anchor=(0.055, 0.30 / height),
               frameon=False, fontsize=7.8, labelcolor=INK_SOFT)

    bar = fig.add_axes([0.70, 0.34 / height, 0.22, 0.075 / height])
    fig.colorbar(ScalarMappable(norm=NORM, cmap=CMAP), cax=bar,
                 orientation="horizontal")
    bar.tick_params(labelsize=7, colors=INK_SOFT, length=2)
    bar.set_title("quality (0 low – 1 high)", fontsize=7.4, color=INK_SOFT,
                  pad=4)

    if any((r["the_site"], r["the_findspot"]) in PROPOSED for r in rows):
        fig.text(0.055, 0.10 / height,
                 "*  proposed for the fifth comparison panel, pending "
                 "confirmation",
                 fontsize=7.2, color=INK_SOFT, style="italic")

    return ips_render._save(fig, out_dir, stem)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Panel figure for the tau calibration")
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "img")
    ap.add_argument("--era", choices=("historical", "astronomical"),
                    default="historical")
    args = ap.parse_args()

    csv_path = args.csv
    if csv_path is None:
        found = sorted((ROOT / "data").glob("*.csv"))
        if len(found) != 1:
            raise SystemExit(
                "  !!  expected exactly one CSV in data/, found "
                f"{len(found)}. Pass --csv.")
        csv_path = found[0]

    rows = select(load_rows(csv_path))
    references = [r for r in rows if r["_role"] == "reference"]
    comparison = [r for r in rows if r["_role"] == "comparison"]

    sheets = [
        (references, "plot_v3_calibration", calibration_title()),
        (comparison, "plot_v3_findspots",
         "Five further findspots, across the range of the corpus"),
    ]

    print(f"  Source            : {csv_path.relative_to(ROOT)}")

    written = []
    for sheet, stem, title in sheets:
        paths = render(sheet, args.out, args.era, stem, title)
        written += paths
        print(f"  {stem:<22}: {len(sheet)} panels, "
              f"{ips_render.year_label(min(num(r['midpoint_year']) for r in sheet), args.era)}"
              f" to "
              f"{ips_render.year_label(max(num(r['midpoint_year']) for r in sheet), args.era)}")

    # The calibration claim, restated as a number so that a silent failure
    # cannot hide behind a figure that still looks plausible.
    binding = [r for r in references if not r.get("_contested")]
    inside = sum(1 for r in binding
                 if num(r["eff_start"]) <= r["_terminus"] <= num(r["eff_end"]))
    print(f"  Terminus inside   : {inside} of {len(binding)}"
          f"  ({len(references) - len(binding)} contested, not counted)")
    if inside < len(binding):
        print("  !!  A reference terminus falls outside its modelled "
              "interval. tau was calibrated as the smallest value at which "
              "none does — this needs looking at before publication.")

    print()
    for path in written:
        print(f"  {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
