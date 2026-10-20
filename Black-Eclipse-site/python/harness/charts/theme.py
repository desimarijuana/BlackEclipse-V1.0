"""The Eclipse chart THEME — the design system's palette, in matplotlib terms.

The app's look is a dark frosted surface with light ink. A matplotlib figure
painted with its defaults (white background, black text, tab colours) looks
like a screenshot from another product, so every figure is painted with THIS
theme instead.

Two rules shape it:

* **The background is transparent.** The figure is dropped onto a frosted glass
  card, and an opaque white rectangle would destroy the frost. Text is light
  because the surface behind it is dark.
* **The light theme is a real theme, not an inversion.** It exists because the
  app has a light mode, and a chart that is unreadable in light mode is a
  broken chart — not a cosmetic detail.

The palette below is the same family the UI uses (`.glass-card` ink
`#e5e7eb`, muted `#94a3b8`, cyan `#0ea5e9`, green `#22c55e`, rose `#e11d48`,
violet `#a78bfa`, amber `#f59e0b`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: The categorical series palette — ordered so that neighbouring series never
#: land on the same hue, and the first two (cyan, violet) read well against
#: the frosted dark surface.
SERIES_COLORS: tuple[str, ...] = (
    "#0ea5e9",  # sky
    "#a78bfa",  # violet
    "#22c55e",  # green
    "#f59e0b",  # amber
    "#e11d48",  # rose
    "#14b8a6",  # teal
    "#f472b6",  # pink
    "#60a5fa",  # blue
    "#a3e635",  # lime
    "#fb923c",  # orange
)

#: Market direction. Up is green, down is rose — the app's convention.
UP_COLOR = "#22c55e"
DOWN_COLOR = "#e11d48"


@dataclass(frozen=True)
class ChartTheme:
    """One palette + rcParams set."""

    name: str
    ink: str
    muted: str
    grid: str
    axis: str
    surface: Optional[str] = None          # None = transparent
    up: str = UP_COLOR
    down: str = DOWN_COLOR
    palette: tuple[str, ...] = SERIES_COLORS
    #: The colour a heatmap's extremes take.
    heat_low: str = "#0ea5e9"
    heat_high: str = "#e11d48"
    rc: dict[str, Any] = field(default_factory=dict)

    def series_color(self, index: int) -> str:
        return self.palette[index % len(self.palette)]

    def direction_color(self, value: float) -> str:
        return self.up if value >= 0 else self.down


DARK_THEME = ChartTheme(
    name="eclipse-dark",
    ink="#e5e7eb",
    muted="#94a3b8",
    grid="#ffffff14",
    axis="#ffffff33",
    surface=None,
    rc={
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
        "text.color": "#e5e7eb",
        "axes.labelcolor": "#94a3b8",
        "axes.edgecolor": "#ffffff33",
        "axes.titlecolor": "#e5e7eb",
        "xtick.color": "#94a3b8",
        "ytick.color": "#94a3b8",
        "grid.color": "#ffffff1a",
        "grid.linestyle": "-",
        "grid.linewidth": 0.6,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "figure.autolayout": False,
    },
)

LIGHT_THEME = ChartTheme(
    name="eclipse-light",
    ink="#111827",
    muted="#6b7280",
    grid="#0f172a14",
    axis="#0f172a33",
    surface=None,
    up=UP_COLOR,
    down=DOWN_COLOR,
    rc={
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
        "text.color": "#111827",
        "axes.labelcolor": "#6b7280",
        "axes.edgecolor": "#0f172a33",
        "axes.titlecolor": "#111827",
        "xtick.color": "#6b7280",
        "ytick.color": "#6b7280",
        "grid.color": "#0f172a14",
        "grid.linestyle": "-",
        "grid.linewidth": 0.6,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "figure.autolayout": False,
    },
)

THEMES: dict[str, ChartTheme] = {
    DARK_THEME.name: DARK_THEME,
    LIGHT_THEME.name: LIGHT_THEME,
}


def get_theme(name: Optional[str]) -> ChartTheme:
    """The named theme, or the dark one. An unknown name is not a crash."""
    if not name:
        return DARK_THEME
    return THEMES.get(str(name), DARK_THEME)


__all__ = [
    "ChartTheme",
    "DARK_THEME",
    "DOWN_COLOR",
    "LIGHT_THEME",
    "SERIES_COLORS",
    "THEMES",
    "UP_COLOR",
    "get_theme",
]
