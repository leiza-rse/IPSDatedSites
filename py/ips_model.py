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
    def num(v):
        v = (v or "").strip()
        return None if v == "" else v

    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                datemin = int(float(r["datemin"]))
                datemax = int(float(r["datemax"]))
            except (TypeError, ValueError, KeyError):
                # A stamp without potter dates cannot contribute. The view
                # already drops these; belt and braces.
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
def k_factor(stamps: list[dict], p: dict):
    """The volume-based coverage factor, from the stamps that carry a die.

    Mirrors the diecounts and kfactor CTEs. Two details that are easy to
    get wrong: dies are counted DISTINCT WITHIN A POTTER, so the same die
    code under two potters counts twice; and the sum that drives k is the
    number of stamps with a die, not the number of stamps.
    """
    per_potter: dict[str, set] = {}
    stamps_with_die = 0
    for s in stamps:
        if s["die"] is None:
            continue
        per_potter.setdefault(s["pottername"], set()).add(s["die"])
        stamps_with_die += 1

    if not per_potter:
        # No die anywhere. k falls back to k_max, which widens the interval
        # for a reason that has nothing to do with the material - hence the
        # flag, so a consumer can tell the two cases apart.
        return None, None, None, True

    n_dies = sum(len(d) for d in per_potter.values())
    rep = pg_round(stamps_with_die / n_dies, 3) if n_dies else None
    k = p["k_max"] - (p["k_max"] - p["k_min"]) * (
        1 - math.exp(-stamps_with_die / p["tau"]))
    return n_dies, stamps_with_die, pg_round(k, 4), False


def dating(stamps: list[dict], p: dict) -> dict:
    """One findspot, from its stamps."""
    dmin = [s["datemin"] for s in stamps]
    dmax = [s["datemax"] for s in stamps]

    avg_min, avg_max = frac(dmin), frac(dmax)
    n_dies, n_stamps_die, k_eff, k_fallback = k_factor(stamps, p)
    k_used = p["k_max"] if k_eff is None else k_eff

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

        "count_stamps": sum(1 for s in stamps if s["stamp_number"] is not None),

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
        "k_is_fallback": k_fallback,
        "sigma_eff": pg_round(sigma, 3),

        "p_k_min": pg_round(p["k_min"], 3), "p_k_max": pg_round(p["k_max"], 3),
        "p_tau": pg_round(p["tau"], 3), "p_w": pg_round(p["w"], 3),
        "p_t0": pg_round(p["t0"], 3),

        # Built from the UNROUNDED sigma, as the query does. Rounding sigma
        # first and multiplying second shifts the bounds by up to half a
        # year, which is visible in the figure.
        "eff_start": pg_round(mid - k_used * sigma, 1),
        "eff_end": pg_round(mid + k_used * sigma, 1),
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
]


def compare(rows: list[dict], csv_path: Path) -> int:
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        ref = {(r["the_site"], r["the_findspot"]): r
               for r in csv.DictReader(fh)}
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
    # NOT default=["Bregenz"]: argparse APPENDS to a list default instead
    # of replacing it, so the default could never be switched off. None,
    # then fill in below, and --exclude-site "" clears it.
    ap.add_argument("--exclude-site", action="append", default=None,
                    help="site to leave out; repeatable, default Bregenz. "
                         'Pass --exclude-site "" to keep everything. '
                         "Editorial, not a data filter — see the view.")
    ap.add_argument("--min-stamps", type=int, default=1)
    for name, val in DEFAULTS.items():
        ap.add_argument(f"--{name.replace('_', '-')}", type=float, default=val)
    args = ap.parse_args()

    exclude = ["Bregenz"] if args.exclude_site is None else [
        x for x in args.exclude_site if x.strip()]
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
