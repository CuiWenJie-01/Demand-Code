"""Optional OCR capability detection and PaddleOCR boundary.

The core package intentionally imports no ML framework. This keeps PDF
preflight and ordinary text-layer conversion usable in a small installation
and makes model installation an explicit desktop setup step.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from .errors import OcrRequiredError
from .conflicts import force_full_page_fallback, resolve_page_model_conflicts
from .layout_profiles import CN_EXAM_QUESTION_V1
from .models import PAGE_MODEL_SCHEMA_VERSION, PageBlock, PageModel, PageSize, PdfKind


QUESTION_HEADING_RE = CN_EXAM_QUESTION_V1.question_heading_pattern


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


class FocusedOcrPipelineCache:
    """Lazily create the cropped-text OCR model once for one conversion job."""

    def __init__(self, **options: Any) -> None:
        self._options = options
        self._pipeline: Any | None = None

    def get(self) -> Any:
        if self._pipeline is None:
            self._pipeline = _focused_text_ocr_pipeline(**self._options)
        return self._pipeline


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
                source="PaddleOCR layout",
            )
        )
    if not blocks:
        warnings.append("未发现可用于重建的 OCR 版面区域。")
    blocks = _replace_text_regions_with_ocr_lines(blocks, payload, warnings)
    blocks = _combine_talk_image_with_label(blocks)
    blocks = _build_editable_page_sidebar(blocks)
    return PageModel(
        schema_version=PAGE_MODEL_SCHEMA_VERSION,
        page_index=page_index,
        size=size,
        source_type=source_type,
        source_image_width_px=_positive_int(payload.get("width")),
        source_image_height_px=_positive_int(payload.get("height")),
        blocks=blocks,
        warnings=warnings,
    )


def _replace_text_regions_with_ocr_lines(
    layout_blocks: list[PageBlock], payload: Mapping[str, Any], warnings: list[str]
) -> list[PageBlock]:
    """Use line-level OCR coordinates for textual layout regions when present."""

    ocr_result = payload.get("overall_ocr_res")
    if not isinstance(ocr_result, Mapping):
        return layout_blocks
    texts = ocr_result.get("rec_texts")
    boxes = ocr_result.get("rec_boxes")
    scores = ocr_result.get("rec_scores")
    if not isinstance(texts, list) or not isinstance(boxes, list) or len(texts) != len(boxes):
        return layout_blocks

    candidates: list[tuple[int, str, tuple[float, float, float, float], float | None]] = []
    for index, (text, box) in enumerate(zip(texts, boxes, strict=True)):
        if not isinstance(box, (list, tuple)) or len(box) < 4 or not str(text).strip():
            continue
        try:
            bbox = tuple(float(value) for value in box[:4])
        except (TypeError, ValueError):
            continue
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        score_value = scores[index] if isinstance(scores, list) and index < len(scores) else None
        try:
            score = float(score_value) if score_value is not None else None
        except (TypeError, ValueError):
            score = None
        candidates.append((index, str(text).strip(), bbox, score))

    if not candidates:
        return layout_blocks
    line_blocks: dict[str, list[PageBlock]] = {}
    suppressed_layout_ids: set[str] = set()
    callout_continuation = False
    for layout_index, layout in enumerate(layout_blocks):
        block_type = layout.block_type.lower()
        if block_type == "text":
            intro_after_table = layout_index > 0 and layout_blocks[layout_index - 1].block_type.lower() == "table"
            next_layout = layout_blocks[layout_index + 1] if layout_index + 1 < len(layout_blocks) else None
            solution_before_answer = bool(
                next_layout is not None
                and next_layout.block_type.lower() == "paragraph_title"
                and "谈答案" in (next_layout.text or "")
            )
            question_context = any(
                _candidate_is_in_layout(bbox, layout.bbox) and QUESTION_HEADING_RE.match(text)
                for _, text, bbox, _ in candidates
            )
            marker = _talk_marker_for_text_layout(layout, candidates)
            if marker is None:
                marker = _missing_talk_callout_line(layout, layout_blocks[max(0, layout_index - 3) : layout_index])
            if marker is not None:
                adjacent_badge = _adjacent_talk_badge(layout, layout_blocks, marker=marker)
                if adjacent_badge is not None:
                    suppressed_layout_ids.add(adjacent_badge.block_id)
                    marker.bbox = adjacent_badge.bbox
                    marker.z_index = min(marker.z_index, adjacent_badge.z_index)
                    marker.reading_order = min(marker.reading_order, adjacent_badge.reading_order)
            # A solution often occupies several consecutive layout blocks
            # (the A/B/C/D reasoning is split from its opening line).  Carry
            # the callout formatting through those blocks until the next
            # numbered question starts.
            if question_context:
                callout_continuation = False
            if marker is not None:
                callout_continuation = True
            lines: list[PageBlock] = []
            if marker is not None:
                lines.append(marker)
            for index, text, bbox, score in candidates:
                if not _candidate_is_in_layout(bbox, layout.bbox):
                    continue
                if marker is not None and _is_marker_candidate(text, bbox, marker):
                    continue
                line = _line_block(
                    layout,
                    index=index,
                    text=text,
                    bbox=bbox,
                    score=score,
                    marker=marker,
                    question_context=question_context,
                    callout_context=callout_continuation,
                    intro_context=intro_after_table,
                    solution_context=solution_before_answer,
                )
                if line is not None:
                    lines.append(line)
            lines.extend(_recovered_semantic_lines(layout, payload))
            if marker is not None:
                lines = _strip_callout_label_from_recovered(lines, marker)
                label = _editable_label_for_marker(marker)
                if label is not None:
                    lines.insert(1, label)
            lines = _prefer_focused_semantic_lines(lines)
            lines = _merge_adjacent_ocr_line_fragments(lines)
            layout_center_y = (layout.bbox[1] + layout.bbox[3]) / 2
            has_external_answer_blank = any(
                _is_answer_blank_candidate(text)
                and not _candidate_is_in_layout(bbox, layout.bbox)
                and abs(((bbox[1] + bbox[3]) / 2) - layout_center_y) <= 50
                for _, text, bbox, _ in candidates
            )
            answer_anchor = _nearest_preceding_answer_geometry(layout, candidates)
            lines = _restore_missing_answer_blank(
                lines,
                layout,
                has_external_answer_blank=has_external_answer_blank,
                answer_anchor_left=answer_anchor[0] if answer_anchor is not None else None,
                answer_anchor_gap=answer_anchor[1] if answer_anchor is not None else None,
                page_width_px=_positive_int(payload.get("width")),
            )
            index_lines = [
                line
                for line in lines
                if line.style.get("semantic_role") == "callout_index"
                or re.match(r"^易(?:错|考)指数", line.text or "")
            ]
            if index_lines:
                for index_line in index_lines:
                    index_line.text = _normalize_index_text(index_line.text or "")
                    index_line.style.update(
                        {
                            "semantic_role": "callout_index",
                            "font_size_pt": 8.0,
                            "font_color": "EF168B",
                            "source": "editable OCR index text",
                        }
                    )
                    index_line.style.pop("justify_to_bbox", None)
                adjacent_image = next(
                    (
                        candidate
                        for candidate in layout_blocks
                        if candidate.block_type.lower() == "image"
                        and abs(((candidate.bbox[1] + candidate.bbox[3]) / 2) - ((index_lines[0].bbox[1] + index_lines[0].bbox[3]) / 2)) <= 45
                        and candidate.bbox[2] <= index_lines[0].bbox[0]
                    ),
                    None,
                )
                label_left = (
                    adjacent_image.bbox[2] + CN_EXAM_QUESTION_V1.callout_label_gap_px
                    if adjacent_image is not None
                    else layout.bbox[0]
                )
                label = _talk_index_label(layout, label_left=label_left, first_index_left=index_lines[0].bbox[0])
                if label is not None:
                    lines.insert(0, label)
                    if adjacent_image is not None:
                        adjacent_image.block_type = "talk_badge_image"
                        adjacent_image.text = None
            if lines:
                line_blocks[layout.block_id] = lines
        elif block_type == "paragraph_title":
            adjacent_badge = _preceding_talk_badge(layout_index, layout_blocks)
            label_left = (
                adjacent_badge.bbox[2] + CN_EXAM_QUESTION_V1.callout_label_gap_px
                if adjacent_badge is not None
                else layout.bbox[0]
            )
            index_lines = _talk_index_blocks(layout, candidates, label_left=label_left)
            if index_lines:
                line_blocks[layout.block_id] = index_lines
                if adjacent_badge is not None:
                    adjacent_badge.block_type = "talk_badge_image"
                    adjacent_badge.text = None
            else:
                answer = _talk_answer_blocks(layout, candidates)
                if answer:
                    line_blocks[layout.block_id] = answer
        elif block_type == "footer" and "指数" in (layout.text or ""):
            adjacent_badge = _preceding_talk_badge(layout_index, layout_blocks)
            label_left = (
                adjacent_badge.bbox[2] + CN_EXAM_QUESTION_V1.callout_label_gap_px
                if adjacent_badge is not None
                else layout.bbox[0]
            )
            index_lines = _talk_index_blocks(layout, candidates, label_left=label_left)
            if index_lines:
                line_blocks[layout.block_id] = index_lines
                if adjacent_badge is not None:
                    adjacent_badge.block_type = "talk_badge_image"
                    adjacent_badge.text = None

    if not line_blocks:
        return layout_blocks
    normalized: list[PageBlock] = []
    for layout in layout_blocks:
        if layout.block_id in suppressed_layout_ids:
            continue
        lines = line_blocks.get(layout.block_id)
        if lines is not None:
            normalized.extend(lines)
        else:
            normalized.append(layout)
    warnings.append(f"已使用 {sum(len(value) for value in line_blocks.values())} 条行级 OCR 坐标重建正文。")
    return normalized


def _prefer_focused_semantic_lines(lines: list[PageBlock]) -> list[PageBlock]:
    """Replace a near-identical full-page OCR line with its focused recovery.

    A focused retry is more reliable beside a decorative callout tag. Keeping
    both results creates two editable boxes on the same baseline, so prefer the
    focused line only when its text and vertical position agree with the first
    pass.
    """

    focused = [line for line in lines if line.style.get("source") == "focused PaddleOCR line"]
    duplicates: set[str] = set()
    for recovered in focused:
        recovered_center = (recovered.bbox[1] + recovered.bbox[3]) / 2
        for line in lines:
            if line is recovered or line.style.get("source") == "focused PaddleOCR line":
                continue
            line_center = (line.bbox[1] + line.bbox[3]) / 2
            if line.text == recovered.text and abs(line_center - recovered_center) <= 12:
                duplicates.add(line.block_id)
    return [line for line in lines if line.block_id not in duplicates]


def _strip_callout_label_from_recovered(lines: list[PageBlock], marker: PageBlock) -> list[PageBlock]:
    """Keep ``谈解析``/``谈提示`` artwork out of focused editable OCR text."""

    result: list[PageBlock] = []
    for line in lines:
        if line.style.get("source") != "focused PaddleOCR line" or not line.text:
            result.append(line)
            continue
        label_match = re.match(r"^(解析|答案|提示)\s*(?P<body>.+)$", line.text)
        if label_match is None:
            result.append(line)
            continue
        body = label_match.group("body").strip()
        if not body:
            continue
        _, top, right, bottom = line.bbox
        line.text = body
        line.bbox = (marker.bbox[2] + 15, top, right, bottom)
        line.style.update(CN_EXAM_QUESTION_V1.right_aligned_text_style("callout_body"))
        result.append(line)
    return result


def _build_editable_page_sidebar(blocks: list[PageBlock]) -> list[PageBlock]:
    """Turn a standard chapter sidebar into editable text plus a vector rule.

    Each CJK chapter character is positioned separately by the Word renderer,
    avoiding automatic vertical-text spacing differences between Word and
    LibreOffice. The small pink page rule is represented as a VML rectangle.
    """

    chapter = next(
        (
            block
            for block in blocks
            if block.block_type.lower() == "aside_text" and re.search(r"第.+章.+", block.text or "")
        ),
        None,
    )
    if chapter is None:
        return blocks
    page_number = next(
        (
            block
            for block in blocks
            if block.block_type.lower() == "number"
            and re.fullmatch(r"\d{3,4}", (block.text or "").strip())
            and block.bbox[1] >= chapter.bbox[3]
        ),
        None,
    )
    if page_number is None:
        return blocks
    chapter_text = PageBlock(
        block_id=f"{chapter.block_id}-sidebar-text",
        block_type="sidebar_vertical_text",
        bbox=chapter.bbox,
        z_index=min(chapter.z_index, page_number.z_index),
        reading_order=min(chapter.reading_order, page_number.reading_order),
        text=(chapter.text or "").replace(" ", ""),
        style={"semantic_role": "sidebar_vertical_text", "font_size_pt": 8.5, "font_color": "555555"},
    )
    page_digits = (page_number.text or "").strip()
    # The narrow page-number box can capture the first sidebar character as a
    # fourth digit (for example source ``115`` becomes ``1151``). This book's
    # running page numbers are three digits, so keep the measured first three.
    if len(page_digits) == 4:
        page_digits = page_digits[:3]
    page_text = PageBlock(
        block_id=f"{page_number.block_id}-sidebar-page-number",
        block_type="sidebar_page_number",
        # Give the editable run enough room for all three ASCII digits without
        # changing the visual page-number anchor or the nearby pink rule.
        bbox=CN_EXAM_QUESTION_V1.sidebar_page_number_bbox(page_number.bbox),
        z_index=page_number.z_index,
        reading_order=page_number.reading_order,
        text=page_digits,
        style={"semantic_role": "sidebar_page_number", "font_size_pt": 8.5, "font_color": "222222"},
    )
    rule = PageBlock(
        block_id=f"{page_number.block_id}-sidebar-rule",
        block_type="sidebar_accent_rule",
        bbox=CN_EXAM_QUESTION_V1.sidebar_rule_bbox(page_number.bbox),
        z_index=page_number.z_index + 1,
        reading_order=page_number.reading_order + 1,
        style={"semantic_role": "sidebar_accent_rule", "fill_color": "EF168B"},
    )
    result: list[PageBlock] = []
    for block in blocks:
        if block.block_id == chapter.block_id:
            result.extend((chapter_text, page_text, rule))
        elif block.block_id != page_number.block_id:
            result.append(block)
    return result


def _combine_talk_image_with_label(blocks: list[PageBlock]) -> list[PageBlock]:
    """Split a callout into badge artwork, editable label and editable value."""

    labels = ("解析", "答案", "提示")
    removed: set[str] = set()
    replacements: list[PageBlock] = []
    for text_block in blocks:
        if text_block.block_type not in {"text_line", "paragraph_title"} or not text_block.text:
            continue
        if text_block.style.get("semantic_role") == "callout_label":
            continue
        if re.match(r"^易(?:错|考)指数", text_block.text):
            text_block.style.update(
                {
                    "semantic_role": "callout_index",
                    "font_size_pt": 8.0,
                    "font_color": "EF168B",
                }
            )
            text_block.style.pop("justify_to_bbox", None)
        match = re.match(r"^(?P<talk>谈)?(?P<label>解析|答案|提示)\s*(?P<body>.*)$", text_block.text)
        # PP-Structure occasionally reads the first glyph of ``答案 B`` as
        # ``名B``.  This is only safe to repair when it is immediately beside
        # the publication's round pink badge; an arbitrary title beginning
        # with ``名`` must remain untouched.
        mistaken_answer = re.fullmatch(r"名\s*(?P<body>[A-D])", text_block.text.strip())
        if match is None and mistaken_answer is not None:
            nearby_badge = next(
                (
                    candidate
                    for candidate in blocks
                    if candidate is not text_block
                    and candidate.block_id not in removed
                    and _is_small_talk_badge(candidate)
                    and candidate.bbox[2] <= text_block.bbox[0] + 8
                    and 0 <= text_block.bbox[0] - candidate.bbox[2] <= 18
                    and candidate.bbox[1] <= text_block.bbox[3]
                    and candidate.bbox[3] >= text_block.bbox[1]
                ),
                None,
            )
            if nearby_badge is not None:
                match = re.match(
                    r"^(?P<talk>)?(?P<label>答案)\s*(?P<body>[A-D])$",
                    f"答案{mistaken_answer.group('body')}",
                )
        if match is None:
            continue
        label = match.group("label")
        has_inline_badge = bool(match.group("talk"))
        body_text = match.group("body").strip()
        left, top, right, bottom = text_block.bbox
        badge = next(
            (
                candidate
                for candidate in blocks
                if candidate is not text_block
                and candidate.block_id not in removed
                and _is_small_talk_badge(candidate)
                and candidate.bbox[2] <= text_block.bbox[0] + 8
                and 0 <= text_block.bbox[0] - candidate.bbox[2] <= 18
                and candidate.bbox[1] <= text_block.bbox[3]
                and candidate.bbox[3] >= text_block.bbox[1]
            ),
            None,
        )
        if badge is None and has_inline_badge:
            badge_right = min(right, left + CN_EXAM_QUESTION_V1.talk_badge_width_px)
            badge = PageBlock(
                block_id=f"{text_block.block_id}-inline-talk-badge",
                block_type="talk_badge_image",
                bbox=(left, top, badge_right, bottom),
                z_index=text_block.z_index - 2,
                reading_order=text_block.reading_order - 2,
                style={"semantic_role": "talk_badge_image", "source": "inline source talk badge"},
            )
            replacements.append(badge)
        if badge is None:
            continue
        badge.block_type = "talk_badge_image"
        badge.text = None
        badge.style.update({"semantic_role": "talk_badge_image", "source": "source talk badge"})

        label_left = max(badge.bbox[2] + CN_EXAM_QUESTION_V1.callout_label_gap_px, left if not has_inline_badge else badge.bbox[2])
        label_top = top + 12 if has_inline_badge else top
        if body_text:
            label_limit = right - CN_EXAM_QUESTION_V1.callout_content_gap_px - 16
            label_right = min(label_limit, label_left + CN_EXAM_QUESTION_V1.callout_label_width_px)
        else:
            label_right = label_left + CN_EXAM_QUESTION_V1.callout_label_width_px
        label_block = PageBlock(
            block_id=f"{text_block.block_id}-editable-{label}-label",
            block_type="text_line",
            bbox=(label_left, label_top, label_right, bottom),
            z_index=text_block.z_index - 1,
            reading_order=text_block.reading_order - 1,
            text=label,
            style={
                "semantic_role": "callout_label",
                "font_size_pt": 8.0,
                "font_color": "EF168B",
                "source": "editable label beside source talk badge",
            },
        )
        replacements.append(label_block)
        if not body_text:
            removed.add(text_block.block_id)
            following_body = next(
                (
                    candidate
                    for candidate in blocks
                    if candidate is not text_block
                    and candidate.block_type == "text_line"
                    and candidate.text
                    and candidate.bbox[0] >= label_right + CN_EXAM_QUESTION_V1.callout_content_gap_px
                    and label_top - 8 <= candidate.bbox[1] <= bottom + 64
                ),
                None,
            )
            if following_body is not None:
                following_body.style.update(CN_EXAM_QUESTION_V1.right_aligned_text_style("callout_body"))
            continue
        body_left = label_right + CN_EXAM_QUESTION_V1.callout_content_gap_px
        if body_left >= right:
            replacements.pop()
            continue
        text_block.text = body_text
        text_block.block_type = "text_line"
        text_block.asset_path = None
        text_block.bbox = (body_left, label_top, right, bottom)
        if label == "答案":
            text_block.style.update(
                {
                    "semantic_role": "callout_answer",
                    "source": "PaddleOCR answer after combined talk tag",
                }
            )
        else:
            text_block.style.update(CN_EXAM_QUESTION_V1.right_aligned_text_style("callout_body"))
    if not replacements:
        return blocks
    return [block for block in blocks if block.block_id not in removed] + replacements


def _candidate_is_in_layout(
    bbox: tuple[float, float, float, float], layout_bbox: tuple[float, float, float, float]
) -> bool:
    left, top, right, bottom = layout_bbox
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return left <= center_x <= right and top <= center_y <= bottom


def _is_small_talk_badge(block: PageBlock) -> bool:
    """Return whether a layout block is the publication's round pink badge."""

    width = block.bbox[2] - block.bbox[0]
    height = block.bbox[3] - block.bbox[1]
    return (
        block.block_type.lower() in {"image", "header", "footer", "talk_badge_image", "talk_callout_tag_image"}
        and width <= 85
        and height <= 75
        # A badge is sometimes stored as a small source image with a trailing
        # OCR artefact (for example ``谈I``).  Its geometry and leading glyph
        # still identify it unambiguously.  Treating it as the badge also
        # suppresses the duplicate image after the adjacent editable label is
        # rebuilt.
        and (
            (block.text or "").strip() in {"", "谈", ",", "，"}
            or (block.text or "").strip().startswith("谈")
        )
    )


