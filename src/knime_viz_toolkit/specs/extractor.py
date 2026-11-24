"""Extract normalized ChartSpec definitions from KNIME visualization & analytics nodes."""

from __future__ import annotations

import re
from typing import Any

from ..io.workflow_reader import KnimeWorkflow
from ..models import ChartKind, ChartSpec, NodeInfo

GENERIC_TITLES = {
    "",
    "bar chart",
    "line plot",
    "scatter plot",
    "box plot",
    "heatmap",
    "pie chart",
    "histogram",
    "scatter matrix",
}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", text.strip()).strip("_")
    return s[:48] or "chart"


def _selected_single(cfg: dict[str, Any], key: str) -> str | None:
    val = cfg.get(key)
    if isinstance(val, dict):
        sel = val.get("selected")
        if sel is not None and str(sel).strip() != "":
            return str(sel)
    elif isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _selected_multi(cfg: dict[str, Any], key: str) -> list[str]:
    val = cfg.get(key)
    if not isinstance(val, dict):
        if isinstance(val, list):
            return [str(x) for x in val if x]
        return []
    # KNIME modern views store selected columns in `selected_Internals` and `manualFilter.manuallySelected`
    for candidate_key in ("selected_Internals", "selected"):
        sub = val.get(candidate_key)
        if isinstance(sub, list) and sub:
            return [str(x) for x in sub if x]
    mf = val.get("manualFilter")
    if isinstance(mf, dict):
        ms = mf.get("manuallySelected")
        if isinstance(ms, list) and ms:
            return [str(x) for x in ms if x]
    return []


def _choose_title(raw_title: str | None, node: NodeInfo, fallback: str) -> tuple[str, str]:
    """Return `(title, subtitle)` picking the most informative non-generic label."""
    t = (raw_title or "").strip()
    ann_lines = [ln.strip() for ln in node.annotation.splitlines() if ln.strip()]
    subtitle = ""

    if t.lower() in GENERIC_TITLES:
        if ann_lines:
            t = ann_lines[0]
            if len(ann_lines) > 1:
                subtitle = ann_lines[1]
        else:
            t = fallback
    elif ann_lines:
        # Use second annotation line as subtitle if distinct from title
        for ln in ann_lines:
            if ln.lower() not in t.lower() and t.lower() not in ln.lower() and len(ln) <= 70:
                subtitle = ln
                break
    return t, subtitle


def _extract_manual_limits(view: dict[str, Any], kind: ChartKind) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    if str(view.get("axisExtentMethod", "AUTO")).upper() != "MANUAL":
        return None, None
    lim = view.get("manualAxisLimits")
    if not isinstance(lim, dict):
        return None, None
    if kind in ("bar", "box"):
        lo, hi = lim.get("min"), lim.get("max")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi > lo:
            return None, (float(lo), float(hi))
    else:
        xlo, xhi = lim.get("xAxisManualMin"), lim.get("xAxisManualMax")
        ylo, yhi = lim.get("yAxisManualMin"), lim.get("yAxisManualMax")
        xlim = (float(xlo), float(xhi)) if (isinstance(xlo, (int, float)) and isinstance(xhi, (int, float)) and xhi > xlo) else None
        ylim = (float(ylo), float(yhi)) if (isinstance(ylo, (int, float)) and isinstance(yhi, (int, float)) and yhi > ylo) else None
        return xlim, ylim
    return None, None


