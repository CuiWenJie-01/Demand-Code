"""Reusable DOCX structure and renderer gates for source-first output."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
VML_NAMESPACE = "urn:schemas-microsoft-com:vml"
NAMESPACES = {"w": WORD_NAMESPACE, "v": VML_NAMESPACE}


class DocumentCheckError(ValueError):
    """Raised when a generated DOCX or its rendered PDF violates a gate."""


@dataclass(frozen=True, slots=True)
class DocumentStructureReport:
    docx: Path
    editable_text_characters: int
    native_frame_paragraphs: int
    legacy_vml_text_boxes: int
    fallback_images: int

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["docx"] = str(self.docx)
        return payload


def _read_document_xml(docx_path: str | Path) -> ElementTree.Element:
    path = Path(docx_path).expanduser().resolve()
    try:
        with zipfile.ZipFile(path) as archive:
            return ElementTree.fromstring(archive.read("word/document.xml"))
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise DocumentCheckError(f"无法读取 DOCX 结构：{path}") from exc


def inspect_docx_structure(docx_path: str | Path) -> DocumentStructureReport:
    """Inspect editability and fallback objects without relying on an old PageModel."""

    path = Path(docx_path).expanduser().resolve()
    root = _read_document_xml(path)
    editable_text = "".join(node.text or "" for node in root.findall(".//w:t", NAMESPACES))
    native_frames = sum(
        1
        for paragraph in root.findall(".//w:p", NAMESPACES)
        if paragraph.find("./w:pPr/w:framePr", NAMESPACES) is not None
    )
    legacy_text_boxes = len(root.findall(".//w:txbxContent", NAMESPACES))
    fallback_images = sum(
        1
        for shape in root.findall(".//v:shape", NAMESPACES)
        if shape.attrib.get("id", "").startswith("pdf2word_image_")
    )
    return DocumentStructureReport(
        docx=path,
        editable_text_characters=len("".join(editable_text.split())),
        native_frame_paragraphs=native_frames,
        legacy_vml_text_boxes=legacy_text_boxes,
        fallback_images=fallback_images,
    )


def assert_source_first_docx_contract(
    docx_path: str | Path,
    *,
    minimum_editable_characters: int = 1,
    allow_legacy_text_boxes: bool = False,
) -> DocumentStructureReport:
    """Require genuine editable text and reject the retired line-text-box layout."""

    report = inspect_docx_structure(docx_path)
    if report.editable_text_characters < minimum_editable_characters:
        raise DocumentCheckError(
            f"可编辑文字不足：要求至少 {minimum_editable_characters} 字，实际 {report.editable_text_characters} 字。"
        )
    if not allow_legacy_text_boxes and report.legacy_vml_text_boxes:
        raise DocumentCheckError(
            f"检测到 {report.legacy_vml_text_boxes} 个旧式 VML 文字框；普通正文必须使用原生 Word 段落。"
        )
    return report


def render_docx_to_pdf(
    docx_path: str | Path,
    output_directory: str | Path,
    *,
    renderer: str | None = None,
) -> Path:
    """Render a DOCX with an Office-compatible headless renderer."""

    docx = Path(docx_path).expanduser().resolve()
    destination = Path(output_directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    executable = renderer or shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        raise DocumentCheckError("未找到 soffice/libreoffice；无法执行 DOCX→PDF 渲染门禁。")
    result = subprocess.run(
        [executable, "--headless", "--convert-to", "pdf", "--outdir", str(destination), str(docx)],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    output = destination / f"{docx.stem}.pdf"
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        details = (result.stderr or result.stdout).strip()
        raise DocumentCheckError(f"DOCX→PDF 渲染失败：{details or result.returncode}")
    return output


def assert_rendered_page_count(pdf_path: str | Path, expected_page_count: int) -> int:
    """Require the renderer output to preserve the expected physical page count."""

    try:
        page_count = len(PdfReader(str(pdf_path), strict=False).pages)
    except Exception as exc:
        raise DocumentCheckError(f"无法读取渲染 PDF：{pdf_path}") from exc
    if page_count != expected_page_count:
        raise DocumentCheckError(f"分页门禁失败：预期 {expected_page_count} 页，实际 {page_count} 页。")
    return page_count
