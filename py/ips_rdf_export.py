"""
IPS Dated Sites — RDF-Export
============================

Liest die CSV aus IPSDatedSites25_final.sql und baut daraus einen
Knowledge Graph in Turtle / JSON-LD.

Der Graph wird mit rdflib *konstruiert*, nicht als Text zusammengeklebt.
Damit ist die gesamte Fehlerklasse des alten Exporters (ungueltige
Literale wie 0.0953^^xsd:decimal, kaputte Escapes, offene Statements)
konstruktionsbedingt ausgeschlossen.

AUFBAU IN DREI SCHICHTEN
------------------------
  1. ORT & FUNDSTELLE   — was in der Welt ist
       samian:loc_ds_<id>          bereits publiziert, wird nur referenziert
       samian:fs_<id>_<slug>       Fundstelle, crm:P89_falls_within Ort

  2. DATIERUNG          — die inhaltliche Aussage
       samian:ts_<id>_<slug>       lado:FindspotDating
                                   -> crm:E52_Time-Span, time:ProperInterval
       traegt eff_start/eff_end (als OWL-Time TimePosition), sigma, k,
       n, D, r, q_interval, q_repetition, q_start, q_end, avg/min/max

  3. DARSTELLUNG        — was die Abbildung erzeugt
       samian:plotrow_<id>_<slug>  lado:PlotRow, lado:renders -> Time-Span
                                   traegt unc_* (laut Doku "visual only")
       samian:fig_<name>           lado:Figure, Konstanten der Abbildung

  + PROV: DatingModel (prov:Plan) mit k_min/k_max/tau/w, pro Zeile eine
    prov:Activity, dazu Agent, Quelldatensatz und der ungeklaerte Filter.

NULL-KONTRAKT
-------------
Fehlt ein Wert, wird das Tripel WEGGELASSEN — nie 0 oder 0.5 behauptet.
Damit Abwesenheit nicht mit "noch nicht gerechnet" verwechselt wird,
setzt der Export zusaetzlich einen expliziten Marker:
    <ts> lado:undefinedMeasure lado:qInterval .

Aufruf (Windows / VS Code):
    python py/ips_rdf_export.py --csv data/daten.csv --out rdf

Normalerweise nicht direkt aufrufen, sondern ueber py/main.py.
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
from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.namespace import DCTERMS, SKOS, XSD

from ips_compat import silence_gyear_warnings

# rdflib < 7.5 kann vorchristliche xsd:gYear nicht in ein Python-date
# wandeln und schreibt dafuer je Literal einen Traceback. Die Literale
# selbst sind korrekt; Begruendung und Nachweis in ips_compat.py.
silence_gyear_warnings()

# --------------------------------------------------------------------------
# Namensraeume
# --------------------------------------------------------------------------
SAMIAN = Namespace("http://data.archaeology.link/data/samian/")
LADO = Namespace("http://archaeology.link/ontology#")
CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
TIME = Namespace("http://www.w3.org/2006/time#")
PROV = Namespace("http://www.w3.org/ns/prov#")  # KORREKT. Die publizierte
# loc_discoverysite_1.ttl bindet prov: faelschlich auf .../ns/prov-o/ ,
# wodurch dort alle sechs PROV-Praedikate ins Leere zeigen. Nicht uebernehmen.
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
PLEIADES = Namespace("https://pleiades.stoa.org/places/")

TRS_GREGORIAN = URIRef("http://www.opengis.net/def/uom/ISO-8601/0/Gregorian")
# Eigenes TRS fuer die Zahlengerade, auf der die Quelle rechnet.
# Begruendung siehe numeric_year().
TRS_IPS = SAMIAN["trs_ips_year"]

PREFIXES = {
    "samian": SAMIAN, "lado": LADO, "crm": CRM, "time": TIME, "prov": PROV,
    "geo": GEO, "dcat": DCAT, "dcterms": DCTERMS, "skos": SKOS,
    "pleiades": PLEIADES, "owl": OWL, "xsd": XSD,
}

# --------------------------------------------------------------------------
# Konstanten der Abbildung (aus IPSDatedSites25.cfm)
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

# Der ungeklaerte Filter aus der Quell-Query.
EXCLUDED_DATEMAX = [260, 120, 150]

# --------------------------------------------------------------------------
# Slug — Transliteration VOR Normalisierung
# --------------------------------------------------------------------------
# Reines NFD/NFKD reicht fuer Deutsch nicht: 'ß' hat gar keine
# Dekomposition und fiele ersatzlos weg ("Emmeranstraße" -> "emmeranstrae").
# Und in JavaScript ist \w ASCII-only, weshalb der alte v5-Exporter aus
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


# Rezept fuer den Findspot-Schluessel. Muss in der spaeteren
# JS-Portierung ZEICHENGENAU reproduziert werden, sonst zeigen die
# beiden Implementierungen auf verschiedene URIs.
KEY_ALGORITHM = "sha256(NFC(trim(findspot)))[0:6], je Fundplatz-ID"


def findspot_hash(findspot: str) -> str:
    """
    Sechsstelliger Hash aus dem Fundstellennamen.

    NFC-Normalisierung ist hier nicht Kosmetik: liefert die Quelle 'ö'
    einmal als U+00F6 und einmal als 'o'+U+0308, ergaeben sich sonst
    zwei verschiedene Hashes fuer dieselbe Fundstelle. In JavaScript
    entspricht das str.normalize("NFC") vor dem Hashen.
    """
    raw = unicodedata.normalize("NFC", str(findspot).strip())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6]


def build_keys(df: pd.DataFrame, mode: str) -> dict:
    """(the_id, findspot) -> URI-Fragment. Prueft auf Kollisionen."""
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
                f"URI-Kollision am Fundplatz {sid}: '{prev}' und "
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
    Ganzjahr -> xsd:gYear.

    era='historical'   : -40 in der DB bedeutet 40 v.Chr. -- so bestaetigt
                         fuer die IPS-Datenbank. xsd:gYear zaehlt
                         astronomisch (Jahr 0 = 1 v.Chr.), also -40 -> -0039.
    era='astronomical' : der DB-Wert ist bereits astronomisch, unveraendert.
    """
    y = int(round(year_db))
    if era == "historical" and y < 0:
        y += 1
    sign = "-" if y < 0 else ""
    return Literal(f"{sign}{abs(y):04d}", datatype=XSD.gYear)