def _preceding_talk_badge(layout_index: int, layout_blocks: list[PageBlock]) -> PageBlock | None:
    if layout_index <= 0:
        return None
    layout = layout_blocks[layout_index]
    for candidate in reversed(layout_blocks[max(0, layout_index - 2) : layout_index]):
        if not _is_small_talk_badge(candidate):
            continue
        if candidate.bbox[2] > layout.bbox[0] + 12:
            continue
        if candidate.bbox[3] < layout.bbox[1] - 30 or candidate.bbox[1] > layout.bbox[3] + 30:
            continue
        return candidate
    return None


def _adjacent_talk_badge(
    layout: PageBlock,
    layout_blocks: list[PageBlock],
    *,
    marker: PageBlock,
) -> PageBlock | None:
    """Reuse a layout-detected badge instead of emitting a duplicate crop."""

    marker_center_y = (marker.bbox[1] + marker.bbox[3]) / 2
    matches = [
        candidate
        for candidate in layout_blocks
        if _is_small_talk_badge(candidate)
        and candidate.bbox[2] <= layout.bbox[0] + 12
        and abs(((candidate.bbox[1] + candidate.bbox[3]) / 2) - marker_center_y) <= 24
    ]
    return min(matches, key=lambda item: abs(item.bbox[2] - layout.bbox[0]), default=None)


