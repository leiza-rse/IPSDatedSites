# IPS Dated Sites — RDF-Export, SPARQL-Rückweg, Abbildungen

Lokaler Prototyp für den RDF-Export der Fundstellen-Datierung (Samian
Research / IPS). Eingabe ist die CSV aus `IPSDatedSites25_final.sql`, eine
Zeile je Findspot. Das CFM-Skript holt später nur noch die Daten aus der
Datenbank; die Modellierung wandert nach JavaScript in den Browser. Diese
Python-Fassung ist die Referenzimplementierung, gegen die sich die
JS-Portierung messen lassen muss.

> **Was wie modelliert wurde und warum, steht in [`docs/`](docs/index.md).**
> Dort liegen auch der Crosswalk zu CIDOC CRM, OWL-Time, GeoSPARQL und
> PROV-O, die Formeln aus dem SQL und die offenen Punkte. Dieses README
> beschreibt nur Bedienung und getroffene Entscheidungen — jede Aussage
> soll genau einen Ort haben.

## Aufbau

```
IPSDatedSites/
├── data/                    Eingabe: CSV aus IPSDatedSites25_final.sql
├── py/                      der gesamte Code
├── queries/                 die SPARQL-Abfragen als .rq für einen Endpoint
├── .github/workflows/       CI: Pipeline, Drift-Prüfung, Validierung
├── docs/          erzeugt   Dokumentation der Modellierung (British English)
│   ├── _config.yml          Jekyll, damit GitHub Pages die Diagramme rendert
│   ├── _layouts/            Layout mit mermaid.js
│   └── diagrams/  erzeugt   die fünf .mmd-Dateien
├── rdf/           erzeugt   Turtle, JSON-LD, LADO-Erweiterung, Bundle
├── img/           erzeugt   beide Abbildungen, je SVG + JPG 300 dpi
├── .gitignore
├── CITATION.cff
├── LICENSE
├── README.md
└── requirements.txt
```

| Datei in `py/` | Aufgabe |
|---|---|
| `main.py` | einziger Einstiegspunkt, fünf Schritte |
| `ips_rdf_export.py` | CSV → RDF, baut den Graphen mit rdflib |
| `ips_sparql.py` | Abfragen, Graphzugriff, Rundlaufprüfung |
| `ips_render.py` | die beiden Abbildungen |
| `ips_docs_text.py` | englische Textquelle für Ontologie **und** Doku |
| `make_bundle.py` | baut das Standalone-Bundle für einen Triplestore |
| `make_diagrams.py` | erzeugt die Mermaid-Diagramme aus Code und Graph |
| `make_docs.py` | erzeugt `docs/*.md` aus dem Code |
| `ips_compat.py` | unterdrückt eine rdflib-Warnung, siehe unten |

Alle Pfade lösen über `Path(__file__).resolve().parent.parent` gegen die
Repo-Wurzel auf. Aufgerufen wird von dort, nicht aus `py/`.

## Einrichtung und Lauf

```powershell
pip install -r requirements.txt
python py/main.py
```

Terminal auf PowerShell lassen; die Skripte schreiben UTF-8 unabhängig von
der Codepage, weil rdflib die Serialisierung übernimmt. Die CSV wird
automatisch aus `data/` genommen.

```powershell
python py/main.py --era astronomical      # andere Ära-Konvention
python py/main.py --findspot-uri slug     # lesbare statt gehashte URIs
python py/main.py --emit-geometry         # IPS-Koordinaten mit ausgeben
python py/main.py --csv data\andere.csv   # andere Eingabedatei
python py/main.py --skip-plots            # ohne Abbildungen
python py/main.py --skip-bundle           # ohne Standalone-Bundle
python py/main.py --skip-docs             # ohne Dokumentation
```

Die Zielordner lassen sich mit `--rdf-out`, `--img-out` und `--docs-out`
umlenken, der Name des Figur-Knotens mit `--figure-name`. Vollständige
Liste: `python py/main.py --help`.

Sechs Schritte laufen durch:

1. CSV → RDF nach `rdf/`
2. Graph laden, alles per SPARQL zurücklesen
3. beide Abbildungen nach `img/`
4. Rundlaufprüfung CSV → RDF → SPARQL, Feld für Feld
5. Standalone-Bundle nach `rdf/IPSDatedSites-bundle.ttl`
6. Dokumentation und Mermaid-Diagramme nach `docs/`

