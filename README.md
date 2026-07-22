# IPS Dated Sites — RDF-Export und SPARQL-Rückweg

Lokaler Prototyp für den RDF-Export der Fundstellen-Datierung
(Samian Research / IPS). Eingabe ist die CSV aus
`IPSDatedSites25_final.sql`; das CFM-Skript holt später nur noch die
Daten aus der Datenbank, die Modellierung wandert nach JavaScript in den
Browser. Diese Python-Fassung ist die Referenzimplementierung, gegen die
sich die spätere JS-Portierung messen lassen muss.

## Aufbau

```
ips-rdf/
├── data/                        Eingabe: die CSV aus IPSDatedSites25_final.sql
├── img/                         (erzeugt) beide Abbildungen, je SVG + JPG 300 dpi
├── rdf/                         (erzeugt) Turtle, JSON-LD, LADO-Erweiterung
├── py/
│   ├── main.py                  einziger Einstiegspunkt: python py/main.py
│   ├── ips_rdf_export.py        CSV -> RDF, baut den Graphen mit rdflib
│   ├── ips_sparql.py            Abfragen, Graphzugriff, Rundlaufprüfung
│   └── ips_render.py            zwei Darstellungen: classic und modern
├── queries/                     dieselben Abfragen als .rq für einen Endpoint
├── README.md
└── requirements.txt
```

Alle Pfade werden über `Path(__file__).resolve().parent.parent` gegen die
Repo-Wurzel aufgelöst — aufgerufen wird immer von dort, nicht aus `py/`.

`ips_rdf_export.py` baut den Graphen. Alles danach liest **ausschließlich
per SPARQL** zurück — auch Randbreiten, Zeilenhöhe, Farbrampe und
Sortierregel stehen im Graphen, nicht in den Renderern. Fehlt im Export
etwas, das die Abbildung braucht, scheitert der Rückweg und sagt genau,
was fehlt. Das ist der Vollständigkeitstest der Modellierung, nicht bloß
eine nette Zugabe.

## Zwei Darstellungen

**v1 classic** ist die bestehende D3-Abbildung: Box, Whisker mit Kappen,
Extremwert-Stubs, gestrichelte Boxkanten bei vorhandener Unsicherheit,
Gradientenlegende unten.

**v2 modern** zeigt dieselben Zahlen in anderer Sprache: Kapsel statt
Box, blasse Vollbereichslinie der beitragenden Stempel im Hintergrund,
Mittelpunktmarke, Zebra-Zeilen statt Gitternetz, BC/AD-Achse,
Direktbeschriftung mit Spanne, n und Die-Wiederholung, Farbleiste
rechts. Nichts davon ist neu gerechnet — es ist derselbe SPARQL-Abruf.

Beide schreiben SVG (vektoriell, für den Satz) und JPG mit 300 dpi.

## Einrichtung (Windows / VS Code)

```powershell
pip install -r requirements.txt
```

Terminal auf PowerShell lassen; die Skripte schreiben UTF-8 unabhängig
von der Codepage, weil rdflib die Serialisierung übernimmt.

## Ablauf

```powershell
python py/main.py
python py/main.py --era astronomical       # andere Ära-Konvention
python py/main.py --findspot-uri slug      # lesbare statt gehashte URIs
python py/main.py --skip-plots             # nur Export und Rundlauf
```

Die CSV wird automatisch aus `data/` genommen. Mit `--csv` lässt sich
eine andere angeben.

Erzeugt wird:

| Datei | Inhalt |
|---|---|
| `rdf/ips_sites_dating_v1.ttl` | der Graph, 2442 Tripel aus 41 Zeilen |
| `rdf/ips_sites_dating_v1.jsonld` | derselbe Graph als JSON-LD |
| `rdf/lado_dating_extension.ttl` | die LADO-Erweiterung (Klassen, Properties) |
| `img/plot_v1_classic.svg` / `.jpg` | 1:1 der bestehenden Abbildung |
| `img/plot_v2_modern.svg` / `.jpg` | dieselben Daten, moderne Fassung |

Die SVGs sind byte-stabil: `SOURCE_DATE_EPOCH` und ein fester
`svg.hashsalt` sorgen dafür, dass ein Rebuild ohne inhaltliche Änderung
identische Dateien erzeugt. Sonst schriebe matplotlib bei jedem Lauf
einen neuen Zeitstempel und neu gewürfelte Element-IDs, und beide
Abbildungen stünden in `git status` dauerhaft als geändert — eine Datei,
deren Diff immer rot ist, ist eine Datei, deren Diff niemand mehr liest.

Der Rückweg endet mit einer Feldprüfung gegen die CSV. Aktueller Stand:
größte Abweichung über alle 17 verglichenen Felder = `0.00e+00`.