def _editable_label_for_marker(marker: PageBlock) -> PageBlock | None:
    label = marker.style.get("callout_label")
    if label not in {"解析", "答案", "提示"}:
        return None
    bbox_value = marker.style.get("callout_label_bbox")
    if isinstance(bbox_value, (list, tuple)) and len(bbox_value) == 4:
        try:
            bbox = tuple(float(value) for value in bbox_value)
        except (TypeError, ValueError):
            bbox = ()
    else:
        bbox = ()
    if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        left = marker.bbox[2] + CN_EXAM_QUESTION_V1.callout_label_gap_px
        top = marker.bbox[1] + 12
        bbox = (left, top, left + CN_EXAM_QUESTION_V1.callout_label_width_px, marker.bbox[3])
    return PageBlock(
        block_id=f"{marker.block_id}-editable-label",
        block_type="text_line",
        bbox=bbox,
        z_index=marker.z_index + 1,
        reading_order=marker.reading_order + 1,
        text=str(label),
        style={
            "semantic_role": "callout_label",
            "font_size_pt": 8.0,
            "font_color": "EF168B",
            "source": "editable label beside source talk badge",
        },
    )


def _nearest_preceding_answer_geometry(
    layout: PageBlock,
    candidates: list[tuple[int, str, tuple[float, float, float, float], float | None]],
) -> tuple[float, float] | None:
    """Use the previous question's right-column answer blank as an anchor."""

    preceding = [
        (text.strip(), bbox)
        for _, text, bbox, _ in candidates
        if _is_answer_blank_candidate(text)
        and bbox[0] > layout.bbox[2] + 20
        and ((bbox[1] + bbox[3]) / 2) <= layout.bbox[3] + 60
    ]
    if not preceding:
        return None
    latest_y = max((bbox[1] + bbox[3]) / 2 for _, bbox in preceding)
    baseline = [(text, bbox) for text, bbox in preceding if abs(((bbox[1] + bbox[3]) / 2) - latest_y) <= 12]
    combined = next((bbox for text, bbox in baseline if re.fullmatch(r"[（(]\s*[）)]", text)), None)
    if combined is not None:
        return combined[0], CN_EXAM_QUESTION_V1.answer_pair_gap_px
    opening = next((bbox for text, bbox in baseline if text in {"(", "（"}), None)
    closing = next((bbox for text, bbox in baseline if text in {")", "）"}), None)
    if opening is None:
        return None
    gap = closing[0] - opening[0] if closing is not None else CN_EXAM_QUESTION_V1.answer_pair_gap_px
    return opening[0], gap


def _is_answer_blank_candidate(text: str) -> bool:
    """Return whether an OCR token represents one or both answer brackets."""

    return re.fullmatch(r"[（(]\s*[）)]", text.strip()) is not None or text.strip() in {"(", ")", "（", "）"}


def _talk_index_blocks(
    layout: PageBlock,
    candidates: list[tuple[int, str, tuple[float, float, float, float], float | None]],
    *,
    label_left: float,
) -> list[PageBlock] | None:
    """Keep the badge as artwork and rebuild the index row as editable text."""

    matches = [
        (index, text, bbox, score)
        for index, text, bbox, score in candidates
        if _candidate_is_in_layout(bbox, layout.bbox)
        and any(label in text for label in CN_EXAM_QUESTION_V1.rating_labels)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: item[2][0])
    label = _talk_index_label(layout, label_left=label_left, first_index_left=matches[0][2][0])
    if label is None:
        return None
    style = label.style
    blocks = [label]
    for index, text, bbox, score in matches:
        blocks.append(
            PageBlock(
                block_id=f"{layout.block_id}-index-{index + 1}",
                block_type="text_line",
                bbox=bbox,
                z_index=layout.z_index * 100 + index,
                reading_order=layout.reading_order * 100 + index,
                confidence=score,
                text=_normalize_index_text(text),
                style={**style, "source": "editable OCR index text"},
            )
        )
    return blocks


def _talk_index_label(layout: PageBlock, *, label_left: float, first_index_left: float) -> PageBlock | None:
    """Build editable ``指数`` text beside the retained round badge."""

    label_right = first_index_left - 12
    if label_right - label_left < 48:
        return None
    style = {
        **layout.style,
        "semantic_role": "callout_index",
        "font_size_pt": 8.0,
        "font_color": "EF168B",
        "source": "editable talk index label",
    }
    style.pop("justify_to_bbox", None)
    return PageBlock(
        block_id=f"{layout.block_id}-talk-index-label",
        block_type="text_line",
        bbox=(label_left, layout.bbox[1], label_right, layout.bbox[3]),
        z_index=layout.z_index * 100 - 1,
        reading_order=layout.reading_order * 100 - 1,
        text="指数",
        style=style,
    )


def _normalize_index_text(text: str) -> str:
    """Normalize OCR star variants to an editable five-character rating."""

    compact = "".join(text.split()).replace("⭐", "★")
    match = re.search(r"(?P<label>易(?:错|考)指数)(?P<stars>[★☆]*)", compact)
    if match is None:
        return compact
    stars = match.group("stars")[:5]
    if len(stars) < 5:
        stars += "☆" * (5 - len(stars))
    return f"{match.group('label')}{stars}"


