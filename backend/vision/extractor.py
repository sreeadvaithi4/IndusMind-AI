"""
Equipment and Relationship Extractor for Engineering Drawings.

Converts detected symbols and OCR extractions into structured equipment
items and relationships suitable for the Knowledge Graph.
"""

import re

from vision.models import (
    DetectedSymbol,
    DrawingRelationship,
    ExtractedEquipment,
    OCRExtraction,
)


# Maps symbol types to equipment types for the knowledge graph
SYMBOL_TO_EQUIPMENT_TYPE: dict[str, str] = {
    "pump": "pump",
    "valve": "valve",
    "tank": "tank",
    "compressor": "compressor",
    "heat_exchanger": "heat_exchanger",
    "motor": "motor",
    "pipeline": "pipeline",
    "flow_meter": "instrument",
    "pressure_sensor": "instrument",
    "temperature_sensor": "instrument",
    "control_valve": "valve",
    "junction": "pipeline",
    "direction_arrow": "pipeline",
}

# Relationship inference patterns — when two equipment items appear
# near each other in text, infer a relationship.
ADJACENCY_RELATIONSHIP_RULES: list[dict] = [
    {
        "source_types": {"pump"},
        "target_types": {"valve", "pipeline"},
        "relationship_type": "connected_to",
    },
    {
        "source_types": {"valve"},
        "target_types": {"pipeline", "tank", "pump"},
        "relationship_type": "connected_to",
    },
    {
        "source_types": {"pipeline"},
        "target_types": {"tank", "heat_exchanger", "valve"},
        "relationship_type": "feeds",
    },
    {
        "source_types": {"flow_meter", "pressure_sensor", "temperature_sensor"},
        "target_types": {"pump", "valve", "pipeline", "tank", "compressor", "heat_exchanger"},
        "relationship_type": "monitors",
    },
    {
        "source_types": {"motor"},
        "target_types": {"pump", "compressor"},
        "relationship_type": "drives",
    },
    {
        "source_types": {"control_valve"},
        "target_types": {"pipeline", "pump"},
        "relationship_type": "controls",
    },
]


def extract_equipment(
    symbols: list[DetectedSymbol],
    ocr_extractions: list[OCRExtraction],
    document_id: str,
    drawing_number: str = "",
) -> list[ExtractedEquipment]:
    """
    Converts detected symbols and OCR equipment tags into structured
    ExtractedEquipment objects.
    """
    equipment: list[ExtractedEquipment] = []
    seen_tags: set[str] = set()

    # From detected symbols
    for symbol in symbols:
        tag = symbol.label
        if tag.lower() in seen_tags:
            continue
        seen_tags.add(tag.lower())

        equipment.append(ExtractedEquipment(
            name=tag,
            tag=tag,
            equipment_type=SYMBOL_TO_EQUIPMENT_TYPE.get(symbol.symbol_type, symbol.symbol_type),
            drawing_reference=drawing_number,
            confidence=symbol.confidence,
            coordinates=symbol.coordinates,
            metadata={
                "source": "symbol_detection",
                "symbol_type": symbol.symbol_type,
                "document_id": document_id,
            },
        ))

    # From OCR equipment tags not already captured
    for extraction in ocr_extractions:
        if extraction.extraction_type == "equipment_tag":
            tag = extraction.text
            if tag.lower() in seen_tags:
                continue
            seen_tags.add(tag.lower())

            equipment.append(ExtractedEquipment(
                name=tag,
                tag=tag,
                equipment_type=_infer_equipment_type(tag),
                drawing_reference=drawing_number,
                confidence=extraction.confidence,
                metadata={
                    "source": "ocr_extraction",
                    "document_id": document_id,
                },
            ))

    return equipment


def extract_relationships(
    equipment: list[ExtractedEquipment],
    symbols: list[DetectedSymbol],
    text: str,
    document_id: str,
) -> list[DrawingRelationship]:
    """
    Infers relationships between equipment items based on:
    1. Adjacency rules (equipment types that typically connect)
    2. Text co-occurrence (equipment mentioned in same sentence/line)
    """
    relationships: list[DrawingRelationship] = []
    seen_pairs: set[str] = set()

    # Build equipment lookup
    equip_by_type: dict[str, list[ExtractedEquipment]] = {}
    for eq in equipment:
        equip_by_type.setdefault(eq.equipment_type, []).append(eq)

    # Apply adjacency rules
    for rule in ADJACENCY_RELATIONSHIP_RULES:
        for source_type in rule["source_types"]:
            for target_type in rule["target_types"]:
                sources = equip_by_type.get(source_type, [])
                targets = equip_by_type.get(target_type, [])

                for source in sources:
                    for target in targets:
                        if source.tag == target.tag:
                            continue

                        pair_key = f"{source.tag}:{target.tag}:{rule['relationship_type']}"
                        if pair_key in seen_pairs:
                            continue

                        # Check text co-occurrence (within 200 chars)
                        if _check_co_occurrence(text, source.tag, target.tag, window=200):
                            seen_pairs.add(pair_key)
                            relationships.append(DrawingRelationship(
                                relationship_type=rule["relationship_type"],
                                source_equipment=source.tag,
                                target_equipment=target.tag,
                                confidence=0.6,
                                metadata={
                                    "source": "adjacency_rule",
                                    "document_id": document_id,
                                },
                            ))

    return relationships


def _infer_equipment_type(tag: str) -> str:
    """Infers equipment type from a tag prefix."""
    prefix_map = {
        "P": "pump",
        "V": "valve",
        "C": "compressor",
        "E": "heat_exchanger",
        "T": "tank",
        "TK": "tank",
        "M": "motor",
        "HX": "heat_exchanger",
        "FV": "valve",
        "PV": "valve",
        "TV": "valve",
        "LV": "valve",
        "XV": "valve",
        "PT": "instrument",
        "TT": "instrument",
        "FT": "instrument",
        "LT": "instrument",
        "PI": "instrument",
        "TI": "instrument",
        "FI": "instrument",
    }

    # Try 2-char prefix first, then 1-char
    if len(tag) >= 2:
        prefix2 = tag[:2].upper()
        if prefix2 in prefix_map:
            return prefix_map[prefix2]

    if tag:
        prefix1 = tag[0].upper()
        if prefix1 in prefix_map:
            return prefix_map[prefix1]

    return "equipment"


def _check_co_occurrence(text: str, tag1: str, tag2: str, window: int = 200) -> bool:
    """
    Checks if two tags appear within `window` characters of each other
    in the text. This heuristic suggests they're related in the drawing.
    """
    pattern1 = re.escape(tag1)
    for match in re.finditer(pattern1, text, re.IGNORECASE):
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        surrounding = text[start:end]
        if re.search(re.escape(tag2), surrounding, re.IGNORECASE):
            return True
    return False
