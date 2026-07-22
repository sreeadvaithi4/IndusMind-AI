"""
PDF parser (PyMuPDF), with OCR fallback for scanned/image-only pages.
"""

from datetime import datetime, timezone

from ingestion.base import BaseParser, ParserRegistry
from ingestion.exceptions import CorruptedFileError, EncryptedDocumentError
from ingestion.ocr import run_ocr_on_pdf, should_attempt_ocr
from ingestion.result import DocumentMetadata, OcrInfo, ParsedDocument, ProcessingInfo
from ingestion.utils import count_characters, count_words, detect_language


def _parse_pdf_datetime(raw_value: str | None) -> str | None:
    """
    PyMuPDF returns PDF date strings like 'D:20240115103000+00'00''.
    Best-effort conversion to ISO 8601; returns the raw string
    unchanged if it doesn't match the expected PDF date format, since
    a non-critical metadata field should never break parsing.
    """
    if not raw_value or not raw_value.startswith("D:"):
        return raw_value or None

    digits = raw_value[2:16]
    try:
        parsed = datetime.strptime(digits, "%Y%m%d%H%M%S")
        return parsed.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return raw_value


@ParserRegistry.register
class PdfParser(BaseParser):
    extension = "pdf"

    def parse(self, file_path: str, document_id: str) -> ParsedDocument:
        started_at = datetime.now(timezone.utc)
        warnings: list[str] = []

        import fitz  # PyMuPDF

        try:
            pdf_document = fitz.open(file_path)
        except fitz.FileDataError as exc:
            raise CorruptedFileError(f"'{file_path}' is not a valid PDF: {exc}") from exc

        try:
            if pdf_document.is_encrypted and not pdf_document.authenticate(""):
                raise EncryptedDocumentError(
                    f"'{file_path}' is password-protected and cannot be parsed "
                    "without credentials."
                )

            page_count = pdf_document.page_count
            page_texts = [page.get_text() for page in pdf_document]
            text = "\n\n".join(page_texts)

            ocr_info = OcrInfo(used=False)
            if should_attempt_ocr(text, page_count):
                ocr_text, ocr_info = run_ocr_on_pdf(file_path, page_count)
                if ocr_info.used and len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                elif not ocr_info.used:
                    warnings.append(
                        f"Text extraction yielded little content and OCR fallback "
                        f"did not run: {ocr_info.reason}"
                    )

            pdf_metadata = pdf_document.metadata or {}
            metadata = DocumentMetadata(
                title=pdf_metadata.get("title") or None,
                author=pdf_metadata.get("author") or None,
                created_at=_parse_pdf_datetime(pdf_metadata.get("creationDate")),
                modified_at=_parse_pdf_datetime(pdf_metadata.get("modDate")),
                language=detect_language(text),
                page_count=page_count,
                extension=self.extension,
                parser_used=self.__class__.__name__,
                ocr_used=ocr_info.used,
                character_count=count_characters(text),
                word_count=count_words(text),
            )
        finally:
            pdf_document.close()

        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - started_at).total_seconds()
        metadata.parsing_time_seconds = duration

        return ParsedDocument(
            document_id=document_id,
            text=text,
            metadata=metadata,
            tables=[],
            images=[],
            ocr=ocr_info,
            processing=ProcessingInfo(
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                warnings=warnings,
            ),
        )