def _talk_marker_for_text_layout(
    layout: PageBlock,
    candidates: list[tuple[int, str, tuple[float, float, float, float], float | None]],
) -> PageBlock | None:
    """Find the pink ``谈`` badge that PP-Structure often excludes from text.

    The badge overlaps the top edge of the adjacent text region, so a strict
    centre-in-region test treats it as normal black text or drops it entirely.
    Retaining it as a tiny image preserves the decorative glyph, while the
    following editable line receives an inline pink label in the DOCX writer.
    """

    left, top, _, _ = layout.bbox
    for index, text, bbox, _ in candidates:
        token = text.strip()
        # ``M`` is a frequent PP-Structure misread for the round pink badge
        # on this publication.  Treat it like the other one-character badge
        # substitutes rather than leaving the following ``提示`` text as a
        # black, vertically split Word textbox.
        if token not in {"谈", "S", "5", "M"} or len(token) > 1:
            continue
        candidate_left, candidate_top, candidate_right, candidate_bottom = bbox
        if not (left <= candidate_left <= left + 105):
            continue
        if not (candidate_bottom >= top - 14 and candidate_top <= top + 12):
            continue
        # A large recognised “谈” is the whole badge. When the badge is
        # misrecognised as a tiny S/5, PP-Structure has usually missed the
        # complete callout heading and its first line. Keep *only* the tag as
        # an image and request a focused second OCR pass for the body text.
        if token == "谈" and candidate_bottom - candidate_top >= 22:
            # OCR often joins the first pink label glyph to the badge's box.
            # Retain the measured left edge but cap the image to the known
            # round-badge width, otherwise a clipped ``解``/``答`` is rendered
            # immediately before the editable label.
            marker_bbox = (
                candidate_left,
                candidate_top,
                min(candidate_right, candidate_left + CN_EXAM_QUESTION_V1.talk_badge_width_px),
                candidate_bottom,
            )
            marker_type = "talk_badge_image"
        else:
            marker_bbox = (
                max(0.0, candidate_left - 26),
                max(0.0, candidate_top - 3),
                max(0.0, candidate_left - 26) + CN_EXAM_QUESTION_V1.talk_badge_width_px,
                candidate_bottom + 23,
            )
            marker_type = "talk_badge_image"
        style: dict[str, Any] = {**layout.style, "semantic_role": marker_type, "layout_block_id": layout.block_id}
        if token != "谈" or candidate_bottom - candidate_top < 22:
            style["recovery_crop_bbox"] = [candidate_left + 86, layout.bbox[1], layout.bbox[2], candidate_bottom + 23]
        return PageBlock(
            block_id=f"{layout.block_id}-talk-marker-{index + 1}",
            block_type=marker_type,
            bbox=marker_bbox,
            z_index=layout.z_index * 100 - 1,
            reading_order=layout.reading_order * 100 - 1,
            style=style,
        )
    # In some scans PP-Structure loses the badge completely but preserves the
    # adjacent pink label as the first OCR token (``提示`` / ``解析``).  Build a
    # small source-image tag around that label so its colour and artwork are
    # retained, then let the normal line builder remove the label from the
    # editable black body.  This is deliberately based on a label's measured
    # coordinates, not an assumed page number or a fixed page crop.
    for index, text, bbox, _ in candidates:
        label_match = re.match(r"^(解析|答案|提示)", text.strip())
        if label_match is None:
            continue
        candidate_left, candidate_top, candidate_right, candidate_bottom = bbox
        if not (left <= candidate_left <= left + 120):
            continue
        if not (candidate_bottom >= top - 12 and candidate_top <= top + 20):
            continue
        label = label_match.group(1)
        label_remainder = text.strip()[label_match.end() :].lstrip()
        # A normal solution sentence can begin with “解析说明…”. Only treat a
        # recognised label-plus-text token as a missing pink badge when its
        # remainder has a callout-like opening; otherwise it is ordinary prose.
        if label_remainder and not re.match(r"^(本题|根据|由|设|正文|[A-D])", label_remainder):
            continue
        compact_text = "".join(text.split())
        label_right = min(
            candidate_right,
            candidate_left
            + (candidate_right - candidate_left) * len(label) / max(1, len(compact_text)),
        )
        marker_bbox = (
            max(0.0, candidate_left - 49),
            max(0.0, candidate_top - 13),
            max(0.0, candidate_left - 49) + CN_EXAM_QUESTION_V1.talk_badge_width_px,
            candidate_bottom + 13,
        )
        label_left = max(candidate_left, marker_bbox[2] + CN_EXAM_QUESTION_V1.callout_label_gap_px)
        return PageBlock(
            block_id=f"{layout.block_id}-talk-label-marker-{index + 1}",
            block_type="talk_badge_image",
            bbox=marker_bbox,
            z_index=layout.z_index * 100 - 1,
            reading_order=layout.reading_order * 100 - 1,
            style={
                **layout.style,
                "semantic_role": "talk_badge_image",
                "layout_block_id": layout.block_id,
                "callout_label": label,
                "callout_label_bbox": [
                    label_left,
                    candidate_top,
                    min(candidate_right, label_left + CN_EXAM_QUESTION_V1.callout_label_width_px),
                    candidate_bottom,
                ],
                "source": f"reconstructed talk {label} tag",
            },
        )
    return None


def _is_marker_candidate(text: str, bbox: tuple[float, float, float, float], marker: PageBlock) -> bool:
    if text.strip() not in {"谈", "S", "5", "M"}:
        return False
    left, top, right, bottom = marker.bbox
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return left <= center_x <= right and top <= center_y <= bottom


def _missing_talk_callout_line(layout: PageBlock, previous_blocks: list[PageBlock]) -> PageBlock | None:
    """Recover a missed badge and editable label from nearby semantic rows."""

    if not previous_blocks:
        return None
    # PP-Structure emits inline ``谈答案`` rows as either normal text or a
    # paragraph-title block.  Treat both forms as the same semantic anchor;
    # otherwise the following ``谈提示`` tag and its first prose line vanish
    # while the second line remains as an orphaned body block.
    answer_anchor = next(
        (
            block
            for block in reversed(previous_blocks)
            if (
                block.block_type.lower() in {"text", "paragraph_title"}
                and (block.text or "").startswith("谈答案")
            )
            or (
                block.block_type.lower() == "paragraph_title"
                and re.fullmatch(r"[A-D]", (block.text or "").strip()) is not None
                and block.bbox[2] - block.bbox[0] <= 160
            )
        ),
        None,
    )
    index_anchor = next((block for block in reversed(previous_blocks) if "指数" in (block.text or "")), None)
    semantic_anchor = answer_anchor or index_anchor
    if semantic_anchor is None:
        return None
    follows_answer = answer_anchor is not None
    previous_left = min(block.bbox[0] for block in previous_blocks)
    previous_bottom = semantic_anchor.bbox[3]
    _, layout_top, layout_right, layout_bottom = layout.bbox
    gap = layout_top - previous_bottom
    if not 18 <= gap <= 52:
        return None
    # After a ``谈答案`` row the next unlabelled prose block is the paper's
    # ``谈提示`` row. PP-Structure frequently misses its first line entirely;
    # recover just the black prose from a focused crop while retaining the
    # complete pink prompt tag as a source image.
    marker_top = layout_top - (5 if follows_answer else 12)
    marker_bottom = marker_top + 52
    # Start focused OCR after the editable label itself. The old whole-tag
    # fallback was 96 px wide; the rebuilt badge + label is wider, so keeping
    # the old 106 px crop leaks the final label glyph (for example ``析``)
    # into the recovered prose.
    crop_left = (
        previous_left
        + CN_EXAM_QUESTION_V1.talk_badge_width_px
        + CN_EXAM_QUESTION_V1.callout_label_gap_px
        + CN_EXAM_QUESTION_V1.callout_label_width_px
    )
    crop_top = layout_top - (7 if follows_answer else 12)
    crop_bottom = min(layout_bottom, layout_top + 42)
    return PageBlock(
        block_id=f"{layout.block_id}-missing-talk-callout",
        block_type="talk_badge_image",
        bbox=(previous_left, marker_top, previous_left + CN_EXAM_QUESTION_V1.talk_badge_width_px, marker_bottom),
        z_index=layout.z_index * 100 - 1,
        reading_order=layout.reading_order * 100 - 1,
        style={
            **layout.style,
            "semantic_role": "talk_badge_image",
            "layout_block_id": layout.block_id,
            "callout_label": "提示" if follows_answer else "解析",
            "callout_label_bbox": [
                previous_left + CN_EXAM_QUESTION_V1.talk_badge_width_px + CN_EXAM_QUESTION_V1.callout_label_gap_px,
                layout_top,
                previous_left
                + CN_EXAM_QUESTION_V1.talk_badge_width_px
                + CN_EXAM_QUESTION_V1.callout_label_gap_px
                + CN_EXAM_QUESTION_V1.callout_label_width_px,
                layout_top + 32,
            ],
            "recovery_crop_bbox": [crop_left, crop_top, layout_right, crop_bottom],
        },
    )


