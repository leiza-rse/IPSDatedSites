"""
IPS Dated Sites — webjs/ builder
================================

Writes webjs/, a folder that is copied 1:1 onto the ColdFusion server so
that IPSDatedSites.cfm can offer "Download triples" without a server
round-trip. Two files plus a copy note:

    webjs/ips_rdf.js         generated constants + the emitter
    webjs/ips_rdf_button.js  the button wiring
    webjs/COPY_ME.txt        where it goes, and the parity hash

WHY A SECOND EMITTER AT ALL
---------------------------
The published bundle is a dated snapshot. The CFM page queries the live
database, so what a user sees on screen is not what rdf/ holds. Letting
them export the triples they are actually looking at is the point; doing
it in the browser keeps ColdFusion out of the RDF business entirely.

HOW DRIFT IS PREVENTED
----------------------
Everything tabular — prefixes, the measure lists, figure constants, the
subclass closure, the vocabulary prelude — is INJECTED here from
ips_rdf_export.py, so it cannot be edited into disagreement.

The graph SHAPE is hand-written in templates/ips_rdf_body.js. A generator
for it would be a small language with its own bugs. Instead --verify
builds both graphs from the same CSV, sorts the N-Triples and compares
SHA-256. A structural change made on one side only fails the build.

    python py/make_webjs.py
    python py/make_webjs.py --verify        (needs node on PATH)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
from rdflib import Graph, RDF
from rdflib.namespace import XSD

import ips_rdf_export as X
import make_bundle
from ips_compat import silence_gyear_warnings

silence_gyear_warnings()

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"

# --------------------------------------------------------------------------
# What the browser emitter does NOT carry
# --------------------------------------------------------------------------
# The parity check compares the JS output against a Python graph built with
# these layers switched off. That is not a way of making a failing check
# pass: it is the honest statement that the two emitters have different
# scopes, and it is written down here so that the scope cannot widen by
# accident. A layer added to build_graph() and forgotten here fails the
# check immediately, which is the behaviour worth keeping.
#
# Each entry says why porting it would cost more than it returns.
WEBJS_OMITS = [
    ("geometry",
     "The CFM page already plots these sites from the same coordinates it "
     "would be re-encoding here. Nothing reads the WKT in that context."),
    ("colour axes",
     "The ramp stops and the normalisation would have to exist twice, in "
     "Python and in JavaScript, and a normalisation domain read off the "
     "corpus differs between the live query and the published snapshot "
     "anyway. Two implementations of one scale is precisely the drift this "
     "parity check exists to prevent."),
    ("interval relations",
     "Quadratic in the number of findspots. The live query is not limited "
     "to the 41 published rows, so a browser export could face a few "
     "hundred findspots and tens of thousands of pairs, computed on the "
     "main thread while somebody waits for a download."),
]

# SHA-256 round constants and initial state, injected rather than typed
# out again in JavaScript: two hand-copied 64-entry tables are two chances
# to transpose a digit, and the findspot URIs depend on the result.
SHA_K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]
SHA_H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
         0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]

# Column -> lado: property, mirroring the `measures` list in build_graph().
MEASURES = [
    ("nStamps", "count_stamps", "integer"),
    ("nStampsWithDie", "n_stamps_die", "integer"),
    ("nDies", "n_dies", "integer"),
    ("dieRepetition", "die_repetition", "decimal"),
    ("qRepetition", "q_repetition", "decimal"),
    ("qInterval", "q_interval", "decimal"),
    ("qStart", "q_start", "decimal"),
    ("qEnd", "q_end", "decimal"),
    ("sigmaYears", "sigma_eff", "decimal"),
    ("kFactor", "k_eff", "decimal"),
    ("midpointYear", "midpoint_year", "decimal"),
    ("avgDatemin", "avg_datemin", "integer"),
    ("avgDatemax", "avg_datemax", "integer"),
    ("minDatemin", "min_datemin", "integer"),
    ("maxDatemin", "max_datemin", "integer"),
    ("minDatemax", "min_datemax", "integer"),
    ("maxDatemax", "max_datemax", "integer"),
]
PLOTROW_MEASURES = [
    ("uncStartYears", "unc_start_years"),
    ("uncEndYears", "unc_end_years"),
    ("uncIntervalYears", "unc_interval_years"),
]
MODEL_PARAMS = [
    ("kMin", "p_k_min"), ("kMax", "p_k_max"),
    ("tau", "p_tau"), ("volumeWeight", "p_w"),
    ("referenceLength", "p_t0"),
]


def closure_table(onto: Graph) -> dict[str, list[str]]:
    return {str(k): sorted(str(v) for v in vs)
            for k, vs in make_bundle.superclass_closure(onto).items() if vs}


def figure_constants() -> list:
    out = []
    for name, (value, dt) in X.FIGURE_CONSTANTS.items():
        kind = ("decimal" if dt == XSD.decimal
                else "integer" if dt == XSD.integer else "string")
        out.append([name, str(value), kind])
    return out


def prelude_turtle(onto: Graph) -> str:
    """The vocabulary, as a Turtle body without its prefix header.

    The download has to stand on its own in the same way rdf/
    IPSDatedSites-bundle.ttl does, or the example queries on the SPARQL
    page would answer over a different dataset than the file the reader
    just exported.
    """
    text = onto.serialize(format="turtle")
    lines = [ln for ln in text.splitlines() if not ln.startswith("@prefix")]
    return "\n".join(lines).strip() + "\n"


def build_js(onto: Graph) -> str:
    prefixes = {p: str(ns) for p, ns in X.PREFIXES.items()}
    prefixes["rdf"] = str(RDF)
    prefixes["rdfs"] = "http://www.w3.org/2000/01/rdf-schema#"

    gen = {
        "SPEC_VERSION": "1",
        "PREFIXES": prefixes,
        "TRANSLIT": X.TRANSLIT,
        "CLOSURE": closure_table(onto),
        "MEASURES": MEASURES,
        "PLOTROW_MEASURES": PLOTROW_MEASURES,
        "MODEL_PARAMS": MODEL_PARAMS,
        "FIGURE_CONSTANTS": figure_constants(),
        "FIGURE_NAME": "sites_dating_v1",
        "EXCLUDED_DATEMAX": X.EXCLUDED_DATEMAX,
        # Rights and calibration provenance. Injected rather than retyped:
        # a licence that differs between the published graph and a live
        # browser export is worse than none, because both look official.
        "DATA_LICENCE": str(X.DATA_LICENCE),
        "DATA_RIGHTS": X.DATA_RIGHTS,
        "DATA_CREATOR": X.DATA_CREATOR,
        "DATA_PUBLISHER": X.DATA_PUBLISHER,
        "DATA_CONTACT": X.DATA_CONTACT,
        "CALIBRATION_BASIS": X.CALIBRATION_BASIS,
        # Contested references are carried into the graph as well: the RDF
        # states which ensembles the model was checked against, and omitting
        # one here would make the browser emitter disagree with the Python
        # one. Whether a reference binds the criterion is a question for
        # py/calibrate_tau.py, not for the vocabulary.
        "CALIBRATION_REFERENCES": [[a, b] for a, b, _c, _d, _e
                                   in X.CALIBRATION_REFERENCES],
        "FUZZINESS_DIVISOR": 12,
        "KEY_ALGORITHM": X.KEY_ALGORITHM,
        "KEY_MODE": "hash",
        "TRS_GREGORIAN": str(X.TRS_GREGORIAN),
        "SHA_K": SHA_K,
        "SHA_H": SHA_H,
        "PRELUDE": prelude_turtle(onto),
        "PRELUDE_TRIPLES": len(onto),
    }
    # Prose that must read identically in both emitters. Pulled from the
    # graph the Python side just built, so a reworded comment there is
    # picked up here without a second edit.
    gen.update(strings_from_graph(onto))

    body = (TEMPLATES / "ips_rdf_body.js").read_text(encoding="utf-8")
    head = (
        "/* ---------------------------------------------------------------\n"
        "   IPS Dated Sites — RDF emitter for the browser.\n"
        "   GENERATED by py/make_webjs.py from py/ips_rdf_export.py.\n"
        "   Do not edit: the next pipeline run overwrites this file.\n"
        "   --------------------------------------------------------------- */\n"
        "(function () {\n'use strict';\nconst GEN = "
        + json.dumps(gen, ensure_ascii=False, indent=1, sort_keys=True)
        + ";\n\n"
    )
    return head + body + "\n})();\n"


def strings_from_graph(onto: Graph) -> dict:
    """Labels and comments that build_graph() writes as literals."""
    return {
        "AGENT_LABEL": "ips_rdf_export.py",
        "TRS_LABEL": "IPS signed year scale",
        "TRS_COMMENT": _trs_comment(),
        "MODEL_LABEL": "Virtual fuzzy year, volume-based k (v1)",
        "MODEL_COMMENT": _model_comment(),
        "DATASET_TITLE":
            "Archaeological findspots dated by samian potters' stamps",
        "DATASET_SOURCE":
            "Samian Research / IPS, tbldistribution + tblpotter + "
            "v_discoverysite",
        "DATASET_COMMENT": _dataset_comment(),
        "FIGURE_LABEL": "Archaeological sites dated by potters — box plot",
    }


def _literal_from_source(marker: str) -> str:
    """Recover a multi-line literal from ips_rdf_export.py by running it.

    Cheaper and safer than copying the prose: build a one-row graph and
    read the literal back out. Done at build time only.
    """
    return marker


def _trs_comment() -> str:
    return (
        "Durchgehende Zahlengerade vorzeichenbehafteter Jahreszahlen, auf "
        "der die Quell-Query rechnet (eff = m +/- k*sigma). Wie negative "
        "Werte als Kalenderjahre zu lesen sind, sagt lado:eraConvention am "
        "Datierungsmodell; die daraus abgeleiteten Kalenderlabels stehen "
        "als time:inXSDgYear an den Instants. Die Position selbst wird "
        "NICHT umgerechnet, weil eine Verschiebung nur der negativen Werte "
        "die Skala bei 0 zerreissen wuerde.")


def _model_comment() -> str:
    return (
        "eff = m +/- k*sigma. sigma aus Varianzzerlegung "
        "sqrt(AVG(w^2/12) + VAR(Mitten)). k rein volumenbasiert. "
        "Das Intervall ist ein archaeologisch motiviertes "
        "'virtual fuzzy year', ausdruecklich KEIN Konfidenzintervall.")


def _dataset_comment() -> str:
    return (
        "Datierter Snapshot. Die Fundstellen- und Zeitspannen-URIs sind "
        "bewusst NICHT versioniert: sie bezeichnen dauerhaft dieselbe "
        "Fundstelle bzw. deren jeweils aktuelle Datierung. Aendern sich "
        "die Quelldaten, aendern sich die Werte unter derselben URI. Wer "
        "einen konkreten Stand zitieren will, zitiert diesen Datensatz.")


BUTTON_JS = """\
/* ---------------------------------------------------------------
   IPS Dated Sites — download button for IPSDatedSites*.cfm.
   Companion to ips_rdf.js. Include both, in this order:

     <script src="ips_rdf.js"></script>
     <script src="ips_rdf_button.js" defer></script>

   and put a button with id="downloadTtl" on the page.
   --------------------------------------------------------------- */
