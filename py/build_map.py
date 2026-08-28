"""
IPS Dated Sites — the map, from the graph
=========================================

Two products from one SPARQL query, run at build time against the same
bundle the query page serves:

    docs/map.geojson    the findspots as points, with their intervals and
                        one normalised value and colour per axis
    docs/map.html       a Leaflet page that reads it

WHY GEOJSON AND NOT PYODIDE
---------------------------
docs/sparql.html parses the Turtle in the browser, which costs a Pyodide
download and some seconds of CPU. That is the right trade for a page whose
purpose is letting somebody edit a query and re-run it. It is the wrong
trade for a map, which people open on a phone to look at dots.

So the query runs here, once, and its result is published as GeoJSON — a
format every mapping tool already reads, which makes the file useful well
beyond this page. Nothing is hidden by that: the query is in queries.yaml,
it is printed on the page, and the same query can be re-run live next door
on the query page. The derivation stays checkable; only the moment it
happens moves.

WHAT THE POINTS ARE
-------------------
Discovery sites, not findspots. The source records one coordinate per
site, so the four Bregenz findspots share a position exactly. Drawing them
as four markers would invent a spatial distinction the data does not make;
they are collected into one marker whose popup lists the findspots
separately, each with its own interval and colour.

That is also why the marker's own colour is the MEDIAN of its findspots'
normalised values rather than a mean: at Bregenz one very sharply dated
context should not drag the site's colour across the ramp, and the median
is the summary that says "typical for this site" without inventing a
precision the aggregation does not have.

BYTE STABILITY
--------------
docs/ is compared byte for byte in CI, so the GeoJSON is written with
sorted keys, sorted features and fixed precision. Coordinates keep six
decimal places — about a tenth of a metre, far beyond what a Roman
findspot coordinate means, but the point is reproducibility rather than
accuracy.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"

# Pinned for the same reason PYODIDE_VERSION is pinned in build_sparql.py:
# an archived copy of this repository should still draw a map in ten years,
# and an unpinned CDN path follows whatever Leaflet ships next.
LEAFLET_VERSION = "1.9.4"
LEAFLET_SRI_JS = ("sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=")
LEAFLET_SRI_CSS = ("sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=")


def parse_wkt_point(literal: str) -> tuple[float, float] | None:
    """
    'POINT(lon lat)', optionally preceded by a CRS IRI, to (lon, lat).

    Deliberately not a WKT parser. The export writes exactly one shape and
    one CRS; anything else here is a sign that the graph changed, and
    returning None makes that visible as a missing marker rather than as a
    marker in the wrong hemisphere.
    """
    text = str(literal).strip()
    if text.startswith("<"):
        text = text.split(">", 1)[-1].strip()
    if not text.upper().startswith("POINT"):
        return None
    inside = text[text.find("(") + 1:text.rfind(")")]
    parts = inside.replace(",", " ").split()
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def collect(graph_file: Path, prefixes: str, sparql: str) -> tuple[list, list]:
    """Run the map query and fold the rows into one feature per site."""
    from rdflib import Graph

    g = Graph()
    g.parse(graph_file, format="turtle")
    rows = list(g.query(prefixes + "\n" + sparql))
    if not rows:
        sys.exit("  !!  the map query matches nothing — no map written.")

    axes = sorted({str(r.axis) for r in rows})
    sites: dict = {}
    for r in rows:
        point = parse_wkt_point(r.wkt)
        if point is None:
            continue
        site = str(r.site)
        entry = sites.setdefault(site, {
            "site": site, "point": point, "findspots": {}, "values": {},
        })
        fs = entry["findspots"].setdefault(str(r.findspot), {
            "findspot": str(r.findspot),
            "from": round(float(r["from"]), 1),
            "to": round(float(r.to), 1),
            "colours": {}, "values": {},
        })
        fs["colours"][str(r.axis)] = str(r.colour)
        fs["values"][str(r.axis)] = round(float(r.norm), 5)
        entry["values"].setdefault(str(r.axis), []).append(float(r.norm))

    features = []
    for site in sorted(sites):
        entry = sites[site]
        lon, lat = entry["point"]
        findspots = [entry["findspots"][k]
                     for k in sorted(entry["findspots"])]
        props = {
            "site": site,
            "findspots": findspots,
            "n_findspots": len(findspots),
            # One representative colour per axis for the marker itself.
            # Median rather than mean — see the module header.
            "median": {a: round(statistics.median(entry["values"][a]), 5)
                       for a in entry["values"]},
            "from": min(f["from"] for f in findspots),
            "to": max(f["to"] for f in findspots),
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": props,
        })
    return features, axes


def write_geojson(features: list, axes: list, path: Path, graph_url: str,
                  sparql: str) -> Path:
    doc = {
        "type": "FeatureCollection",
        # Not decoration. A GeoJSON that travels away from this repository
        # should still say where it came from and how, or it becomes one
        # more undated dot file with no provenance.
        "metadata": {
            "title": "Roman findspots dated by samian potters' stamps",
            "derivedFrom": graph_url,
            "generatedBy": "py/build_map.py",
            "query": sparql.strip(),
            "colourAxes": axes,
            "licence": "https://creativecommons.org/licenses/by/4.0/",
            "note": ("Positions are per discovery site, as the source "
                     "records them; several findspots of one site share "
                     "one point. Colours are presentation, computed from "
                     "the axes published in the graph."),
        },
        "features": features,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return path


def build(cfg: dict, docs: Path, env) -> list[Path]:
    map_cfg = cfg.get("map")
    if not map_cfg:
        return []
    graph_file = ROOT / cfg["graph"]["file"]
    features, axes = collect(graph_file, cfg["prefixes"], map_cfg["sparql"])

    geo_path = write_geojson(features, axes, docs / "map.geojson",
                             cfg["graph"]["url"], map_cfg["sparql"])

    axis_labels = map_cfg.get("axis_labels", {})
    html = env.get_template("map.html.j2").render(
        page=map_cfg, axes=axes, axis_labels=axis_labels,
        leaflet_version=LEAFLET_VERSION,
        leaflet_sri_js=LEAFLET_SRI_JS, leaflet_sri_css=LEAFLET_SRI_CSS,
        n_sites=len(features),
        n_findspots=sum(f["properties"]["n_findspots"] for f in features),
        sparql=map_cfg["sparql"].strip(),
        default_axis=map_cfg.get("default_axis", axes[0]),
        axes_json=json.dumps(axes),
        labels_json=json.dumps(axis_labels, ensure_ascii=False))
    html_path = docs / "map.html"
    html_path.write_text(html, encoding="utf-8")
    return [geo_path, html_path]
