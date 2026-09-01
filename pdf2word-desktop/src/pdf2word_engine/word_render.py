"""Microsoft Word COM rendering for the final Windows acceptance gate."""

from __future__ import annotations

from pathlib import Path

from .document_checks import DocumentCheckError, assert_rendered_page_count, assert_source_first_docx_contract


WORD_EXPORT_FORMAT_PDF = 17


def render_docx_with_microsoft_word(docx_path: str | Path, output_pdf: str | Path) -> Path:
    """Export a DOCX with installed desktop Word, without changing the source file."""

    source = Path(docx_path).resolve()
    destination = Path(output_pdf).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DocumentCheckError("Microsoft Word 实机渲染需要安装桌面版 Word 与可选依赖 pywin32。") from exc
    application = None
    document = None
    try:
        application = win32com.client.DispatchEx("Word.Application")
        application.Visible = False
        application.DisplayAlerts = 0
        document = application.Documents.Open(
            str(source),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
            OpenAndRepair=False,
        )
        document.ExportAsFixedFormat(
            OutputFileName=str(destination),
            ExportFormat=WORD_EXPORT_FORMAT_PDF,
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=0,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
    except Exception as exc:
        raise DocumentCheckError(f"Microsoft Word 导出 PDF 失败：{exc}") from exc
    finally:
        if document is not None:
            document.Close(False)
        if application is not None:
            application.Quit()
    if not destination.is_file() or destination.stat().st_size == 0:
        raise DocumentCheckError("Microsoft Word 未生成有效 PDF。")
    return destination


def verify_with_microsoft_word(
    docx_path: str | Path,
    output_pdf: str | Path,
    *,
    expected_page_count: int,
    minimum_editable_characters: int = 1,
) -> int:
    """Check current DOCX structure, then require Word's page-count result."""

    assert_source_first_docx_contract(
        docx_path,
        minimum_editable_characters=minimum_editable_characters,
    )
    rendered = render_docx_with_microsoft_word(docx_path, output_pdf)
    return assert_rendered_page_count(rendered, expected_page_count)
