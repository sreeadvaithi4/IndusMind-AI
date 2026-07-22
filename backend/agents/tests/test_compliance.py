"""
Tests for the Quality Intelligence & Compliance Agent.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from agents.compliance import (
    QualityComplianceAgent,
    ComplianceAnalysisResult,
    REGULATORY_STANDARDS,
)
from agents.config import RAGConfig
from agents.orchestrator import QueryOrchestrator
from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity

User = get_user_model()


class ComplianceTopicDetectionTests(TestCase):
    """Tests for compliance topic detection."""

    def test_detects_capa(self):
        topics = QualityComplianceAgent._detect_compliance_topics("Show CAPA for pump")
        self.assertIn("capa", topics)

    def test_detects_ncr(self):
        topics = QualityComplianceAgent._detect_compliance_topics("Show NCR history")
        self.assertIn("ncr", topics)

    def test_detects_audit(self):
        topics = QualityComplianceAgent._detect_compliance_topics("Generate audit report")
        self.assertIn("audit", topics)

    def test_detects_calibration(self):
        topics = QualityComplianceAgent._detect_compliance_topics("Show calibration records")
        self.assertIn("calibration", topics)

    def test_detects_sop(self):
        topics = QualityComplianceAgent._detect_compliance_topics("Which SOP applies?")
        self.assertIn("sop", topics)

    def test_detects_gap_analysis(self):
        topics = QualityComplianceAgent._detect_compliance_topics("Show compliance gaps")
        self.assertIn("gap_analysis", topics)

    def test_detects_standards(self):
        topics = QualityComplianceAgent._detect_compliance_topics("Compare with ISO 9001")
        self.assertIn("standard", topics)


class StandardIdentificationTests(TestCase):
    """Tests for regulatory standard identification."""

    def test_identifies_iso_9001(self):
        standards = QualityComplianceAgent._identify_standards("Is this compliant with ISO 9001?")
        names = [s["name"] for s in standards]
        self.assertIn("ISO 9001", names)

    def test_identifies_api(self):
        standards = QualityComplianceAgent._identify_standards("Check API standards")
        names = [s["name"] for s in standards]
        self.assertIn("API Standards", names)

    def test_identifies_asme(self):
        standards = QualityComplianceAgent._identify_standards("ASME requirements")
        names = [s["name"] for s in standards]
        self.assertIn("ASME", names)

    def test_suggests_standards_for_quality_query(self):
        standards = QualityComplianceAgent._identify_standards("quality management system gaps")
        self.assertGreater(len(standards), 0)

    def test_suggests_standards_for_equipment(self):
        standards = QualityComplianceAgent._identify_standards("pump pressure vessel compliance")
        names = [s["name"] for s in standards]
        self.assertTrue(any("API" in n or "ASME" in n for n in names))


class ComplianceAnalysisTests(TestCase):
    """Tests for full compliance analysis."""

    def setUp(self):
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="regulation", name="ISO 9001",
            source_document_ids=["doc-1"],
        ))
        GraphService.add_entity(Entity(
            entity_id="e2", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_analyze_compliance_query(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze(
            "Is pump P-101A compliant with ISO 9001?", config=config
        )
        self.assertIsInstance(result, ComplianceAnalysisResult)
        self.assertIn(result.compliance_status, ("compliant", "partially_compliant", "non_compliant", "unknown"))
        self.assertGreater(len(result.applicable_standards), 0)

    def test_analyze_capa_query(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("Show open CAPA items", config=config)
        self.assertIsNotNone(result.compliance_summary)

    def test_analyze_audit_query(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("Generate audit report for area 3", config=config)
        self.assertIsNotNone(result.compliance_summary)
        self.assertIsInstance(result.audit_findings, list)

    def test_analyze_sop_query(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("Which SOP applies to pump maintenance?", config=config)
        self.assertIsNotNone(result.compliance_summary)

    def test_analyze_calibration_query(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("Show calibration status for instruments", config=config)
        self.assertIsNotNone(result.compliance_summary)

    def test_compliance_score_range(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("Check compliance status", config=config)
        self.assertGreaterEqual(result.compliance_score, 0.0)
        self.assertLessEqual(result.compliance_score, 1.0)

    def test_empty_query_returns_empty(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("", config=config)
        self.assertEqual(result.compliance_summary, "No query provided.")

    def test_generates_followups(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("ISO 9001 compliance check", config=config)
        self.assertGreater(len(result.suggested_followups), 0)

    def test_to_dict_structure(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("Audit compliance", config=config)
        d = result.to_dict()
        self.assertIn("compliance_status", d)
        self.assertIn("compliance_score", d)
        self.assertIn("applicable_standards", d)
        self.assertIn("compliance_gaps", d)
        self.assertIn("audit_findings", d)
        self.assertIn("required_actions", d)
        self.assertIn("missing_documents", d)
        self.assertIn("confidence", d)
        self.assertIn("evidence_score", d)

    def test_identifies_missing_documents(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("Show SOP and calibration for P-101", config=config)
        # With no documents in ChromaDB, should identify missing docs
        self.assertIsInstance(result.missing_documents, list)

    def test_required_evidence_generated(self):
        config = RAGConfig(api_key="")
        result = QualityComplianceAgent.analyze("ISO 9001 audit preparation", config=config)
        self.assertGreater(len(result.required_evidence), 0)


class OrchestratorComplianceIntegrationTests(TestCase):
    """Tests that the orchestrator routes to compliance agent."""

    def setUp(self):
        GraphService.reset()

    def test_compliance_intent_triggers_agent(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Is this compliant with ISO 9001?", config=config
        )
        self.assertEqual(response.intent.intent, "compliance")
        self.assertIsNotNone(response.compliance_analysis)
        self.assertIn("compliance_status", response.compliance_analysis)

    def test_qms_query_triggers_agent(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Show CAPA and NCR for area 3", config=config
        )
        self.assertEqual(response.intent.intent, "compliance")
        self.assertIsNotNone(response.compliance_analysis)

    def test_non_compliance_query_no_analysis(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "What is the weather today?", config=config
        )
        self.assertNotEqual(response.intent.intent, "compliance")
        d = response.to_dict()
        self.assertNotIn("compliance_analysis", d)

    def test_compliance_response_in_api(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Generate audit report for ISO 9001 compliance", config=config
        )
        d = response.to_dict()
        self.assertIn("compliance_analysis", d)
        self.assertIn("compliance_score", d["compliance_analysis"])


class ComplianceAPITests(APITestCase):
    """Tests that /api/query/ returns compliance analysis."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        GraphService.reset()

    def test_compliance_query_via_api(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Check ISO 9001 compliance for pump area"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("compliance_analysis", data)
        self.assertIn("compliance_status", data["compliance_analysis"])
        self.assertIn("applicable_standards", data["compliance_analysis"])

    def test_calibration_query_via_api(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Show calibration records and compliance status"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("compliance_analysis", data)
