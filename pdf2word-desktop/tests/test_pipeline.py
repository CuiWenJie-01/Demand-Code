from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdf2word_engine.cli import _build_parser
from pdf2word_engine.job_store import JobWorkspace
from pdf2word_engine.pipeline import (
    DEFAULT_CURRENT_OUTPUT_DIR,
    DEFAULT_CURRENT_WORKSPACE_DIR,
    create_current_source_first_pilot,
    parse_page_range,
    required_workspace_bytes,
)


class PipelineTests(unittest.TestCase):
    def test_parse_page_range(self) -> None:
        self.assertEqual(parse_page_range("1,3-4", 4), [0, 2, 3])
        with self.assertRaises(ValueError):
            parse_page_range("5", 4)

    def test_workspace_reservation_has_safe_minimum(self) -> None:
        self.assertEqual(required_workspace_bytes(1024), 3 * 1024**3)
        self.assertEqual(required_workspace_bytes(1024**3), 8 * 1024**3)

    def test_source_first_cli_defaults_to_single_current_candidate(self) -> None:
        args = _build_parser().parse_args(["source-first-pilot", "source.pdf"])
        self.assertEqual(args.output_dir, DEFAULT_CURRENT_OUTPUT_DIR)
        self.assertEqual(args.workspace_dir, DEFAULT_CURRENT_WORKSPACE_DIR)

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

    def test_current_candidate_replaces_previous_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current_output = root / "outputs" / "current"
            current_workspace = root / "runtime" / "current"
            current_output.mkdir(parents=True)
            current_workspace.mkdir(parents=True)
            (current_output / "old.docx").write_bytes(b"old")
            (current_workspace / "old-page-model.json").write_text("{}", encoding="utf-8")

            def build_candidate(source_pdf: str | Path, **kwargs: object) -> tuple[Path, Path, Path]:
                staging_output = Path(kwargs["output_dir"])
                staging_workspace = Path(kwargs["workspace_dir"])
                staging_output.mkdir(parents=True)
                staging_workspace.mkdir(parents=True)
                docx = staging_output / "candidate.docx"
                report = staging_output / "report.json"
                manifest = staging_workspace / "manifest.json"
                docx.write_bytes(b"new")
                report.write_text(
                    json.dumps({"docx": str(docx), "workspace": str(staging_workspace)}),
                    encoding="utf-8",
                )
                manifest.write_text(
                    json.dumps({"docx": str(docx), "report": str(report)}),
                    encoding="utf-8",
                )
                return docx, report, manifest

            with patch("pdf2word_engine.pipeline.create_source_first_pilot", side_effect=build_candidate):
                docx, report, manifest = create_current_source_first_pilot(
                    root / "source.pdf",
                    output_dir=current_output,
                    workspace_dir=current_workspace,
                )

            self.assertEqual(docx, current_output.resolve() / "candidate.docx")
            self.assertEqual(report, current_output.resolve() / "report.json")
            self.assertEqual(manifest, current_workspace.resolve() / "manifest.json")
            self.assertEqual(docx.read_bytes(), b"new")
            self.assertFalse((current_output / "old.docx").exists())
            self.assertFalse((current_workspace / "old-page-model.json").exists())
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["docx"], str(docx))
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["report"], str(report))
            self.assertEqual(list((root / "outputs").glob(".*.pending-*")), [])
            self.assertEqual(list((root / "runtime").glob(".*.pending-*")), [])
            self.assertEqual(list((root / "outputs").glob(".*.previous-*")), [])
            self.assertEqual(list((root / "runtime").glob(".*.previous-*")), [])

    def test_failed_candidate_is_cleaned_and_previous_current_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current_output = root / "outputs" / "current"
            current_workspace = root / "runtime" / "current"
            current_output.mkdir(parents=True)
            current_workspace.mkdir(parents=True)
            (current_output / "accepted.docx").write_bytes(b"accepted")
            (current_workspace / "accepted.json").write_text("{}", encoding="utf-8")

            def fail_candidate(source_pdf: str | Path, **kwargs: object) -> tuple[Path, Path, Path]:
                staging_output = Path(kwargs["output_dir"])
                staging_workspace = Path(kwargs["workspace_dir"])
                staging_output.mkdir(parents=True)
                staging_workspace.mkdir(parents=True)
                (staging_output / "partial.docx").write_bytes(b"partial")
                (staging_workspace / "partial.json").write_text("{}", encoding="utf-8")
                raise RuntimeError("simulated OCR failure")

            with patch("pdf2word_engine.pipeline.create_source_first_pilot", side_effect=fail_candidate):
                with self.assertRaisesRegex(RuntimeError, "simulated OCR failure"):
                    create_current_source_first_pilot(
                        root / "source.pdf",
                        output_dir=current_output,
                        workspace_dir=current_workspace,
                    )

            self.assertEqual((current_output / "accepted.docx").read_bytes(), b"accepted")
            self.assertTrue((current_workspace / "accepted.json").exists())
            self.assertEqual(list((root / "outputs").glob(".*.pending-*")), [])
            self.assertEqual(list((root / "runtime").glob(".*.pending-*")), [])

    def test_open_office_candidate_fails_before_starting_fresh_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current_output = root / "outputs" / "current"
            current_workspace = root / "runtime" / "current"
            current_output.mkdir(parents=True)
            current_workspace.mkdir(parents=True)
            (current_output / "~$candidate.docx").write_bytes(b"lock")

            with patch("pdf2word_engine.pipeline.create_source_first_pilot") as create_pilot:
                with self.assertRaisesRegex(PermissionError, "Word/WPS"):
                    create_current_source_first_pilot(
                        root / "source.pdf",
                        output_dir=current_output,
                        workspace_dir=current_workspace,
                    )

            create_pilot.assert_not_called()
