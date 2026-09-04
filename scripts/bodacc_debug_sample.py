"""
Run this FIRST, before trusting any BODACC-based script
(src/failures/bodacc_failures.py, src/mna/bodacc_mna.py, the LBO proxy).

It answers the two open questions blocking real field names in
src/common/bodacc_client.py:
  1. What do real records actually look like (field names, nesting)?
  2. What ODSQL field exposes department/geography, and does it work?
  3. What are the real familleavis_lib values (the taxonomy notices are
     grouped into) — needed to write a correct merger/insolvency filter?

Paste the full console output back so the where-clauses in
bodacc_failures.py / bodacc_mna.py / the LBO proxy can be calibrated to
what the API actually returns, instead of a best-guess.

Usage:
    python scripts/bodacc_debug_sample.py
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import bodacc_client as bc

GEOGRAPHY_FIELD_CANDIDATES = ["departement", "code_departement", "departement_lib"]


def main():
    print("=" * 70)
    print("STEP 1: unfiltered sample — confirms the raw record shape")
    print("=" * 70)
    bc.debug_sample(n=3)

    print("\n" + "=" * 70)
    print("STEP 2: does a geography field exist? trying candidates for Bas-Rhin (67)")
    print("=" * 70)
    working_field = None
    for field in GEOGRAPHY_FIELD_CANDIDATES:
        print(f"\nTrying where={field}=\"67\" ...")
        result = bc.debug_sample(where=f'{field}="67"', n=2)
        if result is not None and result.get("total_count", 0) > 0:
            print(f"  -> WORKS: field '{field}' returned {result['total_count']} total matches for dept 67")
            working_field = field
            break
        elif result is not None:
            print(f"  -> field name accepted but 0 matches (may be wrong value format, not wrong field)")

    if not working_field:
        print("\nNone of the candidate geography fields worked cleanly. Look at the "
              "STEP 1 raw JSON above for a field that looks like a department/region/"
              "tribunal code and try it manually via bc.debug_sample(where='...').")

    print("\n" + "=" * 70)
    print("STEP 3: familleavis_lib taxonomy — what notice categories exist")
    print("=" * 70)
    sample = bc.fetch_all(where="", max_records=100)
    if sample:
        counts = Counter(r.get("familleavis_lib", "(field not found)") for r in sample)
        print("\nDistinct familleavis_lib values seen in 100 recent records:")
        for label, count in counts.most_common():
            print(f"  {count:3d}  {label}")
    else:
        print("Could not fetch a sample for the taxonomy check.")

    print("\n" + "=" * 70)
    print("Paste all of the above back — it's enough to calibrate the real "
          "where-clauses for failures/mergers/LBO-proxy.")
    print("=" * 70)


if __name__ == "__main__":
    main()
