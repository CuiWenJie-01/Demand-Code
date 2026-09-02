from __future__ import annotations

import pytest

from pdf2word_engine.document_profiles import (
    get_source_document_profile,
    resolve_source_document_profile,
    source_document_profile_from_dict,
)


PROFILE_ID = "banyuetan_xingce_1000_part2_v1"


def test_builtin_profile_is_data_driven_and_exactly_matched() -> None:
    profile = get_source_document_profile(PROFILE_ID)

    assert profile.expected_page_count == 381
    assert profile.style_reference_pages == (7, 8, 9, 10, 21, 23)
    assert len(profile.toc_pages) == 2
    assert len(profile.editable_repairs) == 21
    assert profile.raster_cleanup_policy == "central_neutral_gray_v1"
    assert profile.page_class_for(6) == "chapter_opener"
    assert profile.page_class_for(7) is None
    assert (
        resolve_source_document_profile(
            source_sha256=profile.source_sha256,
            page_count=profile.expected_page_count,
        )
        == profile
    )


def test_profile_is_not_inherited_by_other_files_or_page_counts() -> None:
    profile = get_source_document_profile(PROFILE_ID)

    assert resolve_source_document_profile(source_sha256="0" * 64, page_count=381) is None
    assert resolve_source_document_profile(source_sha256=profile.source_sha256, page_count=380) is None
    assert resolve_source_document_profile(source_sha256=profile.source_sha256, page_count=600) is None


def test_profile_rejects_out_of_range_source_specific_pages() -> None:
    with pytest.raises(ValueError, match="页码越界"):
        source_document_profile_from_dict(
            {
                "profile_id": "invalid",
                "version": 1,
                "match": {"sha256": "a" * 64, "page_count": 3},
                "style_reference_pages": [4],
                "extra_review_pages": [],
                "page_class_overrides": {},
            }
        )
