"""
REST API views for persistent chat history.

All views enforce user ownership — users can only access their own
conversations.
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.orchestrator import QueryOrchestrator
from apps.chat.models import Conversation
from apps.chat.services import ConversationService, MessageService

logger = logging.getLogger("apps.chat")


class ConversationListView(APIView):
    """
    GET  /api/chat/conversations/ — list user's conversations
    POST /api/chat/conversations/ — create a new conversation
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get("status")
        pinned = request.query_params.get("pinned") == "true"
        conversations = ConversationService.list_for_user(
            request.user, status=status_filter, pinned_only=pinned
        )
        data = [
            {
                "id": str(c.id),
                "title": c.title,
                "status": c.status,
                "pinned": c.pinned,
                "message_count": c.message_count,
                "equipment_mentioned": c.equipment_mentioned,
                "updated_at": c.updated_at.isoformat(),
                "created_at": c.created_at.isoformat(),
            }
            for c in conversations
        ]
        return Response({"conversations": data, "total": len(data)})

    def post(self, request):
        title = request.data.get("title", "New Conversation")
        conversation = ConversationService.create(request.user, title=title)
        return Response(
            {"id": str(conversation.id), "title": conversation.title},
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(APIView):
    """
    GET    /api/chat/conversations/{id}/ — get conversation with messages
    PATCH  /api/chat/conversations/{id}/ — update (rename, pin, archive)
    DELETE /api/chat/conversations/{id}/ — delete conversation
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conv = ConversationService.get(conversation_id, request.user)
        if not conv:
            return Response(
                {"detail": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        messages = MessageService.get_history(conv, limit=100)
        return Response({
            "id": str(conv.id),
            "title": conv.title,
            "status": conv.status,
            "pinned": conv.pinned,
            "summary": conv.summary,
            "equipment_mentioned": conv.equipment_mentioned,
            "documents_used": conv.documents_used,
            "knowledge_graph_nodes": conv.knowledge_graph_nodes,
            "drawing_references": conv.drawing_references,
            "tags": conv.tags,
            "message_count": conv.message_count,
            "messages": messages,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
        })

    def patch(self, request, conversation_id):
        conv = ConversationService.get(conversation_id, request.user)
        if not conv:
            return Response(
                {"detail": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        allowed_fields = {"title", "pinned", "status", "tags"}
        updates = {k: v for k, v in request.data.items() if k in allowed_fields}
        if not updates:
            return Response(
                {"detail": "No valid fields to update."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ConversationService.update(conv, **updates)
        return Response({"id": str(conv.id), "title": conv.title, "status": conv.status, "pinned": conv.pinned})

    def delete(self, request, conversation_id):
        conv = ConversationService.get(conversation_id, request.user)
        if not conv:
            return Response(
                {"detail": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        ConversationService.delete(conv)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationMessageView(APIView):
    """
    POST /api/chat/conversations/{id}/messages/ — send a message and get AI response

    This is the primary chat endpoint. It:
    1. Validates the conversation belongs to the user
    2. Saves the user message
    3. Invokes the existing QueryOrchestrator (hybrid RAG pipeline)
    4. Saves the assistant response
    5. Returns the structured response
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = ConversationService.get(conversation_id, request.user)
        if not conv:
            return Response(
                {"detail": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        query = request.data.get("query", "").strip()
        if not query:
            return Response(
                {"detail": "query is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save user message
        MessageService.add_user_message(conv, query)

        # Get conversation history for context
        history = MessageService.get_history(conv, limit=20)
        conversation_history = [
            {"role": m["role"], "content": m["content"]} for m in history[:-1]
        ]

        # Embed query for semantic search (optional — graceful fallback)
        query_embedding = None
        try:
            from api.views import SemanticSearchView
            query_embedding = SemanticSearchView._embed_query(query)
        except Exception:
            pass

        # Invoke the existing orchestrator (reuse, not duplicate!)
        response = QueryOrchestrator.process_query(
            query=query,
            session_id=str(conv.id),
            query_embedding=query_embedding,
        )

        # Save assistant message
        response_data = response.to_dict()
        MessageService.add_assistant_message(conv, response_data)

        return Response(response_data)


class ConversationSearchView(APIView):
    """
    GET /api/chat/conversations/search/?q=pump — search conversations
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response(
                {"detail": "q parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        results = ConversationService.search(request.user, query)
        data = [
            {
                "id": str(c.id),
                "title": c.title,
                "message_count": c.message_count,
                "equipment_mentioned": c.equipment_mentioned,
                "updated_at": c.updated_at.isoformat(),
            }
            for c in results
        ]
        return Response({"results": data, "total": len(data)})


class ConversationExportView(APIView):
    """
    GET /api/chat/conversations/{id}/export/?format=markdown
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conv = ConversationService.get(conversation_id, request.user)
        if not conv:
            return Response(
                {"detail": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        fmt = request.query_params.get("export_format", "markdown")
        content = MessageService.export_conversation(conv, format=fmt)
        return Response({"format": fmt, "content": content, "title": conv.title})


class ConversationStatsView(APIView):
    """
    GET /api/chat/stats/ — conversation analytics for the user
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = ConversationService.get_stats(request.user)
        return Response(stats)
