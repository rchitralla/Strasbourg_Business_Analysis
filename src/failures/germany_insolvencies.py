"""
Baden-Württemberg Corporate Insolvencies (Data Room question B9, German side)
================================================================================

German counterpart to src/failures/bodacc_failures.py (France's BODACC
"Procédures collectives" axis) — statistic 52411 ("Statistik über
beantragte Insolvenzverfahren"), table 52411-02-01-4-B specifically
covers BUSINESS insolvency applications ("Beantragte
Unternehmensinsolvenzen"), separate from personal/consumer insolvencies.

CONFIRMED live (2026-09-14), via inspect_table_metadata() and a real
fetch_and_parse_table() call:
    Measure ISV006 ("Beantragte Insolvenzverfahren (Unternehmen)") is
    the business insolvency APPLICATION count, with a real classifying
    sub-variable ISVAT3 ("Beantragte Verfahren") splitting it into:
      ISVART01 = "eröffnet"                  -> proceeding OPENED
      ISVART02 = "mangels Masse abgewiesen"  -> REJECTED (insufficient
                                                 assets to cover costs)
      (blank/NaN attribute code) = "Insgesamt" -> grand total
    Confirmed live: eröffnet + mangels Masse abgewiesen = Insgesamt
    EXACTLY for 2023 BW (1324 + 551 = 1875) — a genuine, disjoint,
    exhaustive 2-category partition matching German insolvency law
    (every application is either opened or rejected for lack of
    assets — there is no third outcome at this stage). Unlike the
    GEWNW3/GEWNW5 risk in germany_registrations.py, summing both
    categories here does NOT double-count.

    For a fair comparison with France's bodacc_failures.py (which
    filters to "opening judgment" specifically, excluding conversions/
    plans per the Data Room brief's own caveat), this module defaults
    to ISVART01 ("eröffnet") only — a rejected application never
    became an actual insolvency proceeding, so it isn't the same kind
    of "failure" event as a French opening judgment.

    Two other measures also live on this table (not wired up here):
    ISVNW1 (Arbeitnehmer/-innen — employees affected) and FOR002
    (voraussichtliche Forderungen — expected claims, in Tsd. EUR) —
    potential bonus metrics for later.

    Data only covers 2015-2024 (confirmed live: no 2025/2026 rows exist
    yet) — narrower than the French BODACC failures axis at the recent
    end; caption this explicitly on any comparison chart.

Usage (DESIGNED FOR JUPYTER, same pattern as germany_registrations.py):
    from src.company_creation import germany_registrations as bw
    from src.failures import germany_insolvencies as gi_fail

    bw.set_credentials()   # shared credential store — set once, used by
                            # every germany_* module in this project

    df, df_raw = gi_fail.run_all()
"""

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.regions import GERMAN_REGIONS
from src.common.plotting import new_figure, save, PRIMARY_COLOR

# Reuses germany_registrations' shared GENESIS HTTP client (credentials +
# POST/auth-header plumbing) instead of duplicating it.
from src.company_creation.germany_registrations import _post, inspect_table_metadata

STATISTIC_CODE = "52411"        # Statistik über beantragte Insolvenzverfahren
TABLE_CODE = "52411-02-01-4-B"  # Beantragte Unternehmensinsolvenzen - regionale Ebenen

REGIONALVARIABLE_LAND = "DLAND"
REGIONAL_KEY = GERMAN_REGIONS["baden_wurttemberg"].ags_code

MEASURE_COUNT = "ISV006"      # Beantragte Insolvenzverfahren (Unternehmen) — the count we want
MEASURE_EMPLOYEES = "ISVNW1"  # Arbeitnehmer/-innen — not wired up yet
MEASURE_CLAIMS = "FOR002"     # voraussichtliche Forderungen — not wired up yet

CATEGORY_OPENED = "ISVART01"      # eröffnet — proceeding opened
CATEGORY_REJECTED = "ISVART02"    # mangels Masse abgewiesen — rejected, insufficient assets

# CONFIRMED live: this table's actual coverage — no 2025/2026 data yet.
START_YEAR = 2015
END_YEAR = 2024


def fetch_and_parse_table(
    table_code: str = TABLE_CODE,
    regional_key: str = REGIONAL_KEY,
    regionalvariable: str = REGIONALVARIABLE_LAND,
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
) -> pd.DataFrame:
    """Same ffcsv fetch/unzip logic as germany_registrations.fetch_and_parse_table, via the shared _post() HTTP client."""
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


