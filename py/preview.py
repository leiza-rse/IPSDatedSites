"""
IPS Dated Sites — local preview of the published site
=====================================================

Serves docs/ over HTTP and opens it, so that the pages can be looked at
before they are pushed.

WHY THIS IS NOT JUST http.server
--------------------------------
docs/ is a Jekyll site and GitHub Pages builds it. What is on disk is not
what is published: the navigation points at /model.html, and the file
beside it is model.md. A plain static server therefore gives a site whose
every link is broken, which is worse than no preview at all — it looks
like a fault in the pages rather than in the server.

So this handler does the two things Jekyll does that matter here:

  * a request for /foo.html with only foo.md on disk renders the Markdown
  * an .html file that CARRIES FRONT MATTER is treated as a Jekyll page
    too: the front matter is stripped, {% raw %} blocks are removed, and
    the layout is applied. Serving those statically was the first version
    of this module and it was wrong — docs/map.html and every page under
    docs/query/ begin with a front-matter block, which a static server
    hands to the browser as visible text, with no layout and no navigation
    around it.
  * the result is wrapped in docs/_layouts/default.html, with the handful
    of Liquid constructs that layout actually uses substituted

AN APPROXIMATION, AND IT SAYS SO
--------------------------------
This is not Jekyll and does not try to be. Jekyll uses kramdown with GFM
input; this uses python-markdown if it is installed. They agree on
headings, paragraphs, lists, links and fenced code, and they disagree at
the edges — footnotes, attribute lists, some table corner cases. Mermaid
blocks are passed through as fenced code either way, because the diagrams
on the published site are rendered by CI into img/diagrams/ rather than in
the browser.

Every rendered page therefore carries a banner saying it is a preview.
Somebody comparing this against the live site should know which of the two
is authoritative, and the answer is never this one.

python-markdown is OPTIONAL and deliberately not added to
requirements.txt: it takes part in no build output, and pinning a
dependency that only ever affects a developer's own screen would make the
pinning mean less. Without it the .md pages are served as plain text with
a note; everything else — the map, the query pages, the companion pages,
the report — is real HTML and works either way.
"""

from __future__ import annotations

import http.server
import re
import socket
import socketserver
import sys
import threading
import webbrowser
from functools import partial
from pathlib import Path

BANNER = (
    '<div style="background:#fff4d6;border:1px solid #e0c97f;'
    'border-radius:6px;padding:.6rem .9rem;margin:0 0 1.2rem;'
    'font-size:.85rem;color:#6b5a20">'
    '<strong>Local preview.</strong> This page was rendered by '
    'py/preview.py, not by Jekyll. Markdown handling differs at the edges; '
    'the published site is what GitHub Pages builds.'
    '</div>'
)

NO_MARKDOWN = (
    '<div style="background:#fdecea;border:1px solid #e0a6a0;'
    'border-radius:6px;padding:.6rem .9rem;margin:0 0 1.2rem;'
    'font-size:.85rem;color:#7a2d24">'
    '<strong>Markdown not rendered.</strong> Install it with '
    '<code>pip install markdown</code> to preview the .md pages; the '
    'source is shown below. The HTML pages — map, query, companion pages '
    '— do not need it.'
    '</div>'
)


def _layout(docs: Path) -> str:
    """The Jekyll layout, or a minimal stand-in if it is missing."""
    path = docs / "_layouts" / "default.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "<!DOCTYPE html><meta charset=utf-8>{{ content }}"


def _site_title(docs: Path) -> str:
    config = docs / "_config.yml"
    if config.exists():
        for line in config.read_text(encoding="utf-8").splitlines():
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip()
    return "IPS dated sites"


def _apply_layout(layout: str, content: str, title: str,
                  site_title: str) -> str:
    """
    The four Liquid constructs docs/_layouts/default.html actually uses.

    Deliberately a substitution and not a Liquid engine. The layout is one
    file in this repository and it is read here; if it grows a construct
    this does not handle, the preview shows the raw {{ ... }} on screen,
    which is a visible failure rather than a silent one.
    """
    out = layout
    out = re.sub(r"\{\{\s*'([^']*)'\s*\|\s*relative_url\s*\}\}",
                 lambda m: m.group(1), out)
    out = re.sub(r'\{\{\s*"([^"]*)"\s*\|\s*relative_url\s*\}\}',
                 lambda m: m.group(1), out)
    out = out.replace("{{ site.title }}", site_title)
    out = out.replace("{{ page.title }}", title)
    out = out.replace("{{ content }}", content)
    # Front matter of the page itself, if the layout re-emits it.
    out = re.sub(r"\{\{.*?\}\}", "", out)
    out = re.sub(r"\{%.*?%\}", "", out, flags=re.S)
    return out


