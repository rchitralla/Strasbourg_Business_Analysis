"""
Cohort survival rate — what share of enterprises created in year Y are
still administratively active today, per French department.

Not an explicit Data Room brief question, but proposed during this
project's own methodology discussion as a cleaner "market saturation"
signal than a churn ratio: it doesn't need the failures axis's opening-
judgment classification to be sorted out first, and it's a more
intuitive story for a non-technical audience ("of the companies that
opened in Strasbourg in 2018, X% are still standing").

WHY THIS NEEDS A SEPARATE FETCH, NOT THE EXISTING CACHED CSVs:
sirene_v3_client.build_dataframe() aggregates raw établissement records
into COUNTS per (year, region, sector, legal_form) and discards the
individual record — including uniteLegale.etatAdministratifUniteLegale
("A"=active, "C"=cessée), which is the one field this module actually
needs. That field was never dropped by INSEE, only by our own
aggregation step. So computing survival means re-fetching each
department via sv3.fetch_establishments() (already uncapped, enterprise-
corrected, retry-safe against 429s — see sirene_v3_client.py) and
extracting status this time, rather than reusing the already-cached
data/processed/*_enterprises.csv files. This roughly doubles the API
cost for whatever year range you choose — pass a narrower min_year/
max_year (e.g. one or two cohort years) for a cheap pilot before
committing to the full 2015-2026 range.

CRITICAL CAVEAT — read before charting this as a trend over years:
"survival as of today" is NOT the same maturity for every cohort. A
2025 cohort has had almost no time to fail, so it will look
artificially healthier than a 2016 cohort that's had a decade to
churn. Comparing raw current-status share by creation year will look
like "companies are getting more resilient over time" when it's
really just younger cohorts not having failed YET. Prefer comparing
cohorts at the SAME AGE (e.g. "share still active 3 years after
creation") across departments/regions for the same creation year,
rather than eyeballing survival rate against calendar year.

Usage:
    from src.company_creation import sirene_v3_client as sv3
    from src.company_creation import survival_rate as surv
    sv3.set_api_key()

    df = surv.collect_all_departments(min_year=2018, max_year=2020)  # cheap pilot first
    df = surv.filter_business_entities(df)  # drop VAT-only/public-body/cooperative-union rows
    summary = surv.build_summary(df)

    # optional: a period life table (age-indexed survival curve + hazard
    # rate) instead of / alongside the raw calendar-year summary --
    # see build_life_table()'s docstring for what this is and its limits
    life_table = surv.build_life_table(summary)
    surv.plot_life_table(life_table)
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.company_creation import sirene_v3_client as sv3
from config.regions import FRENCH_DEPARTMENTS, MIN_YEAR, MAX_YEAR

ACTIVE = "A"
CEASED = "C"


def extract_row(record: dict) -> dict | None:
    """
    Pulls creation year, CURRENT administrative status, and legal form
    from one raw établissement record — records here are already
    siège-filtered and enterprise-corrected by sv3.fetch_establishments()'s
    own query, so this is one row per new enterprise, not per
    établissement.

    legal_form / legal_form_label / category / exclude_from_business_counts
    reuse sirene_v3_client's own official INSEE nomenclature and manual
    review (see sv3.LEGAL_FORM_LABELS / sv3.CATEGORY_BY_CODE /
    sv3.EXCLUDE_FROM_BUSINESS_COUNTS_BY_CODE) rather than duplicating that
    mapping here — this is the SAME lookup collect_all_departments() in
    sirene_v3_client.py already uses for the company-creation axis, so a
    legal form excluded there (VAT-only registrations, public bodies,
    indivisions, professional orders, and — as of 2026-09-19 — the four
    "union de sociétés coopératives" codes 5459/5559/5659/6318, which are
    federations of EXISTING cooperatives, not new standalone companies)
    is excluded here identically. See filter_business_entities() below.
    """
    unite_legale = record.get("uniteLegale") or {}
    date_creation = unite_legale.get("dateCreationUniteLegale")
    if not date_creation:
        return None
    try:
        year = int(date_creation[:4])
    except (ValueError, TypeError):
        return None

    legal_form_code_raw = unite_legale.get("categorieJuridiqueUniteLegale")
    legal_form = str(legal_form_code_raw) if legal_form_code_raw else "?"

    return {
        "year": year,
        "siren": record.get("siren"),
        "etat": unite_legale.get("etatAdministratifUniteLegale"),  # "A" active / "C" cessée
        "legal_form": legal_form,
        "legal_form_label": sv3.LEGAL_FORM_LABELS.get(legal_form),
        "category": sv3.CATEGORY_BY_CODE.get(legal_form, ""),
        "exclude_from_business_counts": sv3.EXCLUDE_FROM_BUSINESS_COUNTS_BY_CODE.get(legal_form, False),
    }


def build_dataframe(records: list[dict], region_name: str) -> pd.DataFrame:
    rows = []
    for record in records:
        row = extract_row(record)
        if row is None:
            continue
        row["region"] = region_name
        rows.append(row)
    return pd.DataFrame(rows)


def filter_business_entities(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drops rows whose legal form isn't a genuine new-business creation in
    the Data Room brief's sense — VAT-only registrations, public bodies,
    indivisions, professional orders, cooperative unions, etc. Call this
    BEFORE build_summary() if you want survival rates computed only over
    real companies:

        df = surv.collect_all_departments(min_year=2015, max_year=2021)
        df = surv.filter_business_entities(df)
        summary = surv.build_summary(df)

    Safe to skip if you deliberately want every legal form Sirene
    registers (e.g. to report the excluded count itself).
    """
    if df.empty or "exclude_from_business_counts" not in df.columns:
        return df
    excluded_count = int(df["exclude_from_business_counts"].sum())
    if excluded_count:
        print(f"Dropping {excluded_count} row(s) with a non-business legal form "
              f"(VAT-only, public body, cooperative union, etc.) — "
              f"{len(df) - excluded_count} remain.")
    return df[~df["exclude_from_business_counts"]].reset_index(drop=True)


