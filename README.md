# IPS Dated Sites

Local prototype for the RDF export of findspot datings (Samian Research /
IPS). The input is the CSV produced by `sql/IPSDatedSites.sql`, one row per
findspot. The CFM script will eventually only fetch the data from the
database; the modelling moves to JavaScript in the browser. This Python
version is the reference implementation the JavaScript port has to be
measured against.

> **What was modelled how, and why, is in [`docs/`](docs/index.md).** The
> crosswalk to CIDOC CRM, OWL-Time, GeoSPARQL and PROV-O lives there too,
> along with the formulas from the SQL and the open questions. This README
> covers operation and the decisions taken — every statement should have
> exactly one home.

## Layout

```
IPSDatedSites/
├── data/                    input: CSV from sql/IPSDatedSites.sql
│   └── derived/   generated verification.json, written by step 0
├── sql/                     the source query, for provenance
├── py/                      all of the code
├── queries/                 the SPARQL queries as .rq for an endpoint
├── .github/workflows/       CI: pipeline, drift check, validation
├── docs/          generated documentation of the model (British English)
│   ├── _config.yml          Jekyll, so that GitHub Pages renders the diagrams
│   ├── _layouts/            layout with mermaid.js
│   ├── diagrams/  generated the five .mmd files
│   └── docu/                hand-built companion pages for the CFM application
├── rdf/           generated Turtle, JSON-LD, LADO extension, bundle
├── img/           generated both figures, SVG + JPG at 300 dpi each
│   └── diagrams/  CI only   the rendered Mermaid diagrams
├── .gitignore
├── CITATION.cff
├── LICENSE
├── LICENSE-DATA
├── README.md
└── requirements.txt
```

| File in `py/` | Purpose |
|---|---|
| `main.py` | the single entry point, seven steps |
| `verify.py` | step 0: checks the CSV against the model it claims to carry |
| `ips_rdf_export.py` | CSV → RDF, builds the graph with rdflib |
| `ips_sparql.py` | queries, graph access, round-trip check |
| `ips_render.py` | the two figures |
| `ips_docs_text.py` | English text source for the ontology **and** the docs |
| `make_bundle.py` | builds the standalone bundle for a triplestore |
| `make_diagrams.py` | generates the Mermaid diagrams from code and graph |
| `make_docs.py` | generates `docs/*.md` from the code |
| `ips_compat.py` | suppresses one rdflib warning, see below |

All paths resolve against the repository root through
`Path(__file__).resolve().parent.parent`. Run from there, not from `py/`.

## Setup and running

```powershell
pip install -r requirements.txt
python py/main.py
```

Leave the terminal on PowerShell; the scripts write UTF-8 regardless of the
code page, because rdflib handles the serialisation. The CSV is picked up
from `data/` automatically — exactly one CSV must be there, or the run stops
and names the candidates.

```powershell
python py/main.py --era astronomical      # the other era convention
python py/main.py --findspot-uri slug     # readable instead of hashed URIs
python py/main.py --emit-geometry         # emit the IPS coordinates as well
python py/main.py --csv data\other.csv    # a different input file
python py/main.py --skip-verify           # without step 0
python py/main.py --verify-strict         # step 0 fails on warnings too
python py/main.py --skip-plots            # without the figures
python py/main.py --skip-bundle           # without the standalone bundle
python py/main.py --skip-docs             # without the documentation
```

The target folders can be redirected with `--rdf-out`, `--img-out` and
`--docs-out`, the name of the figure node with `--figure-name`. Full list:
`python py/main.py --help`.

Seven steps run through:

0. verify the CSV against the model, report to `data/derived/`
1. CSV → RDF into `rdf/`
2. load the graph, read everything back by SPARQL
3. both figures into `img/`
4. round-trip check CSV → RDF → SPARQL, field by field
5. standalone bundle to `rdf/IPSDatedSites-bundle.ttl`
6. documentation into `docs/`

