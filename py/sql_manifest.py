"""
IPS Dated Sites — the SQL fingerprint
=====================================

The PostgreSQL statements are not in this repository. sql/*.sql is
gitignored and lives only on the machines that maintain it; what is
tracked here instead is sql/MANIFEST.json, which records for each file its
size, its SHA-256 and the revision it was at.

WHY THE STATEMENTS ARE NOT PUBLISHED
------------------------------------
The full query names the tables, columns and quality flags of a live
research database that also answers a public web application. Publishing
the schema does not hand anyone the keys, but it removes a step from
anybody looking for a way in, and it does so for no gain: nothing in this
repository needs it. The pipeline reads REST, not PostgreSQL.

WHAT IS NOT LOST BY THAT
------------------------
The method stays reproducible. py/ips_model.py is a complete second
implementation of the dating algorithm, it runs from the public REST
endpoint, and every build checks it column by column against the
database's own aggregation of the same stamps. Somebody who wants to
verify the datings does not need the SQL; they need the model and the
data, and both are here.

WHAT THIS FILE IS FOR, AND WHAT IT IS NOT
-----------------------------------------
The manifest answers ONE question: is the statement on this machine the
same one the last person worked with. It is a file-identity check.

It is deliberately NOT the answer to "are the repository and the CFM
application in step". That question is already answered, and answered
better, by the cross-check in py/main.py: the recomputation is compared
against what the database itself returns, and a disagreement stops the
build. That compares BEHAVIOUR. A hash of the text would fire on a changed
comment and stay silent on a rewrite that happens to produce the same
numbers — it measures the wrong thing.

So: the cross-check tells you the two agree. The manifest tells you which
file you are holding. Neither replaces the other.

    python py/sql_manifest.py            check
    python py/sql_manifest.py --update   record the current files
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
MANIFEST = SQL_DIR / "MANIFEST.json"

# Statements the manifest covers. Named rather than globbed: a new .sql
# file appearing in the folder should be a decision, not a silent addition.
TRACKED = [
    "IPSDatedSites.sql",
    "v_ips_dated_stamps.sql",
    "wide_potters.sql",
]


def digest(path: Path) -> dict:
    """
    Size and SHA-256 of one statement.

    Line endings are normalised to LF before hashing. The same file checked
    out on Windows and on a Linux runner differs byte for byte otherwise,
    and a fingerprint that changes with the platform tells you nothing.
    """
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "revision": revision_of(raw.decode("utf-8", "replace")),
    }


def revision_of(text: str) -> str | None:
    """The highest revision number mentioned in the file's own comments."""
    found = [int(m) for m in re.findall(r"[Rr]evision\s+(\d+)", text)]
    return f"{max(found)}" if found else None


def read_manifest() -> dict:
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def write_manifest(data: dict) -> Path:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return MANIFEST


def check() -> tuple[str, list[str]]:
    """
    ('ok' | 'absent' | 'partial' | 'differs', lines to print).

    ABSENT IS NOT A FAILURE. A fresh clone and every CI run have no sql/
    at all, and that is the normal case now — the pipeline does not read
    PostgreSQL. Only a file that is PRESENT and does not match what the
    manifest records is worth saying something about.
    """
    manifest = read_manifest()
    files = manifest.get("files", {})
    if not files:
        return "absent", ["  SQL manifest      : none recorded"]

    present, missing, differs = [], [], []
    for name, recorded in sorted(files.items()):
        path = SQL_DIR / name
        if not path.exists():
            missing.append(name)
            continue
        actual = digest(path)
        if actual["sha256"] == recorded.get("sha256"):
            present.append(name)
        else:
            differs.append((name, recorded, actual))

    rev = manifest.get("revision")
    head = f"  SQL statements    : revision {rev}" if rev else \
           "  SQL statements    :"

    if not present and not differs:
        return "absent", [
            head + " — not on this machine (gitignored, as intended)",
            "                      The build does not need them; the "
            "cross-check against",
            "                      the database is what confirms the model "
            "is in step."]

    lines = [head + f" — {len(present)} of {len(files)} present and matching"]
    for name, recorded, actual in differs:
        lines.append(f"  !!  {name} differs from the manifest")
        lines.append(f"      recorded {recorded.get('sha256', '?')[:12]} "
                     f"({recorded.get('bytes', '?')} bytes), "
                     f"here {actual['sha256'][:12]} ({actual['bytes']} bytes)")
    if differs:
        lines.append("      If you changed the statement on purpose, run "
                     "python py/sql_manifest.py --update")
        lines.append("      and commit the manifest, so the next person "
                     "knows which version this is.")
    if missing and present:
        lines.append(f"      not on this machine: {', '.join(missing)}")
    return ("differs" if differs else
            "partial" if missing else "ok"), lines


def update() -> tuple[dict, list[str]]:
    files, lines = {}, []
    revisions = []
    for name in TRACKED:
        path = SQL_DIR / name
        if not path.exists():
            lines.append(f"  --  {name} not here, left out of the manifest")
            continue
        entry = digest(path)
        files[name] = entry
        if entry["revision"]:
            revisions.append(int(entry["revision"]))
        lines.append(f"  ok  {name}  {entry['sha256'][:12]}  "
                     f"{entry['bytes']} bytes"
                     + (f"  rev {entry['revision']}" if entry["revision"]
                        else ""))
    data = {
        "note": ("Fingerprints only. The statements themselves are not in "
                 "this repository — see py/sql_manifest.py for why, and "
                 "sql/README.md for where they are."),
        "recorded": date.today().isoformat(),
        "revision": str(max(revisions)) if revisions else None,
        "hashing": "sha256 of the file with CRLF normalised to LF",
        "files": files,
    }
    return data, lines


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check or record the fingerprints of sql/*.sql")
    ap.add_argument("--update", action="store_true",
                    help="record the statements now on this machine")
    args = ap.parse_args()

    if args.update:
        data, lines = update()
        for line in lines:
            print(line)
        if not data["files"]:
            print("  !!  no statements found in sql/ — nothing recorded.")
            return 1
        print(f"  {write_manifest(data).relative_to(ROOT)}  "
              f"(revision {data['revision']})")
        return 0

    state, lines = check()
    for line in lines:
        print(line)
    return 2 if state == "differs" else 0


if __name__ == "__main__":
    sys.exit(main())
