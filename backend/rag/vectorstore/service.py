"""
Enterprise ChromaDB Vector Store Service.

Consumes `EmbeddingResult` (the output of the Embedding Generator) and
persists embedding vectors + metadata into ChromaDB for semantic search.

Features:
    - Batch insertion (configurable batch size)
    - Batch deletion (by document_id)
    - Duplicate prevention (upsert semantics via ChromaDB IDs)
    - Metadata filtering on search (document type, date, source, etc.)
    - Collection management (create, get, delete, stats)
    - Health check
    - Connection pooling (single client per persist directory)
    - Graceful error handling with detailed logging

This service has no dependency on `apps.documents` — it operates purely
on `EmbeddingResult`/`ChunkEmbedding` dataclasses and returns
`IndexingResult`/`SearchResult`. The orchestration (status transitions,
model persistence) belongs in
`apps.documents.services.DocumentProcessingService.store_in_vector_db`.
"""

import logging
import time
from datetime import datetime, timezone

from rag.embeddings.result import ChunkEmbedding, EmbeddingResult, EmbeddingStatus
from rag.vectorstore.config import VectorStoreConfig
from rag.vectorstore.exceptions import (
    VectorStoreCollectionError,
    VectorStoreConfigurationError,
    VectorStoreConnectionError,
    VectorStoreDeletionError,
    VectorStoreError,
    VectorStoreInsertionError,
    VectorStoreSearchError,
    VectorStoreValidationError,
)
from rag.vectorstore.result import (
    CollectionStats,
    IndexingResult,
    SearchHit,
    SearchResult,
)

logger = logging.getLogger("rag.vectorstore")

# Module-level client cache for connection reuse
_client_cache: dict[str, object] = {}


