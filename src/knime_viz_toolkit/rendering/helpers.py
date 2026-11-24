"""Formatting, color resolution, and anti-overlap helpers for Matplotlib rendering."""

from __future__ import annotations

import math
from typing import Any, Sequence

import matplotlib.ticker as mtick
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
import numpy as np

from .themes import ThemeConfig

# Official 16x16 GitHub Octocat mark expressed as cubic Bezier segments (y-flipped for Matplotlib).
_GITHUB_OCTOCAT_VERTS: list[tuple[float, float]] = [
    (8.00, 16.00),
    (3.58, 16.00), (0.00, 12.42), (0.00, 8.00),
    (0.00, 4.46), (2.29, 1.47), (5.47, 0.41),
    (5.87, 0.34), (6.02, 0.58), (6.02, 0.79),
    (6.02, 0.98), (6.01, 1.61), (6.01, 2.28),
    (4.00, 1.91), (3.48, 2.77), (3.32, 3.22),
    (3.23, 3.45), (2.84, 4.16), (2.50, 4.35),
    (2.22, 4.50), (1.82, 4.87), (2.49, 4.88),
    (3.12, 4.89), (3.57, 4.30), (3.72, 4.06),
    (4.44, 2.85), (5.59, 3.19), (6.05, 3.40),
    (6.12, 3.92), (6.33, 4.27), (6.56, 4.47),
    (4.78, 4.67), (2.92, 5.36), (2.92, 8.42),
    (2.92, 9.29), (3.23, 10.01), (3.74, 10.57),
    (3.66, 10.77), (3.38, 11.59), (3.82, 12.69),
    (3.82, 12.69), (4.49, 12.90), (6.02, 11.87),
    (6.66, 12.05), (7.34, 12.14), (8.02, 12.14),
    (8.70, 12.14), (9.38, 12.05), (10.02, 11.87),
    (11.55, 12.90), (12.22, 12.69), (12.22, 12.69),
    (12.66, 11.59), (12.38, 10.77), (12.30, 10.57),
    (12.81, 10.01), (13.12, 9.29), (13.12, 8.42),
    (13.12, 5.35), (11.25, 4.67), (9.47, 4.47),
    (9.76, 4.22), (10.01, 3.74), (10.01, 2.99),
    (10.01, 1.92), (10.00, 1.06), (10.00, 0.79),
    (10.00, 0.58), (10.15, 0.33), (10.55, 0.41),
    (13.71, 1.47), (16.00, 4.46), (16.00, 8.00),
    (16.00, 12.42), (12.42, 16.00), (8.00, 16.00),
    (8.00, 16.00),
]

_GITHUB_OCTOCAT_CODES: list[int] = (
    [MplPath.MOVETO]
    + [MplPath.CURVE4] * (len(_GITHUB_OCTOCAT_VERTS) - 2)
    + [MplPath.CLOSEPOLY]
)


def add_watermark(fig: Any, theme: ThemeConfig, text: str = "1222hxy/knime-viz-toolkit") -> None:
    """Attach a subtle bottom-right vector GitHub Octocat icon + repo text watermark to `fig`."""
    if not text:
        return

    color = "#94A3B8"
    alpha = 0.72 if theme.is_dark else 0.85

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig_bbox = fig.get_tightbbox(renderer)
    inv = fig.transFigure.inverted()

    if fig_bbox is not None:
        (_, y0_fig), (x1_fig, _) = inv.transform(fig_bbox.get_points())
        anchor_x = min(0.992, max(0.95, float(x1_fig)))
        anchor_y = float(y0_fig) - 0.022
    else:
        anchor_x, anchor_y = 0.99, -0.02

    txt = fig.text(
        anchor_x,
        anchor_y,
        text,
        ha="right",
        va="top",
        fontsize=8.2,
        color=color,
        alpha=alpha,
        fontweight="normal",
        zorder=100,
    )

    # Measure rendered text box to place the 1:1 vector GitHub icon cleanly to its left
    fig.canvas.draw()
    tb_px = txt.get_window_extent(renderer=renderer)
    (tx0, ty0), (tx1, ty1) = inv.transform(tb_px.get_points())

    fig_w_in, fig_h_in = fig.get_size_inches()
    icon_in = 0.135  # ~9.7 pt crisp square Octocat mark matching 8.2pt cap-height
    gap_in = 0.080
    icon_w = icon_in / max(fig_w_in, 1.0)
    icon_h = icon_in / max(fig_h_in, 1.0)
    gap_w = gap_in / max(fig_w_in, 1.0)

    icon_x = float(tx0) - gap_w - icon_w
    icon_y = 0.5 * (float(ty0) + float(ty1)) - 0.5 * icon_h

    ax_icon = fig.add_axes([icon_x, icon_y, icon_w, icon_h], frameon=False, zorder=100)
    ax_icon.set_facecolor("none")
    ax_icon.set_xlim(0.0, 16.0)
    ax_icon.set_ylim(0.0, 16.0)
    ax_icon.set_aspect("equal")
    ax_icon.axis("off")

    path = MplPath(_GITHUB_OCTOCAT_VERTS, _GITHUB_OCTOCAT_CODES)
    ax_icon.add_patch(PathPatch(path, facecolor=color, edgecolor="none", alpha=alpha))


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