def tidy_dataframe(df_raw: pd.DataFrame, filter_to_opened: bool = True) -> pd.DataFrame:
    """
    Reduce the raw ffcsv table to a tidy (year, region, count) DataFrame
    of business insolvency counts.

    filter_to_opened=True (default) restricts to ISVART01 ("eröffnet" —
    proceeding actually opened), the fair comparison point with
    France's bodacc_failures.py (which filters to opening judgments
    only). Pass False to get BOTH categories (eröffnet + mangels Masse
    abgewiesen) as a "category" breakdown instead — confirmed live
    these two sum EXACTLY to the table's own Insgesamt total for 2023
    BW, so summing both together does NOT double-count.
    """
    YEAR_COL = "time"
    REGION_COL = "1_variable_attribute_label"
    CATEGORY_CODE_COL = "2_variable_attribute_code"
    CATEGORY_LABEL_COL = "2_variable_attribute_label"
    MEASURE_COL = "value_variable_code"
    VALUE_COL = "value"

    missing = [c for c in (YEAR_COL, REGION_COL, CATEGORY_CODE_COL, CATEGORY_LABEL_COL, MEASURE_COL, VALUE_COL)
               if c not in df_raw.columns]
    if missing:
        raise KeyError(
            f"Expected column(s) {missing} not found. "
            f"Available columns: {list(df_raw.columns)}. "
            "Update the *_COL constants in tidy_dataframe() to match."
        )

    df = df_raw[df_raw[MEASURE_COL] == MEASURE_COUNT].copy()
    if df.empty:
        print(f"WARNING: no rows matched measure={MEASURE_COUNT!r} — nothing to tidy. "
              f"Distinct measures seen: {sorted(df_raw[MEASURE_COL].unique())}.")
        return df

    # CONFIRMED live (2026-09-14): drop the Insgesamt row (blank category
    # code) — it's the exact sum of the two real categories, not a
    # category of its own. Used below only as a cross-check.
    total_rows = df[df[CATEGORY_CODE_COL].isna()]
    df = df[df[CATEGORY_CODE_COL].notna()].copy()

    df = df[[YEAR_COL, REGION_COL, CATEGORY_CODE_COL, CATEGORY_LABEL_COL, VALUE_COL]].copy()
    df.columns = ["year", "region", "category_code", "category", "count"]
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
    df = df.dropna(subset=["year", "count"])
    df["year"] = df["year"].astype(int)

    if not total_rows.empty:
        summed_by_year = df.groupby("year")["count"].sum()
        for _, row in total_rows.iterrows():
            year_val = pd.to_numeric(row[YEAR_COL], errors="coerce")
            if pd.isna(year_val):
                continue
            year_val = int(year_val)
            reported_total = row[VALUE_COL]
            summed = summed_by_year.get(year_val, 0)
            status = "OK" if abs(summed - reported_total) <= 1 else "MISMATCH"
            print(f"Cross-check {year_val}: eröffnet + mangels Masse abgewiesen = {summed:.0f}, "
                  f"GENESIS-reported Insgesamt = {reported_total:.0f} -> {status}")

    if not filter_to_opened:
        return df.drop(columns=["category_code"]).sort_values(["year", "region", "category"]).reset_index(drop=True)

    matches = df["category_code"] == CATEGORY_OPENED
    if not matches.any():
        print(f"WARNING: no row with category_code == {CATEGORY_OPENED!r} ('eröffnet') found — "
              f"filter_to_opened returned nothing. Distinct category codes seen: "
              f"{sorted(df['category_code'].unique())}.")
        return df[matches]

    return df[matches].drop(columns=["category_code", "category"]).reset_index(drop=True)


