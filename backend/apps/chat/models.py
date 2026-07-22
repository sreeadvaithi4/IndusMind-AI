"""
Models for persistent chat history.

Conversation: a single chat thread owned by a user.
Message: a single turn (user question or assistant response) in a conversation.
"""

import uuid

from django.conf import settings
from django.db import models


class ConversationStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class Conversation(models.Model):
    """A persistent chat conversation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    title = models.CharField(
        max_length=255,
        default="New Conversation",
        help_text="Auto-generated or user-edited title.",
    )
    summary = models.TextField(
        blank=True,
        default="",
        help_text="AI-generated summary of the conversation.",
    )
    status = models.CharField(
        max_length=16,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE,
    )
    pinned = models.BooleanField(default=False)

    # Extracted context metadata (populated as conversation progresses)
    equipment_mentioned = models.JSONField(default=list, blank=True)
    documents_used = models.JSONField(default=list, blank=True)
    knowledge_graph_nodes = models.JSONField(default=list, blank=True)
    drawing_references = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)

    message_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "pinned", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.user.username})"


class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class Message(models.Model):
    """A single message in a conversation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=MessageRole.choices)
    content = models.TextField(help_text="The message text (question or answer).")

    # AI response metadata (populated only for assistant messages)
    confidence = models.FloatField(null=True, blank=True)
    citations = models.JSONField(default=list, blank=True)
    retrieved_chunks = models.JSONField(default=list, blank=True)
    knowledge_graph_refs = models.JSONField(default=list, blank=True)
    drawing_refs = models.JSONField(default=list, blank=True)
    related_equipment = models.JSONField(default=list, blank=True)
    related_documents = models.JSONField(default=list, blank=True)
    suggested_followups = models.JSONField(default=list, blank=True)
    token_usage = models.PositiveIntegerField(default=0)
    response_time_seconds = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
