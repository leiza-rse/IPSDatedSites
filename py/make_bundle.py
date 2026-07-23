"""
IPS Dated Sites — standalone bundle
===================================

Writes rdf/IPSDatedSites-bundle.ttl: one file holding the data, the full
LADO vocabulary and a materialised CIDOC CRM / OWL-Time crosswalk, so that
it can be loaded into a triplestore on its own.

WHY MATERIALISE
---------------
The subclass axioms alone are not enough. Most triplestores perform no
RDFS entailment by default, and the NFDI4Objects knowledge graph should
not be assumed to. Loading only the axioms gives this:

    SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE { ?x a crm:E53_Place }
    -> 0

although every findspot IS a place by the axioms. A consumer querying in
CIDOC CRM — which is the whole point of the crosswalk — would see nothing.

This builder therefore computes the transitive closure over
rdfs:subClassOf and writes the inferred rdf:type triples out explicitly.
After that the same query answers correctly with no reasoner involved.

The axioms are kept as well, so a store that DOES reason derives nothing
new and nothing conflicts; the materialised triples are exactly what the
reasoner would have produced.

DISCOVERY SITES ARE TYPED HERE
------------------------------
The incremental export deliberately makes no rdf:type statement about the
published samian:loc_ds_* nodes — it only references them. That is right
for an export meant to be merged alongside loc_discoverysite_1.ttl.

A standalone bundle is a different case: without the published file
present, crm:P89_falls_within would point at an untyped node and a query
for places would miss 32 of them. This builder therefore asserts
lado:DiscoverySite on those nodes, which materialises through
lado:Location to crm:E53_Place.

Note that this is a RESTATEMENT, not a new claim: the published file
already types them lado:DiscoverySite, so the triple is identical and a
merge stays idempotent. Use --no-type-sites to suppress it if the bundle
is only ever loaded together with the published data.

WHAT IS NOT INFERRED
--------------------
Only rdf:type over rdfs:subClassOf. No domain/range inference, no
property closure, no owl:sameAs propagation. Those would generate large
numbers of triples of little use here and would embed assumptions the
source data do not support.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, OWL, XSD

import ips_rdf_export as X
from ips_compat import silence_gyear_warnings

silence_gyear_warnings()

ROOT = Path(__file__).resolve().parent.parent
VOID = Namespace("http://rdfs.org/ns/void#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")

# Classes whose instances are worth counting in the bundle description.
COUNTED = [
    (X.LADO.DiscoverySite, "sites"),
    (X.LADO.Findspot, "findspots"),
    (X.LADO.FindspotDating, "datings"),
    (X.LADO.PlotRow, "plot rows"),
    (X.LADO.DatingActivity, "activities"),
    (X.CRM.E7_Activity, "CIDOC CRM activities (after materialisation)"),
    (X.CRM.E53_Place, "CIDOC CRM places (after materialisation)"),
    (X.CRM["E52_Time-Span"], "CIDOC CRM time-spans (after materialisation)"),
    (X.TIME.ProperInterval, "OWL-Time intervals (after materialisation)"),
]


# --------------------------------------------------------------------------
def superclass_closure(g: Graph) -> dict[URIRef, set[URIRef]]:
    """
    Transitive closure over rdfs:subClassOf.

    Walks the axioms present in the graph rather than a hard-coded table,
    so adding a superclass in ips_rdf_export.py propagates here without a
    second edit.
    """
    direct: dict[URIRef, set[URIRef]] = {}
    for sub, sup in g.subject_objects(RDFS.subClassOf):
        direct.setdefault(sub, set()).add(sup)

    closure: dict[URIRef, set[URIRef]] = {}

    def walk(cls, seen: set) -> set:
        if cls in closure:
            return closure[cls]
        out: set = set()
        for sup in direct.get(cls, ()):
            if sup in seen:          # guard against a cyclic hierarchy
                continue
            out.add(sup)
            out |= walk(sup, seen | {cls})
        closure[cls] = out
        return out

    for cls in list(direct):
        walk(cls, set())
    return closure


def type_discovery_sites(g: Graph) -> int:
    """
    Assert lado:DiscoverySite on referenced published site nodes.

    Identical to the triple already in loc_discoverysite_1.ttl, so merging
    the two files produces no duplicate and no conflict.
    """
    added = 0
    prefix = str(X.SAMIAN) + "loc_ds_"
    for s in {s for s in g.subjects() if str(s).startswith(prefix)}:
        if (s, RDF.type, None) not in g:
            g.add((s, RDF.type, X.LADO.DiscoverySite))
            added += 1
    return added


def materialise(g: Graph) -> int:
    """Write out the rdf:type triples an RDFS reasoner would infer."""
    closure = superclass_closure(g)
    added = 0
    for subj, cls in list(g.subject_objects(RDF.type)):
        for sup in closure.get(cls, ()):
            if (subj, RDF.type, sup) not in g:
                g.add((subj, RDF.type, sup))
                added += 1
    return added


# --------------------------------------------------------------------------
def type_bundle_node(g: Graph, bundle_uri: URIRef) -> None:
    """
    Nur die Typen des Bundle-Knotens.

    Getrennt von describe() und VOR der Materialisierung aufgerufen: sonst
    bekaeme ausgerechnet der Knoten, der das Bundle beschreibt, seine
    CRM-Oberklassen nicht mehr und waere die einzige Instanz im Graphen,
    die aus CIDOC-CRM-Sicht nicht existiert.
    """
    g.add((bundle_uri, RDF.type, VOID.Dataset))
    g.add((bundle_uri, RDF.type, DCAT.Dataset))
    g.add((bundle_uri, RDF.type, X.CRMDIG.D1_Digital_Object))


def describe(g: Graph, bundle_uri: URIRef, inferred: int) -> None:
    """A self-description, so an ingesting catalogue knows what it has."""
    now = datetime.now(timezone.utc)
    # Wie der Export-Datensatz: ueber D1 erreicht auch die
    # Selbstbeschreibung crm:E73_Information_Object.
    g.add((bundle_uri, RDF.type, X.CRMDIG.D1_Digital_Object))
    g.add((bundle_uri, DCTERMS.title, Literal(
        "IPS dated sites — data, vocabulary and materialised CRM crosswalk",
        lang="en")))
    g.add((bundle_uri, DCTERMS.description, Literal(
        "Self-contained bundle: the findspot datings, the full LADO "
        "vocabulary, and rdf:type triples materialised over "
        "rdfs:subClassOf so that CIDOC CRM and OWL-Time queries resolve "
        "without a reasoner. Loadable into a triplestore on its own.",
        lang="en")))
    g.add((bundle_uri, DCTERMS.issued,
           Literal(now.strftime("%Y-%m-%d"), datatype=XSD.date)))
    g.add((bundle_uri, DCTERMS.license, URIRef(
        "https://spdx.org/licenses/MIT.html")))
    g.add((bundle_uri, DCTERMS.source, Literal(
        "Samian Research / IPS. Rights in the source data are held by the "
        "database publishers and are independent of the MIT licence "
        "covering the software that produced this file.", lang="en")))
    g.add((bundle_uri, OWL.versionInfo, Literal(now.strftime("%Y-%m-%d"))))
    g.add((bundle_uri, RDFS.comment, Literal(
        f"{inferred} rdf:type triples in this file are inferred rather "
        f"than asserted: they are the transitive closure over "
        f"rdfs:subClassOf, written out explicitly. The axioms they follow "
        f"from are included, so a reasoning store derives nothing new.",
        lang="en")))
    for cls, label in COUNTED:
        n = len(set(g.subjects(RDF.type, cls)))
        stat = URIRef(f"{bundle_uri}/stat_{label.split()[0].lower()}")
        g.add((bundle_uri, VOID.classPartition, stat))
        g.add((stat, VOID["class"], cls))
        g.add((stat, VOID.entities, Literal(n, datatype=XSD.integer)))


# --------------------------------------------------------------------------
def build(data: Graph, onto: Graph, out: Path,
          do_materialise: bool = True,
          do_type_sites: bool = True) -> tuple[Path, dict]:
    g = Graph()
    for pfx, ns in X.PREFIXES.items():
        g.bind(pfx, ns)
    g.bind("void", VOID)
    g.bind("dcat", DCAT)

    for t in onto:
        g.add(t)
    n_onto = len(g)
    for t in data:
        g.add(t)
    n_data = len(g) - n_onto

    bundle_uri = X.SAMIAN["bundle_IPSDatedSites"]
    typed = type_discovery_sites(g) if do_type_sites else 0
    type_bundle_node(g, bundle_uri)          # vor der Materialisierung
    inferred = materialise(g) if do_materialise else 0
    describe(g, bundle_uri, inferred)        # Zaehlungen danach

    out.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=out, format="turtle", encoding="utf-8")

    stats = {"ontology": n_onto, "data": n_data, "sites_typed": typed,
             "inferred": inferred, "total": len(g)}
    return out, stats


# Klassen, die zum Vokabular gehoeren und keine Instanzen der
# Anwendungsdomaene sind. Eine owl:Class ist kein Ding in der Welt.
VOCABULARY_TYPES = {OWL.Class, OWL.DatatypeProperty, OWL.ObjectProperty,
                    OWL.Ontology}


def unanchored_instances(g: Graph) -> list[tuple]:
    """
    Instanzen von Anwendungsklassen ohne CIDOC-CRM-Typ.

    Die Zusage lautet: JEDE Instanz einer Anwendungsklasse traegt einen
    CRM-Typ, direkt oder ueber eine CRM-Erweiterung, die selbst in CRM
    verankert ist. Fuer Properties gilt das nicht — wo eine OWL-Time- oder
    PROV-Property besser passt, wird sie benutzt.

    Die Zusage geht leicht verloren: eine neue Klasse ohne CRM-Oberklasse
    faellt niemandem auf, weil alles andere weiterlaeuft. Deshalb wird sie
    gemessen und nicht angenommen.
    """
    crm = str(X.CRM)
    out = []
    for s in {s for s in g.subjects(RDF.type, None)}:
        types = set(g.objects(s, RDF.type))
        if types & VOCABULARY_TYPES:
            continue
        if not any(str(t).startswith(crm) for t in types):
            out.append((s, tuple(sorted(str(t) for t in types))))
    return out


def verify(path: Path) -> dict[str, int]:
    """
    Re-parse the written file and query it in CIDOC CRM and OWL-Time terms
    only. No reasoner. This is the test the bundle exists to pass.
    """
    g = Graph()
    g.parse(path, format="turtle")
    checks = {
        "crm:E53_Place": """PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE { ?x a crm:E53_Place }""",
        "crm:E52_Time-Span": """PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            SELECT (COUNT(DISTINCT ?x) AS ?n)
            WHERE { ?x a crm:E52_Time-Span }""",
        "crm:E36_Visual_Item": """PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            SELECT (COUNT(DISTINCT ?x) AS ?n)
            WHERE { ?x a crm:E36_Visual_Item }""",
        "time:ProperInterval": """PREFIX time: <http://www.w3.org/2006/time#>
            SELECT (COUNT(DISTINCT ?x) AS ?n)
            WHERE { ?x a time:ProperInterval }""",
        "crm:E7_Activity": """PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            SELECT (COUNT(DISTINCT ?x) AS ?n)
            WHERE { ?x a crm:E7_Activity }""",
        "crm:E29_Design_or_Procedure":
            """PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            SELECT (COUNT(DISTINCT ?x) AS ?n)
            WHERE { ?x a crm:E29_Design_or_Procedure }""",
        "CRM-only path": """
            PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            PREFIX time: <http://www.w3.org/2006/time#>
            SELECT (COUNT(*) AS ?n) WHERE {
              ?place a crm:E53_Place .
              ?place crm:P4_has_time-span ?ts .
              ?ts a crm:E52_Time-Span ;
                  time:hasBeginning/time:inTimePosition/time:numericPosition ?y .
            }""",
    }
    result = {k: int(list(g.query(q))[0][0]) for k, q in checks.items()}
    loose = unanchored_instances(g)
    if loose:
        raise SystemExit(
            "Instanzen ohne CIDOC-CRM-Anker:\n  "
            + "\n  ".join(f"{s} — {', '.join(t)}" for s, t in loose[:10]))
    total = sum(1 for s in {s for s in g.subjects(RDF.type, None)}
                if not set(g.objects(s, RDF.type)) & VOCABULARY_TYPES)
    result["instances anchored in CRM"] = total
    return result


# --------------------------------------------------------------------------
def main() -> int:
    import pandas as pd

    ap = argparse.ArgumentParser(
        description="Build the standalone bundle from a CSV")
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "rdf" / "IPSDatedSites-bundle.ttl")
    ap.add_argument("--era", choices=("historical", "astronomical"),
                    default="historical")
    ap.add_argument("--no-type-sites", action="store_true",
                    help="Do not restate lado:DiscoverySite on referenced "
                         "published site nodes.")
    ap.add_argument("--no-materialise", action="store_true",
                    help="Leave the crosswalk to the store's reasoner. "
                         "CIDOC CRM queries will then return nothing "
                         "unless RDFS entailment is switched on.")
    args = ap.parse_args()

    csv = args.csv or sorted((ROOT / "data").glob("*.csv"))[0]
    df = pd.read_csv(csv)
    data = X.build_graph(df, args.era, "sites_dating_v1", False, "hash")
    onto = X.build_ontology()
    path, stats = build(data, onto, args.out, not args.no_materialise,
                        not args.no_type_sites)
    print(f"  {path.relative_to(ROOT)}  ({stats['total']} triples)")
    for k, v in verify(path).items():
        print(f"    {k:<22} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
