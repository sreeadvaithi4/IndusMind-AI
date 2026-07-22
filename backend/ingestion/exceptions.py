"""
Custom exceptions for the document ingestion (Parser) module.

All parser-raised errors inherit from `ParserError` so callers (namely
`apps.documents.services.DocumentProcessingService.run_parser`) can
catch a single exception type and translate it into a Document status
transition, while still being able to inspect the specific failure
reason via `exc.__class__` or `exc.args` for logging/diagnostics.
"""


class ParserError(Exception):
    """Base class for all errors raised by the ingestion/parsing module."""


class UnsupportedFileTypeError(ParserError):
    """Raised when no parser is registered for a document's extension."""


class FileNotFoundOnDiskError(ParserError):
    """Raised when the Document's file field points to a missing file."""


class CorruptedFileError(ParserError):
    """Raised when a file cannot be opened/parsed because its content is invalid or corrupted."""


class EncryptedDocumentError(ParserError):
    """Raised when a document (e.g. a password-protected PDF) cannot be read without credentials."""


class EncodingDetectionError(ParserError):
    """Raised when a text-based file's encoding cannot be reliably determined or decoded."""


class OcrFailureError(ParserError):
    """Raised when OCR fallback is attempted but fails (engine error, missing dependency, etc.)."""
