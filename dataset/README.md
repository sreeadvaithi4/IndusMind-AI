# dataset/

Reserved for sample/seed datasets used in development and testing of
ingestion, RAG, and knowledge graph modules (e.g. sample industrial
documents, labeled extraction examples).

## sample_documents/

Test fixtures for the Parser module (`ingestion/`), used by
`backend/apps/documents/tests/test_parser_integration.py` and
`backend/ingestion/tests/`:

| File | Purpose |
|---|---|
| `sample.pdf` | Valid PDF with extractable text + title/author metadata |
| `sample.docx` | Valid DOCX with a paragraph, heading, and a table |
| `sample.txt` | Valid plain text, UTF-8 |
| `sample.csv` | Valid CSV with headers and numeric/text columns |
| `sample.xlsx` | Valid XLSX with one worksheet |
| `corrupted.pdf` | A `.pdf`-named file containing plain text, not a valid PDF — exercises `CorruptedFileError` |
| `encrypted.pdf` | A password-protected PDF (AES-256, empty user password not accepted) — exercises `EncryptedDocumentError` |

These files are deliberately small and synthetic (generated via
PyMuPDF/python-docx/pandas) — they contain no real industrial data.
