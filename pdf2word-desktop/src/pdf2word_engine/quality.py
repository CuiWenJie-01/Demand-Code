"""Raster comparison primitives for DOCX visual-regression validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from PIL import Image


@dataclass(frozen=True, slots=True)
class VisualComparison:
    same_dimensions: bool
    ssim: float
    mean_absolute_error: float


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