Current state: 41 rows, 2691 triples, round trip over 17 fields with a
largest deviation of `0.00e+00`.

## Step 0 verifies rather than recomputes

The query is authoritative. `verify.py` recomputes nothing: it recovers each
published value from the other columns of the **same row** and asserts
agreement. Thirteen checks, carrying the letters used in the header of
`sql/IPSDatedSites.sql` so that the two can be read side by side:

```
c   k_eff  from n_stamps_die and the k parameters
d   interval width equals 2 · k_eff · sigma_eff
h   q_start / q_end from unc_*_years_exact and t0
i   q decreases monotonically in sigma
l   epoch drift sits in the box width          [reported, never fails]
```

plus the parameter columns being constant, the NULL policy, the integer
casts, and the absence of the fabricated 0.5 fallback removed earlier.

Check `i` is the one worth understanding. Until the reference length `t0`
was introduced, `q_start` and `q_end` divided by the mean calendar year,
which made the measure depend on the distance from the era boundary rather
than on the scatter. Feeding those old values back through `verify.py`
produces 21 inversions — findspots with larger scatter scoring better. That
is what a quality measure looks like when it is measuring the wrong thing,
and the check exists so that it cannot happen again unnoticed.

The module is deliberately dependency-free, standard library only. Something
that verifies the pipeline should not share a numerics stack with the code
whose numbers it is checking.

Its JSON report carries a `facts` block holding every figure the
documentation quotes. No timestamp is written unless `--stamp` is passed, so
that repeated runs stay byte-identical.

## The standalone bundle

`rdf/IPSDatedSites-bundle.ttl` holds the data, the complete vocabulary and a
**materialised** CIDOC CRM crosswalk in one file — meant for a triplestore,
the NFDI4Objects KG in particular.

Materialised, because triplestores generally do not reason over
`rdfs:subClassOf`. With the axioms alone,

```sparql
SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE { ?x a crm:E53_Place }
```

returns exactly `0`, although by the axioms every findspot is a place. The
builder therefore writes out the transitive closure over `rdfs:subClassOf`
as `rdf:type` triples. The axioms stay alongside, so a reasoning store
derives nothing new and nothing conflicts.

Counter-check after every run, plain CRM/OWL-Time queries without a reasoner:

```
crm:E53_Place          73     (41 findspots + 32 discovery sites)
crm:E52_Time-Span     123
crm:E36_Visual_Item    42
time:ProperInterval    41
CRM-only path          41     place -> time-span -> numeric year
```

Details in [`docs/bundle.md`](docs/bundle.md).

## The round trip is the real test

`ips_rdf_export.py` builds the graph. Everything after it reads back
**exclusively by SPARQL** — margins, row height, colour ramp and sort rule
are in the graph, not in the renderers. If something the figure needs is
missing from the export, the retrieval fails rather than quietly
substituting a constant.

That **two** different correct figures come out of **one** graph is the
evidence that the information really is in the graph and not in a drawing
routine.

## Two renderings

**v1 classic** is the existing D3 figure, one to one — box, whiskers with
caps, extreme-value stubs, dashed box edges, gradient legend underneath.
Left untouched so that the web output and the print version stay consistent.

**v2 modern** shows **exactly the same channels**, only set more carefully.
The whiskers in particular keep their colour from `q_start` / `q_end`: those
appear nowhere else in the picture, and a red whisker at the early Arretine
findspots is a statement meant to be seen rather than assembled from
numbers.

What is modernised is the presentation: banded rows instead of a grid, a
BC/AD axis, restrained rules, a colour bar on the right, more air between
the rows, a white halo under the whiskers so that the colour stays clear
over the banding.

