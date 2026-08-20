/* =====================================================================
   Emitter body. Everything above this line is generated; everything
   below is the structural counterpart to build_graph() in
   py/ips_rdf_export.py and is hand-written.

   The two implementations are NOT kept in step by generation — a graph
   shape is not a table and a generator for it would be a small language
   with its own bugs. They are kept in step by the parity gate in
   py/make_webjs.py --verify, which builds both graphs from the same CSV,
   sorts the N-Triples and compares SHA-256. A structural change on one
   side that is not made on the other fails the build.
   ===================================================================== */

/* ---- SHA-256, synchronous ------------------------------------------
   Not crypto.subtle: that is undefined outside a secure context, and the
   ColdFusion server is not guaranteed to be on HTTPS. The findspot URIs
   depend on this hash, so an emitter that cannot hash cannot run at all.
   Public-domain style implementation, FIPS 180-4. */
function sha256hex(str) {
  const K = GEN.SHA_K;
  const bytes = new TextEncoder().encode(str);
  const bitLen = bytes.length * 8;
  const withPad = new Uint8Array((((bytes.length + 8) >> 6) + 1) << 6);
  withPad.set(bytes);
  withPad[bytes.length] = 0x80;
  const dv = new DataView(withPad.buffer);
  dv.setUint32(withPad.length - 4, bitLen >>> 0, false);
  dv.setUint32(withPad.length - 8, Math.floor(bitLen / 4294967296), false);

  let h = GEN.SHA_H.slice();
  const w = new Uint32Array(64);
  const rr = (x, n) => (x >>> n) | (x << (32 - n));

  for (let off = 0; off < withPad.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4, false);
    for (let i = 16; i < 64; i++) {
      const s0 = rr(w[i - 15], 7) ^ rr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rr(w[i - 2], 17) ^ rr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 64; i++) {
      const S1 = rr(e, 6) ^ rr(e, 11) ^ rr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
      const S0 = rr(a, 2) ^ rr(a, 13) ^ rr(a, 22);
      const mj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + mj) >>> 0;
      hh = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    h = [h[0] + a, h[1] + b, h[2] + c, h[3] + d,
         h[4] + e, h[5] + f, h[6] + g, h[7] + hh].map(x => x >>> 0);
  }
  return h.map(x => x.toString(16).padStart(8, '0')).join('');
}

/* ---- value helpers -------------------------------------------------- */

function isNA(v) {
  if (v === null || v === undefined) return true;
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    return s === '' || s === 'null' || s === 'nan';
  }
  return typeof v === 'number' && !Number.isFinite(v);
}

function num(v) {
  const n = typeof v === 'number' ? v : Number(String(v).trim());
  return Number.isFinite(n) ? n : null;
}

/* Python's round(): half to even. Math.round(-16.5) and round(-16.5)
   agree by luck, Math.round(2.5)=3 and round(2.5)=2 do not. eff_start
   and eff_end are numeric(10,1), so halves really occur. */
