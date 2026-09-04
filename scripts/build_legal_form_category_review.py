"""
One-off build script: turns the user's manual business-relevance review
of ~170 "non-obvious" INSEE legal-form codes into
data/manual/legal_form_category_review.csv.

This is DIFFERENT from data/manual/insee_categorie_juridique.csv:
  - insee_categorie_juridique.csv = official label + is_sole_shareholder,
    a question of French COMPANY LAW (does this legal form structurally
    require 1 vs 2+ members).
  - legal_form_category_review.csv (this file) = a BUSINESS-RELEVANCE
    judgment call: is this code actually a "company" in the sense the
    Data Room brief means, or is it something else entirely (a VAT-only
    registration, a public administrative body, a trade union, an
    association, a co-ownership syndicate...) that should be excluded
    from company-CREATION counts (B16/B17/B18) even though Sirene lists
    it alongside real companies.

REVIEW_DATA below is the user's own table, transcribed verbatim (code,
remove flag, category comment). Every code is cross-checked against the
official nomenclature (insee_categorie_juridique.csv) at build time —
a code that doesn't match there means a transcription typo and the
script will print a loud warning rather than silently writing bad data.

Columns in the output CSV:
  code                        - INSEE catégorie juridique code
  legal_form_label            - official label (from insee_categorie_juridique.csv, not retyped)
  remove_raw                  - exactly what was marked: "Y", "N", or "" (undecided/keep)
  exclude_from_business_counts - True only when remove_raw == "Y"
  category                    - normalized from the free-text comment: Association,
                                 Syndicat, État, État-Privé, or "" (ordinary company /
                                 not categorized)

Any of the official 260 codes NOT in REVIEW_DATA are ordinary company
legal forms (SA, SARL, SAS, SCI, GIE, SNC, etc. already confirmed in
insee_categorie_juridique.csv) that were never in question — they get
exclude_from_business_counts=False, category="" by default.

Usage:
    python scripts/build_legal_form_category_review.py
"""

import csv
from pathlib import Path

NOMENCLATURE_CSV = "data/manual/insee_categorie_juridique.csv"
OUT_CSV = "data/manual/legal_form_category_review.csv"

