"""
Baden-Württemberg Company Creations BY SECTOR — statistic 52111
=================================================================

Closes the sector gap left by germany_registrations.py (statistic 52311,
"Gewerbeanzeigenstatistik", which has NO WZ/sector classifying variable
at all — see that module's docstring for the confirmation). Statistic
52111 ("Unternehmensregister-System") publishes actual business-
DEMOGRAPHY events (foundings/closures/survivors) broken down by WZ 2008
economic section, on table 52111-54-01-4-B — this is the real German
counterpart to France's NAF-by-creation data.

CONFIRMED live (2026-09-12), via inspect_table_metadata() and a real
fetch_and_parse_table() call against table 52111-54-01-4-B (cross-checked
against the user's manual CSV export of the same table):

    Three classifying-variable levels (52311's tables only have two):
      1_variable_code = "DLAND"    -> region (Bundesländer) — same
                                       pattern as germany_registrations.py
      2_variable_code = "WZ08ABS"  -> WZ 2008 economic section (this is
                                       the real sector split)
      3_variable_code = "URSPOP1"  -> demographic event type. Real
                                       confirmed attribute codes:
                                         INSGESAMT  = Insgesamt (stock)
                                         URS-UNT026 = Unternehmensgründungen
                                                      (creations — what we want)
                                         URS-UNT028 = Unternehmensschließungen
                                                      (closures)
                                         URS-UNT030 = Überlebende Unternehmen
                                                      aus t-3 (survivors)
      value_variable_code = "UNT002" ("Unternehmen (B-N, P-S ohne S94)")

    Data only covers 2021-2023 (confirmed via the GENESIS table-builder
    page: "Verfügbarer Zeitraum: 2021 - 2023") — a much narrower window
    than statistic 52311's, and short of the full 3-year Data Room ask,
    but it is the only sector-classified creation count Destatis
    publishes at this level. Document this window explicitly wherever a
    French-vs-German sector chart is shown.

Usage (DESIGNED FOR JUPYTER, same pattern as germany_registrations.py):
    from src.company_creation import germany_registrations as bw
    from src.company_creation import germany_creations_by_sector as bws

    bw.set_credentials()   # shared credential store — set once, used by
                            # both modules (this one reuses bw's HTTP client)

    df, df_raw = bws.run_all()
    # or step by step:
    bws.inspect_table_metadata()
    df_raw = bws.fetch_and_parse_table()
    df = bws.tidy_dataframe(df_raw)
    bws.plot_stacked_bar(df)
    bws.plot_sector_totals(df)
"""

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.regions import GERMAN_REGIONS
from src.common.plotting import new_figure, save, PRIMARY_COLOR, BRAND_COLORMAP

# Reuses germany_registrations' shared GENESIS HTTP client (credentials +
# POST/auth-header plumbing) instead of duplicating it — bw.set_credentials()
# sets the module-level RGDB_USERNAME/RGDB_PASSWORD that _post() reads from,
# so calling it once covers both modules.
from src.company_creation.germany_registrations import _post, inspect_table_metadata

STATISTIC_CODE = "52111"  # Unternehmensregister-System (business register)
TABLE_CODE = "52111-54-01-4-B"

REGIONALVARIABLE_LAND = "DLAND"
REGIONAL_KEY = GERMAN_REGIONS["baden_wurttemberg"].ags_code

SECTOR_VARIABLE = "WZ08ABS"
EVENT_VARIABLE = "URSPOP1"
EVENT_CREATIONS = "URS-UNT026"   # Unternehmensgründungen — genuine new creations
EVENT_CLOSURES = "URS-UNT028"    # Unternehmensschließungen
EVENT_SURVIVORS = "URS-UNT030"   # Überlebende Unternehmen aus t-3
EVENT_TOTAL = "INSGESAMT"        # Insgesamt (stock)

