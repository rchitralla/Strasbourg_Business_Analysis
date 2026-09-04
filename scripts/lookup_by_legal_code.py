"""
Look up concrete company examples (SIREN, name, address) for a given set
of INSEE "catégorie juridique" (legal-form) codes, via the Sirene v3.11
API. Useful for spot-checking what an unusual/rare legal-form code
actually corresponds to in the real data (e.g. codes seen only a handful
of times in the company-creation dataset).

Unlike collect_all_departments() (which pulls every establishment
created in a date window), this is a targeted, bounded lookup: for each
code, fetch up to --max-per-code matching établissements and print their
SIREN + company name.

By default restricted to the project's 3 departments (Bas-Rhin/Haut-Rhin/
Moselle) to match where these codes were likely encountered. Pass
--national to search all of France instead (useful for very rare codes
that may have zero établissements in these 3 departments — e.g. a single
national "Service du ministère de la Défense" entry, or a foreign entity
code that by definition isn't tied to a French département).

NOTE ON FIELD NAMES: company_name is assembled by trying several possible
Sirene v3.11 uniteLegale fields in order (denominationUniteLegale,
sigleUniteLegale, then personne-physique nom/prénom fields as a
fallback), since these codes include some unusual categories (public
bodies, foreign entities) whose exact field usage hasn't been directly
confirmed against a live response from this project before. If
company_name comes back as "(no name field found)" for a hit, the script
also dumps that record's raw JSON to
outputs/tables/legal_form_lookup_raw_sample_<code>.json — inspect it and
adjust extract_company_details() below if a different field is populated.

Usage:
    python scripts/lookup_by_legal_code.py
    python scripts/lookup_by_legal_code.py --codes 2800,6901,5560 --max-per-code 20
    python scripts/lookup_by_legal_code.py --national
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.company_creation.sirene_v3_client import (
    SEARCH_ENDPOINT,
    LEGAL_FORM_LABELS,
    set_api_key,
    _headers,
    _get_with_retry,
    SECONDS_BETWEEN_REQUESTS,
)

DEFAULT_CODES = ["2800", "6901", "5560", "3220", "7379", "3290", "3110", "7150"]
DEFAULT_DEPARTMENTS = ("67", "68", "57")


def extract_company_details(record: dict, queried_code: str) -> dict:
    unite = record.get("uniteLegale") or {}

    denomination = (
        unite.get("denominationUniteLegale")
        or unite.get("denominationUsuelle1UniteLegale")
        or unite.get("sigleUniteLegale")
    )
    if not denomination:
        parts = [unite.get("prenom1UniteLegale"), unite.get("nomUniteLegale") or unite.get("nomUsageUniteLegale")]
        denomination = " ".join(p for p in parts if p) or None

    adresse = record.get("adresseEtablissement") or {}

    return {
        "queried_legal_form_code": queried_code,
        "queried_legal_form_label": LEGAL_FORM_LABELS.get(queried_code, "(not in nomenclature)"),
        "siren": record.get("siren") or unite.get("siren"),
        "siret": record.get("siret"),
        "company_name": denomination or "(no name field found - see raw JSON dump)",
        "legal_form_code_actual": unite.get("categorieJuridiqueUniteLegale"),
        "commune": adresse.get("libelleCommuneEtablissement"),
        "code_postal": adresse.get("codePostalEtablissement"),
        "date_creation_etablissement": record.get("dateCreationEtablissement"),
        "etat_administratif_etablissement": record.get("etatAdministratifEtablissement"),
    }


def fetch_by_legal_form(code: str, departments=DEFAULT_DEPARTMENTS, max_per_code: int = 25) -> tuple[list[dict], int | None]:
    query = f"categorieJuridiqueUniteLegale:{code}"
    if departments:
        dept_query = " OR ".join(f"codeCommuneEtablissement:{d}*" for d in departments)
        query = f"({query}) AND ({dept_query})"

    params = {"q": query, "curseur": "*", "nombre": min(max_per_code, 1000)}
    response = _get_with_retry(SEARCH_ENDPOINT, params, _headers(), timeout=30)

    if response.status_code != 200:
        print(f"  HTTP {response.status_code} for code {code}: {response.text[:300]}")
        return [], None

    payload = response.json()
    results = payload.get("etablissements", [])
    total = payload.get("header", {}).get("total")
    return results, total


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codes", default=",".join(DEFAULT_CODES),
                         help="Comma-separated legal-form codes to look up.")
    parser.add_argument("--max-per-code", type=int, default=25,
                         help="Max établissements to fetch per code (default 25).")
    parser.add_argument("--national", action="store_true",
                         help="Search all of France instead of restricting to Bas-Rhin/Haut-Rhin/Moselle.")
    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    departments = None if args.national else DEFAULT_DEPARTMENTS

    set_api_key()

    Path("outputs/tables").mkdir(parents=True, exist_ok=True)
    all_rows = []

    for i, code in enumerate(codes):
        label = LEGAL_FORM_LABELS.get(code, "(code not in official nomenclature)")
        scope = "nationally" if departments is None else f"in {'/'.join(departments)}"
        print(f"\nCode {code} — {label} — searching {scope}...")

        results, total = fetch_by_legal_form(code, departments, args.max_per_code)
        print(f"  Total matching établissements {scope}: "
              f"{total if total is not None else 'unknown (request failed)'} "
              f"(fetched {len(results)})")

        if results and not extract_company_details(results[0], code)["company_name"].startswith("("):
            pass  # name resolved fine, no need to dump raw JSON
        elif results:
            dump_path = f"outputs/tables/legal_form_lookup_raw_sample_{code}.json"
            with open(dump_path, "w", encoding="utf-8") as f:
                json.dump(results[0], f, indent=2, ensure_ascii=False)
            print(f"  NOTE: company_name field not resolved for this code — "
                  f"raw sample record dumped to {dump_path} for inspection.")

        for record in results:
            all_rows.append(extract_company_details(record, code))

        if i < len(codes) - 1:
            time.sleep(SECONDS_BETWEEN_REQUESTS)

    if not all_rows:
        print("\nNo results for any code.")
        return

    import pandas as pd
    df = pd.DataFrame(all_rows)
    out_path = "outputs/tables/legal_form_lookup_examples.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df)} company record(s) to {out_path}")
    print(df[["queried_legal_form_code", "siren", "company_name", "commune"]].to_string(index=False))


if __name__ == "__main__":
    main()
