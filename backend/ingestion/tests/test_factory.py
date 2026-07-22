"""Unit tests for the parser factory/registry."""

from django.test import TestCase

from ingestion.base import BaseParser, ParserRegistry
from ingestion.exceptions import UnsupportedFileTypeError
from ingestion.factory import get_parser_for_extension, get_supported_extensions
from ingestion.parsers.csv_parser import CsvParser
from ingestion.parsers.docx_parser import DocParser, DocxParser
from ingestion.parsers.pdf_parser import PdfParser
from ingestion.parsers.txt_parser import TxtParser
from ingestion.parsers.xlsx_parser import XlsxParser


class ParserFactoryTests(TestCase):
    def test_returns_correct_parser_for_each_supported_extension(self):
        expectations = {
            "pdf": PdfParser,
            "docx": DocxParser,
            "doc": DocParser,
            "txt": TxtParser,
            "csv": CsvParser,
            "xlsx": XlsxParser,
        }
        for extension, expected_class in expectations.items():
            with self.subTest(extension=extension):
                parser = get_parser_for_extension(extension)
                self.assertIsInstance(parser, expected_class)

    def test_is_case_insensitive(self):
        parser = get_parser_for_extension("PDF")
        self.assertIsInstance(parser, PdfParser)

    def test_accepts_extension_with_leading_dot(self):
        parser = get_parser_for_extension(".pdf")
        self.assertIsInstance(parser, PdfParser)

    def test_raises_unsupported_file_type_error_for_unknown_extension(self):
        with self.assertRaises(UnsupportedFileTypeError):
            get_parser_for_extension("exe")

    def test_supported_extensions_includes_all_six_formats(self):
        supported = get_supported_extensions()
        for extension in ("pdf", "docx", "doc", "txt", "csv", "xlsx"):
            self.assertIn(extension, supported)


class ParserRegistryTests(TestCase):
    def test_register_requires_extension_attribute(self):
        class NoExtensionParser(BaseParser):
            def parse(self, file_path, document_id):
                raise NotImplementedError

        with self.assertRaises(ValueError):
            ParserRegistry.register(NoExtensionParser)
