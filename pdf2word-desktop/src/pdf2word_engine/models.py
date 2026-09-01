"""Stable data contracts shared by the engine, worker and future desktop host."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


# Version 7 separates immutable OCR/layout evidence from the blocks selected
# for Word output.  ``blocks`` remains the canonical output list for backwards
# compatibility; serialized models also expose it as ``output_blocks`` so a
# quality report cannot confuse raw candidates with rendered content.
PAGE_MODEL_SCHEMA_VERSION = 7


class PdfKind(str, Enum):
    BORN_DIGITAL = "born_digital"
    SCANNED = "scanned"
    OUTLINED = "outlined"
    MIXED = "mixed"
    ENCRYPTED = "encrypted"
    DAMAGED = "damaged"


class JobState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class PageSize:
    width_pt: float
    height_pt: float


@dataclass(slots=True)
class PreflightReport:
    source_path: str
    file_size_bytes: int
    page_count: int
    pdf_version: str | None
    encrypted: bool
    tagged: bool | None
    optimized: bool | None
    metadata: dict[str, str] = field(default_factory=dict)
    kind: PdfKind = PdfKind.DAMAGED
    font_resource_pages: int = 0
    xobject_pages: int = 0
    sample_pages: list[int] = field(default_factory=list)
    sample_text_characters: int = 0
    page_sizes: list[PageSize] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self, *, include_page_sizes: bool = True) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.value
        if not include_page_sizes:
            result.pop("page_sizes", None)
        return result


@dataclass(slots=True)
class RenderedPage:
    page_index: int
    image_path: Path
    size: PageSize


@dataclass(slots=True)
class PageBlock:
    """A normalized region emitted by an OCR/layout engine."""

    block_id: str
    block_type: str
    bbox: tuple[float, float, float, float]
    z_index: int
    reading_order: int
    confidence: float | None = None
    text: str | None = None
    style: dict[str, Any] = field(default_factory=dict)
    asset_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    # These are intentionally first-class fields instead of opaque ``style``
    # values.  They make a generated PageModel auditable without retaining a
    # second copy of all raw OCR output.
    source: str | None = None
    selection_reason: str | None = None
    fallback_mode: str | None = None


@dataclass(slots=True)
class PageModel:
    """Versioned engine-independent page contract for future DOCX renderers."""

    schema_version: int
    page_index: int
    size: PageSize
    source_type: PdfKind
    source_image_width_px: int | None = None
    source_image_height_px: int | None = None
    blocks: list[PageBlock] = field(default_factory=list)
    evidence_blocks: list[PageBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    debug_records: list[dict[str, Any]] = field(default_factory=list)
    page_class: str = "ordinary"
    reconstruction_mode: str = "hybrid"
    source_fingerprint: str | None = None

    @property
    def output_blocks(self) -> list[PageBlock]:
        """Blocks selected for the final Word document."""

        return self.blocks

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source_type"] = self.source_type.value
        result["output_blocks"] = result["blocks"]
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PageModel":
        """Load a serialized PageModel without exposing raw OCR payloads."""

        size_value = value.get("size")
        if not isinstance(size_value, Mapping):
            raise ValueError("PageModel 缺少页面尺寸。")
        def parse_blocks(raw_value: object) -> list[PageBlock]:
            parsed: list[PageBlock] = []
            if not isinstance(raw_value, list):
                return parsed
            for raw_block in raw_value:
                if not isinstance(raw_block, Mapping):
                    continue
                bbox_value = raw_block.get("bbox")
                if not isinstance(bbox_value, (list, tuple)) or len(bbox_value) != 4:
                    continue
                parsed.append(
                    PageBlock(
                        block_id=str(raw_block.get("block_id", "unknown")),
                        block_type=str(raw_block.get("block_type", "unknown")),
                        bbox=tuple(float(item) for item in bbox_value),
                        z_index=int(raw_block.get("z_index", 0)),
                        reading_order=int(raw_block.get("reading_order", 0)),
                        confidence=float(raw_block["confidence"]) if raw_block.get("confidence") is not None else None,
                        text=str(raw_block["text"]) if raw_block.get("text") is not None else None,
                        style=dict(raw_block.get("style", {})) if isinstance(raw_block.get("style"), Mapping) else {},
                        asset_path=str(raw_block["asset_path"]) if raw_block.get("asset_path") else None,
                        warnings=[str(item) for item in raw_block.get("warnings", [])] if isinstance(raw_block.get("warnings"), list) else [],
                        source=str(raw_block["source"]) if raw_block.get("source") else None,
                        selection_reason=str(raw_block["selection_reason"]) if raw_block.get("selection_reason") else None,
                        fallback_mode=str(raw_block["fallback_mode"]) if raw_block.get("fallback_mode") else None,
                    )
                )
            return parsed

        raw_blocks = value.get("output_blocks", value.get("blocks", []))
        if not isinstance(raw_blocks, list):
            raise ValueError("PageModel 的 blocks 字段无效。")
        blocks = parse_blocks(raw_blocks)
        evidence_blocks = parse_blocks(value.get("evidence_blocks", []))
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            page_index=int(value.get("page_index", 0)),
            size=PageSize(float(size_value["width_pt"]), float(size_value["height_pt"])),
            source_type=PdfKind(str(value.get("source_type", PdfKind.SCANNED.value))),
            source_image_width_px=int(value["source_image_width_px"]) if value.get("source_image_width_px") else None,
            source_image_height_px=int(value["source_image_height_px"]) if value.get("source_image_height_px") else None,
            blocks=blocks,
            evidence_blocks=evidence_blocks,
            warnings=[str(item) for item in value.get("warnings", [])] if isinstance(value.get("warnings"), list) else [],
            debug_records=[dict(item) for item in value.get("debug_records", []) if isinstance(item, Mapping)],
            page_class=str(value.get("page_class", "ordinary")),
            reconstruction_mode=str(value.get("reconstruction_mode", "hybrid")),
            source_fingerprint=str(value["source_fingerprint"]) if value.get("source_fingerprint") else None,
        )


@dataclass(slots=True)
class ConversionResult:
    job_id: str
    state: JobState
    preflight: PreflightReport
    outputs: list[Path]
    warnings: list[str] = field(default_factory=list)
    quality_report: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "preflight": self.preflight.to_dict(include_page_sizes=False),
            "outputs": [str(path) for path in self.outputs],
            "warnings": self.warnings,
            "quality_report": str(self.quality_report) if self.quality_report else None,
        }
