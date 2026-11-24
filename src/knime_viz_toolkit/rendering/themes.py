"""Publication-grade visual themes and automatic CJK + Latin font resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import matplotlib as mpl
from matplotlib import font_manager

from ..models import ThemeName


@dataclass(frozen=True)
class ThemeConfig:
    """Complete visual styling configuration for a chart theme."""

    name: ThemeName
    description: str
    palette: list[str]
    primary: str
    accent: str
    negative: str
    neutral: str
    bg: str
    axes_bg: str
    text: str
    title_color: str
    subtitle_color: str
    spine_color: str
    grid_color: str
    grid_linestyle: str
    grid_alpha: float
    legend_bg: str
    legend_edge: str
    heatmap_cmap: str
    is_dark: bool = False
    default_transparent: bool = False
    marker_edge: str = "#FFFFFF"
    wedge_edge: str = "#FFFFFF"
    prefer_donut: bool = False
    prefer_jitter_box: bool = True
    prefer_trendline: bool = True
    prefer_rolling_ma: bool = True
    use_knime_colors: bool = False
    rc_overrides: dict[str, Any] = field(default_factory=dict)


THEMES: dict[ThemeName, ThemeConfig] = {
    "editorial": ThemeConfig(
        name="editorial",
        description="Polished editorial / consulting palette (Navy, Teal, Coral, Amber) with rich accents and crisp hierarchy.",
        palette=["#1B365D", "#0F9D8A", "#E05A47", "#E8A838", "#6D5BD0", "#2563EB", "#475569", "#EC4899"],
        primary="#1B365D",
        accent="#0F9D8A",
        negative="#E05A47",
        neutral="#64748B",
        bg="#FFFFFF",
        axes_bg="#FFFFFF",
        text="#1E293B",
        title_color="#1B365D",
        subtitle_color="#64748B",
        spine_color="#CBD5E1",
        grid_color="#E2E8F0",
        grid_linestyle="--",
        grid_alpha=0.85,
        legend_bg="#FFFFFF",
        legend_edge="#E2E8F0",
        heatmap_cmap="YlGnBu",
        prefer_donut=True,
        prefer_jitter_box=True,
        prefer_trendline=True,
        prefer_rolling_ma=True,
    ),
    "academic": ThemeConfig(
        name="academic",
        description="Clean, minimalist university & thesis style (Steel Blue, Crimson, Forest Green) with zero visual clutter.",
        palette=["#3B6EA5", "#D9534F", "#2E8B57", "#E69F00", "#1F4E79", "#7F8C8D", "#8E44AD", "#16A085"],
        primary="#3B6EA5",
        accent="#2E8B57",
        negative="#D9534F",
        neutral="#7F8C8D",
        bg="#FFFFFF",
        axes_bg="#FFFFFF",
        text="#222222",
        title_color="#1A1A1A",
        subtitle_color="#555555",
        spine_color="#888888",
        grid_color="#E6E6E6",
        grid_linestyle="-",
        grid_alpha=0.90,
        legend_bg="#FFFFFF",
        legend_edge="#DDDDDD",
        heatmap_cmap="YlGnBu",
        prefer_donut=False,
        prefer_jitter_box=False,
        prefer_trendline=True,
        prefer_rolling_ma=True,
    ),
    "nature": ThemeConfig(
        name="nature",
        description="Scientific journal aesthetic using colorblind-safe Okabe-Ito hues and ultra-clean vector typography.",
        palette=["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#333333"],
        primary="#0072B2",
        accent="#009E73",
        negative="#D55E00",
        neutral="#5C6670",
        bg="#FFFFFF",
        axes_bg="#FFFFFF",
        text="#111827",
        title_color="#111827",
        subtitle_color="#4B5563",
        spine_color="#374151",
        grid_color="#E5E7EB",
        grid_linestyle=":",
        grid_alpha=0.85,
        legend_bg="#FFFFFF",
        legend_edge="#D1D5DB",
        heatmap_cmap="viridis",
        prefer_donut=False,
        prefer_jitter_box=True,
        prefer_trendline=True,
        prefer_rolling_ma=False,
    ),
    "presentation_dark": ThemeConfig(
        name="presentation_dark",
        description="High-contrast dark slate keynote theme with luminous accents for widescreen slides.",
        palette=["#38BDF8", "#34D399", "#FB7185", "#FBBF24", "#A78BFA", "#F472B6", "#94A3B8", "#2DD4BF"],
        primary="#38BDF8",
        accent="#34D399",
        negative="#FB7185",
        neutral="#94A3B8",
        bg="#0F172A",
        axes_bg="#1E293B",
        text="#F1F5F9",
        title_color="#F8FAFC",
        subtitle_color="#94A3B8",
        spine_color="#475569",
        grid_color="#334155",
        grid_linestyle="--",
        grid_alpha=0.70,
        legend_bg="#1E293B",
        legend_edge="#475569",
        heatmap_cmap="magma",
        is_dark=True,
        default_transparent=False,
        marker_edge="#1E293B",
        wedge_edge="#0F172A",
        prefer_donut=True,
        prefer_jitter_box=True,
        prefer_trendline=True,
        prefer_rolling_ma=True,
    ),
    "dark_transparent": ThemeConfig(
        name="dark_transparent",
        description="Transparent-background dark PPT theme with crisp white typography, translucent gridlines, and luminous series for dark slides.",
        palette=["#38BDF8", "#34D399", "#FB7185", "#FBBF24", "#A78BFA", "#2DD4BF", "#F472B6", "#E2E8F0"],
        primary="#38BDF8",
        accent="#34D399",
        negative="#FB7185",
        neutral="#CBD5E1",
        bg="none",
        axes_bg="none",
        text="#F1F5F9",
        title_color="#FFFFFF",
        subtitle_color="#CBD5E1",
        spine_color="#94A3B8",
        grid_color="#94A3B8",
        grid_linestyle="--",
        grid_alpha=0.28,
        legend_bg="#0F172A",
        legend_edge="#64748B",
        heatmap_cmap="magma",
        is_dark=True,
        default_transparent=True,
        marker_edge="none",
        wedge_edge="#0F172A",
        prefer_donut=True,
        prefer_jitter_box=True,
        prefer_trendline=True,
        prefer_rolling_ma=True,
    ),
    "knime_enhanced": ThemeConfig(
        name="knime_enhanced",
        description="Respects upstream KNIME Color Manager assignments while upgrading to 300-DPI editorial polish.",
        palette=["#1B365D", "#0F9D8A", "#E05A47", "#E8A838", "#6D5BD0", "#2563EB", "#475569", "#EC4899"],
        primary="#1B365D",
        accent="#0F9D8A",
        negative="#E05A47",
        neutral="#64748B",
        bg="#FFFFFF",
        axes_bg="#FFFFFF",
        text="#1E293B",
        title_color="#1B365D",
        subtitle_color="#64748B",
        spine_color="#CBD5E1",
        grid_color="#E2E8F0",
        grid_linestyle="--",
        grid_alpha=0.85,
        legend_bg="#FFFFFF",
        legend_edge="#E2E8F0",
        heatmap_cmap="YlGnBu",
        prefer_donut=True,
        prefer_jitter_box=True,
        prefer_trendline=True,
        prefer_rolling_ma=True,
        use_knime_colors=True,
    ),
}


@lru_cache(maxsize=2)
def detect_font_stack(prefer_cjk: bool = False) -> list[str]:
    """Build a crisp Latin + CJK font stack based on fonts installed on the host OS."""
    available = {f.name for f in font_manager.fontManager.ttflist}
    latin_pref = ["Segoe UI", "Calibri", "Inter", "Helvetica Neue", "Arial", "Liberation Sans"]
    cjk_pref = [
        "Microsoft YaHei",
        "Noto Sans SC",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "SimHei",
        "WenQuanYi Micro Hei",
    ]
    latin_found = [n for n in latin_pref if n in available]
    cjk_found = [n for n in cjk_pref if n in available]

    stack: list[str] = []
    if prefer_cjk:
        stack.extend(cjk_found[:2])
        stack.extend(latin_found[:2])
    else:
        stack.extend(latin_found[:2])
        stack.extend(cjk_found[:2])
    if "DejaVu Sans" in available and "DejaVu Sans" not in stack:
        stack.append("DejaVu Sans")
    return stack or ["DejaVu Sans"]


def contains_cjk(text: str | None) -> bool:
    """Return True if `text` contains any CJK Unified Ideograph or CJK punctuation."""
    if not text:
        return False
    return any("\u2e80" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff" for ch in text)


def get_theme(name: ThemeName | str) -> ThemeConfig:
    key = str(name).strip().lower()
    if key not in THEMES:
        valid = ", ".join(THEMES.keys())
        raise ValueError(f"Unknown theme '{name}'. Valid themes: {valid}")
    return THEMES[key]  # type: ignore[index]


def build_rc_params(
    theme: ThemeConfig,
    dpi: int = 300,
    prefer_cjk: bool = False,
    transparent: bool | None = None,
) -> dict[str, Any]:
    """Return a matplotlib rcParams dictionary scoped for `mpl.rc_context`."""
    is_trans = theme.default_transparent if transparent is None else transparent
    fig_bg = "none" if is_trans else theme.bg
    ax_bg = "none" if is_trans else theme.axes_bg
    rc: dict[str, Any] = {
        "font.family": "sans-serif",
        "font.sans-serif": detect_font_stack(prefer_cjk=prefer_cjk),
        "axes.unicode_minus": False,
        "figure.facecolor": fig_bg,
        "axes.facecolor": ax_bg,
        "savefig.facecolor": fig_bg,
        "savefig.dpi": dpi,
        "axes.edgecolor": theme.spine_color,
        "axes.linewidth": 0.9,
        "axes.titlesize": 13.0,
        "axes.titleweight": "bold",
        "axes.titlecolor": theme.title_color,
        "axes.labelsize": 10.5,
        "axes.labelcolor": theme.text,
        "xtick.color": theme.text,
        "ytick.color": theme.text,
        "xtick.labelsize": 9.3,
        "ytick.labelsize": 9.3,
        "text.color": theme.text,
        "legend.frameon": True,
        "legend.facecolor": theme.legend_bg,
        "legend.edgecolor": theme.legend_edge,
        "legend.framealpha": 0.72 if is_trans and theme.is_dark else 0.94,
        "legend.fontsize": 9.0,
    }
    rc.update(theme.rc_overrides)
    return rc


def list_themes_info() -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "palette": t.palette,
            "background": "transparent" if t.default_transparent else t.bg,
            "is_dark": t.is_dark,
            "default_transparent": t.default_transparent,
            "heatmap_cmap": t.heatmap_cmap,
        }
        for t in THEMES.values()
    ]
