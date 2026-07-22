"""
Tests for the Computer Vision / Drawing Analysis module (vision/).

Tests cover:
    - Configuration validation
    - Drawing classification (P&ID, mechanical, electrical, etc.)
    - Enhanced OCR extraction (tags, drawing numbers, revisions, etc.)
    - Symbol detection
    - Equipment extraction from symbols + OCR
    - Relationship extraction
    - Drawing metadata extraction
    - Full analysis pipeline
    - Knowledge Graph integration
    - Empty/invalid input handling
"""

from django.test import TestCase

from knowledge_graph.graph import GraphService
from vision.classifier import ClassificationResult, classify_drawing
from vision.config import VisionConfig, DRAWING_TYPES, SYMBOL_TYPES
from vision.extractor import extract_equipment, extract_relationships
from vision.models import (
    DetectedSymbol,
    DrawingAnalysisResult,
    ExtractedEquipment,
    OCRExtraction,
)
from vision.ocr_engine import extract_drawing_metadata, extract_drawing_ocr
from vision.service import DrawingAnalysisService
from vision.symbols import detect_symbols


# Sample P&ID text for testing
PID_TEXT = """
P&ID - PIPING AND INSTRUMENTATION DIAGRAM
PROJECT: REFINERY EXPANSION PHASE II
DRAWING: DWG-PID-001
REV: B
SHEET 1 OF 3
SCALE: NTS
DRAWN BY: J.SMITH

PROCESS LINE DESCRIPTION:
Pump P-101A (centrifugal pump) is connected to control valve FV-101.
The process line feeds Tank TK-201 via 6 inch pipe.
Pressure transmitter PT-101 monitors the discharge of P-101A.
Temperature transmitter TT-201 is installed on TK-201.
Motor M-101 drives P-101A.

Heat exchanger E-301 is connected to valve V-301B downstream.
Compressor C-501 receives flow from separator V-401.

BOM:
ITEM 1: CENTRIFUGAL PUMP, FLOWSERVE 3X2-10
ITEM 2: CONTROL VALVE, FISHER ET, 4 INCH
ITEM 3: PRESSURE TRANSMITTER, ROSEMOUNT 3051

NOTE: ALL PIPING TO BE SS316L PER API 610
ISO 9001 AND API 610 GOVERN THIS INSTALLATION.
"""

MECHANICAL_TEXT = """
MECHANICAL DRAWING - PUMP ASSEMBLY
TOLERANCE: ±0.5mm
SECTION A-A DETAIL

BILL OF MATERIALS:
ITEM 1: SHAFT, 50mm BORE, SS316
ITEM 2: IMPELLER, CAST IRON
ITEM 3: BEARING SKF 6205
ITEM 4: COUPLING, FLEXIBLE

DIMENSION: 250mm overall length
SCALE: 1:10
DRAWN BY: R.JONES
"""

ELECTRICAL_TEXT = """
ELECTRICAL SINGLE LINE DIAGRAM
SWITCHGEAR: MCC-01
TRANSFORMER: 11kV/415V, 2000kVA
CIRCUIT BREAKER CB-101

VFD drives motor M-101A
PLC INPUT: DI-001 to DI-032
"""


def _make_config(**overrides):
    defaults = {
        "ocr_confidence_threshold": 0.3,
        "symbol_confidence_threshold": 0.5,
        "supported_drawing_types": DRAWING_TYPES,
        "supported_symbol_types": SYMBOL_TYPES,
        "max_equipment_per_drawing": 200,
        "max_relationships_per_drawing": 500,
    }
    defaults.update(overrides)
    return VisionConfig(**defaults)


class DrawingClassificationTests(TestCase):
    """Tests for drawing type classification."""

    def test_classifies_pid(self):
        result = classify_drawing(PID_TEXT)
        self.assertEqual(result.drawing_type, "pid")
        self.assertGreater(result.confidence, 0)

    def test_classifies_mechanical(self):
        result = classify_drawing(MECHANICAL_TEXT)
        self.assertEqual(result.drawing_type, "mechanical")

    def test_classifies_electrical(self):
        result = classify_drawing(ELECTRICAL_TEXT)
        self.assertEqual(result.drawing_type, "electrical")

    def test_classifies_instrumentation(self):
        text = "INSTRUMENTATION LOOP DIAGRAM\nPT-101 transmitter 4-20mA signal"
        result = classify_drawing(text)
        self.assertEqual(result.drawing_type, "instrumentation")

    def test_classifies_general_arrangement(self):
        text = "GENERAL ARRANGEMENT DRAWING\nPLAN VIEW ELEVATION"
        result = classify_drawing(text)
        self.assertEqual(result.drawing_type, "general_arrangement")

    def test_unknown_for_empty_text(self):
        result = classify_drawing("")
        self.assertEqual(result.drawing_type, "unknown")
        self.assertEqual(result.confidence, 0.0)

    def test_unknown_for_non_engineering_text(self):
        result = classify_drawing("This is a regular document about cats and dogs.")
        self.assertEqual(result.drawing_type, "unknown")


