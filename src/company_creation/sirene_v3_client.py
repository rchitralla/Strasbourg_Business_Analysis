"""
INSEE Sirene API v3.11 client — cursor-paginated, no 10,000-result cap.

This replaces the recherche-entreprises wrapper API used in
france_creations.py, which silently truncates any department query at
10,000 results (confirmed via scripts/check_api_pagination_limit.py —
Bas-Rhin, Haut-Rhin and Moselle all hit the exact same ceiling). Sirene
v3.11 avoids that by using cursor-based pagination instead of page
offsets.

Confirmed against the live portal (2026-08-30):
  - Base URL:   https://api.insee.fr/api-sirene/3.11
  - Auth:       header "X-INSEE-Api-Key-Integration: <your API key>"
  - Pagination: curseur-based. First request: curseur=*. Each response's
                header.curseurSuivant becomes the next request's curseur.
                Stop when curseurSuivant == curseur (no more results).
                nombre (page size) can go up to 1000, and there is no
                10,000 total-results ceiling.
  - Rate limit: 30 requests/minute on the public plan — this client
                sleeps between requests to stay under that.

DESIGNED FOR JUPYTER / interactive use, same pattern as
germany_registrations.py:

    from src.company_creation import sirene_v3_client as sv3
    sv3.set_api_key()                      # prompts securely
    sample = sv3.debug_sample("67")        # inspect raw response shape FIRST
    records = sv3.fetch_establishments("67", min_year=2015, max_year=2026)

Run debug_sample() before trusting fetch_establishments()/extract_row() —
the field names below (etablissements, uniteLegale, categorieJuridique...)
are my best-confirmed understanding of the v3.11 response shape from
public documentation, but I have not been able to see a real response
from this environment (network access to api.insee.fr is blocked here).
Treat them as unverified until debug_sample()'s printed JSON confirms
them against your own live account.

TWO THINGS CONFIRMED WHILE BUILDING THIS THAT AREN'T FULLY RESOLVED YET:

1. NAF/sector classification (affects B16): Sirene returns the raw NAF
   code (e.g. "62.02A") in `activitePrincipaleEtablissement`, not a
   pre-computed section letter like the recherche-entreprises wrapper
   gave us. This module derives the section (A-U) from the code's
   2-digit prefix using the standard NACE Rev.2 ranges
   (NAF_SECTION_BY_CODE_PREFIX below) — stable, well-documented EU
   standard, high confidence.

   BUT: per the portal's own transition notice (surfaced 2026-08-30),
   from 5-6 January 2027 `activitePrincipaleEtablissement` switches to
   NAF2025 codes, flagged by `nomenclatureActivitePrincipaleEtablissement`
   == "NAF25" (vs "NAFRev2" today). fetch_establishments() checks this
   field on every record and prints a loud warning rather than silently
   mis-mapping a NAF2025 code through the NAF Rev.2 table.

2. Legal-form / sole-shareholder classification (needed for B17/B18) is
   INTENTIONALLY NOT implemented here. `categorieJuridiqueUniteLegale`
   is a numeric code, and INSEE merged the SASU-specific code (5720)
   into the ordinary SAS code (5710) in July 2020 — meaning
   single-shareholder SAS companies may no longer be distinguishable
   from multi-shareholder ones via this field alone. It's unconfirmed
   whether EURL/SARL suffered the same merge. extract_row() passes
   through the raw code UNMAPPED rather than guessing. Do not build
   B17/B18 answers on this until that's resolved — see the module-level
   TODO at the bottom.

Requirements:
    pip install requests pandas
"""

import sys
import time
from getpass import getpass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.sectors import NAF_WZ_SECTION_LABELS

BASE_URL = "https://api.insee.fr/api-sirene/3.11"
SEARCH_ENDPOINT = f"{BASE_URL}/siret"
PAGE_SIZE = 1000                 # max allowed by the API
SECONDS_BETWEEN_REQUESTS = 2.1   # stays under the 30 req/min public-plan limit

_API_KEY = None


def set_api_key(key: str = None):
    """
    Set your INSEE Sirene API key for this session.

        sv3.set_api_key()          # prompts securely, nothing echoed/saved
        sv3.set_api_key("xxx")     # or pass directly
    """
    global _API_KEY
    _API_KEY = key if key is not None else getpass("INSEE Sirene API key: ")
    print("API key set for this session.")


def _headers():
    if not _API_KEY:
        raise RuntimeError("Call set_api_key() first.")
    return {"X-INSEE-Api-Key-Integration": _API_KEY, "Accept": "application/json"}


