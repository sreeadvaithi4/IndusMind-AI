"""
Data models for the Computer Vision module.

Plain dataclasses representing drawing analysis results —
classification, OCR extractions, detected symbols, equipment,
relationships, and metadata.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DrawingMetadata:
    """Metadata extracted from an engineering drawing."""

    drawing_number: str = ""
    revision: str = ""
    revision_date: str = ""
    drawing_type: str = "unknown"
    author: str = ""
    scale: str = ""
    sheet_number: str = ""
    version: str = ""
    project: str = ""
    plant: str = ""
    title: str = ""
    upload_date: str = ""

    def to_dict(self) -> dict:
        return {
            "drawing_number": self.drawing_number,
            "revision": self.revision,
            "revision_date": self.revision_date,
            "drawing_type": self.drawing_type,
            "author": self.author,
            "scale": self.scale,
            "sheet_number": self.sheet_number,
            "version": self.version,
            "project": self.project,
            "plant": self.plant,
            "title": self.title,
            "upload_date": self.upload_date,
        }


@dataclass
class OCRExtraction:
    """A single text extraction from OCR on a drawing."""

    text: str = ""
    extraction_type: str = ""  # equipment_tag, drawing_number, note, label, etc.
    confidence: float = 0.0
    page_number: int = 1
    coordinates: dict = field(default_factory=dict)  # x, y, width, height

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "extraction_type": self.extraction_type,
            "confidence": self.confidence,
            "page_number": self.page_number,
            "coordinates": self.coordinates,
        }


@dataclass
class DetectedSymbol:
    """A symbol detected in an engineering drawing."""

    symbol_id: str = ""
    symbol_type: str = ""  # pump, valve, tank, etc.
    label: str = ""
    confidence: float = 0.0
    page_number: int = 1
    coordinates: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.symbol_id:
            self.symbol_id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "symbol_id": self.symbol_id,
            "symbol_type": self.symbol_type,
            "label": self.label,
            "confidence": self.confidence,
            "page_number": self.page_number,
            "coordinates": self.coordinates,
            "metadata": self.metadata,
        }


@dataclass
class ExtractedEquipment:
    """An equipment item extracted from a drawing."""

    equipment_id: str = ""
    name: str = ""
    tag: str = ""
    equipment_type: str = ""
    drawing_reference: str = ""
    page_number: int = 1
    coordinates: dict = field(default_factory=dict)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.equipment_id:
            self.equipment_id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "tag": self.tag,
            "equipment_type": self.equipment_type,
            "drawing_reference": self.drawing_reference,
            "page_number": self.page_number,
            "coordinates": self.coordinates,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class DrawingRelationship:
    """A relationship between equipment items in a drawing."""

    relationship_id: str = ""
    relationship_type: str = ""  # connected_to, feeds, monitors, etc.
    source_equipment: str = ""
    target_equipment: str = ""
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.relationship_id:
            self.relationship_id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "relationship_id": self.relationship_id,
            "relationship_type": self.relationship_type,
            "source_equipment": self.source_equipment,
            "target_equipment": self.target_equipment,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class DrawingAnalysisResult:
    """Complete result of analyzing an engineering drawing."""

    document_id: str = ""
    drawing_type: str = "unknown"
    classification_confidence: float = 0.0
    metadata: DrawingMetadata = field(default_factory=DrawingMetadata)
    ocr_extractions: list[OCRExtraction] = field(default_factory=list)
    detected_symbols: list[DetectedSymbol] = field(default_factory=list)
    equipment: list[ExtractedEquipment] = field(default_factory=list)
    relationships: list[DrawingRelationship] = field(default_factory=list)
    duration_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def equipment_count(self) -> int:
        return len(self.equipment)

    @property
    def relationship_count(self) -> int:
        return len(self.relationships)

    @property
    def symbol_count(self) -> int:
        return len(self.detected_symbols)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "drawing_type": self.drawing_type,
            "classification_confidence": self.classification_confidence,
            "metadata": self.metadata.to_dict(),
            "ocr_extraction_count": len(self.ocr_extractions),
            "symbol_count": self.symbol_count,
            "equipment_count": self.equipment_count,
            "relationship_count": self.relationship_count,
            "duration_seconds": self.duration_seconds,
            "warnings": self.warnings,
        }
