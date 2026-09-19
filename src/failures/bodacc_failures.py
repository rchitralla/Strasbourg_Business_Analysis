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
via NATURE_CLASSIFICATION below, and headline counts should filter to
nature_classification == "opening" unless you deliberately want the
broader "all proceeding-related notices" number.

CONFIRMED live (2026-09-19) against the real, full distribution across
all 3 departments (93,622 total notices — see NATURE_CLASSIFICATION
below for every value seen and how it's classified). Two things this
run also surfaced:

1. A DIFFERENT, MORE SERIOUS bug in src/common/bodacc_client.py: the
   same accented string was appearing as TWO distinct values — once
   correctly accented, once mojibake-garbled ("procÃ©dure" instead of
   "procédure") — because response.json() trusted requests's guessed
   encoding, which flips inconsistently between UTF-8 and Latin-1 when
   the server sends no explicit charset. FIXED in bodacc_client.py
   (parses response.content directly with json.loads() instead). Any
   department JSON cached BEFORE that fix (check the file's mtime, or
   just re-fetch with resume=False) has this corruption BAKED IN and
   must be re-fetched — NATURE_CLASSIFICATION below uses only the
   correctly-accented spelling, so a stale cache's garbled duplicates
   will show up as unclassified, not as classification errors.

2. "Jugement de clôture pour insuffisance d'actif" (closure, NOT a new
   failure) is the single LARGEST category (29,475 of 93,622) — bigger
   than the main opening category itself. This confirms the Data Room
   brief's caveat was not academic: a raw, unfiltered notice count
   would have been dominated by closures of cases opened years
   earlier, not new failures.

NATURE_CLASSIFICATION below covers every nature value confirmed in that
real distribution, using standard French insolvency-procedure
vocabulary (Code de commerce, Livre VI — sauvegarde / redressement
judiciaire / liquidation judiciaire), grouped into:
  "opening"           - a genuine NEW insolvency proceeding commencing
                         (THE headline "failure" event)
  "conversion"         - an already-open case escalating to a harsher
                         procedure (NOT new — already counted at opening)
  "closure"            - the case ending, for any reason (NOT new)
  "plan"               - a recovery/repayment/sale plan adopted for an
                         already-open case (NOT new)
  "plan_failure"        - a previously-adopted plan collapsing (often
                         into liquidation) — a genuine secondary signal,
                         but tied to a case already counted at its
                         original opening, so kept separate rather than
                         folded into "opening"
  "personal_sanction"   - a sanction on the DIRIGEANT personally (gérer
                         interdiction, faillite personnelle) — not a
                         judgment about the company's insolvency status
  "administrative"      - a procedural filing/notice within an existing
                         case (creditor-claims deposits, plan
                         modifications, organe appointments) — not a
                         judgment on status at all
  "appeal"              - a Court of Appeal ruling, whose effect on the
                         underlying case can't be determined from the
                         label alone
  None (unclassified)   - the generic BODACC catch-all labels
                         ("Autre jugement prononçant", "Autre jugement
                         et ordonnance") — confirmed to be a genuinely
                         large share of real volume (17,000+ combined)
                         but with no way to tell from the label alone
                         what actually happened. Left unclassified
                         deliberately — see build_dataframe()'s warning.

There is NO NAF/sector code on a BODACC record (only a free-text
"activite" description) — a sector breakdown requires cross-referencing
extract_siren() against Sirene (src/company_creation/sirene_v3_client.py),
via enrich_with_sector() below.

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

# CONFIRMED live (2026-09-19) against the real distribution across all 3
# departments (93,622 notices) — see the module docstring for the full
# category explanation. Uses only the correctly-accented spelling; a
# cache fetched before bodacc_client.py's encoding fix will show mojibake
# duplicates of these as unclassified — re-fetch it, don't add garbled
# duplicate keys here.
NATURE_CLASSIFICATION = {
    # --- OPENING: genuine new insolvency proceedings (THE headline
    # "failure" event) ---
    "Jugement d'ouverture de liquidation judiciaire": "opening",
    "Jugement d'ouverture d'une procédure de redressement judiciaire": "opening",
    "Jugement d'ouverture d'une procédure de sauvegarde": "opening",
    "Jugement d'ouverture d'une procédure de traitement de sortie de crise": "opening",
    "Autre jugement d'ouverture": "opening",  # label itself says "d'ouverture" (opening)

    # --- CONVERSION: an already-open case escalating to a harsher
    # procedure (NOT a new failure — the original opening already
    # counted it) ---
    "Jugement de conversion en liquidation judiciaire": "conversion",
    "Jugement de conversion en liquidation judiciaire de la procédure de sauvegarde": "conversion",
    "Jugement de conversion en liquidation judiciaire de la procédure de sauvegarde financière accélérée": "conversion",
    "Jugement de conversion en redressement judiciaire de la procédure de sauvegarde": "conversion",
    "Jugement d'extension d'une procédure de redressement judiciaire": "conversion",
    "Jugement d'extension d'une procédure de sauvegarde": "conversion",
    "Jugement d'extension de liquidation judiciaire": "conversion",

    # --- CLOSURE: the case ending, for any reason (NOT a new failure —
    # confirmed live to be the SINGLE LARGEST category, 29,475/93,622,
    # since it includes closures of cases opened years earlier) ---
    "Jugement de clôture pour insuffisance d'actif": "closure",
    "Jugement de clôture pour insuffisance d'actif et autorisant la reprise des poursuites individuelles": "closure",
    "Jugement de clôture pour extinction du passif": "closure",
    "Jugement de clôture de la procédure de sauvegarde": "closure",
    "Autre jugement de clôture": "closure",
    "Jugement mettant fin à la procédure de redressement judiciaire": "closure",
    "Jugement mettant fin à la procédure de sauvegarde": "closure",
    "Jugement mettant fin à la procédure de sauvegarde financière accélérée": "closure",
    "Jugement de reprise de la procédure de liquidation judiciaire": "closure",  # reopening a previously-closed case

    # --- PLAN: a recovery/repayment/sale plan adopted for an
    # already-open case (NOT a new failure) ---
    "Jugement arrêtant le plan de redressement": "plan",
    "Jugement de plan de redressement": "plan",
    "Jugement arrêtant le plan de sauvegarde": "plan",
    "Jugement arrêtant le plan de sauvegarde financière accélérée": "plan",
    "Jugement arrêtant un plan de cession": "plan",
    "Jugement de plan de traitement de sortie de crise": "plan",
    "Jugement modifiant le plan de continuation": "plan",
    "Jugement modifiant le plan de redressement": "plan",
    "Jugement modifiant le plan de sauvegarde": "plan",

    # --- PLAN_FAILURE: a previously-adopted plan collapsing, usually
    # into liquidation — a genuine secondary failure signal, but tied to
    # a case already counted at its original opening ---
    "Jugement prononçant la résolution du plan de redressement": "plan_failure",
    "Jugement prononçant la résolution du plan de redressement et la liquidation judiciaire": "plan_failure",
    "Jugement prononçant la résolution du plan de cession et la liquidation judiciaire": "plan_failure",
    "Jugement prononçant la résolution du plan de sauvegarde et la liquidation judiciaire": "plan_failure",
    "Jugement prononçant la résolution du plan de sauvegarde et le redressement judiciaire": "plan_failure",
    "Jugement prononçant la résolution du plan de sauvegarde financière accélérée et la liquidation judiciaire": "plan_failure",
    "Jugement prononçant la résolution du plan de sauvegarde accélérée et la liquidation judiciaire": "plan_failure",
    "Jugement prononçant la résolution du plan de traitement de sortie de crise et le redressement judiciaire": "plan_failure",

    # --- PERSONAL_SANCTION: a sanction on the dirigeant personally, not
    # a judgment about the COMPANY's insolvency status ---
    "Jugement d'interdiction de gérer": "personal_sanction",
    "Jugement d'interdiction de gérer Loi de 1985": "personal_sanction",
    "Jugement de faillite personnelle": "personal_sanction",
    "Jugement de faillite personnelle Loi de 1985": "personal_sanction",

    # --- ADMINISTRATIVE: a procedural filing/notice within an existing
    # case — not a judgment on the company's status at all ---
    "Dépôt de l'état des créances": "administrative",
    "Dépôt de l'état des créances Loi de 1985": "administrative",
    "Dépôt de l'état des créances et du projet de répartition": "administrative",
    "Dépôt de l'état de collocation": "administrative",
    "Dépôt du projet de répartition": "administrative",
    "Autre avis de dépôt": "administrative",
    "Autres avis de dépôt": "administrative",
    "Liste des créances nées après le jugement d'ouverture d'une procédure de liquidation judiciaire": "administrative",
    "Liste des créances nées après le jugement d'ouverture d'une procédure de redressement judiciaire": "administrative",
    "Jugement de désignation des organes de la procédure": "administrative",
    "Jugement modifiant la date de cessation des paiements": "administrative",
    "Jugement accordant un délai pour déposer la liste des créances": "administrative",

    # --- APPEAL: Court of Appeal rulings — effect on the underlying
    # case can't be determined from the label alone ---
    "Arrêt de la cour d'appel infirmant une décision soumise à publicité": "appeal",
    "Autre arrêt de la Cour d'Appel": "appeal",

    # "Autre jugement prononçant" and "Autre jugement et ordonnance" are
    # deliberately NOT mapped — confirmed live to be large, genuine BODACC
    # catch-all labels (9,733 and 7,288 notices respectively) with no way
    # to tell from the label alone what happened. Left unclassified
    # (None) rather than guessed — see build_dataframe()'s warning.
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
