"""
Exception hierarchy for the ChromaDB Vector Store module.

All exceptions raised by this module inherit from `VectorStoreError`, so
callers (specifically `DocumentProcessingService.store_in_vector_db`)
can catch a single base class, mirroring the pattern established by
`ingestion.exceptions.ParserError`, `ingestion.chunking.exceptions.ChunkingError`,
and `rag.embeddings.exceptions.EmbeddingError`.
"""


class VectorStoreError(Exception):
    """Base exception for all vector store failures."""


class VectorStoreConfigurationError(VectorStoreError):
    """Raised when the vector store is misconfigured (e.g. invalid persist path)."""


class VectorStoreConnectionError(VectorStoreError):
    """Raised when ChromaDB cannot be initialized or connected to."""


class VectorStoreCollectionError(VectorStoreError):
    """Raised when a collection cannot be created, retrieved, or managed."""


class VectorStoreInsertionError(VectorStoreError):
    """Raised when vectors cannot be inserted into ChromaDB."""


class VectorStoreDeletionError(VectorStoreError):
    """Raised when vectors cannot be deleted from ChromaDB."""


class VectorStoreSearchError(VectorStoreError):
    """Raised when a search query fails."""


class VectorStoreValidationError(VectorStoreError):
    """Raised when input validation fails (e.g. empty embeddings, invalid format)."""
