# IPSDatedSites.cfm — what the page needs for the RDF export

Checked against `IPSDatedSites31.cfm` on 2026-08-28. **All three edits this
file used to ask for are already in the page.** What remains is one link and
the two generated files.

The .cfm itself is not in this repository, and deliberately so: it carries
the full PostgreSQL statement. See `sql/README.md`.

## State of version 31

| What | Where | Status |
|---|---|---|
| `<script src="ips_rdf.js">` and `ips_rdf_button.js` | lines 337–338 | present |
| `<button id="downloadTtl">` | line 372 | present |
| The `rows` loop wide enough for the emitter | 36 fields | present — the emitter reads 30, all 30 are there |
| Link to the published query page | line 373 | points at `sparql.html`, which now only redirects |

The one outstanding change:

```html
<a href="https://leiza-rse.github.io/IPSDatedSites/query/"
   target="_blank" rel="noopener">Query the published graph &rarr;</a>
```

Not urgent. `sparql.html` is a redirect stub written by
`py/build_sparql.py` precisely so that this link, which lives in software
this repository does not control, keeps working after the query pages moved
into `docs/query/`.

## The field contract

The emitter reads these thirty columns off the global `data` array, as
ColdFusion serialised it — **not** the normalised copy the plot builds
inside `DOMContentLoaded`, because the export must not depend on whether D3
has run:

    the_id  count_stamps  n_stamps_die  n_dies  die_repetition
    q_repetition  q_interval  q_start  q_end  sigma_eff  k_eff
    k_no_dierecord  midpoint_year  avg_datemin  avg_datemax
    min_datemin  max_datemin  min_datemax  max_datemax  avg_interval
    unc_start_years  unc_end_years  unc_interval_years
    eff_start  eff_end  p_k_min  p_k_max  p_tau  p_w  p_t0

Field names are read case-insensitively, so ColdFusion's upper-casing and
the CSV's lower-case names both work. That is not an assumption: the
emitter has been run against upper-cased rows and produced the same 3439
triples as against the CSV.

Note `k_no_dierecord`. Earlier versions of this file called it
`k_is_fallback`; the column was renamed with revision 30a, when it stopped
having any effect on the interval and became a note about a gap in the
records rather than a state of the model.

Keep the loop body explicit rather than using `qFiltered.columnList`, so
that the field set stays a visible contract and a change to the query shows
up in a diff instead of slipping through.

## Deploying a new emitter

Two files, copied next to the .cfm, no build step and no network access at
run time:

    ips_rdf.js
    ips_rdf_button.js

They are generated. Edit `py/templates/ips_rdf_body.js` or
`py/make_webjs.py` and run:

    python py/make_webjs.py --verify

`--verify` builds the graph twice from the same CSV — once in Python, once
by running the JavaScript under node — sorts both to N-Triples and compares
SHA-256. A structural change made on one side only fails there rather than
in somebody's browser.

For Allard there is a separate sheet in German with the deployment steps and
how to check they took effect.

## What the download is, and what it is not

Vocabulary, data and the materialised CIDOC CRM crosswalk — the same shape
as `rdf/IPSDatedSites-bundle.ttl`, so the file can be dropped straight into
the query page and the examples answer over it.

It is a **live** snapshot from the database and will differ from the
published bundle whenever the source data have moved on; `dcterms:issued`
and `owl:versionInfo` on the dataset node say when it was taken.

It carries **less** than the published graph: no geometry, no colour axes,
no interval relations. `COPY_ME.txt` gives the reason for each. The parity
check compares against a Python graph built with those switched off, so it
measures agreement where the two emitters overlap; everything they both emit
is identical.
