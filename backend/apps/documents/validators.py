"""
Validators for document uploads.

These are pure functions (no I/O beyond reading the in-memory uploaded
file's metadata/content that Django already buffers) so they can be
reused identically by serializers, the service layer, and future
management commands or async tasks without duplicating validation
rules in multiple places.
"""

import os
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError

# Extensions the platform accepts, per the supported-formats requirement.
# Kept as a single source of truth; both the DRF serializer and the
# service layer import this constant rather than redefining it.
ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "txt", "csv", "xlsx"}

# 50 MB default; overridable via the DOCUMENT_MAX_UPLOAD_SIZE_MB env var
# so operators can tune this per-environment without a code change.
MAX_UPLOAD_SIZE_BYTES = getattr(settings, "DOCUMENT_MAX_UPLOAD_SIZE_MB", 50) * 1024 * 1024

_FILENAME_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_MULTIPLE_UNDERSCORES_PATTERN = re.compile(r"_+")


def get_file_extension(filename):
    """Returns the lowercase extension (without the dot), or '' if none."""
    _, ext = os.path.splitext(filename)
    return ext.lstrip(".").lower()


def validate_extension(filename):
    """
    Raises ValidationError if the file's extension is not in
    ALLOWED_EXTENSIONS. Returns the validated (lowercase) extension.
    """
    extension = get_file_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        supported = ", ".join(sorted(e.upper() for e in ALLOWED_EXTENSIONS))
        raise ValidationError(
            f"Unsupported file type '.{extension or 'unknown'}'. "
            f"Supported formats are: {supported}."
        )
    return extension


def validate_file_size(size_in_bytes):
    """Raises ValidationError if the file exceeds MAX_UPLOAD_SIZE_BYTES."""
    if size_in_bytes <= 0:
        raise ValidationError("The uploaded file is empty.")
    if size_in_bytes > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        actual_mb = size_in_bytes / (1024 * 1024)
        raise ValidationError(
            f"File is too large ({actual_mb:.1f} MB). Maximum allowed size "
            f"is {max_mb} MB."
        )


def sanitize_filename(filename):
    """
    Produces a filesystem-safe filename: strips directory components,
    normalizes unicode, replaces disallowed characters with underscores,
    and collapses repeated underscores. The extension is preserved
    (lowercased).

    This guards against path traversal (`../../etc/passwd`), null bytes,
    and other unsafe filename content before the name is ever used to
    build a filesystem path.
    """
    # Strip any directory components the client may have sent.
    base_name = os.path.basename(filename)

    name, ext = os.path.splitext(base_name)
    ext = ext.lstrip(".").lower()

    # Normalize unicode to a closest-ASCII representation, then drop
    # anything that isn't alphanumeric, dot, underscore, or hyphen.
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    sanitized = _FILENAME_SAFE_PATTERN.sub("_", normalized).strip("._-")
    sanitized = _MULTIPLE_UNDERSCORES_PATTERN.sub("_", sanitized)

    if not sanitized:
        sanitized = "document"

    # Truncate to keep the final "<name>.<ext>" comfortably under common
    # filesystem limits even after the storage layer prefixes a UUID.
    sanitized = sanitized[:120]

    return f"{sanitized}.{ext}" if ext else sanitized


def check_duplicate_filename(original_filename, existing_filenames):
    """
    Returns True if `original_filename` matches (case-insensitively) one
    of `existing_filenames`. Callers use this to surface a non-fatal
    duplicate-filename *warning* — duplicates are not rejected outright,
    since re-uploading a revised version of a document is a legitimate
    use case.
    """
    normalized = original_filename.strip().lower()
    return normalized in {name.strip().lower() for name in existing_filenames}


def validate_upload(filename, size_in_bytes):
    """
    Convenience aggregate validator used by the service layer: runs
    extension and size validation together and returns the validated
    extension. Raises ValidationError on the first failure.
    """
    extension = validate_extension(filename)
    validate_file_size(size_in_bytes)
    return extension
