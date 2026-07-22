"""Unit tests for the PDF parser."""

import uuid

from django.test import TestCase

from ingestion.exceptions import CorruptedFileError, EncryptedDocumentError
from ingestion.parsers.pdf_parser import PdfParser
from ingestion.tests.conftest_paths import sample_path


class PdfParserTests(TestCase):
    def setUp(self):
        self.parser = PdfParser()
        self.document_id = str(uuid.uuid4())

    def test_parses_valid_pdf_and_extracts_text(self):
        result = self.parser.parse(sample_path("sample.pdf"), self.document_id)

        self.assertIn("IndusMind AI Sample PDF Document", result.text)
        self.assertEqual(result.document_id, self.document_id)

    def test_extracts_page_count(self):
        result = self.parser.parse(sample_path("sample.pdf"), self.document_id)
        self.assertEqual(result.metadata.page_count, 1)

    def test_extracts_title_and_author_metadata(self):
        result = self.parser.parse(sample_path("sample.pdf"), self.document_id)
        self.assertEqual(result.metadata.title, "Sample PDF")
        self.assertEqual(result.metadata.author, "IndusMind AI Test Suite")

    def test_sets_parser_used(self):
        result = self.parser.parse(sample_path("sample.pdf"), self.document_id)
        self.assertEqual(result.metadata.parser_used, "PdfParser")

    def test_computes_character_and_word_counts(self):
        result = self.parser.parse(sample_path("sample.pdf"), self.document_id)
        self.assertGreater(result.metadata.character_count, 0)
        self.assertGreater(result.metadata.word_count, 0)

    def test_records_processing_timing(self):
        result = self.parser.parse(sample_path("sample.pdf"), self.document_id)
        self.assertIsNotNone(result.processing)
        self.assertGreaterEqual(result.processing.duration_seconds, 0)

    def test_raises_corrupted_file_error_for_invalid_pdf(self):
        with self.assertRaises(CorruptedFileError):
            self.parser.parse(sample_path("corrupted.pdf"), self.document_id)

    def test_raises_encrypted_document_error_for_password_protected_pdf(self):
        with self.assertRaises(EncryptedDocumentError):
            self.parser.parse(sample_path("encrypted.pdf"), self.document_id)
