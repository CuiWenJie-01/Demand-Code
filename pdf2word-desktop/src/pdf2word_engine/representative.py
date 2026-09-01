"""Versioned representative-page manifests and batch regression orchestration."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .models import PageModel
from .quality import CharacterErrorRate, character_error_rate, compare_rasters, model_text_for_cer, normalize_cer_text
from .renderer import render_pages
from .regression import GoldenPageReport, VisualRegressionError, render_docx_to_png, verify_golden_page
from .word import create_positioned_editable_docx
from .word_render import verify_with_microsoft_word


REQUIRED_COVERAGE = frozenset({"cover", "exam_question", "formula", "table", "chart", "watermark", "last_page"})


@dataclass(frozen=True, slots=True)
class RepresentativePage:
    page_number: int
    coverage: tuple[str, ...]
    description: str
    golden: bool = False
    model_path: Path | None = None
    docx_path: Path | None = None
    visual_baseline_path: Path | None = None
    cer_annotation_path: Path | None = None
    minimum_ssim: float = 0.84
    maximum_mae: float = 9.0
    maximum_cer: float = 0.005


@dataclass(frozen=True, slots=True)
class RepresentativeManifest:
    schema_version: int
    source_page_count: int
    pages: tuple[RepresentativePage, ...]


@dataclass(frozen=True, slots=True)
class RepresentativeRunReport:
    passed: tuple[int, ...]
    pending: tuple[int, ...]
    reports: tuple[GoldenPageReport, ...]


@dataclass(frozen=True, slots=True)
class RepresentativeQualityReport:
    page_number: int
    visual_ssim: float
    visual_mae: float
    cer: CharacterErrorRate | None


@dataclass(frozen=True, slots=True)
class RepresentativeWordReport:
    page_number: int
    pdf_path: Path
    rendered_page_count: int


def _relative_path(value: object, root: Path) -> Path | None:
    if not value:
        return None
    return (root / str(value)).resolve()


def load_representative_page_model(page: RepresentativePage) -> PageModel:
    """Load a representative PageModel and resolve its bundled image assets.

    Conversion-job checkpoints deliberately keep absolute asset paths: their
    lifetime is the job workspace.  A representative baseline is different:
    it must be movable and remain rebuildable after temporary job directories
    have been cleaned.  Relative ``asset_path`` values are therefore resolved
    beside the PageModel when it is loaded through the representative workflow.
    """

    if not page.model_path or not page.model_path.is_file():
        raise VisualRegressionError(f"代表页 {page.page_number} 缺少 PageModel。")
    try:
        payload = json.loads(page.model_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualRegressionError(f"无法读取代表页 {page.page_number} 的 PageModel。") from exc
    if not isinstance(payload, Mapping):
        raise VisualRegressionError(f"代表页 {page.page_number} 的 PageModel 格式无效。")
    blocks = payload.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict) or not isinstance(block.get("asset_path"), str):
                continue
            asset = Path(block["asset_path"])
            if not asset.is_absolute():
                bundled_asset = page.model_path.parent / asset
                # Older local baselines used project-root-relative paths.  Keep
                # them working while preferring the portable asset bundled next
                # to the PageModel.
                if bundled_asset.is_file() or not asset.is_file():
                    block["asset_path"] = str(bundled_asset.resolve())
                else:
                    block["asset_path"] = str(asset.resolve())
    return PageModel.from_dict(payload)


def load_representative_manifest(path: str | Path) -> RepresentativeManifest:
    """Load the checked-in page selection without binding it to a PDF path."""

    manifest_path = Path(path).resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualRegressionError(f"无法读取代表页清单：{manifest_path}") from exc
    if not isinstance(payload, Mapping):
        raise VisualRegressionError("代表页清单根节点必须是 JSON 对象。")
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list):
        raise VisualRegressionError("代表页清单缺少 pages 数组。")
    pages: list[RepresentativePage] = []
    for raw in raw_pages:
        if not isinstance(raw, Mapping):
            raise VisualRegressionError("代表页条目必须是 JSON 对象。")
        coverage = raw.get("coverage", [])
        if not isinstance(coverage, list) or not all(isinstance(item, str) and item for item in coverage):
            raise VisualRegressionError("代表页 coverage 必须是非空字符串数组。")
        try:
            page_number = int(raw["page_number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VisualRegressionError("代表页缺少有效 page_number。") from exc
        pages.append(
            RepresentativePage(
                page_number=page_number,
                coverage=tuple(coverage),
                description=str(raw.get("description", "")),
                golden=bool(raw.get("golden", False)),
                model_path=_relative_path(raw.get("model_path"), manifest_path.parent),
                docx_path=_relative_path(raw.get("docx_path"), manifest_path.parent),
                visual_baseline_path=_relative_path(raw.get("visual_baseline_path"), manifest_path.parent),
                cer_annotation_path=_relative_path(raw.get("cer_annotation_path"), manifest_path.parent),
                minimum_ssim=float(raw.get("minimum_ssim", 0.84)),
                maximum_mae=float(raw.get("maximum_mae", 9.0)),
                maximum_cer=float(raw.get("maximum_cer", 0.005)),
            )
        )
    try:
        source_page_count = int(payload["source_page_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VisualRegressionError("代表页清单缺少有效 source_page_count。") from exc
    manifest = RepresentativeManifest(int(payload.get("schema_version", 1)), source_page_count, tuple(pages))
    validate_representative_manifest(manifest)
    return manifest


def validate_representative_manifest(manifest: RepresentativeManifest) -> None:
    """Fail closed when page selection becomes too small, vague or unrepeatable."""

    if not 12 <= len(manifest.pages) <= 20:
        raise VisualRegressionError("代表页集必须固定为 12–20 页。")
    numbers = [page.page_number for page in manifest.pages]
    if len(set(numbers)) != len(numbers):
        raise VisualRegressionError("代表页集包含重复页码。")
    if any(page_number < 1 or page_number > manifest.source_page_count for page_number in numbers):
        raise VisualRegressionError("代表页页码超出源 PDF 页数。")
    coverage = {item for page in manifest.pages for item in page.coverage}
    missing = sorted(REQUIRED_COVERAGE - coverage)
    if missing:
        raise VisualRegressionError(f"代表页集缺少必需覆盖：{', '.join(missing)}。")
    golden = [page for page in manifest.pages if page.golden]
    if not golden:
        raise VisualRegressionError("代表页集至少需要一个黄金视觉基准。")
    if any(not page.model_path or not page.docx_path for page in golden):
        raise VisualRegressionError("黄金页必须同时登记 PageModel 和 DOCX 路径。")
    for page in manifest.pages:
        if not 0.0 <= page.minimum_ssim <= 1.0 or page.maximum_mae < 0.0 or not 0.0 <= page.maximum_cer <= 1.0:
            raise VisualRegressionError(f"代表页 {page.page_number} 的质量阈值无效。")


def run_representative_regressions(
    manifest: RepresentativeManifest,
    *,
    renderer: str | None = None,
    strict: bool = False,
) -> RepresentativeRunReport:
    """Run complete page gates for ready entries and explicitly report the rest.

    `strict=True` is the M1 exit gate: every selected page must have both a
    model and a generated DOCX. The ordinary mode keeps the selected future
    pages visible while their initial baselines are being built.
    """

    passed: list[int] = []
    pending: list[int] = []
    reports: list[GoldenPageReport] = []
    for page in manifest.pages:
        if not page.model_path or not page.docx_path:
            pending.append(page.page_number)
            continue
        if not page.model_path.is_file() or not page.docx_path.is_file():
            if page.golden:
                raise VisualRegressionError(f"黄金页 {page.page_number} 的基准工件不存在。")
            pending.append(page.page_number)
            continue
        model = load_representative_page_model(page)
        reports.append(verify_golden_page(page.docx_path, model, renderer=renderer))
        passed.append(page.page_number)
    if strict and pending:
        raise VisualRegressionError(f"代表页回归尚未完整：待建立基线页 {pending}。")
    return RepresentativeRunReport(tuple(passed), tuple(pending), tuple(reports))


def _load_cer_annotation(path: Path) -> tuple[str | None, list[str] | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualRegressionError(f"无法读取 CER 标注：{path}") from exc
    if not isinstance(payload, Mapping):
        raise VisualRegressionError(f"CER 标注格式无效：{path}")
    if payload.get("exclude_from_cer") is True:
        if not isinstance(payload.get("exclusion_reason"), str) or not payload["exclusion_reason"].strip():
            raise VisualRegressionError(f"CER 豁免页必须说明原因：{path}")
        return None, None
    if payload.get("schema_version") == 2:
        if payload.get("workflow") != "page_review" or payload.get("page_confirmed") is not True:
            raise VisualRegressionError(f"CER 页审校尚未确认，不能作为人工真值：{path}")
    segments = payload.get("segments")
    if isinstance(segments, list):
        if not segments:
            raise VisualRegressionError(f"CER 标注 segments 不能为空：{path}")
        block_ids: list[str] = []
        parts: list[str] = []
        for segment in segments:
            if not isinstance(segment, Mapping) or not isinstance(segment.get("block_id"), str) or not isinstance(
                segment.get("reference_text"), str
            ):
                raise VisualRegressionError(f"CER 标注 segment 格式无效：{path}")
            block_ids.append(segment["block_id"])
            parts.append(segment["reference_text"])
        return "".join(parts), block_ids
    if not isinstance(payload.get("reference_text"), str):
        raise VisualRegressionError(f"CER 标注格式无效：{path}")
    block_ids = payload.get("block_ids")
    if block_ids is not None and (not isinstance(block_ids, list) or not all(isinstance(item, str) for item in block_ids)):
        raise VisualRegressionError(f"CER 标注 block_ids 格式无效：{path}")
    return payload["reference_text"], block_ids


def _editable_cer_blocks(model: PageModel) -> list[Any]:
    """Return the stable, auditable block sequence used by CER and review."""

    excluded_roles = {"sidebar_page_number", "sidebar_vertical_text", "sidebar_accent_rule"}
    return [
        block
        for block in sorted(model.blocks, key=lambda block: (block.reading_order, block.z_index, block.block_id))
        if block.text and not block.asset_path and str(block.style.get("semantic_role", "")) not in excluded_roles
    ]


def _load_independent_ocr(path: str | Path | None) -> dict[int, dict[str, str]]:
    """Load optional independent OCR text keyed by page number and block id.

    The deliberately small interchange format is ``{"pages": {"10":
    {"block-id": "text"}}}``.  A top-level page mapping is also accepted so
    an evaluator can export its results without a conversion step.
    """

    if path is None:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualRegressionError(f"无法读取独立 OCR 结果：{path}") from exc
    if not isinstance(payload, Mapping):
        raise VisualRegressionError("独立 OCR 结果必须是 JSON 对象。")
    raw_pages = payload.get("pages", payload)
    if not isinstance(raw_pages, Mapping):
        raise VisualRegressionError("独立 OCR 结果缺少 pages 对象。")
    result: dict[int, dict[str, str]] = {}
    for raw_page, raw_blocks in raw_pages.items():
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError) as exc:
            raise VisualRegressionError("独立 OCR 页码必须是整数。") from exc
        if not isinstance(raw_blocks, Mapping) or not all(isinstance(key, str) and isinstance(value, str) for key, value in raw_blocks.items()):
            raise VisualRegressionError(f"独立 OCR 第 {page_number} 页必须是 block_id 到文本的对象。")
        result[page_number] = dict(raw_blocks)
    return result


def _review_segments(model: PageModel, *, independent_text: Mapping[str, str], low_confidence_threshold: float) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    for ordinal, block in enumerate(_editable_cer_blocks(model), start=1):
        production = block.text or ""
        secondary = independent_text.get(block.block_id)
        flags: list[str] = []
        if block.confidence is not None and block.confidence < low_confidence_threshold:
            flags.append("low_confidence")
        if secondary is not None and normalize_cer_text(secondary) != normalize_cer_text(production):
            flags.append("ocr_disagreement")
        if block.warnings:
            flags.append("suspected_missing_or_fragmented_line")
        segments.append(
            {
                "ordinal": ordinal,
                "block_id": block.block_id,
                "semantic_role": str(block.style.get("semantic_role", "")),
                "bbox": list(block.bbox),
                "confidence": block.confidence,
                "production_ocr_text": production,
                "independent_ocr_text": secondary,
                "review_flags": flags,
                # This field is intentionally blank until a reviewer confirms
                # the page in the UI.  OCR text is a draft, never a CER answer.
                "reference_text": "",
            }
        )
    return segments


def _page_review_payload(
    page: RepresentativePage,
    model: PageModel,
    *,
    independent_text: Mapping[str, str],
    low_confidence_threshold: float,
    source_image: str | None = None,
) -> dict[str, object]:
    segments = _review_segments(model, independent_text=independent_text, low_confidence_threshold=low_confidence_threshold)
    unmatched = sorted(set(independent_text) - {str(segment["block_id"]) for segment in segments})
    return {
        "schema_version": 2,
        "workflow": "page_review",
        "page_number": page.page_number,
        "page_confirmed": False,
        "source_image": source_image,
        "low_confidence_threshold": low_confidence_threshold,
        "instructions": "通读原图和预填文本，修正标红处及任何其他错误，最后一次确认整页。预填 OCR 不是人工真值。",
        "unmatched_independent_block_ids": unmatched,
        "segments": segments,
    }


def write_cer_templates(manifest: RepresentativeManifest, output_directory: str | Path) -> tuple[Path, ...]:
    """Create page-review drafts while keeping block IDs for the CER gate.

    Unlike the old block-by-block blank template, each file is one review unit.
    It deliberately separates OCR draft text from the empty human reference and
    cannot be accepted by the CER gate before ``page_confirmed`` is true.
    """

    destination = Path(output_directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for page in manifest.pages:
        if not page.model_path or not page.model_path.is_file():
            raise VisualRegressionError(f"代表页 {page.page_number} 缺少 PageModel，无法生成 CER 模板。")
        model = load_representative_page_model(page)
        segments = _review_segments(model, independent_text={}, low_confidence_threshold=0.90)
        output = destination / f"page-{page.page_number:04d}.json"
        if not segments:
            payload: dict[str, object] = {
                "schema_version": 1,
                "page_number": page.page_number,
                "exclude_from_cer": True,
                "exclusion_reason": "该代表页没有可编辑 OCR 文本，全部内容为源图回退。",
            }
        else:
            payload = _page_review_payload(page, model, independent_text={}, low_confidence_threshold=0.90)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        outputs.append(output)
    return tuple(outputs)


def cer_review_catalog(manifest: RepresentativeManifest, manifest_path: str | Path) -> dict[str, object]:
    """Return the small, UI-facing index for a representative CER library.

    The desktop client uses this instead of inspecting annotation files itself.
    That keeps the source-of-truth paths in the manifest and lets a later
    manifest add only a new/exception page without reopening completed pages.
    """

    entries: list[dict[str, object]] = []
    completed = 0
    for page in manifest.pages:
        annotation_path = page.cer_annotation_path
        confirmed = False
        excluded = False
        if annotation_path and annotation_path.is_file():
            try:
                payload = json.loads(annotation_path.read_text(encoding="utf-8"))
                excluded = isinstance(payload, Mapping) and payload.get("exclude_from_cer") is True
                confirmed = isinstance(payload, Mapping) and payload.get("page_confirmed") is True
            except (OSError, json.JSONDecodeError):
                # A malformed existing annotation is deliberately shown as
                # pending so the reviewer can reopen and repair that page.
                pass
        done = confirmed or excluded
        completed += int(done)
        entries.append(
            {
                "page_number": page.page_number,
                "coverage": list(page.coverage),
                "description": page.description,
                "completed": done,
                "excluded_from_cer": excluded,
                "annotation_path": str(annotation_path) if annotation_path else None,
            }
        )
    return {
        "manifest_path": str(Path(manifest_path).resolve()),
        "selected_page_count": len(manifest.pages),
        "completed_page_count": completed,
        "pages": entries,
    }


def _review_page(manifest: RepresentativeManifest, page_number: int) -> RepresentativePage:
    for page in manifest.pages:
        if page.page_number == page_number:
            return page
    raise VisualRegressionError(f"第 {page_number} 页不在当前代表页清单中。")


def _load_review_model(page: RepresentativePage) -> PageModel:
    if not page.model_path or not page.model_path.is_file():
        raise VisualRegressionError(f"代表页 {page.page_number} 缺少 PageModel，无法进行 CER 审校。")
    return load_representative_page_model(page)


def prepare_cer_review_page(
    manifest: RepresentativeManifest,
    *,
    page_number: int,
    source_pdf: str | Path,
    independent_ocr_path: str | Path | None = None,
    dpi: int = 144,
    low_confidence_threshold: float = 0.90,
) -> dict[str, object]:
    """Build one desktop review page, including a transient source-image data URL.

    Only the selected page is rendered and sent across the sidecar boundary;
    this avoids loading all 12 high-resolution pages merely to review one.
    """

    if not 0.0 <= low_confidence_threshold <= 1.0:
        raise ValueError("低置信度阈值必须介于 0 和 1 之间。")
    source = Path(source_pdf)
    if not source.is_file():
        raise VisualRegressionError(f"源 PDF 不存在：{source}")
    page = _review_page(manifest, page_number)
    model = _load_review_model(page)
    independent = _load_independent_ocr(independent_ocr_path)
    with tempfile.TemporaryDirectory(prefix="pdf2word-cer-review-") as directory:
        rendered = list(
            render_pages(
                source,
                page_indices=[page.page_number - 1],
                page_directory=lambda _: Path(directory),
                dpi=dpi,
            )
        )
        if len(rendered) != 1:
            raise VisualRegressionError(f"无法渲染源 PDF 第 {page.page_number} 页。")
        image_path = rendered[0].image_path
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = _page_review_payload(
        page,
        model,
        independent_text=independent.get(page.page_number, {}),
        low_confidence_threshold=low_confidence_threshold,
    )
    return {
        "page": {
            "page_number": page.page_number,
            "description": page.description,
            "coverage": list(page.coverage),
            "annotation_path": str(page.cer_annotation_path) if page.cer_annotation_path else None,
        },
        "review": payload,
        "source_image_data_url": f"data:image/png;base64,{encoded}",
        # OCR bboxes use the PageModel input raster. The UI scales these to
        # the rendered source image while retaining a stable coordinate basis.
        "annotation_image_width_px": model.source_image_width_px,
        "annotation_image_height_px": model.source_image_height_px,
    }


def save_cer_review_page(
    manifest: RepresentativeManifest,
    *,
    page_number: int,
    segments: list[Mapping[str, object]] | None = None,
) -> Path:
    """Validate and atomically persist one full-page CER confirmation.

    The client may change reference text only. Block IDs and review metadata
    are rebuilt from the PageModel so a stale UI cannot silently write a CER
    annotation for a different baseline revision.
    """

    page = _review_page(manifest, page_number)
    if not page.cer_annotation_path:
        raise VisualRegressionError(f"代表页 {page.page_number} 未配置 cer_annotation_path，无法保存。")
    model = _load_review_model(page)
    expected = _review_segments(model, independent_text={}, low_confidence_threshold=0.90)
    target = page.cer_annotation_path
    if not expected:
        payload: dict[str, object] = {
            "schema_version": 1,
            "page_number": page.page_number,
            "exclude_from_cer": True,
            "exclusion_reason": "该代表页没有可编辑 OCR 文本，全部内容为源图回退。",
        }
    else:
        if not isinstance(segments, list) or len(segments) != len(expected):
            raise VisualRegressionError(f"第 {page.page_number} 页审校片段数量与当前 PageModel 不一致。")
        references: list[str] = []
        for supplied, baseline in zip(segments, expected, strict=True):
            if not isinstance(supplied, Mapping) or supplied.get("block_id") != baseline["block_id"]:
                raise VisualRegressionError(f"第 {page.page_number} 页审校块顺序或 block_id 已过期，请重新打开该页。")
            reference = supplied.get("reference_text")
            if not isinstance(reference, str):
                raise VisualRegressionError(f"第 {page.page_number} 页的 CER 文本必须是字符串。")
            references.append(reference)
        payload = _page_review_payload(page, model, independent_text={}, low_confidence_threshold=0.90)
        payload["page_confirmed"] = True
        payload["reviewed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        clean_segments: list[dict[str, object]] = []
        for base, reference in zip(payload["segments"], references, strict=True):
            segment = dict(base)
            segment["reference_text"] = reference
            segment.pop("production_ocr_text", None)
            segment.pop("independent_ocr_text", None)
            segment.pop("review_flags", None)
            clean_segments.append(segment)
        payload["segments"] = clean_segments
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return target


def _page_review_html(payload: Mapping[str, object]) -> str:
    """Produce a self-contained browser review page with one confirmation action."""

    serialized = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang=\"zh-CN\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>CER 页审校</title>
<style>
body {{ margin:0; background:#f5f2f7; color:#211a23; font:15px 'Microsoft YaHei UI','Segoe UI',sans-serif; }}
main {{ max-width:1500px; margin:auto; padding:24px; }} header,.layout {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(420px,1fr); gap:20px; }}
header {{ grid-template-columns:1fr auto; align-items:center; margin-bottom:18px; }} h1 {{ margin:0; font-size:24px; }} p {{ color:#655e68; }} .panel {{ background:#fff; border:1px solid #e1d9e5; border-radius:14px; padding:16px; }}
.source img {{ width:100%; height:auto; display:block; }} .empty-source {{ padding:80px 20px; text-align:center; background:#faf7fb; color:#786f7d; }}
.summary {{ display:flex; gap:8px; flex-wrap:wrap; margin:10px 0; }} .badge {{ border-radius:99px; padding:4px 9px; background:#f0ecf2; font-size:12px; }} .flag {{ background:#ffe9e7; color:#a32920; }}
.segment {{ border-top:1px solid #eee9ef; padding:10px 0; }} .segment:first-of-type {{ border-top:0; }} label {{ display:flex; justify-content:space-between; gap:12px; font-size:12px; color:#716a75; margin-bottom:5px; }}
textarea {{ width:100%; min-height:44px; resize:vertical; border:1px solid #d8cedc; border-radius:7px; padding:8px; font:14px/1.45 'Microsoft YaHei UI',sans-serif; }} .attention textarea {{ border:2px solid #dd5146; background:#fffafa; }}
.secondary {{ margin:7px 0 0; padding:7px; background:#faf8fb; border-radius:6px; color:#625b66; font-size:13px; }} button {{ border:0; border-radius:9px; padding:11px 16px; background:#c31373; color:white; font-weight:700; cursor:pointer; }} button:disabled {{ background:#c7b9c4; cursor:not-allowed; }}
.footer {{ position:sticky; bottom:16px; margin-top:16px; display:flex; gap:12px; align-items:center; justify-content:space-between; background:#211a23; color:#fff; padding:14px; border-radius:12px; }} .footer span {{ color:#ded4df; }}
@media(max-width:900px) {{ main {{ padding:12px; }} header,.layout {{ grid-template-columns:1fr; }} .footer {{ position:static; flex-direction:column; align-items:stretch; }} }}
</style>
<main><header><div><h1 id=\"title\"></h1><p>逐页通读。只需在最后点击一次“确认整页并下载标注”。红色项来自双 OCR 差异、低置信度或疑似断行。</p></div><div id=\"summary\" class=\"summary\"></div></header>
<div class=\"layout\"><section class=\"panel source\"><h2>原始页面</h2><div id=\"source\"></div></section><section class=\"panel\"><h2>预填文本</h2><p>文本默认来自生产 OCR。逐行编辑只用于修正；确认操作才会将本页文本写成可用于 CER 的人工真值。</p><div id=\"segments\"></div></section></div>
<div class=\"footer\"><span id=\"status\">尚未确认</span><button id=\"confirm\">确认整页并下载标注</button></div></main>
<script>
const review = {serialized};
const byId = id => document.getElementById(id);
const escaped = value => String(value ?? '').replace(/[&<>\"]/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[char]));
byId('title').textContent = `CER 页审校 · 第 ${{review.page_number}} 页`;
const flagged = review.segments.filter(s => s.review_flags.length);
const unmatched = review.unmatched_independent_block_ids?.length ?? 0;
byId('summary').innerHTML = `<span class=\"badge\">${{review.segments.length}} 个可编辑块</span><span class=\"badge flag\">${{flagged.length}} 个需关注</span>${{unmatched ? `<span class=\"badge flag\">${{unmatched}} 条独立 OCR 疑似漏行</span>` : ''}}`;
if (review.source_image) {{ const img=document.createElement('img'); img.src=review.source_image; img.alt='第'+review.page_number+'页原图'; byId('source').append(img); }} else {{ byId('source').innerHTML='<div class=\"empty-source\">未提供源 PDF。请用 <code>cer-review --source-pdf</code> 生成带原图的审校包。</div>'; }}
byId('segments').innerHTML = review.segments.map((s, index) => {{ const attention=s.review_flags.length ? ' attention' : ''; const flags=s.review_flags.map(flag => `<span class=\"badge flag\">${{escaped(flag)}}</span>`).join(''); const secondary=s.review_flags.includes('ocr_disagreement') ? `<div class=\"secondary\">独立 OCR：${{escaped(s.independent_ocr_text)}}</div>` : ''; return `<div class=\"segment${{attention}}\"><label for=\"segment-${{index}}\"><span>#${{s.ordinal}} · ${{escaped(s.semantic_role || 'text')}}</span><span>${{flags}}</span></label><textarea id=\"segment-${{index}}\" data-index=\"${{index}}\">${{escaped(s.production_ocr_text)}}</textarea>${{secondary}}</div>`; }}).join('');
byId('confirm').addEventListener('click', () => {{ const completed = structuredClone(review); completed.page_confirmed = true; completed.reviewed_at = new Date().toISOString(); completed.segments.forEach((segment,index) => {{ segment.reference_text = byId('segment-'+index).value; delete segment.production_ocr_text; delete segment.independent_ocr_text; delete segment.review_flags; }}); const blob=new Blob([JSON.stringify(completed,null,2)],{{type:'application/json;charset=utf-8'}}); const link=document.createElement('a'); link.href=URL.createObjectURL(blob); link.download=`page-${{String(review.page_number).padStart(4,'0')}}.json`; link.click(); URL.revokeObjectURL(link.href); byId('status').textContent='已确认并下载；将 JSON 放到 CER 标注目录后运行质量门禁。'; }});
</script></html>"""


