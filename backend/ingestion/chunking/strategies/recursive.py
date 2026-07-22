"""
Recursive text chunking — the primary text-splitting strategy.

Splits text by trying progressively finer-grained boundaries: first
paragraph breaks (blank lines), then sentence boundaries (via
`sentence.split_into_sentences`), then a hard character-count split as
a last resort for any single "paragraph" or "sentence" that still
exceeds `config.max_chunk_length` (e.g. a huge unbroken block of text
with no punctuation). Adjacent pieces are greedily packed together up
to `config.chunk_size`, with `config.chunk_overlap` characters of
trailing context repeated at the start of the next chunk to preserve
continuity across chunk boundaries.

This mirrors the well-established "recursive character text splitter"
pattern (the same approach LangChain's own splitter uses) reimplemented
locally, since LangChain itself is explicitly out of scope this sprint.
"""

from ingestion.chunking.config import ChunkingConfig
from ingestion.chunking.strategies.sentence import split_into_sentences


def _split_into_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n")]
    return [p for p in paragraphs if p]


def _hard_split(text: str, max_length: int) -> list[str]:
    """Last-resort split: cuts text into fixed-length pieces with no regard for word boundaries."""
    return [text[i : i + max_length] for i in range(0, len(text), max_length)] or [text]


def _break_into_pieces(paragraph: str, config: ChunkingConfig) -> list[str]:
    """
    Breaks a single paragraph down into pieces no larger than
    `config.max_chunk_length`, trying sentence boundaries before
    falling back to a hard character split.
    """
    if len(paragraph) <= config.max_chunk_length:
        return [paragraph]

    sentences = split_into_sentences(paragraph)
    if len(sentences) > 1:
        pieces = []
        for sentence in sentences:
            if len(sentence) <= config.max_chunk_length:
                pieces.append(sentence)
            else:
                pieces.extend(_hard_split(sentence, config.max_chunk_length))
        return pieces

    return _hard_split(paragraph, config.max_chunk_length)


def recursive_chunk_text(text: str, config: ChunkingConfig) -> list[str]:
    """
    Splits `text` into a list of chunk strings according to `config`.

    Algorithm:
        1. Split into paragraphs (blank-line-separated).
        2. Break any paragraph exceeding max_chunk_length into smaller
           pieces (via sentence boundaries, then hard splitting).
        3. Greedily pack consecutive pieces into chunks up to
           chunk_size characters.
        4. Prepend `chunk_overlap` trailing characters from the
           previous chunk onto each subsequent chunk's start.
        5. Merge any final chunk shorter than min_chunk_length into
           the preceding chunk (rather than emitting a near-empty
           trailing chunk).
    """
    if not text or not text.strip():
        return []

    paragraphs = _split_into_paragraphs(text)
    if not paragraphs:
        return []

    pieces: list[str] = []
    for paragraph in paragraphs:
        pieces.extend(_break_into_pieces(paragraph, config))

    chunks: list[str] = []
    current = ""

    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= config.chunk_size or not current:
            current = candidate
        else:
            chunks.append(current)
            current = piece

    if current:
        chunks.append(current)

    if config.chunk_overlap > 0:
        chunks = _apply_overlap(chunks, config.chunk_overlap)

    return _merge_short_trailing_chunks(chunks, config.min_chunk_length)


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if len(chunks) <= 1:
        return chunks

    overlapped = [chunks[0]]
    for previous, current in zip(chunks, chunks[1:]):
        overlap_text = previous[-overlap:]
        overlapped.append(f"{overlap_text}{current}" if overlap_text else current)
    return overlapped


def _merge_short_trailing_chunks(chunks: list[str], min_length: int) -> list[str]:
    if len(chunks) <= 1:
        return chunks

    if len(chunks[-1]) < min_length:
        merged = chunks[:-2] + [f"{chunks[-2]}\n\n{chunks[-1]}"]
        return merged

    return chunks
