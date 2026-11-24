"""Tests for workflow topology, Color Manager, Numeric Scorer, k-Means, and ChartSpec extraction."""

from __future__ import annotations

import unittest
from pathlib import Path

from knime_viz_toolkit import KnimeWorkflow, extract_all_specs, extract_node_chart_spec

ROOT = Path(__file__).resolve().parents[2]
MASTER_KNWF = ROOT / "knime" / "Bike_Sharing_Master_Workflow_EXECUTED.knwf"
REF_KNWF = ROOT / "data" / "reference_pack" / "bike_tree_polished.knwf"


class TestWorkflowAndSpecs(unittest.TestCase):
    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_scorers_and_kmeans_accuracy(self) -> None:
        with KnimeWorkflow(MASTER_KNWF) as wf:
            by_id = {s.node_id: s for s in wf.scorers}
            self.assertEqual(set(by_id.keys()), {65, 68, 74, 77})
            self.assertAlmostEqual(by_id[65].r2, 0.8183, places=3)
            self.assertAlmostEqual(by_id[68].r2, 0.8972, places=3)
            self.assertAlmostEqual(by_id[74].r2, 0.3919, places=3)
            self.assertAlmostEqual(by_id[77].r2, 0.9036, places=3)

            self.assertEqual(len(wf.kmeans_results), 1)
            km = wf.kmeans_results[0]
            self.assertEqual(km.features, ["casual", "registered"])
            self.assertEqual(sum(km.coverage), 731)

    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_extract_all_chart_and_analytics_specs(self) -> None:
        with KnimeWorkflow(MASTER_KNWF) as wf:
            specs = extract_all_specs(wf, include_analytics=True)
            kinds = {s.chart_kind for s in specs}
            self.assertTrue({"bar", "line", "scatter", "box", "heatmap", "pie"}.issubset(kinds))
            self.assertTrue({"model_comparison", "kmeans_regimes", "predictor_diagnostics"}.issubset(kinds))

            # Verify Color Manager was extracted upstream of Scatter Plot (#13)
            sp13 = extract_node_chart_spec(wf, 13)
            self.assertEqual(sp13.x_column, "temp_C")
            self.assertEqual(sp13.y_columns, ["cnt"])
            self.assertEqual(sp13.color_column, "yr")
            self.assertTrue(len(sp13.color_map) >= 2)

    @unittest.skipUnless(REF_KNWF.exists(), "Sample reference .knwf not present")
    def test_extract_scatter_matrix_in_reference_workflow(self) -> None:
        with KnimeWorkflow(REF_KNWF) as wf:
            specs = extract_all_specs(wf, include_analytics=False)
            self.assertEqual(len(specs), 13)
            self.assertIn("scatter_matrix", {s.chart_kind for s in specs})


if __name__ == "__main__":
    unittest.main()
