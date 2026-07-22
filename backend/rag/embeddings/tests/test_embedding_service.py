"""
Tests for the Embedding Generator module (rag/embeddings/).

Tests cover:
    - Configuration validation
    - Input validation (ChunkCollection validation)
    - Per-chunk validation (empty, oversized, missing ID)
    - Batch creation
    - Duplicate detection via checksum
    - Successful embedding generation (mocked API)
    - Retry behavior on transient failures
    - Authentication error handling (non-retryable)
    - Rate limit handling
    - Timeout handling
    - Network error handling
    - All-chunks-failed raises EmbeddingError
    - Result serialization (to_dict)
    - Exception classification
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from ingestion.chunking.result import (
    Chunk,
    ChunkCollection,
    ChunkMetadata,
    ChunkType,
    ChunkingProcessingInfo,
)
from rag.embeddings.config import EmbeddingConfig
from rag.embeddings.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingRateLimitError,
    EmbeddingValidationError,
)
from rag.embeddings.result import (
    ChunkEmbedding,
    EmbeddingResult,
    EmbeddingStatus,
)
from rag.embeddings.service import EmbeddingGeneratorService
from rag.embeddings.validators import validate_chunk_collection, validate_chunk_for_embedding


def _make_chunk(chunk_number=1, text="Hello world", document_id="doc-123"):
    """Helper to create a test Chunk."""
    return Chunk(
        chunk_id=f"{document_id}_chunk_{chunk_number:04d}",
        document_id=document_id,
        chunk_number=chunk_number,
        text=text,
        chunk_type=ChunkType.TEXT,
        metadata=ChunkMetadata(
            document_id=document_id,
            filename="test.pdf",
            parser_used="pdf_parser",
            ocr_used=False,
            chunk_number=chunk_number,
            total_chunks=1,
            section="Introduction",
            source_type="text",
        ),
        word_count=len(text.split()),
        character_count=len(text),
    )


def _make_chunk_collection(num_chunks=3, document_id="doc-123"):
    """Helper to create a test ChunkCollection."""
    chunks = [
        _make_chunk(chunk_number=i + 1, text=f"Chunk text number {i + 1}", document_id=document_id)
        for i in range(num_chunks)
    ]
    return ChunkCollection(
        document_id=document_id,
        chunks=chunks,
        processing=ChunkingProcessingInfo(
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_seconds=0.5,
        ),
    )


def _make_config(**overrides):
    """Helper to create a test EmbeddingConfig."""
    defaults = {
        "model_name": "models/embedding-001",
        "api_key": "test-api-key",
        "batch_size": 20,
        "max_retries": 3,
        "timeout_seconds": 30,
        "max_concurrent_requests": 5,
        "max_chunk_text_length": 10000,
    }
    defaults.update(overrides)
    return EmbeddingConfig(**defaults)


class EmbeddingConfigTests(TestCase):
    """Tests for EmbeddingConfig."""

    @override_settings(GOOGLE_API_KEY="test-key")
    def test_from_settings_with_valid_key(self):
        config = EmbeddingConfig.from_settings()
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.model_name, "models/embedding-001")
        self.assertEqual(config.batch_size, 20)

    @override_settings(GOOGLE_API_KEY="")
    def test_from_settings_raises_on_missing_api_key(self):
        with self.assertRaises(EmbeddingConfigurationError) as ctx:
            EmbeddingConfig.from_settings()
        self.assertIn("GOOGLE_API_KEY", str(ctx.exception))

    @override_settings(GOOGLE_API_KEY="test-key", EMBEDDING_BATCH_SIZE=0)
    def test_from_settings_raises_on_invalid_batch_size(self):
        with self.assertRaises(EmbeddingConfigurationError):
            EmbeddingConfig.from_settings()

    @override_settings(GOOGLE_API_KEY="test-key", EMBEDDING_MAX_RETRIES=-1)
    def test_from_settings_raises_on_negative_retries(self):
        with self.assertRaises(EmbeddingConfigurationError):
            EmbeddingConfig.from_settings()

    @override_settings(GOOGLE_API_KEY="test-key", EMBEDDING_TIMEOUT_SECONDS=0)
    def test_from_settings_raises_on_zero_timeout(self):
        with self.assertRaises(EmbeddingConfigurationError):
            EmbeddingConfig.from_settings()

    @override_settings(
        GOOGLE_API_KEY="test-key",
        EMBEDDING_MODEL_NAME="models/text-embedding-004",
        EMBEDDING_BATCH_SIZE=10,
    )
    def test_from_settings_respects_custom_values(self):
        config = EmbeddingConfig.from_settings()
        self.assertEqual(config.model_name, "models/text-embedding-004")
        self.assertEqual(config.batch_size, 10)


class EmbeddingValidatorTests(TestCase):
    """Tests for embedding input validation."""

    def test_validate_none_chunk_collection(self):
        with self.assertRaises(EmbeddingValidationError):
            validate_chunk_collection(None)

    def test_validate_wrong_type_chunk_collection(self):
        with self.assertRaises(EmbeddingValidationError):
            validate_chunk_collection("not a collection")

    def test_validate_empty_chunk_collection(self):
        collection = ChunkCollection(document_id="doc-123", chunks=[])
        with self.assertRaises(EmbeddingValidationError):
            validate_chunk_collection(collection)

    def test_validate_missing_document_id(self):
        chunk = _make_chunk(document_id="doc-123")
        collection = ChunkCollection(document_id="", chunks=[chunk])
        with self.assertRaises(EmbeddingValidationError):
            validate_chunk_collection(collection)

    def test_validate_valid_collection_passes(self):
        collection = _make_chunk_collection()
        # Should not raise
        validate_chunk_collection(collection)

    def test_validate_chunk_empty_text_returns_skip(self):
        chunk = _make_chunk(text="")
        result = validate_chunk_for_embedding(chunk, max_text_length=10000)
        self.assertEqual(result, "empty_text")

    def test_validate_chunk_whitespace_only_returns_skip(self):
        chunk = _make_chunk(text="   \n\t  ")
        result = validate_chunk_for_embedding(chunk, max_text_length=10000)
        self.assertEqual(result, "empty_text")

    def test_validate_chunk_oversized_returns_none_not_skip(self):
        # Oversized chunks are truncated, not skipped
        chunk = _make_chunk(text="x" * 15000)
        result = validate_chunk_for_embedding(chunk, max_text_length=10000)
        self.assertIsNone(result)

    def test_validate_chunk_missing_id_returns_skip(self):
        chunk = _make_chunk()
        chunk.chunk_id = ""
        result = validate_chunk_for_embedding(chunk, max_text_length=10000)
        self.assertEqual(result, "missing_chunk_id")

    def test_validate_valid_chunk_returns_none(self):
        chunk = _make_chunk()
        result = validate_chunk_for_embedding(chunk, max_text_length=10000)
        self.assertIsNone(result)


class EmbeddingServiceBatchTests(TestCase):
    """Tests for batch creation logic."""

    def test_create_batches_even_split(self):
        chunks = [_make_chunk(chunk_number=i) for i in range(6)]
        batches = EmbeddingGeneratorService._create_batches(chunks, batch_size=3)
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 3)
        self.assertEqual(len(batches[1]), 3)

    def test_create_batches_uneven_split(self):
        chunks = [_make_chunk(chunk_number=i) for i in range(5)]
        batches = EmbeddingGeneratorService._create_batches(chunks, batch_size=3)
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 3)
        self.assertEqual(len(batches[1]), 2)

    def test_create_batches_single_batch(self):
        chunks = [_make_chunk(chunk_number=i) for i in range(2)]
        batches = EmbeddingGeneratorService._create_batches(chunks, batch_size=20)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 2)


class EmbeddingServiceGenerateTests(TestCase):
    """Tests for the main generate_embeddings method."""

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_successful_embedding_generation(self, mock_create_model):
        mock_model = MagicMock()
        # Simulate 768-dimensional embeddings
        mock_model.embed_documents.return_value = [
            [0.1] * 768,
            [0.2] * 768,
            [0.3] * 768,
        ]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=3)
        config = _make_config()

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertIsInstance(result, EmbeddingResult)
        self.assertEqual(result.total_embeddings, 3)
        self.assertEqual(result.successful_count, 3)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(result.embedding_dimension, 768)

        # Check each embedding has required fields
        for emb in result.embeddings:
            self.assertEqual(emb.status, EmbeddingStatus.SUCCESS)
            self.assertEqual(emb.embedding_model, "models/embedding-001")
            self.assertEqual(emb.embedding_dimension, 768)
            self.assertTrue(emb.embedding_timestamp)
            self.assertTrue(emb.checksum)
            self.assertEqual(len(emb.embedding), 768)
            self.assertIn("document_id", emb.metadata)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_duplicate_chunks_are_skipped(self, mock_create_model):
        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 768]
        mock_create_model.return_value = mock_model

        # Create chunks with identical text
        chunk1 = _make_chunk(chunk_number=1, text="Same text here")
        chunk2 = _make_chunk(chunk_number=2, text="Same text here")
        collection = ChunkCollection(
            document_id="doc-123",
            chunks=[chunk1, chunk2],
        )
        config = _make_config()

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 1)
        self.assertEqual(result.skipped_count, 1)
        # API should only be called once (for the non-duplicate)
        mock_model.embed_documents.assert_called_once()

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_empty_text_chunks_are_skipped(self, mock_create_model):
        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 768]
        mock_create_model.return_value = mock_model

        chunk_valid = _make_chunk(chunk_number=1, text="Valid chunk text")
        chunk_empty = _make_chunk(chunk_number=2, text="")
        collection = ChunkCollection(
            document_id="doc-123",
            chunks=[chunk_valid, chunk_empty],
        )
        config = _make_config()

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 1)
        self.assertEqual(result.skipped_count, 1)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_oversized_chunks_are_truncated_not_skipped(self, mock_create_model):
        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 768]
        mock_create_model.return_value = mock_model

        chunk = _make_chunk(chunk_number=1, text="x" * 15000)
        collection = ChunkCollection(
            document_id="doc-123",
            chunks=[chunk],
        )
        config = _make_config(max_chunk_text_length=10000)

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 1)
        # Verify text was truncated before sending to API
        call_args = mock_model.embed_documents.call_args[0][0]
        self.assertEqual(len(call_args[0]), 10000)

    @patch("rag.embeddings.service.time.sleep")
    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_retry_on_transient_error(self, mock_create_model, mock_sleep):
        mock_model = MagicMock()
        # Fail twice then succeed
        mock_model.embed_documents.side_effect = [
            Exception("Connection reset"),
            Exception("Connection reset"),
            [[0.1] * 768, [0.2] * 768, [0.3] * 768],
        ]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=3)
        config = _make_config(max_retries=3)

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 3)
        self.assertEqual(result.processing.retries_performed, 2)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("rag.embeddings.service.time.sleep")
    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_no_retry_on_authentication_error(self, mock_create_model, mock_sleep):
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = Exception(
            "Invalid API key (401 Unauthenticated)"
        )
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=3)
        config = _make_config(max_retries=3)

        # All chunks fail but auth error stops retries immediately
        with self.assertRaises(EmbeddingError):
            EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        # Should NOT have retried (auth errors are non-retryable)
        self.assertEqual(mock_model.embed_documents.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("rag.embeddings.service.time.sleep")
    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_rate_limit_extended_backoff(self, mock_create_model, mock_sleep):
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = [
            Exception("429 Resource exhausted: rate limit exceeded"),
            [[0.1] * 768, [0.2] * 768, [0.3] * 768],
        ]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=3)
        config = _make_config(max_retries=3)

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 3)
        # Rate limit backoff is longer (2^(attempt+2))
        mock_sleep.assert_called_once()
        wait_time = mock_sleep.call_args[0][0]
        self.assertGreaterEqual(wait_time, 4)  # 2^(0+2) = 4

    @patch("rag.embeddings.service.time.sleep")
    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_timeout_error_is_retried(self, mock_create_model, mock_sleep):
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = [
            Exception("Request timed out after 30s"),
            [[0.1] * 768, [0.2] * 768, [0.3] * 768],
        ]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=3)
        config = _make_config(max_retries=3)

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 3)
        self.assertEqual(result.processing.retries_performed, 1)

    @patch("rag.embeddings.service.time.sleep")
    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_all_retries_exhausted_marks_chunks_failed(self, mock_create_model, mock_sleep):
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = Exception("Persistent network error")
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=3)
        config = _make_config(max_retries=2)

        # All chunks fail → raises EmbeddingError
        with self.assertRaises(EmbeddingError):
            EmbeddingGeneratorService.generate_embeddings(collection, config=config)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_batch_size_respected(self, mock_create_model):
        mock_model = MagicMock()
        # Return appropriate number of embeddings per batch
        mock_model.embed_documents.side_effect = [
            [[0.1] * 768, [0.2] * 768],  # batch 1 (2 chunks)
            [[0.3] * 768],  # batch 2 (1 chunk)
        ]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=3)
        config = _make_config(batch_size=2)

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 3)
        self.assertEqual(result.processing.total_batches, 2)
        self.assertEqual(mock_model.embed_documents.call_count, 2)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_result_to_dict_excludes_vectors(self, mock_create_model):
        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 768]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=1)
        config = _make_config()

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)
        result_dict = result.to_dict()

        # to_dict should NOT contain actual embedding vectors
        self.assertNotIn("embeddings", result_dict)
        self.assertIn("total_embeddings", result_dict)
        self.assertIn("successful_count", result_dict)
        self.assertIn("embedding_dimension", result_dict)
        self.assertIn("embedding_model", result_dict)
        self.assertIn("processing", result_dict)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_chunk_embedding_to_dict_excludes_vector(self, mock_create_model):
        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 768]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=1)
        config = _make_config()

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)
        emb_dict = result.embeddings[0].to_dict()

        # to_dict should NOT contain the embedding vector
        self.assertNotIn("embedding", emb_dict)
        self.assertIn("chunk_id", emb_dict)
        self.assertIn("checksum", emb_dict)
        self.assertIn("embedding_dimension", emb_dict)

    def test_checksum_is_deterministic(self):
        text = "Hello, world!"
        checksum1 = ChunkEmbedding.compute_checksum(text)
        checksum2 = ChunkEmbedding.compute_checksum(text)
        self.assertEqual(checksum1, checksum2)

    def test_checksum_differs_for_different_text(self):
        checksum1 = ChunkEmbedding.compute_checksum("Hello")
        checksum2 = ChunkEmbedding.compute_checksum("World")
        self.assertNotEqual(checksum1, checksum2)


class EmbeddingExceptionClassificationTests(TestCase):
    """Tests for exception classification logic."""

    def test_classify_auth_error(self):
        exc = Exception("Invalid API key provided")
        result = EmbeddingGeneratorService._classify_exception(exc)
        self.assertIsInstance(result, EmbeddingAuthenticationError)

    def test_classify_rate_limit_error(self):
        exc = Exception("429 Resource_exhausted: quota exceeded")
        result = EmbeddingGeneratorService._classify_exception(exc)
        self.assertIsInstance(result, EmbeddingRateLimitError)

    def test_classify_timeout_error(self):
        exc = Exception("Request timed out after 30 seconds")
        result = EmbeddingGeneratorService._classify_exception(exc)
        from rag.embeddings.exceptions import EmbeddingTimeoutError
        self.assertIsInstance(result, EmbeddingTimeoutError)

    def test_classify_network_error(self):
        exc = Exception("Connection refused by remote host")
        result = EmbeddingGeneratorService._classify_exception(exc)
        from rag.embeddings.exceptions import EmbeddingNetworkError
        self.assertIsInstance(result, EmbeddingNetworkError)

    def test_classify_unknown_error_as_api_error(self):
        exc = Exception("Something unexpected happened")
        result = EmbeddingGeneratorService._classify_exception(exc)
        from rag.embeddings.exceptions import EmbeddingAPIError
        self.assertIsInstance(result, EmbeddingAPIError)


class EmbeddingServiceProgressTests(TestCase):
    """Tests for progress tracking and processing info."""

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_processing_info_populated(self, mock_create_model):
        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 768, [0.2] * 768]
        mock_create_model.return_value = mock_model

        collection = _make_chunk_collection(num_chunks=2)
        config = _make_config()

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertIsNotNone(result.processing)
        self.assertIsNotNone(result.processing.started_at)
        self.assertIsNotNone(result.processing.finished_at)
        self.assertGreaterEqual(result.processing.duration_seconds, 0)
        self.assertEqual(result.processing.total_chunks, 2)
        self.assertEqual(result.processing.successful_chunks, 2)
        self.assertEqual(result.processing.failed_chunks, 0)
        self.assertEqual(result.processing.skipped_chunks, 0)
        self.assertEqual(result.processing.total_batches, 1)
        self.assertEqual(result.processing.retries_performed, 0)

    @patch("rag.embeddings.service.time.sleep")
    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_warnings_populated_on_partial_failure(self, mock_create_model, mock_sleep):
        mock_model = MagicMock()
        # First batch succeeds, second batch fails
        mock_model.embed_documents.side_effect = [
            [[0.1] * 768],
            Exception("Temporary error"),
            Exception("Temporary error"),
            Exception("Temporary error"),
            Exception("Temporary error"),  # all retries exhausted
        ]
        mock_create_model.return_value = mock_model

        chunk1 = _make_chunk(chunk_number=1, text="First chunk")
        chunk2 = _make_chunk(chunk_number=2, text="Second chunk different")
        collection = ChunkCollection(
            document_id="doc-123",
            chunks=[chunk1, chunk2],
        )
        config = _make_config(batch_size=1, max_retries=3)

        result = EmbeddingGeneratorService.generate_embeddings(collection, config=config)

        self.assertEqual(result.successful_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertTrue(any("failed to embed" in w for w in result.processing.warnings))
