from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def create_text_pdf(path: Path, *, pages: int = 2) -> Path:
    document = canvas.Canvas(str(path), pagesize=A4)
    for index in range(pages):
        document.setFont("Helvetica", 12)
        document.drawString(72, 760, f"PDF2Word test page {index + 1}")
        document.drawString(72, 735, "This born-digital page contains searchable text.")
        document.showPage()
    document.save()
    return path
