"""Plain text parser, with encoding detection."""

from datetime import datetime, timezone

from ingestion.base import BaseParser, ParserRegistry
from ingestion.result import DocumentMetadata, OcrInfo, ParsedDocument, ProcessingInfo
from ingestion.utils import count_characters, count_words, decode_with_best_effort, detect_language


@ParserRegistry.register
class TxtParser(BaseParser):
    extension = "txt"

    def parse(self, file_path: str, document_id: str) -> ParsedDocument:
        started_at = datetime.now(timezone.utc)
        warnings: list[str] = []

        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        text, encoding_used = decode_with_best_effort(raw_bytes)
        if "replacement" in encoding_used:
            warnings.append(
                f"Some bytes could not be decoded cleanly using detected encoding "
                f"and were replaced (final encoding used: {encoding_used})."
            )

        metadata = DocumentMetadata(
            title=None,
            author=None,
            created_at=None,
            modified_at=None,
            language=detect_language(text),
            page_count=None,
            extension=self.extension,
            parser_used=self.__class__.__name__,
            ocr_used=False,
            character_count=count_characters(text),
            word_count=count_words(text),
        )

        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - started_at).total_seconds()
        metadata.parsing_time_seconds = duration

        return ParsedDocument(
            document_id=document_id,
            text=text,
            metadata=metadata,
            tables=[],
            images=[],
            ocr=OcrInfo(used=False),
            processing=ProcessingInfo(
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                warnings=warnings,
            ),
        )
