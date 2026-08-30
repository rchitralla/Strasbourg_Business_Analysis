# Strasbourg Business Analysis — Alsace-Moselle / Baden-Württemberg

Data-driven answers to the questions in `docs/data_room_questions.xlsx`
("Data Meetup — Into the Data Room": Data & Business-Law synergies across
the Alsace / Baden-Württemberg border). Every question compares Bas-Rhin,
Haut-Rhin and Moselle against the France national average and against
Baden-Württemberg, over the last 3 years.

See `docs/DATA_SOURCES.md` for the full question-by-question mapping to
data source and implementation status.

## Project layout

```
config/regions.py            # department/region codes, shared time window
src/
  common/
    sectors.py                # shared NAF (FR) / WZ2008 (DE) sector labels
    plotting.py                # shared chart styling (one look across axes)
  company_creation/            # IMPLEMENTED
    france_creations.py        # INSEE Recherche d'Entreprises API, dept-level
    strasbourg_drilldown.py    # commune-level companion charts for Strasbourg
    germany_registrations.py   # GENESIS/Regionalstatistik API (Jupyter-driven)
  macro/gdp_inflation.py       # SPEC ONLY — GDP, inflation, FDI
  failures/bodacc_failures.py  # SPEC ONLY — corporate failure rates
  mna/bodacc_mna.py            # SPEC ONLY — mergers & acquisitions
  lbo/lbo_manual.py            # SPEC + loader — LBOs (manual dataset)
data/
  raw/        gitignored API dumps (regenerate, don't commit)
  processed/  tidy CSVs each script produces
  manual/     hand-curated, source-cited datasets (FDI, LBO deals, ...)
outputs/
  charts/     PNGs, PowerPoint-ready (16:9, 200dpi)
  tables/     any summary tables exported for the deck
docs/
  data_room_questions.xlsx   # original brief
  DATA_SOURCES.md             # question -> source -> status mapping
notebooks/    exploratory analysis (esp. for the Jupyter-driven German script)
```

Each axis is its own package under `src/` so a module can be developed and
run independently — you don't need the M&A code working to chart company
creations. `config/regions.py` and `src/common/` are the only things every
axis depends on, which keeps region codes and sector labels/chart styling
consistent across every chart in the final deck.

## Setup

```bash
pip install -r requirements.txt
```

The French company-creation script needs no API key. The German script
needs a free account at regionalstatistik.de/genesis/online (see its
docstring).

## Step-by-step plan

**1. Company creations (B16-B18) — ready to run now**
   ```bash
   python -m src.company_creation.france_creations       # Bas-Rhin/Haut-Rhin/Moselle
   python -m src.company_creation.strasbourg_drilldown    # Strasbourg-only companion chart
   ```
   This answers B16 (creations by sector) and B17 (sole proprietorships,
   via `nature_juridique` filtering) directly, and B18 (share of
   multi-partner companies) via the `is_sole_shareholder` column already
   in the output CSV — add one groupby to turn that into a percentage.

**2. Company creations, German side (B16-B18 comparison)**
   In Jupyter: `from src.company_creation import germany_registrations as bw`,
   then run `bw.set_credentials()` → `bw.search_tables_for_statistic()` →
   find the Kreise × WZ2008 breakdown table → `bw.inspect_table_metadata(...)`
   → confirm column names in `tidy_dataframe()` → `bw.run_all(table_code)`.
   This is the one step that needs a human in the loop (picking the right
   table code from GENESIS's catalogue) — budget 30-60 min for it.

**3. Extend `france_creations.py` for B19-B22**
   - B19 (avg. share capital): the API's `capital_social` field is already
     in the raw records; extend `extract_row()` to pull it and aggregate
     with `.mean()` instead of `.count()`.
   - B21-B22 (German subsidiaries, cross-border legal forms): needs a
     filter for foreign-parent companies. Investigate whether
     `dirigeants`/`complements` fields in the API response expose parent
     nationality, or whether this needs a join against Bodacc "TUP"/
     branch-creation notices instead.

**4. Macro-economy (B7-B9)**
   Build against INSEE's BDM API (regional GDP + CPI, Grand Est proxy for
   the 3 departments) and Destatis/regionalstatistik.de (Baden-Württemberg
   GDP/CPI, same GENESIS pattern as step 2). FDI (B8) has no sub-national
   API — populate `data/manual/fdi.csv` from Banque de France / GTAI
   publications instead; see the module docstring for the exact plan.

**5. Corporate failures (B9) + M&A (B11, B13, B14)**
   Both need a Bodacc opendatasoft client — build one shared
   `src/common/bodacc_client.py` (paginated search, rate-limited, like
   `fetch_companies()` in `france_creations.py`) and have
   `src/failures/bodacc_failures.py` and `src/mna/bodacc_mna.py` both use
   it, filtering on different `familleavis_lib` values (insolvency vs.
   merger notices). Acquisition counts (B14) and deal values (part of
   B11) aren't reliably in Bodacc — supplement with a manual CSV using the
   same `source_url`-required pattern as the LBO loader.

**6. LBO (B24)**
   Curate `data/manual/lbo_deals.csv` from trade press (see module
   docstring for source list), validate with
   `src/lbo/lbo_manual.load_and_validate()`, then aggregate and plot.

**7. Assemble the deck**
   Once each axis has produced its `outputs/charts/*.png`, pull them
   into the PowerPoint in the order of the Data Room sheet's rows
   (Macro-économie → M&A → Constitutions d'entreprises → LBO). Every
   manually sourced number must carry its citation on the slide, per the
   `source_url` columns enforced above.

## Known caveats to carry into the final deck

- France's Sirene-based creation stats include liberal professions and
  agriculture; Germany's Gewerbeanzeigen statistic excludes both —
  cross-country totals are not apples-to-apples without a footnote.
- "France national average" for company creations needs the bulk Sirene
  Stock export, not this project's paginated API call (too many records).
- FDI and LBO axes are manual/desk-research by nature — no public API
  exists at the required granularity in either country.
- Acquisition counts (B14) are a lower bound: most share-transfer
  acquisitions carry no legal publication requirement in France.
