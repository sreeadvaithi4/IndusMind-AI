"""
Header-aware section splitting.

Splits a document's flat text into (section_title, section_text)
pairs, using a heuristic that recognizes common heading patterns:
short lines that are entirely uppercase, markdown-style `#` headings,
or numbered-heading patterns (e.g. "1. Introduction", "Section 2:").

This is a best-effort heuristic — the Parser (Sprint 5) does not
preserve structural heading information for most formats (only DOCX
paragraph text is available, with no "this is Heading 1 style" flag
surfaced through `ParsedDocument`), so headers are detected purely from
line-shape, not from the source document's actual style metadata. This
directly affects `Chunk.section_title` and `Chunk.page_number` (see
`ingestion.chunking.service` module docstring for the full
page-number-availability caveat).
"""

import re

_MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+)$")
_NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?:\d{1,2}(?:\.\d{1,2})*[.):]?\s+|Section\s+\d+[.:]?\s*)(.+)$", re.IGNORECASE
)
MAX_HEADING_LINE_LENGTH = 80


def _looks_like_heading(line: str) -> str | None:
    """Returns the heading title if `line` looks like a heading, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_LINE_LENGTH:
        return None

    markdown_match = _MARKDOWN_HEADING_PATTERN.match(stripped)
    if markdown_match:
        return markdown_match.group(1).strip()

    numbered_match = _NUMBERED_HEADING_PATTERN.match(stripped)
    if numbered_match and len(stripped.split()) <= 12:
        return stripped

    # All-caps short line (e.g. "INTRODUCTION", "SAFETY PRECAUTIONS")
    # with no terminal punctuation, and at least one alphabetic character.
    if (
        stripped.isupper()
        and any(char.isalpha() for char in stripped)
        and not stripped.endswith((".", ",", ";"))
        and len(stripped.split()) <= 10
    ):
        return stripped

    return None


def split_into_sections(text: str) -> list[tuple[str | None, str]]:
    """
    Splits `text` into a list of (section_title, section_text) tuples.

    The first section may have `section_title=None` if the document
    has content before its first detected heading (or no headings at
    all, in which case the entire text is a single section with
    `section_title=None`).
    """
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    sections: list[tuple[str | None, list[str]]] = [(None, [])]

    for line in lines:
        heading = _looks_like_heading(line)
        if heading:
            sections.append((heading, []))
        else:
            sections[-1][1].append(line)

    return [
        (title, "\n".join(body_lines).strip())
        for title, body_lines in sections
        if "\n".join(body_lines).strip()
    ]
