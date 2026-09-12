"""
Corporate failures axis (Data Room question B9) — BODACC "Procédures
collectives" notices, via the shared src/common/bodacc_client.py.

CONFIRMED against a live response (2026-09-04, via
scripts/bodacc_debug_sample.py): familleavis_lib="Procédures collectives"
notices carry a `jugement` field (JSON-encoded string) shaped like:
    {"famille": "Jugement prononçant",
     "nature": "Jugement de conversion en liquidation judiciaire",
     "date": "10 décembre 2009",           <- FRENCH TEXT, not ISO
     "complementJugement": "...",
     "type": "initial"}

IMPORTANT — read before treating a raw count as "the" failure count:
jugement.type ("initial") only says whether this BODACC NOTICE is a
first publication — it does NOT distinguish an opening judgment from a
later conversion or plan. The Data Room brief's own caveat is explicit:
"an insolvency = an OPENING JUDGMENT; conversions from reorganisation to
liquidation and terminated plans are not counted again." So this module
classifies jugement.nature (free text) into opening vs. conversion/other
via NATURE_CLASSIFICATION below, and headline counts should use
is_opening_judgment == True unless you deliberately want the broader
"all proceeding-related notices" number.

NATURE_CLASSIFICATION currently covers only the nature strings actually
seen so far (one example: "Jugement de conversion en liquidation
judiciaire" -> conversion). MORE VALUES WILL APPEAR once real volume is
pulled — any unrecognized nature string is classified as None
(unclassified) with a loud warning printed, never silently guessed, so
this needs revisiting once real department-level data comes back. This
is the same defensive-classification pattern used for the Sirene
NAFRev1/legal-form corrections elsewhere in this project.

There is NO NAF/sector code on a BODACC record (only a free-text
"activite" description) — a sector breakdown requires cross-referencing
extract_siren() against Sirene (src/company_creation/sirene_v3_client.py),
which is NOT implemented in this module yet (see TODO).

Usage:
    from src.failures import bodacc_failures as bf
    df = bf.collect_all_departments(min_year=2015, max_year=2026)
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import bodacc_client as bc
from config.regions import FRENCH_DEPARTMENTS

# Only the nature strings actually confirmed against a live response so
# far. Extend this as new values surface — see the module docstring.
NATURE_CLASSIFICATION = {
    "Jugement de conversion en liquidation judiciaire": "conversion",
    # Expected but NOT YET CONFIRMED against a real example — verify
    # the exact wording before relying on these:
    # "Jugement d'ouverture d'une procédure de redressement judiciaire": "opening",
    # "Jugement d'ouverture d'une procédure de liquidation judiciaire": "opening",
    # "Jugement arrêtant le plan de redressement": "plan",
    # "Jugement de clôture pour insuffisance d'actif": "cloture",
}


def _classify_nature(nature: str) -> str | None:
    return NATURE_CLASSIFICATION.get(nature)


def _department_cache_path(dept_code: str, min_year: int, max_year: int) -> str:
    # Year range is part of the cache key — a cache file for one range
    # must NEVER be silently reused for a different range (e.g. after
    # narrowing 2015-2026 down to 2020-2026), or stale/incomplete-looking
    # data would be returned without a fetch actually happening.
    return f"data/processed/bodacc_failures_dept_{dept_code}_{min_year}_{max_year}.json"


def fetch_failures_for_department(dept_code: str, min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch every "Procédures collectives" notice for one department in
    [min_year, max_year], cached to disk. Uses
    bc.fetch_and_cache_by_date_range() rather than a plain fetch — a
    wide enough year range or a busier department can exceed the API's
    10,000-record cap (confirmed live for a different family: 66,067
    "Créations" notices for Bas-Rhin alone over 2015-2026), so the date
    range must be bisected rather than fetched in one query.
    """
    where_base = f'{bc.GEOGRAPHY_FIELD}="{dept_code}" AND familleavis_lib="Procédures collectives"'
    return bc.fetch_and_cache_by_date_range(
        where_base, date_field="dateparution",
        date_start=f"{min_year}-01-01", date_end=f"{max_year}-12-31",
        cache_path=_department_cache_path(dept_code, min_year, max_year),
    )


def extract_row(record: dict) -> dict | None:
    jugement = bc.parse_json_field(record.get("jugement"))
    if jugement is None:
        return None

    nature = jugement.get("nature")
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
        "ville": record.get("ville"),
        "nature": nature,
        "nature_classification": _classify_nature(nature),  # "opening"/"conversion"/... or None if unrecognized
        "jugement_date_text": jugement.get("date"),  # French text, e.g. "10 décembre 2009" - not parsed to a real date yet
        "dateparution": date_parution,
    }


def build_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()

    rows = []
    for record in raw_df.to_dict("records"):
        row = extract_row(record)
        if row is not None:
            rows.append(row)

    df = pd.DataFrame(rows)

    unclassified = sorted(
        df.loc[df["nature_classification"].isna(), "nature"].dropna().unique()
    )
    if unclassified:
        print(f"WARNING: {len(unclassified)} unrecognized jugement.nature value(s) — "
              f"add them to NATURE_CLASSIFICATION in bodacc_failures.py before "
              f"trusting an 'opening judgment' headline count: {unclassified}")

    return df


def collect_all_departments(min_year: int, max_year: int) -> pd.DataFrame:
    """
    Fetch + tidy failures for every French department in
    config.regions.FRENCH_DEPARTMENTS, returning one combined DataFrame.
    Each department's raw fetch is cached independently (see
    fetch_failures_for_department) — delete
    data/processed/bodacc_failures_dept_<code>.json to force a refetch.
    """
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        print(f"\nFetching 'Procédures collectives' notices for {dept.name} "
              f"(dept code {dept.insee_code}), {min_year}-{max_year}...")
        raw_df = fetch_failures_for_department(dept.insee_code, min_year, max_year)
        tidy_df = build_dataframe(raw_df)
        print(f"  {len(tidy_df)} notice(s) extracted.")
        frames.append(tidy_df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def enrich_with_sector(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds naf_code/sector/legal_form_code/legal_form_label/denomination
    columns by cross-referencing each row's SIREN against Sirene — there
    is no sector code on a BODACC record itself (see module docstring).
    Requires sv3.set_api_key() first. Expect this to take real time for
    a busy department: src/common/sirene_lookup.py rate-limits to
    ~2.1s/unique SIREN (progress is cached to disk every 20 lookups, so
    an interrupted run can safely be re-run).

        from src.company_creation import sirene_v3_client as sv3
        sv3.set_api_key()
        df = bf.collect_all_departments(2015, 2026)
        df = bf.enrich_with_sector(df)
    """
    from src.common import sirene_lookup as sl
    return sl.enrich_with_sector(df, siren_col="siren")


# TODO (not yet implemented):
#   1. Parse jugement_date_text (French month names, e.g. "10 décembre
#      2009") into a real date — the notice's dateparution is when
#      BODACC published it, which can lag the actual judgment date.
#   2. Failure RATE (vs. raw count) needs the active-company-stock
#      denominator per department/sector/year - not sourced yet.
#   3. Expand NATURE_CLASSIFICATION as new jugement.nature values surface
#      from real department-level data (only one value is confirmed so
#      far - see module docstring).
#   4. Baden-Württemberg side: Destatis/regionalstatistik.de
#      Insolvenzstatistik (EVAS 52411) - a completely separate API, not
#      BODACC-related. Mirror germany_registrations.py's pattern.