## Aufbau des Graphen

Drei Schichten, bewusst getrennt:

**1 — Ort und Fundstelle.** `samian:loc_ds_<id>` ist bereits publiziert
und wird nur referenziert, nie neu typisiert. Neu ist die Fundstelle
`samian:fs_<id>_<slug>`, die per `crm:P89_falls_within` in den Fundplatz
fällt. Deshalb kann Bregenz sechs Fundstellen tragen, ohne dass sechs
Zeitspannen direkt am Ort hängen.

**2 — Datierung.** `samian:ts_<id>_<slug>` ist eine
`lado:FindspotDating`, über zwei Stufen `rdfs:subClassOf` unter
`crm:E52_Time-Span` und `time:ProperInterval`. Sie trägt die
inhaltliche Aussage: Beginn und Ende als OWL-Time-Instants mit
`time:TimePosition`, dazu σ, k, n, D, r, `q_interval`, `q_repetition`
und die avg/min/max-Werte.

**3 — Darstellung.** `samian:plotrow_<id>_<slug>` trägt `unc_start`,
`unc_end` und `unc_interval`. Die stehen hier und nicht an der
Zeitspanne, weil eure Methodendoku sie ausdrücklich als *visual only*
führt — `√(s²ₐ+s²_b)` ist die Streuung von nichts im Modell. Hingen sie
an der Zeitspanne, behauptete der Graph das Gegenteil. Die Konstanten
der Abbildung (`padYears`, `rowHeight`, Farbrampe, Sortierregel) hängen
einmal am `lado:Figure`-Knoten statt 41-mal in den Zeilen.

Dazu PROV: ein `lado:DatingModel` als `prov:Plan` mit k_min, k_max, τ,
w und dem Divisor 12, pro Zeile eine `prov:Activity` mit
`prov:qualifiedAssociation` auf diesen Plan.

## Die drei Entscheidungen — beantwortet

**Ära-Konvention: `historical`.** Bestätigt: `-40` in der Datenbank
bedeutet 40 v. Chr. Da `xsd:gYear` astronomisch zählt (Jahr 0 = 1 v.
Chr.), wird um +1 verschoben. Kontrolle an Amiens: `eff_start = -16.6`
→ gerundet 17 v. Chr. → `time:inXSDgYear "-0016"`. Der Schalter
`--era astronomical` bleibt für den Fall, dass sich das je ändert.

Wichtig: umgerechnet wird **nur das Kalenderlabel**. Die
`time:numericPosition` bleibt exakt der Quellwert und hängt an einem
eigenen, dokumentierten `samian:trs_ips_year`. Grund: die Query rechnet
`eff = m ± k·σ` auf einer durchgehenden Zahlengeraden; ein „+1 nur für
negative Werte" spränge bei −0,5 → +0,5, wäre nicht umkehrbar und
zerstörte die Arithmetik, aus der der Wert stammt.

**Findspot-URI: Hash.** Die Fundstelle hat keine eigene ID, also
`samian:fs_<site-id>_<hash>` mit sechsstelligem Hash aus dem Namen:

```
sha256( NFC( trim(findspot) ) ).hexdigest()[0:6]
```

Amiens / *Sq. Bocquet pit 1973* wird damit zu
`samian:fs_1003978_969c47`. Das Rezept steht als
`lado:identifierScheme` im Datensatz, weil die spätere JS-Portierung es
**zeichengenau** reproduzieren muss — `str.normalize("NFC")` vor dem
Hashen ist dabei nicht Kosmetik: liefert die Quelle `ö` einmal als
U+00F6 und einmal als `o`+U+0308, ergäben sich sonst zwei URIs für
dieselbe Fundstelle. Der Export prüft auf Kollisionen und bricht ab,
statt still zwei Fundstellen zu verschmelzen.

Ehrlichkeitshalber: der Hash löst die Stabilität **nicht**. Ändert
jemand den Namen, ändert sich der Hash genauso wie ein Slug — man sieht
es nur nicht mehr. Deshalb bleibt der lesbare Slug zusätzlich als
`skos:notation` am Knoten, damit ein gebrochener Link diagnostizierbar
ist. Mit `--findspot-uri slug` lässt sich auf lesbare Fragmente
umstellen; dann greift die Transliteration (`Emmeranstraße` →
`emmeranstrasse`, nicht `emmeranstrae`, weil `ß` keine NFD-Dekomposition
hat).

**Basis-URI: nicht versioniert.** Fundstellen- und Zeitspannen-URIs
bleiben stabil und bezeichnen dauerhaft dieselbe Fundstelle bzw. deren
*jeweils aktuelle* Datierung. Ändern sich die Quelldaten, ändern sich
die Werte unter derselben URI.

