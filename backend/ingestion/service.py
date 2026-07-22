"""
Top-level document parsing service.

`DocumentParserService.parse_document` is the single entry point
`apps.documents.services.DocumentProcessingService.run_parser` calls.
It resolves the correct parser via the factory, runs it, translates
any `ParserError` into a clear log entry, and returns the standardized
`ParsedDocument`. It does not know about Django `Document` model status
transitions — that orchestration remains the responsibility of
`DocumentProcessingService`, keeping this module fully reusable by
anything that just wants "parse this file" (e.g. a future CLI tool or
management command) without pulling in the Document model.
"""

import logging
import time

from ingestion.exceptions import ParserError
from ingestion.factory import get_parser_for_extension
from ingestion.result import ParsedDocument
from ingestion.validators import validate_file_exists_on_disk

logger = logging.getLogger("ingestion")


class DocumentParserService:
    """Stateless facade over the parser factory + registered parsers."""

    @staticmethod
    def parse_document(file_path: str, extension: str, document_id: str) -> ParsedDocument:
        """
        Parses the file at `file_path` using the parser registered for
        `extension`.

        Args:
            file_path: absolute filesystem path to the stored file.
            extension: lowercase file extension (no dot), e.g. "pdf".
            document_id: string UUID of the owning Document, threaded
                through into the returned ParsedDocument.

        Returns:
            ParsedDocument

        Raises:
            ingestion.exceptions.ParserError (or a subclass): on any
                validation or parsing failure. Callers are expected to
                catch this base class.
        """
        logger.info(
            "Starting parse: document_id=%s extension=%s path=%s",
            document_id,
            extension,
            file_path,
        )
        start_time = time.monotonic()

        try:
            validate_file_exists_on_disk(file_path)
            parser = get_parser_for_extension(extension)
            parsed_document = parser.parse(file_path, document_id)
        except ParserError:
            elapsed = time.monotonic() - start_time
            logger.error(
                "Parse failed: document_id=%s extension=%s elapsed=%.3fs",
                document_id,
                extension,
                elapsed,
                exc_info=True,
            )
            raise
        except Exception as exc:
            # Any library-specific exception that a format parser did
            # not already translate into a ParserError subclass is
            # still surfaced as a ParserError, so
            # DocumentProcessingService.run_parser never has to know
            # about PyMuPDF/python-docx/pandas/openpyxl exception types.
            elapsed = time.monotonic() - start_time
            logger.error(
                "Unexpected parser failure: document_id=%s extension=%s elapsed=%.3fs",
                document_id,
                extension,
                elapsed,
                exc_info=True,
            )
            raise ParserError(
                f"Unexpected error while parsing document {document_id}: {exc}"
            ) from exc

        elapsed = time.monotonic() - start_time
        logger.info(
            "Finished parse: document_id=%s extension=%s elapsed=%.3fs "
            "characters=%d words=%d ocr_used=%s",
            document_id,
            extension,
            elapsed,
            parsed_document.metadata.character_count,
            parsed_document.metadata.word_count,
            parsed_document.ocr.used,
        )

        return parsed_document
