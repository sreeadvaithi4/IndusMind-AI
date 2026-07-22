"""
Entity and Relationship Extraction Service.

Uses pattern-based extraction (regex + heuristics) to identify
industrial entities and their relationships from parsed document text.
This is a rule-based, deterministic extractor — no LLM calls — designed
to be fast, predictable, and easily extensible with new patterns.

The extraction is modular: each entity type has its own pattern set,
and new types can be added by appending to the ENTITY_PATTERNS dict.
"""

import logging
import re
import time
from datetime import datetime, timezone

from knowledge_graph.config import KnowledgeGraphConfig
from knowledge_graph.exceptions import EntityExtractionError
from knowledge_graph.models import Entity, ExtractionResult, Relationship

logger = logging.getLogger("knowledge_graph")


# -------------------------------------------------------------------------
# Pattern definitions for entity extraction
# -------------------------------------------------------------------------
# Each key maps to a list of compiled regex patterns. Matches are
# case-insensitive. Group 1 (if present) is the entity name; otherwise
# the full match is used.

ENTITY_PATTERNS: dict[str, list[re.Pattern]] = {
    "pump": [
        re.compile(r"\b([\w\-]+\s*pump(?:\s*\w+)?)\b", re.IGNORECASE),
        re.compile(r"\b(P-\d{3,}[A-Z]?)\b"),
    ],
    "valve": [
        re.compile(r"\b([\w\-]+\s*valve(?:\s*\w+)?)\b", re.IGNORECASE),
        re.compile(r"\b(V-\d{3,}[A-Z]?)\b"),
    ],
    "compressor": [
        re.compile(r"\b([\w\-]+\s*compressor(?:\s*\w+)?)\b", re.IGNORECASE),
        re.compile(r"\b(C-\d{3,}[A-Z]?)\b"),
    ],
    "heat_exchanger": [
        re.compile(r"\b([\w\-]+\s*heat\s*exchanger(?:\s*\w+)?)\b", re.IGNORECASE),
        re.compile(r"\b(E-\d{3,}[A-Z]?)\b"),
        re.compile(r"\b(HX-\d{3,}[A-Z]?)\b"),
    ],
    "tank": [
        re.compile(r"\b([\w\-]+\s*tank(?:\s*\w+)?)\b", re.IGNORECASE),
        re.compile(r"\b(T-\d{3,}[A-Z]?)\b"),
        re.compile(r"\b(TK-\d{3,}[A-Z]?)\b"),
    ],
    "motor": [
        re.compile(r"\b([\w\-]+\s*motor(?:\s*\w+)?)\b", re.IGNORECASE),
        re.compile(r"\b(M-\d{3,}[A-Z]?)\b"),
    ],
    "pipeline": [
        re.compile(r"\b([\w\-]+\s*pipeline(?:\s*\w+)?)\b", re.IGNORECASE),
        re.compile(r"\b(\d+[\"\']?\s*(?:inch|in)\s*(?:line|pipe))\b", re.IGNORECASE),
    ],
    "instrument": [
        re.compile(r"\b([\w\-]+\s*(?:transmitter|gauge|indicator|controller))\b", re.IGNORECASE),
    ],
    "sensor": [
        re.compile(r"\b([\w\-]+\s*sensor(?:\s*\w+)?)\b", re.IGNORECASE),
    ],
    "plant": [
        re.compile(r"\b([\w\s]+\s*(?:plant|facility|refinery|terminal))\b", re.IGNORECASE),
    ],
    "area": [
        re.compile(r"\b((?:area|zone|unit|section)\s*[\w\-]+)\b", re.IGNORECASE),
    ],
    "department": [
        re.compile(r"\b((?:maintenance|operations|engineering|safety|quality)\s*(?:department|dept|team|group))\b", re.IGNORECASE),
    ],
    "manufacturer": [
        re.compile(r"\b(?:manufactured|made|supplied)\s+by\s+([\w\s&]+?)(?:\.|,|\s{2}|\n)", re.IGNORECASE),
    ],
    "sop": [
        re.compile(r"\b(SOP[-\s]?[\w\-]+)\b", re.IGNORECASE),
        re.compile(r"\b((?:standard\s+operating\s+procedure)\s*[\w\-]*)\b", re.IGNORECASE),
    ],
    "regulation": [
        re.compile(r"\b((?:ISO|ASME|API|OSHA|EPA|NFPA|IEC)\s*\d+[\w\-\.]*)\b"),
    ],
    "standard": [
        re.compile(r"\b((?:ASTM|ANSI|BS|EN|DIN)\s*[\w\-\.]+)\b"),
    ],
    "failure_mode": [
        re.compile(r"\b((?:corrosion|erosion|fatigue|leakage|vibration|overheating|cavitation|fouling|blockage|seizure))\b", re.IGNORECASE),
    ],
    "maintenance_activity": [
        re.compile(r"\b((?:preventive|corrective|predictive|condition-based)\s*maintenance)\b", re.IGNORECASE),
        re.compile(r"\b((?:overhaul|repair|replacement|calibration|lubrication|alignment|inspection))\b", re.IGNORECASE),
    ],
    "inspection_activity": [
        re.compile(r"\b((?:visual|ultrasonic|radiographic|magnetic|dye\s*penetrant|thickness)\s*(?:inspection|testing|examination))\b", re.IGNORECASE),
    ],
    "spare_part": [
        re.compile(r"\b((?:bearing|seal|gasket|impeller|shaft|coupling|filter|o-ring|diaphragm)(?:\s*\w+)?)\b", re.IGNORECASE),
    ],
    "equipment": [
        re.compile(r"\b([\w\-]+[-]\d{3,}[A-Z]?(?:/[A-Z])?)\b"),
    ],
    "tag": [
        re.compile(r"\b([A-Z]{2,4}[-_]\d{3,}[-_]?\w*)\b"),
    ],
    "location": [
        re.compile(r"\b((?:building|floor|room|bay|rack)\s*[\w\-]+)\b", re.IGNORECASE),
    ],
}

