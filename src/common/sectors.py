"""
Shared sector-classification labels.

French NAF (rev. 2) "sections" and German WZ 2008 "Abschnitte" both derive
from the EU's NACE Rev. 2 nomenclature, so the same A-U letter code maps to
the same broad sector in both countries. Centralizing the mapping here
keeps French and German charts using identical sector labels, which is
what makes the two sides of the comparison legible side by side.
"""

NAF_WZ_SECTION_LABELS = {
    "A": "Agriculture, forestry, fishing",
    "B": "Mining & quarrying",
    "C": "Manufacturing",
    "D": "Energy (electricity, gas, steam)",
    "E": "Water supply & waste management",
    "F": "Construction",
    "G": "Retail & wholesale trade",
    "H": "Transportation & storage",
    "I": "Accommodation & food service",
    "J": "Information & communication",
    "K": "Finance & insurance",
    "L": "Real estate",
    "M": "Professional, scientific & technical",
    "N": "Administrative & support services",
    "O": "Public administration",
    "P": "Education",
    "Q": "Human health & social work",
    "R": "Arts, entertainment & recreation",
    "S": "Other services",
    "T": "Household employers",       # France only (Sirene covers this)
    "U": "Extraterritorial organizations",
}

# French legal forms relevant to the "constitutions d'entreprises" axis.
FRENCH_LEGAL_FORMS = {
    "EURL": "Entreprise Unipersonnelle à Responsabilité Limitée (sole-shareholder SARL)",
    "SARL": "Société à Responsabilité Limitée",
    "SASU": "Société par Actions Simplifiée Unipersonnelle (sole-shareholder SAS)",
    "SAS": "Société par Actions Simplifiée",
    "SCI": "Société Civile Immobilière (real estate; requires 2+ shareholders)",
}

# Legal forms that by definition have a single associate/shareholder —
# used to compute the "share of companies created with multiple partners"
# question (B18 in the Data Room sheet).
SOLE_SHAREHOLDER_FORMS = {"EURL", "SASU", "EI"}  # EI = entreprise individuelle
