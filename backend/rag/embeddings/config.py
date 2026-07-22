"""
Configuration for the Embedding Generator module.

All values are environment-variable-driven via Django settings,
following the same pattern as `ingestion/chunking/config.py:ChunkingConfig`.
"""

from dataclasses import dataclass

from django.conf import settings

from rag.embeddings.exceptions import EmbeddingConfigurationError


@dataclass(frozen=True)
class EmbeddingConfig:
    """
    Immutable configuration for the embedding service.

    Attributes:
        model_name: Google Gemini embedding model identifier.
        api_key: Google API key for authentication.
        batch_size: Number of chunks to embed in a single API call.
        max_retries: Maximum number of retry attempts for transient failures.
        timeout_seconds: Per-request timeout in seconds.
        max_concurrent_requests: Maximum parallel embedding requests
            (reserved for future async implementation; currently
            embeddings are processed sequentially in batches).
        max_chunk_text_length: Maximum character length for a single
            chunk's text before it is considered oversized.
    """

    model_name: str
    api_key: str
    batch_size: int
    max_retries: int
    timeout_seconds: int
    max_concurrent_requests: int
    max_chunk_text_length: int

    @classmethod
    def from_settings(cls) -> "EmbeddingConfig":
        """
        Constructs an `EmbeddingConfig` from Django settings, which in
        turn are populated from environment variables (see
        `config/settings.py`). Raises `EmbeddingConfigurationError` if
        required settings are missing or invalid.
        """
        api_key = getattr(settings, "GOOGLE_API_KEY", "")
        if not api_key:
            raise EmbeddingConfigurationError(
                "GOOGLE_API_KEY is not configured. Set it in your environment "
                "or .env file to use the Embedding Generator."
            )

        model_name = getattr(settings, "EMBEDDING_MODEL_NAME", "models/embedding-001")
        batch_size = getattr(settings, "EMBEDDING_BATCH_SIZE", 20)
        max_retries = getattr(settings, "EMBEDDING_MAX_RETRIES", 3)
        timeout_seconds = getattr(settings, "EMBEDDING_TIMEOUT_SECONDS", 30)
        max_concurrent_requests = getattr(settings, "EMBEDDING_MAX_CONCURRENT_REQUESTS", 5)
        max_chunk_text_length = getattr(settings, "EMBEDDING_MAX_CHUNK_TEXT_LENGTH", 10000)

        # Validate numeric bounds
        if batch_size < 1:
            raise EmbeddingConfigurationError(
                f"EMBEDDING_BATCH_SIZE must be >= 1, got {batch_size}."
            )
        if max_retries < 0:
            raise EmbeddingConfigurationError(
                f"EMBEDDING_MAX_RETRIES must be >= 0, got {max_retries}."
            )
        if timeout_seconds < 1:
            raise EmbeddingConfigurationError(
                f"EMBEDDING_TIMEOUT_SECONDS must be >= 1, got {timeout_seconds}."
            )
        if max_concurrent_requests < 1:
            raise EmbeddingConfigurationError(
                f"EMBEDDING_MAX_CONCURRENT_REQUESTS must be >= 1, got {max_concurrent_requests}."
            )
        if max_chunk_text_length < 1:
            raise EmbeddingConfigurationError(
                f"EMBEDDING_MAX_CHUNK_TEXT_LENGTH must be >= 1, got {max_chunk_text_length}."
            )

        return cls(
            model_name=model_name,
            api_key=api_key,
            batch_size=batch_size,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            max_concurrent_requests=max_concurrent_requests,
            max_chunk_text_length=max_chunk_text_length,
        )
