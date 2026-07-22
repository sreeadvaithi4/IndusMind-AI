"""
Shared utility helpers for the ingestion module.

Kept format-agnostic and dependency-light (no heavy imports at module
scope beyond what's already a hard requirement) so any parser can use
these without extra coupling.
"""

import re

_WORD_PATTERN = re.compile(r"\S+")


def count_characters(text: str) -> int:
    return len(text) if text else 0


def count_words(text: str) -> int:
    if not text:
        return 0
    return len(_WORD_PATTERN.findall(text))


def detect_language(text: str, sample_size: int = 2000) -> str | None:
    """
    Best-effort language detection using `langdetect`, if installed.

    Returns None (rather than raising) when the dependency is missing,
    the text is too short/empty to classify reliably, or detection
    itself fails — language detection is explicitly "if detectable"
    per the sprint requirements, not a hard dependency of parsing.
    """
    if not text or not text.strip():
        return None

    try:
        from langdetect import LangDetectException, detect
    except ImportError:
        return None

    sample = text[:sample_size].strip()
    if len(sample) < 20:
        # Too little text to classify reliably; avoid a misleading guess.
        return None

    try:
        return detect(sample)
    except LangDetectException:
        return None


def decode_with_best_effort(raw_bytes: bytes) -> tuple[str, str]:
    """
    Decodes `raw_bytes` to text, detecting the encoding first via
    `chardet` when available, falling back to UTF-8 (with replacement
    of undecodable bytes) so a text file with an unusual encoding never
    crashes parsing outright — it degrades to best-effort text with a
    caller-visible encoding name for diagnostics/warnings.

    Returns:
        (decoded_text, encoding_name_used)
    """
    encoding = "utf-8"

    try:
        import chardet

        detection = chardet.detect(raw_bytes)
        detected_encoding = detection.get("encoding")
        confidence = detection.get("confidence") or 0.0
        if detected_encoding and confidence >= 0.5:
            encoding = detected_encoding
    except ImportError:
        pass

    try:
        return raw_bytes.decode(encoding), encoding
    except (UnicodeDecodeError, LookupError):
        return raw_bytes.decode("utf-8", errors="replace"), "utf-8 (with replacement)"
