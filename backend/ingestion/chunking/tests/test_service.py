"""
Unit tests for DocumentChunkerService — the top-level orchestration
facade. Covers the sprint's required scenarios: small document, large
document, table document, OCR document, empty document, invalid input.
"""

from django.test import TestCase

from ingestion.chunking.config import ChunkingConfig
from ingestion.chunking.exceptions import ChunkingError, EmptyDocumentError
from ingestion.chunking.result import ChunkType
from ingestion.chunking.service import DocumentChunkerService
from ingestion.result import DocumentMetadata, OcrInfo, ParsedDocument


def _make_parsed_document(text="", tables=None, ocr=None, parser_used="PdfParser"):
    return ParsedDocument(
        document_id="doc-123",
        text=text,
        metadata=DocumentMetadata(parser_used=parser_used),
        tables=tables or [],
        ocr=ocr or OcrInfo(),
    )


class DocumentChunkerServiceSmallDocumentTests(TestCase):
    def test_chunks_small_document_into_single_chunk(self):
        parsed_document = _make_parsed_document(text="A short document with one paragraph.")

        collection = DocumentChunkerService.chunk_document(
            parsed_document, filename="report.pdf"
        )

        self.assertEqual(collection.total_chunks, 1)
        self.assertEqual(collection.chunks[0].chunk_type, ChunkType.TEXT)
        self.assertEqual(collection.chunks[0].metadata.filename, "report.pdf")
        self.assertEqual(collection.chunks[0].metadata.document_id, "doc-123")

    def test_chunk_ids_are_sequential_and_document_scoped(self):
        parsed_document = _make_parsed_document(
            text="Paragraph one.\n\nParagraph two.\n\nParagraph three."
        )
        collection = DocumentChunkerService.chunk_document(parsed_document, filename="x.txt")

        for index, chunk in enumerate(collection.chunks, start=1):
            self.assertEqual(chunk.chunk_id, f"doc-123_chunk_{index:04d}")
            self.assertEqual(chunk.chunk_number, index)

    def test_word_and_character_counts_are_populated(self):
        parsed_document = _make_parsed_document(text="Five simple words here now.")
        collection = DocumentChunkerService.chunk_document(parsed_document, filename="x.txt")

        chunk = collection.chunks[0]
        self.assertEqual(chunk.word_count, 5)
        self.assertEqual(chunk.character_count, len(chunk.text))

    def test_total_chunks_metadata_is_backfilled_correctly(self):
        config = ChunkingConfig(chunk_size=30, chunk_overlap=0, max_chunk_length=40)
        text = "\n\n".join(f"Paragraph {i} content here." for i in range(10))
        parsed_document = _make_parsed_document(text=text)

        collection = DocumentChunkerService.chunk_document(
            parsed_document, config=config, filename="x.txt"
        )

        for chunk in collection.chunks:
            self.assertEqual(chunk.metadata.total_chunks, collection.total_chunks)


class DocumentChunkerServiceLargeDocumentTests(TestCase):
    def test_chunks_large_document_into_many_chunks(self):
        config = ChunkingConfig(chunk_size=200, chunk_overlap=20, max_chunk_length=300)
        paragraphs = [
            f"This is paragraph number {i} of a very large industrial maintenance "
            f"report describing turbine inspection procedures in detail."
            for i in range(200)
        ]
        text = "\n\n".join(paragraphs)
        parsed_document = _make_parsed_document(text=text)

        collection = DocumentChunkerService.chunk_document(
            parsed_document, config=config, filename="large_report.pdf"
        )

        self.assertGreater(collection.total_chunks, 10)
        # No chunk should wildly exceed the configured ceiling.
        for chunk in collection.chunks:
            self.assertLessEqual(chunk.character_count, config.max_chunk_length + config.chunk_overlap + 50)

    def test_large_document_chunking_completes_and_records_timing(self):
        config = ChunkingConfig(chunk_size=500, chunk_overlap=50)
        text = "\n\n".join(f"Sentence about topic {i}. More detail follows here." for i in range(500))
        parsed_document = _make_parsed_document(text=text)

        collection = DocumentChunkerService.chunk_document(
            parsed_document, config=config, filename="huge.txt"
        )

        self.assertIsNotNone(collection.processing)
        self.assertGreaterEqual(collection.processing.duration_seconds, 0)


