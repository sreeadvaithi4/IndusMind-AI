"""
Enterprise Knowledge Graph Service.

Entry point for the Knowledge Graph module. Orchestrates entity
extraction from parsed document text and populates the NetworkX graph.

This service has no dependency on `apps.documents` — it operates purely
on `ParsedDocument` text and returns structured results. The
orchestration (status transitions, model persistence) belongs in
`apps.documents.services.DocumentProcessingService.update_knowledge_graph`.
"""

import logging
import time

from knowledge_graph.config import KnowledgeGraphConfig
from knowledge_graph.exceptions import (
    EntityExtractionError,
    KnowledgeGraphError,
)
from knowledge_graph.extractor import EntityExtractor
from knowledge_graph.graph import GraphService
from knowledge_graph.models import ExtractionResult

logger = logging.getLogger("knowledge_graph")


class KnowledgeGraphService:
    """
    Entry point for the Knowledge Graph module.

    Usage:
        result = KnowledgeGraphService.process_document(text, document_id)
    """

    @classmethod
    def process_document(
        cls,
        text: str,
        document_id: str,
        config: KnowledgeGraphConfig | None = None,
    ) -> ExtractionResult:
        """
        Extracts entities and relationships from document text, then
        populates the knowledge graph.

        Args:
            text: Full document text (from ParsedDocument.text).
            document_id: The document UUID string.
            config: Optional config override (useful for testing).

        Returns:
            ExtractionResult with entities, relationships, and timing.

        Raises:
            KnowledgeGraphError: on unrecoverable failures.
        """
        if config is None:
            config = KnowledgeGraphConfig.from_settings()

        if not text or not text.strip():
            logger.warning(
                "Empty text for document %s — skipping knowledge graph update.",
                document_id,
            )
            return ExtractionResult(
                document_id=document_id,
                warnings=["Empty text — no entities extracted."],
            )

        if not document_id:
            raise KnowledgeGraphError(
                "document_id is required for knowledge graph processing."
            )

        logger.info(
            "Starting knowledge graph processing for document %s.",
            document_id,
        )

        # Step 1: Extract entities and relationships
        extraction_result = EntityExtractor.extract(
            text=text,
            document_id=document_id,
            config=config,
        )

        # Step 2: Populate the graph
        if extraction_result.entities or extraction_result.relationships:
            graph_summary = GraphService.populate_from_extraction(extraction_result)
            logger.info(
                "Knowledge graph updated for document %s: %d entities, "
                "%d relationships (graph now has %d nodes, %d edges).",
                document_id,
                graph_summary["entities_added"],
                graph_summary["relationships_added"],
                graph_summary["total_nodes"],
                graph_summary["total_edges"],
            )
        else:
            logger.info(
                "No entities or relationships extracted for document %s.",
                document_id,
            )

        return extraction_result

    @classmethod
    def delete_document(cls, document_id: str) -> int:
        """
        Removes all entities exclusively sourced from a document.

        Returns the number of nodes removed.
        """
        return GraphService.delete_document_entities(document_id)

    @classmethod
    def search_entities(
        cls, query: str, entity_type: str | None = None
    ) -> list[dict]:
        """Searches entities by name."""
        return GraphService.search_entities(query, entity_type)

    @classmethod
    def get_entity(cls, entity_id: str) -> dict | None:
        """Gets a single entity by ID."""
        return GraphService.get_entity(entity_id)

    @classmethod
    def get_related_entities(cls, entity_id: str) -> list[dict]:
        """Gets all entities related to the given entity."""
        return GraphService.get_related_entities(entity_id)

    @classmethod
    def get_relationships(cls, entity_id: str) -> list[dict]:
        """Gets all relationships involving the given entity."""
        return GraphService.get_relationships(entity_id)

    @classmethod
    def get_document_entities(cls, document_id: str) -> list[dict]:
        """Gets all entities sourced from a document."""
        return GraphService.get_document_entities(document_id)

    @classmethod
    def get_statistics(cls) -> dict:
        """Gets graph statistics."""
        return GraphService.get_statistics()
