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
    pd.json_normalize() will NOT parse these — use parse_json_field()
    below on the specific column(s) a given family populates.
  - `registre` is a 2-element list holding the SAME SIREN in both a
    spaced and unspaced format, but THE ORDER IS NOT CONSISTENT between
    records — one example had ["752461681", "752 461 833"] (unspaced
    first), another had ["482 309 382", "482309382"] (spaced first). Use
    extract_siren() below (strips non-digits from either element) rather
    than assuming a fixed index.
  - `commercant` (company name as a plain string) and `ville` are at the
    top level on every record.

  Family taxonomy (familleavis_lib) confirmed via the exclusion-loop
  discovery in scripts/bodacc_debug_sample.py — 10 families found:
    "Dépôts des comptes"                        - annual account filings (dominates raw volume)
    "Procédures collectives"                    - insolvency proceedings (B9) - jugement field populated, see below
    "Procédures de conciliation"                - pre-insolvency conciliation (softer than "collectives")
    "Modifications diverses"                    - broad catch-all for company changes (capital increase/decrease, legal-
                                                    form transformation, management changes, etc.) - see schema below.
                                                    NOT confirmed to include mergers/TUP specifically yet - both live
                                                    examples seen were capital changes, not a fusion. If a merger notice
                                                    exists in this dataset it's most likely findable via a substring
                                                    search on modificationsgenerales's descriptif text (e.g. containing
                                                    "fusion") - NOT YET TESTED, see scripts/bodacc_debug_mergers.py.
    "Radiations"                                 - deregistrations/strike-offs
    "Procédures de rétablissement professionnel" - simplified no-asset liquidation (very small businesses)
    "Créations"                                  - NEW COMPANY INCORPORATIONS - CONFIRMED to carry share capital at
                                                    formation (listepersonnes.personne.capital.montantCapital) - see
                                                    schema below. This is THE source for the avg-share-capital question.
    "Immatriculations"                           - registrations, possibly distinct from "Créations" - NOT YET inspected
    "Ventes et cessions"                         - CONFIRMED: fonds-de-commerce (business/goodwill) SALES, not share/
                                                    equity deals. A real transaction signal (buyer via listepersonnes,
                                                    seller via listeprecedentproprietaire, sometimes a price embedded as
                                                    free text in listeetablissements.etablissement.origineFonds, e.g.
                                                    "...prix stipulé de 40.000,00 EUR") but do NOT conflate this with
                                                    M&A/LBO share acquisitions — a fonds-de-commerce sale is an asset
                                                    deal, legally and economically distinct from buying a company's
                                                    equity. Useful as one input to the LBO-holding-company proxy, not
                                                    as a direct answer to "how many acquisitions" (B14).
    "Annonces diverses"                          - miscellaneous catch-all

  "Créations" (new incorporation) schema — CONFIRMED via two real
  examples:
    listepersonnes (JSON string) = {"personne": {"capital":
      {"montantCapital": <STRING, e.g. "3600" or "40000.00" - no
      currency formatting, parse as float>, "devise": "EUR"},
      "typePersonne": "pm", "denomination": ..., "formeJuridique": ...,
      "numeroImmatriculation": {...}, "adresseSiegeSocial": {...},
      "administration": <free text naming gérant/président/etc.>}}.
      NOTE: "capital" was present on both live examples but is likely
      absent for legal forms without share capital (EI, associations) -
      handle a missing capital key as "not applicable", not zero.
    acte (JSON string) = {"creation": {"categorieCreation": <free text,
      e.g. "Immatriculation d'une personne morale (B, C, D) suite à
      création d'un établissement principal">}, "dateImmatriculation":
      <ISO date>, "dateCommencementActivite": <ISO date>}
    listeetablissements (JSON string) = {"etablissement": {"activite":
      <FREE-TEXT sector description, not a NAF code>, "adresse": {...},
      "qualiteEtablissement": ..., "origineFonds": ...}}

  "Ventes et cessions" (fonds-de-commerce sale) schema — CONFIRMED via
  two real examples:
    acte (JSON string) = {"vente": {"categorieVente": <free text, e.g.
      "Achat d'un fonds par une personne morale (insertion
      provisoire)">, "dateEffet": <FRENCH TEXT date>, "publiciteLegale":
      {...}, "opposition": <free text>}, "dateImmatriculation": ...,
      "dateCommencementActivite": ...}
    listeetablissements.etablissement.origineFonds sometimes embeds the
      sale price as free text (e.g. "...prix stipulé de 40.000,00 EUR")
      - a regex extraction, not a structured field.
    listeprecedentproprietaire (JSON string) = the SELLER: {"personne":
      {"denomination"/"nom"+"prenom", "typePersonne": "pp"/"pm", ...}}
      — the buyer is in listepersonnes as usual.

  "Procédures collectives" (insolvency) schema — CONFIRMED via a real
  example (a "Jugement de conversion en liquidation judiciaire"):
    jugement (JSON string) = {"famille": "Jugement prononçant",
      "nature": <free-text judgment type, e.g. "Jugement de conversion
      en liquidation judiciaire">, "date": <FRENCH TEXT date, e.g.
      "10 décembre 2009" - NOT ISO format, needs French month-name
      parsing>, "complementJugement": <free text, often names the
      liquidator>, "type": "initial"}. NOTE: jugement.type ("initial")
      describes whether THIS BODACC NOTICE is a first publication (same
      axis as the outer typeavis_lib="Avis initial") — it does NOT tell
      you whether the underlying judgment itself is an opening
      proceeding vs. a later conversion/plan/clôture. That distinction
      is only in jugement.nature's free text, and only ONE example
      ("conversion en liquidation judiciaire") has been seen so far —
      the Data Room brief's own caveat ("an insolvency = an opening
      judgment; conversions... are not counted again") means
      bodacc_failures.py MUST classify jugement.nature (opening vs.
      conversion vs. plan vs. clôture) rather than counting every
      "Procédures collectives" row as a fresh failure. Expect more
      nature values to surface once real data is pulled at volume —
      classify defensively (a known-values dict + a loud warning for
      anything unrecognized), same pattern used for the Sirene
      NAFRev1/legal-form fixes elsewhere in this project.
    listepersonnes (JSON string) = {"personne": {"typePersonne": "pp" or
      "pm", "numeroImmatriculation": {"numeroIdentification": <SIREN,
      spaced>, ...}, "activite": <FREE-TEXT activity description, NOT a
      NAF code>, plus "nom"/"prenom" for a "pp" (personne physique) or
      "denomination"/"formeJuridique" for a "pm" (personne morale)}}.
      There is NO NAF/sector code anywhere on a BODACC record — sector
      breakdown requires cross-referencing extract_siren(record) against
      Sirene (src/company_creation/sirene_v3_client.py), not the free-
      text "activite" field.

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
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
PAGE_SIZE = 100  # Opendatasoft v2.1 max rows per page
SECONDS_BETWEEN_REQUESTS = 0.5
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 5

