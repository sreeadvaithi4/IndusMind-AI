"""
NetworkX-based Knowledge Graph Service.

Manages the in-memory graph (persisted via pickle), providing CRUD
operations for nodes and edges, traversal, search, and statistics.

The graph is a module-level singleton — one graph for the entire
application. Future sprints can swap NetworkX for a dedicated graph
database (Neo4j, etc.) by reimplementing this module's interface.
"""

import logging
import os
import pickle
import threading
from datetime import datetime, timezone

import networkx as nx

from knowledge_graph.exceptions import GraphOperationError, GraphValidationError
from knowledge_graph.models import Entity, ExtractionResult, Relationship

logger = logging.getLogger("knowledge_graph")

# Thread-safe singleton graph + lock
_graph: nx.DiGraph | None = None
_graph_lock = threading.Lock()
_persist_path: str = ""


class GraphService:
    """
    CRUD and query operations on the Knowledge Graph.

    The graph is a directed graph (DiGraph) where:
        - Nodes represent entities (keyed by entity_id)
        - Edges represent relationships (keyed by source→target)
        - Node attributes store Entity metadata
        - Edge attributes store Relationship metadata
    """

    @classmethod
    def initialize(cls, persist_path: str = "") -> None:
        """
        Initializes the graph, loading from disk if a persisted
        version exists.
        """
        global _graph, _persist_path
        with _graph_lock:
            _persist_path = persist_path
            if persist_path and os.path.exists(persist_path):
                try:
                    with open(persist_path, "rb") as f:
                        _graph = pickle.load(f)
                    logger.info(
                        "Loaded knowledge graph from %s (%d nodes, %d edges).",
                        persist_path,
                        _graph.number_of_nodes(),
                        _graph.number_of_edges(),
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to load graph from %s: %s. Starting fresh.",
                        persist_path,
                        exc,
                    )
                    _graph = nx.DiGraph()
            else:
                _graph = nx.DiGraph()

    @classmethod
    def _get_graph(cls) -> nx.DiGraph:
        """Returns the graph instance, initializing if needed."""
        global _graph
        if _graph is None:
            from django.conf import settings
            persist = getattr(settings, "KG_PERSIST_PATH", "")
            cls.initialize(persist)
        return _graph

    @classmethod
    def _persist(cls) -> None:
        """Saves graph to disk if persist path is configured."""
        global _graph, _persist_path
        if _persist_path and _graph is not None:
            try:
                os.makedirs(os.path.dirname(_persist_path) or ".", exist_ok=True)
                with open(_persist_path, "wb") as f:
                    pickle.dump(_graph, f)
            except Exception as exc:
                logger.warning("Failed to persist graph to %s: %s", _persist_path, exc)

    # ------------------------------------------------------------------
    # Node (Entity) Operations
    # ------------------------------------------------------------------

    @classmethod
    def add_entity(cls, entity: Entity) -> str:
        """
        Adds an entity as a node in the graph. If an entity with the
        same ID exists, merges (updates attributes).

        Returns the entity_id.
        """
        graph = cls._get_graph()
        with _graph_lock:
            if graph.has_node(entity.entity_id):
                # Merge: update attributes
                existing = graph.nodes[entity.entity_id]
                existing_docs = existing.get("source_document_ids", [])
                for doc_id in entity.source_document_ids:
                    if doc_id not in existing_docs:
                        existing_docs.append(doc_id)
                existing["source_document_ids"] = existing_docs
                existing["updated_at"] = datetime.now(timezone.utc).isoformat()
                # Merge aliases
                existing_aliases = set(existing.get("aliases", []))
                existing_aliases.update(entity.aliases)
                existing["aliases"] = list(existing_aliases)
            else:
                graph.add_node(
                    entity.entity_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    aliases=entity.aliases,
                    source_document_ids=entity.source_document_ids,
                    confidence=entity.confidence,
                    metadata=entity.metadata,
                    created_at=entity.created_at,
                    updated_at=entity.updated_at,
                )
        return entity.entity_id

    @classmethod
    def add_relationship(cls, relationship: Relationship) -> str:
        """
        Adds a relationship as an edge in the graph.

        Creates source/target nodes as stubs if they don't exist.
        Returns the relationship_id.
        """
        graph = cls._get_graph()
        with _graph_lock:
            # Ensure both nodes exist
            if not graph.has_node(relationship.source_entity_id):
                graph.add_node(
                    relationship.source_entity_id,
                    entity_type="unknown",
                    name=relationship.source_entity_id,
                    stub=True,
                )
            if not graph.has_node(relationship.target_entity_id):
                graph.add_node(
                    relationship.target_entity_id,
                    entity_type="unknown",
                    name=relationship.target_entity_id,
                    stub=True,
                )

            graph.add_edge(
                relationship.source_entity_id,
                relationship.target_entity_id,
                relationship_id=relationship.relationship_id,
                relationship_type=relationship.relationship_type,
                source_document_id=relationship.source_document_id,
                confidence=relationship.confidence,
                metadata=relationship.metadata,
                created_at=relationship.created_at,
            )
        return relationship.relationship_id

    @classmethod
    def get_entity(cls, entity_id: str) -> dict | None:
        """Returns entity node data, or None if not found."""
        graph = cls._get_graph()
        if graph.has_node(entity_id):
            data = dict(graph.nodes[entity_id])
            data["entity_id"] = entity_id
            return data
        return None

    @classmethod
    def get_related_entities(cls, entity_id: str) -> list[dict]:
        """Returns all entities connected to the given entity."""
        graph = cls._get_graph()
        if not graph.has_node(entity_id):
            return []

        related = []
        # Successors (outgoing edges)
        for neighbor in graph.successors(entity_id):
            data = dict(graph.nodes[neighbor])
            data["entity_id"] = neighbor
            edge_data = graph.edges[entity_id, neighbor]
            data["relationship_type"] = edge_data.get("relationship_type", "")
            data["direction"] = "outgoing"
            related.append(data)

        # Predecessors (incoming edges)
        for neighbor in graph.predecessors(entity_id):
            data = dict(graph.nodes[neighbor])
            data["entity_id"] = neighbor
            edge_data = graph.edges[neighbor, entity_id]
            data["relationship_type"] = edge_data.get("relationship_type", "")
            data["direction"] = "incoming"
            related.append(data)

        return related

    @classmethod
    def get_relationships(cls, entity_id: str) -> list[dict]:
        """Returns all relationships (edges) involving the given entity."""
        graph = cls._get_graph()
        if not graph.has_node(entity_id):
            return []

        relationships = []
        # Outgoing
        for _, target, data in graph.out_edges(entity_id, data=True):
            rel = dict(data)
            rel["source_entity_id"] = entity_id
            rel["target_entity_id"] = target
            relationships.append(rel)
        # Incoming
        for source, _, data in graph.in_edges(entity_id, data=True):
            rel = dict(data)
            rel["source_entity_id"] = source
            rel["target_entity_id"] = entity_id
            relationships.append(rel)

        return relationships

    @classmethod
    def search_entities(cls, query: str, entity_type: str | None = None) -> list[dict]:
        """
        Searches for entities by name (case-insensitive substring match).
        Optionally filters by entity_type.
        """
        graph = cls._get_graph()
        results = []
        query_lower = query.lower()

        for node_id, data in graph.nodes(data=True):
            name = data.get("name", "")
            aliases = data.get("aliases", [])
            node_type = data.get("entity_type", "")

            if entity_type and node_type != entity_type:
                continue

            # Match against name or aliases
            match = query_lower in name.lower()
            if not match:
                match = any(query_lower in alias.lower() for alias in aliases)

            if match:
                result = dict(data)
                result["entity_id"] = node_id
                results.append(result)

        return results

    @classmethod
    def delete_entity(cls, entity_id: str) -> bool:
        """Deletes an entity and all its relationships. Returns True if found."""
        graph = cls._get_graph()
        with _graph_lock:
            if graph.has_node(entity_id):
                graph.remove_node(entity_id)
                return True
        return False

    @classmethod
    def delete_document_entities(cls, document_id: str) -> int:
        """
        Removes all entities (and their relationships) that were
        sourced exclusively from the given document. Entities that
        appear in multiple documents have this document removed from
        their source list but are not deleted.

        Returns the count of nodes removed.
        """
        graph = cls._get_graph()
        nodes_to_remove = []

        with _graph_lock:
            for node_id, data in list(graph.nodes(data=True)):
                source_docs = data.get("source_document_ids", [])
                if document_id in source_docs:
                    source_docs.remove(document_id)
                    if not source_docs:
                        nodes_to_remove.append(node_id)
                    else:
                        data["source_document_ids"] = source_docs

            for node_id in nodes_to_remove:
                graph.remove_node(node_id)

        if nodes_to_remove:
            logger.info(
                "Removed %d nodes for document %s from knowledge graph.",
                len(nodes_to_remove),
                document_id,
            )

        return len(nodes_to_remove)

    @classmethod
    def get_statistics(cls) -> dict:
        """Returns graph statistics."""
        graph = cls._get_graph()
        entity_types: dict[str, int] = {}
        for _, data in graph.nodes(data=True):
            etype = data.get("entity_type", "unknown")
            entity_types[etype] = entity_types.get(etype, 0) + 1

        relationship_types: dict[str, int] = {}
        for _, _, data in graph.edges(data=True):
            rtype = data.get("relationship_type", "unknown")
            relationship_types[rtype] = relationship_types.get(rtype, 0) + 1

        return {
            "total_nodes": graph.number_of_nodes(),
            "total_edges": graph.number_of_edges(),
            "entity_types": entity_types,
            "relationship_types": relationship_types,
        }

    @classmethod
    def get_document_entities(cls, document_id: str) -> list[dict]:
        """Returns all entities sourced from a specific document."""
        graph = cls._get_graph()
        results = []
        for node_id, data in graph.nodes(data=True):
            if document_id in data.get("source_document_ids", []):
                result = dict(data)
                result["entity_id"] = node_id
                results.append(result)
        return results

    @classmethod
    def populate_from_extraction(
        cls, extraction_result: ExtractionResult
    ) -> dict:
        """
        Adds all entities and relationships from an ExtractionResult
        to the graph. Returns a summary dict.
        """
        entities_added = 0
        relationships_added = 0

        for entity in extraction_result.entities:
            cls.add_entity(entity)
            entities_added += 1

        for relationship in extraction_result.relationships:
            cls.add_relationship(relationship)
            relationships_added += 1

        cls._persist()

        return {
            "entities_added": entities_added,
            "relationships_added": relationships_added,
            "total_nodes": cls._get_graph().number_of_nodes(),
            "total_edges": cls._get_graph().number_of_edges(),
        }

    @classmethod
    def reset(cls) -> None:
        """Resets the graph to empty (for testing)."""
        global _graph
        with _graph_lock:
            _graph = nx.DiGraph()