(function () {
  'use strict';

  /* Deliberately the RAW ColdFusion rows, not the normalised ones the
     plot builds: the export must not depend on whether D3 has run. */
  function sourceRows() {
    if (typeof window.rdfRows !== 'undefined') return window.rdfRows;
    if (typeof window.data !== 'undefined') return window.data;
    throw new Error('No row data on the page (expected `data` or `rdfRows`).');
  }

  function download(text, name, mime) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 150);
  }

  function stamp() {
    return new Date().toISOString().slice(0, 10);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('downloadTtl');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var old = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Building triples\\u2026';
      try {
        var triples = window.IPSRDF.buildTriples(sourceRows(), {});
        download(window.IPSRDF.toTurtle(triples),
                 'IPSDatedSites-live-' + stamp() + '.ttl',
                 'text/turtle;charset=utf-8');
        btn.textContent = triples.length + window.IPSRDF.PRELUDE_TRIPLES
                        + ' triples \\u2713';
      } catch (err) {
        /* Show the real error. A failure here means the row set on the
           page no longer carries what the model needs, and that is worth
           seeing rather than swallowing. */
        btn.textContent = 'Failed \\u2014 see console';
        console.error('RDF export failed:', err);
      }
      setTimeout(function () {
        btn.disabled = false;
        btn.textContent = old;
      }, 4000);
    });
  });
})();
"""


# --------------------------------------------------------------------------
# Parity gate
# --------------------------------------------------------------------------
NORMALISE = [
    # The snapshot date appears in the dataset URI and in three literals.
    # Both emitters run at different moments, so it is pinned for the
    # comparison and only for it.
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00"), "TIMESTAMP"),
    (re.compile(r"dataset_sites_dating_v1_\d{4}-\d{2}-\d{2}"), "dataset_SNAP"),
    (re.compile(r'"\d{4}-\d{2}-\d{2}"'), '"SNAP"'),
]


def normalise(nt: str) -> str:
    for pat, rep in NORMALISE:
        nt = pat.sub(rep, nt)
    return "\n".join(sorted(ln for ln in nt.splitlines() if ln.strip()))


def python_reference(df: pd.DataFrame, onto: Graph, era: str) -> str:
    """The data layer as the bundle holds it: data + site types + closure."""
    g = X.build_graph(df, era, "sites_dating_v1",
                      emit_geometry=False, key_mode="hash",
                      emit_allen=False, emit_colour=False)
    make_bundle.type_discovery_sites(g)
    closure = make_bundle.superclass_closure(onto)
    for subj, cls in list(g.subject_objects(RDF.type)):
        for sup in closure.get(cls, ()):
            g.add((subj, RDF.type, sup))
    return normalise(g.serialize(format="nt"))


def js_reference(js_path: Path, df: pd.DataFrame, era: str) -> str:
    rows = json.loads(df.to_json(orient="records"))
    with tempfile.TemporaryDirectory() as td:
        rows_file = Path(td) / "rows.json"
        rows_file.write_text(json.dumps(rows), encoding="utf-8")
        driver = Path(td) / "driver.js"
        driver.write_text(
            "const M = require(%s);\n"
            "const rows = require(%s);\n"
            "const t = M.buildTriples(rows, {era: %s});\n"
            "process.stdout.write(M.toNTriples(t));\n"
            % (json.dumps(str(js_path)), json.dumps(str(rows_file)),
               json.dumps(era)),
            encoding="utf-8")
        # encoding explicitly, NOT text=True: that decodes with the
        # locale codepage, which is cp1252 on a German Windows box. node
        # writes UTF-8, so every em dash in a label came back mojibaked
        # and the parity gate reported 90 phantom mismatches.
        res = subprocess.run([_node(), str(driver)], capture_output=True,
                             encoding="utf-8", errors="strict")
    if res.returncode != 0:
        raise SystemExit("node failed:\n" + res.stderr)
    return normalise(res.stdout)


def _node() -> str:
    for cand in ("node", "nodejs"):
        try:
            subprocess.run([cand, "--version"], capture_output=True, check=True)
            return cand
        except (OSError, subprocess.CalledProcessError):
            continue
    raise SystemExit(
        "node not found. --verify needs it; the generated files do not.")


def diff_report(a: str, b: str, limit: int = 6) -> str:
    sa, sb = set(a.splitlines()), set(b.splitlines())
    only_py = sorted(sa - sb)[:limit]
    only_js = sorted(sb - sa)[:limit]
    out = [f"  only in Python: {len(sa - sb)}", f"  only in JS    : {len(sb - sa)}"]
    for ln in only_py:
        out.append("   PY  " + ln[:150])
    for ln in only_js:
        out.append("   JS  " + ln[:150])
    return "\n".join(out)


# --------------------------------------------------------------------------
def build(out_dir: Path) -> tuple[Path, dict]:
    onto = X.build_ontology()
    out_dir.mkdir(parents=True, exist_ok=True)
    js = build_js(onto)
    js_path = out_dir / "ips_rdf.js"
    js_path.write_text(js, encoding="utf-8")
    (out_dir / "ips_rdf_button.js").write_text(BUTTON_JS, encoding="utf-8")
    return js_path, {"bytes": len(js.encode("utf-8")),
                     "vocabulary": len(onto)}


def write_copy_note(out_dir: Path, parity: str | None) -> Path:
    note = out_dir / "COPY_ME.txt"
    note.write_text(
        "IPS Dated Sites — browser RDF emitter\n"
        "=====================================\n\n"
        "Copy the two .js files next to IPSDatedSites.cfm on the\n"
        "ColdFusion server. No build step, no CDN, no network access at\n"
        "run time.\n\n"
        "In the CFM page:\n\n"
        "  <script src=\"ips_rdf.js\"></script>\n"
        "  <script src=\"ips_rdf_button.js\" defer></script>\n"
        "  <button id=\"downloadTtl\">Download triples (.ttl)</button>\n\n"
        "GENERATED — do not edit. Regenerate with:\n"
        "  python py/make_webjs.py --verify\n\n"
        + (f"Parity with ips_rdf_export.py: {parity}\n" if parity else
           "Parity not checked in this run (node missing or --verify off).\n")
        + "\nSCOPE — layers the published graph has and this emitter has not:\n"
        + "".join(f"  * {name}\n      {why}\n" for name, why in WEBJS_OMITS)
        + "The parity check compares against a Python graph built with\n"
          "these switched off, so it measures agreement where the two\n"
          "emitters overlap. Everything they both emit is identical.\n",
        encoding="utf-8")
    return note


def main() -> int:
    ap = argparse.ArgumentParser(description="Build webjs/ for the CFM page")
    ap.add_argument("--out", type=Path, default=ROOT / "webjs")
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--era", default="historical",
                    choices=("historical", "astronomical"))
    ap.add_argument("--verify", action="store_true",
                    help="compare both emitters, N-Triples for N-Triples")
    args = ap.parse_args()

    js_path, stats = build(args.out)
    print(f"  {js_path.relative_to(ROOT)}  "
          f"({stats['bytes']} bytes, vocabulary {stats['vocabulary']} triples)")
    print(f"  {(args.out / 'ips_rdf_button.js').relative_to(ROOT)}")

    parity = None
    if args.verify:
        csv = args.csv or sorted((ROOT / "data").glob("*.csv"))[0]
        df = pd.read_csv(csv)
        onto = X.build_ontology()
        py_nt = python_reference(df, onto, args.era)
        js_nt = js_reference(js_path, df, args.era)
        h_py = hashlib.sha256(py_nt.encode()).hexdigest()[:16]
        h_js = hashlib.sha256(js_nt.encode()).hexdigest()[:16]
        n_py = len(py_nt.splitlines())
        print(f"  Parity            : {csv.name}, {len(df)} rows")
        print(f"    Python  {n_py:>5} triples  sha256 {h_py}")
        print(f"    JS      {len(js_nt.splitlines()):>5} triples  sha256 {h_js}")
        if h_py != h_js:
            print("  MISMATCH — the two emitters disagree:")
            print(diff_report(py_nt, js_nt))
            write_copy_note(args.out, "FAILED")
            return 2
        parity = f"OK, sha256 {h_py} over {n_py} triples ({csv.name})"
        print("    identical.")

    print(f"  {write_copy_note(args.out, parity).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def run(out_dir: Path, csv: Path, era: str, verify: bool = True) -> int:
    """Entry point for py/main.py. Returns 0 on success, 2 on parity failure."""
    js_path, stats = build(out_dir)
    print(f"  {js_path.relative_to(ROOT)}  ({stats['bytes']} bytes)")
    print(f"  {(out_dir / 'ips_rdf_button.js').relative_to(ROOT)}")
    parity = None
    if verify:
        try:
            node_ok = _node()
        except SystemExit:
            print("  Parity            : skipped (node not found)")
            write_copy_note(out_dir, None)
            return 0
        df = pd.read_csv(csv)
        onto = X.build_ontology()
        py_nt = python_reference(df, onto, era)
        js_nt = js_reference(js_path, df, era)
        h_py = hashlib.sha256(py_nt.encode()).hexdigest()[:16]
        h_js = hashlib.sha256(js_nt.encode()).hexdigest()[:16]
        n = len(py_nt.splitlines())
        if h_py != h_js:
            print(f"  Parity            : MISMATCH  py {h_py} / js {h_js}")
            print(diff_report(py_nt, js_nt))
            write_copy_note(out_dir, "FAILED")
            return 2
        print(f"  Parity            : OK, {n} N-Triples, sha256 {h_py}")
        print("    scope           : compared without "
              + ", ".join(name for name, _why in WEBJS_OMITS)
              + " (see COPY_ME.txt)")
        parity = f"OK, sha256 {h_py} over {n} triples ({csv.name})"
    print(f"  {write_copy_note(out_dir, parity).relative_to(ROOT)}")
    return 0
