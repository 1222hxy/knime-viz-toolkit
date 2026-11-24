"""Example: Integrating KnimeVizAgentToolkit into an OpenAI / Anthropic / Gemini agent loop."""

import json
from pathlib import Path
from knime_viz_toolkit import KnimeVizAgentToolkit

WORKFLOW = str(Path(__file__).resolve().parents[2] / "knime" / "Bike_Sharing_Master_Workflow_EXECUTED.knwf")
OUT_DIR = Path(__file__).resolve().parent / "_agent_demo_output"


def main() -> None:
    toolkit = KnimeVizAgentToolkit(cache_workflows=True)

    # 1. Export JSON Schemas for your LLM SDK
    openai_tools = toolkit.get_openai_tools()
    anthropic_tools = toolkit.get_anthropic_tools()
    print(f"Exported {len(openai_tools)} OpenAI tools & {len(anthropic_tools)} Anthropic tools:")
    print("  Tool names:", toolkit.tool_names)

    # 2. Simulate an autonomous agent inspecting a KNIME workflow and choosing charts
    inspect_res = toolkit.call_tool("inspect_workflow", {"workflow_path": WORKFLOW})
    assert inspect_res["ok"]
    print(
        f"\n[Agent Step 1] Inspected workflow: {inspect_res['data']['workflow_name']} "
        f"({len(inspect_res['data']['chart_nodes'])} chart nodes)"
    )

    # 3. Agent inspects an upstream data node (#4 Math Formula) and asks for chart recommendations
    suggest_res = toolkit.call_tool("suggest_charts", {"workflow_path": WORKFLOW, "node_id": 4})
    assert suggest_res["ok"]
    print(f"[Agent Step 2] Received {len(suggest_res['data']['suggestions'])} chart recommendations for Node #4:")
    for s in suggest_res["data"]["suggestions"]:
        print(f"  - {s['chart_kind']}: {s['reason']}")

    # 4. Agent renders a custom correlation chart directly from Node #4
    custom_res = toolkit.call_tool(
        "render_custom_chart",
        {
            "workflow_path": WORKFLOW,
            "node_id": 4,
            "chart_kind": "correlation",
            "value": "cnt",
            "title": "Feature Correlations with Daily Rentals (from KNIME Node #4)",
            "output_path": str(OUT_DIR / "agent_correlation.png"),
            "theme": "editorial",
        },
    )
    print("\n[Agent Step 3] Custom chart result:")
    print(json.dumps(custom_res, indent=2, ensure_ascii=False))

    toolkit.close()


if __name__ == "__main__":
    main()
