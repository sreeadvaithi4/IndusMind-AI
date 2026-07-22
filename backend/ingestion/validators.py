"""
Pre-parse validation for the ingestion module.

These checks run before any format-specific parser touches a file, so
every parser can assume the file exists and is non-empty, and so
generic failure modes (missing file) produce one consistent error
regardless of which format-specific parser would have handled it.
"""

import os

from ingestion.exceptions import FileNotFoundOnDiskError


def validate_file_exists_on_disk(file_path: str) -> None:
    """
    Raises FileNotFoundOnDiskError if `file_path` does not exist or is
    not a regular file. Guards against the Document row referencing a
    file that was deleted or never fully written (e.g. an interrupted
    upload, or manual filesystem intervention).
    """
    if not file_path or not os.path.isfile(file_path):
        raise FileNotFoundOnDiskError(
            f"Expected file at '{file_path}' but it does not exist on disk."
        )

    if os.path.getsize(file_path) == 0:
        raise FileNotFoundOnDiskError(f"File at '{file_path}' is empty (0 bytes).")
