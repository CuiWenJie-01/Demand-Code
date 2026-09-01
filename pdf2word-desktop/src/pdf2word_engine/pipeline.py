"""End-to-end orchestration with durable page checkpoints."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from .errors import EncryptedPdfError, JobCancelledError
from .conflicts import force_full_page_fallback, static_page_checks
from .execution import OcrExecutionProfile, is_recoverable_gpu_error, resolve_ocr_execution_profile
from .job_store import JobWorkspace, file_sha256
from .models import PAGE_MODEL_SCHEMA_VERSION, ConversionResult, JobState, PageModel, PdfKind, PreflightReport, RenderedPage
from .ocr import (
    FocusedOcrPipelineCache,
    create_paddle_pipeline,
    merge_semantic_callout_lines,
    materialize_visual_fallbacks,
    page_model_from_paddle_result,
    predict_page_model,
    recover_semantic_callout_lines,
    write_page_model,
)
from .preflight import inspect_pdf
from .quality import editable_quality_report
from .renderer import render_pages
from .source_first import (
    PILOT_PAGE_INDICES,
    apply_source_first_hybrid_policy,
    blank_page_model,
    classify_source_page,
    prepare_clean_source_image,
    source_fallback_model,
    toc_page_model,
    write_pdf_without_tagged_watermarks,
)
from .word import create_basic_editable_docx, create_positioned_editable_docx


ProgressCallback = Callable[[dict[str, object]], None]


def parse_page_range(value: str | None, page_count: int) -> list[int]:
    if not value:
        return list(range(page_count))
    selected: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        bounds = token.split("-", maxsplit=1)
        try:
            start = int(bounds[0])
            end = int(bounds[-1])
        except ValueError as exc:
            raise ValueError(f"无效页码范围：{token}") from exc
        if start < 1 or end < start or end > page_count:
            raise ValueError(f"页码范围超出文档：{token}")
        selected.update(range(start - 1, end))
    if not selected:
        raise ValueError("页码范围不能为空。")
    return sorted(selected)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _emit(callback: ProgressCallback | None, payload: dict[str, object]) -> None:
    if callback:
        callback(payload)


def required_workspace_bytes(source_size_bytes: int) -> int:
    """Reserve enough room for page PNGs, OCR artifacts and final DOCX assembly."""

    return max(3 * 1024**3, source_size_bytes * 8)


def ensure_workspace_capacity(source: Path, *destinations: Path) -> None:
    required = required_workspace_bytes(source.stat().st_size)
    checked: set[Path] = set()
    for destination in destinations:
        probe = destination.resolve()
        if probe in checked:
            continue
        checked.add(probe)
        free = shutil.disk_usage(probe).free
        if free < required:
            raise OSError(
                f"磁盘空间不足：{probe} 可用 {free} bytes，当前任务至少需要 {required} bytes。"
            )


def _load_page_model(path: Path) -> PageModel | None:
    try:
        return PageModel.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
        return None


def _render_pages_for_ocr(
    source: Path,
    *,
    workspace: JobWorkspace,
    page_indices: list[int],
    dpi: int,
    report: PreflightReport,
    callback: ProgressCallback | None,
) -> list[RenderedPage]:
    page_sizes = report.page_sizes
    completed = workspace.store.completed_page_paths()
    rendered: dict[int, RenderedPage] = {
        index: RenderedPage(index, image_path, page_sizes[index])
        for index, image_path in completed.items()
        if index in page_indices and image_path.is_file()
    }
    missing = [index for index in page_indices if index not in rendered]
    for page in render_pages(
        source,
        page_indices=missing,
        page_directory=workspace.page_dir,
        dpi=dpi,
        should_cancel=workspace.store.should_cancel,
        progress=callback,
    ):
        workspace.store.mark_page(page.page_index, state="rendered", image_path=page.image_path)
        rendered[page.page_index] = page
    return [rendered[index] for index in page_indices]


def _create_ocr_page_models(
    source: Path,
    *,
    workspace: JobWorkspace,
    page_indices: list[int],
    dpi: int,
    report: PreflightReport,
    callback: ProgressCallback | None,
    execution_profile: OcrExecutionProfile | None = None,
) -> list[PageModel]:
    rendered_pages = _render_pages_for_ocr(
        source,
        workspace=workspace,
        page_indices=page_indices,
        dpi=dpi,
        report=report,
        callback=callback,
    )
    models: dict[int, PageModel] = {}
    pending: list[RenderedPage] = []
    profile = execution_profile or resolve_ocr_execution_profile("cpu")
    focused_pipeline = FocusedOcrPipelineCache(**profile.focused_paddle_options())
    for rendered in rendered_pages:
        page_dir = workspace.page_dir(rendered.page_index)
        model_path = page_dir / "page-model.json"
        model = _load_page_model(model_path)
        if model is not None and model.page_index == rendered.page_index and model.schema_version == PAGE_MODEL_SCHEMA_VERSION:
            models[rendered.page_index] = model
            continue
        # A renderer/model upgrade must not force a costly new OCR pass for a
        # 150 MiB document.  Re-normalize the durable raw Paddle result when it
        # is available, and only enqueue OCR if that raw checkpoint is missing.
        raw_path = page_dir / "paddle-raw.json"
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            rebuilt = page_model_from_paddle_result(
                raw,
                page_index=rendered.page_index,
                size=rendered.size,
                source_type=report.kind,
            )
            focused_lines = recover_semantic_callout_lines(
                rebuilt,
                rendered.image_path,
                page_dir / "regions",
                focused_pipeline=focused_pipeline,
            )
            if focused_lines:
                payload = raw.get("res") if isinstance(raw.get("res"), dict) else raw
                if isinstance(payload, dict):
                    payload["semantic_line_ocr"] = merge_semantic_callout_lines(
                        payload.get("semantic_line_ocr"), focused_lines
                    )
                    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                    rebuilt = page_model_from_paddle_result(
                        raw,
                        page_index=rendered.page_index,
                        size=rendered.size,
                        source_type=report.kind,
                    )
            materialize_visual_fallbacks(
                rebuilt,
                rendered.image_path,
                page_dir / "regions",
                focused_pipeline=focused_pipeline,
            )
            write_page_model(rebuilt, model_path)
            models[rendered.page_index] = rebuilt
            _emit(callback, {"type": "page_rebuilt", "job_id": workspace.job_id, "page": rendered.page_index + 1, "stage": "ocr_cache"})
        except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
            pending.append(rendered)
    if pending:
        pipeline = create_paddle_pipeline(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
            **profile.paddle_options(),
        )
        for rendered in pending:
            _emit(callback, {"type": "page_started", "job_id": workspace.job_id, "page": rendered.page_index + 1, "stage": "ocr"})
            page_dir = workspace.page_dir(rendered.page_index)
            model = predict_page_model(
                pipeline,
                rendered.image_path,
                page_index=rendered.page_index,
                size=rendered.size,
                source_type=report.kind,
                raw_output_path=page_dir / "paddle-raw.json",
                region_directory=page_dir / "regions",
                focused_pipeline=focused_pipeline,
            )
            write_page_model(model, page_dir / "page-model.json")
            models[rendered.page_index] = model
            _emit(callback, {"type": "page_completed", "job_id": workspace.job_id, "page": rendered.page_index + 1, "stage": "ocr"})
    return [models[index] for index in page_indices]


def rebuild_cached_page_models(
    *,
    cached_job: str | Path,
    output_dir: str | Path,
    source_pdf: str | Path,
    progress: ProgressCallback | None = None,
) -> tuple[Path, Path, Path]:
    """Rebuild an existing OCR job without repeating its full-page OCR pass.

    The durable rendered pages and PageModels are the input.  Each old model is
    backed up once, then passed through the new source-fallback materializer
    and conflict resolver.  This is deliberately separate from ``convert`` so
    a finished deliverable is never overwritten by a quality-repair run.
    """

    job = Path(cached_job).expanduser().resolve()
    pages_root = job / "pages"
    source = Path(source_pdf).expanduser().resolve()
    if not pages_root.is_dir() or not source.is_file():
        raise FileNotFoundError("缓存作业或源 PDF 不存在。")
    report = inspect_pdf(source)
    page_dirs = sorted((item for item in pages_root.iterdir() if item.is_dir() and item.name.isdigit()), key=lambda item: int(item.name))
    if len(page_dirs) != report.page_count:
        raise ValueError(f"缓存页数 {len(page_dirs)} 与源 PDF 页数 {report.page_count} 不一致。")
    backup_root = job / "backups" / "page-model-v4-before-accuracy-first"
    backup_root.mkdir(parents=True, exist_ok=True)
    models: list[PageModel] = []
    for ordinal, page_dir in enumerate(page_dirs, start=1):
        model_path = page_dir / "page-model.json"
        render_path = page_dir / "render.png"
        if not render_path.is_file():
            candidates = list(page_dir.glob("*.png"))
            render_path = next((item for item in candidates if item.name == "render.png"), Path())
        model = _load_page_model(model_path)
        if model is None or not render_path.is_file():
            raise ValueError(f"第 {ordinal} 页缓存不完整，无法在不重跑 OCR 的条件下修复。")
        backup_path = backup_root / f"page-{ordinal:04d}.json"
        if not backup_path.exists():
            shutil.copy2(model_path, backup_path)
        materialize_visual_fallbacks(model, render_path, page_dir / "regions")
        write_page_model(model, model_path)
        models.append(model)
        _emit(progress, {"type": "page_rebuilt", "page": ordinal, "stage": "conflict_resolution"})
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    docx = destination / f"{source.stem}-可编辑版-准确优先-v2.docx"
    report_path = destination / f"{source.stem}-准确优先质量报告-v2.json"
    create_positioned_editable_docx(models, docx)
    _write_json(report_path, editable_quality_report(models))
    summary_path = destination / "accuracy-first-rebuild-summary.json"
    _write_json(summary_path, {
        "source_pdf": str(source),
        "source_page_count": report.page_count,
        "rebuild_state": "document_generated_static_checks_complete",
        "quality_state": "requires_end_to_end_representative_gate",
        "backup_page_models": str(backup_root),
        "docx": str(docx),
        "quality_report": str(report_path),
    })
    return docx, report_path, summary_path


def create_source_first_pilot(
    source_pdf: str | Path,
    *,
    output_dir: str | Path,
    workspace_dir: str | Path,
    dpi: int = 300,
    ocr_device: str = "auto",
    cpu_threads: int | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[Path, Path, Path]:
    """Build the clean-source 12-page acceptance pilot.

    This entry point intentionally refuses a non-empty workspace.  It cannot
    resume or rebuild a previous task, which makes accidental use of stale OCR
    and PageModels structurally impossible.
    """

    source = Path(source_pdf).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    workspace = Path(workspace_dir).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"PDF 文件不存在：{source}")
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"源文档直跑工作区必须为空，拒绝读取旧缓存：{workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    report = inspect_pdf(source)
    if report.page_count < max(PILOT_PAGE_INDICES) + 1:
        raise ValueError("源 PDF 页数不足，无法生成约定的代表页样本。")
    ensure_workspace_capacity(source, workspace, destination)
    fingerprint = file_sha256(source)
    selected = list(PILOT_PAGE_INDICES)
    clean_pdf = workspace / "source-without-tagged-watermarks.pdf"
    vector_watermark_report = write_pdf_without_tagged_watermarks(
        source,
        clean_pdf,
        page_indices=selected,
    )
    available_physical_pages = {index + 1 for index in selected}

    def page_directory(page_index: int) -> Path:
        directory = workspace / "pages" / f"{page_index + 1:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    subset_rendered = list(
        render_pages(
            clean_pdf,
            page_indices=list(range(len(selected))),
            page_directory=lambda subset_index: page_directory(selected[subset_index]),
            dpi=dpi,
            progress=progress,
        )
    )
    rendered = [
        RenderedPage(
            page_index=selected[subset_page.page_index],
            image_path=subset_page.image_path,
            size=subset_page.size,
        )
        for subset_page in subset_rendered
    ]
    execution_profile = resolve_ocr_execution_profile(ocr_device, cpu_threads=cpu_threads)
    paddle_pipeline: object | None = None
    focused_pipeline: FocusedOcrPipelineCache | None = None
    models: list[PageModel] = []
    watermark_reports: list[dict[str, object]] = []
    for rendered_page in rendered:
        physical_page = rendered_page.page_index + 1
        page_dir = page_directory(rendered_page.page_index)
        clean_image = page_dir / "clean-source.png"
        watermark = prepare_clean_source_image(rendered_page.image_path, clean_image)
        watermark_reports.append({"page": physical_page, **watermark})
        with Image.open(clean_image) as image:
            page_class = classify_source_page(rendered_page.page_index, image)
        _emit(progress, {"type": "source_page_classified", "page": physical_page, "page_class": page_class})
        if page_class == "blank":
            model = blank_page_model(
                page_index=rendered_page.page_index,
                size=rendered_page.size,
                image_path=clean_image,
                source_fingerprint=fingerprint,
            )
        elif page_class == "table_of_contents":
            model = toc_page_model(
                page_index=rendered_page.page_index,
                size=rendered_page.size,
                image_path=clean_image,
                region_directory=page_dir / "regions",
                source_fingerprint=fingerprint,
                available_pages=available_physical_pages,
            )
        elif page_class in {"cover", "section_divider", "chapter_opener", "formula_heavy"}:
            bookmark = f"source_page_{physical_page:04d}" if page_class == "chapter_opener" else None
            model = source_fallback_model(
                page_index=rendered_page.page_index,
                size=rendered_page.size,
                image_path=clean_image,
                region_directory=page_dir / "regions",
                page_class=page_class,
                source_fingerprint=fingerprint,
                reason=f"{page_class} defaults to clean source-image fidelity in the accuracy-first pilot",
                bookmark_name=bookmark,
            )
        else:
            if paddle_pipeline is None:
                paddle_pipeline = create_paddle_pipeline(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_formula_recognition=False,
                    use_chart_recognition=False,
                    **execution_profile.paddle_options(),
                )
                focused_pipeline = FocusedOcrPipelineCache(**execution_profile.focused_paddle_options())
            _emit(progress, {"type": "page_started", "page": physical_page, "stage": "fresh_source_ocr"})
            model = predict_page_model(
                paddle_pipeline,
                clean_image,
                page_index=rendered_page.page_index,
                size=rendered_page.size,
                source_type=report.kind,
                raw_output_path=page_dir / "paddle-raw.json",
                region_directory=page_dir / "regions",
                focused_pipeline=focused_pipeline,
            )
            model = apply_source_first_hybrid_policy(
                model,
                clean_image,
                page_dir / "regions",
                source_fingerprint=fingerprint,
            )
            blocking_findings = [
                finding
                for finding in static_page_checks(model)
                if finding.get("type") in {"duplicate_text", "image_text_conflict", "high_overlap", "low_confidence"}
            ]
            if blocking_findings:
                finding_types = sorted({str(finding.get("type")) for finding in blocking_findings})
                model = force_full_page_fallback(
                    model,
                    clean_image,
                    page_dir / "regions" / "static-gate-fallback",
                    reason=(
                        "accuracy-first static gate rejected editable reconstruction: "
                        + ", ".join(finding_types)
                    ),
                )
                model.page_class = page_class
                model.reconstruction_mode = "clean_full_page_source_image_after_static_gate"
                model.warnings.append(
                    f"静态门禁触发整页回退：{len(blocking_findings)} 项（{', '.join(finding_types)}）。"
                )
            _emit(progress, {"type": "page_completed", "page": physical_page, "stage": "fresh_source_ocr"})
        if model.blocks and physical_page in available_physical_pages:
            model.blocks[0].style.setdefault("bookmark_name", f"source_page_{physical_page:04d}")
        write_page_model(model, page_dir / "page-model.json")
        models.append(model)

    docx = destination / f"{source.stem}-源文档直跑样本-无上岸人水印-v1.docx"
    quality_path = destination / f"{source.stem}-源文档直跑样本-质量报告-v1.json"
    create_positioned_editable_docx(models, docx)
    quality = editable_quality_report(models)
    quality["source_first"] = {
        "source_pdf": str(source),
        "source_sha256": fingerprint,
        "cache_policy": "fresh render and fresh OCR only; non-empty workspace rejected",
        "selected_physical_pages": [index + 1 for index in selected],
        "page_classes": {str(model.page_index + 1): model.page_class for model in models},
        "reconstruction_modes": {str(model.page_index + 1): model.reconstruction_mode for model in models},
        "watermark_cleanup": watermark_reports,
        "vector_watermark_cleanup": vector_watermark_report,
        "full_book_status": "not_run_waiting_for_pilot_acceptance",
    }
    _write_json(quality_path, quality)
    manifest = workspace / "source-first-pilot.json"
    _write_json(manifest, {
        "source_pdf": str(source),
        "source_sha256": fingerprint,
        "dpi": dpi,
        "selected_physical_pages": [index + 1 for index in selected],
        "watermark_cleanup": vector_watermark_report,
        "docx": str(docx),
        "quality_report": str(quality_path),
    })
    return docx, quality_path, manifest


def convert_pdf(
    source: str | Path,
    *,
    output_dir: str | Path,
    workspace_root: str | Path,
    dpi: int = 200,
    page_range: str | None = None,
    resume_job_id: str | None = None,
    ocr_device: str = "auto",
    cpu_threads: int | None = None,
    progress: ProgressCallback | None = None,
) -> ConversionResult:
    """Convert a PDF while keeping source and temporary state strictly separate."""

    source_path = Path(source).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    if destination == source_path.parent:
        raise ValueError("输出目录不能是输入 PDF 所在目录，以保护原始文件目录。")
    Path(workspace_root).expanduser().resolve().mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    ensure_workspace_capacity(source_path, Path(workspace_root), destination)
    report = inspect_pdf(source_path)
    if report.encrypted:
        raise EncryptedPdfError("PDF 已加密；当前版本不支持密码输入。")
    selected_pages = parse_page_range(page_range, report.page_count)
    uses_ocr = report.kind is not PdfKind.BORN_DIGITAL
    execution_profile = (
        resolve_ocr_execution_profile(ocr_device, cpu_threads=cpu_threads) if uses_ocr else None
    )
    config = {
        "route": "ocr_layout" if uses_ocr else "text_layer",
        "dpi": dpi,
        "page_range": page_range,
        "selected_pages": [index + 1 for index in selected_pages],
    }
    if resume_job_id:
        workspace = JobWorkspace.open(workspace_root, resume_job_id)
        stored = workspace.store.job_details()
        if Path(stored["source_path"]).resolve() != source_path or stored["source_sha256"] != file_sha256(source_path):
            raise ValueError("恢复任务的源文件与当前输入不一致。")
        if json.loads(stored["config_json"]) != config:
            raise ValueError("恢复任务的转换配置与当前请求不一致。")
    else:
        workspace = JobWorkspace.create(workspace_root)
        workspace.store.create(job_id=workspace.job_id, source_path=source_path, config=config, preflight=report)
        _write_json(workspace.path / "source-info.json", report.to_dict(include_page_sizes=True))
    _emit(progress, {"type": "job_state_changed", "job_id": workspace.job_id, "state": JobState.RUNNING.value})
    workspace.store.set_state(JobState.RUNNING)
    if execution_profile is not None:
        _emit(
            progress,
            {
                "type": "ocr_execution_profile",
                "job_id": workspace.job_id,
                "profile": execution_profile.to_dict(),
            },
        )
    outputs: list[Path] = []
    quality_report_path: Path | None = None
    warnings = list(report.warnings)
    try:
        editable_output = destination / f"{source_path.stem}-可编辑版.docx"
        if uses_ocr:
            assert execution_profile is not None
            try:
                models = _create_ocr_page_models(
                    source_path,
                    workspace=workspace,
                    page_indices=selected_pages,
                    dpi=dpi,
                    report=report,
                    callback=progress,
                    execution_profile=execution_profile,
                )
            except Exception as exc:
                if not execution_profile.uses_gpu or not is_recoverable_gpu_error(exc):
                    raise
                fallback_profile = resolve_ocr_execution_profile("cpu", cpu_threads=cpu_threads)
                _emit(
                    progress,
                    {
                        "type": "ocr_execution_fallback",
                        "job_id": workspace.job_id,
                        "from": execution_profile.to_dict(),
                        "to": fallback_profile.to_dict(),
                        "error": str(exc),
                    },
                )
                models = _create_ocr_page_models(
                    source_path,
                    workspace=workspace,
                    page_indices=selected_pages,
                    dpi=dpi,
                    report=report,
                    callback=progress,
                    execution_profile=fallback_profile,
                )
            outputs.append(create_positioned_editable_docx(models, editable_output))
            quality_report_path = destination / f"{source_path.stem}-质量报告.json"
            _write_json(quality_report_path, editable_quality_report(models))
            _emit(progress, {"type": "quality_report_ready", "job_id": workspace.job_id, "path": str(quality_report_path)})
        else:
            outputs.append(
                create_basic_editable_docx(
                    source_path,
                    page_sizes=report.page_sizes,
                    kind=report.kind,
                    page_indices=selected_pages,
                    output_path=editable_output,
                )
            )
        _emit(progress, {"type": "output_ready", "job_id": workspace.job_id, "path": str(editable_output), "mode": "editable"})
        workspace.store.set_state(JobState.COMPLETED)
        _emit(progress, {"type": "job_state_changed", "job_id": workspace.job_id, "state": JobState.COMPLETED.value})
        return ConversionResult(workspace.job_id, JobState.COMPLETED, report, outputs, warnings, quality_report_path)
    except JobCancelledError:
        workspace.store.set_state(JobState.CANCELLED)
        _emit(progress, {"type": "job_state_changed", "job_id": workspace.job_id, "state": JobState.CANCELLED.value})
        raise
    except Exception as exc:
        workspace.store.set_state(JobState.FAILED, error_message=str(exc))
        _emit(progress, {"type": "job_state_changed", "job_id": workspace.job_id, "state": JobState.FAILED.value, "error": str(exc)})
        raise
