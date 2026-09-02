from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
import re

from PIL import Image

from pdf2word_engine.models import PageBlock, PageModel, PageSize, PdfKind
from pdf2word_engine.word import create_positioned_editable_docx


class PositionedEditableWordTests(unittest.TestCase):
    def test_image_only_fallback_page_is_written_without_textbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = root / "cover.png"
            Image.new("RGB", (80, 120), color="navy").save(asset)
            model = PageModel(
                schema_version=7,
                page_index=0,
                size=PageSize(595, 842),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1190,
                source_image_height_px=1684,
                page_class="cover",
                reconstruction_mode="full_page_clean_source_fallback",
                blocks=[PageBlock("cover", "full_page_fallback", (0, 0, 1190, 1684), 1, 1, asset_path=str(asset))],
            )
            output = create_positioned_editable_docx([model], root / "cover.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
                names = archive.namelist()

        self.assertNotIn("w:txbxContent", document_xml)
        self.assertIn("v:imagedata", document_xml)
        self.assertTrue(any(name.startswith("word/media/") for name in names))

    def test_page_model_round_trip_preserves_coordinate_space(self) -> None:
        original = PageModel(
            schema_version=7,
            page_index=2,
            size=PageSize(595, 842),
            source_type=PdfKind.SCANNED,
            source_image_width_px=1190,
            source_image_height_px=1684,
            blocks=[PageBlock("paragraph", "editable_paragraph", (1, 2, 3, 4), 0, 0, text="最终内容")],
            evidence_blocks=[PageBlock("raw-1", "text_line", (1, 2, 3, 4), 0, 0, text="原始证据")],
        )

        restored = PageModel.from_dict(original.to_dict())

        self.assertEqual(restored.source_image_width_px, 1190)
        self.assertEqual(restored.source_image_height_px, 1684)
        self.assertEqual(restored.blocks[0].text, "最终内容")
        self.assertEqual(restored.output_blocks[0].text, "最终内容")
        self.assertEqual(restored.evidence_blocks[0].text, "原始证据")

    def test_native_source_paragraph_is_editable_without_vml_textbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=7,
                page_index=0,
                size=PageSize(595, 842),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1190,
                source_image_height_px=1684,
                page_class="ordinary_question",
                reconstruction_mode="native_word_paragraphs_with_clean_source_region_fallbacks",
                blocks=[
                    PageBlock(
                        "paragraph-1",
                        "editable_paragraph",
                        (150, 220, 1040, 310),
                        0,
                        0,
                        text="1.（2018年国考）这一段必须是Word原生可编辑正文。",
                        style={"font_size_pt": 9.6, "line_spacing_pt": 13.0, "accent_length": 12},
                    )
                ],
            )

            output = create_positioned_editable_docx([model], root / "native.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("Word原生可编辑正文", document_xml)
        self.assertNotIn("w:txbxContent", document_xml)
        self.assertIn('w:pStyle w:val="SourceBody"', document_xml)
        self.assertIn("w:framePr", document_xml)

    def test_unresolved_legacy_text_is_rejected(self) -> None:
        model = PageModel(
            schema_version=7,
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
            blocks=[PageBlock("legacy", "text_line", (10, 10, 100, 30), 0, 0, text="旧文本框正文")],
        )
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "拒绝写入旧式 VML"):
                create_positioned_editable_docx([model], Path(temp) / "legacy.docx")

    def test_short_native_fragment_frame_expands_to_prevent_word_wrap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=7,
                page_index=0,
                size=PageSize(500, 700),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1000,
                source_image_height_px=1400,
                page_class="ordinary_question",
                blocks=[
                    PageBlock(
                        "short",
                        "editable_callout_body",
                        (100, 200, 150, 240),
                        0,
                        0,
                        text="代入。",
                        style={"font_size_pt": 10.0, "line_spacing_pt": 12.0, "line_count": 1},
                    )
                ],
            )

            output = create_positioned_editable_docx([model], root / "short.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        width_match = re.search(r'<w:framePr[^>]*w:w="(\d+)"', document_xml)
        self.assertIsNotNone(width_match)
        self.assertGreater(int(width_match.group(1)), 500)

    def test_slash_fractions_are_written_as_editable_stacked_omml(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=8,
                page_index=0,
                size=PageSize(500, 700),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1000,
                source_image_height_px=1400,
                page_class="ordinary_question",
                blocks=[
                    PageBlock(
                        "fraction-body",
                        "editable_paragraph",
                        (100, 200, 900, 320),
                        0,
                        0,
                        text="西区占总人数的2/5，套餐比例为1/(1+3)。",
                        style={"font_size_pt": 10.0, "line_spacing_pt": 14.0, "line_count": 1},
                    )
                ],
            )

            output = create_positioned_editable_docx([model], root / "fractions.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertEqual(document_xml.count("<m:f>"), 2)
        self.assertIn('xml:space="preserve">2</m:t>', document_xml)
        self.assertIn('xml:space="preserve">5</m:t>', document_xml)
        self.assertIn('xml:space="preserve">1+3</m:t>', document_xml)
        self.assertIn('w:hRule="atLeast"', document_xml)

    def test_talk_label_is_inline_with_its_editable_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = root / "talk-analysis.png"
            Image.new("RGBA", (120, 54), color=(239, 22, 139, 255)).save(asset)
            model = PageModel(
                schema_version=8,
                page_index=0,
                size=PageSize(500, 700),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1000,
                source_image_height_px=1400,
                page_class="ordinary_question",
                blocks=[
                    PageBlock(
                        "inline-label",
                        "talk_label_image",
                        (150, 200, 270, 254),
                        0,
                        0,
                        text="解析",
                        style={"inline_decorative": True, "inline_host_block_id": "callout"},
                        asset_path=str(asset),
                        fallback_mode="talk_label_source_image",
                    ),
                    PageBlock(
                        "callout",
                        "editable_callout_body",
                        (100, 190, 900, 330),
                        0,
                        1,
                        text="根据题意，后面的正文必须保持可编辑。",
                        style={
                            "contains_inline_label": True,
                            "first_line_indent_px": 50.0,
                            "font_size_pt": 10.0,
                            "line_spacing_pt": 14.0,
                        },
                    ),
                ],
            )

            output = create_positioned_editable_docx([model], root / "inline-label.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("<wp:inline", document_xml)
        self.assertIn("后面的正文必须保持可编辑", document_xml)
        self.assertNotIn("pdf2word_image_inline-label", document_xml)
        self.assertIn('w:hRule="atLeast"', document_xml)
        frame_width = re.search(r'<w:framePr[^>]*w:w="(\d+)"', document_xml)
        self.assertIsNotNone(frame_width)
        self.assertGreater(int(frame_width.group(1)), 8000)
        self.assertNotIn('w:position w:val="-8"', document_xml)

    def test_answer_blank_uses_a_right_tab_in_its_native_question_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=9,
                page_index=0,
                size=PageSize(500, 700),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1000,
                source_image_height_px=1400,
                page_class="ordinary_question",
                blocks=[
                    PageBlock(
                        "question",
                        "editable_paragraph",
                        (100, 200, 900, 290),
                        0,
                        0,
                        text="题干最后一行\t（　）",
                        style={"font_size_pt": 10.0, "line_spacing_pt": 14.0, "right_tab_stops_px": [790.0]},
                    )
                ],
            )
            output = create_positioned_editable_docx([model], root / "answer-blank.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn('w:val="right"', document_xml)
        self.assertIn("（　）", document_xml)

    def test_source_line_layout_expands_only_full_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = PageModel(
                schema_version=10,
                page_index=0,
                size=PageSize(500, 700),
                source_type=PdfKind.OUTLINED,
                source_image_width_px=1000,
                source_image_height_px=1400,
                blocks=[
                    PageBlock(
                        "analysis",
                        "editable_callout_body",
                        (100, 200, 900, 330),
                        0,
                        0,
                        text="解析正文第一行\n解析正文第二行\n短尾行",
                        style={
                            "font_size_pt": 10.0,
                            "line_spacing_pt": 14.0,
                            "source_line_layout": [
                                {"left_px": 100, "right_px": 900, "justify": True},
                                {"left_px": 100, "right_px": 900, "justify": True},
                                {"left_px": 100, "right_px": 350, "justify": False},
                            ],
                        },
                    )
                ],
            )
            output = create_positioned_editable_docx([model], root / "source-row-layout.docx")
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn('w:spacing w:val="72"', document_xml)
        self.assertEqual(document_xml.count('w:spacing w:val="72"'), 2)
