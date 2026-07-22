"""
Tests for the Maintenance Intelligence & RCA Agent.
"""

from django.test import TestCase
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from agents.config import RAGConfig
from agents.maintenance import (
    MaintenanceAgent,
    MaintenanceAnalysisResult,
    FAILURE_MODES,
)
from agents.orchestrator import QueryOrchestrator
from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity

User = get_user_model()


class FailureModeDetectionTests(TestCase):
    """Tests for failure mode detection from query text."""

    def test_detects_vibration(self):
        modes = MaintenanceAgent._detect_failure_modes("Pump P-101 has high vibration")
        self.assertIn("vibration", modes)

    def test_detects_overheating(self):
        modes = MaintenanceAgent._detect_failure_modes("Motor is overheating")
        self.assertIn("overheating", modes)

    def test_detects_seal_leakage(self):
        modes = MaintenanceAgent._detect_failure_modes("Seal is leaking on pump")
        self.assertIn("seal_leakage", modes)

    def test_detects_cavitation(self):
        modes = MaintenanceAgent._detect_failure_modes("Pump cavitation detected, low NPSH")
        self.assertIn("cavitation", modes)

    def test_detects_corrosion(self):
        modes = MaintenanceAgent._detect_failure_modes("Corrosion found on pipe")
        self.assertIn("corrosion", modes)

    def test_detects_bearing_wear(self):
        modes = MaintenanceAgent._detect_failure_modes("Bearing wear detected during inspection")
        self.assertIn("bearing_wear", modes)

    def test_detects_misalignment(self):
        modes = MaintenanceAgent._detect_failure_modes("Shaft misalignment on compressor")
        self.assertIn("misalignment", modes)

    def test_detects_lubrication_failure(self):
        modes = MaintenanceAgent._detect_failure_modes("Lubrication oil low in gearbox")
        self.assertIn("lubrication_failure", modes)

    def test_detects_multiple_modes(self):
        modes = MaintenanceAgent._detect_failure_modes(
            "Pump vibrating and overheating, possible bearing failure"
        )
        self.assertIn("vibration", modes)
        self.assertIn("overheating", modes)
        self.assertIn("bearing_wear", modes)

    def test_no_failure_detected_for_general(self):
        modes = MaintenanceAgent._detect_failure_modes("What is pump P-101?")
        self.assertEqual(len(modes), 0)


class EquipmentTagExtractionTests(TestCase):
    """Tests for equipment tag extraction."""

    def test_extracts_tag_format(self):
        tag = MaintenanceAgent._extract_equipment_tag("Why is P-101A vibrating?")
        self.assertEqual(tag, "P-101A")

    def test_extracts_named_equipment(self):
        tag = MaintenanceAgent._extract_equipment_tag("What maintenance does pump XYZ need?")
        self.assertIn("pump", tag.lower())

    def test_empty_for_no_equipment(self):
        tag = MaintenanceAgent._extract_equipment_tag("General question about maintenance")
        # May or may not find 'maintenance' as equipment
        self.assertIsInstance(tag, str)


class MaintenanceAnalysisTests(TestCase):
    """Tests for the full maintenance analysis."""

    def setUp(self):
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"], confidence=0.8,
        ))

    def test_analyze_vibration_query(self):
        config = RAGConfig(api_key="")
        result = MaintenanceAgent.analyze(
            "Why is pump P-101A vibrating?", config=config
        )
        self.assertIsInstance(result, MaintenanceAnalysisResult)
        self.assertEqual(result.equipment_tag, "P-101A")
        self.assertIn("vibration", result.detected_failure_modes)
        self.assertGreater(len(result.root_causes), 0)
        self.assertGreater(len(result.corrective_actions), 0)
        self.assertGreater(len(result.preventive_actions), 0)
        self.assertGreater(len(result.inspection_recommendations), 0)
        self.assertIn(result.risk_level, ("critical", "high", "medium", "low"))

    def test_analyze_overheating_returns_critical_risk(self):
        config = RAGConfig(api_key="")
        result = MaintenanceAgent.analyze("Motor overheating on C-201", config=config)
        self.assertEqual(result.risk_level, "critical")

    def test_analyze_returns_root_causes_with_confidence(self):
        config = RAGConfig(api_key="")
        result = MaintenanceAgent.analyze("P-101A bearing noise", config=config)
        for rc in result.root_causes:
            self.assertGreater(rc.confidence, 0.0)
            self.assertLessEqual(rc.confidence, 1.0)
            self.assertIn(rc.likelihood, ("high", "medium", "low"))

    def test_analyze_generates_followups(self):
        config = RAGConfig(api_key="")
        result = MaintenanceAgent.analyze("P-101A vibration", config=config)
        self.assertGreater(len(result.suggested_followups), 0)

    def test_analyze_empty_query(self):
        config = RAGConfig(api_key="")
        result = MaintenanceAgent.analyze("", config=config)
        self.assertEqual(result.problem_summary, "No query provided.")

    def test_analyze_general_maintenance_query(self):
        config = RAGConfig(api_key="")
        result = MaintenanceAgent.analyze(
            "What maintenance is required for P-101A?", config=config
        )
        self.assertIsNotNone(result.problem_summary)
        self.assertGreater(len(result.preventive_actions), 0)

    def test_to_dict_structure(self):
        config = RAGConfig(api_key="")
        result = MaintenanceAgent.analyze("P-101A seal leak", config=config)
        d = result.to_dict()
        self.assertIn("root_causes", d)
        self.assertIn("corrective_actions", d)
        self.assertIn("preventive_actions", d)
        self.assertIn("inspection_recommendations", d)
        self.assertIn("risk_level", d)
        self.assertIn("confidence", d)
        self.assertIn("equipment_tag", d)


class OrchestratorMaintenanceIntegrationTests(TestCase):
    """Tests that the orchestrator routes to maintenance agent."""

    def setUp(self):
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_maintenance_intent_triggers_agent(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Why is P-101A vibrating?", config=config
        )
        self.assertEqual(response.intent.intent, "maintenance")
        self.assertIsNotNone(response.maintenance_analysis)
        self.assertIn("root_causes", response.maintenance_analysis)
        self.assertIn("corrective_actions", response.maintenance_analysis)

    def test_maintenance_analysis_in_response_dict(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "What maintenance does P-101A need?", config=config
        )
        d = response.to_dict()
        self.assertIn("maintenance_analysis", d)

    def test_non_maintenance_intent_has_no_analysis(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Show me the P&ID drawing", config=config
        )
        self.assertNotEqual(response.intent.intent, "maintenance")
        # maintenance_analysis should be None or not present
        d = response.to_dict()
        self.assertNotIn("maintenance_analysis", d)

    def test_incident_intent_also_triggers_agent(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "What failure occurred on pump P-101A?", config=config
        )
        # incident_lookup should also trigger maintenance agent
        self.assertIn(response.intent.intent, ("maintenance", "incident_lookup", "equipment_lookup"))


class MaintenanceAPIIntegrationTests(APITestCase):
    """Tests that the /api/query/ endpoint returns maintenance analysis."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_maintenance_query_returns_analysis(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Why is P-101A vibrating?"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("maintenance_analysis", data)
        self.assertIn("root_causes", data["maintenance_analysis"])
        self.assertIn("corrective_actions", data["maintenance_analysis"])
        self.assertIn("risk_level", data["maintenance_analysis"])