Aktueller Stand: 41 Zeilen, 2442 Tripel, Rundlauf über 17 Felder mit
größter Abweichung `0.00e+00`.

## Das Standalone-Bundle

`rdf/IPSDatedSites-bundle.ttl` enthält Daten, das komplette Vokabular und
einen **materialisierten** CIDOC-CRM-Crosswalk in einer Datei — gedacht
für einen Triplestore, insbesondere den NFDI4Objects-KG.

Materialisiert, weil Triplestores in der Regel nicht über
`rdfs:subClassOf` schließen. Mit den Axiomen allein liefert

```sparql
SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE { ?x a crm:E53_Place }
```

genau `0`, obwohl jede Fundstelle laut Axiomen ein Place ist. Der Builder
schreibt deshalb die transitive Hülle über `rdfs:subClassOf` als
`rdf:type`-Tripel aus. Die Axiome bleiben daneben stehen, ein
schließender Store leitet also nichts Neues ab und nichts widerspricht
sich.

Gegenprobe nach jedem Lauf, reine CRM/OWL-Time-Abfragen ohne Reasoner:

```
crm:E53_Place          73     (41 Fundstellen + 32 Fundplätze)
crm:E52_Time-Span      41
crm:E36_Visual_Item    42
time:ProperInterval    41
CRM-only path          41     Ort -> Time-Span -> numerisches Jahr
```

Details in [`docs/bundle.md`](docs/bundle.md).

## Der Rundlauf ist der eigentliche Test

`ips_rdf_export.py` baut den Graphen. Alles danach liest **ausschließlich
per SPARQL** zurück — auch Randbreiten, Zeilenhöhe, Farbrampe und
Sortierregel stehen im Graphen, nicht in den Renderern. Fehlt im Export
etwas, das die Abbildung braucht, scheitert der Rückweg, statt still eine
Konstante einzusetzen.

Dass aus **einem** Graphen **zwei** verschiedene korrekte Abbildungen
entstehen, ist der Beleg dafür, dass die Information wirklich im Graphen
steckt und nicht in einer Zeichenroutine.

## Zwei Darstellungen

**v1 classic** ist die bestehende D3-Abbildung, 1:1 — Box, Whisker mit
Kappen, Extremwert-Stubs, gestrichelte Boxkanten, Gradientenlegende
unten. Bleibt unangetastet, damit Webausgabe und Druckfassung konsistent
sind.

**v2 modern** zeigt **exakt dieselben Kanäle**, nur sauberer gesetzt.
Insbesondere behalten die Whisker ihre Farbe nach `q_start` / `q_end`:
die stehen an keiner anderen Stelle im Bild, und ein roter Whisker an den
frühen arretinischen Fundstellen ist eine Aussage, die man sehen und
nicht aus Zahlen zusammensuchen soll.

Modernisiert ist nur die Machart: Zebra-Zeilen statt Gitternetz,
BC/AD-Achse, zurückgenommene Hilfslinien, Farbleiste rechts, mehr Luft
zwischen den Zeilen, ein weißer Halo unter den Whiskern, damit die Farbe
über dem Zebra klar bleibt.

Rechts der Zeitachse steht eine **Wertetabelle** mit acht Spalten:
`interval`, `n`, `sigma`, `unc start`, `q start`, `q int`, `unc end`,
`q end`. Sie deckt ab, was die Webanwendung im Hover-Popup zeigt, plus
die Zahlen, die dort am Whisker stehen. Zwei Gründe: am Whisker
kollidierten sie mit dem Whisker selbst, sobald die Balken lang wurden —
und ein Popup funktioniert nur im Browser, gedruckt wäre die Information
schlicht weg. Die Spalte `sigma` stand nicht in der Webausgabe; sie ist
ergänzt, weil `Breite = 2·k·σ` gilt und man ohne sie sieht, *wie* breit
die Box ist, aber nicht *warum*. Wer sie nicht will, löscht eine Zeile in
`TABLE_COLUMNS`.

Eine frühere v2 hatte die Whiskerfarbe zugunsten einer Kapselform
aufgegeben. Das war ein Fehler: es sah aufgeräumter aus und war weniger
informativ. Die Regel ist es wert, festgehalten zu werden — **modernisiert
wird die Machart, nicht das, was kodiert ist.**

## Die drei Entscheidungen

