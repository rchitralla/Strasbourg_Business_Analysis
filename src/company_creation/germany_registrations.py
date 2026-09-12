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

    # 3. Step B — CONFIRMED live: TABLE_CODE_LAND ("52311-01-04-4-B") lets
    #    you select the Bundesländer level directly (Baden-Württemberg as
    #    one row — no manual Kreis-summing needed). There is NO sector/WZ
    #    variable on this statistic at all — only a registration-REASON
    #    variable (GEWNW1). Inspect the table's structure to confirm the
    #    exact ffcsv column names before trusting tidy_dataframe()'s
    #    guesses:
    bw.inspect_table_metadata(bw.TABLE_CODE_LAND)

    # 4. Step C — fetch, tidy (filters to genuine new creations by
    #    default), and chart it:
    df_raw = bw.fetch_and_parse_table(bw.TABLE_CODE_LAND)
    df = bw.tidy_dataframe(df_raw)   # adjust YEAR_COL/REASON_COL/VALUE_COL
                                       # inside this function if needed —
                                       # check the printed columns from
                                       # fetch_and_parse_table() first
    bw.plot_yearly_trend(df)

    # To chart the reason breakdown itself (Neuerrichtungen vs. Zuzüge
    # vs. sonstige Anmeldung) instead of just the filtered total:
    df_by_reason = bw.tidy_dataframe(df_raw, filter_to_neuerrichtungen=False)
    bw.plot_stacked_bar(df_by_reason)
    bw.plot_reason_totals(df_by_reason)

Nothing runs automatically on import — every step above is a separate
function call, so you can inspect output at each stage before moving on.

IMPORTANT CONTEXT:
-------------------
1. Free registration required at https://www.regionalstatistik.de/genesis/online

