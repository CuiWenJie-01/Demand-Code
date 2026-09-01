from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas

from pdf2word_engine.models import PageBlock, PageModel, PageSize, PdfKind
from pdf2word_engine.regression import (
    VisualRegressionError,
    assert_positioned_model_contract,
    assert_rendered_page_count,
    inspect_positioned_shapes,
    verify_golden_page,
)
from pdf2word_engine.word import create_positioned_editable_docx
from pdf2word_engine.word_render import render_docx_with_microsoft_word


def _golden_question_model() -> PageModel:
    return PageModel(
        schema_version=4,
        page_index=9,
        size=PageSize(516, 729),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1032,
        source_image_height_px=1458,
        blocks=[
            PageBlock(
                "question",
                "text_line",
                (168, 157, 951, 178),
                1,
                1,
                text="7.（2018年国考）题干",
                style={
                    "semantic_role": "question_heading",
                    "accent_length": 11,
                    "bold_prefix_length": 2,
                    "justify_to_bbox": True,
                },
            ),
            PageBlock(
                "body",
                "text_line",
                (130, 193, 951, 214),
                2,
                2,
                text="题干正文右边界对齐",
                style={"semantic_role": "question_body", "justify_to_bbox": True},
            ),
            PageBlock(
                "answer-tag",
                "talk_callout_tag_image",
                (166, 581, 262, 615),
                3,
                3,
            ),
            PageBlock(
                "answer",
                "text_line",
                (274, 593, 291, 615),
                4,
                4,
                text="A",
                style={"semantic_role": "callout_answer"},
            ),
            PageBlock(
                "analysis",
                "text_line",
                (275, 643, 951, 662),
                5,
                5,
                text="解析正文右边界对齐",
                style={"semantic_role": "callout_body", "justify_to_bbox": True},
            ),
            PageBlock(
                "sidebar",
                "sidebar_vertical_text",
                (996, 1219, 1017, 1349),
                6,
                6,
                text="第一章解题方法",
                style={"semantic_role": "sidebar_vertical_text", "font_size_pt": 8.5},
            ),
            PageBlock(
                "page",
                "sidebar_page_number",
                (979, 1385, 1036, 1408),
                7,
                7,
                text="005",
                style={"semantic_role": "sidebar_page_number", "font_size_pt": 8.5},
            ),
            PageBlock(
                "rule",
                "sidebar_accent_rule",
                (1021, 1384, 1024, 1409),
                8,
                8,
                style={"semantic_role": "sidebar_accent_rule", "fill_color": "EF168B"},
            ),
        ],
    )


class GoldenPageRegressionTests(unittest.TestCase):
    def test_model_contract_checks_editability_and_key_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            docx = create_positioned_editable_docx([_golden_question_model()], Path(temp) / "golden.docx")
            checked = assert_positioned_model_contract(docx, _golden_question_model())
            shapes = inspect_positioned_shapes(docx)

        self.assertGreaterEqual(checked, 13)  # 7 sidebar glyphs + 6 key blocks/rule
        self.assertTrue(any(shape.shape_id == "pdf2word_text_answer" and shape.text == "A" for shape in shapes))
        self.assertTrue(any(shape.shape_id == "pdf2word_sidebar_rule_rule" for shape in shapes))

    def test_page_count_gate_rejects_unexpected_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "two-pages.pdf"
            document = canvas.Canvas(str(pdf))
            document.drawString(72, 720, "one")
            document.showPage()
            document.drawString(72, 720, "two")
            document.save()
            with self.assertRaisesRegex(VisualRegressionError, "分页回归失败"):
                assert_rendered_page_count(pdf, 1)

    def test_complete_gate_runs_structure_then_renderer_page_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = _golden_question_model()
            docx = create_positioned_editable_docx([model], root / "golden.docx")
            pdf = root / "golden.pdf"
            document = canvas.Canvas(str(pdf))
            document.drawString(72, 720, "one")
            document.save()
            with patch("pdf2word_engine.regression.render_docx_to_pdf", return_value=pdf):
                report = verify_golden_page(docx, model)

        self.assertEqual(report.rendered_page_count, 1)
        self.assertGreater(report.editable_text_boxes, 0)

    def test_word_renderer_reports_missing_source_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(VisualRegressionError, "Microsoft Word"):
                render_docx_with_microsoft_word(Path(temp) / "missing.docx", Path(temp) / "word.pdf")
