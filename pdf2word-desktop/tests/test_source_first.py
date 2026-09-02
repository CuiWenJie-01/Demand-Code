from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from pdf2word_engine.models import PageBlock, PageModel, PageSize, PdfKind
from pdf2word_engine.quality import assert_body_content_editable, body_image_blocks
from pdf2word_engine.source_first import (
    _derive_source_line_layouts,
    _save_transparent_label_crop,
    apply_region_level_static_fallbacks,
    apply_source_first_hybrid_policy,
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


def test_chapter_opener_keeps_body_editable_and_only_crops_header(tmp_path: Path) -> None:
    source = tmp_path / "chapter.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = PageModel(
        schema_version=6,
        page_index=6,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock("logo", "text_line", (80, 70, 250, 110), 0, 0, confidence=0.99, text="半月谈"),
            PageBlock("title", "header", (330, 190, 680, 245), 0, 1, confidence=0.99, text="第一章 解题方法"),
            PageBlock("q1", "text_line", (145, 340, 900, 375), 0, 2, confidence=0.99, text="1.（2018年国考）正文第一行"),
            PageBlock("q1b", "text_line", (145, 390, 900, 425), 0, 3, confidence=0.99, text="正文第二行仍应可编辑"),
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="chapter_opener",
    )

    decoration = next(block for block in result.blocks if block.block_type == "decoration_image")
    editable_text = "".join(block.text or "" for block in result.blocks if not block.asset_path)
    assert decoration.bbox[3] < 340
    assert "第一章" not in editable_text
    assert "正文第一行" in editable_text
    assert "正文第二行" in editable_text
    assert result.evidence_blocks[0].text == "半月谈"


def test_callout_fallback_uses_one_complete_first_row_and_keeps_later_body_editable(tmp_path: Path) -> None:
    source = tmp_path / "callout.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = PageModel(
        schema_version=7,
        page_index=8,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock("badge", "talk_badge_image", (100, 300, 160, 360), 0, 0),
            PageBlock("inline-badge", "talk_badge_image", (225, 310, 275, 360), 0, 1),
            PageBlock("label", "text_line", (170, 305, 230, 350), 0, 2, text="解析", style={"semantic_role": "callout_label"}),
            PageBlock("first", "text_line", (250, 305, 850, 350), 0, 3, text="第一行与标签必须作为完整源图，不得相互覆盖。"),
            PageBlock("second", "text_line", (250, 385, 850, 430), 0, 4, text="第二行正文仍然必须可以编辑。"),
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="ordinary_question",
    )

    row = next(block for block in result.blocks if block.fallback_mode == "callout_first_row_source_image")
    editable_text = "".join(block.text or "" for block in result.blocks if not block.asset_path)
    assert row.bbox[2] > 850
    assert row.bbox[3] < 385
    assert len([block for block in result.blocks if block.fallback_mode == "callout_first_row_source_image"]) == 1
    assert "第一行" not in editable_text
    assert "第二行正文仍然必须可以编辑" in editable_text


def test_strict_editable_body_keeps_formula_and_callout_text_native(tmp_path: Path) -> None:
    source = tmp_path / "strict.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = PageModel(
        schema_version=7,
        page_index=8,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock("badge", "text_line", (157, 300, 205, 355), 0, 0, text="谈"),
            PageBlock("duplicate-badge", "talk_badge_image", (230, 305, 275, 360), 0, 1),
            PageBlock("label", "text_line", (210, 305, 270, 350), 0, 2, text="解析", style={"semantic_role": "callout_label"}),
            PageBlock("math", "text_line", (290, 305, 850, 350), 0, 3, confidence=0.99, text="8x+3y=6300，χ=630。"),
            PageBlock("plain", "text_line", (250, 385, 850, 430), 0, 4, confidence=0.99, text="普通解释文字仍然保持可编辑。"),
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "strict-regions",
        source_fingerprint="fresh",
        page_class="ordinary_question",
        editable_body_only=True,
    )

    editable_text = "".join(block.text or "" for block in result.blocks if not block.asset_path)
    images = [block for block in result.blocks if block.asset_path]
    assert len(images) == 1
    assert images[0].fallback_mode == "talk_label_source_image"
    assert images[0].text == "解析"
    assert images[0].style["inline_decorative"] is True
    assert images[0].style["inline_host_block_id"]
    assert "解析" not in editable_text
    assert "8x+3y=6300，x=630" in editable_text
    assert "普通解释文字仍然保持可编辑" in editable_text
    assert body_image_blocks(result) == []
    assert_body_content_editable([result])


