from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pdf2word_engine.models import PdfKind
from pdf2word_engine.preflight import inspect_pdf

from .helpers import create_text_pdf


class PreflightTests(unittest.TestCase):
    def test_detects_born_digital_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = create_text_pdf(Path(temp) / "source.pdf")
            report = inspect_pdf(source)

        self.assertEqual(report.page_count, 2)
        self.assertEqual(report.kind, PdfKind.BORN_DIGITAL)
        self.assertGreater(report.font_resource_pages, 0)
        self.assertGreater(report.sample_text_characters, 20)
