"""URL routes for the dashboard application."""

from django.urls import path

from apps.dashboard.views import (
    ChatView,
    CommandCenterView,
    DashboardOverviewView,
    UploadWorkspaceView,
)

app_name = "dashboard"

urlpatterns = [
    path("", DashboardOverviewView.as_view(), name="overview"),
    path("upload/", UploadWorkspaceView.as_view(), name="upload"),
    path("chat/", ChatView.as_view(), name="chat"),
    path("command-center/", CommandCenterView.as_view(), name="command-center"),
]
