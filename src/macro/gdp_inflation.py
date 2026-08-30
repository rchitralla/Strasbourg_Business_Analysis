"""
Macro-economy axis — GDP, inflation, FDI (Data Room questions B7-B9).

STATUS: not yet implemented. This module is a spec for the next
contributor (or the next Claude session) to fill in.

Questions this covers:
  B7 - GDP and inflation evolution, last 3 years, per department
       (Bas-Rhin, Haut-Rhin, Moselle) vs national average vs
       Baden-Württemberg.
  B8 - Foreign Direct Investment (FDI) flows, same comparison.
  B9 - Corporate failure rates by sector, same comparison
       (see also src/failures/ — Bodacc-based, closely related).

Data sources & approach:
  - GDP by department: INSEE "PIB en valeur" / comptes régionaux
    (dataset "PIB_REGIONS" or the "Produit intérieur brut régional"
    series on insee.fr). INSEE does not publish official GDP at the
    department level every year — regional (grand-région, i.e. Grand
    Est) GDP is the finest granularity usually available; department-
    level GDP may need to be estimated or substituted with a proxy
    (e.g. "valeur ajoutée" by department, which INSEE does publish).
  - Inflation: INSEE consumer price index (IPC) is published at the
    regional level, not department level, via the BDM (Banque de
    Données Macroéconomiques) API: https://www.insee.fr/en/statistiques/serie/...
    Use the "Grand Est" region series as the proxy for the three
    Alsace-Moselle departments; France entière for the national line.
  - Baden-Württemberg GDP/inflation: Destatis / regionalstatistik.de,
    same GENESIS webservice used in
    src/company_creation/germany_registrations.py (EVAS 82000-series
    for GDP, "Verbraucherpreisindex" tables for inflation).
  - FDI (B8): no clean department-level API exists. The Banque de
    France publishes FDI stocks/flows at the national level only; for
    sub-national FDI the Data Room sheet itself flags this as
    "Ask Claude" (i.e. manual desk research), not an API pull. Track
    manually sourced figures in data/manual/fdi.csv with a citation
    per row (see src/lbo/lbo_manual.py for the expected manual-CSV
    pattern) rather than trying to script this one.

TODO:
  1. Implement fetch_insee_bdm_series() against the INSEE BDM API for
     regional GDP and CPI series (Grand Est + France).
  2. Implement fetch_destatis_gdp() against regionalstatistik.de for
     Baden-Württemberg (EVAS 82000 "Volkswirtschaftliche
     Gesamtrechnungen der Länder").
  3. Build data/manual/fdi.csv by hand from Banque de France / GTAI
     (Germany Trade & Invest) publications, one row per
     region x year x flow-direction, each with a Source column.
  4. tidy + plot using src/common/plotting.grouped_region_bar().
"""
