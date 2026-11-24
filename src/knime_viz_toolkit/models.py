"""Pydantic data models for KNIME workflows, chart specifications, and rendering."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


ChartKind = Literal[
    "bar",
    "line",
    "scatter",
    "box",
    "heatmap",
    "pie",
    "scatter_matrix",
    "histogram",
    "model_comparison",
    "kmeans_regimes",
    "predictor_diagnostics",
    "correlation",
]

ThemeName = Literal[
    "editorial",
    "academic",
    "nature",
    "presentation_dark",
    "knime_enhanced",
]


class NodeConnection(BaseModel):
    """Directed edge between two KNIME nodes."""

    source_id: int
    source_port: int
    dest_id: int
    dest_port: int


class ColumnSpec(BaseModel):
    """Column metadata extracted from a KNIME port spec.xml."""

    name: str
    cell_class: str
    lower_bound: Any = None
    upper_bound: Any = None
    possible_values: list[str] = Field(default_factory=list)
    color_map: dict[str, str] = Field(default_factory=dict)


class NodeInfo(BaseModel):
    """Metadata and configuration summary for a single KNIME node."""

    node_id: int
    folder_name: str
    name: str
    factory: str
    state: str = "UNKNOWN"
    annotation: str = ""
    warning: str | None = None
    is_chart_node: bool = False
    is_analytics_node: bool = False
    chart_kind: ChartKind | None = None
    has_output_table: bool = False
    has_internal_table: bool = False
    upstream_ids: list[int] = Field(default_factory=list)
    downstream_ids: list[int] = Field(default_factory=list)
    view_config: dict[str, Any] = Field(default_factory=dict)
    model_config_raw: dict[str, Any] = Field(default_factory=dict)


class NumericScorerResult(BaseModel):
    """Parsed metrics from a KNIME Numeric Scorer node."""

    node_id: int
    label: str
    annotation: str = ""
    upstream_model: str = ""
    r2: float | None = None
    mae: float | None = None
    rmse: float | None = None
    mse: float | None = None
    mape: float | None = None
    raw_metrics: dict[str, Any] = Field(default_factory=dict)


class KMeansResult(BaseModel):
    """Parsed cluster metadata from a KNIME k-Means node."""

    node_id: int
    label: str
    features: list[str] = Field(default_factory=list)
    coverage: list[int] = Field(default_factory=list)
    centroids: dict[str, dict[str, float]] = Field(default_factory=dict)


class ChartSpec(BaseModel):
    """Normalized, engine-agnostic chart specification extracted from a KNIME node."""

    spec_id: str
    node_id: int | None = None
    node_name: str = ""
    data_node_id: int | None = None
    data_port: int = 1
    chart_kind: ChartKind
    title: str = ""
    subtitle: str = ""
    x_column: str | None = None
    y_columns: list[str] = Field(default_factory=list)
    category_column: str | None = None
    value_column: str | None = None
    color_column: str | None = None
    aggregation: str | None = None  # AVG, SUM, COUNT, MIN, MAX, MEDIAN, NONE
    orientation: Literal["vertical", "horizontal"] = "vertical"
    bar_mode: Literal["grouped", "stacked"] = "grouped"
    donut: bool = False
    show_markers: bool | None = None
    show_values: bool | None = None
    show_legend: bool = True
    x_label: str | None = None
    y_label: str | None = None
    colorbar_label: str | None = None
    x_limits: tuple[float, float] | None = None
    y_limits: tuple[float, float] | None = None
    small_category_threshold: float | None = None
    small_category_label: str = "Other"
    color_map: dict[str, str] = Field(default_factory=dict)
    max_rows: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RenderOptions(BaseModel):
    """User or AI Agent rendering controls."""

    theme: ThemeName = "editorial"
    dpi: int = Field(default=300, ge=72, le=600)
    fmt: Literal["png", "svg", "pdf"] = "png"
    figsize: tuple[float, float] | None = None
    enhance: bool = True  # Smart trendlines, rolling averages, value labels, clean formatting
    title_override: str | None = None
    subtitle_override: str | None = None
    x_label_override: str | None = None
    y_label_override: str | None = None
    show_values_override: bool | None = None
    palette_override: list[str] | None = None
    transparent: bool = False


class RenderResult(BaseModel):
    """Result returned after rendering a single chart."""

    spec_id: str
    node_id: int | None = None
    chart_kind: ChartKind
    title: str
    theme: str
    output_path: str
    width_px: int | None = None
    height_px: int | None = None
    rows_plotted: int = 0
    warnings: list[str] = Field(default_factory=list)


class WorkflowSummary(BaseModel):
    """High-level overview of a KNIME workflow for CLI & AI Agents."""

    workflow_path: str
    workflow_name: str
    total_nodes: int
    executed_nodes: int
    unexecuted_nodes: int
    connections_count: int
    chart_nodes: list[NodeInfo] = Field(default_factory=list)
    analytics_nodes: list[NodeInfo] = Field(default_factory=list)
    data_nodes: list[NodeInfo] = Field(default_factory=list)
    scorers: list[NumericScorerResult] = Field(default_factory=list)
    kmeans: list[KMeansResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