def _recovered_semantic_lines(layout: PageBlock, payload: Mapping[str, Any]) -> list[PageBlock]:
    """Load focused OCR results persisted beside the ordinary Paddle result."""

    recovered = payload.get("semantic_line_ocr")
    if not isinstance(recovered, list):
        return []
    lines: list[PageBlock] = []
    for index, item in enumerate(recovered):
        if not isinstance(item, Mapping) or str(item.get("layout_block_id")) != layout.block_id:
            continue
        text = str(item.get("text", "")).strip()
        bbox_value = item.get("bbox")
        if not text or not isinstance(bbox_value, (list, tuple)) or len(bbox_value) != 4:
            continue
        try:
            bbox = tuple(float(value) for value in bbox_value)
        except (TypeError, ValueError):
            continue
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        lines.append(
            PageBlock(
                block_id=f"{layout.block_id}-focused-ocr-{index + 1}",
                block_type="text_line",
                bbox=bbox,
                z_index=layout.z_index * 100 - 2 + index,
                reading_order=layout.reading_order * 100 - 2 + index,
                confidence=_as_float(item.get("score")),
                text=text,
                style={
                    **layout.style,
                    "source": "focused PaddleOCR line",
                    "semantic_role": "callout_body",
                    "justify_to_bbox": True,
                },
            )
        )
    return lines


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _line_block(
    layout: PageBlock,
    *,
    index: int,
    text: str,
    bbox: tuple[float, float, float, float],
    score: float | None,
    marker: PageBlock | None,
    question_context: bool,
    callout_context: bool,
    intro_context: bool,
    solution_context: bool,
) -> PageBlock | None:
    style: dict[str, Any] = {**layout.style, "source": "PaddleOCR line"}
    normalized_text = text
    question_match = QUESTION_HEADING_RE.match(normalized_text)
    if question_match:
        style.update(CN_EXAM_QUESTION_V1.question_heading_style(question_match))
    elif marker is not None or callout_context:
        label_match = re.match(r"^(解析|答案|提示)", normalized_text) if marker is not None else None
        if label_match is not None:
            label = label_match.group(1)
            marker.block_type = "talk_badge_image"
            marker.text = None
            marker.style.update(
                {
                    "semantic_role": "talk_badge_image",
                    "callout_label": label,
                    "source": "source talk badge with editable adjacent label",
                }
            )
            label_left = max(marker.bbox[2] + CN_EXAM_QUESTION_V1.callout_label_gap_px, bbox[0])
            label_right = label_left + CN_EXAM_QUESTION_V1.callout_label_width_px
            marker.style["callout_label_bbox"] = [label_left, bbox[1], label_right, bbox[3]]
            normalized_text = normalized_text[label_match.end() :].lstrip()
            # The coloured ``谈解析`` / ``谈提示`` tag is a source-image
            # fallback. Start the editable prose after a real coordinate gap,
            # rather than relying on spaces whose width varies by Word font.
            if label == "答案":
                bbox = (label_right + CN_EXAM_QUESTION_V1.callout_content_gap_px, bbox[1], bbox[2], bbox[3])
                style.update({"semantic_role": "callout_answer", "source": "PaddleOCR answer after talk tag"})
            else:
                bbox = (label_right + CN_EXAM_QUESTION_V1.callout_content_gap_px, bbox[1], bbox[2], bbox[3])
        elif marker is not None and bbox[1] <= marker.bbox[1] + 35 and bbox[0] < marker.bbox[2] + 24:
            # The badge and label are often detected in separate OCR boxes.
            # Move only the adjacent first prose line right of the full tag;
            # later continuation lines retain their source left edge.
            label_bbox = marker.style.get("callout_label_bbox")
            label_right = (
                float(label_bbox[2])
                if isinstance(label_bbox, (list, tuple)) and len(label_bbox) == 4
                else marker.bbox[2] + CN_EXAM_QUESTION_V1.callout_label_width_px
            )
            bbox = (label_right + CN_EXAM_QUESTION_V1.callout_content_gap_px, bbox[1], bbox[2], bbox[3])
        # Every line in the callout shares its source line box. The first line
        # starts after the tag; continuations retain their observed left edge,
        # but all use the same right-edge alignment rule.
        if style.get("semantic_role") != "callout_answer":
            style.update(CN_EXAM_QUESTION_V1.right_aligned_text_style("callout_body"))
        # Paddle can give a short continuation (for example ``洞察力。``) a
        # tightly cropped box.  At the source-to-Word scale that box is too
        # narrow for all CJK glyphs and Word stacks them vertically.  Provide
        # enough measured room for the actual characters while retaining the
        # profile's right-edge alignment contract.
        if label_match is None and len(normalized_text) <= 24:
            minimum_width = len(normalized_text) * 25.0
            if bbox[2] - bbox[0] < minimum_width:
                bbox = (bbox[0], bbox[1], bbox[0] + minimum_width, bbox[3])
    elif question_context:
        # Preserve the source line's observed right edge in Word as well.
        style.update(CN_EXAM_QUESTION_V1.right_aligned_text_style("question_body"))
    elif intro_context:
        # The short solution directly under a numeric table is ordinary
        # editable prose, but it shares the source page's measured right edge.
        style.update(CN_EXAM_QUESTION_V1.right_aligned_text_style("table_intro_body"))
    elif solution_context:
        # Explanation immediately preceding a ``谈答案`` row is a solution
        # paragraph, not an ordinary OCR line. Preserve the publication's
        # common right edge across all of its lines.
        style.update(CN_EXAM_QUESTION_V1.right_aligned_text_style("solution_body"))
        if len(normalized_text) <= 12:
            # LibreOffice's CJK fallback font is wider than the outline's
            # measured glyph boxes.  Give short closing sentences enough room
            # to remain on their observed single source line (for example
            # ``不符合①，排除。``) instead of wrapping their final character.
            minimum_width = len(normalized_text) * 36.0
            if bbox[2] - bbox[0] < minimum_width:
                bbox = (bbox[0], bbox[1], bbox[0] + minimum_width, bbox[3])
            # A standalone closing sentence (for example ``C项当选。``) is
            # compact in the source. Do not distribute its few glyphs merely
            # to reach the solution paragraph's right edge.
            style["semantic_role"] = "solution_short_body"
            style.pop("justify_to_bbox", None)
    # A trailing one-line judgement can be outside the layout region that
    # carries the preceding answer badge, so ``solution_context`` is not
    # always available.  Preserve a compact ``…排除。`` / ``…当选。`` line as
    # one line before Word sees its outline-derived width as a wrap point.
    if len(normalized_text) <= 12 and normalized_text.endswith(("排除。", "当选。")):
        minimum_width = len(normalized_text) * 36.0
        if bbox[2] - bbox[0] < minimum_width:
            bbox = (bbox[0], bbox[1], bbox[0] + minimum_width, bbox[3])
    # The same outline-to-Word metric difference affects short option
    # continuations such as ``常抱歉``.  Widen them locally rather than letting
    # the final glyph stack into an extra visual line.
    if 1 < len(normalized_text) <= 12 and re.search(r"[\u3400-\u9fff]", normalized_text):
        minimum_width = len(normalized_text) * 36.0
        if bbox[2] - bbox[0] < minimum_width:
            bbox = (bbox[0], bbox[1], bbox[0] + minimum_width, bbox[3])
    if not normalized_text or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        # A text candidate can fall under a decorative ``谈`` tag. Moving the
        # editable body to the tag's right edge may leave no valid source box;
        # omit that empty/invalid line instead of emitting a non-editable,
        # unrenderable PageModel block.
        return None
    if normalized_text in {"(", "（"}:
        normalized_text = "（"
        style["semantic_role"] = "answer_blank"
    elif normalized_text in {")", "）"}:
        normalized_text = "）"
        style["semantic_role"] = "answer_blank"
    return PageBlock(
        block_id=f"{layout.block_id}-line-{index + 1}",
        block_type="text_line",
        bbox=bbox,
        z_index=layout.z_index * 100 + index,
        reading_order=layout.reading_order * 100 + index,
        confidence=score,
        text=normalized_text,
        style=style,
    )


def _merge_adjacent_ocr_line_fragments(lines: list[PageBlock]) -> list[PageBlock]:
    """Join OCR shards that belong to one printed baseline.

    PP-Structure occasionally recognises the closing words of a long Chinese
    sentence as several tiny regions (``排除`` / ``A`` / ``B、`` / ``三项。``).
    Those boxes are too narrow once converted to Word points, so their glyphs
    wrap vertically.  Merge only a run that begins with a substantial line and
    remains horizontally adjacent on the same baseline; option rows and other
    independent one-character boxes remain separate.
    """

    text_lines = [
        block
        for block in lines
        if block.block_type == "text_line"
        and block.text
        and block.style.get("source") == "PaddleOCR line"
        and block.style.get("semantic_role") != "answer_blank"
    ]
    if len(text_lines) < 2:
        return lines
    by_id = {block.block_id: block for block in text_lines}
    used: set[str] = set()
    replacements: list[PageBlock] = []
    for seed in sorted(text_lines, key=lambda block: (block.bbox[1], block.bbox[0])):
        if seed.block_id in used or len(seed.text or "") < 8 or "指数" in (seed.text or ""):
            continue
        group = [seed]
        cursor = seed
        while True:
            candidates = [
                candidate
                for candidate in text_lines
                if candidate.block_id not in used
                and candidate.block_id not in {item.block_id for item in group}
                and abs(((candidate.bbox[1] + candidate.bbox[3]) - (cursor.bbox[1] + cursor.bbox[3])) / 2) <= 18
                and candidate.bbox[0] <= cursor.bbox[2] + 35
                and candidate.bbox[2] > cursor.bbox[2] - 5
            ]
            if not candidates:
                break
            next_line = min(candidates, key=lambda block: block.bbox[0])
            group.append(next_line)
            cursor = next_line
        if len(group) < 2:
            continue
        used.update(item.block_id for item in group)
        left = min(item.bbox[0] for item in group)
        top = min(item.bbox[1] for item in group)
        right = max(item.bbox[2] for item in group)
        bottom = max(item.bbox[3] for item in group)
        replacements.append(
            PageBlock(
                block_id=f"{seed.block_id}-merged-fragments",
                block_type="text_line",
                bbox=(left, top, right, bottom),
                z_index=min(item.z_index for item in group),
                reading_order=min(item.reading_order for item in group),
                confidence=seed.confidence,
                text="".join(item.text or "" for item in group),
                style={
                    **seed.style,
                    "source": "merged PaddleOCR line fragments",
                    "merged_prefix_text": seed.text,
                    "merged_prefix_bbox": list(seed.bbox),
                    "tail_fragment_fallback_bbox": [
                        max(seed.bbox[2], min(item.bbox[0] for item in group[1:])),
                        min(item.bbox[1] for item in group[1:]),
                        max(item.bbox[2] for item in group[1:]),
                        max(item.bbox[3] for item in group[1:]),
                    ],
                },
            )
        )
    if not replacements:
        return lines
    return [block for block in lines if block.block_id not in used] + replacements


