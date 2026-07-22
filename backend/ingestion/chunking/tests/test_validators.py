"""Unit tests for chunking pre-validation."""

from django.test import TestCase

from ingestion.chunking.exceptions import CorruptedParsedContentError, EmptyDocumentError
from ingestion.chunking.validators import validate_parsed_document
from ingestion.result import DocumentMetadata, ParsedDocument


def _make_parsed_document(text="", tables=None):
    return ParsedDocument(
        document_id="doc-1",
        text=text,
        metadata=DocumentMetadata(),
        tables=tables or [],
    )


class ValidateParsedDocumentTests(TestCase):
    def test_raises_for_none_input(self):
        with self.assertRaises(CorruptedParsedContentError):
            validate_parsed_document(None)

    def test_raises_for_empty_text_and_no_tables(self):
        with self.assertRaises(EmptyDocumentError):
            validate_parsed_document(_make_parsed_document(text=""))

    def test_raises_for_whitespace_only_text_and_no_tables(self):
        with self.assertRaises(EmptyDocumentError):
            validate_parsed_document(_make_parsed_document(text="   \n\n  "))

    def test_passes_for_text_only(self):
        validate_parsed_document(_make_parsed_document(text="Some real content."))

    def test_passes_for_tables_only_with_no_text(self):
        validate_parsed_document(
            _make_parsed_document(text="", tables=[[["a", "b"], ["1", "2"]]])
        )

    def test_raises_for_malformed_table(self):
        document = _make_parsed_document(text="some text", tables=["not-a-list-of-rows"])
        with self.assertRaises(CorruptedParsedContentError):
            validate_parsed_document(document)
