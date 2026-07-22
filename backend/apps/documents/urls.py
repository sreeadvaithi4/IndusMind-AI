"""URL routes for the Document Management REST API."""

from django.urls import path

from apps.documents.views import (
    DocumentDetailView,
    DocumentListView,
    DocumentParseView,
    DocumentProcessingStatusView,
    DocumentStatusView,
    DocumentUploadView,
    RecentDocumentsView,
    SupportedFormatsView,
)

app_name = "documents"

urlpatterns = [
    path("upload/", DocumentUploadView.as_view(), name="upload"),
    path("recent/", RecentDocumentsView.as_view(), name="recent"),
    path("supported-formats/", SupportedFormatsView.as_view(), name="supported-formats"),
    path("<uuid:id>/", DocumentDetailView.as_view(), name="detail"),
    path("<uuid:id>/status/", DocumentStatusView.as_view(), name="status"),
    path(
        "<uuid:id>/processing-status/",
        DocumentProcessingStatusView.as_view(),
        name="processing-status",
    ),
    path("<uuid:id>/parse/", DocumentParseView.as_view(), name="parse"),
    path("", DocumentListView.as_view(), name="list"),
]
