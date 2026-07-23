"""
IPS Dated Sites — English documentation source
==============================================

This module is the SINGLE SOURCE for the English prose that describes the
vocabulary. It feeds two consumers:

  1. the ontology itself — build_ontology() emits every entry below as an
     rdfs:comment with xml:lang="en", alongside the German comment. An
     ontology intended for integration into a shared knowledge graph must
     carry English definitions.

  2. the generated documentation — make_docs.py renders docs/*.md from the
     structures in ips_rdf_export.py combined with the prose here.

Because both read the same dictionary, a term cannot be documented in one
place and forgotten in the other. make_docs.py additionally FAILS if a
class or property exists in the code without an entry here, so adding a
property to the export forces a decision about how it is described.

British English throughout.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Terms — keyed by local name, must cover every entry in CLASSES, OBJ_PROPS
# and DATA_PROPS in ips_rdf_export.py
# --------------------------------------------------------------------------
TERM_DOCS: dict[str, str] = {
    # ---- classes ----
    "Location":
        "An existing LADO class, anchored here beneath crm:E53_Place so "
        "that consumers who reason over CIDOC CRM can reach it without "
        "knowing LADO.",
    "DiscoverySite":
        "An existing LADO class from the published loc_discoverysite "
        "dataset. This export references such nodes; it never re-types or "
        "redefines them.",
    "Findspot":
        "A named context within a discovery site, such as a pit, a ditch "
        "or a destruction layer. It falls within its site via "
        "crm:P89_falls_within. A site may carry several findspots — "
        "Bregenz has six — which is why the dating hangs on the findspot "
        "and not on the site.",
    "DatedTimeSpan":
        "A time-span inferred from dated material rather than recorded "
        "directly. Sits beneath both crm:E52_Time-Span and "
        "time:ProperInterval so that CIDOC-based and OWL-Time-based "
        "queries each find it by their own route.",
    "FindspotDating":
        "The dating of one findspot derived from samian potters' stamps. "
        "The interval is a 'virtual fuzzy year' of the form m ± k·σ and is "
        "explicitly NOT a confidence interval: it carries no probabilistic "
        "claim about where the true date lies.",
    "DatingInstant":
        "One boundary of a dated interval. A local class rather than a "
        "bare time:Instant so that it can be anchored in CIDOC CRM "
        "without making any claim about time:Instant in general: "
        "crm:E52_Time-Span is the CRM notion of a temporal extent, and "
        "this one has zero duration. Every instance of an application "
        "class in this export reaches CIDOC CRM, and the boundaries are "
        "no exception — without the anchor a CRM-only consumer would see "
        "a time-span whose ends did not exist.",
    "DatingTimePosition":
        "The numeric value of a boundary together with the scale it is "
        "read on. Structurally a crm:E54_Dimension: time:numericPosition "
        "corresponds to P90 has value and time:hasTRS to P91 has unit. "
        "Kept as a local subclass so the alignment is stated here rather "
        "than asserted about OWL-Time itself.",
    "YearScale":
        "The temporal reference system the numeric positions are read "
        "on. A documented convention, and therefore a "
        "crm:E73_Information_Object. Its definition matters because the "
        "positions are signed years on a continuous line, not calendar "
        "labels — see eraConvention.",
    "DatingModel":
        "The parameterisation from which the intervals were computed. "
        "Holds k_min, k_max, τ, w and the fuzziness divisor, so a reader "
        "can recompute any interval from the exported figures alone. It "
        "sits beneath prov:Plan and beneath crm:E29_Design_or_Procedure, "
        "the CIDOC CRM class for a documented procedure; without the "
        "second parent this would be the one local class that never "
        "reaches CIDOC CRM, and a CRM-only consumer could see the "
        "datings but not the method behind them.",
    "DatingActivity":
        "The computation that produced one dating. It sits beneath "
        "crmdig:D10_Software_Execution, whose scope note describes "
        "precisely this: a run completely determined by its digital "
        "input, the software and the generic properties of the device. "
        "Using CRMdig rather than reaching for crm:E7_Activity directly "
        "means the alignment has been done by the extension's authors — "
        "D10 leads through D7 and E11/E65 to E7_Activity — instead of "
        "this vocabulary deciding on its own whether a script run counts "
        "as an action intentionally carried out by an actor.",
    "Figure":
        "A published figure. Carries the constants that belong to the "
        "drawing rather than to the archaeology — padding, row height, "
        "colour ramp, sort order — so that they are stated once instead of "
        "being repeated on every row.",
    "PlotRow":
        "The presentation layer of a single dating. It deliberately "
        "carries the uncertainty whiskers, which the method documentation "
        "describes as visual only, keeping them off the time-span where "
        "they would read as an archaeological claim.",

    # ---- object properties ----
    "renders":
        "Links a plot row to the dating it depicts. Following this "
        "property in reverse tells you whether a given dating appears in "
        "any published figure.",
    "hasRow":
        "Links a figure to the plot rows it contains.",
    "undefinedMeasure":
        "Names a measure that could not be computed for this subject. "
        "Under the open-world assumption a missing triple is merely "
        "unknown; this property distinguishes 'we computed it and it does "
        "not exist' from 'nobody has looked yet'.",

    # ---- measures on the dating ----
    "nStamps":
        "The number of stamps recorded at the findspot. Note that this is "
        "not the n used by the k formula — see nStampsWithDie.",
    "nStampsWithDie":
        "The number of stamps that carry a die attribution. This is the n "
        "in the k formula. It is smaller than nStamps because the "
        "underlying query counts only rows where a die is recorded. "
        "Substituting nStamps here yields a different k from the one "
        "actually used, which is why both are exported.",
    "nDies":
        "The number of distinct dies attested at the findspot, counted "
        "over the pair (potter, die).",
    "dieRepetition":
        "nStampsWithDie divided by nDies. High values indicate that the "
        "same dies recur, which is characteristic of a hoard or a closed "
        "deposit rather than of accumulated site refuse.",
    "qRepetition":
        "1 − 1/repetition, the second quality axis. Deliberately not "
        "combined with qInterval: a findspot that is not a deposit is not "
        "thereby badly dated, and averaging the two would assert exactly "
        "that.",
    "qInterval":
        "The first quality axis, describing how tightly the contributing "
        "potter datings agree. Unlike qStart and qEnd it divides by the "
        "interval width rather than by a calendar value, so it is not "
        "distorted near the era boundary.",
    "qStart":
        "Sharpness of the start date. Use with care: the denominator is "
        "the mean calendar value, so material dated close to the era "
        "boundary is penalised for its position in the calendar rather "
        "than for any property of the evidence.",
    "qEnd":
        "Sharpness of the end date. Subject to the same era-boundary "
        "distortion as qStart.",
    "sigmaYears":
        "The dispersion entering the interval width, obtained by variance "
        "decomposition: the internal fuzziness of each potter's range plus "
        "the scatter of the range midpoints. Together with kFactor it "
        "determines the width of the box, which is 2·k·σ.",
    "kFactor":
        "The volume-based multiplier applied to sigmaYears. It falls from "
        "k_max towards k_min as evidence accumulates, so a findspot with "
        "many stamps receives a narrower interval than one with few.",
    "kIsFallback":
        "True where no die attribution exists at all and k was therefore "
        "set to k_max. This is model behaviour rather than a measurement, "
        "and it widens the interval for a reason unconnected with the "
        "material.",
    "midpointYear":
        "The centre of the averaged interval, the m in m ± k·σ.",
    "avgDatemin": "Mean of the contributing potters' start dates.",
    "avgDatemax": "Mean of the contributing potters' end dates.",
    "minDatemin":
        "Earliest start date among the contributing potters. Drawn as the "
        "left extreme stub in both figures.",
    "maxDatemin": "Latest start date among the contributing potters.",
    "minDatemax": "Earliest end date among the contributing potters.",
    "maxDatemax":
        "Latest end date among the contributing potters. Drawn as the "
        "right extreme stub in both figures.",
    "intervalLabel":
        "The interval rendered as text by the source query, retained for "
        "display and for comparison against the published web output.",

    # ---- presentation layer ----
    "uncStartYears":
        "Sample standard deviation of the contributing start dates. "
        "Presentation only: it measures the scatter of the interval edges, "
        "whereas the box is built from the scatter of the midpoints, so "
        "the whisker does not continue the box in any statistical sense.",
    "uncEndYears":
        "Sample standard deviation of the contributing end dates. "
        "Presentation only, as for uncStartYears.",
    "uncIntervalYears":
        "Combined edge dispersion, sqrt(var(datemin) + var(datemax)). "
        "Presentation only.",

    # ---- model parameters ----
    "kMin":
        "Lower bound of the k factor, approached as evidence accumulates.",
    "kMax":
        "Upper bound of the k factor, applied when evidence is thin or "
        "absent.",
    "tau":
        "The saturation constant of the k curve. At n = τ roughly 63 per "
        "cent of the available narrowing has been achieved.",
    "volumeWeight":
        "Set to 1.0, recording that k depends on volume of evidence alone "
        "and on no other weighting.",
    "fuzzinessDivisor":
        "The value 12, being the variance of a uniform distribution over a "
        "unit range. This is where the per-stamp distributional assumption "
        "enters the model, and stating it makes that assumption "
        "inspectable rather than implicit.",
    "excludedDatemax":
        "A datemax value removed by the source query's filter. The reason "
        "for the exclusion is not currently documented. The filter is not "
        "neutral: it removes the affected potters at every findspot, so it "
        "is recorded here rather than left silent.",
    "identifierScheme":
        "The recipe by which findspot URI fragments are built. Any further "
        "implementation must reproduce it character for character, "
        "including the Unicode normalisation step, or it will mint "
        "different URIs for the same findspot.",
    "eraConvention":
        "How negative years in the source are to be read. Under "
        "'historical', −40 means 40 BC, and the derived xsd:gYear label is "
        "shifted by one because XSD counts astronomically. Only the "
        "calendar label is shifted; the numeric position is left "
        "untouched.",

    # ---- figure constants ----
    "padYears":
        "Years of empty space added at each end of the time axis.",
    "extremeStubYears":
        "Length of the stub drawn at each extreme value. The full range "
        "line was replaced by these stubs in the web application, and both "
        "figures follow that decision.",
    "rowHeight": "Height of one row, in pixels.",
    "svgWidth": "Width of the figure canvas, in pixels.",
    "marginLeft":
        "Left margin, in pixels; it accommodates the site and findspot "
        "labels.",
    "marginRight": "Right margin, in pixels.",
    "marginTop": "Top margin, in pixels.",
    "marginBottom": "Bottom margin, in pixels.",
    "bandPadding":
        "Fraction of each row left empty between bars, following the "
        "d3.scaleBand convention.",
    "colourRamp":
        "Name of the colour ramp mapping quality to colour, recorded so "
        "that a reader can reproduce the fill colours rather than "
        "eyeballing them.",
    "rowOrder":
        "The rule by which rows are sorted, allowing the order of the "
        "published figure to be reproduced from the graph alone.",
}


# --------------------------------------------------------------------------
# The statistical model, as implemented in the source SQL
# --------------------------------------------------------------------------
# (heading, formula, SQL expression, commentary)
FORMULAS: list[tuple[str, str, str, str]] = [
    ("Interval midpoint",
     "m = (mean(datemin) + mean(datemax)) / 2",
     "((AVG(p.datemin) + AVG(p.datemax)) / 2.0)::numeric(10,1)",
     "The centre about which the effective interval is built. Averaged "
     "over every potter attested at the findspot."),

    ("Dispersion by variance decomposition",
     "σ = sqrt( mean(width² / 12) + var(midpoints) )",
     "SQRT( AVG(POWER(p.datemax - p.datemin, 2) / 12.0)\n"
     "      + COALESCE(VAR_SAMP((p.datemin + p.datemax) / 2.0), 0) )",
     "Two sources of spread are added. The first term is the internal "
     "fuzziness of each potter's own range, treated as uniform, whose "
     "variance is width²/12. The second is the disagreement between "
     "potters about where the centre lies. Where only one potter "
     "contributes, the second term is zero and the first survives — a "
     "single potter still does not date a findspot to a point."),

    ("Volume-based k factor",
     "k = k_max − (k_max − k_min) · (1 − exp(−n / τ))",
     "( (SELECT k_max FROM params)\n"
     "  - ((SELECT k_max FROM params) - (SELECT k_min FROM params))\n"
     "    * (1 - EXP(-SUM(stamps_pp)::numeric / (SELECT tau FROM params))) )",
     "The multiplier falls from k_max towards k_min as evidence "
     "accumulates, so that a well-attested findspot receives a narrower "
     "interval. Note that n here is nStampsWithDie, counting only stamps "
     "with a die attribution, and not the total stamp count."),

    ("Effective interval",
     "eff_start = m − k·σ    eff_end = m + k·σ",
     "( (AVG(p.datemin)+AVG(p.datemax))/2.0\n"
     "  ± COALESCE(MIN(k.k_eff), (SELECT k_max FROM params))\n"
     "    * SQRT( AVG(POWER(p.datemax - p.datemin, 2)/12.0)\n"
     "            + COALESCE(VAR_SAMP((p.datemin+p.datemax)/2.0), 0) ) )",
     "The interval drawn as the box. It is an archaeologically motivated "
     "'virtual fuzzy year', not a confidence interval; no probability "
     "statement attaches to it. Its width is exactly 2·k·σ, which is the "
     "identity used to verify that the exported figures are sufficient to "
     "reconstruct the interval."),

    ("Dating sharpness — first quality axis",
     "q_interval = exp( − sqrt(var(datemin) + var(datemax))\n"
     "                  / |mean(datemax) − mean(datemin)| )",
     "EXP(-(SQRT(VAR_SAMP(p.datemin) + VAR_SAMP(p.datemax)) /\n"
     "     ABS(AVG(p.datemax) - AVG(p.datemin))))",
     "Dispersion relative to interval width, mapped onto (0, 1]. Because "
     "the denominator is a width rather than a calendar value, this axis "
     "is unaffected by proximity to the era boundary."),

    ("Edge sharpness — presentation only",
     "q_start = exp( − sd(datemin) / |mean(datemin)| )\n"
     "q_end   = exp( − sd(datemax) / |mean(datemax)| )",
     "EXP(-(STDDEV_SAMP(p.datemin) / ABS(AVG(p.datemin))))\n"
     "EXP(-(STDDEV_SAMP(p.datemax) / ABS(AVG(p.datemax))))",
     "These divide by a calendar value, so material dated near the era "
     "boundary is penalised for its position in the calendar rather than "
     "for any weakness in the evidence. At Amiens the mean end date is "
     "AD 3, and a scatter of 15 years therefore yields q_end ≈ 0.004 — a "
     "red whisker that says 'close to the era boundary', not 'poorly "
     "dated'. Exported for completeness and used for whisker colour, but "
     "not suitable as a quality measure on its own."),

    ("Die repetition — second quality axis",
     "r = n_stamps_die / n_dies\n"
     "q_repetition = 1 − 1 / max(r, 1)",
     "ROUND(SUM(stamps_pp)::numeric / NULLIF(SUM(dies_pp),0), 3)\n"
     "CASE WHEN MIN(k.rep) IS NULL THEN NULL\n"
     "     ELSE ROUND(1 - 1.0/GREATEST(MIN(k.rep),1), 3) END",
     "Describes deposit character rather than dating quality. The two "
     "axes are deliberately kept apart: combining them would let a "
     "findspot that is simply not a hoard appear badly dated. Findspots "
     "without die attribution yield NULL, not zero, because absence of "
     "die information is not evidence of absent repetition."),
]


# --------------------------------------------------------------------------
# Crosswalk commentary — why each external vocabulary is used as it is
# --------------------------------------------------------------------------
CROSSWALK_NOTES: dict[str, str] = {
    "crm":
        "CIDOC CRM is the integration layer. Every class minted here "
        "reaches a CRM class through rdfs:subClassOf, so a consumer that "
        "understands only CRM still sees places, time-spans and visual "
        "items without needing to load the LADO vocabulary. Findspots "
        "attach to their sites with crm:P89_falls_within and to their "
        "datings with crm:P4_has_time-span, both of which are standard "
        "CRM properties used in their intended sense.",
    "time":
        "OWL-Time carries the temporal semantics. Interval boundaries are "
        "time:Instant nodes reached through time:hasBeginning and "
        "time:hasEnd. Each instant carries a time:TimePosition with a "
        "decimal time:numericPosition, because the computed boundaries are "
        "not whole years — forty of forty-one rows have a fractional part, "
        "and rounding them away would discard exactly the precision the "
        "model produces. A rounded time:inXSDgYear is supplied alongside "
        "for consumers that read calendar years only. Note that "
        "time:intervalStarts and time:intervalFinishes are NOT used: they "
        "relate an interval to another interval, not to an instant, and an "
        "earlier version of this export misused them in that way.",
    "geo":
        "GeoSPARQL is referenced rather than asserted. The published "
        "discovery-site dataset already carries geo:hasGeometry with a "
        "geo:wktLiteral for these places, so this export emits no geometry "
        "by default. The --emit-geometry switch adds the IPS coordinates "
        "under a separate geometry node for anyone who wants to compare "
        "the two, but the default is silence rather than a second, "
        "competing position for the same place.",
    "prov":
        "PROV-O records how the intervals came to exist. Each dating is "
        "generated by a prov:Activity whose qualified association names a "
        "prov:Plan holding the model parameters, so the parameters are "
        "stated once rather than repeated on every row. Note the "
        "namespace: the published discovery-site file (2019 release) binds prov: to "
        "http://www.w3.org/ns/prov-o/, which is not the PROV-O namespace "
        "and leaves its six provenance predicates pointing at terms that "
        "do not exist. This export uses http://www.w3.org/ns/prov# and "
        "does not reproduce that error.",
    "crmdig":
        "CRMdig is the CIDOC CRM extension for digital provenance, and it "
        "supplies the class this export needed for the computation behind "
        "each dating: D10 Software Execution. Its own chain into CIDOC "
        "CRM — D10 to D7 Digital Machine Event, then to E11 Modification "
        "and E65 Creation, both subclasses of E7 Activity — is restated "
        "in the vocabulary file so that the standalone bundle resolves "
        "CIDOC CRM queries without CRMdig being loaded alongside. Those "
        "restated axioms belong to CRMdig; they are repeated, not "
        "invented. D3 Formal Derivation was considered and rejected as "
        "too narrow: its scope note describes representation-preserving "
        "derivations such as resizing an image, whereas this computation "
        "produces new values.",
    "dcat":
        "DCAT describes the export as a dataset. Because the time-span "
        "URIs are deliberately not versioned, their values change when the "
        "source data change; the dated dataset node is therefore what a "
        "reader cites when they need a fixed state.",
    "dcterms":
        "Dublin Core Terms supplies title, source, creation and issue "
        "dates on the dataset node.",
    "skos":
        "SKOS is used narrowly: skos:notation retains the readable slug of "
        "each findspot alongside its hashed URI, so that a broken link can "
        "still be diagnosed, and skos:closeMatch relates the local year "
        "scale to the Gregorian reference system.",
    "samian":
        "The namespace for resources under our own control, at "
        "data.archaeology.link. Discovery-site nodes in this namespace are "
        "already published and are only referenced here; findspots, "
        "datings, plot rows, figures and the model are new.",
    "lado":
        "The local ontology, extended here with the classes and properties "
        "that CIDOC CRM and OWL-Time do not supply — chiefly the "
        "separation between an archaeological dating and its presentation, "
        "and the quantities specific to this statistical model.",
    "pleiades":
        "Pleiades identifiers are carried as an add-on where they exist, "
        "which is for 14 of 41 rows. A caveat: the source database stores "
        "them as floating-point values, so the identifiers arrive with a "
        "trailing '.0'. This export casts them to integers. The published "
        "discovery-site file does not, which is why all 280 of its "
        "Pleiades links are unreachable.",
    "owl": "Used for the ontology declaration and for version information.",
    "xsd": "Supplies the literal datatypes.",
}


# --------------------------------------------------------------------------
# Where each SQL output column ends up in the graph
# --------------------------------------------------------------------------
# (SQL column, RDF subject, RDF predicate)
COLUMN_MAP: list[tuple[str, str, str]] = [
    ("the_id",             "samian:loc_ds_<id>",   "(forms the URI)"),
    ("the_site",           "samian:loc_ds_<id>",   "rdfs:label"),
    ("the_findspot",       "samian:fs_<id>_<hash>", "rdfs:label, skos:notation"),
    ("latinsitename",      "samian:loc_ds_<id>",   "lado:ancientName"),
    ("pleiades",           "samian:loc_ds_<id>",   "lado:pleiadesID"),
    ("long, lat",          "samian:loc_ds_<id>",   "geo:hasGeometry (optional)"),
    ("eff_start, eff_end", "samian:ts_<id>_<hash>",
     "time:hasBeginning / time:hasEnd"),
    ("count_stamps",       "samian:ts_<id>_<hash>", "lado:nStamps"),
    ("n_stamps_die",       "samian:ts_<id>_<hash>", "lado:nStampsWithDie"),
    ("n_dies",             "samian:ts_<id>_<hash>", "lado:nDies"),
    ("die_repetition",     "samian:ts_<id>_<hash>", "lado:dieRepetition"),
    ("q_repetition",       "samian:ts_<id>_<hash>", "lado:qRepetition"),
    ("q_interval",         "samian:ts_<id>_<hash>", "lado:qInterval"),
    ("q_start, q_end",     "samian:ts_<id>_<hash>", "lado:qStart / lado:qEnd"),
    ("sigma_eff",          "samian:ts_<id>_<hash>", "lado:sigmaYears"),
    ("k_eff",              "samian:ts_<id>_<hash>", "lado:kFactor"),
    ("k_is_fallback",      "samian:ts_<id>_<hash>", "lado:kIsFallback"),
    ("midpoint_year",      "samian:ts_<id>_<hash>", "lado:midpointYear"),
    ("avg_datemin, avg_datemax", "samian:ts_<id>_<hash>",
     "lado:avgDatemin / lado:avgDatemax"),
    ("min_datemin, max_datemin", "samian:ts_<id>_<hash>",
     "lado:minDatemin / lado:maxDatemin"),
    ("min_datemax, max_datemax", "samian:ts_<id>_<hash>",
     "lado:minDatemax / lado:maxDatemax"),
    ("avg_interval",       "samian:ts_<id>_<hash>", "lado:intervalLabel"),
    ("unc_start_years",    "samian:plotrow_<id>_<hash>", "lado:uncStartYears"),
    ("unc_end_years",      "samian:plotrow_<id>_<hash>", "lado:uncEndYears"),
    ("unc_interval_years", "samian:plotrow_<id>_<hash>",
     "lado:uncIntervalYears"),
    ("p_k_min, p_k_max, p_tau, p_w", "samian:DatingModel_v1",
     "lado:kMin / kMax / tau / volumeWeight"),
]