function pyRound(x) {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

/* Lexical form of a decimal, matching Python str(float). */
function decStr(v) {
  const n = num(v);
  if (n === null) return null;
  if (Number.isInteger(n) && Math.abs(n) < 1e16) return String(n) + '.0';
  return String(n);
}

/* xsd:gYear, four digits, era shift on the calendar label only. */
function gyear(value, era) {
  let y = pyRound(num(value));
  if (era === 'historical' && y < 0) y += 1;
  const sign = y < 0 ? '-' : '';
  return sign + String(Math.abs(y)).padStart(4, '0');
}

function slug(text) {
  let s = String(text).trim();
  s = Array.from(s).map(c => (GEN.TRANSLIT[c] !== undefined ? GEN.TRANSLIT[c] : c)).join('');
  s = s.normalize('NFKD').replace(/[^\x00-\x7F]/g, '');
  s = s.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase();
  return s || 'unknown';
}

/* sha256(NFC(trim(findspot)))[0:6] — see KEY_ALGORITHM on the Python side. */
function findspotHash(findspot) {
  return sha256hex(String(findspot).trim().normalize('NFC')).slice(0, 6);
}

/* ---- term constructors ---------------------------------------------- */
const U = v => ({ t: 'u', v });
const S = (pfx, local) => U(GEN.PREFIXES[pfx] + local);
const Lit = (v, dt, lang) => ({ t: 'l', v: String(v), dt: dt || null, lang: lang || null });
const Dec = v => Lit(decStr(v), GEN.PREFIXES.xsd + 'decimal');
const Int = v => Lit(String(Math.trunc(num(v))), GEN.PREFIXES.xsd + 'integer');
const GYear = (v, era) => Lit(gyear(v, era), GEN.PREFIXES.xsd + 'gYear');

/* ---- graph accumulator ----------------------------------------------
   Types are materialised on the way in: the bundle carries the inferred
   rdf:type triples explicitly, because most stores do no RDFS entailment
   and a CIDOC-CRM query would otherwise come back empty. GEN.CLOSURE is
   the transitive closure over rdfs:subClassOf, computed from the
   ontology at build time — no reasoning happens here. */
function Graph() {
  const seen = new Set();
  const out = [];
  const add = (s, p, o) => {
    const k = s.v + ' ' + p.v + ' ' + (o.t === 'u' ? o.v : o.v + '|' + o.dt + '|' + o.lang);
    if (seen.has(k)) return;
    seen.add(k);
    out.push([s, p, o]);
  };
  const type = (s, cls) => {
    add(s, RDF_TYPE, cls);
    (GEN.CLOSURE[cls.v] || []).forEach(sup => add(s, RDF_TYPE, U(sup)));
  };
  return { add, type, triples: out };
}

const RDF_TYPE = U(GEN.PREFIXES.rdf + 'type');
const RDFS_LABEL = U(GEN.PREFIXES.rdfs + 'label');
const RDFS_COMMENT = U(GEN.PREFIXES.rdfs + 'comment');

/* ---- row field access ------------------------------------------------
   ColdFusion's serializeJSON upper-cases struct keys, the CSV export does
   not. Read case-insensitively so the same emitter serves both, and so
   the parity gate really compares the same code path the browser runs. */
function field(row, name) {
  if (name in row) return row[name];
  const up = name.toUpperCase();
  if (up in row) return row[up];
  const lo = name.toLowerCase();
  if (lo in row) return row[lo];
  return undefined;
}

/* ---- timestamps ------------------------------------------------------ */
function isoSeconds(d) {
  const p = n => String(n).padStart(2, '0');
  return d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate())
       + 'T' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':'
       + p(d.getUTCSeconds()) + '+00:00';
}
function snapshotOf(d) {
  const p = n => String(n).padStart(2, '0');
  return d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate());
}

