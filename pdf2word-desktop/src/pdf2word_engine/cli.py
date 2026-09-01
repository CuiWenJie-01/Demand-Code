"""Command-line entry point for source-first conversion development and QA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .document_checks import (
    assert_rendered_page_count,
    assert_source_first_docx_contract,
    render_docx_to_pdf,
)
from .errors import Pdf2WordError
from .execution import resolve_ocr_execution_profile
from .models import PageModel, PageSize, PdfKind
from .ocr import FocusedOcrPipelineCache, create_paddle_pipeline, predict_page_model, write_page_model
from .pipeline import (
    DEFAULT_CURRENT_OUTPUT_DIR,
    DEFAULT_CURRENT_WORKSPACE_DIR,
    create_current_source_first_pilot,
)
from .preflight import inspect_pdf
from .word import create_positioned_editable_docx
from .word_render import verify_with_microsoft_word


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdf2word-engine", description="PDF2Word Desktop source-first engine")
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight", help="只读检查 PDF 结构并选择处理路线")
    preflight.add_argument("source", type=Path)
    preflight.add_argument("--json", action="store_true", dest="as_json")

    source_pilot = commands.add_parser(
        "source-first-pilot",
        help="从源 PDF 全新渲染并生成第 7、8、9、10、21、23 页可编辑混合样本",
    )
    source_pilot.add_argument("source", type=Path)
    source_pilot.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_CURRENT_OUTPUT_DIR,
        help="当前候选输出目录；新任务成功后替换旧候选",
    )
    source_pilot.add_argument(
        "--workspace-dir",
        type=Path,
        default=DEFAULT_CURRENT_WORKSPACE_DIR,
        help="当前候选工作区；失败任务自动清理，新任务成功后替换旧工作区",
    )
    source_pilot.add_argument("--dpi", type=int, default=300)
    source_pilot.add_argument("--ocr-device", choices=["auto", "cpu", "gpu"], default="auto")
    source_pilot.add_argument("--cpu-threads", type=int)

    ocr_page = commands.add_parser("ocr-page", help="对单张新渲染页识别并写出 PageModel JSON")
    ocr_page.add_argument("image", type=Path)
    ocr_page.add_argument("--page-index", type=int, required=True)
    ocr_page.add_argument("--width-pt", type=float, required=True)
    ocr_page.add_argument("--height-pt", type=float, required=True)
    ocr_page.add_argument("--source-type", choices=[kind.value for kind in PdfKind], default=PdfKind.SCANNED.value)
    ocr_page.add_argument("--output", type=Path, required=True)
    ocr_page.add_argument("--raw-output", type=Path, help="保存 Paddle 原始 JSON，仅用于当前运行调试")
    ocr_page.add_argument("--native-word-output-dir", type=Path, help="保存 Paddle 原生 Word，仅用于引擎对照")
    ocr_page.add_argument("--regions-dir", type=Path, help="保存公式、图表和不可靠区域的源图回退素材")
    ocr_page.add_argument("--ocr-device", choices=["auto", "cpu", "gpu"], default="auto")
    ocr_page.add_argument("--cpu-threads", type=int)

    render_models = commands.add_parser("render-page-model", help="把当前运行的 PageModel JSON 重建为可编辑 DOCX")
    render_models.add_argument("models", type=Path, nargs="+", help="PageModel JSON 文件")
    render_models.add_argument("--output", type=Path, required=True)

    docx_check = commands.add_parser("docx-check", help="检查 DOCX 可编辑结构，并可选执行 LibreOffice 页数门禁")
    docx_check.add_argument("docx", type=Path)
    docx_check.add_argument("--minimum-editable-characters", type=int, default=1)
    docx_check.add_argument("--render-output-dir", type=Path)
    docx_check.add_argument("--expected-pages", type=int)
    docx_check.add_argument("--renderer", help="soffice/libreoffice 可执行文件路径")

    word_check = commands.add_parser("word-render-check", help="使用 Microsoft Word 实机打开、导出并验证当前 DOCX")
    word_check.add_argument("docx", type=Path)
    word_check.add_argument("--output-pdf", type=Path, required=True)
    word_check.add_argument("--expected-pages", type=int, required=True)
    word_check.add_argument("--minimum-editable-characters", type=int, default=1)
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
        if args.command == "source-first-pilot":
            docx, quality_report, manifest = create_current_source_first_pilot(
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
        if args.command == "docx-check":
            structure = assert_source_first_docx_contract(
                args.docx,
                minimum_editable_characters=args.minimum_editable_characters,
            )
            payload = structure.to_dict()
            if args.render_output_dir or args.expected_pages is not None:
                if args.render_output_dir is None or args.expected_pages is None:
                    raise ValueError("执行渲染门禁时必须同时提供 --render-output-dir 与 --expected-pages。")
                rendered = render_docx_to_pdf(args.docx, args.render_output_dir, renderer=args.renderer)
                payload["rendered_pdf"] = str(rendered)
                payload["rendered_page_count"] = assert_rendered_page_count(rendered, args.expected_pages)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        pages = verify_with_microsoft_word(
            args.docx,
            args.output_pdf,
            expected_page_count=args.expected_pages,
            minimum_editable_characters=args.minimum_editable_characters,
        )
        print(json.dumps({"docx": str(args.docx), "pdf": str(args.output_pdf), "pages": pages}, ensure_ascii=False))
        return 0
    except (Pdf2WordError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
