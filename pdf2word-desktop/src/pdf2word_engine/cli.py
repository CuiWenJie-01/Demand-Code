"""Command-line entry point useful for M0/M1 validation and automated tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .errors import Pdf2WordError
from .models import ConversionMode, PageSize, PdfKind
from .ocr import create_paddle_pipeline, predict_page_model, write_page_model
from .pipeline import convert_pdf
from .preflight import inspect_pdf


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
    convert.add_argument("--mode", choices=[mode.value for mode in ConversionMode], default=ConversionMode.VISUAL.value)
    convert.add_argument("--dpi", type=int, default=200)
    convert.add_argument("--pages", dest="page_range")
    convert.add_argument("--resume-job", help="恢复同一输入与同一配置的未完成任务")

    ocr_page = commands.add_parser("ocr-page", help="对单张渲染页进行 PP-StructureV3 识别并写出 PageModel JSON")
    ocr_page.add_argument("image", type=Path)
    ocr_page.add_argument("--page-index", type=int, required=True)
    ocr_page.add_argument("--width-pt", type=float, required=True)
    ocr_page.add_argument("--height-pt", type=float, required=True)
    ocr_page.add_argument("--source-type", choices=[kind.value for kind in PdfKind], default=PdfKind.SCANNED.value)
    ocr_page.add_argument("--output", type=Path, required=True)
    ocr_page.add_argument("--raw-output", type=Path, help="保存 Paddle 原始 JSON，仅用于适配器调试")
    ocr_page.add_argument("--native-word-output-dir", type=Path, help="保存 Paddle 原生 Word，仅用于 M0 对照")
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
            pipeline = create_paddle_pipeline(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_formula_recognition=False,
                use_chart_recognition=False,
            )
            model = predict_page_model(
                pipeline,
                args.image,
                page_index=args.page_index,
                size=PageSize(args.width_pt, args.height_pt),
                source_type=PdfKind(args.source_type),
                raw_output_path=args.raw_output,
                native_word_output_dir=args.native_word_output_dir,
            )
            output = write_page_model(model, args.output)
            print(json.dumps({"output": str(output), "blocks": len(model.blocks), "warnings": model.warnings}, ensure_ascii=False))
            return 0
        result = convert_pdf(
            args.source,
            output_dir=args.output_dir,
            workspace_root=args.workspace_root,
            mode=ConversionMode(args.mode),
            dpi=args.dpi,
            page_range=args.page_range,
            resume_job_id=args.resume_job,
            progress=_progress,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    except (Pdf2WordError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