class DrawingOCRExtractionTests(TestCase):
    """Tests for enhanced OCR extraction."""

    def test_extracts_equipment_tags(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        tags = [e for e in extractions if e.extraction_type == "equipment_tag"]
        tag_texts = [t.text for t in tags]
        self.assertIn("P-101A", tag_texts)
        self.assertIn("FV-101", tag_texts)
        self.assertIn("TK-201", tag_texts)

    def test_extracts_drawing_number(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        dwg_nums = [e for e in extractions if e.extraction_type == "drawing_number"]
        self.assertGreater(len(dwg_nums), 0)

    def test_extracts_revision(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        revisions = [e for e in extractions if e.extraction_type == "revision_number"]
        self.assertGreater(len(revisions), 0)
        self.assertTrue(any("B" in r.text for r in revisions))

    def test_extracts_instrument_ids(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        instruments = [e for e in extractions if e.extraction_type == "instrument_id"]
        instrument_texts = [i.text for i in instruments]
        self.assertIn("PT-101", instrument_texts)
        self.assertIn("TT-201", instrument_texts)

    def test_extracts_sheet_number(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        sheets = [e for e in extractions if e.extraction_type == "sheet_number"]
        self.assertGreater(len(sheets), 0)

    def test_extracts_notes(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        notes = [e for e in extractions if e.extraction_type == "note"]
        self.assertGreater(len(notes), 0)

    def test_extracts_dimensions(self):
        extractions = extract_drawing_ocr(MECHANICAL_TEXT)
        dims = [e for e in extractions if e.extraction_type == "dimension"]
        self.assertGreater(len(dims), 0)

    def test_extracts_bom(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        bom = [e for e in extractions if e.extraction_type == "bom_text"]
        self.assertGreater(len(bom), 0)

    def test_empty_text_returns_empty(self):
        extractions = extract_drawing_ocr("")
        self.assertEqual(len(extractions), 0)

    def test_confidence_scores_assigned(self):
        extractions = extract_drawing_ocr(PID_TEXT)
        for extraction in extractions:
            self.assertGreater(extraction.confidence, 0.0)
            self.assertLessEqual(extraction.confidence, 1.0)

    def test_respects_confidence_threshold(self):
        # High threshold should filter out low-confidence extractions
        high_threshold = extract_drawing_ocr(PID_TEXT, confidence_threshold=0.9)
        low_threshold = extract_drawing_ocr(PID_TEXT, confidence_threshold=0.3)
        self.assertLessEqual(len(high_threshold), len(low_threshold))


class DrawingMetadataExtractionTests(TestCase):
    """Tests for drawing metadata extraction."""

    def test_extracts_metadata_from_pid(self):
        metadata = extract_drawing_metadata(PID_TEXT)
        self.assertIn("PID", metadata.drawing_number.upper())
        self.assertEqual(metadata.revision, "B")
        self.assertEqual(metadata.scale, "NTS")

    def test_extracts_author(self):
        metadata = extract_drawing_metadata(PID_TEXT)
        self.assertIn("SMITH", metadata.author.upper())


class SymbolDetectionTests(TestCase):
    """Tests for symbol detection."""

    def test_detects_pump_symbols(self):
        symbols = detect_symbols(PID_TEXT)
        pump_symbols = [s for s in symbols if s.symbol_type == "pump"]
        self.assertGreater(len(pump_symbols), 0)

    def test_detects_valve_symbols(self):
        symbols = detect_symbols(PID_TEXT)
        valve_symbols = [s for s in symbols if s.symbol_type in ("valve", "control_valve")]
        self.assertGreater(len(valve_symbols), 0)

    def test_detects_tank_symbols(self):
        symbols = detect_symbols(PID_TEXT)
        tank_symbols = [s for s in symbols if s.symbol_type == "tank"]
        self.assertGreater(len(tank_symbols), 0)

    def test_detects_instruments(self):
        symbols = detect_symbols(PID_TEXT)
        instruments = [s for s in symbols if s.symbol_type in ("pressure_sensor", "temperature_sensor", "flow_meter")]
        self.assertGreater(len(instruments), 0)

    def test_detects_motor(self):
        symbols = detect_symbols(PID_TEXT)
        motors = [s for s in symbols if s.symbol_type == "motor"]
        self.assertGreater(len(motors), 0)

    def test_detects_heat_exchanger(self):
        symbols = detect_symbols(PID_TEXT)
        hx = [s for s in symbols if s.symbol_type == "heat_exchanger"]
        self.assertGreater(len(hx), 0)

    def test_empty_text_returns_empty(self):
        symbols = detect_symbols("")
        self.assertEqual(len(symbols), 0)

    def test_confidence_threshold_filters(self):
        high = detect_symbols(PID_TEXT, confidence_threshold=0.9)
        low = detect_symbols(PID_TEXT, confidence_threshold=0.3)
        self.assertLessEqual(len(high), len(low))


class EquipmentExtractionTests(TestCase):
    """Tests for equipment extraction."""

    def test_extracts_equipment_from_symbols(self):
        symbols = [
            DetectedSymbol(symbol_type="pump", label="P-101A", confidence=0.8),
            DetectedSymbol(symbol_type="valve", label="V-201B", confidence=0.8),
        ]
        equipment = extract_equipment(symbols, [], "doc-1")
        self.assertEqual(len(equipment), 2)
        self.assertEqual(equipment[0].tag, "P-101A")
        self.assertEqual(equipment[0].equipment_type, "pump")

    def test_extracts_equipment_from_ocr(self):
        ocr = [
            OCRExtraction(text="TK-301", extraction_type="equipment_tag", confidence=0.85),
        ]
        equipment = extract_equipment([], ocr, "doc-1")
        self.assertEqual(len(equipment), 1)
        self.assertEqual(equipment[0].tag, "TK-301")
        self.assertEqual(equipment[0].equipment_type, "tank")

    def test_deduplicates_equipment(self):
        symbols = [DetectedSymbol(symbol_type="pump", label="P-101A", confidence=0.8)]
        ocr = [OCRExtraction(text="P-101A", extraction_type="equipment_tag", confidence=0.85)]
        equipment = extract_equipment(symbols, ocr, "doc-1")
        self.assertEqual(len(equipment), 1)


class RelationshipExtractionTests(TestCase):
    """Tests for relationship extraction from drawings."""

    def test_extracts_relationships_from_pid(self):
        symbols = detect_symbols(PID_TEXT)
        ocr = extract_drawing_ocr(PID_TEXT)
        equipment = extract_equipment(symbols, ocr, "doc-1")
        relationships = extract_relationships(equipment, symbols, PID_TEXT, "doc-1")
        self.assertGreater(len(relationships), 0)

    def test_relationship_types_are_valid(self):
        symbols = detect_symbols(PID_TEXT)
        ocr = extract_drawing_ocr(PID_TEXT)
        equipment = extract_equipment(symbols, ocr, "doc-1")
        relationships = extract_relationships(equipment, symbols, PID_TEXT, "doc-1")

        valid_types = {"connected_to", "feeds", "monitors", "drives", "controls"}
        for rel in relationships:
            self.assertIn(rel.relationship_type, valid_types)


class DrawingAnalysisServiceTests(TestCase):
    """Tests for the full DrawingAnalysisService."""

    def setUp(self):
        GraphService.reset()
        self.config = _make_config()

    def test_full_analysis_of_pid(self):
        result = DrawingAnalysisService.analyze_drawing(
            PID_TEXT, "doc-1", config=self.config
        )
        self.assertIsInstance(result, DrawingAnalysisResult)
        self.assertEqual(result.drawing_type, "pid")
        self.assertGreater(result.equipment_count, 0)
        self.assertGreater(result.symbol_count, 0)
        self.assertGreater(len(result.ocr_extractions), 0)

    def test_full_analysis_populates_knowledge_graph(self):
        DrawingAnalysisService.analyze_drawing(
            PID_TEXT, "doc-1", config=self.config
        )
        stats = GraphService.get_statistics()
        self.assertGreater(stats["total_nodes"], 0)

    def test_is_engineering_drawing_true_for_pid(self):
        self.assertTrue(DrawingAnalysisService.is_engineering_drawing(PID_TEXT))

    def test_is_engineering_drawing_false_for_regular_text(self):
        self.assertFalse(
            DrawingAnalysisService.is_engineering_drawing("A regular document about nothing.")
        )

    def test_empty_text_returns_empty_result(self):
        result = DrawingAnalysisService.analyze_drawing("", "doc-1", config=self.config)
        self.assertEqual(result.equipment_count, 0)
        self.assertIn("Empty text", result.warnings[0])

    def test_missing_document_id_raises(self):
        from vision.exceptions import VisionError
        with self.assertRaises(VisionError):
            DrawingAnalysisService.analyze_drawing(PID_TEXT, "")

    def test_result_to_dict(self):
        result = DrawingAnalysisService.analyze_drawing(
            PID_TEXT, "doc-1", config=self.config
        )
        result_dict = result.to_dict()
        self.assertIn("drawing_type", result_dict)
        self.assertIn("equipment_count", result_dict)
        self.assertIn("metadata", result_dict)

    def test_analysis_of_mechanical_drawing(self):
        result = DrawingAnalysisService.analyze_drawing(
            MECHANICAL_TEXT, "doc-2", config=self.config
        )
        self.assertEqual(result.drawing_type, "mechanical")

    def test_analysis_of_electrical_drawing(self):
        result = DrawingAnalysisService.analyze_drawing(
            ELECTRICAL_TEXT, "doc-3", config=self.config
        )
        self.assertEqual(result.drawing_type, "electrical")
