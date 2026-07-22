"""
Standardized embedding output types.

`EmbeddingResult` is the contract between the Embedding Generator and
the future ChromaDB integration (Sprint 8+) — each `ChunkEmbedding`
carries everything needed to store a single chunk's vector without a
database round-trip back to the Document model.

Design mirrors `ingestion.result.ParsedDocument` and
`ingestion.chunking.result.ChunkCollection`: plain, JSON-serializable
dataclasses (not Django models).
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EmbeddingStatus(str, Enum):
    """Per-chunk embedding status."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g. empty text, duplicate


@dataclass
class ChunkEmbedding:
    """
    A single chunk's embedding result, enriched with provenance metadata.

    Attributes:
        chunk_id: The original `Chunk.chunk_id` from the ChunkCollection.
        document_id: The owning document's UUID (string).
        chunk_number: Original chunk number in the collection.
        embedding: The dense vector (list of floats). Empty list on failure.
        embedding_model: Model identifier used to generate this embedding.
        embedding_dimension: Length of the embedding vector.
        embedding_timestamp: When this embedding was generated (UTC ISO string).
        checksum: SHA-256 hash of the chunk text that was embedded — for
            duplicate detection and cache invalidation.
        status: Whether this chunk was successfully embedded.
        error_message: Populated only when status is FAILED.
        metadata: Original chunk metadata (passed through unchanged).
    """

    chunk_id: str
    document_id: str
    chunk_number: int
    embedding: list[float]
    embedding_model: str
    embedding_dimension: int
    embedding_timestamp: str
    checksum: str
    status: EmbeddingStatus
    error_message: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-serializable representation (excludes embedding vector for metadata storage)."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "chunk_number": self.chunk_number,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "embedding_timestamp": self.embedding_timestamp,
            "checksum": self.checksum,
            "status": self.status.value,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @staticmethod
    def compute_checksum(text: str) -> str:
        """Compute SHA-256 checksum of chunk text for duplicate detection."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class EmbeddingProcessingInfo:
    """Timing and diagnostic information about a single embedding run."""

    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    total_chunks: int
    successful_chunks: int
    failed_chunks: int
    skipped_chunks: int
    total_batches: int
    retries_performed: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "total_chunks": self.total_chunks,
            "successful_chunks": self.successful_chunks,
            "failed_chunks": self.failed_chunks,
            "skipped_chunks": self.skipped_chunks,
            "total_batches": self.total_batches,
            "retries_performed": self.retries_performed,
            "warnings": self.warnings,
        }


@dataclass
class EmbeddingResult:
    """
    The complete standardized output of embedding one document's chunks.

    This is the contract the future ChromaDB integration will consume —
    specifically `embeddings` (the list of `ChunkEmbedding` objects,
    each carrying its vector and metadata) and `processing` (timing
    and diagnostic info).
    """

    document_id: str
    embeddings: list[ChunkEmbedding] = field(default_factory=list)
    processing: EmbeddingProcessingInfo | None = None

    @property
    def total_embeddings(self) -> int:
        return len(self.embeddings)

    @property
    def successful_count(self) -> int:
        return sum(1 for e in self.embeddings if e.status == EmbeddingStatus.SUCCESS)

    @property
    def failed_count(self) -> int:
        return sum(1 for e in self.embeddings if e.status == EmbeddingStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for e in self.embeddings if e.status == EmbeddingStatus.SKIPPED)

    @property
    def embedding_dimension(self) -> int | None:
        """Returns the dimension from the first successful embedding, or None."""
        for e in self.embeddings:
            if e.status == EmbeddingStatus.SUCCESS and e.embedding:
                return e.embedding_dimension
        return None

    def to_dict(self) -> dict:
        """
        JSON-serializable summary for persistence in
        `Document.embedding_metadata` — excludes actual embedding
        vectors (same rationale as `ChunkCollection.to_dict()` excluding
        chunk text: vectors would bloat the database and are only needed
        by the ChromaDB storage step, which receives the in-memory
        `EmbeddingResult` directly).
        """
        return {
            "document_id": self.document_id,
            "total_embeddings": self.total_embeddings,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "embedding_dimension": self.embedding_dimension,
            "embedding_model": (
                self.embeddings[0].embedding_model if self.embeddings else None
            ),
            "processing": self.processing.to_dict() if self.processing else None,
        }
