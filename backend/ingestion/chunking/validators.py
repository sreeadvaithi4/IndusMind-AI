"""Pre-chunking validation for the chunking module."""

from ingestion.chunking.exceptions import CorruptedParsedContentError, EmptyDocumentError
from ingestion.result import ParsedDocument


def validate_parsed_document(parsed_document: ParsedDocument) -> None:
    """
    Raises EmptyDocumentError if there is neither text nor tables to
    chunk, or CorruptedParsedContentError if the input is structurally
    invalid (e.g. a table that isn't a list of rows).

    Called once at the start of `DocumentChunkerService.chunk_document`
    so every downstream strategy can assume its input is well-formed.
    """
    if parsed_document is None:
        raise CorruptedParsedContentError("parsed_document must not be None.")

    has_text = bool(parsed_document.text and parsed_document.text.strip())
    has_tables = bool(parsed_document.tables)

    if not has_text and not has_tables:
        raise EmptyDocumentError(
            f"Document {parsed_document.document_id} has no extracted text "
            "and no tables — nothing to chunk."
        )

    for table_index, table in enumerate(parsed_document.tables):
        if not isinstance(table, list) or not all(isinstance(row, list) for row in table):
            raise CorruptedParsedContentError(
                f"Table at index {table_index} is not a valid list-of-rows "
                f"structure and cannot be chunked."
            )
