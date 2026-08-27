"""
IPS Dated Sites — main script
=============================

One call, nine steps:

    0. Verify the CSV against the model it claims to carry
    1. CSV from data/  ->  rdf/  (Turtle + JSON-LD + LADO extension)
    2. Load the graph, retrieve everything by SPARQL
    3. Figures to img/, SVG + JPG at 300 dpi each, incl. the panel sheets
    4. Round-trip check CSV -> RDF -> SPARQL, field by field
    5. Standalone bundle to rdf/IPSDatedSites-bundle.ttl
    6. Browser RDF emitter to webjs/, with a parity check
    7. Query page to docs/sparql.html, from queries.yaml
    8. Documentation to docs/

Run from the REPOSITORY ROOT (Windows / VS Code):

    python py/main.py
    python py/main.py --era astronomical
    python py/main.py --csv data\\my_data.csv
    python py/main.py --skip-verify        # skip step 0
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import ips_compat
import build_sparql
import make_bundle
import verify as ips_verify
import make_docs
import make_instance_graphs
import make_webjs
import ips_render
import ips_sparql
from ips_rdf_export import build_graph, build_ontology

ROOT = Path(__file__).resolve().parent.parent


def _archived_retrieval_date(default: str) -> str:
    """The date data/source/ was fetched, from the last snapshot.

    Falls back to the given default when there is no snapshot yet, or when
    it carries no usable date: a first run on a fresh clone has nothing to
    read, and refusing to build for that would be worse than being a day
    out on a file that is about to be written anyway.
    """
    path = ROOT / "data" / "SNAPSHOT.json"
    try:
        retrieved = json.loads(path.read_text(encoding="utf-8"))["retrieved"]
    except (OSError, ValueError, KeyError, TypeError):
        return default
    return retrieved if isinstance(retrieved, str) and retrieved else default


def build_from_rest(offline: bool, timeout: float) -> tuple[Path, str, list]:
    """Get the corpus from the endpoints, recomputed and cross-checked.

    Three steps, and the middle one is the point of the exercise:

      1. /datedsites gives the stamps, one row per stamp with its potter's
         date range and, unlike the published statistics, the_id.
      2. py/ips_model.py recomputes the findspot table from them.
      3. /datedsitesstatistics gives the database's own aggregation of the
         same stamps. The two are compared column by column.

    Step 3 is what makes reading live safe rather than merely convenient.
    The recomputation is an independent implementation of the SQL; if it
    and the database agree to the last decimal on every column, the table
    the pipeline goes on to use is confirmed twice over. If they disagree,
    something has changed in the query that the Python has not followed,
    and building on it would publish the difference without noticing.

    Two columns are recomputed rather than read, because the statistics
    endpoint does not publish them: the_id, which comes from the stamp
    resource, and q_repetition.
    """
    import ips_model
    import ips_rest

    cache = ROOT / "data" / "source"
    paths, origin, notes = ips_rest.resolve(cache, offline=offline,
                                            timeout=timeout)
    for note in notes:
        print(f"  {note}")

    stamps = ips_model.load_stamps(paths["datedsites"])
    rows = ips_model.build(stamps, ips_model.DEFAULTS, [], 1)
    print(f"  Source            : {origin}  "
          f"({len(stamps)} stamps, {len(rows)} findspots)")

    # The cross-check corroborates; it does not produce the corpus. So a
    # DISAGREEMENT is fatal — one of the two implementations has moved and
    # the difference would be published unnoticed — while a reference that
    # cannot be read at all is not. Blocking every build because the
    # secondary resource changed format would be the tail wagging the dog,
    # and the recomputation is a complete implementation in its own right,
    # every row of which check 0 still verifies internally.
    crosscheck = "unavailable"
    try:
        reference = ips_rest.load_statistics(paths["datedsitesstatistics"])
    except SystemExit as exc:
        print(f"{exc}")
        print("  !!  Cross-check skipped: the reference could not be read.")
        print("      Building on the recomputation alone. It is an "
              "independent implementation and internally verified, but "
              "nothing is confirming it against the database on this run.")
    else:
        if ips_model.compare(rows, paths["datedsitesstatistics"]):
            raise SystemExit(
                "  !!  the recomputation disagrees with the database's own "
                "aggregation of the same stamps.\n"
                "      One of the two has moved. Do not build on this: check "
                "sql/IPSDatedSites.sql against py/ips_model.py before "
                "continuing, or pass --csv to use an existing export.")
        crosscheck = f"agrees on {len(reference)} findspots"
        print(f"  Cross-check       : agrees with the database on all "
              f"{len(reference)} findspots")

    # One CSV in data/, named for the day it was pulled. Written after the
    # cross-check, never before: a file in data/ is taken by everything
    # downstream as the corpus, and one that failed its check has no
    # business being there.
    #
    # "The day it was pulled" is today's date only when something was
    # actually pulled. A run that fell back to data/source/ — every CI run,
    # and any workstation run behind a firewall — replays a corpus that was
    # retrieved earlier, and stamping it with today's date says the opposite
    # of what happened: it renames the committed CSV, deletes the old one,
    # and moves the retrieval date in SNAPSHOT.json, none of which is a
    # change to the data. The archive keeps the date it already carries.
    stamp = date.today().isoformat()
    if origin != "live":
        stamp = _archived_retrieval_date(default=stamp)
    target = ROOT / "data" / f"ips_dated_sites_{stamp}.csv"
    for stale in (ROOT / "data").glob("ips_dated_sites_*.csv"):
        if stale != target:
            stale.unlink()
    ips_model.write_csv(rows, target)

    snapshot = ips_rest.snapshot(paths, retrieved=stamp)
    snapshot["origin"] = origin
    snapshot["crosscheck"] = crosscheck
    snapshot["findspots"] = len(rows)
    snapshot["sources"]["datedsites"]["records"] = len(stamps)
    snapshot["model"] = ips_model.DEFAULTS
    ips_rest.write_snapshot(snapshot, ROOT / "data" / "SNAPSHOT.json")

    return target, origin, notes


def find_csv(explicit: Path | None) -> Path:
    if explicit:
        return explicit
    candidates = sorted((ROOT / "data").glob("*.csv"))
    if not candidates:
        raise SystemExit(
            "No CSV in data/ and --no-rest was given. Drop --no-rest to "
            "read from the endpoints, put an export of "
            "sql/IPSDatedSites.sql in data/, or pass --csv.")
    if len(candidates) > 1:
        names = ", ".join(c.name for c in candidates)
        raise SystemExit(
            f"More than one CSV in data/: {names}\n"
            "The first was previously taken in silence — with two export "
            "states side by side the whole pipeline then runs on the wrong "
            "one. Leave exactly one CSV in data/, or pass --csv.")
    return candidates[0]


def rule(title: str) -> None:
    print(f"\n{title}\n" + "─" * max(46, len(title)))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="IPS Dated Sites: CSV -> RDF -> SPARQL -> figures")
    ap.add_argument("--csv", type=Path, default=None,
                    help="default: the CSV in data/")
    ap.add_argument("--rdf-out", type=Path, default=ROOT / "rdf",
                    help="target folder for TTL / JSON-LD")
    ap.add_argument("--img-out", type=Path, default=ROOT / "img",
                    help="target folder for the figures")
    ap.add_argument("--era", choices=("historical", "astronomical"),
                    default="historical",
                    help="reading of negative years. historical: "
                         "-40 = 40 BC -> xsd:gYear -0039.")
    ap.add_argument("--findspot-uri", choices=("hash", "slug"),
                    default="hash")
    ap.add_argument("--figure-name", default="sites_dating_v1")
    ap.add_argument("--emit-geometry", action="store_true")
    ap.add_argument("--skip-verify", action="store_true",
                    help="skip step 0. Only sensible when the CSV comes "
                         "from a different query on purpose.")
    ap.add_argument("--verify-strict", action="store_true",
                    help="in step 0, treat warnings as failures too")
    ap.add_argument("--verify-out", type=Path,
                    default=ROOT / "data" / "derived" / "verification.json",
                    help="target path of the verification report")
    ap.add_argument("--skip-plots", action="store_true")
    ap.add_argument("--skip-docs", action="store_true")
    ap.add_argument("--skip-bundle", action="store_true")
    ap.add_argument("--skip-webjs", action="store_true")
    ap.add_argument("--skip-webjs-verify", action="store_true",
                    help="build webjs/ but skip the parity check "
                         "(for instance when node is unavailable)")
    ap.add_argument("--webjs-out", type=Path, default=ROOT / "webjs")
    ap.add_argument("--skip-sparql", action="store_true")
    ap.add_argument("--skip-graphs", action="store_true")
    ap.add_argument("--graphs-out", type=Path,
                    default=ROOT / "img" / "graphs")
    ap.add_argument("--docs-out", type=Path, default=ROOT / "docs")
    ap.add_argument("--no-rest", action="store_true",
                    help="do not read the endpoints; use the CSV in data/ "
                         "as it stands. Reproduces an older build exactly.")
    ap.add_argument("--offline", action="store_true",
                    help="recompute from the cached payloads in data/source/ "
                         "without attempting the network.")
    ap.add_argument("--rest-timeout", type=float, default=20.0)
    ap.add_argument("--report-out", type=Path, default=ROOT / "docs",
                    help="where the build report goes. Two files: "
                         "run-report.html and run-report.txt.")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args()

    import pandas as pd

    # The corpus comes from the endpoints unless told otherwise. An explicit
    # --csv still wins: reproducing an older build is a legitimate thing to
    # want, and it should not require the server to be up.
    if args.csv:
        csv = args.csv
        print(f"  Source            : {csv} (given explicitly)")
    elif args.no_rest:
        csv = find_csv(None)
        print(f"  Source            : {csv.name} (--no-rest; age unchecked)")
    else:
        rule("REST  Samian Research")
        csv, _origin, _notes = build_from_rest(args.offline,
                                               args.rest_timeout)
        print()
    out = args.rdf_out
    img = args.img_out
    out.mkdir(parents=True, exist_ok=True)
    img.mkdir(parents=True, exist_ok=True)

    # ---- 0. Verification ------------------------------------------------
    # The query is authoritative; nothing is recomputed here. Every
    # published value is recovered from the other columns of the SAME row.
    # If that fails, the CSV is not the output of the query it is taken to
    # be — and everything downstream models something other than what is
    # assumed.
    if not args.skip_verify:
        rule("0 · Verification  CSV against the model")
        marks = {"pass": "ok", "warn": "!!", "fail": "XX", "info": "--"}
        vreport = ips_verify.verify(csv)
        for check in vreport.checks:
            print(f"  [{marks[check.status]}] {check.key:<3} {check.title}")
            if check.status != "pass":
                print(f"         {check.detail}")
        args.verify_out.parent.mkdir(parents=True, exist_ok=True)
        args.verify_out.write_text(
            json.dumps(vreport.to_dict(), indent=2, ensure_ascii=False,
                       sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"  Report            : {args.verify_out.relative_to(ROOT)}")
        if vreport.failed or (args.verify_strict and vreport.warned):
            print("\n  Stopping: the CSV does not carry the model it "
                  "claims to carry.")
            return 2

    # ---- 1. Export ------------------------------------------------------
    rule("1 · Export  CSV -> RDF")
    df = pd.read_csv(csv)
    print(f"  Source            : {csv.relative_to(ROOT)}  ({len(df)} rows)")
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
    print(f"  Ontology          : {onto_path.name}  ({len(onto)} triples)")
    print(f"  Graph             : {ttl_path.name}  ({len(g)} triples)")
    print(f"  JSON-LD           : {jld_path.name}")
    print(f"  Era convention    : {args.era}")
    print(f"  Findspot URI      : {args.findspot_uri}")
    bc = ips_compat.count_bc_gyears(g)
    if bc:
        print(f"  BC years          : {bc} gYear literals before year 1")
        print("                      (rdflib < 7.5 cannot turn them into a")
        print("                       Python date; the literals themselves")
        print("                       are correct, see ips_compat)")

    # ---- 2. Back out of the graph ---------------------------------------
    rule("2 · Retrieval  RDF -> SPARQL")
    gr = ips_sparql.load(ttl_path)
    print(f"  Read-back check   : OK, {len(gr)} triples parsed")
    fig_const = ips_sparql.figure_constants(gr)
    era = ips_sparql.era(gr)
    model = ips_sparql.model(gr)
    rows = ips_sparql.rows(gr)
    print(f"  Figure constants  : from the graph "
          f"(rowOrder='{fig_const['rowOrder']}', "
          f"ramp={fig_const['colourRamp']})")
    print(f"  Model             : k_min={model['kMin']}, "
          f"k_max={model['kMax']}, tau={model['tau']}, w={model['w']}")
    print(f"  Rows              : {len(rows)}")

    # ---- 3. Figures ------------------------------------------------------
    if not args.skip_plots:
        rule("3 · Figures")
        for label, fn, kw in (
            ("v1 classic", ips_render.render_classic, {}),
            ("v2 modern", ips_render.render_modern, {"model": model}),
            ("v2 gauss", ips_render.render_gauss, {"model": model}),
        ):
            paths = fn(fig_const, rows, era, img, **kw)
            names = ", ".join(p.name for p in paths)
            print(f"  {label:<12}: {names}")

        # The two panel sheets. They read the CSV directly rather than the
        # SPARQL rows, because the calibration argument has to be checkable
        # against the source table without a graph in between.
        import make_calibration_panels as panels
        sel = panels.select(panels.load_rows(csv))
        for group, stem, title in (
            ("reference", "plot_v3_calibration",
             panels.calibration_title()),
            ("comparison", "plot_v3_findspots",
             "Five further findspots, across the range of the corpus"),
        ):
            sheet = [r for r in sel if r["_role"] == group]
            names = ", ".join(
                q.name for q in panels.render(sheet, img, era, stem, title))
            print(f"  {stem:<12}: {names}")

        # Contested references are drawn but do not count: the criterion
        # that fixes tau must not be reported as met or missed by a
        # terminus deliberately kept out of it.
        binding = [r for r in sel if r["_terminus"] is not None
                   and not r.get("_contested")]
        inside = sum(1 for r in binding
                     if panels.num(r["eff_start"]) <= r["_terminus"]
                     <= panels.num(r["eff_end"]))
        total = len(binding)
        flag = "OK" if inside == total else "!!"
        print(f"  {flag} terminus inside the modelled interval: "
              f"{inside} of {total}")

    # ---- 4. Round trip ---------------------------------------------------
    rule("4 · Round trip  CSV -> RDF -> SPARQL")
    ok = ips_sparql.roundtrip(rows, csv)

    # ---- 5. Standalone-Bundle -------------------------------------------
    # Data + vocabulary + a materialised CIDOC CRM crosswalk in one
    # file. Materialised because triplestores generally do not reason over
    # rdfs:subClassOf — without it a CRM query against the N4O KG returns
    # nothing at all.
    if not args.skip_bundle:
        rule("5 · Standalone bundle")
        bpath, bstats = make_bundle.build(
            g, onto, out / "IPSDatedSites-bundle.ttl")
        print(f"  {bpath.name}  ({bstats['total']} triples)")
        print(f"    vocabulary {bstats['ontology']}, data {bstats['data']}, "
              f"site types {bstats['sites_typed']}, "
              f"materialised {bstats['inferred']}")
        print("  Counter-check, plain CRM/OWL-Time queries without a reasoner:")
        for k, v in make_bundle.verify(bpath).items():
            print(f"    {k:<22} {v}")

    # ---- 6. Browser emitter -----------------------------------------------
    # webjs/ is copied verbatim onto the ColdFusion server so that the CFM
    # page can export the rows it is showing, live from the database. The
    # tabular parts are injected from ips_rdf_export.py; the graph shape is
    # hand-written and held in step by a parity check: both emitters build
    # from the same CSV, N-Triples sorted, SHA-256 compared.
    if not args.skip_webjs:
        rule("6 · Browser emitter (webjs/)")
        if make_webjs.run(args.webjs_out, csv, args.era,
                          verify=not args.skip_webjs_verify) != 0:
            ok = False

    # ---- 7. Query page ----------------------------------------------------
    # queries.yaml -> docs/sparql.html + .rq files + qmd/. Every example
    # query runs against the real graph; an empty result fails the step,
    # because SPARQL does not fail on a mistyped IRI, it stays silent.
    if not args.skip_sparql:
        rule("7 · Query page (queries.yaml)")
        if build_sparql.run(args.docs_out) != 0:
            ok = False

    # ---- 8. Documentation -------------------------------------------------
    # Regenerated on every run so that it cannot drift away from the code.
    # The structure comes from the code, the prose from py/ips_docs_text.py.
    if not args.skip_docs:
        rule("8 · Documentation")
        for pth in make_docs.build(args.docs_out, gr):
            print(f"  {pth.relative_to(ROOT)}")

    # ---- 9. Instance graphs ----------------------------------------------
    # Real subgraphs, cut with CONSTRUCT and laid out by GraphViz. The
    # Mermaid diagrams show the model; these show the triples. Skipped
    # with a note if GraphViz is absent, because the SVGs are committed.
    if not args.skip_graphs:
        rule("9 \u00b7 Instance graphs (img/graphs/)")
        if make_instance_graphs.run(
                out / "IPSDatedSites-bundle.ttl", args.graphs_out) != 0:
            ok = False

    rule("Result")
    print("  " + ("All consistent." if ok
                  else "Round trip failed — see above."))
    print(f"  RDF        : {out}")
    print(f"  Figures    : {img}")
    if not args.skip_docs:
        print(f"  Docs       : {args.docs_out}")
    return 0 if ok else 2


def run() -> int:
    """main() with everything it prints captured for the report.

    The capture wraps main() rather than living inside it, so that a run
    that stops — whether by SystemExit or by an unhandled exception — still
    produces a report. That is the run whose report is worth the most: the
    log ends exactly where the trouble was, and the last known state is on
    disk beside it.
    """
    import run_report

    stdout, stderr = sys.stdout, sys.stderr
    tee = run_report.Tee(stdout)
    sys.stdout = tee
    sys.stderr = run_report.Tee(stderr) if stderr is not stdout else tee

    code = 0
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if exc.code:
            print(f"{exc}")
    except Exception:
        import traceback
        traceback.print_exc(file=tee)
        code = 1
    finally:
        log = tee.text
        sys.stdout, sys.stderr = stdout, stderr

        argv = sys.argv[1:]
        if "--no-report" not in argv:
            out = ROOT / "docs"
            if "--report-out" in argv:
                out = Path(argv[argv.index("--report-out") + 1])
            written = run_report.write(log, out, ok=(code == 0))
            for path in written:
                print(f"  Report            : {path.relative_to(ROOT)}")
    return code


if __name__ == "__main__":
    sys.exit(run())