To the right of the time axis sits a **value table** with eight columns:
`interval`, `n`, `sigma`, `unc start`, `q start`, `q int`, `unc end`,
`q end`. It covers what the web application shows in its hover popup, plus
the numbers that sit on the whiskers there. Two reasons: on the whisker they
collided with the whisker itself once the bars grew long — and a popup only
works in a browser, so in print the information would simply be gone. The
`sigma` column was not in the web output; it is added because
`width = 2·k·σ` holds and without it one sees *how* wide the box is but not
*why*. To drop it, delete one line in `TABLE_COLUMNS`.

An earlier v2 gave up the whisker colour in favour of a capsule shape. That
was a mistake: it looked tidier and carried less. The rule is worth writing
down — **modernise the presentation, not what is encoded.**

## The three decisions

**Era convention: `historical`.** `-40` in the database means 40 BC. Since
`xsd:gYear` counts astronomically, the label is shifted by +1. Check against
Amiens: `eff_start = -16.6` → rounded 17 BC → `time:inXSDgYear "-0016"`.
Only the **calendar label** is converted; `time:numericPosition` stays the
source value. Reasoning in
[`docs/open-questions.md`](docs/open-questions.md).

**Findspot URI: hash.** `samian:fs_<site-id>_<hash>` with
`sha256(NFC(trim(findspot)))[0:6]`. Amiens / *Sq. Bocquet pit 1973* becomes
`samian:fs_1003978_969c47`. The recipe is in the graph as
`lado:identifierScheme`, because the JavaScript port has to reproduce it
character for character. `--findspot-uri slug` switches to readable
fragments — but the decision should be taken once, since a later change
creates a second set of URIs for the same findspots.

**Base URI: not versioned.** Findspot and time-span URIs stay stable and
denote the *current* dating. What is citable instead is the dated dataset
(`samian:dataset_sites_dating_v1_<date>`), to which every time-span is
attached by `prov:wasDerivedFrom`.

## Documentation that cannot drift

`docs/` is regenerated on every run, in British English. The point is not
convenience but that hand-written structural documentation diverges at the
first new property.

`make_docs.py` reads the **structure** out of the code at runtime: classes,
properties with domain and range, namespaces, figure constants and the
SPARQL queries come from `ips_rdf_export.py`, `ips_render.py` and
`ips_sparql.py` themselves. The **prose** lives in `ips_docs_text.py` — and
that same file feeds the English `rdfs:comment` of the ontology. A
definition therefore cannot be right in the documentation and stale in the
RDF; it is the same string.

The same holds for the **five Mermaid diagrams** under `docs/diagrams/`:
architecture, class hierarchy, relations by layer, a real instance and the
materialisation in the bundle. None of them is drawn — the hierarchy comes
from `CLASSES`, the relations from `RELATIONS` and `LAYERS`, the instance by
SPARQL from the graph just produced, the materialisation from the same
closure function the bundle uses.

Every diagram is written twice from **one** string: as a `.mmd` file and as
a ` ```mermaid ` block in the `.md`. github.com renders the block directly;
GitHub Pages needs `mermaid.js` in the layout, and until then the `.mmd` is
the way out.

This improved the export code as a side effect: `crm:P89_falls_within` and
`crm:P4_has_time-span` previously sat inline in `build_graph` only. They are
now declared in `RELATIONS`, and `build_graph` uses the same constants —
otherwise the diagram would have been a transcription that goes wrong at the
first restructuring.

The generator **stops** if a class or property in the code has no entry:

```
Undocumented terms — add them to py/ips_docs_text.py:
  property testProperty
