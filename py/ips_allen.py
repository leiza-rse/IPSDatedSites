"""
IPS Dated Sites — Allen's interval algebra over the datings
===========================================================

Every pair of dated findspots stands in exactly one of Allen's thirteen
relations. This module computes them and writes them into the graph, so
that a consumer can ask "what was in use before the Keltengraben" without
fetching two numbers and comparing them by hand.

TWO READINGS, AND WHY THE DISTINCTION IS THE POINT
--------------------------------------------------
The interval bounds are not sharp. eff_start and eff_end are a "virtual
fuzzy year" m +/- k*sigma; the same assemblage read more generously spans
everything from the earliest possible start of its earliest potter to the
latest possible end of its latest one. So each dating has two readings:

    INNER — [eff_start, eff_end]
            the modelled interval. What the box in the figure draws.

    OUTER — [min(eff_start, min_datemin), max(eff_end, max_datemax)]
            the evidence envelope: everything the contributing potters
            could account for. What the stubs in the figure draw.

The outer bound is written as a union so that INNER is inside OUTER by
construction rather than by luck. In the corpus of 2026-08-27 the union
changes nothing — the box already sat inside the extremes in all 41 rows —
but a future revision of the model must not be able to break the nesting
silently, and build() reports how many rows needed widening.

A relation is then asserted at two strengths:

    lado:possiblyBefore   the relation holds on the INNER reading.
                          Every pair gets exactly one of these, so the
                          matrix is complete and COUNT is meaningful.

    time:intervalBefore   the SAME relation also holds on the OUTER
                          reading. It does not depend on how generously
                          the interval is read.

Note the definition: stability, not "holds on the wider interval". The
difference matters. Widening two intervals preserves 'before' but not
'during' — A can sit inside B on the boxes and stick out of it on the
envelopes. Defining the strong relation as "the same relation under both
readings" is what makes

    time:intervalX rdfs:subPropertyOf lado:possiblyX

true for all thirteen relations rather than for three of them.

WHY OWL-TIME GETS THE STRONG ONE
--------------------------------
OWL-Time's interval relations are sharp: time:intervalBefore asserts that
one interval ends before the other begins, with no hedge available. Putting
the unstable half of the matrix there would mean the graph asserting
'before' about two findspots whose boxes visibly overlap once the whiskers
are drawn — a contradiction a reader spots immediately in the very figure
this graph describes.

So a query written in pure OWL-Time sees the stable relations and nothing
else. It returns FEWER rows than the lado: version, and that is not a
defect: it is precisely what a vocabulary without a notion of uncertainty
can honestly say. The query page shows both side by side.

WHAT IS NOT DONE HERE
---------------------
No fuzzy or probabilistic algebra, no degree of overlap, no transitive
closure. Allen's composition table would let a reasoner derive further
relations from these, but every pair is computed directly, so there is
nothing left to derive and a closure would only add duplicates.
"""

from __future__ import annotations

import itertools
from decimal import Decimal

from rdflib import Graph, RDF, RDFS, Literal

# --------------------------------------------------------------------------
# The thirteen relations
# --------------------------------------------------------------------------
# (name, inverse name, OWL-Time local name, definition in words)
#
# 'equals' is its own inverse. The list is ordered as Allen presents it.
RELATIONS = [
    ("before", "after", "intervalBefore",
     "ends before the other begins, with a gap"),
    ("after", "before", "intervalAfter",
     "begins after the other ends, with a gap"),
    ("meets", "metBy", "intervalMeets",
     "ends exactly where the other begins"),
    ("metBy", "meets", "intervalMetBy",
     "begins exactly where the other ends"),
    ("overlaps", "overlappedBy", "intervalOverlaps",
     "begins first, ends inside the other"),
    ("overlappedBy", "overlaps", "intervalOverlappedBy",
     "begins inside the other and outlasts it"),
    ("starts", "startedBy", "intervalStarts",
     "begins together with the other and ends first"),
    ("startedBy", "starts", "intervalStartedBy",
     "begins together with the other and outlasts it"),
    ("during", "contains", "intervalDuring",
     "falls strictly inside the other"),
    ("contains", "during", "intervalContains",
     "strictly encloses the other"),
    ("finishes", "finishedBy", "intervalFinishes",
     "begins later and ends together with the other"),
    ("finishedBy", "finishes", "intervalFinishedBy",
     "begins earlier and ends together with the other"),
    ("equals", "equals", "intervalEquals",
     "has the same bounds as the other"),
]

INVERSE = {name: inv for name, inv, _t, _d in RELATIONS}
TIME_LOCAL = {name: t for name, _i, t, _d in RELATIONS}
DEFINITION = {name: d for name, _i, _t, d in RELATIONS}
NAMES = [name for name, *_ in RELATIONS]


def lado_local(name: str) -> str:
    """'before' -> 'possiblyBefore'."""
    return "possibly" + name[0].upper() + name[1:]


