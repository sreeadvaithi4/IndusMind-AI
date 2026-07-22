"""
Configuration for the RAG Pipeline and Agent Orchestrator.
"""

from dataclasses import dataclass, field

from django.conf import settings


QUERY_INTENTS = [
    "knowledge_search",
    "maintenance",
    "compliance",
    "drawing_lookup",
    "equipment_lookup",
    "document_lookup",
    "incident_lookup",
    "general_question",
]


@dataclass(frozen=True)
class RAGConfig:
    """Configuration for the RAG pipeline."""

    # Retrieval
    top_k: int = 10
    similarity_threshold: float = 0.0
    max_context_tokens: int = 4000
    max_response_tokens: int = 2000

    # LLM
    llm_model: str = "gemini-1.5-flash"
    temperature: float = 0.3
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 3

    # Ranking weights (sum to 1.0)
    weight_semantic: float = 0.4
    weight_graph: float = 0.25
    weight_metadata: float = 0.15
    weight_recency: float = 0.1
    weight_confidence: float = 0.1

    # API key
    api_key: str = ""

    @classmethod
    def from_settings(cls) -> "RAGConfig":
        """Constructs config from Django settings."""
        return cls(
            top_k=getattr(settings, "RAG_TOP_K", 10),
            similarity_threshold=getattr(settings, "RAG_SIMILARITY_THRESHOLD", 0.0),
            max_context_tokens=getattr(settings, "RAG_MAX_CONTEXT_TOKENS", 4000),
            max_response_tokens=getattr(settings, "RAG_MAX_RESPONSE_TOKENS", 2000),
            llm_model=getattr(settings, "RAG_LLM_MODEL", "gemini-1.5-flash"),
            temperature=getattr(settings, "RAG_TEMPERATURE", 0.3),
            llm_timeout_seconds=getattr(settings, "RAG_LLM_TIMEOUT_SECONDS", 30),
            llm_max_retries=getattr(settings, "RAG_LLM_MAX_RETRIES", 3),
            weight_semantic=getattr(settings, "RAG_WEIGHT_SEMANTIC", 0.4),
            weight_graph=getattr(settings, "RAG_WEIGHT_GRAPH", 0.25),
            weight_metadata=getattr(settings, "RAG_WEIGHT_METADATA", 0.15),
            weight_recency=getattr(settings, "RAG_WEIGHT_RECENCY", 0.1),
            weight_confidence=getattr(settings, "RAG_WEIGHT_CONFIDENCE", 0.1),
            api_key=getattr(settings, "GOOGLE_API_KEY", ""),
        )
