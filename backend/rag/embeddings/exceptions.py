"""
Exception hierarchy for the Embedding Generator module.

All exceptions raised by this module inherit from `EmbeddingError`, so
callers (specifically `DocumentProcessingService.run_embedding_generator`)
can catch a single base class, mirroring the pattern established by
`ingestion.exceptions.ParserError` and
`ingestion.chunking.exceptions.ChunkingError`.
"""


class EmbeddingError(Exception):
    """Base exception for all embedding generation failures."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the embedding service is misconfigured (e.g. missing API key)."""


class EmbeddingAPIError(EmbeddingError):
    """Raised when the embedding API returns an unexpected error response."""


class EmbeddingRateLimitError(EmbeddingAPIError):
    """Raised when the embedding API rate-limits the request."""


class EmbeddingTimeoutError(EmbeddingAPIError):
    """Raised when an embedding API request times out."""


class EmbeddingAuthenticationError(EmbeddingAPIError):
    """Raised when the embedding API rejects the provided credentials."""


class EmbeddingValidationError(EmbeddingError):
    """Raised when input validation fails (e.g. empty chunk text, oversized chunk)."""


class EmbeddingNetworkError(EmbeddingAPIError):
    """Raised when a network-level failure prevents API communication."""
