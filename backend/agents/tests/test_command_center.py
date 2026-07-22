"""
Tests for the Operations Command Center and Executive Briefing.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from agents.briefing import ExecutiveBriefing, ExecutiveBriefingService
from agents.composer import OperationsReport, ResponseComposerService
from agents.config import RAGConfig
from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity

User = get_user_model()


class ExecutiveBriefingServiceTests(TestCase):
    """Tests for the Executive Briefing Service."""

    def test_generate_without_api_key(self):
        config = RAGConfig(api_key="")
        report = ResponseComposerService.compose(query="test", ai_answer="test answer")
        briefing = ExecutiveBriefingService.generate(report=report, config=config)
        self.assertIsInstance(briefing, ExecutiveBriefing)
        self.assertGreater(len(briefing.text), 0)
        self.assertIn(briefing.plant_health, ("good", "fair", "poor", "critical"))
        self.assertIn(briefing.overall_risk, ("low", "medium", "high", "critical"))

    def test_generate_from_report_dict(self):
        config = RAGConfig(api_key="")
        data = {
            "risk_assessment": {"overall_risk": "high"},
            "warnings": [{"severity": "CRITICAL", "title": "Test"}],
        }
        briefing = ExecutiveBriefingService.generate(report_dict=data, config=config)
        self.assertEqual(briefing.plant_health, "critical")
        self.assertEqual(briefing.critical_alert_count, 1)

    def test_generate_healthy_plant(self):
        config = RAGConfig(api_key="")
        data = {"risk_assessment": {"overall_risk": "low"}, "warnings": []}
        briefing = ExecutiveBriefingService.generate(report_dict=data, config=config)
        self.assertEqual(briefing.plant_health, "good")
        self.assertIn("nominal", briefing.text.lower())

    def test_to_dict(self):
        config = RAGConfig(api_key="")
        briefing = ExecutiveBriefingService.generate(report_dict={}, config=config)
        d = briefing.to_dict()
        self.assertIn("text", d)
        self.assertIn("plant_health", d)
        self.assertIn("overall_risk", d)
        self.assertIn("compliance_score", d)
        self.assertIn("confidence", d)


class CommandCenterViewTests(TestCase):
    """Tests for the Command Center page."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def test_command_center_renders(self):
        self.client.login(username="alex", password="testpass123")
        response = self.client.get(reverse("dashboard:command-center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations Command Center")
        self.assertContains(response, "command-center.js")
        self.assertContains(response, "command-center.css")

    def test_command_center_has_csrf(self):
        self.client.login(username="alex", password="testpass123")
        response = self.client.get(reverse("dashboard:command-center"))
        self.assertIn("csrftoken", response.cookies)


class CommandCenterAPITests(APITestCase):
    """Tests for the command center API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        GraphService.reset()
        GraphService.add_entity(Entity(
            entity_id="e1", entity_type="pump", name="P-101A",
            source_document_ids=["doc-1"],
        ))

    def test_command_center_endpoint(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/command-center/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("plant_health", data)
        self.assertIn("overall_risk", data)
        self.assertIn("compliance_score", data)
        self.assertIn("kpis", data)
        self.assertIn("knowledge_graph", data)

    def test_command_center_requires_auth(self):
        response = self.client.get("/api/command-center/")
        self.assertEqual(response.status_code, 403)

    def test_briefing_endpoint(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/briefing/",
            {"query": "Daily briefing"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("briefing", data)
        self.assertIn("text", data["briefing"])
        self.assertIn("plant_health", data["briefing"])

    def test_briefing_requires_auth(self):
        response = self.client.post("/api/briefing/", {}, format="json")
        self.assertEqual(response.status_code, 403)
