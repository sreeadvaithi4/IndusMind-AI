"""URL configuration for the search/query API."""

from django.urls import path

from api.views import (
    CommandCenterView,
    DrawingSearchView,
    ExecutiveBriefingView,
    HybridQueryView,
    KnowledgeGraphSearchView,
    SemanticSearchView,
)

app_name = "api"

urlpatterns = [
    path("search/semantic/", SemanticSearchView.as_view(), name="semantic-search"),
    path("search/knowledge-graph/", KnowledgeGraphSearchView.as_view(), name="kg-search"),
    path("search/drawings/", DrawingSearchView.as_view(), name="drawing-search"),
    path("query/", HybridQueryView.as_view(), name="hybrid-query"),
    path("briefing/", ExecutiveBriefingView.as_view(), name="executive-briefing"),
    path("command-center/", CommandCenterView.as_view(), name="command-center"),
]
