"""
IPS Dated Sites — the dating model, in Python
=============================================

Recomputes the findspot datings from the raw stamps in
`v_ips_dated_stamps`, producing the same columns as
`sql/IPSDatedSites.sql`. Two implementations of one model, so that it can
be read without a database and checked against itself.

    python py/ips_model.py --raw ips_stamps.csv
    python py/ips_model.py --raw ips_stamps.csv --against data/data-*.csv

The second form is the point of the exercise: it recomputes everything and
compares column by column against the database export, the same way step 4
compares the RDF round trip. A deviation anywhere is a disagreement
between the two implementations, and one of them is wrong.

WHY THIS IS HARDER THAN IT LOOKS
--------------------------------
The arithmetic is easy. The rounding is not, and that is where a
reimplementation quietly diverges:

  * PostgreSQL rounds numeric half AWAY FROM ZERO. Python's round() rounds
    half to EVEN. avg_datemin = -20.5 becomes -21 in the database and -20
    in naive Python.
  * AVG and VAR_SAMP over integer columns are exact rational arithmetic in
    numeric. In float they are not, and a value that should land exactly on
    .5 may land just below it.
  * eff_start uses the UNROUNDED sigma; the exported sigma_eff column is
    rounded to three places. Rounding first and multiplying second gives a
    different answer.
  * STDDEV_SAMP of a single row is NULL, not zero. That NULL travels all
    the way into q_start, and the figure draws it grey.

So the averages and variances here run on Fraction, which is exact for
integer input, and every rounding step goes through pg_round.

WHAT IS NOT DONE HERE
---------------------
The data filters live in the view: which stamps count as dated, and the
eleven placeholder pairs. This script only sees what survived them. The
editorial exclusions are parameters, because they change more often than
the data does.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The model parameters. Mirrors the params CTE; overridable so the script
# can reproduce an older export without editing.
DEFAULTS = {"k_min": 0.5, "k_max": 1.5, "tau": 6.0, "w": 1.0, "t0": 20.0}

# The variance of a uniform distribution over a unit range. Fixed, not a
# tunable: it is where the per-stamp distributional assumption enters.
FUZZINESS_DIVISOR = 12


# --------------------------------------------------------------------------
# Rounding, the PostgreSQL way
# --------------------------------------------------------------------------
def pg_round(value, places: int):
    """ROUND(x, n) as numeric does it: half away from zero.

    Python's round() would give a different answer on every exact half, and
    integer means over an even number of stamps produce exact halves often
    enough to matter.
    """
    if value is None:
        return None
    q = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))


def pg_int(value):
    """::integer on a numeric: half away from zero."""
    if value is None:
        return None
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def frac(values) -> Fraction:
    """AVG over integers, exactly."""
    return Fraction(sum(values), len(values))


def var_samp(values):
    """VAR_SAMP over integers, exactly. NULL for a single row."""
    n = len(values)
    if n < 2:
        return None
    m = Fraction(sum(values), n)
    return sum((Fraction(v) - m) ** 2 for v in values) / (n - 1)


def stddev_samp(values):
    v = var_samp(values)
    return None if v is None else math.sqrt(v)


# --------------------------------------------------------------------------
# Reading the raw stamps
# --------------------------------------------------------------------------
def load_stamps(path: Path) -> list[dict]:
    """The stamp-level input, from CSV or from a saved /datedsites response.

    The JSON form is what the REST endpoint returns; the CSV form is the
    export of sql/v_ips_dated_stamps.sql. Same rows either way.
    """
    def num(v):
        v = (v or "").strip() if isinstance(v, str) else v
        return None if v == "" else v

    if path.suffix.lower() == ".json":
        import ips_rest
        raw = ips_rest.load_datedsites_json(path)
    else:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            head = fh.readline()
            fh.seek(0)
            # The published statistics are pipe-delimited; a stamp export
            # sniffed as comma-delimited would yield one giant column and a
            # KeyError three frames down.
            delim = "|" if head.count("|") > head.count(",") else ","
            raw = list(csv.DictReader(fh, delimiter=delim))

    rows = []
    for r in raw:
        try:
            datemin = int(float(r["datemin"]))
            datemax = int(float(r["datemax"]))
        except (TypeError, ValueError, KeyError):
            # A stamp without potter dates cannot contribute. The view
            # already drops these; belt and braces. If EVERY row lands
            # here the caller is holding ips_stamps.csv, which carries
            # no dates at all — see py/ips_rest.py.
            continue
        rows.append({
            "the_id": num(r.get("the_id")),
            "the_site": r["the_site"],
            "the_findspot": r["the_findspot"],
            "latinsitename": num(r.get("latinsitename")),
            "long": num(r.get("long")),
            "lat": num(r.get("lat")),
            "pleiades": num(r.get("pleiades")),
            "stamp_number": num(r.get("stamp_number")),
            "pottername": r.get("pottername") or "",
            "die": num(r.get("die")),
            "datemin": datemin,
            "datemax": datemax,
        })
    return rows


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------
def die_counts(stamps: list[dict]):
    """The die statistics. Descriptive only — since revision 30a these do
    NOT enter the geometry.

    One detail that is easy to get wrong: dies are counted DISTINCT WITHIN
    A POTTER, so the same die code under two potters counts twice. Counting
    globally distinct dies gives 47 instead of 131 at London / New Fresh
    Wharf, which is how this was found.
    """
    per_potter: dict[str, set] = {}
    stamps_with_die = 0
    for s in stamps:
        if s["die"] is None:
            continue
        per_potter.setdefault(s["pottername"], set()).add(s["die"])
        stamps_with_die += 1

    if not per_potter:
        # No die attribution anywhere at this findspot. Reported, because it
        # is a gap in the record worth closing, but without consequence for
        # the dating.
        return None, None, True

    n_dies = sum(len(d) for d in per_potter.values())
    return n_dies, stamps_with_die, False


def k_factor(n_stamps: int, p: dict) -> float:
    """The volume-based coverage factor.

    k = k_max - (k_max - k_min) * (1 - exp(-n / tau))

    n is the stamp count of the findspot, and nothing else. Before 30a it
    was the number of stamps CARRYING A DIE, taken from the kfactor CTE,
    which coupled the width of the box to how completely the die record
    happened to be filled in; where that CTE returned no row at all, k fell
    back to k_max and the interval widened for a reason that had nothing to
    do with the material. On the August 2026 corpus the two counts agree
    everywhere, so the change moves no number — it removes a failure mode.
    """
    return p["k_max"] - (p["k_max"] - p["k_min"]) * (
        1 - math.exp(-n_stamps / p["tau"]))


def dating(stamps: list[dict], p: dict) -> dict:
    """One findspot, from its stamps."""
    dmin = [s["datemin"] for s in stamps]
    dmax = [s["datemax"] for s in stamps]

    avg_min, avg_max = frac(dmin), frac(dmax)
    n_dies, n_stamps_die, no_dierecord = die_counts(stamps)

    # COUNT(di.number): the stamps of this findspot, which is what k reads.
    count_stamps = sum(1 for s in stamps if s["stamp_number"] is not None)
    k_used = k_factor(count_stamps, p)

    # sigma: the inner fuzziness of each potter's own range, plus the
    # scatter of those ranges' midpoints. VAR_SAMP is NULL for a single
    # stamp, and the query coalesces that to zero - the one place where a
    # missing value is deliberately treated as a known zero.
    inner = frac([(b - a) ** 2 for a, b in zip(dmin, dmax)]) / FUZZINESS_DIVISOR
    mids = [Fraction(a + b, 2) for a, b in zip(dmin, dmax)]
    outer = var_samp_frac(mids) or Fraction(0)
    sigma = math.sqrt(float(inner + outer))

    mid = float(avg_min + avg_max) / 2.0
    sd_min, sd_max = stddev_samp(dmin), stddev_samp(dmax)
    v_min, v_max = var_samp(dmin), var_samp(dmax)

    span = float(avg_max - avg_min)
    q_interval = None
    if span != 0 and v_min is not None and v_max is not None:
        q_interval = pg_round(
            math.exp(-math.sqrt(float(v_min + v_max)) / abs(span)), 3)

    first = stamps[0]
    return {
        "the_id": first["the_id"],
        "the_site": first["the_site"],
        "the_findspot": first["the_findspot"],
        "latinsitename": first["latinsitename"],
        "long": first["long"],
        "lat": first["lat"],
        "pleiades": first["pleiades"],

        "count_stamps": count_stamps,

        "avg_datemin": pg_int(float(avg_min)),
        "avg_datemax": pg_int(float(avg_max)),
        "min_datemin": min(dmin), "max_datemin": max(dmin),
        "min_datemax": min(dmax), "max_datemax": max(dmax),

        "q_start": None if sd_min is None else pg_round(
            math.exp(-sd_min / p["t0"]), 3),
        "q_end": None if sd_max is None else pg_round(
            math.exp(-sd_max / p["t0"]), 3),
        "q_interval": q_interval,

        "n_dies": n_dies,
        "die_repetition": None if n_dies is None else pg_round(
            n_stamps_die / n_dies, 3),
        # Note the query builds this from the ROUNDED repetition, not from
        # the exact ratio. Reproducing that is the whole job here.
        "q_repetition": None if n_dies is None else pg_round(
            1 - 1.0 / max(pg_round(n_stamps_die / n_dies, 3), 1), 3),

        "avg_interval": f"{pg_int(float(avg_min))} to {pg_int(float(avg_max))}",

        "unc_start_years": None if sd_min is None else pg_int(sd_min),
        "unc_end_years": None if sd_max is None else pg_int(sd_max),
        "unc_interval_years": None if v_min is None else pg_int(
            math.sqrt(float(v_min + v_max))),
        "unc_start_years_exact": None if sd_min is None else pg_round(sd_min, 6),
        "unc_end_years_exact": None if sd_max is None else pg_round(sd_max, 6),

        "midpoint_year": pg_round(mid, 3),
        "n_stamps_die": n_stamps_die,
        "k_eff": pg_round(k_used, 4),
        # Renamed in 30a, and it now means something else: a gap in the die
        # record, not a substituted k. It no longer moves eff_start/eff_end.
        "k_no_dierecord": no_dierecord,
        "sigma_eff": pg_round(sigma, 3),

        "p_k_min": pg_round(p["k_min"], 3), "p_k_max": pg_round(p["k_max"], 3),
        "p_tau": pg_round(p["tau"], 3), "p_w": pg_round(p["w"], 3),
        "p_t0": pg_round(p["t0"], 3),

        # Built from the UNROUNDED sigma, as the query does. Rounding sigma
        # first and multiplying second shifts the bounds by up to half a
        # year, which is visible in the figure.
        "eff_start": pg_round(mid - k_used * sigma, 1),
        "eff_end": pg_round(mid + k_used * sigma, 1),

        # The watchdogs, added in 30a and deliberately last so that the
        # earlier column order survives as a prefix. The 100-year threshold
        # is not a tuning knob: Allard confirmed on 2026-08-25 that potters
        # such as Calvus i worked in more than one production centre and
        # took part of their punches with them, so without
        # chemical-mineralogical analysis a long span cannot be separated
        # into displacement, father and son, one person or a workshop. The
        # threshold marks the limit of attainable precision.
        "n_stamps_wide": sum(1 for a, b in zip(dmin, dmax) if b - a >= 100),
        "n_potters_wide": len({s["pottername"] for s in stamps
                               if s["datemax"] - s["datemin"] >= 100}),
        "max_potter_span": max(b - a for a, b in zip(dmin, dmax)),
    }


def var_samp_frac(values):
    """VAR_SAMP over Fractions. Separate from var_samp only because the
    midpoints are halves and must stay exact."""
    n = len(values)
    if n < 2:
        return None
    m = sum(values) / n
    return sum((v - m) ** 2 for v in values) / (n - 1)


def build(stamps: list[dict], p: dict, exclude: list[str],
          min_stamps: int) -> list[dict]:
    groups: dict[tuple, list] = {}
    for s in stamps:
        if any(x.lower() in s["the_site"].lower() for x in exclude):
            continue
        groups.setdefault((s["the_id"], s["the_site"], s["the_findspot"]),
                          []).append(s)

    rows = [dating(g, p) for g in groups.values()]
    rows = [r for r in rows if r["count_stamps"] >= min_stamps]
    # ORDER BY avg_datemin ASC, as the query does.
    rows.sort(key=lambda r: (r["avg_datemin"], r["the_site"] or "",
                             r["the_findspot"] or ""))
    return rows


# --------------------------------------------------------------------------
# Comparison against the database export
# --------------------------------------------------------------------------
NUMERIC = [
    "count_stamps", "avg_datemin", "avg_datemax", "min_datemin",
    "max_datemin", "min_datemax", "max_datemax", "q_start", "q_end",
    "q_interval", "n_dies", "die_repetition", "q_repetition",
    "unc_start_years", "unc_end_years", "unc_interval_years",
    "unc_start_years_exact", "unc_end_years_exact", "midpoint_year",
    "n_stamps_die", "k_eff", "sigma_eff", "eff_start", "eff_end",
    "n_stamps_wide", "n_potters_wide", "max_potter_span",
]

# The REST statistics endpoint does not publish these two: the_id is only in
# the stamp-level resource, q_repetition is not exported at all. Absent from
# the reference is not a disagreement; absent from BOTH would be.
OPTIONAL = {"the_id", "q_repetition"}


def compare(rows: list[dict], csv_path: Path) -> int:
    import ips_rest
    ref = {(r["the_site"], r["the_findspot"]): r
           for r in ips_rest.load_statistics_csv(csv_path)}
    mine = {(r["the_site"], r["the_findspot"]): r for r in rows}

    only_db = sorted(set(ref) - set(mine))
    only_py = sorted(set(mine) - set(ref))
    print(f"  findspots: database {len(ref)}, recomputed {len(mine)}")
    for k in only_db[:5]:
        print(f"    only in the database : {k[0]} — {k[1]}")
    for k in only_py[:5]:
        print(f"    only recomputed      : {k[0]} — {k[1]}")

    shared = sorted(set(ref) & set(mine))
    if not shared:
        print("  !!  no findspot in common — is this the right export?")
        return 2

    bad = 0
    print()
    for col in NUMERIC:
        if col in OPTIONAL and all(ref[k].get(col) is None for k in shared):
            print(f"  -- {col:<24} not published by this reference")
            continue
        worst, where = 0.0, None
        nulls = 0
        for key in shared:
            a, b = mine[key].get(col), ref[key].get(col)
            b = None if b is None or str(b).strip() == "" else float(b)
            if a is None or b is None:
                if (a is None) != (b is None):
                    nulls += 1
                continue
            d = abs(float(a) - b)
            if d > worst:
                worst, where = d, key
        flag = "OK " if worst < 5e-4 and nulls == 0 else "!! "
        if flag == "!! ":
            bad += 1
        note = ""
        if nulls:
            note = f"   {nulls} NULL mismatch(es)"
        elif where and worst >= 5e-4:
            note = f"   worst at {where[0]} — {where[1]}"
        print(f"  {flag}{col:<24} max |Delta| = {worst:.2e}{note}")

    print()
    if bad:
        print(f"  {bad} column(s) disagree. The two implementations are not "
              f"the same model.")
    else:
        print("  Every column agrees. The Python model reproduces the SQL.")
    return 2 if bad else 0


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        raise SystemExit("  !!  nothing to write.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recompute the findspot datings from the raw stamps")
    ap.add_argument("--raw", type=Path, required=True,
                    help="export of v_ips_dated_stamps")
    ap.add_argument("--out", type=Path, default=None,
                    help="write the recomputed table here")
    ap.add_argument("--against", type=Path, default=None,
                    help="compare against a database export of the "
                         "aggregate query")
    # No default exclusion since 2026-08-25. Samian Research is a live
    # database: unchecked findspots will always exist and new ones are
    # declared usable as work proceeds, so naming individual sites in the
    # code is the wrong instrument. What is pinned instead is the retrieval
    # date — see data/SNAPSHOT.json. Still available as a parameter for a
    # deliberate, documented exclusion.
    ap.add_argument("--exclude-site", action="append", default=[],
                    help="site to leave out; repeatable, empty by default. "
                         "Editorial, not a data filter — see the view.")
    ap.add_argument("--min-stamps", type=int, default=1)
    for name, val in DEFAULTS.items():
        ap.add_argument(f"--{name.replace('_', '-')}", type=float, default=val)
    args = ap.parse_args()

    exclude = [x for x in args.exclude_site if x.strip()]
    p = {k: getattr(args, k) for k in DEFAULTS}
    stamps = load_stamps(args.raw)
    if not stamps:
        raise SystemExit(f"  !!  no usable stamps in {args.raw}")
    rows = build(stamps, p, exclude, args.min_stamps)

    print(f"  Stamps            : {len(stamps)}")
    print(f"  Findspots         : {len(rows)}")
    print(f"  Model             : k_min={p['k_min']}, k_max={p['k_max']}, "
          f"tau={p['tau']}, w={p['w']}, t0={p['t0']}")
    if exclude:
        print(f"  Excluded          : {', '.join(exclude)}")
    print()

    if args.out:
        write_csv(rows, args.out)
        print(f"  {args.out}")
    if args.against:
        return compare(rows, args.against)
    return 0


if __name__ == "__main__":
    sys.exit(main())
