"""
Baden-Württemberg Business Registrations — Data Collection & Visualization
============================================================================

Pulls "Gewerbeanmeldungen" (new business registrations) data for
Baden-Württemberg / its Kreise (districts) from the official German
GENESIS statistics webservice (Regionaldatenbank Deutschland), which is
the German equivalent of the French INSEE Sirene/Recherche d'Entreprises
APIs used in france_creations.py. This is the German side of Data Room
questions B16-B18 and B21-B22 (creations by sector, legal forms used,
German subsidiaries).

DESIGNED FOR JUPYTER — usage:
------------------------------
    from src.company_creation import germany_registrations as bw

    # 1. Set credentials (prompts securely, nothing typed into a cell
    #    is saved in the notebook file):
    bw.set_credentials()

    # 2. Step A — list candidate tables under the Gewerbeanzeigenstatistik
    tables = bw.search_tables_for_statistic()

    # 3. Step B — once you spot the right table code in that list (look
    #    for one broken down by Kreise + Wirtschaftsabschnitte/WZ2008),
    #    inspect its structure to confirm variable/column names:
    bw.inspect_table_metadata("52311-XX-XX-X")

    # 4. Step C — fetch, tidy, and chart it:
    df_raw = bw.fetch_and_parse_table("52311-XX-XX-X")
    df = bw.tidy_dataframe(df_raw)   # adjust YEAR_COL/SECTOR_COL/VALUE_COL
                                       # inside this function if needed —
                                       # check the printed columns from
                                       # fetch_and_parse_table() first
    bw.plot_yearly_trend(df)
    bw.plot_stacked_bar(df)
    bw.plot_sector_totals(df)

Nothing runs automatically on import — every step above is a separate
function call, so you can inspect output at each stage before moving on.

IMPORTANT CONTEXT:
-------------------
1. Free registration required at https://www.regionalstatistik.de/genesis/online

2. The relevant statistic is EVAS 52311 "Gewerbeanzeigenstatistik"
   (trade/business registration statistics). It records:
     - Neuerrichtungen  -> genuine new business creations (closest match
                           to INSEE's "créations d'entreprises")
     - Zuzug            -> relocation of an existing business into the area
     - Übernahme        -> takeover of an existing business
   For a fair comparison with the French data, you generally want to
   filter for "Neuerrichtungen" specifically.

3. Structural difference from France: Germany's Gewerbeanzeigen statistic
   does NOT cover "Freiberufler" (liberal professions — doctors, lawyers,
   architects, consultants, etc.) or agriculture/forestry, since these
   aren't required to register a "Gewerbe". France's Sirene-based creation
   stats DO include these. Keep this in mind when comparing absolute
   totals between the French departments and a Baden-Württemberg Kreis —
   document this caveat wherever the comparison is shown (see
   docs/DATA_SOURCES.md).

4. I could not verify the exact table code / column layout myself (no
   live network access in the environment that wrote this script), so
   double-check the printed columns at each step before trusting the
   final chart.

Requirements:
    pip install requests pandas matplotlib
"""

import io
import os
import sys
import zipfile
from getpass import getpass
from pathlib import Path

import requests
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.regions import GERMAN_REGIONS, MIN_YEAR, MAX_YEAR
from src.common.sectors import NAF_WZ_SECTION_LABELS
from src.common.plotting import new_figure, save

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.regionalstatistik.de/genesisws/rest/2020/"

# Prefer set_credentials() (below) over hardcoding these directly.
RGDB_USERNAME = os.environ.get("RGDB_USERNAME", "")
RGDB_PASSWORD = os.environ.get("RGDB_PASSWORD", "")


def set_credentials(username: str = None, password: str = None):
    """
    Set your GENESIS/Regionalstatistik credentials for this session.

    Call with no arguments in a Jupyter cell to be prompted securely
    (the password won't be echoed or saved in the notebook file):

        bw.set_credentials()

    Or pass them directly (e.g. if reading from your own secrets manager):

        bw.set_credentials(username="...", password="...")
    """
    global RGDB_USERNAME, RGDB_PASSWORD
    RGDB_USERNAME = username if username is not None else input("GENESIS username: ")
    RGDB_PASSWORD = password if password is not None else getpass("GENESIS password: ")
    print("Credentials set for this session.")

