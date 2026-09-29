"""
LBO holding-company proxy (Data Room question B24), via the shared
src/common/bodacc_client.py — the acquisition-holding-formation signal
the Data Room brief itself proposes, since no source records LBOs
directly (they're a financing structure, not a legal-filing category).

CONFIRMED against a live response (2026-09-05, via
scripts/bodacc_debug_lbo_proxy.py): BODACC has NO NAF code field at all,
so a NAF 6420Z ("Activités des sociétés holding") proxy has to identify
holding-company formations by free-text search on
listeetablissements — "holding" matched 560/320/277 real "Créations"
notices in Bas-Rhin/Haut-Rhin/Moselle respectively.

CRITICAL SIGNAL-VS-NOISE PROBLEM, confirmed via 5 real examples pulled
across different candidate search terms:
  - Broader terms ("gestion de participations": 108,395 national
    matches; "prise de participations": 95,697) are DOMINATED by
    ordinary personal/family wealth-management holding companies
    (a société civile with EUR1,000-50,000 capital, generic "gestion de
    portefeuille" language) — an extremely common French tax/estate-
    planning structure with NO connection to a leveraged buyout.
  - A genuine LBO acquisition vehicle example (real, from the live
    data): commercant "NEWCO", legal form "Société par Actions
    Simplifiée", activite "Holding d'acquisition et Holding
    opérationnelle" — the "Newco"-style naming, SAS legal form, and
    explicit "acquisition" wording are the actual tells, not just the
    word "holding" alone.

This module therefore does NOT report a raw count of holding-company
creations as an LBO count — it fetches every "Créations" notice
matching "holding" (the anchor term with the most manageable per-
department volume), then computes an ACQUISITION-SIGNAL SCORE per
record from independent heuristic markers, and reports counts broken
out BY SCORE rather than collapsed into one number. Treat even a
high-score match as a candidate to verify manually (e.g. against trade
press or Infogreffe), not a confirmed LBO — per the brief's own
instruction: "present as an estimation method, never as a count."

Usage:
    from src.lbo import bodacc_lbo_proxy as lbo
    df = lbo.collect_all_departments(min_year=2015, max_year=2026)
    summary = lbo.build_summary(df)
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import bodacc_client as bc
from config.regions import FRENCH_DEPARTMENTS

HOLDING_SEARCH_TERM = "holding"

# Naming patterns real acquisition vehicles commonly use (French and
# international LBO/deal practice) — a company literally called "NEWCO",
# "HOLDCO", "TOPCO", "BIDCO" (with an optional trailing number/suffix,
# e.g. "NEWCO 2", "BIDCO SAS") is a strong tell, unlike a descriptive
# family name like "LOPAB" or "JOSEPHINE".
ACQUISITION_NAME_PATTERN = re.compile(r"\b(NEWCO|HOLDCO|TOPCO|BIDCO|MIDCO)\b", re.IGNORECASE)

# Legal forms real LBO acquisition vehicles are set up as. A "Société
# Civile" is the dominant form for the personal/family wealth-management
# holdings that create most of the noise in this search (see module
# docstring) — genuine acquisition vehicles are virtually always a
# société de capitaux.
ACQUISITION_LEGAL_FORMS = {"Société par Actions Simplifiée", "Société Anonyme"}


def _acquisition_signal_score(legal_form_text: str, activite_text: str, commercant: str) -> int:
    """
    A simple additive score (0-3), NOT a probability — each point is one
    independent, confirmed-real marker of an acquisition vehicle rather
    than a personal/family holding:
      +1 legal form is SAS/SA (not Société Civile)
      +1 activite text explicitly mentions "acquisition"
      +1 company name matches a NEWCO/HOLDCO/TOPCO/BIDCO/MIDCO pattern
    A score of 0-1 is very likely noise (a personal wealth vehicle); 2-3
    is a real candidate worth manual verification.
    """
    score = 0
    if legal_form_text in ACQUISITION_LEGAL_FORMS:
        score += 1
    if activite_text and "acquisition" in activite_text.lower():
        score += 1
    if commercant and ACQUISITION_NAME_PATTERN.search(commercant):
        score += 1
    return score


def _department_cache_path(dept_code: str, min_year: int, max_year: int) -> str:
    # Year range is part of the cache key — see bodacc_failures.py's
    # identical comment for why this must never be omitted.
    return f"data/processed/bodacc_lbo_holdings_dept_{dept_code}_{min_year}_{max_year}.json"


def fetch_holding_creations_for_department(dept_code: str, min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch every "Créations" notice mentioning "holding" for one
    department in [min_year, max_year], cached to disk (date-bisected
    to stay under the API's 10,000-record cap, same as the other BODACC
    consumers).
    """
    where_base = (
        f'{bc.GEOGRAPHY_FIELD}="{dept_code}" AND familleavis_lib="Créations" '
        f'AND listeetablissements like "%{HOLDING_SEARCH_TERM}%"'
    )
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

    etablissement = bc.first_or_self(
        (bc.parse_json_field(record.get("listeetablissements")) or {}).get("etablissement")
    )
    activite_text = etablissement.get("activite")

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

    commercant = record.get("commercant")
    legal_form_text = personne.get("formeJuridique")

    return {
        "year": year,
        "department_code": record.get("numerodepartement"),
        "department_name": record.get("departement_nom_officiel"),
        "siren": bc.extract_siren(record),
        "commercant": commercant,
        "legal_form_text": legal_form_text,
        "capital_eur": capital_eur,
        "activite_text": activite_text,
        "acquisition_signal_score": _acquisition_signal_score(legal_form_text, activite_text, commercant),
        "dateparution": date_parution,
    }


