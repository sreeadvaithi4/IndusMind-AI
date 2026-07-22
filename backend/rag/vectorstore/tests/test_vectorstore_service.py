"""
Tests for the ChromaDB Vector Store module (rag/vectorstore/).

Tests cover:
    - Configuration validation
    - Input validation (EmbeddingResult validation)
    - Successful indexing (real ChromaDB in-memory via temp directory)
    - Batch insertion
    - Duplicate prevention (upsert)
    - Document vector deletion
    - Semantic search with results
    - Metadata filtering on search
    - Empty search results
    - Collection stats
    - Health check
    - Error handling
"""

import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase, override_settings

from rag.embeddings.result import (
    ChunkEmbedding,
    EmbeddingProcessingInfo,
    EmbeddingResult,
    EmbeddingStatus,
)
from rag.vectorstore.config import VectorStoreConfig
from rag.vectorstore.exceptions import (
    VectorStoreConfigurationError,
    VectorStoreError,
    VectorStoreInsertionError,
    VectorStoreSearchError,
    VectorStoreValidationError,
)
from rag.vectorstore.result import IndexingResult, SearchResult
from rag.vectorstore.service import VectorStoreService


def _make_chunk_embedding(
    chunk_id="doc-123_chunk_0001",
    document_id="doc-123",
    chunk_number=1,
    text="Test chunk text for embedding",
    embedding=None,
    status=EmbeddingStatus.SUCCESS,
):
    """Helper to create a test ChunkEmbedding."""
    if embedding is None:
        embedding = [0.1] * 768
    return ChunkEmbedding(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_number=chunk_number,
        embedding=embedding,
        embedding_model="models/embedding-001",
        embedding_dimension=len(embedding),
        embedding_timestamp=datetime.now(timezone.utc).isoformat(),
        checksum="abc123",
        status=status,
        metadata={
            "document_id": document_id,
            "filename": "test.pdf",
            "parser_used": "pdf_parser",
            "ocr_used": False,
            "chunk_number": chunk_number,
            "total_chunks": 3,
            "section": "Introduction",
            "source_type": "text",
        },
    )


def _make_embedding_result(num_embeddings=3, document_id="doc-123"):
    """Helper to create a test EmbeddingResult."""
    embeddings = [
        _make_chunk_embedding(
            chunk_id=f"{document_id}_chunk_{i+1:04d}",
            document_id=document_id,
            chunk_number=i + 1,
            text=f"Chunk text number {i + 1} about maintenance procedures",
            embedding=[0.1 * (i + 1)] * 768,
        )
        for i in range(num_embeddings)
    ]
    return EmbeddingResult(
        document_id=document_id,
        embeddings=embeddings,
        processing=EmbeddingProcessingInfo(
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_seconds=0.5,
            total_chunks=num_embeddings,
            successful_chunks=num_embeddings,
            failed_chunks=0,
            skipped_chunks=0,
            total_batches=1,
            retries_performed=0,
        ),
    )


def _make_config(temp_dir):
    """Helper to create a test VectorStoreConfig."""
    return VectorStoreConfig(
        persist_directory=temp_dir,
        collection_name="test_collection",
        batch_size=10,
        search_k=5,
        similarity_threshold=0.0,
        max_results=50,
    )


class VectorStoreConfigTests(TestCase):
    """Tests for VectorStoreConfig."""

    @override_settings(CHROMA_PERSIST_DIRECTORY="/tmp/test_chroma")
    def test_from_settings_with_valid_config(self):
        config = VectorStoreConfig.from_settings()
        self.assertEqual(config.persist_directory, "/tmp/test_chroma")
        self.assertEqual(config.collection_name, "indusmind_documents")
        self.assertEqual(config.batch_size, 100)
        self.assertEqual(config.search_k, 10)

    @override_settings(CHROMA_PERSIST_DIRECTORY="")
    def test_from_settings_raises_on_empty_persist_directory(self):
        with self.assertRaises(VectorStoreConfigurationError):
            VectorStoreConfig.from_settings()

    @override_settings(CHROMA_PERSIST_DIRECTORY="/tmp/test", CHROMA_BATCH_SIZE=0)
    def test_from_settings_raises_on_invalid_batch_size(self):
        with self.assertRaises(VectorStoreConfigurationError):
            VectorStoreConfig.from_settings()

    @override_settings(CHROMA_PERSIST_DIRECTORY="/tmp/test", CHROMA_SEARCH_K=0)
    def test_from_settings_raises_on_invalid_search_k(self):
        with self.assertRaises(VectorStoreConfigurationError):
            VectorStoreConfig.from_settings()


