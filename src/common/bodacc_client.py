"""
Shared BODACC (Bulletin officiel des annonces civiles et commerciales)
client — opendatasoft "Explore API v2.1" against the "annonces-commerciales"
dataset. Free, public, no API key required.

Shared by three axes that all read the same dataset with different
filters:
  - src/failures/bodacc_failures.py  (insolvency notices)
  - src/mna/bodacc_mna.py            (merger notices)
  - src/lbo/lbo_manual.py            (holding-company-formation proxy)

CONFIRMED against a live response (2026-09-04, via scripts/bodacc_debug_sample.py):
  - Geography field is `numerodepartement` (a 2-digit string, e.g. "67"),
    NOT "departement" — that guess 400'd. Companion fields
    departement_nom_officiel, region_code, region_nom_officiel are also
    present on every record.
  - `familleavis` (short code, e.g. "dpc") / `familleavis_lib` (French
    label, e.g. "Dépôts des comptes") categorize the notice type. A
    100-record UNFILTERED sample came back 100% "Dépôts des comptes"
    (annual account filings) — this family dominates raw volume (every
    company files yearly), so an unfiltered sample is NOT a reliable way
    to discover the full familleavis_lib taxonomy. Use
    scripts/bodacc_debug_sample.py's exclusion-based discovery loop
    instead, or confirm each family name you actually need (merger,
    insolvency, etc.) with a direct debug_sample() call once you have a
    candidate string.
  - Nested detail fields — listepersonnes, jugement, acte,
    modificationsgenerales, depot, radiationaurcs, listeprecedentexploitant,
    listeprecedentproprietaire, divers, listeetablissements — are each
    either null OR a JSON-ENCODED STRING (not a real nested object/dict).
    E.g. for a "Dépôts des comptes" notice, `depot` looked like
    '{"dateCloture": "2024-08-31", "typeDepot": "Comptes annuels et
    rapports", ...}' as a STRING. pd.json_normalize() will NOT parse
    these — use parse_json_field() below on the specific column(s) a
    given family populates (which field is populated depends on
    familleavis: expect `jugement` for insolvency notices, likely
    `modificationsgenerales` for mergers — NOT YET CONFIRMED against a
    real example of either, since our only live samples so far are all
    "Dépôts des comptes").
  - `registre` is a 2-element list: [siren_no_spaces, siren_with_spaces],
    e.g. ["752461681", "752 461 681"] — index 0 for a clean SIREN.
  - `commercant` (company name as a plain string) and `ville` are at the
    top level.

API basics (standard Opendatasoft Explore API v2.1 shape):
  Base URL: https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records
  Pagination: `limit` (max 100/page) + `offset`. The JSON response has
  "total_count" (matches for the current `where`, without needing to
  fetch them) and "results" (the actual records for this page).
  Filtering: `where` takes ODSQL (Opendatasoft Query Language), e.g.
  where=numerodepartement="67". No API key needed.

CACHING: fetch_and_cache() saves matching records to a local JSON file
the first time and loads from that file on every subsequent call
instead of re-querying the API — mirrors sirene_v3_client.py's
per-department resume pattern. Delete the cache file to force a
refetch (e.g. after changing the `where` clause).

Records are cached as raw (nested) JSON rather than flattened to CSV,
since the notice shape genuinely differs by type (an insolvency notice's
"jugement" block, a merger's "modificationsgenerales" block, etc. are
different structures) and committing to a flat schema before confirming
field names against a live response risks losing data silently. Callers
get a pandas DataFrame via pd.json_normalize() at load time, but can
also work with the raw list-of-dicts (see fetch_and_cache's return) if
they need a nested field json_normalize didn't flatten usefully.
"""

import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
PAGE_SIZE = 100  # Opendatasoft v2.1 max rows per page
SECONDS_BETWEEN_REQUESTS = 0.5
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 5

GEOGRAPHY_FIELD = "numerodepartement"  # confirmed 2026-09-04, NOT "departement"

# Fields that come back as a JSON-ENCODED STRING (or null) rather than a
# real nested object — confirmed for listepersonnes/depot; the others
# are the same shape by consistent API design but not yet seen non-null.
JSON_STRING_FIELDS = [
    "listepersonnes", "listeetablissements", "jugement", "acte",
    "modificationsgenerales", "radiationaurcs", "depot",
    "listeprecedentexploitant", "listeprecedentproprietaire", "divers",
]


