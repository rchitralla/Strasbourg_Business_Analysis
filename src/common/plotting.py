"""
Shared chart styling so every axis (macro, M&A, company creation, LBO)
produces PowerPoint-ready PNGs that look like one deck, not five.
"""

import matplotlib.pyplot as plt
import pandas as pd

FIGSIZE = (12, 6.75)  # 16:9, fits a PPT slide
DPI = 200

# One consistent color per geography across every chart in the project.
REGION_COLORS = {
    "Bas-Rhin": "#2E5EAA",
    "Haut-Rhin": "#4E8AD4",
    "Moselle": "#7FB2E5",
    "France (national)": "#888888",
    "Baden-Württemberg (Land)": "#A63A3A",
}


def new_figure():
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.spines[["top", "right"]].set_visible(False)
    return fig, ax


def save(fig, output_path: str):
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
