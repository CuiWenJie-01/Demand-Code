from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas

from pdf2word_engine.representative import (
    RepresentativeManifest,
    RepresentativePage,
    cer_review_catalog,
    load_representative_manifest,
    prepare_cer_review_page,
    run_representative_regressions,
    run_representative_word_regressions,
    save_cer_review_page,
    validate_representative_manifest,
    write_cer_review_pages,
    write_cer_templates,
)
from pdf2word_engine.representative import _load_cer_annotation
from pdf2word_engine.regression import VisualRegressionError


class RepresentativePageTests(unittest.TestCase):
    def test_checked_in_manifest_has_required_coverage_and_page10_golden(self) -> None:
        manifest = load_representative_manifest(Path(__file__).parent / "fixtures" / "representative_pages.json")

        self.assertEqual(len(manifest.pages), 12)
        golden_pages = [page for page in manifest.pages if page.golden]
        self.assertEqual([page.page_number for page in golden_pages], [10, 40, 300])
        for page in golden_pages:
            self.assertTrue(page.model_path and page.model_path.is_file())
            self.assertTrue(page.docx_path and page.docx_path.is_file())

    def test_manifest_rejects_missing_required_coverage(self) -> None:
        manifest = RepresentativeManifest(
            1,
            12,
            tuple(RepresentativePage(number, ("exam_question",), "test") for number in range(1, 13)),
        )
        with self.assertRaisesRegex(VisualRegressionError, "缺少必需覆盖"):
            validate_representative_manifest(manifest)

    def test_run_covers_all_selected_pages_without_pending_baselines(self) -> None:
        manifest = load_representative_manifest(Path(__file__).parent / "fixtures" / "representative_pages.json")
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "page10.pdf"
            document = canvas.Canvas(str(pdf))
            document.drawString(72, 720, "one page")
            document.save()
            with patch("pdf2word_engine.representative.verify_golden_page") as verify:
                verify.return_value = object()
                report = run_representative_regressions(manifest)

        self.assertEqual(report.passed, (1, 10, 40, 80, 120, 160, 200, 240, 300, 330, 360, 381))
        self.assertEqual(report.pending, ())

    def test_strict_run_accepts_complete_baselines(self) -> None:
        manifest = load_representative_manifest(Path(__file__).parent / "fixtures" / "representative_pages.json")
        with patch("pdf2word_engine.representative.verify_golden_page"):
            report = run_representative_regressions(manifest, strict=True)
        self.assertEqual(report.pending, ())

    def test_cer_templates_are_unconfirmed_page_review_drafts(self) -> None:
        manifest = load_representative_manifest(Path(__file__).parent / "fixtures" / "representative_pages.json")
        with tempfile.TemporaryDirectory() as temp:
            templates = write_cer_templates(manifest, temp)
            payload = json.loads((Path(temp) / "page-0010.json").read_text(encoding="utf-8"))
            cover_payload = json.loads((Path(temp) / "page-0001.json").read_text(encoding="utf-8"))
        self.assertEqual(len(templates), 12)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["workflow"], "page_review")
        self.assertFalse(payload["page_confirmed"])
        self.assertTrue(payload["segments"])
        self.assertTrue(all(segment["reference_text"] == "" for segment in payload["segments"]))
        self.assertTrue(all("production_ocr_text" in segment for segment in payload["segments"]))
        self.assertTrue(cover_payload["exclude_from_cer"])

    def test_cer_review_renders_one_html_page_with_source_image_and_flags(self) -> None:
        manifest = load_representative_manifest(Path(__file__).parent / "fixtures" / "representative_pages.json")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.pdf"
            document = canvas.Canvas(str(source))
            for _ in range(381):
                document.drawString(72, 720, "source")
                document.showPage()
            document.save()
            output = Path(temp) / "review"
            pages = write_cer_review_pages(manifest, output, source_pdf=source)
            html = (output / "page-0010.html").read_text(encoding="utf-8")
            self.assertTrue((output / "source-pages" / "page-0010.png").is_file())
        self.assertEqual(len(pages), 12)
        self.assertIn("确认整页并下载标注", html)
        self.assertIn("source-pages/page-0010.png", html)

    def test_cer_gate_rejects_unconfirmed_page_review_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            annotation = Path(temp) / "page.json"
            annotation.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "workflow": "page_review",
                        "page_confirmed": False,
                        "segments": [{"block_id": "line-1", "reference_text": "人工确认"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VisualRegressionError, "尚未确认"):
                _load_cer_annotation(annotation)

    def test_desktop_review_payload_renders_one_page_and_save_is_confirmed(self) -> None:
        model_path = Path(__file__).parent.parent / "runtime" / "qa-page10-final-one-page" / "page-model-源PDF对照修复-v3.json"
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            source = temp_path / "source.pdf"
            document = canvas.Canvas(str(source))
            document.drawString(72, 720, "source")
            document.save()
            annotation = temp_path / "cer_annotations" / "page-0001.json"
            manifest = RepresentativeManifest(
                1,
                1,
                (
                    RepresentativePage(
                        1,
                        ("cover",),
                        "desktop test",
                        model_path=model_path,
                        cer_annotation_path=annotation,
                    ),
                ),
            )
            prepared = prepare_cer_review_page(manifest, page_number=1, source_pdf=source)
            self.assertTrue(str(prepared["source_image_data_url"]).startswith("data:image/png;base64,"))
            review = prepared["review"]
            self.assertIsInstance(review, dict)
            segments = review["segments"]
            self.assertIsInstance(segments, list)
            saved = save_cer_review_page(manifest, page_number=1, segments=segments)
            payload = json.loads(saved.read_text(encoding="utf-8"))
            catalog = cer_review_catalog(manifest, temp_path / "manifest.json")

        self.assertTrue(payload["page_confirmed"])
        self.assertTrue(all("production_ocr_text" not in segment for segment in payload["segments"]))
        self.assertEqual(catalog["completed_page_count"], 1)

    def test_word_batch_covers_all_representative_pages(self) -> None:
        manifest = load_representative_manifest(Path(__file__).parent / "fixtures" / "representative_pages.json")
        with tempfile.TemporaryDirectory() as temp:
            with patch("pdf2word_engine.representative.verify_with_microsoft_word", return_value=1):
                reports = run_representative_word_regressions(manifest, temp)
        self.assertEqual([report.page_number for report in reports], [1, 10, 40, 80, 120, 160, 200, 240, 300, 330, 360, 381])
        self.assertTrue(all(report.rendered_page_count == 1 for report in reports))