**Ära-Konvention: `historical`.** `-40` in der Datenbank bedeutet 40
v. Chr. Da `xsd:gYear` astronomisch zählt, wird um +1 verschoben.
Kontrolle an Amiens: `eff_start = -16.6` → gerundet 17 v. Chr. →
`time:inXSDgYear "-0016"`. Umgerechnet wird **nur das Kalenderlabel**;
die `time:numericPosition` bleibt der Quellwert. Begründung in
[`docs/open-questions.md`](docs/open-questions.md).

**Findspot-URI: Hash.** `samian:fs_<site-id>_<hash>` mit
`sha256(NFC(trim(findspot)))[0:6]`. Amiens / *Sq. Bocquet pit 1973* wird
zu `samian:fs_1003978_969c47`. Das Rezept steht als
`lado:identifierScheme` im Graphen, weil die JS-Portierung es
zeichengenau reproduzieren muss. Mit `--findspot-uri slug` auf lesbare
Fragmente umstellbar — aber die Entscheidung sollte einmalig fallen, ein
späterer Wechsel erzeugt einen zweiten Satz URIs für dieselben
Fundstellen.

**Basis-URI: nicht versioniert.** Fundstellen- und Zeitspannen-URIs
bleiben stabil und bezeichnen die *jeweils aktuelle* Datierung. Zitierbar
ist stattdessen der datierte Datensatz
(`samian:dataset_sites_dating_v1_<Datum>`), an dem jede Zeitspanne per
`prov:wasDerivedFrom` hängt.

## Dokumentation, die nicht wegdriften kann

`docs/` wird bei jedem Lauf neu erzeugt, auf British English. Der Punkt
ist nicht Bequemlichkeit, sondern dass handgeschriebene Strukturdoku beim
ersten neuen Property auseinanderläuft.

Die **Struktur** liest `make_docs.py` zur Laufzeit aus dem Code: Klassen,
Properties mit Domain und Range, Namensräume, Figur-Konstanten und die
SPARQL-Abfragen kommen aus `ips_rdf_export.py`, `ips_render.py` und
`ips_sparql.py` selbst. Die **Prosa** steht in `ips_docs_text.py` — und
diese Datei speist zugleich die englischen `rdfs:comment` der Ontologie.
Eine Definition kann also nicht in der Doku stimmen und im RDF veraltet
sein; es ist derselbe String.

Dasselbe gilt für die **fünf Mermaid-Diagramme** unter `docs/diagrams/`:
Architektur, Klassenhierarchie, Beziehungen nach Schichten, eine echte
Instanz und die Materialisierung im Bundle. Keines ist gezeichnet — die
Hierarchie kommt aus `CLASSES`, die Beziehungen aus `RELATIONS` und
`LAYERS`, die Instanz per SPARQL aus dem gerade erzeugten Graphen, die
Materialisierung aus derselben Closure-Funktion, die das Bundle benutzt.

Jedes Diagramm wird zweimal aus **einem** String geschrieben: als
`.mmd`-Datei und als ` ```mermaid `-Block in der `.md`. github.com rendert
den Block direkt; GitHub Pages braucht dafür `mermaid.js` im Layout, bis
dahin ist die `.mmd` der Ausweg.

Nebenbei hat das den Exportcode verbessert: `crm:P89_falls_within` und
`crm:P4_has_time-span` standen vorher nur inline in `build_graph`. Jetzt
sind sie in `RELATIONS` deklariert, und `build_graph` benutzt dieselben
Konstanten — sonst wäre das Diagramm eine Abschrift gewesen, die beim
ersten Umbau falsch wird.

Der Generator **bricht ab**, wenn eine Klasse oder Property im Code keinen
Eintrag hat:

```
Undocumented terms — add them to py/ips_docs_text.py:
  property testProperty
```

Geprüft: neue Property ohne Doku → Exitcode 1; Doku ergänzt → Exitcode 0,
und der Text erscheint danach in `docs/vocabulary.md` **und** als
`rdfs:comment@en` in `rdf/lado_dating_extension.ttl`.

| Seite | Inhalt |
|---|---|
| [`index.md`](docs/index.md) | Überblick und Einstieg |
| [`model.md`](docs/model.md) | die drei Schichten, URI-Strategie, NULL-Kontrakt |
| [`vocabulary.md`](docs/vocabulary.md) | alle Klassen und Properties, generiert |
| [`crosswalk.md`](docs/crosswalk.md) | CIDOC CRM, OWL-Time, GeoSPARQL, PROV-O, DCAT, SKOS |
| [`statistics.md`](docs/statistics.md) | die Formeln aus dem SQL |
| [`queries.md`](docs/queries.md) | die SPARQL-Abfragen und der Rundlauf |
| [`open-questions.md`](docs/open-questions.md) | was offen ist, inklusive des Filters |

## GitHub Pages und die Diagramme

github.com rendert ` ```mermaid `-Blöcke nativ, **GitHub Pages nicht** —
dort läuft Jekyll, und der Block kommt als Code-Element an. Deshalb
liegen unter `docs/` ein `_config.yml` und ein `_layouts/default.html`
mit `mermaid.js`; das Layout wandelt die Code-Elemente beim Laden in
Diagramme um.

