"""
Shared chart styling so every axis (macro, M&A, company creation, LBO)
produces PowerPoint-ready PNGs that look like one deck, not five.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

FIGSIZE = (12, 6.75)  # 16:9, fits a PPT slide
DPI = 200

# Brand palette (set 2026-09-12) — every chart in the project derives its
# colors from these two anchors, not arbitrary/independent hex values.
PRIMARY_COLOR = "#162B2B"    # dark teal — used for single-series charts
                              # and as the most visually prominent series
SECONDARY_COLOR = "#7FA087"  # sage — the lighter anchor

# One consistent color per geography across every chart in the project,
# interpolated between SECONDARY_COLOR (lightest) and PRIMARY_COLOR
# (darkest) so the whole family stays within the two brand colors.
REGION_COLORS = {
    "Bas-Rhin": "#B9CBBD",
    "Haut-Rhin": SECONDARY_COLOR,
    "Moselle": "#456054",
    "France (national)": "#DFE7E1",
    "Baden-Württemberg (Land)": PRIMARY_COLOR,
}

# For charts with an arbitrary/unknown number of categories (e.g. a
# stacked bar with N reason categories) — interpolates smoothly between
# the two brand colors instead of falling back to an unrelated
# matplotlib colormap like "tab20".
BRAND_COLORMAP = LinearSegmentedColormap.from_list("brand", [SECONDARY_COLOR, PRIMARY_COLOR])


def new_figure():
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.spines[["top", "right"]].set_visible(False)
    return fig, ax


def save(fig, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


def grouped_region_bar(df: pd.DataFrame, value_col: str, title: str, ylabel: str, output_path: str):
    """
    df: tidy frame with columns ["year", "region", value_col].
    Renders one bar-group per year, one bar per region, using REGION_COLORS.
    """
    pivot = df.pivot_table(index="year", columns="region", values=value_col, aggfunc="sum")
    colors = [REGION_COLORS.get(c, "#333333") for c in pivot.columns]

    fig, ax = new_figure()
    pivot.plot(kind="bar", ax=ax, color=colors, width=0.8)
    ax.set_title(title, fontsize=15, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel(ylabel)
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9, title="Region")
    save(fig, output_path)