# CONFIRMED live (2026-09-05): this Opendatasoft Explore API v2.1 dataset
# hard-caps offset+limit at 10,000, exactly like the recherche-entreprises
# API this project already had to work around once for Sirene ("Invalid
# value for sum of offset + limit API parameter: 10100 was found but
# <= 10000 is expected"). A single fetch_all() call against a filter
# matching more than this WILL silently stop partway through - use
# fetch_all_bisecting()/fetch_and_cache_by_date_range() below instead of
# fetch_and_cache() for any query that might exceed it (in practice: any
# per-department, multi-year fetch - a department's full company-creation
# volume over 11 years is easily 60,000+ records).
MAX_SAFE_RECORDS_PER_QUERY = 9900  # small safety margin under the real 10,000 cap

GEOGRAPHY_FIELD = "numerodepartement"  # confirmed 2026-09-04, NOT "departement"

# Confirmed 2026-09-04 (scripts/bodacc_debug_mergers.py): merger/TUP
# notices live inside "Modifications diverses" with a short descriptif
# like "fusion" - ODSQL `like` substring-matches modificationsgenerales
# directly even though it's stored as escaped JSON. 15,541 national
# matches for "fusion" alone; "absorption"/"TUP" may overlap with it on
# the same record (a merger notice can mention more than one term), so
# OR them in one query rather than summing separate counts.
MERGER_WHERE_CLAUSE = (
    'familleavis_lib="Modifications diverses" AND '
    '(modificationsgenerales like "%fusion%" OR '
    'modificationsgenerales like "%absorption%" OR '
    'modificationsgenerales like "%TUP%")'
)

# Fields that come back as a JSON-ENCODED STRING (or null) rather than a
# real nested object — confirmed for listepersonnes/depot; the others
# are the same shape by consistent API design but not yet seen non-null.
JSON_STRING_FIELDS = [
    "listepersonnes", "listeetablissements", "jugement", "acte",
    "modificationsgenerales", "radiationaurcs", "depot",
    "listeprecedentexploitant", "listeprecedentproprietaire", "divers",
]


def extract_siren(record: dict) -> str | None:
    """
    Pull a clean 9-digit SIREN out of a record's `registre` field. The
    field holds the same SIREN twice (spaced and unspaced) but the
    ORDER IS NOT CONSISTENT between records (confirmed via two live
    examples with opposite ordering) — strip non-digits instead of
    trusting a fixed index.
    """
    registre = record.get("registre")
    if not registre:
        return None
    for value in registre:
        digits = "".join(c for c in str(value) if c.isdigit())
        if len(digits) == 9:
            return digits
    return None


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


