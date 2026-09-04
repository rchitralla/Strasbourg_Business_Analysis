"""
Run this FIRST, before trusting src/common/sirene_lookup.py at volume.

Tests the `q=siren:{siren}` query pattern against the Sirene v3.11 API
on a few known real SIRENs already seen in this project's live data
(the FIRALIS merger example, the NEWCO holding example) — confirms the
field name works and prints what comes back, so lookup_siren()'s
extraction logic can be corrected if the response shape differs from
what fetch_establishments() already assumes.

Usage:
    python scripts/debug_sirene_lookup.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.company_creation import sirene_v3_client as sv3
from src.common import sirene_lookup as sl

# Real SIRENs already confirmed to exist from earlier live debug runs
# this session (FIRALIS merger example, NEWCO holding example).
KNOWN_SIRENS = ["504944364", "538019670"]


def main():
    sv3.set_api_key()

    for siren in KNOWN_SIRENS:
        print("=" * 70)
        print(f"SIREN: {siren}")
        print("=" * 70)
        params = {"q": f"siren:{siren}", "nombre": 1}
        import requests
        response = requests.get(sv3.SEARCH_ENDPOINT, params=params, headers=sv3._headers(), timeout=30)
        print(f"HTTP {response.status_code}")
        if response.status_code != 200:
            print(response.text[:1000])
            continue

        payload = response.json()
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])

        extracted = sl.lookup_siren(siren)
        print(f"\nExtracted: {extracted}")

    print("\nPaste the above back — confirms whether `q=siren:X` works and "
          "whether the extracted naf_code/sector/legal_form look right.")


if __name__ == "__main__":
    main()
