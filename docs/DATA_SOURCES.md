# Data sources — mapped to Data Room questions

Source: `docs/data_room_questions.xlsx` ("Data Meetup — Into the Data Room",
2026-08-29). Comparison scope on every question: Bas-Rhin, Haut-Rhin,
Moselle vs. France national average vs. Baden-Württemberg, last 3 years.

| # | Question (short) | Axis | Module | Data source | Status |
|---|---|---|---|---|---|
| B7 | GDP & inflation evolution | Macro-economy | `src/macro/gdp_inflation.py` | INSEE BDM (regional), Destatis/regionalstatistik.de | Spec only |
| B8 | FDI flows | Macro-economy | `src/macro/gdp_inflation.py` | Banque de France (national only) — no sub-national API; manual/desk research | Spec only |
| B9 | Corporate failure rates by sector | Macro-economy / Failures | `src/failures/bodacc_failures.py` | Bodacc (opendatasoft API), INSEE défaillances index, Destatis EVAS 52411 | Spec only |
| B11 | M&A volume & average value | M&A | `src/mna/bodacc_mna.py` | Bodacc for volume; trade press for value | Spec only |
| B13 | Mergers completed, by sector | M&A | `src/mna/bodacc_mna.py` | Bodacc (opendatasoft API) — legally required publication | Spec only |
| B14 | Acquisitions completed, by sector | M&A | `src/mna/bodacc_mna.py` | No legal publication requirement — under-counted from Bodacc; supplement manually | Spec only |
| B16 | Company creations by sector | Company creation | `src/company_creation/france_creations.py` + `germany_registrations.py` | INSEE Recherche d'Entreprises API (France); GENESIS EVAS 52311 (Germany) | **Implemented (FR)**, spec (DE table code TBD) |
| B17 | Sole proprietorships by sector | Company creation | `src/company_creation/france_creations.py` | Same API — filter `nature_juridique` | **Implemented** |
| B18 | Share of multi-partner companies | Company creation | `src/company_creation/france_creations.py` | Same API — derived from `is_sole_shareholder` flag | **Implemented** |
| B19 | Average share capital at formation | Company creation | `src/company_creation/france_creations.py` | Same API — `capital_social` field (not yet extracted) | Not started |
| B20 | Capital increases: amount & average | Company creation | *(new module needed)* | Bodacc ("modification du capital" notices) | Not started |
| B21 | German subsidiaries created | Company creation | `src/company_creation/france_creations.py` | Same API — filter on foreign parent / RCS mentions; needs investigation | Not started |
| B22 | Legal forms in cross-border setups | Company creation | `src/company_creation/france_creations.py` | Same API — `nature_juridique`, cross-referenced with B21 filter | Not started |
| B24 | LBOs completed, by sector | LBO | `src/lbo/lbo_manual.py` | No API exists — manual/desk research from trade press | Spec + loader only |

## Notes on comparability

- **France vs. Germany scope mismatch**: France's Sirene-based creation
  stats include liberal professions and agriculture; Germany's
  Gewerbeanzeigen statistic excludes both. Always caveat cross-country
  totals in the final deck (see `germany_registrations.py` docstring).
- **"National average" for France**: the paginated Recherche d'Entreprises
  API is not practical for a full-France pull (millions of records). Use
  the bulk Sirene "Stock" CSV export (data.gouv.fr) instead, or INSEE's
  pre-aggregated national creation statistics, for that one line.
- Questions marked "Spec only" have a module with a detailed docstring
  (data source, API, caveats, TODOs) but no working fetch code yet — see
  the step-by-step plan in `README.md`.
