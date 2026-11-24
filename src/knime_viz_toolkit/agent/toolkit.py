"""Unified AI Agent toolkit with OpenAI, Anthropic, and JSON-RPC tool-calling interfaces."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from ..io.workflow_reader import KnimeWorkflow
from ..models import RenderOptions
from ..rendering.engine import render_chart_spec
from ..rendering.themes import list_themes_info
from ..specs.extractor import (
    build_custom_chart_spec,
    extract_all_specs,
    extract_analytics_specs,
    extract_node_chart_spec,
)
from .schemas import (
    InspectWorkflowInput,
    ListChartNodesInput,
    ListThemesInput,
    ReadNodeDataInput,
    RenderCustomChartInput,
    RenderNodeChartInput,
    RenderWorkflowChartsInput,
    SuggestChartsInput,
)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any], dict[str, Any]]


def _encode_base64_png(path: str) -> str | None:
    p = Path(path)
    if p.exists() and p.suffix.lower() == ".png":
        return base64.b64encode(p.read_bytes()).decode("ascii")
    return None


class KnimeVizAgentToolkit:
    """Agent-ready façade exposing KNIME inspection, data extraction, and high-DPI chart rendering.

    Works seamlessly with:
    - OpenAI / Gemini / DeepSeek / Qwen function calling (`get_openai_tools()`)
    - Anthropic Claude tool use (`get_anthropic_tools()`)
    - Native MCP servers (`knime_viz_toolkit.agent.mcp_server`)
    - Custom Python agent loops (`call_tool(name, arguments)`)
    """

    def __init__(self, cache_workflows: bool = True) -> None:
        self._cache_workflows = cache_workflows
        self._wf_cache: dict[str, KnimeWorkflow] = {}
        self._tools: dict[str, ToolDefinition] = self._register_tools()

    def close(self) -> None:
        for wf in self._wf_cache.values():
            wf.close()
        self._wf_cache.clear()

    def _get_workflow(self, workflow_path: str) -> KnimeWorkflow:
        key = str(Path(workflow_path).resolve())
        if self._cache_workflows and key in self._wf_cache:
            return self._wf_cache[key]
        wf = KnimeWorkflow(workflow_path)
        if self._cache_workflows:
            self._wf_cache[key] = wf
        return wf

    def _release_if_uncached(self, wf: KnimeWorkflow) -> None:
        if not self._cache_workflows:
            wf.close()

    def _register_tools(self) -> dict[str, ToolDefinition]:
        defs = [
            ToolDefinition(
                name="inspect_workflow",
                description=(
                    "Inspect a KNIME workflow (.knwf or directory) and return its nodes, execution status, "
                    "visualization nodes, data nodes, Numeric Scorer metrics, and k-Means clustering results."
                ),
                input_model=InspectWorkflowInput,
                handler=self._handle_inspect_workflow,
            ),
            ToolDefinition(
                name="list_chart_nodes",
                description=(
                    "Extract normalized ChartSpec definitions for every KNIME visualization node (Bar, Line, "
                    "Scatter, Box, Heatmap, Pie, Scatter Matrix) and optional auto-synthesized analytics charts."
                ),
                input_model=ListChartNodesInput,
                handler=self._handle_list_chart_nodes,
            ),
            ToolDefinition(
                name="read_node_data",
                description=(
                    "Decode the actual executed data table from any KNIME node directly from the .knwf file, "
                    "returning shape, column statistics, and preview rows."
                ),
                input_model=ReadNodeDataInput,
                handler=self._handle_read_node_data,
            ),
            ToolDefinition(
                name="suggest_charts",
                description=(
                    "Analyze an executed KNIME data node's schema and statistics to recommend high-value "
                    "publication charts that can be rendered with render_custom_chart."
                ),
                input_model=SuggestChartsInput,
                handler=self._handle_suggest_charts,
            ),
            ToolDefinition(
                name="render_node_chart",
                description=(
                    "Automatically read a KNIME visualization or analytics node and render a publication-grade "
                    "high-DPI chart (PNG, SVG, or PDF) with optional title/label/theme customization."
                ),
                input_model=RenderNodeChartInput,
                handler=self._handle_render_node_chart,
            ),
            ToolDefinition(
                name="render_workflow_charts",
                description=(
                    "Batch-render all visualization nodes (and optional model/cluster analytics dashboards) "
                    "from a KNIME workflow into a directory with a manifest.json index."
                ),
                input_model=RenderWorkflowChartsInput,
                handler=self._handle_render_workflow_charts,
            ),
            ToolDefinition(
                name="render_custom_chart",
                description=(
                    "Render a brand-new high-quality chart (bar, line, scatter, box, heatmap, pie, histogram, "
                    "scatter_matrix, or correlation) from ANY executed data node in a KNIME workflow."
                ),
                input_model=RenderCustomChartInput,
                handler=self._handle_render_custom_chart,
            ),
            ToolDefinition(
                name="list_themes",
                description="List available publication-grade visual themes and color palettes.",
                input_model=ListThemesInput,
                handler=self._handle_list_themes,
            ),
        ]
        return {d.name: d for d in defs}

    # --- Tool schema exporters ---

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return OpenAI / Gemini / DeepSeek compatible function-calling tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_model.model_json_schema(),
                },
            }
            for t in self._tools.values()
        ]

    def get_anthropic_tools(self) -> list[dict[str, Any]]:
        """Return Anthropic Claude compatible tool definitions."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_model.model_json_schema(),
            }
            for t in self._tools.values()
        ]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    # --- Unified dispatcher ---

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate `arguments`, invoke tool `name`, and return a structured JSON-safe dict."""
        if name not in self._tools:
            return {
                "ok": False,
                "error": f"Unknown tool '{name}'. Available tools: {', '.join(self._tools.keys())}",
            }
        tool = self._tools[name]
        try:
            parsed = tool.input_model.model_validate(arguments or {})
            data = tool.handler(parsed)
            return {"ok": True, "tool": name, "data": data}
        except Exception as exc:
            return {"ok": False, "tool": name, "error": f"{type(exc).__name__}: {exc}"}

    def call_tool_json(self, name: str, arguments_json: str = "{}") -> str:
        """Convenience wrapper accepting and returning JSON strings for LLM loops."""
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "tool": name, "error": f"Invalid JSON arguments: {exc}"})
        return json.dumps(self.call_tool(name, args), ensure_ascii=False, indent=2)

    # --- Handlers ---

    def _handle_inspect_workflow(self, inp: InspectWorkflowInput) -> dict[str, Any]:
        wf = self._get_workflow(inp.workflow_path)
        try:
            summary = wf.summarize()
            return summary.model_dump()
        finally:
            self._release_if_uncached(wf)

    def _handle_list_chart_nodes(self, inp: ListChartNodesInput) -> dict[str, Any]:
        wf = self._get_workflow(inp.workflow_path)
        try:
            specs = extract_all_specs(wf, include_analytics=inp.include_analytics)
            return {
                "workflow_name": wf.workflow_name,
                "count": len(specs),
                "specs": [s.model_dump() for s in specs],
            }
        finally:
            self._release_if_uncached(wf)

    def _handle_read_node_data(self, inp: ReadNodeDataInput) -> dict[str, Any]:
        wf = self._get_workflow(inp.workflow_path)
        try:
            tbl = wf.read_node_table(inp.node_id, port=inp.port)
            node = wf.nodes[inp.node_id]
            return {
                "node_id": inp.node_id,
                "node_name": node.name,
                "annotation": node.annotation,
                "shape": {"rows": tbl.shape[0], "columns": tbl.shape[1]},
                "columns": tbl.columns,
                "column_stats": tbl.column_stats(),
                "preview_rows": tbl.head(inp.limit),
            }
        finally:
            self._release_if_uncached(wf)

    def _handle_suggest_charts(self, inp: SuggestChartsInput) -> dict[str, Any]:
        wf = self._get_workflow(inp.workflow_path)
        try:
            tbl = wf.read_node_table(inp.node_id)
            num_cols = [c for c in tbl.numeric_columns() if c.lower() not in ("instant", "id", "index")]
            date_cols = [c for c in tbl.columns if tbl.is_date_column(c)]
            cat_cols = tbl.categorical_columns(max_unique=24)

            suggestions: list[dict[str, Any]] = []
            if date_cols and num_cols:
                suggestions.append({
                    "chart_kind": "line",
                    "reason": f"Time-series trend of '{num_cols[-1]}' over '{date_cols[0]}'.",
                    "recommended_args": {"node_id": inp.node_id, "chart_kind": "line", "x": date_cols[0], "y": [num_cols[-1]]},
                })
            if cat_cols and num_cols:
                suggestions.append({
                    "chart_kind": "bar",
                    "reason": f"Compare average '{num_cols[-1]}' across '{cat_cols[0]}' categories.",
                    "recommended_args": {"node_id": inp.node_id, "chart_kind": "bar", "category": cat_cols[0], "y": [num_cols[-1]], "aggregation": "AVG"},
                })
                suggestions.append({
                    "chart_kind": "box",
                    "reason": f"Distribution & spread of '{num_cols[-1]}' grouped by '{cat_cols[0]}'.",
                    "recommended_args": {"node_id": inp.node_id, "chart_kind": "box", "category": cat_cols[0], "y": [num_cols[-1]]},
                })
            if len(num_cols) >= 2:
                suggestions.append({
                    "chart_kind": "scatter",
                    "reason": f"Explore nonlinear relationship between '{num_cols[0]}' and '{num_cols[-1]}'.",
                    "recommended_args": {
                        "node_id": inp.node_id,
                        "chart_kind": "scatter",
                        "x": num_cols[0],
                        "y": [num_cols[-1]],
                        "color": cat_cols[0] if cat_cols else None,
                    },
                })
            if len(num_cols) >= 3:
                suggestions.append({
                    "chart_kind": "correlation",
                    "reason": f"Rank feature correlations with target '{num_cols[-1]}'.",
                    "recommended_args": {"node_id": inp.node_id, "chart_kind": "correlation", "value": num_cols[-1]},
                })
            if len(cat_cols) >= 2 and num_cols:
                suggestions.append({
                    "chart_kind": "heatmap",
                    "reason": f"2D intensity heatmap of '{num_cols[-1]}' across '{cat_cols[0]}' × '{cat_cols[1]}'.",
                    "recommended_args": {
                        "node_id": inp.node_id,
                        "chart_kind": "heatmap",
                        "category": cat_cols[0],
                        "x": cat_cols[1],
                        "value": num_cols[-1],
                        "aggregation": "AVG",
                    },
                })

            return {
                "node_id": inp.node_id,
                "shape": {"rows": tbl.shape[0], "columns": tbl.shape[1]},
                "date_columns": date_cols,
                "categorical_columns": cat_cols,
                "numeric_columns": num_cols,
                "suggestions": suggestions,
            }
        finally:
            self._release_if_uncached(wf)

    def _handle_render_node_chart(self, inp: RenderNodeChartInput) -> dict[str, Any]:
        wf = self._get_workflow(inp.workflow_path)
        try:
            node = wf.nodes.get(inp.node_id)
            if node is None:
                raise KeyError(f"Node #{inp.node_id} not found.")
            if node.is_chart_node:
                spec = extract_node_chart_spec(wf, inp.node_id)
            else:
                analytics = extract_analytics_specs(wf)
                spec = next((s for s in analytics if s.node_id == inp.node_id), None)
                if spec is None:
                    raise ValueError(
                        f"Node #{inp.node_id} ({node.name}) is not a chart or analytics node. "
                        "Use render_custom_chart to plot arbitrary data nodes."
                    )
            opts = RenderOptions(
                theme=inp.theme,
                dpi=inp.dpi,
                fmt=inp.fmt,
                enhance=inp.enhance,
                title_override=inp.title_override,
                subtitle_override=inp.subtitle_override,
                x_label_override=inp.x_label_override,
                y_label_override=inp.y_label_override,
            )
            res = render_chart_spec(wf, spec, inp.output_path, opts)
            payload = res.model_dump()
            if inp.include_base64 and inp.fmt == "png":
                payload["image_base64"] = _encode_base64_png(res.output_path)
            return payload
        finally:
            self._release_if_uncached(wf)

    def _handle_render_workflow_charts(self, inp: RenderWorkflowChartsInput) -> dict[str, Any]:
        wf = self._get_workflow(inp.workflow_path)
        try:
            out_dir = Path(inp.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            specs = extract_all_specs(wf, include_analytics=inp.include_analytics)
            if inp.node_ids is not None:
                wanted = set(inp.node_ids)
                specs = [s for s in specs if s.node_id in wanted]

            opts = RenderOptions(theme=inp.theme, dpi=inp.dpi, fmt=inp.fmt, enhance=inp.enhance)
            rendered: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []

            for spec in specs:
                out_file = out_dir / f"{spec.spec_id}.{inp.fmt}"
                try:
                    res = render_chart_spec(wf, spec, out_file, opts)
                    rendered.append(res.model_dump())
                except Exception as exc:
                    errors.append({"spec_id": spec.spec_id, "node_id": spec.node_id, "error": str(exc)})

            manifest = {
                "workflow_path": str(Path(inp.workflow_path).resolve()),
                "workflow_name": wf.workflow_name,
                "theme": inp.theme,
                "format": inp.fmt,
                "dpi": inp.dpi,
                "rendered_count": len(rendered),
                "error_count": len(errors),
                "charts": rendered,
                "errors": errors,
            }
            manifest_path = out_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            manifest["manifest_path"] = str(manifest_path.resolve())
            return manifest
        finally:
            self._release_if_uncached(wf)

    def _handle_render_custom_chart(self, inp: RenderCustomChartInput) -> dict[str, Any]:
        wf = self._get_workflow(inp.workflow_path)
        try:
            spec = build_custom_chart_spec(
                node_id=inp.node_id,
                chart_kind=inp.chart_kind,
                x=inp.x,
                y=inp.y,
                category=inp.category,
                color=inp.color,
                value=inp.value,
                aggregation=inp.aggregation,
                title=inp.title,
                subtitle=inp.subtitle,
                x_label=inp.x_label,
                y_label=inp.y_label,
                orientation=inp.orientation,
                bar_mode=inp.bar_mode,
                donut=inp.donut,
            )
            opts = RenderOptions(theme=inp.theme, dpi=inp.dpi, fmt=inp.fmt, enhance=inp.enhance)
            res = render_chart_spec(wf, spec, inp.output_path, opts)
            payload = res.model_dump()
            if inp.include_base64 and inp.fmt == "png":
                payload["image_base64"] = _encode_base64_png(res.output_path)
            return payload
        finally:
            self._release_if_uncached(wf)

    def _handle_list_themes(self, _inp: ListThemesInput) -> dict[str, Any]:
        return {"themes": list_themes_info()}
