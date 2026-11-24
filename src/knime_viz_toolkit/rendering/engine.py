"""High-DPI Matplotlib rendering engine for KNIME workflows."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from ..io.table import KnimeTable, smart_sort_key
from ..io.workflow_reader import KnimeWorkflow
from ..models import ChartSpec, RenderOptions, RenderResult
from .helpers import (
    apply_numeric_formatter,
    contrast_text_color,
    format_number,
    prettify_series_label,
    resolve_colors,
    set_title_and_subtitle,
    smart_rotate_xlabels,
    style_axes,
)
from .themes import ThemeConfig, build_rc_params, contains_cjk, get_theme


def _get_image_dimensions(path: Path, fmt: str, fig: Any, dpi: int) -> tuple[int | None, int | None]:
    if fmt == "png":
        try:
            from PIL import Image

            with Image.open(path) as im:
                return im.size
        except Exception:
            pass
    w_in, h_in = fig.get_size_inches()
    return int(round(w_in * dpi)), int(round(h_in * dpi))


def _apply_overrides(spec: ChartSpec, opts: RenderOptions) -> tuple[str, str, str | None, str | None]:
    title = opts.title_override if opts.title_override is not None else spec.title
    subtitle = opts.subtitle_override if opts.subtitle_override is not None else spec.subtitle
    xlabel = opts.x_label_override if opts.x_label_override is not None else spec.x_label
    ylabel = opts.y_label_override if opts.y_label_override is not None else spec.y_label
    return title, subtitle, xlabel, ylabel


def _render_bar(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    warnings: list[str] = []
    cat_col = spec.category_column or (table.columns[0] if table.columns else None)
    if not cat_col or cat_col not in table:
        raise ValueError(f"Category column '{cat_col}' not found in table columns {table.columns}")

    y_cols = [c for c in spec.y_columns if c in table]
    agg = (spec.aggregation or "AVG").upper()
    if not y_cols:
        # Pure occurrence count
        y_cols = [cat_col]
        agg = "COUNT"

    cats, agg_map = table.groupby_agg(cat_col, y_cols, method=agg)
    if spec.max_rows and len(cats) > spec.max_rows:
        cats = cats[: spec.max_rows]
        agg_map = {k: v[: spec.max_rows] for k, v in agg_map.items()}
        warnings.append(f"Truncated categories to max_rows={spec.max_rows}")

    n_cats = len(cats)
    n_series = len(y_cols)
    figsize = opts.figsize or (
        max(7.4, min(12.2, 4.8 + n_cats * 0.55)),
        max(4.5, min(8.0, 3.6 + n_cats * 0.35)) if spec.orientation == "horizontal" else 4.8,
    )
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    pos = np.arange(n_cats, dtype=float)
    show_vals = opts.show_values_override if opts.show_values_override is not None else (
        spec.show_values or (opts.enhance and n_cats * n_series <= 16)
    )

    all_vals: list[float] = []
    if n_series == 1:
        vals = agg_map[y_cols[0]]
        all_vals.extend(vals)
        if n_cats <= 8 and (theme.use_knime_colors and spec.color_map):
            colors = resolve_colors(cats, theme, spec.color_map, opts.palette_override)
        elif n_cats <= 5 and opts.palette_override:
            colors = resolve_colors(cats, theme, None, opts.palette_override)
        else:
            c0 = (opts.palette_override[0] if opts.palette_override else theme.primary)
            colors = [c0] * n_cats

        if spec.orientation == "horizontal":
            bars = ax.barh(pos, vals, height=0.58, color=colors, alpha=0.92, edgecolor="none")
            ax.set_yticks(pos)
            ax.set_yticklabels(cats)
            ax.invert_yaxis()
            if show_vals:
                span = max(vals) - min(min(vals), 0.0) if vals else 1.0
                for b in bars:
                    w = b.get_width()
                    ax.text(w + span * 0.018, b.get_y() + b.get_height() / 2, format_number(w),
                            va="center", ha="left", fontsize=8.8, fontweight="bold", color=theme.text)
            ax.set_xlabel(ylabel or prettify_series_label(y_cols[0]))
            ax.set_ylabel(xlabel or cat_col)
            style_axes(ax, theme, grid_axis="x")
            apply_numeric_formatter(ax, "x", all_vals)
            if vals:
                ax.set_xlim(min(0.0, min(vals) * 1.12), max(vals) * (1.18 if show_vals else 1.10))
        else:
            bars = ax.bar(pos, vals, width=0.58, color=colors, alpha=0.92, edgecolor="none")
            ax.set_xticks(pos)
            ax.set_xticklabels(cats)
            smart_rotate_xlabels(ax, cats)
            if show_vals:
                span = max(vals) - min(min(vals), 0.0) if vals else 1.0
                for b in bars:
                    h = b.get_height()
                    ax.text(b.get_x() + b.get_width() / 2, h + span * 0.02, format_number(h),
                            va="bottom", ha="center", fontsize=8.8, fontweight="bold", color=theme.text)
            ax.set_xlabel(xlabel or cat_col)
            ax.set_ylabel(ylabel or prettify_series_label(y_cols[0]))
            style_axes(ax, theme, grid_axis="y")
            apply_numeric_formatter(ax, "y", all_vals)
            if spec.y_limits:
                ax.set_ylim(*spec.y_limits)
            elif vals:
                ax.set_ylim(min(0.0, min(vals) * 1.12), max(vals) * (1.18 if show_vals else 1.12))
    else:
        series_colors = resolve_colors(y_cols, theme, None, opts.palette_override)
        if spec.bar_mode == "stacked":
            bottoms = np.zeros(n_cats)
            for s_idx, yc in enumerate(y_cols):
                vals = np.asarray(agg_map[yc], dtype=float)
                all_vals.extend((bottoms + vals).tolist())
                lbl = prettify_series_label(yc)
                if spec.orientation == "horizontal":
                    ax.barh(pos, vals, left=bottoms, height=0.58, color=series_colors[s_idx], alpha=0.92, label=lbl)
                else:
                    ax.bar(pos, vals, bottom=bottoms, width=0.58, color=series_colors[s_idx], alpha=0.92, label=lbl)
                bottoms += vals
        else:
            total_w = 0.74
            w = total_w / n_series
            for s_idx, yc in enumerate(y_cols):
                vals = agg_map[yc]
                all_vals.extend(vals)
                offset = (s_idx - (n_series - 1) / 2.0) * w
                lbl = prettify_series_label(yc)
                if spec.orientation == "horizontal":
                    bars = ax.barh(pos + offset, vals, height=w * 0.92, color=series_colors[s_idx], alpha=0.92, label=lbl)
                    if show_vals:
                        span = max(all_vals) if all_vals else 1.0
                        for b in bars:
                            bw = b.get_width()
                            ax.text(bw + span * 0.015, b.get_y() + b.get_height() / 2, format_number(bw),
                                    va="center", ha="left", fontsize=8.0, color=theme.text)
                else:
                    bars = ax.bar(pos + offset, vals, width=w * 0.92, color=series_colors[s_idx], alpha=0.92, label=lbl)
                    if show_vals:
                        span = max(all_vals) if all_vals else 1.0
                        for b in bars:
                            bh = b.get_height()
                            ax.text(b.get_x() + b.get_width() / 2, bh + span * 0.018, format_number(bh),
                                    va="bottom", ha="center", fontsize=8.2, fontweight="bold", color=theme.text)

        if spec.orientation == "horizontal":
            ax.set_yticks(pos)
            ax.set_yticklabels(cats)
            ax.invert_yaxis()
            ax.set_xlabel(ylabel or "Value")
            ax.set_ylabel(xlabel or cat_col)
            style_axes(ax, theme, grid_axis="x")
            apply_numeric_formatter(ax, "x", all_vals)
            if all_vals:
                ax.set_xlim(min(0.0, min(all_vals) * 1.1), max(all_vals) * 1.20)
        else:
            ax.set_xticks(pos)
            ax.set_xticklabels(cats)
            smart_rotate_xlabels(ax, cats)
            ax.set_xlabel(xlabel or cat_col)
            ax.set_ylabel(ylabel or "Value")
            style_axes(ax, theme, grid_axis="y")
            apply_numeric_formatter(ax, "y", all_vals)
            if spec.y_limits:
                ax.set_ylim(*spec.y_limits)
            elif all_vals:
                ax.set_ylim(min(0.0, min(all_vals) * 1.1), max(all_vals) * 1.20)

        if spec.show_legend:
            ax.legend(loc="upper right", frameon=True, framealpha=0.94, ncol=min(n_series, 3))

    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, len(table), warnings


def _render_line(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    warnings: list[str] = []
    x_col = spec.x_column
    y_cols = [c for c in spec.y_columns if c in table]
    if not y_cols:
        y_cols = table.numeric_columns()[:3]
        if not y_cols:
            raise ValueError("No numeric Y columns available for Line Plot.")

    is_date = bool(x_col and x_col in table and table.is_date_column(x_col))
    is_num_x = bool(x_col and x_col in table and not is_date and table.is_numeric_column(x_col))

    n = len(table)
    if is_date and x_col:
        x_vals: Any = table.as_dates(x_col)
        valid_idx = [i for i, d in enumerate(x_vals) if d is not None]
        valid_idx.sort(key=lambda i: x_vals[i])
    elif is_num_x and x_col:
        x_arr = table.as_floats(x_col)
        valid_idx = [i for i in range(n) if np.isfinite(x_arr[i])]
        valid_idx.sort(key=lambda i: x_arr[i])
        x_vals = x_arr
    elif x_col and x_col in table:
        x_vals = table.as_strings(x_col)
        valid_idx = list(range(n))
    else:
        x_vals = np.arange(n, dtype=float)
        valid_idx = list(range(n))

    if spec.max_rows and len(valid_idx) > spec.max_rows:
        valid_idx = valid_idx[: spec.max_rows]
        warnings.append(f"Truncated line plot rows to max_rows={spec.max_rows}")

    x_plot = [x_vals[i] for i in valid_idx] if not isinstance(x_vals, np.ndarray) else x_vals[valid_idx]
    colors = resolve_colors(y_cols, theme, None, opts.palette_override)

    figsize = opts.figsize or (9.2, 4.7)
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    show_markers = spec.show_markers if spec.show_markers is not None else (len(valid_idx) <= 36)
    all_y: list[float] = []
    markers = ["o", "s", "^", "D", "v", "P"]

    for idx, yc in enumerate(y_cols):
        y_raw = table.as_floats(yc)[valid_idx]
        all_y.extend(y_raw[np.isfinite(y_raw)].tolist())
        lbl = prettify_series_label(yc)
        col = colors[idx]

        # Dense single time series enhancement: translucent raw + crisp rolling average!
        if opts.enhance and theme.prefer_rolling_ma and len(y_cols) == 1 and len(valid_idx) >= 90:
            win = max(7, min(21, len(valid_idx) // 40))
            kernel = np.ones(win) / win
            # Smooth handling without edge artifacts using simple centered/trailing rolling mean
            ma = np.array([
                np.nanmean(y_raw[max(0, j - win + 1) : j + 1]) for j in range(len(y_raw))
            ])
            ax.plot(x_plot, y_raw, color=col, alpha=0.26, linewidth=0.95, label=f"{lbl} (Raw)")
            ax.plot(x_plot, ma, color=col, linewidth=2.3, label=f"{lbl} ({win}-pt Moving Avg)")
            ax.legend(loc="upper left", framealpha=0.94)
        else:
            mk = markers[idx % len(markers)] if show_markers else None
            ls = "-" if idx < 3 else "--"
            ax.plot(
                x_plot,
                y_raw,
                color=col,
                linewidth=2.3,
                linestyle=ls,
                marker=mk,
                markersize=4.5 if mk else 0,
                markeredgecolor=theme.marker_edge,
                markeredgewidth=0.6 if theme.marker_edge != "none" else 0.0,
                label=lbl,
            )

    if len(y_cols) > 1 and spec.show_legend:
        ax.legend(loc="upper left", framealpha=0.94, ncol=min(len(y_cols), 3))

    if is_date:
        locator = mdates.AutoDateLocator(minticks=5, maxticks=10)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    elif is_num_x and x_col and x_col.lower() in ("hr", "hour"):
        ax.set_xticks(range(0, 24, 3))
        ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 3)])
    elif not is_num_x and len(x_plot) > 12:
        step = max(1, len(x_plot) // 12)
        ax.set_xticks(range(0, len(x_plot), step))
        ax.set_xticklabels([str(x_plot[i]) for i in range(0, len(x_plot), step)])
        smart_rotate_xlabels(ax, [str(x) for x in x_plot[::step]])

    if spec.x_limits and not is_date:
        ax.set_xlim(*spec.x_limits)
    if spec.y_limits:
        ax.set_ylim(*spec.y_limits)
    elif all_y:
        lo, hi = min(all_y), max(all_y)
        pad = (hi - lo) * 0.12 if hi > lo else 1.0
        ax.set_ylim(min(0.0, lo - pad) if lo >= 0 else lo - pad, hi + pad)

    apply_numeric_formatter(ax, "y", all_y)
    ax.set_xlabel(xlabel or (x_col or "Index"))
    ax.set_ylabel(ylabel or (prettify_series_label(y_cols[0]) if len(y_cols) == 1 else "Value"))
    style_axes(ax, theme, grid_axis="y")
    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, len(valid_idx), warnings


def _render_scatter(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    warnings: list[str] = []
    x_col = spec.x_column
    y_col = spec.y_columns[0] if spec.y_columns else None
    if not x_col or not y_col or x_col not in table or y_col not in table:
        num_cols = table.numeric_columns()
        if len(num_cols) < 2:
            raise ValueError(f"Scatter plot needs 2 numeric columns; found {num_cols}")
        x_col = x_col if (x_col and x_col in table) else num_cols[0]
        y_col = y_col if (y_col and y_col in table) else num_cols[1]

    x_arr = table.as_floats(x_col)
    y_arr = table.as_floats(y_col)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    idx_all = np.where(mask)[0]
    if spec.max_rows and len(idx_all) > spec.max_rows:
        rng = np.random.default_rng(42)
        idx_all = np.sort(rng.choice(idx_all, size=spec.max_rows, replace=False))
        warnings.append(f"Subsampled scatter plot to {spec.max_rows} points")

    figsize = opts.figsize or (8.0, 5.2)
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    color_col = spec.color_column if (spec.color_column and spec.color_column in table) else None
    pt_size = 28 if len(idx_all) <= 1000 else 16

    if color_col:
        raw_c = [table[color_col][i] for i in idx_all]
        unique_c = sorted({str(v) for v in raw_c if v is not None}, key=smart_sort_key)
        is_categorical = (not table.is_numeric_column(color_col)) or len(unique_c) <= 10
        if is_categorical:
            colors = resolve_colors(unique_c, theme, spec.color_map, opts.palette_override)
            for c_val, col in zip(unique_c, colors):
                sub_mask = np.array([str(v) == c_val for v in raw_c])
                sx = x_arr[idx_all[sub_mask]]
                sy = y_arr[idx_all[sub_mask]]
                ax.scatter(
                    sx,
                    sy,
                    color=col,
                    alpha=0.62,
                    s=pt_size,
                    edgecolors=theme.marker_edge,
                    linewidths=0.35 if theme.marker_edge != "none" else 0.0,
                    label=f"{color_col} = {c_val}" if len(c_val) <= 3 else c_val,
                )
                # Subtle quadratic trend curve if enhanced & group has enough spread (non-cluster)
                if (
                    opts.enhance
                    and theme.prefer_trendline
                    and len(sx) >= 25
                    and len(unique_c) <= 4
                    and "cluster" not in color_col.lower()
                    and np.std(sx) > 1e-9
                ):
                    try:
                        xs = np.linspace(float(np.min(sx)), float(np.max(sx)), 160)
                        deg = 2 if len(sx) >= 40 else 1
                        coeffs = np.polyfit(sx, sy, deg=deg)
                        ax.plot(xs, np.polyval(coeffs, xs), color=col, linewidth=2.2, alpha=0.95)
                    except Exception:
                        pass
            if spec.show_legend:
                ax.legend(loc="best", framealpha=0.94, title=color_col if len(unique_c) <= 6 else None)
        else:
            c_nums = table.as_floats(color_col)[idx_all]
            sc = ax.scatter(
                x_arr[idx_all],
                y_arr[idx_all],
                c=c_nums,
                cmap=theme.heatmap_cmap,
                alpha=0.68,
                s=pt_size,
                edgecolors=theme.marker_edge,
                linewidths=0.3 if theme.marker_edge != "none" else 0.0,
            )
            cbar = fig.colorbar(sc, ax=ax, pad=0.02, fraction=0.046)
            cbar.set_label(color_col, fontsize=9.2, color=theme.text)
    else:
        col = opts.palette_override[0] if opts.palette_override else theme.primary
        sx, sy = x_arr[idx_all], y_arr[idx_all]
        ax.scatter(sx, sy, color=col, alpha=0.65, s=pt_size, edgecolors=theme.marker_edge, linewidths=0.35 if theme.marker_edge != "none" else 0.0)
        if opts.enhance and theme.prefer_trendline and len(sx) >= 25 and np.std(sx) > 1e-9:
            try:
                xs = np.linspace(float(np.min(sx)), float(np.max(sx)), 160)
                coeffs = np.polyfit(sx, sy, deg=2)
                ax.plot(xs, np.polyval(coeffs, xs), color=theme.accent, linewidth=2.3, label="Quadratic Fit")
                ax.legend(loc="best", framealpha=0.94)
            except Exception:
                pass

    if spec.x_limits:
        ax.set_xlim(*spec.x_limits)
    if spec.y_limits:
        ax.set_ylim(*spec.y_limits)
    apply_numeric_formatter(ax, "x", x_arr[idx_all])
    apply_numeric_formatter(ax, "y", y_arr[idx_all])
    ax.set_xlabel(xlabel or x_col)
    ax.set_ylabel(ylabel or y_col)
    style_axes(ax, theme, grid_axis="both")
    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, len(idx_all), warnings


def _render_box(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    warnings: list[str] = []
    y_cols = [c for c in spec.y_columns if c in table]
    if not y_cols:
        y_cols = table.numeric_columns()[:4]
    cat_col = spec.category_column if (spec.category_column and spec.category_column in table) else None

    groups: list[np.ndarray] = []
    labels: list[str] = []
    raw_keys: list[str] = []

    if cat_col:
        target_col = y_cols[0]
        vals = table.as_floats(target_col)
        cat_raw = table[cat_col]
        uniq = sorted({str(v) for v in cat_raw if v is not None}, key=smart_sort_key)
        for u in uniq:
            g = np.array([vals[i] for i, c in enumerate(cat_raw) if str(c) == u and np.isfinite(vals[i])])
            if len(g) > 0:
                groups.append(g)
                raw_keys.append(u)
                labels.append(f"{u}\n(n={len(g):,})" if opts.enhance else u)
    else:
        for yc in y_cols:
            arr = table.as_floats(yc)
            arr = arr[np.isfinite(arr)]
            if len(arr) > 0:
                groups.append(arr)
                raw_keys.append(yc)
                labels.append(prettify_series_label(yc))

    if not groups:
        raise ValueError("No valid numeric observations for Box Plot.")

    colors = resolve_colors(raw_keys, theme, spec.color_map, opts.palette_override)
    figsize = opts.figsize or (max(7.2, min(11.5, 4.2 + len(groups) * 1.15)), 4.9)
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    positions = np.arange(1, len(groups) + 1)
    show_jitter = opts.enhance and theme.prefer_jitter_box and sum(len(g) for g in groups) <= 4000
    bp = ax.boxplot(
        groups,
        positions=positions,
        widths=0.46,
        patch_artist=True,
        showfliers=not show_jitter,
        medianprops=dict(color="#0F172A" if theme.is_dark else "#FFFFFF", linewidth=2.0),
        whiskerprops=dict(color=theme.neutral, linewidth=1.2),
        capprops=dict(color=theme.neutral, linewidth=1.2),
        flierprops=dict(marker="o", markersize=3.2, alpha=0.45, markeredgecolor=theme.neutral),
    )

    rng = np.random.default_rng(42)
    all_vals = np.concatenate(groups)
    for pos_i, patch, gvals, col in zip(positions, bp["boxes"], groups, colors):
        patch.set_facecolor(col)
        patch.set_alpha(0.78)
        patch.set_edgecolor(col)
        patch.set_linewidth(1.1)
        if show_jitter:
            jit = rng.normal(pos_i, 0.055, size=len(gvals))
            ax.scatter(jit, gvals, color=col, alpha=0.20, s=11, zorder=2, edgecolors="none")
        m = float(np.mean(gvals))
        ax.scatter(
            [pos_i],
            [m],
            marker="D",
            color="#F59E0B",
            edgecolors=theme.text,
            s=42,
            zorder=5,
            label="Mean" if pos_i == 1 else None,
        )

    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    smart_rotate_xlabels(ax, raw_keys)
    apply_numeric_formatter(ax, "y", all_vals)
    if spec.y_limits:
        ax.set_ylim(*spec.y_limits)
    else:
        lo, hi = float(np.min(all_vals)), float(np.max(all_vals))
        pad = (hi - lo) * 0.12 if hi > lo else 1.0
        ax.set_ylim(min(0.0, lo - pad) if lo >= 0 else lo - pad, hi + pad)

    ax.set_xlabel(xlabel or (cat_col or ""))
    ax.set_ylabel(ylabel or (y_cols[0] if y_cols else "Value"))
    ax.legend(loc="upper right", framealpha=0.94)
    style_axes(ax, theme, grid_axis="y")
    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, int(len(all_vals)), warnings


def _render_heatmap(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    warnings: list[str] = []
    h_col = spec.x_column
    v_col = spec.category_column
    val_col = spec.value_column
    if not (h_col and v_col and val_col and h_col in table and v_col in table and val_col in table):
        raise ValueError(
            f"Heatmap requires horizontal ({h_col}), vertical ({v_col}), and value ({val_col}) columns."
        )

    rows, cols, mat = table.pivot_agg(v_col, h_col, val_col, method=spec.aggregation or "AVG")
    figsize = opts.figsize or (
        max(7.8, min(12.5, 4.2 + len(cols) * 0.34)),
        max(4.4, min(9.0, 2.8 + len(rows) * 0.48)),
    )
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    cmap = plt.get_cmap(theme.heatmap_cmap)
    im = ax.imshow(mat, aspect="auto", cmap=cmap, interpolation="nearest")
    cbar = fig.colorbar(im, ax=ax, pad=0.025, fraction=0.042)
    cbar.set_label(spec.colorbar_label or val_col, fontsize=9.5, color=theme.text)
    cbar.ax.tick_params(labelsize=8.8, colors=theme.text)
    cbar.outline.set_edgecolor(theme.spine_color)

    ax.set_yticks(np.arange(len(rows)))
    ax.set_yticklabels(rows, fontsize=9.2)
    if len(cols) > 16:
        step = max(1, len(cols) // 12)
        ax.set_xticks(np.arange(0, len(cols), step))
        ax.set_xticklabels([cols[i] for i in range(0, len(cols), step)], fontsize=9.0)
    else:
        ax.set_xticks(np.arange(len(cols)))
        ax.set_xticklabels(cols, fontsize=9.0)
        smart_rotate_xlabels(ax, cols)

    show_vals = opts.show_values_override if opts.show_values_override is not None else (
        spec.show_values or (opts.enhance and len(rows) * len(cols) <= 84)
    )
    if show_vals:
        finite = mat[np.isfinite(mat)]
        vmin, vmax = (float(np.min(finite)), float(np.max(finite))) if len(finite) else (0.0, 1.0)
        norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax if vmax > vmin else vmin + 1.0)
        for ri in range(len(rows)):
            for ci in range(len(cols)):
                v = mat[ri, ci]
                if np.isfinite(v):
                    tcol = contrast_text_color(cmap(norm(v)))
                    ax.text(ci, ri, format_number(v), ha="center", va="center", fontsize=7.8, fontweight="bold", color=tcol)

    for spine in ax.spines.values():
        spine.set_edgecolor(theme.spine_color)
        spine.set_linewidth(0.8)

    ax.set_xlabel(xlabel or h_col)
    ax.set_ylabel(ylabel or v_col)
    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, len(table), warnings


def _render_pie(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    warnings: list[str] = []
    cat_col = spec.category_column or table.columns[0]
    val_col = spec.value_column
    agg = (spec.aggregation or "SUM").upper()

    if val_col and val_col in table:
        cats, res = table.groupby_agg(cat_col, [val_col], method=agg)
        vals = res[val_col]
    else:
        cats, res = table.groupby_agg(cat_col, [cat_col], method="COUNT")
        vals = res[cat_col]

    pairs = [(prettify_series_label(c), max(0.0, float(v))) for c, v in zip(cats, vals) if v > 0]
    pairs.sort(key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in pairs)
    if total <= 0:
        raise ValueError("Pie chart has no positive values to render.")

    # Aggregate small slices matching KNIME config
    if spec.small_category_threshold and spec.small_category_threshold > 0:
        kept: list[tuple[str, float]] = []
        other_sum = 0.0
        for lbl, v in pairs:
            if (v / total) * 100.0 < spec.small_category_threshold:
                other_sum += v
            else:
                kept.append((lbl, v))
        if other_sum > 0:
            kept.append((spec.small_category_label, other_sum))
        pairs = kept

    labels = [p[0] for p in pairs]
    sizes = [p[1] for p in pairs]
    pcts = [s / total * 100.0 for s in sizes]
    colors = resolve_colors(labels, theme, spec.color_map, opts.palette_override)

    is_donut = spec.donut or (opts.enhance and theme.prefer_donut)
    figsize = opts.figsize or (7.2, 5.2)
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, _, _ = _apply_overrides(spec, opts)

    wedgeprops: dict[str, Any] = dict(edgecolor=theme.wedge_edge, linewidth=2.0)
    if is_donut:
        wedgeprops["width"] = 0.40

    wedges, _ = ax.pie(
        sizes,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops=wedgeprops,
    )

    if is_donut:
        ax.text(0, 0.07, format_number(total), ha="center", va="center", fontsize=19, fontweight="bold", color=theme.title_color)
        ax.text(0, -0.14, "Total", ha="center", va="center", fontsize=9.8, color=theme.subtitle_color)
    else:
        for w, pct in zip(wedges, pcts):
            if pct >= 5.0:
                ang = 0.5 * (w.theta1 + w.theta2)
                x = 0.62 * np.cos(np.deg2rad(ang))
                y = 0.62 * np.sin(np.deg2rad(ang))
                ax.text(x, y, f"{pct:.1f}%", ha="center", va="center", fontsize=9.6, fontweight="bold", color="#FFFFFF")

    legend_labels = [f"{lbl}  ({pct:.1f}% · {format_number(val)})" for lbl, pct, val in zip(labels, pcts, sizes)]
    ax.legend(
        wedges,
        legend_labels,
        loc="center left" if len(labels) > 3 else "lower center",
        bbox_to_anchor=(0.98, 0.5) if len(labels) > 3 else (0.5, -0.10),
        ncol=1 if len(labels) > 3 else min(len(labels), 3),
        frameon=False,
        fontsize=9.3,
    )
    ax.set_aspect("equal")
    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, len(table), warnings


def _render_scatter_matrix(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    warnings: list[str] = []
    num_cols = table.numeric_columns()
    # Filter out pure monotonic index columns like `instant` if many columns exist
    if len(num_cols) > 6:
        filtered = [c for c in num_cols if c.lower() not in ("instant", "id", "index")]
        num_cols = filtered[:6] if len(filtered) >= 2 else num_cols[:6]
    if len(num_cols) < 2:
        raise ValueError("Scatter matrix requires at least 2 numeric columns.")

    n_rows = len(table)
    idx = np.arange(n_rows)
    if spec.max_rows and n_rows > spec.max_rows:
        rng = np.random.default_rng(42)
        idx = np.sort(rng.choice(idx, size=spec.max_rows, replace=False))
        warnings.append(f"Subsampled scatter matrix to {spec.max_rows} rows")

    k = len(num_cols)
    data_cols = {c: table.as_floats(c)[idx] for c in num_cols}
    figsize = opts.figsize or (max(7.8, k * 2.05), max(7.2, k * 1.90))
    fig, axes = plt.subplots(k, k, figsize=figsize)
    title, subtitle, _, _ = _apply_overrides(spec, opts)

    for i in range(k):
        for j in range(k):
            ax = axes[i, j]
            xi, yj = data_cols[num_cols[j]], data_cols[num_cols[i]]
            valid = np.isfinite(xi) & np.isfinite(yj)
            if i == j:
                vals = xi[np.isfinite(xi)]
                ax.hist(vals, bins=18, color=theme.primary, alpha=0.80, edgecolor=theme.wedge_edge, linewidth=0.5)
                style_axes(ax, theme, grid_axis="none")
            elif i > j:
                ax.scatter(xi[valid], yj[valid], s=9, alpha=0.45, color=theme.accent, edgecolors="none")
                style_axes(ax, theme, grid_axis="both")
            else:
                # Upper triangle: Pearson r badge!
                r = float(np.corrcoef(xi[valid], yj[valid])[0, 1]) if np.sum(valid) > 2 else float("nan")
                ax.set_xticks([])
                ax.set_yticks([])
                for sp in ax.spines.values():
                    sp.set_visible(False)
                if np.isfinite(r):
                    bg_col = theme.accent if r >= 0 else theme.negative
                    ax.set_facecolor(mpl.colors.to_rgba(bg_col, alpha=min(0.28, abs(r) * 0.35 + 0.04)))
                    ax.text(0.5, 0.54, f"r = {r:+.2f}", transform=ax.transAxes, ha="center", va="center",
                            fontsize=11.5, fontweight="bold", color=theme.title_color)
                    strength = "Strong" if abs(r) >= 0.6 else ("Moderate" if abs(r) >= 0.3 else "Weak")
                    ax.text(0.5, 0.30, strength, transform=ax.transAxes, ha="center", va="center",
                            fontsize=8.2, color=theme.subtitle_color)

            if i == k - 1:
                ax.set_xlabel(num_cols[j], fontsize=9.0, fontweight="bold")
            else:
                ax.set_xticklabels([])
            if j == 0:
                ax.set_ylabel(num_cols[i], fontsize=9.0, fontweight="bold")
            else:
                ax.set_yticklabels([])
            ax.tick_params(labelsize=7.5)

    fig.suptitle(title, fontsize=14, fontweight="bold", color=theme.title_color, y=0.995)
    if subtitle:
        fig.text(0.5, 0.965, subtitle, ha="center", va="top", fontsize=9.5, color=theme.subtitle_color)
    fig.tight_layout(rect=[0, 0, 1, 0.945 if subtitle else 0.965])
    return fig, len(idx), warnings


def _render_histogram(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    x_col = spec.x_column or (table.numeric_columns()[0] if table.numeric_columns() else None)
    if not x_col or x_col not in table:
        raise ValueError("Histogram requires a valid numeric column.")
    vals = table.as_floats(x_col)
    vals = vals[np.isfinite(vals)]
    figsize = opts.figsize or (8.0, 4.7)
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    col = opts.palette_override[0] if opts.palette_override else theme.primary
    ax.hist(vals, bins="auto", color=col, alpha=0.84, edgecolor=theme.wedge_edge, linewidth=0.7)
    if opts.enhance and len(vals) > 0:
        m = float(np.mean(vals))
        med = float(np.median(vals))
        ax.axvline(m, color=theme.negative, linestyle="--", linewidth=1.8, label=f"Mean: {format_number(m)}")
        ax.axvline(med, color=theme.accent, linestyle=":", linewidth=1.8, label=f"Median: {format_number(med)}")
        ax.legend(loc="upper right", framealpha=0.94)

    apply_numeric_formatter(ax, "x", vals)
    ax.set_xlabel(xlabel or x_col)
    ax.set_ylabel(ylabel or "Count")
    style_axes(ax, theme, grid_axis="y")
    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, len(vals), []


def _render_correlation(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    target = spec.value_column or (spec.y_columns[0] if spec.y_columns else None)
    num_cols = table.numeric_columns()
    if not target or target not in table:
        raise ValueError(f"Correlation chart requires a numeric target column; available: {num_cols}")
    t_arr = table.as_floats(target)
    corrs: list[tuple[str, float]] = []
    for c in num_cols:
        if c == target or c.lower() in ("instant", "id", "index"):
            continue
        x_arr = table.as_floats(c)
        valid = np.isfinite(x_arr) & np.isfinite(t_arr)
        if np.sum(valid) >= 3 and np.std(x_arr[valid]) > 0 and np.std(t_arr[valid]) > 0:
            r = float(np.corrcoef(x_arr[valid], t_arr[valid])[0, 1])
            if np.isfinite(r):
                corrs.append((c, r))
    corrs.sort(key=lambda item: item[1])
    names = [c[0] for c in corrs]
    vals = [c[1] for c in corrs]

    figsize = opts.figsize or (8.2, max(4.2, 2.2 + len(names) * 0.42))
    fig, ax = plt.subplots(figsize=figsize)
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    y = np.arange(len(names))
    cols = [theme.negative if v < 0 else theme.accent for v in vals]
    ax.barh(y, vals, color=cols, height=0.58, alpha=0.92)
    ax.axvline(0, color=theme.text, linewidth=0.9)
    for yi, v in zip(y, vals):
        ax.text(
            v + (0.025 if v >= 0 else -0.025),
            yi,
            f"{v:+.2f}",
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=9.0,
            fontweight="bold",
            color=theme.text,
        )
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlim(-1.08, 1.08)
    ax.set_xlabel(xlabel or f"Pearson Correlation (r) with {target}")
    ax.set_ylabel(ylabel or "")
    style_axes(ax, theme, grid_axis="x")
    set_title_and_subtitle(ax, title, subtitle, theme)
    fig.tight_layout()
    return fig, len(table), []


def _render_model_comparison(spec: ChartSpec, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    scorers = spec.extra.get("scorers", [])
    if not scorers:
        raise ValueError("No Numeric Scorer data available for model_comparison chart.")

    labels = [s["label"] for s in scorers]
    r2s = [float(s["r2"]) if s.get("r2") is not None else 0.0 for s in scorers]
    maes = [float(s["mae"]) if s.get("mae") is not None else 0.0 for s in scorers]
    rmses = [float(s["rmse"]) if s.get("rmse") is not None else 0.0 for s in scorers]

    figsize = opts.figsize or (max(10.8, 6.2 + len(labels) * 1.15), 4.8)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, gridspec_kw={"width_ratios": [1.0, 1.15]})
    title, subtitle, _, _ = _apply_overrides(spec, opts)

    x = np.arange(len(labels))
    bar_cols = [theme.accent if v == max(r2s) else (theme.negative if v < 0.5 else theme.primary) for v in r2s]
    b_r2 = ax1.bar(x, r2s, width=0.52, color=bar_cols, alpha=0.92)
    for b in b_r2:
        h = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2, h + 0.025, f"{h:.3f}",
                 ha="center", va="bottom", fontsize=9.4, fontweight="bold", color=theme.text)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=8.6)
    smart_rotate_xlabels(ax1, labels)
    ax1.set_ylim(min(0.0, min(r2s) - 0.1), max(1.12, max(r2s) * 1.18))
    ax1.set_ylabel("Test Set R² (Higher is Better)")
    ax1.set_title("Model Accuracy (R²)", fontsize=11.5, fontweight="bold", color=theme.title_color, pad=10)
    style_axes(ax1, theme, grid_axis="y")

    w = 0.35
    b_mae = ax2.bar(x - w / 2, maes, width=w, color=theme.primary, alpha=0.92, label="MAE")
    b_rmse = ax2.bar(x + w / 2, rmses, width=w, color=theme.negative, alpha=0.86, label="RMSE")
    max_err = max(maes + rmses) if (maes + rmses) else 1.0
    for bars in (b_mae, b_rmse):
        for b in bars:
            h = b.get_height()
            ax2.text(b.get_x() + b.get_width() / 2, h + max_err * 0.02, format_number(h),
                     ha="center", va="bottom", fontsize=8.6, fontweight="bold", color=theme.text)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=8.6)
    smart_rotate_xlabels(ax2, labels)
    ax2.set_ylim(0, max_err * 1.22)
    ax2.set_ylabel("Prediction Error (Lower is Better)")
    ax2.set_title("Error Metrics (MAE vs. RMSE)", fontsize=11.5, fontweight="bold", color=theme.title_color, pad=10)
    ax2.legend(loc="upper right", framealpha=0.94)
    apply_numeric_formatter(ax2, "y", maes + rmses)
    style_axes(ax2, theme, grid_axis="y")

    fig.suptitle(title, fontsize=13.8, fontweight="bold", color=theme.title_color, y=0.99)
    if subtitle:
        fig.text(0.5, 0.935, subtitle, ha="center", va="top", fontsize=9.2, color=theme.subtitle_color)
    fig.tight_layout(rect=[0, 0, 1, 0.90 if subtitle else 0.94], w_pad=2.2)
    return fig, len(scorers), []


def _render_kmeans_regimes(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    km = spec.extra.get("kmeans", {})
    features = km.get("features", [])
    coverage = km.get("coverage", [])
    centroids = km.get("centroids", {})
    cluster_col = next((c for c in table.columns if c.lower() == "cluster"), None)
    if not cluster_col or len(features) < 2:
        raise ValueError("k-Means regime chart requires a Cluster column and >= 2 clustering features.")

    f1, f2 = features[0], features[1]
    if f1 not in table or f2 not in table:
        num_cols = table.numeric_columns()
        f1, f2 = num_cols[0], num_cols[1]

    x_arr = table.as_floats(f1)
    y_arr = table.as_floats(f2)
    c_raw = table.as_strings(cluster_col)
    clusters = sorted({c for c in c_raw if c}, key=smart_sort_key)
    colors = resolve_colors(clusters, theme, spec.color_map, opts.palette_override)

    figsize = opts.figsize or (11.6, 4.7)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, gridspec_kw={"width_ratios": [1.22, 1.0]})
    title, subtitle, _, _ = _apply_overrides(spec, opts)

    counts: list[int] = []
    for cid_str, col in zip(clusters, colors):
        mask = np.array([c == cid_str for c in c_raw]) & np.isfinite(x_arr) & np.isfinite(y_arr)
        sx, sy = x_arr[mask], y_arr[mask]
        counts.append(int(np.sum(mask)))
        ax1.scatter(sx, sy, color=col, alpha=0.62, s=24, edgecolors=theme.marker_edge, linewidths=0.35 if theme.marker_edge != "none" else 0.0, label=cid_str)
        # Plot centroid in table space (mean of cluster points ensures exact scale match even if normalized)
        if len(sx) > 0:
            ax1.scatter([float(np.mean(sx))], [float(np.mean(sy))], marker="*", s=210, color=col,
                        edgecolors=theme.text, linewidths=1.0, zorder=6)

    ax1.set_xlabel(f1)
    ax1.set_ylabel(f2)
    ax1.set_title(f"Cluster Separation ({f1} vs. {f2})", fontsize=11.4, fontweight="bold", color=theme.title_color, pad=10)
    ax1.legend(loc="best", framealpha=0.94)
    apply_numeric_formatter(ax1, "x", x_arr)
    apply_numeric_formatter(ax1, "y", y_arr)
    style_axes(ax1, theme, grid_axis="both")

    # Right panel: cluster sizes & percentage shares
    total = sum(counts) or 1
    bx = np.arange(len(clusters))
    bars = ax2.bar(bx, counts, width=0.52, color=colors, alpha=0.92)
    for b, cnt in zip(bars, counts):
        h = b.get_height()
        ax2.text(b.get_x() + b.get_width() / 2, h + max(counts) * 0.025,
                 f"{cnt:,}\n({cnt / total * 100:.1f}%)",
                 ha="center", va="bottom", fontsize=8.8, fontweight="bold", color=theme.text)
    ax2.set_xticks(bx)
    ax2.set_xticklabels(clusters, fontweight="bold")
    ax2.set_ylim(0, max(counts) * 1.24 if counts else 10)
    ax2.set_ylabel("Row Count")
    ax2.set_title("Cluster Coverage Distribution", fontsize=11.4, fontweight="bold", color=theme.title_color, pad=10)
    apply_numeric_formatter(ax2, "y", counts)
    style_axes(ax2, theme, grid_axis="y")

    fig.suptitle(title, fontsize=13.6, fontweight="bold", color=theme.title_color, y=0.99)
    if subtitle:
        fig.text(0.5, 0.935, subtitle, ha="center", va="top", fontsize=9.2, color=theme.subtitle_color)
    fig.tight_layout(rect=[0, 0, 1, 0.90 if subtitle else 0.94], w_pad=2.0)
    return fig, len(table), []


def _render_predictor_diagnostics(spec: ChartSpec, table: KnimeTable, theme: ThemeConfig, opts: RenderOptions) -> tuple[Any, int, list[str]]:
    actual_col = spec.x_column
    pred_col = spec.y_columns[0] if spec.y_columns else None
    if not actual_col or not pred_col or actual_col not in table or pred_col not in table:
        raise ValueError("Predictor diagnostics requires actual and prediction columns.")

    y_true = table.as_floats(actual_col)
    y_pred = table.as_floats(pred_col)
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[valid], y_pred[valid]
    residuals = y_true - y_pred

    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    # Subsample scatter if huge (> 4000 rows) for crispness
    if len(y_true) > 4000:
        rng = np.random.default_rng(42)
        s_idx = rng.choice(len(y_true), size=4000, replace=False)
        sx, sy = y_true[s_idx], y_pred[s_idx]
    else:
        sx, sy = y_true, y_pred

    figsize = opts.figsize or (11.6, 4.7)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, gridspec_kw={"width_ratios": [1.08, 1.0]})
    title, subtitle, xlabel, ylabel = _apply_overrides(spec, opts)

    ax1.scatter(sx, sy, s=16, alpha=0.45, color=theme.primary, edgecolors="none")
    lo = float(min(np.min(sx), np.min(sy)))
    hi = float(max(np.max(sx), np.max(sy)))
    ax1.plot([lo, hi], [lo, hi], color=theme.negative, linestyle="--", linewidth=1.8, label="Ideal (y = x)")
    ax1.text(
        0.04,
        0.95,
        f"R² = {r2:.3f}\nMAE = {format_number(mae)}\nRMSE = {format_number(rmse)}\nn = {len(y_true):,}",
        transform=ax1.transAxes,
        ha="left",
        va="top",
        fontsize=8.8,
        fontweight="bold",
        color=theme.text,
        bbox=dict(boxstyle="round,pad=0.35", facecolor=theme.legend_bg, edgecolor=theme.legend_edge, alpha=0.95),
    )
    ax1.set_xlabel(xlabel or f"Actual ({actual_col})")
    ax1.set_ylabel(ylabel or f"Predicted ({actual_col})")
    ax1.set_title("Actual vs. Predicted", fontsize=11.4, fontweight="bold", color=theme.title_color, pad=10)
    ax1.legend(loc="lower right", framealpha=0.94)
    apply_numeric_formatter(ax1, "x", sx)
    apply_numeric_formatter(ax1, "y", sy)
    style_axes(ax1, theme, grid_axis="both")

    ax2.hist(residuals, bins=32, color=theme.accent, alpha=0.84, edgecolor=theme.wedge_edge, linewidth=0.5)
    ax2.axvline(0.0, color=theme.negative, linestyle="--", linewidth=1.8, label="Zero Error")
    ax2.set_xlabel(f"Residual (Actual − Predicted)")
    ax2.set_ylabel("Count")
    ax2.set_title("Residual Error Distribution", fontsize=11.4, fontweight="bold", color=theme.title_color, pad=10)
    ax2.legend(loc="upper right", framealpha=0.94)
    apply_numeric_formatter(ax2, "x", residuals)
    style_axes(ax2, theme, grid_axis="y")

    fig.suptitle(title, fontsize=13.6, fontweight="bold", color=theme.title_color, y=0.99)
    if subtitle:
        fig.text(0.5, 0.935, subtitle, ha="center", va="top", fontsize=9.2, color=theme.subtitle_color)
    fig.tight_layout(rect=[0, 0, 1, 0.90 if subtitle else 0.94], w_pad=2.0)
    return fig, len(y_true), []


def render_chart_spec(
    wf: KnimeWorkflow,
    spec: ChartSpec,
    output_path: str | Path,
    options: RenderOptions | None = None,
) -> RenderResult:
    """Render a `ChartSpec` against `wf` and write a high-DPI image to `output_path`."""
    opts = options or RenderOptions()
    theme = get_theme(opts.theme)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower().lstrip(".") != opts.fmt:
        out = out.with_suffix(f".{opts.fmt}")

    table: KnimeTable | None = None
    if spec.chart_kind != "model_comparison":
        if spec.data_node_id is not None:
            table = wf.read_node_table(spec.data_node_id, port=spec.data_port)
        elif spec.node_id is not None:
            table, _ = wf.get_input_table(spec.node_id)
        else:
            raise ValueError(f"ChartSpec '{spec.spec_id}' has no data_node_id or node_id.")

    # Auto-detect whether any title, label, column name, or sample category contains CJK text
    text_probe = [
        opts.title_override or spec.title,
        opts.subtitle_override or spec.subtitle,
        opts.x_label_override or spec.x_label or "",
        opts.y_label_override or spec.y_label or "",
        spec.colorbar_label or "",
    ]
    if table is not None:
        text_probe.extend(table.columns)
        for col in (spec.category_column, spec.color_column, spec.x_column):
            if col and col in table:
                text_probe.extend(str(v) for v in table[col][:30] if v is not None)
    prefer_cjk = any(contains_cjk(t) for t in text_probe)

    is_transparent = theme.default_transparent if opts.transparent is None else opts.transparent
    with mpl.rc_context(build_rc_params(theme, dpi=opts.dpi, prefer_cjk=prefer_cjk, transparent=is_transparent)):
        if spec.chart_kind == "bar":
            assert table is not None
            fig, rows, warns = _render_bar(spec, table, theme, opts)
        elif spec.chart_kind == "line":
            assert table is not None
            fig, rows, warns = _render_line(spec, table, theme, opts)
        elif spec.chart_kind == "scatter":
            assert table is not None
            fig, rows, warns = _render_scatter(spec, table, theme, opts)
        elif spec.chart_kind == "box":
            assert table is not None
            fig, rows, warns = _render_box(spec, table, theme, opts)
        elif spec.chart_kind == "heatmap":
            assert table is not None
            fig, rows, warns = _render_heatmap(spec, table, theme, opts)
        elif spec.chart_kind == "pie":
            assert table is not None
            fig, rows, warns = _render_pie(spec, table, theme, opts)
        elif spec.chart_kind == "scatter_matrix":
            assert table is not None
            fig, rows, warns = _render_scatter_matrix(spec, table, theme, opts)
        elif spec.chart_kind == "histogram":
            assert table is not None
            fig, rows, warns = _render_histogram(spec, table, theme, opts)
        elif spec.chart_kind == "correlation":
            assert table is not None
            fig, rows, warns = _render_correlation(spec, table, theme, opts)
        elif spec.chart_kind == "model_comparison":
            fig, rows, warns = _render_model_comparison(spec, theme, opts)
        elif spec.chart_kind == "kmeans_regimes":
            assert table is not None
            fig, rows, warns = _render_kmeans_regimes(spec, table, theme, opts)
        elif spec.chart_kind == "predictor_diagnostics":
            assert table is not None
            fig, rows, warns = _render_predictor_diagnostics(spec, table, theme, opts)
        else:
            raise NotImplementedError(f"Unsupported chart_kind: {spec.chart_kind}")

        fig.savefig(
            out,
            dpi=opts.dpi,
            format=opts.fmt,
            bbox_inches="tight",
            pad_inches=0.18,
            transparent=is_transparent,
            facecolor="none" if is_transparent else theme.bg,
        )
        w_px, h_px = _get_image_dimensions(out, opts.fmt, fig, opts.dpi)
        plt.close(fig)

    final_title = opts.title_override if opts.title_override is not None else spec.title
    return RenderResult(
        spec_id=spec.spec_id,
        node_id=spec.node_id,
        chart_kind=spec.chart_kind,
        title=final_title,
        theme=theme.name,
        output_path=str(out.resolve()),
        width_px=w_px,
        height_px=h_px,
        rows_plotted=rows,
        warnings=warns,
    )
