"""Deterministic, document-agnostic selection for a task's dynamic canary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .document_profiles import SourceDocumentProfile


@dataclass(frozen=True, slots=True)
class PageInventoryRecord:
    """Low-cost facts collected for one physical page before full OCR."""

    page_index: int
    page_type: str
    layout_cluster: str
    chapter: str | None = None
    reconstruction_mode: str = "unknown"
    risk_features: tuple[str, ...] = ()
    risk_score: float = 0.0
    cluster_distance: float = 0.0
    is_unknown: bool = False
    is_outlier: bool = False

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError("page_index 不能为负数。")
        if not self.page_type.strip():
            raise ValueError("页面普查记录缺少 page_type。")
        if not self.layout_cluster.strip():
            raise ValueError("页面普查记录缺少 layout_cluster。")
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError("risk_score 必须位于 0..1。")
        if self.cluster_distance < 0.0:
            raise ValueError("cluster_distance 不能为负数。")


@dataclass(frozen=True, slots=True)
class DynamicSamplingPolicy:
    """Versioned selection policy; values are task parameters, not page fixes."""

    policy_id: str = "dynamic_canary_v1"
    high_risk_threshold: float = 0.85
    include_first_and_last: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.high_risk_threshold <= 1.0:
            raise ValueError("高风险阈值必须位于 0..1。")


@dataclass(frozen=True, slots=True)
class DynamicSamplingSelection:
    policy_id: str
    page_count: int
    page_indices: tuple[int, ...]
    reasons: tuple[tuple[int, tuple[str, ...]], ...]
    coverage_keys: tuple[tuple[int, tuple[str, ...]], ...]

    @property
    def physical_pages(self) -> tuple[int, ...]:
        return tuple(index + 1 for index in self.page_indices)

    def to_manifest_dict(self) -> dict[str, object]:
        reason_map = dict(self.reasons)
        coverage_map = dict(self.coverage_keys)
        return {
            "selector_version": self.policy_id,
            "page_count": self.page_count,
            "dynamic_canary_pages": [
                {
                    "page": index + 1,
                    "reasons": list(reason_map[index]),
                    "coverage_keys": list(coverage_map[index]),
                }
                for index in self.page_indices
            ],
        }


def select_dynamic_canary_pages(
    inventory: Iterable[PageInventoryRecord],
    *,
    policy: DynamicSamplingPolicy | None = None,
    source_profile: SourceDocumentProfile | None = None,
    source_sha256: str | None = None,
) -> DynamicSamplingSelection:
    """Select a deterministic canary from a complete current-run inventory.

    Every grouping rule is based on observed page features.  A source profile
    may add review pages only after the caller has resolved it by exact source
    fingerprint and page count.
    """

    active_policy = policy or DynamicSamplingPolicy()
    records = sorted(inventory, key=lambda item: item.page_index)
    if not records:
        raise ValueError("动态抽样需要完整且非空的全量页面普查。")
    expected_indices = list(range(len(records)))
    actual_indices = [item.page_index for item in records]
    if actual_indices != expected_indices:
        raise ValueError("全量页面普查必须恰好覆盖连续物理页 1..N。")
    page_count = len(records)
    if source_profile is not None and (
        source_sha256 is None
        or not source_profile.matches(source_sha256=source_sha256, page_count=page_count)
    ):
        raise ValueError("源文档验收配置未与当前源指纹和全量普查页数完整匹配。")

    selected_reasons: dict[int, set[str]] = {}
    selected_coverage: dict[int, set[str]] = {}

    def add(record: PageInventoryRecord, reason: str, coverage_key: str) -> None:
        selected_reasons.setdefault(record.page_index, set()).add(reason)
        selected_coverage.setdefault(record.page_index, set()).add(coverage_key)

    if active_policy.include_first_and_last:
        add(records[0], "first_physical_page", "position:first")
        add(records[-1], "last_physical_page", "position:last")

    for record in records:
        if record.page_type in {"cover", "table_of_contents"}:
            add(record, f"detected_{record.page_type}", f"page_type:{record.page_type}")
        if record.is_unknown:
            add(record, "unknown_page_type", "risk:unknown_page_type")
        if record.is_outlier:
            add(record, "layout_cluster_outlier", "risk:layout_cluster_outlier")
        if record.risk_score >= active_policy.high_risk_threshold:
            add(record, "high_risk_score", "risk:high_score")

    if source_profile is not None:
        for page_index in source_profile.extra_review_page_indices:
            add(
                records[page_index],
                f"source_profile:{source_profile.profile_id}",
                "source_profile:extra_review",
            )

    def add_group_representatives(attribute: str, prefix: str) -> None:
        grouped: dict[str, list[PageInventoryRecord]] = {}
        for record in records:
            raw_value = getattr(record, attribute)
            if raw_value is None or not str(raw_value).strip():
                continue
            grouped.setdefault(str(raw_value), []).append(record)
        for value, group in sorted(grouped.items()):
            representative = min(
                group,
                key=lambda item: (item.cluster_distance, -item.risk_score, item.page_index),
            )
            add(representative, f"representative_{prefix}", f"{prefix}:{value}")

    add_group_representatives("page_type", "page_type")
    add_group_representatives("layout_cluster", "layout_cluster")
    add_group_representatives("chapter", "chapter")
    add_group_representatives("reconstruction_mode", "reconstruction_mode")

    clusters: dict[str, list[PageInventoryRecord]] = {}
    features: dict[str, list[PageInventoryRecord]] = {}
    for record in records:
        clusters.setdefault(record.layout_cluster, []).append(record)
        for feature in set(record.risk_features):
            features.setdefault(feature, []).append(record)
    for cluster, group in sorted(clusters.items()):
        highest_risk = min(group, key=lambda item: (-item.risk_score, item.page_index))
        add(highest_risk, "highest_risk_in_layout_cluster", f"layout_cluster_risk:{cluster}")
    for feature, group in sorted(features.items()):
        representative = min(group, key=lambda item: (-item.risk_score, item.page_index))
        add(representative, "risk_feature_coverage", f"risk_feature:{feature}")

    page_indices = tuple(sorted(selected_reasons))
    return DynamicSamplingSelection(
        policy_id=active_policy.policy_id,
        page_count=page_count,
        page_indices=page_indices,
        reasons=tuple(
            (index, tuple(sorted(selected_reasons[index]))) for index in page_indices
        ),
        coverage_keys=tuple(
            (index, tuple(sorted(selected_coverage[index]))) for index in page_indices
        ),
    )
