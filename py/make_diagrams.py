"""
IPS Dated Sites — Mermaid diagram generator
===========================================

Writes docs/diagrams/*.mmd. Every diagram is derived from the code or from
the generated graph, never hand-drawn, so a change to the model shows up
in the pictures on the next run.

    1  architecture   the pipeline, from database to figures
    2  hierarchy      the LADO classes and their CIDOC CRM superclasses
    3  relations      the class skeleton, grouped by the three layers
    4  instance       one real findspot, read from the generated graph
    5  materialisation what the bundle adds so CRM queries resolve
    6  vocabularies   which external vocabulary carries what
    7  time-chain     one interval boundary, down to the number
    8  provenance     where a dating comes from
    9  links          what makes this Linked Data rather than only RDF
   10  parity         two emitters held to one model

Sources:

    ips_rdf_export   CLASSES, RELATIONS, LAYERS, PREFIXES
    make_bundle      the subclass closure used for materialisation
    the graph        for the instance diagram, queried by SPARQL

Each diagram is written twice from ONE string: as a standalone .mmd file
and, by make_docs.py, as an inline ```mermaid block in the .md page.
GitHub renders the inline block natively; the .mmd stays usable on its
own, for instance to render an SVG with the mermaid CLI.

Note on GitHub Pages: Jekyll does not render Mermaid without mermaid.js
added to the layout. On github.com itself the inline blocks render as they
are.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS

import ips_rdf_export as X
from ips_compat import silence_gyear_warnings

silence_gyear_warnings()

ROOT = Path(__file__).resolve().parent.parent

# Mermaid class definitions, applied by node group. Colours stay muted so
# the diagrams read on both light and dark GitHub themes.
STYLES = """
    classDef local fill:#e8eef7,stroke:#4a6b96,stroke-width:1px,color:#12181f
    classDef crm fill:#efe7f5,stroke:#7a5a96,stroke-width:1px,color:#12181f
    classDef time fill:#e3f2ec,stroke:#3f8a70,stroke-width:1px,color:#12181f
    classDef ext fill:#f3f1ec,stroke:#8a857a,stroke-width:1px,color:#12181f
    classDef io fill:#faf3e3,stroke:#a8872e,stroke-width:1px,color:#12181f
