"""Command-line interface (`knime-viz`) for humans and shell-based AI Agents."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from .agent.toolkit import KnimeVizAgentToolkit


def _emit(res: dict[str, Any], as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(res, ensure_ascii=False, indent=2))
        if not res.get("ok", False):
            sys.exit(1)
        return
    if not res.get("ok", False):
        click.secho(f"Error: {res.get('error', 'Unknown error')}", fg="red", err=True)
        sys.exit(1)


@click.group()
@click.version_option(package_name="knime-viz-toolkit", prog_name="knime-viz")
def main() -> None:
    """KNIME Viz Toolkit — Read executed KNIME workflows (.knwf) and render publication-grade charts."""


@main.command("inspect")
@click.argument("workflow_path")
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON (ideal for AI Agents).")
def cmd_inspect(workflow_path: str, as_json: bool) -> None:
    """Inspect nodes, execution status, chart nodes, scorers, and k-Means in a KNIME workflow."""
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool("inspect_workflow", {"workflow_path": workflow_path})
    _emit(res, as_json)
    if as_json:
        return
    d = res["data"]
    click.secho(f"Workflow: {d['workflow_name']}", fg="cyan", bold=True)
    click.echo(
        f"  Nodes: {d['total_nodes']} total ({d['executed_nodes']} executed, {d['unexecuted_nodes']} unexecuted) | "
        f"Connections: {d['connections_count']}"
    )
    click.echo(f"  Chart nodes ({len(d['chart_nodes'])}):")
    for n in d["chart_nodes"]:
        ann = n["annotation"].splitlines()[0] if n["annotation"] else ""
        click.echo(f"    #{n['node_id']:>2d} [{n['chart_kind']:<14s}] {n['name']:<24s} ({n['state']}) {ann}")
    if d["scorers"]:
        click.echo(f"  Numeric Scorers ({len(d['scorers'])}):")
        for sc in d["scorers"]:
            click.echo(f"    #{sc['node_id']:>2d} {sc['label']}: R2={sc['r2']} | MAE={sc['mae']} | RMSE={sc['rmse']}")
    if d["kmeans"]:
        click.echo(f"  k-Means ({len(d['kmeans'])}):")
        for km in d["kmeans"]:
            click.echo(f"    #{km['node_id']:>2d} {km['label']}: features={km['features']}, coverage={km['coverage']}")


@main.command("list")
@click.argument("workflow_path")
@click.option("--no-analytics", is_flag=True, help="Exclude auto-synthesized analytics charts.")
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
def cmd_list(workflow_path: str, no_analytics: bool, as_json: bool) -> None:
    """List extracted ChartSpec definitions for a KNIME workflow."""
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool("list_chart_nodes", {"workflow_path": workflow_path, "include_analytics": not no_analytics})
    _emit(res, as_json)
    if as_json:
        return
    d = res["data"]
    click.secho(f"Extracted {d['count']} ChartSpec(s) from {d['workflow_name']}:", fg="cyan", bold=True)
    for sp in d["specs"]:
        click.echo(f"  [{sp['chart_kind']:<20s}] node=#{str(sp['node_id']):<4s} | {sp['title']}")


@main.command("data")
@click.argument("workflow_path")
@click.argument("node_id", type=int)
@click.option("--port", default=1, show_default=True, help="Port index.")
@click.option("--limit", default=10, show_default=True, help="Preview row limit.")
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
def cmd_data(workflow_path: str, node_id: int, port: int, limit: int, as_json: bool) -> None:
    """Inspect schema, summary stats, and preview rows of an executed KNIME node."""
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool("read_node_data", {"workflow_path": workflow_path, "node_id": node_id, "port": port, "limit": limit})
    _emit(res, as_json)
    if as_json:
        return
    d = res["data"]
    click.secho(f"Node #{d['node_id']} ({d['node_name']}) — {d['shape']['rows']} rows × {d['shape']['columns']} cols", fg="cyan", bold=True)
    for cs in d["column_stats"]:
        extra = f"min={cs.get('min')}, max={cs.get('max')}, mean={cs.get('mean')}" if cs["inferred_type"] == "numeric" else f"unique={cs['unique']}"
        click.echo(f"  - {cs['name']:<24s} [{cs['inferred_type']:<11s}] {extra}")


@main.command("suggest")
@click.argument("workflow_path")
@click.argument("node_id", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
def cmd_suggest(workflow_path: str, node_id: int, as_json: bool) -> None:
    """Suggest high-value charts for any executed KNIME data node."""
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool("suggest_charts", {"workflow_path": workflow_path, "node_id": node_id})
    _emit(res, as_json)
    if as_json:
        return
    d = res["data"]
    click.secho(f"Chart suggestions for Node #{node_id}:", fg="cyan", bold=True)
    for idx, s in enumerate(d["suggestions"], start=1):
        click.echo(f"  {idx}. [{s['chart_kind']}] {s['reason']}")


@main.command("render")
@click.argument("workflow_path")
@click.option("-o", "--output-dir", required=True, help="Destination directory for rendered charts.")
@click.option("--theme", default="editorial", show_default=True, type=click.Choice(["editorial", "academic", "nature", "presentation_dark", "knime_enhanced"]))
@click.option("--format", "fmt", default="png", show_default=True, type=click.Choice(["png", "svg", "pdf"]))
@click.option("--dpi", default=300, show_default=True, type=int)
@click.option("--no-enhance", is_flag=True, help="Disable trendlines, moving averages, and auto value labels.")
@click.option("--no-analytics", is_flag=True, help="Only render explicit KNIME visualization nodes.")
@click.option("--nodes", "node_ids_str", default=None, help="Comma-separated node IDs to render (e.g. '10,11,13').")
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
def cmd_render(
    workflow_path: str,
    output_dir: str,
    theme: str,
    fmt: str,
    dpi: int,
    no_enhance: bool,
    no_analytics: bool,
    node_ids_str: str | None,
    as_json: bool,
) -> None:
    """Batch-render all charts in a KNIME workflow to publication-grade images."""
    node_ids = [int(x.strip()) for x in node_ids_str.split(",") if x.strip()] if node_ids_str else None
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool(
        "render_workflow_charts",
        {
            "workflow_path": workflow_path,
            "output_dir": output_dir,
            "theme": theme,
            "fmt": fmt,
            "dpi": dpi,
            "enhance": not no_enhance,
            "include_analytics": not no_analytics,
            "node_ids": node_ids,
        },
    )
    _emit(res, as_json)
    if as_json:
        return
    d = res["data"]
    click.secho(f"Rendered {d['rendered_count']} chart(s) ({d['error_count']} error(s)) -> {output_dir}", fg="green", bold=True)
    for ch in d["charts"]:
        click.echo(f"  [OK] {ch['chart_kind']:<20s} -> {ch['output_path']} ({ch['width_px']}x{ch['height_px']})")
    for err in d["errors"]:
        click.secho(f"  [ERR] {err['spec_id']}: {err['error']}", fg="red")


@main.command("render-node")
@click.argument("workflow_path")
@click.argument("node_id", type=int)
@click.option("-o", "--output", "output_path", required=True, help="Output image path.")
@click.option("--theme", default="editorial", show_default=True, type=click.Choice(["editorial", "academic", "nature", "presentation_dark", "knime_enhanced"]))
@click.option("--format", "fmt", default="png", show_default=True, type=click.Choice(["png", "svg", "pdf"]))
@click.option("--dpi", default=300, show_default=True, type=int)
@click.option("--title", "title_override", default=None, help="Override chart title.")
@click.option("--no-enhance", is_flag=True, help="Disable enhancements.")
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
def cmd_render_node(
    workflow_path: str,
    node_id: int,
    output_path: str,
    theme: str,
    fmt: str,
    dpi: int,
    title_override: str | None,
    no_enhance: bool,
    as_json: bool,
) -> None:
    """Render a single KNIME visualization or analytics node."""
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool(
        "render_node_chart",
        {
            "workflow_path": workflow_path,
            "node_id": node_id,
            "output_path": output_path,
            "theme": theme,
            "fmt": fmt,
            "dpi": dpi,
            "enhance": not no_enhance,
            "title_override": title_override,
        },
    )
    _emit(res, as_json)
    if as_json:
        return
    d = res["data"]
    click.secho(f"Rendered Node #{node_id} ({d['chart_kind']}) -> {d['output_path']}", fg="green", bold=True)


@main.command("custom")
@click.argument("workflow_path")
@click.argument("node_id", type=int)
@click.option("--kind", "chart_kind", required=True, type=click.Choice(["bar", "line", "scatter", "box", "heatmap", "pie", "histogram", "scatter_matrix", "correlation"]))
@click.option("-o", "--output", "output_path", required=True, help="Output image path.")
@click.option("--x", default=None, help="X column.")
@click.option("--y", multiple=True, help="Y column(s); repeat --y for multiple series.")
@click.option("--category", default=None, help="Category / vertical column.")
@click.option("--color", default=None, help="Color grouping column.")
@click.option("--value", default=None, help="Value / target column.")
@click.option("--agg", "aggregation", default="AVG", show_default=True)
@click.option("--title", default="", help="Chart title.")
@click.option("--theme", default="editorial", show_default=True, type=click.Choice(["editorial", "academic", "nature", "presentation_dark", "knime_enhanced"]))
@click.option("--format", "fmt", default="png", show_default=True, type=click.Choice(["png", "svg", "pdf"]))
@click.option("--dpi", default=300, show_default=True, type=int)
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
def cmd_custom(
    workflow_path: str,
    node_id: int,
    chart_kind: str,
    output_path: str,
    x: str | None,
    y: tuple[str, ...],
    category: str | None,
    color: str | None,
    value: str | None,
    aggregation: str,
    title: str,
    theme: str,
    fmt: str,
    dpi: int,
    as_json: bool,
) -> None:
    """Synthesize a custom chart from ANY executed data node in a KNIME workflow."""
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool(
        "render_custom_chart",
        {
            "workflow_path": workflow_path,
            "node_id": node_id,
            "chart_kind": chart_kind,
            "output_path": output_path,
            "x": x,
            "y": list(y) if y else None,
            "category": category,
            "color": color,
            "value": value,
            "aggregation": aggregation,
            "title": title,
            "theme": theme,
            "fmt": fmt,
            "dpi": dpi,
        },
    )
    _emit(res, as_json)
    if as_json:
        return
    d = res["data"]
    click.secho(f"Rendered custom {chart_kind} from Node #{node_id} -> {d['output_path']}", fg="green", bold=True)


@main.command("themes")
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
def cmd_themes(as_json: bool) -> None:
    """List available visual themes."""
    tk = KnimeVizAgentToolkit(cache_workflows=False)
    res = tk.call_tool("list_themes", {})
    _emit(res, as_json)
    if as_json:
        return
    for t in res["data"]["themes"]:
        click.secho(f"  {t['name']:<18s}", fg="cyan", bold=True, nl=False)
        click.echo(f" — {t['description']}")


@main.command("mcp")
def cmd_mcp() -> None:
    """Start the native Model Context Protocol (MCP) stdio server for AI Agents."""
    from .agent.mcp_server import main as mcp_main

    mcp_main()


if __name__ == "__main__":
    main()
