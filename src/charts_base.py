"""
Shared helpers for dynamic, interactive charts embedded in the Tk interface.

The module provides a consistent theme, optional hover tooltips and seaborn
styling, semicircular gauges, timeline fills, and a shared color palette.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
import matplotlib.ticker as mticker
import numpy as np

try:
    import seaborn as sns
    _HAS_SEABORN = True
except ImportError:
    _HAS_SEABORN = False


# ============================================================
# Color palette
# ============================================================

COLORS = {
    "alto":      "#e74c3c",
    "medio":     "#f39c12",
    "bajo":      "#27ae60",
    "primary":   "#2563eb",
    "secondary": "#7c3aed",
    "accent":    "#0891b2",
    "accent2":   "#ea580c",
    "neutral":   "#64748b",
    "bg":        "#f0f4f8",
    "bg_card":   "#ffffff",
    "text":      "#1e293b",
    "grid":      "#e2e8f0",
    "border":    "#cbd5e1",
    "fg_dim":    "#64748b",
}

RISK_PALETTE = [COLORS["bajo"], COLORS["medio"], COLORS["alto"]]

# Global rcParams for a clean, modern appearance.
plt.rcParams.update({
    "font.family":          "DejaVu Sans",
    "font.size":            9,
    "axes.titlesize":       11,
    "axes.titleweight":     "bold",
    "axes.labelsize":       8.5,
    "xtick.direction":      "out",
    "ytick.direction":      "out",
    "xtick.labelsize":      8,
    "ytick.labelsize":      8,
    "lines.linewidth":      2.0,
    "lines.solid_capstyle": "round",
    "legend.framealpha":    0.9,
    "legend.fontsize":      8,
    "legend.borderpad":     0.5,
    "figure.dpi":           100,
    "savefig.dpi":          150,
    "savefig.bbox":         "tight",
})


# ============================================================
# Internal helpers
# ============================================================

def _apply_dark_style(fig: Figure, axes=None):
    """Apply the theme and subtle grid styling to a figure and its axes."""
    fig.patch.set_facecolor(COLORS["bg"])
    ax_list = axes if axes is not None else fig.get_axes()
    if not isinstance(ax_list, (list, tuple, np.ndarray)):
        ax_list = [ax_list]
    for ax in ax_list:
        ax.set_facecolor(COLORS["bg_card"])
        ax.tick_params(colors=COLORS["text"], labelsize=8, length=3, width=0.6)
        ax.xaxis.label.set_color(COLORS["text"])
        ax.yaxis.label.set_color(COLORS["text"])
        ax.title.set_color(COLORS["text"])
        # Keep only subtle left and bottom spines.
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_edgecolor(COLORS["grid"])
        ax.spines["left"].set_linewidth(0.8)
        ax.spines["bottom"].set_edgecolor(COLORS["grid"])
        ax.spines["bottom"].set_linewidth(0.8)
        # Draw the grid behind the data
        ax.grid(color=COLORS["grid"], linestyle="-", linewidth=0.4, alpha=0.5)
        ax.set_axisbelow(True)


def _kde_line(values: list, x_min: float = 0, x_max: float = 100,
              bandwidth: float = 8, n_points: int = 300):
    """Return a NumPy-only Gaussian KDE scaled to observations and bin width."""
    if len(values) < 2:
        return np.array([]), np.array([])
    x = np.linspace(x_min, x_max, n_points)
    bin_width = (x_max - x_min) / 10.0  # 10 bins
    y = np.zeros_like(x)
    for v in values:
        y += np.exp(-0.5 * ((x - v) / bandwidth) ** 2)
    # Normalize to probability density, then rescale to frequency.
    y /= (len(values) * bandwidth * np.sqrt(2 * np.pi))
    y *= len(values) * bin_width
    return x, y


def _draw_semicircle_gauge(ax, value_pct: float, color: str,
                            title: str, sublabel: str = ""):
    """Draw a semicircular gauge filled clockwise for a value from 0 to 100."""
    frac = max(0.0, min(1.0, value_pct / 100.0))
    # Three sectors: filled, empty upper arc, and hidden lower semicircle.
    # Total normalizado = 2.0 (top half = 1.0, bottom half = 1.0)
    sizes = [max(frac, 0.001), max(1.0 - frac, 0.001), 1.0]
    pie_colors = [color, COLORS["border"], COLORS["bg"]]

    wedges, _ = ax.pie(
        sizes,
        colors=pie_colors,
        startangle=180,
        counterclock=False,
        wedgeprops={"width": 0.38, "edgecolor": COLORS["bg"], "linewidth": 1.5},
        radius=1.0,
    )
    # Hide the lower half
    wedges[2].set_alpha(0.0)

    # Crop the view to the upper half
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-0.22, 1.25)

    # Center value.
    ax.text(0, 0.32, f"{value_pct:.0f}%",
            ha="center", va="center",
            fontsize=22, fontweight="bold", color=color)
    ax.text(0, 0.02, title,
            ha="center", va="center",
            fontsize=9, color=COLORS["text"], fontweight="bold")
    if sublabel:
        ax.text(0, -0.14, sublabel,
                ha="center", va="center",
                fontsize=7.5, color=COLORS["fg_dim"], style="italic")

    # Endpoint labels.
    ax.text(-1.2, -0.12, "0%", ha="center", fontsize=7, color=COLORS["fg_dim"])
    ax.text( 1.2, -0.12, "100%", ha="center", fontsize=7, color=COLORS["fg_dim"])
    ax.axis("off")


def _style_seaborn_colorbar(ax):
    """Apply the theme to a seaborn-generated color bar."""
    try:
        cbar = ax.collections[0].colorbar
        if cbar is not None:
            cbar.ax.set_facecolor(COLORS["bg"])
            cbar.ax.tick_params(colors=COLORS["text"], labelsize=7, length=2)
            plt.setp(cbar.ax.yaxis.get_ticklabels(), color=COLORS["text"])
            for spine in cbar.ax.spines.values():
                spine.set_edgecolor(COLORS["grid"])
    except (IndexError, AttributeError):
        pass