def plot_yearly_trend(df: pd.DataFrame, output_path: str = "outputs/charts/bw_insolvencies_trend.png"):
    yearly_totals = df.groupby("year")["count"].sum()
    fig, ax = new_figure()
    ax.bar(yearly_totals.index.astype(str), yearly_totals.values, color=PRIMARY_COLOR)
    ax.set_title("Business Insolvency Proceedings Opened in Baden-Württemberg per Year", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of proceedings opened")
    for i, v in enumerate(yearly_totals.values):
        ax.text(i, v, str(int(v)), ha="center", va="bottom", fontsize=9)
    save(fig, output_path)


def plot_france_germany_comparison(
    france_df: pd.DataFrame,
    bw_csv_path: str = "data/processed/bw_insolvencies_by_year.csv",
    output_path: str = "outputs/charts/fr_de_insolvency_comparison.png",
) -> pd.DataFrame:
    """
    Indexed (starting year = 100) trend comparison: French BODACC
    opening-judgment failures vs Baden-Württemberg business insolvencies
    opened, both per year.

    RAW COUNTS ARE NOT COMPARABLE DIRECTLY -- Baden-Württemberg's
    population (~11.15M) dwarfs the three French departments combined
    (~1.1M), so an un-indexed chart would just show "Germany has a
    bigger number," not "did the two countries' failure trends move
    differently." Indexing both series to their own first shared year
    answers the actually interesting question -- same technique used by
    sirene_v3_client.plot_department_share_of_national() for the
    analogous department-vs-national scale mismatch earlier in this
    project.

    france_df: bodacc_failures.collect_all_departments()'s output (or
    any subset -- pass all 3 departments together for the full
    Alsace-Moselle comparison). Opening-classified notices only are
    summed by year, matching this module's own default filter
    (filter_to_opened=True) so both sides count the same KIND of event
    (a genuine new failure, not a conversion/plan/closure).

    bw_csv_path: this module's own tidy CSV (run_all() or
    tidy_dataframe()+to_csv already produces it).

    Only years present in BOTH series are compared -- Germany's table
    has no 2025/2026 data yet, so those French years are dropped with a
    printed note rather than silently misaligning the two series.
    """
    from src.common.plotting import PRIMARY_COLOR, SECONDARY_COLOR, new_figure, save

    bw = pd.read_csv(bw_csv_path)
    bw_yearly = bw.groupby("year")["count"].sum()

    fr_opening = france_df[france_df["nature_classification"] == "opening"]
    fr_yearly = fr_opening.groupby("year").size()

    common_years = sorted(set(bw_yearly.index) & set(fr_yearly.index))
    if not common_years:
        raise ValueError("No overlapping years between the French and German series -- "
                          "check both inputs cover a shared date range.")

    dropped_fr = sorted(set(fr_yearly.index) - set(common_years))
    dropped_de = sorted(set(bw_yearly.index) - set(common_years))
    if dropped_fr or dropped_de:
        print(f"NOTE: comparing only the overlapping window {common_years[0]}-{common_years[-1]}. "
              f"Dropped from France (outside Germany's coverage): {dropped_fr}. "
              f"Dropped from Germany: {dropped_de}.")

    fr_series = fr_yearly.loc[common_years]
    bw_series = bw_yearly.loc[common_years]
    fr_indexed = fr_series / fr_series.iloc[0] * 100
    bw_indexed = bw_series / bw_series.iloc[0] * 100

    fig, ax = new_figure()
    ax.plot(common_years, fr_indexed.values, marker="o", linewidth=2, color=PRIMARY_COLOR,
            label="France (Bas-Rhin + Haut-Rhin + Moselle, opening judgments)")
    ax.plot(common_years, bw_indexed.values, marker="o", linewidth=2, color=SECONDARY_COLOR,
            label="Baden-Württemberg (proceedings opened)")
    ax.axhline(100, color="#cccccc", linewidth=1, linestyle="--")
    ax.set_title(f"Business Failure Trend, Indexed to {common_years[0]} = 100", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel(f"Index ({common_years[0]} = 100)")
    ax.legend(loc="upper left", fontsize=9)
    save(fig, output_path)

    print(f"\nActual counts, {common_years[0]}: France = {fr_series.iloc[0]}, "
          f"Baden-Württemberg = {bw_series.iloc[0]}")
    print(f"Actual counts, {common_years[-1]}: France = {fr_series.iloc[-1]}, "
          f"Baden-Württemberg = {bw_series.iloc[-1]}")

    return pd.DataFrame({
        "year": common_years,
        "france_count": fr_series.values,
        "france_index": fr_indexed.values,
        "bw_count": bw_series.values,
        "bw_index": bw_indexed.values,
    })


def run_all(table_code: str = TABLE_CODE, regional_key: str = REGIONAL_KEY,
            regionalvariable: str = REGIONALVARIABLE_LAND):
    """
    Fetch, tidy, save, and chart Baden-Württemberg business insolvencies
    (opened proceedings only, by default) in one go. Credentials must
    already be set via germany_registrations.set_credentials().

    Returns (df, df_raw).
    """
    print("Inspecting table metadata...")
    inspect_table_metadata(table_code)

    print("\nFetching and tidying data...")
    df_raw = fetch_and_parse_table(table_code, regional_key=regional_key, regionalvariable=regionalvariable)
    df = tidy_dataframe(df_raw)

    csv_path = "data/processed/bw_insolvencies_by_year.csv"
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"Tidy data saved to: {csv_path}")

    print("\nGenerating chart images...")
    plot_yearly_trend(df)
    print("\nAll charts saved — ready to insert into PowerPoint.")
    print("\nNOTE: this table only covers 2015-2024 (no 2025/2026 data "
          "published yet) — caption this window explicitly wherever "
          "this chart is shown alongside the French BODACC failures axis.")

    return df, df_raw
