"""Native Model Context Protocol (MCP) stdio server for AI Agents.

Run via:
    knime-viz-mcp
or:
    python -m knime_viz_toolkit.agent.mcp_server
"""

from __future__ import annotations

import json
from typing import Any, Literal

from .toolkit import KnimeVizAgentToolkit


def create_mcp_server() -> Any:
    """Create and configure a FastMCP server exposing all knime-viz-toolkit tools."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "MCP support requires the `mcp` package. Install it with `pip install 'knime-viz-toolkit[mcp]'`."
        ) from exc

    mcp = FastMCP("knime-viz-toolkit")
    toolkit = KnimeVizAgentToolkit(cache_workflows=True)

    @mcp.tool()
    def inspect_workflow(workflow_path: str) -> str:
        """Inspect a KNIME workflow (.knwf or directory) and return all nodes, chart nodes, scorers, and k-Means results."""
        return json.dumps(toolkit.call_tool("inspect_workflow", {"workflow_path": workflow_path}), ensure_ascii=False, indent=2)

    @mcp.tool()
    def list_chart_nodes(workflow_path: str, include_analytics: bool = True) -> str:
        """List normalized ChartSpec definitions extracted from every visualization & analytics node in a KNIME workflow."""
        return json.dumps(
            toolkit.call_tool("list_chart_nodes", {"workflow_path": workflow_path, "include_analytics": include_analytics}),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool()
    def read_node_data(workflow_path: str, node_id: int, port: int = 1, limit: int = 15) -> str:
        """Decode the executed data table of any KNIME node and return column statistics and preview rows."""
        return json.dumps(
            toolkit.call_tool("read_node_data", {"workflow_path": workflow_path, "node_id": node_id, "port": port, "limit": limit}),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool()
    def suggest_charts(workflow_path: str, node_id: int) -> str:
        """Analyze an executed KNIME data node and recommend high-value charts to render."""
        return json.dumps(
            toolkit.call_tool("suggest_charts", {"workflow_path": workflow_path, "node_id": node_id}),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool()
    def render_node_chart(
        workflow_path: str,
        node_id: int,
        output_path: str,
        theme: Literal["editorial", "academic", "nature", "presentation_dark", "dark_transparent", "knime_enhanced"] = "editorial",
        fmt: Literal["png", "svg", "pdf"] = "png",
        dpi: int = 300,
        enhance: bool = True,
        title_override: str | None = None,
        subtitle_override: str | None = None,
        x_label_override: str | None = None,
        y_label_override: str | None = None,
    ) -> str:
        """Render a specific KNIME visualization or analytics node into a high-DPI publication chart."""
        args = {
            "workflow_path": workflow_path,
            "node_id": node_id,
            "output_path": output_path,
            "theme": theme,
            "fmt": fmt,
            "dpi": dpi,
            "enhance": enhance,
            "title_override": title_override,
            "subtitle_override": subtitle_override,
            "x_label_override": x_label_override,
            "y_label_override": y_label_override,
        }
        return json.dumps(toolkit.call_tool("render_node_chart", args), ensure_ascii=False, indent=2)

    @mcp.tool()
    def render_workflow_charts(
        workflow_path: str,
        output_dir: str,
        theme: Literal["editorial", "academic", "nature", "presentation_dark", "dark_transparent", "knime_enhanced"] = "editorial",
        fmt: Literal["png", "svg", "pdf"] = "png",
        dpi: int = 300,
        enhance: bool = True,
        include_analytics: bool = True,
        node_ids: list[int] | None = None,
    ) -> str:
        """Batch-render every visualization and analytics node in a KNIME workflow into high-DPI charts."""
        args = {
            "workflow_path": workflow_path,
            "output_dir": output_dir,
            "theme": theme,
            "fmt": fmt,
            "dpi": dpi,
            "enhance": enhance,
            "include_analytics": include_analytics,
            "node_ids": node_ids,
        }
        return json.dumps(toolkit.call_tool("render_workflow_charts", args), ensure_ascii=False, indent=2)

    @mcp.tool()
    def render_custom_chart(
        workflow_path: str,
        node_id: int,
        chart_kind: Literal["bar", "line", "scatter", "box", "heatmap", "pie", "histogram", "scatter_matrix", "correlation"],
        output_path: str,
        x: str | None = None,
        y: list[str] | None = None,
        category: str | None = None,
        color: str | None = None,
        value: str | None = None,
        aggregation: str = "AVG",
        title: str = "",
        subtitle: str = "",
        theme: Literal["editorial", "academic", "nature", "presentation_dark", "dark_transparent", "knime_enhanced"] = "editorial",
        fmt: Literal["png", "svg", "pdf"] = "png",
        dpi: int = 300,
        enhance: bool = True,
    ) -> str:
        """Synthesize a custom publication chart from ANY executed KNIME data node."""
        args = {
            "workflow_path": workflow_path,
            "node_id": node_id,
            "chart_kind": chart_kind,
            "output_path": output_path,
            "x": x,
            "y": y,
            "category": category,
            "color": color,
            "value": value,
            "aggregation": aggregation,
            "title": title,
            "subtitle": subtitle,
            "theme": theme,
            "fmt": fmt,
            "dpi": dpi,
            "enhance": enhance,
        }
        return json.dumps(toolkit.call_tool("render_custom_chart", args), ensure_ascii=False, indent=2)

    @mcp.tool()
    def list_themes() -> str:
        """List all available visual themes and color palettes."""
        return json.dumps(toolkit.call_tool("list_themes", {}), ensure_ascii=False, indent=2)

    return mcp


def main() -> None:
    server = create_mcp_server()
    server.run()


if __name__ == "__main__":
    main()