def _department_cache_path(dept_code: str, min_year: int, max_year: int) -> str:
    # Year range in the cache key: a survival snapshot is only valid for
    # the exact window it was fetched over, and "as of today" means the
    # cache also goes stale over time in a way most other caches in this
    # project don't — re-fetch (resume=False) if it's been a while.
    #
    # "_lf" suffix added 2026-09-19 when legal_form/category/
    # exclude_from_business_counts columns were added — a cache file from
    # before that change has neither column, and filter_business_entities()
    # would silently no-op against it (missing column, not "nothing to
    # exclude"). The suffix forces a clean re-fetch instead of a resumed
    # load from an old-shaped CSV.
    return f"data/processed/survival_dept_{dept_code}_{min_year}_{max_year}_lf.csv"


def collect_all_departments(min_year: int = MIN_YEAR, max_year: int = MAX_YEAR, resume: bool = True) -> pd.DataFrame:
    """
    Fetch + tidy (creation_year, region, siren, etat) for every French
    department in config.regions.FRENCH_DEPARTMENTS. Requires
    sv3.set_api_key() first. See module docstring for the re-fetch cost
    caveat — pass a narrow min_year/max_year for a cheap pilot.
    """
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    frames = []
    for dept in FRENCH_DEPARTMENTS.values():
        csv_path = _department_cache_path(dept.insee_code, min_year, max_year)
        if resume and Path(csv_path).exists():
            print(f"\n{dept.name}: already fetched, loading from {csv_path} "
                  f"(pass resume=False to refresh — this snapshot goes stale over time, "
                  f"unlike most other caches in this project, since 'active' status changes daily).")
            frames.append(pd.read_csv(csv_path))
            continue

        print(f"\nFetching enterprise creations + current status for {dept.name} "
              f"(dept code {dept.insee_code}), {min_year}-{max_year}...")
        records, complete = sv3.fetch_establishments(dept.insee_code, min_year=min_year, max_year=max_year)
        print(f"  Total records retrieved: {len(records)} (complete: {complete})")
        dept_df = build_dataframe(records, dept.name)

        if complete:
            dept_df.to_csv(csv_path, index=False)
            print(f"  Saved: {csv_path}")
        else:
            print("  NOT caching — this department's fetch was incomplete. Re-run to retry.")
        frames.append(dept_df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per (creation_year, region): total companies, how many are still
    active, how many have ceased, and the resulting survival_rate.
    Read the module docstring's cohort-age caveat before charting this
    against calendar year.
    """
    if df.empty:
        return pd.DataFrame()

    summary = df.groupby(["year", "region"]).agg(
        total=("etat", "size"),
        active=("etat", lambda s: int((s == ACTIVE).sum())),
        ceased=("etat", lambda s: int((s == CEASED).sum())),
    ).reset_index()
    summary["other_status"] = summary["total"] - summary["active"] - summary["ceased"]
    summary["survival_rate"] = summary["active"] / summary["total"]
    return summary.sort_values(["year", "region"]).reset_index(drop=True)


def build_life_table(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Turns the cross-sectional cohort summary into an approximate
    survival-by-age curve -- a "period life table" / synthetic-cohort
    estimate, the practical substitute for a true Kaplan-Meier curve
    when all you have is each cohort's CURRENT status rather than an
    exact date of cessation per company (see module docstring).

    Each row of `summary` is one (creation_year, region) cohort with
    its own survival_rate, measured at THAT cohort's own age today
    (age = current_year - creation_year). Splicing one age-point per
    cohort together approximates S(age) for the region -- but this
    splices DIFFERENT COHORTS at each age, not one cohort followed over
    its own life, so it conflates a true age effect with any genuine
    difference between cohorts (e.g. a cohort founded in a worse economic
    year would look like "this age is riskier" even though age itself
    changed nothing). State this explicitly if you present S(age) as a
    survival curve -- it is the standard, named limitation of a period
    life table versus a cohort life table, not a bug in this code.

    Also NOTE this only covers whatever age range your cohorts happen to
    span (e.g. ages 5-11 for creation years 2015-2021, fetched in
    2026) -- it is a partial life table, not one starting from age 0,
    and it says nothing about survival at ages outside that observed
    range.

    Adds two columns to a copy of `summary`:
      age          = current_year - creation_year
      hazard_rate  = the discrete hazard between this age and the next
                     OLDER observed age in the same region:
                     h = 1 - S(age_next)/S(age) -- "probability of
                     failing between these two ages, given survival to
                     the younger one." NaN for the oldest age per region
                     (no older point to compare against). CAN come out
                     negative if survival_rate happens to rise with age
                     in the raw data -- that is a real signal that
                     cohort-quality differences are swamping the age
                     effect for that pair, not a bug -- report it as-is
                     rather than clipping it to zero.
    """
    from datetime import date

    if summary.empty:
        return summary.copy()

    current_year = date.today().year
    table = summary.copy()
    table["age"] = current_year - table["year"]
    table = table.sort_values(["region", "age"]).reset_index(drop=True)
    table["hazard_rate"] = None

    for _, group in table.groupby("region"):
        group = group.sort_values("age")
        s = group["survival_rate"].values
        idx = group.index
        for i in range(len(s) - 1):
            table.loc[idx[i], "hazard_rate"] = 1 - (s[i + 1] / s[i]) if s[i] else None

    return table[["region", "year", "age", "total", "active", "ceased", "survival_rate", "hazard_rate"]]


def plot_life_table(table: pd.DataFrame, output_path: str = "outputs/charts/survival_life_table.png"):
    """
    Two-panel chart: survival curve S(age) (step function, one line per
    region) on top, discrete hazard rate h(age) on bottom. Same brand
    dark theme used for the cohort-size/survival chart built earlier
    this project. Read build_life_table()'s docstring for the
    cohort-vs-age caveat before presenting this as a "true" survival
    curve to an audience.
    """
    import matplotlib.pyplot as plt
    from pathlib import Path as _Path

    BG_COLOR = "#162B2B"
    TEXT_COLOR = "#F5F5F0"
    MUTED_TEXT = "#B9C4BE"
    GRID_COLOR = "#2A413F"
    REGION_COLORS = {
        "Bas-Rhin": "#7FA087",
        "Haut-Rhin": "#5B8FB9",
        "Moselle": "#E0A458",
    }

    fig, (ax_surv, ax_haz) = plt.subplots(
        2, 1, figsize=(9, 8), sharex=True, gridspec_kw={"height_ratios": [1, 1]}
    )
    fig.patch.set_facecolor(BG_COLOR)
    for ax in (ax_surv, ax_haz):
        ax.set_facecolor(BG_COLOR)

    for region, color in REGION_COLORS.items():
        sub = table[table["region"] == region].sort_values("age")
        if sub.empty:
            continue
        ax_surv.step(sub["age"], sub["survival_rate"] * 100, where="post",
                     color=color, linewidth=2, label=region)
        ax_surv.plot(sub["age"], sub["survival_rate"] * 100, "o", color=color, markersize=5)

        haz = sub.dropna(subset=["hazard_rate"])
        if not haz.empty:
            ax_haz.plot(haz["age"], haz["hazard_rate"].astype(float) * 100, marker="o",
                        markersize=5, linewidth=2, color=color, label=region)

    ax_surv.set_ylabel("Survival rate S(age) (%)", color=TEXT_COLOR)
    ax_surv.set_title("Survival curve by age (synthetic cohort / period life table)",
                       loc="left", fontsize=11, color=MUTED_TEXT)
    ax_haz.axhline(0, color=GRID_COLOR, linewidth=1)
    ax_haz.set_ylabel("Hazard rate (%)", color=TEXT_COLOR)
    ax_haz.set_xlabel("Age (years since creation)", color=TEXT_COLOR)
    ax_haz.set_title("Discrete hazard rate between observed ages", loc="left",
                      fontsize=11, color=MUTED_TEXT)

    for ax in (ax_surv, ax_haz):
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.tick_params(colors=TEXT_COLOR)

    fig.subplots_adjust(top=0.82, hspace=0.35)
    fig.suptitle("Company survival by age — Alsace-Moselle", y=0.97, fontsize=13, color=TEXT_COLOR)

    handles, labels = ax_surv.get_legend_handles_labels()
    legend = fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False,
                         bbox_to_anchor=(0.5, 0.90), fontsize=10)
    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)

    fig.text(0.5, 0.86,
              "Synthetic-cohort estimate: each age point comes from a DIFFERENT cohort, not one cohort tracked over time",
              ha="center", fontsize=8, style="italic", color=MUTED_TEXT)

    _Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved: {output_path}")
