from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

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