class DocumentChunkerServiceTableDocumentTests(TestCase):
    def test_table_only_document_produces_table_chunks(self):
        table = [["id", "name"], ["1", "Compressor A"], ["2", "Turbine B"]]
        parsed_document = _make_parsed_document(text="", tables=[table])

        collection = DocumentChunkerService.chunk_document(
            parsed_document, filename="data.csv"
        )

        self.assertEqual(collection.text_chunk_count, 0)
        self.assertEqual(collection.table_chunk_count, 1)
        self.assertEqual(collection.chunks[0].chunk_type, ChunkType.TABLE)

    def test_document_with_text_and_tables_produces_both_chunk_types(self):
        table = [["id", "value"], ["1", "100"]]
        parsed_document = _make_parsed_document(
            text="Some narrative text describing the data below.", tables=[table]
        )

        collection = DocumentChunkerService.chunk_document(
            parsed_document, filename="mixed.docx"
        )

        self.assertGreaterEqual(collection.text_chunk_count, 1)
        self.assertEqual(collection.table_chunk_count, 1)

    def test_multiple_tables_each_produce_chunks(self):
        table_a = [["a"], ["1"]]
        table_b = [["b"], ["2"]]
        parsed_document = _make_parsed_document(text="", tables=[table_a, table_b])

        collection = DocumentChunkerService.chunk_document(
            parsed_document, filename="two_tables.xlsx"
        )

        self.assertEqual(collection.table_chunk_count, 2)
        sections = {chunk.section_title for chunk in collection.chunks}
        self.assertEqual(sections, {"Table 1", "Table 2"})


class DocumentChunkerServiceOcrDocumentTests(TestCase):
    def test_ocr_used_flag_propagates_to_chunk_metadata(self):
        parsed_document = _make_parsed_document(
            text="Text recovered via OCR from a scanned page.",
            ocr=OcrInfo(used=True, engine="tesseract", pages_ocred=[1]),
        )

        collection = DocumentChunkerService.chunk_document(
            parsed_document, filename="scanned.pdf"
        )

        self.assertTrue(collection.chunks[0].metadata.ocr_used)

    def test_non_ocr_document_has_ocr_used_false(self):
        parsed_document = _make_parsed_document(text="Regular extracted text.")
        collection = DocumentChunkerService.chunk_document(parsed_document, filename="x.pdf")
        self.assertFalse(collection.chunks[0].metadata.ocr_used)


class DocumentChunkerServiceEmptyDocumentTests(TestCase):
    def test_raises_empty_document_error_for_no_text_and_no_tables(self):
        parsed_document = _make_parsed_document(text="")
        with self.assertRaises(EmptyDocumentError):
            DocumentChunkerService.chunk_document(parsed_document, filename="empty.txt")

    def test_raises_empty_document_error_for_whitespace_only_text(self):
        parsed_document = _make_parsed_document(text="   \n\n\t  ")
        with self.assertRaises(EmptyDocumentError):
            DocumentChunkerService.chunk_document(parsed_document, filename="whitespace.txt")


class DocumentChunkerServiceInvalidInputTests(TestCase):
    def test_raises_chunking_error_for_none_input(self):
        with self.assertRaises(ChunkingError):
            DocumentChunkerService.chunk_document(None, filename="x.txt")

    def test_raises_chunking_error_for_malformed_table(self):
        parsed_document = _make_parsed_document(text="some text", tables=["not-rows"])
        with self.assertRaises(ChunkingError):
            DocumentChunkerService.chunk_document(parsed_document, filename="x.txt")

    def test_wraps_unexpected_exceptions_as_chunking_error(self):
        from unittest import mock

        parsed_document = _make_parsed_document(text="valid text content")
        with mock.patch(
            "ingestion.chunking.service.split_into_sections",
            side_effect=RuntimeError("unexpected crash"),
        ):
            with self.assertRaises(ChunkingError):
                DocumentChunkerService.chunk_document(parsed_document, filename="x.txt")


class DocumentChunkerServiceFilenameFallbackTests(TestCase):
    def test_uses_placeholder_filename_when_none_provided(self):
        parsed_document = _make_parsed_document(text="Some content.")
        collection = DocumentChunkerService.chunk_document(parsed_document)
        self.assertIn("doc-123", collection.chunks[0].metadata.filename)
