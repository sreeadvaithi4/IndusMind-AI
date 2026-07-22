"""
Tests for the Hybrid RAG Pipeline and Agent Orchestrator.

Tests cover:
    - RAG Configuration
    - Query intent detection
    - Hybrid retrieval (KG search, ranking, dedup)
    - Context builder (prompt construction, citations, token limits)
    - Conversation memory (session CRUD)
    - Orchestrator (full pipeline with mocked LLM)
    - LLM service (error classification)
    - API endpoints (auth, validation)
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from agents.config import RAGConfig
from agents.context import ContextBuilder
from agents.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError
from agents.llm import GeminiService
from agents.memory import ConversationMemory
from agents.orchestrator import QueryOrchestrator, QueryIntent
from agents.retrieval import RAGRetrievalService, RetrievalHit, RetrievalResult
from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity

User = get_user_model()


class RAGConfigTests(TestCase):
    """Tests for RAG configuration."""

    def test_from_settings_defaults(self):
        config = RAGConfig.from_settings()
        self.assertEqual(config.top_k, 10)
        self.assertEqual(config.llm_model, "gemini-1.5-flash")
        self.assertEqual(config.temperature, 0.3)

    @override_settings(RAG_TOP_K=20, RAG_TEMPERATURE=0.7)
    def test_from_settings_custom(self):
        config = RAGConfig.from_settings()
        self.assertEqual(config.top_k, 20)
        self.assertEqual(config.temperature, 0.7)


class IntentDetectionTests(TestCase):
    """Tests for query intent detection."""

    def test_detects_maintenance_intent(self):
        intent = QueryOrchestrator.detect_intent("What is the maintenance schedule for P-101?")
        self.assertEqual(intent.intent, "maintenance")
        self.assertGreater(intent.confidence, 0)

    def test_detects_equipment_intent(self):
        intent = QueryOrchestrator.detect_intent("Show me details for pump P-101A")
        self.assertEqual(intent.intent, "equipment_lookup")

    def test_detects_compliance_intent(self):
        intent = QueryOrchestrator.detect_intent("What ISO standards apply?")
        self.assertEqual(intent.intent, "compliance")

    def test_detects_drawing_intent(self):
        intent = QueryOrchestrator.detect_intent("Show me the P&ID for area 3")
        self.assertEqual(intent.intent, "drawing_lookup")

    def test_detects_document_intent(self):
        intent = QueryOrchestrator.detect_intent("Find the SOP for pump maintenance")
        # Could be maintenance or document — either is valid
        self.assertIn(intent.intent, ("maintenance", "document_lookup"))

    def test_general_question_fallback(self):
        intent = QueryOrchestrator.detect_intent("Hello, how are you?")
        self.assertEqual(intent.intent, "general_question")

    def test_intent_has_entities(self):
        intent = QueryOrchestrator.detect_intent("What pump is in area 3?")
        self.assertGreater(len(intent.entities), 0)


class RetrievalServiceTests(TestCase):
    """Tests for the RAG Retrieval Service."""

    def setUp(self):
        GraphService.reset()
        # Add test entities to the knowledge graph
        GraphService.add_entity(Entity(
            entity_id="e1",
            entity_type="pump",
            name="Centrifugal Pump P-101A",
            source_document_ids=["doc-1"],
            confidence=0.8,
        ))
        GraphService.add_entity(Entity(
            entity_id="e2",
            entity_type="valve",
            name="Control Valve V-201",
            source_document_ids=["doc-1"],
            confidence=0.7,
        ))

    def test_search_knowledge_graph(self):
        hits = RAGRetrievalService.search_knowledge_graph("pump")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].source, "knowledge_graph")
        self.assertIn("pump", hits[0].content.lower())

    def test_search_kg_by_entity_type(self):
        hits = RAGRetrievalService.search_knowledge_graph("", entity_type="valve")
        # search with empty query matches all names — check type filter
        valve_hits = [h for h in hits if "valve" in h.content.lower()]
        self.assertGreater(len(valve_hits), 0)

    def test_retrieve_without_embedding_uses_kg_only(self):
        result = RAGRetrievalService.retrieve(
            query="pump",
            query_embedding=None,
        )
        self.assertIsInstance(result, RetrievalResult)
        self.assertIn("knowledge_graph", result.sources_queried)
        self.assertNotIn("chromadb", result.sources_queried)

    def test_retrieve_deduplicates(self):
        result = RAGRetrievalService.retrieve(
            query="Centrifugal Pump P-101A",
            query_embedding=None,
        )
        # Should not have duplicate content
        contents = [h.content for h in result.hits]
        self.assertEqual(len(contents), len(set(contents)))

    def test_retrieve_respects_top_k(self):
        config = RAGConfig(top_k=1, api_key="")
        result = RAGRetrievalService.retrieve(
            query="pump valve",
            query_embedding=None,
            config=config,
        )
        self.assertLessEqual(result.total_hits, 1)


class ContextBuilderTests(TestCase):
    """Tests for the Context Builder."""

    def test_builds_context_from_hits(self):
        retrieval = RetrievalResult(
            query="pump maintenance",
            hits=[
                RetrievalHit(
                    source="chromadb",
                    content="Pump P-101 requires quarterly maintenance.",
                    score=0.9,
                    document_id="doc-1",
                    chunk_id="chunk-1",
                    metadata={"source_filename": "manual.pdf"},
                ),
            ],
            total_hits=1,
        )

        context = ContextBuilder.build("pump maintenance", retrieval)
        self.assertIn("P-101", context.context_text)
        self.assertEqual(len(context.citations), 1)
        self.assertIn("[Source 1]", context.user_prompt)

    def test_respects_token_limit(self):
        # Create a huge retrieval result
        long_content = "A" * 50000
        retrieval = RetrievalResult(
            query="test",
            hits=[
                RetrievalHit(source="chromadb", content=long_content, score=0.9),
            ],
            total_hits=1,
        )

        config = RAGConfig(max_context_tokens=100)
        context = ContextBuilder.build("test", retrieval, config=config)
        self.assertTrue(context.truncated)
        self.assertLessEqual(len(context.context_text), 100 * 4 + 100)

    def test_includes_conversation_history(self):
        retrieval = RetrievalResult(query="follow up", hits=[], total_hits=0)
        history = [{"role": "user", "content": "What pump?"}]
        context = ContextBuilder.build("follow up", retrieval, conversation_history=history)
        self.assertIn("What pump?", context.user_prompt)

    def test_empty_retrieval_produces_valid_context(self):
        retrieval = RetrievalResult(query="test", hits=[], total_hits=0)
        context = ContextBuilder.build("test", retrieval)
        self.assertIn("test", context.user_prompt)
        self.assertEqual(len(context.citations), 0)


class ConversationMemoryTests(TestCase):
    """Tests for session memory."""

    def setUp(self):
        ConversationMemory.reset()

    def test_create_session(self):
        session = ConversationMemory.get_or_create("sess-1")
        self.assertEqual(session.session_id, "sess-1")
        self.assertEqual(len(session.turns), 0)

    def test_add_turns(self):
        session = ConversationMemory.get_or_create("sess-1")
        session.add_turn("user", "Hello")
        session.add_turn("assistant", "Hi there!")
        self.assertEqual(len(session.turns), 2)

    def test_get_history(self):
        session = ConversationMemory.get_or_create("sess-1")
        session.add_turn("user", "Q1")
        session.add_turn("assistant", "A1")
        history = session.get_history()
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Q1")

    def test_max_turns_eviction(self):
        session = ConversationMemory.get_or_create("sess-1")
        session.max_turns = 3
        for i in range(5):
            session.add_turn("user", f"Message {i}")
        self.assertEqual(len(session.turns), 3)

    def test_delete_session(self):
        ConversationMemory.get_or_create("sess-1")
        self.assertTrue(ConversationMemory.delete("sess-1"))
        self.assertIsNone(ConversationMemory.get("sess-1"))

    def test_clear_session(self):
        session = ConversationMemory.get_or_create("sess-1")
        session.add_turn("user", "Hello")
        session.clear()
        self.assertEqual(len(session.turns), 0)


class LLMServiceTests(TestCase):
    """Tests for the Gemini LLM service."""

    def test_classify_rate_limit(self):
        exc = Exception("429 Resource exhausted: quota exceeded")
        result = GeminiService._classify_exception(exc)
        self.assertIsInstance(result, LLMRateLimitError)

    def test_classify_timeout(self):
        exc = Exception("Request timed out")
        result = GeminiService._classify_exception(exc)
        self.assertIsInstance(result, LLMTimeoutError)

    def test_classify_generic(self):
        exc = Exception("Something else")
        result = GeminiService._classify_exception(exc)
        self.assertIsInstance(result, LLMError)

    def test_empty_prompt_raises(self):
        config = RAGConfig(api_key="fake-key")
        with self.assertRaises(LLMError):
            GeminiService.generate("", config=config)

    def test_missing_api_key_raises(self):
        config = RAGConfig(api_key="")
        with self.assertRaises(LLMError):
            GeminiService.generate("Hello", config=config)


class OrchestratorTests(TestCase):
    """Tests for the Query Orchestrator."""

    def setUp(self):
        GraphService.reset()
        ConversationMemory.reset()
        GraphService.add_entity(Entity(
            entity_id="e1",
            entity_type="pump",
            name="Pump P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_process_empty_query(self):
        response = QueryOrchestrator.process_query("")
        self.assertEqual(response.answer, "Please provide a question.")
        self.assertEqual(response.confidence, 0.0)

    def test_process_query_without_api_key(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "What pump is in the system?",
            config=config,
        )
        # Should return fallback answer from retrieval
        self.assertIsInstance(response.answer, str)
        self.assertGreater(len(response.answer), 0)
        self.assertIn(response.intent.intent, ("equipment_lookup", "general_question"))

    def test_process_query_returns_citations(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Tell me about Pump P-101A",
            config=config,
        )
        # Should have some structured response
        self.assertIsNotNone(response.intent)
        self.assertIsInstance(response.citations, list)
        self.assertIsInstance(response.related_equipment, list)

    def test_conversation_memory_maintained(self):
        config = RAGConfig(api_key="")
        QueryOrchestrator.process_query(
            "What is P-101A?",
            session_id="sess-test",
            config=config,
        )
        session = ConversationMemory.get("sess-test")
        self.assertIsNotNone(session)
        self.assertEqual(len(session.turns), 2)  # user + assistant

    def test_response_structure(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Show equipment",
            config=config,
        )
        result_dict = response.to_dict()
        self.assertIn("answer", result_dict)
        self.assertIn("confidence", result_dict)
        self.assertIn("citations", result_dict)
        self.assertIn("intent", result_dict)
        self.assertIn("suggested_followups", result_dict)


class SearchAPITests(APITestCase):
    """Tests for the REST API search endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1",
            entity_type="pump",
            name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_kg_search_requires_auth(self):
        response = self.client.post("/api/search/knowledge-graph/", {"query": "pump"})
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_kg_search_requires_query(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/search/knowledge-graph/", {"query": ""})
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_kg_search_returns_results(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/search/knowledge-graph/",
            {"query": "P-101"},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertGreater(response.data["total"], 0)

    def test_drawing_search_requires_auth(self):
        response = self.client.post("/api/search/drawings/", {"query": "pump"})
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_hybrid_query_requires_auth(self):
        response = self.client.post("/api/query/", {"query": "What pump?"})
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_hybrid_query_returns_structured_response(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Tell me about P-101A"},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertIn("answer", response.data)
        self.assertIn("confidence", response.data)
        self.assertIn("citations", response.data)
        self.assertIn("intent", response.data)