/* ===================================================================== */
function buildTriples(rows, opts) {
  opts = opts || {};
  const era = opts.era || 'historical';
  const figureName = opts.figureName || GEN.FIGURE_NAME;
  const when = opts.generatedAt ? new Date(opts.generatedAt) : new Date();
  const nowLit = Lit(isoSeconds(when), GEN.PREFIXES.xsd + 'dateTime');
  const snapshot = snapshotOf(when);

  const g = Graph();
  const xsd = GEN.PREFIXES.xsd;

  /* ---- agent, TRS, model, dataset, figure ---------------------------- */
  const agent = S('samian', 'IPSDatedSitesExporter');
  g.type(agent, S('prov', 'SoftwareAgent'));
  g.type(agent, S('crmdig', 'D14_Software'));
  g.add(agent, RDFS_LABEL, Lit(GEN.AGENT_LABEL, null, 'en'));

  const trs = S('samian', 'trs_ips_year');
  g.type(trs, S('time', 'TRS'));
  g.type(trs, S('lado', 'YearScale'));
  g.add(trs, RDFS_LABEL, Lit(GEN.TRS_LABEL, null, 'en'));
  g.add(trs, RDFS_COMMENT, Lit(GEN.TRS_COMMENT, null, 'de'));
  g.add(trs, S('skos', 'closeMatch'), U(GEN.TRS_GREGORIAN));

  const model = S('samian', 'DatingModel_v1');
  g.type(model, S('lado', 'DatingModel'));
  g.add(model, RDFS_LABEL, Lit(GEN.MODEL_LABEL, null, 'en'));
  g.add(model, RDFS_COMMENT, Lit(GEN.MODEL_COMMENT, null, 'de'));
  const r0 = rows[0] || {};
  GEN.MODEL_PARAMS.forEach(([prop, col]) => {
    const v = field(r0, col);
    if (!isNA(v)) g.add(model, S('lado', prop), Dec(v));
  });
  g.add(model, S('lado', 'fuzzinessDivisor'), Int(GEN.FUZZINESS_DIVISOR));
  g.add(model, S('lado', 'eraConvention'), Lit(era));
  GEN.EXCLUDED_DATEMAX.forEach(v => g.add(model, S('lado', 'excludedDatemax'), Int(v)));

  const dataset = S('samian', 'dataset_' + figureName + '_' + snapshot);
  g.type(dataset, S('dcat', 'Dataset'));
  g.type(dataset, S('prov', 'Entity'));
  g.type(dataset, S('crmdig', 'D1_Digital_Object'));
  g.add(dataset, S('dcterms', 'title'), Lit(GEN.DATASET_TITLE, null, 'en'));
  g.add(dataset, S('dcterms', 'created'), nowLit);
  g.add(dataset, S('prov', 'wasAttributedTo'), agent);
  g.add(dataset, S('dcterms', 'source'), Lit(GEN.DATASET_SOURCE));
  g.add(dataset, S('dcterms', 'issued'), Lit(snapshot, xsd + 'date'));
  g.add(dataset, S('owl', 'versionInfo'), Lit(snapshot));
  g.add(dataset, S('lado', 'identifierScheme'), Lit(GEN.KEY_ALGORITHM));
  g.add(dataset, RDFS_COMMENT, Lit(GEN.DATASET_COMMENT, null, 'de'));

  const figure = S('samian', 'fig_' + figureName);
  g.type(figure, S('lado', 'Figure'));
  g.add(figure, RDFS_LABEL, Lit(GEN.FIGURE_LABEL, null, 'en'));
  g.add(figure, S('dcterms', 'isPartOf'), dataset);
  GEN.FIGURE_CONSTANTS.forEach(([name, value, kind]) => {
    g.add(figure, S('lado', name),
          kind === 'decimal' ? Dec(value)
        : kind === 'integer' ? Int(value)
        : Lit(value, xsd + 'string'));
  });

  /* ---- rows ---------------------------------------------------------- */
  const collide = {};
  rows.forEach(r => {
    const sid = Math.trunc(num(field(r, 'the_id')));
    const fsName = String(field(r, 'the_findspot'));
    const frag = GEN.KEY_MODE === 'hash' ? findspotHash(fsName) : slug(fsName);
    const ck = sid + '/' + frag;
    if (collide[ck] !== undefined && collide[ck] !== fsName) {
      throw new Error('URI collision at site ' + sid + ": '" + collide[ck]
                      + "' and '" + fsName + "' both give '" + frag + "'.");
    }
    collide[ck] = fsName;
    const key = sid + '_' + frag;

    const place    = S('samian', 'loc_ds_' + sid);
    const findspot = S('samian', 'fs_' + key);
    const ts       = S('samian', 'ts_' + key);
    const row      = S('samian', 'plotrow_' + key);
    const act      = S('samian', 'act_dating_' + key);

    /* place — referenced, not re-typed (see the export docstring) */
    g.add(place, RDFS_LABEL, Lit(String(field(r, 'the_site')), null, 'en'));
    const latin = field(r, 'latinsitename');
    if (!isNA(latin)) g.add(place, S('lado', 'ancientName'), Lit(String(latin)));
    const pl = field(r, 'pleiades');
    if (!isNA(pl)) g.add(place, S('lado', 'pleiadesID'),
                         S('pleiades', String(Math.trunc(num(pl)))));

    /* findspot */
    g.type(findspot, S('lado', 'Findspot'));
    g.add(findspot, RDFS_LABEL, Lit(fsName));
    g.add(findspot, S('skos', 'notation'), Lit(slug(fsName)));
    g.add(findspot, S('crm', 'P89_falls_within'), place);
    g.add(findspot, S('crm', 'P4_has_time-span'), ts);

    /* time-span */
    const effStart = field(r, 'eff_start');
    const effEnd   = field(r, 'eff_end');
    g.type(ts, S('lado', 'FindspotDating'));
    g.add(ts, RDFS_LABEL, Lit(
      field(r, 'the_site') + ' \u2014 ' + fsName + ': '
      + pyRound(num(effStart)) + ' to ' + pyRound(num(effEnd)), null, 'en'));
    g.add(ts, S('prov', 'wasGeneratedBy'), act);

    [['begin', effStart, 'hasBeginning'],
     ['end', effEnd, 'hasEnd']].forEach(([which, value, edge]) => {
      const inst = S('samian', 'ts_' + key + '_' + which);
      const pos  = U(inst.v + '_pos');
      g.add(ts, S('time', edge), inst);
      g.type(inst, S('time', 'Instant'));
      g.type(inst, S('lado', 'DatingInstant'));
      g.add(inst, S('time', 'inTimePosition'), pos);
      g.type(pos, S('time', 'TimePosition'));
      g.type(pos, S('lado', 'DatingTimePosition'));
      g.add(pos, S('time', 'hasTRS'), trs);
      /* numericPosition is deliberately NOT era-shifted: shifting only the
         negative values would tear the scale apart at zero. */
      g.add(pos, S('time', 'numericPosition'), Dec(value));
      g.add(inst, S('time', 'inXSDgYear'), GYear(value, era));
    });

    g.add(ts, S('crm', 'P82a_begin_of_the_begin'), GYear(effStart, era));
    g.add(ts, S('crm', 'P82b_end_of_the_end'), GYear(effEnd, era));

    /* measures — NULL contract: no triple, but an explicit marker */
    GEN.MEASURES.forEach(([prop, col, kind]) => {
      const v = field(r, col);
      if (isNA(v)) g.add(ts, S('lado', 'undefinedMeasure'), S('lado', prop));
      else g.add(ts, S('lado', prop), kind === 'integer' ? Int(v) : Dec(v));
    });

    const ivl = field(r, 'avg_interval');
    if (!isNA(ivl)) g.add(ts, S('lado', 'intervalLabel'), Lit(String(ivl)));
    const kfb = field(r, 'k_is_fallback');
    g.add(ts, S('lado', 'kIsFallback'),
          Lit(/^(true|1|yes)$/i.test(String(kfb)) ? 'true' : 'false',
              xsd + 'boolean'));

    /* presentation layer */
    g.type(row, S('lado', 'PlotRow'));
    g.add(row, S('lado', 'renders'), ts);
    g.add(figure, S('lado', 'hasRow'), row);
    GEN.PLOTROW_MEASURES.forEach(([prop, col]) => {
      const v = field(r, col);
      if (isNA(v)) g.add(row, S('lado', 'undefinedMeasure'), S('lado', prop));
      else g.add(row, S('lado', prop), Int(v));
    });

    /* provenance */
    g.type(act, S('prov', 'Activity'));
    g.type(act, S('lado', 'DatingActivity'));
    g.add(act, RDFS_LABEL, Lit('Dating of ' + field(r, 'the_site')
                               + ' \u2014 ' + fsName, null, 'en'));
    g.add(act, S('prov', 'wasAssociatedWith'), agent);
    g.add(act, S('prov', 'endedAtTime'), nowLit);
    g.add(act, S('prov', 'used'), dataset);
    g.add(act, S('prov', 'used'), model);
    g.add(act, S('crm', 'P33_used_specific_technique'), model);
    g.add(act, S('crm', 'P14_carried_out_by'), agent);
    g.add(ts, S('prov', 'wasDerivedFrom'), dataset);
  });

  /* discovery sites are typed here, as in make_bundle.py: standalone, an
     untyped P89 target would hide every place from a CRM query. */
  const sites = new Set(rows.map(r => 'loc_ds_' + Math.trunc(num(field(r, 'the_id')))));
  sites.forEach(local => g.type(S('samian', local), S('lado', 'DiscoverySite')));

  return g.triples;
}

