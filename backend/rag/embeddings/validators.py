"""
Input validation for the Embedding Generator.

Validates chunks before they are sent to the embedding API, catching
issues early (empty text, oversized text, missing metadata) to avoid
wasting API calls and providing clear error messages.
"""

import logging

from ingestion.chunking.result import Chunk, ChunkCollection
from rag.embeddings.exceptions import EmbeddingValidationError

logger = logging.getLogger("rag.embeddings")


def validate_chunk_collection(chunk_collection: ChunkCollection) -> None:
    """
    Validates that a ChunkCollection is suitable for embedding.

    Raises:
        EmbeddingValidationError: if the collection is None, empty,
            or fundamentally malformed.
    """
    if chunk_collection is None:
        raise EmbeddingValidationError(
            "chunk_collection is None — cannot generate embeddings "
            "without chunked content."
        )

    if not isinstance(chunk_collection, ChunkCollection):
        raise EmbeddingValidationError(
            f"Expected ChunkCollection, got {type(chunk_collection).__name__}."
        )

    if not chunk_collection.chunks:
        raise EmbeddingValidationError(
            "chunk_collection contains no chunks — nothing to embed."
        )

    if not chunk_collection.document_id:
        raise EmbeddingValidationError(
            "chunk_collection.document_id is empty — cannot generate "
            "embeddings without a document identifier."
        )


def validate_chunk_for_embedding(chunk: Chunk, max_text_length: int) -> str | None:
    """
    Validates a single chunk for embedding suitability.

    Returns:
        None if the chunk is valid; a skip-reason string if the chunk
        should be skipped (e.g. empty text). Raises
        `EmbeddingValidationError` only for truly malformed input that
        indicates a programming error.
    """
    if not chunk.text or not chunk.text.strip():
        return "empty_text"

    if len(chunk.text) > max_text_length:
        logger.warning(
            "Chunk %s text length (%d) exceeds max (%d) — will be truncated.",
            chunk.chunk_id,
            len(chunk.text),
            max_text_length,
        )
        # Not a skip — we truncate oversized chunks rather than skipping them.
        # Return None to indicate "valid (after truncation)".
        return None

    if not chunk.chunk_id:
        return "missing_chunk_id"

    return None