```

Tested: new property without documentation → exit code 1; documentation
added → exit code 0, and the text then appears in `docs/vocabulary.md`
**and** as `rdfs:comment@en` in `rdf/lado_dating_extension.ttl`.

| Page | Contents |
|---|---|
| [`index.md`](docs/index.md) | overview and starting point |
| [`model.md`](docs/model.md) | the three layers, URI strategy, the NULL contract |
| [`vocabulary.md`](docs/vocabulary.md) | all classes and properties, generated |
| [`crosswalk.md`](docs/crosswalk.md) | CIDOC CRM, OWL-Time, GeoSPARQL, PROV-O, DCAT, SKOS |
| [`statistics.md`](docs/statistics.md) | the formulas from the SQL |
| [`queries.md`](docs/queries.md) | the SPARQL queries and the round trip |
| [`open-questions.md`](docs/open-questions.md) | what remains open |

`docs/docu/` is different in kind: four hand-built pages that accompany the
CFM application — method and formulae, an at-a-glance summary, a walkthrough
of the query, and a data-and-figures page covering the REST endpoints and the
generated plots. They are **not** generated, and nothing in `py/` writes to
that directory, so they have to be corrected by hand when the model moves.
They were brought level with revision 30a on 27 August 2026.

The figures on the data-and-figures page are embedded by raw URL from `img/`
in this repository rather than copied, so a rebuild that changes a figure
changes what the page shows. `raw.githubusercontent.com` serves `.svg` as
`image/svg+xml`, which is what makes that work in a plain `<img>` tag.

## GitHub Pages and the diagrams

github.com renders ` ```mermaid ` blocks natively, **GitHub Pages does
not** — Jekyll runs there, and the block arrives as a code element. Hence a
`_config.yml` and a `_layouts/default.html` with `mermaid.js` under `docs/`;
the layout converts the code elements into diagrams on load.

The Markdown source stays identical for both targets — one source, two
renderers. `_config.yml` sets the layout through `defaults` for all pages,
so that `make_docs.py` needs to know nothing about Jekyll.

## The GitHub Action

`.github/workflows/build.yml` enforces, on every push, the undertaking the
repository rests on: **the generated files must not lag behind the code.**
Without the check the sync mechanism is only a convention, and an unchecked
convention is eventually forgotten.

Five steps:

1. record the environment — Python and library versions
2. run the pipeline — the round trip is inside it and exits with an error
   code on any deviation
3. `git diff` on `docs/`, separately on `img/`
4. check the RDF semantically: does everything parse, and does the bundle
   answer CIDOC CRM queries without a reasoner?
5. render the diagrams: `.mmd` → SVG and JPG into `img/diagrams/`, committed
   by the bot

The two diff checks are **separate** because their causes are. `docs/` is
plain text from the code structures and identical on every platform — a
difference there means somebody changed code and did not regenerate. `img/`
comes from matplotlib, which writes its own version into the SVG metadata
and derives the `clip-path` identifiers per version. A difference there is
usually a version conflict rather than a substantive one.

`rdf/` is **exempt** from the byte check, deliberately: the files carry
`dcterms:created` and `prov:endedAtTime`, which are meant to change from run
to run. Measured: `docs/`, `docs/diagrams/` and `img/` are byte-identical
across consecutive runs, so the check is meaningful there.

Tested: code changed without regenerating → the action fires; undocumented
property → the pipeline ends with exit code 1.

## Rendered diagrams

Under each diagram in `docs/` are three links: **JPG**, **SVG** and the
**Mermaid source**. They point absolutely at github.com, not relatively — a
relative link to `diagrams/*.mmd` works in the repository but not on GitHub
Pages, because `docs/_config.yml` does not publish the `.mmd` there.

Rendering happens in the action, not in `py/main.py`: `mmdc` needs Node and
a headless browser, and the Windows working environment has neither. The
pipeline therefore stays pure Python and CI supplies the images afterwards —
SVG plus JPG at scale 4, roughly 300 dpi. The same convention as for the two
main figures.

**It follows that `img/diagrams/` only exists locally after a `git pull`.**
However often `python py/main.py` runs, the folder is not created by it — it
is produced by the action and checked in by a bot commit. Until the first
run completes, the JPG and SVG links under the diagrams lead nowhere; the
Mermaid source and the embedded block are unaffected.