STATISTIC_CODE = "52311"  # Gewerbeanzeigenstatistik (business registrations)

# Default region: whole of Baden-Württemberg. See config/regions.py for
# the individual Stadtkreise (Stuttgart, Karlsruhe, Freiburg, ...).
REGIONAL_KEY = GERMAN_REGIONS["baden_wurttemberg"].ags_code

START_YEAR = MIN_YEAR
END_YEAR = MAX_YEAR

# WZ 2008 sections map almost 1:1 onto France's NAF sections (both derive
# from the EU's NACE Rev. 2) — reuse the shared mapping so French and
# German charts use identical sector labels.
WZ_SECTION_LABELS = NAF_WZ_SECTION_LABELS


def _auth_params(extra: dict) -> dict:
    if not RGDB_USERNAME or not RGDB_PASSWORD:
        raise RuntimeError(
            "Credentials not set. Run bw.set_credentials() first "
            "(or bw.set_credentials(username=..., password=...))."
        )
    params = {"username": RGDB_USERNAME, "password": RGDB_PASSWORD}
    params.update(extra)
    return params


# ---------------------------------------------------------------------------
# Step A — find candidate tables for the Gewerbeanzeigenstatistik
# ---------------------------------------------------------------------------

def search_tables_for_statistic(statistic_code: str = STATISTIC_CODE):
    """
    List all GENESIS tables belonging to a given statistic (EVAS code).
    Run this first and look for a table whose description mentions
    "Kreise" (district level) and "Wirtschaftsabschnitte" (WZ sections) —
    that's the one you want for year x sector x district data.
    """
    url = BASE_URL + "catalogue/tables2statistic"
    params = _auth_params({
        "selection": statistic_code,
        "pagelength": 100,
        "language": "de",
    })
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    tables = payload.get("List", [])
    print(f"Found {len(tables)} tables for statistic {statistic_code}:\n")
    for t in tables:
        code = t.get("Code", "?")
        content = t.get("Content", "?")
        print(f"  {code:20s} {content}")
    return tables


# ---------------------------------------------------------------------------
# Step B — inspect a specific table's structure before pulling data
# ---------------------------------------------------------------------------

def inspect_table_metadata(table_code: str):
    """
    Fetch metadata for a specific table: which variables it's broken
    down by (region, year, WZ section, etc.) and what values each
    variable can take. Use this to confirm the correct 'regionalvariable'
    name (e.g. 'KREISE') and classifying variable codes before fetching
    the full dataset.
    """
    url = BASE_URL + "metadata/table"
    params = _auth_params({"name": table_code, "language": "de"})
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    print(payload.get("Object", payload))
    return payload


# ---------------------------------------------------------------------------
# Step C — fetch and tidy the actual data
# ---------------------------------------------------------------------------

def fetch_and_parse_table(
    table_code: str,
    regional_key: str = REGIONAL_KEY,
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
) -> pd.DataFrame:
    """
    Download a table in Flat-File-CSV (ffcsv) format and return it as a
    tidy pandas DataFrame. GENESIS returns ffcsv responses zipped, so we
    unzip in-memory before parsing.
    """
    url = BASE_URL + "data/tablefile"
    params = _auth_params({
        "name": table_code,
        "area": "free",
        "format": "ffcsv",
        "compress": "true",
        "startyear": start_year,
        "endyear": end_year,
        "regionalvariable": "KREISE",   # confirm via inspect_table_metadata()
        "regionalkey": regional_key,
        "language": "de",
    })

    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    # GENESIS returns a zip archive containing one CSV file.
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            inner_name = zf.namelist()[0]
            with zf.open(inner_name) as f:
                df = pd.read_csv(f, sep=";", encoding="utf-8-sig")
    except zipfile.BadZipFile:
        # Some configurations return raw (uncompressed) CSV instead.
        df = pd.read_csv(io.StringIO(response.text), sep=";")

    print("Columns returned by the API:")
    print(list(df.columns))
    print("\nFirst few rows:")
    print(df.head())

    return df


