"""Source-first hybrid reconstruction orchestration."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from .execution import resolve_ocr_execution_profile
from .job_store import file_sha256
from .models import PageModel, RenderedPage
from .ocr import FocusedOcrPipelineCache, create_paddle_pipeline, predict_page_model, write_page_model
from .preflight import inspect_pdf
from .quality import assert_body_content_editable, editable_quality_report
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
from .word import create_positioned_editable_docx


ProgressCallback = Callable[[dict[str, object]], None]

DEFAULT_CURRENT_OUTPUT_DIR = Path("outputs/source-first-editable-v2-current")
DEFAULT_CURRENT_WORKSPACE_DIR = Path("runtime/source-first-editable-v2-current")


def parse_page_range(value: str | None, page_count: int) -> list[int]:
    """Parse a one-based page range for future source-first full-book runs."""

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


def _remove_candidate_directory(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"候选目录路径被文件占用：{path}")
        shutil.rmtree(path)


def _replace_path_prefix(value: object, replacements: tuple[tuple[Path, Path], ...]) -> object:
    if isinstance(value, dict):
        return {key: _replace_path_prefix(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_path_prefix(item, replacements) for item in value]
    if not isinstance(value, str):
        return value
    folded = value.casefold()
    for previous, current in replacements:
        previous_text = str(previous)
        boundary = len(previous_text)
        if folded.startswith(previous_text.casefold()) and (
            len(value) == boundary or value[boundary : boundary + 1] in {"/", "\\"}
        ):
            return str(current) + value[boundary:]
    return value


def _rewrite_candidate_json_paths(
    roots: tuple[Path, ...],
    replacements: tuple[tuple[Path, Path], ...],
) -> None:
    for root in roots:
        for path in root.rglob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            rewritten = _replace_path_prefix(payload, replacements)
            if rewritten != payload:
                path.write_text(json.dumps(rewritten, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_current_candidate_directories(output_dir: Path, workspace_dir: Path) -> None:
    if output_dir == workspace_dir or output_dir in workspace_dir.parents or workspace_dir in output_dir.parents:
        raise ValueError("当前候选输出目录与工作区必须相互独立，不能相同或互相嵌套。")
    for path in (output_dir, workspace_dir):
        if path.exists() and not path.is_dir():
            raise ValueError(f"当前候选目录路径被文件占用：{path}")


def _promote_current_candidate(
    staging_output: Path,
    current_output: Path,
    staging_workspace: Path,
    current_workspace: Path,
) -> None:
    token = uuid.uuid4().hex
    pairs = ((staging_output, current_output), (staging_workspace, current_workspace))
    backups: list[tuple[Path, Path]] = []
    promoted: list[Path] = []
    try:
        for _, current in pairs:
            current.parent.mkdir(parents=True, exist_ok=True)
            if current.exists():
                backup = current.parent / f".{current.name}.previous-{token}"
                current.replace(backup)
                backups.append((current, backup))
        for staging, current in pairs:
            staging.replace(current)
            promoted.append(current)
    except BaseException:
        for current in reversed(promoted):
            _remove_candidate_directory(current)
        for current, backup in reversed(backups):
            if backup.exists():
                backup.replace(current)
        raise
    for _, backup in backups:
        _remove_candidate_directory(backup)


def create_current_source_first_pilot(
    source_pdf: str | Path,
    *,
    output_dir: str | Path = DEFAULT_CURRENT_OUTPUT_DIR,
    workspace_dir: str | Path = DEFAULT_CURRENT_WORKSPACE_DIR,
    dpi: int = 300,
    ocr_device: str = "auto",
    cpu_threads: int | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[Path, Path, Path]:
    """Build and publish the single current six-page candidate.

    The active candidate is never touched until a fresh source-first run has
    completed successfully. A failed run removes its unique staging output and
    workspace automatically. A successful run atomically promotes both staging
    directories and removes the previous current candidate.
    """

    current_output = Path(output_dir).expanduser().resolve()
    current_workspace = Path(workspace_dir).expanduser().resolve()
    _validate_current_candidate_directories(current_output, current_workspace)
    token = uuid.uuid4().hex
    staging_output = current_output.parent / f".{current_output.name}.pending-{token}"
    staging_workspace = current_workspace.parent / f".{current_workspace.name}.pending-{token}"
    replacements = (
        (staging_output, current_output),
        (staging_workspace, current_workspace),
    )
    try:
        docx, quality_report, manifest = create_source_first_pilot(
            source_pdf,
            output_dir=staging_output,
            workspace_dir=staging_workspace,
            dpi=dpi,
            ocr_device=ocr_device,
            cpu_threads=cpu_threads,
            progress=progress,
        )
        relative_docx = docx.relative_to(staging_output)
        relative_quality = quality_report.relative_to(staging_output)
        relative_manifest = manifest.relative_to(staging_workspace)
        _rewrite_candidate_json_paths((staging_output, staging_workspace), replacements)
        _promote_current_candidate(
            staging_output,
            current_output,
            staging_workspace,
            current_workspace,
        )
    except BaseException:
        _remove_candidate_directory(staging_output)
        _remove_candidate_directory(staging_workspace)
        raise
    return (
        current_output / relative_docx,
        current_output / relative_quality,
        current_workspace / relative_manifest,
    )


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
    """Build the clean-source six-page paragraph-editability acceptance pilot.

    This entry point intentionally refuses a non-empty workspace. It cannot
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
    execution_profile = resolve_ocr_execution_profile(
        ocr_device,
        cpu_threads=cpu_threads,
        enforce_gpu_preference=True,
    )
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
        elif page_class in {"cover", "section_divider"}:
            model = source_fallback_model(
                page_index=rendered_page.page_index,
                size=rendered_page.size,
                image_path=clean_image,
                region_directory=page_dir / "regions",
                page_class=page_class,
                source_fingerprint=fingerprint,
                reason=f"{page_class} defaults to clean source-image fidelity in the accuracy-first pilot",
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
                editable_body_only=True,
            )
            model = apply_source_first_hybrid_policy(
                model,
                clean_image,
                page_dir / "regions",
                source_fingerprint=fingerprint,
                page_class=page_class,
                editable_body_only=True,
            )
            _emit(progress, {"type": "page_completed", "page": physical_page, "stage": "fresh_source_ocr"})
        if model.blocks and physical_page in available_physical_pages:
            model.blocks[0].style.setdefault("bookmark_name", f"source_page_{physical_page:04d}")
        write_page_model(model, page_dir / "page-model.json")
        models.append(model)

    assert_body_content_editable(models)
    docx = destination / f"{source.stem}-第二轮6页可编辑混合样本-v2.docx"
    quality_path = destination / f"{source.stem}-第二轮6页可编辑混合样本-质量报告-v2.json"
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
        "ocr_execution_profile": execution_profile.to_dict(),
        "full_book_status": "not_run_waiting_for_pilot_acceptance",
    }
    _write_json(quality_path, quality)
    manifest = workspace / "source-first-pilot.json"
    _write_json(
        manifest,
        {
            "source_pdf": str(source),
            "source_sha256": fingerprint,
            "dpi": dpi,
            "selected_physical_pages": [index + 1 for index in selected],
            "watermark_cleanup": vector_watermark_report,
            "ocr_execution_profile": execution_profile.to_dict(),
            "docx": str(docx),
            "quality_report": str(quality_path),
        },
    )
    return docx, quality_path, manifest
