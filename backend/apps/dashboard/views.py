"""
Views for the dashboard application.

Every view is a presentational TemplateView. Context data below is
representative static data standing in for the future ingestion, RAG,
knowledge graph, and processing-queue services — those services do not
exist yet (see PROJECT_CONTEXT.md, Pending Modules). Once they are
implemented, the corresponding `_get_*` methods will be replaced with
real service/repository calls without any change to the templates.
"""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView


class DashboardOverviewView(TemplateView):
    """Renders the main enterprise dashboard workspace."""

    template_name = "dashboard/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Dashboard — IndusMind AI"
        context["sidebar_items"] = self._get_sidebar_items()
        context["summary_cards"] = self._get_summary_cards()
        context["recent_documents"] = self._get_recent_documents()
        context["processing_pipeline"] = self._get_processing_pipeline()
        context["quick_actions"] = self._get_quick_actions()
        context["activity_feed"] = self._get_activity_feed()
        context["system_health"] = self._get_system_health()
        context["welcome"] = self._get_welcome_data()
        return context

    @staticmethod
    def _get_sidebar_items():
        return [
            {"label": "Dashboard", "icon": "squares-2x2", "url_name": "dashboard:overview", "active": True},
            {"label": "AI Chat", "icon": "chat-bubble-left-right", "url_name": None},
            {"label": "Upload Documents", "icon": "arrow-up-tray", "url_name": "dashboard:upload"},
            {"label": "My Documents", "icon": "document-text", "url_name": None},
            {"label": "Knowledge Graph", "icon": "share", "url_name": None},
            {"label": "Analytics", "icon": "chart-bar", "url_name": None},
            {"label": "Processing Queue", "icon": "queue-list", "url_name": None},
            {"label": "Settings", "icon": "cog-6-tooth", "url_name": None},
        ]

    @staticmethod
    def _get_welcome_data():
        return {
            "user_display_name": "Alex Morgan",
            "last_login": "Today at 08:42 AM",
            "recent_activity_count": 12,
        }

    @staticmethod
    def _get_quick_actions():
        return [
            {"label": "Upload Document", "icon": "arrow-up-tray", "url_name": "dashboard:upload", "style": "primary"},
            {"label": "Ask AI", "icon": "chat-bubble-left-right", "url_name": None, "style": "secondary"},
            {"label": "View Documents", "icon": "document-text", "url_name": None, "style": "secondary"},
            {"label": "Open Knowledge Graph", "icon": "share", "url_name": None, "style": "secondary"},
        ]

    @staticmethod
    def _get_summary_cards():
        return [
            {"label": "Total Documents", "value": 1284, "suffix": "", "icon": "document-text", "trend": "+8.2%"},
            {"label": "Documents Indexed", "value": 1197, "suffix": "", "icon": "check-circle", "trend": "+6.4%"},
            {"label": "Documents Processing", "value": 14, "suffix": "", "icon": "arrow-path", "trend": None},
            {"label": "Knowledge Graph Nodes", "value": 8452, "suffix": "", "icon": "share", "trend": "+3.1%"},
            {"label": "Embeddings Stored", "value": 214300, "suffix": "", "icon": "circle-stack", "trend": "+5.9%"},
            {"label": "Storage Used", "value": 62, "suffix": "%", "icon": "server", "trend": None, "is_gauge": True},
        ]

    @staticmethod
    def _get_recent_documents():
        return [
            {
                "name": "Turbine_Vibration_Analysis_Q3.pdf",
                "uploaded_by": "Alex Morgan",
                "uploaded_at": "2026-07-20 09:12",
                "pages": 42,
                "chunks": 186,
                "status": "indexed",
            },
            {
                "name": "Compressor_Failure_RCA_Report.docx",
                "uploaded_by": "Priya Nair",
                "uploaded_at": "2026-07-20 08:47",
                "pages": 18,
                "chunks": 74,
                "status": "embedding",
            },
            {
                "name": "Refinery_Safety_Checklist_2026.pdf",
                "uploaded_by": "James Chen",
                "uploaded_at": "2026-07-19 17:03",
                "pages": 9,
                "chunks": 0,
                "status": "chunking",
            },
            {
                "name": "Aerospace_Component_Spec_Rev4.xlsx",
                "uploaded_by": "Alex Morgan",
                "uploaded_at": "2026-07-19 15:21",
                "pages": 6,
                "chunks": 0,
                "status": "parsing",
            },
            {
                "name": "Fleet_Maintenance_Log_June.csv",
                "uploaded_by": "Sofia Reyes",
                "uploaded_at": "2026-07-19 11:58",
                "pages": 1,
                "chunks": 0,
                "status": "uploading",
            },
            {
                "name": "Legacy_Boiler_Manual_Scan.pdf",
                "uploaded_by": "James Chen",
                "uploaded_at": "2026-07-18 14:30",
                "pages": 120,
                "chunks": 0,
                "status": "failed",
            },
        ]

    @staticmethod
    def _get_processing_pipeline():
        return {
            "document_name": "Compressor_Failure_RCA_Report.docx",
            "stages": [
                {"label": "Uploading", "icon": "arrow-up-tray", "state": "complete", "progress": 100, "eta": None},
                {"label": "Parsing", "icon": "document-text", "state": "complete", "progress": 100, "eta": None},
                {"label": "Chunking", "icon": "squares-2x2", "state": "complete", "progress": 100, "eta": None},
                {"label": "Generating Embeddings", "icon": "cpu-chip", "state": "active", "progress": 64, "eta": "~18 sec remaining"},
                {"label": "Updating ChromaDB", "icon": "circle-stack", "state": "pending", "progress": 0, "eta": "~25 sec remaining"},
                {"label": "Updating Knowledge Graph", "icon": "share", "state": "pending", "progress": 0, "eta": "~40 sec remaining"},
                {"label": "Completed", "icon": "check-circle", "state": "pending", "progress": 0, "eta": None},
            ],
        }

    @staticmethod
    def _get_activity_feed():
        return [
            {
                "type": "upload",
                "icon": "arrow-up-tray",
                "message": "Sofia Reyes uploaded Fleet_Maintenance_Log_June.csv",
                "timestamp": "2 minutes ago",
            },
            {
                "type": "chat",
                "icon": "chat-bubble-left-right",
                "message": "AI Chat answered a query about compressor bearing failures",
                "timestamp": "11 minutes ago",
            },
            {
                "type": "indexed",
                "icon": "check-circle",
                "message": "Turbine_Vibration_Analysis_Q3.pdf finished indexing (186 chunks)",
                "timestamp": "38 minutes ago",
            },
            {
                "type": "system",
                "icon": "server",
                "message": "Knowledge graph rebuild completed — 8,452 nodes, 21,940 edges",
                "timestamp": "1 hour ago",
            },
            {
                "type": "system",
                "icon": "exclamation-triangle",
                "message": "Legacy_Boiler_Manual_Scan.pdf failed OCR — low scan quality",
                "timestamp": "Yesterday at 2:30 PM",
            },
        ]

    @staticmethod
    def _get_system_health():
        return [
            {"label": "Embedding Service", "status": "operational", "detail": "Gemini text-embedding-004"},
            {"label": "Knowledge Graph", "status": "operational", "detail": "NetworkX in-memory store"},
            {"label": "Vector Database", "status": "operational", "detail": "ChromaDB — 214.3K vectors"},
            {"label": "Gemini Connection", "status": "degraded", "detail": "Elevated latency (~1.4s avg)"},
        ]


