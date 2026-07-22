"""
Models for the Document Management app.

The `Document` model is the single source of truth for a document's
position in the ingestion pipeline. Its `status` field drives both the
REST API responses and (in a future sprint) the Upload Workspace UI's
processing-status widget.

Pipeline stages implemented in this sprint:
    UPLOADED -> VALIDATING -> STORED -> READY_FOR_PARSING

Pipeline stages reserved for future modules (see services.py for the
documented extension points; NOT implemented here):
    PARSING -> PARSED -> CHUNKING -> CHUNKED -> EMBEDDING -> EMBEDDED
    -> INDEXING_VECTOR_DB -> VECTOR_INDEXED -> INDEXING_KNOWLEDGE_GRAPH
    -> INDEXED

FAILED is a terminal state reachable from any non-terminal stage.
"""

import uuid

from django.conf import settings
from django.db import models


class DocumentStatus(models.TextChoices):
    """
    Full pipeline state machine.

    Members below the "STORED" milestone comment are reserved for
    future modules and are intentionally unreachable by any code in
    this sprint — they exist now so the schema does not need a
    migration every time a new pipeline stage is implemented.
    """

    UPLOADED = "uploaded", "Uploaded"
    VALIDATING = "validating", "Validating"
    STORED = "stored", "Stored"
    READY_FOR_PARSING = "ready_for_parsing", "Ready for Parsing"

    # --- Reserved for future modules (not implemented this sprint) ---
    PARSING = "parsing", "Parsing"
    PARSED = "parsed", "Parsed"
    CHUNKING = "chunking", "Chunking"
    CHUNKED = "chunked", "Chunked"
    EMBEDDING = "embedding", "Generating Embeddings"
    EMBEDDED = "embedded", "Embedded"
    INDEXING_VECTOR_DB = "indexing_vector_db", "Updating ChromaDB"
    VECTOR_INDEXED = "vector_indexed", "Vector Indexed"
    INDEXING_KNOWLEDGE_GRAPH = "indexing_knowledge_graph", "Updating Knowledge Graph"
    INDEXED = "indexed", "Indexed"

    FAILED = "failed", "Failed"


class EmbeddingStatus(models.TextChoices):
    """Status of the (not-yet-implemented) embedding generation stage."""

    NOT_STARTED = "not_started", "Not Started"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class KnowledgeGraphStatus(models.TextChoices):
    """Status of the (not-yet-implemented) knowledge graph indexing stage."""

    NOT_STARTED = "not_started", "Not Started"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


def document_upload_path(instance, filename):
    """
    Callable `upload_to` for FileField, delegating to the storage layer.

    Kept as a thin delegation (rather than inline path logic) so the
    directory-organization policy lives in exactly one place:
    `storage.DocumentStorage.build_storage_path`.
    """
    from apps.documents.storage import DocumentStorage

    return DocumentStorage.build_storage_path(instance, filename)


class Document(models.Model):
    """
    Represents a single uploaded document and its position in the
    ingestion pipeline.

    Note on `knowledge_graph_status`: this field exists now so the
    schema is stable for future sprints, but nothing yet sets it to a
    non-default value — it is populated exclusively by the future
    Knowledge Graph module. `embedding_status` and `embedding_metadata`
    are populated by the Embedding Generator module as of Sprint 7.
    `chunk_count`, `chunking_time_seconds`, and `chunker_metadata` are
    populated by the Chunker module as of Sprint 6.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    original_filename = models.CharField(
        max_length=255,
        help_text="The filename as provided by the uploading client, before sanitization.",
    )
    stored_filename = models.CharField(
        max_length=255,
        help_text="The sanitized, collision-resistant filename used on disk.",
    )
    file = models.FileField(
        upload_to=document_upload_path,
        max_length=500,
    )
    extension = models.CharField(max_length=16)
    file_size = models.PositiveBigIntegerField(help_text="File size in bytes.")
    page_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Populated by the future Parser module. Null until parsed.",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    status = models.CharField(
        max_length=32,
        choices=DocumentStatus.choices,
        default=DocumentStatus.UPLOADED,
    )
    processing_stage = models.CharField(
        max_length=32,
        choices=DocumentStatus.choices,
        default=DocumentStatus.UPLOADED,
        help_text="Mirrors `status` for non-failed documents; retains the "
        "last active stage when `status` is FAILED so the UI can show "
        "'Failed while Parsing', etc.",
    )
    processing_percentage = models.PositiveSmallIntegerField(
        default=0,
        help_text="Overall pipeline completion, 0-100.",
    )

    chunk_count = models.PositiveIntegerField(
        default=0,
        help_text="Populated by the Chunker module once chunking completes.",
    )
    chunking_time_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Time taken by the Chunker module to process this document. "
        "Null until chunked.",
    )
    parser_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured metadata returned by the Parser module "
        "(title, author, dates, language, parser used, OCR used, "
        "timing, table/image counts, warnings). Empty until parsed.",
    )
    chunker_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured metadata returned by the Chunker module "
        "(total/text/table chunk counts, timing, warnings). Empty "
        "until chunked.",
    )
    embedding_status = models.CharField(
        max_length=16,
        choices=EmbeddingStatus.choices,
        default=EmbeddingStatus.NOT_STARTED,
        help_text="Populated by the Embedding Generator module (Sprint 7).",
    )
    embedding_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured metadata returned by the Embedding Generator "
        "(model, dimension, counts, timing, warnings). Empty until embedded.",
    )
    knowledge_graph_status = models.CharField(
        max_length=16,
        choices=KnowledgeGraphStatus.choices,
        default=KnowledgeGraphStatus.NOT_STARTED,
        help_text="Populated by the future Knowledge Graph module.",
    )

    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["uploaded_by", "-created_at"]),
        ]
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self):
        return f"{self.original_filename} ({self.status})"

    @property
    def is_terminal(self):
        """True if the document has reached a final state (indexed or failed)."""
        return self.status in {DocumentStatus.INDEXED, DocumentStatus.FAILED}

    @property
    def is_ready_for_parsing(self):
        return self.status == DocumentStatus.READY_FOR_PARSING
