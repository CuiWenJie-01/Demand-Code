"""Read-only PDF inspection and routing decisions."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .models import PageSize, PdfKind, PreflightReport


def _sample_indices(page_count: int, requested: int) -> list[int]:
    if page_count <= 0:
        return []
    requested = max(1, min(requested, page_count))
    if requested == page_count:
        return list(range(page_count))
    positions = {round(index * (page_count - 1) / (requested - 1)) for index in range(requested)}
    return sorted(positions)


def _metadata(reader: PdfReader) -> dict[str, str]:
    raw = reader.metadata or {}
    return {
        str(key).lstrip("/"): str(value)
        for key, value in raw.items()
        if value is not None
    }


def _page_size(page: object) -> PageSize:
    media_box = page.mediabox  # type: ignore[attr-defined]
    return PageSize(
        width_pt=float(media_box.width),
        height_pt=float(media_box.height),
    )


def _resource_count(page: object, resource_name: str) -> bool:
    resources = page.get("/Resources") or {}  # type: ignore[attr-defined]
    return bool(resources.get(resource_name))


def _extract_text(page: object) -> str:
    try:
        return page.extract_text(extraction_mode="layout") or ""  # type: ignore[attr-defined]
    except TypeError:
        return page.extract_text() or ""  # type: ignore[attr-defined]
    except Exception:
        return ""


def _classify(
    *, encrypted: bool, font_resource_pages: int, xobject_pages: int, page_count: int, text_characters: int
) -> PdfKind:
    if encrypted:
        return PdfKind.ENCRYPTED
    if page_count == 0:
        return PdfKind.DAMAGED
    if font_resource_pages == 0 and xobject_pages > 0:
        return PdfKind.OUTLINED
    if text_characters >= 80:
        return PdfKind.BORN_DIGITAL
    if xobject_pages >= max(1, page_count // 2):
        return PdfKind.SCANNED
    return PdfKind.MIXED


def inspect_pdf(source: str | Path, *, sample_pages: int = 7) -> PreflightReport:
    """Inspect a PDF without altering it and choose an extraction route.

    The check deliberately looks at resources across all pages because a small
    sample can misroute an outlined publication PDF to a text-layer pipeline.
    Text extraction itself remains limited to a deterministic page sample.
    """

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在：{source_path}")

    reader = PdfReader(str(source_path), strict=False)
    encrypted = bool(reader.is_encrypted)
    if encrypted:
        return PreflightReport(
            source_path=str(source_path),
            file_size_bytes=source_path.stat().st_size,
            page_count=0,
            pdf_version=None,
            encrypted=True,
            tagged=None,
            optimized=None,
            metadata=_metadata(reader),
            kind=PdfKind.ENCRYPTED,
            warnings=["PDF 已加密；当前版本不尝试解密或读取页面。"],
        )

    pages = reader.pages
    page_count = len(pages)
    sampled = _sample_indices(page_count, sample_pages)
    font_resource_pages = 0
    xobject_pages = 0
    sizes: list[PageSize] = []
    for page in pages:
        sizes.append(_page_size(page))
        font_resource_pages += int(_resource_count(page, "/Font"))
        xobject_pages += int(_resource_count(page, "/XObject"))

    text_characters = sum(len(_extract_text(pages[index]).strip()) for index in sampled)
    kind = _classify(
        encrypted=False,
        font_resource_pages=font_resource_pages,
        xobject_pages=xobject_pages,
        page_count=page_count,
        text_characters=text_characters,
    )
    warnings: list[str] = []
    if kind is PdfKind.OUTLINED:
        warnings.append("未发现页面字体资源，已归类为文字转轮廓/矢量型 PDF，需走 OCR 路径。")
    if kind is PdfKind.SCANNED:
        warnings.append("抽样无法获得可靠文字，已归类为扫描型 PDF，需走 OCR 路径。")
    if kind is PdfKind.MIXED:
        warnings.append("文档可能混合了文字层、图片或矢量页面；转换时应按页选择策略。")

    root = reader.trailer.get("/Root") or {}
    return PreflightReport(
        source_path=str(source_path),
        file_size_bytes=source_path.stat().st_size,
        page_count=page_count,
        pdf_version=str(reader.pdf_header or "").removeprefix("%PDF-") or None,
        encrypted=False,
        tagged=bool(root.get("/MarkInfo", {}).get("/Marked")) if root.get("/MarkInfo") else False,
        optimized=bool(reader.trailer.get("/Linearized")),
        metadata=_metadata(reader),
        kind=kind,
        font_resource_pages=font_resource_pages,
        xobject_pages=xobject_pages,
        sample_pages=[index + 1 for index in sampled],
        sample_text_characters=text_characters,
        page_sizes=sizes,
        warnings=warnings,
    )
