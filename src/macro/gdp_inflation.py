"""
Macro-economy axis — GDP, inflation (Data Room questions B7-B9).

STATUS: exploration/discovery step, NOT a finished pipeline. Unlike
company_creation's Sirene v3 client or BODACC (both proven against live
responses), this module's data sources have not been searched or
fetched live yet — the functions here find and inspect the right
series/tables first, mirroring how every other axis in this project
started (debug_sample() / inspect_table_metadata() before trusting any
tidy_dataframe()).

Questions this covers:
  B7 - GDP and inflation evolution, last 3 years, per department
       (Bas-Rhin, Haut-Rhin, Moselle) vs national average vs
       Baden-Württemberg.
  B9 - Corporate failure rates by sector, same comparison
       (see src/failures/ — already built, BODACC-based).
B8 (FDI) is intentionally NOT addressed here — see the note at the
bottom of this file.

STRUCTURAL CONSTRAINT (true for both countries, not a bug to fix):
INSEE does not publish official GDP at the DEPARTMENT level — the
finest granularity for GDP itself is the REGION (Grand Est, which
contains Bas-Rhin/Haut-Rhin/Moselle among other departments). Likewise
Destatis's regional-accounts GDP is published at Land (state) level.
So this axis is necessarily a REGION-vs-region comparison (Grand Est
vs. France vs. Baden-Württemberg), not the department-level view the
other axes achieve — flag this explicitly on the slide.

--------------------------------------------------------------------
GERMAN SIDE — Baden-Württemberg GDP (more tractable: reuses the proven
GENESIS client from germany_registrations.py, same POST/header-auth
plumbing, same bw.set_credentials()).

EVAS 82* is the "Volkswirtschaftliche Gesamtrechnungen der Länder"
(VGRdL — regional accounts) statistic family — this project has NOT
yet confirmed the exact EVAS code or table code live. search_statistics()
below does a keyword search; search_statistics_by_prefix() lists every
statistic starting "82" as a fallback/cross-check. Run one or both,
then inspect_table_metadata() (imported from germany_registrations.py)
on whatever table looks right, exactly like the 52311/52111 workflow.

UNVERIFIED: find/find is documented as a general keyword-search
endpoint in the GENESIS-Online REST API, but this project has not
called it live yet (only catalogue/tables2statistic and metadata/table
have been confirmed working, both POST). If it 404s/405s, fall back to
search_statistics_by_prefix() instead.

--------------------------------------------------------------------
FRENCH SIDE — Grand Est / France GDP & CPI, via INSEE's BDM (Banque de
Données Macroéconomiques) time-series API.

This is a GENUINELY HARDER discovery problem than Sirene: BDM does not
have a reliable keyword-search endpoint the way GENESIS's catalogue
does, so finding the right "idbank" (series identifier) for "PIB Grand
Est" or "IPC Grand Est" is mostly done by BROWSING insee.fr, not by
scripting a search. Manual steps:
  1. Go to https://www.insee.fr/fr/statistiques and search
     "Produit intérieur brut régional" (or "comptes régionaux").
  2. Open the relevant série chronologique page for Grand Est — the
     URL or the page's "Télécharger (csv)" export contains the idbank
     (an alphanumeric code, e.g. "001694113" style).
  3. Repeat for France entière GDP, and for the CPI ("indice des prix
     à la consommation") series for Grand Est + France.
  4. Call fetch_bdm_series(idbank) with each one found.

fetch_bdm_series() uses the same api.insee.fr key-header auth as
Sirene v3 (X-INSEE-Api-Key-Integration) — set it via set_api_key()
below (kept independent from sirene_v3_client's key in case the two
APIs need separate subscriptions on the same INSEE portal account).
debug_series_raw() prints the raw response FIRST — the SDMX-JSON shape
this module assumes (dataSets[0].series[...].observations +
structure.dimensions.observation[0].values for time labels) is a
best-effort guess from general SDMX-JSON conventions, not confirmed
against a real response from this API.

FDI (B8): no clean department- or region-level API exists for this at
all (Banque de France publishes FDI stocks/flows nationally only).
The Data Room brief itself flags this as desk-research territory, not
an API pull — track manually sourced figures in data/manual/fdi.csv
with a Source column per row, following the same manual-CSV pattern as
src/lbo/lbo_manual.py, rather than building a fetcher here.

Requirements:
    pip install requests pandas
"""

import sys
from getpass import getpass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.company_creation.germany_registrations import _post, inspect_table_metadata  # noqa: F401 (re-exported)

# ---------------------------------------------------------------------------
# German side — Baden-Württemberg GDP (VGR der Länder)
# ---------------------------------------------------------------------------

CANDIDATE_EVAS_PREFIX = "82"  # Volkswirtschaftliche Gesamtrechnungen der Länder


def search_statistics_by_keyword(term: str = "Bruttoinlandsprodukt"):
    """
    UNVERIFIED endpoint (find/find) — try this first. If it errors,
    use search_statistics_by_prefix() instead; either way, inspect
    whatever table code looks right with
    germany_registrations.inspect_table_metadata() before trusting it.
    """
    response = _post("find/find", {
        "term": term,
        "category": "statistics",
        "pagelength": 50,
        "language": "de",
    })
    print(f"HTTP {response.status_code}")
    if response.status_code != 200:
        print(response.text[:1000])
        print("\nfind/find failed — try search_statistics_by_prefix() instead.")
        return None
    payload = response.json()
    print(payload)
    return payload


