"""
Table-aware chunking.

Tables are chunked entirely separately from prose text, never mixed
into text chunks — each table becomes one or more TABLE-type chunks,
preserving its header row, rows, and columns. A table larger than
`config.max_chunk_length` (when rendered as text) is split into
multiple chunks by row group, with the header row repeated in every
resulting chunk so each remains independently interpretable by the
future Embedding Generator (a chunk of rows with no header would be
close to meaningless on its own).
"""

from ingestion.chunking.config import ChunkingConfig


def _render_table_rows_as_text(header: list[str], rows: list[list[str]]) -> str:
    lines = [" | ".join(header)]
    lines.append(" | ".join("-" * len(cell) for cell in header))
    for row in rows:
        lines.append(" | ".join(row))
    return "\n".join(lines)


def chunk_table(table: list[list[str]], config: ChunkingConfig) -> list[str]:
    """
    Splits a single table (list of rows, first row = header) into one
    or more text representations, each rendered as a simple pipe-
    delimited table with the header repeated in every piece.

    Returns an empty list for a table with no data rows (header only,
    or entirely empty).
    """
    if not table:
        return []

    header, *rows = table
    if not rows:
        return []

    full_text = _render_table_rows_as_text(header, rows)
    if len(full_text) <= config.max_chunk_length:
        return [full_text]

    # Split rows into groups small enough that each rendered group
    # (with the header repeated) stays within max_chunk_length.
    pieces = []
    current_rows: list[list[str]] = []

    for row in rows:
        candidate_rows = current_rows + [row]
        candidate_text = _render_table_rows_as_text(header, candidate_rows)
        if len(candidate_text) <= config.max_chunk_length or not current_rows:
            current_rows = candidate_rows
        else:
            pieces.append(_render_table_rows_as_text(header, current_rows))
            current_rows = [row]

    if current_rows:
        pieces.append(_render_table_rows_as_text(header, current_rows))

    return pieces
