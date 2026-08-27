-- =====================================================================
-- IPS Dated Sites — breit datierte Toepfer, Waechterabfrage
-- =====================================================================
--
--   psql:  \encoding UTF8
--          \i sql/wide_potters.sql
--
--   Diese Datei filtert nichts. Sie fragt. Sie ist die Vorstufe zu jeder
--   weiteren Ergaenzung der Platzhalterliste in sql/IPSDatedSites.sql und
--   gehoert deshalb daneben, nicht hinein: das Modellstatement bleibt ein
--   einziges Statement, das py/make_sql.py in seine beiden Zielformen
--   rendert.
--
-- WAS SIE BEANTWORTET
-- -------------------
--   Welche Toepfer sind auf 100 Jahre oder mehr datiert, ohne dass
--   entschieden waere, was das bedeutet?
--
--   Drei Faelle sind zu unterscheiden, und nur der dritte ist offen:
--
--     Platzhalter   Die elf (datemin, datemax)-Paare aus dem Modell.
--                   Keine Produktionszeit, sondern "nicht bestimmt".
--                   Sie fliegen im Modellstatement raus.
--     Geprueft      Echte Toepfer mit tatsaechlich breiter Datierung.
--                   Von Allard Mees durchgesehen und ausdruecklich
--                   behalten. Sie bleiben im Korpus und verbreitern
--                   die Intervalle ihrer Fundstellen zu Recht.
--     Offen         Alles Uebrige. Was diese Abfrage ausgibt, hat noch
--                   niemand angesehen.
--
--   Die Schwelle von 100 Jahren ist von Allard Mees am 2026-08-25
--   ausdruecklich bestaetigt und wird NICHT enger gesetzt: Toepfer wie
--   Calvus i haben in mehreren Produktionszentren gearbeitet, und ohne
--   chemisch-mineralogische Untersuchung lassen sich Verschleppung,
--   Vater/Sohn, Einzelperson und Werkstatt nicht trennen. Die Schwelle
--   markiert die Grenze der moeglichen Genauigkeit, nicht eine Toleranz.
--
-- WIE SIE ZU LESEN IST
-- --------------------
--   Leeres Ergebnis = nichts Neues seit der letzten Durchsicht.
--   Zeilen = entweder ein neuer Platzhalter, der in die Ausschlussliste
--   des Modellstatements gehoert, oder ein echter Toepfer, der in die
--   geprueft-Liste hier gehoert. Die Entscheidung ist archaeologisch und
--   faellt nicht hier.
--
--   Die Spalte anzahl ist die Zahl der Datensaetze in tblpotter, nicht
--   die Zahl der Stempel im Korpus: ein Toepfer, der oben steht, muss
--   nicht haeufig gefunden sein. Fundstellengenau zaehlen die Spalten
--   n_stamps_wide, n_potters_wide und max_potter_span im Modell.
--
--   Formuliert von Allard Mees, Revision 31, 2026-08-27.
-- =====================================================================

WITH ausschluss(dmin, dmax) AS (VALUES
    -- Identisch mit der Paarliste in sql/IPSDatedSites.sql. Zwei Kopien,
    -- weil die beiden Statements getrennt laufen; weichen sie
    -- voneinander ab, meldet diese Abfrage Toepfer, die das Modell
    -- laengst draussen hat, und der Fehler faellt genau hier auf.
    (-30,150),(0,100),(0,120),(0,130),(0,150),
    (0,180),(0,270),(100,200),(150,270),(160,260),(165,270)
),
geprueft(dmin, dmax) AS (VALUES
    -- Geprueft und bewusst behalten: echte Toepfer mit breiter
    -- Datierung. Stand der Durchsicht von Allard Mees, 2026-08-27.
    (150,260),(140,270),(10,120),(1,120),
    (150,250),(180,300),(120,245),(155,260)
)
SELECT pottername, p.datemin, p.datemax,
       p.datemax - p.datemin AS spanne,
       COUNT(*) AS anzahl
FROM tblpotter p
WHERE p.datemax - p.datemin >= 100
  AND (p.datemin, p.datemax) NOT IN (SELECT dmin, dmax FROM ausschluss)
  AND (p.datemin, p.datemax) NOT IN (SELECT dmin, dmax FROM geprueft)
GROUP BY 1, 2, p.datemax
ORDER BY anzahl DESC;
