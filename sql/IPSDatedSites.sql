-- =====================================================================
-- IPS Sites — IPSDatedSites27c  (Findspot-Ebene)
-- Nachfolger von IPSDatedSites26.sql. PostgreSQL.
--
-- 27a gegenueber 27: zwei Aenderungen, beide dokumentarisch bzw. auf die
-- Nachrechenbarkeit gerichtet — die Zahlen des Plots aendern sich NICHT.
--   * unc_*_years_exact jetzt numeric(10,6) statt (10,3). In 27 scheiterte
--     Kontrolle (h) an 2 von 41 Zeilen um 0.001 (Koeln/Hafen, Saalburg/
--     Erdkastell): q wird aus dem vollen STDDEV_SAMP gerechnet, die exakte
--     Spalte war aber selbst gerundet und kippte die dritte Nachkommastelle.
--     Mit (10,6) schliesst der Rundlauf ziffernidentisch.
--   * Die Begruendung fuer t0 ist ersetzt. Siehe (5).
--
-- 27b gegenueber 27a:
--   * t0 = 20 statt 25, verankert an Allards Angabe (siehe (5)).
--     Das AENDERT die Whiskerfarben, nicht die Rangfolge.
--   * Versuchsweise sigma_expected / q_*_relative als Zusatzachse.
--
-- 27c gegenueber 27b:
--   * Die Zusatzachse ist WIEDER ENTFERNT — sechs Spalten weniger.
--     Der Lauf von 27b hat gezeigt, dass sie einen Effekt ein zweites
--     Mal einrechnet, der schon in der Boxbreite steht, und dass sie
--     ihn an einer Groesse misst, die ihn nicht traegt. Ausfuehrlich
--     unter (6). Spaltensatz damit wieder identisch mit 27a.
--   * midpoint_year jetzt numeric(10,3) statt (10,1) — Praezisionslehre
--     aus Kontrolle (k), siehe dort.
--   * t0 = 20 und die absolute Lesart von q_start/q_end bleiben.
--
-- 30a gegenueber 27c — DIESE DATEI IST DER GOLDSTANDARD
--   Sie ist die einzige autoritative Fassung des Modells. Die Fassung im
--   ColdFusion-Template und die Reimplementierung in py/ips_model.py werden
--   an ihr gemessen, nicht umgekehrt. Der ColdFusion-Drop-in wird aus dieser
--   Datei erzeugt:  python py/make_sql.py
--   Der einzige Unterschied ist :min_stamps, das dort zum <cfqueryparam> wird.
--
--   * tau = 6 statt 20. Empirisch kalibriert an fuenf keramikunabhaengig
--     datierten Referenzfundstellen (Dangstetten, Oberaden, Velsen I,
--     Pompeii, Inchtuthil). Allard hat diese Herleitung am 2026-08-25
--     bestaetigt und ihre Offenlegung in der Publikation verlangt: nur
--     diese fuenf Fundorte sind wirklich keramikunabhaengig datiert.
--   * t0 bleibt 20. tau und t0 sind verschiedene Groessen und tragen seit
--     der Kalibrierung verschiedene Werte; sie waren nur zufaellig einmal
--     gleich. Der Zwischenstand, in dem beide auf 6 standen, ist ein
--     Fehler und in keinem Export mehr enthalten.
--   * k kommt aus COUNT(di.number), nicht mehr aus SUM(stamps_pp) der
--     kfactor-CTE. Damit haengt die Geometrie nicht mehr an der
--     Vollstaendigkeit der Stempeltyp-Erfassung, und der COALESCE-Fallback
--     auf k_max entfaellt strukturell: COUNT(*) kann nicht NULL werden.
--     Vorher konnte eine Fundstelle ohne Die-Angabe die breiteste
--     zulaessige Box bekommen, obwohl ihre Datierung nichts dafuer hergab
--     (Pompeii/Hoard: 9.2 a -> 25.4 a).
--   * k_is_fallback -> k_no_dierecord. Reine Warnlampe fuer fehlende
--     Stempeltyp-Erfassung, ohne Geometriewirkung.
--   * Die elf Platzhalter-Datierungspaare ersetzen den alten Filter
--     datemax NOT IN (260,120,150). Paarlogik statt AND-Logik.
--   * Griechische Marker durchgehend als U&-Escape.
--   * kfactor-Join getrimmt und case-insensitiv.
--   * Die geprueften Breitdatierungen stehen seit 31 in
--     sql/wide_potters.sql: acht (datemin, datemax)-Paare, die Allard
--     durchgesehen und ausdruecklich behalten hat. Diese Datei filtert
--     nichts, sie fragt -- sie listet breit datierte Toepfer, die weder
--     Platzhalter noch geprueft sind, und ist damit die Vorstufe zu
--     jeder weiteren Ergaenzung der Platzhalterliste.
--   * n_stamps_wide / n_potters_wide / max_potter_span als Waechter am
--     Ende der Spaltenliste. Schwelle 100 Jahre, von Allard am 2026-08-25
--     ausdruecklich bestaetigt: Toepfer wie Calvus i haben in mehreren
--     Produktionszentren gearbeitet, und ohne chemisch-mineralogische
--     Untersuchung laesst sich Verschleppung, Vater/Sohn, Einzelperson
--     und Werkstatt nicht trennen. Die Schwelle markiert die Grenze der
--     moeglichen Genauigkeit und wird deshalb NICHT enger gesetzt.
--   * Bregenz, dritte Fassung (2026-08-27, Revision 31). Der pauschale
--     Ausschluss ist entfallen und durch eine gezielte Einschlussklausel
--     ersetzt: die vier geprueften Fundkomplexe bleiben, die uebrigen,
--     noch ungepruefteten Records des Ortes nicht. 25 waren es die drei
--     Boeckleareal-Komplexe; 31 kommt 'Samian Hoard 1913' hinzu. Der
--     Korpus waechst damit von 40 auf 41 Fundstellen, sobald der naechste
--     Live-Abzug die Zeilen mitbringt -- die Klausel steht hier, der
--     Datenstand in data/SNAPSHOT.json. Das ist eine
--     editorische Uebergangsloesung und keine Dauerform -- richtig waere,
--     geprueft und ungeprueft in der Datenbank zu markieren und den
--     regulaeren Filter entscheiden zu lassen, statt einen Ortsnamen im
--     SQL zu fuehren. Kontrolle (e) in py/verify.py schlaegt an, wenn die
--     Klausel ins Leere greift, weil sich eine Schreibweise geaendert hat.
--     Urspruengliche Begruendung fuer den Wegfall des Pauschalausschlusses:
--     Samian Research ist eine
--     Live-Datenbank; ungeprüfte Fundstellen wird es immer geben und neue
--     kommen laufend hinzu. Einzelne Orte im SQL auszuschliessen ist dafuer
--     das falsche Mittel. Stattdessen wird der Abzugsstand festgehalten
--     (data/SNAPSHOT.json) und in der Publikation als "Stand Datum x"
--     genannt. Wer dennoch ausschliessen will, tut das als Parameter:
--     py/ips_model.py --exclude-site NAME.
--
-- Eine Ausgabezeile = ein Findspot.
-- =====================================================================
--
-- DOPPELTE VERWENDUNG — derselbe SELECT, zwei Wege:
--
--   a) CSV AUS DER DATENBANK
--      In psql, mit UTF-8-Client (wegen der Literale 'Θ' und 'Σ'):
--          \encoding UTF8
--          \copy ( <kompletter SELECT ohne Semikolon> ) TO 'sites.csv' WITH (FORMAT csv, HEADER)
--      In pgAdmin: SELECT ausfuehren, dann "Download as CSV".
--      NULL erscheint als leere Zelle — das ist so gewollt, siehe (2).
--
--   b) DROP-IN INS CFM
--      Ersetzt den Inhalt zwischen
--          <cfquery name="qDating" datasource="#DATASOURCE#">
--      und
--          </cfquery>
--      Sonst ist am CFM NICHTS zu aendern: `rows` wird namentlich
--      aufgebaut und ignoriert die fuenf neuen Spalten stillschweigend,
--      der JS-Code faengt NULLs bereits ab.
--
-- =====================================================================
-- DIE AENDERUNG GEGENUEBER 26 — (5) q_start / q_end
-- =====================================================================
--
--   BISHER:  q = EXP(-( STDDEV_SAMP(datemin) / ABS(AVG(datemin)) ))
--   JETZT:   q = EXP(-( STDDEV_SAMP(datemin) / t0 ))     -- t0 = 20 Jahre
--
--   WARUM. Der alte Nenner ist der Abstand vom Kalender-Nullpunkt. Damit
--   misst q nicht die Datierungsschaerfe, sondern die Epoche. Belegbar
--   aus der eigenen Abbildung (Werte aus dem v2-Plot):
--
--     Amiens, Sq. Bocquet   sigma_end = 15  ->  q_end = 0.00   (dunkelrot)
--     Bregenz, Keller       sigma_end = 29  ->  q_end = 0.77   (gruen)
--
--   Bregenz hat die doppelte Unsicherheit und die bessere Farbe: das Mass
--   ist nicht monoton in sigma. Amiens steht mit n = 41 Stempeln und
--   sigma_start = 7 unter den bestdatierten Fundplaetzen der Abbildung.
--   Die roten Balken im augusteischen Block sind ausschliesslich dieser
--   Division geschuldet, nicht dem Material.
--
--   Zwei Defekte stecken darin:
--     - keine Translationsinvarianz: dieselben Daten in a.u.c. gerechnet
--       ergaeben andere q-Werte. Ein Qualitaetsmass darf das nicht.
--     - linker und rechter Whisker DERSELBEN Zeile haben verschiedene
--       Nenner (|AVG(datemin)| vs. |AVG(datemax)|), bei Amiens etwa
--       1 : 20 — und werden trotzdem aus einer Farbrampe bedient.
--
--   WAS t0 IST — UND WAS NICHT.
--   t0 ist die Laenge, bei der q auf 1/e ~ 0.37 faellt. Es ist eine
--   KONSTANTE DER FARBSKALA, keine archaeologische Groesse. Eine
--   fruehere Fassung dieses Kommentars begruendete t0 = 25 mit
--   "eine Generation / eine Toepfer-Produktionsphase". Das war falsch
--   und ist hiermit zurueckgenommen: die IPS-Daten unterscheiden nicht
--   zwischen Einzeltoepfer und Firmenname, also darf t0 auch keine
--   Aussage darueber transportieren.
--
--   Der Grund, warum das folgenlos bleibt: exp(-sigma/t0) ist fuer JEDES
--   t0 > 0 streng monoton fallend in sigma. Die RANGFOLGE der Fundplaetze
--   nach q ist damit vollstaendig t0-invariant (an den 41 Zeilen geprueft:
--   Spearman = 1.000000 zwischen t0 = 10 und t0 = 100). t0 aendert die
--   Zahlen und damit die Farben, nie die Ordnung, nie eine Entscheidung.
--   Deshalb ist es dokumentationspflichtig, aber nicht begruendungspflichtig.
--
--   WAHL VON t0 = 20 — VERANKERT (neu in 27b).
--   Fachliche Vorgabe (A. Mees): eine Streuung von rund +/- 5 Jahren gilt
--   fuer terra sigillata als scharf datiert, rund +/- 25 Jahre als
--   unbrauchbar. Das sind zwei Bedingungen an eine einparametrige Kurve,
--   also ueberbestimmt — t0 = 20 trifft beide gut:
--
--       t0    q(sigma=5)   q(sigma=25)
--       15      0.72          0.19
--       20      0.78          0.29     <- gewaehlt
--       25      0.82          0.37
--       30      0.85          0.43
--
--   Bei t0 = 25 landet "unbrauchbar" auf 0.37 und damit auf der Rampe
--   noch im Gelb-Orangen — sichtbar zu freundlich. t0 = 20 legt "scharf"
--   klar ins Gruene und "unbrauchbar" klar ins Rote.
--
--   Damit ist t0 an eine Aussage ueber DATIERUNGSGUETE gebunden, nicht an
--   eine ueber Toepferbiographien. Die IPS-Daten unterscheiden nicht
--   zwischen Einzeltoepfer und Firmenname; diese Frage beruehrt t0 auch
--   nicht — sie steckt in w = datemax - datemin und wird ueber den Term
--   mean(w^2/12) in sigma_eff korrekt absorbiert.
--
--   t0 IST BEWUSST NICHT AUS DEN DATEN ABGELEITET. Ein datengetriebenes
--   t0 (Median/ln 2 = 12.6 a) wuerde sich bei jedem DB-Stand aendern:
--   dieselbe Streuung bekaeme in zwei Laeufen zwei q-Werte, und die
--   Abbildung waere zwischen Publikationen nicht mehr vergleichbar.
--   Ein externer, erklaerter Anker ist der stabilere Vertrag.
--
--   Verteilung bei t0 = 20 (82 Whisker): Median 0.65, q25 0.54, q75 0.72,
--   Minimum 0.16, 7 % unterhalb 1/3.
--
-- =====================================================================
-- (6) KEINE EPOCHENKORREKTUR — UND WARUM NICHT
-- =====================================================================
--
--   BEFUND (A. Mees): die Datierung wird im 2. und 3. Jh. n. Chr.
--   unschaerfer, und zwar bei Anfangs- WIE Enddaten. Ursache ist nicht
--   das Material der einzelnen Fundstelle, sondern der Rahmen: es fehlen
--   historisch fixierte Anker wie Pompeji (AD 79) oder Inchtuthil, und
--   es gibt insgesamt deutlich weniger datierte Fundplaetze.
--
--   27b hat versucht, das ueber ein epochenabhaengiges t0 abzubilden
--   (Spalten sigma_expected, q_*_relative). DAS WAR FALSCH, aus zwei
--   Gruenden, die der erste Lauf beide gezeigt hat.
--
--   ERSTENS: unc_start / unc_end tragen den Effekt gar nicht.
--
--       sigma_eff    = 10.62 +0.0350 * Jahr   r = +0.390   R^2 = 0.15
--       unc_start    =  5.15 +0.0545 * Jahr   r = +0.457   R^2 = 0.21
--       unc_end      = 11.24 -0.0060 * Jahr   r = -0.058   R^2 = 0.00
--
--   unc_start / unc_end messen die Streuung ZWISCHEN den Toepfern eines
--   Fundplatzes. Fehlende Anker machen die Toepfer aber nicht unter-
--   einander uneiniger, sondern JEDES EINZELNE Toepferintervall breiter.
--   Diese Breite w = datemax - datemin steckt in mean(w^2/12) und damit
--   in sigma_eff — genau dem Term, den die Varianzzerlegung von der
--   Zwischen-Toepfer-Streuung trennt. unc_end kann den Effekt nicht
--   sehen; eine Korrektur, die dort ansetzt, korrigiert ins Leere.
--
--   ZWEITENS: der Effekt STEHT SCHON IN DER ABBILDUNG. sigma_eff
--   bestimmt die Boxbreite, und beide von Allard genannten Ursachen
--   kommen getrennt an:
--
--       fehlende Anker  -> breitere w -> sigma_eff steigt
--       weniger Material -> weniger Stempel -> k_eff steigt
--
--                            AD 1     AD 200
--       sigma_eff            10.7 a    17.6 a
--       k_eff                 0.9       1.0
--       Boxbreite            18.1 a    34.6 a     r = +0.431
--
--       Median Boxbreite  vor AD 100  19.8 a  /  ab AD 100  32.1 a
--       Median k_eff      vor AD 100  0.817   /  ab AD 100  1.107
--       Median count_stamps vor AD 100   23   /  ab AD 100     10
--
--   Die Volumenkorrektur (k_eff) faengt die duennere Materialbasis der
--   Spaetzeit also von selbst mit ab. Ein epochenabhaengiges t0 haette
--   denselben Sachverhalt ein zweites Mal eingerechnet.
--
--   MESSBAR SCHLECHTER: in 27b stieg die Epochenabhaengigkeit von q_end
--   durch die "Korrektur" von r = +0.103 auf r = +0.335. Sie hat das
--   Problem vergroessert, das sie loesen sollte.
--
--   Allards Anker sind in den Daten uebrigens direkt sichtbar. Die drei
--   kleinsten sigma_eff aller 41 Fundplaetze sind flavisch:
--       Nijmegen, Barbarossastraat  AD 75   5.77
--       Koeln, Hafen                AD 80   6.52
--       Pompeii, Hoard              AD 75   8.47
--   Und die Dichte bricht dort ein, wo er es sagt: 27.5 Fundplaetze pro
--   Jahrhundert zwischen AD 20 und 100, dann 5.0 (AD 100-140) und 1.2
--   (nach AD 180).
--
--   ENTSCHEIDUNG: q_start und q_end bleiben ABSOLUT. Dass die Whisker
--   im 2. und 3. Jh. roter werden, ist gewollt und archaeologisch
--   zutreffend (A. Mees: "je juenger, desto roter" — die Daten sind
--   dort generell fuzzier). Die Abbildung soll diesen Befund ZEIGEN,
--   nicht wegnormalisieren.
--
--   Das ist dieselbe Entscheidung wie bei q_interval / q_repetition:
--   Achsen nebeneinander statt Kompositmass. Inchtuthil hat gezeigt,
--   was das Verrechnen kostet.
--
--   VORBEHALT: n = 41, R^2 zwischen 0.00 und 0.21. Das sind Tendenzen,
--   keine Gesetze. Sie tragen die Entscheidung, KEINE Korrektur
--   einzubauen — fuer den umgekehrten Schluss waeren sie zu duenn.
--
-- STELLSCHRAUBEN: k_min = 0.5, k_max = 1.5, tau = 6, w = 1.0, t0 = 20
-- SKALENKONSTANTE: t0 = 20 (Farbskala, verankert, siehe (5))
-- KEINE EPOCHENKORREKTUR — bewusst, siehe (6)
-- =====================================================================

