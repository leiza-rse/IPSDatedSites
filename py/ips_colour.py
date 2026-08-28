"""
IPS Dated Sites — colour axes for the map gradient
==================================================

Turns a measured column into a normalised value in [0, 1] and a hex colour,
so that a map client can shade a findspot without recomputing the model.

WHY THE COLOUR IS IN THE GRAPH AT ALL
-------------------------------------
Strictly, a colour is presentation and does not belong in the data. The
precedent for putting it there anyway is tiger (Time Geospatial RDF), which
publishes lado:tiger_cax_norm and lado:tiger_cax_hex on every discovery
site, and the reason is practical: a Leaflet or MapLibre layer reading a
static Turtle file has no colour scale of its own, and forcing every client
to reimplement the normalisation is how two maps of the same data end up
disagreeing.

So the colours travel, but under three conditions that keep them honest:

  1. They sit on the PRESENTATION layer — on lado:PlotRow, never on the
     time-span. Same rule as lado:uncStartYears, which the method
     documentation marks "visual only".
  2. Every axis declares how its colour was made: the ramp stops, the
     interpolation, the normalisation domain and whether that domain is a
     fixed convention or read off this corpus.
  3. The hex is therefore REPRODUCIBLE FROM THE GRAPH. Someone who
     distrusts the colour can recompute it from lado:rampStops and
     lado:normalisedValue without this repository.

NOT THE SAME AS D3
------------------
The box plot colours its boxes with d3.interpolateRdYlGn, which is a
spline through the ColorBrewer anchors. This module interpolates linearly
in RGB between the same anchors. The two agree at the eleven anchor points
and differ by a few units in between. That difference is why the figure's
ramp keeps its own property (lado:colourRamp, the name of the D3 function)
and the axes here carry lado:rampName plus the stops: one is a reference to
a function this export does not reproduce, the other is a complete
specification.

WHY FOUR AXES AND NOT ONE
-------------------------
Choosing the single variable that drives the colour is a decision about
what the map is FOR, and it is not ours to make once for everyone. Dating
sharpness, chronology, sigma and sample size answer different questions and
four axes cost a few hundred triples. The client picks.

The chronological axis deliberately does NOT use a red-green ramp. Red-green
reads as good-bad, and "late" is not "bad" — the epoch drift in this corpus
("je juenger, desto roter") is a property of the evidence, not a defect of
the findspots.
"""

from __future__ import annotations

import math
from decimal import Decimal

# --------------------------------------------------------------------------
# Ramps — anchor stops, interpolated linearly in RGB
# --------------------------------------------------------------------------
# RdYlGn is the ColorBrewer 11-class diverging scheme, the same anchors D3
# splines through. The others are sampled from the matplotlib colormaps of
# the same name at nine evenly spaced positions; sampling rather than
# depending on matplotlib keeps this module free of the plotting stack and
# makes the stops visible in the graph.
RAMPS: dict[str, list[str]] = {
    "RdYlGn": [
        "#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b", "#ffffbf",
        "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837",
    ],
    "viridis": [
        "#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ae80",
        "#5ec962", "#addc30", "#fde725",
    ],
    "cividis": [
        "#00224e", "#123570", "#3b496c", "#575d6d", "#707173", "#8a8678",
        "#a59c74", "#c3b369", "#fee838",
    ],
}
# Reversed variants, so that "low is good" and "high is good" can both be
# expressed without inventing a second colour scheme.
RAMPS["RdYlGn-reversed"] = list(reversed(RAMPS["RdYlGn"]))

INTERPOLATION = "linear-rgb"


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def ramp_colour(ramp: str, t: float) -> str:
    """Position t in [0, 1] on a named ramp -> '#rrggbb'."""
    stops = RAMPS[ramp]
    t = min(1.0, max(0.0, float(t)))
    if t >= 1.0:
        return stops[-1]
    span = 1.0 / (len(stops) - 1)
    i = int(t / span)
    local = (t - i * span) / span
    a, b = _rgb(stops[i]), _rgb(stops[i + 1])
    # round(), not int(): truncation biases every channel downwards and
    # would make the midpoint of two stops visibly darker than either.
    out = tuple(round(a[c] + (b[c] - a[c]) * local) for c in range(3))
    return "#{:02x}{:02x}{:02x}".format(*out)


# --------------------------------------------------------------------------
# Axes
# --------------------------------------------------------------------------
# (axis name, source column, source property local name, ramp, scale,
#  fixed domain or None, why this ramp)
#
# The axis name is capitalised into the property names: qInterval ->
# lado:normQInterval and lado:hexQInterval.
AXES = [
    ("qInterval", "q_interval", "qInterval", "RdYlGn", "linear", (0.0, 1.0),
     "Dating sharpness on its own 0-1 scale, so the domain is a fixed "
     "convention rather than the range this corpus happens to show. Green "
     "is sharp. Matches the legend of the box plot."),
    ("midpointYear", "midpoint_year", "midpointYear", "viridis", "linear",
     None,
     "Chronological position. A sequential ramp on purpose: red-green would "
     "read as a judgement, and late material is not worse material."),
    ("sigmaYears", "sigma_eff", "sigmaYears", "RdYlGn-reversed", "linear",
     None,
     "The dispersion the interval is built from. Reversed, so that small "
     "sigma is green and agrees with the qInterval axis."),
    ("nStamps", "count_stamps", "nStamps", "cividis", "log", None,
     "Sample size. Logarithmic, because the counts run from 2 to 170 and a "
     "linear domain would put four fifths of the findspots in the darkest "
     "eighth of the ramp."),
]


def capitalise(name: str) -> str:
    return name[0].upper() + name[1:]


def norm_property(axis: str) -> str:
    return f"norm{capitalise(axis)}"


def hex_property(axis: str) -> str:
    return f"hex{capitalise(axis)}"


def domain(values: list[float], fixed, scale: str) -> tuple[float, float]:
    """
    The interval the values are stretched onto.

    A fixed domain is a published convention and does not move when the
    corpus grows. An observed domain is read off the data, which means the
    colours of unchanged findspots shift when a findspot is added — that is
    recorded in the graph as lado:domainBasis so nobody has to guess.
    """
    if fixed is not None:
        return fixed
    vals = [v for v in values if v is not None]
    if scale == "log":
        vals = [v for v in vals if v > 0]
    lo, hi = min(vals), max(vals)
    return (lo, hi) if hi > lo else (lo, lo + 1.0)


def normalise(value: float, lo: float, hi: float, scale: str) -> float:
    """Value -> [0, 1]. Values outside the domain are clamped, not dropped."""
    if scale == "log":
        if value <= 0 or lo <= 0:
            return 0.0
        t = (math.log(value) - math.log(lo)) / (math.log(hi) - math.log(lo))
    else:
        t = (value - lo) / (hi - lo)
    return min(1.0, max(0.0, t))


def quantise(t: float) -> Decimal:
    """
    Five decimal places, as tiger publishes its normalised values.

    Fixing the precision here rather than letting the float decide is what
    keeps the Turtle byte-stable between runs and platforms.
    """
    return Decimal(f"{t:.5f}")