# NACE Rev.2 section boundaries (stable EU standard) — used to derive a
# section letter (A-U) from the raw 2-digit NAF prefix Sirene returns.
def _build_naf_section_table():
    table = {}
    ranges = [
        (1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"), (36, 39, "E"),
        (41, 43, "F"), (45, 47, "G"), (49, 53, "H"), (55, 56, "I"), (58, 63, "J"),
        (64, 66, "K"), (68, 68, "L"), (69, 75, "M"), (77, 82, "N"), (84, 84, "O"),
        (85, 85, "P"), (86, 88, "Q"), (90, 93, "R"), (94, 96, "S"), (97, 98, "T"),
        (99, 99, "U"),
    ]
    for lo, hi, section in ranges:
        for i in range(lo, hi + 1):
            table[f"{i:02d}"] = section
    return table


NAF_SECTION_BY_CODE_PREFIX = _build_naf_section_table()


def naf_code_to_section(naf_code: str) -> str:
    if not naf_code or len(naf_code) < 2:
        return "?"
    return NAF_SECTION_BY_CODE_PREFIX.get(naf_code[:2], "?")


def debug_sample(departement_code: str, n: int = 5):
    """
    Fetch a SMALL sample (default 5 records) and pretty-print the raw
    JSON response. Run this FIRST, before fetch_establishments(), to
    visually confirm the response shape (top-level key, "uniteLegale"
    nesting, field names) matches what this module assumes.
    """
    import json

    query = f"codeCommuneEtablissement:{departement_code}*"
    params = {"q": query, "curseur": "*", "nombre": n}
    response = requests.get(SEARCH_ENDPOINT, params=params, headers=_headers(), timeout=30)
    print(f"HTTP {response.status_code}")
    if response.status_code != 200:
        print(response.text[:1000])
        return None
    payload = response.json()
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
    return payload


def fetch_establishments(departement_code: str, min_year: int, max_year: int) -> list[dict]:
    """
    Fetch every "établissement" created in a department within
    [min_year, max_year], walking the cursor until exhausted. No
    10,000-result ceiling (unlike the recherche-entreprises wrapper).
    """
    query = (
        f"codeCommuneEtablissement:{departement_code}* "
        f"AND dateCreationEtablissement:[{min_year}-01-01 TO {max_year}-12-31]"
    )

    all_results = []
    curseur = "*"
    seen_nomenclatures = set()

    while True:
        params = {"q": query, "curseur": curseur, "nombre": PAGE_SIZE}
        response = requests.get(SEARCH_ENDPOINT, params=params, headers=_headers(), timeout=60)

        if response.status_code != 200:
            print(f"Request failed: HTTP {response.status_code}")
            print(response.text[:500])
            break

        payload = response.json()
        header = payload.get("header", {})
        results = payload.get("etablissements", [])
        all_results.extend(results)

        for r in results:
            nomenclature = r.get("nomenclatureActivitePrincipaleEtablissement") or (
                r.get("uniteLegale") or {}
            ).get("nomenclatureActivitePrincipaleUniteLegale")
            if nomenclature:
                seen_nomenclatures.add(nomenclature)

        total = header.get("total")
        print(f"  Fetched {len(results)} records (running total {len(all_results)}"
              f"{f'/{total}' if total is not None else ''})")

        next_curseur = header.get("curseurSuivant")
        if not results or not next_curseur or next_curseur == curseur:
            break
        curseur = next_curseur
        time.sleep(SECONDS_BETWEEN_REQUESTS)

    unexpected = seen_nomenclatures - {"NAFRev2"}
    if unexpected:
        print(f"\nWARNING: unexpected NAF nomenclature(s) seen: {unexpected}. "
              "The NAF Rev.2 section mapping in this module (NAF_SECTION_BY_CODE_PREFIX) "
              "does not apply to these records — see the NAF2025 transition note in "
              "this module's docstring. Sector labels for these records will be wrong.")

    return all_results


def extract_row(record: dict) -> dict | None:
    """
    Pull creation year and sector from one raw établissement record.

    legal_form_code_raw is passed through UNMAPPED (see module docstring,
    item 2) — do not use it as-is for B17/B18 sole-shareholder analysis.
    """
    date_creation = record.get("dateCreationEtablissement")
    if not date_creation:
        return None
    try:
        year = int(date_creation[:4])
    except (ValueError, TypeError):
        return None

    unite_legale = record.get("uniteLegale") or {}

    # Confirmed against a live response (2026-08-30): the établissement-level
    # activitePrincipaleEtablissement field was not visible in our sample
    # (JSON was truncated before we could confirm it either way), but
    # uniteLegale.activitePrincipaleUniteLegale + nomenclatureActivitePrincipaleUniteLegale
    # were directly confirmed present. Prefer the établissement-level field
    # when present (it's the more specific one), fall back to the unit-level one.
    naf_code = record.get("activitePrincipaleEtablissement") or unite_legale.get(
        "activitePrincipaleUniteLegale"
    )
    section = naf_code_to_section(naf_code)
    sector = NAF_WZ_SECTION_LABELS.get(section, "Unknown / unclassified")

    legal_form_code_raw = unite_legale.get("categorieJuridiqueUniteLegale")

    return {
        "year": year,
        "sector": sector,
        "legal_form": str(legal_form_code_raw) if legal_form_code_raw else "?",
        "is_sole_shareholder": None,  # UNRESOLVED — see module docstring item 2
    }


# ---------------------------------------------------------------------------
# TODO before this fully replaces france_creations.py's fetch_companies():
#
# 1. Run debug_sample() for one department and confirm against the printed
#    JSON that: the top-level results key really is "etablissements", that
#    "uniteLegale" nests exactly as assumed, and that
#    "activitePrincipaleEtablissement" / "dateCreationEtablissement" /
#    "categorieJuridiqueUniteLegale" are the real field names (v3.11 docs
#    were not directly viewable from this environment — network access to
#    api.insee.fr and portail-api.insee.fr is blocked here).
#
# 2. Resolve the legal-form / sole-shareholder question (B17/B18): check
#    whether the live nomenclature reference (portal's "Documentation" tab,
#    or https://www.insee.fr/fr/information/2028129) still lets you derive
#    single- vs multi-shareholder status from categorieJuridiqueUniteLegale
#    post-2020, or whether that needs a different source entirely (e.g.
#    INPI's Registre National des Entreprises, which does track associate
#    counts).
# ---------------------------------------------------------------------------
