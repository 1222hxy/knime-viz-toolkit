"""Tests for AI Agent Toolkit (OpenAI/Anthropic schemas, dispatch), CLI JSON mode, and MCP server."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from knime_viz_toolkit import KnimeVizAgentToolkit
from knime_viz_toolkit.agent.mcp_server import create_mcp_server

ROOT = Path(__file__).resolve().parents[2]
MASTER_KNWF = ROOT / "knime" / "Bike_Sharing_Master_Workflow_EXECUTED.knwf"


class TestAgentToolkitAndMCP(unittest.TestCase):
    def setUp(self) -> None:
        self.toolkit = KnimeVizAgentToolkit(cache_workflows=True)

    def tearDown(self) -> None:
        self.toolkit.close()

    def test_openai_and_anthropic_tool_schemas(self) -> None:
        oai = self.toolkit.get_openai_tools()
        ant = self.toolkit.get_anthropic_tools()
        self.assertEqual(len(oai), 8)
        self.assertEqual(len(ant), 8)
        for item in oai:
            self.assertEqual(item["type"], "function")
            self.assertIn("name", item["function"])
            self.assertIn("parameters", item["function"])
        for item in ant:
            self.assertIn("name", item)
            self.assertIn("input_schema", item)

    def test_error_handling_unknown_tool_and_bad_args(self) -> None:
        r1 = self.toolkit.call_tool("nonexistent_tool", {})
        self.assertFalse(r1["ok"])
        r2 = self.toolkit.call_tool("inspect_workflow", {"workflow_path": "missing_file.knwf"})
        self.assertFalse(r2["ok"])
        raw_json = self.toolkit.call_tool_json("list_themes", "{bad json")
        parsed = json.loads(raw_json)
        self.assertFalse(parsed["ok"])

    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_agent_end_to_end_workflow(self) -> None:
        wf_str = str(MASTER_KNWF)
        r_insp = self.toolkit.call_tool("inspect_workflow", {"workflow_path": wf_str})
        self.assertTrue(r_insp["ok"])
        self.assertEqual(r_insp["data"]["executed_nodes"], 51)

        r_data = self.toolkit.call_tool("read_node_data", {"workflow_path": wf_str, "node_id": 4, "limit": 5})
        self.assertTrue(r_data["ok"])
        self.assertEqual(r_data["data"]["shape"]["rows"], 731)
        self.assertEqual(len(r_data["data"]["preview_rows"]), 5)

        r_sug = self.toolkit.call_tool("suggest_charts", {"workflow_path": wf_str, "node_id": 4})
        self.assertTrue(r_sug["ok"])
        self.assertGreaterEqual(len(r_sug["data"]["suggestions"]), 3)

        with tempfile.TemporaryDirectory() as tmp:
            out_png = str(Path(tmp) / "agent_node13.png")
            r_ren = self.toolkit.call_tool(
                "render_node_chart",
                {
                    "workflow_path": wf_str,
                    "node_id": 13,
                    "output_path": out_png,
                    "theme": "editorial",
                    "dpi": 100,
                    "include_base64": True,
                },
            )
            self.assertTrue(r_ren["ok"])
            self.assertTrue(Path(out_png).exists())
            self.assertTrue(len(r_ren["data"].get("image_base64", "")) > 1000)

    def test_mcp_server_registers_all_tools(self) -> None:
        try:
            mcp = create_mcp_server()
        except ImportError:
            self.skipTest("mcp package not installed")
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        expected = {
            "inspect_workflow",
            "list_chart_nodes",
            "read_node_data",
            "suggest_charts",
            "render_node_chart",
            "render_workflow_charts",
            "render_custom_chart",
            "list_themes",
        }
        self.assertEqual(names, expected)

    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_cli_json_mode(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "knime_viz_toolkit.cli", "inspect", str(MASTER_KNWF), "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["total_nodes"], 51)


if __name__ == "__main__":
    unittest.main()
