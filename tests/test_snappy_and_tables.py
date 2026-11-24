"""Tests for Snappy decompression, KnimeTable operations, and KNIME binary table decoding."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from knime_viz_toolkit.io import KnimeTable, KnimeWorkflow, smart_sort_key

ROOT = Path(__file__).resolve().parents[2]
MASTER_KNWF = ROOT / "knime" / "Bike_Sharing_Master_Workflow_EXECUTED.knwf"
REF_KNWF = ROOT / "data" / "reference_pack" / "bike_tree_polished.knwf"
MODELS_KNWF = ROOT / "knime" / "models.knwf"


class TestKnimeTableUnit(unittest.TestCase):
    def test_smart_sort_key_numeric_strings(self) -> None:
        raw = ["1", "10", "2", "12", "3", "11"]
        self.assertEqual(sorted(raw, key=smart_sort_key), ["1", "2", "3", "10", "11", "12"])

    def test_groupby_and_pivot(self) -> None:
        tbl = KnimeTable(
            columns=["cat", "grp", "val"],
            data={"cat": ["10", "2", "10", "2"], "grp": ["A", "A", "B", "B"], "val": [10.0, 20.0, 30.0, 40.0]},
        )
        keys, agg = tbl.groupby_agg("cat", ["val"], method="AVG")
        self.assertEqual(keys, ["2", "10"])
        self.assertEqual(agg["val"], [30.0, 20.0])

        rows, cols, mat = tbl.pivot_agg("cat", "grp", "val", method="SUM")
        self.assertEqual(rows, ["2", "10"])
        self.assertEqual(cols, ["A", "B"])
        self.assertEqual(mat[0, 0], 20.0)
        self.assertEqual(mat[1, 1], 30.0)


class TestRealWorkflowDecoding(unittest.TestCase):
    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_decode_every_node_in_master_workflow(self) -> None:
        with KnimeWorkflow(MASTER_KNWF) as wf:
            summary = wf.summarize()
            self.assertEqual(summary.total_nodes, 51)
            self.assertEqual(summary.executed_nodes, 51)
            for node in summary.data_nodes:
                tbl = wf.read_node_table(node.node_id)
                self.assertGreater(tbl.shape[1], 0, f"Node #{node.node_id} had 0 columns")
            for node in summary.chart_nodes:
                tbl, _ = wf.get_input_table(node.node_id)
                self.assertGreater(tbl.shape[0], 0, f"Chart node #{node.node_id} had 0 input rows")

            # Spot-check Math Formula (#4) exact values (temp * 41 on day 1 = 14.110847)
            t4 = wf.read_node_table(4)
            self.assertEqual(t4.shape[0], 731)
            self.assertIn("temp_C", t4.columns)
            self.assertAlmostEqual(t4["temp_C"][0], 0.344167 * 41.0, places=3)

    @unittest.skipUnless(REF_KNWF.exists(), "Sample reference .knwf not present")
    def test_decode_unpacked_directory_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(REF_KNWF, "r") as z:
                z.extractall(tmp)
            wf_dir = Path(tmp) / "bike_tree_polished"
            with KnimeWorkflow(wf_dir) as wf:
                summary = wf.summarize()
                self.assertEqual(summary.total_nodes, 30)
                self.assertEqual(len(summary.chart_nodes), 13)
                for n in summary.chart_nodes:
                    tbl, _ = wf.get_input_table(n.node_id)
                    self.assertGreater(len(tbl), 0)

    @unittest.skipUnless(MODELS_KNWF.exists(), "Sample models .knwf not present")
    def test_decode_models_workflow(self) -> None:
        with KnimeWorkflow(MODELS_KNWF) as wf:
            summary = wf.summarize()
            self.assertEqual(summary.total_nodes, 18)
            for n in summary.data_nodes:
                tbl = wf.read_node_table(n.node_id)
                self.assertGreater(tbl.shape[1], 0)


if __name__ == "__main__":
    unittest.main()
