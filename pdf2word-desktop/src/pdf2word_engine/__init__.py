"""PDF2Word Desktop conversion engine."""

from .document_profiles import SourceDocumentProfile, resolve_source_document_profile
from .dynamic_sampling import PageInventoryRecord, select_dynamic_canary_pages
from .models import PdfKind, PreflightReport
from .pipeline import create_current_source_first_pilot, create_source_first_pilot
from .preflight import inspect_pdf

__all__ = [
    "PdfKind",
    "PageInventoryRecord",
    "PreflightReport",
    "SourceDocumentProfile",
    "create_source_first_pilot",
    "create_current_source_first_pilot",
    "inspect_pdf",
    "resolve_source_document_profile",
    "select_dynamic_canary_pages",
]
