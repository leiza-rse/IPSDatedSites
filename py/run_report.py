"""
IPS Dated Sites — the build report
==================================

Captures everything `py/main.py` prints and writes it out twice: as a plain
log for grepping and diffing, and as an HTML page in the house style that
gathers the run's provenance, its verification checks and its artefacts on
one screen.

    docs/run-report.txt     the terminal output, verbatim
    docs/run-report.html    the same, with the structure put back in

WHY docs/ AND NOT img/
----------------------
img/ holds figures, and every file there is referenced by the paper. A build
report is not a figure. docs/ is the published site and already carries
model.md, statistics.md and open-questions.md; the report belongs with
those, and lands on GitHub Pages where a reader can reach it. Pass
--report-out to put it elsewhere.

WHY THERE IS NO CLOCK IN IT
---------------------------
Byte-stability, the same discipline as the SVGs (SOURCE_DATE_EPOCH, a fixed
svg.hashsalt) and data/derived/verification.json, which likewise carries no
timestamp. A rebuild that changes nothing must leave `git status` clean,
because a repository where every rebuild dirties a file is one where nobody
reads the diff any more.

The report is therefore dated by the DATA, not by the run: it carries the
retrieval date from data/SNAPSHOT.json. That changes when the corpus
changes, which is the only time the report says anything new.

WHY A FAILED RUN STILL PRODUCES ONE
-----------------------------------
The report of a run that stopped is the one most worth having. main.py
writes it from a finally block, so an abort mid-pipeline still leaves the
log and the last known state on disk.
"""

from __future__ import annotations

import html
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MARKS = {"ok": ("pass", "#2f6b4f"), "!!": ("warn", "#b07d31"),
         "XX": ("fail", "#9e3b26"), "--": ("note", "#46525f")}

# Boxes, rules and the run's own banner lines: structure for a terminal,
# noise in a table.
RULE = re.compile(r"^[\u2500\u2550\-=]{6,}$")


class Tee(io.TextIOBase):
    """Write to the real stream and keep a copy.

    Not a redirect: the point is that the terminal still behaves exactly as
    before. Somebody watching a long build should not have to wait for a
    file to find out how it went.
    """

    def __init__(self, stream):
        self._stream = stream
        self._buffer: list[str] = []

    def write(self, text: str) -> int:
        self._buffer.append(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    @property
    def text(self) -> str:
        return "".join(self._buffer)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _artefacts(dirs: dict[str, Path]) -> list[tuple[str, str, int, int]]:
    """What the run left behind: label, directory, file count, total bytes."""
    out = []
    for label, path in dirs.items():
        if not path.exists():
            continue
        # The report itself is excluded. Counting it would make the file
        # describe its own size, which changes it, which changes the size —
        # and the byte-stability the rest of this module is built around
        # would be lost to a self-reference.
        files = [f for f in path.rglob("*")
                 if f.is_file() and not f.name.startswith("run-report.")]
        out.append((label, str(path.relative_to(ROOT)), len(files),
                    sum(f.stat().st_size for f in files)))
    return out


def _human(n: int) -> str:
    for unit in ("B", "kB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} MB"


def _checks(verification: dict) -> list[dict]:
    return verification.get("checks", []) or []


def render(log: str, verification: dict, snapshot: dict,
           artefacts: list, ok: bool) -> str:
    e = html.escape
    sources = snapshot.get("sources", {})
    retrieved = snapshot.get("retrieved", "unknown")
    origin = snapshot.get("origin", "unknown")
    crosscheck = snapshot.get("crosscheck", "unknown")

    counts = {"pass": 0, "warn": 0, "fail": 0, "info": 0}
    for check in _checks(verification):
        counts[check.get("status", "info")] = \
            counts.get(check.get("status", "info"), 0) + 1

    banner = ("All consistent" if ok else "Stopped")
    banner_colour = "#2f6b4f" if ok else "#9e3b26"

    rows = []
    for check in _checks(verification):
        status = check.get("status", "info")
        colour = {"pass": "#2f6b4f", "warn": "#b07d31",
                  "fail": "#9e3b26", "info": "#46525f"}.get(status, "#46525f")
        rows.append(
            f'<tr><td class="k">{e(str(check.get("key", "")))}</td>'
            f'<td>{e(str(check.get("title", "")))}</td>'
            f'<td class="s" style="color:{colour}">{e(status)}</td>'
            f'<td class="d">{e(str(check.get("detail", "")))}</td></tr>')

    source_rows = []
    for name, meta in sources.items():
        source_rows.append(
            f'<tr><td class="k">{e(name)}</td>'
            f'<td class="d">{e(str(meta.get("endpoint", "")))}</td>'
            f'<td class="n">{e(str(meta.get("records", "—")))}</td>'
            f'<td class="n">{_human(int(meta.get("bytes", 0)))}</td>'
            f'<td class="h">{e(str(meta.get("sha256", ""))[:16])}</td></tr>')

    artefact_rows = "".join(
        f'<tr><td class="k">{e(label)}</td><td class="d">{e(where)}</td>'
        f'<td class="n">{n}</td><td class="n">{_human(size)}</td></tr>'
        for label, where, n, size in artefacts)

    model = snapshot.get("model", {})
    model_row = "  ".join(f"{k} = {v}" for k, v in model.items()) or "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Build report — IPSDatedSites</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,600;0,700;1,400&family=Public+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --ink:#1b2430; --ink-soft:#46525f;
  --paper:#fbfaf7; --paper-2:#f2efe8;
  --slip:#9e3b26; --slip-tint:#f6e8e3;
  --rule:#d9d3c6;
}}
*{{box-sizing:border-box}}
body{{margin:0; background:var(--paper); color:var(--ink);
  font-family:'Public Sans',system-ui,sans-serif; font-size:15px; line-height:1.62}}
