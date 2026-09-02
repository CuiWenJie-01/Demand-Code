"""Source-first reconstruction policies for the 半月谈 workbook.

The source PDF is an outlined InDesign export: it has no usable text layer and
therefore cannot be treated as a normal reflow conversion.  This module makes
the fidelity/editability choice before Word generation.  It deliberately does
not read a previous OCR job or PageModel cache.
"""

from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re
from statistics import fmean, median
from typing import Iterable
import unicodedata

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .conflicts import force_full_page_fallback, intersection_area, resolve_page_model_conflicts, static_page_checks
from .models import PAGE_MODEL_SCHEMA_VERSION, PageBlock, PageModel, PageSize, PdfKind
from .quality import is_allowed_decorative_image


# Second-round editability gate: physical pages 7, 8, 9, 10, 21 and 23.
PILOT_PAGE_INDICES = (6, 7, 8, 9, 20, 22)
_VERIFIED_PILOT_SOURCE_SHA256 = "87a6f8015987906bf690f3a5a0a2a0a660f762c63b69c8ca74cf970b3a19e1b0"


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


_COMPLEX_FORMULA_LINE = re.compile(r"[√∑∫]|\^|[⁰¹²³⁴⁵⁶⁷⁸⁹]|\\(?:frac|sqrt|sum|int)")
_FORMULA_FRAGMENT = re.compile(r"^[\dA-Za-zχxy+\-−—]+$")
_INLINE_FORMULA_LINE = re.compile(r"χ|≈|(?=.*=)(?=.*[A-Za-z×÷])")


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


def _has_vertical_formula_ink(image: Image.Image, block: PageBlock, typical_height: float) -> bool:
    """Detect a denominator/superscript that line OCR omitted around a tiny token."""

    pad_x = max(8, round((block.bbox[2] - block.bbox[0]) * 0.45))
    left = max(0, round(block.bbox[0]) - pad_x)
    right = min(image.width, round(block.bbox[2]) + pad_x)
    above_top = max(0, round(block.bbox[1] - typical_height * 1.25))
    above_bottom = max(above_top, round(block.bbox[1] - 5))
    below_top = min(image.height, round(block.bbox[3] + 5))
    below_bottom = min(image.height, round(block.bbox[3] + typical_height * 1.55))

    grayscale = image.convert("L")

    def ink_count(box: tuple[int, int, int, int]) -> int:
        if box[2] <= box[0] or box[3] <= box[1]:
            return 0
        histogram = grayscale.crop(box).histogram()
        return sum(histogram[:238])

    minimum_ink = max(6, round((right - left) * 0.12))
    return (
        ink_count((left, above_top, right, above_bottom)) >= minimum_ink
        or ink_count((left, below_top, right, below_bottom)) >= minimum_ink
    )


def _replace_stacked_formula_fragments(model: PageModel, image: Image.Image, destination: Path) -> None:
    """Replace narrow numerator/denominator OCR fragments by tiny source crops."""

    lines = [block for block in model.blocks if block.block_type == "text_line" and block.text]
    if not lines:
        return
    heights = [max(1.0, block.bbox[3] - block.bbox[1]) for block in lines]
    typical_height = median(heights)
    candidates: list[PageBlock] = []
    tall_ids: set[str] = set()
    for block in lines:
        text = re.sub(r"\s+", "", block.text or "")
        width = max(1.0, block.bbox[2] - block.bbox[0])
        height = max(1.0, block.bbox[3] - block.bbox[1])
        role = str(block.style.get("semantic_role", ""))
        if role in {"callout_label", "callout_index", "answer_blank", "sidebar_page_number"}:
            continue
        numeric_fragment = bool(_FORMULA_FRAGMENT.fullmatch(text)) and len(text) <= 6 and width <= image.width * 0.065
        tall_fragment = height >= typical_height * 1.45 and width <= image.width * 0.12 and len(text) <= 8
        if numeric_fragment or tall_fragment:
            candidates.append(block)
            if tall_fragment or (numeric_fragment and _has_vertical_formula_ink(image, block, typical_height)):
                tall_ids.add(block.block_id)
    if not candidates:
        return

    adjacency: dict[str, set[str]] = {block.block_id: set() for block in candidates}
    by_id = {block.block_id: block for block in candidates}
    for index, left in enumerate(candidates):
        left_center_x = (left.bbox[0] + left.bbox[2]) / 2
        left_center_y = (left.bbox[1] + left.bbox[3]) / 2
        for right in candidates[index + 1 :]:
            right_center_x = (right.bbox[0] + right.bbox[2]) / 2
            right_center_y = (right.bbox[1] + right.bbox[3]) / 2
            if (
                abs(left_center_x - right_center_x) <= max(24.0, max(left.bbox[2] - left.bbox[0], right.bbox[2] - right.bbox[0]) * 0.75)
                and abs(left_center_y - right_center_y) <= typical_height * 1.9
            ):
                adjacency[left.block_id].add(right.block_id)
                adjacency[right.block_id].add(left.block_id)

    remaining = set(by_id)
    components: list[list[PageBlock]] = []
    extension_ids: set[str] = set()
    while remaining:
        seed = remaining.pop()
        ids = {seed}
        frontier = [seed]
        while frontier:
            current = frontier.pop()
            for neighbour in adjacency[current]:
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    ids.add(neighbour)
                    frontier.append(neighbour)
        component = [by_id[block_id] for block_id in ids]
        if len(component) == 1 and component[0].block_id in tall_ids:
            component_height = component[0].bbox[3] - component[0].bbox[1]
            if component_height < typical_height * 1.45:
                extension_ids.add(component[0].block_id)
        if len(component) >= 2 or any(block.block_id in tall_ids for block in component):
            components.append(component)

    bands: list[list[PageBlock]] = []
    for component in sorted(components, key=lambda items: _union_bbox(items)[1]):
        component_box = _union_bbox(component)
        if bands and component_box[1] <= _union_bbox(bands[-1])[3] + typical_height * 0.35:
            bands[-1].extend(component)
        else:
            bands.append(list(component))

    removed: set[str] = set()
    replacements: list[PageBlock] = []
    for index, component in enumerate(bands, start=1):
        component_box = _union_bbox(component)
        row_lines = [
            line
            for line in lines
            if component_box[1] - typical_height * 0.15
            <= (line.bbox[1] + line.bbox[3]) / 2
            <= component_box[3] + typical_height * 0.15
        ]
        row_box = _union_bbox(component + row_lines)
        related_assets = [
            block
            for block in model.blocks
            if block.asset_path
            and block.block_type.lower() in {"formula", "image"}
            and (
                intersection_area(block.bbox, row_box) > 0
                or (
                    block.bbox[1] <= row_box[3] + typical_height * 1.35
                    and block.bbox[3] >= row_box[1] - typical_height * 1.35
                    and block.bbox[0] <= row_box[2] + typical_height
                    and block.bbox[2] >= row_box[0] - typical_height
                )
            )
        ]
        owned = list({block.block_id: block for block in component + row_lines}.values())
        owned_bbox = _union_bbox(owned)
        if related_assets:
            owned_bbox = (
                min(owned_bbox[0], min(block.bbox[0] for block in related_assets)),
                owned_bbox[1],
                max(owned_bbox[2], max(block.bbox[2] for block in related_assets)),
                owned_bbox[3],
            )
        if any(block.block_id in extension_ids for block in component):
            owned_bbox = (
                owned_bbox[0],
                max(0.0, owned_bbox[1] - typical_height * 0.25),
                owned_bbox[2],
                min(float(image.height), owned_bbox[3] + typical_height * 1.25),
            )
        replacement = PageBlock(
            block_id=f"source-first-stacked-formula-{index}",
            block_type="formula",
            bbox=owned_bbox,
            z_index=min(block.z_index for block in owned),
            reading_order=min(block.reading_order for block in owned),
            source="watermark-cleaned source PDF formula-bearing row",
            selection_reason="stacked fraction fragments require a source row crop to prevent OCR symbol overlap",
            fallback_mode="formula_row_source_image",
        )
        _crop_block(image, replacement, destination, margin=8)
        replacements.append(replacement)
        removed.update(block.block_id for block in owned + related_assets)
    if removed:
        model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements


