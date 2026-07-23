"""
IPS Dated Sites — Hauptskript
=============================

Ein Aufruf, vier Schritte:

    1. CSV aus data/  ->  rdf/  (Turtle + JSON-LD + LADO-Erweiterung)
    2. Graph laden, alles per SPARQL abfragen
    3. Zwei Abbildungen nach img/, je SVG + JPG 300 dpi
    4. Rundlaufpruefung CSV -> RDF -> SPARQL, Feld fuer Feld
    5. Standalone-Bundle nach rdf/IPSDatedSites-bundle.ttl
    6. Dokumentation nach docs/ neu erzeugen

Aufruf aus der REPO-WURZEL (Windows / VS Code):

    python py/main.py
    python py/main.py --era astronomical
    python py/main.py --csv data\\meine_daten.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ips_compat
import make_bundle
import make_docs
import ips_render
import ips_sparql
from ips_rdf_export import build_graph, build_ontology

ROOT = Path(__file__).resolve().parent.parent


def find_csv(explicit: Path | None) -> Path:
    if explicit:
        return explicit
    candidates = sorted((ROOT / "data").glob("*.csv"))
    if not candidates:
        raise SystemExit(
            "Keine CSV in data/ gefunden. Ergebnis von "
            "IPSDatedSites25_final.sql dort ablegen oder --csv angeben.")
    if len(candidates) > 1:
        print(f"Mehrere CSV in data/, nehme: {candidates[0].name}")
    return candidates[0]


def rule(title: str) -> None:
    print(f"\n{title}\n" + "─" * max(46, len(title)))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="IPS Dated Sites: CSV -> RDF -> SPARQL -> Abbildungen")
    ap.add_argument("--csv", type=Path, default=None,
                    help="Standard: erste CSV in data/")
    ap.add_argument("--rdf-out", type=Path, default=ROOT / "rdf",
                    help="Zielordner fuer TTL / JSON-LD")
    ap.add_argument("--img-out", type=Path, default=ROOT / "img",
                    help="Zielordner fuer die Abbildungen")
    ap.add_argument("--era", choices=("historical", "astronomical"),
                    default="historical",
                    help="Lesart negativer Jahreszahlen. historical: "
                         "-40 = 40 v.Chr. -> xsd:gYear -0039.")
    ap.add_argument("--findspot-uri", choices=("hash", "slug"),
                    default="hash")
    ap.add_argument("--figure-name", default="sites_dating_v1")
    ap.add_argument("--emit-geometry", action="store_true")
    ap.add_argument("--skip-plots", action="store_true")
    ap.add_argument("--skip-docs", action="store_true")
    ap.add_argument("--skip-bundle", action="store_true")
    ap.add_argument("--docs-out", type=Path, default=ROOT / "docs")
    args = ap.parse_args()

    import pandas as pd

    csv = find_csv(args.csv)
    out = args.rdf_out
    img = args.img_out
    out.mkdir(parents=True, exist_ok=True)
    img.mkdir(parents=True, exist_ok=True)

    # ---- 1. Export ------------------------------------------------------
    rule("1 · Export  CSV -> RDF")
    df = pd.read_csv(csv)
    print(f"  Quelle            : {csv.relative_to(ROOT)}  ({len(df)} Zeilen)")
    onto = build_ontology()
    g = build_graph(df, args.era, args.figure_name,
                    args.emit_geometry, args.findspot_uri)

    onto_path = out / "lado_dating_extension.ttl"
    ttl_path = out / f"ips_{args.figure_name}.ttl"
    jld_path = out / f"ips_{args.figure_name}.jsonld"
    onto.serialize(destination=onto_path, format="turtle", encoding="utf-8")
    g.serialize(destination=ttl_path, format="turtle", encoding="utf-8")
    g.serialize(destination=jld_path, format="json-ld", indent=2,
                auto_compact=True, encoding="utf-8")
    print(f"  Ontologie         : {onto_path.name}  ({len(onto)} Tripel)")
    print(f"  Graph             : {ttl_path.name}  ({len(g)} Tripel)")
    print(f"  JSON-LD           : {jld_path.name}")
    print(f"  Aera-Konvention   : {args.era}")
    print(f"  Findspot-URI      : {args.findspot_uri}")
    bc = ips_compat.count_bc_gyears(g)
    if bc:
        print(f"  v.Chr.-Jahre      : {bc} gYear-Literale vor Jahr 1")
        print("                      (rdflib < 7.5 kann sie nicht in ein")
        print("                       Python-date wandeln; die Literale")
        print("                       selbst sind korrekt, siehe ips_compat)")

    # ---- 2. Zurueck aus dem Graphen -------------------------------------
    rule("2 · Abruf  RDF -> SPARQL")
    gr = ips_sparql.load(ttl_path)
    print(f"  Rueckleseprobe    : OK, {len(gr)} Tripel geparst")
    fig_const = ips_sparql.figure_constants(gr)
    era = ips_sparql.era(gr)
    model = ips_sparql.model(gr)
    rows = ips_sparql.rows(gr)
    print(f"  Figur-Konstanten  : aus dem Graphen "
          f"(rowOrder='{fig_const['rowOrder']}', "
          f"ramp={fig_const['colourRamp']})")
    print(f"  Modell            : k_min={model['kMin']}, "
          f"k_max={model['kMax']}, tau={model['tau']}, w={model['w']}")
    print(f"  Zeilen            : {len(rows)}")

    # ---- 3. Abbildungen -------------------------------------------------
    if not args.skip_plots:
        rule("3 · Abbildungen")
        for label, fn, kw in (
            ("v1 classic", ips_render.render_classic, {}),
            ("v2 modern", ips_render.render_modern, {"model": model}),
        ):
            paths = fn(fig_const, rows, era, img, **kw)
            names = ", ".join(p.name for p in paths)
            print(f"  {label:<12}: {names}")

    # ---- 4. Rundlauf ----------------------------------------------------
    rule("4 · Rundlauf  CSV -> RDF -> SPARQL")
    ok = ips_sparql.roundtrip(rows, csv)

    # ---- 5. Standalone-Bundle -------------------------------------------
    # Daten + Vokabular + materialisierter CIDOC-CRM-Crosswalk in einer
    # Datei. Materialisiert, weil Triplestores in der Regel nicht ueber
    # rdfs:subClassOf schliessen — ohne das liefert eine CRM-Abfrage im
    # N4O-KG null Treffer.
    if not args.skip_bundle:
        rule("5 · Standalone-Bundle")
        bpath, bstats = make_bundle.build(
            g, onto, out / "IPSDatedSites-bundle.ttl")
        print(f"  {bpath.name}  ({bstats['total']} Tripel)")
        print(f"    Vokabular {bstats['ontology']}, Daten {bstats['data']}, "
              f"Fundplatz-Typen {bstats['sites_typed']}, "
              f"materialisiert {bstats['inferred']}")
        print("  Gegenprobe, reine CRM/OWL-Time-Abfragen ohne Reasoner:")
        for k, v in make_bundle.verify(bpath).items():
            print(f"    {k:<22} {v}")

    # ---- 6. Dokumentation ------------------------------------------------
    # Wird bei jedem Lauf neu erzeugt, damit sie nicht vom Code wegdriften
    # kann. Struktur kommt aus dem Code, Prosa aus py/ips_docs_text.py.
    if not args.skip_docs:
        rule("6 · Dokumentation")
        for pth in make_docs.build(args.docs_out):
            print(f"  {pth.relative_to(ROOT)}")

    rule("Ergebnis")
    print("  " + ("Alles konsistent." if ok
                  else "Rundlauf fehlgeschlagen — siehe oben."))
    print(f"  RDF        : {out}")
    print(f"  Abbildungen: {img}")
    if not args.skip_docs:
        print(f"  Dokumentation: {args.docs_out}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