def first_or_self(value):
    """
    CONFIRMED live (2026-09-05, via an AttributeError on a real
    "Créations" record): nested keys like
    listeetablissements.etablissement and listepersonnes.personne come
    back as a single dict when there's exactly one, but a LIST of dicts
    when there's more than one — a classic XML->JSON single-vs-array
    conversion quirk. Use this on the result of a
    parsed_field.get("etablissement")/.get("personne") call rather than
    assuming a dict: returns the first item for a non-empty list, the
    value unchanged if it's already a dict, or {} for anything else
    (None, empty list, empty dict).
    """
    if isinstance(value, list):
        return value[0] if value else {}
    if isinstance(value, dict):
        return value
    return {}


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


def fetch_all_bisecting(
    where_base: str, date_field: str, date_start: str, date_end: str,
    safe_limit: int = MAX_SAFE_RECORDS_PER_QUERY,
) -> tuple[list[dict], bool]:
    """
    Fetch every record matching `where_base` within [date_start, date_end]
    (ISO "YYYY-MM-DD" strings), recursively bisecting the date range
    whenever a sub-range's count exceeds MAX_SAFE_RECORDS_PER_QUERY — see
    that constant's comment for why this is necessary (this API hard-caps
    offset+limit at 10,000, confirmed live).

    Returns (records, complete). complete is False if ANY sub-window
    couldn't be fully fetched (a count_records() failure, or single-day
    volume that still exceeds the cap and can't be bisected further) —
    callers MUST check this before caching/trusting the result, exactly
    like sirene_v3_client.py's fetch_establishments().
    """
    where = f'{where_base} AND {date_field}>="{date_start}" AND {date_field}<="{date_end}"'
    total = count_records(where)

    if total is None:
        print(f"  count_records failed for {date_start}..{date_end} — this window is INCOMPLETE")
        return [], False
    if total == 0:
        return [], True

    if total <= safe_limit:
        print(f"  {total} record(s) in {date_start}..{date_end} (within the {safe_limit} cap, fetching directly)")
        return fetch_all(where), True

    start_dt = date.fromisoformat(date_start)
    end_dt = date.fromisoformat(date_end)

    if start_dt >= end_dt:
        print(f"  WARNING: {total} record(s) on a single day ({date_start}) exceed the "
              f"{safe_limit} cap and cannot be split further — fetching only the first "
              f"{safe_limit}, this day's data is INCOMPLETE.")
        return fetch_all(where, max_records=safe_limit), False

    mid_dt = start_dt + (end_dt - start_dt) // 2
    print(f"  {total} record(s) in {date_start}..{date_end} exceeds the {safe_limit} cap — "
          f"splitting at {mid_dt.isoformat()}")

    left_records, left_complete = fetch_all_bisecting(where_base, date_field, date_start, mid_dt.isoformat(), safe_limit)
    next_day = (mid_dt + timedelta(days=1)).isoformat()
    right_records, right_complete = fetch_all_bisecting(where_base, date_field, next_day, date_end, safe_limit)

    return left_records + right_records, (left_complete and right_complete)


def fetch_and_cache_by_date_range(
    where_base: str, date_field: str, date_start: str, date_end: str,
    cache_path: str, resume: bool = True,
) -> pd.DataFrame:
    """
    fetch_all_bisecting(), but cached to disk — the date-range-aware
    replacement for fetch_and_cache() that every per-department,
    multi-year fetch should use instead, since department-level BODACC
    volume over several years routinely exceeds the 10,000-record cap
    (confirmed: 66,067 "Créations" notices for Bas-Rhin alone,
    2015-2026). Only caches when the fetch is COMPLETE — an incomplete
    fetch (see fetch_all_bisecting's docstring) is never silently cached
    as if it were the full dataset; re-run to retry it.

        df = fetch_and_cache_by_date_range(
            'numerodepartement="67" AND familleavis_lib="Créations"',
            date_field="dateparution", date_start="2015-01-01", date_end="2026-12-31",
            cache_path="data/processed/bodacc_creations_dept_67.json",
        )
    """
    cache_file = Path(cache_path)
    if resume and cache_file.exists():
        print(f"Loading cached BODACC records from {cache_path} "
              f"(delete this file to force a refetch)")
        with open(cache_file, encoding="utf-8") as f:
            records = json.load(f)
        return pd.json_normalize(records)

    print(f"Fetching from BODACC (where: {where_base}, {date_start}..{date_end})...")
    records, complete = fetch_all_bisecting(where_base, date_field, date_start, date_end)

    if complete:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)
        print(f"Cached {len(records)} record(s) to {cache_path}")
    else:
        print(f"  NOT caching {cache_path} — this fetch was INCOMPLETE (hit the API's "
              f"{MAX_SAFE_RECORDS_PER_QUERY}-record safe cap on a window that couldn't be "
              f"split further, or a count_records() call failed partway through). Re-run "
              f"to retry — do NOT treat {len(records)} as the true total.")

    return pd.json_normalize(records)