/* ---- serialisation --------------------------------------------------- */
function escLiteral(s) {
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
          .replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
}

function ntTerm(t) {
  if (t.t === 'u') return '<' + t.v + '>';
  let s = '"' + escLiteral(t.v) + '"';
  if (t.lang) return s + '@' + t.lang;
  if (t.dt) return s + '^^<' + t.dt + '>';
  return s;
}

/* N-Triples, sorted. This is the canonical form the parity gate hashes:
   Turtle pretty-printing differs harmlessly between rdflib and this file,
   N-Triples does not. */
function toNTriples(triples) {
  return triples
    .map(([s, p, o]) => ntTerm(s) + ' ' + ntTerm(p) + ' ' + ntTerm(o) + ' .')
    .sort()
    .join('\n') + '\n';
}

function toTurtle(triples) {
  const inv = Object.entries(GEN.PREFIXES).sort((a, b) => b[1].length - a[1].length);
  const shorten = uri => {
    for (const [pfx, ns] of inv) {
      if (uri.startsWith(ns)) {
        const local = uri.slice(ns.length);
        if (/^[A-Za-z_][A-Za-z0-9_.\-]*$/.test(local)) return pfx + ':' + local;
      }
    }
    return '<' + uri + '>';
  };
  const term = t => {
    if (t.t === 'u') return shorten(t.v);
    let s = '"' + escLiteral(t.v) + '"';
    if (t.lang) return s + '@' + t.lang;
    if (t.dt) return s + '^^' + shorten(t.dt);
    return s;
  };
  const head = Object.entries(GEN.PREFIXES).sort()
    .map(([p, ns]) => '@prefix ' + p + ': <' + ns + '> .').join('\n');
  const body = triples
    .map(([s, p, o]) => term(s) + ' ' + term(p) + ' ' + term(o) + ' .')
    .sort().join('\n');
  return head + '\n\n' + GEN.PRELUDE + '\n' + body + '\n';
}

const IPSRDF = {
  buildTriples, toTurtle, toNTriples,
  sha256hex, findspotHash, slug, pyRound, gyear,
  SPEC_VERSION: GEN.SPEC_VERSION,
  PRELUDE_TRIPLES: GEN.PRELUDE_TRIPLES
};

if (typeof module !== 'undefined' && module.exports) module.exports = IPSRDF;
if (typeof window !== 'undefined') window.IPSRDF = IPSRDF;