""".rstrip()


def qname(term) -> str:
    s = str(term)
    for pfx, ns in X.PREFIXES.items():
        if s.startswith(str(ns)):
            return f"{pfx}:{s[len(str(ns)):]}"
    return s


def node_id(term) -> str:
    """Mermaid-safe identifier."""
    return qname(term).replace(":", "_").replace("-", "_").replace(".", "_")


def style_of(term) -> str:
    q = qname(term)
    if q.startswith("lado:"):
        return "local"
    if q.startswith("crm:"):
        return "crm"
    if q.startswith("time:"):
        return "time"
    return "ext"


# --------------------------------------------------------------------------
# 1 — architecture
# --------------------------------------------------------------------------
def diagram_architecture(**_) -> str:
    """
    The pipeline. Step names and output files come from the code, so
    adding an output step does not leave the picture behind.
    """
    outs = {
        "rdf": ["ips_sites_dating_v1.ttl", "ips_sites_dating_v1.jsonld",
                "lado_dating_extension.ttl", "IPSDatedSites-bundle.ttl"],
        "img": ["plot_v1_classic", "plot_v2_modern", "plot_v2_gauss"],
    }
    rdf_list = "<br/>".join(outs["rdf"])
    img_list = "<br/>".join(outs["img"])
    return f"""flowchart LR
    DB[("PostgreSQL<br/>Samian Research / IPS")]
    SQL["sql/IPSDatedSites.sql<br/>one row per findspot"]
    CSV["data/*.csv"]
    EXP["py/ips_rdf_export.py"]
    RDF["rdf/<br/>{rdf_list}"]
    SPQ["py/ips_sparql.py<br/>reads everything back"]
    REN["py/ips_render.py"]
    IMG["img/<br/>{img_list}"]
    DOC["py/make_docs.py<br/>py/make_diagrams.py"]
    DOCS["docs/"]
    VER["py/verify.py<br/>step 0"]
    WEB["py/make_webjs.py"]
    JS["webjs/<br/>ips_rdf.js<br/>to the ColdFusion server"]
    SPB["py/build_sparql.py<br/>queries.yaml"]
    PAGE["docs/query/<br/>docs/bundle.ttl<br/>qmd/"]
    CHK{{"round trip<br/>17 fields compared"}}
    PAR{{"parity<br/>sorted N-Triples, SHA-256"}}

    DB --> SQL --> CSV --> EXP --> RDF --> SPQ --> REN --> IMG
    CSV --> VER
    EXP --> DOC --> DOCS
    EXP --> WEB --> JS
    RDF --> SPB --> PAGE
    SPQ --> CHK
    CSV -.-> CHK
    WEB --> PAR
    EXP -.-> PAR

    class DB,SQL,CSV io
    class RDF,IMG,DOCS,JS,PAGE ext
    class EXP,SPQ,REN,DOC,WEB,SPB local
    class CHK,PAR,VER time
{STYLES}"""


# --------------------------------------------------------------------------
# 2 — class hierarchy
# --------------------------------------------------------------------------
def diagram_hierarchy(**_) -> str:
    """
    Read straight from CLASSES. Arrows point from subclass to superclass,
    so every path ends in an external vocabulary — which is the claim the
    crosswalk makes.
    """
    lines = ["flowchart BT"]
    seen: set = set()
    for cls, supers, label, _de in X.CLASSES:
        cid = node_id(cls)
        if cid not in seen:
            lines.append(f'    {cid}["{qname(cls)}"]')
            seen.add(cid)
        for sup in supers:
            sid = node_id(sup)
            if sid not in seen:
                lines.append(f'    {sid}["{qname(sup)}"]')
                seen.add(sid)
            lines.append(f"    {cid} -->|subClassOf| {sid}")

    groups: dict[str, list[str]] = {}
    for cls, supers, _l, _d in X.CLASSES:
        for term in (cls, *supers):
            groups.setdefault(style_of(term), []).append(node_id(term))
    for grp, ids in groups.items():
        lines.append(f"    class {','.join(sorted(set(ids)))} {grp}")
    lines.append(STYLES)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 3 — relations, grouped by layer
# --------------------------------------------------------------------------
def diagram_relations(**_) -> str:
    """
    From RELATIONS and LAYERS. Classes without a layer tag — the external
    OWL-Time and PROV nodes — sit outside the subgraphs, which is exactly
    right: they belong to no layer of ours.
    """
    used: set = set()
    for s, _p, o in X.RELATIONS:
        used.add(s)
        used.add(o)

    lines = ["flowchart LR"]
    by_layer: dict[str, list] = {}
    for term in used:
        layer = X.LAYERS.get(term)
        if layer:
            by_layer.setdefault(layer, []).append(term)

    for layer in ["place", "dating", "presentation", "provenance"]:
        terms = by_layer.get(layer)
        if not terms:
            continue
        lines.append(f'    subgraph {layer}["{X.LAYER_LABELS[layer]}"]')
        lines.append("        direction TB")
        for t in sorted(terms, key=qname):
            lines.append(f'        {node_id(t)}["{qname(t)}"]')
        lines.append("    end")

    grouped = {t for terms in by_layer.values() for t in terms}
    for term in sorted(used - grouped, key=qname):
        lines.append(f'    {node_id(term)}["{qname(term)}"]')

    for s, p, o in X.RELATIONS:
        lines.append(f"    {node_id(s)} -->|{qname(p)}| {node_id(o)}")

    for grp in ("local", "crm", "time", "ext"):
        ids = sorted({node_id(t) for t in used if style_of(t) == grp})
        if ids:
            lines.append(f"    class {','.join(ids)} {grp}")
    lines.append(STYLES)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 4 — one real instance
# --------------------------------------------------------------------------
Q_ONE = """
PREFIX lado: <http://archaeology.link/ontology#>
PREFIX crm:  <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?fs ?fsLabel ?place ?placeLabel ?ts ?begin ?pos ?from ?row
       ?sigma ?k ?q ?unc
