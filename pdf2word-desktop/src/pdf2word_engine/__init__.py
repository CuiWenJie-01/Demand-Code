"""PDF2Word Desktop conversion engine."""

from .models import ConversionMode, PdfKind, PreflightReport
from .pipeline import ConversionResult, convert_pdf
from .preflight import inspect_pdf

__all__ = [
    "ConversionMode",
    "ConversionResult",
    "PdfKind",
    "PreflightReport",
    "convert_pdf",
    "inspect_pdf",
]
