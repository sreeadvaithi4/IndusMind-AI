"""
Exception hierarchy for the Computer Vision module.
"""


class VisionError(Exception):
    """Base exception for all vision/drawing analysis failures."""


class DrawingClassificationError(VisionError):
    """Raised when drawing classification fails."""


class DrawingOCRError(VisionError):
    """Raised when enhanced OCR for drawings fails."""


class SymbolDetectionError(VisionError):
    """Raised when symbol detection fails."""


class DrawingExtractionError(VisionError):
    """Raised when equipment/relationship extraction from drawings fails."""


class DrawingValidationError(VisionError):
    """Raised when input validation fails."""
