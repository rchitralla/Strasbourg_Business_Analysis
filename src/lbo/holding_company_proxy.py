"""
LBO proxy via new holding-company creations (Data Room question B24,
French side) — the acquisition-holding signal the brief itself proposes.

STATUS: a best-effort, EXPLICITLY PARTIAL implementation. No direct
public source exists for LBO transactions in either country (see
src/lbo/lbo_manual.py's docstring) — the Data Room brief proposes a
three-part proxy instead:
  1. NAF code 6420Z ("Activités des sociétés holding") on a NEWLY
     REGISTERED enterprise
  2. Registered office at the DIRECTOR'S HOME ADDRESS
  3. A SUBSEQUENT share acquisition + bank debt visible in filed
     accounts

THIS MODULE ONLY IMPLEMENTS PART 1 — new 6420Z holding-company
creations, correctly enterprise-corrected (reuses
sirene_v3_client.ENTERPRISE_ONLY_FILTER/CREATION_DATE_FIELD, the same
fix confirmed live against the official INSEE figure earlier this
project — so a branch office of an EXISTING holding company is not
miscounted as a new LBO vehicle).

Parts 2 and 3 are NOT implemented, and aren't a quick add:
  - Part 2 (director's home address) needs cross-referencing the
    établissement's registered address against the dirigeant's
    personal address — Sirene has no structured "is this the
    director's home" flag, and this project has no address-matching
    step built for it.
  - Part 3 (subsequent share acquisition + bank debt) needs either
    filed-accounts data (Comptes annuels — Infogreffe/INPI, not
    sourced here) or a per-SIREN BODACC follow-up search, expensive at
    volume and left out of this first version.

Because of this, a count from this module is NOT an LBO count — it is
a count of NEW HOLDING COMPANY CREATIONS BY NAF CODE, which the brief
itself calls "a robust marker" but says should be "presented as an
estimation method, never as a count." Caption it exactly that way on
any chart or slide.

UNVERIFIED: whether Sirene v3's `activitePrincipaleUniteLegale` field
is filterable via the `q` query string the way codeCommuneEtablissement
and dateCreationUniteLegale are (both confirmed live this project) has
NOT been tested. Run debug_holding_sample() first.

Usage:
    from src.company_creation import sirene_v3_client as sv3
    from src.lbo import holding_company_proxy as hcp
    sv3.set_api_key()

    hcp.debug_holding_sample("67")           # verify the query/field first
    df = hcp.collect_all_departments(min_year=2015, max_year=2026)
    summary = hcp.build_summary(df)
"""

import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.company_creation import sirene_v3_client as sv3
from config.regions import FRENCH_DEPARTMENTS, MIN_YEAR, MAX_YEAR

HOLDING_NAF_CODE = "64.20Z"  # "Activités des sociétés holding"


def _build_query(dept_code: str, min_year: int, max_year: int) -> str:
    return (
        f'codeCommuneEtablissement:{dept_code}* AND '
        f'{sv3.ENTERPRISE_ONLY_FILTER} AND '
        f'activitePrincipaleUniteLegale:"{HOLDING_NAF_CODE}" AND '
        f'{sv3.CREATION_DATE_FIELD}:[{min_year}-01-01 TO {max_year}-12-31]'
    )


def debug_holding_sample(dept_code: str, n: int = 5, min_year: int = MIN_YEAR, max_year: int = MAX_YEAR):
    """
    Run this FIRST — confirms activitePrincipaleUniteLegale is actually
    filterable via `q` (unverified) and shows a real matching record
    before trusting collect_all_departments() at volume. Compare
    header.total here against a manual count if you have any doubt.
    """
    import json

    query = _build_query(dept_code, min_year, max_year)
    params = {"q": query, "curseur": "*", "nombre": n}
    response = requests.get(sv3.SEARCH_ENDPOINT, params=params, headers=sv3._headers(), timeout=30)
    print(f"HTTP {response.status_code}")
    print(f"Query: {query}")
    if response.status_code != 200:
        print(response.text[:1000])
        return None
    payload = response.json()
    print(f"header.total: {payload.get('header', {}).get('total')}")
    print(json.dumps(payload.get("etablissements", [])[:2], indent=2, ensure_ascii=False)[:3000])
    return payload


