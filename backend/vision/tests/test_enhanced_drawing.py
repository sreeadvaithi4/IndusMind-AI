"""
Tests for enhanced Drawing Intelligence (Sprint 18).

Tests cover: Gemini analysis, drawing warnings, caching, enhanced
analysis, RAG context generation.
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase

from knowledge_graph.graph import GraphService
from vision.cache import clear_cache, get_cached_analysis, set_cached_analysis
from vision.drawing_warnings import DrawingWarning, generate_drawing_warnings
from vision.gemini_analysis import analyze_with_gemini
from vision.models import (
    DetectedSymbol,
    DrawingAnalysisResult,
    DrawingMetadata,
    ExtractedEquipment,
    DrawingRelationship,
    OCRExtraction,
)
from vision.service import DrawingAnalysisService
from agents.config import RAGConfig


PID_TEXT = """
P&ID - PIPING AND INSTRUMENTATION DIAGRAM
DWG-PID-001 REV: B
Pump P-101A connected to valve FV-101.
Tank TK-201 receives flow. PT-101 monitors pressure.
Motor M-101 drives P-101A. Heat exchanger E-301.
NOTE: ALL PIPING SS316L PER API 610
"""


class DrawingWarningsTests(TestCase):
    """Tests for drawing warning generation."""

    def test_warns_on_missing_drawing_number(self):
        result = DrawingAnalysisResult(
            document_id="doc-1",
            drawing_type="pid",
            metadata=DrawingMetadata(drawing_number=""),
            equipment=[ExtractedEquipment(tag="P-101")],
        )
        warnings = generate_drawing_warnings(result)
        issues = [w.issue for w in warnings]
        self.assertIn("Missing drawing number", issues)

    def test_warns_on_missing_revision(self):
        result = DrawingAnalysisResult(
            document_id="doc-1",
            drawing_type="pid",
            metadata=DrawingMetadata(drawing_number="DWG-001", revision=""),
        )
        warnings = generate_drawing_warnings(result)
        issues = [w.issue for w in warnings]
        self.assertIn("Missing revision information", issues)

    def test_warns_on_disconnected_equipment(self):
        result = DrawingAnalysisResult(
            document_id="doc-1",
            equipment=[
                ExtractedEquipment(tag="P-101"),
                ExtractedEquipment(tag="V-201"),
                ExtractedEquipment(tag="T-301"),
            ],
            relationships=[
                DrawingRelationship(source_equipment="P-101", target_equipment="V-201"),
            ],
        )
        warnings = generate_drawing_warnings(result)
        disconnected_warnings = [w for w in warnings if "Disconnected" in w.issue]
        self.assertGreater(len(disconnected_warnings), 0)

    def test_warns_on_low_ocr_confidence(self):
        result = DrawingAnalysisResult(
            document_id="doc-1",
            ocr_extractions=[
                OCRExtraction(text="P-101", confidence=0.3),
                OCRExtraction(text="V-201", confidence=0.2),
            ],
        )
        warnings = generate_drawing_warnings(result)
        low_conf = [w for w in warnings if "Low OCR" in w.issue]
        self.assertGreater(len(low_conf), 0)

    def test_no_warnings_for_complete_drawing(self):
        result = DrawingAnalysisResult(
            document_id="doc-1",
            drawing_type="pid",
            metadata=DrawingMetadata(drawing_number="DWG-001", revision="A"),
            equipment=[ExtractedEquipment(tag="P-101")],
            relationships=[DrawingRelationship(source_equipment="P-101", target_equipment="V-201")],
            ocr_extractions=[OCRExtraction(text="P-101", confidence=0.9)],
        )
        warnings = generate_drawing_warnings(result)
        # Should have no critical warnings for a well-formed drawing
        critical = [w for w in warnings if w.severity == "critical"]
        self.assertEqual(len(critical), 0)

    def test_warning_to_dict(self):
        w = DrawingWarning(severity="high", issue="Test", reason="R", confidence=0.8, recommendation="Fix it")
        d = w.to_dict()
        self.assertEqual(d["severity"], "high")
        self.assertEqual(d["issue"], "Test")


class DrawingCacheTests(TestCase):
    """Tests for drawing analysis cache."""

    def setUp(self):
        clear_cache()

    def test_cache_miss(self):
        self.assertIsNone(get_cached_analysis("doc-1"))

    def test_cache_set_and_get(self):
        data = {"equipment": [{"tag": "P-101"}]}
        set_cached_analysis("doc-1", data)
        result = get_cached_analysis("doc-1")
        self.assertEqual(result, data)

    def test_clear_cache(self):
        set_cached_analysis("doc-1", {"x": 1})
        clear_cache()
        self.assertIsNone(get_cached_analysis("doc-1"))


class GeminiAnalysisTests(TestCase):
    """Tests for Gemini-powered drawing analysis."""

    def test_returns_empty_without_api_key(self):
        config = RAGConfig(api_key="")
        result = analyze_with_gemini("P-101A pump", ["P-101A"], "pid", config)
        self.assertEqual(result, {})

    def test_returns_empty_for_empty_text(self):
        config = RAGConfig(api_key="test-key")
        result = analyze_with_gemini("", [], "unknown", config)
        self.assertEqual(result, {})

    @patch("vision.gemini_analysis.GeminiService.generate")
    def test_parses_valid_json_response(self, mock_generate):
        mock_response = MagicMock()
        mock_response.text = '{"equipment_summary": [{"tag": "P-101A", "type": "pump"}], "pipelines": [], "engineering_notes": [], "warnings": [], "insights": "Test"}'
        mock_generate.return_value = mock_response

        config = RAGConfig(api_key="test-key")
        result = analyze_with_gemini("P-101A pump", ["P-101A"], "pid", config)
        self.assertIn("equipment_summary", result)
        self.assertEqual(result["equipment_summary"][0]["tag"], "P-101A")

    @patch("vision.gemini_analysis.GeminiService.generate")
    def test_handles_invalid_json(self, mock_generate):
        mock_response = MagicMock()
        mock_response.text = "This is not JSON"
        mock_generate.return_value = mock_response

        config = RAGConfig(api_key="test-key")
        result = analyze_with_gemini("text", [], "pid", config)
        self.assertEqual(result, {})


class EnhancedDrawingAnalysisTests(TestCase):
    """Tests for the enhanced drawing analysis service."""

    def setUp(self):
        GraphService.reset()
        clear_cache()

    def test_enhanced_analysis_returns_structured_dict(self):
        result = DrawingAnalysisService.analyze_drawing_enhanced(PID_TEXT, "doc-1")
        self.assertIsInstance(result, dict)
        self.assertIn("document_id", result)
        self.assertIn("drawing_type", result)
        self.assertIn("equipment", result)
        self.assertIn("drawing_warnings", result)
        self.assertEqual(result["drawing_type"], "pid")

    def test_enhanced_analysis_uses_cache(self):
        # First call
        result1 = DrawingAnalysisService.analyze_drawing_enhanced(PID_TEXT, "doc-1")
        # Second call should use cache (no re-analysis)
        result2 = DrawingAnalysisService.analyze_drawing_enhanced(PID_TEXT, "doc-1")
        self.assertEqual(result1, result2)

    def test_enhanced_analysis_generates_warnings(self):
        result = DrawingAnalysisService.analyze_drawing_enhanced(PID_TEXT, "doc-1")
        # PID_TEXT has revision info but should generate some warnings
        self.assertIsInstance(result["drawing_warnings"], list)

    def test_get_drawing_context_for_rag(self):
        # Run analysis first to populate cache
        DrawingAnalysisService.analyze_drawing_enhanced(PID_TEXT, "doc-1")
        # Get RAG context
        context = DrawingAnalysisService.get_drawing_context_for_rag("doc-1")
        self.assertIn("Engineering Drawing", context)
        self.assertIn("pid", context.lower())

    def test_get_drawing_context_empty_without_cache(self):
        context = DrawingAnalysisService.get_drawing_context_for_rag("nonexistent")
        self.assertEqual(context, "")
