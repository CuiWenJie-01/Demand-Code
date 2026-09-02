"""Versioned, data-driven profiles for source-specific acceptance knowledge.

Profiles contain facts that are true only for one exact source document.  They
must never be used as generic OCR or reconstruction rules.  Generic engine
code resolves a profile by the source SHA-256 and runtime page count; an
unmatched PDF receives no source-specific page overrides.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Iterable, Mapping


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_PAGE_CLASSES = {
    "blank",
    "cover",
    "table_of_contents",
    "section_divider",
    "chapter_opener",
    "formula_heavy",
    "ordinary_question",
}


@dataclass(frozen=True, slots=True)
class PageClassOverride:
    """A one-based, source-specific page classification assertion."""

    physical_page: int
    page_class: str

    def __post_init__(self) -> None:
        if self.physical_page < 1:
            raise ValueError("源文档配置页码必须从 1 开始。")
        if self.page_class not in _ALLOWED_PAGE_CLASSES:
            raise ValueError(f"未知页面类型：{self.page_class}")


@dataclass(frozen=True, slots=True)
class TocEntrySpec:
    chapter: str
    title: str
    printed_page: str
    physical_page: int


@dataclass(frozen=True, slots=True)
class TocGroupSpec:
    title: str
    title_box: tuple[float, float, float, float] | None
    entry_left: float
    entry_right: float
    entry_start_top: float
    entry_step: float
    entry_height: float
    entries: tuple[TocEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class TocPageSpec:
    physical_page: int
    top_decoration_bottom: float
    groups: tuple[TocGroupSpec, ...]


@dataclass(frozen=True, slots=True)
class EditableRepairSpec:
    """Human-reviewed replacement data; applying it still requires a profile match."""

    physical_page: int
    block_id: str
    bbox: tuple[float, float, float, float]
    text: str
    block_type: str = "editable_paragraph"
    first_line_indent_px: float = 0.0
    tab_stops_px: tuple[float, ...] = ()
    accent_length: int = 0
    font_color: str = "222222"

    @property
    def page_index(self) -> int:
        return self.physical_page - 1


@dataclass(frozen=True, slots=True)
class SourceDocumentProfile:
    """Acceptance metadata bound to one immutable source document."""

    profile_id: str
    version: int
    source_sha256: str
    expected_page_count: int
    style_reference_pages: tuple[int, ...] = ()
    extra_review_pages: tuple[int, ...] = ()
    page_class_overrides: tuple[PageClassOverride, ...] = ()
    editable_repair_set: str | None = None
    raster_cleanup_policy: str | None = None
    remove_detected_watermark_blocks: bool = False
    toc_pages: tuple[TocPageSpec, ...] = ()
    editable_repairs: tuple[EditableRepairSpec, ...] = ()

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("源文档配置缺少 profile_id。")
        if self.version < 1:
            raise ValueError("源文档配置版本必须为正整数。")
        normalized_sha = self.source_sha256.casefold()
        if not _SHA256_RE.fullmatch(normalized_sha):
            raise ValueError("源文档配置的 SHA-256 无效。")
        object.__setattr__(self, "source_sha256", normalized_sha)
        if self.expected_page_count < 1:
            raise ValueError("源文档配置的预期页数必须为正整数。")
        if self.raster_cleanup_policy not in {None, "central_neutral_gray_v1"}:
            raise ValueError(f"未知栅格清理策略：{self.raster_cleanup_policy}")
        self._validate_pages("style_reference_pages", self.style_reference_pages)
        self._validate_pages("extra_review_pages", self.extra_review_pages)
        override_pages = tuple(item.physical_page for item in self.page_class_overrides)
        self._validate_pages("page_class_overrides", override_pages)
        self._validate_pages("toc_pages", tuple(item.physical_page for item in self.toc_pages))
        self._validate_pages("editable_repairs", tuple(item.physical_page for item in self.editable_repairs), allow_duplicates=True)
        for page in self.toc_pages:
            if not 0.0 < page.top_decoration_bottom < 1.0:
                raise ValueError("目录装饰边界必须位于 0..1。")
            for group in page.groups:
                if not group.entries:
                    raise ValueError("目录组不得为空。")
                if group.title_box is not None:
                    _validate_normalized_box(group.title_box, "目录组标题")
                if not 0.0 <= group.entry_left < group.entry_right <= 1.0:
                    raise ValueError("目录条目水平边界无效。")
                if group.entry_step <= 0.0 or group.entry_height <= 0.0:
                    raise ValueError("目录条目间距与高度必须为正数。")
                last_bottom = group.entry_start_top + (len(group.entries) - 1) * group.entry_step + group.entry_height
                if group.entry_start_top < 0.0 or last_bottom > 1.0:
                    raise ValueError("目录条目纵向坐标越界。")
                invalid_targets = [
                    entry.physical_page
                    for entry in group.entries
                    if entry.physical_page < 1 or entry.physical_page > self.expected_page_count
                ]
                if invalid_targets:
                    raise ValueError(f"目录目标页码越界：{invalid_targets}")
        for repair in self.editable_repairs:
            _validate_box(repair.bbox, "人工审校修复")
            if not repair.block_id or not repair.text:
                raise ValueError("人工审校修复缺少 block_id 或 text。")
            if repair.first_line_indent_px < 0.0 or repair.accent_length < 0:
                raise ValueError("人工审校修复的缩进或强调长度不能为负数。")
            if any(stop < 0.0 for stop in repair.tab_stops_px):
                raise ValueError("人工审校修复的制表位不能为负数。")

    def _validate_pages(
        self,
        field_name: str,
        pages: tuple[int, ...],
        *,
        allow_duplicates: bool = False,
    ) -> None:
        if not allow_duplicates and len(set(pages)) != len(pages):
            raise ValueError(f"源文档配置 {field_name} 含重复页码。")
        invalid = [page for page in pages if page < 1 or page > self.expected_page_count]
        if invalid:
            raise ValueError(f"源文档配置 {field_name} 页码越界：{invalid}")

    def matches(self, *, source_sha256: str, page_count: int) -> bool:
        """Return true only when both immutable source facts match."""

        return source_sha256.casefold() == self.source_sha256 and page_count == self.expected_page_count

    @property
    def style_reference_page_indices(self) -> tuple[int, ...]:
        return tuple(page - 1 for page in self.style_reference_pages)

    @property
    def extra_review_page_indices(self) -> tuple[int, ...]:
        return tuple(page - 1 for page in self.extra_review_pages)

    def page_class_for(self, page_index: int) -> str | None:
        physical_page = page_index + 1
        return next(
            (item.page_class for item in self.page_class_overrides if item.physical_page == physical_page),
            None,
        )

    def toc_page_for(self, page_index: int) -> TocPageSpec | None:
        physical_page = page_index + 1
        return next((item for item in self.toc_pages if item.physical_page == physical_page), None)

    def editable_repairs_for(self, page_index: int) -> tuple[EditableRepairSpec, ...]:
        return tuple(item for item in self.editable_repairs if item.page_index == page_index)

    def to_manifest_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "source_sha256": self.source_sha256,
            "expected_page_count": self.expected_page_count,
            "style_reference_pages": list(self.style_reference_pages),
            "extra_review_pages": list(self.extra_review_pages),
            "page_class_overrides": {
                str(item.physical_page): item.page_class for item in self.page_class_overrides
            },
            "editable_repair_set": self.editable_repair_set,
            "raster_cleanup_policy": self.raster_cleanup_policy,
            "remove_detected_watermark_blocks": self.remove_detected_watermark_blocks,
            "toc_pages": [item.physical_page for item in self.toc_pages],
            "editable_repair_count": len(self.editable_repairs),
        }


def source_document_profile_from_dict(value: Mapping[str, object]) -> SourceDocumentProfile:
    match = value.get("match")
    if not isinstance(match, Mapping):
        raise ValueError("源文档配置缺少 match。")
    raw_overrides = value.get("page_class_overrides", {})
    if not isinstance(raw_overrides, Mapping):
        raise ValueError("源文档配置 page_class_overrides 必须是对象。")
    overrides = tuple(
        PageClassOverride(physical_page=int(page), page_class=str(page_class))
        for page, page_class in sorted(raw_overrides.items(), key=lambda item: int(item[0]))
    )
    toc_pages = _toc_pages_from_value(value.get("toc_pages", ()))
    editable_repairs = _editable_repairs_from_value(value.get("editable_repairs", ()))
    return SourceDocumentProfile(
        profile_id=str(value.get("profile_id", "")),
        version=int(value.get("version", 0)),
        source_sha256=str(match.get("sha256", "")),
        expected_page_count=int(match.get("page_count", 0)),
        style_reference_pages=_positive_page_tuple(value.get("style_reference_pages", ())),
        extra_review_pages=_positive_page_tuple(value.get("extra_review_pages", ())),
        page_class_overrides=overrides,
        editable_repair_set=(
            str(value["editable_repair_set"]) if value.get("editable_repair_set") else None
        ),
        raster_cleanup_policy=(
            str(value["raster_cleanup_policy"]) if value.get("raster_cleanup_policy") else None
        ),
        remove_detected_watermark_blocks=bool(value.get("remove_detected_watermark_blocks", False)),
        toc_pages=toc_pages,
        editable_repairs=editable_repairs,
    )


def _positive_page_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("源文档配置页码集合必须是数组。")
    return tuple(int(page) for page in value)


def _box(value: object, field_name: str) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{field_name} 必须包含四个坐标。")
    result = tuple(float(item) for item in value)
    _validate_box(result, field_name)
    return result


def _validate_box(box: tuple[float, float, float, float], field_name: str) -> None:
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f"{field_name} 坐标无效。")


def _validate_normalized_box(box: tuple[float, float, float, float], field_name: str) -> None:
    _validate_box(box, field_name)
    if any(value < 0.0 or value > 1.0 for value in box):
        raise ValueError(f"{field_name} 坐标必须位于 0..1。")


def _toc_pages_from_value(value: object) -> tuple[TocPageSpec, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("toc_pages 必须是数组。")
    pages: list[TocPageSpec] = []
    for raw_page in value:
        if not isinstance(raw_page, Mapping):
            raise ValueError("toc_pages 条目必须是对象。")
        raw_groups = raw_page.get("groups", ())
        if not isinstance(raw_groups, (list, tuple)):
            raise ValueError("目录页 groups 必须是数组。")
        groups: list[TocGroupSpec] = []
        for raw_group in raw_groups:
            if not isinstance(raw_group, Mapping):
                raise ValueError("目录组必须是对象。")
            raw_entries = raw_group.get("entries", ())
            if not isinstance(raw_entries, (list, tuple)):
                raise ValueError("目录组 entries 必须是数组。")
            entries: list[TocEntrySpec] = []
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, Mapping):
                    raise ValueError("目录条目必须是对象。")
                entries.append(
                    TocEntrySpec(
                        chapter=str(raw_entry.get("chapter", "")),
                        title=str(raw_entry.get("title", "")),
                        printed_page=str(raw_entry.get("printed_page", "")),
                        physical_page=int(raw_entry.get("physical_page", 0)),
                    )
                )
            raw_title_box = raw_group.get("title_box")
            title_box = _box(raw_title_box, "目录组标题") if raw_title_box is not None else None
            groups.append(
                TocGroupSpec(
                    title=str(raw_group.get("title", "")),
                    title_box=title_box,
                    entry_left=float(raw_group.get("entry_left", 0.0)),
                    entry_right=float(raw_group.get("entry_right", 0.0)),
                    entry_start_top=float(raw_group.get("entry_start_top", 0.0)),
                    entry_step=float(raw_group.get("entry_step", 0.0)),
                    entry_height=float(raw_group.get("entry_height", 0.0)),
                    entries=tuple(entries),
                )
            )
        pages.append(
            TocPageSpec(
                physical_page=int(raw_page.get("physical_page", 0)),
                top_decoration_bottom=float(raw_page.get("top_decoration_bottom", 0.0)),
                groups=tuple(groups),
            )
        )
    return tuple(pages)


def _editable_repairs_from_value(value: object) -> tuple[EditableRepairSpec, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("editable_repairs 必须是数组。")
    repairs: list[EditableRepairSpec] = []
    for raw_repair in value:
        if not isinstance(raw_repair, Mapping):
            raise ValueError("editable_repairs 条目必须是对象。")
        repairs.append(
            EditableRepairSpec(
                physical_page=int(raw_repair.get("physical_page", 0)),
                block_id=str(raw_repair.get("block_id", "")),
                bbox=_box(raw_repair.get("bbox"), "人工审校修复"),
                text=str(raw_repair.get("text", "")),
                block_type=str(raw_repair.get("block_type", "editable_paragraph")),
                first_line_indent_px=float(raw_repair.get("first_line_indent_px", 0.0)),
                tab_stops_px=tuple(float(item) for item in raw_repair.get("tab_stops_px", ())),
                accent_length=int(raw_repair.get("accent_length", 0)),
                font_color=str(raw_repair.get("font_color", "222222")),
            )
        )
    return tuple(repairs)


@lru_cache(maxsize=1)
def load_builtin_source_document_profiles() -> tuple[SourceDocumentProfile, ...]:
    """Load shipped profile data without importing book-specific Python code."""

    profile_root = files("pdf2word_engine").joinpath("profiles")
    loaded: list[SourceDocumentProfile] = []
    for resource in sorted(profile_root.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".json"):
            continue
        payload = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"源文档配置根节点必须是对象：{resource.name}")
        loaded.append(source_document_profile_from_dict(payload))
    profile_ids = [profile.profile_id for profile in loaded]
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("内置源文档配置含重复 profile_id。")
    return tuple(loaded)


def resolve_source_document_profile(
    *,
    source_sha256: str,
    page_count: int,
    profiles: Iterable[SourceDocumentProfile] | None = None,
) -> SourceDocumentProfile | None:
    """Resolve an exact source profile; generic PDFs intentionally return none."""

    candidates = tuple(profiles) if profiles is not None else load_builtin_source_document_profiles()
    matches = [
        profile
        for profile in candidates
        if profile.matches(source_sha256=source_sha256, page_count=page_count)
    ]
    if len(matches) > 1:
        raise ValueError("同一源 PDF 匹配到多个配置，拒绝使用不确定规则。")
    return matches[0] if matches else None


def get_source_document_profile(profile_id: str) -> SourceDocumentProfile:
    matches = [
        profile for profile in load_builtin_source_document_profiles() if profile.profile_id == profile_id
    ]
    if not matches:
        raise KeyError(f"未知源文档配置：{profile_id}")
    return matches[0]
