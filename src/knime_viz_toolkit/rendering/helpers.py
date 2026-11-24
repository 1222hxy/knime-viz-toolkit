"""Formatting, color resolution, and anti-overlap helpers for Matplotlib rendering."""

from __future__ import annotations

import math
from typing import Any, Sequence

import matplotlib.ticker as mtick
import numpy as np

from .themes import ThemeConfig


def format_number(val: float, decimals: int | None = None) -> str:
    """Format numeric annotations cleanly (compact M/K for large values, commas, or decimals)."""
    if not math.isfinite(val):
        return ""
    av = abs(val)
    if decimals is not None:
        return f"{val:,.{decimals}f}"
    if av >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if av >= 100:
        return f"{val:,.0f}"
    if av >= 10:
        return f"{val:,.1f}"
    if av >= 1:
        return f"{val:.2f}"
    return f"{val:.3f}"


def prettify_series_label(raw: str) -> str:
    """Clean verbose KNIME column names like `Mean(registered)` or `Sum(casual)` slightly for legends."""
    s = raw.strip()
    if s.startswith("Mean(") and s.endswith(")"):
        return f"{s[5:-1]} (Mean)"
    if s.startswith("Sum(") and s.endswith(")"):
        return f"{s[4:-1]} (Sum)"
    if s.startswith("Count*(") and s.endswith(")"):
        return f"Count ({s[7:-1]})"
    return s


def style_axes(ax: Any, theme: ThemeConfig, grid_axis: str = "y") -> None:
    """Apply clean publication despine & subtle background gridlines."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(theme.spine_color)
    ax.spines["bottom"].set_color(theme.spine_color)
    if grid_axis in ("x", "y", "both"):
        ax.grid(
            axis=grid_axis,
            color=theme.grid_color,
            linestyle=theme.grid_linestyle,
            linewidth=0.8,
            alpha=theme.grid_alpha,
        )
    else:
        ax.grid(False)
    ax.set_axisbelow(True)


def set_title_and_subtitle(
    ax: Any,
    title: str,
    subtitle: str,
    theme: ThemeConfig,
    fontsize: float = 13.0,
) -> None:
    """Render a crisp title + optional muted subtitle above `ax` without overlapping axes."""
    if subtitle:
        ax.set_title(title, fontsize=fontsize, fontweight="bold", color=theme.title_color, pad=22, loc="left")
        ax.text(
            0.0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=9.2,
            color=theme.subtitle_color,
        )
    else:
        ax.set_title(title, fontsize=fontsize, fontweight="bold", color=theme.title_color, pad=11, loc="left")


def apply_numeric_formatter(ax: Any, axis: str = "y", values: Sequence[float] | np.ndarray | None = None) -> None:
    """Apply comma separators when magnitude >= 1,000."""
    if values is not None and len(values) > 0:
        arr = np.asarray(values, dtype=float)
        arr = arr[np.isfinite(arr)]
        if len(arr) == 0:
            return
        max_abs = float(np.max(np.abs(arr)))
        if max_abs >= 1_000_000:
            fmt = mtick.FuncFormatter(lambda x, _: f"{x / 1e6:.1f}M" if abs(x) >= 1e6 else f"{x:,.0f}")
        elif max_abs >= 1000:
            fmt = mtick.StrMethodFormatter("{x:,.0f}")
        else:
            return
        if axis == "y":
            ax.yaxis.set_major_formatter(fmt)
        else:
            ax.xaxis.set_major_formatter(fmt)


def resolve_colors(
    keys: Sequence[str],
    theme: ThemeConfig,
    color_map: dict[str, str] | None = None,
    palette_override: list[str] | None = None,
) -> list[str]:
    """Assign colors to series/categories, respecting KNIME Color Manager when theme requests it."""
    pal = palette_override if palette_override else theme.palette
    out: list[str] = []
    for idx, k in enumerate(keys):
        if theme.use_knime_colors and color_map and str(k) in color_map:
            out.append(color_map[str(k)])
        else:
            out.append(pal[idx % len(pal)])
    return out


def smart_rotate_xlabels(ax: Any, labels: Sequence[str]) -> None:
    """Rotate x tick labels gently only when needed to avoid text overlap."""
    n = len(labels)
    max_len = max((len(str(l)) for l in labels), default=0)
    if (n >= 8 and max_len >= 5) or (n >= 5 and max_len >= 12) or max_len >= 18:
        ax.tick_params(axis="x", labelrotation=30)
        for lbl in ax.get_xticklabels():
            lbl.set_ha("right")


def contrast_text_color(rgba: tuple[float, float, float, float]) -> str:
    """Pick white or dark text based on perceptual luminance of a heatmap cell background."""
    r, g, b = rgba[:3]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#FFFFFF" if lum < 0.52 else "#111827"
