"""Source-first reconstruction policies for the 半月谈 workbook.

The source PDF is an outlined InDesign export: it has no usable text layer and
therefore cannot be treated as a normal reflow conversion.  This module makes
the fidelity/editability choice before Word generation.  It deliberately does
not read a previous OCR job or PageModel cache.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from PIL import Image, ImageFilter

from .conflicts import force_full_page_fallback, intersection_area, resolve_page_model_conflicts
from .models import PAGE_MODEL_SCHEMA_VERSION, PageBlock, PageModel, PageSize, PdfKind


PILOT_PAGE_INDICES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 20, 22)


def write_pdf_without_tagged_watermarks(
    source_pdf: str | Path,
    output_pdf: str | Path,
    *,
    page_indices: Iterable[int] | None = None,
) -> dict[str, object]:
    """Clone a PDF while omitting only XObjects tagged as watermarks.

    The source InDesign export marks the recurring ``上岸人`` artwork as a
    PDF ``/Artifact`` whose ``/Subtype`` is ``/Watermark``.  Removing its
    ``Do`` invocation at the content-stream level preserves every underlying
    vector path, including text that a raster colour mask would damage.
    """

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ContentStream

    source = Path(source_pdf)
    destination = Path(output_pdf)
    destination.parent.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(source), strict=False)
    selected = list(page_indices) if page_indices is not None else list(range(len(reader.pages)))
    writer = PdfWriter()
    removed_by_page: dict[str, int] = {}
    removed_total = 0
    for page_index in selected:
        if page_index < 0 or page_index >= len(reader.pages):
            raise IndexError(f"PDF 页索引超出范围：{page_index}")
        writer.add_page(reader.pages[page_index])
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        watermark_scope: list[bool] = []
        filtered: list[tuple[list[object], bytes]] = []
        page_removed = 0
        for operands, operator in stream.operations:
            if operator == b"BDC":
                inherited = watermark_scope[-1] if watermark_scope else False
                current = False
                if len(operands) >= 2 and str(operands[0]) == "/Artifact":
                    properties = operands[1]
                    try:
                        current = str(properties.get("/Subtype")) == "/Watermark"
                    except AttributeError:
                        current = False
                watermark_scope.append(inherited or current)
                filtered.append((operands, operator))
                continue
            if operator == b"BMC":
                watermark_scope.append(watermark_scope[-1] if watermark_scope else False)
                filtered.append((operands, operator))
                continue
            if operator == b"EMC":
                filtered.append((operands, operator))
                if watermark_scope:
                    watermark_scope.pop()
                continue
            if operator == b"Do" and watermark_scope and watermark_scope[-1]:
                page_removed += 1
                removed_total += 1
                continue
            filtered.append((operands, operator))
        if page_removed:
            stream.operations = filtered
            page.replace_contents(stream)
            removed_by_page[str(page_index + 1)] = page_removed
    with destination.open("wb") as handle:
        writer.write(handle)
    return {
        "method": "remove /Artifact /Subtype /Watermark XObject invocation",
        "removed_xobjects": removed_total,
        "affected_pages": removed_by_page,
        "selected_physical_pages": [index + 1 for index in selected],
        "output_pdf": str(destination),
    }


@dataclass(frozen=True, slots=True)
class TocEntry:
    chapter: str
    title: str
    printed_page: str
    physical_page: int


@dataclass(frozen=True, slots=True)
class TocGroup:
    title: str
    entries: tuple[TocEntry, ...]


TOC_PAGE_4 = (
    TocGroup(
        "第三部分　数量关系",
        (
            TocEntry("第一章", "解题方法", "002", 7),
            TocEntry("第二章", "工程问题", "018", 23),
            TocEntry("第三章", "行程问题", "029", 34),
            TocEntry("第四章", "经济利润问题", "041", 46),
            TocEntry("第五章", "容斥原理", "062", 67),
            TocEntry("第六章", "排列组合问题", "065", 70),
            TocEntry("第七章", "概率问题", "071", 76),
            TocEntry("第八章", "最值问题", "076", 81),
            TocEntry("第九章", "几何问题", "084", 89),
            TocEntry("第十章", "趣味杂题", "091", 96),
        ),
    ),
    TocGroup(
        "第四部分　判断推理",
        (
            TocEntry("第一章", "图形推理", "106", 111),
            TocEntry("第二章", "定义判断", "141", 146),
        ),
    ),
)

TOC_PAGE_5 = (
    TocGroup(
        "",
        (
            TocEntry("第三章", "类比推理", "182", 187),
            TocEntry("第四章", "逻辑判断", "208", 213),
        ),
    ),
    TocGroup(
        "第五部分　资料分析",
        (
            TocEntry("第一章", "文字材料", "248", 253),
            TocEntry("第二章", "图形材料", "276", 281),
            TocEntry("第三章", "表格材料", "293", 298),
            TocEntry("第四章", "综合性材料", "312", 317),
        ),
    ),
)


def _bbox_area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _overlap_fraction(left: PageBlock, right: PageBlock) -> float:
    area = _bbox_area(left.bbox)
    return intersection_area(left.bbox, right.bbox) / area if area else 0.0


def classify_source_page(page_index: int, image: Image.Image) -> str:
    """Return the source-first page class for this outlined workbook.

    Front matter is intentionally routed by physical position because those
    pages are publishing artefacts rather than ordinary OCR documents.  The
    blank-page check remains visual so the classification is auditable.
    """

    grayscale = image.convert("L").resize((128, 181), Image.Resampling.BILINEAR)
    ink = sum(1 for value in grayscale.getdata() if value < 247)
    if ink / (grayscale.width * grayscale.height) < 0.0007:
        return "blank"
    if page_index in {0, 2}:
        return "cover"
    if page_index in {3, 4}:
        return "table_of_contents"
    if page_index == 5:
        return "section_divider"
    if page_index in {6, 22}:
        return "chapter_opener"
    if page_index == 20:
        return "formula_heavy"
    return "ordinary_question"


def remove_shanganren_watermark(image: Image.Image) -> tuple[Image.Image, dict[str, object]]:
    """Remove the recurring pale neutral-gray ``上岸人`` source watermark.

    The detector uses a large central connected component of the dominant
    exact neutral gray, then removes only nearby neutral antialias pixels.  Dark
    foreground glyph cores and all magenta artwork are protected.
    """

    source = image.convert("RGB")
    width, height = source.size
    search_box = (
        round(width * 0.18),
        round(height * 0.25),
        round(width * 0.86),
        round(height * 0.80),
    )
    crop = source.crop(search_box)
    pixels = crop.load()
    colors: Counter[tuple[int, int, int]] = Counter()
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue = pixels[x, y]
            mean = (red + green + blue) / 3
            if max(red, green, blue) - min(red, green, blue) <= 2 and 210 <= mean <= 242:
                colors[(red, green, blue)] += 1
    if not colors:
        return source.copy(), {"removed": False, "reason": "no neutral-gray candidate"}
    dominant, count = colors.most_common(1)[0]
    minimum = max(900, crop.width * crop.height // 260)
    if count < minimum:
        return source.copy(), {"removed": False, "reason": "neutral-gray candidate too small"}

    dominant_mean = sum(dominant) / 3
    remaining = {
        (x, y)
        for y in range(crop.height)
        for x in range(crop.width)
        if (
            max(pixels[x, y]) - min(pixels[x, y]) <= 4
            and abs(sum(pixels[x, y]) / 3 - dominant_mean) <= 7
        )
    }
    retained: list[tuple[int, int]] = []
    component_minimum = max(120, crop.width * crop.height // 30_000)
    while remaining:
        start = remaining.pop()
        component = [start]
        frontier: deque[tuple[int, int]] = deque([start])
        while frontier:
            x, y = frontier.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.append(neighbor)
                    frontier.append(neighbor)
        if len(component) >= component_minimum:
            retained.extend(component)
    if not retained:
        return source.copy(), {"removed": False, "reason": "no large connected watermark strokes"}

    min_x = min(x for x, _ in retained)
    max_x = max(x for x, _ in retained)
    min_y = min(y for _, y in retained)
    max_y = max(y for _, y in retained)
    if max_x - min_x < crop.width * 0.24 or max_y - min_y < crop.height * 0.15:
        return source.copy(), {"removed": False, "reason": "candidate geometry is not watermark-like"}

    seed = Image.new("L", crop.size, 0)
    seed_pixels = seed.load()
    for x, y in retained:
        seed_pixels[x, y] = 255
    # A wide but bounded dilation captures antialiased watermark edges whose
    # gray differs from the dominant interior fill.  It only expands around a
    # verified large watermark component, never around arbitrary gray text.
    dilated = seed.filter(ImageFilter.MaxFilter(25))
    dilated_pixels = dilated.load()
    output = source.copy()
    output_pixels = output.load()
    offset_x, offset_y = search_box[0], search_box[1]
    removed_pixels = 0
    for y in range(crop.height):
        for x in range(crop.width):
            if not dilated_pixels[x, y]:
                continue
            red, green, blue = pixels[x, y]
            mean = (red + green + blue) / 3
            # The PDF encodes the same pale watermark through several stacked
            # transparency/antialias levels (roughly RGB 90..240), so removing
            # only its lightest fill leaves a visible diagonal ghost.  This
            # mask is already restricted to the verified watermark strokes;
            # retain near-black glyph cores while clearing all lighter neutral
            # watermark levels.  Chromatic magenta elements are never touched.
            if max(red, green, blue) - min(red, green, blue) <= 9 and 70 <= mean <= 250:
                output_pixels[offset_x + x, offset_y + y] = (255, 255, 255)
                removed_pixels += 1
    return output, {
        "removed": True,
        "dominant_rgb": list(dominant),
        "removed_pixels": removed_pixels,
        "bbox": [offset_x + min_x, offset_y + min_y, offset_x + max_x + 1, offset_y + max_y + 1],
    }


def prepare_clean_source_image(source_path: str | Path, output_path: str | Path) -> dict[str, object]:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as opened:
        cleaned, report = remove_shanganren_watermark(opened)
        cleaned.save(destination, format="PNG", optimize=True, compress_level=6)
    return report


def _model_base(
    *,
    page_index: int,
    size: PageSize,
    image_path: str | Path,
    page_class: str,
    reconstruction_mode: str,
    source_fingerprint: str,
) -> PageModel:
    with Image.open(image_path) as image:
        width, height = image.size
    return PageModel(
        schema_version=PAGE_MODEL_SCHEMA_VERSION,
        page_index=page_index,
        size=size,
        source_type=PdfKind.OUTLINED,
        source_image_width_px=width,
        source_image_height_px=height,
        page_class=page_class,
        reconstruction_mode=reconstruction_mode,
        source_fingerprint=source_fingerprint,
    )


def blank_page_model(
    *, page_index: int, size: PageSize, image_path: str | Path, source_fingerprint: str
) -> PageModel:
    model = _model_base(
        page_index=page_index,
        size=size,
        image_path=image_path,
        page_class="blank",
        reconstruction_mode="blank_source_page",
        source_fingerprint=source_fingerprint,
    )
    model.warnings.append("源 PDF 空白页已按物理页序保留。")
    return model


def source_fallback_model(
    *,
    page_index: int,
    size: PageSize,
    image_path: str | Path,
    region_directory: str | Path,
    page_class: str,
    source_fingerprint: str,
    reason: str,
    bookmark_name: str | None = None,
) -> PageModel:
    model = _model_base(
        page_index=page_index,
        size=size,
        image_path=image_path,
        page_class=page_class,
        reconstruction_mode="clean_full_page_source_image",
        source_fingerprint=source_fingerprint,
    )
    force_full_page_fallback(model, image_path, region_directory, reason=reason)
    if bookmark_name and model.blocks:
        model.blocks[0].style["bookmark_name"] = bookmark_name
    return model


def _whiteout_normalized(image: Image.Image, box: tuple[float, float, float, float]) -> None:
    left = max(0, round(image.width * box[0]))
    top = max(0, round(image.height * box[1]))
    right = min(image.width, round(image.width * box[2]))
    bottom = min(image.height, round(image.height * box[3]))
    pixels = image.load()
    for y in range(top, bottom):
        for x in range(left, right):
            pixels[x, y] = (255, 255, 255)


def _px_box(image: Image.Image, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (
        image.width * box[0],
        image.height * box[1],
        image.width * box[2],
        image.height * box[3],
    )


def _toc_group_block(
    image: Image.Image,
    *,
    block_id: str,
    text: str,
    box: tuple[float, float, float, float],
    reading_order: int,
) -> PageBlock:
    return PageBlock(
        block_id=block_id,
        block_type="toc_group",
        bbox=_px_box(image, box),
        z_index=2,
        reading_order=reading_order,
        text=text,
        style={
            "font_color": "F4008A",
            "font_size_pt": 17.5,
            "textbox_min_height_pt": 25.0,
            "font_name_east_asia": "STSong",
            "font_name_ascii": "STSong",
            "text_alignment": "center",
        },
        source="source PDF verified table-of-contents transcription",
        selection_reason="Word-native editable TOC group",
    )


def _toc_entry_block(
    image: Image.Image,
    *,
    block_id: str,
    entry: TocEntry,
    box: tuple[float, float, float, float],
    reading_order: int,
    available_pages: set[int],
) -> PageBlock:
    style: dict[str, object] = {
        "toc_chapter": entry.chapter,
        "toc_title": entry.title,
        "toc_page": entry.printed_page,
        "font_color": "F4008A",
        "font_size_pt": 10.5,
        "textbox_min_height_pt": 16.0,
        "font_name_east_asia": "STSong",
        "toc_level": 1,
    }
    if entry.physical_page in available_pages:
        style["target_bookmark"] = f"source_page_{entry.physical_page:04d}"
    return PageBlock(
        block_id=block_id,
        block_type="toc_entry",
        bbox=_px_box(image, box),
        z_index=2,
        reading_order=reading_order,
        text=f"{entry.chapter}　{entry.title}\t{entry.printed_page}",
        style=style,
        source="source PDF verified table-of-contents transcription",
        selection_reason="Word-native editable TOC entry with dot leader",
    )


def toc_page_model(
    *,
    page_index: int,
    size: PageSize,
    image_path: str | Path,
    region_directory: str | Path,
    source_fingerprint: str,
    available_pages: Iterable[int],
) -> PageModel:
    """Create an editable magenta TOC over a source-faithful decoration layer."""

    destination = Path(region_directory)
    destination.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
        model = _model_base(
            page_index=page_index,
            size=size,
            image_path=image_path,
            page_class="table_of_contents",
            reconstruction_mode="word_native_toc_over_source_decoration",
            source_fingerprint=source_fingerprint,
        )
        # Use non-overlapping decoration strips instead of one full-page
        # background.  Normal Word TOC paragraphs then remain on the document
        # text layer and cannot be hidden by VML stacking differences between
        # Microsoft Word and LibreOffice.
        top_bottom = 0.395 if page_index == 3 else 0.105
        for block_id, normalized_box in (
            ("toc-source-decoration-top", (0.0, 0.0, 1.0, top_bottom)),
            ("toc-source-decoration-footer", (0.0, 0.915, 1.0, 1.0)),
        ):
            left, top, right, bottom = _px_box(image, normalized_box)
            asset = destination / f"{block_id}.png"
            image.crop((round(left), round(top), round(right), round(bottom))).save(
                asset,
                format="PNG",
                optimize=True,
                compress_level=6,
            )
            model.blocks.append(
                PageBlock(
                    block_id=block_id,
                    block_type="image",
                    bbox=(left, top, right, bottom),
                    z_index=0,
                    reading_order=-10,
                    asset_path=str(asset),
                    source="clean source PDF TOC decoration strip",
                    selection_reason="retain non-overlapping decorative artwork while TOC text stays editable",
                    fallback_mode="source_decoration_strip",
                )
            )
        available = set(available_pages)
        order = 0
        if page_index == 3:
            model.blocks.append(_toc_group_block(image, block_id="toc-group-3", text=TOC_PAGE_4[0].title, box=(0.36, 0.400, 0.69, 0.438), reading_order=order))
            order += 1
            for index, entry in enumerate(TOC_PAGE_4[0].entries):
                top = 0.453 + index * 0.03165
                model.blocks.append(_toc_entry_block(image, block_id=f"toc-entry-3-{index + 1}", entry=entry, box=(0.19, top, 0.84, top + 0.022), reading_order=order, available_pages=available))
                order += 1
            model.blocks.append(_toc_group_block(image, block_id="toc-group-4", text=TOC_PAGE_4[1].title, box=(0.36, 0.792, 0.69, 0.830), reading_order=order))
            order += 1
            for index, entry in enumerate(TOC_PAGE_4[1].entries):
                top = 0.846 + index * 0.0318
                model.blocks.append(_toc_entry_block(image, block_id=f"toc-entry-4-{index + 1}", entry=entry, box=(0.19, top, 0.84, top + 0.022), reading_order=order, available_pages=available))
                order += 1
        else:
            for index, entry in enumerate(TOC_PAGE_5[0].entries):
                top = 0.126 + index * 0.0317
                model.blocks.append(_toc_entry_block(image, block_id=f"toc-entry-4c-{index + 1}", entry=entry, box=(0.18, top, 0.83, top + 0.022), reading_order=order, available_pages=available))
                order += 1
            model.blocks.append(_toc_group_block(image, block_id="toc-group-5", text=TOC_PAGE_5[1].title, box=(0.35, 0.218, 0.68, 0.256), reading_order=order))
            order += 1
            for index, entry in enumerate(TOC_PAGE_5[1].entries):
                top = 0.268 + index * 0.0317
                model.blocks.append(_toc_entry_block(image, block_id=f"toc-entry-5-{index + 1}", entry=entry, box=(0.18, top, 0.83, top + 0.022), reading_order=order, available_pages=available))
                order += 1
        model.warnings.append("目录装饰来自源页；目录组、章节名、点引导线和页码为可编辑 Word 结构。")
        return resolve_page_model_conflicts(model)


_FORMULA_LINE = re.compile(r"(?:[A-Za-zχxy]\s*)?\d*[^\n]{0,40}[=×÷][^\n]*")


def _crop_block(image: Image.Image, block: PageBlock, destination: Path, *, margin: int = 4) -> None:
    left = max(0, round(block.bbox[0]) - margin)
    top = max(0, round(block.bbox[1]) - margin)
    right = min(image.width, round(block.bbox[2]) + margin)
    bottom = min(image.height, round(block.bbox[3]) + margin)
    block.bbox = (float(left), float(top), float(right), float(bottom))
    destination.mkdir(parents=True, exist_ok=True)
    asset = destination / f"{block.block_id}.png"
    image.crop((left, top, right, bottom)).save(asset, format="PNG", optimize=True, compress_level=6)
    block.asset_path = str(asset)
    block.fallback_mode = block.fallback_mode or "clean_source_region_image"
    block.source = block.source or "watermark-cleaned source PDF crop"


def _replace_formula_lines(model: PageModel, image: Image.Image, destination: Path) -> None:
    candidates = [
        block
        for block in model.blocks
        if block.block_type == "text_line"
        and block.text
        and _FORMULA_LINE.search(block.text.replace(" ", ""))
        and sum(block.text.count(token) for token in ("=", "×", "÷", "/")) >= 1
    ]
    removed: set[str] = set()
    replacements: list[PageBlock] = []
    for index, candidate in enumerate(candidates, start=1):
        if candidate.block_id in removed:
            continue
        group = [candidate]
        for other in model.blocks:
            if other is candidate or other.block_type != "text_line" or not other.text:
                continue
            vertical_overlap = max(
                0.0,
                min(candidate.bbox[3], other.bbox[3]) - max(candidate.bbox[1], other.bbox[1]),
            )
            min_height = min(candidate.bbox[3] - candidate.bbox[1], other.bbox[3] - other.bbox[1])
            horizontal_gap = max(
                0.0,
                max(candidate.bbox[0], other.bbox[0]) - min(candidate.bbox[2], other.bbox[2]),
            )
            # Formula OCR commonly splits fractions, operators and operands into
            # horizontally disjoint blocks.  Two-dimensional intersection is
            # therefore the wrong grouping signal: same-baseline fragments have
            # no intersection area.  Use line overlap plus a bounded horizontal
            # gap so the entire equation becomes one exclusive source crop.
            if (
                min_height > 0
                and vertical_overlap / min_height >= 0.35
                and horizontal_gap <= max(80.0, image.width * 0.055)
            ):
                group.append(other)
        left = min(item.bbox[0] for item in group)
        top = min(item.bbox[1] for item in group)
        right = max(item.bbox[2] for item in group)
        bottom = max(item.bbox[3] for item in group)
        replacement = PageBlock(
            block_id=f"source-first-formula-line-{index}",
            block_type="formula",
            bbox=(left, top, right, bottom),
            z_index=min(item.z_index for item in group),
            reading_order=min(item.reading_order for item in group),
            source="watermark-cleaned source PDF formula line",
            selection_reason="equation-bearing line is not reliable as editable OCR",
            fallback_mode="formula_line_source_image",
        )
        _crop_block(image, replacement, destination, margin=6)
        replacements.append(replacement)
        removed.update(item.block_id for item in group)
    if removed:
        model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements


def _replace_sidebars(model: PageModel, image: Image.Image, destination: Path) -> None:
    sidebars = [block for block in model.blocks if block.block_type.lower() == "aside_text"]
    for index, sidebar in enumerate(sidebars, start=1):
        left_side = (sidebar.bbox[0] + sidebar.bbox[2]) / 2 < image.width / 2
        if left_side:
            left = max(0, round(sidebar.bbox[0] - 35))
            right = min(image.width, round(max(sidebar.bbox[2] + 35, image.width * 0.16)))
        else:
            left = max(0, round(min(sidebar.bbox[0] - 35, image.width * 0.84)))
            right = min(image.width, round(sidebar.bbox[2] + 35))
        top = max(0, round(sidebar.bbox[1] - 18))
        bottom = image.height
        replacement = PageBlock(
            block_id=f"source-first-sidebar-{index}",
            block_type="image",
            bbox=(float(left), float(top), float(right), float(bottom)),
            z_index=sidebar.z_index,
            reading_order=sidebar.reading_order,
            source="watermark-cleaned source PDF sidebar",
            selection_reason="vertical sidebar typography is decorative and not reliable editable text",
            fallback_mode="sidebar_source_image",
        )
        _crop_block(image, replacement, destination, margin=0)
        retained: list[PageBlock] = []
        for block in model.blocks:
            center_x = (block.bbox[0] + block.bbox[2]) / 2
            center_y = (block.bbox[1] + block.bbox[3]) / 2
            if left <= center_x <= right and top <= center_y <= bottom:
                continue
            retained.append(block)
        model.blocks = retained + [replacement]


def _replace_talk_prefixes(model: PageModel, image: Image.Image, destination: Path) -> None:
    markers = [
        block
        for block in model.blocks
        if block.block_type.lower() in {"talk_badge_image", "talk_callout_tag_image"}
        or (block.asset_path and (block.text or "").strip() == "谈")
    ]
    removed: set[str] = set()
    replacements: list[PageBlock] = []
    for index, marker in enumerate(markers, start=1):
        center_y = (marker.bbox[1] + marker.bbox[3]) / 2
        nearby = [
            block
            for block in model.blocks
            if block.text
            and abs(((block.bbox[1] + block.bbox[3]) / 2) - center_y) <= max(35.0, marker.bbox[3] - marker.bbox[1])
            and block.bbox[0] >= marker.bbox[0] - 10
            and block.bbox[0] < image.width * 0.72
        ]
        is_index = any("指数" in (block.text or "") or block.style.get("semantic_role") == "callout_index" for block in nearby)
        if is_index:
            selected = [block for block in nearby if "指数" in (block.text or "") or block.style.get("semantic_role") == "callout_index"]
            right = max([marker.bbox[2] + 180] + [block.bbox[2] for block in selected]) + 8
        else:
            labels = [block for block in nearby if (block.text or "").strip() in {"谈", "指数", "解析", "答案", "提示"}]
            right = max([marker.bbox[2] + 155] + [block.bbox[2] for block in labels]) + 8
            selected = labels
        top = min([marker.bbox[1]] + [block.bbox[1] for block in selected]) - 6
        bottom = max([marker.bbox[3]] + [block.bbox[3] for block in selected]) + 6
        replacement = PageBlock(
            block_id=f"source-first-talk-prefix-{index}",
            block_type="talk_callout_tag_image",
            bbox=(marker.bbox[0] - 6, top, min(float(image.width), right), bottom),
            z_index=marker.z_index,
            reading_order=marker.reading_order,
            source="watermark-cleaned source PDF callout prefix",
            selection_reason="decorative talk badge/label/rating retained as one reliable source crop",
            fallback_mode="callout_prefix_source_image",
        )
        _crop_block(image, replacement, destination, margin=0)
        replacements.append(replacement)
        for block in model.blocks:
            if _overlap_fraction(block, replacement) >= 0.45:
                removed.add(block.block_id)
    if replacements:
        model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements


def apply_source_first_hybrid_policy(
    model: PageModel,
    clean_image_path: str | Path,
    region_directory: str | Path,
    *,
    source_fingerprint: str,
) -> PageModel:
    """Postprocess a fresh OCR model into an accuracy-first ordinary page."""

    destination = Path(region_directory)
    with Image.open(clean_image_path) as opened:
        image = opened.convert("RGB")
        model.schema_version = PAGE_MODEL_SCHEMA_VERSION
        model.page_class = "ordinary_question"
        model.reconstruction_mode = "editable_text_with_clean_source_region_fallbacks"
        model.source_fingerprint = source_fingerprint
        model.source_image_width_px, model.source_image_height_px = image.size
        # The source image is already cleaned, so a previously inferred
        # watermark layer must never be carried into Word.
        model.blocks = [block for block in model.blocks if block.block_type.lower() != "watermark"]
        _replace_formula_lines(model, image, destination)
        _replace_talk_prefixes(model, image, destination)
        _replace_sidebars(model, image, destination)
        for block in model.blocks:
            if block.text and not block.asset_path and block.block_type == "text_line":
                scale_y = model.size.height_pt / max(1, image.height)
                source_height_pt = (block.bbox[3] - block.bbox[1]) * scale_y
                block.style["font_size_pt"] = round(max(8.6, min(10.2, source_height_pt * 0.88)), 2)
                block.style["font_name_east_asia"] = "SimSun"
                block.style["font_name_ascii"] = "Times New Roman"
                block.style["textbox_min_height_pt"] = round(max(13.0, source_height_pt * 1.30), 2)
                block.style["justify_to_bbox"] = bool(len("".join(block.text.split())) >= 22 and (block.bbox[2] - block.bbox[0]) >= image.width * 0.60)
                block.source = block.source or "fresh source-first PaddleOCR"
                block.selection_reason = block.selection_reason or "fresh OCR retained as editable ordinary text"
        model.warnings.append("此页从源 PDF 新渲染并重新 OCR；未读取旧任务缓存。")
        model.warnings.append("上岸人水印在 OCR 和回退裁图之前已从源渲染中清理。")
    return resolve_page_model_conflicts(model)
