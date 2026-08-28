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

# The figures carry no heading. The words that go with them live here, one
# entry per file, and a figure without an entry is an error rather than an
# untitled picture nobody can place six months later.
CAPTIONS = ROOT / "talk" / "captions.yaml"


def captioned() -> set[str]:
    import yaml
    data = yaml.safe_load(CAPTIONS.read_text(encoding="utf-8")) or {}
    return set((data.get("figures") or {}).keys())


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
    predicate is said once, in the caption.
    """
    dg = L.DiGraph()
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
    dg = L.DiGraph(rankdir="TB")
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
def rdf_figure(sub: Graph, fold_types: bool,
               stem: str, out: Path) -> list[Path]:
    """One RDF subgraph, drawn with py/graph_layout.py.

    Node colouring and the qname/label conventions come from
    make_instance_graphs, so these figures and the ones in img/graphs read
    the same way; only the renderer is different.
    """
    from rdflib import RDF

    dg = L.DiGraph()
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
    known = captioned()
    g = Graph()
    g.parse(graph_path, format="turtle")
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def check(stem: str) -> str:
        if stem not in known:
            raise SystemExit(
                f"  !!  '{stem}' has no entry in talk/captions.yaml. Add one "
                f"before drawing it: a figure whose caption lives only in "
                f"somebody's head is a figure that cannot be reused.")
        return stem

    pompeii = findspot_by_label(g, "Pompeii", "Hoard")
    langenhain = findspot_by_label(g, "Langenhain", "store")

    figures = [
        ("talk-process", CUT_PROCESS, pompeii, True),
        ("talk-pompeii", CUT_FINDSPOT, pompeii, True),
        ("talk-langenhain", CUT_FINDSPOT, langenhain, True),
    ]

    for stem, query, fs, fold in figures:
        sub = Graph()
        for triple in g.query(PFX + query, initBindings={"fs": fs}):
            sub.add(triple)
        if not len(sub):
            raise SystemExit(
                f"  !!  '{stem}' selected no triples. The CONSTRUCT no longer "
                f"matches the graph — fix it rather than shipping an empty "
                f"figure.")
        written += rdf_figure(sub, fold, check(stem), out)
        print(f"  {stem:<22} {len(sub):>3} triples")

    voc = vocabulary_graph()
    written += vocabulary_figure(voc, out, check("talk-vocabularies"))
    print(f"  {'talk-vocabularies':<22} {len(voc):>3} subclass axioms")

    rows = run_criterion(g)
    if not rows:
        raise SystemExit("  !!  the criterion selected no findspots.")
    written += pipeline_figure(len(rows), out, check("talk-pipeline"))
    print(f"  {'talk-pipeline':<22}")
    written += closed_groups_plot(rows, out, check("talk-closed-groups"))
    print(f"  {'talk-closed-groups':<22} {len(rows):>3} findspots "
          f"({rows[0]['from']} to {rows[-1]['to']})")

    pages = publish_page(ROOT / "talk" / "closed-groups.html",
                         ROOT / "docs" / "query")
    written += pages
    print(f"  {'docs/query/':<22} {len(pages):>3} files "
          f"(the same page, for GitHub Pages)")

    return written


def publish_page(src: Path, out_dir: Path) -> list[Path]:
    """Write the GitHub Pages copy of the live query page.

    The same file twice, from one source, with ONE line rewritten: the
    published copy reaches the graph as ../bundle.ttl, because docs/ is the
    site root and docs/bundle.ttl is already there — byte-identical to
    rdf/IPSDatedSites-bundle.ttl and refreshed by the same pipeline run.

    Copying the graph into docs/query/ as well would put a third copy of it
    in the repository, and a copy that only this page reads is a copy that
    will one day be a month behind the other two. One graph, two pages
    pointing at it.

    An earlier version also rewrote a sentence in the footer, and located it
    by a marker in the source file. When the marker went missing — an older
    patch applied over a newer one is all it takes — the generator died with
    ValueError: substring not found, which says nothing about what is wrong
    or where. The footer now says something true of both copies, so there is
    one substitution instead of two and nothing to lose.
    """
    import shutil

    local = "const GRAPH_URL = '../rdf/IPSDatedSites-bundle.ttl';"
    published = "const GRAPH_URL = '../bundle.ttl';"

    html = src.read_text(encoding="utf-8")
    if local not in html:
        if published in html:
            raise SystemExit(
                f"  !!  {src} already points at the published graph. It is "
                f"the LOCAL page and should read {local!r}; docs/query/ is "
                f"written from it, not the other way round.")
        raise SystemExit(
            f"  !!  {src} has no line reading\n"
            f"      {local}\n"
            f"      so the published copy cannot be pointed at the graph "
            f"under docs/. If the line was renamed, rename it here too.")

    html = html.replace(local, published)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    # closed-groups.html, NOT index.html. docs/query/index.html belongs to
    # py/build_sparql.py, which writes the editable query page there; two
    # generators writing one path means whichever runs last wins, silently.
    # The pipeline runs build_sparql on every build and this script only
    # when somebody asks for it, so the loser would always be this page.
    target = out_dir / "closed-groups.html"
    target.write_text(html, encoding="utf-8")
    written.append(target)

    # The stylesheet and the .rq travel with it: the page links to both by
    # a bare filename, so they have to sit beside it in either location.
    for name in ("style.css", "closed-groups-sharply-dated.rq"):
        source = src.parent / name
        if not source.exists():
            raise SystemExit(f"  !!  {source} is missing; the published page "
                             f"links to it by name and would 404.")
        shutil.copyfile(source, out_dir / name)
        written.append(out_dir / name)
    return written


def serve(root: Path, page: str, port: int) -> int:
    """Serve the repository over HTTP and open the live page.

    The page fetches rdf/IPSDatedSites-bundle.ttl, and a browser will not
    fetch anything from a file:// page, so looking at it needs a server.
    Making that one keystroke rather than three is the difference between
    the page being used and the page being forgotten.

    The root is the repository, not talk/, because the graph sits outside
    talk/ and the page reaches it with ../rdf/.
    """
    import functools
    import http.server
    import socket
    import socketserver
    import webbrowser

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(root))

    # A port left open by an earlier run, or by anything else, should not
    # be a dead end: walk up until one is free.
    for attempt in range(port, port + 12):
        try:
            httpd = socketserver.ThreadingTCPServer(("127.0.0.1", attempt),
                                                    handler)
        except OSError as exc:
            if exc.errno not in (48, 98, 10048):     # address in use
                raise
            continue
        break
    else:
        print(f"  !!  no free port between {port} and {port + 11}.")
        return 2

    httpd.allow_reuse_address = True
    url = f"http://127.0.0.1:{attempt}/{page}"
    print(f"\n  Serving {root} at http://127.0.0.1:{attempt}/")
    print(f"  Opening {url}")
    print("  Ctrl-C to stop.\n")
    try:
        webbrowser.open(url)
    except Exception as exc:                          # noqa: BLE001
        print(f"  (could not open a browser: {exc} — open the URL by hand)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        httpd.server_close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Talk figures: real subgraphs and a real result set")
    ap.add_argument("--graph", type=Path,
                    default=ROOT / "rdf" / "IPSDatedSites-bundle.ttl")
    ap.add_argument("--out", type=Path, default=ROOT / "talk" / "img")
    ap.add_argument("--no-serve", action="store_true",
                    help="just write the figures; do not serve or open the "
                         "live page")
    ap.add_argument("--port", type=int, default=8000,
                    help="first port to try for the local server")
    args = ap.parse_args()
    written = build(args.graph, args.out)
    print(f"\n  {len(written)} file(s) written: {args.out.relative_to(ROOT)} "
          f"and docs/query/")

    # Not when the output is being piped or captured: a build server has no
    # browser and nobody there to press Ctrl-C.
    if args.no_serve or not sys.stdout.isatty():
        if not args.no_serve:
            print("  (not a terminal — skipping the live page; "
                  "--no-serve silences this)")
        return 0
    return serve(ROOT, "talk/closed-groups.html", args.port)


if __name__ == "__main__":
    sys.exit(main())
