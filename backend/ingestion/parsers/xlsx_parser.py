"""XLSX parser (openpyxl via pandas), extracting every worksheet as a table."""

from datetime import datetime, timezone

from ingestion.base import BaseParser, ParserRegistry
from ingestion.exceptions import CorruptedFileError
from ingestion.result import DocumentMetadata, OcrInfo, ParsedDocument, ProcessingInfo
from ingestion.utils import count_characters, count_words, detect_language


@ParserRegistry.register
class XlsxParser(BaseParser):
    extension = "xlsx"

    def parse(self, file_path: str, document_id: str) -> ParsedDocument:
        started_at = datetime.now(timezone.utc)
        warnings: list[str] = []

        import pandas as pd

        try:
            sheets = pd.read_excel(file_path, sheet_name=None, engine="openpyxl")
        except ValueError as exc:
            raise CorruptedFileError(
                f"'{file_path}' could not be parsed as XLSX: {exc}"
            ) from exc
        except Exception as exc:  # openpyxl raises its own error types on corruption
            raise CorruptedFileError(
                f"'{file_path}' could not be opened as a valid XLSX workbook: {exc}"
            ) from exc

        if not sheets:
            warnings.append("Workbook contains no worksheets.")

        tables = []
        text_sections = []

        for sheet_name, dataframe in sheets.items():
            headers = list(dataframe.columns.astype(str))
            rows = dataframe.astype(str).values.tolist()
            tables.append([headers] + rows)

            preview = dataframe.head(50).to_string(index=False)
            text_sections.append(
                f"Worksheet: {sheet_name}\n"
                f"Rows: {len(dataframe)}, Columns: {len(dataframe.columns)}\n\n{preview}"
            )
            if len(dataframe) > 50:
                warnings.append(
                    f"Worksheet '{sheet_name}': text preview includes only the "
                    f"first 50 of {len(dataframe)} rows; full data is available "
                    f"in `ParsedDocument.tables`."
                )

        text = "\n\n---\n\n".join(text_sections)

        metadata = DocumentMetadata(
            title=None,
            author=None,
            created_at=None,
            modified_at=None,
            language=detect_language(text),
            page_count=len(sheets) or None,
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
            tables=tables,
            images=[],
            ocr=OcrInfo(used=False),
            processing=ProcessingInfo(
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                warnings=warnings,
            ),
        )
