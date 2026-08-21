"""
IPS Dated Sites — SPARQL layer
==============================

Retrieves everything the figures need, EXCLUSIVELY by SPARQL against the
graph. Margins, row height, colour ramp and sort rule included — none of
it lives in the renderers.

This is the completeness test of the modelling: if a quantity the figure
needs is missing from the export, the retrieval fails here rather than a
renderer quietly substituting a constant.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from ips_compat import silence_gyear_warnings

silence_gyear_warnings()

# --------------------------------------------------------------------------
# Abfragen
# --------------------------------------------------------------------------
Q_FIGURE = """
PREFIX lado: <http://archaeology.link/ontology#>
SELECT ?padYears ?extremeStubYears ?rowHeight ?svgWidth
       ?marginLeft ?marginRight ?marginTop ?marginBottom
       ?bandPadding ?colourRamp ?rowOrder
WHERE {
  ?fig a lado:Figure ;
       lado:padYears ?padYears ; lado:extremeStubYears ?extremeStubYears ;
       lado:rowHeight ?rowHeight ; lado:svgWidth ?svgWidth ;
       lado:marginLeft ?marginLeft ; lado:marginRight ?marginRight ;
       lado:marginTop ?marginTop ; lado:marginBottom ?marginBottom ;
       lado:bandPadding ?bandPadding ; lado:colourRamp ?colourRamp ;
       lado:rowOrder ?rowOrder .
}
"""

# One row of the figure.
# The path to the interval bounds runs through genuine OWL-Time constructs
# (time-span -> instant -> time position -> numeric position) and is still
# Property-Path trotzdem ein Einzeiler.
Q_ROWS = """
PREFIX lado: <http://archaeology.link/ontology#>
PREFIX crm:  <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?site ?findspot ?effStart ?effEnd
       ?qInterval ?qStart ?qEnd ?qRepetition
       ?uncStart ?uncEnd ?uncInterval
       ?minDatemin ?maxDatemax ?maxDatemin ?minDatemax
       ?nStamps ?nDies
       ?avgDatemin ?avgDatemax ?sigma ?k
WHERE {
  ?row  a lado:PlotRow ; lado:renders ?ts .
  ?fs   crm:P4_has_time-span ?ts ; rdfs:label ?findspot ;
        crm:P89_falls_within ?place .
  ?place rdfs:label ?site .

  ?ts time:hasBeginning/time:inTimePosition/time:numericPosition ?effStart .
  ?ts time:hasEnd/time:inTimePosition/time:numericPosition       ?effEnd .

  ?ts lado:minDatemin ?minDatemin ; lado:maxDatemax ?maxDatemax ;
      lado:maxDatemin ?maxDatemin ; lado:minDatemax ?minDatemax ;
      lado:nStamps ?nStamps ; lado:nDies ?nDies ;
      lado:avgDatemin ?avgDatemin ; lado:avgDatemax ?avgDatemax ;
      lado:sigmaYears ?sigma ; lado:kFactor ?k .

  OPTIONAL { ?ts  lado:qInterval        ?qInterval }
  OPTIONAL { ?ts  lado:qStart           ?qStart }
  OPTIONAL { ?ts  lado:qEnd             ?qEnd }
  OPTIONAL { ?ts  lado:qRepetition      ?qRepetition }
  OPTIONAL { ?row lado:uncStartYears    ?uncStart }
  OPTIONAL { ?row lado:uncEndYears      ?uncEnd }
  OPTIONAL { ?row lado:uncIntervalYears ?uncInterval }
}
ORDER BY ?avgDatemin
"""

Q_ERA = """
PREFIX lado: <http://archaeology.link/ontology#>
SELECT ?era WHERE { ?m a lado:DatingModel ; lado:eraConvention ?era }
"""

Q_MODEL = """
PREFIX lado: <http://archaeology.link/ontology#>
SELECT ?kMin ?kMax ?tau ?w
WHERE { ?m a lado:DatingModel ;
          lado:kMin ?kMin ; lado:kMax ?kMax ;
          lado:tau ?tau ; lado:volumeWeight ?w . }