-- :min_stamps
--   Mindestzahl Stempel je Fundensemble; editorische Anzeigeschwelle, kein
--   Datenfilter. In psql:  \set min_stamps 1   bzw. python py/make_sql.py
--   setzt fuer den psql-Lauf 1 ein und fuer ColdFusion den cfqueryparam.
WITH params AS (
    SELECT 0.5::numeric AS k_min,
           1.5::numeric AS k_max,
          6.0::numeric AS tau,		-- war 20.0, empirisch kalibriert
           1.0::numeric AS w,       -- reines Volumen
          20.0::numeric AS t0       -- (5) verankert an Allards 5 / 25 a
),
diecounts AS (
    SELECT
        di.site     AS the_site,
        di.findspot AS the_findspot,
        di.pottername,
        COUNT(DISTINCT di.die) AS dies_pp,
        COUNT(*)               AS stamps_pp
    FROM tbldistribution AS di
    LEFT JOIN tblpotter p ON lower(trim(di.pottername)) = lower(trim(p.pottername))
    -- 30a (3): U&-Escape statt UTF-8-Literal, wie im aeusseren WHERE
    WHERE di.isdate = U&'\0398' AND di.sitecharacter = U&'\03A3'
      AND di.findspot IS NOT NULL
      AND (p.datemin, p.datemax) NOT IN (
          (-30,150), (0,100), (0,120), (0,130), (0,150),
          (0,180), (0,270), (100,200), (150,270),
          (160,260), (165,270) )
      -- Bregenz: die vier geprueften Fundkomplexe bleiben drin, die
      -- uebrigen, noch ungepruefteten Records des Ortes nicht.
      -- Formuliert von Allard Mees am 2026-08-25, 31 ergaenzt um
      -- 'Samian Hoard 1913'. U&-Escape statt rohem
      -- Umlaut aus demselben Grund wie bei Theta und Sigma: das Statement
      -- bleibt reines ASCII und haengt nicht daran, welche Kodierung die
      -- Verbindung gerade meint.
      AND (
            di.site NOT ILIKE '%Bregenz%'
         OR btrim(di.findspot) IN (
                U&'B\00F6ckleareal (period I)',
                U&'B\00F6ckleareal (period II)',
                U&'B\00F6ckleareal (destruction layer period II)',
                U&'Samian Hoard 1913')
          )
      AND di.die IS NOT NULL
    GROUP BY di.site, di.findspot, di.pottername
),
kfactor AS (
    SELECT the_site, the_findspot,
        SUM(dies_pp)   AS n_dies,
        SUM(stamps_pp) AS n_stamps_die,
        ROUND(SUM(stamps_pp)::numeric / NULLIF(SUM(dies_pp),0), 3) AS rep,
        ( (SELECT k_max FROM params)
          - ((SELECT k_max FROM params) - (SELECT k_min FROM params))
            * (1 - EXP(-SUM(stamps_pp)::numeric / (SELECT tau FROM params)))
        )::numeric(10,4) AS k_eff
    FROM diecounts
    GROUP BY the_site, the_findspot
)
SELECT
    vds.id                                   AS the_id,
    di.site                                  AS the_site,
    di.findspot                              AS the_findspot,
    di.siteancientname                       AS latinsitename,
    di.coordinate1                           AS long,
    di.coordinate2                           AS lat,
    di.pleiades,

    COUNT(di.number)                         AS count_stamps,

    AVG(p.datemin)::integer                  AS avg_datemin,
    AVG(p.datemax)::integer                  AS avg_datemax,

    MIN(p.datemin)::integer                  AS min_datemin,
    MAX(p.datemin)::integer                  AS max_datemin,
    MIN(p.datemax)::integer                  AS min_datemax,
    MAX(p.datemax)::integer                  AS max_datemax,

    -- (5) GEAENDERT: epochenunabhaengig, gemeinsame Referenzlaenge t0.
    --     NULL bleibt NULL (n = 1 -> STDDEV_SAMP NULL -> grau), wie (2).
    --     sigma = 0 -> q = 1.000 (Nijmegen), monoton fallend in sigma.
    ROUND(EXP(-(STDDEV_SAMP(p.datemin) / (SELECT t0 FROM params))), 3) AS q_start,
    ROUND(EXP(-(STDDEV_SAMP(p.datemax) / (SELECT t0 FROM params))), 3) AS q_end,


    -- q_interval  ==  q_spread  (Datierungsqualitaet, Achse 1)
    -- unveraendert: Nenner ist eine Differenz, also translationsinvariant
    ROUND(
        CASE WHEN (AVG(p.datemax) - AVG(p.datemin)) = 0 THEN NULL
        ELSE EXP(-(SQRT(VAR_SAMP(p.datemin) + VAR_SAMP(p.datemax)) /
             ABS(AVG(p.datemax) - AVG(p.datemin)))) END, 3) AS q_interval,

    -- Depot-Charakter (Achse 2, deskriptiv, bewusst nicht verrechnet)
    MIN(k.n_dies) AS n_dies,
    MIN(k.rep)    AS die_repetition,
    CASE WHEN MIN(k.rep) IS NULL THEN NULL
         ELSE ROUND(1 - 1.0/GREATEST(MIN(k.rep),1), 3) END AS q_repetition,

    ROUND(AVG(p.datemin),0)::text || ' to ' ||
    ROUND(AVG(p.datemax),0)::text            AS avg_interval,

    -- (2) ohne COALESCE. Gerundet, wie bisher — der Plot zeichnet damit.
    STDDEV_SAMP(p.datemin)::integer          AS unc_start_years,
    STDDEV_SAMP(p.datemax)::integer          AS unc_end_years,
    SQRT(VAR_SAMP(p.datemin) + VAR_SAMP(p.datemax))::integer
                                             AS unc_interval_years,

    -- (5) NEU: unverrundet, damit q_start/q_end aus dem Export exakt
    --     nachrechenbar sind. Siehe Kontrollpunkt (h).
    -- 27a: (10,6) statt (10,3), damit Kontrolle (h) ziffernidentisch
    --      schliesst und nicht an der Rundung der Pruefspalte scheitert.
    STDDEV_SAMP(p.datemin)::numeric(10,6)    AS unc_start_years_exact,
    STDDEV_SAMP(p.datemax)::numeric(10,6)    AS unc_end_years_exact,

    -- 27c: (10,3) statt (10,1). midpoint_year wird weder geplottet noch
    --      in der HTML-Tabelle ausgegeben; die Stellen dienen allein der
    --      Nachrechenbarkeit (Praezisionslehre aus Kontrolle (k)).
    ((AVG(p.datemin) + AVG(p.datemax)) / 2.0)::numeric(10,3)
                                             AS midpoint_year,

    -- (1) PROV: die Groessen, aus denen eff_* entsteht
    -- 30a (1): n_stamps_die bleibt deskriptiv (nur Stempel mit
    --          Typzuweisung) und geht NICHT mehr in k ein.
    MIN(k.n_stamps_die)                      AS n_stamps_die,

    -- 30a (1): k allein aus dem Stempelvolumen der Fundstelle.
    --          k = k_max - (k_max - k_min) * (1 - exp(-n / tau))
    --          Kein COALESCE mehr noetig: COUNT(*) ist nie NULL.
    ( (SELECT k_max FROM params)
      - ((SELECT k_max FROM params) - (SELECT k_min FROM params))
        * (1 - EXP(-COUNT(di.number)::numeric / (SELECT tau FROM params)))
    )::numeric(10,4)                         AS k_eff,

    -- 30a (2): Waechter ohne Geometriewirkung. TRUE = fuer diese
    --          Fundstelle liegt keine Stempeltyp-Erfassung vor,
    --          n_dies/die_repetition/q_repetition sind dann NULL.
    (MIN(k.k_eff) IS NULL)                   AS k_no_dierecord,
    SQRT( AVG(POWER(p.datemax - p.datemin, 2) / 12.0)
          + COALESCE(VAR_SAMP((p.datemin + p.datemax) / 2.0), 0)
    )::numeric(10,3)                         AS sigma_eff,

    -- (4) Modellparameter mitliefern
    (SELECT k_min FROM params)::numeric(10,3) AS p_k_min,
    (SELECT k_max FROM params)::numeric(10,3) AS p_k_max,
    (SELECT tau   FROM params)::numeric(10,3) AS p_tau,
    (SELECT w     FROM params)::numeric(10,3) AS p_w,
    (SELECT t0    FROM params)::numeric(10,3) AS p_t0,

    -- eff: Mitte +/- k(findspot) * sigma_eff ,  k = reines Volumen (w = 1.0)
    -- 30a (1): identischer k-Ausdruck wie oben, kein Fallback mehr.
    ( (AVG(p.datemin) + AVG(p.datemax)) / 2.0
      - ( (SELECT k_max FROM params)
          - ((SELECT k_max FROM params) - (SELECT k_min FROM params))
            * (1 - EXP(-COUNT(di.number)::numeric / (SELECT tau FROM params))) )
        * SQRT( AVG(POWER(p.datemax - p.datemin, 2) / 12.0)
                + COALESCE(VAR_SAMP((p.datemin + p.datemax) / 2.0), 0) )
    )::numeric(10,1)                         AS eff_start,
    ( (AVG(p.datemin) + AVG(p.datemax)) / 2.0
      + ( (SELECT k_max FROM params)
          - ((SELECT k_max FROM params) - (SELECT k_min FROM params))
            * (1 - EXP(-COUNT(di.number)::numeric / (SELECT tau FROM params))) )
        * SQRT( AVG(POWER(p.datemax - p.datemin, 2) / 12.0)
                + COALESCE(VAR_SAMP((p.datemin + p.datemax) / 2.0), 0) )
    )::numeric(10,1)                         AS eff_end,

    -- 30a (6): Waechterspalten ans Ende, Spaltenreihenfolge 29 bleibt
    --          als Praefix erhalten. Breit datierte Toepfer,
    --          fundstellengenau: nach dem Filtern sollten das nur noch
    --          die geprueften Faelle sein; taucht hier etwas Neues auf,
    --          gehoert es angesehen.
    COUNT(di.number) FILTER (
        WHERE p.datemax - p.datemin >= 100)  AS n_stamps_wide,
    COUNT(DISTINCT p.pottername) FILTER (
        WHERE p.datemax - p.datemin >= 100)  AS n_potters_wide,
    MAX(p.datemax - p.datemin)               AS max_potter_span

