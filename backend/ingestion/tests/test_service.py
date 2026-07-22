"""Unit tests for DocumentParserService (the top-level orchestration facade)."""

import uuid

from django.test import TestCase

from ingestion.exceptions import FileNotFoundOnDiskError, ParserError, UnsupportedFileTypeError
from ingestion.service import DocumentParserService
from ingestion.tests.conftest_paths import sample_path


class DocumentParserServiceTests(TestCase):
    def test_parses_supported_file_successfully(self):
        result = DocumentParserService.parse_document(
            file_path=sample_path("sample.txt"),
            extension="txt",
            document_id=str(uuid.uuid4()),
        )
        self.assertGreater(len(result.text), 0)

    def test_raises_unsupported_file_type_error_for_unknown_extension(self):
        with self.assertRaises(UnsupportedFileTypeError):
            DocumentParserService.parse_document(
                file_path=sample_path("sample.txt"),
                extension="exe",
                document_id=str(uuid.uuid4()),
            )

    def test_raises_file_not_found_error_for_missing_file(self):
        with self.assertRaises(FileNotFoundOnDiskError):
            DocumentParserService.parse_document(
                file_path="/definitely/not/real.pdf",
                extension="pdf",
                document_id=str(uuid.uuid4()),
            )

    def test_wraps_unexpected_exceptions_as_parser_error(self):
        from unittest import mock

        with mock.patch(
            "ingestion.service.get_parser_for_extension",
            side_effect=RuntimeError("unexpected library crash"),
        ):
            with self.assertRaises(ParserError):
                DocumentParserService.parse_document(
                    file_path=sample_path("sample.txt"),
                    extension="txt",
                    document_id=str(uuid.uuid4()),
                )