The bot commit carries `[skip ci]`, and a commit made with `GITHUB_TOKEN`
does not trigger another workflow run anyway — a loop is therefore
impossible. `img/diagrams/` is exempt from the byte check on `img/` because
the files appear later in the same run and do not come from the Python
pipeline.

## Why the versions are pinned exactly

`requirements.txt` names exact versions rather than ranges. The reason is
concrete: on the first CI run the drift check failed because matplotlib
3.9.2 was installed locally and 3.10.9 on the runner. The diff read

```
- <dc:title>Matplotlib v3.9.2 …
+ <dc:title>Matplotlib v3.10.9 …
- clip-path="url(#p3b6c313feb)"
+ clip-path="url(#p8bcc3c5794)"
```

The version is in the SVG metadata, and `svg.hashsalt` makes the
`clip-path` identifiers deterministic only *within* one version. The check
was correct — it reported a real difference, just not a substantive one.

Whoever raises a version runs `python py/main.py` once afterwards and
commits the regenerated files with it.

Fonts, incidentally, are not a concern: the renderer sets no `font.family`,
so matplotlib's own DejaVu Sans applies, shipped with the package. Windows
and Linux produce the same text paths.

## rdflib and pre-Christian years

rdflib 7.1.x maps `xsd:gYear` onto Python's `datetime.date`, which cannot
represent years before 1 (`datetime.MINYEAR == 1`). Every BC year therefore
writes a warning and a traceback both when the literal is created *and* when
it is parsed. With the current data that affects eight literals.

The literal itself is correct — checked against exactly this version:

```
Literal("-0016", datatype=XSD.gYear).n3()
→ "-0016"^^<http://www.w3.org/2001/XMLSchema#gYear>
```

Only `.value` stays `None`. Of no consequence, because no query computes on
`gYear`. From rdflib 7.5 the converter is gone and the noise stops by
itself.

`py/ips_compat.py` suppresses **exactly that one message** and nothing else
— silencing `rdflib.term` wholesale would be wrong, since messages worth
seeing arrive on the same logger. `main.py` reports the number of affected
literals instead, so that they stay visible rather than merely silenced.

## Byte-stable SVGs

`SOURCE_DATE_EPOCH` and a fixed `svg.hashsalt` ensure that a rebuild without
a content change produces identical files. Otherwise matplotlib would write
a fresh timestamp and freshly randomised element identifiers on every run,
and both figures would sit permanently modified in `git status` — a file
whose diff is always red is a file whose diff nobody reads.

## Licence and citation

Two licences, on purpose:

| | Licence | File |
|---|---|---|
| Code | MIT | `LICENSE` |
| Data — `data/`, `rdf/`, `docs/bundle.ttl`, `img/` | CC BY 4.0 | `LICENSE-DATA` |

A permissive code licence says nothing about who may reuse the
archaeological record the code processes, and a reader of the graph should
not have to infer the terms of the one from the terms of the other. The
data licence is also machine-readable, on the dataset node itself:
`dcterms:license`, `dcterms:creator`, `dcterms:publisher` and
`dcat:contactPoint`, so an aggregator can read the terms off the graph.

Attribution goes to the **Samian Research Community**; the point of contact
is **Dr. Allard W. Mees** (LEIZA). Citation metadata is in `CITATION.cff`,
which GitHub and Zenodo read directly.

Cite the dated snapshot, not an individual findspot: findspot and time-span
URIs are deliberately not versioned, and their values change when the source
data are improved.

Still open: the release date and the Zenodo DOI, both marked `TODO` in
`CITATION.cff`, and the publisher and URL of the source database.

The house template of the `wdt-*` repositories lists Fiona Schenk as subject
author by default. That is deliberately **not** carried over here: she
belongs to the WD1 speleothem paper, not to Samian Research.

`.gitignore` ignores `__pycache__`, virtual environments and editor
artefacts. `data/`, `rdf/`, `img/` and `docs/` stay **deliberately
versioned** — they are the result and have to be diffable. That is exactly
why the SVGs are byte-stable.
