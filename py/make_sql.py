"""
IPS Dated Sites — the goldstandard SQL, rendered for its two consumers
=====================================================================

    python py/make_sql.py

`sql/IPSDatedSites.sql` is the single authoritative statement of the dating
model. It is tracked in git, it is what gets cited, and it is what the two
reimplementations — the ColdFusion template and `py/ips_model.py` — are
measured against.

This script renders it into the two forms those consumers actually need:

    sql/generated/IPSDatedSites.cfm      paste into <cfquery name="qDating">
    sql/generated/IPSDatedSites.psql     runnable in psql / DBeaver

Both are DERIVED, never edited, and therefore gitignored. Editing a
generated file is the failure mode this arrangement exists to prevent: two
divergent copies of the model with no way to tell which one produced a
given export.

WHY THE GOLDSTANDARD ITSELF IS TRACKED
--------------------------------------
The suggestion was to keep the SQL out of version control. That is the
wrong way round. A goldstandard that is not versioned cannot be diffed,
cannot be cited from the paper, and cannot answer the question this project
keeps having to answer — *which* version of the query produced *this* CSV.
What belongs in .gitignore is the derived output, which is exactly what
this script writes.

THE ONLY DIFFERENCE BETWEEN THE THREE FORMS
-------------------------------------------
One token. The canonical file carries `:min_stamps`, the minimum number of
stamps per findspot — an editorial display threshold, not a data filter.

    canonical    HAVING COUNT(di.number) >= :min_stamps
    ColdFusion   HAVING COUNT(di.number) >= <cfqueryparam value="#MIN_STAMPS#" ...>
    psql         HAVING COUNT(di.number) >= 1

Nothing else is substituted, and the script verifies that: if the rendered
statement differs from the canonical one anywhere other than at that
placeholder, it refuses to write.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "sql" / "IPSDatedSites.sql"
OUT_DIR = ROOT / "sql" / "generated"

PLACEHOLDER = ":min_stamps"

CFM_PARAM = ('<cfqueryparam value="#MIN_STAMPS#" '
             'cfsqltype="cf_sql_integer">')

CFM_HEADER = """<!--- =====================================================================
     GENERATED — DO NOT EDIT
     Source : sql/IPSDatedSites.sql   (the goldstandard, tracked in git)
     Build  : python py/make_sql.py
     Any change belongs in the source. Editing here creates a second,
     silently divergent copy of the dating model.

     Drop-in for IPSDatedSites*.cfm. Requires MIN_STAMPS to be set, e.g.
         <cfparam name="url.minStamps" default="1">
         <cfset MIN_STAMPS = max(1, val(url.minStamps))>
     ===================================================================== --->
