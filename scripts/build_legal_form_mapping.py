"""
One-off build script: turns the official INSEE "catégorie juridique"
nomenclature (data/manual/insee_categorie_juridique_2022-09.xls, provided
by the user — official file, "Dernière mise à jour le 1er septembre 2022")
into data/manual/insee_categorie_juridique.csv, with an is_sole_shareholder
column derived from French company law structural rules, NOT from the
nomenclature file itself (the file gives labels, not shareholder-count
rules).

Classification basis (see basis column in the output CSV for per-row
reasoning):

CONFIRMED MULTI-SHAREHOLDER (structurally requires 2+ members under
French company law, regardless of which INSEE sub-category):
  - SNC / SNC coopérative (5202, 5203) — no unipersonal SNC exists
  - Sociétés en commandite, all variants (5306-5310) — requires both a
    commandité and commanditaire, minimum 2 distinct people
  - SA, ALL variants — à conseil d'administration (55xx) and à directoire
    (56xx) — French SA law has no unipersonal-SA form (unlike SARL->EURL
    or SAS->SASU); every SA sub-category requires 2+ shareholders
  - GIE / GEIE (6210, 6220) — founding law requires 2+ members
  - Sociétés civiles, ALL variants (65xx range: SCI, SCP, SCM, sociétés
    civiles agricoles/foncières/forestières/pastorales, GAEC, etc.) —
    Code civil art. 1832 requires a société civile to have 2+ associates;
    no unipersonal société civile form exists
  - Agricultural cooperatives (6316 CUMA, 6317, 6318) — cooperative
    statutes require multiple members

NOT APPLICABLE (not a shareholder-based société at all):
  - Entrepreneur Individuel (1000)
  - Associations (92xx)
  - Public/administrative bodies, social security, ministries, local
    government (41xx, 61xx, 71xx-79xx, 81xx-85xx)
  - Foreign entities (31xx, 32xx) — different legal system, can't assume
    French shareholder-count rules apply

KNOWN AMBIGUOUS (explicitly flagged, not guessed):
  - SARL générique (5499) — "sans autre indication"; no separate EURL
    code exists in this nomenclature, so single- vs multi-shareholder
    can't be told apart via this field alone
  - SAS (5710) — absorbed the SASU-specific code (5720) in July 2020

EVERYTHING ELSE (rare specialized SARL sub-forms 54xx, Société
européenne 5800, etc.): left unclassified rather than guessed — legal
certainty on whether e.g. "SARL d'économie mixte" can be unipersonal
was not established with confidence, so it stays None.

Usage:
    python scripts/build_legal_form_mapping.py
"""

import sys
from pathlib import Path

import pandas as pd

XLS_PATH = "data/manual/insee_categorie_juridique_2022-09.xls"
OUT_CSV = "data/manual/insee_categorie_juridique.csv"


def classify(code: str, libelle: str):
    """Returns (is_sole_shareholder, basis) for one code."""
    if code == "1000":
        return None, "EI (entrepreneur individuel) - not a société with shareholders"
    if code == "5499":
        return None, "SARL générique - no distinct EURL code in this nomenclature; ambiguous"
    if code == "5710":
        return None, "SAS - SASU code (5720) merged into this in July 2020; ambiguous"

    # Confirmed multi-shareholder families
    if code in ("5202", "5203"):
        return False, "SNC - no unipersonal SNC form exists under French law"
    if code in ("5306", "5307", "5308", "5309", "5310"):
        return False, "Société en commandite - requires commandité + commanditaire (2+ distinct people)"
    if code.startswith("55") or code.startswith("56"):
        return False, "SA (any sub-form) - French SA law has no unipersonal-SA form, requires 2+ shareholders"
    if code in ("6210", "6220"):
        return False, "GIE/GEIE - founding law requires 2+ members"
    if code.startswith("65"):
        return False, "Société civile (any sub-form, incl. SCI/SCP/SCM) - Code civil art. 1832 requires 2+ associates"
    if code in ("6316", "6317", "6318"):
        return False, "Agricultural cooperative - cooperative statutes require multiple members"

    # Not applicable
    if code.startswith("92"):
        return None, "Association - not a shareholder-based société"
    if code[:2] in ("71", "72", "73", "74", "75", "76", "77", "78", "79", "81", "82", "83", "84", "85"):
        return None, "Public/administrative/social-security body - not a shareholder-based société"
    if code.startswith("41") or code.startswith("61"):
        return None, "Public establishment - not a shareholder-based société"
    if code.startswith("31") or code.startswith("32"):
        return None, "Foreign entity - different legal system, French shareholder-count rules don't apply"

    return None, "Not classified - insufficient legal certainty, left unmapped rather than guessed"


def main():
    df = pd.read_excel(XLS_PATH, sheet_name="Niveau III", header=None, skiprows=4)
    df.columns = ["code", "libelle"]
    df = df.dropna(subset=["code"])
    df["code"] = df["code"].astype(str).str.strip()
    df["libelle"] = df["libelle"].astype(str).str.strip()
    df = df[df["code"] != ""]

    rows = []
    for _, r in df.iterrows():
        is_sole, basis = classify(r["code"], r["libelle"])
        rows.append({
            "code": r["code"],
            "libelle": r["libelle"],
            "is_sole_shareholder": is_sole,
            "basis": basis,
        })

    out = pd.DataFrame(rows)
    Path(OUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(out)} codes to {OUT_CSV}")
    print(out["is_sole_shareholder"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
