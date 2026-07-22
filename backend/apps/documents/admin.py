from django.contrib import admin

from apps.documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Operational visibility into uploaded documents for staff users."""

    list_display = (
        "original_filename",
        "extension",
        "uploaded_by",
        "status",
        "processing_percentage",
        "file_size",
        "chunk_count",
        "created_at",
    )
    list_filter = ("status", "extension", "embedding_status", "knowledge_graph_status")
    search_fields = ("original_filename", "stored_filename", "uploaded_by__username")
    readonly_fields = (
        "id",
        "stored_filename",
        "file_size",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
