"""
Service layer for persistent chat history.

Views delegate to these services — no direct model access from views.
"""

import logging

from django.db.models import Q

from apps.chat.models import Conversation, ConversationStatus, Message, MessageRole

logger = logging.getLogger("apps.chat")


class ConversationService:
    """CRUD and search operations for conversations."""

    @staticmethod
    def create(user, title="New Conversation") -> Conversation:
        """Creates a new conversation for a user."""
        conversation = Conversation.objects.create(user=user, title=title)
        logger.info("Created conversation %s for user %s.", conversation.id, user.pk)
        return conversation

    @staticmethod
    def get(conversation_id, user) -> Conversation | None:
        """Gets a conversation by ID, scoped to the user."""
        try:
            return Conversation.objects.get(id=conversation_id, user=user)
        except Conversation.DoesNotExist:
            return None

    @staticmethod
    def list_for_user(user, status=None, pinned_only=False, limit=50):
        """Lists conversations for a user, ordered by most recent."""
        qs = Conversation.objects.filter(user=user)
        if status:
            qs = qs.filter(status=status)
        if pinned_only:
            qs = qs.filter(pinned=True)
        return qs[:limit]

    @staticmethod
    def update(conversation, **kwargs) -> Conversation:
        """Updates conversation fields."""
        allowed = {"title", "status", "pinned", "summary", "tags",
                   "equipment_mentioned", "documents_used",
                   "knowledge_graph_nodes", "drawing_references"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(conversation, key, value)
        conversation.save()
        return conversation

    @staticmethod
    def delete(conversation) -> None:
        """Deletes a conversation and all its messages."""
        logger.info("Deleting conversation %s.", conversation.id)
        conversation.delete()

    @staticmethod
    def search(user, query, limit=20):
        """Searches conversations by title, tags, equipment, or content."""
        qs = Conversation.objects.filter(user=user)
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(equipment_mentioned__icontains=query)
                | Q(documents_used__icontains=query)
                | Q(tags__icontains=query)
            )
        return qs[:limit]

    @staticmethod
    def get_stats(user) -> dict:
        """Returns conversation analytics for a user."""
        total = Conversation.objects.filter(user=user).count()
        active = Conversation.objects.filter(
            user=user, status=ConversationStatus.ACTIVE
        ).count()
        pinned = Conversation.objects.filter(user=user, pinned=True).count()
        archived = Conversation.objects.filter(
            user=user, status=ConversationStatus.ARCHIVED
        ).count()

        # Aggregate metadata
        all_equipment = []
        all_documents = []
        for conv in Conversation.objects.filter(user=user)[:100]:
            all_equipment.extend(conv.equipment_mentioned or [])
            all_documents.extend(conv.documents_used or [])

        from collections import Counter
        top_equipment = Counter(all_equipment).most_common(10)
        top_documents = Counter(all_documents).most_common(10)

        return {
            "total_conversations": total,
            "active": active,
            "pinned": pinned,
            "archived": archived,
            "top_equipment": [{"name": k, "count": v} for k, v in top_equipment],
            "top_documents": [{"name": k, "count": v} for k, v in top_documents],
        }


class MessageService:
    """CRUD operations for messages within conversations."""

    @staticmethod
    def add_user_message(conversation, content) -> Message:
        """Adds a user message to a conversation."""
        msg = Message.objects.create(
            conversation=conversation,
            role=MessageRole.USER,
            content=content,
        )
        conversation.message_count = conversation.messages.count()
        conversation.save(update_fields=["message_count", "updated_at"])
        return msg

    @staticmethod
    def add_assistant_message(conversation, response_data) -> Message:
        """
        Adds an assistant message from an orchestrator response dict.
        Also updates conversation metadata.
        """
        msg = Message.objects.create(
            conversation=conversation,
            role=MessageRole.ASSISTANT,
            content=response_data.get("answer", ""),
            confidence=response_data.get("confidence", 0.0),
            citations=response_data.get("citations", []),
            knowledge_graph_refs=response_data.get("knowledge_graph_references", []),
            drawing_refs=response_data.get("drawing_references", []),
            related_equipment=response_data.get("related_equipment", []),
            related_documents=response_data.get("related_documents", []),
            suggested_followups=response_data.get("suggested_followups", []),
            token_usage=response_data.get("retrieval_summary", {}).get("total_hits", 0),
            response_time_seconds=response_data.get("duration_seconds", 0.0),
        )

        # Update conversation metadata
        conversation.message_count = conversation.messages.count()

        # Accumulate equipment/documents/KG refs
        equipment = set(conversation.equipment_mentioned or [])
        equipment.update(response_data.get("related_equipment", []))
        conversation.equipment_mentioned = list(equipment)[:50]

        documents = set(conversation.documents_used or [])
        documents.update(response_data.get("related_documents", []))
        conversation.documents_used = list(documents)[:50]

        kg_nodes = set(conversation.knowledge_graph_nodes or [])
        kg_nodes.update(response_data.get("knowledge_graph_references", []))
        conversation.knowledge_graph_nodes = list(kg_nodes)[:50]

        drawing_refs = set(conversation.drawing_references or [])
        drawing_refs.update(response_data.get("drawing_references", []))
        conversation.drawing_references = list(drawing_refs)[:20]

        # Auto-generate title from first user message if still default
        if conversation.title == "New Conversation":
            first_user = conversation.messages.filter(role=MessageRole.USER).first()
            if first_user:
                conversation.title = first_user.content[:80].strip()

        conversation.save()
        return msg

    @staticmethod
    def get_history(conversation, limit=50) -> list[dict]:
        """Returns message history as a list of dicts for context."""
        messages = conversation.messages.order_by("created_at")[:limit]
        return [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "confidence": m.confidence,
                "citations": m.citations,
                "related_equipment": m.related_equipment,
                "drawing_refs": m.drawing_refs,
                "suggested_followups": m.suggested_followups,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]

    @staticmethod
    def export_conversation(conversation, format="markdown") -> str:
        """
        Exports a conversation in the specified format.

        Supported: 'markdown', 'text'
        """
        messages = conversation.messages.order_by("created_at")
        lines = [f"# {conversation.title}\n"]
        lines.append(f"*Created: {conversation.created_at.strftime('%Y-%m-%d %H:%M')}*\n")

        if conversation.equipment_mentioned:
            lines.append(f"**Equipment:** {', '.join(conversation.equipment_mentioned)}\n")

        lines.append("---\n")

        for msg in messages:
            if msg.role == "user":
                lines.append(f"## 🧑 User\n{msg.content}\n")
            else:
                lines.append(f"## 🤖 Assistant\n{msg.content}\n")
                if msg.confidence:
                    lines.append(f"*Confidence: {int(msg.confidence * 100)}%*\n")
                if msg.related_equipment:
                    lines.append(f"*Equipment: {', '.join(msg.related_equipment)}*\n")
                if msg.citations:
                    lines.append(f"*Sources: {len(msg.citations)} citations*\n")
            lines.append("---\n")

        return "\n".join(lines)
