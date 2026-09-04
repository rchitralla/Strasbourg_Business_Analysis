"""
Corporate failures axis (Data Room question B9) — INSEE BDM API.

CONFIRMED against a live response (2026-09-02): the "Séries chronologiques"
(BDM) API at https://api.insee.fr/series/BDM is key-less (no auth at all)
and its DEFAILLANCES-ENTREPRISES dataflow returns quarterly business-
failure counts as SDMX-ML StructureSpecificData XML.

Confirmed dimensions on each <Series> element:
  - REF_AREA: region code, e.g. "R93" (PACA), "R94" (Corse), "FE" (France
    entière) — REGION-level, NOT department. There is no direct Bas-Rhin/
    Haut-Rhin/Moselle breakdown; use Grand Est as the proxy. INSEE's
    official region code for Grand Est is "44", so the SDMX code is
    expected to be "R44" — NOT YET CONFIRMED (the sample response that
    informed this module happened not to include it). Run
    find_region_codes() below and check for "Grand Est" before trusting
    any Grand-Est-filtered chart.
  - ACTIVITE_CREAT_ENT: a COARSE custom sector grouping (values seen so
    far: ENS=all sectors, FZ, BE, G, H, I, JZ, KZ, LZ, MN, PQS) — NOT the
    fine NAF A-U sections used in src/common/sectors.py for the Sirene
    company-creation data. A mapping table is needed before charting
    this next to that data — build ACTIVITE_CREAT_ENT_TO_NAF_SECTION
    below once the full code list is confirmed (run list_sector_codes()).
  - FREQ="T" (quarterly).
Each <Series> nests <Obs TIME_PERIOD="YYYY-Qn" OBS_VALUE="..." .../> children.

Endpoint: https://api.insee.fr/series/BDM/data/{DATAFLOW_ID}/all
  ?startPeriod=YYYY   (no headers needed — this API is Key Less)

Requirements:
    pip install requests pandas
"""

import xml.etree.ElementTree as ET

import requests
import pandas as pd

BASE_URL = "https://api.insee.fr/series/BDM/data"
DATAFLOW_ID = "DEFAILLANCES-ENTREPRISES"

# TODO: confirm via find_region_codes(df) before relying on this.
GRAND_EST_REGION_CODE_GUESS = "R44"

# TODO: populate once list_sector_codes(df) confirms the full set, then
# use this to align failure-by-sector charts with the NAF-section-based
# creation data from src/common/sectors.NAF_WZ_SECTION_LABELS.
ACTIVITE_CREAT_ENT_TO_NAF_SECTION = {
    "ENS": None,  # "Tous secteurs d'activité" — total, not a single section
    # "FZ": "F",   # Construction — matches NAF section F directly, needs confirming
    # "BE": ?,     # groups B+C+D+E? needs confirming against INSEE's own docs
    # ... fill in the rest once list_sector_codes() output is confirmed
}


def _localname(tag: str) -> str:
    return tag.split("}")[-1]


def fetch_dataflow_xml(dataflow_id: str = DATAFLOW_ID, start_period: int = None) -> str:
    """Fetch the full raw SDMX-ML XML for a BDM dataflow. No API key needed."""
    url = f"{BASE_URL}/{dataflow_id}/all"
    params = {}
    if start_period:
        params["startPeriod"] = start_period
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.text


def parse_series_to_dataframe(xml_text: str) -> pd.DataFrame:
    """
    Parse StructureSpecificData XML into a tidy DataFrame: one row per
    (idbank, region_code, sector_code, period, value). Namespace-agnostic
    (matches elements by local name) since the exact default namespace
    URI wasn't visible in the sample response used to write this.
    """
    root = ET.fromstring(xml_text)
    rows = []
    for series in root.iter():
        if _localname(series.tag) != "Series":
            continue
        attrs = series.attrib
        for obs in series:
            if _localname(obs.tag) != "Obs":
                continue
            rows.append({
                "idbank": attrs.get("IDBANK"),
                "region_code": attrs.get("REF_AREA"),
                "sector_code": attrs.get("ACTIVITE_CREAT_ENT"),
                "title_fr": attrs.get("TITLE_FR"),
                "period": obs.get("TIME_PERIOD"),
                "value": obs.get("OBS_VALUE"),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def fetch_failures(start_period: int = 2015) -> pd.DataFrame:
    xml_text = fetch_dataflow_xml(start_period=start_period)
    return parse_series_to_dataframe(xml_text)


def find_region_codes(df: pd.DataFrame, name_contains: str = "Grand Est") -> pd.DataFrame:
    """
    Run this FIRST after fetch_failures() to confirm the REF_AREA code
    for Grand Est (or any other region) before trusting
    GRAND_EST_REGION_CODE_GUESS.
    """
    matches = df[df["title_fr"].str.contains(name_contains, na=False)]
    return matches[["region_code", "title_fr"]].drop_duplicates()


def list_sector_codes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run this to see every ACTIVITE_CREAT_ENT code and one example title,
    to build ACTIVITE_CREAT_ENT_TO_NAF_SECTION above.
    """
    return (
        df[["sector_code", "title_fr"]]
        .assign(sector_label=df["title_fr"].str.extract(r" - ([^-]+)$"))
        .drop_duplicates(subset=["sector_code"])
        [["sector_code", "sector_label"]]
    )
