from __future__ import annotations

import pytest

from pdf2word_engine.document_profiles import get_source_document_profile
from pdf2word_engine.dynamic_sampling import (
    PageInventoryRecord,
    select_dynamic_canary_pages,
)


def record(
    page_index: int,
    *,
    page_type: str = "ordinary_question",
    cluster: str = "ordinary",
    chapter: str | None = "chapter-1",
    mode: str = "editable_paragraphs",
    risk_score: float = 0.0,
    risk_features: tuple[str, ...] = (),
    is_unknown: bool = False,
    is_outlier: bool = False,
    distance: float = 0.0,
) -> PageInventoryRecord:
    return PageInventoryRecord(
        page_index=page_index,
        page_type=page_type,
        layout_cluster=cluster,
        chapter=chapter,
        reconstruction_mode=mode,
        risk_score=risk_score,
        risk_features=risk_features,
        is_unknown=is_unknown,
        is_outlier=is_outlier,
        cluster_distance=distance,
    )


def test_single_page_document_is_valid_and_selected_once() -> None:
    selection = select_dynamic_canary_pages([record(0)])

    assert selection.page_count == 1
    assert selection.physical_pages == (1,)
    reasons = dict(selection.reasons)[0]
    assert "first_physical_page" in reasons
    assert "last_physical_page" in reasons


def test_selection_uses_observed_types_clusters_and_risks() -> None:
    inventory = [
        record(0, page_type="cover", cluster="cover", chapter=None),
        record(1, page_type="table_of_contents", cluster="toc", chapter=None),
        record(2, cluster="ordinary", distance=0.0),
        record(3, cluster="ordinary", risk_score=0.92, risk_features=("formula",), distance=0.2),
        record(4, cluster="unknown", is_unknown=True, is_outlier=True),
    ]

    selection = select_dynamic_canary_pages(inventory)
    manifest = selection.to_manifest_dict()

    assert selection.physical_pages == (1, 2, 3, 4, 5)
    assert manifest["page_count"] == 5
    page_four = next(item for item in manifest["dynamic_canary_pages"] if item["page"] == 4)
    assert "high_risk_score" in page_four["reasons"]
    assert "risk_feature:formula" in page_four["coverage_keys"]


def test_source_profile_requires_exact_hash_and_page_count() -> None:
    profile = get_source_document_profile("banyuetan_xingce_1000_part2_v1")
    inventory = [record(index) for index in range(381)]

    with pytest.raises(ValueError, match="完整匹配"):
        select_dynamic_canary_pages(
            inventory,
            source_profile=profile,
            source_sha256="0" * 64,
        )

    selection = select_dynamic_canary_pages(
        inventory,
        source_profile=profile,
        source_sha256=profile.source_sha256,
    )
    assert {7, 21, 23}.issubset(selection.physical_pages)


def test_larger_unknown_document_does_not_inherit_current_book_pages() -> None:
    inventory = [record(index) for index in range(382)]

    selection = select_dynamic_canary_pages(inventory)

    assert selection.physical_pages == (1, 382)
    assert 7 not in selection.physical_pages
    assert 21 not in selection.physical_pages
    assert 23 not in selection.physical_pages


def test_inventory_must_cover_every_page_exactly_once() -> None:
    with pytest.raises(ValueError, match="1..N"):
        select_dynamic_canary_pages([record(0), record(2)])