Damit ist die Zeitspanne allerdings ein bewegliches Ziel für Zitate.
Aufgelöst wird das über den Datensatz: der bekommt ein Datum
(`samian:dataset_sites_dating_v1_2026-07-22`, mit `dcterms:issued` und
`owl:versionInfo`), und jede Zeitspanne hängt per
`prov:wasDerivedFrom` daran. Zitiert wird der datierte Snapshot,
referenziert die stabile URI.

**Geometrie.** `--emit-geometry` ist standardmäßig **aus**, weil
`loc_discoverysite_1.ttl` für dieselben Orte bereits eine Geometrie
publiziert. Einschalten nur, wenn ihr die IPS-Koordinaten bewusst
danebenstellen wollt.

## NULL-Kontrakt

Fehlt ein Wert, wird das Tripel weggelassen — nie `0` oder `0.5`
behauptet. Damit Abwesenheit nicht mit „noch nicht gerechnet"
verwechselt wird, setzt der Export zusätzlich einen expliziten Marker:

```turtle
samian:ts_1000080_ne_gate lado:undefinedMeasure lado:qInterval .
```

In diesem Datenstand feuert der Marker nirgends — die 41 Zeilen sind in
`q_*` und `unc_*` vollständig.

## rdflib und vorchristliche Jahre

rdflib 7.1.x bildet `xsd:gYear` auf Pythons `datetime.date` ab. Das kann
keine Jahre vor 1 darstellen (`datetime.MINYEAR == 1`), weshalb jedes
v.-Chr.-Jahr beim Anlegen *und* beim Parsen des Literals eine Warnung
samt Traceback auf die Konsole schreibt. Bei den aktuellen Daten
betrifft das acht Literale.

Das Literal selbst ist dabei in allen Fällen korrekt — nachgeprüft mit
genau dieser Version:

```
Literal("-0016", datatype=XSD.gYear).n3()
→ "-0016"^^<http://www.w3.org/2001/XMLSchema#gYear>
```

Nur `.value` bleibt `None`. Folgenlos, weil keine Abfrage auf `gYear`
rechnet: die verwertbare Zeitangabe steht als `time:numericPosition` an
der `time:TimePosition`, `time:inXSDgYear` ist die Beigabe für
Konsumenten, die nur Kalenderjahre lesen. Ab rdflib 7.5 ist der
Konverter entfernt und es schweigt ohnehin.

`py/ips_compat.py` unterdrückt deshalb **genau diese eine Meldung** und
sonst nichts — ein pauschales Stummschalten von `rdflib.term` wäre die
falsche Lösung, dort landen auch Meldungen, die man sehen will. Die
Anzahl betroffener Literale gibt `main.py` stattdessen aus, damit sie
sichtbar bleibt statt bloß stummgestellt zu sein.

Eine Anmerkung zu `"0000"`: das ist astronomisch 1 v. Chr. und nach
XSD **1.1** gültig, nach XSD 1.0 nicht. Es entsteht bei Intervallenden
wie `eff_end = -0.9`. Sollte ein Validator darüber stolpern, ist das die
Stelle.

## Bewusst nicht übernommen

Die publizierte `loc_discoverysite_1.ttl` bindet `prov:` auf
`http://www.w3.org/ns/prov-o/`. Dadurch zeigen dort alle sechs
PROV-Prädikate auf nicht existierende Terme. Dieser Export benutzt den
korrekten Namensraum `http://www.w3.org/ns/prov#`. Ebenso wird das `.0`
an den Pleiades-Kennungen abgeschnitten — es steckt bereits in der
Datenbankspalte und macht in der publizierten TTL alle 280
Pleiades-Links unerreichbar.

## Offene Punkte

- Der Findspot hat keinen eigenen Schlüssel in der Datenbank. Die URI
  wird aus dem Text abgeleitet und bricht, sobald jemand einen
  Fundstellennamen korrigiert. Im Datenstand steht z. B.
  `Böckleareal (descruction layer period II)` — ein Tippfehler für
  *destruction*, mitten in einem URI-bildenden Feld.
- `p.datemax NOT IN (260,120,150)` steht als `lado:excludedDatemax` im
  Graphen, die Bedeutung ist weiter ungeklärt.
- `q_start` / `q_end` hängen am Kalender-Nullpunkt und benachteiligen
  augusteisches Material systematisch. Sie sind exportiert, aber der
  Kommentar in der Ontologie warnt davor.
- Die Farbrampe ist hier stückweise linear durch ColorBrewer RdYlGn-11
  interpoliert; `d3.interpolateRdYlGn` legt eine Basis-Spline hindurch.
  Minimale Abweichungen in den Zwischentönen sind normal und nur
  optisch.