Der Markdown-Quelltext bleibt dabei für beide Ziele identisch — eine
Quelle, zwei Renderer. Das `_config.yml` setzt das Layout per `defaults`
für alle Seiten, damit `make_docs.py` nichts über Jekyll wissen muss.

## Die GitHub Action

`.github/workflows/build.yml` erzwingt bei jedem Push die Zusage, auf der
das Repo aufbaut: **die erzeugten Dateien dürfen dem Code nicht
hinterherhinken.** Ohne die Prüfung ist der Sync-Mechanismus nur eine
Konvention, und eine ungeprüfte Konvention vergisst irgendwann jemand.

Fünf Schritte:

1. Umgebung protokollieren — Python- und Bibliotheksversionen
2. Pipeline laufen lassen — der Rundlauf steckt darin und beendet sich
   bei jeder Abweichung mit Fehlercode
3. `git diff` auf `docs/`, getrennt davon auf `img/`
4. RDF semantisch prüfen: parst alles, und beantwortet das Bundle
   CIDOC-CRM-Abfragen ohne Reasoner?
5. Diagramme rendern: `.mmd` → SVG und JPG nach `img/diagrams/`, per
   Bot-Commit ins Repo

Die beiden Diff-Prüfungen sind **getrennt**, weil ihre Fehlerursachen es
sind. `docs/` ist reiner Text aus den Code-Strukturen und auf jeder
Plattform identisch — ein Unterschied dort heißt: jemand hat Code
geändert und nicht neu erzeugt. `img/` kommt aus matplotlib, und das
schreibt seine eigene Version in die SVG-Metadaten und leitet die
`clip-path`-IDs pro Version ab. Ein Unterschied dort ist meistens ein
Versionskonflikt, kein inhaltlicher.

`rdf/` ist von der Byte-Prüfung **ausgenommen**, und das mit Absicht: die
Dateien tragen `dcterms:created` und `prov:endedAtTime`, die sich von Lauf
zu Lauf ändern sollen. Nachgemessen sind `docs/`, `docs/diagrams/` und
`img/` byte-identisch über aufeinanderfolgende Läufe — dort ist die
Prüfung also aussagekräftig.

Getestet: Code geändert ohne neu zu erzeugen → Action schlägt an;
undokumentierte Property → Pipeline endet mit Exitcode 1.

## Gerenderte Diagramme

Unter jedem Diagramm in `docs/` stehen drei Verweise: **JPG**, **SVG** und
die **Mermaid-Quelle**. Sie zeigen absolut auf github.com, nicht relativ —
ein relativer Link auf `diagrams/*.mmd` funktioniert im Repo, aber nicht
auf GitHub Pages, weil `docs/_config.yml` die `.mmd` dort gar nicht
ausliefert.

Gerendert wird in der Action, nicht in `py/main.py`: `mmdc` braucht Node
und einen Headless-Browser, und die Windows-Arbeitsumgebung hat beides
nicht. Die Pipeline bleibt dadurch reines Python, CI liefert die Bilder
nach — SVG plus JPG bei Skalierung 4, also grob 300 dpi. Dieselbe
Konvention wie bei den beiden Hauptabbildungen.

Der Bot-Commit trägt `[skip ci]`, und ein Commit mit `GITHUB_TOKEN` löst
ohnehin keinen weiteren Workflow-Lauf aus — eine Schleife ist also nicht
möglich. `img/diagrams/` ist von der Byte-Prüfung auf `img/` ausgenommen,
weil die Dateien erst später im selben Lauf entstehen und nicht aus der
Python-Pipeline stammen.

## Warum die Versionen exakt gepinnt sind

`requirements.txt` nennt exakte Versionen, nicht Spannen. Der Grund ist
konkret: beim ersten CI-Lauf lief die Drift-Prüfung auf einen Fehler,
weil lokal matplotlib 3.9.2 und auf dem Runner 3.10.9 installiert war.
Im Diff stand

