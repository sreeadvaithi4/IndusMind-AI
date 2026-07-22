"""
Configuration for the ChromaDB Vector Store module.

All values are environment-variable-driven via Django settings,
following the same pattern as `rag/embeddings/config.py:EmbeddingConfig`.
"""

from dataclasses import dataclass

from django.conf import settings

from rag.vectorstore.exceptions import VectorStoreConfigurationError


@dataclass(frozen=True)
class VectorStoreConfig:
    """
    Immutable configuration for the vector store service.

    Attributes:
        persist_directory: Path where ChromaDB persists its data.
        collection_name: Default collection name for document vectors.
        batch_size: Number of vectors to insert per ChromaDB batch call.
        search_k: Default number of results to return for searches.
        similarity_threshold: Minimum similarity score to include in results
            (0.0–1.0 for cosine; lower distance = more similar in ChromaDB).
        max_results: Hard cap on search results.
    """

    persist_directory: str
    collection_name: str
    batch_size: int
    search_k: int
    similarity_threshold: float
    max_results: int

    @classmethod
    def from_settings(cls) -> "VectorStoreConfig":
        """
        Constructs a `VectorStoreConfig` from Django settings.

        Raises `VectorStoreConfigurationError` if required settings are
        missing or invalid.
        """
        persist_directory = getattr(settings, "CHROMA_PERSIST_DIRECTORY", "")
        if not persist_directory:
            raise VectorStoreConfigurationError(
                "CHROMA_PERSIST_DIRECTORY is not configured. Set it in your "
                "environment or .env file."
            )

        collection_name = getattr(
            settings, "CHROMA_COLLECTION_NAME", "indusmind_documents"
        )
        batch_size = getattr(settings, "CHROMA_BATCH_SIZE", 100)
        search_k = getattr(settings, "CHROMA_SEARCH_K", 10)
        similarity_threshold = getattr(settings, "CHROMA_SIMILARITY_THRESHOLD", 0.0)
        max_results = getattr(settings, "CHROMA_MAX_RESULTS", 50)

        if batch_size < 1:
            raise VectorStoreConfigurationError(
                f"CHROMA_BATCH_SIZE must be >= 1, got {batch_size}."
            )
        if search_k < 1:
            raise VectorStoreConfigurationError(
                f"CHROMA_SEARCH_K must be >= 1, got {search_k}."
            )
        if max_results < 1:
            raise VectorStoreConfigurationError(
                f"CHROMA_MAX_RESULTS must be >= 1, got {max_results}."
            )
        if not (0.0 <= similarity_threshold <= 2.0):
            raise VectorStoreConfigurationError(
                f"CHROMA_SIMILARITY_THRESHOLD must be between 0.0 and 2.0, "
                f"got {similarity_threshold}."
            )

        return cls(
            persist_directory=persist_directory,
            collection_name=collection_name,
            batch_size=batch_size,
            search_k=search_k,
            similarity_threshold=similarity_threshold,
            max_results=max_results,
        )
