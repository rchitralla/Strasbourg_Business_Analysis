"""
Diagnostic: does recherche-entreprises.api.gouv.fr cap total paginated
results at 10,000 for a department-level query, independent of how many
companies actually match?

Why this exists: france_creations.py reported "total_results" of exactly
10000 for Bas-Rhin, Haut-Rhin AND Moselle. Three different departments
landing on the exact same total is the signature of a hard API result
ceiling (common on Elasticsearch-backed search APIs, usually to protect
the backend from expensive deep pagination), not a real coincidence.
This script proves or disproves that directly, with a handful of small,
fast requests — it does NOT do a full data pull.

Safe to run in parallel with a long-running france_creations.py fetch in
another terminal — this makes independent, lightweight requests.

Usage:
    python scripts/check_api_pagination_limit.py            # checks 67, 68, 57
    python scripts/check_api_pagination_limit.py 67          # just Bas-Rhin
"""

import sys

import requests

API_URL = "https://recherche-entreprises.api.gouv.fr/search"
PER_PAGE = 25
ASSUMED_CAP = 10_000


def probe(departement_code: str):
    print(f"=== Department {departement_code} ===")

    # 1. What does the API claim the total is, for the unfiltered department query?
    r = requests.get(
        API_URL,
        params={"departement": departement_code, "per_page": PER_PAGE, "page": 1},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    total_results = payload.get("total_results")
    print(f"  API-reported total_results: {total_results}")

    if total_results != ASSUMED_CAP:
        print(f"  -> Does NOT match the suspected {ASSUMED_CAP} cap for this department.")
    else:
        print(f"  -> Matches the suspected {ASSUMED_CAP} cap. Checking if pagination "
              f"actually stops there...")

    # 2. Can we actually page all the way through, or does it cut off before/at
    #    the point a 10,000-result cap would predict?
    last_page_under_cap = ASSUMED_CAP // PER_PAGE  # 400
    for label, page in [
        (f"last page under a {ASSUMED_CAP}-result cap", last_page_under_cap),
        ("one page beyond that", last_page_under_cap + 1),
    ]:
        resp = requests.get(
            API_URL,
            params={"departement": departement_code, "per_page": PER_PAGE, "page": page},
            timeout=30,
        )
        if resp.status_code == 200:
            n = len(resp.json().get("results", []))
            detail = f"{n} results returned"
        else:
            detail = f"body: {resp.text[:200]}"
        print(f"  page {page} ({label}): HTTP {resp.status_code}, {detail}")

    print()


if __name__ == "__main__":
    departments = sys.argv[1:] or ["67", "68", "57"]
    for dept in departments:
        probe(dept)
