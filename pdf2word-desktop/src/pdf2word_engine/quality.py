"""Quality-report, OCR accuracy and raster-comparison primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any
import unicodedata

from PIL import Image

from .conflicts import overlap_ratio, static_page_checks
from .models import PageBlock, PageModel


@dataclass(frozen=True, slots=True)
class VisualComparison:
    same_dimensions: bool
    ssim: float
    mean_absolute_error: float


@dataclass(frozen=True, slots=True)
class CharacterErrorRate:
    """A reproducible CER result based on human-approved reference text."""

    reference_characters: int
    errors: int
    cer: float


def is_allowed_decorative_image(model: PageModel, block: PageBlock) -> bool:
    """Return whether an image is decoration rather than editable body content."""

    if not block.asset_path:
        return False
    width = max(1.0, float(model.source_image_width_px or model.size.width_pt))
    height = max(1.0, float(model.source_image_height_px or model.size.height_pt))
    left, top, right, bottom = block.bbox
    block_width = max(0.0, right - left)
    block_height = max(0.0, bottom - top)
    block_type = block.block_type.lower()
    fallback_mode = (block.fallback_mode or "").lower()
    text = normalize_cer_text(block.text or "")

    if fallback_mode in {
        "chapter_header_source_image",
        "sidebar_source_image",
        "sidebar_page_number_source_image",
        "source_decoration_strip",
    }:
        return True
    if block_type in {"header", "logo"} and top <= height * 0.12:
        return True
    is_talk_badge = (
        block_type in {"talk_badge_image", "talk_callout_tag_image"}
        or text == "谈"
        or "talk_badge" in fallback_mode
    )
    return bool(
        is_talk_badge
        and left <= width * 0.30
        and block_width <= width * 0.08
        and block_height <= height * 0.10
    )


def body_image_blocks(model: PageModel) -> list[PageBlock]:
    """Return image-backed blocks that occupy document body content."""

    return [
        block
        for block in model.blocks
        if block.asset_path and not is_allowed_decorative_image(model, block)
    ]


def assert_body_content_editable(models: list[PageModel]) -> None:
    """Reject a candidate before DOCX creation if any body content is an image."""

    failures = [
        (model.page_index + 1, block.block_id, block.fallback_mode or block.block_type)
        for model in models
        for block in body_image_blocks(model)
    ]
    if failures:
        details = ", ".join(f"第{page}页 {block_id}({mode})" for page, block_id, mode in failures)
        raise ValueError(f"正文零图片门禁失败：{details}")


def normalize_cer_text(value: str) -> str:
    """Normalise only presentation differences that must not count as OCR errors."""

    return "".join(unicodedata.normalize("NFKC", value).split())


def character_error_rate(reference: str, actual: str) -> CharacterErrorRate:
    """Return Levenshtein CER; an empty reference is an invalid evaluation."""

    expected = normalize_cer_text(reference)
    observed = normalize_cer_text(actual)
    if not expected:
        raise ValueError("CER 标注文本不能为空，不能用 OCR 输出自身作为参考答案。")
    previous = list(range(len(observed) + 1))
    for index, expected_character in enumerate(expected, start=1):
        current = [index]
        for observed_index, observed_character in enumerate(observed, start=1):
            current.append(
                min(
                    previous[observed_index] + 1,
                    current[observed_index - 1] + 1,
                    previous[observed_index - 1] + (expected_character != observed_character),
                )
            )
        previous = current
    errors = previous[-1]
    return CharacterErrorRate(len(expected), errors, errors / len(expected))


def editable_quality_report(models: list[PageModel]) -> dict[str, Any]:
    """Summarize editability and image fallbacks without exposing OCR text."""

    pages: list[dict[str, Any]] = []
    total_text_blocks = 0
    total_fallback_blocks = 0
    conflict_pages: list[int] = []
    formula_pages: list[int] = []
    full_page_fallbacks: list[int] = []
    low_confidence_pages: list[int] = []
    automatic_repairs = 0
    coverage_failures: list[int] = []
    page_coverages: list[float] = []
    source_completeness_repair_pages: list[int] = []
    width_fit_pages: list[int] = []
    body_image_failure_pages: list[int] = []
    total_body_image_blocks = 0
    for model in sorted(models, key=lambda item: item.page_index):
        fallback_blocks = [
            {
                "block_id": block.block_id,
                "block_type": block.block_type,
                "bbox": [round(value, 2) for value in block.bbox],
                "fallback_mode": block.fallback_mode,
                "selection_reason": block.selection_reason,
                "source": block.source,
            }
            for block in model.blocks
            if block.asset_path
        ]
        body_fallbacks = body_image_blocks(model)
        if body_fallbacks:
            body_image_failure_pages.append(model.page_index + 1)
            total_body_image_blocks += len(body_fallbacks)
        editable_text_blocks = sum(1 for block in model.blocks if block.text and not block.asset_path)
        total_text_blocks += editable_text_blocks
        total_fallback_blocks += len(fallback_blocks)
        findings = static_page_checks(model)
        conflicts = [item for item in findings if item["type"] in {"duplicate_text", "image_text_conflict"}]
        overlap_warnings = [item for item in findings if item["type"] == "high_overlap"]
        low_confidence = [item for item in findings if item["type"] == "low_confidence"]
        automatic_repairs += len(model.debug_records)
        excluded_owner_types = {
            "formula",
            "decoration_image",
            "figure",
            "chart",
            "table",
            "logo",
            "talk_badge_image",
            "talk_callout_tag_image",
            "image",
            "region_fallback_image",
            "source_uncovered_region",
        }
        excluded_owners = [
            block
            for block in model.blocks
            if block.asset_path and block.block_type.lower() in excluded_owner_types
        ]
        evidence_seen: set[tuple[str, tuple[int, int, int, int]]] = set()
        denominator = 0
        for block in model.evidence_blocks:
            normalized = normalize_cer_text(block.text or "")
            if not normalized:
                continue
            key = (normalized, tuple(round(item) for item in block.bbox))
            if key in evidence_seen:
                continue
            evidence_seen.add(key)
            if any(overlap_ratio(block, owner) >= 0.20 for owner in excluded_owners):
                continue
            denominator += len(normalized)
        editable_characters = sum(
            len(normalize_cer_text(block.text or ""))
            for block in model.blocks
            if block.text and not block.asset_path
        )
        if denominator <= 0:
            coverage = 1.0 if editable_characters or model.page_class in {"blank", "cover", "section_divider"} else 0.0
        else:
            coverage = min(1.0, editable_characters / denominator)
        page_coverages.append(coverage)
        threshold = 0.85 if model.page_class == "ordinary_question" else 0.80 if model.page_class == "chapter_opener" else 0.0
        coverage_passed = coverage + 1e-9 >= threshold
        if not coverage_passed:
            coverage_failures.append(model.page_index + 1)
        page_area = max(1.0, (model.source_image_width_px or model.size.width_pt) * (model.source_image_height_px or model.size.height_pt))
        image_area_coverage = min(
            1.0,
            sum(max(0.0, block.bbox[2] - block.bbox[0]) * max(0.0, block.bbox[3] - block.bbox[1]) for block in model.blocks if block.asset_path) / page_area,
        )
        if conflicts:
            conflict_pages.append(model.page_index + 1)
        if low_confidence:
            low_confidence_pages.append(model.page_index + 1)
        explicit_formula_fallback = any(
            block.block_type == "formula" and block.asset_path for block in model.blocks
        )
        formula_heavy_source_crop = model.page_class == "formula_heavy" and any(
            block.asset_path
            and block.fallback_mode
            in {
                "callout_first_row_source_image",
                "formula_row_source_image",
                "formula_line_source_image",
                "region_source_image_after_static_gate",
            }
            for block in model.blocks
        )
        if explicit_formula_fallback or formula_heavy_source_crop:
            formula_pages.append(model.page_index + 1)
        if any(block.fallback_mode == "uncovered_source_region_image" for block in model.blocks):
            source_completeness_repair_pages.append(model.page_index + 1)
        if any(record.get("action") == "editable_width_fit" for record in model.debug_records):
            width_fit_pages.append(model.page_index + 1)
        if any(block.block_type == "full_page_fallback" for block in model.blocks):
            full_page_fallbacks.append(model.page_index + 1)
        pages.append(
            {
                "page": model.page_index + 1,
                "schema_version": model.schema_version,
                "source_type": model.source_type.value,
                "page_class": model.page_class,
                "reconstruction_mode": model.reconstruction_mode,
                "editable_text_blocks": editable_text_blocks,
                "editable_characters": editable_characters,
                "editable_character_coverage": round(coverage, 4),
                "editable_coverage_threshold": threshold,
                "editable_coverage_gate": "passed" if coverage_passed else "failed",
                "image_area_coverage": round(image_area_coverage, 4),
                "image_fallback_blocks": fallback_blocks,
                "body_image_blocks": [block.block_id for block in body_fallbacks],
                "body_editability_gate": "passed" if not body_fallbacks else "failed",
                "warnings": model.warnings,
                "static_findings": findings,
                "conflict_decisions": model.debug_records,
                "overlap_warnings": overlap_warnings,
            }
        )
    return {
        "schema_version": 2,
        "quality_state": "static_and_editability_checks_passed" if not conflict_pages and not coverage_failures and not body_image_failure_pages else "requires_review",
        "pages": pages,
        "summary": {
            "page_count": len(pages),
            "editable_text_blocks": total_text_blocks,
            "image_fallback_blocks": total_fallback_blocks,
            "body_image_blocks": total_body_image_blocks,
            "body_image_failure_pages": body_image_failure_pages,
            "conflict_pages": conflict_pages,
            "overlap_warning_pages": [page["page"] for page in pages if page["overlap_warnings"]],
            "formula_fallback_pages": formula_pages,
            "full_page_fallback_pages": full_page_fallbacks,
            "low_confidence_pages": low_confidence_pages,
            "source_completeness_repair_pages": source_completeness_repair_pages,
            "editable_width_fit_pages": width_fit_pages,
            "editable_coverage_failure_pages": coverage_failures,
            "mean_editable_character_coverage": round(fmean(page_coverages), 4) if page_coverages else 0.0,
            "automatic_repairs": automatic_repairs,
            "manual_sampling_pages": sorted(
                set(
                    conflict_pages
                    + low_confidence_pages
                    + formula_pages
                    + full_page_fallbacks
                    + source_completeness_repair_pages
                    + width_fit_pages
                )
            ),
            "source_word_render_difference": "generated by the current source-first end-to-end sampling gate; static completion does not imply a full-book raster pass",
        },
    }


def compare_rasters(expected: str | Path, actual: str | Path, *, max_side: int = 1024) -> VisualComparison:
    """Compare page images using global SSIM and MAE without a NumPy dependency.

    The comparator is intentionally deterministic and suitable for a regression
    gate. Production reports can add region masks for Word anti-aliasing later.
    """

    with Image.open(expected) as left_source, Image.open(actual) as right_source:
        same_dimensions = left_source.size == right_source.size
        left = left_source.convert("L")
        right = right_source.convert("L")
        if right.size != left.size:
            right = right.resize(left.size, Image.Resampling.LANCZOS)
        if max(left.size) > max_side:
            scale = max_side / max(left.size)
            size = (max(1, round(left.width * scale)), max(1, round(left.height * scale)))
            left = left.resize(size, Image.Resampling.LANCZOS)
            right = right.resize(size, Image.Resampling.LANCZOS)
        x = list(left.getdata())
        y = list(right.getdata())

    x_mean = fmean(x)
    y_mean = fmean(y)
    x_var = fmean((value - x_mean) ** 2 for value in x)
    y_var = fmean((value - y_mean) ** 2 for value in y)
    covariance = fmean((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True))
    c1 = 6.5025
    c2 = 58.5225
    denominator = (x_mean**2 + y_mean**2 + c1) * (x_var + y_var + c2)
    ssim = 1.0 if denominator == 0 else ((2 * x_mean * y_mean + c1) * (2 * covariance + c2)) / denominator
    mae = fmean(abs(a - b) for a, b in zip(x, y, strict=True))
    return VisualComparison(same_dimensions=same_dimensions, ssim=max(-1.0, min(1.0, ssim)), mean_absolute_error=mae)