def test_talk_label_crop_uses_magenta_ink_bounds_not_the_badge_box(tmp_path: Path) -> None:
    source = Image.new("RGB", (320, 260), "white")
    draw = ImageDraw.Draw(source)
    # The visible label extends beyond the old 100..160 badge rectangle.
    draw.rectangle((105, 76, 214, 187), fill=(239, 22, 139))
    output = tmp_path / "talk.png"

    bbox, has_pink = _save_transparent_label_crop(source, (100, 60, 230, 210), output)

    with Image.open(output) as asset:
        alpha_bounds = asset.convert("RGBA").getchannel("A").getbbox()
        assert alpha_bounds is not None
        left, top, right, bottom = alpha_bounds
        assert left >= 2 and top >= 2
        assert right <= asset.width - 2 and bottom <= asset.height - 2
    assert has_pink is True
    assert bbox[1] <= 76 and bbox[3] >= 187


def test_answer_blank_is_bound_to_question_final_line(tmp_path: Path) -> None:
    source = tmp_path / "answer-blank.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = PageModel(
        schema_version=8,
        page_index=8,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock("stem", "text_line", (100, 100, 900, 205), 0, 0, confidence=0.99, text="1.题干最后一行在这里"),
            PageBlock("open", "text_line", (820, 178, 840, 200), 0, 1, confidence=0.99, text="（", style={"semantic_role": "answer_blank"}),
            PageBlock("close", "text_line", (870, 178, 890, 200), 0, 2, confidence=0.99, text="）", style={"semantic_role": "answer_blank"}),
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="ordinary_question",
        editable_body_only=True,
    )

    stem = next(block for block in result.blocks if "题干最后一行" in (block.text or ""))
    assert stem.text is not None and stem.text.endswith("\t（　）")
    assert stem.style["right_tab_stops_px"] == [790.0]
    assert not any(str(block.style.get("semantic_role")) == "answer_blank" for block in result.blocks)


def test_source_line_layout_is_generic_for_multiline_callout_and_answer_blank() -> None:
    source = Image.new("RGB", (1000, 500), "white")
    draw = ImageDraw.Draw(source)
    # Two source-width rows and a short final row with its answer blank.
    draw.rectangle((100, 100, 892, 114), fill="black")
    draw.rectangle((100, 145, 892, 159), fill="black")
    draw.rectangle((100, 190, 510, 204), fill="black")
    draw.rectangle((840, 190, 870, 204), fill="black")
    model = PageModel(
        schema_version=10,
        page_index=0,
        size=PageSize(500, 700),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=500,
        blocks=[
            PageBlock(
                "analysis",
                "editable_callout_body",
                (100, 90, 900, 220),
                0,
                0,
                text="解析正文第一行\n解析正文第二行\n解析最后一行\t（　）",
                style={"answer_blank_source_ids": ["open", "close"]},
            )
        ],
        evidence_blocks=[
            PageBlock("open", "text_line", (840, 190, 850, 204), 0, 1, text="（"),
            PageBlock("close", "text_line", (860, 190, 870, 204), 0, 2, text="）"),
        ],
    )

    _derive_source_line_layouts(model, source)

    layout = model.blocks[0].style["source_line_layout"]
    assert [row["justify"] for row in layout] == [True, True, False]
    assert layout[-1]["right_px"] < 520


def test_body_image_gate_rejects_formula_crop_but_accepts_decoration(tmp_path: Path) -> None:
    asset = tmp_path / "asset.png"
    Image.new("RGB", (20, 20), "white").save(asset)
    model = PageModel(
        schema_version=7,
        page_index=7,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock(
                "header",
                "header",
                (50, 50, 200, 100),
                0,
                0,
                asset_path=str(asset),
                fallback_mode="region_source_image",
            ),
            PageBlock(
                "formula",
                "formula",
                (200, 400, 800, 460),
                0,
                1,
                asset_path=str(asset),
                fallback_mode="formula_line_source_image",
            ),
        ],
    )

    assert [block.block_id for block in body_image_blocks(model)] == ["formula"]
    try:
        assert_body_content_editable([model])
    except ValueError as exc:
        assert "正文零图片门禁失败" in str(exc)
        assert "formula" in str(exc)
    else:
        raise AssertionError("body image gate should reject formula crops")


def test_sidebar_crop_does_not_capture_editable_body_start(tmp_path: Path) -> None:
    source = tmp_path / "sidebar.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = PageModel(
        schema_version=7,
        page_index=20,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock("sidebar", "aside_text", (60, 900, 90, 1300), 0, 0, text="第三部分数量关系"),
            PageBlock("body", "text_line", (125, 940, 900, 990), 0, 1, text="=4万吨。正文必须只出现一次。"),
            PageBlock("page-number", "number", (60, 1330, 120, 1365), 0, 2, text="016"),
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="formula_heavy",
    )

    sidebar = next(block for block in result.blocks if block.fallback_mode == "sidebar_source_image")
    page_number = next(block for block in result.blocks if block.fallback_mode == "sidebar_page_number_source_image")
    editable_text = "".join(block.text or "" for block in result.blocks if not block.asset_path)
    assert sidebar.bbox[2] <= 125
    assert sidebar.bbox[3] <= page_number.bbox[1]
    assert page_number.bbox[2] > 120
    assert "=4万吨" in editable_text
    assert "016" not in editable_text