def tidy_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Reduce the raw ffcsv table to a tidy (year, sector, count) DataFrame.

    NOTE: ffcsv column names vary slightly by table. Common patterns are
    'Zeit' / 'Zeit_Label' for the year, one or more '<n>_Merkmal_Label' /
    '<n>_Auspraegung_Label' columns for classifying variables (like WZ
    section or registration reason), and 'Wert' for the value. Adjust the
    column names below (YEAR_COL, SECTOR_COL, VALUE_COL) to match what
    fetch_and_parse_table() printed for your specific table.
    """
    YEAR_COL = "Zeit"                     # <-- confirm/adjust
    SECTOR_COL = "1_Auspraegung_Label"    # <-- confirm/adjust
    VALUE_COL = "Wert"                    # <-- confirm/adjust

    missing = [c for c in (YEAR_COL, SECTOR_COL, VALUE_COL) if c not in df_raw.columns]
    if missing:
        raise KeyError(
            f"Expected column(s) {missing} not found. "
            f"Available columns: {list(df_raw.columns)}. "
            "Update YEAR_COL/SECTOR_COL/VALUE_COL in tidy_dataframe()."
        )

    df = df_raw[[YEAR_COL, SECTOR_COL, VALUE_COL]].copy()
    df.columns = ["year", "sector", "count"]
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
    df = df.dropna(subset=["year", "count"])
    df["year"] = df["year"].astype(int)

    return df.sort_values(["year", "sector"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Charts (same visual style as france_creations.py, for side-by-side use)
# ---------------------------------------------------------------------------

def plot_yearly_trend(df: pd.DataFrame, output_path: str = "outputs/charts/bw_registrations_trend.png"):
    yearly_totals = df.groupby("year")["count"].sum()

    fig, ax = new_figure()
    ax.bar(yearly_totals.index.astype(str), yearly_totals.values, color="#A63A3A")
    ax.set_title("New Business Registrations in Baden-Württemberg per Year", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of new registrations")
    for i, v in enumerate(yearly_totals.values):
        ax.text(i, v, str(int(v)), ha="center", va="bottom", fontsize=9)
    save(fig, output_path)


def plot_stacked_bar(df: pd.DataFrame, output_path: str = "outputs/charts/bw_registrations_by_sector.png"):
    pivot = df.pivot_table(index="year", columns="sector", values="count", aggfunc="sum", fill_value=0)
    pivot = pivot[pivot.sum().sort_values(ascending=False).index]

    fig, ax = new_figure()
    pivot.plot(kind="bar", stacked=True, ax=ax, colormap="tab20", width=0.8)
    ax.set_title("New Business Registrations in Baden-Württemberg by Year and Sector", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of new registrations")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8, title="WZ sector")
    save(fig, output_path)


def plot_sector_totals(df: pd.DataFrame, output_path: str = "outputs/charts/bw_registrations_by_sector_total.png"):
    sector_totals = df.groupby("sector")["count"].sum().sort_values(ascending=True)

    fig, ax = new_figure()
    ax.barh(sector_totals.index, sector_totals.values, color="#A63A3A")
    ax.set_title("Total Business Registrations in Baden-Württemberg by Sector (All Years)", fontsize=15, pad=12)
    ax.set_xlabel("Number of new registrations")
    save(fig, output_path)


# ---------------------------------------------------------------------------
# Convenience: run steps B+C+charts together once you know the table code
# ---------------------------------------------------------------------------

def run_all(table_code: str, regional_key: str = REGIONAL_KEY):
    """
    Once you've identified the right table code (via search_tables_for_statistic
    + inspect_table_metadata) and confirmed the column names tidy_dataframe()
    expects, call this to fetch, tidy, save, and chart everything in one go.

        bw.run_all("52311-XX-XX-X")
    """
    print("Inspecting table metadata...")
    inspect_table_metadata(table_code)

    print("\nFetching and tidying data...")
    df_raw = fetch_and_parse_table(table_code, regional_key=regional_key)
    df = tidy_dataframe(df_raw)

    csv_path = "data/processed/bw_registrations_by_year_sector.csv"
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"Tidy data saved to: {csv_path}")

    print("\nGenerating chart images...")
    plot_yearly_trend(df)
    plot_stacked_bar(df)
    plot_sector_totals(df)
    print("\nAll charts saved — ready to insert into PowerPoint.")

    return df
