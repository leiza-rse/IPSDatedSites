"""
IPS Dated Sites — instance graphs as SVG
========================================

Writes img/graphs/*.svg: small, real subgraphs of the published graph,
laid out by GraphViz. For talks and for the documentation, where a picture
of the actual triples says more than a class diagram.

WHY NOT rdf-grapher
-------------------
https://www.ldf.fi/service/rdf-grapher does the same thing and is fine for
looking at a file quickly. It is a poor basis for a figure that has to
last: it is a remote service that may not be there in five years, the
styling cannot be controlled, and a whole findspot is about ninety triples,
which renders as a hairball.

So the cut is made here, with SPARQL, and the rendering is local: each
figure shows exactly the triples a CONSTRUCT selected, and the file lands
in the repository next to everything else that is generated.

WHAT IS DRAWN
-------------
Ellipses are resources, boxes are literals, edge labels are predicates —
the conventions rdf-grapher uses, so the pictures read the same way. Types
are folded into the node label rather than drawn as separate rdf:type
edges, because a node with four materialised types otherwise buries the
structure under its own classification. The materialisation figure is the
exception: there the types ARE the subject.

CUTS
----
    findspot        one findspot, place to dating to plot row
    time-chain      the same dating, only the OWL-Time descent
    provenance      the dating, its activity, plan, agent and dataset
    types           one findspot node with every type it carries

Requires GraphViz (`dot`) on PATH. Without it the step is skipped with a
note rather than failing: the SVGs are committed, so a checkout without
GraphViz still has the pictures.

    python py/make_instance_graphs.py
    python py/main.py                    (as step 9)
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ips_rdf_export as X  # noqa: E402
from ips_compat import silence_gyear_warnings  # noqa: E402

silence_gyear_warnings()

ROOT = Path(__file__).resolve().parent.parent

PREFIXES = """
PREFIX samian:  <http://data.archaeology.link/data/samian/>
PREFIX lado:    <http://archaeology.link/ontology#>
PREFIX crm:     <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX crmdig:  <http://www.ics.forth.gr/isl/CRMdig/>
PREFIX time:    <http://www.w3.org/2006/time#>
PREFIX prov:    <http://www.w3.org/ns/prov#>
PREFIX dcat:    <http://www.w3.org/ns/dcat#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
"""

# Palette shared with the Mermaid diagrams, so the two sets of figures do
# not look like they came from different projects.
FILL = {
    "lado": "#e8eef7", "samian": "#faf3e3", "crm": "#efe7f5",
    "crmdig": "#efe7f5", "time": "#e3f2ec", "prov": "#f3f1ec",
    "dcat": "#f3f1ec", "_lit": "#ffffff",
}
LINE = {
    "lado": "#4a6b96", "samian": "#a8872e", "crm": "#7a5a96",
    "crmdig": "#7a5a96", "time": "#3f8a70", "prov": "#8a857a",
    "dcat": "#8a857a", "_lit": "#b8bec6",
}

# --------------------------------------------------------------------------
# The cuts. Each is a CONSTRUCT, so the figure can only ever show triples
# that are really in the graph.
# --------------------------------------------------------------------------
CUTS = {
    "findspot": {
        "title": "One findspot, as modelled",
        "types": True,
        "query": """
CONSTRUCT {
  ?fs a lado:Findspot ; rdfs:label ?fsLabel ;
      crm:P89_falls_within ?place ; crm:P4_has_time-span ?ts .
  ?place a lado:DiscoverySite ; rdfs:label ?placeLabel .
  ?ts a lado:FindspotDating ;
      lado:nStamps ?n ; lado:sigmaYears ?sigma ; lado:kFactor ?k ;
      lado:qInterval ?qi ;
      time:hasBeginning ?begin ; time:hasEnd ?end .
  ?begin a time:Instant ; time:inXSDgYear ?gyB .
  ?end a time:Instant ; time:inXSDgYear ?gyE .
  ?row a lado:PlotRow ; lado:renders ?ts ; lado:uncStartYears ?uncS .
} WHERE {
  ?fs rdfs:label ?fsLabel ; crm:P89_falls_within ?place ;
      crm:P4_has_time-span ?ts .
  ?place rdfs:label ?placeLabel .
  ?ts lado:nStamps ?n ; lado:sigmaYears ?sigma ; lado:kFactor ?k ;
      lado:qInterval ?qi ;
      time:hasBeginning ?begin ; time:hasEnd ?end .
  ?begin time:inXSDgYear ?gyB .
  ?end time:inXSDgYear ?gyE .
  ?row lado:renders ?ts ; lado:uncStartYears ?uncS .
}
""",
    },
    "time-chain": {
        "title": "The OWL-Time descent of one interval boundary",
        "types": True,
        "query": """
