"""Unit tests for the CSV parser."""

import uuid

from django.test import TestCase

from ingestion.exceptions import CorruptedFileError
from ingestion.parsers.csv_parser import CsvParser
from ingestion.tests.conftest_paths import sample_path


class CsvParserTests(TestCase):
    def setUp(self):
        self.parser = CsvParser()
        self.document_id = str(uuid.uuid4())

    def test_parses_valid_csv_and_extracts_headers(self):
        result = self.parser.parse(sample_path("sample.csv"), self.document_id)
        headers = result.tables[0][0]
        self.assertEqual(
            headers, ["equipment_id", "equipment_name", "failure_mode", "downtime_hours"]
        )

    def test_extracts_rows(self):
        result = self.parser.parse(sample_path("sample.csv"), self.document_id)
        # 1 header row + 3 data rows
        self.assertEqual(len(result.tables[0]), 4)

    def test_text_includes_statistics_summary(self):
        result = self.parser.parse(sample_path("sample.csv"), self.document_id)
        self.assertIn("Rows: 3", result.text)
        self.assertIn("Columns: 4", result.text)

    def test_raises_corrupted_file_error_for_invalid_csv(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(b"")
            tmp_path = tmp.name

        try:
            with self.assertRaises(CorruptedFileError):
                self.parser.parse(tmp_path, self.document_id)
        finally:
            import os

            os.remove(tmp_path)
