"""
IPS Dated Sites — the query page, from queries.yaml
===================================================

One source, three products, so that they cannot drift apart:

    docs/query/index.html          a catalogue of the queries
    docs/query/<id>.html           one interactive page per query
    docs/query/all.html            all of them on one page, as before
    docs/query/rq/*.rq             the same queries as plain files
    docs/sparql.html               a redirect stub, see WHY A STUB below
    qmd/<name>.qmd                 the quarto-live variant, for OER reuse
    docs/map.html, docs/map.geojson   the map, via py/build_map.py

NO ENDPOINT, NO SERVER
----------------------
The graph is a static Turtle file, fetched by the browser and parsed
client-side by rdflib under Pyodide. That is deliberate for supplementary
material: an archived copy of this repository stays queryable with no
service to keep alive, and nothing the reader types leaves their machine.

EVERY QUERY RUNS BEFORE IT SHIPS
--------------------------------
Every query is executed against the real graph here, before any page is
written. **A query that returns no rows fails the build.**

That is not pedantry. SPARQL does not fail on a mistyped IRI, it returns
nothing. An empty result is therefore the ordinary symptom of a broken
graph rather than of a boring question. A page whose examples do not run
is worse than no page: the reader cannot tell whether they broke it or
whether it arrived broken.

JEKYLL
------
docs/ is a Jekyll site, so the generated page carries YAML front matter
and uses the existing layout — navigation and appearance then come from
one source rather than two. Because Jinja2 and Liquid both use {% ... %},
Jinja runs here with [% ... %] and [[ ... ]]; that lets the template hold
a literal {% raw %} for Jekyll, which shields the JavaScript block from
Liquid.

Run:
    python py/build_sparql.py
    python py/main.py                  (as step 7)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ips_compat import silence_gyear_warnings  # noqa: E402

silence_gyear_warnings()

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"
QUERIES_YAML = ROOT / "queries.yaml"
QMD_DIR = ROOT / "qmd"
# The query layer lives under docs/query/. Two owners write into that
# folder: this module writes index.html and rq/, py/make_talk_figures.py
# writes closed-groups.html with its stylesheet and its own .rq. They are
# kept apart by folder rather than by good intentions — write_rq_files()
# clears its target directory, and pointing it at docs/query/ itself would
# delete the talk page's query file on the next run.
QUERY_DIRNAME = "query"
RQ_DIRNAME = "rq"

# VIEWS
# -----
# A query page shows a table. Some results are better read as something
# else: a set of points, or a set of intervals on a scale. queries.yaml can
# therefore give a query a `view`, and the page draws that ABOVE the table.
#
# Above, never instead. These queries are meant to be edited, and an edit
# that drops the column a view needs would otherwise leave a blank panel
# with no explanation. The view says what is missing; the table stays.
VIEW_LABELS = {
    "table": "table",
    "map": "table and map",
    "intervals": "table and interval bars",
    "scatter": "table and scatter plot",
    "barchart": "table and bar chart",
}

# The columns each view reads, and what it falls back on. Declared here
# rather than in the template so that a query asking for a view it cannot
# feed fails at build time with the query's name attached, instead of
# leaving a blank panel in a browser.
VIEW_COLUMNS = {
    "table": {},
    "map": {},
    "intervals": {"from": "from", "to": "to", "label": "findspot"},
    "scatter": {"x": "x", "y": "y", "label": "findspot"},
    "barchart": {"category": "category", "value": "value"},
}

# Leaflet, pinned exactly as in py/build_map.py. Imported from there rather
# than repeated, so a version bump happens once.

# WHY A STUB
# ----------
# docs/sparql.html was the published address of this page and is wired into
# the live ColdFusion application through webjs/CFM_PATCH.md. GitHub Pages
# performs no redirects without a plugin, so the old path keeps a small
# page that forwards. Three lines against a dead link in somebody else's
# application is a trade worth making, and it costs nothing to keep.
REDIRECT_STUB = """\
<!DOCTYPE html>
<meta charset="utf-8">
<title>Moved &mdash; the query page is now at query/</title>
<link rel="canonical" href="query/">
<meta http-equiv="refresh" content="0; url=query/">
<p>The query page has moved to <a href="query/">query/</a>.</p>
"""

# Pinned so that an archived copy keeps working. An unpinned CDN path
# follows whatever Pyodide ships next, and an rdflib that no longer
# parses this Turtle would break the page silently, years after anyone
# is still watching.
PYODIDE_VERSION = "0.26.4"
RDFLIB_VERSION = "7.1.1"

# How many result rows the browser renders. Some queries are
# deliberately unbounded, and an unlimited table can hang a phone.
MAX_ROWS = 500


def load_config() -> dict:
    import yaml
    if not QUERIES_YAML.exists():
        sys.exit(f"  !!  {QUERIES_YAML.name} is missing.")
    cfg = yaml.safe_load(QUERIES_YAML.read_text(encoding="utf-8")) or {}
    for key in ("graph", "prefixes", "queries"):
        if key not in cfg:
            sys.exit(f"  !!  queries.yaml must contain the key '{key}'.")
    graph_file = ROOT / cfg["graph"]["file"]
    if not graph_file.exists():
        sys.exit(f"  !!  {graph_file} is missing. Build the graph first.")
    return cfg


def check_queries(cfg: dict, graph_file: Path) -> bool:
    """Every query against the real graph. Zero rows means failure."""
    from rdflib import Graph

    base = Graph()
    base.parse(graph_file, format="turtle")
    print(f"  Graph             : {graph_file.name}  ({len(base)} triples)")

    ok = True
    for q in cfg["queries"]:
        try:
            rows = list(base.query(cfg["prefixes"] + "\n" + q["sparql"]))
        except Exception as exc:                        # noqa: BLE001
            print(f"    !! {q['id']:<22} {type(exc).__name__}: {exc}")
            ok = False
            continue
        q["rows_at_build"] = len(rows)
        if rows:
            print(f"    OK {q['id']:<22} {len(rows):>4} rows")
        else:
            print(f"    !! {q['id']:<22}    0 rows — parses, matches nothing")
            ok = False
    return ok


def write_rq_files(cfg: dict, docs: Path) -> Path:
    """Each query as a plain .rq file, for use outside the browser."""
    out_dir = docs / QUERY_DIRNAME / RQ_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.rq"):      # drop renamed leftovers
        stale.unlink()
    for q in cfg["queries"]:
        intro = "\n".join(
            f"# {line}" for line in
            textwrap.wrap(" ".join(str(q.get("intro", "")).split()), 76))
        text = (f"# {q['title']}\n{intro}\n\n"
                f"{cfg['prefixes'].rstrip()}\n\n{q['sparql'].rstrip()}\n")
        (out_dir / f"{q['id']}.rq").write_text(text, encoding="utf-8")
    return out_dir


def query_view(q: dict) -> tuple[str, dict]:
    """(view, {role: column}) for one query, defaults filled in."""
    view = q.get("view") or "table"
    if view not in VIEW_LABELS:
        sys.exit(f"  !!  query '{q['id']}' asks for an unknown view "
                 f"'{view}'. Known: {', '.join(sorted(VIEW_LABELS))}.")
    cols = dict(VIEW_COLUMNS[view])
    given = q.get("view_columns") or {}
    unknown = set(given) - set(cols)
    if unknown and cols:
        sys.exit(f"  !!  query '{q['id']}' names view column(s) "
                 f"{sorted(unknown)} that the '{view}' view does not use. "
                 f"It reads {sorted(cols)}.")
    cols.update(given)
    return view, cols


def blurb(text: str, limit: int = 220) -> str:
    """The first sentence or so of an intro, for the catalogue."""
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    stop = cut.rfind(". ")
    return (cut[:stop + 1] if stop > 60 else cut.rstrip() + "\u2026")


def _env():
    """Jinja2 with square delimiters — see JEKYLL in the module header."""
    from jinja2 import Environment, FileSystemLoader
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        block_start_string="[%", block_end_string="%]",
        variable_start_string="[[", variable_end_string="]]",
        comment_start_string="[#", comment_end_string="#]",
        autoescape=False, keep_trailing_newline=True)


def build(docs: Path = ROOT / "docs", strict: bool = True) -> list[Path]:
    cfg = load_config()
    graph_cfg = dict(cfg["graph"])
    graph_file = ROOT / graph_cfg["file"]

    if not check_queries(cfg, graph_file):
        if strict:
            sys.exit("  !!  A query does not work — nothing written.")
        print("  !!  Queries faulty, written anyway (--no-strict).")

    written = [write_rq_files(cfg, docs)]

    # The browser fetches the graph relative to the page. The file stays at
    # the site root — it is the citable artefact and qmd/ hard-codes its
    # absolute URL — so the page, one directory down, reaches it with ../.
    if graph_cfg.get("publish"):
        target = docs / graph_cfg["url"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(graph_file, target)
        written.append(target)
    graph_cfg["page_url"] = "../" + graph_cfg["url"]
    graph_cfg["megabytes"] = f"{graph_file.stat().st_size / 1e6:.1f}"

    queries = []
    for q in cfg["queries"]:
        item = dict(q)
        item["sparql"] = q["sparql"].rstrip("\n")
        # Size the editor to the query, so nothing hides behind a scrollbar
        # the reader has to discover first.
        item["rows"] = max(6, item["sparql"].count("\n") + 2)
        queries.append(item)

    env = _env()
    page = cfg.get("page", {})
    html = env.get_template("sparql.html.j2").render(
        page=page, graph=graph_cfg, queries=queries,
        pyodide_version=PYODIDE_VERSION, rdflib_version=RDFLIB_VERSION,
        qmd_file=cfg.get("qmd", {}).get("file"),
        max_rows=MAX_ROWS,
        prefixes_json=json.dumps(cfg["prefixes"]),
        graph_json=json.dumps(graph_cfg, ensure_ascii=False),
        queries_json=json.dumps({q["id"]: q["sparql"] for q in queries},
                                ensure_ascii=False))
    query_dir = docs / QUERY_DIRNAME
    query_dir.mkdir(parents=True, exist_ok=True)

    # The combined page keeps working, at a name of its own.
    all_path = query_dir / "all.html"
    all_path.write_text(html, encoding="utf-8")
    written.append(all_path)

    # One page per query.
    import build_map
    page_tpl = env.get_template("query_page.html.j2")
    catalogue = []
    for q in queries:
        view, view_cols = query_view(q)
        page_html = page_tpl.render(
            query=q, view=view, view_cols=view_cols,
            view_cols_json=json.dumps(view_cols), graph=graph_cfg,
            pyodide_version=PYODIDE_VERSION, rdflib_version=RDFLIB_VERSION,
            leaflet_version=build_map.LEAFLET_VERSION,
            leaflet_sri_js=build_map.LEAFLET_SRI_JS,
            leaflet_sri_css=build_map.LEAFLET_SRI_CSS,
            max_rows=MAX_ROWS,
            prefixes_json=json.dumps(cfg["prefixes"]),
            graph_json=json.dumps(graph_cfg, ensure_ascii=False),
            query_json=json.dumps(q["sparql"], ensure_ascii=False))
        path = query_dir / f"{q['id']}.html"
        path.write_text(page_html, encoding="utf-8")
        written.append(path)
        catalogue.append({
            "id": q["id"], "title": q["title"],
            "blurb": blurb(q.get("intro", "")),
            "view_label": VIEW_LABELS[view],
            "rows_at_build": q.get("rows_at_build", "?"),
        })

    html_path = query_dir / "index.html"
    html_path.write_text(
        env.get_template("query_index.html.j2").render(
            page=page, queries=catalogue, graph=graph_cfg,
            extras=cfg.get("query_extras", [])),
        encoding="utf-8")
    written.append(html_path)

    stub_path = docs / "sparql.html"
    stub_path.write_text(REDIRECT_STUB, encoding="utf-8")
    written.append(stub_path)

    # The map is generated from the same config and the same graph, so it
    # cannot describe a different corpus than the query page beside it.
    import build_map
    written.extend(build_map.build(cfg, docs, env))

    qmd_cfg = dict(cfg.get("qmd", {}))
    if qmd_cfg.get("file"):
        QMD_DIR.mkdir(exist_ok=True)
        qmd_cfg.setdefault("title", page.get("title", "Querying the graph"))
        qmd_cfg["graph_url"] = qmd_cfg.get("graph_url") or graph_cfg["url"]
        qmd_cfg["megabytes"] = graph_cfg["megabytes"]
        qmd = env.get_template("sparql.qmd.j2").render(
            graph=graph_cfg, queries=queries, qmd=qmd_cfg,
            rdflib_version=RDFLIB_VERSION,
            prefixes=cfg["prefixes"].rstrip("\n"))
        qmd_path = QMD_DIR / qmd_cfg["file"]
        qmd_path.write_text(qmd, encoding="utf-8")
        written.append(qmd_path)

    return written


def run(docs: Path, strict: bool = True) -> int:
    """Entry point for py/main.py."""
    for module in ("jinja2", "yaml", "rdflib"):
        try:
            __import__(module)
        except Exception as exc:                        # noqa: BLE001
            print(f"  !!  {module} is required: {type(exc).__name__}")
            return 2
    try:
        for p in build(docs, strict):
            print(f"  {p.relative_to(ROOT)}")
    except SystemExit as exc:
        print(f"  {exc}")
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="queries.yaml -> docs/sparql.html + .rq + qmd/")
    ap.add_argument("--docs", type=Path, default=ROOT / "docs")
    ap.add_argument("--no-strict", action="store_true",
                    help="write even if a query matches nothing")
    args = ap.parse_args()
    return run(args.docs, strict=not args.no_strict)


if __name__ == "__main__":
    sys.exit(main())
