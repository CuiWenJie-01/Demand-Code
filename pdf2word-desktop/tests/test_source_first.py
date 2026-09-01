from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from pdf2word_engine.models import PageSize
from pdf2word_engine.source_first import (
    classify_source_page,
    remove_shanganren_watermark,
    toc_page_model,
)
from pdf2word_engine.word import create_positioned_editable_docx


def test_watermark_removal_preserves_dark_foreground() -> None:
    image = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(image)
    # Broad repeated neutral-gray strokes approximate the central watermark.
    draw.rectangle((250, 420, 650, 475), fill=(228, 228, 228))
    draw.rectangle((420, 330, 480, 820), fill=(228, 228, 228))
    draw.rectangle((270, 720, 680, 775), fill=(228, 228, 228))
    # Foreground text is represented by a dark stroke crossing the watermark.
    draw.rectangle((180, 590, 740, 606), fill=(20, 20, 20))

    cleaned, report = remove_shanganren_watermark(image)

    assert report["removed"] is True
    assert cleaned.getpixel((300, 450)) == (255, 255, 255)
    assert cleaned.getpixel((500, 598)) == (20, 20, 20)


def test_toc_is_editable_word_structure(tmp_path: Path) -> None:
    source = tmp_path / "toc.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = toc_page_model(
        page_index=3,
        size=PageSize(515.906, 728.504),
        image_path=source,
        region_directory=tmp_path / "regions",
        source_fingerprint="abc123",
        available_pages={7, 23},
    )
    output = create_positioned_editable_docx([model], tmp_path / "toc.docx")

    with ZipFile(output) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        styles_xml = archive.read("word/styles.xml").decode("utf-8")

    assert 'w:leader="dot"' in document_xml
    assert 'w:anchor="source_page_0007"' in document_xml
    assert "第一章" in document_xml
    assert "解题方法" in document_xml
    assert "SourceTOC1" in styles_xml
    assert model.page_class == "table_of_contents"
    assert model.reconstruction_mode == "word_native_toc_over_source_decoration"


def test_front_matter_classification_is_explicit() -> None:
    nonblank = Image.new("RGB", (500, 700), "white")
    ImageDraw.Draw(nonblank).rectangle((100, 100, 400, 300), fill="black")
    assert classify_source_page(0, nonblank) == "cover"
    assert classify_source_page(3, nonblank) == "table_of_contents"
    assert classify_source_page(5, nonblank) == "section_divider"
    assert classify_source_page(6, nonblank) == "chapter_opener"
    assert classify_source_page(20, nonblank) == "formula_heavy"

    blank = Image.new("RGB", (500, 700), "white")
    assert classify_source_page(1, blank) == "blank"

