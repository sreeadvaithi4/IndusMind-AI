"""
Views for the Document Management REST API.

Every view delegates to the service layer (services.py) for anything
beyond request/response shaping — views never touch models, storage,
or validators directly. This keeps the API layer thin and gives future
sprints (async processing, Celery tasks, etc.) a stable seam to call
into without changing this file.
"""

import logging

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, RetrieveDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document
from apps.documents.permissions import IsDocumentOwnerOrReadOnlyForStaff
from apps.documents.serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentUploadSerializer,
    SupportedFormatsSerializer,
)
from apps.documents.services import (
    DocumentProcessingService,
    DocumentStatusService,
    DocumentUploadService,
    DocumentUploadServiceError,
)
from ingestion.chunking.exceptions import ChunkingError
from ingestion.exceptions import ParserError
from knowledge_graph.exceptions import KnowledgeGraphError
from rag.embeddings.exceptions import EmbeddingError
from rag.vectorstore.exceptions import VectorStoreError

logger = logging.getLogger("apps.documents")


class DocumentUploadView(APIView):
    """
    POST /api/documents/upload/

    Accepts a single multipart file upload. Anonymous users are
    rejected by `IsAuthenticated` before this view's logic ever runs.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            document = DocumentUploadService.upload(
                uploaded_file=serializer.validated_data["file"],
                user=request.user,
            )
        except DocumentUploadServiceError as exc:
            raise ValidationError({"file": str(exc)})

        response_serializer = DocumentDetailSerializer(
            document, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DocumentListView(ListAPIView):
    """GET /api/documents/ — paginated list of the current user's documents."""

    serializer_class = DocumentListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Document.objects.filter(uploaded_by=self.request.user)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        extension_filter = self.request.query_params.get("extension")
        if extension_filter:
            queryset = queryset.filter(extension=extension_filter.lower())

        search_term = self.request.query_params.get("search")
        if search_term:
            queryset = queryset.filter(original_filename__icontains=search_term)

        return queryset


class RecentDocumentsView(ListAPIView):
    """GET /api/documents/recent/ — the current user's most recent uploads."""

    serializer_class = DocumentListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    DEFAULT_LIMIT = 10
    MAX_LIMIT = 50

    def get_queryset(self):
        try:
            limit = int(self.request.query_params.get("limit", self.DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = self.DEFAULT_LIMIT
        limit = max(1, min(limit, self.MAX_LIMIT))

        return Document.objects.filter(uploaded_by=self.request.user)[:limit]


class DocumentDetailView(RetrieveDestroyAPIView):
    """
    GET /api/documents/{id}/ — retrieve a single document.
    DELETE /api/documents/{id}/ — delete a document (and its stored file,
    via the post_delete signal in signals.py).

    A document that exists but does not belong to the requesting user
    (and that the user has no staff read access to) is reported as 404
    rather than DRF's default 403, so the API never reveals whether a
    given document ID exists to a user who cannot access it.
    """

    queryset = Document.objects.all()
    serializer_class = DocumentDetailSerializer
    permission_classes = [IsDocumentOwnerOrReadOnlyForStaff]
    lookup_field = "id"

    def check_object_permissions(self, request, obj):
        if not self.get_permissions()[0].has_object_permission(request, self, obj):
            raise NotFound("Document not found.")

    def perform_destroy(self, instance):
        logger.info(
            "Document %s deleted by user %s.", instance.pk, self.request.user.pk
        )
        instance.delete()


class DocumentStatusView(APIView):
    """GET /api/documents/{id}/status/ — lightweight status summary."""

    permission_classes = [IsDocumentOwnerOrReadOnlyForStaff]

    def get(self, request, id):
        document = self._get_document_or_404(id, request)
        return Response(DocumentStatusService.get_status(document))

    @staticmethod
    def _get_document_or_404(document_id, request):
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist as exc:
            raise NotFound("Document not found.") from exc

        if not IsDocumentOwnerOrReadOnlyForStaff().has_object_permission(
            request, None, document
        ):
            raise NotFound("Document not found.")

        return document


class DocumentProcessingStatusView(DocumentStatusView):
    """
    GET /api/documents/{id}/processing-status/

    Returns the same status summary as DocumentStatusView today. Kept
    as a distinct endpoint (rather than reusing the same URL) because
    the future pipeline modules are expected to enrich this response
    with a full per-stage breakdown (see
    `services.DocumentProcessingService`) without changing the
    lightweight `/status/` endpoint's contract.
    """

    def get(self, request, id):
        document = self._get_document_or_404(id, request)
        payload = DocumentStatusService.get_status(document)
        payload["processing_stage"] = document.processing_stage
        payload["processing_stage_display"] = document.get_processing_stage_display()
        return Response(payload)


class DocumentParseView(APIView):
    """
    POST /api/documents/{id}/parse/

    Synchronously triggers the full ingestion pipeline for a document
    currently at READY_FOR_PARSING (or PARSED/FAILED, for re-processing),
    auto-chaining: Parser → Chunker → Embedding Generator → Vector Store
    → Knowledge Graph.

    As of Sprint 9, the full chain ends at INDEXED. If any stage fails,
    the response reports HTTP 422 and the document's final status
    reflects the failing stage.

    This remains a deliberately simple, synchronous trigger rather than
    an automatic-on-upload hook: the project has no task queue
    configured yet.
    """

    permission_classes = [IsDocumentOwnerOrReadOnlyForStaff]

    def post(self, request, id):
        document = DocumentStatusView._get_document_or_404(id, request)

        try:
            parsed_document = DocumentProcessingService.run_parser(document)
        except ParserError as exc:
            return Response(
                {"detail": str(exc), "status": document.status},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            chunk_collection = DocumentProcessingService.run_chunker(document, parsed_document)
        except ChunkingError as exc:
            return Response(
                {"detail": str(exc), "status": document.status},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            embedding_result = DocumentProcessingService.run_embedding_generator(document, chunk_collection)
        except EmbeddingError as exc:
            return Response(
                {"detail": str(exc), "status": document.status},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            DocumentProcessingService.store_in_vector_db(document, embedding_result)
        except VectorStoreError as exc:
            return Response(
                {"detail": str(exc), "status": document.status},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            DocumentProcessingService.update_knowledge_graph(document, parsed_document)
        except KnowledgeGraphError as exc:
            return Response(
                {"detail": str(exc), "status": document.status},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        response_serializer = DocumentDetailSerializer(
            document, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class SupportedFormatsView(APIView):
    """GET /api/documents/supported-formats/ — static upload constraints for client UX."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = SupportedFormatsSerializer(data=SupportedFormatsSerializer.build())
        serializer.is_valid()
        return Response(serializer.validated_data)
