from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pdf2word_engine.job_store import JobWorkspace
from pdf2word_engine.pipeline import parse_page_range, required_workspace_bytes


class PipelineTests(unittest.TestCase):
    def test_parse_page_range(self) -> None:
        self.assertEqual(parse_page_range("1,3-4", 4), [0, 2, 3])
        with self.assertRaises(ValueError):
            parse_page_range("5", 4)

    def test_workspace_reservation_has_safe_minimum(self) -> None:
        self.assertEqual(required_workspace_bytes(1024), 3 * 1024**3)
        self.assertEqual(required_workspace_bytes(1024**3), 8 * 1024**3)

    def test_workspace_can_be_reopened_for_explicit_same_run_recovery(self) -> None:
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