```
- <dc:title>Matplotlib v3.9.2 …
+ <dc:title>Matplotlib v3.10.9 …
- clip-path="url(#p3b6c313feb)"
+ clip-path="url(#p8bcc3c5794)"
```

Die Version steht in den SVG-Metadaten, und `svg.hashsalt` macht die
`clip-path`-IDs nur *innerhalb* einer Version deterministisch. Die
Prüfung war also korrekt — sie hat einen echten Unterschied gemeldet,
nur keinen inhaltlichen.

Wer eine Version anhebt, lässt danach einmal `python py/main.py` laufen
und committet die neu erzeugten Dateien mit.

Schriftarten sind übrigens unkritisch: der Renderer setzt kein
`font.family`, es gilt matplotlibs eigene DejaVu Sans, die mit dem Paket
ausgeliefert wird. Windows und Linux erzeugen dieselben Textpfade.

## rdflib und vorchristliche Jahre

rdflib 7.1.x bildet `xsd:gYear` auf Pythons `datetime.date` ab. Das kann
keine Jahre vor 1 darstellen (`datetime.MINYEAR == 1`), weshalb jedes
v.-Chr.-Jahr beim Anlegen *und* beim Parsen des Literals eine Warnung samt
Traceback schreibt. Bei den aktuellen Daten betrifft das acht Literale.

Das Literal selbst ist korrekt — nachgeprüft mit genau dieser Version:

```
Literal("-0016", datatype=XSD.gYear).n3()
→ "-0016"^^<http://www.w3.org/2001/XMLSchema#gYear>
```

Nur `.value` bleibt `None`. Folgenlos, weil keine Abfrage auf `gYear`
rechnet. Ab rdflib 7.5 ist der Konverter entfernt und es schweigt
ohnehin.

`py/ips_compat.py` unterdrückt **genau diese eine Meldung** und sonst
nichts — ein pauschales Stummschalten von `rdflib.term` wäre falsch, dort
landen auch Meldungen, die man sehen will. Die Anzahl betroffener
Literale gibt `main.py` stattdessen aus, damit sie sichtbar bleibt statt
bloß stummgestellt zu sein.

## Byte-stabile SVGs

`SOURCE_DATE_EPOCH` und ein fester `svg.hashsalt` sorgen dafür, dass ein
Rebuild ohne inhaltliche Änderung identische Dateien erzeugt. Sonst
schriebe matplotlib bei jedem Lauf einen neuen Zeitstempel und neu
gewürfelte Element-IDs, und beide Abbildungen stünden dauerhaft als
geändert in `git status` — eine Datei, deren Diff immer rot ist, ist eine
Datei, deren Diff niemand mehr liest.

## Lizenz und Zitierbarkeit

Code unter **MIT**, siehe `LICENSE`. Die Metadaten für die Zitation stehen
in `CITATION.cff`; GitHub und Zenodo lesen die Datei direkt aus.

**Die Daten sind davon unabhängig.** Sie stammen aus Samian Research /
IPS und nicht aus eigener Erhebung — die MIT-Lizenz deckt nur den Code.
Wie die Datenbank zu zitieren und unter welcher Lizenz sie nachzunutzen
ist, gehört vor der Veröffentlichung geklärt; in `CITATION.cff` steht
dafür ein `references`-Block bereit.

Sieben Stellen sind noch offen und als `TODO` markiert: die ORCID des
Fachautors, das Release-Datum, die Repo-URL, der Zenodo-DOI sowie
Herausgeber und URL der Quelldatenbank. Und eine Entscheidung, die ich
nicht treffen kann: als Fachautor ist derzeit **Allard Mees** eingetragen,
weil er in diesem Projekt der Ansprechpartner ist — falls jemand anderes
genannt gehört, ist das die Zeile, die geändert werden muss.

Die Hausvorlage der `wdt-*`-Repos führt standardmäßig Fiona Schenk als
Fachautorin. Das ist hier bewusst **nicht** übernommen: sie gehört zum
WD1-Speläothem-Paper, nicht zu Samian Research.

`.gitignore` ignoriert `__pycache__`, virtuelle Umgebungen und
Editor-Artefakte. `data/`, `rdf/`, `img/` und `docs/` bleiben **bewusst
versioniert** — sie sind das Ergebnis und müssen diffbar sein. Genau
deshalb sind die SVGs byte-stabil.
