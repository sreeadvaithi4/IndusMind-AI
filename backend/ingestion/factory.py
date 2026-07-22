"""
Factory function for obtaining a parser instance.

Thin wrapper over `ingestion.base.ParserRegistry` — kept as its own
module (rather than requiring callers to import `ParserRegistry`
directly) so the public "get me a parser" API has one obvious entry
point, matching the "Parser factory" requirement as a distinct,
importable unit.
"""

from ingestion.base import BaseParser, ParserRegistry

# Importing the parsers package registers every format-specific parser
# with ParserRegistry as a side effect of the `@ParserRegistry.register`
# decorators in each `ingestion/parsers/*.py` module.
from ingestion import parsers  # noqa: F401,E402


def get_parser_for_extension(extension: str) -> BaseParser:
    """Returns a parser instance for the given file extension."""
    return ParserRegistry.get_parser(extension)


def get_supported_extensions() -> list[str]:
    """Returns the sorted list of extensions with a registered parser."""
    return ParserRegistry.supported_extensions()