def write_cer_review_pages(
    manifest: RepresentativeManifest,
    output_directory: str | Path,
    *,
    source_pdf: str | Path | None = None,
    independent_ocr_path: str | Path | None = None,
    dpi: int = 144,
    low_confidence_threshold: float = 0.90,
) -> tuple[Path, ...]:
    """Generate one visual, one-click confirmation page for every CER sample.

    ``source_pdf`` is optional for dry runs, but a real review must include it:
    the approved reference is always checked against the rendered source page,
    never against either OCR result.
    """

    if not 0.0 <= low_confidence_threshold <= 1.0:
        raise ValueError("低置信度阈值必须介于 0 和 1 之间。")
    destination = Path(output_directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    independent = _load_independent_ocr(independent_ocr_path)
    rendered: dict[int, Path] = {}
    if source_pdf is not None:
        source = Path(source_pdf)
        if not source.is_file():
            raise VisualRegressionError(f"源 PDF 不存在：{source}")
        render_root = destination / "source-pages"
        for page in manifest.pages:
            (render_root / f"page-{page.page_number:04d}").mkdir(parents=True, exist_ok=True)
        for item in render_pages(
            source,
            page_indices=[page.page_number - 1 for page in manifest.pages],
            page_directory=lambda index: render_root / f"page-{index + 1:04d}",
            dpi=dpi,
        ):
            target = render_root / f"page-{item.page_index + 1:04d}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item.image_path), target)
            rendered[item.page_index + 1] = target
    outputs: list[Path] = []
    for page in manifest.pages:
        if not page.model_path or not page.model_path.is_file():
            raise VisualRegressionError(f"代表页 {page.page_number} 缺少 PageModel，无法生成页审校工具。")
        model = load_representative_page_model(page)
        image = rendered.get(page.page_number)
        image_ref = image.relative_to(destination).as_posix() if image else None
        payload = _page_review_payload(
            page,
            model,
            independent_text=independent.get(page.page_number, {}),
            low_confidence_threshold=low_confidence_threshold,
            source_image=image_ref,
        )
        output = destination / f"page-{page.page_number:04d}.html"
        output.write_text(_page_review_html(payload), encoding="utf-8")
        outputs.append(output)
    return tuple(outputs)


def run_representative_quality_gates(
    manifest: RepresentativeManifest,
    *,
    renderer: str | None = None,
    require_cer: bool = False,
) -> tuple[RepresentativeQualityReport, ...]:
    """Regenerate every baseline page and enforce visual/CER thresholds.

    Visual snapshots are approved render outputs, never OCR source text. CER is
    intentionally optional while manual transcripts are being added; requesting
    it fails closed for every page that lacks a transcript.
    """

    reports: list[RepresentativeQualityReport] = []
    failures: list[str] = []
    for page in manifest.pages:
        if not page.model_path or not page.model_path.is_file():
            raise VisualRegressionError(f"代表页 {page.page_number} 缺少 PageModel。")
        if not page.visual_baseline_path or not page.visual_baseline_path.is_file():
            raise VisualRegressionError(f"代表页 {page.page_number} 缺少视觉基线。")
        model = load_representative_page_model(page)
        with tempfile.TemporaryDirectory(prefix=f"pdf2word-representative-{page.page_number:04d}-") as temporary:
            work = Path(temporary)
            candidate = create_positioned_editable_docx([model], work / "candidate.docx")
            verify_golden_page(candidate, model, renderer=renderer)
            rendered = render_docx_to_png(candidate, work, renderer=renderer)
            visual = compare_rasters(page.visual_baseline_path, rendered)
        if visual.ssim < page.minimum_ssim or visual.mean_absolute_error > page.maximum_mae:
            failures.append(
                f"代表页 {page.page_number} 视觉回归失败：SSIM={visual.ssim:.4f}（阈值 {page.minimum_ssim:.4f}），"
                f"MAE={visual.mean_absolute_error:.3f}（阈值 {page.maximum_mae:.3f}）。"
            )
        cer: CharacterErrorRate | None = None
        if page.cer_annotation_path and page.cer_annotation_path.is_file():
            reference_text, block_ids = _load_cer_annotation(page.cer_annotation_path)
            if reference_text is not None:
                try:
                    cer = character_error_rate(reference_text, model_text_for_cer(model, block_ids))
                except ValueError as exc:
                    raise VisualRegressionError(f"代表页 {page.page_number} CER 标注无效：{exc}") from exc
                if cer.cer > page.maximum_cer:
                    failures.append(f"代表页 {page.page_number} CER 失败：{cer.cer:.4%}，阈值 {page.maximum_cer:.4%}。")
        elif require_cer:
            failures.append(f"代表页 {page.page_number} 缺少人工 CER 标注，无法通过 CER 门禁。")
        reports.append(RepresentativeQualityReport(page.page_number, visual.ssim, visual.mean_absolute_error, cer))
    if failures:
        raise VisualRegressionError("\n".join(failures))
    return tuple(reports)


def run_representative_word_regressions(
    manifest: RepresentativeManifest,
    output_directory: str | Path,
) -> tuple[RepresentativeWordReport, ...]:
    """Run the final Microsoft Word pagination gate for every selected page."""

    destination = Path(output_directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    reports: list[RepresentativeWordReport] = []
    for page in manifest.pages:
        if not page.model_path or not page.model_path.is_file() or not page.docx_path or not page.docx_path.is_file():
            raise VisualRegressionError(f"代表页 {page.page_number} 缺少 Word 实机验证工件。")
        model = load_representative_page_model(page)
        output_pdf = destination / f"page-{page.page_number:04d}.pdf"
        page_count = verify_with_microsoft_word(page.docx_path, model, output_pdf)
        reports.append(RepresentativeWordReport(page.page_number, output_pdf, page_count))
    return tuple(reports)
