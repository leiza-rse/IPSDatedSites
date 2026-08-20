# IPSDatedSites — drop-in patch (browser emitter + query page)

Built and tested against the repository state of commit `caeb7f1` ("new
pipeline"), with `data/data-1787218454884.csv`. Unpack over the repository
root; every file lands where it belongs.

    xcopy IPSDatedSites-patch\* C:\git\IPSDatedSites\ /E /Y
    pip install -r requirements.txt
    python py/main.py

## What is in the patch

| Path | Status |
|---|---|
| `queries.yaml` | new — source of truth for the query layer |
| `py/build_sparql.py` | new — queries.yaml → sparql.html + .rq + qmd/ |
| `py/make_webjs.py` | new — the browser emitter and its parity gate |
| `py/templates/ips_rdf_body.js` | new |
| `py/templates/sparql.html.j2` | new |
| `py/templates/sparql.qmd.j2` | new |
| `py/main.py` | **replaced** — gains steps 6 and 7 |
| `requirements.txt` | **replaced** — adds `pyyaml`, `jinja2`, pinned |
| `docs/_layouts/default.html` | **replaced** — one nav link added |
| `.github/workflows/build.yml` | **replaced** — see "CI" below |
| `webjs/*` | new — generated, shipped so the first pull is complete |

Nothing in `py/ips_rdf_export.py`, `py/verify.py`, `py/make_bundle.py` or
`sql/` is touched. The new modules are English and CRLF, matching the rest
of the repository.

## Verified on this state

    6 · Browser emitter (webjs/)
      Parity            : OK, 3492 N-Triples, sha256 f5df7ba2e38fc124
    7 · Query page (queries.yaml)
      OK dated-findspots       42 rows      OK findspots-per-site      5 rows
      OK crm-only              42 rows      OK external-identifiers   33 rows
      OK era-and-scale          6 rows      OK provenance              1 rows
      OK two-quality-axes      15 rows

The parity gate builds the graph twice — once with `ips_rdf_export.py`, once
with the generated JavaScript — from the same CSV, sorts the N-Triples and
compares SHA-256. `ips_rdf_export.py` changed substantially in this pull;
the gate confirms the JavaScript still reproduces it exactly.

`docs/sparql.html` and the `.rq` files were checked to be byte-stable across
rebuilds, which the CI drift check requires.

## What the run produces

    webjs/ips_rdf.js               copy to the ColdFusion server
    webjs/ips_rdf_button.js        copy to the ColdFusion server
    docs/sparql.html               the browser query page
    docs/bundle.ttl                the graph the page fetches
    docs/downloads/queries/*.rq    the same queries as plain files
    qmd/ips-dated-sites-sparql-live.qmd

Node is needed for the parity check only. Without it, step 6 still writes
`webjs/` and says the check was skipped rather than failing.

## Viewing the page locally

    cd docs && python -m http.server

The browser will not fetch Turtle from a `file://` path. Served this way
there is no Jekyll, so the YAML front matter shows as text and the site
navigation is missing; both are correct once pushed to Pages.

## CI

`docs/bundle.ttl` is excluded from the documentation drift check. It is a
copy of the published graph and carries `prov:endedAtTime` and
`dcterms:created`, so it differs after every export whether or not anything
changed — the same is already true of `rdf/`, which that check never
covered. Its content is verified semantically by the "Validate the RDF"
step, which is the meaningful check for a graph. `docs/sparql.html` and the
`.rq` files carry no timestamp and stay in scope.

## The ColdFusion side

See `webjs/CFM_PATCH.md`. Copy the two `.js` files next to
`IPSDatedSites27.cfm`, then make three edits to the CFM page. The first is
blocking: the `<cfloop>` that builds `rows` copies only 22 of the 40 columns
and drops `the_id` and the model parameters, which the emitter needs.

## Now unblocked by the new CSV

`data-1787218454884.csv` is v27c: `q_start` matches `exp(-sigma/t0)` on 40 of
42 rows (the two exceptions are rows where `|avg_datemin|` happens to equal
`t0`, so both formulas agree), and `p_t0 = 20.000` is present.

`ips_rdf_export.py` does not read it yet, so three things are now possible
that were not before — all in files this patch deliberately leaves alone:

- Carry `p_t0` on the model node. The name is a modelling decision:
  `lado:referenceLength` reads better than `lado:t0`, but `t0` is what the
  SQL calls it.
- `rdfs:comment` on `lado:qStart` and `lado:qEnd` still describes the
  era-boundary distortion that v27c removed. It is now wrong.
- `q_start_legacy` / `q_end_legacy` and `unc_*_exact` are in the CSV and
  unused. The legacy pair is what reproduces older figures; the exact pair
  is what makes `q_start` recomputable from the export.

Once `p_t0` is on the model node, a query about it belongs in
`queries.yaml` — worth writing then, not before.

## Also still open

The edge from a dating to the activity that produced it exists only in PROV.
A consumer reading pure CIDOC CRM sees the place, the findspot and the
time-span, but not what generated them. `crm:P94i_was_created_by` would be
the counterpart to `prov:wasGeneratedBy`.