def search_statistics_by_prefix(prefix: str = CANDIDATE_EVAS_PREFIX):
    """
    Fallback/cross-check for search_statistics_by_keyword(): lists every
    statistic whose EVAS code starts with `prefix` via
    catalogue/statistics (the same catalogue/* family already confirmed
    working — POST — in germany_registrations.py), using GENESIS's
    wildcard selection syntax.
    """
    response = _post("catalogue/statistics", {
        "selection": f"{prefix}*",
        "pagelength": 100,
        "language": "de",
    })
    response.raise_for_status()
    payload = response.json()
    stats = payload.get("List", [])
    print(f"Found {len(stats)} statistic(s) starting with '{prefix}':\n")
    for s in stats:
        print(f"  {s.get('Code', '?'):10s} {s.get('Content', '?')}")
    return stats


# ---------------------------------------------------------------------------
# French side — Grand Est / France GDP & CPI via INSEE BDM
# ---------------------------------------------------------------------------

BDM_BASE_URL = "https://api.insee.fr/series/BDM/V1"

_BDM_API_KEY = None


def set_api_key(key: str = None):
    """
    Set the INSEE API key for BDM series requests. Kept independent
    from sirene_v3_client's key — even though both APIs sit behind the
    same api.insee.fr portal, INSEE historically requires subscribing
    to each API separately, so the same key may or may not work here;
    verify with debug_series_raw() before assuming it does.
    """
    global _BDM_API_KEY
    _BDM_API_KEY = key if key is not None else getpass("INSEE API key (for BDM series): ")
    print("API key set for this session.")


def _bdm_headers():
    if not _BDM_API_KEY:
        raise RuntimeError("Call set_api_key() first.")
    return {"X-INSEE-Api-Key-Integration": _BDM_API_KEY, "Accept": "application/json"}


def debug_series_raw(idbank: str):
    """
    Fetch ONE series by idbank and print the raw JSON response.
    Run this FIRST for every idbank found via the manual insee.fr
    browsing steps in the module docstring — confirms both that the
    idbank is correct AND that parse_bdm_series()'s SDMX-JSON field
    guesses below actually match a real response, before trusting them.
    """
    import json

    url = f"{BDM_BASE_URL}/data/SERIES_BDM/{idbank}"
    response = requests.get(url, headers=_bdm_headers(), timeout=30)
    print(f"HTTP {response.status_code}")
    if response.status_code != 200:
        print(response.text[:1000])
        return None
    payload = response.json()
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
    return payload


def parse_bdm_series(payload: dict) -> "pd.DataFrame":
    """
    UNVERIFIED — a best-effort parse of standard SDMX-JSON shape
    (dataSets[0].series[<key>].observations = {index: [value, ...]},
    structure.dimensions.observation[0].values[index].id = time label).
    Run debug_series_raw() first and compare its printed structure
    against this before trusting the output — SDMX-JSON has enough
    real-world variation (dimension ordering, attribute placement) that
    guessing this blind is exactly the kind of mistake this project has
    hit before (see germany_registrations.py's GEWNW1 correction).
    """
    import pandas as pd

    try:
        time_values = payload["structure"]["dimensions"]["observation"][0]["values"]
        series_dict = payload["dataSets"][0]["series"]
        series_key = next(iter(series_dict))
        observations = series_dict[series_key]["observations"]
    except (KeyError, IndexError, StopIteration) as e:
        raise KeyError(
            f"SDMX-JSON structure didn't match the expected shape ({e}). "
            "Run debug_series_raw() and update parse_bdm_series() to match "
            "the real response."
        )

    rows = []
    for obs_index_str, obs_value in observations.items():
        obs_index = int(obs_index_str)
        period = time_values[obs_index]["id"]
        value = obs_value[0] if isinstance(obs_value, list) else obs_value
        rows.append({"period": period, "value": value})

    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)


def fetch_bdm_series(idbank: str) -> "pd.DataFrame":
    """Fetch + parse one BDM series in one call. See debug_series_raw()/parse_bdm_series()."""
    payload = debug_series_raw(idbank)
    if payload is None:
        raise RuntimeError(f"Failed to fetch series {idbank}.")
    return parse_bdm_series(payload)


# ---------------------------------------------------------------------------
# TODO once the discovery steps above have been run and pasted back:
#   1. Confirm the right EVAS/table code for Baden-Württemberg GDP and
#      call inspect_table_metadata() + fetch_and_parse_table()-equivalent
#      (reuse germany_registrations.fetch_and_parse_table() directly if
#      the table shape matches — same ffcsv format).
#   2. Confirm 2-3 real idbanks (Grand Est GDP, France GDP, Grand Est
#      CPI, France CPI) via the manual insee.fr steps + debug_series_raw().
#   3. Build a tidy_dataframe() combining both sides into (year, region,
#      metric, value), matching the shape src.common.plotting.grouped_region_bar()
#      expects.
#   4. FDI (B8): manual data/manual/fdi.csv, not scripted — see docstring.
# ---------------------------------------------------------------------------
