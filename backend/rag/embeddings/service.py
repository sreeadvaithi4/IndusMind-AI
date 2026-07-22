"""
Enterprise Embedding Generator Service.

Consumes `ChunkCollection` (the output of the Chunker module) and
produces `EmbeddingResult` containing vector embeddings for each chunk,
using the Google Gemini Embedding API via LangChain.

Features:
    - Batch embedding (configurable batch size)
    - Retry with exponential backoff for transient failures
    - Rate limit handling (retries on 429)
    - Timeout handling (per-request timeout)
    - Progress tracking via logging
    - Input validation (empty/oversized chunk detection)
    - Duplicate protection (SHA-256 checksum per chunk)
    - Metadata preservation (original chunk metadata carried through)

This service has no dependency on `apps.documents` — it operates purely
on `ChunkCollection`/`Chunk` dataclasses and returns `EmbeddingResult`.
The orchestration (status transitions, model persistence) belongs in
`apps.documents.services.DocumentProcessingService.run_embedding_generator`.
"""

import logging
import time
from datetime import datetime, timezone

from ingestion.chunking.result import Chunk, ChunkCollection
from rag.embeddings.config import EmbeddingConfig
from rag.embeddings.exceptions import (
    EmbeddingAPIError,
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingNetworkError,
    EmbeddingRateLimitError,
    EmbeddingTimeoutError,
    EmbeddingValidationError,
)
from rag.embeddings.result import (
    ChunkEmbedding,
    EmbeddingProcessingInfo,
    EmbeddingResult,
    EmbeddingStatus,
)
from rag.embeddings.validators import validate_chunk_collection, validate_chunk_for_embedding

logger = logging.getLogger("rag.embeddings")


