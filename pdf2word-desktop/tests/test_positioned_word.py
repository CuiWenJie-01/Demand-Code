from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from pdf2word_engine.models import PageBlock, PageModel, PageSize, PdfKind
from pdf2word_engine.word import create_positioned_editable_docx


class PositionedEditableWordTests(unittest.TestCase):
    def test_positioned_text_and_fallback_image_are_written_to_docx(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = root / "regions" / "chart.png"
            asset.parent.mkdir()
            Image.new("RGB", (80, 40), color="navy").save(asset)
            model = PageModel(
                schema_version=1,
                page_index=0,
                size=PageSize(595, 842),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1190,
                source_image_height_px=1684,
                blocks=[
                    PageBlock("text-1", "text", (100, 120, 900, 180), 1, 1, text="可编辑中文内容"),
                    PageBlock("image-1", "paragraph_title", (120, 300, 500, 520), 2, 2, text="图片回退", asset_path=str(asset)),
                ],
            )
            output = create_positioned_editable_docx([model], root / "editable.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
                names = archive.namelist()

        self.assertIn("w:txbxContent", document_xml)
        self.assertIn("可编辑中文内容", document_xml)
        self.assertIn("w:color", document_xml)
        self.assertIn("v:imagedata", document_xml)
        self.assertTrue(any(name.startswith("word/media/") for name in names))

    def test_page_model_round_trip_preserves_coordinate_space(self) -> None:
        original = PageModel(
            schema_version=1,
            page_index=2,
            size=PageSize(595, 842),
            source_type=PdfKind.SCANNED,
            source_image_width_px=1190,
            source_image_height_px=1684,
            blocks=[PageBlock("text-1", "text", (1, 2, 3, 4), 0, 0, text="内容")],
        )

        restored = PageModel.from_dict(original.to_dict())

        self.assertEqual(restored.source_image_width_px, 1190)
        self.assertEqual(restored.source_image_height_px, 1684)
        self.assertEqual(restored.blocks[0].text, "内容")

    def test_semantic_prefix_is_written_as_pink_and_black_editable_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=1,
                page_index=0,
                size=PageSize(595, 842),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1190,
                source_image_height_px=1684,
                blocks=[
                    PageBlock(
                        "question",
                        "text_line",
                        (100, 120, 900, 160),
                        0,
                        0,
                        text="7.（2018年国考）题干",
                        style={
                            "semantic_role": "question_heading",
                            "font_size_pt": 8.0,
                            "accent_length": len("7.（2018年国考）"),
                            "bold_prefix_length": 2,
                            "justify_to_bbox": True,
                        },
                    ),
                    PageBlock(
                        "answer",
                        "text_line",
                        (100, 200, 300, 240),
                        1,
                        1,
                        text="答案A",
                        style={"semantic_role": "talk_答案", "accent_length": 2},
                    ),
                ],
            )
            output = create_positioned_editable_docx([model], root / "semantic.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertGreaterEqual(document_xml.count('w:color w:val="EF168B"'), 2)
        self.assertIn('<w:b/><w:color w:val="EF168B"', document_xml)
        self.assertIn('<w:b w:val="0"/><w:color w:val="EF168B"', document_xml)
        self.assertIn('<w:sz w:val="16"/>', document_xml)
        self.assertIn('<w:jc w:val="left"/>', document_xml)
        self.assertIn("<w:t xml:space=\"preserve\">答案</w:t>", document_xml)
        self.assertIn("<w:t xml:space=\"preserve\">A</w:t>", document_xml)

    def test_sidebar_is_written_as_editable_glyphs_and_vector_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=1,
                page_index=0,
                size=PageSize(595, 842),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1032,
                source_image_height_px=1458,
                blocks=[
                    PageBlock(
                        "sidebar",
                        "sidebar_vertical_text",
                        (996, 1219, 1017, 1349),
                        0,
                        0,
                        text="第一章解题方法",
                        style={"font_size_pt": 8.5, "font_color": "555555"},
                    ),
                    PageBlock("page", "sidebar_page_number", (979, 1387, 1016, 1403), 1, 1, text="005"),
                    PageBlock("rule", "sidebar_accent_rule", (1021, 1384, 1024, 1409), 2, 2, style={"fill_color": "EF168B"}),
                ],
            )
            output = create_positioned_editable_docx([model], root / "sidebar.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("第", document_xml)
        self.assertIn("一", document_xml)
        self.assertIn("解", document_xml)
        self.assertIn("005", document_xml)
        self.assertIn("pdf2word_sidebar_rule_rule", document_xml)
        self.assertIn('fillcolor="#EF168B"', document_xml)

    def test_short_answer_is_left_aligned_even_when_legacy_style_requests_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=5,
                page_index=0,
                size=PageSize(595, 842),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1190,
                source_image_height_px=1684,
                blocks=[PageBlock("short", "text_line", (100, 100, 400, 130), 0, 0, text="答案C", style={"justify_to_bbox": True, "semantic_role": "callout_answer"})],
            )
            output = create_positioned_editable_docx([model], root / "short.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn('<w:jc w:val="left"/>', document_xml)
        self.assertNotIn('<w:jc w:val="distribute"/>', document_xml)
