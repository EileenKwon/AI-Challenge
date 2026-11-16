"""Shared matplotlib style (reference categorical palette, recessive axes)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e4e3df"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def apply() -> None:
    """Apply the project style globally."""
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": TEXT2,
            "axes.labelcolor": TEXT,
            "axes.titlecolor": TEXT,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.color": TEXT2,
            "ytick.color": TEXT2,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "lines.linewidth": 2.0,
            "legend.frameon": False,
            "legend.fontsize": 8.5,
            "font.size": 9.5,
        }
    )


def save(fig, path, dpi: int = 160) -> None:
    """Save and close a figure."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
