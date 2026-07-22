"""
Exception hierarchy for the Knowledge Graph module.

All exceptions raised by this module inherit from `KnowledgeGraphError`,
so callers (specifically `DocumentProcessingService.update_knowledge_graph`)
can catch a single base class, following the established pattern from
ParserError, ChunkingError, EmbeddingError, and VectorStoreError.
"""


class KnowledgeGraphError(Exception):
    """Base exception for all knowledge graph failures."""


class KnowledgeGraphConfigurationError(KnowledgeGraphError):
    """Raised when the knowledge graph module is misconfigured."""


class EntityExtractionError(KnowledgeGraphError):
    """Raised when entity extraction fails."""


class RelationshipExtractionError(KnowledgeGraphError):
    """Raised when relationship extraction fails."""


class GraphOperationError(KnowledgeGraphError):
    """Raised when a graph create/update/delete operation fails."""


class GraphValidationError(KnowledgeGraphError):
    """Raised when input validation fails."""