class VectorStoreValidationTests(TestCase):
    """Tests for input validation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = _make_config(self.temp_dir)

    def tearDown(self):
        VectorStoreService.reset_client_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_none_embedding_result(self):
        with self.assertRaises(VectorStoreValidationError):
            VectorStoreService.index_embeddings(None, config=self.config)

    def test_validate_wrong_type(self):
        with self.assertRaises(VectorStoreValidationError):
            VectorStoreService.index_embeddings("not a result", config=self.config)

    def test_validate_empty_document_id(self):
        result = EmbeddingResult(document_id="", embeddings=[])
        with self.assertRaises(VectorStoreValidationError):
            VectorStoreService.index_embeddings(result, config=self.config)


class VectorStoreIndexingTests(TestCase):
    """Tests for vector indexing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = _make_config(self.temp_dir)

    def tearDown(self):
        VectorStoreService.reset_client_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_successful_indexing(self):
        embedding_result = _make_embedding_result(num_embeddings=3)
        result = VectorStoreService.index_embeddings(
            embedding_result, config=self.config
        )

        self.assertIsInstance(result, IndexingResult)
        self.assertEqual(result.total_indexed, 3)
        self.assertEqual(result.total_skipped, 0)
        self.assertEqual(result.document_id, "doc-123")
        self.assertEqual(result.collection_name, "test_collection")
        self.assertGreater(result.duration_seconds, 0)

    def test_skips_failed_embeddings(self):
        embedding_result = _make_embedding_result(num_embeddings=2)
        # Add a failed embedding
        failed = _make_chunk_embedding(
            chunk_id="doc-123_chunk_0003",
            status=EmbeddingStatus.FAILED,
            embedding=[],
        )
        embedding_result.embeddings.append(failed)

        result = VectorStoreService.index_embeddings(
            embedding_result, config=self.config
        )

        self.assertEqual(result.total_indexed, 2)
        self.assertEqual(result.total_skipped, 1)

    def test_upsert_prevents_duplicates(self):
        embedding_result = _make_embedding_result(num_embeddings=2)

        # Index twice
        VectorStoreService.index_embeddings(embedding_result, config=self.config)
        VectorStoreService.index_embeddings(embedding_result, config=self.config)

        # Collection should have exactly 2 vectors (upsert, not duplicate)
        stats = VectorStoreService.get_collection_stats(config=self.config)
        self.assertEqual(stats.total_vectors, 2)

    def test_batch_indexing(self):
        config = VectorStoreConfig(
            persist_directory=self.temp_dir,
            collection_name="test_collection",
            batch_size=2,  # Small batch to force multiple batches
            search_k=5,
            similarity_threshold=0.0,
            max_results=50,
        )
        embedding_result = _make_embedding_result(num_embeddings=5)
        result = VectorStoreService.index_embeddings(
            embedding_result, config=config
        )

        self.assertEqual(result.total_indexed, 5)

    def test_no_successful_embeddings_returns_zero(self):
        result = EmbeddingResult(
            document_id="doc-123",
            embeddings=[
                _make_chunk_embedding(status=EmbeddingStatus.FAILED, embedding=[]),
            ],
        )
        indexing = VectorStoreService.index_embeddings(result, config=self.config)
        self.assertEqual(indexing.total_indexed, 0)
        self.assertEqual(indexing.total_skipped, 1)

    def test_document_metadata_stored(self):
        embedding_result = _make_embedding_result(num_embeddings=1)
        VectorStoreService.index_embeddings(
            embedding_result,
            config=self.config,
            document_metadata={"document_type": "pdf", "upload_date": "2024-01-01"},
        )

        # Search and verify metadata
        collection = VectorStoreService._get_collection(self.config)
        result = collection.get(ids=["doc-123_chunk_0001"], include=["metadatas"])
        metadata = result["metadatas"][0]
        self.assertEqual(metadata["document_type"], "pdf")
        self.assertEqual(metadata["upload_date"], "2024-01-01")


