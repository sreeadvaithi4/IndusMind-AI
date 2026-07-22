"""
Parser interface and the parser registry (factory).

`BaseParser` is the interface every format-specific parser implements.
`ParserRegistry` maps a file extension to its parser class — the
"Parser Factory" — so adding support for a new format means
registering one new class here, without touching
`DocumentParserService` or `DocumentProcessingService`.
"""

from abc import ABC, abstractmethod

from ingestion.exceptions import UnsupportedFileTypeError
from ingestion.result import ParsedDocument


class BaseParser(ABC):
    """
    Interface for a single-format document parser.

    Implementations must be stateless (safe to reuse a single instance
    across many parse calls) and must raise a `ingestion.exceptions.ParserError`
    subclass on failure rather than letting arbitrary library exceptions
    propagate, so callers only need to handle one exception hierarchy.
    """

    #: File extension (lowercase, no dot) this parser handles, e.g. "pdf".
    extension: str = ""

    @abstractmethod
    def parse(self, file_path: str, document_id: str) -> ParsedDocument:
        """
        Parses the file at `file_path` and returns a `ParsedDocument`.

        Args:
            file_path: absolute filesystem path to the stored file.
            document_id: string UUID of the owning `Document`, copied
                into the returned `ParsedDocument.document_id`.
        """
        raise NotImplementedError


class ParserRegistry:
    """
    Maps file extensions to `BaseParser` implementations.

    Parsers are registered via `ParserRegistry.register` (used as a
    class decorator by each parser module) rather than being
    hardcoded in a single if/elif chain, so `ingestion/parsers/*`
    modules are the single source of truth for which formats exist.
    """

    _parsers: dict[str, type[BaseParser]] = {}

    @classmethod
    def register(cls, parser_class: type[BaseParser]) -> type[BaseParser]:
        if not parser_class.extension:
            raise ValueError(
                f"{parser_class.__name__} must define a non-empty 'extension' "
                "attribute before it can be registered."
            )
        cls._parsers[parser_class.extension] = parser_class
        return parser_class

    @classmethod
    def get_parser(cls, extension: str) -> BaseParser:
        """
        Returns a parser instance for `extension` (case-insensitive).

        Raises:
            UnsupportedFileTypeError: if no parser is registered for
                the given extension.
        """
        normalized = extension.lower().lstrip(".")
        parser_class = cls._parsers.get(normalized)
        if parser_class is None:
            supported = ", ".join(sorted(cls._parsers.keys())) or "(none registered)"
            raise UnsupportedFileTypeError(
                f"No parser registered for extension '.{normalized}'. "
                f"Supported extensions: {supported}."
            )
        return parser_class()

    @classmethod
    def supported_extensions(cls) -> list[str]:
        return sorted(cls._parsers.keys())
