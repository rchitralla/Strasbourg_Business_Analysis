"""
Foreign Direct Investment (FDI) axis (Data Room question B8).

STATUS: desk-research only, by design — no department- or region-level
FDI API exists for either country (Banque de France publishes FDI
stocks/flows at the NATIONAL level only; the German equivalent,
Bundesbank, likewise). This is the same conclusion already reached for
the LBO axis (see src/lbo/lbo_manual.py, whose manual-CSV pattern this
mirrors exactly) — not a gap to close with more API work.

Expected input file: data/manual/fdi.csv, one row per (year, region,
flow_direction):
  year, region, flow_direction (inbound/outbound), value_eur,
  source_url, notes

Realistic sourcing:
  - Banque de France's balance-of-payments FDI statistics (national
    only) — use for the "France (national)" row; there is no
    department-level split, the same structural gap already flagged
    for GDP (see src/macro/gdp_inflation.py's docstring).
  - Deutsche Bundesbank FDI statistics (national) and GTAI (Germany
    Trade & Invest) regional investment reports for a Baden-
    Württemberg-specific figure, if GTAI publishes one at Land level.
  - A regional investment agency for Grand Est (e.g. "Invest in Grand
    Est" / local CCI) sometimes publishes an annual foreign-investment
    figure for the region — the closest available proxy for Bas-Rhin/
    Haut-Rhin/Moselle, which (like GDP) have no FDI figure of their own.
  - Business France's annual "Bilan de l'attractivité" report tabulates
    foreign investment PROJECT COUNTS (not euro values) by region —
    often the most citable region-level number available, even without
    a matching euro amount; use the notes column to flag when a row is
    a count rather than a value.

TODO:
  1. Populate data/manual/fdi.csv from the sources above — every row
     must cite a source_url per the project's "document every
     assumption" convention (see README.md).
  2. Decide whether to report project COUNTS (Business France style) or
     euro VALUES (Banque de France style) as the headline number — they
     come from different sources and are not directly comparable;
     value_eur may be left blank with a count noted instead.
  3. Chart with src/common/plotting.grouped_region_bar() once populated.
"""

import pandas as pd

REQUIRED_COLUMNS = ["year", "region", "flow_direction", "value_eur", "source_url"]
VALID_FLOW_DIRECTIONS = {"inbound", "outbound"}


def load_and_validate(csv_path: str = "data/manual/fdi.csv") -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise KeyError(f"{csv_path} is missing columns: {missing_cols}")

    unsourced = df[df["source_url"].isna() | (df["source_url"] == "")]
    if not unsourced.empty:
        raise ValueError(
            f"{len(unsourced)} row(s) have no source_url — every manually "
            "curated FDI figure must cite a source. Offending rows:\n"
            f"{unsourced[['year', 'region']]}"
        )

    bad_directions = sorted(set(df["flow_direction"].dropna()) - VALID_FLOW_DIRECTIONS)
    if bad_directions:
        raise ValueError(
            f"flow_direction must be one of {VALID_FLOW_DIRECTIONS}, found: {bad_directions}"
        )

    return df