FROM tbldistribution AS di
LEFT JOIN tblpotter        p   ON lower(trim(di.pottername)) = lower(trim(p.pottername))
LEFT JOIN v_discoverysite  vds ON di.site = vds.label
-- 30a (4): getrimmt und case-insensitiv, analog zum Toepfer-Join
LEFT JOIN kfactor          k   ON lower(trim(k.the_site))     = lower(trim(di.site))
                              AND lower(trim(k.the_findspot)) = lower(trim(di.findspot))
WHERE di.isdate = U&'\0398' AND di.sitecharacter = U&'\03A3' AND findspot IS NOT NULL
AND (p.datemin, p.datemax) NOT IN (
      (-30,150), (0,100), (0,120), (0,130), (0,150),
      (0,180), (0,270), (100,200), (150,270),
      (160,260), (165,270) )
  -- Bregenz: die vier geprueften Fundkomplexe bleiben drin, die
  -- uebrigen, noch ungepruefteten Records des Ortes nicht.
  -- Formuliert von Allard Mees am 2026-08-25, 31 ergaenzt um
  -- 'Samian Hoard 1913'. U&-Escape statt rohem
  -- Umlaut aus demselben Grund wie bei Theta und Sigma: das Statement
  -- bleibt reines ASCII und haengt nicht daran, welche Kodierung die
  -- Verbindung gerade meint.
  AND (
    di.site NOT ILIKE '%Bregenz%'
     OR btrim(di.findspot) IN (
        U&'B\00F6ckleareal (period I)',
        U&'B\00F6ckleareal (period II)',
        U&'B\00F6ckleareal (destruction layer period II)',
        U&'Samian Hoard 1913')
      )
