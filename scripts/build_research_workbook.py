"""
Builds data/manual/research_workbook.xlsx — a fill-in workbook for the
three manual-desk-research datasets this project needs (FDI, LBO deals,
and macro GDP/CPI series discovery), since none of these can be pulled
from an API (see src/macro/gdp_inflation.py, src/macro/fdi_manual.py
and src/lbo/lbo_manual.py's docstrings for why).

This is a ONE-TIME GENERATOR, kept for reproducibility (same convention
as scripts/build_legal_form_mapping.py) — re-run it to regenerate a
blank workbook; it does not read or preserve anything a researcher has
already filled in. Column names/order in the FDI and LBO Deals sheets
must exactly match REQUIRED_COLUMNS in src/macro/fdi_manual.py and
src/lbo/lbo_manual.py — if those change, update this script too.

Usage:
    python scripts/build_research_workbook.py
"""

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common.sectors import NAF_WZ_SECTION_LABELS

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "manual" / "research_workbook.xlsx"

FONT_NAME = "Arial"
PRIMARY_COLOR = "162B2B"    # dark teal — matches src/common/plotting.py's brand palette
SECONDARY_COLOR = "7FA087"  # sage
EXAMPLE_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")  # light yellow
HEADER_FILL = PatternFill(start_color=PRIMARY_COLOR, end_color=PRIMARY_COLOR, fill_type="solid")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF")
TITLE_FONT = Font(name=FONT_NAME, bold=True, size=14, color=PRIMARY_COLOR)
NOTE_FONT = Font(name=FONT_NAME, italic=True, size=9, color="666666")
BODY_FONT = Font(name=FONT_NAME, size=10)
WRAP = Alignment(wrap_text=True, vertical="top")

REGIONS_NOTE = (
    "France GDP/FDI has no official department-level figure (INSEE's finest granularity "
    "is the REGION, Grand Est) — use \"Grand Est\" as the proxy for Bas-Rhin/Haut-Rhin/"
    "Moselle unless your source specifically reports one of those departments. Regions to "
    "use: Grand Est, France (national), Baden-Württemberg (Land)."
)


def _set_col_widths(ws, widths: dict):
    for col_letter, width in widths.items():
        ws.column_dimensions[col_letter].width = width


def _style_header_row(ws, row: int, n_cols: int):
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def build_instructions_sheet(wb: Workbook):
    ws = wb.active
    ws.title = "Instructions"
    ws.sheet_view.showGridLines = False
    _set_col_widths(ws, {"A": 100})

    row = 1
    ws.cell(row=row, column=1, value="Manual Research Workbook — Strasbourg Business Analysis").font = TITLE_FONT
    row += 2

    intro = (
        "Three axes in this project have no public API and are documented as desk-research-only: "
        "FDI (Foreign Direct Investment), LBO (Leveraged Buy-Out) deals, and the macro GDP/CPI series "
        "idbank discovery. This workbook is where that research gets recorded — one tab per dataset."
    )
    ws.cell(row=row, column=1, value=intro).font = BODY_FONT
    ws.cell(row=row, column=1).alignment = WRAP
    ws.row_dimensions[row].height = 40
    row += 2

    ws.cell(row=row, column=1, value="How to use this workbook").font = Font(name=FONT_NAME, bold=True, size=12)
    row += 1
    steps = [
        "1. Go to the relevant tab (FDI, LBO Deals, or Macro GDP-CPI Tracker).",
        "2. Row 2 (yellow fill) on each data tab is a worked EXAMPLE, not real data — delete it before finalizing.",
        "3. Add one row per data point you find. Every row MUST cite a source_url — rows without one are "
        "rejected by the project's own loader (src/macro/fdi_manual.py / src/lbo/lbo_manual.py).",
        "4. When a tab is ready, export just that sheet as CSV (File > Save As > CSV, or copy into a new "
        "sheet and Save As) to the exact path named at the top of that tab, matching column names/order exactly.",
        "5. Send the CSV(s) back so they can be validated (load_and_validate()) and charted.",
    ]
    for step in steps:
        ws.cell(row=row, column=1, value=step).font = BODY_FONT
        ws.cell(row=row, column=1).alignment = WRAP
        ws.row_dimensions[row].height = 28
        row += 1
    row += 1

    ws.cell(row=row, column=1, value="Region names to use").font = Font(name=FONT_NAME, bold=True, size=12)
    row += 1
    ws.cell(row=row, column=1, value=REGIONS_NOTE).font = BODY_FONT
    ws.cell(row=row, column=1).alignment = WRAP
    ws.row_dimensions[row].height = 40
    row += 2

    ws.cell(row=row, column=1, value="Sector reference (for the LBO Deals tab)").font = Font(name=FONT_NAME, bold=True, size=12)
    row += 1
    ws.cell(row=row, column=1, value="Use the single-letter NAF/WZ section code, not a free-text sector name — "
                                      "the same codes used throughout the rest of this project:").font = BODY_FONT
    row += 1
    for letter, label in NAF_WZ_SECTION_LABELS.items():
        ws.cell(row=row, column=1, value=f"  {letter} — {label}").font = BODY_FONT
        row += 1
    row += 1

    ws.cell(row=row, column=1, value="Caveats").font = Font(name=FONT_NAME, bold=True, size=12)
    row += 1
    caveats = [
        "- FDI/GDP figures at Grand Est or Baden-Württemberg level are not directly comparable in absolute "
        "terms to the 3 French departments — note this explicitly wherever these numbers are charted.",
        "- Prefer a real disclosed EUR value over an estimate; if only a project COUNT is available "
        "(e.g. Business France's regional attractiveness reports), leave value_eur blank and note the "
        "count in the notes column instead of guessing a euro figure.",
        "- If a figure is provisional/preliminary (common for the most recent year), say so in notes.",
    ]
    for c in caveats:
        ws.cell(row=row, column=1, value=c).font = BODY_FONT
        ws.cell(row=row, column=1).alignment = WRAP
        ws.row_dimensions[row].height = 28
        row += 1


