"""Optional OCR capability detection and PaddleOCR boundary.

The core package intentionally imports no ML framework. This keeps PDF
preflight and ordinary text-layer conversion usable in a small installation
and makes model installation an explicit desktop setup step.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json

from .errors import OcrRequiredError
from .models import PageBlock, PageModel, PageSize, PdfKind


@dataclass(frozen=True, slots=True)
class OcrCapability:
    available: bool
    engine: str
    reason: str | None = None


def paddleocr_capability() -> OcrCapability:
    if importlib.util.find_spec("paddleocr") is None:
        return OcrCapability(
            available=False,
            engine="PaddleOCR PP-StructureV3",
            reason="未安装 paddleocr。请安装项目的 ocr 可选依赖并下载模型包。",
        )
    return OcrCapability(available=True, engine="PaddleOCR PP-StructureV3")


def create_paddle_pipeline(**options: Any) -> Any:
    """Create PP-StructureV3 lazily after the desktop model manager has verified assets."""

    capability = paddleocr_capability()
    if not capability.available:
        raise OcrRequiredError(capability.reason or "PaddleOCR 不可用。")
    from paddleocr import PPStructureV3  # type: ignore[import-not-found]

    return PPStructureV3(**options)


def page_model_from_paddle_result(
    raw: Mapping[str, Any],
    *,
    page_index: int,
    size: PageSize,
    source_type: PdfKind,
) -> PageModel:
    """Normalize PP-StructureV3 JSON without leaking Paddle types downstream.

    Paddle's output fields have evolved between releases.  The adapter therefore
    accepts both the documented names and conservative fallbacks, retaining an
    explicit warning whenever a region cannot be placed faithfully.
    """

    # PaddleOCR 3.7 serializes its result beneath ``res`` while earlier
    # examples expose the same fields at the top level.
    payload = raw.get("res") if isinstance(raw.get("res"), Mapping) else raw
    regions = payload.get("parsing_res_list") or payload.get("layout_res") or []
    if not isinstance(regions, list):
        regions = []
    blocks: list[PageBlock] = []
    warnings: list[str] = []
    for order, region in enumerate(regions):
        if not isinstance(region, Mapping):
            warnings.append(f"忽略了第 {order + 1} 个无法解析的 OCR 区域。")
            continue
        bbox_value = region.get("block_bbox") or region.get("bbox") or region.get("coordinate")
        if not isinstance(bbox_value, (list, tuple)) or len(bbox_value) < 4:
            warnings.append(f"OCR 区域 {order + 1} 缺少坐标，未进入可编辑重建。")
            continue
        try:
            bbox = tuple(float(value) for value in bbox_value[:4])
        except (TypeError, ValueError):
            warnings.append(f"OCR 区域 {order + 1} 坐标无效，未进入可编辑重建。")
            continue
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            warnings.append(f"OCR 区域 {order + 1} 坐标范围无效，未进入可编辑重建。")
            continue
        confidence_value = region.get("confidence", region.get("score"))
        try:
            confidence = float(confidence_value) if confidence_value is not None else None
        except (TypeError, ValueError):
            confidence = None
        text = region.get("block_content", region.get("text", region.get("content")))
        order_value = region.get("block_order", order)
        try:
            reading_order = int(order_value) if order_value is not None else order
        except (TypeError, ValueError):
            reading_order = order
        blocks.append(
            PageBlock(
                block_id=str(region.get("block_id", f"p{page_index + 1}-b{order + 1}")),
                block_type=str(region.get("block_label", region.get("label", "unknown"))),
                bbox=bbox,
                z_index=order,
                reading_order=reading_order,
                confidence=confidence,
                text=str(text) if text is not None else None,
                style={"ocr_engine": "PaddleOCR PP-StructureV3"},
            )
        )
    if not blocks:
        warnings.append("未发现可用于重建的 OCR 版面区域。")
    return PageModel(
        schema_version=1,
        page_index=page_index,
        size=size,
        source_type=source_type,
        blocks=blocks,
        warnings=warnings,
    )


def predict_page_model(
    pipeline: Any,
    image_path: str | Path,
    *,
    page_index: int,
    size: PageSize,
    source_type: PdfKind,
    raw_output_path: str | Path | None = None,
    native_word_output_dir: str | Path | None = None,
) -> PageModel:
    """Run one rendered PDF page through Paddle and return the normalized model."""

    results = pipeline.predict(input=str(image_path))
    result = next(iter(results), None)
    if result is None:
        raise OcrRequiredError("PaddleOCR 没有返回识别结果。")
    raw = getattr(result, "json", result)
    if callable(raw):
        raw = raw()
    if not isinstance(raw, Mapping):
        raise OcrRequiredError("PaddleOCR 返回了无法解析的识别结果。")
    if raw_output_path is not None:
        destination = Path(raw_output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if native_word_output_dir is not None:
        destination = Path(native_word_output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        save_to_word = getattr(result, "save_to_word", None)
        if not callable(save_to_word):
            raise OcrRequiredError("当前 PaddleOCR 结果不支持原生 Word 导出。")
        save_to_word(str(destination))
    return page_model_from_paddle_result(
        raw,
        page_index=page_index,
        size=size,
        source_type=source_type,
    )


def write_page_model(model: PageModel, output_path: str | Path) -> Path:
    """Persist a portable PageModel checkpoint with UTF-8 Chinese text intact."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return destination