WHERE {
  ?fs a lado:Findspot ; rdfs:label ?fsLabel ;
      crm:P89_falls_within ?place ;
      crm:P4_has_time-span ?ts .
  ?place rdfs:label ?placeLabel .
  ?ts time:hasBeginning ?begin ; lado:sigmaYears ?sigma ; lado:kFactor ?k .
  ?begin time:inTimePosition ?pos .
  ?pos time:numericPosition ?from .
  OPTIONAL { ?ts  lado:qInterval ?q }
  ?row lado:renders ?ts ; lado:uncStartYears ?unc .
  FILTER(CONTAINS(STR(?placeLabel), "Amiens"))
}
LIMIT 1
"""


def diagram_instance(graph: Graph | None = None, **_) -> str:
    """
    A real findspot with its real URIs and values, pulled from the graph
    the pipeline just wrote. If the model changes, so does this picture.
    """
    if graph is None:
        graph = Graph()
        graph.parse(ROOT / "rdf" / "ips_sites_dating_v1.ttl", format="turtle")
    res = list(graph.query(Q_ONE))
    if not res:
        return ("flowchart LR\n"
                '    none["no matching instance found"]\n' + STYLES)
    r = res[0]

    def short(u):
        return str(u).rsplit("/", 1)[-1]

    return f"""flowchart LR
    PL["samian:{short(r.place)}<br/><i>{r.placeLabel}</i><br/>lado:DiscoverySite"]
    FS["samian:{short(r.fs)}<br/><i>{r.fsLabel}</i><br/>lado:Findspot"]
    TS["samian:{short(r.ts)}<br/>lado:FindspotDating<br/>sigma {float(r.sigma):.1f} · k {float(r.k):.4f} · q {float(r.q):.2f}"]
    BG["samian:{short(r.begin)}<br/>time:Instant"]
    PO["samian:{short(r.pos)}<br/>time:TimePosition<br/>numericPosition {float(r["from"]):.1f}"]
    RW["samian:{short(r.row)}<br/>lado:PlotRow<br/>uncStartYears {int(r.unc)}"]

    FS -->|crm:P89_falls_within| PL
    FS -->|crm:P4_has_time-span| TS
    TS -->|time:hasBeginning| BG
    BG -->|time:inTimePosition| PO
    RW -->|lado:renders| TS

    class PL,FS,TS,RW local
    class BG,PO time
{STYLES}"""


# --------------------------------------------------------------------------
# 5 — materialisation
# --------------------------------------------------------------------------
def diagram_materialisation(**_) -> str:
    """
    Built from the same closure function the bundle uses, so the dashed
    edges are literally the triples it writes.
    """
    import make_bundle

    onto = X.build_ontology()
    closure = make_bundle.superclass_closure(onto)
    start = X.LADO.Findspot
    inferred = sorted(closure.get(start, ()), key=qname)

    lines = ["flowchart LR",
             '    I["samian:fs_1003978_969c47<br/>one findspot"]',
             f'    A["{qname(start)}"]',
             "    I -->|rdf:type, asserted| A"]
    for sup in inferred:
        lines.append(f'    {node_id(sup)}["{qname(sup)}"]')
        lines.append(f"    I -.->|rdf:type, materialised| {node_id(sup)}")
    lines.append("    class I io")
    lines.append("    class A local")
    for grp in ("crm", "time", "local", "ext"):
        ids = sorted({node_id(s) for s in inferred if style_of(s) == grp})
        if ids:
            lines.append(f"    class {','.join(ids)} {grp}")
    lines.append(STYLES)
    return "\n".join(l for l in lines if l)



# --------------------------------------------------------------------------
# 6 — vocabularies
# --------------------------------------------------------------------------
def diagram_vocabularies(**_) -> str:
    """
    Which external vocabulary carries what.

    Built from PREFIXES and from the superclasses actually used in
    CLASSES, so a vocabulary that stops being used disappears from the
    picture instead of lingering as a claim.
    """
    # Which foreign namespaces do our own classes actually hang from?
    used: dict[str, set[str]] = {}
    for cls, supers, *_ in X.CLASSES:
        for sup in supers:
            q = qname(sup)
            if ":" in q and not q.startswith("lado:"):
                used.setdefault(q.split(":", 1)[0], set()).add(qname(cls))

    ROLES = {
        "crm": ("CIDOC CRM", "places, time-spans,<br/>activities, dimensions"),
        "time": ("OWL-Time", "instants, positions,<br/>time reference systems"),
        "crmdig": ("CRMdig", "the computation<br/>that produced a dating"),
        "prov": ("PROV-O", "activity, plan, agent,<br/>derivation"),
        "geo": ("GeoSPARQL", "geometry<br/>(off by default)"),
        "dcat": ("DCAT", "the dataset snapshot"),
        "skos": ("SKOS", "notations and<br/>loose matches"),
        "dcterms": ("Dublin Core", "titles, dates, sources"),
        "pleiades": ("Pleiades", "ancient places<br/>as external identifiers"),
    }

    lines = ["flowchart LR",
             '    LADO["lado:<br/><b>local extension</b><br/>only what the '
             'standards do not cover"]']
    for pfx, (label, role) in ROLES.items():
        if pfx not in X.PREFIXES:
            continue
        n = len(used.get(pfx, ()))
        anchored = f"<br/><i>{n} class(es) anchored</i>" if n else ""
        lines.append(f'    {pfx}["{label}<br/>{role}{anchored}"]')
        edge = "-->" if n else "-.->"
        lines.append(f"    LADO {edge} {pfx}")
    lines.append("")
    lines.append("    class LADO local")
    for grp, pfxs in (("crm", ("crm", "crmdig")), ("time", ("time",))):
        ids = [p for p in pfxs if p in X.PREFIXES]
        if ids:
            lines.append(f"    class {','.join(ids)} {grp}")
    rest = [p for p in ROLES if p in X.PREFIXES
            and p not in ("crm", "crmdig", "time")]
    if rest:
        lines.append(f"    class {','.join(rest)} ext")
    lines.append(STYLES)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 7 — the time chain
# --------------------------------------------------------------------------
def diagram_time_chain(graph: Graph | None = None, **_) -> str:
    """
    One interval boundary, all the way down to the number.

    The fork at the bottom is the point: the calendar label and the
    arithmetic position deliberately disagree about negative years.
    Values are read from the graph when one is supplied.
    """
    num, cal = "-16.6", "-0016"
    if graph is not None:
        q = """
        PREFIX lado: <http://archaeology.link/ontology#>
        PREFIX crm:  <http://www.cidoc-crm.org/cidoc-crm/>
        PREFIX time: <http://www.w3.org/2006/time#>
        SELECT ?num ?cal WHERE {
          ?ts a lado:FindspotDating ; time:hasBeginning ?i .
          ?i time:inXSDgYear ?cal ; time:inTimePosition ?p .
          ?p time:numericPosition ?num .
          FILTER(?num < 0)
        } ORDER BY ?num LIMIT 1
        """
        for row in graph.query(q):
            num, cal = str(row[0]), str(row[1])

    return f"""flowchart TB
    TS["lado:FindspotDating<br/>crm:E52_Time-Span · time:ProperInterval"]
    I["time:Instant<br/>lado:DatingInstant"]
    P["time:TimePosition<br/>lado:DatingTimePosition"]
    TRS["samian:trs_ips_year<br/>time:TRS · lado:YearScale"]
    NUM["time:numericPosition<br/><b>{num}</b><br/><i>signed number line,<br/>never shifted</i>"]
    CAL["time:inXSDgYear<br/><b>{cal}</b><br/><i>calendar label,<br/>shifted by +1 for BC</i>"]
    GREG["ISO-8601 Gregorian"]

    TS -->|time:hasBeginning| I
    I -->|time:inTimePosition| P
    P -->|time:hasTRS| TRS
    P --> NUM
    I --> CAL
    TRS -.->|skos:closeMatch| GREG

    class TS,TRS local
    class I,P time
    class NUM,CAL io
    class GREG ext
