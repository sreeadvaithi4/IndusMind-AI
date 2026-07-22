"""
Tests for persistent chat history (apps.chat).

Covers: models, services, API endpoints, authorization, search, export.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from apps.chat.models import Conversation, ConversationStatus, Message, MessageRole
from apps.chat.services import ConversationService, MessageService
from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity

User = get_user_model()


class ConversationModelTests(TestCase):
    """Tests for the Conversation model."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def test_create_conversation(self):
        conv = Conversation.objects.create(user=self.user, title="Test Chat")
        self.assertEqual(conv.title, "Test Chat")
        self.assertEqual(conv.status, ConversationStatus.ACTIVE)
        self.assertFalse(conv.pinned)
        self.assertEqual(conv.message_count, 0)

    def test_conversation_ordering(self):
        c1 = Conversation.objects.create(user=self.user, title="First")
        c2 = Conversation.objects.create(user=self.user, title="Second")
        conversations = list(Conversation.objects.filter(user=self.user))
        # Most recent first
        self.assertEqual(conversations[0].id, c2.id)


class MessageModelTests(TestCase):
    """Tests for the Message model."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.conv = Conversation.objects.create(user=self.user, title="Test")

    def test_create_message(self):
        msg = Message.objects.create(
            conversation=self.conv, role=MessageRole.USER, content="Hello"
        )
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "Hello")

    def test_message_ordering(self):
        m1 = Message.objects.create(conversation=self.conv, role="user", content="Q1")
        m2 = Message.objects.create(conversation=self.conv, role="assistant", content="A1")
        messages = list(self.conv.messages.all())
        self.assertEqual(messages[0].id, m1.id)
        self.assertEqual(messages[1].id, m2.id)


class ConversationServiceTests(TestCase):
    """Tests for ConversationService."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.other = User.objects.create_user(username="priya", password="testpass123")

    def test_create(self):
        conv = ConversationService.create(self.user, "My Chat")
        self.assertEqual(conv.title, "My Chat")
        self.assertEqual(conv.user, self.user)

    def test_get_scoped_to_user(self):
        conv = ConversationService.create(self.user)
        self.assertIsNotNone(ConversationService.get(conv.id, self.user))
        self.assertIsNone(ConversationService.get(conv.id, self.other))

    def test_list_for_user(self):
        ConversationService.create(self.user, "Chat 1")
        ConversationService.create(self.user, "Chat 2")
        ConversationService.create(self.other, "Other Chat")
        results = ConversationService.list_for_user(self.user)
        self.assertEqual(len(results), 2)

    def test_update_title(self):
        conv = ConversationService.create(self.user)
        ConversationService.update(conv, title="Renamed")
        conv.refresh_from_db()
        self.assertEqual(conv.title, "Renamed")

    def test_pin(self):
        conv = ConversationService.create(self.user)
        ConversationService.update(conv, pinned=True)
        conv.refresh_from_db()
        self.assertTrue(conv.pinned)

    def test_archive(self):
        conv = ConversationService.create(self.user)
        ConversationService.update(conv, status=ConversationStatus.ARCHIVED)
        conv.refresh_from_db()
        self.assertEqual(conv.status, ConversationStatus.ARCHIVED)

    def test_delete(self):
        conv = ConversationService.create(self.user)
        cid = conv.id
        ConversationService.delete(conv)
        self.assertFalse(Conversation.objects.filter(id=cid).exists())

    def test_search(self):
        ConversationService.create(self.user, "Pump P101 Discussion")
        ConversationService.create(self.user, "Valve Maintenance")
        results = ConversationService.search(self.user, "pump")
        self.assertEqual(len(results), 1)

    def test_get_stats(self):
        ConversationService.create(self.user, "Chat 1")
        ConversationService.create(self.user, "Chat 2")
        stats = ConversationService.get_stats(self.user)
        self.assertEqual(stats["total_conversations"], 2)
        self.assertEqual(stats["active"], 2)


