"""
Standardized parser output types.

`ParsedDocument` is the contract every format-specific parser produces
and the contract the future Chunker (Sprint 6) will consume. It is a
plain, JSON-serializable dataclass — not a Django model — since it
represents an in-memory intermediate result, not something persisted
wholesale (only a summary is persisted, onto `Document.parser_metadata`
and `Document.page_count`).
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DocumentMetadata:
    """Metadata extracted from (or about) a parsed document."""

    title: str | None = None
    author: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    language: str | None = None
    page_count: int | None = None
    extension: str = ""
    parser_used: str = ""
    ocr_used: bool = False
    parsing_time_seconds: float = 0.0
    character_count: int = 0
    word_count: int = 0

    def to_dict(self):
        return {
            "title": self.title,
            "author": self.author,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "language": self.language,
            "page_count": self.page_count,
            "extension": self.extension,
            "parser_used": self.parser_used,
            "ocr_used": self.ocr_used,
            "parsing_time_seconds": self.parsing_time_seconds,
            "character_count": self.character_count,
            "word_count": self.word_count,
        }


@dataclass
class OcrInfo:
    """Describes whether/how OCR fallback was used during parsing."""

    used: bool = False
    engine: str | None = None
    pages_ocred: list[int] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self):
        return {
            "used": self.used,
            "engine": self.engine,
            "pages_ocred": self.pages_ocred,
            "reason": self.reason,
        }


@dataclass
class ProcessingInfo:
    """Timing and diagnostic information about a single parse run."""

    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "warnings": self.warnings,
        }


@dataclass
class ParsedDocument:
    """
    The standardized output of parsing any supported document.

    Attributes:
        document_id: string form of the source Document's UUID.
        text: the full extracted plain text of the document, used
            directly by the future Chunker as its input.
        metadata: see DocumentMetadata.
        tables: each table is a list of rows, each row a list of cell
            strings. Empty for formats/documents with no tabular data.
        images: structural references to embedded/rendered images
            encountered while parsing (e.g. for OCR provenance). This
            sprint does not extract or persist image bytes — only
            tracks that images were present and whether OCR consumed
            them, since image extraction/storage is out of scope.
        ocr: see OcrInfo.
        processing: see ProcessingInfo.
    """

    document_id: str
    text: str
    metadata: DocumentMetadata
    tables: list[list[list[str]]] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    ocr: OcrInfo = field(default_factory=OcrInfo)
    processing: ProcessingInfo | None = None

    def to_dict(self):
        """
        Full JSON-serializable representation, suitable for storage in
        `Document.parser_metadata` (minus `text`/`tables`, which are
        intentionally excluded from persistence — see
        `ingestion.service.DocumentParserService` docstring).
        """
        return {
            "document_id": self.document_id,
            "metadata": self.metadata.to_dict(),
            "ocr": self.ocr.to_dict(),
            "processing": self.processing.to_dict() if self.processing else None,
            "table_count": len(self.tables),
            "image_count": len(self.images),
        }
