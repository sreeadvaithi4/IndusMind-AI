"""
Storage layer for document uploads.

Encapsulates *where* and *how* uploaded files are written to disk,
independent of Django's model layer or the service layer. Views and
services never build filesystem paths themselves — they go through
`DocumentStorage`.
"""

import uuid
from datetime import datetime

from apps.documents.validators import sanitize_filename


class DocumentStorage:
    """
    Directory-organization and path-building policy for uploaded
    documents.

    Files are organized as:
        documents/<year>/<month>/<day>/<uuid>_<sanitized-filename>

    The date-based partitioning keeps any single directory from
    accumulating an unbounded number of files as the platform scales,
    and the UUID prefix guarantees no collision even when two users
    upload files with the same name on the same day.
    """

    ROOT_DIRECTORY = "documents"

    @classmethod
    def build_storage_path(cls, instance, filename):
        """
        Builds the relative storage path for a Document's FileField.

        `instance` is the (possibly still-unsaved) Document instance;
        only its `id` is used, which is safe because `Document.id` is a
        client-side UUID default (set at instantiation, not at INSERT
        time), so it is always available before the file is saved.
        """
        sanitized_name = sanitize_filename(filename)
        today = datetime.utcnow()
        unique_prefix = uuid.uuid4().hex[:12]

        return (
            f"{cls.ROOT_DIRECTORY}/{today:%Y}/{today:%m}/{today:%d}/"
            f"{unique_prefix}_{sanitized_name}"
        )

    @staticmethod
    def stored_filename_from_path(storage_path):
        """Returns just the filename component of a storage path."""
        return storage_path.rsplit("/", 1)[-1]

    @staticmethod
    def delete_file(file_field):
        """
        Deletes the underlying file for a FileField value, tolerating
        the case where the file is already missing on disk (e.g. it was
        manually removed, or this is called twice). `save=False` is
        used by callers that are about to delete the owning model row
        anyway, to avoid an unnecessary extra UPDATE query.
        """
        if not file_field:
            return
        file_field.delete(save=False)
