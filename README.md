# Strasbourg Business Analysis — Alsace-Moselle / Baden-Württemberg

Data-driven answers to the questions in `docs/data_room_questions.xlsx`
("Data Meetup — Into the Data Room": Data & Business-Law synergies across
the Alsace / Baden-Württemberg border). Built for a talk at La Plage
Digitale, Strasbourg — "Market Audit: Inside the Strasbourg Data Room."

Two independent public-data pipelines — one per country — cover company
creations, corporate failures, and an LBO proxy for Bas-Rhin, Haut-Rhin,
Moselle and Baden-Württemberg, with every headline number cross-checked
against an official published figure before being trusted. See
`docs/DATA_SOURCES.md` for the full question-by-question mapping.

## What's actually implemented

**France — company creations**
- `src/company_creation/sirene_v3_client.py` — the main client, against
  INSEE's Sirene v3.11 API. Cursor-paginated (no 10,000-result cap, unlike
  the older `france_creations.py` wrapper this replaces). Filters on the
  *enterprise's* own creation date plus head-office flag, not raw
  establishment creation — an earlier version overcounted by ~77%
  (branch openings and HQ relocations of existing companies were
  miscounted as new creations); the current filter lands within 8.3% of
  INSEE's own published national total.
- `strasbourg_drilldown.py` — the same client, scoped to the Strasbourg
  commune, for the city-level case study.
- `survival_rate.py` — cohort survival by age-since-creation, plus a
  period life table (survival curve + discrete hazard rate) — the
  practical substitute for a true Kaplan-Meier estimate when only
  current status, not an exact failure date, is available.
- `summarize_b16_b17_b18.py`, `share_capital.py` — legal-form / sole-
  shareholder share and average share-capital summaries, against the
  official INSEE "catégorie juridique" nomenclature
  (`data/manual/insee_categorie_juridique.csv`) and a manual review of
  which legal forms are genuine business creations vs. registry noise
  (VAT-only registrations, public bodies, cooperative unions, etc. —
  `data/manual/legal_form_category_review.csv`).

**France — corporate failures**
- `src/common/bodacc_client.py` — shared client for BODACC (France's
  official gazette of insolvency/legal notices). Parses raw response
  bytes directly rather than trusting `requests`'s guessed encoding,
  which otherwise flips inconsistently between UTF-8/Latin-1 across
  pages of the same fetch.
- `src/failures/bodacc_failures.py` — classifies each notice's free-text
  judgment type into a real taxonomy (opening / conversion / closure /
  plan / personal sanction / administrative / appeal — 56 categories,
  built from live volume across all three departments) so a headline
  "failure" count means an actual new insolvency, not a later procedural
  update on an already-counted case. Also computes real per-company
  closure lifespans (`compute_closure_lifespan()`), joining each
  closure's judgment date against the company's true Sirene creation
  date, rather than assuming a round number.
- `insee_failures.py` — the INSEE statistical-view counterpart (one
  count per "défaillance", no procedure-type breakdown — see
  `docs/DATA_SOURCES.md` for how this differs methodologically from the
  BODACC judicial view).

**France — M&A and LBO**
- `src/mna/bodacc_mna.py`, `scripts/bodacc_debug_mergers.py` — merger/
  fusion notices via BODACC's "Modifications diverses" family.
- `src/lbo/holding_company_proxy.py` — new holding-company creations
  (NAF 6420Z), the Data Room brief's own suggested LBO proxy. Explicitly
  documented as an estimation signal, not an LBO count — no public
  source exists for actual LBO transactions in either country.
- `src/lbo/lbo_manual.py`, `data/manual/lbo_deals.csv` — manual/desk-
  research tracking for deals that can be sourced from trade press.

**Germany**
- `src/company_creation/germany_registrations.py` — business
  registrations (Gewerbeanzeigenstatistik, EVAS 52311). This statistic
  has **no sector/WZ classifying variable at all** (confirmed against
  every classifying variable on the table) — only a registration-reason
  split (new creation / relocation / other).
- `germany_creations_by_sector.py` — a **different** statistic
  (Unternehmensregister-System, EVAS 52111) that *does* publish a real
  WZ-2008 sector breakdown, for a narrower 2021-2023 window. Handles a
  real double-counting risk explicitly: the raw table includes an
  "Insgesamt" grand-total pseudo-row per year that must be split off
  and cross-checked, not folded into the per-sector breakdown.
- `src/failures/germany_insolvencies.py` — business insolvencies (EVAS
  52411), cross-validated exactly against an independently-downloaded
  official Destatis table, all 10 years (2015-2024). Also builds the
  **France-vs-Germany indexed failure-trend comparison** — both
  countries' yearly opening-failure counts indexed to a shared base
  year (raw counts aren't comparable given the population gap between
  Baden-Württemberg and the three French départements combined).

