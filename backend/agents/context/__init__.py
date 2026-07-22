"""
Context Builder for RAG prompts.

Constructs optimized prompts by combining retrieval results into a
coherent context block that respects LLM token limits, includes
citations, and removes duplicate information.
"""

from dataclasses import dataclass, field

from agents.config import RAGConfig
from agents.retrieval import RetrievalHit, RetrievalResult


@dataclass
class Citation:
    """A source citation for a response."""

    document_id: str = ""
    chunk_id: str = ""
    entity_id: str = ""
    source_type: str = ""  # "document", "knowledge_graph", "drawing"
    page_number: int | None = None
    confidence: float = 0.0
    drawing_reference: str = ""

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "entity_id": self.entity_id,
            "source_type": self.source_type,
            "page_number": self.page_number,
            "confidence": self.confidence,
            "drawing_reference": self.drawing_reference,
        }


@dataclass
class BuiltContext:
    """The assembled context ready for LLM consumption."""

    system_prompt: str = ""
    user_prompt: str = ""
    context_text: str = ""
    citations: list[Citation] = field(default_factory=list)
    token_estimate: int = 0
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "context_length": len(self.context_text),
            "citation_count": len(self.citations),
            "token_estimate": self.token_estimate,
            "truncated": self.truncated,
        }


SYSTEM_PROMPT = """You are IndusMind AI, an expert industrial intelligence assistant.
You help engineers, maintenance teams, and operations personnel find information
about equipment, maintenance procedures, safety regulations, engineering drawings,
and industrial processes.

Rules:
- Answer based ONLY on the provided context. If the context doesn't contain enough
  information, say so clearly.
- Always cite your sources using [Source N] notation.
- Be precise and technical when discussing equipment or procedures.
- If asked about specific equipment, include tag numbers and specifications.
- For safety-related questions, always emphasize relevant regulations and standards.
"""


class ContextBuilder:
    """
    Builds optimized prompts from retrieval results.

    Usage:
        context = ContextBuilder.build(query, retrieval_result, config)
    """

    @classmethod
    def build(
        cls,
        query: str,
        retrieval_result: RetrievalResult,
        config: RAGConfig | None = None,
        conversation_history: list[dict] | None = None,
    ) -> BuiltContext:
        """
        Constructs the full prompt context from retrieval results.

        Args:
            query: The user's original question.
            retrieval_result: The hybrid retrieval output.
            config: Optional config override.
            conversation_history: Optional prior conversation turns.

        Returns:
            BuiltContext with system prompt, user prompt, and citations.
        """
        if config is None:
            config = RAGConfig.from_settings()

        # Build context sections
        context_parts: list[str] = []
        citations: list[Citation] = []
        source_idx = 0

        for hit in retrieval_result.hits:
            if not hit.content:
                continue

            source_idx += 1
            source_label = f"[Source {source_idx}]"

            # Add to context
            source_info = cls._format_source_info(hit)
            context_parts.append(f"{source_label} {source_info}\n{hit.content}")

            # Build citation
            citations.append(Citation(
                document_id=hit.document_id,
                chunk_id=hit.chunk_id,
                entity_id=hit.entity_id,
                source_type=hit.source,
                page_number=hit.metadata.get("page_number"),
                confidence=hit.score,
                drawing_reference=hit.metadata.get("drawing_number", ""),
            ))

        # Join context and check token limits
        context_text = "\n\n".join(context_parts)
        truncated = False

        # Rough token estimation: 4 chars per token
        max_context_chars = config.max_context_tokens * 4
        if len(context_text) > max_context_chars:
            context_text = context_text[:max_context_chars]
            truncated = True

        # Build conversation history section
        history_text = ""
        if conversation_history:
            history_parts = []
            for turn in conversation_history[-5:]:  # Last 5 turns
                role = turn.get("role", "user")
                content = turn.get("content", "")[:500]
                history_parts.append(f"{role}: {content}")
            history_text = "\n".join(history_parts)

        # Assemble user prompt
        user_prompt_parts = []
        if history_text:
            user_prompt_parts.append(f"Previous conversation:\n{history_text}\n")
        if context_text:
            user_prompt_parts.append(f"Context:\n{context_text}\n")
        user_prompt_parts.append(f"Question: {query}")

        user_prompt = "\n".join(user_prompt_parts)
        full_prompt = SYSTEM_PROMPT + "\n" + user_prompt
        token_estimate = len(full_prompt) // 4

        return BuiltContext(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            context_text=context_text,
            citations=citations,
            token_estimate=token_estimate,
            truncated=truncated,
        )

    @staticmethod
    def _format_source_info(hit: RetrievalHit) -> str:
        """Formats source metadata for display in context."""
        parts = []
        if hit.source == "chromadb":
            filename = hit.metadata.get("source_filename", "")
            if filename:
                parts.append(f"(Document: {filename})")
        elif hit.source == "knowledge_graph":
            entity_type = hit.metadata.get("entity_type", "")
            if entity_type:
                parts.append(f"(Knowledge Graph: {entity_type})")
        return " ".join(parts)
