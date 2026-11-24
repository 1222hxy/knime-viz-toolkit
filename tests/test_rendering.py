"""Tests for high-DPI Matplotlib rendering across chart types, themes, and output formats."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knime_viz_toolkit import (
    KnimeWorkflow,
    RenderOptions,
    build_custom_chart_spec,
    render_chart_spec,
    render_node,
    render_workflow,
)

ROOT = Path(__file__).resolve().parents[2]
MASTER_KNWF = ROOT / "knime" / "Bike_Sharing_Master_Workflow_EXECUTED.knwf"
REF_KNWF = ROOT / "data" / "reference_pack" / "bike_tree_polished.knwf"


class TestRendering(unittest.TestCase):
    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_render_all_master_charts_and_analytics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = render_workflow(MASTER_KNWF, tmp, theme="editorial", dpi=150, include_analytics=True)
            self.assertEqual(len(results), 18)
            for res in results:
                p = Path(res.output_path)
                self.assertTrue(p.exists(), f"Missing output: {p}")
                self.assertGreater(p.stat().st_size, 5_000, f"Suspiciously small PNG: {p}")
                self.assertGreater(res.width_px or 0, 500)
                self.assertGreater(res.height_px or 0, 300)

    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_themes_and_vector_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for theme in ("editorial", "academic", "nature", "presentation_dark", "dark_transparent", "knime_enhanced"):
                res = render_node(MASTER_KNWF, 13, tmp_path / f"s_{theme}.png", theme=theme, dpi=120)
                self.assertTrue(Path(res.output_path).exists())
            # Verify dark_transparent actually produces an RGBA PNG with transparent background
            from PIL import Image
            with Image.open(tmp_path / "s_dark_transparent.png") as im:
                self.assertEqual(im.mode, "RGBA")
                self.assertEqual(im.getpixel((0, 0))[3], 0)
            svg_res = render_node(MASTER_KNWF, 11, tmp_path / "bar.svg", theme="nature", fmt="svg")
            svg_txt = Path(svg_res.output_path).read_text(encoding="utf-8")
            self.assertTrue(svg_txt.startswith("<?xml"))
            self.assertIn("1222hxy/knime-viz-toolkit", svg_txt)
            # Verify watermark can be cleanly disabled via watermark=False
            svg_no_wm = render_node(MASTER_KNWF, 11, tmp_path / "bar_nowm.svg", theme="nature", fmt="svg", watermark=False)
            self.assertNotIn("1222hxy/knime-viz-toolkit", Path(svg_no_wm.output_path).read_text(encoding="utf-8"))
            pdf_res = render_node(MASTER_KNWF, 22, tmp_path / "pie.pdf", theme="academic", fmt="pdf")
            self.assertTrue(Path(pdf_res.output_path).read_bytes().startswith(b"%PDF"))

    @unittest.skipUnless(MASTER_KNWF.exists(), "Sample master .knwf not present")
    def test_custom_histogram_and_correlation_from_data_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, KnimeWorkflow(MASTER_KNWF) as wf:
            tmp_path = Path(tmp)
            hist_spec = build_custom_chart_spec(node_id=4, chart_kind="histogram", x="cnt", title="Daily Count Dist")
            r1 = render_chart_spec(wf, hist_spec, tmp_path / "hist.png", RenderOptions(dpi=120))
            self.assertTrue(Path(r1.output_path).exists())

            corr_spec = build_custom_chart_spec(node_id=4, chart_kind="correlation", value="cnt", title="Correlations")
            r2 = render_chart_spec(wf, corr_spec, tmp_path / "corr.png", RenderOptions(dpi=120))
            self.assertTrue(Path(r2.output_path).exists())

    @unittest.skipUnless(REF_KNWF.exists(), "Sample reference .knwf not present")
    def test_render_scatter_matrix_and_cjk_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res = render_node(REF_KNWF, 28, Path(tmp) / "matrix.png", theme="academic", dpi=120)
            self.assertTrue(Path(res.output_path).exists())
            self.assertGreater(Path(res.output_path).stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
