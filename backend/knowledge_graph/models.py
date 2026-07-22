"""
Data models for Knowledge Graph entities and relationships.

Plain dataclasses — not Django models. The graph itself lives in
NetworkX; these are the structured types that flow between the
extraction layer and the graph service.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Entity:
    """
    A single extracted entity (node in the knowledge graph).

    Attributes:
        entity_id: Unique identifier for this entity.
        entity_type: One of the supported entity types (e.g. 'equipment',
            'pump', 'valve', 'plant').
        name: Canonical name of the entity.
        aliases: Alternative names/references for deduplication.
        source_document_ids: Documents this entity was extracted from.
        confidence: Extraction confidence score (0.0–1.0).
        metadata: Additional structured data (manufacturer, model, etc.).
        created_at: When the entity was first created in the graph.
        updated_at: When the entity was last updated.
    """

    entity_id: str = ""
    entity_type: str = ""
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    source_document_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.entity_id:
            self.entity_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "aliases": self.aliases,
            "source_document_ids": self.source_document_ids,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Relationship:
    """
    A single extracted relationship (edge in the knowledge graph).

    Attributes:
        relationship_id: Unique identifier for this relationship.
        relationship_type: One of the supported relationship types
            (e.g. 'located_in', 'connected_to', 'maintained_by').
        source_entity_id: The entity this relationship originates from.
        target_entity_id: The entity this relationship points to.
        source_document_id: Document this relationship was extracted from.
        confidence: Extraction confidence score (0.0–1.0).
        metadata: Additional structured data (timestamp, context, etc.).
        created_at: When the relationship was first created.
    """

    relationship_id: str = ""
    relationship_type: str = ""
    source_entity_id: str = ""
    target_entity_id: str = ""
    source_document_id: str = ""
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.relationship_id:
            self.relationship_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "relationship_id": self.relationship_id,
            "relationship_type": self.relationship_type,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "source_document_id": self.source_document_id,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class ExtractionResult:
    """
    Complete output of entity/relationship extraction for one document.

    Attributes:
        document_id: The document processed.
        entities: All extracted entities.
        relationships: All extracted relationships.
        entity_count: Number of entities extracted.
        relationship_count: Number of relationships extracted.
        duration_seconds: Time taken for extraction.
        warnings: Any non-fatal issues.
    """

    document_id: str
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    duration_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    @property
    def relationship_count(self) -> int:
        return len(self.relationships)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "entity_count": self.entity_count,
            "relationship_count": self.relationship_count,
            "duration_seconds": self.duration_seconds,
            "entity_types": list(set(e.entity_type for e in self.entities)),
            "relationship_types": list(
                set(r.relationship_type for r in self.relationships)
            ),
            "warnings": self.warnings,
        }