def fetch_holding_creations(dept_code: str, min_year: int = MIN_YEAR, max_year: int = MAX_YEAR) -> tuple[list[dict], bool]:
    """
    Paginated fetch of new 6420Z holding-company creations for one
    department — same cursor/retry logic as
    sirene_v3_client.fetch_establishments(), with the added NAF-code
    filter. See module docstring for what this proxy does and doesn't
    capture. Returns (records, complete) — see fetch_establishments()'s
    docstring for why callers must check `complete` before trusting or
    caching a result.
    """
    query = _build_query(dept_code, min_year, max_year)

    all_results = []
    curseur = "*"
    complete = False

    while True:
        params = {"q": query, "curseur": curseur, "nombre": sv3.PAGE_SIZE}
        try:
            response = sv3._get_with_retry(sv3.SEARCH_ENDPOINT, params, sv3._headers(), timeout=60)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"\nGiving up on department {dept_code} after retries ({e.__class__.__name__}). "
                  f"Returning the {len(all_results)} record(s) fetched so far — INCOMPLETE.")
            break

        if response.status_code != 200:
            print(f"Request failed: HTTP {response.status_code}")
            print(response.text[:500])
            break

        payload = response.json()
        header = payload.get("header", {})
        results = payload.get("etablissements", [])
        all_results.extend(results)

        total = header.get("total")
        print(f"  Fetched {len(results)} record(s) (running total {len(all_results)}"
              f"{f'/{total}' if total is not None else ''})")

        next_curseur = header.get("curseurSuivant")
        if not results or not next_curseur or next_curseur == curseur:
            complete = True
            break
        curseur = next_curseur
        time.sleep(sv3.SECONDS_BETWEEN_REQUESTS)

    return all_results, complete


def extract_row(record: dict) -> dict | None:
    """
    Wraps sirene_v3_client.extract_row() with a defensive check that
    the activity code really is the holding-company NAF code — in case
    the query's activitePrincipaleUniteLegale filter didn't behave as
    expected (see debug_holding_sample()'s UNVERIFIED note), this drops
    any record that slipped through without the right code rather than
    silently counting it.
    """
    unite_legale = record.get("uniteLegale") or {}
    naf_code = record.get("activitePrincipaleEtablissement") or unite_legale.get("activitePrincipaleUniteLegale")
    if naf_code != HOLDING_NAF_CODE:
        return None
    return sv3.extract_row(record)


def build_dataframe(records: list[dict], region_name: str) -> pd.DataFrame:
    rows = []
    for record in records:
        row = extract_row(record)
        if row is None:
            continue
        row["region"] = region_name
        rows.append(row)
    return pd.DataFrame(rows)


def _department_cache_path(dept_code: str) -> str:
    return f"data/processed/lbo_holding_proxy_dept_{dept_code}.csv"


def collect_all_departments(min_year: int = MIN_YEAR, max_year: int = MAX_YEAR, resume: bool = True) -> pd.DataFrame:
    """
    Fetch + tidy new 6420Z holding-company creations for every French
    department in config.regions.FRENCH_DEPARTMENTS. Requires
    sv3.set_api_key() first — reuses the same session-wide API key.
    """
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        csv_path = _department_cache_path(dept.insee_code)
        if resume and Path(csv_path).exists():
            print(f"\n{dept.name}: already fetched, loading from {csv_path} (pass resume=False to re-fetch).")
            frames.append(pd.read_csv(csv_path))
            continue

        print(f"\nFetching 6420Z holding-company creations for {dept.name} (dept code {dept.insee_code}), "
              f"{min_year}-{max_year}...")
        records, complete = fetch_holding_creations(dept.insee_code, min_year, max_year)
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
    Yearly count of new 6420Z holding-company creations per department
    — the proxy SIGNAL itself, NOT an LBO count. See module docstring
    before presenting this anywhere.
    """
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["year", "region"])
        .size()
        .rename("new_holding_companies")
        .reset_index()
        .sort_values(["year", "region"])
    )
