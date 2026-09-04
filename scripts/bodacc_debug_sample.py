"""
Second-round BODACC calibration. Round 1 (this file's earlier version)
already confirmed:
  - geography field is `numerodepartement` (2-digit string), not "departement"
  - familleavis/familleavis_lib categorize notices (e.g. "dpc" / "Dépôts
    des comptes")
  - a plain 100-record UNFILTERED sample is dominated entirely by
    "Dépôts des comptes" (annual account filings happen every year for
    every company, swamping rarer notice types like mergers or
    insolvencies) — so that approach can't discover the full taxonomy.

This version:
  1. Confirms numerodepartement filtering actually works for Bas-Rhin/
     Haut-Rhin/Moselle (67/68/57) and prints each department's total
     notice count.
  2. Discovers the REST of the familleavis_lib taxonomy by repeatedly
     excluding families already seen (WHERE familleavis_lib NOT IN (...))
     — guaranteed to surface rarer families instead of just re-sampling
     "Dépôts des comptes" over and over.
  3. Once a non-"Dépôts des comptes" family is found, pulls one real
     example and prints which nested field (jugement,
     modificationsgenerales, etc.) is actually populated for it — this
     is what src/failures/bodacc_failures.py and src/mna/bodacc_mna.py
     need to extract real data.

Paste the full output back.

Usage:
    python scripts/bodacc_debug_sample.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import bodacc_client as bc

DEPARTMENTS = {"67": "Bas-Rhin", "68": "Haut-Rhin", "57": "Moselle"}
MAX_DISCOVERY_ROUNDS = 6
RECORDS_PER_ROUND = 100


def confirm_geography():
    print("=" * 70)
    print("STEP 1: confirm numerodepartement filtering for the 3 departments")
    print("=" * 70)
    for code, name in DEPARTMENTS.items():
        total = bc.count_records(f'{bc.GEOGRAPHY_FIELD}="{code}"')
        print(f"  {code} ({name}): {total} total notices")


def discover_family_taxonomy():
    print("\n" + "=" * 70)
    print("STEP 2: discover the full familleavis_lib taxonomy "
          "(excluding families already seen, round by round)")
    print("=" * 70)

    seen_counts = {}
    for round_num in range(1, MAX_DISCOVERY_ROUNDS + 1):
        if seen_counts:
            exclusions = " AND ".join(f'familleavis_lib!="{label}"' for label in seen_counts)
            where = exclusions
        else:
            where = ""

        print(f"\nRound {round_num} (excluding {len(seen_counts)} already-seen "
              f"famil{'y' if len(seen_counts) == 1 else 'ies'})...")
        records = bc.fetch_all(where, max_records=RECORDS_PER_ROUND)
        if not records:
            print("  No more records found — taxonomy discovery complete.")
            break

        new_labels = set()
        for r in records:
            label = r.get("familleavis_lib", "(field not found)")
            if label not in seen_counts:
                new_labels.add(label)
            seen_counts[label] = seen_counts.get(label, 0) + 1

        if not new_labels:
            print("  No NEW families surfaced this round — likely have the full taxonomy.")
            break
        print(f"  New famil{'y' if len(new_labels) == 1 else 'ies'} found: {sorted(new_labels)}")

    print("\nFull familleavis_lib taxonomy discovered so far "
          "(count = how many times seen across all discovery rounds, NOT a real national total):")
    for label, count in sorted(seen_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {label}")

    return seen_counts


def inspect_non_default_family(seen_counts: dict):
    non_default = [label for label in seen_counts if label != "Dépôts des comptes"]
    if not non_default:
        print("\nNo non-'Dépôts des comptes' family found yet — try increasing "
              "MAX_DISCOVERY_ROUNDS or RECORDS_PER_ROUND.")
        return

    target = non_default[0]
    print("\n" + "=" * 70)
    print(f"STEP 3: inspect one real example of '{target}' — which nested "
          f"field is populated?")
    print("=" * 70)
    payload = bc.debug_sample(where=f'familleavis_lib="{target}"', n=1)
    if not payload or not payload.get("results"):
        return

    record = payload["results"][0]
    for field in bc.JSON_STRING_FIELDS:
        value = record.get(field)
        if value:
            print(f"\n  Field '{field}' is populated for this family. Parsed content:")
            import json as _json
            print(_json.dumps(bc.parse_json_field(value), indent=2, ensure_ascii=False)[:2000])


def main():
    confirm_geography()
    seen_counts = discover_family_taxonomy()
    inspect_non_default_family(seen_counts)
    print("\n" + "=" * 70)
    print("Paste all of the above back.")
    print("=" * 70)


if __name__ == "__main__":
    main()