def extract_node_chart_spec(wf: KnimeWorkflow, node_id: int) -> ChartSpec:
    """Extract a `ChartSpec` from a KNIME visualization node."""
    if node_id not in wf.nodes:
        raise KeyError(f"Node #{node_id} not found in workflow '{wf.workflow_name}'")
    node = wf.nodes[node_id]
    if not node.is_chart_node or node.chart_kind is None:
        raise ValueError(f"Node #{node_id} ({node.name}) is not a supported KNIME visualization node.")

    kind = node.chart_kind
    view = node.view_config
    model = node.model_config_raw
    conn = wf.get_upstream_connection(node_id, dest_port=1)
    data_node_id = conn.source_id if conn is not None else node_id
    data_port = conn.source_port if conn is not None else 1

    xlim, ylim = _extract_manual_limits(view, kind)
    spec_id = f"node_{node_id:02d}_{kind}_{_slugify(node.annotation.splitlines()[0] if node.annotation else node.name)}"

    if kind == "bar":
        cat_col = _selected_single(model, "categoryColumn") or _selected_single(view, "categoryColumn")
        freq_cols = _selected_multi(model, "frequencyColumns") or _selected_multi(view, "frequencyColumns")
        agg = str(model.get("aggregationMethod", "AVG")).upper()
        direction = str(view.get("direction", "VERTICAL")).upper()
        orientation = "horizontal" if direction == "HORIZONTAL" else "vertical"
        ctype = str(view.get("chartType", "GROUPED")).upper()
        bar_mode = "stacked" if ctype == "STACKED" else "grouped"
        fallback_title = f"{', '.join(freq_cols) or 'Count'} by {cat_col or 'Category'}"
        title, subtitle = _choose_title(view.get("title"), node, fallback_title)
        x_label = view.get("customCategoryAxisLabel") if view.get("useCustomCategoryAxisLabel") else cat_col
        y_label = view.get("customFrequencyAxisLabel") if view.get("useCustomFrequencyAxisLabel") else (
            f"{agg.title()}({', '.join(freq_cols)})" if freq_cols else "Count"
        )
        color_map = wf.get_upstream_color_map(node_id, target_column=cat_col)
        return ChartSpec(
            spec_id=spec_id,
            node_id=node_id,
            node_name=node.name,
            data_node_id=data_node_id,
            data_port=data_port,
            chart_kind="bar",
            title=title,
            subtitle=subtitle,
            category_column=cat_col,
            y_columns=freq_cols,
            aggregation=agg,
            orientation=orientation,
            bar_mode=bar_mode,
            show_values=bool(view.get("showValues", False)),
            show_legend=bool(view.get("showLegend", True)),
            x_label=x_label,
            y_label=y_label,
            x_limits=xlim,
            y_limits=ylim,
            color_map=color_map,
            max_rows=view.get("maxRows") if isinstance(view.get("maxRows"), int) else None,
        )

    if kind == "line":
        x_col = _selected_single(view, "xAxisColumn") or _selected_single(model, "xAxisColumn")
        y_cols = _selected_multi(view, "yAxisColumn") or _selected_multi(model, "yAxisColumn")
        fallback_title = f"{', '.join(y_cols) or 'Trend'} over {x_col or 'Index'}"
        title, subtitle = _choose_title(view.get("title"), node, fallback_title)
        x_label = view.get("customXAxisLabel") if view.get("useCustomXAxisLabel") else x_col
        y_label = view.get("customYAxisLabel") if view.get("useCustomYAxisLabel") else (
            y_cols[0] if len(y_cols) == 1 else "Value"
        )
        return ChartSpec(
            spec_id=spec_id,
            node_id=node_id,
            node_name=node.name,
            data_node_id=data_node_id,
            data_port=data_port,
            chart_kind="line",
            title=title,
            subtitle=subtitle,
            x_column=x_col,
            y_columns=y_cols,
            show_markers=bool(view.get("showDataPointMarkers", False)),
            show_legend=len(y_cols) > 1,
            x_label=x_label,
            y_label=y_label,
            x_limits=xlim,
            y_limits=ylim,
            max_rows=view.get("maxRows") if isinstance(view.get("maxRows"), int) else None,
            extra={"line_size": view.get("lineSize", 2)},
        )

    if kind == "scatter":
        x_col = _selected_single(view, "xAxisColumn") or _selected_single(model, "xAxisColumn")
        y_col = _selected_single(view, "yAxisColumn") or _selected_single(model, "yAxisColumn")
        color_col = _selected_single(view, "colorColumn") or _selected_single(model, "colorColumn")
        fallback_title = f"{y_col or 'Y'} vs. {x_col or 'X'}" + (f" (by {color_col})" if color_col else "")
        title, subtitle = _choose_title(view.get("title"), node, fallback_title)
        x_label = view.get("customXAxisLabel") if view.get("useCustomXAxisLabel") else x_col
        y_label = view.get("customYAxisLabel") if view.get("useCustomYAxisLabel") else y_col
        color_map = wf.get_upstream_color_map(node_id, target_column=color_col)

        extra: dict[str, Any] = {"point_size": view.get("dataPointSize", 6)}
        # Check if x_col & y_col correspond to a k-Means node in workflow
        if color_col and "cluster" in color_col.lower() and wf.kmeans_results:
            for km in wf.kmeans_results:
                if x_col in km.features and y_col in km.features:
                    extra["kmeans_id"] = km.node_id
                    break

        return ChartSpec(
            spec_id=spec_id,
            node_id=node_id,
            node_name=node.name,
            data_node_id=data_node_id,
            data_port=data_port,
            chart_kind="scatter",
            title=title,
            subtitle=subtitle,
            x_column=x_col,
            y_columns=[y_col] if y_col else [],
            color_column=color_col,
            show_legend=bool(color_col),
            x_label=x_label,
            y_label=y_label,
            x_limits=xlim,
            y_limits=ylim,
            color_map=color_map,
            max_rows=view.get("maxRows") if isinstance(view.get("maxRows"), int) else None,
            extra=extra,
        )

    if kind == "box":
        cat_col = _selected_single(model, "categoryColumn") or _selected_single(view, "categoryColumn")
        freq_cols = _selected_multi(model, "frequencyColumns") or _selected_multi(view, "frequencyColumns")
        fallback_title = f"Distribution of {', '.join(freq_cols) or 'Value'}" + (f" by {cat_col}" if cat_col else "")
        title, subtitle = _choose_title(view.get("title"), node, fallback_title)
        x_label = view.get("xAxisLabel") or cat_col or ""
        y_label = view.get("yAxisLabel") or (freq_cols[0] if freq_cols else "Value")
        color_map = wf.get_upstream_color_map(node_id, target_column=cat_col)
        return ChartSpec(
            spec_id=spec_id,
            node_id=node_id,
            node_name=node.name,
            data_node_id=data_node_id,
            data_port=data_port,
            chart_kind="box",
            title=title,
            subtitle=subtitle,
            category_column=cat_col,
            y_columns=freq_cols,
            show_legend=bool(view.get("showLegend", True)),
            x_label=x_label,
            y_label=y_label,
            x_limits=xlim,
            y_limits=ylim,
            color_map=color_map,
        )

    if kind == "heatmap":
        h_col = _selected_single(model, "horizontalColumn") or _selected_single(view, "horizontalColumn")
        v_col = _selected_single(model, "verticalColumn") or _selected_single(view, "verticalColumn")
        val_col = _selected_single(model, "valueColumn") or _selected_single(view, "valueColumn")
        agg = str(model.get("aggregationMethod", "AVG")).upper()
        fallback_title = f"{val_col or 'Value'} Heatmap ({v_col} × {h_col})"
        title, subtitle = _choose_title(view.get("title"), node, fallback_title)
        x_label = view.get("customXAxisLabel") if view.get("useCustomXAxisLabel") else h_col
        y_label = view.get("customYAxisLabel") if view.get("useCustomYAxisLabel") else v_col
        cbar_label = view.get("colorMapLabel") or (f"{agg.title()}({val_col})" if val_col else "Value")
        return ChartSpec(
            spec_id=spec_id,
            node_id=node_id,
            node_name=node.name,
            data_node_id=data_node_id,
            data_port=data_port,
            chart_kind="heatmap",
            title=title,
            subtitle=subtitle,
            x_column=h_col,
            category_column=v_col,
            value_column=val_col,
            aggregation=agg,
            show_values=bool(view.get("showValueLabels", False)),
            x_label=x_label,
            y_label=y_label,
            colorbar_label=cbar_label,
        )

    if kind == "pie":
        cat_col = _selected_single(model, "categoryColumn") or _selected_single(view, "categoryColumn")
        freq_col = _selected_single(model, "frequencyColumn") or _selected_single(view, "frequencyColumn")
        agg = str(model.get("aggregationMethod", "SUM")).upper()
        fallback_title = f"Share of {freq_col or 'Count'} by {cat_col or 'Category'}"
        title, subtitle = _choose_title(view.get("title"), node, fallback_title)
        thresh = view.get("aggregateSmallCategoriesThreshold") if view.get("aggregateSmallCategories", False) else None
        color_map = wf.get_upstream_color_map(node_id, target_column=cat_col)
        return ChartSpec(
            spec_id=spec_id,
            node_id=node_id,
            node_name=node.name,
            data_node_id=data_node_id,
            data_port=data_port,
            chart_kind="pie",
            title=title,
            subtitle=subtitle,
            category_column=cat_col,
            value_column=freq_col,
            aggregation=agg,
            donut=bool(view.get("donutChart", False)),
            show_values=bool(view.get("showLabels", True)),
            show_legend=bool(view.get("showLegend", True)),
            small_category_threshold=float(thresh) if isinstance(thresh, (int, float)) else None,
            small_category_label=str(view.get("smallCategoriesLabel", "Other")),
            color_map=color_map,
        )

    if kind == "scatter_matrix":
        title, subtitle = _choose_title(view.get("title"), node, "Feature Scatter & Correlation Matrix")
        return ChartSpec(
            spec_id=spec_id,
            node_id=node_id,
            node_name=node.name,
            data_node_id=data_node_id,
            data_port=data_port,
            chart_kind="scatter_matrix",
            title=title,
            subtitle=subtitle,
            max_rows=int(model.get("end", 2500)) if isinstance(model.get("end"), int) else 2500,
        )

    # Histogram fallback
    freq_col = (
        _selected_single(model, "binningColumn")
        or _selected_single(model, "frequencyColumn")
        or _selected_single(view, "binningColumn")
    )
    title, subtitle = _choose_title(view.get("title"), node, f"Distribution of {freq_col or 'Value'}")
    return ChartSpec(
        spec_id=spec_id,
        node_id=node_id,
        node_name=node.name,
        data_node_id=data_node_id,
        data_port=data_port,
        chart_kind="histogram",
        title=title,
        subtitle=subtitle,
        x_column=freq_col,
        x_label=view.get("customXAxisLabel") if view.get("useCustomXAxisLabel") else freq_col,
        y_label=view.get("customYAxisLabel") if view.get("useCustomYAxisLabel") else "Frequency",
    )


