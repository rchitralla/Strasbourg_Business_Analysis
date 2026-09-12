"""
French Company Creations — Data Collection & Visualization
================================================================

Pulls company records for Bas-Rhin, Haut-Rhin and Moselle (and, for the
national-average benchmark, all of France) from the official French
"Recherche d'Entreprises" API (recherche-entreprises.api.gouv.fr), a free,
public, no-API-key-required wrapper around the INSEE Sirene registry. It
aggregates creations by year, department and broad economic sector (NAF
section), which answers Data Room questions B16-B18 (company creations by
sector, sole proprietorships, share of multi-partner companies).

This generalizes the original Strasbourg-only (commune-level) script to
department-level, since the Data Room brief compares whole departments,
not a single city. Strasbourg-specific drill-downs are still available via
fetch_companies(commune_code=STRASBOURG_COMMUNE_CODE).

Requirements:
    pip install requests pandas matplotlib

Usage:
    python -m src.company_creation.france_creations
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.regions import FRENCH_DEPARTMENTS, FRANCE_NATIONAL, MIN_YEAR, MAX_YEAR
from src.common.sectors import NAF_WZ_SECTION_LABELS, SOLE_SHAREHOLDER_FORMS
from src.common.plotting import grouped_region_bar

API_URL = "https://recherche-entreprises.api.gouv.fr/search"
PER_PAGE = 25                # API max per page
REQUEST_DELAY_SECONDS = 0.3  # be polite to the free public API

CSV_PATH = "data/processed/france_creations_by_year_dept_sector.csv"


def fetch_companies(commune_code: str = None, departement_code: str = None) -> list[dict]:
    """
    Fetch all company records for a given commune or department code,
    walking through every page of results returned by the API. Pass
    exactly one of commune_code / departement_code.
    """
    if not (bool(commune_code) ^ bool(departement_code)):
        raise ValueError("Pass exactly one of commune_code or departement_code")

    all_results = []
    page = 1

    while True:
        params = {"per_page": PER_PAGE, "page": page}
        if commune_code:
            params["code_commune"] = commune_code
        else:
            params["departement"] = departement_code

        response = requests.get(API_URL, params=params, timeout=30)

        if response.status_code != 200:
            print(f"Request failed on page {page}: HTTP {response.status_code}")
            print(response.text[:500])
            break

        payload = response.json()
        results = payload.get("results", [])
        all_results.extend(results)

        total_results = payload.get("total_results", 0)
        print(f"  Fetched page {page} — {len(results)} records "
              f"({len(all_results)}/{total_results} total)")

        if not results or len(all_results) >= total_results:
            break

        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_results


def extract_row(record: dict) -> dict | None:
    """
    Pull creation year, NAF section, legal form (nature_juridique) and
    associate count from a single company record. Returns None if
    essential fields are missing or malformed.

    creation_date prefers the top-level (ENTERPRISE-level) date_creation
    over siege.date_creation — flipped 2026-09-14 after a Sirene v3
    comparison against the official INSEE "créations d'entreprises"
    figure confirmed that counting by the ESTABLISHMENT's own creation
    date overcounts by ~55-77% nationally (branch openings and
    head-office relocations of already-existing enterprises both get a
    fresh établissement-level creation date without the enterprise
    itself being new — see sirene_v3_client.py's ENTERPRISE_ONLY_FILTER
    comment for a real confirmed example record). This API
    (recherche-entreprises.api.gouv.fr) is documented to expose the
    enterprise's own creation date at the top level and the head
    office's establishment-level date under siege — the previous
    ordering here had that backwards. UNVERIFIED against a live
    response from THIS specific API (only the analogous Sirene v3 field
    has been confirmed) — if Strasbourg's creation counts shift
    noticeably after this change, that's this fix taking effect, not a
    new bug.
    """
    siege = record.get("siege", {}) or {}

    creation_date = record.get("date_creation") or siege.get("date_creation")
    if not creation_date:
        return None

    try:
        year = int(creation_date[:4])
    except (ValueError, TypeError):
        return None

    if not (MIN_YEAR <= year <= MAX_YEAR):
        return None

    section_code = (
        siege.get("section_activite_principale")
        or record.get("section_activite_principale")
        or "?"
    )
    sector = NAF_WZ_SECTION_LABELS.get(section_code, "Unknown / unclassified")

    legal_form = record.get("nature_juridique") or "?"

    return {
        "year": year,
        "sector": sector,
        "legal_form": legal_form,
        "is_sole_shareholder": legal_form in SOLE_SHAREHOLDER_FORMS,
    }


def build_dataframe(records: list[dict], region_name: str) -> pd.DataFrame:
    """
    Turn raw API records into a tidy DataFrame: one row per
    (year, region, sector, legal_form) with a count column.
    """
    counts = defaultdict(int)

    for record in records:
        row = extract_row(record)
        if row is None:
            continue
        key = (row["year"], region_name, row["sector"], row["legal_form"])
        counts[key] += 1

    df = pd.DataFrame(
        [(y, r, s, lf, n) for (y, r, s, lf), n in counts.items()],
        columns=["year", "region", "sector", "legal_form", "count"],
    )
    return df.sort_values(["year", "region", "sector"]).reset_index(drop=True)


def collect_all_regions() -> pd.DataFrame:
    """
    Fetch and tidy creations for every French department in scope plus
    the national total, returning one combined DataFrame.
    """
    frames = []
    for dept in list(FRENCH_DEPARTMENTS.values()) + [FRANCE_NATIONAL]:
        print(f"\nFetching company records for {dept.name} (dept code {dept.insee_code})...")
        if dept.insee_code == "FR":
            print("  Skipping full-France pull here — that volume needs the bulk Sirene "
                  "Stock file, not this paginated API. See docs/DATA_SOURCES.md.")
            continue
        records = fetch_companies(departement_code=dept.insee_code)
        print(f"  Total records retrieved: {len(records)}")
        frames.append(build_dataframe(records, dept.name))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    df = collect_all_regions()
    if df.empty:
        print("No usable data retrieved.")
        sys.exit(1)

    Path(CSV_PATH).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"\nTidy data saved to: {CSV_PATH}")

    yearly_by_region = df.groupby(["year", "region"])["count"].sum().reset_index()
    grouped_region_bar(
        yearly_by_region, value_col="count",
        title="New Company Creations by Year and Department",
        ylabel="Number of new companies",
        output_path="outputs/charts/france_creations_by_year_region.png",
    )


if __name__ == "__main__":
    main()