def build_fdi_sheet(wb: Workbook):
    ws = wb.create_sheet("FDI")
    ws.sheet_view.showGridLines = False

    ws.cell(row=1, column=1, value="Target file: data/manual/fdi.csv").font = NOTE_FONT
    ws.cell(row=2, column=1, value=(
        "Sourcing: Banque de France balance-of-payments FDI stats (France, national only) · "
        "Deutsche Bundesbank FDI stats + GTAI regional investment reports (Baden-Württemberg) · "
        "Business France \"Bilan de l'attractivité\" (regional project counts, Grand Est proxy)."
    )).font = NOTE_FONT
    ws.cell(row=2, column=1).alignment = WRAP
    ws.row_dimensions[2].height = 28

    header_row = 4
    columns = ["year", "region", "flow_direction", "value_eur", "source_url", "notes"]
    for i, col in enumerate(columns, start=1):
        ws.cell(row=header_row, column=i, value=col)
    _style_header_row(ws, header_row, len(columns))

    example_row = header_row + 1
    example_values = [
        2024, "France (national)", "inbound", 34_000_000_000,
        "https://www.banque-france.fr/en/statistics/balance-payments-and-international-investment-position",
        "EXAMPLE ROW — DELETE. Illustrates a national-level figure with flow_direction spelled exactly "
        "'inbound' (required, not 'in'/'Inbound').",
    ]
    for i, val in enumerate(example_values, start=1):
        cell = ws.cell(row=example_row, column=i, value=val)
        cell.fill = EXAMPLE_FILL
        cell.font = BODY_FONT
        if i == len(example_values):
            cell.alignment = WRAP

    _set_col_widths(ws, {"A": 8, "B": 22, "C": 14, "D": 16, "E": 45, "F": 45})
    ws.freeze_panes = f"A{example_row + 1}"


