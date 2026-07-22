"""
Integration tests for DocumentProcessingService.run_chunker — verifying
the Sprint 6 wiring between apps.documents (Document model, status
machine) and ingestion.chunking (the Chunker module) end-to-end,
consuming real ParsedDocument objects produced by the real Parser
(Sprint 5) against the sample documents dataset.
"""

import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.test import TestCase

from apps.documents.models import Document, DocumentStatus
from apps.documents.services import DocumentProcessingService
from ingestion.chunking.exceptions import ChunkingError, EmptyDocumentError

User = get_user_model()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_DOCUMENTS_DIR = PROJECT_ROOT / "dataset" / "sample_documents"


class RunChunkerIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def _make_and_parse_document(self, sample_filename, extension):
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

        parsed_document = DocumentProcessingService.run_parser(document)
        return document, parsed_document

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)

    def test_run_chunker_transitions_parsed_to_chunked(self):
        document, parsed_document = self._make_and_parse_document("sample.pdf", "pdf")

        DocumentProcessingService.run_chunker(document, parsed_document)

        self.assertEqual(document.status, DocumentStatus.CHUNKED)
        self.assertEqual(document.processing_stage, DocumentStatus.CHUNKED)

    def test_run_chunker_persists_chunk_count_and_metadata(self):
        document, parsed_document = self._make_and_parse_document("sample.docx", "docx")

        DocumentProcessingService.run_chunker(document, parsed_document)

        self.assertGreater(document.chunk_count, 0)
        self.assertIsNotNone(document.chunking_time_seconds)
        self.assertIn("total_chunks", document.chunker_metadata)
        self.assertEqual(document.chunker_metadata["total_chunks"], document.chunk_count)

    def test_run_chunker_reflects_in_database_after_reload(self):
        document, parsed_document = self._make_and_parse_document("sample.txt", "txt")
        DocumentProcessingService.run_chunker(document, parsed_document)

        reloaded = Document.objects.get(pk=document.pk)
        self.assertEqual(reloaded.status, DocumentStatus.CHUNKED)
        self.assertGreater(reloaded.chunk_count, 0)

    def test_run_chunker_handles_table_document(self):
        document, parsed_document = self._make_and_parse_document("sample.csv", "csv")

        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)

        self.assertGreater(chunk_collection.table_chunk_count, 0)
        self.assertEqual(document.status, DocumentStatus.CHUNKED)

    def test_run_chunker_handles_xlsx_document(self):
        document, parsed_document = self._make_and_parse_document("sample.xlsx", "xlsx")

        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)

        self.assertGreater(chunk_collection.total_chunks, 0)

    def test_run_chunker_returns_chunk_collection_for_embedding_generator(self):
        document, parsed_document = self._make_and_parse_document("sample.pdf", "pdf")

        chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)

        self.assertEqual(chunk_collection.document_id, str(document.id))
        self.assertGreater(len(chunk_collection.chunks), 0)
        for chunk in chunk_collection.chunks:
            self.assertEqual(chunk.metadata.parser_used, "PdfParser")
            self.assertEqual(chunk.metadata.filename, document.original_filename)

    def test_run_chunker_transitions_to_failed_on_empty_parsed_content(self):
        document, parsed_document = self._make_and_parse_document("sample.txt", "txt")
        # Simulate a parsed document with no usable content reaching
        # the chunker (e.g. a hypothetical future format that extracts
        # nothing) without touching the Parser itself.
        parsed_document.text = ""
        parsed_document.tables = []

        with self.assertRaises(EmptyDocumentError):
            DocumentProcessingService.run_chunker(document, parsed_document)

        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertEqual(document.processing_stage, DocumentStatus.CHUNKING)
        self.assertTrue(document.error_message)

    def test_full_parser_to_chunker_flow_for_every_supported_format(self):
        cases = [
            ("sample.pdf", "pdf"),
            ("sample.docx", "docx"),
            ("sample.txt", "txt"),
            ("sample.csv", "csv"),
            ("sample.xlsx", "xlsx"),
        ]
        for filename, extension in cases:
            with self.subTest(extension=extension):
                document, parsed_document = self._make_and_parse_document(filename, extension)
                chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)

                self.assertEqual(document.status, DocumentStatus.CHUNKED)
                self.assertGreater(chunk_collection.total_chunks, 0)
