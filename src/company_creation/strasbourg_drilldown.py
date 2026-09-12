"""
Strasbourg (commune-level) drill-down charts.

The Data Room questions compare whole departments, but a single-city
deep dive on Strasbourg itself is a natural companion slide.

MIGRATED (2026-09-14) from france_creations.py's fetch_companies() (the
older recherche-entreprises.api.gouv.fr wrapper) to sirene_v3_client.py's
fetch_establishments(). Two real problems this fixes, confirmed live:
  1. That wrapper silently truncates at 10,000 results regardless of
     true match count — the exact reason sirene_v3_client.py replaced
     it for department-level fetches in the first place. A live run
     showed Strasbourg's fetch reporting "10000 total" and then failing
     with HTTP 429 partway through at 8,025 — meaning the number was
     both potentially already-truncated AND further cut short, with no
     warning: main() built the dataframe, saved the CSV, and generated
     all three charts anyway. Given Bas-Rhin alone has 170k+ enterprise
     creations over 2015-2026, Strasbourg's true total plausibly
     exceeds 10,000 too.
  2. fetch_companies()/france_creations.build_dataframe() predate the
     établissement-vs-enterprise fix confirmed live in
     sirene_v3_client.py (ENTERPRISE_ONLY_FILTER) — using it here would
     have carried the same ~55-77%-style overcounting into the
     Strasbourg-specific numbers.

fetch_establishments() takes STRASBOURG_COMMUNE_CODE (a 5-digit INSEE
commune code, "67482") as its query prefix exactly the way it already
takes a 2-digit department code — the wildcard match still resolves to
just this one commune, since no other commune shares that 5-digit
prefix. No 10,000 cap, and it returns a `complete` flag that main()
now checks before trusting/caching anything (same discipline as
sirene_v3_client.collect_all_departments()).

Usage:
    python -m src.company_creation.strasbourg_drilldown
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.regions import STRASBOURG_COMMUNE_CODE, MIN_YEAR, MAX_YEAR
from src.company_creation import sirene_v3_client as sv3
from src.common.plotting import new_figure, save, PRIMARY_COLOR, BRAND_COLORMAP

CSV_PATH = "data/processed/strasbourg_creations_by_year_sector.csv"


def plot_yearly_trend(df, output_path="outputs/charts/strasbourg_creations_trend.png"):
    yearly_totals = df.groupby("year")["count"].sum()
    fig, ax = new_figure()
    ax.bar(yearly_totals.index.astype(str), yearly_totals.values, color=PRIMARY_COLOR)
    ax.set_title("Total New Company Creations in Strasbourg per Year", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of new companies")
    for i, v in enumerate(yearly_totals.values):
        ax.text(i, v, str(int(v)), ha="center", va="bottom", fontsize=9)
    save(fig, output_path)


def plot_stacked_bar(df, output_path="outputs/charts/strasbourg_creations_by_sector.png"):
    pivot = df.pivot_table(index="year", columns="sector", values="count", aggfunc="sum", fill_value=0)
    pivot = pivot[pivot.sum().sort_values(ascending=False).index]
    fig, ax = new_figure()
    pivot.plot(kind="bar", stacked=True, ax=ax, colormap=BRAND_COLORMAP, width=0.8)
    ax.set_title("New Company Creations in Strasbourg by Year and Sector", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of new companies")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8, title="NAF sector")
    save(fig, output_path)


def plot_sector_totals(df, output_path="outputs/charts/strasbourg_creations_by_sector_total.png"):
    sector_totals = df.groupby("sector")["count"].sum().sort_values(ascending=True)
    fig, ax = new_figure()
    ax.barh(sector_totals.index, sector_totals.values, color=PRIMARY_COLOR)
    ax.set_title("Total Company Creations in Strasbourg by Sector (All Years)", fontsize=15, pad=12)
    ax.set_xlabel("Number of new companies")
    save(fig, output_path)


def main(min_year: int = MIN_YEAR, max_year: int = MAX_YEAR):
    """Requires sv3.set_api_key() to have been called first (same session-wide key as the rest of sirene_v3_client.py)."""
    print("Fetching enterprise creations for Strasbourg (commune)...")
    records, complete = sv3.fetch_establishments(STRASBOURG_COMMUNE_CODE, min_year=min_year, max_year=max_year)
    if not complete:
        print(f"\nWARNING: fetch was INCOMPLETE ({len(records)} record(s) retrieved before "
              f"stopping — network failure or rate limit after retries). NOT saving or "
              f"charting this — re-run main() to retry rather than trust a partial count.")
        return

    df = sv3.build_dataframe(records, region_name="Strasbourg")
    if df.empty:
        print("No usable data retrieved.")
        return

    Path(CSV_PATH).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"Tidy data saved to: {CSV_PATH}")

    plot_yearly_trend(df)
    plot_stacked_bar(df)
    plot_sector_totals(df)


if __name__ == "__main__":
    main()
