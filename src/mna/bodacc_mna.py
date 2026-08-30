"""
M&A axis — mergers & acquisitions (Data Room questions B11, B13, B14).

STATUS: not yet implemented. This module is a spec for the next
contributor (or the next Claude session) to fill in.

Questions this covers:
  B11 - Volume and average value of M&A transactions, last 3 years,
        per department vs national average vs Baden-Württemberg.
  B13 - Number of mergers completed, by sector, same comparison.
  B14 - Number of acquisitions completed, by sector, same comparison.

Data sources & approach:
  - Mergers (B13): legally must be published in Bodacc (Bulletin
    officiel des annonces civiles et commerciales) as a
    "fusion" / "TUP" (transmission universelle de patrimoine) notice.
    Free, public, structured API via opendatasoft:
    https://bodacc-datadila.opendatasoft.com/api/records/1.0/search/
    Filter `familleavis_lib` for merger-related notice types, and
    the registered-office department for geography. This is the same
    portal src/failures/bodacc_failures.py needs — consider factoring
    a shared src/common/bodacc_client.py once both are built, so
    pagination/rate-limiting logic isn't duplicated.
  - Acquisitions (B14): the Data Room sheet itself flags this as not
    reliably obtainable from Bodacc — most share-transfer acquisitions
    carry no legal publication requirement. Options, in order of
    effort:
      1. Treat acquisitions as structurally under-counted and report
         only what Bodacc-adjacent signals catch (e.g. capital-hold
         changes disclosed via Infogreffe/RNE extracts, where
         accessible).
      2. Supplement with desk research from trade press, same sources
         listed in src/lbo/lbo_manual.py, using the same manual-CSV +
         source_url pattern.
    Document explicitly in the final deliverable that acquisition
    counts are a lower bound, not a complete count — this caveat
    matters more here than anywhere else in the project.
  - Transaction *value* (part of B11): almost never disclosed in
    Bodacc notices. Expect this half of B11 to rely on manual/desk
    research (trade press deal values) rather than a script, similar
    to the LBO axis.
  - Baden-Württemberg equivalent: Germany has no Bodacc analogue —
    mergers/acquisitions of German companies are recorded in the
    Handelsregister (commercial register) but bulk/free structured
    access is limited. Realistic sourcing is again trade press
    (F&A Aktuell, Unquote) via the manual-CSV pattern.

TODO:
  1. Implement a Bodacc client (opendatasoft search API) filtered to
     merger notices, paginated, for the 3 departments + France.
     Consider sharing this with src/failures/bodacc_failures.py.
  2. Aggregate merger counts by year x department x NAF section.
  3. Build data/manual/acquisitions.csv and data/manual/mna_values.csv
     (mirroring src/lbo/lbo_manual.py's REQUIRED_COLUMNS + source_url
     pattern) for the acquisition-count and deal-value gaps.
  4. Plot with src/common/plotting.grouped_region_bar().
"""