# CONFIRMED live: this table's actual coverage, narrower than statistic
# 52311's MIN_YEAR/MAX_YEAR — don't import those here, GENESIS has nothing
# outside this window for 52111-54-01-4-B anyway.
START_YEAR = 2021
END_YEAR = 2023

# WZ 2008 codes as they actually appear in this table's WZ08ABS attribute
# (confirmed live + cross-checked against the user's manual CSV export),
# mapped to a section label comparable with France's NAF sections
# (src.common.sectors.NAF_WZ_SECTION_LABELS). Several WZ08ABS codes here
# are PRE-AGGREGATED spans (e.g. "WZ08-B-18" covers NAF sections B-E)
# rather than a single letter, so they get a combined label directly
# instead of forcing a single NAF letter onto them.
WZ08_LABELS = {
    "WZ08-B-18": "Mining, manufacturing, energy & water (B-E)",
    "WZ08-F": "Construction (F)",
    "WZ08-G": "Retail & wholesale trade (G)",
    "WZ08-H": "Transportation & storage (H)",
    "WZ08-I": "Accommodation & food service (I)",
    "WZ08-J": "Information & communication (J)",
    "WZ08-K-L": "Finance, insurance & real estate (K-L)",
    "WZ08-M-N": "Professional & administrative services (M-N)",
    "WZ08-P-Q": "Education, health & social work (P-Q)",
    "WZ08-R-S": "Arts, entertainment & other services (R-S)",
}


def fetch_and_parse_table(
    table_code: str = TABLE_CODE,
    regional_key: str = REGIONAL_KEY,
    regionalvariable: str = REGIONALVARIABLE_LAND,
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
) -> pd.DataFrame:
    """
    Same ffcsv fetch/unzip logic as germany_registrations.fetch_and_parse_table
    (via the shared _post() HTTP helper — credentials set once through
    bw.set_credentials() work here too) but defaulting to this statistic's
    own table code and confirmed 2021-2023 availability window.
    """
    response = _post("data/tablefile", {
        "name": table_code,
        "area": "free",
        "format": "ffcsv",
        "compress": "true",
        "startyear": start_year,
        "endyear": end_year,
        "regionalvariable": regionalvariable,
        "regionalkey": regional_key,
        "language": "de",
    }, timeout=60)
    response.raise_for_status()

    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            inner_name = zf.namelist()[0]
            with zf.open(inner_name) as f:
                df = pd.read_csv(f, sep=";", encoding="utf-8-sig")
    except zipfile.BadZipFile:
        df = pd.read_csv(io.StringIO(response.text), sep=";")

    print("Columns returned by the API:")
    print(list(df.columns))
    print("\nFirst few rows:")
    print(df.head())
    return df


