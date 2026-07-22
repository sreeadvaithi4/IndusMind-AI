"""
Configuration for the Computer Vision module.
"""

from dataclasses import dataclass, field

from django.conf import settings

from vision.exceptions import DrawingValidationError


# -------------------------------------------------------------------------
# Drawing Types
# -------------------------------------------------------------------------
DRAWING_TYPES = [
    "pid",  # Piping & Instrumentation Diagram
    "mechanical",
    "electrical",
    "instrumentation",
    "general_arrangement",
    "engineering_specification",
    "standard_document",
    "unknown",
]

# -------------------------------------------------------------------------
# Symbol Types (extensible list)
# -------------------------------------------------------------------------
SYMBOL_TYPES = [
    "pump",
    "valve",
    "tank",
    "compressor",
    "heat_exchanger",
    "motor",
    "pipeline",
    "flow_meter",
    "pressure_sensor",
    "temperature_sensor",
    "control_valve",
    "junction",
    "direction_arrow",
    "check_valve",
    "relief_valve",
    "filter",
    "mixer",
    "reactor",
    "column",
    "fan",
]


@dataclass(frozen=True)
class VisionConfig:
    """
    Immutable configuration for the vision module.

    Attributes:
        ocr_confidence_threshold: Minimum OCR confidence (0.0–1.0)
            for extracted text to be included.
        symbol_confidence_threshold: Minimum confidence for detected symbols.
        supported_drawing_types: Drawing classifications to attempt.
        supported_symbol_types: Symbol types the detector looks for.
        max_equipment_per_drawing: Safety limit.
        max_relationships_per_drawing: Safety limit.
    """

    ocr_confidence_threshold: float
    symbol_confidence_threshold: float
    supported_drawing_types: list[str]
    supported_symbol_types: list[str]
    max_equipment_per_drawing: int
    max_relationships_per_drawing: int

    @classmethod
    def from_settings(cls) -> "VisionConfig":
        """Constructs config from Django settings."""
        ocr_threshold = getattr(settings, "VISION_OCR_CONFIDENCE_THRESHOLD", 0.3)
        symbol_threshold = getattr(settings, "VISION_SYMBOL_CONFIDENCE_THRESHOLD", 0.5)
        drawing_types = getattr(settings, "VISION_SUPPORTED_DRAWING_TYPES", DRAWING_TYPES)
        symbol_types = getattr(settings, "VISION_SUPPORTED_SYMBOL_TYPES", SYMBOL_TYPES)
        max_equipment = getattr(settings, "VISION_MAX_EQUIPMENT_PER_DRAWING", 200)
        max_relationships = getattr(settings, "VISION_MAX_RELATIONSHIPS_PER_DRAWING", 500)

        if not (0.0 <= ocr_threshold <= 1.0):
            raise DrawingValidationError(
                f"VISION_OCR_CONFIDENCE_THRESHOLD must be 0.0–1.0, got {ocr_threshold}."
            )

        return cls(
            ocr_confidence_threshold=ocr_threshold,
            symbol_confidence_threshold=symbol_threshold,
            supported_drawing_types=list(drawing_types),
            supported_symbol_types=list(symbol_types),
            max_equipment_per_drawing=max_equipment,
            max_relationships_per_drawing=max_relationships,
        )
