"""
Integration tests for the ChromaDB Vector Store with the document pipeline.

Tests the full flow: Document → run_parser → run_chunker →
run_embedding_generator → store_in_vector_db using mocked embedding API
and real ChromaDB (temp directory).
"""

import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files import File
from django.test import TestCase, override_settings

from apps.documents.models import Document, DocumentStatus
from apps.documents.services import DocumentProcessingService
from rag.vectorstore.service import VectorStoreService

User = get_user_model()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_DOCUMENTS_DIR = PROJECT_ROOT / "dataset" / "sample_documents"


class VectorStorePipelineIntegrationTests(TestCase):
    """
    Full pipeline integration: Upload → Parse → Chunk → Embed → Store.

    Uses real Parser, Chunker, and ChromaDB; mocks only the external
    Google Gemini API for embedding.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.temp_dir = tempfile.mkdtemp()
        VectorStoreService.reset_client_cache()

    def _make_document(self, sample_filename, extension):
        source_path = SAMPLE_DOCUMENTS_DIR / sample_filename
        document = Document(
            original_filename=sample_filename,
            stored_filename=f"{uuid.uuid4().hex[:8]}_{sample_filename}",
            extension=extension,
            file_size=source_path.stat().st_size,
            uploaded_by=self.user,
            status=DocumentStatus.READY_FOR_PARSING,
            processing_stage=DocumentStatus.READY_FOR_PARSING,
        )
        with open(source_path, "rb") as f:
            document.file.save(sample_filename, File(f), save=True)
        return document

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    @override_settings(GOOGLE_API_KEY="test-api-key")
    def test_full_pipeline_stores_vectors_in_chromadb(self, mock_create_model):
        """Test full pipeline from READY_FOR_PARSING to VECTOR_INDEXED."""
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.1 * (i + 1)] * 768 for i, _ in enumerate(texts)]
        )
        mock_create_model.return_value = mock_model

        from rag.vectorstore.config import VectorStoreConfig

        config = VectorStoreConfig(
            persist_directory=self.temp_dir,
            collection_name="test_pipeline",
            batch_size=100,
            search_k=10,
            similarity_threshold=0.0,
            max_results=50,
        )

        document = self._make_document("sample.txt", "txt")

        # Run parser + chunker + embedding
        parsed_document = DocumentProcessingService.run_parser(document)
        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)
        embedding_result = DocumentProcessingService.run_embedding_generator(
            document, chunk_collection
        )

        # Store in vector DB
        with patch("rag.vectorstore.service.VectorStoreConfig.from_settings", return_value=config):
            indexing_result = DocumentProcessingService.store_in_vector_db(
                document, embedding_result
            )

        self.assertEqual(document.status, DocumentStatus.VECTOR_INDEXED)
        self.assertEqual(document.processing_percentage, 95)
        self.assertGreater(indexing_result.total_indexed, 0)

        # Verify vectors are searchable
        query_embedding = [0.1] * 768
        search_result = VectorStoreService.search(
            query_embedding, k=5, config=config
        )
        self.assertGreater(search_result.total_hits, 0)
        self.assertEqual(
            search_result.hits[0].metadata["document_id"], str(document.id)
        )

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    @override_settings(GOOGLE_API_KEY="test-api-key")
    def test_re_indexing_replaces_old_vectors(self, mock_create_model):
        """Re-running store_in_vector_db replaces existing vectors."""
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.1] * 768 for _ in texts]
        )
        mock_create_model.return_value = mock_model

        from rag.vectorstore.config import VectorStoreConfig

        config = VectorStoreConfig(
            persist_directory=self.temp_dir,
            collection_name="test_reindex",
            batch_size=100,
            search_k=10,
            similarity_threshold=0.0,
            max_results=50,
        )

        document = self._make_document("sample.txt", "txt")

        parsed = DocumentProcessingService.run_parser(document)
        chunks = DocumentProcessingService.run_chunker(document, parsed)
        embs = DocumentProcessingService.run_embedding_generator(document, chunks)

        with patch("rag.vectorstore.service.VectorStoreConfig.from_settings", return_value=config):
            DocumentProcessingService.store_in_vector_db(document, embs)
            stats1 = VectorStoreService.get_collection_stats(config=config)

            # Re-index (simulates document re-processing)
            document.status = DocumentStatus.EMBEDDED
            document.save()
            DocumentProcessingService.store_in_vector_db(document, embs)
            stats2 = VectorStoreService.get_collection_stats(config=config)

        # Count should be the same (upsert, not duplicate)
        self.assertEqual(stats1.total_vectors, stats2.total_vectors)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    @override_settings(GOOGLE_API_KEY="test-api-key")
    def test_document_deletion_removes_vectors(self, mock_create_model):
        """Deleting a document should clean up its ChromaDB vectors."""
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.1] * 768 for _ in texts]
        )
        mock_create_model.return_value = mock_model

        from rag.vectorstore.config import VectorStoreConfig

        config = VectorStoreConfig(
            persist_directory=self.temp_dir,
            collection_name="test_delete",
            batch_size=100,
            search_k=10,
            similarity_threshold=0.0,
            max_results=50,
        )

        document = self._make_document("sample.txt", "txt")
        doc_id = str(document.id)

        parsed = DocumentProcessingService.run_parser(document)
        chunks = DocumentProcessingService.run_chunker(document, parsed)
        embs = DocumentProcessingService.run_embedding_generator(document, chunks)

        with patch("rag.vectorstore.service.VectorStoreConfig.from_settings", return_value=config):
            DocumentProcessingService.store_in_vector_db(document, embs)

            stats = VectorStoreService.get_collection_stats(config=config)
            self.assertGreater(stats.total_vectors, 0)

            # Delete the document (signal should clean up vectors)
            document.delete()

            stats = VectorStoreService.get_collection_stats(config=config)
            self.assertEqual(stats.total_vectors, 0)

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)
        VectorStoreService.reset_client_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
