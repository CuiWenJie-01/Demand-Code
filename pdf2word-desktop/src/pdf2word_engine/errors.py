"""Domain-specific errors exposed to the CLI and desktop host."""


class Pdf2WordError(Exception):
    """Base error for an expected conversion failure."""


class EncryptedPdfError(Pdf2WordError):
    """Raised when a password-protected PDF is supplied without support."""


class OcrRequiredError(Pdf2WordError):
    """Raised when editable output needs OCR but no OCR engine is available."""


class JobCancelledError(Pdf2WordError):
    """Raised when the persisted job cancellation flag is observed."""


class InvalidPageRangeError(Pdf2WordError):
    """Raised for invalid user page-range input."""
