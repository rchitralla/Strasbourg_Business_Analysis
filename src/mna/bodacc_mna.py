"""
Mergers axis (Data Room question B13) — BODACC "Modifications diverses"
notices mentioning fusion/absorption/TUP, via the shared
src/common/bodacc_client.py.

CONFIRMED against a live response (2026-09-04, via
scripts/bodacc_debug_mergers.py): merger notices are NOT a dedicated
familleavis_lib category — they live inside the broad "Modifications
diverses" family, identified by a short free-text descriptif (a real
example was literally just the string "fusion") inside
modificationsgenerales. ODSQL `like` substring-matches this field
directly even though it's stored as escaped JSON internally.
bc.MERGER_WHERE_CLAUSE encodes the confirmed filter (fusion OR
absorption OR TUP, ORed together in one query so a record matching more
than one term isn't double-counted across separate queries).

CAVEATS — read before presenting a merger count:
  1. This is a TEXT-SUBSTRING match on free-text French, not a
     structured "notice type" field — false positives are possible in
     principle (an unrelated modification whose descriptif happens to
     mention one of these words) though unlikely in practice, since
     modificationsgenerales.descriptif is specifically about what
     changed in the company (capital, form, etc.), not general prose.
  2. A merger typically produces TWO notices: the absorbing company's
     "Modifications diverses" (capital increase from the merger — what
     this module counts) and the absorbed company's eventual
     "Radiations" (strike-off) — this module only counts the absorbing
     side. Whether that under- or over-counts real mergers (e.g. a
     multi-step group reorganization producing several "Modifications
     diverses" notices for one underlying transaction) has NOT been
     validated against real volume yet.
  3. Per the Data Room brief's own caveat: territorial allocation
     follows the COURT of the ABSORBING company, which can shift a deal
     to the group's head-office department rather than the local
     target's site.
  4. No NAF/sector code is on a BODACC record — sector requires
     cross-referencing extract_siren() against Sirene.

Usage:
    from src.mna import bodacc_mna as mna
    df = mna.collect_all_departments(min_year=2015, max_year=2026)
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import bodacc_client as bc
from config.regions import FRENCH_DEPARTMENTS


def _department_cache_path(dept_code: str) -> str:
    return f"data/processed/bodacc_mergers_dept_{dept_code}.json"


def fetch_mergers_for_department(dept_code: str, min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch every merger-related "Modifications diverses" notice for one
    department in [min_year, max_year], cached to disk (see
    bc.fetch_and_cache) so re-running never re-hits the API for data
    already fetched.
    """
    where = (
        f'{bc.GEOGRAPHY_FIELD}="{dept_code}" '
        f'AND dateparution>="{min_year}-01-01" '
        f'AND dateparution<="{max_year}-12-31" '
        f'AND {bc.MERGER_WHERE_CLAUSE}'
    )
    return bc.fetch_and_cache(where, _department_cache_path(dept_code))


def extract_row(record: dict) -> dict | None:
    modifications = bc.parse_json_field(record.get("modificationsgenerales"))
    if modifications is None:
        return None

    listepersonnes = bc.parse_json_field(record.get("listepersonnes")) or {}
    personne = listepersonnes.get("personne", {})

    date_parution = record.get("dateparution")
    try:
        year = int(date_parution[:4]) if date_parution else None
    except (ValueError, TypeError):
        year = None

    return {
        "year": year,
        "department_code": record.get("numerodepartement"),
        "department_name": record.get("departement_nom_officiel"),
        "siren": bc.extract_siren(record),
        "commercant": record.get("commercant"),
        "legal_form_text": personne.get("formeJuridique"),
        "descriptif": modifications.get("descriptif"),
        "date_effet": modifications.get("dateEffet"),
        "dateparution": date_parution,
    }


def build_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()

    rows = [extract_row(r) for r in raw_df.to_dict("records")]
    return pd.DataFrame([r for r in rows if r is not None])


def collect_all_departments(min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch + tidy merger notices for every French department in
    config.regions.FRENCH_DEPARTMENTS. Each department's raw fetch is
    cached independently — delete
    data/processed/bodacc_mergers_dept_<code>.json to force a refetch.
    """
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        print(f"\nFetching merger notices for {dept.name} "
              f"(dept code {dept.insee_code}), {min_year}-{max_year}...")
        raw_df = fetch_mergers_for_department(dept.insee_code, min_year, max_year)
        tidy_df = build_dataframe(raw_df)
        print(f"  {len(tidy_df)} merger notice(s) extracted.")
        frames.append(tidy_df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """B13: merger count per department per year."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["year", "department_name"])
        .size()
        .rename("merger_count")
        .reset_index()
        .sort_values(["year", "department_name"])
    )


# ---------------------------------------------------------------------------
# B14 (acquisitions) and the deal-value half of B11 remain NOT implemented.
# Per the Data Room brief's own assessment: most share-transfer
# acquisitions carry no legal publication requirement in France, so
# there is no equivalent structured signal to build against (the
# "Ventes et cessions" family, confirmed via scripts/bodacc_debug_round3.py,
# covers fonds-de-commerce/asset sales, which is legally and
# economically distinct from a share/equity acquisition - see
# src/common/bodacc_client.py's docstring). Treat B14 as desk-research
# territory (trade press, France Invest regional stats) via the
# manual-CSV + source_url pattern used in src/lbo/lbo_manual.py, not as
# a script to build here.
#
# Baden-Württemberg has no Bodacc analogue - mergers of German companies
# are recorded in the Handelsregister but bulk/free structured access is
# limited. Not sourced yet.
# ---------------------------------------------------------------------------