CONSTRUCT {
  ?ts time:hasBeginning ?i ; crm:P82a_begin_of_the_begin ?bb .
  ?i a time:Instant ; time:inTimePosition ?p ; time:inXSDgYear ?gy .
  ?p a time:TimePosition ; time:numericPosition ?np ; time:hasTRS ?trs .
  ?trs a time:TRS ; rdfs:label ?trsLabel ; skos:closeMatch ?greg .
} WHERE {
  ?fs crm:P4_has_time-span ?ts .
  ?ts time:hasBeginning ?i ; crm:P82a_begin_of_the_begin ?bb .
  ?i time:inTimePosition ?p ; time:inXSDgYear ?gy .
  ?p time:numericPosition ?np ; time:hasTRS ?trs .
  ?trs rdfs:label ?trsLabel .
  OPTIONAL { ?trs skos:closeMatch ?greg }
}
""",
    },
    "provenance": {
        "title": "Where one dating comes from",
        "types": True,
        "query": """
CONSTRUCT {
  ?ts a lado:FindspotDating ;
      prov:wasGeneratedBy ?act ; prov:wasDerivedFrom ?ds .
  ?act a lado:DatingActivity ;
       prov:used ?m ; crm:P33_used_specific_technique ?m ;
       prov:wasAssociatedWith ?ag ; crm:P14_carried_out_by ?ag ;
       prov:used ?ds .
  ?m a lado:DatingModel ; lado:kMin ?kmin ; lado:kMax ?kmax ;
     lado:tau ?tau ; lado:referenceLength ?t0 ; lado:eraConvention ?era .
  ?ag a prov:SoftwareAgent ; rdfs:label ?agLabel .
  ?ds a dcat:Dataset ; dcterms:title ?dsTitle .
} WHERE {
  ?fs crm:P4_has_time-span ?ts .
  ?ts prov:wasGeneratedBy ?act ; prov:wasDerivedFrom ?ds .
  ?act crm:P33_used_specific_technique ?m ; crm:P14_carried_out_by ?ag .
  ?ag rdfs:label ?agLabel .
  ?ds dcterms:title ?dsTitle .
  ?m lado:kMin ?kmin ; lado:kMax ?kmax ; lado:tau ?tau ;
     lado:referenceLength ?t0 ; lado:eraConvention ?era .
}
""",
    },
    "types": {
        "title": "Every type one findspot carries",
        # Here the types ARE the subject of the figure, so they stay as
        # edges instead of being folded into the node label.
        "types": False,
        "query": """
