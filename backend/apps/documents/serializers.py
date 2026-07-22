"""
Serializers for the Document Management API.
"""

from rest_framework import serializers

from apps.documents.models import Document
from apps.documents.validators import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES


class DocumentUploadSerializer(serializers.Serializer):
    """
    Validates the incoming upload request shape. Field-level file
    validation (extension, size) is intentionally delegated to
    `DocumentUploadService` / `validators.validate_upload` rather than
    duplicated here, so there is exactly one place those rules live.
    """

    file = serializers.FileField(required=True)

    def validate_file(self, value):
        if value.size == 0:
            raise serializers.ValidationError("The uploaded file is empty.")
        return value


class DocumentListSerializer(serializers.ModelSerializer):
    """Compact representation used for list/recent-uploads endpoints."""

    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id",
            "original_filename",
            "extension",
            "file_size",
            "page_count",
            "uploaded_by_username",
            "status",
            "status_display",
            "processing_percentage",
            "chunk_count",
            "embedding_status",
            "knowledge_graph_status",
            "download_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_download_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class DocumentDetailSerializer(DocumentListSerializer):
    """Full representation used for the retrieve endpoint; adds error detail."""

    processing_stage_display = serializers.CharField(
        source="get_processing_stage_display", read_only=True
    )

    class Meta(DocumentListSerializer.Meta):
        fields = DocumentListSerializer.Meta.fields + (
            "stored_filename",
            "processing_stage",
            "processing_stage_display",
            "error_message",
            "parser_metadata",
            "chunker_metadata",
            "chunking_time_seconds",
            "embedding_metadata",
        )
        read_only_fields = fields


class SupportedFormatsSerializer(serializers.Serializer):
    """Static metadata describing upload constraints, for client-side validation UX."""

    allowed_extensions = serializers.ListField(child=serializers.CharField())
    max_upload_size_bytes = serializers.IntegerField()
    max_upload_size_mb = serializers.FloatField()

    @classmethod
    def build(cls):
        return {
            "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            "max_upload_size_bytes": MAX_UPLOAD_SIZE_BYTES,
            "max_upload_size_mb": round(MAX_UPLOAD_SIZE_BYTES / (1024 * 1024), 2),
        }
