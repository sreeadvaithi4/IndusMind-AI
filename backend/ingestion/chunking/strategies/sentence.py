"""
Sentence-aware splitting.

A lightweight, dependency-free sentence boundary detector (regex-based
— avoids pulling in a full NLP library, which is out of scope for this
sprint). Used by the recursive splitter as one of its fallback
split-point strategies, and directly exposed for callers that want
sentence-level granularity.
"""

import re

# Splits after '.', '!', or '?' followed by whitespace and a capital
# letter or end of string — a deliberately simple heuristic that
# handles the common case well without a full NLP sentence tokenizer.
_SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def split_into_sentences(text: str) -> list[str]:
    """Splits `text` into a list of sentence strings (whitespace-trimmed, non-empty)."""
    if not text or not text.strip():
        return []

    candidates = _SENTENCE_BOUNDARY_PATTERN.split(text.strip())
    return [s.strip() for s in candidates if s.strip()]