""" + STYLES


# --------------------------------------------------------------------------
# 8 — provenance
# --------------------------------------------------------------------------
def diagram_provenance(**_) -> str:
    """
    Where a dating comes from.

    Two vocabularies say the same thing on purpose: PROV for the
    provenance world, CIDOC CRM so that a CRM-only consumer sees the
    method too. The duplication is deliberate and is drawn as such.
    """
    return f"""flowchart LR
    TS["lado:FindspotDating<br/><i>the dating</i>"]
    ACT["lado:DatingActivity<br/>prov:Activity · crmdig:D10_Software_Execution"]
    MOD["lado:DatingModel<br/>prov:Plan · crm:E29_Design_or_Procedure<br/><i>kMin kMax tau referenceLength<br/>volumeWeight eraConvention<br/>excludedDatemax</i>"]
    AG["samian:IPSDatedSitesExporter<br/>prov:SoftwareAgent · crmdig:D14_Software"]
    DS["dcat:Dataset<br/><i>dated snapshot</i>"]

    TS -->|prov:wasGeneratedBy| ACT
    TS -->|prov:wasDerivedFrom| DS
    ACT -->|prov:used| MOD
    ACT -.->|crm:P33_used_specific_technique| MOD
    ACT -->|prov:wasAssociatedWith| AG
    ACT -.->|crm:P14_carried_out_by| AG
    ACT -->|prov:used| DS

    class TS,ACT,MOD,AG local
    class DS ext
{STYLES}"""


# --------------------------------------------------------------------------
# 9 — outward links
# --------------------------------------------------------------------------
def diagram_links(graph: Graph | None = None, **_) -> str:
    """
    What makes this Linked Data rather than only RDF.

    Counts come from the graph, so a claim about how many findspots reach
    Pleiades cannot go stale.
    """
    n_sites = n_pleiades = n_findspots = 0
    if graph is not None:
        def count(q):
            for r in graph.query(q):
                return int(r[0])
            return 0
        base = "PREFIX lado: <http://archaeology.link/ontology#>\n"
        n_sites = count(base + "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE "
                               "{ ?s a lado:DiscoverySite }")
        n_findspots = count(base + "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE "
                                   "{ ?s a lado:Findspot }")
        n_pleiades = count(base + "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE "
                                  "{ ?s lado:pleiadesID ?p }")

    return f"""flowchart LR
    subgraph ours["this repository"]
        direction TB
        FS["lado:Findspot<br/>{n_findspots} findspots<br/><i>URI = sha256(name)[0:6]</i>"]
        DSITE["lado:DiscoverySite<br/>{n_sites} sites"]
        FS -->|crm:P89_falls_within| DSITE
    end

    AL["archaeology.link<br/><i>loc_discoverysite_1.ttl</i><br/>the sites are referenced,<br/>not re-asserted"]
    PL["Pleiades<br/>{n_pleiades} sites carry<br/>an ancient-place URI"]
    N4O["NFDI4Objects<br/>knowledge graph<br/><i>target for the bundle</i>"]

    DSITE ==>|same URI| AL
    DSITE -->|lado:pleiadesID| PL
    ours ==>|IPSDatedSites-bundle.ttl| N4O

    class FS,DSITE local
    class AL,PL,N4O ext
{STYLES}"""


# --------------------------------------------------------------------------
# 10 — two emitters, one model
# --------------------------------------------------------------------------
def diagram_parity(**_) -> str:
    """
    How the browser emitter is kept from drifting.

    The tabular parts are generated; the graph shape is not, and is held
    in step by comparing hashes instead. Drawing the gate makes the
    asymmetry visible rather than leaving it in a docstring.
    """
    return f"""flowchart TB
    SRC["py/ips_rdf_export.py<br/><i>the model</i>"]
    GEN["py/make_webjs.py<br/><i>injects prefixes, measure lists,<br/>figure constants, subclass closure,<br/>the vocabulary prelude</i>"]
    BODY["py/templates/ips_rdf_body.js<br/><i>graph shape, hand-written</i>"]
    JS["webjs/ips_rdf.js"]

    CSV["one CSV"]
    GPY["graph, built in Python"]
    GJS["graph, built in the browser"]
    GATE{{"sorted N-Triples<br/>SHA-256 compared"}}
    OUT["identical, or the build fails"]

    SRC --> GEN --> JS
    BODY --> JS
    CSV --> GPY
    CSV --> GJS
    SRC --> GPY
    JS --> GJS
    GPY --> GATE
    GJS --> GATE
    GATE --> OUT

    class SRC,GEN,BODY local
    class JS,CSV,GPY,GJS ext
    class GATE,OUT time
{STYLES}"""

# --------------------------------------------------------------------------
DIAGRAMS = {
    "architecture": (diagram_architecture,
                     "Pipeline from database to figures"),
    "hierarchy": (diagram_hierarchy,
                  "LADO classes and their CIDOC CRM superclasses"),
    "relations": (diagram_relations,
                  "Class skeleton, grouped by the three layers"),
    "instance": (diagram_instance,
                 "One real findspot as modelled"),
    "materialisation": (diagram_materialisation,
                        "What the bundle adds for reasoner-free CRM queries"),
    "vocabularies": (diagram_vocabularies,
                     "Which external vocabulary carries what"),
    "time-chain": (diagram_time_chain,
                   "One interval boundary, down to the number"),
    "provenance": (diagram_provenance,
                   "Where a dating comes from"),
    "links": (diagram_links,
              "What makes this Linked Data rather than only RDF"),
    "parity": (diagram_parity,
               "Two emitters held to one model"),
}


def build(out: Path, graph: Graph | None = None) -> dict[str, str]:
    """Write the .mmd files and return {name: mermaid source}."""
    out.mkdir(parents=True, exist_ok=True)
    made = {}
    for name, (fn, _desc) in DIAGRAMS.items():
        src = fn(graph=graph)
        (out / f"{name}.mmd").write_text(src + "\n", encoding="utf-8")
        made[name] = src
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate docs/diagrams/*.mmd")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "diagrams")
    args = ap.parse_args()
    for name in build(args.out):
        print("  ", (args.out / f"{name}.mmd").relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
