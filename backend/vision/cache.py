"""
Drawing analysis cache — prevents redundant Gemini Vision calls
for the same document. In-memory cache keyed by document_id.
"""

import threading
import time

_cache: dict[str, dict] = {}
_lock = threading.Lock()
_TTL_SECONDS = 3600  # 1 hour


def get_cached_analysis(document_id: str) -> dict | None:
    """Returns cached analysis for a document, or None if expired/missing."""
    with _lock:
        entry = _cache.get(document_id)
        if entry and (time.time() - entry["timestamp"]) < _TTL_SECONDS:
            return entry["data"]
        elif entry:
            del _cache[document_id]
    return None


def set_cached_analysis(document_id: str, data: dict) -> None:
    """Caches an analysis result for a document."""
    with _lock:
        _cache[document_id] = {"data": data, "timestamp": time.time()}


def invalidate_cache(document_id: str) -> None:
    """Removes a cached analysis."""
    with _lock:
        _cache.pop(document_id, None)


def clear_cache() -> None:
    """Clears the entire cache (for testing)."""
    with _lock:
        _cache.clear()