class MessageServiceTests(TestCase):
    """Tests for MessageService."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.conv = ConversationService.create(self.user)

    def test_add_user_message(self):
        msg = MessageService.add_user_message(self.conv, "What is P-101?")
        self.assertEqual(msg.role, "user")
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.message_count, 1)

    def test_add_assistant_message(self):
        MessageService.add_user_message(self.conv, "Question")
        response_data = {
            "answer": "P-101 is a centrifugal pump.",
            "confidence": 0.85,
            "citations": [{"source_type": "document"}],
            "related_equipment": ["P-101A"],
            "related_documents": ["doc-1"],
            "knowledge_graph_references": ["e1"],
            "drawing_references": ["DWG-001"],
            "suggested_followups": ["Show maintenance history"],
            "duration_seconds": 1.5,
            "retrieval_summary": {"total_hits": 3},
        }
        msg = MessageService.add_assistant_message(self.conv, response_data)
        self.assertEqual(msg.confidence, 0.85)
        self.conv.refresh_from_db()
        self.assertIn("P-101A", self.conv.equipment_mentioned)
        self.assertEqual(self.conv.message_count, 2)

    def test_auto_title_generation(self):
        conv = ConversationService.create(self.user)
        self.assertEqual(conv.title, "New Conversation")
        MessageService.add_user_message(conv, "What maintenance does P-101 need?")
        MessageService.add_assistant_message(conv, {"answer": "..."})
        conv.refresh_from_db()
        self.assertIn("P-101", conv.title)

    def test_get_history(self):
        MessageService.add_user_message(self.conv, "Q1")
        MessageService.add_assistant_message(self.conv, {"answer": "A1"})
        history = MessageService.get_history(self.conv)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")

    def test_export_markdown(self):
        MessageService.add_user_message(self.conv, "What is P-101?")
        MessageService.add_assistant_message(self.conv, {
            "answer": "P-101 is a pump.",
            "confidence": 0.9,
            "related_equipment": ["P-101"],
        })
        export = MessageService.export_conversation(self.conv)
        self.assertIn("P-101", export)
        self.assertIn("User", export)
        self.assertIn("Assistant", export)


class ChatAPITests(APITestCase):
    """Tests for the chat REST API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.other = User.objects.create_user(username="priya", password="testpass123")
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_create_conversation(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/chat/conversations/",
            {"title": "My Chat"},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "My Chat")

    def test_list_conversations(self):
        self.client.force_authenticate(self.user)
        self.client.post("/api/chat/conversations/", {"title": "C1"}, format="json")
        self.client.post("/api/chat/conversations/", {"title": "C2"}, format="json")
        response = self.client.get("/api/chat/conversations/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

    def test_get_conversation_detail(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", {"title": "Test"}, format="json")
        cid = create_resp.data["id"]
        response = self.client.get(f"/api/chat/conversations/{cid}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test")
        self.assertIn("messages", response.data)

    def test_other_user_cannot_access(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", {"title": "Private"}, format="json")
        cid = create_resp.data["id"]

        self.client.force_authenticate(self.other)
        response = self.client.get(f"/api/chat/conversations/{cid}/")
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_rename_conversation(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", format="json")
        cid = create_resp.data["id"]
        response = self.client.patch(
            f"/api/chat/conversations/{cid}/",
            {"title": "Renamed Chat"},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Renamed Chat")

    def test_pin_conversation(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", format="json")
        cid = create_resp.data["id"]
        response = self.client.patch(
            f"/api/chat/conversations/{cid}/",
            {"pinned": True},
            format="json",
        )
        self.assertEqual(response.data["pinned"], True)

    def test_delete_conversation(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", format="json")
        cid = create_resp.data["id"]
        response = self.client.delete(f"/api/chat/conversations/{cid}/")
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

    def test_send_message_and_get_response(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", format="json")
        cid = create_resp.data["id"]
        response = self.client.post(
            f"/api/chat/conversations/{cid}/messages/",
            {"query": "Tell me about P-101A"},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertIn("answer", response.data)
        self.assertIn("confidence", response.data)

    def test_search_conversations(self):
        self.client.force_authenticate(self.user)
        self.client.post("/api/chat/conversations/", {"title": "Pump P101 Chat"}, format="json")
        self.client.post("/api/chat/conversations/", {"title": "Valve Discussion"}, format="json")
        response = self.client.get("/api/chat/conversations/search/?q=pump")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)

    def test_export_conversation(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", {"title": "Export Test"}, format="json")
        cid = create_resp.data["id"]
        response = self.client.get(f"/api/chat/conversations/{cid}/export/?export_format=markdown")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertIn("content", response.data)
        self.assertIn("Export Test", response.data["content"])

    def test_get_stats(self):
        self.client.force_authenticate(self.user)
        self.client.post("/api/chat/conversations/", format="json")
        response = self.client.get("/api/chat/stats/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertIn("total_conversations", response.data)

    def test_unauthenticated_access_denied(self):
        response = self.client.get("/api/chat/conversations/")
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_conversation_persists_after_messages(self):
        self.client.force_authenticate(self.user)
        create_resp = self.client.post("/api/chat/conversations/", format="json")
        cid = create_resp.data["id"]

        # Send a message
        self.client.post(
            f"/api/chat/conversations/{cid}/messages/",
            {"query": "What is P-101A?"},
            format="json",
        )

        # Retrieve — should have messages
        response = self.client.get(f"/api/chat/conversations/{cid}/")
        self.assertGreater(response.data["message_count"], 0)
        self.assertGreater(len(response.data["messages"]), 0)
