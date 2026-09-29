"""
Third-round BODACC calibration — targeted, now that round 2 confirmed
the full familleavis_lib taxonomy (see src/common/bodacc_client.py's
docstring) and the "Procédures collectives" (insolvency) schema in full.

Three families are still unexplored and each matters for a different
Data Room question:
  - "Modifications diverses" - likely holds merger/TUP notices (B13)
  - "Créations"              - likely holds share capital at
                                incorporation (average-capital question)
  - "Ventes et cessions"     - the acquisitions (B14) / LBO-proxy signal

This just pulls 2 real examples of each and prints which nested field is
populated and what it contains — cheap (6 records total), and avoids
guessing field content wrong before building real extraction logic
(same lesson as the earlier Sirene legal-form correction).

Paste the full output back.

Usage:
    python scripts/bodacc_debug_round3.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import bodacc_client as bc

TARGET_FAMILIES = ["Modifications diverses", "Créations", "Ventes et cessions"]


def inspect_family(label: str):
    print("=" * 70)
    print(f"Family: {label}")
    print("=" * 70)
    payload = bc.debug_sample(where=f'familleavis_lib="{label}"', n=2)
    if not payload or not payload.get("results"):
        print("  No results / request failed.")
        return

    for i, record in enumerate(payload["results"], 1):
        print(f"\n  --- Example {i} ---")
        print(f"  numerodepartement: {record.get('numerodepartement')}, "
              f"commercant: {record.get('commercant')}, "
              f"siren: {bc.extract_siren(record)}")
        populated = [f for f in bc.JSON_STRING_FIELDS if record.get(f)]
        print(f"  Populated nested field(s): {populated}")
        for field in populated:
            parsed = bc.parse_json_field(record[field])
            print(f"\n  {field}:")
            print(json.dumps(parsed, indent=2, ensure_ascii=False)[:2000])
    print()


def main():
    for label in TARGET_FAMILIES:
        inspect_family(label)
    print("Paste all of the above back.")


if __name__ == "__main__":
    main()