def extract_analytics_specs(wf: KnimeWorkflow) -> list[ChartSpec]:
    """Synthesize high-value analytics charts from KNIME Scorer, k-Means, and Predictor nodes."""
    specs: list[ChartSpec] = []

    # 1. Unified Model Comparison chart if >= 1 Numeric Scorer exists
    if wf.scorers:
        specs.append(
            ChartSpec(
                spec_id="analytics_model_comparison",
                node_id=wf.scorers[0].node_id,
                node_name="Numeric Scorer Comparison",
                chart_kind="model_comparison",
                title="KNIME Model Performance Comparison",
                subtitle=f"Aggregated from {len(wf.scorers)} executed Numeric Scorer node(s)",
                extra={"scorers": [s.model_dump() for s in wf.scorers]},
            )
        )

    # 2. K-Means Regime Overview chart for each executed k-Means node
    for km in wf.kmeans_results:
        specs.append(
            ChartSpec(
                spec_id=f"analytics_kmeans_{km.node_id:02d}",
                node_id=km.node_id,
                node_name=f"k-Means (#{km.node_id})",
                data_node_id=km.node_id,
                data_port=1,
                chart_kind="kmeans_regimes",
                title=f"KNIME k-Means Clustering Overview (k = {len(km.coverage)})",
                subtitle=km.label,
                extra={"kmeans": km.model_dump()},
            )
        )

    # 3. Predictor Diagnostics (Actual vs Predicted & Residuals) for executed Regression/RF Predictors
    for nid, node in sorted(wf.nodes.items()):
        if node.state != "EXECUTED" or not node.has_output_table:
            continue
        if any(k in node.factory for k in ("RegressionPredictor", "RandomForestRegressionPredictor")):
            specs_cols = wf.read_node_spec(nid, port=1)
            col_names = [c.name for c in specs_cols]
            pred_col = next((c for c in col_names if c.startswith("Prediction (") and c.endswith(")")), None)
            if pred_col:
                target_col = pred_col[len("Prediction (") : -1]
                if target_col in col_names:
                    label = node.annotation.splitlines()[0] if node.annotation else f"{node.name} (#{nid})"
                    specs.append(
                        ChartSpec(
                            spec_id=f"analytics_predictor_{nid:02d}_{_slugify(label)}",
                            node_id=nid,
                            node_name=node.name,
                            data_node_id=nid,
                            data_port=1,
                            chart_kind="predictor_diagnostics",
                            title=f"Prediction Diagnostics: {label}",
                            subtitle=f"Actual '{target_col}' vs. '{pred_col}'",
                            x_column=target_col,
                            y_columns=[pred_col],
                            x_label=f"Actual ({target_col})",
                            y_label=f"Predicted ({target_col})",
                        )
                    )

    return specs