**Macro / FDI**
- `src/macro/gdp_inflation.py`, `src/macro/fdi_manual.py` — mostly
  discovery/spec stage. No sub-national FDI API exists in either
  country at the required granularity; `data/manual/fdi.csv` is a
  manual-tracking template, not yet populated.

## Project layout

```
config/
  regions.py                   # department/region codes, shared time window
src/
  common/
    sectors.py                 # shared NAF (FR) / WZ2008 (DE) sector labels
    plotting.py                 # shared chart styling (one look across every axis)
    bodacc_client.py            # shared BODACC client (failures, M&A, LBO all use this)
    sirene_lookup.py            # per-SIREN enrichment (sector, legal form, creation date)
  company_creation/
    sirene_v3_client.py         # main France client — creations, sector, legal form
    france_creations.py         # older, capped wrapper API — superseded, kept for reference
    strasbourg_drilldown.py     # commune-level case study
    survival_rate.py            # cohort survival + period life table
    summarize_b16_b17_b18.py    # sector/legal-form/sole-shareholder summaries
    share_capital.py            # average share-capital extraction
    germany_registrations.py    # Germany: registrations by reason (no sector variable)
    germany_creations_by_sector.py  # Germany: creations by WZ sector (2021-2023 only)
  failures/
    bodacc_failures.py          # France: judgment classification + closure lifespan
    insee_failures.py           # France: INSEE's own statistical failure count
    germany_insolvencies.py     # Germany: insolvencies + France-Germany comparison chart
  mna/bodacc_mna.py             # France: merger/fusion notices
  lbo/
    holding_company_proxy.py    # France: NAF 6420Z holding-company proxy
    lbo_manual.py                # manual LBO deal tracking
  macro/
    gdp_inflation.py             # discovery stage
    fdi_manual.py                 # manual FDI tracking template
data/
  raw/        gitignored API dumps (regenerate, don't commit)
  processed/  tidy CSVs each script produces (gitignored — regenerate via the scripts)
  manual/     hand-curated, source-cited datasets (legal-form nomenclature, FDI, LBO deals)
outputs/
  charts/     PNGs (gitignored — regenerate via the scripts)
scripts/      one-off debug/discovery scripts referenced by the modules above
docs/
  data_room_questions.xlsx    # original brief
  DATA_SOURCES.md              # question -> source -> status mapping
```

Each axis is its own package under `src/` so a module can be developed and
run independently. `config/regions.py` and `src/common/` are the only
things every axis depends on, which keeps region codes, sector labels,
and chart styling consistent across the whole project.

## Setup

```bash
pip install -r requirements.txt
```

Two sets of credentials, both free:
- **France** (Sirene v3.11): a free API key from
  [api.insee.fr](https://api.insee.fr) — `sv3.set_api_key()` prompts for
  it securely. BODACC needs no key at all.
- **Germany** (GENESIS-Online / Regionalstatistik): a free account at
  [regionalstatistik.de/genesis/online](https://www.regionalstatistik.de/genesis/online)
  — `bw.set_credentials()` prompts for username/password securely.

Everything is designed for interactive use in Jupyter — call
`set_api_key()`/`set_credentials()` once per session, then run each
module's `run_all()` (or the individual steps in its docstring) to
fetch, tidy, cache, and chart.

## Known caveats worth carrying into any presentation of this data

- **Real estate creation counts may run above INSEE's own published
  figures**: INSEE excludes family/non-professional real-estate holding
  companies (mostly SCIs, NAF 68.20A/68.20B) as "non-productive"; this
  pipeline currently classifies sector at the NAF-section level, which
  doesn't yet separate that out from professional real-estate activity
  (agencies, property management — NAF 68.10/68.31/68.32).
- **Germany's registration statistic has no sector breakdown at all**
  (52311) — the sector-classified alternative (52111) only covers
  2021-2023, a narrower window than everything else in this project.
- **A small share of very recent French records lack a sector
  classification** — not a data quality defect, but a genuine
  classification lag: INSEE hasn't yet assigned a NAF code to some
  very recently registered companies at fetch time.
- **BODACC's "Autre jugement..." catch-all categories** (~15-18% of
  notices) can't be classified from the label alone — left explicitly
  unclassified (`None`) rather than guessed.
- **"Survival" and cohort-based life tables measure status as of the
  fetch date, not at a fixed age** — an older cohort has mechanically
  had more time to fail than a younger one; see `survival_rate.py`'s
  module docstring for the full reasoning and its life-table's known
  cohort-vs-age confound.
- **FDI and LBO are manual/desk-research by nature** — no public API
  exists at the required granularity in either country. The LBO
  holding-company proxy is an estimation signal per the Data Room
  brief's own methodology, not a count of actual LBO transactions.
- **Acquisition counts are a lower bound**: most share-transfer
  acquisitions carry no legal publication requirement in France.
