"""
Root URL configuration for IndusMind AI.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.dashboard.views import (
    AnalyticsView,
    ChatHistoryView,
    ChatView,
    CommandCenterView,
    DocumentsView,
    HomePageView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("django.contrib.auth.urls")),

    # Main pages
    path("", auth_views.LoginView.as_view(), name="login-root"),
    path("home/", HomePageView.as_view(), name="home"),
    path("chatbot/", ChatView.as_view(), name="chatbot"),
    path("documents/", DocumentsView.as_view(), name="documents"),
    path("dashboard/", CommandCenterView.as_view(), name="dashboard"),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
    path("history/", ChatHistoryView.as_view(), name="history"),

    # APIs
    path("api/documents/", include("apps.documents.urls")),
    path("api/chat/", include("apps.chat.urls")),
    path("api/", include("api.urls")),
    # Login page LAST (catches "/" only)
    path("", auth_views.LoginView.as_view(), name="login-root"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)