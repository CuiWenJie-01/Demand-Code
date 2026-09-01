"""Command-line entry point useful for M0/M1 validation and automated tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .errors import Pdf2WordError
from .execution import resolve_ocr_execution_profile
from .models import PageModel, PageSize, PdfKind
from .ocr import FocusedOcrPipelineCache, create_paddle_pipeline, predict_page_model, write_page_model
from .pipeline import convert_pdf, create_source_first_pilot, rebuild_cached_page_models
from .preflight import inspect_pdf
from .regression import verify_golden_page
from .representative import (
    load_representative_manifest,
    run_representative_quality_gates,
    run_representative_regressions,
    run_representative_word_regressions,
    write_cer_review_pages,
    write_cer_templates,
)
from .word import create_positioned_editable_docx
from .word_render import verify_with_microsoft_word


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdf2word-engine", description="PDF2Word Desktop conversion engine")
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", help="只读检查 PDF 结构并选择处理路线")
    preflight.add_argument("source", type=Path)
    preflight.add_argument("--json", action="store_true", dest="as_json")

    convert = commands.add_parser("convert", help="转换 PDF 到 DOCX")
    convert.add_argument("source", type=Path)
    convert.add_argument("--output-dir", type=Path, required=True)
    convert.add_argument("--workspace-root", type=Path, default=Path(".pdf2word-workspace"))
    convert.add_argument("--dpi", type=int, default=200)
    convert.add_argument("--pages", dest="page_range")
    convert.add_argument("--resume-job", help="恢复同一输入与同一配置的未完成任务")
    convert.add_argument("--ocr-device", choices=["auto", "cpu", "gpu"], default="auto", help="OCR 硬件：默认自动选择")
    convert.add_argument("--cpu-threads", type=int, help="CPU OCR 线程数；默认按设备保守选择")

    rebuild = commands.add_parser("rebuild-cached-job", help="不重跑全页 OCR，重建缓存作业的准确优先 Word")
    rebuild.add_argument("--cached-job", type=Path, required=True, help="包含 pages/ 的已完成作业目录")
    rebuild.add_argument("--source-pdf", type=Path, required=True)
    rebuild.add_argument("--output-dir", type=Path, required=True)

    source_pilot = commands.add_parser("source-first-pilot", help="从源 PDF 全新渲染并生成 1-10、21、23 页准确优先样本")
    source_pilot.add_argument("source", type=Path)
    source_pilot.add_argument("--output-dir", type=Path, required=True)
    source_pilot.add_argument("--workspace-dir", type=Path, required=True, help="必须为空；拒绝读取旧 OCR/PageModel")
    source_pilot.add_argument("--dpi", type=int, default=300)
    source_pilot.add_argument("--ocr-device", choices=["auto", "cpu", "gpu"], default="auto")
    source_pilot.add_argument("--cpu-threads", type=int)

    ocr_page = commands.add_parser("ocr-page", help="对单张渲染页进行 PP-StructureV3 识别并写出 PageModel JSON")
    ocr_page.add_argument("image", type=Path)
    ocr_page.add_argument("--page-index", type=int, required=True)
    ocr_page.add_argument("--width-pt", type=float, required=True)
    ocr_page.add_argument("--height-pt", type=float, required=True)
    ocr_page.add_argument("--source-type", choices=[kind.value for kind in PdfKind], default=PdfKind.SCANNED.value)
    ocr_page.add_argument("--output", type=Path, required=True)
    ocr_page.add_argument("--raw-output", type=Path, help="保存 Paddle 原始 JSON，仅用于适配器调试")
    ocr_page.add_argument("--native-word-output-dir", type=Path, help="保存 Paddle 原生 Word，仅用于 M0 对照")
    ocr_page.add_argument("--regions-dir", type=Path, help="保存图表、公式和图片等不可重建区域的 PNG 回退素材")
    ocr_page.add_argument("--ocr-device", choices=["auto", "cpu", "gpu"], default="auto")
    ocr_page.add_argument("--cpu-threads", type=int)

    render_models = commands.add_parser("render-page-model", help="把一个或多个 PageModel JSON 重建为可编辑 DOCX")
    render_models.add_argument("models", type=Path, nargs="+", help="PageModel JSON 文件")
    render_models.add_argument("--output", type=Path, required=True)

    regression = commands.add_parser("visual-regression", help="验证黄金 PageModel 生成的 DOCX 可编辑性、对齐与分页")
    regression.add_argument("model", type=Path, help="单页黄金 PageModel JSON 文件")
    regression.add_argument("docx", type=Path, help="待验证的定位式可编辑 DOCX")
    regression.add_argument("--renderer", help="Office 兼容渲染器路径；默认自动查找 soffice/libreoffice")
    regression.add_argument("--expected-pages", type=int, default=1, help="DOCX 再渲染后的预期页数")

    representative = commands.add_parser("representative-regression", help="执行固定代表页集的已就绪视觉回归")
    representative.add_argument("manifest", type=Path, help="代表页 JSON 清单")
    representative.add_argument("--renderer", help="Office 兼容渲染器路径；默认自动查找 soffice/libreoffice")
    representative.add_argument("--strict", action="store_true", help="要求每一张代表页都已有 PageModel 与 DOCX 基线")

    quality_gate = commands.add_parser("representative-quality-gate", help="重新生成代表页并执行视觉差异与可选 CER 门禁")
    quality_gate.add_argument("manifest", type=Path, help="代表页 JSON 清单")
    quality_gate.add_argument("--renderer", help="Office 兼容渲染器路径；默认自动查找 soffice/libreoffice")
    quality_gate.add_argument("--require-cer", action="store_true", help="缺少人工转写 CER 标注时直接失败")

    cer_template = commands.add_parser("cer-template", help="为固定代表页生成按页确认的 CER 审校草稿 JSON")
    cer_template.add_argument("manifest", type=Path, help="代表页 JSON 清单")
    cer_template.add_argument("--output-dir", type=Path, required=True, help="CER 标注 JSON 输出目录")

    cer_review = commands.add_parser("cer-review", help="生成原图对照、差异高亮、一次整页确认的 CER 审校 HTML")
    cer_review.add_argument("manifest", type=Path, help="代表页 JSON 清单")
    cer_review.add_argument("--output-dir", type=Path, required=True, help="审校 HTML 和原图输出目录")
    cer_review.add_argument("--source-pdf", type=Path, help="源 PDF；提供后每页显示原图")
    cer_review.add_argument("--independent-ocr", type=Path, help="可选独立 OCR JSON（pages -> page -> block_id -> text）")
    cer_review.add_argument("--dpi", type=int, default=144, help="原图渲染 DPI，默认 144")
    cer_review.add_argument("--low-confidence-threshold", type=float, default=0.90, help="低于该置信度的块高亮")

    word_regression = commands.add_parser("word-render-regression", help="使用安装的 Microsoft Word 导出并验证单页 DOCX")
    word_regression.add_argument("model", type=Path, help="单页 PageModel JSON 文件")
    word_regression.add_argument("docx", type=Path, help="待验证的 DOCX")
    word_regression.add_argument("--output-pdf", type=Path, required=True, help="Microsoft Word 导出的 PDF 路径")
    word_regression.add_argument("--expected-pages", type=int, default=1)

    representative_word = commands.add_parser("representative-word-regression", help="使用 Microsoft Word 执行全部代表页实机分页验证")
    representative_word.add_argument("manifest", type=Path, help="代表页 JSON 清单")
    representative_word.add_argument("--output-dir", type=Path, required=True, help="Microsoft Word PDF 输出目录")
    return parser


def _progress(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            report = inspect_pdf(args.source)
            if args.as_json:
                print(json.dumps(report.to_dict(include_page_sizes=False), ensure_ascii=False, indent=2))
            else:
                print(f"类型: {report.kind.value}")
                print(f"页数: {report.page_count}")
                print(f"大小: {report.file_size_bytes} bytes")
                print(f"字体资源页: {report.font_resource_pages}")
                print(f"XObject 页: {report.xobject_pages}")
                print(f"抽样文字字符: {report.sample_text_characters}")
                for warning in report.warnings:
                    print(f"警告: {warning}")
            return 0
        if args.command == "ocr-page":
            execution_profile = resolve_ocr_execution_profile(args.ocr_device, cpu_threads=args.cpu_threads)
            pipeline = create_paddle_pipeline(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_formula_recognition=False,
                use_chart_recognition=False,
                **execution_profile.paddle_options(),
            )
            model = predict_page_model(
                pipeline,
                args.image,
                page_index=args.page_index,
                size=PageSize(args.width_pt, args.height_pt),
                source_type=PdfKind(args.source_type),
                raw_output_path=args.raw_output,
                native_word_output_dir=args.native_word_output_dir,
                region_directory=args.regions_dir,
                focused_pipeline=FocusedOcrPipelineCache(**execution_profile.focused_paddle_options()),
            )
            output = write_page_model(model, args.output)
            print(json.dumps({"output": str(output), "blocks": len(model.blocks), "warnings": model.warnings}, ensure_ascii=False))
            return 0
        if args.command == "render-page-model":
            models = [PageModel.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in args.models]
            output = create_positioned_editable_docx(models, args.output)
            print(json.dumps({"output": str(output), "pages": len(models)}, ensure_ascii=False))
            return 0
        if args.command == "rebuild-cached-job":
            docx, quality_report, summary = rebuild_cached_page_models(
                cached_job=args.cached_job,
                output_dir=args.output_dir,
                source_pdf=args.source_pdf,
                progress=_progress,
            )
            print(json.dumps({"docx": str(docx), "quality_report": str(quality_report), "summary": str(summary)}, ensure_ascii=False))
            return 0
        if args.command == "source-first-pilot":
            docx, quality_report, manifest = create_source_first_pilot(
                args.source,
                output_dir=args.output_dir,
                workspace_dir=args.workspace_dir,
                dpi=args.dpi,
                ocr_device=args.ocr_device,
                cpu_threads=args.cpu_threads,
                progress=_progress,
            )
            print(json.dumps({"docx": str(docx), "quality_report": str(quality_report), "manifest": str(manifest)}, ensure_ascii=False))
            return 0
        if args.command == "visual-regression":
            model = PageModel.from_dict(json.loads(args.model.read_text(encoding="utf-8")))
            report = verify_golden_page(
                args.docx,
                model,
                expected_page_count=args.expected_pages,
                renderer=args.renderer,
            )
            print(
                json.dumps(
                    {
                        "docx": str(report.docx),
                        "editable_text_boxes": report.editable_text_boxes,
                        "rendered_page_count": report.rendered_page_count,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "representative-regression":
            manifest = load_representative_manifest(args.manifest)
            report = run_representative_regressions(manifest, renderer=args.renderer, strict=args.strict)
            print(
                json.dumps(
                    {
                        "passed_pages": list(report.passed),
                        "pending_pages": list(report.pending),
                        "selected_page_count": len(manifest.pages),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "representative-quality-gate":
            manifest = load_representative_manifest(args.manifest)
            reports = run_representative_quality_gates(
                manifest,
                renderer=args.renderer,
                require_cer=args.require_cer,
            )
            print(
                json.dumps(
                    {
                        "pages": [
                            {
                                "page": report.page_number,
                                "ssim": report.visual_ssim,
                                "mae": report.visual_mae,
                                "cer": None if report.cer is None else report.cer.cer,
                                "cer_reference_characters": None
                                if report.cer is None
                                else report.cer.reference_characters,
                            }
                            for report in reports
                        ],
                        "cer_required": args.require_cer,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "cer-template":
            manifest = load_representative_manifest(args.manifest)
            templates = write_cer_templates(manifest, args.output_dir)
            print(json.dumps({"templates": [str(path) for path in templates]}, ensure_ascii=False))
            return 0
        if args.command == "cer-review":
            manifest = load_representative_manifest(args.manifest)
            pages = write_cer_review_pages(
                manifest,
                args.output_dir,
                source_pdf=args.source_pdf,
                independent_ocr_path=args.independent_ocr,
                dpi=args.dpi,
                low_confidence_threshold=args.low_confidence_threshold,
            )
            print(json.dumps({"review_pages": [str(path) for path in pages]}, ensure_ascii=False))
            return 0
        if args.command == "word-render-regression":
            model = PageModel.from_dict(json.loads(args.model.read_text(encoding="utf-8")))
            pages = verify_with_microsoft_word(
                args.docx,
                model,
                args.output_pdf,
                expected_page_count=args.expected_pages,
            )
            print(json.dumps({"docx": str(args.docx), "pdf": str(args.output_pdf), "pages": pages}, ensure_ascii=False))
            return 0
        if args.command == "representative-word-regression":
            manifest = load_representative_manifest(args.manifest)
            reports = run_representative_word_regressions(manifest, args.output_dir)
            print(
                json.dumps(
                    {
                        "pages": [
                            {"page": report.page_number, "pdf": str(report.pdf_path), "rendered_page_count": report.rendered_page_count}
                            for report in reports
                        ]
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        result = convert_pdf(
            args.source,
            output_dir=args.output_dir,
            workspace_root=args.workspace_root,
            dpi=args.dpi,
            page_range=args.page_range,
            resume_job_id=args.resume_job,
            ocr_device=args.ocr_device,
            cpu_threads=args.cpu_threads,
            progress=_progress,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    except (Pdf2WordError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
