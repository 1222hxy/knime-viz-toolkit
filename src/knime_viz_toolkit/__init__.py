"""knime-viz-toolkit — Read executed KNIME workflows (.knwf) and render publication-grade charts."""

from __future__ import annotations

from pathlib import Path

from .agent.toolkit import KnimeVizAgentToolkit
from .io.table import KnimeTable
from .io.workflow_reader import KnimeWorkflow
from .models import (
    ChartKind,
    ChartSpec,
    NodeInfo,
    RenderOptions,
    RenderResult,
    ThemeName,
    WorkflowSummary,
)
from .rendering.engine import render_chart_spec
from .rendering.themes import get_theme, list_themes_info
from .specs.extractor import (
    build_custom_chart_spec,
    extract_all_specs,
    extract_analytics_specs,
    extract_node_chart_spec,
)

__version__ = "0.1.0"


def render_workflow(
    workflow_path: str | Path,
    output_dir: str | Path,
    theme: ThemeName = "editorial",
    fmt: str = "png",
    dpi: int = 300,
    enhance: bool = True,
    include_analytics: bool = True,
    watermark: bool = True,
    watermark_text: str = "1222hxy/knime-viz-toolkit",
) -> list[RenderResult]:
    """One-line helper: read a KNIME workflow and render every detected chart to `output_dir`."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    opts = RenderOptions(
        theme=theme,
        fmt=fmt,  # type: ignore[arg-type]
        dpi=dpi,
        enhance=enhance,
        watermark=watermark,
        watermark_text=watermark_text,
    )
    results: list[RenderResult] = []
    with KnimeWorkflow(workflow_path) as wf:
        specs = extract_all_specs(wf, include_analytics=include_analytics)
        for spec in specs:
            results.append(render_chart_spec(wf, spec, out / f"{spec.spec_id}.{fmt}", opts))
    return results


def render_node(
    workflow_path: str | Path,
    node_id: int,
    output_path: str | Path,
    theme: ThemeName = "editorial",
    fmt: str = "png",
    dpi: int = 300,
    enhance: bool = True,
    title_override: str | None = None,
    watermark: bool = True,
    watermark_text: str = "1222hxy/knime-viz-toolkit",
) -> RenderResult:
    """One-line helper: render a single KNIME visualization node to `output_path`."""
    opts = RenderOptions(
        theme=theme,
        fmt=fmt,  # type: ignore[arg-type]
        dpi=dpi,
        enhance=enhance,
        title_override=title_override,
        watermark=watermark,
        watermark_text=watermark_text,
    )
    with KnimeWorkflow(workflow_path) as wf:
        spec = extract_node_chart_spec(wf, node_id)
        return render_chart_spec(wf, spec, output_path, opts)


__all__ = [
    "ChartKind",
    "ChartSpec",
    "KnimeTable",
    "KnimeVizAgentToolkit",
    "KnimeWorkflow",
    "NodeInfo",
    "RenderOptions",
    "RenderResult",
    "ThemeName",
    "WorkflowSummary",
    "__version__",
    "build_custom_chart_spec",
    "extract_all_specs",
    "extract_analytics_specs",
    "extract_node_chart_spec",
    "get_theme",
    "list_themes_info",
    "render_chart_spec",
    "render_node",
    "render_workflow",
]
