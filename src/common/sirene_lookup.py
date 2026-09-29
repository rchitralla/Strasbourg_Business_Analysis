"""
Single-SIREN lookup against the Sirene v3.11 API, for enriching BODACC
data (which has NO NAF/sector code at all — only free text) with a real
NAF section, legal form, and current denomination.

Reuses src/company_creation/sirene_v3_client.py's auth, retry, and
rate-limiting entirely rather than duplicating it — call
sv3.set_api_key() before using this module, exactly as for
sirene_v3_client.py itself.

QUERY PATTERN NOT YET CONFIRMED LIVE: this queries the same
SEARCH_ENDPOINT (/siret) sirene_v3_client.py already uses successfully,
with `q=siren:{siren}` — following the identical Lucene-style
field:value syntax already proven to work for
`codeCommuneEtablissement:X*` there, but this specific field
("siren") has not been directly confirmed against a live response.
Run scripts/debug_sirene_lookup.py FIRST on one known real SIREN
before trusting this at volume.

COST WARNING: the Sirene public plan is rate-limited to 30 req/min
(2.1s between requests, same constant as sirene_v3_client.py). Looking
up thousands of unique SIRENs found across the BODACC datasets
(failures/mergers/share-capital/LBO-proxy) will take real time — e.g.
5,000 SIRENs ≈ 3 hours. lookup_sirens_cached() saves progress to disk
every 20 lookups specifically so an interrupted run doesn't lose
already-completed work; re-running picks up where it left off.

Usage:
    from src.company_creation import sirene_v3_client as sv3
    from src.common import sirene_lookup as sl
    sv3.set_api_key()

    enriched_df = sl.enrich_with_sector(failures_df, siren_col="siren")
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.company_creation import sirene_v3_client as sv3

DEFAULT_CACHE_PATH = "data/manual/sirene_lookup_cache.json"


def _extract_from_record(record: dict) -> dict:
    unite = record.get("uniteLegale") or {}

    naf_code = record.get("activitePrincipaleEtablissement") or unite.get("activitePrincipaleUniteLegale")
    nomenclature = record.get("nomenclatureActivitePrincipaleEtablissement") or unite.get(
        "nomenclatureActivitePrincipaleUniteLegale"
    )
    if nomenclature == "NAFRev2":
        section = sv3.naf_code_to_section(naf_code)
        sector = sv3.NAF_WZ_SECTION_LABELS.get(section, "Unknown / unclassified")
    else:
        sector = f"Unknown / unclassified ({nomenclature or 'no nomenclature'})"

    legal_form_code_raw = unite.get("categorieJuridiqueUniteLegale")
    legal_form_code = str(legal_form_code_raw) if legal_form_code_raw else None

    return {
        "naf_code": naf_code,
        "sector": sector,
        "legal_form_code": legal_form_code,
        "legal_form_label": sv3.LEGAL_FORM_LABELS.get(legal_form_code) if legal_form_code else None,
        "denomination": unite.get("denominationUniteLegale"),
        "date_creation": unite.get("dateCreationUniteLegale"),  # full ISO date, NOT truncated to year
    }


def lookup_siren(siren: str) -> dict | None:
    """
    Look up ONE SIREN. Returns None if not found or the request fails —
    callers should treat None as "no data available", not "error", since
    a genuinely deregistered/very old company may not resolve.

    Filters to etablissementSiege:true — a SIREN with multiple
    établissements (branches/secondary sites) would otherwise return an
    arbitrary one via results[0], and activitePrincipaleEtablissement is
    an ESTABLISHMENT-level field that can genuinely differ between a
    company's sites (e.g. a HQ office vs. a warehouse). Without this
    filter, "sector" here could silently reflect a random branch instead
    of the head office — the same établissement-vs-enterprise ambiguity
    already confirmed live to matter in sirene_v3_client.py (see
    ENTERPRISE_ONLY_FILTER there), applied here before this module gets
    used at volume rather than after finding it the hard way again.
    """
    # CONFIRMED live (2026-09-05): omitting `curseur` causes an HTTP 400
    # with an empty body on this endpoint — every other working call in
    # sirene_v3_client.py always includes it, even for a single-record
    # lookup. Not optional on this API version.
    params = {"q": f"siren:{siren} AND {sv3.ENTERPRISE_ONLY_FILTER}", "curseur": "*", "nombre": 1}
    response = sv3._get_with_retry(sv3.SEARCH_ENDPOINT, params, sv3._headers(), timeout=30)
    if response.status_code != 200:
        print(f"  lookup_siren({siren}) failed: HTTP {response.status_code}: {response.text[:200]}")
        return None
    results = response.json().get("etablissements", [])
    if not results:
        return None
    return _extract_from_record(results[0])


def lookup_sirens_cached(sirens: list[str], cache_path: str = DEFAULT_CACHE_PATH) -> pd.DataFrame:
    """
    Look up every unique SIREN in `sirens`, cached to disk permanently
    (a SIREN's legal form/NAF code essentially never changes, unlike the
    date-scoped BODACC caches). Progress is saved every 20 lookups so an
    interrupted run (Ctrl-C, kernel restart, network drop) doesn't lose
    completed work — just re-run with the same list and it picks up
    where it left off.

    SCHEMA CHANGE (2026-09-21): _extract_from_record() now also returns
    date_creation. A cache file populated BEFORE this change has entries
    that simply lack that key — .get("date_creation") on those returns
    None silently, NOT an error, so a pre-existing cache will look
    "complete" while quietly missing creation dates for every SIREN
    looked up before today. If you're computing lifespan-at-closure (see
    bodacc_failures.compute_closure_lifespan()) and get suspiciously many
    missing dates, delete data/manual/sirene_lookup_cache.json and
    re-run — a full re-fetch is the only fix, there's no way to detect
    "old cache entry" vs "genuinely no creation date on this record"
    from the cached dict alone.
    """
    cache_file = Path(cache_path)
    cache = {}
    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            cache = json.load(f)

    unique_sirens = sorted({s for s in sirens if s})
    missing = [s for s in unique_sirens if s not in cache]
    print(f"{len(unique_sirens)} unique SIREN(s) requested, {len(missing)} not yet cached "
          f"({len(unique_sirens) - len(missing)} already cached).")

    if missing:
        est_minutes = len(missing) * sv3.SECONDS_BETWEEN_REQUESTS / 60
        print(f"Looking up {len(missing)} SIREN(s) at ~{sv3.SECONDS_BETWEEN_REQUESTS}s each "
              f"(~{est_minutes:.1f} min). Progress is saved every 20 lookups — "
              f"safe to interrupt and re-run.")

    for i, siren in enumerate(missing, 1):
        cache[siren] = lookup_siren(siren)  # None is a valid cached "not found" result
        if i % 20 == 0 or i == len(missing):
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            print(f"  Looked up {i}/{len(missing)}, progress saved.")
        time.sleep(sv3.SECONDS_BETWEEN_REQUESTS)

    rows = []
    for siren in unique_sirens:
        result = cache.get(siren) or {}
        rows.append({
            "siren": siren,
            "naf_code": result.get("naf_code"),
            "sector": result.get("sector"),
            "legal_form_code": result.get("legal_form_code"),
            "legal_form_label": result.get("legal_form_label"),
            "denomination": result.get("denomination"),
            "date_creation": result.get("date_creation"),
        })
    return pd.DataFrame(rows)


def enrich_with_sector(df: pd.DataFrame, siren_col: str = "siren", cache_path: str = DEFAULT_CACHE_PATH) -> pd.DataFrame:
    """
    Adds naf_code/sector/legal_form_code/legal_form_label/denomination
    columns to any BODACC-derived DataFrame (failures, mergers,
    share_capital, LBO-proxy) by looking up each unique SIREN against
    Sirene. Requires sv3.set_api_key() to have been called first.
    """
    if df.empty:
        return df
    lookup_df = lookup_sirens_cached(df[siren_col].dropna().tolist(), cache_path=cache_path)
    return df.merge(lookup_df, on=siren_col, how="left")
