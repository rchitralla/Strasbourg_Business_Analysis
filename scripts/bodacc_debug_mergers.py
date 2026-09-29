"""
Tests whether merger/fusion notices can be found inside the
"Modifications diverses" family via a substring search on the
modificationsgenerales field's descriptif text.

Round 3 (scripts/bodacc_debug_round3.py) confirmed "Modifications
diverses" is a broad catch-all (capital changes, legal-form
transformations, etc.) with no dedicated "Fusions" family anywhere in
the confirmed taxonomy. Since modificationsgenerales is stored as a
plain text field internally (even though it happens to contain
escaped JSON), an ODSQL `like` filter should be able to substring-match
it directly — this script tests that hypothesis with a few candidate
terms before src/mna/bodacc_mna.py commits to a real where-clause.

If `like` on this field 400s or returns nothing, the fallback is to
pull a larger unfiltered "Modifications diverses" sample and filter
client-side on the raw JSON string for "fusion"/"absorption" — slower
but guaranteed to work regardless of ODSQL's exact text-search support.

Paste the full output back.

Usage:
    python scripts/bodacc_debug_mergers.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import bodacc_client as bc

CANDIDATE_TERMS = ["fusion", "Fusion", "absorption", "Absorption", "TUP"]


def try_odsql_like():
    print("=" * 70)
    print("Testing ODSQL `like` on modificationsgenerales for merger-related terms")
    print("=" * 70)
    for term in CANDIDATE_TERMS:
        where = f'familleavis_lib="Modifications diverses" AND modificationsgenerales like "%{term}%"'
        total = bc.count_records(where)
        print(f'  like "%{term}%" -> {total} total matches' if total is not None else
              f'  like "%{term}%" -> query failed (see debug_sample for the raw error)')

    print("\nIf any of the above returned a nonzero total, pull one real example:")
    for term in CANDIDATE_TERMS:
        where = f'familleavis_lib="Modifications diverses" AND modificationsgenerales like "%{term}%"'
        total = bc.count_records(where)
        if total:
            print(f"\nExample for term '{term}':")
            bc.debug_sample(where=where, n=1)
            return True
    return False


def fallback_client_side_scan():
    print("\n" + "=" * 70)
    print("FALLBACK: client-side scan of 300 'Modifications diverses' records "
          "for 'fusion'/'absorption' in the raw modificationsgenerales text")
    print("=" * 70)
    records = bc.fetch_all('familleavis_lib="Modifications diverses"', max_records=300)
    hits = [
        r for r in records
        if r.get("modificationsgenerales") and
        any(term.lower() in r["modificationsgenerales"].lower() for term in ["fusion", "absorption"])
    ]
    print(f"\n{len(hits)} / {len(records)} sampled records mention fusion/absorption.")
    if hits:
        import json
        print("\nFirst match's modificationsgenerales:")
        print(json.dumps(bc.parse_json_field(hits[0]["modificationsgenerales"]), indent=2, ensure_ascii=False))


def main():
    found = try_odsql_like()
    if not found:
        fallback_client_side_scan()
    print("\nPaste all of the above back.")


if __name__ == "__main__":
    main()