# --------------------------------------------------------------------------
def relation(a: tuple[Decimal, Decimal],
             b: tuple[Decimal, Decimal]) -> str:
    """
    Allen's relation of interval a to interval b.

    Exactly one of the thirteen holds for any two intervals, which is what
    makes the algebra a partition rather than a collection of predicates.
    Comparison is on Decimal: the bounds come out of the source as decimal
    strings, and a float round-trip would turn 'meets' into 'overlaps' at
    the fifteenth digit.
    """
    a1, a2 = a
    b1, b2 = b
    if a2 < b1:
        return "before"
    if b2 < a1:
        return "after"
    if a2 == b1:
        return "meets"
    if b2 == a1:
        return "metBy"
    if a1 == b1 and a2 == b2:
        return "equals"
    if a1 == b1:
        return "starts" if a2 < b2 else "startedBy"
    if a2 == b2:
        return "finishes" if a1 > b1 else "finishedBy"
    if a1 < b1 and b2 < a2:
        return "contains"
    if b1 < a1 and a2 < b2:
        return "during"
    if a1 < b1 < a2 < b2:
        return "overlaps"
    return "overlappedBy"


def readings(row) -> tuple[tuple[Decimal, Decimal], tuple[Decimal, Decimal]]:
    """(inner, outer) for one row of the source table."""
    def d(v):
        return Decimal(str(v))
    inner = (d(row.eff_start), d(row.eff_end))
    outer = (min(inner[0], d(row.min_datemin)),
             max(inner[1], d(row.max_datemax)))
    return inner, outer


# --------------------------------------------------------------------------
def build(g: Graph, df, uri_of, lado, time_ns,
          emit_inverse: bool = True) -> dict:
    """
    Add the relation triples to g. Returns statistics for the run report.

    `uri_of` maps a DataFrame row to the URI of its time-span. The
    relations hang on the TIME-SPAN, not on the findspot: OWL-Time's
    interval relations relate time:ProperInterval to time:ProperInterval,
    and lado:FindspotDating is declared a ProperInterval. Putting them on
    the findspot would be a category error that no reasoner would catch,
    because the findspot is a place.

    Both directions are written out when emit_inverse is set. OWL-Time does
    declare the inverse pairs, but rdflib under Pyodide performs no
    entailment and neither do most triplestores, so a consumer asking for
    everything related to one findspot would otherwise need a UNION in
    every query. Doubling a few thousand triples is the cheaper of the two.
    """
    rows = []
    widened = 0
    for _, r in df.iterrows():
        inner, outer = readings(r)
        # The union guarantees this; the assertion is here so that a future
        # change to readings() cannot quietly break the subproperty axiom.
        assert outer[0] <= inner[0] and inner[1] <= outer[1]
        # How often the evidence extremes alone would NOT have contained the
        # modelled box. Zero in the 2026-08-27 corpus; a non-zero count means
        # the model has started producing intervals wider than the material
        # they rest on, which is worth seeing in the run report.
        if (Decimal(str(r.min_datemin)) > inner[0]
                or Decimal(str(r.max_datemax)) < inner[1]):
            widened += 1
        rows.append((uri_of(r), inner, outer))

    stats = {
        "pairs": 0, "possible": 0, "stable": 0, "widened": widened,
        "inner": {}, "stable_by_relation": {},
    }

    for (uri_a, in_a, out_a), (uri_b, in_b, out_b) in \
            itertools.combinations(rows, 2):
        stats["pairs"] += 1
        rel_in = relation(in_a, in_b)
        rel_out = relation(out_a, out_b)
        stats["inner"][rel_in] = stats["inner"].get(rel_in, 0) + 1

        pairs = [(uri_a, rel_in, uri_b)]
        if emit_inverse:
            pairs.append((uri_b, INVERSE[rel_in], uri_a))
        for s, rel, o in pairs:
            g.add((s, lado[lado_local(rel)], o))
            stats["possible"] += 1

        if rel_out == rel_in:
            strong = [(uri_a, rel_in, uri_b)]
            if emit_inverse:
                strong.append((uri_b, INVERSE[rel_in], uri_a))
            for s, rel, o in strong:
                g.add((s, time_ns[TIME_LOCAL[rel]], o))
                stats["stable"] += 1
            stats["stable_by_relation"][rel_in] = \
                stats["stable_by_relation"].get(rel_in, 0) + 1

    return stats


def declare(g: Graph, lado, time_ns, owl) -> None:
    """
    The subproperty axioms, emitted alongside the data.

    Stated in the DATA graph and not only in the vocabulary because the
    claim is about these two families of predicates and a consumer loading
    the data without the vocabulary should still be told that every strong
    relation is also a possible one. It is an axiom, not an inference: it
    holds by how build() constructs the two sets.
    """
    for name, inv, time_local, _definition in RELATIONS:
        strong = time_ns[time_local]
        weak = lado[lado_local(name)]
        g.add((strong, RDFS.subPropertyOf, weak))
        g.add((weak, owl.inverseOf, lado[lado_local(inv)]))