class VectorStoreService:
    """
    Entry point for the ChromaDB Vector Store module.

    Usage:
        # Indexing
        result = VectorStoreService.index_embeddings(embedding_result)

        # Searching
        result = VectorStoreService.search(query_embedding, k=10)

        # Deletion
        VectorStoreService.delete_document_vectors(document_id)
    """

    @classmethod
    def index_embeddings(
        cls,
        embedding_result: EmbeddingResult,
        config: VectorStoreConfig | None = None,
        document_metadata: dict | None = None,
    ) -> IndexingResult:
        """
        Indexes all successful embeddings from an EmbeddingResult into
        ChromaDB.

        Args:
            embedding_result: The output from the Embedding Generator.
            config: Optional config override (useful for testing).
            document_metadata: Optional additional metadata to store with
                every vector (e.g. upload_date, document_type, user_id).

        Returns:
            IndexingResult with counts and timing.

        Raises:
            VectorStoreValidationError: if input is invalid.
            VectorStoreError: for unrecoverable storage failures.
        """
        start_time = time.time()

        # Validate input
        cls._validate_embedding_result(embedding_result)

        # Load config
        if config is None:
            config = VectorStoreConfig.from_settings()

        # Get successful embeddings only
        successful = [
            emb for emb in embedding_result.embeddings
            if emb.status == EmbeddingStatus.SUCCESS and emb.embedding
        ]

        skipped = len(embedding_result.embeddings) - len(successful)
        warnings: list[str] = []

        if not successful:
            warnings.append("No successful embeddings to index.")
            return IndexingResult(
                document_id=embedding_result.document_id,
                total_indexed=0,
                total_skipped=skipped,
                collection_name=config.collection_name,
                duration_seconds=round(time.time() - start_time, 3),
                warnings=warnings,
            )

        logger.info(
            "Starting vector indexing for document %s (%d vectors, "
            "batch_size=%d, collection=%s).",
            embedding_result.document_id,
            len(successful),
            config.batch_size,
            config.collection_name,
        )

        # Get or create collection
        collection = cls._get_or_create_collection(config)

        # Build batch data
        total_indexed = 0
        batches = cls._create_batches(successful, config.batch_size)

        for batch_idx, batch in enumerate(batches):
            ids = []
            embeddings = []
            documents = []
            metadatas = []

            for emb in batch:
                metadata = cls._build_metadata(emb, document_metadata)
                ids.append(emb.chunk_id)
                embeddings.append(emb.embedding)
                documents.append(metadata.pop("_text", ""))
                metadatas.append(metadata)

            try:
                collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                )
                total_indexed += len(ids)
            except Exception as exc:
                logger.error(
                    "Failed to insert batch %d/%d for document %s: %s",
                    batch_idx + 1,
                    len(batches),
                    embedding_result.document_id,
                    exc,
                )
                raise VectorStoreInsertionError(
                    f"Failed to insert batch {batch_idx + 1} into ChromaDB: {exc}"
                ) from exc

        duration = round(time.time() - start_time, 3)

        if skipped > 0:
            warnings.append(
                f"{skipped} embedding(s) skipped (failed/skipped status)."
            )

        logger.info(
            "Vector indexing complete for document %s: %d indexed, "
            "%d skipped (%.2fs).",
            embedding_result.document_id,
            total_indexed,
            skipped,
            duration,
        )

        return IndexingResult(
            document_id=embedding_result.document_id,
            total_indexed=total_indexed,
            total_skipped=skipped,
            collection_name=config.collection_name,
            duration_seconds=duration,
            warnings=warnings,
        )

    @classmethod
    def search(
        cls,
        query_embedding: list[float],
        k: int | None = None,
        config: VectorStoreConfig | None = None,
        where: dict | None = None,
        where_document: dict | None = None,
    ) -> SearchResult:
        """
        Performs semantic search using a pre-computed query embedding.

        Args:
            query_embedding: The dense vector for the search query.
            k: Number of results to return (defaults to config.search_k).
            config: Optional config override.
            where: Optional metadata filter dict (ChromaDB where clause).
                Examples:
                    {"document_id": "abc-123"}
                    {"document_type": "pdf"}
                    {"$and": [{"document_id": "abc"}, {"chunk_type": "text"}]}
            where_document: Optional document content filter
                (ChromaDB where_document clause).
                Example: {"$contains": "maintenance"}

        Returns:
            SearchResult with ranked hits.

        Raises:
            VectorStoreSearchError: if the search fails.
        """
        start_time = time.time()

        if config is None:
            config = VectorStoreConfig.from_settings()

        if k is None:
            k = config.search_k
        k = min(k, config.max_results)

        if not query_embedding:
            raise VectorStoreSearchError("query_embedding is empty.")

        try:
            collection = cls._get_collection(config)
        except VectorStoreCollectionError:
            # Collection doesn't exist yet — return empty results
            return SearchResult(
                query="[embedding]",
                hits=[],
                total_hits=0,
                search_time_seconds=round(time.time() - start_time, 3),
                collection_name=config.collection_name,
            )

        query_params: dict = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_params["where"] = where
        if where_document:
            query_params["where_document"] = where_document

        try:
            results = collection.query(**query_params)
        except Exception as exc:
            raise VectorStoreSearchError(
                f"ChromaDB search failed: {exc}"
            ) from exc

        hits = cls._parse_search_results(results, config.similarity_threshold)
        duration = round(time.time() - start_time, 3)

        return SearchResult(
            query="[embedding]",
            hits=hits,
            total_hits=len(hits),
            search_time_seconds=duration,
            collection_name=config.collection_name,
        )

    @classmethod
    def delete_document_vectors(
        cls,
        document_id: str,
        config: VectorStoreConfig | None = None,
    ) -> int:
        """
        Deletes all vectors associated with a document.

        Args:
            document_id: The document whose vectors to remove.
            config: Optional config override.

        Returns:
            Number of vectors deleted (0 if collection doesn't exist).

        Raises:
            VectorStoreDeletionError: on failure.
        """
        if not document_id:
            raise VectorStoreDeletionError("document_id is required.")

        if config is None:
            config = VectorStoreConfig.from_settings()

        try:
            collection = cls._get_collection(config)
        except VectorStoreCollectionError:
            return 0

        try:
            # Get IDs for this document
            existing = collection.get(
                where={"document_id": document_id},
                include=[],
            )
            if not existing["ids"]:
                return 0

            count = len(existing["ids"])
            collection.delete(ids=existing["ids"])

            logger.info(
                "Deleted %d vectors for document %s from collection %s.",
                count,
                document_id,
                config.collection_name,
            )
            return count
        except Exception as exc:
            raise VectorStoreDeletionError(
                f"Failed to delete vectors for document {document_id}: {exc}"
            ) from exc

    @classmethod
    def get_collection_stats(
        cls, config: VectorStoreConfig | None = None
    ) -> CollectionStats:
        """Returns statistics for the configured collection."""
        if config is None:
            config = VectorStoreConfig.from_settings()

        try:
            collection = cls._get_collection(config)
            count = collection.count()
            return CollectionStats(
                collection_name=config.collection_name,
                total_vectors=count,
            )
        except VectorStoreCollectionError:
            return CollectionStats(
                collection_name=config.collection_name,
                total_vectors=0,
            )

    @classmethod
    def health_check(cls, config: VectorStoreConfig | None = None) -> dict:
        """
        Performs a health check on the ChromaDB connection.

        Returns a dict with 'healthy' (bool) and optional 'error' (str).
        """
        if config is None:
            config = VectorStoreConfig.from_settings()

        try:
            client = cls._get_client(config)
            # Heartbeat returns a nanosecond timestamp
            heartbeat = client.heartbeat()
            return {"healthy": True, "heartbeat": heartbeat}
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_client(cls, config: VectorStoreConfig):
        """
        Returns a ChromaDB PersistentClient, reusing existing connections.
        """
        global _client_cache

        if config.persist_directory in _client_cache:
            return _client_cache[config.persist_directory]

        try:
            import chromadb

            client = chromadb.PersistentClient(path=config.persist_directory)
            _client_cache[config.persist_directory] = client
            return client
        except ImportError as exc:
            raise VectorStoreConfigurationError(
                "chromadb is not installed. Install with: pip install chromadb"
            ) from exc
        except Exception as exc:
            raise VectorStoreConnectionError(
                f"Failed to connect to ChromaDB at "
                f"'{config.persist_directory}': {exc}"
            ) from exc

    @classmethod
    def _get_or_create_collection(cls, config: VectorStoreConfig):
        """Gets or creates the configured ChromaDB collection."""
        client = cls._get_client(config)
        try:
            collection = client.get_or_create_collection(
                name=config.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return collection
        except Exception as exc:
            raise VectorStoreCollectionError(
                f"Failed to get/create collection '{config.collection_name}': {exc}"
            ) from exc

    @classmethod
    def _get_collection(cls, config: VectorStoreConfig):
        """Gets an existing collection (raises if it doesn't exist)."""
        client = cls._get_client(config)
        try:
            return client.get_collection(name=config.collection_name)
        except Exception as exc:
            raise VectorStoreCollectionError(
                f"Collection '{config.collection_name}' does not exist: {exc}"
            ) from exc

    @classmethod
    def _validate_embedding_result(cls, embedding_result: EmbeddingResult) -> None:
        """Validates an EmbeddingResult before indexing."""
        if embedding_result is None:
            raise VectorStoreValidationError(
                "embedding_result is None — cannot index without embeddings."
            )
        if not isinstance(embedding_result, EmbeddingResult):
            raise VectorStoreValidationError(
                f"Expected EmbeddingResult, got {type(embedding_result).__name__}."
            )
        if not embedding_result.document_id:
            raise VectorStoreValidationError(
                "embedding_result.document_id is empty."
            )

    @classmethod
    def _build_metadata(
        cls,
        emb: ChunkEmbedding,
        document_metadata: dict | None,
    ) -> dict:
        """
        Builds the metadata dict to store in ChromaDB for a single vector.

        ChromaDB metadata values must be str, int, float, or bool — no
        nested dicts, lists, or None. We flatten and sanitize.
        """
        metadata = {
            "document_id": emb.document_id,
            "chunk_id": emb.chunk_id,
            "chunk_number": emb.chunk_number,
            "embedding_model": emb.embedding_model,
            "embedding_dimension": emb.embedding_dimension,
            "embedding_timestamp": emb.embedding_timestamp,
            "checksum": emb.checksum,
            # From chunk metadata
            "source_filename": emb.metadata.get("filename") or "",
            "parser_used": emb.metadata.get("parser_used") or "",
            "ocr_used": bool(emb.metadata.get("ocr_used", False)),
            "section": emb.metadata.get("section") or "",
            "source_type": emb.metadata.get("source_type") or "",
            "chunk_total": emb.metadata.get("total_chunks") or 0,
            # Page number (currently None from Chunker, stored as -1)
            "page_number": emb.metadata.get("page_number") if emb.metadata.get("page_number") is not None else -1,
            # Processing timestamp
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Add document-level metadata if provided
        if document_metadata:
            for key, value in document_metadata.items():
                # Only store ChromaDB-compatible types, skip None
                if value is not None and isinstance(value, (str, int, float, bool)):
                    metadata[key] = value

        # Store the chunk text as the ChromaDB "document" field
        # (separate from metadata), using a special key to pass it up
        metadata["_text"] = emb.metadata.get("_chunk_text") or ""

        return metadata

    @classmethod
    def _parse_search_results(
        cls, raw_results: dict, similarity_threshold: float
    ) -> list[SearchHit]:
        """Converts raw ChromaDB query results to SearchHit objects."""
        hits = []

        if not raw_results or not raw_results.get("ids"):
            return hits

        ids = raw_results["ids"][0] if raw_results["ids"] else []
        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        for i, chunk_id in enumerate(ids):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (distance / 2) → 0..1
            distance = distances[i] if i < len(distances) else 1.0
            similarity = 1.0 - (distance / 2.0)

            if similarity_threshold > 0 and similarity < similarity_threshold:
                continue

            metadata = metadatas[i] if i < len(metadatas) else {}
            text = documents[i] if i < len(documents) else ""

            hits.append(SearchHit(
                chunk_id=chunk_id,
                document_id=metadata.get("document_id", ""),
                text=text,
                score=round(similarity, 4),
                metadata=metadata,
            ))

        return hits

    @staticmethod
    def _create_batches(items: list, batch_size: int) -> list[list]:
        """Splits a list into batches of `batch_size`."""
        return [
            items[i: i + batch_size]
            for i in range(0, len(items), batch_size)
        ]

    @classmethod
    def reset_client_cache(cls):
        """Resets the client cache (for testing only)."""
        global _client_cache
        _client_cache = {}
