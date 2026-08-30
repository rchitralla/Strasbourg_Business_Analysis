"""
Shared region definitions for the Alsace-Moselle / Baden-Württemberg
cross-border business analysis.

Every analysis axis (macro-economy, M&A, company creations, LBO) compares
the same set of geographies, so region codes live here once instead of
being redefined per script.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FrenchDepartment:
    name: str
    insee_code: str          # 2-digit INSEE "code département"


@dataclass(frozen=True)
class GermanRegion:
    name: str
    ags_code: str            # Amtlicher Gemeindeschlüssel (regional key)


# --- Core comparison set (matches the "Data Room" question sheet) ---------

FRENCH_DEPARTMENTS = {
    "bas_rhin": FrenchDepartment("Bas-Rhin", "67"),
    "haut_rhin": FrenchDepartment("Haut-Rhin", "68"),
    "moselle": FrenchDepartment("Moselle", "57"),
}

# France, whole country — used as the national-average benchmark.
FRANCE_NATIONAL = FrenchDepartment("France (national)", "FR")

# Baden-Württemberg and a few of its Stadtkreise, for the German side of
# the comparison and for optional drill-downs.
GERMAN_REGIONS = {
    "baden_wurttemberg": GermanRegion("Baden-Württemberg (Land)", "08"),
    "stuttgart": GermanRegion("Stadtkreis Stuttgart", "08111"),
    "karlsruhe": GermanRegion("Stadtkreis Karlsruhe", "08212"),
    "freiburg": GermanRegion("Stadtkreis Freiburg im Breisgau", "08311"),
}

# Strasbourg city, for the commune-level drill-down the original script did.
STRASBOURG_COMMUNE_CODE = "67482"

# --- Shared time window -----------------------------------------------------
# The Data Room brief asks for "the last 3 years" on every question; keep a
# slightly wider default window so trend charts have context, and let each
# script narrow to the last 3 years for headline comparisons.
MIN_YEAR = 2015
MAX_YEAR = 2026
HEADLINE_YEARS = 3  # "last 3 years" window used for the actual comparisons