# -------------------------------------------------------------------------
# Pattern definitions for relationship extraction
# -------------------------------------------------------------------------
RELATIONSHIP_PATTERNS: list[dict] = [
    {
        "type": "located_in",
        "pattern": re.compile(
            r"([\w\-]+)\s+(?:is\s+)?(?:located|installed|positioned)\s+(?:in|at)\s+([\w\s]+?)(?:\.|,|\n)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "connected_to",
        "pattern": re.compile(
            r"([\w\-]+)\s+(?:is\s+)?(?:connected|linked|attached|coupled)\s+to\s+([\w\-]+)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "maintained_by",
        "pattern": re.compile(
            r"([\w\-]+)\s+(?:is\s+)?(?:maintained|serviced)\s+by\s+([\w\s]+?)(?:\.|,|\n)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "affects",
        "pattern": re.compile(
            r"([\w\s]+?)\s+(?:affects|impacts|damages)\s+([\w\-]+)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "performed_on",
        "pattern": re.compile(
            r"([\w\s]+?)\s+(?:performed|conducted|carried\s+out)\s+on\s+([\w\-]+)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "applies_to",
        "pattern": re.compile(
            r"([\w\-]+)\s+(?:applies|applicable)\s+to\s+([\w\-]+)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "governs",
        "pattern": re.compile(
            r"([\w\s\-\.]+?)\s+(?:governs|regulates|requires)\s+([\w\-]+)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "part_of",
        "pattern": re.compile(
            r"([\w\-]+)\s+(?:is\s+)?(?:part\s+of|belongs\s+to|within)\s+([\w\s]+?)(?:\.|,|\n)",
            re.IGNORECASE,
        ),
    },
    {
        "type": "requires",
        "pattern": re.compile(
            r"([\w\-]+)\s+(?:requires|needs)\s+([\w\s]+?)(?:\.|,|\n)",
            re.IGNORECASE,
        ),
    },
]


class EntityExtractor:
    """
    Extracts entities and relationships from document text using
    pattern-based rules.

    Usage:
        result = EntityExtractor.extract(text, document_id, config)
    """

    @classmethod
    def extract(
        cls,
        text: str,
        document_id: str,
        config: KnowledgeGraphConfig,
    ) -> ExtractionResult:
        """
        Extracts entities and relationships from text.

        Args:
            text: The full document text (from ParsedDocument).
            document_id: The document UUID string.
            config: Knowledge graph configuration.

        Returns:
            ExtractionResult with all extracted entities and relationships.

        Raises:
            EntityExtractionError: on unrecoverable extraction failures.
        """
        start_time = time.time()
        warnings: list[str] = []

        if not text or not text.strip():
            return ExtractionResult(
                document_id=document_id,
                duration_seconds=0.0,
                warnings=["Empty text — no entities extracted."],
            )

        try:
            # Extract entities
            entities = cls._extract_entities(text, document_id, config)

            # Enforce max limit
            if len(entities) > config.max_entities_per_document:
                warnings.append(
                    f"Entity count ({len(entities)}) exceeds maximum "
                    f"({config.max_entities_per_document}); truncated."
                )
                entities = entities[: config.max_entities_per_document]

            # Extract relationships
            relationships = cls._extract_relationships(
                text, document_id, entities, config
            )

            if len(relationships) > config.max_relationships_per_document:
                warnings.append(
                    f"Relationship count ({len(relationships)}) exceeds maximum "
                    f"({config.max_relationships_per_document}); truncated."
                )
                relationships = relationships[: config.max_relationships_per_document]

            # Add document -> mentions -> entity relationships
            for entity in entities:
                relationships.append(
                    Relationship(
                        relationship_type="mentions",
                        source_entity_id=document_id,
                        target_entity_id=entity.entity_id,
                        source_document_id=document_id,
                        confidence=entity.confidence,
                    )
                )

        except Exception as exc:
            raise EntityExtractionError(
                f"Entity extraction failed for document {document_id}: {exc}"
            ) from exc

        duration = round(time.time() - start_time, 3)

        logger.info(
            "Entity extraction complete for document %s: %d entities, "
            "%d relationships (%.2fs).",
            document_id,
            len(entities),
            len(relationships),
            duration,
        )

        return ExtractionResult(
            document_id=document_id,
            entities=entities,
            relationships=relationships,
            duration_seconds=duration,
            warnings=warnings,
        )

    @classmethod
    def _extract_entities(
        cls,
        text: str,
        document_id: str,
        config: KnowledgeGraphConfig,
    ) -> list[Entity]:
        """Applies entity patterns to text and deduplicates results."""
        seen_names: dict[str, Entity] = {}
        entities: list[Entity] = []

        for entity_type, patterns in ENTITY_PATTERNS.items():
            if entity_type not in config.supported_entity_types:
                continue

            for pattern in patterns:
                for match in pattern.finditer(text):
                    name = match.group(1) if match.lastindex else match.group(0)
                    name = name.strip()

                    if not name or len(name) < 2 or len(name) > 100:
                        continue

                    # Normalize for dedup
                    normalized = name.lower().strip()

                    if normalized in seen_names:
                        # Update existing entity with additional source
                        existing = seen_names[normalized]
                        if document_id not in existing.source_document_ids:
                            existing.source_document_ids.append(document_id)
                        continue

                    entity = Entity(
                        entity_type=entity_type,
                        name=name,
                        source_document_ids=[document_id],
                        confidence=0.7,  # Pattern-based extraction base confidence
                        metadata={"extraction_method": "pattern"},
                    )
                    seen_names[normalized] = entity
                    entities.append(entity)

        # Filter by confidence threshold
        return [
            e
            for e in entities
            if e.confidence >= config.entity_confidence_threshold
        ]

    @classmethod
    def _extract_relationships(
        cls,
        text: str,
        document_id: str,
        entities: list[Entity],
        config: KnowledgeGraphConfig,
    ) -> list[Relationship]:
        """Extracts relationships from text using pattern matching."""
        relationships: list[Relationship] = []
        entity_name_map = {e.name.lower(): e for e in entities}

        for rel_def in RELATIONSHIP_PATTERNS:
            rel_type = rel_def["type"]
            if rel_type not in config.supported_relationship_types:
                continue

            pattern = rel_def["pattern"]
            for match in pattern.finditer(text):
                source_text = match.group(1).strip().lower()
                target_text = match.group(2).strip().lower()

                # Try to match to known entities
                source_entity = cls._find_entity(source_text, entity_name_map)
                target_entity = cls._find_entity(target_text, entity_name_map)

                if source_entity and target_entity:
                    relationships.append(
                        Relationship(
                            relationship_type=rel_type,
                            source_entity_id=source_entity.entity_id,
                            target_entity_id=target_entity.entity_id,
                            source_document_id=document_id,
                            confidence=0.6,
                            metadata={"extraction_method": "pattern"},
                        )
                    )

        # Filter by confidence threshold
        return [
            r
            for r in relationships
            if r.confidence >= config.relationship_confidence_threshold
        ]

    @staticmethod
    def _find_entity(
        text: str, entity_map: dict[str, Entity]
    ) -> Entity | None:
        """Finds an entity by exact or substring match in the entity map."""
        if text in entity_map:
            return entity_map[text]

        # Partial match — check if any entity name is contained in text
        for name, entity in entity_map.items():
            if name in text or text in name:
                return entity

        return None
