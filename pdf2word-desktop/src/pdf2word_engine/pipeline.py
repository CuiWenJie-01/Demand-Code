"""End-to-end orchestration with durable page checkpoints."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from .errors import EncryptedPdfError, JobCancelledError, OcrRequiredError
from .job_store import JobWorkspace, file_sha256
from .models import ConversionMode, ConversionResult, JobState, PreflightReport, RenderedPage
from .preflight import inspect_pdf
from .renderer import render_pages
from .word import create_basic_editable_docx, create_visual_docx


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


def _render_or_resume(
    source: Path,
    *,
    workspace: JobWorkspace,
    page_indices: list[int],
    dpi: int,
    report: PreflightReport,
    callback: ProgressCallback | None,
) -> list[RenderedPage]:
    completed = workspace.store.completed_page_paths()
    missing = [index for index in page_indices if index not in completed or not completed[index].is_file()]
    rendered: dict[int, RenderedPage] = {}
    for index in page_indices:
        if index in completed and completed[index].is_file():
            rendered[index] = RenderedPage(index, completed[index], report.page_sizes[index])
    if missing:
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


def convert_pdf(
    source: str | Path,
    *,
    output_dir: str | Path,
    workspace_root: str | Path,
    mode: ConversionMode = ConversionMode.VISUAL,
    dpi: int = 200,
    page_range: str | None = None,
    resume_job_id: str | None = None,
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
    config = {
        "mode": mode.value,
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
    outputs: list[Path] = []
    warnings = list(report.warnings)
    try:
        if mode in {ConversionMode.VISUAL, ConversionMode.BOTH}:
            pages = _render_or_resume(
                source_path,
                workspace=workspace,
                page_indices=selected_pages,
                dpi=dpi,
                report=report,
                callback=progress,
            )
            visual_output = destination / f"{source_path.stem}-保真版.docx"
            outputs.append(create_visual_docx(pages, visual_output))
            _emit(progress, {"type": "output_ready", "job_id": workspace.job_id, "path": str(visual_output), "mode": "visual"})
        if mode in {ConversionMode.EDITABLE, ConversionMode.BOTH}:
            editable_output = destination / f"{source_path.stem}-可编辑版.docx"
            try:
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
            except OcrRequiredError as exc:
                if mode is ConversionMode.EDITABLE:
                    raise
                warnings.append(str(exc))
        workspace.store.set_state(JobState.COMPLETED)
        _emit(progress, {"type": "job_state_changed", "job_id": workspace.job_id, "state": JobState.COMPLETED.value})
        return ConversionResult(workspace.job_id, JobState.COMPLETED, report, outputs, warnings)
    except JobCancelledError:
        workspace.store.set_state(JobState.CANCELLED)
        _emit(progress, {"type": "job_state_changed", "job_id": workspace.job_id, "state": JobState.CANCELLED.value})
        raise
    except Exception as exc:
        workspace.store.set_state(JobState.FAILED, error_message=str(exc))
        _emit(progress, {"type": "job_state_changed", "job_id": workspace.job_id, "state": JobState.FAILED.value, "error": str(exc)})
        raise
