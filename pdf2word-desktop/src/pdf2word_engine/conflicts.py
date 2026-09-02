"""Deterministic PageModel conflict resolution and static quality checks.

The Word renderer must never be the place where competing OCR output is
resolved.  This module is the single pre-write policy point: it either keeps a
well-described editable block or gives the source-image fallback exclusive
ownership of that region.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from PIL import Image

from .models import PAGE_MODEL_SCHEMA_VERSION, PageBlock, PageModel


_IMAGE_OWNERS = {"image", "chart", "table", "figure", "formula", "logo", "watermark", "talk_badge_image", "talk_callout_tag_image", "talk_label_image", "full_page_fallback"}
_COMPLEX_FORMULA = re.compile(r"[√∑∫]|(?:[A-Za-z0-9）】]\s*)[=/÷](?:\s*[A-Za-z0-9（【])|\b\d+\s*[+\-]\s*\d+\b")
_LABEL_RESIDUE = re.compile(r"^\s*(?:谈\s*)?(?:提示|解析|示|析)\s*(?=\S)")


def _area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersection_area(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    return _area((max(left[0], right[0]), max(left[1], right[1]), min(left[2], right[2]), min(left[3], right[3])))


def overlap_ratio(left: PageBlock, right: PageBlock) -> float:
    overlap = intersection_area(left.bbox, right.bbox)
    smallest = min(_area(left.bbox), _area(right.bbox))
    return overlap / smallest if smallest else 0.0


def _normal_text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def _similar(left: PageBlock, right: PageBlock) -> float:
    return SequenceMatcher(None, _normal_text(left.text), _normal_text(right.text)).ratio()


def _source(block: PageBlock) -> str:
    return block.source or str(block.style.get("source") or block.style.get("ocr_engine") or "unknown")


def _score(block: PageBlock) -> float:
    confidence = block.confidence if block.confidence is not None else 0.84
    source = _source(block).lower()
    # Focused OCR is useful only when it is a cleaner/better local candidate;
    # it gets no unconditional privilege over full-page OCR.
    provenance = 0.02 if "focused" in source else 0.01 if "paddle" in source else 0.0
    residue_penalty = 0.18 if (block.text or "").lstrip().startswith(("示", "析")) else 0.0
    return confidence + provenance - residue_penalty


def _record(model: PageModel, *, action: str, block: PageBlock, reason: str, related: list[str] | None = None) -> None:
    model.debug_records.append({
        "action": action,
        "block_id": block.block_id,
        "block_type": block.block_type,
        "source": _source(block),
        "reason": reason,
        "related_block_ids": related or [],
        "bbox": list(block.bbox),
        "text_preview": (block.text or "")[:80],
    })


def _strip_callout_residue(block: PageBlock) -> None:
    if block.style.get("semantic_role") not in {"callout_body", "callout_body_fragment"} or not block.text:
        return
    cleaned = _LABEL_RESIDUE.sub("", block.text)
    if cleaned != block.text:
        block.text = cleaned
        block.warnings.append("已清理局部补 OCR 带入的谈标签残字。")
        block.selection_reason = "removed callout label residue before comparison"


def _is_exclusive_owner(block: PageBlock) -> bool:
    if (
        block.block_type.lower() == "watermark"
        or block.style.get("render_behind_text")
        or block.style.get("inline_decorative")
    ):
        return False
    return bool(block.asset_path) and (block.block_type.lower() in _IMAGE_OWNERS or block.fallback_mode is not None)


def _is_inline_decoration_host_pair(left: PageBlock, right: PageBlock) -> bool:
    """Return whether geometry intentionally binds a label to its host paragraph."""

    return bool(
        (
            left.style.get("inline_decorative")
            and left.style.get("inline_host_block_id") == right.block_id
        )
        or (
            right.style.get("inline_decorative")
            and right.style.get("inline_host_block_id") == left.block_id
        )
    )


def resolve_page_model_conflicts(model: PageModel) -> PageModel:
    """Remove duplicate/covered OCR before the PageModel can reach Word.

    Removed blocks are never silently discarded: lightweight debug entries give
    the quality report enough evidence to explain every automatic decision.
    """

    model.schema_version = PAGE_MODEL_SCHEMA_VERSION
    for block in model.blocks:
        block.source = block.source or _source(block)
        # A narrow running-page box often captures the leading vertical sidebar
        # character as ``1``.  This book uses three-digit running numbers;
        # e.g. OCR ``1018`` must be rendered as ``018`` rather than ``101``.
        digits = (block.text or "").strip()
        page_height = model.source_image_height_px or model.size.height_pt
        if block.block_type.lower() == "number" and re.fullmatch(r"1\d{3}", digits) and block.bbox[1] >= page_height * 0.88:
            block.text = digits[-3:]
            block.style["semantic_role"] = "sidebar_page_number"
            block.style.setdefault("font_size_pt", 8.5)
            block.selection_reason = "removed leading sidebar OCR artifact from three-digit running page number"
            block.warnings.append("页码 OCR 前置杂字已清理。")
        _strip_callout_residue(block)

    # The pale central ``上岸人`` mark is a reading obstruction rather than
    # source content.  It is intentionally removed before any ownership or
    # duplicate analysis, so it can neither cover text nor be reintroduced by
    # the Word renderer.
    without_watermarks: list[PageBlock] = []
    for block in model.blocks:
        watermark_source = _source(block).lower()
        if block.block_type.lower() == "watermark" and ("neutral-gray" in watermark_source or "上岸" in watermark_source):
            _record(model, action="removed", block=block, reason="user-requested removal of 上岸人 watermark")
            continue
        without_watermarks.append(block)
    model.blocks = without_watermarks

    owners = [block for block in model.blocks if _is_exclusive_owner(block)]
    retained: list[PageBlock] = []
    for block in model.blocks:
        if block in owners or not block.text:
            retained.append(block)
            continue
        block_area = _area(block.bbox)
        covering = [
            owner
            for owner in owners
            if block_area > 0 and intersection_area(block.bbox, owner.bbox) / block_area >= 0.42
        ]
        if covering:
            _record(model, action="removed", block=block, reason="covered by exclusive source-image fallback", related=[item.block_id for item in covering])
            continue
        retained.append(block)

    # Resolve duplicate and containment candidates in descending OCR quality,
    # so a lower-quality line cannot erase the chosen line later in the pass.
    text_blocks = [item for item in retained if item.text and not item.asset_path]
    discarded: set[str] = set()
    for index, left in enumerate(text_blocks):
        if left.block_id in discarded:
            continue
        for right in text_blocks[index + 1 :]:
            if right.block_id in discarded:
                continue
            spatial = overlap_ratio(left, right)
            similarity = _similar(left, right)
            left_text = _normal_text(left.text)
            right_text = _normal_text(right.text)
            shorter, longer = sorted((left_text, right_text), key=len)
            # Tiny formula fragments such as ``1`` or ``1-5`` often sit
            # entirely inside a merged paragraph bbox.  Geometric containment
            # does not make them duplicate prose, and they must never erase a
            # complete question stem.
            contains = (
                len(shorter) >= 8
                and len(shorter) / max(1, len(longer)) >= 0.50
                and shorter in longer
            )
            if spatial < 0.55 or (similarity < 0.78 and not contains):
                continue
            if contains and len(left_text) != len(right_text) and abs(_score(left) - _score(right)) < 0.12:
                winner, loser = (left, right) if len(left_text) > len(right_text) else (right, left)
            else:
                winner, loser = (left, right) if _score(left) >= _score(right) else (right, left)
            winner.selection_reason = winner.selection_reason or "selected as higher-quality OCR candidate after spatial/text comparison"
            _record(model, action="removed", block=loser, reason=f"duplicate OCR (overlap={spatial:.2f}, similarity={similarity:.2f}); kept higher-quality candidate", related=[winner.block_id])
            discarded.add(loser.block_id)
    model.blocks = [block for block in retained if block.block_id not in discarded and (block.text is None or block.text.strip() or block.asset_path)]
    for block in model.blocks:
        block.source = block.source or _source(block)
        if block.asset_path:
            block.fallback_mode = block.fallback_mode or "region_source_image"
            block.selection_reason = block.selection_reason or "retained source-image fallback after conflict resolution"
        elif block.text:
            block.selection_reason = block.selection_reason or "retained editable OCR after conflict resolution"
    model.warnings = [warning for warning in model.warnings if not warning.startswith("冲突消解器已处理 ")]
    if model.debug_records:
        model.warnings.append(f"冲突消解器已处理 {len(model.debug_records)} 个块决策。")
    return model


def force_full_page_fallback(model: PageModel, image_path: str | Path, destination: str | Path, *, reason: str) -> PageModel:
    """Replace an unreliable page by one source-raster owner, preserving audit."""

    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    asset = destination_path / "full-page-source.png"
    with Image.open(image_path) as image:
        image.convert("RGB").save(asset, format="PNG")
        width, height = image.size
    for block in model.blocks:
        _record(model, action="removed", block=block, reason=reason, related=["full-page-source"])
    model.blocks = [PageBlock(
        block_id="full-page-source",
        block_type="full_page_fallback",
        bbox=(0.0, 0.0, float(width), float(height)),
        z_index=0,
        reading_order=0,
        asset_path=str(asset),
        source="source PDF raster",
        selection_reason=reason,
        fallback_mode="full_page_source_image",
    )]
    model.schema_version = PAGE_MODEL_SCHEMA_VERSION
    model.warnings.append("整页源图回退：此页不进行不可靠的文字重建。")
    return model


def static_page_checks(model: PageModel) -> list[dict[str, Any]]:
    """Return non-mutating, reportable PageModel quality findings."""

    findings: list[dict[str, Any]] = []
    blocks = model.blocks
    for index, left in enumerate(blocks):
        if left.confidence is not None and left.confidence < 0.85 and left.text and not left.asset_path:
            findings.append({"type": "low_confidence", "blocks": [left.block_id], "detail": f"confidence={left.confidence:.3f}"})
        for right in blocks[index + 1 :]:
            if _is_inline_decoration_host_pair(left, right):
                continue
            ratio = overlap_ratio(left, right)
            if ratio < 0.72:
                continue
            has_editable_text = (bool(left.text) and not left.asset_path) or (bool(right.text) and not right.asset_path)
            if has_editable_text and _is_exclusive_owner(left) != _is_exclusive_owner(right):
                text_block = left if left.text and not left.asset_path else right
                text_area = _area(text_block.bbox)
                text_coverage = intersection_area(left.bbox, right.bbox) / text_area if text_area else 0.0
                if text_coverage >= 0.42:
                    findings.append({"type": "image_text_conflict", "blocks": [left.block_id, right.block_id], "detail": f"overlap={ratio:.2f}, text_coverage={text_coverage:.2f}"})
            elif left.text and right.text and _similar(left, right) >= 0.78:
                findings.append({"type": "duplicate_text", "blocks": [left.block_id, right.block_id], "detail": f"overlap={ratio:.2f}"})
            elif left.text and right.text:
                left_role = str(left.style.get("semantic_role", ""))
                right_role = str(right.style.get("semantic_role", ""))
                if "answer_blank" in {left_role, right_role}:
                    continue
                if max(int(left.style.get("line_count", 1)), int(right.style.get("line_count", 1))) > 1:
                    continue
                findings.append({"type": "high_overlap", "blocks": [left.block_id, right.block_id], "detail": f"overlap={ratio:.2f}"})
    return findings