GROUP BY vds.id, di.site, di.findspot, di.siteancientname,
         di.coordinate1, di.coordinate2, di.pleiades
HAVING COUNT(di.number) >= :min_stamps

ORDER BY avg_datemin ASC;

-- =====================================================================
-- CSV-EXPORT (nur fuer Weg a — im CFM NICHT mitkopieren)
-- =====================================================================
--   \encoding UTF8
--   \copy (WITH params AS (...) ... ORDER BY avg_datemin ASC) TO 'sites.csv' WITH (FORMAT csv, HEADER)
--
-- Alternativ, wenn Serverzugriff aufs Dateisystem besteht:
--   COPY (...) TO '/tmp/sites.csv' WITH (FORMAT csv, HEADER);
--
-- =====================================================================
-- KONTROLLE NACH DEM ERSTEN LAUF
-- =====================================================================
--   a) Zeilenzahl identisch mit 26?                    (erwartet: ja, 41)
--   b) eff_start / eff_end unveraendert gegenueber 26? (erwartet: ja —
--        (5) fasst die Boxen nicht an)
--   c) k_eff = p_k_max - (p_k_max - p_k_min)
--              * (1 - exp(-count_stamps / p_tau))      (erwartet: exakt)
--        30a: count_stamps, NICHT n_stamps_die. Der Unterschied ist auf
--        dem Korpus vom 2026-08 null, weil beide Zahlen ueberall gleich
--        sind; er wird sichtbar, sobald Stempel ohne Typzuweisung
--        auftreten.
--   d) eff_end - eff_start = 2 * k_eff * sigma_eff     (erwartet: exakt,
--        bis auf die Rundung auf numeric(10,1))
--   e) NULL in q_* / unc_*: dieselben Zeilen wie in 26? (erwartet: ja —
--        q_start/q_end sind weiterhin genau dann NULL, wenn
--        STDDEV_SAMP NULL ist, also bei n = 1)
--   f) k_no_dierecord = true irgendwo? Dann Findspot ohne Stempeltyp-
--        Erfassung. Seit 30a ohne Wirkung auf eff_start/eff_end; die
--        Spalte ist Datenpflege-Hinweis, kein Modellzustand.
--   g) the_id NULL irgendwo? Dann Fundplatz ohne LOD-Knoten.
--
--   (5)-spezifisch:
--   h) q_start = ROUND(exp(-unc_start_years_exact / p_t0), 3)
--      q_end   = ROUND(exp(-unc_end_years_exact   / p_t0), 3)
--                                                      (erwartet: exakt,
--        in ALLEN Zeilen. In 27 mit numeric(10,3) scheiterten 2 von 41
--        um 0.001; mit (10,6) ist das behoben.)
--      Mit unc_start_years statt _exact scheitert der Test weiterhin an
--      der Rundung — das ist kein Fehler, sondern der Grund fuer die
--      beiden Spalten.
--   i) q_start und q_end monoton fallend in sigma? Sortiert nach
--      unc_start_years_exact muss q_start monoton fallen, ueber ALLE
--      Zeilen hinweg. In 26 tat es das nicht — das war der Defekt.
--   j) Stichprobe q_start / q_end bei t0 = 20:
--        Nijmegen, Barbarossastraat  sigma  0.00/ 0.00 -> 1.000 / 1.000
--        Koeln, Hafen                sigma  2.26/ 1.96 -> 0.893 / 0.907
--        Amiens, Sq. Bocquet         sigma  7.05/14.58 -> 0.703 / 0.482
--        Langenhain, store           sigma 36.55/ 3.30 -> 0.161 / 0.848
--
--   (6)-spezifisch:
--   k) sigma_expected / q_*_relative / p_sigma_* NICHT mehr vorhanden?
--        (erwartet: 41 Spalten — 27a-Satz plus die drei Waechter, mit
--         k_no_dierecord an der Stelle des frueheren k_is_fallback)
--   l) Boxbreite (eff_end - eff_start) gegen midpoint_year:
--        r ~ +0.43, Median vor AD 100 ~19.8 a, ab AD 100 ~32.1 a.
--        DAS ist die Epochendrift — sie steht in der Breite, nicht in
--        der Farbe, und braucht deshalb keine Korrektur an q.
--   m) Plot unveraendert gegenueber 27b? (erwartet: ja, vollstaendig.
--        Die entfallenen Spalten wurden von `rows` im CFM nie
--        uebernommen; midpoint_year wird nicht gezeichnet.)
--
--   (c), (d) und (h) sind der eigentliche Test: stimmen sie, sind
--   Intervall UND Whiskerfarbe allein aus den exportierten Zahlen
--   nachrechenbar.
--
-- =====================================================================
-- NOTIZ ZUR FINDSPOT-URI  (bleibt offen, siehe Kopf)
-- =====================================================================
-- Solange kein Findspot-Schluessel existiert, wird die Time-Span-URI aus
-- dem Findspot-Text abgeleitet. Falls die Extension unaccent installiert
-- ist, kann der Schluessel deterministisch hier entstehen statt im CFML
-- — dann sehen CSV und Applikation garantiert denselben Wert:
--
--   lower(regexp_replace(unaccent(trim(di.findspot)), '[^a-zA-Z0-9]+', '_', 'g'))
--       AS findspot_key
--
-- Ungetestet, weil von der Extension abhaengig (CREATE EXTENSION unaccent).
-- Ohne sie im CFML slugifizieren, aber dort mit NFD-Normalisierung, sonst
-- wird aus Koeln wieder "kln".
-- =====================================================================