def parse_json_field(value):
    """
    Safely parse one of JSON_STRING_FIELDS's string-encoded values into
    a real dict/list. Returns None for null/empty/unparseable input
    rather than raising, since most records leave most of these fields
    null (only the field(s) relevant to that notice's familleavis are
    populated).
    """
    if not value or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _get_with_retry(params: dict, timeout: int = 30):
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return requests.get(BASE_URL, params=params, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"  Network error ({e.__class__.__name__}), retrying in {wait}s "
                  f"(attempt {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)
    raise last_exc


def debug_sample(where: str = "", n: int = 5) -> dict | None:
    """
    Fetch a SMALL sample and pretty-print the raw JSON response. Run
    this FIRST — with no filter, then with a candidate geography/date
    filter — to confirm field names before trusting anything else in
    this module or its callers.

        from src.common import bodacc_client as bc
        bc.debug_sample()                              # unfiltered, most recent
        bc.debug_sample('numerodepartement="67"')      # confirmed geography field
    """
    params = {"limit": n}
    if where:
        params["where"] = where
    response = requests.get(BASE_URL, params=params, timeout=30)
    print(f"HTTP {response.status_code}")
    if response.status_code != 200:
        print(response.text[:1500])
        return None
    payload = response.json()
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:6000])
    return payload


def count_records(where: str) -> int | None:
    """
    Return the TOTAL count of records matching an ODSQL filter WITHOUT
    fetching them — cheap way to get a national-scale or Baden-
    Württemberg-scale headline number (e.g. "how many merger notices in
    all of France in 2024") without pulling every row. Use fetch_all()/
    fetch_and_cache() instead when you need the actual records (e.g. for
    the 3-department per-sector breakdown).
    """
    response = _get_with_retry({"where": where, "limit": 1})
    if response.status_code != 200:
        print(f"count_records failed: HTTP {response.status_code}: {response.text[:300]}")
        return None
    return response.json().get("total_count")


def fetch_all(where: str, max_records: int = None) -> list[dict]:
    """
    Paginate through every record matching an ODSQL filter. Prefer
    count_records() instead when you only need a total, not the
    individual records (much cheaper for large national-scale filters).
    """
    records = []
    offset = 0
    while True:
        limit = PAGE_SIZE
        if max_records is not None:
            limit = min(PAGE_SIZE, max_records - len(records))
            if limit <= 0:
                break

        response = _get_with_retry({"where": where, "limit": limit, "offset": offset})
        if response.status_code != 200:
            print(f"fetch_all failed at offset {offset}: HTTP {response.status_code}: "
                  f"{response.text[:300]}")
            break

        payload = response.json()
        batch = payload.get("results", [])
        if not batch:
            break
        records.extend(batch)

        total = payload.get("total_count")
        print(f"  Fetched {len(batch)} records (running total {len(records)}"
              f"{f'/{total}' if total is not None else ''})")

        offset += len(batch)
        if total is not None and offset >= total:
            break
        time.sleep(SECONDS_BETWEEN_REQUESTS)

    return records


def fetch_and_cache(where: str, cache_path: str, max_records: int = None, resume: bool = True) -> pd.DataFrame:
    """
    fetch_all(), but cached to disk so re-running a script (or a whole
    notebook session) never re-hits the API for data already fetched.
    Delete cache_path to force a refetch — e.g. after correcting a
    where-clause once real field names are confirmed.

        df = fetch_and_cache(
            'departement="67" AND familleavis_lib="Procédures collectives"',
            "data/processed/bodacc_failures_67.json",
        )
    """
    cache_file = Path(cache_path)
    if resume and cache_file.exists():
        print(f"Loading cached BODACC records from {cache_path} "
              f"(delete this file to force a refetch)")
        with open(cache_file, encoding="utf-8") as f:
            records = json.load(f)
    else:
        print(f"Fetching from BODACC (where: {where})...")
        records = fetch_all(where, max_records=max_records)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)
        print(f"Cached {len(records)} record(s) to {cache_path}")

    return pd.json_normalize(records)
