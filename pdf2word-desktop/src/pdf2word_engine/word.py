"""DOCX generation helpers for editable Word output."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, RGBColor
from pypdf import PdfReader

from .errors import OcrRequiredError
from .conflicts import resolve_page_model_conflicts
from .models import PageBlock, PageModel, PageSize, PdfKind


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


def _page_coordinate_scale(model: PageModel) -> tuple[float, float]:
    width = model.source_image_width_px or model.size.width_pt
    height = model.source_image_height_px or model.size.height_pt
    return model.size.width_pt / width, model.size.height_pt / height


def _image_shape_style(block: PageBlock, model: PageModel) -> str:
    """Return page-anchored VML geometry for a source-image fallback."""

    scale_x, scale_y = _page_coordinate_scale(model)
    left, top, right, bottom = block.bbox
    width = max(1.0, (right - left) * scale_x)
    height = max(1.0, (bottom - top) * scale_y)
    z_index = 0 if block.style.get("render_behind_text") else max(1, block.z_index + 1)
    return (
        "position:absolute;"
        "mso-position-horizontal-relative:page;"
        "mso-position-vertical-relative:page;"
        f"margin-left:{left * scale_x:.2f}pt;"
        f"margin-top:{top * scale_y:.2f}pt;"
        f"width:{width:.2f}pt;"
        f"height:{height:.2f}pt;"
        f"z-index:{z_index};"
    )


def _toc_native_run_xml(value: str, *, font_pt: float, color: str, ascii_font: str = "STSong") -> str:
    return (
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:rPr>'
        f'<w:rFonts w:ascii="{escape(ascii_font)}" w:hAnsi="{escape(ascii_font)}" w:eastAsia="STSong"/>'
        f'<w:color w:val="{escape(color)}"/><w:sz w:val="{round(font_pt * 2)}"/>'
        '</w:rPr>'
        f'<w:t xml:space="preserve">{escape(value)}</w:t></w:r>'
    )


def _append_native_toc_page(document: Document, model: PageModel) -> None:
    """Render TOC text as normal Word paragraphs, not floating text boxes."""

    scale_x, scale_y = _page_coordinate_scale(model)
    decorations = [block for block in model.blocks if block.asset_path and block.block_type == "image"]
    text_blocks = sorted(
        (block for block in model.blocks if block.block_type in {"toc_group", "toc_entry"}),
        key=lambda item: (item.bbox[1], item.reading_order),
    )
    if not text_blocks:
        page_canvas = document.add_paragraph()
        _format_page_paragraph(page_canvas)
        for decoration in decorations:
            _append_fallback_image(page_canvas, model, decoration)
        return

    first_top = max(1.0, text_blocks[0].bbox[1] * scale_y)
    canvas_height = 1.0
    decoration_canvas = document.add_paragraph()
    _format_page_paragraph(decoration_canvas)
    decoration_canvas.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    decoration_canvas.paragraph_format.line_spacing = Pt(canvas_height)
    decoration_canvas.paragraph_format.space_before = Pt(0)
    decoration_canvas.paragraph_format.space_after = Pt(0)
    for decoration in decorations:
        _append_fallback_image(decoration_canvas, model, decoration)
        bookmark = str(decoration.style.get("bookmark_name", "")).strip()
        if bookmark:
            _append_bookmark(decoration_canvas, bookmark, model.page_index * 10 + 1)

    # Use paragraph spacing for the large top offset.  LibreOffice caps an
    # oversized exact line-height spacer, which previously moved the first TOC
    # group underneath the decoration strip and made it appear missing.
    cursor = canvas_height
    for block in text_blocks:
        top = block.bbox[1] * scale_y
        height = max(float(block.style.get("textbox_min_height_pt", 14.0)), (block.bbox[3] - block.bbox[1]) * scale_y)
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(max(0.0, top - cursor))
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        paragraph.paragraph_format.line_spacing = Pt(height)
        paragraph.paragraph_format.keep_together = True
        left = block.bbox[0] * scale_x
        right = block.bbox[2] * scale_x
        paragraph.paragraph_format.left_indent = Pt(left)
        paragraph.paragraph_format.right_indent = Pt(max(0.0, model.size.width_pt - right))
        font_pt = float(block.style.get("font_size_pt", 10.5))
        color = str(block.style.get("font_color", "F4008A"))
        if block.block_type == "toc_group":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            wrapper = parse_xml(
                '<w:root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                + _toc_native_run_xml(block.text or "", font_pt=font_pt, color=color)
                + '</w:root>'
            )
            for child in list(wrapper):
                paragraph._p.append(child)
        else:
            paragraph.style = document.styles["Source TOC 1"]
            paragraph.paragraph_format.tab_stops.add_tab_stop(
                Pt(max(left + 20.0, right - 3.0)),
                WD_TAB_ALIGNMENT.RIGHT,
                WD_TAB_LEADER.DOTS,
            )
            chapter = str(block.style.get("toc_chapter", ""))
            title = str(block.style.get("toc_title", ""))
            page_number = str(block.style.get("toc_page", ""))
            content = (
                _toc_native_run_xml(f"{chapter}　{title}", font_pt=font_pt, color=color)
                + _toc_native_run_xml("<TAB>", font_pt=font_pt, color=color).replace(
                    '<w:t xml:space="preserve">&lt;TAB&gt;</w:t>', '<w:tab/>'
                )
                + _toc_native_run_xml(page_number, font_pt=font_pt, color=color, ascii_font="Arial")
            )
            bookmark = str(block.style.get("target_bookmark", "")).strip()
            if bookmark:
                element = parse_xml(
                    f'<w:hyperlink xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                    f'w:anchor="{escape(bookmark)}" w:history="1">{content}</w:hyperlink>'
                )
                paragraph._p.append(element)
            else:
                wrapper = parse_xml(
                    '<w:root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    + content
                    + '</w:root>'
                )
                for child in list(wrapper):
                    paragraph._p.append(child)
        cursor = top + height


def _append_bookmark(paragraph: object, name: str, bookmark_id: int) -> None:
    """Add a zero-layout internal-link target to the current source page."""

    safe_name = re.sub(r"[^A-Za-z0-9_]", "_", name)[:40]
    # Adjacent start/end elements are a valid zero-layout target.  A previous
    # hidden zero-width run caused LibreOffice to drop VML image shapes sharing
    # the paragraph, yielding blank cover pages during render verification.
    xml = f'''<w:bookmarkStart xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:id="{bookmark_id}" w:name="{escape(safe_name)}"/>
    <w:bookmarkEnd xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:id="{bookmark_id}"/>'''
    wrapper = parse_xml(f'<w:root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">{xml}</w:root>')
    for child in list(wrapper):
        paragraph._p.append(child)  # type: ignore[attr-defined]


def _ensure_source_styles(document: Document) -> None:
    """Install explicit styles used by the source-faithful Word structure."""

    if "Source TOC 1" not in document.styles:
        toc = document.styles.add_style("Source TOC 1", WD_STYLE_TYPE.PARAGRAPH)
        toc._element.set(qn("w:styleId"), "SourceTOC1")
        toc.font.name = "STSong"
        toc._element.rPr.rFonts.set(qn("w:eastAsia"), "STSong")
        toc.font.size = Pt(10.5)
        toc.paragraph_format.space_before = Pt(0)
        toc.paragraph_format.space_after = Pt(0)
    if "Source Chapter Anchor" not in document.styles:
        anchor = document.styles.add_style("Source Chapter Anchor", WD_STYLE_TYPE.PARAGRAPH)
        anchor._element.set(qn("w:styleId"), "SourceChapterAnchor")
        anchor.base_style = document.styles["Heading 1"]
        anchor.font.hidden = True
        anchor.font.size = Pt(1)
        anchor.paragraph_format.space_before = Pt(0)
        anchor.paragraph_format.space_after = Pt(0)
    for name, style_id, size, color in (
        ("Source Body", "SourceBody", 9.6, "222222"),
        ("Source Callout", "SourceCallout", 9.6, "222222"),
        ("Source Option Row", "SourceOptionRow", 9.6, "222222"),
        ("Source Heading", "SourceHeading", 16.0, "EF168B"),
    ):
        if name in document.styles:
            continue
        style = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style._element.set(qn("w:styleId"), style_id)
        style.font.name = "Times New Roman"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)


_NATIVE_EDITABLE_TYPES = {
    "editable_paragraph",
    "editable_heading",
    "editable_option_row",
    "editable_callout_body",
    "editable_page_number",
}


def _set_native_run_style(
    run: object,
    *,
    font_pt: float,
    color: str,
    bold: bool,
    east_asia_font: str,
    ascii_font: str,
    character_spacing_twips: int,
) -> None:
    run.font.name = ascii_font  # type: ignore[attr-defined]
    run.font.size = Pt(font_pt)  # type: ignore[attr-defined]
    run.font.bold = bold  # type: ignore[attr-defined]
    run.font.color.rgb = RGBColor.from_string(color)  # type: ignore[attr-defined]
    properties = run._element.get_or_add_rPr()  # type: ignore[attr-defined]
    fonts = properties.get_or_add_rFonts()
    fonts.set(qn("w:ascii"), ascii_font)
    fonts.set(qn("w:hAnsi"), ascii_font)
    fonts.set(qn("w:eastAsia"), east_asia_font)
    if character_spacing_twips:
        spacing = properties.find(qn("w:spacing"))
        if spacing is None:
            spacing = parse_xml('<w:spacing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
            properties.append(spacing)
        spacing.set(qn("w:val"), str(character_spacing_twips))


def _append_native_text_runs(paragraph: object, block: PageBlock) -> None:
    text = (block.text or "").replace("\r", "")
    if not text:
        return
    try:
        font_pt = float(block.style.get("font_size_pt", 9.6))
    except (TypeError, ValueError):
        font_pt = 9.6
    try:
        accent_length = max(0, min(len(text), int(block.style.get("accent_length", 0))))
    except (TypeError, ValueError):
        accent_length = 0
    try:
        bold_prefix_length = max(0, min(len(text), int(block.style.get("bold_prefix_length", 0))))
    except (TypeError, ValueError):
        bold_prefix_length = 0
    try:
        spacing = int(block.style.get("character_spacing_twips", 0))
    except (TypeError, ValueError):
        spacing = 0
    default_color = str(block.style.get("font_color", "222222"))
    if block.block_type == "editable_heading":
        default_color = str(block.style.get("font_color", "EF168B"))
    east_asia_font = str(block.style.get("font_name_east_asia", "SimSun"))
    ascii_font = str(block.style.get("font_name_ascii", "Times New Roman"))
    boundaries = sorted({0, len(text), accent_length, bold_prefix_length})
    for start, end in zip(boundaries, boundaries[1:]):
        if start >= end:
            continue
        color = "EF168B" if start < accent_length else default_color
        bold = start < bold_prefix_length
        segment = text[start:end]
        parts = re.split(r"([\n\t])", segment)
        for part in parts:
            if not part:
                continue
            if part == "\n":
                paragraph.add_run().add_break()
                continue
            if part == "\t":
                paragraph.add_run().add_tab()
                continue
            run = paragraph.add_run(part)
            _set_native_run_style(
                run,
                font_pt=font_pt,
                color=color,
                bold=bold,
                east_asia_font=east_asia_font,
                ascii_font=ascii_font,
                character_spacing_twips=spacing,
            )


def _estimated_native_line_width_pt(value: str, font_pt: float, spacing_twips: int) -> float:
    units = 0.0
    visible = 0
    for character in value:
        if character == "\t":
            continue
        visible += 1
        if character.isspace():
            units += 0.35
        elif unicodedata.east_asian_width(character) in {"W", "F"}:
            units += 1.0
        elif character in "=+×÷%≈-—−":
            units += 0.62
        elif character.isupper() or character.isdigit():
            units += 0.56
        else:
            units += 0.50
    return units * font_pt + max(0, visible - 1) * spacing_twips / 20.0


def _append_native_source_page(document: Document, model: PageModel, *, bookmark_base: int) -> None:
    """Place crops and editable paragraphs in source-coordinate page frames.

    ``w:framePr`` keeps the paragraph itself in the main Word document (so it
    remains searchable/editable and is not a VML textbox) while taking it out
    of normal vertical flow.  This is essential for formula-heavy source pages:
    inline numerator/denominator fragments must not push every later paragraph
    onto a new page.
    """

    scale_x, scale_y = _page_coordinate_scale(model)
    canvas = document.add_paragraph()
    _format_page_paragraph(canvas)
    canvas.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    canvas.paragraph_format.line_spacing = Pt(1)
    images = [block for block in model.blocks if block.asset_path]
    for image_block in sorted(images, key=lambda item: (item.z_index, item.reading_order)):
        _append_fallback_image(canvas, model, image_block)
        bookmark = str(image_block.style.get("bookmark_name", "")).strip()
        if bookmark:
            _append_bookmark(canvas, bookmark, bookmark_base)

    bookmarks = [
        str(block.style.get("bookmark_name", "")).strip()
        for block in model.blocks
        if block.style.get("bookmark_name")
    ]
    if not any(str(block.style.get("bookmark_name", "")).strip() for block in images):
        for offset, bookmark in enumerate(dict.fromkeys(item for item in bookmarks if item)):
            _append_bookmark(canvas, bookmark, bookmark_base + offset)

    editable = sorted(
        (
            block
            for block in model.blocks
            if block.block_type in _NATIVE_EDITABLE_TYPES and block.text and not block.asset_path
        ),
        key=lambda item: (item.bbox[1], item.reading_order, item.bbox[0]),
    )
    for block in editable:
        left = max(0.0, block.bbox[0] * scale_x)
        top = max(0.0, block.bbox[1] * scale_y)
        right = min(model.size.width_pt, block.bbox[2] * scale_x)
        paragraph = document.add_paragraph()
        style_name = {
            "editable_heading": "Source Heading",
            "editable_callout_body": "Source Callout",
            "editable_option_row": "Source Option Row",
        }.get(block.block_type, "Source Body")
        paragraph.style = document.styles[style_name]
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.left_indent = Pt(0)
        paragraph.paragraph_format.right_indent = Pt(0)
        try:
            first_line_indent = float(block.style.get("first_line_indent_px", 0.0)) * scale_x
        except (TypeError, ValueError):
            first_line_indent = 0.0
        paragraph.paragraph_format.first_line_indent = Pt(max(0.0, first_line_indent))
        paragraph.paragraph_format.keep_together = True
        try:
            line_spacing = float(block.style.get("line_spacing_pt", 12.0))
        except (TypeError, ValueError):
            line_spacing = 12.0
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        paragraph.paragraph_format.line_spacing = Pt(max(10.5, line_spacing))
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if block.block_type == "editable_option_row":
            for stop in block.style.get("tab_stops_px", []):
                try:
                    paragraph.paragraph_format.tab_stops.add_tab_stop(
                        Pt(float(stop) * scale_x), WD_TAB_ALIGNMENT.LEFT
                    )
                except (TypeError, ValueError):
                    continue
        _append_native_text_runs(paragraph, block)
        try:
            line_count = max(1, int(block.style.get("line_count", (block.text or "").count("\n") + 1)))
        except (TypeError, ValueError):
            line_count = max(1, (block.text or "").count("\n") + 1)
        source_height = max(1.0, (block.bbox[3] - block.bbox[1]) * scale_y)
        frame_height = max(source_height + 2.0, line_count * max(10.5, line_spacing) + 2.0)
        frame_width = max(8.0, right - left)
        if block.block_type != "editable_option_row":
            try:
                font_pt = float(block.style.get("font_size_pt", 9.6))
            except (TypeError, ValueError):
                font_pt = 9.6
            try:
                spacing_twips = int(block.style.get("character_spacing_twips", 0))
            except (TypeError, ValueError):
                spacing_twips = 0
            required_width = max(
                (_estimated_native_line_width_pt(line, font_pt, spacing_twips) for line in (block.text or "").splitlines()),
                default=0.0,
            )
            frame_width = min(max(8.0, model.size.width_pt - left), max(frame_width, required_width + 1.5))
        ppr = paragraph._p.get_or_add_pPr()
        frame = parse_xml(
            '<w:framePr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            f'w:w="{round(frame_width * 20)}" w:h="{round(frame_height * 20)}" '
            f'w:x="{round(left * 20)}" w:y="{round(top * 20)}" '
            'w:hAnchor="page" w:vAnchor="page" w:wrap="none" w:hRule="exact"/>'
        )
        ppr.insert(0, frame)


def _append_fallback_image(paragraph: object, model: PageModel, block: PageBlock) -> None:
    if not block.asset_path or not Path(block.asset_path).is_file():
        return
    style = _image_shape_style(block, model)
    relationship_id, _ = paragraph.part.get_or_add_image(str(block.asset_path))  # type: ignore[attr-defined]
    xml = f'''<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"
        xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <v:shape id="pdf2word_image_{escape(block.block_id)}" type="#_x0000_t75" style="{style}" stroked="f">
        <v:imagedata r:id="{relationship_id}" o:title=""/>
      </v:shape>
    </w:pict>'''
    paragraph.add_run()._r.append(parse_xml(xml))


def create_positioned_editable_docx(models: list[PageModel], output_path: str | Path) -> Path:
    """Build a source-first editable DOCX with local image fallbacks.

    Ordinary text is accepted only through native editable block types. Legacy
    line/text blocks are never serialized as VML text boxes.
    """

    if not models:
        raise ValueError("没有可写入 DOCX 的 PageModel。")
    for model in models:
        resolve_page_model_conflicts(model)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    _ensure_source_styles(document)
    for position, model in enumerate(sorted(models, key=lambda item: item.page_index)):
        section = document.sections[0] if position == 0 else document.add_section(WD_SECTION.NEW_PAGE)
        _set_page_geometry(section, model.size)
        if model.page_class == "table_of_contents":
            _append_native_toc_page(document, model)
            continue
        if any(block.block_type in _NATIVE_EDITABLE_TYPES for block in model.blocks):
            _append_native_source_page(document, model, bookmark_base=position * 20 + 1)
            continue
        # Image-only pages (cover, divider, final fallback) still use one
        # absolutely positioned host paragraph. Textual legacy blocks are
        # rejected instead of silently recreating the retired VML layout.
        unresolved_text = [
            block.block_id
            for block in model.blocks
            if block.text and not block.asset_path
        ]
        if unresolved_text:
            raise ValueError(
                "PageModel 仍包含未段落化文字块，拒绝写入旧式 VML 文本框："
                + ", ".join(unresolved_text)
            )
        page_canvas = document.add_paragraph()
        _format_page_paragraph(page_canvas)
        bookmark_names = [
            str(block.style.get("bookmark_name"))
            for block in model.blocks
            if block.style.get("bookmark_name")
        ]
        for bookmark_offset, bookmark_name in enumerate(dict.fromkeys(bookmark_names)):
            _append_bookmark(page_canvas, bookmark_name, position * 10 + bookmark_offset + 1)
        for block in sorted(model.blocks, key=lambda item: (item.z_index, item.reading_order)):
            if block.asset_path:
                _append_fallback_image(page_canvas, model, block)
    document.save(output)
    return output

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