def test_static_gate_replaces_only_failing_region_not_page(tmp_path: Path) -> None:
    source = tmp_path / "page.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = PageModel(
        schema_version=7,
        page_index=7,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        page_class="ordinary_question",
        blocks=[
            PageBlock("good", "editable_paragraph", (100, 200, 900, 250), 0, 0, confidence=0.99, text="可靠正文"),
            PageBlock("bad", "editable_paragraph", (100, 300, 900, 350), 0, 1, confidence=0.70, text="低置信度正文"),
        ],
    )

    result = apply_region_level_static_fallbacks(model, source, tmp_path / "fallbacks")

    assert any(block.block_id == "good" for block in result.blocks)
    fallback = next(block for block in result.blocks if block.block_type == "region_fallback_image")
    assert Path(fallback.asset_path or "").is_file()
    assert fallback.bbox == (95.0, 295.0, 905.0, 355.0)
    assert all(block.block_type != "full_page_fallback" for block in result.blocks)


def test_uncovered_source_ink_is_repaired_by_local_source_crop(tmp_path: Path) -> None:
    source = tmp_path / "missing-line.png"
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    for x in range(150, 850, 32):
        draw.rectangle((x, 500, x + 20, 516), fill="black")
    for x in range(150, 310, 24):
        draw.rectangle((x, 800, x + 16, 820), fill="black")
    image.save(source)
    model = PageModel(
        schema_version=7,
        page_index=7,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock(
                "recognized-line",
                "text_line",
                (150, 600, 850, 635),
                0,
                0,
                confidence=0.99,
                text="这一行已被识别，上一行完全漏检。",
            )
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="ordinary_question",
    )

    repairs = [block for block in result.blocks if block.fallback_mode == "uncovered_source_region_image"]
    repair = next(block for block in repairs if block.bbox[1] < 500 < block.bbox[3])
    assert repair.bbox[1] < 500 < repair.bbox[3]
    assert Path(repair.asset_path or "").is_file()
    assert any(block.bbox[1] < 800 < block.bbox[3] for block in repairs)
    assert all(block.block_type != "full_page_fallback" for block in result.blocks)


def test_linear_formula_line_uses_source_crop_and_keeps_plain_line_editable(tmp_path: Path) -> None:
    source = tmp_path / "formula.png"
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 300, 850, 334), fill="black")
    image.save(source)
    model = PageModel(
        schema_version=7,
        page_index=22,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock("math", "text_line", (150, 300, 850, 335), 0, 0, confidence=0.99, text="8+3y=6300，6x+6y=6300。"),
            PageBlock("plain", "text_line", (150, 400, 850, 435), 0, 1, confidence=0.99, text="普通解释文字仍然保持可编辑。"),
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="ordinary_question",
    )

    formula = next(block for block in result.blocks if block.fallback_mode == "formula_line_source_image")
    editable_text = "".join(block.text or "" for block in result.blocks if not block.asset_path)
    assert Path(formula.asset_path or "").is_file()
    assert "8+3y" not in editable_text
    assert "普通解释文字仍然保持可编辑" in editable_text


def test_single_fraction_numerator_claims_omitted_denominator(tmp_path: Path) -> None:
    source = tmp_path / "fraction.png"
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((500, 300, 516, 320), fill="black")
    draw.line((494, 328, 522, 328), fill="black", width=3)
    draw.rectangle((500, 338, 516, 358), fill="black")
    image.save(source)
    model = PageModel(
        schema_version=7,
        page_index=6,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock("prefix", "text_line", (150, 306, 480, 336), 0, 0, confidence=0.99, text="生产人数为总数的"),
            PageBlock("numerator", "text_line", (500, 300, 516, 320), 0, 1, confidence=0.99, text="4"),
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="chapter_opener",
    )

    formula = next(block for block in result.blocks if block.fallback_mode == "formula_row_source_image")
    assert formula.bbox[1] < 300
    assert formula.bbox[3] > 350
    assert all((block.text or "") != "4" for block in result.blocks)


def test_width_fit_marks_single_line_that_would_clip_in_word(tmp_path: Path) -> None:
    source = tmp_path / "long-line.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    model = PageModel(
        schema_version=7,
        page_index=20,
        size=PageSize(515.906, 728.504),
        source_type=PdfKind.OUTLINED,
        source_image_width_px=1000,
        source_image_height_px=1400,
        blocks=[
            PageBlock(
                "long",
                "text_line",
                (150, 300, 800, 335),
                0,
                0,
                confidence=0.99,
                text="每当有一个人捐款额变为二千元总钱数增加一千七百元并且这一整行必须完整显示不能裁掉尾字。",
            )
        ],
    )

    result = apply_source_first_hybrid_policy(
        model,
        source,
        tmp_path / "regions",
        source_fingerprint="fresh",
        page_class="formula_heavy",
    )

    editable = next(block for block in result.blocks if block.text and not block.asset_path)
    assert editable.style["width_fit_applied"] is True
    assert editable.style["font_size_pt"] < 10.2
    assert any(record["action"] == "editable_width_fit" for record in result.debug_records)