CONSTRUCT {
  ?fs a ?cls ; rdfs:label ?label .
} WHERE {
  ?fs rdfs:label ?label ; a ?cls .
}
""",
    },
}


# --------------------------------------------------------------------------
# X.PREFIXES has no rdf/rdfs, so without these two the label edge would be
# drawn as a full w3.org URI and swamp its own arrow.
EXTRA_NS = {
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


def qname(term) -> str:
    s = str(term)
    for pfx, ns in list(X.PREFIXES.items()) + list(EXTRA_NS.items()):
        if s.startswith(str(ns)):
            return f"{pfx}:{s[len(str(ns)):]}"
    return s


def group(term, types: dict | None = None) -> str:
    """Which palette entry a node gets.

    Colour by what the node IS, not by where its URI lives. Every instance
    in this graph sits under samian:, so colouring by namespace would paint
    the whole picture one shade and tell the reader nothing. The first type
    in vocabulary order decides instead, which puts OWL-Time instants in the
    time colour and the local classes in theirs.
    """
    if types:
        for t in sorted(types.get(term, []), key=lambda q: q.split(":", 1)[0]):
            pfx = t.split(":", 1)[0]
            if pfx in FILL and pfx != "samian":
                return pfx
    q = qname(term)
    return q.split(":", 1)[0] if ":" in q and not q.startswith("http") else "_lit"


def pick_findspot(g: Graph) -> URIRef:
    """The one findspot every figure is drawn from.

    Chosen as the findspot whose dating begins earliest, then by URI to
    break ties. Two reasons, both practical: the earliest dating is BC, so
    the time-chain figure actually shows the calendar-versus-arithmetic
    fork instead of two identical numbers; and the choice is deterministic,
    which matters because the SVGs are committed — picking "whatever
    SPARQL returned first" would change the files from run to run and set
    the drift check off over nothing.
    """
    rows = list(g.query(PREFIXES + """
        SELECT ?fs ?np WHERE {
          ?fs a lado:Findspot ; crm:P4_has_time-span ?ts .
          ?ts time:hasBeginning/time:inTimePosition/time:numericPosition ?np .
        }
    """))
    if not rows:
        raise SystemExit("  !!  no findspot with a dated beginning in the graph.")
    best = sorted(rows, key=lambda r: (float(r[1]), str(r[0])))[0]
    return URIRef(str(best[0]))


def truncate(s: str, n: int = 46) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def to_dot(g: Graph, title: str, fold_types: bool) -> str:
    """GraphViz source. Resources are ellipses, literals are boxes."""
    from rdflib import RDF

    types: dict[URIRef, list[str]] = {}
    if fold_types:
        for s, o in g.subject_objects(RDF.type):
            types.setdefault(s, []).append(qname(o))

    lines = [
        "digraph G {",
        '  graph [rankdir=LR, fontname="Helvetica", fontsize=10, '
        f'label="{html.escape(title)}", labelloc=t, labeljust=l, '
        "nodesep=0.35, ranksep=0.75, bgcolor=white];",
        '  node [fontname="Helvetica", fontsize=9, style=filled];',
        '  edge [fontname="Helvetica", fontsize=8, color="#5d6a78", '
        'fontcolor="#39434d"];',
    ]

    ids: dict[str, str] = {}

    def nid(term) -> str:
        key = str(term) + ("|L" if isinstance(term, Literal) else "")
        if key not in ids:
            ids[key] = f"n{len(ids)}"
        return ids[key]

    seen: set[str] = set()

    def emit(term) -> None:
        n = nid(term)
        if n in seen:
            return
        seen.add(n)
        if isinstance(term, Literal):
            label = f'"{truncate(str(term))}"'
            if term.datatype is not None:
                label += f"\\n^^{qname(term.datatype)}"
            elif term.language:
                label += f"\\n@{term.language}"
            lines.append(
                f'  {n} [shape=box, label="{html.escape(label)}", '
                f'fillcolor="{FILL["_lit"]}", color="{LINE["_lit"]}"];')
        else:
            grp = group(term, types)
            label = qname(term)
            for t in sorted(types.get(term, [])):
                label += f"\\n{t}"
            lines.append(
                f'  {n} [shape=ellipse, label="{html.escape(label)}", '
                f'fillcolor="{FILL.get(grp, "#f5f5f5")}", '
                f'color="{LINE.get(grp, "#8a857a")}"];')

    for s, p, o in sorted(g, key=lambda t: (str(t[0]), str(t[1]), str(t[2]))):
        if fold_types and p == RDF.type:
            emit(s)
            continue
        emit(s)
        emit(o)
        lines.append(f'  {nid(s)} -> {nid(o)} '
                     f'[label="{html.escape(qname(p))}"];')

    lines.append("}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
def build(graph_path: Path, out: Path) -> list[Path]:
    if shutil.which("dot") is None:
        print("  GraphViz (dot) not found — skipped. The committed SVGs "
              "are still in place.")
        return []

    g = Graph()
    g.parse(graph_path, format="turtle")
    out.mkdir(parents=True, exist_ok=True)
    written = []

    fs = pick_findspot(g)
    print(f"  Drawn from        : {qname(fs)}")

    for name, cut in CUTS.items():
        sub = Graph()
        # initBindings pins ?fs, so each CONSTRUCT cuts one findspot out of
        # the graph rather than matching all of them at once.
        for triple in g.query(PREFIXES + cut["query"], initBindings={"fs": fs}):
            sub.add(triple)
        if not len(sub):
            raise SystemExit(
                f"  !!  cut '{name}' selected no triples. The CONSTRUCT no "
                f"longer matches the graph — fix it rather than shipping an "
                f"empty figure.")

        dot = to_dot(sub, cut["title"], cut["types"])
        dot_path = out / f"{name}.dot"
        dot_path.write_text(dot, encoding="utf-8")
        svg_path = out / f"{name}.svg"
        res = subprocess.run(["dot", "-Tsvg", "-o", str(svg_path),
                              str(dot_path)], capture_output=True, text=True)
        if res.returncode != 0:
            raise SystemExit(f"  !!  dot failed on {name}: {res.stderr}")
        written.append(svg_path)
        print(f"  {svg_path.relative_to(ROOT)}  ({len(sub)} triples)")

    return written


def run(graph_path: Path, out: Path) -> int:
    """Entry point for py/main.py."""
    try:
        build(graph_path, out)
    except SystemExit as exc:
        print(f"  {exc}")
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Real instance subgraphs as SVG, via CONSTRUCT + GraphViz")
    ap.add_argument("--graph", type=Path,
                    default=ROOT / "rdf" / "IPSDatedSites-bundle.ttl")
    ap.add_argument("--out", type=Path, default=ROOT / "img" / "graphs")
    args = ap.parse_args()
    return run(args.graph, args.out)


if __name__ == "__main__":
    sys.exit(main())
