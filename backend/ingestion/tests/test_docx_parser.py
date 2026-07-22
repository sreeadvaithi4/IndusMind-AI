"""Unit tests for the DOCX parser."""

import uuid

from django.test import TestCase

from ingestion.exceptions import CorruptedFileError
from ingestion.parsers.docx_parser import DocParser, DocxParser
from ingestion.tests.conftest_paths import sample_path


class DocxParserTests(TestCase):
    def setUp(self):
        self.parser = DocxParser()
        self.document_id = str(uuid.uuid4())

    def test_parses_valid_docx_and_extracts_paragraphs(self):
        result = self.parser.parse(sample_path("sample.docx"), self.document_id)
        self.assertIn("This is a sample DOCX document", result.text)

    def test_extracts_table(self):
        result = self.parser.parse(sample_path("sample.docx"), self.document_id)
        self.assertEqual(len(result.tables), 1)
        self.assertIn(["Metric", "Value"], result.tables[0])

    def test_extracts_title_and_author(self):
        result = self.parser.parse(sample_path("sample.docx"), self.document_id)
        self.assertEqual(result.metadata.title, "Sample DOCX")
        self.assertEqual(result.metadata.author, "IndusMind AI Test Suite")

    def test_page_count_is_none_with_warning(self):
        result = self.parser.parse(sample_path("sample.docx"), self.document_id)
        self.assertIsNone(result.metadata.page_count)
        self.assertTrue(any("page count" in w.lower() for w in result.processing.warnings))

    def test_raises_corrupted_file_error_for_invalid_docx(self):
        with self.assertRaises(CorruptedFileError):
            self.parser.parse(sample_path("corrupted.pdf"), self.document_id)


class DocParserTests(TestCase):
    def test_doc_parser_raises_clear_unsupported_error(self):
        parser = DocParser()
        with self.assertRaises(CorruptedFileError) as ctx:
            parser.parse(sample_path("sample.docx"), str(uuid.uuid4()))
        self.assertIn(".docx", str(ctx.exception))
