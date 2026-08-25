from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from pdf2word_engine.models import ConversionMode, JobState
from pdf2word_engine.pipeline import convert_pdf, parse_page_range, required_workspace_bytes
from pdf2word_engine.job_store import JobWorkspace

from .helpers import create_text_pdf


class PipelineTests(unittest.TestCase):
    def test_parse_page_range(self) -> None:
        self.assertEqual(parse_page_range("1,3-4", 4), [0, 2, 3])
        with self.assertRaises(ValueError):
            parse_page_range("5", 4)

    def test_workspace_reservation_has_safe_minimum(self) -> None:
        self.assertEqual(required_workspace_bytes(1024), 3 * 1024**3)
        self.assertEqual(required_workspace_bytes(1024**3), 8 * 1024**3)

    def test_visual_conversion_creates_openxml_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = create_text_pdf(root / "source.pdf")
            result = convert_pdf(
                source,
                output_dir=root / "output",
                workspace_root=root / "workspace",
                mode=ConversionMode.VISUAL,
                dpi=96,
            )
            output = result.outputs[0]
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()

        self.assertEqual(result.state, JobState.COMPLETED)
        self.assertTrue(output.name.endswith("保真版.docx"))
        self.assertIn("word/document.xml", names)
        self.assertTrue(any(name.startswith("word/media/") for name in names))

    def test_editable_conversion_works_for_text_layer_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = create_text_pdf(root / "source.pdf")
            result = convert_pdf(
                source,
                output_dir=root / "output",
                workspace_root=root / "workspace",
                mode=ConversionMode.EDITABLE,
                dpi=96,
            )

        self.assertEqual(result.state, JobState.COMPLETED)
        self.assertEqual(len(result.outputs), 1)
        self.assertTrue(result.outputs[0].name.endswith("可编辑版.docx"))

    def test_workspace_can_be_reopened_for_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = JobWorkspace.create(root)
            reopened = JobWorkspace.open(root, workspace.job_id)

        self.assertEqual(reopened.job_id, workspace.job_id)
        self.assertEqual(reopened.path, workspace.path)

    def test_opening_missing_workspace_does_not_create_a_job_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(FileNotFoundError):
                JobWorkspace.open(root, "missing-job")
            self.assertFalse((root / "jobs" / "missing-job").exists())