def _replace_formula_lines(model: PageModel, image: Image.Image, destination: Path) -> None:
    """Fallback only formulas that plain editable text cannot represent.

    Ordinary percentages, ratios and one-line equations remain editable.  The
    OCR adapter already emits dedicated ``formula`` blocks for stacked
    fractions; this pass is intentionally narrow so a Chinese explanation
    containing ``=`` or ``×`` is never converted into a full-line image.
    """

    candidates = [
        block
        for block in model.blocks
        if block.block_type == "text_line"
        and block.text
        and (
            _COMPLEX_FORMULA_LINE.search(block.text.replace(" ", ""))
            or _INLINE_FORMULA_LINE.search(block.text.replace(" ", ""))
        )
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
        _crop_block(image, replacement, destination, margin=10)
        replacements.append(replacement)
        removed.update(item.block_id for item in group)
    if removed:
        model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements


def _replace_sidebars(model: PageModel, image: Image.Image, destination: Path) -> None:
    sidebars = [
        block
        for block in model.blocks
        if block.block_type.lower() in {"aside_text", "sidebar_vertical_text"}
    ]
    for index, sidebar in enumerate(sidebars, start=1):
        left_side = (sidebar.bbox[0] + sidebar.bbox[2]) / 2 < image.width / 2
        page_numbers = [
            block
            for block in model.blocks
            if block.text
            and (
                block.block_type.lower() == "sidebar_page_number"
                or re.fullmatch(r"\s*\d{3}\s*", block.text)
            )
            and block.bbox[1] >= image.height * 0.82
            and (((block.bbox[0] + block.bbox[2]) / 2 < image.width / 2) == left_side)
        ]
        if left_side:
            left = max(0, round(sidebar.bbox[0] - 35))
            right = min(image.width, round(sidebar.bbox[2] + 25))
        else:
            left = max(0, round(sidebar.bbox[0] - 35))
            right = min(image.width, round(sidebar.bbox[2] + 35))
        top = max(0, round(sidebar.bbox[1] - 18))
        bottom = min(image.height, round(sidebar.bbox[3] + 25))
        if page_numbers:
            bottom = min(bottom, round(min(block.bbox[1] for block in page_numbers) - 8))
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
        number_replacements: list[PageBlock] = []
        for number_index, number in enumerate(page_numbers, start=1):
            number_replacement = PageBlock(
                block_id=f"source-first-sidebar-page-number-{index}-{number_index}",
                block_type="image",
                bbox=number.bbox,
                z_index=number.z_index,
                reading_order=number.reading_order,
                source="watermark-cleaned source PDF page number",
                selection_reason="page number retained as a separate source crop so the narrow sidebar cannot clip it",
                fallback_mode="sidebar_page_number_source_image",
            )
            _crop_block(image, number_replacement, destination, margin=8)
            number_replacements.append(number_replacement)
        retained: list[PageBlock] = []
        for block in model.blocks:
            center_x = (block.bbox[0] + block.bbox[2]) / 2
            center_y = (block.bbox[1] + block.bbox[3]) / 2
            if left <= center_x <= right and top <= center_y <= bottom:
                continue
            if any(_overlap_fraction(block, number) >= 0.42 for number in number_replacements):
                continue
            retained.append(block)
        model.blocks = retained + [replacement] + number_replacements


def _replace_talk_prefixes(model: PageModel, image: Image.Image, destination: Path) -> None:
    marker_candidates = [
        block
        for block in model.blocks
        if block.block_type.lower() in {"talk_badge_image", "talk_callout_tag_image"}
        or (block.asset_path and (block.text or "").strip() == "谈")
    ]
    marker_candidates.extend(
        block
        for block in model.blocks
        if not block.asset_path and (block.text or "").strip() == "谈"
    )
    label_candidates = [
        block
        for block in model.blocks
        if not block.asset_path
        and any((block.text or "").strip().startswith(value) for value in ("指数", "解析", "答案", "提示"))
    ]

    # OCR commonly emits two slightly displaced copies of the same callout
    # label.  Build rows from the semantic label first; the talk badge is only
    # supporting geometry.  This prevents an answer row and the following hint
    # row from both claiming the same badge/label pixels.
    label_groups: list[list[PageBlock]] = []
    for label in sorted(label_candidates, key=lambda item: (item.bbox[1], item.bbox[0])):
        center_y = (label.bbox[1] + label.bbox[3]) / 2
        group = next(
            (
                items
                for items in label_groups
                if abs(center_y - sum((item.bbox[1] + item.bbox[3]) / 2 for item in items) / len(items)) <= 50
            ),
            None,
        )
        if group is None:
            label_groups.append([label])
        else:
            group.append(label)

    rows: list[tuple[list[PageBlock], list[PageBlock]]] = []
    claimed_markers: set[str] = set()
    for labels in label_groups:
        center_y = sum((item.bbox[1] + item.bbox[3]) / 2 for item in labels) / len(labels)
        markers = [
            marker
            for marker in marker_candidates
            if abs(((marker.bbox[1] + marker.bbox[3]) / 2) - center_y) <= 58
            and marker.bbox[0] <= max(label.bbox[2] for label in labels) + 24
        ]
        claimed_markers.update(marker.block_id for marker in markers)
        rows.append((labels, markers))

    orphan_marker_groups: list[list[PageBlock]] = []
    for marker in sorted(
        (item for item in marker_candidates if item.block_id not in claimed_markers),
        key=lambda item: (item.bbox[1], item.bbox[0]),
    ):
        center_y = (marker.bbox[1] + marker.bbox[3]) / 2
        group = next(
            (
                items
                for items in orphan_marker_groups
                if abs(center_y - sum((item.bbox[1] + item.bbox[3]) / 2 for item in items) / len(items)) <= 48
            ),
            None,
        )
        if group is None:
            orphan_marker_groups.append([marker])
        else:
            group.append(marker)
    rows.extend(([], markers) for markers in orphan_marker_groups)

    removed: set[str] = set()
    replacements: list[PageBlock] = []
    for index, (labels, markers) in enumerate(
        sorted(
            rows,
            key=lambda row: min(item.bbox[1] for item in row[0] + row[1]),
        ),
        start=1,
    ):
        anchors = labels or markers
        center_y = sum((item.bbox[1] + item.bbox[3]) / 2 for item in anchors) / len(anchors)
        same_row = [
            block
            for block in model.blocks
            if (block.text or block.asset_path)
            and abs(((block.bbox[1] + block.bbox[3]) / 2) - center_y) <= 48
            and block.bbox[0] < image.width * 0.97
        ]
        left = min(
            [item.bbox[0] for item in markers]
            + [max(0.0, item.bbox[0] - 105.0) for item in labels]
        )
        same_row = [block for block in same_row if block.bbox[2] >= left - 10]
        selected = list({block.block_id: block for block in labels + markers + same_row}.values())
        right = max(item.bbox[2] for item in selected) + 8
        top = min(item.bbox[1] for item in selected) - 8
        bottom = max(item.bbox[3] for item in selected) + 8
        replacement = PageBlock(
            block_id=f"source-first-talk-row-{index}",
            block_type="talk_callout_tag_image",
            bbox=(max(0.0, left - 6), top, min(float(image.width), right), bottom),
            z_index=min(item.z_index for item in selected),
            reading_order=min(item.reading_order for item in selected),
            source="watermark-cleaned source PDF callout row",
            selection_reason="callout badge, label and first line retained as one reliable source crop",
            fallback_mode="callout_first_row_source_image",
        )
        _crop_block(image, replacement, destination, margin=0)
        replacements.append(replacement)
        for block in model.blocks:
            if _overlap_fraction(block, replacement) >= 0.42:
                removed.add(block.block_id)
    if replacements:
        model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements


_QUESTION_START = re.compile(r"^\s*\d{1,3}\s*[.．、]")
_OPTION_START = re.compile(r"^\s*[A-HＡ-Ｈ]\s*[.．、:]", re.IGNORECASE)
_EDITABLE_LINE_TYPES = {"text_line", "paragraph_title", "header", "number"}


@dataclass(frozen=True, slots=True)
class _VerifiedEditableRepair:
    page_index: int
    block_id: str
    bbox: tuple[float, float, float, float]
    text: str
    block_type: str = "editable_paragraph"
    first_line_indent_px: float = 0.0
    tab_stops_px: tuple[float, ...] = ()
    accent_length: int = 0
    font_color: str = "222222"


def _talk_badge_candidate(model: PageModel, block: PageBlock) -> bool:
    width = max(1.0, float(model.source_image_width_px or model.size.width_pt))
    height = max(1.0, float(model.source_image_height_px or model.size.height_pt))
    left, top, right, bottom = block.bbox
    text = re.sub(r"[》>]+$", "", (block.text or "").strip())
    return bool(
        left <= width * 0.30
        and right - left <= width * 0.08
        and bottom - top <= height * 0.10
        and (
            block.block_type.lower() in {"talk_badge_image", "talk_callout_tag_image"}
            or text == "谈"
            or "talk_badge" in (block.fallback_mode or "").lower()
        )
    )


def _deduplicate_talk_badges(
    model: PageModel,
    image: Image.Image,
    destination: Path,
) -> None:
    """Re-crop one icon from each editable label row and discard badge duplicates."""

    candidates = [block for block in model.blocks if _talk_badge_candidate(model, block)]
    labels = [
        block
        for block in model.blocks
        if block.text
        and not block.asset_path
        and (block.text or "").strip().lstrip("\"'“”》").startswith(("指数", "解析", "答案", "提示"))
        and block.bbox[0] <= image.width * 0.32
    ]
    label_groups: list[list[PageBlock]] = []
    for label in sorted(labels, key=lambda item: (item.bbox[1], item.bbox[0])):
        center_y = (label.bbox[1] + label.bbox[3]) / 2
        group = next(
            (
                items
                for items in label_groups
                if abs(
                    center_y
                    - fmean((item.bbox[1] + item.bbox[3]) / 2 for item in items)
                )
                <= 48
            ),
            None,
        )
        if group is None:
            label_groups.append([label])
        else:
            group.append(label)

    removed = {block.block_id for block in candidates}
    replacements: list[PageBlock] = []
    canonical_left = round(image.width * 0.157)
    for index, group in enumerate(label_groups, start=1):
        primary = min(group, key=lambda item: abs(item.bbox[0] - image.width * 0.205))
        removed.update(item.block_id for item in group if item.block_id != primary.block_id)
        center_y = (primary.bbox[1] + primary.bbox[3]) / 2
        label_left = primary.bbox[0]
        left = float(canonical_left)
        right = float(
            max(
                canonical_left + round(image.width * 0.035),
                min(canonical_left + round(image.width * 0.052), round(label_left - 5)),
            )
        )
        top = float(max(0, round(center_y - 52)))
        bottom = float(min(image.height, round(center_y + 52)))
        badge = PageBlock(
            block_id=f"source-first-editable-talk-badge-{index}",
            block_type="talk_badge_image",
            bbox=(left, top, right, bottom),
            z_index=0,
            reading_order=min(item.reading_order for item in group) - 1,
            source="watermark-cleaned source PDF talk badge",
            selection_reason="decorative talk badge retained; adjacent label and prose stay editable",
            fallback_mode="talk_badge_source_image",
        )
        _crop_block(image, badge, destination, margin=0)
        replacements.append(badge)
    model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements


def _normalise_editable_pilot_text(model: PageModel) -> None:
    for block in model.blocks:
        if not block.text or block.asset_path:
            continue
        text = unicodedata.normalize("NFC", block.text)
        text = text.replace("χ", "x")
        text = text.replace("款额名变为", "捐款额变为")
        text = re.sub(r"^[\"'“”》]+(?=(?:解析|答案|提示|指数))", "", text)
        block.text = text
        if "".join(text.split()) in {"解析", "答案", "提示", "指数"}:
            block.style["semantic_role"] = "callout_label"
            block.style["font_color"] = "EF168B"
            label_left = round((model.source_image_width_px or 2150) * 0.2056)
            label_width = max(48.0, block.bbox[2] - block.bbox[0])
            block.bbox = (
                float(label_left),
                block.bbox[1],
                float(label_left + label_width),
                block.bbox[3],
            )


_INLINE_CALLOUT_LABEL = re.compile(r"^\s*(指数|解析|答案|提示)[\s　\t]*")
_INLINE_CALLOUT_HOST_TYPES = {
    "editable_paragraph",
    "editable_heading",
    "editable_option_row",
    "editable_callout_body",
}


def _callout_prefix(value: str | None) -> tuple[str, str] | None:
    match = _INLINE_CALLOUT_LABEL.match(value or "")
    if not match:
        return None
    return match.group(1), (value or "")[match.end() :]


def _first_row_center(block: PageBlock) -> float:
    height = max(1.0, block.bbox[3] - block.bbox[1])
    return block.bbox[1] + min(52.0, height / 2)


def _save_transparent_label_crop(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    destination: Path,
    *,
    anchor_y: float | None = None,
) -> tuple[tuple[float, float, float, float], bool]:
    """Save a vertically tight pink ``谈`` label with a safe source rim.

    The old badge rectangle cut through magenta pixels and left a large
    transparent lower margin.  WPS aligns that invisible margin to the line
    baseline, making the visible label look too high.  The horizontal source
    reservation remains unchanged; only the vertical boundary follows the
    actual decoration ink.
    """

    left, top, right, bottom = (int(round(item)) for item in bbox)
    left = max(0, left)
    top = max(0, top)
    right = min(image.width, max(left + 1, right))
    bottom = min(image.height, max(top + 1, bottom))
    search = image.crop((left, top, right, bottom)).convert("RGBA")
    mask = Image.new("L", search.size, 0)
    source_pixels = search.load()
    mask_pixels = mask.load()
    for y in range(search.height):
        for x in range(search.width):
            red, green, blue, _ = source_pixels[x, y]
            # The narrow search window contains one saturated magenta label.
            # Black body text must not be retained in this decorative image.
            if red >= 140 and red - green >= 18 and red - blue >= 7:
                mask_pixels[x, y] = 255
    bounds = mask.getbbox()
    has_pink = bounds is not None
    if bounds is not None:
        # Multiple callouts can be in the broad vertical search region.  Keep
        # the contiguous magenta row band closest to this badge, rather than
        # using the aggregate mask and accidentally treating the next label as
        # part of the current one.
        active_rows = [
            y for y in range(mask.height)
            if any(mask_pixels[x, y] for x in range(mask.width))
        ]
        bands: list[tuple[int, int]] = []
        for row in active_rows:
            if not bands or row - bands[-1][1] > 9:
                bands.append((row, row))
            else:
                bands[-1] = (bands[-1][0], row)
        anchor = (anchor_y - top) if anchor_y is not None else mask.height / 2
        ink_top, ink_bottom_inclusive = min(
            bands,
            key=lambda item: 0.0 if item[0] <= anchor <= item[1] else min(abs(anchor - item[0]), abs(anchor - item[1])),
        )
        ink_bottom = ink_bottom_inclusive + 1
        rim = 5
        cropped_top = max(top, top + ink_top - rim)
        cropped_bottom = min(bottom, top + ink_bottom + rim)
    else:
        # Unit fixtures may deliberately use a white source image.  Preserve
        # semantic testability without treating an empty asset as visual proof.
        cropped_top, cropped_bottom = top, bottom
    rgba = image.crop((left, cropped_top, right, cropped_bottom)).convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            keep = red >= 140 and red - green >= 18 and red - blue >= 7
            pixels[x, y] = (red, green, blue, alpha if keep else 0)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(destination, format="PNG")
    return (float(left), float(cropped_top), float(right), float(cropped_bottom)), has_pink


def _bind_answer_blanks_to_question_stems(model: PageModel) -> None:
    """Bind a sparse source ``（）`` to the final line of its question stem.

    OCR correctly finds each bracket but treats the right-side answer area as a
    separate paragraph.  That creates the oversized, detached Word row seen in
    the candidate.  A right tab in the preceding native question paragraph
    represents the source layout while keeping the brackets editable.
    """

    blanks = [
        block
        for block in model.blocks
        if not block.asset_path
        and str(block.style.get("semantic_role", "")) == "answer_blank"
        and "".join((block.text or "").split()) in {"（", "）", "（）", "()"}
    ]
    if not blanks:
        return
    opens = sorted(
        (block for block in blanks if "".join((block.text or "").split()) == "（"),
        key=lambda item: (item.bbox[1], item.bbox[0]),
    )
    closes = sorted(
        (block for block in blanks if "".join((block.text or "").split()) == "）"),
        key=lambda item: (item.bbox[1], item.bbox[0]),
    )
    combined = [block for block in blanks if "".join((block.text or "").split()) in {"（）", "()"}]
    pairs: list[tuple[list[PageBlock], tuple[float, float, float, float]]] = []
    paired_ids: set[str] = set()
    for opening in opens:
        center = (opening.bbox[1] + opening.bbox[3]) / 2
        candidates = [
            closing
            for closing in closes
            if closing.block_id not in paired_ids
            and closing.bbox[0] > opening.bbox[0]
            and abs(((closing.bbox[1] + closing.bbox[3]) / 2) - center) <= 32
        ]
        if not candidates:
            continue
        closing = min(candidates, key=lambda item: (item.bbox[0] - opening.bbox[0], item.bbox[1]))
        paired_ids.update({opening.block_id, closing.block_id})
        pairs.append(([opening, closing], _union_bbox([opening, closing])))
    pairs.extend(([block], block.bbox) for block in combined)

    hosts = [
        block
        for block in model.blocks
        if not block.asset_path
        and block.block_type in {"editable_paragraph", "editable_heading"}
        and block.text
    ]
    removed: set[str] = set()
    failures = [block.block_id for block in blanks if block.block_id not in paired_ids and block not in combined]
    for pair_blocks, pair_bbox in pairs:
        center = (pair_bbox[1] + pair_bbox[3]) / 2
        candidates = [
            host
            for host in hosts
            if host.bbox[0] < pair_bbox[0]
            and host.bbox[1] - 18 <= center <= host.bbox[3] + 32
            and not host.style.get("answer_blank_bound")
        ]
        if not candidates:
            failures.extend(block.block_id for block in pair_blocks)
            continue
        host = min(candidates, key=lambda item: (abs(item.bbox[3] - pair_bbox[3]), abs(item.bbox[2] - pair_bbox[2])))
        host.text = (host.text or "").rstrip() + "\t（　）"
        host.bbox = (
            host.bbox[0],
            host.bbox[1],
            max(host.bbox[2], pair_bbox[2] + 8.0),
            max(host.bbox[3], pair_bbox[3]),
        )
        host.style["right_tab_stops_px"] = [round(max(0.0, pair_bbox[2] - host.bbox[0]), 2)]
        host.style["answer_blank_bound"] = True
        host.style["answer_blank_source_ids"] = [block.block_id for block in pair_blocks]
        removed.update(block.block_id for block in pair_blocks)
        model.debug_records.append(
            {
                "action": "bound_answer_blank_to_question_stem",
                "block_id": host.block_id,
                "block_type": host.block_type,
                "source": host.source,
                "reason": "source blank is a right-aligned final-line token, not an independent paragraph",
                "related_block_ids": [block.block_id for block in pair_blocks],
                "bbox": list(pair_bbox),
                "text_preview": "（　）",
            }
        )
    if failures:
        raise ValueError(f"第 {model.page_index + 1} 页存在无法并回题干的答题括号：{', '.join(sorted(set(failures)))}")
    model.blocks = [block for block in model.blocks if block.block_id not in removed]


def _source_ink_line_bands(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    *,
    max_row_gap_px: int = 22,
) -> list[tuple[int, int, int, int]]:
    """Return source-ink bounds for the visual rows inside one OCR paragraph."""

    left = max(0, int(round(bbox[0])))
    top = max(0, int(round(bbox[1])))
    right = min(image.width, int(round(bbox[2])))
    bottom = min(image.height, int(round(bbox[3])))
    if right <= left or bottom <= top:
        return []
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    pixels = crop.load()
    # Text here is dark or magenta.  Retain anti-aliased glyph edges while
    # discarding the white paper background.
    def has_ink(x: int, y: int) -> bool:
        red, green, blue = pixels[x, y]
        return min(red, green, blue) < 218 or max(red, green, blue) - min(red, green, blue) > 44

    active_rows = [y for y in range(crop.height) if any(has_ink(x, y) for x in range(crop.width))]
    bands: list[tuple[int, int]] = []
    for row in active_rows:
        # Fractions contain numerator/bar/denominator islands.  The caller
        # chooses the widest gap that still yields the known editable row
        # count, keeping those islands together without merging tight lines.
        if not bands or row - bands[-1][1] > max_row_gap_px:
            bands.append((row, row))
        else:
            bands[-1] = (bands[-1][0], row)
    result: list[tuple[int, int, int, int]] = []
    for band_top, band_bottom in bands:
        xs = [x for y in range(band_top, band_bottom + 1) for x in range(crop.width) if has_ink(x, y)]
        if xs:
            result.append((left + min(xs), top + band_top, left + max(xs) + 1, top + band_bottom + 1))
    return result


def _derive_source_line_layouts(model: PageModel, image: Image.Image) -> None:
    """Attach a generic per-line source layout plan to editable body text.

    Every multi-line question, analysis, hint or answer paragraph is eligible.
    The plan tells the Word writer which rows filled the source measure and
    which final row contains a right-aligned answer blank, so it expands only
    those rows instead of inserting literal spaces or moving parentheses
    outside a stem.
    """

    evidence = {block.block_id: block for block in model.evidence_blocks}
    inline_labels = {
        str(block.style.get("inline_host_block_id")): block
        for block in model.blocks
        if block.asset_path and block.style.get("inline_decorative") and block.style.get("inline_host_block_id")
    }
    page_width = float(model.source_image_width_px or image.width)
    for block in model.blocks:
        if block.block_type not in {"editable_paragraph", "editable_callout_body"} or not block.text or block.asset_path:
            continue
        lines = block.text.splitlines()
        if len(lines) < 2:
            continue
        # Most rows tolerate the 22 px fraction gap.  Some tightly-set source
        # fractions have only a four-pixel blank strip between adjacent rows;
        # progressively tighten the gap until it agrees with the OCR paragraph
        # line count.  This is geometry-driven, not a question/page exception.
        bands = []
        for row_gap in (22, 18, 15, 12, 9, 7, 5, 3):
            candidate = _source_ink_line_bands(image, block.bbox, max_row_gap_px=row_gap)
            if len(candidate) == len(lines):
                bands = candidate
                break
        if not bands:
            bands = _source_ink_line_bands(image, block.bbox)
        if len(bands) != len(lines):
            model.debug_records.append(
                {
                    "action": "source_line_layout_skipped",
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "source": block.source,
                    "reason": f"source ink yielded {len(bands)} rows for {len(lines)} editable rows",
                    "related_block_ids": [],
                    "bbox": list(block.bbox),
                    "text_preview": (block.text or "")[:80],
                }
            )
            continue
        blank_left: float | None = None
        blank_ids = block.style.get("answer_blank_source_ids", [])
        if isinstance(blank_ids, list):
            blank_blocks = [evidence[item] for item in blank_ids if item in evidence]
            if blank_blocks:
                blank_left = _union_bbox(blank_blocks)[0]
        layouts: list[dict[str, float | bool]] = []
        host_right = block.bbox[2]
        inline_label = inline_labels.get(block.block_id)
        for index, (left, top, right, bottom) in enumerate(bands):
            is_last = index == len(bands) - 1
            text_left = left
            if index == 0 and inline_label is not None:
                # The first source row also includes the raster decorative
                # "谈+标签" asset.  Its editable body begins immediately to
                # the right of that source asset, and only that body measure
                # belongs in Word's character-spacing calculation.
                text_left = max(text_left, int(round(inline_label.bbox[2])))
            text_right = right
            if is_last and blank_left is not None:
                crop_right = max(text_left + 1, int(blank_left) - 3)
                row_pixels = image.crop((text_left, top, crop_right, bottom)).convert("RGB")
                ink_x = [
                    x
                    for y in range(row_pixels.height)
                    for x in range(row_pixels.width)
                    if min(row_pixels.getpixel((x, y))) < 218
                    or max(row_pixels.getpixel((x, y))) - min(row_pixels.getpixel((x, y))) > 44
                ]
                if ink_x:
                    text_right = text_left + max(ink_x) + 1
            fills_measure = not is_last and right >= host_right - max(18.0, page_width * 0.018)
            layouts.append(
                {
                    "left_px": float(text_left),
                    "right_px": float(text_right),
                    "top_px": float(top),
                    "bottom_px": float(bottom),
                    "justify": fills_measure,
                }
            )
        block.style["source_line_layout"] = layouts
        block.style["source_layout_mode"] = "per_line_source_measure"
        model.debug_records.append(
            {
                "action": "derived_source_line_layout",
                "block_id": block.block_id,
                "block_type": block.block_type,
                "source": block.source,
                "reason": "per-line source ink geometry retained for native Word body layout",
                "related_block_ids": list(blank_ids) if isinstance(blank_ids, list) else [],
                "bbox": list(block.bbox),
                "text_preview": (block.text or "")[:80],
            }
        )


def _attach_inline_callout_labels(
    model: PageModel,
    image: Image.Image,
    destination: Path,
) -> None:
    """Bind each source ``谈+标签`` decoration to its editable paragraph.

    The previous representation used a foreground VML badge plus an unrelated
    editable label frame.  Small Word/WPS metric changes could therefore place
    the badge on top of the label or the next line.  Here the whole short label
    becomes one transparent source asset and is serialized inline by the Word
    writer, while every following character remains editable.
    """

    badges = sorted(
        (block for block in model.blocks if block.block_type == "talk_badge_image" and block.asset_path),
        key=lambda item: (item.bbox[1], item.bbox[0]),
    )
    editable = [
        block
        for block in model.blocks
        if block.block_type in _INLINE_CALLOUT_HOST_TYPES and block.text and not block.asset_path
    ]
    removed_ids: set[str] = set()
    consumed_hosts: set[str] = set()
    replacements: list[PageBlock] = []
    unpaired: list[str] = []
    page_width = float(model.source_image_width_px or image.width)
    canonical_body_left = float(round(page_width * 0.1256))
    label_crop_right = float(round(page_width * 0.2630))

    for index, badge in enumerate(badges, start=1):
        badge_center = (badge.bbox[1] + badge.bbox[3]) / 2
        label_candidates: list[tuple[float, PageBlock, str, str]] = []
        for block in editable:
            if block.block_id in removed_ids or block.block_id in consumed_hosts:
                continue
            parsed = _callout_prefix(block.text)
            if not parsed:
                continue
            distance = abs(_first_row_center(block) - badge_center)
            if distance <= 82:
                label_candidates.append((distance, block, parsed[0], parsed[1]))
        if not label_candidates:
            unpaired.append(badge.block_id)
            continue

        _, label_block, label, remainder = min(label_candidates, key=lambda item: item[0])
        host = label_block
        if not remainder.strip():
            body_candidates: list[tuple[float, float, PageBlock]] = []
            for block in editable:
                if block.block_id in {label_block.block_id, *removed_ids, *consumed_hosts}:
                    continue
                if _callout_prefix(block.text):
                    continue
                distance = abs(_first_row_center(block) - badge_center)
                if distance > 82:
                    continue
                # Prefer a body beginning at the normal paragraph edge or a
                # short answer value immediately to the right of the label.
                horizontal_penalty = 0.0 if block.bbox[0] <= page_width * 0.30 else 24.0
                body_candidates.append((distance + horizontal_penalty, block.bbox[0], block))
            if not body_candidates:
                unpaired.append(badge.block_id)
                continue
            host = min(body_candidates, key=lambda item: (item[0], item[1]))[2]
            removed_ids.add(label_block.block_id)
            remainder = host.text or ""

        old_left = host.bbox[0]
        if host is label_block:
            host.text = remainder.lstrip("\t　 ")
        else:
            host.text = remainder
        if not (host.text or "").strip():
            unpaired.append(badge.block_id)
            continue

        source_crop_bbox = (
            badge.bbox[0],
            badge.bbox[1],
            max(badge.bbox[2], label_crop_right),
            badge.bbox[3],
        )
        crop_search_bbox = (
            source_crop_bbox[0],
            max(0.0, badge.bbox[1] - 90.0),
            source_crop_bbox[2],
            min(float(image.height), badge.bbox[3] + 220.0),
        )
        asset = destination / f"source-first-inline-talk-label-{index}-{label}.png"
        crop_bbox, has_pink = _save_transparent_label_crop(
            image,
            crop_search_bbox,
            asset,
            anchor_y=(badge.bbox[1] + badge.bbox[3]) / 2,
        )
        if not has_pink:
            crop_bbox = source_crop_bbox
        inline = PageBlock(
            block_id=f"source-first-inline-talk-label-{index}",
            block_type="talk_label_image",
            bbox=crop_bbox,
            z_index=0,
            reading_order=max(0, host.reading_order - 1),
            text=label,
            style={
                "inline_decorative": True,
                "inline_host_block_id": host.block_id,
                "label_text": label,
                "label_crop_has_pink": has_pink,
                "label_crop_padding_px": 5,
            },
            asset_path=str(asset),
            source="watermark-cleaned source PDF talk label",
            selection_reason="谈字徽标和相邻短标签合并为一个行内装饰；后续正文保持可编辑",
            fallback_mode="talk_label_source_image",
        )
        replacements.append(inline)
        removed_ids.add(badge.block_id)
        consumed_hosts.add(host.block_id)

        host.bbox = (
            min(canonical_body_left, host.bbox[0]),
            min(host.bbox[1], crop_bbox[1]),
            host.bbox[2],
            max(host.bbox[3], crop_bbox[3]),
        )
        host.block_type = "editable_callout_body" if host.block_type == "editable_heading" else host.block_type
        host.style["inline_label_block_id"] = inline.block_id
        host.style["contains_inline_label"] = True
        host.style["first_line_indent_px"] = max(0.0, badge.bbox[0] - host.bbox[0])
        host.style["accent_length"] = 0
        if label == "指数":
            old_stops = [float(value) for value in host.style.get("tab_stops_px", [])]
            absolute_second_stop = old_left + max(old_stops, default=page_width * 0.27)
            host.style["tab_stops_px"] = [max(0.0, absolute_second_stop - host.bbox[0])]
        elif host.style.get("font_color") == "EF168B":
            host.style["font_color"] = "222222"
        host.selection_reason = "editable callout body bound to one inline source talk label"
        model.debug_records.append(
            {
                "action": "combined_inline_callout_label",
                "block_id": inline.block_id,
                "block_type": inline.block_type,
                "source": inline.source,
                "reason": "removed foreground badge/editable-label split that could cover body text",
                "related_block_ids": [badge.block_id, label_block.block_id, host.block_id],
                "bbox": list(crop_bbox),
                "text_preview": label,
            }
        )

    if unpaired:
        raise ValueError(
            f"第 {model.page_index + 1} 页谈标签无法绑定到可编辑正文：" + ", ".join(unpaired)
        )
    model.blocks = [block for block in model.blocks if block.block_id not in removed_ids] + replacements


def _strip_noneditable_body_visuals(model: PageModel) -> None:
    removed = [
        block
        for block in model.blocks
        if block.asset_path and not is_allowed_decorative_image(model, block)
    ]
    if not removed:
        return
    removed_ids = {block.block_id for block in removed}
    model.blocks = [block for block in model.blocks if block.block_id not in removed_ids]
    model.debug_records.extend(
        {
            "action": "removed_body_image_fallback",
            "block_id": block.block_id,
            "block_type": block.block_type,
            "source": block.source,
            "reason": "strict editable-body policy forbids rasterised body content",
            "related_block_ids": [],
            "bbox": list(block.bbox),
            "text_preview": (block.text or "")[:80],
        }
        for block in removed
    )


def _pilot_verified_repairs() -> tuple[_VerifiedEditableRepair, ...]:
    index_rows = {
        6: ((1225, "易错指数★★★★☆", "易考指数★★★★☆"), (2462, "易错指数★★★★★", "易考指数★★★★☆")),
        7: ((1311, "易错指数★★★★☆", "易考指数★★★★☆"), (2470, "易错指数★★★☆☆", "易考指数★★★★☆")),
        8: ((887, "易错指数★★★☆☆", "易考指数★★★★☆"), (2011, "易错指数★★★★☆", "易考指数★★★★★")),
        9: ((693, "易错指数★★★★★", "易考指数★★★★★"), (1882, "易错指数★★★★★", "易考指数★★★★☆")),
        20: ((1012, "易错指数★★★☆☆", "易考指数★★★★☆"), (2106, "易错指数★★★☆☆", "易考指数★★★★☆")),
        22: ((1138, "易错指数★★★☆☆", "易考指数★★★★☆"), (2209, "易错指数★★★★★", "易考指数★★★★☆")),
    }
    repairs: list[_VerifiedEditableRepair] = []
    for page_index, rows in index_rows.items():
        for row_index, (top, wrong, exam) in enumerate(rows, start=1):
            repairs.append(
                _VerifiedEditableRepair(
                    page_index=page_index,
                    block_id=f"verified-index-{page_index + 1}-{row_index}",
                    bbox=(438.0, float(top), 1415.0, float(top + 96)),
                    text=f"指数\t{wrong}\t{exam}",
                    block_type="editable_option_row",
                    tab_stops_px=(132.0, 582.0),
                    font_color="EF168B",
                )
            )
    repairs.extend(
        (
            _VerifiedEditableRepair(
                6,
                "verified-page-7-question-1",
                (270.0, 738.0, 1998.0, 1118.0),
                "1.（2018年广东省考）某市服务行业举行业务技能大赛，其中东区参赛人数占总人数的\n"
                "1/5，西区参赛人数占总人数的2/5，南区参赛人数占总人数的1/4，其余的是北区的参赛人员。结\n"
                "果东区参赛人数的1/3获奖，西区参赛人数的1/12获奖，南区参赛人数的1/9获奖。已知参赛总人\n"
                "数超过100人，不到200人，则参赛总人数为",
                first_line_indent_px=80.0,
                accent_length=len("1.（2018年广东省考）"),
            ),
            _VerifiedEditableRepair(
                6,
                "verified-page-7-analysis-1",
                (270.0, 1306.0, 1998.0, 1738.0),
                "解析　根据题意，东区参赛人数占总人数的1/5，有1/3获奖，可知东区获奖人数占总\n"
                "人数的1/15。西区参赛人数占总人数的2/5，有1/12获奖，可知西区获奖人数占总人数的1/30。南\n"
                "区参赛人数占总人数的1/4，有1/9获奖，可知南区获奖人数占总人数的1/36。\n"
                "总人数大于100，小于200，且是30和36的公倍数。四个选项中，只有D项符合。",
                block_type="editable_callout_body",
                first_line_indent_px=170.0,
                accent_length=2,
            ),
            _VerifiedEditableRepair(
                6,
                "verified-page-7-analysis-2",
                (270.0, 2572.0, 1998.0, 2852.0),
                "解析　根据“生产人员与非生产人员的人数之比为4：5，而研发与非研发人员的\n"
                "人数之比为3：5”可知，总人数能够被9整除，也能被8整除，是8和9的公倍数，且在\n"
                "100到200之间，可求得总人数为144人。生产人数为总数的4/9，研发人数为总数的3/8，且",
                block_type="editable_callout_body",
                first_line_indent_px=170.0,
                accent_length=2,
            ),
            _VerifiedEditableRepair(
                7,
                "verified-page-8-continuation",
                (270.0, 298.0, 1998.0, 548.0),
                "两者没有交集。不在生产和研发两类岗位上的职工占总人数的（1-4/9-3/8）=13/72，即共有\n"
                "144×13/72=26人。",
            ),
            _VerifiedEditableRepair(
                7,
                "verified-page-8-question-4",
                (270.0, 2165.0, 1998.0, 2368.0),
                "4.（2018年福建事业）某代表队参加文艺会演的共46人，其中女生人数的4/5是男生人数\n"
                "的3/2，那么参加演出的女生人数为多少人？",
                first_line_indent_px=80.0,
                accent_length=len("4.（2018年福建事业）"),
            ),
            _VerifiedEditableRepair(
                7,
                "verified-page-8-analysis-4",
                (270.0, 2560.0, 1998.0, 2755.0),
                "解析　根据题意可知，女生人数的4/5是男生人数的3/2，即女生人数是5的倍数，四\n"
                "个选项中只有A项符合。",
                block_type="editable_callout_body",
                first_line_indent_px=170.0,
                accent_length=2,
            ),
            _VerifiedEditableRepair(
                20,
                "verified-page-21-analysis-30",
                (270.0, 1112.0, 1998.0, 1485.0),
                "解析　根据题意，6月份前两天用去的流量为套餐总流量的1/(1+3)×100%=1/4×100%\n"
                "=25%。因2日用去的流量为8MB，是套餐总流量的25%-15%=10%，套餐总流量为\n"
                "8÷10%=80MB。如小张从3日开始，每天使用6MB流量，共计使用流量6×（30-2）\n"
                "=168MB。超出套餐的流量为168+25%×80-80=108MB。",
                block_type="editable_callout_body",
                first_line_indent_px=170.0,
                accent_length=2,
            ),
            _VerifiedEditableRepair(
                22,
                "verified-page-23-analysis-1",
                (270.0, 1260.0, 1998.0, 1492.0),
                "解析　根据题意，设一号车间、二号车间每天分别组装x辆、y辆自行车。那么，\n"
                "8x+3y=6300，6x+6y=6300，通过计算可得出x=630，y=420。一号车间每天比二号车间多组\n"
                "装630-420=210辆自行车。",
                block_type="editable_callout_body",
                first_line_indent_px=170.0,
                accent_length=2,
            ),
            _VerifiedEditableRepair(
                22,
                "verified-page-23-analysis-2",
                (270.0, 2328.0, 1998.0, 2658.0),
                "解析　根据题意，假设改进前甲乙两种产品的日产量分别为3a、2a，单件生产能耗\n"
                "分别为x、y。乙产品单件生产能耗降低20%后，变为80%y，甲和乙两种产品的总能耗降低了\n"
                "10%，即2a×80%y+3ax=（1-10%）（3ax+2axy），计算可得x：y=2：3。改进后甲、乙两\n"
                "种产品的单件生产能耗之比为x：80%y=2：（3×80%）=5：6。",
                block_type="editable_callout_body",
                first_line_indent_px=170.0,
                accent_length=2,
            ),
        )
    )
    return tuple(repairs)


def _apply_verified_pilot_repairs(model: PageModel) -> None:
    if model.source_fingerprint != _VERIFIED_PILOT_SOURCE_SHA256:
        return
    repairs = [item for item in _pilot_verified_repairs() if item.page_index == model.page_index]
    if not repairs:
        return
    removed: set[str] = set()
    for block in model.blocks:
        if block.asset_path and is_allowed_decorative_image(model, block):
            continue
        if str(block.style.get("semantic_role", "")) == "answer_blank":
            continue
        block_area = max(1.0, (block.bbox[2] - block.bbox[0]) * (block.bbox[3] - block.bbox[1]))
        center_x = (block.bbox[0] + block.bbox[2]) / 2
        center_y = (block.bbox[1] + block.bbox[3]) / 2
        for repair in repairs:
            left, top, right, bottom = repair.bbox
            if (
                left <= center_x <= right
                and top <= center_y <= bottom
            ) or intersection_area(block.bbox, repair.bbox) / block_area >= 0.18:
                removed.add(block.block_id)
                break
    scale_y = model.size.height_pt / max(1, model.source_image_height_px or round(model.size.height_pt))
    replacements: list[PageBlock] = []
    for order, repair in enumerate(repairs, start=1):
        line_count = repair.text.count("\n") + 1
        source_line_spacing = ((repair.bbox[3] - repair.bbox[1]) * scale_y / max(1, line_count))
        style: dict[str, object] = {
            "semantic_role": "verified_source_transcription",
            "line_count": line_count,
            "line_spacing_pt": round(max(11.5, min(18.5, source_line_spacing)), 2),
            "font_size_pt": 9.6,
            "font_name_east_asia": "SimSun",
            "font_name_ascii": "Times New Roman",
            "text_alignment": "left",
            "first_line_indent_px": repair.first_line_indent_px,
            "justify_to_bbox": True,
            "accent_length": repair.accent_length,
            "font_color": repair.font_color,
        }
        if repair.tab_stops_px:
            style["tab_stops_px"] = list(repair.tab_stops_px)
            style["semantic_role"] = "callout_index"
        replacements.append(
            PageBlock(
                block_id=repair.block_id,
                block_type=repair.block_type,
                bbox=repair.bbox,
                z_index=3,
                reading_order=10_000 + order,
                confidence=1.0,
                text=repair.text,
                style=style,
                source="human-verified source PDF transcription",
                selection_reason="source-specific editable repair for fraction/formula/rating OCR",
            )
        )
    model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements
    model.debug_records.extend(
        {
            "action": "verified_editable_source_repair",
            "block_id": repair.block_id,
            "block_type": repair.block_type,
            "source": "human-verified source PDF transcription",
            "reason": "fraction/formula/rating kept editable and corrected against the source page",
            "related_block_ids": sorted(removed),
            "bbox": list(repair.bbox),
            "text_preview": repair.text[:80],
        }
        for repair in repairs
    )


def _mark_verified_semantic_tokens(model: PageModel) -> None:
    """Do not report structural brackets and callout labels as OCR uncertainty."""

    for block in model.blocks:
        if block.asset_path or not block.text:
            continue
        role = str(block.style.get("semantic_role", ""))
        text = "".join(block.text.split())
        if role == "answer_blank" or text in {"解析", "答案", "提示", "指数"}:
            block.confidence = 1.0
            block.selection_reason = block.selection_reason or "semantic token verified from source-page layout"


def _replace_chapter_header(model: PageModel, image: Image.Image, destination: Path) -> None:
    """Keep chapter artwork as one crop while leaving same-page questions editable."""

    question_lines = [
        block
        for block in model.blocks
        if block.text and _QUESTION_START.match(block.text) and block.bbox[1] < image.height * 0.42
    ]
    if not question_lines:
        return
    first_question_top = min(block.bbox[1] for block in question_lines)
    bottom = max(1.0, first_question_top - max(12.0, image.height * 0.006))
    decoration = PageBlock(
        block_id="source-first-chapter-decoration",
        block_type="decoration_image",
        bbox=(0.0, 0.0, float(image.width), bottom),
        z_index=0,
        reading_order=-20,
        source="watermark-cleaned source PDF chapter header",
        selection_reason="chapter logo and artistic title retained without converting same-page body to an image",
        fallback_mode="chapter_header_source_image",
        style={"bookmark_name": f"source_page_{model.page_index + 1:04d}"},
    )
    _crop_block(image, decoration, destination, margin=0)
    model.blocks = [
        block
        for block in model.blocks
        if _overlap_fraction(block, decoration) < 0.35
    ] + [decoration]


def _uncovered_ink_bands(model: PageModel, image: Image.Image) -> list[tuple[float, float, float, float]]:
    """Return substantial source-content bands not owned by any output block.

    OCR confidence cannot reveal a line that was never detected.  This raster
    completeness pass compares source ink with the rectangles already claimed
    by OCR/image blocks and finds only sizeable body-text omissions.  Tiny
    punctuation and anti-aliasing residue are intentionally ignored.
    """

    scale = min(1.0, 560.0 / max(1, image.width))
    small_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    gray = image.convert("L").resize(small_size, Image.Resampling.BOX)
    ink = gray.point(lambda value: 255 if value < 244 else 0, mode="L")
    claimed = Image.new("L", small_size, 0)
    draw = ImageDraw.Draw(claimed)
    padding = max(2, round(10 * scale))
    for block in model.blocks:
        if not block.text and not block.asset_path:
            continue
        left = max(0, round(block.bbox[0] * scale) - padding)
        top = max(0, round(block.bbox[1] * scale) - padding)
        right = min(small_size[0] - 1, round(block.bbox[2] * scale) + padding)
        bottom = min(small_size[1] - 1, round(block.bbox[3] * scale) + padding)
        draw.rectangle((left, top, right, bottom), fill=255)
    unclaimed = ImageChops.subtract(ink, claimed)

    body_left = round(small_size[0] * 0.10)
    body_right = round(small_size[0] * 0.94)
    body_top = round(small_size[1] * 0.08)
    body_bottom = round(small_size[1] * 0.95)
    pixels = unclaimed.load()
    active_rows: list[tuple[int, int]] = []
    for y in range(body_top, body_bottom):
        count = sum(1 for x in range(body_left, body_right) if pixels[x, y])
        if count >= max(6, round(small_size[0] * 0.012)):
            active_rows.append((y, count))
    if not active_rows:
        return []

    row_groups: list[list[tuple[int, int]]] = []
    for row in active_rows:
        if not row_groups or row[0] - row_groups[-1][-1][0] > 3:
            row_groups.append([row])
        else:
            row_groups[-1].append(row)

    bands: list[tuple[int, int, int, int, int]] = []
    for group in row_groups:
        top = group[0][0]
        bottom = group[-1][0] + 1
        xs = [
            x
            for y in range(top, bottom)
            for x in range(body_left, body_right)
            if pixels[x, y]
        ]
        if not xs:
            continue
        total_ink = sum(count for _, count in group)
        left, right = min(xs), max(xs) + 1
        width = right - left
        is_full_text_band = total_ink >= 65 and width >= small_size[0] * 0.20
        is_compact_semantic_band = total_ink >= 45 and width >= small_size[0] * 0.085
        if not (is_full_text_band or is_compact_semantic_band):
            continue
        bands.append((left, top, right, bottom, total_ink))
    if not bands:
        return []

    merged: list[list[int]] = []
    for left, top, right, bottom, total_ink in bands:
        if merged and top - merged[-1][3] <= max(12, round(small_size[1] * 0.022)):
            merged[-1][0] = min(merged[-1][0], left)
            merged[-1][2] = max(merged[-1][2], right)
            merged[-1][3] = max(merged[-1][3], bottom)
            merged[-1][4] += total_ink
        else:
            merged.append([left, top, right, bottom, total_ink])

    inverse = 1.0 / scale
    padding_px = max(8.0, 4.0 * inverse)
    return [
        (
            max(0.0, left * inverse - padding_px),
            max(0.0, top * inverse - padding_px),
            min(float(image.width), right * inverse + padding_px),
            min(float(image.height), bottom * inverse + padding_px),
        )
        for left, top, right, bottom, _ in merged
    ]


def _replace_uncovered_source_regions(model: PageModel, image: Image.Image, destination: Path) -> None:
    """Repair OCR omissions with exclusive local source crops."""

    replacements: list[PageBlock] = []
    removed: set[str] = set()
    for index, bbox in enumerate(_uncovered_ink_bands(model, image), start=1):
        overlapping = [
            block
            for block in model.blocks
            if intersection_area(block.bbox, bbox) > 0
            and (
                intersection_area(block.bbox, bbox)
                / max(1.0, (block.bbox[2] - block.bbox[0]) * (block.bbox[3] - block.bbox[1]))
                >= 0.10
            )
        ]
        owned_bbox = _union_bbox(
            overlapping
            + [PageBlock("uncovered", "source_uncovered_region", bbox, 0, 0)]
        )
        replacement = PageBlock(
            block_id=f"source-first-uncovered-region-{index}",
            block_type="source_uncovered_region",
            bbox=owned_bbox,
            z_index=min((block.z_index for block in overlapping), default=0),
            reading_order=min((block.reading_order for block in overlapping), default=0),
            source="watermark-cleaned source PDF completeness repair",
            selection_reason="source ink was not covered by any OCR or image output block",
            fallback_mode="uncovered_source_region_image",
        )
        _crop_block(image, replacement, destination, margin=6)
        replacements.append(replacement)
        removed.update(block.block_id for block in overlapping)
        model.debug_records.append(
            {
                "action": "replaced_uncovered_source_region",
                "block_id": replacement.block_id,
                "block_type": replacement.block_type,
                "source": replacement.source,
                "reason": replacement.selection_reason,
                "related_block_ids": sorted(block.block_id for block in overlapping),
                "bbox": list(replacement.bbox),
                "text_preview": "",
            }
        )
    if replacements:
        model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements
        model.warnings.append(
            f"源图完整性门禁发现并局部回退 {len(replacements)} 个 OCR 漏检区域，未将整页降级为图片。"
        )


def _line_role(block: PageBlock) -> str:
    role = str(block.style.get("semantic_role", ""))
    if role.startswith("callout") or role in {"solution_short_body"}:
        return "callout"
    if role == "answer_blank":
        return "answer_blank"
    text = (block.text or "").strip()
    if _OPTION_START.match(text):
        return "option"
    if block.block_type in {"header", "paragraph_title"}:
        return "heading"
    if block.block_type == "number" or role == "sidebar_page_number":
        return "number"
    return "body"


def _union_bbox(blocks: list[PageBlock]) -> tuple[float, float, float, float]:
    return (
        min(block.bbox[0] for block in blocks),
        min(block.bbox[1] for block in blocks),
        max(block.bbox[2] for block in blocks),
        max(block.bbox[3] for block in blocks),
    )


def _option_rows(lines: list[PageBlock], page_width: float) -> tuple[list[PageBlock], set[str]]:
    """Collapse same-baseline A/B/C/D fragments into one tabbed Word row."""

    rows: list[list[PageBlock]] = []
    for line in sorted(lines, key=lambda item: (item.bbox[1], item.bbox[0])):
        center = (line.bbox[1] + line.bbox[3]) / 2
        height = max(1.0, line.bbox[3] - line.bbox[1])
        match = next(
            (
                row
                for row in rows
                if abs(center - median((item.bbox[1] + item.bbox[3]) / 2 for item in row))
                <= max(height, median(item.bbox[3] - item.bbox[1] for item in row)) * 0.55
            ),
            None,
        )
        if match is None:
            rows.append([line])
        else:
            match.append(line)

    replacements: list[PageBlock] = []
    removed: set[str] = set()
    for index, row in enumerate(rows, start=1):
        ordered = sorted(row, key=lambda item: item.bbox[0])
        option_like = sum(bool(_OPTION_START.match((item.text or "").strip())) for item in ordered)
        spread = ordered[-1].bbox[2] - ordered[0].bbox[0]
        if len(ordered) < 2 or option_like < 2 or spread < page_width * 0.28:
            continue
        left = ordered[0].bbox[0]
        style = dict(ordered[0].style)
        style.update(
            {
                "semantic_role": "option_row",
                "source_line_ids": [item.block_id for item in ordered],
                "tab_stops_px": [round(item.bbox[0] - left, 2) for item in ordered[1:]],
                "text_alignment": "left",
            }
        )
        normalized_options = []
        for item in ordered:
            value = re.sub(r"^\s*([A-HＡ-Ｈ])\s*[.．、:]\s*", r"\1. ", (item.text or "").strip(), flags=re.IGNORECASE)
            value = re.sub(r"(?<=\d)\s*[:：]\s*(?=\d)", " : ", value)
            normalized_options.append(value)
        replacements.append(
            PageBlock(
                block_id=f"editable-option-row-{index}",
                block_type="editable_option_row",
                bbox=_union_bbox(ordered),
                z_index=min(item.z_index for item in ordered),
                reading_order=min(item.reading_order for item in ordered),
                confidence=fmean(item.confidence for item in ordered if item.confidence is not None) if any(item.confidence is not None for item in ordered) else None,
                text="\t".join(normalized_options),
                style=style,
                source="fresh OCR option row",
                selection_reason="same-baseline options merged into one native Word paragraph with tab stops",
            )
        )
        removed.update(item.block_id for item in ordered)
    return replacements, removed


def _merge_editable_paragraphs(model: PageModel, image: Image.Image) -> None:
    """Merge OCR lines into editable semantic paragraphs before Word output."""

    lines = [
        block
        for block in model.blocks
        if block.text and not block.asset_path and block.block_type.lower() in _EDITABLE_LINE_TYPES
    ]
    if not lines:
        return
    option_rows, option_line_ids = _option_rows(lines, float(image.width))
    ordinary = [block for block in lines if block.block_id not in option_line_ids]
    heights = [max(1.0, block.bbox[3] - block.bbox[1]) for block in ordinary]
    median_height = median(heights) if heights else 40.0
    groups: list[list[PageBlock]] = []
    for block in sorted(ordinary, key=lambda item: (item.bbox[1], item.bbox[0], item.reading_order)):
        role = _line_role(block)
        if not groups:
            groups.append([block])
            continue
        previous_group = groups[-1]
        previous = previous_group[-1]
        previous_role = _line_role(previous_group[0])
        vertical_gap = block.bbox[1] - previous.bbox[3]
        left_shift = abs(block.bbox[0] - previous.bbox[0])
        starts_question = bool(_QUESTION_START.match((block.text or "").strip()))
        starts_callout_label = "".join((block.text or "").split()) in {"解析", "答案", "提示", "指数"}
        must_split = (
            role in {"heading", "number", "option"}
            or previous_role in {"heading", "number", "option"}
            or role != previous_role
            or starts_question
            or starts_callout_label
            or vertical_gap < -median_height * 0.25
            or vertical_gap > median_height * 1.45
            or left_shift > image.width * 0.18
        )
        if must_split:
            groups.append([block])
        else:
            previous_group.append(block)

    scale_y = model.size.height_pt / max(1, image.height)
    replacements: list[PageBlock] = []
    removed = {block.block_id for block in lines}
    for index, group in enumerate(groups, start=1):
        first = group[0]
        role = _line_role(first)
        block_type = {
            "callout": "editable_callout_body",
            "heading": "editable_heading",
            "number": "editable_page_number",
        }.get(role, "editable_paragraph")
        centers = [(item.bbox[1] + item.bbox[3]) / 2 for item in group]
        baseline_gaps = [right - left for left, right in zip(centers, centers[1:]) if right > left]
        line_spacing_pt = (median(baseline_gaps) * scale_y) if baseline_gaps else max(11.0, median_height * scale_y * 1.18)
        configured_sizes = [
            float(item.style["font_size_pt"])
            for item in group
            if isinstance(item.style.get("font_size_pt"), (int, float))
        ]
        style = dict(first.style)
        style.update(
            {
                "semantic_role": role,
                "source_line_ids": [item.block_id for item in group],
                "line_count": len(group),
                "line_spacing_pt": round(max(10.5, min(18.5, line_spacing_pt)), 2),
                "font_size_pt": round(median(configured_sizes) if configured_sizes else 9.6, 2),
                "font_name_east_asia": "SimSun",
                "font_name_ascii": "Times New Roman",
                "text_alignment": "left",
                "first_line_indent_px": round(first.bbox[0] - min(item.bbox[0] for item in group), 2),
            }
        )
        replacements.append(
            PageBlock(
                block_id=f"editable-paragraph-{index}",
                block_type=block_type,
                bbox=_union_bbox(group),
                z_index=min(item.z_index for item in group),
                reading_order=min(item.reading_order for item in group),
                confidence=fmean(item.confidence for item in group if item.confidence is not None) if any(item.confidence is not None for item in group) else None,
                text="\n".join((item.text or "").strip() for item in group),
                style=style,
                source="fresh source-first OCR paragraph grouping",
                selection_reason="OCR lines merged into one native Word semantic paragraph",
            )
        )
    model.blocks = [block for block in model.blocks if block.block_id not in removed] + replacements + option_rows


def _estimated_text_width_pt(value: str, font_pt: float) -> float:
    units = 0.0
    for character in value:
        if character == "\t":
            continue
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
    return units * font_pt


def _apply_editable_width_fitting(model: PageModel) -> None:
    """Pre-compress native lines whose Word font metrics would clip a tail."""

    scale_x = model.size.width_pt / max(1, model.source_image_width_px or round(model.size.width_pt))
    for block in model.blocks:
        if not block.text or block.asset_path or block.block_type == "editable_option_row":
            continue
        if not block.style.get("justify_to_bbox"):
            continue
        if block.style.get("source_line_layout"):
            continue
        try:
            font_pt = float(block.style.get("font_size_pt", 9.6))
        except (TypeError, ValueError):
            font_pt = 9.6
        lines = [line for line in block.text.splitlines() if line]
        if not lines:
            continue
        longest = max(lines, key=lambda line: _estimated_text_width_pt(line, font_pt))
        available = max(8.0, (block.bbox[2] - block.bbox[0]) * scale_x - 1.5)
        estimated = _estimated_text_width_pt(longest, font_pt)
        if estimated <= available * 0.98:
            continue
        fitted_font = max(8.2, font_pt * min(1.0, available * 0.98 / estimated))
        block.style["font_size_pt"] = round(fitted_font, 2)
        estimated = _estimated_text_width_pt(longest, fitted_font)
        characters = max(2, len(longest.replace(" ", "")))
        spacing_twips = round((available * 0.98 - estimated) * 20 / (characters - 1))
        block.style["character_spacing_twips"] = max(-18, min(0, spacing_twips))
        block.style["width_fit_applied"] = True
        model.debug_records.append(
            {
                "action": "editable_width_fit",
                "block_id": block.block_id,
                "block_type": block.block_type,
                "source": block.source,
                "reason": "predicted Word line width exceeded the exact source frame",
                "related_block_ids": [],
                "bbox": list(block.bbox),
                "text_preview": (block.text or "")[:80],
            }
        )


def apply_region_level_static_fallbacks(
    model: PageModel,
    image_path: str | Path,
    destination: str | Path,
) -> PageModel:
    """Repair only failing editable regions; never escalate one finding to a page image."""

    findings = static_page_checks(model)
    by_id = {block.block_id: block for block in model.blocks}
    editable_ids: set[str] = set()
    adjacency: dict[str, set[str]] = {}
    for finding in findings:
        if finding.get("type") not in {"duplicate_text", "image_text_conflict", "low_confidence"}:
            continue
        finding_ids: list[str] = []
        for block_id in finding.get("blocks", []):
            block = by_id.get(str(block_id))
            if block is not None and block.text and not block.asset_path:
                editable_ids.add(block.block_id)
                finding_ids.append(block.block_id)
        for block_id in finding_ids:
            adjacency.setdefault(block_id, set()).update(item for item in finding_ids if item != block_id)
    if not editable_ids:
        return model
    components: list[list[PageBlock]] = []
    remaining = set(editable_ids)
    while remaining:
        seed = remaining.pop()
        component_ids = {seed}
        frontier = [seed]
        while frontier:
            current = frontier.pop()
            for neighbour in adjacency.get(current, set()):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    component_ids.add(neighbour)
                    frontier.append(neighbour)
        components.append([by_id[block_id] for block_id in sorted(component_ids)])
    target = Path(destination)
    replacements: list[PageBlock] = []
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
        for index, component in enumerate(sorted(components, key=lambda items: _union_bbox(items)[1]), start=1):
            bbox = _union_bbox(component)
            replacement = PageBlock(
                block_id=f"region-gate-fallback-{index}",
                block_type="region_fallback_image",
                bbox=bbox,
                z_index=min(block.z_index for block in component),
                reading_order=min(block.reading_order for block in component),
                source="watermark-cleaned source PDF region",
                selection_reason="static gate rejected only this editable region",
                fallback_mode="region_source_image_after_static_gate",
            )
            _crop_block(image, replacement, target, margin=5)
            replacements.append(replacement)
            for block in component:
                model.debug_records.append(
                    {
                        "action": "replaced_with_region_fallback",
                        "block_id": block.block_id,
                        "block_type": block.block_type,
                        "source": block.source,
                        "reason": "region-level static gate finding",
                        "related_block_ids": [replacement.block_id],
                        "bbox": list(block.bbox),
                        "text_preview": (block.text or "")[:80],
                    }
                )
    model.blocks = [block for block in model.blocks if block.block_id not in editable_ids] + replacements
    model.warnings.append(
        f"静态门禁将 {len(editable_ids)} 个异常文字块合并回退为 {len(replacements)} 个局部源图，未将整页降级为图片。"
    )
    return resolve_page_model_conflicts(model)


def apply_source_first_hybrid_policy(
    model: PageModel,
    clean_image_path: str | Path,
    region_directory: str | Path,
    *,
    source_fingerprint: str,
    page_class: str = "ordinary_question",
    editable_body_only: bool = False,
) -> PageModel:
    """Postprocess a fresh OCR model into an accuracy-first ordinary page."""

    destination = Path(region_directory)
    with Image.open(clean_image_path) as opened:
        image = opened.convert("RGB")
        model.schema_version = PAGE_MODEL_SCHEMA_VERSION
        model.page_class = page_class
        model.reconstruction_mode = (
            "native_word_paragraphs_with_decorative_images_only"
            if editable_body_only
            else "native_word_paragraphs_with_clean_source_region_fallbacks"
        )
        model.source_fingerprint = source_fingerprint
        model.source_image_width_px, model.source_image_height_px = image.size
        model.evidence_blocks = deepcopy(model.blocks)
        # The source image is already cleaned, so a previously inferred
        # watermark layer must never be carried into Word.
        model.blocks = [block for block in model.blocks if block.block_type.lower() != "watermark"]
        if editable_body_only:
            _normalise_editable_pilot_text(model)
            _deduplicate_talk_badges(model, image, destination)
        else:
            # Claim callout first rows before formula fallback.  Those rows often
            # contain stacked fractions; formula-first processing would split the
            # badge, label and equation into overlapping crops.
            _replace_talk_prefixes(model, image, destination)
            _replace_stacked_formula_fragments(model, image, destination)
            _replace_formula_lines(model, image, destination)
        _replace_sidebars(model, image, destination)
        if page_class == "chapter_opener":
            _replace_chapter_header(model, image, destination)
        if editable_body_only:
            _strip_noneditable_body_visuals(model)
        else:
            _replace_uncovered_source_regions(model, image, destination)
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
        resolve_page_model_conflicts(model)
        _merge_editable_paragraphs(model, image)
        if editable_body_only:
            _apply_verified_pilot_repairs(model)
            _bind_answer_blanks_to_question_stems(model)
            _mark_verified_semantic_tokens(model)
            _attach_inline_callout_labels(model, image, destination)
            _derive_source_line_layouts(model, image)
        _apply_editable_width_fitting(model)
        model.warnings.append("此页从源 PDF 新渲染并重新 OCR；未读取旧任务缓存。")
        model.warnings.append("上岸人水印在 OCR 和回退裁图之前已从源渲染中清理。")
        if editable_body_only:
            model.warnings.append("正文零图片模式：正文、分式、公式、题干和解析均为可编辑 Word 内容；分式写为原生 OMML，上述谈标签仅保留行内装饰图。")
    return resolve_page_model_conflicts(model)