def _strip_front_matter(text: str) -> tuple[str, str]:
    """Return (body, title-from-front-matter)."""
    title = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            head = text[3:end]
            for line in head.splitlines():
                if line.strip().startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip("\"'")
            text = text[end + 4:].lstrip("\n")
    return text, title


def _render_markdown(source: str) -> tuple[str, bool]:
    try:
        import markdown
    except ImportError:
        return ("<pre style=\"white-space:pre-wrap\">"
                + source.replace("&", "&amp;").replace("<", "&lt;")
                + "</pre>"), False
    html = markdown.markdown(
        source, extensions=["tables", "fenced_code", "toc", "attr_list"])
    return html, True


class Handler(http.server.SimpleHTTPRequestHandler):
    """Static files, plus Markdown pages rendered the way Jekyll would."""

    def log_message(self, fmt, *args):        # noqa: A003
        # One line per file is noise on a preview; only failures matter.
        if not str(args[1] if len(args) > 1 else "").startswith(("2", "3")):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _jekyll_page(self) -> Path | None:
        """An .html file on disk that Jekyll would process rather than copy.

        Jekyll's rule, and the one used here: a file is a page if it starts
        with a front-matter block, and a static asset otherwise. That is why
        docs/docu/*.html and docs/query/closed-groups.html are served
        untouched — they are complete documents with their own styling —
        while the generated pages get the layout.
        """
        root = Path(self.directory)
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path.endswith("/"):
            path += "index.html"
        if not path.endswith(".html"):
            return None
        target = root / path.lstrip("/")
        try:
            target.relative_to(root)
        except ValueError:
            return None
        if not target.exists():
            return None
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            if fh.read(3) != "---":
                return None
        return target

    def _markdown_source(self) -> Path | None:
        """The .md that would become the requested URL, if there is one."""
        root = Path(self.directory)
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path.endswith("/"):
            path += "index.html"
        if not path.endswith(".html"):
            return None
        target = root / path.lstrip("/")
        if target.exists():
            return None
        candidate = target.with_suffix(".md")
        try:
            candidate.relative_to(root)
        except ValueError:                     # traversal attempt
            return None
        return candidate if candidate.exists() else None

    def do_GET(self):                          # noqa: N802
        docs = Path(self.directory)
        html_page = self._jekyll_page()
        if html_page is not None:
            text, fm_title = _strip_front_matter(
                html_page.read_text(encoding="utf-8"))
            # {% raw %} exists to stop Liquid eating the JavaScript on the
            # way to Pages. Jekyll consumes the markers; a static server
            # does not, and they end up on screen.
            text = re.sub(r"\{%\s*(end)?raw\s*%\}", "", text)
            page = _apply_layout(_layout(docs), BANNER + text,
                                 fm_title or html_page.stem,
                                 _site_title(docs))
            return self._send_html(page)

        source = self._markdown_source()
        if source is None:
            return super().do_GET()
        text, fm_title = _strip_front_matter(
            source.read_text(encoding="utf-8"))
        body, rendered = _render_markdown(text)
        title = fm_title or _first_heading(text) or source.stem
        page = _apply_layout(
            _layout(docs),
            (BANNER if rendered else NO_MARKDOWN) + body,
            title, _site_title(docs))
        return self._send_html(page)

    def _send_html(self, page: str) -> None:
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _first_heading(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _free_port(first: int, tries: int = 20) -> int:
    for port in range(first, first + tries):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"  !!  no free port between {first} and "
                     f"{first + tries - 1}.")


def serve(docs: Path, port: int = 8000, open_browser: bool = True) -> int:
    """Serve docs/ until Ctrl-C. Returns 0 on a clean stop."""
    if not docs.exists():
        print(f"  !!  {docs} does not exist — nothing to preview.")
        return 2
    try:
        import markdown                        # noqa: F401
        note = ""
    except ImportError:
        note = ("  Markdown pages will be shown as source. "
                "'pip install markdown' renders them.\n")

    port = _free_port(port)
    url = f"http://127.0.0.1:{port}/"
    handler = partial(Handler, directory=str(docs))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"  Preview           : {url}")
        print(f"  Serving           : {docs}")
        if note:
            print(note, end="")
        print("  Stop with Ctrl-C.")
        if open_browser:
            # In a thread: the browser can take a moment to start, and on
            # Windows it sometimes returns only after the window is up.
            threading.Thread(target=webbrowser.open, args=(url,),
                             daemon=True).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Preview stopped.")
    return 0