header{{background:var(--ink); border-bottom:3px solid var(--slip);
  padding:26px 32px; color:var(--paper)}}
header h1{{font-family:Spectral,Georgia,serif; font-size:1.7rem; margin:0 0 4px}}
header p{{margin:0; color:#b9c2cb; font-size:.9rem}}
main{{max-width:1080px; margin:0 auto; padding:28px 32px 64px}}
h2{{font-family:Spectral,Georgia,serif; font-size:1.22rem; margin:2.2rem 0 .6rem;
  padding-bottom:.3rem; border-bottom:1px solid var(--rule)}}
.banner{{display:inline-block; padding:5px 14px; border-radius:3px;
  background:{banner_colour}; color:var(--paper); font-weight:600;
  letter-spacing:.03em; font-size:.9rem}}
/* margin on the children rather than flex `gap`: older WebKit engines,
   which is what several PDF and screenshot tools still embed, ignore gap
   and run the whole line together into one word. */
.meta{{margin:14px 0 0; font-size:.9rem; color:var(--ink-soft)}}
.meta span{{display:inline-block; margin:0 26px 6px 0}}
.meta span + span{{border-left:1px solid var(--rule); padding-left:26px}}
.meta b{{color:var(--ink)}}
table{{width:100%; border-collapse:collapse; margin:.6rem 0 1.2rem; font-size:.88rem}}
th{{text-align:left; background:var(--paper-2); font-weight:600;
  padding:7px 10px; border-bottom:1px solid var(--rule)}}
td{{padding:7px 10px; border-bottom:1px solid var(--rule); vertical-align:top}}
td.k{{font-family:'IBM Plex Mono',monospace; white-space:nowrap; font-size:.84rem}}
td.s{{font-weight:600; white-space:nowrap}}
td.n{{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap}}
td.h{{font-family:'IBM Plex Mono',monospace; font-size:.78rem; color:var(--ink-soft)}}
td.d{{color:var(--ink-soft)}}
.tally{{font-family:'IBM Plex Mono',monospace; font-size:.86rem; color:var(--ink-soft)}}
pre{{background:var(--ink); color:#d6e0d9; padding:20px; overflow:auto;
  font-family:'IBM Plex Mono',monospace; font-size:.78rem; line-height:1.55;
  border-radius:4px; max-height:70vh}}
.note{{background:var(--slip-tint); border-left:3px solid var(--slip);
  padding:12px 16px; margin:1rem 0; font-size:.9rem}}
footer{{color:var(--ink-soft); font-size:.82rem; margin-top:2.5rem;
  border-top:1px solid var(--rule); padding-top:14px}}
</style>
</head>
<body>
<header>
  <h1>Build report</h1>
  <p>IPSDatedSites &middot; findspot dating from samian potters' stamps</p>
</header>
<main>

  <p><span class="banner">{e(banner)}</span></p>

  <div class="meta">
    <span>data retrieved <b>{e(str(retrieved))}</b></span>
    <span>read from <b>{e(str(origin))}</b></span>
    <span>cross-check <b>{e(str(crosscheck))}</b></span>
    <span>findspots <b>{e(str(snapshot.get('findspots', '—')))}</b></span>
  </div>

  <div class="note">
    This report carries no clock. It is dated by the data, not by the run, so
    that rebuilding an unchanged corpus leaves it byte-identical and a diff
    means something. The same reason the figures fix
    <code>SOURCE_DATE_EPOCH</code>.
  </div>

  <h2>Model</h2>
  <p class="tally">{e(model_row)}</p>

  <h2>Sources</h2>
  <table>
    <thead><tr><th>Resource</th><th>Endpoint</th><th>Records</th><th>Size</th><th>sha256</th></tr></thead>
    <tbody>{''.join(source_rows) or '<tr><td colspan="5">none recorded</td></tr>'}</tbody>
  </table>

  <h2>Verification</h2>
  <p class="tally">{counts.get('pass', 0)} pass &middot; {counts.get('warn', 0)} warn &middot; {counts.get('fail', 0)} fail &middot; {counts.get('info', 0)} note</p>
  <table>
    <thead><tr><th>Key</th><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="4">no checks recorded</td></tr>'}</tbody>
  </table>

  <h2>Artefacts</h2>
  <table>
    <thead><tr><th>What</th><th>Where</th><th>Files</th><th>Size</th></tr></thead>
    <tbody>{artefact_rows or '<tr><td colspan="4">none</td></tr>'}</tbody>
  </table>

  <h2>Terminal output</h2>
  <pre>{e(log)}</pre>

  <footer>
    Generated by <code>py/run_report.py</code> from the run of
    <code>py/main.py</code>. The plain log is beside this file as
    <code>run-report.txt</code>.
  </footer>
</main>
</body>
</html>
"""


def write(log: str, out_dir: Path, ok: bool) -> list[Path]:
    """Write both forms. Never raises: a report is not worth a failed build."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        verification = _read_json(ROOT / "data" / "derived" / "verification.json")
        snapshot = _read_json(ROOT / "data" / "SNAPSHOT.json")
        artefacts = _artefacts({
            "RDF": ROOT / "rdf",
            "Figures": ROOT / "img",
            "Documentation": ROOT / "docs",
            "Browser emitter": ROOT / "webjs",
            "Data": ROOT / "data",
        })

        txt = out_dir / "run-report.txt"
        txt.write_text(log, encoding="utf-8", newline="\n")

        page = out_dir / "run-report.html"
        page.write_text(render(log, verification, snapshot, artefacts, ok),
                        encoding="utf-8", newline="\n")
        return [page, txt]
    except OSError as exc:
        print(f"  !!  the report could not be written: {exc}",
              file=sys.__stderr__)
        return []
