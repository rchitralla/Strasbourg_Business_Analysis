"""
Tests whether NAF 6420Z-style holding-company formations are findable
inside "Créations" notices via a substring search on
listeetablissements's activite text — BODACC has NO NAF code field
(confirmed in src/common/bodacc_client.py's docstring), so a holding-
company proxy for the LBO axis (B24) has to identify them by activity
DESCRIPTION instead, the same way scripts/bodacc_debug_mergers.py found
mergers via free-text search rather than a dedicated category.

Standard French phrasing for NAF 6420Z ("Activités des sociétés
holding") includes "holding", "prise de participations", "portefeuille
de valeurs mobilières" / "portefeuille de participations" — this script
tests each as a candidate `like` filter on listeetablissements (the
JSON-string field is a valid text-search target the same way
modificationsgenerales was for mergers).

Paste the full output back before src/lbo/ commits to a real filter.

Usage:
    python scripts/bodacc_debug_lbo_proxy.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import bodacc_client as bc

CANDIDATE_TERMS = [
    "holding",
    "Holding",
    "prise de participations",
    "portefeuille de valeurs mobilières",
    "portefeuille de participations",
    "gestion de participations",
]


def main():
    print("=" * 70)
    print("Testing `like` on listeetablissements for holding-company language "
          "(within familleavis_lib=\"Créations\")")
    print("=" * 70)

    found_any = False
    for term in CANDIDATE_TERMS:
        where = f'familleavis_lib="Créations" AND listeetablissements like "%{term}%"'
        total = bc.count_records(where)
        print(f'  like "%{term}%" -> {total} total matches' if total is not None else
              f'  like "%{term}%" -> query failed')
        if total:
            found_any = True

    if not found_any:
        print("\nNo candidate term matched anything - the activite text may use "
              "different phrasing, or holding-company creations may not be "
              "distinguishable this way at all. Try debug_sample() manually on "
              "a few 'Créations' records with a known holding company's SIREN "
              "to see the real activite wording.")
        return

    print("\nPulling one real example per term that matched:")
    for term in CANDIDATE_TERMS:
        where = f'familleavis_lib="Créations" AND listeetablissements like "%{term}%"'
        total = bc.count_records(where)
        if total:
            print(f"\n--- Term: '{term}' ({total} total matches) ---")
            bc.debug_sample(where=where, n=1)

    print("\nAlso testing scoped to the 3 project departments (67/68/57) "
          "to see realistic per-department volume:")
    for dept in ["67", "68", "57"]:
        for term in ["holding", "prise de participations"]:
            where = (f'familleavis_lib="Créations" AND {bc.GEOGRAPHY_FIELD}="{dept}" '
                      f'AND listeetablissements like "%{term}%"')
            total = bc.count_records(where)
            print(f'  dept {dept}, "%{term}%" -> {total} total matches')

    print("\nPaste all of the above back.")


if __name__ == "__main__":
    main()
