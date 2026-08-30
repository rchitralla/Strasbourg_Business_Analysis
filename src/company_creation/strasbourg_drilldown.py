"""
Strasbourg (commune-level) drill-down charts.

The Data Room questions compare whole departments, but a single-city
deep dive on Strasbourg itself is a natural companion slide. This reuses
the fetch/tidy logic from france_creations.py at the commune level and
reproduces the three original chart types: yearly trend, sector stack,
and all-time sector totals.

Usage:
    python -m src.company_creation.strasbourg_drilldown
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.regions import STRASBOURG_COMMUNE_CODE
from src.company_creation.france_creations import fetch_companies, build_dataframe
from src.common.plotting import new_figure, save

CSV_PATH = "data/processed/strasbourg_creations_by_year_sector.csv"


def plot_yearly_trend(df, output_path="outputs/charts/strasbourg_creations_trend.png"):
    yearly_totals = df.groupby("year")["count"].sum()
    fig, ax = new_figure()
    ax.bar(yearly_totals.index.astype(str), yearly_totals.values, color="#2E5EAA")
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
    pivot.plot(kind="bar", stacked=True, ax=ax, colormap="tab20", width=0.8)
    ax.set_title("New Company Creations in Strasbourg by Year and Sector", fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of new companies")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8, title="NAF sector")
    save(fig, output_path)


def plot_sector_totals(df, output_path="outputs/charts/strasbourg_creations_by_sector_total.png"):
    sector_totals = df.groupby("sector")["count"].sum().sort_values(ascending=True)
    fig, ax = new_figure()
    ax.barh(sector_totals.index, sector_totals.values, color="#2E5EAA")
    ax.set_title("Total Company Creations in Strasbourg by Sector (All Years)", fontsize=15, pad=12)
    ax.set_xlabel("Number of new companies")
    save(fig, output_path)


def main():
    print("Fetching company records for Strasbourg (commune)...")
    records = fetch_companies(commune_code=STRASBOURG_COMMUNE_CODE)
    df = build_dataframe(records, region_name="Strasbourg")
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
