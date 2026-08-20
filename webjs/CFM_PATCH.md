# IPSDatedSites27.cfm — the three edits

## 1. Widen `rows` (blocking)

The `SELECT` returns 40 columns; the `<cfloop>` at line 174 copies 22 of them
into `rows`. The emitter only sees what is in `rows`, so as it stands the
browser would produce a thinner graph than `make_bundle.py` and the parity
gate would fail. Missing and needed: `the_id`, `sigma_eff`, `k_eff`,
`k_is_fallback`, `n_stamps_die`, `n_dies`, `die_repetition`, `q_repetition`,
`avg_interval`, `p_k_min`, `p_k_max`, `p_tau`, `p_w`.

Replace the loop body:

```cfml
<cfset rows = []>
<cfloop query="qFiltered">
    <cfset arrayAppend(rows, {
        the_id = qFiltered.the_id,
        the_site = qFiltered.the_site,
        the_findspot = qFiltered.the_findspot,
        latinsitename = qFiltered.latinsitename,
        long = qFiltered.long,
        lat = qFiltered.lat,
        pleiades = qFiltered.pleiades,
        count_stamps = qFiltered.count_stamps,
        avg_datemin = qFiltered.avg_datemin,
        avg_datemax = qFiltered.avg_datemax,
        min_datemin = qFiltered.min_datemin,
        max_datemin = qFiltered.max_datemin,
        min_datemax = qFiltered.min_datemax,
        max_datemax = qFiltered.max_datemax,
        avg_interval = qFiltered.avg_interval,
        q_start = qFiltered.q_start,
        q_end = qFiltered.q_end,
        q_interval = qFiltered.q_interval,
        n_dies = qFiltered.n_dies,
        die_repetition = qFiltered.die_repetition,
        q_repetition = qFiltered.q_repetition,
        n_stamps_die = qFiltered.n_stamps_die,
        unc_start_years = qFiltered.unc_start_years,
        unc_end_years = qFiltered.unc_end_years,
        unc_interval_years = qFiltered.unc_interval_years,
        midpoint_year = qFiltered.midpoint_year,
        sigma_eff = qFiltered.sigma_eff,
        k_eff = qFiltered.k_eff,
        k_is_fallback = qFiltered.k_is_fallback,
        p_k_min = qFiltered.p_k_min,
        p_k_max = qFiltered.p_k_max,
        p_tau = qFiltered.p_tau,
        p_w = qFiltered.p_w,
        eff_start = qFiltered.eff_start,
        eff_end = qFiltered.eff_end
    })>
</cfloop>
```

Explicit rather than `qFiltered.columnList`, so the field set is a visible
contract and a SQL change shows up in the diff instead of slipping through.

## 2. Load the emitter (in `<head>`, before the D3 script)

```html
<script src="ips_rdf.js"></script>
<script src="ips_rdf_button.js" defer></script>
```

## 3. Button and link (next to `<button id="downloadSvg">`, line 241)

```html
<button id="downloadSvg">Download SVG</button>
<button id="downloadTtl">Download triples (.ttl)</button>
<a href="https://leiza-rse.github.io/IPSDatedSites/sparql.html"
   target="_blank" rel="noopener">Query the published graph &rarr;</a>
```

## Why the emitter reads the raw rows

`ips_rdf_button.js` uses the global `data` as ColdFusion serialised it, not
the normalised copy the plot builds inside `DOMContentLoaded`. The export
must not depend on whether D3 has run, and the parity gate exercises exactly
this path. Field names are read case-insensitively, so CF's upper-casing and
the CSV's lower-case column names both work.

## What the download is

Vocabulary + data + the materialised CIDOC-CRM crosswalk — the same shape as
`rdf/IPSDatedSites-bundle.ttl`, so the file can be dropped straight into the
SPARQL page and the example queries answer over it. It is a *live* snapshot
from the database and will differ from the published bundle whenever the
source data have moved on; `dcterms:issued` and `owl:versionInfo` on the
dataset node say when it was taken.
