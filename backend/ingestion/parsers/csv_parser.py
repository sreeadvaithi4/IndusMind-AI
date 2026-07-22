"""CSV parser (pandas), extracting rows/columns/headers and summary statistics."""

from datetime import datetime, timezone

from ingestion.base import BaseParser, ParserRegistry
from ingestion.exceptions import CorruptedFileError
from ingestion.result import DocumentMetadata, OcrInfo, ParsedDocument, ProcessingInfo
from ingestion.utils import count_characters, count_words, decode_with_best_effort, detect_language


def _build_statistics_text(dataframe) -> str:
    """
    Renders a compact, human-readable statistics summary (row/column
    counts, per-column dtype and null counts) as text, so the future
    Chunker/Embedding modules can meaningfully embed "what this
    spreadsheet contains" even before touching individual cell values.
    """
    lines = [
        f"Rows: {len(dataframe)}",
        f"Columns: {len(dataframe.columns)}",
        "Column summary:",
    ]
    for column in dataframe.columns:
        non_null = dataframe[column].notna().sum()
        lines.append(
            f"  - {column} (dtype: {dataframe[column].dtype}, "
            f"non-null: {non_null}/{len(dataframe)})"
        )
    return "\n".join(lines)


@ParserRegistry.register
class CsvParser(BaseParser):
    extension = "csv"

    def parse(self, file_path: str, document_id: str) -> ParsedDocument:
        started_at = datetime.now(timezone.utc)
        warnings: list[str] = []

        import pandas as pd

        with open(file_path, "rb") as f:
            raw_bytes = f.read()
        _, encoding_used = decode_with_best_effort(raw_bytes)

        try:
            dataframe = pd.read_csv(file_path, encoding=encoding_used.split(" ")[0])
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise CorruptedFileError(f"'{file_path}' could not be parsed as CSV: {exc}") from exc
        except pd.errors.EmptyDataError as exc:
            raise CorruptedFileError(f"'{file_path}' contains no parseable data: {exc}") from exc

        headers = list(dataframe.columns.astype(str))
        rows = dataframe.astype(str).values.tolist()
        table = [headers] + rows

        statistics_text = _build_statistics_text(dataframe)
        preview_text = dataframe.head(100).to_string(index=False)
        text = f"{statistics_text}\n\n{preview_text}"

        metadata = DocumentMetadata(
            title=None,
            author=None,
            created_at=None,
            modified_at=None,
            language=detect_language(text),
            page_count=1,
            extension=self.extension,
            parser_used=self.__class__.__name__,
            ocr_used=False,
            character_count=count_characters(text),
            word_count=count_words(text),
        )

        if len(dataframe) > 100:
            warnings.append(
                f"Document text preview includes only the first 100 of "
                f"{len(dataframe)} rows; the full table is available in "
                f"`ParsedDocument.tables`."
            )

        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - started_at).total_seconds()
        metadata.parsing_time_seconds = duration

        return ParsedDocument(
            document_id=document_id,
            text=text,
            metadata=metadata,
            tables=[table],
            images=[],
            ocr=OcrInfo(used=False),
            processing=ProcessingInfo(
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                warnings=warnings,
            ),
        )
