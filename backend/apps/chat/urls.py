"""URL routes for the chat history API."""

from django.urls import path

from apps.chat.views import (
    ConversationDetailView,
    ConversationExportView,
    ConversationListView,
    ConversationMessageView,
    ConversationSearchView,
    ConversationStatsView,
)

app_name = "chat"

urlpatterns = [
    # Non-parameterized paths first
    path("stats/", ConversationStatsView.as_view(), name="stats"),
    path("conversations/", ConversationListView.as_view(), name="list"),
    path("conversations/search/", ConversationSearchView.as_view(), name="search"),
    # UUID-parameterized paths
    path("conversations/<uuid:conversation_id>/", ConversationDetailView.as_view(), name="detail"),
    path("conversations/<uuid:conversation_id>/messages/", ConversationMessageView.as_view(), name="messages"),
    path("conversations/<uuid:conversation_id>/export/", ConversationExportView.as_view(), name="export"),
]
