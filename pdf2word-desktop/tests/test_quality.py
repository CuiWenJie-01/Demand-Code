from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pdf2word_engine.models import PageBlock, PageModel, PageSize, PdfKind
from pdf2word_engine.quality import character_error_rate, compare_rasters, editable_quality_report, normalize_cer_text


class QualityTests(unittest.TestCase):
    def test_editable_quality_report_identifies_fallbacks_without_text(self) -> None:
        report = editable_quality_report(
            [
                PageModel(
                    schema_version=1,
                    page_index=0,
                    size=PageSize(595, 842),
                    source_type=PdfKind.OUTLINED,
                    blocks=[
                        PageBlock("text", "text", (0, 0, 10, 10), 0, 0, text="不应出现在报告中的正文"),
                        PageBlock("image", "image", (10, 10, 20, 20), 1, 1, asset_path="region.png"),
                    ],
                )
            ]
        )

        self.assertEqual(report["summary"]["editable_text_blocks"], 1)
        self.assertEqual(report["summary"]["image_fallback_blocks"], 1)
        self.assertNotIn("不应出现在报告中的正文", str(report))

    def test_identical_images_have_perfect_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "page.png"
            Image.new("L", (32, 32), color=180).save(path)
            result = compare_rasters(path, path)

        self.assertTrue(result.same_dimensions)
        self.assertEqual(result.ssim, 1.0)
        self.assertEqual(result.mean_absolute_error, 0.0)

    def test_different_images_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            left = Path(temp) / "left.png"
            right = Path(temp) / "right.png"
            Image.new("L", (32, 32), color=0).save(left)
            Image.new("L", (32, 32), color=255).save(right)
            result = compare_rasters(left, right)

        self.assertLess(result.ssim, 0.1)
        self.assertGreater(result.mean_absolute_error, 200)

    def test_cer_normalizes_spacing_and_full_width_characters(self) -> None:
        result = character_error_rate("第 １ 题", "第1题")

        self.assertEqual(normalize_cer_text("Ａ B"), "AB")
        self.assertEqual(result.reference_characters, 3)
        self.assertEqual(result.errors, 0)
        self.assertEqual(result.cer, 0.0)

    def test_cer_rejects_missing_human_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能为空"):
            character_error_rate("", "OCR 输出")