<cfquery name="qDating" datasource="#DATASOURCE#">
"""

CFM_FOOTER = "</cfquery>\n"

PSQL_HEADER = """-- =====================================================================
-- GENERATED — DO NOT EDIT
-- Source : sql/IPSDatedSites.sql   (the goldstandard, tracked in git)
-- Build  : python py/make_sql.py
--
-- min_stamps is substituted with 1 (no threshold). To export:
--   \\encoding UTF8
--   \\copy (<paste the statement without the trailing semicolon>)
--        TO 'sites.csv' WITH (FORMAT csv, HEADER)
-- =====================================================================
"""


def extract_statement(text: str) -> str:
    """The executable part: from WITH params to the closing semicolon.

    Everything before is commentary, everything after is the verification
    checklist. Both are the reason the file is worth reading and neither
    belongs in a drop-in.
    """
    start = text.index("WITH params AS (")
    end = text.index("ORDER BY avg_datemin ASC;") + len("ORDER BY avg_datemin ASC;")
    return text[start:end]


def render(statement: str, substitution: str) -> str:
    if PLACEHOLDER not in statement:
        raise SystemExit(
            f"  !!  {PLACEHOLDER} not found in the canonical statement.\n"
            "      Without it neither consumer can set the display "
            "threshold, and the two would drift apart.")
    return statement.replace(PLACEHOLDER, substitution)


def check_placeholder(statement: str) -> None:
    """The placeholder must occur exactly once.

    A second occurrence would mean two thresholds could drift apart between
    the ColdFusion and psql renderings; zero would mean the consumers cannot
    set it at all and would each hard-code their own.
    """
    n = statement.count(PLACEHOLDER)
    if n != 1:
        raise SystemExit(
            f"  !!  {PLACEHOLDER} occurs {n} times in the canonical "
            "statement, expected exactly once.\n"
            "      Refusing to write — this is the divergence the generator "
            "exists to prevent.")


def check_round_trip(canonical: str, rendered: str, substitution: str,
                     label: str) -> None:
    """Rendered = canonical with the one placeholder swapped, nothing else.

    Compared on the two fragments either side of the placeholder rather than
    by substituting back: the psql substitution is "1", and replacing every
    "1" in a statement full of coordinates and year numbers would not tell
    us anything.
    """
    before, after = canonical.split(PLACEHOLDER)
    if rendered != before + substitution + after:
        raise SystemExit(
            f"  !!  {label}: the rendered statement differs from the "
            f"canonical one beyond {PLACEHOLDER}.\n"
            "      Refusing to write.")


def summarise(statement: str) -> None:
    """A few facts about what was rendered, so a silent wrong file shows."""
    # The main SELECT, not the one inside the params CTE, and its own FROM,
    # not the one in diecounts — which sits earlier in the text.
    # Located by pattern rather than by the table's name. The statement is
    # not in this repository any more (see sql/README.md); spelling its
    # schema out here would put back in the code what was taken out of the
    # data, and a pattern is no more fragile than a literal was.
    head = statement.index("SELECT\n    vds.id")
    m = re.compile(r"FROM\s+\w+\s+AS\s+di\b").search(statement, head)
    if not m:
        raise SystemExit("  !!  the main SELECT has no 'FROM ... AS di' — "
                         "the statement is not the one this expects.")
    select = statement[head:m.start()]
    columns = re.findall(r"\bAS\s+([a-z_0-9]+)\b", select)
    tau = re.search(r"([0-9.]+)::numeric AS tau", statement)
    t0 = re.search(r"([0-9.]+)::numeric AS t0", statement)
    # Aliased columns only: di.pleiades is selected bare and does not
    # appear here. 40 aliases + pleiades = the 41 columns of the export.
    print(f"  Aliased columns   : {len(columns)}")
    print(f"  tau / t0          : {tau.group(1) if tau else '?'} / "
          f"{t0.group(1) if t0 else '?'}")
    if tau and t0 and tau.group(1) == t0.group(1):
        print("  !!  tau and t0 carry the same value. They are unrelated "
              "quantities; equal values have been a source of error before. "
              "Check this is intended.")
    if "k_is_fallback" in statement:
        print("  !!  k_is_fallback is still present — expected "
              "k_no_dierecord since revision 30a.")


def main() -> int:
    if not CANONICAL.exists():
        raise SystemExit(f"  !!  {CANONICAL} not found.")

    text = CANONICAL.read_text(encoding="utf-8")
    statement = extract_statement(text)
    check_placeholder(statement)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        (OUT_DIR / "IPSDatedSites.cfm", CFM_PARAM, CFM_HEADER, CFM_FOOTER,
         "ColdFusion"),
        (OUT_DIR / "IPSDatedSites.psql", "1", PSQL_HEADER, "", "psql"),
    ]

    print(f"  Source            : {CANONICAL.relative_to(ROOT)}")
    summarise(statement)
    print()

    for path, substitution, header, footer, label in targets:
        rendered = render(statement, substitution)
        check_round_trip(statement, rendered, substitution, label)
        path.write_text(header + rendered + "\n" + footer, encoding="utf-8",
                        newline="\r\n")
        print(f"  {path.relative_to(ROOT)}")

    print()
    print("  Generated, therefore gitignored. Edit sql/IPSDatedSites.sql.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
