"""
IPS Dated Sites — the Samian Research REST endpoints
====================================================

Since August 2026 the source data are published as REST resources rather
than reached only through a PostgreSQL connection. That changes what this
repository can claim: the datings are now reproducible by anyone, from
published inputs, without database access.

    https://www1.rgzm.de/rest/samianresearch/datedsites
        JSON. One record per dated stamp: findspot, potter, die, and the
        potter's date range. This is the INPUT of the model — the same rows
        that sql/v_ips_dated_stamps.sql delivers.

    https://www1.rgzm.de/rest/samianresearch/datedsitesstatistics
        Pipe-delimited CSV. One row per findspot, everything aggregated.
        This is the OUTPUT of the model, computed in the database. It is
        what py/ips_model.py is checked against.

    https://www1.rgzm.de/ips/lod/ips_stamps.csv
        Pipe-delimited CSV, the stamp list without the potter dates.
        Useful as a listing, NOT usable as model input — see below.

WHAT THE THIRD ENDPOINT CANNOT DO
---------------------------------
ips_stamps.csv carries the_site, the_findspot, pottername, die and
stamp_number, and no dates. The model needs datemin and datemax per stamp,
so it cannot be recomputed from that file alone. Use the JSON endpoint. The
CSV was tried first and produced an empty model in silence, which is why
this is written down here rather than discovered again.

THREE THINGS ABOUT THE PAYLOADS
-------------------------------
  * The JSON is ColdFusion's query serialisation: a COLUMNS list and a DATA
    list of positional rows, not a list of objects. Column names are upper
    case; the rest of this repository uses lower case.
  * The statistics CSV is pipe-delimited, not comma-delimited, and renders
    SQL NULL as an empty field — indistinguishable from an empty string.
    Numeric columns are therefore read as None when blank.
  * The statistics endpoint omits two columns the database query produces:
    the_id and q_repetition. the_id can be recovered from the JSON, which
    does carry it; q_repetition has to be recomputed. Neither is a defect,
    but a comparison that assumes the two column sets match will report
    dozens of spurious differences.

OFFLINE BY DEFAULT
------------------
Nothing here fetches over the network unless asked. The pipeline runs from
files in data/, so that a build is reproducible from the archive alone and
does not depend on a server being up. Pass a URL explicitly, or download
once and point at the file.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

ENDPOINTS = {
    "datedsites": "https://www1.rgzm.de/rest/samianresearch/datedsites",
    "datedsitesstatistics":
        "https://www1.rgzm.de/rest/samianresearch/datedsitesstatistics",
    "ips_stamps": "https://www1.rgzm.de/ips/lod/ips_stamps.csv",
}

# The JSON column names, upper case, mapped to the names used everywhere
# else in this repository.
STAMP_COLUMNS = {
    "THE_ID": "the_id",
    "THE_SITE": "the_site",
    "THE_FINDSPOT": "the_findspot",
    "LATINSITENAME": "latinsitename",
    "LONG": "long",
    "LAT": "lat",
    "PLEIADES": "pleiades",
    "STAMP_NUMBER": "stamp_number",
    "POTTERNAME": "pottername",
    "DIE": "die",
    "DATEMIN": "datemin",
    "DATEMAX": "datemax",
}


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def load_datedsites_json(path: Path) -> list[dict]:
    """The stamp-level input, from a saved response of /datedsites.

    Returns rows with lower-case keys, ready for py/ips_model.py.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))

    if not payload.get("success", True):
        raise SystemExit(f"  !!  {path.name}: the endpoint reports failure.")

    data = payload.get("data")
    if not isinstance(data, dict) or "COLUMNS" not in data:
        raise SystemExit(
            f"  !!  {path.name} is not a ColdFusion query serialisation.\n"
            "      Expected an object with data.COLUMNS and data.DATA.")

    columns = data["COLUMNS"]
    missing = [c for c in ("THE_SITE", "THE_FINDSPOT", "DATEMIN", "DATEMAX")
               if c not in columns]
    if missing:
        raise SystemExit(
            f"  !!  {path.name} lacks {', '.join(missing)}.\n"
            "      Without the potter dates the model cannot be recomputed. "
            "Is this ips_stamps.csv rather than /datedsites?")

    names = [STAMP_COLUMNS.get(c, c.lower()) for c in columns]
    rows = [dict(zip(names, r)) for r in data["DATA"]]

    declared = payload.get("records")
    if declared is not None and declared != len(rows):
        raise SystemExit(
            f"  !!  {path.name}: header declares {declared} records, "
            f"{len(rows)} present. Truncated download?")
    return rows


def load_statistics_csv(path: Path) -> list[dict]:
    """The findspot-level reference, from /datedsitesstatistics.

    Pipe-delimited; empty fields become None so that a missing value is not
    silently read as the string "".
    """
    with path.open(encoding="utf-8-sig", newline="") as fh:
        sample = fh.readline()
        fh.seek(0)
        delimiter = "|" if sample.count("|") > sample.count(",") else ","
        rows = [{k: (v if (v or "").strip() != "" else None)
                 for k, v in r.items()}
                for r in csv.DictReader(fh, delimiter=delimiter)]
    if not rows:
        raise SystemExit(f"  !!  {path.name} is empty.")
    return rows


def stamps_to_csv(rows: list[dict], path: Path) -> None:
    """Write the stamp-level input as the CSV py/ips_model.py reads.

    Keeps the JSON payload as the archived original and this as the working
    copy, rather than teaching every consumer the ColdFusion serialisation.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(STAMP_COLUMNS.values())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r[k]) for k in fields})


# --------------------------------------------------------------------------
# Provenance of the retrieval
# --------------------------------------------------------------------------
def snapshot(paths: dict[str, Path], retrieved: str | None = None) -> dict:
    """What "Stand Datum x" means, in machine-readable form.

    Samian Research is a live database: findspots are added and existing
    ones are declared usable as work proceeds. A fixed expected row count
    is therefore the wrong invariant — it would fail on every legitimate
    addition. What can be pinned is the retrieval: when, from where, how
    many records, and a checksum of exactly those bytes.
    """
    entries = {}
    for name, path in paths.items():
        raw = path.read_bytes()
        entries[name] = {
            "endpoint": ENDPOINTS.get(name),
            "file": path.name,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    return {
        "retrieved": retrieved or date.today().isoformat(),
        "note": ("Samian Research is a live database. This snapshot is what "
                 "the published figures rest on; cite it as the data state "
                 "rather than asserting a fixed number of findspots."),
        "sources": entries,
    }


def write_snapshot(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
