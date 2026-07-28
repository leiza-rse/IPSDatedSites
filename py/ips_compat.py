"""
IPS Dated Sites — compatibility with older rdflib versions
==========================================================

rdflib 7.1.x maps `xsd:gYear` onto Python's `datetime.date`, which cannot
represent years before 1 (`datetime.MINYEAR == 1`). EVERY pre-Christian
year therefore writes a warning and a traceback to the console, both when
the literal is created and when it is parsed:

    Failed to convert Literal lexical form to value.
    Datatype=...XMLSchema#gYear ... ValueError: year -16 is out of range

Affected here are the eight instants of the six pre-Christian findspots,
and the year 0000 (= 1 BC in astronomical counting).

IMPORTANT: the literal itself is correct in every case and is serialised
correctly — checked against rdflib 7.1.1:

    Literal("-0016", datatype=XSD.gYear).n3()
    -> "-0016"^^<http://www.w3.org/2001/XMLSchema#gYear>

Only `.value` stays None, which is of no consequence here because no query
computes on gYear: the usable time value sits on the `time:TimePosition`
as `time:numericPosition`, and `time:inXSDgYear` is the courtesy for
consumers that read calendar years only.

From rdflib 7.5 the converter is gone and the noise stops by itself.

This filter therefore suppresses EXACTLY that one message and nothing
else. Silencing `rdflib.term` wholesale would be the wrong fix — messages
worth seeing arrive on the same logger.
"""

from __future__ import annotations

import logging


class _GYearConversionNoise(logging.Filter):
    """Lets everything through except the gYear conversion warning."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not ("XMLSchema#gYear" in msg
                    and "Failed to convert Literal" in msg)


_installed = False


def silence_gyear_warnings() -> None:
    """Install the filter once. Calling this repeatedly is harmless."""
    global _installed
    if not _installed:
        logging.getLogger("rdflib.term").addFilter(_GYearConversionNoise())
        _installed = True


def count_bc_gyears(graph) -> int:
    """
    Count the BC years written out.

    Reported by main.py so that the affected literals stay visible rather
    than merely silenced.
    """
    from rdflib.namespace import XSD

    n = 0
    for o in graph.objects(None, None):
        if getattr(o, "datatype", None) == XSD.gYear:
            lex = str(o)
            if lex.startswith("-") or lex == "0000":
                n += 1
    return n
