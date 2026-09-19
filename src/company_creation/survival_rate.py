"""
Cohort survival rate — what share of enterprises created in year Y are
still administratively active today, per French department.

Not an explicit Data Room brief question, but proposed during this
project's own methodology discussion as a cleaner "market saturation"
signal than a churn ratio: it doesn't need the failures axis's opening-
judgment classification to be sorted out first, and it's a more
intuitive story for a non-technical audience ("of the companies that
opened in Strasbourg in 2018, X% are still standing").

WHY THIS NEEDS A SEPARATE FETCH, NOT THE EXISTING CACHED CSVs:
sirene_v3_client.build_dataframe() aggregates raw établissement records
into COUNTS per (year, region, sector, legal_form) and discards the
individual record — including uniteLegale.etatAdministratifUniteLegale
("A"=active, "C"=cessée), which is the one field this module actually
needs. That field was never dropped by INSEE, only by our own
aggregation step. So computing survival means re-fetching each
department via sv3.fetch_establishments() (already uncapped, enterprise-
corrected, retry-safe against 429s — see sirene_v3_client.py) and
extracting status this time, rather than reusing the already-cached
data/processed/*_enterprises.csv files. This roughly doubles the API
cost for whatever year range you choose — pass a narrower min_year/
max_year (e.g. one or two cohort years) for a cheap pilot before
committing to the full 2015-2026 range.

CRITICAL CAVEAT — read before charting this as a trend over years:
"survival as of today" is NOT the same maturity for every cohort. A
2025 cohort has had almost no time to fail, so it will look
artificially healthier than a 2016 cohort that's had a decade to
churn. Comparing raw current-status share by creation year will look
like "companies are getting more resilient over time" when it's
really just younger cohorts not having failed YET. Prefer comparing
cohorts at the SAME AGE (e.g. "share still active 3 years after
creation") across departments/regions for the same creation year,
rather than eyeballing survival rate against calendar year.

Usage:
    from src.company_creation import sirene_v3_client as sv3
    from src.company_creation import survival_rate as surv
    sv3.set_api_key()

    df = surv.collect_all_departments(min_year=2018, max_year=2020)  # cheap pilot first
    summary = surv.build_summary(df)
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.company_creation import sirene_v3_client as sv3
from config.regions import FRENCH_DEPARTMENTS, MIN_YEAR, MAX_YEAR

ACTIVE = "A"
CEASED = "C"


def extract_row(record: dict) -> dict | None:
    """
    Pulls creation year + CURRENT administrative status from one raw
    établissement record — records here are already siège-filtered and
    enterprise-corrected by sv3.fetch_establishments()'s own query, so
    this is one row per new enterprise, not per établissement.
    """
    unite_legale = record.get("uniteLegale") or {}
    date_creation = unite_legale.get("dateCreationUniteLegale")
    if not date_creation:
        return None
    try:
        year = int(date_creation[:4])
    except (ValueError, TypeError):
        return None

    return {
        "year": year,
        "siren": record.get("siren"),
        "etat": unite_legale.get("etatAdministratifUniteLegale"),  # "A" active / "C" cessée
    }


def build_dataframe(records: list[dict], region_name: str) -> pd.DataFrame:
    rows = []
    for record in records:
        row = extract_row(record)
        if row is None:
            continue
        row["region"] = region_name
        rows.append(row)
    return pd.DataFrame(rows)


def _department_cache_path(dept_code: str, min_year: int, max_year: int) -> str:
    # Year range in the cache key: a survival snapshot is only valid for
    # the exact window it was fetched over, and "as of today" means the
    # cache also goes stale over time in a way most other caches in this
    # project don't — re-fetch (resume=False) if it's been a while.
    return f"data/processed/survival_dept_{dept_code}_{min_year}_{max_year}.csv"


def collect_all_departments(min_year: int = MIN_YEAR, max_year: int = MAX_YEAR, resume: bool = True) -> pd.DataFrame:
    """
    Fetch + tidy (creation_year, region, siren, etat) for every French
    department in config.regions.FRENCH_DEPARTMENTS. Requires
    sv3.set_api_key() first. See module docstring for the re-fetch cost
    caveat — pass a narrow min_year/max_year for a cheap pilot.
    """
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        csv_path = _department_cache_path(dept.insee_code, min_year, max_year)
        if resume and Path(csv_path).exists():
            print(f"\n{dept.name}: already fetched, loading from {csv_path} "
                  f"(pass resume=False to refresh — this snapshot goes stale over time, "
                  f"unlike most other caches in this project, since 'active' status changes daily).")
            frames.append(pd.read_csv(csv_path))
            continue

        print(f"\nFetching enterprise creations + current status for {dept.name} "
              f"(dept code {dept.insee_code}), {min_year}-{max_year}...")
        records, complete = sv3.fetch_establishments(dept.insee_code, min_year=min_year, max_year=max_year)
        print(f"  Total records retrieved: {len(records)} (complete: {complete})")
        dept_df = build_dataframe(records, dept.name)

        if complete:
            dept_df.to_csv(csv_path, index=False)
            print(f"  Saved: {csv_path}")
        else:
            print("  NOT caching — this department's fetch was incomplete. Re-run to retry.")
        frames.append(dept_df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per (creation_year, region): total companies, how many are still
    active, how many have ceased, and the resulting survival_rate.
    Read the module docstring's cohort-age caveat before charting this
    against calendar year.
    """
    if df.empty:
        return pd.DataFrame()

    summary = df.groupby(["year", "region"]).agg(
        total=("etat", "size"),
        active=("etat", lambda s: int((s == ACTIVE).sum())),
        ceased=("etat", lambda s: int((s == CEASED).sum())),
    ).reset_index()
    summary["other_status"] = summary["total"] - summary["active"] - summary["ceased"]
    summary["survival_rate"] = summary["active"] / summary["total"]
    return summary.sort_values(["year", "region"]).reset_index(drop=True)