"""


# --------------------------------------------------------------------------
def num(v, default=None):
    if v is None:
        return default
    return float(v.toPython()) if hasattr(v, "toPython") else float(v)


def load(ttl: Path) -> Graph:
    g = Graph()
    g.parse(ttl, format="turtle")
    return g


def figure_constants(g: Graph) -> dict:
    res = list(g.query(Q_FIGURE))
    if not res:
        raise RuntimeError(
            "Kein lado:Figure-Knoten im Graphen — die Darstellungsschicht "
            "fehlt im Export.")
    f = res[0]
    return {
        "padYears": int(f.padYears),
        "extremeStubYears": int(f.extremeStubYears),
        "rowHeight": int(f.rowHeight), "svgWidth": int(f.svgWidth),
        "marginLeft": int(f.marginLeft), "marginRight": int(f.marginRight),
        "marginTop": int(f.marginTop), "marginBottom": int(f.marginBottom),
        "bandPadding": float(f.bandPadding), "colourRamp": str(f.colourRamp),
        "rowOrder": str(f.rowOrder),
    }


def era(g: Graph) -> str:
    res = list(g.query(Q_ERA))
    return str(res[0].era) if res else "historical"


def model(g: Graph) -> dict:
    res = list(g.query(Q_MODEL))
    if not res:
        return {}
    m = res[0]
    return {"kMin": num(m.kMin), "kMax": num(m.kMax),
            "tau": num(m.tau), "w": num(m.w)}


def rows(g: Graph) -> list[dict]:
    out = []
    for b in g.query(Q_ROWS):
        out.append({
            "site": str(b.site), "findspot": str(b.findspot),
            # numericPosition sits unshifted on the source number line
            # (samian:trs_ips_year) — nichts zurueckzurechnen.
            "effStart": num(b.effStart), "effEnd": num(b.effEnd),
            "qInterval": num(b.qInterval), "qStart": num(b.qStart),
            "qEnd": num(b.qEnd), "qRepetition": num(b.qRepetition),
            "uncStart": num(b.uncStart, 0), "uncEnd": num(b.uncEnd, 0),
            "uncInterval": num(b.uncInterval, 0),
            "minDatemin": num(b.minDatemin), "maxDatemax": num(b.maxDatemax),
            # The inner extremes: where the earliest start ends and the
            # latest end begins. The spread profile in the gauss figure is
            # built from them, so they now travel with the rest.
            "maxDatemin": num(b.maxDatemin), "minDatemax": num(b.minDatemax),
            "nStamps": num(b.nStamps), "nDies": num(b.nDies),
            "avgDatemin": num(b.avgDatemin), "avgDatemax": num(b.avgDatemax),
            "sigma": num(b.sigma), "k": num(b.k),
        })
    return out


# --------------------------------------------------------------------------
FIELD_PAIRS = [
    ("effStart", "eff_start"), ("effEnd", "eff_end"),
    ("qInterval", "q_interval"), ("qStart", "q_start"), ("qEnd", "q_end"),
    ("qRepetition", "q_repetition"),
    ("uncStart", "unc_start_years"), ("uncEnd", "unc_end_years"),
    ("uncInterval", "unc_interval_years"),
    ("minDatemin", "min_datemin"), ("maxDatemax", "max_datemax"),
    ("maxDatemin", "max_datemin"), ("minDatemax", "min_datemax"),
    ("nStamps", "count_stamps"), ("nDies", "n_dies"),
    ("avgDatemin", "avg_datemin"), ("avgDatemax", "avg_datemax"),
    ("sigma", "sigma_eff"), ("k", "k_eff"),
]


def roundtrip(rows_rdf: list[dict], csv: Path, tol: float = 1e-6) -> bool:
    """Compare CSV -> RDF -> SPARQL, field by field."""
    import pandas as pd

    d = pd.read_csv(csv).sort_values("avg_datemin", kind="mergesort")
    r = pd.DataFrame(rows_rdf)
    print(f"  CSV rows: {len(d)} | SPARQL rows: {len(r)}")
    if len(d) != len(r):
        print("  ERROR: row counts differ.")
        return False

    # Matched on (site, findspot), not on row position
    d = d.set_index(pd.Index(d.the_site.astype(str) + "|"
                             + d.the_findspot.astype(str)))
    r = r.set_index(pd.Index(r.site.astype(str) + "|"
                             + r.findspot.astype(str)))
    if set(d.index) ^ set(r.index):
        print("  ERROR: rows without a counterpart.")
        return False
    r = r.loc[d.index]

    worst = 0.0
    for a, b in FIELD_PAIRS:
        dev = (r[a].astype(float) - d[b].astype(float)).abs().max()
        worst = max(worst, dev)
        flag = "OK" if dev < 1e-9 else ("~ " if dev < tol else "XX")
        print(f"  {flag}  {b:<22} max |Delta| = {dev:.2e}")
    ok = worst < tol
    print(f"\n  Largest deviation: {worst:.2e} — "
          + ("Round trip lossless." if ok else "DEVIATION, check the export."))
    return ok
