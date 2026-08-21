#!/usr/bin/env python3
"""Verify the IPS dated-sites CSV export against the model it claims to encode.

The query (``sql/IPSDatedSites27c.sql``) is authoritative: this module never
recomputes a published value, it only re-derives each one from the other
columns of the same row and asserts agreement. A failure therefore means one
of two things — the export is not the output of the query it purports to be,
or the query has changed without this module being told.

The checks are the control points from the query header, carried over
verbatim so that the letters match:

    (a)  row count
    (c)  k_eff from n_stamps_die and the k parameters
    (d)  interval width equals 2 * k_eff * sigma_eff
    (h)  q_start / q_end from unc_*_years_exact and t0
    (i)  q monotonically decreasing in sigma
    (l)  epoch drift lives in the box width, not in the colour  [reported]

Plus invariants that have no letter because they were never in doubt until
they were: constant parameter columns, the NULL policy, the integer casts,
and the absence of the fabricated 0.5 fallback removed in IPSDatedSites26.

Deliberately dependency-free — standard library only. A module that verifies
the pipeline should not import the pipeline, nor share a numerics stack with
the code that produced the numbers it is checking.

Usage
-----
    python py/verify.py data/sites.csv
    python py/verify.py data/sites.csv --json data/derived/verification.json
    python py/verify.py data/sites.csv --strict        # warnings fail too

Exit codes: 0 all checks passed, 1 at least one failed, 2 the file could not
be read or lacks required columns.

The JSON report carries a ``facts`` block holding every figure the
documentation pages quote. ``docu.py`` reads that block rather than repeating
the arithmetic, so a number can never differ between the prose and the data.
No timestamp is written unless ``--stamp`` is given: an unconditional
timestamp would make every run differ from the last and defeat the
byte-identical rebuild the repository relies on.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------------------
# Tolerances. Each one is the rounding of a specific cast in the query; none
# is a fudge factor. If a cast changes, change the tolerance beside it.
# --------------------------------------------------------------------------

TOL_K_EFF = 5e-5          # k_eff        numeric(10,4)
TOL_WIDTH = 0.11          # eff_start/eff_end  2 x numeric(10,1), plus k*sigma
TOL_Q_EXACT = 1e-9        # q_*          numeric(...,3) against exact sigma
TOL_Q_FLIP = 1.1e-3       # one last-digit flip: warn, do not fail
TOL_INT_CAST = 0.5 + 1e-9 # unc_*_years  ::integer
TOL_PARAM = 1e-12         # parameter columns must be literally constant

REQUIRED_COLUMNS = (
    "the_site", "the_findspot", "count_stamps",
    "q_start", "q_end", "q_interval",
    "unc_start_years", "unc_end_years",
    "unc_start_years_exact", "unc_end_years_exact",
    "midpoint_year", "n_stamps_die", "k_eff", "k_is_fallback", "sigma_eff",
    "p_k_min", "p_k_max", "p_tau", "p_w", "p_t0",
    "eff_start", "eff_end",
)

PARAMETER_COLUMNS = ("p_k_min", "p_k_max", "p_tau", "p_w", "p_t0")

EXPECTED_ROWS = 37        # IPSDatedSites28, pairwise placeholder filter,
                          # Bregenz withheld pending review (6 findspots)

# Allard Mees: a scatter of about +/- 5 years counts as sharply dated for
# samian ware, about +/- 25 years as chronologically unusable. These two
# anchors fix t0; the documentation quotes the q values they produce.
ANCHOR_SHARP_YEARS = 5.0
ANCHOR_UNUSABLE_YEARS = 25.0

STATUS_ORDER = {"pass": 0, "info": 0, "warn": 1, "fail": 2}


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------

@dataclass
class Check:
    """One control point and what became of it."""
    key: str
    title: str
    status: str                      # pass | warn | fail | info
    detail: str = ""
    offenders: list[dict[str, Any]] = field(default_factory=list)

    def line(self) -> str:
        mark = {"pass": "ok  ", "warn": "warn", "fail": "FAIL", "info": "--  "}[self.status]
        return f"  [{mark}] {self.key:<3} {self.title}\n         {self.detail}"


@dataclass
class Report:
    source: str
    checks: list[Check] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def add(self, check: Check) -> Check:
        self.checks.append(check)
        return check

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warned(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "summary": {
                "checks": len(self.checks),
                "failed": len(self.failed),
                "warned": len(self.warned),
            },
            "checks": [
                {
                    "key": c.key, "title": c.title, "status": c.status,
                    "detail": c.detail, "offenders": c.offenders,
                }
                for c in self.checks
            ],
            "facts": self.facts,
        }


# --------------------------------------------------------------------------
# Parsing. NULL in the database arrives as an empty cell; that is meaningful
# (see change (2) in IPSDatedSites26) and must survive as None, never as 0.
# --------------------------------------------------------------------------

def num(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if text == "" or text.upper() in {"NULL", "NAN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def flag(value: str | None) -> bool | None:
    if value is None:
        return None
    text = value.strip().lower()
    if text in {"t", "true", "1", "y", "yes"}:
        return True
    if text in {"f", "false", "0", "n", "no"}:
        return False
    return None


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def label(row: dict[str, str]) -> str:
    site = (row.get("the_site") or "?").strip()
    spot = (row.get("the_findspot") or "").strip()
    return f"{site} / {spot}" if spot else site


# --------------------------------------------------------------------------
# Small statistics, so that the module stays dependency-free
# --------------------------------------------------------------------------

def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xv = [p[0] for p in pairs]
    yv = [p[1] for p in pairs]
    mx, my = statistics.fmean(xv), statistics.fmean(yv)
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    sxx = sum((a - mx) ** 2 for a in xv)
    syy = sum((b - my) ** 2 for b in yv)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def median_or_none(values: Iterable[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_columns(report: Report, rows: list[dict[str, str]]) -> bool:
    present = set(rows[0].keys()) if rows else set()
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    if missing:
        report.add(Check(
            "k", "column set", "fail",
            f"{len(missing)} required column(s) absent: {', '.join(missing)}. "
            "An export from IPSDatedSites26 or earlier cannot be verified — "
            "the exact-sigma and t0 columns do not exist there.",
        ))
        return False
    report.add(Check(
        "k", "column set", "pass",
        f"{len(present)} columns, all {len(REQUIRED_COLUMNS)} required ones present.",
    ))
    return True


def check_row_count(report: Report, rows: list[dict[str, str]]) -> None:
    n = len(rows)
    if n == EXPECTED_ROWS:
        report.add(Check("a", "row count", "pass", f"{n} findspots, as expected."))
    else:
        report.add(Check(
            "a", "row count", "warn",
            f"{n} findspots, expected {EXPECTED_ROWS}. Not an error in itself — "
            "the database grows — but every figure quoted in the documentation "
            "was computed against a different corpus.",
        ))


def read_parameters(report: Report, rows: list[dict[str, str]]) -> dict[str, float]:
    """Parameters are broadcast into every row; they must be identical in all."""
    params: dict[str, float] = {}
    offenders: list[dict[str, Any]] = []
    for column in PARAMETER_COLUMNS:
        values = {row[column].strip() for row in rows}
        if len(values) != 1:
            offenders.append({"column": column, "values": sorted(values)})
            continue
        parsed = num(values.pop())
        if parsed is None:
            offenders.append({"column": column, "values": ["<null>"]})
            continue
        params[column] = parsed

    if offenders:
        report.add(Check(
            "p", "parameter columns constant", "fail",
            "A parameter varies within one export. Two runs have been "
            "concatenated, or the params CTE was edited mid-export.",
            offenders,
        ))
    else:
        shown = ", ".join(f"{k[2:]}={v:g}" for k, v in params.items())
        report.add(Check("p", "parameter columns constant", "pass", shown))
    return params


def check_k_eff(report: Report, rows, params) -> None:
    k_min, k_max, tau = params["p_k_min"], params["p_k_max"], params["p_tau"]
    worst, offenders = 0.0, []
    for row in rows:
        n = num(row["n_stamps_die"])
        k = num(row["k_eff"])
        fallback = flag(row["k_is_fallback"])
        if k is None:
            continue
        if fallback or n is None:
            expected = k_max          # documented model behaviour, not a measurement
        else:
            expected = k_max - (k_max - k_min) * (1.0 - math.exp(-n / tau))
        deviation = abs(k - expected)
        worst = max(worst, deviation)
        if deviation > TOL_K_EFF:
            offenders.append({
                "findspot": label(row), "k_eff": k,
                "expected": round(expected, 6), "deviation": round(deviation, 6),
            })
    if offenders:
        report.add(Check("c", "k_eff from n_stamps_die", "fail",
                         f"{len(offenders)} row(s) beyond {TOL_K_EFF:g}; worst {worst:.2e}.",
                         offenders))
    else:
        report.add(Check("c", "k_eff from n_stamps_die", "pass",
                         f"worst deviation {worst:.2e}, within the numeric(10,4) cast."))


def check_interval_width(report: Report, rows) -> None:
    worst, offenders = 0.0, []
    for row in rows:
        start, end = num(row["eff_start"]), num(row["eff_end"])
        k, sigma = num(row["k_eff"]), num(row["sigma_eff"])
        if None in (start, end, k, sigma):
            continue
        deviation = abs((end - start) - 2.0 * k * sigma)
        worst = max(worst, deviation)
        if deviation > TOL_WIDTH:
            offenders.append({
                "findspot": label(row), "width": round(end - start, 3),
                "expected": round(2.0 * k * sigma, 3), "deviation": round(deviation, 3),
            })
    if offenders:
        report.add(Check("d", "interval width = 2 k sigma", "fail",
                         f"{len(offenders)} row(s) beyond {TOL_WIDTH:g} years; worst {worst:.3f}.",
                         offenders))
    else:
        report.add(Check("d", "interval width = 2 k sigma", "pass",
                         f"worst deviation {worst:.3f} years, within the numeric(10,1) casts."))


def check_q_from_sigma(report: Report, rows, params) -> None:
    """(h) — the check the exact-sigma columns exist for."""
    t0 = params["p_t0"]
    for side, q_col, sigma_col in (("start", "q_start", "unc_start_years_exact"),
                                   ("end", "q_end", "unc_end_years_exact")):
        worst, hard, soft = 0.0, [], []
        for row in rows:
            q, sigma = num(row[q_col]), num(row[sigma_col])
            if q is None or sigma is None:
                continue
            expected = round(math.exp(-sigma / t0), 3)
            deviation = abs(q - expected)
            worst = max(worst, deviation)
            if deviation > TOL_Q_EXACT:
                entry = {"findspot": label(row), q_col: q,
                         "expected": expected, "sigma": sigma}
                (soft if deviation <= TOL_Q_FLIP else hard).append(entry)
        key = "h" if side == "start" else "h'"
        title = f"{q_col} = exp(-sigma / t0)"
        if hard:
            report.add(Check(key, title, "fail",
                             f"{len(hard)} row(s) disagree by more than a last digit; "
                             f"worst {worst:.6f}. The formula in the query is not the one "
                             f"assumed here, or t0 differs.", hard + soft))
        elif soft:
            report.add(Check(key, title, "warn",
                             f"{len(soft)} row(s) differ by one last digit (worst {worst:.6f}). "
                             f"Rounding boundary in {sigma_col}, not a formula error — "
                             f"widen that cast if a digit-identical round trip is wanted.",
                             soft))
        else:
            report.add(Check(key, title, "pass",
                             f"exact in all rows (t0 = {t0:g} years)."))


def check_monotonic(report: Report, rows) -> None:
    """(i) — the defect that made the calendar-origin formula unusable."""
    for side, q_col, sigma_col in (("start", "q_start", "unc_start_years_exact"),
                                   ("end", "q_end", "unc_end_years_exact")):
        pairs = [(num(r[sigma_col]), num(r[q_col]), label(r)) for r in rows]
        pairs = [p for p in pairs if p[0] is not None and p[1] is not None]
        pairs.sort(key=lambda p: p[0])
        offenders = [
            {"after": pairs[i][2], "before": pairs[i - 1][2],
             "sigma": pairs[i][0], "q": pairs[i][1]}
            for i in range(1, len(pairs))
            if pairs[i][1] > pairs[i - 1][1] + 1e-12
        ]
        key = "i" if side == "start" else "i'"
        title = f"{q_col} decreases monotonically in sigma"
        if offenders:
            report.add(Check(key, title, "fail",
                             f"{len(offenders)} inversion(s): a findspot with larger scatter "
                             f"scores better. This is the signature of a quality measure that "
                             f"depends on something other than the scatter.", offenders))
        else:
            report.add(Check(key, title, "pass", f"{len(pairs)} values, no inversion."))


def check_null_policy(report: Report, rows) -> None:
    """q is NULL exactly where sigma is undefined (n = 1). No fabricated middle."""
    offenders = []
    for row in rows:
        for q_col, sigma_col in (("q_start", "unc_start_years_exact"),
                                 ("q_end", "unc_end_years_exact")):
            q, sigma = num(row[q_col]), num(row[sigma_col])
            if (q is None) != (sigma is None):
                offenders.append({"findspot": label(row), "column": q_col,
                                  "q": q, "sigma": sigma})
    if offenders:
        report.add(Check("n", "NULL policy", "fail",
                         "q is defined where sigma is not, or the reverse. NULL must reach "
                         "the plot as NULL so that it renders grey rather than as a colour "
                         "nobody chose.", offenders))
    else:
        report.add(Check("n", "NULL policy", "pass",
                         "q is null exactly where the standard deviation is undefined."))


def check_no_fabricated_fallback(report: Report, rows) -> None:
    """Guard against the COALESCE(..., 0.5) removed in IPSDatedSites26."""
    suspects = []
    for row in rows:
        for q_col, sigma_col in (("q_start", "unc_start_years_exact"),
                                 ("q_end", "unc_end_years_exact"),
                                 ("q_interval", None)):
            q = num(row[q_col])
            if q is None or abs(q - 0.5) > 1e-9:
                continue
            sigma = num(row[sigma_col]) if sigma_col else None
            if sigma_col is not None and sigma is None:
                suspects.append({"findspot": label(row), "column": q_col})
    if suspects:
        report.add(Check("f", "no fabricated 0.5 fallback", "fail",
                         "A quality measure is exactly 0.5 while its input is undefined. "
                         "The COALESCE hull removed in IPSDatedSites26 appears to be back.",
                         suspects))
    else:
        report.add(Check("f", "no fabricated 0.5 fallback", "pass",
                         "no undefined input is reported as a number."))


def check_integer_casts(report: Report, rows) -> None:
    offenders = []
    for row in rows:
        for rounded_col, exact_col in (("unc_start_years", "unc_start_years_exact"),
                                       ("unc_end_years", "unc_end_years_exact")):
            rounded, exact = num(row[rounded_col]), num(row[exact_col])
            if rounded is None or exact is None:
                continue
            if abs(rounded - exact) > TOL_INT_CAST:
                offenders.append({"findspot": label(row), "column": rounded_col,
                                  "rounded": rounded, "exact": exact})
    if offenders:
        report.add(Check("r", "integer casts agree with exact columns", "fail",
                         f"{len(offenders)} row(s) differ by more than half a year — "
                         "the two columns are not two views of one quantity.", offenders))
    else:
        report.add(Check("r", "integer casts agree with exact columns", "pass",
                         "every rounded whisker length is within half a year of its exact value."))


def report_epoch_drift(report: Report, rows) -> dict[str, Any]:
    """(l) — reported, never failed. The drift is a finding, not a defect."""
    mids, widths, sigmas, q_starts, q_ends = [], [], [], [], []
    for row in rows:
        mid = num(row["midpoint_year"])
        start, end = num(row["eff_start"]), num(row["eff_end"])
        if mid is None or start is None or end is None:
            continue
        mids.append(mid)
        widths.append(end - start)
        sigmas.append(num(row["sigma_eff"]))
        q_starts.append(num(row["q_start"]))
        q_ends.append(num(row["q_end"]))

    early = [w for m, w in zip(mids, widths) if m < 100]
    late = [w for m, w in zip(mids, widths) if m >= 100]
    facts = {
        "r_width_vs_year": pearson(mids, widths),
        "r_sigma_eff_vs_year": pearson(mids, sigmas),
        "r_q_start_vs_year": pearson(mids, q_starts),
        "r_q_end_vs_year": pearson(mids, q_ends),
        "median_width_before_ad100": median_or_none(early),
        "median_width_from_ad100": median_or_none(late),
        "n_before_ad100": len(early),
        "n_from_ad100": len(late),
    }
    r = facts["r_width_vs_year"]
    report.add(Check(
        "l", "epoch drift sits in the box width", "info",
        f"r(width, midpoint year) = {r:+.3f}; median width "
        f"{facts['median_width_before_ad100']:.1f} years before AD 100 against "
        f"{facts['median_width_from_ad100']:.1f} from AD 100. Later material is dated "
        f"less sharply because the chronological framework thins out — this belongs in "
        f"the width, and is the reason no epoch correction is applied to the colour.",
    ))
    return facts


def collect_facts(rows, params, drift: dict[str, Any]) -> dict[str, Any]:
    """Every number the documentation pages quote, computed once, here."""
    t0 = params["p_t0"]
    sigmas = [num(r[c]) for r in rows
              for c in ("unc_start_years_exact", "unc_end_years_exact")]
    sigmas = sorted(s for s in sigmas if s is not None)
    q_all = [math.exp(-s / t0) for s in sigmas]

    def q_at(years: float) -> float:
        return round(math.exp(-years / t0), 3)

    return {
        "n_findspots": len(rows),
        "parameters": {k[2:]: v for k, v in params.items()},
        "anchors": {
            "sharp_years": ANCHOR_SHARP_YEARS,
            "q_at_sharp": q_at(ANCHOR_SHARP_YEARS),
            "unusable_years": ANCHOR_UNUSABLE_YEARS,
            "q_at_unusable": q_at(ANCHOR_UNUSABLE_YEARS),
        },
        "sigma_spectrum": {
            "n": len(sigmas),
            "min": sigmas[0] if sigmas else None,
            "median": median_or_none(sigmas),
            "max": sigmas[-1] if sigmas else None,
        },
        "q_spectrum": {
            "min": round(min(q_all), 3) if q_all else None,
            "median": round(statistics.median(q_all), 3) if q_all else None,
            "max": round(max(q_all), 3) if q_all else None,
        },
        "epoch_drift": drift,
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def verify(path: Path) -> Report:
    report = Report(source=str(path))
    rows = load_rows(path)
    if not rows:
        report.add(Check("k", "column set", "fail", "the file holds no data rows."))
        return report
    if not check_columns(report, rows):
        return report

    check_row_count(report, rows)
    params = read_parameters(report, rows)
    if len(params) != len(PARAMETER_COLUMNS):
        return report

    check_k_eff(report, rows, params)
    check_interval_width(report, rows)
    check_q_from_sigma(report, rows, params)
    check_monotonic(report, rows)
    check_null_policy(report, rows)
    check_no_fabricated_fallback(report, rows)
    check_integer_casts(report, rows)
    drift = report_epoch_drift(report, rows)
    report.facts = collect_facts(rows, params, drift)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the IPS dated-sites CSV export against its own model.")
    parser.add_argument("csv", type=Path, help="the export to check")
    parser.add_argument("--json", type=Path, default=None,
                        help="write the machine-readable report here (for docu.py)")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as failures")
    parser.add_argument("--stamp", action="store_true",
                        help="record the run time in the report; off by default so "
                             "that repeated runs stay byte-identical")
    parser.add_argument("--quiet", action="store_true", help="print nothing")
    args = parser.parse_args(argv)

    if not args.csv.is_file():
        print(f"verify: no such file: {args.csv}", file=sys.stderr)
        return 2

    report = verify(args.csv)

    if not args.quiet:
        print(f"\nverify — {args.csv}\n")
        for check in report.checks:
            print(check.line())
        for check in report.checks:
            if check.offenders:
                print(f"\n  {check.key} — offending rows:")
                for entry in check.offenders[:10]:
                    print("    " + json.dumps(entry, ensure_ascii=False))
                if len(check.offenders) > 10:
                    print(f"    ... and {len(check.offenders) - 10} more")
        worst = max((STATUS_ORDER[c.status] for c in report.checks), default=0)
        verdict = {0: "all checks passed", 1: "passed with warnings", 2: "FAILED"}[worst]
        print(f"\n  {verdict} — {len(report.checks)} checks, "
              f"{len(report.failed)} failed, {len(report.warned)} warned\n")

    if args.json:
        payload = report.to_dict()
        if args.stamp:
            from datetime import datetime, timezone
            payload["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8")
        if not args.quiet:
            print(f"  report written to {args.json}\n")

    if report.failed:
        return 1
    if args.strict and report.warned:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
