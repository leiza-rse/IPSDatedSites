# IPSDatedSites — update bundle 2

Step 1 of the rewrite, completed against the actual repository. Unpack over
the repository root; the paths match what is already there.

`py/verify.py` is **not** included — the copy already in the repository is
identical to the one delivered before. Nothing needs doing to it.

---

## 1. Files in this bundle

| Path | Status | Note |
|---|---|---|
| `py/main.py` | **replaces** the existing file | verification added as step 0, plus two fixes described below |
| `sql/IPSDatedSites.sql` | **new** | renamed from `sql/IPSDatedSites27c.sql` |
| `docs/docu/variance_quality_from_sql.html` | **new** | method and formulae |
| `docs/docu/variance_quality_summary.html` | **new** | at a glance |
| `docs/docu/variance_quality_sql.html` | **new** | SQL walkthrough |

**Delete afterwards:** `sql/IPSDatedSites27c.sql` — superseded by the rename.

Nothing else is touched. `requirements.txt` is unchanged; `verify.py` uses the
standard library only.

---

## 2. Then run the pipeline once and commit what changes

```
python py/main.py
```

The figures currently committed under `img/` were rendered from a **pre-27
export**: `plot_v2_modern.svg` still carries the old whisker qualities
`0.00`, `0.01`, `0.10` for Amiens, Basel and Oberaden. 160 value labels change
when the figure is rebuilt from the present CSV. Re-running fixes this; the
new files must be committed.

Expect these to change:

| Path | Why |
|---|---|
| `img/plot_v1_classic.*`, `img/plot_v2_modern.*` | the whisker colours and the printed q values |
| `rdf/*.ttl`, `rdf/*.jsonld` | `lado:qStart` / `lado:qEnd` values, plus the dated dataset node and `prov:endedAtTime` |
| `docs/index.md` | the generation date in the footer line |
| `data/derived/verification.json` | new, written by step 0 |

The date-bearing differences are by design, not drift: the dataset node is
dated for citation. Everything else must be attributable to the change of
formula, and nothing else was observed in a full test run.

---

## 3. What changed in `main.py`

**Step 0 — verification.** Between `find_csv` and the export. The query is
authoritative; nothing is recomputed here, each published value is recovered
from the other columns of the same row. On failure the run stops with exit
code 2 before anything is written, because every later step would otherwise
model something other than what it claims to.

New switches: `--skip-verify`, `--verify-strict`, `--verify-out`. The report
goes to `data/derived/verification.json` by default.

**`find_csv` no longer picks silently.** Two exports side by side used to
produce a printed note and a run against whichever sorted first. That is the
failure mode this project keeps removing elsewhere, so it is now an error
naming both files. `--csv` remains the override.

**Stale reference corrected.** The "no CSV found" message pointed at
`IPSDatedSites25_final.sql`, which no longer exists. It now points at
`sql/IPSDatedSites.sql`.

The header comment still says the same file name in `py/ips_rdf_export.py`
line 5. Left alone deliberately — it is a docstring in a module this bundle
does not otherwise touch, and mixing an unrelated edit into a replacement
file makes the diff harder to read than it is worth. Worth fixing in the same
commit as step 2.

---

## 4. The generated documentation is stale in the same places

`docs/statistics.md` is produced by `py/make_docs.py` from prose in
`py/ips_docs_text.py`. It describes the superseded formulation as current:

| Passage | Location | Issue |
|---|---|---|
| "Edge sharpness — presentation only" | `ips_docs_text.py` line 313 | gives `q_start = exp(−sd(datemin) / |mean(datemin)|)` and the Amiens example with `q_end ≈ 0.004`. Superseded by `exp(−σ / t₀)`, `t₀ = 20` |
| "A caution about the edge measures" | same file, prose block | describes a defect that no longer exists |
| "The unexplained filter" | same file | states the reason for excluding `datemax IN (260, 120, 150)` is undocumented. It is now documented: archaeologically intended (A. Mees) |

This is good news for the plan rather than bad: the pages are generated, so
the fix is a code change in one module, not a hand edit that the next run
would overwrite. It also means `docu.py` is needed only for the three HTML
pages under `docs/docu/` — the Markdown side already has its generator.

Scope for step 3 is therefore:

1. revise the three passages in `ips_docs_text.py`, and add `t₀` to the
   parameter listing;
2. write `docu.py` for the HTML pages, reading `facts` out of
   `data/derived/verification.json` and substituting between sentinels;
3. reconcile one contradiction: the method page states the model parameters
   belong on the time-span, while the RDF step places them on the dating
   activity. One of the two has to give.

---

## 5. The three HTML pages

Moved in unchanged apart from one substitution: the tab and footer links now
point at `IPSDatedSites27.cfm` instead of `IPSDatedSites25.cfm`, four
occurrences in total.

They carry no YAML front matter, so Jekyll copies them verbatim and the
`defaults` layout in `docs/_config.yml` does not apply — the hand-built design
survives publication untouched.

Their **content is stale** in the same way as `statistics.md`; see the
previous bundle's note or the section list below. Do not treat them as
current until step 3 is done.

| Page, section | Issue |
|---|---|
| Method §9 | old formula and the calendar-origin caveat; also still states the `COALESCE(..., 0.5)` fallback, removed in IPSDatedSites26 |
| Method §12 | whisker *length* is still legacy, whisker *colour* is not; the section conflates them |
| Method §13 | needs a second superseded formulation — where `q_start_legacy` belongs |
| Method §14 | three of the listed limitations are resolved |
| Method §15 | `t₀ = 20` missing |
| Method §16 | missing `unc_start_years_exact`, `unc_end_years_exact`, `q_start_legacy`, `q_end_legacy`, `p_t0` |
| Summary | whisker colour not explained at all, which now matters — the figure legend has two bars |
| SQL walkthrough §F | still speaks of two quality measures |

Wording to be used verbatim across all pages and the figure legend:

- box colour — *how tightly the potter dates agree*
- whisker colour — *how firmly the start / end date is fixed*