def extract_all_specs(wf: KnimeWorkflow, include_analytics: bool = True) -> list[ChartSpec]:
    """Extract ChartSpecs for all visualization nodes (and optionally analytics nodes)."""
    specs: list[ChartSpec] = []
    for node in wf.list_chart_nodes():
        specs.append(extract_node_chart_spec(wf, node.node_id))
    if include_analytics:
        specs.extend(extract_analytics_specs(wf))
    return specs


def build_custom_chart_spec(
    node_id: int,
    chart_kind: ChartKind,
    x: str | None = None,
    y: str | list[str] | None = None,
    category: str | None = None,
    color: str | None = None,
    value: str | None = None,
    aggregation: str = "AVG",
    title: str = "",
    subtitle: str = "",
    x_label: str | None = None,
    y_label: str | None = None,
    orientation: str = "vertical",
    bar_mode: str = "grouped",
    donut: bool = False,
) -> ChartSpec:
    """Construct a custom ChartSpec targeting ANY executed data node in a KNIME workflow."""
    y_list: list[str] = []
    if isinstance(y, str) and y:
        y_list = [y]
    elif isinstance(y, list):
        y_list = [str(c) for c in y if c]

    cat_col = category or (x if chart_kind in ("bar", "box", "pie") else None)
    x_col = x
    val_col = value or (y_list[0] if y_list and chart_kind in ("heatmap", "pie") else None)
    auto_title = title or f"{chart_kind.replace('_', ' ').title()} (Node #{node_id})"

    return ChartSpec(
        spec_id=f"custom_node_{node_id:02d}_{chart_kind}_{_slugify(auto_title)}",
        node_id=node_id,
        node_name=f"Node #{node_id}",
        data_node_id=node_id,
        data_port=1,
        chart_kind=chart_kind,
        title=auto_title,
        subtitle=subtitle,
        x_column=x_col,
        y_columns=y_list,
        category_column=cat_col,
        value_column=val_col,
        color_column=color,
        aggregation=aggregation.upper(),
        orientation="horizontal" if orientation.lower() == "horizontal" else "vertical",
        bar_mode="stacked" if bar_mode.lower() == "stacked" else "grouped",
        donut=donut,
        x_label=x_label,
        y_label=y_label,
        show_legend=True,
    )