def numeric_year(value: float) -> Decimal:
    """
    Dezimaljahr — UNVERAENDERT aus der Quelle.

    Bewusst ohne Aera-Umrechnung. Die Quelle rechnet eff = m +/- k*sigma
    auf einer durchgehenden Zahlengeraden; ein '+1 nur fuer negative
    Werte' wuerde bei -0.5 -> +0.5 springen, waere nicht umkehrbar und
    zerstoerte die Arithmetik, aus der der Wert stammt.

    Die Aera-Konvention gehoert deshalb an das KALENDER-LABEL
    (time:inXSDgYear), nicht an die Position auf der Zahlengeraden.
    Die Zahlengerade selbst bekommt ein eigenes, dokumentiertes TRS
    (samian:trs_ips_year) statt stillschweigend als Gregorian zu gelten.
    """
    return Decimal(str(value))


# --------------------------------------------------------------------------
# Ontologie-Erweiterung (LADO)
# --------------------------------------------------------------------------
# Klassen haengen ueber mehrere Stufen unter CIDOC CRM. Die vorhandenen
# LADO-Klassen der publizierten Daten werden hier nachtraeglich in CRM
# verankert, OHNE die publizierten Instanzen neu zu typisieren.
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
    (LADO.DatingModel, [PROV.Plan], "Dating model",
     "Parametrisierung, aus der die Intervalle berechnet wurden."),
    (LADO.Figure, [CRM.E36_Visual_Item], "Figure",
     "Abbildung. Traegt die Konstanten, die nicht zu den Fundplaetzen "
     "gehoeren, sondern zur Grafik."),
    (LADO.PlotRow, [CRM.E36_Visual_Item], "Plot row",
     "Darstellungsschicht einer Datierung. Traegt ausdruecklich die "
     "Groessen, die laut Methodendoku 'visual only' sind."),
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
     "Haengt am Kalender-Nullpunkt und benachteiligt augusteisches "
     "Material systematisch. Mit Vorsicht verwenden."),
    (LADO.qEnd, LADO.DatedTimeSpan, XSD.decimal, "q end",
     "Siehe qStart."),
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
    # Modell
    (LADO.kMin, LADO.DatingModel, XSD.decimal, "k min", ""),
    (LADO.kMax, LADO.DatingModel, XSD.decimal, "k max", ""),
    (LADO.tau, LADO.DatingModel, XSD.decimal, "tau",
     "Saettigungskonstante. Bei n = tau sind rund 63 % der moeglichen "
     "Verschmaelerung erreicht."),
    (LADO.volumeWeight, LADO.DatingModel, XSD.decimal, "volume weight",
     "w = 1.0: k haengt rein am Volumen."),
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

    for prop, dom, rng, label, comment in OBJ_PROPS:
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.domain, dom))
        g.add((prop, RDFS.range, rng))
        g.add((prop, RDFS.label, Literal(label, lang="en")))
        g.add((prop, RDFS.isDefinedBy, onto))
        if comment:
            g.add((prop, RDFS.comment, Literal(comment, lang="de")))

    for prop, dom, rng, label, comment in DATA_PROPS:
        g.add((prop, RDF.type, OWL.DatatypeProperty))
        g.add((prop, RDFS.domain, dom))
        g.add((prop, RDFS.range, rng))
        g.add((prop, RDFS.label, Literal(label, lang="en")))
        g.add((prop, RDFS.isDefinedBy, onto))
        if comment:
            g.add((prop, RDFS.comment, Literal(comment, lang="de")))
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

    # ---- Agent, Modell, Quelle, Datensatz -------------------------------
    agent = SAMIAN.IPSDatedSitesExporter
    g.add((agent, RDF.type, PROV.SoftwareAgent))
    g.add((agent, RDFS.label, Literal("ips_rdf_export.py", lang="en")))

    # ---- Zeitreferenzsystem der Quelle ----------------------------------
    g.add((TRS_IPS, RDF.type, TIME.TRS))
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
    g.add((model, LADO.fuzzinessDivisor, integer(12)))
    g.add((model, LADO.eraConvention, Literal(era)))
    for v in EXCLUDED_DATEMAX:
        g.add((model, LADO.excludedDatemax, integer(v)))

    # Die Time-Span-URIs bleiben stabil; ihr WERT aendert sich mit den
    # Daten. Zitierfaehig ist deshalb der datierte Snapshot, nicht die
    # einzelne Zeitspanne.
    dataset = SAMIAN[f"dataset_{figure_name}_{snapshot}"]
    g.add((dataset, RDF.type, DCAT.Dataset))
    g.add((dataset, RDF.type, PROV.Entity))
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

    # ---- Zeilen ---------------------------------------------------------
    for _, r in df.iterrows():
        sid = int(r.the_id)
        fs_slug = slug(r.the_findspot)          # nur noch als skos:notation
        key = f"{sid}_{keys[(sid, str(r.the_findspot))]}"

        place = SAMIAN[f"loc_ds_{sid}"]
        findspot = SAMIAN[f"fs_{key}"]
        ts = SAMIAN[f"ts_{key}"]
        row = SAMIAN[f"plotrow_{key}"]
        act = SAMIAN[f"act_dating_{key}"]

        # --- Ort: nur referenzieren, nicht neu behaupten ---
        g.add((place, RDFS.label, Literal(str(r.the_site), lang="en")))
        if not isna(r.latinsitename):
            g.add((place, LADO.ancientName, Literal(str(r.latinsitename))))
        if not isna(r.pleiades):
            # Das '.0' steckt bereits in der Datenbank; sauber casten.
            g.add((place, LADO.pleiadesID,
                   PLEIADES[str(int(float(r.pleiades)))]))
        if emit_geometry and not isna(r.lat) and not isna(r["long"]):
            geom = SAMIAN[f"loc_ds_{sid}_geom_ips"]
            g.add((place, GEO.hasGeometry, geom))
            g.add((geom, GEO.asWKT, Literal(
                f"<http://www.opengis.net/def/crs/EPSG/0/4326> "
                f"POINT({r['long']} {r.lat})", datatype=GEO.wktLiteral)))

        # --- Fundstelle ---
        g.add((findspot, RDF.type, LADO.Findspot))
        g.add((findspot, RDFS.label, Literal(str(r.the_findspot))))
        g.add((findspot, SKOS.notation, Literal(fs_slug)))
        g.add((findspot, CRM.P89_falls_within, place))
        g.add((findspot, CRM["P4_has_time-span"], ts))

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
            g.add((inst, TIME.inTimePosition, pos))
            g.add((pos, RDF.type, TIME.TimePosition))
            g.add((pos, TIME.hasTRS, TRS_IPS))
            g.add((pos, TIME.numericPosition, dec(numeric_year(value))))
            # Zusaetzlich gerundet, fuer Konsumenten, die nur Kalender-
            # jahre verstehen. Die exakte Lage steht in numericPosition.
            g.add((inst, TIME.inXSDgYear, gyear(value, era)))

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
                # NULL-KONTRAKT: kein Tripel, aber explizit markiert.
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
        g.add((act, RDFS.label, Literal(
            f"Dating of {r.the_site} — {r.the_findspot}", lang="en")))
        g.add((act, PROV.wasAssociatedWith, agent))
        g.add((act, PROV.endedAtTime, now))
        g.add((act, PROV.used, dataset))
        qa = BNode()
        g.add((act, PROV.qualifiedAssociation, qa))
        g.add((qa, RDF.type, PROV.Association))
        g.add((qa, PROV.agent, agent))
        g.add((qa, PROV.hadPlan, model))
        g.add((ts, PROV.wasDerivedFrom, dataset))

    return g


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="IPS Dated Sites: CSV -> RDF (Turtle / JSON-LD)")
    ap.add_argument("--csv", required=True, type=Path,
                    help="Ergebnis-CSV aus IPSDatedSites25_final.sql")
    ap.add_argument("--out", default=Path("rdf"), type=Path,
                    help="Ausgabeverzeichnis (Standard: rdf)")
    ap.add_argument("--era", choices=("historical", "astronomical"),
                    default="historical",
                    help="Lesart negativer Jahreszahlen der Quelle. "
                         "historical: -40 = 40 v.Chr. (xsd:gYear -0039). "
                         "astronomical: -40 = xsd:gYear -0040.")
    ap.add_argument("--findspot-uri", choices=("hash", "slug"),
                    default="hash",
                    help="Wie das Fundstellen-Fragment gebildet wird. "
                         "hash: sechsstellig aus dem Namen (Standard). "
                         "slug: lesbar transliteriert.")
    ap.add_argument("--figure-name", default="sites_dating_v1")
    ap.add_argument("--emit-geometry", action="store_true",
                    help="Koordinaten aus IPS mit ausgeben. Standard aus, "
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

    # Rueckleseprobe: was geschrieben wurde, muss auch parsbar sein.
    check = Graph()
    check.parse(ttl_path, format="turtle")

    print(f"Zeilen gelesen        : {len(df)}")
    print(f"Ontologie             : {onto_path}  ({len(onto)} Tripel)")
    print(f"Graph (Turtle)        : {ttl_path}  ({len(g)} Tripel)")
    print(f"Graph (JSON-LD)       : {jld_path}")
    print(f"Rueckleseprobe        : OK, {len(check)} Tripel geparst")
    print(f"Aera-Konvention       : {args.era}")
    if args.era == "historical":
        print("  -> negative Quelljahre werden als v.Chr. gelesen und fuer")
        print("     xsd:gYear um +1 auf astronomische Zaehlung verschoben.")
        print("     Falls die Datenbank bereits astronomisch zaehlt:")
        print("     mit --era astronomical erneut ausfuehren.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
