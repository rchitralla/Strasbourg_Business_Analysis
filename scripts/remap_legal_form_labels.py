"""
Re-derive legal_form_label / is_sole_shareholder / exclude_from_business_counts
/ category on ALREADY-FETCHED company-creation CSVs, without re-hitting the
Sirene v3.11 API.

Why this exists: the raw `legal_form` column (the numeric
categorieJuridiqueUniteLegale code) was always fetched correctly — only
the DERIVED columns depend on lookup tables that can change over time:
  - legal_form_label, is_sole_shareholder: from the official nomenclature
    (data/manual/insee_categorie_juridique.csv)
  - exclude_from_business_counts, category: from the user's manual
    business-relevance review (data/manual/legal_form_category_review.csv)
    — is this legal form actually a "company creation", or something else
    Sirene also registers (a VAT-only registration, a commune, a trade
    union, a co-ownership syndicate...)?
Since all four are pure functions of `legal_form`, they can be
recomputed from the code already on disk — no need to re-fetch
~270k+ records per department against a 30-req/min API.

Run this on:
  - each data/processed/france_creations_sirene_v3_dept_<code>.csv
  - the combined data/processed/france_creations_sirene_v3_by_year_dept_sector.csv
    (produced by run_all()), if present

Usage:
    python scripts/remap_legal_form_labels.py
"""

import glob
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.company_creation.sirene_v3_client import (
    LEGAL_FORM_LABELS,
    IS_SOLE_SHAREHOLDER_BY_CODE,
    EXCLUDE_FROM_BUSINESS_COUNTS_BY_CODE,
    CATEGORY_BY_CODE,
)

TARGET_GLOBS = [
    "data/processed/france_creations_sirene_v3_dept_*.csv",
    "data/processed/france_creations_sirene_v3_by_year_dept_sector.csv",
]


def remap_file(csv_path: str) -> None:
    df = pd.read_csv(csv_path, dtype={"legal_form": str})
    if "legal_form" not in df.columns:
        print(f"  SKIP {csv_path}: no legal_form column")
        return

    before = {
        col: df.get(col)
        for col in ("legal_form_label", "is_sole_shareholder", "exclude_from_business_counts", "category")
    }

    df["legal_form_label"] = df["legal_form"].map(LEGAL_FORM_LABELS)
    df["is_sole_shareholder"] = df["legal_form"].map(IS_SOLE_SHAREHOLDER_BY_CODE)
    df["exclude_from_business_counts"] = df["legal_form"].map(EXCLUDE_FROM_BUSINESS_COUNTS_BY_CODE).fillna(False)
    df["category"] = df["legal_form"].map(CATEGORY_BY_CODE).fillna("")

    unmapped_codes = sorted(df.loc[df["legal_form_label"].isna(), "legal_form"].unique())
    if unmapped_codes:
        print(f"  WARNING: {len(unmapped_codes)} legal_form code(s) with no label "
              f"in the nomenclature: {unmapped_codes}")

    changes = {}
    for col, before_series in before.items():
        changes[col] = (
            int((before_series.astype(str) != df[col].astype(str)).sum())
            if before_series is not None else len(df)
        )

    df.to_csv(csv_path, index=False)
    print(f"  Remapped {csv_path}: {len(df)} rows — "
          f"{changes['legal_form_label']} label, "
          f"{changes['is_sole_shareholder']} is_sole_shareholder, "
          f"{changes['exclude_from_business_counts']} exclude_from_business_counts, "
          f"{changes['category']} category value(s) changed.")


def main():
    paths = []
    for pattern in TARGET_GLOBS:
        paths.extend(sorted(glob.glob(pattern)))

    if not paths:
        print("No processed CSVs found under data/processed/ — nothing to remap. "
              "(Run this on the machine where the CSVs actually live.)")
        return

    print(f"Found {len(paths)} file(s) to remap using the corrected "
          f"{len(LEGAL_FORM_LABELS)}-code official nomenclature:\n")
    for path in paths:
        remap_file(path)

    print("\nDone. Re-run `python -m src.company_creation.summarize_b16_b17_b18` "
          "to regenerate B16/B17/B18 outputs with the corrected numbers.")


if __name__ == "__main__":
    main()
