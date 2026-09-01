"""Quality-report, OCR accuracy and raster-comparison primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any
import unicodedata

from PIL import Image

from .models import PageModel


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


def model_text_for_cer(model: PageModel, block_ids: list[str] | None = None) -> str:
    """Extract only editable text in reading order for comparison with a transcript."""

    selected = set(block_ids or [])
    blocks = sorted(model.blocks, key=lambda block: (block.reading_order, block.z_index, block.block_id))
    return "".join(
        block.text or ""
        for block in blocks
        if block.text and not block.asset_path and (not selected or block.block_id in selected)
    )


def editable_quality_report(models: list[PageModel]) -> dict[str, Any]:
    """Summarize editability and image fallbacks without exposing OCR text."""

    pages: list[dict[str, Any]] = []
    total_text_blocks = 0
    total_fallback_blocks = 0
    for model in sorted(models, key=lambda item: item.page_index):
        fallback_blocks = [
            {"block_id": block.block_id, "block_type": block.block_type}
            for block in model.blocks
            if block.asset_path
        ]
        editable_text_blocks = sum(1 for block in model.blocks if block.text and not block.asset_path)
        total_text_blocks += editable_text_blocks
        total_fallback_blocks += len(fallback_blocks)
        pages.append(
            {
                "page": model.page_index + 1,
                "schema_version": model.schema_version,
                "source_type": model.source_type.value,
                "editable_text_blocks": editable_text_blocks,
                "image_fallback_blocks": fallback_blocks,
                "warnings": model.warnings,
            }
        )
    return {
        "schema_version": 1,
        "pages": pages,
        "summary": {
            "page_count": len(pages),
            "editable_text_blocks": total_text_blocks,
            "image_fallback_blocks": total_fallback_blocks,
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
