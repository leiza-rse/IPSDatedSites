/* ---------------------------------------------------------------
   IPS Dated Sites — download button for IPSDatedSites*.cfm.
   Companion to ips_rdf.js. Include both, in this order:

     <script src="ips_rdf.js"></script>
     <script src="ips_rdf_button.js" defer></script>

   and put a button with id="downloadTtl" on the page.
   --------------------------------------------------------------- */
(function () {
  'use strict';

  /* Deliberately the RAW ColdFusion rows, not the normalised ones the
     plot builds: the export must not depend on whether D3 has run. */
  function sourceRows() {
    if (typeof window.rdfRows !== 'undefined') return window.rdfRows;
    if (typeof window.data !== 'undefined') return window.data;
    throw new Error('No row data on the page (expected `data` or `rdfRows`).');
  }

  function download(text, name, mime) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 150);
  }

  function stamp() {
    return new Date().toISOString().slice(0, 10);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('downloadTtl');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var old = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Building triples\u2026';
      try {
        var triples = window.IPSRDF.buildTriples(sourceRows(), {});
        download(window.IPSRDF.toTurtle(triples),
                 'IPSDatedSites-live-' + stamp() + '.ttl',
                 'text/turtle;charset=utf-8');
        btn.textContent = triples.length + window.IPSRDF.PRELUDE_TRIPLES
                        + ' triples \u2713';
      } catch (err) {
        /* Show the real error. A failure here means the row set on the
           page no longer carries what the model needs, and that is worth
           seeing rather than swallowing. */
        btn.textContent = 'Failed \u2014 see console';
        console.error('RDF export failed:', err);
      }
      setTimeout(function () {
        btn.disabled = false;
        btn.textContent = old;
      }, 4000);
    });
  });
})();
