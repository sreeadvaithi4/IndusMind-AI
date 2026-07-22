"""
Integration tests for the Embedding Generator with the document pipeline.

Tests the full flow: Document → run_parser → run_chunker → run_embedding_generator
using mocked API calls to Google Gemini (no real API key needed).
"""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files import File
from django.test import TestCase, override_settings

from apps.documents.models import Document, DocumentStatus, EmbeddingStatus
from apps.documents.services import DocumentProcessingService, DocumentStatusService

User = get_user_model()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_DOCUMENTS_DIR = PROJECT_ROOT / "dataset" / "sample_documents"


@override_settings(GOOGLE_API_KEY="test-api-key-for-integration")
class EmbeddingPipelineIntegrationTests(TestCase):
    """
    Full pipeline integration: Upload → Parse → Chunk → Embed.

    These tests exercise the real Parser and Chunker against sample
    documents, then mock only the external API call to Google Gemini
    for the embedding step.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

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
    def test_full_pipeline_txt_document(self, mock_create_model):
        """Test full pipeline from READY_FOR_PARSING to EMBEDDED for a TXT file."""
        mock_model = MagicMock()
        # Return 768-dim vectors for however many chunks the real chunker produces
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.1] * 768 for _ in texts]
        )
        mock_create_model.return_value = mock_model

        document = self._make_document("sample.txt", "txt")
        self.assertEqual(document.status, DocumentStatus.READY_FOR_PARSING)

        # Run parser
        parsed_document = DocumentProcessingService.run_parser(document)
        self.assertEqual(document.status, DocumentStatus.PARSED)

        # Run chunker
        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)
        self.assertEqual(document.status, DocumentStatus.CHUNKED)
        self.assertGreater(chunk_collection.total_chunks, 0)

        # Run embedding generator
        embedding_result = DocumentProcessingService.run_embedding_generator(
            document, chunk_collection
        )
        self.assertEqual(document.status, DocumentStatus.EMBEDDED)
        self.assertEqual(document.embedding_status, EmbeddingStatus.COMPLETED)
        self.assertEqual(
            embedding_result.successful_count, chunk_collection.total_chunks
        )
        self.assertIsNotNone(document.embedding_metadata)
        self.assertIn("total_embeddings", document.embedding_metadata)

        # Verify percentage progression
        self.assertEqual(document.processing_percentage, 85)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_full_pipeline_csv_document(self, mock_create_model):
        """Test pipeline for a CSV file (table-aware chunking)."""
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.2] * 768 for _ in texts]
        )
        mock_create_model.return_value = mock_model

        document = self._make_document("sample.csv", "csv")

        parsed_document = DocumentProcessingService.run_parser(document)
        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)
        embedding_result = DocumentProcessingService.run_embedding_generator(
            document, chunk_collection
        )

        self.assertEqual(document.status, DocumentStatus.EMBEDDED)
        self.assertEqual(embedding_result.successful_count, chunk_collection.total_chunks)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_embedding_failure_transitions_document_to_failed(self, mock_create_model):
        """When ALL embeddings fail, document should transition to FAILED."""
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = Exception(
            "Invalid API key (401 Unauthenticated)"
        )
        mock_create_model.return_value = mock_model

        document = self._make_document("sample.txt", "txt")

        parsed_document = DocumentProcessingService.run_parser(document)
        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)

        from rag.embeddings.exceptions import EmbeddingError

        with self.assertRaises(EmbeddingError):
            DocumentProcessingService.run_embedding_generator(
                document, chunk_collection
            )

        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertEqual(document.processing_stage, DocumentStatus.EMBEDDING)
        self.assertEqual(document.embedding_status, EmbeddingStatus.FAILED)
        self.assertIn("failed", document.error_message.lower())

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_embedding_metadata_persisted_on_success(self, mock_create_model):
        """Verify embedding_metadata is stored on the Document model."""
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.3] * 768 for _ in texts]
        )
        mock_create_model.return_value = mock_model

        document = self._make_document("sample.txt", "txt")

        parsed_document = DocumentProcessingService.run_parser(document)
        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)
        DocumentProcessingService.run_embedding_generator(document, chunk_collection)

        document.refresh_from_db()
        self.assertIsInstance(document.embedding_metadata, dict)
        self.assertIn("embedding_model", document.embedding_metadata)
        self.assertIn("embedding_dimension", document.embedding_metadata)
        self.assertEqual(document.embedding_metadata["embedding_dimension"], 768)
        self.assertEqual(
            document.embedding_metadata["embedding_model"], "models/embedding-001"
        )
        self.assertIn("processing", document.embedding_metadata)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_embedding_preserves_chunk_metadata(self, mock_create_model):
        """Each ChunkEmbedding should carry through the original chunk metadata."""
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.4] * 768 for _ in texts]
        )
        mock_create_model.return_value = mock_model

        document = self._make_document("sample.txt", "txt")

        parsed_document = DocumentProcessingService.run_parser(document)
        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)
        embedding_result = DocumentProcessingService.run_embedding_generator(
            document, chunk_collection
        )

        for emb in embedding_result.embeddings:
            self.assertIn("document_id", emb.metadata)
            self.assertIn("filename", emb.metadata)
            self.assertIn("parser_used", emb.metadata)
            self.assertEqual(emb.metadata["document_id"], str(document.id))

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)
