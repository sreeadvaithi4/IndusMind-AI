"""
Standardized chunking output types.

`ChunkCollection` is the contract every chunking strategy contributes
to and the contract the future Embedding Generator (Sprint 7) will
consume — one embedding request per `Chunk.text`. Mirrors the design
of `ingestion.result.ParsedDocument` from Sprint 5: plain,
JSON-serializable dataclasses, not Django models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ChunkType(str, Enum):
    """Distinguishes prose/text chunks from tabular chunks."""

    TEXT = "text"
    TABLE = "table"


@dataclass
class ChunkMetadata:
    """
    Metadata attached to every chunk, carrying enough provenance for
    the Embedding Generator (and, later, retrieval/citation in AI
    Chat) to trace a chunk back to its source document without a
    database round-trip.
    """

    document_id: str
    filename: str
    parser_used: str
    ocr_used: bool
    chunk_number: int
    total_chunks: int
    section: str | None
    source_type: str  # "text" | "table" (mirrors ChunkType.value)

    def to_dict(self):
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "parser_used": self.parser_used,
            "ocr_used": self.ocr_used,
            "chunk_number": self.chunk_number,
            "total_chunks": self.total_chunks,
            "section": self.section,
            "source_type": self.source_type,
        }


@dataclass
class Chunk:
    """A single standardized chunk, ready for embedding."""

    chunk_id: str
    document_id: str
    chunk_number: int
    text: str
    chunk_type: ChunkType
    metadata: ChunkMetadata
    word_count: int
    character_count: int
    page_number: int | None = None
    section_title: str | None = None

    def to_dict(self):
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "chunk_number": self.chunk_number,
            "text": self.text,
            "chunk_type": self.chunk_type.value,
            "metadata": self.metadata.to_dict(),
            "word_count": self.word_count,
            "character_count": self.character_count,
            "page_number": self.page_number,
            "section_title": self.section_title,
        }


@dataclass
class ChunkingProcessingInfo:
    """Timing and diagnostic information about a single chunking run."""

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
class ChunkCollection:
    """The complete standardized output of chunking one document."""

    document_id: str
    chunks: list[Chunk] = field(default_factory=list)
    processing: ChunkingProcessingInfo | None = None

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def text_chunk_count(self) -> int:
        return sum(1 for c in self.chunks if c.chunk_type == ChunkType.TEXT)

    @property
    def table_chunk_count(self) -> int:
        return sum(1 for c in self.chunks if c.chunk_type == ChunkType.TABLE)

    def to_dict(self):
        """
        Full JSON-serializable summary, suitable for storage in
        `Document.chunker_metadata` — mirrors
        `ingestion.result.ParsedDocument.to_dict()`'s decision to
        exclude bulk content (chunk text) from persistence, keeping
        only counts/timing/diagnostics. The in-memory `ChunkCollection`
        itself (with full chunk text) is what gets passed directly to
        the future Embedding Generator.
        """
        return {
            "document_id": self.document_id,
            "total_chunks": self.total_chunks,
            "text_chunk_count": self.text_chunk_count,
            "table_chunk_count": self.table_chunk_count,
            "processing": self.processing.to_dict() if self.processing else None,
        }
