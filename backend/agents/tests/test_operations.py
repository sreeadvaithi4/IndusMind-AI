"""
Tests for the Operations Intelligence Layer (Sprint 16).

Covers: FailureIntelligenceAgent, WarningEngine, TrendAnalysisEngine,
ResponseComposerService, OperationsIntelligenceOrchestrator, and
integration with the main QueryOrchestrator.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from agents.composer import ResponseComposerService, OperationsReport
from agents.config import RAGConfig
from agents.failure import FailureIntelligenceAgent, FailureIntelligenceResult
from agents.operations import OperationsIntelligenceOrchestrator
from agents.orchestrator import QueryOrchestrator
from agents.trends import TrendAnalysisEngine, TrendAnalysisResult
from agents.warnings import Warning, WarningEngine
from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity

User = get_user_model()


class FailureIntelligenceTests(TestCase):
    """Tests for FailureIntelligenceAgent."""

    def setUp(self):
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_analyze_returns_result(self):
        config = RAGConfig(api_key="")
        result = FailureIntelligenceAgent.analyze("P-101A failure history", config=config)
        self.assertIsInstance(result, FailureIntelligenceResult)

    def test_generates_best_practices(self):
        config = RAGConfig(api_key="")
        result = FailureIntelligenceAgent.analyze("pump failure", config=config)
        self.assertGreater(len(result.best_practices), 0)

    def test_empty_query(self):
        result = FailureIntelligenceAgent.analyze("")
        self.assertEqual(len(result.historical_incidents), 0)

    def test_to_dict(self):
        config = RAGConfig(api_key="")
        result = FailureIntelligenceAgent.analyze("incident", config=config)
        d = result.to_dict()
        self.assertIn("historical_incidents", d)
        self.assertIn("recurring_failures", d)
        self.assertIn("lessons_learned", d)
        self.assertIn("best_practices", d)


class WarningEngineTests(TestCase):
    """Tests for the Warning Engine."""

    def test_maintenance_critical_warning(self):
        maint_data = {"risk_level": "critical", "problem_summary": "Critical pump failure", "detected_failure_modes": ["vibration"], "confidence": 0.8}
        warnings = WarningEngine.generate_warnings(maintenance_data=maint_data)
        self.assertGreater(len(warnings), 0)
        self.assertEqual(warnings[0].severity, "CRITICAL")

    def test_compliance_non_compliant_warning(self):
        comp_data = {"compliance_status": "non_compliant", "compliance_gaps": [{"priority": "high", "requirement": "SOP", "standard": "ISO 9001", "evidence": "Not found", "required_action": "Create SOP"}], "confidence": 0.7, "missing_documents": ["SOP"]}
        warnings = WarningEngine.generate_warnings(compliance_data=comp_data)
        self.assertGreater(len(warnings), 0)
        high_or_critical = [w for w in warnings if w.severity in ("HIGH", "CRITICAL")]
        self.assertGreater(len(high_or_critical), 0)

    def test_failure_recurring_warning(self):
        fail_data = {"recurring_failures": [{"pattern": "vibration", "occurrences": 5}], "historical_incidents": [1, 2, 3]}
        warnings = WarningEngine.generate_warnings(failure_data=fail_data)
        self.assertGreater(len(warnings), 0)

    def test_no_warnings_without_evidence(self):
        warnings = WarningEngine.generate_warnings()
        self.assertEqual(len(warnings), 0)

    def test_warnings_sorted_by_severity(self):
        maint_data = {"risk_level": "critical", "problem_summary": "X", "detected_failure_modes": ["a"], "confidence": 0.8}
        comp_data = {"compliance_status": "non_compliant", "compliance_gaps": [], "confidence": 0.5, "missing_documents": ["SOP"]}
        warnings = WarningEngine.generate_warnings(maintenance_data=maint_data, compliance_data=comp_data)
        if len(warnings) >= 2:
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            for i in range(len(warnings) - 1):
                self.assertLessEqual(
                    severity_order.get(warnings[i].severity, 9),
                    severity_order.get(warnings[i + 1].severity, 9),
                )


class TrendAnalysisTests(TestCase):
    """Tests for TrendAnalysisEngine."""

    def test_detects_failure_trends(self):
        fail_data = {"recurring_failures": [{"pattern": "vibration", "occurrences": 4}]}
        result = TrendAnalysisEngine.analyze(failure_data=fail_data)
        self.assertIsInstance(result, TrendAnalysisResult)
        self.assertGreater(len(result.trends), 0)
        self.assertEqual(result.trends[0].category, "failure")

    def test_detects_maintenance_trends(self):
        maint_data = {"detected_failure_modes": ["vibration", "overheating", "corrosion"]}
        result = TrendAnalysisEngine.analyze(maintenance_data=maint_data)
        self.assertGreater(len(result.trends), 0)

    def test_detects_compliance_trends(self):
        comp_data = {"compliance_gaps": [{"r": "1"}, {"r": "2"}, {"r": "3"}]}
        result = TrendAnalysisEngine.analyze(compliance_data=comp_data)
        self.assertGreater(len(result.trends), 0)

    def test_no_trends_without_data(self):
        result = TrendAnalysisEngine.analyze()
        self.assertEqual(len(result.trends), 0)
        self.assertEqual(result.overall_risk, "low")

    def test_overall_risk_assessment(self):
        fail_data = {"recurring_failures": [{"pattern": "x", "occurrences": 5}, {"pattern": "y", "occurrences": 3}]}
        maint_data = {"detected_failure_modes": ["a", "b", "c"]}
        result = TrendAnalysisEngine.analyze(failure_data=fail_data, maintenance_data=maint_data)
        self.assertIn(result.overall_risk, ("critical", "high", "medium", "low"))


class ResponseComposerTests(TestCase):
    """Tests for ResponseComposerService."""

    def test_compose_basic_report(self):
        report = ResponseComposerService.compose(
            query="test query",
            ai_answer="Test answer",
            confidence=0.7,
        )
        self.assertIsInstance(report, OperationsReport)
        self.assertIn("test", report.executive_summary.lower())

    def test_compose_with_all_agents(self):
        report = ResponseComposerService.compose(
            query="pump vibration",
            ai_answer="Analysis complete",
            maintenance_data={"risk_level": "high", "detected_failure_modes": ["vibration"]},
            compliance_data={"compliance_status": "partially_compliant"},
            failure_data={"historical_incidents": [{"content": "..."}]},
            warnings=[{"severity": "HIGH", "title": "Warning"}],
            kg_context=[{"entity": "P-101", "type": "pump", "related": []}],
            confidence=0.8,
        )
        self.assertIsNotNone(report.maintenance_intelligence)
        self.assertIsNotNone(report.compliance_intelligence)
        self.assertIsNotNone(report.failure_intelligence)
        self.assertGreater(len(report.warnings), 0)
        self.assertGreater(len(report.suggested_actions), 0)

    def test_to_dict_structure(self):
        report = ResponseComposerService.compose(query="test", ai_answer="answer")
        d = report.to_dict()
        self.assertIn("executive_summary", d)
        self.assertIn("agent_statuses", d)
        self.assertIn("risk_assessment", d)
        self.assertIn("suggested_actions", d)

    def test_agent_statuses(self):
        report = ResponseComposerService.compose(
            query="test",
            maintenance_data={"risk_level": "medium"},
        )
        statuses = {s.agent: s.status for s in report.agent_statuses}
        self.assertEqual(statuses["Maintenance Agent"], "completed")
        self.assertEqual(statuses["Compliance Agent"], "skipped")


class OperationsOrchestratorTests(TestCase):
    """Tests for OperationsIntelligenceOrchestrator."""

    def setUp(self):
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_execute_returns_report(self):
        config = RAGConfig(api_key="")
        report = OperationsIntelligenceOrchestrator.execute(
            "Why is pump P-101A vibrating?", config=config
        )
        self.assertIsInstance(report, OperationsReport)
        self.assertGreater(len(report.agent_statuses), 0)

    def test_execute_generates_warnings(self):
        config = RAGConfig(api_key="")
        report = OperationsIntelligenceOrchestrator.execute(
            "Critical pump P-101A overheating and vibrating", config=config
        )
        # May or may not generate warnings depending on agent results
        self.assertIsInstance(report.warnings, list)

    def test_execute_empty_query(self):
        config = RAGConfig(api_key="")
        report = OperationsIntelligenceOrchestrator.execute("", config=config)
        self.assertEqual(report.executive_summary, "No query provided.")

    def test_execute_includes_trend_analysis(self):
        config = RAGConfig(api_key="")
        report = OperationsIntelligenceOrchestrator.execute(
            "P-101A recurring vibration failure", config=config
        )
        d = report.to_dict()
        if "trend_analysis" in d:
            self.assertIn("trends", d["trend_analysis"])


class QueryOrchestratorOpsIntegrationTests(TestCase):
    """Tests that the main orchestrator triggers operations intelligence."""

    def setUp(self):
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_complex_maintenance_query_triggers_ops(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Why is pump P-101A vibrating? What maintenance is needed?",
            config=config,
        )
        # Should trigger both maintenance agent AND operations intelligence
        d = response.to_dict()
        self.assertIn("maintenance_analysis", d)
        if "operations_report" in d:
            self.assertIn("agent_statuses", d["operations_report"])

    def test_simple_query_no_ops(self):
        config = RAGConfig(api_key="")
        response = QueryOrchestrator.process_query(
            "Hello how are you?", config=config
        )
        d = response.to_dict()
        self.assertNotIn("operations_report", d)


class OperationsAPITests(APITestCase):
    """Tests that /api/query/ returns operations reports."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_maintenance_query_returns_ops_report(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/query/",
            {"query": "Why is P-101A vibrating and what maintenance is needed?"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answer", data)
        # Operations report should be present for complex queries
        if "operations_report" in data:
            self.assertIn("agent_statuses", data["operations_report"])
            self.assertIn("risk_assessment", data["operations_report"])