class VectorStoreSearchTests(TestCase):
    """Tests for semantic search."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = _make_config(self.temp_dir)
        # Index some test data
        embedding_result = _make_embedding_result(num_embeddings=3)
        VectorStoreService.index_embeddings(embedding_result, config=self.config)

    def tearDown(self):
        VectorStoreService.reset_client_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_search_returns_results(self):
        query_embedding = [0.1] * 768
        result = VectorStoreService.search(
            query_embedding, k=3, config=self.config
        )

        self.assertIsInstance(result, SearchResult)
        self.assertGreater(result.total_hits, 0)
        self.assertLessEqual(result.total_hits, 3)
        self.assertGreater(result.search_time_seconds, 0)

    def test_search_hits_have_scores(self):
        query_embedding = [0.1] * 768
        result = VectorStoreService.search(
            query_embedding, k=3, config=self.config
        )

        for hit in result.hits:
            self.assertGreaterEqual(hit.score, 0.0)
            self.assertLessEqual(hit.score, 1.0)
            self.assertTrue(hit.chunk_id)
            self.assertTrue(hit.document_id)

    def test_search_with_metadata_filter(self):
        query_embedding = [0.1] * 768
        result = VectorStoreService.search(
            query_embedding,
            k=10,
            config=self.config,
            where={"document_id": "doc-123"},
        )
        self.assertGreater(result.total_hits, 0)
        for hit in result.hits:
            self.assertEqual(hit.metadata.get("document_id"), "doc-123")

    def test_search_nonexistent_document_returns_empty(self):
        query_embedding = [0.1] * 768
        result = VectorStoreService.search(
            query_embedding,
            k=10,
            config=self.config,
            where={"document_id": "nonexistent"},
        )
        self.assertEqual(result.total_hits, 0)

    def test_search_empty_embedding_raises(self):
        with self.assertRaises(VectorStoreSearchError):
            VectorStoreService.search([], config=self.config)

    def test_search_nonexistent_collection_returns_empty(self):
        config = VectorStoreConfig(
            persist_directory=self.temp_dir,
            collection_name="nonexistent_collection",
            batch_size=100,
            search_k=10,
            similarity_threshold=0.0,
            max_results=50,
        )
        result = VectorStoreService.search(
            [0.1] * 768, config=config
        )
        self.assertEqual(result.total_hits, 0)

    def test_search_respects_k_limit(self):
        query_embedding = [0.1] * 768
        result = VectorStoreService.search(
            query_embedding, k=1, config=self.config
        )
        self.assertLessEqual(result.total_hits, 1)

    def test_similarity_threshold_filters_results(self):
        config = VectorStoreConfig(
            persist_directory=self.temp_dir,
            collection_name="test_collection",
            batch_size=100,
            search_k=10,
            similarity_threshold=0.99,  # Very high threshold
            max_results=50,
        )
        # Use a very different embedding to ensure low similarity
        query_embedding = [-0.9] * 768
        result = VectorStoreService.search(
            query_embedding, config=config
        )
        # Results should be filtered out by threshold
        for hit in result.hits:
            self.assertGreaterEqual(hit.score, 0.99)


class VectorStoreDeletionTests(TestCase):
    """Tests for vector deletion."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = _make_config(self.temp_dir)

    def tearDown(self):
        VectorStoreService.reset_client_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_delete_document_vectors(self):
        # Index first
        embedding_result = _make_embedding_result(num_embeddings=3)
        VectorStoreService.index_embeddings(embedding_result, config=self.config)

        # Verify indexed
        stats = VectorStoreService.get_collection_stats(config=self.config)
        self.assertEqual(stats.total_vectors, 3)

        # Delete
        deleted = VectorStoreService.delete_document_vectors(
            "doc-123", config=self.config
        )
        self.assertEqual(deleted, 3)

        # Verify gone
        stats = VectorStoreService.get_collection_stats(config=self.config)
        self.assertEqual(stats.total_vectors, 0)

    def test_delete_nonexistent_document_returns_zero(self):
        # Create the collection first
        embedding_result = _make_embedding_result(num_embeddings=1)
        VectorStoreService.index_embeddings(embedding_result, config=self.config)

        deleted = VectorStoreService.delete_document_vectors(
            "nonexistent", config=self.config
        )
        self.assertEqual(deleted, 0)

    def test_delete_only_target_document(self):
        # Index two documents
        result1 = _make_embedding_result(num_embeddings=2, document_id="doc-A")
        result2 = _make_embedding_result(num_embeddings=2, document_id="doc-B")
        VectorStoreService.index_embeddings(result1, config=self.config)
        VectorStoreService.index_embeddings(result2, config=self.config)

        stats = VectorStoreService.get_collection_stats(config=self.config)
        self.assertEqual(stats.total_vectors, 4)

        # Delete only doc-A
        deleted = VectorStoreService.delete_document_vectors(
            "doc-A", config=self.config
        )
        self.assertEqual(deleted, 2)

        stats = VectorStoreService.get_collection_stats(config=self.config)
        self.assertEqual(stats.total_vectors, 2)


class VectorStoreCollectionTests(TestCase):
    """Tests for collection management."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = _make_config(self.temp_dir)

    def tearDown(self):
        VectorStoreService.reset_client_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_collection_stats_empty(self):
        # Collection doesn't exist yet
        config = VectorStoreConfig(
            persist_directory=self.temp_dir,
            collection_name="nonexistent",
            batch_size=100,
            search_k=10,
            similarity_threshold=0.0,
            max_results=50,
        )
        stats = VectorStoreService.get_collection_stats(config=config)
        self.assertEqual(stats.total_vectors, 0)

    def test_get_collection_stats_after_indexing(self):
        embedding_result = _make_embedding_result(num_embeddings=5)
        VectorStoreService.index_embeddings(embedding_result, config=self.config)

        stats = VectorStoreService.get_collection_stats(config=self.config)
        self.assertEqual(stats.total_vectors, 5)
        self.assertEqual(stats.collection_name, "test_collection")

    def test_health_check_healthy(self):
        result = VectorStoreService.health_check(config=self.config)
        self.assertTrue(result["healthy"])

    def test_health_check_with_bad_path(self):
        config = VectorStoreConfig(
            persist_directory="/nonexistent/path/that/wont/work/abcxyz",
            collection_name="test",
            batch_size=100,
            search_k=10,
            similarity_threshold=0.0,
            max_results=50,
        )
        VectorStoreService.reset_client_cache()
        # ChromaDB might create the directory or might fail — either way
        # we test the health_check doesn't raise
        result = VectorStoreService.health_check(config=config)
        # Result should be either healthy (ChromaDB created dir) or not
        self.assertIn("healthy", result)
