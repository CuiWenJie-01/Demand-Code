from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pdf2word_engine.models import PageBlock, PageModel, PageSize, PdfKind
from pdf2word_engine.conflicts import resolve_page_model_conflicts
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

    def test_conflict_resolver_keeps_one_cleaner_focused_line_and_audits_removal(self) -> None:
        model = PageModel(
            schema_version=4,
            page_index=22,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
            blocks=[
                PageBlock("main", "text_line", (100, 100, 500, 125), 1, 1, confidence=0.999, text="本题是工程类问题。", style={"semantic_role": "callout_body", "source": "PaddleOCR line"}),
                PageBlock("focused", "text_line", (98, 99, 502, 126), 2, 2, confidence=0.9999, text="示本题是工程类问题。", style={"semantic_role": "callout_body", "source": "focused PaddleOCR line"}),
                PageBlock("formula", "formula", (520, 90, 620, 140), 3, 3, asset_path="formula.png"),
                PageBlock("formula-ocr", "text_line", (530, 100, 590, 120), 4, 4, confidence=0.99, text="1+3"),
            ],
        )

        resolve_page_model_conflicts(model)

        self.assertEqual([block.block_id for block in model.blocks if block.text], ["focused"])
        self.assertEqual(model.blocks[0].text, "本题是工程类问题。")
        self.assertEqual(len(model.debug_records), 2)
        report = editable_quality_report([model])
        self.assertEqual(report["summary"]["conflict_pages"], [])
        self.assertEqual(report["summary"]["formula_fallback_pages"], [23])

    def test_conflict_resolver_removes_the_named_source_watermark(self) -> None:
        model = PageModel(
            schema_version=5,
            page_index=1,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
            blocks=[
                PageBlock("body", "text_line", (20, 20, 200, 45), 1, 1, text="可编辑正文"),
                PageBlock("source-watermark", "watermark", (50, 50, 300, 300), -1, -1, asset_path="watermark.png", style={"source": "neutral-gray central watermark"}),
            ],
        )

        resolve_page_model_conflicts(model)

        self.assertEqual([block.block_id for block in model.blocks], ["body"])
        self.assertTrue(any(item["block_id"] == "source-watermark" for item in model.debug_records))

    def test_formula_heavy_callout_crop_is_reported_as_formula_fallback(self) -> None:
        model = PageModel(
            schema_version=7,
            page_index=20,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
            page_class="formula_heavy",
            blocks=[
                PageBlock(
                    "formula-callout-row",
                    "talk_callout_tag_image",
                    (100, 100, 800, 170),
                    0,
                    0,
                    asset_path="formula-row.png",
                    fallback_mode="callout_first_row_source_image",
                    selection_reason="fraction retained in source callout row",
                ),
                PageBlock("body", "editable_paragraph", (100, 200, 800, 300), 0, 1, text="普通解析正文保持可编辑。"),
            ],
        )

        report = editable_quality_report([model])

        self.assertEqual(report["summary"]["formula_fallback_pages"], [21])
        fallback = report["pages"][0]["image_fallback_blocks"][0]
        self.assertEqual(fallback["fallback_mode"], "callout_first_row_source_image")
        self.assertEqual(fallback["bbox"], [100, 100, 800, 170])

    def test_short_formula_fragment_cannot_delete_complete_question_paragraph(self) -> None:
        model = PageModel(
            schema_version=7,
            page_index=6,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
            blocks=[
                PageBlock(
                    "question",
                    "editable_paragraph",
                    (100, 100, 900, 210),
                    0,
                    0,
                    confidence=0.98,
                    text="1.（2018年广东省考）这是完整题干，必须保留。\n1-5",
                ),
                PageBlock("fraction", "editable_paragraph", (110, 160, 150, 210), 0, 1, confidence=0.999, text="1-5"),
            ],
        )

        resolve_page_model_conflicts(model)

        self.assertEqual({block.block_id for block in model.blocks}, {"question", "fraction"})

    def test_small_callout_crop_cannot_delete_large_editable_body_paragraph(self) -> None:
        model = PageModel(
            schema_version=7,
            page_index=8,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
            blocks=[
                PageBlock(
                    "body",
                    "editable_callout_body",
                    (100, 100, 900, 300),
                    0,
                    0,
                    confidence=0.99,
                    text="这是跨越多行的大段解析正文，左上角的标签截图不能删除整段内容。",
                ),
                PageBlock(
                    "tag",
                    "talk_callout_tag_image",
                    (100, 100, 240, 145),
                    1,
                    1,
                    asset_path="tag.png",
                    fallback_mode="callout_prefix_source_image",
                ),
            ],
        )

        resolve_page_model_conflicts(model)

        self.assertEqual({block.block_id for block in model.blocks}, {"body", "tag"})
        self.assertFalse(any(item["type"] == "image_text_conflict" for item in editable_quality_report([model])["pages"][0]["static_findings"]))

    def test_inline_callout_label_is_not_reported_as_abnormal_overlap(self) -> None:
        model = PageModel(
            schema_version=8,
            page_index=8,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
            blocks=[
                PageBlock(
                    "body",
                    "editable_callout_body",
                    (100, 100, 900, 300),
                    0,
                    0,
                    confidence=0.99,
                    text="这是行内标签后面的可编辑解析正文。",
                ),
                PageBlock(
                    "label",
                    "talk_label_image",
                    (100, 100, 235, 150),
                    1,
                    1,
                    text="解析",
                    asset_path="label.png",
                    fallback_mode="talk_label_source_image",
                    style={"inline_decorative": True, "inline_host_block_id": "body"},
                ),
            ],
            source_image_width_px=2480,
            source_image_height_px=3508,
        )

        findings = editable_quality_report([model])["pages"][0]["static_findings"]

        self.assertEqual(findings, [])
