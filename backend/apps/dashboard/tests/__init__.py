"""
Tests for the Chat UI view and integration with the RAG pipeline.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity

User = get_user_model()


class ChatViewTests(TestCase):
    """Tests for the Chat page view."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def test_chat_page_requires_no_auth_for_template(self):
        # The template itself renders; auth is enforced at API level
        response = self.client.get(reverse("dashboard:chat"))
        self.assertEqual(response.status_code, 200)

    def test_chat_page_renders_template(self):
        self.client.login(username="alex", password="testpass123")
        response = self.client.get(reverse("dashboard:chat"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Industrial Expert Copilot")
        self.assertContains(response, "chatMessages")
        self.assertContains(response, "chatForm")

    def test_chat_page_includes_csrf(self):
        self.client.login(username="alex", password="testpass123")
        response = self.client.get(reverse("dashboard:chat"))
        # ensure_csrf_cookie should set the cookie
        self.assertIn("csrftoken", response.cookies)

    def test_chat_page_includes_js(self):
        self.client.login(username="alex", password="testpass123")
        response = self.client.get(reverse("dashboard:chat"))
        self.assertContains(response, "chat.js")

    def test_chat_page_includes_css(self):
        self.client.login(username="alex", password="testpass123")
        response = self.client.get(reverse("dashboard:chat"))
        self.assertContains(response, "chat.css")


class ChatAPIIntegrationTests(TestCase):
    """Tests that the /api/query/ endpoint works from the chat context."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1",
            entity_type="pump",
            name="Centrifugal Pump P-101A",
            source_document_ids=["doc-1"],
            confidence=0.8,
        ))

    def test_query_endpoint_returns_structured_response(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Tell me about pump P-101A", "session_id": "test"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answer", data)
        self.assertIn("confidence", data)
        self.assertIn("citations", data)
        self.assertIn("related_equipment", data)
        self.assertIn("suggested_followups", data)
        self.assertIn("intent", data)

    def test_query_with_equipment_intent(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "What pump is in the system?"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"]["intent"], "equipment_lookup")

    def test_query_session_memory(self):
        self.client.force_login(self.user)
        # First query
        self.client.post(
            "/api/query/",
            {"query": "Tell me about pump P-101A", "session_id": "sess-1"},
            content_type="application/json",
        )
        # Follow-up
        response = self.client.post(
            "/api/query/",
            {"query": "What is it connected to?", "session_id": "sess-1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_query_empty_returns_400(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": ""},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_query_unauthenticated_returns_403(self):
        response = self.client.post(
            "/api/query/",
            {"query": "test"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_response_has_confidence_score(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Show me P-101A details"},
            content_type="application/json",
        )
        data = response.json()
        self.assertIsInstance(data["confidence"], (int, float))
        self.assertGreaterEqual(data["confidence"], 0.0)
        self.assertLessEqual(data["confidence"], 1.0)

    def test_response_has_citations_structure(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Tell me about P-101A"},
            content_type="application/json",
        )
        data = response.json()
        for citation in data["citations"]:
            self.assertIn("source_type", citation)
            self.assertIn("confidence", citation)