def _restore_missing_answer_blank(
    lines: list[PageBlock],
    layout: PageBlock,
    *,
    has_external_answer_blank: bool = False,
    answer_anchor_left: float | None = None,
    answer_anchor_gap: float | None = None,
    page_width_px: int | None = None,
) -> list[PageBlock]:
    """Restore missing full-width answer parentheses for numbered questions."""

    combined_pair = next(
        (
            line
            for line in lines
            if line.text and re.fullmatch(r"[（(]\s*[）)]", line.text.strip())
        ),
        None,
    )
    if combined_pair is not None:
        left, top, _, bottom = combined_pair.bbox
        width = 20.0
        combined_pair.text = "（"
        combined_pair.bbox = (left, top, left + width, bottom)
        combined_pair.style["semantic_role"] = "answer_blank"
        lines.append(
            PageBlock(
                block_id=f"{combined_pair.block_id}-split-close",
                block_type="text_line",
                bbox=(left + CN_EXAM_QUESTION_V1.answer_pair_gap_px, top, left + CN_EXAM_QUESTION_V1.answer_pair_gap_px + width, bottom),
                z_index=combined_pair.z_index + 1,
                reading_order=combined_pair.reading_order + 1,
                text="）",
                style={**combined_pair.style, "source": "split OCR answer blank"},
            )
        )
        return lines
    blanks = [line for line in lines if line.style.get("semantic_role") == "answer_blank"]
    if len(blanks) == 0:
        if has_external_answer_blank:
            return lines
        heading = next((line for line in lines if line.style.get("semantic_role") == "question_heading"), None)
        if heading is None:
            return lines
        _, _, layout_right, layout_bottom = layout.bbox
        # Question text and its answer blank are often separate layout
        # regions. If OCR misses the latter, align to the nearest preceding
        # question's measured blank. On a page with no usable anchor, use the
        # profile's stable right-column position instead of appending the pair
        # to the end of a narrow heading box.
        top = layout_bottom - 21
        width = 20.0
        if answer_anchor_left is not None:
            left = answer_anchor_left
        elif page_width_px is not None and layout_right < page_width_px * 0.80:
            left = page_width_px * 0.848
        else:
            left = layout_right - 76
        style = {
            key: value
            for key, value in heading.style.items()
            if key not in {"accent_length", "bold_prefix_length"}
        }
        style.update({"semantic_role": "answer_blank", "source": "reconstructed answer blank"})
        pair_gap = answer_anchor_gap or CN_EXAM_QUESTION_V1.answer_pair_gap_px
        lines.extend(
            (
                PageBlock(
                    block_id=f"{heading.block_id}-reconstructed-open",
                    block_type="text_line",
                    bbox=(left, top, left + width, layout_bottom + 1),
                    z_index=max(line.z_index for line in lines) + 1,
                    reading_order=max(line.reading_order for line in lines) + 1,
                    text="（",
                    style=style,
                ),
                PageBlock(
                    block_id=f"{heading.block_id}-reconstructed-close",
                    block_type="text_line",
                    bbox=(left + pair_gap, top, left + pair_gap + width, layout_bottom + 1),
                    z_index=max(line.z_index for line in lines) + 2,
                    reading_order=max(line.reading_order for line in lines) + 2,
                    text="）",
                    style=style,
                ),
            )
        )
        return lines
    if len(blanks) != 1:
        return lines
    detected = blanks[0]
    left, top, right, bottom = detected.bbox
    width = max(1.0, right - left)
    # This publication uses a stable 54 px gap between the two glyph boxes at
    # the 200-DPI OCR resolution. Preserve the detected side's y coordinate.
    if detected.text == "（":
        missing_bbox = (left + 54, top, min(layout.bbox[2], left + 54 + width), bottom)
        missing_text = "）"
    else:
        missing_bbox = (max(layout.bbox[0], left - 54), top, max(layout.bbox[0] + width, right - 54), bottom)
        missing_text = "（"
    if missing_bbox[2] <= missing_bbox[0]:
        return lines
    lines.append(
        PageBlock(
            block_id=f"{detected.block_id}-reconstructed-pair",
            block_type="text_line",
            bbox=missing_bbox,
            z_index=max(line.z_index for line in lines) + 1,
            reading_order=max(line.reading_order for line in lines) + 1,
            text=missing_text,
            style={**detected.style, "source": "reconstructed answer blank"},
        )
    )
    return lines


def _talk_answer_blocks(
    layout: PageBlock,
    candidates: list[tuple[int, str, tuple[float, float, float, float], float | None]],
) -> list[PageBlock] | None:
    """Split inline ``谈答案B`` into badge artwork and editable text."""

    candidate = next(
        (
            (index, text, bbox, score)
            for index, text, bbox, score in candidates
            if _candidate_is_in_layout(bbox, layout.bbox) and re.match(r"^谈(?:解析|答案|提示)", text.strip())
        ),
        None,
    )
    if candidate is None:
        return None
    index, text, bbox, score = candidate
    match = re.match(r"^谈(?P<label>解析|答案|提示)(?P<rest>.*)$", text.strip())
    if match is None:
        return None
    left, top, right, bottom = bbox
    badge_right = min(right, left + CN_EXAM_QUESTION_V1.talk_badge_width_px)
    label_left = badge_right + CN_EXAM_QUESTION_V1.callout_label_gap_px
    label_right = min(
        right - CN_EXAM_QUESTION_V1.callout_content_gap_px - 16,
        label_left + CN_EXAM_QUESTION_V1.callout_label_width_px,
    )
    label_top = min(bottom - 1, top + 12)
    answer_bbox = (
        label_right + CN_EXAM_QUESTION_V1.callout_content_gap_px,
        label_top,
        right,
        bottom,
    )
    answer_text = match.group("rest").strip()
    if not answer_text:
        return None
    return [
        PageBlock(
            block_id=f"{layout.block_id}-talk-badge-{index + 1}",
            block_type="talk_badge_image",
            bbox=(left, top, badge_right, bottom),
            z_index=layout.z_index * 100 + index,
            reading_order=layout.reading_order * 100 + index,
            style={**layout.style, "semantic_role": "talk_badge_image"},
        ),
        PageBlock(
            block_id=f"{layout.block_id}-talk-label-{index + 1}",
            block_type="text_line",
            bbox=(label_left, label_top, label_right, bottom),
            z_index=layout.z_index * 100 + index + 1,
            reading_order=layout.reading_order * 100 + index + 1,
            text=match.group("label"),
            style={
                **layout.style,
                "semantic_role": "callout_label",
                "font_size_pt": 8.0,
                "font_color": "EF168B",
                "source": "editable label beside source talk badge",
            },
        ),
        PageBlock(
            block_id=f"{layout.block_id}-talk-answer-{index + 1}",
            block_type="text_line",
            bbox=answer_bbox,
            z_index=layout.z_index * 100 + index + 2,
            reading_order=layout.reading_order * 100 + index + 2,
            confidence=score,
            text=answer_text,
            style={
                **layout.style,
                "source": "PaddleOCR answer after talk tag",
                "semantic_role": "callout_answer",
            },
        ),
    ]


def _positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _focused_text_ocr_pipeline(**options: Any) -> Any:
    """Create the lightweight OCR pipeline used only for missed callout lines."""

    # A conversion must work with the locally installed model package. Avoid a
    # slow connectivity probe every time a rare focused retry is required.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCR  # type: ignore[import-not-found]

    return PaddleOCR(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        **options,
    )


def _resolve_focused_pipeline(value: FocusedOcrPipelineCache | Any | None) -> Any:
    if isinstance(value, FocusedOcrPipelineCache):
        return value.get()
    return value if value is not None else _focused_text_ocr_pipeline()


def recover_semantic_callout_lines(
    model: PageModel,
    image_path: str | Path,
    region_directory: str | Path,
    *,
    focused_pipeline: FocusedOcrPipelineCache | Any | None = None,
) -> list[dict[str, Any]]:
    """OCR only text that the main layout pass skipped beside a ``谈`` tag.

    The decorative tag is intentionally preserved as a small image. Its
    neighbouring prose is cropped without the tag, recognised by PaddleOCR's
    text-only pipeline and restored as an editable, positioned text line.
    """

    requests = [
        block
        for block in model.blocks
        if block.block_type in {"talk_badge_image", "talk_callout_tag_image"}
        and isinstance(block.style.get("recovery_crop_bbox"), list)
    ]
    if not requests:
        return []
    destination = Path(region_directory)
    destination.mkdir(parents=True, exist_ok=True)
    pipeline = _resolve_focused_pipeline(focused_pipeline)
    recovered: list[dict[str, Any]] = []
    with Image.open(image_path) as source_image:
        image = source_image.convert("RGB")
        width, height = image.size
        for request in requests:
            crop_value = request.style["recovery_crop_bbox"]
            try:
                left, top, right, bottom = (round(float(value)) for value in crop_value)
            except (TypeError, ValueError):
                continue
            left, top = max(0, left), max(0, top)
            right, bottom = min(width, right), min(height, bottom)
            if right <= left or bottom <= top:
                continue
            crop_path = destination / f"{request.block_id}-focused-ocr.png"
            image.crop((left, top, right, bottom)).save(crop_path, format="PNG")
            result = next(iter(pipeline.predict(str(crop_path))), None)
            raw_result = getattr(result, "json", result) if result is not None else None
            if callable(raw_result):
                raw_result = raw_result()
            payload = raw_result.get("res") if isinstance(raw_result, Mapping) and isinstance(raw_result.get("res"), Mapping) else raw_result
            if not isinstance(payload, Mapping):
                continue
            texts = payload.get("rec_texts")
            boxes = payload.get("rec_boxes")
            scores = payload.get("rec_scores")
            if not isinstance(texts, list) or not isinstance(boxes, list):
                continue
            for item_index, text in enumerate(texts):
                if item_index >= len(boxes) or not str(text).strip():
                    continue
                box = boxes[item_index]
                if not isinstance(box, (list, tuple)) or len(box) < 4:
                    continue
                try:
                    box_left, box_top, box_right, box_bottom = (float(value) for value in box[:4])
                except (TypeError, ValueError):
                    continue
                if box_right <= box_left or box_bottom <= box_top:
                    continue
                score = scores[item_index] if isinstance(scores, list) and item_index < len(scores) else None
                recovered.append(
                    {
                        "layout_block_id": str(request.style["layout_block_id"]),
                        "text": str(text).strip(),
                        "bbox": [left + box_left, top + box_top, left + box_right, top + box_bottom],
                        "score": _as_float(score),
                    }
                )
    return recovered


