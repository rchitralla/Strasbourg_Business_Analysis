"""
Corporate failures axis (Data Room question B9, second half — failure
rates "by sector").

STATUS: not yet implemented. This module is a spec for the next
contributor (or the next Claude session) to fill in.

Question this covers:
  B9 - Corporate failure rates by sector, last 3 years, per department
       (Bas-Rhin, Haut-Rhin, Moselle) vs national average vs
       Baden-Württemberg.

Data sources & approach:
  - Bodacc (Bulletin officiel des annonces civiles et commerciales)
    publishes every French insolvency proceeding (redressement
    judiciaire, liquidation judiciaire) as a structured, free, public
    dataset via the opendatasoft API:
    https://bodacc-datadila.opendatasoft.com/api/records/1.0/search/
    Filter on `familleavis_lib` / `typeavis` for insolvency notices and
    on the registered office department for geography. This is the
    same portal src/mna/bodacc_mna.py uses for M&A — consider a shared
    src/common/bodacc_client.py once both are implemented, to avoid
    duplicating pagination/rate-limit logic.
  - INSEE also publishes an annual "défaillances d'entreprises" index
    (BDM series) at the regional level, useful as a cross-check /
    trend line even though it isn't department-granular.
  - Failure *rate* (vs. raw count) needs a denominator: the stock of
    active companies per department/sector. Pull that from the same
    Recherche d'Entreprises / Sirene source used in
    src/company_creation/france_creations.py (active establishment
    counts), or from INSEE's Sirene "stock" statistics.
  - Baden-Württemberg equivalent: "Unternehmensinsolvenzen" statistic
    (EVAS 52411) on regionalstatistik.de, same GENESIS webservice
    pattern as src/company_creation/germany_registrations.py.

TODO:
  1. Implement a Bodacc client (opendatasoft search API) filtered to
     insolvency notices, paginated, for the 3 departments + France.
  2. Aggregate by year x department x NAF section using
     src/common/sectors.NAF_WZ_SECTION_LABELS for consistent labels.
  3. Pull the active-company denominator and compute failure rate =
     failures / active companies, per department x sector x year.
  4. Implement the Baden-Württemberg EVAS 52411 pull, mirroring
     germany_registrations.py's fetch_and_parse_table() pattern.
  5. Plot with src/common/plotting.grouped_region_bar().
"""
