"""DOCX generation helpers for editable Word output."""

from __future__ import annotations

from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION
from docx.shared import Emu, Pt
from pypdf import PdfReader

from .errors import OcrRequiredError
from .models import PageSize, PdfKind


EMU_PER_POINT = 12_700


def _set_page_geometry(section: object, size: PageSize) -> None:
    section.page_width = Emu(round(size.width_pt * EMU_PER_POINT))  # type: ignore[attr-defined]
    section.page_height = Emu(round(size.height_pt * EMU_PER_POINT))  # type: ignore[attr-defined]
    section.top_margin = Emu(0)  # type: ignore[attr-defined]
    section.bottom_margin = Emu(0)  # type: ignore[attr-defined]
    section.left_margin = Emu(0)  # type: ignore[attr-defined]
    section.right_margin = Emu(0)  # type: ignore[attr-defined]
    section.header_distance = Emu(0)  # type: ignore[attr-defined]
    section.footer_distance = Emu(0)  # type: ignore[attr-defined]


def _format_page_paragraph(paragraph: object) -> None:
    paragraph.paragraph_format.space_before = Pt(0)  # type: ignore[attr-defined]
    paragraph.paragraph_format.space_after = Pt(0)  # type: ignore[attr-defined]
    paragraph.paragraph_format.line_spacing = 1  # type: ignore[attr-defined]


def _extract_page_text(source: str | Path) -> list[str]:
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        return []
    result: list[str] = []
    for page in reader.pages:
        try:
            result.append((page.extract_text(extraction_mode="layout") or "").strip())
        except TypeError:
            result.append((page.extract_text() or "").strip())
        except Exception:
            result.append("")
    return result


def create_basic_editable_docx(
    source: str | Path,
    *,
    page_sizes: list[PageSize],
    kind: PdfKind,
    page_indices: list[int],
    output_path: str | Path,
) -> Path:
    """Create an editable baseline for PDFs with an actual text layer.

    OCR-driven absolute-positioned layout is intentionally not emulated here.
    For outlined/scanned input callers receive an explicit error until the
    PaddleOCR PageModel adapter is installed and validated.
    """

    texts = _extract_page_text(source)
    selected = [texts[index] if index < len(texts) else "" for index in page_indices]
    if kind in {PdfKind.OUTLINED, PdfKind.SCANNED} or not any(selected):
        raise OcrRequiredError(
            "该 PDF 没有可靠文字层。需要安装并配置 PaddleOCR 后才能生成可编辑 Word。"
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    for position, (page_index, text) in enumerate(zip(page_indices, selected, strict=True)):
        if position == 0:
            section = document.sections[0]
            paragraph = document.add_paragraph()
        else:
            section = document.add_section(WD_SECTION.NEW_PAGE)
            paragraph = document.add_paragraph()
        _set_page_geometry(section, page_sizes[page_index])
        _format_page_paragraph(paragraph)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            paragraph.add_run(lines[0])
            for line in lines[1:]:
                next_paragraph = document.add_paragraph()
                _format_page_paragraph(next_paragraph)
                next_paragraph.add_run(line)
        else:
            paragraph.add_run("[此页未提取到文字]")
    document.save(output)
    return output
