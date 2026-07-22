"""Custom exceptions for the document chunking module."""


class ChunkingError(Exception):
    """Base class for all errors raised by the chunking module."""


class EmptyDocumentError(ChunkingError):
    """Raised when a ParsedDocument has no text and no tables to chunk."""


class CorruptedParsedContentError(ChunkingError):
    """Raised when the input ParsedDocument is structurally invalid (e.g. malformed tables)."""


class UnsupportedStructureError(ChunkingError):
    """Raised when a document structure cannot be chunked by any available strategy."""
