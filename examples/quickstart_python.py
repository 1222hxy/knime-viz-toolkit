"""Quickstart example: inspect a KNIME workflow and render all charts in Python."""

from pathlib import Path
from knime_viz_toolkit import KnimeWorkflow, render_workflow, render_node

# Point to any executed .knwf file
WORKFLOW = Path(__file__).resolve().parents[2] / "knime" / "Bike_Sharing_Master_Workflow_EXECUTED.knwf"
OUT_DIR = Path(__file__).resolve().parent / "_demo_output"


def main() -> None:
    if not WORKFLOW.exists():
        print(f"Sample workflow not found at {WORKFLOW}. Pass your own .knwf path.")
        return

    with KnimeWorkflow(WORKFLOW) as wf:
        summary = wf.summarize()
        print(f"Loaded '{summary.workflow_name}': {summary.executed_nodes}/{summary.total_nodes} nodes executed")
        print(f"Detected {len(summary.chart_nodes)} chart nodes, {len(summary.scorers)} scorers, {len(summary.kmeans)} k-Means")

    # 1. Batch-render every visualization + analytics node in editorial theme
    results = render_workflow(WORKFLOW, OUT_DIR / "editorial", theme="editorial", dpi=300)
    print(f"\nRendered {len(results)} charts into {OUT_DIR / 'editorial'}:")
    for r in results:
        print(f"  - [{r.chart_kind}] {r.title} -> {r.output_path} ({r.width_px}x{r.height_px})")

    # 2. Render a single node in academic theme as crisp vector SVG
    single = render_node(
        WORKFLOW,
        node_id=13,
        output_path=OUT_DIR / "node13_academic.svg",
        theme="academic",
        fmt="svg",
        title_override="Daily Demand vs. Temperature (°C)",
    )
    print(f"\nSingle SVG rendered -> {single.output_path}")


if __name__ == "__main__":
    main()