2. The relevant statistic is EVAS 52311 "Gewerbeanzeigenstatistik"
   (trade/business registration statistics).

   CONFIRMED live (2026-09-12) — the classifying variable for
   registration REASON is GEWNW1 ("Grund der Gewerbeanmeldung"), with
   three values:
     - GEWM0 = Neuerrichtungen  -> genuine new business creations
                                   (closest match to INSEE's "créations
                                   d'entreprises" — but per the official
                                   definition text this ALSO includes
                                   foundings via legal transformation
                                   under the Umwandlungsgesetz, so it is
                                   not a perfectly pure "brand-new
                                   company" count either)
     - GEWM1 = Zuzüge           -> relocation of an existing business
                                   into the area
     - GEWM2 = sonstige Anmeldung -> other registrations (incl. takeovers)
   For a fair comparison with the French data, filter to GEWM0
   ("Neuerrichtungen") specifically — see tidy_dataframe()'s
   filter_to_neuerrichtungen parameter.

   CONFIRMED live: there is NO Wirtschaftsabschnitt/WZ (economic sector)
   classifying variable anywhere on this statistic — the full Merkmale
   list is DINSG/DLAND/REGBEZ/KREISE (spatial), JAHR (time),
   GEW001-GEW013 (registration/deregistration count measures), and
   GEWNW1-GEWNW6 (registration/deregistration REASON, not sector). This
   is a real, permanent methodological gap, not a bug to fix: at this
   granularity Destatis does not publish a sector breakdown for business
   registrations, likely due to small-cell disclosure suppression at
   Kreis level. The German side of any "creations BY SECTOR" comparison
   cannot be built from this statistic — only a total (optionally
   Neuerrichtungen-only) count per region per year is available. Document
   this explicitly wherever a French-vs-German sector chart is shown:
   the French side has a sector split, the German side structurally does
   not at this granularity.

   Two tables exist under this statistic, confirmed live:
     - 52311-01-04-4   ("regionale Tiefe: Kreise und krfr. Städte") —
       Kreis (district) level only. Baden-Württemberg the STATE is not
       itself a Kreis, so getting a Baden-Württemberg total from this
       table means fetching every Kreis in BW (AGS codes starting "08")
       and summing them yourself.
     - 52311-01-04-4-B ("regionale Ebenen") — CONFIRMED live: its
       regional-level dropdown offers Deutschland (1) / Bundesländer
       (16) / Regierungsbezirke (44) / Kreise und kreisfreie Städte
       (490) as interchangeable levels for the SAME table. Selecting
       Bundesländer gives Baden-Württemberg directly as ONE row — no
       manual Kreis summing needed. THIS IS THE TABLE TO USE for the
       headline BW-vs-France comparison (TABLE_CODE_LAND /
       REGIONALVARIABLE_LAND="DLAND", both confirmed).

3. Structural difference from France: Germany's Gewerbeanzeigen statistic
   does NOT cover "Freiberufler" (liberal professions — doctors, lawyers,
   architects, consultants, etc.) or agriculture/forestry, since these
   aren't required to register a "Gewerbe". France's Sirene-based creation
   stats DO include these. Keep this in mind when comparing absolute
   totals between the French departments and a Baden-Württemberg Kreis —
   document this caveat wherever the comparison is shown (see
   docs/DATA_SOURCES.md).

4. The exact ffcsv column names returned by fetch_and_parse_table() are
   still NOT confirmed against a live response — double-check the
   printed columns at each step before trusting tidy_dataframe()'s
   column-name guesses (YEAR_COL/REASON_COL/VALUE_COL).

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

# CONFIRMED live (2026-09-12) — two tables exist for this statistic:
#   TABLE_CODE_KREISE: Kreis (district) level only. Baden-Württemberg
#     the STATE is not itself a Kreis, so a BW total from this table
#     means summing every Kreis whose AGS code starts "08" yourself.
#     Use this one for a within-BW district drilldown (e.g. isolating
#     border-adjacent Kreise like Ortenau/Breisgau near Alsace).
#   TABLE_CODE_LAND: "regionale Ebenen" — its regional dropdown was
#     confirmed to offer Deutschland (1) / Bundesländer (16) /
#     Regierungsbezirke (44) / Kreise und kreisfreie Städte (490) as
#     interchangeable levels for the SAME table. Selecting Bundesländer
#     gives Baden-Württemberg directly as ONE row — no manual Kreis
#     summing needed. This is the one to use for the headline BW-vs-
#     France comparison.
TABLE_CODE_KREISE = "52311-01-04-4"
TABLE_CODE_LAND = "52311-01-04-4-B"

# CONFIRMED live: the Merkmal code for the Bundesländer regional level
# (matches the dropdown option "Bundesländer (16)" on TABLE_CODE_LAND).
REGIONALVARIABLE_LAND = "DLAND"
REGIONALVARIABLE_KREISE = "KREISE"

# CONFIRMED live: the classifying variable for registration REASON (not
# sector — no sector variable exists on this statistic, see module
# docstring). GEWM0 is the "genuine new creation" category to filter to
# for a fair comparison with the French Sirene data. NOTE: TABLE_CODE_LAND
# also separately offers GEWNW3 ("Neuerrichtungen", a simpler 2-valued
# Ja/Nein split) as an alternative to text-matching GEWNW1's 3-way
# label — potentially cleaner to filter on once its exact values are
# confirmed (not yet checked).
REASON_VARIABLE = "GEWNW1"
REASON_NEUERRICHTUNGEN = "GEWM0"   # genuine new creations
REASON_ZUZUEGE = "GEWM1"           # relocations
REASON_SONSTIGE = "GEWM2"          # other (incl. takeovers)

# Default region: whole of Baden-Württemberg. See config/regions.py for
# the individual Stadtkreise (Stuttgart, Karlsruhe, Freiburg, ...).
REGIONAL_KEY = GERMAN_REGIONS["baden_wurttemberg"].ags_code

START_YEAR = MIN_YEAR
END_YEAR = MAX_YEAR


def _auth_headers() -> dict:
    if not RGDB_USERNAME or not RGDB_PASSWORD:
        raise RuntimeError(
            "Credentials not set. Run bw.set_credentials() first "
            "(or bw.set_credentials(username=..., password=...))."
        )
    return {"username": RGDB_USERNAME, "password": RGDB_PASSWORD}


def _post(path: str, data: dict, timeout: int = 30):
    """
    CONFIRMED live (2026-09-12, via the GENESIS-Online Swagger UI at
    regionalstatistik.de/genesisws/swagger-ui): every REST endpoint this
    module uses (catalogue/*, metadata/*, data/*) is POST-only, with
    username/password sent as HTTP HEADERS — NOT as URL query
    parameters (the earlier GET-based version put credentials directly
    in the URL, which is both why it 405'd and a real credential-
    exposure risk via server/proxy access logs) — and every other
    parameter (table name, language, year range, etc.) as an
    application/x-www-form-urlencoded POST body.
    """
    url = BASE_URL + path
    return requests.post(url, headers=_auth_headers(), data=data, timeout=timeout)


# ---------------------------------------------------------------------------
# Step A — find candidate tables for the Gewerbeanzeigenstatistik
# ---------------------------------------------------------------------------

def search_tables_for_statistic(statistic_code: str = STATISTIC_CODE):
    """
    List all GENESIS tables belonging to a given statistic (EVAS code).
    For 52311 this returns TABLE_CODE_KREISE (Kreis-level only) and
    TABLE_CODE_LAND ("regionale Ebenen" — supports Bundesländer level
    too, confirmed live) — see module docstring for which to use when.
    There is NO sector/WZ variable on this statistic at any level.
    """
    response = _post("catalogue/tables2statistic", {
        "selection": statistic_code,
        "pagelength": 100,
        "language": "de",
    })
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
    response = _post("metadata/table", {"name": table_code, "language": "de"})
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
    regionalvariable: str = REGIONALVARIABLE_LAND,
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
) -> pd.DataFrame:
    """
    Download a table in Flat-File-CSV (ffcsv) format and return it as a
    tidy pandas DataFrame. GENESIS returns ffcsv responses zipped, so we
    unzip in-memory before parsing.

    regionalvariable defaults to REGIONALVARIABLE_LAND ("DLAND" —
    Bundesländer level, confirmed live to work on TABLE_CODE_LAND) so
    regional_key (Baden-Württemberg's AGS code) resolves directly to one
    row. Pass regionalvariable=REGIONALVARIABLE_KREISE (with
    table_code=TABLE_CODE_KREISE and a specific Kreis's AGS code as
    regional_key) instead for a within-BW district drilldown.
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


def tidy_dataframe(df_raw: pd.DataFrame, filter_to_neuerrichtungen: bool = True) -> pd.DataFrame:
    """
    Reduce the raw ffcsv table to a tidy (year, reason, count) DataFrame
    — NOTE: "reason" (registration reason: Neuerrichtungen/Zuzüge/
    sonstige Anmeldung), NOT sector. This statistic has NO sector/WZ
    classifying variable at all (confirmed live 2026-09-12 — see module
    docstring) — an earlier version of this function assumed one existed
    and called this column "sector", which was wrong.

    filter_to_neuerrichtungen=True (default) additionally restricts the
    result to REASON_NEUERRICHTUNGEN only (genuine new creations, the
    fair comparison point with French Sirene data) and drops the
    now-redundant "reason" column. Pass False to keep all three reason
    categories broken out, e.g. to chart Neuerrichtungen vs. Zuzüge vs.
    sonstige Anmeldung directly.

    CONFIRMED live (2026-09-12) — the real ffcsv column names for
    TABLE_CODE_LAND are a "long" format, quite different from earlier
    guesses:
      time                        -> the year (e.g. 2024)
      1_variable_code/_label      -> the regional variable's NAME (e.g.
                                      "DLAND"/"Bundesländer")
      1_variable_attribute_label  -> the regional variable's VALUE for
                                      this row (e.g. "Baden-Württemberg")
      2_variable_code/_label      -> the classifying variable's NAME —
                                      CONFIRMED to be GEWNW5 ("Grund der
                                      Gewerbeanmeldung") by default, NOT
                                      GEWNW1 as originally assumed
      2_variable_attribute_label  -> the classifying variable's VALUE
                                      (e.g. "Zuzüge", "sonstige Anmeldung")
      value                       -> the count
      value_variable_code/_label  -> which measure this is (e.g. "GEW011")

    IMPORTANT: GEWNW5 (the classifying variable this table actually
    returns) may have only 2 categories per the live table-builder UI —
    possibly Zuzüge/sonstige Anmeldung WITHOUT a "Neuerrichtungen" value
    of its own (that may live under the separate GEWNW3 variable
    instead, seen as a sibling in inspect_table_metadata()'s output).
    If so, filter_to_neuerrichtungen can't work by direct text-matching
    here — Neuerrichtungen would need to be derived by SUBTRACTION
    (unclassified GEW011 total minus the GEWNW5 categories) instead.
    Check df_raw["2_variable_attribute_label"].unique() before trusting
    the filter below.
    """
    YEAR_COL = "time"
    REGION_COL = "1_variable_attribute_label"
    REASON_COL = "2_variable_attribute_label"
    VALUE_COL = "value"

    missing = [c for c in (YEAR_COL, REGION_COL, REASON_COL, VALUE_COL) if c not in df_raw.columns]
    if missing:
        raise KeyError(
            f"Expected column(s) {missing} not found. "
            f"Available columns: {list(df_raw.columns)}. "
            "Update YEAR_COL/REGION_COL/REASON_COL/VALUE_COL in tidy_dataframe()."
        )

    df = df_raw[[YEAR_COL, REGION_COL, REASON_COL, VALUE_COL]].copy()
    df.columns = ["year", "region", "reason", "count"]
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
    df = df.dropna(subset=["year", "count"])
    df["year"] = df["year"].astype(int)
    df = df.sort_values(["year", "region", "reason"]).reset_index(drop=True)

    if not filter_to_neuerrichtungen:
        return df

    # CONFIRMED live (2026-09-12): TABLE_CODE_LAND's default classifying
    # variable is GEWNW5, whose own categories may NOT include
    # "Neuerrichtungen" at all (it looked like a 2-value split — Zuzüge/
    # sonstige Anmeldung — with Neuerrichtungen tracked separately under
    # the sibling variable GEWNW3 instead, per inspect_table_metadata()).
    # If so, this text match will correctly find nothing — that is
    # informative, not a bug — and Neuerrichtungen needs to be derived
    # by SUBTRACTION (unclassified GEW011 total minus these categories)
    # rather than filtered directly. Check the warning below's printed
    # distinct values before concluding this is broken vs. expected.
    matches = df["reason"].str.contains("Neuerrichtung", case=False, na=False)
    if not matches.any():
        print(f"WARNING: no 'reason' value containing 'Neuerrichtung' found — "
              f"filter_to_neuerrichtungen returned nothing. Distinct reason "
              f"values seen: {sorted(df['reason'].unique())}. Adjust the match "
              f"string in tidy_dataframe() or pass filter_to_neuerrichtungen=False.")
        return df[matches]

    return df[matches].drop(columns=["reason"]).reset_index(drop=True)


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


def plot_stacked_bar(df: pd.DataFrame, output_path: str = "outputs/charts/bw_registrations_by_reason.png"):
    """
    Requires df from tidy_dataframe(filter_to_neuerrichtungen=False) —
    i.e. a "reason" column (Neuerrichtungen/Zuzüge/sonstige Anmeldung),
    NOT a sector breakdown. This statistic has no sector variable at all
    (see module docstring) — an earlier version of this function
    expected a "sector" column, which never existed in the real data.
    """
    pivot = df.pivot_table(index="year", columns="reason", values="count", aggfunc="sum", fill_value=0)
    pivot = pivot[pivot.sum().sort_values(ascending=False).index]

    fig, ax = new_figure()
    pivot.plot(kind="bar", stacked=True, ax=ax, colormap="tab20", width=0.8)
    ax.set_title("Business Registrations in Baden-Württemberg by Year and Reason", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of registrations")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8, title="Grund der Anmeldung")
    save(fig, output_path)


def plot_reason_totals(df: pd.DataFrame, output_path: str = "outputs/charts/bw_registrations_by_reason_total.png"):
    """Requires a "reason" column — see plot_stacked_bar()'s docstring."""
    reason_totals = df.groupby("reason")["count"].sum().sort_values(ascending=True)

    fig, ax = new_figure()
    ax.barh(reason_totals.index, reason_totals.values, color="#A63A3A")
    ax.set_title("Total Business Registrations in Baden-Württemberg by Reason (All Years)", fontsize=15, pad=12)
    ax.set_xlabel("Number of registrations")
    save(fig, output_path)


# ---------------------------------------------------------------------------
# Convenience: run steps B+C+charts together once you know the table code
# ---------------------------------------------------------------------------

def run_all(table_code: str = TABLE_CODE_LAND, regional_key: str = REGIONAL_KEY,
            regionalvariable: str = REGIONALVARIABLE_LAND):
    """
    Once you've confirmed the column names tidy_dataframe() expects
    (via inspect_table_metadata() + a first fetch_and_parse_table()
    call), run this to fetch, tidy, save, and chart everything in one
    go. Defaults to TABLE_CODE_LAND at the Bundesländer level — gives
    Baden-Württemberg as one row directly (confirmed live). Pass
    table_code=TABLE_CODE_KREISE, regionalvariable=REGIONALVARIABLE_KREISE,
    and a specific Kreis's AGS code instead for a within-BW district
    drilldown.

        bw.run_all()
    """
    print("Inspecting table metadata...")
    inspect_table_metadata(table_code)

    print("\nFetching and tidying data...")
    df_raw = fetch_and_parse_table(table_code, regional_key=regional_key, regionalvariable=regionalvariable)
    df = tidy_dataframe(df_raw)  # filtered to genuine new creations (Neuerrichtungen) by default
    df_by_reason = tidy_dataframe(df_raw, filter_to_neuerrichtungen=False)

    csv_path = "data/processed/bw_registrations_by_year.csv"
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"Tidy data saved to: {csv_path}")

    print("\nGenerating chart images...")
    plot_yearly_trend(df)
    plot_stacked_bar(df_by_reason)
    plot_reason_totals(df_by_reason)
    print("\nAll charts saved — ready to insert into PowerPoint.")

    return df
