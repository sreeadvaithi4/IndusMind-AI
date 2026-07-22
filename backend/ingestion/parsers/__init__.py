"""
Format-specific parser implementations, registered with ParserRegistry.

Importing this package registers every parser as a side effect: each
submodule below applies `@ParserRegistry.register` to its parser
class(es) at import time. `ingestion.factory` imports this package for
exactly that reason — see its module docstring.
"""

from ingestion.parsers import (  # noqa: F401
    csv_parser,
    docx_parser,
    pdf_parser,
    txt_parser,
    xlsx_parser,
)
