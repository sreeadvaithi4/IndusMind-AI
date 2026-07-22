"""Unit tests for the XLSX parser."""

import uuid

from django.test import TestCase

from ingestion.exceptions import CorruptedFileError
from ingestion.parsers.xlsx_parser import XlsxParser
from ingestion.tests.conftest_paths import sample_path


class XlsxParserTests(TestCase):
    def setUp(self):
        self.parser = XlsxParser()
        self.document_id = str(uuid.uuid4())

    def test_parses_valid_xlsx_and_extracts_worksheet(self):
        result = self.parser.parse(sample_path("sample.xlsx"), self.document_id)
        self.assertIn("Readings", result.text)

    def test_extracts_table_headers(self):
        result = self.parser.parse(sample_path("sample.xlsx"), self.document_id)
        headers = result.tables[0][0]
        self.assertEqual(headers, ["sensor_id", "reading", "unit"])

    def test_page_count_matches_worksheet_count(self):
        result = self.parser.parse(sample_path("sample.xlsx"), self.document_id)
        self.assertEqual(result.metadata.page_count, 1)

    def test_raises_corrupted_file_error_for_invalid_xlsx(self):
        with self.assertRaises(CorruptedFileError):
            self.parser.parse(sample_path("corrupted.pdf"), self.document_id)