# (code, remove_raw, category_comment) - transcribed verbatim from the
# user's review table (2026-09-04).
REVIEW_DATA = [
    ("5195", "", "Association"),
    ("9224", "", "Association"),
    ("9260", "", "Association"),
    ("9220", "", "Association"),
    ("9221", "", "Association"),
    ("9230", "", "Association"),
    ("7323", "", "Association"),
    ("7322", "", "Association"),
    ("9222", "", "Association"),
    ("7321", "", "Syndicat"),
    ("9150", "", "Syndicat"),
    ("2800", "Y", ""),
    ("8250", "", ""),
    ("7111", "Y", ""),
    ("7385", "N", "État"),
    ("2900", "", ""),
    ("8490", "", ""),
    ("6901", "", ""),
    ("7490", "", "État"),
    ("9900", "", "État"),
    ("5560", "", ""),
    ("5660", "", ""),
    ("5460", "", ""),
    ("6599", "", ""),
    ("6585", "", ""),
    ("5194", "", ""),
    ("6596", "", ""),
    ("7363", "", ""),
    ("7361", "Y", ""),
    ("8470", "", "Association"),
    ("8310", "", "Syndicat"),
    ("8311", "", "Syndicat"),
    ("9240", "", ""),
    ("6316", "Y", ""),
    ("7220", "Y", ""),
    ("1000", "", ""),
    ("7364", "", ""),
    ("7450", "", "État"),
    ("7430", "", "État"),
    ("4140", "", "État"),
    ("7331", "", "État"),
    ("7366", "", "État"),
    ("7389", "Y", "État"),
    ("4110", "", "État"),
    ("4120", "", "État"),
    ("7383", "", "État"),
    ("6598", "", ""),
    ("9300", "", ""),
    ("6220", "", ""),
    ("9223", "", "Syndicat"),
    ("9970", "", ""),
    ("7470", "", ""),
    ("6534", "", ""),
    ("6538", "", ""),
    ("6536", "", ""),
    ("2120", "Y", ""),
    ("2110", "Y", ""),
    ("8130", "", ""),
    ("8210", "", ""),
    ("8450", "Y", ""),
    ("7381", "Y", ""),
    ("7357", "", ""),
    ("7378", "", "État"),
    ("8110", "Y", ""),
    ("8120", "Y", ""),
    ("7230", "Y", ""),
    ("5599", "", ""),
    ("5699", "", ""),
    ("5558", "", ""),
    ("5547", "", ""),
    ("5530", "Y", ""),
    ("5515", "", "État-Privé"),
    ("5615", "", "État-Privé"),
    ("5546", "", ""),
    ("5522", "", ""),
    ("5510", "", ""),
    ("5453", "", ""),
    ("5458", "", ""),
    ("5426", "", ""),
    ("5410", "", ""),
    ("5710", "", ""),
    ("6578", "", ""),
    ("6561", "", ""),
    ("6564", "", ""),
    ("6573", "", ""),
    ("6571", "", ""),
    ("6565", "", ""),
    ("6576", "", ""),
    ("7172", "Y", ""),
    ("7171", "Y", ""),
    ("5499", "", ""),
    ("6542", "", ""),
    ("6597", "", ""),
    ("6589", "", ""),
    ("6521", "", ""),
    ("6539", "", ""),
    ("6540", "", ""),
    ("6541", "", ""),
    ("3120", "Y", ""),
    ("6317", "", ""),
    ("5192", "", ""),
    ("2220", "", ""),
    ("2210", "", ""),
    ("6411", "", ""),
    ("5485", "", ""),
    ("5385", "", ""),
    ("5785", "", ""),
    ("5470", "", ""),
    ("5570", "", ""),
    ("5770", "", ""),
    ("5308", "", ""),
    ("5306", "", ""),
    ("5202", "", ""),
    ("2320", "", ""),
    ("2385", "", ""),
    ("2310", "", ""),
    ("3220", "", ""),
    ("5800", "", ""),
    ("6511", "", ""),
    ("9110", "Y", ""),
    ("8410", "", "Syndicat"),
    ("7345", "", "Syndicat"),
    ("7353", "", "Syndicat"),
    ("7354", "", "Syndicat"),
    ("7355", "", "Syndicat"),
    ("8420", "", "Syndicat"),
    ("6318", "", ""),
    ("7379", "Y", ""),
    ("7179", "Y", ""),
    ("9210", "", "Association"),
    ("7384", "", ""),
    ("6560", "", ""),
    ("7362", "", ""),
    ("8290", "", ""),
    ("6595", "", "État"),
    ("7367", "", "État"),
    ("7373", "", "État"),
    ("7382", "", "État"),
    ("3210", "", "État"),
    ("5520", "", "État"),
    ("6535", "", ""),
    ("6210", "", ""),
    ("7351", "Y", ""),
    ("7344", "Y", ""),
    ("5553", "", ""),
    ("5551", "", ""),
    ("5532", "", ""),
    ("5610", "", ""),
    ("5442", "", ""),
    ("5415", "", "État-Privé"),
    ("6568", "", ""),
    ("6572", "", ""),
    ("6577", "", ""),
    ("6574", "", ""),
    ("7120", "Y", ""),
    ("7160", "Y", ""),
    ("7372", "Y", ""),
    ("6543", "", ""),
    ("5585", "", ""),
    ("5203", "", ""),
    ("3290", "", ""),
    ("3205", "", ""),
    ("7340", "Y", ""),
    ("4150", "", "État"),
    ("3110", "", ""),
    ("5543", "", ""),
    ("5646", "", ""),
    ("7150", "Y", ""),
]


def main():
    with open(NOMENCLATURE_CSV, newline="", encoding="utf-8") as f:
        official_labels = {row["code"]: row["libelle"] for row in csv.DictReader(f)}

    seen_codes = set()
    rows = []
    missing = []
    duplicates = []

    for code, remove_raw, category in REVIEW_DATA:
        if code in seen_codes:
            duplicates.append(code)
            continue
        seen_codes.add(code)

        label = official_labels.get(code)
        if label is None:
            missing.append(code)
            label = "(NOT FOUND IN OFFICIAL NOMENCLATURE - CHECK FOR TYPO)"

        rows.append({
            "code": code,
            "legal_form_label": label,
            "remove_raw": remove_raw,
            "exclude_from_business_counts": remove_raw.strip().upper() == "Y",
            "category": category,
        })

    if duplicates:
        print(f"WARNING: duplicate code(s) in REVIEW_DATA, later entries ignored: {duplicates}")
    if missing:
        print(f"WARNING: {len(missing)} code(s) not found in {NOMENCLATURE_CSV} - "
              f"likely a transcription typo, please check: {missing}")

    Path(OUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["code", "legal_form_label", "remove_raw",
                                                "exclude_from_business_counts", "category"])
        writer.writeheader()
        writer.writerows(rows)

    n_excluded = sum(r["exclude_from_business_counts"] for r in rows)
    n_categorized = sum(1 for r in rows if r["category"])
    print(f"Wrote {len(rows)} reviewed codes to {OUT_CSV}")
    print(f"  {n_excluded} marked for exclusion from business-creation counts")
    print(f"  {n_categorized} tagged with a category (Association/Syndicat/État/État-Privé)")
    print(f"  {260 - len(rows)} of the official 260 codes are untouched by this review "
          f"(ordinary company legal forms - ineligible for exclusion)")


if __name__ == "__main__":
    main()
