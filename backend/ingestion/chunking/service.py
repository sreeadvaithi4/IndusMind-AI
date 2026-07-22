"""
Top-level document chunking service.

`DocumentChunkerService.chunk_document` is the single entry point
`apps.documents.services.DocumentProcessingService.run_chunker` calls.
It consumes the `ParsedDocument` the Parser (Sprint 5) produces
directly — no modification to the Parser was made or is required — and
returns a standardized `ChunkCollection` for the future Embedding
Generator (Sprint 7) to consume.

Page number availability caveat: `ParsedDocument.text` is a flat string
with no embedded page-boundary markers (the PDF parser joins per-page
text with a blank line but does not expose page offsets through the
`ParsedDocument` contract, and DOCX/TXT/CSV/XLSX have no page concept
at all — see `ingestion/result.py` and the Sprint 5 DOCX parser's own
page_count=None warning). Chunking therefore cannot reliably attribute
a chunk to a specific page for any format, and `Chunk.page_number` is
populated as `None` for all text chunks in this sprint. This is a
Parser-contract limitation, not a Chunker bug — extending
`ParsedDocument` with page-offset tracking would require modifying the
Parser, which this sprint's instructions explicitly prohibit. Table
chunks likewise have no page number (tables are extracted independent
of page position in the current Parser). This limitation is documented
here and in PROJECT_CONTEXT.md as a Sprint 7+ candidate improvement.
"""

import logging
import time
from datetime import datetime, timezone

from ingestion.chunking.config import ChunkingConfig
from ingestion.chunking.exceptions import ChunkingError
from ingestion.chunking.result import (
    Chunk,
    ChunkCollection,
    ChunkingProcessingInfo,
    ChunkMetadata,
    ChunkType,
)
from ingestion.chunking.strategies.header_aware import split_into_sections
from ingestion.chunking.strategies.recursive import recursive_chunk_text
from ingestion.chunking.strategies.table import chunk_table
from ingestion.chunking.validators import validate_parsed_document
from ingestion.result import ParsedDocument

logger = logging.getLogger("ingestion.chunking")


class DocumentChunkerService:
    """Stateless facade orchestrating header-aware, recursive, and table chunking strategies."""

    @staticmethod
    def chunk_document(
        parsed_document: ParsedDocument,
        config: ChunkingConfig | None = None,
        filename: str | None = None,
    ) -> ChunkCollection:
        """
        Chunks `parsed_document` into a standardized `ChunkCollection`.

        Args:
            parsed_document: the ParsedDocument produced by the Parser
                (Sprint 5) — consumed directly, unmodified.
            config: chunking configuration; defaults to
                `ChunkingConfig.from_settings()` if not provided.
            filename: the document's original filename, for chunk
                metadata provenance. `ParsedDocument` does not carry
                the original filename (it is a Django `Document` model
                concern, not a Parser concern), so callers with access
                to the `Document` row should pass it explicitly;
                defaults to a document-id-based placeholder if omitted.

        Returns:
            ChunkCollection

        Raises:
            ingestion.chunking.exceptions.ChunkingError (or a
                subclass): on any validation or chunking failure.
        """
        config = config or ChunkingConfig.from_settings()
        document_id = parsed_document.document_id if parsed_document else "unknown"
        filename = filename or f"document_{document_id}"

        logger.info("Starting chunking: document_id=%s", document_id)
        start_time = time.monotonic()
        started_at_dt = datetime.now(timezone.utc)

        try:
            validate_parsed_document(parsed_document)
            chunks, warnings = DocumentChunkerService._build_chunks(
                parsed_document, config, filename
            )
        except ChunkingError:
            elapsed = time.monotonic() - start_time
            logger.error(
                "Chunking failed: document_id=%s elapsed=%.3fs",
                document_id,
                elapsed,
                exc_info=True,
            )
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            logger.error(
                "Unexpected chunking failure: document_id=%s elapsed=%.3fs",
                document_id,
                elapsed,
                exc_info=True,
            )
            raise ChunkingError(
                f"Unexpected error while chunking document {document_id}: {exc}"
            ) from exc

        finished_at_dt = datetime.now(timezone.utc)
        elapsed = time.monotonic() - start_time

        # Now that the total chunk count is known, backfill
        # metadata.total_chunks on every chunk (it cannot be known
        # while chunks are still being generated one strategy at a time).
        for chunk in chunks:
            chunk.metadata.total_chunks = len(chunks)

        collection = ChunkCollection(
            document_id=document_id,
            chunks=chunks,
            processing=ChunkingProcessingInfo(
                started_at=started_at_dt,
                finished_at=finished_at_dt,
                duration_seconds=elapsed,
                warnings=warnings,
            ),
        )

        logger.info(
            "Finished chunking: document_id=%s elapsed=%.3fs total_chunks=%d "
            "text_chunks=%d table_chunks=%d",
            document_id,
            elapsed,
            collection.total_chunks,
            collection.text_chunk_count,
            collection.table_chunk_count,
        )

        return collection

    @staticmethod
    def _build_chunks(
        parsed_document: ParsedDocument, config: ChunkingConfig, filename: str
    ) -> tuple[list[Chunk], list[str]]:
        warnings: list[str] = []
        chunks: list[Chunk] = []
        chunk_number = 0

        def make_metadata(section: str | None, source_type: str) -> ChunkMetadata:
            return ChunkMetadata(
                document_id=parsed_document.document_id,
                filename=filename,
                parser_used=parsed_document.metadata.parser_used,
                ocr_used=parsed_document.ocr.used,
                chunk_number=0,  # set correctly below, per chunk
                total_chunks=0,  # backfilled by chunk_document() once final count is known
                section=section,
                source_type=source_type,
            )

        if parsed_document.text and parsed_document.text.strip():
            sections = split_into_sections(parsed_document.text)
            if not sections:
                warnings.append("No sections detected; treating document as a single section.")
                sections = [(None, parsed_document.text)]

            for section_title, section_text in sections:
                for piece in recursive_chunk_text(section_text, config):
                    chunk_number += 1
                    metadata = make_metadata(section_title, ChunkType.TEXT.value)
                    metadata.chunk_number = chunk_number
                    chunks.append(
                        Chunk(
                            chunk_id=f"{parsed_document.document_id}_chunk_{chunk_number:04d}",
                            document_id=parsed_document.document_id,
                            chunk_number=chunk_number,
                            text=piece,
                            chunk_type=ChunkType.TEXT,
                            metadata=metadata,
                            word_count=len(piece.split()),
                            character_count=len(piece),
                            page_number=None,
                            section_title=section_title,
                        )
                    )
        else:
            warnings.append("Document has no extracted text; only table chunks were produced.")

        for table_index, table in enumerate(parsed_document.tables):
            table_pieces = chunk_table(table, config)
            if not table_pieces:
                warnings.append(f"Table {table_index} had no data rows and produced no chunks.")
                continue

            for piece in table_pieces:
                chunk_number += 1
                section_label = f"Table {table_index + 1}"
                metadata = make_metadata(section_label, ChunkType.TABLE.value)
                metadata.chunk_number = chunk_number
                chunks.append(
                    Chunk(
                        chunk_id=f"{parsed_document.document_id}_chunk_{chunk_number:04d}",
                        document_id=parsed_document.document_id,
                        chunk_number=chunk_number,
                        text=piece,
                        chunk_type=ChunkType.TABLE,
                        metadata=metadata,
                        word_count=len(piece.split()),
                        character_count=len(piece),
                        page_number=None,
                        section_title=section_label,
                    )
                )

        return chunks, warnings
