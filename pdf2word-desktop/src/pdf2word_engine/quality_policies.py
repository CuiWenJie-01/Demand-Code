"""Versioned quality thresholds kept separate from report implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EditableCoveragePolicy:
    """Resolve editable-character coverage by semantic page class."""

    policy_id: str
    default_threshold: float
    page_class_thresholds: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("质量策略缺少 policy_id。")
        values = (self.default_threshold, *(value for _, value in self.page_class_thresholds))
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError("可编辑覆盖率阈值必须位于 0..1。")
        names = [name for name, _ in self.page_class_thresholds]
        if len(names) != len(set(names)):
            raise ValueError("质量策略含重复页面类型。")

    def threshold_for(self, page_class: str) -> float:
        return next(
            (value for name, value in self.page_class_thresholds if name == page_class),
            self.default_threshold,
        )


# Backwards-compatible policy for the already accepted six-page candidate.
# It is explicitly named so the future full-document entry cannot silently
# mistake pilot exemptions for the generic production threshold.
EDITABLE_PILOT_COVERAGE_V1 = EditableCoveragePolicy(
    policy_id="editable_pilot_coverage_v1",
    default_threshold=0.0,
    page_class_thresholds=(
        ("ordinary_question", 0.85),
        ("chapter_opener", 0.80),
    ),
)


# Intended baseline for a formal full-document task.  Non-body publishing pages
# are exempt; every unknown or content-bearing class defaults to the strict
# threshold instead of passing at zero.
STRICT_FULL_DOCUMENT_COVERAGE_V1 = EditableCoveragePolicy(
    policy_id="strict_full_document_coverage_v1",
    default_threshold=0.85,
    page_class_thresholds=(
        ("blank", 0.0),
        ("cover", 0.0),
        ("section_divider", 0.0),
        ("table_of_contents", 0.80),
        ("chapter_opener", 0.80),
    ),
)
