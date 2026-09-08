"""
IPS Dated Sites — calibrating tau, and showing what it rests on
===============================================================

    python py/calibrate_tau.py
    python py/calibrate_tau.py --drop Haltern

tau is defined as the smallest value at which every reference findspot's
independent terminus still falls inside the interval the model computes from
the stamps alone. That sentence appears in the SQL header, in the RDF as
lado:calibrationBasis, and on the method page. Until now it was a claim about
work done once; this script makes it a computation that can be repeated
whenever the data move.

WHAT IT REPORTS, AND WHY EACH PART MATTERS
------------------------------------------
  * the sweep — which references are contained at which tau. Shows whether
    the criterion has a clean threshold or scrapes through.

  * the binding reference — leave-one-out. Removing a reference either leaves
    tau_min where it was, in which case that reference was carried by the
    others and contributes nothing to the number, or it moves tau_min, in
    which case the calibration rests on it. A five-ensemble basis where four
    are non-binding is a one-ensemble calibration wearing a disguise, and
    the reader is entitled to know that.

  * the margin — how far each terminus sits from the nearer edge of its
    interval. A terminus two months inside is contained in the same sense as
    one six years inside, and the difference matters when judging how much
    weight the criterion bears.

WHAT IT DOES NOT DO
-------------------
It does not choose tau. The published value is set in the SQL and carried on
every row as p_tau; this script says what the data would support and leaves
the decision where it belongs. If the two diverge it says so and exits
non-zero, so that a drift between the stated basis and the actual one cannot
pass unnoticed.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py"))

from ips_rdf_export import CALIBRATION_REFERENCES, rounding_only_miss  # noqa: E402

STEP = 0.01
TAU_CEILING = 60.0


def load_rows(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {(r["the_site"], r["the_findspot"]): r for r in csv.DictReader(fh)}


def interval(row: dict, tau: float) -> tuple[float, float, float]:
    """The modelled interval at a given tau, from the row's own parameters.

    k_min, k_max and sigma are read from the export rather than restated, so
    that a change to the model cannot leave this script quietly computing
    something else.
    """
    n = int(row["count_stamps"])
    mid = float(row["midpoint_year"])
    sigma = float(row["sigma_eff"])
    k_min, k_max = float(row["p_k_min"]), float(row["p_k_max"])
    k = k_max - (k_max - k_min) * (1 - math.exp(-n / tau))
    return mid - k * sigma, mid + k * sigma, k


def contains_all(refs, rows, tau: float) -> bool:
    for site, findspot, terminus, _why, _contested in refs:
        lo, hi, _k = interval(rows[(site, findspot)], tau)
        if not lo <= terminus <= hi:
            return False
    return True


def published_status(refs, rows, tau: float):
    """Where the published tau stands, at full precision and with rounding.

    tau_min() and contains_all() stay strict on purpose — they answer "what
    does exact containment require", which is a fact worth keeping separate
    from "is the published value acceptable". This answers the second
    question, distinguishing a genuine miss from one that only exists at the
    tenth-year decimal eff_start/eff_end carry and nothing else in the
    corpus does. See rounding_only_miss() in py/ips_rdf_export.py for the
    2026-09-08 decision this implements.
    """
    misses, borderline = [], []
    for site, findspot, terminus, _why, _c in refs:
        lo, hi, _k = interval(rows[(site, findspot)], tau)
        if lo <= terminus <= hi:
            continue
        if rounding_only_miss(lo, hi, terminus):
            borderline.append(site)
        else:
            misses.append(site)
    return misses, borderline


def tau_min(refs, rows) -> float | None:
    """Smallest tau satisfying the criterion, to two decimals.

    Linear scan rather than a bisection: containment is monotone in tau for
    each reference individually, but the scan costs nothing here and does not
    require that assumption to hold for the set.
    """
    tau = STEP
    while tau <= TAU_CEILING:
        if contains_all(refs, rows, tau):
            return round(tau, 2)
        tau = round(tau + STEP, 2)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate tau and show its basis")
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--drop", action="append", default=[],
                    help="site to leave out of the reference set; repeatable")
    ap.add_argument("--include-contested", action="store_true",
                    help="include references flagged as contested "
                         "(excluded by default)")
    args = ap.parse_args()

    csv_path = args.csv
    if csv_path is None:
        found = sorted((ROOT / "data").glob("*.csv"))
        if len(found) != 1:
            raise SystemExit("  !!  expected exactly one CSV in data/, found "
                             f"{len(found)}. Pass --csv.")
        csv_path = found[0]

    rows = load_rows(csv_path)

    refs = [r for r in CALIBRATION_REFERENCES if r[0] not in args.drop]
    if not args.include_contested:
        refs = [r for r in refs if not r[4]]
    missing = [f"{a} — {b}" for a, b, _c, _d, _e in refs
               if (a, b) not in rows]
    if missing:
        raise SystemExit("  !!  not in the data: " + "; ".join(missing))
    if len(refs) < 2:
        raise SystemExit("  !!  fewer than two references left; nothing to "
                         "calibrate against.")

    published = float(next(iter(rows.values()))["p_tau"])

    print(f"  Source            : {csv_path.relative_to(ROOT)}")
    print(f"  References        : {len(refs)}"
          + (f"  (dropped: {', '.join(args.drop)})" if args.drop else ""))
    contested = [r[0] for r in CALIBRATION_REFERENCES if r[4]]
    if contested and not args.include_contested:
        print(f"  Excluded as contested: {', '.join(contested)}")
    print()

    # ---- the sweep -------------------------------------------------------
    print("  Containment by tau")
    header = "    tau  " + "".join(f"{r[0][:11]:>13}" for r in refs) + "     all"
    print(header)
    for tau in (1, 2, 3, 4, 5, 6, 8, 10, 15, 20):
        cells, every = [], True
        for site, findspot, terminus, _why, _c in refs:
            lo, hi, _k = interval(rows[(site, findspot)], float(tau))
            ok = lo <= terminus <= hi
            every &= ok
            cells.append(f"{'yes' if ok else 'no':>13}")
        print(f"    {tau:>3}  " + "".join(cells) + f"{'YES' if every else 'no':>8}")
    print()

    floor = tau_min(refs, rows)
    print(f"  Smallest tau satisfying the criterion : {floor}  (full precision)")
    print(f"  Published tau (p_tau on every row)    : {published}")

    misses, borderline = published_status(refs, rows, published)
    if misses:
        print("  !!  At the published tau, these references fall outside "
              "their modelled interval even once rounded to the year: "
              + ", ".join(misses))
        return 1
    if borderline:
        print("  --  At the published tau, these references are outside "
              "at full precision but inside once rounded to the year — "
              "accepted per the 2026-09-08 decision, see "
              "rounding_only_miss() in ips_rdf_export.py: "
              + ", ".join(borderline))
    if floor is None:
        print("  --  No tau up to the ceiling satisfies the criterion at "
              "full precision; the published value is accepted on the "
              "rounded reading above instead. Headroom is not meaningful "
              "here and is not reported.")
    elif published < floor:
        print("  !!  The published tau is BELOW the calibrated floor: the "
              "model contradicts evidence it cannot see.")
        return 1
    else:
        print(f"  Headroom                              : "
              f"{round(published - floor, 2)}")
    print()

    # ---- what the number actually rests on -------------------------------
    print("  Leave-one-out — which reference sets the floor")
    for site, _fs, _t, _why, _c in refs:
        sub = [r for r in refs if r[0] != site]
        if len(sub) < 2:
            continue
        alt = tau_min(sub, rows)
        if floor is None:
            verdict = "the blocker" if alt is not None else "still blocked"
        else:
            verdict = "binding" if alt is not None and alt < floor else "not binding"
        print(f"    without {site:<14} tau_min = {alt!s:<7} {verdict}")
    print()

    # ---- margins ---------------------------------------------------------
    print(f"  Margins at the published tau = {published}")
    for site, findspot, terminus, why, _c in refs:
        row = rows[(site, findspot)]
        lo, hi, k = interval(row, published)
        margin = min(terminus - lo, hi - terminus)
        note = "  (rounding only)" if site in borderline else ""
        print(f"    {site:<14} n={row['count_stamps']:>4}  k={k:.4f}  "
              f"[{lo:8.1f} .. {hi:8.1f}]  terminus {terminus:>4}  "
              f"margin {margin:6.1f} a   {why}{note}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
