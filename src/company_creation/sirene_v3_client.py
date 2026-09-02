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
    records, complete = sv3.fetch_establishments("67", min_year=2015, max_year=2026)

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
   PARTIALLY resolved — see LEGAL_FORM_LABELS / IS_SOLE_SHAREHOLDER_BY_CODE
   below, confirmed against multiple independent sources 2026-09-02 (see
   docs/DATA_SOURCES.md for citations): 1000=EI, 5498=EURL (sole),
   5499=Autre SARL (multi — EURL has its own code so this one doesn't),
   6540=SCI (multi — legally requires 2+ shareholders), 9220/9260=
   associations (not a shareholder société at all). 5710 (SAS) stays
   explicitly ambiguous — INSEE merged the SASU-specific code (5720)
   into it in July 2020, so single- vs multi-shareholder SAS can't be
   told apart via this field. Any code NOT in these two dicts is simply
   unmapped (None), not "no" — the ~100-code INSEE nomenclature is far
   from fully covered yet.

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
MAX_RETRIES = 5                  # for transient network errors (DNS blips, timeouts)
RETRY_BACKOFF_SECONDS = 5        # multiplied by attempt number

_API_KEY = None


def _get_with_retry(url, params, headers, timeout):
    """
    Wraps requests.get() with retries for transient network errors
    (DNS resolution blips, timeouts, connection resets) — a long
    cursor-pagination run (potentially hundreds of requests over 15-30+
    minutes) will otherwise die on a single momentary network hiccup
    and lose everything fetched so far.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return requests.get(url, params=params, headers=headers, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"  Network error ({e.__class__.__name__}), retrying in {wait}s "
                  f"(attempt {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)
    raise last_exc


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


def fetch_establishments(departement_code: str, min_year: int, max_year: int) -> tuple[list[dict], bool]:
    """
    Fetch every "établissement" created in a department within
    [min_year, max_year], walking the cursor until exhausted. No
    10,000-result ceiling (unlike the recherche-entreprises wrapper).

    Returns (records, complete). complete is False if the fetch had to
    give up early (network failure after retries, or a non-200
    response) — callers MUST check this before treating the result as
    a full, cacheable dataset for this department.
    """
    query = (
        f"codeCommuneEtablissement:{departement_code}* "
        f"AND dateCreationEtablissement:[{min_year}-01-01 TO {max_year}-12-31]"
    )

    all_results = []
    curseur = "*"
    seen_nomenclatures = set()
    complete = False

    while True:
        params = {"q": query, "curseur": curseur, "nombre": PAGE_SIZE}
        try:
            response = _get_with_retry(SEARCH_ENDPOINT, params, _headers(), timeout=60)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"\nGiving up on department {departement_code} after {MAX_RETRIES} retries "
                  f"({e.__class__.__name__}). Returning the {len(all_results)} records "
                  f"already fetched for this department so far — nothing is lost, but "
                  f"this department's data is INCOMPLETE (cursor was mid-pagination).")
            break

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
            complete = True
            break
        curseur = next_curseur
        time.sleep(SECONDS_BETWEEN_REQUESTS)

    unexpected = seen_nomenclatures - {"NAFRev2"}
    if unexpected:
        print(f"\nNOTE: {unexpected} nomenclature(s) also seen alongside NAFRev2 "
              "(expected for legal units old enough to predate the 2008 NAF change). "
              "extract_row() buckets those into an explicit "
              "'Unknown / unclassified (<nomenclature>)' sector rather than "
              "guessing via the NAFRev2 table — check how big that bucket is "
              "before treating the sector breakdown as complete.")

    return all_results, complete


# Confirmed against multiple independent sources (2026-09-02) — see
# docs/DATA_SOURCES.md for citations. Deliberately partial: only codes
# confirmed with real evidence are included. Any other code stays
# unmapped rather than guessed.
LEGAL_FORM_LABELS = {
    "1000": "Entrepreneur Individuel (EI)",
    "5498": "EURL (SARL, single shareholder)",
    "5499": "Autre SARL (standard, multi-shareholder)",
    "5710": "SAS (absorbed SASU in 2020 — shareholder count ambiguous)",
    "6540": "SCI (Société Civile Immobilière — legally requires 2+ shareholders)",
    "9220": "Association déclarée",
    "9260": "Association de droit local (Alsace-Moselle)",
}

# is_sole_shareholder per confirmed code. None = ambiguous or not a
# shareholder-based société at all (EI, associations) — excluded from
# B18's "share of multi-partner companies" denominator, not counted as
# either sole or multi. Codes not in this dict are simply unmapped.
IS_SOLE_SHAREHOLDER_BY_CODE = {
    "1000": None,   # EI — not a société; not applicable to B18 at all
    "5498": True,   # EURL
    "5499": False,  # Autre SARL (excludes EURL, which has its own code)
    "5710": None,   # SAS — ambiguous since the 2020 SASU merge
    "6540": False,  # SCI — legally requires 2+ shareholders
    "9220": None,   # association — not a shareholder société
    "9260": None,   # association (Alsace-Moselle local law) — not a shareholder société
}


def extract_row(record: dict) -> dict | None:
    """
    Pull creation year, sector, and legal form from one raw établissement
    record.

    legal_form is the raw numeric categorieJuridiqueUniteLegale code as a
    string. is_sole_shareholder is populated ONLY for the confirmed subset
    in IS_SOLE_SHAREHOLDER_BY_CODE (see docs/DATA_SOURCES.md for sources);
    every other code — the large majority of the ~100-code INSEE
    nomenclature — stays None (unmapped, not "no"). B16 (creations by
    sector) should generally EXCLUDE legal_form == "1000" (EI) if the
    intent is "sociétés" specifically, per how B16 vs B17 are phrased as
    separate questions in the Data Room brief.
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
    nomenclature = record.get("nomenclatureActivitePrincipaleEtablissement") or unite_legale.get(
        "nomenclatureActivitePrincipaleUniteLegale"
    )

    # NAF_SECTION_BY_CODE_PREFIX is built for NAFRev2's code ranges only.
    # Some legal units (old enough to predate the 2008 nomenclature change,
    # and never reclassified since — even though they opened a NEW
    # établissement inside our date window) still carry a NAFRev1 code, and
    # from Jan 2027 some will carry NAF25. Applying the NAFRev2 table to
    # either would silently produce a wrong section letter, so those get an
    # explicit, honest "unclassified" bucket instead of a guessed one.
    if nomenclature == "NAFRev2":
        section = naf_code_to_section(naf_code)
        sector = NAF_WZ_SECTION_LABELS.get(section, "Unknown / unclassified")
    else:
        sector = f"Unknown / unclassified ({nomenclature or 'no nomenclature'})"

    legal_form_code_raw = unite_legale.get("categorieJuridiqueUniteLegale")
    legal_form = str(legal_form_code_raw) if legal_form_code_raw else "?"

    return {
        "year": year,
        "sector": sector,
        "legal_form": legal_form,
        "legal_form_label": LEGAL_FORM_LABELS.get(legal_form),  # None if unmapped
        "is_sole_shareholder": IS_SOLE_SHAREHOLDER_BY_CODE.get(legal_form),
    }


def build_dataframe(records: list[dict], region_name: str) -> "pd.DataFrame":
    """
    Turn raw établissement records into a tidy DataFrame: one row per
    (year, region, sector, legal_form) with a count column. Same shape
    as france_creations.py's build_dataframe(), so it plugs into the
    same CSV/chart pipeline.
    """
    import pandas as pd
    from collections import defaultdict

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
    # Derived purely from legal_form (see LEGAL_FORM_LABELS /
    # IS_SOLE_SHAREHOLDER_BY_CODE) — added as columns rather than folded
    # into the groupby key above, since they're deterministic lookups.
    df["legal_form_label"] = df["legal_form"].map(LEGAL_FORM_LABELS)
    df["is_sole_shareholder"] = df["legal_form"].map(IS_SOLE_SHAREHOLDER_BY_CODE)
    return df.sort_values(["year", "region", "sector"]).reset_index(drop=True)


def _department_csv_path(dept_code: str) -> str:
    return f"data/processed/france_creations_sirene_v3_dept_{dept_code}.csv"


def collect_all_departments(min_year: int, max_year: int, resume: bool = True) -> "pd.DataFrame":
    """
    Fetch and tidy creations for every French department in
    config.regions.FRENCH_DEPARTMENTS, returning one combined DataFrame.
    Requires set_api_key() to have been called first.

    This is the uncapped replacement for france_creations.collect_all_regions()
    — expect it to take a while (rate-limited to ~1 request per 2.1s, and
    each department can be hundreds of pages across an 11-year window).

    Each department's tidy result is saved to its own CSV
    (data/processed/france_creations_sirene_v3_dept_<code>.csv) AS SOON AS
    IT FINISHES, not just at the very end — so a crash partway through
    department 2 of 3 doesn't lose department 1's already-fetched data.
    If resume=True (default) and a department's CSV already exists from
    a previous run, it's loaded from disk instead of re-fetched — re-run
    this after any failure and it'll pick up where it left off.
    """
    import pandas as pd
    from pathlib import Path
    from config.regions import FRENCH_DEPARTMENTS

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        csv_path = _department_csv_path(dept.insee_code)
        if resume and Path(csv_path).exists():
            print(f"\n{dept.name} (dept code {dept.insee_code}): already fetched, "
                  f"loading from {csv_path} (pass resume=False to re-fetch).")
            frames.append(pd.read_csv(csv_path))
            continue

        print(f"\nFetching établissements for {dept.name} (dept code {dept.insee_code}), "
              f"{min_year}-{max_year}...")
        records, complete = fetch_establishments(dept.insee_code, min_year=min_year, max_year=max_year)
        print(f"  Total records retrieved: {len(records)} (complete: {complete})")
        dept_df = build_dataframe(records, dept.name)

        if complete:
            dept_df.to_csv(csv_path, index=False)
            print(f"  Saved: {csv_path}")
        else:
            print(f"  NOT caching — this department's fetch was incomplete. "
                  f"Re-run collect_all_departments()/run_all() to retry it "
                  f"(completed departments will be loaded from cache, not re-fetched).")
        frames.append(dept_df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run_all(min_year: int = 2015, max_year: int = 2026):
    """
    Full pipeline: fetch all 3 departments, save tidy CSV, plot the
    year x region comparison chart. Call after set_api_key().

        sv3.set_api_key()
        df = sv3.run_all()
    """
    from pathlib import Path
    from src.common.plotting import grouped_region_bar

    df = collect_all_departments(min_year, max_year)
    if df.empty:
        print("No usable data retrieved.")
        return df

    csv_path = "data/processed/france_creations_sirene_v3_by_year_dept_sector.csv"
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"\nTidy data saved to: {csv_path}")

    yearly_by_region = df.groupby(["year", "region"])["count"].sum().reset_index()
    grouped_region_bar(
        yearly_by_region, value_col="count",
        title="New Establishment Creations by Year and Department (Sirene v3.11, uncapped)",
        ylabel="Number of new establishments",
        output_path="outputs/charts/france_creations_sirene_v3_by_year_region.png",
    )
    return df


# ---------------------------------------------------------------------------
# REMAINING OPEN QUESTION before this can answer B17/B18:
#
# Resolve the legal-form / sole-shareholder question: check whether the
# live nomenclature reference (portal's "Documentation" tab, or
# https://www.insee.fr/fr/information/2028129) still lets you derive
# single- vs multi-shareholder status from categorieJuridiqueUniteLegale
# post-2020 (SASU code 5720 was merged into SAS code 5710 that year), or
# whether that needs a different source entirely (e.g. INPI's Registre
# National des Entreprises, which does track associate counts). B16
# (creations by sector) does not depend on this and is ready to run now
# via run_all().
# ---------------------------------------------------------------------------