def tidy_dataframe(df_raw: pd.DataFrame, event: str = EVENT_CREATIONS) -> pd.DataFrame:
    """
    Reduce the raw ffcsv table to a tidy (year, region, sector, count)
    DataFrame, filtered to one demographic-event type (default:
    Unternehmensgründungen — genuine new company creations).

    CONFIRMED live (2026-09-12) real column names:
      time                        -> year
      1_variable_attribute_label  -> region (e.g. "Baden-Württemberg")
      2_variable_attribute_code   -> WZ08ABS sector code (e.g. "WZ08-G")
      2_variable_attribute_label  -> WZ08ABS sector's German label
      3_variable_attribute_code   -> URSPOP1 event code — the filter target
      value                       -> the count
    """
    YEAR_COL = "time"
    REGION_COL = "1_variable_attribute_label"
    SECTOR_CODE_COL = "2_variable_attribute_code"
    SECTOR_LABEL_COL = "2_variable_attribute_label"
    EVENT_COL = "3_variable_attribute_code"
    VALUE_COL = "value"

    missing = [c for c in (YEAR_COL, REGION_COL, SECTOR_CODE_COL, SECTOR_LABEL_COL, EVENT_COL, VALUE_COL)
               if c not in df_raw.columns]
    if missing:
        raise KeyError(
            f"Expected column(s) {missing} not found. "
            f"Available columns: {list(df_raw.columns)}. "
            "Update the *_COL constants in tidy_dataframe() to match."
        )

    df = df_raw[df_raw[EVENT_COL] == event].copy()
    if df.empty:
        print(f"WARNING: no rows matched event={event!r} — nothing to tidy. "
              f"Distinct event codes seen: {sorted(df_raw[EVENT_COL].unique())}.")
        return df

    df = df[[YEAR_COL, REGION_COL, SECTOR_CODE_COL, SECTOR_LABEL_COL, VALUE_COL]].copy()
    df.columns = ["year", "region", "sector_code", "sector_label_de", "count"]
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
    df = df.dropna(subset=["year", "count"])
    df["year"] = df["year"].astype(int)

    df["sector"] = df["sector_code"].map(WZ08_LABELS)
    unmapped = sorted(df.loc[df["sector"].isna(), "sector_code"].unique())
    if unmapped:
        print(f"WARNING: {len(unmapped)} WZ08ABS code(s) not in WZ08_LABELS, "
              f"falling back to the raw German label for these — add them "
              f"to WZ08_LABELS if they should map to a named section: {unmapped}")
        df["sector"] = df["sector"].fillna(df["sector_label_de"])

    df = df.sort_values(["year", "sector"]).reset_index(drop=True)
    return df[["year", "region", "sector", "count"]]


def plot_stacked_bar(df: pd.DataFrame, output_path: str = "outputs/charts/bw_creations_by_sector.png"):
    pivot = df.pivot_table(index="year", columns="sector", values="count", aggfunc="sum", fill_value=0)
    pivot = pivot[pivot.sum().sort_values(ascending=False).index]

    fig, ax = new_figure()
    pivot.plot(kind="bar", stacked=True, ax=ax, colormap=BRAND_COLORMAP, width=0.8)
    ax.set_title("New Company Creations in Baden-Württemberg by Year and Sector", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of new companies (Unternehmensgründungen)")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8, title="WZ 2008 sector")
    save(fig, output_path)


def plot_sector_totals(df: pd.DataFrame, output_path: str = "outputs/charts/bw_creations_by_sector_total.png"):
    sector_totals = df.groupby("sector")["count"].sum().sort_values(ascending=True)
    fig, ax = new_figure()
    ax.barh(sector_totals.index, sector_totals.values, color=PRIMARY_COLOR)
    ax.set_title("Total Company Creations in Baden-Württemberg by Sector (2021-2023)", fontsize=15, pad=12)
    ax.set_xlabel("Number of new companies (Unternehmensgründungen)")
    save(fig, output_path)


def run_all(table_code: str = TABLE_CODE, regional_key: str = REGIONAL_KEY,
            regionalvariable: str = REGIONALVARIABLE_LAND):
    """
    Fetch, tidy, save, and chart creations-by-sector in one go.
    Credentials must already be set via germany_registrations.set_credentials()
    (shared across both modules — see module docstring).

    Returns (df, df_raw) so you can inspect the raw fetch (e.g. to check
    for new/unmapped WZ08ABS codes) without re-fetching.
    """
    print("Inspecting table metadata...")
    inspect_table_metadata(table_code)

    print("\nFetching and tidying data...")
    df_raw = fetch_and_parse_table(table_code, regional_key=regional_key, regionalvariable=regionalvariable)
    df = tidy_dataframe(df_raw)

    csv_path = "data/processed/bw_creations_by_sector.csv"
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"Tidy data saved to: {csv_path}")

    print("\nGenerating chart images...")
    plot_stacked_bar(df)
    plot_sector_totals(df)
    print("\nAll charts saved — ready to insert into PowerPoint.")
    print("\nNOTE: this table only covers 2021-2023 (confirmed via the "
          "GENESIS table-builder page) — narrower than the rest of the "
          "project's year range. Caption this window explicitly wherever "
          "this chart is shown.")

    return df, df_raw