def merge_semantic_callout_lines(existing: object, recovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep durable focused-OCR lines when a retry finds additional callouts.

    A later retry commonly sees only the newly recovered ``谈提示`` line.  It
    must not replace earlier cached ``谈提示``/``谈解析`` lines, or their first
    rows disappear from the regenerated Word page.
    """

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[object, ...]]] = set()
    sources = [existing] if isinstance(existing, list) else []
    sources.append(recovered)
    for source in sources:
        if not isinstance(source, list):
            continue
        for line in source:
            if not isinstance(line, Mapping):
                continue
            layout_block_id = str(line.get("layout_block_id", ""))
            text = str(line.get("text", "")).strip()
            bbox = line.get("bbox")
            bbox_key = tuple(bbox) if isinstance(bbox, (list, tuple)) else ()
            if not layout_block_id or not text or len(bbox_key) != 4:
                continue
            key = (layout_block_id, text, bbox_key)
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(line))
    return merged


def materialize_visual_fallbacks(
    model: PageModel,
    image_path: str | Path,
    region_directory: str | Path,
    *,
    focused_pipeline: FocusedOcrPipelineCache | Any | None = None,
    editable_body_only: bool = False,
) -> PageModel:
    """Crop non-textual OCR regions for editable DOCX image fallback.

    Text remains a real Word textbox. Images, charts, formulas and other
    regions that cannot be safely reconstructed are retained as cropped PNGs.
    """

    # The cover is a designed image, not ordinary prose.  Recreating its
    # decorative lettering as black editable text is less accurate than a
    # source screenshot, so it deliberately owns page 1 end-to-end.
    if model.page_index == 0 and any(block.block_type.lower() in {"doc_title", "cover", "cover_title"} for block in model.blocks):
        return force_full_page_fallback(model, image_path, region_directory, reason="cover page uses source-image fidelity fallback")

    fallback_types = {
        "image",
        "chart",
        "logo",
        "watermark",
        "table",
        # Narrow decorative title/header regions are often clipped by Word VML
        # text boxes. Preserve their appearance as a local image instead.
        "header",
        "talk_badge_image",
        "talk_callout_tag_image",
    }
    if not editable_body_only:
        fallback_types.update({"formula", "paragraph_title"})
    destination = Path(region_directory)
    with Image.open(image_path) as source_image:
        image = source_image.convert("RGB")
        width, height = image.size
        model.source_image_width_px = width
        model.source_image_height_px = height
        _restore_unreadable_sidebar_as_image(model, image, destination)
        # Watermark handling belongs to the matched source/preprocessing policy.
        # OCR materialization must not independently add or remove one.
        _restore_callout_ratings_from_source(model, image)
        if not editable_body_only:
            _collapse_formula_fragments_to_image_fallback(model, page_width_px=width)
        _recover_fragmented_text_tails(model, image, destination, focused_pipeline=focused_pipeline)
        if not editable_body_only:
            _restore_fragmented_text_tails_as_images(model)
            _restore_option_figure_strip(model, page_width_px=width, page_height_px=height)
        for block in model.blocks:
            if block.block_type.lower() not in fallback_types:
                continue
            # Some fallbacks, such as the isolated transparent watermark,
            # already provide a prepared asset rather than a raw source crop.
            if block.asset_path:
                continue
            left, top, right, bottom = (round(item) for item in block.bbox)
            if block.block_type.lower() == "table":
                # PP-Structure's table box is usually measured to the final
                # row's text baseline, not to the outside rule.  Pillow's
                # right/bottom coordinates are exclusive as well, so retaining
                # only one extra pixel can still cut off a thin bottom rule.
                # Give the visual fallback a two-pixel safety strip below the
                # detected geometry and grow its placed box by the same amount:
                # this preserves the rule at the visible table edge rather
                # than squeezing it into the last content row.
                right = min(width, right + 1)
                bottom = min(height, bottom + 3)
                block.bbox = (block.bbox[0], block.bbox[1], block.bbox[2], float(bottom))
            elif block.block_type.lower() in {"talk_badge_image", "talk_callout_tag_image"}:
                # The round pink \"谈提示\"/\"谈解析\" badge often has one or
                # two antialiased pixels beyond the narrow layout box.  Keep a
                # small safe strip on the right and bottom so the final glyph
                # is not visibly clipped in the DOCX image fallback.
                right = min(width, right + 2)
                bottom = min(height, bottom + 2)
                block.bbox = (block.bbox[0], block.bbox[1], float(right), float(bottom))
            elif block.block_type.lower() == "formula":
                # Fractions, superscripts and root bars are easy to crop by a
                # pixel.  Retain a small all-round source margin and make the
                # placed region match it exactly.
                left, top = max(0, left - 5), max(0, top - 5)
                right, bottom = min(width, right + 5), min(height, bottom + 5)
                block.bbox = (float(left), float(top), float(right), float(bottom))
            left, right = max(0, left), min(width, right)
            top, bottom = max(0, top), min(height, bottom)
            if right <= left or bottom <= top:
                block.warnings.append("回退区域坐标越界，未生成图片。")
                continue
            destination.mkdir(parents=True, exist_ok=True)
            asset = destination / f"{block.block_id}.png"
            image.crop((left, top, right, bottom)).save(asset, format="PNG")
            block.asset_path = str(asset)
            block.source = block.source or "source PDF crop"
            block.fallback_mode = block.fallback_mode or "region_source_image"
            block.selection_reason = block.selection_reason or "visual region cannot be reconstructed reliably"
    return resolve_page_model_conflicts(model)


def _restore_callout_ratings_from_source(model: PageModel, image: Image.Image) -> None:
    """Recover filled versus outline stars from the rendered source pixels."""

    for block in model.blocks:
        match = re.match(r"^(?P<label>易(?:错|考)指数)", (block.text or "").replace(" ", ""))
        if match is None or block.style.get("semantic_role") != "callout_index":
            continue
        left, top, right, bottom = block.bbox
        star_region_width = 145.0
        star_left = max(left, right - star_region_width)
        advance = star_region_width / 5
        counts: list[int] = []
        for index in range(5):
            slot_left = max(0, round(star_left + index * advance))
            slot_right = min(image.width, round(star_left + (index + 1) * advance))
            slot_top = max(0, round(top - 2))
            slot_bottom = min(image.height, round(bottom + 4))
            ink = 0
            for y in range(slot_top, slot_bottom):
                for x in range(slot_left, slot_right):
                    red, green, blue = image.getpixel((x, y))[:3]
                    if red >= 180 and green <= 110 and 70 <= blue <= 210:
                        ink += 1
            counts.append(ink)
        strongest = max(counts, default=0)
        if strongest < 45:
            continue
        threshold = max(45, strongest * 0.55)
        stars = "".join("★" if count >= threshold else "☆" for count in counts)
        block.text = f"{match.group('label')}{stars}"
        block.style["source"] = "editable rating classified from source star ink"


def _restore_unreadable_sidebar_as_image(model: PageModel, image: Image.Image, destination: Path) -> None:
    """Retain an unreadable right-hand vertical sidebar as a source image.

    A blank ``aside_text`` layout block means OCR located the sidebar but could
    not read its vertical text.  Falling back to its source crop preserves the
    chapter label and page number without inventing editable content.
    """

    unreadable = next(
        (
            block
            for block in model.blocks
            if block.block_type.lower() == "aside_text"
            and not (block.text or "").strip()
            and block.bbox[0] >= image.width * 0.80
        ),
        None,
    )
    if unreadable is None:
        return
    left = max(0, round(unreadable.bbox[0] - 55))
    top = max(0, round(unreadable.bbox[1] - 20))
    right, bottom = image.width, image.height
    if right <= left or bottom <= top:
        return
    destination.mkdir(parents=True, exist_ok=True)
    asset = destination / "unreadable-sidebar.png"
    image.crop((left, top, right, bottom)).save(asset, format="PNG")
    retained: list[PageBlock] = []
    for block in model.blocks:
        center_x = (block.bbox[0] + block.bbox[2]) / 2
        center_y = (block.bbox[1] + block.bbox[3]) / 2
        if center_x >= left and center_y >= top:
            continue
        retained.append(block)
    retained.append(
        PageBlock(
            block_id="unreadable-sidebar",
            block_type="image",
            bbox=(float(left), float(top), float(right), float(bottom)),
            z_index=unreadable.z_index,
            reading_order=unreadable.reading_order,
            style={"source": "unreadable vertical sidebar fallback"},
            asset_path=str(asset),
            warnings=["右侧竖排章节栏 OCR 不可靠，已回退为原图。"],
        )
    )
    model.blocks = retained


def _recover_fragmented_text_tails(
    model: PageModel,
    image: Image.Image,
    destination: Path,
    *,
    focused_pipeline: FocusedOcrPipelineCache | Any | None = None,
) -> None:
    """Retry only a fragmented suffix before falling back to its source image."""

    requests = [
        block
        for block in model.blocks
        if block.block_type == "text_line"
        and isinstance(block.style.get("tail_fragment_fallback_bbox"), list)
        and isinstance(block.style.get("merged_prefix_text"), str)
        and block.style.get("semantic_role") != "callout_index"
    ]
    if not requests:
        return
    pipeline = _resolve_focused_pipeline(focused_pipeline)
    destination.mkdir(parents=True, exist_ok=True)
    replacements: list[PageBlock] = []
    for block in requests:
        tail_value = block.style.get("tail_fragment_fallback_bbox")
        prefix_value = block.style.get("merged_prefix_bbox")
        prefix_text = block.style.get("merged_prefix_text")
        if not (
            isinstance(tail_value, list)
            and len(tail_value) == 4
            and isinstance(prefix_value, list)
            and len(prefix_value) == 4
            and isinstance(prefix_text, str)
        ):
            continue
        try:
            left, top, right, bottom = (round(float(value)) for value in tail_value)
            prefix = tuple(float(value) for value in prefix_value)
        except (TypeError, ValueError):
            continue
        left, top = max(0, left), max(0, top)
        right, bottom = min(image.width, right), min(image.height, bottom)
        if right <= left or bottom <= top:
            continue
        crop_path = destination / f"{block.block_id}-tail-focused-ocr.png"
        image.crop((left, top, right, bottom)).save(crop_path, format="PNG")
        result = next(iter(pipeline.predict(str(crop_path))), None)
        raw_result = getattr(result, "json", result) if result is not None else None
        if callable(raw_result):
            raw_result = raw_result()
        payload = raw_result.get("res") if isinstance(raw_result, Mapping) and isinstance(raw_result.get("res"), Mapping) else raw_result
        if not isinstance(payload, Mapping):
            continue
        texts = payload.get("rec_texts")
        scores = payload.get("rec_scores")
        if not isinstance(texts, list) or not texts:
            continue
        recovered = "".join(str(item).strip() for item in texts if str(item).strip())
        score_values = [
            _as_float(scores[index])
            for index in range(min(len(texts), len(scores) if isinstance(scores, list) else 0))
        ]
        confident_scores = [score for score in score_values if score is not None]
        if not recovered or not confident_scores or min(confident_scores) < 0.98:
            continue
        block.text = prefix_text
        block.bbox = prefix
        block.style.pop("tail_fragment_fallback_bbox", None)
        block.style.pop("merged_prefix_bbox", None)
        block.style.pop("merged_prefix_text", None)
        block.style["source"] = "PaddleOCR line"
        replacements.append(
            PageBlock(
                block_id=f"{block.block_id}-focused-tail",
                block_type="text_line",
                bbox=(float(left), float(top), float(right + 10), float(bottom)),
                z_index=block.z_index + 1,
                reading_order=block.reading_order + 1,
                text=recovered,
                style={
                    **block.style,
                    "source": "focused PaddleOCR line fragment",
                    "semantic_role": "callout_body_fragment",
                    "font_size_pt": 7.0,
                    "justify_to_bbox": False,
                },
            )
        )
    if replacements:
        model.blocks.extend(replacements)


def _restore_fragmented_text_tails_as_images(model: PageModel) -> None:
    """Use a source crop for an OCR fragment tail whose text is incomplete.

    A merged tail is still preferable to vertically stacked glyphs, but a
    sequence of tiny OCR boxes can omit punctuation or an entire option letter.
    Retain that small suffix as a local image; the long, reliable first part of
    the sentence remains editable and the rendered page stays faithful.
    """

    replacements: list[PageBlock] = []
    for block in model.blocks:
        tail_bbox = block.style.get("tail_fragment_fallback_bbox")
        prefix_bbox = block.style.get("merged_prefix_bbox")
        prefix_text = block.style.get("merged_prefix_text")
        if not (
            block.block_type == "text_line"
            and isinstance(tail_bbox, list)
            and len(tail_bbox) == 4
            and isinstance(prefix_bbox, list)
            and len(prefix_bbox) == 4
            and isinstance(prefix_text, str)
            and prefix_text
            and block.style.get("semantic_role") != "callout_index"
        ):
            continue
        try:
            tail = tuple(float(value) for value in tail_bbox)
            prefix = tuple(float(value) for value in prefix_bbox)
        except (TypeError, ValueError):
            continue
        if tail[2] <= tail[0] or tail[3] <= tail[1] or prefix[2] <= prefix[0] or prefix[3] <= prefix[1]:
            continue
        block.text = prefix_text
        block.bbox = prefix
        block.style.pop("tail_fragment_fallback_bbox", None)
        block.style.pop("merged_prefix_bbox", None)
        block.style.pop("merged_prefix_text", None)
        replacements.append(
            PageBlock(
                block_id=f"{block.block_id}-tail-image",
                block_type="image",
                bbox=tail,
                z_index=block.z_index + 1,
                reading_order=block.reading_order + 1,
                style={"source": "unreliable OCR tail fallback"},
            )
        )
    if replacements:
        model.blocks.extend(replacements)


def _restore_option_figure_strip(model: PageModel, *, page_width_px: int, page_height_px: int) -> None:
    """Retain a row of diagram answer choices that layout OCR sees only as A–D.

    PP-Structure emits the option letters beneath a row of small 3D diagrams
    as text, but omits the diagrams' otherwise non-textual region.  The same
    pattern is highly constrained: four single-letter choices in one row near
    the top of a question, with broadly even horizontal spacing.  Preserve
    only the diagram band above those letters, leaving A–D editable.
    """

    labels = [
        block
        for block in model.blocks
        if block.block_type == "text_line"
        and re.fullmatch(r"[A-D]", (block.text or "").strip())
        and block.bbox[0] >= page_width_px * 0.2
        and block.bbox[1] <= page_height_px * 0.25
    ]
    labels.sort(key=lambda block: block.bbox[0])
    if len(labels) < 4:
        return
    for start in range(len(labels) - 3):
        group = labels[start : start + 4]
        tops = [item.bbox[1] for item in group]
        centres = [(item.bbox[0] + item.bbox[2]) / 2 for item in group]
        gaps = [centres[index + 1] - centres[index] for index in range(3)]
        if max(tops) - min(tops) > 22 or min(gaps) < 55 or max(gaps) > 155:
            continue
        if max(gaps) - min(gaps) > 45:
            continue
        top = max(0.0, min(tops) - 115)
        # Keep the thin horizontal rule at the bottom of a cube-net diagram,
        # while ending immediately before the option-letter baseline.
        bottom = max(0.0, min(tops))
        left = max(0.0, group[0].bbox[0] - 240)
        # The rightmost D diagram normally projects ~35 source pixels beyond
        # its option letter.  Retain that edge without rasterising A–D.
        right = min(float(page_width_px), group[-1].bbox[2] + 45)
        if bottom - top < 45 or right - left < 250:
            continue
        if any(
            block.block_type.lower() == "image"
            and block.bbox[0] <= right
            and block.bbox[2] >= left
            and block.bbox[1] <= bottom
            and block.bbox[3] >= top
            for block in model.blocks
        ):
            continue
        model.blocks.append(
            PageBlock(
                block_id=f"option-figure-strip-{start + 1}",
                block_type="image",
                bbox=(left, top, right, bottom),
                z_index=min(item.z_index for item in group) - 1,
                reading_order=min(item.reading_order for item in group) - 1,
                style={"source": "restored option figure strip"},
            )
        )
        # The unfolded cube net at the strip's left has a separate bottom
        # rule below the A–D label baseline.  Keep that narrow source band on
        # its own so the rule is restored without rasterising the editable
        # option letters beneath the four 3D choices.
        net_right = min(float(page_width_px), group[0].bbox[0] - 75)
        if net_right - left >= 100:
            model.blocks.append(
                PageBlock(
                    block_id=f"option-figure-net-bottom-rule-{start + 1}",
                    block_type="image",
                    bbox=(left, min(tops) - 2, net_right, min(tops) + 8),
                    z_index=min(item.z_index for item in group),
                    reading_order=min(item.reading_order for item in group),
                    style={"source": "restored cube-net bottom rule"},
                )
            )
        return


def _collapse_formula_fragments_to_image_fallback(model: PageModel, *, page_width_px: int) -> None:
    """Keep fragmented right-side equations as one source crop.

    OCR may split a fraction into numerator, denominator and operator boxes.
    Reconstructing those fragments as independent Word text boxes overlaps the
    surrounding prose. A compact source-image fallback preserves the equation
    while ordinary text remains editable.
    """

    formula_token = re.compile(r"[≈=÷%]|^\d+(?:\.\d+)?$")
    fragments = [
        block
        for block in model.blocks
        if block.block_type == "text_line"
        and block.text
        and block.bbox[0] >= page_width_px * 0.7
        and formula_token.search(block.text.replace(" ", ""))
    ]
    if len(fragments) < 3:
        return
    fragments.sort(key=lambda block: (block.bbox[1], block.bbox[0]))
    groups: list[list[PageBlock]] = []
    for fragment in fragments:
        if not groups or fragment.bbox[1] - max(item.bbox[3] for item in groups[-1]) > 30:
            groups.append([fragment])
        else:
            groups[-1].append(fragment)
    replacements: list[PageBlock] = []
    removed: set[str] = set()
    for index, group in enumerate(groups, start=1):
        if len(group) < 3:
            continue
        left = min(item.bbox[0] for item in group)
        top = min(item.bbox[1] for item in group)
        right = max(item.bbox[2] for item in group)
        bottom = max(item.bbox[3] for item in group)
        removed.update(item.block_id for item in group)
        replacements.append(
            PageBlock(
                block_id=f"formula-fallback-{index}",
                block_type="formula",
                bbox=(left, top, right, bottom),
                z_index=min(item.z_index for item in group),
                reading_order=min(item.reading_order for item in group),
                style={"source": "fragmented formula fallback"},
                source="source PDF formula crop",
                selection_reason="stacked/fragmented formula is not reliable editable text",
                fallback_mode="formula_source_image",
            )
        )
    if removed:
        model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements


def predict_page_model(
    pipeline: Any,
    image_path: str | Path,
    *,
    page_index: int,
    size: PageSize,
    source_type: PdfKind,
    raw_output_path: str | Path | None = None,
    native_word_output_dir: str | Path | None = None,
    region_directory: str | Path | None = None,
    focused_pipeline: FocusedOcrPipelineCache | Any | None = None,
    editable_body_only: bool = False,
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
    if native_word_output_dir is not None:
        destination = Path(native_word_output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        save_to_word = getattr(result, "save_to_word", None)
        if not callable(save_to_word):
            raise OcrRequiredError("当前 PaddleOCR 结果不支持原生 Word 导出。")
        save_to_word(str(destination))
    model = page_model_from_paddle_result(
        raw,
        page_index=page_index,
        size=size,
        source_type=source_type,
    )
    if region_directory is not None:
        focused_lines = recover_semantic_callout_lines(
            model,
            image_path,
            region_directory,
            focused_pipeline=focused_pipeline,
        )
        if focused_lines:
            payload = raw.get("res") if isinstance(raw.get("res"), Mapping) else raw
            if isinstance(payload, dict):
                payload["semantic_line_ocr"] = merge_semantic_callout_lines(
                    payload.get("semantic_line_ocr"), focused_lines
                )
                model = page_model_from_paddle_result(
                    raw,
                    page_index=page_index,
                    size=size,
                    source_type=source_type,
                )
        materialize_visual_fallbacks(
            model,
            image_path,
            region_directory,
            focused_pipeline=focused_pipeline,
            editable_body_only=editable_body_only,
        )
    if raw_output_path is not None:
        destination = Path(raw_output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return model


def write_page_model(model: PageModel, output_path: str | Path) -> Path:
    """Persist a portable PageModel checkpoint with UTF-8 Chinese text intact."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return destination
