"""
Summarize the Sirene v3.11 company-creation data into direct answers for
Data Room questions B16, B17 and B18.

Run this AFTER sv3.run_all() has produced the three per-department CSVs
with the legal_form_label / is_sole_shareholder columns (see
sirene_v3_client.py — requires the 2026-09-02 fix, not the earlier
pre-fix CSVs).

Usage:
    python -m src.company_creation.summarize_b16_b17_b18
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.company_creation.sirene_v3_client import _department_csv_path
from config.regions import FRENCH_DEPARTMENTS


def load_all_departments() -> pd.DataFrame:
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        csv_path = _department_csv_path(dept.insee_code)
        if not Path(csv_path).exists():
            print(f"WARNING: {csv_path} not found — run sv3.run_all() first.")
            continue
        frames.append(pd.read_csv(csv_path, dtype={"legal_form": str}))
    if not frames:
        raise FileNotFoundError("No department CSVs found under data/processed/.")
    return pd.concat(frames, ignore_index=True)


def b16_creations_by_sector(df: pd.DataFrame, exclude_ei: bool = True) -> pd.DataFrame:
    """
    B16: how many companies by sector were registered, per department,
    per year. exclude_ei=True restricts to "sociétés" (excludes
    legal_form 1000 = Entrepreneur Individuel), matching how B16 and
    B17 are phrased as separate questions in the Data Room brief.
    """
    data = df[df["legal_form"] != "1000"] if exclude_ei else df
    return (
        data.groupby(["year", "region", "sector"])["count"]
        .sum()
        .reset_index()
        .sort_values(["year", "region", "sector"])
    )


def b17_sole_proprietorships_by_sector(df: pd.DataFrame) -> pd.DataFrame:
    """B17: entreprises individuelles (legal_form == "1000") by sector."""
    return (
        df[df["legal_form"] == "1000"]
        .groupby(["year", "region", "sector"])["count"]
        .sum()
        .reset_index()
        .sort_values(["year", "region", "sector"])
    )


def b18_multi_partner_share(df: pd.DataFrame) -> pd.DataFrame:
    """
    B18: share of companies created with multiple partners, per
    department per year. Restricted to rows where is_sole_shareholder
    is confirmed (not NaN/None).

    IMPORTANT CAVEAT — read before presenting this number: the official
    INSEE nomenclature has NO code that confidently means "single
    shareholder." SARL (5499) and SAS (5710) — which together are the
    large majority of real company creations — are both structurally
    ambiguous (SARL has no separate EURL code; SAS absorbed the SASU
    code in 2020) and are EXCLUDED from the classified subset here. The
    subset that remains (SA, SNC, sociétés civiles, GIE/GEIE, ag.
    cooperatives, etc.) is composed entirely of legal forms that
    structurally REQUIRE 2+ members — so this share is mathematically
    guaranteed to be ~100%, by construction, not because most companies
    have multiple partners. It answers "what share of the confirmed-
    multi-owner legal forms are multi-owner" (tautological), NOT "what
    share of all companies created have multiple partners" (the actual
    B18 question). Getting a real answer to B18 requires a data source
    that tracks associate/shareholder counts directly — e.g. INPI's
    Registre National des Entreprises — not the Sirene legal-form code.
    """
    classified = df[df["is_sole_shareholder"].notna()].copy()
    classified["is_sole_shareholder"] = classified["is_sole_shareholder"].astype(bool)

    totals = classified.groupby(["year", "region"])["count"].sum().rename("classified_total")
    multi = (
        classified[~classified["is_sole_shareholder"]]
        .groupby(["year", "region"])["count"]
        .sum()
        .rename("multi_partner_count")
    )

    result = pd.concat([totals, multi], axis=1).fillna(0).reset_index()
    result["multi_partner_share"] = (
        result["multi_partner_count"] / result["classified_total"]
    ).round(4)
    return result.sort_values(["year", "region"])


def main():
    df = load_all_departments()
    print(f"Loaded {len(df)} tidy rows across {df['region'].nunique()} department(s).\n")

    Path("outputs/tables").mkdir(parents=True, exist_ok=True)

    b16 = b16_creations_by_sector(df)
    b16.to_csv("outputs/tables/b16_creations_by_sector.csv", index=False)
    print(f"B16 saved: outputs/tables/b16_creations_by_sector.csv ({len(b16)} rows)")

    b17 = b17_sole_proprietorships_by_sector(df)
    b17.to_csv("outputs/tables/b17_sole_proprietorships_by_sector.csv", index=False)
    print(f"B17 saved: outputs/tables/b17_sole_proprietorships_by_sector.csv ({len(b17)} rows)")

    b18 = b18_multi_partner_share(df)
    b18.to_csv("outputs/tables/b18_multi_partner_share.csv", index=False)
    print(f"B18 saved: outputs/tables/b18_multi_partner_share.csv ({len(b18)} rows)")
    print("\nB18 CAVEAT — DO NOT present this share as-is: it is computed only over "
          "legal forms INSEE's nomenclature confirms structurally require 2+ members "
          "(SA, SNC, sociétés civiles, GIE/GEIE, ag. cooperatives). SARL and SAS — the "
          "majority of real company creations — are excluded as ambiguous (no EURL/SASU "
          "split since 2020). Since no code is confidently 'single-shareholder', this "
          "share is ~100% by construction and does NOT measure the real-world "
          "multi-partner rate. See b18_multi_partner_share()'s docstring for detail and "
          "for what a genuine B18 answer would require (e.g. INPI's Registre National "
          "des Entreprises).")

    print("\nB18 summary (last 3 years, all departments):")
    print(b18[b18["year"] >= b18["year"].max() - 2].to_string(index=False))


if __name__ == "__main__":
    main()
