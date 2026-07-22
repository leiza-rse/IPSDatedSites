"""
IPS Dated Sites — Kompatibilitaet mit aelteren rdflib-Versionen
===============================================================

rdflib 7.1.x bildet `xsd:gYear` auf Pythons `datetime.date` ab. Das kann
keine Jahre vor 1 darstellen (`datetime.MINYEAR == 1`), weshalb JEDES
vorchristliche Jahr beim Anlegen und beim Parsen des Literals eine
Warnung samt Traceback auf die Konsole schreibt:

    Failed to convert Literal lexical form to value.
    Datatype=...XMLSchema#gYear ... ValueError: year -16 is out of range

Betroffen sind bei uns die acht Instants der sechs vorchristlichen
Fundstellen sowie die Jahreszahl 0000 (= 1 v. Chr. in astronomischer
Zaehlung).

WICHTIG: das Literal selbst ist in allen Faellen korrekt und wird
korrekt serialisiert — nachgeprueft mit rdflib 7.1.1:

    Literal("-0016", datatype=XSD.gYear).n3()
    -> "-0016"^^<http://www.w3.org/2001/XMLSchema#gYear>

Nur `.value` bleibt None. Das ist fuer uns folgenlos, weil keine Abfrage
auf gYear rechnet: die verwertbare Zeitangabe steht als
`time:numericPosition` an der `time:TimePosition`, `time:inXSDgYear` ist
die Beigabe fuer Konsumenten, die nur Kalenderjahre lesen.

Ab rdflib 7.5 ist der Konverter entfernt, dort schweigt es ohnehin.

Dieser Filter unterdrueckt deshalb GENAU diese eine Meldung und nichts
sonst. Ein pauschales Stummschalten von `rdflib.term` waere die falsche
Loesung — dort landen auch Meldungen, die man sehen will.
"""

from __future__ import annotations

import logging


class _GYearConversionNoise(logging.Filter):
    """Laesst alles durch ausser der gYear-Konvertierungswarnung."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not ("XMLSchema#gYear" in msg
                    and "Failed to convert Literal" in msg)


_installed = False


def silence_gyear_warnings() -> None:
    """Einmalig den Filter setzen. Mehrfachaufruf ist unschaedlich."""
    global _installed
    if not _installed:
        logging.getLogger("rdflib.term").addFilter(_GYearConversionNoise())
        _installed = True


def count_bc_gyears(graph) -> int:
    """
    Zaehlt die geschriebenen v.-Chr.-Jahreszahlen.

    Wird von main.py ausgegeben, damit die betroffenen Literale sichtbar
    bleiben, statt bloss stumm gestellt zu sein.
    """
    from rdflib.namespace import XSD

    n = 0
    for o in graph.objects(None, None):
        if getattr(o, "datatype", None) == XSD.gYear:
            lex = str(o)
            if lex.startswith("-") or lex == "0000":
                n += 1
    return n
