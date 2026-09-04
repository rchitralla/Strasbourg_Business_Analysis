"""
Average share capital at formation (Data Room question: "average share
capital of companies at their formation") — BODACC "Créations" notices,
via the shared src/common/bodacc_client.py.

CONFIRMED against a live response (2026-09-04, via
scripts/bodacc_debug_round3.py): familleavis_lib="Créations" notices
carry the share capital directly:
    listepersonnes (JSON string) = {"personne": {
        "capital": {"montantCapital": "3600", "devise": "EUR"},
        "typePersonne": "pm", "formeJuridique": "Société par actions simplifiée",
        "denomination": ..., "numeroImmatriculation": {...}, ...
    }}

IMPORTANT — read before presenting a mean: the Data Room brief's own
caveat applies directly here. French SARL/SAS have had NO minimum share
capital since 2003/2008, so the distribution is heavily skewed (a mass
of near-zero-capital companies, a few extreme outliers). REPORT THE
MEDIAN AND DECILES, not just the mean — build_summary() below computes
both so a mean-only chart doesn't slip into the deck by accident.

Capital is not applicable to every legal form (e.g. Entrepreneur
Individuel has no share capital at all) — a missing "capital" key on
listepersonnes.personne is treated as "not applicable" (excluded from
the capital stats) rather than as zero, which would silently drag the
average down and misrepresent EI creations as "companies with 0 capital".

Usage:
    from src.company_creation import share_capital as sc
    df = sc.collect_all_departments(min_year=2015, max_year=2026)
    summary = sc.build_summary(df)
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import bodacc_client as bc
from config.regions import FRENCH_DEPARTMENTS


def _department_cache_path(dept_code: str, min_year: int, max_year: int) -> str:
    # Year range is part of the cache key — see bodacc_failures.py's
    # identical comment for why this must never be omitted.
    return f"data/processed/bodacc_creations_dept_{dept_code}_{min_year}_{max_year}.json"


def fetch_creations_for_department(dept_code: str, min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch every "Créations" notice for one department in
    [min_year, max_year], cached to disk. Uses
    bc.fetch_and_cache_by_date_range() rather than a plain fetch — a
    department's full company-creation volume over several years
    routinely exceeds the API's 10,000-record cap (confirmed: 66,067
    "Créations" notices for Bas-Rhin alone, 2015-2026), so the date
    range must be bisected rather than fetched in one query.
    """
    where_base = f'{bc.GEOGRAPHY_FIELD}="{dept_code}" AND familleavis_lib="Créations"'
    return bc.fetch_and_cache_by_date_range(
        where_base, date_field="dateparution",
        date_start=f"{min_year}-01-01", date_end=f"{max_year}-12-31",
        cache_path=_department_cache_path(dept_code, min_year, max_year),
    )


def extract_row(record: dict) -> dict | None:
    listepersonnes = bc.parse_json_field(record.get("listepersonnes"))
    if listepersonnes is None:
        return None
    personne = bc.first_or_self(listepersonnes.get("personne"))

    date_parution = record.get("dateparution")
    try:
        year = int(date_parution[:4]) if date_parution else None
    except (ValueError, TypeError):
        year = None

    capital_block = personne.get("capital")
    capital_eur = None
    if capital_block and capital_block.get("montantCapital") is not None:
        try:
            capital_eur = float(capital_block["montantCapital"])
        except (TypeError, ValueError):
            capital_eur = None

    etablissement = bc.first_or_self(
        (bc.parse_json_field(record.get("listeetablissements")) or {}).get("etablissement")
    )

    return {
        "year": year,
        "department_code": record.get("numerodepartement"),
        "department_name": record.get("departement_nom_officiel"),
        "siren": bc.extract_siren(record),
        "commercant": record.get("commercant"),
        "legal_form_text": personne.get("formeJuridique"),  # free text, e.g. "Société par actions simplifiée"
        "capital_eur": capital_eur,  # None = not applicable (e.g. EI) or not disclosed, NOT zero
        "activite_text": etablissement.get("activite"),  # free text, not a NAF code
        "dateparution": date_parution,
    }


def build_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()

    rows = [extract_row(r) for r in raw_df.to_dict("records")]
    return pd.DataFrame([r for r in rows if r is not None])


def collect_all_departments(min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch + tidy "Créations" notices for every French department in
    config.regions.FRENCH_DEPARTMENTS. Each department's raw fetch is
    cached independently — delete
    data/processed/bodacc_creations_dept_<code>.json to force a refetch.
    """
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        print(f"\nFetching 'Créations' notices for {dept.name} "
              f"(dept code {dept.insee_code}), {min_year}-{max_year}...")
        raw_df = fetch_creations_for_department(dept.insee_code, min_year, max_year)
        tidy_df = build_dataframe(raw_df)
        n_with_capital = tidy_df["capital_eur"].notna().sum() if not tidy_df.empty else 0
        print(f"  {len(tidy_df)} notice(s) extracted, {n_with_capital} with a disclosed capital amount.")
        frames.append(tidy_df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per department per year: mean, median and decile spread of capital
    at formation, restricted to rows where capital is disclosed
    (not_applicable/undisclosed rows excluded from both numerator and
    denominator here — n_with_capital in the result tells you the base).

    REPORT THE MEDIAN, not the mean, in the deck — see module docstring.
    """
    capitalized = df[df["capital_eur"].notna()]
    if capitalized.empty:
        return pd.DataFrame()

    grouped = capitalized.groupby(["year", "department_name"])["capital_eur"]
    summary = grouped.agg(
        n_with_capital="count",
        mean_capital_eur="mean",
        median_capital_eur="median",
        p10_capital_eur=lambda s: s.quantile(0.10),
        p90_capital_eur=lambda s: s.quantile(0.90),
    ).reset_index()
    return summary.sort_values(["year", "department_name"])


# TODO (not yet implemented):
#   1. Sector: activite_text is free text, not a NAF code - cross-
#      reference extract_siren() against Sirene
#      (src/company_creation/sirene_v3_client.py) for a real NAF section
#      if a sector breakdown of capital is needed.
#   2. National average + Baden-Württemberg comparison (Handelsregister
#      Stammkapital, per the Data Room brief) are not sourced yet.
#   3. legal_form_text is currently free text from BODACC's own label
#      (e.g. "Société par actions simplifiée") rather than the Sirene
#      categorieJuridiqueUniteLegale code - fine for a capital-by-form
#      breakdown, but not directly joinable to sirene_v3_client's
#      LEGAL_FORM_LABELS without a text-matching step.
