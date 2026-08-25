"""Memory-bounded, page-by-page PDFium rendering."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pypdfium2 as pdfium

from .errors import JobCancelledError
from .models import PageSize, RenderedPage


ProgressCallback = Callable[[dict[str, object]], None]


def render_pages(
    source: str | Path,
    *,
    page_indices: list[int],
    page_directory: Callable[[int], Path],
    dpi: int,
    should_cancel: Callable[[], bool] | None = None,
    progress: ProgressCallback | None = None,
) -> Iterator[RenderedPage]:
    """Render requested pages one at a time and release native resources promptly."""

    if dpi < 72 or dpi > 600:
        raise ValueError("DPI 必须介于 72 和 600 之间。")
    document = pdfium.PdfDocument(str(source))
    try:
        for position, page_index in enumerate(page_indices, start=1):
            if should_cancel and should_cancel():
                raise JobCancelledError("任务已取消。")
            page = document[page_index]
            try:
                size = PageSize(width_pt=float(page.get_width()), height_pt=float(page.get_height()))
                bitmap = page.render(scale=dpi / 72)
                try:
                    image = bitmap.to_pil()
                    if image.mode not in {"RGB", "L"}:
                        image = image.convert("RGB")
                    output_path = page_directory(page_index) / "render.png"
                    image.save(output_path, format="PNG", optimize=True, compress_level=6)
                finally:
                    bitmap.close()
                rendered = RenderedPage(page_index=page_index, image_path=output_path, size=size)
                if progress:
                    progress(
                        {
                            "type": "page_rendered",
                            "page_index": page_index,
                            "completed": position,
                            "total": len(page_indices),
                            "image_path": str(output_path),
                        }
                    )
                yield rendered
            finally:
                page.close()
    finally:
        document.close()
