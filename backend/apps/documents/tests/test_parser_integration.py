"""
Integration tests for DocumentProcessingService.run_parser — verifying
the Sprint 5 wiring between apps.documents (Document model, status
machine) and ingestion (the Parser module) end-to-end.
"""

import shutil
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.test import TestCase

from apps.documents.models import Document, DocumentStatus
from apps.documents.services import DocumentProcessingService
from ingestion.exceptions import CorruptedFileError, EncryptedDocumentError, ParserError

User = get_user_model()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_DOCUMENTS_DIR = PROJECT_ROOT / "dataset" / "sample_documents"


class RunParserIntegrationTests(TestCase):
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

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)

    def test_run_parser_transitions_ready_for_parsing_to_parsed(self):
        document = self._make_document("sample.txt", "txt")

        DocumentProcessingService.run_parser(document)

        self.assertEqual(document.status, DocumentStatus.PARSED)
        self.assertEqual(document.processing_stage, DocumentStatus.PARSED)

    def test_run_parser_persists_parser_metadata(self):
        document = self._make_document("sample.pdf", "pdf")

        DocumentProcessingService.run_parser(document)

        self.assertIn("metadata", document.parser_metadata)
        self.assertEqual(document.parser_metadata["metadata"]["parser_used"], "PdfParser")
        self.assertEqual(document.page_count, 1)

    def test_run_parser_reflects_in_database_after_reload(self):
        document = self._make_document("sample.csv", "csv")
        DocumentProcessingService.run_parser(document)

        reloaded = Document.objects.get(pk=document.pk)
        self.assertEqual(reloaded.status, DocumentStatus.PARSED)
        self.assertIn("metadata", reloaded.parser_metadata)

    def test_run_parser_transitions_to_failed_on_corrupted_file(self):
        document = self._make_document("corrupted.pdf", "pdf")

        with self.assertRaises(ParserError):
            DocumentProcessingService.run_parser(document)

        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertEqual(document.processing_stage, DocumentStatus.PARSING)
        self.assertTrue(document.error_message)

    def test_run_parser_transitions_to_failed_on_encrypted_pdf(self):
        document = self._make_document("encrypted.pdf", "pdf")

        with self.assertRaises(EncryptedDocumentError):
            DocumentProcessingService.run_parser(document)

        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertIn("password-protected", document.error_message)

    def test_run_parser_returns_parsed_document_for_chunker(self):
        document = self._make_document("sample.docx", "docx")

        parsed_document = DocumentProcessingService.run_parser(document)

        self.assertEqual(parsed_document.document_id, str(document.id))
        self.assertGreater(len(parsed_document.text), 0)
