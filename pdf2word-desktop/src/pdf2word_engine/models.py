"""Stable data contracts shared by the engine, worker and future desktop host."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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


@dataclass(slots=True)
class PageModel:
    """Versioned engine-independent page contract for future DOCX renderers."""

    schema_version: int
    page_index: int
    size: PageSize
    source_type: PdfKind
    blocks: list[PageBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source_type"] = self.source_type.value
        return result


@dataclass(slots=True)
class ConversionResult:
    job_id: str
    state: JobState
    preflight: PreflightReport
    outputs: list[Path]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "preflight": self.preflight.to_dict(include_page_sizes=False),
            "outputs": [str(path) for path in self.outputs],
            "warnings": self.warnings,
        }