def build_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()

    rows = [extract_row(r) for r in raw_df.to_dict("records")]
    return pd.DataFrame([r for r in rows if r is not None])


def collect_all_departments(min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch + tidy holding-company-formation notices for every French
    department in config.regions.FRENCH_DEPARTMENTS. Each department's
    raw fetch is cached independently — delete
    data/processed/bodacc_lbo_holdings_dept_<code>.json to force a
    refetch.
    """
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        print(f"\nFetching holding-company 'Créations' notices for {dept.name} "
              f"(dept code {dept.insee_code}), {min_year}-{max_year}...")
        raw_df = fetch_holding_creations_for_department(dept.insee_code, min_year, max_year)
        tidy_df = build_dataframe(raw_df)
        print(f"  {len(tidy_df)} holding-language notice(s) extracted.")
        frames.append(tidy_df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Count of holding-company-formation notices per department per year,
    broken out BY acquisition_signal_score — NOT collapsed into one
    "LBO count". A score-3 row is a real candidate to verify manually;
    score 0-1 is very likely a personal/family wealth vehicle. Report
    the score breakdown in the deck, not a single number.
    """
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["year", "department_name", "acquisition_signal_score"])
        .size()
        .rename("count")
        .reset_index()
        .sort_values(["year", "department_name", "acquisition_signal_score"])
    )


def list_high_signal_candidates(df: pd.DataFrame, min_score: int = 2) -> pd.DataFrame:
    """
    The actual candidates worth manually checking against trade press or
    Infogreffe — everything else in `df` is very likely noise (personal/
    family holding vehicles, per the module docstring).
    """
    return df[df["acquisition_signal_score"] >= min_score].sort_values(
        ["year", "department_name", "acquisition_signal_score"], ascending=[True, True, False]
    )


# TODO (not yet implemented):
#   1. Cross-reference each candidate's SIREN against a subsequent
#      "Ventes et cessions" or capital-increase "Modifications diverses"
#      notice within ~12 months, per the brief's proposed methodology -
#      NOT attempted here, since "Ventes et cessions" is confirmed to be
#      fonds-de-commerce sales (an asset deal), not the share acquisition
#      an LBO actually involves (see src/common/bodacc_client.py's
#      docstring) - there is no confirmed BODACC signal for a share
#      acquisition itself.
#   2. Corroborate against INPI's open comptes annuels (annual accounts)
#      data for bank debt on the holding's balance sheet in year 1 - not
#      sourced yet.
#   3. Baden-Württemberg equivalent: BVK/Invest Europe statistics, or the
#      same Handelsregister-based proxy (a new Beteiligungsgesellschaft
#      registration) - not sourced yet.
