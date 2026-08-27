"""
IPS Dated Sites — figures for a talk on the semantic model
==========================================================

    python py/make_talk_figures.py

Six figures into talk/img/, each as SVG and as JPG at 300 dpi. Nothing here
is drawn by hand: four of the six are cut out of the published graph with a
CONSTRUCT, one is built from the class table in py/ips_rdf_export.py, and
the sixth is a plot of what a SPARQL query actually returns. A figure can
therefore not quietly disagree with the data it describes.

WHY NEITHER MERMAID NOR GRAPHVIZ
-------------------------------
Mermaid renders in a browser and its layout is whatever the browser makes
of it — fine for a README, awkward for a slide. GraphViz draws these better
than py/graph_layout.py does, but it is a system package that is not on the
Windows machine where this work happens, and a figure that cannot be
regenerated where it is used is not really generated from code.

So the drawing is done by py/graph_layout.py: a layered layout and
matplotlib, both of which the pipeline already has. Nothing here needs a
browser, a binary or a network, and every file in talk/img/ comes out of
`python py/make_talk_figures.py` on any machine that can run the pipeline
at all.

THE SIX
-------
    process        the computation itself: sigma, k, the run and the plan
    vocabularies   the twelve local classes and where each is anchored
    pompeii        Pompeii — Hoard, one findspot as triples
    langenhain     Langenhain — store, the same shape, a different story
    pipeline       bundle -> rdflib -> SPARQL -> DataFrame -> plot
    closed-groups  the plot that pipeline produces, from the real result

BYTE STABILITY
--------------
GraphViz writes no timestamp, and the matplotlib figure is pinned the same
way as the ones in img/: SOURCE_DATE_EPOCH and a fixed svg.hashsalt before
pyplot is imported. Running this twice over an unchanged graph produces
identical files, so a figure that appears in `git status` has really
changed.

DEPENDENCIES
------------
rdflib and matplotlib, both already pinned in requirements.txt. That is
the whole list.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Byte-stable SVG from matplotlib. Must precede the pyplot import.
os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")

from rdflib import Graph, Literal, RDFS, URIRef  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ips_rdf_export as X  # noqa: E402
import graph_layout as L  # noqa: E402
import make_instance_graphs as G  # noqa: E402
from ips_compat import silence_gyear_warnings  # noqa: E402

silence_gyear_warnings()

ROOT = Path(__file__).resolve().parent.parent
JPG_DPI = 300

PFX = G.PREFIXES


# --------------------------------------------------------------------------
# Cuts out of the published graph
# --------------------------------------------------------------------------
CUT_PROCESS = """
CONSTRUCT {
  ?ts a lado:FindspotDating ;
      lado:nStamps ?n ; lado:sigmaYears ?sigma ; lado:kFactor ?k ;
      lado:midpointYear ?mid ;
      time:hasBeginning ?begin ; time:hasEnd ?end ;
      prov:wasGeneratedBy ?act .
  ?begin a time:Instant ; time:inXSDgYear ?gyB .
  ?end a time:Instant ; time:inXSDgYear ?gyE .
  ?act a lado:DatingActivity ; prov:used ?m ; prov:wasAssociatedWith ?ag .
  ?m a lado:DatingModel ; lado:kMin ?kmin ; lado:kMax ?kmax ;
     lado:tau ?tau ; lado:referenceLength ?t0 ;
     lado:fuzzinessDivisor ?div .
  ?ag a prov:SoftwareAgent ; rdfs:label ?agLabel .
} WHERE {
  ?fs crm:P4_has_time-span ?ts .
  ?ts lado:nStamps ?n ; lado:sigmaYears ?sigma ; lado:kFactor ?k ;
      lado:midpointYear ?mid ;
      time:hasBeginning ?begin ; time:hasEnd ?end ;
      prov:wasGeneratedBy ?act .
  ?begin time:inXSDgYear ?gyB .
  ?end time:inXSDgYear ?gyE .
  ?act prov:used ?m ; prov:wasAssociatedWith ?ag .
  ?ag rdfs:label ?agLabel .
  ?m lado:kMin ?kmin ; lado:kMax ?kmax ; lado:tau ?tau ;
     lado:referenceLength ?t0 ; lado:fuzzinessDivisor ?div .
}
"""

CUT_FINDSPOT = """
CONSTRUCT {
  ?fs a lado:Findspot ; rdfs:label ?fsLabel ;
      crm:P89_falls_within ?place ; crm:P4_has_time-span ?ts .
  ?place a lado:DiscoverySite ; rdfs:label ?placeLabel .
  ?ts a lado:FindspotDating ;
      lado:nStamps ?n ; lado:nDies ?dies ; lado:dieRepetition ?rep ;
      lado:sigmaYears ?sigma ; lado:kFactor ?k ;
      lado:qInterval ?qi ; lado:qStart ?qs ; lado:qEnd ?qe ;
      lado:qRepetition ?qr ;
      time:hasBeginning ?begin ; time:hasEnd ?end .
  ?begin a time:Instant ; time:inTimePosition ?bpos ; time:inXSDgYear ?gyB .
  ?end a time:Instant ; time:inTimePosition ?epos ; time:inXSDgYear ?gyE .
  ?bpos a time:TimePosition ; time:numericPosition ?bnp ; time:hasTRS ?trs .
  ?epos a time:TimePosition ; time:numericPosition ?enp ; time:hasTRS ?trs .
  ?trs a time:TRS ; rdfs:label ?trsLabel .
  ?row a lado:PlotRow ; lado:renders ?ts ;
       lado:uncStartYears ?uncS ; lado:uncEndYears ?uncE .
} WHERE {
  ?fs rdfs:label ?fsLabel ; crm:P89_falls_within ?place ;
      crm:P4_has_time-span ?ts .
  ?place rdfs:label ?placeLabel .
  ?ts lado:nStamps ?n ; lado:nDies ?dies ; lado:dieRepetition ?rep ;
      lado:sigmaYears ?sigma ; lado:kFactor ?k ;
      lado:qInterval ?qi ; lado:qStart ?qs ; lado:qEnd ?qe ;
      lado:qRepetition ?qr ;
      time:hasBeginning ?begin ; time:hasEnd ?end .
  ?begin time:inTimePosition ?bpos ; time:inXSDgYear ?gyB .
  ?end time:inTimePosition ?epos ; time:inXSDgYear ?gyE .
  ?bpos time:numericPosition ?bnp ; time:hasTRS ?trs .
  ?epos time:numericPosition ?enp .
  ?trs rdfs:label ?trsLabel .
  ?row lado:renders ?ts ; lado:uncStartYears ?uncS ;
       lado:uncEndYears ?uncE .
}
"""

# The criterion. Also shipped as talk/closed-groups-sharply-dated.rq; read
# from there rather than restated, so the slide and the file cannot drift.
CRITERION = ROOT / "talk" / "closed-groups-sharply-dated.rq"


def findspot_by_label(g: Graph, site: str, findspot: str) -> URIRef:
    """Resolve a findspot by its labels rather than by its URI hash.

    The hash depends on the URI mode the export ran in, so pinning the
    literal URI would break the figures the first time somebody passes
    --findspot-uri slug. The labels are stable.
    """
    rows = list(g.query(PFX + """
        SELECT ?fs WHERE {
          ?fs a lado:Findspot ; rdfs:label ?fsLabel ;
              crm:P89_falls_within ?p .
          ?p rdfs:label ?siteLabel .
          FILTER(STR(?siteLabel) = ?site && STR(?fsLabel) = ?findspot)
        }
    """, initBindings={"site": Literal(site), "findspot": Literal(findspot)}))
    if not rows:
        raise SystemExit(
            f"  !!  no findspot '{site} — {findspot}' in the graph. The talk "
            f"figures name it explicitly; if the corpus no longer has it, "
            f"choose another rather than shipping an empty figure.")
    return URIRef(str(rows[0][0]))


# --------------------------------------------------------------------------
def vocabulary_figure(g: Graph, out: Path,
                      stem: str = "talk-vocabularies") -> list[Path]:
    """The class hierarchy, without repeating the predicate.

    Every edge here is rdfs:subClassOf, so labelling each one eighteen
    times adds no information and costs the figure half its width. The
    predicate is said once, in the title.
    """
    dg = L.DiGraph(title="Twelve local classes, and where each is anchored. "
                         "Every edge is rdfs:subClassOf.")
    for s_, _p, o in sorted(g, key=lambda t: (str(t[0]), str(t[2]))):
        for term in (s_, o):
            q = G.qname(term)
            dg.add_node(q, [q], shape="ellipse",
                        fill=G.FILL.get(q.split(":", 1)[0], "#f5f5f5"),
                        line=G.LINE.get(q.split(":", 1)[0], "#8a857a"))
        dg.add_edge(G.qname(s_), G.qname(o))
    return L.render(dg, out / f"{stem}.svg", out / f"{stem}.jpg", dpi=JPG_DPI)


def vocabulary_graph() -> Graph:
    """The class hierarchy, built from the code rather than restated.

    X.CLASSES is what the export actually asserts, so a class added there
    appears in the figure on the next run and cannot be forgotten.
    """
    g = Graph()
    for cls, parents, _label, _comment in X.CLASSES:
        for parent in parents:
            g.add((cls, RDFS.subClassOf, parent))
    return g


# --------------------------------------------------------------------------
def pipeline_figure(n_rows: int, out: Path,
                    stem: str = "talk-pipeline") -> list[Path]:
    """The one figure that is not a graph: how a plot gets made.

    Same palette as the others, but boxes rather than ellipses, because
    nothing here is a resource.
    """
    dg = L.DiGraph(title="From the published graph to a plot, "
                         "without leaving the notebook", rankdir="TB")
    steps = [
        ("bundle", ["rdf/IPSDatedSites-bundle.ttl",
                    "data + vocabulary +",
                    "materialised CRM crosswalk"], "#faf3e3", "#a8872e"),
        ("rdflib", ["rdflib",
                    "in Jupyter, or in the browser",
                    "through Pyodide / quarto-live"], "#e3f2ec", "#3f8a70"),
        ("query", ["SPARQL",
                   "qRepetition \u2265 0.30",
                   "qInterval \u2265 0.60",
                   "nStamps \u2265 10"], "#e8eef7", "#4a6b96"),
        ("frame", ["pandas DataFrame",
                   f"{n_rows} findspots",
                   "site \u00b7 interval \u00b7 sigma \u00b7 k"],
         "#e8eef7", "#4a6b96"),
        ("plot", ["box plot",
                  "one row per findspot,",
                  "ordered by date"], "#f6ece4", "#9e3b26"),
    ]
    for k, lines, fill, line in steps:
        dg.add_node(k, lines, shape="box", fill=fill, line=line)
    dg.add_node("note", ["The criterion asks for BOTH quality axes",
                         "without multiplying them into one score.",
                         "In a query the threshold is visible,",
                         "per axis, and can be argued with."],
                shape="box", fill="#ffffff", line="#b8bec6")

    dg.add_edge("bundle", "rdflib", "parse")
    dg.add_edge("rdflib", "query", "one criterion")
    dg.add_edge("query", "frame", "SELECT")
    dg.add_edge("frame", "plot", "matplotlib")
    dg.add_edge("query", "note", dashed=True)
    return L.render(dg, out / f"{stem}.svg", out / f"{stem}.jpg", dpi=JPG_DPI)


# --------------------------------------------------------------------------
def rdf_figure(sub: Graph, title: str, fold_types: bool,
               stem: str, out: Path) -> list[Path]:
    """One RDF subgraph, drawn with py/graph_layout.py.

    Node colouring and the qname/label conventions come from
    make_instance_graphs, so these figures and the ones in img/graphs read
    the same way; only the renderer is different.
    """
    from rdflib import RDF

    dg = L.DiGraph(title=title)
    types: dict = {}
    if fold_types:
        for s_, o in sub.subject_objects(RDF.type):
            types.setdefault(s_, []).append(G.qname(o))

    def key(term) -> str:
        return ("L|" if isinstance(term, Literal) else "U|") + str(term)

    def add(term) -> None:
        if isinstance(term, Literal):
            lines = [f'"{G.truncate(str(term))}"']
            if term.datatype is not None:
                lines.append(f"^^{G.qname(term.datatype)}")
            elif term.language:
                lines.append(f"@{term.language}")
            dg.add_node(key(term), lines, shape="box",
                        fill=G.FILL["_lit"], line=G.LINE["_lit"])
        else:
            grp = G.group(term, types)
            lines = [G.qname(term)] + sorted(types.get(term, []))
            dg.add_node(key(term), lines, shape="ellipse",
                        fill=G.FILL.get(grp, "#f5f5f5"),
                        line=G.LINE.get(grp, "#8a857a"))

    for s_, p_, o_ in sorted(sub, key=lambda t: (str(t[0]), str(t[1]),
                                                 str(t[2]))):
        if fold_types and p_ == RDF.type:
            add(s_)
            continue
        add(s_)
        add(o_)
        dg.add_edge(key(s_), key(o_), G.qname(p_))

    return L.render(dg, out / f"{stem}.svg", out / f"{stem}.jpg", dpi=JPG_DPI)


# --------------------------------------------------------------------------
def closed_groups_plot(rows: list[dict], out: Path,
                       stem: str = "talk-closed-groups") -> list[Path]:
    """The plot the pipeline figure describes, from the real result set.

    Same encoding as the corpus figures: the box is the dated interval,
    filled by qInterval on the RdYlGn ramp; the bar in the left margin is
    qRepetition. Only the selection is different.
    """
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["svg.hashsalt"] = "ips-dated-sites"
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    cmap = plt.get_cmap("RdYlGn")
    norm = Normalize(0, 1)
    PAPER = "#fbfaf7"
    INK = "#1b2430"
    BAR = "#4a6b96"

    n = len(rows)
    # Geometry, left to right: the labels get everything up to LABEL_EDGE,
    # then the repetition bar, then the time axis. The bar carries the tick
    # labels rather than the main axis, because a label hung off the main
    # axis is drawn leftwards THROUGH the bar and the two collide.
    LABEL_EDGE, BAR_W, GAP = 0.285, 0.050, 0.020
    AX_LEFT = LABEL_EDGE + BAR_W + GAP
    BOTTOM, HEIGHT = 0.135, 0.775

    fig = plt.figure(figsize=(11.0, 2.1 + n * 0.46), dpi=100, facecolor=PAPER)
    ax = fig.add_axes((AX_LEFT, BOTTOM, 0.955 - AX_LEFT, HEIGHT))
    ax.set_facecolor(PAPER)

    lo = min(r["from"] for r in rows) - 18
    hi = max(r["to"] for r in rows) + 18
    ax.set_xlim(lo, hi)
    ax.set_ylim(-0.7, n - 0.3)
    ax.invert_yaxis()

    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#9aa4ae")
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#c9d0d7", linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)

    for i, r in enumerate(rows):
        width = r["to"] - r["from"]
        ax.barh(i, width, left=r["from"], height=0.52,
                color=cmap(norm(r["qInterval"])), edgecolor=INK,
                linewidth=0.7, zorder=3)
        ax.plot([r["midpoint"]], [i], marker="|", markersize=11,
                color=INK, zorder=4)
        ax.text(r["to"] + 3, i, f"{r['from']}\u2013{r['to']}",
                va="center", ha="left", fontsize=7.5, color="#46525f",
                zorder=4)

    ax.set_yticks(range(n))
    ax.set_yticklabels([])

    # qRepetition as a bar in the left margin, on its own axis so that the
    # two scales cannot be read as one.
    bar = fig.add_axes((LABEL_EDGE, BOTTOM, BAR_W, HEIGHT))
    bar.set_facecolor(PAPER)
    bar.set_xlim(0, 1)
    bar.set_ylim(-0.7, n - 0.3)
    bar.invert_yaxis()
    for spine in bar.spines.values():
        spine.set_visible(False)
    bar.set_xticks([])
    bar.tick_params(axis="y", length=0)
    for i, r in enumerate(rows):
        bar.barh(i, r["qRepetition"], height=0.34, color=BAR, alpha=0.85)
        bar.text(min(r["qRepetition"] + 0.06, 0.99), i,
                 f"{r['qRepetition']:.2f}", va="center", ha="left",
                 fontsize=6.5, color=BAR)
    bar.set_yticks(range(n))
    bar.set_yticklabels([f"{r['site']}\n{r['findspot']}" for r in rows],
                        fontsize=8.5, color=INK)
    fig.text(LABEL_EDGE + BAR_W / 2, BOTTOM - 0.030,
             "q$_{repetition}$", ha="center", va="top",
             fontsize=7.5, color=BAR)

    ax.set_xlabel("year AD", fontsize=8.5, color="#46525f")
    fig.text(LABEL_EDGE, 0.965,
             "Closed groups that are also sharply dated",
             fontsize=13.5, color=INK, fontweight="semibold", ha="left")
    fig.text(LABEL_EDGE, 0.932,
             "qRepetition \u2265 0.30  \u00b7  qInterval \u2265 0.60  \u00b7  "
             f"nStamps \u2265 10   \u2014   {n} findspots, one SPARQL query",
             fontsize=8.5, color="#46525f", ha="left")

    sm = ScalarMappable(norm=norm, cmap=cmap)
    cax = fig.add_axes((0.735, 0.038, 0.22, 0.016))
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.outline.set_edgecolor("#9aa4ae")
    cb.outline.set_linewidth(0.6)
    cb.set_ticks([0, 0.5, 1])
    cax.tick_params(labelsize=7, colors="#46525f", length=2)
    cax.set_title("q$_{interval}$ \u2014 box fill", fontsize=7.5,
                  color="#46525f", pad=4)

    svg = out / f"{stem}.svg"
    jpg = out / f"{stem}.jpg"
    fig.savefig(svg, format="svg", facecolor=PAPER)
    fig.savefig(jpg, format="jpg", dpi=JPG_DPI, facecolor=PAPER)
    plt.close(fig)
    return [svg, jpg]


# --------------------------------------------------------------------------
def run_criterion(g: Graph) -> list[dict]:
    rows = []
    for r in g.query(CRITERION.read_text(encoding="utf-8")):
        rows.append({
            "site": str(r.site),
            "findspot": str(r.findspot),
            "from": int(str(r["from"])),
            "to": int(str(r["to"])),
            "midpoint": float(r.midpoint),
            "sigma": float(r.sigma),
            "k": float(r.k),
            "qInterval": float(r.qInterval),
            "qRepetition": float(r.qRepetition),
        })
    rows.sort(key=lambda r: (r["from"], r["site"], r["findspot"]))
    return rows


def build(graph_path: Path, out: Path) -> list[Path]:
    g = Graph()
    g.parse(graph_path, format="turtle")
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    pompeii = findspot_by_label(g, "Pompeii", "Hoard")
    langenhain = findspot_by_label(g, "Langenhain", "store")

    figures = [
        ("talk-process", "The computation itself, as triples",
         CUT_PROCESS, pompeii, True),
        ("talk-pompeii", "Pompeii \u2014 Hoard: one box, one subgraph",
         CUT_FINDSPOT, pompeii, True),
        ("talk-langenhain",
         "Langenhain \u2014 store: the same shape, a different story",
         CUT_FINDSPOT, langenhain, True),
    ]

    for stem, title, query, fs, fold in figures:
        sub = Graph()
        for triple in g.query(PFX + query, initBindings={"fs": fs}):
            sub.add(triple)
        if not len(sub):
            raise SystemExit(
                f"  !!  '{stem}' selected no triples. The CONSTRUCT no longer "
                f"matches the graph — fix it rather than shipping an empty "
                f"figure.")
        written += rdf_figure(sub, title, fold, stem, out)
        print(f"  {stem:<22} {len(sub):>3} triples")

    voc = vocabulary_graph()
    written += vocabulary_figure(voc, out)
    print(f"  {'talk-vocabularies':<22} {len(voc):>3} subclass axioms")

    rows = run_criterion(g)
    if not rows:
        raise SystemExit("  !!  the criterion selected no findspots.")
    written += pipeline_figure(len(rows), out)
    print(f"  {'talk-pipeline':<22}")
    written += closed_groups_plot(rows, out)
    print(f"  {'talk-closed-groups':<22} {len(rows):>3} findspots "
          f"({rows[0]['from']} to {rows[-1]['to']})")

    return written


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Talk figures: real subgraphs and a real result set")
    ap.add_argument("--graph", type=Path,
                    default=ROOT / "rdf" / "IPSDatedSites-bundle.ttl")
    ap.add_argument("--out", type=Path, default=ROOT / "talk" / "img")
    args = ap.parse_args()
    written = build(args.graph, args.out)
    print(f"\n  {len(written)} file(s) written to "
          f"{args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