def build_lbo_sheet(wb: Workbook):
    ws = wb.create_sheet("LBO Deals")
    ws.sheet_view.showGridLines = False

    ws.cell(row=1, column=1, value="Target file: data/manual/lbo_deals.csv").font = NOTE_FONT
    ws.cell(row=2, column=1, value=(
        "Sourcing: Les Echos Capital Finance, Unquote, F&A Aktuell (Germany) · law firm / M&A boutique "
        "\"deals of the year\" summaries active in Alsace/Baden-Württemberg · Bodacc can corroborate a deal "
        "already found elsewhere (e.g. a holding-company creation) but is not a reliable primary signal."
    )).font = NOTE_FONT
    ws.cell(row=2, column=1).alignment = WRAP
    ws.row_dimensions[2].height = 28

    header_row = 4
    columns = ["date", "department_or_region", "sector", "target", "sponsor", "value_eur", "source_url"]
    for i, col in enumerate(columns, start=1):
        ws.cell(row=header_row, column=i, value=col)
    _style_header_row(ws, header_row, len(columns))

    example_row = header_row + 1
    example_values = [
        "2024-06-15", "Bas-Rhin", "C", "Example Target SAS", "Example Capital Partners",
        45_000_000, "https://example.com/press-release",
    ]
    for i, val in enumerate(example_values, start=1):
        cell = ws.cell(row=example_row, column=i, value=val)
        cell.fill = EXAMPLE_FILL
        cell.font = BODY_FONT
    ws.cell(row=example_row, column=len(example_values) + 1,
             value="EXAMPLE ROW — DELETE. sector is a single NAF/WZ letter (see Instructions tab), "
                   "not a free-text description.").font = NOTE_FONT
    ws.cell(row=example_row, column=len(example_values) + 1).alignment = WRAP

    _set_col_widths(ws, {"A": 12, "B": 20, "C": 8, "D": 24, "E": 24, "F": 16, "G": 40, "H": 55})
    ws.freeze_panes = f"A{example_row + 1}"


def build_macro_tracker_sheet(wb: Workbook):
    ws = wb.create_sheet("Macro GDP-CPI Tracker")
    ws.sheet_view.showGridLines = False

    ws.cell(row=1, column=1, value="Not a CSV target — this tracks discovery progress toward src/macro/gdp_inflation.py").font = NOTE_FONT
    ws.cell(row=2, column=1, value=(
        "For France: search insee.fr for \"Produit intérieur brut régional\" (GDP) and \"indice des prix à la "
        "consommation\" (CPI), open the Grand Est and France entière series pages, and note the idbank from "
        "the page URL or the CSV export. For Germany: use bw.search_statistics_by_prefix('82') / "
        "gi.search_statistics_by_keyword() then inspect_table_metadata() on the candidate table, same as the "
        "rest of this project's GENESIS tables."
    )).font = NOTE_FONT
    ws.cell(row=2, column=1).alignment = WRAP
    ws.row_dimensions[2].height = 40

    header_row = 4
    columns = ["metric", "region", "idbank_or_table_code", "source_url", "status", "notes"]
    for i, col in enumerate(columns, start=1):
        ws.cell(row=header_row, column=i, value=col)
    _style_header_row(ws, header_row, len(columns))

    example_row = header_row + 1
    example_values = [
        "GDP", "Grand Est", "001234567", "https://www.insee.fr/fr/statistiques/serie/001234567",
        "found", "EXAMPLE ROW — DELETE. status should be one of: pending / found / fetched.",
    ]
    for i, val in enumerate(example_values, start=1):
        cell = ws.cell(row=example_row, column=i, value=val)
        cell.fill = EXAMPLE_FILL
        cell.font = BODY_FONT
        if i == len(example_values):
            cell.alignment = WRAP

    # Blank starter rows for the 6 series this axis needs at minimum.
    starter_rows = [
        ("GDP", "Grand Est", "", "", "pending", ""),
        ("GDP", "France (national)", "", "", "pending", ""),
        ("GDP", "Baden-Württemberg (Land)", "", "", "pending", ""),
        ("CPI", "Grand Est", "", "", "pending", ""),
        ("CPI", "France (national)", "", "", "pending", ""),
        ("CPI", "Baden-Württemberg (Land)", "", "", "pending", ""),
    ]
    for offset, values in enumerate(starter_rows, start=1):
        r = example_row + offset
        for i, val in enumerate(values, start=1):
            ws.cell(row=r, column=i, value=val).font = BODY_FONT

    _set_col_widths(ws, {"A": 10, "B": 24, "C": 20, "D": 45, "E": 12, "F": 45})
    ws.freeze_panes = f"A{example_row + 1}"


def main():
    wb = Workbook()
    build_instructions_sheet(wb)
    build_fdi_sheet(wb)
    build_lbo_sheet(wb)
    build_macro_tracker_sheet(wb)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