class EmbeddingGeneratorService:
    """
    Entry point for the Embedding Generator module.

    Usage:
        result = EmbeddingGeneratorService.generate_embeddings(chunk_collection)
    """

    @classmethod
    def generate_embeddings(
        cls,
        chunk_collection: ChunkCollection,
        config: EmbeddingConfig | None = None,
    ) -> EmbeddingResult:
        """
        Generates embeddings for all chunks in a ChunkCollection.

        Args:
            chunk_collection: The chunked document output from the
                Chunker module.
            config: Optional EmbeddingConfig override (useful for
                testing). If None, loads from Django settings.

        Returns:
            EmbeddingResult containing a ChunkEmbedding for each chunk
            (successfully embedded, failed, or skipped).

        Raises:
            EmbeddingValidationError: if the input is fundamentally invalid.
            EmbeddingConfigurationError: if the service is misconfigured.
            EmbeddingError: for unrecoverable embedding failures that
                prevent any progress (e.g. all batches fail).
        """
        started_at = datetime.now(timezone.utc)

        # Validate input
        validate_chunk_collection(chunk_collection)

        # Load configuration
        if config is None:
            config = EmbeddingConfig.from_settings()

        logger.info(
            "Starting embedding generation for document %s (%d chunks, "
            "batch_size=%d, model=%s).",
            chunk_collection.document_id,
            chunk_collection.total_chunks,
            config.batch_size,
            config.model_name,
        )

        # Initialize the embedding model
        embeddings_model = cls._create_embeddings_model(config)

        # Process chunks in batches
        all_embeddings: list[ChunkEmbedding] = []
        total_retries = 0
        total_batches = 0
        skipped_checksums: set[str] = set()
        warnings: list[str] = []

        batches = cls._create_batches(chunk_collection.chunks, config.batch_size)

        for batch_index, batch in enumerate(batches):
            total_batches += 1
            logger.info(
                "Processing batch %d/%d (%d chunks) for document %s.",
                batch_index + 1,
                len(batches),
                len(batch),
                chunk_collection.document_id,
            )

            # Validate and prepare batch
            valid_chunks: list[Chunk] = []
            for chunk in batch:
                skip_reason = validate_chunk_for_embedding(
                    chunk, config.max_chunk_text_length
                )
                if skip_reason:
                    all_embeddings.append(
                        cls._create_skipped_embedding(
                            chunk, config.model_name, skip_reason
                        )
                    )
                    continue

                # Duplicate protection via checksum
                checksum = ChunkEmbedding.compute_checksum(chunk.text)
                if checksum in skipped_checksums:
                    all_embeddings.append(
                        cls._create_skipped_embedding(
                            chunk, config.model_name, "duplicate_text"
                        )
                    )
                    warnings.append(
                        f"Chunk {chunk.chunk_id} skipped as duplicate "
                        f"(same text as a previous chunk)."
                    )
                    continue
                skipped_checksums.add(checksum)
                valid_chunks.append(chunk)

            if not valid_chunks:
                continue

            # Generate embeddings for this batch with retry
            batch_embeddings, batch_retries = cls._embed_batch_with_retry(
                embeddings_model, valid_chunks, config
            )
            total_retries += batch_retries
            all_embeddings.extend(batch_embeddings)

        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - started_at).total_seconds()

        successful_count = sum(
            1 for e in all_embeddings if e.status == EmbeddingStatus.SUCCESS
        )
        failed_count = sum(
            1 for e in all_embeddings if e.status == EmbeddingStatus.FAILED
        )
        skipped_count = sum(
            1 for e in all_embeddings if e.status == EmbeddingStatus.SKIPPED
        )

        if successful_count == 0 and chunk_collection.total_chunks > 0:
            raise EmbeddingError(
                f"Embedding generation failed for all {chunk_collection.total_chunks} "
                f"chunks in document {chunk_collection.document_id}. "
                f"Failed: {failed_count}, Skipped: {skipped_count}."
            )

        if failed_count > 0:
            warnings.append(
                f"{failed_count} chunk(s) failed to embed and will not have "
                f"vector representations in the vector store."
            )

        processing = EmbeddingProcessingInfo(
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            total_chunks=chunk_collection.total_chunks,
            successful_chunks=successful_count,
            failed_chunks=failed_count,
            skipped_chunks=skipped_count,
            total_batches=total_batches,
            retries_performed=total_retries,
            warnings=warnings,
        )

        result = EmbeddingResult(
            document_id=chunk_collection.document_id,
            embeddings=all_embeddings,
            processing=processing,
        )

        logger.info(
            "Embedding generation complete for document %s: %d/%d successful, "
            "%d failed, %d skipped (%.2fs, %d retries).",
            chunk_collection.document_id,
            successful_count,
            chunk_collection.total_chunks,
            failed_count,
            skipped_count,
            duration,
            total_retries,
        )

        return result

    @classmethod
    def _create_embeddings_model(cls, config: EmbeddingConfig):
        """
        Instantiates the LangChain GoogleGenerativeAIEmbeddings model.

        Raises:
            EmbeddingConfigurationError: if the model cannot be instantiated.
        """
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            model = GoogleGenerativeAIEmbeddings(
                model=config.model_name,
                google_api_key=config.api_key,
                request_timeout=config.timeout_seconds,
            )
            return model
        except ImportError as exc:
            raise EmbeddingConfigurationError(
                "langchain-google-genai is not installed. "
                "Install it with: pip install langchain-google-genai"
            ) from exc
        except Exception as exc:
            raise EmbeddingConfigurationError(
                f"Failed to initialize embedding model '{config.model_name}': {exc}"
            ) from exc

    @classmethod
    def _embed_batch_with_retry(
        cls,
        embeddings_model,
        chunks: list[Chunk],
        config: EmbeddingConfig,
    ) -> tuple[list[ChunkEmbedding], int]:
        """
        Attempts to embed a batch of chunks with exponential-backoff retry.

        Returns:
            Tuple of (list of ChunkEmbedding results, number of retries performed).
        """
        texts = [
            chunk.text[:config.max_chunk_text_length] for chunk in chunks
        ]
        retries = 0
        last_exception: Exception | None = None

        for attempt in range(config.max_retries + 1):
            try:
                vectors = embeddings_model.embed_documents(texts)
                # Success — build ChunkEmbedding objects
                timestamp = datetime.now(timezone.utc).isoformat()
                results = []
                for chunk, vector in zip(chunks, vectors):
                    checksum = ChunkEmbedding.compute_checksum(chunk.text)
                    results.append(
                        ChunkEmbedding(
                            chunk_id=chunk.chunk_id,
                            document_id=chunk.document_id,
                            chunk_number=chunk.chunk_number,
                            embedding=vector,
                            embedding_model=config.model_name,
                            embedding_dimension=len(vector),
                            embedding_timestamp=timestamp,
                            checksum=checksum,
                            status=EmbeddingStatus.SUCCESS,
                            metadata=chunk.metadata.to_dict(),
                        )
                    )
                return results, retries

            except Exception as exc:
                last_exception = exc
                classified = cls._classify_exception(exc)

                if isinstance(classified, EmbeddingAuthenticationError):
                    # Authentication errors are not retryable
                    logger.error(
                        "Authentication failed for embedding API: %s", exc
                    )
                    break

                if isinstance(classified, EmbeddingRateLimitError):
                    # Rate limits — back off longer
                    wait = min(2 ** (attempt + 2), 60)
                    logger.warning(
                        "Rate limited (attempt %d/%d), waiting %.1fs: %s",
                        attempt + 1,
                        config.max_retries + 1,
                        wait,
                        exc,
                    )
                elif isinstance(classified, (EmbeddingTimeoutError, EmbeddingNetworkError)):
                    # Transient — standard backoff
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "Transient error (attempt %d/%d), waiting %.1fs: %s",
                        attempt + 1,
                        config.max_retries + 1,
                        wait,
                        exc,
                    )
                else:
                    # Unknown API error — still retry
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "API error (attempt %d/%d), waiting %.1fs: %s",
                        attempt + 1,
                        config.max_retries + 1,
                        wait,
                        exc,
                    )

                if attempt < config.max_retries:
                    retries += 1
                    time.sleep(wait)
                else:
                    break

        # All retries exhausted — mark every chunk in this batch as FAILED
        timestamp = datetime.now(timezone.utc).isoformat()
        error_msg = str(last_exception) if last_exception else "Unknown error"
        results = []
        for chunk in chunks:
            checksum = ChunkEmbedding.compute_checksum(chunk.text)
            results.append(
                ChunkEmbedding(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    chunk_number=chunk.chunk_number,
                    embedding=[],
                    embedding_model=config.model_name,
                    embedding_dimension=0,
                    embedding_timestamp=timestamp,
                    checksum=checksum,
                    status=EmbeddingStatus.FAILED,
                    error_message=error_msg,
                    metadata=chunk.metadata.to_dict(),
                )
            )
        return results, retries

    @classmethod
    def _classify_exception(cls, exc: Exception):
        """
        Classifies a raw exception from the LangChain/Google SDK into
        our exception hierarchy for appropriate retry/backoff behavior.
        """
        exc_str = str(exc).lower()
        exc_type = type(exc).__name__.lower()

        # Authentication errors
        if any(keyword in exc_str for keyword in ("invalid api key", "api_key_invalid", "401", "unauthenticated")):
            return EmbeddingAuthenticationError(str(exc))

        # Rate limit errors
        if any(keyword in exc_str for keyword in ("429", "rate limit", "resource_exhausted", "quota")):
            return EmbeddingRateLimitError(str(exc))

        # Timeout errors
        if any(keyword in exc_str for keyword in ("timeout", "timed out", "deadline exceeded")):
            return EmbeddingTimeoutError(str(exc))

        # Network errors
        if any(keyword in exc_str for keyword in ("connection", "network", "dns", "refused", "unreachable")):
            return EmbeddingNetworkError(str(exc))

        if "timeout" in exc_type:
            return EmbeddingTimeoutError(str(exc))

        # Default: generic API error (retryable)
        return EmbeddingAPIError(str(exc))

    @staticmethod
    def _create_batches(chunks: list[Chunk], batch_size: int) -> list[list[Chunk]]:
        """Splits a list of chunks into batches of `batch_size`."""
        return [
            chunks[i: i + batch_size]
            for i in range(0, len(chunks), batch_size)
        ]

    @staticmethod
    def _create_skipped_embedding(
        chunk: Chunk, model_name: str, reason: str
    ) -> ChunkEmbedding:
        """Creates a ChunkEmbedding with SKIPPED status."""
        return ChunkEmbedding(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            chunk_number=chunk.chunk_number,
            embedding=[],
            embedding_model=model_name,
            embedding_dimension=0,
            embedding_timestamp=datetime.now(timezone.utc).isoformat(),
            checksum=ChunkEmbedding.compute_checksum(chunk.text) if chunk.text else "",
            status=EmbeddingStatus.SKIPPED,
            error_message=f"Skipped: {reason}",
            metadata=chunk.metadata.to_dict() if chunk.metadata else {},
        )
