"""DOCX visual-regression gates for positioned editable output.

The gate combines OOXML editability/coordinate checks with a DOCX-to-PDF page
count check.  It is intentionally renderer-agnostic: CI can pass an explicit
LibreOffice or Microsoft Word-compatible command, while structural failures are
still caught before a renderer is available.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader
import pypdfium2

from .models import PageBlock, PageModel


VML_NAMESPACE = "urn:schemas-microsoft-com:vml"
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NAMESPACES = {"v": VML_NAMESPACE, "w": WORD_NAMESPACE}
_STYLE_VALUE = re.compile(r"(?P<key>[a-z-]+):(?P<value>[^;]+)")


class VisualRegressionError(ValueError):
    """Raised when a golden-page requirement is not met."""


@dataclass(frozen=True, slots=True)
class PositionedShape:
    shape_id: str
    style: dict[str, str]
    text: str
    has_distributed_alignment: bool
    fill_color: str | None = None


@dataclass(frozen=True, slots=True)
class GoldenPageReport:
    docx: Path
    editable_text_boxes: int
    rendered_page_count: int | None


def _read_docx_xml(docx_path: str | Path) -> ElementTree.Element:
    path = Path(docx_path)
    try:
        with zipfile.ZipFile(path) as archive:
            return ElementTree.fromstring(archive.read("word/document.xml"))
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise VisualRegressionError(f"无法读取 DOCX 结构：{path}") from exc


def _shape_style(style: str) -> dict[str, str]:
    return {match.group("key"): match.group("value").strip() for match in _STYLE_VALUE.finditer(style)}


def inspect_positioned_shapes(docx_path: str | Path) -> list[PositionedShape]:
    """Return editable VML text boxes and vector rule shapes in document order."""

    root = _read_docx_xml(docx_path)
    shapes: list[PositionedShape] = []
    for shape in root.findall(".//v:shape", NAMESPACES):
        text_container = shape.find(".//w:txbxContent", NAMESPACES)
        text = "".join(text_container.itertext()) if text_container is not None else ""
        shapes.append(
            PositionedShape(
                shape_id=shape.attrib.get("id", ""),
                style=_shape_style(shape.attrib.get("style", "")),
                text=text,
                has_distributed_alignment=text_container is not None
                and text_container.find(".//w:jc[@w:val='distribute']", NAMESPACES) is not None,
                fill_color=shape.attrib.get("fillcolor"),
            )
        )
    for rectangle in root.findall(".//v:rect", NAMESPACES):
        shapes.append(
            PositionedShape(
                shape_id=rectangle.attrib.get("id", ""),
                style=_shape_style(rectangle.attrib.get("style", "")),
                text="",
                has_distributed_alignment=False,
                fill_color=rectangle.attrib.get("fillcolor"),
            )
        )
    return shapes


def _points(value: str | None) -> float:
    if value is None or not value.endswith("pt"):
        raise VisualRegressionError(f"定位形状缺少 pt 坐标：{value!r}")
    return float(value.removesuffix("pt"))


def _expected_shape_id(block: PageBlock) -> str:
    if block.block_type == "sidebar_accent_rule":
        return f"pdf2word_sidebar_rule_{block.block_id}"
    return f"pdf2word_text_{block.block_id}"


def assert_positioned_model_contract(docx_path: str | Path, model: PageModel, *, tolerance_pt: float = 0.05) -> int:
    """Verify key page-model semantics survived into editable, positioned OOXML.

    This checks the exact left/right geometry for headings and prose, the
    answer's independent text box/baseline, editable sidebar glyphs/page number
    and the editable accent rule. It does not compare OCR text against the
    source PDF; that belongs to the representative-page CER suite.
    """

    shapes = {shape.shape_id: shape for shape in inspect_positioned_shapes(docx_path)}
    scale_x = model.size.width_pt / (model.source_image_width_px or model.size.width_pt)
    scale_y = model.size.height_pt / (model.source_image_height_px or model.size.height_pt)
    checked = 0
    answer_blocks: list[PageBlock] = []
    tag_blocks: list[PageBlock] = []
    for block in model.blocks:
        role = str(block.style.get("semantic_role", ""))
        check_geometry = role in {
            "question_heading",
            "question_body",
            "callout_body",
            "callout_answer",
            "callout_label",
            "callout_index",
            "answer_blank",
            "sidebar_page_number",
        }
        if role == "callout_answer":
            answer_blocks.append(block)
        if block.block_type in {"talk_badge_image", "talk_callout_tag_image"}:
            tag_blocks.append(block)
        if block.block_type == "sidebar_vertical_text":
            glyph_ids = [f"pdf2word_text_{block.block_id}-glyph-{index + 1}" for index, _ in enumerate("".join((block.text or "").split()))]
            if not glyph_ids or any(identifier not in shapes for identifier in glyph_ids):
                raise VisualRegressionError("右侧栏文字没有以独立可编辑字形写入 DOCX。")
            checked += len(glyph_ids)
            continue
        if role == "sidebar_accent_rule":
            shape = shapes.get(_expected_shape_id(block))
            if shape is None:
                raise VisualRegressionError("页码色条没有以可编辑矢量对象写入 DOCX。")
            expected_fill = f"#{str(block.style.get('fill_color', 'EF168B')).upper()}"
            if shape.fill_color != expected_fill:
                raise VisualRegressionError("页码色条颜色没有按版式档案写入 DOCX。")
            checked += 1
            continue
        if not check_geometry:
            continue
        shape = shapes.get(_expected_shape_id(block))
        if shape is None:
            raise VisualRegressionError(f"缺少可编辑定位文本框：{block.block_id}")
        expected_left = block.bbox[0] * scale_x
        expected_right = block.bbox[2] * scale_x
        expected_top = block.bbox[1] * scale_y
        actual_left = _points(shape.style.get("margin-left"))
        actual_right = actual_left + _points(shape.style.get("width"))
        actual_top = _points(shape.style.get("margin-top"))
        if abs(actual_left - expected_left) > tolerance_pt or abs(actual_right - expected_right) > tolerance_pt:
            raise VisualRegressionError(f"定位文本框横向边界漂移：{block.block_id}")
        if abs(actual_top - expected_top) > tolerance_pt:
            raise VisualRegressionError(f"定位文本框基线漂移：{block.block_id}")
        if role in {"question_heading", "question_body", "callout_body"} and not shape.has_distributed_alignment:
            raise VisualRegressionError(f"右边界对齐规则未写入 DOCX：{block.block_id}")
        if role == "callout_answer" and shape.text != (block.text or ""):
            raise VisualRegressionError("答案必须保持为独立、可编辑的文本框。")
        if role in {"callout_label", "callout_index", "answer_blank"} and shape.text != (block.text or ""):
            raise VisualRegressionError(f"标签、星级或答案括号未保持为可编辑文本：{block.block_id}")
        checked += 1

    for answer in answer_blocks:
        preceding_tags = [tag for tag in tag_blocks if tag.bbox[1] <= answer.bbox[1] <= tag.bbox[3] + 25]
        if preceding_tags and answer.bbox[1] <= preceding_tags[-1].bbox[1]:
            raise VisualRegressionError("答案基线未位于答案标签之后。")
    return checked


def render_docx_to_pdf(docx_path: str | Path, output_directory: str | Path, *, renderer: str | None = None) -> Path:
    """Render with a headless Office-compatible renderer and return its PDF."""

    docx = Path(docx_path).resolve()
    destination = Path(output_directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    executable = renderer or shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        raise VisualRegressionError("未找到 soffice/libreoffice；无法执行 DOCX→PDF 视觉回归。")
    result = subprocess.run(
        [executable, "--headless", "--convert-to", "pdf", "--outdir", str(destination), str(docx)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    output = destination / f"{docx.stem}.pdf"
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        details = (result.stderr or result.stdout).strip()
        raise VisualRegressionError(f"DOCX→PDF 渲染失败：{details or result.returncode}")
    return output


def assert_rendered_page_count(pdf_path: str | Path, expected_page_count: int) -> int:
    try:
        page_count = len(PdfReader(str(pdf_path), strict=False).pages)
    except Exception as exc:  # pypdf exposes several parser exception types.
        raise VisualRegressionError(f"无法读取回归渲染 PDF：{pdf_path}") from exc
    if page_count != expected_page_count:
        raise VisualRegressionError(f"分页回归失败：预期 {expected_page_count} 页，实际 {page_count} 页。")
    return page_count


def render_docx_to_png(docx_path: str | Path, output_directory: str | Path, *, renderer: str | None = None) -> Path:
    """Render the first single-page DOCX page into a deterministic 144-DPI PNG."""

    rendered_pdf = render_docx_to_pdf(docx_path, output_directory, renderer=renderer)
    if assert_rendered_page_count(rendered_pdf, 1) != 1:  # Defensive: preserves a useful error if this helper changes.
        raise VisualRegressionError("视觉快照只接受单页 DOCX。")
    try:
        document = pypdfium2.PdfDocument(str(rendered_pdf))
        page = document[0]
        output = Path(output_directory) / "page-1.png"
        try:
            page.render(scale=2).to_pil().save(output)
        finally:
            page.close()
            document.close()
        return output
    except Exception as exc:
        raise VisualRegressionError(f"无法生成视觉回归 PNG：{rendered_pdf}") from exc


def verify_golden_page(
    docx_path: str | Path,
    model: PageModel,
    *,
    expected_page_count: int = 1,
    renderer: str | None = None,
) -> GoldenPageReport:
    """Run the complete M1 golden-page gate for a generated positioned DOCX."""

    editable_text_boxes = assert_positioned_model_contract(docx_path, model)
    with tempfile.TemporaryDirectory(prefix="pdf2word-regression-") as temporary:
        rendered = render_docx_to_pdf(docx_path, temporary, renderer=renderer)
        page_count = assert_rendered_page_count(rendered, expected_page_count)
    return GoldenPageReport(Path(docx_path), editable_text_boxes, page_count)
