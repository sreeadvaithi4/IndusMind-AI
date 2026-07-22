"""
Configuration for the Knowledge Graph module.

All values are environment-variable-driven via Django settings.
"""

from dataclasses import dataclass, field

from django.conf import settings

from knowledge_graph.exceptions import KnowledgeGraphConfigurationError


# -------------------------------------------------------------------------
# Entity Types — the taxonomy of extractable industrial entities
# -------------------------------------------------------------------------
ENTITY_TYPES = [
    "equipment",
    "pump",
    "valve",
    "compressor",
    "heat_exchanger",
    "tank",
    "motor",
    "pipeline",
    "instrument",
    "sensor",
    "building",
    "department",
    "plant",
    "area",
    "personnel",
    "manufacturer",
    "spare_part",
    "sop",
    "maintenance_activity",
    "inspection_activity",
    "failure_mode",
    "root_cause",
    "corrective_action",
    "preventive_action",
    "regulation",
    "standard",
    "document_reference",
    "tag",
    "date",
    "location",
]

# -------------------------------------------------------------------------
# Relationship Types — the taxonomy of extractable relationships
# -------------------------------------------------------------------------
RELATIONSHIP_TYPES = [
    "has_manual",
    "located_in",
    "connected_to",
    "maintained_by",
    "affects",
    "performed_on",
    "applies_to",
    "governs",
    "resolves",
    "references",
    "mentions",
    "part_of",
    "manufactured_by",
    "requires",
    "caused_by",
    "related_to",
    "inspected_by",
    "replaced_by",
    "installed_in",
    "operated_by",
]


@dataclass(frozen=True)
class KnowledgeGraphConfig:
    """
    Immutable configuration for the Knowledge Graph module.

    Attributes:
        entity_confidence_threshold: Minimum confidence score (0.0–1.0)
            for an extracted entity to be included in the graph.
        relationship_confidence_threshold: Minimum confidence score
            for an extracted relationship.
        supported_entity_types: List of entity type strings to extract.
        supported_relationship_types: List of relationship type strings.
        max_entities_per_document: Safety limit on entity count.
        max_relationships_per_document: Safety limit on relationship count.
        deduplication_enabled: Whether to merge duplicate entities.
    """

    entity_confidence_threshold: float
    relationship_confidence_threshold: float
    supported_entity_types: list[str]
    supported_relationship_types: list[str]
    max_entities_per_document: int
    max_relationships_per_document: int
    deduplication_enabled: bool

    @classmethod
    def from_settings(cls) -> "KnowledgeGraphConfig":
        """Constructs config from Django settings."""
        entity_threshold = getattr(
            settings, "KG_ENTITY_CONFIDENCE_THRESHOLD", 0.3
        )
        relationship_threshold = getattr(
            settings, "KG_RELATIONSHIP_CONFIDENCE_THRESHOLD", 0.3
        )
        entity_types = getattr(
            settings, "KG_SUPPORTED_ENTITY_TYPES", ENTITY_TYPES
        )
        relationship_types = getattr(
            settings, "KG_SUPPORTED_RELATIONSHIP_TYPES", RELATIONSHIP_TYPES
        )
        max_entities = getattr(settings, "KG_MAX_ENTITIES_PER_DOCUMENT", 500)
        max_relationships = getattr(
            settings, "KG_MAX_RELATIONSHIPS_PER_DOCUMENT", 1000
        )
        dedup = getattr(settings, "KG_DEDUPLICATION_ENABLED", True)

        if not (0.0 <= entity_threshold <= 1.0):
            raise KnowledgeGraphConfigurationError(
                f"KG_ENTITY_CONFIDENCE_THRESHOLD must be 0.0–1.0, "
                f"got {entity_threshold}."
            )
        if not (0.0 <= relationship_threshold <= 1.0):
            raise KnowledgeGraphConfigurationError(
                f"KG_RELATIONSHIP_CONFIDENCE_THRESHOLD must be 0.0–1.0, "
                f"got {relationship_threshold}."
            )

        return cls(
            entity_confidence_threshold=entity_threshold,
            relationship_confidence_threshold=relationship_threshold,
            supported_entity_types=list(entity_types),
            supported_relationship_types=list(relationship_types),
            max_entities_per_document=max_entities,
            max_relationships_per_document=max_relationships,
            deduplication_enabled=dedup,
        )
