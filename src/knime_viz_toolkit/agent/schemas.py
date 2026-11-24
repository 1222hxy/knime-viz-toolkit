"""Pydantic input schemas for AI Agent tool calling (OpenAI, Anthropic, Gemini, MCP)."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

from ..models import ChartKind, ThemeName


class InspectWorkflowInput(BaseModel):
    workflow_path: str = Field(
        description="Absolute or relative path to a KNIME `.knwf` archive or unpacked workflow directory."
    )


class ListChartNodesInput(BaseModel):
    workflow_path: str = Field(description="Path to a `.knwf` file or unpacked KNIME workflow directory.")
    include_analytics: bool = Field(
        default=True,
        description="Include auto-synthesized analytics charts (Numeric Scorer comparison, k-Means regimes, Predictor diagnostics).",
    )


class ReadNodeDataInput(BaseModel):
    workflow_path: str = Field(description="Path to the KNIME workflow.")
    node_id: int = Field(description="Integer KNIME node ID (e.g., 10, 20, 53).")
    port: int = Field(default=1, ge=1, description="Output port index (default 1).")
    limit: int = Field(default=15, ge=1, le=200, description="Maximum preview rows to return.")


class SuggestChartsInput(BaseModel):
    workflow_path: str = Field(description="Path to the KNIME workflow.")
    node_id: int = Field(description="Integer ID of an executed data-producing KNIME node.")


class RenderNodeChartInput(BaseModel):
    workflow_path: str = Field(description="Path to the KNIME workflow.")
    node_id: int = Field(description="Integer ID of the KNIME visualization or analytics node to render.")
    output_path: str = Field(description="Destination file path for the rendered image (e.g., 'out/chart.png').")
    theme: ThemeName = Field(
        default="editorial",
        description="Visual theme: 'editorial', 'academic', 'nature', 'presentation_dark', 'dark_transparent', or 'knime_enhanced'.",
    )
    fmt: Literal["png", "svg", "pdf"] = Field(default="png", description="Output file format.")
    dpi: int = Field(default=300, ge=72, le=600, description="Output resolution in DPI.")
    enhance: bool = Field(
        default=True,
        description="Enable smart publication enhancements (moving averages, trend curves, clean value labels, sample sizes).",
    )
    title_override: str | None = Field(default=None, description="Optional custom chart title.")
    subtitle_override: str | None = Field(default=None, description="Optional custom subtitle.")
    x_label_override: str | None = Field(default=None, description="Optional custom x-axis label.")
    y_label_override: str | None = Field(default=None, description="Optional custom y-axis label.")
    include_base64: bool = Field(
        default=False,
        description="If true and fmt='png', include a base64-encoded PNG string for multimodal AI visual inspection.",
    )


class RenderWorkflowChartsInput(BaseModel):
    workflow_path: str = Field(description="Path to the KNIME workflow.")
    output_dir: str = Field(description="Directory where all rendered charts and manifest.json will be saved.")
    theme: ThemeName = Field(default="editorial", description="Visual theme applied to all rendered charts.")
    fmt: Literal["png", "svg", "pdf"] = Field(default="png", description="Output image format.")
    dpi: int = Field(default=300, ge=72, le=600, description="Output DPI.")
    enhance: bool = Field(default=True, description="Enable publication-grade enhancements.")
    include_analytics: bool = Field(
        default=True,
        description="Also render auto-synthesized analytics charts (model comparison, k-Means, predictor diagnostics).",
    )
    node_ids: list[int] | None = Field(
        default=None,
        description="Optional subset of KNIME node IDs to render; omit to render all detected chart nodes.",
    )


class RenderCustomChartInput(BaseModel):
    workflow_path: str = Field(description="Path to the KNIME workflow.")
    node_id: int = Field(description="ID of ANY executed KNIME data node whose output table will be plotted.")
    chart_kind: ChartKind = Field(
        description="Chart type: 'bar', 'line', 'scatter', 'box', 'heatmap', 'pie', 'histogram', 'scatter_matrix', or 'correlation'."
    )
    output_path: str = Field(description="Destination file path for the rendered chart.")
    x: str | None = Field(default=None, description="Column name for x-axis (or category for bar/box/pie).")
    y: list[str] | None = Field(default=None, description="One or more column names for y-axis / values.")
    category: str | None = Field(default=None, description="Category / vertical grouping column (bar, box, pie, heatmap).")
    color: str | None = Field(default=None, description="Color grouping column for scatter plots.")
    value: str | None = Field(default=None, description="Value column for heatmap, pie, or correlation target.")
    aggregation: str = Field(default="AVG", description="Aggregation method: AVG, SUM, COUNT, MEDIAN, MIN, MAX.")
    title: str = Field(default="", description="Chart title.")
    subtitle: str = Field(default="", description="Optional chart subtitle.")
    x_label: str | None = Field(default=None, description="Optional x-axis label.")
    y_label: str | None = Field(default=None, description="Optional y-axis label.")
    orientation: Literal["vertical", "horizontal"] = Field(default="vertical", description="Bar chart orientation.")
    bar_mode: Literal["grouped", "stacked"] = Field(default="grouped", description="Multi-series bar layout.")
    donut: bool = Field(default=False, description="Render pie chart as a donut chart.")
    theme: ThemeName = Field(default="editorial", description="Visual theme.")
    fmt: Literal["png", "svg", "pdf"] = Field(default="png", description="Output image format.")
    dpi: int = Field(default=300, ge=72, le=600, description="Output DPI.")
    enhance: bool = Field(default=True, description="Enable publication enhancements.")
    include_base64: bool = Field(default=False, description="Include base64 PNG in result for visual inspection.")


class ListThemesInput(BaseModel):
    """Empty input schema for listing available visual themes."""
