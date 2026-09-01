from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from pdf2word_engine.models import PAGE_MODEL_SCHEMA_VERSION, JobState, PageSize, PdfKind, RenderedPage
from pdf2word_engine.pipeline import _create_ocr_page_models, convert_pdf, parse_page_range, required_workspace_bytes
from pdf2word_engine.job_store import JobWorkspace
from pdf2word_engine.preflight import PreflightReport

from .helpers import create_text_pdf


class PipelineTests(unittest.TestCase):
    def test_parse_page_range(self) -> None:
        self.assertEqual(parse_page_range("1,3-4", 4), [0, 2, 3])
        with self.assertRaises(ValueError):
            parse_page_range("5", 4)

    def test_workspace_reservation_has_safe_minimum(self) -> None:
        self.assertEqual(required_workspace_bytes(1024), 3 * 1024**3)
        self.assertEqual(required_workspace_bytes(1024**3), 8 * 1024**3)

    def test_editable_conversion_works_for_text_layer_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = create_text_pdf(root / "source.pdf")
            result = convert_pdf(
                source,
                output_dir=root / "output",
                workspace_root=root / "workspace",
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

    def test_stale_page_model_rebuilds_from_raw_checkpoint_without_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = JobWorkspace.create(root)
            page_dir = workspace.page_dir(0)
            image_path = page_dir / "render.png"
            Image.new("RGB", (100, 120), color="white").save(image_path)
            (page_dir / "paddle-raw.json").write_text(
                '{"res":{"parsing_res_list":[{"block_id":"body","block_label":"text","block_bbox":[0,0,100,100],"block_content":"旧段落"}],"overall_ocr_res":{"rec_texts":["新行"],"rec_boxes":[[1,10,90,25]]}}}',
                encoding="utf-8",
            )
            (page_dir / "page-model.json").write_text(
                '{"schema_version":1,"page_index":0,"size":{"width_pt":50,"height_pt":60},"source_type":"outlined","blocks":[]}',
                encoding="utf-8",
            )
            report = PreflightReport("source.pdf", 1, 1, None, False, None, None, kind=PdfKind.OUTLINED, page_sizes=[PageSize(50, 60)])
            rendered = RenderedPage(0, image_path, PageSize(50, 60))
            with patch("pdf2word_engine.pipeline._render_pages_for_ocr", return_value=[rendered]), patch(
                "pdf2word_engine.pipeline.create_paddle_pipeline"
            ) as create_pipeline:
                models = _create_ocr_page_models(
                    root / "source.pdf", workspace=workspace, page_indices=[0], dpi=96, report=report, callback=None
                )

        self.assertEqual(models[0].schema_version, PAGE_MODEL_SCHEMA_VERSION)
        self.assertEqual(models[0].blocks[0].block_type, "text_line")
        self.assertEqual(models[0].blocks[0].text, "新行")
        create_pipeline.assert_not_called()
