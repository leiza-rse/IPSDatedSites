"""
IPS Dated Sites — RDF export
============================

Reads the CSV produced by sql/IPSDatedSites.sql and builds a knowledge
graph from it in Turtle / JSON-LD.

The graph is *constructed* with rdflib rather than glued together as text.
That rules out, by construction, the whole class of faults the earlier
exporter suffered from: invalid literals such as 0.0953^^xsd:decimal,
broken escapes, unterminated statements.

THREE LAYERS
------------
  1. PLACE & FINDSPOT   — what exists in the world
       samian:loc_ds_<id>          already published, only referenced here
       samian:fs_<id>_<slug>       findspot, crm:P89_falls_within place

  2. DATING             — the substantive claim
       samian:ts_<id>_<slug>       lado:FindspotDating
                                   -> crm:E52_Time-Span, time:ProperInterval
       carries eff_start/eff_end (as OWL-Time time positions), sigma, k,
       n, D, r, q_interval, q_repetition, q_start, q_end, avg/min/max

  3. PRESENTATION       — what the figure makes of it
       samian:plotrow_<id>_<slug>  lado:PlotRow, lado:renders -> time-span
                                   carries unc_* ("visual only" per the docs)
       samian:fig_<name>           lado:Figure, the figure constants

  + PROV: DatingModel (prov:Plan) with k_min/k_max/tau/w, one prov:Activity
    per row, plus agent, source dataset and the documented filter.

THE NULL CONTRACT
-----------------
Where a value is missing the triple is OMITTED — never 0 or 0.5 asserted.
So that absence is not mistaken for "not computed yet", the export also
writes an explicit marker:
    <ts> lado:undefinedMeasure lado:qInterval .

Direct use (Windows / VS Code):
    python py/ips_rdf_export.py --csv data/data.csv --out rdf

Normally not called directly, but through py/main.py.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.namespace import DCTERMS, SKOS, XSD

from ips_compat import silence_gyear_warnings
from ips_docs_text import TERM_DOCS

# rdflib < 7.5 cannot convert pre-Christian xsd:gYear into a Python date
# and writes a traceback per literal. The literals themselves are correct;
# the reasoning and the evidence are in ips_compat.py.
silence_gyear_warnings()

# --------------------------------------------------------------------------
# Namensraeume
# --------------------------------------------------------------------------
SAMIAN = Namespace("http://data.archaeology.link/data/samian/")
LADO = Namespace("http://archaeology.link/ontology#")
CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
TIME = Namespace("http://www.w3.org/2006/time#")
PROV = Namespace("http://www.w3.org/ns/prov#")  # KORREKT. Die publizierte
# loc_discoverysite_1.ttl wrongly binds prov: to .../ns/prov-o/ , which
# leaves all six PROV predicates there pointing nowhere. Do not copy it.
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
# CRMdig — the CIDOC CRM extension for digital provenance. The namespace is
# the one assigned by FORTH, checked against the official v4.0 definition and
# against OntoME, because a guessed-wrong namespace is precisely the defect
# we criticise in the 2019 file.
CRMDIG = Namespace("http://www.ics.forth.gr/isl/CRMdig/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
PLEIADES = Namespace("https://pleiades.stoa.org/places/")

TRS_GREGORIAN = URIRef("http://www.opengis.net/def/uom/ISO-8601/0/Gregorian")
# A time reference system of our own for the number line the source
# computes on. See numeric_year() for the reasoning.
TRS_IPS = SAMIAN["trs_ips_year"]

PREFIXES = {
    "samian": SAMIAN, "lado": LADO, "crm": CRM, "time": TIME, "prov": PROV,
    "geo": GEO, "dcat": DCAT, "dcterms": DCTERMS, "skos": SKOS,
    "crmdig": CRMDIG,
    "pleiades": PLEIADES, "owl": OWL, "xsd": XSD,
}

# --------------------------------------------------------------------------
# Relations between the classes
# --------------------------------------------------------------------------
# These predicates used to sit inline in build_graph() only, which made them
# invisible to the documentation: a generated diagram would have had to copy
# them out and would have gone wrong at the first restructuring. Now they are
# declared once; build_graph() AND make_diagrams.py
# benutzen dieselben Namen.
P_FALLS_WITHIN  = CRM.P89_falls_within
P_HAS_TIME_SPAN = CRM["P4_has_time-span"]

# (subject class, predicate, object class) — the skeleton of the graph.
RELATIONS = [
    (LADO.Findspot,       P_FALLS_WITHIN,      LADO.DiscoverySite),
    (LADO.Findspot,       P_HAS_TIME_SPAN,     LADO.FindspotDating),
    (LADO.FindspotDating, TIME.hasBeginning,   TIME.Instant),
    (LADO.FindspotDating, TIME.hasEnd,         TIME.Instant),
    (TIME.Instant,        TIME.inTimePosition, TIME.TimePosition),
    (TIME.TimePosition,   TIME.hasTRS,         TIME.TRS),
    (LADO.PlotRow,        LADO.renders,        LADO.FindspotDating),
    (LADO.Figure,         LADO.hasRow,         LADO.PlotRow),
    (LADO.FindspotDating, PROV.wasGeneratedBy, LADO.DatingActivity),
    (LADO.DatingActivity, PROV.hadPlan,        LADO.DatingModel),
    (LADO.FindspotDating, PROV.wasDerivedFrom, DCAT.Dataset),
]

# Which layer does a class belong to? Drives the grouping in the diagrams
# and makes the separation checkable rather than merely asserted.
LAYERS = {
    LADO.DiscoverySite:  "place",
    LADO.Findspot:       "place",
    LADO.DatedTimeSpan:  "dating",
    LADO.FindspotDating: "dating",
    LADO.DatingModel:    "provenance",
    LADO.DatingActivity: "provenance",
    LADO.PlotRow:        "presentation",
    LADO.Figure:         "presentation",
    LADO.Location:       "place",
}
LAYER_LABELS = {
    "place":        "1 — place and findspot",
    "dating":       "2 — the dating",
    "presentation": "3 — presentation",
    "provenance":   "provenance",
}


# --------------------------------------------------------------------------
# Figure constants (from IPSDatedSites27.cfm)
# --------------------------------------------------------------------------
FIGURE_CONSTANTS = {
    "padYears": (60, XSD.integer),            # Z. 373
    "extremeStubYears": (10, XSD.integer),    # Z. 472
    "rowHeight": (36, XSD.integer),           # Z. 335
    "svgWidth": (1200, XSD.integer),
    "marginLeft": (400, XSD.integer),
    "marginRight": (260, XSD.integer),
    "marginTop": (40, XSD.integer),
    "marginBottom": (120, XSD.integer),
    "bandPadding": (Decimal("0.4"), XSD.decimal),
    "colourRamp": ("interpolateRdYlGn", XSD.string),
    "rowOrder": ("avg_datemin ASC", XSD.string),
}

# The end-date filter from the source query.
EXCLUDED_DATEMAX = [260, 120, 150]

# --------------------------------------------------------------------------
# Slug — Transliteration VOR Normalisierung
# --------------------------------------------------------------------------
# Plain NFD/NFKD is not enough for German: 'ß' has no decomposition at all
# and would simply vanish ("Emmeranstraße" -> "emmeranstrae"). And in
# JavaScript \w is ASCII-only, which is why the old v5 exporter turned
# "Köln" ein "kln" gemacht hat. Beides faengt diese Tabelle ab.
TRANSLIT = {
    "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    "ß": "ss", "æ": "ae", "Æ": "Ae", "ø": "oe", "Ø": "Oe",
    "å": "aa", "Å": "Aa", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
    "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D", "œ": "oe", "Œ": "Oe",
}


def slug(text: str) -> str:
    """Stabiler, verlustarmer ASCII-Slug."""
    s = str(text).strip()
    s = "".join(TRANSLIT.get(c, c) for c in s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s or "unknown"


# The recipe for the findspot key. A later JavaScript port must reproduce
# it CHARACTER FOR CHARACTER, otherwise the two implementations point at
# different URIs.
KEY_ALGORITHM = "sha256(NFC(trim(findspot)))[0:6], per discovery-site id"


def findspot_hash(findspot: str) -> str:
    """
    A six-character hash of the findspot name.

    NFC normalisation is not cosmetic here: if the source delivers 'ö' once
    as U+00F6 and once as 'o'+U+0308, the same findspot would otherwise
    receive two different hashes. In JavaScript this corresponds to
    str.normalize("NFC") before hashing.
    """
    raw = unicodedata.normalize("NFC", str(findspot).strip())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6]


def build_keys(df: pd.DataFrame, mode: str) -> dict:
    """(the_id, findspot) -> URI fragment. Checks for collisions."""
    keys, seen = {}, {}
    for _, r in df.iterrows():
        sid = int(r.the_id)
        frag = (findspot_hash(r.the_findspot) if mode == "hash"
                else slug(r.the_findspot))
        pair = (sid, str(r.the_findspot))
        keys[pair] = frag
        prev = seen.setdefault((sid, frag), str(r.the_findspot))
        if prev != str(r.the_findspot):
            raise SystemExit(
                f"URI collision at discovery site {sid}: '{prev}' and "
                f"'{r.the_findspot}' ergeben beide '{frag}'.")
    return keys


# --------------------------------------------------------------------------
# Literal-Helfer
# --------------------------------------------------------------------------
def isna(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v)


def dec(v) -> Literal:
    """xsd:decimal ohne Fliesskomma-Artefakte."""
    return Literal(Decimal(str(v)), datatype=XSD.decimal)


def integer(v) -> Literal:
    return Literal(int(v), datatype=XSD.integer)


def gyear(year_db: float, era: str) -> Literal:
    """
    Whole year -> xsd:gYear.

    era='historical'   : -40 in the database means 40 BC — confirmed for the
                         IPS database. xsd:gYear counts astronomically
                         (year 0 = 1 BC), so -40 -> -0039.
    era='astronomical' : the database value is already astronomical, passed
                         through unchanged.
    """
    y = int(round(year_db))
    if era == "historical" and y < 0:
        y += 1
    sign = "-" if y < 0 else ""
    return Literal(f"{sign}{abs(y):04d}", datatype=XSD.gYear)


def numeric_year(value: float) -> Decimal:
    """
    Decimal year — UNCHANGED from the source.

    Deliberately without era conversion. The source computes
    eff = m +/- k*sigma on a continuous number line; a '+1 for negative
    values only' would jump from -0.5 to +0.5, would not be invertible, and
    would destroy the arithmetic the value comes from.

    The era convention therefore belongs on the CALENDAR LABEL
    (time:inXSDgYear), not on the position on the number line. The number
    line itself gets a documented time reference system of its own
    (samian:trs_ips_year) rather than passing silently as Gregorian.
    """
    return Decimal(str(value))


# --------------------------------------------------------------------------
# Ontologie-Erweiterung (LADO)
# --------------------------------------------------------------------------
# Classes hang under CIDOC CRM through several steps. The existing LADO
# classes of the published data are anchored in CRM here after the fact,
# WITHOUT retyping the published instances.
CLASSES = [
    # (Klasse, Oberklassen, Label, Kommentar)
    (LADO.Location, [CRM.E53_Place], "Location",
     "Bestehende LADO-Klasse, hier in CIDOC CRM verankert."),
    (LADO.DiscoverySite, [LADO.Location], "Discovery site",
     "Bestehende LADO-Klasse aus loc_discoverysite_1.ttl."),
    (LADO.Findspot, [LADO.Location], "Findspot",
     "Benannte Fundstelle innerhalb eines Fundplatzes. Faellt ueber "
     "crm:P89_falls_within in die DiscoverySite. Ein Fundplatz kann "
     "mehrere Fundstellen tragen (Bregenz: sechs)."),
    (LADO.DatedTimeSpan, [CRM["E52_Time-Span"], TIME.ProperInterval],
     "Dated time-span",
     "Zeitspanne, die aus datiertem Material erschlossen wurde."),
    (LADO.FindspotDating, [LADO.DatedTimeSpan], "Findspot dating",
     "Datierung einer Fundstelle aus Toepferstempeln. Das Intervall ist "
     "ein 'virtual fuzzy year' m +/- k*sigma, KEIN Konfidenzintervall."),
    (LADO.DatingInstant, [TIME.Instant, CRM["E52_Time-Span"]],
     "Dating instant",
     "Eine Intervallgrenze. Eigene Anwendungsklasse, damit sie in CIDOC "
     "CRM verankert werden kann, ohne eine Behauptung ueber time:Instant "
     "im Allgemeinen aufzustellen: crm:E52_Time-Span ist der CRM-Begriff "
     "fuer eine zeitliche Ausdehnung, hier eine von der Dauer null."),
    (LADO.DatingTimePosition, [TIME.TimePosition, CRM.E54_Dimension],
     "Dating time position",
     "Die Zahlenangabe einer Intervallgrenze auf einer benannten Skala. "
     "Strukturell eine crm:E54_Dimension: ein Wert plus das System, in "
     "dem er zu lesen ist — time:numericPosition entspricht P90 has "
     "value, time:hasTRS entspricht P91 has unit."),
    (LADO.YearScale, [TIME.TRS, CRM.E73_Information_Object],
     "Year scale",
     "Das Zeitreferenzsystem, auf dem die Zahlenangaben liegen. Eine "
     "dokumentierte Konvention und damit ein crm:E73_Information_Object."),
    (LADO.DatingModel, [PROV.Plan, CRM.E29_Design_or_Procedure],
     "Dating model",
     "Parametrisierung, aus der die Intervalle berechnet wurden. "
     "Haengt an prov:Plan UND an crm:E29_Design_or_Procedure: sonst waere "
     "dies die einzige lokale Klasse, die CIDOC CRM nicht erreicht, und "
     "ein rein CRM-basierter Konsument saehe die Methode nicht, aus der "
     "die Datierungen stammen."),
    (LADO.DatingActivity, [PROV.Activity, CRMDIG.D10_Software_Execution],
     "Dating activity",
     "Der Rechenlauf, der eine Datierung erzeugt hat. Haengt an "
     "crmdig:D10_Software_Execution, weil dessen Scope Note genau das "
     "beschreibt: ein Lauf, der vollstaendig durch seine digitale "
     "Eingabe, die Software und die Eigenschaften der Maschine bestimmt "
     "ist. CRMdig hat die Ausrichtung auf CIDOC CRM bereits gemacht, "
     "ueber D7 und E11/E65 bis E7_Activity — das ist tragfaehiger, als "
     "selbst zu entscheiden, ob ein Skriptlauf eine E7_Activity ist."),
    (LADO.Figure, [CRM.E36_Visual_Item], "Figure",
     "Abbildung. Traegt die Konstanten, die nicht zu den Fundplaetzen "
     "gehoeren, sondern zur Grafik."),
    (LADO.PlotRow, [CRM.E36_Visual_Item], "Plot row",
     "Darstellungsschicht einer Datierung. Traegt ausdruecklich die "
     "Groessen, die laut Methodendoku 'visual only' sind."),
]

# --------------------------------------------------------------------------
# Restated axioms of foreign vocabularies
# --------------------------------------------------------------------------
# These triples belong to CRMdig, not to us. They are here so that the
# standalone bundle answers CIDOC CRM queries even when CRMdig has not been
# loaded alongside: the materialisation in make_bundle.py follows the axioms
# present IN THE GRAPH, and without these the chain stops at
# crmdig:D10_Software_Execution.
#
# They are restatements, not new claims — looked up in the official CRMdig
# v4.0 definition (Table 1: Class Hierarchy) and in the
# CIDOC-CRM-Klassenhierarchie. Wer CRMdig ohnehin laedt, bekommt dieselben
# triples twice over, and therefore nothing new at all.
EXTERNAL_AXIOMS = [
    (CRMDIG.D10_Software_Execution, CRMDIG.D7_Digital_Machine_Event),
    (CRMDIG.D7_Digital_Machine_Event, CRM.E11_Modification),
    (CRMDIG.D7_Digital_Machine_Event, CRM.E65_Creation),
    (CRM.E11_Modification, CRM.E7_Activity),
    (CRM.E65_Creation, CRM.E7_Activity),
    (CRMDIG.D14_Software, CRMDIG.D1_Digital_Object),
    (CRMDIG.D1_Digital_Object, CRM.E73_Information_Object),
]


# (Property, Domain, Range, Label, Kommentar)
OBJ_PROPS = [
    (LADO.renders, LADO.PlotRow, LADO.DatedTimeSpan, "renders",
     "Verbindet eine Plotzeile mit der Datierung, die sie darstellt."),
    (LADO.hasRow, LADO.Figure, LADO.PlotRow, "has row", ""),
    (LADO.undefinedMeasure, LADO.DatedTimeSpan, RDF.Property,
     "undefined measure",
     "Benennt eine Groesse, die fuer diese Zeitspanne nicht berechenbar "
     "war. Macht Abwesenheit explizit, statt sie der Open-World-Annahme "
     "zu ueberlassen."),
]

DATA_PROPS = [
    # Messschicht — Zeitspanne
    (LADO.nStamps, LADO.DatedTimeSpan, XSD.integer, "number of stamps",
     "Anzahl Stempel an der Fundstelle (count_stamps)."),
    (LADO.nStampsWithDie, LADO.DatedTimeSpan, XSD.integer,
     "number of stamps with a die",
     "ACHTUNG: das n der k-Formel. Zaehlt nur Stempel mit Die-Angabe und "
     "ist NICHT nStamps."),
    (LADO.nDies, LADO.DatedTimeSpan, XSD.integer, "number of dies", ""),
    (LADO.dieRepetition, LADO.DatedTimeSpan, XSD.decimal, "die repetition",
     "nStampsWithDie / nDies. Depot-Indikator."),
    (LADO.qRepetition, LADO.DatedTimeSpan, XSD.decimal, "q repetition",
     "1 - 1/rep. Zweite Qualitaetsachse. Bewusst NICHT mit qInterval "
     "verrechnet: 'kein Depot' ist nicht 'schlecht datiert'."),
    (LADO.qInterval, LADO.DatedTimeSpan, XSD.decimal, "q interval",
     "Datierungsschaerfe (= q_spread). Erste Qualitaetsachse."),
    (LADO.qStart, LADO.DatedTimeSpan, XSD.decimal, "q start",
     "Sharpness of the start date, exp(-sigma / referenceLength). The "
     "denominator is a fixed length, not a calendar value, so the "
     "measure no longer depends on where in the calendar the material "
     "sits."),
    (LADO.qEnd, LADO.DatedTimeSpan, XSD.decimal, "q end",
     "As qStart, for the end date."),
    (LADO.sigmaYears, LADO.DatedTimeSpan, XSD.decimal, "sigma (years)",
     "sqrt( AVG(Breite^2/12) + VAR_SAMP(Mitten) ). Varianzzerlegung: "
     "innere Fuzziness plus Streuung der Intervallmitten."),
    (LADO.kFactor, LADO.DatedTimeSpan, XSD.decimal, "k factor",
     "k = k_max - (k_max-k_min)*(1-exp(-n/tau)), rein volumenbasiert."),
    (LADO.kIsFallback, LADO.DatedTimeSpan, XSD.boolean, "k is fallback",
     "true = keine Die-Angabe, k wurde auf k_max gesetzt. Modell"
     "verhalten, kein Messwert."),
    (LADO.midpointYear, LADO.DatedTimeSpan, XSD.decimal, "midpoint year", ""),
    (LADO.avgDatemin, LADO.DatedTimeSpan, XSD.integer, "average datemin", ""),
    (LADO.avgDatemax, LADO.DatedTimeSpan, XSD.integer, "average datemax", ""),
    (LADO.minDatemin, LADO.DatedTimeSpan, XSD.integer, "minimum datemin", ""),
    (LADO.maxDatemin, LADO.DatedTimeSpan, XSD.integer, "maximum datemin", ""),
    (LADO.minDatemax, LADO.DatedTimeSpan, XSD.integer, "minimum datemax", ""),
    (LADO.maxDatemax, LADO.DatedTimeSpan, XSD.integer, "maximum datemax", ""),
    (LADO.intervalLabel, LADO.DatedTimeSpan, XSD.string, "interval label",
     "Textform aus der Query (avg_interval)."),
    # Darstellungsschicht — Plotzeile
    (LADO.uncStartYears, LADO.PlotRow, XSD.integer,
     "uncertainty start (years)",
     "VISUAL ONLY. STDDEV_SAMP(datemin). Laut Methodendoku die Streuung "
     "von nichts im Modell; deshalb an der Plotzeile, nicht an der "
     "Zeitspanne."),
    (LADO.uncEndYears, LADO.PlotRow, XSD.integer,
     "uncertainty end (years)", "VISUAL ONLY. Siehe uncStartYears."),
    (LADO.uncIntervalYears, LADO.PlotRow, XSD.integer,
     "uncertainty interval (years)", "VISUAL ONLY."),
    # Model
    (LADO.kMin, LADO.DatingModel, XSD.decimal, "k min", ""),
    (LADO.kMax, LADO.DatingModel, XSD.decimal, "k max", ""),
    (LADO.tau, LADO.DatingModel, XSD.decimal, "tau",
     "Saettigungskonstante. Bei n = tau sind rund 63 % der moeglichen "
     "Verschmaelerung erreicht."),
    (LADO.volumeWeight, LADO.DatingModel, XSD.decimal, "volume weight",
     "w = 1.0: k haengt rein am Volumen."),
    (LADO.referenceLength, LADO.DatingModel, XSD.decimal,
     "reference length",
     "Called t0 in sql/IPSDatedSites.sql. The common time scale against "
     "which qStart and qEnd are read: q = exp(-sigma / referenceLength). "
     "A fixed length rather than a calendar value, which is what makes "
     "the measure independent of where in the calendar the material "
     "sits. Anchored on expert thresholds: sigma = 5 years counts as a "
     "sharp dating, sigma = 25 years as an unusable one."),
    (LADO.fuzzinessDivisor, LADO.DatingModel, XSD.integer,
     "fuzziness divisor",
     "12 = Varianz der Gleichverteilung. Die Verteilungsannahme pro "
     "Stempel steckt hier."),
    (LADO.excludedDatemax, LADO.DatingModel, XSD.integer,
     "excluded datemax value",
     "Filter p.datemax NOT IN (...) aus der Quell-Query. Bedeutung "
     "ungeklaert. Der Filter ist nicht neutral: er entfernt die "
     "betroffenen Toepfer an ALLEN Fundplaetzen."),
    (LADO.identifierScheme, DCAT.Dataset, XSD.string, "identifier scheme",
     "Rezept, nach dem die Fundstellen-Fragmente gebildet werden. Muss "
     "von jeder weiteren Implementierung zeichengenau reproduziert "
     "werden, sonst entstehen abweichende URIs."),
    (LADO.eraConvention, LADO.DatingModel, XSD.string, "era convention",
     "Wie negative Jahreszahlen der Quelle zu lesen sind."),
    # Figur
    (LADO.padYears, LADO.Figure, XSD.integer, "pad years", ""),
    (LADO.extremeStubYears, LADO.Figure, XSD.integer, "extreme stub years", ""),
    (LADO.rowHeight, LADO.Figure, XSD.integer, "row height", ""),
    (LADO.svgWidth, LADO.Figure, XSD.integer, "svg width", ""),
    (LADO.marginLeft, LADO.Figure, XSD.integer, "margin left", ""),
    (LADO.marginRight, LADO.Figure, XSD.integer, "margin right", ""),
    (LADO.marginTop, LADO.Figure, XSD.integer, "margin top", ""),
    (LADO.marginBottom, LADO.Figure, XSD.integer, "margin bottom", ""),
    (LADO.bandPadding, LADO.Figure, XSD.decimal, "band padding", ""),
    (LADO.colourRamp, LADO.Figure, XSD.string, "colour ramp", ""),
    (LADO.rowOrder, LADO.Figure, XSD.string, "row order",
     "Sortierregel der Zeilen. Erlaubt es, die Reihenfolge der Abbildung "
     "aus dem Graphen zu reproduzieren."),
]


def _local(term) -> str:
    t = str(term)
    return t.split("#")[-1] if "#" in t else t.rsplit("/", 1)[-1]


def _describe(g: Graph, term) -> None:
    """
    Attach the English rdfs:comment from TERM_DOCS.

    The same text source feeds the generated documentation under docs/, so a
    definition cannot be right in one half and stale in the other. For
    inclusion in a shared knowledge graph an English definition is required
    in any case.
    """
    text = TERM_DOCS.get(_local(term))
    if text:
        g.add((term, RDFS.comment, Literal(text, lang="en")))


def build_ontology() -> Graph:
    g = Graph()
    for p, ns in PREFIXES.items():
        g.bind(p, ns)

    onto = URIRef("http://archaeology.link/ontology")
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((onto, RDFS.label, Literal(
        "LADO — Erweiterung fuer Fundstellen-Datierung", lang="de")))
    g.add((onto, RDFS.comment, Literal(
        "Erweitert LADO um Fundstellen, Datierungs-Zeitspannen und eine "
        "getrennte Darstellungsschicht. Alle Klassen haengen ueber "
        "rdfs:subClassOf unter CIDOC CRM.", lang="de")))

    for cls, supers, label, comment in CLASSES:
        g.add((cls, RDF.type, OWL.Class))
        g.add((cls, RDFS.label, Literal(label, lang="en")))
        g.add((cls, RDFS.isDefinedBy, onto))
        for s in supers:
            g.add((cls, RDFS.subClassOf, s))
        if comment:
            g.add((cls, RDFS.comment, Literal(comment, lang="de")))
        _describe(g, cls)

    # Restated foreign axioms, so that the bundle resolves without CRMdig.
    g.add((onto, RDFS.comment, Literal(
        "Contains a small number of rdfs:subClassOf axioms that belong to "
        "CRMdig and to CIDOC CRM rather than to this vocabulary. They are "
        "restated so that the standalone bundle resolves CIDOC CRM "
        "queries without those ontologies being loaded; they assert "
        "nothing new.", lang="en")))
    for sub, sup in EXTERNAL_AXIOMS:
        g.add((sub, RDFS.subClassOf, sup))

    for prop, dom, rng, label, comment in OBJ_PROPS:
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.domain, dom))
        g.add((prop, RDFS.range, rng))
        g.add((prop, RDFS.label, Literal(label, lang="en")))
        g.add((prop, RDFS.isDefinedBy, onto))
        if comment:
            g.add((prop, RDFS.comment, Literal(comment, lang="de")))
        _describe(g, prop)

    for prop, dom, rng, label, comment in DATA_PROPS:
        g.add((prop, RDF.type, OWL.DatatypeProperty))
        g.add((prop, RDFS.domain, dom))
        g.add((prop, RDFS.range, rng))
        g.add((prop, RDFS.label, Literal(label, lang="en")))
        g.add((prop, RDFS.isDefinedBy, onto))
        if comment:
            g.add((prop, RDFS.comment, Literal(comment, lang="de")))
        _describe(g, prop)
    return g


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def build_graph(df: pd.DataFrame, era: str, figure_name: str,
                emit_geometry: bool, key_mode: str = "hash") -> Graph:
    g = Graph()
    for p, ns in PREFIXES.items():
        g.bind(p, ns)

    now_dt = datetime.now(timezone.utc)
    now = Literal(now_dt.isoformat(timespec="seconds"), datatype=XSD.dateTime)
    snapshot = now_dt.strftime("%Y-%m-%d")
    keys = build_keys(df, key_mode)

    # ---- Agent, model, source, dataset ----------------------------------
    agent = SAMIAN.IPSDatedSitesExporter
    g.add((agent, RDF.type, PROV.SoftwareAgent))
    # The software itself is a digital object: through D14 and D1 the
    # agent reaches crm:E73_Information_Object.
    g.add((agent, RDF.type, CRMDIG.D14_Software))
    g.add((agent, RDFS.label, Literal("ips_rdf_export.py", lang="en")))

    # ---- Time reference system of the source ----------------------------
    g.add((TRS_IPS, RDF.type, TIME.TRS))
    g.add((TRS_IPS, RDF.type, LADO.YearScale))
    g.add((TRS_IPS, RDFS.label, Literal("IPS signed year scale", lang="en")))
    g.add((TRS_IPS, RDFS.comment, Literal(
        "Durchgehende Zahlengerade vorzeichenbehafteter Jahreszahlen, auf "
        "der die Quell-Query rechnet (eff = m +/- k*sigma). Wie negative "
        "Werte als Kalenderjahre zu lesen sind, sagt lado:eraConvention am "
        "Datierungsmodell; die daraus abgeleiteten Kalenderlabels stehen "
        "als time:inXSDgYear an den Instants. Die Position selbst wird "
        "NICHT umgerechnet, weil eine Verschiebung nur der negativen Werte "
        "die Skala bei 0 zerreissen wuerde.", lang="de")))
    g.add((TRS_IPS, SKOS.closeMatch, TRS_GREGORIAN))

    model = SAMIAN.DatingModel_v1
    g.add((model, RDF.type, LADO.DatingModel))
    g.add((model, RDFS.label, Literal(
        "Virtual fuzzy year, volume-based k (v1)", lang="en")))
    g.add((model, RDFS.comment, Literal(
        "eff = m +/- k*sigma. sigma aus Varianzzerlegung "
        "sqrt(AVG(w^2/12) + VAR(Mitten)). k rein volumenbasiert. "
        "Das Intervall ist ein archaeologisch motiviertes "
        "'virtual fuzzy year', ausdruecklich KEIN Konfidenzintervall.",
        lang="de")))
    r0 = df.iloc[0]
    g.add((model, LADO.kMin, dec(r0.p_k_min)))
    g.add((model, LADO.kMax, dec(r0.p_k_max)))
    g.add((model, LADO.tau, dec(r0.p_tau)))
    g.add((model, LADO.volumeWeight, dec(r0.p_w)))
    g.add((model, LADO.referenceLength, dec(r0.p_t0)))
    g.add((model, LADO.fuzzinessDivisor, integer(12)))
    g.add((model, LADO.eraConvention, Literal(era)))
    for v in EXCLUDED_DATEMAX:
        g.add((model, LADO.excludedDatemax, integer(v)))

    # The time-span URIs stay stable; their VALUE changes with the data.
    # What is citable is therefore the dated snapshot, not the individual
    # time-span.
    dataset = SAMIAN[f"dataset_{figure_name}_{snapshot}"]
    g.add((dataset, RDF.type, DCAT.Dataset))
    g.add((dataset, RDF.type, PROV.Entity))
    g.add((dataset, RDF.type, CRMDIG.D1_Digital_Object))
    g.add((dataset, DCTERMS.title, Literal(
        "Archaeological findspots dated by samian potters' stamps",
        lang="en")))
    g.add((dataset, DCTERMS.created, now))
    g.add((dataset, PROV.wasAttributedTo, agent))
    g.add((dataset, DCTERMS.source, Literal(
        "Samian Research / IPS, tbldistribution + tblpotter + "
        "v_discoverysite")))
    g.add((dataset, DCTERMS.issued, Literal(snapshot, datatype=XSD.date)))
    g.add((dataset, OWL.versionInfo, Literal(snapshot)))
    g.add((dataset, LADO.identifierScheme, Literal(KEY_ALGORITHM)))
    g.add((dataset, RDFS.comment, Literal(
        "Datierter Snapshot. Die Fundstellen- und Zeitspannen-URIs sind "
        "bewusst NICHT versioniert: sie bezeichnen dauerhaft dieselbe "
        "Fundstelle bzw. deren jeweils aktuelle Datierung. Aendern sich "
        "die Quelldaten, aendern sich die Werte unter derselben URI. Wer "
        "einen konkreten Stand zitieren will, zitiert diesen Datensatz.",
        lang="de")))

    # ---- Figur ----------------------------------------------------------
    figure = SAMIAN[f"fig_{figure_name}"]
    g.add((figure, RDF.type, LADO.Figure))
    g.add((figure, RDFS.label, Literal(
        "Archaeological sites dated by potters — box plot", lang="en")))
    g.add((figure, DCTERMS.isPartOf, dataset))
    for name, (value, dt) in FIGURE_CONSTANTS.items():
        lit = dec(value) if dt == XSD.decimal else Literal(value, datatype=dt)
        g.add((figure, LADO[name], lit))

    # ---- Rows -----------------------------------------------------------
    for _, r in df.iterrows():
        sid = int(r.the_id)
        fs_slug = slug(r.the_findspot)          # as skos:notation only
        key = f"{sid}_{keys[(sid, str(r.the_findspot))]}"

        place = SAMIAN[f"loc_ds_{sid}"]
        findspot = SAMIAN[f"fs_{key}"]
        ts = SAMIAN[f"ts_{key}"]
        row = SAMIAN[f"plotrow_{key}"]
        act = SAMIAN[f"act_dating_{key}"]

        # --- Place: reference only, do not reassert ---
        g.add((place, RDFS.label, Literal(str(r.the_site), lang="en")))
        if not isna(r.latinsitename):
            g.add((place, LADO.ancientName, Literal(str(r.latinsitename))))
        if not isna(r.pleiades):
            # The '.0' is already in the database; cast it away cleanly.
            g.add((place, LADO.pleiadesID,
                   PLEIADES[str(int(float(r.pleiades)))]))
        if emit_geometry and not isna(r.lat) and not isna(r["long"]):
            geom = SAMIAN[f"loc_ds_{sid}_geom_ips"]
            g.add((place, GEO.hasGeometry, geom))
            g.add((geom, GEO.asWKT, Literal(
                f"<http://www.opengis.net/def/crs/EPSG/0/4326> "
                f"POINT({r['long']} {r.lat})", datatype=GEO.wktLiteral)))

        # --- Findspot ---
        g.add((findspot, RDF.type, LADO.Findspot))
        g.add((findspot, RDFS.label, Literal(str(r.the_findspot))))
        g.add((findspot, SKOS.notation, Literal(fs_slug)))
        g.add((findspot, P_FALLS_WITHIN, place))
        g.add((findspot, P_HAS_TIME_SPAN, ts))

        # --- Zeitspanne ---
        g.add((ts, RDF.type, LADO.FindspotDating))
        g.add((ts, RDFS.label, Literal(
            f"{r.the_site} — {r.the_findspot}: "
            f"{round(r.eff_start)} to {round(r.eff_end)}", lang="en")))
        g.add((ts, PROV.wasGeneratedBy, act))

        begin = SAMIAN[f"ts_{key}_begin"]
        end = SAMIAN[f"ts_{key}_end"]
        g.add((ts, TIME.hasBeginning, begin))
        g.add((ts, TIME.hasEnd, end))
        for inst, value in ((begin, r.eff_start), (end, r.eff_end)):
            pos = URIRef(str(inst) + "_pos")
            g.add((inst, RDF.type, TIME.Instant))
            g.add((inst, RDF.type, LADO.DatingInstant))
            g.add((inst, TIME.inTimePosition, pos))
            g.add((pos, RDF.type, TIME.TimePosition))
            g.add((pos, RDF.type, LADO.DatingTimePosition))
            g.add((pos, TIME.hasTRS, TRS_IPS))
            g.add((pos, TIME.numericPosition, dec(numeric_year(value))))
            # Rounded as well, for consumers that understand calendar
            # years only. The exact position is in numericPosition.
            g.add((inst, TIME.inXSDgYear, gyear(value, era)))

        # CIDOC CRM's own time bounds. Without them a consumer that knows
        # only CRM finds the time-span but gets no year out of it: the data
        # would otherwise hang exclusively behind OWL-Time. P82a/P82b are
        # the outer bounds of the time-span, and that is exactly what
        # eff_start and eff_end are.
        #
        # Rounded to whole years, as time:inXSDgYear is. The exact position
        # stays in time:numericPosition; these two triples are the bridge
        # for CRM, not the authoritative statement.
        g.add((ts, CRM.P82a_begin_of_the_begin, gyear(r.eff_start, era)))
        g.add((ts, CRM.P82b_end_of_the_end, gyear(r.eff_end, era)))

        measures = [
            (LADO.nStamps, r.count_stamps, integer),
            (LADO.nStampsWithDie, r.n_stamps_die, integer),
            (LADO.nDies, r.n_dies, integer),
            (LADO.dieRepetition, r.die_repetition, dec),
            (LADO.qRepetition, r.q_repetition, dec),
            (LADO.qInterval, r.q_interval, dec),
            (LADO.qStart, r.q_start, dec),
            (LADO.qEnd, r.q_end, dec),
            (LADO.sigmaYears, r.sigma_eff, dec),
            (LADO.kFactor, r.k_eff, dec),
            (LADO.midpointYear, r.midpoint_year, dec),
            (LADO.avgDatemin, r.avg_datemin, integer),
            (LADO.avgDatemax, r.avg_datemax, integer),
            (LADO.minDatemin, r.min_datemin, integer),
            (LADO.maxDatemin, r.max_datemin, integer),
            (LADO.minDatemax, r.min_datemax, integer),
            (LADO.maxDatemax, r.max_datemax, integer),
        ]
        for prop, value, caster in measures:
            if isna(value):
                # THE NULL CONTRACT: no triple, but marked explicitly.
                g.add((ts, LADO.undefinedMeasure, prop))
            else:
                g.add((ts, prop, caster(value)))

        if not isna(r.avg_interval):
            g.add((ts, LADO.intervalLabel, Literal(str(r.avg_interval))))
        g.add((ts, LADO.kIsFallback,
               Literal(bool(r.k_is_fallback), datatype=XSD.boolean)))

        # --- Darstellungsschicht ---
        g.add((row, RDF.type, LADO.PlotRow))
        g.add((row, LADO.renders, ts))
        g.add((figure, LADO.hasRow, row))
        for prop, value in ((LADO.uncStartYears, r.unc_start_years),
                            (LADO.uncEndYears, r.unc_end_years),
                            (LADO.uncIntervalYears, r.unc_interval_years)):
            if isna(value):
                g.add((row, LADO.undefinedMeasure, prop))
            else:
                g.add((row, prop, integer(value)))

        # --- PROV ---
        g.add((act, RDF.type, PROV.Activity))
        g.add((act, RDF.type, LADO.DatingActivity))
        g.add((act, RDFS.label, Literal(
            f"Dating of {r.the_site} — {r.the_findspot}", lang="en")))
        g.add((act, PROV.wasAssociatedWith, agent))
        g.add((act, PROV.endedAtTime, now))
        g.add((act, PROV.used, dataset))
        # This used to be a prov:qualifiedAssociation with a blank node of
        # type prov:Association. That was the one instance in the graph
        # which could not be anchored in CIDOC CRM — a reification is not a
        # thing in the world, and CRM has no class for it.
        #
        # Replaced by two direct statements that say the same thing and are
        # valid in both vocabularies: prov:used, because a prov:Plan is also
        # a prov:Entity, and crm:P33_used_specific_technique, whose range is
        # exactly crm:E29_Design_or_Procedure.
        g.add((act, PROV.used, model))
        g.add((act, CRM.P33_used_specific_technique, model))
        g.add((act, CRM.P14_carried_out_by, agent))
        g.add((ts, PROV.wasDerivedFrom, dataset))

    return g


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="IPS Dated Sites: CSV -> RDF (Turtle / JSON-LD)")
    ap.add_argument("--csv", required=True, type=Path,
                    help="result CSV from sql/IPSDatedSites.sql")
    ap.add_argument("--out", default=Path("rdf"), type=Path,
                    help="output directory (default: rdf)")
    ap.add_argument("--era", choices=("historical", "astronomical"),
                    default="historical",
                    help="reading of negative years in the source. "
                         "historical: -40 = 40 v.Chr. (xsd:gYear -0039). "
                         "astronomical: -40 = xsd:gYear -0040.")
    ap.add_argument("--findspot-uri", choices=("hash", "slug"),
                    default="hash",
                    help="how the findspot fragment is formed. "
                         "hash: six characters from the name (default). "
                         "slug: readable transliteration.")
    ap.add_argument("--figure-name", default="sites_dating_v1")
    ap.add_argument("--emit-geometry", action="store_true",
                    help="emit the IPS coordinates as well. Off by default, "
                         "weil loc_discoverysite_1.ttl bereits eine "
                         "Geometrie fuer diese Orte publiziert.")
    args = ap.parse_args()

    if not args.csv.exists():
        print(f"CSV nicht gefunden: {args.csv}", file=sys.stderr)
        return 1

    df = pd.read_csv(args.csv)
    args.out.mkdir(parents=True, exist_ok=True)

    onto = build_ontology()
    g = build_graph(df, args.era, args.figure_name,
                    args.emit_geometry, args.findspot_uri)

    onto_path = args.out / "lado_dating_extension.ttl"
    ttl_path = args.out / f"ips_{args.figure_name}.ttl"
    jld_path = args.out / f"ips_{args.figure_name}.jsonld"

    onto.serialize(destination=onto_path, format="turtle", encoding="utf-8")
    g.serialize(destination=ttl_path, format="turtle", encoding="utf-8")
    g.serialize(destination=jld_path, format="json-ld", indent=2,
                auto_compact=True, encoding="utf-8")

    # Read-back check: what was written has to be parseable too.
    check = Graph()
    check.parse(ttl_path, format="turtle")

    print(f"Rows read             : {len(df)}")
    print(f"Ontology              : {onto_path}  ({len(onto)} triples)")
    print(f"Graph (Turtle)        : {ttl_path}  ({len(g)} triples)")
    print(f"Graph (JSON-LD)       : {jld_path}")
    print(f"Read-back check       : OK, {len(check)} triples parsed")
    print(f"Era convention        : {args.era}")
    if args.era == "historical":
        print("  -> negative source years are read as BC and shifted by +1")
        print("     for xsd:gYear onto astronomical counting.")
        print("     If the database already counts astronomically:")
        print("     re-run with --era astronomical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
