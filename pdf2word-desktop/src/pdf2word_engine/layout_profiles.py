"""Reusable recognition and geometry rules for education-question pages.

The OCR adapter intentionally keeps engine-specific parsing separate from this
module.  A profile is a small, versioned contract that can be selected for a
whole document (or later by classifier confidence), rather than a collection
of one-off DOCX fixes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EducationQuestionLayoutProfile:
    """Rules shared by the current Chinese exam-question page family."""

    profile_id: str = "cn_exam_question_v1"
    # Some data-analysis pages use a bare ``4.`` question marker rather than
    # the usual ``4.（来源）`` form. Both are a pink/bold numbered prefix.
    question_heading_pattern: re.Pattern[str] = re.compile(r"^\s*(?P<number>\d{1,3}[.．、])(?:\s*（[^）]+）)?")
    callout_labels: tuple[str, ...] = ("解析", "答案", "提示")
    answer_pair_gap_px: float = 54.0
    talk_badge_width_px: float = 62.0
    callout_tag_width_px: float = 96.0
    callout_label_gap_px: float = 6.0
    callout_label_width_px: float = 78.0
    callout_content_gap_px: float = 0.0
    sidebar_page_rule_gap_px: float = 5.0
    sidebar_page_rule_width_px: float = 3.0
    sidebar_page_number_extra_right_px: float = 20.0
    sidebar_page_number_top_pad_px: float = 2.0
    sidebar_page_number_bottom_pad_px: float = 5.0

    def match_question_heading(self, text: str) -> re.Match[str] | None:
        return self.question_heading_pattern.match(text)

    def question_heading_style(self, match: re.Match[str]) -> dict[str, object]:
        """Return renderer-neutral semantics for a question heading line."""

        return {
            "layout_profile": self.profile_id,
            "semantic_role": "question_heading",
            "font_size_pt": 8.0,
            "accent_length": len(match.group(0)),
            # Only the numbered marker is bold.  The paper/source descriptor
            # remains the accent colour but must not inherit bold styling.
            "bold_prefix_length": len(match.group("number")),
            "justify_to_bbox": True,
        }

    def right_aligned_text_style(self, role: str) -> dict[str, object]:
        """Preserve the observed right edge without making a raster fallback."""

        return {
            "layout_profile": self.profile_id,
            "semantic_role": role,
            "font_size_pt": 8.0,
            "justify_to_bbox": True,
        }

    def answer_text_bbox(
        self, *, tag_bbox: tuple[float, float, float, float], source_bbox: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        """Place the editable answer on the measured baseline beside its tag."""

        left, top, right, bottom = source_bbox
        tag_right = min(right, tag_bbox[2])
        answer_left = min(right, tag_right + self.callout_content_gap_px)
        return (answer_left, min(bottom - 1, top + self.callout_content_gap_px), right, bottom)

    def sidebar_page_number_bbox(self, bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        left, top, right, bottom = bbox
        return (
            left,
            top - self.sidebar_page_number_top_pad_px,
            right + self.sidebar_page_number_extra_right_px,
            bottom + self.sidebar_page_number_bottom_pad_px,
        )

    def sidebar_rule_bbox(self, bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        _, top, right, bottom = bbox
        return (
            right + self.sidebar_page_rule_gap_px,
            top - 3,
            right + self.sidebar_page_rule_gap_px + self.sidebar_page_rule_width_px,
            bottom + 6,
        )


# The first productized profile is deliberately named by layout family, not by
# source document or page number. Page 10 is its first golden regression case.
CN_EXAM_QUESTION_V1 = EducationQuestionLayoutProfile()