@method_decorator(ensure_csrf_cookie, name="dispatch")
class UploadWorkspaceView(TemplateView):
    """
    Enterprise Upload Workspace.

    Decorated with `ensure_csrf_cookie` because this page's JavaScript
    (static/js/upload-workspace.js) makes unsafe (POST/DELETE) fetch/XHR
    requests directly to the apps.documents REST API without ever
    rendering a Django `{% csrf_token %}` form — without this decorator,
    Django never sets the `csrftoken` cookie the JS reads to satisfy
    DRF's SessionAuthentication CSRF check, and every upload/delete
    request would be rejected with 403.

    Presentational shell only — all document data (queue state, upload
    progress, recent documents, filtering) is fetched client-side from
    the existing `apps.documents` REST API via `static/js/upload-workspace.js`.
    This view supplies only the static, non-document context the page's
    layout needs (sidebar state, supported formats fallback, storage
    usage) — mirroring the same "static representative data" pattern
    already used by `DashboardOverviewView` for metrics that have no
    backing service yet (e.g. storage usage, which `apps.documents` does
    not currently expose via any endpoint).
    """

    template_name = "dashboard/upload_workspace.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Upload Workspace — IndusMind AI"
        context["sidebar_items"] = DashboardOverviewView._get_sidebar_items()
        for item in context["sidebar_items"]:
            item["active"] = item["url_name"] == "dashboard:upload"
        context["storage_usage"] = self._get_storage_usage()
        context["quick_tips"] = self._get_quick_tips()
        return context

    @staticmethod
    def _get_storage_usage():
        # apps.documents does not expose an aggregate storage-usage
        # endpoint yet (out of scope for this sprint's backend, which
        # is explicitly upload-workspace-frontend-only). Represented
        # the same way the dashboard already represents this metric.
        return {"used_gb": 24.6, "total_gb": 100, "percentage": 25}

    @staticmethod
    def _get_quick_tips():
        return [
            "PDF, DOCX, DOC, TXT, CSV, and XLSX files are supported.",
            "You can upload multiple files at once — each uploads independently.",
            "Large files may take longer; you can keep working while they upload.",
            "Parsing, chunking, and indexing begin automatically once a file reaches Ready for Parsing.",
        ]


@method_decorator(ensure_csrf_cookie, name="dispatch")
class ChatView(TemplateView):
    """
    Renders the AI Expert Copilot chat interface.

    The CSRF cookie is ensured so JavaScript can read it for API
    calls to /api/query/ (same pattern as the Upload Workspace).
    """

    template_name = "dashboard/chat.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "AI Copilot — IndusMind AI"
        return context


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CommandCenterView(TemplateView):
    """Renders the Operations Command Center."""

    template_name = "dashboard/command_center.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Operations Command Center — IndusMind AI"
        return context


@method_decorator(ensure_csrf_cookie, name="dispatch")
class HomePageView(TemplateView):
    """Company home page — shown after login."""

    template_name = "dashboard/home.html"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class DocumentsView(TemplateView):
    """Document upload and management page."""
    template_name = "dashboard/documents.html"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AnalyticsView(TemplateView):
    """Enterprise analytics page."""
    template_name = "dashboard/analytics.html"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class ChatHistoryView(TemplateView):
    """Chat history page."""
    template_name = "dashboard/chat_history.html"
