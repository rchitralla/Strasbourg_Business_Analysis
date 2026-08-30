"""
LBO (Leveraged Buy-Out) axis (Data Room question B24).

STATUS: not yet implemented. This module is a spec for the next
contributor (or the next Claude session) to fill in.

Question this covers:
  B24 - Number of LBOs completed, by sector, last 3 years, per
        department vs national average vs Baden-Württemberg.

Data sources & approach:
  - There is no free, structured, public API for LBO transactions in
    either France or Germany. LBOs are a financing structure, not a
    legal-filing category, so they don't appear in Bodacc, Sirene, or
    GENESIS as such. This axis is inherently manual/desk-research,
    same conclusion the Data Room sheet reaches for FDI (B8).
  - Realistic sourcing for a curated, citable dataset:
      - Trade press: Les Echos Capital Finance, Capital Finance,
        Private Equity International, Argus de l'Assurance for
        sector-specific deals, F&A Aktuell / Unquote (Germany).
      - Professional-services deal announcements (law firms, M&A
        boutiques active in Alsace/Bade-Wurtemberg often publish
        "deals of the year" summaries).
      - Bodacc can sometimes surface an LBO indirectly (e.g. a holding
        company creation coinciding with a share transfer), but this
        is unreliable as a primary signal — use only to corroborate a
        deal already found elsewhere.
  - Given the above, this module intentionally does NOT wrap an API.
    It defines the expected shape of a manually curated CSV and a
    loader/validator for it, so the charting side of the pipeline
    still works once someone populates the data.

Expected input file: data/manual/lbo_deals.csv, one row per deal:
  date, department_or_region, sector (NAF/WZ section letter), target,
  sponsor, value_eur (nullable — rarely disclosed), source_url

TODO:
  1. Curate data/manual/lbo_deals.csv from the sources above — every
     row must cite a source_url per the project's "document every
     assumption" convention (see README.md).
  2. Implement load_and_validate() below to check required columns and
     that every row has a source_url.
  3. Aggregate counts by year x region x sector and plot with
     src/common/plotting.grouped_region_bar().
"""

import pandas as pd

REQUIRED_COLUMNS = [
    "date", "department_or_region", "sector", "target", "sponsor",
    "value_eur", "source_url",
]


def load_and_validate(csv_path: str = "data/manual/lbo_deals.csv") -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise KeyError(f"data/manual/lbo_deals.csv is missing columns: {missing_cols}")

    unsourced = df[df["source_url"].isna() | (df["source_url"] == "")]
    if not unsourced.empty:
        raise ValueError(
            f"{len(unsourced)} row(s) have no source_url — every manually "
            "curated deal must cite a source. Offending rows:\n"
            f"{unsourced[['date', 'target']]}"
        )

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    return df
