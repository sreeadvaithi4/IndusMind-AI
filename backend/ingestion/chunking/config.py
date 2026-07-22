"""
Configuration for the chunking module.

All values are overridable via Django settings
(`CHUNKING_CHUNK_SIZE`, `CHUNKING_CHUNK_OVERLAP`,
`CHUNKING_MAX_CHUNK_LENGTH`, `CHUNKING_MIN_CHUNK_LENGTH`), mirroring how
`DOCUMENT_MAX_UPLOAD_SIZE_MB` and `OCR_ENABLED` are configured (Sprint 5).
`ChunkingConfig.from_settings()` is the normal way to obtain a config;
constructing it directly with explicit values is primarily useful in
tests.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingConfig:
    """
    Attributes:
        chunk_size: target size (in characters) for a single text chunk.
        chunk_overlap: number of trailing characters from one chunk
            repeated at the start of the next, to preserve context
            across chunk boundaries.
        max_chunk_length: hard ceiling — a chunk is never emitted
            larger than this even if a strategy would otherwise
            produce one (guards against pathological single
            "paragraphs" with no break points).
        min_chunk_length: chunks smaller than this (in characters) are
            merged into an adjacent chunk rather than emitted standalone,
            avoiding near-useless tiny chunks (e.g. a lone short line).
    """

    chunk_size: int = 1000
    chunk_overlap: int = 150
    max_chunk_length: int = 2000
    min_chunk_length: int = 20

    def __post_init__(self):
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        if self.max_chunk_length < self.chunk_size:
            raise ValueError("max_chunk_length must be >= chunk_size.")
        if self.min_chunk_length < 0:
            raise ValueError("min_chunk_length cannot be negative.")

    @classmethod
    def from_settings(cls) -> "ChunkingConfig":
        from django.conf import settings

        return cls(
            chunk_size=getattr(settings, "CHUNKING_CHUNK_SIZE", 1000),
            chunk_overlap=getattr(settings, "CHUNKING_CHUNK_OVERLAP", 150),
            max_chunk_length=getattr(settings, "CHUNKING_MAX_CHUNK_LENGTH", 2000),
            min_chunk_length=getattr(settings, "CHUNKING_MIN_CHUNK_LENGTH", 20),
        )
